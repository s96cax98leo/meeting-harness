#!/usr/bin/env python3
"""_record_finalize.py <場次目錄>

把錄製段落 錄音/tracks/seg-*.mov 收成：
  影片/<場次名> <YYYY-MM-DD HH.MM.SS>.mov   H.264 high＋AAC 48 kHz 雙聲道（會議視窗畫面＋混音）
  錄音/<場次名> <YYYY-MM-DD HH.MM.SS>.wav   16 kHz 單聲道（轉錄輸入）
做法照 design.md §7.4（D7 整支重編補尾、D8 統一尺寸，合成一次轉碼；D20 兩軌混音、時間戳正規化）：
  1. ffprobe 每段，各軌長度一律由「可解碼的封包」算（不採 stream／format 層 duration，被中斷的 fragment 檔會高報）；
     只有完全讀不到可解碼封包的段（例如沒有 moov 的非 fragment 檔）略過並列出；
  2. 畫布＝(各段寬最大值, 各段高最大值)；位元率＝max(各段影片位元率)×1.5、下限 8 Mb/s；
  3. 逐段正規化成 tracks/.finalize/norm-NNNN.mov：所有軌以同一原點平移（保留段內音影相對位置）、
     影片 -fps_mode passthrough -enc_time_base demux（不重取樣影格、不丟幀、時間基準不變粗）、重複 PTS 只留一個、
     pad 置中補黑邊（不縮放、不裁切）、影片短於段落時以最後一幀補尾、沒有影片的段以前一段最後一幀（第一段則黑畫面）補；
     系統聲音與麥克風兩軌等權混音＋限幅（-1 dBFS），音訊統一 48 kHz 雙聲道 PCM（pcm_s16le，不在這一步編 AAC；
     -t 微秒精度截在段落長，PCM 沒有 priming 也沒有封包補零，解碼長度＝時間戳長度）；正規化後條件不成立即失敗；
  4. concat demuxer 串接：影片 -c:v copy、音訊 -c:a aac 256k 全片一次編碼（缺陷 J：-c copy 會丟掉每段 AAC 的
     edit list，priming 與補零變成真的音訊、逐段延後；spec §4.6.20），以 -enc_time_base demux 確認可完整解碼、
     以 ffprobe 確認每條軌 dts 嚴格遞增；
  5. 由串接結果抽 wav（.part）；
  6. 影片 rename 進 影片/；manifest.json 寫回 gapStats（R2：暫停邊界扣暫停長度、pausedTotal，spec §3.11）、各段 audioDuration、outputCanvas、outputVideoBitrate（其他鍵不動）；
     寫 finalize.json；
  7. 最後才把 wav rename 進 錄音/（同一檔案系統，原子）——場次在這一刻才存在，finalize 期間不會被 status／prep 列出；
  8. 清掉 .finalize/；.pipeline-state.json 記 record: done。
R2：一開始（已完成判斷之前）把 tracks/markers.json 原樣複製成 錄音/markers.json（內容相同不重寫，spec §4.19.3）。
冪等：finalize.json 存在、兩個輸出都在、輸入段（檔名＋大小）相同 → 印「已完成」回 0，不寫任何檔。
收尾成功後刪 tracks/seg-*.mov（manifest、record.meta.json、finalize.json 留著；keep-segments 或 MH_KEEP_SEGMENTS=1 時保留，spec §6 第 111 條）。
段落只刪掉一部分（刪檔失敗）的場次：剩下的段落都在 finalize.json 的輸入裡、成品都在 → 視為已完成並重試清除，不拿殘缺段落重做。

結束碼：0 完成或已完成；2 參數錯；3 沒有段落或全部讀不到；5 失敗（段落保留）。
環境變數：MH_FFMPEG（ffmpeg 路徑，可為測試替身）、MH_FFPROBE、MH_RECORD_HOME（讀 record.defaults.json 的 ffmpeg 路徑）。
"""
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time

AAC_RATE = "256k"
MIN_BITRATE = 8_000_000
VIDEO_TIMESCALE = "90000"
TAIL_PAD_MIN = 0.01       # 影片比段落短超過這麼多就以最後一幀複製補尾（§4.6.3）
CLOSE_GAP = 1 / 60 - 0.001  # 「過近」的相鄰影格間隔（spec §4.3.3 (ii)）：finalize 每個段落邊界最多只能製造 1 個
TAIL_SNAP = 0.01          # 依連結影格率下一幀落在段落結束前這麼多秒內就算已到結尾（grid_reaches_end）
CLONE_SNAP = 1 / 60       # 補尾的複製幀落在 cap 前這麼多秒內就併進 cap（複製幀與 cap 之間不留過近間隔）
TAIL_CAP_MARGIN = 0.005   # 補尾上限 cap＝段落長−5 ms（不依連結影格率，design.md §7.4 第 3 步、spec §4.6.17／§4.6.18）
LATE_VIDEO_MIN = 0.001    # 影片比原點 O 晚這麼多才把第一幀往前延到 0
LIMIT = 0.891             # 混音後限幅上限 -1 dBFS（design.md §7.4）
NORM_START_MAX = 0.05     # 正規化後每條軌 start_time 必須在 [0, 0.05] 秒
NORM_LENGTH_TOL = 0.05    # 正規化後各軌長與段落長差必須 < 50 ms
KEYFRAME_EVERY = 2.0      # 正規化時每 2 秒強制一個關鍵幀（以時間計，VFR 也一致；兼顧拖曳定位）
GOP_FRAMES_MAX = 100000   # 以影格數計的 GOP 上限設到用不到，關鍵幀只由 KEYFRAME_EVERY 決定（缺陷 N）


class FinalizeError(Exception):
    pass


def say(msg):
    print(msg, flush=True)


def record_home():
    return os.environ.get("MH_RECORD_HOME") or os.path.expanduser("~/.meeting-harness")


def keep_segments():
    """收尾成功後是否保留原始段落：MH_KEEP_SEGMENTS=1 或 <record home>/keep-segments 存在（實機驗收要用段落時）。"""
    return os.environ.get("MH_KEEP_SEGMENTS") == "1" or os.path.exists(os.path.join(record_home(), "keep-segments"))


def cleanup_segments(segs):
    """收尾成功（成品已通過長度檢查、wav 已原子出現）後刪掉原始段落：內容與 影片/ 重疊，空間加倍（spec §6 第 111 條）。
    manifest、record.meta.json、levels、finalize.json 留著。"""
    if keep_segments():
        say("  保留原始段落（keep-segments）")
        return
    removed = 0
    for p in segs:
        try:
            os.remove(p)
            removed += 1
        except OSError as e:
            say(f"  ⚠ 刪不掉 {os.path.basename(p)}：{e}")
    say(f"  已刪除原始段落 {removed} 個（成品已驗證；內容與 影片/ 重疊）")


def finalized_without_segments(sess, tracks):
    """原始段落已在收尾成功後刪掉：finalize.json 記的成品都還在 → 已完成。"""
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    if not isinstance(fin, dict):
        return None
    outs = fin.get("outputs") or {}
    paths = [os.path.join(sess, outs.get(k, "")) for k in ("video", "audio")]
    if all(outs.get(k) for k in ("video", "audio")) and all(os.path.isfile(p) for p in paths):
        return paths
    return None


def finalized_with_partial_cleanup(sess, tracks, segs):
    """上次收尾成功、清除段落時只刪掉一部分：剩下的段落是 finalize.json 輸入的真子集、成品都在。
    這時不得用殘缺的段落重做收尾、覆蓋好的成品（ultrareview）。"""
    done = finalized_without_segments(sess, tracks)
    if not done:
        return None
    fin = load_json(os.path.join(tracks, "finalize.json"), None) or {}
    recorded = [(d.get("file"), d.get("size")) for d in fin.get("inputs") or [] if isinstance(d, dict)]
    now = [(d["file"], d["size"]) for d in input_list(segs)]
    if now and len(now) < len(recorded) and set(now) <= set(recorded):
        return done
    return None


def defaults_ffmpeg():
    home = record_home()
    try:
        with open(os.path.join(home, "record.defaults.json"), encoding="utf-8") as f:
            v = json.load(f).get("ffmpeg")
        return v if isinstance(v, str) and os.path.isfile(v) else None
    except (OSError, ValueError, AttributeError):
        return None


def find_tool(name, env):
    """MH_FFMPEG／MH_FFPROBE → record.defaults.json → PATH → Homebrew 常見路徑。
    錄製器由 GUI 啟動時 PATH 沒有 /opt/homebrew/bin，所以要有後面幾層。"""
    v = os.environ.get(env)
    if v:
        return v
    if name == "ffmpeg":
        d = defaults_ffmpeg()
        if d:
            return d
    elif name == "ffprobe":
        d = defaults_ffmpeg()
        if d and os.path.isfile(os.path.join(os.path.dirname(d), "ffprobe")):
            return os.path.join(os.path.dirname(d), "ffprobe")
    w = shutil.which(name)
    if w:
        return w
    for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.isfile(p):
            return p
    return name


FFMPEG = find_tool("ffmpeg", "MH_FFMPEG")
FFPROBE = find_tool("ffprobe", "MH_FFPROBE")


def ffmpeg(*args, what=""):
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FinalizeError(f"ffmpeg 失敗（{what}）：{r.stderr.strip()[-800:]}")
    return r


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def first_stream(info, kind):
    for s in info.get("streams", []):
        if s.get("codec_type") == kind:
            return s
    return None


def stream_start(s):
    """套用 edit list 之後的呈現起點（ffprobe stream 層的 start_time）；讀不到時回 None。"""
    return num((s or {}).get("start_time"))


def packets_by_stream(path, keep_discard=False):
    """每條軌的封包（pts、duration、flags）；略過標了 D（discard，例如 AAC priming）或 C（corrupt，
    例如被中斷的 fragment 檔最後半個封包）的封包——只留「可解碼」的部分（design.md §7.4 第 1 步）。"""
    r = subprocess.run([FFPROBE, "-v", "quiet", "-show_entries", "packet=stream_index,pts_time,duration_time,flags",
                        "-of", "json", str(path)], capture_output=True, text=True)
    out = {}
    try:
        pkts = json.loads(r.stdout or "{}").get("packets") or []
    except ValueError:
        return out
    for k in pkts:
        flags = k.get("flags") or ""
        if "C" in flags or ("D" in flags and not keep_discard):
            continue
        pts = num(k.get("pts_time"))
        if pts is None:
            continue
        idx = k.get("stream_index")
        out.setdefault(idx, []).append((pts, num(k.get("duration_time")) or 0.0))
    return out


def analyze(path):
    """第 1 步：一段的軌道資訊。長度一律由封包算（最後一個可解碼封包的 pts＋duration − 起點），
    不採 stream／format 層的 duration（中斷的 fragment 檔會高報，spec §4.6.15）。
    完全讀不到可解碼封包的段回 None（略過，spec §4.6.9）。"""
    info = probe(path)
    if not info:
        return None
    pk = packets_by_stream(path)
    video, audios = None, []
    for s in info.get("streams", []):
        kind = s.get("codec_type")
        if kind not in ("video", "audio"):
            continue
        rows = pk.get(s.get("index")) or []
        if not rows:
            continue
        start = stream_start(s)
        first = min(p for p, _ in rows)
        if start is None:
            start = first
        end = max(p + d for p, d in rows)
        t = {"stream": s, "start": start, "end": end, "length": max(end - min(start, first), 0.0)}
        if kind == "video":
            if video is None:
                pts = [p for p, _ in rows]
                t["frames"] = len(pts)
                t["dups"] = len(pts) - len(set(pts))
                t["last_pts"] = max(pts)
                video = t
        else:
            audios.append(t)
    if video is None and not audios:
        return None
    tracks = ([video] if video else []) + audios
    origin = min(t["start"] for t in tracks)
    end = max(t["end"] for t in tracks)
    return {"info": info, "video": video, "audios": audios, "origin": origin, "length": end - origin,
            "audioDuration": max((t["length"] for t in audios), default=None)}


def link_fps(s):
    """ffmpeg 給解碼輸出連結的影格率（大致等於 av_guess_frame_rate：先取 r_frame_rate）。
    tpad 依這個影格率補幀，尾端補幀要以它推算要補幾幀（補尾上限 cap 不依它，見 normalize）。"""
    for k in ("r_frame_rate", "avg_frame_rate"):
        v = (s or {}).get(k, "")
        if "/" in v:
            a, b = v.split("/", 1)
            if num(a) and num(b):
                f = num(a) / num(b)
                if 1 <= f <= 1000:
                    return f
    return 30.0


def tick_floor(t, s):
    """t 往下對齊到 stream s 的 time_base tick（讀不到 time_base 時原值）。"""
    tb = (s or {}).get("time_base", "")
    if "/" in tb:
        a, b = tb.split("/", 1)
        if num(a) and num(b) and num(a) > 0 and num(b) > 0:
            step = num(a) / num(b)
            return math.floor(t / step + 1e-6) * step
    return t


def even_up(n):
    n = int(n)
    return n + (n % 2)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def input_list(segs):
    return [{"file": os.path.basename(p), "size": os.path.getsize(p)} for p in segs]


def already_done(sess, tracks, segs):
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    if not isinstance(fin, dict):
        return None
    outs = fin.get("outputs") or {}
    paths = [os.path.join(sess, outs.get(k, "")) for k in ("video", "audio")]
    if all(outs.get(k) for k in ("video", "audio")) and all(os.path.isfile(p) for p in paths) \
            and fin.get("inputs") == input_list(segs):
        return paths
    return None


def paused_total(events):
    """spec §3.14 pausedTotal：Σ（resume.t − 緊接在前的 pause.t）；沒配對的 pause、沒有前導 pause 的 resume 不計；小數 3 位。"""
    total, last_pause = 0.0, None
    for e in events:
        t = num(e.get("t"))
        if t is None:
            continue
        if e.get("kind") == "pause":
            last_pause = t
        elif e.get("kind") == "resume":
            if last_pause is not None:
                total += t - last_pause
            last_pause = None
    return round(total, 3)


def pause_events_of(tracks):
    """record.meta.json 的 pauseEvents（R2，§3.11）；沒有或格式不對 → []。"""
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    ev = meta.get("pauseEvents") if isinstance(meta, dict) else None
    return [e for e in ev if isinstance(e, dict)] if isinstance(ev, list) else []


def has_pause_events_key(tracks):
    """record.meta.json 有 pauseEvents 鍵（R2 錄製器開錄就寫 []）。"""
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    return isinstance(meta, dict) and "pauseEvents" in meta


def pause_length_before(events, resume_t):
    """邊界上那筆 resume 的暫停長度（resume.t − 前一筆 pause.t）；找不到前導 pause → 0。"""
    for k, e in enumerate(events):
        if e.get("kind") == "resume" and num(e.get("t")) == resume_t:
            for prev in reversed(events[:k]):
                if prev.get("kind") == "pause" and num(prev.get("t")) is not None:
                    return resume_t - num(prev["t"])
                if prev.get("kind") == "resume":
                    return 0.0
            return 0.0
    return 0.0


def boundary_gaps(used, events):
    """spec §3.2＋§3.11：g_k＝startedAt_{k+1} − startedAt_k − audioDuration_k；暫停邊界（有 resume.t 與
    startedAt_{k+1} 相差 < 0.5 秒）再扣掉該次暫停長度。"""
    resumes = [num(e.get("t")) for e in events if e.get("kind") == "resume" and num(e.get("t")) is not None]
    gaps = []
    for k in range(len(used) - 1):
        nxt = used[k + 1]["startedAt"]
        g = nxt - used[k]["startedAt"] - used[k]["audioDuration"]
        near = [r for r in resumes if abs(r - nxt) < 0.5]
        if near:
            r = min(near, key=lambda x: abs(x - nxt))
            g -= pause_length_before(events, r)
        gaps.append(round(g, 3))
    return gaps


def copy_markers(rec, tracks):
    """spec §3.12、§4.19.3：tracks/markers.json 原樣複製成 錄音/markers.json；內容相同就不重寫（mtime 不變）。"""
    src = os.path.join(tracks, "markers.json")
    if not os.path.isfile(src):
        return
    dst = os.path.join(rec, "markers.json")
    with open(src, "rb") as f:
        data = f.read()
    try:
        with open(dst, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    tmp = dst + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dst)


def session_stamp(segs, fin_old):
    """輸出檔名的時間戳：沿用上次 finalize.json 的值，否則取第一段的建立時間（≈開錄時間）。"""
    if isinstance(fin_old, dict) and isinstance(fin_old.get("stamp"), str):
        return fin_old["stamp"]
    st = os.stat(segs[0])
    t = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H.%M.%S")


def encoders():
    """videotoolbox 不能用時（例如沒有硬體編碼器的環境）退回 libx264，參數同為 high profile。
    關鍵幀一律以時間計（每 KEYFRAME_EVERY 秒強制一個），以影格數計的 GOP 設成用不到：h264_videotoolbox
    沒指定 -g 時預設每 12 幀一個關鍵幀，稀疏 VFR 段的關鍵幀位置隨影格數漂移（缺陷 N 的觸發條件之一）。
    不用 B 幀（-bf 0）：解碼順序＝呈現順序，最後一個封包就是最後一幀，encode() 才能可靠地設它的長度。"""
    gop = ["-g", GOP_FRAMES_MAX, "-bf", 0,
           "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_EVERY:g})"]
    return [["-c:v", "h264_videotoolbox", "-profile:v", "high", *gop],
            ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium", *gop]]


def encode(inputs, graph, out, *, dur, bitrate, what=""):
    """graph 輸出 [v] 與 [a]。影片 -fps_mode passthrough -enc_time_base demux：保留原始影格時間、
    編碼器沿用輸入 stream 的時間基準（不讓 ffmpeg 依影格率猜，t6 缺陷 3 的根因 (a)）。
    音訊寫 PCM（pcm_s16le）：AAC 只在第 4 步串接時全片編一次（缺陷 J，design.md §7.4 第 3 步）。
    影片最後一個封包的長度設到段落結束 dur（至少 1 tick）：mov muxer 以「最後一幀 PTS＋長度」寫 edit list，
    長度只有 1 tick 時 edit list（movie timescale 1/1000）在最後一幀的 PTS 就結束，最後一幀被標 discard；
    倒數第二幀又剛好是關鍵幀時，mov demuxer 在 edit list 結束後遇到關鍵幀就停止建索引，最後一幀
    （例如補尾的複製幀）整個讀不到（缺陷 N 的根因）。"""
    last_dur = f"setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,max(1\\,round({dur:.6f}/TB)-PTS)\\,DURATION)"
    last = None
    for enc in encoders():
        try:
            ffmpeg(*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                   *enc, "-b:v", bitrate, "-maxrate", 2 * bitrate, "-bufsize", 4 * bitrate, "-pix_fmt", "yuv420p",
                   "-fps_mode", "passthrough", "-enc_time_base:v", "demux", "-bsf:v", last_dur,
                   "-video_track_timescale", VIDEO_TIMESCALE,
                   "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                   "-t", f"{dur:.6f}", "-f", "mov", out, what=what)
            return
        except FinalizeError as e:
            last = e
            if os.path.exists(out):
                os.remove(out)
    raise last


def audio_graph(inputs, seg_input, dur):
    """混音（D20）：兩條音軌各自轉成 48 kHz 雙聲道、對齊到同一原點後等權相加（不做 1/2 衰減）再限幅；
    單軌直接用；沒有音軌回 None（呼叫端補靜音）。單聲道以 pan 複製到左右聲道（不走預設 upmix 的 -3 dB）。
    結尾補靜音到段落長 dur（影片比音訊長時，各軌長仍與段落長一致）。
    seg_input 是段落在 ffmpeg 輸入中的序號；回傳 filter 片段（輸出標籤 [a]）。"""
    parts, labels = [], []
    for k, t in enumerate(inputs):
        ch = int(t["stream"].get("channels") or 2)
        up = "pan=stereo|c0=c0|c1=c0" if ch == 1 else "aformat=channel_layouts=stereo"
        lab = f"a{k}"
        parts.append(f"[{seg_input}:{t['stream']['index']}]aresample=48000,{up},"
                     f"aresample=48000:async=1:first_pts=0[{lab}]")
        labels.append(lab)
    tail = f"apad=whole_dur={dur:.6f}[a]"
    if len(labels) >= 2:
        parts.append("".join(f"[{x}]" for x in labels) +
                     f"amix=inputs={len(labels)}:duration=longest:normalize=0,"
                     f"alimiter=limit={LIMIT}:level=0:latency=1,{tail}")
        return ";".join(parts)
    if len(labels) == 1:
        return ";".join(parts).replace(f"[{labels[0]}]", f",{tail}")
    return None


def check_norm(path, seg, a, tail_padded, tail_at=None):
    """第 3 步正規化後必須成立的條件（design.md §7.4）；不成立即 FinalizeError（結束碼 5、段落保留）。
    tail_at：有補尾時補尾幀應在的 PTS（cap）；讀不到落在那裡的影片封包就明確報錯，不以長度容差帶過（缺陷 N）。"""
    name = os.path.basename(seg)
    info = probe(path)
    if not info:
        raise FinalizeError(f"正規化結果讀不到（{name}）")
    pk = packets_by_stream(path)
    all_rows = packets_by_stream(path, keep_discard=True)
    v0 = first_stream(info, "video")
    if tail_at is not None and v0 is not None:
        vp = [p for p, _ in pk.get(v0.get("index")) or []]
        if not vp or max(vp) < tail_at - 0.001:  # 1 ms：只容許時間基準換算的捨入
            got = f"{max(vp):.3f}" if vp else "無"
            raise FinalizeError(f"正規化後補尾幀沒有可讀的封包：最後一幀 {got}，應在 {tail_at:.3f}（{name}）")
    for s in info.get("streams", []):
        st = stream_start(s)
        kind = s.get("codec_type")
        if st is None or not (-0.0005 <= st <= NORM_START_MAX):
            raise FinalizeError(f"正規化後 {kind} 軌起點 {st} 不在 [0, {NORM_START_MAX}] 秒（{name}）")
        rows = pk.get(s.get("index")) or []
        if not rows:
            continue
        # 影片軌長度以「最後一幀的 PTS」計（最後一幀的長度由編碼器與 muxer 決定，串接時再設成 1 tick，
        # 第 4 步），容差 50 ms、不再加一幀（design.md §7.4 第 3 步，t6 第二輪）
        if kind == "video":
            length = max((p for p, _ in all_rows.get(s.get("index"), rows)), default=0.0)
        else:
            length = max(p + d for p, d in rows) - st
        if abs(length - a["length"]) >= NORM_LENGTH_TOL:
            raise FinalizeError(f"正規化後 {kind} 軌長 {length:.3f} 與段落長 {a['length']:.3f} 不符（{name}）")
    v = first_stream(info, "video")
    if v is None:
        raise FinalizeError(f"正規化結果沒有影片軌（{name}）")
    dts = packet_dts(path, "v:0")
    if any(y <= x for x, y in zip(dts, dts[1:])):
        raise FinalizeError(f"正規化後影片 dts 不是嚴格遞增（{name}）")
    if a["video"] is not None:
        # 不得以丟幀換取遞增：至少要有「輸入影格數 − 重複 PTS 數」；解碼器若已自行錯開重複 PTS，影格可以一張不少
        want = a["video"]["frames"] - a["video"]["dups"]
        got = len(dts)
        if got < want or (not tail_padded and got > a["video"]["frames"]):
            raise FinalizeError(f"正規化後影格數 {got} 與預期 {want} 不符（{name}）")


def packet_dts(path, sel):
    r = subprocess.run([FFPROBE, "-v", "quiet", "-select_streams", sel, "-show_entries", "packet=dts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    out = []
    for x in r.stdout.split():
        x = x.split(",")[0].strip()
        if x and x != "N/A":
            out.append(float(x))
    return out


def normalize(i, seg, a, prev_norm, work, W, H, bitrate):
    """第 3 步：一段正規化成 norm-NNNN.mov。
    時間戳：ffmpeg 預設以輸入檔最早的 start_time（＝各軌起點最小值 O）為原點、所有軌同一個原點平移，
    保留段內音影相對位置；影片晚於 O 開始時把第一幀往前延到 0，音訊晚於 O 開始時前面補靜音；
    完全相同 PTS 的重複影格只留第一個。"""
    v, audios = a["video"], a["audios"]
    dur = a["length"]
    out = os.path.join(work, f"norm-{i:04d}.mov")
    pad = f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    ag = audio_graph(audios, 0 if v is not None else 1, dur)
    tail_padded, tail_at = False, None
    if v is not None:
        inputs = ["-i", seg]
        # 尾端：補尾上限 cap＝段落長−5 ms（不依連結影格率；稀疏 VFR 段的 r_frame_rate 很低，
        # 舊算法 cap＝段落長−1/fps 會讓最後一段的影片早於音訊結束，缺陷 F）。不到 cap 時以 tpad 複製
        # 最後一幀補到 cap：tpad 依解碼輸出連結的影格率補幀（必須接在 setpts 之前，setpts 之後連結
        # 影格率未知、tpad 不會補），補出的幀 PTS 落在 cap 前 CLONE_SNAP 秒內或之後的一律夾成 cap，
        # 再由 select 丟掉重複 PTS（只留第一個）。影片軌的結束點由串接時把最後一個封包設成 1 tick 決定（第 4 步）。
        # 開頭：影片晚於原點 O 開始時，第一幀往前延到 0（以第一幀往前補）。
        # 一律加 setpts（沒有改動時 setpts=PTS）：實測 h264_videotoolbox 在 -fps_mode passthrough 且濾鏡鏈
        # 沒有 setpts 時，把最後一幀的長度記成 1/av_guess_frame_rate（r_frame_rate 很大而平均影格率低時
        # 改取平均影格率，例約 0.094 秒），正規化後影片軌被拉長而超出段落長（缺陷 B）；有 setpts 時最後一幀反而是短的。
        vi = v["stream"]["index"]
        fps = link_fps(v["stream"])
        cap = tick_floor(dur - TAIL_CAP_MARGIN, v["stream"])
        last = v["last_pts"] - a["origin"]
        late = v["start"] - a["origin"] > LATE_VIDEO_MIN
        exprs = []
        vf = f"[0:{vi}]"
        # 例外：依連結影格率下一幀本來就落在段落結束（前 TAIL_SNAP 秒內）或之後、且最後一幀已在
        # 正規化容差內時，沒有缺幀、不補——補出的幀會被夾到 cap，與下一段首幀只隔 5 ms，
        # 使相鄰影格間隔小於輸入（spec §4.6.10）。稀疏 VFR（缺陷 F）的下一幀遠在段落結束前，不受影響。
        grid_reaches_end = last + 1.0 / fps >= dur - TAIL_SNAP and dur - last < NORM_LENGTH_TOL
        # 例外二（spec §4.3.3 (ii)，t6 第三輪實機 0330 場次）：最後一幀距 cap 不到 CLOSE_GAP 時不補——
        # 補到 cap 的那一幀本身就是過近間隔，再加上 cap 與下一段首幀之間的 5 ms，同一個邊界就有 2 個。
        # 這時最後一幀距段落結束 < CLOSE_GAP＋5 ms，遠在正規化容差（50 ms）內。
        if cap - last >= max(TAIL_PAD_MIN, CLOSE_GAP) and not grid_reaches_end:
            n = int(math.ceil((cap - last) * fps)) + 1
            vf += f"tpad=stop_mode=clone:stop={n},"
            # 只動複製幀（PTS 晚於最後一幀；原始影格一律不動）：tpad 第一個複製幀落在「最後一幀 PTS＋
            # 最後一幀長度」，之後依連結影格率；落在 cap 前 CLONE_SNAP 秒內或之後的一律夾成 cap，
            # 複製幀與 cap 之間不會有過近間隔（舊門檻 10 ms 時，0330 場次 seg-0001 的複製幀 60.000 與
            # cap 60.0133 只隔 13.3 ms）。cap 已對齊輸入 time_base 的 tick；以 round 換算成 tick，
            # 避免浮點除法截斷到前一個 tick
            exprs.append((f"gt(PTS\\,round({last:.9f}/TB))*gt(PTS*TB\\,{cap - CLONE_SNAP:.6f})",
                          f"round({cap:.9f}/TB)"))
            tail_padded, tail_at = True, cap
        if late:
            exprs.insert(0, ("eq(N\\,0)", "0"))
        e = "PTS"
        for cond, val in reversed(exprs):
            e = f"if({cond}\\,{val}\\,{e})"
        vf += f"setpts='{e}',"
        # 去重：原始影格只丟完全相同 PTS 的重複幀；補尾的複製幀（PTS 晚於最後一幀）距前一個留下的影格
        # 不到 CLOSE_GAP 的一律丟掉（spec §4.3.3 (ii)：tpad 第一個複製幀落在「最後一幀 PTS＋最後一幀長度」，
        # 最後一幀很短時會緊貼最後一幀，2254 場次 seg-0007 只隔 6.7 ms；連結影格率很高時複製幀之間也會過近）。
        # 夾到 cap 的那一幀距最後一幀 ≥ CLOSE_GAP（上面的門檻）、距其他複製幀 ≥ CLONE_SNAP，一定留下。
        keep = "gt(pts\\,prev_selected_pts)"
        if tail_padded:
            keep = (f"if(gt(pts\\,round({last:.9f}/TB))\\,"
                    f"gte((pts-prev_selected_pts)*TB\\,{CLOSE_GAP - 1e-6:.9f})\\,{keep})")
        vf += f"select='isnan(prev_selected_pts)+{keep}',{pad}"
        vf += "[v]"
        if ag is None:  # 沒有音訊的段補靜音，讓串接後音訊軌連續
            inputs += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            ag = "[1:a]anull[a]"
        encode(inputs, vf + ";" + ag, out, dur=dur, bitrate=bitrate, what=f"正規化 {os.path.basename(seg)}")
    else:
        fps = 30
        if prev_norm:
            still = os.path.join(work, f"still-{i:04d}.png")
            ffmpeg("-sseof", "-0.5", "-i", prev_norm, "-update", "1", "-frames:v", "1", still,
                   what=f"取前一段最後一幀（{os.path.basename(seg)}）")
            vin = ["-loop", "1", "-framerate", fps, "-t", f"{dur:.3f}", "-i", still]
        else:
            vin = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={fps}:d={dur:.3f}"]
        encode([*vin, "-i", seg], f"[0:v]{pad}[v];{ag}", out, dur=dur, bitrate=bitrate,
               what=f"補影片 {os.path.basename(seg)}")
        tail_padded = True
    check_norm(out, seg, a, tail_padded, tail_at)
    return out


def concat_list(norms, path):
    with open(path, "w", encoding="utf-8") as f:
        for p in norms:
            f.write("file '" + p.replace("'", "'\\''") + "'\n")


def set_state_done(sess):
    sf = os.path.join(sess, ".pipeline-state.json")
    d = load_json(sf, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("stages", {})["record"] = {"status": "done"}
    write_json_atomic(sf, d)


def finalize(sess):
    sess = os.path.abspath(sess)
    name = os.path.basename(sess)
    rec = os.path.join(sess, "錄音")
    tracks = os.path.join(rec, "tracks")
    if not os.path.isdir(tracks):
        print(f"✗ 這個場次沒有 錄音/tracks/：{sess}", file=sys.stderr)
        return 3
    segs = sorted(os.path.join(tracks, f) for f in os.listdir(tracks)
                  if f.startswith("seg-") and f.endswith(".mov"))
    if not segs:
        done = finalized_without_segments(sess, tracks)
        if done:
            copy_markers(rec, tracks)
            say(f"✓ 已完成（不重做；原始段落已在收尾時清除）：{done[0]}")
            return 0
        print(f"✗ 這個場次沒有錄製段落（seg-*.mov）：{tracks}", file=sys.stderr)
        return 3

    copy_markers(rec, tracks)  # 在 already_done 之前（已完成的場次之後才出現 markers 也要補上，§4.19.3）
    partial = finalized_with_partial_cleanup(sess, tracks, segs)
    if partial:
        say(f"✓ 已完成（不重做；上次清除原始段落只刪了一部分，重試清除）：{partial[0]}")
        cleanup_segments(segs)
        return 0
    done = already_done(sess, tracks, segs)
    if done:
        say(f"✓ 已完成（不重做）：{done[0]}")
        return 0

    # 1. 篩掉完全讀不到可解碼封包的段（讀得到部分 fragment 的段照用，spec §4.6.9、§4.6.15）
    good, skipped = [], []
    for p in segs:
        a = analyze(p)
        if a is None:
            skipped.append(os.path.basename(p))
            continue
        good.append((p, a))
    if skipped:
        say("⚠ 略過無法讀取的段落：" + "、".join(skipped))
    if not good:
        print("✗ 所有段落都讀不到，沒有東西可以收尾。", file=sys.stderr)
        return 3

    manifest_path = os.path.join(tracks, "manifest.json")
    manifest = load_json(manifest_path, {})
    if not isinstance(manifest, dict):
        manifest = {}
    seg_meta = {s.get("file"): s for s in manifest.get("segments") or [] if isinstance(s, dict)}

    # 2. 輸出參數
    sizes = []
    rates = []
    for p, a in good:
        v = a["video"]["stream"] if a["video"] else None
        if v:
            sizes.append((int(v.get("width") or 0), int(v.get("height") or 0)))
            br = num(v.get("bit_rate"))
            if br:
                rates.append(br)
        else:
            m = seg_meta.get(os.path.basename(p)) or {}
            if m.get("width") and m.get("height"):
                sizes.append((int(m["width"]), int(m["height"])))
    W = even_up(max((w for w, _ in sizes), default=1280) or 1280)
    H = even_up(max((h for _, h in sizes), default=720) or 720)
    bitrate = int(max(MIN_BITRATE, (max(rates) if rates else 0) * 1.5))

    work = os.path.join(tracks, ".finalize")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    try:
        # 3. 逐段正規化
        norms, ads, prev = [], {}, None
        for i, (p, a) in enumerate(good, start=1):
            out = normalize(i, p, a, prev, work, W, H, bitrate)
            say(f"正規化 {i}/{len(good)}")
            norms.append(out)
            ads[os.path.basename(p)] = a["audioDuration"]
            prev = out

        # 4. 串接：影片同編碼器、同參數、同尺寸 → -c:v copy；音訊（各段 PCM）在這裡一次編成 AAC
        #    （缺陷 J：-c copy 串接 AAC 會丟掉每段的 edit list，priming 與補零變成真的音訊）。確認可完整解碼
        lst = os.path.join(work, "concat.txt")
        concat_list(norms, lst)
        video_tmp = os.path.join(work, "video.mov")
        # 影片最後一個封包的長度設成 1 tick，影片軌在最後一幀的 PTS 結束（其他封包不動；
        # setts=duration=0 無效，mov muxer 會自行估長度）——design.md §7.4 第 4 步，缺陷 F
        ffmpeg("-f", "concat", "-safe", "0", "-i", lst, "-c:v", "copy",
               "-c:a", "aac", "-b:a", AAC_RATE,
               "-bsf:v", "setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,1\\,DURATION)",
               "-movflags", "+faststart", video_tmp, what="串接")
        # -enc_time_base demux：不加的話 null muxer 對任何 VFR 輸入都誤報 non monotonically increasing dts
        chk = subprocess.run([FFMPEG, "-v", "error", "-nostdin", "-i", video_tmp, "-enc_time_base", "demux",
                              "-f", "null", "-"], capture_output=True, text=True)
        if chk.returncode != 0 or chk.stderr.strip():
            raise FinalizeError(f"串接結果無法完整解碼：{chk.stderr.strip()[-800:]}")
        for sel in ("v:0", "a:0"):
            dts = packet_dts(video_tmp, sel)
            if not dts or any(y <= x for x, y in zip(dts, dts[1:])):
                raise FinalizeError(f"串接結果 {sel} 的封包 dts 不是嚴格遞增")

        # 5. 抽 wav
        wav_tmp = os.path.join(work, "audio.wav.part")
        ffmpeg("-i", video_tmp, "-map", "0:a:0", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav",
               wav_tmp, what="抽 wav")
    except FinalizeError as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  段落都還在（錄音/tracks/），修好後可以再跑一次 meeting record finish。", file=sys.stderr)
        return 5

    # 6. 影片就位、manifest、finalize.json
    fin_old = load_json(os.path.join(tracks, "finalize.json"), None)
    stamp = session_stamp([p for p, _ in good], fin_old)
    base = f"{name} {stamp}"
    vid_dir = os.path.join(sess, "影片")
    os.makedirs(vid_dir, exist_ok=True)
    video_out = os.path.join(vid_dir, base + ".mov")
    wav_out = os.path.join(rec, base + ".wav")
    os.replace(video_tmp, video_out)

    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    for s in segments:
        if isinstance(s, dict) and s.get("file") in ads:
            s["audioDuration"] = round(ads[s["file"]], 3) if ads[s["file"]] is not None else None
    used = [s for s in segments if isinstance(s, dict) and s.get("file") in ads
            and num(s.get("startedAt")) is not None and s.get("audioDuration") is not None]
    pevents = pause_events_of(tracks)
    gaps = boundary_gaps(used, pevents)
    wall = num(segments[-1].get("finishedAt")) if segments and isinstance(segments[-1], dict) else None
    if wall is None:
        wall = round(sum(a for a in ads.values() if a), 3)
    manifest["gapStats"] = {"boundaries": gaps, "max": max(gaps) if gaps else 0.0,
                            "total": round(sum(gaps), 3), "wallClock": wall}
    # pausedTotal 只寫給 R2 錄製器的場次（meta 有 pauseEvents 鍵）；第一輪場次維持 4 個鍵（spec §6 第 100 條）
    if has_pause_events_key(tracks):
        manifest["gapStats"]["pausedTotal"] = paused_total(pevents)
    manifest["outputCanvas"] = {"width": W, "height": H}
    manifest["outputVideoBitrate"] = bitrate
    write_json_atomic(manifest_path, manifest)
    write_json_atomic(os.path.join(tracks, "finalize.json"), {
        "schemaVersion": 1, "stamp": stamp, "inputs": input_list(segs), "skipped": skipped,
        "outputs": {"video": os.path.relpath(video_out, sess), "audio": os.path.relpath(wav_out, sess)},
        "finishedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z")})

    # 7. 最後一步：wav 原子出現在 錄音/ 第一層
    os.replace(wav_tmp, wav_out)

    # 8. 清暫存、記狀態
    shutil.rmtree(work, ignore_errors=True)
    set_state_done(sess)
    cleanup_segments(segs)
    say(f"✓ 影片：{video_out}")
    say(f"✓ 錄音：{wav_out}")
    if gaps:
        say(f"  段落空隙：最大 {max(gaps):.3f} 秒、合計 {sum(gaps):.3f} 秒")
    return 0


def main(argv):
    if len(argv) != 1 or not argv[0]:
        print("✗ 用法：_record_finalize.py <場次目錄>", file=sys.stderr)
        return 2
    if not os.path.isdir(argv[0]):
        print(f"✗ 找不到場次目錄：{argv[0]}", file=sys.stderr)
        return 2
    try:
        return finalize(argv[0])
    except (OSError, FinalizeError) as e:
        print(f"✗ 收尾失敗：{e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

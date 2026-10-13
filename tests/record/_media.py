"""合成素材（只在 TMPDIR 產生；repo 內不得留下任何媒體檔，spec §4.14.1）。"""
import json
import random
import shutil
import subprocess
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"

SESSION_NAME = "範例場次"
DAY = "20261011"

CONFIG_SNAPSHOT = {
    "filter": "desktopIndependentWindow", "onScreenWindowsOnly": False, "scalesToFit": True,
    "minimumFrameInterval": "1/60", "capturesAudio": True, "sampleRate": 48000, "channelCount": 2,
    "captureMicrophone": True, "microphoneCaptureDeviceID": None, "excludesCurrentProcessAudio": True,
    "fileType": "mov", "videoCodec": "h264", "segmentSeconds": 60,
}

MEETING_JSON = {"type": "internal", "date": "2026-10-11", "attendees": [], "expectedSpeakers": None,
                "language": "zh", "llm": "claude", "_note": "錄製器建立的草稿（範例）"}


def ff(*args):
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 失敗：{r.stderr}")


def probe(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def stream(path, kind):
    info = probe(path)
    if not info:
        return None
    for s in info["streams"]:
        if s.get("codec_type") == kind:
            return s
    return None


def streams(path, kind):
    info = probe(path) or {"streams": []}
    return [s for s in info["streams"] if s.get("codec_type") == kind]


def stream_duration(path, kind):
    s = stream(path, kind)
    return float(s["duration"]) if s and s.get("duration") not in (None, "N/A") else None


def make_segment(path, *, w=320, h=240, dur=2.0, vdur=None, video="testsrc2", fps=30, ar=48000, ac=2,
                 freq=440, recipe=None, **kw):
    """一段 .mov：H.264＋AAC。vdur 為影片長（預設＝dur）；video=None 表示沒有影片軌。

    recipe 不為 None 時改用 RECIPES 裡的配方（D20 的合成素材，spec §4.6.13–4.6.15），其餘參數照該配方的定義。
    """
    if recipe is not None:
        return RECIPES[recipe](path, w=w, h=h, dur=dur, **kw)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = []
    vdur = dur if vdur is None else vdur
    if video is not None:
        src = f"testsrc2=s={w}x{h}:r={fps}:d={vdur}" if video == "testsrc2" else \
              f"color=c={video}:s={w}x{h}:r={fps}:d={vdur}"
        args += ["-f", "lavfi", "-i", src]
    args += ["-f", "lavfi", "-i", f"sine=f={freq}:sample_rate={ar}:d={dur}"]
    if video is not None:
        args += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-b:v", "800k"]
    args += ["-ac", str(ac), "-ar", str(ar), "-c:a", "aac", "-b:a", "128k", "-f", "mov", path]
    ff(*args)
    return path


def sine_amp(rms_db):
    """正弦波的振幅，使其 RMS 為 rms_db dBFS（正弦 RMS＝振幅／√2）。"""
    return round(10 ** (rms_db / 20) * 2 ** 0.5, 6)


def make_two_track_segment(path, *, w=320, h=240, dur=2.0, fps=30, sys_freq=440, mic_freq=1000, level_db=-20.0,
                           sys_dur=None):
    """D20 段落（spec §4.4.1、§4.6.13）：影片＋音軌 0（系統聲音：sys_freq 正弦、雙聲道 48 kHz）
    ＋音軌 1（麥克風：mic_freq 正弦、單聲道 48 kHz），兩條正弦的 RMS 都是 level_db dBFS。
    sys_dur 為系統聲音音軌長（預設＝dur）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    amp = sine_amp(level_db)
    sd = dur if sys_dur is None else sys_dur
    ff("-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r={fps}:d={dur}",
       "-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*{sys_freq}*t)':s=48000:c=stereo:d={sd}",
       "-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*{mic_freq}*t)':s=48000:c=mono:d={dur}",
       "-map", "0:v", "-map", "1:a", "-map", "2:a",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-b:v", "800k",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac:a:0", "2", "-ac:a:1", "1", "-f", "mov", path)
    return path


# spec §4.6.14 配方 (A)：實機 SCK 段落的時間戳特性（VFR、time_base=1/600、has_b_frames=2）
IRREGULAR_SETPTS = "setpts='(N*60+mod(N*37\\,23))/600/TB'"


def make_irregular_segment(path, *, w=320, h=240, dur=4.0, freq=440):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=10:d={dur}",
       "-f", "lavfi", "-i", f"sine=f={freq}:sample_rate=48000:d={dur}",
       "-vf", IRREGULAR_SETPTS, "-c:v", "libx264", "-profile:v", "high", "-bf", "2", "-pix_fmt", "yuv420p",
       "-fps_mode", "passthrough", "-enc_time_base", "1/600", "-video_track_timescale", "600",
       "-c:a", "aac", "-ar", "48000", "-ac", "2", "-f", "mov", path)
    return path


def make_late_video_sync_segment(path, *, w=320, h=180, dur=9.0, video_delay=0.2, audio_shift=0.021):
    """spec §4.6.14 配方 (B)：同步測試源（閃白＋嗶聲），影片 trim=start=video_delay（不重設 PTS）晚開始，
    音訊以 asetpts 往前移 audio_shift 秒、-avoid_negative_ts disabled 寫成負的 start_time。"""
    from tests.record.e2e_check import sync_source_graph

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    vg, ag = sync_source_graph(duration=dur)
    vg = vg.replace("s=640x360", f"s={w}x{h}").replace("r=60", "r=30")
    ff("-f", "lavfi", "-i", vg, "-f", "lavfi", "-i", ag,
       "-filter_complex", f"[0:v]trim=start={video_delay}[v];[1:a]asetpts=PTS-{audio_shift}/TB[a]",
       "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-ar", "48000", "-ac", "2", "-avoid_negative_ts", "disabled", "-f", "mov", path)
    return path


def make_fragment_segment(path, *, w=320, h=240, dur=10.0, fps=30, freq=440, keep=0.6):
    """spec §4.6.15：fragment 檔（+frag_keyframe+empty_moov、-frag_duration 2000000、-g 30），
    寫完後只留前 keep 比例的位元組（截掉後 40%），模擬寫到一半被 kill -9 的 D20 段落。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r={fps}:d={dur}",
       "-f", "lavfi", "-i", f"sine=f={freq}:sample_rate=48000:d={dur}",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-g", "30",
       "-c:a", "aac", "-ar", "48000", "-ac", "2",
       "-movflags", "+frag_keyframe+empty_moov", "-frag_duration", "2000000", "-f", "mov", path)
    data = path.read_bytes()
    path.write_bytes(data[:int(len(data) * keep)])
    return path


def _two_aac_inputs(dur=None):
    """兩條音軌的 lavfi 輸入（spec §4.6.17／§4.6.18）：440 Hz 正弦雙聲道、1000 Hz 正弦單聲道，48 kHz、-20 dBFS。"""
    amp = sine_amp(-20.0)
    d = f":d={dur}" if dur is not None else ""
    return ["-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*440*t)':s=48000:c=stereo{d}",
            "-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*1000*t)':s=48000:c=mono{d}"]


# spec §4.6.17（t6 第二輪，缺陷 B）：VFR、time_base=1/600、r_frame_rate 600、平均約 12 fps、最後一幀 PTS 15.190
VFR_TAIL_SELECT = "select='not(mod(n\\,97))+not(mod(n\\,101))+eq(n\\,9114)'"


def make_vfr_tail_segment(path, *, w=320, h=240, dur=15.1988, **_):
    """單段：testsrc2 600 fps 經 select 取稀疏影格（最後一幀 PTS 15.190，距段落結束 < 0.01 秒，不需補尾），
    libx264 -bf 0、-fps_mode passthrough、-video_track_timescale 600；兩條 AAC 音軌；-t 15.1988（段落長 15.199）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ff("-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=600", *_two_aac_inputs(),
       "-map", "0:v", "-map", "1:a", "-map", "2:a", "-vf", VFR_TAIL_SELECT,
       "-fps_mode", "passthrough", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0",
       "-video_track_timescale", "600",
       "-c:a", "aac", "-ar", "48000", "-ac:a:0", "2", "-ac:a:1", "1", "-t", dur, "-f", "mov", path)
    return path


def make_sparse_vfr_segment(path, *, w=320, h=240, dur=20.0, frames=8, rate="4/3", **_):
    """spec §4.6.18（t6 第二輪，缺陷 F）的 seg-0002：testsrc2 rate=4/3 只取 frames 幀（libx264 -bf 0、
    -video_track_timescale 600），另以 dur 秒的兩條 AAC 音軌 -c copy mux 成同一檔（影片比音訊早很多結束）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    vtmp = path.with_name(path.stem + ".v.mov")
    atmp = path.with_name(path.stem + ".a.mov")
    try:
        ff("-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate={rate}", "-frames:v", frames,
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0", "-video_track_timescale", "600", "-f", "mov", vtmp)
        ff(*_two_aac_inputs(dur), "-map", "0:a", "-map", "1:a",
           "-c:a", "aac", "-ar", "48000", "-ac:a:0", "2", "-ac:a:1", "1", "-f", "mov", atmp)
        ff("-i", vtmp, "-i", atmp, "-map", "0:v", "-map", "1:a", "-c", "copy",
           "-video_track_timescale", "600", "-f", "mov", path)
    finally:
        for t in (vtmp, atmp):
            if t.exists():
                t.unlink()
    return path


# 缺陷 N（t6 第三輪實機）：稀疏 VFR 最後一段，最後一幀距段落結束 60–80 ms。影格 PTS（1/600 tick）：
# 0 起、間隔取 26–100 tick 的固定亂數（相鄰間隔的最大公因數為 1，ffprobe r_frame_rate 才會是 600），
# 結尾三幀固定為實機特性 9.950、9.993、10.108 秒；總數 97 幀同實機（seed 12）——最後一幀序號 96 是 12 的倍數，
# h264_videotoolbox 預設 gop 12 會把它編成關鍵幀，補尾的複製幀接著就被編碼器吃掉（實機重現條件，幀數不同就不會重現）。
SPARSE_TAIL_LAST_TICKS = (5970, 5996, 6065)


def sparse_tail_ticks(seed=12):
    rng = random.Random(seed)
    t, ticks = 0, [0]
    while True:
        t += rng.randint(26, 100)
        if t > SPARSE_TAIL_LAST_TICKS[0] - 40:
            break
        ticks.append(t)
    return ticks + list(SPARSE_TAIL_LAST_TICKS)


def make_sparse_tail_segment(path, *, w=320, h=240, dur=10.1763, last_dur=41, **_):
    """缺陷 N 的段落：testsrc2 600 fps 經 select 取稀疏影格（平均約 9.6 fps、97 幀、time_base 1/600、r_frame_rate 600、
    最後一幀 PTS 10.108），libx264 -bf 0、-fps_mode passthrough；最後一幀的長度以 setts 設成 last_dur tick
    （41 → 影片軌結束於 6106 tick＝10.176667 秒，同實機）；兩條 AAC 音軌 -t dur（比影片軌早一點結束，
    段落長由影片軌決定，同實機）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sel = "select='" + "+".join(f"eq(n\\,{k})" for k in sparse_tail_ticks()) + "'"
    ff("-f", "lavfi", "-i", f"testsrc2=size={w}x{h}:rate=600:d={dur + 0.05:.4f}", *_two_aac_inputs(),
       "-map", "0:v", "-map", "1:a", "-map", "2:a", "-vf", sel,
       "-fps_mode", "passthrough", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-bf", "0",
       "-video_track_timescale", "600",
       "-bsf:v", f"setts=duration='if(eq(PTS\\,{SPARSE_TAIL_LAST_TICKS[-1]})\\,{last_dur}\\,DURATION)'",
       "-c:a", "aac", "-ar", "48000", "-ac:a:0", "2", "-ac:a:1", "1", "-t", dur, "-f", "mov", path)
    return path


# spec §4.6.20（t6 第三輪，缺陷 J）的段落長（秒）：都不是 1024 樣本（48 kHz）的整數倍
DRIFT_LENGTHS = (10.017, 3.3, 7.0, 5.013)


def make_drift_sync_segment(path, *, w=320, h=180, dur=10.017, fps=30, phase=0.0, lead_silence=0.0, seed=1, **_):
    """spec §4.6.20 的段落：影片每 2 秒閃白 0.1 秒＋系統聲音（雙聲道 AAC）同時 1 kHz 嗶聲＋麥克風（單聲道 AAC）
    低音量雜訊。phase＝該段起點在整場的秒數（閃白與嗶聲的相位依段落起點接續）；lead_silence＝系統聲音開頭靜音秒數
    （第一段 0.05：音訊比影片晚開始）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    on = f"lt(mod(t+{phase},2),0.1)"
    mute = f"*gte(t,{lead_silence})" if lead_silence else ""
    ff("-f", "lavfi", "-i", f"color=c=black:s={w}x{h}:r={fps}:d={dur},"
                            f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='{on}'",
       "-f", "lavfi", "-i", f"aevalsrc='0.5*sin(2*PI*1000*(t+{phase}))*{on}{mute}':s=48000:c=stereo:d={dur}",
       "-f", "lavfi", "-i", f"anoisesrc=color=white:amplitude=0.003:seed={seed}:sample_rate=48000:d={dur}",
       "-map", "0:v", "-map", "1:a", "-map", "2:a",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac:a:0", "2", "-ac:a:1", "1", "-t", dur, "-f", "mov", path)
    return path


def drift_segments(lengths=DRIFT_LENGTHS, lead_silence=0.05):
    """make_record_session(..., gap=0.0) 用的段落清單：startedAt 照累加段長，相位依段落起點接續。"""
    out, t = [], 0.0
    for i, L in enumerate(lengths):
        out.append(dict(recipe="drift_sync", dur=L, w=320, h=180, phase=round(t, 3),
                        lead_silence=lead_silence if i == 0 else 0.0, seed=i + 1))
        t += L
    return out


def make_frame_timing_video(path, *, dur=6.0, gaps=None, w=160, h=120):
    """spec §4.3.3 (ii)(iii)（t6 第三輪，發現 M）的影片：60 fps 格點，gaps＝{影格序號 N: 與前一幀的間隔秒}
    把第 N 幀提前到「前一幀＋間隔」（時間基準 1/90000，-bf 0、-fps_mode passthrough）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    expr = "N/60" + "".join(f"+eq(N\\,{n})*({g}-1/60)" for n, g in sorted((gaps or {}).items()))
    ff("-f", "lavfi", "-i", f"testsrc2=s={w}x{h}:r=60:d={dur}", "-vf", f"settb=1/90000,setpts='({expr})/TB'",
       "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-bf", "0", "-fps_mode", "passthrough",
       "-enc_time_base", "1/90000", "-video_track_timescale", "90000", "-f", "mov", path)
    return path


def segment_length(path):
    """spec §4.6.17 的「段落長」：該段各軌 stream 層 start_time＋duration 的最大值。"""
    info = probe(path) or {"streams": []}
    ends = []
    for s in info["streams"]:
        try:
            ends.append(float(s.get("start_time") or 0) + float(s["duration"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(ends) if ends else None


def videotoolbox_h264_available():
    """h264_videotoolbox 能不能真的編（清單有但硬體不可用時也算沒有）。回 (可用與否, 原因)。"""
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                        "testsrc2=size=320x240:rate=30:d=0.2", "-c:v", "h264_videotoolbox", "-f", "null", "-"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"這台機器的 ffmpeg 不能用 h264_videotoolbox 編碼：{r.stderr.strip()[-200:]}"
    return True, ""


RECIPES = {"two_tracks": make_two_track_segment, "irregular": make_irregular_segment,
           "late_video_sync": make_late_video_sync_segment, "fragment": make_fragment_segment,
           "vfr_tail": make_vfr_tail_segment, "sparse_vfr": make_sparse_vfr_segment,
           "drift_sync": make_drift_sync_segment,
           "sparse_tail": make_sparse_tail_segment}


def decoded_audio_end(path, index=0):
    """第 index 條音軌「可解碼」的長度：解碼出的最後一個 frame 的 pts_time＋duration_time − 第一個 frame 的 pts_time。"""
    r = subprocess.run([FFPROBE, "-v", "quiet", "-select_streams", f"a:{index}", "-show_entries",
                        "frame=pts_time,duration_time", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    rows = []
    for line in r.stdout.split():
        parts = line.split(",")
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue
    if not rows:
        return None
    return rows[-1][0] + rows[-1][1] - rows[0][0]


def packet_dts(path, kind_index, field="dts_time"):
    """某條軌（例 "v:0"、"a:0"）全部封包的 dts（秒；field="pts_time" 取 pts）。"""
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", kind_index, "-show_entries", f"packet={field}",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    out = []
    for x in r.stdout.split():
        x = x.split(",")[0].strip()
        if x and x != "N/A":
            out.append(float(x))
    return out


def packet_pts(path, kind_index):
    return packet_dts(path, kind_index, field="pts_time")


def frame_count(path):
    return len(frame_times(path))


def pcm_s16(path, *, rate=16000, stream="0:a:0", af=None):
    """解成 mono s16 樣本（list[int]）；af 為額外的音訊濾鏡（例如帶通）。"""
    from array import array
    import sys

    args = [FFMPEG, "-v", "error", "-i", str(path), "-map", stream]
    if af:
        args += ["-af", af]
    args += ["-ac", "1", "-ar", str(rate), "-f", "s16le", "-"]
    r = subprocess.run(args, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"解不出音訊：{r.stderr[-400:]!r}")
    buf = array("h")
    buf.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
    if sys.byteorder != "little":
        buf.byteswap()
    return buf


def rms_dbfs(samples):
    import math
    if not samples:
        return -math.inf
    ms = sum(x * x for x in samples) / len(samples)
    return -math.inf if ms == 0 else 10 * math.log10(ms / (32768.0 ** 2))


def peak_dbfs(samples):
    import math
    pk = max((abs(x) for x in samples), default=0)
    return -math.inf if pk == 0 else 20 * math.log10(pk / 32768.0)


def truncate(path, frac=0.4):
    """截掉尾巴（含 moov）模擬 kill -9 時沒收尾的段落。"""
    data = Path(path).read_bytes()
    Path(path).write_bytes(data[:int(len(data) * frac)])


def make_record_session(root, segments, *, name=SESSION_NAME, gap=0.02):
    """建一個「錄完、還沒 finalize」的場次：錄音/tracks/seg-*.mov、manifest.json、record.meta.json、meeting.json。

    segments：dict 清單，鍵同 make_segment 的參數，另可加 truncate=True。回傳場次目錄。
    """
    sess = Path(root) / DAY / name
    tracks = sess / "錄音" / "tracks"
    tracks.mkdir(parents=True)
    (sess / "錄音" / "meeting.json").write_text(json.dumps(MEETING_JSON, ensure_ascii=False, indent=2),
                                               encoding="utf-8")
    recs, t = [], 0.0
    for i, spec in enumerate(segments, start=1):
        spec = dict(spec)
        trunc = spec.pop("truncate", False)
        f = tracks / f"seg-{i:04d}.mov"
        make_segment(f, **spec)
        if trunc:
            truncate(f)
        dur = spec.get("dur", 2.0)
        recs.append({"file": f.name, "requestedAt": round(max(t - 0.01, 0), 3), "startedAt": round(t, 3),
                     "finishedAt": round(t + dur, 3), "width": spec.get("w", 320), "height": spec.get("h", 240),
                     "audioDuration": None})
        t += dur + gap
    n = int(t / 0.5) + 1
    manifest = {"schemaVersion": 1, "segmentSeconds": 60, "segments": recs,
                "frameStatus": {"complete": 10, "idle": 2, "blank": 0, "suspended": 0, "started": 1, "stopped": 0},
                "blackIntervals": [], "levels": {"windowSeconds": 0.5, "system": [-20.0] * n, "mic": [-30.0] * n}}
    (tracks / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    meta = {"schemaVersion": 1,
            "window": {"windowID": 41001, "app": "Microsoft Teams", "bundleID": "com.microsoft.teams2",
                       "title": "範例會議"},
            "config": dict(CONFIG_SNAPSHOT),
            "devices": {"input": {"uid": "BuiltInMic", "name": "內建麥克風", "transport": "builtIn"},
                        "output": {"uid": "BuiltInSpk", "name": "內建揚聲器", "transport": "builtIn"}},
            "preflight": [], "deviceEvents": [], "audioFormatEvents": []}
    (tracks / "record.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return sess


def frame_rgb(path, t, w, h):
    """取 t 秒那一幀的 RGB24 位元組。"""
    r = subprocess.run([FFMPEG, "-v", "error", "-ss", str(t), "-i", str(path), "-frames:v", "1",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if r.returncode != 0 or len(r.stdout) < w * h * 3:
        raise RuntimeError(f"抽不到 {t}s 的影格")
    return r.stdout


def pixel(buf, w, x, y):
    i = (y * w + x) * 3
    return tuple(buf[i:i + 3])


def frame_times(path):
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    vals = [x.split(",")[0].strip() for x in r.stdout.split()]
    return [float(x) for x in vals if x and x != "N/A"]


TS = "2026-10-11 10.00.00"


def _silence_factor(silences):
    return "".join(f"*(1-between(t,{a},{b}))" for a, b in silences)


def build_e2e_session(base, *, dur=6.0, fps=60, size=(320, 240), nseg=3, seg_sizes=None, black=None,
                      silences=(), sync_offset=None, input_transport="builtIn", output_transport="builtIn",
                      device_events=(), format_events=(), name=SESSION_NAME, two_tracks=False, sync_noise=False):
    """合成一個「錄完並 finalize 過」的場次，供 e2e_check.py 的判準自我測試。

    影片/ 的 .mov 是 master（H.264＋AAC），段落由 master 切出；錄音/ 的 wav 由 master 抽出；
    manifest.levels 依 silences（[(起, 迄)]）推出：0.5 秒窗的中點落在靜音區間內為 null，否則 -20。
    two_tracks=True 時段落照 D20 的格式（spec §4.4.1）：影片＋系統聲音（master 的音訊）＋麥克風（1000 Hz 單聲道）。
    sync_noise=True（需搭配 sync_offset）時在同步測試源的音訊疊上 500–1500 Hz、每秒 3 次起伏的雜訊（語音替身，
    spec §4.9.3 t6 第三輪：在 1 kHz 附近有能量，全頻 RMS 的舊量法會把它當嗶聲）。
    """
    from tests.record.e2e_check import sync_source_graph

    sess = Path(base) / DAY / name
    rec, tracks, vid = sess / "錄音", sess / "錄音" / "tracks", sess / "影片"
    for d in (tracks, vid):
        d.mkdir(parents=True, exist_ok=True)
    w, h = size
    master = vid / f"{name} {TS}.mov"
    if sync_offset is not None:
        vg, ag = sync_source_graph(offset=sync_offset, duration=dur)
        vg = vg.replace("s=640x360", f"s={w}x{h}").replace("r=60", f"r={fps}")
        if sync_noise:
            noise = (f"anoisesrc=color=white:amplitude=1.0:seed=7:sample_rate=48000:d={dur},"
                     "bandpass=f=1000:width_type=h:w=1000,volume='1.5*(0.5+0.5*sin(2*PI*3*t))':eval=frame,"
                     "aformat=channel_layouts=stereo")
            ag = f"{ag}[s];{noise}[n];[s][n]amix=inputs=2:normalize=0"
    else:
        vg = f"testsrc2=s={w}x{h}:r={fps}:d={dur}"
        if black:
            vg += f",drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{black[0]},{black[1]})'"
        ag = f"aevalsrc='0.3*sin(2*PI*440*t){_silence_factor(silences)}':s=48000:c=stereo:d={dur}"
    ff("-f", "lavfi", "-i", vg, "-f", "lavfi", "-i", ag, "-t", dur, "-c:v", "libx264", "-preset", "ultrafast",
       "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-f", "mov", master)
    sizes = list(seg_sizes or [size] * nseg)
    seglen = dur / len(sizes)
    recs = []
    for i, (sw, sh) in enumerate(sizes):
        f = tracks / f"seg-{i + 1:04d}.mov"
        if two_tracks:
            ff("-ss", i * seglen, "-t", seglen, "-i", master,
               "-f", "lavfi", "-t", seglen, "-i", "sine=f=1000:sample_rate=48000",
               "-map", "0:v", "-map", "0:a", "-map", "1:a", "-vf", f"scale={sw}:{sh}", "-c:v", "libx264",
               "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac:a:1", "1", "-f", "mov", f)
            ad = max(float(x["duration"]) for x in streams(f, "audio"))
        else:
            ff("-ss", i * seglen, "-t", seglen, "-i", master, "-vf", f"scale={sw}:{sh}", "-c:v", "libx264",
               "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-f", "mov", f)
            ad = stream_duration(f, "audio")
        st = round(i * seglen + 0.01 * i, 3)
        recs.append({"file": f.name, "requestedAt": max(st - 0.005, 0), "startedAt": st,
                     "finishedAt": round(st + seglen, 3), "width": sw, "height": sh,
                     "audioDuration": ad})
    gaps = [recs[i + 1]["startedAt"] - recs[i]["startedAt"] - recs[i]["audioDuration"] for i in range(len(recs) - 1)]
    nwin = int(round(dur / 0.5))
    lv = [None if any(a <= (k + 0.5) * 0.5 <= b for a, b in silences) else -20.0 for k in range(nwin)]
    manifest = {"schemaVersion": 1, "segmentSeconds": 60, "segments": recs,
                "frameStatus": {"complete": 100, "idle": 0, "blank": 0, "suspended": 0, "started": 1, "stopped": 0},
                "blackIntervals": [{"start": float(black[0]), "end": float(black[1])}] if black else [],
                "levels": {"windowSeconds": 0.5, "system": lv, "mic": list(lv)},
                "gapStats": {"boundaries": gaps, "max": max(gaps) if gaps else 0.0, "total": sum(gaps),
                             "wallClock": recs[-1]["finishedAt"]},
                "outputCanvas": {"width": max(x for x, _ in sizes), "height": max(y for _, y in sizes)},
                "outputVideoBitrate": 1000000}
    (tracks / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def dev(t):
        return {"uid": f"dev-{t}", "name": f"範例裝置（{t}）", "transport": t}

    def fmt(rate):
        return {"sampleRate": rate, "channels": 2 if rate == 48000 else 1, "interleaved": False,
                "sampleType": "float32"}

    meta = {"schemaVersion": 1,
            "window": {"windowID": 41001, "app": "Microsoft Teams", "bundleID": "com.microsoft.teams2",
                       "title": "範例會議"},
            "config": dict(CONFIG_SNAPSHOT),
            "devices": {"input": dev(input_transport), "output": dev(output_transport)},
            "preflight": [],
            "deviceEvents": [{"t": t, "kind": k, "from": dev(a), "to": dev(b)} for t, k, a, b in device_events],
            "audioFormatEvents": [{"t": t, "source": src, "from": fmt(a), "to": fmt(b)}
                                  for t, src, a, b in format_events]}
    (tracks / "record.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (rec / "meeting.json").write_text(json.dumps(MEETING_JSON, ensure_ascii=False, indent=2), encoding="utf-8")
    ff("-i", master, "-map", "0:a:0", "-ar", 16000, "-ac", 1, "-c:a", "pcm_s16le", "-f", "wav",
       rec / f"{name} {TS}.wav")
    return sess

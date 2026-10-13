#!/usr/bin/env python3
"""e2e_check.py —— 端到端錄製結果的機械核對（spec §4.3、§4.4、§4.6、§4.8.1、§4.9、§4.10、§4.15.16、§4.15.18）。

D20（自管 AVAssetWriter 分段寫檔）的判準放在 --segment-writer 之後，不加進預設判準（spec §6 第 53 條）：
segment_tracks（§4.4.1）、segment_finished／segment_cadence（§4.4.3 (b)(c)）、segment_video_start（§4.4.4）、
stop_tail（§4.4.8）；與 --hfp 同時給時另加 format_rotation（§4.9.3）。

R2（spec §3.11、§4.17.5–§4.17.8、§4.18.5–§4.18.7、§4.18.11、§4.18.12、§4.19.4）：
--pause-mute 加九項判準：pause_events、pause_cut、mic_mute_zero、mute_system_kept、no_false_silence、markers、
mute_timing、no_false_black、event_output_t；沒有事件時各自判「情境未觸發」（不得判 PASS）。
有 pauseEvents／micMuteEvents 時，既有判準依 §3.11 排除暫停與靜音：gap 扣暫停長度、segment_cadence 把 resume 邊界
列為提前換段、stop_tail 加 pausedTotal、讀 levels 的判準跳過暫停（兩路）與靜音（mic）區間、讀混音軌時把錄製時鐘換成
成品時間（record_to_output，語意同 Core outputTime）。沒有這兩個陣列的場次，結果與 R2 之前完全相同。

t6 第三輪（spec §6 第 64、66、68 條）：sync 改用 1 kHz 帶通＋每個閃白的局部起點（sync_offsets，可被測試載入）；
device_switch、hfp 的「其餘時間」改為不得連續 ≥ 3 秒 ≤ -60 dBFS；fps_min_interval 改為三條件（§4.3.3）。

讀場次的 錄音/tracks/record.meta.json、manifest.json、seg-*.mov、錄音/*.wav、影片/*.mov 與 ffprobe／ffmpeg 結果，
逐條印 PASS／FAIL（--json 印機器可讀結果）；全 PASS 回 0，有 FAIL 回 1，參數錯誤回 2。
判準本身由 tests/record/test_e2e_check.py 以合成場次（已知 PASS 與已知 FAIL）自我測試。

用法：
  e2e_check.py <場次> [--expect-min S --expect-max S] [--device-switch] [--all-bluetooth] [--hfp] [--sync]
               [--fps-interval mm:ss-mm:ss] [--space-interval mm:ss-mm:ss] [--status <record.status.json>]
               [--segment-writer] [--pause-mute] [--json]
  e2e_check.py --print-sync-source      印出同步測試源（低音量底音＋每 2 秒一次閃白與嗶聲）的 ffplay 指令
"""
import argparse
import ast
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
from array import array
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE = shutil.which("ffprobe") or "ffprobe"
REPO = Path(__file__).resolve().parents[2]

SILENT_DB = -60.0          # spec §4.5.1、§4.9：峰值 ≤ -60 dBFS 或 null 視為沒有聲音
MAX_INTERRUPT = 3.0        # spec §4.9（D10）：每次切換中斷 < 3 秒
AROUND = 10.0              # spec §4.9：事件前後 10 秒內量中斷
MAX_GAP = 0.5              # spec §4.4.3
SYNC_TOL = 0.1             # spec §4.9.3：閃白與嗶聲時間差 < 100 ms
AV_TOL = 0.1               # spec §4.6.3
FPS_PEAK = 55              # spec §4.3.3
MIN_FRAME_INTERVAL = 1 / 60 - 0.001   # spec §4.3.3 (ii)：「過近」間隔的門檻
FPS_WINDOW_MAX = 61        # spec §4.3.3 (i)（t6 第三輪，發現 M）：1 秒滑動窗影格數最大值 ≤ 61
MIN_FRAME_GAP = 0.001      # spec §4.3.3 (iii)：相鄰影格 PTS 間隔最小值 ≥ 1 ms
SPACE_RATIO = 0.5          # spec §4.10.2
BLUETOOTH = {"bluetooth", "bluetoothLE"}
AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".mov", ".mp4", ".m4v")
CONFIG_SNAPSHOT = {
    "filter": "desktopIndependentWindow", "onScreenWindowsOnly": False, "scalesToFit": True,
    "minimumFrameInterval": "1/60", "capturesAudio": True, "sampleRate": 48000, "channelCount": 2,
    "captureMicrophone": True, "microphoneCaptureDeviceID": None, "excludesCurrentProcessAudio": True,
    "fileType": "mov", "videoCodec": "h264", "segmentSeconds": 60,
}
SYNC_PERIOD = 2.0
SYNC_FLASH = 0.1
# spec §4.9.3（t6 第三輪，缺陷 K (a)）：嗶聲量法＝1 kHz 帶通兩次、48 kHz 單聲道、1 ms 窗 RMS 包絡，
# 每個閃白 ±0.3 秒內取包絡最大值，第一個 ≥ 最大值 50% 的窗為嗶聲起點
SYNC_BAND = "bandpass=f=1000:width_type=h:w=100"
SYNC_RATE = 48000
SYNC_ENV_WIN = 0.001
SYNC_SEARCH = 0.3
SYNC_ONSET_RATIO = 0.5
# spec §4.9.1、§4.9.3（t6 第三輪，缺陷 K (b)）：切換／格式變更以外的時間不得連續 ≥ 3 秒 ≤ -60 dBFS 或 null
QUIET_RUN_MAX = MAX_INTERRUPT
# D20（--segment-writer）
SEGMENT_SECONDS = 60.0     # spec §4.4.3 (c)：定期換段的 startedAt 間隔
CADENCE_TOL = 0.001        # spec §4.4.3 (c)
MAX_FINISH_LAG = 5.0       # spec §4.4.3 (b)：finishedAt_i − startedAt_{i+1} < 5 秒
VIDEO_START_MAX = 0.05     # spec §4.4.4：seg-0002 起影片軌 start_time ≤ 0.05 秒
STOP_TAIL_TOL = 1.0        # spec §4.4.8：wallClock 與 startedAt_1 + Σ audioDuration 差 < 1 秒
ROTATION_TOL = 0.5         # spec §4.9.3：格式變更與段落邊界 startedAt 相差 < 0.5 秒
ROTATION_DEBOUNCE = 1.0    # spec §4.9.3：同一路 1 秒內的連續變更只要求第一筆
# R2（--pause-mute）
PAUSE_TOL = 0.5            # spec §3.11、§4.18.6：resume.t 與 startedAt、pause.t 與段落結束相差 < 0.5 秒
MUTE_EDGE = 0.2            # spec §4.17.5：靜音區間兩端各讓 0.2 秒
MUTE_TIMING_TOL = 0.5      # spec §4.17.8：全 0 區段兩端與事件時刻相差 ≤ 0.5 秒
CUT_TOL = 1.0              # spec §4.18.6：成品長度與（停止點 − startedAt_1 − pausedTotal）相差 < 1 秒
OUTPUT_T_TOL = 0.01        # spec §4.18.12、§4.19.4：outputT／markers.t 與換算結果相差 ≤ 0.01 秒
EVENT_GRACE = 1.0          # spec §4.17.6、§4.18.11：區間結束後再寬限 1 秒
MIC_TRACK = 1              # 段落的第 3 條軌＝第 2 條音軌（0:a:1，麥克風）
SYSTEM_TRACK = 0           # 段落的第 2 條軌＝第 1 條音軌（0:a:0，系統聲音）
PCM_RATE = 48000
NOT_TRIGGERED = "情境未觸發"


class CheckError(Exception):
    pass


# ---------- 同步測試源 ----------

def sync_source_graph(offset=0.0, duration=None):
    """lavfi 濾鏡圖：[out0] 黑底每 2 秒閃白 0.1 秒；[out1] 低音量 220 Hz 底音＋同時的 1 kHz 嗶聲。

    offset：嗶聲相對閃白延後的秒數（自我測試用；實際使用為 0）。
    """
    d = f":d={duration}" if duration else ""
    video = (f"color=c=black:s=640x360:r=60{d},"
             f"drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='lt(mod(t,{SYNC_PERIOD}),{SYNC_FLASH})'")
    audio = (f"aevalsrc='0.02*sin(2*PI*220*t)+0.5*sin(2*PI*1000*t)*lt(mod(t+{SYNC_PERIOD}-{offset},{SYNC_PERIOD}),"
             f"{SYNC_FLASH})':s=48000:c=stereo{d}")
    return video, audio


def print_sync_source():
    v, a = sync_source_graph()
    print(f'ffplay -f lavfi "{v}[out0];{a}[out1]"')
    print("# 全螢幕播放這個視窗當系統聲音來源；錄完用 e2e_check.py <場次> --sync 核對。")


# ---------- 讀檔 ----------

def run(cmd, binary=False):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=not binary)
    return r


def probe(path):
    r = run([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-of", "json", path])
    if r.returncode != 0:
        return None
    return json.loads(r.stdout)


def streams(path, kind):
    info = probe(path)
    return [s for s in (info or {}).get("streams", []) if s.get("codec_type") == kind]


def stream_duration(path, kind):
    s = streams(path, kind)
    if not s or s[0].get("duration") in (None, "N/A"):
        return None
    return float(s[0]["duration"])


def segment_audio_duration(path):
    """spec §3.2 的 audioDuration 算法（與 bin/_record_finalize.py 的 analyze 同一把尺，spec §4.6.19、缺陷 F2）：
    各音軌長度＝最後一個可解碼封包的 pts_time＋duration_time − min(stream 層 start_time, 第一個可解碼封包 pts_time)，
    「可解碼」＝略過 flags 含 D（discard）或 C（corrupt）的封包；取各音軌最大值。不採 stream／format 層的 duration
    （中斷的 fragment 檔會高報）。讀不到任何可解碼音訊封包時回 None。"""
    info = probe(path)
    if not info:
        return None
    r = run([FFPROBE, "-v", "quiet", "-show_entries", "packet=stream_index,pts_time,duration_time,flags",
             "-of", "json", path])
    try:
        pkts = json.loads(r.stdout or "{}").get("packets") or []
    except ValueError:
        return None

    def num(v):
        try:
            x = float(v)
        except (TypeError, ValueError):
            return None
        return x if math.isfinite(x) else None

    rows = {}
    for k in pkts:
        flags = k.get("flags") or ""
        if "C" in flags or "D" in flags:
            continue
        pts = num(k.get("pts_time"))
        if pts is None:
            continue
        rows.setdefault(k.get("stream_index"), []).append((pts, num(k.get("duration_time")) or 0.0))
    lens = []
    for st in info.get("streams", []):
        if st.get("codec_type") != "audio":
            continue
        rs = rows.get(st.get("index")) or []
        if not rs:
            continue
        first = min(p for p, _ in rs)
        start = num(st.get("start_time"))
        if start is None:
            start = first
        end = max(p + d for p, d in rs)
        lens.append(max(end - min(start, first), 0.0))
    return max(lens) if lens else None


def longest_audio_duration(path):
    """各音軌 stream duration 的最大值（design.md §7.2 空隙量法：段落有兩條音軌時取較長者）；
    只有一條音軌時等於 stream_duration(path, "audio")。"""
    ds = [float(x["duration"]) for x in streams(path, "audio") if x.get("duration") not in (None, "N/A")]
    return max(ds) if ds else None


def frame_times(path):
    r = run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time", "-of",
             "csv=p=0", path])
    vals = [x.split(",")[0].strip() for x in r.stdout.split()]
    return [float(x) for x in vals if x and x != "N/A"]


def pcm_mono(path, rate=16000):
    """影片檔第一條音軌解成 mono s16，回傳 (樣本 array, 起始秒)。"""
    a = streams(path, "audio")
    start = float(a[0].get("start_time") or 0) if a else 0.0
    r = run([FFMPEG, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-"],
            binary=True)
    if r.returncode != 0:
        raise CheckError("解不出音訊")
    buf = array("h")
    buf.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
    if sys.byteorder != "little":
        buf.byteswap()
    return buf, start


def rms_db_windows(samples, rate, win):
    n = int(rate * win)
    out = []
    for i in range(0, len(samples) - n + 1, n):
        chunk = samples[i:i + n]
        ms = sum(x * x for x in chunk) / n
        out.append(-math.inf if ms == 0 else 10 * math.log10(ms / (32768.0 ** 2)))
    return out


def parse_interval(s):
    m = re.fullmatch(r"(\d+):(\d{2})-(\d+):(\d{2})", s or "")
    if not m:
        raise argparse.ArgumentTypeError(f"區間格式應為 mm:ss-mm:ss：{s}")
    a = int(m.group(1)) * 60 + int(m.group(2))
    b = int(m.group(3)) * 60 + int(m.group(4))
    if b <= a:
        raise argparse.ArgumentTypeError(f"區間結束要晚於開始：{s}")
    return (float(a), float(b))


class Session:
    def __init__(self, path):
        self.path = Path(path)
        self.rec = self.path / "錄音"
        self.tracks = self.rec / "tracks"
        self._cache = {}

    def json(self, name):
        p = self.tracks / name
        if not p.is_file():
            raise CheckError(f"找不到 錄音/tracks/{name}")
        return json.loads(p.read_text(encoding="utf-8"))

    @property
    def meta(self):
        return self.json("record.meta.json")

    @property
    def manifest(self):
        return self.json("manifest.json")

    @property
    def video(self):
        vids = sorted((self.path / "影片").glob("*.mov"))
        if len(vids) != 1:
            raise CheckError(f"影片/ 應恰有一個 .mov，實際 {len(vids)} 個")
        return vids[0]

    @property
    def wav(self):
        wavs = sorted(self.rec.glob("*.wav"))
        if len(wavs) != 1:
            raise CheckError(f"錄音/ 應恰有一個 .wav，實際 {len(wavs)} 個")
        return wavs[0]

    def segments(self):
        return sorted(self.tracks.glob("seg-*.mov"))

    def mixed_db(self):
        if "mixed" not in self._cache:
            samples, start = pcm_mono(self.video)
            self._cache["mixed"] = (rms_db_windows(samples, 16000, 0.1), start)
        return self._cache["mixed"]


# ---------- R2：暫停、靜音、標記的時間軸（spec §3.11、§3.12） ----------

def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def pause_pairs(events):
    """pauseEvents → [(pause.t, resume.t 或 None)]，依出現順序；resume 只與緊接在前、還沒配對的 pause 配對。"""
    out, open_t = [], None
    for e in events or []:
        t = _num(e.get("t"))
        if t is None:
            continue
        if e.get("kind") == "pause":
            if open_t is None:
                open_t = t
        elif e.get("kind") == "resume" and open_t is not None:
            out.append((open_t, t))
            open_t = None
    if open_t is not None:
        out.append((open_t, None))
    return out


def paused_total(events):
    """spec §3.14 pausedTotal：Σ（resume.t − 緊接在前的 pause.t）；沒配對的 pause 不計；小數 3 位。"""
    return round(sum(r - p for p, r in pause_pairs(events) if r is not None), 3)


def record_to_output(t, first_start, pauses):
    """錄製時鐘 → 成品時間（語意同 Core outputTime，spec §3.14）：t 落在暫停區間（pause.t ≤ t < 配對的 resume.t，
    或沒配對的 pause.t ≤ t）時以該 pause.t 代替；再減 first_start 與「resume.t ≤ 代替後時刻」的已配對暫停長度；
    < 0 夾成 0；小數 3 位。pauses 為 pauseEvents（只用到 t 之前的暫停，所以傳整場或事件當下的陣列結果相同）。"""
    pairs = pause_pairs(pauses)
    x = float(t)
    for p, r in pairs:
        if p <= x and (r is None or x < r):
            x = p
            break
    x -= float(first_start)
    x -= sum(r - p for p, r in pairs if r is not None and r <= x + float(first_start))
    return round(max(x, 0.0), 3)


def mute_pairs(events):
    """micMuteEvents → [(muted=true 的 t, 下一筆 muted=false 的 t 或 None)]。"""
    out, open_t = [], None
    for e in events or []:
        t = _num(e.get("t"))
        if t is None:
            continue
        if e.get("muted") is True:
            if open_t is None:
                open_t = t
        elif e.get("muted") is False and open_t is not None:
            out.append((open_t, t))
            open_t = None
    if open_t is not None:
        out.append((open_t, None))
    return out


def r2_events(s):
    meta = s.meta
    return list(meta.get("pauseEvents") or []), list(meta.get("micMuteEvents") or [])


def seg_audio_durations(s):
    """各段 audioDuration：manifest 有值就用（finalize 寫的，§3.2 算法），否則現場量（同一把尺）。"""
    out = []
    for r in s.manifest.get("segments", []):
        ad = _num(r.get("audioDuration"))
        if ad is None:
            p = s.tracks / r["file"]
            ad = segment_audio_duration(p) if p.is_file() else None
        out.append(ad)
    return out


def segment_ends(s):
    recs = s.manifest.get("segments", [])
    out = []
    for r, ad in zip(recs, seg_audio_durations(s)):
        st = _num(r.get("startedAt"))
        out.append(None if st is None or ad is None else st + ad)
    return out


def first_start(s):
    recs = s.manifest.get("segments", [])
    st = _num(recs[0].get("startedAt")) if recs else None
    if st is None:
        raise CheckError("manifest 沒有第一段的 startedAt")
    return st


def session_end(s):
    ends = [e for e in segment_ends(s) if e is not None]
    if not ends:
        raise CheckError("算不出最後一段的結束（startedAt＋audioDuration）")
    return max(ends)


def closed(pairs, end):
    """把沒配對的區間延伸到 end。"""
    return [(a, b if b is not None else end) for a, b in pairs]


def level_skip(s, track):
    """spec §3.11：讀 levels 時要排除的窗——暫停區間（兩路）與靜音區間（mic 路），沒配對的延伸到最後。
    沒有任何事件時回 None（判準與 R2 之前完全相同）。"""
    pauses, mutes = r2_events(s)
    if not pauses and not (track == "mic" and mutes):
        return None
    iv = closed(pause_pairs(pauses), math.inf)
    if track == "mic":
        iv += closed(mute_pairs(mutes), math.inf)
    ws = (s.manifest.get("levels") or {}).get("windowSeconds") or 0.5
    return lambda a: any(a + ws > x and a < y for x, y in iv)


def track_pcm(s, index):
    """各段第 index 條音軌解成 48 kHz 單聲道 s16，回傳 [(錄製時鐘起點秒, bytes)]（依 startedAt 排序）。
    起點＝startedAt＋該音軌的 start_time（段落檔的時間 0＝startedAt）。"""
    key = ("pcm", index)
    if key in s._cache:
        return s._cache[key]
    out = []
    for r in s.manifest.get("segments", []):
        p = s.tracks / r["file"]
        st = _num(r.get("startedAt"))
        if st is None or not p.is_file():
            continue
        a = streams(p, "audio")
        if len(a) <= index:
            raise CheckError(f"{p.name} 沒有第 {index + 2} 條軌（第 {index + 1} 條音軌）")
        start = float(a[index].get("start_time") or 0)
        res = run([FFMPEG, "-v", "error", "-i", p, "-map", f"0:a:{index}", "-ac", "1", "-ar", str(PCM_RATE),
                   "-f", "s16le", "-"], binary=True)
        if res.returncode != 0:
            raise CheckError(f"{p.name} 解不出第 {index + 1} 條音軌")
        data = res.stdout[:len(res.stdout) // 2 * 2]
        out.append((st + start, data))
    out.sort(key=lambda x: x[0])
    s._cache[key] = out
    return out


def _samples(data, i, j):
    buf = array("h")
    buf.frombytes(data[2 * i:2 * j])
    if sys.byteorder != "little":
        buf.byteswap()
    return buf


def pcm_peak(chunks, a, b):
    """[a, b]（錄製時鐘）內的樣本絕對值最大值；回傳 (峰值, 涵蓋秒數)。沒有段落涵蓋時峰值為 None。"""
    peak, covered = None, 0.0
    for st, data in chunks:
        n = len(data) // 2
        i = max(0, int(math.ceil((a - st) * PCM_RATE)))
        j = min(n, int(math.floor((b - st) * PCM_RATE)) + 1)
        if j <= i:
            continue
        covered += (j - i) / PCM_RATE
        seg = data[2 * i:2 * j]
        if seg.strip(b"\0") == b"":
            pk = 0
        else:
            pk = max(abs(x) for x in _samples(data, i, j))
        peak = pk if peak is None else max(peak, pk)
    return peak, covered


def zero_run(chunks, a, b, contiguous=0.1):
    """spec §4.17.8：包含 [a, b] 的最長「樣本全為 0」區段。回傳 (zs, ze, 左端是否延伸到段落開頭, 右端是否到段落結尾)；
    [a, b] 內有非 0 樣本或沒有段落涵蓋時回 None。相鄰兩段（後段 startedAt − 前段結束 < contiguous 秒）視為接續。"""
    segs = [(st, data, st + len(data) // 2 / PCM_RATE) for st, data in chunks]
    k0 = next((k for k, (st, _, en) in enumerate(segs) if st <= a < en), None)
    k1 = next((k for k, (st, _, en) in enumerate(segs) if st < b <= en), None)
    if k0 is None or k1 is None:
        return None
    peak, _ = pcm_peak(chunks, a, b)
    if peak is None or peak != 0:
        return None
    # 左端
    k = k0
    st, data, _ = segs[k]
    i = max(0, int(math.ceil((a - st) * PCM_RATE)))
    hit_start = False
    while True:
        st, data, _ = segs[k]
        left = data[:2 * i].rstrip(b"\0")
        i = (len(left) + 1) // 2
        if i > 0:
            break
        if k > 0 and st - segs[k - 1][2] < contiguous:
            k -= 1
            i = len(segs[k][1]) // 2
            continue
        hit_start = True
        break
    zs = segs[k][0] + i / PCM_RATE
    # 右端
    k = k1
    st, data, _ = segs[k]
    j = min(len(data) // 2, int(math.floor((b - st) * PCM_RATE)) + 1)
    hit_end = False
    while True:
        st, data, en = segs[k]
        right = data[2 * j:].lstrip(b"\0")
        j = (len(data) - len(right)) // 2
        if j < len(data) // 2:
            break
        if k + 1 < len(segs) and segs[k + 1][0] - en < contiguous:
            k += 1
            j = 0
            continue
        hit_end = True
        break
    ze = segs[k][0] + j / PCM_RATE
    return zs, ze, hit_start, hit_end


def fmt_iv(a, b):
    return f"[{a:.2f}, {'∞' if b is None or b == math.inf else f'{b:.2f}'}]"


# ---------- 判準 ----------

def longest_low(values, ws, t0, t1, offset=0.0, skip=None):
    """values 為每 ws 秒一個 dB 值（None＝沒有緩衝）；回傳與 [t0,t1] 重疊的窗中，連續 ≤ -60 的最長秒數。
    skip(窗起點秒) 為真的窗（R2：暫停／靜音區間）不算低音量、並打斷連續。"""
    best = cur = 0.0
    for i, v in enumerate(values):
        a = offset + i * ws
        if a + ws <= t0 or a >= t1:
            continue
        if skip is not None and skip(a):
            cur = 0.0
            continue
        if v is None or v <= SILENT_DB:
            cur += ws
            best = max(best, cur)
        else:
            cur = 0.0
    return best


def quiet_runs(values, ws, include):
    """include(窗起點秒) 為真的窗中，連續 ≤ -60 dBFS 或 null 的區間：[(起點秒, 長度秒)]。
    被排除的窗（include 為假）會打斷連續。"""
    runs, start, n = [], None, 0
    for i, v in enumerate(list(values) + [0.0]):  # 尾端哨兵：收掉最後一段
        a = i * ws
        low = i < len(values) and include(a) and (v is None or v <= SILENT_DB)
        if low:
            if start is None:
                start, n = a, 0
            n += 1
        elif start is not None:
            runs.append((round(start, 2), round(n * ws, 2)))
            start = None
    return runs


def long_quiet(values, ws, include):
    """spec §4.9.1、§4.9.3（t6 第三輪，缺陷 K (b)）：連續 ≥ 3 秒（0.5 秒時段為 6 個以上）≤ -60 dBFS 或 null 的區間。"""
    return [(a, d) for a, d in quiet_runs(values, ws, include) if d >= QUIET_RUN_MAX - 1e-9]


def quiet_outside(values, ws, events, skip=None):
    """事件前後 10 秒以外，連續 ≥ 3 秒 ≤ -60 或 null 的區間 [(起點秒, 長度秒)]（t6 第三輪，缺陷 K (b)；
    前一版是「任何一個時段 ≤ -60 就算」，對自然說話的停頓過嚴）。skip 同 longest_low（R2）。"""
    if skip is None:
        return long_quiet(values, ws, lambda a: not any(a + ws > t - AROUND and a < t + AROUND for t in events))
    return long_quiet(values, ws, lambda a: not skip(a) and
                      not any(a + ws > t - AROUND and a < t + AROUND for t in events))


def c_config(s, o):
    cfg = s.meta.get("config")
    diff = {k: (cfg.get(k) if isinstance(cfg, dict) else None, v) for k, v in CONFIG_SNAPSHOT.items()
            if not isinstance(cfg, dict) or cfg.get(k) != v or k not in cfg}
    return not diff, "與 spec §3.3 相同" if not diff else f"不同（實際, 應為）：{diff}"


def c_segment_files(s, o):
    segs = s.segments()
    if not segs:
        return False, "沒有任何 seg-*.mov"
    names = [p.name for p in segs]
    want = [f"seg-{i:04d}.mov" for i in range(1, len(segs) + 1)]
    if names != want:
        return False, f"段落檔名應從 seg-0001 連號：{names}"
    bad = [p.name for p in segs if probe(p) is None]
    if [n for n in bad if n != names[-1]]:
        return False, f"無法讀取的段落（不是最後一段）：{bad}"
    return True, f"{len(segs)} 段" + (f"；最後一段 {bad[0]} 無法讀取（未收尾）" if bad else "")


def c_segment_sizes(s, o):
    recs = {r["file"]: r for r in s.manifest.get("segments", [])}
    bad, checked = [], 0
    for p in s.segments():
        v = streams(p, "video")
        if not v:
            continue
        r = recs.get(p.name)
        if r is None:
            bad.append(f"{p.name} 不在 manifest")
            continue
        w, h = int(v[0]["width"]), int(v[0]["height"])
        checked += 1
        if abs(w - r["width"]) > 2 or abs(h - r["height"]) > 2:
            bad.append(f"{p.name} 實際 {w}×{h}，manifest {r['width']}×{r['height']}")
    return (not bad and checked > 0), ("; ".join(bad) if bad else f"{checked} 段與 manifest 相符（±2 px）")


def c_canvas(s, o):
    mf = s.manifest
    segs = mf.get("segments", [])
    want = {"width": max(r["width"] for r in segs), "height": max(r["height"] for r in segs)}
    v = streams(s.video, "video")
    if not v:
        return False, "影片沒有影片軌"
    got = {"width": int(v[0]["width"]), "height": int(v[0]["height"])}
    oc = mf.get("outputCanvas")
    ok = got == want and oc == want
    return ok, f"影片 {got}、outputCanvas {oc}、各段最大 {want}"


def c_video_format(s, o):
    v, a = streams(s.video, "video"), streams(s.video, "audio")
    ok = len(v) == 1 and v[0].get("codec_name") == "h264" and len(a) == 1
    return ok, f"影片軌 {[x.get('codec_name') for x in v]}、音軌 {len(a)} 條"


def c_video_covers(s, o):
    vd, ad = stream_duration(s.video, "video"), stream_duration(s.video, "audio")
    if vd is None or ad is None:
        return False, f"取不到 duration（影片 {vd}、音訊 {ad}）"
    return abs(vd - ad) < AV_TOL, f"影片軌 {vd:.3f}s、音訊軌 {ad:.3f}s、差 {abs(vd - ad) * 1000:.0f} ms"


def c_gap(s, o):
    mf = s.manifest
    recs = mf.get("segments", [])
    durs = []
    for r in recs:
        p = s.tracks / r["file"]
        d = segment_audio_duration(p) if p.is_file() else None  # §3.2 算法，與 finalize 的 gapStats 同一把尺（§4.6.19）
        durs.append(d)
    pauses, _ = r2_events(s)
    pairs = [(a, b) for a, b in pause_pairs(pauses) if b is not None]
    gaps, paused_bounds = [], 0
    for i in range(len(recs) - 1):
        if durs[i] is None or recs[i].get("startedAt") is None or recs[i + 1].get("startedAt") is None:
            continue
        g = recs[i + 1]["startedAt"] - recs[i]["startedAt"] - durs[i]
        # spec §3.11（R2）：暫停邊界（resume.t 與 startedAt_{k+1} 相差 < 0.5 秒）扣掉這次暫停的長度
        hit = next(((a, b) for a, b in pairs if abs(b - recs[i + 1]["startedAt"]) < PAUSE_TOL), None)
        if hit is not None:
            g -= hit[1] - hit[0]
            paused_bounds += 1
        gaps.append(g)
    if not gaps:
        return True, "只有一段，沒有邊界"
    mx, total = max(gaps), sum(gaps)
    amx = max(abs(g) for g in gaps)
    wall = (mf.get("gapStats") or {}).get("wallClock") or (recs[-1].get("finishedAt") or 0)
    ok = amx < MAX_GAP  # spec §4.4.3 (a)：max(|g_i|)；負值＝兩段重疊，也要擋
    note = f"max {mx:.3f}s、max|g| {amx:.3f}s、Σ {total:.3f}s"
    if pauses:
        wall -= paused_total(pauses)  # spec §4.18.5：短場次分界改用 wall − pausedTotal
        note += f"（{paused_bounds} 個暫停邊界已扣暫停長度）"
    if wall <= 240:
        ok = ok and total < MAX_GAP
    else:
        note += "（長場次：累積值只報不判）"
    gs = mf.get("gapStats")
    if gs and abs(gs.get("max", mx) - mx) > 0.01:
        ok = False
        note += f"；manifest.gapStats.max {gs.get('max')} 與實測不符"
    return ok, note


def c_one_audio(s, o):
    files = [p.name for p in s.rec.iterdir() if p.is_file() and p.name.lower().endswith(AUDIO_EXTS)]
    return len(files) == 1, f"錄音/ 第一層音源檔：{files}"


def ts_re():
    tree = ast.parse((REPO / "bin" / "_scaffold.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TS_RE" for t in node.targets):
            return re.compile(node.value.args[0].value)
    raise CheckError("bin/_scaffold.py 找不到 TS_RE")


def c_wav(s, o):
    w = s.wav
    a = streams(w, "audio")
    if not a:
        return False, "wav 沒有音軌"
    sr, ch = int(a[0]["sample_rate"]), int(a[0]["channels"])
    name_ok = re.fullmatch(re.escape(s.path.name) + r" \d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}\.wav", w.name)
    ok = sr == 16000 and ch == 1 and bool(name_ok) and bool(ts_re().search(w.name))
    return ok, f"{w.name}：{sr} Hz、{ch} ch"


def scaffold_keys():
    tree = ast.parse((REPO / "bin" / "_scaffold.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "expectedSpeakers" in keys:
                return set(keys)
    raise CheckError("bin/_scaffold.py 找不到 meeting.json 的 dict")


def c_meeting_json(s, o):
    p = s.rec / "meeting.json"
    if not p.is_file():
        return False, "沒有 錄音/meeting.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    want = scaffold_keys()
    ok = set(d) == want and d.get("expectedSpeakers", 0) is None
    return ok, f"鍵：多出 {sorted(set(d) - want)}、缺少 {sorted(want - set(d))}；expectedSpeakers={d.get('expectedSpeakers')!r}"


def c_levels(s, o):
    lv = s.manifest.get("levels") or {}
    sysv, mic = lv.get("system"), lv.get("mic")
    ok = (lv.get("windowSeconds") == 0.5 and isinstance(sysv, list) and isinstance(mic, list) and sysv and mic
          and all(v is None or isinstance(v, (int, float)) for v in sysv + mic))
    return bool(ok), f"windowSeconds={lv.get('windowSeconds')}、system {len(sysv or [])} 窗、mic {len(mic or [])} 窗"


def transports(meta):
    out = []
    dv = meta.get("devices") or {}
    for k in ("input", "output"):
        if dv.get(k):
            out.append(dv[k].get("transport"))
    for e in meta.get("deviceEvents") or []:
        for k in ("from", "to"):
            if e.get(k):
                out.append(e[k].get("transport"))
    return out


def c_no_aggregate(s, o):
    t = transports(s.meta)
    return "aggregate" not in t, f"transport：{sorted(set(x for x in t if x))}"


def c_expect(s, o):
    d = stream_duration(s.wav, "audio")
    if d is None:
        return False, "取不到 wav 長度"
    lo = o.expect_min if o.expect_min is not None else -math.inf
    hi = o.expect_max if o.expect_max is not None else math.inf
    return lo <= d <= hi, f"wav {d:.1f}s，期望 [{o.expect_min}, {o.expect_max}]"


def c_fps_peak(s, o):
    a, b = o.fps_interval
    ts = [t for t in frame_times(s.video) if a <= t < b]
    best = 0
    for i, t in enumerate(ts):
        if t + 1.0 > b + 1e-9:
            break
        best = max(best, sum(1 for u in ts[i:] if u < t + 1.0))
    return best >= FPS_PEAK, f"{a:.0f}–{b:.0f}s 間 1 秒滑動窗最大 {best} 格（門檻 {FPS_PEAK}）"


def window_peak(ts, win=1.0):
    """排序後的影格時間中，以每一幀為起點的 [t, t+win) 窗內影格數最大值。"""
    best, j = 0, 0
    for i, t in enumerate(ts):
        j = max(j, i)
        while j < len(ts) and ts[j] < t + win:
            j += 1
        best = max(best, j - i)
    return best


def close_intervals(ts):
    """相鄰影格 PTS 間隔 < 1/60 秒 − 1 ms 的次數（ts 已排序）。"""
    return sum(1 for x, y in zip(ts, ts[1:]) if y - x < MIN_FRAME_INTERVAL)


def c_fps_min(s, o):
    """spec §4.3.3（t6 第三輪，發現 M）：影片/*.mov 全片同時滿足
    (i) 1 秒滑動窗影格數最大值 ≤ 61；(ii) 間隔 < 1/60 秒 − 1 ms 的次數 ≤ 各段 seg-*.mov 同條件的合計＋(段數 − 1)；
    (iii) 相鄰影格間隔最小值 ≥ 1 ms。段落讀不到時 (ii) 判 FAIL。"""
    ts = sorted(frame_times(s.video))
    if len(ts) < 2:
        return False, "影格不足"
    peak = window_peak(ts)
    close = close_intervals(ts)
    mn = min(y - x for x, y in zip(ts, ts[1:]))
    segs = s.segments()
    unreadable = [p.name for p in segs if probe(p) is None]
    ok1, ok3 = peak <= FPS_WINDOW_MAX, mn >= MIN_FRAME_GAP
    notes = [f"(i) 1 秒滑動窗最大 {peak} 格（上限 {FPS_WINDOW_MAX}）"]
    if not segs or unreadable:
        ok2 = False
        why = "沒有任何 seg-*.mov" if not segs else f"讀不到的段落 {unreadable}"
        notes.append(f"(ii) 過近間隔 {close} 處，{why}，無法與原始段落比對")
    else:
        orig = sum(close_intervals(sorted(frame_times(p))) for p in segs)
        allowed = orig + len(segs) - 1
        ok2 = close <= allowed
        notes.append(f"(ii) 過近間隔（< {MIN_FRAME_INTERVAL * 1000:.2f} ms）{close} 處（上限＝原始段落 {orig}＋邊界 "
                     f"{len(segs) - 1}＝{allowed}）")
    notes.append(f"(iii) 最小間隔 {mn * 1000:.2f} ms（下限 {MIN_FRAME_GAP * 1000:.0f} ms）")
    return ok1 and ok2 and ok3, "；".join(notes)


def interruption_report(s, t):
    lv = s.manifest["levels"]
    ws = lv["windowSeconds"]
    mixed, start = s.mixed_db()
    pauses, _ = r2_events(s)
    tm = record_to_output(t, first_start(s), pauses) if pauses else t  # spec §4.18.7：混音軌是成品時間
    return {"system": longest_low(lv["system"], ws, t - AROUND, t + AROUND, skip=level_skip(s, "system")),
            "mic": longest_low(lv["mic"], ws, t - AROUND, t + AROUND, skip=level_skip(s, "mic")),
            "mixed": longest_low(mixed, 0.1, tm - AROUND, tm + AROUND, offset=start)}


def c_device_switch(s, o):
    meta = s.meta
    ev = meta.get("deviceEvents") or []
    to_bt = [e for e in ev if (e.get("to") or {}).get("transport") in BLUETOOTH]
    from_bt = [e for e in ev if (e.get("from") or {}).get("transport") in BLUETOOTH]
    if len(ev) < 2 or not to_bt or not from_bt:
        return False, f"deviceEvents 應至少兩筆且含切到藍牙與切回：{len(ev)} 筆"
    notes, ok = [], True
    for e in ev:
        r = interruption_report(s, e["t"])
        if max(r.values()) >= MAX_INTERRUPT:
            ok = False
        notes.append(f"t={e['t']:.1f} " + "、".join(f"{k} {v:.1f}s" for k, v in r.items()))
    lv = s.manifest["levels"]
    times = [e["t"] for e in ev]
    for k in ("system", "mic"):
        q = quiet_outside(lv[k], lv["windowSeconds"], times, skip=level_skip(s, k))
        if q:
            ok = False
            notes.append(f"{k} 在切換以外的時間有連續 ≥ {QUIET_RUN_MAX:.0f} 秒 ≤ -60 dBFS（起點秒, 長度秒）：{q[:5]}")
    return ok, "；".join(notes)


def c_all_bt(s, o):
    dv = s.meta.get("devices") or {}
    i, out = (dv.get("input") or {}).get("transport"), (dv.get("output") or {}).get("transport")
    ev = s.meta.get("deviceEvents") or []
    ok = i in BLUETOOTH and out in BLUETOOTH and not ev
    return ok, f"input {i}、output {out}、deviceEvents {len(ev)} 筆"


def c_all_bt_duration(s, o):
    d = stream_duration(s.wav, "audio") or 0
    return d >= 180, f"錄音 {d:.1f}s（全程藍牙至少 3 分鐘）"


def load_status(o, s):
    cand = [Path(o.status)] if o.status else []
    if not o.status:
        home = os.environ.get("MH_RECORD_HOME") or os.path.expanduser("~/.meeting-harness")
        cand.append(Path(home) / "record.status.json")
    for p in cand:
        if p.is_file():
            st = json.loads(p.read_text(encoding="utf-8"))
            if Path(st.get("session") or "").resolve() == s.path.resolve():
                return st
    return None


def c_hfp(s, o):
    meta = s.meta
    ch = [e for e in meta.get("audioFormatEvents") or []
          if e.get("from") and e.get("to") and e["from"].get("sampleRate") != e["to"].get("sampleRate")]
    if not ch:
        return False, "情境未觸發：audioFormatEvents 沒有 sampleRate 改變，請重測（不得判 PASS）"
    t = ch[0]["t"]
    lv = s.manifest["levels"]
    ws = lv["windowSeconds"]
    notes, ok = [], True
    for k in ("system", "mic"):
        skip = level_skip(s, k)
        gap = longest_low(lv[k], ws, t - AROUND, t + AROUND, skip=skip)
        notes.append(f"{k} 中斷 {gap:.1f}s")
        if gap >= MAX_INTERRUPT:
            ok = False
        if skip is None:
            after = long_quiet(lv[k], ws, lambda a: a >= t + AROUND)
        else:
            after = long_quiet(lv[k], ws, lambda a, skip=skip: a >= t + AROUND and not skip(a))
        if after:
            ok = False
            notes.append(f"{k} 格式變更後有連續 ≥ {QUIET_RUN_MAX:.0f} 秒 ≤ -60 dBFS（起點秒, 長度秒）：{after[:5]}")
    st = load_status(o, s)
    if st is None:
        return False, "；".join(notes + ["找不到該場次的 record.status.json，無法核對 warnings（用 --status 指定）"])
    bad = [w for w in st.get("warnings") or [] if w.get("kind") in ("silence_system", "silence_mic") and w.get("t", 0) >= t]
    if bad:
        ok = False
        notes.append(f"格式變更後出現靜音告警 {len(bad)} 筆")
    return ok, f"t={t:.1f} " + "；".join(notes)


def flashes(path):
    ts = frame_times(path)
    r = run([FFMPEG, "-v", "error", "-i", path, "-map", "0:v:0", "-fps_mode", "passthrough", "-vf",
             "scale=32:18,format=gray", "-f", "rawvideo", "-"], binary=True)
    n = 32 * 18
    lum = [sum(r.stdout[i:i + n]) / n for i in range(0, len(r.stdout) - n + 1, n)]
    out, prev = [], False
    for t, y in zip(ts, lum):
        on = y > 128
        if on and not prev:
            out.append(t)
        prev = on
    return out


def beeps(path):
    """前一版的嗶聲偵測（全頻 RMS、全片單一門檻）。§4.9.3 的 sync 判準自 t6 第三輪起改用 sync_offsets；
    本函式保留給 test_finalize.py（§4.6.14 配方 B）沿用，不再用於判準。"""
    samples, start = pcm_mono(path)
    db = rms_db_windows(samples, 16000, 0.005)
    finite = [d for d in db if d != -math.inf]
    if not finite:
        return []
    th = (statistics.median(finite) + max(finite)) / 2
    out, prev, last = [], False, -10.0
    for i, d in enumerate(db):
        on = d > th
        t = start + i * 0.005
        if on and not prev and t - last > 0.5:
            out.append(t)
            last = t
        prev = on
    return out


def band_pcm(path, index=0):
    """第 index 條音軌過兩次 1 kHz 帶通（spec §4.9.3），解成 48 kHz 單聲道 s16；回傳 (樣本 array, 起始秒)。"""
    a = streams(path, "audio")
    if len(a) <= index:
        raise CheckError(f"沒有第 {index + 1} 條音軌")
    start = float(a[index].get("start_time") or 0)
    r = run([FFMPEG, "-v", "error", "-i", path, "-map", f"0:a:{index}", "-af", f"{SYNC_BAND},{SYNC_BAND}",
             "-ac", "1", "-ar", str(SYNC_RATE), "-f", "s16le", "-"], binary=True)
    if r.returncode != 0:
        raise CheckError("解不出音訊")
    buf = array("h")
    buf.frombytes(r.stdout[:len(r.stdout) // 2 * 2])
    if sys.byteorder != "little":
        buf.byteswap()
    return buf, start


def sync_offsets(path, index=0):
    """spec §4.9.3（t6 第三輪，缺陷 K (a)）的量法：每個閃白對應的「嗶聲 − 閃白」（秒）。

    閃白＝每幀縮成 32×18 灰階、平均亮度由 ≤ 128 變 > 128 的那一幀的 PTS（flashes）；嗶聲＝第 index 條音軌
    過兩次 1 kHz 帶通、48 kHz 單聲道、1 ms 窗 RMS 包絡，在 [閃白 − 0.3, 閃白 + 0.3] 秒內取最大值，
    第一個 ≥ 最大值 50% 的窗的起點。該範圍的包絡最大值 ≤ -60 dBFS（沒有嗶聲）時記 None。
    回傳 [(閃白秒, 嗶聲 − 閃白秒 或 None)]；test_finalize.py（§4.6.20 (iii)）也以此量段落與最終影片。"""
    fl = flashes(path)
    if not fl:
        return []
    samples, start = band_pcm(path, index)
    n = int(round(SYNC_RATE * SYNC_ENV_WIN))
    nwin = len(samples) // n
    floor = 32768.0 * 10 ** (SILENT_DB / 20)
    out = []
    for t in fl:
        lo = max(0, int(math.floor((t - SYNC_SEARCH - start) / SYNC_ENV_WIN)))
        hi = min(nwin, int(math.ceil((t + SYNC_SEARCH - start) / SYNC_ENV_WIN)))
        env = []
        for w in range(lo, hi):
            chunk = samples[w * n:(w + 1) * n]
            env.append(math.sqrt(sum(x * x for x in chunk) / n))
        peak = max(env) if env else 0.0
        if peak <= floor:
            out.append((t, None))
            continue
        k = next(i for i, e in enumerate(env) if e >= SYNC_ONSET_RATIO * peak)
        out.append((t, start + (lo + k) * SYNC_ENV_WIN - t))
    return out


def c_sync(s, o):
    pairs = sync_offsets(s.video)
    diffs = [d for _, d in pairs if d is not None]
    if len(pairs) < 3 or len(diffs) < 3:
        return False, f"閃白 {len(pairs)} 次、嗶聲 {len(diffs)} 次（各至少 3 次）"
    missing = [round(t, 2) for t, d in pairs if d is None]
    worst = max(abs(d) for d in diffs)
    note = f"{len(pairs)} 組，最大時間差 {worst * 1000:.0f} ms（門檻 {SYNC_TOL * 1000:.0f} ms；1 kHz 帶通量法）"
    if missing:
        note += f"；{len(missing)} 個閃白附近 ±{SYNC_SEARCH} 秒找不到嗶聲：{missing[:5]}"
    return worst < SYNC_TOL and not missing, note


def nonblack_ratios(path, a, b, size=128):
    r = run([FFMPEG, "-v", "error", "-ss", str(a), "-to", str(b), "-i", path, "-map", "0:v:0", "-vf",
             f"fps=2,scale={size}:{size}:flags=neighbor,format=gray", "-f", "rawvideo", "-"], binary=True)
    n = size * size
    out = []
    for i in range(0, len(r.stdout) - n + 1, n):
        fr = r.stdout[i:i + n]
        hits = 0
        for gy in range(8):
            for gx in range(8):
                x = size * (2 * gx + 1) // 16
                y = size * (2 * gy + 1) // 16
                hits += fr[y * size + x] > 24
        out.append(hits / 64)
    return out


def c_space(s, o):
    a, b = o.space_interval
    rs = nonblack_ratios(s.video, a, b)
    if not rs:
        return False, f"{a:.0f}–{b:.0f}s 抽不到影格"
    mean = sum(rs) / len(rs)
    return mean >= SPACE_RATIO, f"{a:.0f}–{b:.0f}s 抽 {len(rs)} 幀，非黑比例平均 {mean:.3f}（門檻 {SPACE_RATIO}）"


# ---------- D20：--segment-writer ----------

def c_segment_tracks(s, o):
    """spec §4.4.1：每段恰有 1 條 H.264 影片軌與 2 條 AAC 音軌，順序為影片、系統聲音、麥克風。"""
    segs = s.segments()
    if not segs:
        return False, "沒有任何 seg-*.mov"
    bad = []
    for p in segs:
        info = probe(p)
        if info is None:
            bad.append(f"{p.name} 無法讀取")
            continue
        got = [(x.get("codec_type"), x.get("codec_name")) for x in sorted(info.get("streams", []),
                                                                         key=lambda x: int(x.get("index", 0)))]
        want = [("video", "h264"), ("audio", "aac"), ("audio", "aac")]
        if got != want:
            bad.append(f"{p.name} 軌道 {got}")
    return not bad, ("; ".join(bad) if bad else f"{len(segs)} 段都是 影片 h264＋系統聲音 aac＋麥克風 aac")


def c_segment_finished(s, o):
    """spec §4.4.3 (b)、§4.4.8：每段 finishedAt 不得是 null；每個邊界 finishedAt_i − startedAt_{i+1} < 5 秒。"""
    recs = s.manifest.get("segments", [])
    if not recs:
        return False, "manifest.segments 是空的"
    nulls = [r.get("file") for r in recs if r.get("finishedAt") is None]
    lags, late = [], []
    for a, b in zip(recs, recs[1:]):
        if a.get("finishedAt") is None or b.get("startedAt") is None:
            continue
        lag = a["finishedAt"] - b["startedAt"]
        lags.append(lag)
        if lag >= MAX_FINISH_LAG:
            late.append(f"{a.get('file')} 收尾晚 {lag:.3f}s")
    notes = []
    if nulls:
        notes.append(f"finishedAt 為 null：{nulls}")
    if late:
        notes.append("；".join(late))
    if not notes:
        notes.append(f"{len(recs)} 段都已收尾" + (f"，邊界收尾延遲最大 {max(lags):.3f}s" if lags else ""))
    return not nulls and not late, "；".join(notes)


def sample_rate_changes(meta):
    """audioFormatEvents 中 sampleRate 改變的事件；同一路 1 秒內的連續變更只留第一筆（spec §4.9.3）。"""
    out, last = [], {}
    for e in sorted(meta.get("audioFormatEvents") or [], key=lambda e: e.get("t", 0)):
        if not (e.get("from") and e.get("to")) or e["from"].get("sampleRate") == e["to"].get("sampleRate"):
            continue
        src = e.get("source")
        if src in last and e["t"] - last[src] < ROTATION_DEBOUNCE:
            continue
        last[src] = e["t"]
        out.append(e)
    return out


def c_segment_cadence(s, o):
    """spec §4.4.3 (c)：定期換段的 startedAt_{i+1} − startedAt_i ＝ 60.000 秒（容許 0.001）。

    提前換段不受此約束（t6 第二輪，缺陷 G）：間隔 < 60.000 − 0.001 秒，且 (1) record.meta.json.audioFormatEvents
    中有任何一筆（任何欄位改變都算，不限 sampleRate）的 t 與 startedAt_{i+1} 相差 < 0.5 秒，或 (2) 第 i 段的
    finishedAt 是 null（writer 失敗後提前換段）。只用場次內的檔，不看 record.status.json。"""
    recs = s.manifest.get("segments", [])
    starts = [r.get("startedAt") for r in recs]
    if len(recs) < 2:
        return False, "只有一段，沒有換段可核對"
    if any(x is None for x in starts):
        return False, f"有段落的 startedAt 是 null：{starts}"
    changes = [e["t"] for e in (s.meta.get("audioFormatEvents") or []) if isinstance(e.get("t"), (int, float))]
    resumes = [b for _, b in pause_pairs(r2_events(s)[0]) if b is not None]
    bad, early, resumed = [], 0, 0
    for i in range(len(starts) - 1):
        d = starts[i + 1] - starts[i]
        if abs(d - SEGMENT_SECONDS) <= CADENCE_TOL:
            continue
        if any(abs(starts[i + 1] - t) < PAUSE_TOL for t in resumes):  # spec §4.18.5：暫停後繼續的換段不受 60 秒約束
            resumed += 1
            continue
        near_format = any(abs(starts[i + 1] - t) < ROTATION_TOL for t in changes)
        writer_failed = recs[i].get("finishedAt") is None
        if d < SEGMENT_SECONDS - CADENCE_TOL and (near_format or writer_failed):
            early += 1
            continue
        bad.append(f"{recs[i + 1].get('file')} 與前一段間隔 {d:.3f}s")
    note = "；".join(bad) if bad else f"{len(starts) - 1 - early - resumed} 個定期換段間隔都是 {SEGMENT_SECONDS:.3f}s" + (
        f"（另有 {early} 個提前換段不計：格式變更或 writer 失敗）" if early else "") + (
        f"（另有 {resumed} 個暫停後繼續的換段不計）" if resumed else "")
    return not bad, note


def c_segment_video_start(s, o):
    """spec §4.4.4：seg-0002 起每段都含 video stream，且影片軌 start_time ≤ 0.05 秒。"""
    segs = s.segments()
    if len(segs) < 2:
        return False, f"只有 {len(segs)} 段，沒有跨過換段"
    bad = []
    for p in segs[1:]:
        v = streams(p, "video")
        if not v:
            bad.append(f"{p.name} 沒有 video stream")
            continue
        st = v[0].get("start_time")
        st = float(st) if st not in (None, "N/A") else None
        if st is None or st > VIDEO_START_MAX:
            bad.append(f"{p.name} 影片軌 start_time {st}")
    return not bad, ("; ".join(bad) if bad else f"seg-0002 起 {len(segs) - 1} 段影片軌都從段落起點開始")


def c_stop_tail(s, o):
    """spec §4.4.8：wallClock 與 startedAt_1 + Σ audioDuration_i 差 < 1 秒。"""
    mf = s.manifest
    recs = mf.get("segments", [])
    wall = (mf.get("gapStats") or {}).get("wallClock")
    if not recs or wall is None:
        return False, "manifest 缺 segments 或 gapStats.wallClock"
    ads = [r.get("audioDuration") for r in recs]
    if recs[0].get("startedAt") is None or any(a is None for a in ads):
        return False, f"startedAt_1 或 audioDuration 有 null：{recs[0].get('startedAt')}、{ads}"
    covered = recs[0]["startedAt"] + sum(ads)
    pauses, _ = r2_events(s)
    if not pauses:
        diff = wall - covered
        return abs(diff) < STOP_TAIL_TOL, f"wallClock {wall:.3f}s、startedAt_1＋Σ audioDuration {covered:.3f}s、差 {diff:.3f}s"
    # spec §4.18.5：加 pausedTotal；暫停中停止（最後一筆是 pause）以它的 t 代替 wallClock
    pt = paused_total(pauses)
    covered += pt
    label = "wallClock"
    if pauses[-1].get("kind") == "pause" and _num(pauses[-1].get("t")) is not None:
        wall, label = float(pauses[-1]["t"]), "最後一筆 pause.t"
    diff = wall - covered
    return abs(diff) < STOP_TAIL_TOL, (f"{label} {wall:.3f}s、startedAt_1＋Σ audioDuration＋pausedTotal {pt:.3f} "
                                       f"＝{covered:.3f}s、差 {diff:.3f}s")


def c_format_rotation(s, o):
    """spec §4.9.3（D20）：每筆 sampleRate 改變都有段落邊界的 startedAt 與它相差 < 0.5 秒；不得出現 segment_write_failed。"""
    changes = sample_rate_changes(s.meta)
    if not changes:
        return False, "情境未觸發：audioFormatEvents 沒有 sampleRate 改變，請重測（不得判 PASS）"
    starts = [r.get("startedAt") for r in s.manifest.get("segments", [])[1:] if r.get("startedAt") is not None]
    notes, ok = [], True
    for e in changes:
        near = [b for b in starts if abs(b - e["t"]) < ROTATION_TOL]
        if not near:
            ok = False
            notes.append(f"t={e['t']:.1f}（{e.get('source')}）附近 {ROTATION_TOL}s 內沒有段落邊界")
        else:
            notes.append(f"t={e['t']:.1f} 邊界 {near[0]:.3f}")
    st = load_status(o, s)
    if st is None:
        return False, "；".join(notes + ["找不到該場次的 record.status.json，無法核對 segment_write_failed（用 --status 指定）"])
    failed = [w for w in st.get("warnings") or [] if w.get("kind") == "segment_write_failed"]
    if failed:
        ok = False
        notes.append(f"出現 segment_write_failed {len(failed)} 筆")
    return ok, "；".join(notes)


# ---------- R2：--pause-mute ----------

def _not_triggered(what):
    return False, f"{NOT_TRIGGERED}：{what} 是空的，請重測（不得判 PASS）"


def c_pause_events(s, o):
    """spec §4.18.6：pauseEvents 非空、依時間遞增、pause／resume 交替且以 pause 開頭；
    每筆 pause 的 t 與某段結束（startedAt_i＋audioDuration_i）、每筆 resume 的 t 與某段 startedAt 相差 < 0.5 秒。"""
    ev, _ = r2_events(s)
    if not ev:
        return _not_triggered("pauseEvents")
    ts = [_num(e.get("t")) for e in ev]
    kinds = [e.get("kind") for e in ev]
    bad = []
    if any(t is None for t in ts):
        return False, f"pauseEvents 有 t 不是數字：{ts}"
    if any(b <= a for a, b in zip(ts, ts[1:])):
        bad.append(f"時間沒有遞增：{ts}")
    want = ["pause" if i % 2 == 0 else "resume" for i in range(len(kinds))]
    if kinds != want:
        bad.append(f"kind 應以 pause 開頭、pause／resume 交替：{kinds}")
    ends = [e for e in segment_ends(s) if e is not None]
    starts = [_num(r.get("startedAt")) for r in s.manifest.get("segments", [])]
    starts = [x for x in starts if x is not None]
    for t, k in zip(ts, kinds):
        if k == "pause" and not any(abs(t - e) < PAUSE_TOL for e in ends):
            bad.append(f"pause t={t:.3f} 附近 {PAUSE_TOL}s 內沒有段落結束")
        if k == "resume" and not any(abs(t - x) < PAUSE_TOL for x in starts):
            bad.append(f"resume t={t:.3f} 附近 {PAUSE_TOL}s 內沒有段落開始")
    return not bad, ("；".join(bad) if bad else f"{len(ev)} 筆事件，暫停 {kinds.count('pause')} 次、"
                                                f"共 {paused_total(ev):.3f}s，都對得上段落邊界")


def c_pause_cut(s, o):
    """spec §4.18.6：錄音/*.wav 長度與（停止點 − startedAt_1 − pausedTotal）相差 < 1 秒；停止點＝最後一段 startedAt＋audioDuration。"""
    ev, _ = r2_events(s)
    if not ev:
        return _not_triggered("pauseEvents")
    recs = s.manifest.get("segments", [])
    ends = segment_ends(s)
    if not recs or ends[-1] is None:
        return False, "算不出停止點（最後一段的 startedAt 或 audioDuration 缺）"
    want = ends[-1] - first_start(s) - paused_total(ev)
    d = stream_duration(s.wav, "audio")
    if d is None:
        return False, "取不到 wav 長度"
    return abs(d - want) < CUT_TOL, (f"wav {d:.3f}s、停止點 {ends[-1]:.3f} − startedAt_1 {first_start(s):.3f} − "
                                     f"pausedTotal {paused_total(ev):.3f} ＝ {want:.3f}s、差 {d - want:.3f}s")


def mute_intervals(s, edge=0.0):
    """靜音區間 [m＋edge, u − edge]（沒配對延伸到最後一段結束）。"""
    _, mutes = r2_events(s)
    end = session_end(s)
    return [(m + edge, (u if u is not None else end) - edge, u is not None) for m, u in mute_pairs(mutes)]


def c_mic_mute_zero(s, o):
    """spec §4.17.5：每個靜音區間 [mute.t＋0.2, unmute.t − 0.2] 的麥克風軌（第 3 條軌）解碼後樣本絕對值最大為 0。"""
    _, mutes = r2_events(s)
    if not mutes:
        return _not_triggered("micMuteEvents")
    chunks = track_pcm(s, MIC_TRACK)
    bad, notes = [], []
    for a, b, _ in mute_intervals(s, MUTE_EDGE):
        if b <= a:
            notes.append(f"{fmt_iv(a, b)} 太短，略過")
            continue
        peak, cov = pcm_peak(chunks, a, b)
        if peak is None:
            bad.append(f"{fmt_iv(a, b)} 沒有任何段落涵蓋")
        elif peak != 0:
            bad.append(f"{fmt_iv(a, b)} 麥克風有非 0 樣本（最大絕對值 {peak}）")
        else:
            notes.append(f"{fmt_iv(a, b)} 全為 0（涵蓋 {cov:.1f}s）")
    return not bad, "；".join(bad + notes)


def c_mute_system_kept(s, o):
    """spec §4.17.5：同一個靜音區間內，系統聲音軌至少有一個 0.5 秒窗的峰值 > -60 dBFS。"""
    _, mutes = r2_events(s)
    if not mutes:
        return _not_triggered("micMuteEvents")
    chunks = track_pcm(s, SYSTEM_TRACK)
    floor = 32768.0 * 10 ** (SILENT_DB / 20)
    bad, notes = [], []
    for a, b, _ in mute_intervals(s, MUTE_EDGE):
        if b <= a:
            notes.append(f"{fmt_iv(a, b)} 太短，略過")
            continue
        peak, _ = pcm_peak(chunks, a, b)
        db = -math.inf if not peak else 20 * math.log10(peak / 32768.0)
        if peak is None or peak <= floor:
            bad.append(f"{fmt_iv(a, b)} 系統聲音峰值 {db:.1f} dBFS（應 > {SILENT_DB:.0f}）")
        else:
            notes.append(f"{fmt_iv(a, b)} 系統聲音峰值 {db:.1f} dBFS")
    return not bad, "；".join(bad + notes)


def _status_or_fail(o, s):
    st = load_status(o, s)
    if st is None:
        raise CheckError("找不到該場次的 record.status.json（用 --status 指定）")
    return st


def c_no_false_silence(s, o):
    """spec §4.17.6：warnings 中不得有 silence_mic 落在靜音區間 [mute.t, unmute.t＋1]，也不得有 silence_system／silence_mic
    落在暫停區間 [pause.t, resume.t＋1]（沒配對的延伸到最後）；找不到狀態檔判 FAIL。"""
    pauses, mutes = r2_events(s)
    if not pauses and not mutes:
        return _not_triggered("pauseEvents 與 micMuteEvents")
    st = _status_or_fail(o, s)
    end = session_end(s)
    piv = [(a, b + EVENT_GRACE) for a, b in closed(pause_pairs(pauses), end)]
    miv = [(a, b + EVENT_GRACE) for a, b in closed(mute_pairs(mutes), end)]
    bad = []
    for w in st.get("warnings") or []:
        k, t = w.get("kind"), _num(w.get("t"))
        if t is None:
            continue
        if k == "silence_mic" and any(a <= t <= b for a, b in miv):
            bad.append(f"silence_mic t={t:.1f} 落在靜音區間")
        if k in ("silence_system", "silence_mic") and any(a <= t <= b for a, b in piv):
            bad.append(f"{k} t={t:.1f} 落在暫停區間")
    return not bad, ("；".join(bad) if bad else f"暫停 {len(piv)} 段、靜音 {len(miv)} 段內沒有靜音告警")


def c_markers(s, o):
    """spec §4.19.4：錄音/markers.json 存在且與 tracks/markers.json 相同；label 依序「標記 1」…；t 不遞減、0 ≤ t ≤ wav 長度；
    每筆 t 與 outputTime(recordT, startedAt_1, pauseEvents) 相差 ≤ 0.01 秒。"""
    src, dst = s.tracks / "markers.json", s.rec / "markers.json"
    if not src.is_file() and not dst.is_file():
        return False, f"{NOT_TRIGGERED}：沒有 markers.json，請重測（不得判 PASS）"
    if not dst.is_file():
        return False, "沒有 錄音/markers.json（finalize 應從 tracks/ 複製）"
    if not src.is_file():
        return False, "沒有 錄音/tracks/markers.json"
    if src.read_bytes() != dst.read_bytes():
        return False, "錄音/markers.json 與 錄音/tracks/markers.json 內容不同"
    items = json.loads(dst.read_text(encoding="utf-8"))
    if not isinstance(items, list) or not items:
        return False, f"markers.json 應為非空陣列：{items!r}"
    pauses, _ = r2_events(s)
    st1 = first_start(s)
    wav = stream_duration(s.wav, "audio")
    if wav is None:
        return False, "取不到 wav 長度"
    bad = []
    prev = -math.inf
    for i, mk in enumerate(items, start=1):
        if set(mk) != {"t", "recordT", "wallClock", "label"}:
            bad.append(f"第 {i} 筆鍵應恰為 t、recordT、wallClock、label：{sorted(mk)}")
            continue
        if mk["label"] != f"標記 {i}":
            bad.append(f"第 {i} 筆 label 應為「標記 {i}」：{mk['label']!r}")
        t, rt = _num(mk["t"]), _num(mk["recordT"])
        if t is None or rt is None:
            bad.append(f"第 {i} 筆 t／recordT 不是數字")
            continue
        if t < prev:
            bad.append(f"第 {i} 筆 t={t:.3f} 比前一筆小")
        prev = t
        if not 0 <= t <= wav:
            bad.append(f"第 {i} 筆 t={t:.3f} 不在 [0, wav 長度 {wav:.3f}]")
        want = record_to_output(rt, st1, pauses)
        if abs(t - want) > OUTPUT_T_TOL:
            bad.append(f"第 {i} 筆 t={t:.3f}，outputTime(recordT {rt:.3f}) 為 {want:.3f}")
    return not bad, ("；".join(bad) if bad else f"{len(items)} 個標記，時間對得上成品（wav {wav:.1f}s）")


def c_mute_timing(s, o):
    """spec §4.17.8：麥克風軌依 startedAt 接成錄製時鐘上的序列；每個靜音區間 [m, u) 找出包含 [m＋0.2, u − 0.2] 的最長
    「樣本全為 0」區段 [zs, ze]，|zs − m| ≤ 0.5 且（有配對時）|ze − u| ≤ 0.5；zs 早於 m − 0.5 且延伸到段落開頭時
    說明「靜音前麥克風也是數位 0，無法判定時刻」。"""
    _, mutes = r2_events(s)
    if not mutes:
        return _not_triggered("micMuteEvents")
    chunks = track_pcm(s, MIC_TRACK)
    end = session_end(s)
    bad, notes = [], []
    for m, u in mute_pairs(mutes):
        a, b = m + MUTE_EDGE, (u if u is not None else end) - MUTE_EDGE
        if b <= a:
            notes.append(f"{fmt_iv(m, u)} 太短，略過")
            continue
        run_ = zero_run(chunks, a, b)
        if run_ is None:
            bad.append(f"{fmt_iv(m, u)}：[m＋{MUTE_EDGE}, u − {MUTE_EDGE}] 內不是全為 0（或沒有段落涵蓋）")
            continue
        zs, ze, hit_start, _ = run_
        if zs < m - MUTE_TIMING_TOL and hit_start:
            bad.append(f"{fmt_iv(m, u)}：靜音前麥克風也是數位 0，無法判定時刻（全 0 區段從段落開頭 {zs:.3f} 起）")
            continue
        msg = f"{fmt_iv(m, u)}：全 0 區段 [{zs:.3f}, {ze:.3f}]"
        if abs(zs - m) > MUTE_TIMING_TOL:
            bad.append(msg + f"，開頭與 mute.t 差 {zs - m:.3f}s")
        elif u is not None and abs(ze - u) > MUTE_TIMING_TOL:
            bad.append(msg + f"，結尾與 unmute.t 差 {ze - u:.3f}s")
        else:
            notes.append(msg)
    return not bad, "；".join(bad + notes)


def c_no_false_black(s, o):
    """spec §4.18.11：manifest.blackIntervals 的 start、與 warnings 中 black／suspended 的 t，都不得落在暫停區間
    [pause.t, resume.t＋1]（沒配對延伸到最後一段結束）；找不到狀態檔判 FAIL。"""
    pauses, _ = r2_events(s)
    if not pauses:
        return _not_triggered("pauseEvents")
    end = session_end(s)
    piv = [(a, b + EVENT_GRACE) for a, b in closed(pause_pairs(pauses), end)]
    bad = []
    for bi in s.manifest.get("blackIntervals") or []:
        t = _num(bi.get("start"))
        if t is not None and any(a <= t <= b for a, b in piv):
            bad.append(f"blackIntervals start={t:.1f} 落在暫停區間")
    st = _status_or_fail(o, s)
    for w in st.get("warnings") or []:
        t = _num(w.get("t"))
        if w.get("kind") in ("black", "suspended") and t is not None and any(a <= t <= b for a, b in piv):
            bad.append(f"{w.get('kind')} t={t:.1f} 落在暫停區間")
    return not bad, ("；".join(bad) if bad else f"暫停 {len(piv)} 段內沒有黑畫面區間與 black／suspended 告警")


def c_event_output_t(s, o):
    """spec §4.18.12：pauseEvents 與 micMuteEvents 每一筆的 outputT 與 record_to_output(t, startedAt_1, pauseEvents)
    相差 ≤ 0.01 秒。"""
    pauses, mutes = r2_events(s)
    if not pauses and not mutes:
        return _not_triggered("pauseEvents 與 micMuteEvents")
    st1 = first_start(s)
    bad, n = [], 0
    for name, evs in (("pauseEvents", pauses), ("micMuteEvents", mutes)):
        for i, e in enumerate(evs, start=1):
            t, ot = _num(e.get("t")), _num(e.get("outputT"))
            if t is None or ot is None:
                bad.append(f"{name} 第 {i} 筆缺 t 或 outputT")
                continue
            n += 1
            want = record_to_output(t, st1, pauses)
            if abs(ot - want) > OUTPUT_T_TOL:
                bad.append(f"{name} 第 {i} 筆 t={t:.3f} 的 outputT {ot:.3f}，應為 {want:.3f}")
    return not bad, ("；".join(bad) if bad else f"{n} 筆事件的 outputT 都對得上（startedAt_1 {st1:.3f}）")


PAUSE_MUTE_CHECKS = [
    ("pause_events", c_pause_events), ("pause_cut", c_pause_cut), ("mic_mute_zero", c_mic_mute_zero),
    ("mute_system_kept", c_mute_system_kept), ("no_false_silence", c_no_false_silence), ("markers", c_markers),
    ("mute_timing", c_mute_timing), ("no_false_black", c_no_false_black), ("event_output_t", c_event_output_t),
]


DEFAULT_CHECKS = [
    ("config_snapshot", c_config), ("segment_files", c_segment_files), ("segment_sizes", c_segment_sizes),
    ("canvas", c_canvas), ("video_format", c_video_format), ("video_covers_audio", c_video_covers),
    ("gap", c_gap), ("one_audio_file", c_one_audio), ("wav_format", c_wav), ("meeting_json", c_meeting_json),
    ("levels", c_levels), ("no_aggregate", c_no_aggregate),
]


def selected_checks(o):
    checks = list(DEFAULT_CHECKS)
    if o.expect_min is not None or o.expect_max is not None:
        checks.append(("expect_duration", c_expect))
    if o.fps_interval:
        checks += [("fps_peak", c_fps_peak), ("fps_min_interval", c_fps_min)]
    if o.device_switch:
        checks.append(("device_switch", c_device_switch))
    if o.all_bluetooth:
        checks += [("all_bluetooth", c_all_bt), ("all_bluetooth_duration", c_all_bt_duration)]
    if o.hfp:
        checks.append(("hfp", c_hfp))
    if o.sync:
        checks.append(("sync", c_sync))
    if o.space_interval:
        checks.append(("space_interval", c_space))
    if o.segment_writer:
        checks += [("segment_tracks", c_segment_tracks), ("segment_finished", c_segment_finished),
                   ("segment_cadence", c_segment_cadence), ("segment_video_start", c_segment_video_start),
                   ("stop_tail", c_stop_tail)]
        if o.hfp:
            checks.append(("format_rotation", c_format_rotation))
    if o.pause_mute:
        checks += PAUSE_MUTE_CHECKS
    return checks


def run_checks(session, o):
    s = Session(session)
    results = []
    for name, fn in selected_checks(o):
        try:
            ok, detail = fn(s, o)
        except (CheckError, KeyError, ValueError, TypeError, OSError, json.JSONDecodeError, IndexError,
                ZeroDivisionError, AttributeError) as e:
            ok, detail = False, f"無法核對：{e}"
        results.append({"check": name, "ok": bool(ok), "detail": detail})
    return results


def build_parser():
    p = argparse.ArgumentParser(prog="e2e_check.py", description="端到端錄製結果的機械核對（逐條 PASS／FAIL）")
    p.add_argument("session", nargs="?", help="場次目錄（含 錄音/、影片/）")
    p.add_argument("--expect-min", type=float, metavar="S", help="錄音長度下限（秒）")
    p.add_argument("--expect-max", type=float, metavar="S", help="錄音長度上限（秒）")
    p.add_argument("--device-switch", action="store_true", help="§4.9.1 錄製中切換藍牙：每次中斷 < 3 秒")
    p.add_argument("--all-bluetooth", action="store_true", help="§4.9.2 全程藍牙")
    p.add_argument("--hfp", action="store_true", help="§4.9.3 HFP 取樣率中途改變")
    p.add_argument("--sync", action="store_true",
                   help="§4.9.3 同步測試源的閃白與嗶聲時間差 < 100 ms（嗶聲以 1 kHz 帶通＋局部起點量）")
    p.add_argument("--fps-interval", type=parse_interval, metavar="mm:ss-mm:ss",
                   help="§4.3.3 量 fps 尖峰的區間；同時加 fps_min_interval（全片三條件，含與 seg-*.mov 比對）")
    p.add_argument("--space-interval", type=parse_interval, metavar="mm:ss-mm:ss",
                   help="§4.10.2 Space 切走的區間（非黑比例 ≥ 0.5）")
    p.add_argument("--status", metavar="FILE",
                   help="record.status.json（--hfp、--pause-mute 核對 warnings 用；預設讀 MH_RECORD_HOME）")
    p.add_argument("--segment-writer", action="store_true",
                   help="D20 自管 AVAssetWriter 的段落判準：segment_tracks、segment_finished、segment_cadence、"
                        "segment_video_start、stop_tail；與 --hfp 同時給時加 format_rotation")
    p.add_argument("--pause-mute", action="store_true",
                   help="R2 暫停／麥克風靜音／標記的判準：pause_events、pause_cut、mic_mute_zero、mute_system_kept、"
                        "no_false_silence、markers、mute_timing、no_false_black、event_output_t（後兩項與 "
                        "no_false_silence 讀 --status）")
    p.add_argument("--json", action="store_true", help="印機器可讀結果")
    p.add_argument("--print-sync-source", action="store_true", help="印出產生同步測試源的 ffplay 指令")
    return p


def main(argv=None):
    p = build_parser()
    o = p.parse_args(argv)
    if o.print_sync_source:
        print_sync_source()
        return 0
    if not o.session:
        p.print_usage(sys.stderr)
        print("e2e_check.py：需要場次目錄", file=sys.stderr)
        return 2
    if not Path(o.session).is_dir():
        print(f"e2e_check.py：找不到場次目錄：{o.session}", file=sys.stderr)
        return 2
    results = run_checks(o.session, o)
    if o.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['check']}  {r['detail']}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())

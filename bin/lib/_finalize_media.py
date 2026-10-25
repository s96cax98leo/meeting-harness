"""_finalize_media.py — bin/_record_finalize.py 用的純函式：數值解析、ffprobe 結果的小工具、混音濾鏡字串
（meeting-speed spec §4.13；由 _record_finalize.py 搬出，行為不變）。不啟動子程序、不寫檔。"""
import math
import time

LIMIT = 0.891             # 混音後限幅上限 -1 dBFS（design.md §7.4）


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


def stream_dts(pkts, index):
    """probe_packets 結果中某條軌的 dts（依封包順序；N/A 略過，不看 flags）。"""
    out = []
    for k in pkts:
        if k.get("stream_index") == index:
            d = num(k.get("dts_time"))
            if d is not None:
                out.append(d)
    return out


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")

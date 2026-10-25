"""_finalize_sync.py — 影音延遲補償（S-C）的純函式：每段延遲、連續延後的區間運算、音軌角色
（meeting-speed spec §4.13；由 _record_finalize.py 搬出，行為不變；呼叫 ffmpeg 的部分留在 _record_finalize.py）。"""
import os
import shutil

from _finalize_media import num
from _record_lib import load_json, record_home

SYNC_MODES = ("off", "reported", "calibrated")
SYNC_MAX_DELAY = 0.5      # 補償延遲上限（秒；R3-D9）
SYNC_RATE = 48000         # 補償路徑的 PCM 取樣率；兩軌一律 48 kHz 雙聲道 s16le
SYNC_FRAME_BYTES = 4      # 一個取樣框（雙聲道 × 16 位元）
COPY_CHUNK = 1 << 20


def reported_seconds(e):
    """outputLatencies 一筆的回報延遲：(Latency＋SafetyOffset＋stream Latency＋BufferFrameSize) ÷ NominalSampleRate；
    讀不到（任一為 null）時用 reportedSeconds，仍讀不到回 None（spec §3.17、ADR adr-r3-sync-compensation.md）。"""
    rate = num(e.get("sampleRate"))
    parts = [num(e.get(k)) for k in ("latencyFrames", "safetyOffsetFrames", "streamLatencyFrames", "bufferFrameSize")]
    if rate and rate > 0 and all(p is not None for p in parts):
        return sum(parts) / rate
    return num(e.get("reportedSeconds"))


def calibration_table():
    """<record home>/sync-calibration.json：{"devices": {uid: 秒數}}，或扁平的 {uid: 秒數}；讀不到＝{}。"""
    d = load_json(os.path.join(record_home(), "sync-calibration.json"), {})
    if not isinstance(d, dict):
        return {}
    table = d.get("devices") if isinstance(d.get("devices"), dict) else d
    return {k: v for k, v in table.items() if isinstance(k, str)}


def latency_entry(entries, start, length):
    """段落生效的那筆 outputLatencies：t ≤ 段落起點＋min(0.5, 段長／2) 的最後一筆。
    輸出裝置變更提前換段時，新段起點與該筆 t 相差 < 0.5 秒（spec §4.37.6），起點可能略早於 t；
    容差不超過段長的一半，避免把緊接在裝置變更前的短段算成新裝置。"""
    lim = start + min(0.5, max(length, 0.0) / 2)
    best = None
    for e in entries:
        t = num(e.get("t"))
        if t is not None and t <= lim and (best is None or t >= num(best.get("t"))):
            best = e
    return best


def sync_plan(mode, good, tracks, seg_meta):
    """每段套用的延遲（spec §3.17 finalize.json.syncCompensation.segments；R3-D9）。
    reported：該段生效那筆 outputLatencies 的回報值（讀不到 → 0、source missing；場次沒有 outputLatencies → 0、source none）；
    calibrated：sync-calibration.json 依輸出 uid 查表（查不到 → 0、source missing）；一律夾在 [0, 0.5] 秒。"""
    if mode == "off":
        return []
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    meta = meta if isinstance(meta, dict) else {}
    raw = meta.get("outputLatencies")
    entries = [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []
    dev = (meta.get("devices") or {}).get("output") if isinstance(meta.get("devices"), dict) else None
    fallback_uid = dev.get("uid") if isinstance(dev, dict) and isinstance(dev.get("uid"), str) else None
    table = calibration_table() if mode == "calibrated" else {}
    first = num((seg_meta.get(os.path.basename(good[0][0])) or {}).get("startedAt")) if good else None
    plan, clock = [], first or 0.0
    for p, a in good:
        f = os.path.basename(p)
        st = num((seg_meta.get(f) or {}).get("startedAt"))
        st = clock if st is None else st
        clock = st + a["length"]
        e = latency_entry(entries, st, a["length"])
        uid = e.get("uid") if e and isinstance(e.get("uid"), str) else fallback_uid
        if mode == "reported":
            v = reported_seconds(e) if e else None
            source = "reported" if v is not None else ("missing" if entries else "none")
        else:
            v = num(table.get(uid)) if uid is not None else None
            source = "calibrated" if v is not None else "missing"
        v = 0.0 if v is None else v
        clamped = v < 0.0 or v > SYNC_MAX_DELAY
        v = min(max(v, 0.0), SYNC_MAX_DELAY)
        plan.append({"file": f, "outputUid": uid, "delaySeconds": round(v, 4), "source": source, "clamped": clamped})
    return plan


def delay_ops(frames, delays):
    """系統聲音整條連續延後（ADR adr-r3-concat-then-mix.md 落實第 2 點；修正輪 C）。
    frames：各段在串接時間軸上的取樣框數；delays：各段的延遲（取樣框）。相鄰且延遲相同的段併成一個區間；
    開頭補 L_1；L 變大時在兩區間之間補 (L_{k+1} − L_k)，L 變小時截掉前一區間的尾 (L_k − L_{k+1})；
    最後截到原總長。回傳 [("zero", n) | ("copy", 起點, 長度)]（以取樣框計）與區間清單 [(起, 迄, L)]。"""
    intervals = []
    pos = 0
    for n, d in zip(frames, delays):
        if intervals and intervals[-1][2] == d:
            intervals[-1][1] = pos + n
        else:
            intervals.append([pos, pos + n, d])
        pos += n
    total = pos
    ops = []

    def length():
        return sum(o[1] if o[0] == "zero" else o[2] for o in ops)

    def truncate_to(p):
        # 截掉已排輸出在 p 之後的部分（延遲變小：前一區間的尾與下一區間重疊；前一區間比重疊短時連更前面的也截）
        while ops and length() > p:
            over = length() - p
            o = ops.pop()
            n = o[1] if o[0] == "zero" else o[2]
            if n > over:
                ops.append(("zero", n - over) if o[0] == "zero" else ("copy", o[1], n - over))

    for s, e, d in intervals:
        target = s + d             # 區間 k 的內容在成品裡從 s_k＋L_k 開始
        cur = length()
        if cur < target:
            ops.append(("zero", target - cur))
        elif cur > target:
            truncate_to(target)
        if e > s:
            ops.append(("copy", s, e - s))
    cur = length()
    if cur > total:
        truncate_to(total)         # 最後截到與 off 相同的總長
    elif cur < total:
        ops.append(("zero", total - cur))
    return ops, [tuple(x) for x in intervals]


def track_roles(a):
    """段落的音軌角色：錄製器寫入順序是系統聲音在前、麥克風在後（SegmentWriter）。
    以 ffprobe 的音軌順序判斷（不以有沒有封包判斷，避免某一軌沒有封包時角色錯位）。"""
    order = [s.get("index") for s in a["info"].get("streams", []) if s.get("codec_type") == "audio"]
    by_index = {t["stream"].get("index"): t for t in a["audios"]}
    sys_t = by_index.get(order[0]) if len(order) >= 1 else None
    mic_t = by_index.get(order[1]) if len(order) >= 2 else None
    return sys_t, mic_t


def append_file(dst, src):
    with open(src, "rb") as fi:
        shutil.copyfileobj(fi, dst, COPY_CHUNK)


def write_zeros(dst, nbytes):
    block = bytes(min(nbytes, COPY_CHUNK))
    while nbytes > 0:
        n = min(nbytes, len(block))
        dst.write(block[:n])
        nbytes -= n


def compensation_kind(mode, plan):
    """audio-ready.json 的 compensation：off；補償時各段延遲都相同＝constant，否則 variable（spec §3.2）。"""
    if mode == "off":
        return "off"
    return "constant" if len({x["delaySeconds"] for x in plan}) <= 1 else "variable"

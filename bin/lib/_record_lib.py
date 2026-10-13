#!/usr/bin/env python3
"""_record_lib.py — 錄製相關的共用純函式與小型 CLI（spec §3.15、§3.19、§4.32；design R3-D6）。

函式：
- merge_defaults(home, updates, timeout=5.0)：取 <home>/record.defaults.lock 後「讀 → 合併 → mkstemp → os.replace」。
- output_time(t, first_start, pauses, l_out=0.0)：錄製時鐘 → 成品時間（語意同 Swift Core outputTime）。
- paused_total(pauses)：已配對暫停長度和（沒配對的不計）。
- levels_intervals(levels, window, threshold_db, merge_gap, pad, total)：一維 levels → 有聲區間。
- clip_timestamps(rec_dir)：讀 tracks/manifest.json 與 tracks/record.meta.json，回成品時間的有聲區間。

CLI：
- python3 _record_lib.py clip <錄音目錄>：印 clip_timestamps 的 JSON（小數 3 位；退回整檔時 null），回 0；目錄不存在回 2。
- python3 _record_lib.py sync [off|reported|calibrated]：meeting sync 的實作。

呼叫端以 python3 "$BIN/lib/_record_lib.py" 執行；Python 端以 sys.path.insert(0, <bin>/lib) 匯入。
"""
import fcntl
import json
import math
import os
import sys
import tempfile
import time

DEFAULTS_FILE = "record.defaults.json"
DEFAULTS_LOCK = "record.defaults.lock"
SYNC_MODES = ("off", "reported", "calibrated")

VAD_THRESHOLD_DB = -60.0
VAD_PAD = 0.75
VAD_MERGE_GAP = 2.0
LEVEL_WINDOW = 0.5


# ── record.defaults.json（spec §3.15、§3.16、§3.19） ──────────────────────────

class DefaultsError(Exception):
    """record.defaults.json 無法合併寫入（不是 JSON 物件、取鎖逾時）。"""


def _acquire_lock(path, timeout):
    """阻塞取 flock(LOCK_EX)，最多等 timeout 秒；逾時丟 DefaultsError。回傳 fd。"""
    fd = os.open(path, os.O_CREAT | os.O_RDWR | getattr(os, "O_CLOEXEC", 0), 0o600)
    deadline = time.monotonic() + float(timeout)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except BlockingIOError:
            if time.monotonic() >= deadline:
                os.close(fd)
                raise DefaultsError(f"{DEFAULTS_LOCK} 被其他程序持有超過 {timeout:g} 秒，"
                                    f"放棄寫入 {DEFAULTS_FILE}") from None
            time.sleep(0.05)
        except BaseException:
            os.close(fd)
            raise


def read_defaults(home):
    """讀 <home>/record.defaults.json：缺檔回 {}；不是 JSON 物件丟 DefaultsError。"""
    path = os.path.join(home, DEFAULTS_FILE)
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except FileNotFoundError:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise DefaultsError(f"{DEFAULTS_FILE} 不是合法的 JSON，不覆寫：{e}") from None
    if not isinstance(data, dict):
        raise DefaultsError(f"{DEFAULTS_FILE} 不是 JSON 物件，不覆寫")
    return data


def merge_defaults(home, updates, timeout=5.0):
    """取 <home>/record.defaults.lock（阻塞，最多 timeout 秒）→ 讀（缺檔＝{}）→ 不是 JSON 物件就丟例外、不寫
    → 合併 updates（不認得的鍵保留）→ 同目錄 mkstemp＋os.replace。回傳合併後的內容。"""
    if not isinstance(updates, dict):
        raise TypeError("updates 必須是 dict")
    os.makedirs(home, exist_ok=True)
    fd = _acquire_lock(os.path.join(home, DEFAULTS_LOCK), timeout)
    try:
        data = read_defaults(home)
        data.update(updates)
        tmp_fd, tmp = tempfile.mkstemp(prefix=DEFAULTS_FILE + ".", suffix=".tmp", dir=home)
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp, os.path.join(home, DEFAULTS_FILE))
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise
        return data
    finally:
        os.close(fd)  # 關 fd 即釋放 flock


# ── 時間軸（spec §3.14、§4.32.1、§4.32.3） ────────────────────────────────────

def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


def pause_pairs(pauses):
    """pauseEvents → [(pause.t, resume.t 或 None)]；resume 只與緊接在前、還沒配對的 pause 配對。"""
    out, open_t = [], None
    for e in pauses or []:
        t = _num((e or {}).get("t"))
        if t is None:
            continue
        kind = e.get("kind")
        if kind == "pause":
            if open_t is None:
                open_t = t
        elif kind == "resume" and open_t is not None:
            out.append((open_t, t))
            open_t = None
    if open_t is not None:
        out.append((open_t, None))
    return out


def paused_total(pauses):
    """Σ（resume.t − 緊接在前的 pause.t）；沒配對的 pause 不計；小數 3 位。"""
    return round(sum(r - p for p, r in pause_pairs(pauses) if r is not None), 3)


def output_time(t, first_start, pauses, l_out=0.0):
    """錄製時鐘 t → 成品時間：t 落在暫停區間（pause.t ≤ t < 配對的 resume.t，或沒配對的 pause.t ≤ t）時以 pause.t 代替；
    再減 first_start 與「resume.t ≤ 代替後時刻」的已配對暫停長度；< 0 夾成 0；加上 l_out（S-C 預留，系統聲音在成品裡
    再晚 l_out 秒）；小數 3 位。l_out=0 時與 e2e_check.record_to_output 完全相同。"""
    pairs = pause_pairs(pauses)
    x = float(t)
    for p, r in pairs:
        if p <= x and (r is None or x < r):
            x = p
            break
    fs = float(first_start)
    x -= fs
    x -= sum(r - p for p, r in pairs if r is not None and r <= x + fs)
    return round(max(x, 0.0) + float(l_out), 3)


# ── 有聲區間（spec §4.32.2、design R3-D4 T4） ─────────────────────────────────

def _merge_pad(runs, merge_gap, pad, total):
    """runs（遞增）→ 間隔 < merge_gap 合併 → 前後補 pad、夾在 [0, total] → 重疊的再併成一段。"""
    merged = []
    for a, b in runs:
        if merged and a - merged[-1][1] < merge_gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        a, b = max(a - pad, 0.0), min(b + pad, float(total))
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def _voiced(v, threshold_db):
    v = _num(v)
    return v is not None and v > threshold_db


def levels_intervals(levels, window, threshold_db, merge_gap, pad, total):
    """levels 一維陣列，第 i 個元素是窗 [i × window, (i+1) × window) 的 dBFS 或 None（None 視為無聲）。
    有聲＝嚴格大於 threshold_db；相鄰有聲窗連成一段；段間間隔 < merge_gap 合併（= 不合併）；
    前後補 pad 並夾在 [0, total]。回 [[start, end], …]（遞增、不重疊）。"""
    window = float(window)
    runs, start = [], None
    for i, v in enumerate(levels or []):
        if _voiced(v, threshold_db):
            if start is None:
                start = i
        elif start is not None:
            runs.append((start * window, i * window))
            start = None
    if start is not None:
        runs.append((start * window, len(levels) * window))
    return _merge_pad(runs, float(merge_gap), float(pad), float(total))


def _env_float(name, default):
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        v = float(raw)
    except ValueError:
        v = math.nan
    if not math.isfinite(v):
        print(f"⚠ {name}={raw!r} 不是數字，改用預設 {default:g}", file=sys.stderr)
        return default
    return v


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _max_level(a, b):
    a, b = _num(a), _num(b)
    if a is None:
        return b
    if b is None:
        return a
    return max(a, b)


def clip_timestamps(rec_dir, threshold_db=None, pad=None, merge_gap=None):
    """讀 <rec_dir>/tracks/manifest.json 的 levels（索引 × windowSeconds＝錄製時鐘）與 record.meta.json 的 pauseEvents，
    回成品時間的有聲區間 [[start, end], …]（小數 3 位）。

    做法：同一窗兩路取 max（None 視為無聲）→ 錄製時鐘上的有聲段（不合併、不補）→ 各端點以 output_time 換成成品時間
    → 在成品時間軸上依 merge_gap 合併、補 pad、夾在 [0, 成品全長]。門檻、補、合併間隔預設讀 MH_VAD_THRESHOLD_DB、
    MH_VAD_PAD、MH_VAD_MERGE_GAP（缺值 -60、0.75、2.0）。

    缺 manifest.json、沒有 levels → None；有 levels 但全場沒有有聲區間 → []（呼叫端一律退回整檔）。"""
    if threshold_db is None:
        threshold_db = _env_float("MH_VAD_THRESHOLD_DB", VAD_THRESHOLD_DB)
    if pad is None:
        pad = _env_float("MH_VAD_PAD", VAD_PAD)
    if merge_gap is None:
        merge_gap = _env_float("MH_VAD_MERGE_GAP", VAD_MERGE_GAP)
    tracks = os.path.join(rec_dir, "tracks")
    manifest = _read_json(os.path.join(tracks, "manifest.json"))
    if not isinstance(manifest, dict):
        return None
    lv = manifest.get("levels")
    if not isinstance(lv, dict):
        return None
    sysl = lv.get("system") if isinstance(lv.get("system"), list) else []
    mic = lv.get("mic") if isinstance(lv.get("mic"), list) else []
    if not sysl and not mic:
        return None
    window = _num(lv.get("windowSeconds")) or LEVEL_WINDOW
    if window <= 0:
        return None
    n = max(len(sysl), len(mic))
    combined = [_max_level(sysl[i] if i < len(sysl) else None, mic[i] if i < len(mic) else None) for i in range(n)]

    meta = _read_json(os.path.join(tracks, "record.meta.json"))
    pauses = (meta.get("pauseEvents") if isinstance(meta, dict) else None) or []
    segs = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    starts = [x for x in (_num(s.get("startedAt")) for s in segs) if x is not None]
    ends = [x for x in (_num(s.get("finishedAt")) for s in segs) if x is not None]
    first = min(starts) if starts else 0.0
    record_end = max(ends) if ends else n * window
    total = output_time(record_end, first, pauses)

    raw = levels_intervals(combined, window, threshold_db, 0.0, 0.0, n * window)
    runs = []
    for a, b in raw:
        oa, ob = output_time(a, first, pauses), output_time(b, first, pauses)
        if ob > oa:
            if runs and oa <= runs[-1][1]:
                runs[-1][1] = max(runs[-1][1], ob)
            else:
                runs.append([oa, ob])
    return [[round(a, 3), round(b, 3)] for a, b in _merge_pad(runs, merge_gap, pad, total)]


# ── CLI ───────────────────────────────────────────────────────────────────────

def _record_home():
    return os.environ.get("MH_RECORD_HOME") or os.path.expanduser("~/.meeting-harness")


def cmd_clip(args):
    if len(args) != 1:
        print("用法：_record_lib.py clip <錄音目錄>", file=sys.stderr)
        return 2
    rec = args[0]
    if not os.path.isdir(rec):
        print(f"✗ 錄音目錄不存在：{rec}", file=sys.stderr)
        return 2
    r = clip_timestamps(rec)
    if not r:
        # 退回整檔：stdout 印 null；原因寫 stderr 供呼叫端寫 raw 標頭的 VAD 行
        print("沒有 levels" if r is None else "沒有有聲區間", file=sys.stderr)
        print("null")
        return 0
    print(json.dumps(r))
    return 0


def cmd_sync(args):
    home = _record_home()
    if len(args) > 1 or (args and args[0] not in SYNC_MODES):
        print(f"用法：meeting sync [{'|'.join(SYNC_MODES)}]", file=sys.stderr)
        return 2
    if not args:
        try:
            mode = read_defaults(home).get("syncCompensation")
        except DefaultsError as e:
            print(f"⚠ {e}；以 off 顯示", file=sys.stderr)
            mode = None
        if mode not in SYNC_MODES:
            mode = "off"
        print(f"syncCompensation={mode}")
        return 0
    mode = args[0]
    try:
        merge_defaults(home, {"syncCompensation": mode})
    except (DefaultsError, OSError) as e:
        print(f"✗ 寫不進 {DEFAULTS_FILE}：{e}", file=sys.stderr)
        return 2
    print(f"syncCompensation={mode}（下一次收尾起生效）")
    return 0


def main(argv):
    cmds = {"clip": cmd_clip, "sync": cmd_sync}
    if not argv or argv[0] not in cmds:
        print("用法：_record_lib.py clip <錄音目錄> | sync [off|reported|calibrated]", file=sys.stderr)
        return 2
    return cmds[argv[0]](argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

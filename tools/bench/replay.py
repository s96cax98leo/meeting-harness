#!/usr/bin/env python3
"""重放量測工具（meeting-speed spec §3.12、§4.11.9、§4.14；Story G1、G4）。

用法：replay.py <段落目錄> [--speed N] [--no-worker] [--compare-full] [--legacy] [--keep-sandbox]

<段落目錄> 是錄製器保留下來的 錄音/tracks/ 形狀：seg-*.mov、manifest.json、record.meta.json。
本工具只讀它，不改它；所有寫入都在暫存區的沙盒裡：
1. 建沙盒場次（名稱「[Stand-up] 範例專案」）與沙盒 MH_RECORD_HOME（寫 record.status.json 模擬錄製器的 phase）。
2. 依各段 startedAt／finishedAt 的間隔除以 N，依序把段落放進沙盒的 錄音/tracks/ 並更新 manifest.json；
   第一段放完時照錄製器的規則起增量轉錄 worker（bin/lib/_asr_worker.py 存在、config 沒關、沒給 --no-worker）。
3. 最後一段放完算「停止」，起 bin/_record_finalize.py <沙盒場次>。
4. 認到「音訊就緒：」就起 bin/meeting.sh prep <沙盒場次>（環境只多 MH_PREP_RUN_ID）；
   --legacy 或收尾沒印這一行時，等收尾結束才起。
5. stdout 印一份 JSON 報告（鍵見 spec §3.12；秒數取小數 1 位；不含任何路徑、場次名、視窗標題）。
   --compare-full 另以整檔轉錄為參照，比對增量結果的 cer、timeAlignedRatio（spec §4.11.9）。

harness 根＝本檔的上兩層（tools/bench/ 的上兩層）。子程序的 python 用執行本工具的直譯器。
結束碼：0 完成、2 參數錯、5 管線失敗（收尾或前處理結束碼不是 0、比對無法完成）。
"""
import argparse
import difflib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid

HARNESS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIN = os.path.join(HARNESS, "bin")
SANDBOX_SESSION = "[Stand-up] 範例專案"
AUDIO_READY_PREFIX = "音訊就緒："
VIDEO_READY_PREFIX = "成品就緒："
POLL = 0.05
ALIGN_TOLERANCE = 1.0
# 不從來源目錄複製進沙盒的檔：段落與 manifest 由排程放入；收尾產物不得帶進來（否則收尾會以為已完成）
SKIP_COPY = {"manifest.json", "finalize.json", "audio-ready.json"}


class UsageError(Exception):
    pass


# ---------- 品質比對（spec §4.11.9） ----------

def _chars(segments):
    """把段落攤成 (字, 時刻) 序列：去掉標點、空白與控制字元；段內的字均分在 [start, end]，取每字的中點。"""
    out = []
    for seg in segments or []:
        text = "".join(c for c in str(seg.get("text") or "").lower()
                       if not unicodedata.category(c).startswith(("P", "Z", "C")) and not c.isspace())
        if not text:
            continue
        try:
            start, end = float(seg.get("start") or 0.0), float(seg.get("end") or 0.0)
        except (TypeError, ValueError):
            start = end = 0.0
        end = max(end, start)
        step = (end - start) / len(text)
        out.extend((c, start + (i + 0.5) * step) for i, c in enumerate(text))
    return out


def _levenshtein_pairs(a, b):
    """a、b 的最小編輯距離與對齊對（相同或替換的位置對）。只用在 difflib 的 replace 區塊（通常很小）。"""
    la, lb = len(a), len(b)
    if la * lb > 4_000_000:  # 區塊太大時不做 DP：依位置配對，編輯數取上界
        return max(la, lb), list(zip(range(la), range(lb)))
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
    pairs, i, j = [], la, lb
    while i > 0 and j > 0:
        if d[i][j] == d[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    return d[la][lb], pairs


def compare_metrics(full_segments, incremental_segments):
    """以整檔轉錄為參照比對增量結果（spec §4.11.9）。

    - cer：去標點後逐字的編輯距離 ÷ 參照字數。對齊先用 difflib（autojunk 關）切出相同區塊，不同的區塊內再做
      精確的 Levenshtein；2 小時逐字稿也算得完，結果是精確編輯距離的上界（只會高估、不會低估）。
    - timeAlignedRatio：對齊的字對（相同或替換）中，兩邊時刻差 ≤ 1.0 秒的比例；字的時刻＝所在段落均分後的中點。
    回 {"cer": float, "timeAlignedRatio": float}。
    """
    ref, hyp = _chars(full_segments), _chars(incremental_segments)
    rs, hs = [c for c, _ in ref], [c for c, _ in hyp]
    edits, pairs = 0, []
    sm = difflib.SequenceMatcher(None, rs, hs, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            pairs.extend(zip(range(i1, i2), range(j1, j2)))
        elif tag == "delete":
            edits += i2 - i1
        elif tag == "insert":
            edits += j2 - j1
        else:
            n, sub = _levenshtein_pairs(rs[i1:i2], hs[j1:j2])
            edits += n
            pairs.extend((i1 + a, j1 + b) for a, b in sub)
    cer = edits / len(rs) if rs else (0.0 if not hs else 1.0)
    within = sum(1 for i, j in pairs if abs(ref[i][1] - hyp[j][1]) <= ALIGN_TOLERANCE)
    ratio = within / len(pairs) if pairs else (1.0 if not rs and not hs else 0.0)
    return {"cer": cer, "timeAlignedRatio": ratio}


# ---------- 沙盒與排程 ----------

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path, obj):
    tmp = f"{path}.tmp-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def read_source(src):
    """讀來源段落目錄；回 (manifest, rows)。rows 依 manifest 順序、每列帶 _offset（相對第一段開始的秒數）。"""
    if not os.path.isdir(src):
        raise UsageError("段落目錄不存在")
    try:
        man = load_json(os.path.join(src, "manifest.json"))
    except (OSError, ValueError):
        raise UsageError("段落目錄沒有可讀的 manifest.json")
    rows = [r for r in (man.get("segments") or []) if isinstance(r, dict) and r.get("file")]
    if not rows:
        raise UsageError("manifest.json 沒有段落")
    for r in rows:
        if os.path.basename(r["file"]) != r["file"] or not os.path.isfile(os.path.join(src, r["file"])):
            raise UsageError(f"manifest 列的段落檔不存在：第 {rows.index(r) + 1} 段")
    interval = float(man.get("segmentSeconds") or 60.0)

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    t0 = num(rows[0].get("startedAt"))
    t0 = 0.0 if t0 is None else t0
    prev = t0
    for i, r in enumerate(rows):
        fin = num(r.get("finishedAt"))
        if fin is None:
            st = num(r.get("startedAt"))
            fin = (st if st is not None else prev) + interval
        r["_offset"] = max(fin - t0, prev - t0)
        prev = t0 + r["_offset"]
    return man, rows


def recorded_seconds(rows):
    return rows[-1]["_offset"]


class Sandbox:
    def __init__(self, keep):
        self.dir = tempfile.mkdtemp(prefix="mh-replay-")
        self.keep = keep
        self.home = os.path.join(self.dir, "home")
        self.session = os.path.join(self.dir, "root", SANDBOX_SESSION)
        self.rec = os.path.join(self.session, "錄音")
        self.tracks = os.path.join(self.rec, "tracks")
        self.logs = os.path.join(self.dir, "logs")
        for d in (self.home, self.tracks, self.logs):
            os.makedirs(d, exist_ok=True)
        self.run_id = str(uuid.uuid4()).upper()
        self.started_at = now_iso()

    def status(self, phase, segments):
        """模擬錄製器的 record.status.json（RecordStatus 的必備鍵；droppedFrames 0）。"""
        write_json_atomic(os.path.join(self.home, "record.status.json"), {
            "schemaVersion": 1, "runId": self.run_id, "pid": os.getpid(), "phase": phase, "code": 0, "message": "",
            "session": self.session, "startedAt": self.started_at, "updatedAt": now_iso(), "segments": segments,
            "preflight": [], "warnings": [], "controlVersion": 1, "droppedFrames": 0})

    def cleanup(self):
        if self.keep:
            print(f"[replay] 沙盒保留在：{self.dir}", file=sys.stderr)
        else:
            shutil.rmtree(self.dir, ignore_errors=True)


def copy_side_files(src, sb):
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if name in SKIP_COPY or (name.startswith("seg-") and name.endswith(".mov")) or not os.path.isfile(p):
            continue
        shutil.copy2(p, os.path.join(sb.tracks, name))


def place_segment(src, sb, row):
    tmp = os.path.join(sb.tracks, f".{row['file']}.part")
    shutil.copyfile(os.path.join(src, row["file"]), tmp)
    os.replace(tmp, os.path.join(sb.tracks, row["file"]))


def manifest_with(man, rows):
    out = {k: v for k, v in man.items() if k != "segments"}
    out["segments"] = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows]
    return out


def worker_script():
    return os.path.join(BIN, "lib", "_asr_worker.py")


def incremental_enabled():
    try:
        cfg = load_json(os.path.join(HARNESS, "config.json"))
        return ((cfg.get("transcribe") or {}).get("incremental") or {}).get("enabled") is not False
    except (OSError, ValueError, AttributeError):
        return True


def child_env(sb, **extra):
    env = dict(os.environ)
    for k in ("MH_PREP_EARLY", "MH_PREP_RUN_ID", "MH_ASR_SEGMENTS_JSON"):
        env.pop(k, None)
    env["MH_RECORD_HOME"] = sb.home
    env["PATH"] = f"{os.path.dirname(sys.executable)}:{env.get('PATH', '')}"
    env.update(extra)
    return env


def start_worker(sb):
    asr = os.path.join(sb.tracks, "asr")
    os.makedirs(asr, exist_ok=True)
    log = open(os.path.join(asr, "worker.log"), "ab")
    argv = [sys.executable, worker_script(), "run", sb.session]
    if os.path.exists("/usr/bin/nice"):
        argv = ["/usr/bin/nice", "-n", "10"] + argv
    try:
        return subprocess.Popen(argv, env=child_env(sb), stdout=log, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL)
    finally:
        log.close()


def worker_backlog(sb, finished):
    """停止當下欠的窗數＝已收尾段數 − state.json 已完成的窗數（還沒有 state.json 時＝已收尾段數）。"""
    try:
        windows = load_json(os.path.join(sb.tracks, "asr", "state.json")).get("windows") or []
    except (OSError, ValueError, AttributeError):
        windows = []
    return max(finished - len(windows), 0)


def first_level_wav(rec):
    try:
        return any(n.lower().endswith(".wav") and os.path.isfile(os.path.join(rec, n)) for n in os.listdir(rec))
    except OSError:
        return False


class LineWatcher(threading.Thread):
    """讀收尾的 stdout，記下「音訊就緒：」「成品就緒：」第一次出現的時刻；原文寫進沙盒 log。"""

    def __init__(self, stream, log_path):
        super().__init__(daemon=True)
        self.stream, self.log_path = stream, log_path
        self.audio_ready = self.video_ready = None

    def run(self):
        with open(self.log_path, "w", encoding="utf-8") as log:
            for line in self.stream:
                t = time.time()
                log.write(line)
                log.flush()
                s = line.lstrip()
                if self.audio_ready is None and s.startswith(AUDIO_READY_PREFIX):
                    self.audio_ready = t
                elif self.video_ready is None and s.startswith(VIDEO_READY_PREFIX):
                    self.video_ready = t


def start_prep(sb):
    out = open(os.path.join(sb.logs, "prep.log"), "ab")
    try:
        return subprocess.Popen(["bash", os.path.join(BIN, "meeting.sh"), "prep", sb.session],
                                env=child_env(sb, MH_PREP_RUN_ID=str(uuid.uuid4()).upper()),
                                stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    finally:
        out.close()


def sec(stop, t):
    return None if t is None else round(max(t - stop, 0.0), 1)


# ---------- 比對模式 ----------

def full_reference(sb):
    """以整檔轉錄（不帶 MH_ASR_SEGMENTS_JSON）重轉沙盒的正式 wav，回 segments；失敗回 None。"""
    wavs = sorted(n for n in os.listdir(sb.rec) if n.lower().endswith(".wav"))
    if not wavs:
        return None
    out_dir = os.path.join(sb.dir, "full")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(sb.logs, "full-transcribe.log"), "ab") as log:
        r = subprocess.run(["bash", os.path.join(BIN, "transcribe.sh"), os.path.join(sb.rec, wavs[0]),
                            os.path.join(out_dir, "transcript.raw.md"), os.environ.get("MH_LANG", "zh")],
                           env=child_env(sb, MH_EMIT_SEGMENTS="1"), stdout=log, stderr=subprocess.STDOUT)
    try:
        return load_json(os.path.join(out_dir, "transcript.segments.json")).get("segments") if r.returncode == 0 else None
    except (OSError, ValueError, AttributeError):
        return None


def incremental_result(sb):
    if not os.path.isfile(worker_script()):
        return None
    out = os.path.join(sb.dir, "incremental.json")
    with open(os.path.join(sb.logs, "stitch.log"), "ab") as log:
        r = subprocess.run([sys.executable, worker_script(), "stitch", sb.session, out], env=child_env(sb),
                           stdout=log, stderr=subprocess.STDOUT)
    try:
        return load_json(out).get("segments") if r.returncode == 0 else None
    except (OSError, ValueError, AttributeError):
        return None


# ---------- 主流程 ----------

def parse_args(argv):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            self.print_usage(sys.stderr)
            print(f"replay.py: 參數錯：{message}", file=sys.stderr)
            sys.exit(2)

    p = Parser(prog="replay.py", description="重放保留的錄製段落，量測停止後各成品就緒的時間（報告不含路徑與場次名）。")
    p.add_argument("segments_dir", help="錄製器保留的段落目錄（錄音/tracks/ 形狀：seg-*.mov、manifest.json）")
    p.add_argument("--speed", type=float, default=1.0, help="重放倍速 N：段落間隔除以 N（預設 1）")
    p.add_argument("--no-worker", action="store_true", help="不起增量轉錄 worker")
    p.add_argument("--compare-full", action="store_true", help="另以整檔轉錄為參照，算 cer、timeAlignedRatio")
    p.add_argument("--legacy", action="store_true", help="等收尾結束才起前處理（不看「音訊就緒：」）")
    p.add_argument("--keep-sandbox", action="store_true", help="結束後保留沙盒（路徑印在 stderr，報告裡沒有）")
    a = p.parse_args(argv)
    if not a.speed > 0:
        p.error("--speed 必須大於 0")
    return a


def replay(a):
    src = os.path.abspath(a.segments_dir)
    man, rows = read_source(src)
    sb = Sandbox(a.keep_sandbox)
    procs = []
    try:
        return _replay(a, src, man, rows, sb, procs)
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        sb.cleanup()


def _replay(a, src, man, rows, sb, procs):
    copy_side_files(src, sb)
    write_json_atomic(os.path.join(sb.tracks, "manifest.json"), manifest_with(man, []))
    sb.status("recording", 0)
    use_worker = not a.no_worker and os.path.isfile(worker_script()) and incremental_enabled()
    worker = None
    begin = time.time()
    for i, row in enumerate(rows):
        delay = begin + row["_offset"] / a.speed - time.time()
        if delay > 0:
            time.sleep(delay)
        place_segment(src, sb, row)
        write_json_atomic(os.path.join(sb.tracks, "manifest.json"), manifest_with(man, rows[:i + 1]))
        sb.status("recording", i + 1)
        if use_worker and worker is None:
            worker = start_worker(sb)
            procs.append(worker)

    stop = time.time()
    backlog = worker_backlog(sb, len(rows)) if worker is not None else None
    sb.status("stopping", len(rows))
    fin_err = open(os.path.join(sb.logs, "finalize.stderr.log"), "wb")
    fin = subprocess.Popen([sys.executable, os.path.join(BIN, "_record_finalize.py"), sb.session], env=child_env(sb),
                           stdout=subprocess.PIPE, stderr=fin_err, stdin=subprocess.DEVNULL, text=True,
                           encoding="utf-8", errors="replace")
    fin_err.close()
    procs.append(fin)
    sb.status("finalizing", len(rows))
    watcher = LineWatcher(fin.stdout, os.path.join(sb.logs, "finalize.stdout.log"))
    watcher.start()

    speakers_md = os.path.join(sb.rec, "transcript.speakers.md")
    prep = None
    t_wav = t_md = t_fin_end = t_prep_end = None
    fin_rc = prep_rc = None
    flow = "legacy" if a.legacy else "early"
    while True:
        now = time.time()
        if t_wav is None and first_level_wav(sb.rec):
            t_wav = now
        if t_md is None and os.path.isfile(speakers_md):
            t_md = now
        if fin_rc is None and fin.poll() is not None:
            watcher.join(timeout=5)
            fin_rc, t_fin_end = fin.returncode, time.time()
            sb.status("done" if fin_rc == 0 else "failed", len(rows))
        if prep is None:
            if not a.legacy and watcher.audio_ready is not None:
                prep = start_prep(sb)
            elif fin_rc is not None:
                if watcher.audio_ready is None:
                    flow = "legacy"
                if fin_rc == 0:
                    prep = start_prep(sb)
            if prep is not None:
                procs.append(prep)
        if prep is not None and prep_rc is None and prep.poll() is not None:
            prep_rc, t_prep_end = prep.returncode, time.time()
        if fin_rc is not None and (prep_rc is not None or (prep is None and fin_rc != 0)):
            break
        time.sleep(POLL)
    now = time.time()
    if t_wav is None and first_level_wav(sb.rec):
        t_wav = now
    if t_md is None and os.path.isfile(speakers_md):
        t_md = now

    if worker is not None and worker.poll() is None:
        try:
            worker.wait(timeout=600 if a.compare_full else 30)
        except subprocess.TimeoutExpired:
            pass

    try:
        video_path = load_json(os.path.join(sb.tracks, "finalize.json")).get("videoPath")
    except (OSError, ValueError, AttributeError):
        video_path = None
    t_video = watcher.video_ready
    if t_video is None and fin_rc == 0:
        vids = os.path.join(sb.session, "影片")
        if os.path.isdir(vids) and any(n.lower().endswith(".mov") for n in os.listdir(vids)):
            t_video = t_fin_end
    ends = [t for t in (t_fin_end, t_prep_end) if t is not None]
    report = {
        "speed": int(a.speed) if float(a.speed).is_integer() else a.speed,
        "segments": len(rows),
        "recordedSeconds": round(recorded_seconds(rows), 1),
        "stopToAudioReady": sec(stop, watcher.audio_ready),
        "stopToSpeakersMd": sec(stop, t_md),
        "stopToWav": sec(stop, t_wav),
        "stopToVideo": sec(stop, t_video),
        "stopToAllReady": sec(stop, max(ends)) if ends else None,
        "verifySeconds": sec(watcher.video_ready, t_fin_end) if watcher.video_ready and t_fin_end else None,
        "workerBacklogAtStop": backlog,
        "videoPath": video_path if video_path in ("copy", "reencode") else None,
        "flow": flow,
    }
    rc = 0 if fin_rc == 0 and prep_rc == 0 else 5
    if fin_rc != 0:
        print(f"[replay] 收尾結束碼 {fin_rc}", file=sys.stderr)
    elif prep_rc != 0:
        print(f"[replay] 前處理結束碼 {prep_rc}", file=sys.stderr)

    if a.compare_full:
        report["cer"] = report["timeAlignedRatio"] = None
        inc = incremental_result(sb)
        ref = full_reference(sb) if inc is not None else None
        if inc is None or ref is None:
            print("[replay] 比對無法完成：" + ("沒有可用的增量結果" if inc is None else "整檔轉錄失敗"), file=sys.stderr)
            rc = 5
        else:
            m = compare_metrics(ref, inc)
            report["cer"] = round(m["cer"], 4)
            report["timeAlignedRatio"] = round(m["timeAlignedRatio"], 4)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return rc


def main(argv=None):
    a = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return replay(a)
    except UsageError as e:
        print(f"replay.py: 參數錯：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

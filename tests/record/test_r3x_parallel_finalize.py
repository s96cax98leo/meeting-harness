"""R3x B：收尾平行化（spec R3x §3.25、§4.55；§6 第 152、153、156 條）。

純函式以檔案路徑載入 bin/_record_finalize.py（MH_RECORD_HOME 指向暫存 home）；§3.25 的名稱不存在時以 assert 判 FAIL
（不得 ImportError）。實際收尾以 python3 bin/_record_finalize.py <場次> 執行，素材只在 TMPDIR；需要量平行度時
MH_FFMPEG 指向 fakes/parallel_ffmpeg.py（§3.27），由它的事件紀錄（PAR_FFMPEG_LOG）算「同時在跑的正規化編碼數」。
"""
import ast
import contextlib
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from tests.record import _media as m
from tests.record._helpers import FAKES, Sandbox, dead_pid, snapshot, tmpdir
from tests.record.test_r3_finalize_guard import (FINALIZE_PY, HOLD_FINALIZE_LOCK, finalize_json, load_finalize_module,
                                                 procs_mentioning)
from tests.record.test_r3_lock import sleeper

PAR_FFMPEG = FAKES / "parallel_ffmpeg.py"
SIX = [dict(dur=2.0)] * 6
ENCODE_KINDS = ("vt", "x264")
AUDIO_EXTS = {".wav", ".m4a", ".mp3", ".aac", ".flac", ".caf"}
PROGRESS_RE = re.compile(r"^正規化 已完成 (\d+)/(\d+)$")
CLEAN_ENV = ("MH_FINALIZE_JOBS", "MH_FINALIZE_WAIT_LOCK", "MH_FINALIZE_STEP_TIMEOUT", "MH_FFMPEG", "MH_FFPROBE",
             "MH_SYNC_COMPENSATION", "MH_KEEP_SEGMENTS", "PAR_FFMPEG_LOG", "PAR_FFMPEG_SECONDS", "PAR_FFMPEG_FAIL_SEGS",
             "PAR_FFMPEG_FAIL_VT", "PAR_FFMPEG_REAL")


def need(tc, mod, *names):
    missing = [n for n in names if not hasattr(mod, n)]
    tc.assertEqual(missing, [], f"bin/_record_finalize.py 缺少 spec §3.25 的名稱：{missing}")


def load(tc):
    return load_finalize_module(tc, tmpdir(tc))


def reset_state(mod):
    """spec §4.55.18：每個案例前後重設模組狀態（只在測試中這樣做）。"""
    if hasattr(mod, "_ABORT_DISPATCH"):
        mod._ABORT_DISPATCH.clear()
    if hasattr(mod, "_ABORT_FROM"):
        mod._ABORT_FROM = None


def fin_env(sb, **over):
    """收尾用的環境：先拿掉會影響結果的變數，再套 over。"""
    e = sb.env()
    for k in CLEAN_ENV:
        e.pop(k, None)
    e.update({k: str(v) for k, v in over.items()})
    return e


def par_env(sb, log, seconds=1, **over):
    return fin_env(sb, MH_FFMPEG=PAR_FFMPEG, PAR_FFMPEG_LOG=log, PAR_FFMPEG_SECONDS=seconds, **over)


def run_fin(tc, sess, env, timeout=300):
    """python3 _record_finalize.py <場次>（新的 process group）；逾時就整組 SIGKILL 並判 FAIL。回 (CompletedProcess, 耗時)。"""
    p = subprocess.Popen([sys.executable, "-B", str(FINALIZE_PY), str(sess)], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    t0 = time.monotonic()
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        tc.fail(f"收尾 {timeout} 秒內沒有結束\nstdout:{out}\nstderr:{err}")
    return subprocess.CompletedProcess(p.args, p.returncode, out, err), time.monotonic() - t0


def copy_session(sess, root):
    dst = Path(root) / m.DAY / sess.name
    shutil.copytree(sess, dst)
    return dst


def read_events(path):
    """parallel_ffmpeg.py 的事件紀錄 → [{ev, pid, kind, seg, t, rc}]。"""
    out = []
    p = Path(path)
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        f = ln.split()
        if len(f) >= 5 and f[0] in ("start", "end"):
            out.append({"ev": f[0], "pid": int(f[1]), "kind": f[2], "seg": f[3], "t": float(f[4]),
                        "rc": int(f[5]) if f[0] == "end" and len(f) > 5 else None})
    return out


def intervals(events, kinds=None):
    """依 pid 把 start／end 配成區間：[{kind, seg, start, end（沒有 end＝None）, rc}]。"""
    open_, out = {}, []
    for e in events:
        if kinds is not None and e["kind"] not in kinds:
            continue
        if e["ev"] == "start":
            iv = {"kind": e["kind"], "seg": e["seg"], "start": e["t"], "end": None, "rc": None}
            open_.setdefault(e["pid"], []).append(iv)
            out.append(iv)
        elif open_.get(e["pid"]):
            iv = open_[e["pid"]].pop(0)
            iv["end"], iv["rc"] = e["t"], e["rc"]
    return out


def max_concurrency(ivs):
    pts = []
    for iv in ivs:
        pts.append((iv["start"], 1))
        pts.append((iv["end"] if iv["end"] is not None else float("inf"), -1))
    cur = best = 0
    for _, d in sorted(pts, key=lambda x: (x[0], x[1])):
        cur += d
        best = max(best, cur)
    return best


def audio_files_top(sess):
    rec = sess / "錄音"
    return sorted(p.name for p in rec.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS)


def seg_names(sess):
    return sorted(p.name for p in (sess / "錄音" / "tracks").glob("seg-*.mov"))


def top_defs(tree):
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def call_names(node):
    out = []
    for c in ast.walk(node):
        if isinstance(c, ast.Call):
            f = c.func
            out.append(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None)
    return out


def type_names(node):
    if node is None:
        return []
    if isinstance(node, ast.Tuple):
        return [n for e in node.elts for n in type_names(e)]
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [node.attr]
    return []


class ParallelCase(unittest.TestCase):
    def require_videotoolbox(self):
        ok, why = m.videotoolbox_h264_available()
        if not ok:
            self.skipTest(f"平行度以 h264_videotoolbox 量（退回 libx264 時依 §3.25 一律 1）：{why}")

    def base_session(self, segs=SIX):
        sb = Sandbox(self)
        return sb, m.make_record_session(sb.root, segs)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"收尾應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")


class TestR3xParallelFinalize(ParallelCase):
    # ---------- 純函式 ----------

    # spec §4.55.1、§3.25：finalize_jobs 的值與常數
    def test_finalize_jobs_values(self):
        mod = load(self)
        need(self, mod, "finalize_jobs", "FINALIZE_JOBS_DEFAULT", "FINALIZE_JOBS_MAX", "FINALIZE_JOBS_RECORDING")
        self.assertEqual((mod.FINALIZE_JOBS_DEFAULT, mod.FINALIZE_JOBS_MAX, mod.FINALIZE_JOBS_RECORDING), (3, 3, 2))
        cases = [((None,), {}, 3), (("",), {}, 3), (("1",), {}, 1), (("2",), {}, 2), (("3",), {}, 3),
                 ((" 2 ",), {}, 2), (("9",), {}, 3), (("0",), {}, 3), (("-1",), {}, 3), (("abc",), {}, 3),
                 (("2.5",), {}, 3), (("3",), {"recording": True}, 2), (("1",), {"recording": True}, 1),
                 (("3",), {"fallback": True}, 1), (("2",), {"recording": True, "fallback": True}, 1)]
        for args, kw, want in cases:
            with self.subTest(raw=args[0], **kw):
                self.assertEqual(mod.finalize_jobs(*args, **kw), want)

    # spec §4.55.2、design R3x-D9：recording_in_progress 只讀不寫
    def test_recording_in_progress(self):
        mod = load(self)
        need(self, mod, "recording_in_progress")
        home = tmpdir(self)
        sl = sleeper(self)
        dp = dead_pid()
        cases = [("活著、pid 相同、phase recording", str(sl), {"runId": "r", "pid": sl, "phase": "recording"}, True),
                 ("phase finalizing", str(sl), {"runId": "r", "pid": sl, "phase": "finalizing"}, False),
                 ("pid 不相同", str(sl), {"runId": "r", "pid": dp, "phase": "recording"}, False),
                 ("pid 已死", str(dp), {"runId": "r", "pid": dp, "phase": "recording"}, False),
                 ("沒有 record.pid", None, {"runId": "r", "pid": sl, "phase": "recording"}, False),
                 ("壞 JSON", str(sl), "{壞檔", False)]
        for label, pid_text, st, want in cases:
            with self.subTest(case=label):
                for f in list(home.iterdir()):
                    f.unlink()
                if pid_text is not None:
                    (home / "record.pid").write_text(pid_text + "\n")
                (home / "record.status.json").write_text(st if isinstance(st, str) else json.dumps(st),
                                                         encoding="utf-8")
                before = snapshot(home)
                self.assertIs(mod.recording_in_progress(str(home)), want)
                self.assertEqual(snapshot(home), before, "呼叫前後 home 內所有檔的 mtime 與內容不變、沒有新檔")

    # spec §4.55.3：normalize_deps
    def test_normalize_deps(self):
        mod = load(self)
        need(self, mod, "normalize_deps")
        for has_video, want in (([True, True], [None, None]), ([True, False, False, True], [None, 0, 1, None]),
                                ([False, True], [None, None]), ([], [])):
            with self.subTest(has_video=has_video):
                self.assertEqual(list(mod.normalize_deps(has_video)), want)

    # ---------- run_ordered（§4.55.18；純 Python，不經 ffmpeg） ----------

    def ordered_module(self):
        mod = load(self)
        need(self, mod, "run_ordered", "FinalizeError", "SegmentAborted", "_ABORT_DISPATCH", "_ABORT_FROM", "_SEG_PROCS",
             "_ACTIVE", "_SEG")
        reset_state(mod)
        self.addCleanup(reset_state, mod)
        return mod

    # spec §4.55.18 (1)：嚴格依段號派工，第 k 段的依賴沒完成時第 k 段與之後的段都不派（不跳號）
    def test_run_ordered_strict_order(self):
        mod = self.ordered_module()
        starts, ends, lock = {}, {}, threading.Lock()

        def fn(i):
            with lock:
                starts[i] = time.monotonic()
            time.sleep(1.0 if i == 1 else 0.05)
            with lock:
                ends[i] = time.monotonic()
            return i * 10

        with contextlib.redirect_stdout(io.StringIO()):
            res = mod.run_ordered(6, fn, jobs=lambda: 3, deps=[None, None, 1, None, None, None])
        self.assertEqual(list(res), [0, 10, 20, 30, 40, 50], "回傳值應依索引排列")
        # 開始順序 0–5 遞增（同一批派出的段在不同執行緒起跑，容許 50 ms 的排程誤差）
        for i in range(5):
            self.assertLess(starts[i], starts[i + 1] + 0.05, f"第 {i + 1} 段（索引 {i + 1}）不得早於索引 {i} 開始：{starts}")
        for k in (2, 3, 4):
            self.assertGreaterEqual(starts[k], ends[1], f"索引 {k} 應等索引 1 結束才開始（索引 2 依賴 1，不跳號）")

    # spec §4.55.18 (2)：丟出的是索引最小的 FinalizeError
    def test_run_ordered_lowest_failure(self):
        mod = self.ordered_module()

        def fn(i):
            if i == 1:
                time.sleep(0.5)
                raise mod.FinalizeError("b")
            if i == 3:
                raise mod.FinalizeError("d")
            return i

        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(mod.FinalizeError) as cm:
                mod.run_ordered(6, fn, jobs=lambda: 4)
        self.assertEqual(str(cm.exception), "b", "應丟出索引最小（索引 1）的 FinalizeError")

    # spec §4.55.18 (3)：索引 2 失敗 → 索引 3 在跑的 run_step 被中止（SegmentAborted、子程序不在）；_SEG_PROCS、_ACTIVE 清空
    def test_run_ordered_aborts_higher(self):
        mod = self.ordered_module()
        need(self, mod, "run_step")
        got = {}
        marker = "29.7531"

        def fn(i):
            if i == 2:
                time.sleep(0.5)
                raise mod.FinalizeError("c")
            if i == 3:
                try:
                    mod.run_step(["sleep", marker], "normalize", "seg-0004")
                except mod.SegmentAborted:
                    got[3] = "aborted"
                    raise
                got[3] = "finished"
            return i

        t0 = time.monotonic()
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(mod.FinalizeError) as cm:
                mod.run_ordered(6, fn, jobs=lambda: 4)
        took = time.monotonic() - t0
        self.assertEqual(str(cm.exception), "c")
        self.assertLess(took, 3.0, f"應在 3 秒內丟出索引 2 的例外（耗時 {took:.1f} 秒）")
        self.assertEqual(got.get(3), "aborted", "索引 3 的 fn 應收到 SegmentAborted")
        left = [ln for ln in procs_mentioning(f"sleep {marker}")]
        self.assertEqual(left, [], "被中止的 sleep 子程序應已不在")
        self.assertEqual(dict(mod._SEG_PROCS), {}, "結束後 _SEG_PROCS 應為空")
        self.assertEqual(len(mod._ACTIVE), 0, "結束後 _ACTIVE 應為空")

    # spec §4.55.18 (4)：中止條件在 Popen 之前檢查（沒有啟動子程序）
    def test_run_ordered_checks_before_popen(self):
        mod = self.ordered_module()
        need(self, mod, "run_step")
        target = tmpdir(self) / "不該出現.txt"
        got = {}

        def fn(i):
            if i == 2:
                time.sleep(0.2)
                raise mod.FinalizeError("c")
            if i == 3:
                time.sleep(0.6)
                try:
                    mod.run_step(["touch", str(target)], "normalize", "seg-0004")
                except mod.SegmentAborted:
                    got[3] = "aborted"
                    raise
                got[3] = "finished"
            return i

        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(mod.FinalizeError):
                mod.run_ordered(6, fn, jobs=lambda: 4)
        self.assertEqual(got.get(3), "aborted", "索引 3 的 run_step 應丟 SegmentAborted")
        self.assertFalse(target.exists(), "中止條件成立時不得啟動子程序")

    # spec §4.55.18 (5)：jobs() 回 1 → 不建 thread pool，結果與依序呼叫相同
    def test_run_ordered_serial_no_pool(self):
        mod = self.ordered_module()
        base = threading.active_count()
        seen = []

        def fn(i):
            seen.append((i, threading.active_count(), threading.current_thread() is threading.main_thread(),
                         getattr(mod._SEG, "index", None)))
            return i * i

        with contextlib.redirect_stdout(io.StringIO()):
            res = mod.run_ordered(4, fn, jobs=lambda: 1)
        self.assertEqual(list(res), [0, 1, 4, 9])
        self.assertEqual([s[0] for s in seen], [0, 1, 2, 3], "應依序呼叫")
        self.assertTrue(all(s[1] == base for s in seen), f"不得建 thread pool（active_count 應維持 {base}）：{seen}")
        self.assertTrue(all(s[2] for s in seen), "應在主執行緒呼叫 fn")
        self.assertTrue(all(s[3] is None for s in seen), "串行路徑的 _SEG.index 應為 None")

    # ---------- 實際收尾（parallel_ffmpeg.py） ----------

    # spec §4.55.4：6 段、沒設 MH_FINALIZE_JOBS → 回 0、同時在跑的正規化編碼數最大值恰為 3、stdout 含「收尾平行度：3」
    def test_default_runs_three(self):
        self.require_videotoolbox()
        sb, sess = self.base_session()
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log))
        self.ok(r)
        self.assertEqual(max_concurrency(intervals(read_events(log), ENCODE_KINDS)), 3)
        self.assertIn("收尾平行度：3", r.stdout.splitlines())

    # spec §4.55.5：MH_FINALIZE_JOBS＝1／2／9／abc → 最大值 1／2／3／3，後兩者各有告警行；四者都回 0
    def test_jobs_env(self):
        self.require_videotoolbox()
        sb, sess = self.base_session()
        cases = (("1", 1, None), ("2", 2, None), ("9", 3, "⚠ MH_FINALIZE_JOBS=9 超過上限 3，改用 3"),
                 ("abc", 3, "⚠ MH_FINALIZE_JOBS=abc 不是正整數，改用預設 3"))
        for raw, want, warn in cases:
            with self.subTest(MH_FINALIZE_JOBS=raw):
                s = copy_session(sess, sb.base / f"jobs-{raw}")
                log = sb.base / f"par-{raw}.log"
                r, _ = run_fin(self, s, par_env(sb, log, MH_FINALIZE_JOBS=raw))
                self.ok(r)
                self.assertEqual(max_concurrency(intervals(read_events(log), ENCODE_KINDS)), want)
                lines = r.stdout.splitlines()
                self.assertIn(f"收尾平行度：{want}（MH_FINALIZE_JOBS={raw}）", lines)
                if warn:
                    self.assertIn(warn, lines)

    # spec §4.55.6、design R3x-D9：暫存 home 模擬錄製中 → 最大值 2，stdout 含「錄製中，收尾平行度降為 2」
    def test_recording_lowers_to_two(self):
        self.require_videotoolbox()
        sb, sess = self.base_session()
        sl = sleeper(self)
        (sb.home / "record.pid").write_text(f"{sl}\n")
        (sb.home / "record.status.json").write_text(json.dumps({"schemaVersion": 1, "runId": "run-b", "pid": sl,
                                                                "phase": "recording"}), encoding="utf-8")
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log, MH_RECORD_HOME=sb.home))
        self.ok(r)
        self.assertEqual(max_concurrency(intervals(read_events(log), ENCODE_KINDS)), 2)
        self.assertIn("錄製中，收尾平行度降為 2", r.stdout.splitlines())

    # spec §4.55.7：h264_videotoolbox 一律失敗 → 回 0、libx264 同時最多 1 個、stdout 含「改用 libx264，收尾平行度降為 1」
    def test_x264_fallback_serial(self):
        sb, sess = self.base_session()
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log, PAR_FFMPEG_FAIL_VT="1"))
        self.ok(r)
        x264 = intervals(read_events(log), ("x264",))
        self.assertTrue(x264, "前提：應改用 libx264 編碼")
        self.assertEqual(max_concurrency(x264), 1, "libx264 編碼同時最多 1 個")
        self.assertIn("改用 libx264，收尾平行度降為 1", r.stdout.splitlines())

    # spec §4.55.8、`pf` §4.2：第 3 段沒有影片 → still-0003 的 start 晚於 seg-0002 的 end
    def test_missing_video_waits_previous(self):
        sb, sess = self.base_session([dict(dur=2.0), dict(dur=2.0), dict(dur=2.0, video=None), dict(dur=2.0),
                                      dict(dur=2.0)])
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log))
        self.ok(r)
        evs = read_events(log)
        still = [e["t"] for e in evs if e["ev"] == "start" and e["kind"] == "still" and e["seg"] == "still-0003"]
        seg2_end = [iv["end"] for iv in intervals(evs, ENCODE_KINDS) if iv["seg"] == "seg-0002" and iv["rc"] == 0]
        self.assertTrue(still, "前提：第 3 段應取前一段最後一幀（still-0003）")
        self.assertTrue(seg2_end, "前提：seg-0002 應正規化成功")
        self.assertGreater(still[0], max(seg2_end), "第 3 段應等第 2 段的 norm-0002.mov 完成才取最後一幀")

    # spec §4.55.9：seg-0002、seg-0004 都失敗 → 回 5；stderr 含 seg-0002、不含 seg-0004；段落保留；錄音/ 沒有音源檔
    def test_reports_lowest_failed_segment(self):
        sb, sess = self.base_session()
        segs = seg_names(sess)
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log, PAR_FFMPEG_FAIL_SEGS="seg-0002,seg-0004"))
        self.assertEqual(r.returncode, 5, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("seg-0002", r.stderr)
        self.assertNotIn("seg-0004", r.stderr, "應只回報段號最小的失敗")
        self.assertEqual(seg_names(sess), segs, "tracks/seg-*.mov 應全部保留")
        self.assertEqual(audio_files_top(sess), [], "錄音/ 第一層不得有音源檔")

    # spec §4.55.10（修正輪 I2、N4）：seg-0003 失敗 → 不再派新段；被中止的段不改試 libx264；較小的段跑完
    def test_failure_stops_dispatch(self):
        self.require_videotoolbox()
        sb, sess = self.base_session()
        log = sb.base / "par.log"
        r, _ = run_fin(self, sess, par_env(sb, log, PAR_FFMPEG_FAIL_SEGS="seg-0003"))
        self.assertEqual(r.returncode, 5, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("seg-0003", r.stderr)
        ivs = intervals(read_events(log))
        by = lambda seg: [iv for iv in ivs if iv["seg"] == seg]  # noqa: E731
        for seg in ("seg-0005", "seg-0006"):
            self.assertEqual(by(seg), [], f"{seg} 不得有任何 start（失敗後不再派新段）")
        for iv in by("seg-0004"):
            if iv["kind"] == "vt":
                self.assertNotEqual(iv["rc"], 0, "seg-0004 若有 start vt，就不得有對應的 end … 0（應被中止）")
        self.assertFalse([iv for iv in by("seg-0004") if iv["kind"] == "x264"], "被中止的 seg-0004 不得改試 libx264")
        for seg in ("seg-0001", "seg-0002"):
            self.assertTrue([iv for iv in by(seg) if iv["rc"] == 0], f"{seg} 應跑完（end … 0）")
        self.assertEqual({iv["seg"] for iv in ivs if iv["kind"] == "x264"} - {"seg-0003"}, set(),
                         "x264 的 start 只可能出現在 seg-0003")

    # spec §4.55.12、§4.55.20：平行正規化中收到 SIGTERM → 10 秒內以 5 結束、3 秒內沒有殘留子程序、段落保留
    def test_sigterm_kills_all_groups(self):
        self.require_videotoolbox()
        sb, sess = self.base_session()
        segs = seg_names(sess)
        log = sb.base / "par.log"
        p = subprocess.Popen([sys.executable, "-B", str(FINALIZE_PY), str(sess)], env=par_env(sb, log, seconds=5),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)

        def cleanup():
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except OSError:
                    pass
            p.communicate()
        self.addCleanup(cleanup)
        deadline = time.monotonic() + 20
        running = 0
        while time.monotonic() < deadline and p.poll() is None:
            running = sum(1 for iv in intervals(read_events(log), ENCODE_KINDS) if iv["end"] is None)
            if running >= 2:
                break
            time.sleep(0.05)
        self.assertGreaterEqual(running, 2, "前提：替身應確認已有 2 個正規化編碼同時在跑（20 秒內沒有等到）")
        os.kill(p.pid, signal.SIGTERM)
        try:
            p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.fail("收到 SIGTERM 後 10 秒內應結束")
        self.assertEqual(p.returncode, 5)
        deadline = time.monotonic() + 3.0
        left = procs_mentioning(str(sess))
        while left and time.monotonic() < deadline:
            time.sleep(0.05)
            left = procs_mentioning(str(sess))
        self.assertEqual(left, [], "結束後 3 秒內不得有命令列含該場次路徑的程序")
        self.assertEqual(seg_names(sess), segs, "tracks/seg-*.mov 應全部保留")

    # spec §4.55.13：進度行「正規化 已完成 k/6」恰 6 行、k 依序 1–6；預設與 MH_FINALIZE_JOBS=1 都一樣
    def test_progress_lines(self):
        sb, sess = self.base_session()
        for label, over in (("預設", {}), ("MH_FINALIZE_JOBS=1", {"MH_FINALIZE_JOBS": "1"})):
            with self.subTest(case=label):
                s = copy_session(sess, sb.base / f"progress-{len(over)}")
                r, _ = run_fin(self, s, fin_env(sb, **over))
                self.ok(r)
                hits = [PROGRESS_RE.match(ln) for ln in r.stdout.splitlines()]
                ks = [int(h.group(1)) for h in hits if h and h.group(2) == "6"]
                self.assertEqual(ks, [1, 2, 3, 4, 5, 6], f"stdout:{r.stdout}")
                self.assertEqual(len([h for h in hits if h]), 6)

    # spec §4.55.14：同一份 fixture（4 段，含一段疏影格 VFR）以 MH_FINALIZE_JOBS=1 與預設收尾，判準相同（不要求逐位元相同）
    def test_parallel_matches_serial_criteria(self):
        sb = Sandbox(self)
        src = m.make_record_session(sb.root, [dict(dur=3.0), dict(recipe="sparse_vfr", dur=8.0, frames=8),
                                              dict(dur=3.0), dict(dur=2.0)])
        runs = {}
        for label, over in (("serial", {"MH_FINALIZE_JOBS": "1"}), ("parallel", {})):
            s = copy_session(src, sb.base / label)
            # 成品檔名的時間戳取 finalize.json 的 stamp（R3 現行）：兩份給同一個值，檔名才可比
            (s / "錄音" / "tracks" / "finalize.json").write_text(
                json.dumps({"schemaVersion": 1, "stamp": "2026-10-17 09.05.00"}), encoding="utf-8")
            r, _ = run_fin(self, s, fin_env(sb, MH_KEEP_SEGMENTS="1", **over))
            self.ok(r)
            runs[label] = s
        a, b = runs["serial"], runs["parallel"]
        names = lambda s, d: sorted(p.name for p in (s / d).iterdir() if p.is_file())  # noqa: E731
        for d in ("影片", "錄音"):
            self.assertEqual(names(a, d), names(b, d), f"{d}/ 的成品檔名應相同")
        va, vb = [sorted((s / "影片").glob("*.mov"))[0] for s in (a, b)]
        self.assertEqual(m.frame_count(va), m.frame_count(vb), "成品影片的影格數應相同")
        self.assertLess(abs(m.stream_duration(va, "video") - m.stream_duration(vb, "video")), 0.05,
                        "影片軌長度差應 < 0.05 秒")
        wa, wb = [sorted(p for p in (s / "錄音").glob("*.wav"))[0] for s in (a, b)]
        self.assertEqual(len(m.pcm_s16(wa)), len(m.pcm_s16(wb)), "錄音/*.wav 的樣本數應相同")
        fa, fb = finalize_json(a), finalize_json(b)
        self.assertEqual(sorted(fa), sorted(fb), "finalize.json 的鍵集合應相同")
        self.assertEqual(fa.get("skipped"), fb.get("skipped"))
        e2e = Path(__file__).resolve().parent / "e2e_check.py"
        checks = {}
        for label, s in runs.items():
            rr = subprocess.run([sys.executable, "-B", str(e2e), str(s), "--json"], capture_output=True, text=True,
                                timeout=300)
            self.assertIn(rr.returncode, (0, 1), rr.stderr)
            checks[label] = {x["check"]: x["ok"] for x in json.loads(rr.stdout)}
        self.assertEqual(checks["serial"], checks["parallel"], "e2e_check.py 預設組的結果應相同")
        product = ("canvas", "video_format", "video_covers_audio", "one_audio_file", "wav_format")
        for label in runs:
            self.assertEqual([c for c in product if not checks[label].get(c)], [],
                             f"{label} 的收尾成品應通過 e2e_check.py 的成品檢查")

    # spec §4.55.15：分析平行後順序不變（skipped 依序為 seg-0002、seg-0005）
    def test_parallel_analysis_keeps_order(self):
        sb, sess = self.base_session()
        tracks = sess / "錄音" / "tracks"
        for n in ("seg-0002.mov", "seg-0005.mov"):
            (tracks / n).write_bytes(b"")
        r, _ = run_fin(self, sess, fin_env(sb))
        self.ok(r)
        skipped = (finalize_json(sess) or {}).get("skipped")
        self.assertIsInstance(skipped, list)
        self.assertTrue(all(isinstance(e, dict) for e in skipped), "skipped[] 每筆應為物件（§3.17）")
        self.assertEqual([e.get("file") for e in skipped], ["seg-0002.mov", "seg-0005.mov"])
        line = next((ln for ln in r.stdout.splitlines() if "略過無法讀取的段落：" in ln), None)
        self.assertIsNotNone(line, f"stdout 應有「略過無法讀取的段落：」行\nstdout:{r.stdout}")
        tail = line.split("略過無法讀取的段落：", 1)[1]
        self.assertEqual(tail, "seg-0002.mov、seg-0005.mov", "該行內應依序為這兩個檔名")

    # ---------- 形狀（§4.55.16、§4.55.19、§4.55.20） ----------

    # spec §4.55.16、§4.55.19、§4.55.20、§3.25 模組名稱
    def test_parallel_shape(self):
        src = FINALIZE_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        defs = top_defs(tree)
        problems = []

        def body(name):
            n = defs.get(name)
            if n is None:
                problems.append(f"缺頂層 {name}")
                return None, ""
            return n, ast.get_source_segment(src, n)

        def has(name, text, needles):
            problems.extend(f"{name} 的本體缺 {x}" for x in needles if x not in text)

        def lacks(name, text, needles):
            problems.extend(f"{name} 的本體不得含 {x}" for x in needles if x in text)

        for name in ("encode", "normalize", "run_step", "step_timeout", "on_sigterm", "say", "finalize_locked",
                     "finalize_jobs", "recording_in_progress", "normalize_deps", "run_ordered", "wait_finalize_lock",
                     "SegmentAborted"):
            if name not in defs:
                problems.append(f"缺頂層 {name}（不得改名或包進 class）")
        assigned = {t.id for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))
                    for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
        for name in ("_ACTIVE", "_STOPPING", "_ABORT_DISPATCH", "_ABORT_FROM", "_SEG_PROCS", "_SEG", "_ACTIVE_LOCK",
                     "_X264_LOCK", "_SAY_LOCK", "FINALIZE_JOBS_DEFAULT", "FINALIZE_JOBS_MAX", "FINALIZE_JOBS_RECORDING",
                     "SIGTERM_RESCANS", "SIGTERM_RESCAN_SECONDS", "WAIT_LOCK_POLL_SECONDS"):
            if name not in assigned:
                problems.append(f"缺模組層級的 {name}")

        node, text = body("run_step")
        if node is not None:
            has("run_step", text, ("_ACTIVE_LOCK", "_STOPPING", "_SEG_PROCS", "SegmentAborted", "_ABORT_DISPATCH",
                                   "_ABORT_FROM"))
            if "Popen(" in text and "_SEG_PROCS" in text and text.index("_SEG_PROCS") < text.index("Popen("):
                problems.append("run_step 的 _SEG_PROCS 第一次出現應晚於 Popen(（在 Popen 之後登記）")
            popen = [c.lineno for c in ast.walk(node) if isinstance(c, ast.Call)
                     and (getattr(c.func, "attr", None) == "Popen" or getattr(c.func, "id", None) == "Popen")]
            withs = [w for w in ast.walk(node) if isinstance(w, ast.With) and popen and w.lineno > min(popen)
                     and any(isinstance(i.context_expr, ast.Name) and i.context_expr.id == "_ACTIVE_LOCK" for i in w.items)
                     and "_SEG_PROCS" in ast.get_source_segment(src, w)]
            if not withs:
                problems.append("run_step 應在 Popen 之後的 with _ACTIVE_LOCK 區塊內登記 _SEG_PROCS")

        _, text = body("on_sigterm")
        if text:
            has("on_sigterm", text, ("_STOPPING", "SIGTERM_RESCANS", "os._exit(5)"))
            lacks("on_sigterm", text, ("_ACTIVE_LOCK", "say("))
            if "_STOPPING.set()" in text and "killpg" in text and text.index("_STOPPING.set()") > text.index("killpg"):
                problems.append("on_sigterm 的 _STOPPING.set() 應早於第一個 killpg")
            elif "_STOPPING.set()" not in text:
                problems.append("on_sigterm 應呼叫 _STOPPING.set()")

        node, text = body("encode")
        if node is not None:
            has("encode", text, ("_X264_LOCK",))
            handlers = [h for h in ast.walk(node) if isinstance(h, ast.ExceptHandler)
                        and "SegmentAborted" in type_names(h.type)]
            if not handlers:
                problems.append("encode 的本體應有 except SegmentAborted")
            for h in handlers:
                if any(isinstance(x, ast.Continue) for x in ast.walk(h)):
                    problems.append("encode 的 except SegmentAborted 區塊不得含 continue（被中止的段不改試 libx264）")

        loops = [n for n, d in defs.items() if isinstance(d, ast.FunctionDef) and n != "normalize"
                 and "normalize" in call_names(d)]
        if not loops:
            problems.append("找不到呼叫 normalize( 的函式")
        for n in loops:
            if "normalize_deps(" not in ast.get_source_segment(src, defs[n]):
                problems.append(f"{n}（normalize 迴圈所在函式）應含 normalize_deps(")

        users = {n for n, d in defs.items() if isinstance(d, ast.FunctionDef) and n != "compensated_audio"
                 and "compensated_audio" in call_names(d)}
        if users != {"finalize_locked"}:
            problems.append(f"compensated_audio( 只應出現在 finalize_locked 的本體：{sorted(users)}")
        for ln in src.splitlines():
            if "submit(" in ln and "compensated_audio" in ln:
                problems.append(f"S-C 補償照串行，不得與 submit( 同一行：{ln.strip()}")

        _, text = body("run_ordered")
        if text:
            lacks("run_ordered", text, (".communicate(", ".wait(", ".poll(", "kill_group("))
            has("run_ordered", text, ("os.killpg(", "_SEG_PROCS", "_ACTIVE_LOCK", "KILL_GRACE"))

        node = defs.get("SegmentAborted")
        if isinstance(node, ast.ClassDef):
            bad = [b for b in type_names(ast.Tuple(elts=node.bases)) if b in ("FinalizeError", "StepTimeout")]
            if bad:
                problems.append(f"class SegmentAborted 的基底不得是 FinalizeError：{bad}")
        self.assertEqual(problems, [], "\n".join(problems))

        mod = load(self)
        need(self, mod, "SIGTERM_RESCANS", "SIGTERM_RESCAN_SECONDS", "WAIT_LOCK_POLL_SECONDS", "SegmentAborted",
             "FinalizeError", "_STOPPING", "_ABORT_DISPATCH", "_SEG_PROCS", "_SEG", "_ACTIVE_LOCK", "_X264_LOCK",
             "_SAY_LOCK")
        self.assertEqual((mod.SIGTERM_RESCANS, mod.SIGTERM_RESCAN_SECONDS, mod.WAIT_LOCK_POLL_SECONDS), (2, 0.05, 0.5))
        self.assertFalse(issubclass(mod.SegmentAborted, mod.FinalizeError), "SegmentAborted 不得繼承 FinalizeError")
        self.assertIsInstance(mod._STOPPING, threading.Event)
        self.assertIsInstance(mod._ABORT_DISPATCH, threading.Event)
        self.assertIsInstance(mod._SEG_PROCS, dict)
        self.assertIsInstance(mod._SEG, threading.local)
        lock_t = type(threading.Lock())
        for name in ("_ACTIVE_LOCK", "_X264_LOCK", "_SAY_LOCK"):
            self.assertIsInstance(getattr(mod, name), lock_t, f"{name} 應為 threading.Lock()")

    # spec §4.55.21（修正輪 N5）：say 加鎖、一次寫一行；平行收尾的 stdout 每行完整；8 執行緒 × 200 行長字串不交錯
    def test_say_lines_atomic(self):
        src = FINALIZE_PY.read_text(encoding="utf-8")
        node = top_defs(ast.parse(src)).get("say")
        self.assertIsNotNone(node, "bin/_record_finalize.py 應有頂層 say")
        text = ast.get_source_segment(src, node)
        for x in ("_SAY_LOCK", "sys.stdout.write("):
            self.assertIn(x, text, f"say 的本體應含 {x}")

        sb = Sandbox(self)
        script = (
            "import importlib.util, sys, threading\n"
            "sys.dont_write_bytecode = True\n"
            "spec = importlib.util.spec_from_file_location('_rf_say', sys.argv[1])\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(mod)\n"
            "bar = threading.Barrier(8)\n"
            "def w(t):\n"
            "    bar.wait()\n"
            "    for i in range(200):\n"
            "        mod.say(f'{t}:{i:03d}:' + 'x' * 2000)\n"
            "ths = [threading.Thread(target=w, args=(t,)) for t in range(8)]\n"
            "[th.start() for th in ths]\n"
            "[th.join() for th in ths]\n")
        r = subprocess.run([sys.executable, "-B", "-c", script, str(FINALIZE_PY)], env=fin_env(sb), capture_output=True,
                           text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        lines = r.stdout.split("\n")
        self.assertEqual(lines[-1], "", "輸出應以換行結尾")
        lines = lines[:-1]
        self.assertEqual(len(lines), 1600, "8 個執行緒各 200 行 → 恰 1600 行")
        pat = re.compile(r"^([0-7]):(\d{3}):x{2000}$")
        bad = [i for i, ln in enumerate(lines) if not pat.match(ln)]
        self.assertEqual(bad[:5], [], "每一行都應完整（不交錯）")
        self.assertEqual(len({(mm.group(1), mm.group(2)) for mm in map(pat.match, lines)}), 1600)

        self.require_videotoolbox()
        sess = m.make_record_session(sb.root, SIX)
        r, _ = run_fin(self, sess, par_env(sb, sb.base / "par.log"))
        self.ok(r)
        took = re.compile(r"^耗時 \S+（[^）]+）：\d+\.\d 秒$")
        prog = re.compile(r"^正規化 已完成 \d+/\d+$")
        for ln in r.stdout.splitlines():
            if ln.count("耗時") > 1:
                self.fail(f"一行不得同時含兩個「耗時」：{ln!r}")
            if "耗時" in ln:
                self.assertRegex(ln, took)
            elif "正規化 已完成" in ln:
                self.assertRegex(ln, prog)

    # ---------- 收尾鎖等待（§4.55.22，MH_FINALIZE_WAIT_LOCK） ----------

    def hold_finalize_lock(self, sess, seconds):
        lock = sess / "錄音" / "tracks" / ".finalize.lock"
        h = subprocess.Popen([sys.executable, "-c", HOLD_FINALIZE_LOCK, str(lock), str(seconds)], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: (h.poll() is None and h.kill(), h.wait()))
        self.assertEqual(h.stdout.readline().strip(), "ready", "持鎖程序沒有拿到收尾鎖")
        return h, time.monotonic()

    # spec §4.55.22、§6 第 156 條：已收尾完成的場次、收尾鎖被持有 2 秒 → 等鎖放開、冪等判斷「已完成」、回 0
    def test_wait_lock_then_idempotent(self):
        sb, sess = self.base_session([dict(dur=2.0), dict(dur=2.0)])
        r, _ = run_fin(self, sess, fin_env(sb))
        self.ok(r)
        _, t0 = self.hold_finalize_lock(sess, 2)
        r, _ = run_fin(self, sess, fin_env(sb, MH_FINALIZE_WAIT_LOCK="1"))
        took = time.monotonic() - t0
        self.ok(r)
        self.assertTrue([ln for ln in r.stdout.splitlines() if ln.startswith("● 這個場次正在收尾")],
                        f"應印一行「● 這個場次正在收尾…」\nstdout:{r.stdout}")
        self.assertGreaterEqual(took, 1.5, f"應至少等到鎖放開（耗時 {took:.2f} 秒）")
        self.assertIn("✓ 已完成（不重做", r.stdout)

    # spec §4.55.22：未收尾的場次、同樣持鎖 → 鎖放開後照常收尾、回 0、成品存在
    def test_wait_lock_then_finalize(self):
        sb, sess = self.base_session([dict(dur=2.0), dict(dur=2.0)])
        _, t0 = self.hold_finalize_lock(sess, 2)
        r, _ = run_fin(self, sess, fin_env(sb, MH_FINALIZE_WAIT_LOCK="1"))
        took = time.monotonic() - t0
        self.ok(r)
        self.assertGreaterEqual(took, 1.5, f"應至少等到鎖放開（耗時 {took:.2f} 秒）")
        self.assertEqual(len(list((sess / "影片").glob("*.mov"))), 1, "影片/ 應有成品")
        self.assertEqual(len([n for n in audio_files_top(sess) if n.endswith(".wav")]), 1, "錄音/ 應有 wav 成品")

    # spec §4.55.22：等待中送 SIGTERM → 5 秒內回 5；沒設 MH_FINALIZE_WAIT_LOCK 時照 §4.28.1 在 3 秒內回 5
    def test_wait_lock_sigterm(self):
        sb, sess = self.base_session([dict(dur=2.0), dict(dur=2.0)])
        self.hold_finalize_lock(sess, 60)
        p = subprocess.Popen([sys.executable, "-B", str(FINALIZE_PY), str(sess)],
                             env=fin_env(sb, MH_FINALIZE_WAIT_LOCK="1"), stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(lambda: (p.poll() is None and os.killpg(p.pid, signal.SIGKILL), p.communicate()))
        t_end = time.monotonic() + 1.0
        while time.monotonic() < t_end and p.poll() is None:
            time.sleep(0.05)
        if p.poll() is not None:
            out, err = p.communicate()
            self.fail(f"MH_FINALIZE_WAIT_LOCK=1 時拿不到收尾鎖應等待，不得立刻結束（rc={p.returncode}）\n"
                      f"stdout:{out}\nstderr:{err}")
        os.kill(p.pid, signal.SIGTERM)
        try:
            out, err = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            self.fail("等待收尾鎖時收到 SIGTERM，應在 5 秒內結束")
        self.assertEqual(p.returncode, 5, f"stdout:{out}\nstderr:{err}")
        self.assertIn("● 這個場次正在收尾", out)

        t0 = time.monotonic()
        r, _ = run_fin(self, sess, fin_env(sb), timeout=30)
        self.assertLess(time.monotonic() - t0, 3.0, "沒設 MH_FINALIZE_WAIT_LOCK 時應立刻結束")
        self.assertEqual(r.returncode, 5, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("這個場次正在收尾", r.stderr)


if __name__ == "__main__":
    unittest.main()

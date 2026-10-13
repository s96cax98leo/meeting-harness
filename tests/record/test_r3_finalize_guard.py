"""收尾鎖、mkstemp、逐步逾時、讀不到的段落（spec §4.28.1–§4.28.4、§4.28.7、§4.28.8；R3-§2.2 的 finish 5）。

合成素材只在 TMPDIR；收尾以 python3 bin/_record_finalize.py <場次> 直接執行（MH_RECORD_HOME 指向暫存 home）。
finalize.json 的位置：spec §3.17 寫「錄音/finalize.json」，現行程式寫「錄音/tracks/finalize.json」，本檔兩處都找。
"""
import ast
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

from tests.record import _media as m
from tests.record._helpers import BIN, SLOW_FFMPEG, Sandbox, snapshot, tmpdir

FINALIZE_PY = BIN / "_record_finalize.py"
TIMEOUT_STEPS = {"normalize", "concat", "mix", "probe"}

HOLD_FINALIZE_LOCK = r'''
import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("ready", flush=True)
time.sleep(float(sys.argv[2]))
'''


def finalize_json(sess):
    for p in (sess / "錄音" / "tracks" / "finalize.json", sess / "錄音" / "finalize.json"):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def run_finalize(sb, sess, timeout=300, **env):
    """以新的 process group 執行；逾時就整組 SIGKILL 後回 None（呼叫端判 FAIL）。"""
    p = subprocess.Popen([sys.executable, str(FINALIZE_PY), str(sess)], env=sb.env(**env), cwd=str(sb.cwd),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    t0 = time.monotonic()
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, time.monotonic() - t0
    return subprocess.CompletedProcess(p.args, p.returncode, out, err), time.monotonic() - t0


def procs_mentioning(text):
    r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True)
    return [ln for ln in r.stdout.splitlines() if text in ln and "ps -axo" not in ln]


def load_finalize_module(tc, home):
    """以檔案路徑載入 _record_finalize.py（載入時會找 ffmpeg；MH_RECORD_HOME 指向暫存 home，不讀使用者的設定）。"""
    spec = importlib.util.spec_from_file_location("_record_finalize_under_test", FINALIZE_PY)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.dict(os.environ, {"MH_RECORD_HOME": str(home)}), mock.patch.object(sys, "dont_write_bytecode", True):
        os.environ.pop("MH_FINALIZE_STEP_TIMEOUT", None)
        spec.loader.exec_module(mod)
    return mod


class TestR3FinalizeGuard(unittest.TestCase):
    TWO = [dict(dur=2.0), dict(dur=2.0)]

    # spec §4.28.1：收尾鎖被持有 → 5、「這個場次正在收尾」、場次內檔案全不變（finalize.json 不存在時不建立）
    def test_second_finalize_refused(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.TWO)
        lock = sess / "錄音" / "tracks" / ".finalize.lock"
        h = subprocess.Popen([sys.executable, "-c", HOLD_FINALIZE_LOCK, str(lock), "60"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: (h.poll() is None and h.kill(), h.wait()))
        self.assertEqual(h.stdout.readline().strip(), "ready")
        before = snapshot(sess)
        r, _ = run_finalize(sb, sess, timeout=60)
        self.assertIsNotNone(r, "收尾鎖被持有時應立刻結束，不得等待")
        self.assertEqual(r.returncode, 5, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("這個場次正在收尾", r.stderr)
        self.assertEqual(snapshot(sess), before, "場次內所有檔的 mtime 與內容應不變")
        self.assertIsNone(finalize_json(sess), "finalize.json 原本不存在時不得建立")
        self.assertFalse((sess / "影片").exists(), "不得建立 影片/")

    # spec §4.28.2：write_json_atomic 用同目錄 tempfile.mkstemp；不得有 + ".tmp" 或 '.tmp' 字面
    def test_atomic_write_uses_mkstemp(self):
        src = FINALIZE_PY.read_text(encoding="utf-8")
        tree = ast.parse(src)
        fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "write_json_atomic"),
                  None)
        self.assertIsNotNone(fn, "_record_finalize.py 應有 write_json_atomic")
        body = ast.get_source_segment(src, fn)
        self.assertIn("mkstemp", body, "write_json_atomic 應以 tempfile.mkstemp 建暫存檔")
        self.assertIn("dir=", body, "mkstemp 應建在同目錄（dir=）")
        for lit in ('+ ".tmp"', "'.tmp'"):
            self.assertNotIn(lit, src, f"_record_finalize.py 不得出現 {lit}")

    # spec §4.28.3：MH_FINALIZE_STEP_TIMEOUT=2＋慢速 ffmpeg → 30 秒內回 5、timedOut.step、段落保留、沒有殘留子程序
    def test_step_timeout_exits_5_and_keeps_segments(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.TWO)
        segs = sorted(p.name for p in (sess / "錄音" / "tracks").glob("seg-*.mov"))
        r, took = run_finalize(sb, sess, timeout=40, MH_FFMPEG=SLOW_FFMPEG, SLOW_FFMPEG_SECONDS="8",
                               MH_FINALIZE_STEP_TIMEOUT="2")
        self.assertIsNotNone(r, f"收尾應在 30 秒內因逐步逾時結束（40 秒仍未結束，已強制終止；耗時 {took:.1f} 秒）")
        self.assertEqual(r.returncode, 5, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertLess(took, 30.0, f"耗時 {took:.1f} 秒")
        fin = finalize_json(sess)
        self.assertIsInstance(fin, dict, "逾時也應寫 finalize.json（含 timedOut）")
        self.assertIsInstance(fin.get("timedOut"), dict)
        self.assertIn(fin["timedOut"].get("step"), TIMEOUT_STEPS)
        self.assertEqual(fin["timedOut"].get("seconds"), 2)
        self.assertEqual(sorted(p.name for p in (sess / "錄音" / "tracks").glob("seg-*.mov")), segs,
                         "tracks/seg-*.mov 應全部保留")
        deadline = time.monotonic() + 3.0
        left = procs_mentioning(str(sess))
        while left and time.monotonic() < deadline:
            left = procs_mentioning(str(sess))
        self.assertEqual(left, [], "不得殘留 ffmpeg／ffprobe 子程序")

    # spec §4.28.4：step_timeout 的預設值
    def test_step_timeout_values(self):
        mod = load_finalize_module(self, tmpdir(self))
        step_timeout = getattr(mod, "step_timeout", None)
        self.assertTrue(callable(step_timeout), "_record_finalize.py 應有模組函式 step_timeout(step, seconds)")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MH_FINALIZE_STEP_TIMEOUT", None)
            for (step, secs), want in ((("probe", 60), 30), (("normalize", 5), 120), (("normalize", 60), 600),
                                       (("concat", 50), 300), (("mix", 3600), 10800)):
                with self.subTest(step=step, seconds=secs):
                    self.assertAlmostEqual(float(step_timeout(step, secs)), want, delta=0.001)

    # spec §4.28.7、§6 第 126 條：0 位元組的 seg-0002.mov 搬到 tracks/unreadable/，skipped[].movedTo 記相對路徑
    def test_unreadable_moved_not_deleted(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)])
        tracks = sess / "錄音" / "tracks"
        (tracks / "seg-0002.mov").write_bytes(b"")
        r, _ = run_finalize(sb, sess)
        self.assertIsNotNone(r)
        self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue((tracks / "unreadable" / "seg-0002.mov").is_file(), "讀不到的段落應搬到 tracks/unreadable/")
        self.assertFalse((tracks / "seg-0002.mov").exists())
        self.assertEqual(sorted(p.name for p in tracks.glob("seg-*.mov")), [], "已併入成品的段落照常刪除")
        fin = finalize_json(sess)
        self.assertIsInstance(fin, dict)
        skipped = fin.get("skipped")
        self.assertIsInstance(skipped, list)
        self.assertEqual(len(skipped), 1, skipped)
        self.assertIsInstance(skipped[0], dict, "skipped[] 每筆應為物件（含 movedTo）")
        self.assertEqual(skipped[0].get("movedTo"), "tracks/unreadable/seg-0002.mov")

        # 撞名加 -1：另一場次的 unreadable/ 已有同名檔
        sess2 = m.make_record_session(sb.base / "根2", [dict(dur=2.0), dict(dur=2.0)])
        t2 = sess2 / "錄音" / "tracks"
        (t2 / "unreadable").mkdir()
        (t2 / "unreadable" / "seg-0002.mov").write_bytes(b"old")
        (t2 / "seg-0002.mov").write_bytes(b"")
        r, _ = run_finalize(sb, sess2)
        self.assertIsNotNone(r)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((t2 / "unreadable" / "seg-0002.mov").read_bytes(), b"old", "既有的檔不得被覆蓋")
        new = sorted(p.name for p in (t2 / "unreadable").iterdir() if p.name != "seg-0002.mov")
        self.assertEqual(len(new), 1, new)
        self.assertIn("-1", new[0])
        moved = (finalize_json(sess2) or {}).get("skipped") or [{}]
        self.assertEqual(moved[0].get("movedTo"), "tracks/unreadable/" + new[0])

    # spec §4.28.8：每一步 ffmpeg／ffprobe 的耗時寫進 log（一行一步，含步驟名與秒數，小數 1 位）
    def test_step_durations_logged(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.TWO)
        r, _ = run_finalize(sb, sess)
        self.assertIsNotNone(r)
        self.assertEqual(r.returncode, 0, r.stderr)
        log = r.stdout + "\n" + r.stderr
        lf = sb.home / "record.log"
        if lf.is_file():
            log += "\n" + lf.read_text(encoding="utf-8", errors="replace")
        dur = re.compile(r"\d+\.\d(?!\d)")
        for names in (("normalize", "正規化"), ("concat", "串接"), ("probe", "ffprobe")):
            with self.subTest(step=names[0]):
                lines = [ln for ln in log.splitlines() if any(n in ln for n in names) and dur.search(ln)
                         and ("秒" in ln or re.search(r"\d+\.\ds\b", ln))]
                self.assertTrue(lines, f"log 應有「{names[0]}」步驟的耗時行（秒數小數 1 位）")


if __name__ == "__main__":
    unittest.main()

"""bin/lib/_record_lib.py 與 Python／Swift 共用向量（spec §3.15、§3.19、§4.32.1–§4.32.6；design R3-D6）。

模組以檔案路徑載入（bin/lib/ 不是套件）；檔案不存在時判 FAIL，不得跳過。所有寫檔都在 TMPDIR。
向量檔 tests/record/vectors/*.json 也給 swift:R3RecordLibVectorTests 讀（同一份檔，Python 與 Swift 各跑一遍）：
- output_time.json：陣列，每筆 {name, t, first_start, pauses（PauseEvent：t、outputT、wallClock、kind）, l_out, expect}
- levels_intervals.json：陣列，每筆 {name, levels（一維、每窗 dBFS 或 null）, window, threshold_db, merge_gap, pad,
  total, expect（[[start, end], …]）}
"""
import ast
import importlib.util
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.record import _fixtures as fx
from tests.record._helpers import tmpdir
from tests.record.e2e_check import record_to_output
from tests.record.surface import REPO

LIB_DIR = REPO / "bin" / "lib"
RECORD_LIB = LIB_DIR / "_record_lib.py"
VECTORS = Path(__file__).resolve().parent / "vectors"
TOL = 0.0005

HOLD_DEFAULTS_LOCK = r'''
import fcntl, os, sys, time
fd = os.open(os.path.join(sys.argv[1], "record.defaults.lock"), os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("ready", flush=True)
time.sleep(float(sys.argv[2]))
'''


def load_record_lib(tc):
    """以檔案路徑載入 bin/lib/_record_lib.py；不存在判 FAIL。"""
    tc.assertTrue(RECORD_LIB.is_file(), f"{RECORD_LIB.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
    spec = importlib.util.spec_from_file_location("_record_lib_under_test", RECORD_LIB)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.object(sys, "dont_write_bytecode", True):  # 不在 bin/lib/ 留下 __pycache__
        spec.loader.exec_module(mod)
    return mod


def func(tc, mod, name):
    f = getattr(mod, name, None)
    tc.assertTrue(callable(f), f"bin/lib/_record_lib.py 應有函式 {name}")
    return f


def vectors(name):
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


def clip_fixture(base):
    """錄音目錄：兩段（0–20、30–50 秒，錄製時鐘），20→30 暫停；錄製時鐘 5–10 與 35–40 秒有聲。

    成品時間的 clip（門檻 -60、補 0.75、合併間隔 2.0）＝[[4.25, 10.75], [24.25, 30.75]]。"""
    rec = Path(base) / "錄音"
    n = 100  # 50 秒 × 每秒 2 窗
    sysl, mic = [], []
    for k in range(n):
        t = k * 0.5
        if 20.0 <= t < 30.0:
            sysl.append(None)
            mic.append(None)
        elif 5.0 <= t < 10.0 or 35.0 <= t < 40.0:
            sysl.append(-20.0 if k % 2 else -75.0)
            mic.append(-75.0 if k % 2 else -25.0)
        else:
            sysl.append(-75.0)
            mic.append(-80.0)
    fx.write_tracks_json(rec, [(0.0, 20.0), (30.0, 20.0)], system=sysl, mic=mic,
                         pauses=[(20.0, "pause"), (30.0, "resume")])
    return rec


CLIP_EXPECT = [[4.25, 10.75], [24.25, 30.75]]


class TestR3RecordLib(unittest.TestCase):
    def assert_intervals(self, got, want, msg=""):
        self.assertIsInstance(got, list, msg)
        self.assertEqual(len(got), len(want), f"{msg} 區間數：{got} vs {want}")
        for g, w in zip(got, want):
            self.assertEqual(len(g), 2, msg)
            self.assertAlmostEqual(float(g[0]), w[0], delta=TOL, msg=f"{msg} {got} vs {want}")
            self.assertAlmostEqual(float(g[1]), w[1], delta=TOL, msg=f"{msg} {got} vs {want}")

    # spec §4.32.1：向量涵蓋 R2 §4.18 的 outputTime 案例、沒配對的 pause、l_out=0.18
    def test_output_time_vectors(self):
        cases = vectors("output_time.json")
        self.assertIsInstance(cases, list)
        self.assertTrue(any(c["l_out"] == 0.18 for c in cases), "向量應含 l_out=0.18")
        self.assertTrue(any(c["pauses"] and c["pauses"][-1]["kind"] == "pause" for c in cases), "向量應含沒配對的 pause")
        for c in cases:
            self.assertEqual(set(c), {"name", "t", "first_start", "pauses", "l_out", "expect"}, c.get("name"))
            if c["l_out"] == 0:
                self.assertAlmostEqual(record_to_output(c["t"], c["first_start"], c["pauses"]), c["expect"],
                                       delta=TOL, msg=f"{c['name']}：l_out=0 時應與 e2e_check.record_to_output 相同")
        lib = load_record_lib(self)
        output_time = func(self, lib, "output_time")
        for c in cases:
            with self.subTest(case=c["name"]):
                got = output_time(c["t"], c["first_start"], c["pauses"], c["l_out"])
                self.assertAlmostEqual(got, c["expect"], delta=TOL)
                if c["l_out"] == 0:
                    self.assertAlmostEqual(output_time(c["t"], c["first_start"], c["pauses"]), c["expect"], delta=TOL,
                                           msg="l_out 預設應為 0")

    # spec §4.32.2：門檻嚴格大於、間隔 < merge_gap 合併、= 不合併、pad 夾在 [0, total]、null 視為無聲
    def test_levels_intervals_vectors(self):
        cases = vectors("levels_intervals.json")
        self.assertIsInstance(cases, list)
        lib = load_record_lib(self)
        levels_intervals = func(self, lib, "levels_intervals")
        for c in cases:
            with self.subTest(case=c["name"]):
                got = levels_intervals(c["levels"], c["window"], c["threshold_db"], c["merge_gap"], c["pad"],
                                       c["total"])
                self.assert_intervals([list(x) for x in got], c["expect"], c["name"])

    # spec §4.32.3：paused_total 只算已配對的暫停；clip_timestamps 缺 manifest 或沒有 levels 時回 None
    def test_paused_total_and_clip_none(self):
        lib = load_record_lib(self)
        paused_total = func(self, lib, "paused_total")
        clip_timestamps = func(self, lib, "clip_timestamps")
        ev = [{"t": 70.0, "kind": "pause"}, {"t": 100.0, "kind": "resume"}, {"t": 150.0, "kind": "pause"}]
        self.assertAlmostEqual(paused_total(ev), 30.0, delta=TOL)
        self.assertAlmostEqual(paused_total([]), 0.0, delta=TOL)
        self.assertAlmostEqual(paused_total([{"t": 5.0, "kind": "resume"}]), 0.0, delta=TOL)
        d = tmpdir(self)
        empty = d / "沒有manifest" / "錄音"
        empty.mkdir(parents=True)
        self.assertIsNone(clip_timestamps(str(empty)), "缺 manifest.json 時應回 None")
        nolv = d / "沒有levels" / "錄音"
        fx.write_tracks_json(nolv, [(0.0, 10.0)])
        self.assertIsNone(clip_timestamps(str(nolv)), "manifest 沒有 levels 時應回 None")
        rec = clip_fixture(d / "有levels")
        self.assert_intervals([list(x) for x in clip_timestamps(str(rec))], CLIP_EXPECT, "clip_timestamps")

    # spec §4.32.4、§3.19：clip CLI 印 JSON（小數 3 位；退回整檔時 null）回 0；目錄不存在回 2
    def test_cli_clip(self):
        self.assertTrue(RECORD_LIB.is_file(), f"{RECORD_LIB.relative_to(REPO)} 不存在")
        d = tmpdir(self)
        rec = clip_fixture(d / "場次")

        def run(*args):
            return subprocess.run([sys.executable, str(RECORD_LIB), "clip", *map(str, args)], capture_output=True,
                                  text=True, timeout=60, cwd=str(d))

        r = run(rec)
        self.assertEqual(r.returncode, 0, r.stderr)
        got = json.loads(r.stdout)
        self.assert_intervals(got, CLIP_EXPECT, "clip CLI")
        for a, b in got:
            for v in (a, b):
                self.assertEqual(round(v, 3), v, "小數 3 位")
        empty = d / "沒有levels" / "錄音"
        empty.mkdir(parents=True)
        r = run(empty)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIsNone(json.loads(r.stdout), "退回整檔時應印 null")
        r = run(d / "不存在的目錄")
        self.assertEqual(r.returncode, 2, "目錄不存在應回 2")

    # spec §4.32.5：bin/lib/*.py 都過 ast.parse，且 _record_lib.py 存在（_lint.sh 26 檔由 test_regression 驗）
    def test_bin_lib_syntax(self):
        self.assertTrue(LIB_DIR.is_dir(), "bin/lib/ 不存在")
        self.assertTrue(RECORD_LIB.is_file(), "bin/lib/_record_lib.py 不存在")
        files = sorted(LIB_DIR.glob("*.py"))
        self.assertTrue(files)
        for p in files:
            with self.subTest(file=p.name):
                ast.parse(p.read_text(encoding="utf-8"), filename=str(p))

    # spec §4.32.6、§3.15：merge_defaults 取 record.defaults.lock、讀後合併、壞檔不寫、持鎖逾時約 5 秒丟例外
    def test_merge_defaults(self):
        lib = load_record_lib(self)
        merge_defaults = func(self, lib, "merge_defaults")
        home = tmpdir(self)
        path = home / "record.defaults.json"

        merge_defaults(str(home), {"syncCompensation": "reported"})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"syncCompensation": "reported"},
                         "缺檔時只有 updates 的鍵")

        seven = {"root": "/範例/根", "type": "internal", "attendees": ["範例甲"], "harness": "/範例/harness",
                 "python3": "/usr/bin/python3", "ffmpeg": "/usr/bin/ffmpeg", "minFreeBytes": 123, "x": [1, 2]}
        path.write_text(json.dumps(seven, ensure_ascii=False), encoding="utf-8")
        merge_defaults(str(home), {"syncCompensation": "calibrated"})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), dict(seven, syncCompensation="calibrated"),
                         "只改 updates 的鍵，其他（含不認得的 x）原樣保留")
        self.assertEqual(sorted(p.name for p in home.iterdir() if not p.name.startswith("record.defaults.")), [],
                         "同目錄的暫存檔應已 rename 掉")

        for bad in ("[1, 2]", "{壞檔", '"字串"'):
            with self.subTest(bad=bad):
                path.write_text(bad, encoding="utf-8")
                before = path.read_bytes()
                with self.assertRaises(Exception):
                    merge_defaults(str(home), {"syncCompensation": "off"})
                self.assertEqual(path.read_bytes(), before, "不是 JSON 物件時不得覆寫")

        path.write_text(json.dumps(seven, ensure_ascii=False), encoding="utf-8")
        before = path.read_bytes()
        h = subprocess.Popen([sys.executable, "-c", HOLD_DEFAULTS_LOCK, str(home), "6"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: (h.poll() is None and h.kill(), h.wait()))
        self.assertEqual(h.stdout.readline().strip(), "ready")
        t0 = time.monotonic()
        with self.assertRaises(Exception):
            merge_defaults(str(home), {"syncCompensation": "off"})
        took = time.monotonic() - t0
        self.assertTrue(4.5 <= took <= 6.0, f"另一程序持鎖 6 秒時應約 5 秒後逾時：{took:.2f} 秒")
        self.assertEqual(path.read_bytes(), before, "逾時不得寫入")


if __name__ == "__main__":
    unittest.main()

"""結構重構（meeting-speed spec §4.13.1、§4.13.2；Story G8）。

- §4.13.1 的行數上限以 `wc -l` 的同一算法（換行字元數）判定；函式本體由第一個 `{` 起到配對的 `}`（含）計行。
- §4.13.2 的 paused_total：先鎖定 bin/_record_finalize.py 的現行輸出（Red 層就綠，E4(3)），
  再要求 bin/lib/_record_lib.py 的 paused_total 與它相同（prep-pipeline 負責轉綠）。
  輸入與期望值在 tests/record/vectors/ms-paused-total.json（期望值＝_record_finalize.paused_total 在 042c404 的輸出）。
"""
import ast
import re
import unittest

from tests.record import test_static_rules as sr
from tests.record import test_ms_support as s

SOURCES = sr.SOURCES
MENUBAR = SOURCES / "Trigger" / "MenuBar.swift"
RECORDING_SESSION = SOURCES / "Capture" / "RecordingSession.swift"
PREFLIGHT_RUNNER = SOURCES / "Capture" / "PreflightRunner.swift"
TRANSCRIPT_QUALITY_PY = s.BIN / "lib" / "_transcript_quality.py"
HELPERS = ("paused_total", "write_json_atomic", "load_json", "record_home")


def wc_l(path):
    return path.read_bytes().count(b"\n")


def bash_function_body(src, name):
    """bash 函式 `name() {` 起到第一個只有 `}` 的行（含）；找不到回 None。"""
    lines = src.splitlines()
    for i, ln in enumerate(lines):
        if re.match(rf"^{re.escape(name)}\(\)\s*\{{", ln):
            for j in range(i + 1, len(lines)):
                if lines[j] == "}":
                    return lines[i:j + 1]
            return None
    return None


def top_level_defs(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


class TestMSRefactor(unittest.TestCase):
    def assert_lines_at_most(self, path, limit):
        self.assertTrue(path.is_file(), f"{path.relative_to(s.REPO)} 不存在")
        n = wc_l(path)
        self.assertLessEqual(n, limit, f"{path.relative_to(s.REPO)} 有 {n} 行，spec §4.13.1 上限 {limit}")

    # spec §4.13.1：MenuBar.swift ≤ 1000 行（trigger-ui）
    def test_line_limit_menubar(self):
        self.assert_lines_at_most(MENUBAR, 1000)

    # spec §4.13.1：RecordingSession.swift ≤ 1000 行（recorder-capture）
    def test_line_limit_recording_session(self):
        self.assert_lines_at_most(RECORDING_SESSION, 1000)

    # spec §4.13.1：PreflightRunner.swift 的 run 函式本體 ≤ 80 行（recorder-capture）
    def test_preflight_run_length(self):
        self.assertTrue(PREFLIGHT_RUNNER.is_file(), "PreflightRunner.swift 不存在")
        src = sr.strip_swift_comments(PREFLIGHT_RUNNER.read_text(encoding="utf-8"))
        bodies = sr.swift_functions(src).get("run", [])
        self.assertTrue(bodies, "PreflightRunner.swift 應仍有 func run(")
        longest = max(len(b.splitlines()) for b in bodies)
        self.assertLessEqual(longest, 80, f"PreflightRunner 的 run 函式本體有 {longest} 行，spec §4.13.1 上限 80")

    # spec §4.13.1：bin/_record_finalize.py ≤ 1300 行（finalize-fast）
    def test_line_limit_record_finalize(self):
        self.assert_lines_at_most(s.FINALIZE_PY, 1300)

    # spec §4.13.1：record.sh 的 cmd_control 本體 ≤ 100 行（record-sh-split）
    def test_cmd_control_length(self):
        body = bash_function_body(s.RECORD_SH.read_text(encoding="utf-8"), "cmd_control")
        self.assertIsNotNone(body, "bin/record.sh 應仍有 cmd_control() {")
        self.assertLessEqual(len(body), 100, f"cmd_control 本體有 {len(body)} 行，spec §4.13.1 上限 100")

    # spec §4.13.1：transcribe.sh 不再含品質檢查的 heredoc（搬到 bin/lib/_transcript_quality.py；asr-robust）
    def test_transcribe_no_quality_heredoc(self):
        src = s.TRANSCRIBE_SH.read_text(encoding="utf-8")
        for needle in ("<<'PYQ'", "compression_ratio", "no_speech_loop", "repeat_run", "zlib"):
            self.assertNotIn(needle, src, f"transcribe.sh 不得再含品質檢查 heredoc 的內容：{needle}")
        self.assertTrue(TRANSCRIPT_QUALITY_PY.is_file(), "應有 bin/lib/_transcript_quality.py")
        q = TRANSCRIPT_QUALITY_PY.read_text(encoding="utf-8")
        for needle in ("compression_ratio", "no_speech_loop", "repeat_run"):
            self.assertIn(needle, q, f"_transcript_quality.py 應含品質判準 {needle}")
        self.assertIn("_transcript_quality.py", src, "transcribe.sh 應呼叫 bin/lib/_transcript_quality.py")

    # spec §4.13.2：_record_finalize.py 不自行定義四個 helper，改由 _record_lib import；_record_lib 各定義一次
    def test_record_helpers_single_definition(self):
        fin_defs = top_level_defs(s.FINALIZE_PY)
        lib_defs = top_level_defs(s.RECORD_LIB_PY)
        for name in HELPERS:
            with self.subTest(helper=name):
                self.assertNotIn(name, fin_defs, f"bin/_record_finalize.py 不得自行定義 {name}")
                self.assertEqual(lib_defs.count(name), 1, f"bin/lib/_record_lib.py 應恰定義一次 {name}")
        fin = s.load_module(s.FINALIZE_PY, "_record_finalize_ms_helpers")
        for name in HELPERS:
            self.assertTrue(callable(getattr(fin, name, None)), f"_record_finalize 模組內仍應可用 {name}")

    # spec §4.13.2（E4(3)）：鎖定 _record_finalize.paused_total 的現行行為（Red 層就綠）
    def test_paused_total_finalize_locked(self):
        fin = s.load_module(s.FINALIZE_PY, "_record_finalize_ms_paused")
        for case in s.load_vector("ms-paused-total.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(fin.paused_total(case["events"]), case["expect"])

    # spec §4.13.2（E4(3)）：_record_lib.paused_total 與 _record_finalize 的期望值相同
    def test_paused_total_record_lib_matches_finalize(self):
        lib = s.load_record_lib()
        for case in s.load_vector("ms-paused-total.json")["cases"]:
            with self.subTest(case=case["name"]):
                self.assertEqual(lib.paused_total(case["events"]), case["expect"])


if __name__ == "__main__":
    unittest.main()

"""R3 實機缺陷 F1：試錄改用內部旗標 --skip-finalize 跳過收尾（spec R3-§6 第 144 條、R3-§7 疑慮 62）。

靜態檢查（不建置、不啟動 app）：
- Capture 原始碼（去掉註解）認得 skip-finalize，且是不吃值的布林旗標。
- 首次引導的試錄啟動參數帶 --skip-finalize。
- bin/ 底下沒有任何檔案含 skip-finalize（meeting.sh／record.sh 不得帶這個旗標）。
- 內部旗標不列在 helpText、README.md、meeting-record 的 SKILL.md（同 MH_RECORD_OPEN 的慣例）。
- 帶旗標時不會走到完成通知：發「會議錄製完成」通知的函式裡，`guard !ctx.skipFinalize` 早於 Notifier.post。
"""
import re
import unittest

from tests.record import test_static_rules as sr
from tests.record.surface import REPO

SOURCES = sr.SOURCES
CAPTURE = SOURCES / "Capture"
SUPPORT = CAPTURE / "Support.swift"
COMMANDS = CAPTURE / "Commands.swift"
RECORDING_SESSION = CAPTURE / "RecordingSession.swift"
ONBOARDING = SOURCES / "Trigger" / "Onboarding.swift"
MAIN_SWIFT = SOURCES / "main.swift"
BIN = REPO / "bin"
README = REPO / "README.md"
RECORD_SKILL = REPO / ".claude" / "skills" / "meeting-record" / "SKILL.md"
FLAG = "skip-finalize"


def rel(p):
    return p.relative_to(REPO).as_posix()


def code(tc, path):
    """去掉註解的原始碼；檔案不存在判 FAIL（不得跳過）。"""
    tc.assertTrue(path.is_file(), f"{rel(path)} 不存在（不得因檔案不存在而跳過）")
    return sr.strip_swift_comments(path.read_text(encoding="utf-8"))


def bracket_after(src, start):
    """從 start 之後第一個 `[` 起，回傳到配對 `]` 的內容（字串內容先遮掉再配對）。"""
    masked = sr.blank_swift_strings(src)
    i = masked.find("[", start)
    if i < 0:
        return ""
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == "[":
            depth += 1
        elif masked[j] == "]":
            depth -= 1
            if depth == 0:
                return src[i:j + 1]
    return src[i:]


class SkipFinalizeStatic(unittest.TestCase):
    def test_capture_knows_flag(self):
        src = "\n".join(code(self, p) for p in sorted(CAPTURE.glob("*.swift")))
        self.assertIn(FLAG, src, "Capture 原始碼（去掉註解）應認得 skip-finalize")
        self.assertRegex(code(self, COMMANDS), r'args\.has\(\s*"skip-finalize"\s*\)',
                         "Commands.swift 應以 args.has(\"skip-finalize\") 讀旗標")

    def test_flag_is_boolean(self):
        m = re.search(r"static\s+let\s+booleanFlags\s*:\s*Set<String>\s*=\s*\[([^\]]*)\]", code(self, SUPPORT))
        self.assertIsNotNone(m, "找不到 Args.booleanFlags")
        self.assertIn(f'"{FLAG}"', m.group(1), "skip-finalize 不帶值，應列在 Args.booleanFlags")

    def test_trial_start_args_have_flag(self):
        src = code(self, ONBOARDING)
        calls = [m.start() for m in re.finditer(r'openSelf\(\s*\[\s*"start"', src)]
        self.assertEqual(len(calls), 1, "試錄應恰有一處以 openSelf([\"start\", …]) 叫起錄製實例")
        args = bracket_after(src, calls[0])
        self.assertIn(f'"--{FLAG}"', args, "試錄的 start 參數應帶 --skip-finalize")
        self.assertNotIn('"--harness"', args, "試錄不得帶 --harness")

    def test_bin_never_passes_flag(self):
        hits = [rel(p) for p in sorted(BIN.rglob("*")) if p.is_file() and FLAG.encode() in p.read_bytes()]
        self.assertEqual(hits, [], "bin/ 底下不得有檔案含 skip-finalize（只給 app 內部使用）")

    def test_flag_not_documented(self):
        for p in (README, RECORD_SKILL):
            self.assertTrue(p.is_file(), f"{rel(p)} 不存在")
            self.assertNotIn(FLAG, p.read_text(encoding="utf-8"), f"{rel(p)} 不列內部旗標 skip-finalize")
        help_m = re.search(r'let\s+helpText\s*=\s*"""(.*?)"""', MAIN_SWIFT.read_text(encoding="utf-8"), re.S)
        self.assertIsNotNone(help_m, "找不到 main.swift 的 helpText")
        self.assertNotIn(FLAG, help_m.group(1), "helpText 不列內部旗標 skip-finalize")

    def test_guard_before_completion_post(self):
        src = code(self, RECORDING_SESSION)
        bodies = [b for bs in sr.swift_functions(src).values() for b in bs
                  if '"會議錄製完成"' in b and "Notifier.post(" in b]
        self.assertTrue(bodies, "RecordingSession.swift 應有發「會議錄製完成」通知的函式")
        for b in bodies:
            post = b.find("Notifier.post(")
            g = re.search(r"guard\s+!\s*ctx\.skipFinalize\b[^{]*\belse\s*\{", b)
            self.assertIsNotNone(g, "發完成通知的函式應有 guard !ctx.skipFinalize else { … }")
            self.assertLess(g.start(), post, "guard !ctx.skipFinalize 應早於 Notifier.post")
            # guard 的 else 區塊必須離開（exit／return），不得落到 Notifier.post
            masked = sr.blank_swift_strings(b)
            i, depth = g.end() - 1, 0
            for j in range(i, len(masked)):
                if masked[j] == "{":
                    depth += 1
                elif masked[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
            else_block = b[i:j + 1]
            self.assertLess(j, post, "guard 的 else 區塊應在 Notifier.post 之前結束")
            self.assertRegex(else_block, r"\b(exit\(|return\b)", "guard 的 else 區塊應以 exit／return 離開")
            self.assertNotIn("Notifier.post(", else_block, "guard 的 else 區塊不得發通知")

    def test_skip_branch_does_not_run_finalizer(self):
        src = code(self, RECORDING_SESSION)
        bodies = sr.swift_functions(src).get("beginFinalize", [])
        self.assertEqual(len(bodies), 1, "應恰有一個 beginFinalize")
        b = bodies[0]
        skip = re.search(r"\bif\s+ctx\.skipFinalize\b", b)
        self.assertIsNotNone(skip, "beginFinalize 應在帶 --skip-finalize 時另走跳過收尾的分支")
        self.assertLess(skip.start(), b.find("FinalizeRunner("), "跳過收尾的判斷應早於建立 FinalizeRunner")


if __name__ == "__main__":
    unittest.main()

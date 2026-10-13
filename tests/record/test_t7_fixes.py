"""t7 實機驗收發現的修正（spec §6 第 102–106 條）：實作形狀的靜態檢查。

行為面（通知內文、瀏海判定、mic_rms 降級）由 Swift 測試 T7Tests.swift、PreflightTests.swift 涵蓋。
"""
import re
import unittest

from tests.record import test_r2_static as r2
from tests.record import test_static_rules as sr

PREFLIGHT_RUNNER = r2.CAPTURE / "PreflightRunner.swift"


def src(path):
    return sr.strip_swift_comments(path.read_text(encoding="utf-8"))


class T7Fixes(unittest.TestCase):
    # §6 第 102 條：麥克風安靜只提醒、不擋開錄
    def test_mic_rms_quiet_is_warn_only(self):
        code = src(PREFLIGHT_RUNNER)
        self.assertRegex(code, r"(?s)PreflightResult\(\s*item:\s*\.mic_rms,\s*ok:\s*false,.{0,400}?warnOnly:\s*true\)",
                         "麥克風安靜時應以 PreflightResult(item: .mic_rms, …, warnOnly: true) 回報")
        self.assertIn("15 秒", code)
        self.assertNotIn("檢查時請對麥克風說一句話", code)

    # §6 第 103 條：從系統的畫面錄製指示停止＝一般停止
    def test_user_stopped_stream_is_normal_stop(self):
        code = src(r2.RECORDING_SESSION)
        self.assertIn("SCStreamError.Code.userStopped", code)
        m = re.search(r"didStopWithError error: Error\)\s*\{(.*?)\n    \}", code, re.S)
        self.assertIsNotNone(m, "找不到 didStopWithError")
        body = m.group(1)
        i_user = body.find("isUserStoppedStream(error)")
        i_forced = body.find("self.forced")
        self.assertGreaterEqual(i_user, 0, "didStopWithError 應先判斷 isUserStoppedStream")
        self.assertLess(i_user, i_forced, "userStopped 判斷應在設定 forced（結束碼 5）之前")
        branch = body[i_user:body.find("return", i_user) + len("return")]
        self.assertIn("return", branch, "userStopped 分支應直接 return，不設 hadError／forced")
        self.assertNotIn("hadError", branch)

    # §6 第 104 條：⌘W 以實體鍵碼判斷（中文輸入法）
    def test_preferences_cmd_w_uses_key_code(self):
        code = src(r2.PREFERENCES)
        self.assertIn("event.keyCode == preferencesCloseKeyCode", code)
        self.assertRegex(code, r"preferencesCloseKeyCode:\s*UInt16\s*=\s*13\b")

    # §6 第 105 條：快捷鍵送出控制後發通知回饋
    def test_hotkey_feedback_notification(self):
        code = src(r2.MENUBAR)
        self.assertIn("controlFeedback(cmd, markerSeq: written.markerSeq)", code)
        for action in ("mute", "pause", "mark"):
            self.assertRegex(code, rf'action:\s*"{action}",\s*feedback:\s*true',
                             f"快捷鍵 {action} 應帶 feedback: true")

    # §6 第 106 條：錄製中檢查圖示是否被瀏海擋住
    def test_status_item_obscured_check(self):
        code = src(r2.MENUBAR)
        self.assertIn("statusItemObscured(", code)
        self.assertIn("auxiliaryTopLeftArea", code)
        self.assertIn("occlusionState", code)

    # §6 第 108 條：自動前處理經登入 shell 跑，PATH 才有使用者裝的 mlx_whisper 等工具
    def test_autoprep_runs_through_login_shell(self):
        code = src(r2.TRIGGER / "Completion.swift")
        self.assertIn('URL(fileURLWithPath: "/bin/zsh")', code)
        self.assertRegex(code, r'p\.arguments\s*=\s*\["-lc",[^\]]*"prep",\s*session\]')

    # §6 第 109 條：record.log 以 O_APPEND 開檔，多個程序同時寫不互相覆蓋
    def test_logger_append_uses_o_append(self):
        code = src(r2.CAPTURE / "Support.swift")
        self.assertIn("O_APPEND", code)
        self.assertNotIn("seekToEndOfFile", code)


if __name__ == "__main__":
    unittest.main()

"""R2 文件（spec §4.24.3）：SKILL.md 說明 R2 功能、README.md 錄製段提到 R2 並指向 SKILL.md。

第一輪 §4.12.6 (d) 的逐行檢查（文件不得寫 spec 沒有的子指令或旗標）由 test_docs.py::test_docs_cli_block_matches_spec 照跑。
"""
import unittest

from tests.record.test_docs import README, SKILL, read, record_section

R2_CONTROLS = ["⌃⌥⌘R", "⌃⌥⌘M", "⌃⌥⌘P", "⌃⌥⌘B", "麥克風靜音", "系統聲音照錄", "暫停", "剪掉", "pauseEvents", "標記",
               "markers.json", "舊版", "./pause"]
R2_MENUBAR = ["錄這個視窗", "存到", "偏好設定", "登入時自動開啟", "停止後自動跑前處理", "預設關", "顯示上一場成品",
              "在 Finder 顯示"]
R2_README = ["⌃⌥⌘P", "麥克風靜音", "markers.json"]


class TestR2Docs(unittest.TestCase):
    # spec §4.24.3：快捷鍵、靜音、暫停、標記、舊版錄製器、保留字
    def test_r2_controls_documented(self):
        text = read(self, SKILL)
        missing = [k for k in R2_CONTROLS if k not in text]
        self.assertEqual(missing, [], f"SKILL.md 應說明 R2 控制功能，缺少：{missing}")

    # spec §4.24.3：選單、偏好設定、自動前處理、完成通知
    def test_r2_menubar_documented(self):
        text = read(self, SKILL)
        missing = [k for k in R2_MENUBAR if k not in text]
        self.assertEqual(missing, [], f"SKILL.md 應說明 R2 選單與偏好設定，缺少：{missing}")

    # spec §4.24.3：README 錄製段含 ⌃⌥⌘P、麥克風靜音、markers.json，並有一行指向 SKILL.md
    def test_r2_readme_mentions(self):
        sec = record_section(read(self, README))
        self.assertIsNotNone(sec, "README 應有「## 錄製會議」段")
        missing = [k for k in R2_README if k not in sec]
        self.assertEqual(missing, [], f"README 錄製段應提到 R2，缺少：{missing}")
        self.assertTrue(any("SKILL.md" in l for l in sec.split("\n")), "README 錄製段應有一行指向 SKILL.md")


if __name__ == "__main__":
    unittest.main()

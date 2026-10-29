"""spec §4.4.6、§4.4.7：tools/merge_gate_project/scan_names.py（由 app-tools 轉綠）。

名稱一律用虛構的範例字串；場次名範例用「[Stand-up] 範例專案」。
"""
import os
import shutil
import unittest

from tests.governance.support import PY, SCAN_NAMES, run, tmpdir

OUTPUTS = {"沒有", "有", "名稱清單讀不到"}
NAME_A = "ExampleClientAlpha"
NAME_B = "範例客戶乙"


def env_without_list(**extra):
    env = {k: v for k, v in os.environ.items() if k != "MH_CLIENT_NAMES_FILE"}
    env.update(extra)
    return env


class ScanNamesTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCAN_NAMES.is_file(), "tools/merge_gate_project/scan_names.py 不存在")
        self.d = tmpdir(self, "mh-scan-")
        self.names = self.d / "names.txt"
        self.names.write_text(f"\n  \n{NAME_A}\n\n{NAME_B}\n", encoding="utf-8")
        self.hit = self.d / "hit.md"
        self.hit.write_text("# [Stand-up] 範例專案\n\n與 exampleclientALPHA 的窗口確認時程。\n", encoding="utf-8")
        self.clean = self.d / "clean.md"
        self.clean.write_text("# [Stand-up] 範例專案\n\n只有一般內容。\n", encoding="utf-8")

    def scan(self, *files, names=None, env=None, script=SCAN_NAMES):
        args = [PY, str(script)] + (["--names-file", str(names)] if names else []) + [str(f) for f in files]
        return run(args, env=env or env_without_list(), cwd=self.d)

    def assert_result(self, r, code, word):
        self.assertEqual(r.returncode, code, f"stdout={r.stdout!r} stderr={r.stderr!r}")
        self.assertEqual(r.stdout.strip(), word)

    def test_exit_codes(self):
        """§4.4.6：沒命中 0「沒有」；命中（不分大小寫）1「有」；清單讀不到或沒有非空行 2「名稱清單讀不到」。"""
        self.assert_result(self.scan(self.clean, names=self.names), 0, "沒有")
        self.assert_result(self.scan(self.hit, names=self.names), 1, "有")
        self.assert_result(self.scan(self.clean, self.hit, names=self.names), 1, "有")
        blank = self.d / "blank.txt"
        blank.write_text("\n   \n\n", encoding="utf-8")
        self.assert_result(self.scan(self.clean, names=blank), 2, "名稱清單讀不到")
        self.assert_result(self.scan(self.clean, names=self.d / "nope.txt"), 2, "名稱清單讀不到")
        # 空白行不能變成「任何內容都命中」
        self.assert_result(self.scan(self.clean, names=self.names), 0, "沒有")

    def test_output_never_leaks(self):
        """§4.4.6：任何情況輸出只有三種字之一，不印名單內容、命中字或命中行。"""
        cases = [self.scan(self.hit, names=self.names), self.scan(self.clean, names=self.names),
                 self.scan(self.clean, names=self.d / "nope.txt")]
        for r in cases:
            self.assertIn(r.stdout.strip(), OUTPUTS)
            both = (r.stdout + r.stderr).lower()
            for s in (NAME_A.lower(), NAME_B, "exampleclientalpha", "窗口確認時程"):
                self.assertNotIn(s, both)

    def test_default_path(self):
        """§4.4.7：沒給 --names-file 時先讀 MH_CLIENT_NAMES_FILE，再讀 <repo 根>/_tpm/runs/client-names.txt。"""
        # 以腳本位置推 repo 根：把腳本複製到暫存的 repo 樹
        root = self.d / "repo"
        (root / "tools" / "merge_gate_project").mkdir(parents=True)
        (root / "_tpm" / "runs").mkdir(parents=True)
        script = root / "tools" / "merge_gate_project" / "scan_names.py"
        shutil.copy2(SCAN_NAMES, script)
        (root / "_tpm" / "runs" / "client-names.txt").write_text(f"{NAME_B}\n", encoding="utf-8")
        only_b = self.d / "only_b.md"
        only_b.write_text(f"提到 {NAME_B}。\n", encoding="utf-8")
        env_list = self.d / "env_names.txt"
        env_list.write_text(f"{NAME_A}\n", encoding="utf-8")

        # 沒有環境變數：讀 repo 根的清單
        self.assert_result(self.scan(only_b, script=script), 1, "有")
        self.assert_result(self.scan(self.hit, script=script), 0, "沒有")
        # 有環境變數：以它為準（repo 根清單不再採用）
        env = env_without_list(MH_CLIENT_NAMES_FILE=str(env_list))
        self.assert_result(self.scan(self.hit, script=script, env=env), 1, "有")
        self.assert_result(self.scan(only_b, script=script, env=env), 0, "沒有")
        # --names-file 優先於環境變數
        self.assert_result(self.scan(only_b, names=root / "_tpm" / "runs" / "client-names.txt", script=script, env=env), 1, "有")
        # repo 根沒有清單、也沒有環境變數：2
        (root / "_tpm" / "runs" / "client-names.txt").unlink()
        self.assert_result(self.scan(self.clean, script=script), 2, "名稱清單讀不到")


if __name__ == "__main__":
    unittest.main()

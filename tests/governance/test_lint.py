"""spec §4.2.1–§4.2.4：bin/_lint.sh（由 lint-fix 轉綠）。

lint 以腳本所在目錄當 BIN、讀 BIN/../config.json，所以行為測試把 _lint.sh 複製到暫存的 bin/ 再跑。
"""
import re
import shutil
import unittest

from tests.governance.support import REPO, run, tmpdir

LINT = REPO / "bin" / "_lint.sh"


def sandbox(tc, files: dict):
    base = tmpdir(tc, "mh-lint-")
    b = base / "bin"
    b.mkdir()
    shutil.copy2(LINT, b / "_lint.sh")
    (b / "ok.py").write_text("print('ok')\n", encoding="utf-8")
    (base / "config.json").write_text("{}\n", encoding="utf-8")
    for name, body in files.items():
        (b / name).write_text(body, encoding="utf-8")
    return b


def lint(b):
    return run(["bash", str(b / "_lint.sh")], cwd=b.parent)


class LintTest(unittest.TestCase):
    def test_detects_fullwidth_after_var(self):
        """§4.2.1：`$名稱` 緊接非 ASCII 字元時回 1，並印出檔名與行號。"""
        clean = sandbox(self, {"good.sh": '#!/usr/bin/env bash\nf=x\necho "${f}：好"\n'})
        r0 = lint(clean)
        self.assertEqual(r0.returncode, 0, f"乾淨的暫存 bin 應回 0：{r0.stdout}{r0.stderr}")
        b = sandbox(self, {"bad.sh": '#!/usr/bin/env bash\necho "$f：壞"\n'})
        r = lint(b)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 1, f"應回 1：{out}")
        self.assertIn("bad.sh", out)
        self.assertRegex(out, r"(^|[:\s])2[:：]", "要印出命中的行號 2")

    def test_repo_bin_clean(self):
        """§4.2.2：在本 repo 的 bin/ 上 bash bin/_lint.sh 回 0。"""
        r = run(["bash", str(LINT)], cwd=REPO)
        self.assertEqual(r.returncode, 0, f"{r.stdout[-800:]}{r.stderr[-400:]}")

    def test_no_grep_p(self):
        """§4.2.3：_lint.sh 不含 `grep -P`、`grep -nP`。"""
        src = LINT.read_text(encoding="utf-8")
        self.assertNotIn("grep -P", src)
        self.assertNotIn("grep -nP", src)
        self.assertIsNone(re.search(r"grep\s+-[a-zA-Z]*P", src), "_lint.sh 仍用 grep 的 -P 旗標")

    def test_backtick_check_kept(self):
        """§4.2.4：雙引號字串內含反引號時回 1（既有第 2 項檢查不變）。"""
        b = sandbox(self, {"tick.sh": '#!/usr/bin/env bash\necho "看 `date` 的輸出"\n'})
        r = lint(b)
        self.assertEqual(r.returncode, 1, f"{r.stdout}{r.stderr}")
        self.assertIn("tick.sh", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()

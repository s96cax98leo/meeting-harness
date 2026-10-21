"""R3 文件、捨棄沒有 CLI、R3 檔的客戶名稱掃描（spec §4.34.4、§4.42.6、§4.45.3、§4.46.4）。

客戶名稱清單由 MH_CLIENT_NAMES_FILE 指定（不在 repo 內）；本檔只回報命中的「路徑:行號」，絕不印出清單內容或命中的字。
"""
import os
import subprocess
import unittest
from pathlib import Path

from tests.record._helpers import Sandbox
from tests.record.surface import REPO, SURFACE
from tests.record.test_docs import README, SKILL, read

R2_BASE = "377dd92"
RECORD_SKILL_R3 = ["已有錄製在跑", "pid", "逾時", "取消收尾", "tracks/unreadable/", "meeting sync", "off", "reported",
                   "calibrated", "meeting search", "meeting reminders", "iCloud", "錄製小窗", "捨棄這次錄製", "會議偵測"]


def r3_files():
    """R3 新增或修改的檔：git diff --name-only 377dd92（工作樹）＋未追蹤檔（不含 .gitignore 忽略的）。"""
    def git(*args):
        return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True).stdout

    names = set(git("diff", "--name-only", R2_BASE).splitlines())
    names |= set(git("ls-files", "--others", "--exclude-standard").splitlines())
    return sorted(REPO / n for n in names if n and (REPO / n).is_file())


class TestR3Docs(unittest.TestCase):
    # spec §4.45.3：meeting-record SKILL.md 與 README 說明 R3 的錄製行為與新指令
    def test_record_skill_r3(self):
        for path in (SKILL, README):
            text = read(self, path)
            with self.subTest(doc=path.name):
                missing = [k for k in RECORD_SKILL_R3 if k not in text]
                self.assertEqual(missing, [], f"{path.relative_to(REPO)} 應說明 R3 功能，缺少：{missing}")

    # spec §4.34.4：說明 iCloud 同步會讓內容離開本機與 --dry-run
    def test_reminders_documented(self):
        for path in (SKILL, README):
            text = read(self, path)
            with self.subTest(doc=path.name):
                for k in ("meeting reminders", "iCloud", "--dry-run", "離開本機"):
                    self.assertIn(k, text, f"{path.relative_to(REPO)} 缺少「{k}」")

    # spec §4.42.6：§2.4 封閉清單沒有 discard；meeting record discard 依 R2 規則當成根目錄
    def test_no_discard_cli(self):
        self.assertFalse(any("discard" in f for f in SURFACE.forms), "§2.4 封閉清單不得有 discard")
        sb = Sandbox(self)
        r = sb.meeting("record", "help")
        self.assertEqual(r.returncode, 0)
        self.assertNotIn("discard", r.stdout)
        a = sb.meeting("record", "discard", "--window", "1", "--yes")
        b = sb.meeting("record", "範例不存在的根", "--window", "1", "--yes")
        self.assertEqual(a.returncode, b.returncode, "discard 應與任一個根目錄名稱同樣處理")
        self.assertEqual(a.stderr.replace("discard", "<根>"), b.stderr.replace("範例不存在的根", "<根>"))
        self.assertEqual(sb.read_calls(), [], "不得呼叫 app")

    # spec §4.46.4：R3 新增或修改的檔都不得含 client-names.txt 的名稱（沒有清單時 skip）
    def test_no_client_names_in_r3_files(self):
        path = os.environ.get("MH_CLIENT_NAMES_FILE")
        if not path:
            self.skipTest("未設定 MH_CLIENT_NAMES_FILE，略過客戶名稱檢查")
        p = Path(path)
        self.assertTrue(p.is_file(), "MH_CLIENT_NAMES_FILE 指向的清單檔不存在")
        names = [s.strip().casefold() for s in p.read_text(encoding="utf-8").splitlines()
                 if s.strip() and not s.strip().startswith("#")]
        self.assertTrue(names, "名稱清單沒有任何有效行")
        files = r3_files()
        self.assertTrue(files, "前提：應有 R3 新增或修改的檔")
        hits = []
        for f in files:
            if f.resolve() == p.resolve():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                text = f.read_bytes().decode("utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                low = line.casefold()
                if any(n in low for n in names):
                    hits.append(f"{f.relative_to(REPO)}:{i}")
        self.assertEqual(hits, [], "R3 檔含客戶名稱（只列路徑:行號）")


if __name__ == "__main__":
    unittest.main()

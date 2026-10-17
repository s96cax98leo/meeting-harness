"""R3x 文件（spec R3x §4.56.1）：meeting-record SKILL.md 與 README.md 說明背景收尾與 MH_FINALIZE_JOBS。

record-cli 區塊維持 12 個寫法（§4.45.1）由既有 test_docs、test_r2_docs、test_r3_docs 驗，本檔不重複、也不改它們。
"""
import unittest

from tests.record.surface import REPO
from tests.record.test_docs import README, SKILL, read

R3X_DOC_TERMS = ["背景收尾", "MH_FINALIZE_JOBS"]


class TestR3xDocs(unittest.TestCase):
    # spec §4.56.1：兩檔都含「背景收尾」與 MH_FINALIZE_JOBS
    def test_docs_mention_background_finalize(self):
        for path in (SKILL, README):
            text = read(self, path)
            with self.subTest(doc=path.name):
                missing = [k for k in R3X_DOC_TERMS if k not in text]
                self.assertEqual(missing, [], f"{path.relative_to(REPO)} 應說明 R3x 的背景收尾與收尾平行度，缺少：{missing}")


if __name__ == "__main__":
    unittest.main()

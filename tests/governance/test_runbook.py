"""spec §4.6.5：specs/auto-merge/runbook.md（由 runbook 轉綠）。

結構約定（讓「每步寫四項」可機械判定）：design §6 上線順序的每一步是一個 2–4 級標題，標題含「第 N 步」（N＝1–8）；
該步的段落（到下一步的標題為止）要寫「誰做」「指令或畫面路徑」「讀回方式」「是否不可逆」四項。
"""
import re
import unittest

from tests.governance.support import REPO

RUNBOOK = REPO / "specs" / "auto-merge" / "runbook.md"
STEP = re.compile(r"^#{2,4} .*第\s*([1-8])\s*步")
FIELDS = ("誰做", "指令或畫面路徑", "讀回方式", "是否不可逆")
ORDER = ["1", "2", "3", "4", "11", "5", "6", "7", "8", "12", "9", "10", "13"]


class RunbookTest(unittest.TestCase):
    def test_sections(self):
        self.assertTrue(RUNBOOK.is_file(), "specs/auto-merge/runbook.md 不存在")
        text = RUNBOOK.read_text(encoding="utf-8")
        lines = text.splitlines()
        starts = [(i, int(m.group(1))) for i, ln in enumerate(lines) if (m := STEP.match(ln))]
        self.assertEqual([n for _, n in starts], list(range(1, 9)), "要有第 1–8 步的標題，且依序各一次")
        bounds = [i for i, _ in starts] + [len(lines)]
        for k, (i, n) in enumerate(starts):
            end = bounds[k + 1]
            for j in range(i + 1, bounds[k + 1]):
                if re.match(r"^#{1,4} ", lines[j]) and (len(lines[j]) - len(lines[j].lstrip("#"))) <= (len(lines[i]) - len(lines[i].lstrip("#"))):
                    end = j
                    break
            body = "\n".join(lines[i:end])
            for f in FIELDS:
                self.assertIn(f, body, f"第 {n} 步缺「{f}」")
        headings = [ln for ln in lines if ln.startswith("#")]
        for words in (("凍結", "解凍"), ("私鑰外洩",), ("交人合併",)):
            self.assertTrue(any(all(w in h for w in words) for h in headings), f"缺「{'與'.join(words)}」程序段（標題）")
        for s in ("待閘門 2", "重新決定", "推論"):
            self.assertNotIn(s, text)
        # G8 段照 spec §4.7 開頭「執行順序」表（plan §2 runbook 完成條件），不照條號數字
        pos = [(m.start() if (m := re.search(r"§4[.]7[.]" + x + r"(?![0-9])", text)) else -1) for x in ORDER]
        self.assertNotIn(-1, pos, "§4.7.1–§4.7.13 每條都要出現")
        self.assertEqual(pos, sorted(pos), "§4.7 條號第一次出現的位置要照執行順序表")
        self.assertIn("Claude Code 以外的終端機", text, "§4.7.8 要寫明由使用者在 Claude Code 以外的終端機執行")


if __name__ == "__main__":
    unittest.main()

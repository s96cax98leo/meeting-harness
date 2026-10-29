"""spec §4.1.5、§4.1.8 前半、§4.6.1–§4.6.4、§4.6.6：規則文字（由 rules-merge 轉綠）。"""
import re
import unittest

from tests.governance.support import GUARD_CONFIG_NAME, PY, REPO, TOOLS_DIR, read, run, section

RULE_START = re.compile(r"^(\d+)\. ")


def rules_md() -> str:
    return read(".claude/teams/rules.md")


def general_rule(n: int) -> str:
    """「## 通用規則」段的第 n 條：從 `n. ` 開頭的行到下一條、標題或分隔線之前。"""
    out, inside = [], False
    for ln in section(rules_md(), "## 通用規則").splitlines():
        m = RULE_START.match(ln)
        if m:
            if inside:
                break
            inside = int(m.group(1)) == n
        elif inside and (ln.startswith("#") or ln.strip() == "---"):
            break
        if inside:
            out.append(ln)
    return "\n".join(out)


def auto_merge_entry() -> str:
    """〈專案規則〉中以 `- **自動合併（auto_merge）**` 開頭的條目（含縮排的續行，到下一個同層條目為止）。"""
    out, inside = [], False
    for ln in section(rules_md(), "## 專案規則").splitlines():
        if ln.startswith("- **自動合併（auto_merge）**"):
            inside = True
        elif inside and (ln.startswith("- ") or ln.startswith("#")):
            break
        if inside:
            out.append(ln)
    return "\n".join(out)


class RulesMergeTest(unittest.TestCase):
    def test_general_rules_merged(self):
        """§4.1.5：通用規則照 spec §6 第 1 條的處置表合回。"""
        r1, r2, r3, r16, r24 = (general_rule(n) for n in (1, 2, 3, 16, 24))
        self.assertIn("本專案目前沒有上游 repo", r1, "規則 1")
        for s in ("public", "當下同意", "publish.py", "publisher"):
            self.assertIn(s, r2, f"規則 2 缺「{s}」")
        self.assertIn("push、開 PR", r3, "規則 3")
        self.assertIn("四個閘門都要使用者核准", r16, "規則 16")
        self.assertIn("不用 `--by policy`", r16, "規則 16")
        self.assertIn("合併通道裡不確定就 hold", r24, "規則 24")
        text = rules_md()
        for s in ("guard-paths.sh", "guard-bash.sh", "check-envelope.sh", "{{"):
            self.assertNotIn(s, text, f"rules.md 不應含「{s}」")

    def test_rule6(self):
        """§4.6.1：規則 6 寫明核准一律不做、合併只在 enabled 為 true 時由 steward 在 gate 判 merge 後執行、其餘由人合併、指向〈專案規則〉。"""
        r6 = general_rule(6)
        self.assertTrue(r6, "找不到規則 6")
        for s in ("核准", "auto_merge.enabled", "agent-workflow:dev-merge-steward", "由人合併", "自動合併（auto_merge）"):
            self.assertIn(s, r6, f"規則 6 缺「{s}」")
        self.assertRegex(r6, r"gate[^。\n]*merge", "規則 6 要寫明 gate 判 merge 後才合併")

    def test_auto_merge_project_rule(self):
        """§4.6.2：〈專案規則〉的「自動合併（auto_merge）」條目含核准紀錄與營運規則。"""
        e = auto_merge_entry()
        self.assertTrue(e, "〈專案規則〉沒有以 `- **自動合併（auto_merge）**` 開頭的條目")
        for s in ("使用者", "2026-10-28", "medium",
                  "GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger",
                  "只有主 session 執行 `gh_app_token.py`",
                  "~/.config/meeting-harness/gh/", "agent 不讀",
                  "scan_names.py", "tests/governance", "bypass", "suspend", "不自動 pull",
                  "merge-audit.jsonl", "CI 綠不等於 verify 綠",
                  "沒有自己 spec 的 bugfix PR 以 `Spec-Epic` 指向它修的 epic，需求為該 epic 全部條目"):
            self.assertIn(s, e, f"自動合併條目缺「{s}」")

    def test_main_session_no_direct_edit(self):
        """§4.6.6：自動合併條目逐字含「主 session 也不直接改守門設定…」那一句。"""
        n = GUARD_CONFIG_NAME
        sentence = (f"`auto_merge.enabled` 為 true 後，主 session 也不直接改 `{n}`、`merge-audit.jsonl`、"
                    f"`publish-audit.jsonl`；要改 `{n}` 一律走 PR 與 code owner 核准。")
        self.assertIn(sentence, auto_merge_entry())

    def test_claude_md_irreversible(self):
        """§4.6.3：CLAUDE.md「## 不可逆節點」改寫：不再是「不合併」，合併只由 steward 在 enabled 且 gate 判 merge 時執行。"""
        sec = section(read("CLAUDE.md"), "## 不可逆節點")
        self.assertTrue(sec.strip(), "CLAUDE.md 沒有「## 不可逆節點」段")
        self.assertNotIn("agent 不推送、不合併、不 approve", sec)
        self.assertNotIn("`main` 未受保護", sec)
        for s in ("不推送", "不 approve", "steward", "auto_merge.enabled", "gate"):
            self.assertIn(s, sec, f"不可逆節點段缺「{s}」")
        self.assertRegex(sec, r"gate[^。\n]*merge", "要寫明 gate 判 merge 時才合併")

    def test_claude_md_import(self):
        """§4.1.8 前半：CLAUDE.md 有一行 `@.claude/teams/agent-workflow.CLAUDE.md`，且該檔存在。"""
        self.assertIn("@.claude/teams/agent-workflow.CLAUDE.md", read("CLAUDE.md").splitlines())
        self.assertTrue((REPO / ".claude/teams/agent-workflow.CLAUDE.md").is_file())

    def test_check_rules(self):
        """§4.6.4：check_rules.py 回 0（帶三份規則文件檢查）；三份文件不含 `{{`。"""
        files = (".claude/teams/rules.md", "CLAUDE.md", ".claude/teams/README.md")
        r = run([PY, str(TOOLS_DIR / "check_rules.py"), *[str(REPO / f) for f in files]], cwd=REPO)
        self.assertEqual(r.returncode, 0, f"check_rules.py exit {r.returncode}：{r.stdout[-600:]}")
        for f in files:
            self.assertNotIn("{{", read(f), f"{f} 含未替換的 {{{{")


if __name__ == "__main__":
    unittest.main()

"""升級當下才成立的驗收（spec §4.1.3、§4.1.4、§4.1.7、§4.1.8 後半、§4.1.9、§4.1.11、§4.5.1）。

以 e72a9cb（升級前的 main）為基準比對合回結果，或斷言 auto_merge.enabled 為 false；
只在 auto-merge epic 驗收時跑，CI 不跑，啟用後必紅（見 README.md）。
"""
import json
import subprocess
import unittest

from tests.governance.support import (AUTO_MERGE_SPEC, GUARD_CONFIG_REL, REPO, guard_config_path, read, section,
                                      strip_notes)

OLD = "e72a9cb"


def old_bytes(rel: str) -> bytes:
    return subprocess.run(["git", "-C", str(REPO), "show", f"{OLD}:{rel}"], capture_output=True, check=True).stdout


def old_text(rel: str) -> str:
    return old_bytes(rel).decode("utf-8")


def missing_lines(old_lines, new_text):
    new = set(new_text.splitlines())
    return [ln for ln in old_lines if ln.strip() and ln not in new]


class UpgradeOnceTest(unittest.TestCase):
    def test_meeting_pipeline_untouched(self):
        """§4.1.3：meeting-pipeline.js 與 e72a9cb 逐位元相同。"""
        rel = ".claude/workflows/meeting-pipeline.js"
        self.assertEqual((REPO / rel).read_bytes(), old_bytes(rel))

    def test_project_rules_kept(self):
        """§4.1.4：e72a9cb 版 rules.md 第 52–68 行的每一行都原文出現在新版「## 專案規則」段內。"""
        old = old_text(".claude/teams/rules.md").splitlines()[51:68]
        self.assertEqual(len(old), 17)
        sec = section(read(".claude/teams/rules.md"), "## 專案規則")
        self.assertTrue(sec.strip(), "新版 rules.md 沒有「## 專案規則」段")
        miss = missing_lines(old, sec)
        self.assertEqual(miss, [], f"專案規則有 {len(miss)} 行沒有原文保留")

    def test_teams_readme_kept(self):
        """§4.1.7：e72a9cb 版 .claude/teams/README.md 中含 meeting 的每一行都原文出現在新版。"""
        old = [ln for ln in old_text(".claude/teams/README.md").splitlines() if "meeting" in ln]
        self.assertTrue(old, "e72a9cb 版 README 沒有含 meeting 的行（基準讀錯）")
        miss = missing_lines(old, read(".claude/teams/README.md"))
        self.assertEqual(miss, [], f"README 有 {len(miss)} 行沒有原文保留：{miss[:3]}")

    def test_claude_md_kept(self):
        """§4.1.8 後半：e72a9cb 版 CLAUDE.md「## 不可逆節點」段以外的每一行都原文保留。"""
        old = old_text("CLAUDE.md")
        irreversible = set(section(old, "## 不可逆節點").splitlines()) | {"## 不可逆節點"}
        keep = [ln for ln in old.splitlines() if ln not in irreversible]
        miss = missing_lines(keep, read("CLAUDE.md"))
        self.assertEqual(miss, [], f"CLAUDE.md 有 {len(miss)} 行沒有原文保留：{miss[:3]}")

    def test_guard_config_preserved(self):
        """§4.1.9：e72a9cb 版守門設定的每個頂層鍵都存在；除 §3 列出的鍵以外值都相同（`_說明` 這類說明鍵不比）。"""
        old = json.loads(old_text(GUARD_CONFIG_REL))
        new = json.loads(guard_config_path().read_text(encoding="utf-8"))
        spec3 = {"protected_branches", "auto_merge", "requirements",
                 "main_session_github_rules", "team_agent_namespaces", "extension_agents"}
        self.assertEqual(sorted(set(old) - set(new)), [], "升級後少了頂層鍵")
        diff = [k for k in strip_notes(old) if k not in spec3 and old[k] != new[k]]
        self.assertEqual(diff, [], f"這些鍵的值被改了：{diff}")

    def test_settings_permissions_kept(self):
        """§4.1.11：.claude/settings.json 的 $schema 相同，permissions.allow／deny 舊元素都在新版。"""
        old = json.loads(old_text(".claude/settings.json"))
        new = json.loads(read(".claude/settings.json"))
        self.assertEqual(new.get("$schema"), old.get("$schema"))
        for key in ("allow", "deny"):
            old_list = (old.get("permissions") or {}).get(key) or []
            new_list = (new.get("permissions") or {}).get(key) or []
            miss = [x for x in old_list if x not in new_list]
            self.assertEqual(miss, [], f"permissions.{key} 少了 {len(miss)} 項")

    def test_auto_merge_values(self):
        """§4.5.1：升級當下 auto_merge 等於 spec §3 的值（enabled 為 false）。"""
        am = json.loads(guard_config_path().read_text(encoding="utf-8")).get("auto_merge")
        self.assertIsInstance(am, dict)
        self.assertEqual(strip_notes(am), AUTO_MERGE_SPEC)
        self.assertIs(am["enabled"], False)


if __name__ == "__main__":
    unittest.main()

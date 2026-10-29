"""spec §4.1.1、§4.5.2、§4.5.7：scaffold 升級後長期成立的部分（由 m-upgrade 轉綠；Red 時就應綠）。"""
import unittest

from tests.governance.support import (AUTO_MERGE_SPEC, PY, REQUIREMENTS_SPEC, TOOLS_DIR, load_guard_config, run,
                                      strip_notes)


class UpgradeTest(unittest.TestCase):
    def test_gate_selftest(self):
        """§4.1.1：tools 有 merge_gate.py、publish.py、checklist.py；merge_gate.py --selftest 回 0 並印「全部通過」。"""
        for name in ("merge_gate.py", "publish.py", "checklist.py"):
            self.assertTrue((TOOLS_DIR / name).is_file(), f".claude/teams/tools/{name} 不存在")
        r = run([PY, str(TOOLS_DIR / "merge_gate.py"), "--selftest"], timeout=300)
        self.assertEqual(r.returncode, 0, f"merge_gate.py --selftest exit {r.returncode}：{r.stdout[-800:]}{r.stderr[-400:]}")
        self.assertIn("全部通過", r.stdout)

    def test_requirements_config(self):
        """§4.5.2：守門設定的 requirements 等於 spec §3 的 command 設定；protected_branches 含 main。"""
        cfg = load_guard_config()
        self.assertIsInstance(cfg.get("requirements"), dict, "守門設定沒有 requirements 物件")
        self.assertEqual(strip_notes(cfg["requirements"]), REQUIREMENTS_SPEC)
        self.assertIn("main", cfg.get("protected_branches") or [])

    def test_auto_merge_shape(self):
        """§4.5.7：auto_merge 含 §3 全部鍵；enabled 是布林（不檢查值）；merge_method、merger_role、repos 照 §3。"""
        am = load_guard_config().get("auto_merge")
        self.assertIsInstance(am, dict, "守門設定沒有 auto_merge 物件")
        missing = sorted(set(AUTO_MERGE_SPEC) - set(am))
        self.assertEqual(missing, [], f"auto_merge 缺鍵：{missing}")
        self.assertIsInstance(am["enabled"], bool)
        self.assertEqual(am["merge_method"], "merge")
        self.assertEqual(am["merger_role"], "agent-workflow:dev-merge-steward")
        self.assertEqual(am["repos"], {"s96cax98leo/meeting-harness": "medium"})


if __name__ == "__main__":
    unittest.main()

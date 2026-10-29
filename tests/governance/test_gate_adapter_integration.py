"""spec §4.3.11：merge_gate.py check 經守門設定的 command 需求來源呼叫 adapter（由 reqs-adapter 轉綠）。

在暫存專案目錄（git repo）放 spec §3 的守門設定與 adapter 副本，再以 --project-dir 指過去跑 gate；
守門設定的檔名與路徑一律從 support 的常數組出（spec §4.2.8）。
"""
import json
import shutil
import unittest

from tests.governance.support import (ADAPTER, AUTO_MERGE_SPEC, GUARD_CONFIG_REL, PY, REQUIREMENTS_SPEC, TOOLS_DIR,
                                      git, git_env, run, tmpdir)

SPEC = """# spec：demo

## 4. 驗收條件

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.1.1 | 甲條文 | G1 | x | y |
"""
SHA_LEN = 40


class GateAdapterIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ADAPTER.is_file(), "tools/merge_gate_project/reqs_from_spec.py 不存在")
        base = tmpdir(self, "mh-gate-")
        self.proj = base / "proj"
        self.proj.mkdir()
        self.env = git_env()
        git(self.proj, "init", "-q", "-b", "main", env=self.env)
        (self.proj / "specs" / "demo").mkdir(parents=True)
        (self.proj / "specs" / "demo" / "spec.md").write_text(SPEC, encoding="utf-8")
        (self.proj / "tools" / "merge_gate_project").mkdir(parents=True)
        shutil.copy2(ADAPTER, self.proj / "tools" / "merge_gate_project" / "reqs_from_spec.py")
        cfg = self.proj / GUARD_CONFIG_REL
        cfg.parent.mkdir(parents=True)
        cfg.write_text(json.dumps({"runs_dir": "_tpm/runs", "protected_branches": ["main"],
                                   "auto_merge": AUTO_MERGE_SPEC, "requirements": REQUIREMENTS_SPEC},
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        (self.proj / "src").mkdir()
        (self.proj / "src" / "a.txt").write_text("v1\n", encoding="utf-8")
        git(self.proj, "add", "-A", env=self.env)
        git(self.proj, "commit", "-q", "-m", "chore: base", env=self.env)
        git(self.proj, "checkout", "-q", "-b", "feature", env=self.env)

    def head(self, msg: str) -> str:
        (self.proj / "src" / "a.txt").write_text(msg, encoding="utf-8")
        git(self.proj, "commit", "-q", "-am", msg, env=self.env)
        sha = git(self.proj, "rev-parse", "HEAD", env=self.env)
        self.assertEqual(len(sha), SHA_LEN)
        return sha

    def gate(self, head: str):
        env = dict(self.env)
        env.update({"AWF_REQ_BASE": "main", "CLAUDE_PROJECT_DIR": str(self.proj)})
        r = run([PY, str(TOOLS_DIR / "merge_gate.py"), "check", "--project-dir", str(self.proj),
                 "--repo", "s96cax98leo/meeting-harness", "--pr", "1", "--head-sha", head, "--no-audit"],
                cwd=self.proj, env=env, timeout=300)
        self.assertIn(r.returncode, (0, 1, 3), f"gate exit {r.returncode}：{r.stderr[-400:]}")
        return r, json.loads(r.stdout)

    def test_gate_reads_adapter(self):
        """requirements_source 以 command 開頭，reasons 不含「需求清單指令」。"""
        head = self.head("feat: 改一點\n\nSpec-Epic: demo\n")
        _, out = self.gate(head)
        self.assertTrue(str(out.get("requirements_source", "")).startswith("command"), out.get("requirements_source"))
        reasons = "\n".join(map(str, out.get("reasons") or []))
        self.assertNotIn("需求清單指令", reasons)

    def test_adapter_failure_holds(self):
        """adapter exit 2（沒有指出 epic）時 gate 判 hold，原因來自需求清單指令。"""
        head = self.head("fix: 沒有 trailer、沒碰 specs\n")
        r, out = self.gate(head)
        self.assertEqual(out.get("decision"), "hold")
        self.assertEqual(r.returncode, 1)
        reasons = "\n".join(map(str, out.get("reasons") or []))
        self.assertIn("需求清單指令 exit 2", reasons)


if __name__ == "__main__":
    unittest.main()

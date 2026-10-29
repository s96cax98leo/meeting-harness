"""spec §4.1.2、§4.1.6、§4.5.3、§4.5.4：methodology.json 與 workflows（由 flow-merge 轉綠）。"""
import json
import os
import re
import shutil
import unittest
from pathlib import Path

from tests.governance.support import PY, REPO, TOOLS_DIR, read, run, tmpdir

WF = REPO / ".claude" / "workflows"
METH_RE = re.compile(r"/\*@methodology\*/ (.*?) /\*@end\*/", re.S)
GUIDANCE_MUST = (
    "GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger",
    "--merge",
    "scan_names.py",
    "agent-merge-gate/decision",
    "--watch",
    "tests/governance",
)


def methodology() -> dict:
    return json.loads(read(".claude/teams/methodology.json"))


def merge_guidance(m: dict) -> str:
    g = ((m.get("stages") or {}).get("merge") or {}).get("guidance")
    return "\n".join(g) if isinstance(g, list) else str(g or "")


class FlowMergeTest(unittest.TestCase):
    def agents_dir(self) -> Path:
        """模版角色定義檔在 agent-workflow plugin（不在本 repo）。

        有 plugin（AWF_PLUGIN_DIR 或 CLAUDE_PLUGIN_ROOT 底下有 agents/）時用它，連定義檔存在與否一起檢查；
        沒有時（例如 CI 容器）在暫存目錄為 workflows 提到的每個 tpm-*／dev-* 角色放一個空的定義檔，
        其餘檢查（meta、schema、乾跑）照常執行。
        """
        for k in ("AWF_PLUGIN_DIR", "CLAUDE_PLUGIN_ROOT"):
            v = os.environ.get(k, "").strip()
            if v and (Path(v) / "agents").is_dir():
                return Path(v) / "agents"
        d = tmpdir(self, "mh-agents-")
        roles = set()
        for f in WF.glob("*.js"):
            roles |= set(re.findall(r"\b((?:tpm|dev)-[a-z][a-z0-9-]*[a-z0-9])\b", f.read_text(encoding="utf-8")))
        for role in roles:
            (d / f"{role}.md").write_text(f"# {role}（測試用的空定義檔）\n", encoding="utf-8")
        return d

    def test_build_check(self):
        """§4.1.2：sdlc-merge.js、event-post-merge.js 存在；build.py --check 回 0。"""
        for name in ("sdlc-merge.js", "event-post-merge.js"):
            self.assertTrue((WF / name).is_file(), f".claude/workflows/{name} 不存在")
        r = run([PY, str(TOOLS_DIR / "build.py"), "--check"])
        self.assertEqual(r.returncode, 0, f"build.py --check exit {r.returncode}：{r.stdout[-600:]}{r.stderr[-400:]}")

    def test_check_workflows(self):
        """§4.1.2：node .claude/teams/tools/check_workflows.mjs 回 0。"""
        node = shutil.which("node")
        self.assertIsNotNone(node, "找不到 node（check_workflows.mjs 需要）")
        r = run([node, str(TOOLS_DIR / "check_workflows.mjs"), "--agents-dir", str(self.agents_dir())], cwd=REPO, timeout=300)
        self.assertEqual(r.returncode, 0, f"check_workflows.mjs exit {r.returncode}：{r.stdout[-800:]}{r.stderr[-400:]}")

    def test_d8_kept(self):
        """§4.1.6：sdlc-build.js 給 implementer 的派工含「不要改 progress.md」，全檔不含「更新 progress.md 對應項」。"""
        src = (WF / "sdlc-build.js").read_text(encoding="utf-8")
        # 不用 assertIn：失敗訊息會把整支 workflow 印進 log
        self.assertTrue("不要改 progress.md" in src, "sdlc-build.js 缺「不要改 progress.md」")
        self.assertFalse("更新 progress.md 對應項" in src, "sdlc-build.js 仍含「更新 progress.md 對應項」")

    def test_merge_guidance(self):
        """§4.5.3：stages.merge.guidance 含本 repo 的合併做法關鍵字。"""
        g = merge_guidance(methodology())
        for s in GUIDANCE_MUST:
            self.assertIn(s, g, f"stages.merge.guidance 缺「{s}」")

    def test_trailer_convention(self):
        """§4.5.4：conventions.commit.format 含 `Spec-Epic: <epic>`。"""
        fmt = str(((methodology().get("conventions") or {}).get("commit") or {}).get("format") or "")
        self.assertIn("Spec-Epic: <epic>", fmt)

    def test_guidance_embedded(self):
        """§4.5.4：sdlc-merge.js 內嵌的 METHODOLOGY 含 §4.5.3 的 guidance 原文。"""
        m = METH_RE.search((WF / "sdlc-merge.js").read_text(encoding="utf-8"))
        self.assertIsNotNone(m, "sdlc-merge.js 沒有 /*@methodology*/ 內嵌標記")
        embedded = json.loads(m.group(1))
        self.assertIsInstance(embedded, dict, "sdlc-merge.js 沒有內嵌 methodology（仍是 null）")
        g = merge_guidance(embedded)
        self.assertEqual(g, merge_guidance(methodology()), "內嵌的 merge guidance 與 methodology.json 不同")
        for s in GUIDANCE_MUST:
            self.assertIn(s, g, f"內嵌的 merge guidance 缺「{s}」")


if __name__ == "__main__":
    unittest.main()

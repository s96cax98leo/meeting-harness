"""spec §4.2.5、§4.2.6、§4.5.5、§4.5.6：.github 底下的靜態檢查（ci.yml、CODEOWNERS 由 ci 轉綠；gate workflow 由 m-upgrade）。

只用標準庫，YAML 以文字規則檢查（不依賴 PyYAML）。
"""
import re
import unittest

from tests.governance.support import GUARD_CONFIG_REL, REPO

GH = REPO / ".github"
CI = GH / "workflows" / "ci.yml"


def ci_text(tc) -> str:
    tc.assertTrue(CI.is_file(), ".github/workflows/ci.yml 不存在")
    return CI.read_text(encoding="utf-8")


def strip_comment(ln: str) -> str:
    return re.sub(r"\s+#.*$", "", ln) if not ln.lstrip().startswith("#") else ""


def block(text: str, key_re: str, indent: int = 0) -> list[str]:
    """`key:` 在指定縮排時，回傳它底下（縮排更深）的非空行；行內值放在第一個元素（以 '=' 開頭）。"""
    lines = [strip_comment(x) for x in text.splitlines()]
    out, inside = [], False
    for ln in lines:
        if not ln.strip():
            continue
        ind = len(ln) - len(ln.lstrip(" "))
        if inside:
            if ind <= indent:
                break
            out.append(ln)
        else:
            m = re.match(rf"^ {{{indent}}}{key_re}\s*:\s*(.*)$", ln)
            if m and ind == indent:
                inside = True
                if m.group(1).strip():
                    out.append("=" + m.group(1).strip())
    return out


def child_keys(lines: list[str]) -> list[str]:
    if not lines or lines[0].startswith("="):
        return []
    base = min(len(x) - len(x.lstrip(" ")) for x in lines)
    return [re.match(r"\s*([^:\s]+)\s*:", x).group(1) for x in lines
            if len(x) - len(x.lstrip(" ")) == base and re.match(r"\s*[^:\s-][^:]*:", x)]


class CiStaticTest(unittest.TestCase):
    def test_ci_shape(self):
        """§4.2.5：觸發、權限、釘版、job 名稱、runner、checkout 設定。"""
        t = ci_text(self)
        on = block(t, r"""(?:on|"on"|'on')""")
        self.assertTrue(on, "ci.yml 沒有 on: 區塊")
        self.assertEqual(sorted(child_keys(on)), ["pull_request", "push"], f"觸發應只有 pull_request 與 push：{on}")
        push = "\n".join(block("\n".join(on), "push", min(len(x) - len(x.lstrip()) for x in on)))
        self.assertRegex(push, r"(?m)branches\s*:\s*(\[\s*['\"]?main['\"]?\s*\]|\n\s*-\s*['\"]?main['\"]?\s*$)",
                         "push 應只限 branches: [main]")
        self.assertNotRegex(push, r"branches\s*:\s*\[[^\]]*,", "push 的 branches 應只有 main")
        for s in ("pull_request_target", "secrets.", "MH_CLIENT_NAMES_FILE", "meeting.sh", "doctor", "swift", "mlx"):
            self.assertNotIn(s, t, f"ci.yml 不應含「{s}」")
        perms = [ln.strip() for ln in t.splitlines() if re.match(r"\s*permissions\s*:", strip_comment(ln))]
        self.assertTrue(perms, "ci.yml 沒有 permissions")
        top = block(t, "permissions")
        self.assertEqual([x.strip() for x in top], ["contents: read"], f"permissions 應只有 contents: read：{top}")
        for ind in sorted({len(ln) - len(ln.lstrip(" ")) for ln in t.splitlines() if re.match(r"\s+permissions\s*:", ln)}):
            sub = block(t, "permissions", ind)
            self.assertEqual([x.strip() for x in sub], ["contents: read"], f"job 層 permissions 也只能是 contents: read：{sub}")
        uses = re.findall(r"^\s*-?\s*uses\s*:\s*(\S+)", t, re.M)
        self.assertTrue(uses, "ci.yml 沒有 uses:")
        for u in uses:
            self.assertRegex(u, r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$", f"uses 要以 40 碼 SHA 釘版：{u}")
        self.assertRegex(t, r"(?m)^\s+name\s*:\s*['\"]?ci-ubuntu-subset['\"]?\s*$", "job 的 name 應為 ci-ubuntu-subset")
        runs_on = re.findall(r"(?m)^\s+runs-on\s*:\s*['\"]?(\S*)", t)
        self.assertTrue(runs_on, "ci.yml 沒有 runs-on")
        for v in runs_on:
            self.assertTrue(v.startswith("ubuntu-"), f"runs-on 應以 ubuntu- 開頭：{v}")
        self.assertRegex(t, r"(?m)^\s+fetch-depth\s*:\s*0\s*$")
        self.assertRegex(t, r"(?m)^\s+persist-credentials\s*:\s*false\s*$")
        self.assertTrue(any("actions/checkout@" in u for u in uses), "要用 actions/checkout")

    def test_subset_excludes_name_tests(self):
        """§4.2.6：依序 lint → governance → tests.record 明確模組清單；不含 governance_once 與讀名稱清單的模組。"""
        t = ci_text(self)
        self.assertNotIn("governance_once", t)
        a = t.find("bash bin/_lint.sh")
        b = t.find("python3 -m unittest discover -s tests/governance -t .")
        c = t.find("python3 -m unittest tests.record.")
        self.assertTrue(a >= 0 and b >= 0 and c >= 0, "三條指令要都在 ci.yml")
        self.assertTrue(a < b < c, "三條指令要依序：lint、governance、tests.record 子集")
        mods = re.findall(r"tests\.record\.([A-Za-z0-9_]+)", t[c:])
        self.assertTrue(mods, "tests.record 模組清單是空的")
        for m in mods:
            self.assertNotIn(m, ("test_ms_docs", "test_r3_docs"))
            f = REPO / "tests" / "record" / f"{m}.py"
            self.assertTrue(f.is_file(), f"清單裡的模組不存在：{m}")
            self.assertNotIn("MH_CLIENT_NAMES_FILE", f.read_text(encoding="utf-8"), f"{m} 會讀名稱清單，不能進 CI")

    def test_gate_workflow_present(self):
        """§4.5.5：agent-merge-gate.yml 存在、含 pull_request_target 與 agent-merge-gate/decision、沒有未替換的模版佔位。

        GitHub Actions 的運算式一律寫成 `${{ … }}`，所以「不含 `{{`」以「`{{` 前面不是 `$`」判定（未替換的 init 佔位）。
        """
        p = GH / "workflows" / "agent-merge-gate.yml"
        self.assertTrue(p.is_file(), ".github/workflows/agent-merge-gate.yml 不存在")
        t = p.read_text(encoding="utf-8")
        self.assertIn("pull_request_target", t)
        self.assertIn("agent-merge-gate/decision", t)
        self.assertIsNone(re.search(r"(?<!\$)\{\{", t), "agent-merge-gate.yml 有未替換的 {{…}} 佔位")

    def test_codeowners(self):
        """§4.5.6：CODEOWNERS 恰五條、擁有者都是 @s96cax98leo、沒有萬用路徑；第一條是守門設定。"""
        p = GH / "CODEOWNERS"
        self.assertTrue(p.is_file(), ".github/CODEOWNERS 不存在")
        entries = [ln.split() for ln in p.read_text(encoding="utf-8").splitlines()
                   if ln.strip() and not ln.lstrip().startswith("#")]
        want = ["/" + GUARD_CONFIG_REL, "/.claude/teams/tools/", "/.claude/hooks/", "/.github/", "/tools/merge_gate_project/"]
        self.assertEqual(len(entries), 5, f"CODEOWNERS 應恰有 5 條：{[e[0] for e in entries]}")
        self.assertEqual(entries[0][0], "/" + GUARD_CONFIG_REL, "第一條應是守門設定")
        self.assertEqual(sorted(e[0] for e in entries), sorted(want))
        for e in entries:
            self.assertEqual(e[1:], ["@s96cax98leo"], f"{e[0]} 的擁有者應只有 @s96cax98leo")
            self.assertNotIn("*", e[0])
            self.assertNotEqual(e[0], "/")


if __name__ == "__main__":
    unittest.main()

"""spec §4.3.1–§4.3.10、§4.3.12、§4.3.13：requirements adapter tools/merge_gate_project/reqs_from_spec.py（由 reqs-adapter 轉綠）。

每個測試在暫存目錄建 git repo（main＝base，feature＝PR head），以 cwd＝暫存 repo 執行 adapter；
§4.3.9 用 git alternates 借本 repo 的物件、在暫存 repo 疊一個帶 trailer 的空 commit，不改本 repo、不連網路。
"""
import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.governance.support import ADAPTER, FAKES, PY, REPO, git, git_env, run, tmpdir

REAL_SPECS_BASE = "e72a9cb"
ROW = re.compile(r"^\|\s*(\d+(?:\.\d+)+[a-z]?)\s*\|")

DEMO_SPEC = """# spec：demo

## 1. 範圍

- 只是測試用的範例 spec（[Stand-up] 範例專案）。

## 4. 驗收條件

### 4.1 一般

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.1.1 | 甲條文 | G1 | x | y |
| 4.1.2 | 乙條文 | G1 | x | y |

## 6. 整合修訂與例外

| 第 n 條 | 原條文 | 修訂 | 理由 | 核准 |
|---|---|---|---|---|
| 1 | 原本的說法 | 修訂 §4.1.2 的內容 | 理由文字 | 使用者 |
"""

OTHER_SPEC = """# spec：other

## 4. 驗收條件

| # | 條文 |
|---|---|
| 4.1.1 | 別的 epic |
"""


class Repo:
    """暫存 git repo：main 上放 specs，feature 從 main 開。"""

    def __init__(self, tc, files: dict | None = None):
        self.tc = tc
        self.base = tmpdir(tc, "mh-reqs-")
        self.path = self.base / "repo"
        self.path.mkdir()
        self.tmp = self.base / "tmp"
        self.tmp.mkdir()
        self.env = git_env()
        self.git("init", "-q", "-b", "main")
        self.write(files if files is not None else {"specs/demo/spec.md": DEMO_SPEC, "specs/other/spec.md": OTHER_SPEC,
                                                     "src/app.txt": "v1\n"})
        self.commit("chore: base")
        self.main = self.git("rev-parse", "main")
        self.git("checkout", "-q", "-b", "feature")

    def git(self, *args):
        return git(self.path, *args, env=self.env)

    def write(self, files: dict):
        for rel, body in files.items():
            p = self.path / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")

    def commit(self, msg: str, files: dict | None = None, allow_empty=False) -> str:
        if files:
            self.write(files)
        self.git("add", "-A")
        msg_file = self.base / "msg.txt"
        msg_file.write_text(msg, encoding="utf-8")
        self.git("commit", "-q", "-F", str(msg_file), *(["--allow-empty"] if allow_empty else []))
        msg_file.unlink()
        return self.git("rev-parse", "HEAD")

    def adapter(self, head: str, base: str | None = "main", drop=(), path_prefix: str | None = None, **extra):
        env = dict(self.env)
        env.update({"AWF_REPO": "s96cax98leo/meeting-harness", "AWF_PR": "7", "AWF_HEAD_SHA": head, "TMPDIR": str(self.tmp)})
        if base is not None:
            env["AWF_REQ_BASE"] = base
        for k in drop:
            env.pop(k, None)
        if path_prefix:
            env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
        env.update(extra)
        return run([PY, str(ADAPTER)], cwd=self.path, env=env)


def trailer(epic: str, *more: str) -> str:
    return "feat: 改一點東西\n\n內文。\n\n" + "\n".join([f"Spec-Epic: {epic}", *more,
                                                     "Co-Authored-By: Example <noreply@example.invalid>"]) + "\n"


class ReqsFromSpecTest(unittest.TestCase):
    def setUp(self):
        self.assertTrue(ADAPTER.is_file(), "tools/merge_gate_project/reqs_from_spec.py 不存在")

    def ok(self, r) -> dict:
        self.assertEqual(r.returncode, 0, f"adapter 應 exit 0：stderr={r.stderr[-400:]!r}")
        return json.loads(r.stdout)

    def fail2(self, r, word: str | None = None):
        self.assertEqual(r.returncode, 2, f"adapter 應 exit 2：rc={r.returncode} stdout={r.stdout[:200]!r} stderr={r.stderr[-300:]!r}")
        if word:
            self.assertIn(word, r.stderr)
        self.assertLessEqual(len(r.stderr.strip()), 300, "stderr 原因應 ≤300 字")

    def test_trailer_resolves(self):
        """§4.3.1：commit 帶 Spec-Epic trailer、base 有該 spec → exit 0，輸出 §2.1 的 JSON。"""
        repo = Repo(self)
        head = repo.commit(trailer("demo"), {"src/app.txt": "v2\n"})
        out = self.ok(repo.adapter(head))
        self.assertEqual(sorted(out), ["base", "epic", "requirements"])
        self.assertEqual(out["epic"], "demo")
        self.assertEqual(out["base"], repo.main)
        self.assertRegex(out["base"], r"^[0-9a-f]{40}$")
        self.assertEqual([r["id"] for r in out["requirements"]], ["4.1.1", "4.1.2"])
        self.assertEqual(out["requirements"][0]["text"], "甲條文 | G1 | x | y")
        for r in out["requirements"]:
            self.assertEqual(sorted(r), ["id", "source", "text"])

    def test_diff_path_resolves(self):
        """§4.3.2：沒有 trailer、diff 只碰到一個 specs/<e>/（specs/_templates 不算）→ 解析出 <e>。"""
        repo = Repo(self)
        head = repo.commit("docs: 補筆記\n", {"specs/demo/notes.md": "筆記\n", "specs/_templates/x.md": "範本\n"})
        out = self.ok(repo.adapter(head))
        self.assertEqual(out["epic"], "demo")
        self.assertEqual([r["id"] for r in out["requirements"]], ["4.1.1", "4.1.2"])

    def test_zero_or_many_epics(self):
        """§4.3.3：候選 0 個 → exit 2「沒有指出 epic」；2 個以上 → exit 2「多個 epic」。"""
        repo = Repo(self)
        head = repo.commit("fix: 小修\n", {"src/app.txt": "v2\n"})
        self.fail2(repo.adapter(head), "沒有指出 epic")
        head2 = repo.commit(trailer("demo"), {"specs/other/notes.md": "筆記\n"})
        self.fail2(repo.adapter(head2), "多個 epic")

    def test_reads_base_not_head(self):
        """§4.3.4：spec 不在 base → exit 2「不在 base」；PR head 改了 base 已有的 spec → 輸出 base 版本。"""
        repo = Repo(self)
        head = repo.commit(trailer("newepic"), {"specs/newepic/spec.md": DEMO_SPEC.replace("demo", "newepic")})
        self.fail2(repo.adapter(head), "不在 base")
        repo2 = Repo(self)
        changed = DEMO_SPEC.replace("甲條文", "被 PR 改過的條文").replace(
            "| 4.1.2 | 乙條文 | G1 | x | y |", "| 4.1.2 | 乙條文 | G1 | x | y |\n| 4.1.3 | PR 新增的條文 | G1 | x | y |")
        head2 = repo2.commit(trailer("demo"), {"specs/demo/spec.md": changed})
        out = self.ok(repo2.adapter(head2))
        self.assertEqual([r["id"] for r in out["requirements"]], ["4.1.1", "4.1.2"])
        self.assertTrue(out["requirements"][0]["text"].startswith("甲條文"))

    def test_missing_objects(self):
        """§4.3.5：head 不是本機 commit、base 解析不出、必填環境變數缺漏 → exit 2。"""
        repo = Repo(self)
        head = repo.commit(trailer("demo"), {"src/app.txt": "v2\n"})
        self.fail2(repo.adapter("0123456789abcdef0123456789abcdef01234567"))
        self.fail2(repo.adapter(head, base="refs/heads/no-such-branch"))
        self.fail2(repo.adapter(head, base=None))  # 預設 origin/main：暫存 repo 沒有 remote
        for k in ("AWF_REPO", "AWF_PR", "AWF_HEAD_SHA"):
            with self.subTest(missing=k):
                self.fail2(repo.adapter(head, drop=(k,)))

    def test_no_network_git(self):
        """§4.3.5：PATH 前置記錄參數的替身 git 時，沒有任何一次子指令是 fetch、pull、clone、remote。"""
        repo = Repo(self)
        head = repo.commit(trailer("demo"), {"src/app.txt": "v2\n"})
        bin_dir = repo.base / "fakebin"
        bin_dir.mkdir()
        shutil.copy2(FAKES / "git", bin_dir / "git")
        log = repo.base / "git.log"
        real = shutil.which("git")
        extra = {"FAKE_GIT_LOG": str(log), "FAKE_GIT_REAL": real}
        self.ok(repo.adapter(head, path_prefix=str(bin_dir), **extra))
        self.fail2(repo.adapter(head, base="refs/heads/no-such-branch", path_prefix=str(bin_dir), **extra))
        repo.git("checkout", "-q", "-b", "no-epic", "main")
        no_epic = repo.commit("fix: 沒有 epic\n", {"src/app.txt": "v3\n"})
        self.fail2(repo.adapter(no_epic, path_prefix=str(bin_dir), **extra))
        self.assertTrue(log.is_file(), "adapter 沒有經 PATH 上的 git 執行（替身沒有紀錄）")
        calls = [json.loads(ln) for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertTrue(calls)
        for argv in calls:
            sub = subcommand(argv)
            self.assertNotIn(sub, ("fetch", "pull", "clone", "remote"), f"adapter 執行了 git {sub}")

    def test_round_selection(self):
        """§4.3.6：有 `## R<數字>` 時只取最後一個之後第一個含「驗收」的標題段；沒有時取第一個 2–4 級含「驗收」的段。"""
        spec = """# 驗收總覽（一級標題不算）

## 4. 驗收條件

| 4.1.1 | 第一輪 |

## R2 第二輪

### R2-§4 驗收

| 4.20.1 | 第二輪 |

## R3 第三輪

### R3-§4 驗收

| 4.30.1 | 第三輪 |

## R3 補充輪（R3x）

### R3x-§3 設計

| 4.39.1 | 不在驗收段 |

### R3x-§4 驗收

| 4.40.1 | 補充輪甲 |

#### 4.41 實機驗收（更深的標題仍在段內）

| 4.41.1 | 補充輪乙 |

### R3x-§5 影響系統

| 4.49.1 | 段落已結束 |

### R3x-§6 驗收補記（第二個含驗收的段，不取）

| 4.50.1 | 不取 |
"""
        repo = Repo(self, {"specs/demo/spec.md": spec})
        head = repo.commit(trailer("demo"), {"src/x.txt": "x\n"})
        out = self.ok(repo.adapter(head))
        self.assertEqual([r["id"] for r in out["requirements"]], ["4.40.1", "4.41.1"])
        plain = """# 驗收說明（一級，不算）

## 1. 範圍

| 4.0.1 | 不在驗收段 |

### 4. 驗收

| 4.1.1 | 甲 |

#### 4.1 細項

| 4.1.2 | 乙 |

### 5. 其他

| 4.9.1 | 不取 |

## 7. 驗收紀錄

| 4.7.1 | 不取 |
"""
        repo2 = Repo(self, {"specs/demo/spec.md": plain})
        head2 = repo2.commit(trailer("demo"), {"src/x.txt": "x\n"})
        out2 = self.ok(repo2.adapter(head2))
        self.assertEqual([r["id"] for r in out2["requirements"]], ["4.1.1", "4.1.2"])

    def test_row_filters(self):
        """§4.3.7：排除「（修正輪刪除」「（選做）」開頭的列；條號重複或一條都沒有 → exit 2。"""
        spec = DEMO_SPEC.replace("| 4.1.2 | 乙條文 | G1 | x | y |",
                                 "| 4.1.2 | 乙條文 | G1 | x | y |\n"
                                 "| 4.1.3 | （修正輪刪除：改由 4.1.2 涵蓋） | G1 | x | y |\n"
                                 "| 4.1.4 | （選做）加分項 | G1 | x | y |\n"
                                 "| 4.1.5a | 帶字母的條號 | G1 | x | y |")
        repo = Repo(self, {"specs/demo/spec.md": spec})
        head = repo.commit(trailer("demo"), {"src/x.txt": "x\n"})
        out = self.ok(repo.adapter(head))
        self.assertEqual([r["id"] for r in out["requirements"]], ["4.1.1", "4.1.2", "4.1.5a"])
        dup = DEMO_SPEC.replace("| 4.1.2 | 乙條文 |", "| 4.1.1 | 乙條文 |")
        repo2 = Repo(self, {"specs/demo/spec.md": dup})
        self.fail2(repo2.adapter(repo2.commit(trailer("demo"), {"src/x.txt": "x\n"})))
        empty = "# spec\n\n## 4. 驗收條件\n\n（還沒寫）\n\n## 5. 其他\n\n| 4.1.1 | 不在驗收段 |\n"
        repo3 = Repo(self, {"specs/demo/spec.md": empty})
        self.fail2(repo3.adapter(repo3.commit(trailer("demo"), {"src/x.txt": "x\n"})))

    def test_exception_pointer(self):
        """§4.3.8：「整合修訂與例外」段的表格列提到 §<條號> 時，該條 text 附指標，不抄該列內容。"""
        repo = Repo(self)
        head = repo.commit(trailer("demo"), {"src/x.txt": "x\n"})
        out = self.ok(repo.adapter(head))
        reqs = {r["id"]: r for r in out["requirements"]}
        line = 1 + DEMO_SPEC.splitlines().index("| 1 | 原本的說法 | 修訂 §4.1.2 的內容 | 理由文字 | 使用者 |")
        self.assertTrue(reqs["4.1.2"]["text"].endswith(f"〔整合修訂與例外第 1 條提到本條，見 specs/demo/spec.md:{line}〕"),
                        reqs["4.1.2"]["text"])
        self.assertTrue(reqs["4.1.2"]["text"].startswith("乙條文"))
        self.assertNotIn("理由文字", reqs["4.1.2"]["text"])
        self.assertNotIn("原本的說法", reqs["4.1.2"]["text"])
        self.assertNotIn("〔", reqs["4.1.1"]["text"])

    def test_real_specs(self):
        """§4.3.9：以 AWF_REQ_BASE=REAL_SPECS_BASE 讀本 repo 的 meeting-speed 與 meeting-record。"""
        base_spec = subprocess.run(["git", "-C", str(REPO), "show", f"{REAL_SPECS_BASE}:specs/meeting-speed/spec.md"],
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout
        sec, inside = [], False
        for ln in base_spec.splitlines():
            if ln.startswith("## "):
                inside = ln.startswith("## 4. 驗收條件")
                continue
            if inside:
                sec.append(ln)
        rows = [ln for ln in sec if ROW.match(ln)]
        self.assertGreater(len(rows), 2)

        speed = self.ok(self.real_run("meeting-speed"))
        ids = [r["id"] for r in speed["requirements"]]
        self.assertEqual(speed["epic"], "meeting-speed")
        self.assertEqual(len(ids), len(rows) - 2)
        self.assertNotIn("4.2.7", ids)
        self.assertNotIn("4.2.11", ids)

        record = self.ok(self.real_run("meeting-record"))
        rids = [r["id"] for r in record["requirements"]]
        self.assertTrue(rids)
        for i in rids:
            self.assertTrue(48 <= int(i.split(".")[1]) <= 58 and i.startswith("4."), f"不在 4.48–4.58：{i}")
        self.assertNotIn("4.58.6", rids)

    def real_run(self, epic: str):
        """暫存 repo 以 alternates 借本 repo 的物件，在 REAL_SPECS_BASE 上疊一個帶 Spec-Epic 的空 commit。"""
        tmp = tmpdir(self, "mh-reqs-real-")
        env = git_env()
        git(tmp, "init", "-q", env=env)
        common = Path(subprocess.run(["git", "-C", str(REPO), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                     capture_output=True, text=True, check=True).stdout.strip())
        (tmp / ".git" / "objects" / "info" / "alternates").write_text(str(common / "objects") + "\n", encoding="utf-8")
        base = git(tmp, "rev-parse", f"{REAL_SPECS_BASE}^{{commit}}", env=env)
        tree = git(tmp, "rev-parse", f"{base}^{{tree}}", env=env)
        head = git(tmp, "commit-tree", tree, "-p", base, "-m", trailer(epic), env=env)
        e = dict(env)
        e.update({"AWF_REPO": "s96cax98leo/meeting-harness", "AWF_PR": "7", "AWF_HEAD_SHA": head,
                  "AWF_REQ_BASE": REAL_SPECS_BASE})
        return run([PY, str(ADAPTER)], cwd=tmp, env=e)

    def test_source_points_to_row(self):
        """§4.3.10：source＝specs/<e>/spec.md:<行號>@<base 前 12 碼>，該行號在 base 版就是該條號所在列。"""
        repo = Repo(self)
        changed = "# 前面多一行\n" + DEMO_SPEC
        head = repo.commit(trailer("demo"), {"specs/demo/spec.md": changed})  # head 的行號和 base 不同
        out = self.ok(repo.adapter(head))
        base_lines = DEMO_SPEC.splitlines()
        for r in out["requirements"]:
            m = re.fullmatch(r"specs/demo/spec\.md:(\d+)@([0-9a-f]{12})", r["source"])
            self.assertIsNotNone(m, r["source"])
            self.assertEqual(m.group(2), repo.main[:12])
            row = ROW.match(base_lines[int(m.group(1)) - 1])
            self.assertIsNotNone(row, f"{r['source']} 指到的不是表格列")
            self.assertEqual(row.group(1), r["id"])

    def test_writes_nothing(self):
        """§4.3.12：exit 0 與 exit 2 各跑一次後，git status --porcelain --ignored、TMPDIR、cwd 都沒有變化。"""
        repo = Repo(self)
        head = repo.commit(trailer("demo"), {"src/app.txt": "v2\n"})
        (repo.path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
        (repo.path / "ignored").mkdir()
        (repo.path / "ignored" / "a.txt").write_text("a\n", encoding="utf-8")

        def snap():
            files = sorted(str(p.relative_to(repo.path)) for p in repo.path.rglob("*") if ".git" not in p.relative_to(repo.path).parts)
            return repo.git("status", "--porcelain", "--ignored"), files, sorted(os.listdir(repo.tmp))
        before = snap()
        self.ok(repo.adapter(head))
        self.assertEqual(snap(), before, "exit 0 那次留下了檔案")
        self.fail2(repo.adapter(head, base="refs/heads/no-such-branch"))
        self.assertEqual(snap(), before, "exit 2 那次留下了檔案")

    def test_no_narrowing_trailer(self):
        """§4.3.13：另帶 Spec-Reqs 或其他 trailer 時，輸出與不帶時逐位元相同。"""
        repo = Repo(self)
        plain = repo.commit(trailer("demo"), {"src/app.txt": "v2\n"})
        r1 = repo.adapter(plain)
        repo.git("checkout", "-q", "-b", "feature2", "main")
        narrowed = repo.commit(trailer("demo", "Spec-Reqs: 4.1.1", "Reviewed-by: Example <x@example.invalid>"),
                               {"src/app.txt": "v2\n"})
        r2 = repo.adapter(narrowed)
        self.ok(r1)
        self.ok(r2)
        self.assertEqual(r1.stdout, r2.stdout)


def subcommand(argv: list[str]) -> str:
    """git 參數列的子指令：跳過 -C <dir>、-c <k=v>、--git-dir=… 這類全域選項。"""
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"):
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        return a
    return ""


if __name__ == "__main__":
    unittest.main()

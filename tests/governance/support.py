"""tests/governance 共用的常數與輔助（不是測試模組）。

- 讀守門設定一律經 guard_config_path()（spec §4.2.8）：環境變數 MH_GUARD_CONFIG 有設就用它，
  否則用 repo 裡的 GUARD_CONFIG_REL。其他測試檔不寫守門設定的檔名字面值，一律從這裡的常數組出。
- 以腳本執行時提供 flip-enabled 子指令（plan §3 第 7 條）：
      python3 tests/governance/support.py flip-enabled <輸出檔>
  把守門設定複製一份、auto_merge.enabled 改成 true，寫到 <輸出檔>（不碰原檔）。

只用標準庫；import 本檔不得有副作用。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable

# 守門設定的檔名與相對 repo 根的路徑（spec §4.2.8）
GUARD_CONFIG_NAME = "guard.config.json"
GUARD_CONFIG_REL = ".claude/teams/" + GUARD_CONFIG_NAME

TOOLS_DIR = REPO / ".claude" / "teams" / "tools"
PROJECT_TOOLS = REPO / "tools" / "merge_gate_project"
ADAPTER = PROJECT_TOOLS / "reqs_from_spec.py"
APP_TOKEN = PROJECT_TOOLS / "gh_app_token.py"
SCAN_NAMES = PROJECT_TOOLS / "scan_names.py"
FAKES = Path(__file__).resolve().parent / "fakes"

# spec §3 的設定值（auto_merge 的 enabled 另外判斷）
AUTO_MERGE_SPEC = {
    "enabled": False,
    "repos": {"s96cax98leo/meeting-harness": "medium"},
    "merger_role": "agent-workflow:dev-merge-steward",
    "merge_method": "merge",
    "freeze_writers": ["agent-workflow:tpm-writer", "agent-workflow:dev-release-watcher"],
    "daily_cap": 3,
    "upstream_authorized_by": {},
    "freeze_file": "_tpm/runs/auto-merge.freeze.json",
    "small_lines": 100,
    "large_lines": 400,
    "large_files": 20,
    "carry_verdict_on_rebase": False,
}
REQUIREMENTS_SPEC = {
    "source": "command",
    "command": ["python3", "tools/merge_gate_project/reqs_from_spec.py"],
    "path": "",
    "id_pattern": "",
}


def guard_config_path() -> Path:
    """守門設定的路徑：MH_GUARD_CONFIG（有設時）或 repo 的 GUARD_CONFIG_REL。"""
    env = os.environ.get("MH_GUARD_CONFIG", "").strip()
    return Path(env) if env else REPO / GUARD_CONFIG_REL


def load_guard_config() -> dict:
    return json.loads(guard_config_path().read_text(encoding="utf-8"))


def strip_notes(d: dict) -> dict:
    """去掉 `_說明` 這類以底線開頭的說明鍵（模版渲染的說明文字，不是設定值）。"""
    return {k: v for k, v in d.items() if not str(k).startswith("_")}


def tmpdir(tc, prefix: str = "mh-gov-") -> Path:
    d = Path(tempfile.mkdtemp(prefix=prefix))
    tc.addCleanup(shutil.rmtree, d, True)
    return d


def run(cmd, *, cwd=None, env=None, timeout=120, input=None):
    """執行指令並回傳 CompletedProcess（文字模式、UTF-8）。"""
    return subprocess.run(cmd, cwd=cwd, env=env, input=input, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def git(repo, *args, env=None) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} 失敗：{r.stderr.strip()}")
    return r.stdout.strip()


def git_env(extra: dict | None = None) -> dict:
    """暫存 repo 用的 git 環境：固定作者、不讀使用者的全域設定。"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid",
        "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
    })
    if extra:
        env.update(extra)
    return env


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """markdown 從 heading 那一行（完全相同）到下一個同級或更高級標題之前的內容；找不到回空字串。"""
    lines = text.splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    out, inside = [], False
    for ln in lines:
        if inside:
            if ln.startswith("#") and (len(ln) - len(ln.lstrip("#"))) <= level and ln[len(ln) - len(ln.lstrip("#")):].startswith(" "):
                break
            out.append(ln)
        elif ln.strip() == heading:
            inside = True
    return "\n".join(out)


def flip_enabled(out: Path) -> None:
    data = json.loads(guard_config_path().read_text(encoding="utf-8"))
    if not isinstance(data.get("auto_merge"), dict):
        raise SystemExit("守門設定沒有 auto_merge 物件")
    data["auto_merge"]["enabled"] = True
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "flip-enabled":
        flip_enabled(Path(argv[1]))
        print(f"已寫出 auto_merge.enabled=true 的副本：{argv[1]}")
        return 0
    print("用法：python3 tests/governance/support.py flip-enabled <輸出檔>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

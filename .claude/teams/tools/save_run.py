"""把 workflow 的回傳存進 run 目錄，並記錄 SDLC 閘門（Workflow 腳本不能寫檔，由主 session 呼叫）。

run 目錄：_tpm/runs/<YYYYMMDD>-<事件>-<短名>/
    run.json            事件、目標 repo、各段狀態、閘門核准紀錄
    <stage>.json        該段 workflow 的完整回傳（每個 agent 的信封）

用法：
    python3 save_run.py init <run_dir> --event sdlc --target <repo> --requirement <描述或路徑>
    python3 save_run.py stage <run_dir> <stage> < result.json     # 存回傳並逐一驗證信封
    python3 save_run.py approve <run_dir> <stage> --by <誰> --at <ISO 時間> [--note <備註>]
    python3 save_run.py status <run_dir>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schemalib  # noqa: E402

SDLC = ["plan", "design", "build", "test", "deliver"]
GATED = {"plan", "design", "test", "deliver"}


def opt(argv: list[str], name: str, default: str = "") -> str:
    return argv[argv.index(name) + 1] if name in argv else default


def load(run: Path) -> dict:
    return json.loads((run / "run.json").read_text(encoding="utf-8"))


def dump(run: Path, data: dict) -> None:
    (run / "run.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def envelopes(node):
    """在回傳結構裡找出所有信封（有 status＋payload 的 dict）。"""
    if isinstance(node, dict):
        if "status" in node and "payload" in node:
            yield node
        for v in node.values():
            yield from envelopes(v)
    elif isinstance(node, list):
        for v in node:
            yield from envelopes(v)


def main(argv: list[str]) -> int:
    cmd, run = argv[0], Path(argv[1])
    if cmd == "init":
        run.mkdir(parents=True, exist_ok=True)
        if (run / "run.json").exists():
            print(f"已存在：{run / 'run.json'}")
            return 0
        event = opt(argv, "--event")
        dump(run, {
            "event": event,
            "target_repo": opt(argv, "--target"),
            "requirement": opt(argv, "--requirement"),
            "stages": {s: {"status": "pending", "gate": s in GATED} for s in (SDLC if event == "sdlc" else ["run"])},
        })
        print(f"已建立 {run / 'run.json'}")
        return 0
    data = load(run)
    if cmd == "stage":
        stage = argv[2]
        result = json.load(sys.stdin)
        (run / f"{stage}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        errs = []
        envs = list(envelopes(result))
        for i, env in enumerate(envs):
            errs += [f"信封 {i}：{e}" for e in schemalib.check(env)]
        statuses = [e.get("status") for e in envs]
        st = data["stages"].setdefault(stage, {"status": "pending", "gate": stage in GATED})
        st["status"] = "invalid" if errs else ("needs_decision" if "needs_decision" in statuses else "blocked" if "blocked" in statuses else "done")
        st["envelopes"] = len(envs)
        dump(run, data)
        for e in errs:
            print(e, file=sys.stderr)
        print(f"{stage}：{len(envs)} 份信封，狀態 {st['status']}" + ("（需要使用者核准才能進下一段）" if st.get("gate") and st["status"] == "done" else ""))
        return 1 if errs else 0
    if cmd == "approve":
        stage = argv[2]
        st = data["stages"][stage]
        st["approved"] = {"by": opt(argv, "--by"), "at": opt(argv, "--at"), "note": opt(argv, "--note")}
        dump(run, data)
        print(f"{stage} 已記錄核准：{st['approved']['by']} @ {st['approved']['at']}")
        return 0
    if cmd == "status":
        for name, st in data["stages"].items():
            gate = "閘門" if st.get("gate") else ""
            ok = f"核准 {st['approved']['by']}" if st.get("approved") else ""
            print(f"{name:8} {st['status']:15} {gate} {ok}")
        nxt = next((s for s in data["stages"] if data["stages"][s]["status"] != "done" or (data["stages"][s].get("gate") and not data["stages"][s].get("approved"))), None)
        print(f"下一步：{nxt or '全部完成'}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

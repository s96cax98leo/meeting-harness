"""把 schemas/ 內嵌進 .claude/workflows/*.js（Workflow 腳本不能 import 檔案）。

標記寫法（腳本內）：
    const SUBTASKS = /*@schema:subtasks*/ null /*@end*/
build 後變成 `/*@schema:subtasks*/ {...完整 JSON...} /*@end*/`。名稱是 payload 名；
`envelope` 代表 payload 不限形狀。

用法：
    python3 .claude/teams/tools/build.py          # 寫回
    python3 .claude/teams/tools/build.py --check  # 不一致就 exit 1（驗證用）
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import schemalib  # noqa: E402

WF_DIR = Path(__file__).resolve().parents[2] / "workflows"
MARK = re.compile(r"/\*@schema:([a-z-]+)\*/.*?/\*@end\*/", re.S)


def render(text: str) -> str:
    def sub(m: re.Match) -> str:
        name = m.group(1)
        schema = schemalib.compose(None if name == "envelope" else name)
        return f"/*@schema:{name}*/ {json.dumps(schema, ensure_ascii=False, separators=(',', ':'))} /*@end*/"

    return MARK.sub(sub, text)


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    files = sorted(WF_DIR.glob("*.js"))
    for f in files:
        old = f.read_text(encoding="utf-8")
        new = render(old)
        if new != old:
            stale.append(f.name)
            if not check:
                f.write_text(new, encoding="utf-8")
    if check and stale:
        print("workflow 內嵌的 schema 跟 schemas/ 不一致：" + "、".join(stale) + "（請跑 build.py）")
        return 1
    print(("檢查" if check else "已更新") + f"：{len(files)} 支 workflow" + ("，全部一致" if check else f"，改了 {len(stale)} 支"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

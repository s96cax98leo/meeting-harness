#!/usr/bin/env python3
"""掃描檔案是否含名稱清單裡的任一名稱（spec §2.3、§4.4.6、§4.4.7）。

    python3 tools/merge_gate_project/scan_names.py [--names-file <清單>] <檔案>...

清單來源依序：--names-file → 環境變數 MH_CLIENT_NAMES_FILE → <repo 根>/_tpm/runs/client-names.txt
（repo 根以本腳本位置往上兩層推得）。每行一個名稱，空白行忽略；不分大小寫的固定字串比對
（等同 `grep -qiF -f <清單>`）。

輸出與 exit：
- 0「沒有」：沒有任何檔案命中
- 1「有」：至少一個檔案命中
- 2「名稱清單讀不到」：清單讀不到，或沒有任何非空行
- 2（stdout 不印字）：要掃描的檔案讀不到；stderr 只寫「掃描目標讀不到」，不印路徑
任何情況都不印名單內容、命中字或命中行。只用標準庫。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

NO_HIT, HIT, NO_LIST = "沒有", "有", "名稱清單讀不到"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LIST = REPO_ROOT / "_tpm" / "runs" / "client-names.txt"


def list_path(cli: str | None) -> Path:
    if cli:
        return Path(cli)
    env = os.environ.get("MH_CLIENT_NAMES_FILE", "").strip()
    return Path(env) if env else DEFAULT_LIST


def load_names(path: Path) -> list[str] | None:
    """讀清單；讀不到或沒有非空行回 None。名稱一律 casefold。"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    names = [ln.strip().casefold() for ln in text.splitlines()]
    names = [n for n in names if n]
    return names or None


def hits(path: Path, names: list[str]) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").casefold()
    return any(n in text for n in names)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="掃描檔案是否含名稱清單裡的名稱（只回答有／沒有）")
    ap.add_argument("--names-file", default=None, help="名稱清單（每行一個）")
    ap.add_argument("files", nargs="+", help="要掃描的檔案")
    args = ap.parse_args(argv)

    names = load_names(list_path(args.names_file))
    if names is None:
        print(NO_LIST)
        return 2
    found = False
    for f in args.files:
        try:
            if hits(Path(f), names):
                found = True
        except OSError:
            print("掃描目標讀不到", file=sys.stderr)
            return 2
    print(HIT if found else NO_HIT)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

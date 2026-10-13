#!/usr/bin/env python3
"""_to_tw.py <file> [file...] — 簡體 → 台灣正體（OpenCC s2twp），就地改寫。

用途：Breeze-ASR-25 原生輸出繁體，不需要這支；但
  - fallback 走 whisper-large-v3 時仍會吐簡體
  - 地端 Qwen 產的總結也常吐簡體
這兩種情況才套用。

原則：只轉字形/詞彙，不動內容、不動排版。轉換前後字數不同時（詞組轉換）仍以 OpenCC 結果為準。
選項：
  --check   只回報簡體殘留字數，不改檔（exit 1 表示有殘留）
"""
import sys, os

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    check = "--check" in sys.argv
    if not args:
        print("usage: _to_tw.py [--check] <file> [file...]", file=sys.stderr)
        sys.exit(2)
    try:
        import opencc
    except ImportError:
        print("[to-tw] 未安裝 opencc（pip install opencc）→ 跳過轉換", file=sys.stderr)
        sys.exit(0 if not check else 0)

    cc = opencc.OpenCC("s2twp")
    total = 0
    for p in args:
        if not os.path.isfile(p):
            print(f"[to-tw] 略過（不存在）：{p}", file=sys.stderr)
            continue
        src = open(p, encoding="utf-8").read()
        dst = cc.convert(src)
        if src == dst:
            print(f"[to-tw] 已是正體，未變更：{os.path.basename(p)}")
            continue
        diff = sum(1 for a, b in zip(src, dst) if a != b) if len(src) == len(dst) else abs(len(dst) - len(src)) + 1
        total += diff
        if check:
            print(f"[to-tw] 簡體殘留 ~{diff} 字：{os.path.basename(p)}")
        else:
            open(p, "w", encoding="utf-8").write(dst)
            print(f"[to-tw] 轉為正體（~{diff} 字）：{os.path.basename(p)}")
    sys.exit(1 if (check and total) else 0)

if __name__ == "__main__":
    main()

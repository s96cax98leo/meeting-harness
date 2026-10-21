#!/usr/bin/env python3
"""_search.py — meeting search <根> <關鍵字>（spec §3.19、§4.33；R3-§2.2）。

- 搜 <根> 底下各場次的 summary.md、meeting.record.json、錄音/transcript.speakers.md、錄音/transcript.raw.md。
- 場次＝<根> 底下（不含 <根> 本身、最多 3 層，與 meeting.sh list_sessions 的 maxdepth 4 對齊）、
  含上述任一檔的資料夾；名為「錄音」的資料夾不算場次。
- 大小寫不分、純子字串（不當 regex）。
- 每筆一行：<場次相對 <根> 的路徑>/<檔名>:<行號>: <該行，超過 120 字截斷加「…」>。
- 場次依相對 <根> 的路徑（日期在前，例 YYYYMMDD/HHMM 會議）新到舊；同場次依 <檔名> 字串、行號遞增。
- 只讀 <根> 以內的檔：symlink 的檔與目錄一律略過，實際路徑也必須落在 <根> 之內（客戶資料邊界，§4.33.3）。

結束碼：0 有結果；1 沒有結果（stdout 空）；2 缺參數、根目錄不存在。
"""
import os
import sys

SEARCH_FILES = ("summary.md", "meeting.record.json", "錄音/transcript.speakers.md", "錄音/transcript.raw.md")
REC_DIR = "錄音"
MAX_DEPTH = 3
MAX_CHARS = 120


def usage():
    print("用法：meeting search <會議根目錄> <關鍵字>", file=sys.stderr)


def _inside(path, root_real):
    real = os.path.realpath(path)
    return real == root_real or real.startswith(root_real + os.sep)


def _safe_file(sess, rel, root_real):
    """回傳可讀的檔案路徑；路徑上任何一段是 symlink 或落在根目錄外就回 None。"""
    cur = sess
    for part in rel.split("/"):
        cur = os.path.join(cur, part)
        if os.path.islink(cur):
            return None
    if not os.path.isfile(cur) or not _inside(cur, root_real):
        return None
    return cur


def find_sessions(root):
    """回傳 [(相對路徑, 絕對路徑)]，只走實體目錄（不跟 symlink）。"""
    root_real = os.path.realpath(root)
    out = []
    for dirpath, dirnames, _files in os.walk(root, followlinks=False):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        # os.walk 不跟 symlink 目錄，但仍把它列在 dirnames；明確剔除
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        if depth >= MAX_DEPTH:
            dirnames[:] = []
        if rel == "." or os.path.basename(dirpath) == REC_DIR:
            continue
        if not _inside(dirpath, root_real):
            continue
        if any(_safe_file(dirpath, f, root_real) for f in SEARCH_FILES):
            out.append((rel.replace(os.sep, "/"), dirpath))
    # 依相對路徑新到舊（spec §4.33.1）：錄製器的場次是 <根>/YYYYMMDD/HHMM 會議，只看 basename 會只剩時刻，
    # 較舊日期的晚場會排到較新日期的早場前面；相對路徑唯一，結果穩定
    out.sort(key=lambda s: s[0], reverse=True)
    return out


def search_file(path, needle):
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as fh:
            text = fh.read()
    except OSError:
        return
    for no, line in enumerate(text.split("\n"), 1):
        line = line.rstrip("\r")
        if needle in line.casefold():
            yield no, (line[:MAX_CHARS] + "…") if len(line) > MAX_CHARS else line


def main(argv):
    if len(argv) != 2 or not argv[0] or not argv[1]:
        usage()
        return 2
    root, keyword = argv
    if not os.path.isdir(root):
        print(f"✗ 找不到會議根目錄：{root}", file=sys.stderr)
        return 2
    root_real = os.path.realpath(root)
    needle = keyword.casefold()
    hits = 0
    for rel, sess in find_sessions(root):
        for name in sorted(SEARCH_FILES):
            path = _safe_file(sess, name, root_real)
            if path is None:
                continue
            for no, line in search_file(path, needle):
                print(f"{rel}/{name}:{no}: {line}")
                hits += 1
    return 0 if hits else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        # 接 head 之類的管道被提早關閉：不印 traceback
        sys.stderr.close()
        sys.exit(0)

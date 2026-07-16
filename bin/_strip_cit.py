#!/usr/bin/env python3
"""_strip_cit.py — 移除來源標註（[逐字稿]/[投影片 IMG_xxxx]/〔…IMG…〕等），供最終檔案乾淨呈現。
保留：（存疑）、（來源：URL）、其他非出處的 〔…〕 註記（如〔本場新出現〕）。
只動半形 [] 與全形 〔〕，不動全形 （）（那是內文語氣，如「（逐字稿音譯為…）」）。
可當模組 import strip_text，或 CLI：_strip_cit.py <file> [file2 ...] 就地清理。
"""
import re, sys

_KEY = re.compile(r'逐字稿|投影片|IMG_')

def _repl_sq(m):
    return '' if _KEY.search(m.group(1)) else m.group(0)

def strip_text(t: str) -> str:
    # 半形 [ ... ]（單行、不含巢狀）
    t = re.sub(r'\[([^\[\]\n]*?)\]', _repl_sq, t)
    # 全形 〔 ... 〕
    t = re.sub(r'〔([^〔〕\n]*?)〕', _repl_sq, t)
    # 殘留的裸「投影片 IMG_xxxx」或「IMG_xxxx」（含範圍，如 IMG_0012–0013）
    t = re.sub(r'投影片\s*IMG[_\s]*[0-9A-Za-z]+(?:[–\-][0-9A-Za-z]+)?', '', t)
    t = re.sub(r'\bIMG_[0-9]+(?:[–\-][0-9]+)?\b', '', t)
    # 收尾：空的 （）、標點前多餘空白、連續空白
    t = re.sub(r'（\s*）', '', t)
    t = re.sub(r'[ \t]{2,}', ' ', t)
    t = re.sub(r'[ \t]+([。，、；：！？）】」』])', r'\1', t)
    t = re.sub(r'（[ \t]+', '（', t)
    return t

def main():
    for fp in sys.argv[1:]:
        s = open(fp, encoding='utf-8').read()
        open(fp, 'w', encoding='utf-8').write(strip_text(s))
        print(f"stripped: {fp}")

if __name__ == '__main__':
    main()

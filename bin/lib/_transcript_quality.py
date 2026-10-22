#!/usr/bin/env python3
"""_transcript_quality.py <transcript.segments.json> <transcript.quality.json>

transcribe.sh 的品質檔（spec §3.18、§4.30.5；meeting-speed §4.13.1 從 heredoc 搬出來，判準不變）。
逐段標出可疑段落，只標記、不動 raw（鐵則 1）；衍生檔（speakers.md、VTT）會在這些段落前加「（聽不清）」（鐵則 4）。
  compression_ratio：該段文字 zlib 壓縮比 > 2.4
  no_speech_loop   ：同一句（≥ 2 字）在該段內連續重複 ≥ 3 次
  repeat_run       ：相鄰 ≥ 4 段文字完全相同，每段各一筆
讀不到段落檔時寫 []（無從判斷）。輸出依 start 排序的 [{"start", "end", "reason"}]。
"""
import json
import os
import re
import sys
import zlib


def main(argv):
    if len(argv) != 2:
        print("usage: _transcript_quality.py <transcript.segments.json> <transcript.quality.json>", file=sys.stderr)
        return 2
    segp, outp = argv
    segs = []
    if os.path.isfile(segp):
        try:
            d = json.load(open(segp, encoding="utf-8"))
            segs = [s for s in (d.get("segments") or []) if isinstance(s, dict)] if isinstance(d, dict) else []
        except (OSError, ValueError):
            segs = []
    LOOP = re.compile(r"(.{2,}?)\1{2,}", re.S)
    def ratio(t):
        b = t.encode("utf-8")
        return len(b) / len(zlib.compress(b)) if b else 0.0
    texts = [str(s.get("text") or "").strip() for s in segs]
    flags = [[] for _ in segs]
    for i, t in enumerate(texts):
        if not t:
            continue
        if ratio(t) > 2.4:
            flags[i].append("compression_ratio")
        if LOOP.search(re.sub(r"\s+", "", t)):
            flags[i].append("no_speech_loop")
    i = 0
    while i < len(texts):
        j = i
        while j + 1 < len(texts) and texts[j + 1] == texts[i]:
            j += 1
        if texts[i] and j - i + 1 >= 4:
            for k in range(i, j + 1):
                flags[k].append("repeat_run")
        i = j + 1
    out = []
    for s, fl in zip(segs, flags):
        for r in fl:
            out.append({"start": s.get("start"), "end": s.get("end"), "reason": r})
    out.sort(key=lambda e: (e["start"] if isinstance(e["start"], (int, float)) else 0.0))
    with open(outp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")
    n = len(out)
    print(f"[transcribe] quality -> {outp}（{n} 筆）" if n else f"[transcribe] quality -> {outp}（沒有可疑段落）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

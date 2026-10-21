#!/usr/bin/env python3
"""MH_EMBED_SPEAKER_CMD 的替身（meeting-speed spec §3.7、§4.6.4）：取代 `_diarize_pyannote.py --embed-speaker`。

參數：[--embed-speaker] <wav> <diarization.json> <SPEAKER_xx> <out.json>（開頭的 --embed-speaker 可有可無）。
- 在 FAKE_EMBED_LOG（未設就不記）附加一行 JSON：{"argv", "out"}。
- 寫 <out.json>：{"model": "fake", "dim": 3, "speaker": <SPEAKER_xx>, "vector": V, "speakers": {<SPEAKER_xx>: V}}，
  V＝FAKE_EMBED_VECTOR（JSON 陣列）或 [0.0, 0.0, 1.0]。
- FAKE_EMBED_EXIT 非 0 時不寫檔、以該值結束。
"""
import json
import os
import sys

args = sys.argv[1:]
if args and args[0] == "--embed-speaker":
    args = args[1:]
log = os.environ.get("FAKE_EMBED_LOG")
out = args[3] if len(args) >= 4 else None
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "out": out}, ensure_ascii=False) + "\n")
code = int(os.environ.get("FAKE_EMBED_EXIT", "0") or 0)
if code:
    sys.exit(code)
if len(args) < 4:
    print("usage: ms_embed_speaker.py [--embed-speaker] <wav> <diarization.json> <SPEAKER_xx> <out.json>", file=sys.stderr)
    sys.exit(2)
vec = json.loads(os.environ.get("FAKE_EMBED_VECTOR") or "[0.0, 0.0, 1.0]")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"model": "fake", "dim": len(vec), "speaker": args[2], "vector": vec, "speakers": {args[2]: vec}}, f,
              ensure_ascii=False)
sys.exit(0)

#!/usr/bin/env python3
"""_diarize.py <wav_path> <out_json>  — 在 senko venv 內執行。
用 Senko 對音檔做講者分離（本機 CoreML，免 HF token），輸出 speaker 段 JSON。
輸出格式：{"segments":[{"start":float,"end":float,"speaker":"SPEAKER_00"}, ...]}
"""
import sys, json

def main():
    if len(sys.argv) < 3:
        print("usage: _diarize.py <wav> <out.json>", file=sys.stderr); sys.exit(2)
    wav, out = sys.argv[1], sys.argv[2]
    try:
        import senko
    except Exception as e:
        print(json.dumps({"error": f"senko import failed: {e}"})); sys.exit(3)

    diarizer = senko.Diarizer(device="auto", warmup=True, quiet=True)
    result = diarizer.diarize(wav, generate_colors=False)

    # senko 回傳 merged_segments；欄位名在不同版本可能是 start/end/speaker 或 begin/stop/label
    raw = result.get("merged_segments") or result.get("segments") or result
    segs = []
    for s in raw:
        st = s.get("start", s.get("begin", s.get("from")))
        en = s.get("end", s.get("stop", s.get("to")))
        sp = s.get("speaker", s.get("label", s.get("spk")))
        if st is None or en is None:
            continue
        segs.append({"start": float(st), "end": float(en), "speaker": str(sp)})
    segs.sort(key=lambda x: x["start"])
    n_spk = len({s["speaker"] for s in segs})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"segments": segs, "numSpeakers": n_spk}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "segments": len(segs), "numSpeakers": n_spk}, ensure_ascii=False))

if __name__ == "__main__":
    main()

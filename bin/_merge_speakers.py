#!/usr/bin/env python3
"""_merge_speakers.py <transcript.segments.json> <diarization.json> <out.speakers.md> [speakers.map.json]
把 whisper 逐字段（含時間戳）與 senko 講者段合併：每個逐字段指派給「時間重疊最多」的講者，
連續同講者併段，輸出講者標記逐字稿。若給 speakers.map.json 則把 SPEAKER_xx 改成指定名稱。
"""
import sys, json, os

def load_whisper_segments(path):
    d = json.load(open(path, encoding="utf-8"))
    segs = d.get("segments", d if isinstance(d, list) else [])
    out = []
    for s in segs:
        st, en = s.get("start"), s.get("end")
        txt = (s.get("text") or "").strip()
        if st is None or en is None or not txt:
            continue
        out.append({"start": float(st), "end": float(en), "text": txt})
    return out

def load_speaker_segments(path):
    d = json.load(open(path, encoding="utf-8"))
    return d.get("segments", [])

def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))

def assign_speaker(seg, spk_segs):
    """回傳與此逐字段重疊時間最長的講者；無重疊則取中點最近者。"""
    best, best_ov = None, 0.0
    for sp in spk_segs:
        ov = overlap(seg["start"], seg["end"], sp["start"], sp["end"])
        if ov > best_ov:
            best_ov, best = ov, sp["speaker"]
    if best is not None:
        return best
    mid = (seg["start"] + seg["end"]) / 2
    nearest, nd = None, float("inf")
    for sp in spk_segs:
        d = 0 if sp["start"] <= mid <= sp["end"] else min(abs(mid - sp["start"]), abs(mid - sp["end"]))
        if d < nd:
            nd, nearest = d, sp["speaker"]
    return nearest or "SPEAKER_?"

def fmt_ts(sec):
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

def main():
    if len(sys.argv) < 4:
        print("usage: _merge_speakers.py <transcript.segments.json> <diarization.json> <out.md> [speakers.map.json]", file=sys.stderr)
        sys.exit(2)
    wj, dj, out = sys.argv[1], sys.argv[2], sys.argv[3]
    name_map = {}
    if len(sys.argv) >= 5 and os.path.exists(sys.argv[4]):
        name_map = json.load(open(sys.argv[4], encoding="utf-8"))

    wsegs = load_whisper_segments(wj)
    ssegs = load_speaker_segments(dj)
    if not wsegs:
        print("ERROR: 無逐字段", file=sys.stderr); sys.exit(3)
    if not ssegs:
        print("ERROR: 無講者段", file=sys.stderr); sys.exit(3)

    # 選用：把總時長過短的講者（零星插話/雜訊）併入最近的主要講者
    # 用 MH_MIN_SPEAKER_SEC 設門檻（秒），預設 0 = 全部保留（誠實）
    min_sec = float(os.environ.get("MH_MIN_SPEAKER_SEC", "0") or 0)
    if min_sec > 0:
        tot = {}
        for sp in ssegs:
            tot[sp["speaker"]] = tot.get(sp["speaker"], 0.0) + (sp["end"] - sp["start"])
        major = {s for s, d in tot.items() if d >= min_sec} or set(tot)
        def nearest_major(seg):
            best, bd = None, float("inf")
            for sp in ssegs:
                if sp["speaker"] not in major:
                    continue
                mid = (seg["start"] + seg["end"]) / 2
                d = 0 if sp["start"] <= mid <= sp["end"] else min(abs(mid - sp["start"]), abs(mid - sp["end"]))
                if d < bd:
                    bd, best = d, sp["speaker"]
            return best
        for sp in ssegs:
            if sp["speaker"] not in major:
                sp["speaker"] = nearest_major(sp) or sp["speaker"]

    labeled = [{**s, "spk": assign_speaker(s, ssegs)} for s in wsegs]

    # 連續同講者併段
    blocks, cur = [], None
    for s in labeled:
        if cur and s["spk"] == cur["spk"]:
            cur["text"] += ("" if cur["text"].endswith(("。", "！", "？", "，")) else "") + s["text"]
            cur["end"] = s["end"]
        else:
            cur = {"spk": s["spk"], "start": s["start"], "end": s["end"], "text": s["text"]}
            blocks.append(cur)

    speakers = sorted({b["spk"] for b in blocks})
    disp = {sp: name_map.get(sp, sp) for sp in speakers}

    lines = ["# 逐字稿（講者分離：mlx-whisper + Senko）\n",
             f"> 偵測講者數：{len(speakers)}　（{', '.join(disp[s] for s in speakers)}）",
             "> 講者標籤為匿名，可用 speakers.map.json 對應真實姓名。\n"]
    for b in blocks:
        lines.append(f"\n**[{disp[b['spk']]}]** _( {fmt_ts(b['start'])} )_")
        lines.append(b["text"])
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"status": "ok", "speakersPath": out, "numSpeakers": len(speakers),
                      "blocks": len(blocks)}, ensure_ascii=False))

if __name__ == "__main__":
    main()

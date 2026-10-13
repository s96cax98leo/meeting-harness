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
    """回傳 (主要講者段, 含重疊的講者段)。

    主要段來自 exclusive diarization（一個時間點只屬一位講者，對齊逐字稿最乾淨）；
    含重疊那份在主要段判不出歸屬時當第二順位——短插話（「對」「嗯」）常常落在
    exclusive 的空隙裡，退一步用重疊版通常就找得到人，而且仍然是有依據的歸屬。
    """
    d = json.load(open(path, encoding="utf-8"))
    return d.get("segments", []), d.get("segmentsOverlapped", [])

def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))

# 逐字段要歸給某位講者，需要「足夠的重疊證據」。不夠就標未知，不硬指派——
# whisper 在靜音/雜訊段也會產出文字，硬塞給「最近的講者」會製造假歸屬
# （0915 那場的假 SPEAKER_03 就是這樣被放大的）。
#
# 兩個判準取其一即可（實測 0907 一對一）：
#   比例：重疊 / 逐字段長度 ≥ 0.3
#   秒數：重疊 ≥ 0.6 秒
# 為什麼要有絕對秒數這條：whisper 常把前後靜音併進同一段，
# 例如「你是在家裡還是在公司」被標成 9 秒、實際只講 2 秒，比例只有 0.23 但證據其實很足。
# 只有比例一條的話，這種段會被冤枉成未知（實測 45 段裡有 25 段是這樣）。
MIN_OVERLAP_RATIO = float(os.environ.get("MH_MIN_OVERLAP_RATIO", "0.3"))
MIN_OVERLAP_SEC = float(os.environ.get("MH_MIN_OVERLAP_SEC", "0.6"))
UNKNOWN = "SPEAKER_?"

def assign_speaker(seg, spk_segs):
    """回傳與此逐字段重疊最多的講者；證據不足則回傳 SPEAKER_?（不猜）。"""
    dur = max(seg["end"] - seg["start"], 1e-6)
    best, best_ov = None, 0.0
    for sp in spk_segs:
        ov = overlap(seg["start"], seg["end"], sp["start"], sp["end"])
        if ov > best_ov:
            best_ov, best = ov, sp["speaker"]
    if best is not None and (best_ov / dur >= MIN_OVERLAP_RATIO or best_ov >= MIN_OVERLAP_SEC):
        return best
    return UNKNOWN

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
        raw_map = json.load(open(sys.argv[4], encoding="utf-8"))
        # 兩種格式都吃：{"SPEAKER_01": "Kevin"} 或
        # {"SPEAKER_01": {"name": "Kevin", "confidence": 0.92, "apply": true, "evidence": "..."}}
        # 套不套用的判準：有 apply 就聽它的（寫入方自己知道門檻），沒有就看信心值 ≥ 0.7。
        # 不夠的維持匿名標籤，由總結標為存疑——寧可匿名也不掛錯名字。
        for k, v in raw_map.items():
            if isinstance(v, dict):
                ok = v.get("apply") if "apply" in v else (float(v.get("confidence", 1.0)) >= 0.7)
                if ok and v.get("name"):
                    name_map[k] = v["name"]
            elif v:
                name_map[k] = v

    wsegs = load_whisper_segments(wj)
    ssegs, ssegs_all = load_speaker_segments(dj)
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

    def assign(seg):
        spk = assign_speaker(seg, ssegs)
        if spk == UNKNOWN and ssegs_all:
            alt = assign_speaker(seg, ssegs_all)   # 退到含重疊那份再試一次
            if alt != UNKNOWN:
                return alt
        return spk

    labeled = [{**s, "spk": assign(s)} for s in wsegs]

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

    named = [s for s in speakers if s != UNKNOWN]
    lines = ["# 逐字稿（講者分離）\n",
             f"> 偵測講者數：{len(named)}　（{', '.join(disp[s] for s in named)}）",
             "> 講者標籤為匿名，可用 speakers.map.json 對應真實姓名。"]
    if UNKNOWN in speakers:
        n_unk = sum(1 for b in blocks if b["spk"] == UNKNOWN)
        lines.append(f"> ⚠ 有 {n_unk} 段找不到足夠的重疊證據（< {MIN_OVERLAP_RATIO:.0%} 且 < {MIN_OVERLAP_SEC} 秒），"
                     "標為 SPEAKER_?，未指派歸屬（多為靜音段誤判或重疊講話）。")
    lines.append("")
    for b in blocks:
        lines.append(f"\n**[{disp[b['spk']]}]** _( {fmt_ts(b['start'])} )_")
        lines.append(b["text"])
    open(out, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(json.dumps({"status": "ok", "speakersPath": out, "numSpeakers": len(named),
                      "unknownBlocks": sum(1 for b in blocks if b["spk"] == UNKNOWN),
                      "blocks": len(blocks)}, ensure_ascii=False))

if __name__ == "__main__":
    main()

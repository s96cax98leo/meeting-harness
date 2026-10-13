#!/usr/bin/env python3
"""_render.py <場次目錄> [--summary] [--actions] [--vtt] [--all] [--annotate-speakers]

由 `<場次>/meeting.record.json`（schema/meeting-record.v1.json）渲染所有對外產物：

  summary.md      人看的會議紀錄（依會議型態套模板）。固定含
                  「一句話：」與 ## 決議 / ## 依賴 / ## 風險與未決 / ## 交辦 / ## 存疑
                  ——下游知識庫專案 的 tools/meetings.py 是照這幾個標題檢查的。
  actions.csv     交辦事項表（任何試算表/任務系統都吃）
  actions.ics     iCalendar VTODO（RFC 5545），可直接匯入行事曆/提醒事項
  錄音/transcript.vtt  WebVTT（W3C）逐字稿；對得到真名的段落帶 <v 講者> 標籤
                  （講者歸屬與 _merge_speakers.py 相同）

--annotate-speakers 只做 錄音/transcript.speakers.md 的後處理（meeting diarize 在
_merge_speakers.py 之後呼叫），不產其他檔；沒有註記可加時不改檔。

沒有參數時＝--all（有什麼來源就產什麼）。
單一真相：只改 meeting.record.json 再重跑本程式，所有產物一致。
"""
import sys, os, json, csv, datetime, re

UNSET = "（未指定）"

# ── 型態 → 章節順序 ────────────────────────────────────────────────
# 五個必備段（決議/依賴/風險與未決/交辦/存疑）每種型態都有，只是位置不同；
# 沒有內容就寫「（無）」，不刪標題——下游是照標題找東西的。
LAYOUT = {
    "seminar":   ["tldr", "topics", "decisions", "dependencies", "risks", "actions", "glossary", "open", "uncertain"],
    "internal":  ["tldr", "decisions", "topics", "actions", "dependencies", "risks", "open", "glossary", "uncertain"],
    "client":    ["tldr", "decisions", "topics", "actions", "dependencies", "risks", "open", "glossary", "uncertain"],
    "1on1":      ["tldr", "actions", "decisions", "topics", "dependencies", "risks", "open", "glossary", "uncertain"],
    "workshop":  ["tldr", "topics", "decisions", "actions", "dependencies", "risks", "open", "glossary", "uncertain"],
    "interview": ["tldr", "topics", "actions", "decisions", "dependencies", "risks", "open", "glossary", "uncertain"],
}
TYPE_LABEL = {
    "seminar": "研討會／演講", "internal": "內部會議", "client": "客戶會議",
    "1on1": "一對一", "workshop": "工作坊", "interview": "訪談／面談",
}

def fmt_ref(refs):
    if not refs:
        return ""
    bits = []
    for r in refs:
        t = r.get("t")
        s = r.get("speaker")
        bits.append("".join(x for x in [f"{t}" if t not in (None, "") else "", f" {s}" if s else ""]).strip())
    bits = [b for b in bits if b]
    return f"（{'；'.join(bits)}）" if bits else ""

def sec_tldr(rec, out):
    s = rec.get("summary", {})
    out.append(f"一句話：{s.get('oneLiner', '').strip()}")
    out.append("")
    if s.get("tldr"):
        out.append("## TL;DR")
        out += [f"{i}. {x}" for i, x in enumerate(s["tldr"], 1)]
        out.append("")

def sec_topics(rec, out):
    out.append("## 逐議題討論")
    topics = rec.get("topics") or []
    if not topics:
        out.append("（無）")
    for t in topics:
        out.append(f"\n### {t['title']}")
        for p in t.get("points", []):
            out.append(f"- {p}")
        if t.get("speakers"):
            out.append(f"- 發言者：{'、'.join(t['speakers'])}")
    out.append("")

def sec_decisions(rec, out):
    out.append("## 決議")
    ds = rec.get("decisions") or []
    if not ds:
        out.append("（無）")
    else:
        out.append("| 編號 | 決議 | 拍板 |")
        out.append("|---|---|---|")
        for i, d in enumerate(ds, 1):
            out.append(f"| {d.get('id') or f'D-{i:02d}'} | {d['text']} | {d.get('by') or UNSET} |")
        rats = [d for d in ds if d.get("rationale")]
        if rats:
            out.append("")
            for d in rats:
                out.append(f"- {d.get('id') or d['text'][:12]}：{d['rationale']}")
    out.append("")

def sec_actions(rec, out):
    out.append("## 交辦")
    acts = rec.get("actions") or []
    if not acts:
        out.append("（無）")
    else:
        out.append("| 編號 | 事項 | 負責人 | 期限 | 狀態 |")
        out.append("|---|---|---|---|---|")
        for i, a in enumerate(acts, 1):
            out.append(f"| {a.get('id') or f'A-{i:02d}'} | {a['title']} | {a.get('owner') or UNSET} "
                       f"| {a.get('due') or UNSET} | {a.get('status') or '待辦'} |")
        det = [a for a in acts if a.get("detail")]
        if det:
            out.append("")
            for a in det:
                out.append(f"- {a.get('id') or a['title'][:12]}：{a['detail']}")
    out.append("")

def sec_dependencies(rec, out):
    out.append("## 依賴")
    ds = rec.get("dependencies") or []
    if not ds:
        out.append("（無）")
    else:
        out.append("| 編號 | 事項 | 誰在等 | 等誰 | 需要時間 |")
        out.append("|---|---|---|---|---|")
        for i, d in enumerate(ds, 1):
            out.append(f"| {d.get('id') or f'DEP-{i:02d}'} | {d['text']} | {d.get('from') or UNSET} "
                       f"| {d.get('to') or UNSET} | {d.get('needBy') or UNSET} |")
    out.append("")

def sec_risks(rec, out):
    out.append("## 風險與未決")
    rs = rec.get("risks") or []
    if not rs:
        out.append("（無）")
    else:
        for i, r in enumerate(rs, 1):
            sev = f"[{r['severity']}] " if r.get("severity") else ""
            own = f"（負責人：{r['owner']}）" if r.get("owner") else ""
            out.append(f"- {sev}{r['text']}{own}")
            if r.get("mitigation"):
                out.append(f"  - 因應：{r['mitigation']}")
    out.append("")

def sec_open(rec, out):
    qs = rec.get("openQuestions") or []
    if not qs:
        return
    out.append("## 待確認")
    for q in qs:
        who = f"（{q['owner']}）" if q.get("owner") else ""
        by = f"　期限：{q['by']}" if q.get("by") else ""
        out.append(f"- {q['text']}{who}{by}")
    out.append("")

def sec_glossary(rec, out):
    gs = rec.get("glossary") or []
    if not gs:
        return
    out.append("## 名詞")
    for g in gs:
        al = f"（{'／'.join(g['aliases'])}）" if g.get("aliases") else ""
        out.append(f"- **{g['term']}**{al}：{g.get('definition', '')}")
    out.append("")

def sec_uncertain(rec, out):
    out.append("## 存疑（建議人工確認）")
    us = rec.get("uncertain") or []
    if not us:
        out.append("（無）")
    for u in us:
        heard = f"　逐字稿聽成「{u['heardAs']}」" if u.get("heardAs") else ""
        guess = f"　推測：{u['guess']}" if u.get("guess") else ""
        out.append(f"- {u['text']}{heard}{guess}{fmt_ref(u.get('refs'))}")
    out.append("")

SECTIONS = {"tldr": sec_tldr, "topics": sec_topics, "decisions": sec_decisions,
            "actions": sec_actions, "dependencies": sec_dependencies, "risks": sec_risks,
            "open": sec_open, "glossary": sec_glossary, "uncertain": sec_uncertain}

def render_summary(rec):
    m = rec["meeting"]
    t = m.get("type", "internal")
    who = "、".join(f"{a['name']}" + (f"（{a['org']}）" if a.get("org") else "") for a in m.get("attendees", []))
    fm = ["---", "type: meeting-notes", f"meetingType: {t}",
          f"title: {m['title']}", f"date: {m['date']}"]
    if m.get("org"):      fm.append(f"org: {m['org']}")
    if m.get("durationMin"): fm.append(f"durationMin: {m['durationMin']}")
    if m.get("attendees"):
        fm.append("attendees: [" + ", ".join(a["name"] for a in m["attendees"]) + "]")
    if m.get("sources"):  fm.append("sources: [" + ", ".join(m["sources"]) + "]")
    fm.append("---")

    out = fm + ["", f"# {m['title']}", ""]
    meta = [f"{TYPE_LABEL.get(t, t)}", m["date"]]
    if m.get("startTime"): meta.append(f"{m['startTime']}–{m.get('endTime','')}".rstrip("–"))
    if who: meta.append(f"出席：{who}")
    out += ["　｜　".join(meta), ""]

    for key in LAYOUT.get(t, LAYOUT["internal"]):
        SECTIONS[key](rec, out)
    return "\n".join(out).rstrip() + "\n"

def render_actions_csv(rec, path):
    acts = rec.get("actions") or []
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["編號", "事項", "說明", "負責人", "期限", "狀態", "來源會議"])
        mid = rec["meeting"].get("id") or rec["meeting"]["title"]
        for i, a in enumerate(acts, 1):
            w.writerow([a.get("id") or f"A-{i:02d}", a["title"], a.get("detail", ""),
                        a.get("owner", ""), a.get("due", ""), a.get("status", "待辦"), mid])
    return len(acts)

def _ics_escape(s):
    return s.replace("\\", "\\\\").replace(";", r"\;").replace(",", r"\,").replace("\n", r"\n")

def render_actions_ics(rec, path):
    acts = rec.get("actions") or []
    m = rec["meeting"]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//meeting-harness//meeting-record v1//ZH-TW"]
    for i, a in enumerate(acts, 1):
        aid = a.get("id") or f"A-{i:02d}"
        lines += ["BEGIN:VTODO",
                  f"UID:{m.get('id', m['title'])}-{aid}@meeting-harness",
                  f"DTSTAMP:{now}",
                  f"SUMMARY:{_ics_escape(a['title'])}"]
        desc = [x for x in [a.get("detail"), f"負責人：{a.get('owner') or UNSET}",
                            f"來源：{m.get('id') or m['title']}（{m['date']}）"] if x]
        lines.append("DESCRIPTION:" + _ics_escape("\n".join(desc)))
        due = (a.get("due") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", due):
            lines.append("DUE;VALUE=DATE:" + due.replace("-", ""))
        lines.append("STATUS:" + ("COMPLETED" if a.get("status") == "已完成" else "NEEDS-ACTION"))
        lines.append("END:VTODO")
    lines.append("END:VCALENDAR")
    open(path, "w", encoding="utf-8").write("\r\n".join(lines) + "\r\n")
    return len(acts)

def _ts(sec):
    h, rem = divmod(float(sec), 3600)
    mnt, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(mnt):02d}:{s:06.3f}"

# ── 講者歸屬：與 _merge_speakers.py 用同一套（spec §4.29.2；該檔不改） ──────────
# 段落→講者以 importlib 載入 bin/_merge_speakers.py 既有的 assign_speaker／load_speaker_segments／UNKNOWN，
# 它 main() 內的套名判準、MH_MIN_SPEAKER_SEC 併入、退到含重疊那份照抄於下方函式（註解寫出處行號），
# 一致性由 tests/record/test_r3_vtt_raw.py::test_render_copy_matches_merge 保證。
_MERGE = None

def _merge_module():
    """以 importlib 載入 bin/_merge_speakers.py（有 __main__ 保護，匯入不會執行 main）。不寫 .pyc。"""
    global _MERGE
    if _MERGE is None:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("_merge_speakers", os.path.join(here, "_merge_speakers.py"))
        mod = importlib.util.module_from_spec(spec)
        dwb, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = dwb
        _MERGE = mod
    return _MERGE

def load_name_map(path):
    """speakers.map.json → {代號: 真名}。照抄 _merge_speakers.py:70-82（main 內的套名判準）：
    dict 值有 apply 就聽 apply，沒有就看 confidence ≥ 0.7；字串值直接套。不夠的不掛名（鐵則 3）。"""
    name_map = {}
    if path and os.path.exists(path):
        raw_map = json.load(open(path, encoding="utf-8"))
        for k, v in raw_map.items():
            if isinstance(v, dict):
                ok = v.get("apply") if "apply" in v else (float(v.get("confidence", 1.0)) >= 0.7)
                if ok and v.get("name"):
                    name_map[k] = v["name"]
            elif v:
                name_map[k] = v
    return name_map

def _fold_minor_speakers(ssegs):
    """照抄 _merge_speakers.py:91-111：MH_MIN_SPEAKER_SEC > 0 時，把總時長過短的講者併入最近的主要講者
    （只動主要講者段，不動含重疊那份；與原程式相同）。"""
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

def speaker_assigner(rec_dir):
    """回傳 (assign, name_map)；assign(seg) → 講者代號（證據不足為 UNKNOWN）。沒有講者分段時回傳 (None, {})。
    歸屬本身用 _merge_speakers.assign_speaker（_merge_speakers.py:47）；
    「主要段判不出來就退到含重疊那份再試一次」照抄 _merge_speakers.py:113-119。"""
    dp = os.path.join(rec_dir, "diarization.json")
    if not os.path.isfile(dp):
        return None, {}
    ms = _merge_module()
    ssegs, ssegs_all = ms.load_speaker_segments(dp)          # _merge_speakers.py:20
    if not ssegs:
        return None, {}
    _fold_minor_speakers(ssegs)
    unknown = ms.UNKNOWN                                       # _merge_speakers.py:45

    def assign(seg):
        spk = ms.assign_speaker(seg, ssegs)
        if spk == unknown and ssegs_all:
            alt = ms.assign_speaker(seg, ssegs_all)   # 退到含重疊那份再試一次
            if alt != unknown:
                return alt
        return spk
    return assign, load_name_map(os.path.join(rec_dir, "speakers.map.json"))

def render_vtt(sess, path):
    """逐字稿 → WebVTT。來源是 raw segments（不改 raw 本身）。
    講者歸屬與 transcript.speakers.md 相同（speaker_assigner）；只有對得到真名的講者才加 <v 名字>，
    代號與 SPEAKER_? 一律不加（鐵則 3：不確定的姓名不掛）。"""
    rec_dir = os.path.join(sess, "錄音")
    segp = os.path.join(rec_dir, "transcript.segments.json")
    if not os.path.isfile(segp):
        return 0
    segs = json.load(open(segp, encoding="utf-8")).get("segments", [])
    assign, names = speaker_assigner(rec_dir)

    def who(s):
        if assign is None:
            return None
        name = names.get(assign({"start": float(s["start"]), "end": float(s["end"])}))
        return name if name and not str(name).startswith("SPEAKER_") else None

    lines = ["WEBVTT", ""]
    for i, s in enumerate(segs, 1):
        txt = (s.get("text") or "").strip()
        if not txt:
            continue
        v = who(s)
        lines += [str(i), f"{_ts(s['start'])} --> {_ts(s['end'])}",
                  (f"<v {v}>{txt}" if v else txt), ""]
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return len(segs)

def annotate_speakers(sess):
    """transcript.speakers.md 的後處理掛勾（spec §4.31.10）：插註記行與「（聽不清）」。
    目前沒有任何註記來源，所以一律不改檔；回傳是否改了檔。註記內容由後續子任務補上。"""
    p = os.path.join(sess, "錄音", "transcript.speakers.md")
    if not os.path.isfile(p):
        return False
    return False

def main():
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    sess = os.path.abspath(sys.argv[1])
    flags = set(sys.argv[2:]) or {"--all"}
    if "--all" in flags:
        flags = {"--summary", "--actions", "--vtt"}

    recp = os.path.join(sess, "meeting.record.json")
    rec = None
    if os.path.isfile(recp):
        rec = json.load(open(recp, encoding="utf-8"))
    elif flags & {"--summary", "--actions"}:
        print(f"[render] 找不到 {recp}（總結階段應先產出這份）", file=sys.stderr)
        if "--vtt" not in flags:
            sys.exit(3)

    done = []
    if "--annotate-speakers" in flags and annotate_speakers(sess):
        done.append("錄音/transcript.speakers.md（註記）")
    if rec and "--summary" in flags:
        p = os.path.join(sess, "summary.md")
        open(p, "w", encoding="utf-8").write(render_summary(rec))
        done.append(f"summary.md（{rec['meeting'].get('type')} 模板）")
    if rec and "--actions" in flags:
        n = render_actions_csv(rec, os.path.join(sess, "actions.csv"))
        render_actions_ics(rec, os.path.join(sess, "actions.ics"))
        done.append(f"actions.csv / actions.ics（{n} 筆）")
    if "--vtt" in flags:
        n = render_vtt(sess, os.path.join(sess, "錄音", "transcript.vtt"))
        if n:
            done.append(f"錄音/transcript.vtt（{n} 段）")
    print(json.dumps({"status": "ok", "session": sess, "rendered": done}, ensure_ascii=False))

if __name__ == "__main__":
    main()

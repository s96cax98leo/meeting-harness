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

有錄製資料（錄音/tracks/、markers）時：summary.md 在五個必備段之後加「## 標記」「## 錄製註記」
（render_recording_sections，地端 summarize-local.py 也呼叫它）；VTT 加 NOTE 註記；
transcript.quality.json 列出的段落在衍生檔前加「（聽不清）」。沒有標記、沒有事件時輸出與 R2 相同。

--annotate-speakers 只做 錄音/transcript.speakers.md 的後處理（meeting diarize 在
_merge_speakers.py 之後呼叫）：插註記行與「（聽不清）」，冪等，不產其他檔；沒有註記可加時不改檔。

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

def _confidence_ok(v):
    """照抄 _merge_speakers.confidence_ok：confidence ≥ 0.7 才套；沒有或不是數字一律不套。"""
    try:
        return float(v["confidence"]) >= 0.7
    except (KeyError, TypeError, ValueError):
        return False

def load_name_map(path):
    """speakers.map.json → {代號: 真名}。照抄 _merge_speakers.py:79-92（main 內的套名判準）：
    dict 值有 apply 就聽 apply，沒有就看 confidence ≥ 0.7（沒有 confidence 視為未確認、不套，
    meeting-speed spec §4.6.2）；字串值直接套。不夠的不掛名（鐵則 3）。"""
    name_map = {}
    if path and os.path.exists(path):
        raw_map = json.load(open(path, encoding="utf-8"))
        for k, v in raw_map.items():
            if isinstance(v, dict):
                ok = v.get("apply") if "apply" in v else _confidence_ok(v)
                if ok and v.get("name"):
                    name_map[k] = v["name"]
            elif v:
                name_map[k] = v
    return name_map

def _fold_minor_speakers(ssegs):
    """照抄 _merge_speakers.py:101-121：MH_MIN_SPEAKER_SEC > 0 時，把總時長過短的講者併入最近的主要講者
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
    「主要段判不出來就退到含重疊那份再試一次」照抄 _merge_speakers.py:123-129。"""
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

# ── 錄製註記與標記（spec §3.18、§4.31；design R3-D5） ─────────────────────────
# 來源：錄音/tracks/record.meta.json（pauseEvents、micMuteEvents、deviceEvents）、錄音/tracks/manifest.json
# （levels、segments.startedAt）、meeting.record.json.markers（沒有才取 錄音/markers.json）。全部換成成品時間；
# 錄製時鐘 → 成品時間用 bin/lib/_record_lib.py 的 output_time（與 Swift outputTime 同一份共用向量）。
# 只寫 transport，不寫裝置名稱、uid、視窗標題（spec §4.31.7）。
LONG_SILENCE_DB = -60.0      # 兩路都 ≤ 這個值（含 null）才算靜音
LONG_SILENCE_SEC = 30.0      # 連續 ≥ 這麼久才標「長靜音」
_RECLIB = None

def _record_lib():
    """以 importlib 載入 bin/lib/_record_lib.py（不寫 .pyc）。"""
    global _RECLIB
    if _RECLIB is None:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("_record_lib", os.path.join(here, "lib", "_record_lib.py"))
        mod = importlib.util.module_from_spec(spec)
        dwb, sys.dont_write_bytecode = sys.dont_write_bytecode, True
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = dwb
        _RECLIB = mod
    return _RECLIB

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None

def _mmss(t):
    total = int(max(round(float(t), 3), 0.0))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"

def _markers(sess, rec):
    """[(t, label, speaker 或 None)]，依 t 遞增。meeting.record.json.markers 優先，沒有才取 錄音/markers.json。"""
    lib = _record_lib()
    raw = rec.get("markers") if isinstance(rec, dict) else None
    from_record = isinstance(raw, list)
    if not from_record:
        mj = _read_json(os.path.join(sess, "錄音", "markers.json"))
        raw = mj.get("markers") if isinstance(mj, dict) else mj
    out = []
    for m in raw if isinstance(raw, list) else []:
        if not isinstance(m, dict):
            continue
        t, label = lib._num(m.get("t")), m.get("label")
        if t is None or t < 0 or not isinstance(label, str) or not label.strip():
            continue
        spk = m.get("speaker") if from_record else None   # markers.json 沒有講者；不推測（鐵則 3）
        out.append((t, label.strip(), spk.strip() if isinstance(spk, str) and spk.strip() else None))
    return sorted(out, key=lambda x: x[0])

def _transport(dev):
    tr = dev.get("transport") if isinstance(dev, dict) else None
    return tr if isinstance(tr, str) and tr else "unknown"

def recording_events(sess):
    """錄製事件（成品時間）：[{kind, start, end, from, to}]，依 start 遞增。
    kind ∈ pause（end＝start＋暫停長度，不在成品時間軸上）、mute、device（end 為 None）、silence。沒有 tracks 時 []。"""
    lib = _record_lib()
    tracks = os.path.join(sess, "錄音", "tracks")
    meta = _read_json(os.path.join(tracks, "record.meta.json"))
    manifest = _read_json(os.path.join(tracks, "manifest.json"))
    meta = meta if isinstance(meta, dict) else {}
    manifest = manifest if isinstance(manifest, dict) else {}
    if not meta and not manifest:
        return []
    pauses = [e for e in (meta.get("pauseEvents") or []) if isinstance(e, dict)]
    segs = [s for s in (manifest.get("segments") or []) if isinstance(s, dict)]
    starts = [x for x in (lib._num(s.get("startedAt")) for s in segs) if x is not None]
    ends = [x for x in (lib._num(s.get("finishedAt")) for s in segs) if x is not None]
    first = min(starts) if starts else 0.0
    lv = manifest.get("levels") if isinstance(manifest.get("levels"), dict) else {}
    sysl = lv.get("system") if isinstance(lv.get("system"), list) else []
    mic = lv.get("mic") if isinstance(lv.get("mic"), list) else []
    window = lib._num(lv.get("windowSeconds")) or lib.LEVEL_WINDOW
    n = max(len(sysl), len(mic))
    record_end = max(ends + [n * window if window > 0 else 0.0] + [0.0])

    def ot(t):
        return lib.output_time(t, first, pauses)

    events = []
    pairs = lib.pause_pairs(pauses)
    for p, r in pairs:
        a = ot(p)
        events.append({"kind": "pause", "start": a, "end": round(a + max((r if r is not None else record_end) - p, 0.0), 3)})

    open_t = None
    mute_pairs = []
    for e in meta.get("micMuteEvents") or []:
        t = lib._num((e or {}).get("t")) if isinstance(e, dict) else None
        if t is None:
            continue
        if e.get("muted") is True and open_t is None:
            open_t = t
        elif e.get("muted") is False and open_t is not None:
            mute_pairs.append((open_t, t))
            open_t = None
    if open_t is not None:
        mute_pairs.append((open_t, max(record_end, open_t)))
    for a, b in mute_pairs:
        oa, ob = ot(a), ot(b)
        if ob > oa:
            events.append({"kind": "mute", "start": oa, "end": ob})

    for e in meta.get("deviceEvents") or []:
        if not isinstance(e, dict) or e.get("kind") != "output":
            continue
        t = lib._num(e.get("t"))
        if t is not None:
            events.append({"kind": "device", "start": ot(t), "end": None,
                           "from": _transport(e.get("from")), "to": _transport(e.get("to"))})

    if n and window > 0:
        def paused(c):
            return any(p <= c and (r is None or c < r) for p, r in pairs)

        def quiet(v):
            v = lib._num(v)
            return v is None or v <= LONG_SILENCE_DB

        runs, start = [], None
        for i in range(n + 1):
            ok = i < n and not paused((i + 0.5) * window) and \
                quiet(sysl[i] if i < len(sysl) else None) and quiet(mic[i] if i < len(mic) else None)
            if ok and start is None:
                start = i
            elif not ok and start is not None:
                runs.append((start * window, i * window))
                start = None
        merged = []
        for a, b in runs:                       # 成品時間軸上相接的（中間只隔暫停）視為同一段
            oa, ob = ot(a), ot(b)
            if merged and oa <= merged[-1][1] + 1e-6:
                merged[-1][1] = max(merged[-1][1], ob)
            elif ob > oa:
                merged.append([oa, ob])
        for oa, ob in merged:
            if ob - oa >= LONG_SILENCE_SEC - 1e-6:
                events.append({"kind": "silence", "start": oa, "end": ob})

    order = {"pause": 0, "mute": 1, "device": 2, "silence": 3}
    return sorted(events, key=lambda e: (e["start"], order[e["kind"]]))

_NOTE_KIND = {"pause": "暫停（未錄）", "mute": "麥克風靜音", "silence": "長靜音"}

def render_recording_sections(sess, rec=None):
    """summary.md 的「## 標記」「## 錄製註記」兩段（spec §3.18）；兩段都沒有時回 ""。
    _render.py 的 summary 與 bin/summarize-local.py 的地端 summary 都呼叫這一個函式。
    rec 為 None 時讀 <sess>/meeting.record.json（讀不到就只用 錄音/markers.json）。"""
    if rec is None:
        rec = _read_json(os.path.join(sess, "meeting.record.json"))
    out = []
    marks = _markers(sess, rec)
    if marks:
        out.append("## 標記")
        out += [f"- {_mmss(t)} {label}" + (f"（{spk}）" if spk else "") for t, label, spk in marks]
        out.append("")
    evs = recording_events(sess)
    if evs:
        out.append("## 錄製註記")
        for e in evs:
            if e["kind"] == "device":
                out.append(f"- {_mmss(e['start'])} 輸出裝置切換：{e['from']} → {e['to']}")
            else:
                out.append(f"- {_mmss(e['start'])}–{_mmss(e['end'])} {_NOTE_KIND[e['kind']]}")
        out.append("")
    return "\n".join(out).rstrip() + "\n" if out else ""

def annotation_lines(sess, rec=None):
    """逐字稿衍生檔的註記行：[(成品時間, "〔…〕")]，依時間遞增（spec §3.18 註記行）。"""
    if rec is None:
        rec = _read_json(os.path.join(sess, "meeting.record.json"))
    items = []
    for e in recording_events(sess):
        a = _mmss(e["start"])
        if e["kind"] == "pause":
            txt = f"〔暫停 {a}–{_mmss(e['end'])}，這段沒有錄〕"
        elif e["kind"] == "mute":
            txt = f"〔麥克風靜音 {a}–{_mmss(e['end'])}〕"
        elif e["kind"] == "silence":
            txt = f"〔長靜音 {a}–{_mmss(e['end'])}〕"
        else:
            txt = f"〔輸出裝置切換：{e['from']} → {e['to']}〕"
        items.append((e["start"], txt))
    items += [(t, f"〔{label}〕") for t, label, _ in _markers(sess, rec)]
    return sorted(items, key=lambda x: x[0])   # sorted 是穩定排序：同時間依事件、標記的先後

def align_index(t, segs):
    """t 對齊到哪一段（spec §4.31.3）：start ≤ t < end 掛該段；否則掛「start > t 的第一段」（兩段之間掛下一段；
    離最近一段 > 2 秒的獨立成行，在 VTT 與 speakers.md 都落在同一個位置：下一段之前）；之後沒有段落回 None（放檔尾）。"""
    for i, s in enumerate(segs):
        if s["start"] <= t < s["end"]:
            return i
    for i, s in enumerate(segs):
        if s["start"] > t:
            return i
    return None

def unclear_flags(rec_dir, segs):
    """transcript.quality.json 列出的段落（start／end 相同，容許 0.01 秒）→ 每段是否要加「（聽不清）」。"""
    q = _read_json(os.path.join(rec_dir, "transcript.quality.json"))
    spans = []
    for x in q if isinstance(q, list) else []:
        if isinstance(x, dict) and isinstance(x.get("start"), (int, float)) and isinstance(x.get("end"), (int, float)):
            spans.append((float(x["start"]), float(x["end"])))
    return [any(abs(s["start"] - a) <= 0.01 and abs(s["end"] - b) <= 0.01 for a, b in spans) for s in segs]

UNCLEAR = "（聽不清）"

def render_vtt(sess, path, rec=None):
    """逐字稿 → WebVTT。來源是 raw segments（不改 raw 本身）。
    講者歸屬與 transcript.speakers.md 相同（speaker_assigner）；只有對得到真名的講者才加 <v 名字>，
    代號與 SPEAKER_? 一律不加（鐵則 3：不確定的姓名不掛）。
    錄製註記與標記放 NOTE 區塊（不佔 cue），依 align_index 排在所掛段落的 cue 之前；
    transcript.quality.json 列出的段落文字前加「（聽不清）」（spec §4.30.6、§4.31.1）。"""
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

    cues = [(i, s) for i, s in enumerate(segs, 1) if (s.get("text") or "").strip()]
    timed = [{"start": float(s["start"]), "end": float(s["end"])} for _, s in cues]
    unclear = unclear_flags(rec_dir, timed)
    notes = {}
    for t, txt in annotation_lines(sess, rec):
        notes.setdefault(align_index(t, timed), []).append(txt)

    lines = ["WEBVTT", ""]
    for k, (i, s) in enumerate(cues):
        for txt in notes.get(k, []):
            lines += [f"NOTE {txt}", ""]
        txt = (UNCLEAR if unclear[k] else "") + (s.get("text") or "").strip()
        v = who(s)
        lines += [str(i), f"{_ts(s['start'])} --> {_ts(s['end'])}",
                  (f"<v {v}>{txt}" if v else txt), ""]
    for txt in notes.get(None, []):
        lines += [f"NOTE {txt}", ""]
    open(path, "w", encoding="utf-8").write("\n".join(lines))
    return len(segs)

_HEADER_RE = re.compile(r"\*\*\[[^\n]*\]\*\* _\( [0-9:]+ \)_")
_NOTE_RE = re.compile(r"〔[^\n]*〕")

def _rebuild_blocks(rec_dir):
    """照 _merge_speakers.py:131-144 的併段規則重建 block：[{header, text, raw_text, segs}]。
    段落與歸屬用 _merge_speakers.load_whisper_segments 與 speaker_assigner（同一套歸屬）；
    text 已在 transcript.quality.json 列出的段落前加「（聽不清）」。資料不足回 None。"""
    segp = os.path.join(rec_dir, "transcript.segments.json")
    if not os.path.isfile(segp):
        return None
    assign, names = speaker_assigner(rec_dir)
    if assign is None:
        return None
    ms = _merge_module()
    wsegs = ms.load_whisper_segments(segp)
    if not wsegs:
        return None
    unclear = unclear_flags(rec_dir, wsegs)
    blocks, cur = [], None
    for k, s in enumerate(wsegs):
        spk = assign(s)
        piece = (UNCLEAR if unclear[k] else "") + s["text"]
        if cur and spk == cur["spk"]:
            cur["raw_text"] += s["text"]
            cur["text"] += piece
            cur["segs"].append(k)
        else:
            cur = {"spk": spk, "start": s["start"], "raw_text": s["text"], "text": piece, "segs": [k]}
            blocks.append(cur)
    for b in blocks:
        b["header"] = f"**[{names.get(b['spk'], b['spk'])}]** _( {ms.fmt_ts(b['start'])} )_"
    return blocks, wsegs

def annotate_speakers(sess):
    """transcript.speakers.md 的後處理（spec §4.31.10）：在所掛段落所屬 block 的標頭行之前插註記行
    （之後沒有段落的放檔尾），並在 transcript.quality.json 列出的段落文字前加「（聽不清）」。
    以同一套歸屬重建 block；標頭數對不上時整檔不動，個別 block 的文字對不上時不動該 block，都在 stderr 記一行。
    先拿掉自己上次插的註記行再重插，所以冪等；除插入的行與「（聽不清）」外其他位元組不變。回傳是否改了檔。"""
    rec_dir = os.path.join(sess, "錄音")
    p = os.path.join(rec_dir, "transcript.speakers.md")
    if not os.path.isfile(p):
        return False
    built = _rebuild_blocks(rec_dir)
    if built is None:
        return False
    blocks, wsegs = built
    orig = open(p, encoding="utf-8").read()
    lines = orig.split("\n")
    heads = [i for i, ln in enumerate(lines) if _HEADER_RE.fullmatch(ln)]
    if len(heads) != len(blocks) or not orig.endswith("\n"):
        print(f"[render] {p}：block 數與重建結果不同（{len(heads)} ≠ {len(blocks)}），不加註記", file=sys.stderr)
        return False

    # 拆成：檔頭、各 block（標頭、文字行），去掉上次插入的註記行
    prefix = lines[:heads[0]]
    while prefix and _NOTE_RE.fullmatch(prefix[-1]):
        prefix.pop()
    bodies = []
    for j, h in enumerate(heads):
        last = j == len(heads) - 1
        region = lines[h + 1:(heads[j + 1] if not last else len(lines) - 1)]
        if last:
            k = blocks[j]["text"].count("\n") + 1
            body, tail = region[:k], region[k:]
            if any(not _NOTE_RE.fullmatch(x) for x in tail):
                print(f"[render] {p}：檔尾有無法辨識的行，不加註記", file=sys.stderr)
                return False
        else:
            while region and _NOTE_RE.fullmatch(region[-1]):
                region.pop()
            if not region or region[-1] != "":
                print(f"[render] {p}：第 {j + 1} 個 block 之後的格式與預期不同，不加註記", file=sys.stderr)
                return False
            body = region[:-1]
        bodies.append(body)

    notes = {}
    for t, txt in annotation_lines(sess):
        k = align_index(t, wsegs)
        notes.setdefault(None if k is None else next(j for j, b in enumerate(blocks) if k in b["segs"]), []).append(txt)

    out = list(prefix)
    for j, (h, b) in enumerate(zip(heads, blocks)):
        header, body = lines[h], "\n".join(bodies[j])
        if header == b["header"] and body in (b["raw_text"], b["text"]):
            body = b["text"]
        else:
            print(f"[render] {p}：第 {j + 1} 個 block 與重建結果不同，該 block 不動", file=sys.stderr)
        out += notes.get(j, []) + [header] + body.split("\n")
        if j < len(blocks) - 1:
            out.append("")
    out += notes.get(None, []) + [""]
    new = "\n".join(out)
    if new == orig:
        return False
    open(p, "w", encoding="utf-8").write(new)
    return True

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
        text = render_summary(rec)
        extra = render_recording_sections(sess, rec)
        if extra:                       # 沒有標記、沒有事件時與 R2 逐位元相同（spec §4.31.5）
            text += "\n" + extra
        open(p, "w", encoding="utf-8").write(text)
        done.append(f"summary.md（{rec['meeting'].get('type')} 模板）")
    if rec and "--actions" in flags:
        n = render_actions_csv(rec, os.path.join(sess, "actions.csv"))
        render_actions_ics(rec, os.path.join(sess, "actions.ics"))
        done.append(f"actions.csv / actions.ics（{n} 筆）")
    if "--vtt" in flags:
        n = render_vtt(sess, os.path.join(sess, "錄音", "transcript.vtt"), rec)
        if n:
            done.append(f"錄音/transcript.vtt（{n} 段）")
    print(json.dumps({"status": "ok", "session": sess, "rendered": done}, ensure_ascii=False))

if __name__ == "__main__":
    main()

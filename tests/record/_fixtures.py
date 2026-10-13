"""手寫的 spec §3.8.7 格式 windows --json 樣本（標題一律中性範例，spec §4.15 前言）。"""

ROW_KEYS = ["windowID", "app", "bundleID", "title", "untitled", "width", "height", "onScreen", "active",
            "fullScreenSized", "isMeetingApp", "meeting", "meetingTabInactive", "meetingCheck", "label"]


def row(windowID, app, bundleID, title, width, height, onScreen, active, label, *, meeting=None,
        fullScreenSized=False, meetingTabInactive=False, meetingCheck=None):
    r = {"windowID": windowID, "app": app, "bundleID": bundleID, "title": title, "untitled": title == "",
         "width": width, "height": height, "onScreen": onScreen, "active": active,
         "fullScreenSized": fullScreenSized, "isMeetingApp": meeting is not None, "meeting": meeting,
         "meetingTabInactive": meetingTabInactive, "meetingCheck": meetingCheck, "label": label}
    assert list(r) == ROW_KEYS
    return r


TEAMS_STAR = row(41001, "Microsoft Teams", "com.microsoft.teams2", "範例會議", 1280, 800, True, False,
                 "★ 會議（Teams）  Microsoft Teams — 範例會議  1280×800  背景",
                 meeting={"service": "Teams", "source": "app"})
CHROME_NOT_AUTH = row(52001, "Google Chrome", "com.google.Chrome", "範例頁面", 1200, 800, True, True,
                      "Google Chrome — 範例頁面  1200×800  前景", meetingCheck="not_authorized")
LINE_UNTITLED = row(70001, "LINE", "jp.naver.line.mac.LineCall", "", 500, 500, True, False,
                    "LINE（無標題）  500×500  背景")
PPT_UNTITLED = row(70002, "Microsoft PowerPoint", "com.microsoft.Powerpoint", "", 1197, 840, True, False,
                   "Microsoft PowerPoint（無標題）  1197×840  背景")
MPLUS_STAR = row(89596, "Google Chrome", "com.google.Chrome", "[Stand-up] 範例專案", 1496, 938, False, False,
                 "★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上",
                 meeting={"service": "M+ Meet", "source": "url"}, fullScreenSized=True, meetingCheck="ok")

# 含 ★ 列（原生 app）、無標題列、meetingCheck=not_authorized 的 Chrome 列；順序照 spec §3.8.5（★ 在前）
WINDOWS_WITH_STAR = [TEAMS_STAR, CHROME_NOT_AUTH, LINE_UNTITLED]
# 沒有 ★ 列
WINDOWS_NO_STAR = [CHROME_NOT_AUTH, PPT_UNTITLED, LINE_UNTITLED]
# Apple Events 已授權、Chrome 會議分頁有 ★
WINDOWS_MPLUS = [MPLUS_STAR, LINE_UNTITLED]


# ---------- R3（spec §3.17、§3.18、§4.30、§4.31、§4.32）：只有 JSON 的錄音目錄、meeting.record.json 樣本 ----------
# 名稱一律中性範例（spec §4.14、R3 前言）：場次「[Stand-up] 範例專案」、講者「範例甲／範例乙」。

R3_WINDOW_TITLE = "[Stand-up] 範例專案"


def write_tracks_json(rec_dir, segments, *, system=None, mic=None, window=0.5, pauses=(), mutes=(),
                      device_events=(), output_latencies=None, devices=None):
    """在 <rec_dir>/tracks/ 寫 manifest.json 與 record.meta.json（不建媒體檔）。

    segments：[(startedAt, 長度秒)]（錄製時鐘）；system／mic：levels（None＝沒有 levels 鍵）；
    pauses：[(t, "pause"|"resume")]；mutes：[(t, muted)]；device_events：[(t, kind, 舊 transport, 新 transport)]；
    output_latencies：record.meta.json.outputLatencies（None＝省略鍵）。回傳 tracks 目錄。"""
    import json
    from pathlib import Path
    from tests.record.e2e_check import record_to_output

    tracks = Path(rec_dir) / "tracks"
    tracks.mkdir(parents=True, exist_ok=True)
    first = segments[0][0] if segments else 0.0
    recs = [{"file": f"seg-{i:04d}.mov", "requestedAt": round(max(st - 0.005, 0.0), 3), "startedAt": round(st, 3),
             "finishedAt": round(st + d, 3), "width": 320, "height": 240, "audioDuration": round(d, 3)}
            for i, (st, d) in enumerate(segments, start=1)]
    manifest = {"schemaVersion": 1, "segmentSeconds": 60, "segments": recs,
                "frameStatus": {"complete": 10, "idle": 0, "blank": 0, "suspended": 0, "started": 1, "stopped": 0},
                "blackIntervals": []}
    if system is not None or mic is not None:
        manifest["levels"] = {"windowSeconds": window, "system": list(system or []), "mic": list(mic or [])}
    (tracks / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    pev = []
    for t, kind in pauses:
        e = {"t": round(t, 3), "outputT": 0.0, "wallClock": "2026-10-12T21:00:00+08:00", "kind": kind}
        e["outputT"] = record_to_output(e["t"], first, pev + [e])
        pev.append(e)
    mev = [{"t": round(t, 3), "outputT": record_to_output(round(t, 3), first, pev),
            "wallClock": "2026-10-12T21:00:00+08:00", "muted": bool(m)} for t, m in mutes]

    def dev(transport, uid=None, name=None):
        return {"uid": uid or f"uid-範例-{transport}", "name": name or f"範例裝置（{transport}）", "transport": transport}

    meta = {"schemaVersion": 1,
            "window": {"windowID": 89596, "app": "Google Chrome", "bundleID": "com.google.Chrome",
                       "title": R3_WINDOW_TITLE},
            "config": {"fps": 60, "segmentSeconds": 60},
            "devices": devices or {"input": dev("builtIn"), "output": dev("builtIn")},
            "preflight": [],
            "deviceEvents": [{"t": t, "kind": k, "from": dev(a), "to": dev(b)} for t, k, a, b in device_events],
            "audioFormatEvents": [], "pauseEvents": pev, "micMuteEvents": mev}
    if output_latencies is not None:
        meta["outputLatencies"] = output_latencies
    (tracks / "record.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return tracks


def meeting_record(*, markers=None, actions=None, title=R3_WINDOW_TITLE, mid="20261011-範例專案"):
    """schema/meeting-record.v1.json 的最小合法樣本（五個必備段都有內容；markers=None 時沒有 markers 鍵）。"""
    rec = {"schemaVersion": 1,
           "meeting": {"id": mid, "title": title, "date": "2026-10-11", "type": "internal",
                       "attendees": [{"name": "範例甲"}, {"name": "範例乙"}]},
           "summary": {"oneLiner": "範例專案本週進度確認。"},
           "decisions": [{"text": "範例決議：先完成第一階段。"}],
           "dependencies": [{"text": "範例依賴：等待測試環境。"}],
           "risks": [{"text": "範例風險：時程偏緊。"}],
           "actions": actions if actions is not None else [{"title": "範例交辦：整理需求清單", "owner": "範例甲",
                                                            "due": "2026-10-20"}],
           "uncertain": []}
    if markers is not None:
        rec["markers"] = markers
    return rec

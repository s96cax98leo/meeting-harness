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

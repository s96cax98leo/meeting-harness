// spec §3.8、§4.15.1–§4.15.9：WindowList.swift（D15 視窗清單、D16 會議標記）。
// 只以手建的 WindowCandidate／ChromeWindowInfo 餵 Core 純函式，不呼叫任何擷取或 Apple Events API。
// 範例標題一律用中性名稱（spec §4.15 前言）：M+ 會議視窗用「[Stand-up] 範例專案」，其他用「範例頁面」「範例文件」之類。
// 尺寸、windowID 81837→89596 等實測數字照 spec 引用的診斷結果。
import Foundation
import CoreGraphics

let mrtWindowListTests: [MRTCase] = [
    ("testExclusionReasons", testExclusionReasons),
    ("testMeetingServiceFromURL", testMeetingServiceFromURL),
    ("testMeetingAppService", testMeetingAppService),
    ("testChromeWindowMatching", testChromeWindowMatching),
    ("testWindowRowsOrderingAndMarks", testWindowRowsOrderingAndMarks),
    ("testWindowRowLabel", testWindowRowLabel),
    ("testFullScreenSized", testFullScreenSized),
    ("testRowsWithoutAutomation", testRowsWithoutAutomation),
    ("testWindowRowJSONKeys", testWindowRowJSONKeys),
    ("testAutomationStatusMapping", testAutomationStatusMapping),
    ("testResolveWindow", testResolveWindow),
    ("testDiagnoseIncludesExcluded", testDiagnoseIncludesExcluded),
]

let mrtMPlusTitle = "[Stand-up] 範例專案"
let mrtMPlusID: UInt32 = 89596
let mrtDisplays = [CGRect(x: 0, y: 0, width: 1496, height: 967)]

func mrtWin(_ id: UInt32, _ app: String, _ bundle: String, _ title: String, layer: Int = 0,
            x: Double = 0, y: Double = 0, w: Double, h: Double,
            onScreen: Bool = true, active: Bool = false) -> WindowCandidate {
    WindowCandidate(windowID: id, app: app, bundleID: bundle, title: title, layer: layer,
                    frame: CGRect(x: x, y: y, width: w, height: h), onScreen: onScreen, active: active)
}

func mrtChrome(_ id: UInt32, _ title: String, x: Double = 0, y: Double = 0, w: Double, h: Double,
               onScreen: Bool = true, active: Bool = false) -> WindowCandidate {
    mrtWin(id, "Google Chrome", "com.google.Chrome", title, x: x, y: y, w: w, h: h, onScreen: onScreen, active: active)
}

func mrtTabs(_ title: String, x: Double = 0, y: Double = 0, w: Double, h: Double,
             active: String, tabs: [String]? = nil) -> ChromeWindowInfo {
    ChromeWindowInfo(title: title, bounds: CGRect(x: x, y: y, width: w, height: h),
                     activeTabURL: active, tabURLs: tabs ?? [active])
}

/// spec §4.15.4 的輸入：8 個 Chrome 視窗、1 個 Teams、1 個 LINE 通話、1 個 Safari，外加 1 個會被濾掉的 Chrome 工具列。
/// 輸入順序刻意打亂，排序由 buildWindowRows 負責。
let mrtFixtureCandidates: [WindowCandidate] = [
    mrtWin(3001, "LINE", "jp.naver.line.mac.LineCall", "", x: 400, y: 200, w: 500, h: 500),
    mrtChrome(1006, "範例頁面 F", w: 1000, h: 700, onScreen: false),
    mrtChrome(1099, "", w: 1496, h: 81),                                                   // 全螢幕工具列：尺寸濾掉
    mrtChrome(1002, "範例頁面 B", x: 50, y: 60, w: 1200, h: 800, onScreen: true),         // 作用中分頁不是會議，但有會議分頁
    mrtWin(4001, "Safari", "com.apple.Safari", "範例文件", x: 20, y: 40, w: 1300, h: 850),
    mrtChrome(1005, "範例頁面 E", w: 1000, h: 700, onScreen: false),
    mrtChrome(mrtMPlusID, mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, onScreen: false),  // M+ Meet、全螢幕尺寸
    mrtWin(2001, "Microsoft Teams", "com.microsoft.teams2", "範例會議", x: 100, y: 100, w: 1280, h: 720),
    mrtChrome(1003, "範例頁面 C", x: 10, y: 30, w: 1400, h: 900, onScreen: true, active: true),
    mrtChrome(1007, "範例頁面 G", w: 900, h: 600, onScreen: false),
    mrtChrome(1004, "範例頁面 D", w: 1100, h: 750, onScreen: false),
    mrtChrome(1008, "範例頁面 H", w: 800, h: 600, onScreen: false),
]

/// Chrome 回報的視窗（順序與上面不同；標題唯一，所以全部以標題對上）。
let mrtFixtureChrome: [ChromeWindowInfo] = [
    mrtTabs("範例頁面 C", x: 10, y: 30, w: 1400, h: 900, active: "https://www.example.com/c"),
    mrtTabs("範例頁面 B", x: 50, y: 60, w: 1200, h: 800, active: "https://www.example.com/b",
            tabs: ["https://www.example.com/b", "https://meet.google.com/x"]),
    mrtTabs(mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, active: "https://meet.mplusapp.com/m/joinMeeting?shortUrl=x"),
    mrtTabs("範例頁面 D", w: 1100, h: 750, active: "https://www.example.com/d"),
    mrtTabs("範例頁面 E", w: 1000, h: 700, active: "https://www.example.com/e"),
    mrtTabs("範例頁面 F", w: 1000, h: 700, active: "https://www.example.com/f"),
    mrtTabs("範例頁面 G", w: 900, h: 600, active: "https://www.example.com/g"),
    mrtTabs("範例頁面 H", w: 800, h: 600, active: "https://www.example.com/h"),
]

/// 依 spec §3.8.5 手算的期望順序：★ 列（M+、Teams）→ active → 面積大 → windowID 小。
let mrtExpectedOrder: [UInt32] = [mrtMPlusID, 2001, 1003, 4001, 1002, 1004, 1005, 1006, 1007, 1008, 3001]

// §4.15.1：layer != 0 → .layer；寬 < 400 或高 < 300 → .size；標題不參與。
func testExclusionReasons() throws {
    // LINE 通話視窗與 PowerPoint：layer 0、無標題，仍納入
    mrtEqual(exclusionReasons(mrtWin(1, "LINE", "jp.naver.line.mac.LineCall", "", w: 500, h: 500)), [])
    mrtEqual(exclusionReasons(mrtWin(2, "Microsoft PowerPoint", "com.microsoft.Powerpoint", "", w: 1197, h: 840)), [])
    // Chrome 全螢幕時的工具列／浮層：尺寸濾掉
    for (w, h) in [(1496.0, 81.0), (1496.0, 158.0), (1016.0, 87.0), (1016.0, 139.0)] {
        mrtEqual(exclusionReasons(mrtChrome(3, "", w: w, h: h)), [.size], "\(w)×\(h)")
    }
    mrtEqual(exclusionReasons(mrtWin(4, "範例", "com.example.app", "範例文件", layer: 3, w: 800, h: 600)), [.layer])
    mrtEqual(exclusionReasons(mrtWin(5, "範例", "com.example.app", "範例文件", layer: 25, w: 300, h: 200)), [.layer, .size])
    // 恰好邊界 400×300 納入；399 或 299 濾掉
    mrtEqual(exclusionReasons(mrtWin(6, "範例", "com.example.app", "範例文件", w: 400, h: 300)), [])
    mrtEqual(exclusionReasons(mrtWin(7, "範例", "com.example.app", "範例文件", w: 399, h: 300)), [.size])
    mrtEqual(exclusionReasons(mrtWin(8, "範例", "com.example.app", "範例文件", w: 400, h: 299)), [.size])
    mrtEqual(ExclusionReason.layer.rawValue, "layer")
    mrtEqual(ExclusionReason.size.rawValue, "size")
}

// §4.15.2：meetingService(url:) 的網址表與 nil 案例。
func testMeetingServiceFromURL() throws {
    let hits: [(String, String)] = [
        ("https://meet.mplusapp.com/m/joinMeeting?shortUrl=x", "M+ Meet"),
        ("https://meet.google.com/abc-defg-hij", "Google Meet"),
        ("HTTPS://MEET.GOOGLE.COM/abc", "Google Meet"),
        ("https://teams.microsoft.com/l/meetup-join/x", "Teams"),
        ("https://teams.live.com/meet/1", "Teams"),
        ("https://us02web.zoom.us/wc/1", "Zoom"),
        ("https://zoom.us/j/1", "Zoom"),
        ("https://acme.webex.com/meet/x", "Webex"),
        ("https://webex.com/meet/x", "Webex"),
    ]
    for (url, service) in hits { mrtEqual(meetingService(url: url), service, url) }

    let misses = [
        "https://meet.mplusapp.com.evil.example/x",
        "https://notzoom.us/j/1",
        "http://meet.google.com/abc",
        "https://www.google.com/",
        "",
        "%%not a url%%",
        "https://evil.meet.mplusapp.com/x",       // 「等於」不接受子網域
        "https://meet.google.com.evil.example/x",
        "https://evilwebex.com/x",                // 「結尾」要以「.」＋網域結尾
        "ftp://zoom.us/j/1",
    ]
    for url in misses { mrtExpect(meetingService(url: url) == nil, "應回 nil：\(url)") }
}

// §4.15.2：meetingAppService(bundleID:) 的原生 app 表；瀏覽器與 LINE 回 nil。
func testMeetingAppService() throws {
    let table: [(String, String)] = [
        ("com.microsoft.teams", "Teams"), ("com.microsoft.teams2", "Teams"),
        ("us.zoom.xos", "Zoom"),
        ("Cisco-Systems.Spark", "Webex"), ("com.cisco.webexmeetingsapp", "Webex"),
        ("com.tencent.meeting", "騰訊會議"), ("com.tencent.tencentmeeting", "騰訊會議"),
    ]
    for (b, s) in table { mrtEqual(meetingAppService(bundleID: b), s, b) }
    for b in ["com.google.Chrome", "com.apple.Safari", "jp.naver.line.mac", "jp.naver.line.mac.LineCall"] {
        mrtExpect(meetingAppService(bundleID: b) == nil, "應回 nil：\(b)")
    }
    mrtEqual(chromeBundleID, "com.google.Chrome")
}

// §4.15.3：標題優先、bounds 只用來分辨同名視窗（±2 pt）。
func testChromeWindowMatching() throws {
    let frame = CGRect(x: 0, y: 29, width: 1496, height: 938)
    // (a) 標題唯一相同、bounds 不同（模擬全螢幕 bounds 不一致）→ matched
    let a = [mrtTabs("範例頁面 A", w: 800, h: 600, active: "https://www.example.com/a"),
             mrtTabs(mrtMPlusTitle, x: 0, y: 0, w: 1496, h: 967, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: a), .matched(index: 1))
    // (b) 兩個同標題、恰一個 bounds 在 ±2 pt 內 → matched 該者（差 2 pt 仍算在內）
    let b = [mrtTabs(mrtMPlusTitle, x: 300, y: 200, w: 1000, h: 700, active: "https://www.example.com/x"),
             mrtTabs(mrtMPlusTitle, x: 2, y: 27, w: 1494, h: 940, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: b), .matched(index: 1))
    // (c) 兩個同標題、bounds 都在 ±2 pt 內 → ambiguous
    let c1 = [mrtTabs(mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, active: "https://www.example.com/x"),
              mrtTabs(mrtMPlusTitle, x: 1, y: 30, w: 1495, h: 937, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: c1), .ambiguous)
    // (c) 兩個同標題、bounds 都不在 ±2 pt 內（差 3 pt 即不在）→ ambiguous
    let c2 = [mrtTabs(mrtMPlusTitle, x: 3, y: 29, w: 1496, h: 938, active: "https://www.example.com/x"),
              mrtTabs(mrtMPlusTitle, x: 500, y: 300, w: 900, h: 600, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: c2), .ambiguous)
    // (d) 沒有同標題（大小寫不同、前後多空白都不算相同）→ unmatched
    let d = [mrtTabs("範例頁面 A", x: 0, y: 29, w: 1496, h: 938, active: "https://meet.mplusapp.com/m/1"),
             mrtTabs(mrtMPlusTitle + " ", x: 0, y: 29, w: 1496, h: 938, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: d), .unmatched)
    mrtEqual(matchChromeWindow(title: mrtMPlusTitle, frame: frame, in: []), .unmatched)
    // (e) SCWindow 標題為空 → unmatched（即使 Chrome 端也有空標題的視窗）
    let e = [mrtTabs("", x: 0, y: 29, w: 1496, h: 938, active: "https://meet.mplusapp.com/m/1")]
    mrtEqual(matchChromeWindow(title: "", frame: frame, in: e), .unmatched)
}

// §4.15.4：8 個 Chrome＋Teams＋LINE＋Safari 的標記與排序（automation == .authorized）。
func testWindowRowsOrderingAndMarks() throws {
    let rows = buildWindowRows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                               chrome: mrtFixtureChrome, automation: .authorized)
    mrtEqual(rows.map { $0.windowID }, mrtExpectedOrder, "★ → active → 面積 → windowID")
    mrtExpect(!rows.contains { $0.windowID == 1099 }, "Chrome 工具列 1496×81 應被濾掉")
    let byID = Dictionary(uniqueKeysWithValues: rows.map { ($0.windowID, $0) })

    let mplus = byID[mrtMPlusID]
    mrtEqual(mplus?.meeting, MeetingMark(service: "M+ Meet", source: "url"))
    mrtEqual(mplus?.meetingCheck, "ok")
    mrtEqual(mplus?.fullScreenSized, true)
    mrtEqual(mplus?.untitled, false)
    mrtEqual(mplus?.width, 1496); mrtEqual(mplus?.height, 938)
    mrtEqual(mplus?.onScreen, false); mrtEqual(mplus?.active, false)
    mrtEqual(mplus?.title, mrtMPlusTitle)
    mrtEqual(mplus?.app, "Google Chrome")

    mrtEqual(byID[2001]?.meeting, MeetingMark(service: "Teams", source: "app"))
    mrtExpect(byID[2001]?.meetingCheck == nil, "非 Chrome 列 meetingCheck 為 nil")

    let inactive = byID[1002]
    mrtExpect(inactive?.meeting == nil, "作用中分頁不是會議 → 不標 ★")
    mrtEqual(inactive?.meetingTabInactive, true)
    mrtEqual(inactive?.meetingCheck, "ok")

    for id: UInt32 in [1003, 1004, 1005, 1006, 1007, 1008] {
        mrtExpect(byID[id]?.meeting == nil, "Chrome \(id) 不得標 ★")
        mrtEqual(byID[id]?.meetingTabInactive, false, "Chrome \(id)")
        mrtEqual(byID[id]?.meetingCheck, "ok", "Chrome \(id) 以標題對上")
    }
    mrtExpect(byID[3001] != nil, "LINE 列應存在於輸出中")
    mrtExpect(byID[3001]?.meeting == nil, "LINE 不標 ★")
    mrtEqual(byID[3001]?.untitled, true)
    mrtExpect(byID[3001]?.meetingCheck == nil)
    mrtExpect(byID[4001]?.meeting == nil, "Safari 不標 ★")
    mrtExpect(byID[4001]?.meetingCheck == nil)

    for r in rows {
        mrtEqual(r.isMeetingApp, r.meeting != nil, "isMeetingApp == (meeting != nil)：\(r.windowID)")
        mrtEqual(r.label, windowRowLabel(r), "label 欄即 windowRowLabel：\(r.windowID)")
    }
    // 所有 ★ 列在非 ★ 列之前
    let stars = rows.map { $0.meeting != nil }
    mrtEqual(stars, stars.sorted { $0 && !$1 }, "★ 列應全部排在前面")
    mrtEqual(stars.filter { $0 }.count, 2)
}

// §4.15.5：windowRowLabel 依 §3.8.6；§3.8.6 的兩個例子逐字相等。
func testWindowRowLabel() throws {
    let mplus = WindowListRow(windowID: mrtMPlusID, app: "Google Chrome", bundleID: "com.google.Chrome", title: mrtMPlusTitle,
                              untitled: false, width: 1496, height: 938, onScreen: false, active: false, fullScreenSized: true,
                              isMeetingApp: true, meeting: MeetingMark(service: "M+ Meet", source: "url"),
                              meetingTabInactive: false, meetingCheck: "ok", label: "")
    mrtEqual(windowRowLabel(mplus), "★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上")

    let line = WindowListRow(windowID: 3001, app: "LINE", bundleID: "jp.naver.line.mac.LineCall", title: "",
                             untitled: true, width: 500, height: 500, onScreen: true, active: true, fullScreenSized: false,
                             isMeetingApp: false, meeting: nil, meetingTabInactive: false, meetingCheck: nil, label: "")
    mrtEqual(windowRowLabel(line), "LINE（無標題）  500×500  前景")

    // 背景；有會議分頁但沒在顯示 → 以提示結尾
    let bg = WindowListRow(windowID: 1002, app: "Google Chrome", bundleID: "com.google.Chrome", title: "範例頁面 B",
                           untitled: false, width: 1200, height: 800, onScreen: true, active: false, fullScreenSized: false,
                           isMeetingApp: false, meeting: nil, meetingTabInactive: true, meetingCheck: "ok", label: "")
    let bgLabel = windowRowLabel(bg)
    mrtEqual(bgLabel, "Google Chrome — 範例頁面 B  1200×800  背景  （這個視窗有會議分頁，但目前顯示的不是它）")
    mrtExpect(bgLabel.hasSuffix("（這個視窗有會議分頁，但目前顯示的不是它）"))

    // 原生會議 app 的 ★
    let teams = WindowListRow(windowID: 2001, app: "Microsoft Teams", bundleID: "com.microsoft.teams2", title: "範例會議",
                              untitled: false, width: 1280, height: 720, onScreen: true, active: false, fullScreenSized: false,
                              isMeetingApp: true, meeting: MeetingMark(service: "Teams", source: "app"),
                              meetingTabInactive: false, meetingCheck: nil, label: "")
    mrtEqual(windowRowLabel(teams), "★ 會議（Teams）  Microsoft Teams — 範例會議  1280×720  背景")

    // buildWindowRows 算出的 M+ 列 label 也等於 §3.8.6 例子
    let rows = buildWindowRows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                               chrome: mrtFixtureChrome, automation: .authorized)
    mrtEqual(rows.first { $0.windowID == mrtMPlusID }?.label,
             "★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上")
    mrtEqual(rows.first { $0.windowID == 3001 }?.label, "LINE（無標題）  500×500  背景")
}

// §4.15.5：isFullScreenSized：|寬差| ≤ 2 且 高 ≥ 顯示器高 − 40。
func testFullScreenSized() throws {
    let d = mrtDisplays
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 29, width: 1496, height: 938), displays: d), true)
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1197, height: 840), displays: d), false)
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1496, height: 900), displays: d), false)
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1494, height: 927), displays: d), true, "邊界：寬差 2、高差 40")
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1493, height: 967), displays: d), false, "寬差 3")
    // 多顯示器：任一顯示器符合即可
    let two = d + [CGRect(x: 1496, y: 0, width: 1920, height: 1080)]
    mrtEqual(isFullScreenSized(frame: CGRect(x: 1496, y: 25, width: 1920, height: 1055), displays: two), true)
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1920, height: 1055), displays: d), false)
    mrtEqual(isFullScreenSized(frame: CGRect(x: 0, y: 0, width: 1496, height: 938), displays: []), false)
}

// §4.15.6：沒有授權時清單照常、Chrome 列沒有 ★ 且 meetingCheck 為 automation 的 raw value。
func testRowsWithoutAutomation() throws {
    let authorized = buildWindowRows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                                     chrome: mrtFixtureChrome, automation: .authorized)
    let expected: [(AutomationStatus, String)] = [
        (.notAuthorized, "not_authorized"), (.notDetermined, "not_determined"),
        (.chromeNotRunning, "chrome_not_running"), (.error, "error"),
    ]
    for (status, raw) in expected {
        let rows = buildWindowRows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                                   chrome: mrtFixtureChrome, automation: status)
        mrtEqual(Set(rows.map { $0.windowID }), Set(authorized.map { $0.windowID }), "\(raw)：windowID 集合不變")
        mrtEqual(rows.count, authorized.count, raw)
        for r in rows where r.bundleID == "com.google.Chrome" {
            mrtExpect(r.meeting == nil, "\(raw)：Chrome \(r.windowID) 不得有 ★")
            mrtExpect(!r.label.contains("★"), "\(raw)：Chrome \(r.windowID) label 不得有 ★")
            mrtEqual(r.meetingCheck, raw, "\(raw)：Chrome \(r.windowID)")
            mrtEqual(r.meetingTabInactive, false, "\(raw)：忽略 chrome 時不判斷分頁")
            mrtEqual(r.isMeetingApp, false)
        }
        mrtEqual(rows.first { $0.windowID == 2001 }?.meeting, MeetingMark(service: "Teams", source: "app"),
                 "\(raw)：原生會議 app 的 ★ 不受影響")
        mrtEqual(rows.filter { $0.meeting != nil }.map { $0.windowID }, [2001], raw)
        mrtEqual(rows.first?.windowID, 2001, "\(raw)：唯一的 ★ 列排第一")
        mrtExpect(rows.first { $0.windowID == 3001 }?.meetingCheck == nil, "\(raw)：非 Chrome 列 meetingCheck 為 nil")
    }
    mrtEqual(AutomationStatus.authorized.rawValue, "authorized")
}

// §4.15.7：WindowListRow 的 JSON 鍵恰為 15 個；nil 寫 null 不省略；DiagnosedWindow 的鍵。
func testWindowRowJSONKeys() throws {
    let keys: Set<String> = ["windowID", "app", "bundleID", "title", "untitled", "width", "height", "onScreen", "active",
                             "fullScreenSized", "isMeetingApp", "meeting", "meetingTabInactive", "meetingCheck", "label"]
    let plain = WindowListRow(windowID: 3001, app: "LINE", bundleID: "jp.naver.line.mac.LineCall", title: "",
                              untitled: true, width: 500, height: 500, onScreen: true, active: true, fullScreenSized: false,
                              isMeetingApp: false, meeting: nil, meetingTabInactive: false, meetingCheck: nil,
                              label: "LINE（無標題）  500×500  前景")
    let o1 = mrtJSONObject(plain)
    mrtEqual(Set(o1.keys), keys)
    mrtExpect(mrtIsNull(o1["meeting"]), "meeting 為 nil 時應寫 null")
    mrtExpect(mrtIsNull(o1["meetingCheck"]), "meetingCheck 為 nil 時應寫 null")
    mrtEqual(o1["windowID"] as? Int, 3001)
    mrtEqual(o1["label"] as? String, "LINE（無標題）  500×500  前景")

    let rows = buildWindowRows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                               chrome: mrtFixtureChrome, automation: .authorized)
    guard let star = rows.first else { mrtExpect(false, "buildWindowRows 沒有輸出"); return }
    let o2 = mrtJSONObject(star)
    mrtEqual(Set(o2.keys), keys)
    mrtEqual(mrtKeys(o2["meeting"]), ["service", "source"])
    mrtEqual((o2["meeting"] as? [String: Any])?["service"] as? String, "M+ Meet")
    mrtEqual((o2["meeting"] as? [String: Any])?["source"] as? String, "url")
    mrtEqual(o2["meetingCheck"] as? String, "ok")
    // 網址不落地：輸出只有服務名
    let text = String(decoding: (try? JSONEncoder().encode(rows)) ?? Data(), as: UTF8.self)
    mrtExpect(!text.contains("mplusapp.com") && !text.contains("example.com") && !text.contains("meet.google.com"),
              "windows --json 不得含分頁網址")

    let diag = diagnoseWindows(candidates: mrtFixtureCandidates, displays: mrtDisplays,
                               chrome: mrtFixtureChrome, automation: .authorized)
    guard let first = diag.first else { mrtExpect(false, "diagnoseWindows 沒有輸出"); return }
    let o3 = mrtJSONObject(first)
    mrtEqual(Set(o3.keys), ["row", "layer", "x", "y", "excludedBy"])
    mrtEqual(mrtKeys(o3["row"]), keys)
    if let toolbar = diag.first(where: { $0.row.windowID == 1099 }) {
        let o4 = mrtJSONObject(toolbar)
        mrtEqual((o4["excludedBy"] as? [String]) ?? [], ["size"])
    } else {
        mrtExpect(false, "diagnoseWindows 應含被濾掉的 1099")
    }
}

// §4.15.7：automationStatus(fromOSStatus:) 的對映。
func testAutomationStatusMapping() throws {
    mrtEqual(automationStatus(fromOSStatus: 0), .authorized)
    mrtEqual(automationStatus(fromOSStatus: -1743), .notAuthorized)
    mrtEqual(automationStatus(fromOSStatus: -1744), .notDetermined)
    mrtEqual(automationStatus(fromOSStatus: -600), .chromeNotRunning)
    mrtEqual(automationStatus(fromOSStatus: -1), .error)
    mrtEqual(automationStatus(fromOSStatus: -1712), .error)
    mrtEqual([AutomationStatus.authorized, .notAuthorized, .notDetermined, .chromeNotRunning, .error].map { $0.rawValue },
             ["authorized", "not_authorized", "not_determined", "chrome_not_running", "error"])
}

// §4.15.8：windowID 優先；找不到才以 (bundleID, 標題) 在通過篩選的視窗中唯一認回。
func testResolveWindow() throws {
    let mplus = mrtChrome(mrtMPlusID, mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, onScreen: false)
    let other = mrtChrome(1003, "範例頁面 C", w: 1400, h: 900)
    let toolbarSameTitle = mrtChrome(1099, mrtMPlusTitle, w: 1496, h: 81)
    let ref = WindowRef(windowID: 81837, bundleID: "com.google.Chrome", title: mrtMPlusTitle)

    // windowID 存在 → exact（有沒有附 bundleID／title 都一樣）
    mrtEqual(resolveWindow(WindowRef(windowID: mrtMPlusID, bundleID: nil, title: nil), in: [other, mplus]), .exact(mrtMPlusID))
    mrtEqual(resolveWindow(WindowRef(windowID: 1003, bundleID: "com.google.Chrome", title: mrtMPlusTitle), in: [other, mplus]),
             .exact(1003))
    // candidates 是未篩選的全部視窗：windowID 存在即 exact
    mrtEqual(resolveWindow(WindowRef(windowID: 1099, bundleID: nil, title: nil), in: [toolbarSameTitle]), .exact(1099))

    // 81837 不存在、同 bundleID 與標題的 89596 唯一存在且通過篩選 → reidentified(89596)
    mrtEqual(resolveWindow(ref, in: [other, mplus]), .reidentified(mrtMPlusID))
    // 同 bundleID、同標題但 exclusionReasons 非空的視窗不得被認回
    mrtEqual(resolveWindow(ref, in: [other, toolbarSameTitle]), .notFound)
    mrtEqual(resolveWindow(ref, in: [toolbarSameTitle, mplus]), .reidentified(mrtMPlusID), "被濾掉的同名視窗不算第二個")
    // 同 bundleID 與標題的視窗有兩個 → ambiguous
    let twin = mrtChrome(89600, mrtMPlusTitle, x: 100, y: 100, w: 1200, h: 800)
    mrtEqual(resolveWindow(ref, in: [mplus, twin, other]), .ambiguous)
    // 沒有 → notFound
    mrtEqual(resolveWindow(ref, in: [other]), .notFound)
    mrtEqual(resolveWindow(ref, in: []), .notFound)
    // 標題相同但 bundleID 不同 → 不算
    let safariSame = mrtWin(4001, "Safari", "com.apple.Safari", mrtMPlusTitle, w: 1300, h: 850)
    mrtEqual(resolveWindow(ref, in: [safariSame]), .notFound)
    // ref 沒有 bundleID／title（使用者自己打 --window <id>）→ notFound，不猜
    mrtEqual(resolveWindow(WindowRef(windowID: 81837, bundleID: nil, title: nil), in: [mplus]), .notFound)
    mrtEqual(resolveWindow(WindowRef(windowID: 81837, bundleID: "com.google.Chrome", title: nil), in: [mplus]), .notFound)
    mrtEqual(resolveWindow(WindowRef(windowID: 81837, bundleID: nil, title: mrtMPlusTitle), in: [mplus]), .notFound)
    // 無標題的 LINE 通話視窗可依 ("jp.naver.line.mac.LineCall", "") 認回
    let line = mrtWin(70123, "LINE", "jp.naver.line.mac.LineCall", "", w: 500, h: 500)
    mrtEqual(resolveWindow(WindowRef(windowID: 70000, bundleID: "jp.naver.line.mac.LineCall", title: ""), in: [mplus, line]),
             .reidentified(70123))
}

// §4.15.9：diagnoseWindows 對每個輸入視窗輸出一筆（含被濾掉的），順序＝輸入順序，excludedBy＝exclusionReasons。
func testDiagnoseIncludesExcluded() throws {
    let input: [WindowCandidate] = [
        mrtChrome(5, "", x: 0, y: 0, w: 1496, h: 81),
        mrtChrome(mrtMPlusID, mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, onScreen: false),
        mrtWin(7, "範例", "com.example.app", "範例浮層", layer: 25, x: 12, y: 34, w: 300, h: 200),
        mrtWin(8, "LINE", "jp.naver.line.mac.LineCall", "", x: 400, y: 200, w: 500, h: 500),
        mrtWin(9, "範例", "com.example.app", "範例面板", layer: 3, x: -100, y: 50, w: 800, h: 600),
    ]
    let chrome = [mrtTabs(mrtMPlusTitle, x: 0, y: 29, w: 1496, h: 938, active: "https://meet.mplusapp.com/m/1")]
    let diag = diagnoseWindows(candidates: input, displays: mrtDisplays, chrome: chrome, automation: .authorized)
    mrtEqual(diag.count, input.count, "每個輸入視窗一筆")
    mrtEqual(diag.map { $0.row.windowID }, input.map { $0.windowID }, "順序＝輸入順序")
    for (d, w) in zip(diag, input) {
        mrtEqual(d.excludedBy, exclusionReasons(w), "\(w.windowID)")
        mrtEqual(d.layer, w.layer, "\(w.windowID)")
        mrtEqual(d.x, Int(w.frame.origin.x), "\(w.windowID)")
        mrtEqual(d.y, Int(w.frame.origin.y), "\(w.windowID)")
    }
    mrtEqual(diag.map { $0.excludedBy }, [[.size], [], [.layer, .size], [], [.layer]])
    // row 依 §3.8.2、§3.8.6 計算：M+ 列有 ★、label 與清單相同
    let m = diag.first { $0.row.windowID == mrtMPlusID }?.row
    mrtEqual(m?.meeting, MeetingMark(service: "M+ Meet", source: "url"))
    mrtEqual(m?.label, "★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上")
    mrtEqual(diag.first { $0.row.windowID == 8 }?.row.label, "LINE（無標題）  500×500  背景")
    // 沒有授權時一樣列出全部
    let noAuth = diagnoseWindows(candidates: input, displays: mrtDisplays, chrome: chrome, automation: .notDetermined)
    mrtEqual(noAuth.map { $0.row.windowID }, input.map { $0.windowID })
}

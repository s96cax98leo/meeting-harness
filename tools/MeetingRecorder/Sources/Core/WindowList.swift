// Core/WindowList.swift —— 視窗清單的篩選、會議標記、排序、顯示、認回與診斷（spec §3.4、§3.8；D15、D16）
// 純函式：SCK 與 Apple Events 的呼叫在 Capture/，這裡只吃手建得出來的值，方便單元測試。
// 分頁網址只在這裡比對，不出現在任何輸出結構（WindowListRow 只有服務名）。
import CoreGraphics
import Foundation

struct WindowCandidate: Equatable {
    var windowID: UInt32
    var app: String
    var bundleID: String
    var title: String       // 無標題為 ""
    var layer: Int
    var frame: CGRect       // point
    var onScreen: Bool
    var active: Bool
}

enum ExclusionReason: String, Codable { case layer, size }

/// §3.8.1：依 layer、size 的順序列出；空陣列＝納入。標題不參與。
func exclusionReasons(_ w: WindowCandidate) -> [ExclusionReason] {
    var out: [ExclusionReason] = []
    if w.layer != 0 { out.append(.layer) }
    if w.frame.width < 400 || w.frame.height < 300 { out.append(.size) }
    return out
}

/// §3.8.6：存在某顯示器 d 使 |寬差| ≤ 2 且 高 ≥ d.高 − 40。只描述尺寸，不宣稱是 native 全螢幕。
func isFullScreenSized(frame: CGRect, displays: [CGRect]) -> Bool {
    displays.contains { d in
        abs(frame.width - d.width) <= 2 + 1e-9 && frame.height >= d.height - 40 - 1e-9
    }
}

/// §3.8.2 網址表：scheme 必須是 https；host 轉小寫後「等於」或「結尾（完全相同或以 .網域 結尾）」。
func meetingService(url: String) -> String? {
    guard let comps = URLComponents(string: url),
          comps.scheme?.lowercased() == "https",
          let host = comps.host?.lowercased(), !host.isEmpty else { return nil }
    let equals: [(String, String)] = [
        ("meet.mplusapp.com", "M+ Meet"), ("meet.google.com", "Google Meet"),
        ("teams.microsoft.com", "Teams"), ("teams.live.com", "Teams"),
    ]
    for (h, s) in equals where host == h { return s }
    let suffixes: [(String, String)] = [("zoom.us", "Zoom"), ("webex.com", "Webex")]
    for (d, s) in suffixes where host == d || host.hasSuffix("." + d) { return s }
    return nil
}

/// §3.8.2 原生會議 app 表；瀏覽器、LINE 等回 nil。
func meetingAppService(bundleID: String) -> String? {
    switch bundleID {
    case "com.microsoft.teams", "com.microsoft.teams2": return "Teams"
    case "us.zoom.xos": return "Zoom"
    case "Cisco-Systems.Spark", "com.cisco.webexmeetingsapp": return "Webex"
    case "com.tencent.meeting", "com.tencent.tencentmeeting": return "騰訊會議"
    default: return nil
    }
}

let chromeBundleID: String = "com.google.Chrome"

struct ChromeWindowInfo: Equatable {
    var title: String
    var bounds: CGRect
    var activeTabURL: String
    var tabURLs: [String]
}

enum ChromeMatch: Equatable { case matched(index: Int), unmatched, ambiguous }

/// §3.8.3：標題完全相同優先；同名 2 個以上才用 bounds（x、y、寬、高各差 ≤ 2 pt）分辨；對不上不猜。
func matchChromeWindow(title: String, frame: CGRect, in chrome: [ChromeWindowInfo]) -> ChromeMatch {
    guard !title.isEmpty else { return .unmatched }
    let same = chrome.indices.filter { chrome[$0].title == title }
    if same.isEmpty { return .unmatched }
    if same.count == 1 { return .matched(index: same[0]) }
    func near(_ a: CGFloat, _ b: CGFloat) -> Bool { abs(a - b) <= 2 + 1e-9 }
    let close = same.filter { i in
        let b = chrome[i].bounds
        return near(b.origin.x, frame.origin.x) && near(b.origin.y, frame.origin.y)
            && near(b.width, frame.width) && near(b.height, frame.height)
    }
    return close.count == 1 ? .matched(index: close[0]) : .ambiguous
}

enum AutomationStatus: String, Codable {
    case authorized, notAuthorized = "not_authorized", notDetermined = "not_determined",
         chromeNotRunning = "chrome_not_running", error
}

/// §3.8.4：0／-1743／-1744／-600／其他。
func automationStatus(fromOSStatus status: Int32) -> AutomationStatus {
    switch status {
    case 0: return .authorized
    case -1743: return .notAuthorized       // errAEEventNotPermitted
    case -1744: return .notDetermined       // errAEEventWouldRequireUserConsent
    case -600: return .chromeNotRunning     // procNotFound
    default: return .error
    }
}

struct MeetingMark: Codable, Equatable {
    var service: String
    var source: String      // "url"｜"app"
}

struct WindowListRow: Codable, Equatable {
    var windowID: UInt32
    var app: String
    var bundleID: String
    var title: String
    var untitled: Bool
    var width: Int
    var height: Int
    var onScreen: Bool
    var active: Bool
    var fullScreenSized: Bool
    var isMeetingApp: Bool
    var meeting: MeetingMark?
    var meetingTabInactive: Bool
    var meetingCheck: String?
    var label: String

    // JSON 鍵恰為 15 個；meeting、meetingCheck 為 nil 時寫 null（不得省略鍵）。
    enum CodingKeys: String, CodingKey {
        case windowID, app, bundleID, title, untitled, width, height, onScreen, active, fullScreenSized,
             isMeetingApp, meeting, meetingTabInactive, meetingCheck, label
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(windowID, forKey: .windowID)
        try c.encode(app, forKey: .app)
        try c.encode(bundleID, forKey: .bundleID)
        try c.encode(title, forKey: .title)
        try c.encode(untitled, forKey: .untitled)
        try c.encode(width, forKey: .width)
        try c.encode(height, forKey: .height)
        try c.encode(onScreen, forKey: .onScreen)
        try c.encode(active, forKey: .active)
        try c.encode(fullScreenSized, forKey: .fullScreenSized)
        try c.encode(isMeetingApp, forKey: .isMeetingApp)
        try c.encode(meeting, forKey: .meeting)
        try c.encode(meetingTabInactive, forKey: .meetingTabInactive)
        try c.encode(meetingCheck, forKey: .meetingCheck)
        try c.encode(label, forKey: .label)
    }
}

/// §3.8.6：片段之間兩個半形空白。
func windowRowLabel(_ row: WindowListRow) -> String {
    var parts: [String] = []
    if let m = row.meeting { parts.append("★ 會議（\(m.service)）") }
    parts.append(row.untitled ? "\(row.app)（無標題）" : "\(row.app) — \(row.title)")
    parts.append("\(row.width)×\(row.height)")
    if row.fullScreenSized { parts.append("全螢幕尺寸") }
    parts.append(row.onScreen ? (row.active ? "前景" : "背景") : "不在畫面上")
    if row.meetingTabInactive { parts.append("（這個視窗有會議分頁，但目前顯示的不是它）") }
    return parts.joined(separator: "  ")
}

/// 單一視窗依 §3.8.2、§3.8.6 算出一列（不篩選、不排序）。automation != .authorized 時忽略 chrome。
private func makeRow(_ w: WindowCandidate, displays: [CGRect],
                     chrome: [ChromeWindowInfo], automation: AutomationStatus) -> WindowListRow {
    var meeting: MeetingMark?
    var tabInactive = false
    var check: String?
    if let s = meetingAppService(bundleID: w.bundleID) {
        meeting = MeetingMark(service: s, source: "app")
    } else if w.bundleID == chromeBundleID {
        if automation != .authorized {
            check = automation.rawValue
        } else {
            switch matchChromeWindow(title: w.title, frame: w.frame, in: chrome) {
            case .matched(let i):
                check = "ok"
                if let s = meetingService(url: chrome[i].activeTabURL) {
                    meeting = MeetingMark(service: s, source: "url")
                } else if chrome[i].tabURLs.contains(where: { meetingService(url: $0) != nil }) {
                    tabInactive = true
                }
            case .unmatched: check = "unmatched"
            case .ambiguous: check = "ambiguous"
            }
        }
    }
    var row = WindowListRow(
        windowID: w.windowID, app: w.app, bundleID: w.bundleID, title: w.title, untitled: w.title.isEmpty,
        width: Int(w.frame.width.rounded()), height: Int(w.frame.height.rounded()),
        onScreen: w.onScreen, active: w.active,
        fullScreenSized: isFullScreenSized(frame: w.frame, displays: displays),
        isMeetingApp: meeting != nil, meeting: meeting, meetingTabInactive: tabInactive,
        meetingCheck: check, label: "")
    row.label = windowRowLabel(row)
    return row
}

/// §3.8.1 篩選＋§3.8.2 標記＋§3.8.5 排序（★ → active → 面積大 → windowID 小）＋§3.8.6 label。
func buildWindowRows(candidates: [WindowCandidate], displays: [CGRect],
                     chrome: [ChromeWindowInfo], automation: AutomationStatus) -> [WindowListRow] {
    let kept = candidates.filter { exclusionReasons($0).isEmpty }
    let pairs = kept.map { (w: $0, row: makeRow($0, displays: displays, chrome: chrome, automation: automation)) }
    return pairs.sorted { a, b in
        let sa = a.row.meeting != nil, sb = b.row.meeting != nil
        if sa != sb { return sa }
        if a.w.active != b.w.active { return a.w.active }
        let aa = a.w.frame.width * a.w.frame.height, ab = b.w.frame.width * b.w.frame.height
        if aa != ab { return aa > ab }
        return a.w.windowID < b.w.windowID
    }.map { $0.row }
}

struct DiagnosedWindow: Codable, Equatable {
    var row: WindowListRow
    var layer: Int
    var x: Int
    var y: Int
    var excludedBy: [ExclusionReason]
}

/// §3.8.9：每個 candidate 一筆（含被濾掉的），順序＝輸入順序。
func diagnoseWindows(candidates: [WindowCandidate], displays: [CGRect],
                     chrome: [ChromeWindowInfo], automation: AutomationStatus) -> [DiagnosedWindow] {
    candidates.map { w in
        DiagnosedWindow(row: makeRow(w, displays: displays, chrome: chrome, automation: automation),
                        layer: w.layer, x: Int(w.frame.origin.x.rounded()), y: Int(w.frame.origin.y.rounded()),
                        excludedBy: exclusionReasons(w))
    }
}

struct WindowRef: Equatable {
    var windowID: UInt32
    var bundleID: String?
    var title: String?
}

enum WindowResolution: Equatable { case exact(UInt32), reidentified(UInt32), notFound, ambiguous }

/// §3.8.8：windowID 優先；找不到時，bundleID 與 title 都有值才在通過篩選的視窗中唯一認回；不猜。
/// candidates 是當下全部 SCShareableContent.windows（未篩選）。
func resolveWindow(_ ref: WindowRef, in candidates: [WindowCandidate]) -> WindowResolution {
    if candidates.contains(where: { $0.windowID == ref.windowID }) { return .exact(ref.windowID) }
    guard let bundle = ref.bundleID, let title = ref.title else { return .notFound }
    let hits = candidates.filter { exclusionReasons($0).isEmpty && $0.bundleID == bundle && $0.title == title }
    switch hits.count {
    case 0: return .notFound
    case 1: return .reidentified(hits[0].windowID)
    default: return .ambiguous
    }
}

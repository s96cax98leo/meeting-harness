// Trigger/QuickStart.swift —— quick-start：用上次的設定開錄（design §8；spec §4.11.1、§4.21.3）
// 判斷交給 Core：沒帶 --window 時 quickStartDecision（★ 列恰好一個才開錄，不猜）；
// 帶 --window 時 resolveWindow＋explicitWindowDecision；存檔位置一律 quickStartRoot（--root ＞ menubar.prefs.json ＞ record.defaults.json）。
// 不跳 Apple Events 授權框。
import Foundation

func cmdQuickStart(_ args: Args) async {
    let home = recordHome(args)
    let log = Logger(path: home.appendingPathComponent("record.log").path, append: true)
    log.line("── quick-start \(isoNow()) ──")
    let defaults = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))
    let prefs = loadMenuBarPrefs(home.appendingPathComponent(menuBarPrefsFileName))   // 只讀 root（spec §3.13）

    func fail(_ code: Int32, _ message: String, rows: [WindowListRow] = []) -> Never {
        var body = message
        if code == 3, chromeAutomationHint(rows, include: ["not_authorized", "not_determined"]) {
            body += "\nChrome 會議分頁要允許 Apple Events 才標得出來（系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome）"
        }
        Notifier.post(title: "MeetingRecorder 沒有開錄", body: body, log: log)
        exit(code)
    }

    let listing: WindowListing
    do {
        listing = try await WindowListing.load(askAutomation: false)
    } catch {
        Notifier.post(title: "MeetingRecorder 沒有開錄",
                      body: "取不到視窗清單：螢幕錄製權限沒給，或授權後還沒完全結束 MeetingRecorder 再重開", log: log)
        exit(4)
    }
    let rows = listing.rows

    // --window：選單「錄這個視窗」指定的視窗——以 resolveWindow 認回，不經 ★ 恰好一個的判斷（spec §4.21.3）。
    // 沒帶 --window：與第一輪相同，★ 列恰好一個才開錄（spec §4.11.1）。
    let decision: QuickStartDecision
    var explicitRef: WindowRef?
    if let w = args.str("window") {
        guard let wid = UInt32(w) else { fail(2, "--window 不是數字：\(w)") }
        let bundle = args.str("window-bundle"), title = args.str("window-title")
        // 與 preflight 相同：--window-bundle 與 --window-title 都給才用來認回，只給一個時只認 windowID（不猜）
        let ref = (bundle != nil && title != nil) ? WindowRef(windowID: wid, bundleID: bundle, title: title)
                                                  : WindowRef(windowID: wid, bundleID: nil, title: nil)
        explicitRef = ref
        decision = explicitWindowDecision(hasDefaults: defaults != nil,
                                          resolution: resolveWindow(ref, in: listing.candidates))
    } else {
        let starred = rows.filter { $0.meeting != nil }.map { $0.windowID }
        decision = quickStartDecision(hasDefaults: defaults != nil, starredWindowIDs: starred)
    }

    switch decision {
    case .fail(let code, let message):
        fail(code, message, rows: explicitRef == nil ? rows : [])
    case .start(let windowID):
        guard let defaults else { exit(2) }
        let root: String
        switch quickStartRoot(argRoot: args.str("root"), prefsRoot: prefs.root, defaultsRoot: defaults.root,
                              isDirectory: { p in
                                  var dir: ObjCBool = false
                                  return FileManager.default.fileExists(atPath: p, isDirectory: &dir) && dir.boolValue
                              }) {
        case .use(let r): root = r
        case .fail(let code, let message): fail(code, message)
        }
        // 認回時視窗資訊以當下的那一列為準；不在篩選後清單（例如 exact 命中被濾掉的視窗）時沿用參數給的
        let row = rows.first(where: { $0.windowID == windowID })
        let windowRef = WindowRef(windowID: windowID, bundleID: row?.bundleID ?? explicitRef?.bundleID,
                                  title: row?.title ?? explicitRef?.title)
        let now = Date()
        let day = DateFormatter()
        day.dateFormat = "yyyyMMdd"
        let hm = DateFormatter()
        hm.dateFormat = "HHmm"
        let session = URL(fileURLWithPath: root, isDirectory: true)
            .appendingPathComponent(day.string(from: now), isDirectory: true)
            .appendingPathComponent("\(hm.string(from: now)) 會議", isDirectory: true)
        let ctx = RunContext(home: home, runId: UUID().uuidString, session: session,
                             minFreeBytes: defaults.minFreeBytes ?? fallbackMinFreeBytes(),
                             windowRef: windowRef, harness: defaults.harness, log: log)
        log.line("● quick-start：視窗 [\(windowID)]、場次 \(session.path)")
        Notifier.post(title: "MeetingRecorder 開錄前檢查", body: "檢查約 10 秒；可以對麥克風說一句話（沒說也會照常開錄）", log: log)
        await runPreflightThenRecord(ctx, start: true, defaults: defaults, notifyWarnings: true) {
            try writeMeetingJSON(ctx: ctx, defaults: defaults, date: now)
        }
    }
}

/// 錄音/meeting.json：key 集合與 bin/_scaffold.py 寫入的 7 個相同；expectedSpeakers 固定 null（spec §3.6）。
/// 已存在就不覆寫。meeting.json 不是音源副檔名，不會讓場次提早出現。
func writeMeetingJSON(ctx: RunContext, defaults: RecordDefaults, date: Date) throws {
    let url = ctx.recordingDir.appendingPathComponent("meeting.json")
    guard !FileManager.default.fileExists(atPath: url.path) else { return }
    let f = DateFormatter()
    f.dateFormat = "yyyy-MM-dd"
    let obj: [String: Any] = [
        "type": defaults.type,
        "date": f.string(from: date),
        "attendees": defaults.attendees,
        "expectedSpeakers": NSNull(),
        "language": "zh",
        "llm": "claude",
        "_note": "由 MeetingRecorder 快捷開錄寫入。type 可改：seminar/internal/client/1on1/workshop/interview；填 attendees 可讓講者命名更準",
    ]
    try FileManager.default.createDirectory(at: ctx.recordingDir, withIntermediateDirectories: true)
    let data = try JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted, .sortedKeys])
    try data.write(to: url, options: .atomic)
}

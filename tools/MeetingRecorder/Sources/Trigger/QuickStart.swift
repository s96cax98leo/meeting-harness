// Trigger/QuickStart.swift —— quick-start：用上次的設定開錄（design §8；spec §4.11.1）
// 判斷交給 Core 的 quickStartDecision：★ 列恰好一個才開錄，不猜；不跳 Apple Events 授權框。
import Foundation

func cmdQuickStart(_ args: Args) async {
    let home = recordHome(args)
    let log = Logger(path: home.appendingPathComponent("record.log").path, append: true)
    log.line("── quick-start \(isoNow()) ──")
    let defaults = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))

    let listing: WindowListing
    do {
        listing = try await WindowListing.load(askAutomation: false)
    } catch {
        Notifier.post(title: "MeetingRecorder 沒有開錄",
                      body: "取不到視窗清單：螢幕錄製權限沒給，或授權後還沒完全結束 MeetingRecorder 再重開", log: log)
        exit(4)
    }
    let rows = listing.rows
    let starred = rows.filter { $0.meeting != nil }.map { $0.windowID }
    switch quickStartDecision(hasDefaults: defaults != nil, starredWindowIDs: starred) {
    case .fail(let code, let message):
        var body = message
        if code == 3, chromeAutomationHint(rows, include: ["not_authorized", "not_determined"]) {
            body += "\nChrome 會議分頁要允許 Apple Events 才標得出來（系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome）"
        }
        Notifier.post(title: "MeetingRecorder 沒有開錄", body: body, log: log)
        exit(code)
    case .start(let windowID):
        guard let defaults, let row = rows.first(where: { $0.windowID == windowID }) else { exit(3) }
        let now = Date()
        let day = DateFormatter()
        day.dateFormat = "yyyyMMdd"
        let hm = DateFormatter()
        hm.dateFormat = "HHmm"
        let session = URL(fileURLWithPath: defaults.root, isDirectory: true)
            .appendingPathComponent(day.string(from: now), isDirectory: true)
            .appendingPathComponent("\(hm.string(from: now)) 會議", isDirectory: true)
        let ctx = RunContext(home: home, runId: UUID().uuidString, session: session,
                             minFreeBytes: defaults.minFreeBytes ?? fallbackMinFreeBytes(),
                             windowRef: WindowRef(windowID: windowID, bundleID: row.bundleID, title: row.title),
                             harness: defaults.harness, log: log)
        log.line("● quick-start：視窗 [\(windowID)]、場次 \(session.path)")
        Notifier.post(title: "MeetingRecorder 開錄前檢查", body: "請對麥克風說一句話（約 3 秒）", log: log)
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

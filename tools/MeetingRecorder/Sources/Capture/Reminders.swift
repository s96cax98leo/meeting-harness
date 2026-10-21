// Capture/Reminders.swift —— app 子指令 reminders：把會議交辦寫進提醒事項（spec §3.19、§4.34.3；F5）
//
// 由 `meeting reminders <場次> --list <名稱>`（bin/lib/_reminders.py）以
// `open -W -n -a MeetingRecorder --args reminders --input <json> --list <名稱>` 啟動。
// 流程：requestFullAccessToReminders → 找名稱完全相同的清單（不代建）→ 讀出清單內現有項目的 URL →
// 相同 URL（meetingharness://action/<uid>）就更新 title、notes、dueDateComponents，否則新增 →
// 每項 save(commit: false)，最後一次 commit。
// 結果寫 <input>.result.json {"code", "created", "updated", "message"}；code 同 R3-§2.2：
// 0 寫入完成；3 清單不存在；4 權限被拒；5 寫入失敗（部分項目可能已寫入，重跑會去重）。
// 只動提醒事項（EKReminder），不建立、不修改清單本身。
import EventKit
import Foundation

let reminderURLPrefix = "meetingharness://action/"
private let remindersTimeoutSeconds = 600.0

/// _reminders.py 交來的一個項目（spec §3.19）。due 缺值為 null，不補猜。
struct ReminderItem: Decodable {
    let uid: String
    let title: String
    let notes: String
    let due: String?
    let url: String
}

private struct RemindersResult: Encodable {
    let code: Int
    let created: Int
    let updated: Int
    let message: String
}

/// 結果只寫一次；寫完就結束程序（回呼可能在任意 queue 上，用鎖避免重複寫入）。
private final class RemindersReporter: @unchecked Sendable {
    private let path: String
    private let lock = NSLock()
    private var done = false

    init(inputPath: String) { path = inputPath + ".result.json" }

    func finish(code: Int, created: Int = 0, updated: Int = 0, message: String) -> Never {
        lock.lock()
        if !done {
            done = true
            let enc = JSONEncoder()
            enc.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
            let res = RemindersResult(code: code, created: created, updated: updated, message: message)
            if let data = try? enc.encode(res) {
                try? data.write(to: URL(fileURLWithPath: path), options: .atomic)
            }
            if code != 0 { FileHandle.standardError.write(Data((message + "\n").utf8)) }
            exit(Int32(code))
        }
        lock.unlock()
        // 另一個執行緒已在寫結果並結束程序
        while true { Thread.sleep(forTimeInterval: 1) }
    }
}

/// "YYYY-MM-DD" → 全天的 DateComponents；其他寫法回 nil（不猜，鐵則 2）。
func reminderDueComponents(_ due: String?) -> DateComponents? {
    guard let due = due?.trimmingCharacters(in: .whitespaces), due.count == 10 else { return nil }
    let parts = due.split(separator: "-", omittingEmptySubsequences: false)
    guard parts.count == 3, parts[0].count == 4, parts[1].count == 2, parts[2].count == 2,
          let y = Int(parts[0]), let m = Int(parts[1]), let d = Int(parts[2]),
          (1...12).contains(m), (1...31).contains(d) else { return nil }
    var dc = DateComponents()
    dc.calendar = Calendar(identifier: .gregorian)
    dc.year = y
    dc.month = m
    dc.day = d
    return dc
}

private final class RemindersJob: @unchecked Sendable {
    let store = EKEventStore()
    let items: [ReminderItem]
    let listName: String
    let reporter: RemindersReporter

    init(items: [ReminderItem], listName: String, reporter: RemindersReporter) {
        self.items = items
        self.listName = listName
        self.reporter = reporter
    }

    func start() {
        switch EKEventStore.authorizationStatus(for: .reminder) {
        case .denied, .restricted:
            denied()
        default:
            store.requestFullAccessToReminders { [self] granted, error in
                guard granted else { denied(error) }
                findList()
            }
        }
    }

    private func denied(_ error: Error? = nil) -> Never {
        var msg = "提醒事項權限被拒：到「系統設定 → 隱私權與安全性 → 提醒事項」打開 MeetingRecorder 的「完整取用權限」再重跑"
        if let error { msg += "（\(error.localizedDescription)）" }
        reporter.finish(code: 4, message: msg)
    }

    private func findList() {
        let lists = store.calendars(for: .reminder).filter { $0.title == listName }
        guard let list = lists.first(where: { $0.allowsContentModifications }) ?? lists.first else {
            reporter.finish(code: 3, message: "找不到名為「\(listName)」的提醒事項清單（不代建；請先在提醒事項 app 建立）")
        }
        guard list.allowsContentModifications else {
            reporter.finish(code: 5, message: "提醒事項清單「\(listName)」不允許修改")
        }
        let predicate = store.predicateForReminders(in: [list])
        store.fetchReminders(matching: predicate) { [self] existing in
            guard let existing else {
                reporter.finish(code: 5, message: "讀不到清單內現有的提醒事項（fetchRemindersMatchingPredicate 回傳 nil）")
            }
            write(list: list, existing: existing)
        }
    }

    private func write(list: EKCalendar, existing: [EKReminder]) -> Never {
        var byURL: [String: EKReminder] = [:]
        for r in existing {
            // 鍵與下方查詢用同一個正規化（reminderURLKey；R3x §6 第 160 條）
            if let u = r.url?.absoluteString, let k = reminderURLKey(u, prefix: reminderURLPrefix)?.key, byURL[k] == nil { byURL[k] = r }
        }
        var created = 0, updated = 0
        for item in items {
            guard let (key, url) = reminderURLKey(item.url, prefix: reminderURLPrefix) else {
                reporter.finish(code: 5, message: "項目的 url 不是 \(reminderURLPrefix) 開頭：\(item.uid)")
            }
            let r: EKReminder
            if let old = byURL[key] {
                r = old
                updated += 1
            } else {
                r = EKReminder(eventStore: store)
                r.calendar = list
                r.url = url
                byURL[key] = r
                created += 1
            }
            r.title = item.title
            let due = reminderDueComponents(item.due)
            var notes = item.notes
            if due == nil, let raw = item.due, !raw.isEmpty { notes += "\n期限（原文）：\(raw)" }
            r.notes = notes
            r.dueDateComponents = due
            do {
                try store.save(r, commit: false)
            } catch {
                reporter.finish(code: 5, message: "寫入失敗（saveReminder）：\(item.uid)：\(error.localizedDescription)")
            }
        }
        do {
            try store.commit()
        } catch {
            reporter.finish(code: 5, message: "寫入失敗（commit）：\(error.localizedDescription)；重跑會依 URL 去重")
        }
        reporter.finish(code: 0, created: created, updated: updated,
                        message: "已寫入提醒事項「\(listName)」：新增 \(created)、更新 \(updated)")
    }
}

/// reminders --input <json> --list <名稱>
func cmdReminders(_ args: Args) {
    guard let input = args.str("input"), !input.isEmpty, let name = args.str("list"), !name.isEmpty else {
        die("✗ reminders 需要 --input <json> 與 --list <名稱>", code: 2)
    }
    let reporter = RemindersReporter(inputPath: input)
    let items: [ReminderItem]
    do {
        let data = try Data(contentsOf: URL(fileURLWithPath: input))
        items = try JSONDecoder().decode([ReminderItem].self, from: data)
    } catch {
        reporter.finish(code: 5, message: "讀不了交辦清單 \(input)：\(error.localizedDescription)")
    }
    // 權限框等使用者回應、或 EventKit 沒有回呼時，不讓 open -W 永遠等下去
    DispatchQueue.main.asyncAfter(deadline: .now() + remindersTimeoutSeconds) {
        reporter.finish(code: 5, message: "提醒事項寫入逾時（\(Int(remindersTimeoutSeconds)) 秒）；重跑會依 URL 去重")
    }
    RemindersJob(items: items, listName: name, reporter: reporter).start()
}

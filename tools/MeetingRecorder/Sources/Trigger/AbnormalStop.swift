// Trigger/AbnormalStop.swift —— 選單 app 啟動時偵測上次錄製異常中止（meeting-speed spec §4.16.2、§3.10；D3 b、E2）。
// 只讀共享狀態檔 record.status.json：kill(status.pid, 0) 判斷程序是否還在、status.session 是否為存在的目錄、
// 段落是否待收尾，交給 Core 的 abnormalStopSession 判定；不讀 record.pid（E2）。
// 成立時發一則 abnormalStopNotification 的通知（只寫場次代號，不含場次名或路徑；spec §4.12、§6 第 17 條），
// 帶「收尾」動作；使用者按下才以現行執行 meeting.sh 的方式跑 meeting.sh record finish <場次>（不自動跑）。
import Foundation
import UserNotifications

let abnormalStopCategoryID = "mh.abnormalStop"
let abnormalStopFinishActionID = "mh.abnormalStop.finish"

/// 異常中止通知的動作類別：「收尾」
func abnormalStopCategory() -> UNNotificationCategory {
    let finish = UNNotificationAction(identifier: abnormalStopFinishActionID, title: "收尾", options: [])
    return UNNotificationCategory(identifier: abnormalStopCategoryID, actions: [finish], intentIdentifiers: [], options: [])
}

/// spec §3.10「段落待收尾」：<場次>/錄音/tracks/ 有 seg-*.mov，且 finalize.json 不存在、或 videoPublishedAt 為 null、
/// 或（舊 schema）沒有 videoPublishedAt 鍵也沒有 finishedAt。finalize.json 讀不到或不是物件時當作兩個鍵都沒有
/// （與 record.sh 的 abnormal_stop_session 同一套）。
func abnormalStopSegmentsPending(session: String) -> Bool {
    let tracks = URL(fileURLWithPath: session, isDirectory: true)
        .appendingPathComponent("錄音", isDirectory: true).appendingPathComponent("tracks", isDirectory: true)
    let names = (try? FileManager.default.contentsOfDirectory(atPath: tracks.path)) ?? []
    guard names.contains(where: { $0.hasPrefix("seg-") && $0.hasSuffix(".mov") }) else { return false }
    let finURL = tracks.appendingPathComponent("finalize.json")
    guard FileManager.default.fileExists(atPath: finURL.path) else { return true }
    let fin = (try? Data(contentsOf: finURL))
        .flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any] ?? [:]
    if let published = fin["videoPublishedAt"] { return published is NSNull }
    return fin["finishedAt"] == nil
}

/// 啟動時的偵測與「收尾」動作的執行端。同一場只跑一個 finish。
final class AbnormalStopHandler {
    private let home: URL
    private var finishing = Set<String>()

    init(home: URL) {
        self.home = home
    }

    private var logURL: URL { home.appendingPathComponent("record.log") }

    /// spec §4.16.2：讀 record.status.json、kill(status.pid, 0)、場次目錄、段落待收尾 → abnormalStopSession；
    /// 回非 nil 才發通知（不自動收尾）。EPERM（無權限送訊號）視同程序還在，與 record.sh 一致。
    func checkOnLaunch() {
        guard let status = readStatus(home.appendingPathComponent("record.status.json")) else { return }
        let alive = status.pid > 0 && (kill(status.pid, 0) == 0 || errno == EPERM)
        let sessionExists = !status.session.isEmpty && isDirectoryPath(status.session)
        let pending = sessionExists && abnormalStopSegmentsPending(session: status.session)
        guard let session = abnormalStopSession(status: status, pidAlive: alive, sessionExists: sessionExists,
                                                segmentsPending: pending) else { return }
        let label = sessionCodeLabel(startedAt: status.startedAt, runId: status.runId)
        let note = abnormalStopNotification(label: label)
        let log = Logger(path: logURL.path, append: true)
        log.line("\(isoNow()) 偵測到異常中止的場次（\(label)）：已發通知，等使用者按「收尾」")
        let policy = notificationPolicy(kind: .failure, runId: status.runId, timeSensitiveAllowed: false)
        DispatchQueue.global(qos: .utility).async {
            Notifier.post(title: note.title, body: note.body, log: log, identifier: "mh.abnormalStop." + status.runId,
                          policy: policy, categoryIdentifier: abnormalStopCategoryID,
                          userInfo: ["session": session, "label": label])
        }
    }

    /// 使用者按「收尾」：經登入 shell 跑 /bin/bash <harness>/bin/meeting.sh record finish <場次>（與自動前處理同一種方式），
    /// stdout／stderr append 到 record.log；結束後發一則只含場次代號的結果通知。
    func finish(session: String, label: String) {
        guard finishing.insert(session).inserted else { return }
        let log = Logger(path: logURL.path, append: true)
        guard let harness = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))?.harness else {
            finishing.remove(session)
            log.line("\(isoNow()) ✗ record.defaults.json 沒有 harness 路徑，沒辦法收尾異常中止的場次")
            post(title: "異常中止的場次沒有收尾", body: completionNotificationBody(ok: false, label: label), ok: false)
            return
        }
        let script = URL(fileURLWithPath: harness, isDirectory: true).appendingPathComponent("bin/meeting.sh").path
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", #"exec /bin/bash "$0" "$@""#, script, "record", "finish", session]
        p.currentDirectoryURL = URL(fileURLWithPath: harness, isDirectory: true)
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"   // 登入 shell 前的底線
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        // O_APPEND：錄製器與 record.sh 也會寫 record.log，多個程序同時寫不互相覆蓋
        let fd = open(logURL.path, O_WRONLY | O_APPEND | O_CREAT, 0o644)
        let handle = fd >= 0 ? FileHandle(fileDescriptor: fd, closeOnDealloc: true) : nil
        if let handle {
            p.standardOutput = handle
            p.standardError = handle
        }
        log.line("\(isoNow()) 使用者按「收尾」：meeting.sh record finish（\(label)）")
        p.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            DispatchQueue.main.async {
                try? handle?.close()
                self?.finishing.remove(session)
                log.line("\(isoNow()) 異常中止場次的收尾結束（結束碼 \(code)）")
                self?.post(title: code == 0 ? "異常中止的場次已收尾" : "異常中止的場次收尾失敗",
                           body: completionNotificationBody(ok: code == 0, label: label), ok: code == 0)
            }
        }
        do {
            try p.run()
        } catch {
            try? handle?.close()
            finishing.remove(session)
            log.line("\(isoNow()) ✗ meeting.sh record finish 啟動失敗：\(error.localizedDescription)")
            post(title: "異常中止的場次收尾失敗", body: completionNotificationBody(ok: false, label: label), ok: false)
        }
    }

    private func post(title: String, body: String, ok: Bool) {
        let log = Logger(path: logURL.path, append: true)
        let policy = notificationPolicy(kind: ok ? .completion : .failure, runId: nil, timeSensitiveAllowed: false)
        DispatchQueue.global(qos: .utility).async { Notifier.post(title: title, body: body, log: log, policy: policy) }
    }
}

// Capture/Notifier.swift —— 系統通知（quick-start 不開錄的原因、錄製完成的場次路徑；design §8、spec §4.11.1、§4.11.7）
import Foundation
import UserNotifications

enum Notifier {
    /// 送一則通知；最多等 3 秒（第一次會跳通知授權，不授權就只寫 log）。
    /// identifier：指定時以它為通知識別碼（同識別碼的新通知取代舊的，例如完成通知 completionNotificationID(runId:)，
    /// spec §3.13、§4.23.3）；nil 時用隨機 UUID（第一輪行為）。
    static func post(title: String, body: String, log: Logger? = nil, identifier: String? = nil) {
        log?.line("通知：\(title)｜\(body)")
        guard Bundle.main.bundleIdentifier != nil else { return }   // 不在 .app 裡（例如測試）就不送
        let center = UNUserNotificationCenter.current()
        let done = DispatchSemaphore(value: 0)
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { done.signal(); return }
            let content = UNMutableNotificationContent()
            content.title = title
            content.body = body
            let req = UNNotificationRequest(identifier: identifier ?? UUID().uuidString, content: content, trigger: nil)
            center.add(req) { _ in done.signal() }
        }
        _ = done.wait(timeout: .now() + 3)
    }
}

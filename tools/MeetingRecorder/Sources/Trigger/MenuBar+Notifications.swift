// Trigger/MenuBar+Notifications.swift —— 通知類別、完成／捨棄通知、通知動作的回應（spec §4.23.3、§4.42.3、§4.44.3；
// meeting-speed spec §4.12.3、§4.16.2）。meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出，行為不變。
import AppKit
import UserNotifications

extension MenuBarController {
    func setupNotifications() {
        guard Bundle.main.bundleIdentifier != nil else { return }   // 不在 .app 裡就不碰通知中心
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        let reveal = UNNotificationAction(identifier: revealActionID, title: "在 Finder 顯示", options: [.foreground])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: completionCategoryID, actions: [reveal], intentIdentifiers: [], options: []),
            meetingDetectCategory(),     // F3：「開始錄製」「這場不用」（spec §4.44.3）
            abnormalStopCategory(),      // meeting-speed：異常中止的「收尾」（spec §4.16.2）
        ])
    }

    /// 與錄製實例的完成通知同一個識別碼（取代它），另加 category 與「在 Finder 顯示」動作（spec §4.23.3）
    func postCompletion(_ st: RecordStatus) {
        guard Bundle.main.bundleIdentifier != nil else { return }
        let content = UNMutableNotificationContent()
        content.title = "會議錄製完成"
        // spec §4.12.3：內文只放場次代號，不含場次名或路徑；「在 Finder 顯示」用的 userInfo["session"] 保留
        content.body = completionNotificationBody(ok: true, label: sessionCodeLabel(startedAt: st.startedAt, runId: st.runId))
        content.categoryIdentifier = completionCategoryID
        content.userInfo = ["session": st.session]
        Notifier.apply(notificationPolicy(kind: .completion, runId: st.runId, timeSensitiveAllowed: false), to: content)
        let req = UNNotificationRequest(identifier: completionNotificationID(runId: st.runId), content: content,
                                        trigger: nil)
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            center.add(req) { _ in }
        }
    }

    /// 捨棄完成：以同一個完成通知識別碼取代錄製實例的通知；不放場次名與路徑
    func postDiscarded(_ st: RecordStatus) {
        let log = Logger(path: logURL.path, append: true)
        let policy = notificationPolicy(kind: .completion, runId: st.runId, timeSensitiveAllowed: false)
        let id = completionNotificationID(runId: st.runId)
        DispatchQueue.global(qos: .utility).async {
            Notifier.post(title: "已捨棄這次錄製", body: "錄音資料夾已移到垃圾桶，可從垃圾桶復原。", log: log, identifier: id,
                          policy: policy)
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if response.actionIdentifier == revealActionID,
           let s = response.notification.request.content.userInfo["session"] as? String, !s.isEmpty {
            DispatchQueue.main.async { revealSessionProduct(s) }
        }
        // meeting-speed spec §4.16.2：按「收尾」才跑 meeting.sh record finish <場次>
        let info = response.notification.request.content.userInfo
        if response.notification.request.content.categoryIdentifier == abnormalStopCategoryID,
           response.actionIdentifier == abnormalStopFinishActionID,
           let s = info["session"] as? String, !s.isEmpty {
            let label = info["label"] as? String ?? ""
            DispatchQueue.main.async { [weak self] in self?.abnormalStop.finish(session: s, label: label) }
        }
        // F3（spec §4.44.3）：「開始錄製」走既有 quick-start（用上次的設定）；「這場不用」本 episode 不再提示
        if response.notification.request.content.categoryIdentifier == meetingDetectCategoryID {
            switch response.actionIdentifier {
            case meetingDetectStartActionID:
                DispatchQueue.main.async { [weak self] in
                    guard let self else { return }
                    self.refresh()
                    if self.model.canStart { self.startRecording() }
                }
            case meetingDetectDismissActionID:
                DispatchQueue.main.async { [weak self] in self?.meetingDetector?.dismissCurrentEpisode() }
            default:
                break
            }
        }
        completionHandler()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list])
    }
}

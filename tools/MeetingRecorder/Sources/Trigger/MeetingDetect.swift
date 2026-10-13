// Trigger/MeetingDetect.swift —— F3 會議偵測提示（spec §4.44.2、§4.44.3；design-r3/README.md §6.1 F3-A）
// 每 meetingDetectPollSeconds 秒輪詢一次：
//   - 預設輸入裝置是否「有程序在用」：只讀 Core Audio 的 kAudioDevicePropertyDeviceIsRunningSomewhere，
//     本程序不開麥克風、不擷取任何聲音或畫面；
//   - 前景 app 的 bundle ID 與 localizedName（只用 app 名稱，不讀視窗標題）；
//   - record.lock 是否被持有（試鎖一次、拿到就立刻放掉）；錄製中不提示；
//   - 設定的 meetingDetect 開關（「回饋與通知」分頁）。
// 要不要提示一律交給 Core 的 meetingPromptDecision（同一個 episode 只提示一次）。
// 提示＝系統一般通知（F3-A）：標題「錄這個會議？」、內文只放 app 名稱、兩個動作「開始錄製」「這場不用」。
// 不自動開錄：「開始錄製」由 MenuBarController 走既有 quick-start（用上次的設定）。
import AppKit
import CoreAudio
import UserNotifications

/// 輪詢間隔（spec §4.44.2）
let meetingDetectPollSeconds: Double = 3
/// 通知的動作類別與動作識別碼（MenuBarController 以 setNotificationCategories 註冊、在 didReceive 分派）
let meetingDetectCategoryID = "mh.meetingDetected"
let meetingDetectStartActionID = "mh.meetingDetected.start"
let meetingDetectDismissActionID = "mh.meetingDetected.dismiss"

/// F3-A 的字面（spec §4.44.3）
let meetingPromptTitle = "錄這個會議？"

/// 內文只放 app 名稱（前景 app 的 localizedName；取不到用「會議 app」），不放視窗標題。
func meetingPromptBody(appName: String?) -> String {
    let name = (appName?.isEmpty == false ? appName : nil) ?? "會議 app"
    return "\(name) 正在使用麥克風。要開始錄製嗎？"
}

/// 「開始錄製」「這場不用」兩個動作；都不把 app 帶到前景
func meetingDetectCategory() -> UNNotificationCategory {
    let start = UNNotificationAction(identifier: meetingDetectStartActionID, title: "開始錄製", options: [])
    let dismiss = UNNotificationAction(identifier: meetingDetectDismissActionID, title: "這場不用", options: [])
    return UNNotificationCategory(identifier: meetingDetectCategoryID, actions: [start, dismiss], intentIdentifiers: [],
                                  options: [])
}

/// 預設輸入裝置目前是否有任何程序在用（kAudioDevicePropertyDeviceIsRunningSomewhere）。
/// 只讀屬性、不開裝置；取不到（沒有輸入裝置、查詢失敗）→ nil。
func defaultInputDeviceRunningSomewhere() -> Bool? {
    var device = AudioDeviceID(kAudioObjectUnknown)
    var size = UInt32(MemoryLayout<AudioDeviceID>.size)
    var address = AudioObjectPropertyAddress(mSelector: kAudioHardwarePropertyDefaultInputDevice,
                                             mScope: kAudioObjectPropertyScopeGlobal,
                                             mElement: kAudioObjectPropertyElementMain)
    guard AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &device) == noErr,
          device != kAudioObjectUnknown else { return nil }
    var running: UInt32 = 0
    size = UInt32(MemoryLayout<UInt32>.size)
    address.mSelector = kAudioDevicePropertyDeviceIsRunningSomewhere
    guard AudioObjectGetPropertyData(device, &address, 0, nil, &size, &running) == noErr else { return nil }
    return running != 0
}

final class MeetingDetector {
    private let home: URL
    /// 設定的 meetingDetect（每次輪詢重讀，設定視窗改了立即生效）
    private let enabled: () -> Bool
    /// menu bar 看到的錄製中（含準備中、收尾中）；與 record.lock 任一成立就不提示
    private let recordingInProgress: () -> Bool
    private var episode = MeetingEpisode()
    private var timer: Timer?

    init(home: URL, enabled: @escaping () -> Bool, recordingInProgress: @escaping () -> Bool) {
        self.home = home
        self.enabled = enabled
        self.recordingInProgress = recordingInProgress
    }

    func start() {
        timer?.invalidate()
        let t = Timer(timeInterval: meetingDetectPollSeconds, repeats: true) { [weak self] _ in self?.poll() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    /// 「這場不用」：本 episode 不再提示（輸入裝置停用後 Core 會重設 episode）
    func dismissCurrentEpisode() {
        episode.dismissed = true
    }

    private func poll() {
        let inputRunning = defaultInputDeviceRunningSomewhere() ?? false
        let front = NSWorkspace.shared.frontmostApplication
        // 只有輸入裝置在用、開關打開時才試鎖（其餘情況 Core 不看鎖，省一次檔案操作）
        let on = enabled()
        let lockHeld = inputRunning && on ? (recordingInProgress() || recordLockHeldNow()) : false
        let (next, decision) = meetingPromptDecision(episode, inputRunning: inputRunning,
                                                     frontmostBundleID: front?.bundleIdentifier,
                                                     recordLockHeld: lockHeld, enabled: on)
        episode = next
        guard decision == .prompt else { return }
        post(appName: front?.localizedName)
    }

    /// record.lock 是否被別的程序持有：試鎖一次（不重試），拿到就立刻放掉；打不開鎖檔視為沒有持有
    private func recordLockHeldNow() -> Bool {
        switch acquireRecordLock(home: home, retrySeconds: 0) {
        case .acquired(let fd):
            close(fd)
            return false
        case .heldByOther:
            return true
        case .unavailable:
            return false
        }
    }

    /// 一般通知（F3-A）：interruptionLevel、threadIdentifier 依 notificationPolicy(.meetingDetected)（§4.39.1）
    private func post(appName: String?) {
        let log = Logger(path: home.appendingPathComponent("record.log").path, append: true)
        let policy = notificationPolicy(kind: .meetingDetected, runId: nil, timeSensitiveAllowed: false)
        let body = meetingPromptBody(appName: appName)
        DispatchQueue.global(qos: .utility).async {
            Notifier.post(title: meetingPromptTitle, body: body, log: log, identifier: "mh.meetingDetected",
                          policy: policy, categoryIdentifier: meetingDetectCategoryID)
        }
    }
}

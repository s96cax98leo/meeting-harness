// Core/Appearance.swift —— 選單列外觀 8 種、口語計時、選單依階段、音量條長度、VoiceOver 字面、HUD 顯示與回饋路徑、
// 通知分級（spec §3.20、§4.38.1、§4.38.2、§4.38.7、§4.39.1、§4.39.2、§4.40.1–§4.40.3、§4.41.1、§4.41.2、§4.41.4、§4.41.7；
// ADR adr-r3-menu-stages.md）。純函式，不依賴 AppKit。
import Foundation

/// 選單列圖示的 8 種外觀（U1）；由 menuBarModel 的列決定（spec §4.38.1）。
enum MenuBarAppearance: String, CaseIterable, Equatable {
    case idle, preparing, recording, recordingMuted, recordingAlert, paused, finalizing, failed
}

/// VoiceOver 讀的口語計時（spec §4.38.2）：< 0 視為 0；有小時時只讀到分。
/// 0 → 已錄 0 秒；60 → 已錄 1 分；125 → 已錄 2 分 5 秒；3600 → 已錄 1 小時；3725 → 已錄 1 小時 2 分。
func spokenDuration(seconds: Int) -> String {
    let s = max(0, seconds)
    let h = s / 3600, m = (s % 3600) / 60, sec = s % 60
    if h > 0 { return "已錄 \(h) 小時" + (m > 0 ? " \(m) 分" : "") }
    if m > 0 { return "已錄 \(m) 分" + (sec > 0 ? " \(sec) 秒" : "") }
    return "已錄 \(sec) 秒"
}

/// 選單的階段（U6）。
enum MenuStage: String, Equatable { case idle, recording, finalizing, failed }

func menuStage(_ m: MenuBarModel) -> MenuStage {
    switch m.appearance {
    case .idle: return .idle
    case .preparing, .recording, .recordingMuted, .recordingAlert, .paused: return .recording
    case .finalizing: return .finalizing
    case .failed: return .failed
    }
}

enum MenuItemID: String, CaseIterable {
    case status, levels, alert, copyDiagnostics, failureDetail, start, recordWindow, saveTo,
         pauseResume, mute, mark, stop, discard, cancelFinalize, showHUD, openSession, showLast, preferences, quit
}

/// 各階段顯示的選單項目＝menuGroups(stage:) 攤平（spec §4.41.2）。
func menuItems(stage: MenuStage) -> [MenuItemID] {
    menuGroups(stage: stage).flatMap { $0 }
}

/// 各階段的選單分組；組與組之間一條分隔線（spec §4.41.7）。
func menuGroups(stage: MenuStage) -> [[MenuItemID]] {
    switch stage {
    case .idle:
        return [[.status], [.start, .recordWindow, .saveTo], [.openSession, .showLast], [.preferences, .quit]]
    case .recording:
        return [[.status, .levels, .alert], [.pauseResume, .mute, .mark], [.stop, .discard], [.showHUD, .openSession],
                [.preferences, .quit]]
    case .finalizing:
        return [[.status], [.cancelFinalize], [.openSession], [.preferences, .quit]]
    case .failed:
        return [[.status], [.failureDetail, .copyDiagnostics], [.start, .recordWindow, .saveTo], [.openSession, .showLast],
                [.preferences, .quit]]
    }
}

/// 音量條長度：clamp((dBFS + 60) / 60, 0, 1)；nil 或非有限值 → 0（spec §4.41.4）。
func levelFraction(dBFS: Double?) -> Double {
    guard let db = dBFS, !db.isNaN else { return 0 }
    return min(max((db + 60) / 60, 0), 1)
}

/// status item 的 accessibilityLabel 與 toolTip（spec §4.38.7）。
func menuBarAccessibilityLabel(appearance: MenuBarAppearance, alertBadge: Bool, spoken: String,
                               alertText: String?, status: String) -> String {
    let head = "MeetingRecorder："
    switch appearance {
    case .idle: return head + "待機中"
    case .preparing: return head + "開錄前檢查中"
    case .recording: return head + "錄製中，\(spoken)"
    case .recordingMuted: return head + "錄製中，\(spoken)，麥克風靜音"
    case .recordingAlert: return head + "錄製中，\(spoken)，有告警" + (alertText.map { "：\($0)" } ?? "")
    case .paused: return head + "已暫停，\(spoken)" + (alertBadge ? "，有告警" : "")
    case .finalizing: return head + "收尾中"
    case .failed: return head + "需要處理：\(status)"
    }
}

let hudAlertExpandSeconds: Double = 8        // 新告警時 HUD 自動展開的秒數（§4.40.7）
let hudCollapseDelaySeconds: Double = 0.6    // 滑鼠離開後收合的延遲
let hudAnimationSeconds: Double = 0.2        // 展開／收合動畫；「減少動態效果」時不做動畫
let levelMeterRefreshSeconds: Double = 0.5

enum HUDMode: String, Codable, CaseIterable { case auto, always, never }

/// 錄製中、靜音、告警、暫停才可能顯示；always → true；auto → obscured；never → false（spec §4.40.1）。
func hudVisible(mode: HUDMode, obscured: Bool, appearance: MenuBarAppearance) -> Bool {
    switch appearance {
    case .recording, .recordingMuted, .recordingAlert, .paused: break
    case .idle, .preparing, .finalizing, .failed: return false
    }
    switch mode {
    case .always: return true
    case .auto: return obscured
    case .never: return false
    }
}

enum FeedbackRoute: String, Equatable { case hud, none, notification }

/// 快捷鍵回饋：HUD 顯示中 → .hud；圖示看得到 → .none；兩者都沒有 → .notification（spec §4.40.2）。
func feedbackRoute(hudVisible: Bool, iconVisible: Bool) -> FeedbackRoute {
    if hudVisible { return .hud }
    return iconVisible ? .none : .notification
}

enum ObscuredAction: Equatable { case none, showHUD, hideHUD }

/// 只在 auto 且錄製中、圖示被擋住的狀態改變時動作（spec §4.40.3）。
func obscuredAction(previous: Bool?, current: Bool, mode: HUDMode, recording: Bool) -> ObscuredAction {
    guard mode == .auto, recording else { return .none }
    if current, previous != true { return .showHUD }
    if !current, previous == true { return .hideHUD }
    return .none
}

let obscuredCheckSeconds: Double = 5

enum NotificationKind: String, CaseIterable { case alertWarning, failure, completion, hotkeyFeedback, meetingDetected, onboarding }
enum NotificationLevel: String, Equatable { case passive, active, timeSensitive }
struct NotificationPolicy: Equatable { var level: NotificationLevel; var threadIdentifier: String }

/// 通知分級（spec §4.39.1）。threadIdentifier＝非空 runId，否則 "mh.app"；meetingDetected 一律 "mh.app"。
func notificationPolicy(kind: NotificationKind, runId: String?, timeSensitiveAllowed: Bool) -> NotificationPolicy {
    let level: NotificationLevel
    switch kind {
    case .alertWarning: level = timeSensitiveAllowed ? .timeSensitive : .active
    case .failure, .completion, .meetingDetected: level = .active
    case .hotkeyFeedback, .onboarding: level = .passive
    }
    let thread: String
    if kind == .meetingDetected {
        thread = "mh.app"
    } else if let r = runId, !r.isEmpty {
        thread = r
    } else {
        thread = "mh.app"
    }
    return NotificationPolicy(level: level, threadIdentifier: thread)
}

/// current 中告警類、且（t, kind）不在 previous 的項（spec §4.39.2）；順序同 current。
func newAlertWarnings(previous: [RecordWarning], current: [RecordWarning]) -> [RecordWarning] {
    current.filter { w in
        w.kind.isAlert && !previous.contains { $0.t == w.t && $0.kind == w.kind }
    }
}

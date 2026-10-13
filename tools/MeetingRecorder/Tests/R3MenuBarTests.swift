// spec §3.20（Core/Appearance.swift、Core/MeetingDetect.swift、Core/Trigger.swift 的增補）：選單列外觀 8 種、
// 口語計時、選單依階段、通知分級、HUD 顯示、快捷鍵回饋路徑、圖示被擋住的動作、會議偵測提示。
// 驗收：§4.38.1、§4.38.2、§4.39.1、§4.39.2、§4.40.1–§4.40.3、§4.41.1、§4.41.2、§4.41.7、§4.44.1。
// 沿用 TriggerTests.swift 的 mrtMenuRows／mrtStatus／mrtNow 與 MenuBarR2Tests.swift 的 mrtR2Recording（不改既有檔）。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation

let mrtR3MenuBarTests: [MRTCase] = [
    ("testAppearanceMapping", testAppearanceMapping),
    ("testSpokenDuration", testSpokenDuration),
    ("testMenuStage", testMenuStage),
    ("testMenuItemsPerStage", testMenuItemsPerStage),
    ("testMenuGroups", testMenuGroups),
    ("testNotificationPolicy", testNotificationPolicy),
    ("testNewAlertWarnings", testNewAlertWarnings),
    ("testHudVisible", testHudVisible),
    ("testFeedbackRoute", testFeedbackRoute),
    ("testObscuredAction", testObscuredAction),
    ("testMeetingPromptDecision", testMeetingPromptDecision),
]

/// §4.38.1 的列 → 外觀。
let mrtR3RowAppearance: [String: MenuBarAppearance] = [
    "M1": .idle, "M5": .idle, "M8": .preparing, "M9": .recording, "M7": .recordingAlert,
    "M6a": .finalizing, "M10": .finalizing, "M2": .failed, "M3": .failed, "M4": .failed, "M6": .failed,
]

/// 8 種外觀各一個代表模型（由 menuBarModel 產生，不手組 MenuBarModel）。
func mrtR3ModelFor(_ a: MenuBarAppearance) -> MenuBarModel {
    let now = mrtNow(500)
    switch a {
    case .idle: return menuBarModel(status: nil, pidAlive: false, now: now)
    case .preparing: return menuBarModel(status: mrtStatus(.preflight), pidAlive: true, now: now)
    case .recording: return menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5), pidAlive: true, now: now)
    case .recordingMuted:
        return menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, micMuted: true), pidAlive: true, now: now)
    case .recordingAlert:
        return menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, warnings: [mrtAlertNew]),
                            pidAlive: true, now: now)
    case .paused:
        return menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10), pidAlive: true, now: now)
    case .finalizing: return menuBarModel(status: mrtStatus(.finalizing), pidAlive: true, now: now)
    case .failed: return menuBarModel(status: mrtStatus(.failed, code: 5, message: "擷取串流中斷"), pidAlive: true, now: now)
    }
}

// §4.38.1：menuBarModel 的 appearance／alertBadge。
func testAppearanceMapping() throws {
    mrtEqual(MenuBarAppearance.allCases.map(\.rawValue),
             ["idle", "preparing", "recording", "recordingMuted", "recordingAlert", "paused", "finalizing", "failed"],
             "MenuBarAppearance 8 種與順序")
    for r in mrtMenuRows {
        guard let want = mrtR3RowAppearance[r.row] else {
            mrtFail("\(r.row) 沒有對應外觀", file: #fileID, line: #line); continue
        }
        let m = mrtModel(r)
        mrtEqual(m.appearance, want, "\(r.row)（\(m.statusLine)）")
        mrtEqual(m.state, r.state, "\(r.row) 的 state 與 R2 相同")
    }
    let now = mrtNow(500)
    // M9 micMuted → recordingMuted
    let muted = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, micMuted: true),
                             pidAlive: true, now: now)
    mrtEqual(muted.appearance, MenuBarAppearance.recordingMuted, "M9 micMuted")
    mrtEqual(muted.state, MenuBarState.recording, "state 不變")
    // M9（R2 欄位）→ recording
    let rec = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5), pidAlive: true, now: now)
    mrtEqual(rec.appearance, MenuBarAppearance.recording, "M9")
    // M6b 沒告警 → paused、alertBadge false
    let p = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10),
                         pidAlive: true, now: now)
    mrtEqual(p.appearance, MenuBarAppearance.paused, "M6b")
    mrtEqual(p.alertBadge, false, "M6b 沒有告警類 warning")
    // M6b 有告警類 warning → paused、alertBadge true
    let pa = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10,
                                                 warnings: [mrtAlertOld, mrtRecordOnly]),
                          pidAlive: true, now: now)
    mrtEqual(pa.appearance, MenuBarAppearance.paused, "M6b 有告警")
    mrtEqual(pa.alertBadge, true, "M6b 有告警類 warning")
    mrtEqual(pa.state, MenuBarState.paused, "state 不變")
    mrtEqual(pa.symbolName, "pause.circle.fill", "symbolName 不變")
    // 只有紀錄類 warning 不算告警
    let pr = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10,
                                                 warnings: [mrtRecordOnly]),
                          pidAlive: true, now: now)
    mrtEqual(pr.alertBadge, false, "M6b 只有紀錄類 warning")
}

// §4.38.2：spokenDuration 與 accessibilityLabel 用口語計時。
func testSpokenDuration() throws {
    let cases: [(Int, String)] = [
        (0, "已錄 0 秒"), (59, "已錄 59 秒"), (60, "已錄 1 分"), (125, "已錄 2 分 5 秒"),
        (3600, "已錄 1 小時"), (3725, "已錄 1 小時 2 分"), (-3, "已錄 0 秒"),
    ]
    for (s, want) in cases { mrtEqual(spokenDuration(seconds: s), want, "\(s) 秒") }

    let now = mrtNow(500)
    // 錄製中：recordedSeconds＝125 − 5＝120
    let rec = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5), pidAlive: true, now: now)
    mrtEqual(rec.timerText, "02:00", "前提：timerText")
    mrtEqual(rec.spokenDuration, "已錄 2 分", "錄製中的 spokenDuration")
    let recLabel = menuBarAccessibilityLabel(appearance: rec.appearance, alertBadge: rec.alertBadge, spoken: rec.spokenDuration,
                                             alertText: nil, status: rec.statusLine)
    mrtContains(recLabel, "已錄 2 分", "錄製中 accessibilityLabel")
    mrtExpect(!recLabel.contains("02:00"), "錄製中 accessibilityLabel 不得含 timerText 寫法：\(recLabel)")
    // 暫停中：100 − 20 − 10＝70
    let p = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10), pidAlive: true, now: now)
    mrtEqual(p.timerText, "01:10", "前提：timerText")
    mrtEqual(p.spokenDuration, "已錄 1 分 10 秒", "暫停中的 spokenDuration")
    let pLabel = menuBarAccessibilityLabel(appearance: p.appearance, alertBadge: p.alertBadge, spoken: p.spokenDuration,
                                           alertText: nil, status: p.statusLine)
    mrtContains(pLabel, "已錄 1 分 10 秒", "暫停中 accessibilityLabel")
    mrtExpect(!pLabel.contains("01:10"), "暫停中 accessibilityLabel 不得含 timerText 寫法：\(pLabel)")
}

// §4.41.1：menuStage。
func testMenuStage() throws {
    let want: [MenuBarAppearance: MenuStage] = [
        .idle: .idle, .preparing: .recording, .recording: .recording, .recordingMuted: .recording,
        .recordingAlert: .recording, .paused: .recording, .finalizing: .finalizing, .failed: .failed,
    ]
    for a in MenuBarAppearance.allCases {
        let m = mrtR3ModelFor(a)
        mrtEqual(m.appearance, a, "前提：代表模型的 appearance")
        mrtEqual(menuStage(m), want[a]!, "\(a.rawValue)")
    }
    mrtEqual(MenuStage.idle.rawValue, "idle")
    mrtEqual(MenuStage.recording.rawValue, "recording")
    mrtEqual(MenuStage.finalizing.rawValue, "finalizing")
    mrtEqual(MenuStage.failed.rawValue, "failed")
}

let mrtR3ExpectedGroups: [(MenuStage, [[MenuItemID]])] = [
    (.idle, [[.status], [.start, .recordWindow, .saveTo], [.openSession, .showLast], [.preferences, .quit]]),
    (.recording, [[.status, .levels, .alert], [.pauseResume, .mute, .mark], [.stop, .discard], [.showHUD, .openSession],
                  [.preferences, .quit]]),
    (.finalizing, [[.status], [.cancelFinalize], [.openSession], [.preferences, .quit]]),
    (.failed, [[.status], [.failureDetail, .copyDiagnostics], [.start, .recordWindow, .saveTo], [.openSession, .showLast],
               [.preferences, .quit]]),
]

// §4.41.2：menuItems(stage:) 恰為表列。
func testMenuItemsPerStage() throws {
    mrtEqual(menuItems(stage: .idle), [.status, .start, .recordWindow, .saveTo, .openSession, .showLast, .preferences, .quit], "idle")
    mrtEqual(menuItems(stage: .recording),
             [.status, .levels, .alert, .pauseResume, .mute, .mark, .stop, .discard, .showHUD, .openSession, .preferences, .quit],
             "recording")
    mrtEqual(menuItems(stage: .finalizing), [.status, .cancelFinalize, .openSession, .preferences, .quit], "finalizing")
    mrtEqual(menuItems(stage: .failed),
             [.status, .failureDetail, .copyDiagnostics, .start, .recordWindow, .saveTo, .openSession, .showLast, .preferences, .quit],
             "failed")
    mrtEqual(MenuItemID.allCases.count, 19, "MenuItemID 19 項")
}

// §4.41.7：menuGroups(stage:) 恰為表列，攤平等於 menuItems(stage:)。
func testMenuGroups() throws {
    for (stage, groups) in mrtR3ExpectedGroups {
        mrtEqual(menuGroups(stage: stage), groups, "\(stage.rawValue)")
        mrtEqual(menuGroups(stage: stage).flatMap { $0 }, menuItems(stage: stage), "\(stage.rawValue) 攤平")
    }
}

// §4.39.1：notificationPolicy。
func testNotificationPolicy() throws {
    let run = "00000000-0000-4000-8000-000000000002"
    func p(_ k: NotificationKind, _ runId: String?, _ ts: Bool) -> NotificationPolicy {
        notificationPolicy(kind: k, runId: runId, timeSensitiveAllowed: ts)
    }
    mrtEqual(NotificationKind.allCases.map(\.rawValue),
             ["alertWarning", "failure", "completion", "hotkeyFeedback", "meetingDetected", "onboarding"])
    mrtEqual(p(.alertWarning, run, true), NotificationPolicy(level: .timeSensitive, threadIdentifier: run), "告警、允許時效性")
    mrtEqual(p(.alertWarning, run, false), NotificationPolicy(level: .active, threadIdentifier: run), "告警、不允許時效性")
    for k in [NotificationKind.failure, .completion] {
        mrtEqual(p(k, run, true), NotificationPolicy(level: .active, threadIdentifier: run), "\(k.rawValue)")
        mrtEqual(p(k, run, false).level, NotificationLevel.active, "\(k.rawValue)")
    }
    mrtEqual(p(.meetingDetected, run, true), NotificationPolicy(level: .active, threadIdentifier: "mh.app"),
             "meetingDetected 一律 mh.app")
    mrtEqual(p(.hotkeyFeedback, run, true), NotificationPolicy(level: .passive, threadIdentifier: run), "hotkeyFeedback")
    mrtEqual(p(.onboarding, nil, true), NotificationPolicy(level: .passive, threadIdentifier: "mh.app"), "onboarding")
    // threadIdentifier：非空 runId，否則 mh.app
    mrtEqual(p(.failure, nil, true).threadIdentifier, "mh.app", "runId nil")
    mrtEqual(p(.failure, "", true).threadIdentifier, "mh.app", "runId 空字串")
    mrtEqual(p(.alertWarning, nil, true), NotificationPolicy(level: .timeSensitive, threadIdentifier: "mh.app"), "告警、runId nil")
}

// §4.39.2：newAlertWarnings 只回新的告警類。
func testNewAlertWarnings() throws {
    mrtEqual(newAlertWarnings(previous: [], current: [mrtAlertOld, mrtRecordOnly]), [mrtAlertOld], "紀錄類不回")
    // 同一則連續兩次輪詢只發一次
    mrtEqual(newAlertWarnings(previous: [mrtAlertOld, mrtRecordOnly], current: [mrtAlertOld, mrtRecordOnly]), [],
             "同一則告警第二次不回")
    mrtEqual(newAlertWarnings(previous: [mrtAlertOld], current: [mrtAlertOld, mrtAlertNew, mrtRecordOnly]), [mrtAlertNew], "只回新增的")
    // 同 kind 不同 t → 新的一則
    mrtEqual(newAlertWarnings(previous: [mrtAlertNew], current: [mrtAlertNew, mrtAlertMicAgain]), [mrtAlertMicAgain], "(t, kind) 不同")
    // 同 t 不同 kind → 新的一則
    let sameT = RecordWarning(t: mrtAlertNew.t, kind: .silenceSystem, message: "系統聲音已連續 15 秒沒有聲音")
    mrtEqual(newAlertWarnings(previous: [mrtAlertNew], current: [mrtAlertNew, sameT]), [sameT], "同 t 不同 kind")
    // 只比 (t, kind)：訊息不同但 (t, kind) 相同 → 不是新的
    let sameKey = RecordWarning(t: mrtAlertNew.t, kind: mrtAlertNew.kind, message: "改寫過的訊息")
    mrtEqual(newAlertWarnings(previous: [mrtAlertNew], current: [sameKey]), [], "(t, kind) 相同")
}

// §4.40.1：hudVisible；以及 HUD 相關常數（§3.20）。
func testHudVisible() throws {
    let live: Set<MenuBarAppearance> = [.recording, .recordingMuted, .recordingAlert, .paused]
    for a in MenuBarAppearance.allCases {
        for obscured in [false, true] {
            let isLive = live.contains(a)
            mrtEqual(hudVisible(mode: .always, obscured: obscured, appearance: a), isLive, "always \(a.rawValue) obscured=\(obscured)")
            mrtEqual(hudVisible(mode: .auto, obscured: obscured, appearance: a), isLive && obscured,
                     "auto \(a.rawValue) obscured=\(obscured)")
            mrtEqual(hudVisible(mode: .never, obscured: obscured, appearance: a), false, "never \(a.rawValue) obscured=\(obscured)")
        }
    }
    mrtEqual(hudAlertExpandSeconds, 8.0, "hudAlertExpandSeconds")
    mrtEqual(hudCollapseDelaySeconds, 0.6, "hudCollapseDelaySeconds")
    mrtEqual(hudAnimationSeconds, 0.2, "hudAnimationSeconds")
}

// §4.40.2：feedbackRoute。
func testFeedbackRoute() throws {
    mrtEqual(feedbackRoute(hudVisible: true, iconVisible: true), FeedbackRoute.hud)
    mrtEqual(feedbackRoute(hudVisible: true, iconVisible: false), FeedbackRoute.hud)
    mrtEqual(feedbackRoute(hudVisible: false, iconVisible: true), FeedbackRoute.none)
    mrtEqual(feedbackRoute(hudVisible: false, iconVisible: false), FeedbackRoute.notification)
}

// §4.40.3：obscuredAction 只在 auto 且錄製中、狀態改變時動作；檢查間隔 5 秒。
func testObscuredAction() throws {
    let autoCases: [(Bool?, Bool, ObscuredAction)] = [
        (nil, true, .showHUD), (false, true, .showHUD), (true, false, .hideHUD),
        (true, true, .none), (false, false, .none), (nil, false, .none),
    ]
    for (prev, cur, want) in autoCases {
        mrtEqual(obscuredAction(previous: prev, current: cur, mode: .auto, recording: true), want,
                 "auto 錄製中 (\(String(describing: prev)), \(cur))")
        mrtEqual(obscuredAction(previous: prev, current: cur, mode: .auto, recording: false), ObscuredAction.none,
                 "auto 非錄製中 (\(String(describing: prev)), \(cur))")
        for mode in [HUDMode.always, .never] {
            for recording in [true, false] {
                mrtEqual(obscuredAction(previous: prev, current: cur, mode: mode, recording: recording), ObscuredAction.none,
                         "\(mode.rawValue) recording=\(recording) (\(String(describing: prev)), \(cur))")
            }
        }
    }
    mrtEqual(obscuredCheckSeconds, 5.0, "obscuredCheckSeconds")
}

// §4.44.1：meetingPromptDecision（★ 清單＝Core/WindowList.swift 的會議 app 表）。
func testMeetingPromptDecision() throws {
    let zoom = "us.zoom.xos"           // ★ 清單內（meetingAppService 回 Zoom）
    let other = "com.apple.Safari"     // ★ 清單外
    mrtExpect(meetingAppService(bundleID: zoom) != nil, "前提：\(zoom) 在 ★ 清單")
    mrtExpect(meetingAppService(bundleID: other) == nil, "前提：\(other) 不在 ★ 清單")
    let fresh = MeetingEpisode()
    mrtEqual(fresh, MeetingEpisode(inputRunning: false, prompted: false, dismissed: false), "預設值")

    // enabled false → none
    mrtEqual(meetingPromptDecision(fresh, inputRunning: true, frontmostBundleID: zoom, recordLockHeld: false, enabled: false).1,
             MeetingPrompt.none, "enabled false")
    // record.lock 被持有 → none
    mrtEqual(meetingPromptDecision(fresh, inputRunning: true, frontmostBundleID: zoom, recordLockHeld: true, enabled: true).1,
             MeetingPrompt.none, "recordLockHeld true")
    // inputRunning false → none，episode 重設
    let used = MeetingEpisode(inputRunning: true, prompted: true, dismissed: true)
    let (reset, r0) = meetingPromptDecision(used, inputRunning: false, frontmostBundleID: zoom, recordLockHeld: false, enabled: true)
    mrtEqual(r0, MeetingPrompt.none, "inputRunning false")
    mrtEqual(reset.prompted, false, "inputRunning false 時 prompted 重設")
    mrtEqual(reset.dismissed, false, "inputRunning false 時 dismissed 重設")
    // 前景不在 ★ 清單 → none
    mrtEqual(meetingPromptDecision(fresh, inputRunning: true, frontmostBundleID: other, recordLockHeld: false, enabled: true).1,
             MeetingPrompt.none, "前景不在清單")
    mrtEqual(meetingPromptDecision(fresh, inputRunning: true, frontmostBundleID: nil, recordLockHeld: false, enabled: true).1,
             MeetingPrompt.none, "沒有前景 app")
    // 在清單、prompted false → prompt，prompted 變 true
    let (ep1, r1) = meetingPromptDecision(fresh, inputRunning: true, frontmostBundleID: zoom, recordLockHeld: false, enabled: true)
    mrtEqual(r1, MeetingPrompt.prompt, "第一次")
    mrtEqual(ep1.prompted, true, "提示後 prompted true")
    // 同一 episode 第二次 → none
    let (ep2, r2) = meetingPromptDecision(ep1, inputRunning: true, frontmostBundleID: zoom, recordLockHeld: false, enabled: true)
    mrtEqual(r2, MeetingPrompt.none, "同一 episode 第二次")
    // episode 結束後再開始 → 可再 prompt
    let (ep3, r3) = meetingPromptDecision(ep2, inputRunning: false, frontmostBundleID: zoom, recordLockHeld: false, enabled: true)
    mrtEqual(r3, MeetingPrompt.none, "episode 結束")
    let (_, r4) = meetingPromptDecision(ep3, inputRunning: true, frontmostBundleID: zoom, recordLockHeld: false, enabled: true)
    mrtEqual(r4, MeetingPrompt.prompt, "新 episode 可再提示")
}

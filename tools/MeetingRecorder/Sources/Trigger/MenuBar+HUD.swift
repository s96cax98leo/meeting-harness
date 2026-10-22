// Trigger/MenuBar+HUD.swift —— 錄製小窗（Trigger/HUD.swift）的顯示判斷與「顯示錄製小窗」（spec §4.40.1、§4.41.3）。
// meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出，行為不變。
// R3（spec §4.40）：錄製小窗（Trigger/HUD.swift）依 hudVisible 顯示；圖示是否被擋住每 obscuredCheckSeconds 檢查一次
//   交給 obscuredAction；快捷鍵回饋依 feedbackRoute。
import AppKit

extension MenuBarController {
    /// 本場強制顯示 HUD（不寫設定）；只在 HUD 可能顯示的外觀（錄製中、靜音、告警、暫停）有效
    @objc func showHUDForThisRun() {
        guard let runId = status?.runId, hudEligible(model) else { return }
        hudForcedRunId = runId
        refresh()
    }

    /// HUD 可能顯示的外觀（錄製中、靜音、告警、暫停；spec §4.40.1）
    func hudEligible(_ m: MenuBarModel) -> Bool {
        hudVisible(mode: .always, obscured: false, appearance: m.appearance)
    }

    /// HUD 顯示與否＝hudVisible（設定的 hudMode、圖示是否被擋住、目前外觀）；收尾中與之後不顯示
    func updateHUD(_ m: MenuBarModel) {
        let settings = loadMenuBarSettings(home: home)
        // 「顯示錄製小窗」按過的那一場視同 always（不寫設定；換一場就失效；spec §4.41.3）
        let forced = hudForcedRunId != nil && hudForcedRunId == status?.runId
        let visible = hudVisible(mode: forced ? .always : settings.hudMode, obscured: iconObscured ?? false,
                                 appearance: m.appearance)
        let label = menuBarAccessibilityLabel(appearance: m.appearance, alertBadge: m.alertBadge, spoken: m.spokenDuration,
                                              alertText: latestAlertMessage(status), status: m.statusLine)
        hud.update(model: m, status: status, visible: visible, hudPosition: settings.hudPosition,
                   screen: item.button?.window?.screen, accessibilityLabel: label)
    }

    /// 標題列左側 10pt 圓點（spec §4.41.3）：待機 textDisabled、準備中與錄製中 recording、暫停 attention、
    /// 收尾中 processing、失敗 recording 空心環。顏色取自 DarkroomColor；非 template。
    func stageDotImage(_ a: MenuBarAppearance) -> NSImage {
        let hex: String
        var hollow = false
        switch a {
        case .idle: hex = DarkroomColor.textDisabled
        case .preparing, .recording, .recordingMuted, .recordingAlert: hex = DarkroomColor.recording
        case .paused: hex = DarkroomColor.attention
        case .finalizing: hex = DarkroomColor.processing
        case .failed:
            hex = DarkroomColor.recording
            hollow = true
        }
        let color = darkroomColor(hex)
        let d: CGFloat = 10
        let image = NSImage(size: NSSize(width: d, height: d), flipped: false) { rect in
            if hollow {
                let ring: CGFloat = 1.5
                let p = NSBezierPath(ovalIn: rect.insetBy(dx: ring / 2, dy: ring / 2))
                p.lineWidth = ring
                color.setStroke()
                p.stroke()
            } else {
                color.setFill()
                NSBezierPath(ovalIn: rect).fill()
            }
            return true
        }
        image.isTemplate = false
        return image
    }
}

// MARK: - HUD 按鈕的執行端（與選單同一條控制路徑；Trigger/HUD.swift）

extension MenuBarController: HUDActions {
    func hudControl(_ cmd: ControlCommand, action: String, availability: ControlAvailability) {
        performControl(cmd, action: action, availability: availability, feedback: false)
    }

    func hudStop(_ decision: StopTarget, status current: RecordStatus?) {
        guard model.canStop else {
            logStopSkip(stopPathLogLine(source: "hudStop", reason: "沒有進行中的錄製"))
            return
        }
        performStop(decision, current: current)
    }

    func hudRecordLockHeld() -> Bool {
        recordLockHeld()
    }

    func hudExecutablePath(_ pid: Int32) -> String? {
        executablePath(pid)
    }
}

// Trigger/Onboarding.swift —— 首次引導（U4-A 分步精靈 5 步；spec §4.43.5、§6 第 123、139 條；design-r3/README.md §6.2）
// menubar.settings.json 的 onboardingCompletedAt 為 nil 時，menu bar 啟動後顯示；設定視窗「重新執行首次設定…」也會叫起。
// 步驟：歡迎 → 權限 → 存檔位置（含 harness）→ 選單列空間 → 試錄（含四組快捷鍵說明）。
//   - 固定 onboardingWidth×onboardingHeight、不可縮放、跟系統深淺色（顏色一律取自 DarkroomColor）。
//   - 完成、全部略過或關閉視窗（Esc、⌘W，沿用設定視窗 PreferencesWindow 的實體鍵碼判斷）時寫 onboardingCompletedAt。
//   - 權限按鈕只觸發 TCC 授權框或打開系統設定，不做其他系統設定變更；狀態一律有狀態字（不只靠顏色）。
//   - 只有「存檔位置」一步呼叫 writeOnboardingDefaults（record.defaults.json 只寫 harness、root 兩鍵，合併寫入）。
//   - 試錄（§6 第 139 條）：場次放在 temporaryDirectory 底下的 meeting-harness-trial-<runId>/（--home 也指向這裡，
//     狀態檔、鎖檔、record.log 都不碰使用者的 ~/.meeting-harness），錄 5 秒自動停止；不帶 --harness、暫存 home 沒有
//     record.defaults.json，錄製實例找不到收尾程式就直接結束（跳過收尾）。讀狀態檔的 recentLevels 判斷兩路是否有聲，
//     之後以 removeItem 直接刪除這個暫存目錄（只限這個路徑），不移垃圾桶、不寫 record.discard.json、不跳確認框。
// 自訂繪製：步驟條、權限列、主按鈕；其餘用標準 AppKit 控制項。字型一律系統字（不打包字型，§4.43.9）。
import AppKit
import AVFoundation
import EventKit
import UserNotifications

/// 5 個步驟名（步驟條標籤與 VoiceOver）
let onboardingStepNames = ["歡迎", "權限", "存檔位置", "選單列空間", "試錄"]
/// 試錄長度（秒）
let trialRecordSeconds: Double = 5

// MARK: - 權限狀態（引導的權限步與設定視窗的「權限」分頁共用）

enum AppPermission: String, CaseIterable {
    case screenCapture, microphone, notifications, automation, reminders

    var title: String {
        switch self {
        case .screenCapture: return "螢幕錄製"
        case .microphone: return "麥克風"
        case .notifications: return "通知"
        case .automation: return "自動化（Chrome）"
        case .reminders: return "提醒事項"
        }
    }

    var detail: String {
        switch self {
        case .screenCapture: return "錄下你指定的會議視窗"
        case .microphone: return "錄你自己的聲音"
        case .notifications: return "錄製告警與完成提醒"
        case .automation: return "只有要錄 Chrome 分頁時才需要"
        case .reminders: return "只有 meeting reminders 把交辦寫進提醒事項時才需要"
        }
    }

    /// 選用的權限：沒給不影響錄製
    var isOptional: Bool { self == .automation || self == .reminders }

    /// 系統設定 › 隱私權與安全性（或通知）的對應頁面
    var settingsURL: URL? {
        let privacy = "x-apple.systempreferences:com.apple.preference.security?"
        switch self {
        case .screenCapture: return URL(string: privacy + "Privacy_ScreenCapture")
        case .microphone: return URL(string: privacy + "Privacy_Microphone")
        case .notifications: return URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")
        case .automation: return URL(string: privacy + "Privacy_Automation")
        case .reminders: return URL(string: privacy + "Privacy_Reminders")
        }
    }
}

enum AppPermissionState: Equatable {
    case granted, needsRelaunch, notDetermined, denied, optional

    /// 狀態字（狀態不只靠顏色）
    var statusText: String {
        switch self {
        case .granted: return "已允許"
        case .needsRelaunch: return "需要重新開啟"
        case .notDetermined: return "尚未允許"
        case .denied: return "被拒，要到系統設定打開"
        case .optional: return "選用"
        }
    }

    var buttonTitle: String {
        switch self {
        case .granted: return "已完成"
        case .needsRelaunch: return "重新開啟"
        case .notDetermined, .optional: return "允許"
        case .denied: return "打開系統設定"
        }
    }

    /// 狀態點的顏色 token（深色、淺色）
    var dotHex: (dark: String, light: String) {
        switch self {
        case .granted: return (DarkroomColor.done, DarkroomColor.doneOnLight)
        case .needsRelaunch: return (DarkroomColor.attention, DarkroomColor.attentionTextOnLight)
        case .notDetermined, .optional: return (DarkroomColor.textDisabled, DarkroomColor.lineOnLight)
        case .denied: return (DarkroomColor.recording, DarkroomColor.failedTextOnLight)
        }
    }

    /// 狀態字的顏色 token（深色、淺色）
    var textHex: (dark: String, light: String) {
        switch self {
        case .granted: return (DarkroomColor.doneText, DarkroomColor.doneOnLight)
        case .needsRelaunch: return (DarkroomColor.attentionText, DarkroomColor.attentionTextOnLight)
        case .notDetermined, .optional: return (DarkroomColor.textSecondary, DarkroomColor.textOnLight)
        case .denied: return (DarkroomColor.recordingText, DarkroomColor.failedTextOnLight)
        }
    }
}

/// 只查詢、不跳授權框；request 才會在使用者按「允許」時觸發 TCC 授權框。
enum PermissionProbe {
    /// 本程序是否已經對螢幕錄製要過一次授權（之後才打開的授權要重新開啟 app 才生效）
    static var screenCaptureRequested = false

    static func query(_ kinds: [AppPermission], done: @escaping ([AppPermission: AppPermissionState]) -> Void) {
        var result: [AppPermission: AppPermissionState] = [:]
        let group = DispatchGroup()
        let lock = NSLock()
        func set(_ k: AppPermission, _ s: AppPermissionState) {
            lock.lock()
            result[k] = s
            lock.unlock()
        }
        for k in kinds {
            switch k {
            case .screenCapture:
                set(k, CGPreflightScreenCaptureAccess() ? .granted : (screenCaptureRequested ? .needsRelaunch : .notDetermined))
            case .microphone:
                switch AVCaptureDevice.authorizationStatus(for: .audio) {
                case .authorized: set(k, .granted)
                case .notDetermined: set(k, .notDetermined)
                default: set(k, .denied)
                }
            case .notifications:
                guard Bundle.main.bundleIdentifier != nil else { set(k, .notDetermined); continue }
                group.enter()
                UNUserNotificationCenter.current().getNotificationSettings { s in
                    switch s.authorizationStatus {
                    case .authorized, .provisional, .ephemeral: set(k, .granted)
                    case .denied: set(k, .denied)
                    default: set(k, .notDetermined)
                    }
                    group.leave()
                }
            case .automation:
                group.enter()
                Task {
                    let st = await chromeAutomationStatus(askUserIfNeeded: false)
                    switch st {
                    case .authorized: set(k, .granted)
                    case .notAuthorized: set(k, .denied)
                    default: set(k, .optional)
                    }
                    group.leave()
                }
            case .reminders:
                switch EKEventStore.authorizationStatus(for: .reminder) {
                case .fullAccess: set(k, .granted)
                case .denied, .restricted, .writeOnly: set(k, .denied)
                default: set(k, .optional)
                }
            }
        }
        group.notify(queue: .main) { done(result) }
    }

    /// 依目前狀態執行按鈕的動作；完成後在主執行緒呼叫 then（重新查詢）
    static func act(_ k: AppPermission, state: AppPermissionState, then: @escaping () -> Void) {
        switch state {
        case .granted:
            then()
        case .denied:
            openSettings(k)
            then()
        case .needsRelaunch:
            relaunchApp()
        case .notDetermined, .optional:
            request(k, then: then)
        }
    }

    private static func request(_ k: AppPermission, then: @escaping () -> Void) {
        let back = { DispatchQueue.main.async { then() } }
        switch k {
        case .screenCapture:
            screenCaptureRequested = true
            _ = CGRequestScreenCaptureAccess()
            back()
        case .microphone:
            AVCaptureDevice.requestAccess(for: .audio) { _ in back() }
        case .notifications:
            guard Bundle.main.bundleIdentifier != nil else { back(); return }
            UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in back() }
        case .automation:
            // Chrome 沒在跑時不送任何 Apple Event（chromeAutomationStatus 直接回 chromeNotRunning）
            Task {
                _ = await chromeAutomationStatus(askUserIfNeeded: true)
                back()
            }
        case .reminders:
            // 提醒事項的授權由 meeting reminders 第一次寫入時要；這裡只帶到系統設定
            openSettings(k)
            back()
        }
    }

    static func openSettings(_ k: AppPermission) {
        if let url = k.settingsURL { NSWorkspace.shared.open(url) }
    }

    /// 螢幕錄製授權對已經啟動的程序不生效：本程序結束後再以 open -a 開回來
    static func relaunchApp() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = ["-c", "while /bin/kill -0 \"$1\" 2>/dev/null; do /bin/sleep 0.2; done; /usr/bin/open -a \"$2\"",
                       "relaunch", String(getpid()), Bundle.main.bundlePath]
        try? p.run()
        NSApp.terminate(nil)
    }
}

// MARK: - 顏色與字（取自 Core 的 token；Core 不 import AppKit）

/// "#RRGGBB" → sRGB NSColor；格式不對時用 labelColor
func darkroomHexColor(_ hex: String) -> NSColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return .labelColor }
    return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                   blue: CGFloat(v & 0xFF) / 255, alpha: 1)
}

/// 跟系統深淺色變的顏色（深色、淺色各一個 token）
func darkroomDynamicColor(dark: String, light: String) -> NSColor {
    NSColor(name: nil) { appearance in
        let match = appearance.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua,
                                                .accessibilityHighContrastDarkAqua])
        let isDark = match == .darkAqua || match == .accessibilityHighContrastDarkAqua
        return darkroomHexColor(isDark ? dark : light)
    }
}

/// TypeToken → 系統字（不打包字型；§4.43.9）
func darkroomFont(_ t: TypeToken) -> NSFont {
    let weight: NSFont.Weight
    switch t.weight {
    case "bold": weight = .bold
    case "semibold": weight = .semibold
    default: weight = .regular
    }
    return NSFont.systemFont(ofSize: CGFloat(t.size), weight: weight)
}

/// 視窗的面：深色 surface、淺色 light
let darkroomWindowBackground = darkroomDynamicColor(dark: DarkroomColor.surface, light: DarkroomColor.light)
private let rowBackground = darkroomDynamicColor(dark: DarkroomColor.raised, light: DarkroomColor.menuBarLight)
private let primaryText = darkroomDynamicColor(dark: DarkroomColor.text, light: DarkroomColor.textOnLight)
private let secondaryText = darkroomDynamicColor(dark: DarkroomColor.textSecondary, light: DarkroomColor.textOnLight)
private let tertiaryText = darkroomDynamicColor(dark: DarkroomColor.textTertiary, light: DarkroomColor.textOnLight)
private let lineColor = darkroomDynamicColor(dark: DarkroomColor.line, light: DarkroomColor.lineOnLight)
private let lineStrongColor = darkroomDynamicColor(dark: DarkroomColor.lineStrong, light: DarkroomColor.lineOnLight)
private let doneColor = darkroomDynamicColor(dark: DarkroomColor.done, light: DarkroomColor.doneOnLight)
/// 主按鈕：底 text、字 ink（淺色外觀反過來：底 textOnLight、字 light）
private let primaryButtonFill = darkroomDynamicColor(dark: DarkroomColor.text, light: DarkroomColor.textOnLight)
private let primaryButtonText = darkroomDynamicColor(dark: DarkroomColor.ink, light: DarkroomColor.light)

private func label(_ s: String, _ t: TypeToken, color: NSColor = primaryText, wrap: Bool = false) -> NSTextField {
    let l = wrap ? NSTextField(wrappingLabelWithString: s) : NSTextField(labelWithString: s)
    l.font = darkroomFont(t)
    l.textColor = color
    if wrap {
        l.preferredMaxLayoutWidth = CGFloat(DarkroomMetric.onboardingWidth - DarkroomMetric.onboardingPaddingH * 2)
    }
    return l
}

/// 路徑用等寬字（monospacedSystemFont）
private func pathLabel(_ s: String) -> NSTextField {
    let l = NSTextField(labelWithString: s)
    l.font = NSFont.monospacedSystemFont(ofSize: CGFloat(DarkroomType.rowDetail.size), weight: .regular)
    l.textColor = secondaryText
    l.lineBreakMode = .byTruncatingMiddle
    l.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    return l
}

private func vstack(_ views: [NSView], spacing: CGFloat) -> NSStackView {
    let s = NSStackView(views: views)
    s.orientation = .vertical
    s.alignment = .leading
    s.spacing = spacing
    return s
}

private func hstack(_ views: [NSView], spacing: CGFloat) -> NSStackView {
    let s = NSStackView(views: views)
    s.orientation = .horizontal
    s.alignment = .centerY
    s.spacing = spacing
    return s
}

// MARK: - 自訂元件：步驟條、主按鈕、權限列

/// 5 段步驟條（高 4、間距 8；已完成 done、目前 text、未到 line）＋下方標籤
final class OnboardingStepBar: NSView {
    var current = 0 {
        didSet {
            needsDisplay = true
            setAccessibilityLabel("第 \(current + 1) 步，共 5 步：\(onboardingStepNames[current])")
        }
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        setAccessibilityElement(true)
        setAccessibilityRole(.staticText)
        setAccessibilityLabel("第 1 步，共 5 步：\(onboardingStepNames[0])")
    }

    required init?(coder: NSCoder) { nil }

    override var intrinsicContentSize: NSSize { NSSize(width: NSView.noIntrinsicMetric, height: 24) }

    override func draw(_ dirtyRect: NSRect) {
        let n = CGFloat(onboardingStepNames.count)
        let gap: CGFloat = 8
        let w = (bounds.width - gap * (n - 1)) / n
        let font = darkroomFont(DarkroomType.stepLabel)
        for (i, name) in onboardingStepNames.enumerated() {
            let x = CGFloat(i) * (w + gap)
            let color = i < current ? doneColor : (i == current ? primaryText : lineColor)
            color.setFill()
            NSBezierPath(roundedRect: NSRect(x: x, y: bounds.height - 4, width: w, height: 4), xRadius: 2, yRadius: 2).fill()
            let attrs: [NSAttributedString.Key: Any] = [.font: font,
                                                        .foregroundColor: i == current ? primaryText : tertiaryText]
            (name as NSString).draw(at: NSPoint(x: x, y: 0), withAttributes: attrs)
        }
    }
}

/// 主按鈕（底 text、字 ink；高 buttonHeight、圓角 buttonCornerRadius）與外框按鈕
final class DarkroomButton: NSButton {
    enum Style { case primary, outline }
    private let style: Style

    init(title: String, style: Style, target: AnyObject?, action: Selector?) {
        self.style = style
        super.init(frame: .zero)
        self.title = title
        self.target = target
        self.action = action
        isBordered = false
        setButtonType(.momentaryPushIn)
        font = darkroomFont(style == .primary ? DarkroomType.button
                                              : TypeToken(size: DarkroomType.button.size, weight: "regular"))
    }

    required init?(coder: NSCoder) { nil }

    override var intrinsicContentSize: NSSize {
        let text = (title as NSString).size(withAttributes: [.font: font ?? darkroomFont(DarkroomType.button)])
        return NSSize(width: ceil(text.width) + 40, height: CGFloat(DarkroomMetric.buttonHeight))
    }

    override func draw(_ dirtyRect: NSRect) {
        let r = CGFloat(DarkroomMetric.buttonCornerRadius)
        let rect = bounds.insetBy(dx: 0.5, dy: 0.5)
        let path = NSBezierPath(roundedRect: rect, xRadius: r, yRadius: r)
        let alpha: CGFloat = isEnabled ? (isHighlighted ? 0.8 : 1) : 0.4
        let textColor: NSColor
        switch style {
        case .primary:
            primaryButtonFill.withAlphaComponent(alpha).setFill()
            path.fill()
            textColor = primaryButtonText
        case .outline:
            lineStrongColor.withAlphaComponent(alpha).setStroke()
            path.lineWidth = 1
            path.stroke()
            textColor = primaryText.withAlphaComponent(alpha)
        }
        let attrs: [NSAttributedString.Key: Any] = [.font: font ?? darkroomFont(DarkroomType.button),
                                                    .foregroundColor: textColor]
        let size = (title as NSString).size(withAttributes: attrs)
        (title as NSString).draw(at: NSPoint(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2),
                                 withAttributes: attrs)
    }
}

/// 權限列：狀態點＋名稱＋說明＋狀態字＋按鈕（底 raised、圓角 rowCornerRadius）
final class PermissionRowView: NSView {
    let permission: AppPermission
    private let dot = NSView()
    private let status = NSTextField(labelWithString: "")
    private let button: NSButton
    var onAction: ((AppPermission, AppPermissionState) -> Void)?
    private var state: AppPermissionState = .notDetermined

    init(_ p: AppPermission) {
        permission = p
        button = NSButton(title: "", target: nil, action: nil)
        super.init(frame: .zero)
        wantsLayer = true
        layer?.cornerRadius = CGFloat(DarkroomMetric.rowCornerRadius)
        dot.wantsLayer = true
        dot.layer?.cornerRadius = 5
        dot.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([dot.widthAnchor.constraint(equalToConstant: 10),
                                     dot.heightAnchor.constraint(equalToConstant: 10)])
        var titleText = p.title
        if p.isOptional { titleText += "（選用）" }
        let title = label(titleText, DarkroomType.rowTitle)
        let detail = label(p.detail, DarkroomType.rowDetail, color: secondaryText)
        status.font = darkroomFont(DarkroomType.rowDetail)
        button.bezelStyle = .rounded
        button.target = self
        button.action = #selector(tapped)
        let texts = vstack([title, detail, status], spacing: 2)
        let row = hstack([dot, texts, NSView(), button], spacing: CGFloat(DarkroomMetric.spacing[2]))
        row.translatesAutoresizingMaskIntoConstraints = false
        addSubview(row)
        let ph = CGFloat(DarkroomMetric.rowPaddingH), pv = CGFloat(DarkroomMetric.rowPaddingV)
        NSLayoutConstraint.activate([
            row.leadingAnchor.constraint(equalTo: leadingAnchor, constant: ph),
            row.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -ph),
            row.topAnchor.constraint(equalTo: topAnchor, constant: pv),
            row.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -pv),
        ])
        update(.notDetermined)
    }

    required init?(coder: NSCoder) { nil }

    override func updateLayer() {
        super.updateLayer()
        layer?.backgroundColor = rowBackground.cgColor
        dot.layer?.backgroundColor = darkroomDynamicColor(dark: state.dotHex.dark, light: state.dotHex.light).cgColor
    }

    override var wantsUpdateLayer: Bool { true }

    func update(_ s: AppPermissionState) {
        state = s
        status.stringValue = s.statusText
        status.textColor = darkroomDynamicColor(dark: s.textHex.dark, light: s.textHex.light)
        button.title = s.buttonTitle
        button.isEnabled = s != .granted
        needsDisplay = true
        setAccessibilityLabel("\(permission.title)：\(s.statusText)")
    }

    @objc private func tapped() {
        onAction?(permission, state)
    }
}

// MARK: - 試錄（§6 第 139 條）

enum TrialResult: Equatable {
    case notTried
    case running(String)
    case bothSound
    case missing(system: Bool, mic: Bool)
    case failed(String)

    var text: String {
        switch self {
        case .notTried: return "還沒試錄"
        case .running(let s): return s
        case .bothSound: return "兩路都有聲：系統聲音與麥克風都收得到。"
        case .missing(let system, let mic):
            var lines: [String] = []
            if system {
                lines.append("系統聲音沒有聲音：試錄時請播放一段有聲音的影片或會議，並確認輸出音量不是 0。")
            }
            if mic {
                lines.append("麥克風沒有聲音：試錄時請對麥克風說一句話，並確認麥克風權限已允許、輸入裝置選對。")
            }
            return lines.joined(separator: "\n")
        case .failed(let s): return "試錄沒有完成：\(s)"
        }
    }
}

/// 一次試錄：在暫存目錄開一個錄製實例（--home 與場次都在暫存目錄裡），錄 trialRecordSeconds 秒後停止，
/// 讀 recentLevels 判斷兩路是否有聲，錄製實例結束後直接刪除暫存目錄。
final class TrialRecording {
    let runId: String
    private let trialDir: URL
    private var timer: Timer?
    private var startedAt: Date?
    private var recordingSince: Date?
    private var stopSentAt: Date?
    private var maxSystem: Double?
    private var maxMic: Double?
    private var outcome: TrialResult?
    private var finished = false
    /// 已叫起錄製實例（start）
    private var launched = false
    private var cancelled = false
    private let onUpdate: (TrialResult) -> Void

    init(onUpdate: @escaping (TrialResult) -> Void) {
        let runId = UUID().uuidString
        self.runId = runId
        let trialDir = FileManager.default.temporaryDirectory.appendingPathComponent("meeting-harness-trial-\(runId)",
                                                                                     isDirectory: true)
        self.trialDir = trialDir
        self.onUpdate = onUpdate
    }

    private var statusURL: URL { trialDir.appendingPathComponent("record.status.json") }
    private var pidURL: URL { trialDir.appendingPathComponent("record.pid") }

    func start() {
        do {
            try FileManager.default.createDirectory(at: trialDir, withIntermediateDirectories: true)
        } catch {
            finish(.failed("建立暫存目錄失敗：\(error.localizedDescription)"))
            return
        }
        startedAt = Date()
        onUpdate(.running("試錄中：讀取視窗清單…"))
        let list = trialDir.appendingPathComponent("windows.json")
        openSelf(["windows", "--json", "--log", list.path])
        schedule(0.25) { [weak self] in self?.pollWindowList(list) }
    }

    /// 關掉引導時：還沒叫起錄製實例就直接結束；已叫起的照常輪詢，開錄後立刻停止，等它結束再刪暫存目錄
    /// （不在錄製實例還活著時刪目錄，免得留下一個沒人停的錄製）
    func cancel() {
        guard !finished else { return }
        cancelled = true
        outcome = outcome ?? .failed("已取消")
        if launched {
            sendStop()
        } else {
            cleanUp()
        }
    }

    private func schedule(_ interval: Double, _ tick: @escaping () -> Void) {
        timer?.invalidate()
        let t = Timer(timeInterval: interval, repeats: true) { _ in tick() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
    }

    private func pollWindowList(_ list: URL) {
        if let data = try? Data(contentsOf: list), !data.isEmpty,
           let rows = try? JSONDecoder().decode([WindowListRow].self, from: data) {
            // ★ 會議視窗優先，沒有就錄目前看得到的第一個視窗
            guard let row = rows.first(where: { $0.meeting != nil }) ?? rows.first(where: { $0.onScreen }) ?? rows.first
            else {
                finish(.failed("沒有可錄的視窗：先打開會議或任何一個視窗再試"))
                return
            }
            onUpdate(.running("試錄中：開錄前檢查…"))
            launched = true
            openSelf(["start", "--home", trialDir.path, "--session", trialDir.appendingPathComponent("session").path,
                      "--run-id", runId, "--window", String(row.windowID), "--window-bundle", row.bundleID,
                      "--window-title", row.title])
            schedule(0.5) { [weak self] in self?.pollStatus() }
        } else if Date().timeIntervalSince(startedAt ?? Date()) >= 15 {
            finish(.failed("取不到視窗清單：先在權限那一步允許螢幕錄製"))
        }
    }

    private func pollStatus() {
        let st = readStatus(statusURL)
        let pid = readPid(pidURL) ?? st?.pid
        let alive = pid.map(pidAlive) ?? false
        if let st, st.runId == runId {
            if let v = st.recentLevels?.system { maxSystem = max(maxSystem ?? v, v) }
            if let v = st.recentLevels?.mic { maxMic = max(maxMic ?? v, v) }
            switch st.phase {
            case .recording:
                if recordingSince == nil { recordingSince = Date() }
                if stopSentAt == nil, !cancelled {
                    let elapsed = Date().timeIntervalSince(recordingSince ?? Date())
                    onUpdate(.running("試錄中：\(max(0, Int(ceil(trialRecordSeconds - elapsed)))) 秒"))
                    if elapsed >= trialRecordSeconds { sendStop() }
                } else if cancelled {
                    sendStop()
                }
            case .preflightFailed, .failed:
                // 開錄前就失敗才算試錄失敗；錄過之後的 failed 是找不到收尾程式（刻意跳過收尾），照常判斷聲音
                guard recordingSince == nil else { break }
                outcome = outcome ?? .failed(st.message.split(separator: "\n").first.map(String.init) ?? "開錄前檢查沒通過")
            default:
                break
            }
        }
        // 錄製實例已結束（或從沒起來）：結算並刪除暫存目錄
        let waited = Date().timeIntervalSince(startedAt ?? Date())
        if !alive, (st?.phase == .done || st?.phase == .failed || st?.phase == .preflightFailed || stopSentAt != nil) {
            cleanUp()
        } else if waited >= 120 {
            outcome = outcome ?? .failed("等不到錄製實例結束")
            sendStop()
            if !alive { cleanUp() }
        }
    }

    /// 停止前先確認 pid 真的是持有暫存目錄 record.lock 的錄製實例（與選單的停止同一套 stopTargetDecision）
    private func sendStop() {
        guard stopSentAt == nil || Date().timeIntervalSince(stopSentAt ?? Date()) > 10 else { return }
        let recordPid = readPid(pidURL)
        let st = readStatus(statusURL)
        let lockHeld: Bool
        switch acquireRecordLock(home: trialDir, retrySeconds: 0) {
        case .acquired(let fd):
            close(fd)
            lockHeld = false
        case .heldByOther:
            lockHeld = true
        case .unavailable:
            lockHeld = false
        }
        let decision = stopTargetDecision(lockHeld: lockHeld, recordPid: recordPid,
                                          pidAlive: recordPid.map(pidAlive) ?? false, statusPid: st?.pid,
                                          command: recordPid.flatMap(trialExecutablePath))
        guard case let .signal(pid) = decision else { return }
        stopSentAt = Date()
        onUpdate(.running("試錄中：停止並檢查聲音…"))
        kill(pid, SIGTERM)
    }

    private func cleanUp() {
        guard !finished else { return }
        let result: TrialResult
        if let outcome {
            result = outcome
        } else if recordingSince == nil {
            result = .failed("錄製沒有開始")
        } else {
            let systemSilent = (maxSystem ?? -.infinity) <= -60
            let micSilent = (maxMic ?? -.infinity) <= -60
            result = systemSilent || micSilent ? .missing(system: systemSilent, mic: micSilent) : .bothSound
        }
        // 試錄的錄製實例找不到收尾程式會發一則「結束（有錯誤）」通知：收回它（暫存場次不是使用者的會議）
        if Bundle.main.bundleIdentifier != nil {
            UNUserNotificationCenter.current()
                .removeDeliveredNotifications(withIdentifiers: [completionNotificationID(runId: runId)])
        }
        // 直接刪除本程序建立的試錄暫存目錄（只限這個路徑；不移垃圾桶、不跳確認框；§6 第 139 條）
        try? FileManager.default.removeItem(at: trialDir)
        finish(result)
    }

    private func finish(_ r: TrialResult) {
        timer?.invalidate()
        timer = nil
        finished = true
        onUpdate(r)
    }

    private func openSelf(_ args: [String]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-n", "-a", Bundle.main.bundlePath, "--args"] + args
        try? p.run()
    }
}

/// 程序的執行檔完整路徑（stopTargetDecision 的 command）；取不到回 nil
private func trialExecutablePath(_ pid: Int32) -> String? {
    var buf = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
    let n = proc_pidpath(pid, &buf, UInt32(buf.count))
    return n > 0 ? String(cString: buf) : nil
}

/// meeting-harness 的位置：record.defaults.json 的 harness ＞ ~/.claude/skills/meeting-record（symlink 回 repo）往上找；
/// 都找不到才請使用者指定。只認含 bin/meeting.sh 的目錄。
func detectHarnessPath(home: URL) -> String? {
    func valid(_ p: String) -> Bool {
        FileManager.default.isExecutableFile(atPath: (p as NSString).appendingPathComponent("bin/meeting.sh"))
            || FileManager.default.fileExists(atPath: (p as NSString).appendingPathComponent("bin/meeting.sh"))
    }
    if let h = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))?.harness, valid(h) { return h }
    let skill = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".claude/skills/meeting-record")
    var dir = skill.resolvingSymlinksInPath()
    for _ in 0..<4 {
        if valid(dir.path) { return dir.path }
        dir = dir.deletingLastPathComponent()
    }
    return nil
}

// MARK: - 引導視窗

final class OnboardingWindowController: NSWindowController, NSWindowDelegate {
    private let home: URL
    private let prefsStore: MenuBarPrefsStore
    private let failedHotKeyIDs: Set<UInt32>
    /// 選單列圖示是否被擋住（MenuBarController 提供；nil＝還不知道）
    private let iconObscured: () -> Bool?
    private let stepBar = OnboardingStepBar()
    private let body = NSView()
    private var step = 0
    private lazy var skipButton: NSButton = {
        let b = NSButton(title: "略過", target: self, action: #selector(skip))
        b.isBordered = false
        b.font = darkroomFont(DarkroomType.button)
        b.contentTintColor = secondaryText
        return b
    }()
    private lazy var backButton = DarkroomButton(title: "上一步", style: .outline, target: self, action: #selector(back))
    private lazy var nextButton = DarkroomButton(title: "下一步", style: .primary, target: self, action: #selector(next))
    private var permissionRows: [PermissionRowView] = []
    private var stepTimer: Timer?
    private var rootPath: String?
    private var harnessPath: String?
    private let saveError = NSTextField(wrappingLabelWithString: "")
    private let obscuredLabel = NSTextField(labelWithString: "")
    private let obscuredHelp = NSTextField(wrappingLabelWithString: "")
    private lazy var alwaysHUDButton = NSButton(title: "改成一律顯示錄製小窗", target: self, action: #selector(alwaysShowHUD))
    private let trialLabel = NSTextField(wrappingLabelWithString: "")
    private lazy var trialButton = DarkroomButton(title: "試錄 5 秒", style: .outline, target: self, action: #selector(startTrial))
    private var trial: TrialRecording?
    private var completed = false

    init(home: URL, prefsStore: MenuBarPrefsStore, failedHotKeyIDs: Set<UInt32>, iconObscured: @escaping () -> Bool?) {
        self.home = home
        self.prefsStore = prefsStore
        self.failedHotKeyIDs = failedHotKeyIDs
        self.iconObscured = iconObscured
        // 固定尺寸、不可縮放；Esc、⌘W 沿用設定視窗的實體鍵碼判斷（PreferencesWindow）
        let window = PreferencesWindow(contentRect: NSRect(x: 0, y: 0, width: DarkroomMetric.onboardingWidth,
                                                           height: DarkroomMetric.onboardingHeight),
                                       styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "歡迎使用 MeetingRecorder"
        window.isReleasedWhenClosed = false
        window.backgroundColor = darkroomWindowBackground
        super.init(window: window)
        window.delegate = self
        let defaults = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))
        rootPath = (prefsStore.current.root?.isEmpty == false ? prefsStore.current.root : nil) ?? defaults?.root
        harnessPath = detectHarnessPath(home: home)
        build()
    }

    required init?(coder: NSCoder) { nil }

    func present() {
        completed = false
        show(step: 0)
        if window?.isVisible != true { window?.center() }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    private func build() {
        guard let content = window?.contentView else { return }
        let footer = hstack([skipButton, NSView(), backButton, nextButton], spacing: CGFloat(DarkroomMetric.spacing[2]))
        nextButton.keyEquivalent = "\r"      // Return＝主按鈕
        for v in [stepBar, body, footer] {
            v.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(v)
        }
        let ph = CGFloat(DarkroomMetric.onboardingPaddingH), pv = CGFloat(DarkroomMetric.onboardingPaddingV)
        NSLayoutConstraint.activate([
            stepBar.topAnchor.constraint(equalTo: content.topAnchor, constant: pv),
            stepBar.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: ph),
            stepBar.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -ph),
            stepBar.heightAnchor.constraint(equalToConstant: 24),
            body.topAnchor.constraint(equalTo: stepBar.bottomAnchor, constant: CGFloat(DarkroomMetric.spacing[4])),
            body.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: ph),
            body.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -ph),
            body.bottomAnchor.constraint(lessThanOrEqualTo: footer.topAnchor, constant: -CGFloat(DarkroomMetric.spacing[3])),
            footer.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: ph),
            footer.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -ph),
            footer.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -pv),
        ])
        saveError.font = darkroomFont(DarkroomType.rowDetail)
        saveError.textColor = darkroomDynamicColor(dark: DarkroomColor.recordingText, light: DarkroomColor.failedTextOnLight)
        obscuredLabel.font = darkroomFont(DarkroomType.rowTitle)
        obscuredHelp.font = darkroomFont(DarkroomType.onboardingBody)
        obscuredHelp.textColor = secondaryText
        trialLabel.font = darkroomFont(DarkroomType.onboardingBody)
        trialLabel.textColor = secondaryText
    }

    // MARK: 換步（不做轉場動畫，「減少動態效果」下也一樣）

    private func show(step s: Int) {
        step = max(0, min(s, onboardingStepNames.count - 1))
        stepTimer?.invalidate()
        stepTimer = nil
        stepBar.current = step
        backButton.isEnabled = step > 0
        nextButton.title = step == onboardingStepNames.count - 1 ? "完成" : "下一步"
        nextButton.invalidateIntrinsicContentSize()
        nextButton.needsDisplay = true
        body.subviews.forEach { $0.removeFromSuperview() }
        let page: NSView
        switch step {
        case 0: page = welcomePage()
        case 1: page = permissionsPage()
        case 2: page = savePage()
        case 3: page = menuBarPage()
        default: page = trialPage()
        }
        page.translatesAutoresizingMaskIntoConstraints = false
        body.addSubview(page)
        NSLayoutConstraint.activate([
            page.topAnchor.constraint(equalTo: body.topAnchor),
            page.leadingAnchor.constraint(equalTo: body.leadingAnchor),
            page.trailingAnchor.constraint(equalTo: body.trailingAnchor),
            page.bottomAnchor.constraint(equalTo: body.bottomAnchor),
        ])
    }

    private func page(title: String, body text: String, _ extra: [NSView]) -> NSView {
        let t = label(title, DarkroomType.onboardingTitle)
        let b = label(text, DarkroomType.onboardingBody, color: secondaryText, wrap: true)
        let s = vstack([t, b] + extra, spacing: CGFloat(DarkroomMetric.spacing[3]))
        for v in extra { v.widthAnchor.constraint(equalTo: s.widthAnchor).isActive = true }
        return s
    }

    private func welcomePage() -> NSView {
        page(title: "錄會議，全部留在這台電腦", body: "錄指定的會議視窗、系統聲音與麥克風，全部留在本機。", [])
    }

    private func permissionsPage() -> NSView {
        // 引導只列四項（spec §4.43.5）；提醒事項在設定的「權限」分頁
        let kinds: [AppPermission] = [.screenCapture, .microphone, .notifications, .automation]
        permissionRows = kinds.map { k in
            let r = PermissionRowView(k)
            r.onAction = { [weak self] p, st in PermissionProbe.act(p, state: st) { self?.reloadPermissions() } }
            return r
        }
        let rows = vstack(permissionRows, spacing: CGFloat(DarkroomMetric.rowGap))
        for r in permissionRows { r.widthAnchor.constraint(equalTo: rows.widthAnchor).isActive = true }
        reloadPermissions()
        // 使用者在系統設定改完回來時更新狀態
        let t = Timer(timeInterval: 2, repeats: true) { [weak self] _ in self?.reloadPermissions() }
        RunLoop.main.add(t, forMode: .common)
        stepTimer = t
        return page(title: "先給三個權限", body: "錄影、聲音與通知都只留在這台電腦。", [rows])
    }

    private func reloadPermissions() {
        let rows = permissionRows
        PermissionProbe.query(rows.map { $0.permission }) { states in
            for r in rows { r.update(states[r.permission] ?? .notDetermined) }
        }
    }

    private func savePage() -> NSView {
        let rootValue = pathLabel(rootPath.map { ($0 as NSString).abbreviatingWithTildeInPath } ?? "還沒選")
        let rootChange = NSButton(title: "更改…", target: self, action: #selector(changeRoot))
        let harnessValue = pathLabel(harnessPath.map { ($0 as NSString).abbreviatingWithTildeInPath }
                                     ?? "找不到，請指定 meeting-harness 資料夾")
        let harnessChange = NSButton(title: "更改…", target: self, action: #selector(changeHarness))
        saveError.stringValue = ""
        let rows = vstack([
            label("存檔資料夾", DarkroomType.rowTitle), hstack([rootValue, rootChange], spacing: 8),
            label("meeting-harness 位置", DarkroomType.rowTitle), hstack([harnessValue, harnessChange], spacing: 8),
            saveError,
        ], spacing: CGFloat(DarkroomMetric.spacing[1]))
        return page(title: "錄好的檔案放哪裡",
                    body: "每場會議會在存檔資料夾底下開一個資料夾。按「下一步」時記下這兩個位置。", [rows])
    }

    private func menuBarPage() -> NSView {
        obscuredHelp.stringValue = "看不到時：按住 ⌘ 拖動選單列圖示，把它移到瀏海旁看得到的位置；或到「系統設定 › 選單列」"
            + "關掉用不到的圖示。也可以讓錄製時一律在螢幕邊緣顯示錄製小窗。"
        alwaysHUDButton.isEnabled = loadMenuBarSettings(home: home).hudMode != .always
        alwaysHUDButton.title = alwaysHUDButton.isEnabled ? "改成一律顯示錄製小窗" : "已改成一律顯示錄製小窗"
        reloadObscured()
        let t = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.reloadObscured() }
        RunLoop.main.add(t, forMode: .common)
        stepTimer = t
        return page(title: "確認看得到選單列圖示",
                    body: "錄製時看選單列的錄製膠囊就知道狀態。有瀏海的螢幕上，圖示多的時候可能被擋住。",
                    [obscuredLabel, obscuredHelp, alwaysHUDButton])
    }

    private func reloadObscured() {
        let o = iconObscured()
        switch o {
        case .some(true):
            obscuredLabel.stringValue = "被擋住"
            obscuredLabel.textColor = darkroomDynamicColor(dark: DarkroomColor.attentionText,
                                                           light: DarkroomColor.attentionTextOnLight)
        case .some(false):
            obscuredLabel.stringValue = "看得到"
            obscuredLabel.textColor = darkroomDynamicColor(dark: DarkroomColor.doneText, light: DarkroomColor.doneOnLight)
        case .none:
            obscuredLabel.stringValue = "還不確定"
            obscuredLabel.textColor = secondaryText
        }
        obscuredHelp.isHidden = o != true
        alwaysHUDButton.isHidden = o != true
    }

    private func trialPage() -> NSView {
        let names = hotKeyActionTitles
        let keys = r2HotKeys.map { spec -> NSView in
            let failed = failedHotKeyIDs.contains(spec.id)
            let key = NSTextField(labelWithString: spec.display)
            key.font = NSFont.monospacedSystemFont(ofSize: CGFloat(DarkroomType.rowDetail.size), weight: .regular)
            key.textColor = primaryText
            let text = (names[spec.action] ?? spec.action) + (failed ? "（註冊失敗，請改用選單）" : "")
            return hstack([key, label(text, DarkroomType.rowDetail, color: secondaryText)], spacing: 12)
        }
        if trial == nil { trialLabel.stringValue = TrialResult.notTried.text }
        return page(title: "試錄 5 秒",
                    body: "按「試錄 5 秒」錄一小段，確認系統聲音與麥克風都收得到。試錄放在暫存目錄，錄完直接刪除，"
                        + "不會出現在存檔資料夾，也不會移到垃圾桶。",
                    [vstack(keys, spacing: 4), trialButton, trialLabel])
    }

    // MARK: 動作

    @objc private func next() {
        if step == 2, !saveLocations() { return }
        if step == onboardingStepNames.count - 1 {
            finish()
        } else {
            show(step: step + 1)
        }
    }

    @objc private func back() {
        show(step: step - 1)
    }

    /// 略過這一步；最後一步略過＝結束引導
    @objc private func skip() {
        if step == onboardingStepNames.count - 1 {
            finish()
        } else {
            show(step: step + 1)
        }
    }

    /// 「存檔位置」一步：只在這裡呼叫 writeOnboardingDefaults（只寫 harness、root 兩鍵、合併寫入；§6 第 123 條）
    private func saveLocations() -> Bool {
        guard let root = rootPath, !root.isEmpty else {
            saveError.stringValue = "請先選存檔資料夾（或按「略過」）"
            return false
        }
        guard let harness = harnessPath, !harness.isEmpty else {
            saveError.stringValue = "請先指定 meeting-harness 資料夾（或按「略過」）"
            return false
        }
        do {
            try writeOnboardingDefaults(home: home, harness: harness, root: root)
        } catch DefaultsMergeError.notObject {
            saveError.stringValue = "record.defaults.json 不是 JSON 物件，沒有覆寫；請先修好或刪掉它"
            return false
        } catch DefaultsMergeError.lockTimeout {
            saveError.stringValue = "record.defaults.json 正在被別的程序寫入，請稍後再按一次"
            return false
        } catch {
            saveError.stringValue = "寫入失敗：\(error.localizedDescription)"
            return false
        }
        return true
    }

    @objc private func changeRoot() {
        guard let path = chooseFolder(startingAt: rootPath) else { return }
        rootPath = path
        show(step: 2)
        window?.makeKeyAndOrderFront(nil)
    }

    @objc private func changeHarness() {
        guard let path = chooseFolder(startingAt: harnessPath) else { return }
        guard FileManager.default.fileExists(atPath: (path as NSString).appendingPathComponent("bin/meeting.sh")) else {
            show(step: 2)
            saveError.stringValue = "這個資料夾裡沒有 bin/meeting.sh，不是 meeting-harness"
            window?.makeKeyAndOrderFront(nil)
            return
        }
        harnessPath = path
        show(step: 2)
        window?.makeKeyAndOrderFront(nil)
    }

    /// 選單列空間被擋住時：寫 hudMode = always（menubar.settings.json）
    @objc private func alwaysShowHUD() {
        var s = loadMenuBarSettings(home: home)
        s.hudMode = .always
        do {
            try saveMenuBarSettings(s, home: home)
            alwaysHUDButton.isEnabled = false
            alwaysHUDButton.title = "已改成一律顯示錄製小窗"
        } catch {
            obscuredHelp.stringValue = "寫設定失敗：\(error.localizedDescription)"
        }
    }

    @objc private func startTrial() {
        guard trial == nil else { return }
        trialButton.isEnabled = false
        let t = TrialRecording { [weak self] r in
            guard let self else { return }
            self.trialLabel.stringValue = r.text
            if case .running = r { return }
            self.trial = nil
            self.trialButton.isEnabled = true
        }
        trial = t
        t.start()
    }

    // MARK: 結束（完成、略過最後一步、關閉視窗都算看過引導）

    private func finish() {
        markCompleted()
        window?.close()
    }

    func windowWillClose(_ notification: Notification) {
        stepTimer?.invalidate()
        stepTimer = nil
        trial?.cancel()
        markCompleted()
    }

    private func markCompleted() {
        guard !completed else { return }
        completed = true
        var s = loadMenuBarSettings(home: home)
        s.onboardingCompletedAt = isoNow()
        do {
            try saveMenuBarSettings(s, home: home)
        } catch {
            Logger(path: home.appendingPathComponent("record.log").path, append: true)
                .line("\(isoNow()) 寫 \(menuBarSettingsFileName) 失敗：\(error.localizedDescription)")
        }
    }
}

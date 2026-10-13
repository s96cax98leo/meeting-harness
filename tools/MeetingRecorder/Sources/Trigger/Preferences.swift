// Trigger/Preferences.swift —— 設定視窗（spec §4.22.4、§4.22.5、§4.43.6、§4.44.4、§6 第 130 條；HIG settings window 慣例）
// R3 U5-A：7 個工具列分頁（NSToolbar；SettingsTab 的 title、symbolName 來自 Core）。寬 settingsWidth 固定、高跟內容、
// 不可縮放、只有一個；視窗標題跟著分頁變成該分頁的 title；記住上次分頁（menubar.settings.json 的 lastSettingsTab）。
// 改動立即寫入，沒有「確定」按鈕。控制項用標準 AppKit，只有視窗底色用 token（跟系統深淺色）。
// 登入項目（SMAppService）只在這個檔處理，而且只在使用者點勾選框時註冊／取消；任何自動流程都不註冊。
import AppKit
import ServiceManagement

/// app 沒有 main menu（LSUIElement），標準的 ⌘W 與 Esc 不會自動接到視窗上：自己處理（設計審查 R2 SF-2）。
/// ⌘W 的 W 鍵實體鍵碼（Carbon kVK_ANSI_W），與鍵盤配置、輸入法無關。
let preferencesCloseKeyCode: UInt16 = 13

/// 四組快捷鍵的動作名（設定的「快捷鍵」分頁與首次引導的試錄步共用）
let hotKeyActionTitles = ["start": "開始錄製（用上次的設定）", "mute": "麥克風靜音／取消靜音", "pause": "暫停／繼續錄製",
                          "mark": "加標記"]

final class PreferencesWindow: NSWindow {
    override func cancelOperation(_ sender: Any?) { performClose(sender) }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        // t7（§6 第 104 條）：注音等中文輸入法下 charactersIgnoringModifiers 不是 "w"——以實體鍵碼判斷（kVK_ANSI_W＝13）
        let mods = event.modifierFlags.intersection([.command, .shift, .option, .control])
        if mods == .command, event.keyCode == preferencesCloseKeyCode || event.charactersIgnoringModifiers == "w" {
            performClose(nil)
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class PreferencesWindowController: NSWindowController, NSToolbarDelegate {
    private let home: URL
    private let prefsStore: MenuBarPrefsStore
    private let failedHotKeyIDs: Set<UInt32>
    /// 「重新執行首次設定…」：交給 MenuBarController 開引導視窗
    private let onRerunOnboarding: () -> Void
    private var currentTab: SettingsTab = .general
    private let rootLabel = NSTextField(labelWithString: "")
    private let recentLabel = NSTextField(wrappingLabelWithString: "")
    private let loginCheckbox = NSButton(checkboxWithTitle: "登入時自動開啟", target: nil, action: nil)
    private let loginNote = NSTextField(wrappingLabelWithString: "")
    private let openSettingsButton = NSButton(title: "打開系統設定的登入項目", target: nil, action: nil)
    private let autoPrepCheckbox = NSButton(checkboxWithTitle: "停止後自動跑前處理", target: nil, action: nil)
    private let timerCheckbox = NSButton(checkboxWithTitle: "選單列計時：錄製中顯示 12:34", target: nil, action: nil)
    private let hudModeControl = NSSegmentedControl(labels: ["自動", "一律顯示", "不要"], trackingMode: .selectOne,
                                                    target: nil, action: nil)
    private let hudPositionControl = NSSegmentedControl(labels: ["右邊緣", "左邊緣"], trackingMode: .selectOne,
                                                        target: nil, action: nil)
    private let timeSensitiveCheckbox = NSButton(checkboxWithTitle: "用時效性通知（可穿過專注模式）", target: nil, action: nil)
    private let meetingDetectCheckbox = NSButton(checkboxWithTitle: "偵測到會議 app 使用麥克風時問我要不要錄", target: nil,
                                                 action: nil)
    private let notificationStatus = NSTextField(labelWithString: "")
    private var permissionLabels: [AppPermission: NSTextField] = [:]
    private var pages: [SettingsTab: NSView] = [:]

    init(home: URL, prefsStore: MenuBarPrefsStore, failedHotKeyIDs: Set<UInt32>,
         onRerunOnboarding: @escaping () -> Void = {}) {
        self.home = home
        self.prefsStore = prefsStore
        self.failedHotKeyIDs = failedHotKeyIDs
        self.onRerunOnboarding = onRerunOnboarding
        let window = PreferencesWindow(contentRect: NSRect(x: 0, y: 0, width: DarkroomMetric.settingsWidth, height: 300),
                                       styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.backgroundColor = darkroomWindowBackground
        window.toolbarStyle = .preference
        super.init(window: window)
        build()
    }

    required init?(coder: NSCoder) { nil }

    /// 已開就帶到前面，不開第二個；打開時回到上次的分頁
    func present() {
        let tab = settingsTab(loadMenuBarSettings(home: home).lastSettingsTab)
        select(tab, remember: false)
        if window?.isVisible != true { window?.center() }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    // MARK: - 工具列分頁

    private func build() {
        let toolbar = NSToolbar(identifier: "MeetingRecorderSettings")
        toolbar.delegate = self
        toolbar.displayMode = .iconAndLabel
        toolbar.allowsUserCustomization = false
        window?.toolbar = toolbar
        for c in [loginCheckbox, autoPrepCheckbox, timerCheckbox, timeSensitiveCheckbox, meetingDetectCheckbox] {
            c.target = self
        }
        loginCheckbox.action = #selector(toggleLoginItem(_:))
        autoPrepCheckbox.action = #selector(toggleAutoPrep(_:))
        timerCheckbox.action = #selector(toggleTimer(_:))
        timeSensitiveCheckbox.action = #selector(toggleTimeSensitive(_:))
        meetingDetectCheckbox.action = #selector(toggleMeetingDetect(_:))
        hudModeControl.target = self
        hudModeControl.action = #selector(changeHUDMode(_:))
        hudPositionControl.target = self
        hudPositionControl.action = #selector(changeHUDPosition(_:))
        openSettingsButton.target = self
        openSettingsButton.action = #selector(openLoginItemsSettings)
    }

    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        SettingsTab.allCases.map { NSToolbarItem.Identifier($0.rawValue) }
    }

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarAllowedItemIdentifiers(toolbar)
    }

    func toolbarSelectableItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        toolbarAllowedItemIdentifiers(toolbar)
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier id: NSToolbarItem.Identifier,
                 willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        let tab = settingsTab(id.rawValue)
        let item = NSToolbarItem(itemIdentifier: id)
        item.label = tab.title
        item.paletteLabel = tab.title
        item.toolTip = tab.title
        item.image = NSImage(systemSymbolName: tab.symbolName, accessibilityDescription: tab.title)
        item.target = self
        item.action = #selector(toolbarTabClicked(_:))
        return item
    }

    @objc private func toolbarTabClicked(_ sender: NSToolbarItem) {
        select(settingsTab(sender.itemIdentifier.rawValue), remember: true)
    }

    /// 換分頁：視窗標題＝分頁的 title（HIG；§6 第 130 條），高度跟內容，寬度固定 settingsWidth
    private func select(_ tab: SettingsTab, remember: Bool) {
        currentTab = tab
        window?.toolbar?.selectedItemIdentifier = NSToolbarItem.Identifier(tab.rawValue)
        window?.title = tab.title
        reload()
        let page = pages[tab] ?? makePage(tab)
        pages[tab] = page
        // 每次換分頁都放進新的容器（舊容器連同約束一起丟掉）
        page.removeFromSuperview()
        let container = NSView()
        page.translatesAutoresizingMaskIntoConstraints = false
        container.addSubview(page)
        let pad = CGFloat(DarkroomMetric.spacing[4])
        NSLayoutConstraint.activate([
            page.topAnchor.constraint(equalTo: container.topAnchor, constant: pad),
            page.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -pad),
            page.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: pad),
            page.trailingAnchor.constraint(lessThanOrEqualTo: container.trailingAnchor, constant: -pad),
            container.widthAnchor.constraint(equalToConstant: CGFloat(DarkroomMetric.settingsWidth)),
        ])
        container.layoutSubtreeIfNeeded()
        let size = NSSize(width: CGFloat(DarkroomMetric.settingsWidth), height: container.fittingSize.height)
        if let window {
            // 頂端固定、往下長（不做動畫；「減少動態效果」下也一樣）
            let frame = window.frameRect(forContentRect: NSRect(origin: .zero, size: size))
            let top = window.frame.maxY
            window.contentView = container
            window.setFrame(NSRect(x: window.frame.minX, y: top - frame.height, width: frame.width, height: frame.height),
                            display: true)
        }
        if remember {
            var s = loadMenuBarSettings(home: home)
            s.lastSettingsTab = tab.rawValue
            saveSettings(s)
        }
    }

    // MARK: - 分頁內容

    private func sectionLabel(_ s: String) -> NSTextField {
        let l = NSTextField(labelWithString: s)
        l.alignment = .right
        l.font = darkroomFont(DarkroomType.settingsRowLabel)
        return l
    }

    private func note(_ s: String) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: s)
        l.font = darkroomFont(DarkroomType.caption)
        l.textColor = .secondaryLabelColor
        l.preferredMaxLayoutWidth = 380
        return l
    }

    /// 路徑、指令用等寬字
    private func mono(_ s: String) -> NSTextField {
        let l = NSTextField(labelWithString: s)
        l.font = NSFont.monospacedSystemFont(ofSize: CGFloat(DarkroomType.caption.size), weight: .regular)
        l.textColor = .secondaryLabelColor
        l.lineBreakMode = .byTruncatingMiddle
        l.preferredMaxLayoutWidth = 380
        l.isSelectable = true
        return l
    }

    private func column(_ views: [NSView], spacing: CGFloat = 6) -> NSStackView {
        let s = NSStackView(views: views)
        s.orientation = .vertical
        s.alignment = .leading
        s.spacing = spacing
        return s
    }

    private func grid(_ rows: [(String, NSView)]) -> NSGridView {
        let g = NSGridView(views: rows.map { [sectionLabel($0.0), $0.1] })
        g.rowSpacing = 18
        g.columnSpacing = 10
        g.column(at: 0).xPlacement = .trailing
        g.column(at: 0).width = 130
        for r in 0..<g.numberOfRows { g.row(at: r).yPlacement = .top }
        return g
    }

    private func makePage(_ tab: SettingsTab) -> NSView {
        switch tab {
        case .general: return generalPage()
        case .recording: return recordingPage()
        case .feedback: return feedbackPage()
        case .hotkeys: return hotkeysPage()
        case .afterRecording: return afterRecordingPage()
        case .permissions: return permissionsPage()
        case .advanced: return advancedPage()
        }
    }

    private func generalPage() -> NSView {
        rootLabel.lineBreakMode = .byTruncatingMiddle
        rootLabel.preferredMaxLayoutWidth = 380
        rootLabel.font = NSFont.monospacedSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
        recentLabel.font = NSFont.monospacedSystemFont(ofSize: CGFloat(DarkroomType.caption.size), weight: .regular)
        recentLabel.textColor = .secondaryLabelColor
        recentLabel.preferredMaxLayoutWidth = 380
        let change = NSButton(title: "更改…", target: self, action: #selector(changeRoot))
        loginNote.font = darkroomFont(DarkroomType.caption)
        loginNote.textColor = .secondaryLabelColor
        loginNote.preferredMaxLayoutWidth = 380
        let harness = defaults()?.harness
        return grid([
            ("預設存檔位置：", column([rootLabel, change])),
            ("最近用過的位置：", recentLabel),
            ("登入：", column([loginCheckbox, loginNote, openSettingsButton])),
            ("meeting-harness：", column([mono(harness.map { ($0 as NSString).abbreviatingWithTildeInPath } ?? "（還沒設定）"),
                                          note("唯讀；由首次設定或 meeting record 記下")])),
        ])
    }

    private func recordingPage() -> NSView {
        let d = defaults()
        let type = NSTextField(labelWithString: d?.type ?? "（還沒設定）")
        let attendees = NSTextField(wrappingLabelWithString: (d?.attendees.isEmpty ?? true) ? "（沒有）"
                                    : d!.attendees.joined(separator: "、"))
        attendees.preferredMaxLayoutWidth = 380
        return grid([
            ("預設會議類型：", type),
            ("與會者：", column([attendees, note("唯讀；要改請在終端機跑 meeting record")])),
            ("★ 快速開錄：", note("「開始錄製（用上次的設定）」與 ⌃⌥⌘R 只在視窗清單裡恰好一個 ★ 會議視窗時開錄；"
                                  + "有好幾個或一個都沒有時不猜，請改用「錄其他視窗」。")),
        ])
    }

    private func feedbackPage() -> NSView {
        let openNotify = NSButton(title: "打開通知設定", target: self, action: #selector(openNotificationSettings))
        notificationStatus.font = darkroomFont(DarkroomType.settingsRowLabel)
        return grid([
            ("選單列計時：", timerCheckbox),
            ("錄製小窗：", column([hudModeControl, note("自動：選單列圖示被瀏海擋住時才出現")])),
            ("錄製小窗位置：", hudPositionControl),
            ("錄製中告警：", timeSensitiveCheckbox),
            ("會議偵測：", column([meetingDetectCheckbox,
                                  note("只看麥克風是否被會議 app 使用與前景 app 的名稱；不開麥克風、不讀視窗標題，也不會自動開錄")])),
            ("通知授權：", column([notificationStatus, openNotify])),
        ])
    }

    private func hotkeysPage() -> NSView {
        // 四組快捷鍵（唯讀，D7-A；註冊失敗的那組就地標出來）
        let keyRows: [NSView] = r2HotKeys.map { spec in
            let failed = failedHotKeyIDs.contains(spec.id)
            let text = "\(spec.display)　\(hotKeyActionTitles[spec.action] ?? spec.action)" + (failed ? "（註冊失敗，請改用選單）" : "")
            let l = NSTextField(labelWithString: text)
            l.font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
            if failed { l.textColor = darkroomDynamicColor(dark: DarkroomColor.recordingText, light: DarkroomColor.failedTextOnLight) }
            return l
        }
        return grid([("快捷鍵：", column(keyRows + [note("快捷鍵不能修改")], spacing: 4))])
    }

    private func afterRecordingPage() -> NSView {
        let log = home.appendingPathComponent("autoprep.log").path
        return grid([
            ("錄完之後：", column([autoPrepCheckbox,
                                  note("錄製收尾成功後，在背景跑 meeting.sh prep（轉錄、投影片 OCR、講者分離），輸出寫到 autoprep.log"),
                                  mono((log as NSString).abbreviatingWithTildeInPath)])),
        ])
    }

    private func permissionsPage() -> NSView {
        var rows: [(String, NSView)] = []
        for p in AppPermission.allCases {
            let status = NSTextField(labelWithString: "")
            status.font = darkroomFont(DarkroomType.settingsRowLabel)
            permissionLabels[p] = status
            let open = NSButton(title: "打開系統設定", target: self, action: #selector(openPermissionSettings(_:)))
            open.identifier = NSUserInterfaceItemIdentifier(p.rawValue)
            rows.append((p.title + "：", column([status, note(p.detail), open], spacing: 4)))
        }
        let rerun = NSButton(title: "重新執行首次設定…", target: self, action: #selector(rerunOnboarding))
        rows.append(("首次設定：", rerun))
        return grid(rows)
    }

    private func advancedPage() -> NSView {
        let sync = syncCompensationValue()
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
        return grid([
            ("影音同步補償：", column([mono("syncCompensation=\(sync)"),
                                     note("唯讀；用 meeting sync 修改（例：meeting sync reported），下一次收尾起生效")])),
            ("記錄檔：", column([mono((home.appendingPathComponent("record.log").path as NSString).abbreviatingWithTildeInPath),
                                mono((home.appendingPathComponent("autoprep.log").path as NSString).abbreviatingWithTildeInPath)],
                               spacing: 2)),
            ("版本：", NSTextField(labelWithString: version)),
        ])
    }

    // MARK: - 讀值

    private func defaults() -> RecordDefaults? {
        RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))
    }

    /// record.defaults.json 的 syncCompensation（缺鍵＝off；只讀，§3.16）
    private func syncCompensationValue() -> String {
        guard let data = try? Data(contentsOf: home.appendingPathComponent("record.defaults.json")),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let v = obj["syncCompensation"] as? String, !v.isEmpty else { return "off" }
        return v
    }

    private func reload() {
        let prefs = prefsStore.current
        let root = (prefs.root?.isEmpty == false ? prefs.root : nil) ?? defaults()?.root
        rootLabel.stringValue = root.map { ($0 as NSString).abbreviatingWithTildeInPath }
            ?? "還沒有設定：請先在終端機跑一次 meeting record，或按「更改…」"
        rootLabel.toolTip = root
        let recent = prefs.recentRoots.map { ($0 as NSString).abbreviatingWithTildeInPath }
        recentLabel.stringValue = recent.isEmpty ? "（沒有）" : recent.joined(separator: "\n")
        autoPrepCheckbox.state = prefs.autoPrep ? .on : .off
        let s = loadMenuBarSettings(home: home)
        timerCheckbox.state = s.showTimer ? .on : .off
        hudModeControl.selectedSegment = HUDMode.allCases.firstIndex(of: s.hudMode) ?? 0
        hudPositionControl.selectedSegment = s.hudPosition == "left" ? 1 : 0
        timeSensitiveCheckbox.state = s.timeSensitiveAlerts ? .on : .off
        meetingDetectCheckbox.state = s.meetingDetect ? .on : .off
        reloadLoginItem()
        PermissionProbe.query(AppPermission.allCases) { [weak self] states in
            guard let self else { return }
            for (p, l) in self.permissionLabels { l.stringValue = (states[p] ?? .notDetermined).statusText }
            self.notificationStatus.stringValue = (states[.notifications] ?? .notDetermined).statusText
        }
    }

    private func saveSettings(_ s: MenuBarSettings) {
        do {
            try saveMenuBarSettings(s, home: home)
        } catch {
            Logger(path: home.appendingPathComponent("record.log").path, append: true)
                .line("\(isoNow()) 寫 \(menuBarSettingsFileName) 失敗：\(error.localizedDescription)")
        }
    }

    private func updateSettings(_ change: (inout MenuBarSettings) -> Void) {
        var s = loadMenuBarSettings(home: home)
        change(&s)
        saveSettings(s)
    }

    private func loginItemState() -> LoginItemState {
        switch SMAppService.mainApp.status {
        case .enabled: return .enabled
        case .requiresApproval: return .requiresApproval
        case .notRegistered: return .notRegistered
        case .notFound: return .notFound
        @unknown default: return .notFound
        }
    }

    private func reloadLoginItem(error: String? = nil) {
        let d = loginItemDisplay(loginItemState())
        loginCheckbox.state = d.isOn ? .on : .off
        let text = [d.note, error ?? ""].filter { !$0.isEmpty }.joined(separator: "\n")
        loginNote.stringValue = text
        loginNote.isHidden = text.isEmpty
        openSettingsButton.isHidden = !d.showOpenSettings
    }

    // MARK: - 動作

    @objc private func changeRoot() {
        guard let path = chooseFolder(startingAt: prefsStore.current.root) else { return }
        prefsStore.setRoot(path)
        reload()
        window?.makeKeyAndOrderFront(nil)
    }

    /// 只有使用者點這個勾選框才註冊／取消登入項目
    @objc private func toggleLoginItem(_ sender: NSButton) {
        var failure: String?
        do {
            if sender.state == .on {
                try SMAppService.mainApp.register()
            } else {
                try SMAppService.mainApp.unregister()
            }
        } catch {
            failure = "設定失敗：\(error.localizedDescription)"
            Logger(path: home.appendingPathComponent("record.log").path, append: true)
                .line("\(isoNow()) 登入項目\(failure ?? "")")
        }
        reloadLoginItem(error: failure)
    }

    @objc private func openLoginItemsSettings() {
        SMAppService.openSystemSettingsLoginItems()
    }

    @objc private func toggleAutoPrep(_ sender: NSButton) {
        let on = sender.state == .on
        prefsStore.update { $0.autoPrep = on }
    }

    @objc private func toggleTimer(_ sender: NSButton) {
        let on = sender.state == .on
        updateSettings { $0.showTimer = on }
    }

    @objc private func changeHUDMode(_ sender: NSSegmentedControl) {
        let i = sender.selectedSegment
        guard HUDMode.allCases.indices.contains(i) else { return }
        updateSettings { $0.hudMode = HUDMode.allCases[i] }
    }

    @objc private func changeHUDPosition(_ sender: NSSegmentedControl) {
        let left = sender.selectedSegment == 1
        updateSettings { $0.hudPosition = left ? "left" : "right" }
    }

    @objc private func toggleTimeSensitive(_ sender: NSButton) {
        let on = sender.state == .on
        updateSettings { $0.timeSensitiveAlerts = on }
    }

    @objc private func toggleMeetingDetect(_ sender: NSButton) {
        let on = sender.state == .on
        updateSettings { $0.meetingDetect = on }
    }

    @objc private func openNotificationSettings() {
        PermissionProbe.openSettings(.notifications)
    }

    @objc private func openPermissionSettings(_ sender: NSButton) {
        guard let raw = sender.identifier?.rawValue, let p = AppPermission(rawValue: raw) else { return }
        PermissionProbe.openSettings(p)
    }

    @objc private func rerunOnboarding() {
        onRerunOnboarding()
    }
}

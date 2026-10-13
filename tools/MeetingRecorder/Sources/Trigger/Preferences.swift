// Trigger/Preferences.swift —— 偏好設定視窗（spec §4.22.4、§4.22.5；HIG settings window 慣例）
// 不可縮放、只有一個；改動立即寫入，沒有「確定」按鈕。
// 登入項目（SMAppService）只在這個檔處理，而且只在使用者點勾選框時註冊／取消；任何自動流程都不註冊。
import AppKit
import ServiceManagement

/// app 沒有 main menu（LSUIElement），標準的 ⌘W 與 Esc 不會自動接到視窗上：自己處理（設計審查 R2 SF-2）。
/// ⌘W 的 W 鍵實體鍵碼（Carbon kVK_ANSI_W），與鍵盤配置、輸入法無關。
let preferencesCloseKeyCode: UInt16 = 13

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

final class PreferencesWindowController: NSWindowController {
    private let home: URL
    private let prefsStore: MenuBarPrefsStore
    private let failedHotKeyIDs: Set<UInt32>
    private let rootLabel = NSTextField(labelWithString: "")
    private let loginCheckbox = NSButton(checkboxWithTitle: "登入時自動開啟", target: nil, action: nil)
    private let loginNote = NSTextField(wrappingLabelWithString: "")
    private let openSettingsButton = NSButton(title: "打開系統設定的登入項目", target: nil, action: nil)
    private let autoPrepCheckbox = NSButton(checkboxWithTitle: "停止後自動跑前處理", target: nil, action: nil)

    init(home: URL, prefsStore: MenuBarPrefsStore, failedHotKeyIDs: Set<UInt32>) {
        self.home = home
        self.prefsStore = prefsStore
        self.failedHotKeyIDs = failedHotKeyIDs
        let window = PreferencesWindow(contentRect: NSRect(x: 0, y: 0, width: 480, height: 300),
                              styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "MeetingRecorder 設定"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        build()
    }

    required init?(coder: NSCoder) { nil }

    /// 已開就帶到前面，不開第二個
    func present() {
        reload()
        if window?.isVisible != true { window?.center() }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    private func sectionLabel(_ s: String) -> NSTextField {
        let l = NSTextField(labelWithString: s)
        l.alignment = .right
        return l
    }

    private func note(_ s: String) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: s)
        l.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        l.textColor = .secondaryLabelColor
        l.preferredMaxLayoutWidth = 320
        return l
    }

    private func column(_ views: [NSView], spacing: CGFloat = 6) -> NSStackView {
        let s = NSStackView(views: views)
        s.orientation = .vertical
        s.alignment = .leading
        s.spacing = spacing
        return s
    }

    private func build() {
        // 預設存檔位置與「更改…」
        rootLabel.lineBreakMode = .byTruncatingMiddle
        rootLabel.preferredMaxLayoutWidth = 320
        let change = NSButton(title: "更改…", target: self, action: #selector(changeRoot))
        let rootRow = column([rootLabel, change])

        // 四組快捷鍵（唯讀；註冊失敗的那組標出來）
        let names = ["start": "開始錄製（用上次的設定）", "mute": "麥克風靜音／取消靜音", "pause": "暫停／繼續錄製",
                     "mark": "加標記"]
        let keyRows: [NSView] = r2HotKeys.map { spec in
            let failed = failedHotKeyIDs.contains(spec.id)
            let text = "\(spec.display)　\(names[spec.action] ?? spec.action)" + (failed ? "（註冊失敗，請改用選單）" : "")
            let l = NSTextField(labelWithString: text)
            l.font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
            if failed { l.textColor = .systemRed }
            return l
        }
        let keys = column(keyRows, spacing: 4)

        // 登入時自動開啟
        loginCheckbox.target = self
        loginCheckbox.action = #selector(toggleLoginItem(_:))
        loginNote.font = NSFont.systemFont(ofSize: NSFont.smallSystemFontSize)
        loginNote.textColor = .secondaryLabelColor
        loginNote.preferredMaxLayoutWidth = 320
        openSettingsButton.target = self
        openSettingsButton.action = #selector(openLoginItemsSettings)
        let login = column([loginCheckbox, loginNote, openSettingsButton])

        // 停止後自動跑前處理（預設不勾）
        autoPrepCheckbox.target = self
        autoPrepCheckbox.action = #selector(toggleAutoPrep(_:))
        let prep = column([autoPrepCheckbox,
                           note("錄製收尾成功後，在背景跑 meeting.sh prep（轉錄、投影片 OCR、講者分離），輸出寫到 autoprep.log")])

        let grid = NSGridView(views: [
            [sectionLabel("預設存檔位置："), rootRow],
            [sectionLabel("快捷鍵："), keys],
            [sectionLabel("登入："), login],
            [sectionLabel("錄完之後："), prep],
        ])
        grid.rowSpacing = 18
        grid.columnSpacing = 10
        grid.column(at: 0).xPlacement = .trailing
        for r in 0..<grid.numberOfRows { grid.row(at: r).yPlacement = .top }
        grid.translatesAutoresizingMaskIntoConstraints = false

        let content = NSView()
        content.addSubview(grid)
        NSLayoutConstraint.activate([
            grid.topAnchor.constraint(equalTo: content.topAnchor, constant: 20),
            grid.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -20),
            grid.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 20),
            grid.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -20),
        ])
        window?.contentView = content
    }

    private func reload() {
        let prefs = prefsStore.current
        let root = (prefs.root?.isEmpty == false ? prefs.root : nil)
            ?? RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))?.root
        rootLabel.stringValue = root.map { ($0 as NSString).abbreviatingWithTildeInPath }
            ?? "還沒有設定：請先在終端機跑一次 meeting record，或按「更改…」"
        rootLabel.toolTip = root
        autoPrepCheckbox.state = prefs.autoPrep ? .on : .off
        reloadLoginItem()
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
}

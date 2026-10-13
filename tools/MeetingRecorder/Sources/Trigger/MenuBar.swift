// Trigger/MenuBar.swift —— menu bar 常駐實例（design §8、§8.2；spec §3.4.1、§4.11.2、§4.11.3、§4.11.5–4.11.10）
// 只做 AppKit 接線：每秒讀 record.status.json 與 kill -0，交給 Core 的 menuBarModel 算圖示、狀態列與選單可用性。
// menu bar 實例自己不擷取；「開始錄製」＝以 open -n -a 自己帶 quick-start；「停止錄製」＝ SIGTERM 給錄製實例。
import AppKit
import Carbon

final class MenuBarController: NSObject, NSMenuDelegate {
    private let home: URL
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    private let menu = NSMenu()
    private let statusLine = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    private let startItem = NSMenuItem(title: "開始錄製（用上次的設定）", action: #selector(startRecording), keyEquivalent: "r")
    private let detailItem = NSMenuItem(title: "複製完整訊息與補救指令", action: #selector(copyDetail), keyEquivalent: "")
    private let stopItem = NSMenuItem(title: "停止錄製", action: #selector(stopRecording), keyEquivalent: "")
    private let openItem = NSMenuItem(title: "打開場次資料夾", action: #selector(openSession), keyEquivalent: "")
    private let quitItem = NSMenuItem(title: "結束 MeetingRecorder 選單", action: #selector(quitMenu), keyEquivalent: "q")
    private var timer: Timer?
    private var hotKey: HotKey?
    private var model = menuBarModel(status: nil, pidAlive: false, now: Date())
    private var status: RecordStatus?
    private var stopRequestedRunId: String?
    /// 上次真的送出 quick-start 的時間：選單快速鍵與 Carbon hot key 可能被同一次按鍵各觸發一次，
    /// 2 秒內的重複呼叫忽略，一次按鍵只開一場（spec §4.11.6）。
    private var lastStartAt: Date?

    init(home: URL) {
        self.home = home
        super.init()
    }

    private var statusURL: URL { home.appendingPathComponent("record.status.json") }
    private var pidURL: URL { home.appendingPathComponent("record.pid") }
    private var logURL: URL { home.appendingPathComponent("record.log") }

    func setup() {
        menu.autoenablesItems = false     // 當下不能用的項目灰掉而不是隱藏（spec §4.11.6）
        statusLine.isEnabled = false
        // 選單上顯示 ⌃⌥⌘R（與下方 Carbon hot key 同一組，spec §4.11.6）
        startItem.keyEquivalentModifierMask = [.control, .option, .command]
        quitItem.keyEquivalentModifierMask = [.command]
        quitItem.toolTip = "只結束 menu bar，不會停止正在進行的錄製"
        for i in [detailItem, startItem, stopItem, openItem, quitItem] { i.target = self }
        menu.addItem(statusLine)
        menu.addItem(detailItem)
        menu.addItem(.separator())
        menu.addItem(startItem)
        menu.addItem(stopItem)
        menu.addItem(openItem)
        menu.addItem(.separator())
        menu.addItem(quitItem)
        menu.delegate = self              // 開選單時立即 refresh（spec §4.11.9）
        item.menu = menu
        refresh()
        // 加進 .common mode：選單展開時 run loop 在 event tracking mode，只排在 .default 的 timer 不會觸發（spec §4.11.9）
        let t = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.refresh() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
        // ⌃⌥⌘R：開始錄製（等同選單的「開始錄製」）。Carbon hot key，不需要輔助使用授權。
        hotKey = HotKey(keyCode: kVK_ANSI_R, modifiers: controlKey | optionKey | cmdKey) { [weak self] in
            guard let self, self.model.canStart else { return }
            self.startRecording()
        }
        if hotKey == nil {   // 被別的 app 佔用等：menu bar 照常運作，只記一行（spec §4.11.3）
            startItem.keyEquivalent = ""   // 選單上不顯示用不了的 ⌃⌥⌘R（設計審查 N-3）
            Logger(path: logURL.path, append: true)
                .line("\(isoNow()) 快捷鍵 ⌃⌥⌘R 註冊失敗（可能被別的 app 佔用），請改用選單或 Shortcuts 捷徑")
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        refresh()
    }

    private func refresh() {
        var st = readStatus(statusURL)
        let pid = st?.pid ?? readPid(pidURL) ?? 0
        let alive = pidAlive(pid)
        // 點下「停止錄製」後立即顯示「收尾中…」，不等錄製實例寫出 stopping（spec §4.11.7）
        if var s = st, s.runId == stopRequestedRunId, s.phase == .recording {
            s.phase = .stopping
            st = s
        }
        status = st
        let m = menuBarModel(status: st, pidAlive: alive, now: Date())
        model = m
        if let button = item.button {
            let image = NSImage(systemSymbolName: m.symbolName, accessibilityDescription: m.accessibilityText)
            image?.isTemplate = true      // template image：淺色／深色 menu bar 都清楚；三態以形狀區分
            button.image = image
            button.contentTintColor = m.state == .warning ? .systemRed : nil   // 只有告警態加紅色，形狀已能區分
            button.toolTip = m.accessibilityText
            button.setAccessibilityLabel(m.accessibilityText)
        }
        // 狀態列：不可點，但用 labelColor 而非系統灰色；過長截斷，完整內容放 toolTip（spec §4.11.8）
        statusLine.attributedTitle = NSAttributedString(
            string: truncatedStatusTitle(m.statusLine, limit: 40),
            attributes: [.foregroundColor: NSColor.labelColor, .font: NSFont.menuFont(ofSize: 0)])
        statusLine.toolTip = m.statusLine
        // 失敗類的完整訊息（停止原因、補救指令）狀態列放不下：另給一項可複製（設計審查 N-1）
        detailItem.isHidden = m.detailText == m.statusLine
        detailItem.toolTip = m.detailText
        startItem.isEnabled = m.canStart
        stopItem.isEnabled = m.canStop
        openItem.isEnabled = m.canOpenSession
    }

    @objc private func startRecording() {
        guard model.canStart else { return }
        let now = Date()
        if let last = lastStartAt, now.timeIntervalSince(last) < 2 { return }
        lastStartAt = now
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-n", "-a", Bundle.main.bundlePath, "--args", "quick-start", "--home", home.path]
        try? p.run()
    }

    @objc private func copyDetail() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(model.detailText, forType: .string)
    }

    @objc private func stopRecording() {
        guard model.canStop, let st = status else { return }
        let pid = readPid(pidURL) ?? st.pid
        guard pid > 0, kill(pid, SIGTERM) == 0 else { return }
        stopRequestedRunId = st.runId
        refresh()
    }

    @objc private func openSession() {
        guard let s = status?.session, !s.isEmpty else { return }
        var url = URL(fileURLWithPath: s, isDirectory: true)
        while !FileManager.default.fileExists(atPath: url.path), url.path != "/" { url.deleteLastPathComponent() }
        NSWorkspace.shared.open(url)
    }

    /// 只結束 menu bar 實例；錄製是另一個 process，不受影響。
    @objc private func quitMenu() {
        NSApp.terminate(nil)
    }
}

private var menuBarController: MenuBarController?
/// menubar.lock 的 fd：持有到 process 結束，不 close（spec §4.11.10）。
private var menuBarLockFD: Int32 = -1

func runMenuBar(_ args: Args) -> Never {
    let home = recordHome(args)
    // 單一實例：在建立 NSStatusItem 與註冊快捷鍵之前取得鎖（spec §4.11.10）
    switch acquireMenuBarLock(at: home.appendingPathComponent("menubar.lock")) {
    case .acquired(let fd):
        menuBarLockFD = fd
    case .heldByOther:
        Logger(path: home.appendingPathComponent("record.log").path, append: true)
            .line("\(isoNow()) 已有 MeetingRecorder 選單在執行，本實例結束")
        exit(0)
    case .unavailable(let e):
        // 只防重複圖示，不得因此擋住 menu bar：記原因後照常啟動
        Logger(path: home.appendingPathComponent("record.log").path, append: true)
            .line("\(isoNow()) menubar.lock 無法使用（errno \(e)：\(String(cString: strerror(e)))），照常啟動選單")
    }
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let c = MenuBarController(home: home)
    menuBarController = c
    c.setup()
    app.run()
    exit(0)
}

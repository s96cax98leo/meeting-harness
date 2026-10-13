// Trigger/MenuBar.swift —— menu bar 常駐實例（design §8、§8.2；spec §3.4.1、§4.11、§4.20、§4.21、§4.23）
// 只做 AppKit 接線：每秒讀 record.status.json 與 kill -0，交給 Core 的 menuBarModel 算圖示、計時、狀態列與選單可用性。
// menu bar 實例自己不擷取、不呼叫 SCK：
//   「開始錄製」「錄這個視窗」＝以 open -n -a 自己帶 quick-start；視窗清單＝以 open -n -a 自己帶 windows --json；
//   「停止錄製」＝ SIGTERM 給錄製實例；暫停／麥克風靜音／加標記＝ requestControl 寫控制檔後送 SIGUSR1（spec §4.20.8）。
// 登入項目只在偏好設定視窗的勾選框處理（Trigger/Preferences.swift），這裡任何流程都不註冊。
import AppKit
import Carbon
import UserNotifications

final class MenuBarController: NSObject, NSMenuDelegate, UNUserNotificationCenterDelegate {
    private let home: URL
    private let prefsStore: MenuBarPrefsStore
    private let autoPrep: AutoPrepRunner
    // 寬度隨內容變：錄製中在圖示右側顯示計時（spec §4.20.4）
    private let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    private let menu = NSMenu()
    private let statusLine = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    private let levelItem = NSMenuItem(title: "", action: nil, keyEquivalent: "")
    private let detailItem = NSMenuItem(title: "複製完整訊息與補救指令", action: #selector(copyDetail), keyEquivalent: "")
    private let startItem = NSMenuItem(title: "開始錄製（用上次的設定）", action: #selector(startRecording), keyEquivalent: "r")
    private let windowsItem = NSMenuItem(title: "錄這個視窗", action: nil, keyEquivalent: "")
    private let windowsMenu = NSMenu()
    private let saveToItem = NSMenuItem(title: "存到", action: nil, keyEquivalent: "")
    private let saveToMenu = NSMenu()
    private let pauseItem = NSMenuItem(title: "暫停錄製", action: #selector(togglePause), keyEquivalent: "p")
    private let muteItem = NSMenuItem(title: "麥克風靜音", action: #selector(toggleMute), keyEquivalent: "m")
    private let markItem = NSMenuItem(title: "加標記", action: #selector(addMarker), keyEquivalent: "b")
    private let stopItem = NSMenuItem(title: "停止錄製", action: #selector(stopRecording), keyEquivalent: "")
    private let openItem = NSMenuItem(title: "打開場次資料夾", action: #selector(openSession), keyEquivalent: "")
    private let lastItem = NSMenuItem(title: "顯示上一場成品", action: #selector(showLastSession), keyEquivalent: "")
    private let prefsItem = NSMenuItem(title: "偏好設定…", action: #selector(openPreferences), keyEquivalent: ",")
    private let quitItem = NSMenuItem(title: "結束 MeetingRecorder 選單", action: #selector(quitMenu), keyEquivalent: "q")
    private var timer: Timer?
    /// r2HotKeys 四組各自的實例（註冊失敗的是 nil）；持有到 process 結束
    private var hotKeys: [HotKey?] = []
    private var failedHotKeyIDs = Set<UInt32>()
    private var model = menuBarModel(status: nil, pidAlive: false, now: Date())
    private var status: RecordStatus?
    private var stopRequestedRunId: String?
    /// 上次真的送出 quick-start 的時間：選單快速鍵與 Carbon hot key 可能被同一次按鍵各觸發一次，
    /// 2 秒內的重複呼叫忽略，一次按鍵只開一場（spec §4.11.6）。
    private var lastStartAt: Date?
    /// 暫停、麥克風靜音、加標記的去抖（同一動作 1 秒內只算一次；spec §4.20.7）
    private var debouncer = TriggerDebouncer(interval: 1.0)
    /// 本次執行期間看過處於進行中（recording／stopping／finalizing）的 runId（spec §4.23.3）
    private var seenInProgress = Set<String>()
    private var completionPosted = Set<String>()
    /// 已檢查過「圖示被瀏海擋住」的 runId（每場只提醒一次，§6 第 106 條）
    private var obscureChecked = Set<String>()
    /// 「錄這個視窗」子選單讀清單用的輪詢
    private var windowsTimer: Timer?
    private var preferences: PreferencesWindowController?

    init(home: URL) {
        self.home = home
        prefsStore = MenuBarPrefsStore(home: home)
        autoPrep = AutoPrepRunner(home: home)
        super.init()
    }

    private var statusURL: URL { home.appendingPathComponent("record.status.json") }
    private var pidURL: URL { home.appendingPathComponent("record.pid") }
    private var logURL: URL { home.appendingPathComponent("record.log") }
    private var defaultsURL: URL { home.appendingPathComponent("record.defaults.json") }

    func setup() {
        menu.autoenablesItems = false     // 當下不能用的項目灰掉而不是隱藏（spec §4.11.6、§4.20.6）
        windowsMenu.autoenablesItems = false
        saveToMenu.autoenablesItems = false
        statusLine.isEnabled = false
        levelItem.isEnabled = false
        // 選單上顯示的快捷鍵與下方 Carbon hot key 同一組（spec §4.20.5、§4.20.6）
        startItem.keyEquivalentModifierMask = [.control, .option, .command]
        pauseItem.keyEquivalentModifierMask = [.control, .option, .command]
        muteItem.keyEquivalentModifierMask = [.control, .option, .command]
        markItem.keyEquivalentModifierMask = [.control, .option, .command]
        prefsItem.keyEquivalentModifierMask = [.command]
        quitItem.keyEquivalentModifierMask = [.command]
        quitItem.toolTip = "只結束 menu bar，不會停止正在進行的錄製"
        for i in [detailItem, startItem, pauseItem, muteItem, markItem, stopItem, openItem, lastItem, prefsItem, quitItem] {
            i.target = self
        }
        windowsItem.submenu = windowsMenu
        saveToItem.submenu = saveToMenu
        windowsMenu.delegate = self
        saveToMenu.delegate = self
        menu.addItem(statusLine)
        menu.addItem(levelItem)
        menu.addItem(detailItem)
        menu.addItem(.separator())
        menu.addItem(startItem)
        menu.addItem(windowsItem)
        menu.addItem(saveToItem)
        menu.addItem(.separator())
        menu.addItem(pauseItem)
        menu.addItem(muteItem)
        menu.addItem(markItem)
        menu.addItem(stopItem)
        menu.addItem(.separator())
        menu.addItem(openItem)
        menu.addItem(lastItem)
        menu.addItem(.separator())
        menu.addItem(prefsItem)
        menu.addItem(quitItem)
        menu.delegate = self              // 開選單時立即 refresh（spec §4.11.9）
        item.menu = menu
        setupNotifications()
        refresh()
        // 加進 .common mode：選單展開時 run loop 在 event tracking mode，只排在 .default 的 timer 不會觸發（spec §4.11.9）
        let t = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.refresh() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
        // 四組快捷鍵（Carbon hot key，不需要輔助使用授權）；任一組失敗不影響其他組與選單（spec §4.20.5）
        for spec in r2HotKeys {
            guard let code = hotKeyCode(spec.key) else { continue }
            let action = spec.action
            let hotKey = HotKey(keyCode: code, modifiers: controlKey | optionKey | cmdKey, id: spec.id) { [weak self] in
                self?.hotKeyPressed(action)
            }
            hotKeys.append(hotKey)
            if hotKey == nil {   // 被別的 app 佔用等：選單上不顯示用不了的快捷鍵（設計審查 N-3），只記一行
                switch spec.action {
                case "start": startItem.keyEquivalent = ""
                case "mute": muteItem.keyEquivalent = ""
                case "pause": pauseItem.keyEquivalent = ""
                default: markItem.keyEquivalent = ""
                }
                failedHotKeyIDs.insert(spec.id)
                Logger(path: logURL.path, append: true)
                    .line("\(isoNow()) 快捷鍵 \(spec.display) 註冊失敗（可能被別的 app 佔用），請改用選單或 Shortcuts 捷徑")
            }
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        if menu === windowsMenu {
            loadWindowList()
        } else if menu === saveToMenu {
            rebuildSaveToMenu()
        } else {
            refresh()
        }
    }

    func menuDidClose(_ menu: NSMenu) {
        if menu === windowsMenu {
            windowsTimer?.invalidate()
            windowsTimer = nil
        }
    }

    private func refresh() {
        let raw = readStatus(statusURL)
        var st = raw
        let pid = st?.pid ?? readPid(pidURL) ?? 0
        let alive = pidAlive(pid)
        trackCompletion(raw)
        checkObscured(raw)
        // 點下「停止錄製」後立即顯示「收尾中…」，不等錄製實例寫出 stopping（spec §4.11.7）
        if var s = st, s.runId == stopRequestedRunId, s.phase == .recording {
            s.phase = .stopping
            st = s
        }
        status = st
        let m = menuBarModel(status: st, pidAlive: alive, now: Date())
        model = m
        updateButton(m)
        // 狀態列：不可點，但用 labelColor 而非系統灰色；過長截斷，完整內容放 toolTip（spec §4.11.8）
        statusLine.attributedTitle = NSAttributedString(
            string: truncatedStatusTitle(m.statusLine, limit: 40),
            attributes: [.foregroundColor: NSColor.labelColor, .font: NSFont.menuFont(ofSize: 0)])
        statusLine.toolTip = m.statusLine
        // 收音指示列：只在錄製中（levelLine 非空）顯示（spec §4.20.6）
        levelItem.isHidden = m.levelLine.isEmpty
        levelItem.attributedTitle = NSAttributedString(
            string: m.levelLine,
            attributes: [.foregroundColor: NSColor.labelColor, .font: NSFont.menuFont(ofSize: 0)])
        // 失敗類的完整訊息（停止原因、補救指令）狀態列放不下：另給一項可複製（設計審查 N-1）
        detailItem.isHidden = m.detailText == m.statusLine
        detailItem.toolTip = m.detailText
        let ready = startReady()
        startItem.isEnabled = m.canStart && ready
        windowsItem.isEnabled = m.canStart && ready
        saveToItem.isEnabled = ready
        let root = effectiveRoot()
        saveToItem.title = root.map { "存到：\(($0 as NSString).lastPathComponent)" } ?? "存到"
        saveToItem.toolTip = root
        pauseItem.title = m.paused ? "繼續錄製" : "暫停錄製"
        pauseItem.isEnabled = m.canControl
        muteItem.state = m.micMuted ? .on : .off
        muteItem.isEnabled = m.canControl
        markItem.isEnabled = m.canControl
        stopItem.isEnabled = m.canStop
        openItem.isEnabled = m.canOpenSession
        lastItem.isEnabled = lastSessionPath() != nil
    }

    /// 圖示＋計時（spec §4.20.4）：圖示一律 template image；錄製中與告警態染紅；計時用等寬數字，每秒更新寬度不抖動。
    private func updateButton(_ m: MenuBarModel) {
        guard let button = item.button else { return }
        // 錄製中與告警態用紅色符號（paletteColors、非 template）；其他狀態用 template image，淺色／深色 menu bar 都清楚。
        // t7（spec §6 第 107 條）：macOS 26 選單列上 template image＋button 染色會畫成透明，不得改回那種寫法。
        let red = m.state == .recording || m.state == .warning
        var image = NSImage(systemSymbolName: m.symbolName, accessibilityDescription: m.accessibilityText)
        if red {
            image = image?.withSymbolConfiguration(NSImage.SymbolConfiguration(paletteColors: [.systemRed]))
            image?.isTemplate = false
        } else {
            image?.isTemplate = true
        }
        button.image = image
        if m.timerText.isEmpty {
            button.imagePosition = .imageOnly
            button.attributedTitle = NSAttributedString(string: "")
        } else {
            button.imagePosition = .imageLeading
            let font = NSFont.monospacedDigitSystemFont(ofSize: NSFont.systemFontSize, weight: .regular)
            let title = NSMutableAttributedString()
            if m.micMuted, let mic = NSImage(systemSymbolName: "mic.slash", accessibilityDescription: nil) {
                mic.isTemplate = true
                let attachment = NSTextAttachment()
                attachment.image = mic
                title.append(NSAttributedString(string: " ", attributes: [.font: font]))
                title.append(NSAttributedString(attachment: attachment))
            }
            title.append(NSAttributedString(string: " " + m.timerText, attributes: [.font: font]))
            button.attributedTitle = title
        }
        button.toolTip = m.accessibilityText
        button.setAccessibilityLabel(m.accessibilityText)
    }

    // MARK: - 開始錄製

    /// 開始與「錄這個視窗」都要 record.defaults.json 讀得到、有 harness（spec §4.20.6）
    private func startReady() -> Bool {
        RecordDefaults.load(defaultsURL)?.harness != nil
    }

    private func effectiveRoot() -> String? {
        if let r = prefsStore.current.root, !r.isEmpty { return r }
        return RecordDefaults.load(defaultsURL)?.root
    }

    /// 2 秒內的重複開錄忽略；回 true＝這次要送
    private func acceptStart() -> Bool {
        let now = Date()
        if let last = lastStartAt, now.timeIntervalSince(last) < 2 { return false }
        lastStartAt = now
        return true
    }

    private func openSelf(_ args: [String]) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        p.arguments = ["-n", "-a", Bundle.main.bundlePath, "--args"] + args
        try? p.run()
    }

    @objc private func startRecording() {
        guard model.canStart, startReady(), acceptStart() else { return }
        openSelf(["quick-start", "--home", home.path])
    }

    private func hotKeyPressed(_ action: String) {
        switch action {
        case "start":
            if model.canStart { startRecording() }
        // 快捷鍵按下後一律發通知回饋（t7，§6 第 105 條：圖示被瀏海擋住時看不到任何反應，使用者會一直重按）
        case "mute": sendControl(model.micMuted ? .unmute : .mute, action: "mute", feedback: true)
        case "pause": sendControl(model.paused ? .resume : .pause, action: "pause", feedback: true)
        case "mark": sendControl(.mark, action: "mark", feedback: true)
        default: break
        }
    }

    // MARK: - 錄這個視窗（spec §4.21.4）

    private func placeholder(_ title: String) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        i.isEnabled = false
        return i
    }

    /// 以 open -n -a 自己帶 windows --json 取清單（menu bar 程序本身不呼叫 SCK、不跳 Apple Events 授權框）
    private func loadWindowList() {
        windowsTimer?.invalidate()
        windowsMenu.removeAllItems()
        windowsMenu.addItem(placeholder("讀取視窗清單中…"))
        let out = FileManager.default.temporaryDirectory
            .appendingPathComponent("mh-windows-\(UUID().uuidString).json")
        openSelf(["windows", "--json", "--log", out.path])
        let started = Date()
        let t = Timer(timeInterval: 0.25, repeats: true) { [weak self] t in
            guard let self else { t.invalidate(); return }
            if let data = try? Data(contentsOf: out), !data.isEmpty,
               let rows = try? JSONDecoder().decode([WindowListRow].self, from: data) {
                t.invalidate()
                try? FileManager.default.removeItem(at: out)
                self.showWindowRows(rows)
            } else if Date().timeIntervalSince(started) >= 10 {
                t.invalidate()
                try? FileManager.default.removeItem(at: out)
                self.windowsMenu.removeAllItems()
                self.windowsMenu.addItem(self.placeholder("取不到視窗清單"))
            }
        }
        RunLoop.main.add(t, forMode: .common)
        windowsTimer = t
    }

    private func showWindowRows(_ rows: [WindowListRow]) {
        windowsMenu.removeAllItems()
        guard !rows.isEmpty else {
            windowsMenu.addItem(placeholder("沒有可錄的視窗"))
            return
        }
        for row in rows {   // 順序照 app 輸出（★ 在前）
            let i = NSMenuItem(title: truncatedStatusTitle(row.label, limit: 60), action: #selector(recordWindow(_:)),
                               keyEquivalent: "")
            i.toolTip = row.label
            i.target = self
            i.representedObject = WindowChoice(windowID: row.windowID, bundleID: row.bundleID, title: row.title)
            i.isEnabled = model.canStart
            windowsMenu.addItem(i)
        }
    }

    @objc private func recordWindow(_ sender: NSMenuItem) {
        guard let w = sender.representedObject as? WindowChoice, model.canStart, startReady(), acceptStart() else { return }
        var args = ["quick-start", "--home", home.path, "--window", String(w.windowID),
                    "--window-bundle", w.bundleID, "--window-title", w.title]
        if let r = prefsStore.current.root, !r.isEmpty { args += ["--root", r] }
        openSelf(args)
    }

    // MARK: - 存到（spec §4.21.5）

    private func rebuildSaveToMenu() {
        saveToMenu.removeAllItems()
        let current = effectiveRoot()
        var list: [String] = []
        if let current { list.append(current) }
        for r in prefsStore.current.recentRoots where !list.contains(where: { sameRoot($0, r) }) { list.append(r) }
        for path in list {
            let exists = isDirectoryPath(path)
            let shown = (path as NSString).abbreviatingWithTildeInPath
            let i = NSMenuItem(title: exists ? shown : "\(shown)（找不到）", action: #selector(chooseRoot(_:)),
                               keyEquivalent: "")
            i.target = self
            i.representedObject = path
            i.toolTip = path
            i.state = (current.map { sameRoot($0, path) } ?? false) ? .on : .off
            i.isEnabled = exists
            saveToMenu.addItem(i)
        }
        if !list.isEmpty { saveToMenu.addItem(.separator()) }
        let pick = NSMenuItem(title: "選擇資料夾…", action: #selector(pickRootFolder), keyEquivalent: "")
        pick.target = self
        saveToMenu.addItem(pick)
    }

    @objc private func chooseRoot(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        prefsStore.setRoot(path)
        refresh()
    }

    @objc private func pickRootFolder() {
        guard let path = chooseFolder(startingAt: effectiveRoot()) else { return }
        prefsStore.setRoot(path)
        refresh()
    }

    // MARK: - 暫停／麥克風靜音／加標記（spec §4.20.7、§4.20.8）

    /// 暫停與靜音寫「目標狀態」（由目前的 model 算出，不讀控制檔來切換）
    @objc private func togglePause() {
        sendControl(model.paused ? .resume : .pause, action: "pause")
    }

    @objc private func toggleMute() {
        sendControl(model.micMuted ? .unmute : .mute, action: "mute")
    }

    @objc private func addMarker() {
        sendControl(.mark, action: "mark")
    }

    private func sendControl(_ cmd: ControlCommand, action: String, feedback: Bool = false) {
        guard debouncer.accept(action, at: ProcessInfo.processInfo.systemUptime) else { return }
        let recordPid = readPid(pidURL)
        let availability = controlAvailability(status: readStatus(statusURL), recordPid: recordPid,
                                               pidAlive: recordPid.map(pidAlive) ?? false)
        switch availability {
        case .unavailable(let message):
            notify(title: "MeetingRecorder 沒辦法操作錄製", body: message)
        case .ready(let pid, let runId):
            let written: RecordControl
            do {
                written = try requestControl(cmd, home: home, runId: runId)
            } catch {
                notify(title: "MeetingRecorder 沒辦法操作錄製", body: "寫控制檔失敗：\(error.localizedDescription)")
                return
            }
            if kill(pid, SIGUSR1) != 0 {
                notify(title: "MeetingRecorder 沒辦法操作錄製", body: "通知錄製實例失敗（errno \(errno)）")
            } else if feedback {
                notify(title: "MeetingRecorder", body: controlFeedback(cmd, markerSeq: written.markerSeq))
            }
        }
    }

    /// 通知在背景送（Notifier.post 最多等 3 秒，不得卡住主執行緒）
    private func notify(title: String, body: String) {
        let log = Logger(path: logURL.path, append: true)
        DispatchQueue.global(qos: .utility).async { Notifier.post(title: title, body: body, log: log) }
    }

    // MARK: - 停止、打開場次、上一場成品

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
        NSWorkspace.shared.open(nearestExistingDirectory(s))
    }

    /// 狀態檔是收尾完成的場次時優先（最新），否則用 menubar.prefs.json 的 lastSession（spec §4.23.4）
    private func lastSessionPath() -> String? {
        if let st = status, st.phase == .done, !st.session.isEmpty { return st.session }
        if let s = prefsStore.current.lastSession, !s.isEmpty { return s }
        return nil
    }

    @objc private func showLastSession() {
        guard let s = lastSessionPath() else { return }
        revealSessionProduct(s)
    }

    @objc private func openPreferences() {
        let p = preferences ?? PreferencesWindowController(home: home, prefsStore: prefsStore,
                                                           failedHotKeyIDs: failedHotKeyIDs)
        preferences = p
        p.present()
    }

    /// 只結束 menu bar 實例；錄製是另一個 process，不受影響。
    @objc private func quitMenu() {
        NSApp.terminate(nil)
    }

    // MARK: - 完成通知與自動前處理（spec §4.23）

    private func setupNotifications() {
        guard Bundle.main.bundleIdentifier != nil else { return }   // 不在 .app 裡就不碰通知中心
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        let reveal = UNNotificationAction(identifier: revealActionID, title: "在 Finder 顯示", options: [.foreground])
        center.setNotificationCategories([
            UNNotificationCategory(identifier: completionCategoryID, actions: [reveal], intentIdentifiers: [], options: []),
        ])
    }

    /// 錄製中第一次 refresh（計時已顯示、寬度已定）時看圖示是否被瀏海擋住或被系統藏起來；是就發一次通知（§6 第 106 條）
    private func checkObscured(_ st: RecordStatus?) {
        guard let st, st.phase == .recording, !obscureChecked.contains(st.runId) else { return }
        obscureChecked.insert(st.runId)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in
            guard let self, let window = self.item.button?.window else { return }
            let frame = window.frame
            let screen = window.screen ?? NSScreen.main
            var notchMinX: CGFloat? = nil, notchMaxX: CGFloat? = nil
            if let sc = screen, let l = sc.auxiliaryTopLeftArea, let r = sc.auxiliaryTopRightArea {
                notchMinX = sc.frame.minX + l.maxX
                notchMaxX = sc.frame.minX + r.minX
            }
            let visible = window.occlusionState.contains(.visible)
            if statusItemObscured(itemMinX: frame.minX, itemMaxX: frame.maxX, visible: visible,
                                  notchMinX: notchMinX, notchMaxX: notchMaxX) {
                Logger(path: self.logURL.path, append: true)
                    .line("\(isoNow()) 選單列圖示看不到（x \(Int(frame.minX))–\(Int(frame.maxX))、visible \(visible)）：已提醒使用者")
                self.notify(title: "MeetingRecorder 正在錄製，但選單列圖示被擋住了",
                            body: "可按住 ⌘ 把右上角其他圖示拖走騰出空間；暫停 ⌃⌥⌘P、靜音 ⌃⌥⌘M、標記 ⌃⌥⌘B 按下後都會跳通知")
            }
        }
    }

    private func trackCompletion(_ st: RecordStatus?) {
        guard let st else { return }
        switch st.phase {
        case .recording, .stopping, .finalizing:
            seenInProgress.insert(st.runId)
        case .done where st.code == 0 && seenInProgress.contains(st.runId) && !completionPosted.contains(st.runId):
            completionPosted.insert(st.runId)
            if !st.session.isEmpty { prefsStore.update { $0.lastSession = st.session } }
            postCompletion(st)
        default:
            break
        }
        let prefs = prefsStore.current
        if let session = shouldAutoPrep(autoPrep: prefs.autoPrep, status: st, seenInProgressRunIds: seenInProgress,
                                        lastAutoPrepRunId: prefs.lastAutoPrepRunId) {
            prefsStore.update { $0.lastAutoPrepRunId = st.runId }   // 啟動前先記，同一場不會跑兩次
            autoPrep.enqueue(session)
        }
    }

    /// 與錄製實例的完成通知同一個識別碼（取代它），另加 category 與「在 Finder 顯示」動作（spec §4.23.3）
    private func postCompletion(_ st: RecordStatus) {
        guard Bundle.main.bundleIdentifier != nil else { return }
        let content = UNMutableNotificationContent()
        content.title = "會議錄製完成"
        content.body = st.session
        content.categoryIdentifier = completionCategoryID
        content.userInfo = ["session": st.session]
        let req = UNNotificationRequest(identifier: completionNotificationID(runId: st.runId), content: content,
                                        trigger: nil)
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            center.add(req) { _ in }
        }
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, didReceive response: UNNotificationResponse,
                                withCompletionHandler completionHandler: @escaping () -> Void) {
        if response.actionIdentifier == revealActionID,
           let s = response.notification.request.content.userInfo["session"] as? String, !s.isEmpty {
            DispatchQueue.main.async { revealSessionProduct(s) }
        }
        completionHandler()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list])
    }
}

/// 「錄這個視窗」每一列帶的視窗資訊
private final class WindowChoice: NSObject {
    let windowID: UInt32
    let bundleID: String
    let title: String
    init(windowID: UInt32, bundleID: String, title: String) {
        self.windowID = windowID
        self.bundleID = bundleID
        self.title = title
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

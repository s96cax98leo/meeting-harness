// Trigger/MenuBar.swift —— menu bar 常駐實例（design §8、§8.2；spec §3.4.1、§4.11、§4.20、§4.21、§4.23）
// 只做 AppKit 接線：每秒讀 record.status.json 與 kill -0，交給 Core 的 menuBarModel 算圖示、計時、狀態列與選單可用性。
// R3（spec §4.38、§4.39、§4.27.4）：選單列＝U1-C 錄製膠囊（8 種外觀自繪，顏色一律取自 Core 的 menuBarCapsuleStyle）；
//   toolTip／VoiceOver＝menuBarAccessibilityLabel；停止前先 stopTargetDecision；新告警發分級通知（notificationPolicy）。
// R3（spec §4.40）：錄製小窗（Trigger/HUD.swift）依 hudVisible 顯示；圖示是否被擋住每 obscuredCheckSeconds 檢查一次
//   交給 obscuredAction；快捷鍵回饋依 feedbackRoute。
// menu bar 實例自己不擷取、不呼叫 SCK：
//   「開始錄製」「錄這個視窗」＝以 open -n -a 自己帶 quick-start；視窗清單＝以 open -n -a 自己帶 windows --json；
//   「停止錄製」＝ stopTargetDecision 確認後 SIGTERM 給錄製實例；暫停／麥克風靜音／加標記＝ requestControl 寫控制檔後送 SIGUSR1（spec §4.20.8）。
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
    /// 選單列圖示是否被瀏海擋住或被系統藏起來（錄製中每 obscuredCheckSeconds 檢查一次；nil＝這次錄製還沒檢查過；
    /// spec §4.40.3、§6 第 121 條）
    private var iconObscured: Bool?
    /// 已排過開錄後第一次檢查的 runId（計時顯示、寬度定下來後再看）
    private var obscureFirstCheckRunId: String?
    private var obscuredTimer: Timer?
    /// 錄製小窗 U2-C（Trigger/HUD.swift）；何時顯示由 hudVisible 決定
    private lazy var hud: HUDController = {
        let h = HUDController(home: home)
        h.actions = self
        return h
    }()
    /// 「錄這個視窗」子選單讀清單用的輪詢
    private var windowsTimer: Timer?
    private var preferences: PreferencesWindowController?
    /// 新告警通知（spec §4.39.2、§4.39.3）：上一次看到的 warnings 與它屬於哪一場
    private var alertRunId: String?
    private var seenWarnings: [RecordWarning] = []
    /// 選單列深淺色切換時立即重畫膠囊（不等下一秒的 refresh）
    private var appearanceObservation: NSKeyValueObservation?

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
        // 使用者 ⌘ 拖動圖示後，重開仍在同一個位置（spec §4.38.4）
        item.autosaveName = "MeetingRecorderStatusItem"
        // 深色／淺色、增加對比、減少透明度改變時重畫膠囊（spec §4.38.3）
        appearanceObservation = item.button?.observe(\.effectiveAppearance, options: [.new]) { [weak self] _, _ in
            DispatchQueue.main.async { self?.redrawButton() }
        }
        NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.redrawButton() }
        setupNotifications()
        refresh()
        // 加進 .common mode：選單展開時 run loop 在 event tracking mode，只排在 .default 的 timer 不會觸發（spec §4.11.9）
        let t = Timer(timeInterval: 1, repeats: true) { [weak self] _ in self?.refresh() }
        RunLoop.main.add(t, forMode: .common)
        timer = t
        // 圖示是否被擋住：錄製中持續檢查，結果驅動 auto 模式的 HUD 與快捷鍵回饋路徑（spec §4.40.3、§6 第 121 條）
        let o = Timer(timeInterval: obscuredCheckSeconds, repeats: true) { [weak self] _ in self?.checkObscured() }
        RunLoop.main.add(o, forMode: .common)
        obscuredTimer = o
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
        scheduleFirstObscuredCheck(raw)
        // 點下「停止錄製」後立即顯示「收尾中…」，不等錄製實例寫出 stopping（spec §4.11.7）
        if var s = st, s.runId == stopRequestedRunId, s.phase == .recording {
            s.phase = .stopping
            st = s
        }
        status = st
        let m = menuBarModel(status: st, pidAlive: alive, now: Date())
        model = m
        updateButton(m)
        if !hudEligible(m) { iconObscured = nil }   // 這次錄製結束：下一場重新判斷
        updateHUD(m)
        notifyNewAlerts(raw)
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

    /// 選單列圖示（spec §4.38.3）：待機＝SF Symbol record.circle（template）；其他 7 種＝自繪的錄製膠囊（非 template），
    /// 形狀、符號、字與顏色一律取自 menuBarCapsuleStyle。toolTip 與 VoiceOver＝menuBarAccessibilityLabel（§4.38.7），
    /// 不含場次名（toolTip 會出現在螢幕上，使用者可能正在分享整個螢幕；§6 第 135 條）。
    private func updateButton(_ m: MenuBarModel) {
        guard let button = item.button else { return }
        let label = menuBarAccessibilityLabel(appearance: m.appearance, alertBadge: m.alertBadge, spoken: m.spokenDuration,
                                              alertText: latestAlertMessage(status), status: m.statusLine)
        let dark = isDarkAppearance(button.effectiveAppearance)
        let workspace = NSWorkspace.shared
        let settings = loadMenuBarSettings(home: home)
        let image: NSImage?
        if let capsule = capsuleImage(m, dark: dark,
                                      increaseContrast: workspace.accessibilityDisplayShouldIncreaseContrast,
                                      reduceTransparency: workspace.accessibilityDisplayShouldReduceTransparency,
                                      showTimer: settings.showTimer) {
            image = capsule
        } else {
            // 待機的 MenuBarState 是 .idle，symbolName 就是 "record.circle"（R2 的對映保留，§6 第 128、129 條）
            let symbol = m.state == .idle ? m.symbolName : "record.circle"
            let idle = NSImage(systemSymbolName: symbol, accessibilityDescription: label)
            idle?.isTemplate = true     // 待機跟系統選單列上色（淺色、深色、增加對比都由系統處理）
            image = idle
        }
        image?.accessibilityDescription = label
        button.image = image
        button.imagePosition = .imageOnly
        button.attributedTitle = NSAttributedString(string: "")
        button.toolTip = label
        button.setAccessibilityLabel(label)
    }

    /// 只重畫圖示（外觀或輔助使用設定改變時）
    private func redrawButton() {
        updateButton(model)
    }

    /// 告警類中 t 最大的一筆的訊息（menuBarAccessibilityLabel 的 alertText；§4.38.7）
    private func latestAlertMessage(_ st: RecordStatus?) -> String? {
        st?.warnings.filter { $0.kind.isAlert }.max(by: { $0.t < $1.t })?.message
    }

    /// 錄製膠囊（U1-C；spec §4.38.3、§4.38.5、design-r3/README.md §2）。待機回 nil（改用 template symbol）。
    /// dark＝status item 按鈕的 effectiveAppearance；increaseContrast＝系統「增加對比」（深一階的底色由 Core 決定）；
    /// reduceTransparency＝系統「減少透明度」：外框膠囊（準備中、需處理）沒有底色，這時墊上選單列的參考底
    /// （menuBarDark／menuBarLight），字的對比與 §4.38.6 的計算一致；實心膠囊本來就不透明。
    private func capsuleImage(_ m: MenuBarModel, dark: Bool, increaseContrast: Bool, reduceTransparency: Bool,
                              showTimer: Bool) -> NSImage? {
        let style = menuBarCapsuleStyle(m.appearance, alertBadge: m.alertBadge, dark: dark,
                                        increaseContrast: increaseContrast)
        guard style.shape != .templateSymbol else { return nil }
        let metric = DarkroomMetric.self
        let height = CGFloat(metric.capsuleHeight)
        let padH = CGFloat(metric.capsulePaddingH)
        let gap = CGFloat(metric.capsuleGap)
        let dot = CGFloat(metric.capsuleDot)
        let font = NSFont.monospacedDigitSystemFont(ofSize: CGFloat(DarkroomType.capsule.size),
                                                    weight: darkroomFontWeight(DarkroomType.capsule.weight))
        let textColor = darkroomColor(style.text ?? DarkroomColor.onSignal)
        // 設定「選單列計時」關掉時不畫計時，膠囊照畫（§4.38.3）
        let timer = style.showsTimer && showTimer ? m.timerText : ""
        let words = [style.label, timer].filter { !$0.isEmpty }.joined(separator: " ")
        let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: textColor]
        let textSize = words.isEmpty ? .zero : (words as NSString).size(withAttributes: attrs)
        let hasGlyph = style.glyph != .none
        let split = style.shape == .split
        // 靜音分段膠囊左段：mic.slash（paletteColors 白、非 template）
        var mic: NSImage? = nil
        if split {
            let config = NSImage.SymbolConfiguration(pointSize: CGFloat(DarkroomType.capsule.size) - 2, weight: .bold)
                .applying(NSImage.SymbolConfiguration(paletteColors: [darkroomColor(DarkroomColor.onSignal)]))
            mic = NSImage(systemSymbolName: "mic.slash", accessibilityDescription: nil)?.withSymbolConfiguration(config)
            mic?.isTemplate = false
        }
        let micSize = mic?.size ?? .zero
        let leftWidth = split ? CGFloat(metric.muteSegmentPaddingLeading) + ceil(micSize.width)
            + CGFloat(metric.muteSegmentPaddingTrailing) : 0
        let mainWidth = padH * 2 + (hasGlyph ? dot : 0) + (hasGlyph && !words.isEmpty ? gap : 0) + ceil(textSize.width)
        let capsuleWidth = leftWidth + mainWidth
        let badgeD = CGFloat(metric.badgeDiameter)
        let badgeStroke = CGFloat(metric.badgeStroke)
        let imageWidth = capsuleWidth + (style.badge ? 2 : 0)    // 角標壓在右上角，略超出膠囊
        let borderWidth = CGFloat(style.borderWidth)
        let fill = style.fill.map(darkroomColor)
        let border = style.border.map(darkroomColor)
        let backdrop = style.fill == nil && reduceTransparency
            ? darkroomColor(dark ? DarkroomColor.menuBarDark : DarkroomColor.menuBarLight) : nil
        let glyph = style.glyph
        let image = NSImage(size: NSSize(width: imageWidth, height: height), flipped: true) { _ in
            let rect = NSRect(x: 0, y: 0, width: capsuleWidth, height: height)
            let inset = rect.insetBy(dx: borderWidth / 2, dy: borderWidth / 2)
            let radius = inset.height / 2
            let body = NSBezierPath(roundedRect: inset, xRadius: radius, yRadius: radius)
            if let backdrop {
                backdrop.setFill()
                body.fill()
            }
            if let fill {
                NSGraphicsContext.saveGraphicsState()
                NSBezierPath(roundedRect: rect, xRadius: height / 2, yRadius: height / 2).addClip()
                fill.setFill()
                rect.fill()
                if split {
                    darkroomColor(DarkroomColor.mutedSegment).setFill()
                    NSRect(x: 0, y: 0, width: leftWidth, height: height).fill()
                }
                NSGraphicsContext.restoreGraphicsState()
            }
            if let border, borderWidth > 0 {
                border.setStroke()
                body.lineWidth = borderWidth
                body.stroke()
            }
            if let mic {
                let r = NSRect(x: CGFloat(metric.muteSegmentPaddingLeading), y: (height - micSize.height) / 2,
                               width: micSize.width, height: micSize.height)
                mic.draw(in: r, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
            }
            var x = leftWidth + padH
            if hasGlyph {
                textColor.setFill()
                let y = (height - dot) / 2
                if glyph == .pause {   // 暫停符號：兩條
                    let barW: CGFloat = 2.5, barGap: CGFloat = 2.5, barH = dot + 1
                    let x0 = x + (dot - barW * 2 - barGap) / 2
                    for bx in [x0, x0 + barW + barGap] {
                        NSBezierPath(roundedRect: NSRect(x: bx, y: (height - barH) / 2, width: barW, height: barH),
                                     xRadius: 1, yRadius: 1).fill()
                    }
                } else {               // 錄製點（.dot；分段膠囊的右段也是點）
                    NSBezierPath(ovalIn: NSRect(x: x, y: y, width: dot, height: dot)).fill()
                }
                x += dot + (words.isEmpty ? 0 : gap)
            }
            if !words.isEmpty {
                (words as NSString).draw(at: NSPoint(x: x, y: (height - textSize.height) / 2), withAttributes: attrs)
            }
            if style.badge {   // 有告警的角標：attention 底、onAttention 描邊（灰階也分得出，WCAG 1.4.1）
                let r = NSRect(x: imageWidth - badgeD - badgeStroke / 2, y: badgeStroke / 2, width: badgeD, height: badgeD)
                let p = NSBezierPath(ovalIn: r)
                darkroomColor(DarkroomColor.attention).setFill()
                p.fill()
                darkroomColor(DarkroomColor.onAttention).setStroke()
                p.lineWidth = badgeStroke
                p.stroke()
            }
            return true
        }
        image.isTemplate = false    // 紅、黃、紫都是自訂色，不給系統上色（macOS 26 template＋染色會畫成透明，§6 第 107 條）
        return image
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
        // 快捷鍵回饋依 feedbackRoute（spec §4.40.5）：HUD 看得到走 HUD、圖示看得到不發、兩者都看不到才發通知
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
        let recordPid = readPid(pidURL)
        let availability = controlAvailability(status: readStatus(statusURL), recordPid: recordPid,
                                               pidAlive: recordPid.map(pidAlive) ?? false)
        performControl(cmd, action: action, availability: availability, feedback: feedback)
    }

    /// 選單、快捷鍵與 HUD 共用：依 controlAvailability 的結果寫控制檔、送 SIGUSR1（同一動作 1 秒內只算一次）
    private func performControl(_ cmd: ControlCommand, action: String, availability: ControlAvailability,
                                feedback: Bool) {
        guard debouncer.accept(action, at: ProcessInfo.processInfo.systemUptime) else { return }
        switch availability {
        case .unavailable(let message):
            notify(title: "MeetingRecorder 沒辦法操作錄製", body: message, kind: .failure)
        case .ready(let pid, let runId):
            let written: RecordControl
            do {
                written = try requestControl(cmd, home: home, runId: runId)
            } catch {
                notify(title: "MeetingRecorder 沒辦法操作錄製", body: "寫控制檔失敗：\(error.localizedDescription)",
                       kind: .failure, runId: runId)
                return
            }
            if kill(pid, SIGUSR1) != 0 {
                notify(title: "MeetingRecorder 沒辦法操作錄製", body: "通知錄製實例失敗（errno \(errno)）",
                       kind: .failure, runId: runId)
            } else if feedback {
                switch feedbackRoute(hudVisible: hud.isShown, iconVisible: iconObscured != true) {
                case .hud, .none:   // HUD 或選單列圖示看得到：下一次 refresh 就反映新狀態，不另發通知
                    break
                case .notification:
                    notify(title: "MeetingRecorder", body: controlFeedback(cmd, markerSeq: written.markerSeq),
                           kind: .hotkeyFeedback, runId: runId)
                }
            }
        }
    }

    /// 通知在背景送（Notifier.post 最多等 3 秒，不得卡住主執行緒）；依種類分級（spec §4.39.1）
    private func notify(title: String, body: String, kind: NotificationKind, runId: String? = nil) {
        let log = Logger(path: logURL.path, append: true)
        let policy = notificationPolicy(kind: kind, runId: runId,
                                        timeSensitiveAllowed: loadMenuBarSettings(home: home).timeSensitiveAlerts)
        DispatchQueue.global(qos: .utility).async { Notifier.post(title: title, body: body, log: log, policy: policy) }
    }

    /// 錄製中出現新告警時發一則通知（spec §4.39.2、§4.39.3）。第一次看到某一場時只記下當下的 warnings、不補發
    /// （menu bar 中途重開不洗版）；之後只發 newAlertWarnings 的最新一則。內文用固定句，不放場次名與視窗標題。
    private func notifyNewAlerts(_ st: RecordStatus?) {
        guard let st else { return }
        guard alertRunId == st.runId else {
            alertRunId = st.runId
            seenWarnings = st.warnings
            return
        }
        let fresh = newAlertWarnings(previous: seenWarnings, current: st.warnings)
        seenWarnings = st.warnings
        guard st.phase == .recording, let latest = fresh.max(by: { $0.t < $1.t }) else { return }
        hud.newAlert(message: latest.message)   // HUD 顯示中才自動展開 8 秒（§4.40.7）
        let more = fresh.count > 1 ? "（另有 \(fresh.count - 1) 則新告警）" : ""
        notify(title: "MeetingRecorder 錄製中有告警", body: alertNotificationBody(latest.kind) + more,
               kind: .alertWarning, runId: st.runId)
    }

    // MARK: - 停止、打開場次、上一場成品

    @objc private func copyDetail() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(model.detailText, forType: .string)
    }

    /// 停止前先確認 record.pid 真的是持有 record.lock 的錄製實例（spec §4.27.4）：
    /// 只有 stopTargetDecision 回 .signal(pid:) 才送 SIGTERM；拒絕時說明原因、不送任何訊號。
    @objc private func stopRecording() {
        guard model.canStop else { return }
        let recordPid = readPid(pidURL)
        let current = readStatus(statusURL)
        let decision = stopTargetDecision(lockHeld: recordLockHeld(), recordPid: recordPid,
                                          pidAlive: recordPid.map(pidAlive) ?? false, statusPid: current?.pid,
                                          command: recordPid.flatMap(executablePath))
        performStop(decision, current: current)
    }

    /// 選單與 HUD 共用：只有 stopTargetDecision 回 .signal(pid:) 才送 SIGTERM
    private func performStop(_ decision: StopTarget, current: RecordStatus?) {
        guard case let .signal(pid) = decision else {
            if case .refuse(let why) = decision {
                Logger(path: logURL.path, append: true).line("\(isoNow()) 停止錄製被拒（\(why.rawValue)）：不送訊號")
                notify(title: "MeetingRecorder 沒有停止錄製", body: stopRefusalText(why), kind: .failure,
                       runId: current?.runId)
            }
            return
        }
        guard kill(pid, SIGTERM) == 0 else { return }
        stopRequestedRunId = current?.runId
        refresh()
    }

    /// record.lock 是否被別的程序持有：試鎖一次（不重試、不阻塞），拿到就立刻放掉。
    /// 打不開鎖檔（.unavailable）視為沒有持有，寧可不送訊號（spec §4.27.1）。
    private func recordLockHeld() -> Bool {
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

    /// HUD 可能顯示的外觀（錄製中、靜音、告警、暫停；spec §4.40.1）
    private func hudEligible(_ m: MenuBarModel) -> Bool {
        hudVisible(mode: .always, obscured: false, appearance: m.appearance)
    }

    /// HUD 顯示與否＝hudVisible（設定的 hudMode、圖示是否被擋住、目前外觀）；收尾中與之後不顯示
    private func updateHUD(_ m: MenuBarModel) {
        let settings = loadMenuBarSettings(home: home)
        let visible = hudVisible(mode: settings.hudMode, obscured: iconObscured ?? false, appearance: m.appearance)
        let label = menuBarAccessibilityLabel(appearance: m.appearance, alertBadge: m.alertBadge, spoken: m.spokenDuration,
                                              alertText: latestAlertMessage(status), status: m.statusLine)
        hud.update(model: m, status: status, visible: visible, hudPosition: settings.hudPosition,
                   screen: item.button?.window?.screen, accessibilityLabel: label)
    }

    /// 開錄後第一次 refresh 時排一次檢查（計時已顯示、寬度已定），之後由 obscuredTimer 每 obscuredCheckSeconds 檢查
    private func scheduleFirstObscuredCheck(_ st: RecordStatus?) {
        guard let st, st.phase == .recording, obscureFirstCheckRunId != st.runId else { return }
        obscureFirstCheckRunId = st.runId
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.checkObscured() }
    }

    /// 看選單列圖示是否被瀏海擋住或被系統藏起來（spec §4.40.3、§6 第 121 條）。結果交給 obscuredAction：
    /// auto 模式下狀態改變時顯示／收起 HUD；同一結果也決定快捷鍵回饋走哪條路（feedbackRoute）。
    private func checkObscured() {
        guard hudEligible(model) else {
            iconObscured = nil
            return
        }
        guard let window = item.button?.window else { return }
        let frame = window.frame
        let screen = window.screen ?? NSScreen.main
        var notchMinX: CGFloat? = nil, notchMaxX: CGFloat? = nil
        if let sc = screen, let l = sc.auxiliaryTopLeftArea, let r = sc.auxiliaryTopRightArea {
            notchMinX = sc.frame.minX + l.maxX
            notchMaxX = sc.frame.minX + r.minX
        }
        let visible = window.occlusionState.contains(.visible)
        let obscured = statusItemObscured(itemMinX: frame.minX, itemMaxX: frame.maxX, visible: visible,
                                          notchMinX: notchMinX, notchMaxX: notchMaxX)
        let previous = iconObscured
        iconObscured = obscured
        let mode = loadMenuBarSettings(home: home).hudMode
        switch obscuredAction(previous: previous, current: obscured, mode: mode, recording: true) {
        case .showHUD:
            Logger(path: logURL.path, append: true)
                .line("\(isoNow()) 選單列圖示看不到（x \(Int(frame.minX))–\(Int(frame.maxX))、visible \(visible)）：顯示錄製小窗")
            updateHUD(model)
        case .hideHUD:
            Logger(path: logURL.path, append: true).line("\(isoNow()) 選單列圖示又看得到了：收起錄製小窗")
            updateHUD(model)
        case .none:
            break
        }
    }

    private func trackCompletion(_ st: RecordStatus?) {
        guard let st else { return }
        switch st.phase {
        case .recording, .stopping, .finalizing:
            seenInProgress.insert(st.runId)
        case .done where st.code == 0 && seenInProgress.contains(st.runId) && !completionPosted.contains(st.runId):
            completionPosted.insert(st.runId)
            if st.discarded == true {
                // 捨棄成功（spec §4.42.3）：場次已移到垃圾桶，不記 lastSession、不給「在 Finder 顯示」
                postDiscarded(st)
            } else {
                if !st.session.isEmpty { prefsStore.update { $0.lastSession = st.session } }
                postCompletion(st)
            }
        default:
            break
        }
        let prefs = prefsStore.current
        if let session = shouldAutoPrep(autoPrep: prefs.autoPrep, status: st, seenInProgressRunIds: seenInProgress,
                                        lastAutoPrepRunId: prefs.lastAutoPrepRunId) {
            prefsStore.update { $0.lastAutoPrepRunId = st.runId }   // 啟動前先記，同一場不會跑兩次
            autoPrep.enqueue(session, runId: st.runId)
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
    private func postDiscarded(_ st: RecordStatus) {
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
        completionHandler()
    }

    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .list])
    }
}

// MARK: - HUD 按鈕的執行端（與選單同一條控制路徑；Trigger/HUD.swift）

extension MenuBarController: HUDActions {
    func hudControl(_ cmd: ControlCommand, action: String, availability: ControlAvailability) {
        performControl(cmd, action: action, availability: availability, feedback: false)
    }

    func hudStop(_ decision: StopTarget, status current: RecordStatus?) {
        guard model.canStop else { return }
        performStop(decision, current: current)
    }

    func hudRecordLockHeld() -> Bool {
        recordLockHeld()
    }

    func hudExecutablePath(_ pid: Int32) -> String? {
        executablePath(pid)
    }
}

// MARK: - 膠囊與通知的小工具

/// DarkroomColor 的 "#RRGGBB" → sRGB NSColor（Core 不 import AppKit，只放字串；spec §3.20）。格式不對時用 labelColor。
private func darkroomColor(_ hex: String) -> NSColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return .labelColor }
    return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                   blue: CGFloat(v & 0xFF) / 255, alpha: 1)
}

/// TypeToken.weight（"regular"／"semibold"／"bold"）→ NSFont.Weight
private func darkroomFontWeight(_ w: String) -> NSFont.Weight {
    switch w {
    case "bold": return .bold
    case "semibold": return .semibold
    default: return .regular
    }
}

/// 選單列是否深色（含「增加對比」的深色外觀）
private func isDarkAppearance(_ a: NSAppearance) -> Bool {
    let match = a.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
    return match == .darkAqua || match == .accessibilityHighContrastDarkAqua
}

/// 程序的執行檔完整路徑（等同 ps -o comm=；stopTargetDecision 的 command）；取不到回 nil
private func executablePath(_ pid: Int32) -> String? {
    var buf = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
    let n = proc_pidpath(pid, &buf, UInt32(buf.count))
    return n > 0 ? String(cString: buf) : nil
}

/// 停止被拒的說明（不含場次名）
private func stopRefusalText(_ r: StopRefusal) -> String {
    switch r {
    case .noLock: return "找不到正在錄製的實例（record.lock 沒有被持有），沒有送出停止"
    case .noPid: return "找不到 record.pid，沒有送出停止"
    case .pidDead: return "record.pid 的程序已經不在，請執行 meeting record finish 收尾"
    case .pidMismatch: return "record.pid 與狀態檔的 pid 不一致，為了安全沒有送出停止"
    case .notRecorder: return "record.pid 指向的不是 MeetingRecorder，為了安全沒有送出停止"
    }
}

/// 告警通知的內文（spec §4.39.3）：依種類用固定句，不帶場次名、視窗標題或檔名
private func alertNotificationBody(_ kind: WarningKind) -> String {
    switch kind {
    case .silenceSystem: return "系統聲音已連續 15 秒幾乎沒有聲音：檢查會議 app 的輸出與音量"
    case .silenceMic: return "麥克風已連續 15 秒幾乎沒有聲音：檢查麥克風是否被拔掉或靜音"
    case .black: return "會議視窗畫面已連續 5 秒全黑：確認會議畫面是否正常（錄製照常進行）"
    case .suspended: return "會議視窗的擷取已暫停超過 5 秒（多半是被最小化）：把視窗還原"
    case .diskLow: return "磁碟可用空間低於 2 GB，已自動停止並收尾"
    case .segmentWriteFailed: return "段落寫檔失敗，檔案保留；詳見 record.log"
    case .deviceChange, .audioFormatChange: return "錄製中有新狀況，打開選單看詳情"
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

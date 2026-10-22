// Trigger/HUD.swift —— 錄製小窗 U2-C「收在螢幕邊緣」（spec §4.40.4、§4.40.7、§4.40.8；design-r3/README.md §3）。
// 收合：貼螢幕邊緣的直立標籤（錄製點＋直排計時）；滑鼠移入展開成面板（狀態、計時、兩條音量條、四顆按鈕）。
// 非啟用的 NSPanel、所有桌面可見、不被螢幕分享擷取；一律深色；顏色、字級、尺寸一律取自 Core 的 DarkroomColor／
// DarkroomType／DarkroomMetric，不用系統色。何時顯示由 menu bar 依 Core 的 hudVisible 決定（MenuBar.swift）。
// 四顆按鈕與選單走同一條控制路徑：controlAvailability／stopTargetDecision 判斷後交給 menu bar 實例執行（HUDActions）。
// 不顯示錄音資料夾名稱與視窗標題（使用者可能正在分享螢幕）。
import AppKit

/// HUD 按鈕的執行端（MenuBarController 實作）：與選單項目共用送控制檔、送停止訊號、去抖與失敗通知。
protocol HUDActions: AnyObject {
    func hudControl(_ cmd: ControlCommand, action: String, availability: ControlAvailability)
    func hudStop(_ decision: StopTarget, status: RecordStatus?)
    func hudRecordLockHeld() -> Bool
    func hudExecutablePath(_ pid: Int32) -> String?
}

/// 每次 refresh 交給 HUD 畫的內容
private struct HUDContent: Equatable {
    var paused = false
    var micMuted = false
    var canControl = false
    var canStop = false
    var timerText = ""
    var system: Double? = nil
    var mic: Double? = nil
    /// 本次錄製出現過告警類 warning：外框改 attention，維持到這次錄製結束（warnings 只累加；§4.40.7）
    var alertBorder = false
    /// 新告警的訊息（40 字截斷），顯示在展開區狀態列下方的告警膠囊
    var alertMessage: String? = nil
}

// MARK: - 控制器

final class HUDController: NSObject {
    weak var actions: HUDActions?
    private let home: URL
    private let window = HUDWindow()
    private let root = HUDRootView()
    private(set) var isShown = false
    private var expanded = false
    /// 點標籤（或展開後點面板空白處）固定展開，再點一下取消
    private var pinned = false
    private var hovering = false
    /// 新告警自動展開的期間（hudAlertExpandSeconds）
    private var alertHolding = false
    private var alertGeneration = 0
    private var collapseWork: DispatchWorkItem?
    private var content = HUDContent()
    private var runId: String?
    private var edgeRight = true
    private var screen: NSScreen?
    private var lastTarget: NSRect?
    private var displayOptionsObserver: NSObjectProtocol?

    init(home: URL) {
        self.home = home
        super.init()
        window.contentView = root
        root.controller = self
        root.tab.onPress = { [weak self] in self?.tabPressed() }
        root.panel.onBackgroundClick = { [weak self] in self?.panelBackgroundClicked() }
        let p = root.panel
        for (b, sel) in [(p.pauseButton, #selector(pausePressed)), (p.muteButton, #selector(mutePressed)),
                         (p.markButton, #selector(markPressed)), (p.stopButton, #selector(stopPressed))] {
            b.target = self
            b.action = sel
        }
        p.stopButton.destructive = true
        // 「減少透明度」「增加對比」改變時重畫（「減少動態效果」在每次展開／收合時讀）
        displayOptionsObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.root.redraw() }
    }

    deinit {
        if let o = displayOptionsObserver { NSWorkspace.shared.notificationCenter.removeObserver(o) }
    }

    private var statusURL: URL { home.appendingPathComponent("record.status.json") }
    private var pidURL: URL { home.appendingPathComponent("record.pid") }

    /// menu bar 每次 refresh 呼叫。visible＝hudVisible(mode:obscured:appearance:)；hudPosition＝設定的 right／left；
    /// screen＝status item 按鈕視窗所在的螢幕（取不到時用 NSScreen.main）；accessibilityLabel＝menuBarAccessibilityLabel。
    func update(model m: MenuBarModel, status st: RecordStatus?, visible: Bool, hudPosition: String, screen: NSScreen?,
                accessibilityLabel: String) {
        if st?.runId != runId {   // 換了一次錄製：告警膠囊、固定展開都重來
            runId = st?.runId
            content.alertMessage = nil
            pinned = false
        }
        guard visible else {
            hide()
            return
        }
        content.paused = m.paused
        content.micMuted = m.micMuted
        content.canControl = m.canControl
        content.canStop = m.canStop
        content.timerText = m.timerText
        content.system = st?.recentLevels?.system
        content.mic = st?.recentLevels?.mic
        content.alertBorder = st?.warnings.contains { $0.kind.isAlert } ?? false
        edgeRight = hudPosition != "left"
        self.screen = screen
        let head = "MeetingRecorder："
        let body = accessibilityLabel.hasPrefix(head) ? String(accessibilityLabel.dropFirst(head.count)) : accessibilityLabel
        root.tab.setAccessibilityLabel("錄製小窗：" + body)
        apply()
        if !isShown {
            show()
        } else {
            reposition()
        }
    }

    /// 新告警（newAlertWarnings 非空；§4.40.7）：HUD 顯示中才自動展開 hudAlertExpandSeconds；不顯示時不強制顯示。
    func newAlert(message: String) {
        content.alertMessage = truncatedStatusTitle(message, limit: 40)
        content.alertBorder = true
        apply()
        guard isShown else { return }
        alertGeneration += 1
        let generation = alertGeneration
        alertHolding = true
        collapseWork?.cancel()
        setExpanded(true)
        DispatchQueue.main.asyncAfter(deadline: .now() + hudAlertExpandSeconds) { [weak self] in
            guard let self, self.alertGeneration == generation else { return }
            self.alertHolding = false
            if !self.hovering && !self.pinned { self.setExpanded(false) }
        }
    }

    // MARK: 顯示、展開、收合

    private func apply() {
        root.edgeRight = edgeRight
        root.tab.content = content
        root.panel.content = content
        root.redraw()
    }

    private var reduceMotion: Bool { NSWorkspace.shared.accessibilityDisplayShouldReduceMotion }

    private func show() {
        isShown = true
        expanded = false
        root.showExpanded(false)
        let frame = targetFrame(expanded: false)
        lastTarget = frame
        window.setFrame(frame, display: true)
        if reduceMotion {
            window.alphaValue = 1
            window.orderFrontRegardless()
        } else {
            window.alphaValue = 0
            window.orderFrontRegardless()
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = hudAnimationSeconds
                window.animator().alphaValue = 1
            }
        }
    }

    private func hide() {
        guard isShown else { return }
        isShown = false
        expanded = false
        hovering = false
        alertHolding = false
        alertGeneration += 1
        collapseWork?.cancel()
        lastTarget = nil
        window.orderOut(nil)
    }

    /// 螢幕、貼邊側或面板高度（告警膠囊）變了才移動；不打斷正在進行的展開動畫
    private func reposition() {
        let frame = targetFrame(expanded: expanded)
        guard frame != lastTarget else { return }
        lastTarget = frame
        window.setFrame(frame, display: true)
    }

    private func setExpanded(_ e: Bool) {
        guard isShown else { return }
        expanded = e
        root.showExpanded(e)
        let frame = targetFrame(expanded: e)
        lastTarget = frame
        if reduceMotion {   // 「減少動態效果」：直接出現與消失，不做滑動
            window.setFrame(frame, display: true)
        } else {
            NSAnimationContext.runAnimationGroup { ctx in
                ctx.duration = hudAnimationSeconds
                window.animator().setFrame(frame, display: true)
            }
        }
    }

    /// 標籤頂端＝所在螢幕 visibleFrame 頂端往下 hudTabTopFraction × 高度；展開的面板頂端對齊標籤頂端
    private func targetFrame(expanded e: Bool) -> NSRect {
        let vf = (screen ?? NSScreen.main)?.visibleFrame ?? .zero
        let top = vf.maxY - CGFloat(DarkroomMetric.hudTabTopFraction) * vf.height
        let size = e
            ? NSSize(width: CGFloat(DarkroomMetric.hudPanelWidth),
                     height: HUDPanelView.height(alert: content.alertMessage != nil))
            : NSSize(width: CGFloat(DarkroomMetric.hudTabWidth), height: CGFloat(DarkroomMetric.hudTabHeight))
        let x = edgeRight ? vf.maxX - size.width : vf.minX
        let y = max(vf.minY, top - size.height)
        return NSRect(x: x, y: y, width: size.width, height: size.height)
    }

    fileprivate func mouseEntered() {
        hovering = true
        collapseWork?.cancel()
        if !expanded { setExpanded(true) }
    }

    fileprivate func mouseExited() {
        hovering = false
        scheduleCollapse()
    }

    /// 滑鼠離開 hudCollapseDelaySeconds 後收合（固定展開、告警自動展開期間不收）
    private func scheduleCollapse() {
        collapseWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            guard let self, !self.hovering, !self.pinned, !self.alertHolding else { return }
            self.setExpanded(false)
        }
        collapseWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + hudCollapseDelaySeconds, execute: work)
    }

    private func tabPressed() {
        pinned = true
        collapseWork?.cancel()
        setExpanded(true)
    }

    private func panelBackgroundClicked() {
        pinned.toggle()
        if !pinned && !hovering { scheduleCollapse() }
    }

    // MARK: 四顆按鈕（與選單同一條控制路徑）

    @objc private func pausePressed() {
        control(content.paused ? .resume : .pause, action: "pause")
    }

    @objc private func mutePressed() {
        control(content.micMuted ? .unmute : .mute, action: "mute")
    }

    @objc private func markPressed() {
        control(.mark, action: "mark")
    }

    private func control(_ cmd: ControlCommand, action: String) {
        guard content.canControl, let actions else { return }
        let recordPid = readPid(pidURL)
        let availability = controlAvailability(status: readStatus(statusURL), recordPid: recordPid,
                                               pidAlive: recordPid.map(pidAlive) ?? false)
        actions.hudControl(cmd, action: action, availability: availability)
    }

    /// 停止前先確認 record.pid 真的是持有 record.lock 的錄製實例（spec §4.27.4），由 menu bar 依結果送 SIGTERM 或說明拒絕原因
    @objc private func stopPressed() {
        guard content.canStop, let actions else {
            // spec §4.10.3：提早 return 前記一行
            Logger(path: home.appendingPathComponent("record.log").path, append: true)
                .line("\(isoNow()) " + stopPathLogLine(source: "HUD.stopPressed", reason: "目前不能停止或選單已不在"))
            return
        }
        let recordPid = readPid(pidURL)
        let current = readStatus(statusURL)
        let decision = stopTargetDecision(lockHeld: actions.hudRecordLockHeld(), recordPid: recordPid,
                                          pidAlive: recordPid.map(pidAlive) ?? false, statusPid: current?.pid,
                                          command: recordPid.flatMap { actions.hudExecutablePath($0) })
        actions.hudStop(decision, status: current)
    }
}

// MARK: - 視窗

/// 非啟用的浮動面板：點按鈕不搶走會議 app 的焦點；所有桌面可見；螢幕分享與螢幕錄製擷取不到（sharingType）
private final class HUDWindow: NSPanel {
    init() {
        super.init(contentRect: NSRect(x: 0, y: 0, width: DarkroomMetric.hudTabWidth, height: DarkroomMetric.hudTabHeight),
                   styleMask: [.nonactivatingPanel, .borderless], backing: .buffered, defer: true)
        isFloatingPanel = true
        level = .statusBar
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        sharingType = .none
        isOpaque = false
        backgroundColor = .clear
        hasShadow = true
        hidesOnDeactivate = false
        isMovable = false
        isReleasedWhenClosed = false
        becomesKeyOnlyIfNeeded = true
        appearance = NSAppearance(named: .darkAqua)   // 暗房：一律深色，不跟系統淺色
    }

    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

/// 收合時只顯示標籤、展開時只顯示面板；整個視窗的滑鼠移入／移出決定展開與收合
private final class HUDRootView: NSView {
    weak var controller: HUDController?
    let tab = HUDTabView()
    let panel = HUDPanelView()
    var edgeRight = true {
        didSet {
            tab.edgeRight = edgeRight
            panel.edgeRight = edgeRight
            layoutChildren()
        }
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        addSubview(tab)
        addSubview(panel)
        panel.isHidden = true
        setAccessibilityElement(false)
    }

    required init?(coder: NSCoder) { nil }

    override var isFlipped: Bool { true }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        for t in trackingAreas { removeTrackingArea(t) }
        addTrackingArea(NSTrackingArea(rect: .zero, options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                                       owner: self, userInfo: nil))
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        updateTrackingAreas()
    }

    override func mouseEntered(with event: NSEvent) { controller?.mouseEntered() }
    override func mouseExited(with event: NSEvent) { controller?.mouseExited() }

    override func resizeSubviews(withOldSize oldSize: NSSize) {
        layoutChildren()
    }

    /// 面板貼在邊緣那一側（展開動畫中視窗變寬時從邊緣長出）
    private func layoutChildren() {
        tab.frame = bounds
        let w = CGFloat(DarkroomMetric.hudPanelWidth)
        panel.frame = NSRect(x: edgeRight ? bounds.width - w : 0, y: 0, width: w, height: bounds.height)
    }

    func showExpanded(_ e: Bool) {
        tab.isHidden = e
        panel.isHidden = !e
    }

    func redraw() {
        tab.needsDisplay = true
        panel.refresh()
    }
}

// MARK: - 收合標籤（自訂繪製）

private final class HUDTabView: NSView {
    var content = HUDContent()
    var edgeRight = true
    var onPress: (() -> Void)?

    override init(frame: NSRect) {
        super.init(frame: frame)
        setAccessibilityElement(true)
        setAccessibilityRole(.button)
    }

    required init?(coder: NSCoder) { nil }

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func mouseDown(with event: NSEvent) { onPress?() }
    override func accessibilityPerformPress() -> Bool {
        onPress?()
        return true
    }

    override func draw(_ dirtyRect: NSRect) {
        let frameStyle = hudFrameStyle(alpha: 0.94, alert: content.alertBorder)
        drawEdgeShape(bounds, radius: CGFloat(DarkroomMetric.hudTabCornerRadius), edgeRight: edgeRight, style: frameStyle)
        let dot = CGFloat(DarkroomMetric.hudTabDot)
        let gap = dot   // 稿：點與計時的間距 10，與點徑同（design-r3/README.md §3）
        let attrs: [NSAttributedString.Key: Any] = [
            .font: hudFont(DarkroomType.hudTabTimer),
            .foregroundColor: hudColor(content.paused ? DarkroomColor.attentionText : DarkroomColor.text),
        ]
        let timer = content.timerText as NSString
        let timerSize = content.timerText.isEmpty ? .zero : timer.size(withAttributes: attrs)
        let mic = content.micMuted ? hudSymbol("mic.slash", pointSize: 12, color: DarkroomColor.onSignal) : nil
        let micSize = mic?.size ?? .zero
        let total = dot + (timerSize.width > 0 ? gap + timerSize.width : 0) + (mic != nil ? gap + micSize.height : 0)
        let cx = bounds.midX
        var y = (bounds.height - total) / 2
        if content.paused {   // 暫停：兩條 attention 暫停符號
            hudColor(DarkroomColor.attention).setFill()
            let barW = dot / 4, barGap = dot / 4
            let x0 = cx - (barW * 2 + barGap) / 2
            for bx in [x0, x0 + barW + barGap] {
                NSBezierPath(roundedRect: NSRect(x: bx, y: y, width: barW, height: dot), xRadius: barW / 2,
                             yRadius: barW / 2).fill()
            }
        } else {              // 錄製點
            hudColor(DarkroomColor.recording).setFill()
            NSBezierPath(ovalIn: NSRect(x: cx - dot / 2, y: y, width: dot, height: dot)).fill()
        }
        y += dot
        if timerSize.width > 0 {   // 直排計時：字轉 90°
            y += gap
            NSGraphicsContext.saveGraphicsState()
            let t = NSAffineTransform()
            t.translateX(by: cx, yBy: y + timerSize.width / 2)
            t.rotate(byDegrees: 90)
            t.concat()
            timer.draw(at: NSPoint(x: -timerSize.width / 2, y: -timerSize.height / 2), withAttributes: attrs)
            NSGraphicsContext.restoreGraphicsState()
            y += timerSize.width
        }
        if let mic {   // 麥克風靜音：計時下方 12pt mic.slash（白）
            y += gap
            mic.draw(in: NSRect(x: cx - micSize.width / 2, y: y, width: micSize.width, height: micSize.height),
                     from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
        }
    }
}

// MARK: - 展開面板（自訂繪製＋自訂按鈕）

private final class HUDPanelView: NSView {
    var content = HUDContent()
    var edgeRight = true
    var onBackgroundClick: (() -> Void)?
    let pauseButton = HUDButton(frame: .zero)
    let muteButton = HUDButton(frame: .zero)
    let markButton = HUDButton(frame: .zero)
    let stopButton = HUDButton(frame: .zero)
    let meter = HUDMeterView()

    private static var padding: CGFloat { CGFloat(DarkroomMetric.hudPanelPadding) }
    private static var rowHeight: CGFloat { ceil(lineHeight(hudFont(DarkroomType.hudTimer))) }
    private static var capsuleHeight: CGFloat {
        ceil(lineHeight(hudFont(DarkroomType.hudAlert))) + CGFloat(DarkroomMetric.spacing[0]) * 2
    }
    private static var sectionGap: CGFloat { CGFloat(DarkroomMetric.spacing[2]) }
    private static var capsuleGap: CGFloat { CGFloat(DarkroomMetric.spacing[1]) }
    private static var buttonsHeight: CGFloat {
        CGFloat(DarkroomMetric.hudButtonHeight) * 2 + CGFloat(DarkroomMetric.hudButtonGap)
    }

    /// 展開面板的高度：內距＋狀態列（＋告警膠囊）＋兩條音量條＋2×2 按鈕＋內距
    static func height(alert: Bool) -> CGFloat {
        padding + rowHeight + (alert ? capsuleGap + capsuleHeight : 0) + sectionGap + HUDMeterView.height + sectionGap
            + buttonsHeight + padding
    }

    override init(frame: NSRect) {
        super.init(frame: frame)
        for v in [meter, pauseButton, muteButton, markButton, stopButton] as [NSView] { addSubview(v) }
        markButton.title = "標記"
        markButton.toolTip = "加標記（⌃⌥⌘B）"
        markButton.setAccessibilityLabel("加標記（⌃⌥⌘B）")
        stopButton.title = "停止"
        stopButton.toolTip = "停止錄製並收尾"
        stopButton.setAccessibilityLabel("停止錄製並收尾")
        setAccessibilityElement(true)
        setAccessibilityRole(.group)
    }

    required init?(coder: NSCoder) { nil }

    override var isFlipped: Bool { true }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func mouseDown(with event: NSEvent) { onBackgroundClick?() }

    override func resizeSubviews(withOldSize oldSize: NSSize) {
        layoutButtons()
    }

    /// 依目前狀態換按鈕字面、無障礙標籤與可用性，再重排、重畫
    func refresh() {
        let c = content
        pauseButton.title = c.paused ? "繼續" : "暫停"
        let pauseHint = c.paused ? "繼續錄製（⌃⌥⌘P）" : "暫停錄製（⌃⌥⌘P）"
        pauseButton.toolTip = pauseHint
        pauseButton.setAccessibilityLabel(pauseHint)
        muteButton.title = c.micMuted ? "取消靜音" : "靜音"
        let muteHint = c.micMuted ? "取消麥克風靜音（⌃⌥⌘M）" : "麥克風靜音（⌃⌥⌘M）"
        muteButton.toolTip = muteHint
        muteButton.setAccessibilityLabel(muteHint)
        muteButton.selectedStyle = c.micMuted
        // canControl 為 false 時前三顆停用（§4.40.4）
        pauseButton.isEnabled = c.canControl
        muteButton.isEnabled = c.canControl
        markButton.isEnabled = c.canControl
        stopButton.isEnabled = c.canStop
        meter.system = c.system
        meter.mic = c.mic
        meter.muted = c.micMuted
        setAccessibilityLabel(c.paused ? "已暫停" : "錄製中")
        layoutButtons()
        for v in [self, meter, pauseButton, muteButton, markButton, stopButton] as [NSView] { v.needsDisplay = true }
    }

    private func layoutButtons() {
        let p = Self.padding
        let inner = bounds.width - p * 2
        var y = p + Self.rowHeight
        if content.alertMessage != nil { y += Self.capsuleGap + Self.capsuleHeight }
        y += Self.sectionGap
        meter.frame = NSRect(x: p, y: y, width: inner, height: HUDMeterView.height)
        y += HUDMeterView.height + Self.sectionGap
        let gap = CGFloat(DarkroomMetric.hudButtonGap)
        let w = (inner - gap) / 2
        let h = CGFloat(DarkroomMetric.hudButtonHeight)
        pauseButton.frame = NSRect(x: p, y: y, width: w, height: h)
        muteButton.frame = NSRect(x: p + w + gap, y: y, width: w, height: h)
        markButton.frame = NSRect(x: p, y: y + h + gap, width: w, height: h)
        stopButton.frame = NSRect(x: p + w + gap, y: y + h + gap, width: w, height: h)
    }

    override func draw(_ dirtyRect: NSRect) {
        let frameStyle = hudFrameStyle(alpha: 0.96, alert: content.alertBorder)
        drawEdgeShape(bounds, radius: CGFloat(DarkroomMetric.hudPanelCornerRadius), edgeRight: edgeRight,
                      style: frameStyle)
        let p = Self.padding
        let rowH = Self.rowHeight
        // 第 1 行：狀態字（hudLabel、textSecondary）＋右側計時（hudTimer）
        let labelAttrs: [NSAttributedString.Key: Any] = [.font: hudFont(DarkroomType.hudLabel),
                                                         .foregroundColor: hudColor(DarkroomColor.textSecondary)]
        let state = (content.paused ? "已暫停" : "錄製中") as NSString
        let stateSize = state.size(withAttributes: labelAttrs)
        state.draw(at: NSPoint(x: p, y: p + (rowH - stateSize.height) / 2), withAttributes: labelAttrs)
        let timerAttrs: [NSAttributedString.Key: Any] = [
            .font: hudFont(DarkroomType.hudTimer),
            .foregroundColor: hudColor(content.paused ? DarkroomColor.attentionText : DarkroomColor.text),
        ]
        let timer = content.timerText as NSString
        let timerSize = timer.size(withAttributes: timerAttrs)
        timer.draw(at: NSPoint(x: bounds.width - p - timerSize.width, y: p + (rowH - timerSize.height) / 2),
                   withAttributes: timerAttrs)
        // 告警膠囊：底 attention、字 onAttention（hudAlert）
        if let message = content.alertMessage {
            let capH = Self.capsuleHeight
            let rect = NSRect(x: p, y: p + rowH + Self.capsuleGap, width: bounds.width - p * 2, height: capH)
            hudColor(DarkroomColor.attention).setFill()
            NSBezierPath(roundedRect: rect, xRadius: capH / 2, yRadius: capH / 2).fill()
            let attrs: [NSAttributedString.Key: Any] = [.font: hudFont(DarkroomType.hudAlert),
                                                        .foregroundColor: hudColor(DarkroomColor.onAttention)]
            let text = message as NSString
            let size = text.size(withAttributes: attrs)
            let inset = CGFloat(DarkroomMetric.spacing[1])
            text.draw(with: NSRect(x: rect.minX + inset, y: rect.minY + (capH - size.height) / 2,
                                   width: rect.width - inset * 2, height: size.height),
                      options: [.usesLineFragmentOrigin, .truncatesLastVisibleLine], attributes: attrs)
        }
    }
}

/// 2×2 的四顆按鈕：前三顆底 raised、框 lineStrong、字 text；停止底 recording、白字 bold；靜音中以選取樣式（底 text、字 ink）
private final class HUDButton: NSButton {
    var destructive = false
    var selectedStyle = false

    override init(frame: NSRect) {
        super.init(frame: frame)
        isBordered = false
        setButtonType(.momentaryChange)
        focusRingType = .none
    }

    required init?(coder: NSCoder) { nil }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }

    override func draw(_ dirtyRect: NSRect) {
        let r = CGFloat(DarkroomMetric.hudButtonCornerRadius)
        let path = NSBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), xRadius: r, yRadius: r)
        let fill: String, textHex: String
        var border: String? = nil
        var weight = DarkroomType.hudButton.weight
        if destructive {
            fill = DarkroomColor.recording
            textHex = DarkroomColor.onSignal
            weight = "bold"
        } else if selectedStyle {
            fill = DarkroomColor.text
            textHex = DarkroomColor.ink
        } else {
            fill = DarkroomColor.raised
            textHex = DarkroomColor.text
            border = DarkroomColor.lineStrong
        }
        hudColor(fill).setFill()
        path.fill()
        if let border {
            hudColor(border).setStroke()
            path.lineWidth = 1
            path.stroke()
        }
        let attrs: [NSAttributedString.Key: Any] = [
            .font: hudFont(TypeToken(size: DarkroomType.hudButton.size, weight: weight)),
            .foregroundColor: hudColor(isEnabled ? textHex : DarkroomColor.textDisabled),
        ]
        let text = title as NSString
        let size = text.size(withAttributes: attrs)
        text.draw(at: NSPoint(x: (bounds.width - size.width) / 2, y: (bounds.height - size.height) / 2),
                  withAttributes: attrs)
    }
}

/// 系統、麥克風兩條音量條（取 A 稿樣式：軌道 line、系統 text、麥克風 done，高 6）；靜音時麥克風那行改「已靜音」
private final class HUDMeterView: NSView {
    var system: Double?
    var mic: Double?
    var muted = false {
        didSet { updateAccessibility() }
    }

    private static let barHeight: CGFloat = 6
    private static var rowHeight: CGFloat { ceil(lineHeight(hudFont(DarkroomType.menuMeterLabel))) }
    static var height: CGFloat { rowHeight * 2 + CGFloat(DarkroomMetric.spacing[0]) }

    override init(frame: NSRect) {
        super.init(frame: frame)
        setAccessibilityElement(true)
        setAccessibilityRole(.levelIndicator)
        setAccessibilityLabel("收音")
    }

    required init?(coder: NSCoder) { nil }

    override var isFlipped: Bool { true }

    /// 「系統聲音 有聲／無聲；麥克風 有聲／無聲／已靜音」（門檻 -60 dBFS 嚴格大於，同選單音量條；§4.41.4）
    private func updateAccessibility() {
        func mark(_ v: Double?) -> String { (v ?? -.infinity) > -60 ? "有聲" : "無聲" }
        setAccessibilityValue("系統聲音 \(mark(system))；麥克風 \(muted ? "已靜音" : mark(mic))")
    }

    override func draw(_ dirtyRect: NSRect) {
        updateAccessibility()
        let rowH = Self.rowHeight
        let labelW = CGFloat(DarkroomMetric.meterLabelWidth)
        let attrs: [NSAttributedString.Key: Any] = [.font: hudFont(DarkroomType.menuMeterLabel),
                                                    .foregroundColor: hudColor(DarkroomColor.textSecondary)]
        let rows: [(String, Double?, String, Bool)] = [("系統", system, DarkroomColor.text, false),
                                                        ("麥克風", mic, DarkroomColor.done, muted)]
        for (i, row) in rows.enumerated() {
            let y = CGFloat(i) * (rowH + CGFloat(DarkroomMetric.spacing[0]))
            let label = row.0 as NSString
            let size = label.size(withAttributes: attrs)
            label.draw(at: NSPoint(x: 0, y: y + (rowH - size.height) / 2), withAttributes: attrs)
            let barX = labelW
            let barW = max(0, bounds.width - labelW)
            if row.3 {
                let mutedText = "已靜音" as NSString
                let ms = mutedText.size(withAttributes: attrs)
                mutedText.draw(at: NSPoint(x: barX, y: y + (rowH - ms.height) / 2), withAttributes: attrs)
                continue
            }
            let barY = y + (rowH - Self.barHeight) / 2
            let track = NSRect(x: barX, y: barY, width: barW, height: Self.barHeight)
            hudColor(DarkroomColor.line).setFill()
            NSBezierPath(roundedRect: track, xRadius: Self.barHeight / 2, yRadius: Self.barHeight / 2).fill()
            let fraction = CGFloat(levelFraction(dBFS: row.1))
            if fraction > 0 {
                hudColor(row.2).setFill()
                NSBezierPath(roundedRect: NSRect(x: barX, y: barY, width: barW * fraction, height: Self.barHeight),
                             xRadius: Self.barHeight / 2, yRadius: Self.barHeight / 2).fill()
            }
        }
    }
}

// MARK: - 外框、色、字的小工具

private struct HUDFrameStyle {
    var fill: NSColor
    var border: NSColor
    var borderWidth: CGFloat
}

/// 底色：surface 的指定不透明度（「減少透明度」時 1.0）；外框：1pt lineStrong，「增加對比」時 2pt text，告警時 2pt attention
private func hudFrameStyle(alpha: CGFloat, alert: Bool) -> HUDFrameStyle {
    let ws = NSWorkspace.shared
    let fillAlpha: CGFloat = ws.accessibilityDisplayShouldReduceTransparency ? 1.0 : alpha
    let fill = hudColor(DarkroomColor.surface, alpha: fillAlpha)
    if alert { return HUDFrameStyle(fill: fill, border: hudColor(DarkroomColor.attention), borderWidth: 2) }
    if ws.accessibilityDisplayShouldIncreaseContrast {
        return HUDFrameStyle(fill: fill, border: hudColor(DarkroomColor.text), borderWidth: 2)
    }
    return HUDFrameStyle(fill: fill, border: hudColor(DarkroomColor.lineStrong), borderWidth: 1)
}

/// 貼邊那側直角、內側圓角的外形；外框不畫貼邊那一側
private func drawEdgeShape(_ rect: NSRect, radius: CGFloat, edgeRight: Bool, style: HUDFrameStyle) {
    style.fill.setFill()
    edgePath(rect, radius: radius, edgeRight: edgeRight, closed: true).fill()
    let half = style.borderWidth / 2
    var inset = rect.insetBy(dx: 0, dy: half)
    if edgeRight {
        inset.origin.x += half
        inset.size.width -= half
    } else {
        inset.size.width -= half
    }
    let border = edgePath(inset, radius: max(0, radius - half), edgeRight: edgeRight, closed: false)
    style.border.setStroke()
    border.lineWidth = style.borderWidth
    border.stroke()
}

private func edgePath(_ r: NSRect, radius: CGFloat, edgeRight: Bool, closed: Bool) -> NSBezierPath {
    let p = NSBezierPath()
    if edgeRight {
        p.move(to: NSPoint(x: r.maxX, y: r.minY))
        p.line(to: NSPoint(x: r.minX + radius, y: r.minY))
        p.appendArc(from: NSPoint(x: r.minX, y: r.minY), to: NSPoint(x: r.minX, y: r.minY + radius), radius: radius)
        p.line(to: NSPoint(x: r.minX, y: r.maxY - radius))
        p.appendArc(from: NSPoint(x: r.minX, y: r.maxY), to: NSPoint(x: r.minX + radius, y: r.maxY), radius: radius)
        p.line(to: NSPoint(x: r.maxX, y: r.maxY))
    } else {
        p.move(to: NSPoint(x: r.minX, y: r.minY))
        p.line(to: NSPoint(x: r.maxX - radius, y: r.minY))
        p.appendArc(from: NSPoint(x: r.maxX, y: r.minY), to: NSPoint(x: r.maxX, y: r.minY + radius), radius: radius)
        p.line(to: NSPoint(x: r.maxX, y: r.maxY - radius))
        p.appendArc(from: NSPoint(x: r.maxX, y: r.maxY), to: NSPoint(x: r.maxX - radius, y: r.maxY), radius: radius)
        p.line(to: NSPoint(x: r.minX, y: r.maxY))
    }
    if closed { p.close() }
    return p
}

/// DarkroomColor 的 "#RRGGBB" → sRGB NSColor（Core 只放字串；spec §3.20）
private func hudColor(_ hex: String, alpha: CGFloat = 1) -> NSColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return .white }
    return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                   blue: CGFloat(v & 0xFF) / 255, alpha: alpha)
}

/// TypeToken → 系統字（數字等寬，計時不跳動；字型不打包）
private func hudFont(_ t: TypeToken) -> NSFont {
    let weight: NSFont.Weight
    switch t.weight {
    case "bold": weight = .bold
    case "semibold": weight = .semibold
    default: weight = .regular
    }
    return NSFont.monospacedDigitSystemFont(ofSize: CGFloat(t.size), weight: weight)
}

private func lineHeight(_ f: NSFont) -> CGFloat {
    f.ascender - f.descender + f.leading
}

private func hudSymbol(_ name: String, pointSize: CGFloat, color: String) -> NSImage? {
    let config = NSImage.SymbolConfiguration(pointSize: pointSize, weight: .regular)
        .applying(NSImage.SymbolConfiguration(paletteColors: [hudColor(color)]))
    let image = NSImage(systemSymbolName: name, accessibilityDescription: nil)?.withSymbolConfiguration(config)
    image?.isTemplate = false
    return image
}

// Trigger/FailureDetail.swift —— 失敗詳情小視窗（U6「錯誤詳情…」；spec §4.41.5）。
// 標準 NSWindow（.titled、.closable，寬 480、不可縮放，跟系統深淺色）；標題「錯誤詳情」。
// 依序顯示：message（rowTitle）、補救指令（monospacedSystemFont 12pt、可選取）、record.log 路徑（中間截斷）、
// 「複製完整訊息與補救指令」按鈕（複製內容＝MenuBarModel.detailText，同 spec §6 第 73 條）。
// ⌘W 與 Esc 關閉（沿用設定視窗的做法：app 沒有 main menu，自己接）。
// 畫面上不得顯示視窗標題與場次名：訊息與指令裡的場次路徑換成「〈場次資料夾〉」；複製的內容是完整原文。
import AppKit

/// 失敗詳情要顯示的內容（由 menu bar 從狀態檔與 MenuBarModel 組出來）
struct FailureDetailContent: Equatable {
    /// 完整訊息（MenuBarModel.detailText）；也是「複製」按鈕的內容
    var detailText: String
    /// 狀態檔的場次路徑（畫面上要遮掉；可為空）
    var sessionPath: String
    /// record.log 的完整路徑
    var logPath: String
}

/// 畫面上的文字：把場次路徑（與資料夾名）換成「〈場次資料夾〉」
func failureDetailRedacted(_ text: String, sessionPath: String) -> String {
    let session = sessionPath.hasSuffix("/") ? String(sessionPath.dropLast()) : sessionPath
    guard !session.isEmpty else { return text }
    var out = text.replacingOccurrences(of: session, with: "〈場次資料夾〉")
    let name = (session as NSString).lastPathComponent
    if !name.isEmpty, name != "/" { out = out.replacingOccurrences(of: name, with: "〈場次資料夾〉") }
    return out
}

/// 從完整訊息取出補救指令（`meeting record …` 起到該行結尾，去掉句尾的「重跑」）；沒有 → nil
func failureDetailRemedy(_ text: String) -> String? {
    for line in text.split(separator: "\n", omittingEmptySubsequences: true) {
        guard let r = line.range(of: "meeting record ") else { continue }
        var cmd = String(line[r.lowerBound...]).trimmingCharacters(in: .whitespaces)
        for tail in [" 重跑", "重跑", "。"] where cmd.hasSuffix(tail) {
            cmd = String(cmd.dropLast(tail.count)).trimmingCharacters(in: .whitespaces)
        }
        return cmd.isEmpty ? nil : cmd
    }
    return nil
}

private final class FailureDetailWindow: NSWindow {
    override func cancelOperation(_ sender: Any?) { performClose(sender) }
    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        // 注音等中文輸入法下 charactersIgnoringModifiers 不是 "w"：以實體鍵碼判斷（同設定視窗，§6 第 104 條）
        let mods = event.modifierFlags.intersection([.command, .shift, .option, .control])
        if mods == .command, event.keyCode == preferencesCloseKeyCode || event.charactersIgnoringModifiers == "w" {
            performClose(nil)
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

final class FailureDetailController: NSWindowController {
    private static let width: CGFloat = 480
    private let messageLabel = NSTextField(wrappingLabelWithString: "")
    private let remedyLabel = NSTextField(wrappingLabelWithString: "")
    private let logLabel = NSTextField(labelWithString: "")
    private let copyButton = NSButton(title: "複製完整訊息與補救指令", target: nil, action: nil)
    private var content = FailureDetailContent(detailText: "", sessionPath: "", logPath: "")

    init() {
        let window = FailureDetailWindow(contentRect: NSRect(x: 0, y: 0, width: Self.width, height: 200),
                                         styleMask: [.titled, .closable], backing: .buffered, defer: false)
        window.title = "錯誤詳情"
        window.isReleasedWhenClosed = false
        super.init(window: window)
        build()
    }

    required init?(coder: NSCoder) { nil }

    private func build() {
        let pad = CGFloat(DarkroomMetric.spacing[4])
        let textWidth = Self.width - pad * 2
        messageLabel.font = NSFont.systemFont(ofSize: CGFloat(DarkroomType.rowTitle.size),
                                              weight: DarkroomType.rowTitle.weight == "bold" ? .bold : .regular)
        messageLabel.isSelectable = true
        messageLabel.preferredMaxLayoutWidth = textWidth
        remedyLabel.font = NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        remedyLabel.isSelectable = true
        remedyLabel.preferredMaxLayoutWidth = textWidth
        logLabel.font = NSFont.systemFont(ofSize: CGFloat(DarkroomType.caption.size))
        logLabel.textColor = .secondaryLabelColor
        logLabel.lineBreakMode = .byTruncatingMiddle
        logLabel.isSelectable = true
        logLabel.cell?.truncatesLastVisibleLine = true
        copyButton.target = self
        copyButton.action = #selector(copyAll)
        copyButton.bezelStyle = .rounded
        copyButton.keyEquivalent = "\r"
        let stack = NSStackView(views: [messageLabel, remedyLabel, logLabel, copyButton])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = CGFloat(DarkroomMetric.spacing[2])
        stack.edgeInsets = NSEdgeInsets(top: pad, left: pad, bottom: pad, right: pad)
        stack.translatesAutoresizingMaskIntoConstraints = false
        for v in [messageLabel, remedyLabel, logLabel] {
            v.widthAnchor.constraint(equalToConstant: textWidth).isActive = true
        }
        let root = NSView()
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            stack.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            stack.topAnchor.constraint(equalTo: root.topAnchor),
            stack.bottomAnchor.constraint(equalTo: root.bottomAnchor),
            root.widthAnchor.constraint(equalToConstant: Self.width),
        ])
        window?.contentView = root
    }

    /// 已開就更新內容並帶到前面，不開第二個
    func present(_ c: FailureDetailContent) {
        content = c
        let shown = failureDetailRedacted(c.detailText, sessionPath: c.sessionPath)
        messageLabel.stringValue = shown.isEmpty ? "沒有錯誤訊息" : shown
        if let remedy = failureDetailRemedy(c.detailText) {
            remedyLabel.stringValue = failureDetailRedacted(remedy, sessionPath: c.sessionPath)
            remedyLabel.isHidden = false
        } else {
            remedyLabel.isHidden = true
        }
        let log = (c.logPath as NSString).abbreviatingWithTildeInPath
        logLabel.stringValue = "記錄檔：\(log)"
        logLabel.toolTip = log
        window?.contentView?.layoutSubtreeIfNeeded()
        if let fitting = window?.contentView?.fittingSize { window?.setContentSize(fitting) }
        if window?.isVisible != true { window?.center() }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    @objc private func copyAll() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(content.detailText, forType: .string)
    }
}

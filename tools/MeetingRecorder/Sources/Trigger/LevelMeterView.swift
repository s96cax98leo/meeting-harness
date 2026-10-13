// Trigger/LevelMeterView.swift —— 選單的即時音量條（U6-A；spec §4.41.4；design-r3/README.md §4）。
// 自訂 view（menuMeterWidth × 44）：兩行「系統」「麥克風」，標籤寬 meterLabelWidth、字 menuMeterLabel，條高 meterBarHeight；
// 長度＝levelFraction(dBFS:)；顏色一律取自 Core 的 DarkroomColor（深色：軌道 line、系統 text、麥克風 done；
// 淺色：軌道 lineOnLight、系統 textOnLight、麥克風 doneOnLight）。靜音時麥克風那行改「已靜音」字。
// 由 MenuBar.swift 每 levelMeterRefreshSeconds 更新；不可聚焦（選單的鍵盤導覽直接跳過）。
import AppKit

final class LevelMeterView: NSView {
    static let height: CGFloat = 44

    private var system: Double?
    private var mic: Double?
    private var muted = false

    init() {
        super.init(frame: NSRect(x: 0, y: 0, width: CGFloat(DarkroomMetric.menuMeterWidth), height: Self.height))
        setAccessibilityElement(true)
        setAccessibilityRole(.levelIndicator)
        setAccessibilityLabel("收音")
        updateAccessibility()
    }

    required init?(coder: NSCoder) { nil }

    override var isFlipped: Bool { true }
    override var acceptsFirstResponder: Bool { false }
    override var canBecomeKeyView: Bool { false }
    override var intrinsicContentSize: NSSize {
        NSSize(width: CGFloat(DarkroomMetric.menuMeterWidth), height: Self.height)
    }

    /// system／mic＝最近視窗的 dBFS（nil＝還沒有值）；muted＝麥克風靜音中
    func update(system: Double?, mic: Double?, muted: Bool) {
        guard system != self.system || mic != self.mic || muted != self.muted else { return }
        self.system = system
        self.mic = mic
        self.muted = muted
        updateAccessibility()
        needsDisplay = true
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        needsDisplay = true
    }

    /// 「系統聲音 有聲／無聲；麥克風 有聲／無聲／已靜音」；門檻沿用 levelIndicatorLine 的 -60 dBFS（嚴格大於）
    private func updateAccessibility() {
        func mark(_ v: Double?) -> String {
            if let v, v > -60 { return "有聲" }
            return "無聲"
        }
        setAccessibilityValue("系統聲音 \(mark(system))；麥克風 \(muted ? "已靜音" : mark(mic))")
    }

    override func draw(_ dirtyRect: NSRect) {
        let dark = meterIsDark(effectiveAppearance)
        typealias C = DarkroomColor
        let track = meterColor(dark ? C.line : C.lineOnLight)
        let systemColor = meterColor(dark ? C.text : C.textOnLight)
        let micColor = meterColor(dark ? C.done : C.doneOnLight)
        let font = NSFont.systemFont(ofSize: CGFloat(DarkroomType.menuMeterLabel.size),
                                     weight: meterFontWeight(DarkroomType.menuMeterLabel.weight))
        // 標籤字色：選單是系統 NSMenu、跟系統深淺色，用 labelColor（與標題列一致）
        let attrs: [NSAttributedString.Key: Any] = [.font: font, .foregroundColor: NSColor.labelColor]
        let inset = CGFloat(DarkroomMetric.spacing[3])
        let labelW = CGFloat(DarkroomMetric.meterLabelWidth)
        let barH = CGFloat(DarkroomMetric.meterBarHeight)
        let rowH = bounds.height / 2
        let barX = inset + labelW
        let barW = max(0, bounds.width - barX - inset)
        let rows: [(String, Double?, NSColor, Bool)] = [("系統", system, systemColor, false),
                                                       ("麥克風", mic, micColor, muted)]
        for (i, row) in rows.enumerated() {
            let y = CGFloat(i) * rowH
            let label = row.0 as NSString
            let size = label.size(withAttributes: attrs)
            label.draw(at: NSPoint(x: inset, y: y + (rowH - size.height) / 2), withAttributes: attrs)
            if row.3 {
                let text = "已靜音" as NSString
                let ts = text.size(withAttributes: attrs)
                text.draw(at: NSPoint(x: barX, y: y + (rowH - ts.height) / 2), withAttributes: attrs)
                continue
            }
            let barY = y + (rowH - barH) / 2
            track.setFill()
            NSBezierPath(roundedRect: NSRect(x: barX, y: barY, width: barW, height: barH),
                         xRadius: barH / 2, yRadius: barH / 2).fill()
            let fraction = CGFloat(levelFraction(dBFS: row.1))
            if fraction > 0 {
                row.2.setFill()
                NSBezierPath(roundedRect: NSRect(x: barX, y: barY, width: barW * fraction, height: barH),
                             xRadius: barH / 2, yRadius: barH / 2).fill()
            }
        }
    }
}

// MARK: - 小工具（與 MenuBar.swift 的同名工具各自 private，避免跨檔名稱衝突）

private func meterColor(_ hex: String) -> NSColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return .labelColor }
    return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                   blue: CGFloat(v & 0xFF) / 255, alpha: 1)
}

private func meterFontWeight(_ w: String) -> NSFont.Weight {
    switch w {
    case "bold": return .bold
    case "semibold": return .semibold
    default: return .regular
    }
}

private func meterIsDark(_ a: NSAppearance) -> Bool {
    let match = a.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
    return match == .darkAqua || match == .accessibilityHighContrastDarkAqua
}

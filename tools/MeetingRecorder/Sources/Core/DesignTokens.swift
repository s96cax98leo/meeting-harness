// Core/DesignTokens.swift —— 設計語言「暗房」的色、字級、尺寸 token，WCAG 對比計算，選單列膠囊樣式表
// （spec §3.20、§4.38.5、§4.38.6、§4.38.8；design-r3/README.md §1–§2；design.md R3-D21）。
// 色值一律 "#RRGGBB" 大寫字串；AppKit 端由這裡取值，不得自己寫色值或用系統色取代。不依賴 AppKit。
import Foundation

enum DarkroomColor {
    static let ink = "#0F1115", surface = "#171A21", raised = "#1F232C", light = "#F6F5F2", line = "#2A2F3A", lineStrong = "#3A404D"
    static let text = "#ECEEF2", textSecondary = "#C3C9D4", textTertiary = "#9AA3B2", textDisabled = "#5B6372"
    static let recording = "#FF4D4F", attention = "#F5A524", processing = "#8B7CF6", done = "#2DD4BF"
    static let recordingText = "#FF6B6E", attentionText = "#F7C46C", processingText = "#B9AEFF", doneText = "#5EE6D2"
    static let onAttention = "#1A1206", mutedSegment = "#1A0B0C", onSignal = "#FFFFFF", iconStroke = "#2E333E"
    static let menuBarDark = "#1E2129", menuBarLight = "#E9E7E2", textOnLight = "#1A1C21", lineOnLight = "#C9C6BF"
    static let recordingOnLight = "#D92D30", processingOnLight = "#6D5BD0", processingTextOnLight = "#5E4BC4"
    static let failedTextOnLight = "#B42318", attentionTextOnLight = "#8A5A00", doneOnLight = "#0F766E"
    static let recordingHighContrast = "#CC2F32", recordingHighContrastOnLight = "#C42B2E"

    /// 以上 34 個 token：名稱 → 值。
    static var all: [String: String] {
        [
            "ink": ink, "surface": surface, "raised": raised, "light": light, "line": line, "lineStrong": lineStrong,
            "text": text, "textSecondary": textSecondary, "textTertiary": textTertiary, "textDisabled": textDisabled,
            "recording": recording, "attention": attention, "processing": processing, "done": done,
            "recordingText": recordingText, "attentionText": attentionText, "processingText": processingText, "doneText": doneText,
            "onAttention": onAttention, "mutedSegment": mutedSegment, "onSignal": onSignal, "iconStroke": iconStroke,
            "menuBarDark": menuBarDark, "menuBarLight": menuBarLight, "textOnLight": textOnLight, "lineOnLight": lineOnLight,
            "recordingOnLight": recordingOnLight, "processingOnLight": processingOnLight,
            "processingTextOnLight": processingTextOnLight,
            "failedTextOnLight": failedTextOnLight, "attentionTextOnLight": attentionTextOnLight, "doneOnLight": doneOnLight,
            "recordingHighContrast": recordingHighContrast, "recordingHighContrastOnLight": recordingHighContrastOnLight,
        ]
    }
}

/// 字級 token；weight ∈ "regular"、"semibold"、"bold"。
struct TypeToken: Equatable { var size: Double; var weight: String }

enum DarkroomType {
    static let capsule = TypeToken(size: 14, weight: "bold"), hudTabTimer = TypeToken(size: 13, weight: "semibold")
    static let hudTimer = TypeToken(size: 18, weight: "semibold"), hudLabel = TypeToken(size: 13, weight: "regular")
    static let hudButton = TypeToken(size: 12, weight: "regular"), hudAlert = TypeToken(size: 12, weight: "bold")
    static let menuMeterLabel = TypeToken(size: 12, weight: "regular"), onboardingTitle = TypeToken(size: 26, weight: "bold")
    static let onboardingBody = TypeToken(size: 15, weight: "regular"), rowTitle = TypeToken(size: 15, weight: "bold")
    static let rowDetail = TypeToken(size: 13, weight: "regular"), button = TypeToken(size: 14, weight: "bold")
    static let stepLabel = TypeToken(size: 12, weight: "regular"), settingsTabLabel = TypeToken(size: 12, weight: "regular")
    static let settingsRowLabel = TypeToken(size: 14, weight: "regular"), caption = TypeToken(size: 12, weight: "regular")
}

enum DarkroomMetric {
    static let spacing: [Double] = [4, 8, 12, 16, 24]
    static let capsuleHeight: Double = 20, capsulePaddingH: Double = 10, capsuleGap: Double = 6, capsuleDot: Double = 8, capsuleBorder: Double = 1.5
    static let muteSegmentPaddingLeading: Double = 9, muteSegmentPaddingTrailing: Double = 7, badgeDiameter: Double = 7, badgeStroke: Double = 1.5
    static let hudTabWidth: Double = 34, hudTabHeight: Double = 120, hudTabCornerRadius: Double = 14, hudTabDot: Double = 10, hudTabTopFraction: Double = 0.25
    static let hudPanelWidth: Double = 230, hudPanelPadding: Double = 16, hudPanelCornerRadius: Double = 16
    static let hudButtonHeight: Double = 44, hudButtonCornerRadius: Double = 10, hudButtonGap: Double = 6
    static let meterBarHeight: Double = 5, meterLabelWidth: Double = 40, menuMeterWidth: Double = 240
    static let onboardingWidth: Double = 620, onboardingHeight: Double = 560, onboardingPaddingH: Double = 32, onboardingPaddingV: Double = 28
    static let rowPaddingH: Double = 16, rowPaddingV: Double = 14, rowCornerRadius: Double = 14, rowGap: Double = 10
    static let buttonHeight: Double = 44, buttonCornerRadius: Double = 12, settingsWidth: Double = 600, settingsTabWidth: Double = 76
}

/// "#RRGGBB" → (r, g, b) 0–255；格式不對 → nil。
private func hexRGB(_ s: String) -> (Double, Double, Double)? {
    let u = Array(s.utf8)
    guard u.count == 7, u[0] == UInt8(ascii: "#") else { return nil }
    var vals: [Double] = []
    for i in stride(from: 1, to: 7, by: 2) {
        guard let hi = hexDigit(u[i]), let lo = hexDigit(u[i + 1]) else { return nil }
        vals.append(Double(hi * 16 + lo))
    }
    return (vals[0], vals[1], vals[2])
}

private func hexDigit(_ c: UInt8) -> Int? {
    switch c {
    case UInt8(ascii: "0")...UInt8(ascii: "9"): return Int(c - UInt8(ascii: "0"))
    case UInt8(ascii: "A")...UInt8(ascii: "F"): return Int(c - UInt8(ascii: "A")) + 10
    case UInt8(ascii: "a")...UInt8(ascii: "f"): return Int(c - UInt8(ascii: "a")) + 10
    default: return nil
    }
}

/// WCAG 2.x 相對亮度（design-r3/README.md §1.4）。
private func relativeLuminance(_ rgb: (Double, Double, Double)) -> Double {
    func ch(_ v: Double) -> Double {
        let c = v / 255
        return c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * ch(rgb.0) + 0.7152 * ch(rgb.1) + 0.0722 * ch(rgb.2)
}

/// WCAG 2.x 對比值 (L亮 + 0.05) / (L暗 + 0.05)；任一不是 #RRGGBB → 0。
func contrastRatio(_ a: String, _ b: String) -> Double {
    guard let ra = hexRGB(a), let rb = hexRGB(b) else { return 0 }
    let la = relativeLuminance(ra), lb = relativeLuminance(rb)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)
}

enum CapsuleShape: String, Equatable { case templateSymbol, outline, filled, split }
enum CapsuleGlyph: String, Equatable { case none, dot, pause, micSlash }

struct CapsuleStyle: Equatable {
    var shape: CapsuleShape
    var glyph: CapsuleGlyph
    var label: String
    var showsTimer: Bool
    var fill: String?
    var border: String?
    var borderWidth: Double
    var text: String?
    var badge: Bool
    var largeText: Bool
}

/// 選單列膠囊樣式表（spec §4.38.5；U1-C）。dark＝選單列深色外觀；increaseContrast＝系統「增加對比」。
func menuBarCapsuleStyle(_ a: MenuBarAppearance, alertBadge: Bool, dark: Bool, increaseContrast: Bool) -> CapsuleStyle {
    typealias C = DarkroomColor
    let ic = increaseContrast
    func style(_ shape: CapsuleShape, _ glyph: CapsuleGlyph, _ label: String, timer: Bool, fill: String? = nil,
               border: String? = nil, borderWidth: Double = 0, text: String? = nil, badge: Bool = false,
               largeText: Bool = false) -> CapsuleStyle {
        CapsuleStyle(shape: shape, glyph: glyph, label: label, showsTimer: timer, fill: fill, border: border,
                     borderWidth: borderWidth, text: text, badge: badge, largeText: largeText)
    }
    let recordingFill: String
    switch (dark, ic) {
    case (true, false): recordingFill = C.recording
    case (false, false): recordingFill = C.recordingOnLight
    case (true, true): recordingFill = C.recordingHighContrast
    case (false, true): recordingFill = C.recordingHighContrastOnLight
    }
    switch a {
    case .idle:
        return style(.templateSymbol, .none, "", timer: false)
    case .preparing:
        return style(.outline, .none, "檢查中", timer: false, border: dark ? C.processing : C.processingTextOnLight,
                     borderWidth: 1.5, text: dark ? C.processingText : C.processingTextOnLight)
    case .recording:
        return style(.filled, .dot, "", timer: true, fill: recordingFill, text: C.onSignal, largeText: dark && !ic)
    case .recordingMuted:
        return style(.split, .micSlash, "", timer: true, fill: recordingFill, border: recordingFill, borderWidth: 1,
                     text: C.onSignal, largeText: dark && !ic)
    case .recordingAlert:
        return style(.filled, .dot, "", timer: true, fill: recordingFill, border: C.attention, borderWidth: 1.5,
                     text: C.onSignal, badge: true, largeText: dark && !ic)
    case .paused:
        return style(.filled, .pause, "", timer: true, fill: C.attention, border: dark ? nil : C.attentionTextOnLight,
                     borderWidth: dark ? 0 : 1, text: C.onAttention, badge: alertBadge, largeText: false)
    case .finalizing:
        let fill: String
        switch (dark, ic) {
        case (true, false): fill = C.processing
        case (false, false): fill = C.processingOnLight
        case (true, true): fill = C.processingOnLight
        case (false, true): fill = C.processingTextOnLight
        }
        return style(.filled, .none, "收尾中", timer: false, fill: fill, text: C.onSignal, largeText: dark && !ic)
    case .failed:
        return style(.outline, .none, "需處理", timer: false, border: dark ? C.recording : C.failedTextOnLight,
                     borderWidth: 1.5, text: dark ? C.recordingText : C.failedTextOnLight)
    }
}

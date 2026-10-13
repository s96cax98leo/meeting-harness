// spec §3.20（Core/DesignTokens.swift、Core/Appearance.swift、Core/Settings.swift）、design-r3/README.md §1–§2：設計語言「暗房」。
// 驗收：§4.38.5（膠囊樣式表）、§4.38.6（對比與形狀可分）、§4.38.7（VoiceOver 字面）、§4.38.8（token 值）、
// §4.41.4（levelFraction）、§4.43.6（SettingsTab）。
// 閘門 2（2026-10-13）：疑慮 52 採 (a)——膠囊字 14pt bold，淺色列與「增加對比」用深一階底色；字型不打包。
import Foundation

let mrtR3DesignTokenTests: [MRTCase] = [
    ("testColorTokens", testColorTokens),
    ("testTypeAndMetricTokens", testTypeAndMetricTokens),
    ("testContrastRatio", testContrastRatio),
    ("testCapsuleStyleTable", testCapsuleStyleTable),
    ("testCapsuleContrast", testCapsuleContrast),
    ("testCapsuleShapesDistinct", testCapsuleShapesDistinct),
    ("testMenuBarAccessibilityLabel", testMenuBarAccessibilityLabel),
    ("testLevelFraction", testLevelFraction),
    ("testSettingsTabs", testSettingsTabs),
]

/// §3.20 的 34 個色 token（名稱 → 值）。
let mrtR3ExpectedColors: [String: String] = [
    "ink": "#0F1115", "surface": "#171A21", "raised": "#1F232C", "light": "#F6F5F2", "line": "#2A2F3A", "lineStrong": "#3A404D",
    "text": "#ECEEF2", "textSecondary": "#C3C9D4", "textTertiary": "#9AA3B2", "textDisabled": "#5B6372",
    "recording": "#FF4D4F", "attention": "#F5A524", "processing": "#8B7CF6", "done": "#2DD4BF",
    "recordingText": "#FF6B6E", "attentionText": "#F7C46C", "processingText": "#B9AEFF", "doneText": "#5EE6D2",
    "onAttention": "#1A1206", "mutedSegment": "#1A0B0C", "onSignal": "#FFFFFF", "iconStroke": "#2E333E",
    "menuBarDark": "#1E2129", "menuBarLight": "#E9E7E2", "textOnLight": "#1A1C21", "lineOnLight": "#C9C6BF",
    "recordingOnLight": "#D92D30", "processingOnLight": "#6D5BD0", "processingTextOnLight": "#5E4BC4",
    "failedTextOnLight": "#B42318", "attentionTextOnLight": "#8A5A00", "doneOnLight": "#0F766E",
    "recordingHighContrast": "#CC2F32", "recordingHighContrastOnLight": "#C42B2E",
]

// §4.38.8：DarkroomColor 34 項、格式、逐一相等。
func testColorTokens() throws {
    let all = DarkroomColor.all
    mrtEqual(all.count, 34, "DarkroomColor.all 恰為 34 項")
    mrtEqual(all, mrtR3ExpectedColors, "名稱與值逐一相等")
    let re = try NSRegularExpression(pattern: "^#[0-9A-F]{6}$")
    for (k, v) in all {
        let ok = re.firstMatch(in: v, range: NSRange(v.startIndex..., in: v)) != nil
        mrtExpect(ok, "\(k)＝\(v) 應符合 ^#[0-9A-F]{6}$")
    }
    // 靜態成員與 all 一致（抽樣每一行）
    let members: [(String, String)] = [
        ("ink", DarkroomColor.ink), ("surface", DarkroomColor.surface), ("raised", DarkroomColor.raised),
        ("light", DarkroomColor.light), ("line", DarkroomColor.line), ("lineStrong", DarkroomColor.lineStrong),
        ("text", DarkroomColor.text), ("textSecondary", DarkroomColor.textSecondary), ("textTertiary", DarkroomColor.textTertiary),
        ("textDisabled", DarkroomColor.textDisabled), ("recording", DarkroomColor.recording), ("attention", DarkroomColor.attention),
        ("processing", DarkroomColor.processing), ("done", DarkroomColor.done), ("recordingText", DarkroomColor.recordingText),
        ("attentionText", DarkroomColor.attentionText), ("processingText", DarkroomColor.processingText),
        ("doneText", DarkroomColor.doneText), ("onAttention", DarkroomColor.onAttention), ("mutedSegment", DarkroomColor.mutedSegment),
        ("onSignal", DarkroomColor.onSignal), ("iconStroke", DarkroomColor.iconStroke), ("menuBarDark", DarkroomColor.menuBarDark),
        ("menuBarLight", DarkroomColor.menuBarLight), ("textOnLight", DarkroomColor.textOnLight),
        ("lineOnLight", DarkroomColor.lineOnLight), ("recordingOnLight", DarkroomColor.recordingOnLight),
        ("processingOnLight", DarkroomColor.processingOnLight), ("processingTextOnLight", DarkroomColor.processingTextOnLight),
        ("failedTextOnLight", DarkroomColor.failedTextOnLight), ("attentionTextOnLight", DarkroomColor.attentionTextOnLight),
        ("doneOnLight", DarkroomColor.doneOnLight), ("recordingHighContrast", DarkroomColor.recordingHighContrast),
        ("recordingHighContrastOnLight", DarkroomColor.recordingHighContrastOnLight),
    ]
    mrtEqual(members.count, 34, "成員數")
    for (k, v) in members {
        mrtEqual(v, mrtR3ExpectedColors[k], "DarkroomColor.\(k)")
        mrtEqual(all[k], v, "DarkroomColor.all[\"\(k)\"] 與成員一致")
    }
}

// §4.38.8：DarkroomType、DarkroomMetric 每個成員等於 §3.20；spacing 都是 4 的倍數。
func testTypeAndMetricTokens() throws {
    let types: [(String, TypeToken, TypeToken)] = [
        ("capsule", DarkroomType.capsule, TypeToken(size: 14, weight: "bold")),
        ("hudTabTimer", DarkroomType.hudTabTimer, TypeToken(size: 13, weight: "semibold")),
        ("hudTimer", DarkroomType.hudTimer, TypeToken(size: 18, weight: "semibold")),
        ("hudLabel", DarkroomType.hudLabel, TypeToken(size: 13, weight: "regular")),
        ("hudButton", DarkroomType.hudButton, TypeToken(size: 12, weight: "regular")),
        ("hudAlert", DarkroomType.hudAlert, TypeToken(size: 12, weight: "bold")),
        ("menuMeterLabel", DarkroomType.menuMeterLabel, TypeToken(size: 12, weight: "regular")),
        ("onboardingTitle", DarkroomType.onboardingTitle, TypeToken(size: 26, weight: "bold")),
        ("onboardingBody", DarkroomType.onboardingBody, TypeToken(size: 15, weight: "regular")),
        ("rowTitle", DarkroomType.rowTitle, TypeToken(size: 15, weight: "bold")),
        ("rowDetail", DarkroomType.rowDetail, TypeToken(size: 13, weight: "regular")),
        ("button", DarkroomType.button, TypeToken(size: 14, weight: "bold")),
        ("stepLabel", DarkroomType.stepLabel, TypeToken(size: 12, weight: "regular")),
        ("settingsTabLabel", DarkroomType.settingsTabLabel, TypeToken(size: 12, weight: "regular")),
        ("settingsRowLabel", DarkroomType.settingsRowLabel, TypeToken(size: 14, weight: "regular")),
        ("caption", DarkroomType.caption, TypeToken(size: 12, weight: "regular")),
    ]
    for (k, got, want) in types {
        mrtEqual(got, want, "DarkroomType.\(k)")
        mrtExpect(["regular", "semibold", "bold"].contains(got.weight), "DarkroomType.\(k) 的 weight＝\(got.weight)")
    }

    mrtEqual(DarkroomMetric.spacing, [4, 8, 12, 16, 24], "spacing")
    for v in DarkroomMetric.spacing { mrtExpect(v.truncatingRemainder(dividingBy: 4) == 0, "spacing \(v) 應為 4 的倍數") }
    let metrics: [(String, Double, Double)] = [
        ("capsuleHeight", DarkroomMetric.capsuleHeight, 20), ("capsulePaddingH", DarkroomMetric.capsulePaddingH, 10),
        ("capsuleGap", DarkroomMetric.capsuleGap, 6), ("capsuleDot", DarkroomMetric.capsuleDot, 8),
        ("capsuleBorder", DarkroomMetric.capsuleBorder, 1.5),
        ("muteSegmentPaddingLeading", DarkroomMetric.muteSegmentPaddingLeading, 9),
        ("muteSegmentPaddingTrailing", DarkroomMetric.muteSegmentPaddingTrailing, 7),
        ("badgeDiameter", DarkroomMetric.badgeDiameter, 7), ("badgeStroke", DarkroomMetric.badgeStroke, 1.5),
        ("hudTabWidth", DarkroomMetric.hudTabWidth, 34), ("hudTabHeight", DarkroomMetric.hudTabHeight, 120),
        ("hudTabCornerRadius", DarkroomMetric.hudTabCornerRadius, 14), ("hudTabDot", DarkroomMetric.hudTabDot, 10),
        ("hudTabTopFraction", DarkroomMetric.hudTabTopFraction, 0.25),
        ("hudPanelWidth", DarkroomMetric.hudPanelWidth, 230), ("hudPanelPadding", DarkroomMetric.hudPanelPadding, 16),
        ("hudPanelCornerRadius", DarkroomMetric.hudPanelCornerRadius, 16),
        ("hudButtonHeight", DarkroomMetric.hudButtonHeight, 44), ("hudButtonCornerRadius", DarkroomMetric.hudButtonCornerRadius, 10),
        ("hudButtonGap", DarkroomMetric.hudButtonGap, 6),
        ("meterBarHeight", DarkroomMetric.meterBarHeight, 5), ("meterLabelWidth", DarkroomMetric.meterLabelWidth, 40),
        ("menuMeterWidth", DarkroomMetric.menuMeterWidth, 240),
        ("onboardingWidth", DarkroomMetric.onboardingWidth, 620), ("onboardingHeight", DarkroomMetric.onboardingHeight, 560),
        ("onboardingPaddingH", DarkroomMetric.onboardingPaddingH, 32), ("onboardingPaddingV", DarkroomMetric.onboardingPaddingV, 28),
        ("rowPaddingH", DarkroomMetric.rowPaddingH, 16), ("rowPaddingV", DarkroomMetric.rowPaddingV, 14),
        ("rowCornerRadius", DarkroomMetric.rowCornerRadius, 14), ("rowGap", DarkroomMetric.rowGap, 10),
        ("buttonHeight", DarkroomMetric.buttonHeight, 44), ("buttonCornerRadius", DarkroomMetric.buttonCornerRadius, 12),
        ("settingsWidth", DarkroomMetric.settingsWidth, 600), ("settingsTabWidth", DarkroomMetric.settingsTabWidth, 76),
    ]
    for (k, got, want) in metrics { mrtEqual(got, want, "DarkroomMetric.\(k)") }
}

// §4.38.6 (e)：contrastRatio 的公式與非法輸入。
func testContrastRatio() throws {
    mrtExpect(abs(contrastRatio("#FFFFFF", "#000000") - 21) < 0.01, "白對黑＝21（實際 \(contrastRatio("#FFFFFF", "#000000"))）")
    mrtExpect(abs(contrastRatio("#000000", "#FFFFFF") - 21) < 0.01, "順序不影響")
    mrtExpect(abs(contrastRatio("#FFFFFF", "#FF4D4F") - 3.27) < 0.01, "白對 recording＝3.27（實際 \(contrastRatio("#FFFFFF", "#FF4D4F"))）")
    mrtEqual(contrastRatio("x", "#000000"), 0, "不是 #RRGGBB → 0")
    mrtEqual(contrastRatio("#000000", "#12345"), 0, "長度不對 → 0")
    mrtEqual(contrastRatio("#GG0000", "#000000"), 0, "非十六進位 → 0")
    mrtExpect(abs(contrastRatio("#1E2129", "#1E2129") - 1) < 0.0001, "同色＝1")
}

/// §4.38.5 的期望（只列 spec 寫明的欄；nil＝spec 沒規定，不比）。
struct MRTCapsuleExpect {
    var shape: CapsuleShape; var glyph: CapsuleGlyph; var label: String; var showsTimer: Bool
    var fill: String??; var border: String??; var borderWidth: Double?; var text: String??
    var badge: Bool?; var largeText: Bool?
}

func mrtR3CapsuleExpect(_ a: MenuBarAppearance, alertBadge: Bool, dark: Bool, ic: Bool) -> MRTCapsuleExpect {
    let C = mrtR3ExpectedColors
    switch a {
    case .idle:
        return MRTCapsuleExpect(shape: .templateSymbol, glyph: .none, label: "", showsTimer: false, fill: .some(nil), border: .some(nil),
                                borderWidth: 0, text: .some(nil), badge: false, largeText: false)
    case .preparing:
        let c = dark ? C["processing"]! : C["processingTextOnLight"]!
        let t = dark ? C["processingText"]! : C["processingTextOnLight"]!
        return MRTCapsuleExpect(shape: .outline, glyph: .none, label: "檢查中", showsTimer: false, fill: .some(nil), border: .some(c),
                                borderWidth: 1.5, text: .some(t), badge: nil, largeText: nil)
    case .recording, .recordingMuted, .recordingAlert:
        let fill: String
        switch (dark, ic) {
        case (true, false): fill = C["recording"]!
        case (false, false): fill = C["recordingOnLight"]!
        case (true, true): fill = C["recordingHighContrast"]!
        case (false, true): fill = C["recordingHighContrastOnLight"]!
        }
        var e = MRTCapsuleExpect(shape: .filled, glyph: .dot, label: "", showsTimer: true, fill: .some(fill), border: .some(nil),
                                 borderWidth: 0, text: .some(C["onSignal"]!), badge: false, largeText: dark && !ic)
        if a == .recordingMuted {
            e.shape = .split; e.glyph = .micSlash; e.border = .some(fill); e.borderWidth = 1
        } else if a == .recordingAlert {
            e.border = .some(C["attention"]!); e.borderWidth = 1.5; e.badge = true
        }
        return e
    case .paused:
        return MRTCapsuleExpect(shape: .filled, glyph: .pause, label: "", showsTimer: true, fill: .some(C["attention"]!),
                                border: .some(dark ? nil : C["attentionTextOnLight"]!), borderWidth: dark ? 0 : 1,
                                text: .some(C["onAttention"]!), badge: alertBadge, largeText: false)
    case .finalizing:
        let fill: String
        switch (dark, ic) {
        case (true, false): fill = C["processing"]!
        case (false, false): fill = C["processingOnLight"]!
        case (true, true): fill = C["processingOnLight"]!
        case (false, true): fill = C["processingTextOnLight"]!
        }
        return MRTCapsuleExpect(shape: .filled, glyph: .none, label: "收尾中", showsTimer: false, fill: .some(fill), border: nil,
                                borderWidth: nil, text: .some(C["onSignal"]!), badge: nil, largeText: dark && !ic)
    case .failed:
        let c = dark ? C["recording"]! : C["failedTextOnLight"]!
        let t = dark ? C["recordingText"]! : C["failedTextOnLight"]!
        return MRTCapsuleExpect(shape: .outline, glyph: .none, label: "需處理", showsTimer: false, fill: .some(nil), border: .some(c),
                                borderWidth: 1.5, text: .some(t), badge: nil, largeText: nil)
    }
}

// §4.38.5：menuBarCapsuleStyle 逐欄對表（8 外觀 × 深淺 × 增對比；paused 另取 alertBadge true）。
func testCapsuleStyleTable() throws {
    for a in MenuBarAppearance.allCases {
        for dark in [true, false] {
            for ic in [false, true] {
                for badge in (a == .paused ? [false, true] : [false]) {
                    let s = menuBarCapsuleStyle(a, alertBadge: badge, dark: dark, increaseContrast: ic)
                    let e = mrtR3CapsuleExpect(a, alertBadge: badge, dark: dark, ic: ic)
                    let tag = "\(a.rawValue) dark=\(dark) ic=\(ic) alertBadge=\(badge)"
                    mrtEqual(s.shape, e.shape, "\(tag) shape")
                    mrtEqual(s.glyph, e.glyph, "\(tag) glyph")
                    mrtEqual(s.label, e.label, "\(tag) label")
                    mrtEqual(s.showsTimer, e.showsTimer, "\(tag) showsTimer")
                    if let f = e.fill { mrtEqual(s.fill, f, "\(tag) fill") }
                    if let b = e.border { mrtEqual(s.border, b, "\(tag) border") }
                    if let w = e.borderWidth { mrtEqual(s.borderWidth, w, "\(tag) borderWidth") }
                    if let t = e.text { mrtEqual(s.text, t, "\(tag) text") }
                    if let b = e.badge { mrtEqual(s.badge, b, "\(tag) badge") }
                    if let l = e.largeText { mrtEqual(s.largeText, l, "\(tag) largeText") }
                }
            }
        }
    }
    mrtEqual(CapsuleShape.templateSymbol.rawValue, "templateSymbol")
    mrtEqual(CapsuleGlyph.micSlash.rawValue, "micSlash")
}

// §4.38.6 (a)–(c)：7 種非待機外觀 × 深淺 × 增對比 × alertBadge 的對比門檻。
func testCapsuleContrast() throws {
    for a in MenuBarAppearance.allCases where a != .idle {
        for dark in [true, false] {
            let bar = dark ? DarkroomColor.menuBarDark : DarkroomColor.menuBarLight
            for ic in [false, true] {
                for badge in [false, true] {
                    let s = menuBarCapsuleStyle(a, alertBadge: badge, dark: dark, increaseContrast: ic)
                    let tag = "\(a.rawValue) dark=\(dark) ic=\(ic) alertBadge=\(badge)"
                    // (a) 文字對比
                    if let text = s.text {
                        let r = contrastRatio(text, s.fill ?? bar)
                        let need = s.largeText ? 3.0 : 4.5
                        mrtExpect(r >= need, "\(tag)：文字對比 \(r) < \(need)")
                    } else if !s.label.isEmpty || s.showsTimer {
                        mrtFail("\(tag)：有字但 text 為 nil", file: #fileID, line: #line)
                    }
                    if ic { mrtEqual(s.largeText, false, "\(tag)：增對比時 largeText 必為 false") }
                    // (b) 外形對比
                    let shape = max(s.fill.map { contrastRatio($0, bar) } ?? 0, s.border.map { contrastRatio($0, bar) } ?? 0)
                    mrtExpect(shape >= 3.0, "\(tag)：外形對比 \(shape) < 3.0")
                    // (c) 角標
                    if s.badge {
                        let b = max(contrastRatio(DarkroomColor.attention, bar), contrastRatio(DarkroomColor.onAttention, bar))
                        mrtExpect(b >= 3.0, "\(tag)：角標對比 \(b) < 3.0")
                    }
                }
            }
        }
    }
}

// §4.38.6 (d)：8 種外觀（shape, glyph, label, showsTimer, badge）兩兩不同；paused 帶 alertBadge 也和其他 7 種不同。
func testCapsuleShapesDistinct() throws {
    struct Key: Hashable { let shape: String; let glyph: String; let label: String; let timer: Bool; let badge: Bool }
    func key(_ s: CapsuleStyle) -> Key {
        Key(shape: s.shape.rawValue, glyph: s.glyph.rawValue, label: s.label, timer: s.showsTimer, badge: s.badge)
    }
    for dark in [true, false] {
        for ic in [false, true] {
            var seen: [Key: MenuBarAppearance] = [:]
            for a in MenuBarAppearance.allCases {
                let k = key(menuBarCapsuleStyle(a, alertBadge: false, dark: dark, increaseContrast: ic))
                if let other = seen[k] {
                    mrtFail("dark=\(dark) ic=\(ic)：\(a.rawValue) 與 \(other.rawValue) 只靠顏色才分得出來", file: #fileID, line: #line)
                }
                seen[k] = a
            }
            let pb = key(menuBarCapsuleStyle(.paused, alertBadge: true, dark: dark, increaseContrast: ic))
            for (k, a) in seen where a != .paused {
                mrtExpect(k != pb, "dark=\(dark) ic=\(ic)：paused（alertBadge）與 \(a.rawValue) 相同")
            }
        }
    }
}

// §4.38.7：menuBarAccessibilityLabel 的字面。
func testMenuBarAccessibilityLabel() throws {
    let spoken = "已錄 12 分 34 秒"
    let alert = "麥克風已連續 15 秒幾乎沒有聲音"
    let st = "錄製中 12:34・[Stand-up] 範例專案"
    func l(_ a: MenuBarAppearance, badge: Bool = false, alertText: String? = nil, status: String = st) -> String {
        menuBarAccessibilityLabel(appearance: a, alertBadge: badge, spoken: spoken, alertText: alertText, status: status)
    }
    mrtEqual(l(.idle), "MeetingRecorder：待機中")
    mrtEqual(l(.preparing), "MeetingRecorder：開錄前檢查中")
    mrtEqual(l(.recording), "MeetingRecorder：錄製中，已錄 12 分 34 秒")
    mrtEqual(l(.recordingMuted), "MeetingRecorder：錄製中，已錄 12 分 34 秒，麥克風靜音")
    mrtEqual(l(.recordingAlert, alertText: alert), "MeetingRecorder：錄製中，已錄 12 分 34 秒，有告警：麥克風已連續 15 秒幾乎沒有聲音")
    mrtEqual(l(.recordingAlert, alertText: nil), "MeetingRecorder：錄製中，已錄 12 分 34 秒，有告警", "alertText nil")
    mrtEqual(l(.paused), "MeetingRecorder：已暫停，已錄 12 分 34 秒")
    mrtEqual(l(.paused, badge: true), "MeetingRecorder：已暫停，已錄 12 分 34 秒，有告警", "paused＋alertBadge")
    mrtEqual(l(.finalizing), "MeetingRecorder：收尾中")
    mrtEqual(l(.failed, status: "開錄前檢查沒過"), "MeetingRecorder：需要處理：開錄前檢查沒過")
}

// §4.41.4：levelFraction＝clamp((dBFS + 60) / 60, 0, 1)；nil → 0；每 0.5 秒更新。
func testLevelFraction() throws {
    let cases: [(Double?, Double)] = [(nil, 0), (-90, 0), (-60, 0), (-30, 0.5), (0, 1), (6, 1)]
    for (db, want) in cases {
        mrtNear(levelFraction(dBFS: db), want, tol: 1e-9, "dBFS \(String(describing: db))")
    }
    mrtEqual(levelMeterRefreshSeconds, 0.5, "levelMeterRefreshSeconds")
}

// §4.43.6：SettingsTab 7 個分頁的順序、title、symbolName；settingsTab("x") → .general。
func testSettingsTabs() throws {
    let want: [(SettingsTab, String, String, String)] = [
        (.general, "general", "一般", "gearshape"),
        (.recording, "recording", "錄製", "record.circle"),
        (.feedback, "feedback", "回饋與通知", "bell.badge"),
        (.hotkeys, "hotkeys", "快捷鍵", "command"),
        (.afterRecording, "afterRecording", "錄完之後", "checkmark.circle"),
        (.permissions, "permissions", "權限", "lock.shield"),
        (.advanced, "advanced", "進階", "slider.horizontal.3"),
    ]
    mrtEqual(SettingsTab.allCases, want.map { $0.0 }, "7 個分頁與順序")
    for (tab, raw, title, symbol) in want {
        mrtEqual(tab.rawValue, raw, "\(raw) rawValue")
        mrtEqual(tab.title, title, "\(raw) title")
        mrtEqual(tab.symbolName, symbol, "\(raw) symbolName")
        mrtEqual(settingsTab(raw), tab, "settingsTab(\"\(raw)\")")
    }
    mrtEqual(settingsTab("x"), SettingsTab.general, "不認得 → .general")
    mrtEqual(settingsTab(""), SettingsTab.general, "空字串 → .general")
}

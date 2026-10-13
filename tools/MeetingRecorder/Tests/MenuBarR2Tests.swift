// spec §3.13、§3.14、§3.14.1（menuBarModel 的 R2 規則：M6b 與 M7／M9 的 R2 欄位）：Control.swift 的 menu bar 側名稱與 Trigger.swift 增補。
// 驗收：§4.20.2、§4.20.3、§4.20.5、§4.20.7、§4.21.1、§4.21.2、§4.22.1、§4.22.3、§4.23.1。
// 第一輪 TriggerTests.swift 不改；本檔沿用其 mrtStatus／mrtNow／mrtMenuRows／mrtSessionName（pid 4242、場次名「範例週會」）。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation

let mrtMenuBarR2Tests: [MRTCase] = [
    ("testMenuBarR2Rows", testMenuBarR2Rows),
    ("testLevelIndicator", testLevelIndicator),
    ("testHotKeySpecs", testHotKeySpecs),
    ("testTriggerDebouncer", testTriggerDebouncer),
    ("testQuickStartRootAndExplicitWindow", testQuickStartRootAndExplicitWindow),
    ("testUpdatedRecentRoots", testUpdatedRecentRoots),
    ("testMenuBarPrefsFile", testMenuBarPrefsFile),
    ("testLaunchMode", testLaunchMode),
    ("testLoginItemDisplay", testLoginItemDisplay),
    ("testShouldAutoPrep", testShouldAutoPrep),
    ("testNotificationIDs", testNotificationIDs),
]

/// 錄製中狀態，加上 R2 欄位（recordingStartedAt＝now − startedAgo 秒；pausedAt＝now − pausedAgo 秒）。
func mrtR2Recording(now: Date, startedAgo: Double, pausedSeconds: Double, pausedAgo: Double? = nil,
                    controlVersion: Int? = 1, micMuted: Bool? = nil, recent: RecentLevels? = nil,
                    warnings: [RecordWarning] = []) -> RecordStatus {
    var s = mrtStatus(.recording, warnings: warnings)
    s.controlVersion = controlVersion
    s.recordingStartedAt = mrtR2ISO(now.addingTimeInterval(-startedAgo))
    s.pausedSeconds = pausedSeconds
    if let pausedAgo {
        s.paused = true
        s.pausedAt = mrtR2ISO(now.addingTimeInterval(-pausedAgo))
    } else {
        s.paused = false
    }
    s.micMuted = micMuted
    s.recentLevels = recent
    return s
}

// §4.20.2、§3.14.1：M6b、M9 計時、R2 欄位、raw value、accessibilityText。
func testMenuBarR2Rows() throws {
    let now = mrtNow(500)   // startedAt（preflight 開始）在 500 秒前；計時應改用 recordingStartedAt

    // (a) M6b：暫停中
    let a = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10),
                         pidAlive: true, now: now)
    mrtEqual(a.state, MenuBarState.paused, "(a) state")
    mrtEqual(MenuBarState.paused.rawValue, "paused")
    mrtEqual(a.symbolName, "pause.circle.fill", "(a) symbolName")
    mrtContains(a.statusLine, "已暫停", "(a)")
    mrtContains(a.statusLine, "01:10", "(a) 計時＝100 − 20 − 10")
    mrtContains(a.statusLine, mrtSessionName, "(a) 場次名")
    mrtEqual(a.timerText, "01:10", "(a) timerText")
    mrtEqual(a.canStop, true, "(a) canStop")
    mrtEqual(a.canStart, false, "(a) canStart")
    mrtEqual(a.canOpenSession, true, "(a) canOpenSession")
    mrtEqual(a.canControl, true, "(a) canControl")
    mrtEqual(a.paused, true, "(a) paused")
    mrtEqual(a.levelLine, "收音：暫停中", "(a) levelLine")
    mrtExpect(a.accessibilityText.hasPrefix("MeetingRecorder："), "(a) paused 態 accessibilityText 應以「MeetingRecorder：」開頭")
    mrtEqual(a.accessibilityText, "MeetingRecorder：" + a.statusLine)

    // (b) 同 (a) 再加 2 則告警類 warning → 仍為 paused（M6b 先於 M7）
    let b = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 100, pausedSeconds: 20, pausedAgo: 10,
                                                warnings: [mrtAlertOld, mrtAlertNew, mrtRecordOnly]),
                         pidAlive: true, now: now)
    mrtEqual(b.state, MenuBarState.paused, "(b) 舊告警不得蓋掉暫停狀態")
    mrtContains(b.statusLine, "（告警 2 則）", "(b)")
    mrtContains(b.statusLine, "已暫停", "(b)")

    // (c) M9：計時＝recordedSeconds
    let c = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5), pidAlive: true, now: now)
    mrtEqual(c.state, MenuBarState.recording, "(c) state")
    mrtContains(c.statusLine, "錄製中 02:00", "(c)")
    mrtEqual(c.timerText, "02:00", "(c) timerText")
    mrtEqual(c.paused, false, "(c) paused")
    mrtEqual(c.canControl, true, "(c) canControl")

    // (d) M9 且 micMuted
    let d = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, micMuted: true,
                                                recent: RecentLevels(windowSeconds: 3, system: -30, mic: nil)),
                         pidAlive: true, now: now)
    mrtContains(d.statusLine, "麥克風靜音中", "(d)")
    mrtEqual(d.micMuted, true, "(d) micMuted")
    mrtContains(d.levelLine, "⊘ 已靜音", "(d) levelLine")
    mrtEqual(d.levelLine, levelIndicatorLine(recent: RecentLevels(windowSeconds: 3, system: -30, mic: nil),
                                             micMuted: true, paused: false, thresholdDBFS: -60), "(d) levelLine 照 levelIndicatorLine")

    // (e) M7：recording、有告警 → timerText 非空、canControl 依 controlVersion
    let e1 = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, warnings: [mrtAlertNew]),
                          pidAlive: true, now: now)
    mrtEqual(e1.state, MenuBarState.warning, "(e) M7")
    mrtEqual(e1.timerText, "02:00", "(e) timerText 非空且與計時相同")
    mrtEqual(e1.canControl, true, "(e) controlVersion 1 → canControl true")
    let e2 = menuBarModel(status: mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5, controlVersion: nil,
                                                 warnings: [mrtAlertNew]),
                          pidAlive: true, now: now)
    mrtExpect(!e2.timerText.isEmpty, "(e) controlVersion nil 時 timerText 仍非空")
    mrtEqual(e2.canControl, false, "(e) controlVersion nil → canControl false")

    // (f) 第一輪格式的狀態（沒有 R2 鍵）：沿用 now − startedAt
    let f = menuBarModel(status: mrtStatus(.recording), pidAlive: true, now: mrtNow(125))
    mrtEqual(f.canControl, false, "(f) canControl")
    mrtEqual(f.timerText, "02:05", "(f) timerText 等於經過時間")
    mrtContains(f.statusLine, f.timerText, "(f) statusLine 含同一個計時")
    mrtEqual(f.levelLine, "收音：讀取中…", "(f) recentLevels nil → 讀取中")

    // (g) M1–M6、M6a、M8、M10（以及 phase 不是 recording 的 M7）→ R2 五個欄位皆為預設值；
    //     就算狀態檔帶了 R2 欄位也一樣
    for r in mrtMenuRows {
        let recordingAlive = r.status?.phase == .recording && r.pidAlive
        if recordingAlive { continue }
        var st = r.status
        if st != nil {
            st!.controlVersion = 1
            st!.recordingStartedAt = mrtStartedAt
            st!.paused = true
            st!.pausedSeconds = 1
            st!.pausedAt = mrtStartedAt
            st!.micMuted = true
            st!.recentLevels = RecentLevels(windowSeconds: 3, system: -20, mic: -20)
        }
        for s in [r.status, st] {
            let m = menuBarModel(status: s, pidAlive: r.pidAlive, now: r.now)
            mrtEqual(m.state, r.state, "(g) \(r.row) 第一輪 state 不變")
            mrtEqual(m.timerText, "", "(g) \(r.row) timerText")
            mrtEqual(m.paused, false, "(g) \(r.row) paused")
            mrtEqual(m.micMuted, false, "(g) \(r.row) micMuted")
            mrtEqual(m.canControl, false, "(g) \(r.row) canControl")
            mrtEqual(m.levelLine, "", "(g) \(r.row) levelLine")
        }
    }

    // (h) 全表 12 列的 statusLine 不含 raw value
    let kindCodes: [String] = [WarningKind.silenceSystem, .silenceMic, .black, .suspended, .diskLow, .deviceChange,
                               .audioFormatChange, .segmentWriteFailed].map { $0.rawValue }
    let phaseCodes: [String] = [RecordPhase.preflight, .preflightFailed, .recording, .stopping, .finalizing, .done,
                                .failed].map { $0.rawValue }
    let commandCodes: [String] = ControlCommand.allCases.map { $0.rawValue }
    let pauseKindCodes: [String] = [PauseEventKind.pause.rawValue, PauseEventKind.resume.rawValue]
    var codes: [String] = kindCodes
    codes += phaseCodes
    codes += commandCodes
    codes += pauseKindCodes
    let models = mrtMenuRows.map { mrtModel($0) } + [a, b, c, d, e1, e2, f]
    for m in models {
        for code in codes { mrtExpect(!m.statusLine.contains(code), "(h) statusLine 含內部代碼 \(code)：\(m.statusLine)") }
    }
}

// §4.20.3：recentPeak、levelIndicatorLine（thresholdDBFS -60、嚴格大於）。
func testLevelIndicator() throws {
    mrtEqual(recentPeak([-70, nil, -50.5], count: 6), -50.5)
    mrtEqual(recentPeak([nil, nil], count: 6), nil)
    mrtEqual(recentPeak([], count: 6), nil)
    mrtEqual(recentPeak([-10, -80, -80, -80, -80, -80, -80], count: 6), -80, "只取最後 6 個")

    func line(_ sys: Double?, _ mic: Double?, muted: Bool = false, paused: Bool = false, nilRecent: Bool = false) -> String {
        levelIndicatorLine(recent: nilRecent ? nil : RecentLevels(windowSeconds: 3, system: sys, mic: mic),
                           micMuted: muted, paused: paused, thresholdDBFS: -60)
    }
    mrtEqual(line(-30, -30, paused: true), "收音：暫停中")
    mrtEqual(line(nil, nil, paused: true, nilRecent: true), "收音：暫停中", "paused 先於 recent nil")
    mrtEqual(line(nil, nil, nilRecent: true), "收音：讀取中…")
    mrtEqual(line(-30, -70), "收音：系統聲音 ● 有聲\u{3000}麥克風 ○ 無聲")
    mrtEqual(line(-30, -70), "收音：系統聲音 ● 有聲　麥克風 ○ 無聲")
    mrtEqual(line(-60.0, -30), "收音：系統聲音 ○ 無聲　麥克風 ● 有聲", "等於門檻算無聲（嚴格大於）")
    mrtEqual(line(-30, nil), "收音：系統聲音 ● 有聲　麥克風 ○ 無聲", "mic nil → 無聲")
    mrtEqual(line(-30, -20, muted: true), "收音：系統聲音 ● 有聲　麥克風 ⊘ 已靜音")
    mrtEqual(line(-30, nil, muted: true), "收音：系統聲音 ● 有聲　麥克風 ⊘ 已靜音")
}

// §4.20.5：r2HotKeys 恰為 4 筆、id 1–4 不重複。
func testHotKeySpecs() throws {
    mrtEqual(r2HotKeys, [HotKeySpec(id: 1, key: "r", action: "start", display: "⌃⌥⌘R"),
                         HotKeySpec(id: 2, key: "m", action: "mute", display: "⌃⌥⌘M"),
                         HotKeySpec(id: 3, key: "p", action: "pause", display: "⌃⌥⌘P"),
                         HotKeySpec(id: 4, key: "b", action: "mark", display: "⌃⌥⌘B")])
    mrtEqual(r2HotKeys.count, 4)
    mrtEqual(Set(r2HotKeys.map { $0.id }), Set<UInt32>([1, 2, 3, 4]), "id 1–4 不重複")
    mrtEqual(r2HotKeys.map { $0.display }, ["⌃⌥⌘R", "⌃⌥⌘M", "⌃⌥⌘P", "⌃⌥⌘B"])
}

// §4.20.7：TriggerDebouncer(interval: 1.0)。
func testTriggerDebouncer() throws {
    var d = TriggerDebouncer(interval: 1.0)
    mrtEqual(d.accept("mark", at: 0), true)
    mrtEqual(d.accept("mark", at: 0.5), false)
    mrtEqual(d.accept("pause", at: 0.5), true, "不同 action 互不影響")
    mrtEqual(d.accept("mark", at: 1.0), true)
    mrtEqual(d.accept("mark", at: 1.5), false, "距上次被接受 0.5")
}

// §4.21.1：quickStartRoot、explicitWindowDecision。
func testQuickStartRootAndExplicitWindow() throws {
    let yes: (String) -> Bool = { _ in true }
    mrtEqual(quickStartRoot(argRoot: "/a", prefsRoot: "/b", defaultsRoot: "/c", isDirectory: yes), RootChoice.use("/a"))
    mrtEqual(quickStartRoot(argRoot: nil, prefsRoot: "/b", defaultsRoot: "/c", isDirectory: yes), RootChoice.use("/b"))
    mrtEqual(quickStartRoot(argRoot: "", prefsRoot: nil, defaultsRoot: "/c", isDirectory: yes), RootChoice.use("/c"))
    func fail(_ c: RootChoice) -> (Int32, String)? { if case .fail(let code, let m) = c { return (code, m) }; return nil }
    let none = fail(quickStartRoot(argRoot: nil, prefsRoot: nil, defaultsRoot: nil, isDirectory: yes))
    mrtEqual(none?.0, Int32(2), "都沒有 → fail(2)")
    mrtContains(none?.1 ?? "", "先在終端機跑一次 meeting record")
    let missingPath = "/Users/範例/Documents/[Stand-up] 範例專案"
    let missing = fail(quickStartRoot(argRoot: nil, prefsRoot: missingPath, defaultsRoot: "/c",
                                      isDirectory: { $0 != missingPath }))
    mrtEqual(missing?.0, Int32(2), "取到的路徑不是目錄 → fail(2)")
    mrtContains(missing?.1 ?? "", "存檔位置不存在")
    mrtContains(missing?.1 ?? "", missingPath)

    func code(_ d: QuickStartDecision) -> Int32? { if case .fail(let c, _) = d { return c }; return nil }
    func message(_ d: QuickStartDecision) -> String { if case .fail(_, let m) = d { return m }; return "" }
    let noDefaults = explicitWindowDecision(hasDefaults: false, resolution: WindowResolution.exact(7))
    mrtEqual(code(noDefaults), Int32(2), "hasDefaults false → fail(2)")
    mrtEqual(message(noDefaults), message(quickStartDecision(hasDefaults: false, starredWindowIDs: [7])),
             "與 quickStartDecision 相同的訊息")
    mrtEqual(explicitWindowDecision(hasDefaults: true, resolution: WindowResolution.exact(7)), QuickStartDecision.start(windowID: 7))
    mrtEqual(explicitWindowDecision(hasDefaults: true, resolution: WindowResolution.reidentified(9)), QuickStartDecision.start(windowID: 9))
    let nf = explicitWindowDecision(hasDefaults: true, resolution: WindowResolution.notFound)
    mrtEqual(code(nf), Int32(3))
    mrtContains(message(nf), "選的視窗已經不在了")
    let amb = explicitWindowDecision(hasDefaults: true, resolution: WindowResolution.ambiguous)
    mrtEqual(code(amb), Int32(3))
    mrtContains(message(amb), "同名")
}

// §4.21.1：updatedRecentRoots(limit: 5)。
func testUpdatedRecentRoots() throws {
    mrtEqual(updatedRecentRoots(["/a", "/b"], adding: "/c", limit: 5), ["/c", "/a", "/b"])
    mrtEqual(updatedRecentRoots(["/a", "/b", "/c"], adding: "/b/", limit: 5), ["/b", "/a", "/c"], "結尾 / 去掉後比、不重複")
    let six = ["/a", "/b", "/c", "/d", "/e", "/f"]
    let r = updatedRecentRoots(six, adding: "/g", limit: 5)
    mrtEqual(r.count, 5, "恰 5 項")
    mrtEqual(r.first, "/g", "新項在最前")
    mrtEqual(r, ["/g", "/a", "/b", "/c", "/d"])
    mrtEqual(updatedRecentRoots(["/a"], adding: "/", limit: 5).first, "/", "\"/\" 本身不去掉")
    mrtEqual(updatedRecentRoots(["/a", "/b"], adding: "", limit: 5), ["/a", "/b"], "空字串 → 原樣")
}

// §4.21.2、§3.13：loadMenuBarPrefs／saveMenuBarPrefs。
func testMenuBarPrefsFile() throws {
    mrtEqual(menuBarPrefsFileName, "menubar.prefs.json")
    let fm = FileManager.default
    let dir = mrtR2TempDir("prefs")
    defer { try? fm.removeItem(at: dir) }
    let defaults = MenuBarPrefs(schemaVersion: 1, root: nil, recentRoots: [], autoPrep: false,
                                lastSession: nil, lastAutoPrepRunId: nil)
    mrtEqual(loadMenuBarPrefs(dir.appendingPathComponent("menubar.prefs.json")), defaults, "不存在 → 預設值")
    try fm.createDirectory(at: dir, withIntermediateDirectories: true)
    let broken = dir.appendingPathComponent("broken.json")
    try Data("{".utf8).write(to: broken)
    mrtEqual(loadMenuBarPrefs(broken), defaults, "內容為 { → 預設值")
    try fm.removeItem(at: broken)

    let url = dir.appendingPathComponent("menubar.prefs.json")
    try saveMenuBarPrefs(defaults, to: url)
    let obj = (try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]) ?? [:]
    mrtEqual(Set(obj.keys), ["schemaVersion", "root", "recentRoots", "autoPrep", "lastSession", "lastAutoPrepRunId"],
             "JSON 鍵恰為 6 個")
    mrtExpect(mrtIsNull(obj["root"]) && mrtIsNull(obj["lastSession"]) && mrtIsNull(obj["lastAutoPrepRunId"]), "nil 寫 null")
    mrtEqual(loadMenuBarPrefs(url), defaults, "往返相等（預設值）")

    let full = MenuBarPrefs(schemaVersion: 1, root: "/Users/範例/Documents/範例專案",
                            recentRoots: ["/Users/範例/Documents/範例專案", "/tmp/範例根"], autoPrep: true,
                            lastSession: "/Users/範例/Documents/範例專案/20261012/[Stand-up] 範例專案",
                            lastAutoPrepRunId: "00000000-0000-4000-8000-000000000001")
    try saveMenuBarPrefs(full, to: url)
    mrtEqual(loadMenuBarPrefs(url), full, "往返相等（有值）")
    mrtEqual(try fm.contentsOfDirectory(atPath: dir.path), ["menubar.prefs.json"], "目錄不留 tmp 檔")
}

// §4.22.1：launchMode。
func testLaunchMode() throws {
    mrtEqual(launchMode(arguments: []), "menubar")
    mrtEqual(launchMode(arguments: ["-psn_0_12345"]), "menubar")
    mrtEqual(launchMode(arguments: ["help"]), "help")
    mrtEqual(launchMode(arguments: ["--help"]), "--help")
    mrtEqual(launchMode(arguments: ["quick-start", "--home", "/x"]), "quick-start")
    mrtEqual(launchMode(arguments: ["-psn_0_1", "windows"]), "windows")
}

// §4.22.3：loginItemDisplay。
func testLoginItemDisplay() throws {
    mrtEqual(LoginItemState.allCases.count, 4)
    mrtEqual(loginItemDisplay(LoginItemState.enabled), LoginItemDisplay(isOn: true, note: "", showOpenSettings: false))
    mrtEqual(loginItemDisplay(LoginItemState.notRegistered), LoginItemDisplay(isOn: false, note: "", showOpenSettings: false))
    let ra = loginItemDisplay(LoginItemState.requiresApproval)
    mrtEqual(ra.isOn, true)
    mrtContains(ra.note, "系統設定")
    mrtContains(ra.note, "登入項目")
    mrtEqual(ra.showOpenSettings, true)
    let nf = loginItemDisplay(LoginItemState.notFound)
    mrtEqual(nf.isOn, false)
    mrtContains(nf.note, "找不到")
    mrtEqual(nf.showOpenSettings, false)
}

// §4.23.1：shouldAutoPrep。
func testShouldAutoPrep() throws {
    func st(_ phase: RecordPhase = .done, code: Int32 = 0, runId: String = "a", session: String = "/s") -> RecordStatus {
        var s = mrtStatus(phase, code: code)
        s.runId = runId
        s.session = session
        return s
    }
    let seen: Set<String> = ["a"]
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(), seenInProgressRunIds: seen, lastAutoPrepRunId: nil), "/s")
    mrtEqual(shouldAutoPrep(autoPrep: false, status: st(), seenInProgressRunIds: seen, lastAutoPrepRunId: nil), nil, "autoPrep false")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(code: 5), seenInProgressRunIds: seen, lastAutoPrepRunId: nil), nil, "code 5")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(.finalizing), seenInProgressRunIds: seen, lastAutoPrepRunId: nil), nil,
             "phase finalizing")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(), seenInProgressRunIds: [], lastAutoPrepRunId: nil), nil, "seen 不含 a")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(), seenInProgressRunIds: seen, lastAutoPrepRunId: "a"), nil, "last a")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: st(session: ""), seenInProgressRunIds: seen, lastAutoPrepRunId: nil), nil,
             "session 空")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: nil, seenInProgressRunIds: seen, lastAutoPrepRunId: nil), nil, "status nil")
}

// §4.23.1、§3.13：通知識別碼。
func testNotificationIDs() throws {
    mrtEqual(completionNotificationID(runId: "a"), "mh.complete.a")
    mrtEqual(completionCategoryID, "mh.complete")
    mrtEqual(revealActionID, "mh.reveal")
}

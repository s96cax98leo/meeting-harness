// spec §3.4.1（menuBarModel 對映表 M1–M10 加 M6a 共 11 列，唯一正本）、§4.11.1、§4.11.2、§4.11.5–§4.11.8、§4.11.10：Trigger.swift。
// 每個案例的註解標明對應的表列（M1…M10、M6a）。
// M6a（D17）：spec §6 第 41 條的測試例外——使用者核准把原「M7：stopping、有告警類 → warning」案例改為 M6a 的預期；
// 其餘既有預期不得放寬。
import Foundation

let mrtTriggerTests: [MRTCase] = [
    ("testMenuBarStateMapping", testMenuBarStateMapping),
    ("testRecordOnlyWarningsDoNotAlert", testRecordOnlyWarningsDoNotAlert),
    ("testSymbolNames", testSymbolNames),
    ("testMenuItemAvailability", testMenuItemAvailability),
    ("testStopAvailabilityByPhase", testStopAvailabilityByPhase),
    ("testStatusLineHumanReadable", testStatusLineHumanReadable),
    ("testQuickStartDecision", testQuickStartDecision),
    ("testAccessibilityTextPrefix", testAccessibilityTextPrefix),
    ("testTruncatedStatusTitle", testTruncatedStatusTitle),
    ("testMenuBarLockSingleInstance", testMenuBarLockSingleInstance),
    ("testFinalizeFailureStatusLineShort", testFinalizeFailureStatusLineShort),
    ("testPreflightWarnNotification", testPreflightWarnNotification),
]

let mrtStartedAt = "2026-10-11T10:00:00+08:00"
let mrtSession = "/tmp/範例根/20261011/範例週會"
let mrtSessionName = "範例週會"

func mrtDate(_ iso: String) -> Date { ISO8601DateFormatter().date(from: iso)! }
/// now ＝ startedAt ＋ seconds
func mrtNow(_ seconds: Double) -> Date { mrtDate(mrtStartedAt).addingTimeInterval(seconds) }

func mrtStatus(_ phase: RecordPhase, code: Int32 = 0, message: String = "",
               warnings: [RecordWarning] = []) -> RecordStatus {
    RecordStatus(schemaVersion: 1, runId: "00000000-0000-4000-8000-000000000002", pid: 4242, phase: phase,
                 code: code, message: message, session: mrtSession, startedAt: mrtStartedAt,
                 updatedAt: mrtStartedAt, segments: 0, preflight: [], warnings: warnings)
}

/// spec §3.4.1 的一列：輸入、期望 state、statusLine 必須包含的片段、三個 can* 欄。
struct MRTRow {
    let row: String
    let status: RecordStatus?
    let pidAlive: Bool
    let now: Date
    let state: MenuBarState
    let mustContain: [String]
    let canStart: Bool, canStop: Bool, canOpenSession: Bool
}

let mrtAlertOld = RecordWarning(t: 30, kind: .silenceSystem, message: "系統聲音已連續 15 秒沒有聲音")
let mrtAlertNew = RecordWarning(t: 95, kind: .silenceMic, message: "麥克風已連續 15 秒沒有聲音，請檢查麥克風")
let mrtRecordOnly = RecordWarning(t: 120, kind: .deviceChange, message: "輸入裝置已切換為藍牙耳機")
let mrtAlertMicAgain = RecordWarning(t: 150, kind: .silenceMic, message: "麥克風又連續 15 秒沒有聲音")

/// spec §3.4.1 全表 11 列（M1–M10 與 M6a）的案例（每列至少一個；M2 涵蓋 code 2、3、4；
/// M6a 涵蓋 stopping 與 finalizing，且至少一案告警數 N ≥ 2）。
let mrtMenuRows: [MRTRow] = [
    // M1：status == nil → idle、「待機」
    MRTRow(row: "M1", status: nil, pidAlive: false, now: mrtNow(0), state: .idle,
           mustContain: ["待機"], canStart: true, canStop: false, canOpenSession: false),
    // M2：phase == preflight_failed、code 2 → warning、「開錄前檢查沒通過」＋訊息首行
    MRTRow(row: "M2", status: mrtStatus(.preflightFailed, code: 2, message: "同名場次已存在\n請換一個場次名"),
           pidAlive: false, now: mrtNow(5), state: .warning,
           mustContain: ["開錄前檢查沒通過", "同名場次已存在"], canStart: true, canStop: false, canOpenSession: false),
    // M2：code 3
    MRTRow(row: "M2", status: mrtStatus(.preflightFailed, code: 3, message: "找不到要錄的視窗\n請重新選擇"),
           pidAlive: false, now: mrtNow(5), state: .warning,
           mustContain: ["開錄前檢查沒通過", "找不到要錄的視窗"], canStart: true, canStop: false, canOpenSession: false),
    // M2：code 4（pid 仍活著也一樣，preflight_failed 不算進行中）
    MRTRow(row: "M2", status: mrtStatus(.preflightFailed, code: 4, message: "沒有螢幕錄製權限\n系統設定 › 隱私權與安全性"),
           pidAlive: true, now: mrtNow(5), state: .warning,
           mustContain: ["開錄前檢查沒通過", "沒有螢幕錄製權限"], canStart: true, canStop: false, canOpenSession: false),
    // M3：phase == failed → warning、「錄製失敗」＋訊息首行
    MRTRow(row: "M3", status: mrtStatus(.failed, code: 5, message: "擷取串流中斷\n已落盤段落保留"),
           pidAlive: false, now: mrtNow(300), state: .warning,
           mustContain: ["錄製失敗", "擷取串流中斷"], canStart: true, canStop: false, canOpenSession: true),
    // M4：phase == done 且 code != 0 → warning、「錄製失敗」＋訊息首行
    MRTRow(row: "M4", status: mrtStatus(.done, code: 5, message: "收尾失敗\n可執行 meeting record finish"),
           pidAlive: false, now: mrtNow(300), state: .warning,
           mustContain: ["錄製失敗", "收尾失敗"], canStart: true, canStop: false, canOpenSession: true),
    // M5：phase == done 且 code == 0 → idle、「待機」
    MRTRow(row: "M5", status: mrtStatus(.done, code: 0, message: "完成"),
           pidAlive: false, now: mrtNow(300), state: .idle,
           mustContain: ["待機"], canStart: true, canStop: false, canOpenSession: true),
    // M6：進行中（recording）且 pidAlive == false → warning、「異常中止」＋「meeting record finish」
    MRTRow(row: "M6", status: mrtStatus(.recording), pidAlive: false, now: mrtNow(300), state: .warning,
           mustContain: ["異常中止", "meeting record finish"], canStart: true, canStop: false, canOpenSession: true),
    // M6：進行中（finalizing）且 pid 已死；有告警類也不影響（M6 先於 M7）
    MRTRow(row: "M6", status: mrtStatus(.finalizing, warnings: [mrtAlertNew]), pidAlive: false, now: mrtNow(300),
           state: .warning, mustContain: ["異常中止", "meeting record finish"],
           canStart: true, canStop: false, canOpenSession: true),
    // M7：recording、pid 活著、有告警類 → warning、最新告警（t 最大）的 message；canStop == (phase == recording)
    MRTRow(row: "M7", status: mrtStatus(.recording, warnings: [mrtAlertOld, mrtAlertNew, mrtRecordOnly]),
           pidAlive: true, now: mrtNow(125), state: .warning,
           mustContain: [mrtAlertNew.message], canStart: false, canStop: true, canOpenSession: true),
    // M6a（D17；spec §6 第 41 條核准把原「M7：stopping、有告警類 → warning」改為此預期）：
    // stopping、pid 活著、有告警類 → recording、「收尾中…（告警 N 則）」，N＝告警類項數（此案 N＝2）
    MRTRow(row: "M6a", status: mrtStatus(.stopping, warnings: [mrtAlertNew, mrtAlertOld]),
           pidAlive: true, now: mrtNow(125), state: .recording,
           mustContain: ["收尾中…", "（告警 2 則）"], canStart: false, canStop: false, canOpenSession: true),
    // M6a：finalizing、pid 活著、告警類 1 則（N＝1）
    MRTRow(row: "M6a", status: mrtStatus(.finalizing, warnings: [mrtAlertNew]),
           pidAlive: true, now: mrtNow(200), state: .recording,
           mustContain: ["收尾中…", "（告警 1 則）"], canStart: false, canStop: false, canOpenSession: true),
    // M6a：finalizing；告警數不去重（同 kind 兩則都算），紀錄類 warning 不計入 → N＝3
    MRTRow(row: "M6a", status: mrtStatus(.finalizing, warnings: [mrtAlertOld, mrtAlertNew, mrtRecordOnly, mrtAlertMicAgain]),
           pidAlive: true, now: mrtNow(200), state: .recording,
           mustContain: ["收尾中…", "（告警 3 則）"], canStart: false, canStop: false, canOpenSession: true),
    // M7：preflight、pid 活著、有告警類 → warning、最新告警；canStop false（M6a 先於 M7，M7 只在 preflight／recording 成立）
    MRTRow(row: "M7", status: mrtStatus(.preflight, warnings: [mrtAlertNew, mrtAlertOld]),
           pidAlive: true, now: mrtNow(10), state: .warning,
           mustContain: [mrtAlertNew.message], canStart: false, canStop: false, canOpenSession: true),
    // M8：preflight、pid 活著、無告警類 → recording、「開錄前檢查中」
    MRTRow(row: "M8", status: mrtStatus(.preflight), pidAlive: true, now: mrtNow(2), state: .recording,
           mustContain: ["開錄前檢查中"], canStart: false, canStop: false, canOpenSession: true),
    // M9：recording、pid 活著、無告警類 → recording、「錄製中」＋經過時間 mm:ss＋場次名
    MRTRow(row: "M9", status: mrtStatus(.recording), pidAlive: true, now: mrtNow(125), state: .recording,
           mustContain: ["錄製中", "02:05", mrtSessionName], canStart: false, canStop: true, canOpenSession: true),
    // M9：≥ 60 分鐘時 h:mm:ss
    MRTRow(row: "M9", status: mrtStatus(.recording), pidAlive: true, now: mrtNow(3725), state: .recording,
           mustContain: ["錄製中", "1:02:05", mrtSessionName], canStart: false, canStop: true, canOpenSession: true),
    // M10：stopping、pid 活著、無告警類 → recording、「收尾中…」
    MRTRow(row: "M10", status: mrtStatus(.stopping), pidAlive: true, now: mrtNow(200), state: .recording,
           mustContain: ["收尾中…"], canStart: false, canStop: false, canOpenSession: true),
    // M10：finalizing
    MRTRow(row: "M10", status: mrtStatus(.finalizing), pidAlive: true, now: mrtNow(200), state: .recording,
           mustContain: ["收尾中…"], canStart: false, canStop: false, canOpenSession: true),
]

func mrtModel(_ r: MRTRow) -> MenuBarModel { menuBarModel(status: r.status, pidAlive: r.pidAlive, now: r.now) }

// §4.11.2：全表 11 列（M1–M10 與 M6a）的 state 與 statusLine；preflight_failed 歸告警態並顯示訊息首行。
func testMenuBarStateMapping() throws {
    let covered = Set(mrtMenuRows.map { $0.row })
    mrtEqual(covered, Set((1...10).map { "M\($0)" } + ["M6a"]), "全表 11 列（M1–M10 與 M6a）每列至少一個案例")
    let m2Codes = Set(mrtMenuRows.filter { $0.row == "M2" }.compactMap { $0.status?.code })
    mrtEqual(m2Codes, Set([Int32(2), 3, 4]), "M2 涵蓋 code 2、3、4")
    // M6a（D17）：涵蓋 stopping 與 finalizing，且至少一案告警數 N ≥ 2
    let m6a = mrtMenuRows.filter { $0.row == "M6a" }
    mrtEqual(Set(m6a.compactMap { $0.status?.phase }), Set([RecordPhase.stopping, .finalizing]), "M6a 涵蓋 stopping、finalizing")
    mrtExpect(m6a.contains { ($0.status?.warnings.filter { $0.kind.isAlert }.count ?? 0) >= 2 }, "M6a 至少一案 N ≥ 2")
    for r in mrtMenuRows {
        let m = mrtModel(r)
        mrtEqual(m.state, r.state, "\(r.row) \(r.status?.phase.rawValue ?? "nil")")
        for part in r.mustContain { mrtContains(m.statusLine, part, r.row) }
    }
    // M2 的三種 code 都是 warning
    for c in [Int32(2), 3, 4] {
        mrtEqual(menuBarModel(status: mrtStatus(.preflightFailed, code: c, message: "檢查沒通過"), pidAlive: false,
                              now: mrtNow(1)).state, .warning, "M2 code \(c)")
    }
    // M7：最新告警以 t 最大為準，不是陣列最後一筆
    let m7 = menuBarModel(status: mrtStatus(.recording, warnings: [mrtAlertNew, mrtAlertOld]), pidAlive: true, now: mrtNow(125))
    mrtContains(m7.statusLine, mrtAlertNew.message, "M7 取 t 最大")
}

// §4.11.2：只有告警類 warning 會轉告警態；device_change、audio_format_change 不會。
func testRecordOnlyWarningsDoNotAlert() throws {
    let alerts: Set<WarningKind> = [.silenceSystem, .silenceMic, .black, .suspended, .diskLow]
    for k in [WarningKind.silenceSystem, .silenceMic, .black, .suspended, .diskLow, .deviceChange, .audioFormatChange] {
        mrtEqual(k.isAlert, alerts.contains(k), k.rawValue)
    }
    let recordOnly = [RecordWarning(t: 10, kind: .deviceChange, message: "輸入裝置已切換"),
                      RecordWarning(t: 11, kind: .audioFormatChange, message: "系統聲音格式改為 16 kHz")]
    let m = menuBarModel(status: mrtStatus(.recording, warnings: recordOnly), pidAlive: true, now: mrtNow(125))
    mrtEqual(m.state, .recording, "只有紀錄類 warning 應維持錄製中（M9）")
    mrtContains(m.statusLine, "錄製中")
    mrtEqual(m.canStop, true)
    // 再加一筆告警類就轉告警態（M7）
    let m2 = menuBarModel(status: mrtStatus(.recording, warnings: recordOnly + [RecordWarning(t: 5, kind: .black, message: "畫面已全黑超過 5 秒")]),
                          pidAlive: true, now: mrtNow(125))
    mrtEqual(m2.state, .warning)
    mrtContains(m2.statusLine, "畫面已全黑超過 5 秒")
}

// §4.11.5：三態圖示為 SF Symbols record.circle、record.circle.fill、exclamationmark.triangle.fill。
func testSymbolNames() throws {
    let expected: [MenuBarState: String] = [.idle: "record.circle", .recording: "record.circle.fill",
                                            .warning: "exclamationmark.triangle.fill"]
    for r in mrtMenuRows {
        let m = mrtModel(r)
        mrtEqual(m.symbolName, expected[m.state] ?? "", "\(r.row)")
    }
    mrtEqual(Set(mrtMenuRows.map { mrtModel($0).state }), Set([MenuBarState.idle, .recording, .warning]))
    mrtEqual(MenuBarState.idle.rawValue, "idle")
    mrtEqual(MenuBarState.recording.rawValue, "recording")
    mrtEqual(MenuBarState.warning.rawValue, "warning")
}

// §4.11.6：選單項當下能不能用以 §3.4.1 的 canStart／canStop／canOpenSession 欄為準。
func testMenuItemAvailability() throws {
    for r in mrtMenuRows {
        let m = mrtModel(r)
        mrtEqual(m.canStart, r.canStart, "\(r.row) canStart")
        mrtEqual(m.canStop, r.canStop, "\(r.row) canStop")
        mrtEqual(m.canOpenSession, r.canOpenSession, "\(r.row) canOpenSession")
    }
}

// §4.11.7：「停止錄製」只在 phase=recording 且 pid 活著時可點；stopping／finalizing 期間灰掉。
func testStopAvailabilityByPhase() throws {
    let phases: [RecordPhase] = [.preflight, .preflightFailed, .recording, .stopping, .finalizing, .done, .failed]
    for p in phases {
        for alive in [true, false] {
            for warn in [[], [mrtAlertNew]] {
                let m = menuBarModel(status: mrtStatus(p, code: p == .preflightFailed ? 4 : 0, message: "說明", warnings: warn),
                                     pidAlive: alive, now: mrtNow(60))
                mrtEqual(m.canStop, p == .recording && alive, "\(p.rawValue) pidAlive=\(alive) 告警=\(!warn.isEmpty)")
            }
        }
    }
    mrtEqual(menuBarModel(status: nil, pidAlive: false, now: mrtNow(0)).canStop, false)
}

// §4.11.8：statusLine 為完整中文句子，不得含 WarningKind 與 RecordPhase 的 raw value。
func testStatusLineHumanReadable() throws {
    let codes = [WarningKind.silenceSystem, .silenceMic, .black, .suspended, .diskLow, .deviceChange, .audioFormatChange].map { $0.rawValue }
        + [RecordPhase.preflight, .preflightFailed, .recording, .stopping, .finalizing, .done, .failed].map { $0.rawValue }
    for r in mrtMenuRows {
        let line = mrtModel(r).statusLine
        mrtExpect(!line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, "\(r.row) statusLine 不得為空")
        for c in codes { mrtExpect(!line.contains(c), "\(r.row) statusLine 含內部代碼 \(c)：\(line)") }
    }
    // M9 的經過時間格式：mm:ss
    mrtContains(menuBarModel(status: mrtStatus(.recording), pidAlive: true, now: mrtNow(59)).statusLine, "00:59")
    mrtContains(menuBarModel(status: mrtStatus(.recording), pidAlive: true, now: mrtNow(3599)).statusLine, "59:59")
    mrtContains(menuBarModel(status: mrtStatus(.recording), pidAlive: true, now: mrtNow(3600)).statusLine, "1:00:00")
}

// §4.11.1：沒有預設值 → fail(2)；★ 視窗不是恰好一個 → fail(3)；否則 start。
func testQuickStartDecision() throws {
    func code(_ d: QuickStartDecision) -> Int32? { if case .fail(let c, _) = d { return c }; return nil }
    func message(_ d: QuickStartDecision) -> String? { if case .fail(_, let m) = d { return m }; return nil }

    mrtEqual(quickStartDecision(hasDefaults: true, starredWindowIDs: [89596]), .start(windowID: 89596))
    mrtEqual(code(quickStartDecision(hasDefaults: false, starredWindowIDs: [89596])), Int32(2), "沒有預設值優先回 2")
    mrtEqual(code(quickStartDecision(hasDefaults: false, starredWindowIDs: [])), Int32(2))
    mrtEqual(code(quickStartDecision(hasDefaults: true, starredWindowIDs: [])), Int32(3), "沒有 ★")
    mrtEqual(code(quickStartDecision(hasDefaults: true, starredWindowIDs: [89596, 2001])), Int32(3), "★ 不唯一不得猜選")
    for d in [quickStartDecision(hasDefaults: false, starredWindowIDs: []),
              quickStartDecision(hasDefaults: true, starredWindowIDs: [1, 2])] {
        mrtExpect(!(message(d) ?? "").isEmpty, "fail 應附說明原因的訊息")
    }

    // starredWindowIDs 來自 buildWindowRows 中 meeting != nil 的列（spec §3.8.2）：
    // 8 個 Chrome 視窗只有 1 個 ★ 時可以開錄（前一版整個 Chrome 標 ★ 會永遠不唯一）
    let rows = buildWindowRows(candidates: mrtFixtureCandidates.filter { $0.bundleID == chromeBundleID },
                               displays: mrtDisplays, chrome: mrtFixtureChrome, automation: .authorized)
    let starred = rows.filter { $0.meeting != nil }.map { $0.windowID }
    mrtEqual(starred, [mrtMPlusID])
    mrtEqual(quickStartDecision(hasDefaults: true, starredWindowIDs: starred), .start(windowID: mrtMPlusID))
}

// §4.11.8（D18）：accessibilityText ＝ 待機態為 statusLine；其餘狀態為「MeetingRecorder：」＋statusLine。
func testAccessibilityTextPrefix() throws {
    let prefix = "MeetingRecorder："
    for r in mrtMenuRows {
        let m = mrtModel(r)
        if m.state == .idle {
            mrtEqual(m.accessibilityText, m.statusLine, "\(r.row) 待機態 accessibilityText 應等於 statusLine")
        } else {
            mrtEqual(m.accessibilityText, prefix + m.statusLine, "\(r.row) \(m.state.rawValue) 應為「MeetingRecorder：」＋statusLine")
        }
    }
    // M9：錄製中含 mm:ss 經過時間與場次名
    let m9 = menuBarModel(status: mrtStatus(.recording), pidAlive: true, now: mrtNow(125))
    mrtExpect(m9.accessibilityText.hasPrefix(prefix), "M9 應以「MeetingRecorder：」開頭")
    mrtContains(m9.accessibilityText, "02:05", "M9 含經過時間")
    mrtContains(m9.accessibilityText, mrtSessionName, "M9 含場次名")
    // M7：告警含最新告警一句話
    let m7 = menuBarModel(status: mrtStatus(.recording, warnings: [mrtAlertNew, mrtAlertOld]), pidAlive: true, now: mrtNow(125))
    mrtEqual(m7.accessibilityText, prefix + m7.statusLine)
    mrtContains(m7.accessibilityText, mrtAlertNew.message, "M7 含最新告警")
    // M1 待機：不加前綴
    let m1 = menuBarModel(status: nil, pidAlive: false, now: mrtNow(0))
    mrtEqual(m1.accessibilityText, m1.statusLine)
    mrtExpect(!m1.accessibilityText.hasPrefix(prefix), "待機態不得加「MeetingRecorder：」前綴")
}

// §3.4、§4.11.8（D18）：以 Character 計；count <= limit 原樣；否則前 limit-1 個字＋「…」共 limit 個字；limit < 2 視為 2。
func testTruncatedStatusTitle() throws {
    // 短句原樣
    mrtEqual(truncatedStatusTitle("待機", limit: 40), "待機")
    mrtEqual(truncatedStatusTitle("", limit: 40), "")
    // 恰好 40 個字原樣
    let forty = String(repeating: "錄", count: 40)
    mrtEqual(truncatedStatusTitle(forty, limit: 40), forty, "恰好 limit 個字不截")
    // 41 個字 → 前 39 個字＋「…」，共 40 個字
    let fortyOne = String(repeating: "錄", count: 39) + "製中"
    let t = truncatedStatusTitle(fortyOne, limit: 40)
    mrtEqual(t, String(repeating: "錄", count: 39) + "…")
    mrtEqual(t.count, 40, "截斷後共 limit 個字")
    // 實際狀態列：錄製中＋經過時間＋長場次名
    let line = "錄製中 1:02:05　[Stand-up] 範例專案　第三季規劃與跨部門資源協調的延伸討論（含預算、時程與人力）"
    mrtExpect(line.count > 40, "前提：範例句超過 40 個字")
    let lt = truncatedStatusTitle(line, limit: 40)
    mrtEqual(lt.count, 40)
    mrtEqual(lt, String(line.prefix(39)) + "…")
    mrtExpect(lt.hasPrefix("錄製中 1:02:05"), "截斷保留開頭")
    // 以 Character（字素）計，不以 UTF-16／Unicode scalar 計：組合字元 e+U+0301、國旗各算 1 個字
    let combining = String(repeating: "e\u{301}", count: 5)   // 5 個 Character、10 個 scalar
    mrtEqual(truncatedStatusTitle(combining, limit: 5), combining, "5 個字元未超過 limit 5")
    mrtEqual(truncatedStatusTitle(combining, limit: 4), String(repeating: "e\u{301}", count: 3) + "…")
    let flags = "🇹🇼🇯🇵🇺🇸"
    mrtEqual(truncatedStatusTitle(flags, limit: 3), flags)
    mrtEqual(truncatedStatusTitle(flags, limit: 2), "🇹🇼…")
    // limit < 2 視為 2
    mrtEqual(truncatedStatusTitle("範例專案", limit: 1), "範…", "limit 1 視為 2")
    mrtEqual(truncatedStatusTitle("範例專案", limit: 0), "範…", "limit 0 視為 2")
    mrtEqual(truncatedStatusTitle("範例專案", limit: -3), "範…", "負數 limit 視為 2")
    mrtEqual(truncatedStatusTitle("範例", limit: 1), "範例", "2 個字在 limit 視為 2 時不截")
    mrtEqual(truncatedStatusTitle("範", limit: 0), "範")
}

// §3.4、§4.11.10（D18）：menubar 單一實例鎖。暫存目錄內：第一次 .acquired、第二次 .heldByOther、
// close 第一個 fd 後再取得為 .acquired；上層目錄不存在時會建立；上層路徑是檔案（mkdir 失敗）→ .unavailable。
func testMenuBarLockSingleInstance() throws {
    let fm = FileManager.default
    let root = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        .appendingPathComponent("mrt-lock-\(UUID().uuidString)", isDirectory: true)
    defer { try? fm.removeItem(at: root) }
    let parent = root.appendingPathComponent("home/sub", isDirectory: true)
    let lockURL = parent.appendingPathComponent("menubar.lock")
    mrtExpect(!fm.fileExists(atPath: parent.path), "前提：上層目錄尚不存在")

    func fd(of r: MenuBarLockResult) -> Int32? { if case .acquired(let f) = r { return f }; return nil }

    // 第一次：取得
    let first = acquireMenuBarLock(at: lockURL)
    guard let fd1 = fd(of: first) else {
        mrtFail("第一次應為 .acquired，實際 \(first)", file: #fileID, line: #line); return
    }
    mrtExpect(fd1 >= 0, "fd 應 ≥ 0")
    var isDir: ObjCBool = false
    mrtExpect(fm.fileExists(atPath: parent.path, isDirectory: &isDir) && isDir.boolValue, "上層目錄應被建立")
    mrtExpect(fm.fileExists(atPath: lockURL.path), "menubar.lock 應被建立")
    if let perm = (try? fm.attributesOfItem(atPath: lockURL.path))?[.posixPermissions] as? NSNumber {
        mrtEqual(perm.intValue & 0o777, 0o600, "menubar.lock 權限應為 0600")
    } else {
        mrtFail("讀不到 menubar.lock 的權限", file: #fileID, line: #line)
    }

    // 第二次（同一路徑、另一個 open）：被佔用
    mrtEqual(acquireMenuBarLock(at: lockURL), .heldByOther, "第一個 fd 仍持有時應為 .heldByOther")
    mrtEqual(acquireMenuBarLock(at: lockURL), .heldByOther, "再試一次仍為 .heldByOther（不留殘鎖、不誤取得）")

    // 關掉第一個 fd（模擬第一個實例結束）後再取得
    close(fd1)
    let third = acquireMenuBarLock(at: lockURL)
    if let fd3 = fd(of: third) {
        mrtExpect(fd3 >= 0)
        mrtEqual(acquireMenuBarLock(at: lockURL), .heldByOther, "新持有者存在時應為 .heldByOther")
        close(fd3)
    } else {
        mrtFail("close 第一個 fd 後應為 .acquired，實際 \(third)", file: #fileID, line: #line)
    }

    // 上層路徑是一般檔案 → mkdir／open 失敗 → .unavailable(errno)（不得 crash、不得回 .acquired）
    let blocker = root.appendingPathComponent("blocker")
    mrtExpect(fm.createFile(atPath: blocker.path, contents: Data("x".utf8)), "前提：建立擋路的檔案")
    let bad = acquireMenuBarLock(at: blocker.appendingPathComponent("menubar.lock"))
    if case .unavailable(let e) = bad {
        mrtExpect(e != 0, "errno 應非 0")
    } else {
        mrtFail("上層路徑是檔案時應為 .unavailable，實際 \(bad)", file: #fileID, line: #line)
    }
}

// 設計審查 N-1（spec §6 第 73 條）：收尾失敗時狀態列只放短句（40 字內看得到「收尾沒完成」與補救方向），
// 完整訊息（停止原因、收尾失敗、補救指令）放在 detailText，由 menu bar 放進狀態列的 toolTip。
func testFinalizeFailureStatusLineShort() throws {
    let full = "磁碟可用空間低於 2 GB（剩 1.70 GB），已自動停止並收尾；收尾失敗（_record_finalize.py 回 5），段落保留：可執行 meeting record finish \(mrtSession)"
    for st in [mrtStatus(.failed, code: 5, message: full), mrtStatus(.done, code: 5, message: full)] {
        let m = menuBarModel(status: st, pidAlive: false, now: mrtNow(10))
        mrtEqual(m.state, .warning)
        let shown = truncatedStatusTitle(m.statusLine, limit: 40)
        mrtContains(shown, "收尾失敗")
        mrtExpect(!shown.contains("…"), "收尾失敗的狀態列應在 40 字內：\(m.statusLine)")
        mrtExpect(!m.statusLine.contains("_record_finalize.py"), "狀態列不得含內部腳本名：\(m.statusLine)")
        mrtContains(m.detailText, "meeting record finish")
        mrtContains(m.detailText, "磁碟可用空間低於 2 GB")
    }
    // 不是收尾失敗：detailText 是完整多行訊息，statusLine 維持「錄製失敗：首行」
    let other = menuBarModel(status: mrtStatus(.failed, code: 5, message: "段落連續寫檔失敗\n第二行"), pidAlive: false, now: mrtNow(10))
    mrtContains(other.statusLine, "段落連續寫檔失敗")
    mrtContains(other.detailText, "第二行")
    // 其他狀態 detailText 就是 statusLine
    let idle = menuBarModel(status: nil, pidAlive: false, now: mrtNow(0))
    mrtEqual(idle.detailText, idle.statusLine)
}

// 設計審查 N-2（spec §6 第 74 條）：quick-start 沒有終端機，preflight 有 warn 時開錄後要送一則通知。
func testPreflightWarnNotification() throws {
    mrtExpect(preflightWarnNotification(warnText: "") == nil, "沒有 warn 不送通知")
    let text = "會議分頁標記：甲\n系統聲音：乙\n視窗：幕前調度已開啟\n第四行"
    guard let n = preflightWarnNotification(warnText: text) else { mrtExpect(false, "有 warn 應送通知"); return }
    mrtEqual(n.title, "MeetingRecorder 已開錄（有提示）")
    mrtContains(n.body, "幕前調度已開啟")
    mrtExpect(!n.body.contains("第四行"), "通知內文最多 3 行，其餘看 record.log")
    mrtContains(n.body, "record.log")
}

// spec §4.2.1、§4.2.2：Preflight.swift（PreflightItem 13 項、Severity、failCode、PreflightResult、exitCode）。
// spec §4.2.9（D19）：第 5 項兩段式的 Core 判定（SystemAudioCheck、systemAudioCheck、PreflightResult.warnOnly）。
// spec §3.4、§4.2.12（t6 第三輪，發現 I）：幕前調度提醒 stageManagerNotice。
import Foundation

let mrtPreflightTests: [MRTCase] = [
    ("testPreflightItemsAndSeverity", testPreflightItemsAndSeverity),
    ("testFailCodesAndPrecedence", testFailCodesAndPrecedence),
    ("testResultJSONKeys", testResultJSONKeys),
    ("testSystemAudioCheckTwoStage", testSystemAudioCheckTwoStage),
    ("testSystemAudioWarnOnlyResult", testSystemAudioWarnOnlyResult),
    ("testStageManagerNotice", testStageManagerNotice),
]

// §4.2.1：恰有 13 項；signing、power、window_minimized、apple_events 為 warn，其餘 9 項為 hard；
// failCode(of: .apple_events) 為 0。
func testPreflightItemsAndSeverity() throws {
    let raw = PreflightItem.allCases.map { $0.rawValue }
    mrtEqual(raw.count, 13)
    mrtEqual(Set(raw), Set([
        "signing", "screen_permission", "relaunch_needed", "mic_permission", "system_audio_rms", "mic_rms",
        "disk", "window_exists", "session_collision", "power", "already_running", "window_minimized",
        "apple_events",
    ]))
    let warn: Set<PreflightItem> = [.signing, .power, .window_minimized, .apple_events]
    for item in PreflightItem.allCases {
        let expected: Severity = warn.contains(item) ? .warn : .hard
        mrtEqual(severity(of: item), expected, "\(item.rawValue)")
        if expected == .warn { mrtEqual(failCode(of: item), Int32(0), "warn 項 \(item.rawValue)") }
    }
    mrtEqual(PreflightItem.allCases.filter { severity(of: $0) == .hard }.count, 9)
    mrtEqual(failCode(of: .apple_events), Int32(0))
    mrtEqual(Severity.hard.rawValue, "hard")
    mrtEqual(Severity.warn.rawValue, "warn")
}

// §4.2.2：權限三項、RMS 兩項、disk → 4；window_exists → 3；session_collision、already_running → 2；
// 多項同時失敗取 4＞3＞2。
func testFailCodesAndPrecedence() throws {
    let expected: [PreflightItem: Int32] = [
        .screen_permission: 4, .relaunch_needed: 4, .mic_permission: 4,
        .system_audio_rms: 4, .mic_rms: 4, .disk: 4,
        .window_exists: 3,
        .session_collision: 2, .already_running: 2,
        .signing: 0, .power: 0, .window_minimized: 0, .apple_events: 0,
    ]
    for (item, code) in expected { mrtEqual(failCode(of: item), code, "\(item.rawValue)") }

    // PreflightResult 的 computed severity／code
    mrtEqual(PreflightResult(item: .disk, ok: false).code, Int32(4))
    mrtEqual(PreflightResult(item: .disk, ok: true).code, Int32(0))
    mrtEqual(PreflightResult(item: .power, ok: false).code, Int32(0), "warn 項失敗 code 仍為 0")
    mrtEqual(PreflightResult(item: .power, ok: false).severity, .warn)
    mrtEqual(PreflightResult(item: .window_exists, ok: false, message: "找不到視窗").severity, .hard)
    mrtEqual(PreflightResult(item: .disk, ok: true).message, "", "message 預設為空字串")

    func r(_ i: PreflightItem, _ ok: Bool) -> PreflightResult { PreflightResult(item: i, ok: ok) }
    let allOK = PreflightItem.allCases.map { r($0, true) }
    mrtEqual(exitCode(for: []), Int32(0))
    mrtEqual(exitCode(for: allOK), Int32(0))
    mrtEqual(exitCode(for: [r(.signing, false), r(.power, false), r(.window_minimized, false), r(.apple_events, false)]),
             Int32(0), "只有 warn 失敗")
    mrtEqual(exitCode(for: [r(.session_collision, false)]), Int32(2))
    mrtEqual(exitCode(for: [r(.already_running, false), r(.window_exists, true)]), Int32(2))
    mrtEqual(exitCode(for: [r(.session_collision, false), r(.window_exists, false)]), Int32(3))
    mrtEqual(exitCode(for: [r(.window_exists, false), r(.session_collision, false), r(.disk, false)]), Int32(4))
    mrtEqual(exitCode(for: [r(.relaunch_needed, false), r(.already_running, false)]), Int32(4))
    mrtEqual(exitCode(for: [r(.power, false), r(.window_exists, false)]), Int32(3))
}

// §4.2.2：PreflightResult 的 JSON 含 item、ok、severity、code、message 五鍵；
// decode 時忽略 severity 與 code，以 item 重算（spec §3.4）。
func testResultJSONKeys() throws {
    let obj = mrtJSONObject(PreflightResult(item: .disk, ok: false, message: "可用空間不足"))
    mrtEqual(Set(obj.keys), Set(["item", "ok", "severity", "code", "message"]))
    mrtEqual(obj["item"] as? String, "disk")
    mrtEqual(obj["ok"] as? Bool, false)
    mrtEqual(obj["severity"] as? String, "hard")
    mrtEqual(obj["code"] as? Int, 4)
    mrtEqual(obj["message"] as? String, "可用空間不足")

    let warnObj = mrtJSONObject(PreflightResult(item: .apple_events, ok: false))
    mrtEqual(warnObj["severity"] as? String, "warn")
    mrtEqual(warnObj["code"] as? Int, 0)
    mrtEqual(warnObj["item"] as? String, "apple_events")

    // decode：檔內 severity／code 與 item 不符時以 item 重算
    let wrong = #"{"item":"disk","ok":false,"severity":"warn","code":0,"message":"x"}"#
    let d1 = try JSONDecoder().decode(PreflightResult.self, from: Data(wrong.utf8))
    mrtEqual(d1, PreflightResult(item: .disk, ok: false, message: "x"))
    mrtEqual(d1.severity, .hard)
    mrtEqual(d1.code, Int32(4))
    // 沒有 severity／code 鍵也能 decode
    let bare = #"{"item":"window_exists","ok":false,"message":"y"}"#
    let d2 = try JSONDecoder().decode(PreflightResult.self, from: Data(bare.utf8))
    mrtEqual(d2.code, Int32(3))
    // 往返
    let orig = PreflightResult(item: .mic_rms, ok: true, message: "麥克風有聲音")
    let back = try JSONDecoder().decode(PreflightResult.self, from: JSONEncoder().encode(orig))
    mrtEqual(back, orig)
}

// §4.2.9、§4.2.5 (c)（D19）：systemAudioCheck 的 8 組案例；門檻 -60、比較一律「嚴格大於」、NaN 視同 -∞。
// target > 門檻 → .pass（不看 display）；否則 display > 門檻 → .warnTargetSilent；display nil 或 ≤ 門檻 → .fail。
func testSystemAudioCheckTwoStage() throws {
    let th = -60.0
    let cases: [(target: Double, display: Double?, expected: SystemAudioCheck, note: String)] = [
        (-10.2, nil, .pass, "target -10.2、display nil（t6 實機 Chrome 播影片的量測值）"),
        (-59.9, nil, .pass, "target -59.9、display nil（剛好高於門檻）"),
        (-60.0, -19.9, .warnTargetSilent, "target 恰在門檻 -60（不算有聲）、display -19.9"),
        (-Double.infinity, -19.9, .warnTargetSilent, "target -∞、display -19.9"),
        (-Double.infinity, -Double.infinity, .fail, "target -∞、display -∞"),
        (-Double.infinity, -60.0, .fail, "target -∞、display 恰在門檻 -60"),
        (-Double.infinity, nil, .fail, "target -∞、display nil（(b) 沒跑成）"),
        (Double.nan, Double.nan, .fail, "target NaN、display NaN（NaN 視同 -∞）"),
    ]
    for c in cases {
        mrtEqual(systemAudioCheck(targetPeakDBFS: c.target, displayPeakDBFS: c.display, thresholdDBFS: th),
                 c.expected, c.note)
    }
    // §3.4：JSON／raw 值
    mrtEqual(SystemAudioCheck.pass.rawValue, "pass")
    mrtEqual(SystemAudioCheck.warnTargetSilent.rawValue, "warn_target_silent")
    mrtEqual(SystemAudioCheck.fail.rawValue, "fail")
}

// §4.2.9、§3.4（D19）：warnOnly 的 severity、code、exitCode 與 JSON 往返。
// 第 5 項的分級不變（§4.2.1）；只有 item == .system_audio_rms 且 ok == false 時 warnOnly 才存成 true。
func testSystemAudioWarnOnlyResult() throws {
    // 分級不變
    mrtEqual(severity(of: .system_audio_rms), .hard, "D19 不改第 5 項分級")
    mrtEqual(failCode(of: .system_audio_rms), Int32(4))

    let msg = "會議 app 目前沒有聲音；系統聲音擷取權限正常，開錄後若持續 15 秒沒有聲音會告警"
    let w = PreflightResult(item: .system_audio_rms, ok: false, message: msg, warnOnly: true)
    mrtEqual(w.warnOnly, true)
    mrtEqual(w.severity, .warn, "warnOnly 的第 5 項 severity 應為 warn")
    mrtEqual(w.code, Int32(0), "warnOnly 的第 5 項 code 應為 0")
    mrtEqual(w.message, msg)

    // 預設 warnOnly = false：第 5 項失敗仍是 hard、code 4
    let hardFail = PreflightResult(item: .system_audio_rms, ok: false, message: "x")
    mrtEqual(hardFail.warnOnly, false, "warnOnly 預設為 false")
    mrtEqual(hardFail.severity, .hard)
    mrtEqual(hardFail.code, Int32(4))

    // exitCode：warnOnly 不影響
    func r(_ i: PreflightItem, _ ok: Bool) -> PreflightResult { PreflightResult(item: i, ok: ok) }
    mrtEqual(exitCode(for: [w]), Int32(0), "單獨的 warnOnly 第 5 項 → 0")
    mrtEqual(exitCode(for: [w, r(.window_exists, false)]), Int32(3), "與 window_exists 失敗並列 → 3")
    mrtEqual(exitCode(for: [r(.session_collision, false), w]), Int32(2), "與 session_collision 失敗並列 → 2")
    mrtEqual(exitCode(for: [w, r(.mic_rms, false)]), Int32(4), "與麥克風 RMS 失敗並列 → 4（來自 mic_rms）")
    mrtEqual(exitCode(for: [hardFail]), Int32(4), "非 warnOnly 的第 5 項失敗仍回 4")
    mrtEqual(exitCode(for: PreflightItem.allCases.map { $0 == .system_audio_rms ? w : r($0, true) }), Int32(0),
             "其餘 12 項 pass、第 5 項 warnOnly → 照常開錄")

    // warnOnly 只在 item == .system_audio_rms 且 ok == false 時存成 true
    let okTrue = PreflightResult(item: .system_audio_rms, ok: true, message: "", warnOnly: true)
    mrtEqual(okTrue.warnOnly, false, "ok 為 true 時 warnOnly 應存成 false")
    mrtEqual(okTrue.severity, .hard, "ok 為 true 時 severity 照 severity(of:)")
    mrtEqual(okTrue.code, Int32(0))
    let disk = PreflightResult(item: .disk, ok: false, message: "", warnOnly: true)
    mrtEqual(disk.warnOnly, false, "其他 item（disk）warnOnly 應存成 false")
    mrtEqual(disk.severity, .hard)
    mrtEqual(disk.code, Int32(4))
    // t7（§6 第 102 條）：第 6 項（mic_rms）失敗也可降為 warn——照常開錄，錄製中 15 秒靜音告警兜底
    let mic = PreflightResult(item: .mic_rms, ok: false, message: "", warnOnly: true)
    mrtEqual(mic.warnOnly, true, "第 6 項（mic_rms）ok 為 false 時 warnOnly 應存成 true")
    mrtEqual(mic.severity, .warn)
    mrtEqual(mic.code, Int32(0))
    mrtEqual(exitCode(for: [mic]), Int32(0))
    let micHard = PreflightResult(item: .mic_rms, ok: false, message: "")
    mrtEqual(micHard.severity, .hard, "沒帶 warnOnly 的 mic_rms 失敗仍為 hard（例：螢幕錄製權限沒生效、量不到）")
    mrtEqual(micHard.code, Int32(4))
    let power = PreflightResult(item: .power, ok: false, message: "", warnOnly: true)
    mrtEqual(power.warnOnly, false, "其他 item（power）warnOnly 應存成 false")
    mrtEqual(power.severity, .warn, "power 本來就是 warn，照 severity(of:)")
    mrtEqual(power, PreflightResult(item: .power, ok: false, message: ""))

    // JSON：仍恰為五鍵（不另加 warnOnly 鍵），severity 為 "warn"、code 為 0
    let obj = mrtJSONObject(w)
    mrtEqual(Set(obj.keys), Set(["item", "ok", "severity", "code", "message"]), "JSON 不得另加鍵")
    mrtEqual(obj["item"] as? String, "system_audio_rms")
    mrtEqual(obj["ok"] as? Bool, false)
    mrtEqual(obj["severity"] as? String, "warn")
    mrtEqual(obj["code"] as? Int, 0)
    mrtEqual(obj["message"] as? String, msg)
    let hardObj = mrtJSONObject(hardFail)
    mrtEqual(hardObj["severity"] as? String, "hard")
    mrtEqual(hardObj["code"] as? Int, 4)

    // 往返 decode 後相等
    let back = try JSONDecoder().decode(PreflightResult.self, from: JSONEncoder().encode(w))
    mrtEqual(back, w, "warnOnly 結果 JSON 往返應相等")
    mrtEqual(back.warnOnly, true)
    mrtEqual(back.severity, .warn)
    mrtEqual(back.code, Int32(0))
    let backHard = try JSONDecoder().decode(PreflightResult.self, from: JSONEncoder().encode(hardFail))
    mrtEqual(backHard, hardFail)
    mrtEqual(backHard.warnOnly, false)

    // decode：唯一例外是 system_audio_rms、ok false、severity "warn" → warnOnly true（code 一律忽略）
    let warnJSON = #"{"item":"system_audio_rms","ok":false,"severity":"warn","code":4,"message":"m"}"#
    let d1 = try JSONDecoder().decode(PreflightResult.self, from: Data(warnJSON.utf8))
    mrtEqual(d1.warnOnly, true)
    mrtEqual(d1.severity, .warn)
    mrtEqual(d1.code, Int32(0), "decode 時忽略檔內 code")
    mrtEqual(d1, PreflightResult(item: .system_audio_rms, ok: false, message: "m", warnOnly: true))
    // ok 為 true 不還原
    let okJSON = #"{"item":"system_audio_rms","ok":true,"severity":"warn","code":0,"message":""}"#
    let d2 = try JSONDecoder().decode(PreflightResult.self, from: Data(okJSON.utf8))
    mrtEqual(d2.severity, .hard, "ok 為 true 時不還原 warnOnly，severity 以 item 重算")
    mrtEqual(d2.warnOnly, false)
    // severity "hard" 或沒有 severity 鍵 → warnOnly false
    let hardJSON = #"{"item":"system_audio_rms","ok":false,"severity":"hard","code":4,"message":""}"#
    let d3 = try JSONDecoder().decode(PreflightResult.self, from: Data(hardJSON.utf8))
    mrtEqual(d3.warnOnly, false)
    mrtEqual(d3.code, Int32(4))
    let bareJSON = #"{"item":"system_audio_rms","ok":false,"message":""}"#
    let d4 = try JSONDecoder().decode(PreflightResult.self, from: Data(bareJSON.utf8))
    mrtEqual(d4.warnOnly, false)
    mrtEqual(d4.severity, .hard)
    mrtEqual(d4.code, Int32(4))
    // mic_rms 帶 "warn" 還原為 warnOnly（t7，§6 第 102 條）；其他 item 帶 "warn" 仍以 item 重算
    let micJSON = #"{"item":"mic_rms","ok":false,"severity":"warn","code":0,"message":""}"#
    let d5 = try JSONDecoder().decode(PreflightResult.self, from: Data(micJSON.utf8))
    mrtEqual(d5.warnOnly, true)
    mrtEqual(d5.severity, .warn)
    mrtEqual(d5.code, Int32(0))
    let diskJSON = #"{"item":"disk","ok":false,"severity":"warn","code":0,"message":""}"#
    let d6 = try JSONDecoder().decode(PreflightResult.self, from: Data(diskJSON.utf8))
    mrtEqual(d6.warnOnly, false)
    mrtEqual(d6.severity, .hard)
    mrtEqual(d6.code, Int32(4))
}

// §3.4、§4.2.12：stageManagerNotice(globallyEnabled:)——
// true → 幕前調度提醒，應含「幕前調度」「縮圖」「目前舞台」；false、nil → nil。
func testStageManagerNotice() throws {
    let on = stageManagerNotice(globallyEnabled: true)
    mrtExpect(on != nil, "globallyEnabled: true 應回傳提醒，實際 nil")
    let text = on ?? ""
    for keyword in ["幕前調度", "縮圖", "目前舞台"] {
        mrtExpect(text.contains(keyword), "true 的提醒應含「\(keyword)」，實際「\(text)」")
    }
    mrtExpect(stageManagerNotice(globallyEnabled: false) == nil, "globallyEnabled: false 應為 nil")
    mrtExpect(stageManagerNotice(globallyEnabled: nil) == nil, "globallyEnabled: nil 應為 nil")
}

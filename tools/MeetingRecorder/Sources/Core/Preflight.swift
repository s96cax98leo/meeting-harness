// Core/Preflight.swift —— preflight 13 項的分級與結束碼（spec §3.4、§4.2.1、§4.2.2；design §6）
// 實際的檢查（權限、RMS、磁碟…）在 Capture/PreflightRunner.swift；這裡只有規則。
import Foundation

enum PreflightItem: String, CaseIterable, Codable {
    case signing, screen_permission, relaunch_needed, mic_permission, system_audio_rms, mic_rms,
         disk, window_exists, session_collision, power, already_running, window_minimized,
         apple_events    // 第 13 項（D16，warn）：Chrome 分頁標記用的 Apple Events 狀態
}

enum Severity: String, Codable { case hard, warn }

func severity(of item: PreflightItem) -> Severity {
    switch item {
    case .signing, .power, .window_minimized, .apple_events: return .warn
    default: return .hard
    }
}

/// hard 項失敗時的結束碼；warn 項回 0。
func failCode(of item: PreflightItem) -> Int32 {
    switch item {
    case .screen_permission, .relaunch_needed, .mic_permission, .system_audio_rms, .mic_rms, .disk: return 4
    case .window_exists: return 3
    case .session_collision, .already_running: return 2
    case .signing, .power, .window_minimized, .apple_events: return 0
    }
}

struct PreflightResult: Codable, Equatable {
    let item: PreflightItem
    let ok: Bool
    let message: String
    /// D19：第 5 項兩段式 (b) 有聲時，該筆結果降為 warn（spec §4.2.5、§4.2.9）。
    /// 只在 item == .system_audio_rms 且 ok == false 時存成 true；其他情形一律存成 false。
    let warnOnly: Bool

    init(item: PreflightItem, ok: Bool, message: String = "", warnOnly: Bool = false) {
        self.item = item
        self.ok = ok
        self.message = message
        self.warnOnly = warnOnly && item == .system_audio_rms && !ok
    }

    var severity: Severity { warnOnly ? .warn : MeetingRecorder_severity(item) }
    var code: Int32 { ok || severity == .warn ? 0 : failCode(of: item) }

    // JSON 鍵固定為 item、ok、severity、code、message（warnOnly 以 severity 表達，不另加鍵）。
    // decode 時忽略 code；severity 也以 item 重算，唯一例外：system_audio_rms、ok == false 且 severity == "warn" → warnOnly。
    enum CodingKeys: String, CodingKey { case item, ok, severity, code, message }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        item = try c.decode(PreflightItem.self, forKey: .item)
        ok = try c.decode(Bool.self, forKey: .ok)
        message = try c.decodeIfPresent(String.self, forKey: .message) ?? ""
        let sev = try? c.decodeIfPresent(Severity.self, forKey: .severity)
        warnOnly = item == .system_audio_rms && !ok && sev == .warn
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(item, forKey: .item)
        try c.encode(ok, forKey: .ok)
        try c.encode(severity, forKey: .severity)
        try c.encode(code, forKey: .code)
        try c.encode(message, forKey: .message)
    }
}

// PreflightResult 內的 computed 屬性名 severity 會遮蔽同名全域函式，經這個別名呼叫。
private func MeetingRecorder_severity(_ item: PreflightItem) -> Severity { severity(of: item) }

/// 沒有 hard 失敗回 0；否則取 4＞3＞2。
func exitCode(for results: [PreflightResult]) -> Int32 {
    let codes = results.filter { !$0.ok && $0.severity == .hard }.map { $0.code }
    for c: Int32 in [4, 3, 2] where codes.contains(c) { return c }
    return 0
}

/// D19：第 5 項兩段式的判定（spec §3.4、§4.2.5、§4.2.9）。比較一律嚴格大於；NaN 視同 -∞。
enum SystemAudioCheck: String, Codable, Equatable { case pass, warnTargetSilent = "warn_target_silent", fail }

func systemAudioCheck(targetPeakDBFS: Double, displayPeakDBFS: Double?, thresholdDBFS: Double) -> SystemAudioCheck {
    // NaN > x 恆為 false，所以 NaN 自然落到「不超過門檻」（視同 -∞）。
    if targetPeakDBFS > thresholdDBFS { return .pass }
    if let d = displayPeakDBFS, d > thresholdDBFS { return .warnTargetSilent }
    return .fail
}

/// 幕前調度提醒（spec §3.4、§4.2.12；t6 第三輪，發現 I）。
/// globallyEnabled 由 Capture 只讀 com.apple.WindowManager 的 GloballyEnabled 取得；
/// true → 第 12 項 window_minimized 的 warn 訊息；false、nil（讀不到）→ nil。
func stageManagerNotice(globallyEnabled: Bool?) -> String? {
    guard globallyEnabled == true else { return nil }
    return "幕前調度已開啟：會議視窗不在目前舞台時會被縮成側邊縮圖，錄影解析度會跟著變小。錄會議時讓會議視窗留在目前舞台，或先關閉幕前調度"
}

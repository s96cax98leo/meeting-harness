// Core/Settings.swift —— menubar.settings.json 與首次引導寫 record.defaults.json 的合併（spec §3.15、§3.16、§3.20、
// §4.40.6、§4.43.1、§4.43.4、§4.43.6；ADR adr-r3-defaults-writers.md）。不依賴 AppKit。
import Foundation

let menuBarSettingsFileName = "menubar.settings.json"

/// <home>/menubar.settings.json（app 唯一寫者）。不含 schemaVersion 欄位：存檔時由 encode(to:) 補寫 "schemaVersion": 1；
/// onboardingCompletedAt 為 nil 時省略鍵。讀取時缺鍵、null、型別不對、不認得的值 → 該鍵用預設值（spec §3.16）。
struct MenuBarSettings: Codable, Equatable {
    var showTimer = true
    var hudMode = HUDMode.auto
    var hudPosition = "right"
    var timeSensitiveAlerts = true
    var lastSettingsTab = "general"
    var onboardingCompletedAt: String? = nil
    var meetingDetect = true

    enum CodingKeys: String, CodingKey {
        case schemaVersion, showTimer, hudMode, hudPosition, timeSensitiveAlerts, lastSettingsTab, onboardingCompletedAt,
             meetingDetect
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(1, forKey: .schemaVersion)
        try c.encode(showTimer, forKey: .showTimer)
        try c.encode(hudMode, forKey: .hudMode)
        try c.encode(hudPosition, forKey: .hudPosition)
        try c.encode(timeSensitiveAlerts, forKey: .timeSensitiveAlerts)
        try c.encode(lastSettingsTab, forKey: .lastSettingsTab)
        try c.encodeIfPresent(onboardingCompletedAt, forKey: .onboardingCompletedAt)
        try c.encode(meetingDetect, forKey: .meetingDetect)
    }
}

/// hudPosition 允許的值（U2-C：螢幕右緣或左緣）。
private let hudPositions: Set<String> = ["right", "left"]

extension MenuBarSettings {
    /// 寬鬆讀取：每一鍵各自 try?，壞的鍵用預設值，不讓一個鍵壞掉拖累整份設定。
    /// 寫在 extension 裡，保留合成的 init() 與逐欄 init。
    init(from decoder: Decoder) throws {
        self.init()
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let v = try? c.decodeIfPresent(Bool.self, forKey: .showTimer) { showTimer = v }
        if let raw = try? c.decodeIfPresent(String.self, forKey: .hudMode), let v = HUDMode(rawValue: raw) { hudMode = v }
        if let v = try? c.decodeIfPresent(String.self, forKey: .hudPosition), hudPositions.contains(v) { hudPosition = v }
        if let v = try? c.decodeIfPresent(Bool.self, forKey: .timeSensitiveAlerts) { timeSensitiveAlerts = v }
        if let v = try? c.decodeIfPresent(String.self, forKey: .lastSettingsTab), SettingsTab(rawValue: v) != nil {
            lastSettingsTab = v
        }
        if let v = try? c.decodeIfPresent(String.self, forKey: .onboardingCompletedAt) { onboardingCompletedAt = v }
        if let v = try? c.decodeIfPresent(Bool.self, forKey: .meetingDetect) { meetingDetect = v }
    }
}

/// 設定視窗的 7 個工具列分頁（U5-A；spec §4.43.6）。
enum SettingsTab: String, CaseIterable {
    case general, recording, feedback, hotkeys, afterRecording, permissions, advanced

    var title: String {
        switch self {
        case .general: return "一般"
        case .recording: return "錄製"
        case .feedback: return "回饋與通知"
        case .hotkeys: return "快捷鍵"
        case .afterRecording: return "錄完之後"
        case .permissions: return "權限"
        case .advanced: return "進階"
        }
    }

    var symbolName: String {
        switch self {
        case .general: return "gearshape"
        case .recording: return "record.circle"
        case .feedback: return "bell.badge"
        case .hotkeys: return "command"
        case .afterRecording: return "checkmark.circle"
        case .permissions: return "lock.shield"
        case .advanced: return "slider.horizontal.3"
        }
    }
}

/// 不認得 → .general。
func settingsTab(_ raw: String) -> SettingsTab {
    SettingsTab(rawValue: raw) ?? .general
}

/// 缺檔、壞檔、不是物件 → 全部預設值；個別鍵的處理見 MenuBarSettings.init(from:)。
func loadMenuBarSettings(home: URL) -> MenuBarSettings {
    let url = home.appendingPathComponent(menuBarSettingsFileName)
    guard let data = try? Data(contentsOf: url),
          let s = try? JSONDecoder().decode(MenuBarSettings.self, from: data) else { return MenuBarSettings() }
    return s
}

/// 寫 <home>/menubar.settings.json（同目錄暫存檔＋rename）；不碰 R2 的 menubar.prefs.json。
func saveMenuBarSettings(_ s: MenuBarSettings, home: URL) throws {
    try writeJSONAtomically(s, to: home.appendingPathComponent(menuBarSettingsFileName))
}

enum DefaultsMergeError: Error, Equatable { case notObject, lockTimeout }

/// existing（record.defaults.json 的位元組；nil＝缺檔）合併 harness、root 兩鍵，其他鍵與值原樣保留。
/// existing 不是 JSON 物件（含不是合法 JSON）→ 丟 .notObject。
func mergedDefaultsJSON(existing: Data?, harness: String, root: String) throws -> Data {
    var obj: [String: Any] = [:]
    if let data = existing {
        guard let parsed = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]),
              let dict = parsed as? [String: Any] else { throw DefaultsMergeError.notObject }
        obj = dict
    }
    obj["harness"] = harness
    obj["root"] = root
    return try JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes])
}

/// 取 <home>/record.defaults.lock（阻塞，最多 timeout 秒，每 100 ms 重試；逾時丟 .lockTimeout）→ 讀 record.defaults.json
/// （缺檔＝nil）→ mergedDefaultsJSON（壞檔丟 .notObject、不寫）→ 同目錄 mkstemp＋rename（spec §3.15、§3.16）。
func writeOnboardingDefaults(home: URL, harness: String, root: String) throws {
    try writeOnboardingDefaults(home: home, harness: harness, root: root, timeout: 5.0)
}

private func posixError(_ what: String, _ e: Int32) -> NSError {
    NSError(domain: NSPOSIXErrorDomain, code: Int(e),
            userInfo: [NSLocalizedDescriptionKey: "\(what) 失敗：\(String(cString: strerror(e)))"])
}

private func writeOnboardingDefaults(home: URL, harness: String, root: String, timeout: Double) throws {
    let fm = FileManager.default
    try fm.createDirectory(at: home, withIntermediateDirectories: true)
    let lockFD = open(home.appendingPathComponent("record.defaults.lock").path, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
    guard lockFD >= 0 else { throw posixError("open record.defaults.lock", errno) }
    defer { close(lockFD) }     // close 會一併放掉 flock
    let deadline = Date().addingTimeInterval(timeout)
    while true {
        var rc: Int32
        repeat { rc = flock(lockFD, LOCK_EX | LOCK_NB) } while rc != 0 && errno == EINTR
        if rc == 0 { break }
        let e = errno
        guard e == EWOULDBLOCK else { throw posixError("flock record.defaults.lock", e) }
        let remaining = deadline.timeIntervalSinceNow
        if remaining <= 0 { throw DefaultsMergeError.lockTimeout }
        usleep(useconds_t(min(0.1, remaining) * 1_000_000))
    }

    let target = home.appendingPathComponent("record.defaults.json")
    let existing: Data?
    if fm.fileExists(atPath: target.path) {
        existing = try Data(contentsOf: target)
    } else {
        existing = nil
    }
    let merged = try mergedDefaultsJSON(existing: existing, harness: harness, root: root)

    var template = Array(home.appendingPathComponent(".record.defaults.json.XXXXXX").path.utf8CString)
    let fd = template.withUnsafeMutableBufferPointer { mkstemp($0.baseAddress!) }
    guard fd >= 0 else { throw posixError("mkstemp", errno) }
    let tmpPath = String(cString: template.withUnsafeBufferPointer { $0.baseAddress! })
    let handle = FileHandle(fileDescriptor: fd, closeOnDealloc: true)
    do {
        try handle.write(contentsOf: merged)
        try handle.close()
        guard rename(tmpPath, target.path) == 0 else { throw posixError("rename", errno) }
    } catch {
        unlink(tmpPath)
        throw error
    }
}


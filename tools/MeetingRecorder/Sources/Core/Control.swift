// Core/Control.swift —— R2 的控制通道、暫停／靜音事件、標記、計時、收音指示、menu bar 偏好與小工具
// （spec §3.9–§3.14；ADR adr-r2-control-file.md、adr-r2-status-fields.md）。
// 純邏輯與檔案 I/O：不碰擷取 API、不送訊號（訊號由呼叫端送），可與 Tests/ 一起編譯。
import Foundation

// MARK: - 控制檔（spec §3.9）

let controlFileName = "record.control.json"
let controlLockFileName = "record.control.lock"
let controlProtocolVersion = 1

/// JSON 鍵恰為這 5 個（沒有 Optional，合成 Codable 即可）。
struct RecordControl: Codable, Equatable {
    var schemaVersion: Int
    var runId: String
    var paused: Bool
    var micMuted: Bool
    var markerSeq: Int
}

func freshControl(runId: String) -> RecordControl {
    RecordControl(schemaVersion: controlProtocolVersion, runId: runId, paused: false, micMuted: false, markerSeq: 0)
}

enum ControlCommand: String, CaseIterable { case pause, resume, mute, unmute, mark }

/// 只改該命令的欄位；runId、schemaVersion 不變。
func applying(_ cmd: ControlCommand, to c: RecordControl) -> RecordControl {
    var r = c
    switch cmd {
    case .pause: r.paused = true
    case .resume: r.paused = false
    case .mute: r.micMuted = true
    case .unmute: r.micMuted = false
    case .mark: r.markerSeq += 1
    }
    return r
}

/// 錄製實例收到 SIGUSR1 後要做的事。pause／micMute 為 nil＝不變。
struct ControlActions: Equatable {
    var pause: Bool?
    var micMute: Bool?
    var newMarkers: Int
}

/// requested 為 nil、runId 與 applied 不同、或 schemaVersion != 1 → 無動作；
/// 否則只回報與 applied 不同的狀態，newMarkers＝max(0, requested.markerSeq − applied.markerSeq)。
func controlActions(applied: RecordControl, requested: RecordControl?) -> ControlActions {
    guard let req = requested, req.runId == applied.runId, req.schemaVersion == controlProtocolVersion else {
        return ControlActions(pause: nil, micMute: nil, newMarkers: 0)
    }
    return ControlActions(pause: req.paused != applied.paused ? req.paused : nil,
                          micMute: req.micMuted != applied.micMuted ? req.micMuted : nil,
                          newMarkers: max(0, req.markerSeq - applied.markerSeq))
}

/// 不存在或解不開 → nil。
func readControl(_ url: URL) -> RecordControl? {
    guard let data = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(RecordControl.self, from: data)
}

/// 取 <home>/record.control.lock 的 flock(LOCK_EX)（上層目錄不存在先建），在持有鎖時執行 body。
private func withControlLock<T>(home: URL, _ body: () throws -> T) throws -> T {
    try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    let lockPath = home.appendingPathComponent(controlLockFileName).path
    let fd = open(lockPath, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
    guard fd >= 0 else { throw controlPOSIXError("開不了 \(controlLockFileName)") }
    defer { close(fd) }
    var rc: Int32
    repeat { rc = flock(fd, LOCK_EX) } while rc != 0 && errno == EINTR
    guard rc == 0 else { throw controlPOSIXError("鎖不住 \(controlLockFileName)") }
    defer { _ = flock(fd, LOCK_UN) }
    return try body()
}

private func controlPOSIXError(_ what: String) -> NSError {
    let e = errno
    return NSError(domain: NSPOSIXErrorDomain, code: Int(e),
                   userInfo: [NSLocalizedDescriptionKey: "\(what)：\(String(cString: strerror(e)))"])
}

/// 錄製實例開錄時呼叫：把控制檔重設成 freshControl(runId:)。
@discardableResult
func resetControl(home: URL, runId: String) throws -> RecordControl {
    try withControlLock(home: home) {
        let c = freshControl(runId: runId)
        try writeJSONAtomically(c, to: home.appendingPathComponent(controlFileName))
        return c
    }
}

/// menu bar／CLI 送控制：持鎖 read-modify-write。讀不到、runId 不同（或 schemaVersion 不是 1）就從
/// freshControl(runId:) 起算；回傳寫入的內容。不送訊號。
@discardableResult
func requestControl(_ cmd: ControlCommand, home: URL, runId: String) throws -> RecordControl {
    try withControlLock(home: home) {
        let url = home.appendingPathComponent(controlFileName)
        var cur = freshControl(runId: runId)
        if let existing = readControl(url), existing.runId == runId, existing.schemaVersion == controlProtocolVersion {
            cur = existing
        }
        let next = applying(cmd, to: cur)
        try writeJSONAtomically(next, to: url)
        return next
    }
}

enum ControlAvailability: Equatable {
    case ready(pid: Int32, runId: String)
    case unavailable(message: String)
}

/// 依序判斷、第一個成立者為準（spec §3.14）。
func controlAvailability(status: RecordStatus?, recordPid: Int32?, pidAlive: Bool) -> ControlAvailability {
    guard let st = status, let pid = recordPid, pidAlive else { return .unavailable(message: "沒有錄製在跑") }
    guard st.pid == pid else { return .unavailable(message: "沒有錄製在跑（狀態檔不是這個錄製實例的）") }
    switch st.phase {
    case .preflight:
        return .unavailable(message: "還在開錄前檢查，開始錄製後才能暫停、靜音或加標記")
    case .stopping, .finalizing:
        return .unavailable(message: "錄製正在收尾，不能再暫停、靜音或加標記")
    case .recording:
        break
    case .preflightFailed, .done, .failed:
        return .unavailable(message: "沒有錄製在跑")
    }
    guard (st.controlVersion ?? 0) >= 1 else {
        return .unavailable(message: "這場錄製是舊版錄製器開的，不支援暫停、靜音或加標記；重建 app 後下一場才能用")
    }
    return .ready(pid: pid, runId: st.runId)
}

// MARK: - 事件與標記（spec §3.11、§3.12）

enum PauseEventKind: String, Codable { case pause, resume }

struct PauseEvent: Codable, Equatable {
    var t: Double
    var outputT: Double
    var wallClock: String
    var kind: PauseEventKind
}

struct MicMuteEvent: Codable, Equatable {
    var t: Double
    var outputT: Double
    var wallClock: String
    var muted: Bool
}

struct Marker: Codable, Equatable {
    var t: Double
    var recordT: Double
    var wallClock: String
    var label: String
}

func markerLabel(_ n: Int) -> String { "標記 \(n)" }

/// 小數 3 位。
private func controlRound3(_ v: Double) -> Double { (v * 1000).rounded() / 1000 }

/// 把事件配成暫停區間：pause 與緊接其後的 resume 一組；沒有前導 pause 的 resume 略過；
/// 連續的 pause 以第一筆為準；最後沒配對的 pause 的 end 為 nil。
private func pauseIntervals(_ events: [PauseEvent]) -> [(start: Double, end: Double?)] {
    var out: [(start: Double, end: Double?)] = []
    var pending: Double?
    for e in events {
        switch e.kind {
        case .pause:
            if pending == nil { pending = e.t }
        case .resume:
            if let p = pending {
                out.append((p, e.t))
                pending = nil
            }
        }
    }
    if let p = pending { out.append((p, nil)) }
    return out
}

/// Σ（resume.t − 緊接在前的 pause.t）；沒配對的 pause、沒有前導 pause 的 resume 不計；小數 3 位。
func pausedTotal(_ events: [PauseEvent]) -> Double {
    controlRound3(pauseIntervals(events).reduce(0) { acc, iv in acc + (iv.end.map { $0 - iv.start } ?? 0) })
}

/// 錄製時鐘 → 成品時間：落在暫停區間時以該 pause.t 代替；再減 firstSegmentStart 與已結束（resume.t ≤ 代替後時刻）
/// 的已配對暫停長度；< 0 夾成 0；小數 3 位。
func outputTime(recordT: Double, firstSegmentStart: Double, pauses: [PauseEvent]) -> Double {
    let ivs = pauseIntervals(pauses)
    var x = recordT
    for iv in ivs where iv.start <= recordT {
        if let end = iv.end {
            if recordT < end { x = iv.start; break }
        } else {
            x = iv.start
            break
        }
    }
    var v = x - firstSegmentStart
    for iv in ivs {
        if let end = iv.end, end <= x { v -= end - iv.start }
    }
    return max(0, controlRound3(v))
}

/// 目前狀態＝最後一筆的 kind（沒有事件視為 resume）；kind 等於目前狀態 → 原樣（冪等）；
/// 否則 append：t 取小數 3 位、outputT 以「既有事件＋這一筆」算。
func appendingPauseEvent(_ events: [PauseEvent], kind: PauseEventKind, t: Double, firstSegmentStart: Double,
                         wallClock: String) -> [PauseEvent] {
    let current = events.last?.kind ?? .resume
    guard kind != current else { return events }
    var e = PauseEvent(t: controlRound3(t), outputT: 0, wallClock: wallClock, kind: kind)
    var out = events
    out.append(e)
    e.outputT = outputTime(recordT: e.t, firstSegmentStart: firstSegmentStart, pauses: out)
    out[out.count - 1] = e
    return out
}

struct PauseStatusFields: Equatable {
    var paused: Bool
    var pausedAt: String?
    var pausedSeconds: Double
}

func pauseStatusFields(_ events: [PauseEvent]) -> PauseStatusFields {
    let paused = events.last?.kind == .pause
    return PauseStatusFields(paused: paused, pausedAt: paused ? events.last?.wallClock : nil,
                             pausedSeconds: pausedTotal(events))
}

/// 只設 paused、pausedAt（nil＝JSON 省略鍵）、pausedSeconds；其餘欄位不變。
func applyingPauseFields(_ f: PauseStatusFields, to s: RecordStatus) -> RecordStatus {
    var r = s
    r.paused = f.paused
    r.pausedAt = f.pausedAt
    r.pausedSeconds = f.pausedSeconds
    return r
}

/// 目前狀態＝最後一筆的 muted（沒有事件視為 false）；muted 等於目前狀態 → 原樣；否則 append。
func appendingMuteEvent(_ events: [MicMuteEvent], muted: Bool, t: Double, firstSegmentStart: Double,
                        pauses: [PauseEvent], wallClock: String) -> [MicMuteEvent] {
    let current = events.last?.muted ?? false
    guard muted != current else { return events }
    let rt = controlRound3(t)
    return events + [MicMuteEvent(t: rt, outputT: outputTime(recordT: rt, firstSegmentStart: firstSegmentStart, pauses: pauses),
                                  wallClock: wallClock, muted: muted)]
}

// MARK: - 計時與收音指示（spec §3.10、§3.14、§4.20.1、§4.20.3）

/// now − recordingStartedAt − pausedSeconds −（暫停中再扣 now − pausedAt），向下取整，< 0 夾成 0；
/// 任一字串解不開 → nil。
func recordedSeconds(recordingStartedAt: String, pausedSeconds: Double, pausedAt: String?, now: Date) -> Int? {
    let f = ISO8601DateFormatter()
    guard let start = f.date(from: recordingStartedAt) else { return nil }
    var v = now.timeIntervalSince(start) - pausedSeconds
    if let pausedAt {
        guard let p = f.date(from: pausedAt) else { return nil }
        v -= now.timeIntervalSince(p)
    }
    guard v.isFinite else { return nil }
    return max(0, Int(floor(v + 1e-6)))
}

/// < 3600 → "mm:ss"；≥ 3600 → "h:mm:ss"；負值視為 0。
func clockText(seconds: Int) -> String {
    let total = max(0, seconds)
    let h = total / 3600, m = (total % 3600) / 60, s = total % 60
    return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%02d:%02d", m, s)
}

/// 取最後 count 個（不足取全部）中非 nil 的最大值；沒有 → nil。
func recentPeak(_ windows: [Double?], count: Int) -> Double? {
    windows.suffix(max(0, count)).compactMap { $0 }.max()
}

/// 收音指示列；比較一律「嚴格大於」門檻。兩路之間是全形空白 U+3000。
func levelIndicatorLine(recent: RecentLevels?, micMuted: Bool, paused: Bool, thresholdDBFS: Double) -> String {
    if paused { return "收音：暫停中" }
    guard let recent else { return "收音：讀取中…" }
    func mark(_ v: Double?) -> String {
        if let v, v > thresholdDBFS { return "● 有聲" }
        return "○ 無聲"
    }
    return "收音：系統聲音 " + mark(recent.system) + "\u{3000}麥克風 " + (micMuted ? "⊘ 已靜音" : mark(recent.mic))
}

// MARK: - menu bar 偏好（spec §3.13）

let menuBarPrefsFileName = "menubar.prefs.json"

/// JSON 鍵恰為這 6 個；nil 寫 null。只有 menu bar 程序寫。
struct MenuBarPrefs: Codable, Equatable {
    var schemaVersion: Int
    var root: String?
    var recentRoots: [String]
    var autoPrep: Bool
    var lastSession: String?
    var lastAutoPrepRunId: String?

    enum CodingKeys: String, CodingKey { case schemaVersion, root, recentRoots, autoPrep, lastSession, lastAutoPrepRunId }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(schemaVersion, forKey: .schemaVersion)
        try c.encode(root, forKey: .root)
        try c.encode(recentRoots, forKey: .recentRoots)
        try c.encode(autoPrep, forKey: .autoPrep)
        try c.encode(lastSession, forKey: .lastSession)
        try c.encode(lastAutoPrepRunId, forKey: .lastAutoPrepRunId)
    }
}

/// 不存在或解不開 → 預設值 (1, nil, [], false, nil, nil)；不得因此擋住 menu bar。
func loadMenuBarPrefs(_ url: URL) -> MenuBarPrefs {
    let fallback = MenuBarPrefs(schemaVersion: 1, root: nil, recentRoots: [], autoPrep: false,
                                lastSession: nil, lastAutoPrepRunId: nil)
    guard let data = try? Data(contentsOf: url),
          let prefs = try? JSONDecoder().decode(MenuBarPrefs.self, from: data) else { return fallback }
    return prefs
}

func saveMenuBarPrefs(_ prefs: MenuBarPrefs, to url: URL) throws {
    try writeJSONAtomically(prefs, to: url)
}

/// 去掉結尾 "/"（"/" 本身除外）。
private func trimmedTrailingSlash(_ p: String) -> String {
    var s = p
    while s.count > 1 && s.hasSuffix("/") { s.removeLast() }
    return s
}

/// root 為空字串 → 原樣；否則正規化後移除相同的既有項、插到最前、截到 limit 個。
func updatedRecentRoots(_ list: [String], adding root: String, limit: Int) -> [String] {
    guard !root.isEmpty else { return list }
    let r = trimmedTrailingSlash(root)
    let rest = list.filter { trimmedTrailingSlash($0) != r }
    return Array(([r] + rest).prefix(max(0, limit)))
}

// MARK: - quick-start（spec §4.21）

enum RootChoice: Equatable {
    case use(String)
    case fail(code: Int32, message: String)
}

/// 依序取第一個非空的 argRoot、prefsRoot、defaultsRoot。
func quickStartRoot(argRoot: String?, prefsRoot: String?, defaultsRoot: String?,
                    isDirectory: (String) -> Bool) -> RootChoice {
    guard let root = [argRoot, prefsRoot, defaultsRoot].compactMap({ $0 }).first(where: { !$0.isEmpty }) else {
        return .fail(code: 2, message: "還沒有上次的設定：請先在終端機跑一次 meeting record")
    }
    guard isDirectory(root) else { return .fail(code: 2, message: "存檔位置不存在：" + root) }
    return .use(root)
}

/// 選單「錄這個視窗」：不經 ★ 恰好一個的判斷。
func explicitWindowDecision(hasDefaults: Bool, resolution: WindowResolution) -> QuickStartDecision {
    guard hasDefaults else { return quickStartDecision(hasDefaults: false, starredWindowIDs: []) }
    switch resolution {
    case .exact(let id), .reidentified(let id):
        return .start(windowID: id)
    case .notFound:
        return .fail(code: 3, message: "選的視窗已經不在了：請從選單重新選視窗")
    case .ambiguous:
        return .fail(code: 3, message: "有好幾個同名的視窗，認不出選的是哪一個：請從選單重新選視窗")
    }
}

/// arguments 不含 argv[0]；先去掉 "-psn_" 開頭的項；剩下為空 → "menubar"；否則剩下的第一個。
func launchMode(arguments: [String]) -> String {
    arguments.first { !$0.hasPrefix("-psn_") } ?? "menubar"
}

// MARK: - 登入項目（spec §4.22）

enum LoginItemState: String, CaseIterable { case notRegistered, enabled, requiresApproval, notFound }

struct LoginItemDisplay: Equatable {
    let isOn: Bool
    let note: String
    let showOpenSettings: Bool
}

func loginItemDisplay(_ state: LoginItemState) -> LoginItemDisplay {
    switch state {
    case .enabled:
        return LoginItemDisplay(isOn: true, note: "", showOpenSettings: false)
    case .notRegistered:
        return LoginItemDisplay(isOn: false, note: "", showOpenSettings: false)
    case .requiresApproval:
        return LoginItemDisplay(isOn: true,
                                note: "還要到「系統設定 › 一般 › 登入項目」允許 MeetingRecorder，登入時才會自動開啟",
                                showOpenSettings: true)
    case .notFound:
        return LoginItemDisplay(isOn: false,
                                note: "系統找不到這個 app 的登入項目設定；請確認 app 放在「應用程式」資料夾後再試",
                                showOpenSettings: false)
    }
}

// MARK: - 自動前處理與完成通知（spec §3.13、§4.23）

/// 全部成立時回 status.session，否則 nil。R3（spec §4.42.5）：discarded == true 的結果不觸發。
func shouldAutoPrep(autoPrep: Bool, status: RecordStatus?, seenInProgressRunIds: Set<String>,
                    lastAutoPrepRunId: String?) -> String? {
    guard autoPrep, let st = status, st.phase == .done, st.code == 0, st.discarded != true,
          seenInProgressRunIds.contains(st.runId), st.runId != lastAutoPrepRunId, !st.session.isEmpty else { return nil }
    return st.session
}

func completionNotificationID(runId: String) -> String { "mh.complete." + runId }
let completionCategoryID = "mh.complete"
let revealActionID = "mh.reveal"

// MARK: - 快捷鍵與去抖（spec §4.20.5、§4.20.7）

struct HotKeySpec: Equatable {
    let id: UInt32
    let key: String
    let action: String
    let display: String
}

let r2HotKeys: [HotKeySpec] = [
    HotKeySpec(id: 1, key: "r", action: "start", display: "⌃⌥⌘R"),
    HotKeySpec(id: 2, key: "m", action: "mute", display: "⌃⌥⌘M"),
    HotKeySpec(id: 3, key: "p", action: "pause", display: "⌃⌥⌘P"),
    HotKeySpec(id: 4, key: "b", action: "mark", display: "⌃⌥⌘B"),
]

/// 同一 action 距上次「被接受」< interval → false（不更新）；否則 true 並記下 t；不同 action 互不影響。
struct TriggerDebouncer {
    private let interval: Double
    private var lastAccepted: [String: Double] = [:]

    init(interval: Double) { self.interval = interval }

    mutating func accept(_ action: String, at t: Double) -> Bool {
        if let last = lastAccepted[action], t - last < interval { return false }
        lastAccepted[action] = t
        return true
    }
}

// MARK: - t7 實機驗收的修正（spec §6 第 105、106 條）

/// 快捷鍵送出控制後的通知內文：圖示被瀏海擋住時，使用者靠這則通知知道按到了（§6 第 105 條）。
func controlFeedback(_ cmd: ControlCommand, markerSeq: Int) -> String {
    switch cmd {
    case .mute: return "麥克風已靜音"
    case .unmute: return "麥克風已取消靜音"
    case .pause: return "已暫停錄製"
    case .resume: return "已繼續錄製"
    case .mark: return "已加標記 \(markerSeq)"
    }
}

/// 選單列圖示是否看不到：視窗不可見、寬度 0，或 x 範圍壓到瀏海（notchMinX…notchMaxX）（§6 第 106 條）。
func statusItemObscured(itemMinX: CGFloat, itemMaxX: CGFloat, visible: Bool,
                        notchMinX: CGFloat?, notchMaxX: CGFloat?) -> Bool {
    if !visible || itemMaxX <= itemMinX { return true }
    guard let lo = notchMinX, let hi = notchMaxX, hi > lo else { return false }
    return itemMaxX > lo && itemMinX < hi
}

// Core/Trigger.swift —— menu bar 狀態對映與 quick-start 判斷（spec §3.4、§3.4.1、§3.14.1、§4.11、§4.20.2）
// 對映規則的唯一正本是 spec §3.4.1 全表（M1–M10 加 M6a）與 §3.14.1 的 M6b：由上而下取第一個成立的列。
// statusLine 一律是給人看的中文句子，不得含 WarningKind／RecordPhase 的 raw value（§4.11.8）。
import Foundation

enum MenuBarState: String, Equatable { case idle, recording, warning, paused }

struct MenuBarModel: Equatable {
    let state: MenuBarState
    let symbolName: String
    let statusLine: String
    let canStart: Bool
    let canStop: Bool
    let canOpenSession: Bool
    /// 狀態列 toolTip 的完整內容（設計審查 N-1）：失敗類（M2–M4）為完整多行訊息，其餘同 statusLine。
    var detailText: String = ""
    // ---- R2（spec §3.14.1）：只在 phase == recording 且 pid 活著的列（M6b、M7、M9）設定，其他列為預設值 ----
    var timerText: String = ""
    var paused: Bool = false
    var micMuted: Bool = false
    var canControl: Bool = false
    var levelLine: String = ""
}

extension MenuBarModel {
    /// status item 的 toolTip／accessibilityLabel／圖示描述（spec §4.11.8，D18）：
    /// 待機態＝statusLine；其餘狀態加「MeetingRecorder：」前綴，讓 VoiceOver 聽得出是哪個 app。
    var accessibilityText: String {
        state == .idle ? statusLine : "MeetingRecorder：" + statusLine
    }
}

private func symbol(for state: MenuBarState) -> String {
    switch state {
    case .idle: return "record.circle"
    case .recording: return "record.circle.fill"
    case .warning: return "exclamationmark.triangle.fill"
    case .paused: return "pause.circle.fill"
    }
}

private func firstLine(_ s: String) -> String {
    s.split(separator: "\n", maxSplits: 1, omittingEmptySubsequences: false).first.map(String.init) ?? ""
}

/// 經過時間：mm:ss；≥ 60 分鐘時 h:mm:ss（第一輪：now − startedAt）。
private func elapsedText(from startedAt: String, now: Date) -> String? {
    let f = ISO8601DateFormatter()
    guard let start = f.date(from: startedAt) else { return nil }
    return clockText(seconds: Int(now.timeIntervalSince(start)))
}

/// spec §3.14.1 M9 的計時：有 recordingStartedAt 時＝clockText(recordedSeconds(...))；沒有時沿用第一輪的 now − startedAt。
private func recordingTimerText(_ st: RecordStatus, now: Date) -> String? {
    if let rsa = st.recordingStartedAt {
        return recordedSeconds(recordingStartedAt: rsa, pausedSeconds: st.pausedSeconds ?? 0,
                               pausedAt: st.pausedAt, now: now).map { clockText(seconds: $0) }
    }
    return elapsedText(from: st.startedAt, now: now)
}

func menuBarModel(status: RecordStatus?, pidAlive: Bool, now: Date) -> MenuBarModel {
    func model(_ state: MenuBarState, _ line: String, start: Bool, stop: Bool, open: Bool) -> MenuBarModel {
        MenuBarModel(state: state, symbolName: symbol(for: state), statusLine: line,
                     canStart: start, canStop: stop, canOpenSession: open, detailText: line)
    }
    // M1
    guard let st = status else {
        return model(.idle, "MeetingRecorder 待機中", start: true, stop: false, open: false)
    }
    let detail = firstLine(st.message)
    let suffix = detail.isEmpty ? "" : "：\(detail)"
    let fullSuffix = st.message.isEmpty ? "" : "：\(st.message)"
    /// 失敗類：狀態列放短句，完整訊息進 detailText（toolTip）。
    /// 收尾失敗時首行常被停止原因佔滿、補救指令落在 40 字以後，改放固定短句（設計審查 N-1）。
    func failed(_ head: String, open: Bool) -> MenuBarModel {
        var line = "\(head)\(suffix)"
        if st.message.contains("收尾失敗") { line = "\(head)：收尾失敗，段落保留（滑過看補救方法）" }
        var m = model(.warning, line, start: true, stop: false, open: open)
        m.detailText = "\(head)\(fullSuffix)"
        return m
    }
    switch st.phase {
    case .preflightFailed:    // M2（不論 code）
        return failed("開錄前檢查沒通過", open: false)
    case .failed:             // M3
        return failed("錄製失敗", open: true)
    case .done where st.code != 0:   // M4
        return failed("錄製失敗", open: true)
    case .done:               // M5
        return model(.idle, "MeetingRecorder 待機中", start: true, stop: false, open: true)
    case .preflight, .recording, .stopping, .finalizing:
        break
    }
    // 進行中
    if !pidAlive {            // M6
        return model(.warning, "上一場錄製異常中止，請執行 meeting record finish 收尾",
                     start: true, stop: false, open: true)
    }
    let alerts = st.warnings.filter { $0.kind.isAlert }
    if st.phase == .stopping || st.phase == .finalizing, !alerts.isEmpty {   // M6a（D17）：告警數不去重
        return model(.recording, "收尾中…（告警 \(alerts.count) 則）", start: false, stop: false, open: true)
    }
    // 以下 M6b、M7（recording）、M9 是「錄製中且 pid 活著」的列，要帶 R2 欄位（§3.14.1）
    let name = (st.session as NSString).lastPathComponent
    let timer = st.phase == .recording ? (recordingTimerText(st, now: now) ?? "") : ""
    let isPaused = st.paused ?? false
    let isMuted = st.micMuted ?? false
    func withR2(_ m: MenuBarModel) -> MenuBarModel {
        guard st.phase == .recording else { return m }
        var m = m
        m.timerText = timer
        m.paused = isPaused
        m.micMuted = isMuted
        m.canControl = (st.controlVersion ?? 0) >= 1
        m.levelLine = levelIndicatorLine(recent: st.recentLevels, micMuted: isMuted, paused: isPaused, thresholdDBFS: -60)
        return m
    }
    if st.phase == .recording, isPaused {   // M6b：排在 M7 前，舊告警不得蓋掉暫停狀態
        let t = timer.isEmpty ? "" : " \(timer)"
        let warn = alerts.isEmpty ? "" : "（告警 \(alerts.count) 則）"
        return withR2(model(.paused, "已暫停\(t)・\(name)\(warn)", start: false, stop: true, open: true))
    }
    if let latest = alerts.max(by: { $0.t < $1.t }) {   // M7
        return withR2(model(.warning, "告警：\(latest.message)", start: false, stop: st.phase == .recording, open: true))
    }
    switch st.phase {
    case .preflight:          // M8
        return model(.recording, "開錄前檢查中…", start: false, stop: false, open: true)
    case .recording:          // M9
        let t = timer.isEmpty ? "" : " \(timer)"
        let muted = isMuted ? "（麥克風靜音中）" : ""
        return withR2(model(.recording, "錄製中\(t)\(muted)・\(name)", start: false, stop: true, open: true))
    default:                  // M10：stopping、finalizing
        return model(.recording, "收尾中…", start: false, stop: false, open: true)
    }
}

/// 狀態列的顯示文字（spec §3.4、§4.11.8，D18）：以 Character 計；超過 limit 時取前 limit-1 個字＋「…」。
/// limit < 2 視為 2。完整文字另放在該選單項的 toolTip。
func truncatedStatusTitle(_ line: String, limit: Int) -> String {
    let n = max(2, limit)
    guard line.count > n else { return line }
    return String(line.prefix(n - 1)) + "…"
}

/// menubar 單一實例鎖（spec §3.4、§4.11.10，D18）。只有 menubar 子指令會用。
enum MenuBarLockResult: Equatable {
    case acquired(fd: Int32)
    case heldByOther
    case unavailable(errno: Int32)
}

/// 上層目錄不存在先建；open(O_CREAT|O_RDWR, 0600) 後 flock(LOCK_EX|LOCK_NB)。
/// .acquired 的 fd 由呼叫端持有到 process 結束（crash 時系統自動釋放，不留殘鎖）；
/// EWOULDBLOCK → .heldByOther（先 close 自己開的 fd）；mkdir／open／其他 flock 錯誤 → .unavailable(errno)。
/// 用 flock 而非 fcntl 鎖：flock 綁 open file description，同一 process 再 open 一次也會被擋。
func acquireMenuBarLock(at lockURL: URL) -> MenuBarLockResult {
    // 逐層 mkdir，取得精確的 errno（EEXIST 略過；擋路的若是一般檔案，下面的 open 會回 ENOTDIR）
    var dir = ""
    for comp in lockURL.deletingLastPathComponent().standardizedFileURL.path.split(separator: "/") {
        dir += "/" + comp
        if mkdir(dir, 0o755) != 0, errno != EEXIST { return .unavailable(errno: errno) }
    }
    let fd = open(lockURL.path, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
    guard fd >= 0 else { return .unavailable(errno: errno) }
    var rc: Int32
    repeat { rc = flock(fd, LOCK_EX | LOCK_NB) } while rc != 0 && errno == EINTR
    if rc == 0 { return .acquired(fd: fd) }
    let e = errno
    close(fd)
    return e == EWOULDBLOCK ? .heldByOther : .unavailable(errno: e)
}

enum QuickStartDecision: Equatable {
    case start(windowID: UInt32)
    case fail(code: Int32, message: String)
}

/// 沒有預設值 → fail(2)；★ 視窗不是恰好一個 → fail(3)；否則 start。不猜選視窗。
/// starredWindowIDs＝buildWindowRows(...) 中 meeting != nil 的列（spec §3.8.2）。
func quickStartDecision(hasDefaults: Bool, starredWindowIDs: [UInt32]) -> QuickStartDecision {
    guard hasDefaults else {
        return .fail(code: 2, message: "還沒有上次的設定：請先在終端機跑一次 meeting record")
    }
    guard starredWindowIDs.count == 1, let id = starredWindowIDs.first else {
        let why = starredWindowIDs.isEmpty ? "清單裡沒有標 ★ 的會議視窗" : "清單裡有 \(starredWindowIDs.count) 個標 ★ 的會議視窗"
        return .fail(code: 3, message: "\(why)，不會猜選：請在終端機用 meeting record 選視窗")
    }
    return .start(windowID: id)
}

/// quick-start 沒有終端機：preflight 有 warn 時開錄後送一則通知（設計審查 N-2）。
/// warnText 為空 → nil；內文取前 3 行，其餘提示看 record.log。
func preflightWarnNotification(warnText: String) -> (title: String, body: String)? {
    let lines = warnText.split(separator: "\n").map(String.init).filter { !$0.isEmpty }
    guard !lines.isEmpty else { return nil }
    var body = lines.prefix(3).joined(separator: "\n")
    body += lines.count > 3 ? "\n（還有 \(lines.count - 3) 則，見 record.log）" : "\n（完整內容見 record.log）"
    return ("MeetingRecorder 已開錄（有提示）", body)
}

// Core/Lock.swift —— 開錄鎖、stop 的 pid 確認、收尾期限、暫停心跳、捨棄請求（spec §3.15、§3.20、§4.26.1、§4.27.1、
// §4.28.5、§4.42.1；design R3-D2、R3-D3）。純函式與 flock 包裝，不依賴 AppKit。
import Foundation

/// 取鎖與試鎖的重試間隔（spec §3.15：1 秒內每 100 ms 重試）。
private let lockRetryInterval: Double = 0.1

/// 逐層 mkdir（EEXIST 略過）；失敗回 errno，成功回 nil。
private func lockMakeParents(_ dir: URL) -> Int32? {
    var path = ""
    for comp in dir.standardizedFileURL.path.split(separator: "/") {
        path += "/" + comp
        if mkdir(path, 0o755) != 0, errno != EEXIST { return errno }
    }
    return nil
}

/// <home>/record.lock：open(O_CREAT|O_RDWR|O_CLOEXEC, 0600) 後以 flock(LOCK_EX|LOCK_NB) 取鎖；
/// 被別人持有時每 100 ms 重試，retrySeconds 內都拿不到 → .heldByOther；mkdir／open／其他 flock 錯誤 → .unavailable(errno)。
/// .acquired 的 fd 由呼叫端持有到程序結束（或試鎖者立刻 close 放掉）。不得在主執行緒上呼叫（會阻塞到 retrySeconds）。
func acquireRecordLock(home: URL, retrySeconds: Double = 1.0) -> MenuBarLockResult {
    if let e = lockMakeParents(home) { return .unavailable(errno: e) }
    let path = home.appendingPathComponent("record.lock").path
    let fd = open(path, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
    guard fd >= 0 else { return .unavailable(errno: errno) }
    let deadline = Date().addingTimeInterval(max(0, retrySeconds))
    while true {
        var rc: Int32
        repeat { rc = flock(fd, LOCK_EX | LOCK_NB) } while rc != 0 && errno == EINTR
        if rc == 0 { return .acquired(fd: fd) }
        let e = errno
        guard e == EWOULDBLOCK else {
            close(fd)
            return .unavailable(errno: e)
        }
        let remaining = deadline.timeIntervalSinceNow
        if remaining <= 0 {
            close(fd)
            return .heldByOther
        }
        usleep(useconds_t(min(lockRetryInterval, remaining) * 1_000_000))
    }
}

/// stop 拒絕送訊號的原因（R3-§2.2；raw value 是給人與 log 看的代號）。
enum StopRefusal: String, Equatable {
    case noLock = "no_lock", noPid = "no_pid", pidDead = "pid_dead",
         pidMismatch = "pid_mismatch", notRecorder = "not_recorder"
}

enum StopTarget: Equatable {
    case signal(pid: Int32)
    case refuse(StopRefusal)
}

/// 依序判斷（spec §4.27.1）：鎖沒被持有 → noLock；沒有 record.pid → noPid；pid 不在 → pidDead；
/// 狀態檔的 pid 與 record.pid 不同（含 nil）→ pidMismatch；command 為 nil 或不以 MeetingRecorder 結尾 → notRecorder；
/// 全部成立 → .signal(pid:)。
func stopTargetDecision(lockHeld: Bool, recordPid: Int32?, pidAlive: Bool, statusPid: Int32?, command: String?) -> StopTarget {
    guard lockHeld else { return .refuse(.noLock) }
    guard let pid = recordPid else { return .refuse(.noPid) }
    guard pidAlive else { return .refuse(.pidDead) }
    guard statusPid == pid else { return .refuse(.pidMismatch) }
    guard let cmd = command, cmd.hasSuffix("MeetingRecorder") else { return .refuse(.notRecorder) }
    return .signal(pid: pid)
}

/// 收尾總期限（秒）＝max(recordedSeconds, 0) × 3 + 600（spec §4.28.5，D14a-A）。
func finalizeDeadline(recordedSeconds: Double) -> Double {
    max(recordedSeconds, 0) * 3 + 600
}

/// 暫停中重寫 record.status.json（只更新 updatedAt）的間隔秒數（spec §4.26.6）。
let pausedHeartbeatSeconds: Double = 5

/// <home>/record.discard.json（spec §3.15）。
struct DiscardRequest: Codable, Equatable {
    var schemaVersion: Int
    var runId: String
    var requestedAt: String
}

/// 有效＝r 非 nil、runId 等於目前實例、requestedAt 可解析且 0 ≤ now − requestedAt ≤ 30 秒（spec §3.15、§4.42.1）。
func discardRequestValid(_ r: DiscardRequest?, runId: String, now: Date) -> Bool {
    guard let r, r.runId == runId, let at = ISO8601DateFormatter().date(from: r.requestedAt) else { return false }
    let age = now.timeIntervalSince(at)
    return age >= 0 && age <= 30
}

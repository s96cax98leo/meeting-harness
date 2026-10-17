// Core/BackgroundFinalize.swift —— 背景收尾的路徑與常數、tryFlock、每場狀態、條件式寫入判斷、record.pid 守門、
// 清理判斷、取消判斷、場次代號、menu bar 疊加、自動前處理去重（spec R3x §3.21–§3.24、§3.26；design R3x-D1–D15）。
// 純函式與 flock 包裝，不依賴 AppKit。名稱與簽名照 spec §3.26 逐字，build 段不得改名。
import Foundation

let backgroundFinalizeDirName = "finalizing"
let finalizeQueuePollSeconds: Double = 0.5
let backgroundPruneSeconds: Double = 86_400

// MARK: - 路徑（§3.21、§3.22）

/// <home>/finalizing/<runId>.status.json
func backgroundStatusURL(home: URL, runId: String) -> URL {
    home.appendingPathComponent(backgroundFinalizeDirName, isDirectory: true)
        .appendingPathComponent("\(runId).status.json")
}

/// <home>/finalizing/<runId>.lock
func backgroundLockURL(home: URL, runId: String) -> URL {
    home.appendingPathComponent(backgroundFinalizeDirName, isDirectory: true)
        .appendingPathComponent("\(runId).lock")
}

/// <home>/finalize.queue.lock
func finalizeQueueLockURL(home: URL) -> URL {
    home.appendingPathComponent("finalize.queue.lock")
}

/// 非空且只含 [A-Za-z0-9._-]（§3.21）。
func backgroundRunIdAllowed(_ runId: String) -> Bool {
    guard !runId.isEmpty else { return false }
    return runId.unicodeScalars.allSatisfy { c in
        switch c {
        case "A"..."Z", "a"..."z", "0"..."9", ".", "_", "-": return true
        default: return false
        }
    }
}

// MARK: - 鎖（§3.22、§3.26）

/// 逐層 mkdir（EEXIST 略過）；失敗回 errno，成功回 nil。
private func bgMakeParents(_ dir: URL) -> Int32? {
    var path = ""
    for comp in dir.standardizedFileURL.path.split(separator: "/") {
        path += "/" + comp
        if mkdir(path, 0o755) != 0, errno != EEXIST { return errno }
    }
    return nil
}

/// 逐層 mkdir；open(O_CREAT|O_RDWR|O_CLOEXEC, 0600)；flock(LOCK_EX|LOCK_NB) 只試一次（EINTR 不算一次）。
/// EWOULDBLOCK → .heldByOther（先 close）；其他錯誤 → .unavailable(errno)。.acquired 的 fd 由呼叫端持有或 close。
func tryFlock(at url: URL) -> MenuBarLockResult {
    if let e = bgMakeParents(url.deletingLastPathComponent()) { return .unavailable(errno: e) }
    let fd = open(url.path, O_CREAT | O_RDWR | O_CLOEXEC, 0o600)
    guard fd >= 0 else { return .unavailable(errno: errno) }
    var rc: Int32
    repeat { rc = flock(fd, LOCK_EX | LOCK_NB) } while rc != 0 && errno == EINTR
    if rc == 0 { return .acquired(fd: fd) }
    let e = errno
    close(fd)
    return e == EWOULDBLOCK ? .heldByOther : .unavailable(errno: e)
}

/// 旁觀者判斷「活著」（§3.22）：以 O_RDWR（不帶 O_CREAT）開檔、LOCK_EX|LOCK_NB 試一次、拿到立刻放。
/// 檔不存在或拿得到 → false；EWOULDBLOCK → true。不重試、不建任何檔。
private func bgLockHeldByOther(_ url: URL) -> Bool {
    let fd = open(url.path, O_RDWR | O_CLOEXEC)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    var rc: Int32
    repeat { rc = flock(fd, LOCK_EX | LOCK_NB) } while rc != 0 && errno == EINTR
    if rc == 0 {
        _ = flock(fd, LOCK_UN)
        return false
    }
    return errno == EWOULDBLOCK
}

// MARK: - 每場狀態（§3.21、§3.26）

struct BackgroundFinalizeJob: Equatable {
    var status: RecordStatus
    var ownerAlive: Bool
    var sessionExists: Bool = true
}

enum BackgroundJobState: String, Equatable { case queued, running, crashed, orphaned, done, failed }

func backgroundJobState(_ job: BackgroundFinalizeJob) -> BackgroundJobState {
    let st = job.status
    switch st.phase {
    case .finalizing:
        if job.ownerAlive { return st.queued == true ? .queued : .running }
        return job.sessionExists ? .crashed : .orphaned
    case .done where st.code == 0:
        return .done
    default:
        return .failed
    }
}

/// 讀 <home>/finalizing/*.status.json（讀不懂的略過）；ownerAlive 以不帶 O_CREAT 的試鎖判斷；
/// sessionExists＝status.session 非空且該路徑是存在的目錄；依 startedAt、再依 runId 遞增排序。
/// 不建立 finalizing/，也不建立任何 .lock。
func loadBackgroundJobs(home: URL) -> [BackgroundFinalizeJob] {
    let fm = FileManager.default
    let dir = home.appendingPathComponent(backgroundFinalizeDirName, isDirectory: true)
    guard let names = try? fm.contentsOfDirectory(atPath: dir.path) else { return [] }
    let suffix = ".status.json"
    var jobs: [BackgroundFinalizeJob] = []
    for name in names where name.hasSuffix(suffix) {
        let url = dir.appendingPathComponent(name)
        guard let data = try? Data(contentsOf: url),
              let st = try? JSONDecoder().decode(RecordStatus.self, from: data) else { continue }
        let runId = String(name.dropLast(suffix.count))
        let alive = bgLockHeldByOther(backgroundLockURL(home: home, runId: runId))
        var isDir: ObjCBool = false
        let exists = !st.session.isEmpty && fm.fileExists(atPath: st.session, isDirectory: &isDir) && isDir.boolValue
        jobs.append(BackgroundFinalizeJob(status: st, ownerAlive: alive, sessionExists: exists))
    }
    let f = ISO8601DateFormatter()
    return jobs.sorted { a, b in
        let sa = a.status.startedAt, sb = b.status.startedAt
        if sa != sb {
            if let da = f.date(from: sa), let db = f.date(from: sb), da != db { return da < db }
            if f.date(from: sa) == nil || f.date(from: sb) == nil { return sa < sb }
        }
        return a.status.runId < b.status.runId
    }
}

// MARK: - 進背景、排隊（§3.23 第 2、9 步）

enum BackgroundEntry: Equatable {
    case background
    case foreground(reason: String)
}

func backgroundEntryDecision(runIdAllowed: Bool, lock: MenuBarLockResult?) -> BackgroundEntry {
    guard runIdAllowed else { return .foreground(reason: "runId 含不允許的字元") }
    switch lock {
    case .acquired?: return .background
    case .heldByOther?: return .foreground(reason: "每場鎖被另一個程序持有")
    case .unavailable(let e)?: return .foreground(reason: "每場鎖開不了（errno \(e)）")
    case nil: return .foreground(reason: "沒有試每場鎖")
    }
}

enum QueueWaitStep: Equatable {
    case acquired(fd: Int32)
    case retry
    case unavailable(errno: Int32)
    case cancelled
}

/// cancelRequested → .cancelled（不呼叫 tryLock）；否則呼叫 tryLock() 一次並對映。
func queueWaitStep(cancelRequested: Bool, tryLock: () -> MenuBarLockResult) -> QueueWaitStep {
    if cancelRequested { return .cancelled }
    switch tryLock() {
    case .acquired(let fd): return .acquired(fd: fd)
    case .heldByOther: return .retry
    case .unavailable(let e): return .unavailable(errno: e)
    }
}

// MARK: - 自動前處理去重（§3.26，修正輪 B1）

/// autoPrep false → []；否則依 statuses 順序、以 runId 去重（同一 runId 只看第一筆），
/// 留下 shouldAutoPrep(...) 不是 nil、而且 runId 不在 enqueuedRunIds 的。
func autoPrepCandidates(autoPrep: Bool, statuses: [RecordStatus], seenInProgressRunIds: Set<String>,
                        lastAutoPrepRunId: String?, enqueuedRunIds: Set<String>) -> [RecordStatus] {
    guard autoPrep else { return [] }
    var seen = Set<String>()
    var out: [RecordStatus] = []
    for st in statuses {
        guard seen.insert(st.runId).inserted else { continue }
        guard !enqueuedRunIds.contains(st.runId),
              shouldAutoPrep(autoPrep: true, status: st, seenInProgressRunIds: seenInProgressRunIds,
                             lastAutoPrepRunId: lastAutoPrepRunId) != nil else { continue }
        out.append(st)
    }
    return out
}

// MARK: - 場次代號與取消確認（§3.26，修正輪 I8）

/// startedAt 可解析 → `M/d HH:mm 開始的場次`；不可解析 → `場次 <runId 前 8 個字元>`。不讀 session。
func backgroundJobLabel(_ job: BackgroundFinalizeJob, timeZone: TimeZone = .current) -> String {
    guard let start = ISO8601DateFormatter().date(from: job.status.startedAt) else {
        return "場次 \(job.status.runId.prefix(8))"
    }
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.calendar = Calendar(identifier: .gregorian)
    f.timeZone = timeZone
    f.dateFormat = "M/d HH:mm"
    return "\(f.string(from: start)) 開始的場次"
}

func backgroundCancelPrompt(target: BackgroundFinalizeJob, others: Int, timeZone: TimeZone = .current) -> String {
    let head = "要取消「\(backgroundJobLabel(target, timeZone: timeZone))」的收尾嗎？段落會保留，之後可以用 meeting record finish 收完。"
    return others > 0 ? head + "\n另有 \(others) 場收尾中／排隊，不受影響。" : head
}

// MARK: - 共用狀態檔、record.pid、清理（§3.21、§3.23、§3.24）

func sharedStatusWritable(lockAcquired: Bool, current: RecordStatus?, runId: String) -> Bool {
    guard lockAcquired else { return false }
    guard let current else { return true }
    return current.runId == runId
}

/// 去掉前後空白後是十進位整數且等於 ownPid → true；其他 → false。
func shouldRemoveRecordPid(pidFileContents: String?, ownPid: Int32) -> Bool {
    guard let raw = pidFileContents else { return false }
    let s = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !s.isEmpty, s.unicodeScalars.allSatisfy({ ("0"..."9").contains($0) }), let n = Int32(s) else { return false }
    return n == ownPid
}

/// .orphaned → true（不看時間）；.done／.failed、ownerAlive false、updatedAt 可解析且超過 backgroundPruneSeconds → true；
/// 其餘 false（.crashed 不清，留給 meeting record finish）。
func prunableBackgroundJob(_ job: BackgroundFinalizeJob, now: Date) -> Bool {
    let state = backgroundJobState(job)
    if state == .orphaned { return true }
    guard state == .done || state == .failed, !job.ownerAlive,
          let updated = ISO8601DateFormatter().date(from: job.status.updatedAt) else { return false }
    return now.timeIntervalSince(updated) > backgroundPruneSeconds
}

// MARK: - 取消（§3.26，Q4 (a)）

enum BackgroundCancelRefusal: String, Equatable {
    case recording = "recording", noJob = "no_job", ownerGone = "owner_gone",
         pidDead = "pid_dead", notRecorder = "not_recorder"
}

enum BackgroundCancelTarget: Equatable {
    case signal(pid: Int32)
    case refuse(BackgroundCancelRefusal)
}

/// 第一個 .running；沒有就第一個 .queued；都沒有 → nil。也是 menu bar 背景收尾階段顯示的那一場。
func backgroundCancelCandidate(_ jobs: [BackgroundFinalizeJob]) -> BackgroundFinalizeJob? {
    jobs.first { backgroundJobState($0) == .running } ?? jobs.first { backgroundJobState($0) == .queued }
}

/// 依序：recordLockHeld → .recording；job nil 或 phase 不是 finalizing → .noJob（Red 層補字面 (1)）；
/// !ownerAlive → .ownerGone；!pidAlive → .pidDead；command nil 或不以 MeetingRecorder 結尾 → .notRecorder；
/// 否則 .signal(pid: job.status.pid)。
func backgroundCancelDecision(job: BackgroundFinalizeJob?, recordLockHeld: Bool, pidAlive: Bool,
                              command: String?) -> BackgroundCancelTarget {
    if recordLockHeld { return .refuse(.recording) }
    guard let job, job.status.phase == .finalizing else { return .refuse(.noJob) }
    guard job.ownerAlive else { return .refuse(.ownerGone) }
    guard pidAlive else { return .refuse(.pidDead) }
    guard let cmd = command, cmd.hasSuffix("MeetingRecorder") else { return .refuse(.notRecorder) }
    return .signal(pid: job.status.pid)
}

// MARK: - menu bar 疊加（§4.54.1，修正輪 I7、I8）

private func bgCopy(_ m: MenuBarModel, statusLine: String, canStart: Bool, canStop: Bool) -> MenuBarModel {
    var r = MenuBarModel(state: m.state, symbolName: m.symbolName, statusLine: statusLine, canStart: canStart,
                         canStop: canStop, canOpenSession: m.canOpenSession, detailText: m.detailText)
    r.timerText = m.timerText
    r.paused = m.paused
    r.micMuted = m.micMuted
    r.canControl = m.canControl
    r.levelLine = m.levelLine
    r.appearance = m.appearance
    r.alertBadge = m.alertBadge
    r.spokenDuration = m.spokenDuration
    r.backgroundFinalizing = m.backgroundFinalizing
    return r
}

func applyBackgroundFinalize(_ m: MenuBarModel, status: RecordStatus?, jobs: [BackgroundFinalizeJob]) -> MenuBarModel {
    let live = jobs.filter { let s = backgroundJobState($0); return s == .running || s == .queued }
    let target = backgroundCancelCandidate(jobs)
    let sharedIsBackground = status?.background == true
    let notRecording = m.appearance == .idle || m.appearance == .failed
        || (m.appearance == .finalizing && sharedIsBackground)

    // (a)／(a2)：沒有錄製在跑 → 背景收尾階段
    let a2 = target == nil && m.appearance == .finalizing && sharedIsBackground
    if (notRecording && target != nil) || a2 {
        let shown = target?.status ?? status!
        let name = (shown.session as NSString).lastPathComponent
        // 目標就是共用狀態檔那一場、且 m 是 M6a（收尾中有告警）→ 帶告警數
        var head = "背景收尾中…"
        if let st = status, st.runId == shown.runId, m.appearance == .finalizing,
           st.phase == .stopping || st.phase == .finalizing {
            let k = st.warnings.filter { $0.kind.isAlert }.count
            if k > 0 { head = "背景收尾中…（告警 \(k) 則）" }
        }
        var line = "\(head)・\(name)"
        let n = target == nil ? 0 : live.count - 1
        if n >= 1 { line += "（另有 \(n) 場收尾中／排隊）" }
        var r = bgCopy(m, statusLine: line, canStart: true, canStop: false)
        r.backgroundFinalizing = true
        r.appearance = .finalizing
        r.detailText = m.appearance == .failed ? line + "\n" + m.detailText : line
        return r
    }

    // (b)：其他情況 → 只在結尾加附註；(c) 沒有可加的 → == m
    let others = jobs.filter { $0.status.runId != status?.runId }
    var note = ""
    if others.contains(where: { let s = backgroundJobState($0); return s == .running || s == .queued }) {
        note += "（上一場收尾中）"
    }
    if others.contains(where: { backgroundJobState($0) == .crashed }) {
        note += "（上一場收尾異常中止）"
    }
    guard !note.isEmpty else { return m }
    var r = bgCopy(m, statusLine: m.statusLine + note, canStart: m.canStart, canStop: m.canStop)
    r.detailText = m.detailText + note
    return r
}

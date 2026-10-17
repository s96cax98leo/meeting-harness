// spec R3x §3.21–§3.26（Core/BackgroundFinalize.swift，以及 Records／Appearance／Trigger 的增補）：
// 背景收尾的路徑與常數、tryFlock、每場狀態檔的選用鍵、共用狀態檔的條件式寫入、record.pid 的刪除判斷、
// 進背景判斷、排隊一步、清理判斷、每場狀態、讀每場狀態檔、取消判斷、場次代號、menu bar 套用、選單階段與分組、自動前處理去重。
// 驗收：§4.48.1–§4.48.3、§4.48.8、§4.49.1、§4.49.2、§4.50.4、§4.50.7、§4.50.8、§4.53.2、§4.53.3、§4.54.1–§4.54.3、§4.54.5。
// 「另一個子程序持有鎖」沿用 R3LockTests 的 mrtR3HoldLock（/usr/bin/perl 的 flock）；不碰 ~/.meeting-harness，一律在暫存目錄。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation

let mrtR3xBackgroundTests: [MRTCase] = [
    ("testBackgroundPaths", testBackgroundPaths),
    ("testTryFlock", testTryFlock),
    ("testRecordStatusBackgroundKeys", testRecordStatusBackgroundKeys),
    ("testSharedStatusWritable", testSharedStatusWritable),
    ("testShouldRemoveRecordPid", testShouldRemoveRecordPid),
    ("testBackgroundEntryDecision", testBackgroundEntryDecision),
    ("testQueueWaitStep", testQueueWaitStep),
    ("testBackgroundCancelDecision", testBackgroundCancelDecision),
    ("testBackgroundJobLabel", testBackgroundJobLabel),
    ("testPrunableBackgroundJob", testPrunableBackgroundJob),
    ("testBackgroundJobState", testBackgroundJobState),
    ("testLoadBackgroundJobs", testLoadBackgroundJobs),
    ("testApplyBackgroundFinalize", testApplyBackgroundFinalize),
    ("testMenuStageBackground", testMenuStageBackground),
    ("testMenuGroupsBackground", testMenuGroupsBackground),
    ("testAutoPrepCandidates", testAutoPrepCandidates),
]

// MARK: - 輔助

let mrtR3xSessionRoot = "/x/20261017"
func mrtR3xSession(_ suffix: String) -> String { "\(mrtR3xSessionRoot)/[Stand-up] 範例專案\(suffix)" }
func mrtR3xName(_ suffix: String) -> String { "[Stand-up] 範例專案\(suffix)" }

/// 每場狀態檔形狀的 RecordStatus（background 預設 true，§3.21）。
func mrtR3xStatus(_ runId: String, _ phase: RecordPhase, code: Int32 = 0, message: String = "",
                  session: String? = nil, startedAt: String = mrtStartedAt, updatedAt: String = mrtStartedAt,
                  pid: Int32 = 4242, background: Bool? = true, queued: Bool? = nil,
                  warnings: [RecordWarning] = []) -> RecordStatus {
    var s = RecordStatus(schemaVersion: 1, runId: runId, pid: pid, phase: phase, code: code, message: message,
                         session: session ?? mrtR3xSession("-\(runId)"), startedAt: startedAt, updatedAt: updatedAt,
                         segments: 3, preflight: [], warnings: warnings)
    s.background = background
    s.queued = queued
    return s
}

func mrtR3xJob(_ runId: String, _ phase: RecordPhase, code: Int32 = 0, ownerAlive: Bool, sessionExists: Bool = true,
               queued: Bool? = nil, pid: Int32 = 4242, startedAt: String = mrtStartedAt,
               updatedAt: String = mrtStartedAt) -> BackgroundFinalizeJob {
    BackgroundFinalizeJob(status: mrtR3xStatus(runId, phase, code: code, startedAt: startedAt, updatedAt: updatedAt,
                                               pid: pid, queued: queued),
                          ownerAlive: ownerAlive, sessionExists: sessionExists)
}

func mrtR3xRunning(_ runId: String, pid: Int32 = 4242) -> BackgroundFinalizeJob {
    mrtR3xJob(runId, .finalizing, ownerAlive: true, pid: pid)
}
func mrtR3xQueued(_ runId: String, pid: Int32 = 4242) -> BackgroundFinalizeJob {
    mrtR3xJob(runId, .finalizing, ownerAlive: true, queued: true, pid: pid)
}
func mrtR3xCrashed(_ runId: String) -> BackgroundFinalizeJob {
    mrtR3xJob(runId, .finalizing, ownerAlive: false, sessionExists: true)
}
func mrtR3xOrphaned(_ runId: String) -> BackgroundFinalizeJob {
    mrtR3xJob(runId, .finalizing, ownerAlive: false, sessionExists: false)
}
func mrtR3xDone(_ runId: String, code: Int32 = 0) -> BackgroundFinalizeJob {
    mrtR3xJob(runId, .done, code: code, ownerAlive: false)
}

/// 比對除 statusLine、detailText 以外的所有 MenuBarModel 欄位（§4.54.1 (b)「其他欄位與 m 完全相同」）。
func mrtR3xExpectSameExceptLines(_ a: MenuBarModel, _ m: MenuBarModel, _ tag: String,
                                 file: StaticString = #fileID, line: UInt = #line) {
    mrtEqual(a.state, m.state, "\(tag)：state", file: file, line: line)
    mrtEqual(a.symbolName, m.symbolName, "\(tag)：symbolName", file: file, line: line)
    mrtEqual(a.canStart, m.canStart, "\(tag)：canStart", file: file, line: line)
    mrtEqual(a.canStop, m.canStop, "\(tag)：canStop", file: file, line: line)
    mrtEqual(a.canOpenSession, m.canOpenSession, "\(tag)：canOpenSession", file: file, line: line)
    mrtEqual(a.timerText, m.timerText, "\(tag)：timerText", file: file, line: line)
    mrtEqual(a.paused, m.paused, "\(tag)：paused", file: file, line: line)
    mrtEqual(a.micMuted, m.micMuted, "\(tag)：micMuted", file: file, line: line)
    mrtEqual(a.canControl, m.canControl, "\(tag)：canControl", file: file, line: line)
    mrtEqual(a.levelLine, m.levelLine, "\(tag)：levelLine", file: file, line: line)
    mrtEqual(a.appearance, m.appearance, "\(tag)：appearance", file: file, line: line)
    mrtEqual(a.alertBadge, m.alertBadge, "\(tag)：alertBadge", file: file, line: line)
    mrtEqual(a.spokenDuration, m.spokenDuration, "\(tag)：spokenDuration", file: file, line: line)
    mrtEqual(a.backgroundFinalizing, m.backgroundFinalizing, "\(tag)：backgroundFinalizing", file: file, line: line)
}

// MARK: - §4.48 放鎖時機與每場狀態

// §4.48.1：路徑、常數、runId 允許字元。
func testBackgroundPaths() throws {
    let h = URL(fileURLWithPath: "/h", isDirectory: true)
    mrtEqual(backgroundStatusURL(home: h, runId: "r1").path, "/h/finalizing/r1.status.json", "backgroundStatusURL")
    mrtEqual(backgroundLockURL(home: h, runId: "r1").path, "/h/finalizing/r1.lock", "backgroundLockURL")
    mrtEqual(finalizeQueueLockURL(home: h).path, "/h/finalize.queue.lock", "finalizeQueueLockURL")
    mrtEqual(backgroundFinalizeDirName, "finalizing", "backgroundFinalizeDirName")
    mrtEqual(finalizeQueuePollSeconds, 0.5, "finalizeQueuePollSeconds")
    mrtEqual(backgroundPruneSeconds, 86_400.0, "backgroundPruneSeconds")
    mrtEqual(backgroundRunIdAllowed("8F0C-1a_b.c"), true, "\"8F0C-1a_b.c\" 應允許")
    for bad in ["", "../x", "a/b", "a b"] {
        mrtEqual(backgroundRunIdAllowed(bad), false, "\"\(bad)\" 應不允許")
    }
}

// §4.48.2、§3.26：tryFlock 只試一次；FD_CLOEXEC；被持有 → .heldByOther（0.3 秒內）；不可寫 → .unavailable；逐層建目錄。
func testTryFlock() throws {
    let fm = FileManager.default
    func fd(of r: MenuBarLockResult) -> Int32? { if case .acquired(let f) = r { return f }; return nil }

    let home = mrtR3Home("r3x-flock")
    defer { try? fm.removeItem(at: home) }

    // (1) 沒人持有 → .acquired(fd)，fd 有 FD_CLOEXEC
    let lockURL = home.appendingPathComponent("finalizing/r1.lock")
    try fm.createDirectory(at: lockURL.deletingLastPathComponent(), withIntermediateDirectories: true)
    let first = tryFlock(at: lockURL)
    if let f = fd(of: first) {
        let flags = fcntl(f, F_GETFD)
        mrtExpect(flags >= 0 && (flags & FD_CLOEXEC) != 0, "fd 應有 FD_CLOEXEC（實際 flags \(flags)）")
        close(f)
    } else {
        mrtFail("沒人持有時應為 .acquired，實際 \(first)", file: #fileID, line: #line)
    }

    // (2) 另一個子程序持有 → 0.3 秒內 .heldByOther（不重試）
    let holder = try mrtR3HoldLock(lockURL.path, seconds: 10)
    let t0 = Date()
    let held = tryFlock(at: lockURL)
    let elapsed = Date().timeIntervalSince(t0)
    holder.terminate()
    holder.waitUntilExit()
    mrtEqual(held, MenuBarLockResult.heldByOther, "被另一個子程序持有時應為 .heldByOther")
    mrtExpect(elapsed < 0.3, "tryFlock 不重試，應在 0.3 秒內回（實際 \(elapsed)）")

    // (3) 上層目錄不可寫 → .unavailable(errno)
    let ro = mrtR3Home("r3x-flock-ro")
    defer {
        try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: ro.path)
        try? fm.removeItem(at: ro)
    }
    try fm.setAttributes([.posixPermissions: 0o500], ofItemAtPath: ro.path)
    let roResult = tryFlock(at: ro.appendingPathComponent("x.lock"))
    if case .unavailable(let e) = roResult {
        mrtExpect(e != 0, "errno 應非 0")
    } else {
        mrtFail("上層目錄不可寫時應為 .unavailable(errno)，實際 \(roResult)", file: #fileID, line: #line)
    }

    // (4) 上層目錄不存在 → 逐層建立後取得
    let deep = home.appendingPathComponent("a/b/c/q.lock")
    let deepResult = tryFlock(at: deep)
    if let f = fd(of: deepResult) {
        var isDir: ObjCBool = false
        mrtExpect(fm.fileExists(atPath: home.appendingPathComponent("a/b/c").path, isDirectory: &isDir) && isDir.boolValue,
                  "上層目錄應被逐層建立")
        mrtExpect(fm.fileExists(atPath: deep.path), "鎖檔應被建立")
        close(f)
    } else {
        mrtFail("上層目錄不存在時應逐層建立並 .acquired，實際 \(deepResult)", file: #fileID, line: #line)
    }
}

// §4.48.3、§3.21、§6 第 148 條：background／queued nil 省略鍵；true 寫 true；舊狀態檔解得出來。
func testRecordStatusBackgroundKeys() throws {
    let base: Set<String> = ["schemaVersion", "runId", "pid", "phase", "code", "message", "session", "startedAt",
                             "updatedAt", "segments", "preflight", "warnings"]
    let plain = mrtStatus(.finalizing)
    mrtEqual(plain.background, nil, "預設 background 為 nil")
    mrtEqual(plain.queued, nil, "預設 queued 為 nil")
    let plainKeys = Set(mrtJSONObject(plain).keys)
    mrtEqual(plainKeys, base, "background、queued 為 nil 時鍵集合不變")

    var s = mrtStatus(.finalizing)
    s.background = true
    s.queued = true
    let obj = mrtJSONObject(s)
    mrtEqual(obj["background"] as? Bool, true, "background 為 true 時寫 true")
    mrtEqual(obj["queued"] as? Bool, true, "queued 為 true 時寫 true")
    mrtEqual(Set(obj.keys), base.union(["background", "queued"]), "只多 background、queued 兩個鍵")

    // 不含兩鍵的舊狀態檔（由 nil 的值編碼而來）解得出來、兩者為 nil
    let oldData = try JSONEncoder().encode(plain)
    let decoded = try JSONDecoder().decode(RecordStatus.self, from: oldData)
    mrtEqual(decoded.background, nil, "舊狀態檔 background 為 nil")
    mrtEqual(decoded.queued, nil, "舊狀態檔 queued 為 nil")
    mrtEqual(decoded, plain, "舊狀態檔往返相等")

    // 往返：有兩鍵的也解得回來
    let roundTrip = try JSONDecoder().decode(RecordStatus.self, from: try JSONEncoder().encode(s))
    mrtEqual(roundTrip, s, "有 background、queued 的狀態往返相等")
}

// §4.48.8、§3.26：backgroundEntryDecision。
func testBackgroundEntryDecision() throws {
    mrtEqual(backgroundEntryDecision(runIdAllowed: false, lock: .acquired(fd: 3)),
             BackgroundEntry.foreground(reason: "runId 含不允許的字元"), "(false, .acquired)")
    mrtEqual(backgroundEntryDecision(runIdAllowed: true, lock: .acquired(fd: 3)),
             BackgroundEntry.background, "(true, .acquired)")
    mrtEqual(backgroundEntryDecision(runIdAllowed: true, lock: .heldByOther),
             BackgroundEntry.foreground(reason: "每場鎖被另一個程序持有"), "(true, .heldByOther)")
    mrtEqual(backgroundEntryDecision(runIdAllowed: true, lock: .unavailable(errno: 13)),
             BackgroundEntry.foreground(reason: "每場鎖開不了（errno 13）"), "(true, .unavailable(13))")
    mrtEqual(backgroundEntryDecision(runIdAllowed: true, lock: nil),
             BackgroundEntry.foreground(reason: "沒有試每場鎖"), "(true, nil)")
}

// MARK: - §4.49 上一場不改寫、不刪除下一場的共用狀態與 pid

// §4.49.1、§3.24：sharedStatusWritable。
func testSharedStatusWritable() throws {
    var a = mrtStatus(.recording); a.runId = "a"
    var b = mrtStatus(.recording); b.runId = "b"
    mrtEqual(sharedStatusWritable(lockAcquired: false, current: nil, runId: "a"), false, "(false, nil, a)")
    mrtEqual(sharedStatusWritable(lockAcquired: true, current: nil, runId: "a"), true, "(true, nil, a)")
    mrtEqual(sharedStatusWritable(lockAcquired: true, current: a, runId: "a"), true, "(true, a, a)")
    mrtEqual(sharedStatusWritable(lockAcquired: true, current: b, runId: "a"), false, "(true, b, a)")
}

// §4.49.2、§3.23 第 5、11 步：shouldRemoveRecordPid。
func testShouldRemoveRecordPid() throws {
    let cases: [(String?, Bool)] = [
        ("123", true), ("123\n", true), (" 123 ", true),
        ("456", false), (nil, false), ("", false), ("abc", false),
    ]
    for (contents, expected) in cases {
        mrtEqual(shouldRemoveRecordPid(pidFileContents: contents, ownPid: 123), expected,
                 "pidFileContents \(String(describing: contents))")
    }
}

// MARK: - §4.50 排隊、取消

// §4.50.7、§3.26：queueWaitStep 的四種結果與 tryLock 呼叫次數；另以暫存目錄實跑排隊鎖。
func testQueueWaitStep() throws {
    var calls = 0
    mrtEqual(queueWaitStep(cancelRequested: true, tryLock: { calls += 1; return .acquired(fd: 5) }),
             QueueWaitStep.cancelled, "cancelRequested true")
    mrtEqual(calls, 0, "cancelRequested true 時不呼叫 tryLock")

    calls = 0
    mrtEqual(queueWaitStep(cancelRequested: false, tryLock: { calls += 1; return .acquired(fd: 5) }),
             QueueWaitStep.acquired(fd: 5), ".acquired(fd: 5)")
    mrtEqual(calls, 1, ".acquired 時 tryLock 呼叫 1 次")

    calls = 0
    mrtEqual(queueWaitStep(cancelRequested: false, tryLock: { calls += 1; return .heldByOther }),
             QueueWaitStep.retry, ".heldByOther → .retry")
    mrtEqual(calls, 1, ".heldByOther 時 tryLock 呼叫 1 次")

    calls = 0
    mrtEqual(queueWaitStep(cancelRequested: false, tryLock: { calls += 1; return .unavailable(errno: 2) }),
             QueueWaitStep.unavailable(errno: 2), ".unavailable(errno: 2)")
    mrtEqual(calls, 1, ".unavailable 時 tryLock 呼叫 1 次")

    // 實跑：子程序持有排隊鎖時連 3 次 .retry；子程序結束後下一次 .acquired
    let fm = FileManager.default
    let home = mrtR3Home("r3x-queue")
    defer { try? fm.removeItem(at: home) }
    let qURL = finalizeQueueLockURL(home: home)
    let holder = try mrtR3HoldLock(qURL.path, seconds: 30)
    for i in 1...3 {
        let r = queueWaitStep(cancelRequested: false, tryLock: { tryFlock(at: qURL) })
        mrtEqual(r, QueueWaitStep.retry, "子程序持有排隊鎖時第 \(i) 次應為 .retry")
    }
    holder.terminate()
    holder.waitUntilExit()
    let after = queueWaitStep(cancelRequested: false, tryLock: { tryFlock(at: qURL) })
    if case .acquired(let f) = after {
        close(f)
    } else {
        mrtFail("子程序結束後應為 .acquired，實際 \(after)", file: #fileID, line: #line)
    }
}

// §4.50.4、§3.26：backgroundCancelCandidate 與 backgroundCancelDecision（Q4 (a)）。
func testBackgroundCancelDecision() throws {
    // candidate
    let doneA = mrtR3xDone("A"), queuedC = mrtR3xQueued("C"), runningD = mrtR3xRunning("D"), queuedE = mrtR3xQueued("E")
    mrtEqual(backgroundCancelCandidate([doneA, queuedC, runningD]), runningD, "[done A, queued C, running D] → D")
    mrtEqual(backgroundCancelCandidate([queuedC, queuedE]), queuedC, "[queued C, queued E] → C")
    mrtEqual(backgroundCancelCandidate([mrtR3xCrashed("A"), mrtR3xDone("B")]), nil, "[crashed A, done B] → nil")
    mrtEqual(backgroundCancelCandidate([]), nil, "[] → nil")

    // decision（依 §3.26 的順序）
    let rec = "/Applications/x/MeetingRecorder"
    for live in [mrtR3xRunning("D", pid: 77), mrtR3xQueued("C", pid: 77)] {
        let tag = live.status.queued == true ? "queued" : "running"
        mrtEqual(backgroundCancelDecision(job: live, recordLockHeld: true, pidAlive: true, command: rec),
                 BackgroundCancelTarget.refuse(.recording), "\(tag)：recordLockHeld → .recording")
        mrtEqual(backgroundCancelDecision(job: live, recordLockHeld: false, pidAlive: false, command: rec),
                 BackgroundCancelTarget.refuse(.pidDead), "\(tag)：pidAlive false → .pidDead")
        mrtEqual(backgroundCancelDecision(job: live, recordLockHeld: false, pidAlive: true, command: "/bin/sleep"),
                 BackgroundCancelTarget.refuse(.notRecorder), "\(tag)：/bin/sleep → .notRecorder")
        mrtEqual(backgroundCancelDecision(job: live, recordLockHeld: false, pidAlive: true, command: nil),
                 BackgroundCancelTarget.refuse(.notRecorder), "\(tag)：command nil → .notRecorder")
        mrtEqual(backgroundCancelDecision(job: live, recordLockHeld: false, pidAlive: true, command: rec),
                 BackgroundCancelTarget.signal(pid: 77), "\(tag)：全部成立 → .signal(77)")
        var gone = live
        gone.ownerAlive = false
        mrtEqual(backgroundCancelDecision(job: gone, recordLockHeld: false, pidAlive: true, command: rec),
                 BackgroundCancelTarget.refuse(.ownerGone), "\(tag)：ownerAlive false → .ownerGone")
    }
    mrtEqual(backgroundCancelDecision(job: nil, recordLockHeld: false, pidAlive: true, command: rec),
             BackgroundCancelTarget.refuse(.noJob), "job nil → .noJob")
    mrtEqual(backgroundCancelDecision(job: doneA, recordLockHeld: false, pidAlive: true, command: rec),
             BackgroundCancelTarget.refuse(.noJob), "done → .noJob")
    // 順序：recording 最先（job nil 也是 .recording）
    mrtEqual(backgroundCancelDecision(job: nil, recordLockHeld: true, pidAlive: false, command: nil),
             BackgroundCancelTarget.refuse(.recording), "順序：recording 在 noJob 前")

    // rawValue
    mrtEqual(BackgroundCancelRefusal.recording.rawValue, "recording")
    mrtEqual(BackgroundCancelRefusal.noJob.rawValue, "no_job")
    mrtEqual(BackgroundCancelRefusal.ownerGone.rawValue, "owner_gone")
    mrtEqual(BackgroundCancelRefusal.pidDead.rawValue, "pid_dead")
    mrtEqual(BackgroundCancelRefusal.notRecorder.rawValue, "not_recorder")
}

// §4.50.8、§3.26：backgroundJobLabel（不含會議名）與 backgroundCancelPrompt。
func testBackgroundJobLabel() throws {
    let tz = TimeZone(secondsFromGMT: 28800)!
    let session = "/x/20261017/[Stand-up] 範例專案"
    var s = mrtR3xStatus("8F0C1A2B-xyz", .finalizing, session: session, startedAt: "2026-10-17T09:05:00+08:00")
    let job = BackgroundFinalizeJob(status: s, ownerAlive: true)
    let label = backgroundJobLabel(job, timeZone: tz)
    mrtEqual(label, "10/17 09:05 開始的場次", "startedAt 可解析")
    mrtExpect(!label.contains("範例專案"), "場次代號不得含會議名（實際「\(label)」）")

    s.startedAt = "not-a-date"
    let bad = backgroundJobLabel(BackgroundFinalizeJob(status: s, ownerAlive: true), timeZone: tz)
    mrtEqual(bad, "場次 8F0C1A2B", "startedAt 讀不懂 → runId 前 8 字")
    mrtExpect(!bad.contains("範例專案"), "場次代號不得含會議名（實際「\(bad)」）")

    let p0 = backgroundCancelPrompt(target: job, others: 0, timeZone: tz)
    mrtExpect(!p0.contains("\n"), "others 0 時恰為一行（實際「\(p0)」）")
    mrtContains(p0, "「10/17 09:05 開始的場次」")
    mrtContains(p0, "meeting record finish")
    mrtEqual(p0, "要取消「10/17 09:05 開始的場次」的收尾嗎？段落會保留，之後可以用 meeting record finish 收完。",
             "others 0 的全文（§3.26）")
    mrtExpect(!p0.contains("範例專案"), "確認框不得含會議名")

    let p2 = backgroundCancelPrompt(target: job, others: 2, timeZone: tz)
    mrtEqual(p2, p0 + "\n另有 2 場收尾中／排隊，不受影響。", "others 2 多一行")
}

// MARK: - §4.53 清理與每場狀態

// §4.53.2、§3.26：prunableBackgroundJob。
func testPrunableBackgroundJob() throws {
    let now = mrtDate("2026-10-17T12:00:00+08:00")
    let f = ISO8601DateFormatter()
    func ago(_ hours: Double) -> String { f.string(from: now.addingTimeInterval(-hours * 3600)) }

    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .done, ownerAlive: false, updatedAt: ago(25)), now: now), true,
             "done、ownerAlive false、25 小時前")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .done, ownerAlive: false, updatedAt: ago(23)), now: now), false,
             "done、23 小時前")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .failed, code: 5, ownerAlive: false, updatedAt: ago(25)), now: now), true,
             "failed、25 小時前")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .finalizing, ownerAlive: false, sessionExists: true, updatedAt: ago(25)),
                                   now: now), false, "crashed、25 小時前不清")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .finalizing, ownerAlive: false, sessionExists: false,
                                             updatedAt: ago(1.0 / 60)), now: now), true, "orphaned、1 分鐘前也清")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .done, ownerAlive: true, updatedAt: ago(25)), now: now), false,
             "done 但 ownerAlive true")
    mrtEqual(prunableBackgroundJob(mrtR3xJob("a", .done, ownerAlive: false, updatedAt: "not-a-date"), now: now), false,
             "updatedAt 讀不懂")
}

// §4.53.3、§3.26：backgroundJobState。
func testBackgroundJobState() throws {
    mrtEqual(backgroundJobState(mrtR3xJob("a", .finalizing, ownerAlive: true, queued: true)), BackgroundJobState.queued,
             "finalizing＋alive＋queued")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .finalizing, ownerAlive: true)), BackgroundJobState.running,
             "finalizing＋alive")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .finalizing, ownerAlive: false, sessionExists: true)),
             BackgroundJobState.crashed, "finalizing＋!alive＋sessionExists")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .finalizing, ownerAlive: false, sessionExists: false)),
             BackgroundJobState.orphaned, "finalizing＋!alive＋!sessionExists")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .done, code: 0, ownerAlive: false)), BackgroundJobState.done, "done／0")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .done, code: 5, ownerAlive: false)), BackgroundJobState.failed, "done／5")
    mrtEqual(backgroundJobState(mrtR3xJob("a", .failed, code: 5, ownerAlive: false)), BackgroundJobState.failed, "failed")
    // sessionExists 預設 true（§3.26 的 struct 預設值）
    let dflt = BackgroundFinalizeJob(status: mrtR3xStatus("a", .finalizing), ownerAlive: false)
    mrtEqual(dflt.sessionExists, true, "sessionExists 預設 true")
}

// §4.53.3、§3.21、§3.22：loadBackgroundJobs 讀每場狀態檔、略過壞 JSON、以不帶 O_CREAT 的試鎖判斷活著、依 startedAt 排序。
func testLoadBackgroundJobs() throws {
    let fm = FileManager.default
    let home = mrtR3Home("r3x-load")
    defer { try? fm.removeItem(at: home) }
    let sessions = mrtR3Home("r3x-load-sessions")
    defer { try? fm.removeItem(at: sessions) }
    let liveSession = sessions.appendingPathComponent("[Stand-up] 範例專案-1")
    let crashedSession = sessions.appendingPathComponent("[Stand-up] 範例專案-2")
    try fm.createDirectory(at: liveSession, withIntermediateDirectories: true)
    try fm.createDirectory(at: crashedSession, withIntermediateDirectories: true)
    let missingSession = sessions.appendingPathComponent("[Stand-up] 範例專案-不存在").path

    let dir = home.appendingPathComponent(backgroundFinalizeDirName, isDirectory: true)
    try fm.createDirectory(at: dir, withIntermediateDirectories: true)

    // runId 的字母順序故意與 startedAt 順序不同，驗「依 startedAt 排序」
    let liveStatus = mrtR3xStatus("zz-live", .finalizing, session: liveSession.path, startedAt: "2026-10-17T09:00:00+08:00")
    let crashedStatus = mrtR3xStatus("aa-crashed", .finalizing, session: crashedSession.path,
                                     startedAt: "2026-10-17T10:00:00+08:00")
    let orphanStatus = mrtR3xStatus("mm-orphan", .finalizing, session: missingSession,
                                    startedAt: "2026-10-17T11:00:00+08:00")
    try writeJSONAtomically(liveStatus, to: backgroundStatusURL(home: home, runId: liveStatus.runId))
    try writeJSONAtomically(crashedStatus, to: backgroundStatusURL(home: home, runId: crashedStatus.runId))
    try writeJSONAtomically(orphanStatus, to: backgroundStatusURL(home: home, runId: orphanStatus.runId))
    try Data("{ not json".utf8).write(to: backgroundStatusURL(home: home, runId: "broken"))

    let holder = try mrtR3HoldLock(backgroundLockURL(home: home, runId: liveStatus.runId).path, seconds: 30)
    defer { holder.terminate(); holder.waitUntilExit() }

    func lockFiles() -> Set<String> {
        Set(((try? fm.contentsOfDirectory(atPath: dir.path)) ?? []).filter { $0.hasSuffix(".lock") })
    }
    let locksBefore = lockFiles()
    mrtEqual(locksBefore, ["zz-live.lock"], "前置：只有持鎖那一場有鎖檔")

    let jobs = loadBackgroundJobs(home: home)
    mrtEqual(jobs.map { $0.status.runId }, ["zz-live", "aa-crashed", "mm-orphan"], "回三筆、依 startedAt 排序、壞 JSON 略過")
    mrtEqual(jobs.map { $0.ownerAlive }, [true, false, false], "ownerAlive 依序")
    mrtEqual(jobs.map { $0.sessionExists }, [true, true, false], "sessionExists 依序")
    if jobs.count == 3 {
        mrtEqual(jobs[0].status, liveStatus, "讀回的狀態與寫入相同")
    }
    mrtEqual(lockFiles(), locksBefore, "loadBackgroundJobs 不得新建任何 .lock")

    // 沒有 finalizing/ 目錄 → 空陣列
    let empty = mrtR3Home("r3x-load-empty")
    defer { try? fm.removeItem(at: empty) }
    mrtEqual(loadBackgroundJobs(home: empty).count, 0, "沒有 finalizing/ 時回空陣列")
    mrtExpect(!fm.fileExists(atPath: empty.appendingPathComponent(backgroundFinalizeDirName).path),
              "沒有 finalizing/ 時不得建立它")
}

// MARK: - §4.54 menu bar

// §4.54.1：applyBackgroundFinalize。
func testApplyBackgroundFinalize() throws {
    let now = mrtNow(500)
    let busy = "背景收尾中…"

    // (a) idle（M1）＋一個 running（I7）
    do {
        let m = menuBarModel(status: nil, pidAlive: false, now: now)
        let a = applyBackgroundFinalize(m, status: nil, jobs: [mrtR3xRunning("A")])
        let line = "\(busy)・\(mrtR3xName("-A"))"
        mrtEqual(a.backgroundFinalizing, true, "idle＋running：backgroundFinalizing")
        mrtEqual(a.canStart, true, "idle＋running：canStart")
        mrtEqual(a.appearance, MenuBarAppearance.finalizing, "idle＋running：appearance")
        mrtEqual(a.canStop, false, "idle＋running：canStop")
        mrtEqual(a.statusLine, line, "idle＋running：statusLine")
        mrtEqual(a.detailText, line, "idle＋running：detailText＝statusLine")
    }

    // (a) failed（M2）＋一個 queued → detailText 帶上一次的錯誤
    do {
        var st = mrtStatus(.preflightFailed, code: 2, message: "麥克風沒有授權")
        st.runId = "B"
        let m = menuBarModel(status: st, pidAlive: false, now: now)
        mrtEqual(m.appearance, MenuBarAppearance.failed, "前置：M2 為 .failed")
        let a = applyBackgroundFinalize(m, status: st, jobs: [mrtR3xQueued("A")])
        let line = "\(busy)・\(mrtR3xName("-A"))"
        mrtEqual(a.backgroundFinalizing, true, "M2＋queued：backgroundFinalizing")
        mrtEqual(a.canStart, true, "M2＋queued：canStart")
        mrtEqual(a.appearance, MenuBarAppearance.finalizing, "M2＋queued：appearance")
        mrtEqual(a.canStop, false, "M2＋queued：canStop")
        mrtEqual(a.statusLine, line, "M2＋queued：statusLine")
        mrtEqual(a.detailText, line + "\n" + m.detailText, "M2＋queued：detailText＝statusLine＋換行＋m.detailText")
        mrtContains(a.detailText, m.detailText)
    }

    // (a) 共用狀態檔是 queued 的 A、另有 running 的 D（I8）→ 顯示 D，另有 1 場
    do {
        let stA = mrtR3xStatus("A", .finalizing, queued: true)
        let m = menuBarModel(status: stA, pidAlive: true, now: now)
        let a = applyBackgroundFinalize(m, status: stA, jobs: [mrtR3xQueued("A"), mrtR3xRunning("D")])
        let line = "\(busy)・\(mrtR3xName("-D"))（另有 1 場收尾中／排隊）"
        mrtEqual(a.backgroundFinalizing, true, "A queued＋D running：backgroundFinalizing")
        mrtEqual(a.canStart, true, "A queued＋D running：canStart")
        mrtEqual(a.statusLine, line, "A queued＋D running：statusLine 是 D")
        mrtEqual(a.detailText, line, "A queued＋D running：detailText")
    }

    // (a) M6a：目標就是共用狀態檔那一場、且有告警
    do {
        let stA = mrtR3xStatus("A", .finalizing, warnings: [mrtAlertNew])
        let m = menuBarModel(status: stA, pidAlive: true, now: now)
        mrtEqual(m.statusLine, "收尾中…（告警 1 則）", "前置：M6a")
        let a = applyBackgroundFinalize(m, status: stA, jobs: [mrtR3xRunning("A")])
        mrtEqual(a.statusLine, "背景收尾中…（告警 1 則）・\(mrtR3xName("-A"))", "M6a：statusLine 帶告警數")
        mrtEqual(a.backgroundFinalizing, true, "M6a：backgroundFinalizing")
    }

    // (a2) 共用狀態檔 background true、每場檔還沒讀到 → 以共用狀態檔的場次名，n＝0
    do {
        let stA = mrtR3xStatus("A", .finalizing, queued: true)
        let m = menuBarModel(status: stA, pidAlive: true, now: now)
        let a = applyBackgroundFinalize(m, status: stA, jobs: [])
        let line = "\(busy)・\(mrtR3xName("-A"))"
        mrtEqual(a.backgroundFinalizing, true, "(a2)：backgroundFinalizing")
        mrtEqual(a.canStart, true, "(a2)：canStart")
        mrtEqual(a.appearance, MenuBarAppearance.finalizing, "(a2)：appearance")
        mrtEqual(a.canStop, false, "(a2)：canStop")
        mrtEqual(a.statusLine, line, "(a2)：statusLine")
        mrtEqual(a.detailText, line, "(a2)：detailText")
    }

    // (b) recording（B）＋上一場 running → 結尾加（上一場收尾中）
    let recStatus = mrtR2Recording(now: now, startedAgo: 125, pausedSeconds: 5)
    let rec = menuBarModel(status: recStatus, pidAlive: true, now: now)
    mrtEqual(rec.appearance, MenuBarAppearance.recording, "前置：錄製中")
    do {
        let a = applyBackgroundFinalize(rec, status: recStatus, jobs: [mrtR3xRunning("A")])
        mrtEqual(a.statusLine, rec.statusLine + "（上一場收尾中）", "recording＋running：statusLine")
        mrtEqual(a.detailText, rec.detailText + "（上一場收尾中）", "recording＋running：detailText")
        mrtR3xExpectSameExceptLines(a, rec, "recording＋running")
    }
    // (b) recording＋上一場 queued 也算 live
    do {
        let a = applyBackgroundFinalize(rec, status: recStatus, jobs: [mrtR3xQueued("A")])
        mrtEqual(a.statusLine, rec.statusLine + "（上一場收尾中）", "recording＋queued：statusLine")
        mrtR3xExpectSameExceptLines(a, rec, "recording＋queued")
    }
    // (b) recording＋running＋crashed → 兩個附註依序
    do {
        let a = applyBackgroundFinalize(rec, status: recStatus, jobs: [mrtR3xCrashed("C"), mrtR3xRunning("A")])
        mrtEqual(a.statusLine, rec.statusLine + "（上一場收尾中）（上一場收尾異常中止）", "recording＋running＋crashed：statusLine")
        mrtEqual(a.detailText, rec.detailText + "（上一場收尾中）（上一場收尾異常中止）",
                 "recording＋running＋crashed：detailText")
        mrtR3xExpectSameExceptLines(a, rec, "recording＋running＋crashed")
    }
    // (b) recording＋orphaned → == m
    mrtEqual(applyBackgroundFinalize(rec, status: recStatus, jobs: [mrtR3xOrphaned("O")]), rec, "recording＋orphaned → == m")
    // (b) jobs 中 runId 等於 status.runId 的不算「上一場」
    do {
        var selfJob = mrtR3xRunning("self")
        selfJob.status.runId = recStatus.runId
        mrtEqual(applyBackgroundFinalize(rec, status: recStatus, jobs: [selfJob]), rec, "runId 與共用狀態檔相同的不加附註")
    }
    // (b) 沒有錄製在跑、live 為空、只有 crashed → 加（上一場收尾異常中止），其他欄位不變
    do {
        let idle = menuBarModel(status: nil, pidAlive: false, now: now)
        let a = applyBackgroundFinalize(idle, status: nil, jobs: [mrtR3xCrashed("C")])
        mrtEqual(a.statusLine, idle.statusLine + "（上一場收尾異常中止）", "idle＋crashed：statusLine")
        mrtR3xExpectSameExceptLines(a, idle, "idle＋crashed")
    }

    // (c) jobs 為空且 (a2) 不成立 → == m
    let idle = menuBarModel(status: nil, pidAlive: false, now: now)
    mrtEqual(applyBackgroundFinalize(idle, status: nil, jobs: []), idle, "idle＋[] → == m")
    mrtEqual(applyBackgroundFinalize(rec, status: recStatus, jobs: []), rec, "recording＋[] → == m")
    let fin = menuBarModel(status: mrtStatus(.finalizing), pidAlive: true, now: now)
    mrtEqual(applyBackgroundFinalize(fin, status: mrtStatus(.finalizing), jobs: []), fin,
             "前景收尾（沒有 background）＋[] → == m")
}

// §4.54.2、§6 第 148 條：menuStage 的 backgroundFinalizing 階段。
func testMenuStageBackground() throws {
    let now = mrtNow(500)
    var fin = menuBarModel(status: mrtStatus(.finalizing), pidAlive: true, now: now)
    mrtEqual(fin.backgroundFinalizing, false, "預設 backgroundFinalizing 為 false")
    mrtEqual(menuStage(fin), MenuStage.finalizing, "finalizing＋false → .finalizing")
    fin.backgroundFinalizing = true
    mrtEqual(menuStage(fin), MenuStage.backgroundFinalizing, "finalizing＋true → .backgroundFinalizing")

    var idle = menuBarModel(status: nil, pidAlive: false, now: now)
    idle.backgroundFinalizing = true
    mrtEqual(menuStage(idle), MenuStage.idle, "appearance 不是 .finalizing 時照 §4.41.1")

    let applied = applyBackgroundFinalize(menuBarModel(status: nil, pidAlive: false, now: now), status: nil,
                                          jobs: [mrtR3xRunning("A")])
    mrtEqual(menuStage(applied), MenuStage.backgroundFinalizing, "applyBackgroundFinalize (a) 的結果 → .backgroundFinalizing")

    mrtEqual(MenuStage.backgroundFinalizing.rawValue, "backgroundFinalizing")
}

// §4.54.3：menuGroups(stage: .backgroundFinalizing)；既有四個階段不變。
func testMenuGroupsBackground() throws {
    mrtEqual(menuGroups(stage: .backgroundFinalizing),
             [[.status], [.start, .recordWindow, .saveTo], [.cancelFinalize], [.openSession, .showLast], [.preferences, .quit]],
             ".backgroundFinalizing 的分組")
    for (stage, groups) in mrtR3ExpectedGroups {
        mrtEqual(menuGroups(stage: stage), groups, "既有階段 \(stage.rawValue) 的分組不變")
    }
}

// §4.54.5、§3.26（修正輪 B1）：autoPrepCandidates 去重；模擬三次 refresh 合計恰 2 筆。
func testAutoPrepCandidates() throws {
    let sharedR2 = mrtR3xStatus("r2", .done, background: nil)
    let perR1 = mrtR3xStatus("r1", .done)
    let perR2 = mrtR3xStatus("r2", .done)
    let statuses = [sharedR2, perR1, perR2]
    let seen: Set<String> = ["r1", "r2"]

    var enqueued = Set<String>()
    var last: String? = nil
    var perRefresh: [[String]] = []
    for _ in 0..<3 {
        let c = autoPrepCandidates(autoPrep: true, statuses: statuses, seenInProgressRunIds: seen,
                                   lastAutoPrepRunId: last, enqueuedRunIds: enqueued)
        perRefresh.append(c.map { $0.runId })
        for s in c {
            enqueued.insert(s.runId)
            last = s.runId
        }
    }
    mrtEqual(perRefresh, [["r2", "r1"], [], []], "三次 refresh 依序為 [r2, r1]、[]、[]")
    mrtEqual(perRefresh.reduce(0) { $0 + $1.count }, 2, "三次合計恰 2 筆")

    mrtEqual(autoPrepCandidates(autoPrep: false, statuses: statuses, seenInProgressRunIds: seen,
                                lastAutoPrepRunId: nil, enqueuedRunIds: []).count, 0, "autoPrep false → []")

    var discardedR1 = perR1
    discardedR1.discarded = true
    let withDiscarded = autoPrepCandidates(autoPrep: true, statuses: [sharedR2, discardedR1, perR2],
                                           seenInProgressRunIds: seen, lastAutoPrepRunId: nil, enqueuedRunIds: [])
    mrtExpect(!withDiscarded.map { $0.runId }.contains("r1"), "r1 discarded → 不含 r1（實際 \(withDiscarded.map { $0.runId })）")

    let notSeen = autoPrepCandidates(autoPrep: true, statuses: statuses, seenInProgressRunIds: ["r2"],
                                     lastAutoPrepRunId: nil, enqueuedRunIds: [])
    mrtExpect(!notSeen.map { $0.runId }.contains("r1"), "r1 不在 seenInProgressRunIds → 不含 r1（實際 \(notSeen.map { $0.runId })）")
}

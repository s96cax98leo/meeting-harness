// spec §3.15、§3.16、§3.20（Core/Lock.swift、Core/Settings.swift）：開錄鎖、stop 的 pid 確認、收尾期限、暫停心跳、
// 捨棄請求、首次引導寫 record.defaults.json 的合併、menubar.settings.json。
// 驗收：§4.26.1、§4.26.6、§4.27.1、§4.28.5、§4.40.6、§4.42.1、§4.42.5、§4.43.1、§4.43.4。
// 「另一個子程序持有鎖」用 /usr/bin/perl 的 flock 模擬（與 Swift 端同為 flock(2)）；不碰 ~/.meeting-harness，一律在暫存目錄。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation

let mrtR3LockTests: [MRTCase] = [
    ("testAcquireRecordLock", testAcquireRecordLock),
    ("testPausedHeartbeatConstant", testPausedHeartbeatConstant),
    ("testStopTargetDecision", testStopTargetDecision),
    ("testFinalizeDeadline", testFinalizeDeadline),
    ("testDiscardRequestValid", testDiscardRequestValid),
    ("testDiscardedNoAutoPrep", testDiscardedNoAutoPrep),
    ("testMergedDefaults", testMergedDefaults),
    ("testMenuBarSettingsDefaults", testMenuBarSettingsDefaults),
    ("testMenuBarSettingsRoundTrip", testMenuBarSettingsRoundTrip),
]

/// 建一個暫存 home（已建立）。
func mrtR3Home(_ tag: String) -> URL {
    let u = mrtR2TempDir("r3-\(tag)")
    try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
    return u
}

/// 另一個子程序以 flock(LOCK_EX) 持有 path，持有 seconds 秒後結束。回傳時子程序已確定拿到鎖（讀到 "locked"）。
func mrtR3HoldLock(_ path: String, seconds: Double) throws -> Process {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/perl")
    p.arguments = ["-e",
                   "use Fcntl qw(:flock O_CREAT O_RDWR); sysopen(my $f, $ARGV[0], O_CREAT|O_RDWR, 0600) or die \"open\"; "
                   + "flock($f, LOCK_EX) or die \"flock\"; $| = 1; print \"locked\\n\"; "
                   + "select(undef, undef, undef, $ARGV[1]); exit 0;",
                   path, String(seconds)]
    let out = Pipe()
    p.standardOutput = out
    try p.run()
    var got = ""
    while !got.contains("locked") {
        let d = out.fileHandleForReading.availableData   // 阻塞到有資料或 EOF
        if d.isEmpty { break }
        got += String(decoding: d, as: UTF8.self)
    }
    if !got.contains("locked") { mrtFail("持鎖子程序沒有回報 locked", file: #fileID, line: #line) }
    return p
}

// §4.26.1、§3.15：acquireRecordLock 的四種情況與 FD_CLOEXEC。
func testAcquireRecordLock() throws {
    let fm = FileManager.default
    func fd(of r: MenuBarLockResult) -> Int32? { if case .acquired(let f) = r { return f }; return nil }

    // (1) 沒人持有 → .acquired(fd)，fd 有 FD_CLOEXEC，record.lock 權限 0600
    let home = mrtR3Home("lock")
    defer { try? fm.removeItem(at: home) }
    let lockPath = home.appendingPathComponent("record.lock").path
    let first = acquireRecordLock(home: home)
    if let f = fd(of: first) {
        mrtExpect(f >= 0, "fd 應 ≥ 0")
        let flags = fcntl(f, F_GETFD)
        mrtExpect(flags >= 0 && (flags & FD_CLOEXEC) != 0, "fd 應有 FD_CLOEXEC（實際 flags \(flags)）")
        mrtExpect(fm.fileExists(atPath: lockPath), "<home>/record.lock 應被建立")
        if let perm = (try? fm.attributesOfItem(atPath: lockPath))?[.posixPermissions] as? NSNumber {
            mrtEqual(perm.intValue & 0o777, 0o600, "record.lock 權限應為 0600")
        }
        close(f)
    } else {
        mrtFail("沒人持有時應為 .acquired，實際 \(first)", file: #fileID, line: #line)
    }

    // (2) 另一個子程序持續持有 → 約 retrySeconds 後 .heldByOther（retrySeconds 0.3：耗時介於 0.25 與 1.0 秒）
    let holder = try mrtR3HoldLock(lockPath, seconds: 10)
    let t0 = Date()
    let held = acquireRecordLock(home: home, retrySeconds: 0.3)
    let elapsed = Date().timeIntervalSince(t0)
    holder.terminate()
    holder.waitUntilExit()
    mrtEqual(held, MenuBarLockResult.heldByOther, "持續被持有時應為 .heldByOther")
    mrtExpect(elapsed >= 0.25 && elapsed <= 1.0, "retrySeconds 0.3 的耗時應介於 0.25 與 1.0 秒（實際 \(elapsed)）")

    // (3) 另一個子程序持有 0.2 秒後放掉 → retrySeconds 1.0 內取得
    let brief = try mrtR3HoldLock(lockPath, seconds: 0.2)
    let third = acquireRecordLock(home: home, retrySeconds: 1.0)
    brief.waitUntilExit()
    if let f = fd(of: third) { close(f) } else {
        mrtFail("持有 0.2 秒後放掉時應在重試內 .acquired，實際 \(third)", file: #fileID, line: #line)
    }

    // (4) home 不可寫 → .unavailable(errno)
    let ro = mrtR3Home("lock-ro")
    defer {
        try? fm.setAttributes([.posixPermissions: 0o700], ofItemAtPath: ro.path)
        try? fm.removeItem(at: ro)
    }
    try fm.setAttributes([.posixPermissions: 0o500], ofItemAtPath: ro.path)
    let ro1 = acquireRecordLock(home: ro, retrySeconds: 0.3)
    if case .unavailable(let e) = ro1 {
        mrtExpect(e != 0, "errno 應非 0")
    } else {
        mrtFail("home 不可寫時應為 .unavailable(errno)，實際 \(ro1)", file: #fileID, line: #line)
    }
}

// §4.26.6：暫停心跳 5 秒。
func testPausedHeartbeatConstant() throws {
    mrtEqual(pausedHeartbeatSeconds, 5.0, "pausedHeartbeatSeconds")
}

// §4.27.1：stopTargetDecision 依序判斷五項。
func testStopTargetDecision() throws {
    let rec = "/Applications/x/MeetingRecorder"
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: 123, command: rec),
             StopTarget.signal(pid: 123), "全部成立")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: 456, command: rec),
             StopTarget.refuse(.pidMismatch), "statusPid 不同")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: nil, command: rec),
             StopTarget.refuse(.pidMismatch), "statusPid nil 也算不同")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: 123, command: "/bin/sleep"),
             StopTarget.refuse(.notRecorder), "command 不以 MeetingRecorder 結尾")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: 123, command: nil),
             StopTarget.refuse(.notRecorder), "command nil")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: false, statusPid: 123, command: rec),
             StopTarget.refuse(.pidDead), "pid 不在")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: nil, pidAlive: true, statusPid: 123, command: rec),
             StopTarget.refuse(.noPid), "沒有 record.pid")
    mrtEqual(stopTargetDecision(lockHeld: false, recordPid: 123, pidAlive: true, statusPid: 123, command: rec),
             StopTarget.refuse(.noLock), "鎖沒被持有")
    // 判斷順序：前面的條件先回
    mrtEqual(stopTargetDecision(lockHeld: false, recordPid: nil, pidAlive: false, statusPid: nil, command: nil),
             StopTarget.refuse(.noLock), "順序：noLock 最先")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: nil, pidAlive: false, statusPid: nil, command: nil),
             StopTarget.refuse(.noPid), "順序：noPid 在 pidDead 前")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: false, statusPid: 456, command: nil),
             StopTarget.refuse(.pidDead), "順序：pidDead 在 pidMismatch 前")
    mrtEqual(stopTargetDecision(lockHeld: true, recordPid: 123, pidAlive: true, statusPid: 456, command: nil),
             StopTarget.refuse(.pidMismatch), "順序：pidMismatch 在 notRecorder 前")
    // raw value（R3-§2.2 的拒絕原因字串）
    mrtEqual(StopRefusal.noLock.rawValue, "no_lock")
    mrtEqual(StopRefusal.noPid.rawValue, "no_pid")
    mrtEqual(StopRefusal.pidDead.rawValue, "pid_dead")
    mrtEqual(StopRefusal.pidMismatch.rawValue, "pid_mismatch")
    mrtEqual(StopRefusal.notRecorder.rawValue, "not_recorder")
}

// §4.28.5：finalizeDeadline＝max(recordedSeconds, 0) × 3 + 600。
func testFinalizeDeadline() throws {
    mrtNear(finalizeDeadline(recordedSeconds: 0), 600, tol: 1e-9, "0")
    mrtNear(finalizeDeadline(recordedSeconds: 100), 900, tol: 1e-9, "100")
    mrtNear(finalizeDeadline(recordedSeconds: 3600), 11400, tol: 1e-9, "3600")
    mrtNear(finalizeDeadline(recordedSeconds: -5), 600, tol: 1e-9, "-5")
}

// §4.42.1、§3.15：record.discard.json 的有效性。
func testDiscardRequestValid() throws {
    let now = mrtNow(1000)
    let f = ISO8601DateFormatter()
    func req(_ runId: String, _ offset: Double) -> DiscardRequest {
        DiscardRequest(schemaVersion: 1, runId: runId, requestedAt: f.string(from: now.addingTimeInterval(offset)))
    }
    let run = "00000000-0000-4000-8000-000000000002"
    mrtEqual(discardRequestValid(nil, runId: run, now: now), false, "nil")
    mrtEqual(discardRequestValid(req("00000000-0000-4000-8000-000000000009", -5), runId: run, now: now), false, "runId 不同")
    mrtEqual(discardRequestValid(req(run, -31), runId: run, now: now), false, "now − 31 秒")
    mrtEqual(discardRequestValid(req(run, -5), runId: run, now: now), true, "now − 5 秒")
    mrtEqual(discardRequestValid(req(run, 5), runId: run, now: now), false, "now + 5 秒（未來）")
    mrtEqual(discardRequestValid(DiscardRequest(schemaVersion: 1, runId: run, requestedAt: "不是時間"), runId: run, now: now),
             false, "requestedAt 解析失敗")
    // 形狀（§3.15）：三個鍵
    let obj = mrtJSONObject(req(run, -5))
    mrtEqual(Set(obj.keys), ["schemaVersion", "runId", "requestedAt"], "record.discard.json 的鍵")
}

// §4.42.5：discarded=true 不自動前處理；discarded nil 時編碼沒有該鍵。
func testDiscardedNoAutoPrep() throws {
    var s = mrtStatus(.done, code: 0)
    s.runId = "a"
    s.session = "/s"
    mrtEqual(shouldAutoPrep(autoPrep: true, status: s, seenInProgressRunIds: ["a"], lastAutoPrepRunId: nil), "/s",
             "前提：discarded nil 時照 R2 規則觸發")
    mrtExpect(mrtJSONObject(s)["discarded"] == nil, "discarded 為 nil 時編碼不得有該鍵")
    s.discarded = true
    mrtEqual(shouldAutoPrep(autoPrep: true, status: s, seenInProgressRunIds: ["a"], lastAutoPrepRunId: nil), nil,
             "discarded true 時不觸發前處理")
    mrtEqual(mrtJSONObject(s)["discarded"] as? Bool, true, "discarded true 時編碼有該鍵")
}

func mrtR3JSONDict(_ data: Data?) -> NSDictionary? {
    guard let d = data, let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return nil }
    return o as NSDictionary
}

// §4.43.1、§3.16：mergedDefaultsJSON 只改 harness 與 root；writeOnboardingDefaults 經同一規則寫檔。
func testMergedDefaults() throws {
    // existing nil → 只有兩鍵
    let a = try mergedDefaultsJSON(existing: nil, harness: "/tmp/範例harness", root: "/tmp/範例根")
    mrtEqual(mrtR3JSONDict(a), ["harness": "/tmp/範例harness", "root": "/tmp/範例根"] as NSDictionary, "existing nil")

    // existing 7 鍵＋syncCompensation＋x → 只改 harness、root
    let existing: [String: Any] = [
        "root": "/tmp/舊根", "type": "standup", "attendees": "[Stand-up] 範例專案", "harness": "/tmp/舊harness",
        "python3": "/usr/bin/python3", "ffmpeg": "/opt/homebrew/bin/ffmpeg", "minFreeBytes": 2_000_000_000,
        "syncCompensation": "reported", "x": ["保留": true],
    ]
    let exData = try JSONSerialization.data(withJSONObject: existing)
    let b = try mergedDefaultsJSON(existing: exData, harness: "/tmp/新harness", root: "/tmp/新根")
    var want = existing
    want["harness"] = "/tmp/新harness"
    want["root"] = "/tmp/新根"
    mrtEqual(mrtR3JSONDict(b), want as NSDictionary, "其他鍵與值原樣")

    // 不是 JSON 物件 → .notObject
    for bad in ["[1, 2]", "不是 JSON", "\"字串\""] {
        do {
            _ = try mergedDefaultsJSON(existing: Data(bad.utf8), harness: "/h", root: "/r")
            mrtFail("「\(bad)」應丟 .notObject", file: #fileID, line: #line)
        } catch let e as DefaultsMergeError {
            mrtEqual(e, DefaultsMergeError.notObject, "「\(bad)」")
        } catch {
            mrtFail("「\(bad)」應丟 DefaultsMergeError.notObject，實際 \(error)", file: #fileID, line: #line)
        }
    }

    // writeOnboardingDefaults：合併寫入、不認得的鍵保留
    let fm = FileManager.default
    let home = mrtR3Home("defaults")
    defer { try? fm.removeItem(at: home) }
    let file = home.appendingPathComponent("record.defaults.json")
    try exData.write(to: file)
    try writeOnboardingDefaults(home: home, harness: "/tmp/新harness", root: "/tmp/新根")
    mrtEqual(mrtR3JSONDict(try? Data(contentsOf: file)), want as NSDictionary, "writeOnboardingDefaults 合併寫入")

    // 壞檔：不寫、報錯（§3.16「不覆寫壞檔」）
    try Data("[1, 2]".utf8).write(to: file)
    do {
        try writeOnboardingDefaults(home: home, harness: "/h", root: "/r")
        mrtFail("壞檔時 writeOnboardingDefaults 應丟錯", file: #fileID, line: #line)
    } catch {}
    mrtEqual(String(decoding: (try? Data(contentsOf: file)) ?? Data(), as: UTF8.self), "[1, 2]", "壞檔不得被覆寫")
}

/// 寫 <home>/menubar.settings.json。
func mrtR3WriteSettings(_ home: URL, _ text: String) throws {
    try Data(text.utf8).write(to: home.appendingPathComponent("menubar.settings.json"))
}

// §4.43.4、§3.16、§4.40.6：缺檔、壞檔、缺鍵、不認得的值 → 預設值；hudMode、hudPosition 存在 menubar.settings.json。
func testMenuBarSettingsDefaults() throws {
    let fm = FileManager.default
    let home = mrtR3Home("settings")
    defer { try? fm.removeItem(at: home) }
    let d = MenuBarSettings()
    // §3.16 的預設值
    mrtEqual(d.showTimer, true, "showTimer")
    mrtEqual(d.hudMode, HUDMode.auto, "hudMode")
    mrtEqual(d.hudPosition, "right", "hudPosition")
    mrtEqual(d.timeSensitiveAlerts, true, "timeSensitiveAlerts")
    mrtEqual(d.lastSettingsTab, "general", "lastSettingsTab")
    mrtEqual(d.onboardingCompletedAt, nil, "onboardingCompletedAt")
    mrtEqual(d.meetingDetect, true, "meetingDetect")
    mrtEqual(HUDMode.allCases.map(\.rawValue), ["auto", "always", "never"], "HUDMode")

    mrtEqual(loadMenuBarSettings(home: home), d, "缺檔")
    try mrtR3WriteSettings(home, "{壞掉")
    mrtEqual(loadMenuBarSettings(home: home), d, "壞檔")
    try mrtR3WriteSettings(home, "[1]")
    mrtEqual(loadMenuBarSettings(home: home), d, "不是物件")
    try mrtR3WriteSettings(home, "{\"schemaVersion\": 1}")
    mrtEqual(loadMenuBarSettings(home: home), d, "缺鍵")

    try mrtR3WriteSettings(home, "{\"schemaVersion\": 1, \"hudMode\": \"x\", \"hudPosition\": \"topRight\", \"showTimer\": false}")
    let s1 = loadMenuBarSettings(home: home)
    mrtEqual(s1.hudMode, HUDMode.auto, "hudMode x → auto")
    mrtEqual(s1.hudPosition, "right", "hudPosition topRight → right")
    mrtEqual(s1.showTimer, false, "其他鍵照讀")

    try mrtR3WriteSettings(home, "{\"schemaVersion\": 1, \"hudMode\": \"never\", \"hudPosition\": \"left\", \"lastSettingsTab\": \"x\"}")
    let s2 = loadMenuBarSettings(home: home)
    mrtEqual(s2.hudMode, HUDMode.never, "hudMode never")
    mrtEqual(s2.hudPosition, "left", "hudPosition left")
    mrtEqual(s2.lastSettingsTab, "general", "lastSettingsTab 不認得 → general")

    // §4.40.6：hudMode、hudPosition 存在 menubar.settings.json
    var s = d
    s.hudMode = .always
    s.hudPosition = "left"
    try saveMenuBarSettings(s, home: home)
    let obj = mrtR3JSONDict(try? Data(contentsOf: home.appendingPathComponent("menubar.settings.json")))
    mrtEqual(obj?["hudMode"] as? String, "always", "menubar.settings.json 的 hudMode")
    mrtEqual(obj?["hudPosition"] as? String, "left", "menubar.settings.json 的 hudPosition")
    // R2 的 menubar.prefs.json 不被寫
    mrtExpect(!fm.fileExists(atPath: home.appendingPathComponent(menuBarPrefsFileName).path),
              "saveMenuBarSettings 不得寫 menubar.prefs.json")
}

// §4.43.4：save 後 load 等於原值。
func testMenuBarSettingsRoundTrip() throws {
    let fm = FileManager.default
    let home = mrtR3Home("settings-rt")
    defer { try? fm.removeItem(at: home) }
    var s = MenuBarSettings()
    s.showTimer = false
    s.hudMode = .never
    s.hudPosition = "left"
    s.timeSensitiveAlerts = false
    s.lastSettingsTab = "advanced"
    s.onboardingCompletedAt = "2026-10-13T10:00:00+08:00"
    s.meetingDetect = false
    try saveMenuBarSettings(s, home: home)
    mrtEqual(loadMenuBarSettings(home: home), s, "save → load")
    try saveMenuBarSettings(MenuBarSettings(), home: home)
    mrtEqual(loadMenuBarSettings(home: home), MenuBarSettings(), "預設值 save → load")
    let names = (try? fm.contentsOfDirectory(atPath: home.path)) ?? []
    mrtExpect(names.contains("menubar.settings.json"), "應寫在 <home>/menubar.settings.json（實際 \(names)）")
}

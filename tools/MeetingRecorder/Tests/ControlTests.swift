// spec §3.9–§3.12、§3.14（R2 Core 名稱，唯一正本）：Control.swift、Records.swift 增補、Detectors.swift 增補、
// Segments.swift 增補、AudioLevel.swift 增補。
// 驗收：§4.16.1–§4.16.3、§4.16.10、§4.17.1、§4.17.3、§4.17.4、§4.17.7、§4.18.1、§4.18.2（行為）、§4.18.8–§4.18.10、
// §4.19.1、§4.20.1。數值一律照抄 spec（§3.11／§3.12 是同一場：startedAt_1＝0.182、暫停 70.012→100.004＝29.992 秒）。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation
import CoreMedia
import AudioToolbox

let mrtControlTests: [MRTCase] = [
    ("testApplyingCommands", testApplyingCommands),
    ("testControlActions", testControlActions),
    ("testRequestAndResetControlFile", testRequestAndResetControlFile),
    ("testControlAvailability", testControlAvailability),
    ("testStatusR2Keys", testStatusR2Keys),
    ("testZeroedAudioSample", testZeroedAudioSample),
    ("testMetaR2EventKeys", testMetaR2EventKeys),
    ("testDetectorResets", testDetectorResets),
    ("testAppendingMuteEvent", testAppendingMuteEvent),
    ("testPausedTotalAndOutputTime", testPausedTotalAndOutputTime),
    ("testPauseGateAndSwitchReason", testPauseGateAndSwitchReason),
    ("testPauseEventsAndStatusFields", testPauseEventsAndStatusFields),
    ("testDetectorFeed", testDetectorFeed),
    ("testMarkerShape", testMarkerShape),
    ("testRecordedSecondsAndClockText", testRecordedSecondsAndClockText),
]

/// 小數 3 位的比較容差（spec §3.14「小數 3 位」；容許實作用不同方式取位）。
let mrtR2Tol = 0.0005

func mrtR2TempDir(_ tag: String) -> URL {
    URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        .appendingPathComponent("mrt-\(tag)-\(UUID().uuidString)", isDirectory: true)
}

func mrtPE(_ t: Double, _ kind: PauseEventKind, outputT: Double = 0, wallClock: String = "") -> PauseEvent {
    PauseEvent(t: t, outputT: outputT, wallClock: wallClock, kind: kind)
}

func mrtUnavailableMessage(_ a: ControlAvailability) -> String? {
    if case .unavailable(let m) = a { return m }
    return nil
}

/// R2 欄位全為 nil 的錄製中狀態（同 TriggerTests 的 mrtStatus：pid 4242）。
func mrtR2Status(_ phase: RecordPhase, controlVersion: Int? = 1) -> RecordStatus {
    var s = mrtStatus(phase)
    s.controlVersion = controlVersion
    return s
}

// §4.16.1：applying 每步只改該命令的欄位；runId、schemaVersion 全程不變。
func testApplyingCommands() throws {
    mrtEqual(controlFileName, "record.control.json")
    mrtEqual(controlLockFileName, "record.control.lock")
    mrtEqual(controlProtocolVersion, 1)
    mrtEqual(ControlCommand.allCases.map { $0.rawValue }, ["pause", "resume", "mute", "unmute", "mark"])

    let c0 = freshControl(runId: "r")
    mrtEqual(c0, RecordControl(schemaVersion: 1, runId: "r", paused: false, micMuted: false, markerSeq: 0))

    var expected = c0
    var cur = c0
    let steps: [(ControlCommand, (inout RecordControl) -> Void)] = [
        (ControlCommand.pause, { $0.paused = true }),
        (ControlCommand.pause, { _ in }),                 // 第二次 pause 不變
        (ControlCommand.mute, { $0.micMuted = true }),
        (ControlCommand.mark, { $0.markerSeq = 1 }),
        (ControlCommand.mark, { $0.markerSeq = 2 }),
        (ControlCommand.resume, { $0.paused = false }),
        (ControlCommand.unmute, { $0.micMuted = false }),
    ]
    for (i, (cmd, change)) in steps.enumerated() {
        cur = applying(cmd, to: cur)
        change(&expected)
        mrtEqual(cur, expected, "第 \(i + 1) 步 \(cmd.rawValue)")
        mrtEqual(cur.runId, "r", "runId 全程不變")
        mrtEqual(cur.schemaVersion, 1, "schemaVersion 全程不變")
    }
    mrtEqual(cur.markerSeq, 2, "兩次 mark 後 markerSeq 為 2")
}

// §4.16.1：controlActions 的七個案例。
func testControlActions() throws {
    func rc(_ runId: String, _ p: Bool, _ m: Bool, _ seq: Int, schema: Int = 1) -> RecordControl {
        RecordControl(schemaVersion: schema, runId: runId, paused: p, micMuted: m, markerSeq: seq)
    }
    let none = ControlActions(pause: nil, micMute: nil, newMarkers: 0)
    mrtEqual(controlActions(applied: rc("r", false, false, 0), requested: rc("r", true, false, 2)),
             ControlActions(pause: true, micMute: nil, newMarkers: 2))
    mrtEqual(controlActions(applied: rc("r", false, false, 0), requested: rc("r", false, false, 0)), none, "相同 → 無動作")
    mrtEqual(controlActions(applied: rc("r", false, false, 0), requested: rc("x", true, true, 5)), none, "runId 不同 → 無動作")
    mrtEqual(controlActions(applied: rc("r", false, false, 0), requested: nil), none, "requested nil → 無動作")
    mrtEqual(controlActions(applied: rc("r", false, false, 0), requested: rc("r", true, true, 5, schema: 2)), none,
             "schemaVersion 2 → 無動作")
    mrtEqual(controlActions(applied: rc("r", false, false, 5), requested: rc("r", false, false, 3)).newMarkers, 0,
             "requested markerSeq 小於 applied → newMarkers 0")
    mrtEqual(controlActions(applied: rc("r", true, true, 3), requested: rc("r", false, false, 3)),
             ControlActions(pause: false, micMute: false, newMarkers: 0))
}

// §4.16.2、§3.9：requestControl／resetControl／readControl 與控制檔、鎖檔。
func testRequestAndResetControlFile() throws {
    let fm = FileManager.default
    let root = mrtR2TempDir("control")
    defer { try? fm.removeItem(at: root) }
    let home = root.appendingPathComponent("home/sub", isDirectory: true)
    let file = home.appendingPathComponent("record.control.json")
    let lock = home.appendingPathComponent("record.control.lock")
    mrtExpect(!fm.fileExists(atPath: home.path), "前提：暫存 home 尚不存在")

    // 不存在的 home：建立目錄、控制檔（鍵恰為 5 個、paused true、runId "r"）並留下鎖檔
    let r1 = try requestControl(ControlCommand.pause, home: home, runId: "r")
    mrtEqual(r1, RecordControl(schemaVersion: 1, runId: "r", paused: true, micMuted: false, markerSeq: 0))
    mrtExpect(fm.fileExists(atPath: file.path), "應建立 record.control.json")
    mrtExpect(fm.fileExists(atPath: lock.path), "應留下 record.control.lock")
    let obj = (try JSONSerialization.jsonObject(with: Data(contentsOf: file)) as? [String: Any]) ?? [:]
    mrtEqual(Set(obj.keys), ["schemaVersion", "runId", "paused", "micMuted", "markerSeq"], "JSON 鍵恰為 5 個")
    mrtEqual(obj["paused"] as? Bool, true)
    mrtEqual(obj["runId"] as? String, "r")
    mrtEqual(readControl(file), r1, "readControl 讀回寫入的內容")

    // 控制檔 runId 為 "old" 且 paused true：從 freshControl(runId: "r") 起算
    let old = #"{"schemaVersion":1,"runId":"old","paused":true,"micMuted":true,"markerSeq":7}"#
    try Data(old.utf8).write(to: file)
    let r2 = try requestControl(ControlCommand.mark, home: home, runId: "r")
    mrtEqual(r2, RecordControl(schemaVersion: 1, runId: "r", paused: false, micMuted: false, markerSeq: 1))
    // 連續第二次 mark
    let r3 = try requestControl(ControlCommand.mark, home: home, runId: "r")
    mrtEqual(r3.markerSeq, 2, "連續兩次 mark 後 markerSeq 為 2")
    mrtEqual(readControl(file), r3)

    // resetControl 覆寫成 freshControl(runId: "r2")
    let reset = try resetControl(home: home, runId: "r2")
    mrtEqual(reset, freshControl(runId: "r2"))
    mrtEqual(readControl(file), freshControl(runId: "r2"))

    // readControl：不存在、內容為 "{" → nil
    mrtExpect(readControl(home.appendingPathComponent("no-such.json")) == nil, "不存在的檔應回 nil")
    let broken = root.appendingPathComponent("broken.json")
    try Data("{".utf8).write(to: broken)
    mrtExpect(readControl(broken) == nil, "內容為 { 的檔應回 nil")

    // 寫完後目錄裡不得留 tmp 檔
    let names = Set(try fm.contentsOfDirectory(atPath: home.path))
    mrtEqual(names, ["record.control.json", "record.control.lock"], "目錄只剩控制檔與鎖檔")

    // resetControl 也會建立不存在的上層目錄
    let home2 = root.appendingPathComponent("other/home", isDirectory: true)
    _ = try resetControl(home: home2, runId: "r9")
    mrtEqual(readControl(home2.appendingPathComponent("record.control.json")), freshControl(runId: "r9"))
    mrtExpect(fm.fileExists(atPath: home2.appendingPathComponent("record.control.lock").path), "resetControl 也留下鎖檔")
}

// §4.16.3：controlAvailability 依 §3.14 的順序判斷。
func testControlAvailability() throws {
    let rec = mrtR2Status(.recording)
    func msg(_ s: RecordStatus?, _ pid: Int32?, _ alive: Bool) -> String {
        mrtUnavailableMessage(controlAvailability(status: s, recordPid: pid, pidAlive: alive)) ?? "<不是 unavailable>"
    }
    mrtContains(msg(nil, 4242, true), "沒有錄製在跑", "status nil")
    mrtContains(msg(rec, nil, true), "沒有錄製在跑", "recordPid nil")
    mrtContains(msg(rec, 4242, false), "沒有錄製在跑", "pidAlive false")
    mrtContains(msg(rec, 4243, true), "狀態檔不是這個錄製實例的", "status.pid 4242、recordPid 4243")
    mrtContains(msg(mrtR2Status(.preflight), 4242, true), "還在開錄前檢查")
    mrtContains(msg(mrtR2Status(.stopping), 4242, true), "正在收尾")
    mrtContains(msg(mrtR2Status(.finalizing), 4242, true), "正在收尾")
    for p in [RecordPhase.done, RecordPhase.failed, RecordPhase.preflightFailed] {
        mrtContains(msg(mrtR2Status(p), 4242, true), "沒有錄製在跑", p.rawValue)
    }
    mrtContains(msg(mrtR2Status(.recording, controlVersion: nil), 4242, true), "舊版錄製器", "controlVersion nil")
    mrtContains(msg(mrtR2Status(.recording, controlVersion: 0), 4242, true), "舊版錄製器", "controlVersion 0")
    // 順序：pid 不符先於 phase、phase 先於 controlVersion
    mrtContains(msg(mrtR2Status(.preflight, controlVersion: nil), 4243, true), "狀態檔不是這個錄製實例的", "pid 不符優先")
    mrtContains(msg(mrtR2Status(.stopping, controlVersion: nil), 4242, true), "正在收尾", "phase 先於 controlVersion")
    mrtEqual(controlAvailability(status: rec, recordPid: 4242, pidAlive: true),
             ControlAvailability.ready(pid: 4242, runId: rec.runId))
}

// §4.16.10、§3.10、§3.9：RecordStatus 的 R2 欄位 nil 時省略鍵、有值時 20 鍵；GapStats.pausedTotal；RecordControl 鍵。
func testStatusR2Keys() throws {
    let r1Keys: Set<String> = ["schemaVersion", "runId", "pid", "phase", "code", "message", "session", "startedAt",
                               "updatedAt", "segments", "preflight", "warnings"]
    let plain = mrtStatus(.recording)
    let (plainObj, _, _) = try mrtWriteAndRead(plain, name: "record.status.json")
    mrtEqual(Set(plainObj.keys), r1Keys, "R2 欄位全為 nil 時鍵恰為第一輪的 12 個")

    var full = mrtStatus(.recording)
    full.controlVersion = 1
    full.recordingStartedAt = "2026-10-12T21:00:00+08:00"
    full.paused = true
    full.micMuted = false
    full.pausedSeconds = 29.992
    full.pausedAt = "2026-10-12T21:02:30+08:00"
    full.markers = 2
    full.recentLevels = RecentLevels(windowSeconds: 3, system: -30.5, mic: nil)
    let (obj, text, files) = try mrtWriteAndRead(full, name: "record.status.json")
    mrtEqual(files, ["record.status.json"])
    mrtEqual(Set(obj.keys), r1Keys.union(["controlVersion", "recordingStartedAt", "paused", "micMuted", "pausedSeconds",
                                          "pausedAt", "markers", "recentLevels"]), "8 個欄位都有值時恰為 20 鍵")
    mrtEqual(obj.count, 20)
    mrtEqual(mrtKeys(obj["recentLevels"]), ["windowSeconds", "system", "mic"])
    mrtExpect(mrtIsNull((obj["recentLevels"] as? [String: Any])?["mic"]), "recentLevels.mic 為 nil 時寫 null")
    mrtEqual(obj["controlVersion"] as? Int, 1)
    mrtEqual(try JSONDecoder().decode(RecordStatus.self, from: Data(text.utf8)), full, "往返 JSON 後相等")

    // 第一輪格式（12 鍵）的 JSON 解得回來、R2 欄位為 nil
    let r1JSON = #"""
    {"schemaVersion":1,"runId":"00000000-0000-4000-8000-000000000001","pid":4242,"phase":"recording","code":0,
     "message":"","session":"/tmp/範例根/20261012/[Stand-up] 範例專案","startedAt":"2026-10-12T21:00:00+08:00",
     "updatedAt":"2026-10-12T21:00:05+08:00","segments":1,"preflight":[],"warnings":[]}
    """#
    let back = try JSONDecoder().decode(RecordStatus.self, from: Data(r1JSON.utf8))
    mrtExpect(back.controlVersion == nil && back.recordingStartedAt == nil && back.paused == nil && back.micMuted == nil
              && back.pausedSeconds == nil && back.pausedAt == nil && back.markers == nil && back.recentLevels == nil,
              "第一輪格式解回來後 R2 欄位應全為 nil")

    // GapStats.pausedTotal：nil → 4 鍵；有值 → 5 鍵
    var g = GapStats(boundaries: [0.01], max: 0.01, total: 0.01, wallClock: 100.0)
    mrtEqual(Set(mrtJSONObject(g).keys), ["boundaries", "max", "total", "wallClock"], "pausedTotal nil 時鍵恰為 4 個")
    g.pausedTotal = 29.992
    let gObj = mrtJSONObject(g)
    mrtEqual(Set(gObj.keys), ["boundaries", "max", "total", "wallClock", "pausedTotal"], "有值時 5 個")
    mrtEqual(try JSONDecoder().decode(GapStats.self, from: JSONEncoder().encode(g)), g)

    // RecordControl 往返、鍵恰為 5 個
    let c = RecordControl(schemaVersion: 1, runId: "00000000-0000-4000-8000-000000000001", paused: true, micMuted: false, markerSeq: 3)
    mrtEqual(Set(mrtJSONObject(c).keys), ["schemaVersion", "runId", "paused", "micMuted", "markerSeq"])
    mrtEqual(try JSONDecoder().decode(RecordControl.self, from: JSONEncoder().encode(c)), c)
}

/// 讀出 CMSampleBuffer 的資料位元組（拿不到回空陣列）。
func mrtR2Bytes(_ sb: CMSampleBuffer) -> [UInt8] {
    guard let bb = CMSampleBufferGetDataBuffer(sb) else { return [] }
    let n = CMBlockBufferGetDataLength(bb)
    var out = [UInt8](repeating: 0, count: n)
    let st = out.withUnsafeMutableBytes { CMBlockBufferCopyDataBytes(bb, atOffset: 0, dataLength: n, destination: $0.baseAddress!) }
    return st == kCMBlockBufferNoErr ? out : []
}

// §4.17.1：zeroedAudioSample 深拷貝並清 0；frame 數、PTS、duration、format description 相同；原緩衝不變。
func testZeroedAudioSample() throws {
    let cases: [(String, Int32, CMSampleBuffer?)] = [
        ("Float32 非交錯 雙聲道 48 kHz 480 frame", 48000,
         mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32, frames: 480) { f, _ in
             0.5 * sin(2 * Double.pi * 1000 * Double(f) / 48000) }),
        ("Int16 交錯 單聲道 16 kHz 160 frame", 16000,
         mrtMakeAudioBuffer(sampleRate: 16000, channels: 1, interleaved: true, kind: .int16, frames: 160) { f, _ in
             0.5 * sin(2 * Double.pi * 440 * Double(f) / 16000) }),
    ]
    for (name, rate, made) in cases {
        guard let base = made else { mrtFail("\(name)：前提：自建緩衝失敗", file: #fileID, line: #line); continue }
        // 換一個非 0 的 PTS，讓「PTS 相同」的檢查有意義
        var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: rate),
                                        presentationTimeStamp: CMTime(value: 12345, timescale: 1000),
                                        decodeTimeStamp: .invalid)
        var copied: CMSampleBuffer?
        let st = CMSampleBufferCreateCopyWithNewTiming(allocator: kCFAllocatorDefault, sampleBuffer: base,
                                                       sampleTimingEntryCount: 1, sampleTimingArray: &timing,
                                                       sampleBufferOut: &copied)
        guard st == noErr, let orig = copied else { mrtFail("\(name)：前提：改 PTS 失敗", file: #fileID, line: #line); continue }
        let origBytesBefore = mrtR2Bytes(orig)
        mrtExpect(origBytesBefore.contains { $0 != 0 }, "\(name)：前提：原緩衝有非 0 值")

        guard let z = zeroedAudioSample(orig) else { mrtFail("\(name)：應回非 nil", file: #fileID, line: #line); continue }
        let zb = mrtR2Bytes(z)
        mrtEqual(zb.count, origBytesBefore.count, "\(name)：資料長度相同")
        mrtExpect(!zb.isEmpty && zb.allSatisfy { $0 == 0 }, "\(name)：資料位元組應全為 0")
        mrtEqual(CMSampleBufferGetNumSamples(z), CMSampleBufferGetNumSamples(orig), "\(name)：frame 數相同")
        mrtEqual(CMSampleBufferGetPresentationTimeStamp(z), CMSampleBufferGetPresentationTimeStamp(orig), "\(name)：PTS 相同")
        mrtEqual(CMSampleBufferGetDuration(z), CMSampleBufferGetDuration(orig), "\(name)：duration 相同")
        if let fz = CMSampleBufferGetFormatDescription(z), let fo = CMSampleBufferGetFormatDescription(orig) {
            mrtExpect(CMFormatDescriptionEqual(fz, otherFormatDescription: fo), "\(name)：format description 相等")
        } else {
            mrtFail("\(name)：缺 format description", file: #fileID, line: #line)
        }
        mrtEqual(mrtR2Bytes(orig), origBytesBefore, "\(name)：原緩衝的資料不變")
        mrtNear(rmsDBFS(sampleBuffer: z), -Double.infinity, "\(name)：清 0 後 rmsDBFS 為 -∞")
    }
}

// §4.17.3、§3.11：RecordMeta 的 pauseEvents／micMuteEvents。
func testMetaR2EventKeys() throws {
    let r1Keys: Set<String> = ["schemaVersion", "window", "config", "devices", "preflight", "deviceEvents", "audioFormatEvents"]
    let base = mrtSampleMeta()
    mrtEqual(Set(mrtJSONObject(base).keys), r1Keys, "兩者都為 nil 時鍵恰為第一輪的 7 個")

    var empty = base
    empty.pauseEvents = []
    empty.micMuteEvents = []
    mrtEqual(Set(mrtJSONObject(empty).keys), r1Keys.union(["pauseEvents", "micMuteEvents"]), "兩者為空陣列時恰為 9 個")

    var withEvents = base
    withEvents.pauseEvents = [PauseEvent(t: 70.012, outputT: 69.830, wallClock: "2026-10-12T21:01:10+08:00", kind: PauseEventKind.pause),
                              PauseEvent(t: 100.004, outputT: 69.830, wallClock: "2026-10-12T21:01:40+08:00", kind: PauseEventKind.resume)]
    withEvents.micMuteEvents = [MicMuteEvent(t: 60.020, outputT: 59.838, wallClock: "2026-10-12T21:01:00+08:00", muted: true)]
    let (obj, text, _) = try mrtWriteAndRead(withEvents, name: "record.meta.json")
    let pes = (obj["pauseEvents"] as? [[String: Any]]) ?? []
    mrtEqual(pes.count, 2)
    mrtEqual(Set(pes.first?.keys.map { $0 } ?? []), ["t", "outputT", "wallClock", "kind"])
    mrtEqual(pes.map { $0["kind"] as? String ?? "" }, ["pause", "resume"])
    let mes = (obj["micMuteEvents"] as? [[String: Any]]) ?? []
    mrtEqual(Set(mes.first?.keys.map { $0 } ?? []), ["t", "outputT", "wallClock", "muted"])
    mrtEqual(mes.first?["muted"] as? Bool, true)
    mrtEqual(PauseEventKind.pause.rawValue, "pause")
    mrtEqual(PauseEventKind.resume.rawValue, "resume")
    mrtEqual(try JSONDecoder().decode(RecordMeta.self, from: Data(text.utf8)), withEvents, "含事件的 meta 往返後相等")

    // 第一輪格式（沒有這兩鍵）的 meta JSON 解得回來、兩欄為 nil
    var r1Obj = mrtJSONObject(withEvents)
    r1Obj.removeValue(forKey: "pauseEvents")
    r1Obj.removeValue(forKey: "micMuteEvents")
    let r1Data = try JSONSerialization.data(withJSONObject: r1Obj)
    let back = try JSONDecoder().decode(RecordMeta.self, from: r1Data)
    mrtExpect(back.pauseEvents == nil && back.micMuteEvents == nil, "第一輪格式解回來兩欄應為 nil")
    mrtEqual(back.deviceEvents, base.deviceEvents)
}

// §4.17.4：SilenceDetector／SuspendedDetector.reset() 之後與新實例相同；BlackDetector.interrupt(at:)。
func testDetectorResets() throws {
    func ts(_ from: Double, _ to: Double) -> [Double] { stride(from: from, to: to - 1e-9, by: 0.5).map { $0 } }

    // Silence：-80 dBFS 每 0.5 秒餵 10 秒 → reset → 再餵 20 秒（正式值 -60／15 秒）
    var s = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    for t in ts(0, 10) { _ = s.feed(t: t, dbfs: -80) }
    s.reset()
    var sFresh = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    let sAfter = ts(10, 30).map { s.feed(t: $0, dbfs: -80) }
    let sNew = ts(10, 30).map { sFresh.feed(t: $0, dbfs: -80) }
    mrtEqual(sAfter, sNew, "SilenceDetector reset 之後應與新實例逐一相同")
    mrtEqual(sNew.filter { $0 }.count, 1, "前提：新實例在 20 秒內告警一次")

    // reset 也要清掉「已告警」：先觸發，再 reset，與新實例相同
    var s2 = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    for t in ts(0, 20) { _ = s2.feed(t: t, dbfs: -80) }
    s2.reset()
    var s2Fresh = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    mrtEqual(ts(20, 40).map { s2.feed(t: $0, dbfs: -80) }, ts(20, 40).map { s2Fresh.feed(t: $0, dbfs: -80) },
             "已告警後 reset 也應與新實例相同")

    // Suspended（正式值 5 秒）
    var u = SuspendedDetector(seconds: 5)
    for t in ts(0, 10) { _ = u.feed(t: t, status: .suspended) }
    u.reset()
    var uFresh = SuspendedDetector(seconds: 5)
    let uAfter = ts(10, 30).map { u.feed(t: $0, status: .suspended) }
    let uNew = ts(10, 30).map { uFresh.feed(t: $0, status: .suspended) }
    mrtEqual(uAfter, uNew, "SuspendedDetector reset 之後應與新實例逐一相同")
    mrtEqual(uNew.filter { $0 }.count, 1, "前提：新實例在 20 秒內觸發一次")

    // Black（正式值 0.01／5 秒）：已開啟的區間 interrupt 後 end ＝ t
    var b = BlackDetector(ratio: 0.01, seconds: 5)
    for t in ts(0, 6) { _ = b.feed(t: t, nonBlackRatio: 0) }
    mrtEqual(b.intervals, [BlackInterval(start: 0, end: nil)], "前提：已開一個區間")
    b.interrupt(at: 6.2)
    mrtEqual(b.intervals, [BlackInterval(start: 0, end: 6.2)], "interrupt 後 end 應等於 t")
    // 之後再餵 3 秒低於門檻：不得新開區間
    let after3 = ts(6.5, 9.5).map { b.feed(t: $0, nonBlackRatio: 0) }
    mrtEqual(after3.filter { $0 }.count, 0, "interrupt 之後 3 秒不得新開區間")
    mrtEqual(b.intervals.count, 1)
    // 之後的開區間判斷與新實例相同（從 6.5 起連續 5 秒才開）
    var bFresh = BlackDetector(ratio: 0.01, seconds: 5)
    _ = ts(6.5, 9.5).map { bFresh.feed(t: $0, nonBlackRatio: 0) }
    mrtEqual(ts(9.5, 14).map { b.feed(t: $0, nonBlackRatio: 0) }, ts(9.5, 14).map { bFresh.feed(t: $0, nonBlackRatio: 0) },
             "interrupt 之後的開區間判斷應與新實例相同")
    mrtEqual(b.intervals.count, 2, "連續 5 秒後才新開第二個區間")
    mrtEqual(b.intervals.last?.start, 6.5)

    // 沒有開啟中的區間：intervals 不變
    var b2 = BlackDetector(ratio: 0.01, seconds: 5)
    for t in ts(0, 2) { _ = b2.feed(t: t, nonBlackRatio: 0) }
    b2.interrupt(at: 2.0)
    mrtEqual(b2.intervals, [], "沒有開啟區間時 intervals 不變")
    var b3 = BlackDetector(ratio: 0.01, seconds: 5)
    for t in ts(0, 6) { _ = b3.feed(t: t, nonBlackRatio: 0) }
    _ = b3.feed(t: 6, nonBlackRatio: 1)
    let closed = b3.intervals
    b3.interrupt(at: 7.0)
    mrtEqual(b3.intervals, closed, "已關閉的區間保留、不被改")
}

// §4.17.7：appendingMuteEvent。
func testAppendingMuteEvent() throws {
    let w = "2026-10-12T21:01:00+08:00"
    let one = appendingMuteEvent([], muted: true, t: 60.0204, firstSegmentStart: 0.182, pauses: [], wallClock: w)
    mrtEqual(one.count, 1)
    if let e = one.first {
        mrtNear(e.t, 60.020, tol: mrtR2Tol, "t 取小數 3 位")
        mrtNear(e.outputT, 59.838, tol: mrtR2Tol)
        mrtEqual(e.wallClock, w)
        mrtEqual(e.muted, true)
    }
    mrtEqual(appendingMuteEvent(one, muted: true, t: 61, firstSegmentStart: 0.182, pauses: [], wallClock: "w2"), one,
             "muted 等於目前狀態 → 原樣（1 筆）")
    mrtEqual(appendingMuteEvent([], muted: false, t: 10, firstSegmentStart: 0.182, pauses: [], wallClock: w), [],
             "沒有事件視為 false：unmute → []")
    let inPause = appendingMuteEvent([], muted: true, t: 80.0, firstSegmentStart: 0.182,
                                     pauses: [mrtPE(70.012, PauseEventKind.pause)], wallClock: w)
    mrtNear(inPause.first?.outputT, 69.830, tol: mrtR2Tol, "暫停中靜音的 outputT 為暫停點的成品時間")
    let two = appendingMuteEvent(one, muted: false, t: 90.0, firstSegmentStart: 0.182, pauses: [], wallClock: "w3")
    mrtEqual(two.count, 2)
    mrtEqual(two.last?.muted, false)
    mrtEqual(two.first, one.first, "既有事件不變")
}

// §4.18.1：pausedTotal、outputTime。
func testPausedTotalAndOutputTime() throws {
    let p70 = mrtPE(70, PauseEventKind.pause), r100 = mrtPE(100, PauseEventKind.resume), p150 = mrtPE(150, PauseEventKind.pause)
    mrtNear(pausedTotal([p70, r100, p150]), 30.0, tol: mrtR2Tol, "沒配對的 pause 不計")
    mrtNear(pausedTotal([]), 0, tol: mrtR2Tol)
    mrtNear(pausedTotal([mrtPE(5, PauseEventKind.resume)]), 0, tol: mrtR2Tol, "沒有前導 pause 的 resume 不計")

    let ps = [p70, r100]
    mrtNear(outputTime(recordT: 50, firstSegmentStart: 0.2, pauses: ps), 49.8, tol: mrtR2Tol)
    mrtNear(outputTime(recordT: 80, firstSegmentStart: 0.2, pauses: ps), 69.8, tol: mrtR2Tol, "落在暫停區間以 pause.t 代替")
    mrtNear(outputTime(recordT: 130, firstSegmentStart: 0.2, pauses: ps), 99.8, tol: mrtR2Tol)
    mrtNear(outputTime(recordT: 0.1, firstSegmentStart: 0.2, pauses: ps), 0, tol: mrtR2Tol, "< 0 夾成 0")
    mrtNear(outputTime(recordT: 160, firstSegmentStart: 0.2, pauses: ps + [p150]), 119.8, tol: mrtR2Tol, "沒配對的 pause 之後")
}

// §4.18.8（§4.18.2 的行為）：SwitchReason、PauseGate 與 pausing／resuming／pauseRoute／segmentOpened／openReason。
func testPauseGateAndSwitchReason() throws {
    let reasons: [SwitchReason] = SwitchReason.allCases
    let expectedReasons: [SwitchReason] = [.first, .periodic, .formatChange, .writerFailure, .resume, .outputDeviceChange]
    mrtEqual(reasons, expectedReasons, "SwitchReason 恰為六個")
    let g0 = PauseGate()
    mrtEqual(g0, PauseGate(paused: false, cutPoint: nil, resumePending: false), "預設值")
    mrtEqual(pauseRoute(g0, sampleStart: 5), PauseSampleRoute.normal)
    mrtEqual(openReason(route: PauseSampleRoute.normal, hasCurrent: false, everOpened: false, switchOnNextSample: false),
             SwitchReason.first)
    mrtEqual(openReason(route: PauseSampleRoute.normal, hasCurrent: false, everOpened: true, switchOnNextSample: false),
             SwitchReason.writerFailure)
    mrtEqual(openReason(route: PauseSampleRoute.normal, hasCurrent: true, everOpened: true, switchOnNextSample: true),
             SwitchReason.writerFailure)
    mrtEqual(openReason(route: PauseSampleRoute.normal, hasCurrent: true, everOpened: true, switchOnNextSample: false), nil)

    // 暫停
    let g1 = pausing(g0, maxEnd: 70.0, segmentStart: 60.0)
    mrtEqual(g1, PauseGate(paused: true, cutPoint: 70.0, resumePending: false))
    mrtEqual(pausing(g1, maxEnd: 75, segmentStart: 60), g1, "已暫停 → 原樣")
    mrtEqual(pausing(g0, maxEnd: nil, segmentStart: 60.0).cutPoint, 60.0, "maxEnd nil 時取 segmentStart")
    mrtEqual(pausing(g0, maxEnd: nil, segmentStart: nil).cutPoint, nil, "兩者皆 nil 時 cutPoint 為 nil")
    mrtEqual(pauseRoute(g1, sampleStart: 69.9), PauseSampleRoute.prevOnly)
    mrtEqual(pauseRoute(g1, sampleStart: 70.0), PauseSampleRoute.drop)
    mrtEqual(pauseRoute(g1, sampleStart: 90.0), PauseSampleRoute.drop)
    for r in [PauseSampleRoute.prevOnly, PauseSampleRoute.drop] {
        mrtEqual(openReason(route: r, hasCurrent: false, everOpened: true, switchOnNextSample: false), nil,
                 "暫停中不因 cur == nil 自動開段（\(r)）")
        mrtEqual(openReason(route: r, hasCurrent: false, everOpened: true, switchOnNextSample: true), nil)
    }

    // 繼續
    let g2 = resuming(g1)
    mrtEqual(g2, PauseGate(paused: false, cutPoint: 70.0, resumePending: true))
    mrtEqual(resuming(g0), g0, "沒在暫停 → 原樣")
    mrtEqual(pauseRoute(g2, sampleStart: 69.95), PauseSampleRoute.prevOnly)
    mrtEqual(pauseRoute(g2, sampleStart: 100.0), PauseSampleRoute.resumeBoundary)
    mrtEqual(openReason(route: PauseSampleRoute.resumeBoundary, hasCurrent: false, everOpened: true, switchOnNextSample: false),
             SwitchReason.resume)
    mrtEqual(openReason(route: PauseSampleRoute.resumeBoundary, hasCurrent: false, everOpened: false, switchOnNextSample: false),
             SwitchReason.first)
    mrtEqual(segmentOpened(g2), PauseGate(), "開新段後回到初始")
    mrtEqual(pauseRoute(segmentOpened(g2), sampleStart: 100.5), PauseSampleRoute.normal)

    // cutPoint 為 nil 的暫停：任何 sampleStart 都是 drop；繼續後任何 sampleStart 都是 resumeBoundary
    let gn = pausing(g0, maxEnd: nil, segmentStart: nil)
    for t in [0.0, 5.0, 1000.0] {
        mrtEqual(pauseRoute(gn, sampleStart: t), PauseSampleRoute.drop, "cutPoint nil、暫停中 t=\(t)")
        mrtEqual(pauseRoute(resuming(gn), sampleStart: t), PauseSampleRoute.resumeBoundary, "cutPoint nil、繼續後 t=\(t)")
    }
    // segmentOpened 不改 paused
    mrtEqual(segmentOpened(g1).paused, true, "segmentOpened 的 paused 不變")
}

// §4.18.9：appendingPauseEvent、pauseStatusFields、applyingPauseFields。
func testPauseEventsAndStatusFields() throws {
    let fs = 0.182
    let w1 = "2026-10-12T21:01:10+08:00", w2 = "2026-10-12T21:01:40+08:00", w3 = "2026-10-12T21:02:30+08:00"
    let one = appendingPauseEvent([], kind: PauseEventKind.pause, t: 70.0124, firstSegmentStart: fs, wallClock: w1)
    mrtEqual(one.count, 1)
    if let e = one.first {
        mrtNear(e.t, 70.012, tol: mrtR2Tol, "t 取小數 3 位")
        mrtNear(e.outputT, 69.830, tol: mrtR2Tol)
        mrtEqual(e.wallClock, w1)
        mrtEqual(e.kind, PauseEventKind.pause)
    }
    mrtEqual(appendingPauseEvent(one, kind: PauseEventKind.pause, t: 80, firstSegmentStart: fs, wallClock: "x"), one,
             "再 append pause → 原樣（冪等）")
    mrtEqual(appendingPauseEvent([], kind: PauseEventKind.resume, t: 10, firstSegmentStart: fs, wallClock: "x"), [],
             "沒有事件視為 resume：resume → []")
    let two = appendingPauseEvent(one, kind: PauseEventKind.resume, t: 100.004, firstSegmentStart: fs, wallClock: w2)
    mrtEqual(two.count, 2)
    mrtEqual(two.last?.kind, PauseEventKind.resume)
    mrtNear(two.last?.t, 100.004, tol: mrtR2Tol)
    mrtNear(two.last?.outputT, 69.830, tol: mrtR2Tol, "resume 的 outputT 等於暫停點的成品時間")

    func check(_ f: PauseStatusFields, _ paused: Bool, _ at: String?, _ secs: Double, _ label: String) {
        mrtEqual(f.paused, paused, "\(label) paused")
        mrtEqual(f.pausedAt, at, "\(label) pausedAt")
        mrtNear(f.pausedSeconds, secs, tol: mrtR2Tol, "\(label) pausedSeconds")
    }
    check(pauseStatusFields([]), false, nil, 0, "[]")
    check(pauseStatusFields([mrtPE(70.012, PauseEventKind.pause, wallClock: w1)]), true, w1, 0, "[pause]")
    let paired = [mrtPE(70.012, PauseEventKind.pause, wallClock: w1), mrtPE(100.004, PauseEventKind.resume, wallClock: w2)]
    check(pauseStatusFields(paired), false, nil, 29.992, "[pause, resume]")
    check(pauseStatusFields(paired + [mrtPE(150.0, PauseEventKind.pause, wallClock: w3)]), true, w3, 29.992, "[pause, resume, pause]")

    var s = mrtStatus(.recording)
    s.pausedAt = "x"
    s.paused = true
    s.markers = 3
    let applied = applyingPauseFields(PauseStatusFields(paused: false, pausedAt: nil, pausedSeconds: 29.992), to: s)
    mrtEqual(applied.paused, false)
    mrtNear(applied.pausedSeconds, 29.992, tol: mrtR2Tol)
    mrtEqual(applied.markers, 3, "其餘欄位不變")
    mrtEqual(applied.pausedAt, nil)
    mrtEqual(applied.runId, s.runId)
    mrtEqual(applied.warnings, s.warnings)
    let obj = mrtJSONObject(applied)
    mrtExpect(obj["pausedAt"] == nil, "pausedAt nil 時 JSON 不得有此鍵")
    mrtEqual(obj["paused"] as? Bool, false)
}

// §4.18.10：detectorFeed。
func testDetectorFeed() throws {
    let allOn = DetectorFeed(systemSilence: true, micSilence: true, black: true, suspended: true)
    let allOff = DetectorFeed(systemSilence: false, micSilence: false, black: false, suspended: false)
    mrtEqual(detectorFeed(paused: false, micMuted: false), allOn)
    mrtEqual(detectorFeed(paused: false, micMuted: true), DetectorFeed(systemSilence: true, micSilence: false, black: true, suspended: true))
    mrtEqual(detectorFeed(paused: true, micMuted: false), allOff)
    mrtEqual(detectorFeed(paused: true, micMuted: true), allOff)
}

// §4.19.1、§3.12：markerLabel、Marker 的 JSON 形狀；範例數值自洽（125.700 − 0.182 − 29.992＝95.526）。
func testMarkerShape() throws {
    mrtEqual(markerLabel(3), "標記 3")
    mrtEqual(markerLabel(1), "標記 1")
    let pauses = [mrtPE(70.012, PauseEventKind.pause), mrtPE(100.004, PauseEventKind.resume)]
    let t = outputTime(recordT: 125.700, firstSegmentStart: 0.182, pauses: pauses)
    mrtNear(t, 95.526, tol: mrtR2Tol, "§3.12 範例自洽")
    let m = Marker(t: 95.526, recordT: 125.700, wallClock: "2026-10-12T21:02:05+08:00", label: markerLabel(1))
    let obj = mrtJSONObject(m)
    mrtEqual(Set(obj.keys), ["t", "recordT", "wallClock", "label"])
    mrtEqual(obj["label"] as? String, "標記 1")
    let back: Marker = try JSONDecoder().decode(Marker.self, from: JSONEncoder().encode(m))
    mrtEqual(back, m, "往返後相等")
    // markers.json 頂層是陣列
    let list: [Marker] = [m]
    let arr = (try JSONSerialization.jsonObject(with: JSONEncoder().encode(list)) as? [[String: Any]]) ?? []
    mrtEqual(arr.count, 1, "頂層是陣列")
    mrtEqual(Set(arr.first?.keys.map { $0 } ?? []), ["t", "recordT", "wallClock", "label"])
}

func mrtR2ISO(_ d: Date) -> String {
    let f = ISO8601DateFormatter()
    f.timeZone = TimeZone(secondsFromGMT: 8 * 3600)
    return f.string(from: d)
}

// §4.20.1：clockText、recordedSeconds。
func testRecordedSecondsAndClockText() throws {
    mrtEqual(clockText(seconds: 0), "00:00")
    mrtEqual(clockText(seconds: 59), "00:59")
    mrtEqual(clockText(seconds: 3599), "59:59")
    mrtEqual(clockText(seconds: 3600), "1:00:00")
    mrtEqual(clockText(seconds: 3665), "1:01:05")
    mrtEqual(clockText(seconds: -5), "00:00")

    let now = mrtDate("2026-10-12T21:10:00+08:00")
    mrtEqual(recordedSeconds(recordingStartedAt: mrtR2ISO(now.addingTimeInterval(-125)), pausedSeconds: 5, pausedAt: nil, now: now), 120)
    mrtEqual(recordedSeconds(recordingStartedAt: mrtR2ISO(now.addingTimeInterval(-100)), pausedSeconds: 20,
                             pausedAt: mrtR2ISO(now.addingTimeInterval(-10)), now: now), 70, "暫停中再扣 now − pausedAt")
    mrtEqual(recordedSeconds(recordingStartedAt: mrtR2ISO(now.addingTimeInterval(5)), pausedSeconds: 0, pausedAt: nil, now: now), 0,
             "< 0 夾成 0")
    mrtEqual(recordedSeconds(recordingStartedAt: "x", pausedSeconds: 0, pausedAt: nil, now: now), nil, "解不開 → nil")
    mrtEqual(recordedSeconds(recordingStartedAt: mrtR2ISO(now.addingTimeInterval(-100)), pausedSeconds: 0, pausedAt: "x", now: now), nil,
             "pausedAt 解不開 → nil")
    // 向下取整
    mrtEqual(recordedSeconds(recordingStartedAt: mrtR2ISO(now.addingTimeInterval(-100)), pausedSeconds: 0.6, pausedAt: nil, now: now), 99)
}

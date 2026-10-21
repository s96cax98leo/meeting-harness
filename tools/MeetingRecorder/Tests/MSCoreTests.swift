// meeting-speed spec §3.10 的 Swift Core 新名稱、§4 驗法欄 `swift:` 前綴的測試（Red 層 red-swift）。
// 每個測試的註解標明對應的 spec 條號；斷言的字面一律照 spec §3.10「字面」段逐字。
// 型別一律寫全名（例如 `PrepOutcome.ok`），避免 Core 尚未實作時出現「缺名稱」以外的編譯錯誤。
// 範例場次名一律用「[Stand-up] 範例專案」。
import Foundation

let mrtMSCoreTests: [MRTCase] = [
    // §4.1.3
    ("testMSStatusFieldsOmittedWhenNil", testMSStatusFieldsOmittedWhenNil),
    ("testMSCanvasLockCodable", testMSCanvasLockCodable),
    ("testMSOldStatusDecodes", testMSOldStatusDecodes),
    // §4.2.8
    ("testMSIsAudioReadyLine", testMSIsAudioReadyLine),
    // §4.2.9
    ("testMSAutoPrepPickEarly", testMSAutoPrepPickEarly),
    ("testMSAutoPrepPickNoDoubleEnqueue", testMSAutoPrepPickNoDoubleEnqueue),
    ("testMSAutoPrepPickDoneFallback", testMSAutoPrepPickDoneFallback),
    // §4.8.6
    ("testMSPrepOutcomeOk", testMSPrepOutcomeOk),
    ("testMSPrepOutcomeFailed", testMSPrepOutcomeFailed),
    ("testMSPrepOutcomeUnknown", testMSPrepOutcomeUnknown),
    // §4.8.7、§4.12.2
    ("testMSPrepNotification", testMSPrepNotification),
    // §4.10.1
    ("testMSAudioProbeDeviceFailed", testMSAudioProbeDeviceFailed),
    ("testMSAudioProbePassthrough", testMSAudioProbePassthrough),
    ("testMSAudioDeviceFailedMessage", testMSAudioDeviceFailedMessage),
    // §4.10.3
    ("testMSStopPathLogLine", testMSStopPathLogLine),
    // §4.11.1
    ("testMSAsrWorkerShouldStart", testMSAsrWorkerShouldStart),
    // §4.12.1
    ("testMSSessionCodeLabel", testMSSessionCodeLabel),
    // §4.12.3
    ("testMSCompletionNotificationBody", testMSCompletionNotificationBody),
    // §4.16.1
    ("testMSAbnormalStopDetected", testMSAbnormalStopDetected),
    ("testMSAbnormalStopNotWhenAlive", testMSAbnormalStopNotWhenAlive),
    ("testMSAbnormalStopNotWhenOtherPhase", testMSAbnormalStopNotWhenOtherPhase),
    ("testMSAbnormalStopNotWhenSessionMissing", testMSAbnormalStopNotWhenSessionMissing),
    ("testMSAbnormalStopNotWhenNoStatus", testMSAbnormalStopNotWhenNoStatus),
    ("testMSAbnormalStopNotWhenNoPendingSegments", testMSAbnormalStopNotWhenNoPendingSegments),
    // §4.16.2
    ("testMSAbnormalStopNotification", testMSAbnormalStopNotification),
]

// MARK: - 共用夾具

let mrtMSRunId = "6F1C2A3B-0000-4000-8000-000000000021"
let mrtMSStartedAt = "2026-10-21T09:30:00+08:00"
let mrtMSSessionName = "[Stand-up] 範例專案"
let mrtMSSession = "/x/20261021/[Stand-up] 範例專案"
/// `mrtMSStartedAt` 在 UTC+8 的場次代號（spec §3.10 sessionCodeLabel 字面）。
let mrtMSLabel = "10/21 09:30 開始的場次"
let mrtMSTZ = TimeZone(secondsFromGMT: 8 * 3600)!

func mrtMSStatus(_ phase: RecordPhase, code: Int32 = 0, runId: String = mrtMSRunId, pid: Int32 = 4242,
                 session: String = mrtMSSession, startedAt: String = mrtMSStartedAt) -> RecordStatus {
    RecordStatus(schemaVersion: 1, runId: runId, pid: pid, phase: phase, code: code, message: "",
                 session: session, startedAt: startedAt, updatedAt: startedAt, segments: 3,
                 preflight: [], warnings: [])
}

func mrtMSDecode<T: Decodable>(_ type: T.Type, _ json: String,
                               file: StaticString = #fileID, line: UInt = #line) -> T? {
    do { return try JSONDecoder().decode(type, from: Data(json.utf8)) } catch {
        mrtFail("解碼失敗：\(error)", file: file, line: line)
        return nil
    }
}

// MARK: - §4.1.3 狀態檔與 record.meta.json 新欄位

// §4.1.3、§3.1、§3.3：audioReady、droppedFrames、canvasLock 為 nil 時省略鍵；有值時寫出。
func testMSStatusFieldsOmittedWhenNil() throws {
    var s = mrtMSStatus(.finalizing)
    let plain = mrtJSONObject(s)
    mrtExpect(plain["audioReady"] == nil, "audioReady 為 nil 時不得有該鍵")
    mrtExpect(plain["droppedFrames"] == nil, "droppedFrames 為 nil 時不得有該鍵")

    s.audioReady = true
    s.droppedFrames = 3
    let filled = mrtJSONObject(s)
    mrtEqual(filled["audioReady"] as? Bool, true, "audioReady true 時應寫出")
    mrtEqual(filled["droppedFrames"] as? Int, 3, "droppedFrames 有值時應寫出")

    var meta = mrtSampleMeta()
    mrtExpect(mrtJSONObject(meta)["canvasLock"] == nil, "canvasLock 為 nil 時不得有該鍵")
    meta.canvasLock = CanvasLock(width: 1920, height: 1080)
    let lock = mrtJSONObject(meta)["canvasLock"] as? [String: Any]
    mrtEqual(Set((lock ?? [:]).keys), ["width", "height"], "canvasLock 的鍵恰為 width、height")
    mrtEqual(lock?["width"] as? Int, 1920)
    mrtEqual(lock?["height"] as? Int, 1080)
}

// §4.1.3、§3.3：CanvasLock 是 Codable、Equatable，可來回編解碼；RecordMeta 帶 canvasLock 可來回。
func testMSCanvasLockCodable() throws {
    let lock = CanvasLock(width: 1280, height: 720)
    let lockObj = mrtJSONObject(lock)
    mrtEqual(Set(lockObj.keys), ["width", "height"], "CanvasLock 的鍵恰為 width、height")
    let lockJSON = String(decoding: try JSONSerialization.data(withJSONObject: lockObj), as: UTF8.self)
    mrtEqual(mrtMSDecode(CanvasLock.self, lockJSON), lock, "CanvasLock 來回編解碼應相等")
    mrtEqual(mrtMSDecode(CanvasLock.self, #"{"width":1920,"height":1080}"#), CanvasLock(width: 1920, height: 1080))

    var meta = mrtSampleMeta()
    meta.canvasLock = lock
    let metaBack = try JSONDecoder().decode(RecordMeta.self, from: try JSONEncoder().encode(meta))
    mrtEqual(metaBack.canvasLock, lock, "RecordMeta.canvasLock 來回編解碼應保留")
    mrtEqual(metaBack, meta)
}

// §4.1.3：舊版狀態檔（沒有 audioReady、droppedFrames）與舊 record.meta.json（沒有 canvasLock）應能解碼，新欄位為 nil。
func testMSOldStatusDecodes() throws {
    let oldStatus = """
    {"schemaVersion":1,"runId":"\(mrtMSRunId)","pid":4242,"phase":"finalizing","code":0,"message":"",
     "session":"\(mrtMSSession)","startedAt":"\(mrtMSStartedAt)","updatedAt":"\(mrtMSStartedAt)",
     "segments":3,"preflight":[],"warnings":[],"background":true}
    """
    let st = mrtMSDecode(RecordStatus.self, oldStatus)
    mrtExpect(st != nil, "舊版狀態檔應能解碼")
    mrtEqual(st?.audioReady, nil, "舊檔沒有 audioReady → nil")
    mrtEqual(st?.droppedFrames, nil, "舊檔沒有 droppedFrames → nil")
    mrtEqual(st?.phase, .finalizing)

    let newStatus = """
    {"schemaVersion":1,"runId":"\(mrtMSRunId)","pid":4242,"phase":"finalizing","code":0,"message":"",
     "session":"\(mrtMSSession)","startedAt":"\(mrtMSStartedAt)","updatedAt":"\(mrtMSStartedAt)",
     "segments":3,"preflight":[],"warnings":[],"audioReady":true,"droppedFrames":2}
    """
    let st2 = mrtMSDecode(RecordStatus.self, newStatus)
    mrtEqual(st2?.audioReady, true)
    mrtEqual(st2?.droppedFrames, 2)

    // 舊 record.meta.json：以現行（不含 canvasLock）的編碼結果當舊檔。
    let oldMeta = mrtSampleMeta()
    let oldObj = mrtJSONObject(oldMeta)
    mrtExpect(oldObj["canvasLock"] == nil, "前提：舊 meta 沒有 canvasLock 鍵")
    let oldData = try JSONSerialization.data(withJSONObject: oldObj)
    let decoded = try JSONDecoder().decode(RecordMeta.self, from: oldData)
    mrtEqual(decoded.canvasLock, nil, "舊 meta 沒有 canvasLock → nil")
}

// MARK: - §4.2.8 音訊就緒行

// §4.2.8、§3.8：去掉前導空白後以「音訊就緒：」開頭才成立。
func testMSIsAudioReadyLine() throws {
    mrtExpect(isAudioReadyLine("音訊就緒：錄音/\(mrtMSSessionName) 2026-10-21 09.30.00.wav"), "標準行")
    mrtExpect(isAudioReadyLine("  音訊就緒：錄音/a.wav"), "前導空白應去掉")
    mrtExpect(isAudioReadyLine("\t音訊就緒：錄音/a.wav"), "前導 tab 應去掉")
    mrtExpect(!isAudioReadyLine("成品就緒：影片/a.mov"), "成品就緒不是音訊就緒")
    mrtExpect(!isAudioReadyLine(""), "空字串")
    mrtExpect(!isAudioReadyLine("· 音訊就緒：錄音/a.wav"), "前面有其他字元")
    mrtExpect(!isAudioReadyLine("音訊就緒"), "缺全形冒號")
    mrtExpect(!isAudioReadyLine("音訊就緒:錄音/a.wav"), "半形冒號不算")
}

// MARK: - §4.2.9 autoPrepPick

/// `.finalizing`＋`audioReady == true` 的狀態（§4.2.9 `.early` 的前提）。
func mrtMSFinalizingReady(runId: String = mrtMSRunId) -> RecordStatus {
    var s = mrtMSStatus(.finalizing, runId: runId)
    s.audioReady = true
    return s
}

// §4.2.9：finalizing＋audioReady＋未捨棄＋曾在進行中被看見＋尚未排過 → .early；任一條件不成立 → nil。
func testMSAutoPrepPickEarly() throws {
    let seen: Set<String> = [mrtMSRunId]
    let ready = mrtMSFinalizingReady()
    mrtEqual(autoPrepPick(autoPrep: true, status: ready, seenInProgressRunIds: seen, enqueuedRunIds: []),
             AutoPrepPick.early(session: mrtMSSession, runId: mrtMSRunId), "條件全部成立 → .early")

    mrtEqual(autoPrepPick(autoPrep: false, status: ready, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "自動前處理關閉")
    mrtEqual(autoPrepPick(autoPrep: true, status: nil, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "沒有狀態")

    var notReady = mrtMSStatus(.finalizing)
    mrtEqual(autoPrepPick(autoPrep: true, status: notReady, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "audioReady nil")
    notReady.audioReady = false
    mrtEqual(autoPrepPick(autoPrep: true, status: notReady, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "audioReady false")

    var discarded = ready
    discarded.discarded = true
    mrtEqual(autoPrepPick(autoPrep: true, status: discarded, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "discarded true")

    mrtEqual(autoPrepPick(autoPrep: true, status: ready, seenInProgressRunIds: [], enqueuedRunIds: []), nil,
             "runId 沒在進行中被看見")

    for phase in [RecordPhase.recording, .stopping] {
        var s = mrtMSStatus(phase)
        s.audioReady = true
        mrtEqual(autoPrepPick(autoPrep: true, status: s, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
                 "phase \(phase.rawValue) 不排 .early")
    }
}

// §4.2.9：同一 runId 排過 .early 之後，finalizing 不再回 .early、done 時不得再回 .done。
func testMSAutoPrepPickNoDoubleEnqueue() throws {
    let seen: Set<String> = [mrtMSRunId]
    let enqueued: Set<String> = [mrtMSRunId]
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSFinalizingReady(), seenInProgressRunIds: seen,
                          enqueuedRunIds: enqueued), nil, "已排過 → 不再回 .early")

    var done = mrtMSStatus(.done)
    done.audioReady = true
    mrtEqual(autoPrepPick(autoPrep: true, status: done, seenInProgressRunIds: seen, enqueuedRunIds: enqueued), nil,
             "排過 .early 的 runId 在 .done 時不得再回 .done")

    // 別的 runId 已排過，不影響這一場。
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSFinalizingReady(), seenInProgressRunIds: seen,
                          enqueuedRunIds: ["other-run"]),
             AutoPrepPick.early(session: mrtMSSession, runId: mrtMSRunId), "別場排過不影響")
}

// §4.2.9：沒排過 .early 的場次在 .done 時照 shouldAutoPrep 的條件回 .done。
func testMSAutoPrepPickDoneFallback() throws {
    let seen: Set<String> = [mrtMSRunId]
    let done = mrtMSStatus(.done)
    mrtEqual(autoPrepPick(autoPrep: true, status: done, seenInProgressRunIds: seen, enqueuedRunIds: []),
             AutoPrepPick.done(session: mrtMSSession, runId: mrtMSRunId), "done＋code 0＋看見過＋沒排過 → .done")
    mrtEqual(shouldAutoPrep(autoPrep: true, status: done, seenInProgressRunIds: seen, lastAutoPrepRunId: nil),
             mrtMSSession, "前提：shouldAutoPrep 對同一輸入成立")

    // 舊錄製器沒有 audioReady 時，只走 .done 路徑。
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSStatus(.finalizing), seenInProgressRunIds: seen,
                          enqueuedRunIds: []), nil, "finalizing 但沒有 audioReady → 等 done")

    mrtEqual(autoPrepPick(autoPrep: false, status: done, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "自動前處理關閉")
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSStatus(.done, code: 5), seenInProgressRunIds: seen,
                          enqueuedRunIds: []), nil, "code 5（同 shouldAutoPrep）")
    mrtEqual(autoPrepPick(autoPrep: true, status: done, seenInProgressRunIds: [], enqueuedRunIds: []), nil,
             "沒在進行中被看見（同 shouldAutoPrep）")
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSStatus(.done, session: ""), seenInProgressRunIds: seen,
                          enqueuedRunIds: []), nil, "session 空（同 shouldAutoPrep）")
    var discarded = done
    discarded.discarded = true
    mrtEqual(autoPrepPick(autoPrep: true, status: discarded, seenInProgressRunIds: seen, enqueuedRunIds: []), nil,
             "discarded true（同 shouldAutoPrep）")
    mrtEqual(autoPrepPick(autoPrep: true, status: mrtMSStatus(.failed, code: 5), seenInProgressRunIds: seen,
                          enqueuedRunIds: []), nil, "failed 不排")
}

// MARK: - §4.8.6 prepOutcome

func mrtMSPipeline(_ json: String) -> Data { Data(json.utf8) }

// §4.8.6、§3.5：prep.runId 等於這次、expect 的每個 stage 都是 done 且帶同一 runId → .ok。
func testMSPrepOutcomeOk() throws {
    let ok = mrtMSPipeline("""
    {"prep":{"runId":"R1","startedAt":"2026-10-21T11:30:15+08:00","expect":["transcribe","diarize"]},
     "stages":{"record":{"status":"done"},
               "transcribe":{"status":"done","runId":"R1"},
               "diarize":{"status":"done","runId":"R1"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: ok, runId: "R1"), PrepOutcome.ok)

    // 不在 expect 的 stage（record 不帶 runId、別次的 slide-ocr）不影響結果。
    let extra = mrtMSPipeline("""
    {"prep":{"runId":"R1","expect":["transcribe"]},
     "stages":{"record":{"status":"done"},
               "transcribe":{"status":"done","runId":"R1"},
               "slide-ocr":{"status":"failed","runId":"R0"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: extra, runId: "R1"), PrepOutcome.ok, "只看 expect 列的 stage")
}

// §4.8.6：expect 中有任何 stage 不是 done、或 runId 不同、或缺 → .failed([stage…])，依 expect 順序。
func testMSPrepOutcomeFailed() throws {
    let diarizeFailed = mrtMSPipeline("""
    {"prep":{"runId":"R1","expect":["transcribe","diarize"]},
     "stages":{"transcribe":{"status":"done","runId":"R1"},
               "diarize":{"status":"failed","runId":"R1"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: diarizeFailed, runId: "R1"), PrepOutcome.failed(["diarize"]))

    let order = mrtMSPipeline("""
    {"prep":{"runId":"R1","expect":["transcribe","slide-ocr","diarize"]},
     "stages":{"diarize":{"status":"failed","runId":"R1"},
               "slide-ocr":{"status":"done","runId":"R1"},
               "transcribe":{"status":"failed","runId":"R1"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: order, runId: "R1"), PrepOutcome.failed(["transcribe", "diarize"]),
             "依 expect 順序列出")

    let staleRun = mrtMSPipeline("""
    {"prep":{"runId":"R1","expect":["transcribe","diarize"]},
     "stages":{"transcribe":{"status":"done","runId":"R1"},
               "diarize":{"status":"done","runId":"R0"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: staleRun, runId: "R1"), PrepOutcome.failed(["diarize"]),
             "done 但 runId 是上一次 → 不算")

    let missing = mrtMSPipeline("""
    {"prep":{"runId":"R1","expect":["transcribe","diarize"]},
     "stages":{"transcribe":{"status":"done","runId":"R1"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: missing, runId: "R1"), PrepOutcome.failed(["diarize"]),
             "expect 列了但沒有該 stage")
}

// §4.8.6：讀不到檔、JSON 壞、prep.runId 不同 → .unknown。
func testMSPrepOutcomeUnknown() throws {
    mrtEqual(prepOutcome(pipelineState: nil, runId: "R1"), PrepOutcome.unknown, "讀不到檔")
    mrtEqual(prepOutcome(pipelineState: mrtMSPipeline("{not json"), runId: "R1"), PrepOutcome.unknown, "JSON 壞")
    let otherRun = mrtMSPipeline("""
    {"prep":{"runId":"R0","expect":["transcribe"]},
     "stages":{"transcribe":{"status":"done","runId":"R0"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: otherRun, runId: "R1"), PrepOutcome.unknown, "prep.runId 不同")
    let legacy = mrtMSPipeline("""
    {"stages":{"transcribe":{"status":"done"}}}
    """)
    mrtEqual(prepOutcome(pipelineState: legacy, runId: "R1"), PrepOutcome.unknown,
             "舊格式沒有 prep → prep.runId 不等於這次")
}

// MARK: - §4.8.7、§4.12.2 prepNotification

// §3.10 字面：.ok＋0 → 完成；.failed＋0、.unknown＋0、結束碼 ≠ 0 → 失敗；內文以 label 開頭，不含場次名或路徑。
func testMSPrepNotification() throws {
    let label = mrtMSLabel
    let ok = prepNotification(outcome: PrepOutcome.ok, exitCode: 0, label: label)
    mrtEqual(ok.title, "前處理完成")
    mrtEqual(ok.body, label)

    let failed = prepNotification(outcome: PrepOutcome.failed(["transcribe", "diarize"]), exitCode: 0, label: label)
    mrtEqual(failed.title, "前處理失敗")
    mrtEqual(failed.body, "\(label)：transcribe、diarize 失敗，詳見 autoprep.log")

    let one = prepNotification(outcome: PrepOutcome.failed(["diarize"]), exitCode: 0, label: label)
    mrtEqual(one.body, "\(label)：diarize 失敗，詳見 autoprep.log")

    let unknown = prepNotification(outcome: PrepOutcome.unknown, exitCode: 0, label: label)
    mrtEqual(unknown.title, "前處理失敗")
    mrtEqual(unknown.body, "\(label)：無法確認結果，詳見 autoprep.log")

    for outcome in [PrepOutcome.ok, PrepOutcome.failed(["diarize"]), PrepOutcome.unknown] {
        let n = prepNotification(outcome: outcome, exitCode: 3, label: label)
        mrtEqual(n.title, "前處理失敗", "結束碼 ≠ 0 一律失敗（\(outcome)）")
        mrtEqual(n.body, "\(label)：結束碼 3，詳見 autoprep.log", "結束碼 ≠ 0 的內文（\(outcome)）")
    }

    for n in [ok, failed, one, unknown] {
        mrtExpect(n.body.hasPrefix(label), "內文以場次代號開頭：\(n.body)")
        mrtExpect(!n.title.contains(mrtMSSessionName) && !n.body.contains(mrtMSSessionName), "不得含場次名")
        mrtExpect(!n.body.contains(mrtMSSession) && !n.body.contains("/x/"), "不得含路徑：\(n.body)")
    }
}

// MARK: - §4.10.1 preflight 音訊裝置

// §4.10.1：probe stream 開不起來 → .deviceFailed，不論 peak 值。
func testMSAudioProbeDeviceFailed() throws {
    mrtEqual(audioProbeVerdict(opened: false, targetPeakDBFS: -10, displayPeakDBFS: -10, thresholdDBFS: -60),
             AudioProbeVerdict.deviceFailed, "peak 高於門檻也要回 deviceFailed")
    mrtEqual(audioProbeVerdict(opened: false, targetPeakDBFS: -.infinity, displayPeakDBFS: nil, thresholdDBFS: -60),
             AudioProbeVerdict.deviceFailed, "全靜音、沒有 display peak")
    mrtEqual(audioProbeVerdict(opened: false, targetPeakDBFS: .nan, displayPeakDBFS: -80, thresholdDBFS: -60),
             AudioProbeVerdict.deviceFailed)
}

// §4.10.1：開得起來時應等於 .check(systemAudioCheck(…))；既有 SystemAudioCheck 不改。
func testMSAudioProbePassthrough() throws {
    let cases: [(Double, Double?, Double)] = [
        (-20, nil, -60),       // pass
        (-80, -20, -60),       // warnTargetSilent
        (-80, -90, -60),       // fail
        (-80, nil, -60),       // fail
        (.nan, nil, -60),      // NaN 視同 -∞ → fail
    ]
    for (t, d, th) in cases {
        mrtEqual(audioProbeVerdict(opened: true, targetPeakDBFS: t, displayPeakDBFS: d, thresholdDBFS: th),
                 AudioProbeVerdict.check(systemAudioCheck(targetPeakDBFS: t, displayPeakDBFS: d, thresholdDBFS: th)),
                 "target \(t) display \(String(describing: d)) 門檻 \(th)")
    }
    mrtEqual(audioProbeVerdict(opened: true, targetPeakDBFS: -20, displayPeakDBFS: nil, thresholdDBFS: -60),
             AudioProbeVerdict.check(SystemAudioCheck.pass))
    mrtEqual(audioProbeVerdict(opened: true, targetPeakDBFS: -80, displayPeakDBFS: -20, thresholdDBFS: -60),
             AudioProbeVerdict.check(SystemAudioCheck.warnTargetSilent))
    mrtEqual(audioProbeVerdict(opened: true, targetPeakDBFS: -80, displayPeakDBFS: -90, thresholdDBFS: -60),
             AudioProbeVerdict.check(SystemAudioCheck.fail))
}

// §4.10.1、§3.10 字面：音訊裝置無法啟動（輸入：<input>／<inputTransport>；輸出：<output>／<outputTransport>）。
func testMSAudioDeviceFailedMessage() throws {
    mrtEqual(audioDeviceFailedMessage(input: "MacBook 麥克風", inputTransport: "builtIn",
                                      output: "範例藍牙耳機", outputTransport: "bluetooth"),
             "音訊裝置無法啟動（輸入：MacBook 麥克風／builtIn；輸出：範例藍牙耳機／bluetooth）")
    mrtEqual(audioDeviceFailedMessage(input: "", inputTransport: "", output: "", outputTransport: ""),
             "音訊裝置無法啟動（輸入：／；輸出：／）")
}

// MARK: - §4.10.3 停止路徑 log

// §3.10 字面：停止略過（<source>）：<reason>。
func testMSStopPathLogLine() throws {
    mrtEqual(stopPathLogLine(source: "hudStop", reason: "沒有進行中的錄製"), "停止略過（hudStop）：沒有進行中的錄製")
    mrtEqual(stopPathLogLine(source: "Onboarding.sendStop", reason: "record.sh 不存在"),
             "停止略過（Onboarding.sendStop）：record.sh 不存在")
    mrtEqual(stopPathLogLine(source: "", reason: ""), "停止略過（）：")
}

// MARK: - §4.11.1 增量轉錄 worker 啟動條件

// §4.11.1：第一段收尾、worker 檔存在、incremental 不是 false、尚未起過 → 起一次；其餘不起。
func testMSAsrWorkerShouldStart() throws {
    mrtExpect(asrWorkerShouldStart(finishedSegments: 1, alreadyStarted: false, workerScriptExists: true,
                                   incrementalEnabled: true), "第一段收尾 → 起 worker")
    mrtExpect(!asrWorkerShouldStart(finishedSegments: 0, alreadyStarted: false, workerScriptExists: true,
                                    incrementalEnabled: true), "還沒有段落收尾")
    mrtExpect(!asrWorkerShouldStart(finishedSegments: 1, alreadyStarted: true, workerScriptExists: true,
                                    incrementalEnabled: true), "已起過 → 只起一次")
    mrtExpect(!asrWorkerShouldStart(finishedSegments: 3, alreadyStarted: true, workerScriptExists: true,
                                    incrementalEnabled: true), "已起過、之後的段落收尾不再起")
    mrtExpect(!asrWorkerShouldStart(finishedSegments: 1, alreadyStarted: false, workerScriptExists: false,
                                    incrementalEnabled: true), "bin/lib/_asr_worker.py 不存在 → 走舊流程")
    mrtExpect(!asrWorkerShouldStart(finishedSegments: 1, alreadyStarted: false, workerScriptExists: true,
                                    incrementalEnabled: false), "transcribe.incremental.enabled 為 false")
}

// MARK: - §4.12.1 場次代號

// §3.10 字面：startedAt 可解析 → `M/d HH:mm 開始的場次`；不可解析 → `場次 <runId 前 8 個字元>`；backgroundJobLabel 輸出不變。
func testMSSessionCodeLabel() throws {
    mrtEqual(sessionCodeLabel(startedAt: mrtMSStartedAt, runId: mrtMSRunId, timeZone: mrtMSTZ), mrtMSLabel)
    mrtEqual(sessionCodeLabel(startedAt: "2026-01-05T08:05:00+08:00", runId: mrtMSRunId, timeZone: mrtMSTZ),
             "1/5 08:05 開始的場次", "月日不補零、時分補零")
    mrtEqual(sessionCodeLabel(startedAt: "2026-10-21T01:30:00Z", runId: mrtMSRunId, timeZone: mrtMSTZ),
             mrtMSLabel, "依 timeZone 換算")
    mrtEqual(sessionCodeLabel(startedAt: "", runId: mrtMSRunId, timeZone: mrtMSTZ), "場次 6F1C2A3B")
    mrtEqual(sessionCodeLabel(startedAt: "不是時間", runId: "abc", timeZone: mrtMSTZ), "場次 abc",
             "runId 不足 8 字元時整串")

    for startedAt in [mrtMSStartedAt, "", "2026-01-05T08:05:00+08:00"] {
        let job = BackgroundFinalizeJob(status: mrtMSStatus(.finalizing, startedAt: startedAt), ownerAlive: true)
        mrtEqual(backgroundJobLabel(job, timeZone: mrtMSTZ),
                 sessionCodeLabel(startedAt: startedAt, runId: mrtMSRunId, timeZone: mrtMSTZ),
                 "backgroundJobLabel 與 sessionCodeLabel 輸出相同（startedAt「\(startedAt)」）")
    }
}

// MARK: - §4.12.3 錄製完成通知內文

// §3.10 字面：ok true → <label>；ok false → <label>：收尾有錯誤，詳見 record.log。
func testMSCompletionNotificationBody() throws {
    mrtEqual(completionNotificationBody(ok: true, label: mrtMSLabel), mrtMSLabel)
    mrtEqual(completionNotificationBody(ok: false, label: mrtMSLabel), "\(mrtMSLabel)：收尾有錯誤，詳見 record.log")
    for ok in [true, false] {
        let body = completionNotificationBody(ok: ok, label: mrtMSLabel)
        mrtExpect(!body.contains(mrtMSSessionName) && !body.contains(mrtMSSession), "不得含場次名或路徑")
    }
}

// MARK: - §4.16.1 異常中止判定

/// 異常中止的典型狀態：phase stopping、pid 4242。
func mrtMSStopping(pid: Int32 = 4242, session: String = mrtMSSession) -> RecordStatus {
    mrtMSStatus(.stopping, pid: pid, session: session)
}

// §4.16.1：stopping＋pid > 0＋pid 已不在＋session 非空且存在＋段落待收尾 → 回 status.session。
func testMSAbnormalStopDetected() throws {
    mrtEqual(abnormalStopSession(status: mrtMSStopping(), pidAlive: false, sessionExists: true, segmentsPending: true),
             mrtMSSession)
    mrtEqual(abnormalStopSession(status: mrtMSStopping(pid: 1), pidAlive: false, sessionExists: true,
                                 segmentsPending: true), mrtMSSession, "pid 1 也是正整數")
}

// §4.16.1：狀態檔記錄的 pid 還在、或 pid 不是正整數 → nil。
func testMSAbnormalStopNotWhenAlive() throws {
    mrtEqual(abnormalStopSession(status: mrtMSStopping(), pidAlive: true, sessionExists: true, segmentsPending: true),
             nil, "pid 還活著（正常停止中）")
    mrtEqual(abnormalStopSession(status: mrtMSStopping(pid: 0), pidAlive: false, sessionExists: true,
                                 segmentsPending: true), nil, "pid 0 不算")
    mrtEqual(abnormalStopSession(status: mrtMSStopping(pid: -1), pidAlive: false, sessionExists: true,
                                 segmentsPending: true), nil, "pid 負數不算")
}

// §4.16.1：phase 不是 stopping → nil。
func testMSAbnormalStopNotWhenOtherPhase() throws {
    let others: [RecordPhase] = [.preflight, .preflightFailed, .recording, .finalizing, .done, .failed]
    for phase in others {
        mrtEqual(abnormalStopSession(status: mrtMSStatus(phase), pidAlive: false, sessionExists: true,
                                     segmentsPending: true), nil, "phase \(phase.rawValue)")
    }
}

// §4.16.1：場次目錄不存在或 session 空 → nil。
func testMSAbnormalStopNotWhenSessionMissing() throws {
    mrtEqual(abnormalStopSession(status: mrtMSStopping(), pidAlive: false, sessionExists: false, segmentsPending: true),
             nil, "場次目錄不存在")
    mrtEqual(abnormalStopSession(status: mrtMSStopping(session: ""), pidAlive: false, sessionExists: true,
                                 segmentsPending: true), nil, "session 空字串")
}

// §4.16.1：沒有狀態檔 → nil。
func testMSAbnormalStopNotWhenNoStatus() throws {
    mrtEqual(abnormalStopSession(status: nil, pidAlive: false, sessionExists: true, segmentsPending: true), nil)
    mrtEqual(abnormalStopSession(status: nil, pidAlive: false, sessionExists: false, segmentsPending: false), nil)
}

// §4.16.1、§7 疑慮 15：段落不是待收尾（已收尾、keep-segments 留著段落）→ nil，壓掉收尾後的重複通知。
func testMSAbnormalStopNotWhenNoPendingSegments() throws {
    mrtEqual(abnormalStopSession(status: mrtMSStopping(), pidAlive: false, sessionExists: true,
                                 segmentsPending: false), nil)
}

// MARK: - §4.16.2 異常中止通知

// §3.10 字面：(上次錄製異常中止, <label>：段落還在，按「收尾」執行 meeting record finish)；不含場次名或路徑。
func testMSAbnormalStopNotification() throws {
    let label = sessionCodeLabel(startedAt: mrtMSStartedAt, runId: mrtMSRunId, timeZone: mrtMSTZ)
    let n = abnormalStopNotification(label: label)
    mrtEqual(n.title, "上次錄製異常中止")
    mrtEqual(n.body, "\(mrtMSLabel)：段落還在，按「收尾」執行 meeting record finish")
    mrtExpect(!n.title.contains(mrtMSSessionName) && !n.body.contains(mrtMSSessionName), "不得含場次名")
    mrtExpect(!n.body.contains(mrtMSSession), "不得含路徑")
}

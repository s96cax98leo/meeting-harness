// spec §3.20（Core/SegmentScheduler.swift）、§4.36.1–§4.36.8：換段排程的純狀態機。
// 時間單位為秒（錄製時鐘）；seg 從 1 起編；segmentSeconds=60。每個斷言是「已處理的事件序列 → 最後一個事件回傳的動作」。
import Foundation

let mrtR3SegmentSchedulerTests: [MRTCase] = [
    ("testFirstSample", testFirstSample),
    ("testPeriodicSwitchAndPrevClose", testPeriodicSwitchAndPrevClose),
    ("testPrevTimeout", testPrevTimeout),
    ("testPauseResume", testPauseResume),
    ("testPauseEmptySegmentCancelled", testPauseEmptySegmentCancelled),
    ("testStopFinishOrCancel", testStopFinishOrCancel),
    ("testWriterFailureRepeated", testWriterFailureRepeated),
    ("testFormatChange", testFormatChange),
    ("testOutputDeviceChange", testOutputDeviceChange),
]

func mrtS(_ track: SchedulerTrack, _ start: Double, _ end: Double, formatChanged: Bool = false) -> SchedulerEvent {
    .sample(track: track, start: start, end: end, formatChanged: formatChanged)
}

func mrtR3HasOpen(_ actions: [SchedulerAction]) -> Bool {
    actions.contains { if case .open = $0 { return true }; return false }
}

func mrtR3HasCancel(_ actions: [SchedulerAction]) -> Bool {
    actions.contains { if case .cancel = $0 { return true }; return false }
}

// §4.36.1
func testFirstSample() throws {
    mrtEqual(SchedulerTrack.allCases.map(\.rawValue), ["video", "system", "mic"], "SchedulerTrack")
    var s = SegmentScheduler(segmentSeconds: 60)
    mrtEqual(s.current, nil, "開始前沒有目前段")
    mrtEqual(s.prev, nil, "開始前沒有 prev")
    mrtEqual(s.handle(mrtS(.video, 0.0, 0.016)), [.open(segment: 1, reason: .first, boundary: 0.0), .write(segment: 1, track: .video)])
    mrtEqual(s.current, 1, "current")
    // 預設 segmentSeconds＝60
    var d = SegmentScheduler()
    _ = d.handle(mrtS(.video, 0.0, 0.016))
    mrtEqual(d.handle(mrtS(.system, 60.0, 60.02)), [.open(segment: 2, reason: .periodic, boundary: 60.0), .write(segment: 2, track: .system)],
             "init() 的 segmentSeconds 預設 60")
}

// §4.36.2：定期換段、跨邊界兩邊都寫、三路都過邊界才收 prev。
func testPeriodicSwitchAndPrevClose() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    mrtEqual(s.handle(mrtS(.system, 0.0, 0.02)), [.write(segment: 1, track: .system)], "第一段內的 system")
    mrtEqual(s.handle(mrtS(.mic, 0.0, 0.02)), [.write(segment: 1, track: .mic)], "第一段內的 mic")
    mrtEqual(s.handle(mrtS(.video, 30.0, 30.0)), [.write(segment: 1, track: .video)], "邊界前不換段")

    mrtEqual(s.handle(mrtS(.system, 60.0, 60.02)), [.open(segment: 2, reason: .periodic, boundary: 60.0), .write(segment: 2, track: .system)],
             "start ≥ 60 換段")
    mrtEqual(s.prev, 1, "換段後 prev == 1")
    mrtEqual(s.current, 2, "換段後 current == 2")
    mrtEqual(s.handle(mrtS(.mic, 59.99, 60.01)), [.write(segment: 1, track: .mic), .write(segment: 2, track: .mic)],
             "跨邊界兩邊都寫（routeSample .both）")
    let m = s.handle(mrtS(.mic, 60.01, 60.03))
    mrtExpect(!m.contains(.finish(segment: 1)), "video 還沒有過邊界的 sample，不得收 prev：\(m)")
    mrtEqual(m, [.write(segment: 2, track: .mic)], "mic 只寫新段")
    mrtEqual(s.prev, 1, "prev 仍在")
    let v = s.handle(mrtS(.video, 60.016, 60.016))
    mrtExpect(v.contains(.finish(segment: 1)), "三路都出現過 start ≥ 60 的 sample 時回傳含 finish(1)：\(v)")
    mrtExpect(v.contains(.write(segment: 2, track: .video)), "video 寫進新段：\(v)")
    mrtEqual(s.prev, nil, "收掉後 prev == nil")
}

// §4.36.3：prev 逾時。
func testPrevTimeout() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    _ = s.handle(mrtS(.system, 60.0, 60.02))
    mrtEqual(s.prev, 1, "前提：有 prev")
    mrtEqual(s.handle(.prevTimeout(segment: 1)), [.finish(segment: 1)], "有 prev 時")
    mrtEqual(s.prev, nil, "逾時收掉後 prev == nil")
    mrtEqual(s.handle(.prevTimeout(segment: 1)), [], "prev 已收掉時")
}

// §4.36.4：暫停／繼續。
func testPauseResume() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    _ = s.handle(mrtS(.mic, 5.0, 5.02))
    _ = s.handle(mrtS(.video, 10.0, 10.0))      // 已處理 sample 的最大 end＝10.0
    let p = s.handle(.pause)
    mrtExpect(!mrtR3HasOpen(p), "pause 回傳不含 open：\(p)")
    mrtExpect(!mrtR3HasCancel(p), "目前段有內容，pause 不得 cancel：\(p)")
    mrtEqual(s.prev, 1, "pause 後目前段轉 prev")
    mrtEqual(s.gate.paused, true, "gate.paused")
    mrtEqual(s.gate.cutPoint, 10.0, "停止點 E＝10.0")
    mrtEqual(s.handle(mrtS(.video, 9.98, 10.0)), [.write(segment: 1, track: .video)], "E 之前晚到的 sample 只進舊段")
    mrtEqual(s.handle(mrtS(.video, 12.0, 12.016)), [.drop(track: .video)], "暫停中")
    mrtEqual(s.handle(.resume), [], "resume")
    mrtEqual(s.handle(mrtS(.mic, 15.0, 15.02)), [.open(segment: 2, reason: .resume, boundary: 15.0), .write(segment: 2, track: .mic)],
             "繼續後第一個 sample 開新段")
    mrtEqual(s.current, 2, "current")
    mrtEqual(s.gate.paused, false, "gate.paused")
}

// §4.36.4 末句：暫停時目前段沒有寫過任何 sample → 回傳 cancel(該段)。
// 只用 §3.20 的公開事件無法造出「目前段已開、沒有 sample」（每個 open 都伴隨同一 sample 的 write），
// 此處只驗可達的反面：目前段有內容時不得 cancel；正面案例待 spec 補可達的事件序列（open_questions）。
func testPauseEmptySegmentCancelled() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    let first = s.handle(mrtS(.video, 0.0, 0.016))
    mrtEqual(first, [.open(segment: 1, reason: .first, boundary: 0.0), .write(segment: 1, track: .video)], "前提")
    let p = s.handle(.pause)
    mrtExpect(!p.contains(.cancel(segment: 1)), "目前段已寫過 sample，pause 不得 cancel(1)：\(p)")
    // 沒有任何 sample 就暫停：沒有目前段，不得產生 open 或 cancel
    var e = SegmentScheduler(segmentSeconds: 60)
    let ep = e.handle(.pause)
    mrtExpect(!mrtR3HasOpen(ep) && !mrtR3HasCancel(ep), "沒有目前段時 pause 不開段、不 cancel：\(ep)")
    mrtEqual(e.current, nil, "沒有目前段")
}

// §4.36.5：停止。
func testStopFinishOrCancel() throws {
    // 目前段有內容、且有 prev → finish 兩段
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    _ = s.handle(mrtS(.system, 60.0, 60.02))
    mrtEqual(s.prev, 1, "前提：有 prev")
    let st = s.handle(.stop)
    mrtExpect(st.contains(.finish(segment: 2)), "stop 回傳 finish(目前段)：\(st)")
    mrtExpect(st.contains(.finish(segment: 1)), "有 prev 也一併 finish：\(st)")
    mrtExpect(!mrtR3HasCancel(st) && !mrtR3HasOpen(st), "有內容時不 cancel、不 open：\(st)")
    // stop 之後任何 sample → drop
    mrtEqual(s.handle(mrtS(.mic, 61.0, 61.02)), [.drop(track: .mic)], "stop 之後 mic")
    mrtEqual(s.handle(mrtS(.video, 62.0, 62.0)), [.drop(track: .video)], "stop 之後 video")
    mrtEqual(s.handle(mrtS(.system, 63.0, 63.02, formatChanged: true)), [.drop(track: .system)], "stop 之後格式變更也 drop")

    // 只有一段、有內容 → finish(1)
    var one = SegmentScheduler(segmentSeconds: 60)
    _ = one.handle(mrtS(.video, 0.0, 0.016))
    mrtEqual(one.handle(.stop), [.finish(segment: 1)], "單段有內容")
}

// §4.36.6：writer 失敗與連續失敗。
func testWriterFailureRepeated() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    mrtEqual(s.handle(.writerFailed(segment: 1)), [], "writerFailed")
    mrtEqual(s.current, nil, "失敗後 current == nil")
    mrtEqual(s.handle(mrtS(.video, 30.0, 30.016)),
             [.open(segment: 2, reason: .writerFailure, boundary: 30.0), .write(segment: 2, track: .video)], "下一個 sample 開新段")
    mrtEqual(s.handle(.writerFailed(segment: 2)), [], "連續再失敗")
    mrtEqual(s.current, nil, "再失敗後 current == nil")
    let third = s.handle(mrtS(.video, 31.0, 31.016))
    mrtEqual(third, [.open(segment: 3, reason: .writerFailure, boundary: 31.0), .write(segment: 3, track: .video)], "再開 3")
    // 新段邊界不早於上一段起點：上一段起點 31.0，晚到的 sample start 30.5
    _ = s.handle(.writerFailed(segment: 3))
    let late = s.handle(mrtS(.mic, 30.5, 30.52))
    guard let firstAction = late.first, case let .open(seg, reason, boundary) = firstAction else {
        mrtFail("晚到的 sample 應開新段：\(late)", file: #fileID, line: #line); return
    }
    mrtEqual(seg, 4, "段號")
    mrtEqual(reason, SwitchReason.writerFailure, "原因")
    mrtExpect(boundary >= 31.0, "新段邊界 \(boundary) 不得早於上一段起點 31.0")
}

// §4.36.7：格式變更提前換段；1 秒內同一路再變不開新段。
func testFormatChange() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    _ = s.handle(mrtS(.system, 10.0, 10.02))
    mrtEqual(s.handle(mrtS(.system, 20.0, 20.02, formatChanged: true)),
             [.open(segment: 2, reason: .formatChange, boundary: 20.0), .write(segment: 2, track: .system)], "格式變更")
    let again = s.handle(mrtS(.system, 20.5, 20.52, formatChanged: true))
    mrtExpect(!mrtR3HasOpen(again), "1 秒內同一路再一次 formatChanged 不開新段：\(again)")
    mrtEqual(again, [.write(segment: 2, track: .system)], "照常寫進目前段")
    mrtEqual(s.current, 2, "current 不變")
}

// §4.36.8：輸出裝置變更在下一個 sample 換段；暫停中發生的由 resume 的換段吸收。
func testOutputDeviceChange() throws {
    var s = SegmentScheduler(segmentSeconds: 60)
    _ = s.handle(mrtS(.video, 0.0, 0.016))
    _ = s.handle(mrtS(.mic, 3.0, 3.02))
    mrtEqual(s.handle(.outputDeviceChange), [], "outputDeviceChange 本身不動作")
    mrtEqual(s.handle(mrtS(.mic, 5.0, 5.02)),
             [.open(segment: 2, reason: .outputDeviceChange, boundary: 5.0), .write(segment: 2, track: .mic)], "下一個 sample 換段")
    let after = s.handle(mrtS(.video, 5.1, 5.1))
    mrtExpect(!mrtR3HasOpen(after), "只換一次：\(after)")

    // 暫停中發生 → 由 resume 的換段吸收
    var p = SegmentScheduler(segmentSeconds: 60)
    _ = p.handle(mrtS(.video, 0.0, 0.016))
    _ = p.handle(mrtS(.video, 10.0, 10.0))
    _ = p.handle(.pause)
    mrtEqual(p.handle(.outputDeviceChange), [], "暫停中的 outputDeviceChange")
    _ = p.handle(.resume)
    mrtEqual(p.handle(mrtS(.mic, 15.0, 15.02)), [.open(segment: 2, reason: .resume, boundary: 15.0), .write(segment: 2, track: .mic)],
             "以 resume 換段")
    let next = p.handle(mrtS(.video, 15.1, 15.1))
    mrtExpect(!mrtR3HasOpen(next), "不另開 outputDeviceChange 段：\(next)")
    mrtEqual(p.current, 2, "current 仍為 2")
}

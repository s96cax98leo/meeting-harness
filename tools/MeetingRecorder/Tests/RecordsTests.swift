// spec §3.1–§3.3、§4.5.4：Records.swift（RecordStatus、Manifest、RecordMeta 與 writeJSONAtomically）。
// 鍵名＝Swift 屬性名，必須與 spec §3.1–§3.3 的範例一致；writeJSONAtomically 以 .sortedKeys 寫、
// Optional 為 nil 時寫 null（鍵不得省略）、同目錄 tmp 檔＋rename（寫完目錄裡只剩目標檔）。
// spec §4.4.6（D20）：WarningKind.segmentWriteFailed 的 raw value、isAlert 與 RecordWarning JSON 往返。
// spec §4.4.9（t6 第二輪，缺陷 D）：CompletionOutcome／completionOutcome（停止原因開頭、收尾失敗附在後面）。
import Foundation

let mrtRecordsTests: [MRTCase] = [
    ("testMetaJSONKeys", testMetaJSONKeys),
    ("testStatusJSONKeys", testStatusJSONKeys),
    ("testManifestJSONKeys", testManifestJSONKeys),
    ("testSegmentWriteFailedWarningKind", testSegmentWriteFailedWarningKind),
    ("testCompletionOutcome", testCompletionOutcome),
]

/// 用 writeJSONAtomically 寫進新的暫存目錄，回傳（JSON 物件、原始文字、寫完後目錄內的檔名）。
func mrtWriteAndRead<T: Encodable>(_ value: T, name: String) throws -> ([String: Any], String, [String]) {
    let dir = URL(fileURLWithPath: NSTemporaryDirectory())
        .appendingPathComponent("mr-tests-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: dir) }
    let url = dir.appendingPathComponent(name)
    try writeJSONAtomically(value, to: url)
    let data = try Data(contentsOf: url)
    let obj = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    let files = try FileManager.default.contentsOfDirectory(atPath: dir.path).sorted()
    return (obj, String(decoding: data, as: UTF8.self), files)
}

func mrtKeys(_ any: Any?) -> Set<String> { Set(((any as? [String: Any]) ?? [:]).keys) }
func mrtIsNull(_ any: Any?) -> Bool { any is NSNull }

/// 依 spec §3.3 範例建一份 RecordMeta（microphoneCaptureDeviceID 為 nil、一筆 deviceEvent 的 from 為 nil）。
func mrtSampleMeta() -> RecordMeta {
    let builtIn = AudioDeviceInfo(uid: "BuiltInMicrophoneDevice", name: "MacBook 麥克風", transport: "builtIn")
    let bt = AudioDeviceInfo(uid: "00-11-22-33-44-55:output", name: "範例藍牙耳機", transport: "bluetooth")
    return RecordMeta(
        schemaVersion: 1,
        window: WindowInfo(windowID: 89596, app: "Google Chrome", bundleID: "com.google.Chrome", title: "[Stand-up] 範例專案"),
        config: StreamConfigSnapshot(filter: "desktopIndependentWindow", onScreenWindowsOnly: false, scalesToFit: true,
                                     minimumFrameInterval: "1/60", capturesAudio: true, sampleRate: 48000, channelCount: 2,
                                     captureMicrophone: true, microphoneCaptureDeviceID: nil,
                                     excludesCurrentProcessAudio: true, fileType: "mov", videoCodec: "h264", segmentSeconds: 60),
        devices: AudioDevices(input: builtIn, output: bt),
        preflight: [PreflightResult(item: .screen_permission, ok: true)],
        deviceEvents: [DeviceEvent(t: 61.2, kind: .input, from: builtIn, to: bt),
                       DeviceEvent(t: 75.0, kind: .output, from: nil, to: bt)],
        audioFormatEvents: [AudioFormatEvent(t: 61.4, source: .system,
                                             from: AudioFormat(sampleRate: 48000, channels: 2, interleaved: false, sampleType: .float32),
                                             to: AudioFormat(sampleRate: 16000, channels: 1, interleaved: false, sampleType: .float32))])
}

// §4.5.4、§3.3：record.meta.json 的鍵集合與值。
func testMetaJSONKeys() throws {
    let meta = mrtSampleMeta()
    let (obj, text, files) = try mrtWriteAndRead(meta, name: "record.meta.json")
    mrtEqual(files, ["record.meta.json"], "寫完後目錄只剩目標檔（tmp＋rename）")
    mrtEqual(Set(obj.keys), ["schemaVersion", "window", "config", "devices", "preflight", "deviceEvents", "audioFormatEvents"])
    mrtExpect(obj["canvas"] == nil, "canvas 欄位已移除（D8）")
    mrtEqual(mrtKeys(obj["window"]), ["windowID", "app", "bundleID", "title"])
    mrtEqual(mrtKeys(obj["config"]), ["filter", "onScreenWindowsOnly", "scalesToFit", "minimumFrameInterval", "capturesAudio",
                                      "sampleRate", "channelCount", "captureMicrophone", "microphoneCaptureDeviceID",
                                      "excludesCurrentProcessAudio", "fileType", "videoCodec", "segmentSeconds"])
    let config = (obj["config"] as? [String: Any]) ?? [:]
    mrtExpect(mrtIsNull(config["microphoneCaptureDeviceID"]), "nil 應寫成 null")
    mrtEqual(config["minimumFrameInterval"] as? String, "1/60")
    mrtEqual(config["filter"] as? String, "desktopIndependentWindow")
    mrtEqual(mrtKeys(obj["devices"]), ["input", "output"])
    let devices = (obj["devices"] as? [String: Any]) ?? [:]
    mrtEqual(mrtKeys(devices["input"]), ["uid", "name", "transport"])
    mrtEqual((devices["output"] as? [String: Any])?["transport"] as? String, "bluetooth")

    let events = (obj["deviceEvents"] as? [[String: Any]]) ?? []
    mrtEqual(events.count, 2)
    mrtEqual(Set(events.first?.keys.map { $0 } ?? []), ["t", "kind", "from", "to"])
    mrtEqual(events.first?["kind"] as? String, "input")
    mrtEqual(mrtKeys(events.first?["from"]), ["uid", "name", "transport"])
    mrtEqual(Set(events.last?.keys.map { $0 } ?? []), ["t", "kind", "from", "to"], "from 為 nil 仍要有鍵")
    mrtExpect(mrtIsNull(events.last?["from"]), "from 為 nil 應寫成 null")

    let fmts = (obj["audioFormatEvents"] as? [[String: Any]]) ?? []
    mrtEqual(Set(fmts.first?.keys.map { $0 } ?? []), ["t", "source", "from", "to"])
    mrtEqual(fmts.first?["source"] as? String, "system")
    mrtEqual(mrtKeys(fmts.first?["to"]), ["sampleRate", "channels", "interleaved", "sampleType"])
    mrtEqual((fmts.first?["to"] as? [String: Any])?["sampleType"] as? String, "float32")

    let pf = (obj["preflight"] as? [[String: Any]]) ?? []
    mrtEqual(Set(pf.first?.keys.map { $0 } ?? []), ["item", "ok", "severity", "code", "message"])

    // .sortedKeys：頂層鍵依字典序出現
    let order = ["\"audioFormatEvents\"", "\"config\"", "\"deviceEvents\"", "\"devices\"", "\"preflight\"",
                 "\"schemaVersion\"", "\"window\""]
    let positions = order.compactMap { text.range(of: $0)?.lowerBound }
    mrtEqual(positions.count, order.count)
    mrtEqual(positions, positions.sorted(), "鍵應依字典序排列")

    // 往返
    let back = try JSONDecoder().decode(RecordMeta.self, from: Data(text.utf8))
    mrtEqual(back, meta)
}

// §3.1：record.status.json 的鍵集合與 phase／warning 的 raw value。
func testStatusJSONKeys() throws {
    let status = RecordStatus(schemaVersion: 1, runId: "00000000-0000-4000-8000-000000000001", pid: 4242,
                              phase: .preflightFailed, code: 4, message: "沒有螢幕錄製權限\n請到系統設定開啟",
                              session: "/tmp/範例根/20261011/範例會議", startedAt: "2026-10-11T10:00:00+08:00",
                              updatedAt: "2026-10-11T10:00:03+08:00", segments: 0,
                              preflight: [PreflightResult(item: .screen_permission, ok: false, message: "沒有權限")],
                              warnings: [RecordWarning(t: 12.5, kind: .silenceMic, message: "麥克風已連續 15 秒沒有聲音")])
    let (obj, text, files) = try mrtWriteAndRead(status, name: "record.status.json")
    mrtEqual(files, ["record.status.json"])
    mrtEqual(Set(obj.keys), ["schemaVersion", "runId", "pid", "phase", "code", "message", "session", "startedAt",
                             "updatedAt", "segments", "preflight", "warnings"])
    mrtEqual(obj["phase"] as? String, "preflight_failed")
    let w = (obj["warnings"] as? [[String: Any]]) ?? []
    mrtEqual(Set(w.first?.keys.map { $0 } ?? []), ["t", "kind", "message"])
    mrtEqual(w.first?["kind"] as? String, "silence_mic")
    mrtEqual(try JSONDecoder().decode(RecordStatus.self, from: Data(text.utf8)), status)

    // raw value 對照 spec §3.4
    mrtEqual([RecordPhase.preflight, .preflightFailed, .recording, .stopping, .finalizing, .done, .failed].map { $0.rawValue },
             ["preflight", "preflight_failed", "recording", "stopping", "finalizing", "done", "failed"])
    mrtEqual([WarningKind.silenceSystem, .silenceMic, .black, .suspended, .diskLow, .deviceChange, .audioFormatChange].map { $0.rawValue },
             ["silence_system", "silence_mic", "black", "suspended", "disk_low", "device_change", "audio_format_change"])
}

// §3.2：manifest.json 的鍵集合；levels 的 nil 寫 null；gapStats 等 finalize 欄位為 nil 時鍵仍在、值為 null。
func testManifestJSONKeys() throws {
    let m = Manifest(schemaVersion: 1, segmentSeconds: 60,
                     segments: [SegmentRecord(file: "seg-0001.mov", requestedAt: 0, startedAt: 0.012, finishedAt: 60.031,
                                              width: 2992, height: 1876, audioDuration: nil)],
                     frameStatus: FrameStatusCounts(complete: 1, idle: 2, blank: 0, suspended: 0, started: 1, stopped: 0),
                     blackIntervals: [BlackInterval(start: 860, end: 1085), BlackInterval(start: 1200, end: nil)],
                     levels: AudioLevels(windowSeconds: 0.5, system: [-23.1, nil], mic: [-41.0, -38.2]),
                     gapStats: nil, outputCanvas: nil, outputVideoBitrate: nil)
    let (obj, text, _) = try mrtWriteAndRead(m, name: "manifest.json")
    mrtEqual(Set(obj.keys), ["schemaVersion", "segmentSeconds", "segments", "frameStatus", "blackIntervals", "levels",
                             "gapStats", "outputCanvas", "outputVideoBitrate"])
    mrtExpect(mrtIsNull(obj["gapStats"]) && mrtIsNull(obj["outputCanvas"]) && mrtIsNull(obj["outputVideoBitrate"]),
              "finalize 前的欄位應寫 null")
    let seg = ((obj["segments"] as? [[String: Any]]) ?? []).first ?? [:]
    mrtEqual(Set(seg.keys), ["file", "requestedAt", "startedAt", "finishedAt", "width", "height", "audioDuration"])
    mrtExpect(mrtIsNull(seg["audioDuration"]))
    mrtEqual(mrtKeys(obj["frameStatus"]), ["complete", "idle", "blank", "suspended", "started", "stopped"])
    let bi = (obj["blackIntervals"] as? [[String: Any]]) ?? []
    mrtEqual(bi.count, 2)
    mrtEqual(Set(bi.last?.keys.map { $0 } ?? []), ["start", "end"])
    mrtExpect(mrtIsNull(bi.last?["end"]), "未恢復的黑畫面區間 end 為 null")
    let levels = (obj["levels"] as? [String: Any]) ?? [:]
    mrtEqual(Set(levels.keys), ["windowSeconds", "system", "mic"])
    let sys = (levels["system"] as? [Any]) ?? []
    mrtEqual(sys.count, 2)
    mrtExpect(sys.count == 2 && mrtIsNull(sys[1]), "沒有緩衝的時段應寫 null")
    mrtEqual(try JSONDecoder().decode(Manifest.self, from: Data(text.utf8)), m)

    var done = m
    done.gapStats = GapStats(boundaries: [0.021], max: 0.021, total: 0.021, wallClock: 180.4)
    done.outputCanvas = PixelSize(width: 2992, height: 1876)
    done.outputVideoBitrate = 11605500
    let (o2, _, _) = try mrtWriteAndRead(done, name: "manifest.json")
    mrtEqual(mrtKeys(o2["gapStats"]), ["boundaries", "max", "total", "wallClock"])
    mrtEqual(mrtKeys(o2["outputCanvas"]), ["width", "height"])
}

// §4.4.6（D20）：segment_write_failed 為告警類；RecordWarning 以它往返 JSON 後相等；
// 既有七個 kind 的 raw value 與 isAlert 不變（§3.4）。
func testSegmentWriteFailedWarningKind() throws {
    let k: WarningKind = WarningKind.segmentWriteFailed
    mrtEqual(k.rawValue, "segment_write_failed")
    mrtEqual(k.isAlert, true, "segment_write_failed 應為告警類")
    mrtEqual(WarningKind(rawValue: "segment_write_failed"), WarningKind.segmentWriteFailed)

    let w = RecordWarning(t: 61.5, kind: WarningKind.segmentWriteFailed, message: "段落 seg-0002.mov 寫檔失敗，已開新段繼續錄")
    let data = try JSONEncoder().encode(w)
    let obj = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    mrtEqual(Set(obj.keys), ["t", "kind", "message"])
    mrtEqual(obj["kind"] as? String, "segment_write_failed")
    mrtEqual(try JSONDecoder().decode(RecordWarning.self, from: data), w)

    // 既有七個 kind 不變
    let existing: [(WarningKind, String, Bool)] = [
        (.silenceSystem, "silence_system", true), (.silenceMic, "silence_mic", true), (.black, "black", true),
        (.suspended, "suspended", true), (.diskLow, "disk_low", true),
        (.deviceChange, "device_change", false), (.audioFormatChange, "audio_format_change", false),
    ]
    for (kind, raw, alert) in existing {
        mrtEqual(kind.rawValue, raw)
        mrtEqual(kind.isAlert, alert, raw)
    }
}

// §4.4.9（t6 第二輪，缺陷 D）：錄製結束的最終結果。停止原因（forced 訊息）一律在最終訊息開頭，
// 收尾失敗原因附在其後，不得被蓋掉（§4.4.7）。
func testCompletionOutcome() throws {
    let forced = "段落連續寫檔失敗，已停止並收尾；已落盤段落保留"

    // (rc 5, forced (5, …), hadError true, "/x/s") → .failed、5、以「段落連續寫檔失敗」開頭且含收尾失敗與場次路徑
    let a: CompletionOutcome = completionOutcome(finalizeCode: 5, forcedCode: 5, forcedMessage: forced,
                                                 hadError: true, sessionPath: "/x/s")
    mrtEqual(a.phase, RecordPhase.failed, "收尾失敗＋forced")
    mrtEqual(a.code, Int32(5), "收尾失敗＋forced")
    mrtExpect(a.message.hasPrefix("段落連續寫檔失敗"), "訊息應以「段落連續寫檔失敗」開頭：\(a.message)")
    mrtExpect(a.message.hasPrefix(forced), "停止原因應完整保留在開頭：\(a.message)")
    mrtContains(a.message, "收尾失敗（_record_finalize.py 回 5）")
    mrtContains(a.message, "/x/s")
    if let r1 = a.message.range(of: "段落連續寫檔失敗"), let r2 = a.message.range(of: "收尾失敗（_record_finalize.py 回 5）") {
        mrtExpect(r1.lowerBound < r2.lowerBound, "收尾失敗原因應附在停止原因之後：\(a.message)")
    }

    // (rc 0, forced 同上, true) → .done、5、message 等於 forced 訊息
    let b: CompletionOutcome = completionOutcome(finalizeCode: 0, forcedCode: 5, forcedMessage: forced,
                                                 hadError: true, sessionPath: "/x/s")
    mrtEqual(b, CompletionOutcome(phase: .done, code: 5, message: forced), "收尾成功＋forced")

    // (rc 0, nil, true) → .done、5、"錄製中出過錯（見 record.log），已收尾；段落保留"
    let c: CompletionOutcome = completionOutcome(finalizeCode: 0, forcedCode: nil, forcedMessage: nil,
                                                 hadError: true, sessionPath: "/x/s")
    mrtEqual(c, CompletionOutcome(phase: .done, code: 5, message: "錄製中出過錯（見 record.log），已收尾；段落保留"),
             "收尾成功＋錄製中出過錯")

    // (rc 0, nil, false, "/x/s") → .done、0、"已完成：/x/s"
    let d: CompletionOutcome = completionOutcome(finalizeCode: 0, forcedCode: nil, forcedMessage: nil,
                                                 hadError: false, sessionPath: "/x/s")
    mrtEqual(d, CompletionOutcome(phase: .done, code: 0, message: "已完成：/x/s"), "正常完成")

    // (rc 127, nil, false, "/x/s") → .failed、5、以「收尾失敗（_record_finalize.py 回 127）」開頭
    let e: CompletionOutcome = completionOutcome(finalizeCode: 127, forcedCode: nil, forcedMessage: nil,
                                                 hadError: false, sessionPath: "/x/s")
    mrtEqual(e.phase, RecordPhase.failed, "收尾失敗 127")
    mrtEqual(e.code, Int32(5), "收尾失敗 127")
    mrtExpect(e.message.hasPrefix("收尾失敗（_record_finalize.py 回 127）"),
              "訊息應以「收尾失敗（_record_finalize.py 回 127）」開頭：\(e.message)")
}

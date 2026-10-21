// spec §3.17、§3.20（Core/SyncLatency.swift、Core/Records.swift 與 Core/Segments.swift 的增補）：輸出裝置延遲紀錄。
// 驗收：§4.35.5、§4.35.6、§4.36.9。RecordsTests.swift 的 testMetaJSONKeys 不改（§6 第 133 條）。
import Foundation

let mrtR3SyncTests: [MRTCase] = [
    ("testReportedLatency", testReportedLatency),
    ("testOutputLatenciesOmittedWhenNil", testOutputLatenciesOmittedWhenNil),
    ("testSwitchReasonCases", testSwitchReasonCases),
]

/// §3.17 的 outputLatencies 一筆的鍵。
let mrtR3OutputLatencyKeys: Set<String> = [
    "t", "uid", "transport", "sampleRate", "latencyFrames", "safetyOffsetFrames", "streamLatencyFrames", "bufferFrameSize",
    "reportedSeconds",
]

// §4.35.5：reportedLatencySeconds；OutputLatency 不是 AudioDeviceInfo 的欄位。
func testReportedLatency() throws {
    mrtNear(reportedLatencySeconds(sampleRate: 48000, latency: 24, safety: 144, stream: 0, buffer: 512), 0.0142, tol: 1e-9,
            "(48000, 24, 144, 0, 512)：四項幀數和 ÷ sampleRate，小數 4 位")
    mrtEqual(reportedLatencySeconds(sampleRate: nil, latency: 24, safety: 144, stream: 0, buffer: 512), nil, "sampleRate nil")
    mrtEqual(reportedLatencySeconds(sampleRate: 48000, latency: nil, safety: 144, stream: 0, buffer: 512), nil, "latency nil")
    mrtEqual(reportedLatencySeconds(sampleRate: 48000, latency: 24, safety: nil, stream: 0, buffer: 512), nil, "safety nil")
    mrtEqual(reportedLatencySeconds(sampleRate: 48000, latency: 24, safety: 144, stream: nil, buffer: 512), nil, "stream nil")
    mrtEqual(reportedLatencySeconds(sampleRate: 48000, latency: 24, safety: 144, stream: 0, buffer: nil), nil, "buffer nil")
    mrtEqual(reportedLatencySeconds(sampleRate: 0, latency: 24, safety: 144, stream: 0, buffer: 512), nil, "sampleRate 0")

    // AudioDeviceInfo 只有 uid、name、transport：延遲值不進它的 Equatable
    let labels = Mirror(reflecting: AudioDeviceInfo(uid: "u", name: "範例藍牙耳機", transport: "bluetooth")).children.compactMap(\.label)
    mrtEqual(labels, ["uid", "name", "transport"], "AudioDeviceInfo 不得有延遲欄位")
}

// §4.35.6、§3.17：RecordMeta.outputLatencies nil 時省略鍵；有值時鍵名同 §3.17，讀不到的數值欄寫 null。
func testOutputLatenciesOmittedWhenNil() throws {
    var meta = mrtSampleMeta()
    mrtEqual(meta.outputLatencies, nil, "預設 nil")
    mrtExpect(mrtJSONObject(meta)["outputLatencies"] == nil, "outputLatencies 為 nil 時編碼不得有該鍵")

    let full = OutputLatency(t: 0.0, uid: "00-11-22-33-44-55:output", transport: "bluetooth", sampleRate: 48000,
                             latencyFrames: 24, safetyOffsetFrames: 144, streamLatencyFrames: 0, bufferFrameSize: 512,
                             reportedSeconds: 0.0142)
    let partial = OutputLatency(t: 75.0, uid: "BuiltInSpeakerDevice", transport: "builtIn", sampleRate: nil,
                                latencyFrames: nil, safetyOffsetFrames: 16, streamLatencyFrames: nil, bufferFrameSize: 512,
                                reportedSeconds: nil)
    meta.outputLatencies = [full, partial]
    let obj = mrtJSONObject(meta)
    guard let arr = obj["outputLatencies"] as? [[String: Any]] else {
        mrtFail("有值時應編碼成陣列：\(String(describing: obj["outputLatencies"]))", file: #fileID, line: #line); return
    }
    mrtEqual(arr.count, 2, "筆數")
    mrtEqual(Set(arr[0].keys), mrtR3OutputLatencyKeys, "第一筆的鍵")
    mrtEqual(Set(arr[1].keys), mrtR3OutputLatencyKeys, "讀不到的數值欄也要有鍵（寫 null）")
    for k in ["sampleRate", "latencyFrames", "streamLatencyFrames", "reportedSeconds"] {
        mrtExpect(arr[1][k] is NSNull, "\(k) 讀不到時寫 null（實際 \(String(describing: arr[1][k]))）")
    }
    mrtEqual(arr[0]["transport"] as? String, "bluetooth")
    mrtNear((arr[0]["reportedSeconds"] as? NSNumber)?.doubleValue, 0.0142, tol: 1e-9, "reportedSeconds")

    // 解碼回來相等
    let data = try JSONEncoder().encode(meta)
    let back = try JSONDecoder().decode(RecordMeta.self, from: data)
    mrtEqual(back, meta, "encode → decode")
    // 既有其他鍵不變（R2 的鍵集合＋outputLatencies）
    mrtEqual(Set(obj.keys), ["schemaVersion", "window", "config", "devices", "preflight", "deviceEvents", "audioFormatEvents",
                             "outputLatencies"], "只多 outputLatencies")
}

// §4.36.9、§6 第 127 條：SwitchReason 恰為六個，outputDeviceChange 在最後。
func testSwitchReasonCases() throws {
    mrtEqual(SwitchReason.allCases, [.first, .periodic, .formatChange, .writerFailure, .resume, .outputDeviceChange],
             "SwitchReason 恰為六個")
    mrtEqual(SwitchReason.outputDeviceChange.rawValue, "outputDeviceChange", "rawValue")
}

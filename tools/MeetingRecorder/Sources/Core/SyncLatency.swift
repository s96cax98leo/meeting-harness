// Core/SyncLatency.swift —— 輸出裝置延遲紀錄與帶 lOut 的成品時間換算（spec §3.17、§3.20、§4.32.1、§4.35.5；
// design R3-D9；ADR adr-r3-sync-compensation.md）。
import Foundation

/// record.meta.json 的 outputLatencies 一筆（spec §3.17）。讀不到的數值欄寫 null（不省略鍵），所以自訂 encode。
/// 不是 AudioDeviceInfo 的欄位：AudioDeviceInfo 的 Equatable 不受延遲值影響（spec §4.35.5）。
struct OutputLatency: Codable, Equatable {
    var t: Double
    var uid: String
    var transport: String
    var sampleRate: Double?
    var latencyFrames: Int?
    var safetyOffsetFrames: Int?
    var streamLatencyFrames: Int?
    var bufferFrameSize: Int?
    var reportedSeconds: Double?

    enum CodingKeys: String, CodingKey {
        case t, uid, transport, sampleRate, latencyFrames, safetyOffsetFrames, streamLatencyFrames, bufferFrameSize, reportedSeconds
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(t, forKey: .t)
        try c.encode(uid, forKey: .uid)
        try c.encode(transport, forKey: .transport)
        try c.encode(sampleRate, forKey: .sampleRate)
        try c.encode(latencyFrames, forKey: .latencyFrames)
        try c.encode(safetyOffsetFrames, forKey: .safetyOffsetFrames)
        try c.encode(streamLatencyFrames, forKey: .streamLatencyFrames)
        try c.encode(bufferFrameSize, forKey: .bufferFrameSize)
        try c.encode(reportedSeconds, forKey: .reportedSeconds)
    }
}

/// (latency + safety + stream + buffer) ÷ sampleRate，小數 4 位；任一參數 nil 或 sampleRate ≤ 0 → nil。
func reportedLatencySeconds(sampleRate: Double?, latency: Int?, safety: Int?, stream: Int?, buffer: Int?) -> Double? {
    guard let sr = sampleRate, sr.isFinite, sr > 0,
          let l = latency, let s = safety, let st = stream, let b = buffer else { return nil }
    return (Double(l + s + st + b) / sr * 10_000).rounded() / 10_000
}

/// 同 R2 的 outputTime(recordT:firstSegmentStart:pauses:)，再加上系統聲音在成品裡的延遲 lOut（S-C 預留）；
/// < 0 夾成 0、小數 3 位。lOut = 0 時結果與 R2 版本相同（共用向量 tests/record/vectors/output_time.json）。
func outputTime(recordT: Double, firstSegmentStart: Double, pauses: [PauseEvent], lOut: Double) -> Double {
    let base = outputTime(recordT: recordT, firstSegmentStart: firstSegmentStart, pauses: pauses)
    return max(0, ((base + lOut) * 1000).rounded() / 1000)
}

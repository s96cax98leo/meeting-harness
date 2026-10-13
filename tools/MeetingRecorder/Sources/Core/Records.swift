// Core/Records.swift —— 狀態檔、manifest、meta 的資料型別與原子寫入（spec §3.1–§3.4）
//
// JSON 鍵名＝Swift 屬性名（不做 snake_case 轉換）。Optional 為 nil 時一律寫 null、不省略鍵：
// 合成的 Codable 對 Optional 用 encodeIfPresent（會省略鍵），所以含 Optional 的型別各自實作 encode(to:)。
// 例外（spec §3.10、§3.11、§6 第 79 條）：RecordStatus、RecordMeta、GapStats 的 R2 選用欄位 nil 時「省略鍵」，
// 靠的正是合成 Codable 的 encodeIfPresent——這三個型別不得改成自訂 encode(to:)，否則第一輪的鍵集合會變。
import Foundation

enum RecordPhase: String, Codable {
    case preflight, preflightFailed = "preflight_failed", recording, stopping, finalizing, done, failed
}

enum WarningKind: String, Codable {
    case silenceSystem = "silence_system", silenceMic = "silence_mic", black, suspended,
         diskLow = "disk_low", deviceChange = "device_change", audioFormatChange = "audio_format_change",
         segmentWriteFailed = "segment_write_failed"    // D20：段落 writer 失敗（design §7.2〈writer 失敗〉）

    /// 告警類（menu bar 轉告警態）為 true；紀錄類（裝置、音訊格式變更）為 false。
    var isAlert: Bool {
        switch self {
        case .silenceSystem, .silenceMic, .black, .suspended, .diskLow, .segmentWriteFailed: return true
        case .deviceChange, .audioFormatChange: return false
        }
    }
}

struct RecordWarning: Codable, Equatable {
    let t: Double
    let kind: WarningKind
    let message: String
}

struct RecordStatus: Codable, Equatable {
    var schemaVersion: Int
    var runId: String
    var pid: Int32
    var phase: RecordPhase
    var code: Int32
    var message: String
    var session: String
    var startedAt: String
    var updatedAt: String
    var segments: Int
    var preflight: [PreflightResult]
    var warnings: [RecordWarning]
    // ---- R2 選用欄位（spec §3.10）：nil 時省略鍵；舊版錄製器的狀態檔沒有這些鍵 ----
    var controlVersion: Int? = nil
    var recordingStartedAt: String? = nil
    var paused: Bool? = nil
    var micMuted: Bool? = nil
    var pausedSeconds: Double? = nil
    var pausedAt: String? = nil
    var markers: Int? = nil
    var recentLevels: RecentLevels? = nil
    // ---- R3（spec §3.17）：只在捨棄成功時寫 true，其餘 nil（省略鍵）----
    var discarded: Bool? = nil
}

/// spec §3.10：status 的 recentLevels。JSON 鍵恰為 3 個；system／mic 為 nil 時寫 null（不省略）。
struct RecentLevels: Codable, Equatable {
    var windowSeconds: Double
    var system: Double?
    var mic: Double?

    enum CodingKeys: String, CodingKey { case windowSeconds, system, mic }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(windowSeconds, forKey: .windowSeconds)
        try c.encode(system, forKey: .system)
        try c.encode(mic, forKey: .mic)
    }
}

struct SegmentRecord: Codable, Equatable {
    var file: String
    var requestedAt: Double
    var startedAt: Double?
    var finishedAt: Double?
    var width: Int
    var height: Int
    var audioDuration: Double?

    enum CodingKeys: String, CodingKey { case file, requestedAt, startedAt, finishedAt, width, height, audioDuration }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(file, forKey: .file)
        try c.encode(requestedAt, forKey: .requestedAt)
        try c.encode(startedAt, forKey: .startedAt)
        try c.encode(finishedAt, forKey: .finishedAt)
        try c.encode(width, forKey: .width)
        try c.encode(height, forKey: .height)
        try c.encode(audioDuration, forKey: .audioDuration)
    }
}

struct FrameStatusCounts: Codable, Equatable {
    var complete, idle, blank, suspended, started, stopped: Int
}

struct AudioLevels: Codable, Equatable {
    var windowSeconds: Double
    var system: [Double?]
    var mic: [Double?]
}

struct GapStats: Codable, Equatable {
    var boundaries: [Double]
    var max: Double
    var total: Double
    var wallClock: Double
    var pausedTotal: Double? = nil      // R2（spec §3.11）：finalize 寫；nil 時省略鍵
}

struct PixelSize: Codable, Equatable {
    var width: Int
    var height: Int
}

struct Manifest: Codable, Equatable {
    var schemaVersion: Int
    var segmentSeconds: Int
    var segments: [SegmentRecord]
    var frameStatus: FrameStatusCounts
    var blackIntervals: [BlackInterval]
    var levels: AudioLevels
    var gapStats: GapStats?
    var outputCanvas: PixelSize?
    var outputVideoBitrate: Int?

    enum CodingKeys: String, CodingKey {
        case schemaVersion, segmentSeconds, segments, frameStatus, blackIntervals, levels,
             gapStats, outputCanvas, outputVideoBitrate
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(schemaVersion, forKey: .schemaVersion)
        try c.encode(segmentSeconds, forKey: .segmentSeconds)
        try c.encode(segments, forKey: .segments)
        try c.encode(frameStatus, forKey: .frameStatus)
        try c.encode(blackIntervals, forKey: .blackIntervals)
        try c.encode(levels, forKey: .levels)
        try c.encode(gapStats, forKey: .gapStats)
        try c.encode(outputCanvas, forKey: .outputCanvas)
        try c.encode(outputVideoBitrate, forKey: .outputVideoBitrate)
    }
}

struct WindowInfo: Codable, Equatable {
    var windowID: UInt32
    var app: String
    var bundleID: String
    var title: String
}

struct StreamConfigSnapshot: Codable, Equatable {
    var filter: String
    var onScreenWindowsOnly: Bool
    var scalesToFit: Bool
    var minimumFrameInterval: String
    var capturesAudio: Bool
    var sampleRate: Int
    var channelCount: Int
    var captureMicrophone: Bool
    var microphoneCaptureDeviceID: String?
    var excludesCurrentProcessAudio: Bool
    var fileType: String
    var videoCodec: String
    var segmentSeconds: Int

    enum CodingKeys: String, CodingKey {
        case filter, onScreenWindowsOnly, scalesToFit, minimumFrameInterval, capturesAudio, sampleRate, channelCount,
             captureMicrophone, microphoneCaptureDeviceID, excludesCurrentProcessAudio, fileType, videoCodec, segmentSeconds
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(filter, forKey: .filter)
        try c.encode(onScreenWindowsOnly, forKey: .onScreenWindowsOnly)
        try c.encode(scalesToFit, forKey: .scalesToFit)
        try c.encode(minimumFrameInterval, forKey: .minimumFrameInterval)
        try c.encode(capturesAudio, forKey: .capturesAudio)
        try c.encode(sampleRate, forKey: .sampleRate)
        try c.encode(channelCount, forKey: .channelCount)
        try c.encode(captureMicrophone, forKey: .captureMicrophone)
        try c.encode(microphoneCaptureDeviceID, forKey: .microphoneCaptureDeviceID)
        try c.encode(excludesCurrentProcessAudio, forKey: .excludesCurrentProcessAudio)
        try c.encode(fileType, forKey: .fileType)
        try c.encode(videoCodec, forKey: .videoCodec)
        try c.encode(segmentSeconds, forKey: .segmentSeconds)
    }
}

struct AudioDeviceInfo: Codable, Equatable {
    var uid: String
    var name: String
    var transport: String
}

struct AudioDevices: Codable, Equatable {
    var input: AudioDeviceInfo?
    var output: AudioDeviceInfo?

    enum CodingKeys: String, CodingKey { case input, output }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(input, forKey: .input)
        try c.encode(output, forKey: .output)
    }
}

enum DeviceKind: String, Codable { case input, output }

struct DeviceEvent: Codable, Equatable {
    var t: Double
    var kind: DeviceKind
    var from: AudioDeviceInfo?
    var to: AudioDeviceInfo?

    enum CodingKeys: String, CodingKey { case t, kind, from, to }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(t, forKey: .t)
        try c.encode(kind, forKey: .kind)
        try c.encode(from, forKey: .from)
        try c.encode(to, forKey: .to)
    }
}

enum AudioSource: String, Codable { case system, mic }

struct AudioFormatEvent: Codable, Equatable {
    var t: Double
    var source: AudioSource
    var from: AudioFormat?
    var to: AudioFormat

    enum CodingKeys: String, CodingKey { case t, source, from, to }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(t, forKey: .t)
        try c.encode(source, forKey: .source)
        try c.encode(from, forKey: .from)
        try c.encode(to, forKey: .to)
    }
}

struct RecordMeta: Codable, Equatable {
    var schemaVersion: Int
    var window: WindowInfo
    var config: StreamConfigSnapshot
    var devices: AudioDevices
    var preflight: [PreflightResult]
    var deviceEvents: [DeviceEvent]
    var audioFormatEvents: [AudioFormatEvent]
    // ---- R2（spec §3.11）：R2 錄製實例開錄時寫空陣列；nil 時省略鍵（舊場次沒有這兩鍵）----
    var pauseEvents: [PauseEvent]? = nil
    var micMuteEvents: [MicMuteEvent]? = nil
    // ---- R3（spec §3.17）：開錄時一筆 t=0，之後每筆輸出裝置 deviceEvents 一筆；nil 時省略鍵 ----
    var outputLatencies: [OutputLatency]? = nil
}

/// t6 第二輪（缺陷 D，§4.4.9）：錄製結束時寫進 record.status.json 與 record.log 的最終結果。
struct CompletionOutcome: Equatable {
    let phase: RecordPhase
    let code: Int32
    let message: String
}

/// finalizeCode != 0 → (.failed, 5, 前綴 + "收尾失敗（_record_finalize.py 回 <rc>），段落保留：可執行 meeting record finish <sessionPath>")；
///   前綴＝forcedMessage 非 nil 時為 forcedMessage + "；"，否則為 ""（停止原因不得被收尾失敗蓋掉）。
/// 否則 forcedMessage 非 nil → (.done, forcedCode ?? 5, forcedMessage)；
/// 否則 hadError → (.done, 5, "錄製中出過錯（見 record.log），已收尾；段落保留")；
/// 否則 → (.done, 0, "已完成：<sessionPath>")。
func completionOutcome(finalizeCode: Int32, forcedCode: Int32?, forcedMessage: String?, hadError: Bool,
                       sessionPath: String) -> CompletionOutcome {
    if finalizeCode != 0 {
        let prefix = forcedMessage.map { $0 + "；" } ?? ""
        return CompletionOutcome(phase: .failed, code: 5,
                                 message: prefix + "收尾失敗（_record_finalize.py 回 \(finalizeCode)），段落保留：可執行 meeting record finish \(sessionPath)")
    }
    if let forcedMessage {
        return CompletionOutcome(phase: .done, code: forcedCode ?? 5, message: forcedMessage)
    }
    if hadError {
        return CompletionOutcome(phase: .done, code: 5, message: "錄製中出過錯（見 record.log），已收尾；段落保留")
    }
    return CompletionOutcome(phase: .done, code: 0, message: "已完成：\(sessionPath)")
}

/// 同目錄 tmp 檔＋rename；鍵排序（.sortedKeys）；Optional 為 nil 時寫 null。
func writeJSONAtomically<T: Encodable>(_ value: T, to url: URL) throws {
    let enc = JSONEncoder()
    enc.outputFormatting = [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes]
    let data = try enc.encode(value)
    let dir = url.deletingLastPathComponent()
    try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let tmp = dir.appendingPathComponent(".\(url.lastPathComponent).\(UUID().uuidString).tmp")
    do {
        try data.write(to: tmp)
        guard rename(tmp.path, url.path) == 0 else {
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno),
                          userInfo: [NSLocalizedDescriptionKey: "rename 失敗：\(String(cString: strerror(errno)))"])
        }
    } catch {
        try? FileManager.default.removeItem(at: tmp)
        throw error
    }
}

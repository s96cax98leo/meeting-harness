// Capture/SegmentWriter.swift —— 一個段落一個 AVAssetWriter（D20；design §7.2；spec §4.4.1、§4.4.5）
//
// 三個 input、順序固定：0 影片（H.264）、1 系統聲音（AAC 2 聲道）、2 麥克風（AAC 1 聲道）。
// 執行緒：呼叫端（RecordingSession）只在自己的序列佇列上呼叫本類別；finishWriting 的完成回呼
// 在 AVFoundation 的佇列，由呼叫端自行轉回序列佇列。
import AVFoundation
import CoreMedia
import Foundation

/// 段落檔裡的軌道（＝input 的索引，順序固定）。
enum SegmentTrack: Int, CaseIterable { case video = 0, system = 1, mic = 2 }

final class SegmentWriter {
    enum AppendResult { case ok, dropped, failed }

    let index: Int
    let file: String
    let url: URL
    /// 段落起點 B_i（sample 時鐘；startSession(atSourceTime:) 的值）。
    let start: CMTime
    let size: PixelSize
    /// 由「writer 失敗而提前換段」開出的段落：開段的 host clock 秒數（10 秒內再失敗就停止）。
    let replacementOpenedAt: Double?

    private let writer: AVAssetWriter
    private let inputs: [AVAssetWriterInput]
    private(set) var lastVideoPTS: CMTime = .invalid
    /// 各 input 因 isReadyForMoreMediaData == false 丟掉的 sample 數。
    private(set) var droppedNotReady = [0, 0, 0]
    /// 視訊 PTS 不是嚴格遞增（或早於段落起點）而丟掉的 sample 數。
    private(set) var droppedNonMonotonic = 0
    private(set) var appended = [0, 0, 0]
    /// 換段後：各 input 是否已看到屬於下一段的 sample（三個都看到就可以收尾，design §7.2 第 5 步）。
    var sawPast: Set<SegmentTrack> = []
    var failureReported = false
    private(set) var finishing = false

    var hasFailed: Bool { writer.status == .failed }
    var error: Error? { writer.error }
    var appendedTotal: Int { appended.reduce(0, +) }

    init(directory: URL, index: Int, start: CMTime, size: PixelSize, replacementOpenedAt: Double?) throws {
        self.index = index
        self.file = segmentFileName(index: index)
        self.url = directory.appendingPathComponent(file)
        self.start = start
        self.size = size
        self.replacementOpenedAt = replacementOpenedAt

        let w = try AVAssetWriter(outputURL: url, fileType: .mov)
        w.movieFragmentInterval = CMTime(seconds: 10, preferredTimescale: 600)
        w.overallDurationHint = CMTime(seconds: Double(segmentSeconds), preferredTimescale: 600)
        w.shouldOptimizeForNetworkUse = false

        let video = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: size.width,
            AVVideoHeightKey: size.height,
            // updateConfiguration 生效前的舊尺寸幀等比縮進新畫布、留黑邊、不裁切（design §7.1）
            AVVideoScalingModeKey: AVVideoScalingModeResizeAspect,
            AVVideoCompressionPropertiesKey: [
                AVVideoProfileLevelKey: AVVideoProfileLevelH264HighAutoLevel,
                AVVideoAverageBitRateKey: segmentVideoBitRate(width: size.width, height: size.height),
                AVVideoExpectedSourceFrameRateKey: 60,
                AVVideoMaxKeyFrameIntervalDurationKey: 2,
                // 不開 B-frame：dts 與 pts 一致、單調遞增（design §7.2）
                AVVideoAllowFrameReorderingKey: false,
            ] as [String: Any],
        ])
        let system = AVAssetWriterInput(mediaType: .audio, outputSettings: SegmentWriter.aacSettings(channels: 2, bitRate: 192_000))
        let mic = AVAssetWriterInput(mediaType: .audio, outputSettings: SegmentWriter.aacSettings(channels: 1, bitRate: 128_000))
        let all = [video, system, mic]
        for input in all {
            input.expectsMediaDataInRealTime = true
            guard w.canAdd(input) else {
                throw NSError(domain: "MeetingRecorder", code: 1,
                              userInfo: [NSLocalizedDescriptionKey: "AVAssetWriter 不接受 \(input.mediaType.rawValue) input"])
            }
            w.add(input)
        }
        writer = w
        inputs = all
    }

    private static func aacSettings(channels: Int, bitRate: Int) -> [String: Any] {
        var layout = AudioChannelLayout()
        layout.mChannelLayoutTag = channels == 1 ? kAudioChannelLayoutTag_Mono : kAudioChannelLayoutTag_Stereo
        return [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: 48_000,
            AVNumberOfChannelsKey: channels,
            AVEncoderBitRateKey: bitRate,
            AVChannelLayoutKey: Data(bytes: &layout, count: MemoryLayout<AudioChannelLayout>.size),
        ]
    }

    /// startWriting＋startSession(atSourceTime: B_i)。失敗回 false（呼叫端當成 writer 失敗）。
    func begin() -> Bool {
        guard writer.startWriting() else { return false }
        writer.startSession(atSourceTime: start)
        return true
    }

    /// 未 ready 就丟並計數、不阻塞；視訊 PTS 必須嚴格遞增。append 回 false 且 writer 進 failed → .failed。
    func append(_ sb: CMSampleBuffer, to track: SegmentTrack) -> AppendResult {
        guard !finishing else { return .dropped }
        switch writer.status {
        case .writing: break
        case .failed: return .failed
        default: return .dropped
        }
        let i = track.rawValue
        if track == .video {
            let pts = CMSampleBufferGetPresentationTimeStamp(sb)
            // 早於段落起點的幀也不寫（第一段的起點可能來自先到的音訊）
            if CMTimeCompare(pts, start) < 0 || (lastVideoPTS.isValid && CMTimeCompare(pts, lastVideoPTS) <= 0) {
                droppedNonMonotonic += 1
                return .dropped
            }
        }
        guard inputs[i].isReadyForMoreMediaData else {
            droppedNotReady[i] += 1
            return .dropped
        }
        guard inputs[i].append(sb) else {
            return writer.status == .failed ? .failed : .dropped
        }
        appended[i] += 1
        if track == .video { lastVideoPTS = CMSampleBufferGetPresentationTimeStamp(sb) }
        return .ok
    }

    /// endSession(atSourceTime: end) → 三個 input markAsFinished() → finishWriting。
    /// completion(true) ＝ status == .completed；其他（含 writer 早已失敗）為 false。
    func finish(at end: CMTime, completion: @escaping (Bool, Error?) -> Void) {
        guard !finishing else { return }
        finishing = true
        guard writer.status == .writing else {
            completion(false, writer.error)
            return
        }
        writer.endSession(atSourceTime: end)
        for input in inputs { input.markAsFinished() }
        writer.finishWriting { [writer] in
            completion(writer.status == .completed, writer.error)
        }
    }

    /// 段落沒有任何內容（停止點不晚於段落起點）時捨棄；cancelWriting 會刪掉部分寫入的檔。
    func cancel() {
        guard !finishing else { return }
        finishing = true
        if writer.status == .writing { writer.cancelWriting() }
    }

    /// 影片因 writer 未 ready 丟掉的幀數（狀態檔 droppedFrames 的每段增量；meeting-speed spec §3.1）
    var droppedVideoFrames: Int { droppedNotReady[SegmentTrack.video.rawValue] }

    /// 丟棄數的 log 文字。
    var dropSummary: String {
        "未 ready 丟棄 影片 \(droppedNotReady[0])／系統聲音 \(droppedNotReady[1])／麥克風 \(droppedNotReady[2])，"
            + "影片 PTS 非遞增丟棄 \(droppedNonMonotonic)"
    }
}

/// 以新的 PTS 複製一個視訊 sample（換段時把最後一個 complete 幀重新打戳到新段起點，design §7.2 第 3 步）。
func retimedVideoSample(_ sb: CMSampleBuffer, pts: CMTime) -> CMSampleBuffer? {
    var timing = CMSampleTimingInfo(duration: .invalid, presentationTimeStamp: pts, decodeTimeStamp: .invalid)
    var out: CMSampleBuffer?
    let rc = CMSampleBufferCreateCopyWithNewTiming(allocator: kCFAllocatorDefault, sampleBuffer: sb,
                                                   sampleTimingEntryCount: 1, sampleTimingArray: &timing,
                                                   sampleBufferOut: &out)
    return rc == noErr ? out : nil
}

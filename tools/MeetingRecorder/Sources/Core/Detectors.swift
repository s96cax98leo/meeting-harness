// Core/Detectors.swift —— 錄製中監看的判斷（spec §3.4、§4.5.1–4.5.3、§4.5.8）
// 純邏輯：只吃數字與位元組。CVPixelBuffer 的鎖定與取 plane 0 留在 Capture/。
import Foundation

/// 連續 seconds 秒 < thresholdDBFS 時告警一次；dbfs ≥ 門檻即重置。-∞ 算靜音。
struct SilenceDetector {
    private let threshold: Double
    private let seconds: Double
    private var runStart: Double?
    private var fired = false

    init(thresholdDBFS: Double, seconds: Double) {
        self.threshold = thresholdDBFS
        self.seconds = seconds
    }

    mutating func feed(t: Double, dbfs: Double) -> Bool {
        if dbfs >= threshold {
            runStart = nil
            fired = false
            return false
        }
        let start = runStart ?? t
        runStart = start
        if !fired && t - start >= seconds - 1e-9 {
            fired = true
            return true
        }
        return false
    }
}

struct BlackInterval: Codable, Equatable {
    var start: Double
    var end: Double?    // nil＝尚未恢復

    enum CodingKeys: String, CodingKey { case start, end }
    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(start, forKey: .start)
        try c.encode(end, forKey: .end)       // nil 寫 null，不省略鍵
    }
}

/// 非黑比例連續 seconds 秒 < ratio 時開一個區間；恢復的第一個樣本關閉。
struct BlackDetector {
    private let ratio: Double
    private let seconds: Double
    private var runStart: Double?
    private var open = false
    private(set) var intervals: [BlackInterval] = []

    init(ratio: Double, seconds: Double) {
        self.ratio = ratio
        self.seconds = seconds
    }

    mutating func feed(t: Double, nonBlackRatio: Double) -> Bool {
        if nonBlackRatio < ratio {
            let start = runStart ?? t
            runStart = start
            if !open && t - start >= seconds - 1e-9 {
                open = true
                intervals.append(BlackInterval(start: start, end: nil))
                return true
            }
            return false
        }
        if open, !intervals.isEmpty { intervals[intervals.count - 1].end = t }
        open = false
        runStart = nil
        return false
    }
}

enum FrameStatusKind: String, Codable { case complete, idle, blank, suspended, started, stopped }

/// 連續 seconds 秒只收到 suspended 時回一次 true；收到其他狀態即重置。
struct SuspendedDetector {
    private let seconds: Double
    private var runStart: Double?
    private var fired = false

    init(seconds: Double) { self.seconds = seconds }

    mutating func feed(t: Double, status: FrameStatusKind) -> Bool {
        guard status == .suspended else {
            runStart = nil
            fired = false
            return false
        }
        let start = runStart ?? t
        runStart = start
        if !fired && t - start >= seconds - 1e-9 {
            fired = true
            return true
        }
        return false
    }
}

/// 8×8 格點中心共 64 點、亮度 > 24 的比例（video range 的黑約 16）；寬或高 ≤ 16 回 nil。
/// 以 bytesPerRow 定址，行尾填充不計入。
func nonBlackRatio(lumaPlane: UnsafeBufferPointer<UInt8>, width: Int, height: Int, bytesPerRow: Int) -> Double? {
    guard width > 16, height > 16 else { return nil }
    let grid = 8
    var nonBlack = 0
    for gy in 0..<grid {
        for gx in 0..<grid {
            let x = width * (2 * gx + 1) / (2 * grid)
            let y = height * (2 * gy + 1) / (2 * grid)
            let i = y * bytesPerRow + x
            guard i < lumaPlane.count else { continue }
            if lumaPlane[i] > 24 { nonBlack += 1 }
        }
    }
    return Double(nonBlack) / Double(grid * grid)
}

// ===== R2 增補（spec §3.14、§4.17.4、§4.18.10）=====

extension SilenceDetector {
    /// 之後的行為與 init(同參數) 的新實例完全相同（取消靜音、繼續錄製時呼叫）。
    mutating func reset() {
        runStart = nil
        fired = false
    }
}

extension SuspendedDetector {
    /// 同 SilenceDetector.reset()。
    mutating func reset() {
        runStart = nil
        fired = false
    }
}

extension BlackDetector {
    /// 暫停時呼叫：開啟中的區間（end 為 nil）在 t 關閉；連續計數歸零（之後的開區間判斷與新實例相同）；
    /// 已記錄的區間保留。
    mutating func interrupt(at t: Double) {
        if let last = intervals.last, last.end == nil { intervals[intervals.count - 1].end = t }
        open = false
        runStart = nil
    }
}

/// 各偵測器這一刻要不要餵（spec §4.18.10）：暫停中四項都不餵；麥克風靜音只停 micSilence。
struct DetectorFeed: Equatable {
    let systemSilence: Bool
    let micSilence: Bool
    let black: Bool
    let suspended: Bool
}

func detectorFeed(paused: Bool, micMuted: Bool) -> DetectorFeed {
    if paused { return DetectorFeed(systemSilence: false, micSilence: false, black: false, suspended: false) }
    return DetectorFeed(systemSilence: true, micSilence: !micMuted, black: true, suspended: true)
}

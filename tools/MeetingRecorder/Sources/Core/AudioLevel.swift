// Core/AudioLevel.swift —— 音量計算（spec §3.4、§4.2.5、§4.2.7、§4.5.7、§4.5.8）
//
// 純邏輯：只讀 CMSampleBuffer 的位元組，不碰任何擷取 API，可與 Tests/ 一起編譯。
// 原則（design §7.5）：不假設格式固定，每個緩衝依它自己的 ASBD 取樣；
// 時段以呈現時間（PTS 秒）切，不以樣本數切，所以取樣率中途改變不影響時段邊界。
import AudioToolbox
import CoreMedia
import Foundation

enum SampleType: String, Codable { case float32, int16 }

struct AudioFormat: Equatable, Codable {
    let sampleRate: Double
    let channels: Int
    let interleaved: Bool
    let sampleType: SampleType
}

/// 讀 ASBD；非 Linear PCM 或不支援的樣本型別（例如 Float64、Int32）回 nil。
func audioFormat(of sampleBuffer: CMSampleBuffer) -> AudioFormat? {
    guard let fd = CMSampleBufferGetFormatDescription(sampleBuffer),
          let p = CMAudioFormatDescriptionGetStreamBasicDescription(fd) else { return nil }
    let asbd = p.pointee
    guard asbd.mFormatID == kAudioFormatLinearPCM else { return nil }
    let isFloat = asbd.mFormatFlags & kAudioFormatFlagIsFloat != 0
    let isSigned = asbd.mFormatFlags & kAudioFormatFlagIsSignedInteger != 0
    let type: SampleType
    if isFloat && asbd.mBitsPerChannel == 32 {
        type = .float32
    } else if !isFloat && isSigned && asbd.mBitsPerChannel == 16 {
        type = .int16
    } else {
        return nil
    }
    let interleaved = asbd.mFormatFlags & kAudioFormatFlagIsNonInterleaved == 0
    return AudioFormat(sampleRate: asbd.mSampleRate, channels: Int(asbd.mChannelsPerFrame),
                       interleaved: interleaved, sampleType: type)
}

/// 均方值轉 dBFS；均方為 0 回 -∞。
private func dbfs(meanSquare: Double) -> Double {
    meanSquare > 0 ? 10 * log10(meanSquare) : -Double.infinity
}

/// 空陣列或全零回 -∞。
func rmsDBFS(samples: [Float]) -> Double {
    guard !samples.isEmpty else { return -Double.infinity }
    var sum = 0.0
    for s in samples { sum += Double(s) * Double(s) }
    return dbfs(meanSquare: sum / Double(samples.count))
}

/// 依該緩衝自己的格式，對全部聲道與 frame 算均方根。
/// 一律經 withAudioBufferList 取緩衝：用 MemoryLayout<AudioBufferList>.size 自己配置時，
/// 雙聲道非交錯會因空間不足靜默失敗、看起來像 -∞（d2:34-39）。不支援的格式回 nil，不當成 -∞。
func rmsDBFS(sampleBuffer: CMSampleBuffer) -> Double? {
    guard let fmt = audioFormat(of: sampleBuffer) else { return nil }
    do {
        return try sampleBuffer.withAudioBufferList { abl, _ -> Double? in
            var sum = 0.0
            var count = 0
            for buf in abl {
                guard let data = buf.mData else { continue }
                switch fmt.sampleType {
                case .float32:
                    let n = Int(buf.mDataByteSize) / MemoryLayout<Float32>.size
                    let p = data.assumingMemoryBound(to: Float32.self)
                    for i in 0..<n { let v = Double(p[i]); sum += v * v }
                    count += n
                case .int16:
                    let n = Int(buf.mDataByteSize) / MemoryLayout<Int16>.size
                    let p = data.assumingMemoryBound(to: Int16.self)
                    for i in 0..<n { let v = Double(p[i]) / 32768.0; sum += v * v }
                    count += n
                }
            }
            guard count > 0 else { return -Double.infinity }
            return dbfs(meanSquare: sum / Double(count))
        }
    } catch {
        return nil
    }
}

/// 以 t（PTS 秒）把 dBFS 收斂成固定長度時段的峰值。時段 k ＝ [k·w, (k+1)·w)，從 0 起算。
struct PeakWindow {
    private let windowSeconds: Double
    private var nextIndex = 0              // 第一個尚未收斂的時段
    private var peaks: [Int: Double] = [:]
    private(set) var maxDBFS: Double = -Double.infinity

    init(windowSeconds: Double) {
        self.windowSeconds = windowSeconds
    }

    mutating func feed(t: Double, dbfs: Double) {
        let k = Int(floor(t / windowSeconds + 1e-9))
        if dbfs > maxDBFS { maxDBFS = dbfs }
        guard k >= nextIndex else { return }    // 該時段已收斂，晚到的值不再改寫
        peaks[k] = max(peaks[k] ?? -Double.infinity, dbfs)
    }

    /// 回傳結束時間 ≤ t 的各時段峰值（依時間順序）；沒收到任何 feed 的時段為 -∞，不得略過。
    mutating func close(upTo t: Double) -> [Double] {
        var out: [Double] = []
        while Double(nextIndex + 1) * windowSeconds <= t + 1e-9 {
            out.append(peaks.removeValue(forKey: nextIndex) ?? -Double.infinity)
            nextIndex += 1
        }
        return out
    }
}

// ===== R2 增補（spec §3.14、§4.17.1）=====

/// 麥克風靜音：深拷貝資料緩衝並全部清 0；frame 數、PTS、duration、format description 與原緩衝相同；
/// 不改原緩衝。拿不到資料緩衝（或不是可展開成 AudioBufferList 的音訊）→ nil。
func zeroedAudioSample(_ sb: CMSampleBuffer) -> CMSampleBuffer? {
    guard CMSampleBufferGetDataBuffer(sb) != nil, let fmt = CMSampleBufferGetFormatDescription(sb) else { return nil }

    // 原緩衝各個 AudioBuffer 的聲道數與位元組數（只讀，不碰資料）
    let layout: [(channels: UInt32, bytes: UInt32)]
    do {
        layout = try sb.withAudioBufferList { abl, _ in abl.map { ($0.mNumberChannels, $0.mDataByteSize) } }
    } catch {
        return nil
    }
    guard !layout.isEmpty else { return nil }

    // 時間資訊原樣帶過去
    var timingCount: CMItemCount = 0
    guard CMSampleBufferGetSampleTimingInfoArray(sb, entryCount: 0, arrayToFill: nil,
                                                 entriesNeededOut: &timingCount) == noErr else { return nil }
    var timing = [CMSampleTimingInfo](repeating: CMSampleTimingInfo(), count: Int(timingCount))
    if timingCount > 0 {
        guard CMSampleBufferGetSampleTimingInfoArray(sb, entryCount: timingCount, arrayToFill: &timing,
                                                     entriesNeededOut: &timingCount) == noErr else { return nil }
    }
    var sizeCount: CMItemCount = 0
    if CMSampleBufferGetSampleSizeArray(sb, entryCount: 0, arrayToFill: nil, entriesNeededOut: &sizeCount) != noErr {
        sizeCount = 0
    }
    var sizes = [Int](repeating: 0, count: Int(sizeCount))
    if sizeCount > 0 {
        guard CMSampleBufferGetSampleSizeArray(sb, entryCount: sizeCount, arrayToFill: &sizes,
                                               entriesNeededOut: &sizeCount) == noErr else { return nil }
    }

    var out: CMSampleBuffer?
    let created = timing.withUnsafeBufferPointer { tp in
        sizes.withUnsafeBufferPointer { sp in
            CMSampleBufferCreate(allocator: kCFAllocatorDefault, dataBuffer: nil, dataReady: false,
                                 makeDataReadyCallback: nil, refcon: nil, formatDescription: fmt,
                                 sampleCount: CMSampleBufferGetNumSamples(sb),
                                 sampleTimingEntryCount: timingCount, sampleTimingArray: tp.baseAddress,
                                 sampleSizeEntryCount: sizeCount, sampleSizeArray: sp.baseAddress,
                                 sampleBufferOut: &out)
        }
    }
    guard created == noErr, let out else { return nil }

    // 全 0 的 AudioBufferList（calloc），由 CoreMedia 複製進新的 block buffer
    let abl = AudioBufferList.allocate(maximumBuffers: layout.count)
    defer {
        for b in abl { free(b.mData) }
        free(abl.unsafeMutablePointer)
    }
    for (i, l) in layout.enumerated() {
        guard let mem = calloc(max(Int(l.bytes), 1), 1) else { return nil }
        abl[i] = AudioBuffer(mNumberChannels: l.channels, mDataByteSize: l.bytes, mData: mem)
    }
    guard CMSampleBufferSetDataBufferFromAudioBufferList(out, blockBufferAllocator: kCFAllocatorDefault,
                                                         blockBufferMemoryAllocator: kCFAllocatorDefault,
                                                         flags: 0, bufferList: abl.unsafePointer) == noErr
    else { return nil }
    return out
}

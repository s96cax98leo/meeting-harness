// spec §4.2.5、§4.2.7、§4.5.7、§4.5.8：AudioLevel.swift（AudioFormat、rmsDBFS、PeakWindow）。
// 三種 CMSampleBuffer 都在測試裡自建，不碰任何擷取 API：
//   48 kHz 雙聲道非交錯 Float32、16 kHz 單聲道 Int16、24 kHz 雙聲道交錯 Float32。
// 「interleaved」依 ASBD 判讀：mFormatFlags 含 kAudioFormatFlagIsNonInterleaved 即為 false。
import Foundation
import CoreMedia
import AudioToolbox

let mrtAudioLevelTests: [MRTCase] = [
    ("testFormatsAcrossSampleRates", testFormatsAcrossSampleRates),
    ("testNonInterleavedStereoBuffer", testNonInterleavedStereoBuffer),
    ("testPeakWindowJudgement", testPeakWindowJudgement),
    ("testPeakWindowEmptyWindowIsNegInf", testPeakWindowEmptyWindowIsNegInf),
    ("testPeakWindowIgnoresSampleRateChange", testPeakWindowIgnoresSampleRateChange),
]

enum MRTSampleKind { case float32, int16, float64 }

/// 自建 PCM CMSampleBuffer。value(frame, channel) 回傳 -1…1 的樣本值（Int16 乘 32767 後取整）。
func mrtMakeAudioBuffer(sampleRate: Double, channels: Int, interleaved: Bool, kind: MRTSampleKind,
                        frames: Int, value: (Int, Int) -> Double) -> CMSampleBuffer? {
    let bytesPerSample: Int
    var flags: AudioFormatFlags = kAudioFormatFlagIsPacked
    switch kind {
    case .float32: bytesPerSample = 4; flags |= kAudioFormatFlagIsFloat
    case .float64: bytesPerSample = 8; flags |= kAudioFormatFlagIsFloat
    case .int16: bytesPerSample = 2; flags |= kAudioFormatFlagIsSignedInteger
    }
    if !interleaved { flags |= kAudioFormatFlagIsNonInterleaved }
    let bytesPerFrame = interleaved ? bytesPerSample * channels : bytesPerSample
    var asbd = AudioStreamBasicDescription(
        mSampleRate: sampleRate, mFormatID: kAudioFormatLinearPCM, mFormatFlags: flags,
        mBytesPerPacket: UInt32(bytesPerFrame), mFramesPerPacket: 1, mBytesPerFrame: UInt32(bytesPerFrame),
        mChannelsPerFrame: UInt32(channels), mBitsPerChannel: UInt32(bytesPerSample * 8), mReserved: 0)

    var fmt: CMAudioFormatDescription?
    guard CMAudioFormatDescriptionCreate(allocator: kCFAllocatorDefault, asbd: &asbd, layoutSize: 0, layout: nil,
                                         magicCookieSize: 0, magicCookie: nil, extensions: nil,
                                         formatDescriptionOut: &fmt) == noErr, let fmt else { return nil }

    var timing = CMSampleTimingInfo(duration: CMTime(value: 1, timescale: CMTimeScale(sampleRate)),
                                    presentationTimeStamp: .zero, decodeTimeStamp: .invalid)
    var sb: CMSampleBuffer?
    guard CMSampleBufferCreate(allocator: kCFAllocatorDefault, dataBuffer: nil, dataReady: false,
                               makeDataReadyCallback: nil, refcon: nil, formatDescription: fmt,
                               sampleCount: frames, sampleTimingEntryCount: 1, sampleTimingArray: &timing,
                               sampleSizeEntryCount: 0, sampleSizeArray: nil, sampleBufferOut: &sb) == noErr,
          let sb else { return nil }

    let bufferCount = interleaved ? 1 : channels
    let channelsPerBuffer = interleaved ? channels : 1
    let bytesPerBuffer = frames * bytesPerSample * channelsPerBuffer
    let abl = AudioBufferList.allocate(maximumBuffers: bufferCount)
    defer {
        for b in abl { free(b.mData) }
        free(abl.unsafeMutablePointer)
    }
    for i in 0..<bufferCount {
        let mem = malloc(bytesPerBuffer)!
        for f in 0..<frames {
            for c in 0..<channelsPerBuffer {
                let ch = interleaved ? c : i
                let v = value(f, ch)
                let idx = f * channelsPerBuffer + c
                switch kind {
                case .float32: mem.assumingMemoryBound(to: Float32.self)[idx] = Float32(v)
                case .float64: mem.assumingMemoryBound(to: Float64.self)[idx] = v
                case .int16: mem.assumingMemoryBound(to: Int16.self)[idx] = Int16((v * 32767).rounded())
                }
            }
        }
        abl[i] = AudioBuffer(mNumberChannels: UInt32(channelsPerBuffer), mDataByteSize: UInt32(bytesPerBuffer), mData: mem)
    }
    guard CMSampleBufferSetDataBufferFromAudioBufferList(sb, blockBufferAllocator: kCFAllocatorDefault,
                                                         blockBufferMemoryAllocator: kCFAllocatorDefault,
                                                         flags: 0, bufferList: abl.unsafePointer) == noErr
    else { return nil }
    return sb
}

/// 20·log10(RMS)。
func mrtDB(_ rms: Double) -> Double { 20 * log10(rms) }

// §4.5.8：16 kHz 單聲道 Int16、24 kHz 雙聲道交錯 Float32、48 kHz 雙聲道非交錯 Float32
// 三種緩衝的 audioFormat(of:) 與 rmsDBFS(sampleBuffer:) 都應回正確值。
func testFormatsAcrossSampleRates() throws {
    // rmsDBFS(samples:)：空陣列或全零為 -∞；常數 0.5 為 -6.02 dBFS
    mrtEqual(rmsDBFS(samples: []), -Double.infinity, "空陣列")
    mrtEqual(rmsDBFS(samples: [0, 0, 0, 0]), -Double.infinity, "全零")
    mrtNear(rmsDBFS(samples: [0.5, -0.5, 0.5, -0.5]), mrtDB(0.5))

    // 左聲道 0.5、右聲道 0.25：均方 = (0.25 + 0.0625) / 2 = 0.15625 → -8.06 dBFS
    // （只算第一聲道會得到 -6.02，只算第二聲道會得到 -12.04，都分得出來）
    let stereoExpected = mrtDB(sqrt(0.15625))
    let lr: (Int, Int) -> Double = { f, ch in (ch == 0 ? 0.5 : 0.25) * (f % 2 == 0 ? 1 : -1) }

    // (1) 48 kHz 雙聲道非交錯 Float32
    guard let b48 = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32,
                                        frames: 480, value: lr) else {
        mrtExpect(false, "無法建立 48 kHz 非交錯 Float32 緩衝"); return
    }
    mrtEqual(audioFormat(of: b48), AudioFormat(sampleRate: 48000, channels: 2, interleaved: false, sampleType: .float32))
    mrtNear(rmsDBFS(sampleBuffer: b48), stereoExpected, "48 kHz 雙聲道非交錯 Float32")

    // (2) 16 kHz 單聲道 Int16（常數幅度 0.5 → -6.02 dBFS；以 32767 或 32768 正規化都在容許內）
    guard let b16 = mrtMakeAudioBuffer(sampleRate: 16000, channels: 1, interleaved: false, kind: .int16,
                                        frames: 160, value: { f, _ in f % 2 == 0 ? 0.5 : -0.5 }) else {
        mrtExpect(false, "無法建立 16 kHz Int16 緩衝"); return
    }
    mrtEqual(audioFormat(of: b16), AudioFormat(sampleRate: 16000, channels: 1, interleaved: false, sampleType: .int16))
    mrtNear(rmsDBFS(sampleBuffer: b16), mrtDB(0.5), "16 kHz 單聲道 Int16")

    // (3) 24 kHz 雙聲道交錯 Float32
    guard let b24 = mrtMakeAudioBuffer(sampleRate: 24000, channels: 2, interleaved: true, kind: .float32,
                                        frames: 240, value: lr) else {
        mrtExpect(false, "無法建立 24 kHz 交錯 Float32 緩衝"); return
    }
    mrtEqual(audioFormat(of: b24), AudioFormat(sampleRate: 24000, channels: 2, interleaved: true, sampleType: .float32))
    mrtNear(rmsDBFS(sampleBuffer: b24), stereoExpected, "24 kHz 雙聲道交錯 Float32")

    // 不支援的樣本型別（Float64）：兩者都回 nil
    guard let b64 = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float64,
                                        frames: 64, value: lr) else {
        mrtExpect(false, "無法建立 Float64 緩衝"); return
    }
    mrtExpect(audioFormat(of: b64) == nil, "Float64 應回 nil")
    mrtExpect(rmsDBFS(sampleBuffer: b64) == nil, "Float64 應回 nil")

    // 靜音緩衝為 -∞（不是 nil）
    if let silent = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32,
                                       frames: 480, value: { _, _ in 0 }) {
        mrtEqual(rmsDBFS(sampleBuffer: silent), -Double.infinity, "全零緩衝")
    } else {
        mrtExpect(false, "無法建立靜音緩衝")
    }
}

// §4.2.7：雙聲道非交錯 Float32 不得因 AudioBufferList 配置不足而回 -∞（d2:34-39）。
func testNonInterleavedStereoBuffer() throws {
    guard let both = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32,
                                         frames: 1024, value: { f, _ in f % 2 == 0 ? 0.5 : -0.5 }) else {
        mrtExpect(false, "無法建立緩衝"); return
    }
    let v = rmsDBFS(sampleBuffer: both)
    mrtExpect(v != nil, "雙聲道非交錯 Float32 不應回 nil")
    mrtExpect(v != -Double.infinity, "雙聲道非交錯 Float32 不應回 -∞")
    mrtNear(v, mrtDB(0.5), "兩聲道皆 0.5")

    // 只有第二聲道有聲音：仍要量得到（均方 0.125 → -9.03 dBFS）
    guard let right = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32,
                                          frames: 1024, value: { f, ch in ch == 1 ? (f % 2 == 0 ? 0.5 : -0.5) : 0 }) else {
        mrtExpect(false, "無法建立緩衝"); return
    }
    mrtNear(rmsDBFS(sampleBuffer: right), mrtDB(sqrt(0.125)), "只有右聲道")
}

// §4.2.5：判定為「任一 0.5 秒時段峰值 > -60 dBFS」，PeakWindow(windowSeconds: 0.5) 收斂後取最大值。
func testPeakWindowJudgement() throws {
    // 3 秒 probe：底噪 -70，只有 1.3 秒附近一個 -40 的測試音
    var pw = PeakWindow(windowSeconds: 0.5)
    var t = 0.05
    while t < 3.0 {
        pw.feed(t: t, dbfs: abs(t - 1.3) < 0.06 ? -40 : -70)
        t += 0.1
    }
    let peaks = pw.close(upTo: 3.0)
    mrtEqual(peaks.count, 6, "3 秒應收斂成 6 個 0.5 秒時段")
    mrtEqual(peaks.max() ?? -Double.infinity, -40)
    mrtExpect((peaks.max() ?? -Double.infinity) > -60, "有測試音時應判定通過")
    mrtEqual(pw.maxDBFS, -40)
    mrtNear(peaks.count > 2 ? peaks[2] : nil, -40, "1.3 秒落在第 3 個時段 [1.0, 1.5)")

    // 同一時段取峰值（最大者），不是平均
    var same = PeakWindow(windowSeconds: 0.5)
    same.feed(t: 0.1, dbfs: -50)
    same.feed(t: 0.2, dbfs: -30)
    same.feed(t: 0.3, dbfs: -45)
    mrtEqual(same.close(upTo: 0.5), [-30])

    // 全程 -70：任一時段都不超過 -60 → 判定失敗
    var quiet = PeakWindow(windowSeconds: 0.5)
    t = 0.05
    while t < 3.0 { quiet.feed(t: t, dbfs: -70); t += 0.1 }
    let qp = quiet.close(upTo: 3.0)
    mrtEqual(qp.count, 6)
    mrtExpect(!qp.contains { $0 > -60 }, "全程 -70 不得判定通過")
    mrtEqual(quiet.maxDBFS, -70)

    // 未 feed 過時 maxDBFS 為 -∞
    let fresh = PeakWindow(windowSeconds: 0.5)
    mrtEqual(fresh.maxDBFS, -Double.infinity)
}

// §4.5.7：沒有收到任何緩衝的時段應記為 -∞，不得被略過；已收斂的時段不重複回傳。
func testPeakWindowEmptyWindowIsNegInf() throws {
    var pw = PeakWindow(windowSeconds: 0.5)
    pw.feed(t: 0.1, dbfs: -20)
    // [0.5, 1.0) 沒有任何 feed（例如 HFP 重新協商、緩衝中斷）
    pw.feed(t: 1.2, dbfs: -30)
    mrtEqual(pw.close(upTo: 1.5), [-20, -Double.infinity, -30])

    // 之後完全沒有緩衝：每個時段都是 -∞，不得略過
    mrtEqual(pw.close(upTo: 2.5), [-Double.infinity, -Double.infinity])
    mrtEqual(pw.maxDBFS, -20)

    // 從未 feed：時段從 0 起算，一樣逐段回 -∞
    var none = PeakWindow(windowSeconds: 0.5)
    mrtEqual(none.close(upTo: 1.0), [-Double.infinity, -Double.infinity])
    mrtEqual(none.maxDBFS, -Double.infinity)
}

// §4.5.8：同一串 feed 中途改變取樣率時，時段邊界只依 t（PTS 秒）決定。
func testPeakWindowIgnoresSampleRateChange() throws {
    var pw = PeakWindow(windowSeconds: 0.5)
    // 前段：48 kHz、每緩衝 1024 frames（約 0.0213 秒一次），值 -20
    var t = 0.0
    while t < 0.9 { pw.feed(t: t, dbfs: -20); t += 1024.0 / 48000.0 }
    // 0.9 秒起切到 16 kHz HFP、每緩衝 2048 frames（0.128 秒一次），值 -35
    t = 0.9
    while t < 2.0 { pw.feed(t: t, dbfs: -35); t += 2048.0 / 16000.0 }
    let peaks = pw.close(upTo: 2.0)
    // 時段：[0,0.5) -20、[0.5,1.0) 兩種格式都有 → -20、[1.0,1.5) -35、[1.5,2.0) -35
    mrtEqual(peaks, [-20, -20, -35, -35])

    // 以實際緩衝量測後 feed：格式改變不影響邊界
    guard let a = mrtMakeAudioBuffer(sampleRate: 48000, channels: 2, interleaved: false, kind: .float32,
                                      frames: 480, value: { f, _ in f % 2 == 0 ? 0.5 : -0.5 }),
          let b = mrtMakeAudioBuffer(sampleRate: 16000, channels: 1, interleaved: false, kind: .int16,
                                      frames: 160, value: { f, _ in f % 2 == 0 ? 0.25 : -0.25 }),
          let da = rmsDBFS(sampleBuffer: a), let db = rmsDBFS(sampleBuffer: b) else {
        mrtExpect(false, "無法建立或量測緩衝"); return
    }
    var mixed = PeakWindow(windowSeconds: 0.5)
    mixed.feed(t: 0.2, dbfs: da)
    mixed.feed(t: 0.7, dbfs: db)
    let mp = mixed.close(upTo: 1.0)
    mrtEqual(mp.count, 2)
    mrtNear(mp.first, mrtDB(0.5))
    mrtNear(mp.count == 2 ? mp[1] : nil, mrtDB(0.25), tol: 0.02)
}

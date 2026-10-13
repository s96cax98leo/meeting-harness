// spec §4.5.1–4.5.3、§4.5.8：Detectors.swift（SilenceDetector、BlackDetector、SuspendedDetector、nonBlackRatio）。
// 參數一律明寫正式值（spec §3.4：-60 dBFS／15 秒、0.01／5 秒、5 秒）。
// 觸發時點容許「到達門檻的那個樣本」或「下一個樣本」（≥ 與 > 兩種邊界讀法），其餘一律精確。
import Foundation

let mrtDetectorsTests: [MRTCase] = [
    ("testSilenceDetector15s", testSilenceDetector15s),
    ("testSilenceNotTriggeredByFormatChange", testSilenceNotTriggeredByFormatChange),
    ("testBlackDetector5s", testBlackDetector5s),
    ("testSuspendedDetector", testSuspendedDetector),
    ("testNonBlackRatio", testNonBlackRatio),
]

/// 以 0.5 秒步進 feed，回傳回 true 的時間點。
func mrtFeedSilence(_ d: inout SilenceDetector, from: Double, to: Double, dbfs: Double) -> [Double] {
    var fired: [Double] = []
    var t = from
    while t < to - 1e-9 {
        if d.feed(t: t, dbfs: dbfs) { fired.append(t) }
        t += 0.5
    }
    return fired
}

// §4.5.1：連續 15 秒 < -60 dBFS 告警，同一段靜音只告警一次；dbfs ≥ 門檻即重置。
func testSilenceDetector15s() throws {
    var d = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    let fired = mrtFeedSilence(&d, from: 0, to: 40, dbfs: -70)
    mrtEqual(fired.count, 1, "同一段靜音只告警一次")
    if let f = fired.first { mrtExpect(f >= 15.0 && f <= 15.5, "應在連續 15 秒時觸發，實際 \(f)") }

    // 恢復（≥ -60）後重置，再靜音 15 秒會再告警一次
    mrtEqual(d.feed(t: 40, dbfs: -30), false)
    let again = mrtFeedSilence(&d, from: 40.5, to: 70, dbfs: -70)
    mrtEqual(again.count, 1, "重置後的新一段靜音應再告警一次")
    if let f = again.first { mrtExpect(f >= 55.5 && f <= 56.0, "實際 \(f)") }

    // 14.5 秒的靜音不告警
    var short = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    mrtEqual(mrtFeedSilence(&short, from: 0, to: 14.5, dbfs: -70), [])
    mrtEqual(short.feed(t: 14.5, dbfs: -20), false)
    mrtEqual(mrtFeedSilence(&short, from: 15, to: 29, dbfs: -70), [], "中途恢復後重新計時")

    // 剛好等於門檻（-60）算重置，不算靜音
    var edge = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    _ = mrtFeedSilence(&edge, from: 0, to: 10, dbfs: -70)
    mrtEqual(edge.feed(t: 10, dbfs: -60), false)
    mrtEqual(mrtFeedSilence(&edge, from: 10.5, to: 25, dbfs: -70), [], "-60 應重置計時")

    // -∞（時段沒有緩衝）算靜音
    var inf = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    mrtEqual(mrtFeedSilence(&inf, from: 0, to: 20, dbfs: -Double.infinity).count, 1)
}

// §4.5.8：SilenceDetector 吃 PeakWindow 的時段峰值；格式改變造成的短暫中斷不得觸發。
func testSilenceNotTriggeredByFormatChange() throws {
    var d = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    var pw = PeakWindow(windowSeconds: 0.5)
    var fired: [Double] = []
    // 0–20 秒 48 kHz 正常有聲（-25），20–22.5 秒 HFP 重新協商沒有緩衝，22.5–60 秒 16 kHz 有聲（-30）
    var t = 0.0
    while t < 20 { pw.feed(t: t, dbfs: -25); t += 1024.0 / 48000.0 }
    t = 22.5
    while t < 60 { pw.feed(t: t, dbfs: -30); t += 2048.0 / 16000.0 }
    let peaks = pw.close(upTo: 60)
    mrtEqual(peaks.count, 120)
    for (i, p) in peaks.enumerated() where d.feed(t: Double(i) * 0.5 + 0.5, dbfs: p) {
        fired.append(Double(i) * 0.5 + 0.5)
    }
    mrtEqual(fired, [], "2.5 秒的格式切換中斷不得觸發靜音告警")

    // 對照：真的中斷 ≥ 15 秒才告警
    var d2 = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    var pw2 = PeakWindow(windowSeconds: 0.5)
    t = 0
    while t < 10 { pw2.feed(t: t, dbfs: -25); t += 0.1 }
    t = 30
    while t < 40 { pw2.feed(t: t, dbfs: -25); t += 0.1 }
    var n = 0
    for (i, p) in pw2.close(upTo: 40).enumerated() where d2.feed(t: Double(i) * 0.5 + 0.5, dbfs: p) { n += 1 }
    mrtEqual(n, 1, "20 秒沒有緩衝應告警一次")
}

// §4.5.2：非黑比例連續 5 秒 < 0.01 開一個區間，恢復時關閉。
func testBlackDetector5s() throws {
    var d = BlackDetector(ratio: 0.01, seconds: 5)
    var opened: [Double] = []
    // 每秒一幀：0–2 正常、3–10 全黑、11 起恢復
    for s in 0...14 {
        let ratio: Double = (3...10).contains(s) ? 0.0 : 1.0
        if d.feed(t: Double(s), nonBlackRatio: ratio) { opened.append(Double(s)) }
        if s == 9 {
            mrtEqual(d.intervals.count, 1, "全黑 5 秒後應已開區間")
            mrtExpect(d.intervals.last?.end == nil, "尚未恢復時 end 應為 nil")
        }
    }
    mrtEqual(opened.count, 1, "同一段只開一次")
    if let o = opened.first { mrtExpect(o == 8 || o == 9, "連續 5 秒（3→8）時開區間，實際 \(o)") }
    mrtEqual(d.intervals, [BlackInterval(start: 3, end: 11)], "start＝第一個低於門檻的樣本，end＝恢復的第一個樣本")

    // 第二段：20–30 全黑，至結束仍未恢復
    for s in 15...30 {
        _ = d.feed(t: Double(s), nonBlackRatio: s >= 20 ? 0.005 : 0.5)
    }
    mrtEqual(d.intervals, [BlackInterval(start: 3, end: 11), BlackInterval(start: 20, end: nil)])

    // 只黑 3 秒不開區間；比例恰為 0.01 不算黑
    var short = BlackDetector(ratio: 0.01, seconds: 5)
    for s in 0...10 {
        let r: Double = (2...4).contains(s) ? 0.0 : 0.01
        mrtEqual(short.feed(t: Double(s), nonBlackRatio: r), false, "t=\(s)")
    }
    mrtEqual(short.intervals, [])
}

// §4.5.3：連續 5 秒只收到 suspended 回一次 true；收到其他狀態即重置。
func testSuspendedDetector() throws {
    var d = SuspendedDetector(seconds: 5)
    var fired: [Double] = []
    for s in 0...12 {
        if d.feed(t: Double(s), status: .suspended) { fired.append(Double(s)) }
    }
    mrtEqual(fired.count, 1, "同一段只回一次 true")
    if let f = fired.first { mrtExpect(f == 5 || f == 6, "實際 \(f)") }

    // 收到 complete 重置；之後 4 秒 suspended 不觸發
    mrtEqual(d.feed(t: 13, status: .complete), false)
    for s in 14...17 { mrtEqual(d.feed(t: Double(s), status: .suspended), false, "t=\(s)") }
    // idle 也算其他狀態
    mrtEqual(d.feed(t: 18, status: .idle), false)
    var again: [Double] = []
    for s in 19...30 where d.feed(t: Double(s), status: .suspended) { again.append(Double(s)) }
    mrtEqual(again.count, 1, "重置後新一段應再回一次 true")
}

/// 建一個 Y plane：bright(x, y) 為 true 的像素填 value，其餘填 16（video range 黑）。
func mrtLuma(width: Int, height: Int, bytesPerRow: Int, value: UInt8 = 200,
             bright: (Int, Int) -> Bool) -> [UInt8] {
    var buf = [UInt8](repeating: 0, count: bytesPerRow * height)
    for y in 0..<height { for x in 0..<width { buf[y * bytesPerRow + x] = bright(x, y) ? value : 16 } }
    return buf
}

// §4.5.2：8×8 格點中心共 64 點、亮度 > 24 的比例；寬或高 ≤ 16 回 nil。
func testNonBlackRatio() throws {
    func ratio(_ buf: [UInt8], _ w: Int, _ h: Int, _ bpr: Int) -> Double? {
        buf.withUnsafeBufferPointer { nonBlackRatio(lumaPlane: $0, width: w, height: h, bytesPerRow: bpr) }
    }
    // bytesPerRow 大於 width（有行尾填充），確認以 bytesPerRow 定址
    let w = 64, h = 48, bpr = 80
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr) { _, _ in false }, w, h, bpr), 0.0, "全黑")
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr) { _, _ in true }, w, h, bpr), 1.0, "全亮")
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr) { x, _ in x < w / 2 }, w, h, bpr), 0.5, "左半亮")
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr) { _, y in y < h / 4 }, w, h, bpr), 0.25, "上四分之一亮")
    // 行尾填充區塞滿亮值，不得被算進去
    var padded = mrtLuma(width: w, height: h, bytesPerRow: bpr) { _, _ in false }
    for y in 0..<h { for x in w..<bpr { padded[y * bpr + x] = 255 } }
    mrtEqual(ratio(padded, w, h, bpr), 0.0, "行尾填充不得計入")
    // 門檻：亮度 24 算黑、25 算非黑
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr, value: 24) { _, _ in true }, w, h, bpr), 0.0)
    mrtEqual(ratio(mrtLuma(width: w, height: h, bytesPerRow: bpr, value: 25) { _, _ in true }, w, h, bpr), 1.0)
    // 寬或高 ≤ 16 回 nil；17 可算
    mrtExpect(ratio([UInt8](repeating: 200, count: 16 * 64), 16, 64, 16) == nil, "寬 16 應回 nil")
    mrtExpect(ratio([UInt8](repeating: 200, count: 64 * 16), 64, 16, 64) == nil, "高 16 應回 nil")
    mrtEqual(ratio([UInt8](repeating: 200, count: 17 * 17), 17, 17, 17), 1.0)
}

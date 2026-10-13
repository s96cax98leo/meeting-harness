// Core/Segments.swift —— 段落命名、空隙計算、每段畫布尺寸、換段分流、影片位元率、影片心跳（spec §3.4、§4.3.2、§4.3.6、§4.4.1、§4.4.3、§4.4.6、§4.4.10）
import CoreGraphics
import Foundation

/// index 從 1 起；1 → "seg-0001.mov"。
func segmentFileName(index: Int) -> String {
    String(format: "seg-%04d.mov", index)
}

/// g_i = startedAt[i+1] − startedAt[i] − audioDurations[i]；n < 2 回 []。重疊時為負值，不截成 0。
func boundaryGaps(startedAt: [Double], audioDurations: [Double]) -> [Double] {
    let n = min(startedAt.count, audioDurations.count)
    guard n >= 2 else { return [] }
    return (0..<(n - 1)).map { startedAt[$0 + 1] - startedAt[$0] - audioDurations[$0] }
}

/// 各邊 point×scale 後向下取偶數（H.264 要求偶數寬高）；結果至少 2×2。
func evenPixelSize(points: CGSize, scale: Double) -> PixelSize {
    func even(_ v: Double) -> Int {
        var n = Int(floor(v * scale + 1e-9))
        n -= n % 2
        return max(n, 2)
    }
    return PixelSize(width: even(Double(points.width)), height: even(Double(points.height)))
}

/// t6 第二輪（缺陷 A，§4.3.6）：換段當下同步讀到的視窗大小（point）決定新段尺寸。
/// windowPoints 為 nil、寬或高 ≤ 0、或任一邊非有限值 → previous（讀不到沿用上一段）；
/// 否則 evenPixelSize(points: windowPoints, scale: scale)（與 previous 相同也照回）。
func nextSegmentSize(windowPoints: CGSize?, scale: Double, previous: PixelSize) -> PixelSize {
    guard let p = windowPoints else { return previous }
    let w = Double(p.width), h = Double(p.height)
    guard w.isFinite, h.isFinite, w > 0, h > 0 else { return previous }
    return evenPixelSize(points: p, scale: scale)
}

/// D20：換段時 sample 的去向（design §7.2 換段第 4 步）。
enum SampleRoute: Equatable { case old, new, both }

/// 單位秒（sample 時鐘）；呼叫端保證 end ≥ start；視訊 sample 以 end == start 呼叫。
/// end ≤ boundary → .old；否則 start ≥ boundary → .new；否則（start < boundary < end）→ .both。
func routeSample(start: Double, end: Double, boundary: Double) -> SampleRoute {
    if end <= boundary && start < boundary { return .old }
    if start >= boundary { return .new }
    return .both
}

/// D20：width × height × 5 / 4（整數運算），夾在 [4_000_000, 10_000_000]；2992×1876 → 7_016_240。
func segmentVideoBitRate(width: Int, height: Int) -> Int {
    let raw = width * height * 5 / 4
    return min(max(raw, 4_000_000), 10_000_000)
}

/// t6 第二輪（缺陷 E／D22，§4.4.10）：收到 idle 的 .screen sample 時，是否重送最後一個 complete 幀。
/// hasLastFrame == false、lastVideoPTS 為 nil、或任一時間非有限值 → false；
/// 否則 samplePTS − lastVideoPTS ≥ interval → true（單位秒，sample 時鐘；正式值 interval = 1.0，呼叫端明寫）。
func shouldEmitVideoHeartbeat(samplePTS: Double, lastVideoPTS: Double?, hasLastFrame: Bool, interval: Double) -> Bool {
    guard hasLastFrame, let last = lastVideoPTS, samplePTS.isFinite, last.isFinite, interval.isFinite else { return false }
    return samplePTS - last >= interval
}

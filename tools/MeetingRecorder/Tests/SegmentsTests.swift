// spec §4.3.2、§4.4.1、§4.4.3（計算）：Segments.swift（segmentFileName、boundaryGaps、evenPixelSize）。
// spec §4.4.6（D20）：Segments.swift（SampleRoute、routeSample、segmentVideoBitRate）。
// spec §4.3.6、§4.4.10（t6 第二輪，缺陷 A、E／D22）：Segments.swift（nextSegmentSize、shouldEmitVideoHeartbeat）。
import Foundation
import CoreGraphics

let mrtSegmentsTests: [MRTCase] = [
    ("testSegmentFileName", testSegmentFileName),
    ("testBoundaryGaps", testBoundaryGaps),
    ("testEvenPixelSize", testEvenPixelSize),
    ("testRouteSample", testRouteSample),
    ("testSegmentVideoBitRate", testSegmentVideoBitRate),
    ("testNextSegmentSize", testNextSegmentSize),
    ("testShouldEmitVideoHeartbeat", testShouldEmitVideoHeartbeat),
]

// §4.4.1：四位數、從 0001 起。
func testSegmentFileName() throws {
    mrtEqual(segmentFileName(index: 1), "seg-0001.mov")
    mrtEqual(segmentFileName(index: 2), "seg-0002.mov")
    mrtEqual(segmentFileName(index: 12), "seg-0012.mov")
    mrtEqual(segmentFileName(index: 180), "seg-0180.mov")
    mrtEqual(segmentFileName(index: 9999), "seg-9999.mov")
}

// §4.4.3：g_i = startedAt[i+1] − startedAt[i] − audioDurations[i]；n < 2 回 []。
func testBoundaryGaps() throws {
    let g = boundaryGaps(startedAt: [0.012, 60.033, 120.050], audioDurations: [60.000, 60.010, 59.900])
    mrtEqual(g.count, 2)
    mrtNear(g.first, 0.021, tol: 1e-9)
    mrtNear(g.count == 2 ? g[1] : nil, 0.007, tol: 1e-9)
    // 重疊（下一段比上一段音訊結束還早開始）為負值，不截成 0
    let neg = boundaryGaps(startedAt: [0, 59.9], audioDurations: [60.0, 60.0])
    mrtEqual(neg.count, 1)
    mrtNear(neg.first, -0.1, tol: 1e-9)
    mrtEqual(boundaryGaps(startedAt: [0.012], audioDurations: [60.0]), [])
    mrtEqual(boundaryGaps(startedAt: [], audioDurations: []), [])
}

// §4.3.2：各邊 point×scale 後向下取偶數；結果至少 2×2。
func testEvenPixelSize() throws {
    mrtEqual(evenPixelSize(points: CGSize(width: 1496, height: 938), scale: 2), PixelSize(width: 2992, height: 1876))
    mrtEqual(evenPixelSize(points: CGSize(width: 1197, height: 840), scale: 1), PixelSize(width: 1196, height: 840))
    mrtEqual(evenPixelSize(points: CGSize(width: 500.7, height: 301.9), scale: 1), PixelSize(width: 500, height: 300))
    mrtEqual(evenPixelSize(points: CGSize(width: 333.5, height: 201), scale: 1.5), PixelSize(width: 500, height: 300))
    mrtEqual(evenPixelSize(points: CGSize(width: 0.4, height: 0.4), scale: 1), PixelSize(width: 2, height: 2))
    mrtEqual(evenPixelSize(points: CGSize(width: 1, height: 1), scale: 1), PixelSize(width: 2, height: 2))
    let p = evenPixelSize(points: CGSize(width: 1023.3, height: 767.7), scale: 2)
    mrtEqual(p.width % 2, 0); mrtEqual(p.height % 2, 0)
    mrtEqual(p, PixelSize(width: 2046, height: 1534))
}

// §4.4.6（D20）：換段時 sample 的去向，案例照 §4.4.6 原文。視訊 sample 以 end == start 呼叫。
// 注意 (60.0, 60.0, 60) → .new：PTS 恰在邊界的視訊 sample 屬於新段（design.md §7.2 換段第 4 步
// 「舊 writer 只收 PTS < 邊界的 sample」；ADR「第一個 PTS ≥ B_{i+1} 的 sample 一到就切換」）。
func testRouteSample() throws {
    let cases: [(start: Double, end: Double, boundary: Double, expected: SampleRoute, note: String)] = [
        (59.0, 59.5, 60, SampleRoute.old, "整段在邊界前"),
        (59.98, 60.0, 60, SampleRoute.old, "結束恰在邊界（end ≤ boundary）"),
        (59.99, 60.01, 60, SampleRoute.both, "跨過邊界"),
        (60.0, 60.0, 60, SampleRoute.new, "視訊 sample 恰在邊界（end == start == boundary）"),
        (60.0, 60.02, 60, SampleRoute.new, "開始恰在邊界（start ≥ boundary）"),
        (61.0, 61.0, 60, SampleRoute.new, "視訊 sample 在邊界後"),
    ]
    for c in cases {
        let r: SampleRoute = routeSample(start: c.start, end: c.end, boundary: c.boundary)
        mrtEqual(r, c.expected, "(\(c.start), \(c.end), \(c.boundary)) \(c.note)")
    }
}

// §4.4.6（D20）：width × height × 5 / 4（整數運算），再夾在 [4_000_000, 10_000_000]。
func testSegmentVideoBitRate() throws {
    let cases: [(width: Int, height: Int, expected: Int)] = [
        (2992, 1876, 7_016_240),
        (640, 480, 4_000_000),
        (5120, 2880, 10_000_000),
        (1920, 1080, 4_000_000),
    ]
    for c in cases {
        let b: Int = segmentVideoBitRate(width: c.width, height: c.height)
        mrtEqual(b, c.expected, "\(c.width)×\(c.height)")
    }
}

// §4.3.6（t6 第二輪，缺陷 A）：換段當下同步讀到的視窗大小（point）決定新段尺寸；
// 讀不到（nil）、寬或高 ≤ 0、或任一邊非有限值 → 沿用上一段（previous）；否則 evenPixelSize。
func testNextSegmentSize() throws {
    let big = PixelSize(width: 2992, height: 1876)
    let small = PixelSize(width: 2770, height: 1736)
    let cases: [(points: CGSize?, scale: Double, previous: PixelSize, expected: PixelSize, label: String)] = [
        (CGSize(width: 1496, height: 938), 2.0, big, big, "尺寸未變"),
        (CGSize(width: 1385, height: 868), 2.0, big, small, "縮小後換段即套用"),
        (CGSize(width: 1385.5, height: 868.7), 2.0, big, small, "非整數 point 向下取偶數"),
        (nil, 2.0, small, small, "讀不到沿用上一段"),
        (CGSize(width: 0, height: 868), 2.0, big, big, "寬為 0 沿用上一段"),
        (CGSize(width: 1385, height: -1), 2.0, big, big, "高為負沿用上一段"),
        (CGSize(width: CGFloat.infinity, height: 868), 2.0, big, big, "非有限值沿用上一段"),
    ]
    for c in cases {
        let got: PixelSize = nextSegmentSize(windowPoints: c.points, scale: c.scale, previous: c.previous)
        mrtEqual(got, c.expected, c.label)
    }
}

// §4.4.10（t6 第二輪，缺陷 E／D22）：收到 idle 的 .screen sample 時，距目前段落最後一個視訊 PTS ≥ interval（1.0 秒）
// 且有最後一個 complete 幀才重送；lastVideoPTS 為 nil、沒有最後一幀、或任一時間非有限值 → false。
func testShouldEmitVideoHeartbeat() throws {
    let cases: [(sample: Double, last: Double?, hasLast: Bool, expected: Bool, label: String)] = [
        (10.0, 9.0, true, true, "剛好 1 秒"),
        (9.999, 9.0, true, false, "未滿 1 秒"),
        (70.0, 9.0, true, true, "遠超過 1 秒"),
        (10.0, nil, true, false, "目前段落尚無視訊 PTS"),
        (10.0, 9.0, false, false, "沒有最後一個 complete 幀"),
        (Double.nan, 9.0, true, false, "samplePTS 為 NaN"),
        (10.0, Double.infinity, true, false, "lastVideoPTS 為無限大"),
    ]
    for c in cases {
        let got: Bool = shouldEmitVideoHeartbeat(samplePTS: c.sample, lastVideoPTS: c.last,
                                                 hasLastFrame: c.hasLast, interval: 1.0)
        mrtEqual(got, c.expected, c.label)
    }
}

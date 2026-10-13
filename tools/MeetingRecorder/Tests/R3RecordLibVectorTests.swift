// spec §4.32.1、§4.32.2（Q9a）：Python `bin/lib/_record_lib.py` 與 Swift Core 共用的測試向量。
// 向量檔 tests/record/vectors/output_time.json、levels_intervals.json 由 r3-red-py 寫（plan.md §10.2：Red 層整合後才一起可跑）。
// 找檔順序：環境變數 MRT_VECTORS_DIR → 從目前目錄與本檔路徑往上找 tests/record/vectors。
// 檔案頂層可為陣列，或含 "cases" 陣列的物件。
import Foundation

let mrtR3RecordLibVectorTests: [MRTCase] = [
    ("testOutputTimeVectors", testOutputTimeVectors),
    ("testLevelsIntervalsVectors", testLevelsIntervalsVectors),
]

func mrtR3VectorsDir() -> URL? {
    let fm = FileManager.default
    if let env = ProcessInfo.processInfo.environment["MRT_VECTORS_DIR"], !env.isEmpty {
        return URL(fileURLWithPath: env, isDirectory: true)
    }
    var starts = [URL(fileURLWithPath: fm.currentDirectoryPath, isDirectory: true)]
    let here = URL(fileURLWithPath: "\(#filePath)")
    starts.append(here.path.hasPrefix("/") ? here.deletingLastPathComponent()
                  : URL(fileURLWithPath: fm.currentDirectoryPath).appendingPathComponent(here.path).deletingLastPathComponent())
    for start in starts {
        var dir = start.standardizedFileURL
        for _ in 0..<8 {
            let cand = dir.appendingPathComponent("tests/record/vectors", isDirectory: true)
            var isDir: ObjCBool = false
            if fm.fileExists(atPath: cand.path, isDirectory: &isDir), isDir.boolValue { return cand }
            let up = dir.deletingLastPathComponent()
            if up.path == dir.path { break }
            dir = up
        }
    }
    return nil
}

/// 讀向量檔，回每一筆（[String: Any]）；讀不到就記一筆失敗並回 []。
func mrtR3LoadVectors(_ name: String, file: StaticString = #fileID, line: UInt = #line) -> [[String: Any]] {
    guard let dir = mrtR3VectorsDir() else {
        mrtFail("找不到 tests/record/vectors（r3-red-py 的向量檔）", file: file, line: line); return []
    }
    let url = dir.appendingPathComponent(name)
    guard let data = try? Data(contentsOf: url) else {
        mrtFail("讀不到 \(url.path)", file: file, line: line); return []
    }
    guard let top = try? JSONSerialization.jsonObject(with: data) else {
        mrtFail("\(name) 不是合法 JSON", file: file, line: line); return []
    }
    if let arr = top as? [[String: Any]] { return arr }
    if let obj = top as? [String: Any], let arr = obj["cases"] as? [[String: Any]] { return arr }
    mrtFail("\(name) 的頂層應為陣列或含 cases 陣列的物件", file: file, line: line)
    return []
}

func mrtR3Num(_ any: Any?) -> Double? {
    if any is NSNull { return nil }
    if let n = any as? NSNumber { return n.doubleValue }
    return nil
}

/// pauses 欄：pauseEvents 形狀（[{t, kind, ...}]）或配對形狀（[[pause.t, resume.t 或 null]]）都轉成 [PauseEvent]。
func mrtR3Pauses(_ any: Any?) -> [PauseEvent]? {
    guard let arr = any as? [Any] else { return any == nil || any is NSNull ? [] : nil }
    var out: [PauseEvent] = []
    for e in arr {
        if let d = e as? [String: Any] {
            guard let t = mrtR3Num(d["t"]), let ks = d["kind"] as? String, let k = PauseEventKind(rawValue: ks) else { return nil }
            out.append(PauseEvent(t: t, outputT: mrtR3Num(d["outputT"]) ?? 0, wallClock: (d["wallClock"] as? String) ?? "", kind: k))
        } else if let pair = e as? [Any], pair.count == 2, let p = mrtR3Num(pair[0]) {
            out.append(PauseEvent(t: p, outputT: 0, wallClock: "", kind: .pause))
            if let r = mrtR3Num(pair[1]) { out.append(PauseEvent(t: r, outputT: 0, wallClock: "", kind: .resume)) }
        } else {
            return nil
        }
    }
    return out
}

// §4.32.1：Swift outputTime(recordT:firstSegmentStart:pauses:lOut:) 與向量的 expect 相同（±0.0005）。
func testOutputTimeVectors() throws {
    let cases = mrtR3LoadVectors("output_time.json")
    mrtExpect(!cases.isEmpty, "output_time.json 至少要有一筆")
    var sawLOut018 = false
    var sawUnpaired = false
    for (i, c) in cases.enumerated() {
        guard let t = mrtR3Num(c["t"]), let first = mrtR3Num(c["first_start"]), let expect = mrtR3Num(c["expect"]),
              let pauses = mrtR3Pauses(c["pauses"]) else {
            mrtFail("第 \(i) 筆缺 t／first_start／pauses／expect：\(c)", file: #fileID, line: #line); continue
        }
        let lOut = mrtR3Num(c["l_out"]) ?? 0
        if abs(lOut - 0.18) < 1e-9 { sawLOut018 = true }
        if pauses.last?.kind == .pause { sawUnpaired = true }
        mrtNear(outputTime(recordT: t, firstSegmentStart: first, pauses: pauses, lOut: lOut), expect, tol: 0.0005, "第 \(i) 筆 \(c)")
        if lOut == 0 {
            // l_out=0 時與 R2 的 outputTime 結果相同（R2 §4.18）
            mrtNear(outputTime(recordT: t, firstSegmentStart: first, pauses: pauses), expect, tol: 0.0005, "第 \(i) 筆（R2 outputTime）")
        }
    }
    mrtExpect(sawLOut018, "向量應涵蓋 l_out=0.18")
    mrtExpect(sawUnpaired, "向量應涵蓋沒配對的 pause")
}

// §4.32.2：levels_intervals 向量的性質（門檻嚴格大於、null 視為無聲、夾在 [0, total]、遞增不重疊）。
// §3.20 沒有列 Swift 端 levels_intervals 的名稱，Swift 側只驗共用向量本身符合 §4.32.2 的規則（open_questions）。
// 欄位依 design.md R3-D6 的 levels_intervals(levels, window, threshold_db, merge_gap, pad, total) 加 expect。
func testLevelsIntervalsVectors() throws {
    let cases = mrtR3LoadVectors("levels_intervals.json")
    mrtExpect(!cases.isEmpty, "levels_intervals.json 至少要有一筆")
    var sawThresholdEqual = false
    var sawNull = false
    for (i, c) in cases.enumerated() {
        guard let levels = c["levels"] as? [Any], let window = mrtR3Num(c["window"]), let threshold = mrtR3Num(c["threshold_db"]),
              let total = mrtR3Num(c["total"]), let expectRaw = c["expect"] as? [Any] else {
            mrtFail("第 \(i) 筆缺 levels／window／threshold_db／total／expect：\(c)", file: #fileID, line: #line); continue
        }
        var ivs: [(Double, Double)] = []
        for e in expectRaw {
            guard let pair = e as? [Any], pair.count == 2, let s = mrtR3Num(pair[0]), let en = mrtR3Num(pair[1]) else {
                mrtFail("第 \(i) 筆 expect 的元素應為 [start, end]：\(e)", file: #fileID, line: #line); continue
            }
            ivs.append((s, en))
        }
        for (j, iv) in ivs.enumerated() {
            mrtExpect(iv.0 >= 0 && iv.1 <= total + 1e-9, "第 \(i) 筆區間 \(iv) 應夾在 [0, \(total)]")
            mrtExpect(iv.0 < iv.1, "第 \(i) 筆區間 \(iv) 應 start < end")
            if j > 0 { mrtExpect(ivs[j - 1].1 < iv.0, "第 \(i) 筆區間應遞增且不重疊：\(ivs[j - 1]) 與 \(iv)") }
        }
        for (k, lv) in levels.enumerated() {
            let v = mrtR3Num(lv)
            if v == nil { sawNull = true }
            if v == threshold { sawThresholdEqual = true }
            let loud = (v ?? -Double.infinity) > threshold     // 門檻嚴格大於；null 視為無聲
            let mid = (Double(k) + 0.5) * window
            if loud, mid <= total {
                mrtExpect(ivs.contains { $0.0 <= mid && mid <= $0.1 }, "第 \(i) 筆：有聲的窗 \(k)（中點 \(mid)）應被某個區間涵蓋")
            }
        }
        if !levels.contains(where: { (mrtR3Num($0) ?? -Double.infinity) > threshold }) {
            mrtEqual(ivs.count, 0, "第 \(i) 筆：沒有有聲的窗時應為空")
        }
    }
    mrtExpect(sawThresholdEqual, "向量應涵蓋等於門檻（-60.0 視為無聲）的窗")
    mrtExpect(sawNull, "向量應涵蓋 null 的窗")
}

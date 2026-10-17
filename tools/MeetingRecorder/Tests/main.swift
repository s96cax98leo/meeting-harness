// MeetingRecorder Core 測試的極簡斷言執行器（plan.md §2 t2）。
// 不依賴 XCTest：run.sh 以 swiftc 把 Core 與各 *Tests.swift 編成一支執行檔。
// 有任何斷言失敗即以結束碼 1 結束。可傳一個參數只跑名稱含該字串的測試。
import Foundation

final class MRTState {
    static var current = ""
    static var failures: [String] = []
}

func mrtFail(_ msg: String, file: StaticString, line: UInt) {
    MRTState.failures.append("\(MRTState.current)：\(msg)（\(file):\(line)）")
}

func mrtExpect(_ cond: Bool, _ msg: @autoclosure () -> String = "",
               file: StaticString = #fileID, line: UInt = #line) {
    if !cond { mrtFail("條件不成立 \(msg())", file: file, line: line) }
}

func mrtEqual<T: Equatable>(_ actual: T, _ expected: T, _ msg: @autoclosure () -> String = "",
                            file: StaticString = #fileID, line: UInt = #line) {
    if actual != expected {
        mrtFail("實際 \(String(describing: actual))，預期 \(String(describing: expected)) \(msg())", file: file, line: line)
    }
}

func mrtNear(_ actual: Double?, _ expected: Double, tol: Double = 0.01, _ msg: @autoclosure () -> String = "",
             file: StaticString = #fileID, line: UInt = #line) {
    guard let a = actual else {
        mrtFail("實際 nil，預期 \(expected) \(msg())", file: file, line: line); return
    }
    if expected.isInfinite || a.isInfinite {
        if a != expected { mrtFail("實際 \(a)，預期 \(expected) \(msg())", file: file, line: line) }
        return
    }
    if abs(a - expected) > tol {
        mrtFail("實際 \(a)，預期 \(expected)±\(tol) \(msg())", file: file, line: line)
    }
}

func mrtContains(_ text: String, _ part: String, _ msg: @autoclosure () -> String = "",
                 file: StaticString = #fileID, line: UInt = #line) {
    if !text.contains(part) { mrtFail("「\(text)」不含「\(part)」 \(msg())", file: file, line: line) }
}

/// 把 Encodable 以 JSONEncoder 編碼後轉回 [String: Any]，供檢查鍵集合。
func mrtJSONObject<T: Encodable>(_ value: T, file: StaticString = #fileID, line: UInt = #line) -> [String: Any] {
    do {
        let data = try JSONEncoder().encode(value)
        if let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] { return obj }
        mrtFail("編碼結果不是 JSON 物件", file: file, line: line)
    } catch {
        mrtFail("編碼失敗：\(error)", file: file, line: line)
    }
    return [:]
}

typealias MRTCase = (name: String, run: () throws -> Void)

let mrtSuites: [(String, [MRTCase])] = [
    ("AudioLevelTests", mrtAudioLevelTests),
    ("ControlTests", mrtControlTests),
    ("DetectorsTests", mrtDetectorsTests),
    ("MenuBarR2Tests", mrtMenuBarR2Tests),
    ("T7Tests", mrtT7Tests),
    ("PreflightTests", mrtPreflightTests),
    ("RecordsTests", mrtRecordsTests),
    ("SegmentsTests", mrtSegmentsTests),
    ("TriggerTests", mrtTriggerTests),
    ("WindowListTests", mrtWindowListTests),
    // R3（spec §3.20、§4.26–§4.44 的 swift: 測試欄）
    ("R3LockTests", mrtR3LockTests),
    ("R3MenuBarTests", mrtR3MenuBarTests),
    ("R3SegmentSchedulerTests", mrtR3SegmentSchedulerTests),
    ("R3SyncTests", mrtR3SyncTests),
    ("R3RecordLibVectorTests", mrtR3RecordLibVectorTests),
    ("R3DesignTokenTests", mrtR3DesignTokenTests),
    ("R3xBackgroundTests", mrtR3xBackgroundTests),
]

let mrtFilter = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
var mrtRan = 0
var mrtFailedTests = 0
for (suite, cases) in mrtSuites {
    for c in cases where mrtFilter.isEmpty || c.name.contains(mrtFilter) || suite.contains(mrtFilter) {
        MRTState.current = "\(suite).\(c.name)"
        let before = MRTState.failures.count
        do { try c.run() } catch { mrtFail("丟出錯誤：\(error)", file: #fileID, line: #line) }
        mrtRan += 1
        if MRTState.failures.count > before {
            mrtFailedTests += 1
            print("FAIL \(MRTState.current)")
            for f in MRTState.failures[before...] { print("  - \(f)") }
        } else {
            print("ok   \(MRTState.current)")
        }
    }
}
print("共 \(mrtRan) 支，失敗 \(mrtFailedTests) 支")
if mrtRan == 0 { print("沒有任何測試被執行"); exit(1) }
exit(mrtFailedTests == 0 ? 0 : 1)

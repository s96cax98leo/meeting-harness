// Capture/Support.swift —— 共用小工具：log、參數、時間、家目錄、pid、上次預設值
import Foundation

/// 同時印到 stdout 與（選用的）log 檔。由 `open --args` 啟動時 stdout 無處可去，所以一律另寫檔。
final class Logger {
    private let handle: FileHandle?
    private let queue = DispatchQueue(label: "mh.logger")

    /// append=false 時清空既有內容（windows／diagnose-windows 的輸出檔）；
    /// append=true 給 record.log（同一個檔可能有正在錄製的實例在寫，不得清空）。
    init(path: String?, append: Bool = false) {
        guard let path else { handle = nil; return }
        let url = URL(fileURLWithPath: path)
        try? FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        if !append || !FileManager.default.fileExists(atPath: path) {
            FileManager.default.createFile(atPath: path, contents: nil, attributes: nil)
        }
        if append {
            // O_APPEND：每次寫入都接在當下檔尾。錄製實例、menu bar、quick-start 會同時寫 record.log，
            // 只在開檔時 seek 一次會互相覆蓋（t7，spec §6 第 109 條）
            let fd = open(path, O_WRONLY | O_APPEND | O_CLOEXEC)
            handle = fd >= 0 ? FileHandle(fileDescriptor: fd, closeOnDealloc: true) : nil
        } else {
            handle = FileHandle(forWritingAtPath: path)
        }
    }

    func line(_ s: String) {
        queue.sync {
            print(s)
            fflush(stdout)
            if let handle, let d = (s + "\n").data(using: .utf8) { handle.write(d) }
        }
    }
}

func die(_ msg: String, code: Int32, log: Logger? = nil) -> Never {
    log?.line(msg)
    FileHandle.standardError.write(Data((msg + "\n").utf8))
    exit(code)
}

/// 參數解析：只有 booleanFlags 裡的旗標不帶值，其餘 `--x` 一律吃下一個參數當值
/// （`--window-title ""` 的空字串、以 `-` 開頭的標題都不會被誤判）。
struct Args {
    static let booleanFlags: Set<String> = ["json", "ask-automation"]
    private var flags: [String: String] = [:]
    let positional: [String]

    init(_ argv: [String]) {
        var pos: [String] = []
        var i = 0
        while i < argv.count {
            let a = argv[i]
            if a.hasPrefix("--"), a.count > 2 {
                let key = String(a.dropFirst(2))
                if Args.booleanFlags.contains(key) || i + 1 >= argv.count {
                    flags[key] = "1"
                    i += 1
                } else {
                    flags[key] = argv[i + 1]
                    i += 2
                }
            } else {
                pos.append(a)
                i += 1
            }
        }
        positional = pos
    }

    func str(_ k: String) -> String? { flags[k] }
    func int(_ k: String) -> Int? { flags[k].flatMap { Int($0) } }
    func int64(_ k: String) -> Int64? { flags[k].flatMap { Int64($0) } }
    func has(_ k: String) -> Bool { flags[k] != nil }
}

/// ISO 8601（本地時區，含偏移），例 2026-10-11T10:00:00+08:00。
func isoNow(_ date: Date = Date()) -> String {
    let f = ISO8601DateFormatter()
    f.timeZone = TimeZone.current
    f.formatOptions = [.withInternetDateTime]
    return f.string(from: date)
}

/// 秒數取小數 3 位（spec §3.2）。
func round3(_ v: Double) -> Double { (v * 1000).rounded() / 1000 }
/// dBFS 取小數 1 位；-∞ 或非有限值為 nil（寫成 null，spec §3.2）。
func round1OrNil(_ v: Double) -> Double? { v.isFinite ? (v * 10).rounded() / 10 : nil }

/// 狀態檔所在目錄：--home ＞ MH_RECORD_HOME ＞ ~/.meeting-harness。
/// 由 open 啟動時環境變數不會傳進來，所以 record.sh 一律帶 --home。
func recordHome(_ args: Args) -> URL {
    if let h = args.str("home"), !h.isEmpty { return URL(fileURLWithPath: h, isDirectory: true) }
    if let h = ProcessInfo.processInfo.environment["MH_RECORD_HOME"], !h.isEmpty {
        return URL(fileURLWithPath: h, isDirectory: true)
    }
    return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".meeting-harness", isDirectory: true)
}

func pidAlive(_ pid: Int32) -> Bool {
    guard pid > 0 else { return false }
    return kill(pid, 0) == 0 || errno == EPERM
}

func readPid(_ url: URL) -> Int32? {
    guard let s = try? String(contentsOf: url, encoding: .utf8) else { return nil }
    return Int32(s.trimmingCharacters(in: .whitespacesAndNewlines))
}

func readStatus(_ url: URL) -> RecordStatus? {
    guard let d = try? Data(contentsOf: url) else { return nil }
    return try? JSONDecoder().decode(RecordStatus.self, from: d)
}

/// record.sh 每次成功開錄後覆寫的上次設定（design §3.1）；quick-start 只讀這個。
struct RecordDefaults {
    var root: String
    var type: String
    var attendees: [String]
    var harness: String?
    var python3: String?
    var ffmpeg: String?
    var minFreeBytes: Int64?

    static func load(_ url: URL) -> RecordDefaults? {
        guard let d = try? Data(contentsOf: url),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let root = o["root"] as? String, !root.isEmpty else { return nil }
        let attendees = (o["attendees"] as? [Any])?.compactMap { $0 as? String } ?? []
        func str(_ keys: String...) -> String? {
            for k in keys { if let v = o[k] as? String, !v.isEmpty { return v } }
            return nil
        }
        var mfb: Int64? = (o["minFreeBytes"] as? NSNumber)?.int64Value
        if mfb == nil, let s = o["minFreeBytes"] as? String { mfb = Int64(s) }
        return RecordDefaults(root: root, type: str("type") ?? "internal", attendees: attendees,
                              harness: str("harness", "harnessRoot"), python3: str("python3", "python"),
                              ffmpeg: str("ffmpeg", "ffmpegPath"), minFreeBytes: mfb)
    }
}

/// 沒有 record.sh 傳 --min-free-bytes 時的退路：與 bin/_record_estimate.py 同一公式（spec §3.7），以 120 分鐘估。
func fallbackMinFreeBytes(minutes: Double = 120) -> Int64 {
    Int64((minutes * (4 * 56_000_000 + 1_920_000)).rounded(.up)) + 2_000_000_000
}

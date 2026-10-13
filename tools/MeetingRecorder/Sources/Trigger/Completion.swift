// Trigger/Completion.swift —— menu bar 的共用小工具：menubar.prefs.json 讀改寫、選資料夾、
// 在 Finder 顯示成品、停止後自動前處理（spec §3.13、§4.21.5、§4.23）。
// R3：前處理通知帶通知分級（spec §4.39.1）；捨棄的場次（discarded）不自動前處理由 Core 的 shouldAutoPrep 擋（§4.42.5）。
import AppKit

/// menubar.prefs.json 的讀改寫。只有 menu bar 程序寫（含偏好設定視窗）；每次都從檔案讀最新再改，
/// 檔不存在或解不開時以預設值運作（loadMenuBarPrefs），寫失敗只記 record.log，不擋住 menu bar。
final class MenuBarPrefsStore {
    private let url: URL
    private let logURL: URL

    init(home: URL) {
        url = home.appendingPathComponent(menuBarPrefsFileName)
        logURL = home.appendingPathComponent("record.log")
    }

    var current: MenuBarPrefs { loadMenuBarPrefs(url) }

    func update(_ change: (inout MenuBarPrefs) -> Void) {
        var p = loadMenuBarPrefs(url)
        let before = p
        change(&p)
        guard p != before else { return }
        do {
            try saveMenuBarPrefs(p, to: url)
        } catch {
            Logger(path: logURL.path, append: true)
                .line("\(isoNow()) 寫 \(menuBarPrefsFileName) 失敗：\(error.localizedDescription)")
        }
    }

    /// 「存到」打勾的位置＝偏好設定的「預設存檔位置」；recentRoots 最多 5 個、最近的在前
    func setRoot(_ path: String) {
        update {
            $0.root = path
            $0.recentRoots = updatedRecentRoots($0.recentRoots, adding: path, limit: 5)
        }
    }
}

func isDirectoryPath(_ path: String) -> Bool {
    var dir: ObjCBool = false
    return FileManager.default.fileExists(atPath: path, isDirectory: &dir) && dir.boolValue
}

/// 結尾 "/" 去掉後比較（與 updatedRecentRoots 相同的規則）
func sameRoot(_ a: String, _ b: String) -> Bool {
    func trim(_ s: String) -> String {
        var s = s
        while s.count > 1 && s.hasSuffix("/") { s.removeLast() }
        return s
    }
    return trim(a) == trim(b)
}

/// 選存檔位置的資料夾；取消回 nil。
func chooseFolder(startingAt start: String?) -> String? {
    let panel = NSOpenPanel()
    panel.canChooseDirectories = true
    panel.canChooseFiles = false
    panel.canCreateDirectories = true
    panel.allowsMultipleSelection = false
    panel.prompt = "選擇"
    panel.message = "選擇錄音場次要存放的資料夾（之後的快捷開錄都存到這裡）"
    if let start, isDirectoryPath(start) { panel.directoryURL = URL(fileURLWithPath: start, isDirectory: true) }
    NSApp.activate(ignoringOtherApps: true)    // accessory app：不先帶到前面，面板會被別的視窗蓋住
    return panel.runModal() == .OK ? panel.url?.path : nil
}

/// 路徑本身不存在時往上找第一個存在的資料夾
func nearestExistingDirectory(_ path: String) -> URL {
    var url = URL(fileURLWithPath: path, isDirectory: true)
    while !FileManager.default.fileExists(atPath: url.path), url.path != "/" { url.deleteLastPathComponent() }
    return url
}

/// 在 Finder 選取場次 影片/ 下最新的 .mov；沒有就選場次目錄（spec §4.23.3、§4.23.4）
func revealSessionProduct(_ session: String) {
    let dir = URL(fileURLWithPath: session, isDirectory: true)
    let videos = dir.appendingPathComponent("影片", isDirectory: true)
    let fm = FileManager.default
    let movs = ((try? fm.contentsOfDirectory(at: videos, includingPropertiesForKeys: [.contentModificationDateKey],
                                             options: [.skipsHiddenFiles])) ?? [])
        .filter { $0.pathExtension.lowercased() == "mov" }
    func mtime(_ u: URL) -> Date {
        (try? u.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate) ?? .distantPast
    }
    if let newest = movs.max(by: { mtime($0) < mtime($1) }) {
        NSWorkspace.shared.activateFileViewerSelecting([newest])
    } else if fm.fileExists(atPath: dir.path) {
        NSWorkspace.shared.activateFileViewerSelecting([dir])
    } else {
        NSWorkspace.shared.open(nearestExistingDirectory(session))
    }
}

/// 停止後自動前處理（spec §4.23.2）：/bin/bash <harness>/bin/meeting.sh prep <場次目錄> 在背景跑，
/// stdout／stderr append 到 <home>/autoprep.log；以 terminationHandler 等結束（主執行緒不等）；同時只跑一個、其餘排隊。
final class AutoPrepRunner {
    private let home: URL
    /// 排隊中的（場次目錄, runId）；runId 給通知的 threadIdentifier 用
    private var pending: [(session: String, runId: String?)] = []
    private var running: Process?

    init(home: URL) {
        self.home = home
    }

    private var logURL: URL { home.appendingPathComponent("autoprep.log") }

    func enqueue(_ session: String, runId: String? = nil) {
        pending.append((session, runId))
        startNext()
    }

    private func appendLog(_ handle: FileHandle?, _ line: String) {
        handle?.write(Data((line + "\n").utf8))
    }

    private func openLog() -> FileHandle? {
        let fm = FileManager.default
        try? fm.createDirectory(at: home, withIntermediateDirectories: true)
        if !fm.fileExists(atPath: logURL.path) { fm.createFile(atPath: logURL.path, contents: nil) }
        let h = FileHandle(forWritingAtPath: logURL.path)
        h?.seekToEndOfFile()
        return h
    }

    private func startNext() {
        guard running == nil, !pending.isEmpty else { return }
        let (session, runId) = pending.removeFirst()
        let name = (session as NSString).lastPathComponent
        let handle = openLog()
        appendLog(handle, "── \(isoNow()) 自動前處理：\(session)")
        guard let harness = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))?.harness else {
            appendLog(handle, "✗ record.defaults.json 沒有 harness 路徑，沒辦法跑前處理")
            try? handle?.close()
            post(title: "前處理沒有執行", body: "\(name)：找不到 meeting-harness 路徑，詳見 autoprep.log", kind: .failure,
                 runId: runId)
            startNext()
            return
        }
        let script = URL(fileURLWithPath: harness, isDirectory: true).appendingPathComponent("bin/meeting.sh").path
        let p = Process()
        // 經登入 shell（zsh -l，讀 ~/.zprofile）跑 meeting.sh prep：menu bar 與登入項目的 PATH 很短，
        // 找不到 mlx_whisper 等使用者自己裝的工具（t7，spec §6 第 108 條）
        p.executableURL = URL(fileURLWithPath: "/bin/zsh")
        p.arguments = ["-lc", #"exec /bin/bash "$0" "$@""#, script, "prep", session]
        p.currentDirectoryURL = URL(fileURLWithPath: harness, isDirectory: true)
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"   // 登入 shell 前的底線
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        if let handle {
            p.standardOutput = handle
            p.standardError = handle
        }
        p.terminationHandler = { [weak self] proc in
            let code = proc.terminationStatus
            DispatchQueue.main.async {
                self?.appendLog(handle, "── \(isoNow()) 結束（結束碼 \(code)）")
                try? handle?.close()
                self?.finished(name: name, code: code, runId: runId)
            }
        }
        do {
            try p.run()
            running = p
        } catch {
            appendLog(handle, "✗ 啟動失敗：\(error.localizedDescription)")
            try? handle?.close()
            post(title: "前處理失敗", body: "\(name)：啟動失敗，詳見 autoprep.log", kind: .failure, runId: runId)
            startNext()
        }
    }

    private func finished(name: String, code: Int32, runId: String?) {
        running = nil
        if code == 0 {
            post(title: "前處理完成", body: name, kind: .completion, runId: runId)
        } else {
            post(title: "前處理失敗", body: "\(name)：結束碼 \(code)，詳見 \(logURL.path)（autoprep.log）", kind: .failure,
                 runId: runId)
        }
        startNext()
    }

    private func post(title: String, body: String, kind: NotificationKind, runId: String?) {
        let policy = notificationPolicy(kind: kind, runId: runId, timeSensitiveAllowed: false)
        DispatchQueue.global(qos: .utility).async { Notifier.post(title: title, body: body, policy: policy) }
    }
}

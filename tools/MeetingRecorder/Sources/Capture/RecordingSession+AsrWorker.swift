// Capture/RecordingSession+AsrWorker.swift —— 增量轉錄 worker 的啟動（meeting-speed spec §4.11.1；design §11）
// 從 RecordingSession.swift 拆出（meeting-speed spec §4.13.1），行為不變。
import AVFoundation
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

extension RecordingSession {
    /// 增量轉錄 worker（meeting-speed spec §4.11.1；design §11）：第一段收尾後起一次
    /// `/usr/bin/nice -n 10 <python3> <harness>/bin/lib/_asr_worker.py run <場次>`；直譯器沿用收尾那一支，不經 zsh -l。
    /// 要不要起交給 Core asrWorkerShouldStart（worker 檔不存在、config.json 的 transcribe.incremental.enabled 為 false 都不起）。
    /// worker 的 stdout／stderr 寫 錄音/tracks/asr/worker.log（spec §3.6）；錄製器結束不影響它，停止後由它自己補完欠的窗。
    /// 只在 q 上呼叫。
    func startAsrWorkerIfNeeded() {
        guard !asrWorkerStarted else { return }
        let harness = ctx.harness ?? defaults?.harness ?? ""
        let script = URL(fileURLWithPath: harness).appendingPathComponent("bin/lib/_asr_worker.py")
        let exists = !harness.isEmpty && FileManager.default.fileExists(atPath: script.path)
        guard asrWorkerShouldStart(finishedSegments: finishedSegments, alreadyStarted: asrWorkerStarted,
                                   workerScriptExists: exists,
                                   incrementalEnabled: incrementalTranscribeEnabled(harness: harness)) else { return }
        asrWorkerStarted = true
        let asrDir = ctx.tracksDir.appendingPathComponent("asr", isDirectory: true)
        let logURL = asrDir.appendingPathComponent("worker.log")
        let fm = FileManager.default
        try? fm.createDirectory(at: asrDir, withIntermediateDirectories: true)
        if !fm.fileExists(atPath: logURL.path) { fm.createFile(atPath: logURL.path, contents: nil) }
        let out = try? FileHandle(forWritingTo: logURL)
        _ = try? out?.seekToEnd()
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/nice")
        p.arguments = ["-n", "10", defaults?.python3 ?? "/usr/bin/python3", script.path, "run", ctx.session.path]
        p.qualityOfService = .utility
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if let ff = defaults?.ffmpeg, !ff.isEmpty { env["MH_FFMPEG"] = ff }
        env["MH_RECORD_HOME"] = ctx.home.path
        p.environment = env
        p.standardInput = FileHandle.nullDevice
        p.standardOutput = out ?? FileHandle.nullDevice
        p.standardError = out ?? FileHandle.nullDevice
        do {
            try p.run()
            log.line("● 增量轉錄已啟動（bin/lib/_asr_worker.py，pid \(p.processIdentifier)，nice 10）")
        } catch {
            log.line("⚠ 增量轉錄啟動失敗（\(error.localizedDescription)），停止後照整檔轉錄")
        }
        try? out?.close()
    }
}

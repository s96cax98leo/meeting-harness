// Capture/FinalizeRunner.swift —— 錄製實例的收尾執行器（spec §4.28.6；design R3-D3「總上限與取消」）
//
// 以 Process 啟動 `_record_finalize.py <場次>`，輸出逐行寫進 record.log（spec §4.28.8 的耗時行也走這條）。
// 總期限＝Core 的 finalizeDeadline(recordedSeconds:)（錄製長度扣暫停 × 3 ＋ 600 秒，D14a-A）。
// 逾時或取消（收尾中再收到一次 SIGTERM）時：只對 Python 程序送 SIGTERM（它會先 SIGKILL 自己的子程序群組、
// 再以結束碼 5 退出，r3-finalize-guard），寬限 5 秒後仍在就 SIGKILL。這裡不 killpg、不碰 ffmpeg。

import Foundation

/// 收尾被中止的原因。
enum FinalizeAbort: Equatable {
    case timedOut(seconds: Double)
    case cancelled
}

/// FinalizeRunner.run 的結果。
enum FinalizeRunResult: Equatable {
    case exited(Int32)            // 子程序自行結束（含啟動失敗的 126／127）
    case aborted(FinalizeAbort)   // 逾時或取消；子程序已送過 SIGTERM（必要時 SIGKILL）
}

/// 中止時寫進 record.status.json 的結果：phase=failed、code=5；message 含「收尾逾時」或「收尾已取消」與重跑指令。
/// 停止原因（forcedMessage）照 completionOutcome 的慣例放在開頭。
func finalizeAbortOutcome(_ reason: FinalizeAbort, forcedMessage: String?, sessionPath: String) -> CompletionOutcome {
    let prefix = forcedMessage.map { $0 + "；" } ?? ""
    let what: String
    switch reason {
    case .timedOut(let seconds): what = "收尾逾時（超過 \(Int(seconds.rounded())) 秒）"
    case .cancelled: what = "收尾已取消"
    }
    return CompletionOutcome(phase: .failed, code: 5,
                             message: prefix + what + "，段落保留，可用 meeting record finish \(sessionPath) 重跑")
}

final class FinalizeRunner {
    /// SIGTERM 之後等多久才 SIGKILL（spec §4.28.6）。
    static let killGraceSeconds: Double = 5

    let deadlineSeconds: Double
    private let log: Logger
    private let lock = NSLock()
    private var process: Process?
    private var abortReason: FinalizeAbort?
    private var finished = false
    private var cancelRequested = false

    init(recordedSeconds: Double, log: Logger) {
        self.deadlineSeconds = finalizeDeadline(recordedSeconds: recordedSeconds)
        self.log = log
    }

    /// 收尾中再收到 SIGTERM：轉成取消。可從任何執行緒呼叫；還沒啟動就記下，啟動後立刻中止；已結束則不做事。
    func cancel() {
        lock.lock()
        let done = finished
        cancelRequested = true
        lock.unlock()
        if done { return }
        abort(.cancelled)
    }

    /// 是否已收到取消（spec R3x §3.22、§3.23 第 9 步）：背景收尾排隊時每一輪先看它，為 true 就不再等、不啟動收尾子程序。
    var isCancelRequested: Bool {
        lock.lock()
        defer { lock.unlock() }
        return cancelRequested
    }

    /// 同步執行（不得在錄製實例的 q 上呼叫）。
    func run(executable: URL, arguments: [String], environment: [String: String]) -> FinalizeRunResult {
        let p = Process()
        p.executableURL = executable
        p.arguments = arguments
        p.environment = environment
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        let exited = DispatchSemaphore(value: 0)
        p.terminationHandler = { _ in exited.signal() }

        lock.lock()
        do { try p.run() } catch {
            finished = true
            lock.unlock()
            log.line("✗ 啟動收尾失敗：\(error.localizedDescription)")
            return .exited(126)
        }
        process = p
        let cancelEarly = cancelRequested
        lock.unlock()
        log.line("● 收尾總期限 \(Int(deadlineSeconds.rounded())) 秒")

        // 讀輸出放在另一條執行緒：子程序被 SIGKILL 時，留下來的孫程序可能還握著管道寫端，不能讓它卡住收尾
        let readerDone = DispatchSemaphore(value: 0)
        let reader = pipe.fileHandleForReading
        let log = self.log
        DispatchQueue.global(qos: .utility).async {
            var buffer = Data()
            while true {
                let chunk = reader.availableData
                if chunk.isEmpty { break }
                buffer.append(chunk)
                while let nl = buffer.firstIndex(of: 0x0A) {
                    log.line("  " + String(decoding: buffer[buffer.startIndex..<nl], as: UTF8.self))
                    buffer.removeSubrange(buffer.startIndex...nl)
                }
            }
            if !buffer.isEmpty { log.line("  " + String(decoding: buffer, as: UTF8.self)) }
            readerDone.signal()
        }

        if cancelEarly { abort(.cancelled) }
        if exited.wait(timeout: .now() + deadlineSeconds) == .timedOut {
            abort(.timedOut(seconds: deadlineSeconds))
            exited.wait()
        }
        // 正常結束時管道已到 EOF；被中止時最多再等 2 秒把剩下的輸出寫進 record.log
        if readerDone.wait(timeout: .now() + 2) == .timedOut {
            log.line("⚠ 收尾子程序的輸出管道 2 秒內沒有關閉，不再等待")
        }

        lock.lock()
        finished = true
        let reason = abortReason
        lock.unlock()
        if let reason { return .aborted(reason) }
        return .exited(p.terminationStatus)
    }

    /// 對 Python 程序送 SIGTERM，寬限 killGraceSeconds 秒後仍在就 SIGKILL。只做第一次。
    private func abort(_ reason: FinalizeAbort) {
        lock.lock()
        guard abortReason == nil, !finished, let p = process, p.isRunning else {
            lock.unlock()
            return
        }
        abortReason = reason
        let pid = p.processIdentifier
        lock.unlock()

        switch reason {
        case .timedOut(let s): log.line("✗ 收尾逾時（超過 \(Int(s.rounded())) 秒），對收尾程序（pid \(pid)）送 SIGTERM")
        case .cancelled: log.line("● 收尾已取消，對收尾程序（pid \(pid)）送 SIGTERM")
        }
        kill(pid, SIGTERM)
        DispatchQueue.global(qos: .userInitiated).asyncAfter(deadline: .now() + FinalizeRunner.killGraceSeconds) { [log] in
            guard p.isRunning else { return }
            log.line("✗ 收尾程序 \(Int(FinalizeRunner.killGraceSeconds)) 秒內沒有結束，送 SIGKILL")
            kill(pid, SIGKILL)
        }
    }
}

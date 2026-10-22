// Capture/PreflightRunner.swift —— preflight 13 項的實際檢查（design §6；spec §4.2）
// 分級與結束碼的規則在 Core/Preflight.swift；這裡只負責量測並寫出 PreflightResult（含補救步驟）。
import AVFoundation
import CoreGraphics
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

/// preflight／start 共用的執行參數（spec §3.5）。
struct RunContext {
    let home: URL
    let runId: String
    let session: URL
    let minFreeBytes: Int64
    let windowRef: WindowRef
    let harness: String?
    let log: Logger
    /// 內部旗標 --skip-finalize（只給 app 的首次引導試錄用；spec R3-§6 第 144 條）：停止後不跑收尾、不發完成通知
    var skipFinalize = false

    var statusURL: URL { home.appendingPathComponent("record.status.json") }
    var pidURL: URL { home.appendingPathComponent("record.pid") }
    var defaultsURL: URL { home.appendingPathComponent("record.defaults.json") }
    var recordingDir: URL { session.appendingPathComponent("錄音", isDirectory: true) }
    var tracksDir: URL { recordingDir.appendingPathComponent("tracks", isDirectory: true) }
}

/// 本程序持有的 <home>/record.lock fd（spec §3.15）：取到後持有到程序結束，不主動 close。
var recordLockFD: Int32?

/// record.status.json 的寫者：tmp＋rename 原子寫入；呼叫端自行序列化。
final class StatusWriter {
    let url: URL
    private(set) var status: RecordStatus
    private let lock = NSLock()

    init(ctx: RunContext) {
        url = ctx.statusURL
        let now = isoNow()
        status = RecordStatus(schemaVersion: 1, runId: ctx.runId, pid: getpid(), phase: .preflight, code: 0,
                              message: "", session: ctx.session.path, startedAt: now, updatedAt: now,
                              segments: 0, preflight: [], warnings: [])
    }

    /// 進背景收尾之後的 home（spec R3x §3.24）；nil＝還沒進背景，照 R3 無條件寫共用狀態檔。
    private var backgroundHome: URL?

    /// 進背景收尾（spec R3x §3.23 第 3 步）：之後每次 update 一定寫每場狀態檔，共用狀態檔改為條件式寫入。
    func enterBackground(home: URL) {
        lock.lock(); defer { lock.unlock() }
        backgroundHome = home
    }

    func update(_ change: (inout RecordStatus) -> Void) {
        lock.lock(); defer { lock.unlock() }
        change(&status)
        status.updatedAt = isoNow()
        guard let home = backgroundHome else {
            try? writeJSONAtomically(status, to: url)
            return
        }
        // §3.24 第 1 點：每場狀態檔一定寫（background: true）
        var own = status
        own.background = true
        try? writeJSONAtomically(own, to: backgroundStatusURL(home: home, runId: status.runId))
        writeSharedIfOwned(home: home)
    }

    /// §3.24 第 2 點：仍持有 record.lock → 直接寫；否則短暫取鎖（1 秒重試），
    /// 共用狀態檔不存在或 runId 還是自己（sharedStatusWritable）才寫，寫完立刻放鎖。取不到鎖就不寫。
    private func writeSharedIfOwned(home: URL) {
        if recordLockFD != nil {
            try? writeJSONAtomically(status, to: url)
            return
        }
        switch acquireRecordLock(home: home, retrySeconds: 1.0) {
        case .acquired(let fd):
            if sharedStatusWritable(lockAcquired: true, current: readStatus(url), runId: status.runId) {
                try? writeJSONAtomically(status, to: url)
            }
            close(fd)
        case .heldByOther, .unavailable:
            break
        }
    }
}

/// 本程序持有的每場鎖 <home>/finalizing/<runId>.lock fd（spec R3x §3.22、§3.23 第 2 步）：
/// 進背景收尾時取得，持有到程序結束（O_CLOEXEC，收尾子程序不繼承）；nil＝不在背景路徑。
var backgroundLockFD: Int32?

let audioExtensions: Set<String> = ["m4a", "mp3", "wav", "mov", "mp4", "m4v"]

struct PreflightOutcome {
    let results: [PreflightResult]
    let content: SCShareableContent?
    let window: SCWindow?
    let resolution: WindowResolution
    /// 幕前調度提醒（spec §4.2.12）；沒開或讀不到為 nil。start／quick-start 開錄時寫一行進 record.log。
    let stageManagerNotice: String?
    var code: Int32 { exitCode(for: results) }
}

enum PreflightRunner {
    /// 13 項依序檢查（順序照舊：有副作用的權限詢問、鎖與 probe stream 的先後不變）；各項的量測與訊息在下列 check*／measureAudio
    /// （個別檢查在 PreflightChecks.swift；meeting-speed spec §4.13.1 拆出，行為不變）。
    static func run(_ ctx: RunContext) async -> PreflightOutcome {
        var r: PreflightResults = [:]

        // 1 簽章身分（warn）
        let (signOK, signMsg) = checkSigning(home: ctx.home, log: ctx.log)
        r.set(.signing, signOK, signMsg)

        // 2、3 螢幕錄製權限／剛授權要重啟（hard 4，兩者訊息不同，PROBE-REPORT.md:51-53）
        let preflightAccess = CGPreflightScreenCaptureAccess()
        var content: SCShareableContent?
        do { content = try await shareableContent() } catch { content = nil }
        checkScreenPermission(preflightAccess: preflightAccess, contentAvailable: content != nil, into: &r)

        // 4 麥克風權限（hard 4）
        await checkMicPermission(into: &r)

        // 8 目標視窗存在（hard 3）：windowID 優先，找不到才以 (bundleID, 標題) 唯一認回（spec §3.8.8）
        let (resolution, window) = checkWindow(ctx, content: content, into: &r)

        // 9 場次撞名（hard 2）
        if sessionCollides(ctx) {
            r.set(.session_collision, false, "場次已存在（錄音/ 已有音源檔或 tracks/）：換一個場次名")
        } else {
            r.set(.session_collision, true, "")
        }

        // 7 磁碟空間（含目標目錄可寫，hard 4）
        let (diskOK, diskMsg) = checkDisk(ctx)
        r.set(.disk, diskOK, diskMsg)

        // 10 電源（warn）
        let (powerOK, powerMsg) = checkPower(log: ctx.log)
        r.set(.power, powerOK, powerMsg)

        // 11 已有錄製在跑（hard 2）
        checkAlreadyRunning(ctx, into: &r)

        // 13 Apple Events（warn，永不 hard；不跳授權框）
        await checkAppleEvents(into: &r)

        // 5、6、12 以 3 秒 probe stream 量測（與正式錄製同一組音訊設定）
        await measureAudio(ctx, content: content, window: window, into: &r)

        // 12（續）幕前調度提醒（spec §4.2.12）
        let stageNotice = applyStageManagerNotice(into: &r)

        let results = PreflightItem.allCases.map { r[$0] ?? PreflightResult(item: $0, ok: false, message: "沒有檢查") }
        return PreflightOutcome(results: results, content: content, window: window, resolution: resolution,
                                stageManagerNotice: stageNotice)
    }

    /// 11 已有錄製在跑（hard 2）：以 record.lock 為準（spec §3.15、§4.26.2）。呼叫端應已持有；
    /// 沒有（例如日後新的進入點忘了取）就在這裡補取，被持有即判失敗。record.pid 的檢查照舊保留。
    static func checkAlreadyRunning(_ ctx: RunContext, into r: inout PreflightResults) {
        var lockHeldByOther = false
        if recordLockFD == nil {
            switch acquireRecordLock(home: ctx.home) {
            case .acquired(let fd): recordLockFD = fd
            case .heldByOther: lockHeldByOther = true
            case .unavailable: break
            }
        }
        if lockHeldByOther {
            r.set(.already_running, false, "已有錄製在跑（record.lock 被持有）：先 meeting record stop，或用 meeting record status 確認")
        } else if let pid = readPid(ctx.pidURL), pid != getpid(), pidAlive(pid) {
            r.set(.already_running, false, "已有錄製在跑（pid \(pid)）：先 meeting record stop，或用 meeting record status 確認")
        } else {
            r.set(.already_running, true, "")
        }
    }

    /// 5、6、12 以 3 秒 probe stream 量測（與正式錄製同一組音訊設定）。
    /// 第 5 項兩段式（D19，spec §4.2.5）：(a) 目標視窗、不播測試音；(a) 沒聲音才開 (b) display filter＋afplay 測試音。
    static func measureAudio(_ ctx: RunContext, content: SCShareableContent?, window: SCWindow?,
                             into r: inout PreflightResults) async {
        if let content {
            func peakText(_ v: Double) -> String { v.isFinite ? String(format: "%.1f dBFS", v) : "-∞" }
            let m = await ProbeMeter.measureTarget(content: content, window: window, log: ctx.log)
            // 目標視窗認不到時 (a) 的系統聲音視為 -∞
            let target = window == nil ? -Double.infinity : m.system
            var display: Double?
            if m.opened, !(target > -60) {
                display = await ProbeMeter.measureDisplay(content: content, log: ctx.log)
            }
            // probe stream 開不起來＝音訊裝置無法啟動（meeting-speed spec §4.10.1）：不再誤判成權限沒有生效
            let verdict: AudioProbeVerdict = m.opened
                ? .check(systemAudioCheck(targetPeakDBFS: target, displayPeakDBFS: display, thresholdDBFS: -60))
                : audioProbeVerdict(opened: false, targetPeakDBFS: target, displayPeakDBFS: display, thresholdDBFS: -60)
            switch verdict {
            case .deviceFailed:
                let d = currentDevices()
                r.set(.system_audio_rms, false, audioDeviceFailedMessage(
                    input: d.input?.name ?? "（無）", inputTransport: d.input?.transport ?? "（無）",
                    output: d.output?.name ?? "（無）", outputTransport: d.output?.transport ?? "（無）"))
            case .check(.pass):
                r.set(.system_audio_rms, true, "系統聲音峰值 \(peakText(target))")
            case .check(.warnTargetSilent):
                r[.system_audio_rms] = PreflightResult(
                    item: .system_audio_rms, ok: false,
                    message: "會議 app 目前沒有聲音（會議視窗峰值 \(peakText(target))）；系統聲音擷取權限正常（測試音 \(peakText(display ?? -.infinity))）。開錄後若持續 15 秒沒有聲音會告警",
                    warnOnly: true)
            case .check(.fail):
                r.set(.system_audio_rms, false, "3 秒內系統聲音的峰值都低於 -60 dBFS（會議視窗 \(peakText(target))、測試音 \(peakText(display ?? -.infinity))）：系統聲音擷取權限沒有生效。請到 系統設定 › 隱私權與安全性 › 螢幕與系統錄音 重新授權螢幕錄製給 MeetingRecorder；若剛授權，請完全結束 MeetingRecorder 再重開")
            }
            if verdict == .deviceFailed {
                r.set(.mic_rms, true, deviceFailedSkipMessage)
            } else if m.mic > -60 {
                r.set(.mic_rms, true, "麥克風峰值 \(peakText(m.mic))")
            } else {
                // t7（§6 第 102 條）：開會時按下開錄的那 3 秒不一定有人說話——只提醒、照常開錄，錄製中 15 秒靜音告警兜底
                r[.mic_rms] = PreflightResult(
                    item: .mic_rms, ok: false,
                    message: "麥克風目前很安靜（3 秒內峰值 \(peakText(m.mic))，低於 -60 dBFS）：照常開錄；開錄後若持續 15 秒沒有聲音會告警。確認麥克風沒被拔掉或靜音",
                    warnOnly: true)
            }
            if window == nil {
                r.set(.window_minimized, true, "（目標視窗不存在，略過）")
            } else if verdict == .deviceFailed {
                r.set(.window_minimized, true, deviceFailedSkipMessage)
            } else if m.screenFrames == 0 || m.nonSuspendedFrames == 0 {
                r.set(.window_minimized, false, minimizedMessage)
            } else {
                r.set(.window_minimized, true, "")
            }
        } else {
            r.set(.system_audio_rms, false, "螢幕錄製權限沒生效，無法量測系統聲音：先處理螢幕錄製權限")
            r.set(.mic_rms, false, "螢幕錄製權限沒生效，無法量測麥克風：先處理螢幕錄製權限")
            r.set(.window_minimized, true, "（取不到視窗，略過）")
        }
    }

    /// probe stream 開不起來時第 6、12 項的訊息（meeting-speed spec §4.10.1）：略過，不當成失敗
    static let deviceFailedSkipMessage = "略過（音訊裝置無法啟動）"

    static let minimizedMessage = "會議視窗可能被最小化（3 秒內沒有畫面或只收到暫停狀態）：把它還原，最小化期間錄不到畫面"

    /// 每次都讀當下的值（spec §4.5.9，缺陷 L）：以路徑新建 URL 並清掉快取，不沿用同一個 URL 物件的 resourceValues。
    static func availableBytes(_ url: URL) -> Int64? {
        var fresh = URL(fileURLWithPath: existingAncestor(url).path)
        fresh.removeAllCachedResourceValues()
        let v = try? fresh.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey,
                                                                    .volumeAvailableCapacityKey])
        if let n = v?.volumeAvailableCapacityForImportantUsage, n > 0 { return n }
        return v?.volumeAvailableCapacity.map { Int64($0) }
    }
}

/// 3 秒 probe stream：系統聲音、麥克風各自收斂成 0.5 秒時段峰值；同時看視窗有沒有畫面（design §6 第 5、6、12 項）。
final class ProbeMeter: NSObject, SCStreamOutput, SCStreamDelegate {
    struct Result {
        let system: Double; let mic: Double; let screenFrames: Int; let nonSuspendedFrames: Int
        var opened = true
    }

    private let lock = NSLock()
    private let t0 = CMClockGetTime(CMClockGetHostTimeClock()).seconds
    private var sys = PeakWindow(windowSeconds: 0.5)
    private var mic = PeakWindow(windowSeconds: 0.5)
    private var screenFrames = 0
    private var nonSuspended = 0

    private func time(_ sb: CMSampleBuffer) -> Double {
        let pts = CMSampleBufferGetPresentationTimeStamp(sb)
        let now = CMClockGetTime(CMClockGetHostTimeClock()).seconds
        return (pts.isValid ? pts.seconds : now) - t0
    }

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        switch type {
        case .screen:
            let st = frameStatusKind(sb)
            lock.lock(); screenFrames += 1; if st != .suspended { nonSuspended += 1 }; lock.unlock()
        case .audio:
            guard let db = rmsDBFS(sampleBuffer: sb) else { return }
            let t = time(sb)
            lock.lock(); sys.feed(t: max(0, t), dbfs: db); lock.unlock()
        case .microphone:
            guard let db = rmsDBFS(sampleBuffer: sb) else { return }
            let t = time(sb)
            lock.lock(); mic.feed(t: max(0, t), dbfs: db); lock.unlock()
        @unknown default:
            break
        }
    }

    /// (a) 目標視窗的 probe stream（第 5、6、12 項共用）：**不播測試音**（spec §4.2.5 (a)）。
    /// 目標視窗認不到時改用整個顯示器量麥克風（第 5 項的 (a) 由呼叫端視為 -∞）。
    static func measureTarget(content: SCShareableContent, window: SCWindow?, log: Logger) async -> Result {
        let filter: SCContentFilter
        if let window {
            filter = SCContentFilter(desktopIndependentWindow: window)
        } else if let d = content.displays.first {
            filter = SCContentFilter(display: d, excludingWindows: [])
        } else {
            return silentResult
        }
        return await capture(filter: filter, log: log, during: nil)
    }

    /// (b) 系統聲音擷取權限：整個顯示器的 probe stream，期間由子程序 afplay 播測試音兩次，回系統聲音峰值。
    /// 沒有顯示器或 stream 開不起來回 nil（systemAudioCheck 視為 (b) 沒跑成）。
    static func measureDisplay(content: SCShareableContent, log: Logger) async -> Double? {
        guard let d = content.displays.first else { return nil }
        let filter = SCContentFilter(display: d, excludingWindows: [])
        let r = await capture(filter: filter, log: log) {
            // 系統聲音的測試音由子程序 afplay 播放（excludesCurrentProcessAudio=true 下錄得到，d2:19）
            for delay in [0.3, 1.6] {
                DispatchQueue.global().asyncAfter(deadline: .now() + delay) { playTestSound() }
            }
        }
        return r.opened ? r.system : nil
    }

    private static let silentResult = Result(system: -.infinity, mic: -.infinity, screenFrames: 0, nonSuspendedFrames: 0)

    /// 開一條 3 秒的 probe stream（與正式錄製同一組音訊設定）；during 在 startCapture 成功後呼叫。
    private static func capture(filter: SCContentFilter, log: Logger, during: (() -> Void)?) async -> Result {
        let meter = ProbeMeter()
        let cfg = SCStreamConfiguration()
        cfg.width = 640
        cfg.height = 360
        cfg.scalesToFit = true
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 10)
        cfg.capturesAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        cfg.captureMicrophone = true
        cfg.excludesCurrentProcessAudio = true
        let stream = SCStream(filter: filter, configuration: cfg, delegate: meter)
        let q = DispatchQueue(label: "mh.preflight.probe")
        do {
            try stream.addStreamOutput(meter, type: .screen, sampleHandlerQueue: q)
            try stream.addStreamOutput(meter, type: .audio, sampleHandlerQueue: q)
            try stream.addStreamOutput(meter, type: .microphone, sampleHandlerQueue: q)
            try await stream.startCapture()
        } catch {
            log.line("⚠ preflight probe stream 開不起來：\(error.localizedDescription)")
            return Result(system: -.infinity, mic: -.infinity, screenFrames: 0, nonSuspendedFrames: 0, opened: false)
        }
        during?()
        try? await Task.sleep(nanoseconds: 3_200_000_000)
        try? await stream.stopCapture()
        return meter.result(upTo: 3.0)
    }

    private func result(upTo t: Double) -> Result {
        lock.lock(); defer { lock.unlock() }
        let sysPeak = sys.close(upTo: t).max() ?? -.infinity
        let micPeak = mic.close(upTo: t).max() ?? -.infinity
        return Result(system: sysPeak, mic: micPeak, screenFrames: screenFrames, nonSuspendedFrames: nonSuspended)
    }
}

func playTestSound() {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: "/usr/bin/afplay")
    p.arguments = ["/System/Library/Sounds/Ping.aiff"]
    try? p.run()
}

func frameStatusKind(_ sb: CMSampleBuffer) -> FrameStatusKind? {
    guard let arr = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
          let raw = arr.first?[.status] as? Int,
          let s = SCFrameStatus(rawValue: raw) else { return nil }
    switch s {
    case .complete: return .complete
    case .idle: return .idle
    case .blank: return .blank
    case .suspended: return .suspended
    case .started: return .started
    case .stopped: return .stopped
    @unknown default: return nil
    }
}

/// CVPixelBuffer 的鎖定與取 plane 0（Y）留在 Capture/，判定交給 Core 的 nonBlackRatio。
func lumaNonBlackRatio(_ sb: CMSampleBuffer) -> Double? {
    guard let px = sb.imageBuffer else { return nil }
    guard CVPixelBufferLockBaseAddress(px, .readOnly) == kCVReturnSuccess else { return nil }
    defer { CVPixelBufferUnlockBaseAddress(px, .readOnly) }
    guard CVPixelBufferIsPlanar(px), let base = CVPixelBufferGetBaseAddressOfPlane(px, 0) else { return nil }
    let w = CVPixelBufferGetWidthOfPlane(px, 0)
    let h = CVPixelBufferGetHeightOfPlane(px, 0)
    let bpr = CVPixelBufferGetBytesPerRowOfPlane(px, 0)
    let buf = UnsafeBufferPointer(start: base.assumingMemoryBound(to: UInt8.self), count: bpr * h)
    return nonBlackRatio(lumaPlane: buf, width: w, height: h, bytesPerRow: bpr)
}

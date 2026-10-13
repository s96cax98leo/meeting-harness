// Capture/PreflightRunner.swift —— preflight 13 項的實際檢查（design §6；spec §4.2）
// 分級與結束碼的規則在 Core/Preflight.swift；這裡只負責量測並寫出 PreflightResult（含補救步驟）。
import AVFoundation
import CoreGraphics
import CoreMedia
import Foundation
import IOKit.ps
@preconcurrency import ScreenCaptureKit
import Security

/// preflight／start 共用的執行參數（spec §3.5）。
struct RunContext {
    let home: URL
    let runId: String
    let session: URL
    let minFreeBytes: Int64
    let windowRef: WindowRef
    let harness: String?
    let log: Logger

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

    func update(_ change: (inout RecordStatus) -> Void) {
        lock.lock(); defer { lock.unlock() }
        change(&status)
        status.updatedAt = isoNow()
        try? writeJSONAtomically(status, to: url)
    }
}

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
    static func run(_ ctx: RunContext) async -> PreflightOutcome {
        var r: [PreflightItem: PreflightResult] = [:]
        func set(_ item: PreflightItem, _ ok: Bool, _ msg: String) { r[item] = PreflightResult(item: item, ok: ok, message: msg) }

        // 1 簽章身分（warn）
        let (signOK, signMsg) = checkSigning(home: ctx.home)
        set(.signing, signOK, signMsg)

        // 2、3 螢幕錄製權限／剛授權要重啟（hard 4，兩者訊息不同，PROBE-REPORT.md:51-53）
        let preflightAccess = CGPreflightScreenCaptureAccess()
        var content: SCShareableContent?
        do { content = try await shareableContent() } catch { content = nil }
        if !preflightAccess && content == nil {
            set(.screen_permission, false, """
                沒有螢幕錄製權限。到 系統設定 › 隱私權與安全性 › 螢幕與系統錄音 打開 MeetingRecorder \
                （open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"），\
                然後完全結束 MeetingRecorder 再重開
                """)
            set(.relaunch_needed, true, "（螢幕錄製權限還沒給，先處理上一項）")
        } else if content == nil {
            set(.screen_permission, true, "螢幕錄製已授權")
            set(.relaunch_needed, false, "螢幕錄製已授權但還沒生效：請完全結束 MeetingRecorder 再重開（授權對已啟動的程式不生效）")
        } else {
            set(.screen_permission, true, "螢幕錄製已授權")
            set(.relaunch_needed, true, "")
        }

        // 4 麥克風權限（hard 4）
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            set(.mic_permission, true, "麥克風已授權")
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            if granted {
                set(.mic_permission, true, "麥克風已授權")
            } else {
                set(.mic_permission, false, "麥克風沒有授權：到 系統設定 › 隱私權與安全性 › 麥克風 打開 MeetingRecorder，然後完全結束 MeetingRecorder 再重開")
            }
        default:
            set(.mic_permission, false, "沒有麥克風權限：到 系統設定 › 隱私權與安全性 › 麥克風 打開 MeetingRecorder，然後完全結束 MeetingRecorder 再重開")
        }

        // 8 目標視窗存在（hard 3）：windowID 優先，找不到才以 (bundleID, 標題) 唯一認回（spec §3.8.8）
        var resolution: WindowResolution = .notFound
        var window: SCWindow?
        if let content {
            resolution = resolveWindow(ctx.windowRef, in: windowCandidates(content))
            switch resolution {
            case .exact(let id):
                window = content.windows.first { $0.windowID == id }
                set(.window_exists, true, "視窗 \(id) 存在")
            case .reidentified(let id):
                window = content.windows.first { $0.windowID == id }
                set(.window_exists, true, "視窗 ID 已由 \(ctx.windowRef.windowID) 變為 \(id)，以 app 與標題認回")
            case .notFound:
                set(.window_exists, false, "找不到視窗 \(ctx.windowRef.windowID)：會議視窗被關掉或換了 ID，請重新跑 meeting record 選一次")
            case .ambiguous:
                set(.window_exists, false, "有多個同 app、同標題的視窗，請重新用 meeting record 選")
            }
        } else {
            set(.window_exists, false, "取不到視窗清單（螢幕錄製權限），無法確認視窗 \(ctx.windowRef.windowID)")
        }

        // 9 場次撞名（hard 2）
        if sessionCollides(ctx) {
            set(.session_collision, false, "場次已存在（錄音/ 已有音源檔或 tracks/）：換一個場次名")
        } else {
            set(.session_collision, true, "")
        }

        // 7 磁碟空間（含目標目錄可寫，hard 4）
        let (diskOK, diskMsg) = checkDisk(ctx)
        set(.disk, diskOK, diskMsg)

        // 10 電源（warn）
        let (powerOK, powerMsg) = checkPower()
        set(.power, powerOK, powerMsg)

        // 11 已有錄製在跑（hard 2）：以 record.lock 為準（spec §3.15、§4.26.2）。呼叫端應已持有；
        // 沒有（例如日後新的進入點忘了取）就在這裡補取，被持有即判失敗。record.pid 的檢查照舊保留。
        var lockHeldByOther = false
        if recordLockFD == nil {
            switch acquireRecordLock(home: ctx.home) {
            case .acquired(let fd): recordLockFD = fd
            case .heldByOther: lockHeldByOther = true
            case .unavailable: break
            }
        }
        if lockHeldByOther {
            set(.already_running, false, "已有錄製在跑（record.lock 被持有）：先 meeting record stop，或用 meeting record status 確認")
        } else if let pid = readPid(ctx.pidURL), pid != getpid(), pidAlive(pid) {
            set(.already_running, false, "已有錄製在跑（pid \(pid)）：先 meeting record stop，或用 meeting record status 確認")
        } else {
            set(.already_running, true, "")
        }

        // 13 Apple Events（warn，永不 hard；不跳授權框）
        let ae = await chromeAutomationStatus(askUserIfNeeded: false)
        if ae == .authorized {
            set(.apple_events, true, "Chrome 會議分頁標記可用（Apple Events 已授權）")
        } else {
            let why: String
            switch ae {
            case .chromeNotRunning: why = "Chrome 沒有開"
            case .notAuthorized: why = "沒有允許 MeetingRecorder 控制 Google Chrome"
            case .notDetermined: why = "還沒決定是否允許 MeetingRecorder 控制 Google Chrome"
            default: why = "查不到 Apple Events 狀態"
            }
            set(.apple_events, false, "會議分頁不會標記，不影響錄製（\(why)）。要開啟：系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome")
        }

        // 5、6、12 以 3 秒 probe stream 量測（與正式錄製同一組音訊設定）
        // 第 5 項兩段式（D19，spec §4.2.5）：(a) 目標視窗、不播測試音；(a) 沒聲音才開 (b) display filter＋afplay 測試音。
        if let content {
            func peakText(_ v: Double) -> String { v.isFinite ? String(format: "%.1f dBFS", v) : "-∞" }
            let m = await ProbeMeter.measureTarget(content: content, window: window, log: ctx.log)
            // 目標視窗認不到時 (a) 的系統聲音視為 -∞
            let target = window == nil ? -Double.infinity : m.system
            var display: Double?
            if !(target > -60) {
                display = await ProbeMeter.measureDisplay(content: content, log: ctx.log)
            }
            switch systemAudioCheck(targetPeakDBFS: target, displayPeakDBFS: display, thresholdDBFS: -60) {
            case .pass:
                set(.system_audio_rms, true, "系統聲音峰值 \(peakText(target))")
            case .warnTargetSilent:
                r[.system_audio_rms] = PreflightResult(
                    item: .system_audio_rms, ok: false,
                    message: "會議 app 目前沒有聲音（會議視窗峰值 \(peakText(target))）；系統聲音擷取權限正常（測試音 \(peakText(display ?? -.infinity))）。開錄後若持續 15 秒沒有聲音會告警",
                    warnOnly: true)
            case .fail:
                set(.system_audio_rms, false, "3 秒內系統聲音的峰值都低於 -60 dBFS（會議視窗 \(peakText(target))、測試音 \(peakText(display ?? -.infinity))）：系統聲音擷取權限沒有生效。請到 系統設定 › 隱私權與安全性 › 螢幕與系統錄音 重新授權螢幕錄製給 MeetingRecorder；若剛授權，請完全結束 MeetingRecorder 再重開")
            }
            if m.mic > -60 {
                set(.mic_rms, true, "麥克風峰值 \(peakText(m.mic))")
            } else {
                // t7（§6 第 102 條）：開會時按下開錄的那 3 秒不一定有人說話——只提醒、照常開錄，錄製中 15 秒靜音告警兜底
                r[.mic_rms] = PreflightResult(
                    item: .mic_rms, ok: false,
                    message: "麥克風目前很安靜（3 秒內峰值 \(peakText(m.mic))，低於 -60 dBFS）：照常開錄；開錄後若持續 15 秒沒有聲音會告警。確認麥克風沒被拔掉或靜音",
                    warnOnly: true)
            }
            if window == nil {
                set(.window_minimized, true, "（目標視窗不存在，略過）")
            } else if m.screenFrames == 0 || m.nonSuspendedFrames == 0 {
                set(.window_minimized, false, minimizedMessage)
            } else {
                set(.window_minimized, true, "")
            }
        } else {
            set(.system_audio_rms, false, "螢幕錄製權限沒生效，無法量測系統聲音：先處理螢幕錄製權限")
            set(.mic_rms, false, "螢幕錄製權限沒生效，無法量測麥克風：先處理螢幕錄製權限")
            set(.window_minimized, true, "（取不到視窗，略過）")
        }

        // 12（續）幕前調度提醒（spec §4.2.12）：只讀設定；開啟 → 同一項 warn，與「疑似最小化」並列時以「；」串接
        let stageNotice = stageManagerNotice(globallyEnabled: stageManagerGloballyEnabled())
        if let stageNotice, let cur = r[.window_minimized] {
            let parts = (cur.ok ? [] : [cur.message]) + [stageNotice]
            set(.window_minimized, false, parts.joined(separator: "；"))
        }

        let results = PreflightItem.allCases.map { r[$0] ?? PreflightResult(item: $0, ok: false, message: "沒有檢查") }
        return PreflightOutcome(results: results, content: content, window: window, resolution: resolution,
                                stageManagerNotice: stageNotice)
    }

    static let minimizedMessage = "會議視窗可能被最小化（3 秒內沒有畫面或只收到暫停狀態）：把它還原，最小化期間錄不到畫面"

    /// 幕前調度是否開啟（spec §4.2.12）：只讀 com.apple.WindowManager 的 GloballyEnabled，不觸發任何授權框、不改設定。
    /// 讀不到或型別不對回 nil。
    static func stageManagerGloballyEnabled() -> Bool? {
        guard let v = CFPreferencesCopyAppValue("GloballyEnabled" as CFString, "com.apple.WindowManager" as CFString) else {
            return nil
        }
        if let b = v as? Bool { return b }
        if let n = v as? NSNumber { return n.boolValue }
        return nil
    }

    // MARK: - 個別檢查

    static func checkSigning(home: URL) -> (Bool, String) {
        var code: SecCode?
        var staticCode: SecStaticCode?
        var info: CFDictionary?
        guard SecCodeCopySelf([], &code) == errSecSuccess, let code,
              SecCodeCopyStaticCode(code, [], &staticCode) == errSecSuccess, let staticCode,
              SecCodeCopySigningInformation(staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let dict = info as? [String: Any] else {
            return (false, "讀不到自己的簽章資訊；若擷取失敗，到系統設定重新授權螢幕錄製與麥克風")
        }
        let certs = dict[kSecCodeInfoCertificates as String] as? [SecCertificate] ?? []
        let cdhash = (dict[kSecCodeInfoUnique as String] as? Data)?.map { String(format: "%02x", $0) }.joined() ?? ""
        let store = home.appendingPathComponent("record.cdhash")
        let previous = (try? String(contentsOf: store, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines)
        if !cdhash.isEmpty {
            try? FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
            try? cdhash.write(to: store, atomically: true, encoding: .utf8)
        }
        if certs.isEmpty {
            return (false, "app 是 ad-hoc 簽章，每次重建授權都可能失效；建議建立「MeetingHarness Dev」簽章身分後重跑 build.sh")
        }
        if let previous, !previous.isEmpty, previous != cdhash {
            return (false, "app 重建過（簽章指紋與上次不同）；若擷取失敗，到系統設定重新授權螢幕錄製與麥克風")
        }
        let name = SecCertificateCopySubjectSummary(certs[0]).map { $0 as String } ?? "固定身分"
        return (true, "簽章身分：\(name)")
    }

    static func sessionCollides(_ ctx: RunContext) -> Bool {
        let fm = FileManager.default
        if fm.fileExists(atPath: ctx.tracksDir.path) { return true }
        let items = (try? fm.contentsOfDirectory(atPath: ctx.recordingDir.path)) ?? []
        return items.contains { !$0.hasPrefix(".") && audioExtensions.contains(($0 as NSString).pathExtension.lowercased()) }
    }

    /// 最近一個已存在的上層目錄（場次目錄在 preflight 時可能還沒建立）。
    static func existingAncestor(_ url: URL) -> URL {
        var u = url
        while !FileManager.default.fileExists(atPath: u.path), u.path != "/" { u = u.deletingLastPathComponent() }
        return u
    }

    /// 每次都讀當下的值（spec §4.5.9，缺陷 L）：以路徑新建 URL 並清掉快取，不沿用同一個 URL 物件的 resourceValues。
    static func availableBytes(_ url: URL) -> Int64? {
        var fresh = URL(fileURLWithPath: existingAncestor(url).path)
        fresh.removeAllCachedResourceValues()
        let v = try? fresh.resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey,
                                                                    .volumeAvailableCapacityKey])
        if let n = v?.volumeAvailableCapacityForImportantUsage, n > 0 { return n }
        return v?.volumeAvailableCapacity.map { Int64($0) }
    }

    static func checkDisk(_ ctx: RunContext) -> (Bool, String) {
        let gb = { (b: Int64) in String(format: "%.1f GB", Double(b) / 1e9) }
        guard let avail = availableBytes(ctx.session) else {
            return (false, "讀不到目標磁碟的可用空間：確認根目錄存在")
        }
        if avail < ctx.minFreeBytes {
            return (false, "可用空間 \(gb(avail))，低於需要的 \(gb(ctx.minFreeBytes))：清出空間或換一個根目錄")
        }
        // 可寫探測：在最近的已存在目錄建一個探測檔再刪掉（寫 ~/Documents 底下要「文件」授權，失敗是靜默的）
        let dir = existingAncestor(ctx.tracksDir)
        let probe = dir.appendingPathComponent(".mh-write-probe-\(UUID().uuidString)")
        if FileManager.default.createFile(atPath: probe.path, contents: Data("x".utf8)) {
            try? FileManager.default.removeItem(at: probe)
        } else {
            return (false, "寫不進 \(dir.path)：若在 ~/Documents 底下，到 系統設定 › 隱私權與安全性 › 檔案與檔案夾 給 MeetingRecorder「文件」權限，然後重開")
        }
        return (true, "可用空間 \(gb(avail))（需要 \(gb(ctx.minFreeBytes))）")
    }

    static func checkPower() -> (Bool, String) {
        guard let blob = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let list = IOPSCopyPowerSourcesList(blob)?.takeRetainedValue() as? [CFTypeRef] else { return (true, "") }
        for ps in list {
            guard let d = IOPSGetPowerSourceDescription(blob, ps)?.takeUnretainedValue() as? [String: Any] else { continue }
            let onBattery = (d[kIOPSPowerSourceStateKey] as? String) == kIOPSBatteryPowerValue
            let cur = d[kIOPSCurrentCapacityKey] as? Int ?? 100
            let maxCap = d[kIOPSMaxCapacityKey] as? Int ?? 100
            let pct = maxCap > 0 ? cur * 100 / maxCap : 100
            if onBattery && pct < 20 {
                return (false, "用電池且電量 \(pct)%（低於 20%）：接上電源，長時間錄製與收尾很耗電")
            }
        }
        return (true, "")
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

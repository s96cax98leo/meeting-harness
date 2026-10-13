// Capture/RecordingSession.swift —— 正式錄製：擷取、自管 AVAssetWriter 的 60 秒分段、監看、優雅停止、finalize 觸發
// （design §7.1–§7.6；spec §3.2、§3.3、§4.2.11、§4.3、§4.4、§4.5）
//
// 執行緒：所有可變狀態（含 SegmentWriter）只在序列佇列 q 上讀寫；SCK 的回呼在各自佇列，一律 q.async 回來。
// 時間：
//   - sample 時鐘：SCK sample 的 PTS（host clock）。writer 的 session 時間軸直接用 PTS（design §7.2）。
//   - manifest／levels 的秒數＝PTS 秒數 − t0（t0＝startCapture 前一刻的 host clock），寫檔時取小數 3 位。
//
// R2（spec §4.16.4、§4.17.2、§4.18.2、§4.18.3、§4.19.2、§4.23.3）：
//   - 控制：SIGUSR1 → 在 q 上 readControl → controlActions → 套用（暫停／繼續、麥克風靜音、標記）。
//   - 暫停閘門、換段原因、事件 append、狀態欄位、偵測器餵送一律經 Core 純函式（Segments.swift、Control.swift、
//     Detectors.swift）；本檔只負責呼叫與落盤。
import AVFoundation
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

let segmentSeconds = 60
let diskLowBytes: Int64 = 2_000_000_000     // 2 GB（十進位，spec §6 第 23 條）

/// preflight 最後一條 probe stream 停下後，等這麼久才呼叫正式 startCapture()（design §7.6、spec §4.2.11）。
let startCaptureSettleSeconds: Double = 1.0
/// 正式 startCapture() 第一次失敗後，等這麼久、重建 SCStream 再試一次（design §7.6、spec §4.2.11）。
let startCaptureRetryDelaySeconds: Double = 2.0
/// 影片心跳：靜止畫面（只送 idle）時，距目前段落最後一個視訊 PTS 滿這麼久就重送最後一幀
/// （讓影片軌前進、AVAssetWriter 才寫得出 fragment；design §7.2〈當機〉、spec §4.4.10）。
let videoHeartbeatSeconds: Double = 1.0

func hostSeconds() -> Double { CMClockGetTime(CMClockGetHostTimeClock()).seconds }

// 可變狀態只在序列佇列 q 上讀寫（見檔頭），所以標 @unchecked Sendable。
final class RecordingSession: NSObject, SCStreamOutput, SCStreamDelegate, @unchecked Sendable {
    private let ctx: RunContext
    private let status: StatusWriter
    private let defaults: RecordDefaults?
    private let q = DispatchQueue(label: "mh.rec.state")
    private let screenQ = DispatchQueue(label: "mh.rec.screen")
    private let audioQ = DispatchQueue(label: "mh.rec.audio")
    private let micQ = DispatchQueue(label: "mh.rec.mic")

    private var window: SCWindow
    private var filter: SCContentFilter
    private let cfg = SCStreamConfiguration()
    private var scale: Double
    private var stream: SCStream!
    private var t0 = hostSeconds()

    // 段落（design §7.2）
    private var segIndex = 0
    private var segRow: [Int: Int] = [:]             // 段落 index → manifest.segments 的位置
    private var cur: SegmentWriter?                    // 目前的段落
    private var prev: SegmentWriter?                   // 剛換段、還收 PTS < 邊界 sample 的舊段
    private var prevEnd: CMTime = .invalid             // 舊段的結束點＝新段的起點
    private var closing: [Int: SegmentWriter] = [:]    // 已呼叫 finish、等完成回呼的段落
    private var nextBoundary: CMTime = .invalid
    private var lastSegmentStart: CMTime = .invalid     // 最近一次開段的起點
    private var curSize: PixelSize
    /// 換段當下同步讀會議視窗大小（point）；可替換（design §7.1，spec §4.3.6）。只在 q 上呼叫。
    var windowPointSize: (UInt32) -> CGSize? = cgWindowPointSize
    private var lastFrame: CMSampleBuffer?             // 最後一個 complete 幀（換段時重新打戳）
    private var lastFormatChangePTS: [AudioSource: Double] = [:]
    private var switchOnNextSample = false             // writer 失敗：以下一個 sample 的 PTS 開新段
    private var everOpened = false
    private var finishedSegments = 0
    private var maxEnd: CMTime = .invalid              // 三路已收到的 sample 最晚結束點
    private var firstSampleLogged = false

    // 紀錄
    private var manifest: Manifest
    private var meta: RecordMeta

    // 監看
    private var sysPeak = PeakWindow(windowSeconds: 0.5)
    private var micPeak = PeakWindow(windowSeconds: 0.5)
    private var sysSilence = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    private var micSilence = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    private var black = BlackDetector(ratio: 0.01, seconds: 5)
    private var suspended = SuspendedDetector(seconds: 5)
    private var lastFormat: [AudioSource: AudioFormat] = [:]
    private var lastBlackSample = -10.0      // 只在 screenQ 上讀寫

    // 停止
    private var stopping = false
    private var stopPoint: CMTime?                     // 停止點 E；PTS ≥ E 的 sample 一律不寫
    private var writersDrained = false                 // 已對目前與舊 writer 呼叫收尾
    private var finalizeStarted = false
    private var hadError = false
    private var forced: (code: Int32, message: String)?
    private var timers: [DispatchSourceTimer] = []
    private var levelsTimer: DispatchSourceTimer?
    private var signals: [DispatchSourceSignal] = []
    private var deviceMonitor: AudioDeviceMonitor?

    // R2 控制（spec §3.9–§3.12）。除 micMutedForMicQ 外都只在 q 上讀寫。
    private var controlEnabled = false                 // phase 轉 recording 後才接受控制
    private var applied: RecordControl                 // 已套用的控制狀態（與控制檔比差異）
    private var gate = PauseGate()                     // 暫停閘門（Core/Segments.swift）
    private var micMuted = false
    private var markers: [Marker] = []
    private var lastRecentLevelsWrite = -Double.infinity
    /// 麥克風靜音旗標給 micQ 的 sample 回呼讀（q 寫、micQ 讀，以鎖保護）。
    private let muteLock = NSLock()
    private var micMutedForMicQ = false

    init(ctx: RunContext, status: StatusWriter, window: SCWindow, preflight: [PreflightResult], defaults: RecordDefaults?) {
        self.ctx = ctx
        self.status = status
        self.defaults = defaults
        self.window = window
        self.filter = SCContentFilter(desktopIndependentWindow: window)
        self.scale = Double(filter.pointPixelScale)
        self.curSize = evenPixelSize(points: window.frame.size, scale: Double(filter.pointPixelScale))
        manifest = Manifest(schemaVersion: 1, segmentSeconds: segmentSeconds, segments: [],
                            frameStatus: FrameStatusCounts(complete: 0, idle: 0, blank: 0, suspended: 0, started: 0, stopped: 0),
                            blackIntervals: [], levels: AudioLevels(windowSeconds: 0.5, system: [], mic: []),
                            gapStats: nil, outputCanvas: nil, outputVideoBitrate: nil)
        meta = RecordMeta(schemaVersion: 1,
                          window: WindowInfo(windowID: window.windowID,
                                             app: window.owningApplication?.applicationName ?? "",
                                             bundleID: window.owningApplication?.bundleIdentifier ?? "",
                                             title: window.title ?? ""),
                          config: StreamConfigSnapshot(filter: "", onScreenWindowsOnly: false, scalesToFit: true,
                                                       minimumFrameInterval: "", capturesAudio: true, sampleRate: 0,
                                                       channelCount: 0, captureMicrophone: true,
                                                       microphoneCaptureDeviceID: nil, excludesCurrentProcessAudio: true,
                                                       fileType: "mov", videoCodec: "h264", segmentSeconds: segmentSeconds),
                          devices: currentDevices(), preflight: preflight, deviceEvents: [], audioFormatEvents: [])
        meta.pauseEvents = []          // R2：開錄就寫兩個空陣列（spec §3.11）
        meta.micMuteEvents = []
        applied = freshControl(runId: ctx.runId)
        super.init()
    }

    private var log: Logger { ctx.log }
    private func now() -> Double { hostSeconds() - t0 }
    private var manifestURL: URL { ctx.tracksDir.appendingPathComponent("manifest.json") }
    private var metaURL: URL { ctx.tracksDir.appendingPathComponent("record.meta.json") }
    private var markersURL: URL { ctx.tracksDir.appendingPathComponent("markers.json") }

    // MARK: - 開始

    func start() async {
        do {
            try FileManager.default.createDirectory(at: ctx.tracksDir, withIntermediateDirectories: true)
        } catch {
            fail(code: 5, "建不了 \(ctx.tracksDir.path)：\(error.localizedDescription)")
        }
        installSignalHandlers()
        // 控制檔殘留（上一場暫停中當機等）不得帶進這一場：寫 record.pid 之前重設（spec §4.16.4、design R2-D2）
        do {
            let fresh = try resetControl(home: ctx.home, runId: ctx.runId)
            q.sync { applied = fresh }
        } catch {
            log.line("⚠ 重設 \(controlFileName) 失敗：\(error.localizedDescription)")
        }

        // 畫布＝當下會議視窗的像素大小（D8）
        cfg.width = curSize.width
        cfg.height = curSize.height
        cfg.scalesToFit = true
        cfg.minimumFrameInterval = CMTime(value: 1, timescale: 60)
        cfg.pixelFormat = kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
        cfg.showsCursor = true
        cfg.queueDepth = 8
        cfg.capturesAudio = true
        cfg.sampleRate = 48000
        cfg.channelCount = 2
        cfg.captureMicrophone = true
        cfg.microphoneCaptureDeviceID = nil
        cfg.excludesCurrentProcessAudio = true
        meta.config = StreamConfigSnapshot(
            filter: "desktopIndependentWindow", onScreenWindowsOnly: false, scalesToFit: cfg.scalesToFit,
            minimumFrameInterval: "\(cfg.minimumFrameInterval.value)/\(cfg.minimumFrameInterval.timescale)",
            capturesAudio: cfg.capturesAudio, sampleRate: cfg.sampleRate, channelCount: cfg.channelCount,
            captureMicrophone: cfg.captureMicrophone, microphoneCaptureDeviceID: cfg.microphoneCaptureDeviceID,
            excludesCurrentProcessAudio: cfg.excludesCurrentProcessAudio, fileType: "mov", videoCodec: "h264",
            segmentSeconds: segmentSeconds)
        writeMeta()
        writeManifest()

        try? String(getpid()).write(to: ctx.pidURL, atomically: true, encoding: .utf8)

        // writer 在第一個 sample 到達時才建（design §7.2），所以 startCapture 失敗不會留下任何 seg-*.mov。
        // 第一次失敗：記 log、丟掉這條 stream、等 startCaptureRetryDelaySeconds、以同一組 filter 與設定重建後重試一次（§7.6）。
        stream = makeStream()
        t0 = hostSeconds()
        do {
            try await stream.startCapture()
        } catch {
            log.line("⚠ startCapture 第一次失敗（\(error.localizedDescription)），\(Int(startCaptureRetryDelaySeconds)) 秒後重試")
            try? await stream.stopCapture()
            try? await Task.sleep(nanoseconds: UInt64(startCaptureRetryDelaySeconds * 1_000_000_000))
            stream = makeStream()
            t0 = hostSeconds()
            do {
                try await stream.startCapture()
                log.line("● startCapture 重試成功")
            } catch {
                try? FileManager.default.removeItem(at: ctx.pidURL)
                fail(code: 5, "startCapture 失敗：\(error.localizedDescription)")
            }
        }
        log.line("● 開始錄製：視窗 [\(window.windowID)]、畫布 \(cfg.width)×\(cfg.height) px、場次 \(ctx.session.path)")
        q.sync { controlEnabled = true }
        status.update {
            $0.phase = .recording
            $0.code = 0
            $0.message = "錄製中"
            // R2 選用欄位（spec §3.10）：controlVersion 讓 menu bar／CLI 知道可以送控制
            $0.controlVersion = controlProtocolVersion
            $0.recordingStartedAt = isoNow()
            $0.paused = false
            $0.micMuted = false
            $0.pausedSeconds = 0
            $0.markers = 0
        }

        q.sync {
            let devices = meta.devices
            let mon = AudioDeviceMonitor(queue: q) { [weak self] kind, from, to in self?.deviceChanged(kind, from, to) }
            mon.start(initial: devices)
            deviceMonitor = mon
            // S-B 輸出延遲唯讀記錄（spec §3.17、§4.35.7）：開錄時一筆 t=0，之後每筆輸出裝置 deviceEvents 一筆
            meta.outputLatencies = [outputLatencySnapshot(t: 0)]
            writeMeta()
            levelsTimer = repeating(0.5) { [weak self] in self?.closeLevels() }
            timers.append(repeating(30) { [weak self] in self?.checkDisk() })
            // 暫停心跳（spec §4.26.6）：暫停中每 pausedHeartbeatSeconds 秒重寫狀態檔，讓 menu bar／CLI 看得出實例還活著
            timers.append(repeating(pausedHeartbeatSeconds) { [weak self] in self?.pausedHeartbeat() })
        }
    }

    /// 建一條 SCStream 並掛上三個 output（重試時重建，不重用失敗過的 stream，design §7.6）。
    private func makeStream() -> SCStream {
        let s = SCStream(filter: filter, configuration: cfg, delegate: self)
        do {
            try s.addStreamOutput(self, type: .screen, sampleHandlerQueue: screenQ)
            try s.addStreamOutput(self, type: .audio, sampleHandlerQueue: audioQ)
            try s.addStreamOutput(self, type: .microphone, sampleHandlerQueue: micQ)
        } catch {
            fail(code: 5, "掛不上擷取輸出：\(error.localizedDescription)")
        }
        return s
    }

    /// 開錄前就失敗：寫 failed 狀態後結束（已落盤段落保留）。
    private func fail(code: Int32, _ message: String) -> Never {
        log.line("✗ \(message)")
        status.update {
            $0.phase = .failed
            $0.code = code
            $0.message = message
        }
        try? FileManager.default.removeItem(at: ctx.pidURL)
        exit(code)
    }

    private func repeating(_ seconds: Double, _ body: @escaping () -> Void) -> DispatchSourceTimer {
        let t = DispatchSource.makeTimerSource(queue: q)
        t.schedule(deadline: .now() + seconds, repeating: seconds, leeway: .milliseconds(20))
        t.setEventHandler(handler: body)
        t.resume()
        return t
    }

    private func installSignalHandlers() {
        for sig in [SIGTERM, SIGINT] {
            signal(sig, SIG_IGN)
            let s = DispatchSource.makeSignalSource(signal: sig, queue: q)
            s.setEventHandler { [weak self] in
                self?.log.line("● 收到停止訊號（\(sig == SIGTERM ? "SIGTERM" : "SIGINT")），開始優雅停止")
                self?.requestStop()
            }
            s.resume()
            signals.append(s)
        }
        // R2 控制（spec §4.16.4）：與 SIGTERM 相同的 DispatchSource 模式；預設動作會終止程序，所以先忽略
        signal(SIGUSR1, SIG_IGN)
        let usr1 = DispatchSource.makeSignalSource(signal: SIGUSR1, queue: q)
        usr1.setEventHandler { [weak self] in self?.applyControl() }
        usr1.resume()
        signals.append(usr1)
    }

    // MARK: - SCStreamDelegate

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        q.async {
            // t7（§6 第 103 條）：使用者從選單列的系統「畫面錄製」指示按停止 → 一般停止（結束碼 0），不是中斷
            if isUserStoppedStream(error) {
                self.log.line("● 使用者從系統的畫面錄製指示停止，照一般停止收尾")
                self.requestStop()
                return
            }
            self.log.line("✗ 擷取串流中斷：\(error.localizedDescription)")
            self.hadError = true
            self.forced = self.forced ?? (5, "擷取串流中斷，已落盤段落保留：\(error.localizedDescription)")
            self.requestStop()
        }
    }

    // MARK: - 樣本（監看＋寫檔）

    func stream(_ stream: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
        guard sb.isValid else { return }
        let pts = CMSampleBufferGetPresentationTimeStamp(sb)
        let t = (pts.isValid ? pts.seconds : hostSeconds()) - t0
        switch type {
        case .screen:
            let st = frameStatusKind(sb)
            var ratio: Double?
            if st == .complete, t - lastBlackSample >= 1.0 {      // 每秒抽一幀
                ratio = lumaNonBlackRatio(sb)
                lastBlackSample = t
            }
            let writable = st == .complete && pts.isValid && sb.imageBuffer != nil
            let heartbeat = st == .idle && pts.isValid      // 影片心跳只由 idle sample 驅動（spec §4.4.10）
            q.async { [self] in
                onScreen(t: t, status: st, ratio: ratio)
                if writable { ingest(sb, track: .video, start: pts, end: pts, formatChangedOn: nil) }
                if heartbeat { videoHeartbeat(pts) }
            }
        case .audio, .microphone:
            let src: AudioSource = type == .audio ? .system : .mic
            // 麥克風靜音（spec §4.17.2）：算 RMS 之前以數位 0 的深拷貝取代，照常寫進 mic 軌（軌道不中斷）
            var buf = sb
            if type == .microphone, isMicMutedForMicQ(), let z = zeroedAudioSample(sb) { buf = z }
            let fmt = audioFormat(of: buf)
            let db = rmsDBFS(sampleBuffer: buf)
            let end = audioEnd(buf, pts: pts, format: fmt)
            q.async {
                let changed = self.onAudio(src, t: t, format: fmt, dbfs: db)
                guard pts.isValid else { return }
                self.ingest(buf, track: src == .system ? .system : .mic, start: pts, end: end,
                            formatChangedOn: changed ? src : nil)
            }
        @unknown default:
            break
        }
    }

    /// 音訊緩衝的結束點＝PTS＋duration（duration 無效時以 frame 數／取樣率算）。
    private func audioEnd(_ sb: CMSampleBuffer, pts: CMTime, format: AudioFormat?) -> CMTime {
        let d = CMSampleBufferGetDuration(sb)
        if d.isValid, d.seconds > 0 { return CMTimeAdd(pts, d) }
        let n = CMSampleBufferGetNumSamples(sb)
        if let rate = format?.sampleRate, rate > 0, n > 0 {
            return CMTimeAdd(pts, CMTime(value: CMTimeValue(n), timescale: CMTimeScale(rate)))
        }
        return pts
    }

    private func onScreen(t: Double, status st: FrameStatusKind?, ratio: Double?) {
        if let st {
            switch st {
            case .complete: manifest.frameStatus.complete += 1
            case .idle: manifest.frameStatus.idle += 1
            case .blank: manifest.frameStatus.blank += 1
            case .suspended: manifest.frameStatus.suspended += 1
            case .started: manifest.frameStatus.started += 1
            case .stopped: manifest.frameStatus.stopped += 1
            }
            if detectorFeed(paused: gate.paused, micMuted: micMuted).suspended, suspended.feed(t: t, status: st) {
                warn(.suspended, "會議視窗的擷取已暫停超過 5 秒（多半是被最小化）：把視窗還原")
            }
        }
        if let ratio, detectorFeed(paused: gate.paused, micMuted: micMuted).black, black.feed(t: t, nonBlackRatio: ratio) {
            warn(.black, "會議視窗畫面已連續 5 秒全黑：確認會議畫面是否正常（錄製照常進行）")
        }
    }

    /// 回傳本緩衝的格式是否與該路上一個緩衝不同（design §7.5）。
    @discardableResult
    private func onAudio(_ src: AudioSource, t: Double, format: AudioFormat?, dbfs: Double?) -> Bool {
        var changed = false
        if let format {
            if let last = lastFormat[src], last != format {
                changed = true
                meta.audioFormatEvents.append(AudioFormatEvent(t: round3(t), source: src, from: last, to: format))
                writeMeta()
                let who = src == .system ? "系統聲音" : "麥克風"
                warn(.audioFormatChange,
                     "\(who)的音訊格式改為 \(Int(format.sampleRate / 1000)) kHz \(format.channels) 聲道（常見於藍牙耳機切換）")
            }
            lastFormat[src] = format
        }
        if let dbfs {      // 讀不懂的格式不當成 -∞
            if src == .system { sysPeak.feed(t: t, dbfs: dbfs) } else { micPeak.feed(t: t, dbfs: dbfs) }
        }
        return changed
    }

    // MARK: - 段落（只在 q 上呼叫；design §7.2）

    /// 一個 sample 進來：必要時換段，再以 routeSample 分流寫進舊段／新段。
    /// updatesLastFrame：影片心跳重送的幀傳 false（不得成為新的「最後一個 complete 幀」，spec §4.4.10）。
    private func ingest(_ sb: CMSampleBuffer, track: SegmentTrack, start: CMTime, end: CMTime, formatChangedOn src: AudioSource?,
                        updatesLastFrame: Bool = true) {
        if let e = stopPoint, CMTimeCompare(start, e) >= 0 { return }     // 停止點之後不寫
        // 暫停閘門（spec §4.18.2）：在 maxEnd 更新之前判斷；prevOnly、drop 不更新 maxEnd、不自動開段
        let route = pauseRoute(gate, sampleStart: start.seconds)
        switch route {
        case .prevOnly:
            if let p = prev { write(sb, track: track, to: p) }       // 停止點 E 之前晚到的 sample 只進舊段
            if track == .video, updatesLastFrame { lastFrame = sb }
            return
        case .drop:
            if track == .video, updatesLastFrame { lastFrame = sb }  // 照常更新最後一個 complete 幀（不寫入）
            return
        case .normal, .resumeBoundary:
            break
        }
        if stopPoint == nil, !maxEnd.isValid || CMTimeCompare(end, maxEnd) > 0 { maxEnd = end }
        if !firstSampleLogged {
            firstSampleLogged = true
            let offset = start.seconds - hostSeconds()
            log.line("● 第一個 sample：PTS − host clock = \(String(format: "%.3f", offset)) 秒")
            if abs(offset) > 1 { log.line("⚠ 第一個 sample 的 PTS 與 host clock 相差超過 1 秒（\(String(format: "%.3f", offset)) 秒）") }
        }

        if !stopping {
            if let reason = openReason(route: route, hasCurrent: cur != nil, everOpened: everOpened,
                                       switchOnNextSample: switchOnNextSample) {
                // 第一段：B_1＝第一個 sample 的 PTS。writer 失敗後的新段：以下一個 sample 的 PTS 當邊界，
                // 但不早於上一段的起點（同一個時間點不會出現兩段重疊）。繼續（resume）：以第一個 PTS ≥ E 的 sample 為邊界。
                let b = lastSegmentStart.isValid && CMTimeCompare(start, lastSegmentStart) < 0 ? lastSegmentStart : start
                startNewSegment(boundary: b, reason: reason, trigger: track, triggerStart: start)
                if route == .resumeBoundary, cur != nil { resumedSegmentOpened(at: b) }
            } else if let src, let c = cur, shouldSwitchForFormat(src, at: start.seconds),
                      CMTimeCompare(start, c.start) > 0 {
                // 格式變更提前換段：以第一個新格式緩衝的 PTS 為邊界（design §7.5）
                log.line("● \(src == .system ? "系統聲音" : "麥克風")格式變更，提前換段")
                startNewSegment(boundary: start, reason: .formatChange, trigger: track, triggerStart: start)
            } else if nextBoundary.isValid,
                      CMTimeCompare(start, nextBoundary) >= 0 || CMTimeCompare(end, nextBoundary) > 0 {
                // 定期換段：第一個越過邊界的 sample（PTS ≥ 邊界，或音訊緩衝跨過邊界）到達時切換
                startNewSegment(boundary: nextBoundary, reason: .periodic, trigger: track, triggerStart: start)
            }
        }

        if let p = prev, let c = cur {
            let r = routeSample(start: start.seconds, end: end.seconds, boundary: prevEnd.seconds)
            if r != .old {
                p.sawPast.insert(track)
                if p.sawPast.count == SegmentTrack.allCases.count { closePrev() }
            }
            if r == .old || r == .both { write(sb, track: track, to: p) }
            if r == .new || r == .both { write(sb, track: track, to: c) }
        } else if let c = cur {
            write(sb, track: track, to: c)
        }
        if track == .video, updatesLastFrame { lastFrame = sb }
    }

    /// 影片心跳（design §7.2〈當機〉、spec §4.4.10）：收到 idle 的 .screen sample 時，距目前段落最後一個已寫入的
    /// 視訊 PTS ≥ videoHeartbeatSeconds，就把最後一個 complete 幀以 idle 的 PTS 重新打戳，走與一般視訊 sample
    /// 相同的路（停止點、換段、分流、PTS 遞增檢查）寫入；不更新 lastFrame、不計入 frameStatus.complete。
    private func videoHeartbeat(_ pts: CMTime) {
        guard let c = cur, let lf = lastFrame else { return }
        let last: Double? = c.lastVideoPTS.isValid ? c.lastVideoPTS.seconds : nil
        guard shouldEmitVideoHeartbeat(samplePTS: pts.seconds, lastVideoPTS: last, hasLastFrame: true,
                                       interval: videoHeartbeatSeconds),
              let copy = retimedVideoSample(lf, pts: pts) else { return }
        ingest(copy, track: .video, start: pts, end: pts, formatChangedOn: nil, updatesLastFrame: false)
    }

    /// 同一路 1 秒內再變一次格式時不再提前換段（避免 HFP 協商抖動時連續開檔，design §7.5）。
    private func shouldSwitchForFormat(_ src: AudioSource, at t: Double) -> Bool {
        defer { lastFormatChangePTS[src] = t }
        if let last = lastFormatChangePTS[src], t - last < 1.0 { return false }
        return true
    }

    private func write(_ sb: CMSampleBuffer, track: SegmentTrack, to seg: SegmentWriter) {
        if seg.append(sb, to: track) == .failed { writerFailed(seg, seg.error) }
    }

    /// 開新段：舊段（若有）轉成 prev 繼續收邊界前的 sample，1 秒內或三路都過邊界後收尾。
    private func startNewSegment(boundary b: CMTime, reason: SwitchReason, trigger: SegmentTrack, triggerStart: CMTime) {
        let replacement = reason == .writerFailure
        switchOnNextSample = false
        if prev != nil { closePrev() }
        let old = cur
        cur = nil

        // 尺寸：換段當下同步讀會議視窗大小，經 nextSegmentSize 決定（讀不到沿用上一段）；
        // 與上一段不同就 updateConfiguration（不等完成）。第一段沿用開錄時的視窗尺寸（design §7.1、spec §4.3.6）。
        let size = reason == .first ? curSize
            : nextSegmentSize(windowPoints: windowPointSize(window.windowID), scale: scale, previous: curSize)
        if size != curSize {
            log.line("● 視窗尺寸改變：\(curSize.width)×\(curSize.height) → \(size.width)×\(size.height) px（本段起生效）")
            curSize = size
            cfg.width = size.width
            cfg.height = size.height
            stream.updateConfiguration(cfg) { [weak self] err in
                if let err { self?.log.line("⚠ updateConfiguration 失敗：\(err.localizedDescription)") }
            }
        }

        let requested = everOpened ? round3(now()) : 0
        everOpened = true
        lastSegmentStart = b
        let seg = openSegment(start: b, requestedAt: requested, replacement: replacement)

        if let old, !old.hasFailed {
            prev = old
            prevEnd = b
            q.asyncAfter(deadline: .now() + 1.0) { [weak self, weak old] in
                guard let self, let old, self.prev === old else { return }
                self.closePrev()
            }
        }
        guard let seg else { return }
        cur = seg
        nextBoundary = CMTimeAdd(b, CMTime(seconds: Double(segmentSeconds), preferredTimescale: b.timescale))

        // 新段第一個視訊 sample：觸發換段的正是 PTS == 邊界的 complete 幀就直接寫它；
        // 否則把最後一個 complete 幀以邊界重新打戳寫進新段（design §7.2 第 3 步）。
        let triggerIsBoundaryFrame = trigger == .video && CMTimeCompare(triggerStart, b) == 0
        if reason != .first, !triggerIsBoundaryFrame, let lf = lastFrame, let copy = retimedVideoSample(lf, pts: b) {
            write(copy, track: .video, to: seg)
        }
    }

    /// 建 writer、startWriting、startSession；失敗時依〈writer 失敗〉處理並回 nil。
    private func openSegment(start b: CMTime, requestedAt: Double, replacement: Bool) -> SegmentWriter? {
        segIndex += 1
        let name = segmentFileName(index: segIndex)
        let size = curSize
        manifest.segments.append(SegmentRecord(file: name, requestedAt: requestedAt, startedAt: round3(b.seconds - t0),
                                               finishedAt: nil, width: size.width, height: size.height, audioDuration: nil))
        segRow[segIndex] = manifest.segments.count - 1
        writeManifest()
        let opened = replacement ? hostSeconds() : nil
        let seg: SegmentWriter
        do {
            seg = try SegmentWriter(directory: ctx.tracksDir, index: segIndex, start: b, size: size, replacementOpenedAt: opened)
        } catch {
            openFailed(name, error, replacement: replacement)
            return nil
        }
        guard seg.begin() else {
            seg.failureReported = true
            openFailed(name, seg.error, replacement: replacement)
            return nil
        }
        log.line("● 開段 \(name)（\(size.width)×\(size.height) px、起點 \(String(format: "%.3f", b.seconds - t0)) 秒）")
        return seg
    }

    private func openFailed(_ name: String, _ error: Error?, replacement: Bool) {
        hadError = true
        let why = error?.localizedDescription ?? "未知錯誤"
        log.line("✗ \(name) 寫檔失敗：\(why)")
        warn(.segmentWriteFailed, "\(name) 寫檔失敗（開檔）：\(why)；檔案保留")
        if replacement {
            stopForRepeatedFailure()
        } else {
            switchOnNextSample = true
        }
    }

    /// 段落 writer 失敗（append 回 false、finishWriting 結果 failed、收尾逾時）：記告警、保留檔案；
    /// 目前的段落失敗就以下一個 sample 提前換段；10 秒內又失敗就優雅停止（design §7.2〈writer 失敗〉）。
    private func writerFailed(_ seg: SegmentWriter, _ error: Error?) {
        guard !seg.failureReported else { return }
        seg.failureReported = true
        hadError = true
        let why = error?.localizedDescription ?? "未知錯誤"
        log.line("✗ \(seg.file) 寫檔失敗：\(why)")
        if seg === prev { prev = nil }
        if seg === cur, !stopping {
            if let opened = seg.replacementOpenedAt, hostSeconds() - opened < 10 {
                warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留")
                cur = nil
                stopForRepeatedFailure()
            } else {
                warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留，已換新段繼續錄")
                switchOnNextSample = true
            }
        } else {
            warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留")
        }
    }

    private func stopForRepeatedFailure() {
        forced = forced ?? (5, "段落連續寫檔失敗，已停止並收尾；已落盤段落保留")
        requestStop()
    }

    private func closePrev() {
        guard let p = prev else { return }
        prev = nil
        finishSegment(p, at: prevEnd)
    }

    /// endSession → markAsFinished → finishWriting；完成回呼回 q 記 finishedAt 或失敗。
    private func finishSegment(_ seg: SegmentWriter, at end: CMTime) {
        closing[seg.index] = seg
        seg.finish(at: end) { [weak self] ok, err in
            guard let self else { return }
            self.q.async { self.segmentFinished(seg, ok: ok, error: err) }
        }
    }

    private func segmentFinished(_ seg: SegmentWriter, ok: Bool, error: Error?) {
        guard closing.removeValue(forKey: seg.index) != nil else { return }     // 收尾逾時已處理過
        if ok {
            if let row = segRow[seg.index] { manifest.segments[row].finishedAt = round3(now()) }
            finishedSegments += 1
            manifest.blackIntervals = roundedBlack()
            writeManifest()
            let n = finishedSegments
            status.update { $0.segments = n }
            log.line("✓ \(seg.file) 收尾（\(seg.size.width)×\(seg.size.height)；\(seg.dropSummary)）")
        } else {
            writerFailed(seg, error)
        }
        checkStopDone()
    }

    // MARK: - 監看（計時）

    /// 每 0.5 秒由主機時鐘收斂一次時段；沒有緩衝的時段為 -∞（寫 null），再餵靜音偵測。
    /// 平時延後 0.3 秒收斂（音訊緩衝送達比 PTS 晚幾十毫秒，太早收斂會把有聲音的時段誤記成空的）；停止時收到底。
    private func closeLevels(final: Bool = false) {
        let t = final ? now() : now() - 0.3
        let feed = detectorFeed(paused: gate.paused, micMuted: micMuted)
        for p in sysPeak.close(upTo: t) {
            manifest.levels.system.append(round1OrNil(p))
            if feed.systemSilence, sysSilence.feed(t: Double(manifest.levels.system.count) * 0.5, dbfs: p) {
                warn(.silenceSystem, "系統聲音已連續 15 秒幾乎沒有聲音（低於 -60 dBFS）：檢查會議 app 的輸出與音量")
            }
        }
        for p in micPeak.close(upTo: t) {
            manifest.levels.mic.append(round1OrNil(p))
            if feed.micSilence, micSilence.feed(t: Double(manifest.levels.mic.count) * 0.5, dbfs: p) {
                warn(.silenceMic, "麥克風已連續 15 秒幾乎沒有聲音（低於 -60 dBFS）：檢查麥克風是否被拔掉或靜音")
            }
        }
        if !final { updateRecentLevels() }
    }

    /// 收音指示（spec §3.10）：各路最後 6 個 0.5 秒時段的最大值；靜音中 mic 為 null；暫停中沒有此鍵；每秒最多寫一次。
    private func updateRecentLevels() {
        guard controlEnabled, !stopping, !gate.paused else { return }
        let t = now()
        guard t - lastRecentLevelsWrite >= 1.0 else { return }
        lastRecentLevelsWrite = t
        let sys = recentPeak(manifest.levels.system, count: 6)
        let mic = micMuted ? nil : recentPeak(manifest.levels.mic, count: 6)
        status.update { $0.recentLevels = RecentLevels(windowSeconds: 3, system: sys, mic: mic) }
    }

    /// 暫停心跳（spec §4.26.6）：只在暫停中重寫 record.status.json，只有 updatedAt 改變（鍵集合不變）。
    private func pausedHeartbeat() {
        guard controlEnabled, !stopping, gate.paused else { return }
        status.update { _ in }
    }

    private func deviceChanged(_ kind: DeviceKind, _ from: AudioDeviceInfo?, _ to: AudioDeviceInfo?) {
        let t = round3(now())
        meta.deviceEvents.append(DeviceEvent(t: t, kind: kind, from: from, to: to))
        if kind == .output {   // S-B：與這筆 deviceEvents 同一個 t（spec §3.17）
            meta.outputLatencies = (meta.outputLatencies ?? []) + [outputLatencySnapshot(t: t)]
        }
        writeMeta()
        let what = kind == .input ? "輸入" : "輸出"
        let name = to.map { "\($0.name)（\($0.transport)）" } ?? "（無）"
        warn(.deviceChange, "\(what)裝置已切換為 \(name)")
        // 預設輸入變更時以新裝置 UID 更新設定（SCK 是否自動跟隨未知，req:292）；只讀裝置，不改使用者的預設值
        if kind == .input, !stopping {
            cfg.microphoneCaptureDeviceID = to?.uid
            stream.updateConfiguration(cfg) { [weak self] err in
                if let err { self?.log.line("⚠ 換麥克風裝置失敗：\(err.localizedDescription)") }
            }
        }
    }

    private func checkDisk() {
        guard let avail = PreflightRunner.availableBytes(ctx.session), avail < diskLowBytes else { return }
        warn(.diskLow, "磁碟可用空間低於 2 GB，已自動停止並收尾")
        forced = forced ?? (5, "磁碟可用空間低於 2 GB（剩 \(String(format: "%.2f", Double(avail) / 1e9)) GB），已自動停止並收尾；段落保留")
        requestStop()
    }

    private func warn(_ kind: WarningKind, _ message: String) {
        let w = RecordWarning(t: round3(now()), kind: kind, message: message)
        log.line("⚠ \(message)")
        status.update { $0.warnings.append(w) }
    }

    // MARK: - R2 控制（只在 q 上呼叫；spec §4.16.4、§4.17.2、§4.18.2、§4.18.3、§4.19.2）

    /// SIGUSR1：讀控制檔、與已套用的狀態比差異後套用。開錄前與停止中不接受（controlAvailability 也不會放行）。
    private func applyControl() {
        guard controlEnabled, !stopping else {
            log.line("● 收到 SIGUSR1，但目前不接受控制（\(stopping ? "收尾中" : "還沒開始錄製")），略過")
            return
        }
        let requested = readControl(ctx.home.appendingPathComponent(controlFileName))
        let actions = controlActions(applied: applied, requested: requested)
        if let p = actions.pause { if p { pauseRecording() } else { resumeRecording() } }
        if let m = actions.micMute { setMicMuted(m) }
        if actions.newMarkers > 0 { addMarkers(actions.newMarkers) }
        if let r = requested, r.runId == applied.runId, r.schemaVersion == controlProtocolVersion {
            applied.paused = r.paused
            applied.micMuted = r.micMuted
            applied.markerSeq = max(applied.markerSeq, r.markerSeq)
        }
    }

    /// 成品時間換算的 startedAt_1（還沒有任何段落時為 0）。
    private var firstSegmentStart: Double { manifest.segments.first?.startedAt ?? 0 }

    /// 暫停（design R2-D3 第 1 步）：以停止點 E 收掉目前段落、偵測器停餵、記 pause 事件與狀態欄位。
    private func pauseRecording() {
        guard !gate.paused else { return }
        let c = cur
        gate = pausing(gate, maxEnd: maxEnd.isValid ? maxEnd.seconds : nil, segmentStart: c?.start.seconds)
        let e: CMTime? = maxEnd.isValid ? maxEnd : c?.start
        if prev != nil { closePrev() }
        cur = nil
        nextBoundary = .invalid
        switchOnNextSample = false
        if let c {
            if c.hasFailed {
                writerFailed(c, c.error)
            } else if let e, CMTimeCompare(e, c.start) > 0, c.appendedTotal > 0 {
                // 目前段轉成 prev：只收 PTS < E 的晚到 sample，1 秒後收尾（與換段相同）
                prev = c
                prevEnd = e
                q.asyncAfter(deadline: .now() + 1.0) { [weak self, weak c] in
                    guard let self, let c, self.prev === c else { return }
                    self.closePrev()
                }
            } else {
                // 段落沒有任何內容：捨棄並從 manifest 移除（與停止時相同）
                c.cancel()
                if let row = segRow[c.index], row == manifest.segments.count - 1 {
                    manifest.segments.removeLast()
                    segRow[c.index] = nil
                }
                log.line("● \(c.file) 沒有內容，捨棄")
            }
        }
        let cutT = gate.cutPoint.map { $0 - t0 } ?? 0
        black.interrupt(at: cutT)
        let events = appendingPauseEvent(meta.pauseEvents ?? [], kind: .pause, t: cutT,
                                         firstSegmentStart: firstSegmentStart, wallClock: isoNow())
        meta.pauseEvents = events
        writeManifest()
        writeMeta()
        let fields = pauseStatusFields(events)
        status.update {
            $0 = applyingPauseFields(fields, to: $0)
            $0.recentLevels = nil
        }
        log.line("● 暫停錄製（停止點 \(String(format: "%.3f", cutT)) 秒）")
    }

    /// 繼續（design R2-D3 第 3 步）：下一個 PTS ≥ E 的 sample 開新段（SwitchReason.resume）；偵測器重設。
    /// resume 事件的 t＝新段 startedAt，所以等開段時才記（resumedSegmentOpened）；狀態檔先反映「沒在暫停」。
    private func resumeRecording() {
        guard gate.paused else { return }
        gate = resuming(gate)
        sysSilence.reset()
        micSilence.reset()
        suspended.reset()
        let provisional = appendingPauseEvent(meta.pauseEvents ?? [], kind: .resume, t: now(),
                                              firstSegmentStart: firstSegmentStart, wallClock: isoNow())
        let fields = pauseStatusFields(provisional)
        status.update { $0 = applyingPauseFields(fields, to: $0) }
        log.line("● 繼續錄製（等下一個 sample 開新段）")
    }

    /// 繼續後的新段已開：記 resume 事件（t＝新段 startedAt）、閘門回到一般狀態。
    private func resumedSegmentOpened(at b: CMTime) {
        gate = segmentOpened(gate)
        let t = b.seconds - t0
        let events = appendingPauseEvent(meta.pauseEvents ?? [], kind: .resume, t: t,
                                         firstSegmentStart: firstSegmentStart, wallClock: isoNow())
        meta.pauseEvents = events
        writeMeta()
        let fields = pauseStatusFields(events)
        status.update { $0 = applyingPauseFields(fields, to: $0) }
    }

    /// 麥克風靜音／取消靜音（design R2-D4）：mic 緩衝改寫成數位 0；取消時重設 micSilence。系統聲音不受影響。
    private func setMicMuted(_ muted: Bool) {
        guard muted != micMuted else { return }
        micMuted = muted
        muteLock.lock(); micMutedForMicQ = muted; muteLock.unlock()
        if !muted { micSilence.reset() }
        meta.micMuteEvents = appendingMuteEvent(meta.micMuteEvents ?? [], muted: muted, t: now(),
                                                firstSegmentStart: firstSegmentStart, pauses: meta.pauseEvents ?? [],
                                                wallClock: isoNow())
        writeMeta()
        status.update {
            $0.micMuted = muted
            if muted, $0.recentLevels != nil { $0.recentLevels?.mic = nil }
        }
        log.line(muted ? "● 麥克風靜音" : "● 麥克風取消靜音")
    }

    private func isMicMutedForMicQ() -> Bool {
        muteLock.lock(); defer { muteLock.unlock() }
        return micMutedForMicQ
    }

    /// 標記（spec §3.12、§4.19.2）：t＝成品時間（暫停中為該次暫停點）、recordT＝錄製時鐘；整檔 tmp＋rename 重寫。
    private func addMarkers(_ n: Int) {
        let recordT = round3(now())
        let pauses = meta.pauseEvents ?? []
        for _ in 0..<n {
            markers.append(Marker(t: outputTime(recordT: recordT, firstSegmentStart: firstSegmentStart, pauses: pauses),
                                  recordT: recordT, wallClock: isoNow(), label: markerLabel(markers.count + 1)))
        }
        do { try writeJSONAtomically(markers, to: markersURL) } catch {
            log.line("⚠ 寫 markers.json 失敗：\(error.localizedDescription)")
        }
        let count = markers.count
        status.update { $0.markers = count }
        log.line("● 加標記（共 \(count) 個）")
    }

    // MARK: - 停止（design §7.4）

    /// SIGTERM、磁碟不足、串流中斷、段落連續寫檔失敗都走這裡（只在 q 上呼叫）。
    /// 1. 記停止點 E；2. stopCapture（最多 10 秒）並排空三個 sample 佇列；
    /// 3. 收尾目前與所有舊 writer（各最多 10 秒）；4. finalize。
    private func requestStop() {
        guard !stopping else { return }
        stopping = true
        for t in timers { t.cancel() }
        timers.removeAll()
        stopPoint = maxEnd.isValid ? maxEnd : .zero
        if maxEnd.isValid {
            log.line("● 停止點 E＝\(String(format: "%.3f", maxEnd.seconds - t0)) 秒")
        }
        status.update { $0.phase = .stopping }

        var proceeded = false
        let proceed: () -> Void = { [weak self] in
            guard let self else { return }
            self.q.async {
                guard !proceeded else { return }
                proceeded = true
                // 對三個 sample 佇列各送一個空的同步工作：已排進佇列的 sample 都轉進 q 之後才收尾
                DispatchQueue.global(qos: .userInitiated).async {
                    self.screenQ.sync {}
                    self.audioQ.sync {}
                    self.micQ.sync {}
                    self.q.async { self.drainWriters() }
                }
            }
        }
        if let s = stream {
            s.stopCapture { [weak self] err in
                if let err { self?.log.line("⚠ stopCapture：\(err.localizedDescription)") }
                proceed()
            }
        } else {
            proceed()
        }
        q.asyncAfter(deadline: .now() + 10) { [weak self] in
            guard let self, !proceeded else { return }
            self.log.line("⚠ stopCapture 10 秒沒有回來，直接收尾")
            proceed()
        }
    }

    private func drainWriters() {
        guard !writersDrained else { return }
        writersDrained = true
        closePrev()
        if let c = cur {
            cur = nil
            let e = stopPoint ?? .zero
            if c.hasFailed {
                writerFailed(c, c.error)
            } else if CMTimeCompare(e, c.start) <= 0 || c.appendedTotal == 0 {
                // 段落沒有任何內容：捨棄（cancelWriting 會刪掉檔），不當成失敗
                c.cancel()
                if let row = segRow[c.index], row == manifest.segments.count - 1 {
                    manifest.segments.removeLast()
                    segRow[c.index] = nil
                }
                log.line("● \(c.file) 沒有內容，捨棄")
            } else {
                finishSegment(c, at: e)
            }
        }
        writeManifest()
        // 收尾逾時：各 writer 最多 10 秒，逾時視為寫檔失敗（段落保留）
        q.asyncAfter(deadline: .now() + 10) { [weak self] in
            guard let self, !self.closing.isEmpty else { return }
            for seg in self.closing.values.sorted(by: { $0.index < $1.index }) {
                self.closing[seg.index] = nil
                self.writerFailed(seg, NSError(domain: "MeetingRecorder", code: 2,
                                               userInfo: [NSLocalizedDescriptionKey: "收尾逾時（10 秒）"]))
            }
            self.checkStopDone()
        }
        checkStopDone()
    }

    /// 停止中、所有 writer 都到終態（completed／failed／逾時）才進 finalize。
    private func checkStopDone() {
        guard stopping, writersDrained, closing.isEmpty, !finalizeStarted else { return }
        finalizeStarted = true
        beginFinalize()
    }

    private func roundedBlack() -> [BlackInterval] {
        black.intervals.map { BlackInterval(start: round3($0.start), end: $0.end.map(round3)) }
    }

    private func beginFinalize() {
        levelsTimer?.cancel()
        closeLevels(final: true)
        deviceMonitor?.stop()
        lastFrame = nil
        manifest.blackIntervals = roundedBlack()
        writeManifest()
        writeMeta()
        let n = finishedSegments
        status.update {
            $0.phase = .finalizing
            $0.segments = n
            $0.message = "收尾中"
        }
        log.line("● 收尾中（\(n) 段）")
        DispatchQueue.global(qos: .userInitiated).async {
            let rc = self.runFinalize()
            self.q.async { self.complete(finalizeCode: rc) }
        }
    }

    /// spawn "<python3>" "<harness>/bin/_record_finalize.py" "<場次>"；輸出逐行寫進 record.log。
    private func runFinalize() -> Int32 {
        guard let harness = ctx.harness ?? defaults?.harness, !harness.isEmpty else {
            log.line("✗ 不知道 meeting-harness 的路徑（--harness 與 record.defaults.json 都沒有），無法收尾")
            return 127
        }
        let script = URL(fileURLWithPath: harness).appendingPathComponent("bin/_record_finalize.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            log.line("✗ 找不到 \(script.path)，無法收尾")
            return 127
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: defaults?.python3 ?? "/usr/bin/python3")
        p.arguments = [script.path, ctx.session.path]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if let ff = defaults?.ffmpeg, !ff.isEmpty { env["MH_FFMPEG"] = ff }
        p.environment = env
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        do { try p.run() } catch {
            log.line("✗ 啟動收尾失敗：\(error.localizedDescription)")
            return 126
        }
        let reader = pipe.fileHandleForReading
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
        p.waitUntilExit()
        return p.terminationStatus
    }

    /// 最終結果一律由 Core completionOutcome 決定：停止原因（forced）在開頭，收尾失敗附在其後（spec §4.4.7、§4.4.9）。
    private func complete(finalizeCode rc: Int32) {
        let outcome = completionOutcome(finalizeCode: rc, forcedCode: forced?.code, forcedMessage: forced?.message,
                                        hadError: hadError, sessionPath: ctx.session.path)
        status.update {
            $0.phase = outcome.phase
            $0.code = outcome.code
            $0.message = outcome.message
        }
        try? FileManager.default.removeItem(at: ctx.pidURL)
        log.line(outcome.code == 0 ? "✓ \(outcome.message)" : "✗ \(outcome.message)")
        Notifier.post(title: outcome.code == 0 ? "會議錄製完成" : "會議錄製結束（有錯誤）",
                      body: outcome.code == 0 ? ctx.session.path : "\(outcome.message)\n\(ctx.session.path)",
                      identifier: completionNotificationID(runId: ctx.runId))
        exit(outcome.code)
    }

    // MARK: - 落盤

    private func writeManifest() {
        do { try writeJSONAtomically(manifest, to: manifestURL) } catch { log.line("⚠ 寫 manifest.json 失敗：\(error.localizedDescription)") }
    }

    private func writeMeta() {
        do { try writeJSONAtomically(meta, to: metaURL) } catch { log.line("⚠ 寫 record.meta.json 失敗：\(error.localizedDescription)") }
    }
}

/// SCStreamError.userStopped（-3817）：使用者從系統的畫面錄製指示（選單列紫色圖示）停止擷取。
func isUserStoppedStream(_ error: Error) -> Bool {
    let e = error as NSError
    return e.domain == SCStreamErrorDomain && e.code == SCStreamError.Code.userStopped.rawValue
}

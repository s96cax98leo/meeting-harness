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
//
// R3 Q6（spec §4.36.10、§4.36.11；design R3-D10）：開段、寫入、收段、暫停閘門的判斷都交給 Core 的 SegmentScheduler。
//   本檔把事件（sample、暫停、繼續、輸出裝置變更、writer 失敗、prev 逾時、停止）餵給 scheduler.handle，
//   照回傳的動作建 writer、append、finish／cancel；writer 層的實體檢查（失敗、空段、停止點）照 R2 保留在本檔。
//
// R3 F2 捨棄（spec §3.15、§4.42.3、§4.42.4；design R3 §捨棄）：SIGTERM 時讀 record.discard.json（讀後刪），
//   discardRequestValid 為 true → 照常停止擷取、收掉 writer，但跳過收尾，改以 trashItem 把 <場次>/錄音/ 移到垃圾桶；
//   從不對場次路徑硬刪。無效或不存在 → 照一般停止收尾。開錄時刪掉殘留的 record.discard.json。
//
// 拆檔（meeting-speed spec §4.13.1）：段落 writer 操作在 RecordingSession+Segments.swift、停止收 writer 與捨棄在
//   RecordingSession+Stop.swift、監看與落盤在 RecordingSession+Monitor.swift、增量轉錄 worker 在 RecordingSession+AsrWorker.swift；
//   都是同一個 class 的 extension，跨檔用到的成員因此由 private 放寬為模組內可見。被既有靜態測試釘住的函式留在本檔。
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
    let ctx: RunContext
    let status: StatusWriter
    let defaults: RecordDefaults?
    let q = DispatchQueue(label: "mh.rec.state")
    private let screenQ = DispatchQueue(label: "mh.rec.screen")
    private let audioQ = DispatchQueue(label: "mh.rec.audio")
    private let micQ = DispatchQueue(label: "mh.rec.mic")

    private var window: SCWindow
    private var filter: SCContentFilter
    private let cfg = SCStreamConfiguration()
    private var scale: Double
    private var stream: SCStream!
    var t0 = hostSeconds()

    // 段落（design §7.2；開段／寫入／收段的判斷在 Core 的 SegmentScheduler，spec §4.36.10）
    var scheduler = SegmentScheduler(segmentSeconds: Double(segmentSeconds))
    var writers: [Int: SegmentWriter] = [:]    // 排程器段號（＝段落 index）→ 目前段與 prev 的 writer
    var segEnd: [Int: CMTime] = [:]            // 已轉成 prev 的段落收尾點（新段起點或暫停停止點 E）
    var segRow: [Int: Int] = [:]             // 段落 index → manifest.segments 的位置
    var closing: [Int: SegmentWriter] = [:]    // 已呼叫 finish、等完成回呼的段落
    // 排程器的邊界是 Double 秒；以下兩個 CMTime 只用來把邊界還原成精確的 PTS（不參與換段判斷）
    var nextBoundary: CMTime = .invalid         // 最近一段起點＋segmentSeconds
    var lastSegmentStart: CMTime = .invalid     // 最近一次開段的起點
    /// 畫布尺寸：開錄當下會議視窗的偶數像素大小，整場不變（record.meta.json.canvasLock；meeting-speed spec §4.4.1）
    let curSize: PixelSize
    /// 最近一次換段時讀到的會議視窗像素大小（只用來判斷要不要寫「視窗尺寸改變」log）
    private var windowSize: PixelSize
    /// 換段當下同步讀會議視窗大小（point）；可替換（design §7.1，spec §4.3.6）。只在 q 上呼叫。
    var windowPointSize: (UInt32) -> CGSize? = cgWindowPointSize
    var lastFrame: CMSampleBuffer?             // 最後一個 complete 幀（換段時重新打戳）
    var finishedSegments = 0
    /// 本場累計丟幀數（各段收尾時加上該段影片「writer 未 ready」丟掉的幀；meeting-speed spec §3.1）
    var droppedFramesTotal = 0
    /// 增量轉錄 worker 已起過（每場只起一次；spec §4.11.1）
    var asrWorkerStarted = false
    /// 三路已收到的 sample 最晚結束點（CMTime 版；與排程器同一規則更新：通過暫停閘門才更新、停止後不更新）
    var maxEnd: CMTime = .invalid
    private var firstSampleLogged = false
    /// 繼續後的開段失敗時，resume 事件留到下一個成功開的段落再記（t＝該段 startedAt）
    private var pendingResumeEvent = false

    // 紀錄
    var manifest: Manifest
    var meta: RecordMeta

    // 監看
    var sysPeak = PeakWindow(windowSeconds: 0.5)
    var micPeak = PeakWindow(windowSeconds: 0.5)
    var sysSilence = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    var micSilence = SilenceDetector(thresholdDBFS: -60, seconds: 15)
    var black = BlackDetector(ratio: 0.01, seconds: 5)
    private var suspended = SuspendedDetector(seconds: 5)
    var lastFormat: [AudioSource: AudioFormat] = [:]
    private var lastBlackSample = -10.0      // 只在 screenQ 上讀寫

    // 停止
    var stopping = false
    var stopPoint: CMTime?                     // 停止點 E；PTS ≥ E 的 sample 一律不寫
    var writersDrained = false                 // 已對目前與舊 writer 呼叫收尾
    var finalizeStarted = false
    private var finalizeRunner: FinalizeRunner?         // 收尾執行器（spec §4.28.6）；beginFinalize 建立，只在 q 上讀寫
    private var queueLockFD: Int32?                    // 排隊鎖 <home>/finalize.queue.lock（spec R3x §3.22）；取得後持有到程序結束
    var discarding = false                     // 這次停止是 F2 捨棄（spec §4.42.3）：跳過收尾、移到垃圾桶
    var hadError = false
    var forced: (code: Int32, message: String)?
    private var timers: [DispatchSourceTimer] = []
    var levelsTimer: DispatchSourceTimer?
    private var signals: [DispatchSourceSignal] = []
    var deviceMonitor: AudioDeviceMonitor?

    // R2 控制（spec §3.9–§3.12）。除 micMutedForMicQ 外都只在 q 上讀寫。
    var controlEnabled = false                 // phase 轉 recording 後才接受控制
    private var applied: RecordControl                 // 已套用的控制狀態（與控制檔比差異）
    /// 暫停閘門（Core/Segments.swift）；由 SegmentScheduler 持有與更新，這裡唯讀
    var gate: PauseGate { scheduler.gate }
    var micMuted = false
    private var markers: [Marker] = []
    var lastRecentLevelsWrite = -Double.infinity
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
        self.windowSize = curSize
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

    var log: Logger { ctx.log }
    func now() -> Double { hostSeconds() - t0 }
    var manifestURL: URL { ctx.tracksDir.appendingPathComponent("manifest.json") }
    var metaURL: URL { ctx.tracksDir.appendingPathComponent("record.meta.json") }
    private var markersURL: URL { ctx.tracksDir.appendingPathComponent("markers.json") }
    /// <home>/record.discard.json（spec §3.15）
    var discardURL: URL { ctx.home.appendingPathComponent("record.discard.json") }

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
        // 上一場殘留的捨棄請求不得帶進這一場（spec §4.42.4）
        try? FileManager.default.removeItem(at: discardURL)

        // 畫布＝開錄當下會議視窗的偶數像素大小（D8），整場鎖定（meeting-speed spec §4.4.1）：之後每段都以這個尺寸開檔，
        // 視窗縮放時內容等比縮放進同一張畫布（preservesAspectRatio，§4.4.2），finalize 才能走 copy 串接。
        // 擷取幀率維持 1/60、不設尺寸上限（使用者 2026-10-22 對 §4.4.13 的決定）。
        cfg.width = curSize.width
        cfg.height = curSize.height
        cfg.scalesToFit = true
        cfg.preservesAspectRatio = true
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
        meta.canvasLock = CanvasLock(width: curSize.width, height: curSize.height)
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
        // startCapture 失敗時記錯誤的 domain、code 與當下的輸入／輸出裝置（meeting-speed spec §4.10.2）
        func logStartCaptureError(_ error: Error) {
            let e = error as NSError
            let d = currentDevices()
            let input = d.input.map { "\($0.name)／\($0.transport)" } ?? "（無）"
            let output = d.output.map { "\($0.name)／\($0.transport)" } ?? "（無）"
            log.line("⚠ startCapture 錯誤：domain \(e.domain)、code \(e.code)；輸入：\(input)；輸出：\(output)")
        }
        stream = makeStream()
        t0 = hostSeconds()
        do {
            try await stream.startCapture()
        } catch {
            log.line("⚠ startCapture 第一次失敗（\(error.localizedDescription)），\(Int(startCaptureRetryDelaySeconds)) 秒後重試")
            logStartCaptureError(error)
            try? await stream.stopCapture()
            try? await Task.sleep(nanoseconds: UInt64(startCaptureRetryDelaySeconds * 1_000_000_000))
            stream = makeStream()
            t0 = hostSeconds()
            do {
                try await stream.startCapture()
                log.line("● startCapture 重試成功")
            } catch {
                logStartCaptureError(error)
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
                guard let self else { return }
                self.log.line("● 收到停止訊號（\(sig == SIGTERM ? "SIGTERM" : "SIGINT")）")
                // F2 捨棄只看 SIGTERM，且只在還沒開始停止時（spec §4.42.3）
                if sig == SIGTERM, !self.stopping, self.consumeDiscardRequest() { self.discarding = true }
                self.requestStop(fromSignal: true)
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

    // MARK: - 段落（只在 q 上呼叫；design §7.2、R3-D10）

    /// 一個 sample 進來：交給 SegmentScheduler（暫停閘門、開段、routeSample 分流、收 prev 都在那裡判斷），
    /// 再照回傳的動作執行。updatesLastFrame：影片心跳重送的幀傳 false（不得成為新的「最後一個 complete 幀」，spec §4.4.10）。
    private func ingest(_ sb: CMSampleBuffer, track: SegmentTrack, start: CMTime, end: CMTime, formatChangedOn src: AudioSource?,
                        updatesLastFrame: Bool = true) {
        if let e = stopPoint, CMTimeCompare(start, e) >= 0 { return }     // 停止點之後不寫
        // 停止中（R2 行為）：不因格式變更換段；end 夾到停止點 E，讓跨 E 的緩衝不觸發定期換段（writer 收尾本來就截在 E）
        let schedEnd = stopPoint.map { CMTimeMinimum(end, $0) } ?? end
        let event = SchedulerEvent.sample(track: schedulerTrack(track), start: start.seconds, end: schedEnd.seconds,
                                          formatChanged: src != nil && !stopping)
        let gateBefore = scheduler.gate
        let curBefore = scheduler.current
        let prevBefore = scheduler.prev
        var next = scheduler
        let actions = next.handle(event)
        if stopping, curBefore == nil, actions.contains(where: { if case .open = $0 { return true } else { return false } }) {
            // 停止中、沒有目前段：R2 不換段也不寫（停止前 writer 失敗或開段失敗），所以不採用這次的開段
            if track == .video, updatesLastFrame { lastFrame = sb }
            return
        }
        scheduler = next
        // 通過暫停閘門（normal，或繼續後第一個 PTS ≥ E 的 sample）：與排程器同一規則更新 CMTime 版 maxEnd
        let resumeOpened = gateBefore.resumePending && !scheduler.gate.resumePending
        if !(gateBefore.paused || gateBefore.resumePending) || resumeOpened {
            if stopPoint == nil, !maxEnd.isValid || CMTimeCompare(end, maxEnd) > 0 { maxEnd = end }
            if !firstSampleLogged {
                firstSampleLogged = true
                let offset = start.seconds - hostSeconds()
                log.line("● 第一個 sample：PTS − host clock = \(String(format: "%.3f", offset)) 秒")
                if abs(offset) > 1 { log.line("⚠ 第一個 sample 的 PTS 與 host clock 相差超過 1 秒（\(String(format: "%.3f", offset)) 秒）") }
            }
        }

        for action in actions {
            switch action {
            case let .open(n, reason, boundary):
                if reason == .formatChange {
                    log.line("● \(track == .system ? "系統聲音" : "麥克風")格式變更，提前換段")
                } else if reason == .outputDeviceChange {
                    log.line("● 輸出裝置變更，提前換段")
                }
                if resumeOpened { pendingResumeEvent = true }
                startNewSegment(index: n, boundary: boundary, reason: reason, oldCurrent: curBefore,
                                trigger: track, triggerStart: start)
            case let .write(n, _):
                if let w = writers[n] { write(sb, track: track, to: w) }
            case .drop:
                break
            case let .finish(n):
                finishScheduled(n)
            case let .cancel(n):
                closeAtCut(n, at: maxEnd.isValid ? maxEnd : nil, keepAsPrev: false)
            }
        }
        armPrevTimeout(since: prevBefore)
        if track == .video, updatesLastFrame { lastFrame = sb }
    }

    /// 目前段的 writer（心跳用）；writer 失敗、暫停、停止後為 nil。
    private var cur: SegmentWriter? { scheduler.current.flatMap { writers[$0] } }

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

    /// 執行排程器的 open：原本的目前段（排程器已轉成 prev）記收尾點＝新段起點，再建新段 writer。
    private func startNewSegment(index n: Int, boundary bSeconds: Double, reason: SwitchReason, oldCurrent old: Int?,
                                 trigger: SegmentTrack, triggerStart: CMTime) {
        let b = boundaryTime(bSeconds, reason: reason, triggerStart: triggerStart)
        let replacement = reason == .writerFailure
        if let old, old != n, let ow = writers[old] {
            if ow.hasFailed {
                writers[old] = nil       // 已失敗的舊段不轉 prev、不收尾（R2 行為）
            } else {
                segEnd[old] = b
            }
        }

        // 尺寸：換段當下同步讀會議視窗大小，經 nextSegmentSize 算出（讀不到沿用上一次讀到的；design §7.1、spec §4.3.6）。
        // 畫布鎖定（meeting-speed spec §4.4.1）：每段都以開錄時的 curSize 開檔，視窗尺寸改變只寫一行 log，
        // 不改 SCStreamConfiguration 的寬高（內容由 preservesAspectRatio 等比縮放進同一張畫布）。
        if reason != .first {
            let size = nextSegmentSize(windowPoints: windowPointSize(window.windowID), scale: scale, previous: windowSize)
            if size != windowSize {
                log.line("● 視窗尺寸改變：\(windowSize.width)×\(windowSize.height) → \(size.width)×\(size.height)（畫布維持開錄時的 \(curSize.width)×\(curSize.height)，內容等比縮放）")
                windowSize = size
            }
        }

        let requested = reason == .first ? 0 : round3(now())     // 排程器只在從沒開過段時給 .first
        lastSegmentStart = b
        guard let seg = openSegment(index: n, start: b, requestedAt: requested, replacement: replacement) else { return }
        writers[n] = seg
        nextBoundary = CMTimeAdd(b, CMTime(seconds: Double(segmentSeconds), preferredTimescale: b.timescale))

        // 新段第一個視訊 sample：觸發換段的正是 PTS == 邊界的 complete 幀就直接寫它；
        // 否則把最後一個 complete 幀以邊界重新打戳寫進新段（design §7.2 第 3 步）。
        let triggerIsBoundaryFrame = trigger == .video && CMTimeCompare(triggerStart, b) == 0
        if reason != .first, !triggerIsBoundaryFrame, let lf = lastFrame, let copy = retimedVideoSample(lf, pts: b) {
            write(copy, track: .video, to: seg)
        }
        if pendingResumeEvent {
            pendingResumeEvent = false
            resumedSegmentOpened(at: b)
        }
    }

    // MARK: - 監看（計時；音量時段、磁碟與告警在 RecordingSession+Monitor.swift）

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
        // 輸出裝置變更（S-C、R3-D9；spec §4.36.8）：交給排程器，下一個 sample 提前換段（暫停中由繼續的換段吸收）
        if kind == .output, !stopping { dispatch(.outputDeviceChange) }
        // 預設輸入變更時以新裝置 UID 更新設定（SCK 是否自動跟隨未知，req:292）；只讀裝置，不改使用者的預設值
        if kind == .input, !stopping {
            cfg.microphoneCaptureDeviceID = to?.uid
            stream.updateConfiguration(cfg) { [weak self] err in
                if let err { self?.log.line("⚠ 換麥克風裝置失敗：\(err.localizedDescription)") }
            }
        }
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

    /// 暫停（design R2-D3 第 1 步）：交給排程器（目前段寫過 sample 就轉成 prev、只收 E 之前晚到的 sample，
    /// 1 秒後由 prevTimeout 收尾；r3-core 接線約定 1），偵測器停餵、記 pause 事件與狀態欄位。
    private func pauseRecording() {
        guard !gate.paused else { return }
        let c = scheduler.current
        let e: CMTime? = maxEnd.isValid ? maxEnd : c.flatMap { writers[$0]?.start }
        let prevBefore = scheduler.prev
        pendingResumeEvent = false
        for action in scheduler.handle(.pause) {
            switch action {
            case let .finish(n): finishScheduled(n)
            case let .cancel(n): closeAtCut(n, at: e, keepAsPrev: false)
            case .open, .write, .drop: break
            }
        }
        // 目前段轉成 prev：照 R2 的實體檢查（已失敗、E 不晚於段起點或沒寫進任何 sample → 不留作 prev）
        if let c, scheduler.prev == c { closeAtCut(c, at: e, keepAsPrev: true) }
        armPrevTimeout(since: prevBefore)
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
        dispatch(.resume)
        sysSilence.reset()
        micSilence.reset()
        suspended.reset()
        let provisional = appendingPauseEvent(meta.pauseEvents ?? [], kind: .resume, t: now(),
                                              firstSegmentStart: firstSegmentStart, wallClock: isoNow())
        let fields = pauseStatusFields(provisional)
        status.update { $0 = applyingPauseFields(fields, to: $0) }
        log.line("● 繼續錄製（等下一個 sample 開新段）")
    }

    /// 繼續後的新段已開：記 resume 事件（t＝新段 startedAt）。閘門回到一般狀態由排程器在開段時處理。
    private func resumedSegmentOpened(at b: CMTime) {
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
    /// 已在停止中時：收尾中（phase=finalizing）再收到停止訊號＝取消收尾（spec §4.28.6、§4.41.6）；
    /// 收尾前的停止階段與內部來源（磁碟、串流、寫檔失敗）的重複呼叫則略過。
    func requestStop(fromSignal: Bool = false) {
        if stopping {
            if fromSignal, let runner = finalizeRunner {
                log.line("● 收尾中再收到停止訊號：取消收尾")
                runner.cancel()
            } else if fromSignal {
                log.line("● 停止中（還沒進收尾），略過這次停止訊號")
            }
            return
        }
        log.line("● 開始優雅停止")
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

    // MARK: - 收尾（收掉 writer 與 F2 捨棄在 RecordingSession+Stop.swift）

    func beginFinalize() {
        levelsTimer?.cancel()
        closeLevels(final: true)
        deviceMonitor?.stop()
        lastFrame = nil
        manifest.blackIntervals = roundedBlack()
        writeManifest()
        writeMeta()
        // 內部旗標 --skip-finalize（首次引導試錄；spec R3-§6 第 144 條）：不跑 _record_finalize.py，直接結束
        if ctx.skipFinalize {
            log.line("● 依 --skip-finalize 跳過收尾（\(finishedSegments) 段）")
            complete(finalizeCode: 0, skipped: true)
            return
        }
        // 第 1 步
        let n = finishedSegments
        // 第 2 步：runId 合格才試每場鎖；判斷交 Core backgroundEntryDecision（spec R3x §3.23、§3.26）
        let runIdOK = backgroundRunIdAllowed(ctx.runId)
        let perRunLock: MenuBarLockResult? = runIdOK ? tryFlock(at: backgroundLockURL(home: ctx.home, runId: ctx.runId)) : nil
        let entry = backgroundEntryDecision(runIdAllowed: runIdOK, lock: perRunLock)
        let background: Bool
        if entry == .background, case .acquired(let fd)? = perRunLock {
            backgroundLockFD = fd
            background = true
        } else {
            if case .foreground(let reason) = entry {
                log.line("⚠ 不能進背景收尾（\(reason)），改在前景收尾")
            }
            background = false
        }
        if background {
            // 第 3、4 步：之後的寫入照 §3.24；這一次仍持有 record.lock，共用狀態檔一定寫入
            status.enterBackground(home: ctx.home)
            status.update {
                $0.phase = .finalizing
                $0.segments = n
                $0.message = "收尾排隊中"
                $0.background = true
                $0.queued = true
            }
            // 第 5 步：record.pid 內容是自己才刪（此時仍持有 record.lock）
            let pidText = try? String(contentsOf: ctx.pidURL, encoding: .utf8)
            if shouldRemoveRecordPid(pidFileContents: pidText, ownPid: getpid()) {
                try? FileManager.default.removeItem(at: ctx.pidURL)
            }
            // 第 6 步：清掉過期的終態與孤兒（§3.21 清理 (1)）
            let fm = FileManager.default
            for job in loadBackgroundJobs(home: ctx.home)
            where prunableBackgroundJob(job, now: Date()) && backgroundRunIdAllowed(job.status.runId) {
                try? fm.removeItem(at: backgroundStatusURL(home: ctx.home, runId: job.status.runId))
                try? fm.removeItem(at: backgroundLockURL(home: ctx.home, runId: job.status.runId))
            }
            // 第 7 步：放開開錄鎖，從這裡起下一場可以開錄
            releaseRecordLock()
            log.line("● 已放開開錄鎖：收尾改在背景跑，可以開始下一場（\(n) 段）")
        } else {
            // 前景收尾：照 R3 現行流程（不放 record.lock、不寫每場狀態檔）
            status.update {
                $0.phase = .finalizing
                $0.segments = n
                $0.message = "收尾中"
            }
            log.line("● 收尾中（\(n) 段）")
        }
        // 第 8 步：收尾中（含排隊中）的停止訊號照 §4.28.6 轉成 runner.cancel()
        let runner = FinalizeRunner(recordedSeconds: recordedSecondsAtStop(), log: log)
        // 音訊先出（meeting-speed spec §4.2.8）：收尾印出「音訊就緒：」那一行時，狀態檔 audioReady 設 true（phase 維持 finalizing）
        runner.onAudioReady = { [weak self] in self?.status.update { $0.audioReady = true } }
        finalizeRunner = runner
        DispatchQueue.global(qos: .userInitiated).async {
            if background {
                // 第 9 步：排隊；排隊中被取消 → 不啟動 _record_finalize.py
                guard self.waitFinalizeQueue(runner) else {
                    self.q.async { self.complete(finalizeCode: 5, aborted: .cancelled) }
                    return
                }
                // 第 10 步
                self.status.update {
                    $0.queued = nil
                    $0.message = "收尾中"
                }
                self.log.line("● 收尾中（\(n) 段）")
            }
            let result = self.runFinalize(runner)
            self.q.async {
                switch result {
                case .exited(let rc): self.complete(finalizeCode: rc)
                case .aborted(let reason): self.complete(finalizeCode: 5, aborted: reason)
                }
            }
        }
    }

    /// 背景收尾排隊（spec R3x §3.22、§3.23 第 9 步）：每 finalizeQueuePollSeconds 以 tryFlock 試排隊鎖一次，
    /// 每一輪由 Core queueWaitStep 決定（先看取消、再試鎖）；不用阻塞的 flock，排隊中收到取消才能立刻離開。
    /// 取得 → 持有到程序結束、回 true；開不了鎖檔 → 記一行、不排隊、回 true；被取消 → 回 false。不得在 q 上呼叫。
    private func waitFinalizeQueue(_ runner: FinalizeRunner) -> Bool {
        let lockURL = finalizeQueueLockURL(home: ctx.home)
        var announced = false
        while true {
            switch queueWaitStep(cancelRequested: runner.isCancelRequested, tryLock: { tryFlock(at: lockURL) }) {
            case .acquired(let fd):
                queueLockFD = fd
                return true
            case .retry:
                if !announced {
                    announced = true
                    log.line("● 等上一場收尾完成（排隊中）")
                }
                usleep(useconds_t(finalizeQueuePollSeconds * 1_000_000))
            case .unavailable(let e):
                log.line("⚠ 開不了排隊鎖 finalize.queue.lock（errno \(e)），不排隊、直接收尾")
                return true
            case .cancelled:
                log.line("● 排隊中收到取消，不啟動收尾")
                return false
            }
        }
    }

    /// 以 FinalizeRunner spawn "<python3>" "<harness>/bin/_record_finalize.py" "<場次>"；輸出逐行寫進 record.log；
    /// 超過 finalizeDeadline 或被取消時由 FinalizeRunner 中止（spec §4.28.6）。
    private func runFinalize(_ runner: FinalizeRunner) -> FinalizeRunResult {
        guard let harness = ctx.harness ?? defaults?.harness, !harness.isEmpty else {
            log.line("✗ 不知道 meeting-harness 的路徑（--harness 與 record.defaults.json 都沒有），無法收尾")
            return .exited(127)
        }
        let script = URL(fileURLWithPath: harness).appendingPathComponent("bin/_record_finalize.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            log.line("✗ 找不到 \(script.path)，無法收尾")
            return .exited(127)
        }
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        if let ff = defaults?.ffmpeg, !ff.isEmpty { env["MH_FFMPEG"] = ff }
        // 收尾子程序讀同一個 home（spec R3x §3.23 第 10 步）；背景路徑才等收尾鎖（§3.25、§6 第 156 條），前景不設
        env["MH_RECORD_HOME"] = ctx.home.path
        if backgroundLockFD != nil {
            env["MH_FINALIZE_WAIT_LOCK"] = "1"
        } else {
            env.removeValue(forKey: "MH_FINALIZE_WAIT_LOCK")
        }
        return runner.run(executable: URL(fileURLWithPath: defaults?.python3 ?? "/usr/bin/python3"),
                          arguments: [script.path, ctx.session.path], environment: env)
    }

    /// 最終結果一律由 Core completionOutcome 決定：停止原因（forced）在開頭，收尾失敗附在其後（spec §4.4.7、§4.4.9）。
    /// 收尾被 FinalizeRunner 中止（逾時、取消）時改用 finalizeAbortOutcome：phase=failed、code=5（spec §4.28.6）。
    /// skipped（--skip-finalize）：沒有跑收尾，phase 照 completionOutcome 的非失敗分支（done），code 0 時改寫訊息；
    /// 不發完成通知（spec R3-§6 第 144 條）。
    private func complete(finalizeCode rc: Int32, aborted: FinalizeAbort? = nil, skipped: Bool = false) {
        let base = aborted.map { finalizeAbortOutcome($0, forcedMessage: forced?.message, sessionPath: ctx.session.path) }
            ?? completionOutcome(finalizeCode: rc, forcedCode: forced?.code, forcedMessage: forced?.message,
                                 hadError: hadError, sessionPath: ctx.session.path)
        let outcome = skipped && base.code == 0
            ? CompletionOutcome(phase: .done, code: 0, message: "已停止，依 --skip-finalize 跳過收尾：\(ctx.session.path)")
            : base
        status.update {
            $0.phase = outcome.phase
            $0.code = outcome.code
            $0.message = outcome.message
        }
        // record.pid 內容是自己才刪：背景收尾時它可能已是下一場的（spec R3x §3.23 第 11 步、§4.49.4）
        let pidText = try? String(contentsOf: ctx.pidURL, encoding: .utf8)
        if shouldRemoveRecordPid(pidFileContents: pidText, ownPid: getpid()) {
            try? FileManager.default.removeItem(at: ctx.pidURL)
        }
        log.line(outcome.code == 0 ? "✓ \(outcome.message)" : "✗ \(outcome.message)")
        // 試錄（--skip-finalize）不發完成通知：暫存場次不是使用者的會議（實機缺陷 F1）
        guard !ctx.skipFinalize else { exit(outcome.code) }
        // 通知內文只用場次代號，不含場次名、路徑或結果訊息（meeting-speed spec §4.12.3；詳情在 record.log）
        let label = sessionCodeLabel(startedAt: status.status.startedAt, runId: ctx.runId)
        Notifier.post(title: outcome.code == 0 ? "會議錄製完成" : "會議錄製結束（有錯誤）",
                      body: completionNotificationBody(ok: outcome.code == 0, label: label),
                      identifier: completionNotificationID(runId: ctx.runId))
        exit(outcome.code)
    }
}

/// SCStreamError.userStopped（-3817）：使用者從系統的畫面錄製指示（選單列紫色圖示）停止擷取。
func isUserStoppedStream(_ error: Error) -> Bool {
    let e = error as NSError
    return e.domain == SCStreamErrorDomain && e.code == SCStreamError.Code.userStopped.rawValue
}

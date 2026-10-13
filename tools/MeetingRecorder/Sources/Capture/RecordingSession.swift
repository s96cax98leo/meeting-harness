// Capture/RecordingSession.swift —— 正式錄製：擷取、自管 AVAssetWriter 的 60 秒分段、監看、優雅停止、finalize 觸發
// （design §7.1–§7.6；spec §3.2、§3.3、§4.2.11、§4.3、§4.4、§4.5）
//
// 執行緒：所有可變狀態（含 SegmentWriter）只在序列佇列 q 上讀寫；SCK 的回呼在各自佇列，一律 q.async 回來。
// 時間：
//   - sample 時鐘：SCK sample 的 PTS（host clock）。writer 的 session 時間軸直接用 PTS（design §7.2）。
//   - manifest／levels 的秒數＝PTS 秒數 − t0（t0＝startCapture 前一刻的 host clock），寫檔時取小數 3 位。
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
    private enum SwitchReason { case first, periodic, formatChange, writerFailure }

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
        super.init()
    }

    private var log: Logger { ctx.log }
    private func now() -> Double { hostSeconds() - t0 }
    private var manifestURL: URL { ctx.tracksDir.appendingPathComponent("manifest.json") }
    private var metaURL: URL { ctx.tracksDir.appendingPathComponent("record.meta.json") }

    // MARK: - 開始

    func start() async {
        do {
            try FileManager.default.createDirectory(at: ctx.tracksDir, withIntermediateDirectories: true)
        } catch {
            fail(code: 5, "建不了 \(ctx.tracksDir.path)：\(error.localizedDescription)")
        }
        installSignalHandlers()

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
        status.update {
            $0.phase = .recording
            $0.code = 0
            $0.message = "錄製中"
        }

        q.sync {
            let devices = meta.devices
            let mon = AudioDeviceMonitor(queue: q) { [weak self] kind, from, to in self?.deviceChanged(kind, from, to) }
            mon.start(initial: devices)
            deviceMonitor = mon
            levelsTimer = repeating(0.5) { [weak self] in self?.closeLevels() }
            timers.append(repeating(30) { [weak self] in self?.checkDisk() })
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
    }

    // MARK: - SCStreamDelegate

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        q.async {
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
            let fmt = audioFormat(of: sb)
            let db = rmsDBFS(sampleBuffer: sb)
            let end = audioEnd(sb, pts: pts, format: fmt)
            q.async {
                let changed = self.onAudio(src, t: t, format: fmt, dbfs: db)
                guard pts.isValid else { return }
                self.ingest(sb, track: src == .system ? .system : .mic, start: pts, end: end,
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
            if suspended.feed(t: t, status: st) {
                warn(.suspended, "會議視窗的擷取已暫停超過 5 秒（多半是被最小化）：把視窗還原")
            }
        }
        if let ratio, black.feed(t: t, nonBlackRatio: ratio) {
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
        if stopPoint == nil, !maxEnd.isValid || CMTimeCompare(end, maxEnd) > 0 { maxEnd = end }
        if !firstSampleLogged {
            firstSampleLogged = true
            let offset = start.seconds - hostSeconds()
            log.line("● 第一個 sample：PTS − host clock = \(String(format: "%.3f", offset)) 秒")
            if abs(offset) > 1 { log.line("⚠ 第一個 sample 的 PTS 與 host clock 相差超過 1 秒（\(String(format: "%.3f", offset)) 秒）") }
        }

        if !stopping {
            if cur == nil || switchOnNextSample {
                // 第一段：B_1＝第一個 sample 的 PTS。writer 失敗後的新段：以下一個 sample 的 PTS 當邊界，
                // 但不早於上一段的起點（同一個時間點不會出現兩段重疊）。
                let b = lastSegmentStart.isValid && CMTimeCompare(start, lastSegmentStart) < 0 ? lastSegmentStart : start
                startNewSegment(boundary: b, reason: everOpened ? .writerFailure : .first, trigger: track, triggerStart: start)
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
        for p in sysPeak.close(upTo: t) {
            manifest.levels.system.append(round1OrNil(p))
            if sysSilence.feed(t: Double(manifest.levels.system.count) * 0.5, dbfs: p) {
                warn(.silenceSystem, "系統聲音已連續 15 秒幾乎沒有聲音（低於 -60 dBFS）：檢查會議 app 的輸出與音量")
            }
        }
        for p in micPeak.close(upTo: t) {
            manifest.levels.mic.append(round1OrNil(p))
            if micSilence.feed(t: Double(manifest.levels.mic.count) * 0.5, dbfs: p) {
                warn(.silenceMic, "麥克風已連續 15 秒幾乎沒有聲音（低於 -60 dBFS）：檢查麥克風是否被拔掉或靜音")
            }
        }
    }

    private func deviceChanged(_ kind: DeviceKind, _ from: AudioDeviceInfo?, _ to: AudioDeviceInfo?) {
        let t = round3(now())
        meta.deviceEvents.append(DeviceEvent(t: t, kind: kind, from: from, to: to))
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
                      body: outcome.code == 0 ? ctx.session.path : "\(outcome.message)\n\(ctx.session.path)")
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

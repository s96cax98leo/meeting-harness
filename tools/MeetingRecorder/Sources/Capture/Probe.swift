// Capture/Probe.swift —— 第 0 階段的 probe 子指令（保留，量測可重跑）
// 回答：用 ScreenCaptureKit 的單視窗擷取，切換 Space 時會不會黑畫面。同時看 SCFrameStatus 與實際非黑比例
// （Chromium 停止重繪時 status 仍可能是 complete，只有看像素才分得出來）。
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

final class ProbeOutput: NSObject, SCStreamOutput, SCStreamDelegate, SCRecordingOutputDelegate {
    private let log: Logger
    private let started = Date()
    private var counts: [String: Int] = [:]
    private var blackFrames = 0
    private var totalSampled = 0
    private var lastCompleteAt: Date?

    init(log: Logger) { self.log = log }

    func stream(_ stream: SCStream, didOutputSampleBuffer sampleBuffer: CMSampleBuffer, of type: SCStreamOutputType) {
        guard type == .screen else { return }
        let t = Date().timeIntervalSince(started)
        let status = frameStatusKind(sampleBuffer)?.rawValue ?? "unknown"
        counts[status, default: 0] += 1
        if status == "complete" { lastCompleteAt = Date() }
        var ratioText = "—"
        if let ratio = lumaNonBlackRatio(sampleBuffer) {
            totalSampled += 1
            if ratio < 0.01 { blackFrames += 1 }
            ratioText = String(format: "%.3f", ratio)
        }
        let sinceComplete = lastCompleteAt.map { String(format: "%.1f", Date().timeIntervalSince($0)) } ?? "never"
        log.line(String(format: "t=%6.1fs  status=%-9@  nonBlackRatio=%@  sinceComplete=%@s",
                        t, status as NSString, ratioText, sinceComplete))
    }

    func summary() -> String {
        let order = ["complete", "idle", "blank", "suspended", "started", "stopped", "unknown"]
        let total = counts.values.reduce(0, +)
        var parts: [String] = []
        for k in order where (counts[k] ?? 0) > 0 {
            let n = counts[k]!
            parts.append("\(k)=\(n)（\(total > 0 ? n * 100 / total : 0)%）")
        }
        let blackPct = totalSampled > 0 ? blackFrames * 100 / totalSampled : 0
        return """

        ── 統計 ──
        幀狀態：\(parts.joined(separator: "  "))
        抽樣 \(totalSampled) 幀，其中 \(blackFrames) 幀幾乎全黑（\(blackPct)%）

        判讀：
          complete ≥80% 且非黑比例與基線相近  → 這個情境可用
          complete 但 nonBlackRatio <0.01     → app 停止重繪（只看 status 會誤判為正常）
          idle >95% 但最後一幀內容正確        → 可能只是畫面真的沒變，配合 probe.mov 人眼確認
          blank / 完全沒有幀                  → window server 沒有合成這個視窗
          suspended                           → 擷取暫停（官方承認的唯一情形：視窗被最小化）
        """
    }

    func stream(_ stream: SCStream, didStopWithError error: Error) {
        log.line("✗ stream 中斷：\(error.localizedDescription)")
    }

    func recordingOutput(_ recordingOutput: SCRecordingOutput, didFailWithError error: Error) {
        log.line("✗ 寫檔失敗：\(error.localizedDescription)")
    }

    func recordingOutputDidFinishRecording(_ recordingOutput: SCRecordingOutput) {
        log.line("✓ 寫檔完成")
    }
}

/// probe --window <windowID> [--seconds N] [--fps N] [--log <path>] [--mov <path>]
func cmdProbe(_ args: Args) async {
    guard let wantedID = args.int("window") else {
        die("✗ 用法: MeetingRecorder probe --window <windowID> [--seconds N] [--fps N] [--log <path>] [--mov <path>]\n"
            + "  先跑 MeetingRecorder windows 看 windowID", code: 2)
    }
    let seconds = args.int("seconds") ?? 30
    let fps = args.int("fps") ?? 2
    let log = Logger(path: args.str("log"))

    let content: SCShareableContent
    do {
        content = try await shareableContent()
    } catch {
        die("✗ 取不到視窗清單（螢幕錄製權限？）：\(error.localizedDescription)", code: 4, log: log)
    }
    guard let window = content.windows.first(where: { $0.windowID == CGWindowID(wantedID) }) else {
        die("✗ 找不到 windowID \(wantedID)。會議 app 重開過的話 windowID 會變，重跑 windows 再挑。", code: 3, log: log)
    }

    let app = window.owningApplication?.applicationName ?? "?"
    let bundle = window.owningApplication?.bundleIdentifier ?? "?"
    log.line("""
    ── probe ──
    視窗：[\(window.windowID)] \(app) — \(window.title ?? "")
    bundle：\(bundle)
    尺寸：\(Int(window.frame.width))×\(Int(window.frame.height))　onScreen=\(window.isOnScreen)　active=\(window.isActive)
    filter：SCContentFilter(desktopIndependentWindow:)　fps 上限=\(fps)　時長=\(seconds)s
    """)

    // 第 0 階段的量法：畫布鎖主顯示器完整像素（視窗中途被縮放時畫布不必改，最差只是留黑邊），保持可重跑比對
    let displayID = content.displays.first?.displayID ?? CGMainDisplayID()
    let canvas = displayPixelSize(displayID)
    let filter = SCContentFilter(desktopIndependentWindow: window)
    let cfg = SCStreamConfiguration()
    cfg.width = canvas.w
    cfg.height = canvas.h
    cfg.scalesToFit = true
    cfg.minimumFrameInterval = CMTime(value: 1, timescale: CMTimeScale(fps))
    cfg.pixelFormat = kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange
    cfg.showsCursor = true
    cfg.queueDepth = 6
    cfg.capturesAudio = false // probe 只驗畫面
    log.line("畫布：\(canvas.w)×\(canvas.h) px（鎖顯示器完整像素）")

    let out = ProbeOutput(log: log)
    let stream = SCStream(filter: filter, configuration: cfg, delegate: out)
    do {
        try stream.addStreamOutput(out, type: .screen, sampleHandlerQueue: DispatchQueue(label: "mh.probe.screen"))
    } catch {
        die("✗ addStreamOutput 失敗：\(error.localizedDescription)", code: 5, log: log)
    }

    // 低 fps 的 probe.mov 供人眼覆核（官方 header：必須在 startCapture 之前加掛）
    var recording: SCRecordingOutput?
    if let movPath = args.str("mov") {
        let rc = SCRecordingOutputConfiguration()
        rc.outputURL = URL(fileURLWithPath: movPath)
        rc.outputFileType = .mov
        rc.videoCodecType = .h264
        let r = SCRecordingOutput(configuration: rc, delegate: out)
        do {
            try stream.addRecordingOutput(r)
            recording = r
            log.line("覆核影片：\(movPath)")
        } catch {
            log.line("⚠ 加掛寫檔失敗，只做量測：\(error.localizedDescription)")
        }
    }

    do {
        try await stream.startCapture()
    } catch {
        die("""
            ✗ startCapture 失敗：\(error.localizedDescription)

            若訊息與權限有關：授權後「必須完全結束這個 app 再重開」才生效（Apple 官方 sample 明寫）。
            """, code: 4, log: log)
    }
    log.line("開始擷取。現在照情境操作（切 Space、全螢幕、遮住、最小化…），每一步口述時間點。\n")
    try? await Task.sleep(nanoseconds: UInt64(seconds) * 1_000_000_000)
    try? await stream.stopCapture()
    if let recording { try? stream.removeRecordingOutput(recording) }
    try? await Task.sleep(nanoseconds: 1_000_000_000) // 等最後的 buffer 與寫檔收尾
    log.line(out.summary())
    exit(0)
}

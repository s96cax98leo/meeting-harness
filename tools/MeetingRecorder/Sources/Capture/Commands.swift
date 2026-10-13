// Capture/Commands.swift —— app 子指令：windows、diagnose-windows、preflight、start（spec §3.5、§3.8.7、§3.8.9）
import Foundation
@preconcurrency import ScreenCaptureKit

let screenPermissionHelp = """
    這幾乎都是「螢幕錄製」權限還沒給。做法：
      1) open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"
      2) 把 MeetingRecorder 打開
      3) 一定要完全結束 MeetingRecorder 再重開（授權對已啟動的程式不生效）
    """

private func jsonText<T: Encodable>(_ value: T) -> String {
    let enc = JSONEncoder()
    enc.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
    return (try? enc.encode(value)).map { String(decoding: $0, as: UTF8.self) } ?? "[]"
}

/// windows [--json] [--ask-automation] --log <檔>：列出可錄的視窗（spec §3.8.7）。
/// 只有帶 --ask-automation 時才讓系統跳「允許控制 Google Chrome」授權框。
func cmdWindows(_ args: Args) async {
    let listing: WindowListing
    do {
        listing = try await WindowListing.load(askAutomation: args.has("ask-automation"))
    } catch {
        // 不寫 --log：record.sh 以「等不到輸出」判定為權限問題（結束碼 4，spec §2.2、§4.1.6）
        die("✗ 取不到視窗清單：\(error.localizedDescription)\n\n\(screenPermissionHelp)", code: 4)
    }
    let log = Logger(path: args.str("log"))
    let rows = listing.rows
    if args.has("json") {
        log.line(jsonText(rows))
        exit(0)
    }
    if rows.isEmpty {
        log.line("（沒有符合條件的視窗。若連一個都沒有，通常是螢幕錄製權限沒給。）")
    }
    for r in rows { log.line("[\(r.windowID)] \(r.label)") }
    log.line("")
    log.line("顯示器：")
    for d in listing.content.displays {
        let px = displayPixelSize(d.displayID)
        log.line("  [\(d.displayID)] \(d.width)×\(d.height) pt → \(px.w)×\(px.h) px")
    }
    if chromeAutomationHint(rows, include: ["not_authorized", "not_determined", "error"]) {
        log.line("")
        log.line(automationHintLine)
    }
    exit(0)
}

private struct DiagnoseOutput: Encodable {
    let automation: AutomationStatus
    let windows: [DiagnosedWindow]
}

/// diagnose-windows [--json] --log <檔>：列出每一個視窗（含被濾掉的與原因），不跳授權框（spec §3.8.9）。
func cmdDiagnoseWindows(_ args: Args) async {
    let listing: WindowListing
    do {
        listing = try await WindowListing.load(askAutomation: false)
    } catch {
        die("✗ 取不到視窗清單：\(error.localizedDescription)\n\n\(screenPermissionHelp)", code: 4)
    }
    let log = Logger(path: args.str("log"))
    let diag = listing.diagnosed
    if args.has("json") {
        log.line(jsonText(DiagnoseOutput(automation: listing.automation, windows: diag)))
        exit(0)
    }
    for d in diag {
        let mark = d.excludedBy.isEmpty ? "✓" : "✗ " + d.excludedBy.map { $0.rawValue }.joined(separator: ",")
        log.line("\(mark) [\(d.row.windowID)] \(d.row.label)  layer=\(d.layer)  @(\(d.x),\(d.y))")
    }
    log.line("automation: \(listing.automation.rawValue)")
    exit(0)
}

let preflightItemNames: [PreflightItem: String] = [
    .signing: "簽章身分", .screen_permission: "螢幕錄製權限", .relaunch_needed: "剛授權要重啟",
    .mic_permission: "麥克風權限", .system_audio_rms: "系統聲音 RMS", .mic_rms: "麥克風 RMS",
    .disk: "磁碟空間", .window_exists: "目標視窗存在", .session_collision: "場次撞名", .power: "電源",
    .already_running: "已有錄製在跑", .window_minimized: "視窗是否最小化", .apple_events: "Apple Events（Chrome 會議分頁標記）",
]

/// preflight／start 的參數（spec §3.5）。缺必要參數回 nil 與原因。
func runContext(from args: Args, log: Logger) -> (RunContext?, String) {
    let home = recordHome(args)
    let runId = args.str("run-id") ?? UUID().uuidString
    guard let w = args.str("window"), let wid = UInt32(w) else {
        return (nil, "缺 --window <id>（或不是數字）")
    }
    guard let s = args.str("session"), !s.isEmpty else { return (nil, "缺 --session <場次目錄>") }
    // --window-bundle 與 --window-title 要嘛都給、要嘛都不給；只給一個時只認 windowID（不猜）
    let bundle = args.str("window-bundle"), title = args.str("window-title")
    let ref = (bundle != nil && title != nil) ? WindowRef(windowID: wid, bundleID: bundle, title: title)
                                              : WindowRef(windowID: wid, bundleID: nil, title: nil)
    let defaults = RecordDefaults.load(home.appendingPathComponent("record.defaults.json"))
    let minFree = args.int64("min-free-bytes") ?? defaults?.minFreeBytes ?? fallbackMinFreeBytes()
    let ctx = RunContext(home: home, runId: runId, session: URL(fileURLWithPath: s, isDirectory: true),
                         minFreeBytes: minFree, windowRef: ref, harness: args.str("harness") ?? defaults?.harness, log: log)
    return (ctx, "")
}

/// preflight：只檢查（通過 → phase=done code=0；hard 失敗 → preflight_failed）。
/// start：先跑同一套 preflight，通過才開錄。
func cmdPreflight(_ args: Args, start: Bool) async {
    let home = recordHome(args)
    let log = Logger(path: home.appendingPathComponent("record.log").path, append: true)
    log.line("── \(start ? "start" : "preflight") \(isoNow()) ──")
    let (ctxOpt, why) = runContext(from: args, log: log)
    guard let ctx = ctxOpt else {
        // 沒有場次也要讓 record.sh 看得到結果（runId 相符的 preflight_failed，code 2）
        if let runId = args.str("run-id") {
            let now = isoNow()
            let st = RecordStatus(schemaVersion: 1, runId: runId, pid: getpid(), phase: .preflightFailed, code: 2,
                                  message: "參數不足：\(why)", session: args.str("session") ?? "", startedAt: now,
                                  updatedAt: now, segments: 0, preflight: [], warnings: [])
            try? writeJSONAtomically(st, to: home.appendingPathComponent("record.status.json"))
        }
        die("✗ 參數不足：\(why)", code: 2, log: log)
    }
    let defaults = RecordDefaults.load(ctx.defaultsURL)
    await runPreflightThenRecord(ctx, start: start, defaults: defaults, beforeRecording: nil)
}

func runPreflightThenRecord(_ ctx: RunContext, start: Bool, defaults: RecordDefaults?,
                            notifyWarnings: Bool = false,
                            beforeRecording: (() throws -> Void)?) async {
    let log = ctx.log
    let sw = StatusWriter(ctx: ctx)
    sw.update { $0.phase = .preflight; $0.message = "開錄前檢查中" }
    let outcome = await PreflightRunner.run(ctx)
    for r in outcome.results {
        let mark = r.ok ? "✓" : (r.severity == .hard ? "✗" : "⚠")
        let name = preflightItemNames[r.item] ?? r.item.rawValue
        log.line("\(mark) \(name)\(r.message.isEmpty ? "" : "：\(r.message)")")
    }
    let code = outcome.code
    if code != 0 {
        // 訊息首行＝決定結束碼的那一項；其餘 hard 失敗接在後面
        let failed = outcome.results.filter { !$0.ok && $0.severity == .hard }
        let ordered = failed.filter { $0.code == code } + failed.filter { $0.code != code }
        let text = ordered.map { "\(preflightItemNames[$0.item] ?? $0.item.rawValue)：\($0.message)" }.joined(separator: "\n")
        sw.update {
            $0.preflight = outcome.results
            $0.phase = .preflightFailed
            $0.code = code
            $0.message = text
        }
        log.line("✗ 開錄前檢查沒通過（結束碼 \(code)），不開錄")
        exit(code)
    }
    let warns = outcome.results.filter { !$0.ok }
    let warnText = warns.map { "\(preflightItemNames[$0.item] ?? $0.item.rawValue)：\($0.message)" }.joined(separator: "\n")
    if !start {
        sw.update {
            $0.preflight = outcome.results
            $0.phase = .done
            $0.code = 0
            $0.message = warns.isEmpty ? "開錄前檢查通過" : "開錄前檢查通過（有提示）\n\(warnText)"
        }
        log.line("✓ 開錄前檢查通過")
        exit(0)
    }
    sw.update {
        $0.preflight = outcome.results
        $0.message = warnText
    }
    // 幕前調度提醒（spec §4.2.12）：start／quick-start 開錄時同一句寫一行進 record.log
    if let notice = outcome.stageManagerNotice { log.line("⚠ \(notice)") }
    // quick-start 沒有終端機看得到 warn：送一則通知（設計審查 N-2）
    if notifyWarnings, let n = preflightWarnNotification(warnText: warnText) {
        Notifier.post(title: n.title, body: n.body, log: log)
    }
    guard let window = outcome.window else {
        sw.update { $0.phase = .preflightFailed; $0.code = 3; $0.message = "找不到要錄的視窗" }
        exit(3)
    }
    do {
        try beforeRecording?()
    } catch {
        sw.update { $0.phase = .failed; $0.code = 5; $0.message = "開錄前準備失敗：\(error.localizedDescription)" }
        exit(5)
    }
    // preflight 的 probe stream 剛停，音訊裝置（尤其藍牙在 A2DP／HFP 之間）可能還在釋放或重新協商：
    // 等 startCaptureSettleSeconds 才呼叫正式 startCapture()（design §7.6、spec §4.2.11）
    try? await Task.sleep(nanoseconds: UInt64(startCaptureSettleSeconds * 1_000_000_000))
    let session = RecordingSession(ctx: ctx, status: sw, window: window, preflight: outcome.results, defaults: defaults)
    retainedSession = session
    await session.start()
}

/// 錄製中的 session 要活到程序結束。
var retainedSession: RecordingSession?

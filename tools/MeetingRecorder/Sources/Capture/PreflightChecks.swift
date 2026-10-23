// Capture/PreflightChecks.swift —— preflight 的個別檢查（design §6；spec §4.2）
// 從 PreflightRunner.swift 拆出（meeting-speed spec §4.13.1），行為與訊息不變；第 5、6、12 項的 probe 量測、
// 第 11 項的鎖與 availableBytes 留在 PreflightRunner.swift（既有靜態測試釘在那支檔）。
import AVFoundation
import CoreGraphics
import Foundation
import IOKit.ps
@preconcurrency import ScreenCaptureKit
import Security

/// 各項結果（以項目為鍵）；PreflightRunner.run 依序填入，最後依 PreflightItem.allCases 排序。
typealias PreflightResults = [PreflightItem: PreflightResult]

extension Dictionary where Key == PreflightItem, Value == PreflightResult {
    /// ok／fail 兩態的結果；warn 等級（warnOnly）的結果由呼叫端直接建 PreflightResult。
    mutating func set(_ item: PreflightItem, _ ok: Bool, _ msg: String) {
        self[item] = PreflightResult(item: item, ok: ok, message: msg)
    }
}

extension PreflightRunner {
    /// 2、3 螢幕錄製權限／剛授權要重啟（hard 4，兩者訊息不同，PROBE-REPORT.md:51-53）。
    static func checkScreenPermission(preflightAccess: Bool, contentAvailable: Bool, into r: inout PreflightResults) {
        if !preflightAccess && !contentAvailable {
            r.set(.screen_permission, false, """
                沒有螢幕錄製權限。到 系統設定 › 隱私權與安全性 › 螢幕與系統錄音 打開 MeetingRecorder \
                （open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"），\
                然後完全結束 MeetingRecorder 再重開
                """)
            r.set(.relaunch_needed, true, "（螢幕錄製權限還沒給，先處理上一項）")
        } else if !contentAvailable {
            r.set(.screen_permission, true, "螢幕錄製已授權")
            r.set(.relaunch_needed, false, "螢幕錄製已授權但還沒生效：請完全結束 MeetingRecorder 再重開（授權對已啟動的程式不生效）")
        } else {
            r.set(.screen_permission, true, "螢幕錄製已授權")
            r.set(.relaunch_needed, true, "")
        }
    }

    /// 4 麥克風權限（hard 4）。
    static func checkMicPermission(into r: inout PreflightResults) async {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            r.set(.mic_permission, true, "麥克風已授權")
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .audio)
            if granted {
                r.set(.mic_permission, true, "麥克風已授權")
            } else {
                r.set(.mic_permission, false, "麥克風沒有授權：到 系統設定 › 隱私權與安全性 › 麥克風 打開 MeetingRecorder，然後完全結束 MeetingRecorder 再重開")
            }
        default:
            r.set(.mic_permission, false, "沒有麥克風權限：到 系統設定 › 隱私權與安全性 › 麥克風 打開 MeetingRecorder，然後完全結束 MeetingRecorder 再重開")
        }
    }

    /// 8 目標視窗存在（hard 3）：windowID 優先，找不到才以 (bundleID, 標題) 唯一認回（spec §3.8.8）。
    static func checkWindow(_ ctx: RunContext, content: SCShareableContent?,
                            into r: inout PreflightResults) -> (WindowResolution, SCWindow?) {
        var resolution: WindowResolution = .notFound
        var window: SCWindow?
        if let content {
            resolution = resolveWindow(ctx.windowRef, in: windowCandidates(content))
            switch resolution {
            case .exact(let id):
                window = content.windows.first { $0.windowID == id }
                r.set(.window_exists, true, "視窗 \(id) 存在")
            case .reidentified(let id):
                window = content.windows.first { $0.windowID == id }
                r.set(.window_exists, true, "視窗 ID 已由 \(ctx.windowRef.windowID) 變為 \(id)，以 app 與標題認回")
            case .notFound:
                r.set(.window_exists, false, "找不到視窗 \(ctx.windowRef.windowID)：會議視窗被關掉或換了 ID，請重新跑 meeting record 選一次")
            case .ambiguous:
                r.set(.window_exists, false, "有多個同 app、同標題的視窗，請重新用 meeting record 選")
            }
        } else {
            r.set(.window_exists, false, "取不到視窗清單（螢幕錄製權限），無法確認視窗 \(ctx.windowRef.windowID)")
        }
        return (resolution, window)
    }

    /// 13 Apple Events（warn，永不 hard；不跳授權框）。
    static func checkAppleEvents(into r: inout PreflightResults) async {
        let ae = await chromeAutomationStatus(askUserIfNeeded: false)
        if ae == .authorized {
            r.set(.apple_events, true, "Chrome 會議分頁標記可用（Apple Events 已授權）")
        } else {
            let why: String
            switch ae {
            case .chromeNotRunning: why = "Chrome 沒有開"
            case .notAuthorized: why = "沒有允許 MeetingRecorder 控制 Google Chrome"
            case .notDetermined: why = "還沒決定是否允許 MeetingRecorder 控制 Google Chrome"
            default: why = "查不到 Apple Events 狀態"
            }
            r.set(.apple_events, false, "會議分頁不會標記，不影響錄製（\(why)）。要開啟：系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome")
        }
    }

    /// 12（續）幕前調度提醒（spec §4.2.12）：只讀設定；開啟 → 同一項 warn，與「疑似最小化」並列時以「；」串接。
    /// 回傳提醒文字（沒開或讀不到為 nil），start／quick-start 開錄時寫進 record.log。
    static func applyStageManagerNotice(into r: inout PreflightResults) -> String? {
        let stageNotice = stageManagerNotice(globallyEnabled: stageManagerGloballyEnabled())
        if let stageNotice, let cur = r[.window_minimized] {
            let parts = (cur.ok ? [] : [cur.message]) + [stageNotice]
            r.set(.window_minimized, false, parts.joined(separator: "；"))
        }
        return stageNotice
    }

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

    static func checkSigning(home: URL, log: Logger? = nil) -> (Bool, String) {
        var code: SecCode?
        var staticCode: SecStaticCode?
        var info: CFDictionary?
        guard SecCodeCopySelf([], &code) == errSecSuccess, let code,
              SecCodeCopyStaticCode(code, [], &staticCode) == errSecSuccess, let staticCode,
              SecCodeCopySigningInformation(staticCode, SecCSFlags(rawValue: kSecCSSigningInformation), &info) == errSecSuccess,
              let dict = info as? [String: Any] else {
            // 提早 return 前留一行 log（meeting-speed spec §4.10.3）
            log?.line(stopPathLogLine(source: "preflight 簽章", reason: "讀不到自己的簽章資訊，第 1 項記為 warn"))
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

    static func checkPower(log: Logger? = nil) -> (Bool, String) {
        guard let blob = IOPSCopyPowerSourcesInfo()?.takeRetainedValue(),
              let list = IOPSCopyPowerSourcesList(blob)?.takeRetainedValue() as? [CFTypeRef] else {
            // 提早 return 前留一行 log（meeting-speed spec §4.10.3）
            log?.line(stopPathLogLine(source: "preflight 電源", reason: "讀不到電源資訊，略過電量檢查"))
            return (true, "")
        }
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

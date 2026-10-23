// Capture/RecordingSession+Stop.swift —— 停止時收掉所有 writer，以及 F2 捨棄（design §7.4；spec §4.42.3、§4.42.4）
// 從 RecordingSession.swift 拆出（meeting-speed spec §4.13.1），行為不變。只在 q 上呼叫。
import AVFoundation
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

extension RecordingSession {
    func drainWriters() {
        guard !writersDrained else { return }
        writersDrained = true
        // 排程器的 stop：先 finish prev，再 finish／cancel 目前段。目前段照 R2 的實體檢查在停止點 E 處理：
        // 已失敗 → 記失敗；E 不晚於段起點或沒寫進任何 sample → 捨棄（cancelWriting 會刪掉檔），不當成失敗；否則收尾於 E。
        let e = stopPoint ?? .zero
        let c = scheduler.current
        for action in scheduler.handle(.stop) {
            switch action {
            case let .finish(n), let .cancel(n):
                if n == c { closeAtCut(n, at: e, keepAsPrev: false) } else { finishScheduled(n) }
            case .open, .write, .drop:
                break
            }
        }
        // 防禦：排程器已不再指向、但還沒收掉的 writer（正常流程不會有）一律在記下的收尾點或 E 處理
        for n in writers.keys.sorted() { closeAtCut(n, at: segEnd[n] ?? e, keepAsPrev: false) }
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
    func checkStopDone() {
        guard stopping, writersDrained, closing.isEmpty, !finalizeStarted else { return }
        finalizeStarted = true
        if discarding {
            finishDiscard()
        } else {
            beginFinalize()
        }
    }

    /// 讀 record.discard.json 後刪掉（讀後刪，§3.15）；有效（discardRequestValid）才回 true。只在 q 上呼叫。
    func consumeDiscardRequest() -> Bool {
        guard FileManager.default.fileExists(atPath: discardURL.path) else { return false }
        let request = (try? Data(contentsOf: discardURL)).flatMap { try? JSONDecoder().decode(DiscardRequest.self, from: $0) }
        try? FileManager.default.removeItem(at: discardURL)
        if discardRequestValid(request, runId: ctx.runId, now: Date()) {
            log.line("● 捨棄請求有效：停止錄製、跳過收尾，錄音資料夾移到垃圾桶")
            return true
        }
        log.line("● record.discard.json 無效（runId 不符、過期或讀不懂），照一般停止收尾")
        return false
    }

    /// 段落都已收掉之後：不啟動收尾子程序，以 trashItem 把 <場次>/錄音/ 移到垃圾桶；
    /// <場次> 只剩 meeting.json（與 .DS_Store）時再把 <場次> 移到垃圾桶，使用者自己放的其他檔不碰（§7 疑慮 51）。
    /// 從不硬刪。成功 → done／0／discarded=true；錄音/ 移不動 → failed／5、檔案原地保留。
    func finishDiscard() {
        levelsTimer?.cancel()
        closeLevels(final: true)
        deviceMonitor?.stop()
        lastFrame = nil
        manifest.blackIntervals = roundedBlack()
        writeManifest()
        writeMeta()
        let fm = FileManager.default
        var trashed: NSURL?
        do {
            try fm.trashItem(at: ctx.recordingDir, resultingItemURL: &trashed)
        } catch {
            let message = "捨棄失敗：錄音資料夾移不到垃圾桶（\(error.localizedDescription)），檔案原地保留：\(ctx.recordingDir.path)"
            log.line("✗ \(message)")
            status.update {
                $0.phase = .failed
                $0.code = 5
                $0.message = message
            }
            try? fm.removeItem(at: ctx.pidURL)
            Notifier.post(title: "捨棄這次錄製失敗", body: "錄音資料夾移不到垃圾桶，檔案原地保留",
                          identifier: completionNotificationID(runId: ctx.runId))
            exit(5)
        }
        log.line("✓ 錄音資料夾已移到垃圾桶：\(trashed?.path ?? "（系統沒有回報位置）")")
        let left = (try? fm.contentsOfDirectory(atPath: ctx.session.path)) ?? []
        if left.contains("meeting.json"), Set(left).isSubset(of: ["meeting.json", ".DS_Store"]) {
            var sessionTrashed: NSURL?
            do {
                try fm.trashItem(at: ctx.session, resultingItemURL: &sessionTrashed)
                log.line("✓ 場次資料夾只剩 meeting.json，一併移到垃圾桶")
            } catch {
                // 錄音/ 已進垃圾桶，捨棄本身已完成；場次資料夾留在原地
                log.line("⚠ 場次資料夾移不到垃圾桶（\(error.localizedDescription)），留在原地")
            }
        }
        status.update {
            $0.phase = .done
            $0.code = 0
            $0.message = "已捨棄，錄音已移到垃圾桶"
            $0.discarded = true
        }
        try? fm.removeItem(at: ctx.pidURL)
        log.line("✓ 已捨棄這次錄製（沒有收尾、沒有成品）")
        Notifier.post(title: "已捨棄這次錄製", body: "錄音資料夾已移到垃圾桶，可從垃圾桶復原。",
                      identifier: completionNotificationID(runId: ctx.runId))
        exit(0)
    }
}

// Capture/RecordingSession+Segments.swift —— 段落 writer 的開檔、收段與失敗處理（只在 q 上呼叫；design §7.2、R3-D10）
// 開段／寫入／收段的判斷在 Core 的 SegmentScheduler（spec §4.36.10）；這裡只照排程器的動作操作 SegmentWriter。
// 從 RecordingSession.swift 拆出（meeting-speed spec §4.13.1），行為不變。
import AVFoundation
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

extension RecordingSession {
    /// 非 sample 事件（prev 逾時、writer 失敗、繼續、輸出裝置變更）：交給排程器，執行回傳的收段動作。
    func dispatch(_ e: SchedulerEvent) {
        let prevBefore = scheduler.prev
        for action in scheduler.handle(e) {
            switch action {
            case let .finish(n): finishScheduled(n)
            case let .cancel(n): closeAtCut(n, at: maxEnd.isValid ? maxEnd : nil, keepAsPrev: false)
            case .open, .write, .drop: break       // 非 sample 事件不開段、不寫入（spec §3.20）
            }
        }
        armPrevTimeout(since: prevBefore)
    }

    /// 排程器換上新的 prev 時，1 秒後送 prevTimeout（R2 的 1 秒收尾；prev 已被收掉時排程器回 []）。
    func armPrevTimeout(since before: Int?) {
        guard let p = scheduler.prev, p != before else { return }
        q.asyncAfter(deadline: .now() + 1.0) { [weak self] in self?.dispatch(.prevTimeout(segment: p)) }
    }

    func write(_ sb: CMSampleBuffer, track: SegmentTrack, to seg: SegmentWriter) {
        if seg.append(sb, to: track) == .failed { writerFailed(seg, seg.error) }
    }

    /// 排程器的邊界（Double 秒）還原成精確的 CMTime：依換段原因取對應的 PTS，與排程器的值一致才用，否則以秒數換算。
    func boundaryTime(_ seconds: Double, reason: SwitchReason, triggerStart start: CMTime) -> CMTime {
        let candidate: CMTime
        switch reason {
        case .periodic:
            candidate = nextBoundary
        case .first, .writerFailure, .resume:
            candidate = lastSegmentStart.isValid && CMTimeCompare(start, lastSegmentStart) < 0 ? lastSegmentStart : start
        case .formatChange, .outputDeviceChange:
            candidate = start
        }
        if candidate.isValid, abs(candidate.seconds - seconds) < 1e-6 { return candidate }
        log.line("⚠ 換段邊界對不上 sample 時鐘（\(String(format: "%.6f", seconds)) 秒），以秒數換算")
        return CMTime(seconds: seconds, preferredTimescale: start.isValid ? start.timescale : 1_000_000_000)
    }

    /// 建 writer、startWriting、startSession；失敗時依〈writer 失敗〉處理並回 nil。
    func openSegment(index: Int, start b: CMTime, requestedAt: Double, replacement: Bool) -> SegmentWriter? {
        let name = segmentFileName(index: index)
        let size = curSize
        manifest.segments.append(SegmentRecord(file: name, requestedAt: requestedAt, startedAt: round3(b.seconds - t0),
                                               finishedAt: nil, width: size.width, height: size.height, audioDuration: nil))
        segRow[index] = manifest.segments.count - 1
        writeManifest()
        let opened = replacement ? hostSeconds() : nil
        let seg: SegmentWriter
        do {
            seg = try SegmentWriter(directory: ctx.tracksDir, index: index, start: b, size: size, replacementOpenedAt: opened)
        } catch {
            openFailed(name, error, index: index, replacement: replacement)
            return nil
        }
        guard seg.begin() else {
            seg.failureReported = true
            openFailed(name, seg.error, index: index, replacement: replacement)
            return nil
        }
        log.line("● 開段 \(name)（\(size.width)×\(size.height) px、起點 \(String(format: "%.3f", b.seconds - t0)) 秒）")
        return seg
    }

    /// 開檔失敗：告訴排程器這段沒了（下一個 sample 以 writerFailure 開新段）；換上的新段又開不了就優雅停止。
    func openFailed(_ name: String, _ error: Error?, index: Int, replacement: Bool) {
        hadError = true
        let why = error?.localizedDescription ?? "未知錯誤"
        log.line("✗ \(name) 寫檔失敗：\(why)")
        warn(.segmentWriteFailed, "\(name) 寫檔失敗（開檔）：\(why)；檔案保留")
        dispatch(.writerFailed(segment: index))
        if replacement { stopForRepeatedFailure() }
    }

    /// 段落 writer 失敗（append 回 false、finishWriting 結果 failed、收尾逾時）：記告警、保留檔案；
    /// 目前的段落失敗就以下一個 sample 提前換段；10 秒內又失敗就優雅停止（design §7.2〈writer 失敗〉）。
    /// 停止中目前段失敗不換段（R2 行為），writer 留到停止收尾時再處理。
    func writerFailed(_ seg: SegmentWriter, _ error: Error?) {
        guard !seg.failureReported else { return }
        seg.failureReported = true
        hadError = true
        let why = error?.localizedDescription ?? "未知錯誤"
        log.line("✗ \(seg.file) 寫檔失敗：\(why)")
        let n = seg.index
        let tracked = writers[n] === seg
        if tracked, scheduler.prev == n {
            writers[n] = nil
            segEnd[n] = nil
            dispatch(.writerFailed(segment: n))
        }
        if tracked, scheduler.current == n, !stopping {
            writers[n] = nil
            if let opened = seg.replacementOpenedAt, hostSeconds() - opened < 10 {
                warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留")
                dispatch(.writerFailed(segment: n))
                stopForRepeatedFailure()
            } else {
                warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留，已換新段繼續錄")
                dispatch(.writerFailed(segment: n))
            }
        } else {
            warn(.segmentWriteFailed, "\(seg.file) 寫檔失敗：\(why)；檔案保留")
        }
    }

    func stopForRepeatedFailure() {
        forced = forced ?? (5, "段落連續寫檔失敗，已停止並收尾；已落盤段落保留")
        requestStop()
    }

    /// 排程器的 finish（prev 逾時、三路都過邊界、換段時收掉更早的 prev、暫停、停止）：在記下的收尾點收尾。
    func finishScheduled(_ n: Int) {
        guard let w = writers[n] else { return }        // 已失敗或已捨棄的段落：排程器的動作不再有對象
        guard let end = segEnd[n] else {
            closeAtCut(n, at: maxEnd.isValid ? maxEnd : nil, keepAsPrev: false)
            return
        }
        writers[n] = nil
        segEnd[n] = nil
        finishSegment(w, at: end)
    }

    /// 在停止點 E 處理一段（暫停把目前段轉 prev、停止收掉目前段；R2 的實體檢查）：
    /// writer 已失敗 → 記失敗；E 晚於段起點且寫過 sample → 收尾於 E（keepAsPrev 時改為記下 E、留給排程器當 prev）；
    /// 否則段落沒有內容 → cancelWriting 刪檔並從 manifest 移除。
    func closeAtCut(_ n: Int, at e: CMTime?, keepAsPrev: Bool) {
        guard let w = writers[n] else { return }
        if w.hasFailed {
            writers[n] = nil
            segEnd[n] = nil
            writerFailed(w, w.error)
        } else if let e, CMTimeCompare(e, w.start) > 0, w.appendedTotal > 0 {
            if keepAsPrev {
                segEnd[n] = e
            } else {
                writers[n] = nil
                segEnd[n] = nil
                finishSegment(w, at: e)
            }
        } else {
            writers[n] = nil
            segEnd[n] = nil
            w.cancel()
            if let row = segRow[w.index], row == manifest.segments.count - 1 {
                manifest.segments.removeLast()
                segRow[w.index] = nil
            }
            log.line("● \(w.file) 沒有內容，捨棄")
        }
    }

    /// endSession → markAsFinished → finishWriting；完成回呼回 q 記 finishedAt 或失敗。
    func finishSegment(_ seg: SegmentWriter, at end: CMTime) {
        closing[seg.index] = seg
        seg.finish(at: end) { [weak self] ok, err in
            guard let self else { return }
            self.q.async { self.segmentFinished(seg, ok: ok, error: err) }
        }
    }

    func segmentFinished(_ seg: SegmentWriter, ok: Bool, error: Error?) {
        guard closing.removeValue(forKey: seg.index) != nil else { return }     // 收尾逾時已處理過
        if ok {
            if let row = segRow[seg.index] { manifest.segments[row].finishedAt = round3(now()) }
            finishedSegments += 1
            // 丟幀＝影片 writer 未 ready 而丟掉的幀（編碼跟不上的訊號）；PTS 非遞增的丟棄是換段打戳的正常結果，不算
            droppedFramesTotal += seg.droppedVideoFrames
            manifest.blackIntervals = roundedBlack()
            writeManifest()
            let n = finishedSegments
            let dropped = droppedFramesTotal
            status.update {
                $0.segments = n
                $0.droppedFrames = dropped
            }
            log.line("✓ \(seg.file) 收尾（\(seg.size.width)×\(seg.size.height)；\(seg.dropSummary)）")
            startAsrWorkerIfNeeded()
        } else {
            writerFailed(seg, error)
        }
        checkStopDone()
    }
}

/// SegmentWriter 的軌道 → SegmentScheduler 的軌道（同樣三路）。
func schedulerTrack(_ t: SegmentTrack) -> SchedulerTrack {
    switch t {
    case .video: return .video
    case .system: return .system
    case .mic: return .mic
    }
}

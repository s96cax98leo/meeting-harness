// Capture/RecordingSession+Monitor.swift —— 監看（音量時段、格式變更、磁碟、告警）與 manifest／meta 落盤
// 從 RecordingSession.swift 拆出（meeting-speed spec §4.13.1），行為不變。只在 q 上呼叫。
import AVFoundation
import CoreMedia
import Foundation
@preconcurrency import ScreenCaptureKit

extension RecordingSession {
    /// 音訊緩衝的結束點＝PTS＋duration（duration 無效時以 frame 數／取樣率算）。
    func audioEnd(_ sb: CMSampleBuffer, pts: CMTime, format: AudioFormat?) -> CMTime {
        let d = CMSampleBufferGetDuration(sb)
        if d.isValid, d.seconds > 0 { return CMTimeAdd(pts, d) }
        let n = CMSampleBufferGetNumSamples(sb)
        if let rate = format?.sampleRate, rate > 0, n > 0 {
            return CMTimeAdd(pts, CMTime(value: CMTimeValue(n), timescale: CMTimeScale(rate)))
        }
        return pts
    }

    /// 回傳本緩衝的格式是否與該路上一個緩衝不同（design §7.5）。
    @discardableResult
    func onAudio(_ src: AudioSource, t: Double, format: AudioFormat?, dbfs: Double?) -> Bool {
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

    /// 每 0.5 秒由主機時鐘收斂一次時段；沒有緩衝的時段為 -∞（寫 null），再餵靜音偵測。
    /// 平時延後 0.3 秒收斂（音訊緩衝送達比 PTS 晚幾十毫秒，太早收斂會把有聲音的時段誤記成空的）；停止時收到底。
    func closeLevels(final: Bool = false) {
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
    func updateRecentLevels() {
        guard controlEnabled, !stopping, !gate.paused else { return }
        let t = now()
        guard t - lastRecentLevelsWrite >= 1.0 else { return }
        lastRecentLevelsWrite = t
        let sys = recentPeak(manifest.levels.system, count: 6)
        let mic = micMuted ? nil : recentPeak(manifest.levels.mic, count: 6)
        status.update { $0.recentLevels = RecentLevels(windowSeconds: 3, system: sys, mic: mic) }
    }

    func checkDisk() {
        guard let avail = PreflightRunner.availableBytes(ctx.session), avail < diskLowBytes else { return }
        warn(.diskLow, "磁碟可用空間低於 2 GB，已自動停止並收尾")
        forced = forced ?? (5, "磁碟可用空間低於 2 GB（剩 \(String(format: "%.2f", Double(avail) / 1e9)) GB），已自動停止並收尾；段落保留")
        requestStop()
    }

    func warn(_ kind: WarningKind, _ message: String) {
        let w = RecordWarning(t: round3(now()), kind: kind, message: message)
        log.line("⚠ \(message)")
        status.update { $0.warnings.append(w) }
    }

    func roundedBlack() -> [BlackInterval] {
        black.intervals.map { BlackInterval(start: round3($0.start), end: $0.end.map(round3)) }
    }

    /// 錄製長度（扣暫停）＝停止點 E 的錄製時鐘秒數 − 暫停總長（沒配對的暫停算到 E）；給 finalizeDeadline 用。
    func recordedSecondsAtStop() -> Double {
        let end = (stopPoint ?? maxEnd).isValid ? (stopPoint ?? maxEnd).seconds - t0 : now()
        let events = meta.pauseEvents ?? []
        var paused = pausedTotal(events)
        if let last = events.last, last.kind == .pause { paused += max(0, end - last.t) }
        return max(0, end - paused)
    }

    func writeManifest() {
        do { try writeJSONAtomically(manifest, to: manifestURL) } catch { log.line("⚠ 寫 manifest.json 失敗：\(error.localizedDescription)") }
    }

    func writeMeta() {
        do { try writeJSONAtomically(meta, to: metaURL) } catch { log.line("⚠ 寫 record.meta.json 失敗：\(error.localizedDescription)") }
    }
}

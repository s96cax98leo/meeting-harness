// Trigger/MenuBar+Discard.swift —— 捨棄這次錄製（F2；spec §4.42.2）。確認對話框在 Trigger/Discard.swift。
// meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出，行為不變。
import AppKit

extension MenuBarController {
    /// 只在錄製中（含暫停）可捨棄；已點過停止、收尾中與之後都不行
    func canDiscard(_ st: RecordStatus?) -> Bool {
        guard model.canStop, let st, st.phase == .recording else { return false }
        return st.runId != stopRequestedRunId
    }

    /// 先顯示確認對話框（打開期間錄製照常）；使用者按「捨棄並移到垃圾桶」後，再確認一次停止目標
    /// （stopTargetDecision，與「停止錄製」同一套），才寫 record.discard.json 並送 SIGTERM。
    /// 跳過收尾與移到垃圾桶由錄製實例做（§4.42.3）。按「繼續錄製」沒有任何副作用。
    @objc func discardRecording() {
        guard let st = status, canDiscard(st) else { return }
        let runId = st.runId
        guard confirmDiscard(spokenDuration: model.spokenDuration) else { return }
        // 對話框開著的期間錄製可能已經結束或換了一場：只對同一場、仍在錄製中的實例捨棄
        let current = readStatus(statusURL)
        guard let current, current.runId == runId, current.phase == .recording else {
            notify(title: "MeetingRecorder 沒有捨棄錄製", body: "這次錄製已經停止或在收尾，沒有捨棄", kind: .failure,
                   runId: runId)
            return
        }
        let recordPid = readPid(pidURL)
        let decision = stopTargetDecision(lockHeld: recordLockHeld(), recordPid: recordPid,
                                          pidAlive: recordPid.map(pidAlive) ?? false, statusPid: current.pid,
                                          command: recordPid.flatMap(executablePath))
        guard case .signal = decision else {
            performStop(decision, current: current)   // 拒絕：說明原因、不送任何訊號
            return
        }
        do {
            try writeDiscardRequest(home: home, runId: runId)
        } catch {
            notify(title: "MeetingRecorder 沒有捨棄錄製", body: "寫 \(discardRequestFileName) 失敗：\(error.localizedDescription)",
                   kind: .failure, runId: runId)
            return
        }
        Logger(path: logURL.path, append: true).line("\(isoNow()) 使用者確認捨棄這次錄製：送 SIGTERM")
        performStop(decision, current: current)
    }
}

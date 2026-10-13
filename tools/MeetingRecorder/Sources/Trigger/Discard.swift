// Trigger/Discard.swift —— F2 捨棄這次錄製：確認對話框與 record.discard.json（spec §3.15、§4.42.2；design-r3/README.md §5）
// 外觀用系統 NSAlert（§7 疑慮 53）：先 NSApp.activate（accessory app 不先帶到前面，對話框會被別的視窗蓋住）。
// 對話框打開期間錄製照常（錄製是另一個 process）；按「繼續錄製」沒有任何副作用。
// 使用者按「捨棄並移到垃圾桶」後，呼叫端才寫 record.discard.json 並送 SIGTERM；移到垃圾桶由錄製實例做（§4.42.3）。
import AppKit

/// <home>/record.discard.json（spec §3.15）：menu bar 寫（tmp＋rename），錄製實例讀後刪。
let discardRequestFileName = "record.discard.json"

/// 顯示 F2 確認對話框；回 true＝使用者按了「捨棄並移到垃圾桶」。
/// spokenDuration＝menuBarModel 的口語計時（例「已錄 42 分 7 秒」）。不顯示場次名稱與路徑。
func confirmDiscard(spokenDuration: String) -> Bool {
    NSApp.activate(ignoringOtherApps: true)
    let alert = NSAlert()
    alert.alertStyle = .warning
    alert.icon = NSApp.applicationIconImage     // app 圖示（U7）
    alert.messageText = "捨棄這次錄製？"
    alert.informativeText = "\(spokenDuration)。會停止錄製、不收尾、不產生成品；這場的錄音資料夾會移到垃圾桶，可從垃圾桶復原。"
    // 第一顆＝預設鍵（Return）
    let keep = alert.addButton(withTitle: "繼續錄製")
    keep.keyEquivalent = "\r"
    // 第二顆：破壞性動作，沒有快捷鍵（Return、Esc 都按不到）
    let discard = alert.addButton(withTitle: "捨棄並移到垃圾桶")
    discard.hasDestructiveAction = true
    discard.keyEquivalent = ""
    return alert.runModal() == .alertSecondButtonReturn
}

/// 寫 <home>/record.discard.json（tmp＋rename 原子寫入）；requestedAt＝現在（ISO 8601 含時區）。
func writeDiscardRequest(home: URL, runId: String, now: Date = Date()) throws {
    let req = DiscardRequest(schemaVersion: 1, runId: runId, requestedAt: isoNow(now))
    try writeJSONAtomically(req, to: home.appendingPathComponent(discardRequestFileName))
}

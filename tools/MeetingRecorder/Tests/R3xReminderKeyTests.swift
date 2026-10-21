// spec R3x §6 第 160 條（Core/ReminderKey.swift）：提醒事項去重鍵用正規化 URL。
// EKReminder.url 存回的是 URL(string:) 正規化後的字串（空白、方括號、中文都會變成 %XX），
// 所以查詢與寫入都要用同一個正規化結果，重跑才會 created=0（spec §4.34.3）。
// 範例名稱一律「[Stand-up] 範例專案」。
import Foundation

// 與 Capture/Reminders.swift 的 reminderURLPrefix 相同（Capture 不編進測試執行檔）
let mrtReminderPrefix = "meetingharness://action/"

func mrtKey(_ raw: String) -> (key: String, url: URL)? { reminderURLKey(raw, prefix: mrtReminderPrefix) }

let mrtR3xReminderKeyTests: [MRTCase] = [
    ("testReminderKeyPlainUid", testReminderKeyPlainUid),
    ("testReminderKeyMatchesStoredURL", testReminderKeyMatchesStoredURL),
    ("testReminderKeyIdempotent", testReminderKeyIdempotent),
    ("testReminderKeyRejectsOtherScheme", testReminderKeyRejectsOtherScheme),
]

func testReminderKeyPlainUid() {
    let raw = mrtReminderPrefix + "abc-123"
    mrtEqual(mrtKey(raw)?.key, raw)
    mrtEqual(mrtKey(raw)?.url.absoluteString, raw)
}

func testReminderKeyMatchesStoredURL() {
    // 含空白、方括號、中文的 uid：EventKit 存回的是 URL.absoluteString（已編碼）
    for uid in ["[Stand-up] 範例專案#3", "20261017 範例 專案/交辦 1", "中文 uid"] {
        let raw = mrtReminderPrefix + uid
        guard let first = mrtKey(raw) else { mrtFail("回傳 nil：\(uid)", file: #fileID, line: #line); continue }
        // 模擬「寫入後從 EKReminder.url 讀回」：讀回的字串就是 url.absoluteString
        let stored = first.url.absoluteString
        mrtEqual(mrtKey(stored)?.key, first.key, "uid=\(uid)")
        mrtEqual(first.key, stored, "uid=\(uid)")
        // 舊寫法拿原始字串當查詢鍵：和讀回的字串不同，所以永遠對不上（本測試要防的回歸）
        mrtExpect(raw != stored, "uid=\(uid) 應被正規化")
        mrtExpect(first.key.hasPrefix(mrtReminderPrefix), "uid=\(uid)")
    }
}

func testReminderKeyIdempotent() {
    let raw = mrtReminderPrefix + "[Stand-up] 範例專案"
    let k1 = mrtKey(raw)?.key ?? ""
    let k2 = mrtKey(k1)?.key ?? "x"
    mrtEqual(k2, k1)
}

func testReminderKeyRejectsOtherScheme() {
    mrtExpect(mrtKey("https://example.com/x") == nil)
    mrtExpect(mrtKey("") == nil)
}

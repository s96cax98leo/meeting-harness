// Core/ReminderKey.swift —— 提醒事項去重鍵（spec §3.19、§4.34.3；R3x §6 第 160 條）
//
// EKReminder.url 讀回的是 URL(string:) 正規化後的 absoluteString：uid 含空白、方括號或中文時會變成 %XX。
// 查詢鍵與寫入鍵都必須走同一個正規化，否則重跑永遠對不上、每次都重複新增。
// 前綴（meetingharness://action/）由呼叫端傳入：常數 reminderURLPrefix 留在 Capture/Reminders.swift。
import Foundation

/// 把項目或現有提醒事項的 URL 字串正規化成去重鍵。
/// 回傳 (key, url)：key 一律是 url.absoluteString；不是 prefix 開頭或無法建 URL 時回 nil。
/// 對已正規化的字串再套一次結果不變（冪等）。
func reminderURLKey(_ raw: String, prefix: String) -> (key: String, url: URL)? {
    guard raw.hasPrefix(prefix), let url = URL(string: raw) else { return nil }
    let key = url.absoluteString
    guard key.hasPrefix(prefix) else { return nil }
    return (key, url)
}

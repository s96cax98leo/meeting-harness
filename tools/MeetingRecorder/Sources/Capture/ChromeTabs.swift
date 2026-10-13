// Capture/ChromeTabs.swift —— 以 Apple Events 唯讀查 Google Chrome 各視窗的標題、位置與分頁網址（spec §3.8.4；D16）
//
// 守則：
//   - 只查 com.google.Chrome；先確認 Chrome 在跑，沒在跑就不送任何 Apple Event（不得因查詢把 Chrome 開起來）。
//   - 權限以 AEDeterminePermissionToAutomateTarget 判斷；askUserIfNeeded 只有 windows --ask-automation 為 true。
//   - 腳本只用 get 取值，不切分頁、不執行 JavaScript、不開關視窗。以 NSAppleScript 在程序內執行（授權記在
//     MeetingRecorder 名下），不 spawn 外部腳本程式。整段逾時 5 秒，逾時或任何錯誤 → 回 nil（呼叫端記為 error）。
//   - 分頁網址只在記憶體中比對，不寫進任何 log、狀態檔或輸出。
import AppKit
import CoreServices
import Foundation

/// 全 Sources/ 唯一一段 Chrome 腳本。只讀：每個視窗的 title、bounds、作用中分頁網址、全部分頁網址。
let chromeTabsScript = """
with timeout of 5 seconds
    tell application id "com.google.Chrome"
        get {title of every window, bounds of every window, URL of active tab of every window, URL of every tab of every window}
    end tell
end timeout
"""

func chromeIsRunning() -> Bool {
    !NSRunningApplication.runningApplications(withBundleIdentifier: chromeBundleID).isEmpty
}

/// Chrome 沒在跑 → .chromeNotRunning（不送任何 Apple Event）；否則依 AEDeterminePermissionToAutomateTarget 對映。
func chromeAutomationStatus(askUserIfNeeded: Bool) async -> AutomationStatus {
    guard chromeIsRunning() else { return .chromeNotRunning }
    return await withCheckedContinuation { cont in
        // askUserIfNeeded 為 true 時會等使用者按授權框，放到背景佇列，不卡主執行緒。
        DispatchQueue.global(qos: .userInitiated).async {
            var target = AEAddressDesc()
            let bundle = Array(chromeBundleID.utf8)
            let made = bundle.withUnsafeBufferPointer { p in
                AECreateDesc(DescType(typeApplicationBundleID), p.baseAddress, p.count, &target)
            }
            guard made == noErr else { cont.resume(returning: .error); return }
            defer { AEDisposeDesc(&target) }
            let st = AEDeterminePermissionToAutomateTarget(&target, AEEventClass(typeWildCard),
                                                           AEEventID(typeWildCard), askUserIfNeeded)
            cont.resume(returning: automationStatus(fromOSStatus: st))
        }
    }
}

/// NSAppleScript 不是 thread-safe：一律在這條序列佇列上執行（design §8.3）。
private let chromeScriptQueue = DispatchQueue(label: "mh.chrome.applescript")

/// 只 resume 一次（腳本結果與逾時兩者競速）。
private final class ResumeOnce<T>: @unchecked Sendable {
    private let lock = NSLock()
    private var cont: CheckedContinuation<T, Never>?
    init(_ c: CheckedContinuation<T, Never>) { cont = c }
    func resume(_ v: T) {
        lock.lock(); let c = cont; cont = nil; lock.unlock()
        c?.resume(returning: v)
    }
}

/// 有授權時才呼叫。回傳 nil＝逾時（整段 5 秒）或任何錯誤（網址不落地，錯誤內容也不含網址）。
func queryChromeWindows() async -> [ChromeWindowInfo]? {
    guard chromeIsRunning() else { return nil }
    return await withCheckedContinuation { cont in
        let once = ResumeOnce<[ChromeWindowInfo]?>(cont)
        chromeScriptQueue.async { once.resume(runChromeTabsScript()) }
        DispatchQueue.global().asyncAfter(deadline: .now() + 5) { once.resume(nil) }
    }
}

private func runChromeTabsScript() -> [ChromeWindowInfo]? {
    guard let script = NSAppleScript(source: chromeTabsScript) else { return nil }
    var err: NSDictionary?
    let result = script.executeAndReturnError(&err)
    guard err == nil, result.numberOfItems == 4 else { return nil }
    guard let titles = result.atIndex(1), let bounds = result.atIndex(2),
          let actives = result.atIndex(3), let alls = result.atIndex(4) else { return nil }
    let n = min(titles.numberOfItems, bounds.numberOfItems, actives.numberOfItems, alls.numberOfItems)
    guard n > 0 else { return [] }
    var out: [ChromeWindowInfo] = []
    for i in 1...n {
        let title = titles.atIndex(i)?.stringValue ?? ""
        var rect = CGRect.zero
        if let b = bounds.atIndex(i), b.numberOfItems == 4 {
            let v = (1...4).map { Double(b.atIndex($0)?.int32Value ?? 0) }
            rect = CGRect(x: v[0], y: v[1], width: v[2] - v[0], height: v[3] - v[1])
        }
        let active = actives.atIndex(i)?.stringValue ?? ""
        var tabs: [String] = []
        if let list = alls.atIndex(i), list.numberOfItems > 0 {
            for j in 1...list.numberOfItems { tabs.append(list.atIndex(j)?.stringValue ?? "") }
        }
        out.append(ChromeWindowInfo(title: title, bounds: rect, activeTabURL: active, tabURLs: tabs))
    }
    return out
}

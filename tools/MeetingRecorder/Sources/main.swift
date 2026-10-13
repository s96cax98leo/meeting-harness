// MeetingRecorder —— meeting-harness 的錄製器
//
// 以 SCContentFilter(desktopIndependentWindow:) 錄下單一會議視窗（切到別的 Space 也錄得到），
// 同時錄系統聲音與麥克風，每 60 秒落一段 tracks/seg-NNNN.mov；收到 SIGTERM 時優雅停止並 spawn finalize。
// 一律以 `open -n -a MeetingRecorder --args <子指令> …` 啟動（TCC 的責任程序才會是這個 app）；
// stdout 無處可去，所以結果走 --log 或 ~/.meeting-harness/record.status.json（spec §3.1、§3.5）。
//
// 原始碼切分（design §9）：Core/ 純邏輯（可單元測試）、Capture/ 擷取與系統 API、Trigger/ menu bar 與快捷鍵。

import AppKit
import CoreGraphics
import Foundation

let helpText = """
MeetingRecorder —— meeting-harness 的錄製器（本機）

子指令（一律由 open -n -a MeetingRecorder --args <子指令> … 啟動；結果寫 --log 或狀態檔）
  windows [--json] [--ask-automation] --log <檔>
      列出可錄的視窗（★ 會議＝原生會議 app，或作用中分頁是會議網址的 Chrome 視窗）。
      --ask-automation：第一次會跳「允許控制 Google Chrome」授權框（只有終端機互動時才帶）。

  diagnose-windows [--json] --log <檔>
      列出每一個視窗（含被濾掉的與原因 layer／size）與 Apple Events 狀態；不跳授權框。

  probe --window <windowID> [--seconds 30] [--fps 2] [--log <檔>] [--mov <檔>]
      第 0 階段的量測：逐幀印出 SCFrameStatus 與畫面非黑比例。

  preflight --window <id> [--window-bundle <bundleID> --window-title <標題>] --session <場次目錄>
            --min-free-bytes <n> --run-id <uuid> --home <目錄>
      開錄前檢查 13 項（hard 失敗不開錄；warn 只提示），結果寫 record.status.json。

  start  （同 preflight 的參數 ＋ --harness <meeting-harness 目錄>）
      先跑 preflight，全部 hard 項通過才開錄；收到 SIGTERM 時優雅停止並收尾。

  quick-start [--home <目錄>] [--window <id> --window-bundle <bundleID> --window-title <標題>] [--root <存檔位置>]
      用上次 meeting record 留下的預設值開錄；沒帶 --window 時清單裡恰好一個 ★ 視窗才開錄，否則以通知說明原因。
      帶 --window（選單「錄這個視窗」）時直接錄該視窗；存檔位置依 --root ＞ 選單的「存到」＞ 上次 meeting record。

  menubar
      在 menu bar 放狀態圖示（待機／錄製中＋計時／暫停中／告警）與選單；
      ⌃⌥⌘R 開始錄製、⌃⌥⌘M 麥克風靜音、⌃⌥⌘P 暫停／繼續、⌃⌥⌘B 加標記。不帶任何子指令啟動時也進這個模式（登入時自動開啟）。

  reminders --input <json> --list <名稱>
      把會議交辦寫進提醒事項中名稱完全相同的清單（不代建）；以 URL 去重，重跑不重複寫入。
      由 meeting reminders 叫起；結果寫 <json>.result.json（code 0／3 清單不存在／4 權限被拒／5 寫入失敗）。

  help
      印出這份說明。
"""

// 無參數啟動（Finder 雙擊、登入項目）＝ menubar；系統可能多塞一個 -psn_… 參數，一併略過（spec §4.22.2）
let argv = CommandLine.arguments.dropFirst().filter { !$0.hasPrefix("-psn_") }
let sub = launchMode(arguments: argv)
let args = Args(Array(argv.dropFirst()))

// SIGUSR1 是 menu bar／record.sh 通知錄製實例「讀控制檔」的訊號（spec §4.16.4）。預設動作是結束程序，
// 所以在分派任何子指令之前先忽略：送錯程序（menubar、windows…）也不會被殺；錄製實例另以 DispatchSource 接收。
signal(SIGUSR1, SIG_IGN)

// 在分派任何 Task 之前，於主執行緒（頂層程式碼）建立 WindowServer（CGS／SkyLight）連線。
// 這條連線若第一次是在 Swift concurrency 的背景執行緒被觸發（例如 SCContentFilter(desktopIndependentWindow:)
// 內部呼叫 SLSGetDisplaysWithRect），SkyLight 會 assert 讓整個 app SIGABRT（t6 實機的 preflight 當機）。
// NSApplication.shared 建立 app 物件並連上 WindowServer；.accessory 與 Info.plist 的 LSUIElement 一致，不出 Dock 圖示。
// CGMainDisplayID() 再保險地在主執行緒碰一次 CGS。menubar 模式之後再取 NSApplication.shared 拿到的是同一個實例。
_ = NSApplication.shared
NSApp.setActivationPolicy(.accessory)
_ = CGMainDisplayID()

switch sub {
case "windows":
    Task { await cmdWindows(args) }
case "diagnose-windows":
    Task { await cmdDiagnoseWindows(args) }
case "probe":
    Task { await cmdProbe(args) }
case "preflight":
    Task { await cmdPreflight(args, start: false) }
case "start":
    Task { await cmdPreflight(args, start: true) }
case "quick-start":
    Task { await cmdQuickStart(args) }
case "menubar":
    runMenuBar(args)
case "reminders":
    cmdReminders(args)
case "-h", "--help", "help":
    print(helpText)
    exit(0)
default:
    die("✗ 未知的子指令：\(sub)\n  說明： MeetingRecorder help", code: 2)
}

RunLoop.main.run()

# ADR：錄製視窗清單怎麼讓使用者認出會議視窗

- 狀態：提議（待閘門 2 核准；方向已由使用者以 D16 選定）
- 日期：2026-10-11（第六修正輪）
- 範圍：`tools/MeetingRecorder/Sources/Core/WindowList.swift`、`Sources/Capture/ChromeTabs.swift`、`Resources/MeetingRecorder.entitlements`、`Resources/Info.plist`、`bin/_record_prompt.py`
- 規則正本：`spec.md §3.8`；設計摘要：`design.md §8.3`

## 背景

- 使用者回報「清單裡根本沒有那個視窗」；診斷發現要錄的 M+ Meet（Chrome 分頁）其實被篩選納入，但網頁標題是會議名稱（真實會議名稱不寫進 repo，下文一律以中性範例「[Stand-up] 範例專案」代稱，原文只在 run 目錄的診斷報告），清單只顯示「Google Chrome — <會議名稱>」，與其他 7 個 Chrome 視窗混在一起認不出來（run 目錄、不進版控的 `_tpm/runs/20261010-sdlc-meeting-record/window-filter-diagnosis.md:31-32`、`:37`）。
- 原型把 Chrome、Safari 整個 app 標 ★（`main.swift:106-112`），8 個 Chrome 視窗全部有 ★，標記沒有資訊量；quick-start 要求「★ 恰好一個」，因此在這種情境下永遠失敗。
- 同時發現「標題非空」篩選把無標題的 LINE 通話視窗濾掉（`window-filter-diagnosis.md:18`），這是獨立的 bug，不論選哪個選項都要修。

## 選項

| 選項 | 怎麼判斷會議視窗 | 授權 | 代價 |
|---|---|---|---|
| A. Apple Events 讀 Chrome 分頁網址 | 以 `NSAppleScript` 唯讀取每個 Chrome 視窗的標題、bounds、作用中分頁網址；網址主機在會議服務表內（M+ Meet、Google Meet、Teams、Zoom、Webex）就標 ★；SCWindow 與 Chrome 視窗以標題（同名時加 bounds）對應 | 「自動化」（MeetingRecorder → Google Chrome），選用；hardened runtime 要 `com.apple.security.automation.apple-events` entitlement 與 `NSAppleEventsUsageDescription` | 多一個 TCC 授權與 entitlement；只支援 Chrome；同名同位置的兩個視窗對不上；第一次授權要有人在場 |
| B. 標題關鍵字 | 標題含「Meet」「Zoom」「Teams」等字就標 ★ | 無 | M+ 的網頁標題是會議名稱、不含任何產品字（`window-filter-diagnosis.md:30`），**正好漏掉這次的情境**；會議名稱含關鍵字的非會議頁會誤標 |
| C. 輔助使用（Accessibility）讀網址列 | 用 AX API 讀 Chrome 網址列文字 | 「輔助使用」，權限遠大於只讀網址 | `req:255` 為了不要「輔助使用」授權而禁用 `addGlobalMonitorForEvents`，同理不該為此要求；AX 樹結構隨 Chrome 改版變動 |
| D. 不標記，只把每列資訊顯示得更完整 | 不判斷；顯示尺寸、全螢幕尺寸、前景與否 | 無 | 8 個同為 1496×938 的 Chrome 視窗仍分不出哪個是會議；quick-start 仍無法自動選 |

## 決定

採 **A**（使用者 D16「讀瀏覽器分頁網址來標記（建議）」），並同時做 D 的「每列顯示更多資訊」（D15 3(b)）與移除「標題非空」篩選（D15 3(a)）。細節：
- 只看**作用中分頁**：單視窗擷取只錄得到正在顯示的分頁。
- 對應方式：標題完全相同優先，同名時才用 bounds（±2 pt）；對不上就不標、不猜。
- 授權框只在終端機互動流程（`record.sh` 有 tty 時帶 `--ask-automation`）跳；quick-start、menu bar 不跳。
- 沒授權或 Chrome 沒開：清單照常、只是沒有標記；preflight 第 13 項 warn、doctor 印「◦」，永不 hard fail。
- 網址只在記憶體比對，不寫進任何檔或輸出。

## 後果

- entitlements 由一項變兩項（`spec.md §6` 第 25、33 條），t1 的靜態檢查改名為 `test_entitlements_audio_and_apple_events`，t3 的 `plistlib` 斷言改為兩項。
- ★ 的意義改變：Chrome／Safari 不再整個 app 是 ★；quick-start 在「只開一個 Chrome 會議分頁」時才可能自動選到它。
- 沒在終端機跑過 `meeting record`（因此沒授權）的使用者，quick-start 看不到 Chrome 的 ★；SKILL.md 必須寫明（`spec.md §4.12.10`）。
- Safari、其他 Chromium 瀏覽器、LINE 通話不標 ★，列為衍生工作（不編號）。
- ad-hoc 簽章時「自動化」授權每次重建都可能要重給（`spec.md §7` 疑慮 14）。

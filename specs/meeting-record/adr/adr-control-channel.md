# ADR：`record.sh` 與錄製器之間的控制與狀態通道

- 狀態：提議（待閘門 2 核准）
- 日期：2026-10-11（修正輪：補 menu bar 與 `./record` 撞名的關係）
- 範圍：`bin/record.sh`、`tools/MeetingRecorder/Sources/`

## 背景

- 觸發層一律 `open -n -a MeetingRecorder.app --args …`，不准直接 exec 二進位（`req:205`），否則 TCC 責任程序會落到終端機。
- `open` 派送後立刻回 0，不接 stdout、不轉傳結束碼（`req:207`；`tools/MeetingRecorder/probe.sh:88-92` 因此改讀 log）。
- `record.sh` 必須自己推導 `4`／`5`（`research-code-contracts.md:113-117`）；`stop` 需要一個辦法通知正在錄的那個 process。

## 選項

| 選項 | 狀態回傳 | 停止 | 代價 |
|---|---|---|---|
| A. 狀態檔＋pid＋SIGTERM | app 原子寫 `~/.meeting-harness/record.status.json`；`record.sh` 輪詢、以 `runId` 過濾殘檔 | `kill -TERM $(cat record.pid)`，app 用 `DispatchSource` 接 signal 後優雅停止 | 要處理殘留 pid（`kill -0` 判活）；輪詢有最多 0.5 秒延遲 |
| B. 第二個實例轉送 | 同 A | `open -n -a … --args stop` 啟一個新實例，再用 `DistributedNotificationCenter` 通知錄製實例 | 停止也要經 LaunchServices，多一個「通知沒送到」的靜默失敗點；仍需狀態檔回報結果 |
| C. 本機 socket／XPC | app 開 Unix domain socket，`record.sh` 用 `nc -U` 收送 | 同一條連線 | shell 端要多一個依賴與逾時處理；app crash 時 socket 檔殘留同樣要清；複雜度最高 |

## 決定

採 **A**。理由：狀態檔是需求本來就指定的通道（`req:207`），pid＋SIGTERM 不經 LaunchServices，也不需要任何授權；殘檔問題用 `runId` 與 `kill -0` 解決，`kill -9` 後的殘留正好是 `record status` 判斷「異常中止」的依據。

## 後果

- 狀態檔欄位（`design.md §3.2`）是 `record.sh` 與 app 之間唯一的契約，兩邊都要有測試釘住欄位名。
- menu bar 的「停止」也走 SIGTERM，與終端機同一條路；menu bar 判斷狀態除了讀狀態檔，也用 `kill -0 record.pid` 分辨「正在錄」與「異常中止」（`design.md §8.2`）。
- 狀態檔的 Swift 型別（`RecordStatus` 等）與 JSON 鍵名以 `spec.md §3.4` 為唯一契約。
- 快捷鍵與 menu bar 直接 `open` app、不經 `meeting.sh`，所以 `./record` 目錄撞名（D11，`design.md §8.1`）不影響這條通道。

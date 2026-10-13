# ADR：錄製中的控制通道（R2：暫停、麥克風靜音、標記）

- 狀態：提議（待 R2 閘門 2 核准）
- 日期：2026-10-12
- 範圍：`tools/MeetingRecorder/Sources/`（錄製實例、menu bar）、`bin/record.sh`（CLI 對等子指令）
- 關係：延伸 `adr-control-channel.md`（狀態檔＋pid＋SIGTERM），不取代它

## 背景

- R2 要在錄製中切換「暫停／繼續」「麥克風靜音／取消」「加標記」，入口有三個：menu bar 選單、全域快捷鍵、`meeting record pause|resume|mute|unmute|mark`（brief:22-27、:37）。
- 錄製實例目前只接 SIGTERM／SIGINT（`Sources/Capture/RecordingSession.swift:228-239`），沒有任何錄製中的控制通道。
- brief 的架構決定（brief:35）：`~/.meeting-harness/record.control.json`（原子 rename）＋SIGUSR1，錄製實例收到後重讀控制檔，切換冪等。
- 調研指出三個風險：SIGUSR1 的預設動作是終止程序，送到沒裝 handler 的程序（舊版 app、preflight 階段）會直接殺掉錄製（`research-code-contracts.md` C1）；控制檔跨場次共用，上一場暫停中當機會讓下一場一開就暫停（C10）；兩個寫者（menu bar、CLI）同時 read-modify-write 會互相蓋掉（同檔 C9 的同類問題）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 控制檔＋SIGUSR1（brief 定案）＋防護 | 寫者取 `record.control.lock` 的 `flock` → 讀控制檔 → 改成「目標狀態」→ 原子寫回 → 對 `record.pid` 的 pid 送 SIGUSR1；錄製實例收到後重讀、與已套用狀態比較 | 多一個控制檔與一個鎖檔；送訊號前要做能力與 pid 檢查 |
| B. 一個動作一個訊號（SIGUSR1＝暫停切換、SIGUSR2＝靜音切換、SIGWINCH 類＝標記），不用檔案 | 寫者直接 `kill -USR1` | 訊號會被合併（dispatch source 對同一訊號只回報一次），連按兩次標記可能只記一次；「切換」語意不冪等，menu bar 與 CLI 看到的狀態不同步時會切反；可用訊號不夠、語意靠約定 |
| C. 第二個實例轉送（`open -n -a … --args pause`＋`DistributedNotificationCenter`） | 與第一輪 ADR 的選項 B 相同 | 經 LaunchServices、多一個靜默失敗點；第一輪已因同樣理由不採 |

## 決定

採 **A**，並加四條防護：

1. **目標狀態而非切換**：控制檔存 `{schemaVersion, runId, paused, micMuted, markerSeq}`（`spec.md` R2 §3.9），寫者寫「要變成什麼」，錄製實例以 `controlActions(applied:requested:)` 算出差異才動作，所以重複寫、訊號合併都冪等；`markerSeq` 是本場累計次數，差值就是要新增的標記數。
2. **runId 範圍**：錄製實例在裝好訊號 handler 之後、寫 `record.pid` 之前，以自己的 `runId` 重寫一份全 false、`markerSeq = 0` 的控制檔（`resetControl`）；只採信 `runId` 相符的內容。寫者以 `record.status.json` 的 `runId` 為準，控制檔 `runId` 不同就從全 false 起算。
3. **只對能接的程序送**：送 SIGUSR1 前同時成立：`record.pid` 存在且 `kill -0` 活著、`record.status.json.pid` 等於它、`phase == recording`、`controlVersion ≥ 1`（R2 新增的選用欄位，舊版沒有）。pid 一律取 `record.pid`，不退回 `status.pid`（`record.pid` 在 handler 裝好之後才寫，`RecordingSession.swift:130` 先、`:156` 後）。另外 `main.swift` 在 dispatch 前把 SIGUSR1 設成 `SIG_IGN`，新版任何模式誤收都不會被殺。條件不成立一律回 3（「沒有可控制的錄製」）並說明原因，不送訊號。
4. **寫者互斥**：寫者在 read-modify-write 期間持有 `<home>/record.control.lock` 的 `flock(LOCK_EX)`；錄製實例只讀不寫（重設除外，也取同一把鎖）。

## 後果

- 對外契約多兩個檔：`record.control.json`、`record.control.lock`（`spec.md` R2 §3.9）；兩邊（Swift `Core/Control.swift`、`bin/record.sh` 內的 Python）都有測試釘住鍵名與語意。
- CLI 的回應以 `record.status.json` 回報為準：寫完送訊號後最多等 5 秒看到狀態反映才回 0；沒反映回 3（錄製器沒有回應）。
- 舊版錄製實例（R2 之前開的錄製）不支援控制，只能停止；這是相容性代價，不是缺陷。
- SIGTERM 的停止路徑完全不變。

# 設計審查：meeting-record（menu bar 常駐實例）— t6 三輪中途修正後複驗（cb417b4）

- 審查對象：`feature/meeting-record` @ `cb417b4`（比對基準 `main`；前一輪複驗在 `aff7c05`，報告 commit `5a49f79`）
- 本輪範圍內的改動：t6 三輪中途修正（D19–D23、缺陷 A–N）。跟畫面有關的只有三類：
  1. 會流進 menu bar 狀態列與通知的**新字串**：`completionOutcome`（`Sources/Core/Records.swift:234-253`，§4.4.9）、`segment_write_failed` 告警（`RecordingSession.swift:487-519`，§4.4.7，屬告警類，會走 M7）。
  2. preflight 的**新提示**：第 5 項兩段式的 warn（D19／D21，§4.2.5）、幕前調度提醒（§4.2.12，發現 I）。
  3. `main.swift` 在頂層新增 `NSApplication.shared`＋`setActivationPolicy(.accessory)`（§4.2.10）。
  另外，`SKILL.md`／`README.md` 補了錄音範圍與幕前調度的說明。
- 沒有改動的部分：`Sources/Trigger/{MenuBar,HotKey,QuickStart}.swift`、`Sources/Core/Trigger.swift`、`Sources/Capture/Notifier.swift`、`Resources/Info.plist`、`Tests/TriggerTests.swift`，從 `aff7c05` 到 `cb417b4` 都沒有改（證據 §1）。所以前一輪逐條核對過的 §3.4.1 全表與 §4.11.2–4.11.10 結論都還成立，本輪不再重複列出。
- 審查方式：**只做靜態審查**（派工單約束 3）。沒有建置到 `~/Applications`，沒有啟動 app，沒有截圖，也沒有觸發任何 TCC 授權框。
- 對照依據：`spec.md §3.4.1`、`§4.2.4–4.2.6`、`§4.2.12`、`§4.4.7`、`§4.4.9`、`§4.11.1`、`§4.11.7`、`§4.11.8`、`design.md §8.2`（已把 HIG menu bar extra 慣例寫成 spec 條文）。
- 設計系統：本專案沒有（`.claude/teams/rules.md` 專案規則：「設計系統 skill：無」），沒有 checklist 可勾，也不做 token 掃描。淺色／深色的規定由 §4.11.5 的 template image 承擔，兩種外觀都要在實機截圖驗證（交使用者）。
- 8 個階段在本輪的對應：
  - 1 準備：已做。
  - 2 截圖、3 互動：not_verifiable，交使用者實機。
  - 4 版面、5 視覺：只做靜態，用字數與截斷量測。
  - 6 無障礙：只做靜態，相關程式沒有改。
  - 7 例外狀態：檢查新增的失敗訊息在狀態列會怎麼呈現。
  - 8 console：not_verifiable。

## 證據

| 檔 | 內容 |
|---|---|
| `specs/meeting-record/evidence/design-review-swift-tests.txt` | `tools/MeetingRecorder/Tests/run.sh` 全量：共 50 支，失敗 0（含 `TriggerTests` 全部、`testCompletionOutcome`、`testStageManagerNotice`、`testSystemAudioCheckTwoStage`） |
| `specs/meeting-record/evidence/design-review-static-rules.txt` | 畫面與文件相關靜態規則 15 支全 OK：menu bar 9 支、`test_windowserver_connection_initialized_on_main_thread`、`test_preflight_system_audio_two_stage`、`test_completion_uses_outcome`、`test_stage_manager_read_only`、`test_stage_manager_documented`、`test_no_client_names_in_repo_text` |
| `specs/meeting-record/evidence/design-review-static-grep.txt` | 共 8 段：§1 畫面檔有沒有改；§2、§8 反作弊（測試檔只有新增，刪掉的兩行是模組 docstring）；§3 新字串的出處；§4 `truncatedStatusTitle(limit: 40)` 套在新字串上的實際顯示；§5 quick-start 路徑 preflight warn 出現在哪裡；§6 activation policy；§7 前一輪 N-1、N-2 的現況 |

測試一律帶 `TMPDIR=$(mktemp -d)`、`LC_ALL=en_US.UTF-8`、`MH_CLIENT_NAMES_FILE=<run 目錄的清單>` 執行，清單內容沒有讀出來。

## 前一輪發現的處置

| 前一輪 | 本輪結果 | 證據 |
|---|---|---|
| N-1　快捷鍵註冊失敗時，選單上仍顯示 ⌃⌥⌘R | **仍在，沿用**。`MenuBar.swift` 沒有改；spec §4.11.6 也沒有修訂，實作符合 spec。下面改列為本輪 N-3，讓使用者決定 | grep §7（`MenuBar.swift:12,38,61-63`） |
| N-2　SKILL.md「告警狀態會一直留著」跟 M5／M6a 不一致 | **已解決**。改成「錄製中出現的告警，收尾成功後就回到待機；開錄前檢查沒通過、錄製失敗或異常中止的告警狀態會一直留著」，跟 §3.4.1 M2–M6、M5 一致 | `SKILL.md:214`；grep §7 |

## 逐條對照（本輪改動，靜態）

| 條文 | 結果 | 證據 |
|---|---|---|
| §3.4.1 statusLine 不得含 `WarningKind`／`RecordPhase` 的 raw value（新增的 `segment_write_failed`） | 符合。M7 用的是 warning 的中文 `message`（「`seg-NNNN.mov` 寫檔失敗：…；檔案保留」），不含 `segment_write_failed` | `RecordingSession.swift:487-514`；`Trigger.swift:78-79`；`testStatusLineHumanReadable` 綠 |
| §4.11.2 只有告警類轉告警態：`segmentWriteFailed.isAlert == true` | 符合。寫檔失敗屬於使用者需要知道的錯誤，歸告警類合理；M6a 計數會把它算進去 | `Records.swift:19` |
| §4.4.9／§4.4.7 最終訊息：停止原因在前，收尾失敗附在後 | 符合（M3／M4 首行就是 `message`，因為 `completionOutcome` 的訊息沒有換行） | `Records.swift:240-253`；`testCompletionOutcome` 綠；`test_completion_uses_outcome` OK |
| §4.11.7 完成後送一則含場次路徑的通知 | 符合。成功時 body＝場次路徑；失敗時 body＝完整訊息＋場次路徑，標題「會議錄製結束（有錯誤）」 | `RecordingSession.swift:768-769` |
| §4.11.8 狀態列 40 字截斷，完整文字放 toolTip | 機制符合（程式沒改）。新字串截斷後的可讀性見 N-1 | grep §4 |
| §4.2.12 幕前調度：只讀、不改系統設定；SKILL.md／README 各一句 | 符合 | `test_stage_manager_read_only`、`test_stage_manager_documented` OK |
| §4.2.5 D21：`.fail` 訊息只含授權補救，不再叫使用者取消靜音 | 符合；SKILL.md 第 5 項的補救欄也同步改寫，並註明「輸出靜音不影響錄音」 | `test_preflight_system_audio_two_stage` OK；`SKILL.md` 第 5 項列 |
| §4.2.10 頂層 `setActivationPolicy(.accessory)` | 符合，而且對畫面沒有副作用：`LSUIElement=true`，`MenuBar.swift:153` 本來就設 `.accessory`，兩者一致，不會讓 Dock 冒出圖示 | grep §6 |

## 發現

### Blocker

無。

### Should-fix

無。

### Nit

**N-1　收尾失敗的狀態列被截在 40 字，補救指令看不到；有一種情況只看得到「已自動停止並收尾」**
- 位置：`tools/MeetingRecorder/Sources/Core/Records.swift:241-245`（訊息組法）；`Sources/Core/Trigger.swift:60-63,95-99`（M3 與截斷）；`spec.md §4.4.9`、`§4.11.8`
- 現況（grep §4 的實際量測）：
  - 只有收尾失敗：顯示「錄製失敗：收尾失敗（_record_finalize.py 回 5），段落保留…」。補救的 `meeting record finish` 落在 40 字以後。
  - 磁碟不足自動停止，接著收尾失敗：這是 t6 第三輪 §4.5.5 實際發生過的組合。顯示「錄製失敗：磁碟可用空間低於 2 GB（剩 1.70 GB），已自動停止並收尾；…」。看得到的部分寫「已自動停止並收尾」，收尾其實失敗了，「收尾失敗」幾個字被截掉。
  - 狀態列裡還有內部腳本名 `_record_finalize.py`。
- 依據：
  - §4.11.8 要求 statusLine 是完整中文句子、不出現內部代碼。§4.4.9 則**明訂**訊息要含「收尾失敗（_record_finalize.py 回 N）」，而且停止原因要放在前面。實作照 §4.4.9 做，兩條 spec 之間有張力，所以這則列 Nit，不判實作錯。
  - 有緩解：完整文字在狀態列的 toolTip 看得到（§4.11.8），失敗通知的 body 也有完整訊息加場次路徑（`RecordingSession.swift:768-769`），使用者拿得到補救資訊。
- 建議（spec 層，交使用者決定）：讓 menu bar 的 M3 在 `phase == failed` 且訊息含「收尾失敗」時，只顯示「錄製失敗：收尾沒完成，段落保留（滑過看詳情）」這類短句，完整訊息留在 toolTip。也可以維持現況，在實機時確認可以接受。
- 信心：0.7

**N-2　用 quick-start（快捷鍵或選單）開錄時，preflight 的提示看不到（新的幕前調度、第 5 項 warn 都是）**
- 位置：`tools/MeetingRecorder/Sources/Capture/Commands.swift:152-169`；`Sources/Trigger/QuickStart.swift:44-47`；`Sources/Core/Trigger.swift:84-87`（M9 不讀 `message`）
- 現況：只有 warn 時，提示只寫進 `record.status.json` 的 `message`、`preflight` 與 `record.log`（幕前調度另外多寫一行 log）。終端機 `meeting record` 會印出來，可是 quick-start 沒有終端機，開錄後 menu bar 走 M9，只顯示「錄製中 mm:ss・場次名」。使用者因此不會知道「幕前調度已開啟：…錄影解析度會跟著變小」或「會議 app 目前沒有聲音」。這個缺口以前就有（簽章、電量這些 warn 也一樣），但 §4.2.12 新增的提醒正是為了防止 t6 發現 I（錄成縮圖解析度），而 quick-start 是 menu bar 的主要開錄路徑，影響比以前大。
- 依據：§4.2.6「warn 項應照常開錄且有提示」；§4.2.12 的目的（提醒使用者把會議視窗留在目前舞台）。§4.2.4 只規定要列在 `record` 的輸出與 `record.status.json.preflight`，沒有規定 quick-start 怎麼呈現，所以實作沒有違反 spec。列 Nit。
- 建議（spec 層，交使用者決定）：
  - A：quick-start 在 preflight 有 warn 時，開錄後多送一則通知，標題「MeetingRecorder 已開錄（有提示）」，body 是 `warnText` 的前幾行。
  - B：維持現況，在 SKILL.md 的 quick-start 段註明「提示只寫在 `record.log`」。
- 信心：0.65

**N-3（沿用前一輪 N-1）快捷鍵註冊失敗時，選單上仍顯示 ⌃⌥⌘R**
- 位置：`tools/MeetingRecorder/Sources/Trigger/MenuBar.swift:12,38,61-63`；`spec.md §4.11.6`
- 現況與依據同前一輪：實作符合 spec，HIG 慣例是選單上顯示的快速鍵要真的能用。本輪程式沒有改，spec 也沒有修訂。
- 建議：spec §4.11.6 加一句「`hotKey == nil` 時清掉 `startItem.keyEquivalent`」，或者維持現況，在實機時確認可以接受。
- 信心：0.6

### 範圍外（交使用者實機驗收，not_verifiable）

前一輪列的 menu bar 實機點都還沒做（`progress.md:113` 未勾）。t6 已經實機驗過的只有 §4.11.1 code 3 分支與 §4.11.10 單一實例（run 目錄 `t6-results.md` 的 §4.11.1、§4.11.10 兩條，都是 PASS）。下面這些需要使用者在場，或者會碰到畫面與 TCC：

- **截圖**：只截 menu bar 區域，放 run 目錄、不進 repo（§4.14.1）。
  - 三態圖示在淺色與深色 menu bar 各一張（§4.11.5 template image 的對比）。
  - 三態展開的選單各一張，其中要有 M6a「收尾中…（告警 N 則）」，以及一則超過 40 字被截斷的訊息。本輪建議直接用 N-1 的「收尾失敗」或「段落寫檔失敗」案例。
- §4.11.8：`labelColor` 在 disabled 選單項上的實際顏色；中文 40 字的選單寬度；toolTip 會不會出現完整文字；VoiceOver 會不會讀出「MeetingRecorder：」前綴。
- §4.11.9：錄製中打開選單停 5 秒，看秒數有沒有在走。
- §4.11.7：有告警、沒告警各按一次停止，1 秒內出現「收尾中…」；收尾成功與收尾失敗各看一次通知內容。
- §4.11.6、§4.11.3：選單上看得到 ⌃⌥⌘R；選單展開時按一次只開一場；按鍵被佔用時 log 有寫。
- §4.2.12 實機：由使用者自己開啟幕前調度後跑一次 `meeting record preflight`，看第 12 項 warn，之後由使用者自己關閉（主 session 與 agent 不得替使用者切換）。
- console 錯誤（要實際執行才看得到）；告警態 `.systemRed` 在兩種外觀下的對比度。

## 結論

畫面相關的程式（menu bar、快捷鍵、quick-start、通知、Info.plist）從 `aff7c05` 到 `cb417b4` 完全沒有改，前一輪逐條核對的結論都還成立。本輪新增會流到畫面上的東西有三樣：`completionOutcome` 的最終訊息、`segment_write_failed` 告警、preflight 的幕前調度與第 5 項 warn。它們都符合 spec：statusLine 不含 raw value，告警類分類合理，失敗通知帶完整訊息，幕前調度只讀不寫。Swift 50 支、靜態規則 15 支全綠；反作弊比對只看到新增的測試，刪掉的兩行是 docstring。

前一輪的 N-2 已經修好。本輪沒有 Blocker，也沒有 Should-fix，有三則 Nit：
- N-1：收尾失敗的訊息被截斷，補救指令看不到；有一種情況只看得到「已自動停止並收尾」。這是 §4.4.9 與 §4.11.8 之間的張力。
- N-2：quick-start 路徑看不到 preflight 的提示，包括新的幕前調度提醒。
- N-3：沿用前一輪 N-1，快捷鍵註冊失敗時選單上仍顯示 ⌃⌥⌘R。

三則都要在 spec 層由使用者決定，不影響功能。所有截圖與互動項目都要使用者在場，列為 not_verifiable。

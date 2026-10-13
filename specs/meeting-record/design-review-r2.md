# 設計審查：meeting-record R2（menu bar 紅點＋計時、收音指示、暫停／靜音／標記、錄這個視窗、存到、偏好設定、完成通知）

- 審查對象：`feature/meeting-record` @ `59d4047`；R2 範圍＝`meeting-record-r1-baseline`（`f084765`）..HEAD，共 22 個 commit。
- 檔名說明：派工單本文寫 `design-review.md`，但授權補充明訂第一輪的 `design-review.md` 不得覆寫、本輪寫 `design-review-r2.md`。本報告照授權補充寫在這裡，第一輪報告沒有動。
- 本輪跟畫面有關的改動：
  - `Sources/Trigger/MenuBar.swift`（改，+457/−）：status item 改成 `variableLength`，加計時與 `mic.slash`；選單 18 項；四組快捷鍵；「錄這個視窗」與「存到」兩個子選單；完成通知的「在 Finder 顯示」。
  - `Sources/Trigger/Preferences.swift`（新）：偏好設定視窗。
  - `Sources/Trigger/Completion.swift`（新）：`NSOpenPanel`、在 Finder 顯示、停止後自動前處理的通知。
  - `Sources/Trigger/HotKey.swift`（改）：多組 id。
  - `Sources/Core/Trigger.swift`（改）：M6b、M9 計時、R2 欄位。
  - `Sources/Core/Control.swift`（新）：`levelIndicatorLine`、`clockText`、`loginItemDisplay` 等純函式。
  - `SKILL.md`／`README.md` 的 menu bar 段。
- 審查方式：只做靜態審查（派工約束 3）。沒有建置 app，沒有啟動或覆蓋 `~/Applications/MeetingRecorder.app`，沒有送訊號，沒有寫 `~/.meeting-harness/`，也沒有觸發任何 TCC 授權框。截圖與互動交使用者在 t7（spec §4.25.2）實機做。
- 對照依據：spec §3.13、§3.14、§3.14.1、§4.20.1–§4.20.8、§4.21.1–§4.21.5、§4.22.1–§4.22.6、§4.23.1–§4.23.4、§4.24.3、§6 第 80、81 條；HIG menu bar extra、settings window、keyboard shortcuts（spec §4.20.4、§4.20.6、§4.22.4 把這幾條寫成了設計審查依據）；WCAG 1.4.1（不只靠顏色）。
- 設計系統：本專案沒有（`rules.md` 專案規則：「設計系統 skill：無」），所以沒有 checklist 可勾，也不跑 `check-tokens.sh`。淺色與深色都要測：§4.20.4 明訂兩種外觀都要看得清楚。
- 8 個階段在本輪的對應：
  - 1 準備：已做。
  - 2 截圖、3 互動：not_verifiable，交 t7。
  - 4 版面：用字數與截斷量測（證據 §2）。
  - 5 視覺：程式碼層的 template、tint、字型檢查。
  - 6 無障礙：accessibilityLabel 與「不只靠顏色」。
  - 7 例外狀態：舊版錄製器、取不到視窗清單、登入項目要核准、快捷鍵註冊失敗。
  - 8 console：not_verifiable。

## 證據

| 檔 | 內容 |
|---|---|
| `specs/meeting-record/evidence/design-review-r2-swift-tests.txt` | `tools/MeetingRecorder/Tests/run.sh` 全量：共 78 支，失敗 0。含 `MenuBarR2Tests` 全部、`ControlTests` 全部；`TriggerTests` 全綠，而且沒有改（證據 grep §1） |
| `specs/meeting-record/evidence/design-review-r2-static-rules.txt` | `test_r2_static`、`test_r2_docs`、`test_static_rules` 共 54 支，全 OK。含 `test_trigger_status_item_variable_length`、`test_trigger_menu_items_r2`、`test_trigger_preferences_window`、`test_trigger_login_item_only_in_preferences`、`test_menubar_uses_template_image`、`test_menubar_sets_accessibility_label`、`test_no_client_names_in_repo_text`（結果是 ok，不是 skipped） |
| `specs/meeting-record/evidence/design-review-r2-static-grep.txt` | 共 10 段：§1 第一輪畫面測試與 Info.plist 沒有改；§2 R2 狀態列與收音列的實際輸出量測（只編 `Sources/Core/*.swift`）；§3 選單順序與快捷鍵；§4 status item 的繪製；§5 沒有 main menu；§6 偏好設定的用語；§7 加標記的回饋；§8 路徑顯示；§9 取不到視窗清單；§10 第一輪 N-1–N-3 的現況 |

- 測試一律帶 `TMPDIR=$(mktemp -d)`、`LC_ALL=en_US.UTF-8`、`MH_CLIENT_NAMES_FILE=<run 目錄的清單>` 執行，清單內容沒有讀出來。
- 三個證據檔都用 `grep -qF -f` 比對過清單，結果是「沒有」。

## 逐條對照（靜態）

| 條文 | 結果 | 證據 |
|---|---|---|
| §4.20.4 `variableLength`，不再用 `squareLength` | 符合 | `MenuBar.swift:16`；`test_trigger_status_item_variable_length` OK |
| §4.20.4 圖示一律 template；錄製中與告警態 `.systemRed`，待機與暫停中 nil | 符合 | `MenuBar.swift:199-202` |
| §4.20.4 計時用 `monospacedDigitSystemFont`，空字串時只放圖示 | 符合。`mm:ss` 內每秒換字寬度不變；到 1 小時變成 `h:mm:ss` 時會加寬一次，這是格式本身決定的，可以接受 | `MenuBar.swift:203-218` |
| §4.20.4 靜音時計時前加 `mic.slash`（template） | 實作有加，但是以 `NSTextAttachment` 放進 `attributedTitle`。深色 menu bar 下能不能看清楚是風險，見 SF-1 | `MenuBar.swift:210-216` |
| §4.20.4 toolTip、accessibilityLabel＝`accessibilityText` | 符合。暫停中也有「MeetingRecorder：」前綴（證據 §2 M6b） | `MenuBar.swift:220-221` |
| §4.20.3／§3.14.1 收音指示列 | 符合，而且不只靠顏色：用「● 有聲／○ 無聲／⊘ 已靜音」的形狀加文字（WCAG 1.4.1）；21–22 字，不需要截斷 | 證據 §2 |
| §4.20.6 選單 18 項的順序、快捷鍵、灰掉不隱藏 | 符合。順序與 spec 逐項相同；`autoenablesItems = false`；收音列只在 `levelLine` 非空時顯示 | `MenuBar.swift:66-103`；`test_trigger_menu_items_r2` OK |
| §4.20.6「暫停錄製」在暫停中改成「繼續錄製」；「麥克風靜音」在靜音中打勾 | 符合，而且符合 HIG：可切換的動作改標題，狀態屬性用勾選 | `MenuBar.swift:186-189` |
| §4.20.5 任一組快捷鍵註冊失敗：清掉對應的 `keyEquivalent`，寫 log | 符合。第一輪 N-3 的處理擴大到四組 | `MenuBar.swift:113-131` |
| §4.20.7 寫目標狀態加去抖；§4.20.8 先判斷 `controlAvailability` | 符合。不能控制時用通知說明原因（含「舊版錄製器」），使用者有回饋 | `MenuBar.swift:367-399` |
| §3.14.1 M6b 排在 M7 前；M9 加「麥克風靜音中」 | 符合。M9 把「（麥克風靜音中）」放在場次名**前面**，不會被截掉；M6b 的「（告警 N 則）」放在**後面**，見 N-2 | 證據 §2 |
| §4.21.4「錄這個視窗」：讀取中、取不到、60 字截斷加 toolTip、★ 在前 | 符合 | `MenuBar.swift:276-317` |
| §4.21.5「存到」：目前位置打勾；找不到的灰掉並標「（找不到）」；「選擇資料夾…」用 `NSOpenPanel` | 符合。面板有 `prompt` 與 `message`，開之前先 `activate`，accessory app 的面板不會被別的視窗蓋住 | `MenuBar.swift:329-363`；`Completion.swift:56-67` |
| §4.22.4 偏好設定：不可縮放、標題、四段順序、立即寫入、沒有「確定」 | 符合（`styleMask [.titled, .closable]`；`NSGridView` 右對齊標籤，是 macOS 設定視窗的慣例版式）。HIG 的鍵盤慣例與用語見 SF-2、N-3、N-4 | `Preferences.swift:21-118` |
| §4.22.3／§4.22.4 登入項目要核准時的說明與「打開系統設定的登入項目」 | 符合。註冊失敗時說明寫在勾選框下方，也寫 log | `Preferences.swift:141-176` |
| §4.22.5 `SMAppService` 只在勾選框的動作裡 | 符合 | `test_trigger_login_item_only_in_preferences` OK |
| §4.23.2 自動前處理的完成／失敗通知 | 符合（成功：「前處理完成」＋場次名；失敗：結束碼加 autoprep.log） | `Completion.swift:172-180` |
| §4.23.3 完成通知同一個識別碼、category、「在 Finder 顯示」；`willPresent` 回 banner | 符合 | `MenuBar.swift:453-512` |
| §4.23.4「顯示上一場成品」 | 符合 spec；SKILL.md 的說法跟 spec 不一致，見 N-5 | `MenuBar.swift:428-437` |
| §4.24.3 SKILL.md／README 的 R2 說明 | 符合 | `test_r2_docs` 三支 OK |

## 第一輪發現的處置

第一輪 N-1、N-2、N-3 都已經在 R1 基準點之前依 spec §6 第 73–75 條修好（證據 §10）。R2 把 N-3 的處理擴大到四組快捷鍵（§4.20.5）。本輪不再列。

## 發現

### Blocker

無。

### Should-fix

**SF-1　靜音圖示 `mic.slash` 放在 `NSTextAttachment` 裡，深色 menu bar 下可能看不見（t7 要先看這一項）**
- 位置：`tools/MeetingRecorder/Sources/Trigger/MenuBar.swift:210-216`
- 現況：`mic.slash` 設了 `isTemplate = true`，以 `NSTextAttachment` 塞進 status item 按鈕的 `attributedTitle`。AppKit 的文字系統畫 attachment 時，template image 不一定會跟著 menu bar 的外觀或 `contentTintColor` 著色；如果沒著色，畫出來就是黑色遮罩，在深色 menu bar 上幾乎看不見。另外 attachment 沒設 `bounds`，SF Symbol 的基線與計時數字可能對不齊。
- 依據：§4.20.4「淺色與深色 menu bar 下，……麥克風靜音中……都看得清楚」；HIG menu bar extra（template image）。
- 為什麼不是 Blocker：靜態看不出實際的著色結果。另外麥克風靜音中還有其他提示：選單狀態列有「（麥克風靜音中）」、收音列有「⊘ 已靜音」、accessibilityLabel 也有，所以就算圖示看不見，資訊還在。
- 建議（三選一，實機確認之後再決定）：
  - A：t7 用深色 menu bar 截一張靜音中的圖。看得清楚就維持現況。
  - B：把 `record.circle.fill` 與 `mic.slash` 合成一張 template image 當 `button.image`，計時照用 `attributedTitle`。這樣著色由 status bar 統一處理。
  - C：靜音時把 `button.image` 換成 `mic.slash`（錄製狀態由計時與紅色表示）。這個做法要修 spec §4.20.4。
- 信心：0.55

**SF-2　偏好設定視窗不能用 ⌘W 或 Esc 關閉**
- 位置：`tools/MeetingRecorder/Sources/Trigger/Preferences.swift:21-37`；`Sources/` 全部都沒有設 `NSApp.mainMenu`（證據 §5）
- 現況：app 是 accessory，沒有 main menu。⌘W 在 AppKit 是經由 main menu 的「關閉」項送 `performClose:`，現在沒有這一項，所以 ⌘W 沒有作用；視窗也沒有處理 `cancelOperation`，Esc 同樣沒有作用。偏好設定視窗只能用滑鼠點標題列的關閉鈕。
- 依據：§4.22.4「設計審查依 HIG settings window 慣例」；HIG keyboard shortcuts 的標準組合 ⌘W＝關閉目前視窗。
- 建議：在 `PreferencesWindowController` 攔 ⌘W 與 Esc（例如覆寫 window 的 `performKeyEquivalent` 或 `cancelOperation` 來呼叫 `performClose`），或在 menubar 模式建一個只有「關閉視窗 ⌘W」的最小 main menu。這只動 `Trigger/`，不影響 spec 的其他條文。
- 信心：0.7

### Nit

**N-1　「加標記」成功時 menu bar 端沒有回饋**
- 位置：`MenuBar.swift:376-399`；`Core/Trigger.swift`（沒有讀 `status.markers`，證據 §7）
- 現況：會議中按 ⌃⌥⌘B，成功時畫面上什麼都不會變。暫停與靜音都有可見變化（圖示換成 `pause.circle.fill`、多一個 `mic.slash`），失敗也有通知；只有加標記成功時看不出有沒有記到。終端機的 `meeting record mark` 會印「已加標記 N」。
- 依據：§3.10 的 `markers` 欄位已經在狀態檔裡；HIG 的回饋原則。spec §3.14.1 沒有規定要顯示，所以實作沒有違反 spec。
- 建議（spec 層，交使用者決定）：
  - A：M9／M6b 的 statusLine 或收音列加「・標記 N」。
  - B：維持現況，只在 t7 確認使用者可以接受。
- 信心：0.65

**N-2　暫停中又有告警時，場次名長的話「（告警 N 則）」會被截掉**
- 位置：`Core/Trigger.swift:119-123`
- 現況（證據 §2 實測）：「已暫停 1:01:55・[Stand-up] 範例專案 第三季產品規劃與跨部門協調會議（告警 2 則）」共 51 字，選單只顯示到「…跨部門…」。暫停態的圖示不是紅色，所以告警只靠這一段文字提示，被截掉後選單上就看不出有告警，只剩 toolTip 看得到。M9 把「（麥克風靜音中）」放在場次名前面，沒有這個問題。
- 依據：§3.14.1 M6b「有告警類時再加（告警 N 則）」；§4.11.8 的 40 字截斷。
- 建議：把告警數移到場次名前面，例如「已暫停 01:10（告警 2 則）・場次名」。`MenuBarR2Tests.swift:50,68-69` 只斷言「含」，順序改了測試不用動；spec 文字也不用改。
- 信心：0.7

**N-3　偏好設定的區段標籤寫「開機：」，勾選框寫「登入時自動開啟」**
- 位置：`Preferences.swift:100`
- 現況：登入項目是登入使用者帳號時啟動，不是開機。同一列的標籤和勾選框用了兩個不同的詞。
- 依據：§4.22.4「登入時自動開啟」；HIG writing（同一個概念用同一個詞）。
- 建議：標籤改成「登入：」或「啟動：」。
- 信心：0.75

**N-4　選單項寫「偏好設定…」，視窗標題寫「MeetingRecorder 設定」**
- 位置：`MenuBar.swift:32`；`Preferences.swift:23`；spec §4.20.6、§4.22.4
- 現況：實作照 spec。不過 macOS 13 起系統與 HIG 都把 Preferences 改稱 Settings（繁中「設定⋯」），而且 spec 自己的選單項與視窗標題就用了兩種說法。
- 依據：HIG settings window；§4.20.6 與 §4.22.4 之間的用語不一致。
- 建議（spec 層）：選單項改成「設定…」（⌘, 不變），並同步改 SKILL.md 與 `test_trigger_menu_items_r2` 的字串。也可以維持現況。
- 信心：0.6

**N-5　SKILL.md 寫「顯示上一場成品」選的是「上一場成功收尾的成品」，實作與 spec 不看結束碼**
- 位置：`.claude/skills/meeting-record/SKILL.md:280`；`MenuBar.swift:428-432`；spec §4.23.4
- 現況：spec 與實作的條件是「狀態檔 `phase == done` 而且 `session` 非空」，沒有排除 `code != 0`（收尾失敗）。上一場收尾失敗時，這一項會選到那一場：沒有 `.mov`，所以會選場次目錄，跟文件說的「成功收尾」不一樣。
- 依據：§4.24.3（文件不得寫 spec 沒有的行為）；§4.23.4。
- 建議：spec 與實作加 `code == 0`，跟 `lastSession` 的寫入條件（§3.13「成功收尾」）一致；或者把文件改成「上一場收尾的場次」。
- 信心：0.7

**N-6　「錄這個視窗」取不到清單時，一律等滿 10 秒，而且不說原因**
- 位置：`MenuBar.swift:284-297`（證據 §9）
- 現況：子程序很快就失敗時（例如螢幕錄製權限沒給），選單也要等滿 10 秒才顯示「取不到視窗清單」，沒有任何補救提示。這符合 spec §4.21.4 的字面。
- 依據：§4.21.4；HIG 的回饋原則。
- 建議（spec 層）：失敗時加一句「（看 record.log）」，或者偵測子程序已經結束就提早顯示。也可以維持現況。
- 信心：0.5

### 範圍外（交使用者 t7 實機，not_verifiable）

只截 menu bar 區域與偏好設定視窗。截圖存 run 目錄，不進 repo（§4.14.1、§4.25.2）。需要的畫面：

- **status item，淺色與深色各一組**：
  - 待機
  - 錄製中（紅點＋計時）
  - 暫停中（`pause.circle.fill`，不是紅色）
  - 麥克風靜音中（`mic.slash`，**SF-1 優先看這一張**）
  - 告警
  - 計時跨過 1 小時的寬度變化
- **選單展開，淺色與深色各一張**：收音列、灰掉的項目、「繼續錄製」標題、麥克風靜音的勾。
- **兩個子選單**：
  - 「錄這個視窗」：讀取中、清單、60 字截斷。
  - 「存到」：長路徑時的選單寬度，以及「（找不到）」的列。
- **偏好設定視窗**：
  - 長路徑時視窗會不會被撐寬（`rootLabel` 設了 `byTruncatingMiddle`，但寬度沒有上限約束）
  - 快捷鍵註冊失敗那一列的紅字
  - 登入項目要核准時的說明與按鈕
  - ⌘W／Esc 能不能關（SF-2）
- **互動**：
  - 四組快捷鍵各按一次，只觸發自己的動作。
  - 選單展開時按一次 ⌃⌥⌘B，只加一個標記。
  - 舊版錄製器在跑時按 ⌃⌥⌘P，會跳通知說明。
  - 完成通知的「在 Finder 顯示」。
  - 前處理完成與失敗的通知。
- **VoiceOver**：status item 讀出「MeetingRecorder：已暫停 …」；收音列的「●／○／⊘」怎麼念。
- **console 錯誤**：要實際執行才看得到。

## 結論

R2 的畫面改動逐條對 spec §4.20–§4.23 都符合，靜態看得到的部分都是按 HIG 做的：
- 選單 18 項的順序、快捷鍵與灰掉規則都跟 spec 一致。
- 狀態列不含 raw value；收音指示用「● 有聲／○ 無聲／⊘ 已靜音」，不只靠顏色。
- 偏好設定照 settings window 慣例：不可縮放、立即生效、標籤右對齊。
- 不能控制時有通知說明原因。

Swift 78 支與靜態規則 54 支全綠，第一輪的 `TriggerTests.swift` 沒有改。

本輪沒有 Blocker。
- Should-fix 2 則：
  - SF-1：`mic.slash` 用 text attachment，深色 menu bar 下可能看不見。這要等 t7 截圖確認，所以信心 0.55。
  - SF-2：偏好設定視窗不能用 ⌘W 或 Esc 關閉。
- Nit 6 則：
  - N-1：加標記成功時沒有回饋。
  - N-2：暫停中告警數被截掉。
  - N-3：「開機」與「登入」用語不一致。
  - N-4：「偏好設定」與「設定」的命名。
  - N-5：SKILL.md 說「成功收尾」，但實作不看結束碼。
  - N-6：取不到視窗清單時要等滿 10 秒。

N-1、N-4、N-5、N-6 要在 spec 層由使用者決定。截圖與互動全部交 t7。

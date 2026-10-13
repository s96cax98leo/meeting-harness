---
name: meeting-record
description: 會議開始前用：把會議視窗（Teams、Zoom、Chrome 裡的 M+ Meet／Google Meet 等）連同系統聲音與麥克風錄下來，落到會議資料夾的 錄音/ 與 影片/，錄完直接接 meeting-summary；錄製中可暫停、只靜音麥克風、加標記。全程本機。也涵蓋捨棄這次錄製、錄製小窗（HUD），以及 meeting search／meeting sync／meeting reminders 三個頂層指令。當使用者要「錄會議／開始錄製／停止錄製／暫停錄製／麥克風靜音／加標記／捨棄錄製／錄影沒收尾要救回／搜會議紀錄／交辦寫進提醒事項」時使用。
---

# meeting-record（錄下會議視窗與雙路音訊）

會議**開始前**用。錄製器 `MeetingRecorder.app` 只錄你選的那一個會議視窗（切到別的 Space 也錄得到），
同時錄系統聲音（遠端的人）與麥克風（你自己），每 60 秒落一段到磁碟；停止後自動收尾成一支影片與一個 wav，
放進會議資料夾，之後照 **meeting-summary** 做前處理與會議紀錄。
錄製中可以整段暫停（暫停的時段直接剪掉）、只靜音麥克風（系統聲音照錄）、加標記，見〈3. 錄製中：暫停、麥克風靜音、標記〉。

> **錄到哪些聲音**：系統聲音只錄會議視窗所屬的那個 app。錄 Chrome 裡的會議時，Chrome 所有分頁的聲音都會錄進去，
> 別的 app 的通知音、音樂不會；麥克風照常錄。所以**錄會議時，同一個瀏覽器不要再播其他有聲音的分頁**。

> **幕前調度（Stage Manager）**：開著幕前調度時，會議視窗不在目前舞台會被縮成側邊縮圖，錄到的畫面也會跟著變小；
> 錄會議時讓會議視窗留在目前舞台上，或先關閉幕前調度。開錄前檢查（preflight）偵測到幕前調度開著時，第 12 項會提醒（warn、照常開錄）；錄製器只讀這個設定、不會替你切換。

工具在 **`/Users/yuktang/Documents/Agent/meeting-harness`**（以下用 `$MH`），任何工作目錄都能呼叫：

```bash
MH=/Users/yuktang/Documents/Agent/meeting-harness
meeting() { bash "$MH/bin/meeting.sh" "$@"; }
```

> `meeting record`（錄製）和 `meeting render`（由 `meeting.record.json` 重出 `summary.md` 等產物）是兩件不相干的事：
> `record` 產出的是錄音與影片，`meeting.record.json` 是寫會議紀錄那一步才有的檔，和錄製無關。

## 指令一覽

<!-- record-cli:begin -->
| 寫法 | 旗標 | 結束碼 |
|---|---|---|
| `meeting record [<根>]` | `--window <id>` | 0 2 3 4 5 |
| `meeting record windows` | `--json` | 0 2 4 |
| `meeting record preflight` | `--window <id>` | 0 2 3 4 |
| `meeting record stop` | — | 0 3 5 |
| `meeting record status` | — | 0 5 |
| `meeting record finish <場次>` | — | 0 2 3 5 |
| `meeting record pause` | — | 0 3 |
| `meeting record resume` | — | 0 3 |
| `meeting record mute` | — | 0 3 |
| `meeting record unmute` | — | 0 3 |
| `meeting record mark` | — | 0 3 |
| `meeting record help` | — | 0 |
<!-- record-cli:end -->

上表之外還有兩個 `meeting.sh` 層旗標，所有寫法都能加、位置不限（`record` 之後任何位置）：

- `--recorder`：明確要錄製，略過 `./record` 撞名檢查（見〈目前目錄有 record 資料夾〉）。
- `--yes`：宣告沒有人可問，只影響 `./record` 撞名的判斷。

`meeting record help`（或 `-h`、`--help`）印出完整說明，不啟動錄製器。`help` 是保留字：根目錄剛好叫 `help` 時寫 `meeting record ./help`。
`pause`、`resume`、`mute`、`unmute`、`mark` 同樣是保留字：根目錄剛好叫這幾個名字時，加上 `./`，例如 `meeting record ./pause`。

結束碼的意思：

| 碼 | 意思 |
|---|---|
| 0 | 成功（`status` 包含「沒有錄製在跑」；`finish` 包含「已完成」；`pause`、`resume`、`mute`、`unmute`、`mark` 是已套用且狀態檔 5 秒內反映，本來就是目標狀態時直接回 0） |
| 2 | 參數或前提不符：缺參數、根目錄不存在、app 未建置、場次撞名、已有錄製在跑、非互動又沒有 `--window`；任何寫法遇到未知的選項、或 `./record` 撞名而沒有人可問，也回 2（`stop` 與五個控制寫法多給位置參數也回 2） |
| 3 | 找不到目標：視窗不存在、沒有錄製在跑（`stop`）、該場次沒有段落（`finish`）；五個控制寫法沒有可控制的錄製（沒有錄製在跑、還在開錄前檢查、正在收尾、舊版錄製器開的錄製），或送出後 5 秒內狀態沒有反映 |
| 4 | 開錄前檢查的 hard 項失敗（權限、RMS、磁碟），或開錄後 20 秒內沒有任何狀態（多半是權限）；`windows` 取不到視窗清單（權限） |
| 5 | 錄製或收尾出錯，已落盤段落保留——用 `meeting record finish <場次>` 收尾；`status` 回 5 表示上次錄製異常中止 |

R3 起各寫法在既有結束碼內多了這些情況（數字集合不變）：

- `meeting record [<根>]` 回 2：已有錄製在跑（開錄互斥鎖被持有），不啟動錄製器、不碰狀態檔，stderr 含「已有錄製在跑」。
- `meeting record preflight` 回 2：錄製中，不跑 13 項檢查、不碰狀態檔，stderr 含「錄製中」。
- `meeting record stop` 回 3：pid 確認的四項任一不成立，不送任何訊號（見〈4. 停止〉）。
- `meeting record finish <場次>` 回 5：該場次正在收尾（收尾鎖被持有），或某一步逾時（見〈5. 收尾與救援〉）。

**`record` 封閉清單之外的頂層指令**：`meeting search`、`meeting sync`、`meeting reminders` 是 `meeting` 頂層的子指令，不屬於 `record`，
所以不在上表；說明見〈10. 搜尋、影音補償與提醒事項〉。`record` 後面也沒有 `sync`、`discard` 這類寫法：寫了會照 R2 的規則被當成根目錄名稱。
**保留字**：`sync`、`search`、`reminders` 因此成為 `meeting` 頂層的保留字——根目錄剛好叫這三個名字時，前處理要寫 `meeting ./search` 這種 `./` 寫法（`meeting search` 會被當成搜尋指令）。

## 1. 開錄：`meeting record`

在終端機（有 tty）跑：

```bash
meeting record "<會議根目錄>"
```

它會依序問：根目錄、場次名、會議型態、出席者、要錄哪個視窗（清單見〈會議視窗標記〉，有 ★ 的列是預設，直接按 Enter 即選它），
接著提示「可以說一句話」並跑開錄前檢查（preflight），全部 hard 項通過才開始錄（沒說話也會開錄，只會提示麥克風很安靜）。
答案記成下次的預設值，快捷鍵（quick-start）就是讀這份預設值。

- 只想先看有哪些視窗：`meeting record windows`（機器可讀用 `meeting record windows --json`）。
- 只想先跑開錄前檢查、不錄：`meeting record preflight --window <id>`。
- **沒有 tty 的呼叫者**（例如其他 Claude Code session 透過 Bash 工具呼叫）沒辦法回答問題，一定要帶 `--window <id>`
  （id 從 `meeting record windows` 取得），否則回 2：`meeting record "<會議根目錄>" --window <id>`。

錄製中隨時看狀態：`meeting record status`。

**同一時間只能有一場錄製（開錄互斥鎖）**：錄製器的 `start`、`quick-start`、`preflight` 一開始就持有 `~/.meeting-harness/record.lock`，
持有到程序結束；終端機、快捷鍵、menu bar 開錄前都會先試鎖（1 秒內每 100 ms 重試一次，拿到立刻放掉）。
鎖被持有時，`meeting record` 回 2、stderr 說「已有錄製在跑」，不會啟動錄製器、也不會動到正在錄的那場的狀態檔；
quick-start、menu bar 的開錄同樣拒絕，`record.log` 記一行「已有錄製在跑」。錄製器當掉時鎖會跟著程序釋放，不需要手動刪檔。
極少數情況下兩個終端機幾乎同時開錄、都通過了試鎖，由錄製器的鎖決定誰勝出：落敗的那邊等不到狀態，照「開錄後 20 秒內沒有任何狀態」回 4，不會有兩場同時在錄。

## 2. 開錄前檢查（preflight）失敗時怎麼救

preflight 共 13 項，分 hard 與 warn：**任何 hard 項失敗就不開錄**；warn 項只提示、照常開錄（提示也會列在輸出）。
多項同時失敗時結束碼取 4 ＞ 3 ＞ 2。

| # | 項目 | 等級 | 失敗碼 | 怎麼救 |
|---|---|---|---|---|
| 1 | 簽章身分 | warn | — | ad-hoc 簽章或 app 重建過時提示；若之後擷取失敗，到系統設定重新授權螢幕錄製與麥克風 |
| 2 | 螢幕錄製權限 | hard | 4 | 系統設定 › 隱私權與安全性 › 螢幕與系統錄音，打開 MeetingRecorder；授權後**要完全結束 MeetingRecorder 再重開** |
| 3 | 剛授權要重啟 | hard | 4 | 已授權但還沒生效：**完全結束 MeetingRecorder 再重開**，然後重跑 |
| 4 | 麥克風權限 | hard | 4 | 系統設定 › 隱私權與安全性 › 麥克風，打開 MeetingRecorder；第一次會跳授權框，按允許後重開再跑 |
| 5 | 系統聲音 RMS | hard（見右欄，有時只是 warn） | 4 | 先聽會議視窗所屬的 app 有沒有聲音，有就通過。沒有的話錄製器會播兩次提示音，確認系統聲音錄得到：錄得到 → 只提示「會議 app 目前沒有聲音」（warn）、照常開錄，開錄後若持續 15 秒沒聲音會告警；錄不到 → 不開錄，代表系統聲音擷取權限有問題：重新授權螢幕錄製；若剛授權，完全結束 MeetingRecorder 再重開。**輸出靜音不影響錄音**（Mac 按了靜音或音量調到 0，會議的聲音照樣錄得到，不必為了錄音把聲音打開） |
| 6 | 麥克風 RMS | warn（量不到時 hard） | — | 檢查的 3 秒內麥克風很安靜時只提示「麥克風目前很安靜」、照常開錄，開錄後若持續 15 秒沒聲音會告警；看到提示就確認麥克風沒被拔掉或靜音。螢幕錄製權限沒生效、量不到時才擋（結束碼 4） |
| 7 | 磁碟空間（含目標目錄可寫） | hard | 4 | 清出空間或換一個根目錄；寫不進 `~/Documents` 底下時，到系統設定給 MeetingRecorder「文件」資料夾權限 |
| 8 | 目標視窗存在 | hard | 3 | 會議視窗被關掉或換了 ID；重新跑 `meeting record` 選一次。有多個同 app、同標題的視窗時也會失敗，同樣重新選 |
| 9 | 場次撞名 | hard | 2 | 該場次已有音源檔或 `tracks/`；換一個場次名 |
| 10 | 電源 | warn | — | 用電池且電量 < 20% 時提示；接上電源 |
| 11 | 已有錄製在跑 | hard | 2 | 先 `meeting record stop`，或用 `meeting record status` 確認。R3 起錄製中直接跑 preflight 會在檢查之前就回 2（stderr 含「錄製中」），不跑這 13 項 |
| 12 | 視窗是否最小化 | warn | — | 會議視窗可能被最小化；把它還原（最小化期間錄不到畫面） |
| 13 | Apple Events（Chrome 會議分頁標記） | warn | — | 只影響 ★ 標記、不影響錄製；要開的話見〈會議視窗標記〉 |

權限類（2、3、4）改完一律**完全結束 MeetingRecorder 再重開**才會生效，「剛授權要重啟」與「沒有授權」的訊息不同，照訊息做即可。

## 3. 錄製中：暫停、麥克風靜音、標記

三件事都可以從終端機、menu bar 選單或全域快捷鍵做（快捷鍵要 menu bar 開著才有，見〈8. 快捷鍵與 menu bar〉）：

| 要做的事 | 終端機 | 快捷鍵 | menu bar 選單 |
|---|---|---|---|
| 整段暫停／繼續 | `meeting record pause`／`meeting record resume` | ⌃⌥⌘P | 「暫停錄製」（暫停中變成「繼續錄製」） |
| 麥克風靜音／取消 | `meeting record mute`／`meeting record unmute` | ⌃⌥⌘M | 「麥克風靜音」（靜音中打勾） |
| 加標記 | `meeting record mark` | ⌃⌥⌘B | 「加標記」 |

⌃ 是 Control、⌥ 是 Option、⌘ 是 Command；開始錄製是 ⌃⌥⌘R。

**麥克風靜音**：只靜音麥克風，系統聲音照錄（遠端的人照樣錄得到）。靜音期間麥克風軌照常寫，內容是數位 0，
所以軌道不中斷、收尾不受影響，也不會因此告警「麥克風沒聲音」。不會動到系統的麥克風設定，會議 app 那邊仍聽得到你——
要讓對方聽不到，請在會議 app 裡另外靜音。每次切換記在 `錄音/tracks/record.meta.json` 的 `micMuteEvents`；
menu bar 圖示變成左段有麥克風斜線的分段膠囊，選單與錄製小窗的麥克風音量條顯示「已靜音」。

**暫停**：整段暫停，畫面與兩路聲音都不錄；暫停的時段在成品裡**直接剪掉**（不補黑畫面、不補靜音），
繼續後從新的一段接著錄。暫停期間不會告警靜音、黑畫面；暫停中直接停止也照常收尾。
每次暫停與繼續記在 `record.meta.json` 的 `pauseEvents`（`t` 是錄製時鐘、含暫停時間；`outputT` 是成品時間），
收尾時 `manifest.json` 的 `gapStats.pausedTotal` 寫暫停總秒數。menu bar 的計時不含暫停時間，暫停中狀態列顯示「已暫停」。

**標記**：會議中聽到重點時按一下，記下「標記 N」（N 從 1 起），不收任何文字輸入。
錄製中寫在 `錄音/tracks/markers.json`，收尾時原樣複製成 `錄音/markers.json`（沒有標記就沒有這個檔）：

```json
[ { "t": 95.526, "recordT": 125.700, "wallClock": "2026-10-12T21:02:05+08:00", "label": "標記 1" } ]
```

`t` 是成品時間（扣掉暫停，直接對應 `影片/`、`錄音/` 成品的秒數）；`recordT` 是錄製時鐘；暫停中加的標記落在該次暫停點。
`markers.json` 不是音源檔，不影響 `meeting status` 的場次判斷。

**限制**：

- 舊版錄製器（R2 之前建置的 `MeetingRecorder.app`）開的錄製不能暫停／靜音／標記，五個寫法都回 3、stderr 說明是舊版；
  重新 `bash tools/MeetingRecorder/build.sh` 之後，下一場開始才有。
- 還在開錄前檢查、或正在收尾時也回 3；本來就是目標狀態（例如已經暫停又下 `pause`）時直接回 0、不重複送。
- 送出後 5 秒內狀態檔沒有反映就回 3；`meeting record status` 可以看目前是否暫停、是否靜音、有幾個標記。

## 4. 停止：`meeting record stop`

```bash
meeting record stop
```

停止後自動收尾（finalize）：逐段印進度，最後列出黑畫面區間（mm:ss–mm:ss）與各類告警次數。
收尾會整支重新編碼，長場次要等一下。回 5 表示停止了但收尾失敗或錄製中出過錯——段落都還在，用 `meeting record finish <場次>` 再收一次。

**stop 只停錄製器（pid 確認）**：送 SIGTERM 之前依序確認四項，任一項不成立就回 3、不送任何訊號，stderr 說明是哪一項：

1. `~/.meeting-harness/record.lock` 被持有（有錄製實例在跑）；
2. `record.pid` 記的 pid 還活著（已經死掉時順手刪掉這份過期的 `record.pid`）；
3. `record.status.json` 的 `pid` 與 `record.pid` 相同；
4. 該 pid 的程序名稱以 `MeetingRecorder` 結尾（不會因為 pid 被別的程序重用而誤殺它）。

正在停止或收尾中（狀態是 `stopping`、`finalizing`）時再下 `stop` 不會重送訊號，照常等結果。
等收尾的上限是 3 × 已錄時間（含暫停）＋ 630 秒，涵蓋錄製器自己的收尾期限與中止收尾所需的時間；讀不到開始時間時等 7200 秒。

不想留這場錄製時，不用 stop：用 menu bar 的「捨棄這次錄製…」（見〈8. 快捷鍵與 menu bar〉）。捨棄只在 app 裡，CLI 沒有對應寫法。

錄製中會告警的情況：系統聲音或麥克風任一路連續 15 秒幾乎沒聲音、畫面連續 5 秒全黑、會議視窗被暫停（例如最小化）、
磁碟剩不到 2 GB（會自動優雅停止並收尾，結束碼 5）。切換耳機或喇叭只記錄、不告警。

## 5. 收尾與救援：`meeting record finish`

```bash
meeting record finish "<場次目錄>"
```

錄製被中斷（當機、`kill -9`、電腦重開）時用它把已落盤的段落收成影片與 wav。`meeting record status` 回 5 就是在提醒你跑它。

- **最後一段未收尾的 1 分鐘會丟**（上限）：段落每 60 秒換一段，正在寫的那一段每 10 秒落一次盤（畫面靜止時也一樣），所以實際通常只丟最後約 10 秒。實測 `kill -9` 前錄了 133 秒，救回 130 秒；110 秒的場次救回 100 秒。
- 可以重跑：已完成的場次再跑一次會回 0、印「已完成」，不會改動任何輸出檔。
- 讀不到的段落會略過並列出，其餘照常完成；略過的段落搬到 `錄音/tracks/unreadable/`（撞名加 `-1`、`-2`），不會被刪，
  `tracks/finalize.json` 的 `skipped[]` 每筆是 `{"file": "seg-0002.mov", "movedTo": "tracks/unreadable/seg-0002.mov"}`（搬不動時 `movedTo` 為 `null`、段落留在原處）。
- **收尾鎖**：同一個場次同時只能有一個收尾在跑（`錄音/tracks/.finalize.lock`）。錄製器正在收尾時再跑 `meeting record finish` 會回 5、stderr 說「這個場次正在收尾」，場次裡的檔一個都不動；等它收完再看結果即可。
- **逐步逾時**：每一個 ffmpeg／ffprobe 步驟都有上限——ffprobe 30 秒；逐段正規化 max(120 秒, 該段長度 × 10)；串接與混音 max(300 秒, 全片長度 × 3)。
  任一步逾時就中止該步、回 5，`tracks/finalize.json` 記 `timedOut`（哪一步、上限幾秒），段落全部保留，之後可以再跑 `meeting record finish`。
  每一步的耗時印一行 `耗時 normalize（seg-0001）：1.2 秒`；錄製器啟動的收尾寫進 `~/.meeting-harness/record.log`，直接跑 finish 時印在終端機。
- **收尾總期限與取消收尾**：錄製器自己跑的收尾，超過 3 × 已錄秒數 ＋ 600 秒就判定「收尾逾時」；收尾中按 menu bar 的「取消收尾」則是「收尾已取消」。
  兩者都會先對收尾子程序送 SIGTERM、5 秒後還在就 SIGKILL，狀態寫失敗、結束碼 5，訊息附上補救指令 `meeting record finish <場次>`；段落都還在。
- 收尾**成功**後會自動刪掉 `tracks/seg-*.mov`（內容與 `影片/` 的成品重疊）；`manifest.json`、`record.meta.json`、`finalize.json` 留著，之後再跑 `meeting record finish` 會回「已完成」。收尾失敗時段落一律保留。要保留段落做驗收時，建立空檔 `~/.meeting-harness/keep-segments`（或設 `MH_KEEP_SEGMENTS=1`）。
- 段落檔（`tracks/seg-*.mov`）裡系統聲音與麥克風是分開的兩條音軌，收尾時才混成一軌；直接開段落檔時，有些播放器只播第一條（只聽得到遠端）。正式成果請看 `影片/` 與 `錄音/`。

## 6. 資料擺法

```
<根>/<YYYYMMDD>/<場次名>/
├── 錄音/
│   ├── <場次名> <YYYY-MM-DD HH.MM.SS>.wav   ← 收尾最後一步才出現（16 kHz 單聲道，直接給轉錄用）
│   ├── meeting.json                         ← 開錄前寫（型態、出席者）
│   ├── markers.json                         ← 有加標記才有，收尾時從 tracks/ 複製過來
│   └── tracks/                              ← 錄製段落 seg-0001.mov …、manifest.json、record.meta.json、markers.json、finalize.json
│       └── unreadable/                      ← 收尾時讀不到的段落搬來這裡（有才有，不會被刪）
├── 影片/
│   └── <場次名> <YYYY-MM-DD HH.MM.SS>.mov   ← 會議視窗畫面＋混音（遠端＋自己）
└── 照片/
```

錄製與收尾期間 `錄音/` 第一層不會有音源檔，所以同時跑 `meeting status`／前處理也不會把錄到一半的場次當成場次。
磁碟峰值約為錄製大小的 4 倍（段落＋收尾暫存＋輸出），preflight 第 7 項會先算好。
錄完後照 **meeting-summary**：`meeting "<根>"` 做前處理，再寫會議紀錄。

## 7. 會議視窗標記

清單（`meeting record windows`、互動選單）每列依序顯示：

1. ★ 列才有：`★ 會議（<服務名>）`
2. 名稱：`<app> — <標題>`；沒有標題的視窗顯示 `<app>（無標題）`（例如 LINE 通話視窗，照樣列出、可以選）
3. 尺寸：`<寬>×<高>`（point）
4. `全螢幕尺寸`：視窗和某個螢幕一樣大（只描述尺寸，不代表一定是 native 全螢幕）
5. 狀態：`前景`、`背景` 或 `不在畫面上`（在別的 Space 也可以錄）
6. `（這個視窗有會議分頁，但目前顯示的不是它）`：見下方「只看作用中分頁」

例：`★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上`

★ 列排在最前面，互動選單的預設就是第一個 ★ 列；沒有 ★ 列時沒有預設，要自己選。★ 只有兩個來源：

- **原生會議 app**：Teams、Zoom、Webex、騰訊會議。
- **Chrome 的會議分頁**：作用中分頁的網址是 M+ Meet、Google Meet、Teams、Zoom、Webex 的會議頁。

其他一律不標 ★（Safari、其他瀏覽器、LINE 都不標，自己選即可）。

**只看作用中分頁**：單視窗錄製只錄得到該視窗正在顯示的分頁。會議分頁在背景時，那個 Chrome 視窗不標 ★、
label 加上「（這個視窗有會議分頁，但目前顯示的不是它）」——先切到會議分頁再選。

**Apple Events 授權是選用的**：Chrome 會議分頁的 ★ 要讓 MeetingRecorder 以 Apple Events 唯讀查 Chrome 各視窗的分頁網址
（只讀標題與網址、不切分頁、不執行任何東西、Chrome 沒開時不會把它打開；網址只在記憶體比對，不寫進任何檔）。

- 第一次在終端機跑 `meeting record` 或 `meeting record windows` 時，系統會跳「允許控制 Google Chrome」的授權框，
  按允許即可。
- 之後要改：系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome。
- **不授權也能錄**：清單照常列出、照常可以選，只是 Chrome 視窗沒有 ★（清單最後會多一行說明）；preflight 第 13 項是 warn、不擋開錄。
- 不授權（或從沒在終端機跑過 `meeting record`）時，quick-start 看不到 Chrome 會議分頁的 ★，
  可能因此找不到唯一的會議視窗而不開錄（通知會說明）；這時改在終端機跑 `meeting record` 選視窗。
- 快捷鍵（quick-start）與 menu bar 不會跳授權框；沒有 tty 的呼叫也不會。

**清單裡找不到我的視窗**：用診斷子指令列出所有視窗（含被濾掉的，與被濾掉的原因 layer／size）與 Apple Events 狀態，不跳授權框：

```bash
open -n -a MeetingRecorder --args diagnose-windows --log "$HOME/.meeting-harness/diagnose-windows.txt"
```

清單只濾掉兩種：不是一般視窗層（layer）、寬 < 400 或高 < 300 pt（size，例如 Chrome 全螢幕時的工具列）。

## 8. 快捷鍵與 menu bar

**Shortcuts 捷徑（全域快捷鍵）**：

1. 打開「捷徑」（Shortcuts）app，新增一個捷徑，命名例如「開始錄會議」。
2. 加入「執行 Shell 腳本」動作，內容只放這一行：

```
open -n -a MeetingRecorder --args quick-start
```

3. 在捷徑的詳細資訊裡「加入鍵盤快速鍵」，設一組你要的按鍵。

quick-start 用上次 `meeting record` 留下的預設值（根目錄、型態、出席者）開錄，場次名是「<HHMM> 會議」；
存檔位置以 menu bar「存到」選的位置優先，沒選過才用終端機上次的根目錄。
清單裡**恰好一個** ★ 視窗才會開錄；沒有預設值（先在終端機跑一次 `meeting record`）或 ★ 不是恰好一個時，以通知說明原因、不開錄，不會猜。

**menu bar**：用下面這行在 menu bar 放一個圖示（直接打開 app、不帶參數也一樣進 menu bar）：

```bash
open -n -a MeetingRecorder --args menubar
```

這行重複執行也只會有一個圖示（已經有 menu bar 在跑時，新開的會直接結束）。

第一次打開 menu bar（還沒完成過設定）時會先出現**首次設定**的 5 步引導：歡迎 → 權限（「先給三個權限」：螢幕錄製、麥克風、通知，自動化（Chrome）標「選用」）→
存檔位置（含 harness 位置）→ 選單列空間（圖示被瀏海或其他圖示擋住時，可以改成一律顯示錄製小窗）→ 試錄（錄 5 秒看兩路有沒有聲音，並說明四組快捷鍵）。
每一步都能「略過」；完成、全部略過或關掉視窗後就不再自動出現，要重來到設定的「權限」分頁按「重新執行首次設定…」。
試錄的檔放在系統暫存目錄、錄完直接刪掉，不會寫進你的會議根目錄；引導只會在「存檔位置」這一步寫 `record.defaults.json` 的 `harness` 與 `root` 兩個鍵（合併寫入，其他鍵保留）。

**選單列圖示**（8 種外觀，灰階也分得出來，不只靠顏色）：待機是 `record.circle` 圖示；檢查中是外框膠囊「檢查中」；錄製中是紅色實心膠囊＋圓點＋計時（例如 `02:00`，不含暫停時間）；
麥克風靜音是分段膠囊，左段是麥克風斜線；有告警時膠囊帶告警標示；暫停中顯示暫停樣式（有告警時加角標）；收尾中與需要處理（開錄前檢查沒過、錄製失敗）各有自己的樣式。
檢查中與收尾中不會是紅色。設定可以關掉計時（膠囊照畫）。VoiceOver 與滑鼠停留提示讀成「MeetingRecorder：錄製中，已錄 12 分 34 秒」這類句子，**不含場次名**（分享整個螢幕時提示也不會洩漏場次名）。
圖示可以按住 ⌘ 拖到別的位置，重開後保留。

**選單依階段整份換掉**：不屬於目前階段的項目直接隱藏；階段內暫時不能用的才灰掉（例如舊版錄製器開的錄製，暫停、麥克風靜音、加標記灰掉）。
R3 改了幾個項目的名稱，括號裡是 R2 的舊稱：「錄其他視窗」（R2 稱「錄這個視窗」）、「停止錄製並收尾」（R2 稱「停止錄製」）、「設定…」（R2 稱「偏好設定…」）。

| 階段 | 選單（分組依序，組間有分隔線） |
|---|---|
| 待機 | 狀態列／「開始錄製（用上次的設定）」⌃⌥⌘R、「錄其他視窗」、「存到」／「打開場次資料夾」、「顯示上一場成品」／「設定…」⌘,、「結束 MeetingRecorder 選單」⌘Q |
| 錄製中 | 狀態列、即時音量條（系統、麥克風兩條；靜音時麥克風那行顯示「已靜音」）、告警列（有告警才有）／「暫停錄製」⌃⌥⌘P（暫停中「繼續錄製」）、「麥克風靜音」⌃⌥⌘M、「加標記」⌃⌥⌘B（已有標記時顯示「加標記（已有 N 個）」）／「停止錄製並收尾」、「捨棄這次錄製…」／「顯示錄製小窗」、「打開場次資料夾」／「設定…」、「結束 MeetingRecorder 選單」 |
| 收尾中 | 狀態列／「取消收尾」／「打開場次資料夾」／「設定…」、「結束 MeetingRecorder 選單」 |
| 需要處理 | 狀態列／「錯誤詳情…」、「複製完整訊息與補救指令」／「開始錄製（用上次的設定）」、「錄其他視窗」、「存到」／「打開場次資料夾」、「顯示上一場成品」／「設定…」、「結束 MeetingRecorder 選單」 |

開始、「錄其他視窗」、「存到」要先在終端機跑過一次 `meeting record`（留下預設值）。快捷鍵 ⌃⌥⌘R／P／M／B 與 ⌘,、⌘Q 都和 R2 相同（⌃⌥⌘R 只做開始，不做停止）。

- **開始錄製**：與 quick-start 相同。目前的視窗清單恰有一個 ★ 時，標題會改成「開始錄製：<app 名稱>」。
- **錄其他視窗**（R2 稱「錄這個視窗」）：子選單列出目前的視窗（★ 在前；讀取中顯示「讀取視窗清單中…」，10 秒取不到顯示「取不到視窗清單」），
  點一列就用上次的設定錄那個視窗，不需要清單裡恰好一個 ★；那個視窗已經關掉或有同名視窗分不清時，以通知說明、不開錄。不會跳授權框。
- **存到**：子選單列出目前的存檔位置（打勾）與最近用過的 5 個（資料夾不見了的灰掉並標「（找不到）」），
  「選擇資料夾…」可以挑新位置；選定的位置記在 `~/.meeting-harness/menubar.prefs.json`，之後 menu bar 與 quick-start 開錄都存到這裡。
  終端機的 `meeting record` 照常問根目錄，不受影響。
- **停止錄製並收尾**（R2 稱「停止錄製」）：停止前同樣做〈4. 停止〉的 pid 確認。按下後進入收尾中，狀態列顯示「收尾中…」（錄製中有告警時是「收尾中…（告警 N 則）」）。
  收尾完會送一則通知，通知上有「在 Finder 顯示」，按了會在 Finder 選取 `影片/` 下最新的 `.mov`（沒有就選場次資料夾）。
- **捨棄這次錄製…**：只在錄製中出現，**只有 app 裡有，CLI 沒有對應寫法**。按下後先跳確認框「捨棄這次錄製？」，說明已錄多久、會停止錄製、不收尾、不產生成品，
  錄音資料夾會移到垃圾桶；框開著時錄製照常進行。預設鍵是「繼續錄製」（按 Return 或關掉框都不會捨棄，也沒有任何副作用），
  要捨棄得用滑鼠按「捨棄並移到垃圾桶」。確認後錄製器停止、不跑收尾，把 `<場次>/錄音/` 移到垃圾桶（場次資料夾只剩 `meeting.json` 時連場次資料夾一起移），
  可以從垃圾桶「放回原處」；不會直接刪除。捨棄成功的場次不會觸發「停止後自動跑前處理」；移動失敗時檔案原地保留、狀態顯示失敗。
- **取消收尾**：只在收尾中出現，中止正在跑的收尾（見〈5. 收尾與救援〉的「收尾已取消」），段落保留，之後用 `meeting record finish <場次>` 再收。
- **錯誤詳情…**：需要處理時出現，打開「錯誤詳情」小視窗，顯示訊息、補救指令（可選取）與 `record.log` 路徑，並有「複製完整訊息與補救指令」按鈕；不顯示視窗標題與場次名。
- **顯示上一場成品**：同「在 Finder 顯示」，選取上一場成功收尾的成品；還沒有任何一場時灰掉。
- **結束 MeetingRecorder 選單**：只關掉 menu bar，不會停止正在進行的錄製。

錄製中出現的告警，收尾成功後就回到待機；開錄前檢查沒通過、錄製失敗或異常中止的告警狀態會一直留著，直到下次開始錄製（詳細內容在停止時的終端機輸出與 `manifest.json`）。
錄製中切換耳機或喇叭（輸出裝置）時，錄製器會在切換點提前換一段，方便收尾時分段處理影音延遲（見〈10.〉的 `meeting sync`）。暫停中狀態檔每 5 秒更新一次 `updatedAt`，menu bar 據此判斷錄製器還活著。

**錄製小窗（HUD）**：錄製中可以不看選單列就看到狀態、做控制。小窗貼在螢幕右緣（或左緣）是一個直立標籤（紅點＋直排計時），
滑鼠移進去展開成面板：「錄製中」／「已暫停」＋計時、系統與麥克風兩條音量條，以及「暫停」「靜音」「標記」「停止」四顆按鈕（和選單走同一條控制路徑）；
滑鼠離開後收合，點標籤可以固定展開。小窗不搶焦點、所有桌面都看得到，也**不會被螢幕分享或錄影擷取**；不顯示場次名與視窗標題；收尾中與之後不顯示。
顯示時機看設定的「錄製小窗」：「自動」（預設；選單列圖示被瀏海或其他圖示擋住時才顯示，每 5 秒檢查一次）／「一律顯示」／「不要」；
選單的「顯示錄製小窗」可以只在這一場強制顯示。錄製中出現新告警時，小窗會自動展開 8 秒並顯示告警內容，標籤外框改成告警色直到這場結束。

**通知**：錄製中出現新告警時發通知（同一則只發一次；設定可選「用時效性通知（可穿過專注模式）」）；失敗、完成照常通知；
快捷鍵的回饋則看得到錄製小窗就顯示在小窗、看得到選單列圖示就不另外通知，兩者都看不到才發通知。通知不含場次名與視窗標題。

**會議偵測**：menu bar 開著、沒有錄製在跑時，每 3 秒讀一次「預設輸入裝置是否有 app 在用」（只讀這個狀態，**不會打開麥克風**）；
前景 app 是 ★ 清單裡的會議 app 且開始用麥克風時，送一則通知「錄這個會議？」，內文只放 app 名稱（不放視窗標題），
動作「開始錄製」（走 quick-start，用上次的設定）與「這場不用」（這次通話不再問）。會議偵測**只提示、不會自動開錄**；
同一次通話只問一次；設定的「回饋與通知」分頁可以關掉（「偵測到會議 app 使用麥克風時問我要不要錄」）。

**快捷鍵**：menu bar 開著時，四組全域快捷鍵都能用——⌃⌥⌘R 開始錄製、⌃⌥⌘M 麥克風靜音、⌃⌥⌘P 暫停／繼續、⌃⌥⌘B 加標記，
各自只觸發自己的動作。某一組被別的 app 佔用時那一組不會生效：`record.log` 會記一行「<按鍵> 註冊失敗」、選單上那一項不再顯示按鍵，
其他組照常；這時改用選單、終端機，或上面的 Shortcuts 捷徑。

**設定**：選單「設定…」（⌘,，R2 稱「偏好設定…」）打開設定視窗，改了立即生效、沒有確定按鈕。上方是 7 個分頁，視窗標題跟著分頁變，下次打開回到上次的分頁：

- **一般**：預設存檔位置與「更改…」（和「存到」是同一個設定）；「登入時自動開啟」（預設關）：勾了之後登入時自動開 menu bar。
  系統要求你核准時，下方會說明，並多一顆「打開系統設定的登入項目」，到系統設定 › 一般 › 登入項目把 MeetingRecorder 打開。
  只有你自己勾這一格才會註冊，任何自動流程都不會替你註冊。harness 位置唯讀。
- **錄製**：預設會議類型與與會者（唯讀，來自終端機上次的答案）、★ 規則說明。
- **回饋與通知**：選單列計時、錄製小窗（自動／一律顯示／不要）與位置（右邊緣／左邊緣）、用時效性通知、會議偵測、通知授權狀態。
- **快捷鍵**：四組快捷鍵的清單（唯讀；註冊失敗的那組就地標「註冊失敗」）。
- **錄完之後**：「停止後自動跑前處理」（預設關）：勾了之後，menu bar 看到一場錄製成功收尾（結束碼 0），就在背景跑該場次的前處理
  （`meeting prep "<場次目錄>"`，同一時間只跑一個、其餘排隊），輸出寫到 `~/.meeting-harness/autoprep.log`；
  跑完送通知（成功是「前處理完成」＋場次名，失敗會附結束碼與 autoprep.log）。只處理 menu bar 開著時看到錄製中的場次；收尾失敗（結束碼 5）與捨棄的不跑。
- **權限**：四項權限的狀態與「打開系統設定」、「重新執行首次設定…」。
- **進階**：目前的影音延遲補償模式（唯讀；要改用 `meeting sync`）與 log 位置。

這些設定存在 `~/.meeting-harness/menubar.settings.json`（只有 app 寫）；R2 的 `menubar.prefs.json` 照舊。

## 9. 目前目錄有 `record` 資料夾

`meeting record …` 在目前目錄有名為 `record` 的資料夾時不會默默選邊：有 tty 就問你要錄製還是要把 `./record` 當會議根目錄跑前處理；
沒有人可問（沒有 tty，或帶了 `--yes`）就回 2，並印出兩種明確寫法：

- 要錄製：`meeting record --recorder …`（例 `meeting record --recorder windows`）
- 要前處理：`meeting prep ./record`

其他 session 經 Bash 工具呼叫（沒有 tty）時，一律直接寫 `--recorder`。

## 10. 搜尋、影音補償與提醒事項（`meeting search`、`meeting sync`、`meeting reminders`）

這三個是 `meeting` 頂層的子指令，不屬於 `record`（不在上面的 `record-cli` 表），都不需要錄製器在跑。
它們讓 `search`、`sync`、`reminders` 成為 `meeting` 頂層的保留字：根目錄剛好叫這些名字時，前處理寫成 `meeting ./search`、`meeting ./sync`、`meeting ./reminders`。

### `meeting search <根> <關鍵字>`：跨場次搜尋

```bash
meeting search "<會議根目錄>" "Stand-up"
```

搜 `<根>` 底下各場次的 `summary.md`、`meeting.record.json`、`錄音/transcript.speakers.md`、`錄音/transcript.raw.md`。
大小寫不分、照字面比對（`.*` 這類字元不當成正規表示式）。每筆一行：

```
20261013/[Stand-up] 範例專案/錄音/transcript.speakers.md:42: 那這週的 Stand-up 先到這裡…
```

格式是 `<場次相對根目錄的路徑>/<檔名>:<行號>: <該行>`（超過 120 字截斷加「…」）；場次依資料夾名稱新到舊，同場次依檔名、行號排序。
只讀這個根目錄底下的檔：指到根目錄外的 symlink 不會跟進去，也不會跨到別的根目錄（不同客戶的資料各放各的根目錄）。
結束碼：0 有結果；1 沒有結果（stdout 為空）；2 缺參數或根目錄不存在。

### `meeting sync [off|reported|calibrated]`：系統聲音的影音延遲補償

用藍牙耳機等有輸出延遲的裝置開會時，成品裡遠端的聲音可能比畫面早一點。`meeting sync` 設定收尾時要不要依段落把系統聲音往後挪：

| 模式 | 做什麼 |
|---|---|
| `off`（預設） | 不補償，和 R2 的收尾完全相同 |
| `reported` | 用錄製時 Core Audio 回報的輸出延遲（記在 `錄音/tracks/record.meta.json` 的 `outputLatencies`），依段落延後系統聲音 |
| `calibrated` | 用你手寫的 `~/.meeting-harness/sync-calibration.json`（`{"schemaVersion": 1, "devices": {"<輸出裝置 uid>": <秒數>}}`）；沒有該裝置的值就當 0，超過 0.5 秒夾到 0.5 |

```bash
meeting sync              # 印目前模式，例如 syncCompensation=off
meeting sync reported     # 改成 reported，印 syncCompensation=reported（下一次收尾起生效）
```

設定寫在 `~/.meeting-harness/record.defaults.json` 的 `syncCompensation` 鍵：以 `record.defaults.lock` 取鎖（最多等 5 秒）、讀後合併寫入，其他鍵原樣保留；
檔案不是 JSON 物件時不覆寫、回 2。參數不是三個值之一、或給了多個參數，也回 2 且檔案不變。
預設維持 `off`：`reported` 的方向與大小還沒在實機驗收場確認過，改預設要等實機結果再由使用者決定。每次收尾用的模式與各段延遲記在 `tracks/finalize.json` 的 `syncCompensation`。

### `meeting reminders <場次> --list <名稱> [--dry-run]`：交辦寫進提醒事項

把 `<場次>/meeting.record.json` 的交辦（`actions[]`）寫進 macOS「提醒事項」裡名稱完全相同的清單：

```bash
meeting reminders "<場次目錄>" --list "工作" --dry-run   # 先看會寫什麼（印 JSON，不啟動 app）
meeting reminders "<場次目錄>" --list "工作"             # 真的寫入
```

- 每筆的標題是交辦內容，備註是「負責人：<負責人>」（沒有負責人寫「負責人：（未定）」）加場次名，期限照 `meeting.record.json`，**沒有期限就不設、不猜**。
- 每筆帶一個 `meetingharness://action/<uid>` 網址（`uid` 與同場 `actions.ics` 的 `UID` 相同）：重跑時同一筆會更新、不會重複新增。
- 清單要先自己在「提醒事項」建好，**不會代建**；第一次會跳提醒事項的權限框（完整取用）。
- **隱私**：「提醒事項」的清單如果開了 iCloud 同步，寫進去的交辦內容（標題、負責人、場次名）會同步到 iCloud，**離開本機**。
  錄製與前處理全程本機，這一步則取決於清單的同步設定；不確定時先用 `--dry-run` 看內容，或改寫進只存在「我的 Mac」上的清單。
- 結束碼：0 寫入完成（`--dry-run` 為印完）；2 缺參數、場次沒有 `meeting.record.json`、或錄製器 app 還沒建置；3 指定的清單不存在；4 提醒事項權限被拒；5 寫入失敗（可能已寫入部分項目，重跑會去重）。

## 重要原則
- 錄檔（`.mov`、`.wav`）只放會議資料夾，不放進 repo。
- 不改使用者的預設輸入／輸出裝置，不需要 BlackHole 或多重輸出裝置；切換耳機照常錄。
- 錄完的 raw 逐字稿照 meeting-summary 的鐵則處理：不改、不編造、不確定的姓名不掛。

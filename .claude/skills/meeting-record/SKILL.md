---
name: meeting-record
description: 會議開始前用：把會議視窗（Teams、Zoom、Chrome 裡的 M+ Meet／Google Meet 等）連同系統聲音與麥克風錄下來，落到會議資料夾的 錄音/ 與 影片/，錄完直接接 meeting-summary。全程本機。當使用者要「錄會議／開始錄製／停止錄製／錄影沒收尾要救回」時使用。
---

# meeting-record（錄下會議視窗與雙路音訊）

會議**開始前**用。錄製器 `MeetingRecorder.app` 只錄你選的那一個會議視窗（切到別的 Space 也錄得到），
同時錄系統聲音（遠端的人）與麥克風（你自己），每 60 秒落一段到磁碟；停止後自動收尾成一支影片與一個 wav，
放進會議資料夾，之後照 **meeting-summary** 做前處理與會議紀錄。

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
| `meeting record help` | — | 0 |
<!-- record-cli:end -->

上表之外還有兩個 `meeting.sh` 層旗標，所有寫法都能加、位置不限（`record` 之後任何位置）：

- `--recorder`：明確要錄製，略過 `./record` 撞名檢查（見〈目前目錄有 record 資料夾〉）。
- `--yes`：宣告沒有人可問，只影響 `./record` 撞名的判斷。

`meeting record help`（或 `-h`、`--help`）印出完整說明，不啟動錄製器。`help` 是保留字：根目錄剛好叫 `help` 時寫 `meeting record ./help`。

結束碼的意思：

| 碼 | 意思 |
|---|---|
| 0 | 成功（`status` 包含「沒有錄製在跑」；`finish` 包含「已完成」） |
| 2 | 參數或前提不符：缺參數、根目錄不存在、app 未建置、場次撞名、已有錄製在跑、非互動又沒有 `--window`；任何寫法遇到未知的選項、或 `./record` 撞名而沒有人可問，也回 2 |
| 3 | 找不到目標：視窗不存在、沒有錄製在跑（`stop`）、該場次沒有段落（`finish`） |
| 4 | 開錄前檢查的 hard 項失敗（權限、RMS、磁碟），或開錄後 20 秒內沒有任何狀態（多半是權限）；`windows` 取不到視窗清單（權限） |
| 5 | 錄製或收尾出錯，已落盤段落保留——用 `meeting record finish <場次>` 收尾；`status` 回 5 表示上次錄製異常中止 |

## 1. 開錄：`meeting record`

在終端機（有 tty）跑：

```bash
meeting record "<會議根目錄>"
```

它會依序問：根目錄、場次名、會議型態、出席者、要錄哪個視窗（清單見〈會議視窗標記〉，有 ★ 的列是預設，直接按 Enter 即選它），
接著提示「請說一句話」並跑開錄前檢查（preflight），全部 hard 項通過才開始錄。
答案記成下次的預設值，快捷鍵（quick-start）就是讀這份預設值。

- 只想先看有哪些視窗：`meeting record windows`（機器可讀用 `meeting record windows --json`）。
- 只想先跑開錄前檢查、不錄：`meeting record preflight --window <id>`。
- **沒有 tty 的呼叫者**（例如其他 Claude Code session 透過 Bash 工具呼叫）沒辦法回答問題，一定要帶 `--window <id>`
  （id 從 `meeting record windows` 取得），否則回 2：`meeting record "<會議根目錄>" --window <id>`。

錄製中隨時看狀態：`meeting record status`。

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
| 6 | 麥克風 RMS | hard | 4 | 檢查時要對麥克風說一句話；麥克風被拔掉或靜音就會失敗 |
| 7 | 磁碟空間（含目標目錄可寫） | hard | 4 | 清出空間或換一個根目錄；寫不進 `~/Documents` 底下時，到系統設定給 MeetingRecorder「文件」資料夾權限 |
| 8 | 目標視窗存在 | hard | 3 | 會議視窗被關掉或換了 ID；重新跑 `meeting record` 選一次。有多個同 app、同標題的視窗時也會失敗，同樣重新選 |
| 9 | 場次撞名 | hard | 2 | 該場次已有音源檔或 `tracks/`；換一個場次名 |
| 10 | 電源 | warn | — | 用電池且電量 < 20% 時提示；接上電源 |
| 11 | 已有錄製在跑 | hard | 2 | 先 `meeting record stop`，或用 `meeting record status` 確認 |
| 12 | 視窗是否最小化 | warn | — | 會議視窗可能被最小化；把它還原（最小化期間錄不到畫面） |
| 13 | Apple Events（Chrome 會議分頁標記） | warn | — | 只影響 ★ 標記、不影響錄製；要開的話見〈會議視窗標記〉 |

權限類（2、3、4）改完一律**完全結束 MeetingRecorder 再重開**才會生效，「剛授權要重啟」與「沒有授權」的訊息不同，照訊息做即可。

## 3. 停止：`meeting record stop`

```bash
meeting record stop
```

停止後自動收尾（finalize）：逐段印進度，最後列出黑畫面區間（mm:ss–mm:ss）與各類告警次數。
收尾會整支重新編碼，長場次要等一下。回 5 表示停止了但收尾失敗或錄製中出過錯——段落都還在，用 `meeting record finish <場次>` 再收一次。

錄製中會告警的情況：系統聲音或麥克風任一路連續 15 秒幾乎沒聲音、畫面連續 5 秒全黑、會議視窗被暫停（例如最小化）、
磁碟剩不到 2 GB（會自動優雅停止並收尾，結束碼 5）。切換耳機或喇叭只記錄、不告警。

## 4. 收尾與救援：`meeting record finish`

```bash
meeting record finish "<場次目錄>"
```

錄製被中斷（當機、`kill -9`、電腦重開）時用它把已落盤的段落收成影片與 wav。`meeting record status` 回 5 就是在提醒你跑它。

- **最後一段未收尾的 1 分鐘會丟**（上限）：段落每 60 秒換一段，正在寫的那一段每 10 秒落一次盤（畫面靜止時也一樣），所以實際通常只丟最後約 10 秒。實測 `kill -9` 前錄了 133 秒，救回 130 秒；110 秒的場次救回 100 秒。
- 可以重跑：已完成的場次再跑一次會回 0、印「已完成」，不會改動任何輸出檔。
- 讀不到的段落會略過並列出，其餘照常完成。
- `tracks/` 的段落永遠保留，程式不會自動刪；確定不需要時自己刪。
- 段落檔（`tracks/seg-*.mov`）裡系統聲音與麥克風是分開的兩條音軌，收尾時才混成一軌；直接開段落檔時，有些播放器只播第一條（只聽得到遠端）。正式成果請看 `影片/` 與 `錄音/`。

## 5. 資料擺法

```
<根>/<YYYYMMDD>/<場次名>/
├── 錄音/
│   ├── <場次名> <YYYY-MM-DD HH.MM.SS>.wav   ← 收尾最後一步才出現（16 kHz 單聲道，直接給轉錄用）
│   ├── meeting.json                         ← 開錄前寫（型態、出席者）
│   └── tracks/                              ← 錄製段落 seg-0001.mov …、manifest.json、record.meta.json
├── 影片/
│   └── <場次名> <YYYY-MM-DD HH.MM.SS>.mov   ← 會議視窗畫面＋混音（遠端＋自己）
└── 照片/
```

錄製與收尾期間 `錄音/` 第一層不會有音源檔，所以同時跑 `meeting status`／前處理也不會把錄到一半的場次當成場次。
磁碟峰值約為錄製大小的 4 倍（段落＋收尾暫存＋輸出），preflight 第 7 項會先算好。
錄完後照 **meeting-summary**：`meeting "<根>"` 做前處理，再寫會議紀錄。

## 6. 會議視窗標記

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

## 7. 快捷鍵與 menu bar

**Shortcuts 捷徑（全域快捷鍵）**：

1. 打開「捷徑」（Shortcuts）app，新增一個捷徑，命名例如「開始錄會議」。
2. 加入「執行 Shell 腳本」動作，內容只放這一行：

```
open -n -a MeetingRecorder --args quick-start
```

3. 在捷徑的詳細資訊裡「加入鍵盤快速鍵」，設一組你要的按鍵。

quick-start 用上次 `meeting record` 留下的預設值（根目錄、型態、出席者）開錄，場次名是「<HHMM> 會議」。
清單裡**恰好一個** ★ 視窗才會開錄；沒有預設值（先在終端機跑一次 `meeting record`）或 ★ 不是恰好一個時，以通知說明原因、不開錄，不會猜。

**menu bar**：用下面這行在 menu bar 放一個圖示，三種狀態：待機、錄製中、告警。

```bash
open -n -a MeetingRecorder --args menubar
```

這行重複執行也只會有一個圖示（已經有 menu bar 在跑時，新開的會直接結束）。

選單依序是狀態列、「開始錄製（用上次的設定）」、「停止錄製」、「打開場次資料夾」、「結束 MeetingRecorder 選單」；
當下不能用的項目會灰掉。「開始錄製」與 quick-start 相同，menu bar 開著時也可以直接按快捷鍵 ⌃⌥⌘R（Control＋Option＋Command＋R）；
這組按鍵被別的 app 佔用時快捷鍵不會生效（`record.log` 會記一行），改用選單或上面的 Shortcuts 捷徑。
「停止錄製」只在錄製中可點，按下後狀態列顯示「收尾中…」（錄製中有告警時是「收尾中…（告警 N 則）」），自動收尾完會送一則通知。
「結束 MeetingRecorder 選單」只關掉 menu bar，不會停止正在進行的錄製。錄製中出現的告警，收尾成功後就回到待機；開錄前檢查沒通過、錄製失敗或異常中止的告警狀態會一直留著，直到下次開始錄製（詳細內容在停止時的終端機輸出與 `manifest.json`）。

## 8. 目前目錄有 `record` 資料夾

`meeting record …` 在目前目錄有名為 `record` 的資料夾時不會默默選邊：有 tty 就問你要錄製還是要把 `./record` 當會議根目錄跑前處理；
沒有人可問（沒有 tty，或帶了 `--yes`）就回 2，並印出兩種明確寫法：

- 要錄製：`meeting record --recorder …`（例 `meeting record --recorder windows`）
- 要前處理：`meeting prep ./record`

其他 session 經 Bash 工具呼叫（沒有 tty）時，一律直接寫 `--recorder`。

## 重要原則
- 錄檔（`.mov`、`.wav`）只放會議資料夾，不放進 repo。
- 不改使用者的預設輸入／輸出裝置，不需要 BlackHole 或多重輸出裝置；切換耳機照常錄。
- 錄完的 raw 逐字稿照 meeting-summary 的鐵則處理：不改、不編造、不確定的姓名不掛。

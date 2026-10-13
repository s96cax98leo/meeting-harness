# spec：meeting-record（錄製器本體＋觸發層）

- epic：`meeting-record`；上游：`intent.md`（已核准）、`design.md`、`adr/`
- 需求正本：`_tpm/runs/20261010-sdlc-meeting-record/requirement.md`（以下 `req:<行>`）；D1–D16：同目錄 `gate1-decisions.md`（D6 藍牙必驗；D7–D12 為閘門 2 前的使用者決定；D13「文件先寫」、D14「告警停到下次開錄」為閘門 2 第三修正輪的使用者決定；D15「先診斷，再補進 spec」、D16「讀瀏覽器分頁網址來標記」為閘門 2 核准後、build 前補的使用者決定；D17、D18 為 test 段閘門前的使用者決定；D19「preflight 第 5 項兩段式、系統聲音範圍」為 test 段 t6 實機驗收中的使用者決定；D20「自己管 AVAssetWriter（建議）」為 t6 量測閘門不過後的使用者決定，本檔標「D20」的節是 t6 中途修正輪新增或改寫，實機紀錄見同目錄 `t6-results.md`；D21「改規格配合實機（建議）」——系統輸出靜音只 warn、D22「修正輪先試著修，修不好再放寬（建議）」——當機時段落讀不到的 fragment 問題，兩者為 t6 接續中的使用者決定，本檔標「t6 第二輪」的節是 t6 第二次中途修正輪新增或改寫，缺陷 A／B／E 的根因調查見同目錄 `t6-rca-ABE.md`、缺陷 F 的根因見 `design.md §7.4` 第 3 步）；D2 實測：同目錄 `d2-audio-experiment.md`（以下 `d2:<行>`）；視窗清單診斷：同目錄 `window-filter-diagnosis.md`（以下 `wfd:<行>`）；修正輪對照：同目錄 `design-revise-對照.md`（含第一至六輪）
- **t6 第三輪（2026-10-12，定案）**：t6 第二輪重測的發現 I（幕前調度把背景視窗縮成縮圖）、缺陷 J（finalize 串接後音訊每個段落邊界晚約 21–37 ms、逐段累積）、缺陷 K（`e2e_check.py` 的 sync 嗶聲偵測與 `hfp`／`device_switch` 判準）、缺陷 L（錄製中磁碟檢查讀到快取值）、發現 M（§4.3.3 影格間隔判準對 SCK 過嚴）與 §4.8.1 wav 上限，依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」，由主 session 依建議選項定案（使用者可於醒來後改選，§6 第 63–70 條）；本檔標「t6 第三輪」的節是這一輪新增或改寫，事實與數字見同目錄 `t6-results.md`「t6 第二輪重測」與「t6 第二輪 7」兩段，根因見 `design.md §7.1`〈幕前調度〉、`§7.4`〈缺陷 J〉。
- **Story ID 的替代**：本 repo 沒有任務系統、不得自編編號（`CLAUDE.md:29`、`rules.md:24`）。驗收條件以本檔**節編號**識別（例「spec §4.6.3」），「依據」欄寫需求正本行號；commit scope 用模組名（`record`、`meeting-record`）。此替代記在 §6。
- 驗收句型：EARS（「…應…」／「當…時，…應…」／「在…期間，…應…」／「若…，則…應…」）。
- 「測試」欄：`tests/record/<檔>::<函式>` 是 Python unittest；`swift:<檔>::<函式>` 是 `tools/MeetingRecorder/Tests/` 的 Swift 測試；「人工」是 test 段由使用者操作、`tests/record/e2e_check.py` 做機械核對的部分。

---

## 1. 範圍

**在範圍內**：需求正本第 1 階段（錄製器本體，`req:251-252`）與第 2 階段（觸發層，`req:254-255`）；新增 `meeting record` 的**七種寫法**（定義與清單只在 §2.4：intent §2 列的六種——`meeting record` 本身與 `windows`、`preflight`、`stop`、`status`、`finish`——加上 D13 新增的 `help`，§6 第 27 條）、第七個 skill `meeting-record`。本檔其他地方提到寫法數、旗標或 `meeting record` 的結束碼，一律以 §2.4 為準。GIT 管控修正（D4、D5）已在 `3f47b65` 完成，本 spec 以 §4.13.6（commit 格式）與 §4.13.7（設定內容，防迴歸）驗它；「第一個 commit」的字面差異見 §6 第 20 條。錄製器的視窗清單（篩選、會議標記、排序、每列顯示、視窗認回、診斷子指令）的唯一契約是 §3.8（D15、D16，第六修正輪補進）。

**不在範圍內**：見 `design.md §11` 與 intent §5〈明確在範圍外〉。

---

## 2. 結束碼對映（全域）

### 2.1 `meeting.sh` 既有面（不得改變）

| 情境 | 結束碼 | 依據 |
|---|---|---|
| 無參數 | 1 | `bin/meeting.sh:398` |
| 缺參數／路徑不存在／未知選項／未知指令 | 2 | `bin/meeting.sh:93,97,399,407` |
| 找不到場次 | 3 | `bin/meeting.sh:251,346` |
| `meeting diarize` 失敗 | 1（`run_diarize` 回 1） | `bin/meeting.sh:184,189` |

內部腳本的 `4`／`5`（`bin/diarize.sh:28,44`、`bin/transcribe.sh:190`、`bin/setup-diarize.sh:33,49`、`bin/to-docx.sh:15`）不經 `meeting.sh` 對外，語意與下表無關。

### 2.2 `meeting record …`（新增，`req:224`）

| 寫法 | 0 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| `record [<根>]` | 已開始錄製（`phase=recording`） | 缺參數／根目錄不存在／app 未建置／場次撞名／已有錄製在跑／非互動終端又沒有 `--window` | 目標視窗不存在 | preflight 有 hard 項失敗（權限、RMS、磁碟）；或 20 秒內沒有任何狀態（多半是權限） | 開錄後串流中斷，已落盤段落保留 |
| `record windows [--json]` | 列出成功 | app 未建置 | — | 取不到視窗清單（權限） | — |
| `record preflight [--window <id>]` | 沒有 hard 失敗（warn 可有） | app 未建置／`--window` 缺值 | 視窗不存在 | hard 失敗 | — |
| `record stop` | 已停止且 finalize 成功 | — | 沒有錄製在跑 | — | 停止了但 finalize 失敗或錄製中出過錯（段落保留，可 `record finish`） |
| `record status` | 正常（含「沒有錄製在跑」） | — | — | — | 偵測到上次錄製異常中止（pid 已死、phase 停在 `recording`／`stopping`／`finalizing`） |
| `record finish <場次>` | 完成或已完成（冪等） | 缺參數／路徑不存在 | 該場次沒有 `錄音/tracks/seg-*.mov` | — | finalize 失敗（段落保留） |
| `record help`（`-h`、`--help` 同義） | 依 §2.4.3 的格式印到 stdout | — | — | — | — |

**通則結束碼 2**（全部 7 種寫法都適用；上表各列的 2 欄**不重複列**）：(i) **未知選項**＝`meeting.sh` 先把 `record` 之後任何位置出現的層旗標 `--recorder`、`--yes`（每個出現處）拿掉、其餘參數維持原序交給 `record.sh`；拿掉層旗標之後，仍不屬於該寫法寫法旗標集合（§2.4.2 表第二欄的旗標名）的 `--` 開頭參數，即為未知選項，回通則結束碼 2。判斷範圍：寫法本身的字（含 `help` 同義字 `-h`、`--help`）與寫法旗標之值不參與判斷；只以單一 `-` 開頭的參數不算未知選項，照一般參數處理（§6 第 31 條）。（§2.4.2、§4.1.12）；(ii) 目前目錄有 `record/` 而沒有人可問（§2.3、§4.1.10）。上表 2 欄是 `—` 的寫法（`stop`、`status`、`help`）只會因通則回 2。§2.4 的「寫法結束碼」＝上表該列不是 `—` 的欄，不含通則的 2（第四修正輪：前一版 `status` 列的 2 只有「未知選項」，與 §2.4「未知選項的 2 不列入」互相矛盾）。

preflight 多項同時失敗：`4` ＞ `3` ＞ `2`（`design.md §4`）。MeetingRecorder 二進位自己的結束碼經 `open` 不可觀測，只以 `record.status.json.code` 傳遞。

### 2.3 `./record` 目錄撞名（D11，`design.md §8.1`）

適用於上表所有 `meeting.sh record …` 寫法：目前目錄有名為 `record` 的目錄時，有 tty（stdin 與 stderr 皆是）且參數沒有 `--yes` → 互動詢問「開始錄製／當會議根目錄跑前處理」；沒有人可問 → 結束碼 2，並印出 `meeting.sh record --recorder …`（明確要錄製）與 `meeting.sh prep ./record`（明確要前處理）兩種寫法。參數任何位置含 `--recorder`（例 `meeting.sh record --recorder …`、`meeting.sh record windows --recorder`）一律直接錄製、不檢查；參數任何位置含 `--yes` 即視為沒有人可問。層旗標的位置與拿掉規則見 §2.4.2。

### 2.4 `meeting record` 的 CLI 表面（文件與實作的共同契約，D13）

D13：文件先寫（t5），程式（t3、t4）照文件做。本節是 `meeting record` 對外可見面（寫法、旗標、結束碼）的**唯一定義**：§1 的寫法數、§2.2 的通則、§4.1.2（`meeting.sh help`）、§4.1.4（結束碼矩陣）、§4.1.11（`record help`）、§4.1.12（未知選項）、§4.12.6–4.12.8（文件一致性）一律引用本節的名詞與規則，不另行定義。`tests/record/surface.py` 照本節實作常數 `SURFACE` 與解析／組參數函式（§2.4.8），`test_docs.py`、`test_cli_dispatch.py`、`test_record_sh.py` 都 import 它，不各自另抄；`bin/record.sh` 的 `help` 照 §2.4.3、`bin/meeting.sh` 的 `usage()` 照 §2.4.6 輸出。結束碼的**語意**以 §2.2 為準，本節只定「哪些碼會出現」。（第四修正輪：前一版只有一張表加四條文字說明，`--recorder`／`--yes` 放不進區塊、help 第 2、3 段沒有行格式、`status` 的 2 有兩種讀法；本輪拆成 §2.4.1–2.4.8。）

#### 2.4.1 名詞

- **寫法（form）**：§2.4.2 表第一欄的字串，逐字比對（含 `[<根>]`、`<場次>` 佔位符；字與字之間恰好一個半形空白）。共 12 種＝intent §2 的 6 種＋D13 新增的 `help`＋R2 新增的 `pause`、`resume`、`mute`、`unmute`、`mark`（R2-Q5 使用者決定「全面更新子指令」，§6 第 77 條；第一輪為 7 種）。
- **寫法旗標（form flag）**：只屬於某一寫法的旗標，§2.4.2 表第二欄；以 `--` 開頭、含值佔位符的整串為一個旗標（`--window <id>` 是一個旗標）。**旗標名**＝去掉值佔位符的部分（`--window`）。
- **層旗標（layer flag）**：`--recorder`、`--yes`。由 `meeting.sh` 處理、所有寫法共用，**不是任何寫法的寫法旗標**：不出現在 §2.4.2 表第二欄、`record help` 的「旗標：」段、文件的 `record-cli` 區塊；只出現在 `record help` 的「meeting.sh 層旗標：」段（§2.4.3）與 `usage()` 的層旗標行（§2.4.6）。
- **`help` 同義字**：`-h`、`--help` 是 `help` 寫法的另外兩種拼法，不是旗標、不算未知選項、不列入任何旗標集合。
- **寫法結束碼**：§2.4.2 表第三欄＝§2.2 該寫法那一列不是 `—` 的欄，數字遞增。
- **通則結束碼 2**：§2.2 表後「通則」的兩種情境（未知選項、`./record` 撞名無人可問），適用全部寫法（R2 起 12 種），**一律不列入**寫法結束碼，也**不得**出現在 `EXIT_CODE_CASES`（§2.4.7）；分別由 §4.1.12、§4.12.8 (b) 與 §4.1.10 驗。

#### 2.4.2 封閉清單（`SURFACE`）

| 寫法 | 寫法旗標 | 寫法結束碼 |
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

- 層旗標（兩個，順序固定）：`--recorder`（明確錄製、略過 `./record` 撞名檢查，§2.3）、`--yes`（宣告沒有人可問，只影響 §2.3 的判斷）。位置：`record` 之後**任何位置**都可以（例 `meeting.sh record --recorder windows`、`meeting.sh record preflight --recorder --window 1`、`meeting.sh record windows --json --yes`）；`meeting.sh` 先依它們做 §2.3 的判斷，再把每個出現處**拿掉**、其餘參數維持原序交給 `record.sh`，`record.sh` 看不到它們（§6 第 28、31 條）。層旗標名不在任何寫法的寫法旗標集合內，所以拿掉它們不會誤拿寫法旗標。
- `SURFACE` 的五個成分（全部由上表與上一條機械導出）：`forms`（12 個寫法，依表順序的 list）、`form_flags`（（寫法，寫法旗標）的集合，本表 3 組）、`form_codes`（（寫法，結束碼）的集合，本表 5＋3＋4＋3＋2＋4＋2×5＋1＝32 組；R2 前為 7 個寫法、22 組，§6 第 77 條）、`layer_flags`（list：`--recorder`、`--yes`）、`codes`（list：0、2、3、4、5）。
- **未知選項**＝`meeting.sh` 先把 `record` 之後任何位置出現的層旗標 `--recorder`、`--yes`（每個出現處）拿掉、其餘參數維持原序交給 `record.sh`；拿掉層旗標之後，仍不屬於該寫法寫法旗標集合（§2.4.2 表第二欄的旗標名）的 `--` 開頭參數，即為未知選項，回通則結束碼 2。判斷範圍：寫法本身的字（含 `help` 同義字 `-h`、`--help`）與寫法旗標之值不參與判斷；只以單一 `-` 開頭的參數不算未知選項，照一般參數處理（§6 第 31 條）。stderr 含「未知的選項」（沿用 `bin/meeting.sh:399` 的字樣）。適用全部寫法（含 `stop`、`help`）。
- `help` 是保留字：要把名為 `help` 的資料夾當根目錄錄製，寫 `meeting record ./help`（§7 疑慮 12）。R2 起 `pause`、`resume`、`mute`、`unmute`、`mark` 同樣是保留字（寫 `meeting record ./pause` 等），這五個寫法的語意與結束碼見檔尾 R2-§2.2（§6 第 77、78 條）。
- `record help` 同樣適用 §2.3 的 `./record` 撞名判斷（D11 的語意不因本輪改變）；所有測試一律在沒有 `record/` 的暫存工作目錄跑。

#### 2.4.3 `meeting.sh record help` 的 stdout 格式（t4 照此實作）

`record help`、`record -h`、`record --help` 三者 stdout 逐位元組相同；不啟動錄製器、不寫任何檔、不讀狀態檔，回 0。stdout 的文法：

1. UTF-8，每行以 `\n` 結尾。**欄位分隔＝兩個以上半形空白**（可多補空白對齊）；欄位內部不得出現連續兩個半形空白。
2. 依序含四個**段頭行**，每行整行（不含 `\n`）恰好等於：`寫法：`、`旗標：`、`meeting.sh 層旗標：`、`結束碼：`（冒號是全形 U+FF1A），各恰好一次、順序固定、行首無空白。
3. **段內容**＝段頭行之後、連續的「以恰好兩個半形空白開頭、第三個字元不是空白」的行；遇到不符合的行（含空行）即結束。段頭行與段內容以外的行（標題、段間空行、結尾說明）不受比對，但不得與段頭行相同。
4. 「寫法：」段：恰好 12 行（R2 前為 7 行）、順序同 §2.4.2；每行恰好兩個欄位：`<寫法>`、`結束碼 <碼> <碼> …`（`結束碼` 後接一個或多個「一個半形空白＋一位數字」），數字＝該寫法的寫法結束碼、遞增。
5. 「旗標：」段：每個（寫法，寫法旗標）恰好一行、順序同 §2.4.2；每行恰好兩個欄位：`<寫法>`、`<寫法旗標>`（含值佔位符，例 `--window <id>`）。沒有寫法旗標的寫法不出現；**層旗標不得出現在這段**。依本表恰好 3 行。
6. 「meeting.sh 層旗標：」段：恰好 2 行、順序 `--recorder`、`--yes`；每行兩個欄位：`<層旗標>`、`<說明>`（說明不比對）。
7. 「結束碼：」段：恰好 5 行、碼依序 0、2、3、4、5；每行兩個欄位：`<碼>`、`<語意>`。語意不機械比對，內容照 §2.2；2 那一行要提到通則的「未知的選項」與 `./record` 撞名。

範例（結構是規範；標題與說明文字只是示意）：

```
meeting record — 錄下會議視窗與雙路音訊（本機）

寫法：
  meeting record [<根>]          結束碼 0 2 3 4 5
  meeting record windows         結束碼 0 2 4
  meeting record preflight       結束碼 0 2 3 4
  meeting record stop            結束碼 0 3 5
  meeting record status          結束碼 0 5
  meeting record finish <場次>   結束碼 0 2 3 5
  meeting record pause           結束碼 0 3
  meeting record resume          結束碼 0 3
  meeting record mute            結束碼 0 3
  meeting record unmute          結束碼 0 3
  meeting record mark            結束碼 0 3
  meeting record help            結束碼 0

旗標：
  meeting record [<根>]          --window <id>
  meeting record windows         --json
  meeting record preflight       --window <id>

meeting.sh 層旗標：
  --recorder  明確要錄製，略過 ./record 撞名檢查
  --yes       宣告沒有人可問（只影響 ./record 撞名判斷）

結束碼：
  0  成功
  2  參數或前提不符；任何寫法遇到未知的選項、或 ./record 撞名而沒有人可問也回 2
  3  找不到目標（視窗、錄製、場次段落）
  4  開錄前檢查的 hard 項失敗（權限、RMS、磁碟）
  5  錄製或收尾出錯，已落盤段落保留（可 meeting record finish）
```

#### 2.4.4 解析規則（三種來源 → 同一組成分）

- `parse_help(text)`：依 §2.4.3 切段與切欄，產出 `forms`（「寫法：」段第 1 欄，依順序）、`form_flags`（「旗標：」段每行的（第 1 欄，第 2 欄））、`form_codes`（「寫法：」段每行的（第 1 欄，第 2 欄 `結束碼` 之後的每個數字））、`layer_flags`（「meeting.sh 層旗標：」段第 1 欄，依順序）、`codes`（「結束碼：」段第 1 欄轉整數，依順序）。任何一條文法不符（段頭缺漏、重複或順序錯，欄位數不對，`結束碼` 欄格式錯，「旗標：」段第 1 欄不在 `forms` 內）→ 解析失敗，以「行號＋該行內容」報錯。
- `parse_block(text)`：取 `<!-- record-cli:begin -->` 與 `<!-- record-cli:end -->` 之間的 markdown 表（格式見 §2.4.5），產出 `forms`、`form_flags`、`form_codes` 三項（區塊不含層旗標與 `codes`）。每格先刪除所有反引號再去前後空白。
- `parse_usage(text)`：見 §2.4.6，產出 `forms`。
- **比對一律是相等**：`forms`、`layer_flags`、`codes` 比 list（順序也要相同），`form_flags`、`form_codes` 比集合；不等就失敗，失敗訊息列出兩邊的差集（「多出」「缺少」）。

#### 2.4.5 文件的機械可讀區塊（t5 照此撰寫）

SKILL.md 與 README.md 各含**恰好一個** `<!-- record-cli:begin -->` 行與**恰好一個** `<!-- record-cli:end -->` 行，兩行之間只有一張 markdown 表：

- 表頭行恰好是 `| 寫法 | 旗標 | 結束碼 |`，下一行是 `|---|---|---|`，接著恰好 12 列（R2 前為 7 列），順序同 §2.4.2；
- 「寫法」格＝寫法（可包反引號）；「旗標」格＝該寫法的寫法旗標以「、」分隔（每個旗標可各自包反引號），沒有就寫 `—`（U+2014）；「結束碼」格＝寫法結束碼，以一個半形空白分隔、遞增；
- 層旗標**不放進區塊**；兩份文件都要在區塊外提到 `--recorder` 與 `--yes`（§4.12.6）；
- 兩份文件 begin 行與 end 行之間的內容逐位元組相同。

區塊外的說明文字不做集合比對，但受 §4.12.6 的逐行規則約束。

#### 2.4.6 `meeting.sh help`（`usage()`）的 record 段（t4 照此實作）

`usage()` 在「其他指令」段之後新增一段，結構固定：

1. 段頭一行，整行恰好等於 `錄製（meeting record；完整說明：meeting record help）`，行首無空白；
2. 緊接 12 行（R2 前為 7 行），順序同 §2.4.2，每行 `  <寫法>` 後接兩個以上半形空白與說明（兩個空白開頭；寫法後**不得**接旗標）；
3. 接 1 行以 `  層旗標：` 開頭，該行含 `--recorder` 與 `--yes`；
4. 接 1 行以 `  結束碼：` 開頭，該行依序含子字串 `0 `、`2 `、`3 `、`4 `、`5 `（數字後一個半形空白再接語意）；
5. 之後接一個空行。

`parse_usage(text)`：整份輸出中凡符合正規式 `^  meeting record( |$)` 的行，去掉行首兩個空白、取到第一個「兩個以上半形空白」之前（沒有就取到行尾）的字串，依出現順序組成 `forms`。`usage()` 的其他段不得出現以 `  meeting record` 開頭的行。

#### 2.4.7 執行用的參數組法（§4.1.4、§4.12.8 共用；`surface.form_argv`）

- 寫法 → argv：開頭的 `meeting` 換成 `bin/meeting.sh` 的絕對路徑（以 `bash` 執行）；`[<根>]` → 測試建立的暫存根目錄絕對路徑；`<場次>` → 暫存場次目錄絕對路徑；其他字原樣。
- 寫法旗標 → 加在寫法最後一個字之後：`--window <id>` → `--window`、`1`；`--json` → `--json`。
- 層旗標 → 預設插在 `record` 之後、其餘字之前（§4.12.8 (a) 用這個組法）。層旗標在中間或結尾的位置案例不經 `form_argv`，由 §4.1.12 的兩支測試直接寫死 argv。表外旗標固定用 `--no-such-flag`，加在最後。
- 執行環境：cwd＝沒有 `record/` 的暫存目錄；`MH_RECORD_OPEN`＝`tests/record/fakes/fake_open.sh`；`MH_RECORD_HOME`＝暫存目錄；情境沒指定時 `FAKE_SCENARIO=recording`；stdin＝`/dev/null`。
- `EXIT_CODE_CASES`（定義在 `tests/record/test_record_sh.py` 模組層，`test_exit_code_matrix` 與 `test_docs_exit_codes_match_behavior` 共用）：list，每筆是 dict，鍵恰好為 `form`（§2.4.2 的寫法字串，逐字）、`scenario`（`FAKE_SCENARIO` 值或 `None`）、`setup`（前置條件代號字串，由 `test_record_sh.py` 解讀，例 `app_missing`、`root_missing`、`session_no_segments`）、`extra_args`（list，只能含該寫法的寫法旗標名與其值）、`expect`（整數）。限制：`extra_args` 不得含表外旗標或層旗標；`setup` 不得在 cwd 建 `record/`；`{(form, expect)}` 必須**等於** `SURFACE.form_codes`（32 組，不多不少；R2 前為 22 組）。R2 五個寫法的 `setup` 代號與替身情境見檔尾 §4.16.5、§4.16.6。

#### 2.4.8 `tests/record/surface.py`（t1 照此實作）

模組層常數 `SURFACE`（§2.4.2 的五個成分，逐字抄本節，不從其他檔讀）與函式 `parse_help(text)`、`parse_block(text)`、`parse_usage(text)`、`form_argv(form, *, root, session, form_flag=None, layer_flag=None, extra=None)`，行為依 §2.4.3–2.4.7。檔名不以 `test` 開頭，`unittest discover` 不會把它當測試模組。解析器本身的正確性由 `tests/record/test_surface_parsers.py` 驗（spec §2.4.3 範例原樣餵入 `parse_help` 應得到等於 `SURFACE` 的五個成分；每一條文法違規各一例應報錯；`parse_block`、`parse_usage`、`form_argv` 各以合法樣本驗），紅燈階段就要綠——t4、t5 都對著這些解析器轉綠，解析器錯了兩邊會一起卡住。

---

## 3. 資料契約

### 3.1 `~/.meeting-harness/record.status.json`
欄位依 `design.md §3.2`，`schemaVersion=1`；Swift 型別見 §3.4 `RecordStatus`。寫入一律 tmp＋rename。

### 3.2 `錄音/tracks/manifest.json`
```json
{ "schemaVersion": 1, "segmentSeconds": 60,
  "segments": [ { "file": "seg-0001.mov", "requestedAt": 0.000, "startedAt": 0.012, "finishedAt": 60.031,
                  "width": 2992, "height": 1876, "audioDuration": 60.010 } ],
  "frameStatus": { "complete": 0, "idle": 0, "blank": 0, "suspended": 0, "started": 0, "stopped": 0 },
  "blackIntervals": [ { "start": 860.0, "end": 1085.0 } ],
  "levels": { "windowSeconds": 0.5, "system": [-23.1, null], "mic": [-41.0, -38.2] },
  "gapStats": { "boundaries": [0.021], "max": 0.021, "total": 0.021, "wallClock": 180.4 },
  "outputCanvas": { "width": 2992, "height": 1876 }, "outputVideoBitrate": 11605500 }
```
時間一律是自錄製開始起算的秒數（小數 3 位）。`levels` 每個元素是一個 0.5 秒時段的峰值 dBFS（小數 1 位），`null`＝-∞ 或該時段沒有緩衝（`design.md §7.5`）。錄製器寫 `segments` 的前六欄、`frameStatus`、`blackIntervals`、`levels`；finalize 填各段 `audioDuration`、`gapStats`、`outputCanvas`、`outputVideoBitrate`，並保留其他鍵不動。

**`segments[i]` 時間欄位的定義（D20 改寫；欄位名稱、型別、`SegmentRecord` 都不變）**。「sample 時鐘」＝SCK sample 的 PTS（與 host clock 同一個時鐘），換成秒數一律減 `t0`（`startCapture` 前一刻的 host clock）；`B_i`＝第 i 段 writer 的 `startSession(atSourceTime:)`（`design.md §7.2`）：

| 欄位 | 定義 | 誰寫、何時 |
|---|---|---|
| `requestedAt` | 錄製器**決定**開第 i 段的時刻（host clock − `t0`）：第 1 段為 0；之後＝第一個 PTS ≥ 邊界的 sample 到達的時刻（定期換段），或偵測到格式變更／writer 失敗而提前換段的時刻 | 錄製器，開段時 |
| `startedAt` | 該段的呈現起點＝`B_i − t0`（sample 時鐘）；定期換段時 `startedAt_{i+1} = startedAt_i + 60.000` | 錄製器，開段時（不再等任何回呼，所以不會是 `null`） |
| `finishedAt` | 該段 writer 的 `finishWriting` 完成且 `status == .completed` 的時刻（host clock − `t0`）；writer 失敗、收尾逾時、或當機時為 `null` | 錄製器，收尾完成回呼裡 |
| `audioDuration` | 該段**各音軌**長度的最大值（秒，小數 3 位）；長度一律由封包算（最後一個可解碼封包的 `pts_time + duration_time` − min(該軌 stream 層 `start_time`, 第一個可解碼封包的 `pts_time`)；「可解碼」＝略過 `flags` 含 `D` 或 `C` 的封包），不採 stream／format 層的 `duration`（中斷的 fragment 檔會高報，`§4.6.15`）。**t6 第二輪**：`e2e_check.py` 的 `gap` 判準必須用這個同一算法量（前一版用 stream 層 `duration`，與 finalize 寫回的 `gapStats` 不一致，實機場次重新收尾後 `gap` 會因「與實測不符」誤判 FAIL，`design.md §7.4` 缺陷 F2；§4.6.19） | finalize |

D20 之前（`SCRecordingOutput`）的段落仍可能出現在 t6 期間錄下的場次裡：那些段落的 `startedAt`／`finishedAt` 依舊定義（`recordingOutputDidStart／DidFinishRecording` 回呼），finalize 與 `e2e_check.py` 不得因欄位為 `null` 而失敗（照現行行為略過該邊界的空隙計算）。

### 3.3 `錄音/tracks/record.meta.json`
```json
{ "schemaVersion": 1,
  "window": { "windowID": 0, "app": "", "bundleID": "", "title": "" },
  "config": { "filter": "desktopIndependentWindow", "onScreenWindowsOnly": false, "scalesToFit": true,
              "minimumFrameInterval": "1/60", "capturesAudio": true, "sampleRate": 48000, "channelCount": 2,
              "captureMicrophone": true, "microphoneCaptureDeviceID": null,
              "excludesCurrentProcessAudio": true, "fileType": "mov", "videoCodec": "h264", "segmentSeconds": 60 },
  "devices": { "input":  { "uid": "", "name": "", "transport": "builtIn" },
               "output": { "uid": "", "name": "", "transport": "bluetooth" } },
  "preflight": [ { "item": "screen_permission", "ok": true, "severity": "hard", "code": 0, "message": "" } ],
  "deviceEvents": [ { "t": 61.2, "kind": "input",
                      "from": { "uid": "", "name": "", "transport": "builtIn" },
                      "to":   { "uid": "", "name": "", "transport": "bluetooth" } } ],
  "audioFormatEvents": [ { "t": 61.4, "source": "system",
                           "from": { "sampleRate": 48000, "channels": 2, "interleaved": false, "sampleType": "float32" },
                           "to":   { "sampleRate": 16000, "channels": 1, "interleaved": false, "sampleType": "float32" } } ] }
```
原本的 `canvas` 欄位移除：畫布改為每段各自的 `manifest.json.segments[i].width／height`（D8）。`transport` 取值：`builtIn`、`bluetooth`、`bluetoothLE`、`usb`、`aggregate`、`virtual`、`unknown`。

### 3.4 Swift `Core/` 對外名稱（test 子任務依此寫紅燈測試，build 段不得改名）

本節是 `Core/` 的**唯一**契約（`design.md §9` 只列檔案歸屬）。標「預設值」的參數可省略；其餘參數呼叫端必須明寫（例如 `PeakWindow(windowSeconds: 0.5)`，0.5 是正式值、不是預設值）。所有型別與函式皆為 `public` 以外的 module 內部可見即可（測試與 Core 同一次 `swiftc` 編譯）。

```swift
// ===== AudioLevel.swift =====
enum SampleType: String, Codable { case float32, int16 }
struct AudioFormat: Equatable, Codable {
    let sampleRate: Double; let channels: Int; let interleaved: Bool; let sampleType: SampleType
}
func audioFormat(of sampleBuffer: CMSampleBuffer) -> AudioFormat?        // 讀 ASBD；非 PCM 或不支援的樣本型別回 nil
func rmsDBFS(samples: [Float]) -> Double                                  // 空陣列或全零回 -.infinity
func rmsDBFS(sampleBuffer: CMSampleBuffer) -> Double?                     // 依該緩衝自己的格式（任意取樣率、聲道數、交錯與否、Float32／Int16）
                                                                          // 對全部聲道與 frame 算均方根；經 withAudioBufferList 取緩衝；不支援的格式回 nil
struct PeakWindow {
    init(windowSeconds: Double)
    mutating func feed(t: Double, dbfs: Double)                           // t＝PTS 秒；與取樣率無關
    mutating func close(upTo t: Double) -> [Double]                       // 回傳結束時間 ≤ t 的各時段峰值（依時間順序）；沒收到任何 feed 的時段為 -.infinity
    var maxDBFS: Double { get }                                           // 至今已 feed 的最大值；未 feed 過為 -.infinity
}

// ===== Detectors.swift =====
struct SilenceDetector {
    init(thresholdDBFS: Double, seconds: Double)                          // 正式值 -60、15
    mutating func feed(t: Double, dbfs: Double) -> Bool                   // 本次是否「新觸發」告警；同一段只回一次 true；dbfs ≥ 門檻即重置
}
struct BlackInterval: Codable, Equatable { var start: Double; var end: Double? }   // end 為 nil＝尚未恢復
struct BlackDetector {
    init(ratio: Double, seconds: Double)                                  // 正式值 0.01、5
    mutating func feed(t: Double, nonBlackRatio: Double) -> Bool          // 本次是否新開一個區間；start＝該段連續低於門檻的第一個樣本時間；end＝恢復的第一個樣本時間
    var intervals: [BlackInterval] { get }
}
enum FrameStatusKind: String, Codable { case complete, idle, blank, suspended, started, stopped }
struct SuspendedDetector {
    init(seconds: Double)                                                 // 正式值 5
    mutating func feed(t: Double, status: FrameStatusKind) -> Bool        // 連續 seconds 秒只收到 suspended 時回一次 true；收到其他狀態即重置
}
func nonBlackRatio(lumaPlane: UnsafeBufferPointer<UInt8>, width: Int, height: Int, bytesPerRow: Int) -> Double?
                                                                          // 沿用 main.swift:238-265 的判定：8×8 格點中心共 64 點、亮度 > 24 的比例；寬或高 ≤ 16 回 nil
                                                                          // （CVPixelBuffer 的鎖定與取 plane 0 留在 Capture/，Core 只吃位元組，方便測試）

// ===== Preflight.swift =====
enum PreflightItem: String, CaseIterable, Codable {
    case signing, screen_permission, relaunch_needed, mic_permission, system_audio_rms, mic_rms,
         disk, window_exists, session_collision, power, already_running, window_minimized,
         apple_events                                                     // 第 13 項（D16，warn）：Chrome 分頁標記用的 Apple Events 狀態，§3.8.4
}
enum Severity: String, Codable { case hard, warn }
func severity(of item: PreflightItem) -> Severity
func failCode(of item: PreflightItem) -> Int32                            // warn 項回 0
func stageManagerNotice(globallyEnabled: Bool?) -> String?                // t6 第三輪（發現 I，§4.2.12）：true → 幕前調度提醒（含「幕前調度」「縮圖」「目前舞台」）；false／nil → nil
struct PreflightResult: Codable, Equatable {
    let item: PreflightItem; let ok: Bool; let message: String
    let warnOnly: Bool                                                    // D19：第 5 項兩段式 (b) 有聲時，該筆結果降為 warn（§4.2.5、§4.2.9）
    init(item: PreflightItem, ok: Bool, message: String = "", warnOnly: Bool = false)
                                                                          // warnOnly 只在 item == .system_audio_rms 且 ok == false 時存成 true；其他情形一律存成 false
    var severity: Severity { get }                                        // warnOnly == true → .warn；否則＝severity(of: item)
    var code: Int32 { get }                                               // ok 或 severity == .warn 為 0；hard 失敗為 failCode(of: item)
    // JSON 鍵固定為 item、ok、severity、code、message（不另加鍵，warnOnly 以 severity 表達；encode 時寫出 computed 的 severity 與 code）。
    // decode 時忽略 code；severity 也一律忽略、以 item 重算，唯一例外：item == system_audio_rms、ok == false 且 severity == "warn" → warnOnly = true
}
func exitCode(for results: [PreflightResult]) -> Int32                    // 沒有 hard 失敗（ok == false 且 severity == .hard）回 0；否則取 4＞3＞2
enum SystemAudioCheck: String, Codable, Equatable { case pass, warnTargetSilent = "warn_target_silent", fail }
func systemAudioCheck(targetPeakDBFS: Double, displayPeakDBFS: Double?, thresholdDBFS: Double) -> SystemAudioCheck
                                                                          // D19，§4.2.5、§4.2.9；正式值 thresholdDBFS = -60（呼叫端明寫），比較一律「嚴格大於」
                                                                          // targetPeak > 門檻 → .pass（不看 displayPeak）；否則 displayPeak > 門檻 → .warnTargetSilent；
                                                                          // displayPeak 為 nil（(b) 沒跑成）或 ≤ 門檻 → .fail；NaN 視同 -.infinity

// ===== Records.swift =====
enum RecordPhase: String, Codable {
    case preflight, preflightFailed = "preflight_failed", recording, stopping, finalizing, done, failed
}
enum WarningKind: String, Codable {
    case silenceSystem = "silence_system", silenceMic = "silence_mic", black, suspended,
         diskLow = "disk_low", deviceChange = "device_change", audioFormatChange = "audio_format_change",
         segmentWriteFailed = "segment_write_failed"                     // D20：段落 writer 失敗（design §7.2〈writer 失敗〉）
    var isAlert: Bool { get }                                             // silenceSystem、silenceMic、black、suspended、diskLow、segmentWriteFailed 為 true（告警類）；
                                                                          // deviceChange、audioFormatChange 為 false（紀錄類）
}
struct RecordWarning: Codable, Equatable { let t: Double; let kind: WarningKind; let message: String }
struct RecordStatus: Codable, Equatable {
    var schemaVersion: Int; var runId: String; var pid: Int32; var phase: RecordPhase; var code: Int32
    var message: String; var session: String; var startedAt: String; var updatedAt: String
    var segments: Int; var preflight: [PreflightResult]; var warnings: [RecordWarning]
}
struct SegmentRecord: Codable, Equatable {
    var file: String; var requestedAt: Double; var startedAt: Double?; var finishedAt: Double?
    var width: Int; var height: Int; var audioDuration: Double?
}
struct FrameStatusCounts: Codable, Equatable { var complete, idle, blank, suspended, started, stopped: Int }
struct AudioLevels: Codable, Equatable { var windowSeconds: Double; var system: [Double?]; var mic: [Double?] }
struct GapStats: Codable, Equatable { var boundaries: [Double]; var max: Double; var total: Double; var wallClock: Double }
struct PixelSize: Codable, Equatable { var width: Int; var height: Int }
struct Manifest: Codable, Equatable {
    var schemaVersion: Int; var segmentSeconds: Int; var segments: [SegmentRecord]
    var frameStatus: FrameStatusCounts; var blackIntervals: [BlackInterval]; var levels: AudioLevels
    var gapStats: GapStats?; var outputCanvas: PixelSize?; var outputVideoBitrate: Int?
}
struct WindowInfo: Codable, Equatable { var windowID: UInt32; var app: String; var bundleID: String; var title: String }
struct StreamConfigSnapshot: Codable, Equatable {
    var filter: String; var onScreenWindowsOnly: Bool; var scalesToFit: Bool; var minimumFrameInterval: String
    var capturesAudio: Bool; var sampleRate: Int; var channelCount: Int; var captureMicrophone: Bool
    var microphoneCaptureDeviceID: String?; var excludesCurrentProcessAudio: Bool
    var fileType: String; var videoCodec: String; var segmentSeconds: Int
}
struct AudioDeviceInfo: Codable, Equatable { var uid: String; var name: String; var transport: String }
struct AudioDevices: Codable, Equatable { var input: AudioDeviceInfo?; var output: AudioDeviceInfo? }
enum DeviceKind: String, Codable { case input, output }
struct DeviceEvent: Codable, Equatable { var t: Double; var kind: DeviceKind; var from: AudioDeviceInfo?; var to: AudioDeviceInfo? }
enum AudioSource: String, Codable { case system, mic }
struct AudioFormatEvent: Codable, Equatable { var t: Double; var source: AudioSource; var from: AudioFormat?; var to: AudioFormat }
struct RecordMeta: Codable, Equatable {
    var schemaVersion: Int; var window: WindowInfo; var config: StreamConfigSnapshot; var devices: AudioDevices
    var preflight: [PreflightResult]; var deviceEvents: [DeviceEvent]; var audioFormatEvents: [AudioFormatEvent]
}
struct CompletionOutcome: Equatable { let phase: RecordPhase; let code: Int32; let message: String }
func completionOutcome(finalizeCode: Int32, forcedCode: Int32?, forcedMessage: String?, hadError: Bool,
                       sessionPath: String) -> CompletionOutcome
                                                                          // t6 第二輪（缺陷 D，§4.4.9）：錄製結束時寫進 record.status.json 與 record.log 的最終結果
                                                                          // finalizeCode != 0 → (.failed, 5, 前綴 + "收尾失敗（_record_finalize.py 回 <rc>），段落保留：可執行 meeting record finish <sessionPath>")；
                                                                          //   前綴＝forcedMessage 非 nil 時為 forcedMessage + "；"，否則為 ""（停止原因不得被收尾失敗蓋掉）
                                                                          // 否則 forcedMessage 非 nil → (.done, forcedCode ?? 5, forcedMessage)
                                                                          // 否則 hadError → (.done, 5, "錄製中出過錯（見 record.log），已收尾；段落保留")
                                                                          // 否則 → (.done, 0, "已完成：<sessionPath>")
func writeJSONAtomically<T: Encodable>(_ value: T, to url: URL) throws    // 同目錄 tmp 檔＋rename；鍵排序（.sortedKeys）；Optional 為 nil 時寫 null
// 各型別編碼後的 JSON 鍵名＝Swift 屬性名（不做 snake_case 轉換），必須與 §3.1–§3.3 的範例一致

// ===== Segments.swift =====
func segmentFileName(index: Int) -> String                               // index 從 1 起；1 → "seg-0001.mov"
func boundaryGaps(startedAt: [Double], audioDurations: [Double]) -> [Double]
                                                                          // 兩陣列等長 n；回傳 n-1 個 g_i = startedAt[i+1] - startedAt[i] - audioDurations[i]；n < 2 回 []
func evenPixelSize(points: CGSize, scale: Double) -> PixelSize            // 各邊 point×scale 後向下取偶數；結果至少 2×2
func nextSegmentSize(windowPoints: CGSize?, scale: Double, previous: PixelSize) -> PixelSize
                                                                          // t6 第二輪（缺陷 A，§4.3.6）：換段當下同步讀到的視窗大小（point）決定新段尺寸
                                                                          // windowPoints 為 nil、寬或高 ≤ 0、或任一邊非有限值 → previous（讀不到沿用上一段）；
                                                                          // 否則 evenPixelSize(points: windowPoints, scale: scale)（讀到新尺寸就套用，與 previous 相同也照回）
enum SampleRoute: Equatable { case old, new, both }                       // D20：換段時 sample 的去向（design §7.2 換段第 4 步）
func routeSample(start: Double, end: Double, boundary: Double) -> SampleRoute
                                                                          // 單位秒（sample 時鐘）；呼叫端保證 end ≥ start；視訊 sample 以 end == start 呼叫
                                                                          // 判定順序（t6 第二輪更正，與 §4.4.6、design §7.2 一致）：start ≥ boundary → .new；
                                                                          // 否則 end ≤ boundary → .old；否則（start < boundary < end）→ .both
                                                                          // （前一版註解先判 end ≤ boundary，與 §4.4.6 的 (60.0, 60.0, 60) → .new 矛盾）
func segmentVideoBitRate(width: Int, height: Int) -> Int                 // D20：width × height × 5 / 4（整數運算），再夾在 [4_000_000, 10_000_000]；2992×1876 → 7_016_240
func shouldEmitVideoHeartbeat(samplePTS: Double, lastVideoPTS: Double?, hasLastFrame: Bool, interval: Double) -> Bool
                                                                          // t6 第二輪（缺陷 E／D22，§4.4.10）：收到 idle 的 .screen sample 時，是否重送最後一幀
                                                                          // hasLastFrame == false、lastVideoPTS 為 nil、或任一時間非有限值 → false；
                                                                          // 否則 samplePTS − lastVideoPTS ≥ interval → true（正式值 interval = 1.0，呼叫端明寫；單位秒，sample 時鐘）

// ===== Trigger.swift =====
enum MenuBarState: String, Equatable { case idle, recording, warning }
struct MenuBarModel: Equatable {
    let state: MenuBarState
    let symbolName: String                                                // idle "record.circle"；recording "record.circle.fill"；warning "exclamationmark.triangle.fill"
    let statusLine: String                                                // 選單第一行（狀態列）的完整文字；toolTip／accessibilityLabel 用 accessibilityText（§4.11.8）
    let canStart: Bool; let canStop: Bool; let canOpenSession: Bool
}
extension MenuBarModel {
    var accessibilityText: String { get }                                 // state == .idle → statusLine；其餘 → "MeetingRecorder：" + statusLine（D18，§4.11.8）
}
func menuBarModel(status: RecordStatus?, pidAlive: Bool, now: Date) -> MenuBarModel   // 對映規則見 §3.4.1（本檔，唯一正本）
func truncatedStatusTitle(_ line: String, limit: Int) -> String           // 以 Character 計；line.count <= limit 原樣回傳；否則回傳前 limit-1 個字＋「…」（共 limit 個字）
                                                                          // 正式值 limit = 40（呼叫端明寫）；limit < 2 視為 2（D18，§4.11.8）
enum MenuBarLockResult: Equatable { case acquired(fd: Int32), heldByOther, unavailable(errno: Int32) }
func acquireMenuBarLock(at lockURL: URL) -> MenuBarLockResult             // 上層目錄不存在先建；open(O_CREAT|O_RDWR, 0600) 後 flock(LOCK_EX|LOCK_NB)
                                                                          // 成功 → .acquired(fd)（呼叫端持有到 process 結束，不得 close）；EWOULDBLOCK → .heldByOther（fd 先 close）
                                                                          // open／mkdir／其他 flock 錯誤 → .unavailable(errno)（D18，§4.11.10）
enum QuickStartDecision: Equatable { case start(windowID: UInt32), fail(code: Int32, message: String) }
func quickStartDecision(hasDefaults: Bool, starredWindowIDs: [UInt32]) -> QuickStartDecision
                                                                          // 沒有預設值 → fail(2)；★ 視窗不是恰好一個 → fail(3)；否則 start
                                                                          // starredWindowIDs＝buildWindowRows(...) 中 meeting != nil 的列（§3.8.2）

// ===== WindowList.swift =====（D15、D16；行為規則只寫在 §3.8）
struct WindowCandidate: Equatable {
    var windowID: UInt32; var app: String; var bundleID: String; var title: String   // 無標題為 ""
    var layer: Int; var frame: CGRect                                                  // SCWindow.windowLayer、SCWindow.frame（point）
    var onScreen: Bool; var active: Bool                                               // SCWindow.isOnScreen、SCWindow.isActive
}
enum ExclusionReason: String, Codable { case layer, size }
func exclusionReasons(_ w: WindowCandidate) -> [ExclusionReason]          // §3.8.1；依 layer、size 的順序列出；空陣列＝納入；標題不參與
func isFullScreenSized(frame: CGRect, displays: [CGRect]) -> Bool         // §3.8.6
func meetingService(url: String) -> String?                               // §3.8.2 網址表；不符回 nil
func meetingAppService(bundleID: String) -> String?                       // §3.8.2 原生 app 表；不符回 nil（com.google.Chrome、com.apple.Safari 回 nil）
let chromeBundleID: String                                                // ＝"com.google.Chrome"
struct ChromeWindowInfo: Equatable { var title: String; var bounds: CGRect; var activeTabURL: String; var tabURLs: [String] }
enum ChromeMatch: Equatable { case matched(index: Int), unmatched, ambiguous }   // index＝chrome 陣列索引
func matchChromeWindow(title: String, frame: CGRect, in chrome: [ChromeWindowInfo]) -> ChromeMatch   // §3.8.3
enum AutomationStatus: String, Codable {
    case authorized, notAuthorized = "not_authorized", notDetermined = "not_determined",
         chromeNotRunning = "chrome_not_running", error
}
func automationStatus(fromOSStatus status: Int32) -> AutomationStatus     // §3.8.4：0／-1743／-1744／-600／其他
struct MeetingMark: Codable, Equatable { var service: String; var source: String }   // source："url"｜"app"
struct WindowListRow: Codable, Equatable {
    var windowID: UInt32; var app: String; var bundleID: String; var title: String; var untitled: Bool
    var width: Int; var height: Int; var onScreen: Bool; var active: Bool; var fullScreenSized: Bool
    var isMeetingApp: Bool; var meeting: MeetingMark?; var meetingTabInactive: Bool; var meetingCheck: String?
    var label: String
    // JSON 鍵恰為上列 15 個；meeting、meetingCheck 為 nil 時寫 null（不得省略鍵）；isMeetingApp ＝ meeting != nil
}
func buildWindowRows(candidates: [WindowCandidate], displays: [CGRect],
                     chrome: [ChromeWindowInfo], automation: AutomationStatus) -> [WindowListRow]
                                                                          // §3.8.1 篩選＋§3.8.2 標記＋§3.8.5 排序＋§3.8.6 label；automation != .authorized 時忽略 chrome
func windowRowLabel(_ row: WindowListRow) -> String                       // §3.8.6；buildWindowRows 的 label 欄即此值
struct DiagnosedWindow: Codable, Equatable {
    var row: WindowListRow; var layer: Int; var x: Int; var y: Int; var excludedBy: [ExclusionReason]
}
func diagnoseWindows(candidates: [WindowCandidate], displays: [CGRect],
                     chrome: [ChromeWindowInfo], automation: AutomationStatus) -> [DiagnosedWindow]
                                                                          // §3.8.9；每個 candidate 一筆（含被濾掉的），順序＝輸入順序
struct WindowRef: Equatable { var windowID: UInt32; var bundleID: String?; var title: String? }
enum WindowResolution: Equatable { case exact(UInt32), reidentified(UInt32), notFound, ambiguous }
func resolveWindow(_ ref: WindowRef, in candidates: [WindowCandidate]) -> WindowResolution   // §3.8.8
```

#### 3.4.1 `menuBarModel` 對映表（第二輪 skeptic 問題 3）

由上而下取**第一個**成立的列。M6a 是 D17 在 M6 與 M7 之間插入的列；列名不重新編號，既有引用的 M1–M10 意義不變，「全表」＝M1–M10 加 M6a 共 11 列。記號：「進行中」＝`phase ∈ {preflight, recording, stopping, finalizing}`；「告警類」＝`warnings` 中 `kind.isAlert == true` 的項；「最新告警」＝告警類中 `t` 最大的一筆；「場次名」＝`session` 的最後一段路徑；「經過時間」＝`now − startedAt`，格式 `mm:ss`（≥ 60 分鐘時 `h:mm:ss`）；「訊息首行」＝`message` 第一個換行前的文字；「告警數」＝告警類的項數（不去重，`N ≥ 1`）。`symbolName` 一律由 `state` 決定（idle `record.circle`、recording `record.circle.fill`、warning `exclamationmark.triangle.fill`）。

| 列 | 條件 | `state` | `statusLine` 必須包含 | `canStart` | `canStop` | `canOpenSession` |
|---|---|---|---|---|---|---|
| M1 | `status == nil` | idle | 「待機」 | true | false | false |
| M2 | `phase == preflight_failed`（不論 `code`；契約上必為 2／3／4） | **warning** | 「開錄前檢查沒通過」＋訊息首行 | true | false | false |
| M3 | `phase == failed` | warning | 「錄製失敗」＋訊息首行 | true | false | true |
| M4 | `phase == done` 且 `code != 0` | warning | 「錄製失敗」＋訊息首行 | true | false | true |
| M5 | `phase == done` 且 `code == 0` | idle | 「待機」 | true | false | true |
| M6 | 進行中且 `pidAlive == false` | warning | 「異常中止」＋「meeting record finish」 | true | false | true |
| M6a | `phase ∈ {stopping, finalizing}`、`pidAlive == true`、有告警類（D17） | recording | 「收尾中…」＋「（告警 N 則）」，N＝告警數，例「收尾中…（告警 2 則）」 | false | false | true |
| M7 | 進行中、`pidAlive == true`、有告警類 | warning | 最新告警的 `message` | false | `phase == recording` | true |
| M8 | `phase == preflight`、`pidAlive == true`、無告警類 | recording | 「開錄前檢查中」 | false | false | true |
| M9 | `phase == recording`、`pidAlive == true`、無告警類 | recording | 「錄製中」＋經過時間＋場次名 | false | true | true |
| M10 | `phase ∈ {stopping, finalizing}`、`pidAlive == true`、無告警類 | recording | 「收尾中…」 | false | false | true |

- 每一列的 `statusLine` 都不得含 `WarningKind` 的 raw value（例如 `silence_mic`）與 `RecordPhase` 的 raw value（例如 `preflight_failed`）（§4.11.8）。
- 紀錄類 warning（`device_change`、`audio_format_change`）不影響本表（M6a、M7 只看告警類；只有紀錄類 warning 的 stopping／finalizing 走 M10）。
- M6a 先於 M7，所以 M7 實際只會在 `phase ∈ {preflight, recording}` 成立；M7 的 `canStop` 欄維持原寫法，值不變。
- `testMenuBarStateMapping` 應對全表 11 列（M1–M10 與 M6a）每列至少一個案例，其中 M2 應涵蓋 `code` 為 2、3、4 三種、M6a 應涵蓋 stopping 與 finalizing 兩種且至少一案 N ≥ 2；`testStopAvailabilityByPhase`、`testMenuItemAvailability` 以本表的 `canStop`／`canStart`／`canOpenSession` 欄為準。

### 3.5 `record.sh` → app 的參數
`windows [--json] [--ask-automation] --log <檔>`／`preflight --window <id> [--window-bundle <bundleID> --window-title <標題>] --session <dir> --min-free-bytes <n> --run-id <uuid> --home <dir>`／`start`（同 preflight 的參數 ＋ `--harness <dir>`；start 先跑 preflight）／`quick-start`／`menubar`／`diagnose-windows [--json] --log <檔>`（D15，§3.8.9）／`probe …`（第 0 階段，保留）。

- `--ask-automation`：只有 `record.sh` 在 stdin 與 stderr 都是 tty 時才加（判斷方式同 §2.3）；有它時 `windows` 才會讓系統跳出「允許控制 Google Chrome」的授權框（§3.8.4）。`record.sh` 帶它時等 `windows` 輸出的上限至少 120 秒（使用者要讀授權框），沒帶時照原本的等待上限。
- `--window-bundle`、`--window-title`：`record.sh` 從 `_record_prompt.py` 的輸出（§3.7）取得後一併傳給 app，供 §3.8.8 的視窗認回；兩者要嘛都給、要嘛都不給（`--window-title` 可為空字串，代表無標題視窗）。使用者自己打的 `meeting record preflight --window <id>` 不帶這兩個參數，此時只認 windowID。
- `menubar` 是單一實例：已有 menubar 實例持有 `<home>/menubar.lock` 時，新實例立即結束（結束碼 0），其他模式不受影響（§4.11.10）。
- 這三個參數與 `diagnose-windows` 都只在 app 的 `--args` 層，**不是** `meeting record` 的寫法旗標，不進 §2.4 的封閉清單。

### 3.6 `錄音/meeting.json`
key 集合＝`bin/_scaffold.py:107-110` 寫入的 7 個：`type`、`date`、`attendees`、`expectedSpeakers`、`language`、`llm`、`_note`。`expectedSpeakers` 固定 `null`；`_note` 用錄製器專用文字，不得出現「鎖定人數」之意。

### 3.7 `bin/_record_prompt.py` 與 `bin/_record_estimate.py` 的介面
- `_record_prompt.py --windows-json <檔> --defaults <檔>`：問答提示一律印到 stderr；最後在 stdout 印**一行** JSON：`{"root","session","type","attendees","windowID","bundleID","title"}`（後兩鍵為第六修正輪新增，值取自所選那一列的同名欄位，供 §3.8.8 認回）；任何情況都不寫檔。使用者中斷（EOF／Ctrl-C）回 2。
- 視窗選單（D16）：依 `--windows-json` 陣列的原順序（已由 app 依 §3.8.5 排好）每列印 `<序號>) <label>`（`label` 逐字照印，不自行組字）；**預設＝第一個 `meeting` 非 null 的列**，提示寫成「[預設 <序號>]」，直接按 Enter 即選它；沒有任何 `meeting` 非 null 的列時**沒有預設**，空白輸入要重問，不得自行選第一列。有任何一列 `meetingCheck` 是 `not_authorized` 或 `not_determined` 時，選單後多印一行說明：Chrome 視窗沒有會議標記是因為沒有允許 MeetingRecorder 控制 Chrome（選用；系統設定 › 隱私權與安全性 › 自動化），不允許也能錄。
- `_record_estimate.py --minutes <N>`：stdout 印一個整數＝`ceil(N × (4 × 56,000,000 ＋ 1,920,000)) ＋ 2,000,000,000`（bytes，公式依據 `design.md §5 Q7`）；`--human` 另印「約 X.X GB」；`N` 不是正數回 2。

### 3.8 視窗清單（`windows`、`diagnose-windows`、`quick-start`、`menubar` 共用；D15、D16）

本節是錄製器視窗清單的**唯一**契約（第六修正輪補進；前一版 spec 沒有定義篩選與 ★，行為只存在於第 0 階段原型 `tools/MeetingRecorder/Sources/main.swift:106-133`）。判斷全部是 `Core/WindowList.swift` 的純函式（§3.4），Apple Events 與 SCK 呼叫留在 `Capture/`。

依據（`wfd` 為 run 目錄的 `_tpm/runs/20261010-sdlc-meeting-record/window-filter-diagnosis.md`，**不進版控**；本 spec 只引它的行號與實測數字，不抄其中的真實視窗標題，客戶資料邊界見 §4.14.3）：
- 使用者回報「清單裡根本沒有那個視窗」，要錄的是 Chrome 裡的 M+ Meet（`wfd:9-10`）；實測該視窗被現行篩選**納入**，但網頁標題是會議名稱（真實會議名稱不寫進 repo，下文一律以中性範例「[Stand-up] 範例專案」代稱，原文只在 run 目錄的診斷報告），清單只顯示「Google Chrome — <會議名稱>」，與其他 7 個 Chrome 視窗混在一起認不出來（`wfd:31-32`、`wfd:37`）。
- 「標題非空」篩選把 LINE 通話視窗（500×500、layer 0）與 PowerPoint（1197×840、layer 0）濾掉（`wfd:18-19`、`wfd:39`）。
- Chrome 全螢幕時另有寬 1496、高 81～158 與 1016×87～139 的內部視窗，由尺寸規則濾掉是正確的（`wfd:20`）。
- 同一個 M+ 視窗的 windowID 由 81837 變成 89596（`wfd:33`、`wfd:38`）。
- 該視窗按綠色按鈕進 native 全螢幕、切到別的 Space 後，`desktopIndependentWindow` 擷取 complete 3／idle 14、0 張全黑（`wfd:17`、`wfd:40`）。

#### 3.8.1 篩選

候選視窗＝`SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)` 的 `windows` 中，`exclusionReasons` 為空者。`exclusionReasons` 依序檢查：`layer != 0` → `.layer`；寬 < 400 pt 或高 < 300 pt → `.size`。**標題不參與篩選**（前一版原型的「標題非空」規則移除）；無標題視窗照常列出，顯示方式見 §3.8.6。

#### 3.8.2 會議標記（★）

一列的 `meeting` 不是 null，就是 ★ 列。來源只有兩種：

(a) **原生會議 app**（`source: "app"`）：`meetingAppService(bundleID:)` 查下表。

| bundleID | 服務名 |
|---|---|
| `com.microsoft.teams`、`com.microsoft.teams2` | Teams |
| `us.zoom.xos` | Zoom |
| `Cisco-Systems.Spark`、`com.cisco.webexmeetingsapp` | Webex |
| `com.tencent.meeting`、`com.tencent.tencentmeeting` | 騰訊會議 |

(b) **Chrome 的會議分頁**（`source: "url"`）：bundleID 為 `com.google.Chrome`、`automation == .authorized`、`matchChromeWindow` 回 `.matched(index: i)`，且 `meetingService(url: chrome[i].activeTabURL)` 不是 nil。`meetingService` 規則：以 `URLComponents` 解析；scheme（不分大小寫）必須是 `https`；host 轉小寫後依下表比對，「等於」只接受完全相同，「結尾」接受完全相同或以「`.`＋網域」結尾；其他一律回 nil（例：`https://meet.mplusapp.com.evil.example/…`、`https://notzoom.us/…`、`http://meet.google.com/…` 都是 nil）。

| host 規則 | 服務名 |
|---|---|
| 等於 `meet.mplusapp.com` | M+ Meet |
| 等於 `meet.google.com` | Google Meet |
| 等於 `teams.microsoft.com` 或 `teams.live.com` | Teams |
| 結尾 `zoom.us` | Zoom |
| 結尾 `webex.com` | Webex |

- **只看作用中分頁**：單視窗擷取只錄得到該視窗正在顯示的分頁。作用中分頁不是會議、但 `tabURLs` 裡有會議網址時，該列**不標 ★**、`meetingTabInactive = true`，label 加提示（§3.8.6），讓使用者知道要先切到會議分頁。
- **其他一律不標 ★**：包括 Safari、Chrome 以外的瀏覽器、LINE。前一版原型把 `com.google.Chrome`、`com.apple.Safari` 整個 app 當成會議 app（`main.swift:106-112`），使用者開 8 個 Chrome 視窗時 8 列都有 ★，等於沒有標記，quick-start 也永遠「★ 不唯一」——本版移除。Safari 分頁網址、其他 Chromium 瀏覽器、LINE 列為衍生工作（不編號）。

#### 3.8.3 SCWindow 與 Chrome 視窗的對應（`matchChromeWindow`）

Chrome 的 AppleScript 視窗 `id` 是 Chrome 自己的編號，不是 `CGWindowID`，所以只能以標題與位置對應。依序：
1. SCWindow 標題為空 → `.unmatched`。
2. 取 `chrome` 中 `title` 與 SCWindow 標題**完全相同**者（Chrome 視窗的 `title` 就是作用中分頁的標題）。
3. 恰好 1 個 → `.matched`。
4. 2 個以上 → 再取其中 `bounds` 與 SCWindow `frame` 的 x、y、寬、高四個值相差都 ≤ 2 pt 者；恰好 1 個 → `.matched`，否則 → `.ambiguous`。
5. 0 個 → `.unmatched`。

標題優先、bounds 只用來分辨同名視窗，是因為 native 全螢幕時 Chrome 回報的 bounds 與 SCWindow `frame`（實測 1496×938 @(0,29)，`wfd:17`）是否一致沒有實測。**對不上時的行為**：`.unmatched`／`.ambiguous` 的列不標 ★、照常列出，`meetingCheck` 寫 `unmatched`／`ambiguous`；不猜、不退而求其次用其他規則。

#### 3.8.4 Apple Events 查詢（只讀、選用）

- **只查 Google Chrome**（`com.google.Chrome`）。先用 `NSRunningApplication.runningApplications(withBundleIdentifier:)` 確認 Chrome 在執行；沒在執行 → `.chromeNotRunning`，**不送任何 Apple Event**（不得因為查詢而把 Chrome 開起來）。
- **權限**：以 `AEDeterminePermissionToAutomateTarget`（目標 `com.google.Chrome`、event class 與 ID 皆 `typeWildCard`）判斷；`askUserIfNeeded` 只有 `windows` 帶 `--ask-automation` 時為 true，`quick-start`、`menubar`、`preflight`、`start`、`diagnose-windows` 一律 false（快捷鍵與 menu bar 不得跳授權框卡住）。回傳值對映（`automationStatus(fromOSStatus:)`）：`0` → `authorized`、`-1743`（errAEEventNotPermitted）→ `not_authorized`、`-1744`（errAEEventWouldRequireUserConsent）→ `not_determined`、`-600`（procNotFound）→ `chrome_not_running`、其他 → `error`。
- **只讀**：腳本只取每個視窗的 `title`、`bounds`、`URL of active tab`、`URL of every tab`（以 `get {…} of every window` 的形式，不用變數）。腳本文字是 `Sources/Capture/ChromeTabs.swift` 中的字串常數 `chromeTabsScript`（全 `Sources/` 唯一一段 Chrome 腳本），其中不得出現 `activate`、`execute`、`javascript`、`make`、`close`、`set `、`reload`、`open location`（不分大小寫）。以 `NSAppleScript` 在程序內執行，不 spawn `osascript`（授權要記在 MeetingRecorder 名下）。整段查詢逾時 5 秒，逾時或任何錯誤 → `error`。
- **網址不落地**：分頁網址只在記憶體中比對，不寫進 `record.log`、`record.meta.json`、`record.status.json`、`windows --json` 或 `diagnose-windows` 的輸出（輸出只有服務名）。
- **不影響錄製與結束碼**：`automation` 不是 `authorized` 時，`buildWindowRows` 忽略 `chrome`，清單照常列出、只是 Chrome 列沒有 ★，Chrome 列的 `meetingCheck` 寫 `automation` 的 raw value；`windows`、`quick-start`、`start` 的結束碼不因此改變。
- **preflight 第 13 項 `apple_events`（warn）**：以 `askUserIfNeeded: false` 判斷；`authorized` → pass；其餘（含 `chrome_not_running`，照 D16 字面「沒有授權或 Chrome 沒開」）→ warn，訊息說明「會議分頁不會標記，不影響錄製」與開啟方式（系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome）。永遠不是 hard（`failCode` 為 0）。
- **doctor**：錄製器段加一行以「◦」開頭、含「會議分頁標記」「Apple Events」「選用」的說明，指向 `meeting record preflight` 查實際狀態（doctor 不啟動 app，查不到 TCC，與 `design.md §5 Q8` 同一理由）；這一行一律是「◦」，不得是「✗」或「⚠」，也不影響 doctor 的結束碼。

#### 3.8.5 排序與預設

`buildWindowRows` 的輸出依序比：★ 列在前 → `active` 為 true 在前 → 面積（寬×高）大在前 → `windowID` 小在前。`windows` 的文字與 JSON 輸出、`_record_prompt.py` 的選單都照這個順序。互動選單的預設＝第一個 ★ 列；沒有 ★ 列時沒有預設（§3.7）。`quick-start` 只有 ★ 列恰好一個時開錄（`quickStartDecision`，§4.11.1）。

#### 3.8.6 每列顯示（`label`）

`windowRowLabel` 依序串接下列片段（片段之間兩個半形空白）：
1. ★ 列：`★ 會議（<服務名>）`；其他列沒有這個片段。
2. 名稱：有標題 → `<app> — <title>`；無標題 → `<app>（無標題）`。
3. 尺寸：`<寬>×<高>`（point，整數，`×` 為 U+00D7）。
4. `fullScreenSized` 為 true 時：`全螢幕尺寸`。`isFullScreenSized` 的定義：存在某顯示器 `d`（point）使 `|frame.width − d.width| ≤ 2` 且 `frame.height ≥ d.height − 40`（實測 M+ 全螢幕為 1496×938，顯示器 1496×967，差的 29 pt 是選單列，`wfd:17`）。這只描述尺寸，不宣稱視窗處於 native 全螢幕（沒有公開 API 可判斷）。
5. 狀態：`onScreen` 且 `active` → `前景`；`onScreen` 且非 `active` → `背景`；非 `onScreen` → `不在畫面上`。
6. `meetingTabInactive` 為 true 時：`（這個視窗有會議分頁，但目前顯示的不是它）`。

例：`★ 會議（M+ Meet）  Google Chrome — [Stand-up] 範例專案  1496×938  全螢幕尺寸  不在畫面上`；`LINE（無標題）  500×500  前景`。

#### 3.8.7 `windows` 的輸出

- `--json`：一個 JSON 陣列，元素是 `WindowListRow`（§3.4），鍵恰為 15 個（`windowID`、`app`、`bundleID`、`title`、`untitled`、`width`、`height`、`onScreen`、`active`、`fullScreenSized`、`isMeetingApp`、`meeting`、`meetingTabInactive`、`meetingCheck`、`label`）；`meeting` 為 `{"service","source"}` 或 null；`meetingCheck` 在非 Chrome 列為 null，Chrome 列為 `ok`、`unmatched`、`ambiguous` 或 `automation` 的 raw value（`not_authorized`、`not_determined`、`chrome_not_running`、`error`）。順序照 §3.8.5。
- 文字：每列一行 `[<windowID>] <label>`；之後照舊列顯示器；若有任何 Chrome 列的 `meetingCheck` 是 `not_authorized`、`not_determined` 或 `error`，最後加一行，含「會議分頁標記」「Apple Events」「不授權也能錄」。
- 結束碼不變：成功 0；取不到 `SCShareableContent`（螢幕錄製權限）4。

#### 3.8.8 視窗認回（`resolveWindow`）

`preflight` 第 8 項（`window_exists`）與 `start` 用它決定要錄哪個視窗。`candidates` 是當下全部 `SCShareableContent.windows`（未篩選）：
1. `ref.windowID` 在 `candidates` 中 → `.exact`。
2. 否則，`ref.bundleID` 與 `ref.title` 都有值時，取 `candidates` 中 `exclusionReasons` 為空、`bundleID` 與 `title` 都完全相同者：恰好 1 個 → `.reidentified(新 windowID)`；0 個 → `.notFound`；2 個以上 → `.ambiguous`。
3. 沒有 `bundleID`／`title`（使用者自己打 `--window <id>`）→ `.notFound`。

`.exact`、`.reidentified` → 第 8 項 pass（`.reidentified` 的 `message` 寫「視窗 ID 已由 <舊> 變為 <新>，以 app 與標題認回」），錄製與 `record.meta.json.window` 用認回後的 windowID；`.notFound`、`.ambiguous` → 第 8 項 hard 失敗（code 3），`.ambiguous` 的訊息說明「有多個同 app、同標題的視窗，請重新用 meeting record 選」。**不猜**：不以服務名、尺寸或其他線索擴大比對。錄製中途 windowID 改變不在本 epic 範圍（§7 疑慮 15）。

#### 3.8.9 `diagnose-windows`（app 層診斷子指令，D15）

`open -n -a MeetingRecorder --args diagnose-windows [--json] --log <檔>`：列出 `SCShareableContent.windows` 的**每一個**視窗（含被 §3.8.1 濾掉的），每筆是 `DiagnosedWindow`（`row` 為該視窗照 §3.8.2、§3.8.6 算出的 `WindowListRow`，另加 `layer`、`x`、`y`、`excludedBy`）。`--json` 輸出物件 `{"automation": <AutomationStatus raw value>, "windows": [DiagnosedWindow…]}`；文字輸出每列 `<✓ 或 ✗ <原因,…>> [<windowID>] <label>  layer=<n>  @(<x>,<y>)`，最後一行印 `automation`。不跳授權框；結束碼 0，取不到 `SCShareableContent` 回 4。它**只在 app 的 `--args` 層**，不是 `meeting record` 的寫法（不進 §2.4 封閉清單，D13 的文件一致性檢查不受影響）；SKILL.md 在「清單裡找不到我的視窗」的排錯段寫這一行指令（§4.12.9 驗它存在於 `main.swift` 的 dispatch）。它取代第 0 階段 `main` 上 stash「probe --all 診斷旗標」的用途（stash 本身由主 session 處理）。

---

## 4. 驗收條件

### 4.1 介面與相容性

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.1.1 | 當使用者執行 `meeting.sh record …` 且目前目錄沒有 `record/` 時，`meeting.sh` 應把其餘參數原樣交給 `bin/record.sh` 並以其結束碼結束；頂層 `record)` 分支應位於頂層 `*)`（`^  \*)$`）之前。 | `req:224`；`research-code-contracts.md:25` | `tests/record/test_cli_dispatch.py::test_record_dispatches_to_record_sh` |
| 4.1.2 | `meeting.sh help` 的輸出應含 §2.4.6 結構的 record 段：段頭行恰好一行；`parse_usage(stdout).forms` 應等於 `SURFACE.forms`（7 種寫法、順序相同，多一項或少一項都失敗）；該段恰有一行以 `  層旗標：` 開頭且含 `--recorder` 與 `--yes`，恰有一行以 `  結束碼：` 開頭且依序含 `0 `、`2 `、`3 `、`4 `、`5 `。 | `req:224`；D11、D13 | `test_cli_dispatch.py::test_help_lists_record_forms` |
| 4.1.3 | `meeting.sh` 應維持 §2.1 的既有結束碼：無參數回 1、`meeting.sh --bogus` 回 2、`meeting.sh 不存在的指令` 回 2、`meeting.sh render`（缺場次）回 2、`meeting.sh status <空目錄>` 回 0、`meeting.sh prep <空目錄>` 回 3；**在含有空 `record/` 目錄的工作目錄下**，`meeting.sh prep ./record` 與 `meeting.sh ./record` 仍應回 3（與新增 `record)` 前的 `meeting.sh record` 同結果），而非互動執行 `meeting.sh record` 應回 2（§6 第 17 條的核准變更）。 | `rules.md:68`；`req:83`；D11 | `test_cli_dispatch.py::test_existing_exit_codes_unchanged`、`::test_record_dir_explicit_prep_paths_unchanged` |
| 4.1.4 | `record` 各寫法應依 §2.2 回傳結束碼：`EXIT_CODE_CASES`（§2.4.7）的每一筆，依 §2.4.7 組參數、以 `MH_RECORD_OPEN` 替身執行，實際結束碼應等於 `expect`；`{(form, expect)}` 應等於 `SURFACE.form_codes`。 | `req:224`、`req:273` | `tests/record/test_record_sh.py::test_exit_code_matrix` |
| 4.1.5 | `bin/record.sh` 應只以 `open -n -a` 或 `MH_RECORD_OPEN` 啟動錄製器，原始碼中不得出現 `Contents/MacOS/MeetingRecorder` 的直接執行。 | `req:205` | `tests/record/test_static_rules.py::test_no_direct_exec_of_recorder` |
| 4.1.6 | 若 `open` 之後 20 秒內沒有 `runId` 相符的狀態，則 `record` 應回 4 並印出開啟螢幕錄製設定的指令與「授權後要完全結束再重開」。 | `req:207`；`probe.sh:35-38` | `test_record_sh.py::test_no_status_within_timeout_exits_4` |
| 4.1.7 | `record.sh` 應忽略 `runId` 與本次不符的殘留狀態檔。 | `adr/adr-control-channel.md` | `test_record_sh.py::test_stale_status_ignored` |
| 4.1.8 | `bin/_record_prompt.py` 應依 §3.7 把提示印到 stderr、把答案以一行 JSON 印到 stdout，且執行前後暫存目錄內不得新增或修改任何檔；型態選項應等於 `bin/_profile.py` 的 `PROFILES` 鍵（以 import 取得，不另抄清單）。 | `req:217` | `tests/record/test_prompt.py::test_prompt_prints_json_and_writes_nothing`、`::test_prompt_types_come_from_profiles` |
| 4.1.9 | `bin/_record_estimate.py --minutes N` 應印出 §3.7 公式的整數；`meeting.sh doctor` 的錄製器段與 `record.sh` 的 `--min-free-bytes` 應都呼叫這支程式取得數值（原始碼 grep 可見兩處呼叫）。 | `req:219`；`design.md §5 Q7` | `tests/record/test_estimate.py::test_formula`、`::test_shared_by_doctor_and_record_sh` |
| 4.1.10 | 當目前目錄有 `record/` 時：(a) 若 stdin 或 stderr 不是 tty、或參數含 `--yes`，`meeting.sh record …` 應回 2、不啟動錄製器也不跑 prep，並印出 `--recorder` 與 `prep ./record` 兩種寫法；(b) 若在 tty 上回答「1」，應交給 `record.sh`；回答「2」，應執行與 `meeting.sh prep record` 相同的流程；(c) `meeting.sh record --recorder …` 應直接交給 `record.sh`、不詢問。 | D11；`design.md §8.1` | `test_cli_dispatch.py::test_record_dir_conflict_noninteractive_exits_2`、`::test_record_dir_conflict_yes_flag_exits_2`、`::test_record_dir_conflict_interactive_choices`（以 `pty` 模擬終端機）、`::test_record_dir_conflict_explicit_recorder_flag` |
| 4.1.11 | 當使用者在沒有 `record/` 的目錄執行 `meeting.sh record help`、`record -h`、`record --help` 時，`meeting.sh` 應各回 0、三者 stdout 逐位元組相同，且 `parse_help(stdout)`（§2.4.4）不報文法錯誤、五個成分（`forms`、`form_flags`、`form_codes`、`layer_flags`、`codes`）都等於 `SURFACE`；不得呼叫 `MH_RECORD_OPEN` 替身，`MH_RECORD_HOME` 下不得新增或修改任何檔。 | D13；`req:224` | `test_cli_dispatch.py::test_record_help_prints_surface` |
| 4.1.12 | 若 `meeting.sh record <寫法>` 帶了未知選項（§2.4.2；測試用 `--no-such-flag`，依 §2.4.7 加在最後），則對 `SURFACE.forms` 的每一種寫法都應回 2 且 stderr 含「未知的選項」；層旗標 `--recorder`、`--yes` 應在交給 `record.sh` 前被拿掉（以 `MH_RECORD_OPEN` 替身把收到的參數寫進暫存檔，驗證兩個字都不在其中）；層旗標不論在中間或結尾都依 §2.4.2 拿掉、不算未知選項。**替身參數的判定**（第七修正輪，取代前一版「恰為」，因 §3.5 規定 `record.sh` 呼叫 app 時一定另帶必帶參數）：「替身參數」＝`MH_RECORD_OPEN` 替身每次被呼叫時的 `argv[1:]`（`fake_open.sh` 逐次記錄）；本條不約束 `record.sh` 在 app 參數前放什麼（例如 `-n -a <app> --args`），只用下列三條斷言：(i) **層旗標不在**——每一次呼叫的替身參數都不含 `--recorder`、`--yes`；(ii) **使用者給的參數依原序是子序列**——至少有一次呼叫含該寫法的子指令字，且在該次呼叫中，使用者給的參數拿掉層旗標之後（(a) 為 `preflight`、`--window`、`1`；(b) 為 `windows`、`--json`）依原序是替身參數的子序列，其中 `--window` 的下一個參數是 `1`；(iii) **§3.5 的必帶參數存在**——同一次呼叫中，(a) `--session`、`--min-free-bytes`、`--run-id`、`--home` 各出現且各自緊接一個不以 `--` 開頭的值；(b) `--log` 出現且緊接一個值，並且（stdin＝`/dev/null`）不含 `--ask-automation`（§4.15.13）。執行環境照 §2.4.7（app 視為已建置、`FAKE_SCENARIO=recording`）。(a) 中間——cwd 有空的 `record/`、stdin＝`/dev/null`，執行 `meeting.sh record preflight --recorder --window 1`：不出現撞名提示、不因撞名回 2，替身參數滿足 (i)–(iii)，stderr 不含「未知的選項」，結束碼等於同環境下 `meeting.sh record --recorder preflight --window 1` 的結束碼；(b) 結尾——cwd 沒有 `record/`、stdin＝`/dev/null`，執行 `meeting.sh record windows --json --yes`：替身參數滿足 (i)–(iii)，stderr 不含「未知的選項」，結束碼等於同環境下 `meeting.sh record windows --json` 的結束碼；同一指令在 cwd 有空的 `record/` 時應回 2、印出 §2.3 的兩種寫法、替身未被呼叫（`--yes` 在結尾仍生效）。 | D11、D13；`bin/meeting.sh:399` | `test_cli_dispatch.py::test_record_unknown_flag_exits_2`、`::test_meeting_sh_layer_flags_stripped`、`::test_layer_flag_mid_position_stripped`、`::test_layer_flag_trailing_position_stripped` |

### 4.2 preflight（D1：12 項、分級；D16 加第 13 項 `apple_events`，warn）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.2.1 | `PreflightItem` 應恰有 13 項（§3.4），其中 `signing`、`power`、`window_minimized`、`apple_events` 為 warn，其餘 9 項為 hard；`failCode(of: .apple_events)` 應為 0。第 5 項 `system_audio_rms` 的**分級**仍為 hard（`severity(of:)`、`failCode(of:)` 不變，D19 不改分級）；單筆結果只在 §4.2.5 的 `.warnTargetSilent` 情形以 `warnOnly` 降為 warn（§4.2.9）。 | D1；D16；D19；`req:197`、`req:293` | `swift:PreflightTests.swift::testPreflightItemsAndSeverity` |
| 4.2.2 | hard 項失敗碼應為：權限三項、RMS 兩項、`disk` → 4；`window_exists` → 3；`session_collision`、`already_running` → 2；多項同時失敗時取 4＞3＞2；`PreflightResult` 的 JSON 應含 `item`、`ok`、`severity`、`code`、`message` 五鍵。 | `req:273`；`design.md §6` | `swift:PreflightTests.swift::testFailCodesAndPrecedence`、`::testResultJSONKeys` |
| 4.2.3 | 若有任一 hard 項失敗，則錄製器不應開始寫任何 `seg-*.mov`，狀態應為 `preflight_failed`。 | D1 修訂 `req:197` | `test_record_sh.py::test_hard_fail_does_not_start`（替身）；人工 §4.2.6 |
| 4.2.4 | 當只有 warn 項失敗時，錄製器應照常開錄，並在 `record` 的輸出與 `record.status.json.preflight` 列出該 warn。 | D1 | `test_record_sh.py::test_warn_only_starts_with_notice` |
| 4.2.5 | **第 5 項系統聲音（D19 兩段式）與第 6 項麥克風**：時段判定一律為「任一 0.5 秒時段峰值 > -60 dBFS」（`PeakWindow(windowSeconds: 0.5)` 收斂後取最大值）。(a) **目標視窗**：錄製器應對目標視窗的 probe stream（`SCContentFilter(desktopIndependentWindow:)`，與正式錄製同一組音訊設定、`excludesCurrentProcessAudio=true`）量 3 秒，期間**不播測試音**；系統聲音與麥克風各自判定。第 6 項（麥克風）只看 (a)，判定、分級與訊息不變。(b) **系統聲音擷取權限**：只有在 (a) 的系統聲音最大值 ≤ -60 dBFS（含 -∞；目標視窗認不到時 (a) 的系統聲音視為 -∞）時，錄製器才應在 (a) 結束後另開一條 `SCContentFilter(display:excludingWindows: [])` 的 3 秒 probe stream（同樣 `excludesCurrentProcessAudio=true`），期間由錄製器 spawn `/usr/bin/afplay` 子程序播放測試音兩次，以同一判定量系統聲音；(a) 已 pass 時不得開 (b)、不得播測試音。(c) **第 5 項的結果**應由 `systemAudioCheck(targetPeakDBFS: (a), displayPeakDBFS: (b) 或 nil, thresholdDBFS: -60)` 決定：`.pass` → ok；`.warnTargetSilent` → `PreflightResult(item: .system_audio_rms, ok: false, message: …, warnOnly: true)`（severity warn、code 0，照常開錄並依 §4.2.4 列出），message 應含「會議 app 目前沒有聲音」「擷取權限正常」「15 秒」，讓使用者知道會議 app 目前沒有聲音、系統聲音擷取權限正常、開錄後若持續靜音 15 秒會告警（§4.5.1）；`.fail` → hard、結束碼 4，**t6 第二輪（D21）**：message 只含授權補救——應含「重新授權螢幕錄製」與「完全結束 MeetingRecorder 再重開」（若剛授權，完全結束再重開），`PreflightRunner.swift` 的任何字串字面值都**不得**再含「取消輸出靜音」「把音量調大」。理由（D21 實機事實）：ScreenCaptureKit 擷取系統聲音在系統輸出靜音之前，輸出靜音時會議 app 的聲音與 `afplay` 測試音都錄得到，所以 (b) 錄不到只可能是擷取權限問題，叫使用者取消靜音、調大音量是錯的補救。 | `req:198`；`d2:19`、`d2:23-27`；D19（t6 實機：單一視窗 filter 錄不到錄製器 spawn 的 `afplay`，§4.3.5）；D21（t6：輸出靜音＋影片播放 (a) -11.8 dBFS pass；輸出靜音＋影片暫停 (a) -∞、(b) 測試音 -17.4 dBFS → warn） | `swift:AudioLevelTests.swift::testPeakWindowJudgement`（時段判定）；`swift:PreflightTests.swift::testSystemAudioCheckTwoStage`（(c) 的判定，D21 不改）；`test_static_rules.py::test_preflight_system_audio_two_stage`（(a)(b)(c) 的實作形狀；`.fail` 訊息的預期依 D21 改，§6 第 54 條）；人工 §4.2.6 |
| 4.2.6 | 13 項各製造一次失敗（撤銷螢幕錄製權限、授權後不重開、撤銷麥克風權限、靜音輸出、拔麥克風或靜音輸入、目標磁碟可用空間 < `minFreeBytes`、關掉會議 app、同名場次、用電池且 < 20%、已有錄製在跑、最小化會議視窗、ad-hoc 簽章、在「自動化」不允許 MeetingRecorder 控制 Chrome）時，hard 項應回 §4.2.2 的結束碼且訊息含補救步驟，warn 項應照常開錄且有提示；「剛授權要重啟」與「沒有授權」的訊息應不同。**第 5 項依 §4.2.5 分三步做**（D19；以 Chrome 會議視窗為目標，例如標題「[Stand-up] 範例專案」的視窗）：(i) **t6 第二輪（D21）**：系統輸出靜音、且會議 app 沒有聲音 → 第 5 項 warn（`.warnTargetSilent`）、照常開錄、結束碼 0，訊息同 (ii)；系統輸出靜音、會議 app 正在發聲 → 第 5 項 pass（輸出靜音不影響錄音）；`.fail` 路徑（擷取權限不通）在第 2、3 項通過時實機難以單獨製造，改由 §4.2.9 的 Swift 測試與 §4.2.5 的靜態檢查涵蓋；(ii) 沒有靜音、會議 app 沒有聲音（例如會議還沒開始、被錄的 Chrome 沒有分頁在播）→ 第 5 項 warn、照常開錄，訊息含「會議 app 目前沒有聲音」「擷取權限正常」「15 秒」，檢查期間聽得到兩次測試音；(iii) 會議 app 正在發聲（例如在被錄的 Chrome 視窗播有聲影片）→ 第 5 項 pass，檢查期間**不播**測試音。三步都要另確認第 6 項（麥克風）的結果不受影響。 | `req:273`（D1 修訂）；`PROBE-REPORT.md:51-53`；D19 | 人工；結果記在 test 段報告 |
| 4.2.7 | `rmsDBFS(sampleBuffer:)` 對雙聲道非交錯 Float32 buffer 應回正確值，不得因 `AudioBufferList` 配置不足而回 -∞。 | `d2:34-39` | `swift:AudioLevelTests.swift::testNonInterleavedStereoBuffer` |
| 4.2.8 | **hardened runtime 與 entitlement（麥克風＋Apple Events）**：`tools/MeetingRecorder/Resources/MeetingRecorder.entitlements` 應存在，且其頂層鍵集合應恰為 `{com.apple.security.device.audio-input, com.apple.security.automation.apple-events}`、兩者值皆為 true（不得含 `com.apple.security.app-sandbox`）；`Resources/Info.plist` 應有非空的 `NSAppleEventsUsageDescription`（繁中，含「Chrome」與「網址」）；`build.sh` 中每一個 `codesign --force` 呼叫都應帶 `--entitlements`；當簽章身分存在時，建出的 app `codesign -dvv` 的 flags 應含 `runtime`，`codesign -d --entitlements -` 的輸出應同時含 `com.apple.security.device.audio-input` 與 `com.apple.security.automation.apple-events`；使用者重新授權後，preflight 第 4 項（麥克風權限）與第 6 項（麥克風 RMS）應 pass，第一次以 `--ask-automation` 執行 `windows` 時應跳出「允許控制 Google Chrome」授權框（§4.15.18）。 | Apple〈Hardened Runtime〉Resource Access；`design.md §9.1`；第二輪 skeptic 問題 2；D16；第六修正輪 skeptic 問題 2 | `test_static_rules.py::test_entitlements_audio_and_apple_events`、`::test_info_plist_apple_events_usage`、`::test_build_signs_with_entitlements`；t3 完成條件（暫存目錄建 app 後 `codesign` 檢查）；人工（t6 第一步、§4.15.18） |
| 4.2.9 | **第 5 項兩段式的 Core 判定（D19）**：`systemAudioCheck(targetPeakDBFS:displayPeakDBFS:thresholdDBFS: -60)` 應：target -10.2、display nil → `.pass`；target -59.9、display nil → `.pass`；target -60（恰在門檻）、display -19.9 → `.warnTargetSilent`；target -∞、display -19.9 → `.warnTargetSilent`；target -∞、display -∞ → `.fail`；target -∞、display -60 → `.fail`；target -∞、display nil → `.fail`；target NaN、display NaN → `.fail`。`PreflightResult(item: .system_audio_rms, ok: false, warnOnly: true)` 的 `severity` 應為 `.warn`、`code` 為 0，與任何 hard 失敗並列時 `exitCode(for:)` 不受它影響（例：與 `window_exists` 失敗並列回 3、單獨回 0）；`warnOnly: true` 配 `ok: true` 或配其他 item（例 `.disk`、`.mic_rms`）時 `warnOnly` 應存成 false、`severity` 照 `severity(of:)`；JSON 仍恰為五鍵、`severity` 為 "warn"、往返 decode 後相等；`{"item":"system_audio_rms","ok":true,"severity":"warn",…}` decode 後 `severity` 為 `.hard`（ok 為 true 不還原）；§4.2.2 `testResultJSONKeys` 的既有預期（`disk` 帶 "warn" 時以 item 重算為 hard）不變。 | D19；§3.4 | `swift:PreflightTests.swift::testSystemAudioCheckTwoStage`、`::testSystemAudioWarnOnlyResult` |
| 4.2.10 | **WindowServer 連線在主執行緒建立**（t6 實機缺陷）：錄製器 `main.swift` 應在第一個 `Task { … }` 之前、於頂層（主執行緒、無縮排）呼叫 `NSApplication.shared` 或 `CGMainDisplayID()` 初始化 WindowServer 連線；實機上 `preflight`／`start`／`quick-start` 建 `SCContentFilter` 時不得因 SkyLight assert 而 SIGABRT。 | t6 第 1 步實機（`gate1-decisions.md` D19 列「另記」）；紅燈 `b16a375`、修正 `413eb50`；§6 第 46 條 | `test_static_rules.py::test_windowserver_connection_initialized_on_main_thread`；人工（t6：preflight、start、quick-start 各跑一次不當掉） |
| 4.2.11 | **preflight 到正式 `startCapture` 的等待與重試（D20 一併修，t6 缺陷 4）**：`start`／`quick-start` 在 preflight 最後一條 probe stream 的 `stopCapture()` 回來後，應等 `startCaptureSettleSeconds`（1.0 秒）才呼叫正式 `startCapture()`；若 `startCapture()` 丟錯，應在 `record.log` 記一行含「startCapture 第一次失敗」與錯誤訊息、等 `startCaptureRetryDelaySeconds`（2.0 秒）、以同一組 filter 與設定**重建** `SCStream` 後重試**恰好一次**；重試仍失敗才照現行回 `phase=failed`、`code=5`（`record` 的結束碼 5），且整個過程不得留下任何 `seg-*.mov`。兩個常數應定義在 `tools/MeetingRecorder/Sources/Capture/` 且數值如上，各自在定義以外至少被引用一次。 | t6 實機（`t6-results.md`「缺陷 4」）；`design.md §7.6` | `test_static_rules.py::test_start_capture_settle_and_retry`；人工（t6：輸入與輸出都用藍牙耳機，連續 `meeting record` 開錄、錄 10 秒、`stop` 五次，五次都要開錄成功；`record.log` 若出現「startCapture 第一次失敗」要記進報告） |
| 4.2.12 | **幕前調度提醒（t6 第三輪，發現 I）**：preflight 應以只讀方式讀 `com.apple.WindowManager` 的 `GloballyEnabled`（`CFPreferencesCopyAppValue`；不呼叫 SCK、不觸發任何授權框）；值為 true 時，第 12 項 `window_minimized` 應為 `ok: false`（warn、code 0、照常開錄，§4.2.4），message 應含 `stageManagerNotice(globallyEnabled: true)` 的全文——說明「幕前調度已開啟：會議視窗不在目前舞台時會被縮成側邊縮圖，錄影解析度會跟著變小」與補救「錄會議時讓會議視窗留在目前舞台，或先關閉幕前調度」；視窗同時疑似最小化時兩段訊息都要列出（以「；」連接）。開錄時同一提醒寫一行進 `record.log`。`stageManagerNotice(true)` 應含「幕前調度」「縮圖」「目前舞台」；`stageManagerNotice(false)`、`stageManagerNotice(nil)` 應為 nil。錄製器與 `bin/record.sh` 不得改寫任何系統設定：`tools/MeetingRecorder/Sources/` 與 `bin/` 不得出現 `CFPreferencesSetAppValue`、`CFPreferencesSetValue`、`defaults write`、`com.apple.WindowManager` 的寫入；`PreflightItem` 仍恰 13 項（§4.2.1 不變）。錄製中的尺寸跟隨（§4.3.4）**不變**：幕前調度開著且會議視窗被縮成縮圖時，該段仍照縮圖尺寸錄（已知限制，§7 疑慮 31）。`.claude/skills/meeting-record/SKILL.md` 與 `README.md` 錄製段應各有一句說明（含「幕前調度」「縮圖」），`README.md` 不得動 `record-cli` 區塊。 | 發現 I（`t6-results.md`「t6 第二輪重測」第 6 項：ffplay 視窗被縮成 105×99 pt、段落 210×198 px）；`design.md §7.1`〈幕前調度〉；§6 第 63 條 | `swift:PreflightTests.swift::testStageManagerNotice`；`test_static_rules.py::test_stage_manager_read_only`；`test_docs.py::test_stage_manager_documented`；人工（使用者自行開啟幕前調度後跑一次 `meeting record preflight`，看到第 12 項 warn；之後自行關閉——主 session 與 agent 不得替使用者切換） |

### 4.3 擷取設定

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.3.1 | 開錄時，錄製器應把 §3.3 的 `config` 快照寫進 `record.meta.json`，值應與該範例相同。 | `req:173-185` | `tests/record/e2e_check.py`（人工錄製後）；判準自測 `test_e2e_check.py::test_config_snapshot_check` |
| 4.3.2 | 每一段 `seg-NNNN.mov` 的寬高應等於該段開檔時會議視窗的像素尺寸（`evenPixelSize`，容許 ±2 px），並記在 `manifest.json.segments[i].width／height`；`影片/*.mov` 的寬高應等於 `manifest.json.outputCanvas`＝(各段寬最大值, 各段高最大值)。 | D8（取代 `req:179` 的固定畫布，§6 第 5 條） | `swift:SegmentsTests.swift::testEvenPixelSize`；`e2e_check.py`；`test_e2e_check.py::test_canvas_check` |
| 4.3.3 | `record.meta.json.config.minimumFrameInterval` 應為 `"1/60"`；當目標視窗持續變化（播放 60 fps 合成測試畫面至少 20 秒）時，`影片/*.mov` 在該區間以 1 秒滑動窗計的影格數最大值應 ≥ 55，且（**t6 第三輪，發現 M**，取代前一版「全片相鄰影格 PTS 間隔最小值 ≥ 1/60 秒 − 1 ms」）`影片/*.mov` 全片應同時滿足：(i) 以 1 秒滑動窗計的影格數最大值 ≤ 61（沒有超過 60 fps 的突發）；(ii) 相鄰影格 PTS 間隔 < 1/60 秒 − 1 ms 的次數 ≤ 各段原始 `seg-*.mov` 中同條件的次數合計＋（段數 − 1）（finalize 不得製造新的過近影格，每個段落邊界最多容許 1 個）；(iii) 相鄰影格 PTS 間隔最小值 ≥ 1 ms（擋 t6 缺陷 3 那種被擠到 1/90000 秒的影格）；`影片/*.mov` 應為 H.264、恰好一條音軌。 | D9；`req:264` 經 §6 第 6 條修訂 | `e2e_check.py --fps-interval mm:ss-mm:ss`；`test_e2e_check.py::test_fps_peak_check`（`fps120` 仍判 `fps_min_interval` FAIL，由 (i) 擋）、`::test_fps_min_interval_check`（t6 第三輪：原始段落本身有 10 ms 間隔、最終片只多 1 個邊界間隔 → PASS；正規化把間隔擠成 < 1 ms → FAIL；最終片過近間隔比原始多出段數以上 → FAIL）；實機數據見 §6 第 68 條 |
| 4.3.4 | 在錄製期間把會議視窗縮小、再放大（各至少跨過一次 60 秒輪替）時，**縮放完成後的第一個段落邊界開出的** `seg-NNNN.mov` 起，寬高應反映新的視窗像素尺寸（§4.3.2 判準；**t6 第二輪**：尺寸在換段當下同步讀取，`design.md §7.1`，不再有「慢一段才生效」——t6 缺陷 A：約 1:10 縮小，120 秒開的 seg-0003 仍是舊尺寸、180 秒的 seg-0004 才改），段內縮放時內容不得被裁切（`scalesToFit` 等比留邊）；`影片/*.mov` 應以 §4.3.2 的輸出畫布涵蓋每一段，各段畫面不縮放、只置中補邊。 | D8；`design.md §7.1` | 人工（test 段量測閘門）；`e2e_check.py`；不過則 `needs_decision` |
| 4.3.5 | **錄到的系統聲音範圍（D19）**：以單一視窗 filter（`record.meta.json.config.filter` 為 `"desktopIndependentWindow"`，§3.3）錄製時，錄到的系統聲音應只含**擁有會議視窗的那個 app** 的聲音——例：錄 Chrome 裡的會議，同一個 Chrome 所有分頁的聲音都會錄進來；別的 app 的通知音、音樂不會；麥克風照常錄。錄製器不得為了收到其他 app 的聲音而改用 display filter 錄製（display filter 只用於 preflight §4.2.5 (b)）。`.claude/skills/meeting-record/SKILL.md` 應用一般使用者看得懂的一兩句說明這個範圍，並提醒錄會議時同一個瀏覽器不要再播其他有聲音的分頁（含「同一個瀏覽器」與「其他」「分頁」字樣）；`README.md` 錄製段應有一句同義說明（不得動 `record-cli` 區塊）。§4.9、§4.10 的端到端量測中，系統聲音來源（有聲影片、`e2e_check.py --print-sync-source` 的同步測試源）應由被錄視窗所屬的 app 播放（例如直接選 ffplay 播同步測試源的那個視窗開錄，或在被錄的 Chrome 視窗裡播影片），否則系統聲音路必然靜音。 | D19；t6 實機：Chrome 播影片時對該 Chrome 視窗 preflight 系統聲音 -10.2 dBFS、同一時間對終端機視窗 -∞，錄製器 spawn 的 `afplay` 在單一視窗 filter 下錄不到（`gate1-decisions.md` D19 列）；對照 D2 實驗 D 是 display filter（`d2:7`、`d2:19`） | `test_docs.py::test_audio_scope_documented`；人工（t6：錄 Chrome 會議視窗時，另一個 app 播音樂不應進 `錄音/*.wav`，同一個 Chrome 另一分頁的聲音會進） |
| 4.3.6 | **換段當下同步讀視窗尺寸（t6 第二輪，缺陷 A）**：`nextSegmentSize(windowPoints:scale:previous:)` 應：((1496, 938), 2.0, 2992×1876) → 2992×1876；((1385, 868), 2.0, 2992×1876) → 2770×1736；((1385.5, 868.7), 2.0, 2992×1876) → 2770×1736；(nil, 2.0, 2770×1736) → 2770×1736；((0, 868), 2.0, 2992×1876) → 2992×1876；((1385, -1), 2.0, 2992×1876) → 2992×1876；((.infinity, 868), 2.0, 2992×1876) → 2992×1876。實作形狀：`tools/MeetingRecorder/Sources/Capture/` 應出現 `CGWindowListCreateDescriptionFromArray` 與 `kCGWindowBounds`；`RecordingSession.swift` 應呼叫 `nextSegmentSize(`，且不得再出現 `pendingSize`、`sizeQuery`、`scheduleSizeQuery`（邊界前 1 秒非同步查詢的做法整個移除）；`startNewSegment` 的函式本體應呼叫 `nextSegmentSize(`，且不得出現 `await`、`Task {`、`shareableContent(`（尺寸讀取必須同步、在換段當下完成；舊段 1 秒後收尾的既有 `asyncAfter` 不在此限）。 | t6 缺陷 A；`t6-rca-ABE.md`〈A〉；`design.md §7.1` | `swift:SegmentsTests.swift::testNextSegmentSize`；`test_static_rules.py::test_segment_size_read_synchronously_at_boundary`；人工 §4.3.4 |

### 4.4 分段落盤（D3：60 秒）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.4.1 | 在錄製期間，錄製器應以 sample 時鐘每 60 秒換一個 `tracks/seg-NNNN.mov`（四位數、從 0001 起），每段收尾後都能被 `ffprobe` 讀取；**D20**：每段應恰有 1 條 H.264 影片軌與 2 條 AAC 音軌，順序為影片、系統聲音、麥克風。 | `req:200`（D3）；D20 | `swift:SegmentsTests.swift::testSegmentFileName`；`e2e_check.py`；`e2e_check.py --segment-writer` 的 `segment_tracks`；`test_e2e_check.py::test_segment_tracks_check` |
| 4.4.2 | 在錄製期間，`錄音/` 第一層不應出現任何 `m4a/mp3/wav/mov/mp4/m4v` 檔。 | `req:156` | `tests/record/test_concurrency.py::test_recording_session_not_listed`；人工 §4.7.1 |
| 4.4.3 | **量測閘門（D20 後重跑）**：3 分鐘錄製（至少 2 個邊界）時，(a) 段落空隙（`design.md §7.2` 量法，`audioDuration` 取各音軌最長）應滿足 `max(\|g_i\|) < 0.5 秒` 且 `Σ g_i < 0.5 秒`；(b) 除了被 `kill -9` 中斷的情形，每一段的 `finishedAt` 都不得是 `null`，且每個邊界 `finishedAt_i − startedAt_{i+1} < 5 秒`；(c) 定期換段的 `startedAt_{i+1} − startedAt_i` 應等於 60.000 秒（容許 0.001）。**t6 第二輪（缺陷 G）**：「定期換段」以外的提前換段不受 (c) 約束，判定（只用場次內的檔，不看 `record.status.json`）：邊界 i→i+1 若 (1) `record.meta.json.audioFormatEvents` 中有任何一筆（**任何欄位改變都算**，不限 `sampleRate`——錄製器對取樣率、聲道數、交錯與否、樣本型別的改變都會提前換段，`design.md §7.5`）的 `t` 與 `startedAt_{i+1}` 相差 < 0.5 秒，或 (2) 第 i 段的 `finishedAt` 是 `null`（writer 失敗後提前換段，`design.md §7.2`〈writer 失敗〉），且間隔 < 60.000 − 0.001 秒，即為提前換段、略過；其餘邊界照 60.000 判。門檻 0.5 秒是 D3「空隙門檻沿用 0.5 秒」，不是 D10 的 3 秒（那是裝置切換的中斷容許值）。 | `req:201`、`req:268`；D3；D20（t6：4 次輪替每次約 10.5 秒、各段 `finishedAt` 全 `null`） | `swift:SegmentsTests.swift::testBoundaryGaps`（計算）；`e2e_check.py`（`gap`）、`e2e_check.py --segment-writer`（`segment_finished`、`segment_cadence`）；`test_e2e_check.py::test_gap_check`、`::test_segment_finished_check`、`::test_segment_cadence_excludes_early_rotation`（t6 第二輪）；**test 段量測閘門**（t6 中途修正輪後第一步） |
| 4.4.4 | **D20 改為必驗**：靜止視窗錄 70 秒以上跨過一次換段時，`seg-0002.mov` 應含 video stream，且其影片軌 `start_time` ≤ 0.05 秒（新段第一個視訊 sample 落在段落起點，`design.md §7.2` 換段第 3 步）；`影片/*.mov` 應有涵蓋全程的影片軌（§4.6.3）。 | `adr/adr-segment-writer.md`；D20 | test 段量測閘門；`e2e_check.py --segment-writer`（`segment_video_start`）；`test_e2e_check.py::test_segment_video_start_check` |
| 4.4.5 | **D20 寫檔機制的靜態約束**：`tools/MeetingRecorder/Sources/Capture/` 中除 `Probe.swift` 以外的檔案不得出現 `SCRecordingOutput`、`addRecordingOutput`、`removeRecordingOutput`；`Capture/` 應出現 `AVAssetWriter(`、`startSession(atSourceTime:`、`endSession(atSourceTime:`、`markAsFinished()`、`finishWriting`、`movieFragmentInterval`、`AVVideoAllowFrameReorderingKey`、`AVVideoScalingModeKey`、`expectsMediaDataInRealTime = true`、`routeSample(`、`segmentVideoBitRate(`、`segmentWriteFailed`。 | D20；`design.md §7.2` | `test_static_rules.py::test_segment_writer_uses_assetwriter` |
| 4.4.6 | **D20 的 Core 判定**：`routeSample(start:end:boundary:)` 應：(59.0, 59.5, 60) → `.old`；(59.98, 60.0, 60) → `.old`；(59.99, 60.01, 60) → `.both`；(60.0, 60.0, 60) → `.new`；(60.0, 60.02, 60) → `.new`；(61.0, 61.0, 60) → `.new`。`segmentVideoBitRate` 應：(2992, 1876) → 7_016_240；(640, 480) → 4_000_000；(5120, 2880) → 10_000_000；(1920, 1080) → 4_000_000。`WarningKind.segmentWriteFailed.rawValue` 應為 `"segment_write_failed"`、`isAlert` 為 true，`RecordWarning` 以它往返 JSON 後相等；既有七個 kind 的 raw value 與 `isAlert` 不變。 | D20；§3.4 | `swift:SegmentsTests.swift::testRouteSample`、`::testSegmentVideoBitRate`；`swift:RecordsTests.swift::testSegmentWriteFailedWarningKind` |
| 4.4.7 | **writer 失敗（D20）**：若錄製中某段 writer 失敗，錄製器應在 `warnings[]` 加 `segment_write_failed`（訊息為中文、含段落檔名）、保留該段檔案、立刻開新段繼續錄；新段在 10 秒內又失敗時應優雅停止並收尾，`record.status.json.code` 為 5、訊息含「段落連續寫檔失敗」；只失敗一次而錄製繼續到使用者 `stop` 時，`code` 也應為 5（錄製中出過錯）。**t6 第二輪（缺陷 D）**：因段落連續寫檔失敗而停止後，**即使收尾（finalize）也失敗**（例如 `tracks/` 仍唯讀），`record.status.json.message` 與 `record.log` 最後一行訊息仍應含「段落連續寫檔失敗」，可在其後附加收尾失敗的原因（`completionOutcome`，§3.4、§4.4.9）；`phase` 為 `failed`、`code` 為 5。 | D20；`design.md §7.2`〈writer 失敗〉；§2.2 `record` 列的 5；t6 缺陷 D（`RecordingSession.swift` 的 forced 訊息被收尾失敗訊息蓋掉） | 人工（t6：錄製中對 `tracks/` 執行 `chmod a-w` 跨過一次換段，應先出現告警、10 秒內再失敗即自動停止、`code` 5；`chmod u+w` 後 `meeting record finish <場次>` 應回 0 並納入失敗前已收尾的段落） |
| 4.4.8 | **停止時最後一段的收尾（D20）**：`record stop` 正常結束後，最後一段的 `finishedAt` 不得是 `null`，且 `wallClock`（`manifest.json.gapStats.wallClock`）與 `startedAt_1 + Σ audioDuration_i` 差應 < 1 秒（最後一段寫到停止點為止，沒有因收尾而截掉）。 | D20；`design.md §7.4` | `e2e_check.py --segment-writer`（`segment_finished`、`stop_tail`）；`test_e2e_check.py::test_segment_finished_check` |
| 4.4.9 | **錄製結束的最終結果（t6 第二輪，缺陷 D）**：`completionOutcome` 應：(rc 5, forced (5, "段落連續寫檔失敗，已停止並收尾；已落盤段落保留"), hadError true, "/x/s") → `.failed`、5、message 以「段落連續寫檔失敗」開頭且含「收尾失敗（_record_finalize.py 回 5）」與「/x/s」；(rc 0, forced 同上, true) → `.done`、5、message 等於 forced 訊息；(rc 0, nil, true) → `.done`、5、"錄製中出過錯（見 record.log），已收尾；段落保留"；(rc 0, nil, false, "/x/s") → `.done`、0、"已完成：/x/s"；(rc 127, nil, false, "/x/s") → `.failed`、5、message 以「收尾失敗（_record_finalize.py 回 127）」開頭。`RecordingSession.swift` 的 `complete(finalizeCode:)` 應呼叫 `completionOutcome(`，且本體不得再自行組「收尾失敗（」字串。 | t6 缺陷 D；§3.4 | `swift:RecordsTests.swift::testCompletionOutcome`；`test_static_rules.py::test_completion_uses_outcome`；人工 §4.4.7 |
| 4.4.10 | **影片心跳（t6 第二輪，缺陷 E／D22）**：`shouldEmitVideoHeartbeat(samplePTS:lastVideoPTS:hasLastFrame:interval: 1.0)` 應：(10.0, 9.0, true) → true；(9.999, 9.0, true) → false；(70.0, 9.0, true) → true；(10.0, nil, true) → false；(10.0, 9.0, false) → false；(.nan, 9.0, true) → false；(10.0, .infinity, true) → false。實作形狀：`tools/MeetingRecorder/Sources/Capture/` 應定義 `videoHeartbeatSeconds`（值 1.0）且在定義以外至少被引用一次；`RecordingSession.swift` 應呼叫 `shouldEmitVideoHeartbeat(` 與 `retimedVideoSample(`（至少兩處：換段首幀與心跳），且「本體含 `shouldEmitVideoHeartbeat(` 的函式」或「呼叫該函式的函式」之中，至少一個的本體出現 `.idle`（心跳只由 idle sample 驅動）。行為（`design.md §7.2`〈當機〉）：在錄製期間收到 `idle` 的 `.screen` sample（PTS 有效）時，若距目前段落最後一個已寫入的視訊 PTS ≥ 1 秒，錄製器應把最後一個 complete 幀以該 idle sample 的 PTS 重新打戳寫進目前段落（走一般的換段與分流），且**不得**把重送的幀當成新的「最後一個 complete 幀」。 | D22；`t6-rca-ABE.md`〈E〉（合成重現：靜止畫面讀不到 fragment；每 1 秒重送最後一幀 → 20.06 秒內讀得到） | `swift:SegmentsTests.swift::testShouldEmitVideoHeartbeat`；`test_static_rules.py::test_video_heartbeat_on_idle`；人工 §4.8.4 |

### 4.5 錄製中監看

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.5.1 | 當系統聲音或麥克風任一路連續 15 秒 < -60 dBFS 時，錄製器應在 `warnings[]` 各自加入 `silence_system` 或 `silence_mic`，同一段靜音只告警一次。 | `req:199` | `swift:DetectorsTests.swift::testSilenceDetector15s` |
| 4.5.2 | 當抽樣幀非黑比例連續 5 秒 < 0.01 時，錄製器應開一個黑畫面區間並在恢復時關閉，區間寫入 `manifest.json.blackIntervals`；錄製行為不得改變（不得改錄整個螢幕）。 | `req:189-191` | `swift:DetectorsTests.swift::testBlackDetector5s`、`::testNonBlackRatio` |
| 4.5.3 | 當 `.screen` 連續 5 秒只收到 `suspended` 時，錄製器應在 `warnings[]` 加入 `suspended`。 | `req:293` | `swift:DetectorsTests.swift::testSuspendedDetector`；人工 §4.10.3 |
| 4.5.4 | 當系統預設輸入或輸出裝置改變時，錄製器應在 `record.meta.json.deviceEvents` 追加一筆 `{t, kind, from, to}`（含 `uid`、`name`、`transport`）。 | `req:199`、`req:271` | `swift:RecordsTests.swift::testMetaJSONKeys`；人工 §4.9.1 |
| 4.5.5 | 若錄製中目標磁碟可用空間 < 2 GB（2,000,000,000 bytes），則錄製器應優雅停止並跑 finalize，`record.status.json.code` 應為 5、訊息說明原因。 | `req:199` | 人工（以小容量 disk image 為目標根目錄）；`test_record_sh.py::test_stop_reports_code_5`（替身） |
| 4.5.6 | `stop` 結束後，`record stop` 應列出黑畫面區間（mm:ss–mm:ss）與各類告警次數。 | `req:191` | `test_record_sh.py::test_stop_prints_black_intervals` |
| 4.5.7 | 在錄製期間，錄製器應把兩路的 0.5 秒時段峰值寫進 `manifest.json.levels`（§3.2）；沒有收到任何緩衝的時段應記為 `null`，不得被略過。 | D6、D10；`design.md §7.5` | `swift:AudioLevelTests.swift::testPeakWindowEmptyWindowIsNegInf`；`e2e_check.py` |
| 4.5.8 | `rmsDBFS(sampleBuffer:)` 與 `audioFormat(of:)` 對 16 kHz 單聲道 Int16、24 kHz 雙聲道交錯 Float32、48 kHz 雙聲道非交錯 Float32 三種緩衝都應回正確值；`PeakWindow` 在同一串 feed 中途改變取樣率時，時段邊界應只依 `t` 決定；`SilenceDetector` 不得因格式改變而觸發。 | D6；`design.md §7.5` | `swift:AudioLevelTests.swift::testFormatsAcrossSampleRates`、`::testPeakWindowIgnoresSampleRateChange`；`swift:DetectorsTests.swift::testSilenceNotTriggeredByFormatChange` |
| 4.5.9 | **錄製中的磁碟檢查每次都讀新值（t6 第三輪，缺陷 L）**：`PreflightRunner.availableBytes(_:)` 每次呼叫都應取得當下的可用空間，不得沿用 Foundation 對同一個 `URL` 物件快取的 `resourceValues`——實作應在讀取前以路徑**新建** `URL`（`URL(fileURLWithPath:)`）或對要讀的 `URL` 呼叫 `removeAllCachedResourceValues()`；`volumeAvailableCapacityForImportantUsage` ≤ 0 時退回 `volumeAvailableCapacity` 的既有邏輯不變（sparse image 上前者回 0）。錄製中每 30 秒的檢查（`RecordingSession` 的磁碟監看）在可用空間 < 2 GB 後的下一次檢查就應觸發 §4.5.5 的優雅停止。 | 缺陷 L（`t6-results.md`「t6 第二輪 7」§4.5.5：35 GB sparse image 開錄後填到剩 1.71 GB，等 90 秒以上沒有停止；離線重現：同一 URL 寫入 300 MB 後仍回舊值，`removeAllCachedResourceValues()` 或新建 URL 才更新）；§6 第 67 條 | `test_static_rules.py::test_available_bytes_not_cached`（`availableBytes` 函式本體應含 `removeAllCachedResourceValues` 或 `URL(fileURLWithPath:`）；人工 §4.5.5 重測（sparse image 為根，錄製中填到 < 2 GB，60 秒內應停止、`code` 5） |

### 4.6 停止與 finalize

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.6.1 | finalize 完成後，`錄音/` 第一層應恰好一個音源檔（不計 `meeting.json` 與 `tracks/`）。 | `req:263` | `tests/record/test_finalize.py::test_exactly_one_audio_file`；`e2e_check.py` |
| 4.6.2 | 該音源檔應為 16000 Hz、1 channel 的 wav，檔名為 `<場次名> <YYYY-MM-DD HH.MM.SS>.wav` 且能被 `bin/_scaffold.py` 的 `TS_RE` 比對到。 | `req:137`、`req:157`、`req:265` | `test_finalize.py::test_wav_format_and_name` |
| 4.6.3 | `影片/<場次名> <YYYY-MM-DD HH.MM.SS>.mov` 的影片軌與音訊軌 duration（`ffprobe` stream 層）差應 < 100 ms。 | `req:267`；D7；`adr/adr-video-tail-pad.md` | `test_finalize.py::test_video_audio_duration_within_100ms`（合成素材影片軌刻意短 2 秒）；`e2e_check.py` |
| 4.6.4 | `錄音/meeting.json` 的 key 集合應等於 `bin/_scaffold.py` 寫入的 7 個 key（測試以 `ast` 解析該檔取得，不另抄清單），且 `expectedSpeakers` 為 `null`。 | `req:269`；§3.6 | `test_finalize.py::test_meeting_json_keys_match_scaffold` |
| 4.6.5 | 在 finalize 期間，`錄音/` 第一層不應出現任何音源副檔名的檔；wav 應以同一檔案系統內的 rename 一次出現。 | intent §3 競態 | `tests/record/test_concurrency.py::test_finalizing_session_not_listed`（`MH_FFMPEG` 慢速替身，期間跑 `meeting.sh status`） |
| 4.6.6 | 當 `record finish <場次>` 對已完成的場次再跑一次時，應回 0、印「已完成」，且所有輸出檔的 mtime 與內容不變。 | `req:218`、`req:275` | `test_finalize.py::test_idempotent_second_run` |
| 4.6.7 | finalize 應保留 `tracks/` 全部 `seg-*.mov`、`manifest.json`、`record.meta.json`，不刪任何段落；只清掉自己在 `.finalize/` 產生的暫存。 | `design.md §5 Q7` | `test_finalize.py::test_tracks_preserved` |
| 4.6.8 | finalize 應把 `gapStats`、各段 `audioDuration`、`outputCanvas`、`outputVideoBitrate` 寫回 `manifest.json` 且保留其他鍵，並在 `.pipeline-state.json` 記 `record: done`。 | `req:268` | `test_finalize.py::test_manifest_gapstats_written` |
| 4.6.9 | 若某段完全讀不到可解碼的封包（例如沒有 moov 的非 fragment 檔），則 finalize 應略過該段並在輸出中列出，其餘段照常完成；**D20**：讀得到部分 fragment 的段落不得略過（§4.6.15）。 | `req:275`（D3）；D20 | `test_finalize.py::test_skips_unreadable_segment` |
| 4.6.10 | 當各段寬高不同時，`影片/*.mov` 的寬高應等於 (各段寬最大值, 各段高最大值)，各段畫面不縮放、置中補黑邊（以合成段落中心點顏色與四角黑邊抽樣驗證）；輸出影片應為 H.264 high profile、位元率 ≥ 各段實測影片位元率最大值，且相鄰影格最小間隔不小於輸入（不改 fps）；`ffmpeg -v error -i <輸出> -f null -` 不得有任何錯誤輸出。 | D7、D8；`design.md §7.4` | `test_finalize.py::test_mixed_sizes_padded_not_scaled`、`::test_reencode_quality_and_fps_preserved` |
| 4.6.11 | 若某段沒有 video stream，則 finalize 應以前一段最後一幀補足該段長度的影片（第一段即缺時以黑畫面），輸出影片軌仍應涵蓋全程（§4.6.3 成立）。 | §4.4.4；`design.md §7.4` | `test_finalize.py::test_segment_without_video_filled` |
| 4.6.12 | 當各段音訊取樣率或聲道數不同（例如 48 kHz 雙聲道與 16 kHz 單聲道）時，finalize 應統一成 48 kHz 雙聲道後串接（**t6 第三輪，缺陷 J**：各段正規化成 PCM、串接後才一次編成 AAC，`design.md §7.4` 第 3、4 步），輸出音訊軌應為 AAC，長度應等於各段音訊長度總和（容許每段 50 ms）。 | D6；`design.md §7.4`、`§7.5` | `test_finalize.py::test_mixed_audio_formats_concat` |
| 4.6.13 | **兩條音軌混成一軌（D20）**：當段落有兩條音軌（系統聲音、麥克風）時，`影片/*.mov` 應恰有一條音軌、`錄音/*.wav` 為單聲道，兩者都同時含兩條音軌的內容且**等權**（不做 1/2 衰減）：以合成段落（影片＋音軌 0：440 Hz 正弦 -20 dBFS 雙聲道 48 kHz＋音軌 1：1000 Hz 正弦 -20 dBFS 單聲道 48 kHz）驗，輸出 wav 經 440 Hz 與 1000 Hz 帶通後各自的 RMS 都應在 -20 dBFS ± 3 dB 內、整體峰值 ≤ -1 dBFS（+0.1 dB 容差）；只有一條音軌的段落（D20 之前的段落）照既有 §4.6.1–4.6.12 的合成素材照常通過。 | D20（「混成一軌」的使用者決定不變，混音改在 finalize） | `test_finalize.py::test_two_audio_tracks_mixed`；既有 `test_finalize.py` 全部 |
| 4.6.14 | **先逐段正規化時間戳再串接（D20 一併修，t6 缺陷 3）**：當段落具有實機 SCK 段落的時間戳特性時，finalize 應回 0，且 (i) `影片/*.mov` 每條軌的封包 dts 嚴格遞增；(ii) `ffmpeg -v error -i <輸出> -enc_time_base demux -f null -` 沒有任何錯誤輸出；(iii) 輸出影格數 ≥ 各段影格數總和減去完全相同 PTS 的重複影格數（不得以丟幀換取遞增）；(iv) 相鄰影格間隔 < 1 ms 的對數為 0；(v) §4.6.3 成立；(vi) 段內影片晚於音訊開始時，段內的閃白與嗶聲在輸出中的時間差 < 100 ms（原點平移不得破壞段內音影對齊）。**合成素材**（不放真實錄音；spec-author 已在 repo 外驗證配方 (A) 在 `HEAD`（`09e6f05`）的 finalize 上兩段即回 5、stderr 含 `non monotonically increasing dts`）：(A) 兩段以上，每段 `testsrc2` 10 fps 經 `setpts='(N*60+mod(N*37\,23))/600/TB'` 造出不規則影格間隔，`-c:v libx264 -profile:v high -bf 2 -fps_mode passthrough -enc_time_base 1/600 -video_track_timescale 600`，配 48 kHz AAC 音訊——對應實機的 VFR、`time_base=1/600`、`has_b_frames=2`；(B) 一段以 `e2e_check.py` 的同步測試源（`sync_source_graph`）產生閃白與嗶聲，影片以 `trim=start=0.2`（不重設 PTS）讓影片晚 0.2 秒開始、音訊以負的 `start_time` 寫入（例：音訊 `asetpts=PTS-0.021/TB` 並以 `-avoid_negative_ts disabled` 寫成 edit list），用來驗 (vi)（**t6 第二輪補充**：ffmpeg 7 的 mov muxer 把負時間戳寫成 edit list，`ffprobe` 的 stream `start_time` 仍是 0；測試以「第一個音訊封包的 `pts` < 0」認定素材確實以負時間戳寫入，m1 已照此實作）；(B) 不要求在修正前失敗。tester 若 (A) 在 `HEAD` 上沒有重現 rc 5，應改用 t6 保留的實機段落（`~/.meeting-harness/e2e/` 下該場次，只在本機、不進 repo）以 `ffprobe` 量出各軌 `start_time`、`time_base`、`has_b_frames`、最小影格間隔，把數字記在 run 目錄後依特徵調整配方；仍造不出就以 `needs_decision` 回報。 | t6 實機（`t6-results.md`「缺陷 3」）；根因見 `design.md §7.4` 第 3 步 | `test_finalize.py::test_irregular_timestamps_concat`；人工（§4.6.16） |
| 4.6.15 | **被中斷的 fragment 段落（D20）**：當某段是寫到一半被中斷的 fragment 檔（stream 層 `duration` 可能高報）時，finalize 應納入它可讀的部分，該段 `audioDuration` 應等於最後一個可解碼音訊封包的結束時間（± 0.1 秒），輸出音訊長度應等於各段 `audioDuration` 總和（每段容許 50 ms）。合成素材：10 秒段落以 `-movflags +frag_keyframe+empty_moov -frag_duration 2000000`（`-g 30`）寫成 fragment 檔後截掉後 40% 位元組；spec-author 在 repo 外驗證過此素材 `ffprobe` 回報 7.0 秒、最後一個音訊封包約 6.0 秒，`HEAD` 的 finalize 以 7.0 秒計。 | D20；`design.md §7.2`〈當機〉、`§7.4` 第 1 步 | `test_finalize.py::test_truncated_fragment_segment_used` |
| 4.6.16 | **實機段落回歸（D20）**：對 t6 期間保留、先前 finalize 失敗的 4 段場次（`SCRecordingOutput` 段落、單一混音音軌）執行 `meeting record finish <場次>` 應回 0，`e2e_check.py <場次>` 的 `video_format`、`video_covers_audio`、`one_audio_file`、`wav` 應 PASS（`gap` 可因當時的 10 秒空隙而 FAIL，只記錄）。 | t6 實機；§4.6.14 | 人工（t6 中途修正輪後；場次只在本機，路徑不寫進 repo） |
| 4.6.17 | **尾幀不得被編得過長（t6 第二輪，缺陷 B）**：當段落的影片是 VFR、`time_base=1/600`、`r_frame_rate` 為 600 而平均影格率約 12 fps、最後一幀距段落結束 < 0.01 秒（不需補尾）時，finalize 應回 0，且輸出影片軌 stream 層 `duration` ≤ 段落長＋1/600 秒、與音訊軌差 < 100 ms（§4.6.3）。**段落長**＝該段各軌 stream 層 `start_time + duration` 的最大值。**合成素材**（spec-author 已在 repo 外以 `HEAD`（`bae4c6c`）的 finalize 複本驗證：回 5「正規化後 video 軌長 15.278 與段落長 15.199 不符」；照 `design.md §7.4` 第 3、4 步的修法後回 0，影片 15.197／音訊 15.220 秒）：單段場次，`testsrc2=size=320x240:rate=600` 經 `select='not(mod(n\,97))+not(mod(n\,101))+eq(n\,9114)'`（最後一幀 PTS 15.190）、`-fps_mode passthrough -c:v libx264 -pix_fmt yuv420p -bf 0 -video_track_timescale 600`，兩條 AAC 音軌（440 Hz 正弦雙聲道、1000 Hz 正弦單聲道，48 kHz），`-t 15.1988`（段落長 15.199）。缺陷只在 `h264_videotoolbox` 出現：機器上沒有該編碼器時本測試 `skipTest` 並寫明原因。 | t6 缺陷 B（1650 場次 seg-0005：rc 5、15.284 對 15.199）；`t6-rca-ABE.md`〈B〉 | `test_finalize.py::test_tail_frame_not_overlong` |
| 4.6.18 | **稀疏 VFR 的最後一段（t6 第二輪，缺陷 F）**：當最後一段的影片只有少數幾幀、`r_frame_rate` 很低（例 4/3）、影片比音訊早很多結束時，finalize 應回 0，§4.6.3 成立（輸出影片軌與音訊軌 stream 層 `duration` 差 < 100 ms），輸出影片軌 `duration` 應落在 [Σ段落長 − 0.05, Σ段落長＋1/600] 秒內，且輸出影格數不少於各段影格數總和（不得以丟幀換長度）。**合成素材**（spec-author 已在 repo 外驗證：`HEAD` 的 finalize 回 0 但影片 24.500／音訊 25.021、差 521 ms；照 `design.md §7.4` 修法後 24.995／25.021、差 26 ms）：兩段；seg-0001＝`testsrc2` 10 fps 5 秒＋兩條 AAC 5 秒（音軌同 §4.6.17）；seg-0002＝`testsrc2=size=320x240:rate=4/3` 只取 8 幀（`-frames:v 8`，libx264 `-bf 0`、`-video_track_timescale 600`），另以 20 秒的兩條 AAC 音軌 `-c copy` mux 成同一檔（段落長 20.0）。需要 `h264_videotoolbox`（同 §4.6.17）。 | t6 缺陷 F（2254 場次：影片 307.060／音訊 307.456 秒、差 396 ms）；根因見 `design.md §7.4` 第 3 步 | `test_finalize.py::test_sparse_vfr_last_segment_covers_audio`；人工（t6 第二輪重測：2254、1650 場次重新收尾） |
| 4.6.19 | **`gapStats` 與 `e2e_check.py` 的 `gap` 用同一把尺（t6 第二輪，缺陷 F2）**：`e2e_check.py` 應提供 `segment_audio_duration(path)`，以 §3.2 的 `audioDuration` 算法（封包算、略過 `D`／`C` 旗標、起點取 min(stream `start_time`, 第一個可解碼封包 pts)、各音軌取最大）量各段長度，`gap` 判準改用它；對下列合成段落，它與 `bin/_record_finalize.py` 的 `analyze(path)["audioDuration"]` 差應 ≤ 0.001 秒：(1) 影片從 0 開始、兩條音軌分別晚 0.2 與 0.3 秒開始（`adelay`；對應實機第一段音訊晚於影片）；(2) §4.6.15 的截斷 fragment 段落；(3) 只有一條音軌的段落。`gap` 的備註不得再因定義不同出現「與實測不符」。 | t6 第二輪調查：2254、1650 場次複本以現行 finalize 重新收尾後，前一版 `e2e_check.py` 以 stream 層 `duration` 量得 max 0.181／0.117 秒，finalize 寫回 0.224／0.181 秒，`gap` 因「與實測不符」FAIL；`design.md §7.4` 缺陷 F2 | `test_e2e_check.py::test_gap_uses_finalize_audio_duration` |
| 4.6.20 | **串接不得讓音訊逐段延後（t6 第三輪，缺陷 J）**：當場次有 ≥ 3 段、各段長度不是 1024 樣本（48 kHz）的整數倍、且第一段的音訊比影片晚開始時，finalize 應回 0，且 (i) `影片/*.mov` 音訊軌**實際解碼出的樣本數** ÷ 48000 與該軌 stream 層 `duration` 差 ≤ 25 ms（一個 AAC 封包；前一版每個邊界多出一個 AAC priming 封包與前一段最後一個封包的補零，邊界越多差越大）；(ii) `錄音/*.wav` 長度與 `影片/*.mov` 音訊軌 stream 層 `duration` 差 ≤ 25 ms；(iii) 以 §4.9.3 的量法分段量，`影片/*.mov` 中每一段時距內「嗶聲 − 閃白」的中位數與該段原始 `seg-*.mov`（系統聲音軌）的中位數差 ≤ 10 ms；(iv) `.finalize/norm-*.mov` 的音訊軌應為 PCM（`pcm_s16le`），串接命令不得對音訊用 `-c copy`／`-c:a copy`（靜態檢查）。合成素材（離線可重現、不需錄製器）：每 2 秒閃白 0.1 秒的影片＋同時 1 kHz 嗶聲的系統聲音軌（雙聲道 AAC）＋低音量雜訊的麥克風軌（單聲道 AAC），4 段長 10.017／3.3／7.0／5.013 秒（內容的時間相位依段落起點接續），第一段系統聲音前 50 ms 為靜音。 | 缺陷 J（`t6-results.md`「t6 第二輪重測」第 6 項：最終影片 0–60 s 中位 29 ms、60–72 s 69 ms、72 s 後 79 ms，段內原始 19–35 ms）；`design.md §7.4`〈缺陷 J〉；§6 第 65 條 | `test_finalize.py::test_concat_no_audio_drift`；`test_static_rules.py::test_finalize_concat_reencodes_audio_once` |
| 4.6.21 | **實機段落回歸（t6 第三輪）**：以 t6 保留場次的段落複本（`~/.meeting-harness/` 下只讀、複製到 scratchpad 處理）用修後的 `_record_finalize.py` 重新收尾：t6r2-HFP2 場次每段時距的「嗶聲 − 閃白」中位數與段內原始差 ≤ 10 ms；t6r2-HFP2、2254、1650、t6r2-AE、t6r2-E2、t6r2-E3 六場的 `video_covers_audio`、`gap` 都 PASS，其餘 `e2e_check.py --segment-writer` 的結果與修前相同（已知的 `no_aggregate`、`segment_finished` FAIL 不變）；§4.6.20 (i) 在六場都成立。 | 缺陷 J；spec-author 以複本預先驗證（`design.md §7.4`〈缺陷 J〉的數字） | 人工（主 session，離線、不需使用者；複本用完刪） |

### 4.7 並發安全

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.7.1 | 在錄製進行中，另一個終端機執行 `meeting prep <根>` 時，該場次不應被列為場次。 | `req:277` | 人工；`test_concurrency.py::test_recording_session_not_listed` |
| 4.7.2 | 在 finalize 進行中，同上應成立。 | intent §2、§3 | `test_concurrency.py::test_finalizing_session_not_listed` |

### 4.8 crash 救援（D3 修訂）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.8.1 | 錄 2 分鐘後 `kill -9` 錄製實例，`meeting record status` 應回 5 並提示 `record finish`；`meeting record finish <場次>` 應回 0，產出的 wav 長度應 ≥ 60 秒且 ≤（開錄到 `kill -9` 的秒數＋1 秒）（**t6 第三輪**：上限原為 125 秒，是 D3「最後一段 60 秒會丟」時代的假設；D20＋影片心跳後只丟 < 10 秒，t6 實測開錄後 133 秒 `kill -9` 救回 130.1 秒。下限不變）。 | `req:275`（D3 修訂）；§6 第 70 條 | 人工；`e2e_check.py --expect-min 60 --expect-max <開錄到 kill -9 的秒數＋1>`；`test_e2e_check.py::test_expect_duration_check` |
| 4.8.2 | 對同一場次再跑一次 `record finish` 應符合 §4.6.6。 | `req:275` | 同 §4.6.6 |
| 4.8.3 | `meeting-record` 的 SKILL.md 與 `record finish` 的說明應寫明「最後一段未收尾的 1 分鐘會丟」。 | `req:275`（D3） | `tests/record/test_docs.py::test_crash_loss_documented` |
| 4.8.4 | **當機最多丟 1 段（D20）**：錄 90 秒以上後 `kill -9` 錄製實例，`meeting record finish <場次>` 應回 0，產出的 wav 長度應 ≥（開錄到 `kill -9` 的秒數 − 21 秒）；被中斷的那一段（與當時若有正在收尾的前一段）應被 finalize 納入而非略過（finalize 輸出不得把它列為「略過無法讀取的段落」）。21 秒＝兩個 writer 各最多丟一個未滿 10 秒的 fragment，加 1 秒量測容差。不過時退回 `design.md §7.2`〈當機〉所述的退化保證並以 `needs_decision` 回報。**t6 第二輪（D22）**：t6 第一次實測不過——開錄約 104 秒時 `kill -9`，seg-0002.mov（已寫約 44 秒）只有 `ftyp`／`wide`／`mdat`、沒有 `moov`／`moof`，finalize 略過它，wav 60.03 秒 < 期望 83 秒；根因是靜止視窗只送 `idle` sample、影片軌不前進，`AVAssetWriter` 要所有軌都越過 fragment 邊界才寫 fragment（`t6-rca-ABE.md`〈E〉）。修法為影片心跳（§4.4.10、`design.md §7.2`〈當機〉），**判準 21 秒不變**。重測時會議視窗保持靜止（最壞情況）、會議 app 有聲音；另記一次「會議 app 沒有聲音」的結果（只記錄，§7 疑慮 27）。修法後仍不過，依 D22 以 `needs_decision` 回報，選項之一是把本條改為「當機最多丟 1 段（60 秒）」。 | D3；D20；D22 | 人工；`e2e_check.py --expect-min <秒>` |

### 4.9 裝置切換與藍牙耳機（D6、D10）

**test 段必驗**：§4.9.1–4.9.3 不得標 `not_verifiable`。耳機用使用者配對過的 XROUND FORGE NC 或 XROUND FORGE PRO（至少一副，報告記型號）；需要使用者在場操作。下列「中斷時間」的定義：在該事件時點前後 10 秒內，該路 `manifest.json.levels` 連續 < -60 dBFS（含 `null`）的最長區間長度；混音音軌則以 `影片/*.mov` 音訊 0.1 秒窗 RMS 計。量測期間由操作者確保兩路都有持續聲音（系統聲音：持續有聲的影片或 `e2e_check.py --print-sync-source` 印出的同步測試源；麥克風：使用者持續說話）。中斷容許值 3 秒（D10）與錄製中「連續 15 秒靜音才告警」（§4.5.1）是兩回事，兩者並存。

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.9.1 | **(b) 錄製中切換**：錄 3 分鐘（第 1 分鐘內建喇叭／麥克風、第 2 分鐘切藍牙耳機、第 3 分鐘切回），`record.meta.json.deviceEvents` 應記到至少兩個切換時點（`transport` 由 `builtIn` 變 `bluetooth` 再變回）；每次切換的系統聲音路、麥克風路與混音音軌中斷時間都應 < 3 秒；其餘時間兩路都**不得連續 ≥ 3 秒**（6 個以上相鄰 0.5 秒時段）≤ -60 dBFS 或沒有緩衝（**t6 第三輪，缺陷 K**：前一版「其餘時間每個時段峰值都 > -60 dBFS」對自然說話的停頓過嚴；3 秒與切換中斷的容許值同一把尺）。 | `req:271`；D6 (b)；D10 | 人工；`e2e_check.py --device-switch`；`test_e2e_check.py::test_device_switch_check`（2 秒中斷判 PASS、4 秒判 FAIL；t6 第三輪：切換以外有 2.5 秒的低音量停頓判 PASS、3 秒判 FAIL） |
| 4.9.2 | **(a) 全程藍牙**：開錄前就把藍牙耳機設為輸入與輸出、全程不切換錄一場（≥ 3 分鐘，含遠端聲音與自己說話），`record.meta.json.devices` 的輸入與輸出 `transport` 都應為 `bluetooth`（或 `bluetoothLE`）；`e2e_check.py <場次>` 應回 0；使用者聽 `影片/*.mov` 應記下遠端與自己聲音各至少一個時間點。 | D6 (a)；`req:266` | 人工；`e2e_check.py --all-bluetooth` |
| 4.9.3 | **(c) HFP 取樣率中途改變**：以藍牙耳機只當輸出開錄、播放同步測試源，錄製中途把輸入切到同一副耳機的麥克風（觸發 HFP）並持續說話，再錄 ≥ 60 秒：`record.meta.json.audioFormatEvents` 應至少有一筆 `sampleRate` 改變（沒有則判「情境未觸發」重測，不得判 PASS）；格式變更後兩路中斷時間應 < 3 秒，且之後兩路都**不得連續 ≥ 3 秒** ≤ -60 dBFS 或沒有緩衝（t6 第三輪，缺陷 K，同 §4.9.1）；該區間 `warnings[]` 不得出現 `silence_system`／`silence_mic`；finalize 後 §4.6.3 成立，且同步測試源的每個閃白與嗶聲在 `影片/*.mov` 中的時間差都應 < 100 ms。**D20**：格式變更時錄製器應提前換段——`audioFormatEvents` 中每一筆 `sampleRate` 改變，都應有一個段落邊界的 `startedAt` 與它的 `t` 相差 < 0.5 秒（同一路 1 秒內的連續變更只要求第一筆）；該場不得出現 `segment_write_failed`。**t6 第三輪（缺陷 K）sync 的量法**：閃白＝`影片/*.mov` 每幀縮成 32×18 灰階、平均亮度由 ≤ 128 變 > 128 的那一幀的 PTS；嗶聲＝`影片/*.mov` 音訊軌先過兩次 1 kHz 帶通（`bandpass=f=1000:width_type=h:w=100` 串兩次，以 48 kHz 單聲道解碼），算 1 ms 窗的 RMS 包絡，對每個閃白在 [閃白 − 0.3 秒, 閃白 + 0.3 秒] 內取包絡最大值，**第一個 ≥ 最大值 50% 的窗**為該閃白對應的嗶聲起點；每個閃白的「嗶聲 − 閃白」都應 < 100 ms（絕對值），且閃白、嗶聲各至少 3 次。前一版以全頻 RMS、全片單一門檻找嗶聲，持續說話會產生假嗶聲（t6r2-HFP2：閃白 64、嗶聲 106，最大差 385 ms）；新量法在同一場的修後影片最大 81 ms、修前 140 ms（擋得到缺陷 J）。濾波器群延遲約 5 ms，屬量測偏差、不另扣。 | D6 (c)；D10；`req:267`；D20（`design.md §7.5` 落盤列） | 人工；`e2e_check.py --hfp --sync`；提前換段由 `e2e_check.py --hfp --segment-writer` 的 `format_rotation` 查（只在兩個旗標同時給時才跑，既有 `--hfp` 判準不變）；`test_hfp_and_sync_check`（t6 第三輪：同步素材疊上會在 1 kHz 附近有能量的雜訊／語音替身時仍判 PASS；嗶聲晚 150 ms 判 FAIL；格式變更後有 2.5 秒低音量停頓判 PASS、3 秒判 FAIL）、`test_e2e_check.py::test_format_rotation_check` |
| 4.9.4 | 錄製器與 `record.sh` 應不改變使用者的預設輸入／輸出裝置、不依賴 BlackHole 或多重輸出裝置：`tools/MeetingRecorder/Sources/` 與 `bin/record.sh` 不得出現 `AudioObjectSetPropertyData` 與 `BlackHole`；§4.9.1–4.9.3 的操作過程中使用者不需開啟「音訊 MIDI 設定」（記入報告），且各場 `devices` 的 `transport` 不得為 `aggregate`。 | intent §2；`req:130`、`req:271` | `test_static_rules.py::test_no_default_device_write_in_sources`（只掃 `tools/MeetingRecorder/Sources/`）、`::test_no_default_device_write_in_record_sh`（只掃 `bin/record.sh`；檔案不存在時應**失敗**而非跳過，避免空檔案假綠）；人工；`e2e_check.py` |

### 4.10 端到端

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.10.1 | 錄一場 3 分鐘假會議（Teams 自我通話＋播一段有聲影片＋自己說話）並 `record stop` 後，§4.3.1–4.3.2、§4.4.3、§4.6.1–4.6.4 應全部成立。 | `req:261-269` | 人工；`e2e_check.py` |
| 4.10.2 | 同一場中，會議視窗所在的 Space 被切走至少 30 秒時，該區間的 `影片/*.mov` 抽幀非黑比例應 ≥ 0.5（Teams 通話中）。 | intent Q9；`PROBE-REPORT.md:35` | 人工；`e2e_check.py --space-interval mm:ss-mm:ss`；`test_e2e_check.py::test_space_interval_check` |
| 4.10.3 | 同一場中，把會議視窗最小化 10 秒，`warnings[]` 應出現 `suspended`；Mission Control 只記觀察結果。native 全螢幕：Chrome 會議頁（M+ Meet）進 native 全螢幕後切到別的 Space 已實測可擷取、不黑（`wfd:17`、`wfd:40`），t6 以 §4.15.16 驗「選得到、標得出、錄得到」；Teams 原生 app 的 native 全螢幕只記觀察結果。SKILL.md 不得寫「會議視窗不要用 native 全螢幕」這類一律迴避的說法；若 t6 觀察到某個 app 的 native 全螢幕擷取失敗，test 段把該 app 的限制補進 SKILL.md（只寫觀察到的那個 app）。 | intent Q9；`req:249`；D15；第六修正輪 skeptic 問題 1 | 人工（t6 驗收項）；`test_docs.py::test_meeting_tab_marking_documented`（不得含「不要用 native 全螢幕」） |
| 4.10.4 | **混音音軌裡應同時聽得到遠端與自己**：使用者聽 `影片/*.mov`，記下遠端聲音與自己聲音各至少一個時間點寫進 test 段報告。 | `req:266` | 人工（唯一證據，RMS 不能取代） |

### 4.11 觸發層（第 2 階段）與 menu bar 設計審查（D12）

§4.11.5–4.11.8 是 `dev-design-reviewer` 的對照依據（macOS Human Interface Guidelines 的 menu bar extra 慣例，`design.md §8.2`）；審查材料為 t6 截的三態圖示（淺色、深色 menu bar 各一）與三態下展開的選單截圖，只截 menu bar 區域。

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.11.1 | 當以 `open -n -a MeetingRecorder --args quick-start` 啟動且 `record.defaults.json` 存在、`buildWindowRows` 的結果中恰好一個 ★ 列（§3.8.2，`meeting` 非 null）時，錄製器應以預設值開錄；否則應以通知說明原因並以 code 2（無預設值）或 3（★ 不是恰好一個）結束，不得猜選視窗；code 3 且有 Chrome 列的 `meetingCheck` 為 `not_authorized`／`not_determined` 時，通知應另說明「Chrome 會議分頁要允許 Apple Events 才標得出來」。quick-start 不得跳 Apple Events 授權框（§3.8.4）。 | `req:255`；`design.md §8`；D16 | `swift:TriggerTests.swift::testQuickStartDecision`；人工（t6） |
| 4.11.2 | menu bar 實例應以三種狀態（待機、錄製中、告警）表示錄製狀態，狀態取自 `record.status.json` 與 `kill -0 record.pid`，對映規則依 §3.4.1 全表（M1–M10 與 M6a；`preflight_failed` 歸告警態並顯示訊息首行）；只有告警類 warning 會轉告警態，`device_change`、`audio_format_change` 不會；選單「停止錄製」應送 SIGTERM 給 `record.pid`。 | `req:255`、`req:191` | `swift:TriggerTests.swift::testMenuBarStateMapping`、`::testRecordOnlyWarningsDoNotAlert`；人工（t6） |
| 4.11.3 | 全域快捷鍵（⌃⌥⌘R）應以 Carbon `RegisterEventHotKey` 註冊；`tools/MeetingRecorder/Sources/` 中不得出現 `addGlobalMonitorForEvents`。註冊失敗（`HotKey(...)` 回 nil，例如組合被別的 app 佔用）時，menu bar 實例應照常運作，並在 `record.log`（append）寫一行含「快捷鍵」與「註冊失敗」的說明（例「快捷鍵 ⌃⌥⌘R 註冊失敗（可能被別的 app 佔用），請改用選單或 Shortcuts 捷徑」）。 | `req:255`；D18（設計審查 N-1） | `tests/record/test_static_rules.py::test_no_global_event_monitor`、`::test_hotkey_uses_carbon`、`::test_hotkey_failure_logged`；人工按快捷鍵（t6） |
| 4.11.4 | SKILL.md 應寫明 Shortcuts 捷徑的建立步驟，捷徑內容僅為 `open -n -a MeetingRecorder --args quick-start` 一行。 | `req:255` | `test_docs.py::test_shortcuts_instruction` |
| 4.11.5 | **圖示**：三態圖示應分別為 SF Symbols `record.circle`、`record.circle.fill`、`exclamationmark.triangle.fill`，以 template image 呈現（淺色與深色 menu bar 都清楚可見），三態以形狀即可區分、不只靠顏色；menu bar 上只放圖示、不放文字。 | HIG menu bar extra；D12；`req:191` | `swift:TriggerTests.swift::testSymbolNames`；`test_static_rules.py::test_menubar_uses_template_image`；設計審查 |
| 4.11.6 | **選單項**：選單應依序為不可點的狀態列、分隔線、「開始錄製（用上次的設定）」（選單上顯示快速鍵 ⌃⌥⌘R：`keyEquivalent` 為 `"r"`、`keyEquivalentModifierMask` 為 `[.control, .option, .command]`，與 §4.11.3 的全域快捷鍵同一組）、「停止錄製」、「打開場次資料夾」、分隔線（狀態列之後另有「複製完整訊息與補救指令」，只在失敗類狀態顯示，§6 第 73 條）、「結束 MeetingRecorder 選單」（⌘Q）；當下不能用的項目應灰掉而非隱藏。選單展開時按一次 ⌃⌥⌘R 應只送出一次 quick-start（選單快速鍵與 Carbon hot key 不得各觸發一次）。 | HIG menu bar extra；D12；D18（設計審查 N-1） | `swift:TriggerTests.swift::testMenuItemAvailability`；`test_static_rules.py::test_start_item_shows_hotkey`；設計審查；人工（t6：選單上看得到 ⌃⌥⌘R、選單展開時按一次只開一場） |
| 4.11.7 | **停止行為**：「停止錄製」只在 `phase=recording` 且 pid 活著時可點；點下後 1 秒內狀態列應含「收尾中…」，不論場次有沒有告警類 warning（無告警類＝§3.4.1 M10「收尾中…」；有告警類＝M6a「收尾中…（告警 N 則）」，D17）；`stopping`／`finalizing` 期間「停止錄製」應灰掉；完成後應送一則含場次路徑的通知；「結束 MeetingRecorder 選單」不得停止正在進行的錄製。 | D12；D17；`design.md §8.2` | `swift:TriggerTests.swift::testStopAvailabilityByPhase`、`::testMenuBarStateMapping`（M6a、M10 的 statusLine 含「收尾中…」）；人工（t6：有告警與無告警各按一次停止）；設計審查 |
| 4.11.8 | **可讀性**：status item 應設 `toolTip` 與 `accessibilityLabel`，內容等於 `MenuBarModel.accessibilityText`（§3.4：待機態＝`statusLine`，其餘狀態＝「MeetingRecorder：」＋`statusLine`；錄製中含 mm:ss 經過時間與場次名，告警含最新告警一句話）；`statusLine` 應為完整中文句子、不出現內部代碼（例如 `silence_mic`）。選單的狀態列（不可點）應以 `attributedTitle` 顯示 `truncatedStatusTitle(statusLine, limit: 40)`，前景色 `NSColor.labelColor`（不用系統的灰色），該選單項的 `toolTip` 等於完整的 `statusLine`。 | HIG menu bar extra（可及性）；D12；D18（設計審查 N-2、N-3） | `swift:TriggerTests.swift::testStatusLineHumanReadable`、`::testAccessibilityTextPrefix`、`::testTruncatedStatusTitle`；`test_static_rules.py::test_menubar_sets_accessibility_label`、`::test_status_title_uses_label_color`；設計審查 |
| 4.11.9 | **選單展開時照常更新**：選單展開期間，狀態列（含 M9 的經過時間）與選單項可用性應照常每秒更新：每秒 refresh 的 timer 應加入 `RunLoop.main` 的 `.common` mode（只排在 `.default` mode 的 timer 在選單展開時不會觸發），或另以 `NSMenuDelegate.menuWillOpen(_:)` 在開選單時立即 refresh；兩者都做亦可。 | HIG menu bar extra；D18（設計審查 SF-1） | `test_static_rules.py::test_menubar_refresh_while_menu_open`（`Sources/Trigger/MenuBar.swift` 含 `forMode: .common` 或 `menuWillOpen`）；人工（t6：錄製中打開選單停 5 秒，秒數有在走） |
| 4.11.10 | **單一實例**：當以 `--args menubar` 啟動、而 `<home>/menubar.lock`（`<home>` 同 `record.status.json` 所在目錄）已被另一個 menubar 實例以 `flock(LOCK_EX)` 持有時（`acquireMenuBarLock` 回 `.heldByOther`），新實例應在建立 `NSStatusItem` 與註冊快捷鍵之前結束、結束碼 0，並在 `record.log`（append）寫一行「已有 MeetingRecorder 選單在執行，本實例結束」；取得鎖（`.acquired`）的實例持有該 fd 到 process 結束（crash 時由系統釋放，不留殘鎖）；回 `.unavailable` 時照常啟動並在 `record.log` 寫一行原因（單一實例只防重複圖示，不得因此擋住 menu bar）。`quick-start`、`windows`、`diagnose-windows`、`preflight`、`start`、`probe` 不得讀寫 `menubar.lock`，也不得因 menubar 實例存在而改變行為。 | HIG menu bar extra（一個 app 只放一個）；D18（設計審查 SF-3） | `swift:TriggerTests.swift::testMenuBarLockSingleInstance`（暫存目錄：第一次 `.acquired`、第二次 `.heldByOther`、close 第一個 fd 後再取得為 `.acquired`；上層目錄不存在時會建立）；`test_static_rules.py::test_menubar_lock_only_in_menubar`（`menubar.lock` 與 `acquireMenuBarLock` 只出現在 `Sources/Core/Trigger.swift` 與 `Sources/Trigger/MenuBar.swift`）；人工（t6：連跑兩次 `open -n -a MeetingRecorder --args menubar`，menu bar 只有一個圖示、`record.log` 有那一行；第一個實例結束後再開可正常出現） |

### 4.12 skill 與文件

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.12.1 | `.claude/skills/meeting-record/SKILL.md` 應存在，frontmatter `name: meeting-record`，正文涵蓋：開錄、preflight 失敗的補救（含重啟）、stop、finish、資料擺法、`./record` 撞名時的兩種明確寫法。 | `req:220`；D11 | `test_docs.py::test_skill_exists_and_sections` |
| 4.12.2 | `.claude/skills/meeting-summary/SKILL.md` 的 frontmatter（第 1 行到第二個 `---`）應與 `main` 相同；正文應有一行指向 `meeting-record`。 | `req:222`；`research-code-contracts.md:30` | `test_docs.py::test_meeting_summary_frontmatter_unchanged` |
| 4.12.3 | `README.md` 的指令表應含 `record` 各列、結束碼說明應含 `4`／`5`、skill 表與重裝 for-loop 應含 `meeting-record`、目錄樹註解應寫 7 個 skill。 | `research-code-contracts.md:28-29` | `test_docs.py::test_readme_updated` |
| 4.12.4 | `bin/diarize.sh` 與 `bin/_merge_speakers.py` 應與 `main` 完全相同。 | `req:257` | `tests/record/test_regression.py::test_diarize_and_merge_untouched` |
| 4.12.5 | `~/.claude/skills/meeting-record` symlink 應指向本 repo 的 `.claude/skills/meeting-record`。 | `req:220` | 人工（主 session 在 deliver 閘門後建立，見 plan.md） |
| 4.12.6 | `.claude/skills/meeting-record/SKILL.md` 與 `README.md` 應：(a) 各含恰好一個 §2.4.5 格式的 `record-cli` 區塊，兩者 begin／end 之間逐位元組相同；(b) 各自 `parse_block` 的 `forms`、`form_flags`、`form_codes` 等於 `SURFACE` 的同名成分；(c) 區塊外都含 `--recorder` 與 `--yes`；(d) 逐行檢查（含區塊內）：先刪除該行所有反引號，再以正規式 `meeting(?:\.sh)? record(?: +(\S+))?` 找出每個出現處；群組 1（`record` 後的第一個字）存在、不含 `/`、且開頭有連續的 ASCII 小寫字母 `[a-z]+` 時，這段字母應是 `windows`、`preflight`、`stop`、`status`、`finish`、`help` 之一（以 `-`、`[`、`<`、`.`、`~`、`"`、`$` 或中文開頭的字，視為旗標、佔位符、路徑或說明文字而略過）；有任何出現處的行，以正規式 `--[a-z][a-z-]*` 取出的每個旗標名都應屬於 {`--window`、`--json`、`--recorder`、`--yes`、`--help`}（寫法旗標名 ∪ 層旗標 ∪ `help` 同義字；文件不得寫 spec 沒有的功能）。 | D13 | `test_docs.py::test_docs_cli_block_matches_spec` |
| 4.12.7 | 當 build 全部合併後，`parse_help(meeting.sh record help 的 stdout)` 的 `forms`、`form_flags`、`form_codes` 應分別等於兩份文件 `parse_block` 的同名成分（比較方式依 §2.4.4，失敗訊息列出差集）；`layer_flags` 不與區塊比（區塊不含層旗標），應等於 `SURFACE.layer_flags`；`codes` 應等於 `SURFACE.codes`。 | D13 | `test_docs.py::test_docs_cli_block_matches_help` |
| 4.12.8 | 當 build 全部合併後，以 §2.4.7 的參數組法與執行環境：(a) 對 SKILL.md 區塊 `form_flags` 的每一組（寫法，旗標），以及每個寫法各配一次層旗標 `--recorder`、`--yes`（共 3＋7×2＝17 次），stderr 不得含「未知的選項」；(b) 每個寫法加上 `--no-such-flag` 應回 2 且 stderr 含「未知的選項」（7 次）；(c) `{(c["form"], c["expect"]) for c in EXIT_CODE_CASES}` 應等於 SKILL.md 區塊的 `form_codes`（因此不含通則的 2，§2.4.1），且逐筆執行時實際結束碼等於 `expect`。 | D13；§2.2 | `test_docs.py::test_docs_flags_match_behavior`、`::test_docs_exit_codes_match_behavior` |
| 4.12.9 | SKILL.md 中出現的每個錄製器參數 `--args <子指令>`，都應是 `tools/MeetingRecorder/Sources/main.swift` dispatch 的一個 case（§3.5；含 D15 的 `diagnose-windows`）。 | D13；`req:255` | `test_docs.py::test_docs_app_args_exist_in_sources` |
| 4.12.10 | `.claude/skills/meeting-record/SKILL.md` 應寫明會議視窗標記（D16）：(a) 含「★ 會議（」與 §3.8.2 兩張表的全部服務名（M+ Meet、Google Meet、Teams、Zoom、Webex、騰訊會議）；(b) 含「Apple Events」與「選用」，並說明第一次會跳「允許控制 Google Chrome」、在哪裡改（「自動化」）；(c) 說明不授權的後果——含「不授權也能錄」，且說明 Chrome 視窗不會有 ★、quick-start 可能因此找不到唯一的會議視窗；(d) 說明只看作用中分頁（含「作用中分頁」）；(e) 含 `--args diagnose-windows` 的排錯指令；(f) 不得含「不要用 native 全螢幕」。README.md 的錄製段應有一行指向 SKILL.md 的這段說明（含「會議視窗標記」）。 | D16；D13（文件先寫，只寫 spec 定案的行為） | `test_docs.py::test_meeting_tab_marking_documented` |

### 4.13 迴歸與 verify

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.13.1 | `bash bin/_lint.sh` 應通過且檔數為 26。 | `req:280`；`bin/_lint.sh:32` | `test_regression.py::test_lint_passes_26_files` |
| 4.13.2 | 在沒有 `MeetingRecorder.app`（`MH_RECORDER_APP` 指向不存在路徑）的情況下，`bash bin/meeting.sh doctor` 應回 0，錄製器那一行以「◦」開頭；輸出中錄製器段不得出現「✗」。 | `rules.md:59`；`design.md §5 Q8` | `test_regression.py::test_doctor_green_without_recorder` |
| 4.13.3 | `meeting status <根>` 應列出 finalize 完成的新場次。 | `req:281` | `test_finalize.py::test_status_lists_finalized_session`；人工 |
| 4.13.4 | 對新場次跑 `meeting prep <根>` 後，`transcript.raw.md` 非空，且（開分離時）`diarization.json`、`transcript.speakers.md` 存在。 | `req:282` | 人工（需要模型；`run_in_background`） |
| 4.13.5 | 對一個既有已完成場次刪掉 `diarization.json` 重跑 `meeting diarize`，與原結果的逐秒一致率應為 100%。 | `req:283` | 人工 |
| 4.13.6 | 本 epic 的 commit 應通過 `python3 .claude/teams/tools/check_rules.py --git . main..feature/meeting-record`。 | intent §5 Q5 | integrator 每層合併後執行 |
| 4.13.7 | GIT 管控設定內容應維持 `3f47b65` 的修正：`.claude/teams/guard.config.json` 的 `fork_repo` 為 `s96cax98leo/meeting-harness`；`workflow.config` 的 `FORK_REPO` 為同值；`CLAUDE.md` 與 `.claude/teams/rules.md` 不得出現「沒有 remote」；`.claude/workflows/sdlc-{plan,design,design-revise,build}.js` 內的署名行應為 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。 | D4、D5；intent §2 | `test_regression.py::test_git_governance_content` |

### 4.14 資料邊界

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.14.1 | 測試與端到端驗證結束後，`git ls-files` 與 `git status --porcelain` 中不應出現任何 `.mov`／`.wav`／`.m4a`／`.mp4`／`.m4v`／`.mp3`；menu bar 截圖只能放 run 目錄（repo 外）。 | `rules.md:54`、`:66`；intent §4 限制 4 | `test_static_rules.py::test_no_media_in_repo` |
| 4.14.2 | `.gitignore` 應忽略 `tracks/`、`影片/` 與上述媒體副檔名（防手滑的第二道防線）。 | intent §4；`research-code-contracts.md:123-127` | `test_static_rules.py::test_gitignore_media_rules` |
| 4.14.3 | **客戶名稱不進 repo**（第七修正輪）：當環境變數 `MH_CLIENT_NAMES_FILE` 指向一個清單檔（UTF-8，每行一個名稱；空行與 `#` 開頭的行忽略）時，`specs/`、`tests/`、`tools/MeetingRecorder/Tests/` 下每一個檔（工作目錄中實際存在的檔，含未追蹤檔）的內容都不應含清單中的任何一個字串（逐字子字串比對、區分大小寫）；命中時失敗訊息只列 `<相對路徑>:<行號>`，**不得印出命中的字串**。`MH_CLIENT_NAMES_FILE` 指向不存在的檔、或清單沒有任何有效行 → 失敗（不得假綠）；清單檔被 git 追蹤（`git ls-files --error-unmatch <檔>` 成功）→ 失敗（清單本身不得進 repo）；未設定 `MH_CLIENT_NAMES_FILE` → `skipTest`，訊息含「未設定 MH_CLIENT_NAMES_FILE」（其他 session 沒有清單時不誤紅）；所以 integrator 與 t1／t2 的完成條件一律帶這個環境變數跑（`plan.md §3`）。清單檔放 run 目錄（`_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`，由主 session 建立），**不得**寫進 repo 任何檔，本 spec 也不列清單內容。 | `CLAUDE.md`〈客戶資料邊界〉；`rules.md` 通用規則 13；第七修正輪 skeptic 問題 1 | `test_static_rules.py::test_no_client_names_in_repo_text` |

### 4.15 視窗清單與會議標記（D15、D16；第六修正輪）

規則正本是 §3.8；本節只寫可判定的驗收。Swift 測試一律以手建的 `WindowCandidate`／`ChromeWindowInfo` 餵 Core 純函式，不呼叫 SCK 與 Apple Events。

**範例標題一律用中性名稱**（第七修正輪，客戶資料邊界）：本節、§3.8 與 t1／t2 的測試檔中，視窗標題、會議名稱、檔名一律用中性範例——M+ 會議視窗用「[Stand-up] 範例專案」，其他視窗用「範例文件」「範例頁面」之類；**不得**使用任何真實客戶名稱、真實會議名稱、使用者的真實視窗／分頁標題或簡報檔名。實測數字（尺寸、windowID 81837→89596、layer、complete／idle／全黑張數）可以照用。§4.14.3 以靜態檢查擋。

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.15.1 | `exclusionReasons` 應：對 layer 0、500×500、標題為空的 LINE 通話視窗（`jp.naver.line.mac.LineCall`）與 layer 0、1197×840、標題為空的 PowerPoint 視窗回 `[]`；對 1496×81、1496×158、1016×87、1016×139 回 `[.size]`；對 layer 3、800×600 回 `[.layer]`；對 layer 25、300×200 回 `[.layer, .size]`；對 400×300 恰好邊界回 `[]`。 | §3.8.1；`wfd:17-20`；D15 3(a) | `swift:WindowListTests.swift::testExclusionReasons` |
| 4.15.2 | `meetingService(url:)` 應對 §3.8.2 網址表每列至少一個 https 網址回對應服務名（含 `https://meet.mplusapp.com/m/joinMeeting?shortUrl=x` → `M+ Meet`、`https://us02web.zoom.us/wc/1` 與 `https://zoom.us/j/1` → `Zoom`、`https://acme.webex.com/meet/x` → `Webex`、`HTTPS://MEET.GOOGLE.COM/abc` → `Google Meet`），並對 `https://meet.mplusapp.com.evil.example/x`、`https://notzoom.us/j/1`、`http://meet.google.com/abc`、`https://www.google.com/`、空字串、無法解析的字串回 nil；`meetingAppService(bundleID:)` 應對 §3.8.2 原生 app 表每個 bundleID 回對應服務名，對 `com.google.Chrome`、`com.apple.Safari`、`jp.naver.line.mac` 回 nil。 | §3.8.2；D16 | `swift:WindowListTests.swift::testMeetingServiceFromURL`、`::testMeetingAppService` |
| 4.15.3 | `matchChromeWindow` 應：(a) 標題唯一相同、bounds 不同（模擬全螢幕 bounds 不一致）→ `.matched`；(b) 兩個同標題、其中恰一個 bounds 在 ±2 pt 內 → `.matched` 該者；(c) 兩個同標題、bounds 都在 ±2 pt 內或都不在 → `.ambiguous`；(d) 沒有同標題 → `.unmatched`；(e) SCWindow 標題為空 → `.unmatched`。 | §3.8.3；D16 | `swift:WindowListTests.swift::testChromeWindowMatching` |
| 4.15.4 | 當輸入含 8 個 Chrome 視窗（其中 1 個作用中分頁為 `https://meet.mplusapp.com/m/joinMeeting?…`、標題「[Stand-up] 範例專案」（中性範例名，§4.15 前言）、1496×938、`active == false`；另 1 個作用中分頁不是會議但 `tabURLs` 含 `https://meet.google.com/x`）、1 個 Teams 原生視窗、1 個 LINE 通話視窗、1 個 Safari 視窗，且 `automation == .authorized` 時，`buildWindowRows` 應：M+ 列 `meeting == {service: "M+ Meet", source: "url"}`；Teams 列 `meeting == {service: "Teams", source: "app"}`；含非作用中會議分頁的 Chrome 列 `meeting == nil` 且 `meetingTabInactive == true`；其餘 Chrome 列、LINE 列、Safari 列 `meeting == nil`；所有 ★ 列排在非 ★ 列之前，同為 ★ 或同為非 ★ 時依 `active`、面積、`windowID` 排序（§3.8.5）；`isMeetingApp == (meeting != nil)`；LINE 列存在於輸出中。 | §3.8.2、§3.8.5；D16；`wfd:31-32`、`wfd:37` | `swift:WindowListTests.swift::testWindowRowsOrderingAndMarks` |
| 4.15.5 | `windowRowLabel` 應依 §3.8.6 產生字串：§3.8.6 的兩個例子逐字相等；`meetingTabInactive` 列以「（這個視窗有會議分頁，但目前顯示的不是它）」結尾；`isFullScreenSized` 對 1496×938 與顯示器 1496×967 回 true、對 1197×840 與同一顯示器回 false、對 1496×900 回 false。 | §3.8.6；D15 3(b) | `swift:WindowListTests.swift::testWindowRowLabel`、`::testFullScreenSized` |
| 4.15.6 | 若 `automation` 為 `notAuthorized`、`notDetermined`、`chromeNotRunning`、`error` 任一，則 `buildWindowRows`（即使傳入含會議網址的 `chrome`）輸出的 `windowID` 集合應與 `authorized` 時相同，所有 Chrome 列 `meeting == nil` 且 `meetingCheck` 等於該 raw value，原生會議 app 列的 ★ 不受影響。 | §3.8.4；D16「不授權仍可錄」 | `swift:WindowListTests.swift::testRowsWithoutAutomation` |
| 4.15.7 | `WindowListRow` 編碼成 JSON 後的鍵集合應恰為 §3.8.7 的 15 個，`meeting` 與 `meetingCheck` 為 nil 時鍵仍存在、值為 null；`DiagnosedWindow` 的鍵應恰為 `row`、`layer`、`x`、`y`、`excludedBy`；`automationStatus(fromOSStatus:)` 對 0、-1743、-1744、-600、-1 應分別回 `authorized`、`notAuthorized`、`notDetermined`、`chromeNotRunning`、`error`。 | §3.8.4、§3.8.7、§3.8.9 | `swift:WindowListTests.swift::testWindowRowJSONKeys`、`::testAutomationStatusMapping` |
| 4.15.8 | `resolveWindow` 應：windowID 存在 → `.exact`；windowID 81837 不存在、同 bundleID 與標題的 89596 唯一存在且通過篩選 → `.reidentified(89596)`；同 bundleID 與標題的視窗有兩個 → `.ambiguous`；沒有 → `.notFound`；`ref` 沒有 bundleID／title → `.notFound`；同 bundleID、同標題但 `exclusionReasons` 非空的視窗不得被認回；無標題（`title == ""`）的 LINE 通話視窗可依 `("jp.naver.line.mac.LineCall", "")` 認回。 | §3.8.8；`wfd:33`、`wfd:38`；D15 3(c) | `swift:WindowListTests.swift::testResolveWindow` |
| 4.15.9 | `diagnoseWindows` 應對每個輸入視窗輸出一筆（含被濾掉的），`excludedBy` 等於 `exclusionReasons`；錄製器 `main.swift` 的 dispatch 應有 `diagnose-windows` case，app 的 help 應列出它。 | §3.8.9；D15 3(d) | `swift:WindowListTests.swift::testDiagnoseIncludesExcluded`；t3 完成條件（grep） |
| 4.15.10 | `tools/MeetingRecorder/Sources/` 中應恰有一個檔定義 `chromeTabsScript`（`Capture/ChromeTabs.swift`），其字串內容不得含 `activate`、`execute`、`javascript`、`make`、`close`、`set `、`reload`、`open location`（不分大小寫）；同檔應含 `runningApplications(withBundleIdentifier` 與 `AEDeterminePermissionToAutomateTarget`；`Sources/` 不得出現 `osascript`。 | §3.8.4；D16「唯讀」 | `test_static_rules.py::test_chrome_query_read_only` |
| 4.15.11 | `Resources/Info.plist` 應含 `NSAppleEventsUsageDescription`，值非空、含「Chrome」與「網址」。 | §3.8.4；D16 | `test_static_rules.py::test_info_plist_apple_events_usage` |
| 4.15.12 | `_record_prompt.py` 的視窗選單應依 §3.7：(a) 給含 ★ 列的 `--windows-json` 時，stderr 依序出現每列的 `label` 逐字、提示含「[預設 <第一個 ★ 列的序號>]」，stdin 只送 Enter 時選中該列；(b) 給沒有 ★ 列的 `--windows-json` 時，提示不含「預設」，只送 Enter 會重問、之後 EOF 回 2；(c) 有 `meetingCheck == "not_authorized"` 的列時，stderr 含「自動化」與「不允許也能錄」；(d) stdout 的 JSON 含 `windowID`、`bundleID`、`title` 三鍵，值等於所選那一列。 | §3.7；D16 | `test_prompt.py::test_prompt_window_menu_labels_and_default`、`::test_prompt_no_default_without_meeting`、`::test_prompt_outputs_window_identity` |
| 4.15.13 | `record.sh` 呼叫 app 的 `windows` 時，應只有在 stdin 與 stderr 都是 tty 時才帶 `--ask-automation`（以 `MH_RECORD_OPEN` 替身記錄參數；pty 下有、stdin 為 `/dev/null` 時沒有）；互動開錄時傳給 app 的 `preflight`／`start` 參數應含 `--window-bundle <所選列的 bundleID>` 與 `--window-title <所選列的 title>`。 | §3.5、§3.8.4、§3.8.8 | `test_record_sh.py::test_windows_ask_automation_only_with_tty`、`::test_start_passes_window_identity` |
| 4.15.14 | `MH_RECORDER_APP` 指向不存在路徑時，`bash bin/meeting.sh doctor` 應回 0，錄製器段應恰有一行含「會議分頁標記」，該行以「◦」開頭且含「Apple Events」「選用」；錄製器段不得出現「✗」（§4.13.2）。 | §3.8.4；D16 | `test_regression.py::test_doctor_mentions_meeting_tab_marking` |
| 4.15.15 | 文件應依 §4.12.10 寫明會議視窗標記、Apple Events 是選用、不授權的後果。 | D16；D13 | `test_docs.py::test_meeting_tab_marking_documented` |
| 4.15.16 | **M+ 全螢幕**：使用者開 M+ Meet 會議頁並按綠色按鈕進 native 全螢幕、已允許 Apple Events 後，`meeting record windows` 的第一列與互動選單（`meeting record`）的第一列都應是該視窗、label 以「★ 會議（M+ Meet）」開頭且含「全螢幕尺寸」，互動選單的預設是它；選它開錄並切到別的 Space 至少 30 秒，`e2e_check.py --space-interval` 該區間應 PASS。 | D15 1、4；D16；`wfd:17`、`wfd:31-33` | 人工（t6） |
| 4.15.17 | **LINE 通話**：開著 LINE 通話時，`meeting record windows --json` 應含 LINE 通話視窗那一列（診斷時記錄為 `jp.naver.line.mac.LineCall`，以實際 bundleID 為準），其 `untitled == true`、label 的名稱片段為「<app 名>（無標題）」；互動選單也應列出同一列。 | D15 2、3(a)；`wfd:18` | 人工（t6） |
| 4.15.18 | **Apple Events 授權兩條路**：(a) 第一次授權——以 `tccutil reset AppleEvents com.meetingharness.recorder` 清掉紀錄後，在終端機跑 `meeting record windows`，應跳出「允許控制 Google Chrome」授權框，按允許後清單出現 ★ 會議列；(b) 不授權仍可錄——在「自動化」關掉 MeetingRecorder › Google Chrome 後，`meeting record windows` 照常列出（Chrome 列沒有 ★、最後一行有 Apple Events 說明），preflight 第 13 項為 warn 而非 hard，選 Chrome 會議視窗開錄 1 分鐘並 `record stop`，`e2e_check.py <場次>` 應回 0。 | D16；§3.8.4 | 人工（t6） |

---

## 5. 影響系統

| 檔案／系統 | 動作 | 風險與守則 |
|---|---|---|
| `bin/meeting.sh` | `*)` 前加 `record)`（含 `./record` 撞名判斷、拿掉層旗標 `--recorder`／`--yes`）；`usage()` 加 §2.4.6 結構的 record 段與環境變數；`doctor()` 加錄製器段（含「◦ 會議分頁標記」一行，§3.8.4）並 `return 0` | 同一行不得雙引號＋反引號並存（`bin/_lint.sh:19-23`）；中文前的變數寫 `${VAR}`；`./record` 撞名是核准的語意變更（§6 第 17 條） |
| `bin/record.sh`、`bin/_record_prompt.py`、`bin/_record_finalize.py`、`bin/_record_estimate.py` | 新增（prompt 的視窗選單與輸出照 §3.7；`record.sh` 依 §3.5 帶 `--ask-automation`、`--window-bundle`、`--window-title`） | 進 `_lint.sh` 掃描；lint 檔數 22 → 26 |
| `config.json` `sourceLayout` | 加 `videoDir`、`recordTracks`、`recordStatus` 三鍵（純文件，無程式讀） | 保持合法 JSON |
| `tools/MeetingRecorder/Sources/**`、`build.sh`、`Resources/Info.plist`、`Resources/MeetingRecorder.entitlements`（新增） | 擴充；切出 `Core/`（含 `WindowList.swift`）、`Capture/`（含 `ChromeTabs.swift`）、`Trigger/`；`build.sh` 改編多檔、以 SHA-1 簽章並帶 `--entitlements`（固定身分時另帶 `--options runtime`）；`Info.plist` 加 `NSAppleEventsUsageDescription`；新增 app 子指令 `diagnose-windows` | `probe` 子指令保留（第 0 階段量測可重跑）；entitlements 恰為麥克風與 Apple Events 兩項（§4.2.8）；視窗篩選移除「標題非空」、★ 改依 §3.8.2（Chrome／Safari 不再整個 app 標 ★）；**D20**：新增 `Capture/SegmentWriter.swift`，正式錄製改以 `AVAssetWriter` 寫段落（§4.4.5），`SCRecordingOutput` 只留在 `Probe.swift` |
| `tools/MeetingRecorder/Tests/`、`tests/record/`（含 §2.4.8 的 `surface.py`） | 新增 | 不產生、不提交任何真實錄音 |
| `.claude/skills/meeting-record/SKILL.md` | 新增（build 第 1 層，先於程式寫成；含 §2.4 的 `record-cli` 區塊） | 改 repo 等於改全域（`rules.md:68`）；是 t3、t4 的契約（§6 第 29 條） |
| `.claude/skills/meeting-summary/SKILL.md` | 正文加一行 | frontmatter 不動 |
| `README.md` | 指令表、結束碼、skill 表、for-loop、目錄樹；加 §2.4 的 `record-cli` 區塊 | 與 SKILL.md 的區塊內容相同（§4.12.6） |
| `.gitignore` | 加 `tracks/`、`影片/`、媒體副檔名 | — |
| `specs/meeting-record/progress.md` | 主 session 在每層合併與每個閘門後更新勾選 | 不屬任何子任務的 owns（`plan.md §1`），避免平行子任務共用同一檔 |
| `~/.meeting-harness/` | 新增 `record.status.json`、`record.pid`、`record.log`、`record.defaults.json`、`record.cdhash`（preflight 第 1 項記錄並比對上次的 cdhash，app 寫，§6 第 42 條）、`menubar.lock`（menubar 單一實例的 `flock` 鎖檔，只有 menubar 模式開，§4.11.10） | repo 外 |
| `~/.claude/skills/meeting-record` | 新增 symlink | 全域變更，deliver 閘門後由主 session 執行 |
| TCC：螢幕錄製、麥克風、文件資料夾 | 新 bundle／新簽章身分第一次使用時授權 | 授權後要重啟（preflight 第 3 項）；t6 開始前由使用者重給 |
| TCC：自動化（MeetingRecorder → Google Chrome，Apple Events） | 第一次在終端機跑 `windows`（帶 `--ask-automation`）時跳授權框；選用 | 不授權只影響 Chrome 會議分頁的 ★，不影響錄製（§3.8.4）；ad-hoc 簽章每次重建都可能要重給（§7 疑慮 14） |
| 鑰匙圈 `MeetingHarness Dev`（SHA-1 `5E249F84A9EC2F2D2B3914120906DF29FB4DF348`） | 只讀用於簽章 | 不受信任狀態不影響簽章，見 §6 第 13 條 |

**結構性不受影響**（intent §3 已覆核）：`bin/_combine_audio.py`、`has_audio()`／`list_sessions()`、`bin/diarize.sh`、`bin/_merge_speakers.py`、`bin/_profile.py`、`bin/_render.py`。

---

## 6. 整合修訂與例外

以下為經使用者決定（D1–D22）或本 spec 依實測修正的項目；凡標「待閘門 2 核准」者，閘門 2 核准即視為核准。

| # | 原文 | 修訂 | 依據 |
|---|---|---|---|
| 1 | `req:197`「任何 fail 一律不開錄」；`req:197` 列 11 項 | 「任何 hard fail 不開錄」；第 12 項＝視窗是否最小化（warn） | D1 |
| 2 | `req:273` 驗收 | 12 項各製造一次失敗，hard 項驗結束碼、warn 項驗照常開錄且有提示（第六修正輪起為 13 項，見第 34 條） | D1；D16 |
| 3 | `req:200` 每 5 分鐘輪替 | 每 60 秒 | D3 |
| 4 | `req:275`「救回約 2 分鐘（最後未滿 5 分鐘那段會丟）」 | 「救回約 1–2 分鐘（最後未收尾的 1 分鐘會丟）」，量化為 60–125 秒（§4.8.1；t6 第三輪把上限改為「開錄到 `kill -9` 的秒數＋1 秒」，第 70 條） | D3 |
| 5 | `req:179`、`req:264` 畫布 2992×1876 | **每段以當下會議視窗像素大小開檔；finalize 統一成各段最大寬高、置中補邊不裁切**（§4.3.2、§4.3.4）。前一版「畫布＝`displayPixelSize()` 2992×1934」的修訂**作廢** | D8 |
| 6 | `req:264`「≈60 fps」 | 驗設定 `minimumFrameInterval=1/60`，並在畫面持續變化時量到 1 秒滑動窗 ≥ 55 fps 的尖峰；平均 fps 不驗（畫面不變時不寫幀，`PROBE-REPORT.md:27`） | D9；「接近 60」量化為 ≥ 55 待閘門 2 核准 |
| 7 | `req:271`「切換瞬間容許短暫掉落」；前一版量化為每次 < 15 秒 | 每次 < 3 秒（系統聲音路、麥克風路、混音音軌分別量）；`req:199` 的 15 秒只作錄製中告警門檻 | D10 |
| 8 | Story ID | 以 spec 節編號代替；commit scope 用模組名 | `rules.md:24`；intent §4 限制 7 |
| 9 | 第 0 階段直接在 `main` 開發（`9a76c83`） | 記錄為對 SDLC 的偏離；不 revert，`feature/meeting-record` 從 `main` 開 | intent §5〈已知既成事實〉1 |
| 10 | intent §5 Q2 標「已定案」但量法待 design | 量法已依 D2 實測定案（§4.2.5、`design.md §6`） | `d2:23-29` |
| 11 | intent §5〈已知既成事實〉3 末段指向「本次信封」 | 該問題已由 D5 定案並於 `3f47b65` 完成 | `gate1-decisions.md` D5 |
| 12 | `forbidden_trailers` 清空後 `check_rules.py:31` 的預設值會補回 `Co-Authored-By` | 補回後仍被同一行的過濾式去掉（`ATTR_KEY` 同名），行為不變；字面衝突移到程式預設值，屬上游 AgentWorkFlow 範圍，列衍生工作 | `.claude/teams/tools/check_rules.py:29-31` |
| 13 | intent §5〈已知既成事實〉2「私鑰與憑證沒配成對」 | 實測身分已成對但**不受信任**（`CSSMERR_TP_NOT_TRUSTED`）；`build.sh:32` 的 `-v` 過濾造成退回 ad-hoc。`build.sh` 改以 SHA-1 `5E249F84A9EC2F2D2B3914120906DF29FB4DF348` 判斷與簽章；preflight 第 1 項在 ad-hoc 時才 warn | `security find-identity -p codesigning` |
| 14 | `PROBE-REPORT.md` 兩份 | 以 `tools/MeetingRecorder/PROBE-REPORT.md` 為正本 | intent §5〈已知既成事實〉4 |
| 15 | `rules.md:58`「`dev-design-reviewer` 與 `has_ui` 一律 false」 | 本 epic test 段 `has_ui=true`，平行派 `dev-design-reviewer` 審 menu bar；沒有設計系統 skill，依據為 macOS HIG menu bar extra 慣例（§4.11.5–4.11.8）。只適用本 epic，不改 `rules.md` | D12（使用者決定，核准人：使用者） |
| 16 | `req:123`「保留原樣全解析度」；`req:267` duration 差 | finalize 整支重新編碼（逐段正規化＋補尾，`h264_videotoolbox` high profile、位元率 ≥ 原片最大值 × 1.5、下限 8 Mb/s、不縮放、不改 fps），以 stream 層量 duration 差。**這與使用者先前「保留原樣全解析度」的決定相比有一次轉碼損失，使用者在知情下選擇** | D7（使用者決定） |
| 17 | intent「既有行為零變更、純加法」；`bin/meeting.sh:400-402` 把 `record` 當根目錄跑 prep | 目前目錄有 `record/` 時，`meeting.sh record …` 不默默選邊：有 tty 就詢問，沒有人可問就回 2 並印出 `--recorder`／`prep ./record` 兩種明確寫法（§2.3、§4.1.3、§4.1.10） | D11（使用者決定） |
| 18 | `req:199`「RMS 只用於監看、不寫檔」 | 解讀為「不另寫分路音檔」；兩路 0.5 秒時段峰值（數字）寫進 `manifest.json.levels`，作為 D6／D10「每路中斷 < 3 秒」的唯一分路證據 | D6、D10；待閘門 2 核准 |
| 19 | 需求未提音訊轉碼 | finalize 把每段音訊統一成 48 kHz 雙聲道 AAC 256 kb/s 後串接（HFP 讓各段格式可能不同）；`錄音/*.wav` 仍是 16 kHz 單聲道，轉錄輸入不受影響 | D6、D7；待閘門 2 核准 |
| 20 | intent §2「GIT 管控修正是 `feature/meeting-record` 的第一個 commit」 | `3f47b65` 實際是分支上第 3 個 commit；前兩個（`89cbd28`、`ca211b0`）只是 intent 文件，仍在任何功能程式碼之前，目的（先修管控、再寫程式）成立。內容以 §4.13.7 防迴歸 | `git log --oneline main..feature/meeting-record` |
| 21 | 前一版 build 段量測閘門（t3 量 §4.4.3、§4.4.4） | 移到 test 段 t6 第一步，使用者重新授權 TCC 之後量；加上 §4.3.4 縮放量測 | `design.md §7.2`；派工單修正指示 |
| 22 | 前一版 §4.4.4「`seg-0002.mov` 應含 video stream，不過則 `needs_decision`」 | 改為只記錄；缺 video stream 的段由 finalize 補（§4.6.11），不再阻斷。**D20 後由第 51 條取代（改回必驗）** | `design.md §7.4` |
| 23 | 前一版 design 寫「2 GiB」、spec 寫「2 GB」 | 統一為 2 GB＝2,000,000,000 bytes（照 `req:199` 字面），所有容量一律十進位 | skeptic 問題 14 |
| 24 | 需求未定音影同步的量法 | HFP 情境以同步測試源的閃白／嗶聲時間差 < 100 ms 驗（門檻沿用 `req:267` 的 100 ms） | D6 (c)；待閘門 2 核准 |
| 25 | 需求與前一版 design 未提 entitlement；app 過去實際上從未以 hardened runtime 執行 | 新增 `MeetingRecorder.entitlements`，`build.sh` 以 `--entitlements` 簽。**第六修正輪改為兩項**：`com.apple.security.device.audio-input` ＋ `com.apple.security.automation.apple-events`（D16 讀 Chrome 分頁網址需要，見第 33 條）；其他 hardened runtime entitlement 依文件判斷不需要（`design.md §9.1`），未實測，t6 驗 | 第二輪 skeptic 問題 2；D16；第六修正輪 skeptic 問題 2；待閘門 2 核准 |
| 26 | 前一版 `design.md §8.2`「`phase ∈ {done, preflight_failed}` 且 `code=0` → 待機」 | `preflight_failed` 一律歸告警態，狀態列顯示「開錄前檢查沒通過」＋訊息首行，「開始錄製」可點；完整對映改以 §3.4.1 表為唯一正本 | 第二輪 skeptic 問題 3；告警停留時間由 D14 定為「停到下次開錄」（使用者決定）；其餘待閘門 2 核准 |
| 27 | 前一版 §2.2 只有六個子指令（intent §2 同，`intent.md:46`），沒有 `record help` | 新增 `meeting record help`（`-h`、`--help` 同義），結束碼 0，輸出格式見 §2.4.3；寫法因此是七種（§1、§2.4.1），`meeting.sh help` 的 record 段列七種（§4.1.2）；`help` 成為保留字，名為 `help` 的根目錄要寫 `./help` | D13（使用者在決定中指定以 `meeting.sh record help` 的輸出比對文件）；待閘門 2 核准 |
| 28 | `design.md §8.1` 只寫「拿掉 `--recorder` 後交給 `record.sh`」，`--yes` 交出去後 `record.sh` 怎麼處理沒定 | `--yes` 與 `--recorder` 一樣由 `meeting.sh` 判斷後拿掉，`record.sh` 看不到；語意仍只有 §2.3（D11 不變） | 第三修正輪補齊（避免 t4 自行發明 `--yes` 在 `record.sh` 的語意）；待閘門 2 核准 |
| 29 | 前一版 plan：t5 文件依 t3、t4 的實際 help 文字寫 | **文件先寫**：t5 只依 spec／design 定案內容寫文件，t3、t4 依賴 t5，`meeting.sh record help`、子指令、旗標、結束碼以 t5 的文件為準；不一致時改程式不改文件，真要改文件以 `needs_decision` 回報。§2.4 的封閉清單與 §4.12.6–4.12.9 是這個約定的機械判準 | D13（使用者決定） |
| 30 | 前一版 §2.2 `status` 列的 2 欄寫「未知選項」，§2.4 卻說未知選項的 2 不列入（同一組合兩種讀法）；`--recorder`／`--yes` 要求列在 help 卻放不進區塊格式 | 未知選項與 `./record` 撞名無人可問改為§2.2 的**通則結束碼 2**，各列 2 欄不再列；`status` 的寫法結束碼為 `0 5`；層旗標獨立成一類，只在 help 的「meeting.sh 層旗標：」段與 `usage()` 的層旗標行出現；help、`usage()`、文件區塊的格式與解析規則統一寫在 §2.4.3–2.4.7。只是把同一套語意寫成單一定義，`meeting record status` 的實際行為不變（未知選項仍回 2） | 第四修正輪 skeptic 問題 1；待閘門 2 核准 |
| 31 | 第四修正輪 §2.4.2 寫層旗標「只能緊接在 `record` 之後」，同時未知選項的定義不看位置、`design.md §8.1` 又寫 `--yes` 任何位置都拿掉（三處互相矛盾）；前一版未知選項以單一 `-` 開頭判斷 | 層旗標在 `record` 之後任何位置出現都由 `meeting.sh` 拿掉、其餘參數原序交給 `record.sh`；未知選項在 §2.2 通則、§2.4.2、`design.md §8.1` 用同一句定義（拿掉層旗標之後、仍不屬於該寫法寫法旗標集合的 `--` 開頭參數）。因定義改以 `--` 開頭判斷，只以單一 `-` 開頭的參數（`-h` 之外）不再回「未知的選項」，照一般參數處理（例如 `meeting record -x` 的 `-x` 當 `<根>`，路徑不存在仍回 2）；所有寫法旗標都是 `--` 開頭，沒有寫法因此失去檢查。新增 §4.1.12 中間／結尾兩個案例 | 第五修正輪 skeptic 問題 1；主 session 依 `design.md §8.1` 現行寫法定案（實作細節）；待閘門 2 核准 |
| 32 | 前一版 spec 沒有定義視窗清單；第 0 階段原型 `main.swift:122-133` 以 layer 0、寬 ≥ 400 且高 ≥ 300、**標題非空**三條篩選，並把 `com.google.Chrome`、`com.apple.Safari` 整個 app 標 ★ | 新增 §3.8 為唯一契約：移除「標題非空」（無標題視窗顯示為「<app 名>（無標題）」）、保留另兩條；★ 只給原生會議 app 與「作用中分頁是會議網址」的 Chrome 視窗；每列顯示 app 名、標題、尺寸、是否全螢幕尺寸、前景／背景、會議標記；新增 Core 純函式與 Swift 測試（§3.4、§4.15.1–4.15.9） | D15（使用者原話「先診斷，再補進 spec（建議）」）；`wfd:18-20`、`wfd:37`；第六修正輪 skeptic 問題 1；待閘門 2 核准 |
| 33 | 前一版 `design.md §9.1` 判定 `com.apple.security.automation.apple-events`「不要」；spec 第 25 條「只含 audio-input」 | 錄製器以 Apple Events 唯讀查 Chrome 各視窗分頁網址（§3.8.4）；entitlements 恰為 audio-input＋automation.apple-events，`Info.plist` 加 `NSAppleEventsUsageDescription`；授權是選用：沒授權或 Chrome 沒開時清單照常、只是沒有標記，preflight 第 13 項 `apple_events` 為 warn、doctor 為「◦」，不得 hard fail | D16（使用者原話「讀瀏覽器分頁網址來標記（建議）」）；第六修正輪 skeptic 問題 2；待閘門 2 核准 |
| 34 | D1「preflight 12 項」 | 加第 13 項 `apple_events`（warn，`failCode` 0）；§4.2.1、§4.2.6 改為 13 項；其餘 12 項的名稱、分級、結束碼不變 | D16 要求「preflight 用 warn 標示」；待閘門 2 核准 |
| 35 | D16「網址屬於會議服務的 Chrome 視窗」未指明看哪一個分頁 | 只看**作用中分頁**（單視窗擷取只錄得到正在顯示的分頁）；有會議分頁但不在作用中的視窗不標 ★、label 加提示（§3.8.2、§3.8.6）。對應方式依 D16 授權由 design 定：標題優先、bounds 只分辨同名，對不上不標、不猜（§3.8.3） | D16（「對應方式由 design 定」）；待閘門 2 核准（§7 疑慮 17 列為非阻擋問題） |
| 36 | 前一版 §4.10.3「native 全螢幕失敗時 SKILL.md 寫『會議視窗不要用 native 全螢幕』」、plan 要 t5 一律寫這句 | 刪除一律迴避的寫法：Chrome 會議頁 native 全螢幕切 Space 已實測可錄（`wfd:17`、`wfd:40`），問題出在清單認不出來，由 §3.8 處理；t6 以 §4.15.16 驗；只有 t6 觀察到某 app 失敗時才把該 app 的限制補進 SKILL.md | 第六修正輪 skeptic 問題 1；D15；待閘門 2 核准 |
| 37 | 診斷報告 `wfd:38` 稱「spec 既有的『windowID 找不到才以 (bundleID, title) 認回』」 | **前一版 spec 並沒有這條規則**（`grep -n '認回' spec.md design.md` 在本輪之前無結果；preflight 第 8 項只判 windowID 是否存在）。本輪新增 §3.8.8：windowID 優先、找不到時以 (bundleID, title) 在通過篩選的視窗中**唯一**認回，否則 code 3；`record.sh` 傳 `--window-bundle`／`--window-title`，prompt 輸出加 `bundleID`、`title` | D15 3(c)（派工單「沿用既有」與 spec 實況不符，照其意圖補上）；`wfd:33`、`wfd:38`；待閘門 2 核准 |
| 38 | D15 3(d)：是否把 `main` 上 stash「probe --all 診斷旗標」做成 app 層診斷子指令 | 做：新增 app 子指令 `diagnose-windows`（§3.8.9），只在 `--args` 層，不進 §2.4 封閉清單、不加 `meeting.sh` 寫法；歸 t3 | D15 3(d)；理由：下次「清單沒有我的視窗」不必再依賴 repo 外的 spike app（`wfd:5`），且邏輯就是 `exclusionReasons`，增量小；待閘門 2 核准 |
| 39 | 第六修正輪在 §3.8 依據、§3.8.6 例子、§4.15.4、`design.md §2`、`adr-meeting-window-marking.md` 寫入真實會議名稱（repo 為 public） | 全部換成中性範例「[Stand-up] 範例專案」；`wfd` 改明寫為 run 目錄、不進版控的檔，specs 只引行號與實測數字；§4.15 前言規定測試範例標題一律中性；新增 §4.14.3 靜態檢查（清單在 run 目錄、以 `MH_CLIENT_NAMES_FILE` 傳入，不進 repo）；`0d680c4` 等歷史 commit 仍含原文，本輪不改寫歷史，改列為推送前必辦（`plan.md §5`） | `CLAUDE.md`〈客戶資料邊界〉；`rules.md` 通用規則 13；使用者在閘門 2 第七修正輪的派工決定 2、3；第七修正輪 skeptic 問題 1 |
| 40 | 第五修正輪 §4.1.12 (a)(b) 要求替身參數「恰為 `preflight --window 1`」「恰為 `windows --json`」，與 §3.5（`record.sh` 呼叫 app 必帶 `--log`／`--session`、`--min-free-bytes`、`--run-id`、`--home`）及 §4.15.13 矛盾，t4 無法同時滿足 | 改為三條可同時成立的斷言：層旗標不在替身參數中、使用者給的參數依原序是替身參數的子序列、§3.5 的必帶參數存在（§4.1.12 (i)–(iii)） | 第七修正輪 skeptic 問題 2；待閘門 2 核准 |
| 41 | §3.4.1 M7 排在 M10 之前，有告警類 warning 的場次按停止後狀態列持續顯示最新告警、看不到「收尾中…」，與 §4.11.7「1 秒內顯示收尾中…」互相矛盾（設計審查 SF-2） | 在 M6 與 M7 之間新增 M6a（stopping／finalizing、pid 活著、有告警類 → recording、「收尾中…（告警 N 則）」）；§4.11.7 改為不論有無告警都要含「收尾中…」。**測試例外**：test 段使用者核准調整 `tools/MeetingRecorder/Tests/TriggerTests.swift::testMenuBarStateMapping` 的預期以涵蓋新列——覆蓋集合由 M1–M10 改為全表 11 列、原「M7：stopping、有告警類 → warning」案例改為 M6a 的預期；其餘測試的既有預期不得放寬 | D17（使用者決定，核准人：使用者；test 段閘門前） |
| 42 | 前一版 §5 的 `~/.meeting-harness/` 檔案清單沒有 `record.cdhash` | 補上：preflight 第 1 項用它記錄並比對上次的 cdhash（簽章身分變了要提醒重新授權），t3 在 build 段實作時新增（`Sources/Capture/PreflightRunner.swift`），屬於 spec 漏列，行為不變 | D18（使用者決定一併補進）；build 段實作 |
| 43 | 前一版 §4.11 沒有規定選單展開時的更新、menubar 單一實例、選單上的快速鍵顯示、快捷鍵註冊失敗的處理；§4.11.8 規定 toolTip／accessibilityLabel 等於 `statusLine`，狀態列用系統灰色、長度不限 | 新增 §4.11.9（選單展開時照常更新）、§4.11.10（單一實例，`menubar.lock`）；§4.11.3 加註冊失敗寫 log；§4.11.6 加 ⌃⌥⌘R 顯示；§4.11.8 改為 toolTip／accessibilityLabel 等於 `accessibilityText`（非待機加「MeetingRecorder：」前綴，`statusLine` 本身不變，§3.4.1 的「必須包含」照舊成立），狀態列用 `labelColor`、超過 40 字截斷、完整內容放該選單項的 toolTip；§3.4 新增 `accessibilityText`、`truncatedStatusTitle`、`MenuBarLockResult`、`acquireMenuBarLock`（只新增，不改既有名稱） | D18（使用者決定「t6 之前先修」；設計審查 SF-1、SF-3、N-1–N-3） |
| 44 | 前一版 §4.2.5／`design.md §6` 第 5 項：對目標視窗的 probe stream 播 `afplay` 測試音、任一時段 > -60 dBFS 才 pass，否則 hard | **兩段式**：(a) 目標視窗 3 秒、不播測試音，有聲即 pass；(a) 沒過才 (b) display filter（`excludingWindows: []`）3 秒＋`afplay` 兩次——有聲 → 第 5 項 warn（會議 app 目前沒聲音、擷取權限正常、開錄後 15 秒靜音會告警），照常開錄；仍無聲 → hard fail（結束碼 4，訊息沿用）。第 5 項的分級（`severity(of:)`）不變，改以單筆結果的 `warnOnly` 降為 warn；§3.4 只新增 `warnOnly`、`SystemAudioCheck`、`systemAudioCheck`，既有名稱不改；第 6 項（麥克風）不變；§4.2.6 第 5 項改為三步人工驗收 | D19（使用者決定「兩段式（建議）」，核准人：使用者）；t6 實機：單一視窗 filter 只錄得到擁有該視窗的 app 的聲音，舊判定永遠 fail |
| 45 | 前一版 spec、design、SKILL.md 只寫「錄系統聲音（遠端的人）」，沒有說明範圍 | 新增 §4.3.5：單一視窗 filter 錄到的系統聲音只限擁有會議視窗的 app（同一個 app 的其他分頁也會進來，別的 app 不會）；麥克風照常；SKILL.md、README 用一般使用者看得懂的話寫明，§4.9／§4.10 的系統聲音來源要由被錄的 app 播放 | D19；t6 實機 -10.2 dBFS／-∞（`gate1-decisions.md` D19 列） |
| 46 | 前一版 spec 沒有規定 WindowServer 連線在哪個執行緒建立 | 新增 §4.2.10：`main.swift` 在分派 Task 前於主執行緒（頂層）`NSApplication.shared`＋`.accessory`＋`CGMainDisplayID()`。屬於**只有實機才測得出的缺陷**（preflight 建 `SCContentFilter` 時 SkyLight assert 造成 SIGABRT；單元測試與替身都不會碰到 WindowServer）；紅燈 `b16a375`（`test_windowserver_connection_initialized_on_main_thread`）、修正 `413eb50`，實機確認不再當掉 | t6 第 1 步實機；`gate1-decisions.md` D19 列「另記」 |
| 47 | `req:161-163`「既然只要混音一軌，就不必自己手刻 `AVAssetWriter`，`SCRecordingOutput` 由系統負責落盤與收尾」；`adr-segment-writer.md` 初版採選項 A | **改採選項 B：自管 `AVAssetWriter`**。同一條 `SCStream` 不停，每段一個 writer（影片＋系統聲音＋麥克風三軌，順序固定），在 sample 時鐘上每 60 秒無縫換段、舊 writer 非同步收尾；系統聲音與麥克風分兩軌寫，finalize 以 ffmpeg 混成一軌（「混成一軌」不變，只是混音時點移到 finalize）；影片保留原解析度、H.264 high、fps 上限仍是 SCK 的 1/60，新增寫檔位元率公式 `segmentVideoBitRate`（2992×1876 約 7.0 Mb/s，與磁碟估算 56 MB／分鐘一致）。t6 實機：A 的 finish 回呼在執行中的 stream 上不來（4 次輪替每次約 10.5 秒、各段 `finishedAt` 全 `null`），不等回呼則整條 stream 中斷（ReplayKit -5814） | **D20**（使用者原話「自己管 AVAssetWriter（建議）」，核准人：使用者；本修訂需使用者重新核准 spec／design 後才實作）；`adr/adr-segment-writer.md`；`design.md §7.2` |
| 48 | §3.2 `segments[i]` 的 `requestedAt`／`startedAt`／`finishedAt`／`audioDuration` 依 `SCRecordingOutput` 回呼定義；§4.4.3 只判空隙 | 改為 sample 時鐘與 writer 收尾的定義（§3.2 表）；`audioDuration` 取各音軌最長、一律由封包算；§4.4.3 加「段落確實收尾」與「換段週期恰 60 秒」兩項判準、空隙改判 `\|g_i\|`。**門檻不變**：仍是 D3 的 0.5 秒；D10 的「每次 < 3 秒」是裝置切換的中斷容許值（§4.9），不套用在換段空隙 | D3、D10；D20 |
| 49 | 前一版 §4.6 只用 `lavfi` 合成素材驗 finalize，`design.md §7.4` 用 `-fps_mode passthrough`、完整解碼檢查不帶參數 | 新增 §4.6.14：逐段正規化時間戳（同一原點平移、影片 `-fps_mode passthrough -enc_time_base demux`、重複 PTS 只留一個、`-avoid_negative_ts make_zero`）再串接，完整解碼檢查加 `-enc_time_base demux`；並以貼近實機特性（VFR、`time_base=1/600`、B-frame）的合成素材驗。根因（spec-author 在 repo 外以實機段落副本重現）見 `design.md §7.4` 第 3 步 | t6 實機「缺陷 3」（rc=5、影片與 wav 未產出）；D20 一併修 |
| 50 | 前一版沒有規定 preflight 與正式 `startCapture` 之間的處理 | 新增 §4.2.11：等 1.0 秒、失敗時等 2.0 秒重建 `SCStream` 重試一次，仍失敗才回既有的 5；不改 CLI、不加旗標 | t6 實機「缺陷 4」；D20 一併修 |
| 51 | 第 22 條：§4.4.4「`seg-0002.mov` 是否含 video stream」只記錄、缺的由 finalize 補 | **改回必驗**：D20 的換段把當下畫面以段落起點重新打戳寫入，每段都應有 video stream 且從段落起點開始；finalize 的補幀（§4.6.11）保留給舊段落與「錄製以來沒收過任何幀」的情形 | D20；`adr/adr-segment-writer.md` |
| 52 | §3.4 `WarningKind` 七種 | 只新增 `segmentWriteFailed = "segment_write_failed"`（告警類），既有七種的名稱、raw value、`isAlert` 不變；§3.4 另新增 `SampleRoute`、`routeSample`、`segmentVideoBitRate`（只新增，不改既有名稱） | D20；`design.md §7.2`〈writer 失敗〉 |
| 53 | `e2e_check.py` 的既有判準 | D20 的新判準（`segment_tracks`、`segment_finished`、`segment_cadence`、`segment_video_start`、`stop_tail`、`format_rotation`）一律放在新旗標 `--segment-writer` 之後，不加進預設判準：t6 期間以 `SCRecordingOutput` 錄下的舊場次（單一音軌）仍可用預設判準核對，既有 `test_e2e_check.py` 的合成場次與預期不必改；`gap` 判準改為取各音軌最長並加判 `\|g_i\|`（單一音軌時結果與前一版相同） | D20；`rules.md` 規則 20（不改既有測試的預期） |
| 54 | §4.2.5 (c) 與 §4.2.6 (i)：系統輸出靜音＋會議 app 沒聲音 → hard fail，`.fail` 訊息含「取消輸出靜音、把音量調大」；`tests/record/test_static_rules.py::test_preflight_system_audio_two_stage` 第 261–263 行斷言 `.fail` 訊息「應保留」這兩句 | **t6 第二輪**：靜音＋會議 app 沒聲音 → warn（`.warnTargetSilent`），照常開錄；`.fail` 訊息只留「重新授權螢幕錄製；若剛授權，完全結束 MeetingRecorder 再重開」；SKILL.md 補「輸出靜音不影響錄音」。**測試例外（使用者核准）**：該靜態測試的這一組預期改為「字串字面值中應含『重新授權螢幕錄製』與『完全結束 MeetingRecorder 再重開』，且任何字面值都不得含『取消輸出靜音』『把音量調大』」；同一測試的其他斷言、`PreflightTests.swift` 的既有預期（`systemAudioCheck` 的判定不變）一律不得放寬或改動 | D21（使用者選「改規格配合實機（建議）」，決定原文即要求拿掉這兩項補救）；t6：輸出靜音＋影片播放 (a) -11.8 dBFS pass、輸出靜音＋影片暫停 (a) -∞、(b) -17.4 dBFS → warn、rc 0 |
| 55 | `design.md §7.1`：邊界前 1 秒以 `SCShareableContent` 非同步查視窗尺寸並暫存（`pendingSize`） | 換段當下在錄製器的序列佇列上**同步**讀 `CGWindowListCreateDescriptionFromArray` 的 `kCGWindowBounds`，經新 Core 純函式 `nextSegmentSize` 決定新段尺寸；讀不到沿用上一段；刪除 `pendingSize`／`sizeQuery`／`scheduleSizeQuery`（§3.4、§4.3.4、§4.3.6）。§3.4 只新增名稱 | t6 缺陷 A（尺寸慢一段才生效）；`t6-rca-ABE.md`〈A〉：`shareableContent()` 約 1000 個視窗、晚於邊界回來或丟例外被 `try?` 吞掉，邊界時清掉 `pendingSize`，晚回的值落到下一段 |
| 56 | `design.md §7.4` 第 3 步：只在需要時才加 `setpts`；補尾上限 `cap = 段落長 − 1/連結影格率`（連結影格率取 `r_frame_rate`）；第 4 步 `-c copy` 串接沿用各段封包長度 | 一律加 `setpts`（沒有改動時 `setpts=PTS`）；`cap = 段落長 − 5 ms`，不再依連結影格率；串接時以 `-bsf:v setts=duration=if(eq(NEXT_PTS\,NOPTS)\,1\,DURATION)` 把整支影片最後一個封包的長度設為 1 tick；正規化後影片軌長改以「最後一幀 PTS」判、容差 50 ms（不再加一幀）。新增 §4.6.17、§4.6.18 | t6 缺陷 B（1650 場次 rc 5）、缺陷 F（2254 場次差 396 ms）；兩者都在 repo 外以場次複本與合成素材驗證修法（`design.md §7.4` 第 3 步） |
| 57 | `design.md §7.4` 第 3 步與 §6 第 49 條寫「輸出加 `-avoid_negative_ts make_zero`」；正規化後「各軌長度與段落長差 < 50 ms」；補尾門檻「≥ 0.1 秒」 | 追認 m4 的實作：**不加** `make_zero`（加了會讓 AAC priming 變成可聽的約 21 ms、每段音影差 21 ms，且讓既有 §4.6.10 的解碼檢查報錯；不加時 mov muxer 以 edit list 處理負時間戳，各軌 `start_time` 已在 [0, 0.05] 秒內）；補尾門檻 0.01 秒；影片軌長容差 m4 實作為「50 ms＋一幀」——此項由第 56 條再改為「最後一幀 PTS、50 ms」。第 49 條其餘內容不變 | m4 open_questions（`build-m.json`）；使用者在 t6 第二輪派工中要求「改成與實作一致」 |
| 58 | §4.4.7 只要求停止時訊息含「段落連續寫檔失敗」，沒有規定收尾也失敗時哪個訊息優先 | 停止原因（forced 訊息）一律保留在最終訊息開頭，收尾失敗原因附在其後；新增 Core `CompletionOutcome`／`completionOutcome`（§3.4、§4.4.9）。只新增名稱，`record` 的結束碼不變（仍是 5） | t6 缺陷 D（`t6-results.md` §4.4.7：最終訊息只剩「收尾失敗（_record_finalize.py 回 5）」） |
| 59 | `design.md §7.2`〈當機〉以 `movieFragmentInterval = 10 秒` 保證當機最多丟約 20 秒；§4.8.4 判準 21 秒 | 新增影片心跳：收到 `idle` 的 `.screen` sample、距目前段落最後一個視訊 PTS ≥ 1 秒時，重送最後一個 complete 幀（以 idle 的 PTS 重新打戳，不更新「最後一個 complete 幀」）；新增 Core `shouldEmitVideoHeartbeat`、常數 `videoHeartbeatSeconds = 1.0`（§3.4、§4.4.10）。§4.8.4 的 21 秒判準不變；修不好時依 D22 以 `needs_decision` 回報，選項之一是改為「當機最多丟 1 段（60 秒）」 | D22（「修正輪先試著修，修不好再放寬（建議）」）；`t6-rca-ABE.md`〈E〉 |
| 60 | §4.4.3 (c) 與 `e2e_check.py --segment-writer` 的 `segment_cadence`：只把與 `sampleRate` 改變相差 < 0.5 秒的邊界當提前換段 | 任何欄位的音訊格式變更（`audioFormatEvents` 任一筆）與 writer 失敗（前一段 `finishedAt` 為 `null`）造成的提前換段都排除，只判定期換段；新增 `test_e2e_check.py::test_segment_cadence_excludes_early_rotation`（含提前換段的合成場次判 PASS）。`format_rotation`（§4.9.3）不變 | t6 缺陷 G（2254 場次 seg-0004 於 165.197 因麥克風緩衝由交錯改為非交錯而提前換段，`sampleRate` 沒變，`segment_cadence` 誤判 FAIL） |
| 61 | §3.2 `audioDuration`「− 第一個封包的 `pts_time`」；`e2e_check.py` 的 `gap` 以 stream 層 `duration` 量 | §3.2 寫明起點取 min(stream `start_time`, 第一個可解碼封包 pts)、可解碼＝略過 `D`／`C` 旗標（即 m4 實作）；`e2e_check.py` 的 `gap` 改用同一算法（§4.6.19）。既有 `test_e2e_check.py` 的預期不得改；若既有合成場次因此改變結果，以 `needs_decision` 回報 | t6 第二輪調查（缺陷 F2）：兩支程式用不同的尺，實機場次重新收尾後 `gap` 誤判 FAIL |
| 62 | §3.4 `routeSample` 註解先判 `end ≤ boundary`；§4.6.14 (B) 字面「音訊以負的 `start_time` 寫入」；`design.md §7.2`、`§7.4` 沒寫 m3 的三處實作選擇 | §3.4 註解改為先判 `start ≥ boundary → .new`（與 §4.4.6、`design.md §7.2`、已實作的 `routeSample` 一致，行為不變）；§4.6.14 (B) 補 edit list 的說明（以第一個音訊封包 pts < 0 認定）；`design.md §7.2`／`§7.4` 追認 m3：音訊緩衝跨邊界時立即換段且兩段都寫、停止點 E 取三路 sample 結束點（音訊為 PTS＋duration）的最大值、停止時最後一段沒有內容就捨棄並從 manifest 移除（不當成寫檔失敗） | m1、m2 open_questions；m3 summary〈跟 design 字面不同的地方〉（`build-m.json`） |
| 63 | 發現 I：幕前調度開啟時，會議視窗不在目前舞台會被縮成側邊縮圖，SCK 單視窗擷取與 CGWindow bounds 都是縮圖尺寸，錄製器照 §4.3.4 跟隨、錄成縮圖解析度（未有規格） | **選項 A（preflight 提醒）**：preflight 只讀 `GloballyEnabled`，開啟時第 12 項 `window_minimized` 以 warn 提醒並照常開錄、`record.log` 記一行；SKILL.md／README 各補一句。錄製中尺寸跟隨不變，**不**改使用者系統設定、不加第 14 項（§4.2.12、`design.md §7.1`〈幕前調度〉）。未採：B「尺寸只增不減、縮圖期間放大」（畫質仍是縮圖、只是放大，並改變 §4.3.4 對使用者主動縮小視窗的語意）；C「開錄時自動關閉幕前調度」（改使用者系統設定，違反 intent §2 原則） | 依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 64 | §4.9.3 sync：每個閃白與嗶聲時間差 < 100 ms，量法未規定（`e2e_check.py` 以全頻 RMS、全片單一門檻找嗶聲） | 量法寫進 §4.9.3：1 kHz 帶通（兩次）＋每個閃白 ±0.3 秒內的局部最大值 50% 起點；判準 100 ms 不變 | 缺陷 K (a)；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 65 | `design.md §7.4` 第 3 步「音訊：混音後 48 kHz、`-ac 2`、`-c:a aac -b:a 256k`」、第 4 步 concat demuxer `-c copy` 串接全部軌 | 正規化時音訊寫 PCM（`pcm_s16le`）；串接時影片 `-c:v copy`（含既有 `setts`）、音訊 `-c:a aac -b:a 256k` 一次編碼；§4.6.12 字面隨之修訂；新增 §4.6.20、§4.6.21。音訊仍只有一次有損編碼（原本是每段各一次，§6 第 16 條的「音訊一次轉碼」語意不變） | 缺陷 J（`design.md §7.4`〈缺陷 J〉）；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 66 | §4.9.1「其餘時間兩路時段峰值應 > -60 dBFS」、§4.9.3「格式變更後時段峰值 > -60 dBFS」 | **選項 A**：改為「不得連續 ≥ 3 秒 ≤ -60 dBFS 或沒有緩衝」；`e2e_check.py` 的 `device_switch`、`hfp` 判準與 `test_e2e_check.py` 自我測試隨之修改（既有預期中與本條衝突的部分依本條改，屬使用者核准的測試修改）。未採：B「判準不變，測試改用持續音源代替說話」（實際會議一定有停頓，判準與用途脫節）；C 其他門檻（例 5 秒，與切換中斷 3 秒不同把尺） | 缺陷 K (b)（t6r2-HFP：格式變更後 5 個 0.5 秒時段 ≤ -60；t6r2-HFP2：2 個，都是說話停頓）；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 67 | §4.5.5 只規定 < 2 GB 要停，沒規定可用空間怎麼讀 | 新增 §4.5.9：每次讀前新建 URL 或清快取 | 缺陷 L；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 68 | §4.3.3「全片相鄰影格 PTS 間隔最小值應 ≥ 1/60 秒 − 1 ms」 | 改為 (i) 1 秒滑動窗影格數最大值 ≤ 61、(ii) 過近間隔數 ≤ 原始段落合計＋(段數 − 1)、(iii) 最小間隔 ≥ 1 ms；`e2e_check.py` 的 `fps_min_interval` 與自我測試隨之修改。實機（t6r2-HFP2，60 fps 同步測試源）：原始段落最小間隔 10.0 ms、< 15.67 ms 的間隔 240 處（seg-0001 212、seg-0002 23、seg-0003 5）；最終片 243 處（多出 3 處＝3 個邊界，最小 6.67 ms）、1 秒窗最大 59 格 → 新判準 PASS。未採「間隔中位數 ≥ 15.67 ms」：VFR 靜止畫面時中位數必然很大，擋不到任何東西 | 發現 M；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 69 | §7 疑慮 29「短段正規化後音訊比時距長約 42 ms，只記錄」 | 根因併入缺陷 J（AAC priming 與尾端補零在串接時變成真的音訊），由 §4.6.20 驗 | 缺陷 J |
| 70 | §4.8.1「wav 長度介於 60 與 125 秒」 | 「≥ 60 秒且 ≤ 開錄到 `kill -9` 的秒數＋1 秒」；`req:275` 的「救回約 1–2 分鐘」說法不變（§6 第 4 條的量化 60–125 秒同步改為本條） | t6「t6 第二輪 7」§4.8.1（133 秒 `kill -9` 救回 130.1 秒）；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選 |
| 71 | `design.md §7.4` 第 3 步只規定補尾用 `tpad` 與 `setpts`，沒規定關鍵幀間距與最後一個封包長度 | 正規化以 `setts` 把最後一個影片封包長度設到段落結束；關鍵幀每 2 秒強制一個、不用 B 幀；`cap` 對齊 tick；補尾幀讀不到時明確報錯（`design.md §7.4`〈缺陷 N〉） | 缺陷 N（t6r3-e2e 0330 finalize rc 5）；主 session 依「明天一早就要完成」指示修正，屬實作修正、不改既有判準 |
| 72 | `design.md §7.4` 第 3 步「補出的幀 PTS 落在 `cap` 前 0.01 秒內或之後的一律夾成 `cap`」 | 複製幀落在 `cap` 前 1/60 秒內併進 `cap`；最後一幀距 `cap` < 1/60 秒 − 1 ms 時不補尾；去重時丟掉距前一幀 < 1/60 秒 − 1 ms 的複製幀。§4.3.3 判準不變 | test 段 verifier（HEAD cb417b4）§4.3.3 (ii) fail，由 sdlc-test 修正輪 `af91ec0` 修好；屬實作修正、不改判準 |
| 73 | §4.11.8 狀態列超過 40 字截斷、完整內容放 toolTip；收尾失敗時看得到的部分可能只有停止原因，補救指令被截掉（設計審查 N-1） | 收尾失敗時 `statusLine` 改為固定短句「錄製失敗：收尾失敗，段落保留（滑過看補救方法）」；`MenuBarModel` 新增 `detailText`（失敗類為完整多行訊息，其餘等於 `statusLine`）；選單在狀態列之後多一項「複製完整訊息與補救指令」，只在 `detailText != statusLine` 時顯示。§4.11.8 的 toolTip 規定不變 | 設計審查 N-1；使用者 2026-10-12 指示「你先修其他問題」，主 session 依審查建議定案，可改選 |
| 74 | §4.2.4 只規定 warn 列在 `record` 輸出與 `record.status.json`，quick-start 沒有終端機看不到（設計審查 N-2） | quick-start 開錄時 preflight 有 warn 就送一則通知「MeetingRecorder 已開錄（有提示）」，內文前 3 行、其餘見 `record.log`（`preflightWarnNotification`）；終端機 `meeting record` 不送 | 設計審查 N-2；同上 |
| 75 | §4.11.6 選單永遠顯示 ⌃⌥⌘R，快捷鍵註冊失敗時也是（設計審查 N-3） | 註冊失敗時清掉「開始錄製」的 `keyEquivalent`（選單項本身照常可用） | 設計審查 N-3；同上 |
| 76 | 原始計畫「新增的檔案」寫 `tools/MeetingRecorder/`（Xcode project ＋ Swift 來源 ＋ `build.sh`） | 只有 Swift 來源與 `build.sh`（`swiftc` 直接編譯、簽章），沒有 `.xcodeproj`；不影響功能與簽章（§4.2.8） | 計畫對照（2026-10-12）補記 |

---

## 7. 疑慮

1. **換段空隙與每段換尺寸**（D20 後更新）：`SCRecordingOutput` 輪替在 t6 實測不可行（每次約 10.5 秒空隙、段落未收尾），已依 D20 改自管 `AVAssetWriter`。新做法在設計上無空隙，但**沒有本機實測**；§4.4.3、§4.4.4、§4.3.4 在 t6 中途修正輪後重跑量測閘門，不過仍以 `needs_decision` 回報（ADR 的退回選項只剩 C「不分段」或接受實測數字）。**t6 接續結果**：1650 場次 §4.4.3 PASS（max |g| 0.117 秒）、§4.4.4 PASS；§4.3.4 尺寸慢一段才生效（缺陷 A），t6 第二輪改為換段當下同步讀尺寸（§4.3.6），修正後重測。
2. **麥克風 RMS 在安靜房間＋耳機時可能誤判失敗**：-60 dBFS 是正本門檻（`req:198`），安靜環境底噪可能更低。設計以「preflight 前提示說一句話」緩解；實測若仍誤判，需要使用者決定門檻或改判「是否為數位全零」。
3. **SCK 在預設輸入變更時是否自動跟隨**未知（`req:292`）；D20 後格式變更改由錄製器**提前換段**處理（每段每路只有一種輸入格式，`design.md §7.5`），但 `AVAssetWriterInput` 能否把 16／24 kHz 單聲道 LPCM 轉成 48 kHz AAC 輸出未實測。設計以 `updateConfiguration` 主動切換、以 §4.9.1–4.9.3 驗；不過時的退回選項見 `design.md §7.5`。
4. **錄製器寫 `~/Documents/…` 需要「文件與資料夾」授權**，失敗同樣靜默；已併入 preflight 第 7 項的可寫探測，但不在 D1 的 12 項名稱裡（歸在「磁碟空間」）。
5. **整支重編**（D7）讓長場次 finalize 變久、磁碟峰值升到約 4 倍；`record stop` 會逐段印進度。
6. **`./record` 撞名後，無 tty 的呼叫者（例如其他 session 透過 skill 呼叫）在那個目錄下會拿到 2**：SKILL.md 要教它改用 `--recorder`（§4.12.1）。
7. **`record` 與 `render`、`meeting.record.json` 撞名易混淆**（`research-code-contracts.md:52`）：usage 與 SKILL.md 要明寫區分。
8. **磁碟係數 4 × 56 MB/分**是上界（`req:60`）；`minFreeBytes` 預設以 120 分鐘估（`MH_RECORD_EST_MINUTES` 可改），約 29.1 GB（120 × 225.92 MB ＋ 2 GB）。在磁碟較小的機器上可能讓 preflight 過嚴。
9. **fps 尖峰門檻 55** 與 **音影同步 100 ms** 是本 spec 對「接近 60」與「仍對齊」的量化（§6 第 6、24 條），若使用者有別的數字，閘門 2 改即可。
10. **hardened runtime 只確定需要麥克風與 Apple Events 兩個 entitlement**（後者為 D16 新增），其餘（尤其 SCK 擷取）依 Apple 文件判斷不需要、未實測（`design.md §9.1`）。t6 第一步若發現擷取在 runtime 下失敗，要以 `needs_decision` 回報，不由 agent 自行加 entitlement。
11. **告警態會停留到下一次開錄**（§3.4.1 M2–M4、M6）：已由使用者在閘門 2 決定維持（D14「停到下次開錄」），本項關閉；設計審查若仍有意見，記為 test 段發現交使用者決定，不由 agent 改。
12. **`help` 成為 `meeting record` 的保留字**（§2.4.2、§6 第 27 條）：根目錄剛好叫 `help` 的使用者要寫 `./help`。`record` 是新子指令，這不影響任何既有呼叫。
13. **文件先寫的邊界**（D13）：§2.4 只封閉「寫法、旗標、結束碼」三項。非互動開錄（`--window`）時型態、出席者從哪裡來，spec 目前沒有細到文件能逐字照寫的程度；t5 只能寫「非互動要帶 `--window`」，不得自行描述來源；t4 若發現需要新旗標，依 §6 第 29 條以 `needs_decision` 回報，不得自行加旗標（加了會讓 §4.1.11、§4.12.7 失敗）。
14. **Apple Events 授權跟簽章走**：TCC 以簽章的 designated requirement 記錄「自動化」授權；固定身分（SHA-1 簽章）重建後應沿用，ad-hoc 簽章每次重建都可能要重給。t6 §4.15.18 驗第一次授權與不授權兩條路；固定身分重建後是否沿用未實測。
15. **錄製中途 windowID 改變不處理**：§3.8.8 只在 preflight／start 時認回。實測同一視窗 windowID 會變（`wfd:33`），若錄製中變了，SCK 單視窗串流可能停止或只收到 `suspended`（會觸發 §4.5.3 告警）；中途重新掛載視窗列為衍生工作（不編號）。
16. **native 全螢幕下 Chrome AppleScript 的 `bounds` 與 SCWindow `frame` 是否一致未實測**：§3.8.3 以標題優先比對，bounds 只用來分辨同名視窗，所以單一會議視窗不受影響；同時開兩個同名的會議分頁且都全螢幕時可能 `.ambiguous`（不標 ★、不猜）。t6 §4.15.16 會實測單一視窗情境。
17. **★ 只看作用中分頁**（§6 第 35 條）是對 D16 的解讀：若使用者希望「視窗內任何一個分頁是會議就標 ★」，代價是可能錄到非會議分頁的畫面；閘門 2 可改。
18. **preflight 第 13 項在 Chrome 沒開時也是 warn**：照 D16 字面「沒有 Apple Events 授權或 Chrome 沒開時……preflight 用 warn 標示」。用原生 Teams 開會、Chrome 沒開時也會看到這個 warn（不影響開錄）；若覺得吵，閘門 2 可改為「Chrome 沒開 → pass 並附說明」。
19. **客戶名稱的歷史與 specs 以外的檔**（第七修正輪）：本輪只讓 `specs/` 的 HEAD 乾淨；第六輪的 `0d680c4` 仍含真實會議名稱，`main` 上尚未推送的歷史 commit 與 `main` 的 `README.md` 也有客戶名稱的命中（以清單掃描得知，只記檔與 commit、不記字串，見 run 目錄 `design-revise-對照.md` 第七輪）。改寫歷史是不可逆動作、`README.md` 不在 specs 範圍，兩者都不由 agent 處理，列為 `plan.md §5` 的推送前必辦，交使用者決定。§4.14.3 的靜態檢查只掃 `specs/`、`tests/`、`tools/MeetingRecorder/Tests/`，不掃 `README.md`（`README.md` 既有命中在 `main` 上，掃它會讓 t5 背別人的債；由推送前必辦處理）。
20. **第 5 項 warn 時只證明「擷取權限正常」，沒證明「會議 app 的聲音錄得到」**（D19）：(b) 用 display filter 驗的是系統聲音擷取權限與輸出沒靜音；會議 app 在開錄後若一直沒聲音（例如會議 app 自己靜音、或被錄的 app 不是發聲的那個），要等 §4.5.1 的 15 秒靜音告警才會發現。另外 (a) 沒過時 preflight 多跑 3 秒（(b)）並播兩次測試音；`record.sh` 的等待上限 120 秒不受影響。
21. **D20 自管 `AVAssetWriter` 的未實測點**（ADR〈後果〉）：(a) `AVVideoScalingModeKey` 對尺寸不同的幀是否等比縮放（§4.3.4）；(b) 被 `kill -9` 中斷的 fragment 段落 ffmpeg 讀得到多少（§4.8.4；以 ffmpeg 自己寫的 fragment 檔已在 repo 外驗證可讀，`AVAssetWriter` 寫的還沒驗）——**t6 已實測不過**（靜止視窗時 `AVAssetWriter` 完全沒寫 fragment），t6 第二輪以影片心跳修（§4.4.10），殘留風險見疑慮 27；(c) 錄製器自己編碼後，sample 佇列是否會因 `isReadyForMoreMediaData == false` 而丟幀——丟幀數會寫進 `record.log`，t6 量測閘門要記錄；(d) sample PTS 與 host clock 是否同一時鐘，錄製器第一個 sample 時記偏移到 `record.log`。任何一項不過都以 `needs_decision` 回報，不自行換做法。
22. **段落檔直接播放時聽到的聲音**（D20）：`tracks/seg-*.mov` 現在有兩條音軌（系統聲音、麥克風），有些播放器只播第一條（只聽得到遠端）。這只影響「直接開段落檔」；正式產出的 `影片/*.mov` 與 `錄音/*.wav` 是混好的一軌。SKILL.md 的救援段已加一句說明。
23. **混音音量**（D20）：兩軌等權相加、不做 1/2 衰減（避免整體變小聲），兩邊同時很大聲時由限幅器壓在 -1 dBFS 以下；這與 `SCRecordingOutput` 的系統混音（演算法未公開）聽感可能略有不同。§4.10.4「兩邊都聽得到」仍由使用者聽寫時間點覆核。
24. **本輪修訂指示寫的「§4.4.3 每次 < 3 秒」與 spec 不一致**：§4.4.3 自始就是 D3 的 0.5 秒門檻（`max(g_i) < 0.5 秒`、3 分鐘場次 `Σ g_i < 0.5 秒`），3 秒是 D10 裝置切換的中斷容許值。本輪維持 0.5 秒（§6 第 48 條）；若使用者其實要放寬換段空隙門檻，請在核准時明說。

25. **觀察 H：藍牙剛切回內建後第一次 preflight 的麥克風是 -∞**（t6 2254 場次開錄前；只發生一次、第二次 -33.4 dBFS 正常，未重現）：-∞ 代表 probe stream 3 秒內完全沒有麥克風緩衝，不是音量太小。推測是預設輸入剛切換、裝置還沒準備好。本輪**不修**；t6 重測時每次切換裝置後的第一次 preflight 都記下第 6 項的數值，若重現再以 `needs_decision` 提出（例：第 6 項 -∞ 時自動重量一次）。
26. **第一段的「空隙」包含音訊晚開始的時間**：第一段的起點 `B_1` 是第一個到達的 sample（常是影片），音訊晚 0.19–0.25 秒才開始（t6 1650、2254 場次），§3.2 的 `audioDuration` 從音訊自己的第一個封包算，所以 `g_1` 會多出這段（0.181、0.224 秒），其實不是邊界上的空隙。門檻 0.5 秒下不影響判定；本輪不改定義（改了會牽動 finalize 與既有測試）。若使用者希望 `g_1` 只反映邊界，可改為「以段落起點量到音訊結束點」，屬下一輪的決定。
27. **影片心跳的殘留風險**（D22）：(a) 會議視窗最小化時 SCK 只送 `suspended`、沒有 `idle`，心跳不會發，當機時正在寫的段落仍可能整段讀不到；(b) `AVAssetWriter` 要**所有**軌越過 fragment 邊界才寫 fragment，而會議 app 沒聲音時 SCK 不送系統聲音緩衝（t6 2254 場次 43–178.5 秒沒有任何系統聲音緩衝），系統聲音軌同樣不前進，影片心跳補不到這一路。t6 第二輪重測 §4.8.4 時另記一次「會議 app 沒有聲音」的 `kill -9` 結果（只記錄，不判）；若 (b) 確實讀不到，與「當機最多丟 1 段」一起以 `needs_decision` 交使用者（例：系統聲音也補靜音心跳，或接受放寬）。
28. **finalize 的尾端修法依 ffmpeg 7.1.1 的行為**（缺陷 B、F）：`setts` 的 `NEXT_PTS`／`NOPTS` 判最後一個封包、`h264_videotoolbox` 在 `setpts` 之後的最後一幀長度，都是在本機 ffmpeg 7.1.1 上實測得出；ffmpeg 升級後若 §4.6.17、§4.6.18 轉紅，先查這兩點。另：影片心跳讓靜止視窗每秒至少一幀，`r_frame_rate` 會更接近 1，前一版「`cap = 段落長 − 1/連結影格率`」在心跳之後只會更糟——缺陷 F 的修法與心跳無關、兩者都要做。
29. **各段正規化後的音訊比段落時距略長**（只記錄）：2254 場次 8 段正規化後音訊合計 307.435 秒，比 `startedAt_8 + 段 8 長 − startedAt_1` 的 307.391 秒長 44 ms，主要來自 seg-0004（多約 42 ms，格式變更提前換段的短段）。遠小於 §4.6.3 的 100 ms 與 §4.4.3 的 0.5 秒，本輪不處理；若長場次累積可見，再查短段的 AAC priming／尾端封包。**t6 第三輪**：已查明——就是缺陷 J（串接時每段的 AAC priming 1024 樣本與前一段最後一個封包的補零變成真的音訊），由 §4.6.20 修與驗，本條結案（§6 第 69 條）。
30. **缺陷 J 的影響範圍**（t6 第三輪，只記錄）：前一版每個段落邊界讓解碼後的音訊比影片多約 21–37 ms（一個 AAC priming 封包 21.3 ms＋前一段最後一個封包的補零 0–21 ms），**逐段累積**：2254 場次 8 段，解碼長度比時間戳長 235 ms；1 小時（60 段）約 1.3–2.6 秒。`錄音/*.wav` 也由同一份音訊解出，所以逐字稿時間軸在長會議後段同樣偏晚。已出的場次可以用修後的 finalize 重新收尾（`meeting record finish`，先把舊輸出移到備份，與 t6 第二輪 2254 的做法相同；屬使用者決定，不自動做）。
31. **幕前調度下的縮圖錄影仍會發生**（發現 I，選項 A 的殘留）：A 只提醒、不改行為；使用者忽略提醒時，會議視窗被縮成縮圖的那幾段仍是縮圖解析度。以不碰 TCC 的方式（只讀 `defaults`、CGWindowList，不呼叫 SCK）查不到取得「非縮圖」原始尺寸或內容的公開 API：t6 實測 SCK 的 `SCWindow.frame` 與 `kCGWindowBounds` 都回縮圖尺寸、單視窗擷取的內容也是縮圖（`design.md §7.1`〈幕前調度〉）。若之後要「切走也錄到完整畫面」，需另立需求（例：改錄整個顯示器、或 B 選項），屬使用者決定。
32. **正規化暫存檔變大**（缺陷 J 修法的代價）：`norm-*.mov` 的音訊由 AAC 256 kb/s 改成 PCM 48 kHz 雙聲道 16 bit（約 11.5 MB／分，前一版約 1.9 MB／分），finalize 期間的峰值磁碟用量每分鐘多約 9.6 MB（相對 `_record_estimate.py` 的 4 × 56 MB／分約 +4%）。本輪不改估算公式（2 GB 底線涵蓋 3 小時以內的差額）；若長場次 finalize 因磁碟不足失敗，再調 `PER_MINUTE`。
33. **新 sync 量法的偏差**：兩次 1 kHz 帶通（頻寬 100 Hz）的群延遲約 5 ms，會讓量到的「嗶聲 − 閃白」系統性偏大約 5 ms；局部最大值 50% 起點在嗶聲被說話大幅蓋過時仍可能偏移。判準 100 ms 下影響小，不另扣；t6r2-HFP2 段內原始的 −37～+75 ms 抖動來自 SCK 送幀，非量法。
34. **本輪定案的程序**：§6 第 63–70 條依使用者 2026-10-12 的指示由主 session 依建議選項定案（不是使用者逐條選），使用者醒來後可改選；改選時受影響的節：I → §4.2.12；K → §4.9.1、§4.9.3；M → §4.3.3；§4.8.1 上限 → §4.8.1。

---

## R2 第二輪（2026-10-12）：麥克風靜音、暫停、選單選視窗與位置、計時、標記、偏好設定

- 性質：R2 增補。上游：`intent.md`〈R2 第二輪功能〉〈R2 閘門 1 使用者決定〉（已核准）、`design.md`〈R2 第二輪設計〉、`adr/adr-r2-*.md` 四則。需求正本 `_tpm/runs/20261010-sdlc-meeting-record/r2-brief.md`（以下 `brief:<行>`）。
- **本檔第一輪內容（§1–§7）一字不改**，唯一例外是 §2.4（CLI 封閉清單）依使用者決定 R2-Q5「全面更新子指令」直接更新（§6 第 77 條）。第一輪各節被 R2 取代或補充的地方，逐條記在本節的〈R2-§6〉（第 77 條起）；資料契約接續編號 §3.9–§3.14，驗收條件 §4.16 起。
- 識別、句型、「測試」欄記號沿用檔頭（節編號代替 Story ID；`swift:<檔>::<函式>`＝`tools/MeetingRecorder/Tests/`；`tests/record/<檔>::<函式>`＝Python unittest；「人工」＝t7 由使用者操作、`tests/record/e2e_check.py` 機械核對）。Python 測試檔名省略 `tests/record/` 前綴時同義。
- 範例名稱一律用「[Stand-up] 範例專案」（§4.15 前言、§4.14.3）；`markers.json` 的 `label` 一律「標記 N」，不收任何使用者輸入。
- **閘門 2 修正輪（2026-10-12）**：依使用者在閘門 2 的四項決定與 skeptic 的 8 條問題修正本 R2 節（第一輪 §1–§7 與 §2.4 仍照前述，一字不改）。使用者決定：(1) `markers.json` 的 `t` 用成品時間、另附 `recordT`；`record.meta.json` 事件的 `t` 用錄製時鐘、另附 `outputT`（design R2-D5 原案，§6 第 95 條）；(2) 停止後自動前處理遇到下一場開錄時先不讓路，t7 實機觀察（§7 疑慮 38 保留，§6 第 96 條）；(3) `record.status.json`／`record.meta.json` 的 R2 新欄位 nil 時省略鍵、`RecordsTests` 不改（§6 第 79 條）；(4) skeptic 問題全部修正，resume 換段與暫停狀態轉移搬到 Core 的純函式並以 Swift 單元測試驗收（§3.14 的 `Segments.swift` 與 `Control.swift` 增補、§4.18.8–§4.18.10）。本輪新增的驗收：§4.16.11、§4.17.7、§4.17.8、§4.18.8–§4.18.12；修改：§3.12 範例數值、§3.14、§4.18.2、§4.18.3、§4.25.1、R2-§5、R2-§6 第 79、95、96 條（依據欄）與新增第 98、99 條、R2-§7 疑慮 38。對照表在 run 目錄 `design-revise-對照.md`〈R2 閘門 2 修正輪〉。

### R2-§2.2 新寫法的結束碼語意（接續 §2.2）

| 寫法 | 0 | 2 | 3 |
|---|---|---|---|
| `record pause`／`record resume`／`record mute`／`record unmute`／`record mark` | 已套用，且 `record.status.json` 在 5 秒內反映（`pause`→`paused == true`；`resume`→`false`；`mute`／`unmute`→`micMuted`；`mark`→`markers ≥` 寫入的 `markerSeq`）；本來就是目標狀態時不送訊號、直接回 0 | 只有通則（未知選項、`./record` 撞名無人可問）；另外多餘的位置參數回 2（與 `record stop` 的現行行為 `bin/record.sh:509` 相同，不列入寫法結束碼，§7 疑慮 36） | 沒有可控制的錄製：沒有錄製在跑、`phase` 是 `preflight`／`stopping`／`finalizing`、`record.pid` 與 `status.pid` 不符、舊版錄製器（狀態檔沒有 `controlVersion`）、或送出後 5 秒內狀態沒有反映；stderr 一句說明（字樣見 §3.14 `controlAvailability`） |

- stdout（回 0 時一行）：`pause`「已暫停（已錄 <計時>）」或「已經是暫停中」；`resume`「已繼續錄製」或「本來就在錄製中」；`mute`「麥克風已靜音」或「麥克風本來就是靜音」；`unmute`「麥克風已取消靜音」或「麥克風本來就沒有靜音」；`mark`「已加標記 N」。<計時> 照 `clockText`。
- 五個寫法都不接參數、沒有寫法旗標；不讀不寫 `record.defaults.json`、`menubar.prefs.json`。

### R2-§3 資料契約（§3.9–§3.14）

#### 3.9 `~/.meeting-harness/record.control.json` 與 `record.control.lock`（ADR `adr-r2-control-file.md`）

```json
{ "schemaVersion": 1, "runId": "00000000-0000-4000-8000-000000000001", "paused": false, "micMuted": false, "markerSeq": 0 }
```
- 鍵恰為上列 5 個；寫者一律在持有 `<home>/record.control.lock` 的 `flock(LOCK_EX)` 時 read-modify-write，以同目錄 tmp＋rename 寫入。
- 寫者：menu bar 與 `bin/record.sh`（`requestControl` 語意，§3.14）；錄製實例只在開錄時重設（`resetControl`）。控制檔的 `runId` 與 `record.status.json.runId` 不同時，寫者從 `freshControl(runId:)` 起算。
- 錄製實例只採信 `runId` 與自己相同、`schemaVersion == 1` 的內容；`markerSeq` 是本場累計的「要求加標記次數」。

#### 3.10 `record.status.json` 的 R2 選用欄位（ADR `adr-r2-status-fields.md`）

| 欄位 | 型別 | 寫入時機與語意 |
|---|---|---|
| `controlVersion` | int | `phase` 轉 `recording` 時寫 1；舊版錄製器沒有此鍵＝不支援控制 |
| `recordingStartedAt` | string（ISO 8601，同 `startedAt` 格式） | `startCapture` 成功、`phase` 轉 `recording` 的時刻（計時起點；`startedAt` 不變，仍是 preflight 開始時刻） |
| `paused` | bool | 目前是否暫停 |
| `micMuted` | bool | 目前麥克風是否靜音 |
| `pausedSeconds` | number（小數 3 位） | 已結束的暫停總長＝`pausedTotal(pauseEvents)` |
| `pausedAt` | string（ISO 8601） | 目前這次暫停的開始時刻（使用者動作的時間）；沒在暫停時**沒有此鍵** |
| `markers` | int | 已記錄的標記數 |
| `recentLevels` | object `{windowSeconds, system, mic}` | `windowSeconds` 固定 3；`system`／`mic`＝該路 `levels` 最後 6 個 0.5 秒時段的最大值（dBFS，小數 1 位），全為 null 時寫 null；麥克風靜音中 `mic` 為 null；暫停中沒有此鍵。錄製實例每秒最多更新一次 |

- **nil 時省略鍵**：這 8 個欄位為 nil 時不寫進 JSON（`Core/Records.swift:3-4`「nil 寫 null」慣例的例外，§6 第 79 條）；`recentLevels` 內部的 `system`／`mic` 仍照慣例寫 null。第一輪的 12 個鍵與其語意不變；`RecordPhase`、`WarningKind` 不加值。

#### 3.11 `record.meta.json` 的事件、`manifest.json` 的 `gapStats.pausedTotal` 與 `levels` 語意

```json
"pauseEvents":   [ { "t": 70.012, "outputT": 69.830, "wallClock": "2026-10-12T21:01:10+08:00", "kind": "pause" },
                   { "t": 100.004, "outputT": 69.830, "wallClock": "2026-10-12T21:01:40+08:00", "kind": "resume" } ],
"micMuteEvents": [ { "t": 60.020, "outputT": 59.838, "wallClock": "2026-10-12T21:01:00+08:00", "muted": true } ]
```
- R2 錄製實例開錄時就寫兩個空陣列，之後每次事件 append 並重寫 meta；Swift 型別為 Optional，nil 時省略鍵（舊場次沒有這兩鍵）。
- `t` 是**錄製時鐘**（與 `segments[].startedAt`、`levels`、`deviceEvents` 同一把尺，含暫停時間）：`kind == pause` 的 `t`＝停止點 E − t0；`kind == resume` 的 `t`＝繼續後新段的 `startedAt`；`micMuteEvents.t`＝錄製實例處理該次控制的時刻。`outputT`＝`outputTime(recordT: t, firstSegmentStart: startedAt_1, pauses: 當下的 pauseEvents)`（成品時間）；`wallClock`＝使用者動作被處理時的本地時間。`pauseEvents` 依時間遞增、`pause`／`resume` 交替、以 `pause` 開頭；最後一筆可以是沒配對的 `pause`（暫停中停止）。
- `manifest.json.gapStats` 新增 `pausedTotal`（number，小數 3 位；finalize 寫，沒有暫停寫 0.0）。`boundaries[k]`：邊界 k→k+1 若有 `kind == resume` 的事件其 `t` 與 `startedAt_{k+1}` 相差 < 0.5 秒（「暫停邊界」），則 g_k＝`startedAt_{k+1} − startedAt_k − audioDuration_k −（該 resume.t − 前一筆 pause.t）`；其餘邊界照 §3.2。`max`、`total` 由調整後的 boundaries 算；`wallClock` 定義不變。
- **`levels` 的 null**（§3.2 的補充）：暫停期間兩路的時段照常補、值為 null；麥克風靜音期間 mic 的時段為 null（數位 0）。凡讀 `levels` 判斷低音量或中斷的判準，都要先排除落在暫停區間（[pause.t, resume.t)，兩路）與靜音區間（[muted=true 的 t, 下一筆 muted=false 的 t)，mic 路；沒有配對的區間延伸到最後）的時段。

#### 3.12 `錄音/tracks/markers.json` 與 `錄音/markers.json`

```json
[ { "t": 95.526, "recordT": 125.700, "wallClock": "2026-10-12T21:02:05+08:00", "label": "標記 1" } ]
```
- 範例與 §3.11 是同一場（`startedAt_1`＝0.182、一次已配對的暫停 70.012→100.004＝29.992 秒）：125.700 − 0.182 − 29.992＝95.526；測試照抄這組數字時預期必須自洽（閘門 2 修正輪更正，原寫 95.512）。
- 頂層是陣列，元素鍵恰為 `t`、`recordT`、`wallClock`、`label`。**`t` 是成品時間**（brief:27「錄到的時間，扣掉暫停」）＝`outputTime(recordT:…)`；`recordT` 是錄製時鐘；`label`＝`markerLabel(N)`＝「標記 N」，N 從 1 起、依記錄順序。
- 錄製實例在第一次標記時建立 `tracks/markers.json`，之後每次以 tmp＋rename 整檔重寫；沒有標記就沒有這個檔。finalize 把它原樣複製到 `錄音/markers.json`（§4.19.3）；兩處內容逐位元組相同。
- `錄音/markers.json` 不是音源副檔名（`bin/meeting.sh:255` 的 `AUDIO_EXTS`、`PreflightRunner.swift:50` 的 `audioExtensions` 都不含 json），不影響場次判斷；summary 端怎麼用是衍生工作（不編號）。

#### 3.13 `~/.meeting-harness/menubar.prefs.json`、`autoprep.log`、通知識別碼

```json
{ "schemaVersion": 1, "root": "/Users/<使用者>/Documents/範例專案", "recentRoots": ["/Users/<使用者>/Documents/範例專案"],
  "autoPrep": false, "lastSession": null, "lastAutoPrepRunId": null }
```
- 鍵恰為上列 6 個；nil 寫 null（`writeJSONAtomically`）。**只有 menu bar 程序寫**（含偏好設定視窗）；`quick-start` 只讀 `root`；`bin/` 不讀不寫。`record.defaults.json` 維持 `record.sh` 單一寫者，Swift 不寫（R2-Q3 使用者決定）。
- `root`＝「存到 ▸」打勾的位置＝偏好設定的「預設存檔位置」；`recentRoots` 最多 5 個、最近的在前、不重複（結尾 `/` 去掉後比較）；`autoPrep` 預設 false；`lastSession`＝menu bar 上次看到成功收尾（`done`、`code 0`）的場次；`lastAutoPrepRunId`＝上次自動前處理過的 `runId`。檔不存在或解不開時以預設值（`root` null、`recentRoots` 空、`autoPrep` false）運作，不得因此擋住 menu bar。
- `autoprep.log`：menu bar 啟動的 `meeting.sh prep` 的 stdout／stderr（append，每次開頭一行時間與場次）。
- 完成通知的識別碼＝`completionNotificationID(runId:)`＝`"mh.complete." + runId`；category＝`"mh.complete"`；動作「在 Finder 顯示」的識別碼＝`"mh.reveal"`。

#### 3.14 Swift `Core/` 的 R2 名稱（test 子任務依此寫紅燈測試，build 段不得改名）

規則同 §3.4：標「預設值」的參數可省略；正式值由呼叫端明寫；module 內部可見即可。第一輪 §3.4 的名稱與簽名不變，以下只列新增與增補。

```swift
// ===== Control.swift（R2 新增）=====
let controlFileName: String                    // "record.control.json"
let controlLockFileName: String                // "record.control.lock"
let controlProtocolVersion: Int                // 1
struct RecordControl: Codable, Equatable {
    var schemaVersion: Int; var runId: String; var paused: Bool; var micMuted: Bool; var markerSeq: Int   // JSON 鍵恰為這 5 個
}
func freshControl(runId: String) -> RecordControl                     // (1, runId, false, false, 0)
enum ControlCommand: String, CaseIterable { case pause, resume, mute, unmute, mark }
func applying(_ cmd: ControlCommand, to c: RecordControl) -> RecordControl
                                                                      // pause → paused = true；resume → false；mute → micMuted = true；unmute → false；
                                                                      // mark → markerSeq + 1；其餘欄位（含 runId、schemaVersion）不變
struct ControlActions: Equatable { var pause: Bool?; var micMute: Bool?; var newMarkers: Int }
func controlActions(applied: RecordControl, requested: RecordControl?) -> ControlActions
                                                                      // requested 為 nil、runId 與 applied 不同、或 schemaVersion != 1 → (nil, nil, 0)；
                                                                      // 否則 pause ＝ requested.paused != applied.paused ? requested.paused : nil；micMute 同理；
                                                                      // newMarkers ＝ max(0, requested.markerSeq − applied.markerSeq)
func readControl(_ url: URL) -> RecordControl?                       // 不存在或解不開 → nil
func resetControl(home: URL, runId: String) throws -> RecordControl  // 取 <home>/record.control.lock 的 flock(LOCK_EX)（上層目錄不存在先建）後寫 freshControl(runId:)
func requestControl(_ cmd: ControlCommand, home: URL, runId: String) throws -> RecordControl
                                                                      // 取同一把鎖；讀控制檔，讀不到或 runId 不同就從 freshControl(runId:) 起算；
                                                                      // applying 後以 writeJSONAtomically 寫回並回傳寫入的內容；不送訊號（訊號由呼叫端送）
enum ControlAvailability: Equatable { case ready(pid: Int32, runId: String), unavailable(message: String) }
func controlAvailability(status: RecordStatus?, recordPid: Int32?, pidAlive: Bool) -> ControlAvailability
                                                                      // 依序判斷、第一個成立者為準：
                                                                      // status 為 nil、recordPid 為 nil、或 pidAlive == false → unavailable("沒有錄製在跑")；
                                                                      // status.pid != recordPid → unavailable("沒有錄製在跑（狀態檔不是這個錄製實例的）")；
                                                                      // phase == preflight → unavailable 訊息含「還在開錄前檢查」；
                                                                      // phase ∈ {stopping, finalizing} → unavailable 訊息含「正在收尾」；
                                                                      // phase 為其他非 recording 值 → unavailable("沒有錄製在跑")；
                                                                      // controlVersion 為 nil 或 < 1 → unavailable 訊息含「舊版錄製器」；
                                                                      // 否則 ready(pid: recordPid, runId: status.runId)
enum PauseEventKind: String, Codable { case pause, resume }
struct PauseEvent: Codable, Equatable { var t: Double; var outputT: Double; var wallClock: String; var kind: PauseEventKind }
struct MicMuteEvent: Codable, Equatable { var t: Double; var outputT: Double; var wallClock: String; var muted: Bool }
struct Marker: Codable, Equatable { var t: Double; var recordT: Double; var wallClock: String; var label: String }
func markerLabel(_ n: Int) -> String                                  // "標記 \(n)"
// ---- 閘門 2 修正輪新增：事件 append 與狀態欄位（§4.17.7、§4.18.9）----
func appendingPauseEvent(_ events: [PauseEvent], kind: PauseEventKind, t: Double, firstSegmentStart: Double, wallClock: String) -> [PauseEvent]
                                                                      // 目前狀態＝最後一筆的 kind（沒有事件視為 resume）；kind 等於目前狀態 → 原樣回傳（冪等，不 append）；
                                                                      // 否則 append 一筆：t 取小數 3 位；outputT＝outputTime(recordT: t, firstSegmentStart:, pauses: events＋這一筆)；wallClock 原樣
struct PauseStatusFields: Equatable { var paused: Bool; var pausedAt: String?; var pausedSeconds: Double }
func pauseStatusFields(_ events: [PauseEvent]) -> PauseStatusFields   // paused＝最後一筆是 pause；pausedAt＝paused 時為最後一筆的 wallClock、否則 nil；
                                                                      // pausedSeconds＝pausedTotal(events)
func applyingPauseFields(_ f: PauseStatusFields, to s: RecordStatus) -> RecordStatus
                                                                      // 只設 paused、pausedAt（nil＝JSON 省略鍵）、pausedSeconds；其餘欄位不變
func appendingMuteEvent(_ events: [MicMuteEvent], muted: Bool, t: Double, firstSegmentStart: Double,
                        pauses: [PauseEvent], wallClock: String) -> [MicMuteEvent]
                                                                      // 目前狀態＝最後一筆的 muted（沒有事件視為 false）；muted 等於目前狀態 → 原樣回傳；
                                                                      // 否則 append 一筆：t 取小數 3 位；outputT＝outputTime(recordT: t, firstSegmentStart:, pauses:)；wallClock 原樣
func pausedTotal(_ events: [PauseEvent]) -> Double                    // Σ（resume.t − 緊接在前的 pause.t）；沒配對的 pause、沒有前導 pause 的 resume 不計；小數 3 位
func outputTime(recordT: Double, firstSegmentStart: Double, pauses: [PauseEvent]) -> Double
                                                                      // 落在暫停區間（pause.t ≤ recordT < 配對的 resume.t，或沒配對的 pause.t ≤ recordT）時以該 pause.t 代替 recordT；
                                                                      // 再減 firstSegmentStart 與「resume.t ≤ 代替後時刻」的已配對暫停長度；< 0 夾成 0；小數 3 位
func recordedSeconds(recordingStartedAt: String, pausedSeconds: Double, pausedAt: String?, now: Date) -> Int?
                                                                      // ISO 8601（internet date time）；任一字串解不開 → nil；
                                                                      // now − recordingStartedAt − pausedSeconds −（pausedAt 非 nil 時再扣 now − pausedAt），向下取整，< 0 夾成 0
func clockText(seconds: Int) -> String                                // < 3600 → "mm:ss"；≥ 3600 → "h:mm:ss"；負值視為 0
func recentPeak(_ windows: [Double?], count: Int) -> Double?          // 取最後 count 個（不足取全部）中非 nil 的最大值；沒有 → nil；正式值 count = 6
func levelIndicatorLine(recent: RecentLevels?, micMuted: Bool, paused: Bool, thresholdDBFS: Double) -> String
                                                                      // 正式值 thresholdDBFS = -60（呼叫端明寫）；比較一律「嚴格大於」
                                                                      // paused → "收音：暫停中"；recent 為 nil → "收音：讀取中…"；
                                                                      // 否則 "收音：系統聲音 " + 標記(system) + "　麥克風 " + (micMuted ? "⊘ 已靜音" : 標記(mic))（兩路之間是全形空白 U+3000）
                                                                      // 標記(v)＝v 非 nil 且 v > 門檻 → "● 有聲"；否則 → "○ 無聲"
let menuBarPrefsFileName: String                                      // "menubar.prefs.json"
struct MenuBarPrefs: Codable, Equatable {
    var schemaVersion: Int; var root: String?; var recentRoots: [String]; var autoPrep: Bool
    var lastSession: String?; var lastAutoPrepRunId: String?          // JSON 鍵恰為這 6 個；nil 寫 null
}
func loadMenuBarPrefs(_ url: URL) -> MenuBarPrefs                    // 不存在或解不開 → MenuBarPrefs(1, nil, [], false, nil, nil)
func saveMenuBarPrefs(_ prefs: MenuBarPrefs, to url: URL) throws     // writeJSONAtomically
func updatedRecentRoots(_ list: [String], adding root: String, limit: Int) -> [String]
                                                                      // root 為空字串 → list 原樣；否則去掉結尾 "/"（"/" 本身除外）、移除與它相同的既有項（同樣去掉結尾 "/" 後比）、
                                                                      // 插到最前、截到 limit 個；正式值 limit = 5
enum RootChoice: Equatable { case use(String), fail(code: Int32, message: String) }
func quickStartRoot(argRoot: String?, prefsRoot: String?, defaultsRoot: String?, isDirectory: (String) -> Bool) -> RootChoice
                                                                      // 依序取第一個非空的 argRoot、prefsRoot、defaultsRoot；都沒有 → fail(2, "還沒有上次的設定：請先在終端機跑一次 meeting record")；
                                                                      // 取到的 isDirectory 為 false → fail(2, "存檔位置不存在：" + 路徑)；否則 use(路徑)
func explicitWindowDecision(hasDefaults: Bool, resolution: WindowResolution) -> QuickStartDecision
                                                                      // hasDefaults == false → fail(2, 與 quickStartDecision 相同的訊息)；
                                                                      // .exact(id)、.reidentified(id) → start(windowID: id)；
                                                                      // .notFound → fail(3, 訊息含「選的視窗已經不在了」)；.ambiguous → fail(3, 訊息含「同名」)
func launchMode(arguments: [String]) -> String                        // arguments 不含 argv[0]；先去掉所有以 "-psn_" 開頭的項；剩下為空 → "menubar"；否則剩下的第一個
enum LoginItemState: String, CaseIterable { case notRegistered, enabled, requiresApproval, notFound }
struct LoginItemDisplay: Equatable { let isOn: Bool; let note: String; let showOpenSettings: Bool }
func loginItemDisplay(_ state: LoginItemState) -> LoginItemDisplay
                                                                      // enabled → (true, "", false)；notRegistered → (false, "", false)；
                                                                      // requiresApproval → (true, 含「系統設定」與「登入項目」的說明, true)；notFound → (false, 含「找不到」的說明, false)
func shouldAutoPrep(autoPrep: Bool, status: RecordStatus?, seenInProgressRunIds: Set<String>, lastAutoPrepRunId: String?) -> String?
                                                                      // 全部成立時回 status.session，否則 nil：autoPrep；status 非 nil；phase == done；code == 0；
                                                                      // seenInProgressRunIds 含 status.runId；status.runId != lastAutoPrepRunId；session 非空
func completionNotificationID(runId: String) -> String                // "mh.complete." + runId
let completionCategoryID: String                                      // "mh.complete"
let revealActionID: String                                            // "mh.reveal"
struct HotKeySpec: Equatable { let id: UInt32; let key: String; let action: String; let display: String }
let r2HotKeys: [HotKeySpec]                                           // 恰為 4 筆、依序：(1, "r", "start", "⌃⌥⌘R")、(2, "m", "mute", "⌃⌥⌘M")、
                                                                      // (3, "p", "pause", "⌃⌥⌘P")、(4, "b", "mark", "⌃⌥⌘B")
struct TriggerDebouncer {
    init(interval: Double)                                            // 正式值 1.0（呼叫端明寫）
    mutating func accept(_ action: String, at t: Double) -> Bool      // 同一 action 距上次「被接受」< interval → false（不更新）；否則 true 並記下 t；不同 action 互不影響
}

// ===== Records.swift（增補）=====
struct RecentLevels: Codable, Equatable { var windowSeconds: Double; var system: Double?; var mic: Double? }   // JSON 鍵恰為 3 個；nil 寫 null
// RecordStatus 新增（宣告為 var、預設 nil、nil 時省略鍵）：
//   controlVersion: Int?、recordingStartedAt: String?、paused: Bool?、micMuted: Bool?、pausedSeconds: Double?、
//   pausedAt: String?、markers: Int?、recentLevels: RecentLevels?
// RecordMeta 新增（同上）：pauseEvents: [PauseEvent]?、micMuteEvents: [MicMuteEvent]?
// GapStats 新增（同上）：pausedTotal: Double?

// ===== Detectors.swift（增補）=====
extension SilenceDetector   { mutating func reset() }                 // 之後的行為與 init(同參數) 的新實例完全相同
extension SuspendedDetector { mutating func reset() }                 // 同上
extension BlackDetector     { mutating func interrupt(at t: Double) } // 若最後一個區間的 end 為 nil 就設成 t；連續計數歸零（之後的開區間判斷與新實例相同）；已記錄的區間保留
struct DetectorFeed: Equatable { let systemSilence: Bool; let micSilence: Bool; let black: Bool; let suspended: Bool }   // 閘門 2 修正輪新增（§4.18.10）
func detectorFeed(paused: Bool, micMuted: Bool) -> DetectorFeed       // paused → 四項皆 false（不論 micMuted）；否則 micMuted → (true, false, true, true)；否則四項皆 true

// ===== Segments.swift（增補；閘門 2 修正輪新增，§4.18.8）=====
enum SwitchReason: String, CaseIterable { case first, periodic, formatChange, writerFailure, resume }
                                                                      // 自 Capture/RecordingSession.swift:28 的 private enum 搬來並加 resume；
                                                                      // Capture/ 不得再宣告 SwitchReason（改用本型別）
struct PauseGate: Equatable {
    var paused: Bool = false                                          // 暫停中
    var cutPoint: Double? = nil                                       // 停止點 E（sample PTS 秒數，與 maxEnd 同一把尺）；暫停前還沒有任何 sample 時為 nil
    var resumePending: Bool = false                                   // 已繼續、還在等第一個 PTS ≥ E 的 sample 開新段
}
enum PauseSampleRoute: Equatable { case normal, prevOnly, drop, resumeBoundary }
func pausing(_ g: PauseGate, maxEnd: Double?, segmentStart: Double?) -> PauseGate
                                                                      // g.paused → 原樣；否則 (paused true, cutPoint＝maxEnd ?? segmentStart, resumePending false)
func resuming(_ g: PauseGate) -> PauseGate                            // !g.paused → 原樣；否則 (paused false, cutPoint 不變, resumePending true)
func pauseRoute(_ g: PauseGate, sampleStart: Double) -> PauseSampleRoute
                                                                      // g.paused 或 g.resumePending 時：cutPoint 非 nil 且 sampleStart < cutPoint → prevOnly（只寫進還開著的 prev，沒有 prev 就丟）；
                                                                      //   否則 paused → drop；resumePending → resumeBoundary；
                                                                      // 其餘 → normal
func segmentOpened(_ g: PauseGate) -> PauseGate                       // resumePending → false、cutPoint → nil；paused 不變
func openReason(route: PauseSampleRoute, hasCurrent: Bool, everOpened: Bool, switchOnNextSample: Bool) -> SwitchReason?
                                                                      // prevOnly、drop → nil（暫停中不因 cur == nil 自動開段）；
                                                                      // resumeBoundary → everOpened ? resume : first；
                                                                      // normal 且 (!hasCurrent || switchOnNextSample) → everOpened ? writerFailure : first；
                                                                      // normal 其餘 → nil（定期換段與格式變更換段仍由呼叫端照第一輪判斷）
// 呼叫端（Capture）的規則：route ∈ {prevOnly, drop} 時不更新 maxEnd；route ∈ {normal, resumeBoundary} 照第一輪更新。

// ===== AudioLevel.swift（增補）=====
func zeroedAudioSample(_ sb: CMSampleBuffer) -> CMSampleBuffer?       // 深拷貝資料緩衝並全部清 0；frame 數、PTS、duration、format description 與原緩衝相同；
                                                                      // 不改原緩衝；拿不到資料緩衝 → nil

// ===== Trigger.swift（增補）=====
// MenuBarState 新增 case paused（rawValue "paused"）；symbolName：paused → "pause.circle.fill"（其他三態不變）
// MenuBarModel 新增（var、有預設值）：timerText: String = ""、paused: Bool = false、micMuted: Bool = false、
//   canControl: Bool = false、levelLine: String = ""
// menuBarModel(status:pidAlive:now:) 的簽名不變；R2 規則見 §3.14.1
```

#### 3.14.1 `menuBarModel` 的 R2 規則（增補 §3.4.1；列名不重新編號）

- **M6b**（新列，排在 M6a 之後、M7 之前）：`phase == recording`、`pidAlive == true`、`paused == true` → `state` paused；`statusLine` 含「已暫停」＋計時＋場次名，有告警類時再加「（告警 N 則）」（N＝告警數）；`canStart` false、`canStop` true、`canOpenSession` true。排在 M7 前的理由：舊告警不得蓋掉暫停狀態。
- **M9 的計時**：狀態檔有 `recordingStartedAt` 時，計時＝`clockText(recordedSeconds(...))`；沒有時沿用第一輪的 `now − startedAt`（舊狀態檔）。`micMuted == true` 時 `statusLine` 另含「麥克風靜音中」。
- **R2 欄位**：只在 `phase == recording` 且 `pidAlive == true` 的列（M6b、M7、M9）設定：`timerText`＝與狀態列相同的計時字串；`paused`＝`status.paused ?? false`；`micMuted`＝`status.micMuted ?? false`；`canControl`＝`(status.controlVersion ?? 0) ≥ 1`；`levelLine`＝`levelIndicatorLine(recent: status.recentLevels, micMuted:, paused:, thresholdDBFS: -60)`。其他列一律是預設值。
- 全表（M1–M10、M6a、M6b 共 12 列）的 `statusLine` 不得含 `RecordPhase`、`WarningKind`、`ControlCommand`、`PauseEventKind` 的 raw value；`accessibilityText` 規則不變（paused 態也加「MeetingRecorder：」前綴）。

### 4.16 控制通道與 CLI 五個子指令（F1、F2、F6 的共同通道；R2-Q4、R2-Q5、R2-Q11）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.16.1 | `applying` 應：對 `freshControl(runId: "r")` 依序套 pause、pause、mute、mark、mark、resume、unmute，每步只改該命令的欄位（第二次 pause 不變；兩次 mark 後 `markerSeq` 為 2），`runId`、`schemaVersion` 全程不變。`controlActions` 應：(applied (r,F,F,0), requested (r,T,F,2)) → (true, nil, 2)；requested 與 applied 相同 → (nil, nil, 0)；requested 的 runId 為 "x" → (nil, nil, 0)；requested 為 nil → (nil, nil, 0)；requested `schemaVersion` 2 → (nil, nil, 0)；requested `markerSeq` 小於 applied → `newMarkers` 0；(applied (r,T,T,3), requested (r,F,F,3)) → (false, false, 0)。 | brief:35；design R2-D2 | `swift:ControlTests.swift::testApplyingCommands`、`::testControlActions` |
| 4.16.2 | 在不存在的暫存 home 下，`requestControl(.pause, home:, runId: "r")` 應建立目錄與 `record.control.json`（JSON 鍵恰為 5 個、`paused` true、`runId` "r"）並留下 `record.control.lock`；控制檔 `runId` 為 "old" 且 `paused` true 時 `requestControl(.mark, runId: "r")` 應回 (1, "r", false, false, 1)；連續兩次 `.mark` 後 `markerSeq` 為 2；`resetControl(home:, runId: "r2")` 應把檔覆寫成 `freshControl(runId: "r2")`；`readControl` 對不存在的檔與內容為 `{` 的檔回 nil；寫完後目錄裡不得留 tmp 檔。 | §3.9；R2-Q11 | `swift:ControlTests.swift::testRequestAndResetControlFile` |
| 4.16.3 | `controlAvailability` 應依 §3.14 的順序回傳：status nil、recordPid nil、pidAlive false 各回含「沒有錄製在跑」；`status.pid` 4242、recordPid 4243 → 含「狀態檔不是這個錄製實例的」；`phase` preflight → 含「還在開錄前檢查」；stopping、finalizing → 含「正在收尾」；done、failed、preflight_failed → 含「沒有錄製在跑」；recording 但 `controlVersion` nil 或 0 → 含「舊版錄製器」；recording、`controlVersion` 1、pid 相符 → `.ready(pid: 4242, runId:)`。 | R2-Q4；ADR `adr-r2-control-file.md` | `swift:ControlTests.swift::testControlAvailability` |
| 4.16.4 | 錄製實例應在 `installSignalHandlers()` 內以與 SIGTERM 相同的 `DispatchSource` 模式加裝 SIGUSR1，收到時在序列佇列 `q` 上 `readControl` → `controlActions` → 套用；`start()` 中的順序應為 `installSignalHandlers()` → `resetControl(` → 寫 `record.pid`。`main.swift` 應在子指令分派（`switch`）之前執行 `signal(SIGUSR1, SIG_IGN)`。 | R2-Q4、R2-Q11；`RecordingSession.swift:130`、`:156`、`:228-239` | `tests/record/test_r2_static.py::test_capture_sigusr1_handler_before_pid`、`::test_main_ignores_sigusr1_before_dispatch` |
| 4.16.5 | 當 `fake_recorder.sh` 以 `FAKE_CONTROL=1` 執行（狀態檔含 `controlVersion` 1、收到 SIGUSR1 時依控制檔更新 `paused`／`micMuted`／`markers`）時：`meeting.sh record pause` 應回 0、stdout 含「已暫停」、控制檔 `paused` true 且 `runId` 等於狀態檔的 `runId`、替身收到恰 1 次 SIGUSR1；再跑一次 `pause` 應回 0、stdout 含「已經是暫停中」、替身沒有再收到訊號；`resume`、`mute`、`unmute` 各回 0 且控制檔與狀態檔一致；`mark` 連跑兩次各回 0、stdout 依序含「已加標記 1」「已加標記 2」、控制檔 `markerSeq` 2；每次呼叫後 `<home>/record.control.lock` 存在。`EXIT_CODE_CASES` 應新增這五個寫法回 0 的案例（`setup` 代號 `running_controllable`）。 | R2-§2.2；brief:37 | `tests/record/test_r2_cli.py::test_control_commands_with_fake_recorder`、`::test_control_idempotent_no_signal`、`::test_mark_increments`；`test_record_sh.py::test_exit_code_matrix` |
| 4.16.6 | 五個寫法都應在下列情境回 3、stderr 含 §3.14 對應字樣、且不改控制檔：沒有 `record.pid`；替身狀態 `phase` 為 `preflight`、`stopping`、`finalizing`；以 `FAKE_CONTROL` 未設定的替身（舊版：狀態檔沒有 `controlVersion`、也沒有裝 SIGUSR1 處理）執行時，CLI 應回 3、含「舊版錄製器」，且呼叫結束後替身程序仍活著（沒有被 SIGUSR1 殺掉）。`EXIT_CODE_CASES` 應新增五個寫法回 3 的案例（沒有錄製在跑）。 | R2-Q4；R2-§2.2 | `test_r2_cli.py::test_control_unavailable_exit_3`、`::test_old_recorder_not_signalled`；`test_record_sh.py::test_exit_code_matrix` |
| 4.16.7 | 以 `FAKE_CONTROL=ignore`（有 `controlVersion` 1、但忽略 SIGUSR1、狀態不反映）的替身執行 `record pause` 時，應在 5 秒以上、10 秒以內回 3，stderr 含「沒有回應」。 | R2-§2.2；design R2-D2 | `test_r2_cli.py::test_control_no_response_exit_3` |
| 4.16.8 | 五個寫法各加一個多餘位置參數（例 `record pause x`）應回 2；各加 `--no-such-flag` 應回 2 且 stderr 含「未知的選項」。目前目錄有名為 `pause` 的資料夾時，`meeting.sh record ./pause`（以 `MH_RECORD_OPEN` 替身）應走開錄流程（替身收到的參數含 `start` 或 `preflight`），而不是控制流程。 | R2-Q5（保留字）；§2.4.2 | `test_r2_cli.py::test_control_extra_args_exit_2`、`::test_reserved_words_dot_slash_root`；`test_cli_dispatch.py::test_record_unknown_flag_exits_2` |
| 4.16.9 | `meeting record status` 在替身狀態為錄製中且含 `recordingStartedAt`（現在 − 125 秒）、`pausedSeconds` 5 時，應印「錄製中 02:00」（容許 ±1 秒，即 01:59–02:01）；`paused` true、`pausedAt` 現在 − 10 秒時應含「暫停中」；`micMuted` true 時含「麥克風靜音中」；`markers` 2 時含「標記 2 個」。狀態檔沒有這些鍵時輸出與第一輪相同。 | design R2-D11；R2-Q12 | `test_r2_cli.py::test_status_shows_pause_mute_markers` |
| 4.16.10 | `RecordStatus` 的 R2 欄位全為 nil 時 JSON 鍵應恰為第一輪的 12 個（既有 `testStatusJSONKeys` 不改）；8 個欄位都有值時應恰為 20 個（12＋`controlVersion`、`recordingStartedAt`、`paused`、`micMuted`、`pausedSeconds`、`pausedAt`、`markers`、`recentLevels`），`recentLevels` 的鍵恰為 `windowSeconds`、`system`、`mic` 且 `mic` 為 nil 時寫 null；往返 JSON 後相等；第一輪格式（12 鍵）的 JSON 解得回來、R2 欄位為 nil。`GapStats` 的 `pausedTotal` 為 nil 時鍵恰為第一輪的 4 個、有值時 5 個。`RecordControl` 往返 JSON 後相等、鍵恰為 5 個。 | §3.9、§3.10；ADR `adr-r2-status-fields.md` | `swift:ControlTests.swift::testStatusR2Keys` |
| 4.16.11 | 當 `meeting record stop` 收尾成功、且場次 `錄音/tracks/record.meta.json` 的 `pauseEvents` 有 kind 為 pause 的事件或最終狀態檔的 `markers` > 0 時，`stop` 的摘要應多印恰一行「暫停 N 次、共 mm:ss；標記 M 個」：N＝`pauseEvents` 中 kind 為 pause 的筆數；共＝`pausedTotal`（只計已配對，向下取整秒，`mm:ss`）；M＝狀態檔 `markers`（沒有此鍵為 0）。合成：`pauseEvents` [pause 70.0, resume 100.0, pause 150.0]、`markers` 2 → stdout 含「暫停 2 次、共 00:30；標記 2 個」；`pauseEvents` 為空陣列、`markers` 1 → 含「暫停 0 次、共 00:00；標記 1 個」；meta 沒有 `pauseEvents` 鍵且狀態檔沒有 `markers` 鍵 → stdout 不含「次、共」（第一輪摘要不變，既有 `test_stop_prints_black_intervals` 不改且全綠）。結束碼規則不變。 | design R2-D11 | `test_r2_cli.py::test_stop_summary_pause_markers`；`test_record_sh.py::test_stop_prints_black_intervals`（不改） |

### 4.17 只靜音麥克風（F1，brief:22）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.17.1 | `zeroedAudioSample` 應：對 Float32、非交錯、雙聲道、48 kHz、480 frame 的正弦波緩衝，以及 Int16、交錯、單聲道、16 kHz、160 frame 的緩衝，各回非 nil；結果的資料位元組全為 0、`CMSampleBufferGetNumSamples`、PTS、duration 與原緩衝相同、format description 相等（`CMFormatDescriptionEqual`）；原緩衝的資料不變（仍有非 0 值）；`rmsDBFS(sampleBuffer:)` 對結果回 -∞。 | brief:22；design R2-D4 | `swift:ControlTests.swift::testZeroedAudioSample` |
| 4.17.2 | 在麥克風靜音期間，錄製實例應在 mic 緩衝算 `rmsDBFS` 之前以 `zeroedAudioSample` 取代原緩衝並照常寫進 mic 軌（軌道不中斷）、不餵 `micSilence`；取消靜音時應呼叫 `micSilence.reset()`；每次切換應 append 一筆 `micMuteEvents` 並重寫 meta、更新狀態檔 `micMuted`；系統聲音路不受影響。實作形狀：`RecordingSession.swift` 的 sample 回呼函式本體中 `zeroedAudioSample(` 出現在 `rmsDBFS(sampleBuffer:` 之前；檔內含 `micSilence.reset()`、`micMuteEvents`。 | brief:22；design R2-D4 | `test_r2_static.py::test_capture_mic_zeroed_before_rms`；人工 t7（§4.25） |
| 4.17.3 | `RecordMeta` 的 `pauseEvents`、`micMuteEvents` 都為 nil 時 JSON 鍵應恰為第一輪的 7 個；兩者為空陣列時應恰為 9 個；`MicMuteEvent` 的鍵恰為 `t`、`outputT`、`wallClock`、`muted`，`PauseEvent` 恰為 `t`、`outputT`、`wallClock`、`kind`（`kind` 為 "pause"／"resume"）；含事件的 meta 往返 JSON 後相等；第一輪格式（沒有這兩鍵）的 meta JSON 解得回來、兩欄為 nil。 | §3.11；ADR `adr-r2-status-fields.md` | `swift:ControlTests.swift::testMetaR2EventKeys` |
| 4.17.4 | `SilenceDetector.reset()`、`SuspendedDetector.reset()`：對同一串 feed 序列，reset 之後的實例與 `init(同參數)` 的新實例回傳值逐一相同（序列：-80 dBFS 每 0.5 秒餵 10 秒 → reset → 再餵 20 秒；suspended 同理）。`BlackDetector.interrupt(at:)`：已開啟（`end` 為 nil）的區間之後 `end` 等於 t；沒有開啟區間時 `intervals` 不變；interrupt 之後再餵 3 秒低於門檻的樣本不得新開區間（連續計數已歸零，正式值 5 秒）。 | design R2-D3、R2-D4 | `swift:ControlTests.swift::testDetectorResets` |
| 4.17.5 | `e2e_check.py --pause-mute <場次>` 應包含：`mic_mute_zero`——每個靜音區間 [mute.t＋0.2, unmute.t − 0.2]（沒配對延伸到最後一段結束）在對應段落 `tracks/seg-*.mov` 的麥克風軌（第 3 條軌）解碼後樣本絕對值最大為 0；`mute_system_kept`——同區間系統聲音軌至少有一個 0.5 秒窗的峰值 > -60 dBFS；`micMuteEvents` 為空時兩者都判 FAIL 並說明「情境未觸發」（不得判 PASS）。合成場次：靜音區間 mic 全 0 → PASS；其中混入一個非 0 樣本 → FAIL。 | brief:62-63；design R2-D12 | `tests/record/test_r2_e2e_check.py::test_mic_mute_zero_check`；人工 t7 |
| 4.17.6 | `e2e_check.py --pause-mute` 應包含 `no_false_silence`：`record.status.json`（`--status` 或 `MH_RECORD_HOME`，同 `hfp`）的 warnings 中，不得有 `silence_mic` 的 `t` 落在任何靜音區間 [mute.t, unmute.t＋1]，也不得有 `silence_system`／`silence_mic` 落在任何暫停區間 [pause.t, resume.t＋1]；找不到該場次的狀態檔時判 FAIL 並說明。 | brief:65 | `test_r2_e2e_check.py::test_no_false_silence_check`；人工 t7 |
| 4.17.7 | `appendingMuteEvent` 應：([], muted true, t 60.0204, firstSegmentStart 0.182, pauses [], wallClock w) → 一筆 (60.020, 59.838, w, true)；對該結果再 append muted true → 原樣（1 筆）；([], muted false, …) → []；pauses 為 [pause t 70.012] 時 append (muted true, t 80.0) → 該筆 `outputT` 69.830；[mute] 之後 append muted false → 2 筆、第二筆 `muted` false。 | §3.11、§3.14；brief:22 | `swift:ControlTests.swift::testAppendingMuteEvent` |
| 4.17.8 | `e2e_check.py --pause-mute` 應包含 `mute_timing`：把各段 `tracks/seg-*.mov` 的麥克風軌（第 3 條軌）依 `startedAt` 接成錄製時鐘上的序列，對每個靜音區間 [m, u)（m＝muted true 的 t、u＝下一筆 muted false 的 t；沒配對時 u＝最後一段結束、不檢查結束端），找出包含 [m＋0.2, u − 0.2] 的最長「樣本全為 0」區段 [zs, ze]，判準 \|zs − m\| ≤ 0.5 且（有配對時）\|ze − u\| ≤ 0.5；zs 早於 m − 0.5 且延伸到該段開頭時說明「靜音前麥克風也是數位 0，無法判定時刻」並判 FAIL；`micMuteEvents` 為空時判 FAIL（情境未觸發）。合成場次：m 10.0、u 20.0、mic 在 [10.0, 20.0) 為 0、其餘為正弦波 → PASS；mic 改在 [8.0, 20.0) 為 0（事件記晚 2 秒）→ FAIL；mic 在 [10.0, 22.0) 為 0 → FAIL。 | intent R2-2 t7「micMuteEvents 的時間正確」；brief:62-63 | `test_r2_e2e_check.py::test_mute_timing_check`；人工 t7 |

### 4.18 整段暫停／繼續（F2，brief:14、:23）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.18.1 | `pausedTotal` 應：[pause 70, resume 100, pause 150] → 30.0；[] → 0；[resume 5] → 0。`outputTime`（firstSegmentStart 0.2、pauses [pause 70, resume 100]）應：recordT 50 → 49.8；80 → 69.8；130 → 99.8；0.1 → 0；pauses 再加 [pause 150] 時 recordT 160 → 119.8。 | §3.11；design R2-D5 | `swift:ControlTests.swift::testPausedTotalAndOutputTime` |
| 4.18.2 | 在暫停期間，錄製實例應：以停止點 E 收掉目前段落（轉成 prev、只收 PTS < E 的 sample；沒有內容就捨棄並從 manifest 移除）；丟棄 PTS ≥ E 的 sample 且不更新 `maxEnd`；不得因 `cur == nil` 自動開新段；照常更新最後一個 complete 幀（不寫入）；不餵靜音、黑畫面、suspended 偵測器；照常每 30 秒檢查磁碟。繼續時應以下一個 PTS ≥ E 的 sample 為邊界開新段（`SwitchReason` 新增 `resume`），新段首幀以最後一個 complete 幀重新打戳，並重設靜音與 suspended 偵測器。上述判斷一律經 §3.14 的 Core 純函式（`pausing`、`resuming`、`pauseRoute`、`segmentOpened`、`openReason`、`detectorFeed`；換段原因用 Core 的 `SwitchReason`），行為以 §4.18.8、§4.18.10 的單元測試為準。實作形狀：`ingest` 函式本體中第一個 `pauseRoute(` 出現在 `maxEnd =` 之前；`Sources/Capture/` 下沒有任何一行宣告 `enum SwitchReason`；`RecordingSession.swift` 含 `pausing(`、`resuming(`、`segmentOpened(`、`openReason(`、`detectorFeed(`、`.interrupt(at:`、`sysSilence.reset()`、`micSilence.reset()`。 | ADR `adr-r2-pause-cut.md`；design R2-D3 | `test_r2_static.py::test_capture_pause_gate_before_maxend`、`::test_capture_uses_core_pause_functions`；`swift:ControlTests.swift::testPauseGateAndSwitchReason`、`::testDetectorFeed`（行為）；人工 t7 |
| 4.18.3 | 每次暫停與繼續，錄製實例應 append 一筆 `pauseEvents`（§3.11 的 `t` 定義）並更新狀態檔：暫停時 `paused` true、`pausedAt` 為當下；繼續時 `paused` false、刪除 `pausedAt`、`pausedSeconds`＝`pausedTotal(pauseEvents)`。暫停中按停止應照常收尾，`pauseEvents` 最後一筆為 `pause`。事件 append 與狀態欄位一律經 `appendingPauseEvent`、`pauseStatusFields`、`applyingPauseFields`（行為見 §4.18.9）；實作形狀：`RecordingSession.swift` 含這三個名稱與 `appendingMuteEvent(`。暫停前還沒有任何 sample（`cutPoint` 為 nil）時 pause 事件的 `t` 記 0.000。 | §3.10、§3.11；brief:23 | `swift:ControlTests.swift::testPauseEventsAndStatusFields`；`test_r2_static.py::test_capture_uses_core_pause_functions`；人工 t7（`e2e_check.py --pause-mute` 的 `pause_events`、`event_output_t`） |
| 4.18.4 | `_record_finalize.py` 對合成場次（2 段：seg-0001 約 10 秒、`startedAt` 0.0；seg-0002 約 7 秒、`startedAt` 40.0；`record.meta.json.pauseEvents` 為 [pause t≈10.0, resume t=40.0]）應回 0；`gapStats.boundaries[0]` 絕對值 < 0.05、`pausedTotal` 等於 30.0（±0.01）；成品 `錄音/*.wav` 長度在 17 ± 0.5 秒。沒有 `pauseEvents` 的場次：`pausedTotal` 為 0.0，其餘 `gapStats` 欄位與 §3.2 的算法相同（既有 `test_finalize.py` 全部預期不變）。 | design R2-D12；R2-Q9 | `tests/record/test_r2_finalize.py::test_gapstats_subtracts_pause`、`::test_gapstats_no_pause_unchanged` |
| 4.18.5 | `e2e_check.py` 的既有判準在有 `pauseEvents` 時應：`gap` 以 §3.11 調整後的 g 判（`wall <= 240` 的短場次分界改用 wall − `pausedTotal`）；`segment_cadence` 把「startedAt_{i+1} 與某筆 resume.t 相差 < 0.5 秒」的邊界列為提前換段（不受 60.000 秒約束）；`stop_tail` 比較 `wallClock` 與 `startedAt_1 + Σ audioDuration + pausedTotal`，若 `pauseEvents` 最後一筆是 pause，則以它的 `t` 代替 `wallClock`。合成場次（含一次 30 秒暫停、或暫停中停止）三項判 PASS；把 resume.t 改到與 `startedAt_{i+1}` 相差 2 秒時 `gap` 判 FAIL。沒有 `pauseEvents` 的場次結果與修改前相同（既有 `test_e2e_check.py` 一字不改且全綠）。 | §4.4.3、§4.4.8 的補充；design R2-D12 | `test_r2_e2e_check.py::test_pause_aware_segment_checks`；`test_e2e_check.py`（全部，不改） |
| 4.18.6 | `e2e_check.py --pause-mute` 應包含：`pause_events`——`pauseEvents` 非空、依時間遞增、`pause`／`resume` 交替且以 `pause` 開頭；每筆 pause 的 t 與某段 i 的結束（`startedAt_i + audioDuration_i`）相差 < 0.5 秒；每筆 resume 的 t 與某段 `startedAt` 相差 < 0.5 秒；`pause_cut`——`錄音/*.wav` 長度與（停止點 − `startedAt_1` − `pausedTotal`）相差 < 1 秒，停止點＝最後一段 `startedAt + audioDuration`。`pauseEvents` 為空時兩者判 FAIL（情境未觸發）。 | brief:61-62、:64 | `test_r2_e2e_check.py::test_pause_cut_and_events_check`、`::test_pause_mute_requires_events`；人工 t7 |
| 4.18.7 | 讀 `levels` 的判準（`device_switch`、`hfp` 的低音量與 `quiet_outside`、`interruption_report`）應排除 §3.11 定義的暫停區間（兩路）與靜音區間（mic 路）的時段；讀混音軌（成品）的量測應先以 `outputTime` 把事件的錄製時鐘換成成品時間。合成場次：只有暫停或靜音造成的 null 段（> 3 秒）時 `device_switch`、`hfp` 的低音量部分不判 FAIL；同樣長度的 null 段不在任何區間內時仍判 FAIL。 | §3.11；§6 第 66 條的延伸 | `test_r2_e2e_check.py::test_levels_checks_exclude_pause_and_mute` |
| 4.18.8 | `SwitchReason.allCases` 應恰為 first、periodic、formatChange、writerFailure、resume 五個。設 g0＝`PauseGate()`：`pauseRoute(g0, sampleStart: 5)` → normal；`openReason(route: .normal, hasCurrent: false, everOpened: false, switchOnNextSample: false)` → first；(normal, false, true, false) → writerFailure；(normal, true, true, true) → writerFailure；(normal, true, true, false) → nil。g1＝`pausing(g0, maxEnd: 70.0, segmentStart: 60.0)` → (true, 70.0, false)；`pausing(g1, maxEnd: 75, segmentStart: 60)` 等於 g1；`pausing(g0, maxEnd: nil, segmentStart: 60.0).cutPoint` 為 60.0；兩者皆 nil 時 `cutPoint` 為 nil。`pauseRoute(g1, 69.9)` → prevOnly；(g1, 70.0) → drop；(g1, 90.0) → drop；route 為 prevOnly 或 drop 時 `openReason`（hasCurrent false、everOpened true）→ nil。g2＝`resuming(g1)` → (false, 70.0, true)；`resuming(g0)` 等於 g0；`pauseRoute(g2, 69.95)` → prevOnly；(g2, 100.0) → resumeBoundary；`openReason(route: .resumeBoundary, hasCurrent: false, everOpened: true, …)` → resume、everOpened false → first；`segmentOpened(g2)` 等於 `PauseGate()`。`cutPoint` 為 nil 的暫停：任何 sampleStart 都是 drop；繼續後任何 sampleStart 都是 resumeBoundary。 | intent R2-2〈可以判定的成果〉「resume 換段」；ADR `adr-r2-pause-cut.md`；design R2-D3 | `swift:ControlTests.swift::testPauseGateAndSwitchReason` |
| 4.18.9 | `appendingPauseEvent`（firstSegmentStart 0.182）應：([], pause, t 70.0124, w1) → 一筆 (70.012, 69.830, w1, pause)；再 append pause → 原樣；([], resume, …) → []；[pause 70.012] 後 append (resume, 100.004, w2) → 第二筆 `outputT` 69.830。`pauseStatusFields` 應：[] → (false, nil, 0)；[pause(w1)] → (true, w1, 0)；[pause 70.012, resume 100.004] → (false, nil, 29.992)；再加 [pause 150.0 (w3)] → (true, w3, 29.992)。`applyingPauseFields((false, nil, 29.992), to:)` 對一個 `pausedAt` 為 "x"、`paused` true、`markers` 3 的 `RecordStatus` → `paused` false、`pausedSeconds` 29.992、`markers` 仍 3，編成 JSON 後沒有 `pausedAt` 鍵。 | §3.10、§3.11；intent R2-2 | `swift:ControlTests.swift::testPauseEventsAndStatusFields` |
| 4.18.10 | `detectorFeed` 應：(paused false, micMuted false) → 四項皆 true；(false, true) → (true, false, true, true)；(true, false) 與 (true, true) → 四項皆 false。 | intent F2「暫停期間不誤報靜音、黑畫面」；design R2-D3、R2-D4 | `swift:ControlTests.swift::testDetectorFeed` |
| 4.18.11 | `e2e_check.py --pause-mute` 應包含 `no_false_black`：場次 `manifest.json` 的 `blackIntervals` 中，不得有 `start` 落在任何暫停區間 [pause.t, resume.t＋1]（沒配對的 pause 延伸到最後一段結束）；`record.status.json`（同 §4.17.6 的取得方式）的 warnings 中，不得有 kind 為 `black` 或 `suspended` 的 `t` 落在同樣的區間；`pauseEvents` 為空時判 FAIL（情境未觸發）；找不到狀態檔時判 FAIL 並說明。合成場次：暫停 [70, 100]、`blackIntervals` [{start 80, end 85}] → FAIL；[{start 120, end 130}] → PASS；warnings 含 {t 90, kind black} → FAIL。 | intent F2；brief:65 | `test_r2_e2e_check.py::test_no_false_black_check`；人工 t7 |
| 4.18.12 | `e2e_check.py --pause-mute` 應包含 `event_output_t`：`pauseEvents` 與 `micMuteEvents` 的每一筆，`outputT` 與 `record_to_output(t, startedAt_1, pauseEvents)`（語意同 Core `outputTime`；只用到 t 之前的暫停，所以用整場的 `pauseEvents` 算與事件當下算結果相同）相差 ≤ 0.01 秒；兩個陣列都為空時判 FAIL（情境未觸發）。合成場次：§3.11 範例（`startedAt_1` 0.182）→ PASS；把 mute 的 `outputT` 改成 59.900 → FAIL。 | §3.11；intent R2-2 t7「時間正確」 | `test_r2_e2e_check.py::test_event_output_t_check`；人工 t7 |

### 4.19 標記（F6，brief:27）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.19.1 | `markerLabel(3)` 應為「標記 3」；`Marker` 的 JSON 鍵恰為 `t`、`recordT`、`wallClock`、`label`，往返 JSON 後相等。 | §3.12 | `swift:ControlTests.swift::testMarkerShape` |
| 4.19.2 | 每次 `newMarkers > 0`，錄製實例應依序加入 N＝現有數＋1…的標記（`label`＝`markerLabel(N)`、`recordT`＝當下錄製時鐘、`t`＝`outputTime(recordT:…)`；暫停中則 `t` 為該次暫停點的成品時間）、以 tmp＋rename 重寫 `tracks/markers.json`、更新狀態檔 `markers`。實作形狀：`RecordingSession.swift` 含 `"markers.json"`、`markerLabel(`、`outputTime(`。 | brief:27；design R2-D5 | `test_r2_static.py::test_capture_markers_written`；人工 t7 |
| 4.19.3 | `_record_finalize.py` 應在 `already_done` 判斷之前把 `tracks/markers.json` 複製成 `錄音/markers.json`：首次收尾後兩檔逐位元組相同；第二次 `meeting record finish`（已完成、冪等）時 `錄音/markers.json` 不被重寫（mtime 不變）；已完成的場次之後才出現 `tracks/markers.json`（或被刪的 `錄音/markers.json`）時，再跑一次 finish 應補上；沒有 `tracks/markers.json` 時不建 `錄音/markers.json`。只有 `錄音/markers.json`、沒有音源檔的場次不得被 `meeting status <根>` 列為場次。 | brief:27；`cc:` C14；§4.4.2 | `test_r2_finalize.py::test_markers_copied_and_idempotent`、`::test_markers_copied_on_already_done`、`::test_markers_absent_no_file`、`::test_markers_not_listed_as_session` |
| 4.19.4 | `e2e_check.py --pause-mute` 應包含 `markers`：`錄音/markers.json` 存在且與 `tracks/markers.json` 相同；`label` 依序為「標記 1」…；`t` 不遞減、0 ≤ t ≤ wav 長度；每筆 `t` 與 `outputTime(recordT, startedAt_1, pauseEvents)` 相差 ≤ 0.01 秒；沒有 markers 檔時判 FAIL（情境未觸發）。 | brief:64 | `test_r2_e2e_check.py::test_markers_check`；人工 t7 |

### 4.20 menu bar：紅點＋計時、收音指示、選單、快捷鍵（F5、F9；R2-Q7、R2-Q12；取代 §4.11.5 的「只放圖示」與 §4.11.6 的選單結構）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.20.1 | `clockText` 應：0 → "00:00"；59 → "00:59"；3599 → "59:59"；3600 → "1:00:00"；3665 → "1:01:05"；-5 → "00:00"。`recordedSeconds` 應：(now − 125 s, 5, nil) → 120；(now − 100 s, 20, now − 10 s) → 70；(now + 5 s, 0, nil) → 0；`recordingStartedAt` 為 "x" → nil。 | R2-Q12；brief:26 | `swift:ControlTests.swift::testRecordedSecondsAndClockText` |
| 4.20.2 | `menuBarModel` 應符合 §3.14.1：(a) M6b（recording、pid 活著、`paused` true、`recordingStartedAt` now − 100 s、`pausedSeconds` 20、`pausedAt` now − 10 s、`controlVersion` 1）→ state paused、`symbolName` "pause.circle.fill"、statusLine 含「已暫停」「01:10」與場次名、`timerText` "01:10"、`canStop` true、`canStart` false、`canControl` true、`paused` true、`levelLine` "收音：暫停中"；(b) 同 (a) 再加 2 則告警類 warning → 仍為 paused、statusLine 含「（告警 2 則）」；(c) M9（`recordingStartedAt` now − 125 s、`pausedSeconds` 5）→ statusLine 含「錄製中 02:00」、`timerText` "02:00"；(d) M9 且 `micMuted` true → statusLine 含「麥克風靜音中」、`micMuted` true、`levelLine` 含「⊘ 已靜音」；(e) M7（recording、有告警）→ `timerText` 非空、`canControl` 依 `controlVersion`；(f) 第一輪格式的狀態（沒有 R2 鍵）→ `canControl` false、`timerText` 等於 statusLine 中的經過時間；(g) M1–M6、M6a、M8、M10 → R2 五個欄位皆為預設值；(h) 全表 statusLine 不含 raw value（§3.14.1）；paused 態 `accessibilityText` 以「MeetingRecorder：」開頭。第一輪 `TriggerTests.swift` 既有測試不改且全綠。 | §3.14.1；brief:26 | `swift:MenuBarR2Tests.swift::testMenuBarR2Rows`；`swift:TriggerTests.swift`（全部，不改） |
| 4.20.3 | `recentPeak` 應：([-70, nil, -50.5], 6) → -50.5；([nil, nil], 6) → nil；([], 6) → nil；([-10, -80, -80, -80, -80, -80, -80], 6) → -80。`levelIndicatorLine(thresholdDBFS: -60)` 應：paused → "收音：暫停中"；recent nil → "收音：讀取中…"；(system -30, mic -70) → "收音：系統聲音 ● 有聲　麥克風 ○ 無聲"；system -60.0 → 系統聲音「○ 無聲」（嚴格大於）；mic nil → 「○ 無聲」；micMuted → 麥克風「⊘ 已靜音」。 | brief:30；design R2-D6 | `swift:MenuBarR2Tests.swift::testLevelIndicator` |
| 4.20.4 | **status item**：應以 `NSStatusItem.variableLength` 建立（不得再用 `squareLength`）；圖示由 `MenuBarModel.symbolName` 決定、一律 template image；錄製中與告警態的 `contentTintColor` 為 `.systemRed`、待機與暫停中為 nil；`timerText` 非空時以 `NSFont.monospacedDigitSystemFont` 顯示在圖示右側，空字串時只有圖示；`micMuted` 時計時前另顯示 SF Symbol `mic.slash`（template）；toolTip 與 accessibilityLabel 規則同 §4.11.8。設計審查：淺色與深色 menu bar 下，錄製中（紅點＋計時）、暫停中、麥克風靜音中、告警四態都看得清楚，計時每秒更新時寬度不抖動。 | brief:26；HIG menu bar extra；取代 §4.11.5「menu bar 上只放圖示、不放文字」（§6 第 80 條） | `test_r2_static.py::test_trigger_status_item_variable_length`；`test_static_rules.py::test_menubar_uses_template_image`（不改）；設計審查（t7 截圖） |
| 4.20.5 | **快捷鍵**：`r2HotKeys` 應恰為 4 筆、id 為 1–4 且不重複、`display` 依序 "⌃⌥⌘R"、"⌃⌥⌘M"、"⌃⌥⌘P"、"⌃⌥⌘B"。`HotKey` 應以呼叫端給的 id 註冊（`HotKey.swift` 不得出現寫死的 `id: 1)`），handler 以 `GetEventParameter`（`kEventParamDirectObject`、`typeEventHotKeyID`）取得事件的 id，不是自己的回 `eventNotHandledErr`；menu bar 應依 `r2HotKeys` 註冊四組；任一組註冊失敗時，`record.log` 寫一行含該組 `display` 與「註冊失敗」、清掉對應選單項的 `keyEquivalent`，其他組與選單照常。 | brief:22-27；R2-Q7；§4.11.3 的延伸 | `swift:MenuBarR2Tests.swift::testHotKeySpecs`；`test_r2_static.py::test_trigger_hotkeys_distinct_ids`；`test_static_rules.py::test_hotkey_uses_carbon`、`::test_hotkey_failure_logged`（不改）；人工 t7（四組各按一次只觸發自己的動作） |
| 4.20.6 | **選單項**（取代 §4.11.6 的順序）：應依序為：不可點的狀態列、收音指示列（不可點；只在 `levelLine` 非空時顯示）、「複製完整訊息與補救指令」（條件同 §6 第 73 條）、分隔線、「開始錄製（用上次的設定）」⌃⌥⌘R、「錄這個視窗」子選單、「存到」子選單（標題含目前位置的最後一段資料夾名）、分隔線、「暫停錄製」⌃⌥⌘P（暫停中標題改「繼續錄製」）、「麥克風靜音」⌃⌥⌘M（靜音中打勾）、「加標記」⌃⌥⌘B、「停止錄製」、分隔線、「打開場次資料夾」、「顯示上一場成品」、分隔線、「偏好設定…」⌘,、「結束 MeetingRecorder 選單」⌘Q。可用性：開始與「錄這個視窗」＝`canStart` 且 `record.defaults.json` 讀得到、有 `harness`；「存到」＝`record.defaults.json` 讀得到、有 `harness`；暫停、麥克風靜音、加標記＝`canControl`；其餘同第一輪。不能用的項目灰掉不隱藏（收音指示列除外）。實作形狀：上列標題字串在 `Trigger/MenuBar.swift` 中第一次出現的位置依序遞增；暫停、靜音、標記三項的 `keyEquivalent` 分別為 "p"、"m"、"b"，`keyEquivalentModifierMask` 為 `[.control, .option, .command]`；偏好設定為 ","、`[.command]`。 | brief:22-28；HIG menu bar extra；§6 第 81 條 | `test_r2_static.py::test_trigger_menu_items_r2`；`test_static_rules.py::test_start_item_shows_hotkey`（不改）；設計審查；人工 t7 |
| 4.20.7 | `TriggerDebouncer(interval: 1.0)` 應：accept("mark", 0) → true；("mark", 0.5) → false；("pause", 0.5) → true；("mark", 1.0) → true；("mark", 1.5) → false（距上次被接受 0.5）。menu bar 的暫停與麥克風靜音應寫「目標狀態」（由目前 `MenuBarModel.paused`／`micMuted` 算出，不讀控制檔來切換），並與加標記一樣經 `TriggerDebouncer` 去抖。 | design R2-D7 | `swift:MenuBarR2Tests.swift::testTriggerDebouncer`；人工 t7（選單展開時按一次 ⌃⌥⌘B 只加一個標記） |
| 4.20.8 | menu bar 送控制時應先 `controlAvailability(status:recordPid:pidAlive:)`，只有 `.ready(pid:runId:)` 才 `requestControl` 並對該 pid 送 SIGUSR1；`unavailable` 時不送、以通知顯示訊息。實作形狀：`Trigger/MenuBar.swift` 含 `controlAvailability(`、`requestControl(`、`SIGUSR1`，且含 `SIGUSR1` 的每一行都不含 `st.pid`、`status.pid`、`.pid ??`。 | R2-Q4 | `test_r2_static.py::test_trigger_control_uses_availability` |

### 4.21 選單選視窗與存檔位置、quick-start（F3、F4；R2-Q3、R2-Q15；§4.11.1 的補充）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.21.1 | `quickStartRoot` 應：("/a", "/b", "/c") → use("/a")；(nil, "/b", "/c") → use("/b")；("", nil, "/c") → use("/c")；(nil, nil, nil) → fail(2, 含「先在終端機跑一次 meeting record」)；isDirectory 對取到的路徑回 false → fail(2, 含「存檔位置不存在」與該路徑)。`explicitWindowDecision` 應：hasDefaults false → fail(2)；.exact(7) → start(7)；.reidentified(9) → start(9)；.notFound → fail(3, 含「選的視窗已經不在了」)；.ambiguous → fail(3, 含「同名」)。`updatedRecentRoots(limit: 5)` 應：(["/a","/b"], "/c") → ["/c","/a","/b"]；(["/a","/b","/c"], "/b/") → ["/b","/a","/c"]；6 項加入新項 → 恰 5 項且新項在最前；("/" 加入) → 第一項 "/"；("" 加入) → 原樣。 | brief:24-25；design R2-D8 | `swift:MenuBarR2Tests.swift::testQuickStartRootAndExplicitWindow`、`::testUpdatedRecentRoots` |
| 4.21.2 | `loadMenuBarPrefs` 對不存在的檔與內容為 `{` 的檔回預設值 (1, nil, [], false, nil, nil)；`saveMenuBarPrefs` 寫出的 JSON 鍵恰為 6 個、nil 寫 null、往返相等、目錄不留 tmp 檔。 | §3.13 | `swift:MenuBarR2Tests.swift::testMenuBarPrefsFile` |
| 4.21.3 | 當以 `quick-start --home <h> --window <id> --window-bundle <b> --window-title <t> [--root <r>]` 啟動時，錄製器應以 `resolveWindow`（§3.8.8）在通過篩選的視窗中認回該視窗，交給 `explicitWindowDecision`，**不經** ★ 恰好一個的判斷；存檔位置依 `quickStartRoot(argRoot: --root, prefsRoot: menubar.prefs.json 的 root, defaultsRoot: record.defaults.json 的 root, …)`；失敗時以通知說明並以 code 結束（同 §4.11.1）；不得跳 Apple Events 授權框。沒帶 `--window` 時的行為與 §4.11.1 完全相同（存檔位置同樣依 `quickStartRoot`）。實作形狀：`Trigger/QuickStart.swift` 含 `explicitWindowDecision(`、`quickStartRoot(`、`resolveWindow(`、`quickStartDecision(`，不含 `askAutomation: true`。 | brief:24；§6 第 83 條 | `test_r2_static.py::test_trigger_quick_start_explicit_window`；`swift:TriggerTests.swift::testQuickStartDecision`（不改）；人工 t7 |
| 4.21.4 | 「錄這個視窗」子選單應以 `open -n -a <自己> --args windows --json --log <暫存檔>` 取得清單（不帶 `--ask-automation`），讀取期間顯示不可點的「讀取視窗清單中…」，10 秒內取不到顯示「取不到視窗清單」；每列標題為 `truncatedStatusTitle(label, limit: 60)`、toolTip 為完整 label，順序照 app 輸出（★ 在前）；點選後以 `open -n -a <自己> --args quick-start --home <home> --window … --window-bundle … --window-title …`（`menubar.prefs.json` 有 `root` 時再加 `--root`）開錄。menu bar 程序本身不得呼叫 SCK：`Trigger/MenuBar.swift` 與 `Trigger/Preferences.swift` 不得出現 `SCShareableContent`、`WindowListing.load(`；`MenuBar.swift` 含 `"windows"`、`"--json"`、`"--log"`。 | brief:24；R2-Q15 | `test_r2_static.py::test_trigger_window_list_via_open`；人工 t7 |
| 4.21.5 | 「存到」子選單應列出 `root`（打勾）與 `recentRoots`（目錄不存在的灰掉並標「（找不到）」）、分隔線、「選擇資料夾…」（`NSOpenPanel`：`canChooseDirectories = true`、`canChooseFiles = false`、`canCreateDirectories = true`）；選定後寫 `menubar.prefs.json` 的 `root` 與 `updatedRecentRoots(…, limit: 5)`。`tools/MeetingRecorder/Sources/` 不得寫 `record.defaults.json`：凡含 `writeJSONAtomically(` 或 `.write(to:` 的行都不得含 `defaults`（不分大小寫）。 | brief:25；R2-Q3 使用者決定 | `test_r2_static.py::test_trigger_prefs_and_open_panel`、`::test_defaults_single_writer`；人工 t7（換位置開錄一次，下次沿用） |

### 4.22 偏好設定、登入時自動開啟、無參數啟動（F7；R2-Q6）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.22.1 | `launchMode` 應：[] → "menubar"；["-psn_0_12345"] → "menubar"；["help"] → "help"；["--help"] → "--help"；["quick-start", "--home", "/x"] → "quick-start"；["-psn_0_1", "windows"] → "windows"。 | ADR `adr-r2-login-item.md` | `swift:MenuBarR2Tests.swift::testLaunchMode` |
| 4.22.2 | `main.swift` 應以 `launchMode(arguments:` 決定子指令；無參數啟動應進 menubar 模式（照 §4.11.10 單一實例）；`help`、`-h`、`--help` 仍印說明後結束碼 0。 | R2-Q6；§4.12.9 的補充（§6 第 86 條） | `test_r2_static.py::test_main_launch_mode_dispatch`；`test_docs.py::test_docs_app_args_exist_in_sources`（不改） |
| 4.22.3 | `loginItemDisplay` 應：enabled → (true, "", false)；notRegistered → (false, "", false)；requiresApproval → isOn true、note 含「系統設定」與「登入項目」、showOpenSettings true；notFound → isOn false、note 含「找不到」、showOpenSettings false。`LoginItemState.allCases` 恰為 4 個。 | brief:28 | `swift:MenuBarR2Tests.swift::testLoginItemDisplay` |
| 4.22.4 | 選單「偏好設定…」應打開一個不可縮放、標題「MeetingRecorder 設定」的視窗（已開就帶到前面，不開第二個），依序含：預設存檔位置與「更改…」、四組快捷鍵的唯讀清單（註冊失敗的那組標「註冊失敗」）、「登入時自動開啟」勾選框與 `loginItemDisplay` 的說明（`showOpenSettings` 時多一顆「打開系統設定的登入項目」，呼叫 `SMAppService.openSystemSettingsLoginItems()`）、「停止後自動跑前處理」勾選框（預設不勾）；改動立即寫入、沒有「確定」按鈕。設計審查依 HIG settings window 慣例。 | brief:28；HIG | `test_r2_static.py::test_trigger_preferences_window`（`Trigger/Preferences.swift` 含上列標題字串與 `openSystemSettingsLoginItems`）；設計審查（t7 截圖） |
| 4.22.5 | `SMAppService` 只得出現在 `Trigger/Preferences.swift`；`.register()`／`.unregister()` 只得在勾選框的動作函式（`@objc`）內呼叫；`Trigger/MenuBar.swift` 的 `setup` 與 `runMenuBar` 本體不得含 `register(`。任何自動流程都不得註冊登入項目。 | 派工約束（不改使用者系統設定）；ADR | `test_r2_static.py::test_trigger_login_item_only_in_preferences` |
| 4.22.6 | 開啟「登入時自動開啟」後登出再登入，menu bar 應出現（只有一個圖示）；重建 app 後再登入一次的結果記錄在 t7 結果（不判，§7 疑慮 39）。 | brief:68 | 人工 t7 |

### 4.23 停止後自動前處理、完成通知、顯示上一場成品（F8、F5；R2-Q13、R2-Q14）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.23.1 | `shouldAutoPrep` 應：(true, done／code 0／runId "a"／session "/s", seen ["a"], last nil) → "/s"；autoPrep false → nil；code 5 → nil；phase finalizing → nil；seen 不含 "a" → nil；last "a" → nil；session "" → nil；status nil → nil。`completionNotificationID(runId: "a")` 應為 "mh.complete.a"；`completionCategoryID` 為 "mh.complete"；`revealActionID` 為 "mh.reveal"。 | brief:29；design R2-D10 | `swift:MenuBarR2Tests.swift::testShouldAutoPrep`、`::testNotificationIDs` |
| 4.23.2 | 當 `shouldAutoPrep` 回場次路徑時，menu bar 應以 `/bin/bash <record.defaults.json 的 harness>/bin/meeting.sh prep <場次目錄>` 在背景執行（傳場次目錄、不是根目錄），stdout／stderr append 到 `<home>/autoprep.log`，以 `terminationHandler` 等結束（主執行緒不 `waitUntilExit`）；同時只跑一個、其餘排隊；啟動前把 `lastAutoPrepRunId` 寫進 `menubar.prefs.json`；結束時送通知（成功「前處理完成」＋場次名；失敗含結束碼與「autoprep.log」）。實作形狀：`Trigger/` 含 `"prep"`、`autoprep.log`、`terminationHandler`、`shouldAutoPrep(`；`Trigger/MenuBar.swift` 不含 `waitUntilExit`。 | brief:29；R2-Q13 | `test_r2_static.py::test_trigger_autoprep_session_prep`；人工 t7（`錄音/transcript.raw.md` 產出） |
| 4.23.3 | 錄製實例的完成通知應以 `completionNotificationID(runId:)` 為識別碼送出（其他行為與 §4.11.7 相同）。menu bar 在本次執行期間看過某 `runId` 處於進行中、之後看到它 `phase == done` 時，應以同一識別碼送一則 category 為 `completionCategoryID`、含動作「在 Finder 顯示」（`revealActionID`）的通知，並把該場次寫進 `lastSession`；menu bar 是 `UNUserNotificationCenter` 的 delegate，收到 `revealActionID` 時以 `NSWorkspace.shared.activateFileViewerSelecting` 選取 `影片/` 下最新的 `.mov`（沒有就選場次目錄）。 | brief:26；R2-Q14 | `test_r2_static.py::test_capture_completion_notification_id`、`::test_trigger_completion_notification_category`；人工 t7 |
| 4.23.4 | 「顯示上一場成品」應在 `menubar.prefs.json.lastSession` 非 null、或狀態檔 `phase == done` 且 `session` 非空時可用，動作同 4.23.3 的選取規則；兩者都沒有時灰掉。 | brief:26 | `test_r2_static.py::test_trigger_completion_notification_category`（含 `"顯示上一場成品"`）；人工 t7 |

### 4.24 文件與 CLI 表面（R2-Q5 使用者決定「全面更新子指令」）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.24.1 | `tests/record/surface.py` 的 `SURFACE` 應逐字等於更新後的 §2.4.2：`forms` 12 個（依表順序）、`form_flags` 3 組（不變）、`form_codes` 32 組、`layer_flags`、`codes` 不變；`parse_help` 對更新後的 §2.4.3 範例應得到等於 `SURFACE` 的五個成分。 | §2.4；§6 第 77 條 | `test_surface_parsers.py`（數字依 §6 第 77 條修改） |
| 4.24.2 | `meeting.sh record help`、`meeting.sh help` 的 record 段、SKILL.md 與 README.md 的 `record-cli` 區塊應列出 12 個寫法，並通過第一輪 §4.1.2、§4.1.11、§4.12.6–§4.12.8 的一致性檢查（字面的「7 行」「17 次」「6 個字」依 §6 第 93 條改為 12 行、27 次、11 個字）。`usage_help` 的說明段應提到五個新保留字的 `./` 寫法。 | §2.4；§6 第 93 條 | `test_cli_dispatch.py::test_help_lists_record_forms`、`::test_record_help_prints_surface`；`test_docs.py::test_docs_cli_block_matches_spec`、`::test_docs_cli_block_matches_help`、`::test_docs_flags_match_behavior`、`::test_docs_exit_codes_match_behavior` |
| 4.24.3 | `.claude/skills/meeting-record/SKILL.md` 應說明 R2 功能，至少含：「⌃⌥⌘R」「⌃⌥⌘M」「⌃⌥⌘P」「⌃⌥⌘B」；「麥克風靜音」與「系統聲音照錄」；「暫停」與「剪掉」與「pauseEvents」；「標記」與「markers.json」；「錄這個視窗」「存到」「偏好設定」「登入時自動開啟」「停止後自動跑前處理」「預設關」「顯示上一場成品」「在 Finder 顯示」；「舊版」（舊版錄製器開的錄製不能暫停／靜音／標記）；「./pause」（保留字）。README.md 的錄製段應含「⌃⌥⌘P」「麥克風靜音」「markers.json」，並有一行指向 SKILL.md。兩份文件不得寫 spec 沒有的子指令或旗標（第一輪 §4.12.6 (d) 的逐行檢查照跑）。 | brief:45；D13（文件先寫） | `tests/record/test_r2_docs.py::test_r2_controls_documented`、`::test_r2_menubar_documented`、`::test_r2_readme_mentions` |
| 4.24.4 | R2 新增與修改的 `specs/`、`tests/`、`tools/MeetingRecorder/Tests/` 檔應通過第一輪 §4.14.3 的客戶名稱檢查（帶 `MH_CLIENT_NAMES_FILE`、不得 `skipped`）；範例一律「[Stand-up] 範例專案」。 | §4.14.3 | `test_static_rules.py::test_no_client_names_in_repo_text`（不改） |
| 4.24.5 | `bin/` 不新增檔：`bash bin/_lint.sh` 檔數維持 26（§4.13.1 不變）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。 | design R2-D11；`rules.md` verify | `test_regression.py::test_lint_passes_26_files`（不改）；verify |

### 4.25 實機 t7（使用者在場；brief:59-70，含第一輪未完成的 §4.9.1 重錄、§4.3.5、§4.2.3、§4.11.1）

agent 不得啟動 `~/Applications/MeetingRecorder.app`、不得觸發 TCC 授權框或改系統設定；以下由使用者操作，主 session 只跑 `e2e_check.py` 與記錄。

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.25.1 | 劇本：錄約 4 分鐘；1:00 按 ⌃⌥⌘M 靜音 30 秒後取消；2:00 按 ⌃⌥⌘P 暫停 30 秒後繼續；之後按 ⌃⌥⌘B 兩次（間隔 > 1 秒）；停止。整段期間會議 app 持續有聲音。`e2e_check.py <場次> --segment-writer --pause-mute --status <該場次的 record.status.json>` 的 `gap`、`segment_cadence`、`stop_tail`、`pause_events`、`pause_cut`、`mic_mute_zero`、`mute_system_kept`、`no_false_silence`、`markers`，以及閘門 2 修正輪新增的 `mute_timing`、`no_false_black`、`event_output_t` 全 PASS；成品長度與「錄製時間（停止點 − `startedAt_1`）− 30 秒」相差 < 1 秒。 | brief:60-66 | 人工；`e2e_check.py` |
| 4.25.2 | 錄製中打開選單：計時每秒走、暫停期間停住、繼續後接續（扣掉暫停）；收音指示列兩路都顯示「● 有聲」、靜音中麥克風顯示「⊘ 已靜音」；status item 錄製中紅點＋計時、暫停中 `pause.circle.fill`、靜音中有 `mic.slash`。截圖（淺色、深色各一組：錄製中、暫停中、靜音中、告警、選單展開、兩個子選單、偏好設定視窗）存 run 目錄，交設計審查。 | brief:66、:70 | 人工；設計審查 |
| 4.25.3 | 從「錄這個視窗 ▸」選一個非 ★ 的視窗開錄一次，錄到的是該視窗；從「存到 ▸ › 選擇資料夾…」選另一個位置開錄一次，場次落在新位置，下一次按 ⌃⌥⌘R 仍落在新位置。 | brief:67 | 人工 |
| 4.25.4 | 偏好設定勾「登入時自動開啟」後登出再登入，menu bar 出現（§4.22.6）；勾「停止後自動跑前處理」後錄一場短的，停止後 `錄音/transcript.raw.md` 產出且收到完成通知；完成通知的「在 Finder 顯示」選到成品。 | brief:68-69 | 人工 |
| 4.25.5 | 第一輪未完成的實機項目：§4.9.1 錄製中切換（重錄）、§4.3.5 系統聲音範圍、§4.2.3 hard fail 不留段落、§4.11.1 quick-start code 2／3／開錄，照第一輪條文驗。 | brief:53 | 人工；`e2e_check.py` |

### R2-§5 影響系統（接續 §5）

| 檔案／系統 | 動作 | 風險與守則 |
|---|---|---|
| `tools/MeetingRecorder/Sources/Core/` | 新增 `Control.swift`；`Records.swift`、`Detectors.swift`、`AudioLevel.swift`、`Trigger.swift`、`Segments.swift`（`SwitchReason` 搬入、`PauseGate` 一組純函式；閘門 2 修正輪）增補（§3.14） | 第一輪 §3.4 名稱與行為不變；新欄位 Optional、nil 省略 |
| `tools/MeetingRecorder/Sources/Capture/` | `RecordingSession.swift`（SIGUSR1、暫停、mic 歸零、標記、事件、狀態欄位、完成通知識別碼；刪掉 private `SwitchReason` 改用 Core 的）、`PreflightRunner.swift`（`RunContext` 加控制檔路徑）、`Notifier.swift`（可指定識別碼） | 分段架構不變（ADR `adr-segment-writer.md`）；SIGTERM 停止路徑不變 |
| `tools/MeetingRecorder/Sources/Trigger/`、`main.swift` | `MenuBar.swift`、`HotKey.swift`、`QuickStart.swift` 改寫；新增 `Preferences.swift`（可另拆 `Trigger/` 內新檔） | menu bar 不呼叫 SCK；只在使用者勾選時註冊登入項目 |
| `tools/MeetingRecorder/build.sh`、`tools/MeetingRecorder/Resources/`（`Info.plist`、entitlements） | 原則上不改（r2f 擁有，`SMAppService`、`NSOpenPanel`、通知在非 sandbox app 不需新 entitlement，`cc:` §3）；實作發現必須改時以 `needs_decision` 回報、經使用者核准後才改並補記本表 | entitlements 恰為兩項（§4.2.8）不變 |
| `bin/record.sh`、`bin/meeting.sh`、`bin/_record_finalize.py` | 五個子指令與 `status`／`stop` 摘要；`usage()`；`gapStats` 扣暫停、`pausedTotal`、複製 `markers.json` | 不新增 `bin/` 檔（lint 26）；`_lint.sh` 的兩個坑照守 |
| `.claude/skills/meeting-record/SKILL.md`、`README.md` | R2 說明、`record-cli` 區塊 12 列 | 改 repo 的 SKILL.md＝改全域（`rules.md:68`）；不得寫真實名稱 |
| `tests/record/`、`tools/MeetingRecorder/Tests/` | **新增**：`test_r2_cli.py`、`test_r2_finalize.py`、`test_r2_e2e_check.py`、`test_r2_static.py`、`test_r2_docs.py`、`Tests/ControlTests.swift`、`Tests/MenuBarR2Tests.swift`。**修改既有的測試工具與替身**（不是測試預期）：`e2e_check.py`（`--pause-mute` 九項判準、既有判準的暫停／靜音排除、`record_to_output`）、`fakes/fake_recorder.sh`（`FAKE_CONTROL`、`FAKE_PHASE`、最終狀態可帶 R2 欄位）、`_media.py`（合成場次：mic 數位 0 段、暫停邊界、事件與 markers）、`_helpers.py`／`_fixtures.py`（只在新情境需要時新增函式或常數，既有函式行為不改）、`Tests/main.swift`（`mrtSuites` 登記兩個新 suite，只加不改）。**修改既有測試預期**：只有 §6 第 77、93 條列的那幾處 | 「一字不改」指的是既有**測試檔的斷言與預期**（`test_*.py`、`*Tests.swift`）——§6 第 77 條列的之外不得改；測試工具與替身的修改必須讓既有測試（含 `test_e2e_check.py`、`test_record_sh.py`）不改且全綠 |
| `~/.meeting-harness/` | 新增 `record.control.json`、`record.control.lock`、`menubar.prefs.json`、`autoprep.log` | repo 外 |
| 場次資料夾 | `錄音/tracks/markers.json`、`錄音/markers.json`；`record.meta.json` 兩個事件陣列；`manifest.json.gapStats.pausedTotal` | 不是音源副檔名，不影響場次判斷 |
| 登入項目（`SMAppService.mainApp`）、通知權限 | 使用者在偏好設定勾選時註冊；`.requiresApproval` 時由使用者在系統設定允許 | agent 不得代做；t7 由使用者驗 |

### R2-§6 整合修訂與例外（續，第 77 條起）

| # | 原文 | 修訂 | 依據 |
|---|---|---|---|
| 77 | §2.4 封閉清單 7 種寫法、`form_codes` 22 組 | 直接更新 §2.4（本 R2 唯一的就地修改）：新增 `pause`、`resume`、`mute`、`unmute`、`mark` 五個寫法（結束碼 `0 3`、沒有寫法旗標），12 種寫法、32 組；`help` 之外再多五個保留字。**使用者核准的既有測試修改**（只改下列與數字或清單直接相關的斷言，其餘一字不改；commit 內文寫明本條）：`tests/record/surface.py` 的 `SURFACE`（新增 5 個寫法常數與 10 組結束碼）、`test_surface_parsers.py:60-63`（7→12、22→32；該檔的 §2.4.3 範例是直接從本檔讀取，不用改文字——本輪 design commit 之後到 r2a 合併之前，`test_parse_help_accepts_spec_example` 會因 `SURFACE` 尚未更新而紅，屬預期）、`test_cli_dispatch.py:63-65`（緊接 7 行→12 行）、`test_docs.py:16`（`SUBCOMMANDS` 加五個字）、`test_docs.py:172`（17→27）；`test_record_sh.py` 的 `EXIT_CODE_CASES` 只新增 10 筆（不改既有筆）、`:24` 註解的「22 組」改「32 組」；build 段補：`test_surface_parsers.py` 的 `VALID_BLOCK`、`VALID_USAGE` 兩個樣本各加五列新寫法（同屬 CLI 表面清單，依使用者 R2-Q5「全面更新子指令」涵蓋，主 session 2026-10-12 判定）；`test_cli_dispatch.py:77-79` 的層旗標、結束碼、空行位置改 `h+13`／`h+14`／`h+15`（同屬 R2-Q5） | R2-Q5 使用者決定「全面更新子指令」（intent〈R2 閘門 1 使用者決定〉）；`rules.md:37` |
| 78 | §2.2 只有七個寫法的語意 | 新寫法的語意見 R2-§2.2；多餘位置參數回 2 比照 `stop` 現行行為、不列入寫法結束碼（§7 疑慮 36） | R2-Q5 |
| 79 | `Core/Records.swift:3-4`「Optional 為 nil 時一律寫 null、不省略鍵」 | R2 新增在 `RecordStatus`（8 個）、`RecordMeta`（2 個）、`GapStats`（1 個）頂層的 Optional，nil 時**省略鍵**；巢狀型別內部（`RecentLevels`、`MenuBarPrefs`、`RecordControl`）仍寫 null。既有 `testStatusJSONKeys`、`testMetaJSONKeys`、`testManifestJSONKeys` 不改 | ADR `adr-r2-status-fields.md`；R2-Q10；閘門 2 使用者決定 3（2026-10-12，接受建議） |
| 80 | D12／`design.md §8.2`「menu bar 上只放圖示，不放文字（不顯示計時）」；§4.11.5 同句；「只有告警態可加系統紅色」；`symbolName` 三態 | 錄製中與暫停中顯示計時（變寬 status item、等寬數字）；錄製中的圓點加系統紅色；新增第四態 `paused`（`pause.circle.fill`）；靜音時加 `mic.slash`（§4.20.4）。§4.11.5 其餘（template image、形狀區分）不變 | 使用者 R2 決定「紅點加計時」（brief:13、:26） |
| 81 | §4.11.6 的選單項順序與 `design.md §8.2`「選單結構」列 | 改為 §4.20.6 的順序；第一輪既有項目的標題、快速鍵、可用性規則不變 | brief:22-28 |
| 82 | §3.4.1 全表 11 列；M9「經過時間＝now − startedAt」 | 新增 M6b（排在 M7 前）；M9 有 `recordingStartedAt` 時用扣暫停的錄製時間（舊狀態檔沿用 `startedAt`）；新增 R2 欄位規則（§3.14.1）。修掉計時比開錄早約 10 秒的既有偏差 | R2-Q12；`cc:` C8 |
| 83 | §4.11.1「quick-start … ★ 恰好一個才開錄，不猜」；存檔位置只取 `record.defaults.json.root`（`design.md §8` 表） | 帶 `--window` 時略過 ★ 判斷、改以 `explicitWindowDecision`（使用者已明確選視窗，不是猜）；存檔位置一律依 `quickStartRoot`（`--root` ＞ `menubar.prefs.json.root` ＞ `record.defaults.json.root`）。沒帶 `--window` 時 ★ 規則不變 | brief:24-25；R2-Q3 |
| 84 | §4.11.3 只有 ⌃⌥⌘R 一組、`HotKey` id 寫死 1 | 四組快捷鍵、每組不同 id、handler 比對 id；註冊失敗規則逐組適用 | brief:22-27；R2-Q7；`cc:` C2 |
| 85 | §3.5「`quick-start`」不帶參數 | quick-start 接受 `--home`、`--window`、`--window-bundle`、`--window-title`、`--root`（app 的 `--args` 層，不是 `meeting record` 的寫法旗標，不進 §2.4）；menu bar 以 `open -n -a … --args windows --json --log` 列視窗 | brief:24；R2-Q15 |
| 86 | §4.12.9、`design.md §9` 的 dispatch：`""` → 印 help 後結束 | 無參數（或只有 `-psn_` 參數）→ `menubar`；`help`／`-h`／`--help` 不變；`main.swift` 在 dispatch 前忽略 SIGUSR1 | ADR `adr-r2-login-item.md`；R2-Q6 |
| 87 | §4.4.3 (a)(c)、§4.4.8 的判準與提前換段的兩種排除 | 依 §3.11 對暫停邊界扣除暫停長度；resume 邊界列為第三種提前換段；`stop_tail` 加 `pausedTotal`、暫停中停止以最後一筆 pause 的 t 代替 `wallClock`；`GapStats` 新增 `pausedTotal`。沒有暫停的場次判準與數字完全不變 | ADR `adr-r2-pause-cut.md`；R2-Q9 |
| 88 | §3.2「`null`＝-∞ 或該時段沒有緩衝」；§6 第 66 條的低音量判準 | 暫停期間兩路、靜音期間 mic 的時段也是 null；讀 `levels` 的判準先排除這些區間（§3.11、§4.18.7） | R2-Q8；`sa:` C6 |
| 89 | §3.2「時間一律是自錄製開始起算的秒數」 | 仍成立於 `tracks/` 的 `manifest.json` 與 `record.meta.json`（新事件另附 `outputT`）；`markers.json` 是例外，`t` 為成品時間、`recordT` 為錄製時鐘（§3.12） | brief:27；R2-Q8 |
| 90 | `design.md §3.1` 的 `~/.meeting-harness/` 檔案表 | 新增 `record.control.json`、`record.control.lock`、`menubar.prefs.json`、`autoprep.log`；`record.defaults.json` 仍只有 `record.sh` 寫 | R2-Q3 使用者決定 |
| 91 | §4.11.7「完成後應送一則含場次路徑的通知」（只有錄製實例送） | 錄製實例以固定識別碼送；menu bar 看到同一場完成時以同識別碼送一則可點「在 Finder 顯示」的通知取代之（§4.23.3）；新增選單「顯示上一場成品」 | brief:26；R2-Q14 |
| 92 | `rules.md`「`has_ui` 一律 false」與第一輪 D12 的例外 | R2 的 test 段同樣 `has_ui=true`、派 `dev-design-reviewer`（偏好設定視窗、變寬 status item、新選單），依據 HIG menu bar extra 與 settings window；`has_security` 維持 false | `sa:` K11 |
| 93 | §1、§2.2、§4.1.2、§4.12.6 (d)、§4.12.8 字面的「七種寫法」「全部 7 種寫法」「恰好 7 行」「`windows`、`preflight`、`stop`、`status`、`finish`、`help` 之一」「共 3＋7×2＝17 次」「7 次」 | 依 §2.4 改讀為 12 種寫法、12 行、11 個字（加 `pause`、`resume`、`mute`、`unmute`、`mark`）、3＋12×2＝27 次、12 次；這些節的其餘規則不變（第一輪內容不就地改，以本條為準） | R2-Q5；第 77 條 |
| 94 | `record.sh status` 的「錄製中 mm:ss」＝現在 − `startedAt` | 有 `recordingStartedAt` 時改用扣暫停的錄製時間，並印暫停、靜音、標記數（§4.16.9）；舊狀態檔不變 | R2-Q12 |
| 95 | intent R2-Q8 建議「事件一律用錄製時鐘、另加成品時間欄位」 | `record.meta.json` 的事件照建議；`markers.json` 依 brief:27 原文以成品時間為 `t`（下游 summary 對逐字稿用成品時間），另附 `recordT`。兩者以檔案區分，`outputTime` 是唯一換算 | brief:27；R2-Q8；閘門 2 使用者決定 1（2026-10-12，design 選項 A） |
| 96 | brief:29「`meeting prep <場次>`（轉錄＋講者分離）」 | 由 menu bar 執行、傳場次目錄；說法改為「跑既有前處理」（講者分離依會議型態 `MH_DO_DIARIZE`），驗收看 `錄音/transcript.raw.md`；同時只跑一個；不在下一場開錄時讓路（§7 疑慮 38） | R2-Q13；`bin/meeting.sh:232`；閘門 2 使用者決定 2（2026-10-12，選項 A：先不讓路、t7 觀察） |
| 97 | brief:22-23 的事件形狀 `micMuteEvents [{t, muted}]`、`pauseEvents [{t, wallClock, kind}]` | 兩者都改為 `{t, outputT, wallClock, …}`（加欄位，不改 brief 的欄位名與語意）；控制檔加 `schemaVersion`、`runId`（brief:35 的 `{paused, micMuted, markerSeq}` 之外）；status 比 brief:36 多 `controlVersion`、`recordingStartedAt`、`pausedAt` | R2-Q8、R2-Q11、R2-Q12；ADR |
| 98 | intent R2-3「`SwitchReason` 是 `RecordingSession.swift:28` 的 `private enum`」；design R2-D3 第 3 步「加在 `RecordingSession.swift:28` 的 private enum」 | 搬到 `Core/Segments.swift`（internal）並加 `resume`；暫停／繼續的閘門、換段原因、事件 append、狀態欄位、偵測器餵送一律是 Core 純函式（§3.14），Capture 只呼叫。第一輪四個 case 的語意不變 | 閘門 2 使用者決定 4；intent R2-2〈可以判定的成果〉「Swift Core 單元測試涵蓋 resume 換段」 |
| 99 | intent R2-2 t7 的判準清單（`e2e_check.py --pause-mute` 六項） | 新增 `mute_timing`（§4.17.8）、`no_false_black`（§4.18.11）、`event_output_t`（§4.18.12），`--pause-mute` 共九項；`stop` 摘要多一行（§4.16.11） | 閘門 2 使用者決定 4（skeptic 問題 2、3、6） |
| 100 | §3.11／§4.18.4「gapStats 一律寫 `pausedTotal`」 | 只有 `record.meta.json` 有 `pauseEvents` 鍵的場次（R2 錄製器開錄就寫 `[]`）才寫 `pausedTotal`；第一輪場次維持 4 個鍵，`test_finalize.py` 不改；`test_r2_finalize.py::test_gapstats_no_pause_unchanged` 的場次 meta 補 `pauseEvents: []` | 使用者 2026-10-12 決定「只有新版錄製器的場次才寫」（build 段 r2g 回報兩支測試互斥） |
| 101 | §4.22.4 偏好設定視窗只規定 `.closable`，沒規定鍵盤關閉；標籤「開機：」與勾選框「登入時自動開啟」用詞不一 | 視窗類別 `PreferencesWindow` 接 Esc（`cancelOperation`）與 ⌘W（`performKeyEquivalent`）關閉；標籤改「登入：」 | 設計審查 R2 SF-2 與 Nit；使用者 2026-10-12 指示「快速開發」，主 session 依審查建議修正 |
| 102 | §4.2.1／§4.2.2 第 6 項（麥克風 RMS）hard、結束碼 4；`PreflightTests.swift` 預期 `mic_rms` 的 `warnOnly` 一律存成 false | 第 6 項失敗（3 秒內峰值 ≤ -60 dBFS）改以 `PreflightResult(item: .mic_rms, ok: false, warnOnly: true)` 回報：warn、code 0、照常開錄，訊息含「麥克風目前很安靜」「15 秒」；螢幕錄製權限沒生效、量不到時仍 hard。`warnOnlyItems` = {system_audio_rms, mic_rms}，decode 時兩者帶 "warn" 都還原；`PreflightTests.swift` 的 `mic` 與 `micJSON` 兩段預期改為 warn／0，另加 `micHard`、`diskJSON` 兩段；SKILL.md 第 6 列與 quick-start 通知改寫 | t7 實機：開錄前檢查以第 6 項擋下 4 次（-87.6～-91.0 dBFS），開會時按下開錄的 3 秒內不一定有人說話；使用者 2026-10-12 決定「降為提醒、不擋開錄」（含此處的測試修改） |
| 103 | §4.4（串流中斷 → 結束碼 5） | `SCStreamError.userStopped`（使用者從選單列系統「畫面錄製」指示按停止）視為一般停止：記一行後走 `requestStop()`，不設 `hadError`／`forced`，結束碼 0，照常發完成通知與自動前處理；其他串流錯誤維持結束碼 5 | t7 實機：2254、2339、2344、2348、2355 五場都由系統指示停止，被記為「擷取串流中斷」結束碼 5，完成通知與自動前處理都沒觸發；使用者 2026-10-12 同意「現在直接修」 |
| 104 | §6 第 101 條 ⌘W 以 `charactersIgnoringModifiers == "w"` 判斷 | 改以實體鍵碼 `keyCode == 13`（kVK_ANSI_W）判斷，原字元判斷保留為備援；修飾鍵只看 ⌘⇧⌥⌃ 四個 | t7 實機：使用者回報「⌘W 沒關、Esc 有關」（推測中文輸入法讓字元不是 "w"）；使用者 2026-10-12 同意「現在直接修」 |
| 105 | §4.20.5 快捷鍵只切換狀態、沒有回饋 | 快捷鍵 ⌃⌥⌘M／P／B 送出控制成功後發通知（`controlFeedback`：「麥克風已靜音」「已暫停錄製」「已加標記 N」等）；選單點擊不發 | t7 實機：選單列圖示看不到，使用者連按 ⌃⌥⌘M 9 次（靜音被來回切換）；同時處理設計審查 R2 Nit「加標記沒有回饋」 |
| 106 | §4.20.4 沒有規定圖示被擋住時的處理 | 每場錄製第一次看到 recording 時（1.5 秒後）以 `statusItemObscured` 判斷圖示是否不可見、寬度 0 或壓到瀏海（`auxiliaryTopLeftArea`／`auxiliaryTopRightArea` 之間）；是就發一次通知，說明 ⌘ 拖曳騰空間與快捷鍵，並寫一行 record.log | t7 實機：使用者兩張截圖都沒有 MeetingRecorder 圖示（只有系統的畫面錄製指示）；使用者 2026-10-12 同意「現在直接修」 |
| 107 | §4.20.4 錄製中與告警態以 `contentTintColor = .systemRed` 染紅 template image；`test_r2_static.py::test_trigger_status_item_variable_length` 要求 MenuBar.swift 含 `contentTintColor` | 紅色改用 `NSImage.SymbolConfiguration(paletteColors: [.systemRed])`、`isTemplate = false`；其他狀態維持 template image。該測試改為要求 `paletteColors`、禁止 `contentTintColor` | t7 實機：macOS 26 上 template image＋`contentTintColor` 的選單列圖示畫成透明（點得到、看不到）；最小重現程式 F（paletteColors）看得到、G（contentTintColor）看不到。錄製中與上一場結束碼 5 時圖示都看不到，也是使用者連按快捷鍵、改用系統指示停止的根因。使用者 2026-10-13 核准修改該測試 |
| 108 | §4.23.2 自動前處理以 `/bin/bash meeting.sh prep` 搭固定 PATH 執行 | 改經登入 shell：`/bin/zsh -lc 'exec /bin/bash "$0" "$@"' meeting.sh prep <場次>`，讀 `~/.zprofile` 取得使用者自己裝的工具路徑；固定 PATH 保留為登入 shell 前的底線 | t7 實機：自動前處理有觸發，但轉錄失敗「mlx-whisper 未安裝」（固定 PATH 沒有 mlx_whisper 所在目錄）；同一場以 `env -i … zsh -lc` 重跑 prep 結束碼 0、產出逐字稿與講者分離稿 |
| 109 | §4.10（record.log 由多個程序 append）沒有規定開檔方式 | `Logger(append: true)` 以 `open(O_WRONLY｜O_APPEND)` 開檔，每次寫入接在當下檔尾；不再只在開檔時 `seekToEndOfFile` | t7 實機：menu bar 的快捷鍵回饋紀錄被錄製實例的輸出蓋掉（`通知：MeetingRecorder｜` 後面接上錄製實例的行），原因是各程序停在開檔當下的檔尾覆寫 |
| 110 | `meeting ingest`（`bin/_scaffold.py`）以硬連結／跨磁碟複製把錄影與截圖歸進場次，原檔留在原處 | 改為**移動**：同磁碟 `os.rename`；跨磁碟先複製到暫存名、大小相同才改名並刪原檔；目的地已有同名檔就跳過、原檔不動；`--dry-run` 不動任何檔。README 第 80 行同步改寫；新增 `test_ingest_move.py` | 使用者 2026-10-13：「很多重複的影片……把這個動作變成移動不要變複製」，選「改成移動（建議）」 |
| 111 | §4.6.7 收尾後 `tracks/` 段落一律保留；`test_finalize.py::test_tracks_preserved` 預期段落不得被刪 | 收尾成功（成品長度檢查通過、wav 原子出現）後刪 `tracks/seg-*.mov`，`manifest.json`／`record.meta.json`／`finalize.json` 保留；`MH_KEEP_SEGMENTS=1` 或 `<record home>/keep-segments` 存在時保留。段落已刪的場次再跑 `record finish`：`record.sh` 有 `finalize.json` 時交給 `_record_finalize.py`，成品都在 → 回 0「已完成」。`test_tracks_preserved` 與 `test_tail_pad_no_extra_close_interval` 改帶 `MH_KEEP_SEGMENTS=1`，新增 `test_segments_removed_after_success`；SKILL.md 說明改寫。**之後的實機驗收（e2e_check 需要段落）要先建 keep-segments** | 使用者 2026-10-13 選「收尾成功就刪（建議）」；測試修改為此決定的直接後果，待閘門 3 追認 |
| 112 | `bin/_profile.py` 以 `f'MH_LANG="{…}"'` 印出、`meeting.sh load_profile` 直接 `eval` | 每個值一律 `shlex.quote`；meeting.json 的 `language`／`llm` 含引號或 `$(…)` 也不會執行 | ultrareview（安全）：可編輯的 meeting.json 經 eval 造成指令注入；`test_review_fixes.py::test_profile_eval_no_injection` |
| 113 | §6 第 111 條：清除段落時逐檔刪、失敗只警告 | 段落只刪掉一部分時，下次 `record finish` 若剩下的段落是 finalize.json 輸入的真子集且成品都在 → 回 0「已完成」並重試清除，不得拿殘缺段落重做、覆蓋成品；模組說明改寫 | ultrareview：部分刪除後重跑會以殘缺段落覆蓋好的成品；`test_partial_cleanup_does_not_refinalize` |
| 114 | `_voiceprint.py match` 依 embeddings.json 順序逐一取最佳名字，名字被用過就整個略過 | 所有（SPEAKER, 名字）配對依 cos 由高到低全域指派：同一名字給信心最高者，被搶的 SPEAKER 可拿次佳名字 | ultrareview：信心較低者先搶到名字並被自動改名；`test_voiceprint_match_assigns_by_confidence` |
| 115 | `_voiceprint.py add` 以 `zip` 平均新舊向量 | 維度不同回 2 並提示先 remove 再重建，不寫檔 | ultrareview：換分離模型時聲紋被靜默截斷；`test_voiceprint_add_rejects_dim_mismatch` |
| 116 | config.json 的 `diarize.enabled／device／minOverlapRatio`、`voiceprint.enabled／renameThreshold／hintThreshold` 沒有任何程式讀 | `_profile.py`（diarize.enabled=false → 不分離，`MH_DIARIZE=1` 仍可強制）、`_voiceprint.py`（enabled、兩個門檻）、`_diarize_pyannote.py`（device）讀 repo 根的 config.json；環境變數仍優先；`meeting.sh` 開頭「預設關閉」的說明改寫。`minOverlapRatio` **不接**：§4.12.4 規定本 epic 不得改 `bin/_merge_speakers.py`（仍只認 `MH_MIN_OVERLAP_RATIO`），列衍生工作（不編號） | ultrareview（含 nit 兩則）；`test_config_diarize_enabled_false`、`test_config_voiceprint_enabled_false_and_thresholds`、`test_stale_comments_fixed` |

### R2-§7 疑慮（續，第 35 條起）

35. **暫停期間 SCK 的行為沒有本機數據**：設計假設 stream 不停、sample 照常送達（被丟棄）。暫停很久時 SCK 是否會因為沒有消費而有其他行為、繼續時第一個 sample 的延遲多大，未能確認；t7 記錄 `record.log` 的丟幀摘要與繼續後新段的 `requestedAt − startedAt`。
36. **`stop` 與五個新寫法的「多餘參數回 2」不在寫法結束碼內**：第一輪 `stop` 已是如此（`bin/record.sh:509` 回 2，§2.4.2 只列 `0 3 5`），R2 比照以免同類寫法兩套規則；若要把 2 列入，要同時改 `stop` 與 `EXIT_CODE_CASES` 的結構（`extra_args` 目前只能放旗標），屬下一輪的決定。
37. **快捷鍵組合是否被系統或常見 app 佔用未查證**：⌃⌥⌘M／P／B 是 brief 指定；佔用時照 §4.20.5 只記 log、選單照常。t7 記錄四組的註冊結果。
38. **自動前處理與下一場錄製同時跑**：轉錄（MPS）與錄製（SCK、硬體編碼）同時進行時是否造成丟幀，沒有本機數據；本輪不讓路。t7 若在前處理期間開錄，記下 `record.log` 丟幀摘要；有問題再提選項（例：開錄時暫停前處理、或錄製中延後前處理）。**閘門 2 使用者決定 2（2026-10-12）**：選項 A——先不讓路、t7 實機觀察，本條保留。
39. **登入項目的前提**：`SMAppService.mainApp` 對 app 位置（`~/Applications`）、簽章身分改變（每次 `build.sh` 重建）後是否仍有效、以及能否帶參數，都是依 API 形狀推論、未實測（ADR `adr-r2-login-item.md`）；只能由使用者在 t7 驗。若重建後失效，選項：每次重建後在偏好設定重勾一次（文件說明）、或改 `SMAppService.agent`。
40. **完成通知被取代時可能閃兩次**：同識別碼的通知會取代前一則，但系統可能各顯示一次橫幅；屬視覺小問題，t7 觀察。menu bar 沒開時只有錄製實例那則（不能點「在 Finder 顯示」）。
41. **`outputT` 與成品實際位置的誤差**：換算不計段落邊界的微小空隙（§4.4.3 門檻 0.5 秒、實測 max |g| 0.117 秒），長會議多個邊界時誤差會累積（仍遠小於 1 秒的情形下 t7 才判 PASS）；summary 端對逐字稿時要知道這個上限。
42. **收音指示的延遲**：`recentLevels` 每秒最多寫一次、menu bar 每秒讀一次，加上 3 秒窗，畫面反映有約 1–4 秒延遲；它是「有沒有錄到」的粗指示，不是即時電平表。

## R3 第三輪（2026-10-13）：錄製穩定、逐字稿源頭、狀態可見、UI 重設計、會前會後、影音一致

- 上游：`intent.md`〈R3 第三輪〉（閘門 1 已核准：R3-Q1＝A、R3-Q8＝B，D3／D4／D7／D9／D11／D12／D13／D14a／D14b 照預設）；設計：`design.md`〈R3 第三輪設計〉R3-D1–R3-D20；ADR：`adr/adr-r3-sync-compensation.md`、`adr/adr-r3-concat-then-mix.md`、`adr/adr-r3-defaults-writers.md`、`adr/adr-r3-menu-stages.md`。
- 本節以上的第一輪與 R2 條文**一字不改**（修正輪起沒有就地修改：原 §6 第 117 條撤回，`sync` 改為 `meeting` 頂層子指令 `meeting sync`，不進 §2.4 的 `record` 封閉清單）；R3 取代既有條文的地方逐條列在 R3-§6。
- 編號接續：資料契約 §3.15–§3.20、驗收 §4.26–§4.47、整合修訂第 117 條起、疑慮第 43 條起。修正輪（skeptic 意見，2026-10-13）新增的整合修訂從第 136 條起、疑慮從第 57 條起（第 134、135 條與疑慮 52–56 屬 UI 設計稿條文）；撤回的條號標「撤回」、不重用。
- **UI 外觀（2026-10-13 定案）**：使用者選定的設計稿與設計語言「暗房」存在 `specs/meeting-record/design-r3/`（`README.md`＋原始稿 `*.dc.html`；`design.md` R3-D21、R3-D22）。U1＝C、U2＝C、U4＝A、U5＝A、U6＝A、U7＝A、F2＝A、F3＝A。本節的外觀條文（§4.38.3、§4.38.5–§4.38.7、§4.40.4、§4.40.7–§4.40.8、§4.41.2–§4.41.5、§4.41.7、§4.42.2、§4.43.5–§4.43.7、§4.43.9、§4.44.3）照該稿寫成可測的字面；稿與本 spec 不一致時以本 spec 為準。build 不得自行決定本節沒寫的色值、字級、尺寸與字面；要改就回報。
- **設計 token 是 Core 常數**：色值、字級、間距一律來自 `Core/DesignTokens.swift`（§3.20），AppKit 端不得自己寫色值或用 `systemRed` 等系統色取代。標「自訂」的是自訂 `NSView`／自繪圖，其餘用標準 AppKit 控制項。
- **R3 新增的 Python 檔一律放 `bin/lib/`**（`_record_lib.py`、`_search.py`、`_reminders.py`）：`bin/` 頂層不新增檔，所以 `_lint.sh` 檔數維持 26、§4.13.1 與 §4.24.5 照舊成立、`test_regression.py::test_lint_passes_26_files` 不改（原 §6 第 125 條撤回）。`_lint.sh` 不掃子目錄，`req:280`「新增的 `bin/*.py` 必須過檢查」改由 §4.32.5 的語法測試涵蓋。呼叫端以 `python3 "$BIN/lib/<檔>"` 執行、Python 端以 `sys.path.insert(0, <bin>/lib)` 匯入（沿用 `bin/_record_prompt.py:20` 的寫法）。
- **`bin/_merge_speakers.py` 不改**（原 §6 第 122 條撤回）：`_render.py` 以 `importlib` 匯入它既有的 `assign_speaker`、`load_speaker_segments`、`UNKNOWN`，`main()` 內的套名判準照抄並以一致性測試保證相同（§4.29.5）；`transcript.speakers.md` 的註記與「（聽不清）」改由 `_render.py --annotate-speakers` 後處理（§4.31.10）。
- 範例名稱一律用「[Stand-up] 範例專案」；測試、fixture、log 範例不得含真實名稱（§4.14 照舊適用）。
- 測試欄的寫法：`test_r3_<slug>.py::<函式>` 在 `tests/record/`；`swift:<檔>::<函式>` 在 `tools/MeetingRecorder/Tests/`；`test_r3_app_static.py::<類別>.<函式>` 是只能靜態檢查的 app 端（類別名對應子任務）；「實機」＝R3 實機驗收場（§4.47，使用者在場）。
- **Red 層補字面（2026-10-13）**：Red 層兩個測試子任務回報 spec 沒定字面、或字面與現行程式不同之處，依主 session 的決定補齊；都是補漏與對齊，不改閘門 2 核准過的行為，每處都落在既有紅燈測試的接受範圍內。逐條：
  - Red 層補字面（2026-10-13）：§3.17 `finalize.json` 的位置改為 `錄音/tracks/finalize.json`（與現行程式一致）；§4.35.2 同步改寫。
  - Red 層補字面（2026-10-13）：§3.18、§4.29.1、§4.29.3、§4.30.4、R3-§5 的 `segments.json` 一律改為 `transcript.segments.json`（`錄音/` 底下）。
  - Red 層補字面（2026-10-13）：§3.17、§4.28.7 `skipped[]` 改為物件 `{file, movedTo}`；讀取端對舊場次同時接受字串與物件。
  - Red 層補字面（2026-10-13）：§3.18 暫停註記〔暫停 a–b〕：a 是成品時間點，b＝a＋暫停長度，b 不在成品時間軸上。
  - Red 層補字面（2026-10-13）：§4.31.3 標記的「掛下一段」與「獨立成行」註明自動測試只驗順序。
  - Red 層補字面（2026-10-13）：§3.18、§3.19、§4.30.1、§4.30.2 的 `--clip-timestamps` 傳法。
  - Red 層補字面（2026-10-13）：§4.35.2 `--sync-player` 的檢查名 `sync_player`。
  - Red 層補字面（2026-10-13）：§4.35.3 `--sync-acoustic` 的輸入（`錄音/tracks/` 雙音軌段落）與輸出格式。
  - Red 層補字面（2026-10-13）：§3.19、§4.33.1 `meeting search` 的 `<檔名>` 帶 `錄音/`。
  - Red 層補字面（2026-10-13）：§4.28.8 步驟耗時印到 stdout（app 啟動的收尾經現行管道進 `<home>/record.log`）。
  - Red 層補字面（2026-10-13）：§4.32.2 `levels_intervals` 的 `levels` 是一維陣列；Swift 不新增 `levelsIntervals`，Swift 測試只驗向量合乎規則。
  - Red 層補字面（2026-10-13）：§4.36.4 末句、§4.36.5 的「目前段已開但沒有 sample → cancel」註明為防禦性分支，自動測試只驗反面。
  - Red 層補字面（2026-10-13）：§4.36.2 收 prev 的條件改為三路各有 `routeSample != .old` 的 sample（跨邊界也算數）。
  - Red 層補字面（2026-10-13）：§3.16、§3.20 `MenuBarSettings` 不加 `schemaVersion`，存檔時由自訂 encode 補上；`onboardingCompletedAt` 為 nil 時省略鍵，§3.16 範例同步。
  - Red 層補字面（2026-10-13）：§4.45.1 `usage()` 只要求列出 `search` 與 `sync`，`reminders` 不要求。
  - Red 層補字面（2026-10-13）：§4.39.3「通知不得含場次名或視窗標題」改由實機驗收場確認（§4.47.4 同步）。
  - §7 疑慮 45（Info.plist 鍵名）維持原狀，由 `r3-reminders` 開工前查證。
- **第 1 層合併後對齊（2026-10-13）**：只對齊字面，不改行為。逐條：
  - 第 1 層合併後對齊（2026-10-13）：§4.28.8 耗時行的 `<對象>` 對原始段落只寫主檔名，範例改為 `耗時 normalize（seg-0001）：1.2 秒`（既有 `test_finalize.py:330` 規定 stdout 不得出現完整段落檔名，`r3-finalize-guard` 已照此實作）；`.claude/skills/meeting-record/SKILL.md` 的同一範例一起改。
  - 第 1 層合併後對齊（2026-10-13）：`design.md` R3-D8 的 `--sync-player` 對 `syncCompensation` 延遲改為「只列出，不再加減」，與 §4.35.2 一致（收尾時延遲已套用到成品上，再扣一次會重複）。
- **第 3 層合併後（2026-10-13）**：§7 疑慮 45 標為已解決：提醒事項權限鍵依 Apple 官方文件為 `NSRemindersFullAccessUsageDescription`，並保留舊鍵 `NSRemindersUsageDescription`；本機 SDK 標頭沒有這個字串；權限框是否實際出現由 §4.47.5 確認。不改行為。
- **build 收尾補記（2026-10-13）**：第 3–6 層各子任務自行決定、spec 原本沒寫的事項，逐條讀程式確認後補成字面（以 `3478f69` 的程式為準）。除第 141 條（改變 §6 第 73 條的顯示條件，閘門 3 追認）外都是補漏，不改閘門 2 核准過的行為。逐條：
  - build 收尾補記（2026-10-13）：§4.41.4 音量條標籤字色 `labelColor`、左右內距 `spacing[3]`＝16；§4.41.3 標題列失敗空心環線寬 1.5；§4.41.5 錯誤詳情內距 `spacing[4]`＝24、列間距 `spacing[2]`＝12、log 路徑 `caption`＋`secondaryLabelColor`、畫面上場次路徑換成「〈場次資料夾〉」而複製完整原文（`r3-menu-stages`）。
  - build 收尾補記（2026-10-13）：§4.41.3、§4.41.5「複製完整訊息與補救指令」在失敗階段一律顯示，取代 §6 第 73 條的顯示條件；新增 §6 第 141 條。
  - build 收尾補記（2026-10-13）：§4.42.3 捨棄時目前段照常收完（不 `cancelWriting`）再移到垃圾桶；場次根目錄只剩 `meeting.json`（可再加 `.DS_Store`）才一起移（`r3-discard`；`design.md` R3-D13 同步）。
  - build 收尾補記（2026-10-13）：§3.17、§4.37 的 `source` 取值規則、冪等判斷含 mode、補償區間只印 stdout（`r3-sync-compensate`）；新增 §7 疑慮 60（標記與 VAD 換算未加 `L_out`）。
  - build 收尾補記（2026-10-13）：§4.46.2 建置以「子目錄_檔名」symlink 編譯（兩支同名 `MeetingDetect.swift`）；§4.43.6 權限分頁 5 列；§4.43.5 試錄的完成通知事後收回（`r3-onboarding-settings`）；新增 §7 疑慮 61、62 與 §4.47.13 實機觀察項。
  - build 收尾補記（2026-10-13）：§4.28.6 收尾中尚未進入 finalizing 時的停止訊號只記 log、期限以 uptime 計時、中止時結束碼固定 5（`r3-finalize-runner`）。
  - build 收尾補記（2026-10-13）：§4.40.5 快捷鍵回饋走 HUD 時沒有額外提示、`hudMode` 為 `never` 時圖示被擋住的處理；列入 §4.47.12 實機觀察項（`r3-hud`）。
  - build 收尾補記（2026-10-13）：§4.30.2 clip 計算失敗時的 VAD 行與 stderr 警告（`r3-transcript-vad`）；新增 §7 疑慮 63（多音檔串接時 levels 時間軸）。

### R3-§2.2 結束碼語意（接續 §2.2、R2-§2.2）

| 寫法 | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| `record [<根>]`（增補） | 不變 | — | **增**：已有錄製在跑（`record.lock` 被持有；不啟動 app、不碰狀態檔） | 不變 | 不變 | 不變 |
| `record preflight`（增補，D14b） | 不變 | — | **增**：錄製中（`record.lock` 被持有；不跑 13 項、不啟動 app、不碰狀態檔） | 不變 | 不變 | — |
| `record stop`（增補，Q5） | 不變 | — | — | **增**：四項 pid 確認任一不成立（不送訊號） | — | 不變 |
| `record finish <場次>`（增補，Q4、Q3） | 不變 | — | 不變 | 不變 | — | **增**：該場次正在收尾（收尾鎖被持有）；任一步逾時 |
| `meeting sync [off\|reported\|calibrated]`（新，不屬 `record`；修正輪由 `meeting record sync` 改為頂層） | 不帶參數：印目前模式；帶參數：已寫入 | — | 參數不是三個值之一、或多於一個參數；`record.defaults.json` 不是 JSON 物件；取鎖逾時 | — | — | — |
| `meeting search <根> <關鍵字>`（新，不屬 `record`） | 有結果 | 沒有結果 | 缺參數、根目錄不存在 | — | — | — |
| `meeting reminders <場次> --list <名稱> [--dry-run]`（新，不屬 `record`） | 寫入完成（或 `--dry-run` 印完） | — | 缺參數、場次沒有 `meeting.record.json`、app 未建置 | 指定的提醒事項清單不存在 | 提醒事項權限被拒 | 寫入失敗（部分項目可能已寫入，重跑會去重） |

`meeting sync`、`meeting search`、`meeting reminders` 是 `meeting` 頂層的新子指令，不在 §2.4 的 `record` 封閉清單內（§2.4 不改，`test_surface_parsers`、`test_cli_dispatch`、`test_docs`、`test_record_sh` 的既有斷言都不改）；它們讓 `sync`、`search`、`reminders` 成為 `meeting` 頂層保留字（名為 `search` 的根目錄要寫 `meeting ./search`；§7 疑慮 46）。`meeting record sync` 不是寫法：依 R2 規則 `sync` 會被當成根目錄（同 §4.42.6 的 `discard`）。

### R3-§3 資料契約（§3.15–§3.20）

#### 3.15 鎖檔與捨棄請求

| 檔 | 誰持有／寫 | 形狀與規則 |
|---|---|---|
| `<home>/record.lock` | 錄製實例（`start`、`quick-start`、`preflight` 三個子指令）以 `flock(LOCK_EX\|LOCK_NB)` 持有到程序結束；`record.sh` 與 menu bar 只**試鎖**（拿到立刻放） | 內容不讀不寫（空檔即可）；`open` 帶 `O_CREAT\|O_RDWR\|O_CLOEXEC`、權限 0600。`<home>`＝`MH_RECORD_HOME`，預設 `~/.meeting-harness`。**試鎖會短暫持有鎖**，為了不讓錄製實例或另一個試鎖者因此誤判，所有取鎖與試鎖一律在 1 秒內每 100 ms 重試，1 秒內都拿不到才判定「被持有」；menu bar 不得在主執行緒上試鎖 |
| `<home>/record.defaults.lock` | `record.sh` 的 `write_defaults` 與 `meeting sync`（兩者都經 `bin/lib/_record_lib.py` 的 `merge_defaults`），app 的 `writeOnboardingDefaults` | 寫 `record.defaults.json` 前取 `flock(LOCK_EX)`（阻塞，最多等 5 秒，逾時放棄寫入並報錯）；持有期間「讀 → 合併 → 同目錄 `mkstemp` → `rename`」 |
| `錄音/tracks/.finalize.lock` | `_record_finalize.py` | `flock(LOCK_EX\|LOCK_NB)` 持有到程序結束；拿不到 → 結束碼 5 |
| `<home>/record.discard.json` | menu bar 寫（tmp＋rename）；錄製實例讀後刪 | `{"schemaVersion": 1, "runId": "<runId>", "requestedAt": "<ISO 8601 含時區>"}`；有效＝`runId` 等於目前實例且 `0 ≤ now − requestedAt ≤ 30` 秒 |

#### 3.16 設定檔

- `<home>/record.defaults.json`（R2 起 `record.sh` 寫 7 鍵：`root`、`type`、`attendees`、`harness`、`python3`、`ffmpeg`、`minFreeBytes`）：**R3 起有兩個寫者、一律合併寫入**（ADR `adr-r3-defaults-writers.md`）。新增鍵 `syncCompensation`（字串，`off`｜`reported`｜`calibrated`；缺鍵＝`off`），只由 `meeting sync` 寫。app 只在首次引導寫 `harness` 與 `root`。任何寫者都不得刪掉自己不認得的鍵。檔案不是 JSON 物件時，寫者一律不寫、報錯（不覆寫壞檔）。
- `<home>/menubar.settings.json`（新，app 唯一寫者；R2 的 `menubar.prefs.json` 6 鍵不動）：

  ```json
  { "schemaVersion": 1, "showTimer": true, "hudMode": "auto", "hudPosition": "right",
    "timeSensitiveAlerts": true, "lastSettingsTab": "general", "meetingDetect": true }
  ```
  上例是全部預設值時存檔的內容。`onboardingCompletedAt`（ISO 8601 含時區的字串，例 `"2026-10-13T10:00:00+08:00"`）在 nil 時**省略鍵**（與 §3.20 增補的 Optional 同慣例；`encodeIfPresent`）；讀取時缺鍵與 `null` 都當 nil。`schemaVersion` 不是 `MenuBarSettings` 的欄位（§3.20）：`saveMenuBarSettings` 以自訂 `encode(to:)` 一律補寫 `"schemaVersion": 1`，`loadMenuBarSettings` 不看它（缺鍵或其他值都照常讀其餘鍵）。（Red 層補字面）
  缺檔、壞檔、缺鍵 → 該鍵用上面的預設值；不認得的值（例 `hudMode: "x"`、`hudPosition: "topRight"`）→ 預設值。`hudPosition` ∈ `right`、`left`（U2＝C：HUD 收在螢幕右緣或左緣）；`lastSettingsTab` ∈ `SettingsTab` 的 7 個 rawValue（§3.20）。
- `<home>/sync-calibration.json`（新，使用者或實機驗收場手寫，不進 repo）：`{"schemaVersion": 1, "devices": {"<輸出裝置 uid>": <秒數>}}`。

#### 3.17 場次檔的新欄位

- `錄音/tracks/record.meta.json` 新增選用 `outputLatencies`（nil 省略鍵；R2-Q10 先例）：

  ```json
  "outputLatencies": [ { "t": 0.0, "uid": "", "transport": "bluetooth", "sampleRate": 48000,
                         "latencyFrames": 0, "safetyOffsetFrames": 0, "streamLatencyFrames": 0, "bufferFrameSize": 512,
                         "reportedSeconds": 0.0 } ]
  ```
  `t` 為錄製時鐘秒數（開錄時一筆 `t=0`，之後每筆輸出裝置 `deviceEvents` 一筆，`t` 相同）；讀不到的數值欄寫 `null`，`reportedSeconds`＝四項幀數和 ÷ `sampleRate`（任一為 null 時 null），小數 4 位。
- `record.status.json` 新增選用 `discarded`（Bool；只在捨棄成功時寫 `true`，其餘省略鍵）。暫停中每 5 秒重寫一次（只更新 `updatedAt`），不加新鍵。
- `錄音/tracks/finalize.json`（位置與現行程式相同，`bin/_record_finalize.py:757`；Red 層補字面）：`skipped[]` 的元素由字串（R2：段落檔名）改成物件 `{"file": "<段落檔名>", "movedTo": "<相對 錄音/ 的路徑>"}`（例 `{"file": "seg-0003.mov", "movedTo": "tracks/unreadable/seg-0003.mov"}`；搬移失敗、段落留在原處時 `movedTo` 為 `null`）。**讀取端**（`_record_finalize.py` 的冪等判斷與之後任何讀 `skipped[]` 的程式）對舊場次要同時接受字串與物件：字串 `"x"` 視同 `{"file": "x", "movedTo": null}`；新增選用 `timedOut: {"step": "normalize|concat|mix|probe", "seconds": <上限>}`；新增選用 `syncCompensation: {"mode": "off|reported|calibrated", "segments": [{"file", "outputUid", "delaySeconds", "source": "reported|calibrated|missing|none", "clamped"}]}`（`mode` 為 `off` 時 `segments` 為 `[]`）。**`source` 的取值**（build 收尾補記，`bin/_record_finalize.py:733-765`）：`reported` 模式下，該段生效的那筆 `outputLatencies`（`t` ≤ 段落起點＋min(0.5, 段長／2) 的最後一筆，`:721-731`）算得出回報值 → `reported`；場次的 `record.meta.json` **完全沒有** `outputLatencies`（缺鍵、不是陣列或沒有任何物件）→ `none`；有 `outputLatencies` 但該段沒有生效的那筆、或那筆的值讀不到（幀數與 `sampleRate` 算不出、`reportedSeconds` 也是 null，`:700-707`）→ `missing`。`calibrated` 模式下，以該筆的 `uid`（沒有就用 `devices.output.uid`）查 `sync-calibration.json`，查得到 → `calibrated`，查不到或沒有 uid → `missing`（`calibrated` 模式不會出現 `none`）。`none`、`missing` 的 `delaySeconds` 一律 0。**冪等判斷含 mode**（`:513-524`）：段落還在時，`finalize.json.syncCompensation.mode` 與本次解析出的 mode 不同（R2 以前的場次沒有這個鍵，視為 `off`）就不算已完成、重做收尾；原始段落已清除的場次不受影響（照舊回「已完成」）。**補償區間不寫進 `finalize.json`**：每個區間只以 `  補償區間：串接後 <s>–<e> 秒，系統聲音延後 <d> 秒` 印到 stdout（`:890`；app 啟動的收尾經現行管道進 `<home>/record.log`，同 §4.28.8）。

#### 3.18 逐字稿衍生檔與 schema

- `錄音/transcript.segments.json`（段落檔；檔名與現行程式相同，`bin/transcribe.sh:120`、`bin/meeting.sh:244`、`bin/_render.py:235`；Red 層補字面）：`transcribe.sh` **一律輸出**（R2 前只在 `MH_EMIT_SEGMENTS=1` 時），格式不變。
- **送 ASR 的 clip**（Red 層補字面）：`mlx_whisper` 以 CLI 參數 `--clip-timestamps <start>,<end>,<start>,<end>,…` 傳入（一個參數值、逗號分隔、不含空白與方括號、成品秒數、小數 3 位，例 `--clip-timestamps 4.250,10.750,24.250,30.750`；值取自 §3.19 `_record_lib.py clip` 的輸出攤平）；`openai-whisper` 退路以同值的 `--clip_timestamps` 傳入。退回整檔時不帶這個參數。
- `transcript.quality.json`（新）：`[{"start": 12.5, "end": 18.0, "reason": "compression_ratio"}]`；`reason` ∈ `compression_ratio`（該段文字 zlib 壓縮比 > 2.4）、`no_speech_loop`（同一句在該段內連續重複 ≥ 3 次）、`repeat_run`（相鄰 ≥ 4 段文字完全相同，每段各一筆）；依 `start` 遞增；沒有就 `[]`。
- `transcript.raw.md` 標頭：`> 來源：… 模型：…` 的下一行是 VAD 行，二選一：`> VAD：clip <N> 段，門檻 <x> dBFS，補 <p> 秒，合併間隔 <g> 秒`，或 `> VAD：未套用（<原因>）`，原因 ∈ `沒有 levels`、`沒有有聲區間`、`MH_VAD=0`。raw 的正文照舊不清洗。
- `schema/meeting-record.v1.json`：頂層加選用 `markers`（陣列；每筆必有 `label`（字串）、`t`（≥ 0 的數字，成品秒數），選用 `speaker`、`note`（字串））；`required` 不變。
- `summary.md`：五個必備段（`一句話：` 與決議、依賴、風險、交辦）之後，有標記才加 `## 標記`（每行 `- <mm:ss> <label>（<speaker>）`，沒有 speaker 不加括號），有暫停／麥克風靜音／輸出裝置切換／長靜音才加 `## 錄製註記`（每行 `- <mm:ss>–<mm:ss> <種類>`，種類 ∈ `暫停（未錄）`、`麥克風靜音`、`長靜音`，裝置切換寫 `- <mm:ss> 輸出裝置切換：<舊 transport> → <新 transport>`）。不寫裝置名稱與 uid。兩段由 `_render.py` 的同一個函式產生；`bin/summarize-local.py`（地端總結）寫出的 `summary.md` 也在模型輸出之後接上這兩段（§4.31.9），雲端與地端的 `summary.md` 段落一致。
- 註記行（`transcript.speakers.md` 與 VTT）：`〔暫停 <mm:ss>–<mm:ss>，這段沒有錄〕`、`〔麥克風靜音 <mm:ss>–<mm:ss>〕`、`〔長靜音 <mm:ss>–<mm:ss>〕`、`〔輸出裝置切換：<舊> → <新>〕`、`〔<label>〕`（標記）。VTT 一律放在 `NOTE` 區塊，不佔 cue。**暫停註記的兩個時間**（Red 層補字面）：`〔暫停 a–b，這段沒有錄〕` 與 summary 的 `- a–b 暫停（未錄）` 中，a＝暫停開始在成品時間軸上的時間點（`outputTime(pause.t)`）；b＝a＋暫停長度（`resume.t − pause.t`，錄製時鐘秒數；沒配對的暫停以錄製結束為 resume）。b **不在成品時間軸上**（成品裡暫停長度為 0，b 之後的成品內容從 a 接續），只用來表示暫停了多久。例：成品 02:00 暫停 90 秒 → `〔暫停 02:00–03:30，這段沒有錄〕`。自動測試只比對 a 與「b 是 `mm:ss`」（`test_r3_annotations.py:34`、`:289`）。長靜音＝兩路 `levels` 都 ≤ -60 dBFS（含 null）連續 ≥ 30 秒，且不在暫停區間內。

#### 3.19 CLI 與程式介面（新）

- `meeting sync [off|reported|calibrated]`（`bin/meeting.sh` 頂層分派到 `python3 "$BIN/lib/_record_lib.py" sync …`）：不帶參數印一行 `syncCompensation=<mode>`；帶參數經 §3.15 的鎖以 `merge_defaults` 合併寫入，印 `syncCompensation=<mode>（下一次收尾起生效）`。
- `bin/lib/_record_lib.py` 的 `merge_defaults(home, updates, timeout=5.0)`：取 `<home>/record.defaults.lock`（阻塞，最多 5 秒）→ 讀 `record.defaults.json`（缺檔＝`{}`）→ 不是 JSON 物件就丟例外、不寫 → 合併 `updates`（不認得的鍵保留）→ 同目錄 `mkstemp`＋`os.replace`。`record.sh` 的 `write_defaults` 與 `meeting sync` 都呼叫它。
- **stop 檢查的測試旁路**（§6 第 136 條）：`record.sh stop` 第 (4) 項比對 `ps -o comm=` 的結尾字串預設是 `MeetingRecorder`；`MH_RECORDER_COMM` 有值**且** `MH_RECORD_OPEN` 也有值（測試環境的既有旁路）時改用 `MH_RECORDER_COMM`，否則一律用 `MeetingRecorder`。
- `meeting search <根> <關鍵字>`：搜 `<根>` 底下各場次的 `summary.md`、`transcript.speakers.md`、`transcript.raw.md`、`meeting.record.json`；大小寫不分、純子字串；每筆一行 `<場次相對 <根> 的路徑>/<檔名>:<行號>: <該行，超過 120 字截斷加「…」>`；`<檔名>` 是相對場次目錄的路徑，**帶 `錄音/`**：`summary.md`、`meeting.record.json`、`錄音/transcript.speakers.md`、`錄音/transcript.raw.md`（Red 層補字面）；場次依資料夾名稱（日期在前）新到舊；同場次依 `<檔名>` 字串（Python 字串比較）、行號遞增。
- `meeting reminders <場次> --list <名稱> [--dry-run]`：`bin/lib/_reminders.py` 讀 `<場次>/meeting.record.json` 的 `actions[]`，組出項目 `{uid, title, notes, due, url}`：`uid`＝`f"{record.get('id', record['title'])}-{aid}@meeting-harness"`（與 `actions.ics` 相同）；`title`＝交辦內容；`notes`＝「負責人：<owner 或（未定）>」＋場次名；`due`＝期限（缺值 `null`，不補猜）；`url`＝`meetingharness://action/<uid>`。`--dry-run` 印 JSON 陣列後回 0、不啟動 app；否則以 `open -W -n -a <app> --args reminders --input <暫存 json> --list <名稱>` 交給 app，並以 app 寫的 `<暫存>.result.json` 的 `code` 為結束碼（沒有結果檔回 5）。
- MeetingRecorder 子指令 `reminders --input <json> --list <名稱>`：`requestFullAccessToRemindersWithCompletion:` → 找名稱完全相同的清單（不代建）→ `fetchRemindersMatchingPredicate:` 讀出現有項目的 `URL` → 相同 URL 更新 `title`、`notes`、`dueDateComponents`，否則新增 → `saveReminder:commit:NO`，最後 `commit`；結果寫 `<input>.result.json` `{"code", "created", "updated", "message"}`，code 0／3／4／5 同 R3-§2.2。
- `python3 bin/lib/_record_lib.py clip <錄音目錄>`：印 `clip_timestamps` 的 JSON（`[[start, end], …]`，成品秒數，小數 3 位；退回整檔時印 `null`），結束碼 0；目錄不存在 2。`transcribe.sh` 依 §3.18 把它攤平成 `--clip-timestamps` 的值。

#### 3.20 Swift `Core/` 對外名稱（R3；test 子任務依此寫紅燈測試，build 段不得改名）

```swift
// Core/Lock.swift
func acquireRecordLock(home: URL, retrySeconds: Double = 1.0) -> MenuBarLockResult  // <home>/record.lock；既有的 .acquired(fd)／.heldByOther／.unavailable(errno)；每 100 ms 重試
enum StopRefusal: String, Equatable { case noLock = "no_lock", noPid = "no_pid", pidDead = "pid_dead",
                                      pidMismatch = "pid_mismatch", notRecorder = "not_recorder" }
enum StopTarget: Equatable { case signal(pid: Int32); case refuse(StopRefusal) }
func stopTargetDecision(lockHeld: Bool, recordPid: Int32?, pidAlive: Bool, statusPid: Int32?, command: String?) -> StopTarget
func finalizeDeadline(recordedSeconds: Double) -> Double            // max(recordedSeconds, 0) × 3 + 600
let pausedHeartbeatSeconds: Double = 5
struct DiscardRequest: Codable, Equatable { var schemaVersion: Int; var runId: String; var requestedAt: String }
func discardRequestValid(_ r: DiscardRequest?, runId: String, now: Date) -> Bool

// Core/Appearance.swift
enum MenuBarAppearance: String, CaseIterable, Equatable { case idle, preparing, recording, recordingMuted, recordingAlert, paused, finalizing, failed }
func spokenDuration(seconds: Int) -> String
enum MenuStage: String, Equatable { case idle, recording, finalizing, failed }
func menuStage(_ m: MenuBarModel) -> MenuStage
enum MenuItemID: String, CaseIterable { case status, levels, alert, copyDiagnostics, failureDetail, start, recordWindow, saveTo,
                                        pauseResume, mute, mark, stop, discard, cancelFinalize, showHUD, openSession, showLast, preferences, quit }
func menuItems(stage: MenuStage) -> [MenuItemID]            // ＝ menuGroups(stage:) 攤平
func menuGroups(stage: MenuStage) -> [[MenuItemID]]         // 組與組之間一條分隔線（§4.41.7）
func levelFraction(dBFS: Double?) -> Double                 // 音量條長度：clamp((dBFS + 60) / 60, 0, 1)；nil → 0
func menuBarAccessibilityLabel(appearance: MenuBarAppearance, alertBadge: Bool, spoken: String,
                               alertText: String?, status: String) -> String   // §4.38.7
let hudAlertExpandSeconds: Double = 8        // 新告警時 HUD 自動展開的秒數（§4.40.7）
let hudCollapseDelaySeconds: Double = 0.6    // 滑鼠離開後收合的延遲
let hudAnimationSeconds: Double = 0.2        // 展開／收合動畫；「減少動態效果」時不做動畫
let levelMeterRefreshSeconds: Double = 0.5
enum HUDMode: String, Codable, CaseIterable { case auto, always, never }
func hudVisible(mode: HUDMode, obscured: Bool, appearance: MenuBarAppearance) -> Bool
enum FeedbackRoute: String, Equatable { case hud, none, notification }
func feedbackRoute(hudVisible: Bool, iconVisible: Bool) -> FeedbackRoute
enum ObscuredAction: Equatable { case none, showHUD, hideHUD }
func obscuredAction(previous: Bool?, current: Bool, mode: HUDMode, recording: Bool) -> ObscuredAction
let obscuredCheckSeconds: Double = 5
enum NotificationKind: String, CaseIterable { case alertWarning, failure, completion, hotkeyFeedback, meetingDetected, onboarding }
enum NotificationLevel: String, Equatable { case passive, active, timeSensitive }
struct NotificationPolicy: Equatable { var level: NotificationLevel; var threadIdentifier: String }
func notificationPolicy(kind: NotificationKind, runId: String?, timeSensitiveAllowed: Bool) -> NotificationPolicy
func newAlertWarnings(previous: [RecordWarning], current: [RecordWarning]) -> [RecordWarning]

// Core/Settings.swift
struct MenuBarSettings: Codable, Equatable { var showTimer = true; var hudMode = HUDMode.auto; var hudPosition = "right"
    var timeSensitiveAlerts = true; var lastSettingsTab = "general"; var onboardingCompletedAt: String? = nil; var meetingDetect = true }
    // 不含 schemaVersion 欄位；自訂 encode(to:) 存檔時補寫 "schemaVersion": 1，onboardingCompletedAt 為 nil 時省略鍵（encodeIfPresent）；
    // loadMenuBarSettings 遇缺鍵、null、不認得的值 → 該鍵用預設值（§3.16）
enum SettingsTab: String, CaseIterable { case general, recording, feedback, hotkeys, afterRecording, permissions, advanced
    var title: String { get }; var symbolName: String { get } }   // 值見 §4.43.6
func settingsTab(_ raw: String) -> SettingsTab                    // 不認得 → .general
func loadMenuBarSettings(home: URL) -> MenuBarSettings
func saveMenuBarSettings(_ s: MenuBarSettings, home: URL) throws
enum DefaultsMergeError: Error, Equatable { case notObject, lockTimeout }
func mergedDefaultsJSON(existing: Data?, harness: String, root: String) throws -> Data
func writeOnboardingDefaults(home: URL, harness: String, root: String) throws

// Core/DesignTokens.swift（設計語言「暗房」；值的出處見 design-r3/README.md §1；色值一律 "#RRGGBB" 大寫字串）
enum DarkroomColor {
    static let ink = "#0F1115", surface = "#171A21", raised = "#1F232C", light = "#F6F5F2", line = "#2A2F3A", lineStrong = "#3A404D"
    static let text = "#ECEEF2", textSecondary = "#C3C9D4", textTertiary = "#9AA3B2", textDisabled = "#5B6372"
    static let recording = "#FF4D4F", attention = "#F5A524", processing = "#8B7CF6", done = "#2DD4BF"
    static let recordingText = "#FF6B6E", attentionText = "#F7C46C", processingText = "#B9AEFF", doneText = "#5EE6D2"
    static let onAttention = "#1A1206", mutedSegment = "#1A0B0C", onSignal = "#FFFFFF", iconStroke = "#2E333E"
    static let menuBarDark = "#1E2129", menuBarLight = "#E9E7E2", textOnLight = "#1A1C21", lineOnLight = "#C9C6BF"
    static let recordingOnLight = "#D92D30", processingOnLight = "#6D5BD0", processingTextOnLight = "#5E4BC4"
    static let failedTextOnLight = "#B42318", attentionTextOnLight = "#8A5A00", doneOnLight = "#0F766E"
    static let recordingHighContrast = "#CC2F32", recordingHighContrastOnLight = "#C42B2E"
    static var all: [String: String] { get } }   // 以上 34 個 token：名稱 → 值
struct TypeToken: Equatable { var size: Double; var weight: String }   // weight ∈ "regular"、"semibold"、"bold"
enum DarkroomType {
    static let capsule = TypeToken(size: 14, weight: "bold"), hudTabTimer = TypeToken(size: 13, weight: "semibold")
    static let hudTimer = TypeToken(size: 18, weight: "semibold"), hudLabel = TypeToken(size: 13, weight: "regular")
    static let hudButton = TypeToken(size: 12, weight: "regular"), hudAlert = TypeToken(size: 12, weight: "bold")
    static let menuMeterLabel = TypeToken(size: 12, weight: "regular"), onboardingTitle = TypeToken(size: 26, weight: "bold")
    static let onboardingBody = TypeToken(size: 15, weight: "regular"), rowTitle = TypeToken(size: 15, weight: "bold")
    static let rowDetail = TypeToken(size: 13, weight: "regular"), button = TypeToken(size: 14, weight: "bold")
    static let stepLabel = TypeToken(size: 12, weight: "regular"), settingsTabLabel = TypeToken(size: 12, weight: "regular")
    static let settingsRowLabel = TypeToken(size: 14, weight: "regular"), caption = TypeToken(size: 12, weight: "regular") }
enum DarkroomMetric {
    static let spacing: [Double] = [4, 8, 12, 16, 24]
    static let capsuleHeight: Double = 20, capsulePaddingH: Double = 10, capsuleGap: Double = 6, capsuleDot: Double = 8, capsuleBorder: Double = 1.5
    static let muteSegmentPaddingLeading: Double = 9, muteSegmentPaddingTrailing: Double = 7, badgeDiameter: Double = 7, badgeStroke: Double = 1.5
    static let hudTabWidth: Double = 34, hudTabHeight: Double = 120, hudTabCornerRadius: Double = 14, hudTabDot: Double = 10, hudTabTopFraction: Double = 0.25
    static let hudPanelWidth: Double = 230, hudPanelPadding: Double = 16, hudPanelCornerRadius: Double = 16
    static let hudButtonHeight: Double = 44, hudButtonCornerRadius: Double = 10, hudButtonGap: Double = 6
    static let meterBarHeight: Double = 5, meterLabelWidth: Double = 40, menuMeterWidth: Double = 240
    static let onboardingWidth: Double = 620, onboardingHeight: Double = 560, onboardingPaddingH: Double = 32, onboardingPaddingV: Double = 28
    static let rowPaddingH: Double = 16, rowPaddingV: Double = 14, rowCornerRadius: Double = 14, rowGap: Double = 10
    static let buttonHeight: Double = 44, buttonCornerRadius: Double = 12, settingsWidth: Double = 600, settingsTabWidth: Double = 76 }
func contrastRatio(_ a: String, _ b: String) -> Double   // WCAG 2.x（design-r3/README.md §1.4）；任一不是 #RRGGBB → 0
enum CapsuleShape: String, Equatable { case templateSymbol, outline, filled, split }
enum CapsuleGlyph: String, Equatable { case none, dot, pause, micSlash }
struct CapsuleStyle: Equatable { var shape: CapsuleShape; var glyph: CapsuleGlyph; var label: String; var showsTimer: Bool
    var fill: String?; var border: String?; var borderWidth: Double; var text: String?; var badge: Bool; var largeText: Bool }
func menuBarCapsuleStyle(_ a: MenuBarAppearance, alertBadge: Bool, dark: Bool, increaseContrast: Bool) -> CapsuleStyle   // §4.38.5

// Core/SegmentScheduler.swift
enum SchedulerTrack: String, CaseIterable, Equatable { case video, system, mic }
enum SchedulerEvent: Equatable {
    case sample(track: SchedulerTrack, start: Double, end: Double, formatChanged: Bool)
    case pause, resume, outputDeviceChange, writerFailed(segment: Int), prevTimeout(segment: Int), stop }
enum SchedulerAction: Equatable {
    case open(segment: Int, reason: SwitchReason, boundary: Double)
    case write(segment: Int, track: SchedulerTrack)
    case drop(track: SchedulerTrack)
    case finish(segment: Int)
    case cancel(segment: Int) }
struct SegmentScheduler { init(segmentSeconds: Double = 60)
    mutating func handle(_ e: SchedulerEvent) -> [SchedulerAction]
    var current: Int? { get }; var prev: Int? { get }; var gate: PauseGate { get } }

// Core/SyncLatency.swift
struct OutputLatency: Codable, Equatable { var t: Double; var uid: String; var transport: String; var sampleRate: Double?
    var latencyFrames: Int?; var safetyOffsetFrames: Int?; var streamLatencyFrames: Int?; var bufferFrameSize: Int?; var reportedSeconds: Double? }
func reportedLatencySeconds(sampleRate: Double?, latency: Int?, safety: Int?, stream: Int?, buffer: Int?) -> Double?
func outputTime(recordT: Double, firstSegmentStart: Double, pauses: [PauseEvent], lOut: Double) -> Double

// Core/MeetingDetect.swift
struct MeetingEpisode: Equatable { var inputRunning = false; var prompted = false; var dismissed = false }
enum MeetingPrompt: Equatable { case none, prompt }
func meetingPromptDecision(_ ep: MeetingEpisode, inputRunning: Bool, frontmostBundleID: String?, recordLockHeld: Bool,
                           enabled: Bool) -> (MeetingEpisode, MeetingPrompt)

// 既有檔的增補
// Core/Records.swift：RecordMeta.outputLatencies: [OutputLatency]?；RecordStatus.discarded: Bool?（皆 nil 省略鍵）
// Core/Segments.swift：SwitchReason 新增 .outputDeviceChange（放在 .resume 之後）
// Core/Trigger.swift：MenuBarModel 新增 appearance: MenuBarAppearance = .idle、alertBadge: Bool = false、spokenDuration: String = ""
```

`MenuBarState`、`symbolName` 與 R2 的 `menuBarModel` 各列其他欄位不變（§6 第 128 條只改外觀的歸屬）。

### R3-§4 驗收

#### 4.26 開錄鎖、preflight 互斥、暫停心跳（Q1、Q2、D14b）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.26.1 | `acquireRecordLock(home:retrySeconds:)` 應：沒人持有 → `.acquired(fd)`；另一個子程序持續持有 `record.lock` → 約 `retrySeconds` 後回 `.heldByOther`（`retrySeconds: 0.3` 時耗時介於 0.25 與 1.0 秒）；另一個子程序持有 0.2 秒後放掉 → `.acquired(fd)`（`retrySeconds: 1.0`）；`home` 不可寫 → `.unavailable(errno)`。fd 應有 `FD_CLOEXEC`。 | R3-D2 | `swift:R3LockTests.swift::testAcquireRecordLock` |
| 4.26.2 | 錄製實例的 `start`、`quick-start`、`preflight` 應在建立 `StatusWriter` 與寫 `record.pid` **之前**呼叫 `acquireRecordLock`；`.heldByOther` 時不寫 `record.status.json`、不寫 `record.pid`、`record.log` 記一行含「已有錄製在跑」，以結束碼 2 結束。實作形狀：`Capture/Commands.swift` 與 `Capture/PreflightRunner.swift` 中 `acquireRecordLock(` 第一次出現的位置早於 `StatusWriter(` 第一次出現的位置。 | Q1、Q2；`Capture/Commands.swift:126` | `test_r3_app_static.py::LockStatic.test_lock_before_status_writer`；實機 |
| 4.26.3 | 當 `record.lock` 被別的程序持有時，`meeting record <根> --window 1` 應回 2、stderr 含「已有錄製在跑」，且替身 app 沒有被呼叫、`record.status.json` 的 mtime 與內容不變。 | Q2；R3-§2.2 | `test_r3_lock.py::test_record_refused_when_locked` |
| 4.26.4 | 當 `record.lock` 被持有時，`meeting record preflight --window 1` 應回 2、stderr 含「錄製中」，替身 app 沒有被呼叫、狀態檔不變（D14b-A）；沒被持有時行為與 R2 完全相同（既有 `test_record_sh.py` 的 preflight 案例不改）。 | D14b；§6 第 119 條 | `test_r3_lock.py::test_preflight_refused_when_recording` |
| 4.26.5 | `record.sh` 試鎖成功後應立刻放掉鎖（試鎖程序結束後，另一個程序能馬上 `LOCK_NB` 拿到）；別的程序只持有 0.2 秒時，`record.sh` 的試鎖應在重試內拿到、照常開錄（§3.15 的 1 秒重試）。 | R3-D2 | `test_r3_lock.py::test_try_lock_releases` |
| 4.26.6 | 暫停中，錄製實例應每 `pausedHeartbeatSeconds`（5 秒）重寫一次 `record.status.json`，只有 `updatedAt` 改變；`RecordStatus` 的鍵集合不變。實作形狀：`RecordingSession.swift` 含 `pausedHeartbeatSeconds`，且暫停分支會呼叫狀態寫入。 | Q1；`RecordingSession.swift:640` | `swift:R3LockTests.swift::testPausedHeartbeatConstant`；`test_r3_app_static.py::LockStatic.test_paused_heartbeat`；實機（暫停 30 秒，`updatedAt` 至少前進 5 次） |
| 4.26.7 | 兩個 `record.sh` 同時開錄（兩個都過了試鎖）時，應只有一個錄製實例寫狀態檔；另一個 `record.sh` 依 §4.1.6 回 4 或依 4.26.3 回 2，不得兩個都回 0。 | R3-D2；§7 疑慮 43 | `test_r3_lock.py::test_concurrent_record_only_one_wins`（替身 app 依 `FAKE_OPEN_LOCK=1` 模擬取鎖；與 `fake_recorder.sh` 的 `FAKE_LOCK` 分開命名，§6 第 136 條） |

#### 4.27 `stop` 只停錄製器（Q5）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.27.1 | `stopTargetDecision` 應依序判斷：`lockHeld` false → `.refuse(.noLock)`；`recordPid` nil → `.refuse(.noPid)`；`pidAlive` false → `.refuse(.pidDead)`；`statusPid != recordPid` → `.refuse(.pidMismatch)`；`command` 為 nil 或不以 `MeetingRecorder` 結尾 → `.refuse(.notRecorder)`；全部成立 → `.signal(pid:)`。例：(true, 123, true, 123, "/Applications/x/MeetingRecorder") → `.signal(pid: 123)`；(true, 123, true, 456, …) → `.refuse(.pidMismatch)`；(true, 123, true, 123, "/bin/sleep") → `.refuse(.notRecorder)`。 | Q5 | `swift:R3LockTests.swift::testStopTargetDecision` |
| 4.27.2 | `meeting record stop` 在下列任一情況應回 3、不送任何訊號：`record.lock` 沒被持有；`record.pid` 的 pid 已死（並刪掉該 `record.pid`）；`record.status.json.pid` 與 `record.pid` 不同；`ps -o comm=` 不以 `MeetingRecorder` 結尾（測試環境依 §3.19 改比 `MH_RECORDER_COMM`；以一個無關的 `sleep` 程序的 pid 寫進 `record.pid`、`record.lock` 由測試持有來驗：該程序在 stop 之後仍活著）。stderr 說明是哪一項。另外：沒有設 `MH_RECORD_OPEN` 時，`MH_RECORDER_COMM` 不得生效（設 `MH_RECORDER_COMM=sleep` 而不設 `MH_RECORD_OPEN`，對 `sleep` 程序仍回 3）。 | Q5；`record.sh:546`；§6 第 136 條 | `test_r3_lock.py::test_stop_refuses_foreign_pid`、`::test_stop_cleans_dead_pid`、`::test_stop_refuses_without_lock`、`::test_comm_override_needs_record_open` |
| 4.27.3 | `phase` 為 `stopping` 或 `finalizing` 時，`meeting record stop` 不得再送 SIGTERM，照 R2 現行方式等結果。 | R3-D2、R3-D3 | `test_r3_lock.py::test_stop_does_not_resignal_while_finalizing` |
| 4.27.5 | `record.sh stop` 等待收尾的上限應不小於錄製實例的收尾總期限加上收尾被中止所需的時間：上限＝3 × max(0, now − `startedAt`) ＋ 630 秒（`finalizeDeadline` 的 ×3＋600，再加 30 秒給 SIGTERM→5 秒→SIGKILL 與寫狀態檔；`startedAt` 不扣暫停，所以一定 ≥ `finalizeDeadline(recordedSeconds)`＋30）；讀不到 `startedAt` 時沿用 7200 秒。實作形狀：`cmd_stop` 不再含 `2 * max(0`；以 `record.sh` 中算上限的那段 Python（`cmd_stop` 內唯一的 `limit="$(python3` 區塊）配一份 `startedAt` 為 now − 100 秒的狀態檔執行，輸出介於 930 與 932 之間；now − 3600 秒 → 11430 到 11432；壞檔 → 7200。 | 修正輪 G；`bin/record.sh:560`；§4.28.5 | `test_r3_lock.py::test_stop_wait_limit_covers_finalize_deadline` |
| 4.27.6 | 既有的 stop／status／暫停控制測試（`test_record_sh.py` 的 `EXIT_CODE_CASES` 中 `stop` 與 `status` 各筆、`test_stop_reports_code_5`、`test_stop_prints_black_intervals`；`test_r2_cli.py` 以 `start_fake` 起替身的各案例）在 Q5 的四項確認上線後**斷言一字不改**仍綠：替身 `fake_recorder.sh` 預設持有 `<home>/record.lock`（`FAKE_LOCK`，預設 `1`）、`_helpers.Sandbox.env` 預設帶 `MH_RECORDER_COMM=bash`（§6 第 136 條）。 | 修正輪 A；`tests/record/fakes/fake_recorder.sh:111` | 既有 `test_record_sh`、`test_r2_cli`；`test_r3_lock.py::test_fake_recorder_holds_lock`（`FAKE_LOCK` 未設時替身存活期間 `record.lock` 被持有、替身被 SIGKILL 後 2 秒內釋放；`FAKE_LOCK=0` 時不持有） |
| 4.27.4 | menu bar 的停止與捨棄送 SIGTERM 前應呼叫 `stopTargetDecision`，只有 `.signal(pid:)` 才送；`Trigger/MenuBar.swift` 含 `SIGTERM` 的每一行都不含 `st.pid`、`status.pid`、`?? st`。 | Q5；`MenuBar.swift:428-431` | `test_r3_app_static.py::MenuBarStatesStatic.test_stop_uses_decision` |

#### 4.28 收尾鎖、逾時、取消、讀不到的段落（Q4、Q3、D12、D14a）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.28.1 | 當另一個程序持有 `錄音/tracks/.finalize.lock` 時，`_record_finalize.py <場次>` 應回 5、stderr 含「這個場次正在收尾」，且場次內所有檔的 mtime 與內容不變（含 `finalize.json` 不存在時不建立）。 | Q4 | `test_r3_finalize_guard.py::test_second_finalize_refused` |
| 4.28.2 | `write_json_atomic` 應用 `tempfile.mkstemp`（同目錄）建暫存檔；`bin/_record_finalize.py` 不得出現 `+ ".tmp"` 或 `'.tmp'` 字面。 | Q4 | `test_r3_finalize_guard.py::test_atomic_write_uses_mkstemp` |
| 4.28.3 | 每個 ffmpeg／ffprobe 子程序都應有逾時；`MH_FFMPEG` 指向 `fakes/slow_ffmpeg.sh`、`MH_FINALIZE_STEP_TIMEOUT=2` 時，`_record_finalize.py` 應在 30 秒內回 5，`finalize.json.timedOut.step` 為 `normalize`、`concat`、`mix`、`probe` 之一，`tracks/seg-*.mov` 全部保留，沒有殘留的 ffmpeg 子程序。 | Q3；D14a | `test_r3_finalize_guard.py::test_step_timeout_exits_5_and_keeps_segments` |
| 4.28.4 | 沒有設 `MH_FINALIZE_STEP_TIMEOUT` 時，逾時應為：ffprobe 30 秒；逐段正規化 max(120, 該段長度 × 10)；串接與混音 max(300, 全片長度 × 3)。（以模組函式 `step_timeout(step, seconds)` 驗：("probe", 60) → 30；("normalize", 5) → 120；("normalize", 60) → 600；("concat", 50) → 300；("mix", 3600) → 10800。） | Q3 | `test_r3_finalize_guard.py::test_step_timeout_values` |
| 4.28.5 | `finalizeDeadline` 應：0 → 600；100 → 900；3600 → 11400；-5 → 600。 | D14a-A | `swift:R3LockTests.swift::testFinalizeDeadline` |
| 4.28.6 | 錄製實例應以 `Capture/FinalizeRunner.swift` 執行收尾：超過 `finalizeDeadline` 或收尾中再收到 SIGTERM 時，對子程序送 SIGTERM、5 秒後仍在就 SIGKILL；狀態寫 `phase=failed`、`code=5`，message 含「收尾逾時」或「收尾已取消」，並含 `meeting record finish`。**補記**（build 收尾補記，`r3-finalize-runner`）：(1) 已在停止中、但收尾子程序還沒啟動（`FinalizeRunner` 尚未建立，即還沒進入 `phase=finalizing`）時再收到停止訊號（SIGTERM 或 SIGINT），只在 `record.log` 記「停止中（還沒進收尾），略過這次停止訊號」，不取消、不改狀態（`RecordingSession.swift:906-913`）；(2) `finalizeDeadline` 的期限以 `DispatchSemaphore.wait(timeout: .now() + 秒數)` 計時，`DispatchTime` 是 uptime 時鐘，**不含系統睡眠**（`FinalizeRunner.swift:106`）；(3) 逾時與取消一律寫 `code=5`、錄製實例以 5 結束（`finalizeAbortOutcome`，`FinalizeRunner.swift:22-33`），不採用子程序被中止後的實際結束碼。實作形狀：`FinalizeRunner.swift` 含 `finalizeDeadline(`、`SIGKILL`；`RecordingSession.swift` 的 `requestStop` 在收尾中不再直接 return（含「取消」分支）。 | Q3；`RecordingSession.swift:818`、`:927` | `test_r3_app_static.py::FinalizeRunnerStatic.test_deadline_and_cancel`；實機（收尾中按「取消收尾」） |
| 4.28.7 | 讀不到的段落應搬到 `錄音/tracks/unreadable/`（撞名加 `-1`、`-2`），`finalize.json.skipped[].movedTo` 記相對路徑；收尾成功後被刪的只有已併入成品的段落。以一個 0 位元組的 `seg-0002.mov` 驗：收尾後 `tracks/unreadable/seg-0002.mov` 存在，`tracks/seg-0002.mov` 不存在，其他段落依 §6 第 111 條照常刪除；`錄音/tracks/finalize.json` 的 `skipped` 恰一筆，是物件、`movedTo` 為 `tracks/unreadable/seg-0002.mov`（§3.17；Red 層補字面）。 | D12-A；§6 第 126 條 | `test_r3_finalize_guard.py::test_unreadable_moved_not_deleted` |
| 4.28.8 | 每一步 ffmpeg／ffprobe 的耗時應由 `_record_finalize.py` 印到 **stdout**，一行一步：`耗時 <步驟>（<對象>）：<秒數> 秒`，`<步驟>` ∈ `normalize`、`concat`、`mix`、`probe`（同 `timedOut.step`），`<對象>` 為原始段落的主檔名（不含副檔名，例 `seg-0001`）或成品檔名，秒數小數 1 位（例 `耗時 normalize（seg-0001）：1.2 秒`）。app 啟動的收尾照現行把 stdout 逐行寫進 `<home>/record.log`（`RecordingSession.swift:926`），`meeting record finish` 直接跑時印在終端；`_record_finalize.py` 不自行開 `record.log`。（Red 層補字面；測試合併讀 stdout、stderr 與 `<home>/record.log`，`test_r3_finalize_guard.py:181-184`） | intent R3-9 衍生工作 | `test_r3_finalize_guard.py::test_step_durations_logged` |

#### 4.29 VTT 講者、raw 不重轉、無效參數（T1、T2、T3）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.29.1 | 同一份 `transcript.segments.json`＋講者分段＋聲紋結果（`apply` false、cos 0.72 的講者 A；`apply` true、cos 0.81 的講者 B），`transcript.vtt` 與 `transcript.speakers.md` 對每一段的講者名稱應完全一致：A 不掛真名（`speakers.md` 用 `_merge_speakers.py`（不改）現行的代號，VTT 不加 `<v>`），B 掛真名。 | T1；鐵則 3 | `test_r3_vtt_raw.py::test_vtt_uses_merge_assignment` |
| 4.29.2 | `_render.py` 不得再有自己的講者比例規則（不得出現 `0.3` 的比例比較）；段落→講者的歸屬以 `importlib` 從 `bin/_merge_speakers.py` 載入既有的 `assign_speaker`（不改該檔）；`speakers.map.json` 的套名判準（有 `apply` 聽 `apply`，沒有就 `confidence` ≥ 0.7；字串值直接套）、`MH_MIN_SPEAKER_SEC` 的併入、證據不足時退到含重疊那份再試一次，照抄 `_merge_speakers.main` 的邏輯，並在函式註解寫明出處行號。 | T1；修正輪 E | `test_r3_vtt_raw.py::test_render_has_no_private_ratio` |
| 4.29.3 | `meeting diarize <場次>` 在缺 `transcript.segments.json` 時，`transcript.raw.md` 的內容與 mtime 應不變；之後 `transcript.segments.json` 存在。替身轉錄指令應收到一個不是場次目錄的輸出目錄。 | T2；`bin/meeting.sh:247` | `test_r3_vtt_raw.py::test_diarize_keeps_raw` |
| 4.29.5 | 照抄的一致性：以至少 6 組 fixture（`apply` true／false、沒有 `apply` 的 `confidence` 0.69 與 0.7、字串值、`MH_MIN_SPEAKER_SEC=5`、需要退到含重疊那份的段落）各跑一次 `_merge_speakers.py`（子程序）與 `_render.py` 的 VTT，對每一段比較「掛的真名」：`speakers.md` 中該段所屬 block 的講者顯示名若是真名，VTT 該 cue 的 `<v>` 應是同一個名字；若是代號或 `SPEAKER_?`，VTT 不加 `<v>`。全部一致。 | T1；修正輪 E；鐵則 3 | `test_r3_vtt_raw.py::test_render_copy_matches_merge` |
| 4.29.4 | `bin/transcribe.sh` 不得出現 `--compression-ratio-threshold`；`meeting-transcribe` 的 SKILL.md 不得再說這個參數有作用。 | T3 | `test_r3_vtt_raw.py::test_no_compression_flag` |

#### 4.30 VAD clip 與品質檔（T4、T5）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.30.1 | 有 `manifest.json.levels` 時，`transcribe.sh` 應把 `_record_lib.py clip` 的結果依 §3.18 以 `--clip-timestamps <start>,<end>,…` 交給 ASR（替身 ASR 記下收到的參數）；raw 標頭第二行為 `> VAD：clip <N> 段，門檻 -60 dBFS，補 0.75 秒，合併間隔 2.0 秒`。 | T4 | `test_r3_transcript_vad.py::test_clip_passed_to_asr` |
| 4.30.2 | 沒有 levels（ingest 的音檔）、全部無聲、或 `MH_VAD=0` 時，送 ASR 的參數應與 R2 相同（沒有 `--clip-timestamps`），raw 標頭第二行分別為 `> VAD：未套用（沒有 levels）`、`（沒有有聲區間）`、`（MH_VAD=0）`。`_record_lib.py clip` 執行失敗（結束碼非 0）或結果解析失敗時同樣退回整檔：VAD 行寫 `> VAD：未套用（沒有 levels）`，並在 stderr 印 `[transcribe] WARN: VAD 計算失敗，退回整檔轉錄：…` 或 `[transcribe] WARN: clip 結果解析失敗，退回整檔轉錄`（`bin/transcribe.sh:69-98`；build 收尾補記）。 | T4 | `test_r3_transcript_vad.py::test_fallback_without_levels` |
| 4.30.3 | `MH_VAD_THRESHOLD_DB`、`MH_VAD_PAD`、`MH_VAD_MERGE_GAP` 應覆寫預設值並反映在 raw 標頭。 | T4 | `test_r3_transcript_vad.py::test_vad_env_overrides` |
| 4.30.4 | `transcript.segments.json` 應一律輸出（沒設 `MH_EMIT_SEGMENTS` 也有）。 | T5 | `test_r3_transcript_vad.py::test_segments_always_written` |
| 4.30.5 | `transcript.quality.json` 應符合 §3.18：fixture 有一段「好的好的好的好的」重複（`no_speech_loop`）、一段壓縮比 > 2.4（`compression_ratio`）、連續 4 段相同文字（`repeat_run`，4 筆），其餘段落不得列入；沒有問題的 fixture → `[]`。`QUALITY_WARNING` 的既有輸出格式不變。 | T5 | `test_r3_transcript_vad.py::test_quality_file` |
| 4.30.6 | 衍生檔（`transcript.speakers.md`、VTT）中，列在 `transcript.quality.json` 的段落文字前應加「（聽不清）」（`speakers.md` 由 §4.31.10 的後處理加）；`transcript.raw.md` 不得出現「（聽不清）」以外的任何改動（與沒有品質檔時的 raw 逐位元相同）。 | T5；鐵則 1、4 | `test_r3_annotations.py::test_unclear_marked_in_derived_only` |

#### 4.31 標示與標記（T6、T7、D11）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.31.1 | 有 `pauseEvents`（一組 120→210 秒的暫停）、`micMuteEvents`（300→330）、一筆輸出裝置 `deviceEvents`、兩路連續 40 秒 ≤ -60 dBFS 的場次，`transcript.speakers.md`（經 §4.31.10 後處理）與 VTT 應依 §3.18 各出現一行對應註記（時間為成品時間），VTT 的註記在 `NOTE` 區塊。 | T6 | `test_r3_annotations.py::test_annotations_in_speakers_and_vtt` |
| 4.31.2 | 長靜音判斷：連續 29.5 秒不標、30 秒標；落在暫停區間內的不標。 | T6 | `test_r3_annotations.py::test_long_silence_threshold` |
| 4.31.3 | 標記對齊：t 在某段 `start ≤ t < end` 掛該段；在兩段之間掛下一段；離最近一段 > 2 秒獨立成行。例：段落 [0,5)、[8,12)，t=4.9 → 第 1 段；t=6 → 第 2 段；段落 [0,5)、[20,25)，t=10 → 獨立。「掛下一段」與「獨立成行」的差別只在 `transcript.speakers.md` 的插入位置（§4.31.10）；VTT 兩者都是依時間排在前後 cue 之間的 `NOTE`。**自動測試只驗順序**（VTT 中標記 `NOTE` 與前後 cue 的先後，`test_r3_annotations.py:263-265`），不區分「掛下一段」與「獨立成行」（Red 層補字面）。 | T7 | `test_r3_annotations.py::test_marker_alignment` |
| 4.31.4 | `meeting.record.json` 有 `markers[]` 時應通過 `schema/meeting-record.v1.json` 驗證；`markers` 的 `t` 為負數、缺 `label` 時驗證失敗；沒有 `markers` 的既有 fixture 仍通過。 | D11-A | `test_r3_annotations.py::test_schema_markers_optional` |
| 4.31.5 | `summary.md` 應依 §3.18 加「## 標記」「## 錄製註記」；沒有標記、沒有事件時兩段都不出現（與 R2 輸出逐位元相同）。 | T7、T6 | `test_r3_annotations.py::test_summary_sections`、`::test_summary_unchanged_without_events` |
| 4.31.6 | `meeting.record.json` 沒有 `markers` 時，`## 標記` 應取 `錄音/markers.json`；兩者都有時以 `meeting.record.json` 為準。 | R3-D5 | `test_r3_annotations.py::test_markers_source_precedence` |
| 4.31.7 | `summary.md` 與註記行不得含裝置名稱、uid 或視窗標題。 | intent R3-4 第 8 點 | `test_r3_annotations.py::test_no_device_names` |
| 4.31.9 | `bin/summarize-local.py` 寫出的 `summary.md` 應在模型輸出之後接上與 `_render.py` 相同的「## 標記」「## 錄製註記」（以 `importlib` 呼叫 `_render.py` 的同一個函式，不另寫一份）；沒有標記、沒有事件時兩段都不出現（與現行輸出相同）。測試以替身模型（不連 ollama）驗。 | 修正輪 J；§3.18 | `test_r3_annotations.py::test_local_summary_sections` |
| 4.31.10 | `transcript.speakers.md` 的後處理：`meeting.sh` 的 `run_diarize` 在 `_merge_speakers.py` 成功後呼叫 `python3 "$BIN/_render.py" <場次> --annotate-speakers`；它依 §3.18 插入註記行（插在所掛段落所屬 block 的標頭行之前；獨立成行者依時間插在前後 block 之間）、在 `transcript.quality.json` 列出的段落文字前加「（聽不清）」。後處理以同一套歸屬重建 block，重建出的 block 文字與檔案不同時不動該 block 並在 stderr 記一行；除插入的行與「（聽不清）」外，`speakers.md` 的其他位元組不變；對已處理過的檔再跑一次結果不變（冪等）。`--annotate-speakers` 由 `r3-vtt-raw` 先接好（沒有事件、沒有品質檔時不改檔），註記內容由 `r3-annotations` 補上。 | T5、T6、T7；修正輪 E | `test_r3_vtt_raw.py::test_annotate_hook_noop`；`test_r3_annotations.py::test_speakers_post_process`、`::test_speakers_post_process_idempotent` |
| 4.31.8 | 下游相容：加了兩個新段的 `summary.md` 交給下游知識庫專案的 `meetings._missing_sections(text)`（以 `importlib` 從該專案的 `tools/meetings.py` 載入，唯讀）應回空清單；該專案不存在時測試標 skip 並在報告寫 `not_verifiable`，test 段由主 session 補跑。 | D11；`.claude/teams/rules.md:67` | `test_r3_annotations.py::test_downstream_missing_sections` |

#### 4.32 `_record_lib.py` 與共用向量（Q9a）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.32.1 | `tests/record/vectors/output_time.json` 每一筆 `{t, first_start, pauses, l_out, expect}` 應同時滿足：`_record_lib.output_time` 結果 = `expect`（±0.0005）；`l_out=0` 的筆與 `e2e_check.record_to_output` 結果相同；Swift `outputTime(recordT:firstSegmentStart:pauses:lOut:)` 結果相同。向量至少涵蓋 R2 §4.18 的 `outputTime` 案例、沒配對的 pause、`l_out=0.18`。 | Q9a | `test_r3_record_lib.py::test_output_time_vectors`；`swift:R3RecordLibVectorTests.swift::testOutputTimeVectors` |
| 4.32.2 | `levels_intervals(levels, window, threshold_db, merge_gap, pad, total)` 應回 `[[start, end], …]`（遞增、不重疊）：`levels` 是**一維陣列**，第 i 個元素是窗 [i × `window`, (i+1) × `window`) 的 dBFS 或 `null`（`clip_timestamps` 傳入的是同一窗兩路的 max，`null` 視為無聲，`design.md` R3-D6 T4）；門檻嚴格大於（-60.0 視為無聲）；間隔 < `merge_gap` 合併、= 不合併；前後補 `pad` 但夾在 [0, total]；`null` 視為無聲。向量檔 `levels_intervals.json`（陣列，每筆 `{name, levels, window, threshold_db, merge_gap, pad, total, expect}`）Python 與 Swift 共用。有聲區間**只在 Python 端計算**：Swift Core **不新增** `levelsIntervals`（§3.20 不列），Swift 測試只驗共用向量本身合乎本條規則，語意比對只在 Python（Red 層補字面）。 | Q9a、T4 | `test_r3_record_lib.py::test_levels_intervals_vectors`（語意比對）；`swift:R3RecordLibVectorTests.swift::testLevelsIntervalsVectors`（只驗向量合乎規則） |
| 4.32.3 | `paused_total` 應等於已配對暫停長度和（沒配對的不計）；`clip_timestamps(rec_dir)` 在缺 `manifest.json` 或沒有 `levels` 時回 `None`。 | Q9a | `test_r3_record_lib.py::test_paused_total_and_clip_none` |
| 4.32.4 | `python3 bin/lib/_record_lib.py clip <錄音目錄>` 應印 §3.19 的 JSON、回 0；目錄不存在回 2。 | §3.19 | `test_r3_record_lib.py::test_cli_clip` |
| 4.32.5 | `bin/lib/` 底下每一個 `*.py` 都應通過 `ast.parse`，且 `bin/lib/_record_lib.py` 存在；`bash bin/_lint.sh` 仍回「lint 通過（26 個檔）」。 | `req:280`；修正輪 E；§4.24.5 | `test_r3_record_lib.py::test_bin_lib_syntax`；既有 `test_regression.py::test_lint_passes_26_files`（不改） |
| 4.32.6 | `merge_defaults`：缺檔 → 只有 `updates` 的鍵；既有 7 鍵＋不認得的 `x` → 只改 `updates` 的鍵；檔案不是 JSON 物件 → 丟例外、檔案位元組不變；另一程序持鎖 6 秒 → 約 5 秒後丟逾時例外、不寫。 | §3.15、§3.19 | `test_r3_record_lib.py::test_merge_defaults` |

#### 4.33 `meeting search`（F1）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.33.1 | 根目錄下兩個場次都含關鍵字時，應回 0、依 §3.19 的格式輸出，較新的場次在前；`<檔名>` 帶 `錄音/`（§3.19）；大小寫不分（`Stand-up` 搜得到 `stand-up`）；關鍵字含 `.*` 時照字面比對。 | F1 | `test_r3_search.py::test_hits_sorted_and_literal` |
| 4.33.2 | 沒有結果回 1、stdout 空；缺參數或根目錄不存在回 2。 | F1；R3-§2.2 | `test_r3_search.py::test_exit_codes` |
| 4.33.3 | 不得讀根目錄以外的檔（以根目錄外放一個含關鍵字的檔、symlink 進根目錄驗：不出現在結果）。 | 客戶資料邊界 | `test_r3_search.py::test_single_root_only` |
| 4.33.4 | `meeting.sh help` 應列出 `search`；`meeting.sh` 原有子指令與結束碼不變（`test_cli_dispatch.py::test_existing_exit_codes_unchanged` 不改）。 | §4.1.3 | `test_r3_search.py::test_usage_lists_search` |

#### 4.34 提醒事項（F5）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.34.1 | `meeting reminders <場次> --list 範例清單 --dry-run` 應印 §3.19 的項目陣列、回 0、不呼叫替身 app；`uid` 與同一場 `actions.ics` 的 `UID:` 完全相同；缺負責人時 `notes` 含「負責人：（未定）」，缺期限時 `due` 為 `null`。 | F5；鐵則 2 | `test_r3_reminders.py::test_dry_run_items`、`::test_uid_matches_ics` |
| 4.34.2 | 非 dry-run 時應以 `open -W -n -a … --args reminders --input … --list …` 呼叫 app（以 `MH_RECORD_OPEN` 替身記錄參數），並以結果檔的 `code` 為結束碼；替身不寫結果檔時回 5；場次沒有 `meeting.record.json` 回 2。 | F5；R3-§2.2 | `test_r3_reminders.py::test_invokes_app_and_maps_code` |
| 4.34.3 | app 的 `reminders` 子指令應：用 `requestFullAccessToRemindersWithCompletion`；以 `URL`（`meetingharness://action/`）去重；清單不存在回 3 不代建；權限被拒回 4。實作形狀：`Capture/Reminders.swift` 含 `requestFullAccessToReminders`、`fetchRemindersMatchingPredicate`、`meetingharness://action/`、`saveReminder`，且不含 `saveCalendar`；`main.swift` 分派 `reminders`；`Info.plist` 含提醒事項權限說明鍵（鍵名照 Apple 文件，§7 疑慮 45），說明文字含「iCloud」。 | F5；R3-Q3 | `test_r3_app_static.py::RemindersStatic.test_eventkit_shape`；實機（寫入兩次，第二次 created=0） |
| 4.34.4 | SKILL.md 與 README 應說明「清單開了 iCloud 同步時，內容會離開本機」與 `--dry-run`。 | intent R3-4 第 5 點 | `test_r3_docs.py::test_reminders_documented` |

#### 4.35 影音一致的量測與延遲紀錄（S-A、D3、S-B）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.35.1 | `e2e_check.py --sync`（`c_sync`，ffplay 路徑，< 100 ms）的行為與 R2 相同；`test_e2e_check.py::test_hfp_and_sync_check` 不改。 | D3-A | 既有測試 |
| 4.35.2 | `e2e_check.py --sync-player <場次>` 應：把閃白與嗶聲配對後依 60 秒時段分組，每組取差值中位數；全部組 \|中位數\| < 45 ms → PASS。合成 fixture：某一組有一個 159 ms 的離群值、其他 8 個差值 20 ms → PASS；所有差值 60 ms → FAIL。有 `錄音/tracks/finalize.json` 的 `syncCompensation` 時，報告列出各段套用的延遲（秒，例 `0.15`）。檢查名為 `sync_player`（`--json` 輸出中恰一筆檢查名含 `player`；命名同既有 `sync`、`segment_tracks` 的蛇形寫法；Red 層補字面）。 | D3-A；`spec.md:708` | `test_r3_sync_measure.py::test_sync_player_median` |
| 4.35.3 | `e2e_check.py --sync-acoustic <場次>` 應印每個 60 秒時段的 mic − sys 中位數（毫秒，整數）與組數，回 0（只報數字）；沒有可配對的嗶聲時印「沒有可配對的嗶聲」、回 0。**輸入**（Red 層補字面）：讀 `<場次>/錄音/tracks/` 的雙音軌段落（收尾前、或 `keep-segments` 保留的 `seg-*.mov`；第 1 條音軌＝系統聲音、第 2 條＝麥克風）與 `tracks/manifest.json` 的 `segments[].startedAt`；嗶聲時刻＝各音軌過 `band_pcm` 的 1 kHz 帶通、1 ms 窗 RMS 包絡，每個 > -60 dBFS 的峰取第一個 ≥ 峰值 50% 的窗起點（同 `sync_offsets` 的起點判定），加上該段 `startedAt` 換成錄製時鐘；每個系統嗶聲配 ±0.5 秒內最近的麥克風嗶聲，配不到的不計。時段＝錄製時鐘 [0, 60)、[60, 120)、…。**輸出**（stdout，每個有配對的時段一行，依時間遞增）：`<mm:ss>–<mm:ss> mic − sys 中位數 <整數> ms（<n> 組）`，`<n>`＝該時段配對到的嗶聲數（例 `00:00–01:00 mic − sys 中位數 80 ms（4 組）`；負值寫 ASCII 減號）。 | S-A | `test_r3_sync_measure.py::test_sync_acoustic_report` |
| 4.35.4 | `e2e_check.py --print-sync-file <路徑>` 應只寫到指定路徑，產出可被 `ffprobe` 讀出影像與聲音兩軌的檔。 | S-A | `test_r3_sync_measure.py::test_print_sync_file` |
| 4.35.5 | `reportedLatencySeconds` 應：(48000, 24, 144, 0, 512) → 0.0142（小數 4 位）；任一參數 nil → nil；`sampleRate` 0 → nil。`OutputLatency` 不得是 `AudioDeviceInfo` 的欄位，`AudioDeviceInfo` 的 Equatable 結果不受延遲值影響。 | S-B | `swift:R3SyncTests.swift::testReportedLatency` |
| 4.35.6 | `RecordMeta.outputLatencies` 為 nil 時編碼不得有該鍵（`testMetaJSONKeys` 不改）；有值時鍵名同 §3.17。 | S-B；R2-Q10 | `swift:R3SyncTests.swift::testOutputLatenciesOmittedWhenNil` |
| 4.35.7 | 錄製實例應在開錄時與每筆輸出裝置 `deviceEvents` 時 append 一筆 `outputLatencies`；只用 `AudioObjectGetPropertyData` 讀，不得出現 `AudioObjectSetPropertyData`（§4.9.4 照舊）。實作形狀：`AudioDeviceMonitor.swift` 含 `kAudioDevicePropertyLatency`、`kAudioDevicePropertySafetyOffset`、`kAudioStreamPropertyLatency`、`kAudioDevicePropertyBufferFrameSize`；`AudioDeviceInfo` 的宣告區塊不含 `latency`。 | S-B | `test_r3_app_static.py::LatencyLogStatic.test_latency_read_only` |

#### 4.36 `SegmentScheduler`（Q6）

時間單位為秒（錄製時鐘）；`seg` 從 1 起編；每列是「已處理的事件序列 → 最後一個事件回傳的動作」。`segmentSeconds=60`。

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.36.1 | `sample(video, 0.0, 0.016)` → `[open(1, .first, 0.0), write(1, video)]`。 | Q6；R2-D3a | `swift:R3SegmentSchedulerTests.swift::testFirstSample` |
| 4.36.2 | 定期換段：…之後 `sample(system, 60.0, 60.02)` → `[open(2, .periodic, 60.0), write(2, system)]`，`prev == 1`；之後 `sample(mic, 59.99, 60.01)` → `[write(1, mic), write(2, mic)]`（跨邊界兩邊都寫，`routeSample` 語意）；**收 prev 的條件**（照現行 `RecordingSession.swift:436-440`；Red 層補字面）：三路（video、system、mic）各自都出現過一個對 prev 邊界 `routeSample` 結果 `!= .old`（即 `.new` 或 `.both`，**跨邊界的 sample 也算數**）的 sample 時，該 sample 的回傳含 `finish(1)`，之後 `prev == nil`；回傳中 `write` 在前、`finish` 在後（自動測試只驗含有）。例：上述 system 60.0（`.new`）與 mic 59.99–60.01（`.both`）之後，`sample(mic, 60.01, 60.03)` → `[write(2, mic)]`（video 還沒有），`sample(video, 60.016, 60.016)` → 含 `finish(1)` 與 `write(2, video)`。 | §3.2；`routeSample` | `swift:R3SegmentSchedulerTests.swift::testPeriodicSwitchAndPrevClose` |
| 4.36.3 | prev 逾時：有 prev 時 `prevTimeout(segment: 1)` → `[finish(1)]`；prev 已收掉時同一事件 → `[]`。 | 現行 1 秒收尾 | `swift:R3SegmentSchedulerTests.swift::testPrevTimeout` |
| 4.36.4 | 暫停／繼續：已處理 sample 的最大 end 為 10.0 時 `pause` → 目前段轉 prev（停止點 E＝10.0），回傳不含 `open`；`sample(video, 9.98, 10.0)` → `[write(1, video)]`；`sample(video, 12.0, 12.016)` → `[drop(video)]`；`resume` → `[]`；`sample(mic, 15.0, 15.02)` → `[open(2, .resume, 15.0), write(2, mic)]`。沒有目前段時 `pause` 不開段、不 `cancel`。暫停時目前段沒有寫過任何 sample → 回傳 `cancel(該段)`：這是**防禦性分支**，只用 §3.20 的公開事件造不出「目前段已開、沒有 sample」（每個 `open` 都伴隨同一 sample 的 `write`），**自動測試只驗反面**：目前段有內容時 `pause` 不得 `cancel`（Red 層補字面）。 | R2-D3 | `swift:R3SegmentSchedulerTests.swift::testPauseResume`、`::testPauseEmptySegmentCancelled` |
| 4.36.5 | 停止：目前段有內容 → `stop` 回傳 `finish(目前段)`（有 prev 也一併 `finish`）；目前段剛開、沒有 sample → `cancel(目前段)`（**防禦性分支**，理由同 4.36.4；**自動測試只驗反面**：目前段有內容時 `stop` 不得 `cancel`、不得 `open`；Red 層補字面）；`stop` 之後任何 `sample`（含 `formatChanged: true`）→ `[drop(…)]`。 | §4.6 | `swift:R3SegmentSchedulerTests.swift::testStopFinishOrCancel` |
| 4.36.6 | writer 失敗：`writerFailed(segment: 1)` → `[]`、`current == nil`；下一個 `sample(video, 30.0, 30.016)` → `[open(2, .writerFailure, 30.0), write(2, video)]`；連續再失敗一次 → 下一個 sample 開 `open(3, .writerFailure, …)`；新段邊界不早於上一段起點。 | `RecordingSession.swift:560` | `swift:R3SegmentSchedulerTests.swift::testWriterFailureRepeated` |
| 4.36.7 | 格式變更：`sample(system, 20.0, 20.02, formatChanged: true)` → `[open(2, .formatChange, 20.0), write(2, system)]`；1 秒內同一路再一次 `formatChanged` → 不開新段。 | D20；§4.9.3 | `swift:R3SegmentSchedulerTests.swift::testFormatChange` |
| 4.36.8 | 輸出裝置變更：`outputDeviceChange` → `[]`；下一個 sample（任一路，start=s）→ `[open(n, .outputDeviceChange, s), write(n, …)]`；暫停中發生的 `outputDeviceChange` 由 `resume` 的換段吸收（不另開段）。 | S-C；R3-D9 | `swift:R3SegmentSchedulerTests.swift::testOutputDeviceChange` |
| 4.36.9 | `SwitchReason.allCases` 應恰為 `[.first, .periodic, .formatChange, .writerFailure, .resume, .outputDeviceChange]`。 | §6 第 127 條 | `swift:R3SyncTests.swift::testSwitchReasonCases`；`ControlTests.swift::testPauseGateAndSwitchReason`（§6 第 127 條改預期） |
| 4.36.10 | `RecordingSession.swift` 應只依 `SegmentScheduler.handle` 回傳的動作開段、寫入、收段：`ingest` 內不得再直接呼叫 `openReason(`、`routeSample(`、`shouldSwitchForFormat(`；輸出裝置變更時呼叫 `handle(.outputDeviceChange)`。 | Q6 | `test_r3_app_static.py::SegmentSchedulerStatic.test_session_delegates_to_scheduler`；實機（全套 e2e 迴歸） |
| 4.36.11 | 實作形狀（給 §6 第 137 條改綁的既有靜態測試）：`Core/SegmentScheduler.swift` 處理 `sample` 的程式在一個名為 `ingest` 的函式（`mutating func ingest(`，由 `handle` 呼叫）裡，以名為 `maxEnd` 的屬性記已處理 sample 的最大 end，且 `pauseRoute(` 出現在 `maxEnd =` 之前；`SegmentScheduler.swift` 呼叫 `pausing(`、`resuming(`、`pauseRoute(`、`segmentOpened(`、`openReason(`、`routeSample(`；`RecordingSession.swift` 仍呼叫 `detectorFeed(`、`.interrupt(at:`、`sysSilence.reset()`、`micSilence.reset()`、`appendingPauseEvent`、`pauseStatusFields`、`applyingPauseFields`、`appendingMuteEvent(`。`r3-core` 合併後 `test_r2_static.py` 的 `test_capture_*` 與 `test_static_rules.py::test_segment_writer_uses_assetwriter` 綠，`r3-segment-scheduler` 合併後仍綠。 | 修正輪 B；`test_r2_static.py:128-145`；`test_static_rules.py:321-332` | `test_r2_static.py::test_capture_pause_gate_before_maxend`、`::test_capture_uses_core_pause_functions`、`test_static_rules.py::test_segment_writer_uses_assetwriter`（§6 第 137 條改綁） |

#### 4.37 S-C：依時段補償系統聲音

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.37.1 | `meeting sync` 不帶參數應印 `syncCompensation=off`（缺鍵時）並回 0；`meeting sync reported` 應合併寫入（其他 7 鍵與不認得的鍵保留）、回 0；`meeting sync foo`、`meeting sync a b` 回 2 且檔案不變；`record.defaults.json` 不是 JSON 物件時回 2、檔案不變。`meeting help` 的其他指令段列出 `sync`。 | R3-Q6；R3-§2.2；修正輪 E | `test_r3_search.py::test_meeting_sync_cli` |
| 4.37.2 | mode 解析：`MH_SYNC_COMPENSATION` 有值時優先；否則讀 `record.defaults.json.syncCompensation`；都沒有＝`off`；不認得的值＝`off` 並在 `record.log` 記一行。段落還在的場次，解析出的 mode 與上次 `finalize.json.syncCompensation.mode` 不同時應重做收尾（冪等判斷含 mode；§3.17，build 收尾補記）。 | R3-D9 | `test_r3_sync_compensate.py::test_mode_resolution` |
| 4.37.3 | `off` 時應走 R2 的 D20 流程：`finalize.json.syncCompensation` 為 `{"mode": "off", "segments": []}`；以 `_media.py` 合成的同一份 `tracks/`，成品長度與 R2 版本相差 ≤ 0.1 秒，`--sync` 的每個事件差值變化 ≤ 1/60 秒，全套 e2e 判準（`e2e_check.py` 預設組）結果與 R2 版本相同。 | intent R3-4 第 6 點；R3-D9 的等價判準 | `test_r3_sync_compensate.py::test_off_equivalent` |
| 4.37.4 | `reported` 時：兩段、輸出延遲分別為 0.0 與 0.150 秒的合成場次，成品中第 2 段系統聲音的嗶聲應比 off 時晚 0.150 ± 0.005 秒、第 1 段不變；成品總長與 off 相差 ≤ 0.1 秒；`finalize.json.syncCompensation.segments` 兩筆的 `delaySeconds` 為 0.0 與 0.15、`source` 為 `reported`；系統聲音只在段界（L 由 0 變 0.150 處）有一段 0.150 ± 0.005 秒的靜音。**多段、延遲固定、段界無空洞**：三段（每段 2 秒、`segmentSeconds` 換段）、三段的輸出延遲都是 0.150 秒、系統聲音是跨段連續的 1 kHz 正弦：成品系統聲音在開頭 0.150 秒之後到結尾，每個 10 ms 窗的 RMS 都 > -40 dBFS（段界沒有空洞、沒有截掉），三段的嗶聲都比 off 晚 0.150 ± 0.005 秒，總長與 off 相差 ≤ 0.1 秒。延遲只在 L 改變處補靜音（變大）或截掉重疊（變小，截前一段的尾），不在每個段界截尾（ADR `adr-r3-concat-then-mix.md`）。補償區間（相鄰且延遲相同的段併成一個）只印到 stdout／`record.log`，不寫進 `finalize.json`（§3.17，build 收尾補記）。 | R3-D9；ADR；修正輪 C | `test_r3_sync_compensate.py::test_reported_delays_per_segment`、`::test_constant_delay_no_gaps`、`::test_delay_decrease_trims_overlap` |
| 4.37.5 | `calibrated` 時：`sync-calibration.json` 有該 uid → 用它（`source: calibrated`）；沒有 → 0（`source: missing`）；值 0.8 → 夾到 0.5（`clamped: true`）。`reported` 時場次完全沒有 `outputLatencies` → `source: none`、該段值讀不到或沒有生效的那筆 → `source: missing`，兩者延遲都是 0（§3.17，build 收尾補記）。 | R3-Q6 | `test_r3_sync_compensate.py::test_calibrated_lookup_and_clamp` |
| 4.37.6 | 錄製實例應在輸出裝置變更時提前換段（不論 mode），`manifest.json.segments` 的邊界與該筆 `deviceEvents.t` 相差 < 0.5 秒。 | R3-D9 | `test_r3_app_static.py::SyncCompensateStatic.test_device_change_split`；實機 |
| 4.37.7 | `e2e_check.py --sync-player` 對 `reported` 收尾的合成場次（播放端延遲 0.150 秒的模擬）應 PASS、對同一場 off 收尾的成品應 FAIL。 | D3；S-C | `test_r3_sync_compensate.py::test_sync_player_with_compensation` |
| 4.37.8 | S-C 的預設值在 R3 維持 `off`；改預設要在實機驗收場 E2／E4 之後由使用者決定，並記 §6。 | 使用者決定 2 | `test_r3_sync_compensate.py::test_default_off` |

#### 4.38 選單列圖示 8 種外觀（U1）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.38.1 | `menuBarModel` 的 `appearance` 應：M1、M5 → `.idle`；M8 → `.preparing`；M9 → `.recording`（`micMuted` 時 `.recordingMuted`）；M7 → `.recordingAlert`；M6b → `.paused`（有告警類 warning 時 `alertBadge` true）；M6a、M10 → `.finalizing`；M2、M3、M4、M6 → `.failed`。`state` 與 `symbolName` 與 R2 相同（`TriggerTests` 與 `MenuBarR2Tests` 不改）。 | U1 | `swift:R3MenuBarTests.swift::testAppearanceMapping` |
| 4.38.2 | `spokenDuration`：0 → "已錄 0 秒"；59 → "已錄 59 秒"；60 → "已錄 1 分"；125 → "已錄 2 分 5 秒"；3600 → "已錄 1 小時"；3725 → "已錄 1 小時 2 分"；-3 → "已錄 0 秒"。錄製中與暫停中的 `accessibilityLabel` 應含 `spokenDuration`，不含 `timerText` 的「01:02」寫法。 | U1；無障礙 | `swift:R3MenuBarTests.swift::testSpokenDuration` |
| 4.38.3 | **外觀＝U1-C 錄製膠囊**（`design-r3/README.md` §2、`design-r3/U1-MenuBar.dc.html` 的 C 列）：待機用 SF Symbol `record.circle`（template）；其他 7 種是**自訂**繪製的非 template 圖（`NSImage(size:flipped:drawingHandler:)`，`isTemplate = false`），形狀、符號、字與顏色一律取自 `menuBarCapsuleStyle(…)`（§4.38.5），`dark` 取自 status item 按鈕的 `effectiveAppearance`、`increaseContrast` 取自 `NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast`。靜音分段膠囊左段的麥克風斜線用 SF Symbol `mic.slash`（`paletteColors` 白、非 template）。計時用 `monospacedDigitSystemFont`、字級 `DarkroomType.capsule`；設定 `showTimer` 為 false 時不畫計時、膠囊照畫。準備中與收尾中不得畫紅色。`MenuBar.swift` 不得出現 `systemRed`、`contentTintColor`。 | U1；R3-Q8＝B；使用者選定 U1＝C | `test_r3_app_static.py::MenuBarStatesStatic.test_capsule_drawing`；`test_r2_static.py::test_trigger_status_item_variable_length`（§6 第 129 條改預期）；設計審查（實機截圖：深色／淺色選單列、增加對比、灰階） |
| 4.38.4 | status item 應設 `autosaveName`（使用者拖動後重開仍保留位置）。 | intent R3-9 | `test_r3_app_static.py::MenuBarStatesStatic.test_autosave_name`；實機 |
| 4.38.5 | `menuBarCapsuleStyle(a, alertBadge:, dark:, increaseContrast:)` 應回下表（「深／淺」＝`dark` true／false；「增對比」＝`increaseContrast` true，未寫的欄與一般相同）。共同：`idle` → `shape .templateSymbol`、`glyph .none`、`label ""`、`showsTimer false`、`fill/border/text nil`、`borderWidth 0`、`badge false`、`largeText false`（四種組合都一樣）。`preparing` → `.outline`、`.none`、`"檢查中"`、無計時、`fill nil`、`borderWidth 1.5`；深：`border processing`、`text processingText`；淺：`border` 與 `text` 都是 `processingTextOnLight`。`recording` → `.filled`、`.dot`、`""`、有計時、`border nil`、`borderWidth 0`、`text onSignal`；`fill`：深 `recording`、淺 `recordingOnLight`、深增對比 `recordingHighContrast`、淺增對比 `recordingHighContrastOnLight`；`largeText`＝深且非增對比。`recordingMuted` → `.split`、`.micSlash`，其餘同 `recording`，另 `border`＝同 `fill`、`borderWidth 1`。`recordingAlert` → 同 `recording`，另 `border attention`、`borderWidth 1.5`、`badge true`。`paused` → `.filled`、`.pause`、`""`、有計時、`fill attention`、`text onAttention`、`badge`＝`alertBadge`、`largeText false`；深：`border nil`、`borderWidth 0`；淺：`border attentionTextOnLight`、`borderWidth 1`。`finalizing` → `.filled`、`.none`、`"收尾中"`、無計時、`text onSignal`；`fill`：深 `processing`、淺 `processingOnLight`、深增對比 `processingOnLight`、淺增對比 `processingTextOnLight`；`largeText`＝深且非增對比。`failed` → `.outline`、`.none`、`"需處理"`、無計時、`fill nil`、`borderWidth 1.5`；深：`border recording`、`text recordingText`；淺：`border` 與 `text` 都是 `failedTextOnLight`。（以上 token 名都是 `DarkroomColor.` 的成員。） | U1；`design-r3/README.md` §2 | `swift:R3DesignTokenTests.swift::testCapsuleStyleTable` |
| 4.38.6 | 對 7 種非待機外觀 × 深淺 × 增對比與否（`alertBadge` 取 false 與 true）：(a) 文字對比 `contrastRatio(text, fill ?? 選單列底)` ≥ 4.5，`largeText` 為 true 時 ≥ 3.0；增對比時 `largeText` 必為 false；(b) 外形對比 max(`contrastRatio(fill, 選單列底)`, `contrastRatio(border, 選單列底)`)（nil 當 0）≥ 3.0；(c) 角標（`attention` 底、`onAttention` 描邊）對選單列底的 max 對比 ≥ 3.0。選單列底＝深 `menuBarDark`、淺 `menuBarLight`。(d) 8 種外觀（`alertBadge` false）的（`shape`, `glyph`, `label`, `showsTimer`, `badge`）兩兩不同，`paused` 帶 `alertBadge` true 時也和其他 7 種不同（灰階可分，WCAG 1.4.1）。(e) `contrastRatio("#FFFFFF", "#000000")` 與 21 的差 < 0.01；`contrastRatio("#FFFFFF", "#FF4D4F")` 與 3.27 的差 < 0.01；`contrastRatio("x", "#000000")` = 0。 | U1；WCAG 1.4.1、1.4.3、1.4.11 | `swift:R3DesignTokenTests.swift::testCapsuleContrast`、`::testCapsuleShapesDistinct`、`::testContrastRatio` |
| 4.38.7 | `menuBarAccessibilityLabel`（`spoken` 例「已錄 12 分 34 秒」、`alertText` 例「麥克風已連續 15 秒幾乎沒有聲音」）：`idle` → 「MeetingRecorder：待機中」；`preparing` → 「MeetingRecorder：開錄前檢查中」；`recording` → 「MeetingRecorder：錄製中，已錄 12 分 34 秒」；`recordingMuted` → 「MeetingRecorder：錄製中，已錄 12 分 34 秒，麥克風靜音」；`recordingAlert` → 「MeetingRecorder：錄製中，已錄 12 分 34 秒，有告警：麥克風已連續 15 秒幾乎沒有聲音」（`alertText` nil 時結尾只到「，有告警」）；`paused` → 「MeetingRecorder：已暫停，已錄 12 分 34 秒」，`alertBadge` 時再加「，有告警」；`finalizing` → 「MeetingRecorder：收尾中」；`failed`（`status`「開錄前檢查沒過」）→ 「MeetingRecorder：需要處理：開錄前檢查沒過」。status item 按鈕的 `accessibilityLabel` 與 `toolTip` 都用它（取代 R2 的 `accessibilityText`，§6 第 135 條）。 | U1；無障礙 | `swift:R3DesignTokenTests.swift::testMenuBarAccessibilityLabel`；`test_r3_app_static.py::MenuBarStatesStatic.test_capsule_drawing`（含 `menuBarAccessibilityLabel(`） |
| 4.38.8 | `DarkroomColor.all` 恰為 34 項、每個值符合 `^#[0-9A-F]{6}$`，且與 §3.20 列的值逐一相等；`DarkroomType`、`DarkroomMetric` 的每個成員等於 §3.20 的值；`DarkroomMetric.spacing` 每項都是 4 的倍數。 | `design-r3/README.md` §1 | `swift:R3DesignTokenTests.swift::testColorTokens`、`::testTypeAndMetricTokens` |

#### 4.39 通知分級（U3）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.39.1 | `notificationPolicy`：`alertWarning` 且 `timeSensitiveAllowed` → `.timeSensitive`，不允許時 `.active`；`failure`、`completion`、`meetingDetected` → `.active`；`hotkeyFeedback`、`onboarding` → `.passive`。`threadIdentifier`＝非空 `runId`，否則 `"mh.app"`；`meetingDetected` 一律 `"mh.app"`。 | U3 | `swift:R3MenuBarTests.swift::testNotificationPolicy` |
| 4.39.2 | `newAlertWarnings(previous:current:)` 只回 `current` 中 `isAlert` 為 true 且（`t`, `kind`）不在 `previous` 的項；同一則告警連續兩次輪詢只發一次。 | U3 | `swift:R3MenuBarTests.swift::testNewAlertWarnings` |
| 4.39.3 | 錄製中出現新告警時，menu bar 應發通知（`interruptionLevel` 依 4.39.1、`threadIdentifier` 依 4.39.1）；通知標題與內文不得含場次名或視窗標題（**由實機驗收場確認**，§4.47.4 觸發告警時一併檢查通知文字；自動測試不驗；Red 層補字面）。entitlements 依 §6 第 138 條恰為 3 項（閘門 2 疑慮 57 選 (b)）。實作形狀：`Notifier.swift` 含 `interruptionLevel`、`threadIdentifier`；`MenuBar.swift` 呼叫 `newAlertWarnings(`。 | U3；R3-D11 | `test_r3_app_static.py::NotifyStatic.test_policy_applied`；實機（Time Sensitive 是否生效，§7 疑慮 44；通知不含場次名與視窗標題，§4.47.4） |
| 4.39.4 | 通知的文字與動作照本節；外觀為系統原生（D11 不出稿）。 | intent R3-2 | 設計審查 |

#### 4.40 HUD（U2；推翻 §6 第 105、106 條）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.40.1 | `hudVisible`：appearance ∈ {recording, recordingMuted, recordingAlert, paused} 才可能 true；`always` → true；`auto` → 等於 `obscured`；`never` → false；其他 appearance 一律 false。 | U2；D4-A | `swift:R3MenuBarTests.swift::testHudVisible` |
| 4.40.2 | `feedbackRoute`：(true, _) → `.hud`；(false, true) → `.none`；(false, false) → `.notification`。 | §6 第 120 條 | `swift:R3MenuBarTests.swift::testFeedbackRoute` |
| 4.40.3 | `obscuredAction`：只在 `mode == .auto` 且 `recording` 時動作；(nil, true) → `.showHUD`；(false, true) → `.showHUD`；(true, false) → `.hideHUD`；(true, true)、(false, false)、(nil, false) → `.none`；`always`／`never` 或非錄製中一律 `.none`。圖示被擋住的檢查每 `obscuredCheckSeconds`（5 秒）做一次，不再只做一次。 | §6 第 121 條 | `swift:R3MenuBarTests.swift::testObscuredAction` |
| 4.40.4 | HUD 應為非啟用的 `NSPanel`（`.nonactivatingPanel`）、所有桌面可見、`sharingType = .none`；**外觀＝U2-C 收在螢幕邊緣**（`design-r3/README.md` §3、`design-r3/U2-HUD.dc.html` 的 C 欄），整個 HUD 是**自訂** view、一律深色（`NSAppearance(named: .darkAqua)`，不跟系統淺色）。收合：貼在 `hudPosition`（`right`／`left`）那一側螢幕邊緣的直立標籤 `hudTabWidth`×`hudTabHeight`、內側圓角 `hudTabCornerRadius`、底 `DarkroomColor.surface` 不透明度 0.94、1pt `lineStrong` 外框（貼邊側無框），內容為直徑 `hudTabDot` 的 `recording` 點與直排計時（`hudTabTimer`）；標籤頂端＝所在螢幕 `visibleFrame` 頂端往下 `hudTabTopFraction` × 高度；所在螢幕＝status item 按鈕視窗的 `screen`，取不到用 `NSScreen.main`。展開（滑鼠移入標籤）：同一側長出寬 `hudPanelWidth` 的面板（內距 `hudPanelPadding`、圓角 `hudPanelCornerRadius`、底 `surface` 0.96），依序為狀態字「錄製中」／「已暫停」＋計時（`hudTimer`）、系統與麥克風兩條音量條（`levelFraction(dBFS:)`；靜音時麥克風那行改「已靜音」）、2×2 四顆按鈕「暫停」（暫停中「繼續」）、「靜音」（靜音中「取消靜音」）、「標記」、「停止」（高 `hudButtonHeight`、圓角 `hudButtonCornerRadius`、間距 `hudButtonGap`；停止鈕底 `recording`）；滑鼠離開 `hudCollapseDelaySeconds` 後收合，點標籤可固定展開。四顆按鈕各自走與選單相同的控制路徑（`controlAvailability(`、`stopTargetDecision(`），`canControl` 為 false 時前三顆停用。HUD 不顯示場次名與視窗標題；收尾中與之後不顯示（§4.40.1，不做稿下方的完成卡片）。實作形狀：`Trigger/HUD.swift` 含 `nonactivatingPanel`、`sharingType = .none`、`canJoinAllSpaces`、`setAccessibilityLabel`、`hudPosition`、`hudTabTopFraction`、`levelFraction(`、`darkAqua`，且不得出現 `systemRed`、`場次`。 | U2；intent R3-4 第 8 點；使用者選定 U2＝C | `test_r3_app_static.py::HudStatic.test_panel_shape`、`::test_edge_tab`；設計審查；實機（`sharingType` 對其他 app 的分享是否有效，intent R3-5 第 5 點） |
| 4.40.5 | 快捷鍵回饋應依 `feedbackRoute` 決定：只有 `.notification` 時才發通知（`hotkeyFeedback`，`.passive`）。`controlFeedback` 的文字不變。**補記**（build 收尾補記，`r3-hud`；`MenuBar.swift:738-745`、`:972-997`）：走 `.hud`（以及 `.none`）時不另做提示，只靠下一次 refresh 反映新狀態——暫停與靜音會改變 HUD 的狀態字與按鈕標題，**標記在 HUD 上沒有可見回饋**（HUD 不顯示標記數；選單的「加標記（已有 N 個）」只在打開選單時看得到）。`hudMode` 為 `never` 時 `obscuredAction` 一律 `.none`：圖示被擋住不顯示 HUD、不寫 log，也不發「圖示被擋住」的通知（R2 的一次性通知已由 §6 第 121 條取消）；此時快捷鍵回饋依 `feedbackRoute(false, false)` 照常走 `.notification`。兩者列入 §4.47.12 實機觀察。 | §6 第 120 條 | `test_r3_app_static.py::HudStatic.test_feedback_route_used` |
| 4.40.6 | 設定中的 `hudMode`、`hudPosition` 應存在 `menubar.settings.json`（§3.16）。 | U2、U5 | `swift:R3LockTests.swift::testMenuBarSettingsDefaults` |
| 4.40.7 | **告警加強**（U2-C 容易被忽略的補償）：HUD 顯示中、`newAlertWarnings(previous:current:)` 非空時，(1) 收合標籤的外框改 2pt `attention`，維持到本場結束；(2) HUD 自動展開一次、維持 `hudAlertExpandSeconds`（8 秒），展開區狀態列下方顯示告警膠囊（底 `attention`、字 `onAttention`、`hudAlert`，內容＝該則告警的 message，40 字截斷），8 秒到時滑鼠不在面板內就收合；同一則告警不再自動展開。HUD 不顯示時（auto 且圖示沒被擋住）不強制顯示，告警照 §4.39.3 發通知、選單列換成有告警的膠囊。實作形狀：`HUD.swift` 含 `hudAlertExpandSeconds`、`newAlertWarnings(` 或由 `MenuBar.swift` 傳入新告警、`attention`。 | U2；使用者要求「告警時要加強」 | `test_r3_app_static.py::HudStatic.test_alert_emphasis`；實機（拔麥克風觸發告警，§4.47.4 同場） |
| 4.40.8 | 無障礙：標籤的 `accessibilityLabel`＝「錄製小窗：」接 `menuBarAccessibilityLabel` 去掉「MeetingRecorder：」的部分；四顆按鈕的 `accessibilityLabel` 與 `toolTip` 為「暫停錄製（⌃⌥⌘P）」／「繼續錄製（⌃⌥⌘P）」、「麥克風靜音（⌃⌥⌘M）」／「取消麥克風靜音（⌃⌥⌘M）」、「加標記（⌃⌥⌘B）」、「停止錄製並收尾」；音量條的 `accessibilityValue` 同 §4.41.4。`accessibilityDisplayShouldReduceTransparency` 為 true 時底色不透明度 1.0；`accessibilityDisplayShouldIncreaseContrast` 為 true 時外框改 2pt `text`（告警時仍為 `attention`）；`accessibilityDisplayShouldReduceMotion` 為 true 時展開、收合、自動展開都不做動畫（否則 `hudAnimationSeconds`）。 | U2；brief §2〈VoiceOver／鍵盤〉 | `test_r3_app_static.py::HudStatic.test_accessibility_modes`；設計審查 |

#### 4.41 選單依階段（U6；推翻 §4.20.6 的「灰掉不隱藏」）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.41.1 | `menuStage`：appearance `.idle` → `.idle`；`.preparing`、`.recording`、`.recordingMuted`、`.recordingAlert`、`.paused` → `.recording`；`.finalizing` → `.finalizing`；`.failed` → `.failed`。 | U6 | `swift:R3MenuBarTests.swift::testMenuStage` |
| 4.41.2 | `menuItems(stage:)` 應恰為：`.idle` → [status, start, recordWindow, saveTo, openSession, showLast, preferences, quit]；`.recording` → [status, levels, alert, pauseResume, mute, mark, stop, discard, showHUD, openSession, preferences, quit]；`.finalizing` → [status, cancelFinalize, openSession, preferences, quit]；`.failed` → [status, failureDetail, copyDiagnostics, start, recordWindow, saveTo, openSession, showLast, preferences, quit]。（U6-A 稿新增 `alert` 告警列與 `showHUD`「顯示錄製小窗」。） | U6；ADR `adr-r3-menu-stages.md`；使用者選定 U6＝A | `swift:R3MenuBarTests.swift::testMenuItemsPerStage` |
| 4.41.3 | menu bar 應只顯示 `menuItems(stage:)` 的項目（其他項目隱藏）；階段內的可用性規則沿用 §4.20.6（例：錄製中 `canControl` false 時暫停、靜音、標記灰掉）；`levels` 與 `alert` 是資訊列，各自只在有值時顯示（`alert`＝有告警類 warning）。快捷鍵 ⌃⌥⌘R／P／M／B 與 ⌘,、⌘Q 不變（R2-§4.20.5、D7-A；稿把「停止錄製並收尾」標成 ⌃⌥⌘R，不採用）。**標題字面**（`design-r3/README.md` §4）：「開始錄製（用上次的設定）」建立時字面不變，最近一次載入的視窗清單恰有一個 ★ 時改成「開始錄製：<app 名稱>」；「錄這個視窗」→「錄其他視窗」；「停止錄製」→「停止錄製並收尾」；「偏好設定…」→「設定…」；新增「捨棄這次錄製…」「取消收尾」「錯誤詳情…」「顯示錄製小窗」；其餘（「存到」「暫停錄製」／「繼續錄製」「麥克風靜音」「加標記」「打開場次資料夾」「顯示上一場成品」「複製完整訊息與補救指令」「結束 MeetingRecorder 選單」）不變；「加標記」在 `markers` > 0 時改「加標記（已有 N 個）」。「顯示錄製小窗」：本場強制顯示 HUD（不寫設定；只在 `hudVisible` 的 mode 為 `always` 時會為 true 的外觀，即錄製中、靜音、告警、暫停才有效），HUD 已顯示時灰掉。標題列（`status`）：`attributedTitle` 用 `menuFont` 的 bold、`labelColor`，`image` 為 10pt 圓點（待機 `textDisabled`、錄製與準備中 `recording`、暫停 `attention`、收尾中 `processing`、失敗 `recording` 空心環，環的線寬 1.5pt、向內縮半個線寬；build 收尾補記，`MenuBar.swift:385-389`）。失敗階段的「複製完整訊息與補救指令」（`copyDiagnostics`）依 `menuItems(stage: .failed)` **一律顯示**，不再看 `detailText != statusLine`（§6 第 141 條；build 收尾補記，`MenuBar.swift:274-282`）。告警列：`image` 為 `exclamationmark.triangle.fill`（`paletteColors` `attention`），字為最新告警訊息（`truncatedStatusTitle(…, limit: 40)`，完整放 `toolTip`），字色深色外觀 `attentionText`、淺色 `attentionTextOnLight`。選單本身是系統 `NSMenu`，不做稿上的紅底醒目列。實作形狀：`MenuBar.swift` 呼叫 `menuItems(stage:` 或 `menuGroups(stage:` 並對每個 `MenuItemID` 設 `isHidden`；含上列新字面。 | U6；§6 第 118、134 條 | `test_r3_app_static.py::MenuStagesStatic.test_menu_built_from_stage`、`::test_titles_r3`；`test_r2_static.py::test_trigger_menu_items_r2`（§6 第 118、134 條改預期）；`test_static_rules.py::test_start_item_shows_hotkey`（不改） |
| 4.41.4 | 收音改為即時音量條（**自訂** `LevelMeterView`，`menuMeterWidth`×44）：兩行「系統」「麥克風」（標籤寬 `meterLabelWidth`、`menuMeterLabel`；標籤字色 `labelColor`（跟系統深淺色，與標題列一致）；整條左右內距 `spacing[3]`＝16，標籤從左內距起、條在標籤之後延伸到右內距；build 收尾補記，`LevelMeterView.swift:64-71`），條高 `meterBarHeight`、長度 `levelFraction(dBFS:)`；深色外觀：軌道 `line`、系統 `text`、麥克風 `done`；淺色：軌道 `lineOnLight`、系統 `textOnLight`、麥克風 `doneOnLight`；靜音時麥克風那行改「已靜音」字。每 `levelMeterRefreshSeconds`（0.5 秒）更新；不可聚焦；`accessibilityValue` 讀「系統聲音 有聲／無聲；麥克風 有聲／無聲／已靜音」（判斷沿用 `levelIndicatorLine` 的門檻 -60 dBFS 嚴格大於）。`levelFraction`：nil → 0；-90 → 0；-60 → 0；-30 → 0.5；0 → 1；6 → 1。實作形狀：`Trigger/LevelMeterView.swift` 存在且含 `setAccessibilityValue`、`levelFraction(`。 | U6；intent R3-5 第 9 點 | `test_r3_app_static.py::MenuStagesStatic.test_level_meter_accessibility`；`swift:R3DesignTokenTests.swift::testLevelFraction`；實機（鍵盤導覽與 VoiceOver） |
| 4.41.5 | 失敗詳情小視窗（標準 `NSWindow`，`.titled`、`.closable`，寬 480、不可縮放，跟系統深淺色）：標題「錯誤詳情」；依序顯示 message（`rowTitle`）、補救指令（`monospacedSystemFont` 12pt、可選取）、`record.log` 路徑（中間截斷），以及「複製完整訊息與補救指令」按鈕（複製內容同 §6 第 73 條，即 `MenuBarModel.detailText`）；⌘W 與 Esc 關閉（沿用設定視窗的做法）；不得顯示視窗標題與場次名。稿未畫此畫面，以上依暗房 token 與既有設定視窗的慣例訂。**補記**（build 收尾補記，`r3-menu-stages`；`FailureDetail.swift:19-27`、`:74-97`、`:114-138`）：四周內距 `spacing[4]`＝24，各列間距 `spacing[2]`＝12；log 路徑一行寫「記錄檔：<路徑>」（家目錄縮成 `~`），字用 `caption`＋`secondaryLabelColor`；message 與補救指令在**畫面上**把場次路徑（與其資料夾名）換成「〈場次資料夾〉」，按「複製」時複製的是未替換的完整原文（`detailText`）；沒有可辨識的補救指令（`meeting record …`）時補救指令列隱藏。失敗階段選單的「複製完整訊息與補救指令」一律顯示（§6 第 141 條）。實作形狀：`Trigger/FailureDetail.swift` 存在、含「錯誤詳情」「複製完整訊息與補救指令」、`monospacedSystemFont`、`cancelOperation`。 | U6 | `test_r3_app_static.py::MenuStagesStatic.test_failure_detail` |
| 4.41.6 | 「取消收尾」應對錄製實例送 SIGTERM（經 `stopTargetDecision`），觸發 4.28.6 的取消。 | Q3、R3-D12 | `test_r3_app_static.py::MenuStagesStatic.test_cancel_finalize` |
| 4.41.7 | `menuGroups(stage:)` 應恰為（組與組之間一條分隔線）：`.idle` → [[status], [start, recordWindow, saveTo], [openSession, showLast], [preferences, quit]]；`.recording` → [[status, levels, alert], [pauseResume, mute, mark], [stop, discard], [showHUD, openSession], [preferences, quit]]；`.finalizing` → [[status], [cancelFinalize], [openSession], [preferences, quit]]；`.failed` → [[status], [failureDetail, copyDiagnostics], [start, recordWindow, saveTo], [openSession, showLast], [preferences, quit]]；四個階段的攤平結果都等於 `menuItems(stage:)`。 | U6-A 稿的分隔線位置 | `swift:R3MenuBarTests.swift::testMenuGroups` |

#### 4.42 捨棄這次錄製（F2）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.42.1 | `discardRequestValid`：nil → false；`runId` 不同 → false；`requestedAt` 是 now − 31 秒 → false；now − 5 秒 → true；now + 5 秒（未來）→ false；`requestedAt` 解析失敗 → false。 | F2 | `swift:R3LockTests.swift::testDiscardRequestValid` |
| 4.42.2 | **外觀＝F2-A 確認對話框，錄製照常進行**（`design-r3/README.md` §5）。「捨棄這次錄製…」應先 `NSApp.activate` 再顯示系統 `NSAlert`：`messageText`「捨棄這次錄製？」；`informativeText`「<spokenDuration>。會停止錄製、不收尾、不產生成品；這場的錄音資料夾會移到垃圾桶，可從垃圾桶復原。」；第一顆按鈕「繼續錄製」（預設鍵，Return）；第二顆「捨棄並移到垃圾桶」，`hasDestructiveAction = true`、`keyEquivalent = ""`（Return、Esc 都按不到）；不顯示場次名稱與路徑；圖示用 app 圖示。對話框打開期間錄製照常；按「繼續錄製」沒有任何副作用。使用者按「捨棄並移到垃圾桶」後才寫 `record.discard.json` 並送 SIGTERM。實作形狀：`Trigger/Discard.swift` 含 `NSAlert`、`hasDestructiveAction`、`record.discard.json`、上列四段字面、`spokenDuration`；「繼續錄製」的 `addButton` 出現在「捨棄並移到垃圾桶」之前。 | F2；`CLAUDE.md`〈不可逆節點〉；使用者選定 F2＝A（預設鍵「繼續錄製」） | `test_r3_app_static.py::DiscardStatic.test_confirm_then_request` |
| 4.42.3 | 錄製實例收到 SIGTERM 且 `discardRequestValid` 為 true 時：不得啟動收尾子程序；以 `trashItem(at:resultingItemURL:)` 移動 `<場次>/錄音/`，`<場次>` 只剩 `meeting.json`（與 `.DS_Store`）時再移動 `<場次>`；原始碼不得對場次路徑呼叫 `removeItem(`；成功 → `phase=done`、`code=0`、`discarded=true`；失敗 → `phase=failed`、`code=5`、檔案原地保留。**補記**（build 收尾補記，`r3-discard`；`RecordingSession.swift:289`、`:956-995`、`:1013-1062`）：(1) 捨棄**不** `cancelWriting`：停止擷取後照一般停止的流程把目前段與 prev 收完（`finish`，與不捨棄時相同；只有本來就沒寫進任何 sample 的空段照 §4.36.5 捨棄），所有 writer 到終態後才移到垃圾桶，因為 `cancelWriting` 會刪掉正在寫的段落檔，等於對使用者資料硬刪；(2) 只在 `<場次>` 第一層剩下的項目**包含** `meeting.json` 且是 {`meeting.json`, `.DS_Store`} 的子集時才移動 `<場次>`；`<場次>` 已經是空資料夾（沒有 `meeting.json`）或還有其他檔時留在原地；`<場次>` 移不動只記 log，捨棄仍算成功（`錄音/` 已進垃圾桶）；(3) 只在還沒開始停止時收到的 SIGTERM 才讀 `record.discard.json`（SIGINT 不看）。 | F2；intent R3-4 第 3 點 | `test_r3_app_static.py::DiscardStatic.test_trash_not_delete`；實機（垃圾桶中可「放回原處」） |
| 4.42.4 | `record.discard.json` 無效或不存在時，SIGTERM 照一般停止收尾；開錄時殘留的 `record.discard.json` 會被刪除。 | F2 | `test_r3_app_static.py::DiscardStatic.test_stale_request_ignored` |
| 4.42.5 | `shouldAutoPrep` 對 `discarded=true` 的結果應回 false；`RecordStatus.discarded` 為 nil 時編碼沒有該鍵（`testStatusJSONKeys` 不改）。 | F2；R2-Q10 | `swift:R3LockTests.swift::testDiscardedNoAutoPrep` |
| 4.42.6 | CLI 沒有 `discard` 寫法（§2.4 封閉清單不含）；`meeting record discard` 依 R2 規則當成根目錄 `discard`。 | R3-Q2 | `test_r3_docs.py::test_no_discard_cli` |

#### 4.43 首次引導、設定分頁、app 圖示（U4、U5、U7；推翻 R2-Q3）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.43.1 | `mergedDefaultsJSON`：existing nil → 只有 `harness`、`root` 兩鍵；existing 有 7 鍵＋`syncCompensation`＋不認得的 `x` → 只改 `harness`、`root`，其他鍵與值原樣；existing 不是 JSON 物件 → 丟 `.notObject`。 | U4；ADR | `swift:R3LockTests.swift::testMergedDefaults` |
| 4.43.2 | `record.sh` 的 `write_defaults` 應取 `record.defaults.lock`、讀後合併：事先放 `syncCompensation`、`x` 兩個鍵，開錄寫 defaults 後兩鍵仍在、其他 7 鍵為新值；檔案不是 JSON 物件時不寫、stderr 報錯、開錄照常進行（defaults 只是記憶）。 | R3-Q5；`bin/record.sh:329-341` | `test_r3_lock.py::test_write_defaults_merges`、`::test_write_defaults_refuses_broken_file` |
| 4.43.3 | 兩個寫者同時寫（Python 程序持鎖 2 秒時，另一個合併寫入要等到鎖放開，結果兩邊的鍵都在）。 | ADR | `test_r3_lock.py::test_defaults_lock_serializes` |
| 4.43.4 | `loadMenuBarSettings`：缺檔、壞檔 → 全部預設值（§3.16）；`hudMode: "x"` → `.auto`；`hudPosition: "topRight"` → `"right"`；`saveMenuBarSettings` 後 `load` 等於原值；`menubar.prefs.json` 的讀寫不變（`MenuBarR2Tests.swift:258` 的 6 鍵不改）。 | U5 | `swift:R3LockTests.swift::testMenuBarSettingsDefaults`、`::testMenuBarSettingsRoundTrip` |
| 4.43.5 | `onboardingCompletedAt` 為 nil 時，menu bar 啟動後應顯示首次引導。**外觀＝U4-A 分步精靈 5 步**（`design-r3/README.md` §6.2、`design-r3/U4-Onboarding.dc.html` 的 A）：固定 `onboardingWidth`×`onboardingHeight` 視窗（不可縮放，跟系統深淺色）；上方 5 段步驟條＋標籤「歡迎」「權限」「存檔位置」「選單列空間」「試錄」；步驟依序為歡迎、權限、存檔位置（含 harness）、選單列空間、試錄（含四組快捷鍵說明），每步有「略過」「上一步」（第 1 步停用）「下一步」（最後一步為「完成」）；完成、全部略過或關閉視窗（Esc、⌘W，沿用設定視窗的實體鍵碼判斷）時寫 `onboardingCompletedAt`。權限步標題「先給三個權限」，四列「螢幕錄製」「麥克風」「通知」「自動化（Chrome）」（最後一列標「選用」），每列有狀態字（「已允許」「需要重新開啟」「尚未允許」「被拒，要到系統設定打開」「選用」之一）與按鈕（「已完成」停用／「重新開啟」／「允許」／「打開系統設定」）——狀態不只靠顏色。引導不得自行觸發 TCC 授權框以外的系統設定變更；選單列空間步被擋住時提供「改成一律顯示錄製小窗」（寫 `hudMode = always`）；試錄（§6 第 139 條）不寫進使用者的會議根目錄：場次放在 `FileManager.default.temporaryDirectory` 底下的 `meeting-harness-trial-<runId>/`，錄 5 秒自動停止、跳過收尾，讀狀態檔的 `recentLevels` 顯示兩路是否有聲，之後以 `removeItem` 直接刪除這個暫存目錄（只限這個路徑），不移垃圾桶、不寫 `record.discard.json`、不跳確認框。**跳過收尾的做法**（build 收尾補記，`r3-onboarding-settings`；`Onboarding.swift:8-11`、`:627-646`）：試錄的錄製實例不帶 `--harness`、`--home` 指向試錄暫存目錄（裡面沒有 `record.defaults.json`），所以找不到 `_record_finalize.py`、不收尾就結束；錄製實例因此照 §4.39 發一則標題「會議錄製結束（有錯誤）」的完成通知（`RecordingSession.swift:1139`），引導在清理時以 `removeDeliveredNotifications(withIdentifiers: [completionNotificationID(runId:)])` 收回（§7 疑慮 62）。只有「存檔位置」一步會呼叫 `writeOnboardingDefaults`。步驟條的 `accessibilityLabel` 為「第 N 步，共 5 步：<步驟名>」。**自訂**：步驟條、權限列、主按鈕。實作形狀：`Trigger/Onboarding.swift` 存在、含 `writeOnboardingDefaults(`、上列 5 個步驟名、「先給三個權限」「共 5 步」、`DarkroomMetric.onboardingWidth`、`temporaryDirectory` 與 `meeting-harness-trial-`（其中每個 `removeItem(` 的參數都是試錄路徑變數，§6 第 139 條）；Trigger 原始碼中寫 `record.defaults.json` 的只有這一處。 | U4；R3-D14；使用者選定 U4＝A | `test_r3_app_static.py::OnboardingSettingsStatic.test_onboarding_flow_shape`；`test_r2_static.py::test_defaults_single_writer`（§6 第 123 條改預期）；實機 |
| 4.43.6 | **外觀＝U5-A 7 個工具列分頁**（`design-r3/README.md` §6.3、`design-r3/U5-Settings.dc.html` 的 A）：`SettingsTab` 依序為 `general`「一般」`gearshape`、`recording`「錄製」`record.circle`、`feedback`「回饋與通知」`bell.badge`、`hotkeys`「快捷鍵」`command`、`afterRecording`「錄完之後」`checkmark.circle`、`permissions`「權限」`lock.shield`、`advanced`「進階」`slider.horizontal.3`（`title`、`symbolName` 依此）；`settingsTab("x")` → `.general`。設定視窗用 `NSToolbar` 分頁，寬 `settingsWidth` 固定、高跟內容、不可縮放；**視窗標題跟著分頁變成該分頁的 `title`**（HIG；取代「MeetingRecorder 設定」，§6 第 130 條）；記住上次分頁（`lastSettingsTab`）。各分頁內容照 `design-r3/README.md` §6.3：一般（存檔位置＋「更改…」、登入時自動開啟＋「打開系統設定的登入項目」、harness 唯讀）、錄製（預設會議類型與與會者唯讀、★ 規則說明）、回饋與通知（選單列計時、錄製小窗「自動／一律顯示／不要」、錄製小窗位置「右邊緣／左邊緣」、「用時效性通知（可穿過專注模式）」、會議偵測、通知授權狀態＋「打開通知設定」）、快捷鍵（四組 `r2HotKeys` 的 `display`、不可編輯，D7-A；註冊失敗就地顯示）、錄完之後（停止後自動跑前處理）、權限（`AppPermission` 全部 5 列：§4.43.5 的四項「螢幕錄製」「麥克風」「通知」「自動化（Chrome）」，加第 5 列「提醒事項」（`isOptional` 為 true，說明「只有 meeting reminders 把交辦寫進提醒事項時才需要」）；每列狀態字＋說明＋「打開系統設定」，最後「重新執行首次設定…」；引導的權限步仍只列前四項；build 收尾補記，`Onboarding.swift:25-49`、`:825`，`Preferences.swift:301-313`）、進階（`syncCompensation` 唯讀與「用 meeting sync 修改」、log 位置）。控制項用標準 AppKit，只有視窗底色用 token。實作形狀：`Preferences.swift` 含 `NSToolbar`、`lastSettingsTab`、`settingsTab(`、`SettingsTab`、「自動」「一律顯示」「不要」「右邊緣」「左邊緣」「用時效性通知（可穿過專注模式）」。 | U5；D7；使用者選定 U5＝A | `test_r3_app_static.py::OnboardingSettingsStatic.test_settings_tabs`；`swift:R3DesignTokenTests.swift::testSettingsTabs`；`test_r2_static.py::test_trigger_preferences_window`（§6 第 130 條改預期） |
| 4.43.7 | app 圖示：**外觀＝U7-A 錄製點＋聲波**（`design-r3/README.md` §6.4 的幾何比例；> 32 px 三條聲波、≤ 32 px 兩條）。`Resources/AppIcon.icns` 存在，`iconutil --convert iconset` 展開後恰有 `icon_16x16.png`、`icon_16x16@2x.png`、`icon_32x32.png`、`icon_32x32@2x.png`、`icon_128x128.png`、`icon_128x128@2x.png`、`icon_256x256.png`、`icon_256x256@2x.png`、`icon_512x512.png`、`icon_512x512@2x.png` 10 張；`Info.plist` 的 `CFBundleIconFile` 為 `AppIcon`；`build.sh` 把它複製進 bundle 的 `Contents/Resources/`。entitlements 仍恰為 2 項。深色、tinted 變體不在本輪。 | U7；使用者選定 U7＝A | `test_r3_app_static.py::OnboardingSettingsStatic.test_app_icon_bundled`；設計審查（16、32、128 px 截圖） |
| 4.43.8 | 引導、設定、HUD、確認框、通知的所有字面不得含 `client-names.txt` 的任何名稱（以 `MH_CLIENT_NAMES_FILE` 指定清單；沒有清單時 skip）。 | §4.14 | `test_r3_app_static.py::OnboardingSettingsStatic.test_no_client_names` |
| 4.43.9 | **字型不打包**（`design.md` R3-D22）：`tools/MeetingRecorder/Sources/` 去掉註解後不得出現 `JetBrains`、`Space Grotesk`、`Noto Sans`、`NSFont(name:`；`tools/MeetingRecorder/Resources/` 底下不得有 `.ttf`、`.otf`、`.ttc`；`Info.plist` 不得有 `ATSApplicationFontsPath`。計時一律 `monospacedDigitSystemFont`，指令與路徑用 `monospacedSystemFont`，其餘用 `systemFont(ofSize:weight:)`。 | 設計稿字型的退回規則 | `test_r3_app_static.py::OnboardingSettingsStatic.test_no_bundled_fonts` |

#### 4.44 會議偵測提示（F3；推翻 R2「會議自動偵測在範圍外」）

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.44.1 | `meetingPromptDecision`：`enabled` false → `.none`；`recordLockHeld` true → `.none`；`inputRunning` false → `.none` 且 episode 重設（`prompted`、`dismissed` 回 false）；`inputRunning` true、前景 bundle ID 不在 ★ 清單 → `.none`；在清單、`prompted` false → `.prompt` 且 `prompted` 變 true；同一 episode 第二次 → `.none`；episode 結束（`inputRunning` false）後再開始 → 可再 `.prompt`。 | F3；R3-Q4 | `swift:R3MenuBarTests.swift::testMeetingPromptDecision` |
| 4.44.2 | 偵測只讀 `kAudioDevicePropertyDeviceIsRunningSomewhere`（預設輸入裝置），每 3 秒輪詢；不得開啟麥克風（`Trigger/MeetingDetect.swift` 不得出現 `AVCaptureDevice`、`AVAudioEngine`、`SCStream`）；`record.lock` 以試鎖判斷。 | intent R3-4 第 4 點 | `test_r3_app_static.py::MeetingDetectStatic.test_read_only_detection` |
| 4.44.3 | **外觀＝F3-A 一般通知**（系統原生外觀；`design-r3/README.md` §6.1）：標題「錄這個會議？」；內文「<app 名稱> 正在使用麥克風。要開始錄製嗎？」——app 名稱＝前景 app 的 `localizedName`，取不到用「會議 app」，**只放 app 名稱、不放視窗標題**；兩個動作「開始錄製」（走既有 quick-start，用上次的設定）與「這場不用」（本 episode 不再提示）；`interruptionLevel` 與 `threadIdentifier` 依 §4.39.1（`meetingDetected`）；不得自動開錄。實作形狀：`Trigger/MeetingDetect.swift` 含上列字面（標題、內文的「正在使用麥克風。要開始錄製嗎？」、兩個動作、「會議 app」）與 `localizedName`；該檔不含 `kCGWindowName`、`SCWindow`、`CGWindowListCopyWindowInfo`（取視窗標題的寫法）。 | F3；使用者選定 F3＝A | `test_r3_app_static.py::MeetingDetectStatic.test_prompt_actions`；實機 |
| 4.44.4 | 設定的「回饋與通知」分頁可以關閉偵測（`meetingDetect`；字面「偵測到會議 app 使用麥克風時問我要不要錄」）。 | F3、U5 | `test_r3_app_static.py::MeetingDetectStatic.test_toggle_in_settings` |

#### 4.45 文件與 CLI 表面

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.45.1 | `meeting.sh record help`、`meeting.sh help` 的 record 段、SKILL.md 與 README.md 的 `record-cli` 區塊照 §2.4 維持 12 個寫法（修正輪：`sync` 改為頂層 `meeting sync`，不進封閉清單）；§4.1.2、§4.1.11、§4.12.6–§4.12.8、§4.24.2 的一致性檢查照舊通過。`usage()` 的「其他指令」段（`meeting help` 輸出中「其他指令」行與「錄製（meeting record」行之間）必須各有一行以 `meeting search ` 與 `meeting sync` 開頭；`meeting reminders` 列不列在 `usage()` **不要求**（Red 層補字面）。三者都寫在 SKILL.md、README 的 `record-cli` 區塊外（§4.34.4、§4.45.3）。 | §2.4；§6 第 117 條（撤回） | 既有 `test_cli_dispatch.py`、`test_docs.py`、`test_surface_parsers.py`（不改）；`test_r3_search.py::test_usage_lists_search` |
| 4.45.2 | **撤回**（修正輪）：`EXIT_CODE_CASES` 不新增、不改（§6 第 117 條撤回）。 | — | 既有 `test_record_sh.py::test_exit_code_matrix`（不改） |
| 4.45.3 | SKILL.md（meeting-record）與 README 應說明：開錄鎖與「已有錄製在跑」、`stop` 的 pid 確認、收尾逾時與取消、`tracks/unreadable/`、`meeting sync` 三種模式與預設 off、`meeting search`、`meeting reminders`（含 iCloud 說明）、HUD、捨棄只在選單、會議偵測只提示不自動開錄。meeting-transcribe SKILL.md 說明 VAD 與 `transcript.quality.json`；meeting-notes SKILL.md 說明「## 標記」「## 錄製註記」。 | R3 全部 | `test_r3_docs.py::test_record_skill_r3`、`test_r3_transcript_vad.py::test_transcribe_skill_updated`、`test_r3_annotations.py::test_notes_skill_updated` |

#### 4.46 迴歸與 verify

| 節 | 驗收（EARS） | 依據 | 測試 |
|---|---|---|---|
| 4.46.1 | `bash bin/_lint.sh` 應通過且檔數維持 26（R3 新 Python 檔在 `bin/lib/`，§4.24.5 照舊）；`bin/lib/*.py` 的語法由 §4.32.5 驗；`bash bin/meeting.sh doctor` 全綠。`tests.record.test_regression` 整支自 Red 層起每一層都應綠。 | `CLAUDE.md`〈專案特定〉；§6 第 125 條（撤回） | `test_regression.py::test_lint_passes_26_files`（不改） |
| 4.46.2 | 全量 Python（`python3 -m unittest discover -s tests/record -p 'test_*.py'`，`TMPDIR` 暫存、`LC_ALL=en_US.UTF-8`、`MH_CLIENT_NAMES_FILE` 指向 run 目錄清單）與 Swift（`bash tools/MeetingRecorder/Tests/run.sh`）全綠；`bash tools/MeetingRecorder/build.sh` 在暫存輸出目錄成功。**建置說明**（build 收尾補記，`r3-onboarding-settings`；`build.sh:34-44`）：`Sources/Core/MeetingDetect.swift`（§3.20）與 `Sources/Trigger/MeetingDetect.swift`（§4.44.2）同名，swiftc 不接受同一個 module 有兩個同名檔；`build.sh` 先在 `mktemp -d` 的暫存目錄以「子目錄_檔名」（例 `Core_MeetingDetect.swift`、`Trigger_MeetingDetect.swift`）對 `Sources/` 底下每個 `.swift` 建 symlink，再對這些 symlink 編譯，結束時刪暫存目錄；原始碼位置不變（另一做法見 §7 疑慮 61）。 | §4.13 | integrator |
| 4.46.3 | §4.12.4 照舊：`bin/diarize.sh` 與 `bin/_merge_speakers.py` 與 `main` 完全相同（修正輪：T1 改成 `_render.py` 匯入既有函式＋照抄判準，T5／T6／T7 改成後處理）。 | §6 第 122 條（撤回） | `test_regression.py::test_diarize_and_merge_untouched`（不改） |
| 4.46.4 | R3 新增或修改的檔（含測試、fixture、向量、設計稿）以 `client-names.txt` 掃描都應為「沒有」。 | §4.14；intent R3-4 第 8 點 | `test_r3_docs.py::test_no_client_names_in_r3_files`（`MH_CLIENT_NAMES_FILE`；沒有清單時 skip） |

#### 4.47 R3 實機驗收場（D13-A；使用者在場，test 段）

依序做，結果寫進 run 目錄（只寫 run 代號、不寫會議名）：

| 節 | 項目 | 判準 |
|---|---|---|
| 4.47.1 | E4 聲學回授：內建喇叭與藍牙耳機各錄一段同步測試源，`e2e_check.py --sync-acoustic` | 記下各時段 mic − sys 中位數；寫入 `sync-calibration.json` 的候選值（使用者決定是否採用） |
| 4.47.2 | E2 補償型播放端：同一場次以 off 與 reported 各收尾一次，用 QuickTime／Chrome 播 `--print-sync-file` 的檔，`e2e_check.py --sync-player` | 記錄兩種 mode 的 PASS／FAIL 與中位數；**使用者據此決定 S-C 預設**（§4.37.8） |
| 4.47.3 | HUD 的 `sharingType`：在會議 app 分享整個螢幕時 HUD 是否被分享出去 | 記錄結果；被分享出去時改預設或加說明（選項式提問） |
| 4.47.4 | Time Sensitive：觸發一個告警（例如拔掉麥克風） | 記錄是否以 Time Sensitive 呈現（§7 疑慮 44）；通知標題與內文不含場次名與視窗標題（§4.39.3） |
| 4.47.5 | `.ics` 匯入提醒事項與 `meeting reminders`：權限框、寫入、重跑去重 | 第二次 `created=0`；缺負責人／期限的項目照實留空 |
| 4.47.6 | F3：開一個 ★ 清單的會議 app 並使用麥克風 | 只提示一次、「開始錄製」走 quick-start、「這次不要」後同 episode 不再提示 |
| 4.47.7 | F2：錄 30 秒後捨棄 | 錄音資料夾在垃圾桶、可放回原處、沒有跑收尾 |
| 4.47.8 | 首次引導：刪 `menubar.settings.json` 的 `onboardingCompletedAt` 後重開 | 五步都能走完或略過；`record.defaults.json` 其他鍵保留 |
| 4.47.9 | `keep-segments` 錄一場真實多人會議（使用者決定 3） | 用來調 T4 門檻與雙軌實驗素材；結果只寫數字 |
| 4.47.10 | 全套 e2e 迴歸（含 §4.25.1 劇本與 `--segment-writer --pause-mute`） | 全部 PASS；`SegmentScheduler` 重構後的段落行為與 R2 一致 |
| 4.47.11 | 設計審查（`has_ui=true`）：8 種選單列膠囊（深色與淺色桌布＋半透明選單列各一張、「增加對比」一張、灰階一張）、HUD（收合、展開、暫停、靜音、告警自動展開、「減少透明度」）、選單四階段、失敗詳情、確認框、引導 5 步、設定 7 分頁、app 圖示 16／32／128 px | 照 `design-r3/README.md` 與 HIG；README §7 第 6 點的實際選單列對比在此記錄 |
| 4.47.12 | 快捷鍵回饋的可見性（build 收尾補記，§4.40.5）：(a) HUD 顯示中按 ⌃⌥⌘B 加標記；(b) `hudMode` 設 `never`、讓選單列圖示被瀏海擋住，按 ⌃⌥⌘P／M／B | (a) 記錄使用者是否察覺標記已加（HUD 上沒有可見回饋）；(b) 記錄是否收到快捷鍵回饋通知、`record.log` 沒有「圖示看不到」的行；不足時以選項式提問決定要不要在 HUD 加標記回饋（衍生工作，不編號） |
| 4.47.13 | 首次引導的試錄（build 收尾補記，§4.43.5） | 記錄試錄結束時「會議錄製結束（有錯誤）」通知是否閃一下；有就照 §7 疑慮 62 處理 |

### R3-§5 影響系統（接續 §5、R2-§5）

| 系統／檔 | 變化 | 子任務 |
|---|---|---|
| `bin/record.sh` | 試鎖、stop 四項確認（含 `MH_RECORDER_COMM` 測試旁路）、stop 等待上限對齊收尾期限、preflight 錄製中回 2、`write_defaults` 經 `merge_defaults` 合併 | `r3-lock` |
| `bin/meeting.sh` | `run_diarize` 不刪 raw、`--annotate-speakers` 後處理掛勾；頂層 `sync`、`search`；`reminders` | `r3-vtt-raw`、`r3-search`、`r3-reminders` |
| `bin/transcribe.sh` | 拿掉無效參數；VAD clip；`transcript.segments.json` 一律輸出；品質檔 | `r3-vtt-raw`、`r3-transcript-vad` |
| `bin/_render.py`（`bin/_merge_speakers.py` 不改，只被匯入） | VTT 同一套歸屬（照抄判準＋一致性測試）；`speakers.md` 後處理；標示、標記、聽不清、summary 兩段 | `r3-vtt-raw`、`r3-annotations` |
| `bin/summarize-local.py` | 地端 summary 接上「## 標記」「## 錄製註記」 | `r3-annotations` |
| `bin/_record_finalize.py` | 收尾鎖、mkstemp、逐步逾時、unreadable；S-C 混音 | `r3-finalize-guard`、`r3-sync-compensate` |
| `bin/lib/_record_lib.py`、`bin/lib/_search.py`、`bin/lib/_reminders.py`（新，`bin/lib/` 新目錄） | §3.19（含 `merge_defaults`、`sync` CLI） | `r3-record-lib`、`r3-search`、`r3-reminders` |
| `schema/meeting-record.v1.json` | 選用 `markers[]` | `r3-annotations` |
| `tools/MeetingRecorder/Sources/Core/` | §3.20 全部（含新檔 `DesignTokens.swift`：暗房的色、字、間距 token 與膠囊樣式、對比計算） | `r3-core` |
| `Capture/Commands.swift`、`PreflightRunner.swift` | 先取鎖 | `r3-lock` |
| `Capture/RecordingSession.swift` | 心跳與 S-B → 取消收尾 → 捨棄 → Scheduler 接線 → 提前換段 | `r3-lock`（併入原 `r3-latency-log`）→ `r3-finalize-runner` → `r3-discard` → `r3-segment-scheduler` → `r3-sync-compensate` |
| `Capture/AudioDeviceMonitor.swift` | 延遲讀取 | `r3-lock` |
| `Capture/FinalizeRunner.swift`、`Capture/Reminders.swift`（新） | 收尾執行器；EventKit | `r3-finalize-runner`、`r3-reminders` |
| `Capture/Notifier.swift` | 分級、thread | `r3-menubar-states`（併入原 `r3-notify`）、`r3-onboarding-settings`（併入原 `r3-meeting-detect`） |
| `Trigger/MenuBar.swift` | 外觀、stop 確認與通知 → HUD → 捨棄 → 階段選單 → 引導入口與偵測 | 序列鏈（`plan.md §10`） |
| `Trigger/` 新檔 | `HUD.swift`、`Discard.swift`、`FailureDetail.swift`、`LevelMeterView.swift`、`Onboarding.swift`、`MeetingDetect.swift` | 各 UI 子任務 |
| `specs/meeting-record/design-r3/` | 選定設計稿（`README.md`＋原始稿 `*.dc.html`），UI 子任務與設計審查的依據；不進 app | design 段 |
| `Trigger/Preferences.swift`、`Trigger/Completion.swift` | 分頁；`discarded` 不自動前處理 | `r3-onboarding-settings`、`r3-menubar-states`（併入原 `r3-notify`） |
| `Sources/main.swift`、`Resources/Info.plist`、`Resources/AppIcon.icns`、`build.sh` | `reminders` 子指令；權限說明；圖示 | `r3-reminders`、`r3-onboarding-settings` |
| `tests/record/e2e_check.py` | `--sync-acoustic`、`--sync-player`、`--print-sync-file`；補償資訊 | `r3-sync-measure`、`r3-sync-compensate` |
| SKILL.md（meeting-record／-transcribe／-notes）、README | §4.45.3 | `r3-docs`、`r3-transcript-vad`、`r3-annotations` |
| 測試 | `tests/record/test_r3_*.py`、`vectors/`、`fakes/`（只加不改既有替身的行為）、§6 核准的既有測試修改；`Tests/R3*Tests.swift`（含 `R3DesignTokenTests.swift`）、`Tests/main.swift` 登記、`ControlTests.swift`（§6 第 127 條） | `r3-red-py`、`r3-red-swift` |
| 下游知識庫專案 | 只讀驗相容（§4.31.8），不改 | — |

### R3-§6 整合修訂與例外（續，第 117 條起）

以下每條都是**需要使用者在閘門 2 核准**的修改：「舊預期」是既有 spec／測試的寫法，「新預期」是 R3 的寫法。標「既有測試修改」者，只改列出的斷言，其餘一字不改；commit 內文寫明條號（`.claude/teams/rules.md:37`）。

| # | 舊預期 | 新預期 | 理由 |
|---|---|---|---|
| 117 | **撤回**（修正輪 2026-10-13：`sync` 改為頂層 `meeting sync`，§2.4 的就地修改已還原，下列既有測試都不改；`test_surface_parsers` 回綠）。原文留存：§2.4 封閉清單 12 種寫法、`form_codes` 32 組；`help` 與五個 R2 字為保留字 | ~~§2.4 就地更新（本 R3 唯一的就地修改）：新增 `meeting record sync`（結束碼 `0 2`、沒有寫法旗標），13 種、34 組；`sync` 成為保留字。**既有測試修改**：`surface.py` 的 `SURFACE`（加 `F_SYNC` 與 2 組結束碼）；`test_surface_parsers.py:71-73`（12→13、32→34）與 `VALID_BLOCK`、`VALID_USAGE` 樣本各加一列；`test_cli_dispatch.py:63-65`（緊接 12 行→13 行）、`:77-79`（`h+13`／`h+14`／`h+15` → `h+14`／`h+15`／`h+16`）；`test_docs.py:16`（`SUBCOMMANDS` 加 `sync`）、`:172`（27→29）；`test_record_sh.py` 的 `EXIT_CODE_CASES` 只新增 2 筆（§4.45.2）、`:24` 註解「32 組」改「34 組」。本條 commit 之後到 `r3-red-py` 合併之前，`test_parse_help_accepts_spec_example` 會紅，屬預期~~ | R3-Q6 定案：`syncCompensation` 由 CLI 寫（app 啟動的收尾讀不到 shell 環境變數，`design.md` R3-D9）；撤回理由：頂層寫法不改任何既有測試（`design.md` R3-D30） |
| 118 | §4.20.6「不能用的項目灰掉不隱藏」與固定 18 項順序；`test_r2_static.py::test_trigger_menu_items_r2` 的 `MENU_TITLES` 依序出現 | 依階段顯示（§4.41.2–§4.41.3），不屬目前階段的項目隱藏、階段內暫時不能用的仍灰掉；快捷鍵不變。**既有測試修改**：`MENU_TITLES` 依序斷言改成「每個標題都出現在 `MenuBar.swift`」＋「`menuItems(stage:` 被呼叫」；`assert_key` 的快捷鍵斷言、「繼續錄製」「canControl」不改；`levelLine` 斷言改為 `LevelMeterView`（收音列改音量條）。若設計稿改了標題字面，在稿挑定時另列條號 | 使用者決定 1（D5 取 A）；ADR `adr-r3-menu-stages.md` |
| 119 | §2.2 `record preflight` 的 2＝「app 未建置／`--window` 缺值」；t6 測過「錄製中再跑 preflight」會照跑 13 項 | 2 另含「錄製中」：不跑檢查、不碰狀態檔（R3-§2.2）；既有測試不改（沒有既有測試在持鎖下跑 preflight） | D14b-A |
| 120 | §6 第 105 條：快捷鍵回饋一律走通知（`test_t7_fixes.py::test_hotkey_feedback_notification`） | 依 `feedbackRoute`：HUD 看得到走 HUD、圖示看得到不發、兩者都看不到才發通知（§4.40.2、§4.40.5）。**既有測試修改**：該測試的「每次都呼叫通知」斷言改成「通知呼叫在 `feedbackRoute(` 為 `.notification` 的分支內」；`controlFeedback` 文字的斷言不改 | intent R3-3 第 4 點；U2 |
| 121 | §6 第 106 條：圖示被擋住只檢查一次、只發一次通知（`test_t7_fixes.py::test_status_item_obscured_check`） | 每 5 秒持續檢查，結果驅動 auto 模式 HUD 與回饋路徑；狀態改變才動作（§4.40.3）。**既有測試修改**：「只檢查一次」的斷言改為「以 `obscuredCheckSeconds` 計時重複檢查、呼叫 `obscuredAction(`」；`statusItemObscured` 的純函式測試不改 | intent R3-3 第 4 點；U2 |
| 122 | **撤回**（修正輪 2026-10-13）。原文留存：§4.12.4：`bin/diarize.sh` 與 `bin/_merge_speakers.py` 與 `main` 完全相同（`test_regression.py::test_diarize_and_merge_untouched`） | ~~只約束 `bin/diarize.sh`；`_merge_speakers.py` 允許 §4.46.3 列的改動~~。改為：`_merge_speakers.py` 不改，`_render.py` 匯入既有函式＋照抄判準（§4.29.2、§4.29.5），衍生檔標示改後處理（§4.31.10）；`test_regression.py` 不改 | 撤回理由：有不改既有測試的替代寫法（`design.md` R3-D30） |
| 123 | R2-Q3「`record.defaults.json` 維持 `record.sh` 單一寫者」；`test_r2_static.py::test_defaults_single_writer`（Swift 任何一行都不得寫 defaults 檔） | 兩個寫者、共用 `record.defaults.lock`、讀後合併（§3.15、§3.16）；app 只在首次引導寫兩鍵。**既有測試修改**：該測試改成「寫 `record.defaults.json` 的 Swift 只有 `Core/Settings.swift` 的 `writeOnboardingDefaults` 一處，且呼叫端只有 `Trigger/Onboarding.swift`」 | 使用者決定 1（D6 取 A）；ADR `adr-r3-defaults-writers.md` |
| 124 | §4.9.3 的 sync 判準：每個閃白與嗶聲的差都 < 100 ms（ffplay） | ffplay 的 `--sync` 保留為「錄製器沒有引入額外偏移」的迴歸；新增 `--sync-player`（補償型播放端、按 60 秒時段取中位數、\|d\| < 45 ms）為 R3 起的影音一致判準（§4.35.2）。既有測試不改（`test_hfp_and_sync_check` 照舊） | D3-A；`sync` §0 |
| 125 | **撤回**（修正輪 2026-10-13）。原文留存：`test_regression.py::test_lint_passes_26_files`：`_lint.sh` 檢查 26 個檔 | ~~29 個檔~~。改為：新 Python 檔放 `bin/lib/`，檔數維持 26、測試不改；語法由 §4.32.5 驗 | 撤回理由：有不改既有測試的替代寫法（`design.md` R3-D30） |
| 126 | §6 第 111 條：收尾成功後刪段落（含讀不到的） | 讀不到的段落搬到 `tracks/unreadable/`、記 `movedTo`；已併入成品的照刪（§4.28.7）。既有 `test_finalize.py` 不改（`test_segments_removed_after_success` 只看 `tracks/seg-*.mov`，不遞迴） | D12-A |
| 127 | `ControlTests.swift::testPauseGateAndSwitchReason`：`SwitchReason` 恰為五個 | 恰為六個（加 `.outputDeviceChange`，放在最後）。**既有測試修改**：`expectedReasons` 加一項、訊息「恰為五個」改「恰為六個」 | S-C「輸出裝置變更提前換段」；R3-Q1＝A |
| 128 | §3.4.1／§4.11.5、§4.20.4 的圖示外觀（`symbolName` 四態、錄製中與告警加系統紅色） | 外觀改由 `MenuBarAppearance` 8 種決定（§4.38）；`MenuBarState`、`symbolName` 的值保留供相容與既有測試。§4.20.4 的計時、等寬數字、`mic.slash`、variableLength 不變 | U1；intent R3-3 第 7 點 |
| 129 | `test_r2_static.py::test_trigger_status_item_variable_length` 要求 `symbolName`、`paletteColors`、`systemRed`、`mic.slash`、不得有 `contentTintColor`；`test_static_rules.py::test_menubar_uses_template_image` 要求三個 symbol 與 `isTemplate = true` | 選單列改成 U1-C 錄製膠囊（§4.38.3、§4.38.5）：顏色只來自 `DarkroomColor`，`MenuBar.swift` 不得再出現 `systemRed`。**既有測試修改**（只改 `test_r2_static.py:191` 那一行的 tuple）：`test_trigger_status_item_variable_length` 要求的字串 `"systemRed"` 換成 `"menuBarCapsuleStyle("`；`monospacedDigitSystemFont`、`"mic.slash"`（靜音分段膠囊左段）、`paletteColors`、`symbolName`（待機的 `record.circle`）、`timerText`、`variableLength`、不得有 `squareLength`、不得有 `contentTintColor` 都不改。`test_static_rules.py::test_menubar_uses_template_image` **不改**：三個 symbol 名仍在 `Core/Trigger.swift` 的 `symbolName`（`MenuBarState` 保留，§6 第 128 條），待機仍是 template（`isTemplate = true`） | 使用者選定 U1＝C；R3-Q8＝B；`design.md` R3-D21 |
| 130 | `test_static_rules.py::test_start_item_shows_hotkey`（`START_ITEM_TITLE`＝「開始錄製（用上次的設定）」）、`test_r2_static.py::test_trigger_preferences_window`（「MeetingRecorder 設定」等字串） | `test_start_item_shows_hotkey` **不改**：開始錄製項建立時的字面仍是「開始錄製（用上次的設定）」、⌃⌥⌘R 不變；只在快取的視窗清單恰有一個 ★ 時於執行期改標題為「開始錄製：<app 名稱>」（§4.41.3）。設定視窗改成 7 個工具列分頁、**視窗標題跟著分頁變**（§4.43.6），不再固定「MeetingRecorder 設定」。**既有測試修改**（只改 `test_r2_static.py:275` 那一行的 tuple）：`test_trigger_preferences_window` 要求的字串 `"MeetingRecorder 設定"` 換成 `"settingsTab("`；其餘 10 個字串（「預設存檔位置」「更改…」「登入時自動開啟」「停止後自動跑前處理」「打開系統設定的登入項目」`openSystemSettingsLoginItems`、`loginItemDisplay(`、`r2HotKeys`、「註冊失敗」、`autoPrep`）與「不得有 `.resizable`」不改 | 使用者選定 U5＝A、U6＝A；HIG settings「Update the window's title to reflect the currently visible pane」 |
| 131 | intent R2「明確在範圍外」的「會議自動偵測」「捨棄這次錄製」（`intent.md:295`） | 改做 F3（只提示）與 F2（移到垃圾桶）；行事曆提醒仍在範圍外 | 使用者決定 1 |
| 132 | `_record_finalize.py` 的結束碼 5 只表示「收尾失敗」 | 另含「該場次正在收尾（收尾鎖被持有）」與「步驟逾時」（R3-§2.2；`finish` 的寫法結束碼仍是 `0 2 3 5`，數字集合不變） | Q4、Q3 |
| 133 | `RecordMeta`、`RecordStatus` 的鍵集合（`RecordsTests.swift:58`、`:112-113`） | 新增 `outputLatencies`、`discarded` 兩個頂層 Optional，nil 省略鍵；`RecordsTests` 不改（R2 第 79 條先例）。心跳不加鍵 | S-B、F2；intent R3-3 第 8 點 |
| 134 | §4.20.6 的選單字面「錄這個視窗」「停止錄製」「偏好設定…」；`test_r2_static.py::test_trigger_menu_items_r2` 的 `MENU_TITLES`（`:26-27`）與 `assert_key(self, src, "偏好設定…", ",", {".command"})`（`:214`） | U6-A 稿的字面（§4.41.3）：「錄其他視窗」「停止錄製並收尾」「設定…」（設計審查 R2 N-4）；新增「捨棄這次錄製…」「取消收尾」「錯誤詳情…」「顯示錄製小窗」；其餘字面不變（含「結束 MeetingRecorder 選單」「顯示上一場成品」）。**既有測試修改**（接在第 118 條之後，同一個 commit）：`MENU_TITLES` 的「錄這個視窗」→「錄其他視窗」、「停止錄製」→「停止錄製並收尾」、「偏好設定…」→「設定…」，其他 9 項不改；`:214` 的「偏好設定…」→「設定…」（`,`、`{".command"}` 不改）。`test_r2_docs.py` **不改**：`r3-docs` 寫 SKILL.md 時新名稱與 R2 舊稱並列（例「錄其他視窗（R2 稱「錄這個視窗」）」「設定…（R2 稱「偏好設定…」）」），`R2_MENUBAR` 仍找得到 | 使用者選定 U6＝A；ADR `adr-r3-menu-stages.md` |
| 135 | §4.11.8、§3.4.1：status item 的 `accessibilityLabel` 與 `toolTip`＝`MenuBarModel.accessibilityText` | 改用 `menuBarAccessibilityLabel(…)`（§4.38.7；計時讀成「已錄 12 分 34 秒」、有告警時帶告警內容；錄製中**不再含場次名**，因為 toolTip 會出現在螢幕上、使用者可能正在分享整個螢幕）；`MenuBarModel.accessibilityText` 保留供相容，`TriggerTests` 不改；`test_static_rules.py::test_menubar_sets_accessibility_label` 不改（只要求 `toolTip` 與 `setAccessibilityLabel` 存在） | U1；無障礙 |
| 136 | 測試替身 `fakes/fake_recorder.sh` 不持有任何鎖、程序名是 `bash`；`_helpers.Sandbox.env` 不帶 `MH_RECORDER_COMM`；`record.sh stop` 只看 `record.pid` 活著就送訊號 | **閘門 2 使用者已核准（2026-10-13）**。Q5 的四項確認上線後，既有 stop／status 測試的替身會被判「沒有鎖」「不是錄製器」而回 3。改法（斷言一字不改）：(1) `record.sh` 第 (4) 項的比對字串可由 `MH_RECORDER_COMM` 覆寫，**只在 `MH_RECORD_OPEN` 也有設時採用**（與 `MH_RECORD_OPEN` 同類的測試旁路，§3.19、§4.27.2）；(2) `fake_recorder.sh` 加 `FAKE_LOCK`（預設 `1`）：在寫 `record.status.json` 與 `record.pid` **之前**由背景 `python3` 子程序以 `fcntl.flock` 持有 `<home>/record.lock`，子程序每 0.2 秒看父程序是否還在、父程序結束（含 SIGKILL）就退出放鎖；`on_term` 與正常結束時先結束該子程序；`FAKE_LOCK=0` 時不持鎖；(3) `_helpers.Sandbox.env` 的預設環境加一鍵 `MH_RECORDER_COMM=bash`。(2)(3) 屬替身與 helper 的**新增**行為，其餘行不改；`test_record_sh.py:43`（`stop` 0）、`:104`、`:178`、`:185`，`test_r2_cli.py:244` 等既有斷言不改 | 修正輪 A；`tests/record/fakes/fake_recorder.sh:111`；`spec.md` §4.27.2、§4.27.6 |
| 137 | `test_r2_static.py::test_capture_pause_gate_before_maxend`（`:128-133`：`RecordingSession.swift` 的 `ingest` 本體裡 `pauseRoute(` 在 `maxEnd =` 之前）、`::test_capture_uses_core_pause_functions`（`:135-144`：13 個 Core 名稱都要出現在 `RecordingSession.swift`）；`test_static_rules.py::test_segment_writer_uses_assetwriter`（`:321-332`：`SEGMENT_WRITER_REQUIRED` 含 `routeSample(`，只在 `Capture/` 找） | **閘門 2 使用者已核准（2026-10-13）**。`SegmentScheduler` 接手開段與暫停閘門後，這些名稱移到 `Core/SegmentScheduler.swift`（§4.36.10、§4.36.11）。**既有測試修改**：(1) `test_capture_pause_gate_before_maxend` 讀的檔由 `RECORDING_SESSION` 改為 `SOURCES / "Core" / "SegmentScheduler.swift"`（函式名 `ingest`、`maxEnd =`、`pauseRoute(` 的斷言不改）；(2) `test_capture_uses_core_pause_functions` 的名稱清單拆兩份：`pausing(`、`resuming(`、`pauseRoute(`、`segmentOpened(`、`openReason(` 改在 `SegmentScheduler.swift` 找，其餘 8 個仍在 `RecordingSession.swift` 找；`enum SwitchReason` 的逐行檢查不改；(3) `test_segment_writer_uses_assetwriter` 中 `routeSample(` 一項改在 `Capture/`（不含 Probe.swift）加 `Core/SegmentScheduler.swift` 的合併原始碼裡找，其他 11 項與「不得出現」的檢查不改。三支函式名不改 | 修正輪 B；R3-Q1＝A；`design.md` R3-D10 |
| 138 | §4.2.8：entitlements 恰為 `{audio-input, automation.apple-events}` 兩項（`test_static_rules.py::test_entitlements_audio_and_apple_events`）；§4.39.3、§4.43.7、plan §10 的「entitlements 恰為兩項」 | **條件式，閘門 2 使用者選 (b)，本條生效（2026-10-13）**。選 (a) 不加：本條不生效。選 (b) 加：entitlements 恰為三項（加 `com.apple.security.personal-information.calendars`，值 true）；**既有測試修改**：`test_entitlements_audio_and_apple_events` 的預期鍵集合加這一鍵（函式名不改）；§4.2.8、§4.39.3、§4.43.7 與 plan §10、`r3-subtasks` 的「恰為兩項」一律讀作「恰為三項」；`Resources/MeetingRecorder.entitlements` 歸 `r3-reminders` | 修正輪 D；F5 EventKit 在 hardened runtime 下的資源存取 |
| 139 | §4.43.5、`design.md` R3-D14：首次引導的試錄「錄 5 秒後走 F2 的捨棄路徑（移到垃圾桶）」 | **閘門 2 使用者已核准（2026-10-13）**。試錄不寫進使用者的會議根目錄：場次放在 `FileManager.default.temporaryDirectory` 底下的 `meeting-harness-trial-<runId>/`，錄 5 秒自動停止、**跳過收尾**，讀狀態檔的 `recentLevels` 顯示兩路是否有聲，之後以 `removeItem` 直接刪除這個暫存目錄（只限這個路徑），不移垃圾桶、不寫 `record.discard.json`、不跳確認框。實作形狀：`Trigger/Onboarding.swift` 含 `temporaryDirectory` 與 `meeting-harness-trial-`，其中每個 `removeItem(` 的參數都是這個試錄路徑變數；§4.42.3「不得對場次路徑呼叫 `removeItem(`」與 `r3-discard` 的檢查不受影響（試錄目錄不是使用者的場次） | 修正輪 I。理由：試錄是引導為了驗權限而產生的暫存，不是使用者要留的會議資料，也不在使用者的根目錄；每次引導都往垃圾桶丟一個資料夾只增加雜訊；加確認框對使用者沒有保護作用、只多一步。`CLAUDE.md`〈不可逆節點〉的「刪資料」指使用者資料，本條把刪除範圍限在本程序剛建立的暫存目錄 |
| 140 | `tests/record/test_concurrency.py::test_finalizing_session_not_listed`：`record finish` 的程序還活著（`p.poll() is None`）時，`錄音/` 第一層出現音檔或 `meeting status` 列出場次，一律算違規 | 只有在「尚未發佈」時才算違規：`錄音/tracks/finalize.json` 沒有 `finishedAt`，或其 `outputs.audio` 的檔名不是看到的那一個音檔。產品的發佈順序（§4.6.5：先寫 `finalize.json`、最後才把 wav 原子 rename 進 `錄音/`，之後清暫存、記狀態、刪段落）不變；原判斷把「發佈完成後、程序結束前」的空窗誤判為違規 | 使用者 2026-10-13 核准（R3 build 第 3 層整合時，10 輪重現 2 次；探針確認誤報當下 `finalize.json` 已有 `finishedAt`、`outputs.audio` 相符、`.finalize/` 已清除）。只改這支測試的判斷條件，`polls ≥ 3` 與其他斷言不變 |
| 141 | §6 第 73 條：選單在狀態列之後多一項「複製完整訊息與補救指令」，**只在 `detailText != statusLine` 時顯示** | 失敗階段（`menuStage == .failed`）一律顯示「複製完整訊息與補救指令」（`copyDiagnostics`，§4.41.2、§4.41.3），不再看 `detailText != statusLine`；其他階段隱藏。複製內容仍是 `detailText`（§6 第 73 條的其餘規定與 §4.11.8 的 toolTip 不變）；錯誤詳情視窗的按鈕同此（§4.41.5）。既有測試不改 | r3-menu-stages 實作、主 session 認可，閘門 3 追認（build 收尾補記，2026-10-13；`MenuBar.swift:274-282`、`:338`）。理由：§4.41.2 定案的 `.failed` 項目清單已含 `copyDiagnostics`，選單依階段顯示後再疊一層內容比對只會讓同一階段的選單時有時無 |

### R3-§7 疑慮（續，第 43 條起）

43. **試鎖與 app 取鎖之間的空窗**：兩個 `record.sh` 幾乎同時開錄時都會過試鎖，由 app 的鎖決定勝負；落敗的 `record.sh` 等不到本次 `runId` 的狀態，照 §4.1.6 回 4（訊息是「沒有狀態」而不是「已有錄製在跑」）。要完全消除得讓 `record.sh` 持鎖並交給 app，但 `open` 啟動的 app 不能繼承 fd；本輪接受這個退化（§4.26.7 只保證不會有兩個實例在錄）。
44. **Time Sensitive 需要 entitlement**：`UNUserNotificationCenter.h:31` 註明要 time-sensitive entitlement；§4.2.8 規定 entitlements 恰為 2 項，自簽下加 entitlement 可能讓 app 無法啟動。本輪只設 `interruptionLevel`，系統不給時退回一般通知；實機驗收場確認（§4.47.4）。若沒有效果，選項：(a) 接受，告警靠 HUD；(b) 加 entitlement 並改 §4.2.8（要使用者核准、實機驗啟動）。
45. **提醒事項權限的 Info.plist 鍵名未一手確認**（2026-10-13 已解決）：本機 SDK 標頭只有 `requestFullAccessToRemindersWithCompletion:`，沒有 plist 鍵名；`NSRemindersFullAccessUsageDescription` 來自調研的二手資料。`r3-reminders` 開工前要查 Apple 文件確認，若不同就改用正確鍵名並在本條記錄。
   **解決（2026-10-13，第 3 層合併後）**：鍵名依 Apple 官方文件為 `NSRemindersFullAccessUsageDescription`（macOS 14 起 `requestFullAccessToRemindersWithCompletion:` 讀這個鍵），`Info.plist` 同時保留舊鍵 `NSRemindersUsageDescription`（`r3-reminders`）。本機 SDK 標頭（`EventKit.framework` 在內的整個 `Frameworks/`）沒有這個字串，所以只能以 Apple 文件為準；權限框實際是否出現，由實機驗收場 §4.47.5 確認。
46. **`sync`、`search`、`reminders` 成為 `meeting` 頂層保留字**（`sync` 為修正輪新增）：名為 `sync`／`search`／`reminders` 的根目錄要寫 `./search` 這類寫法；`meeting <根>` 的預設分支（`bin/meeting.sh:468`）原本會把它們當根目錄。SKILL.md 與 README 要寫明。
47. **S-C 的方向與大小未實測**：`reported` 依 Core Audio 回報值，A2DP 與 HFP 的實測與回報方向可能相反（intent R3-5 第 1 點）；預設 off，實機驗收場 E2／E4 之後才決定（§4.37.8）。
48. **`SegmentScheduler` 重構的回歸面**：熱路徑改動只有 Core 行為測試＋實機 e2e 保護；`RecordingSession` 的 AVFoundation 呼叫本身沒有自動測試。實機驗收場的全套 e2e（§4.47.10）是唯一的端到端證據。
49. **UI 外觀等稿**（2026-10-13 已解除）：使用者已選定設計稿，存在 `design-r3/`；外觀條文與 §6 第 129、130、134、135 條已補完。UI 子任務的外觀部分改以這些條文為準，不再等稿。
50. **VAD 預設門檻只是起點**：-60 dBFS／0.75 秒／2.0 秒來自 0141 單場實驗（`tr` §2.2）；真實多人會議（遠端聲音小、背景噪音）可能切掉輕聲。實機驗收場用 `keep-segments` 的場次調，`MH_VAD=0` 可以隨時退回。
51. **F2 只移動 `錄音/`**：場次資料夾若還有使用者自己放的檔，只有 `錄音/` 會進垃圾桶，`<場次>` 與其他檔留著；這是刻意的保守做法（不可逆節點只碰本次錄製產生的東西）。
52. **選單列膠囊的白字對比**（閘門 2 使用者決定（2026-10-13）：採 (a)）（`design-r3/README.md` §7 第 1 點）：稿的白字對錄製紅 `#FF4D4F` 是 3.27:1、對處理紫 `#8B7CF6` 3.33:1，13pt 不到 WCAG 一般文字的 4.5:1。本 spec 採 (a)：字放大到 14pt bold（WCAG 大字門檻 3:1），淺色選單列與「增加對比」換深一階的底色（§4.38.5）；代價是膠囊每字寬約多 1pt、字比稿重。其他選項：(b) 深色列也改深一階底 `#CC2F32`／`#6D5BD0`（白字 5.22／5.18），選單列上的紅變暗、和稿的「唯一發光的紅點」語氣不同；(c) 保留底色、字改深色 `#1A0B0C`（5.86），膠囊看起來像警示標籤。要改選項時只改 §4.38.5 的表與 `DesignTokens.swift`，不影響其他子任務。
53. **F2 用系統 `NSAlert`，不做稿 A 的深色卡片**（閘門 2 使用者決定（2026-10-13）：照此）：系統 alert 免費帶來置中、模態、Esc／⌘.、VoiceOver 朗讀順序與 accessory app 的前景處理；稿的卡片要另做自訂 `NSPanel` 並自己處理這些。若使用者要稿上的深色卡片，改 §4.42.2 與 `r3-discard` 的擁有檔（新增自訂面板），代價是多一個要自行處理鍵盤與 VoiceOver 的自訂視窗。
54. **字型不打包**（閘門 2 使用者決定（2026-10-13）：不打包；原標題「字型不打包是預設、要不要打包待使用者決定」）（`design.md` R3-D22）：稿用 Noto Sans TC、Space Grotesk、JetBrains Mono；三者公開發行的授權都是 SIL Open Font License 1.1（可隨 app 散布，要附授權全文；打包前要再從各專案的發行頁確認版本與授權，本輪未查證）。打包的代價：app 變大（Noto Sans TC 的中文字集遠大於另外兩套，實際大小未量）、`build.sh` 要複製字型並在 `Info.plist` 加 `ATSApplicationFontsPath`、§4.43.9 要改、中文字的渲染與系統的 PingFang TC 不同。
55. **選單列的實際底色量不到**：macOS 26 的選單列是半透明，膠囊的對比（§4.38.6）以稿上的選單列色 `#1E2129`／`#E9E7E2` 計算；實際桌布不同時對比會變，由實機設計審查（§4.47.11）在深色與淺色桌布各截一張確認，不夠就改 §4.38.5 的色。
56. **稿上沒採用的部分**：選單的紅底醒目列（`NSMenu` 要每列換自訂 view，會失去系統的鍵盤導覽與高亮）、「停止錄製並收尾 ⌃⌥⌘R」（⌃⌥⌘R 只做開始，D7-A）、「上一場：10/13 14:05・42 分鐘」（要新的上一場資料來源，衍生工作）、HUD 完成卡片（§4.40.1 規定收尾後不顯示）、HUD 收合時的音量條（稿 C 沒畫，依稿不放）、錄製中選單沒有「結束」（依 ADR 保留）。
57. **F5 在 hardened runtime 下可能需要行事曆 entitlement**（修正輪 D，**閘門 2 使用者決定（2026-10-13）：(b) 現在加，entitlements 恰為三項，§6 第 138 條生效**）：固定身分簽章帶 `--options runtime`（`tools/MeetingRecorder/build.sh:49`），Apple〈Hardened Runtime〉的 Resource Access 列有 `com.apple.security.personal-information.calendars`；EventKit 的提醒事項是否也落在這一項、沒有它時 `requestFullAccessToRemindersWithCompletion:` 會不會直接回拒絕，本機 SDK 標頭查不到，未一手確認。現況 entitlements 恰兩項（§4.2.8，`Resources/MeetingRecorder.entitlements`）。選項：(a) 不加，`r3-reminders` 照現況做，若實機（§4.47.5）權限框不出現或直接拒絕，再回頭走 (b)——代價：F5 可能在實機才發現不能用，要多一輪修改與重簽；(b) 現在就加（§6 第 138 條）——代價：改一支既有測試、entitlements 變三項，加的若其實不需要就是多要一項權限；這一項屬 hardened runtime 的資源存取類（與已在用的 `audio-input` 同類），不是需要描述檔的受限 entitlement，自簽下不影響啟動的風險低於疑慮 44 的 Time Sensitive。建議 (b)。
58. **S-C 連續延後在暫停邊界的行為**（修正輪 C）：延後以「串接後（不含暫停）」的時間軸為準，L 不變時暫停前最後 L 秒的系統聲音會落到繼續後的開頭（最多 0.5 秒）。這是把延後做成連續的必然結果；若實機（§4.47.2）判讀這段聽起來不對，選項是在暫停邊界把 L 視為由 L 變 0 再變 L（多一段靜音、截掉暫停前的尾），列為之後的調整。
59. **`MH_RECORDER_COMM` 是安全檢查的旁路**（修正輪 A）：只在 `MH_RECORD_OPEN` 也有設時生效，而 `MH_RECORD_OPEN` 本身就會把 app 換成替身，正式使用不會設；README 與 SKILL.md 不列這兩個變數（同 `MH_RECORD_OPEN` 現況）。
60. **S-C 開啟時，標記與 VAD 換到成品時間沒有加 `L_out`**（build 收尾補記，2026-10-13）：`bin/lib/_record_lib.py` 的 `output_time(t, first_start, pauses, l_out=0.0)` 已預留 `l_out`（`:137-150`），但目前沒有任何呼叫端傳入（`bin/_render.py:407`、`_record_lib.py:268`、`:273` 都用預設 0）；補償開啟時系統聲音在成品裡晚了 `L_out`，標記與 VAD 區間仍照未補償的時間軸換算，最多早 0.5 秒（`L_out` 上限，§4.37.5）。預設 `off` 不受影響。要不要開補償在實機驗收場（§4.47.2）決定時一併處理：選項 (a) 呼叫端依 `finalize.json.syncCompensation.segments` 傳入該時段的 `delaySeconds`——代價：`_render.py` 與 `clip` 都要讀 `finalize.json`、多一組向量測試；(b) 維持現狀並在 SKILL.md 註明——代價：開補償時標記最多早 0.5 秒。衍生工作（不編號）。
61. **兩支同名 `MeetingDetect.swift` 的建置做法**（build 收尾補記，2026-10-13）：目前 `build.sh` 以暫存目錄的「子目錄_檔名」symlink 編譯（§4.46.2）。另一做法是把 `Trigger/MeetingDetect.swift` 改名（例 `MeetingDetectPrompt.swift`），`build.sh` 回到直接編譯；代價：`test_r3_app_static.py::MeetingDetectStatic` 與 §4.44.2、§4.44.3 寫死的路徑要改，屬既有測試修改，需要使用者核准。留到閘門 3 決定；不改時現狀可用（全量建置與 Swift 測試已綠）。`Tests/run.sh` 只編 `Core/`，不受影響。
62. **試錄的完成通知可能閃一下**（build 收尾補記，2026-10-13）：試錄靠「不帶 `--harness`」跳過收尾（§4.43.5），錄製實例會發一則「會議錄製結束（有錯誤）」通知，引導事後用 `removeDeliveredNotifications` 收回；收回前通知可能已短暫出現。實機（§4.47.13）若看到通知閃一下，做法是在 Capture 加 `--skip-finalize` 旗標（錄製實例明確跳過收尾、不發完成通知），引導改帶這個旗標；代價：Capture 多一個內部旗標，`main.swift` 的說明與 `test_r3_app_static.py::OnboardingSettingsStatic` 要對應補。
63. **多音檔場次串接後 levels 的時間軸可能錯位**（build 收尾補記，2026-10-13）：`錄音/` 有多個音檔時，`bin/_combine_audio.py` 依檔名排序串成 `錄音/.combined.wav` 再轉錄；`transcribe.sh` 以音檔所在目錄（`錄音/`）跑 `_record_lib.py clip`，用的是錄製器那一場的 `manifest.json.levels`（`bin/transcribe.sh:63-69`）。串接的其他音檔排在錄製器成品之前或之後時，levels 的時間軸與 `.combined.wav` 對不上，clip 可能切掉有聲段或送進靜音段。留給實機驗收場確認；必要時 `MH_VAD=0` 可退回整檔。選項：(a) 多音檔時一律不套 VAD（VAD 行寫「未套用（多音檔）」，要擴 §3.18 的原因清單）；(b) 依串接順序把 levels 位移到對應的時間段。衍生工作（不編號）。

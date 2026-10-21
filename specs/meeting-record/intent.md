# intent：meeting-record（把會議紀錄的起點從「已錄好的檔案」推到「開始錄」）

- epic：`meeting-record`
- 階段範圍：需求正本的**第 1 階段（錄製器本體，requirement.md:251-252）與第 2 階段（觸發層，requirement.md:254-255）**
- 需求正本（使用者已核准，逐字為準）：`_tpm/runs/20261010-sdlc-meeting-record/requirement.md`（300 行，本機、不在版控；`.gitignore:36` 的 `/_tpm/runs/*`）
- 閘門 1 前的使用者決定：`_tpm/runs/20261010-sdlc-meeting-record/gate1-decisions.md` 的 D1–D4（本檔以下稱 D1–D4；只是本檔內引用，不是任務編號）
- 已完成的實測：`tools/MeetingRecorder/PROBE-REPORT.md`（版控正本）
- 調研依據：同 run 目錄的 `research-requirement.md`、`research-specs-adr.md`、`research-code-contracts.md`、`research-upstream.md`
- 本檔是本 repo 的第一份 spec 文件；`specs/_templates/intent.md` 不存在（`research-specs-adr.md:31`），故用 workflow 的 fallback 五節格式。
- 行號引用一律以本檔修訂當下的檔案內容為準，可用 `sed -n '<行>p' <檔>` 重跑核對。

---

## 1. 問題

會議紀錄管線目前的起點是「`錄音/` 裡已經有一個檔」（場次定義：`bin/meeting.sh:193-204`；正本轉述見 requirement.md:66）。錄製本身仍是手工活，有兩個會造成**不可補救損失**的失敗模式（requirement.md:5-8）：

1. **漏錄**。預設輸入是「聚集裝置」、預設輸出是「多重輸出裝置」，成員寫死；換一次藍牙耳機或改用內建喇叭就得重配，漏配就沒錄到音，而且**會議結束才發現**（requirement.md:7、39-40）。更根本的是沒有公開 API 可查詢錄音權限，未授權的失敗模式是**靜默錄到全靜音**（requirement.md:110；同義重述於 :198）；授權後還必須重啟 app 才生效，本身就是一次必然的漏錄（requirement.md:116）。
2. **黑畫面**。切換 Space 時，錄製中的指定視窗變黑（requirement.md:8、41）；實際使用的是 ⇧⌘5 的「錄製所選視窗」（requirement.md:21、41）。

**第 0 階段對第 2 項的歸因結論**：黑畫面**不是 ScreenCaptureKit 的限制**，而是 macOS 26 全新的 ⇧⌘5 視窗錄影實作的問題（`PROBE-REPORT.md:8-10`）。證據：Chromium 系視窗在別的 Space 上仍擷取到真實內容——幀狀態 complete 3／idle 22、非黑比例 **0.766、0 幀全黑**（`PROBE-REPORT.md:16`），錄出影片最後一幀平均亮度 **205.7/255**、非黑像素 83.8%（`PROBE-REPORT.md:19`）；前景基線組 complete **100%**、非黑比例 1.000（`PROBE-REPORT.md:17`），證明量測本身可信。

**第 1 項的歸因結論**：痛點的根源是**音訊裝置成員寫死**（requirement.md:40），不是操作不小心；只要錄製路徑不依賴寫死的裝置成員，這個失敗模式就能結構性消除（requirement.md:30）。

**流程面的問題（使用者點名「GIT 的管控」，依 D4 納入本 epic）**：GIT 管控的設定與事實不符。實測 `git remote -v` 回 `origin https://github.com/s96cax98leo/meeting-harness.git`、`git rev-list --count origin/main..main` 回 **9**，repo 是 **public**（`research-upstream.md:15-23`）；但 `CLAUDE.md:16`、`.claude/teams/rules.md:15`、`.claude/teams/rules.md:52`、`.claude/teams/guard.config.json:8`（`"fork_repo": ""`）、`workflow.config:7`（`FORK_REPO=`）五處都寫成或等同「沒有 remote」。其中 `fork_repo` 為空**不只是文件錯誤**：守門 hook 在 `fork_repo` 為空時只要求 `gh` 寫入帶任何 `--repo`、且 `gh api` 的目標限制整條被跳過（`/Users/yuktang/Documents/Agent/AgentWorkFlow/plugin/hooks/guard.py:246-253`，唯讀查閱；分析見 `research-code-contracts.md:147-153`）。另外署名行設定與使用者目前的模型不符，且 `attribution_line` 與 `forbidden_trailers` 字面衝突（見 §5 已定案 Q5）。

## 2. 期望結果

**錄製本體與觸發**
- 使用者在會議開始前用一個動作（終端機選單、或 menu bar／全域快捷鍵）就開始錄，錄完自動成為管線認得的場次（requirement.md:125、252、255）。
- **全程不需要碰 BlackHole、音訊 MIDI 設定或預設輸出裝置**；錄製中換藍牙耳機也不中斷（requirement.md:30、130；驗收見 requirement.md:271）。
- **漏錄在技術上被三道防線擋住**（requirement.md:195-201）：開錄前 preflight（requirement.md:197-198，項目與分級依 D1，見 §5 Q1）、錄製中監看（requirement.md:199）、分段落盤（每段獨立可播的 `.mov`，分段長度依 D3 為 **1 分鐘**；crash 後可 `meeting record finish` 救回，requirement.md:200 經 D3 修訂）。
- 切到別的 Space 繼續錄到會議視窗；偵測到疑似黑畫面時**只告警不自動改行為**（不自動降級成錄整個螢幕；requirement.md:191）。
- 產出擺法依 requirement.md:132-157：`錄音/` 永遠只有**一個** 16k mono wav ＋ `meeting.json`，中間產物全在非遞迴 glob 掃不到的 `錄音/tracks/`，全解析度影片另放 `影片/`。正本「『場次存在』與『錄製完成』同一瞬間發生」（requirement.md:156）**要成立有前提**：finalize 不得直接寫入 `錄音/`，見 §3 的競態項目。

**端到端驗收中必須帶進 spec 的條目**（requirement.md:261-283 全數承接，以下列出容易被壓縮掉或經使用者修訂的條目）
- `錄音/` 裡恰好一個音源檔（requirement.md:263）。
- **混音音軌裡同時聽得到遠端與自己**（requirement.md:266）。這是 `capturesAudio` ＋ `captureMicrophone` 兩者都生效的**唯一證據**；只有一邊有聲＝其中一個權限沒拿到，而失敗模式是靜默的。preflight 的 RMS 與錄製中雙路 RMS 都不能取代這條「成品檔裡兩邊都聽得到」的驗收。
- 裝置切換：錄 3 分鐘、第 2 分鐘切藍牙耳機再切回，全程 RMS > -60 dBFS 無斷點、`record.meta.json` 有兩次裝置變更事件（requirement.md:271）。
- preflight：每一項各製造一次失敗，確認訊息看得懂、結束碼正確（requirement.md:273；項目數與 hard／warn 分級依 D1）。
- **crash 救援（依 D3 修訂）**：錄 2 分鐘後 `kill -9`，`meeting record finish <場次>` **救回約 1–2 分鐘**（最後一段未收尾的 1 分鐘會丟，這是預期行為，要寫在說明裡），再跑一次確認冪等。原文 requirement.md:275 寫「救回約 2 分鐘（最後未滿 5 分鐘那段會丟）」，與 5 分鐘分段自相矛盾，已由 D3 取代。
- 並發安全：錄製進行中另一個終端機跑 `meeting prep <根>`，該場次不應被列為場次（requirement.md:277）；**finalize 進行中**也要同樣成立（見 §3）。
- 迴歸：`meeting status <根>` 認得出新場次、`meeting prep <根>` 跑完 `transcript.raw.md` 非空且 `diarization.json`／`transcript.speakers.md` 存在、既有場次重跑 `meeting diarize` 逐秒一致率 100%（requirement.md:280-283）。

**介面與 skill**
- `meeting record` / `record windows` / `record preflight` / `record stop` / `record status` / `record finish <場次>` 六個子指令是**純加法**，既有子指令與結束碼語意零變更（requirement.md:224；`.claude/teams/rules.md:68`）。
- 第七個 skill `meeting-record` 上線並以 symlink 裝到 `~/.claude/skills/`（requirement.md:220）；`meeting-summary` 只在正文加一行指路（requirement.md:222），**不動 frontmatter**（它是觸發詞來源，`research-code-contracts.md:30`）。
- `diarize.sh` 與 `_merge_speakers.py` **完全不動**（requirement.md:257）。

**GIT 管控（依 D4，本 epic 交付）**
- 五處設定與事實對齊、署名行換成使用者目前的模型、`attribution_line` 與 `forbidden_trailers` 的字面衝突釐清；在 `feature/meeting-record` 的**第一個 commit** 完成（細目見 §5〈已知既成事實〉第 3 條）。
- 本 epic 全程不推送、不開 PR；推送仍是不可逆節點，要使用者當下同意（`CLAUDE.md:15-16`）。

## 3. 受影響的使用者與系統

**使用者**：本機唯一使用者（會議主持人／紀錄者）。失敗語意與既有 skill 不同——**錄製失敗＝會議要開始了、不可重來、要立刻去開權限**；總結失敗可以重跑。這是新增第七個 skill 而非擴充 `meeting-summary` 的主要理由（requirement.md:226-228）。

**要改的既有檔（contract surface）**

| 檔案:行 | 動作 | 風險 |
|---|---|---|
| `bin/meeting.sh:359-409`（`case "$cmd"` dispatch；`*)` 在 :400） | 在 `*)` 之前插入 `record)` 分支 | 順序是硬要求，插在 `*)` 之後永遠不會被命中（`research-code-contracts.md:25`） |
| `bin/meeting.sh:24-86` `usage()` | 加 `record` 說明 | `bin/_lint.sh:19-23` 的反引號規則：同一行不得「雙引號 ＋ 一對反引號」並存 |
| `bin/meeting.sh:102-157` `doctor()` | 加錄製器／TCC／簽章檢查 | `doctor()` **沒有 `return 0`**，新增檢查若以裸 `grep`／`command -v` 收尾會讓 verify 變紅（`research-code-contracts.md:27`） |
| `README.md:9,24,90-108,357-379` | 目錄樹、指令表、結束碼語意、skill 表與重裝 for-loop 補第七個 | 漏改會讓換機重裝少裝 `meeting-record`（`research-code-contracts.md:28-29`） |
| `.claude/skills/meeting-summary/SKILL.md` | 正文加一行指路 | 只改正文，frontmatter 不動 |
| `config.json:44-64` `sourceLayout` | 加「影片」／`tracks` 等鍵（純文件，無程式讀） | 必須保持合法 JSON（`bin/_lint.sh:30`） |
| D4 的 GIT 管控檔（§5〈已知既成事實〉第 3 條） | 第一個 commit 修正 | 共用規則檔，改了等於改所有 agent 的行為；依 D4 已獲使用者決定 |

**要新增**：`tools/MeetingRecorder/Sources/*.swift` 擴充、`bin/record.sh`、`bin/_record_prompt.py`、`bin/_record_finalize.py`、`bin/_record_estimate.py`、`.claude/skills/meeting-record/SKILL.md` ＋ symlink（requirement.md:211-220）。

**已逐條覆核為「結構性不受影響」**（`research-code-contracts.md:39-47`）：
- `bin/_combine_audio.py:12-18` 的 glob 非遞迴 → `錄音/tracks/seg-*.mov` 掃不到那個「多檔會被串接不是混音」的陷阱。
- `has_audio()`／`list_sessions()`（`bin/meeting.sh:194`、`199-204`）非遞迴 → **錄製中**不被當場次。
- `bin/diarize.sh:27-28` 的 `ffmpeg -ar 16000 -ac 1` 無條件執行，輸入已是 16k mono 只是便宜複製，兩行不用改。
- 「影片」目錄在全 repo 零處理。

**不在上述清單、design 必須解的項目：finalize 直接寫入 `錄音/` 的競態。** `has_audio` 只用 `ls` 判斷副檔名、不檢查檔案是否寫完（`bin/meeting.sh:194`）。finalize 若讓 ffmpeg 直接輸出 `錄音/<場次>.wav`，在寫到一半時別的 session 跑 `meeting prep` 會把半成品當場次並餵給轉錄（`research-code-contracts.md:119-121`）。正本的並發驗收只驗「錄製中」（requirement.md:277），沒驗「finalize 進行中」。design 要定寫入方式（例如先寫到 `tracks/` 或點號開頭的暫存檔再原子換名）並補一條對應驗收。

**可重用的既有程式碼**（第 0 階段已在 `main` 的 `9a76c83`，`tools/MeetingRecorder/Sources/main.swift`）：`Logger`(:24-41)、`Args`(:58-87)、`displayPixelSize`(:91-96)、`shareableContent`(:102-104)、`candidateWindows`(:106-133，含會議 app 清單)、`cmdWindows`(:135-187，`--json` 分支 :153-168)、`frameStatus`(:221-235)、`nonBlackRatio`(:239-265)、`SCRecordingOutput` 加掛樣板(:361-376)；`tools/MeetingRecorder/probe.sh:29-48` 的 `follow()` 是檔案式狀態通道輪詢的現成樣板。**真正要新寫的**：`.audio` output 與 RMS、preflight、狀態檔／pid、Core Audio 預設裝置 listener、磁碟檢查、分段輪替、menu bar／hotkey（`research-code-contracts.md:77`）。

**系統面**：TCC（螢幕錄製、麥克風）、LaunchServices（`open -n -a … --args`）、鑰匙圈（固定自簽憑證）、`~/.meeting-harness/`（狀態檔、pid、log）。

## 4. 限制

**不得推翻的既有定案**

1. **`meeting.sh` 是對外介面**：子指令與結束碼語意不得破壞性變更；六個 skill 以 symlink 裝在 `~/.claude/skills/`，改 repo 的 `SKILL.md` 等於改全域（`.claude/teams/rules.md:68`、`CLAUDE.md:49`）。新增 `4`＝preflight 硬性失敗、`5`＝錄製異常但段落已保留，**只出現在新子指令上**（requirement.md:224）。注意 `4`／`5` 在既有腳本已被使用（`bin/diarize.sh:28` 的 `exit 4`、`bin/diarize.sh:44` 的 `exit 5`、`bin/transcribe.sh:190` 的 `exit 4`），所以 spec 要寫出全域結束碼對映表（`research-requirement.md:161-164`）。
2. **verify 指令固定** `bash bin/_lint.sh && bash bin/meeting.sh doctor`，**沒有錄音檔也要能全綠**，不綠就是環境壞了，不要改測試去配合（`.claude/teams/rules.md:59`）。
3. **raw 逐字稿不改、不編造 owner／期限、不確定的姓名不掛、雜訊標「（聽不清）」、聲紋只留本機 `vault/`**（`.claude/teams/rules.md:62-66`）。錄製器不碰逐字稿與認人；互動選單問出席者**只為講者命名，不是鎖人數**，`meeting.json` 的 `expectedSpeakers` 必須寫 `null`（requirement.md:269；`bin/_profile.py:28-33` 的註解：硬鎖人數讓逐秒一致率從 94.1% 掉到 80.0%；`bin/_profile.py:78-80` 只調上限）。
4. **錄製產出含人聲與客戶畫面，一律不落在 repo 內**（會議資料目錄的定案：`.claude/teams/rules.md:54`）；端到端驗證與 D2 實測的錄檔寫到會議資料目錄或 `~/.meeting-harness/`。D2 的測試影片屬於某一客戶的會議資料，實測產出只能放在該客戶目錄或 `~/.meeting-harness/`，不得複製進 repo、run 目錄，也不得與其他客戶的資料交叉引用（`.claude/teams/rules.md:28`）。
5. **分軌方案已被使用者移除**：音訊混成一軌，`diarize.sh` 與 `_merge_speakers.py` 完全不動（requirement.md:148、257）。
6. **`has_ui`／`has_security` 一律 false、無 compose**（`CLAUDE.md:47`、`.claude/teams/rules.md:58`）——但第 2 階段的 menu bar 是本 repo 第一次有 UI，見待解 Q4。
7. **不自編任務編號**（`CLAUDE.md:29`、`.claude/teams/rules.md:24`）。既有 commit 的 scope 是模組名（`feat(record):`）；本 epic 的驗收條目改用節編號（例 `spec.md §3.2`）代替 Story ID，這件事要寫進 spec 的〈整合修訂與例外〉（`research-specs-adr.md:110-112`）。

**技術限制**（第 0 階段的 API 結論在此列為 design 的出發點，不是問題本身）

- **API 前提（requirement.md:173-185，已在本機 SDK 逐項確認存在）**：切到別的 Space 也要錄到視窗，唯一可用的初始化器是 `SCContentFilter(desktopIndependentWindow:)`（requirement.md:177），且 `onScreenWindowsOnly` 必須 `false`（requirement.md:178；`PROBE-REPORT.md:25` 實測確認）。系統聲音 `capturesAudio` 與麥克風 `captureMicrophone` 是同一條 stream 上的兩個獨立 output type（requirement.md:28），`microphoneCaptureDeviceID = nil` 代表跟隨系統預設輸入（requirement.md:183）——這是「換藍牙耳機也不壞」的結構性依據。
- **TCC 歸屬鐵則**：任何觸發層都不准直接 `exec` 錄製二進位，一律 `open -n -a MeetingRecorder.app --args …`（requirement.md:205）。代價必須付（requirement.md:207）：`open` 成功派送後**立刻回 0、不轉傳被啟動 app 的結束碼**，所以 `record.sh` 的 `4`／`5` 必須自己從狀態檔推導；`~/.meeting-harness/record.status.json` 是 `record.sh` 與 MeetingRecorder 之間**新的、唯一的**契約（`research-code-contracts.md:113-117`）。
- **第 2 階段的觸發層做法**（requirement.md:255）：先用內建 Shortcuts 綁全域快捷鍵（只執行一行 `open -n -a MeetingRecorder --args quick-start`，不碰任何需授權的 API，TCC 歸屬不受影響）；再做 menu bar（`LSUIElement`、`NSStatusItem`、Carbon `RegisterEventHotKey`），**避開 `NSEvent.addGlobalMonitorForEvents`**——它需要「輔助使用」授權，會多一個漏錄來源。
- **授權對已啟動的程式不生效，必須完全結束 app 再重開**，而失敗訊息長得像「被拒絕」（`PROBE-REPORT.md:51-53`：TCC 資料庫是 `kTCCServiceScreenCapture | com.meetingharness.recorder | 2`＝已允許，程式卻回拒絕）。preflight 必須把「剛授權要重啟」與「真的沒授權」分開報。
- **目前是 ad-hoc 簽章**（`tools/MeetingRecorder/build.sh:31-45` 的 fallback；`PROBE-REPORT.md:57`），重建後 cdhash 變、TCC 授權會掉；正本要求固定自簽憑證（requirement.md:209），但目前**尚未建成功**——`security find-identity -v -p codesigning` 回「0 valid identities found」。依 D1，簽章身分在憑證建好前只列 warn。
- **畫布尺寸**：requirement.md:179 與驗收 requirement.md:264 寫 2992×1876（另見 :57、:123、:144），但第 0 階段實測畫布為 **2992×1934**（`PROBE-REPORT.md:4`），面板原生 3456×2234；1876 看來是舊 ⇧⌘5 錄檔的尺寸（requirement.md:57），不是顯示器像素。驗收硬寫 1876 會直接 fail（`research-requirement.md:149-151`）。
- **fps 不能驗平均值**：`minimumFrameInterval = 1/60` 是上限（requirement.md:181），而第 0 階段證實「沒有新內容就不寫」（`PROBE-REPORT.md:27`：Chrome 那場擷取 12 秒只產出 1.49 秒影片，PTS 時間軸正確）。「≈60 fps」（requirement.md:264）只能改驗設定正確與尖峰值（`research-requirement.md:153-155`）。
- **影片軌會比音訊軌短**（`PROBE-REPORT.md:29`）→「duration 差 < 100 ms」（requirement.md:267）需要 finalize 補幀，而補幀是尚未設計的工作項（`research-requirement.md:157-159`）。
- **分段長度依 D3 為 1 分鐘**（取代 requirement.md:200 的 5 分鐘）。代價寫明：輪替次數是 5 分鐘方案的 **5 倍**（每小時 60 次對 12 次），每次輪替的空隙損失累積同比放大。空隙門檻**沿用 0.5 秒**（requirement.md:201、268）；超過就退回「不分段」或自管 `AVAssetWriter`（requirement.md:201）。第 0 階段只掛過單一 `SCRecordingOutput`、沒做過任何輪替，空隙大小目前**無本機數據**（`research-requirement.md:220`）；正本只說「一條 stream 只支援一個 recordingOutput」（requirement.md:201、295）。design 要說明在 1 分鐘分段下空隙的量法與累積損失的判定方式。
- **已知缺陷要避開**：`captureMicrophone = true` 有「產出 MP4 無法播放」的官方論壇回報（無結論）→ 容器用 `.mov`（requirement.md:115、167、185）；macOS 26.5 beta 有「process tap 跑幾分鐘後 buffer 全變 0」的社群回報（requirement.md:117）。
- **`_lint.sh` 會掃新增的 `bin/*.sh`／`bin/*.py`**（`bin/_lint.sh:12`、`:26`；現況基線 `bash bin/_lint.sh` 回「lint 通過（22 個檔）」，新增 4 檔後應為 26）；`tools/MeetingRecorder/*.sh` 不在掃描範圍，那兩支腳本目前**沒有 `bash -n` 檢查**。

**GIT 管控限制（使用者本次特別點名）**

- 本 epic 在 worktree `/Users/yuktang/Documents/Agent/meeting-harness/.worktrees/meeting-record`、分支 `feature/meeting-record`（從 `main` 開，天然含第 0 階段 `9a76c83`）；子任務用 `feature/meeting-record--<sub>` 各開 worktree、檔案所有權不重疊（`.claude/teams/rules.md:36`）。
- **推送、開 PR、寫上游、加 remote 一律是不可逆節點**，要使用者當下同意，先前的同意不延伸；agent 不推送、不合併、不 approve（`CLAUDE.md:15-16`、`.claude/teams/rules.md:15-16`、`.claude/teams/rules.md:19`）。**本 epic 的開發過程不會動到遠端。**
- 遠端 `main` **未受保護**（`protected: false`），一次寫入就直接改寫 public 的 `main`，沒有 PR 當緩衝（`research-upstream.md:22`、`:84`）。
- 上游**沒有任何競爭變更**：0 PR、0 fork、0 Actions run，`origin/main`（`0b4e9c3`）是本機 `main` 的祖先且可 fast-forward；遠端完全沒有 `tools/`、`.claude/teams/`。所以合併衝突風險實質為零，但**也沒有遠端 CI 可倚賴**，全靠本機 verify（`research-upstream.md:16-21`、`:31-35`、`:83`）。
- 不強制覆寫遠端、不 `--no-verify`；Conventional Commits。署名行依 D4 改為 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`（第一個 commit 起生效，細目見 §5〈已知既成事實〉第 3 條）。
- `.gitignore`（39 行）沒有 `tracks/`、「影片」、媒體副檔名規則，也沒有 `.worktrees/`（`grep -n 'tracks\|影片\|worktrees' .gitignore` 無結果；本次建立 worktree 後 `git status` 仍乾淨，故非阻斷，但缺第二道防線；`research-code-contracts.md:123-127`）。

## 5. 待解問題

編號 Q-xx 僅供本檔內引用，**不是任務編號**。Q1、Q2、Q3、Q5 已由使用者在閘門 1 前定案（`gate1-decisions.md` 的 D1–D4）；Q4、Q6–Q9 由 Design 段定案。

### 已定案

| # | 問題 | 定案（依據） | 對 spec 的要求 |
|---|---|---|---|
| Q1 | preflight 的第 12 項是什麼、每項是 hard 還是 warn？（正本三處寫「12 項」：requirement.md:197、252、273，但 :197 實列 11 項；:293 的「視窗最小化改用 preflight 警告」未入列） | **已定案（D1）**：第 12 項＝**視窗是否最小化**，沒有公開 API 可判斷（requirement.md:293），**只能警告**。每項標 hard（exit 4、不開錄）或 warn（照開錄、提示使用者）。分級原則：**權限類**（螢幕錄製權限、「剛授權要重啟」、麥克風權限）與 **RMS 類**（系統聲音 RMS、麥克風 RMS）＝hard；**簽章身分在固定自簽憑證建好前＝warn**。其餘項目（磁碟空間、目標視窗存在、場次撞名、電源、已有錄製在跑）的分級與結束碼（requirement.md:273 要求 4／2／3）由 design 依同一原則逐項定案 | requirement.md:197「任何 fail 一律不開錄」改為「任何 hard fail 不開錄」，此修訂要寫進 spec〈整合修訂與例外〉；requirement.md:273 的驗收改為 12 項各製造一次失敗，並驗 hard 項 exit 4、warn 項照常開錄且有提示 |
| Q2 | 開錄前怎麼驗證系統聲音錄得到？（requirement.md:184 要 `excludesCurrentProcessAudio = true`，會排除錄製器自己播的測試音；requirement.md:198 卻要開錄前播測試音量 RMS） | **已定案的驗證方式（D2）**：用使用者提供的**真實會議影片**，由**另一個 app** 播放（不受 `excludesCurrentProcessAudio` 影響）實測系統聲音擷取；同一輪順便實測用 `afplay` 播測試音會不會被排除。**preflight 的正式量法由 design 依實測結果定案** | **design 段的前置輸入：影片路徑待使用者提供。** 實測產出依 §4 限制 4 落在 repo 外；design 要寫明 preflight 系統聲音那一項的訊號來源與判定門檻（正本門檻為 > -60 dBFS，requirement.md:198） |
| Q3 | 分段長度與 crash 救援的數字怎麼對齊？（requirement.md:200 每 5 分鐘輪替；requirement.md:275 要「錄 2 分鐘 kill -9 救回約 2 分鐘」，依其自述應救回 0 分鐘） | **已定案（D3）**：**分段 1 分鐘**；驗收改為「錄 2 分鐘 `kill -9` 救回約 1–2 分鐘」 | 輪替次數為 5 分鐘方案的 5 倍、累積空隙損失同比放大；空隙門檻沿用 0.5 秒（requirement.md:201、268）。兩處正本修訂（:200、:275）寫進 spec〈整合修訂與例外〉 |
| Q5 | `guard.config.json:17` 的 `attribution_line` 與 `:18` 的 `forbidden_trailers` 字面衝突，哪一邊為準？ | **已定案，併入 D4 交付**：以 `attribution_line` 為準，署名行換成 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；字面衝突在第一個 commit 一併釐清（細目見下方〈已知既成事實〉第 3 條） | 釐清後 `python3 .claude/teams/tools/check_rules.py --git <repo> <range>` 對本 epic 的 commit 要通過 |

### 留給 Design 段定案

| # | 待解 | 為什麼擋住 | 出處 |
|---|---|---|---|
| Q4 | 第 2 階段的 menu bar 要不要讓 test 段 `has_ui=true`？ | `CLAUDE.md:47`／`.claude/teams/rules.md:58` 寫一律 false，但 menu bar 是本 repo 第一次有 UI；repo 無設計系統 skill，審查缺對照依據 | `research-specs-adr.md:97-99` |
| Q6 | `meeting.json` 要不要寫第 7 個 key `_note`？`bin/_scaffold.py:107-110` 實際寫 7 個 key，而 requirement.md:269 的驗收要「key 集合完全相同」、requirement.md:78 的自述只列 6 個 | 字面照驗，寫 6 個 key 就 fail | `research-code-contracts.md:51`、`research-specs-adr.md:126-127` |
| Q7 | `tracks/` 在 finalize 之後留不留？冪等（requirement.md:218）通常意味保留輸入 → 磁碟峰值 2 倍（67 分鐘場次約 7.4 GiB），直接決定 preflight 磁碟門檻與 `_record_estimate.py`（requirement.md:219）的係數 | 正本未說何時刪 | `research-requirement.md:170-172` |
| Q8 | `doctor` 新增的錄製器檢查怎麼同時守住 `.claude/teams/rules.md:59`「沒有錄音檔也要全綠」？ | 若用硬性 fail，未建 app 的機器 verify 直接紅，影響所有既有流程 | `research-specs-adr.md:93-95`（建議：沿用既有「◦ 未裝（選用）」語意，硬性 fail 只出現在 `record preflight`） |
| Q9 | 第 0 階段四個未驗情境（Teams 通話中＋別的 Space／native 全螢幕後切走／最小化／Mission Control）進第 1 階段驗收，還是列衍生工作？ | 需人工操作；正本只對 native 全螢幕給了處置（requirement.md:249） | `PROBE-REPORT.md:31-38`、`research-requirement.md:182-184` |

### 已知既成事實（要寫進 spec 的〈整合修訂與例外〉）

1. **第 0 階段在主工作目錄直接開發並 commit 到 `main`**（`9a76c83`，5 檔 692 行，全在 `tools/MeetingRecorder/`；`git show --stat 9a76c83`），未開 feature 分支／worktree、跳過 plan→design 閘門，是對 AI-native SDLC 的偏離（`.claude/teams/rules.md:33`、`:36`）。該 commit 的檔案與第 1 階段要動的檔案完全重疊，所以 `feature/meeting-record` 從 `main` 開是正確處置，**不需要 revert**。
2. **固定自簽憑證尚未建成功**（憑證在鑰匙圈但 `security find-identity -v -p codesigning` 回「0 valid identities found」，私鑰與憑證沒配成對）；`tools/MeetingRecorder/build.sh:31-45` 目前會 fallback 到 ad-hoc 並印警告。依 D1，在建好前 preflight 的簽章項只列 warn；建好需使用者在鑰匙圈 GUI 操作（步驟見 `PROBE-REPORT.md:57-61`）。
3. **GIT 管控設定與事實不符，依使用者 D4 決定，在本 epic 第一個 commit 修正**（`feature/meeting-record` 上、任何功能程式碼之前）。要修的檔與值：

   | 檔:行 | 現值 | 修正後 |
   |---|---|---|
   | `.claude/teams/guard.config.json:8` | `"fork_repo": ""` | `"fork_repo": "s96cax98leo/meeting-harness"`（**收緊**守門：`gh` 寫入必須帶 `--repo s96cax98leo/meeting-harness`，`gh api` 寫入只能打 `repos/s96cax98leo/meeting-harness/`；依據 `guard.py:246-253`） |
   | `workflow.config:7` | `FORK_REPO=` | `FORK_REPO=s96cax98leo/meeting-harness`（`guard.config.json:2` 註明它由 `workflow.config` 經 init.sh 產生，兩邊不同步會在下次 init 被蓋回） |
   | `CLAUDE.md:16` | 「本 repo 目前沒有 remote，要加 remote 也要先問」 | 改為已有 `origin`（public GitHub repo `s96cax98leo/meeting-harness`），推送仍要使用者當下同意 |
   | `.claude/teams/rules.md:15` | 「本 repo 目前沒有任何 remote（`fork_repo` 空）」 | 同上，並註明 `fork_repo` 已設定 |
   | `.claude/teams/rules.md:52` | 「目前 6 個 commit 都只在本機，沒有 remote」 | 改為有 remote 的敘述；commit 數會過期，建議不寫數字（實測 `git rev-list --count main` 為 18） |
   | 署名行：`.claude/teams/guard.config.json:17`、`workflow.config:18`、`CLAUDE.md:39`、`.claude/teams/rules.md:35` | `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` | `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`（使用者已切換模型） |
   | `.claude/teams/guard.config.json:18` | `"forbidden_trailers": ["Co-Authored-By"]` | 釐清字面衝突（見下） |

   **`attribution_line` 與 `forbidden_trailers` 的字面衝突釐清**：實際執行上**沒有衝突**——`.claude/teams/tools/check_rules.py:30-31` 先取署名行的 key（`Co-Authored-By`），再把 `forbidden_trailers` 裡與它同名的項目濾掉，所以 `Co-Authored-By` 不會被判違規；守門 hook 也不讀 `forbidden_trailers`（`grep -rn forbidden_trailers /Users/yuktang/Documents/Agent/AgentWorkFlow/plugin` 無結果）。衝突只在字面，會讓讀設定的人與 agent 誤判（`research-upstream.md:78`、`research-code-contracts.md:158`）。修正方式是讓設定字面上自洽：`forbidden_trailers` 不再列出與署名行同名的 key，具體值（清空，或改列真正要禁止的 trailer）在第一個 commit 決定並在 commit 內文說明；`check_rules.py` 的 R4 只比對 trailer 的 key（`check_rules.py:77-78`），所以換署名行的模型名稱不影響既有 commit 的檢查結果。

   範圍備註：同一個舊署名字串另硬寫在 `.claude/workflows/sdlc-build.js:21`、`sdlc-design-revise.js:29`、`sdlc-design.js:33`、`sdlc-plan.js:53`（`git grep -n 'Opus 5 (1M context)'`）。D4 原話只列「署名行換成目前的」，未逐檔列舉；不同步替換的話，後續 SDLC 段派出的 agent 會繼續用舊署名行。是否一併納入第一個 commit 列在本次信封的 open_questions（非阻斷，建議納入）。

   既有 6 個 commit 另帶 CLAUDE.md 未規定的 `Claude-Session` trailer（`git log --format=%B | grep -c '^Claude-Session'` 回 6），推到 public repo 會公開 session 連結（`research-upstream.md:78`）。處理它要改寫已存在的歷史，不在 D4 範圍，列入第 6 條的推送前人工確認清單。
4. **`PROBE-REPORT.md` 有兩份**（`tools/MeetingRecorder/PROBE-REPORT.md` 進版控；`_tpm/runs/20261010-sdlc-meeting-record/phase0-probe-report.md` 被 `.gitignore:36` 的 `/_tpm/runs/*` 排除），內容相同，需指定正本避免漂移；建議以 `tools/` 那份為正本。
5. **需求正本對現況的描述有兩條已不成立**，spec 不應承接，也不該為它們開任務：
   - requirement.md:75 寫 `config.json:45` 的 `audioGlob` 少了 m4v，實際六種齊全（`sed -n '45p' config.json`；`research-specs-adr.md:114-120`）。
   - requirement.md:80 寫「既有錄製程式碼：無」，已因第 0 階段 `9a76c83` 進 `main` 而過期（`tools/MeetingRecorder/Sources/main.swift` 存在）。
6. **repo 是 public，且已追蹤檔含真實視窗標題**（`tools/MeetingRecorder/PROBE-REPORT.md:16` 的 Chrome 視窗標題）與 11 個檔含 `/Users/yuktang` 絕對路徑（`research-upstream.md:75-76`），加上第 3 條的 `Claude-Session` trailer。不影響開發，但要列進 deliver 段對外送出前的人工確認清單。

### 明確在範圍外

- 分軌改善講者識別（使用者已移除，requirement.md:257）。
- 讀行事曆在會議開始前推播提醒（requirement.md:300，正本已標「衍生工作（不編號）」）。
- 第 0 階段本身（已完成，`PROBE-REPORT.md`）。
- 常駐第二條低 fps 保險 stream：觸發條件是 `.complete` 且非黑比例 < 0.01（requirement.md:247），實測 0.766（`PROBE-REPORT.md:16`），條件未成立。
- 收斂四份副檔名清單（衍生工作，不編號；四份目前一致，`research-specs-adr.md:120`）。
- `config.json:34` 的 diarize 說明（寫「有 attendees/expectedSpeakers 就鎖 num_speakers」）與 `bin/_profile.py:76-81` 的實際行為（只調 `max_spk`）相反：本 epic 之前就存在的文件錯誤，建議順手修但非本 epic 驗收（`research-specs-adr.md:122-124`）。

---

## R2 第二輪功能（2026-10-12）

- 性質：第二輪（R2）增補，**另走 R2 的閘門 1 核准**；本節以上的第一輪內容（第 1–176 行，§1–§5）原文不動，仍以第一輪的核准為準。
- 需求正本：`_tpm/runs/20261010-sdlc-meeting-record/r2-brief.md`（82 行，本機、不在版控；以下簡寫 `brief:<行>`）。派工單轉述使用者 2026-10-12 在 plan mode 核准了這份計畫。
- 調研依據：同 run 目錄四份筆記的 R2 節——`research-requirement.md`（:226 起，簡寫 `rq:`）、`research-specs-adr.md`（:153 起，簡寫 `sa:`）、`research-code-contracts.md`（:1-252，簡寫 `cc:`）、`research-upstream.md`（簡寫 `up:`）。
- 程式行號以 worktree HEAD `f084765` 為準。編號 F1–F9、R2-Qxx 只供本節內引用，**不是任務編號**。
- 範例名稱一律用「[Stand-up] 範例專案」；本節不寫任何真實客戶、會議或視窗標題。
- 行號位移提醒：`research-code-contracts.md` 在 R2 調研時改版，第一輪原文移到附錄（`cc:254` 起）。第一輪 §1–§5 引用該檔的行號（例如 `research-code-contracts.md:25`）要加 255 才對得到（實測：第一輪 `:158` 現在在 `:413`）。第一輪內容不改，只在這裡記錄。

### R2-1. 問題

第一輪交付的 menu bar 只有「開始（用上次設定）／停止／打開資料夾」（brief:4）。實際使用時有三個缺口（brief:5-7）：

1. **想暫時不錄自己的聲音（例如講私事）時，沒有地方可以按。** 錄製端只接 SIGTERM／SIGINT（`tools/MeetingRecorder/Sources/Capture/RecordingSession.swift:228-239`），沒有任何錄製中的控制通道。
2. **換資料夾或換視窗都得回終端機。** 「開始」只能用上次的根目錄（`Sources/Trigger/QuickStart.swift:31-33` 取 `defaults.root`），而且畫面上要剛好只有一個 ★ 視窗（`quickStartDecision`，`spec.md §4.11.1`）。
3. **錄製中看不到計時、沒有偏好設定、重開機後要手動把 menu bar 叫回來。** 第一輪 D12 的定案是「menu bar 上只放圖示，不放文字（不顯示計時）」（`specs/meeting-record/design.md:387`；`spec.md:720` §4.11.5）。

外部調研的結論（brief:9、:72-75）：選視窗、選存檔位置、全域快捷鍵、選單列紅點加計時、暫停／繼續、停止後在 Finder 顯示、偏好設定、登入時啟動，是完整錄製工具的基本配備。只靜音麥克風在官方文件中只看到 OBS 有做，卻是會議情境最需要的。

### R2-2. 期望結果

**使用者決定（brief:11-14，2026-10-12）**：要做「只靜音我的麥克風」；範圍包含選單選視窗與存檔位置、紅點加計時、偏好設定加登入自動開、標記，並由主 session 補建議；「整段暫停時，暫停那段在成品中剪掉，但要記下時間點」。F8、F9 在 brief 標為「（我的建議）」（brief:29-30），是主 session 補的建議，隨整份 brief 一起核准（`rq:244-248`）。

| # | 功能 | 使用者看得到的結果 | 依據 |
|---|---|---|---|
| F1 | 只靜音麥克風（⌃⌥⌘M、選單「麥克風靜音」打勾） | 靜音期間 mic 軌照常寫，但內容是數位 0；系統聲音照錄；不因靜音觸發靜音誤報；事後查得到每次靜音、取消靜音的時間點 | brief:22 |
| F2 | 整段暫停／繼續（⌃⌥⌘P、選單） | 暫停那段不出現在成品；事後查得到每次暫停、繼續的時間點；暫停期間不誤報靜音、黑畫面，也不把暫停判成空隙 | brief:23；使用者決定 brief:14 |
| F3 | 選單「錄這個視窗 ▸」 | 從選單直接選要錄的視窗開錄，★ 排前面，不必回終端機 | brief:24 |
| F4 | 選單「存到 ▸」 | 從最近用過的位置（最多 5 個）或「選擇資料夾…」挑存檔位置，選定的位置下次沿用 | brief:25 |
| F5 | 紅點＋計時 | 錄製中 menu bar 顯示圓點加 `mm:ss`（扣掉暫停時間）；暫停、麥克風靜音各有可辨識的圖示；停止後的通知可「在 Finder 顯示」，選單有「顯示上一場成品」 | brief:26 |
| F6 | 標記（⌃⌥⌘B、選單「加標記」） | 會議中按一下就留下「標記 N」與時間點，成品資料夾裡有 `錄音/markers.json`，不影響場次判斷；summary 端怎麼用列為衍生工作 | brief:27；`bin/meeting.sh:255-256` 只認音源副檔名（`rq:R2-5` 第 15 條） |
| F7 | 偏好設定＋登入自動開 | 一個設定視窗：預設存檔位置、快捷鍵一覽（唯讀）、「登入時自動開啟」、「停止後自動跑前處理」；開啟登入自動開後，重新登入 menu bar 會出現 | brief:28、:68 |
| F8 | 停止後自動前處理（預設關） | 開啟時，收尾成功後在背景對這一場跑既有的 `meeting prep`，完成後通知 | brief:29 |
| F9 | 選單內收音指示 | 選單裡一行「系統聲音 ●　麥克風 ●」，依最近 3 秒有沒有超過 -60 dBFS 顯示有聲或無聲 | brief:30 |

**可以判定的成果**（細節由 spec §4.16 起寫成 EARS 驗收條件，brief:45）：

- 自動：Swift Core 單元測試涵蓋控制檔冪等、計時扣暫停、menuBarModel 暫停與靜音列、mic 歸零後 PCM 全 0、resume 換段；Python 測試涵蓋 finalize 剪掉暫停段後 gapStats 扣除、markers 複製、`e2e_check` 的暫停判準、CLI 新子指令結束碼；`bash bin/_lint.sh && bash bin/meeting.sh doctor` 全綠（brief:58）。
- 實機 t7（使用者在場，brief:59-70）：錄 4 分鐘，1:00 靜音麥克風 30 秒 → 2:00 整段暫停 30 秒 → 繼續 → 加 2 個標記 → 停止。驗：成品長度約為「錄製時間 − 30 秒」；靜音段 mic 全 0、系統聲音照常；`pauseEvents`、`micMuteEvents`、`markers.json` 的時間正確；暫停與靜音期間沒有靜音誤報；選單計時扣掉暫停。另外從選單換視窗、換存檔位置各開錄一次；開啟登入自動開後重新登入確認 menu bar 出現；開啟自動前處理確認 `transcript.raw.md` 產出；截圖交設計審查。
- 第一輪尚未完成的實機項目（§4.9.1 重錄、§4.3.5、§4.2.3、§4.11.1）一起在 t7 驗（brief:53）。

### R2-3. 受影響的使用者與系統

**使用者**：本機唯一使用者（會議主持人兼紀錄者），以及透過 `bin/meeting.sh` 與 `~/.claude/skills/meeting-*` 呼叫錄製的其他 session（`CLAUDE.md`〈對外介面〉；`.claude/teams/rules.md:68`）。

**對外契約面**（本 repo 沒有服務、沒有 `contracts/` 端點；R2 的契約全是本機介面，`cc:11`；上游沒有 PR、issue、CI，`up:4-7`）：

| 契約面 | R2 的變化 | 依據 |
|---|---|---|
| `meeting record` CLI | 新增 `pause｜resume｜mute｜unmute｜mark` 五個子指令，走控制檔＋訊號；既有子指令與結束碼不改 | brief:37；`spec.md §2.4`（封閉清單 7 種寫法） |
| `~/.meeting-harness/record.control.json`（新） | menu bar 與 CLI 寫入、錄製實例讀取 | brief:35 |
| `~/.meeting-harness/record.status.json` | 只加選用欄位 `paused`、`micMuted`、`pausedSeconds`、`markers`、`recentLevels`，不新增 `RecordPhase` | brief:36；`Sources/Capture/Support.swift:105-108` |
| `~/.meeting-harness/record.defaults.json` | F4 要加 `recentRoots`、寫回選定位置；目前只有 `record.sh` 一個寫者且整檔覆寫 | brief:25；`bin/record.sh:315-327`（`sa:C4`、`cc:C9`） |
| 場次 `record.meta.json` | 新增 `pauseEvents`、`micMuteEvents` | brief:22-23 |
| 場次 `tracks/markers.json`、`錄音/markers.json`（新） | 錄製實例寫、finalize 複製 | brief:27 |
| app 子指令與訊號 | 新增 SIGUSR1；quick-start 新增 `--window`／`--window-bundle`／`--window-title`／`--root` | brief:24、:35；`Sources/Capture/Commands.swift:89-98` 已有同名選項 |
| 登入項目 | `SMAppService.mainApp` 註冊；需要使用者在系統設定核准時引導過去 | brief:28 |

**要改的既有檔**（brief:41-45，`cc:§1` 已逐檔覆核）：`Sources/Capture/RecordingSession.swift`（暫停閘門、mic 歸零、偵測器重設、SIGUSR1；`SwitchReason` 是本檔 `:28` 的 `private enum`，不在 `Segments.swift`，`rq:R2-4`）、`Sources/Core/Segments.swift`、`Records.swift`、`Trigger.swift`、新增 `Sources/Core/Control.swift`、`Sources/Trigger/MenuBar.swift`、`HotKey.swift`、`QuickStart.swift`、新增 `Sources/Trigger/Preferences.swift`、`Sources/main.swift`（無參數啟動的行為，見 R2-Q6）、`bin/_record_finalize.py`、`bin/record.sh`、`bin/meeting.sh`、`tests/record/e2e_check.py`、`.claude/skills/meeting-record/SKILL.md`、`README.md`，以及 `specs/meeting-record/` 的 design、spec、plan、progress 與 ADR。

**要以 R2 決定取代、或要補規則的第一輪定案**（design 段寫明並記 `spec.md §6`，目前到第 76 條，`sa:161-165`）：

- D12「menu bar 只放圖示、不顯示計時」（`design.md:387`、`spec.md:720`）→ F5 取代。
- 選單結構固定（`spec.md §4.11.6`；`design.md:391`）→ F3–F7、F9 要插入新項目。
- CLI 封閉清單與寫死的測試預期（`tests/record/test_docs.py:16` 子指令集合、`:172` 的 17 次執行）→ 改測試預期屬 `rules.md:37` 的例外，要使用者核准。
- `record.status.json` 鍵集合恰為 12 個（`tools/MeetingRecorder/Tests/RecordsTests.swift:112-113`）→ 加選用欄位時同樣碰到既有測試（`cc:C7`）。
- 分段量測閘門（`spec.md §4.4.3`、`§4.4.8` stop_tail）、`levels` 的 `null` 語意（`spec.md §3.2`、`§6` 第 66 條）→ 要補「扣掉暫停、排除靜音區間」的規則（`sa:C5`、`sa:C6`）。
- quick-start「不猜選視窗」（`spec.md §4.11.1`）→ F3 帶 `--window` 時略過 ★ 判斷是新規則（`rq:R2-5` 第 9 條）。
- `has_ui` 例外：第一輪由 D12 定為 test 段派設計審查；R2 多了第一個真正的視窗（偏好設定），要再明確一次（`sa:K11`）。

### R2-4. 限制

1. **架構已定（brief:35-38）**：控制通道＝`record.control.json`（原子 rename）＋SIGUSR1，錄製實例收到後重讀控制檔，切換冪等；status 只加選用欄位、不新增 `RecordPhase`（新 phase 會讓舊版 `readStatus` 解碼失敗，`Support.swift:105-108`；`bin/record.sh:180-195` 的 `wait_phase` 只認固定集合）；CLI 對等子指令只新增不改既有，「3＝沒有錄製在跑」沿用；可測邏輯放 `Sources/Core`，AppKit 只負責接線。控制通道是第一輪 ADR（`adr/adr-control-channel.md:21-29`）的延伸，照慣例要補 ADR 後註或另立 ADR（`sa:K1`）。
2. **對外介面不得破壞性變更**：`bin/meeting.sh` 的子指令與結束碼（`.claude/teams/rules.md:68`）；`WarningKind` 也不加新 case，因為舊版 `readStatus` 用 `try?` 解碼，任何新 enum 值都會讓它回 nil（`sa:K3`）。
3. **分段架構沿用**：一條 stream 不停、每段一個 `AVAssetWriter`、新段第一個視訊 sample 落在邊界（`adr/adr-segment-writer.md:38-42`；`spec.md §4.4.4`）；F2 的 `.resume` 換段也要滿足。
4. **麥克風跟隨系統預設**：不碰預設音訊裝置（`spec.md §4.9.4`），所以「選麥克風裝置」列在範圍外（brief:32）。
5. **暫停段剪掉＝不落盤**：暫停期間丟棄 sample，不涉及刪檔；`tracks/` 永不自動刪的定案不變（`design.md:157`；`sa:K14`）。
6. **五條鐵則不變**（`rules.md:62-66`）：F8 只呼叫既有 `meeting prep`，不碰逐字稿內容。
7. **public repo**：specs、tests、範例不得含真實客戶、會議、視窗標題；範例一律用「[Stand-up] 範例專案」；`markers.json` 的 `label` 預設「標記 N」，不含使用者輸入（`spec.md §4.14.1`、`§4.14.3`；`sa:K12`）。
8. **subagent 不得啟動 `~/Applications/MeetingRecorder.app`、不得觸發 TCC 授權框或改使用者的系統設定**：登入項目、通知動作、快捷鍵、選單互動的實機驗收只能由使用者在 t7 做（brief:55）。
9. **分支與時程**：沿用 `feature/meeting-record` 與同一個 worktree；第一輪閘門 3 與 deliver 尚未通過（`progress.md`；`run.json` 的 `stages.test.status = needs_decision`、`deliver = pending`），R2 疊在同一分支上，第一輪剩下的實機項目與 R2 一起在 t7 驗（brief:53）。R2 走 plan → design → build → test 四個閘門，今晚的會議仍用現有的 `meeting record`（brief:16）。不 push、不改 `main`、不改寫歷史；`origin` 只有 `main`、是本分支的祖先，上游沒有衝突風險（`up:4-7`）。
10. **測試失敗改程式、不改測試**；必須改既有測試預期的（R2-3 列出的 CLI 封閉清單、狀態檔鍵集合、選單結構）要使用者核准並記在 spec〈整合修訂與例外〉（`rules.md:37`）。

### R2-5. 待解問題

編號 R2-Qxx 只供本節內引用，不是任務編號。

#### 交主 session／使用者決定（流程面，不擋 intent 起草）

| # | 問題 | 選項與代價 | 建議 | 依據 |
|---|---|---|---|---|
| R2-Q1 | 第一輪的證據與拆包範圍怎麼和 R2 切開？第一輪閘門 3（含 `spec.md §6` 第 63–75 條追認、verifier 的 §4.9.1）與 deliver 都還沒過，`plan.md §5` 的拆 PR／cherry-pick 規劃與 verifier 證據（HEAD `af91ec0` 時點）會被 R2 打散 | A. R2 第一個程式 commit 前打本機 tag 當第一輪基準點，t7 一起驗（照 brief:53）：多一個本機標記，拆包有明確切點／B. 不打標記，第一輪與 R2 一起驗、一起 deliver：test 段整份重驗，`plan.md §5` 要重寫／C. R2 另開分支：與派工單「沿用同一分支」不符，兩條線改同一批檔，合併會衝突 | A | `sa:C10`；brief:53 |
| R2-Q2 | R2 各閘門的核准記在哪裡？`run.json` 只有一組 `stages`，查不到 R2 的核准紀錄；照舊用 `save_run.py approve` 記到同一個 `stages.plan` 會蓋掉第一輪的紀錄 | A. `stages` 加 `r2-plan` 這類前綴鍵：要確認 `save_run.py` 支不支援／B. 另開 run 目錄給 R2：`r2-brief.md` 要搬或連結 | A 或 B，避免覆寫 | `sa:C11` |

#### 留給 Design 段定案（附建議，均非阻斷）

| # | 待解 | 為什麼重要 | 建議方向 | 依據 |
|---|---|---|---|---|
| R2-Q3 | `recentRoots`、F7「預設存檔位置」、既有 `defaults.root` 怎麼分工？哪一個決定 quick-start 與 ⌃⌥⌘R 的存檔位置？ | `record.sh` 的 `write_defaults` 每次開錄都把 `record.defaults.json` 整檔覆寫成固定 7 鍵，menu bar 寫的鍵會被洗掉；從沒跑過 CLI 的機器上只有 `root` 的 defaults 會讓收尾因 `harness` 缺值失敗 | 偏好設定另開檔，`record.defaults.json` 維持單一寫者；沒有完整 defaults 時「存到 ▸」灰掉並提示先跑一次 CLI | `bin/record.sh:315-327`；`rq:R2-5` 第 1 條；`sa:C4`；`cc:C9` |
| R2-Q4 | SIGUSR1 送到不會接的程序怎麼辦？ | SIGUSR1 預設動作是終止程序；舊版錄製實例或 preflight 階段（`pid` 先於 handler 寫入）收到就直接被殺、不收尾 | 只送給 `record.pid` 的 pid、只在 `phase == recording` 時送；status 加能力旗標，舊版沒有就不送並回固定結束碼與說明 | `RecordingSession.swift:130`、`:156`、`:228-239`；`cc:C1`；`rq:R2-5` 第 2 條 |
| R2-Q5 | 新子指令與 `meeting record [<根>]` 撞名，以及各種狀態下的結束碼 | `meeting record pause` 目前會把 `./pause` 當根目錄；已暫停再 `pause`、未暫停 `resume`、暫停中 `mark`、`phase` 是 preflight／stopping／finalizing、舊版實例，各回什麼都未定 | 比照 `help` 列為保留字並在 SKILL.md 教 `./pause` 寫法，記 `spec.md §7`；重複操作冪等回 0，沒有可控制的錄製一律回 3、stderr 說明原因，補 `spec.md §2.2` | `spec.md §2.4`；`spec.md:81`（`help` 保留字先例）；`rq:R2-5` 第 3–4 條；`cc:§5` 第 2–3 條 |
| R2-Q6 | 登入自動開時 app 以無參數啟動，現在會印 help 後結束 | 照 brief 做，登入後 menu bar 不會出現；點通知動作重新啟動 app 也會落在同一個分支 | 無參數改成進 menubar 模式（`help` 保留）；改 `spec.md §4.12.9` 的 dispatch 清單；`SMAppService` 能否帶參數由 design 查 Apple 文件確認 | `Sources/main.swift:73-75`；`cc:C3`；`sa:C9` |
| R2-Q7 | 多個全域快捷鍵會互相搶 | `HotKey` 的 `EventHotKeyID` 寫死 `id: 1`、handler 不比對 ID；加到 4 組後按 ⌃⌥⌘R 可能變成加標記 | 每組不同 id、handler 比對 id，新增測試；新三組沿用「註冊失敗寫 log、選單不顯示」（`spec.md §4.11.3`） | `Sources/Trigger/HotKey.swift:12-29`、`:23`；`cc:C2` |
| R2-Q8 | 時間軸：`pauseEvents`、`micMuteEvents`、`markers.t` 各用哪一把尺？暫停與靜音期間 `levels` 怎麼寫？ | 既有 `t` 全是含暫停的主機時鐘，markers 卻要扣暫停，同一場會有兩把尺；`levels` 以索引×0.5 秒對時，暫停停寫會錯位、補 null 會被判中斷；靜音記 null 又和「麥克風掉了」分不開 | 事件一律用既有錄製時鐘，另加成品時間欄位（例如 `outputT`）；`levels` 暫停期間照補 null，判準以 `pauseEvents`、`micMuteEvents` 排除區間；`e2e_check` 跟著改 | `rq:R2-5` 第 5–6 條；`sa:C6`、`sa:C7`；`cc:C5` |
| R2-Q9 | 暫停如何與分段量測閘門、`gapStats`、`stop_tail` 相容？暫停收段時晚到的 sample 怎麼處理？ | 暫停會產生短於 60 秒的段與等於暫停長度的空隙，`spec.md §4.4.3`、`§4.4.8` 三條判準都會 FAIL；直接把目前段落收掉會讓晚到的 sample 觸發 `.writerFailure` 開新段 | §4.4.3 加第三種排除（以 `pauseEvents` 判定）、`GapStats` 欄位擴充記 §6；暫停＝把目前段轉成 prev（停止點 E），只收 PTS < E 的 sample | `RecordingSession.swift:344-385`、`:437-444`；`sa:C5`；`cc:C6` |
| R2-Q10 | `record.status.json`／`record.meta.json` 新增鍵與「鍵集合恰為 N 個」的既有測試衝突 | 照慣例寫 null 要改既有測試（要使用者核准）；nil 時省略鍵違反本檔慣例 | 二選一：新欄位另放 `record.live.json`，既有檔完全不動；或寫 null、改測試並記 `spec.md §6` | `RecordsTests.swift:58`、`:112-113`；`cc:C7` |
| R2-Q11 | 控制檔殘留 | 控制檔跨場次共用、沒有 `runId`；上一場暫停中當機，下一場一開錄就會暫停或靜音 | 控制檔帶 `runId`，錄製實例開錄時以自己的 `runId` 重寫一份全 false 的控制檔，`markerSeq` 也以 `runId` 為範圍；寫進 ADR 後註 | `adr/adr-control-channel.md:23`；`sa:C8`；`cc:C10`；`rq:R2-5` 第 14 條 |
| R2-Q12 | 計時的起點與 `mm:ss` 超過 60 分鐘的顯示 | `startedAt` 在 preflight 開始時就設定，比真正開錄早約 10 秒；第一輪已有 67 分鐘場次的估算，`61:05` 還是 `1:01:05` 未定，也影響變寬 status item 的寬度與截斷規則 | 狀態檔由錄製實例直接給錄製秒數（扣暫停）；超過 60 分鐘改 `h:mm:ss`；用等寬數字避免每秒抖動 | `cc:C8`；`rq:R2-5` 第 8 條；`sa:C1` |
| R2-Q13 | F8 的執行者、範圍與互動 | 錄製實例收尾後立刻結束，不能等 `meeting prep`；講者分離只在 `MH_DO_DIARIZE=1` 時跑；傳根目錄會重跑整個根目錄；下一場開錄時上一場的轉錄還在吃 GPU | 由常駐的 menu bar 在看到 `done` 後啟動，或脫離的子程序；明寫傳場次目錄；說法改成「跑既有前處理」，驗收看 `transcript.raw.md`；開錄時是否讓路由 design 定 | `bin/meeting.sh:232`、`:261-266`；`cc:C13`；`rq:R2-5` 第 10 條；`sa:C14` |
| R2-Q14 | 「在 Finder 顯示」通知動作由誰接？ | 發收尾通知的錄製實例送完就 `exit`，沒有 category、沒有 delegate | 由 menu bar 偵測到 `done` 後發通知並當 delegate；menu bar 沒開時退回現行通知；「顯示上一場成品」選單項是保底入口 | `RecordingSession.swift:758-771`；`cc:C4`；`rq:R2-5` 第 11 條 |
| R2-Q15 | F3 列視窗、F7 登入項目的前提 | menu bar 是常駐程序，第一次在裡面呼叫 SCK，延遲與系統提示未能確認；`SMAppService` 對 app 位置與簽章的要求、重建後登入項目是否還有效未能確認 | F3 可照 `record.sh` 的 `fetch_windows` 另開短命程序列視窗；F7 的前提由 design 查文件寫明，實機只由使用者在 t7 驗 | `Sources/Capture/WindowSource.swift:68-80`；`bin/record.sh:204-234`；`cc:C11`；`rq:R2-5` 第 12 條 |
| R2-Q16 | 其他互動與細節 | 靜音中暫停、暫停中按停止（沒有目前段落時停止點怎麼算）、繼續時偵測器重設、暫停中磁碟檢查照不照跑、`markers.json` 在 `meeting record finish` 重跑時能否補上（`already_done` 會提早 return）、F9 `recentLevels` 的資料形狀與靜音中的顯示、t7「約為錄製時間 − 30 秒」的容許誤差與 240 秒分界 | 由 design 逐項寫進 spec；markers 複製放在 `already_done` 之前並冪等 | `rq:R2-5` 第 7、13、14、16 條；`sa:C13`；`cc:C14`；`tests/record/e2e_check.py:401` |

#### 明確在範圍外（brief:32）

開錄倒數；選麥克風裝置（會破壞「跟隨系統預設、換耳機不壞」的設計，要另議）；會議自動偵測與行事曆提醒；捨棄這次錄製；檢查更新（Sparkle）；Dock 備用入口。summary 端使用 `markers.json` 列為衍生工作（不編號）（brief:27）。

#### 衍生工作（不編號）

- summary 端讀 `錄音/markers.json` 對逐字稿（brief:27）。
- `startedAt` 比真正開錄早約 10 秒的既有偏差，即使不做 R2 也該修（`cc:C8`）；R2-Q12 若採建議，會一併處理計時這一面。
- app 無參數啟動只印 help，也影響「從 Finder 點 app 沒反應」（`cc:C3`）；R2-Q6 若採建議會一併修好。

### R2 閘門 1 使用者決定（2026-10-12）
- R2-Q1：R2 開工前打本機 tag `meeting-record-r1-baseline`（指向 `f084765`）當第一輪基準點；第一輪可單獨核准、單獨拆 PR；實機驗證與 R2 的 t7 一起做。tag 不推送。
- R2-Q2：R2 各段的紀錄與核准以 `r2-` 前綴的 stage 鍵記在同一個 run 目錄（`r2-plan`、`r2-design`、`r2-build`、`r2-test`），不覆寫第一輪。
- R2-Q3：最近位置清單另開 menu bar 專用設定檔，`record.defaults.json` 維持 `record.sh` 單一寫者。
- R2-Q5：使用者原話「全面更新子指令」：接受 CLI 表面的語意變更，新子指令（pause／resume／mute／unmute／mark）比照 `help` 列為保留字，並全面更新 CLI 封閉清單（`spec.md §2.4`）、`surface.py`、usage、SKILL.md、README 與鍵集合測試的預期（屬使用者核准的測試修改，記 `spec.md §6`）。
- 閘門 1：核准。

---

## R3 第三輪（2026-10-13）

- 性質：第三輪（R3）增補，**另走 R3 的閘門 1 核准**；本節以上的第一輪（第 1–176 行）與 R2（第 180–308 行）原文不動，仍以各自的核准為準。本節推翻的既有定案逐條列在 R3-3〈要推翻或改寫的既有定案〉。
- 調研依據（本機、不在版控）：`_tpm/runs/20261010-sdlc-meeting-record/` 的 `r3-research-synthesis.md`（收斂結論，簡寫 `syn`），細節查同目錄 `r3-research-sync.md`（`sync`）、`r3-research-transcript.md`（`tr`）、`r3-research-features.md`（`feat`）、`r3-research-ui.md`（`ui`）、`r3-research-quality.md`（`q`）。引用格式為「簡寫 §節」或「簡寫:行」。
- 使用者決定：2026-10-13 由主 session 轉述（派工單「使用者已做的決定」1–4），本節照寫，以下簡寫「使用者決定 1–4」。
- 程式行號：調研在 `3ab9df3` 做。R3 的起點是 origin/main 的 `377dd92`；`feature/meeting-record-r3` 在起點之上另有 intent 的 commit，只改 `specs/meeting-record/intent.md`、不動程式（`git diff --stat 377dd92 HEAD`）。`3ab9df3` 到 `377dd92` 共 12 個檔，每檔都是同數量的單行替換、行數沒有位移（`git diff --numstat 3ab9df3 377dd92`），所以報告裡的程式與 spec 行號可以沿用；本節自己查證後更正的行號（例如 `bin/record.sh` 的 `write_defaults`）以本節為準。
- 代號：T／Q／S／U／F／D 開頭的代號（T1、Q9a、S-A、U4、F2、D5 等）沿用 `syn` 的對照標籤，R3-Qx 只供本節內引用，**都不是任務編號**。子任務一律用描述性 slug。
- 範例名稱一律用「[Stand-up] 範例專案」；實機場次只用 run 代號（例如 0145）；本節不寫任何真實客戶、組織、會議或視窗標題。

### R3-1. 問題

R2 交付並經 t7 實機驗收之後（`run.json` 的 `r2-test` 註記「sync 判讀為播放端延遲，改善列 R3」），調研在五個面向找到四類問題：

1. **錄壞了也不知道的競態與卡死**（`q` ★1–★5，信心 0.8–0.85）：
   - 開錄沒有互斥，preflight 期間第二次開錄也會通過（★2，`Capture/Commands.swift:130-131`）。
   - `record.status.json` 會被其他實例覆寫；暫停中被覆寫後就無法繼續（★1，`RecordingSession.swift:181`、`:641`）。
   - 收尾沒有逾時、不能取消，ffmpeg 卡住時錄製器永遠不結束（★3，`_record_finalize.py:153-169`；`RecordingSession.swift:819`、`:953-964`）。
   - 同一場次可以同時跑兩個收尾，彼此破壞（★4，`_record_finalize.py:685-687`）。
   - `stop` 沒有確認 pid 屬於錄製器，pid 被重用時會 SIGTERM 到無關程序（★5，`record.sh:546-567`）。
2. **逐字稿品質從源頭就有缺口**：
   - 產 VTT 時忽略聲紋的 `apply` 旗標，cos 0.70–0.75 的講者會被掛成真名，違反鐵則 3（`tr` §3(6)；`bin/_render.py:246-262`；`.claude/teams/rules.md:64`）。
   - 靜音段整段送進 ASR 會產生迴圈。用 levels 做 VAD 只送有聲區間，0141 場次實驗的迴圈從 5 處降到 0 處（`tr` §2.2）。
   - `run_diarize` 會刪掉 raw 後重轉（`bin/meeting.sh:247`）；`--compression-ratio-threshold` 沒有作用（`tr` §3(5a)）。
   - 暫停、靜音、標記在逐字稿裡看不到（`tr` §3(2)、§3(4)）。
3. **錄製中的狀態看不清楚**：t7 時選單列圖示看不到，使用者連按快捷鍵 9 次（`spec.md:1358-1360`，§6 第 105–107 條）。準備中與收尾中也用紅點；錄製中的告警完全不發通知（`ui` §1 P0-3、P0-4、P1-1、P1-2）。選單是 18 項扁平清單、全部灰掉不隱藏（`spec.md:1255`，§4.20.6；`ui` §3.3）。沒有首次使用引導，只用選單列 app 的人要先在終端機跑一次 `meeting record` 才能開錄（`ui` §3.7，P1-4）。也沒有 app 圖示（`ui` P2-3）。
4. **影音一致沒有可信的量法**：t7 的「藍牙 +80／內建 −45 ms」是 ffplay 加上裝置切換歷程的結果，不能拿來推算真實會議 app 的偏移（`sync` §0 第 3 點）。一手證據顯示，SCK 系統聲音的 PTS 約等於 render 時間，不含輸出裝置延遲：內建喇叭的聲學回授 mic − sys 為 25–26 ms，三個時段各 19–29 組（`sync` §2.3）。以此推論，戴藍牙 A2DP 開會補償延遲的播放端時，成品的聲音會比畫面早約 150–185 ms，超過 ITU-R BT.1359 的 90 ms 門檻（`sync` §0 第 4 點，推論、未實測）。

另外，會前會後有三個缺口：不想要的錄製只能等收尾跑完再手動刪（`feat` §3.3）；會議開始時沒有任何提示（`feat` §3.1）；`actions.ics` 能不能匯入提醒事項沒有一手依據（`feat` §3.6）。

### R3-2. 期望結果

**範圍（使用者決定 1）**＝`syn` §1.1 的核心 18 項 ＋ UI 全面重設計（U4–U7）＋ 會前會後功能（F2、F3、F5）＋ 影音一致的分層做法（使用者決定 2）。

#### 做

| 群組 | 代號 | 使用者看得到的結果 | 大小 | 依據 |
|---|---|---|---|---|
| 錄製穩定 | Q1＋Q2 | 同時只會有一個錄製實例；第二次開錄直接被拒，而且不會碰狀態檔；暫停中狀態檔仍有低頻心跳 | M | `syn` §1.1 第 2 列；`q` ★1、★2 |
| | Q4 | 同一場次的收尾互斥；暫存檔改用 `mkstemp` | S | `syn` 第 3 列；`q` ★4 |
| | Q5 | `stop` 只會把 SIGTERM 送給錄製器本身 | S | `syn` 第 4 列；`q` ★5 |
| | Q3 | 收尾有上限、可以取消；逾時回 5 並保留段落 | M | `syn` 第 5 列；`q` ★3 |
| 逐字稿 | T1 | VTT 的講者歸屬和 `speakers.md` 用同一套規則，聲紋 < 0.75 不掛名 | S | `syn` 第 1 列；`tr` §3(6) |
| | T2 | `run_diarize` 不再刪掉 raw 重轉 | S | `syn` 第 6 列 |
| | T3 | 移除沒有作用的參數，並更正 meeting-transcribe SKILL.md | S | `syn` 第 7 列 |
| | T4 | 用 levels 的有聲區間組成 `clip_timestamps`，靜音段不送 ASR；ingest 進來的舊檔退回現行做法；raw 標頭記下 clip 參數 | M | `syn` 第 8 列；`tr` §2.2 |
| | T5 | 逐段品質檔 `transcript.quality.json`，衍生檔標「（聽不清）」；`QUALITY_WARNING` 原格式保留 | S | `syn` 第 9 列 |
| | T6 | 暫停、麥克風靜音、長靜音、裝置切換標進 `speakers.md`、vtt 與總結（只寫衍生檔，raw 不動） | M | `syn` 第 15 列；`tr` §3(4) |
| | T7 | 標記對齊逐字稿；`meeting.record.json` 加選用 `markers[]`，summary 加「## 標記」 | M | `syn` 第 16 列；`tr` §3(2) |
| | Q9a | `bin/_record_lib.py` 最小版（`output_time`、`paused_total`、levels 區間），Swift 與 Python 共用一份測試向量 | S–M | `syn` 第 18 列；`q` ★9 |
| | F1 | `meeting search <根> <關鍵字>`，只搜單一根目錄 | S | `syn` 第 17 列；`feat` §3.7 |
| 狀態可見 | U1 | 選單列圖示 8 種外觀，只看形狀就分得出來；準備中與收尾中不再用紅點 | S | `syn` 第 10 列；`ui` §3.2 |
| | U3 | 通知分級：錄製中告警用 Time Sensitive；同一場的通知以 `threadIdentifier=runId` 分組 | S | `syn` 第 11 列；`ui` §3.6 |
| | U2 | 錄製中浮動小窗 HUD（紅點、計時、兩格音量條；滑鼠移上去出現暫停／靜音／標記／停止）；快捷鍵回饋改顯示在 HUD | M | `syn` 第 12 列；`ui` §3.4 |
| UI 重設計（使用者決定 1） | U4 | 首次使用引導（權限、存檔位置與 harness、選單列空間、快捷鍵與試錄） | M | `ui` §3.7 |
| | U5 | 設定視窗改成工具列分頁 | M | `ui` §3.5 |
| | U6 | 選單依階段（待機／錄製中／收尾或失敗）顯示；收音改成即時音量條；失敗改成詳情小視窗 | M | `ui` §3.3 |
| | U7 | app 圖示 | S | `ui` P2-3、§4.2 D12 |
| 會前會後（使用者決定 1） | F2 | 選單「捨棄這次錄製…」＋確認對話框：停止後不收尾，場次資料夾移到垃圾桶（可復原） | M | `feat` §3.3 |
| | F3 | 偵測到麥克風正在被使用時，發「錄這個會議？」通知；**只提示，不自動開錄**；按鈕走既有 quick-start | M | `feat` §3.1 |
| | F5 | 交辦用 EventKit 寫進提醒事項，以 UID 去重、可重跑；負責人或期限缺值就照實留空 | M | `feat` §3.6 |
| 影音一致（使用者決定 2） | S-A | `e2e_check.py --sync-acoustic`（mic − sys 聲學回授）；sync 判準改成按時段取中位數；產生給補償型播放端（QuickTime／Chrome）用的同步檔 | S | `syn` 第 13 列；`sync` §6 第 1 點 |
| | S-B | 開錄時與每次 deviceEvent 時，唯讀記錄輸出裝置延遲（Latency、SafetyOffset、stream Latency、BufferFrameSize、NominalSampleRate）到 `record.meta.json`；延遲欄位**不能放進 Equatable 比較的結構**，要另外放一個物件 | S | `syn` 第 14 列；`sync` §6 第 2 點；`AudioDeviceMonitor.swift:51-55`、`:84` |
| | S-C | finalize 依時段把系統聲音軌延後 L_out；開關 off／reported／calibrated，**預設 off**；輸出裝置變更時也提前換段；`finalize.json` 記下每段實際套用的延遲；要寫新 ADR。排在最後一層，預設要不要開由 R3 實機驗收場 E2／E4 的結果決定 | M | `sync` §3、§6 第 3 點；`syn` §1.2 |

UI 重設計的流程（使用者決定 1）：U4–U7 的畫面（U6 本來就在其中；對應 `ui` §4.2 的 D2–D6、D9 為 U6，D8 為 U5，D10 為 U4，D12 為 U7），先用 Claude Design 依 `ui` §4（共通規格、畫面清單、驗收要點）出設計稿，**在 design 段由使用者挑選**，挑定的稿才寫進 spec。U1（選單列圖示 8 種外觀，`ui` §4.2 D1）與 U2（HUD，D7）要不要也走設計稿，列為閘門 1 待決問題 R3-Q8；U3 的通知（D11）只定文字與動作、外觀用系統原生，照 spec 文字做。設計稿裡的範例資料同樣只能用「[Stand-up] 範例專案」與通用 app 名稱（`ui` §4.1）。

**長期方向**（使用者決定 2；`syn` D2 的 A）：成品要重現使用者當下看到與聽到的時間關係。R3 的順序是「先量測、再補償」，S-A、S-B 先做，S-C 最後做。

**可以判定的成果**（細節由 design 段寫成 spec 的 EARS 驗收條件）：

- 自動：Swift Core 與 Python 單元測試涵蓋開錄鎖（第二個實例拿不到鎖時不寫狀態檔）、收尾鎖與逾時、`stop` 的 pid 確認、VTT 與 `speakers.md` 講者歸屬一致（0.70–0.75 不掛名）、`output_time` 共用測試向量、VAD clip 區間、品質檔、標記與暫停的標示、`meeting search`、`MenuBarState` 8 種外觀、S-B 的延遲欄位不影響 deviceEvent 判斷、S-C 三種開關模式（off 時不套用任何延遲；但「輸出裝置變更時提前換段」會改變段落切分，所以 off 時只要求成品的音畫內容和現行等價，檔案切分可能不同，**不宣稱逐位元相同**；「等價」的判準由 design 段定，在 test 段驗證）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` 全綠（`CLAUDE.md`〈專案特定〉）。
- 下游相容：`summary.md` 加「## 標記」後，四段與 `一句話：` 不變，並用下游知識庫專案的 `meetings._missing_sections()` 驗過（`.claude/teams/rules.md:67`）。
- 實機（R3 實機驗收場，一場，使用者在場；`syn` §2 第 11 點、D13）：依序做 E4 聲學回授、E2 補償型播放端、HUD 的 `sharingType`、Time Sensitive 原型、`.ics` 匯入與 F5 的 EventKit 寫入提醒事項、F3 偵測提示、F2 捨棄後資料夾在垃圾桶、首次引導；再用 `keep-segments` 錄一場真實多人會議，用來調 T4 的門檻，也當雙軌實驗素材（使用者決定 3）；最後做全套 e2e 迴歸。這份清單和 R3-4 第 9 點、D13、R3-7、R3-8 的 `r3-field-check` 寫法一致。

#### 不做（本輪）

| 項目 | 理由 | 依據 |
|---|---|---|
| T8 另存兩軌（D8 取 A） | 使用者決定 3：不另存；實機驗收場另用 `keep-segments` 錄一場做雙軌實驗 | 使用者決定 3；`syn` §2 第 2 點 |
| 雙軌能量差做「我方／對方」歸屬 | 延後；依賴雙軌實驗的結果 | 使用者決定 3；`tr` §3(1) |
| 即時／近即時轉錄（D16 取 A） | 使用者決定 4 | 使用者決定 4；`tr` §3(3) |
| T9 術語 prompt（D10 取 C） | 使用者決定 4；要等 T4 穩定，而且用全域術語表會跨客戶串用 | 使用者決定 4；`tr` §3(5c) |
| Q7 收尾效能、Q8、Q9b、Q10 拆檔 | `syn` §1.2 列為可選，使用者未選；Q10 在 UI 子任務期間會和 MenuBar.swift 衝突 | `syn` §1.2、§2 第 7 點 |
| F4 捷徑自動化教學、F6 會後一句話摘要、F7 會議結束提示 | 使用者在 D15 選 F2＋F3＋F5，這三項未選 | 使用者決定 1；`syn` §1.2 |
| 行事曆會前提醒（EventKit 讀行事曆） | 事件標題含客戶名稱，不能寫進 log 與狀態檔；F3 只讀麥克風狀態，不需要行事曆 | `syn` §1.3；`feat` §3.1 |
| 靜默自動開錄、開錄倒數、選麥克風 UI、推送到手機或寄 email、跨根目錄搜尋 | 同意與隱私、R2 定案、不可逆的對外寄送、客戶資料邊界 | `syn` §1.3；`feat` §5 |
| 錄製中重新打戳、整檔 `-itsoffset`、`hallucination_silence_threshold`、`ControlWidget` | 會改到 raw 段落或只能整檔平移；內容流失；打包改動大 | `syn` §1.3；`sync` §3 |
| Q6 抽出 `SegmentScheduler` | **待決**（R3-Q1）：S-C 依賴它 | `syn` §1.2；`q` ★6 |

### R3-3. 受影響的使用者與系統

**使用者**：本機唯一使用者（會議主持人兼紀錄者），以及透過 `bin/meeting.sh` 與 `~/.claude/skills/meeting-*` 呼叫錄製與前處理的其他 session（`CLAUDE.md`〈對外介面〉；`.claude/teams/rules.md:68`）。F2 的刪除只對使用者本人在 UI 上的確認生效。

**對外契約面**（本 repo 沒有服務；契約全是本機介面）：

| 契約面 | R3 的變化 | 依據 |
|---|---|---|
| `meeting` CLI | 新增 `meeting search`；新子指令依 R2-Q5 先例列保留字，並更新 CLI 封閉清單、usage、SKILL.md、README；既有子指令與結束碼不改 | `syn` 第 17 列；本檔第 307 行 |
| `meeting record preflight` 在錄製中的行為 | 預設採用 D14b-A 時，錄製中直接回 2，不跑 13 項檢查、不碰狀態檔 | `syn` D14 |
| `~/.meeting-harness/record.lock`（新） | 錄製實例與 `record.sh` 共用的開錄鎖 | `syn` 第 2、4 列 |
| `~/.meeting-harness/record.status.json` | 可能加心跳時間（選用欄位） | `syn` §2 第 8 點 |
| `~/.meeting-harness/record.defaults.json` | 第二個寫者：app 只能在首次引導寫 `harness` 與預設根目錄兩個鍵，用 flock＋tmp＋rename；`record.sh` 的 `write_defaults` 目前是整檔覆寫（只寫自己的 7 個鍵，`bin/record.sh:329-341`，呼叫點 `:460`），要改成拿同一把鎖、讀後合併寫入（R3-Q5）。S-C 的開關（off／reported／calibrated）也放這個檔，但由 CLI 寫，app 不寫 | 使用者決定 1（D6-A）；`sync` §6 第 3 點；`bin/record.sh:329-341`、`:460` |
| 場次 `record.meta.json` | S-B 新增輸出延遲的選用欄位 | `syn` 第 14 列 |
| 場次 `finalize.json` | S-C 記下每段套用的延遲；D12 預設採用時記下讀不到的段落（搬到 `tracks/unreadable/`，由 `r3-finalize-guard` 承接） | `sync` §6 第 3 點；`syn` D12 |
| 場次 `transcript.quality.json`、`segments.json`（衍生檔） | 新增；`segments.json` 一律輸出 | `syn` 第 9 列 |
| `schema/meeting-record.v1.json` | 加選用 `markers[]`（D11 預設採用 A） | `syn` D11；`schema/meeting-record.v1.json:164-170` |
| `summary.md`、`transcript.vtt`、`transcript.speakers.md` | 新增「## 標記」段與暫停、靜音的標示；五個必備段不動 | `syn` 第 15、16 列 |
| 提醒事項（EventKit，新） | F5 寫入；需要提醒事項的 TCC 權限；清單開了 iCloud 同步時，內容會離開本機 | `feat` §3.6 |
| 垃圾桶（新） | F2 把場次資料夾移到垃圾桶 | `feat` §3.3 |

**要推翻或改寫的既有定案**（design 段寫明，並記入 `spec.md §6`〈整合修訂與例外〉）：

1. **R2「明確在範圍外」的「會議自動偵測」與「捨棄這次錄製」**（本檔第 295 行）→ 使用者決定 1 推翻，改做 F3（只提示、不自動開錄）與 F2。「行事曆提醒」維持在範圍外。
2. **R2-Q3「`record.defaults.json` 維持 `record.sh` 單一寫者」**（本檔第 278、306 行）→ 使用者決定 1（D6 取 A）推翻，app 只能在首次引導寫兩個鍵（見上表）。
3. **`spec.md §4.20.6`「不能用的項目灰掉不隱藏」**（`spec.md:1255`）→ 使用者決定 1（D5 取 A）改成依階段顯示。`test_r2_static.py::test_trigger_menu_items_r2` 的預期要跟著改，屬於使用者核准的測試修改（`.claude/teams/rules.md:37`）。
4. **`spec.md §6` 第 105、106 條**（快捷鍵回饋走通知、圖示被擋住只發一次通知；`spec.md:1358-1359`）→ U2 上線後改成「HUD 與圖示都看不到時才發通知」，圖示被擋住的偵測改成持續進行（`syn` §2 第 5 點）。
5. **`spec.md §4.9.3` 的 sync 判準**（`spec.md:708`：每個閃白與嗶聲的差都 < 100 ms）→ D3 預設採用 A 時改寫（R3-6 的 D3）。
6. **`spec.md §6` 第 111 條「收尾成功後刪段落」**（`spec.md:1364`）→ D12 預設採用 A 時，讀不到的段落改成保留到 `tracks/unreadable/`（R3-6 的 D12）。由 `r3-finalize-guard` 承接：刪段落的程式在 `bin/_record_finalize.py`，和 Q4、Q3 的 Python 端同一支檔（`syn` §2 第 2 點）。
7. **`MenuBarState` 與 spec §3.4.1 的圖示外觀** → U1 改成 8 種；既有靜態測試的預期要改（`syn` 第 10 列）。
8. **既有測試「鍵集合恰為 N 個」**（`RecordsTests.swift:58`、`:112-113`）→ S-B 與 Q1 的心跳碰到時，照 R2-Q10 與 `adr/adr-r2-status-fields.md` 的先例處理（`syn` §2 第 8 點）。
9. **D20 的「逐段正規化、串接時一次編 AAC」流程**（`adr/adr-segment-writer.md`；`design.md:307-311`）→ S-C 的段落邊界補償會動到它，要寫新 ADR（`sync` §6 風險第 4 點）。

**要改的既有檔**（主要；完整清單由 design 段逐子任務列出，`syn` §4）：`bin/_render.py`、`bin/_merge_speakers.py`、`bin/meeting.sh`、`bin/transcribe.sh`、`bin/record.sh`、`bin/_record_finalize.py`、新增 `bin/_record_lib.py` 與 `bin/_search.py`、`schema/meeting-record.v1.json`、`tools/MeetingRecorder/Sources/` 的 `Capture/Commands.swift`、`PreflightRunner.swift`、`RecordingSession.swift`、`AudioDeviceMonitor.swift`、`Core/Trigger.swift`、`Trigger/MenuBar.swift`、`Notifier.swift`，新增 HUD、引導、設定分頁與 EventKit 的來源檔、app 圖示資源、`tests/record/e2e_check.py`、`.claude/skills/meeting-*/SKILL.md`、`README.md`，以及 `specs/meeting-record/` 的 design、spec、plan、progress 與 ADR。

### R3-4. 限制

1. **對外介面不得破壞性變更**：`bin/meeting.sh` 的子指令與結束碼、`~/.claude/skills/meeting-*`（`.claude/teams/rules.md:68`）。新增子指令照 R2-Q5 先例（本檔第 307 行）。狀態檔不加新的 `RecordPhase` 或 `WarningKind` case（本檔第 252–253 行）。
2. **五條鐵則不變**（`.claude/teams/rules.md:62-66`）：
   - T4 只改送進 ASR 的範圍，T6、T7 只寫衍生檔，raw 不動。
   - T1 修的就是鐵則 3。
   - F5 缺負責人或期限時照實留空，不補猜。
3. **刪資料是不可逆節點**（`CLAUDE.md`〈不可逆節點〉）：
   - F2 只能由使用者本人在 UI 確認後執行，而且是移到垃圾桶，不是硬刪。
   - 沒有 tty 的 session 呼叫時一律拒絕（`feat` §3.3）。
4. **F3 只讀狀態**：
   - 不能為了偵測去開麥克風，否則藍牙會切到 HFP（`feat` §3.1）。
   - 要排除本工具自己的 preflight。
   - 只提示、不自動開錄（使用者決定 1）。
5. **F5 的資料邊界**：
   - 只寫進使用者指定的提醒事項清單。
   - 說明裡要明講「清單開了 iCloud 同步時，內容會離開本機」（`feat` §3.6）。
   - 只同步該場紀錄自己的交辦，不跨客戶根目錄（`CLAUDE.md`〈客戶資料邊界〉）。
6. **S-C 預設 off**：方向或大小錯了，偏移會加倍；E2／E4 沒有證實之前不能預設開（`sync` §6 風險第 1 點；使用者決定 2）。off 時不套用任何延遲；「輸出裝置變更時提前換段」會改變段落切分，所以 off 時只要求成品的音畫內容和現行等價，檔案切分可能不同，不要求逐位元相同。等價的判準由 design 段定，在 test 段驗證。
7. **S-B 只讀**：
   - 不改變預設裝置（`spec.md §4.9.4`）。
   - 延遲欄位不能讓 A2DP↔HFP 切換多出 deviceEvent（`AudioDeviceMonitor.swift:84`）。
8. **public repo**：
   - specs、tests、設計稿、範例都不得含真實客戶、組織、會議或視窗標題；範例一律用「[Stand-up] 範例專案」。
   - HUD 與錄製中的通知預設不露出場次名或視窗標題（`ui` §4.3）。
   - 每次 commit 前用 `client-names.txt` 掃描 staged diff，只回報「有／沒有」，不印出比中的內容。指令一律用絕對路徑，並把 git 與 grep 的結束碼分開看（管線只會回 grep 的結束碼，git 失敗會被吃掉）：

     ```bash
     R=/Users/yuktang/Documents/Agent/meeting-harness
     D=$(mktemp); git -C "$R/.worktrees/meeting-record-r3" diff --cached >"$D"; g=$?
     grep -qiF -f "$R/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt" "$D"; s=$?
     rm -f "$D"; echo "git=$g grep=$s"
     ```

     判讀：`git` 不是 0（例如 128）＝git 出錯，要重跑；`grep=0`＝有，`grep=1`＝沒有，`grep=2` 以上＝grep 出錯（例如清單檔不存在），要重跑，不能當成「沒有」。子任務 worktree 把 `-C` 的路徑換成該 worktree 的絕對路徑。
9. **subagent 的實機限制**：
   - 不得啟動 MeetingRecorder、不得觸發 TCC 授權框、不得改系統設定、不得寫 `~/.meeting-harness`、不得改 `~/Applications`。
   - 下列項目只能由使用者在 R3 實機驗收場（一場）做：E4、E2、HUD 的 `sharingType`、Time Sensitive、`.ics` 匯入與 F5 的提醒事項權限和 EventKit 寫入、F3 偵測、F2 捨棄後資料夾在垃圾桶、首次引導、`keep-segments` 的真實多人會議，最後全套 e2e 迴歸（同 R3-2〈可以判定的成果〉的實機清單）。
10. **檔案熱點要序列化**（`syn` §2 第 1、7 點；和 R3-8 的分層一致）：
    - `_record_finalize.py`：Q4、Q3 的 Python 端、D12（同一個子任務）→ S-C。
    - `RecordingSession.swift`：Q1 → Q3 Swift 端 → S-B → F2 →（Q6，R3-Q1 選 A 時）→ S-C。
    - `MenuBar.swift`：Q5（`stop` 的 pid 確認，`MenuBar.swift:428-431`）→ U1 → U3 → U2 → F2 → U6 → U4、U5、U7 →（F3，若要改這支檔）。
    - `_render.py`／`_merge_speakers.py`：T1 → T6、T7 →（F5，若抽出 `_render.py:212` 的 UID 組法共用）。
    - `bin/meeting.sh`：T2 → F1 → F5 的 CLI 入口。
    - `Resources/Info.plist`：F5（提醒事項權限說明）→ U7（app 圖示）。
11. **測試失敗改程式、不改測試**：R3-3 列出的既有測試預期修改（§4.20.6 選單、§6 第 105–107 條、`MenuBarState`、鍵集合、sync 判準），都要使用者核准，並記在 `spec.md §6`（`.claude/teams/rules.md:37`）。
12. **流程**：
    - R3 的 epic 分支是 `feature/meeting-record-r3`（從 origin/main `377dd92` 開出）；子任務分支一律 `feature/meeting-record-r3--<slug>`，各開 worktree（`CLAUDE.md`〈commit 與分支〉的 `feature/<epic>--<sub>`）。`syn` §4 寫的 `feature/meeting-record--<sub>` 是 R2 的命名，R3 不用。
    - 不 push、不改 `main`。
    - R3 的閘門紀錄沿用 R2-Q2 的先例，用 `r3-` 前綴的 stage 鍵（本檔第 305 行）。這是預設採用，閘門 1 可以改。

### R3-5. 假設（未能確認，帶進 design 與實機驗收）

依據 `syn` §5。

1. SCK 系統聲音的 PTS 在藍牙輸出時是否仍然等於 render 時間，沒有確認。A2DP 與 HFP 的實測值和回報值方向相反，原因也沒有確認（`sync` §2.2、§2.4）。→ 由 E4 驗。S-C 的 `reported` 模式可能不可靠，`calibrated` 可能要做每顆耳機的校正表。
2. Teams 在 macOS 上是否補償輸出延遲沒有確認；Chromium 路徑的細節只是推論（`sync` §5）。→ 由 E2 驗。
3. 雙軌轉錄能不能提升 ASR 準確度，證據不足，只有一場 76 秒的測試音場次（`tr` §2.2）。→ 用驗收場的 `keep-segments` 實驗補。
4. 自簽憑證下能不能用 Time Sensitive，沒有確認（`ui` §3.6）。不行的話，錄製中的告警只靠 HUD 呈現。
5. `sharingType=.none` 能不能擋住其他 app 的螢幕分享，沒有確認（`ui` §3.4）。
6. `actions.ics` 的 VTODO 能不能匯入提醒事項，只有二手來源（`feat` §3.6）。F5 改走 EventKit，不依賴這一點。EventKit 的 API 名稱與 plist key 由 design 段查一手文件確認。
7. 會議視窗在錄製中被關掉時，錄製器的結束碼與收尾行為沒有確認（`feat` §4）。
8. 收尾耗時的分布是用 mtime 推估的，不夠精確（`q` ★7）。這會影響 D14 逾時上限的合理性。
9. `NSMenuItem.view` 自訂收音列在 macOS 26 的鍵盤導覽與 VoiceOver 行為，沒有確認（`ui` §3.3）。要先做原型。

### R3-6. 待決問題

#### 交閘門 1 決定（R3-Q1、R3-Q8，附選項與代價）

| # | 問題 | 選項與代價 | 建議 | 依據 |
|---|---|---|---|---|
| R3-Q1 | Q6（抽出 `SegmentScheduler`，並用假 writer 補行為測試）要不要納入 R3？S-C 的「輸出裝置變更提前換段」要改錄製熱路徑，而 `RecordingSession` 的編排邏輯目前只有靜態字串檢查 | A. 納入：多一個大小 L 的子任務 `r3-segment-scheduler`，插在 `RecordingSession.swift` 序列鏈的 F2 與 S-C 之間，S-C 要等它合併；大幅重構熱路徑，要用全套 e2e 重新驗收／B. 不納入，S-C 直接在 `RecordingSession.swift` 加換段觸發：少一個 L 子任務、序列鏈短一節，但熱路徑的改動沒有行為測試保護，回歸只能靠實機 e2e／C. 不納入，S-C 也延到下一輪，R3 只做 S-A、S-B：和使用者決定 2「S-C 排最後一層」不一致，要使用者改決定 | **A**（`syn` 註明「R3 要做 S-C 的話，Q6 要先做」） | `syn` §1.2 Q6 列；`q` ★6；使用者決定 2 |
| R3-Q8 | U1（選單列圖示 8 種外觀，`ui` §4.2 D1）與 U2（HUD，D7）要不要也走 Claude Design 設計稿？使用者決定 1 只點名 U4–U7 | A. 只有 U4–U7 走設計稿，U1、U2 照 spec 文字（`ui` §3.2、§3.4）先做。代價：圖示與 HUD 沒有視覺驗收依據；U4–U7 的稿定調之後，圖示與 HUD 的風格可能要回頭改／B. U1、U2 也走設計稿。代價：design 段多挑 D1、D7 兩組稿，U1、U2 的 spec 要等稿挑定才能寫；`r3-menubar-states` 固定排第 1 層（選 A 時，若接受和 `r3-lock` 在 `Core/Trigger.swift` 的合併衝突，可以提前到第 0 層） | **B**：t7 的主要問題就是圖示看不到（`spec.md:1358-1360`），HUD 是錄製中最常看的畫面；和 U6 的選單一起定調，可以避免回頭改 | 使用者決定 1；`ui` §3.2、§3.4、§4.2；`syn` §4 第 0 層 `r3-menubar-states` 列 |

#### 預設採用，閘門 1 可改

| # | 問題 | 預設採用 | 其他選項與代價 | 依據 |
|---|---|---|---|---|
| D3 | `spec.md §4.9.3` 的 sync 判準要不要改 | **A**：補償型播放端按時段取中位數，\|d\| < 45 ms；ffplay 只用來驗錄製器沒有引入額外偏移；和 S-A 一起做。代價：要改 spec 與 `e2e_check` 的既有預期（需要核准） | B 維持 ffplay、全片最大值 < 100 ms。代價：0145 的 159 ms 這類離群值與裝置切換歷程會繼續造成誤判 | `syn` D3；`spec.md:708` |
| D4 | HUD 預設怎麼顯示 | **A**：自動，偵測到圖示被擋住才顯示，設定裡可以改成一律顯示。代價：依賴偵測的準確度 | B 一律顯示。代價：每場都多一個浮窗，分享整個螢幕時別人看得到／C 不做 HUD。代價：和範圍內的 U2 衝突，Time Sensitive 也未確認 | `syn` D4；`ui` §5 第 1 題 |
| D7 | 快捷鍵要不要開放自訂 | **A**：R3 不開放；U5 的快捷鍵分頁只顯示、不能改。代價：被別的 app 占用時仍然只能寫 log | B 開放。代價：`r2HotKeys`、SKILL.md、README 的固定字串都要改 | `syn` D7 |
| D9 | 「我方（本機麥克風）」能不能直接掛使用者本人的名字 | **A**：不行，一律顯示「我方（本機麥克風）」，`voiceprint add` 確認後才掛名。雙軌歸屬延後，這題實際上也延後 | B 直接用本人姓名。代價：共用麥克風或喇叭外放時違反鐵則 3 | `syn` D9；`.claude/teams/rules.md:64` |
| D11 | markers 怎麼進 schema | **A**：v1 加選用欄位 `markers[]`，summary 加「## 標記」，五個必備段不動。代價：要過下游知識庫專案的相容檢查 | B 升 v2。代價：下游都要改 | `syn` D11；`.claude/teams/rules.md:67` |
| D12 | 讀不到的段落（skipped）收尾後要刪還是留 | **A**：保留，搬到 `tracks/unreadable/`，並寫進 `finalize.json`；由 `r3-finalize-guard` 實作。代價：要改 `spec.md §6` 第 111 條的字面寫法 | B 照現行全部刪除。代價：可能用其他工具救回的檔會被永久刪掉 | `syn` D12；`q` 第 11 項；`spec.md:1364` |
| D13 | R3 實機驗收場怎麼安排 | **A**：一場實機驗收，使用者在場，依序做 E4、E2、HUD 的 `sharingType`、Time Sensitive、`.ics` 匯入與 F5 的 EventKit 寫入、F3 偵測、F2 捨棄、首次引導，再錄一場 `keep-segments` 的真實多人會議，最後全套 e2e 迴歸；排在 S-C 預設決定之前 | B 只做 E4 與 HUD，VAD 門檻用測試場次調。代價：門檻可能不適合真實會議；S-C 的預設也沒有 E2 可以依據；F5、F3、F2、首次引導沒有實機驗收 | `syn` D13、§2 第 11 點 |
| D14a | 收尾逾時上限 | **A**：「錄製長度 ×3＋10 分鐘」，逾時回 5 並保留段落 | B 不設上限，只能取消。代價：ffmpeg 卡住時仍然要手動處理 | `syn` D14 |
| D14b | 開錄鎖要不要也擋 `meeting record preflight` | **A**：擋，錄製中直接回 2，不跑 13 項檢查、不碰狀態檔。代價：preflight 在錄製中的行為改變（t6 測過「錄製中再跑 preflight」），既有預期要調整 | B 不擋，但不寫狀態檔。代價：錄製中跑 preflight 仍會開麥克風與 SCK | `syn` D14 |
| — | R3 的閘門紀錄 | `run.json` 用 `r3-` 前綴的 stage 鍵，同一個 run 目錄 | 另開 run 目錄。代價：調研報告要搬或連結 | 本檔第 305 行（R2-Q2 先例） |

#### 留給 design 段定案（附建議，不阻斷）

| # | 待解 | 建議方向 | 依據 |
|---|---|---|---|
| R3-Q2 | F2 有沒有 CLI 對等子指令？ | R3 只在選單提供；CLI 不新增 `discard`，避免其他 session 刪資料。如果要加，就照 R2-Q5 列保留字，而且沒有 tty 時拒絕 | `feat` §3.3；本檔第 307 行 |
| R3-Q3 | F5 由哪個程序取得提醒事項權限？入口是 CLI 子指令還是 app？ | TCC 權限跟著 app bundle，建議由 MeetingRecorder.app 執行寫入，CLI 只觸發；需要 `NSRemindersFullAccessUsageDescription`（由 design 查一手文件確認） | `feat` §3.6 |
| R3-Q4 | F3 的偵測怎麼排除本工具自己的 preflight 與錄製？前景 app 不在 ★ 清單時要不要提示？ | 用 R3 的開錄鎖判斷「本工具正在用麥克風」；只在前景 app 屬於 ★ 清單時提示；同一場會議只提示一次 | `feat` §3.1；`syn` §2 第 9 點 |
| R3-Q5 | `record.defaults.json` 兩個寫者的鎖：`record.sh` 的整檔覆寫要不要改成合併寫入？ | 兩邊拿同一把 flock；`record.sh` 的 `write_defaults` 改成「讀、合併、tmp＋rename」，保留 app 寫的鍵。建議併入 `r3-lock`（同樣改 `record.sh`、同屬鎖），之後 U4 的 app 端與 S-C 的 CLI 開關都只沿用這個寫法 | `bin/record.sh:329-341`、`:460`；使用者決定 1（D6-A） |
| R3-Q6 | S-C 開關放在哪裡、`calibrated` 的校正值從哪裡來？ | 開關放 `record.defaults.json`，由 CLI 寫；`calibrated` 讀 E4 量出的每個裝置校正表（放 `~/.meeting-harness/`，不進 repo） | `sync` §6 第 3 點、風險第 2 點 |
| R3-Q7 | UI 設計稿怎麼進流程？Claude Design 的稿怎麼保存，才不會帶入真實名稱？ | 設計稿是 design 段的產出，不是 build 子任務：design 段開頭先出 U4–U7 對應的 D2–D6、D8–D10、D12（R3-Q8 選 B 時加 D1、D7），使用者挑定後存到 `specs/meeting-record/design-r3/`（存之前照 R3-4 第 8 點掃名稱）；被挑定的稿是 spec 的驗收依據 | 使用者決定 1；`ui` §4 |

### R3-7. 相對大小（不估工期）

`.claude/teams/rules.md:23`（第 8 條）禁止寫人天、人月與工時估算，本節不寫任何天數或時數，只列每個子任務的相對大小，供排序與拆分參考。各項目的大小照抄 `syn` §1.1、§1.2 的「大小」欄；子任務大小是由組成項目合併的推估：只有一個 S 為 S，多個 S 或一個 M 為 M，M 再加其他項目、或 `syn` 標 L 的為 L。`syn` 沒標大小的項目寫「未標」。

| 層 | 子任務 | 組成（`syn` 的項目大小） | 相對大小 |
|---|---|---|---|
| 0 | `r3-vtt-raw` | T1 S、T2 S、T3 S | M |
| 0 | `r3-record-lib` | Q9a S–M（含 L_out 換算的預留） | S–M |
| 0 | `r3-lock` | Q1＋Q2 M、Q5 S、R3-Q5 的 defaults 合併寫入（未標） | L |
| 0 | `r3-finalize-guard` | Q4 S、Q3 的 Python 端（Q3 為 M 的一部分）、D12（未標） | M |
| 0 | `r3-sync-measure` | S-A S | S |
| 1 | `r3-search` | F1 S | S |
| 1 | `r3-menubar-states` | U1 S | S |
| 1 | `r3-finalize-runner` | Q3 的 Swift 端（Q3 為 M 的一部分） | M |
| 1 | `r3-transcript-vad` | T4 M、T5 S | L |
| 1 | `r3-annotations` | T6 M、T7 M | L |
| 2 | `r3-latency-log` | S-B S | S |
| 2 | `r3-notify` | U3 S | S |
| 2 | `r3-reminders` | F5 M | M |
| 3 | `r3-hud` | U2 M | M |
| 4 | `r3-discard` | F2 M | M |
| 5 | `r3-menu-stages` | U6 M | M |
| 5 | `r3-segment-scheduler`（R3-Q1 選 A 時） | Q6 L | L |
| 6 | `r3-onboarding-settings` | U4 M、U5 M、U7 S | L |
| 6 | `r3-sync-compensate` | S-C M＋新 ADR | M |
| 7 | `r3-meeting-detect` | F3 M | M |

不在上表、也不是 build 子任務的兩件事：

- **UI 設計稿**（design 段）：Claude Design 出稿加上使用者挑選，大小 `syn` 未標；R3-Q8 選 B 時多 D1、D7 兩組。
- **R3 實機驗收場**（test 段，`r3-field-check`）：一場實機驗收，使用者在場，項目同 R3-2〈可以判定的成果〉的實機清單。本輪不寫時數：使用者在場的時間也是人力時間，屬第 8 條的範圍；而且 `syn` D13 的時數只涵蓋 E4、E2、HUD、Time Sensitive、`.ics` 與 `keep-segments`，加上 F5、F3、F2、首次引導與 e2e 迴歸之後已經無法回查。

決定經過時間的是序列鏈長度（R3-4 第 10 點），不是大小加總：最長的是 `RecordingSession.swift` 與 `MenuBar.swift` 兩條鏈。

### R3-8. 建議子任務分層摘要

依據 `syn` §4，並按使用者決定 1–2 補上 UI 重設計、會前會後與 S-C。`<slug>` 是描述性名稱，**不是任務編號**；子任務分支一律 `feature/meeting-record-r3--<slug>`，epic 分支是 `feature/meeting-record-r3`。分層原則：同一層的子任務不改同一支檔；改同一支檔的子任務依 R3-4 第 10 點的序列鏈排先後。最後的切分、檔案歸屬與完成條件，由 design 段在 intent 核准後定案。

**不是 build 子任務**：UI 設計稿屬於 design 段的產出（R3-Q7），在 design 段由使用者挑定、寫進 spec 之後 build 才開工，所以不列在下表；原草稿的 `r3-ui-design` 刪除。實機驗收屬於 test 段（`r3-field-check`，見表末）。

| 層 | slug | 內容 | 依賴（理由） |
|---|---|---|---|
| 0 | `r3-vtt-raw` | T1、T2、T3 | — |
| 0 | `r3-record-lib` | Q9a；`output_time` 要預留 S-C 的 L_out 換算參數（預設 0）：S-C 開啟後系統聲音在 wav 裡再晚 L_out，VAD 的錄製時鐘換成品時間要一起算進去（`syn` §2 第 3 點） | — |
| 0 | `r3-lock` | Q1、Q2、Q5；R3-Q5 的 `write_defaults` 合併寫入（建議） | — |
| 0 | `r3-finalize-guard` | Q4、Q3 的 Python 端、D12（讀不到的段落搬到 `tracks/unreadable/`，記入 `finalize.json`） | — |
| 0 | `r3-sync-measure` | S-A（含 D3 判準） | — |
| 1 | `r3-search` | F1 | `r3-vtt-raw`（同改 `bin/meeting.sh`：T2 改 `:247`，F1 改分派；`syn` §4 原列第 0 層，為了同層不改同檔移到第 1 層） |
| 1 | `r3-menubar-states` | U1（R3-Q8 選 B 時照挑定的稿） | `r3-lock`（同改 `Core/Trigger.swift` 與 `MenuBar.swift`） |
| 1 | `r3-finalize-runner` | Q3 的 Swift 端 | `r3-lock`（`RecordingSession.swift`）、`r3-finalize-guard`（收尾結束碼與逾時行為） |
| 1 | `r3-transcript-vad` | T4、T5 | `r3-record-lib`（`output_time`、levels 區間）、`r3-vtt-raw`（`bin/transcribe.sh`） |
| 1 | `r3-annotations` | T6、T7 | `r3-record-lib`、`r3-vtt-raw`（`_render.py`、`_merge_speakers.py`）。T5 的「（聽不清）」若也要改這兩支檔，design 段要把 T5 的那部分排到本子任務之後，不可同層平行 |
| 2 | `r3-latency-log` | S-B | `r3-finalize-runner`（`RecordingSession.swift` 序列鏈） |
| 2 | `r3-notify` | U3 | `r3-menubar-states`（`MenuBar.swift`、`Notifier.swift`） |
| 2 | `r3-reminders` | F5 | `r3-lock`（app 端入口在 `Capture/Commands.swift`）、`r3-search`（CLI 入口在 `bin/meeting.sh`，新子指令照 R2-Q5 列保留字）；若要抽出 `_render.py:212` 的 UID 組法共用，再加 `r3-annotations`（同改 `_render.py`）。原草稿寫的「交辦資料形狀」不成立：`actions[]` 已在 v1 schema（`schema/meeting-record.v1.json:74-91`），T7 只加 `markers[]` |
| 3 | `r3-hud` | U2（R3-Q8 選 B 時照挑定的稿），修 §6 第 105、106 條 | `r3-lock`（狀態檔可信）、`r3-menubar-states`、`r3-notify`（`MenuBar.swift` 序列鏈） |
| 4 | `r3-discard` | F2 | `r3-finalize-runner`（「停止但不收尾」的路徑）、`r3-latency-log`（`RecordingSession.swift` 序列鏈）、`r3-hud`（選單項目與確認框在 `MenuBar.swift`，不和 HUD 同層平行改這支檔） |
| 5 | `r3-menu-stages` | U6 | `r3-discard`（`MenuBar.swift` 序列鏈；U6 依階段排選單時把 F2 的項目放進「錄製中」階段） |
| 5 | `r3-segment-scheduler` | Q6（R3-Q1 選 A 時） | `r3-discard`（`RecordingSession.swift` 序列鏈的最後一個非 S-C 子任務）。改的檔是 `RecordingSession.swift`、新的 `SegmentScheduler` 來源檔與 Core 測試，不碰 `MenuBar.swift`、`Core/Trigger.swift`；同層的 `r3-menu-stages` 不改這些檔。design 段若發現它要碰任何 UI 子任務的檔，就移到 `r3-meeting-detect` 之後 |
| 6 | `r3-onboarding-settings` | U4、U5、U7（含 D6-A 的 app 端 defaults 寫入，沿用 `r3-lock` 的鎖） | `r3-menu-stages`（`MenuBar.swift` 序列鏈）、`r3-notify`（分頁內容）、`r3-reminders`（同改 `Resources/Info.plist`） |
| 6 | `r3-sync-compensate` | S-C，開關預設 off，加新 ADR；啟用 `r3-record-lib` 預留的 L_out 換算 | `r3-latency-log`、`r3-sync-measure`、`r3-finalize-runner`、`r3-finalize-guard`（`_record_finalize.py`）、`r3-record-lib`、（`r3-segment-scheduler`，R3-Q1 選 A 時；選 B 時改依賴 `r3-discard`） |
| 7 | `r3-meeting-detect` | F3 | `r3-lock`（排除本工具自己的 preflight）、`r3-notify`（`Notifier.swift`）；通知按鈕要接 quick-start 而改 `MenuBar.swift` 時，排在 `r3-onboarding-settings` 之後（`MenuBar.swift` 序列鏈末端）。只改新檔與 `Notifier.swift` 時可以提前到第 3 層 |
| test 段 | `r3-field-check` | 不寫程式，使用者在場：R3 實機驗收場（一場，項目同 R3-2 的實機清單）；結果寫進 run 目錄，並決定 S-C 的預設要不要開 | 全部 build 子任務合併後 |

平行度：第 0 層 5 個、第 1 層 5 個、第 2 層 3 個，之後每層 1–2 個。序列鏈見 R3-4 第 10 點；最長的兩條是 `RecordingSession.swift`（lock → finalize-runner → latency-log → discard →（segment-scheduler）→ sync-compensate）與 `MenuBar.swift`（lock → menubar-states → notify → hud → discard → menu-stages → onboarding-settings →（meeting-detect））。

### R3-9. 衍生工作（不編號）

- `bin/_profile.py:13`、`:30` 的註解疑似含真實組織名稱（`syn` §6）。在本 worktree 對 `bin/_profile.py` 分別用 `client-names.txt` 與 `name-candidates.txt` 跑 `grep -qiF -f <清單絕對路徑> <檔案絕對路徑>`，兩者結束碼都是 1（沒有；不是 2 以上的錯誤），可能已經在 main 處理過。design 段確認後就可以結案。
- status item 的 `autosaveName` 沒有設定，使用者拖動圖示後重開 app，位置會不會保留要驗證（`ui` §6）。可以併入 `r3-menubar-states`。
- 在 `_record_finalize.py` 的 `ffmpeg()`／`probe()` 加逐步計時 log（`q` §6）。可以併入 `r3-finalize-guard`，也能為 D14a 的上限提供依據。
- Swift 和 Python 同時寫控制檔的整合測試，`markerSeq` 不能掉號（`q` §6）。
- 設計審查 R2 還沒處理的 N-2、N-4、N-5、N-6，併入 UI 子任務（`ui` §6）。

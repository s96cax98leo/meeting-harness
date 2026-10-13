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

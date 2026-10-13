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

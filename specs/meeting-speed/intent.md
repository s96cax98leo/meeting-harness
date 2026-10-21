# intent：meeting-speed（停止錄製後 5 分鐘內就緒＋全專案重構）

- epic：`meeting-speed`；分支 `feature/meeting-speed`，從 `origin/main` @ `042c404` 開（PR #7 合併點，`git log --oneline -1 origin/main`）。
- 狀態：**草稿，待閘門 1 核准**。核准後本檔不再改；要改就回報主 session。
- 需求來源：使用者 2026-10-21 在對話裡口述（本 repo 沒有上層任務系統，`.claude/teams/rules.md` 專案規則「需求來源」）。原話（逐字，取自派工單）：
  > 重新 refactor 整個專案，問題都找出來，並且開一個一個的 task 讓 agent 完成。並且請考量效能問題，昨天 2 小時的會議，要 30 分鐘才能完成所有的工作，能在 5 分鐘內完成，轉換一下方法。
- 使用者已決定的三項（AskUserQuestion，2026-10-21）：`_tpm/runs/20261021-sdlc-meeting-speed/plan-approved.md:8-11`。
- 已核准的計畫與盤點：同 run 目錄的 `plan-approved.md`（133 行）、`b0-audit.md`（66 行；行號基準 `414b65c`，位移對照見 `research-code-contracts.md:8-17`）。
- 調研依據：同 run 目錄的 `research-requirement.md`、`research-specs-adr.md`、`research-code-contracts.md`、`research-upstream.md`。run 目錄不在版控（`.gitignore` 的 `/_tpm/runs/*`）。
- `specs/_templates/intent.md` 不存在（`ls specs/` 只有 `meeting-record`），本檔用 fallback 五節格式。
- 本檔裡的 G1–G9（目標）、Q1–Q5（待決問題）、C1–C10（衝突）只是本檔內引用，**不是任務編號**。
- 行號以 `042c404` 為準，可用 `sed -n '<行>p' <檔>` 重跑核對。範例場次名一律用「[Stand-up] 範例專案」。

---

## 1. 問題

### 1.1 停止錄製後要等約 30 分鐘

2026-10-20 的 2 小時場（121 段），從停止到 `transcript.speakers.md` 就緒約 30 分（`plan-approved.md:14-23`；加總 ≈ 29.5 分，`research-requirement.md:25`）：

| 階段 | 耗時 | 根因（依據） |
|---|---|---|
| normalize 121 段 | 16.5 分 | 每段都重新編碼（`bin/_record_finalize.py:1210-1292`）；錄製時每段尺寸跟著視窗變（`RecordingSession.swift:124,174-176,524-534`），只能逐段補邊；碼率＝各段最大 ×1.5、下限 8M（`bin/_record_finalize.py:1447`） |
| concat | 149 秒 | 2 小時 AAC 單執行緒編碼＋`+faststart` 重寫整檔（`bin/_record_finalize.py:1487-1490`） |
| 解碼驗證 | 49 秒 | 整支 null 解碼＋兩次封包掃描（`bin/_record_finalize.py:1491-1499`），log 上記成 concat（`step="concat"`，`:1493`） |
| 抽 wav | 5 秒 | 從 AAC 解回 16k，排在最後（`bin/_record_finalize.py:1501-1504`） |
| 等收尾 | — | 自動前處理要等 `phase == .done`（`tools/MeetingRecorder/Sources/Core/Control.swift:414`），但前處理其實只要 wav |
| 轉錄 | 5 分 56 秒 | mlx-whisper 單 process、一次解一窗（`bin/transcribe.sh:120-133`） |
| 講者分離 | 3.6 分 | 排在轉錄之後才跑（`bin/meeting.sh:327-338`），但不依賴轉錄；16k wav 又轉一次（`bin/diarize.sh:28`） |

2026-10-21 的 87 分鐘場（88 段，R3 合併後版本）收尾約 26 分＋前處理 7.3 分 ≈ 33 分：這組數字只出現在派工單，repo 與 run 目錄都找不到出處（`research-requirement.md:16`），**未能確認**，本檔不拿它當驗收基準。

**結論**：四分之三的時間花在影片收尾；而前處理只需要音訊，卻被排在影片之後，轉錄與分離又串行。只壓縮各步驟不夠，要換做法：音訊和影片拆開、前處理平行、錄製中先做一部分。

### 1.2 正確性與五條鐵則的缺陷

盤點找到下列現存缺陷（`b0-audit.md:42-66`、`research-code-contracts.md:48-54`）：

- **ASR 失敗被吞掉**：mlx_whisper CLI 出例外也回 0（`b0-audit.md:44`），退回鏈從不觸發；`| tail -8` 截掉 traceback（`bin/transcribe.sh:132`）。
- **缺 segments.json 時靜默重轉**：`bin/meeting.sh:247-273` 會不出聲地再跑一次約 6 分鐘的轉錄。
- **鐵則 5（聲紋只留 `vault/`）**：`embeddings.json` 寫在場次資料夾（`bin/diarize.sh:31`、`bin/_diarize_pyannote.py:223-240`），`.gitignore` 也沒排除它。
- **鐵則 3（不確定的姓名不掛）**：speakers.map 的 confidence 預設 1.0（`bin/_merge_speakers.py:78`、`bin/_render.py:270`），`bin/_voiceprint.py:116` 卻預設 0；人工寫的字串對應或沒有 confidence 的對應會被聲紋比對覆蓋（`bin/_voiceprint.py:115-118`，分析見 `research-code-contracts.md:52`）。
- **鐵則 1（raw 不改）**：`_to_tw.py` 原地改寫 raw（`bin/transcribe.sh:194-201`）。
- `_voiceprint.py` remove 沒有過濾檔名（`bin/_voiceprint.py:172`）；meeting-speakers SKILL 少了 annotate 步驟（`.claude/skills/meeting-speakers/SKILL.md:42-46`）。
- **preflight 誤報**：音訊裝置開不起來時被報成「權限沒有生效」，結束碼 4，還會連帶誤報兩項（`b0-audit.md:6-11`）。
- **停止路徑靜默 return**：`MenuBar.swift` 800、819、877、891、943、1191，`HUD.swift:271`，`Onboarding.swift` 621、624（`b0-audit.md:12-16`）。
- **state 檔無鎖並發寫**：`bin/meeting.sh:300-310`（非原子、無鎖）對上 `bin/_record_finalize.py:1301-1307`（原子、無鎖）（`research-code-contracts.md:36`）。
- `meta["embeddings"]` 在 diarization.json 寫完後才設定，這個鍵從不落盤（`research-code-contracts.md:54`）。

### 1.3 結構

長檔與長函式讓每次修改都要動大量行數：`MenuBar.swift` 1309 行、`RecordingSession.swift` 1278 行、`bin/_record_finalize.py` 1583 行（`research-requirement.md:65` 以 `wc -l` 核對）；`finalize_locked` 186 行、`record.sh cmd_control` 152 行等（`b0-audit.md:38-40`）。重複實作見 `b0-audit.md:56-62`。

### 1.4 R3 交下來的項目

- 前處理完成通知的內文含場次名（`tools/MeetingRecorder/Sources/Trigger/Completion.swift:132` 取 `lastPathComponent`，`:138`、`:172`、`:180`、`:182` 放進內文），跟 R3-§6 第 135 條和 spec §4.39.3「通知不得含場次名」不一致（`research-requirement.md:28`、`research-specs-adr.md:39`）。
- `tests/record/test_r3_lock.py:351-355` 的計時容許範圍只有 +2 秒（(930, 932)、(11430, 11432)）。R3 交接所說的「±1 秒太緊」是不是指這一條，**未能確認**（`research-specs-adr.md:63`）。
- N-3（被中止的段落印「改用 libx264」沒有行為測試）、N-4（前景退回路徑沒有整合測試）（`_tpm/runs/20261010-sdlc-meeting-record/pr-description.md:109`）。N-3 對應計畫的 video-copy（`plan-approved.md:83`）；N-4 不在計畫的 12 個子任務裡（`research-requirement.md:30`）。

## 2. 期望結果

- **G1 速度（主目標）**：2 小時場從停止錄製到「`transcript.speakers.md` 以及影片、錄音成品都就緒」≤ 5 分鐘，AI 總結不計（使用者決定 1，`plan-approved.md:9`）。量法：用 keep-segments 保留的 2 小時段落重放，量停止 → 終點；改之前約 30 分（`plan-approved.md:129-130`）。每一層子任務完成後各量一次，記進 progress.md（`plan-approved.md:131`）。影片「就緒」包不包含背景驗證、適用多長的會議，見 Q1。
- **G2 邊錄邊處理，但錄製優先**：錄製中可以先轉錄已關閉的段落；背景工作低優先權，一出現丟幀就暫停，停止後補做（使用者決定 2，`plan-approved.md:10`）。實機驗收：錄一場 ≥ 30 分鐘的會議，背景 ASR 在跑，丟幀為 0；停止後量完成時間（`plan-approved.md:133`）。
- **G3 換做法（關鍵路徑）**，依 `plan-approved.md:25-33`：
  1. 停止後先從各段 PCM 產出 16k wav，標記「音訊就緒」，觸發前處理；
  2. 轉錄和講者分離平行；
  3. 影片走固定畫布＋`-c:v copy` 串接，不符合條件時退回現行整支重編；
  4. 錄製中增量轉錄，停止後只剩最後一段。
- **G4 品質不退步**：增量轉錄和整檔轉錄比對字錯率與時間戳；影片沿用既有判準，用缺陷 B、F、N 的情境重驗（`plan-approved.md:132`）。增量轉錄要多準才能採用，見 Q5。
- **G5 失敗看得到**：ASR 失敗回非 0；拿掉靜默重轉，改成明確報錯並提示（C8）；preflight 分得出「音訊裝置無法啟動」和「權限沒有生效」，並附上裝置與 transport；停止路徑每個 return 都寫 log（`plan-approved.md:38-59`）。
- **G6 五條鐵則**：`embeddings.json` 離開場次資料夾；人工確認的對應不被聲紋比對覆蓋；raw 逐字稿不再被原地改寫，正體版另存；SKILL 補上 annotate（`plan-approved.md:44-50`）。
- **G7 並發安全**：`.pipeline-state.json` 的寫入者一律原子寫入＋flock。這是「音訊就緒就提早開始前處理」的前提（`plan-approved.md:60-62`），寫法沿用 `adr-r3-defaults-writers`：flock、讀後合併、mkstemp/rename、等鎖 5 秒逾時（`research-specs-adr.md:14`）。
- **G8 結構重構**：拆長檔與長函式、集中重複的 helper（`plan-approved.md:95-107`），排在速度改完之後做，避免衝突。行為不變，以全量測試佐證。
- **G9 R3 交下來的項目**：完成通知改用場次代號，不含場次名；`test_r3_lock` 計時容差（要不要改，要使用者核准，見 §4.3）；N-3 補行為測試；N-4 要放進子任務或明確列為不做（交 design）。

驗收時每個子任務都要過（`plan-approved.md:127`；`.claude/teams/rules.md` 專案規則 verify）：
- `bash bin/_lint.sh && bash bin/meeting.sh doctor`
- `tools/MeetingRecorder/Tests/run.sh`
- Python 全量測試
- 名稱掃描（只回報有或沒有）

## 3. 受影響的使用者與系統

**使用者**
- 錄會議的本人：停止後等待的時間；錄製中背景工作對錄影的影響（G2）；成品影片的解析度、幀率與檔案大小（Q3）。
- 其他 Claude session：透過 `bin/meeting.sh` 與 `~/.claude/skills/meeting-*`（symlink 回本 repo）呼叫，所以子指令、結束碼、SKILL 文字都算對外介面（`CLAUDE.md`「對外介面」；`.claude/teams/rules.md` 專案規則第 7 條）。

**系統與對外契約**（本 repo 沒有 `contracts/`；實際的契約整理在 `research-code-contracts.md:19-54`）
- CLI 結束碼：
  - `meeting.sh`：`prep` 找不到場次回 3；轉錄或分離失敗仍回 0（`bin/meeting.sh:327-338`）。
  - `meeting record`：`stop` 0/3/5、`finish` 0/2/3/5、`status` 0/5（`bin/record.sh:40-74`）。
  - `transcribe.sh`：0/2/3；`diarize.sh`：0/2/3/4/5；`_record_finalize.py`：0/2/3/5。
- 狀態檔 `record.status.json`、`finalizing/<runId>.status.json`（`RecordStatus`，`Core/Records.swift:33-60`）：新欄位只能加成 Optional、nil 時省略鍵，**不新增 `RecordPhase` 值**（`specs/meeting-record/adr/adr-r2-status-fields.md:24,35`）。舊版讀端遇到不認得的 phase 會整筆解不開（`Core/BackgroundFinalize.swift:111-113`）。
- 「wav 出現＝場次存在」的時機契約（C1）：
  - `bin/_record_finalize.py:22`、`:1554`；
  - `.claude/skills/meeting-record/SKILL.md:249`；
  - `bin/meeting.sh` 的 `list_sessions`／`has_audio`（`:286-298`）；
  - `錄音/` 第一層的音檔數會影響 VAD 與串接（`bin/transcribe.sh:63-76`、`bin/_combine_audio.py:12-18`）。
- 產物檔：
  - `錄音/tracks/finalize.json` 與冪等判斷（`bin/_record_finalize.py:735-746`）；
  - `manifest.json` 的 `outputCanvas`／`outputVideoBitrate`，e2e 判準 `c_canvas` 要求影片尺寸＝各段最大寬高（`tests/record/e2e_check.py:638-648`）；
  - `transcript.segments.json` 與 `transcript.quality.json` 必須成對（`bin/meeting.sh:254-264`）；
  - `embeddings.json`：寫入方、讀入方、兩份 SKILL 要一起改（`research-code-contracts.md:51`）。
- 自動前處理：`AutoPrepRunner` 實際下的指令，以及結束碼 0 就發「前處理完成」（`Trigger/Completion.swift:143-148,174-176`）。
- 下游知識庫專案：`summary.md` 格式不在本 epic 範圍；若動到 `_render.py` 的輸出，要用對方的 `meetings._missing_sections()` 驗過（專案規則第 6 條）。
- 上游：無。origin 就是本 repo，main ＝ `042c404`，沒有開著的 PR、沒有 CI（`research-upstream.md:7-22`）。

## 4. 限制

### 4.1 硬限制（不得推翻）
- 五條鐵則（`CLAUDE.md`「專案特定」；`.claude/teams/rules.md` 專案規則 1–5）。增量轉錄拼出來的結果也算 raw：只能換來源，不能清洗輸出（`research-specs-adr.md:18`）。
- `meeting.sh` 的子指令與結束碼不得破壞性變更；新情況以增補處理，結束碼集合不變。先例是 R3x-§2.2（`specs/meeting-record/spec.md:1996-2005`）。
- 狀態通道只有狀態檔＋pid＋SIGTERM（`adr-control-channel.md:21-29`）；audioReady 和丟幀數只能用 Optional 欄位對外（`adr-r2-status-fields.md`）。
- 全程本機；聲紋只留 `vault/`。
- 測試失敗就改程式、不改測試；要改既有測試必須逐條經使用者核准，並記進 spec「整合修訂與例外」（`.claude/teams/rules.md` 通用規則 20）。
- 公開 repo：spec、筆記、commit 不得出現真實會議名稱、客戶名稱、視窗標題（spec §6 第 39 條，`specs/meeting-record/spec.md:869`）。
- 新的 Python 檔放 `bin/lib/`，`_lint.sh` 檔數維持 26。先例是 R3-§6 第 125 條（`research-specs-adr.md:19,44`）。所以計畫的 `bin/_asr_worker.py` 應改放 `bin/lib/_asr_worker.py`。
- 錄製中的背景工作要沿用 R3x-D9 判斷「錄製中」的方式（`record.pid`＋`kill -0`＋phase），以及錄製中平行度降為 2（spec R3x §3.21–§3.25，`research-specs-adr.md:16`）。上一場背景收尾、這一場錄製、這一場 ASR 三方同時跑時的資源分配，要在 design 寫明。

### 4.2 本 epic 會推翻或修訂的既有定案（每條都要在 spec 寫明取代關係，並經使用者核准）
依 `research-requirement.md:36-47`、`research-specs-adr.md:22-40`：

| # | 計畫的換法 | 被推翻／修訂的既有定案 | 出處 |
|---|---|---|---|
| C1 | wav 先發佈、audioReady 觸發前處理 | 「場次存在與錄製完成同一瞬間」；§4.6.5、§4.7.2；R3-§6 第 140 條；`test_concurrency.py::test_finalizing_session_not_listed` | `specs/meeting-record/spec.md:666,689,1953`；`bin/_record_finalize.py:22` |
| C2 | 冪等判斷要能處理「只有 wav、影片還沒出」的中間態 | §4.6.6：兩個輸出都在才算已完成 | `bin/_record_finalize.py:735-746` |
| C3 | wav 改從各段 PCM 產出 | 現行由串接結果抽 wav；§4.6.20 (ii) wav 與影片音訊軌長度差 ≤ 25 ms；補償開啟時要用 `compensated_audio` | `specs/meeting-record/spec.md:681`；`bin/_record_finalize.py:1477` |
| C4 | 串接音訊改用 `aac_at`、拿掉 `+faststart` | §6 第 65 條「`-c:a aac -b:a 256k` 一次編碼」；`test_static_rules.py:505-522` 要求相鄰的 `"-c:a", "aac"` | `specs/meeting-record/spec.md:895` |
| C5 | 固定畫布 | **使用者決定 D8**（每段用當下視窗像素、收尾統一成各段最大寬高；畫布＝`displayPixelSize()` 已明文作廢）；需求正本「保留原樣全解析度」；§6 第 63 條 | spec §6 第 5 條（`specs/meeting-record/spec.md:835`）；`specs/meeting-record/adr/adr-segment-writer.md:44` |
| C6 | 60→30 fps（待決） | §4.3.3 `minimumFrameInterval = "1/60"`、1 秒窗 ≥ 55 fps；§6 第 6 條 | `specs/meeting-record/spec.md:624,836` |
| C7 | `-c:v copy`，碼率等於來源 | **使用者決定 D7**（整支重編、碼率 ×1.5、下限 8 Mb/s）；§4.6.10「位元率 ≥ 各段最大值」 | `specs/meeting-record/adr/adr-video-tail-pad.md:22-31`；spec §6 第 16 條 |
| C8 | 拿掉缺 segments.json 時的靜默重轉 | §4.29.3（之後 segments.json 要存在）；`test_r3_vtt_raw.py::test_diarize_keeps_raw` | `specs/meeting-record/spec.md:1673` |
| C9 | 解碼驗證移到成品交付之後 | 現行驗證失敗就回 5、成品不發佈；移到之後，驗證失敗時成品已經發佈，要定義怎麼處理 | `bin/_record_finalize.py:1491-1499,1506-1509` |
| C10 | 效能基準要讀 keep-segments 保留的段落 | §4.6.21 的實機段落在 `~/.meeting-harness/` 底下，本 epic 的調研規則不讀這個目錄 | `specs/meeting-record/spec.md:682`；`plan-approved.md:129` |

另外：R3 把即時轉錄與拆檔列為「本輪不做」（`specs/meeting-record/intent.md:386-397`），已被 2026-10-21 使用者的新決定取代，不需要再問（`research-specs-adr.md:38`）。

### 4.3 會擋住計畫的既有測試（改任何一條都要核准）
依 `research-code-contracts.md:56-69`、`research-specs-adr.md:32-40`：
- `test_regression.py:50-54` `test_diarize_and_merge_untouched`：`diarize.sh` 與 `_merge_speakers.py` 必須和 main 完全相同，但 prep-parallel 和 iron-rules 都要改這兩個檔。
- 替身 `fakes/asr/mlx_whisper` 與 argv 斷言（`test_r3_transcript_vad.py`、`test_r3_vtt_raw.py`、`test_deliver_fixes.py`、`test_t7_fixes.py`）：ASR 改成 in-process 呼叫後就攔不到。
- `test_static_rules.py:505-522`（concat 呼叫要有相鄰的 `aac`）、`test_r3_finalize_guard.py`（步驟名只能是 normalize／concat／mix／probe）、`test_static_rules.py:368-374`（`nextSegmentSize(`）。
- Swift 靜態測試把檔名與函式本體釘死：`test_r3_app_static.py:128-137,209,320`（`stopTargetDecision(`）、`test_r2_static.py`、`test_r3x_app_static.py`。
- `test_r3x_parallel_finalize.py` 直接讀寫模組全域；拆檔後全域變成副本，測試會悄悄失效。
- `test_r3_lock.py:332-356`：`cmd_stop()` 裡必須恰好一個 `limit=` 區塊；計時容差也在這支。
- `test_e2e_check.py` 的 fps 判準（只有 Q3 選 30 fps 時才會碰到）。
- R3 的先例：兩次都撤回改測試，改成換做法（R3-§6 第 122、125 條）。

### 4.4 環境限制
- 這台的 `python3`（pyenv shim）會卡住。`AutoPrepRunner` 走 `zsh -l`，會帶進 shim（`research-code-contracts.md:102`）。ASR 改走 Python 時，直譯器來源要固定。
- mlx-whisper（Metal）和 pyannote（MPS）平行時會搶 GPU，實際加速多少要量過才知道（`research-code-contracts.md:103`）。2 小時場分離約 3.5 分，關鍵路徑估計 4–4.5 分（`plan-approved.md:30-31`），離 5 分的餘裕不到 1 分。
- pyannote 4 不傳 `return_embeddings` 時是否仍會回 `speaker_embeddings`：**未能確認**，要實跑驗證（`research-code-contracts.md:53`）。

### 4.5 不做（本輪）
- AI 總結的速度（使用者決定 1）。
- 增量講者分離 embedding，列為衍生工作（`plan-approved.md:93`）。
- `meeting.sh prep` 失敗時改回非 0：這是結束碼語意變更。建議維持回 0，`AutoPrepRunner` 改讀 `.pipeline-state.json` 判斷成敗（`research-code-contracts.md:100`）。列為衍生工作，要做的話另外請使用者決定。

## 5. 待解問題（閘門 1 請使用者決定）

以下五題會影響範圍或驗收。每題都列出選項、代價與建議；**建議不等於已決定**。

### Q1 「5 分鐘」量到哪裡、適用多長的會議
使用者決定的終點包含影片成品（`plan-approved.md:9`），但計畫的量法只量到 `transcript.speakers.md`（`:129`）。
- (a) 終點包含影片成品，背景解碼驗證不計；以 2 小時場為準，更長的場次只記錄實測值。代價：影片 copy 路徑也要在 5 分內完成；驗證失敗時成品已經發佈（C9），要定義回收或標記的方式。
- (b) 終點包含影片成品與背景驗證。代價：影片驗證（現在 49 秒）也要擠進關鍵路徑，餘裕更小。
- (c) 只量 `transcript.speakers.md`，影片另訂目標。代價：跟使用者決定的字面不一致。
- 建議：(a)。這是使用者決定的字面，又不讓驗證拖慢交付。

### Q2 音訊先出之後，「場次存在」怎麼定義、audioReady 怎麼對外呈現
衝突 C1、C2；契約限制是不新增 phase、只加 Optional 欄位（`adr-r2-status-fields.md:24`）。
- (a) wav 先 rename 進 `錄音/`，從那一刻起就算場次存在；改寫 §4.6.5、§4.7.2、第 140 條，冪等要認得中間態；改 `test_concurrency`。代價：要改的 spec 條文和測試最多；其他 session 跑 `meeting status`／`prep` 會看到影片還沒好的場次。
- (b) wav 先寫到 `錄音/tracks/` 下的固定路徑，或 `.` 開頭的隱藏名；只有自動前處理直接吃這個路徑，`錄音/` 第一層照舊在最後才出現正式 wav。代價：prep 要多一個輸入來源（參數或約定路徑），轉錄結果要能對應到最後的正式 wav。
- (c) 維持現狀，只把影片步驟加速。代價：關鍵路徑多了影片收尾的 1–1.5 分，5 分內的餘裕不夠。
- 不論選哪個，對外呈現都建議這樣做（`research-code-contracts.md:92-97`）：
  - `RecordStatus` 加 `audioReady: Bool?`，phase 維持 `finalizing`；
  - `shouldAutoPrep` 另開提早觸發的判準，原本的 done 路徑保留，用來容錯；
  - `record stop` 的結束碼與等待語意不變，只多印一行「音訊已就緒」；
  - `.pipeline-state.json` 加一個 `audio` stage。
- 建議：(b)。保住「場次存在＝錄製完成」的既有定案，也不用改 `test_concurrency`。

### Q3 影片：畫布尺寸、幀率、碼率
這題會推翻使用者先前的決定 D8（C5）、修訂 D7（C7），也可能改 §4.3.3（C6）。
- (a) 畫布＝主顯示器像素（參考 `Probe.swift:102-109`），維持 60 fps；全場符合條件就 `-c:v copy`，碼率等於來源（不再 ×1.5），否則整場退回現行重編。代價：推翻 D8；小視窗會被放大或補邊（檔案變大）；e2e 的 `c_canvas` 與 `nextSegmentSize` 相關測試要改（需核准）；成品碼率變低，要用缺陷 B、F、N 的情境重驗。
- (b) 固定 1920×1080 或 2560×1440，並降到 30 fps。代價：違反需求正本的「保留原樣全解析度」與 §4.3.3 的 55 fps 判準，還要改 fps 系列測試；好處是錄製中的編碼負擔最小，背景 ASR 比較有餘裕。
- (c) 維持 D8 的可變尺寸，不走 copy，只加速 concat、驗證、ffprobe。代價：normalize 16.5 分不會消失，影片達不到 5 分（如果 Q1 選 (a) 或 (b)，G1 就做不到）。
- 建議：(a)。這是唯一能讓影片進 5 分、又維持全解析度和 60 fps 的選項；`aac_at` 先量它對 149 秒串接的實際收益，再決定要不要申請改 `test_static_rules`。

### Q4 既有測試的處理原則
受影響的測試見 §4.3。
- (a) 全部繞開：保留 `stopTargetDecision(`、`-c:a aac`、模組全域、mlx_whisper CLI 這道接縫與既有檔名；`diarize.sh`／`_merge_speakers.py` 不動，改在 `bin/lib/` 寫新入口。代價：拿不到 `aac_at` 的加速；拆檔幅度受限；會留下兩份邏輯和死碼。
- (b) 閘門 2 逐條列出要改的測試與理由，附等價的新斷言，經核准後記進 spec §6。代價：每條都要使用者核准；改測試有削弱守門的風險。
- (c) 混合：
  - 第 0～2 層照 (a)；ASR 用 `bin/lib/_asr.py` 保留同一組 CLI 介面，替身照樣攔得到；
  - 鐵則相關的 `_merge_speakers.py` 與 `diarize.sh` 例外，改在源頭，`test_diarize_and_merge_untouched` 逐條核准；
  - 第 3 層的結構重構測試一次送核准；
  - `test_r3_lock` 的容差單獨核准。
  - 代價：第 3 層前還要再過一次核准閘門。
- 建議：(c)。速度相關的改動不碰測試；鐵則修正改在源頭，比留兩份邏輯單純。

### Q5 增量轉錄的切點、丟幀判準與採用門檻
`plan-approved.md:89-91` 只寫「VAD 靜音點，或前後重疊 2–3 秒再去重」與「一出現丟幀就暫停」；status 目前沒有丟幀欄位（`research-code-contracts.md:85`）。
- (a) 切點取段尾附近的 VAD 靜音點（重用 `bin/lib/_record_lib.py` 的 `levels_intervals`）；丟幀判準是新增的 Optional 丟幀數一增加就暫停，錄製中不恢復，停止後補做；採用門檻是逐段結果完整，且模型、語言、VAD 參數和整檔路徑一致，否則退回整檔轉錄。代價：碰到沒有靜音的長段要硬切，可能切到字中間。
- (b) 切點是前後重疊 2–3 秒再去重；丟幀暫停後，一段時間沒有新的丟幀就恢復。代價：去重邏輯本身可能在 raw 裡產生重複或缺字（鐵則 1 只能標記、不能清洗）；恢復條件要另外定門檻。
- 品質門檻（字錯率差幾 %、時間戳差多少 ms）不論選哪個都要在 design 定數字，閘門 2 核准。
- 建議：(a)。不會在 raw 裡製造重複；暫停後不恢復最保守，跟「保護錄製」的決定一致。

### 不問、由 design 依預設處理的模糊點（閘門 1 可以推翻）
1. **場次代號**：用既有的 `backgroundJobLabel`（`Core/BackgroundFinalize.swift:189-200`，不讀 session）。
2. **confidence 預設**：
   - 沒有 confidence 的 dict 視為未確認，不套名；
   - 字串值（人工確認）直接套，聲紋比對一律不覆蓋；
   - 0.7（spec §4.29.2）與 0.75（`.claude/teams/rules.md` 專案規則第 3 條）兩套門檻的關係，由 design 統一成一套，在 spec 寫明。
   - 代價：舊場次重跑 render，原本沒有 confidence 的 dict 對應會不再掛名（`research-requirement.md:55`、`research-specs-adr.md:49`）。
3. **`embeddings.json` 放哪裡**：每場的 embedding 包含沒確認過的講者，不放 `vault/voiceprints/`。改放 `vault/` 底下另一個按場次分的暫存目錄，用完可刪；`.gitignore` 補上 `embeddings.json`（`research-requirement.md:56`）。
4. **靜默重轉的替代行為**：缺 segments.json 時明確印出原因並提示指令，`meeting diarize` 的結束碼集合不變（C8）。
5. **spec 編號**：`specs/meeting-speed/spec.md` 自己從 §1、第 1 條起算；被取代的 meeting-record 條文逐條列出原條號。
6. **效能基準的資料來源（C10）**：保留段落的路徑由使用者在量測時提供，或由主 session 量測；子 agent 不讀 `~/.meeting-harness/`。
7. **N-4（前景退回路徑沒有整合測試）**：design 決定放進 stop-gate 或 audio-first 子任務；放不進去就明確列為不做。

## 6. 衍生工作（不編號）
- R2 留下的「完成通知含場次路徑」（`RecordingSession.swift:1248-1250`、`MenuBar.swift:1129`）；F2 試錄選錯 app；補尾膨脹；pyenv shim 卡住；增量講者分離；VAD 門檻調到 -45～-50 dBFS（要先做小聲講者的回歸測試）（`plan-approved.md:109`）。
- `meeting.sh prep` 失敗時的結束碼（§4.5）。
- 把 87 分鐘場的基準數字（遮罩後）補進 run 目錄，讓它有出處（`research-requirement.md:71`）。
- `run.json` 五個 stage 都是 `pending`，沒有 plan-approved.md 的核准紀錄（`research-requirement.md:67`）。閘門紀錄由主 session 用 `save_run.py approve` 補記。
- `config.json` 的 `requireVerifierPassBeforePublish` 沒有程式在檢查；`meeting-pipeline.js` 舊流程直接寫 summary.md，有違反鐵則 2 的風險（`b0-audit.md:53-55`）。docs-cleanup 要決定改接新流程還是標示棄用。

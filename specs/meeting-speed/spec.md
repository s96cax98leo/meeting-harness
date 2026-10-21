# spec：meeting-speed（停止錄製後 5 分鐘內就緒＋全專案重構）

- 上游：`specs/meeting-speed/intent.md`（閘門 1 已核准，2026-10-21；**§7 是決定全文**）、`design.md`、`adr/` 四則。
- 狀態：**閘門 2 已核准（使用者 2026-10-21）**。使用者 2026-10-21 在閘門 2 前已先決定 D1–D5 與 E1–E4（原文與逐條處理見 run 目錄 `_tpm/runs/20261021-sdlc-meeting-speed/design-revise-對照.md`，該目錄不進 repo）：§6 第 1–21 條核准（D1）；G1 拆兩條線量（D2，§4.14.4）；當晚錄製異常中止的 4 項修正併入（D3，§4.4.12、§4.4.13、§4.16）；每個子任務都跑四件套（D4，§4.15）；§4.11.9 品質門檻核准、結構重構不另開第 4 層（D5）；§6 第 23 條（E1）、第 24 條與異常中止判定改用共享狀態檔的 pid（E2）確認；四件套的兩個例外以「允許仍紅」一詞統一（E3，§4.15.1）；拿掉早期模式、影片線外推值 > 240 秒補長錄、`paused_total` 以 `_record_finalize` 的算法為準（E4，§3.7、§4.14.4、§4.13.2）。§4.4.13 的擷取幀率／尺寸待 `video-spike` 實測後由使用者決定。
- 行號以 `042c404` 為準（`git log --oneline -1 origin/main`）。
- 編號：本 spec 的節號與 §6 條號從 §1、第 1 條自己起算；引用 meeting-record 的條文一律寫「meeting-record §x.y」或「meeting-record §6 第 n 條」。
- Story ID：本 repo 沒有上層任務系統，Story ID 用 intent §2 的目標代號 **G1–G9**（只在本 epic 內引用，不是任務編號）。commit scope 用 `meeting-speed`。
- 句型：驗收條件一律用 EARS（「系統應…」「當…時，…應…」「在…期間，…應…」「若…，則…應…」）。
- 範例場次名一律用「[Stand-up] 範例專案」；本檔不得出現真實會議名稱、客戶名稱、視窗標題。
- `specs/_templates/` 不存在，格式沿用 `specs/meeting-record/spec.md`。

---

## 1. 範圍

| Story | 內容（intent §2、§7） | 本 spec 節 |
|---|---|---|
| G1 | 2 小時場從停止錄製到 `transcript.speakers.md`、影片成品、錄音成品都就緒 ≤ 5 分鐘（300 秒）；AI 總結不計；背景驗證不計；量法拆逐字稿線與影片線（D2） | §4.2–§4.5、§4.14 |
| G2 | 錄製中先轉錄已收尾段落；背景低優先權；丟幀數一增加就暫停到停止 | §4.11 |
| G3 | 關鍵路徑的做法依閘門 1 決定（音訊先出、轉錄與分離並行、影片 copy、增量轉錄）；擷取幀率／尺寸上限待 `video-spike` 實測後由使用者決定（D3 d） | §4.2–§4.11、§4.4.13（做法本身不另列驗收） |
| G4 | 品質不退步：增量與整檔比對字差異率與時間戳；影片用缺陷 B、F、N 情境重驗；退回重編路徑的補尾幀數不再依 `r_frame_rate` 推算（D3 a） | §4.4、§4.4.12、§4.11.9、§4.14 |
| G5 | 失敗看得到：ASR 失敗走退回鏈、拿掉靜默重轉、preflight 分得出裝置失敗、停止路徑寫 log、前處理失敗發失敗通知；上次錄製異常中止時，選單啟動就通知並一鍵收尾、`record finish` 不帶參數可接手（D3 b、c） | §4.7、§4.8、§4.10、§4.16 |
| G6 | 五條鐵則：embedding 不落場次資料夾、人工確認不被覆蓋、raw 不原地改寫、SKILL 補 annotate | §4.6 |
| G7 | `.pipeline-state.json` 寫入者一律原子寫入＋flock | §4.9 |
| G8 | 結構重構：拆長檔、集中重複 helper，行為不變 | §4.13 |
| G9 | 完成通知（前處理三則、錄製完成兩則）改用場次代號；`test_r3_lock` 容差送核准；N-3 補行為測試；N-4 明確不做 | §4.4.10、§4.12、§6 第 21 條、§7 疑慮 7 |

**不在範圍**（intent §4.5、§7；design §15）：AI 總結速度；增量講者分離；`meeting.sh prep` 失敗時回非 0；`aac_at`；pyannote 4 不傳 `return_embeddings`；N-4；`_lint.sh` 加 `-W error::ResourceWarning`；停止流程提早把共享狀態標成「可救回」（`incident-2018-windowserver.md` 衍生工作第 3 項，D3 未列入）；`bin/_record_prompt.py:45` 的 `load_json` 併入共用 helper；`harness_config` 三份（`bin/_diarize_pyannote.py:24`、`bin/_voiceprint.py:26`、`bin/_profile.py:49`）合一（修正輪 2 移出，理由見 §4.13.2）。

---

## 2. 結束碼（集合一律不變）

| 指令 | 結束碼集合（`042c404`） | 本 epic 的新情況 | 對映 |
|---|---|---|---|
| `meeting record finish` | 0／2／3／5（`bin/record.sh:1199-1219`） | 不帶參數、共享狀態檔記錄的 pid 已不在且 phase＝stopping（§4.16.3；不看 `record.pid`） | 照該場次跑，結束碼照 `finish <場次>` 現行；沒有可接手的場次時照舊 2 |
| `meeting.sh prep` | 同上 | 轉錄、OCR、分離任一失敗 | 仍回 0（intent §4.5），只寫 `.pipeline-state.json` |
| `meeting.sh diarize` | 0／1／2 | 缺 `transcript.segments.json`（§4.8.4；§6 第 13、20 條，使用者 2026-10-21 核准） | 1 |
| `meeting record stop`／`finish`／`status` | `stop` 0/3/5、`finish` 0/2/3/5、`status` 0/5（`bin/record.sh:40-74`） | 背景驗證失敗（§4.5） | 5（同「收尾失敗」） |
| `_record_finalize.py` | 0／2／3／5 | 背景驗證失敗或逾時 | 5 |
| `transcribe.sh` | 0／2／3／4（＋`set -e` 帶出的其他碼，`bin/transcribe.sh:5`） | ASR 引擎回 0 但沒有非空 `.json`（§4.7.1） | 走退回鏈；全部引擎都失敗時照舊 3 |
| `diarize.sh` | 0／2／3／4／5 | 無 | 不變 |
| `_voiceprint.py` | 0／2 | `add` 時無法重算向量（diarize venv 不在） | 2 |
| `_asr_worker.py`（新，內部） | — | `run`：0 完成、2 參數錯；`stitch`：0 可用、2 參數錯、3 不可用 | 新檔，不是對外介面 |
| `tools/bench/replay.py`（新，測試工具） | — | 0 完成、2 參數錯、5 管線失敗 | 新檔，不是對外介面 |
| preflight（錄製器） | 第 5 項 hard、結束碼 4 | 音訊裝置無法啟動（§4.10.1） | 4（集合不變） |

---

## 3. 資料契約

### 3.1 狀態檔新欄位（`record.status.json`、`finalizing/<runId>.status.json`）

沿用 meeting-record `adr-r2-status-fields.md:24,35`：只加 Optional、nil 時省略鍵、**不新增 `RecordPhase` 值**。

| 鍵 | 型別 | 寫入者 | 意義 |
|---|---|---|---|
| `audioReady` | `Bool?` | 錄製器（`FinalizeRunner` 認到 §3.8 的「音訊就緒：」一行後） | `true`＝正式 wav 已出現在 `錄音/` 第一層、`錄音/tracks/audio-ready.json` 已原子寫好（§3.2）；其他時候省略 |
| `droppedFrames` | `Int?` | 錄製器（每段收尾時累加該段丟幀數；錄製中第一段收尾後才出現） | 本場累計丟幀數；ASR worker 用它判斷暫停（§4.11.4） |

### 3.2 音訊先出：正式 wav 與 `錄音/tracks/audio-ready.json`

D2（使用者 2026-10-21）：正式 wav 必須先於影片發佈、不等影片。所以音訊一備好就直接發佈正式 wav，不再另設暫存音檔與「早期模式」（修正輪拿掉 `錄音/tracks/audio/`、`MH_PREP_EARLY`、`MH_TRANSCRIBE_REC_DIR`、`MH_DIARIZE_AUDIO`，理由見 design §3）。

- 產生：16000 Hz、1 channel、`pcm_s16le`，先寫 `錄音/tracks/.finalize/audio.wav.part`（現行暫存目錄，`bin/_record_finalize.py:1449,1502`）。
- 發佈順序（§4.2.1、§4.2.3）：`audio-ready.json` → `finalize.json` 第一階段（§3.4）→ `os.replace` 成 `錄音/<場次名> <YYYY-MM-DD HH.MM.SS>.wav`（檔名照 meeting-record §4.6.2）→ 印「音訊就緒：」。
- `錄音/tracks/audio-ready.json`（原子寫入）：

```json
{
  "schemaVersion": 1,
  "wav": "[Stand-up] 範例專案 2026-10-21 09.30.00.wav",
  "stamp": "2026-10-21 09.30.00",
  "compensation": "off",
  "segments": [
    {"file": "seg-0001.mov", "size": 123456789, "duration": 60.012, "start": 0.0}
  ],
  "createdAt": "2026-10-21T11:30:12+08:00"
}
```

  `segments[i].start` 是該段在成品時間軸上的起點（秒，小數 3 位）＝前面所有可讀段落 `duration` 的總和；`duration` 是 finalize 分析時採用的段長。`compensation` 取 `off`／`constant`／`variable`（沿用 `compensated_audio` 的模式名，`bin/_record_finalize.py:1108-1151`）。冪等（§4.3.2）與增量轉錄的對齊（§4.11.7）都讀這個檔。

### 3.3 `record.meta.json` 新欄位

| 鍵 | 型別 | 寫入者 | 意義 |
|---|---|---|---|
| `canvasLock` | `{width: Int, height: Int}?` | 錄製器（開錄時，新錄製器一律寫） | 開錄當下會議視窗的偶數像素尺寸；整場每段以此尺寸開檔。舊場次沒有這個鍵 |

Swift：`struct CanvasLock: Codable, Equatable { var width: Int; var height: Int }`，`RecordMeta.canvasLock: CanvasLock? = nil`（nil 省略鍵）。

### 3.4 `錄音/tracks/finalize.json`、`manifest.json` 新欄位

`finalize.json` 改成兩階段寫入（D2；R3-§6 第 140 條「先寫 finalize.json、wav 後出現」的順序照舊，§6 第 23 條）：

- **第一階段**（正式 wav 出現之前）：現行鍵 `schemaVersion`、`stamp`、`inputs`、`skipped`、`outputs.video`（預定路徑，檔案此時還不存在）、`outputs.audio`、`syncCompensation`、`finishedAt`（＝錄音成品發佈時刻），另加 `videoPublishedAt: null`。
- **第二階段**（影片 rename 進 `影片/` 之後）：讀後合併，加 `videoPublishedAt`（ISO 時刻）、`videoPath`、`verify`；其他鍵不變。
- `videoPath`：`"copy"` 或 `"reencode"`。
- `verify`：`{"status": "pending"|"ok"|"failed", "reason": <字串，失敗時>, "path": "copy"|"reencode"}`。沒有 `verify` 鍵的舊檔視為 `ok`。
- 逾時（`timedOut`，meeting-record §4.28.3）照舊合併進同一檔。
- `manifest.json.outputVideoBitrate`：copy 路徑寫各段影片位元率的最大值（資訊用）。

### 3.5 `.pipeline-state.json`

現行結構 `{"stages": {<stage>: {"status": ...}}}`（`bin/meeting.sh:300-310`）保留，新增：

```json
{
  "prep": {"runId": "6F1C…", "startedAt": "2026-10-21T11:30:15+08:00", "expect": ["transcribe", "diarize"]},
  "stages": {
    "record": {"status": "done"},
    "transcribe": {"status": "done", "runId": "6F1C…"},
    "diarize": {"status": "failed", "runId": "6F1C…"}
  }
}
```

- `prep.expect` 是這一次 prep 對這一場應跑的 stage（`transcribe` 必有；有 `照片/` 才有 `slide-ocr`；要分離才有 `diarize`）。
- prep 寫的 stage 一律帶 `runId`；`record` 由 finalize 寫、不帶 `runId`。修正輪拿掉 `audio` stage（intent §7 沒有要求，見 §4.2.11）。
- 鎖檔：`<場次>/.pipeline-state.lock`（flock）。

### 3.6 `錄音/tracks/asr/`（增量轉錄）

| 檔 | 內容 |
|---|---|
| `worker.lock` | worker 持有的 flock |
| `state.json` | `{"schemaVersion":1,"status":"running"|"paused"|"complete"|"failed","pausedReason":"drops"|"otherFinalizing"|null,"heartbeat":<ISO>,"params":{…},"windows":[{"index":k,"start":s,"end":e,"segments":[…],"file":"w-0001.json"}],"droppedFramesAtStart":n}`，原子寫入 |
| `w-NNNN.json` | 第 k 窗 `mlx_whisper.transcribe()` 的結果（時間戳已平移到成品時間軸） |
| `worker.log` | worker 的 stdout／stderr |

`params` 鍵：`model`、`language`、`initialPrompt`、`vadThresholdDb`、`vadPad`、`vadMergeGap`、`vadApplied`、`compensation`。

### 3.7 內部環境變數（只由 `AutoPrepRunner`、`meeting.sh`、`diarize.sh` 內部設定）

| 變數 | 設定者 | 讀者 | 意義 |
|---|---|---|---|
| `MH_PREP_RUN_ID` | `AutoPrepRunner`（每次） | `meeting.sh prep` | 寫進 `prep.runId`；沒給時 prep 自己產 uuid |
| `MH_ASR_SEGMENTS_JSON` | `meeting.sh prep`（`stitch` 回 0 時） | `transcribe.sh` | 現成的 mlx_whisper 同 schema JSON；給了就不呼叫 ASR 引擎 |
| `MH_EMBEDDINGS_OUT` | 既有；`diarize.sh` 沒被指定時改用 `mktemp` | `_diarize_pyannote.py` | embedding 暫存檔路徑（§4.6.1） |
| `MH_EMBED_SPEAKER_CMD` | 測試專用 | `_voiceprint.py add` | 取代 `_diarize_pyannote.py --embed-speaker` 的指令（替身用） |

沒有這些變數時，`meeting.sh`、`transcribe.sh`、`diarize.sh` 的行為與 `042c404` 相同（§4.1.2），但 §4.6、§4.7、§4.8 列的鐵則與失敗判準修正不受環境變數控制、一律生效。修正輪拿掉的 `MH_PREP_EARLY`、`MH_TRANSCRIBE_REC_DIR`、`MH_DIARIZE_AUDIO`：正式 wav 在音訊階段就發佈（§3.2），prep 照現行方式讀 `錄音/` 第一層即可，不需要它們（D1 對 `MH_DIARIZE_AUDIO` 的放行因此用不到，§7 疑慮 13）。

### 3.8 stdout 新增行（`_record_finalize.py`）

- `音訊就緒：錄音/<檔名>.wav`：§3.2 的 `audio-ready.json`、`finalize.json` 第一階段、正式 wav 都就位後印一次，在任何影片步驟之前。
- `成品就緒：影片/<檔名>`：影片 rename 進 `影片/`、`manifest.json`、`finalize.json` 第二階段都寫好後印一次，在背景驗證之前。

Swift Core：`func isAudioReadyLine(_ line: String) -> Bool`（去掉前導空白後以 `音訊就緒：` 開頭）。

### 3.9 `bin/lib/_asr_worker.py` CLI（內部）

- `run <場次>`：持 `worker.lock`；依 §4.11 逐窗轉錄；結束碼 0／2。
- `stitch <場次> <out.json>`：依 §4.11.7 判斷可不可用；可用時把各窗結果拼成與 mlx_whisper `--output-format json` 同 schema 的 JSON 寫到 `<out.json>`，回 0；不可用回 3，stderr 印一行原因；參數錯 2。
- `meeting.sh prep` 在 `bin/lib/_asr_worker.py` 存在時才呼叫 `stitch`；不存在時直接整檔轉錄。

### 3.10 Swift `Core/` 新名稱（red-swift 依此寫紅燈測試，build 段不得改名）

```swift
// Records.swift
struct CanvasLock: Codable, Equatable { var width: Int; var height: Int }
// RecordStatus：var audioReady: Bool? = nil；var droppedFrames: Int? = nil
// RecordMeta：var canvasLock: CanvasLock? = nil

// Control.swift
enum AutoPrepPick: Equatable { case early(session: String, runId: String), done(session: String, runId: String) }
func autoPrepPick(autoPrep: Bool, status: RecordStatus?, seenInProgressRunIds: Set<String>,
                  enqueuedRunIds: Set<String>) -> AutoPrepPick?
enum PrepOutcome: Equatable { case ok, failed([String]), unknown }
func prepOutcome(pipelineState: Data?, runId: String) -> PrepOutcome
func prepNotification(outcome: PrepOutcome, exitCode: Int32, label: String) -> (title: String, body: String)
func completionNotificationBody(ok: Bool, label: String) -> String
func isAudioReadyLine(_ line: String) -> Bool
func stopPathLogLine(source: String, reason: String) -> String
func asrWorkerShouldStart(finishedSegments: Int, alreadyStarted: Bool, workerScriptExists: Bool,
                          incrementalEnabled: Bool) -> Bool

// BackgroundFinalize.swift
func sessionCodeLabel(startedAt: String, runId: String, timeZone: TimeZone = .current) -> String
// backgroundJobLabel(_:timeZone:) 改呼叫 sessionCodeLabel，輸出逐字不變

// Preflight.swift
enum AudioProbeVerdict: Equatable { case check(SystemAudioCheck), deviceFailed }
func audioProbeVerdict(opened: Bool, targetPeakDBFS: Double, displayPeakDBFS: Double?,
                       thresholdDBFS: Double) -> AudioProbeVerdict
func audioDeviceFailedMessage(input: String, inputTransport: String,
                              output: String, outputTransport: String) -> String

// Control.swift（D3 b，修正輪新增；修正輪 2 依 E2 拿掉 recordPid 參數）
func abnormalStopSession(status: RecordStatus?, pidAlive: Bool, sessionExists: Bool, segmentsPending: Bool) -> String?
func abnormalStopNotification(label: String) -> (title: String, body: String)
```

既有 `shouldAutoPrep(…)`、`SystemAudioCheck`、`systemAudioCheck(…)`、`backgroundJobLabel(…)` 的簽名與行為不變（`TriggerTests`、`PreflightTests`、`R3xBackgroundTests` 不改）。字面：

- `prepNotification`：`.ok`＋0 → (`前處理完成`, `<label>`)；`.failed(s)`＋0 → (`前處理失敗`, `<label>：<s 以「、」連接> 失敗，詳見 autoprep.log`)；`.unknown`＋0 → (`前處理失敗`, `<label>：無法確認結果，詳見 autoprep.log`)；結束碼 ≠ 0 → (`前處理失敗`, `<label>：結束碼 <n>，詳見 autoprep.log`)。
- `completionNotificationBody(ok:true)` → `<label>`；`ok:false` → `<label>：收尾有錯誤，詳見 record.log`。
- `stopPathLogLine` → `停止略過（<source>）：<reason>`。
- `audioDeviceFailedMessage` → `音訊裝置無法啟動（輸入：<input>／<inputTransport>；輸出：<output>／<outputTransport>）`。
- `sessionCodeLabel`：startedAt 可解析 → `M/d HH:mm 開始的場次`；不可解析 → `場次 <runId 前 8 個字元>`。
- `abnormalStopSession`：`status` 非 nil、`phase == .stopping`、`status.pid > 0`、`pidAlive == false`（呼叫端以 `kill(status.pid, 0)` 判斷）、`status.session` 非空、`sessionExists == true`（呼叫端判斷 `status.session` 是存在的目錄）、`segmentsPending == true`（呼叫端依 「段落待收尾」＝`<status.session>/錄音/tracks/` 有 `seg-*.mov`，且 `錄音/tracks/finalize.json` 不存在、或其 `videoPublishedAt` 為 null、或（舊 schema）沒有 `videoPublishedAt` 鍵也沒有 `finishedAt`；有 `videoPublishedAt` 非 null，或舊 schema 有 `finishedAt`，都算已收尾（keep-segments 開著時段落會留著，靠這一項排除））→ 回 `status.session`；其餘回 nil。判定不讀、不依賴 `record.pid`（E2；§4.16）。`segmentsPending` 是使用者 2026-10-21 閘門 2 決定加的條件，用來壓掉收尾後的重複通知（§7 疑慮 15）。
- `abnormalStopNotification` → (`上次錄製異常中止`, `<label>：段落還在，按「收尾」執行 meeting record finish`)。

### 3.11 Python 新名稱

| 檔 | 名稱 | 說明 |
|---|---|---|
| `bin/lib/_record_lib.py` | `update_pipeline_state(sess, updates, timeout=5.0) -> bool`；CLI `state-set <場次> <stage> <status> [--run-id ID]`、`state-begin <場次> <runId> <stage>…` | §4.9 |
| `bin/_record_finalize.py` | `segment_audio_pcm(seg_path, plan_row, work_dir) -> str`（頂層函式，回 48 kHz 雙聲道 PCM 路徑） | 音訊先出與 worker 共用 |
| `bin/_record_finalize.py` | 模組常數 `TAIL_PAD_FPS_FLOOR = 240` | §4.4.12（D3 a） |
| `bin/_diarize_pyannote.py` | `--embed-speaker <wav> <diarization.json> <SPEAKER_xx> <out.json>` | §4.6.4 |
| `bin/_voiceprint.py` | `match`、`add` 新增 `--embeddings <路徑>` | §4.6.3–§4.6.4 |
| `bin/lib/_asr_worker.py` | §3.9 | 新檔 |
| `bin/lib/_transcript_quality.py` | `transcribe.sh` 品質檢查 heredoc 搬過來（asr-robust 的重構 commit） | §4.13 |
| `bin/lib/_record_lib.py` | 公開 `load_json`、`write_json_atomic`、`record_home`（prep-pipeline 加；finalize-fast 改 import）；`paused_total(pauses)` 改成 `_record_finalize.paused_total` 的算法（prep-pipeline；E4(3)） | §4.13.2 |

### 3.12 重放量測報告（`tools/bench/replay.py` 的 stdout JSON）

鍵恰為：`speed`、`segments`、`recordedSeconds`、`stopToAudioReady`、`stopToSpeakersMd`、`stopToWav`、`stopToVideo`、`stopToAllReady`、`verifySeconds`、`workerBacklogAtStop`、`videoPath`、`flow`（`"early"`＝認到「音訊就緒：」就起 prep／`"legacy"`＝等收尾結束才起），比對模式另加 `cer`、`timeAlignedRatio`。秒數取小數 1 位；**不含任何路徑、場次名、視窗標題**。

---

## 4. 驗收條件

表格欄位：條號｜條文（EARS）｜Story｜依據｜驗法（測試 ID）。`swift:` 前綴是 `tools/MeetingRecorder/Tests/MSCoreTests.swift` 的函式；其他是 `tests/record/` 的 Python 測試。

### 4.1 介面與相容性

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.1.1 | `meeting.sh`、`record.sh`、`transcribe.sh`、`diarize.sh`、`_record_finalize.py` 的子指令與結束碼集合應與 §2 相同；既有 `test_surface_parsers`、`test_cli_dispatch`、`test_docs`、`test_record_sh`、`test_r2_cli` 應不改而綠。 | G1–G9 | intent §4.1；`.claude/teams/rules.md` 專案規則 7 | 列出的既有測試 |
| 4.1.2 | 當 §3.7 的環境變數都沒設定時，`meeting.sh prep`、`transcribe.sh`、`diarize.sh` 的介面與輸出檔集合應與 `042c404` 相同（既有轉錄、分離相關測試不改而綠；§4.6–§4.8 的鐵則與失敗判準修正除外）。 | G1 | adr-ms-audio-first | `test_ms_prep.py::test_env_absent_unchanged`；既有 `test_r3_transcript_vad`、`test_deliver_fixes`、`test_t7_fixes` |
| 4.1.3 | 狀態檔與 `record.meta.json` 的新欄位為 nil 時應省略鍵；舊版狀態檔（沒有新鍵）應能解碼。 | G1、G2 | `adr-r2-status-fields.md:24,35` | `swift:testMSStatusFieldsOmittedWhenNil`、`swift:testMSCanvasLockCodable`、`swift:testMSOldStatusDecodes` |
| 4.1.4 | `bin/` 頂層檔數應維持 26（新 Python 檔一律放 `bin/lib/`）。 | G1–G8 | intent §4.1.1 | `bash bin/_lint.sh` |
| 4.1.5 | `Sources/Core/` 不得 import AppKit。 | G5、G9 | meeting-record 慣例 | `test_ms_app_static.py::CoreStatic::test_core_no_appkit` |

### 4.2 音訊先出（Q2；D2）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.2.1 | 當 finalize 開始處理一個有段落的場次時，系統應在任何影片步驟（copy remux、normalize、concat）之前，依 §3.2 的順序寫好 `audio-ready.json`、`finalize.json` 第一階段、正式 wav（`錄音/<同名>.wav`），並在 stdout 印 §3.8 的「音訊就緒：」一行；正式 wav 不得等影片。 | G1 | intent §7 Q2；D2 | `test_ms_audio_first.py::test_wav_published_before_video`（`MH_FFMPEG` 慢速替身記錄呼叫順序：正式 wav 出現時還沒有任何影片步驟的 ffmpeg 呼叫） |
| 4.2.2 | 正式 wav 應為 16000 Hz、1 channel，檔名照 meeting-record §4.6.2；`audio-ready.json` 的鍵與 §3.2 相同，`segments[i].start` 等於前面各段 `duration` 的總和（± 0.001 秒）。 | G1 | §3.2 | `test_ms_audio_first.py::test_ready_json_fields` |
| 4.2.3 | 在 `finalize.json` 第一階段（含 `finishedAt` 與 `outputs.audio`）寫好之前，`錄音/` 第一層不應出現任何音源副檔名的檔；寫好之後正式 wav 才以 `os.replace` 一次出現（R3-§6 第 140 條「先 finalize.json、後 wav」照舊）。 | G1 | §6 第 23 條 | 既有 `test_concurrency.py::test_finalizing_session_not_listed`（不改）；`test_ms_audio_first.py::test_finalize_json_before_wav` |
| 4.2.4 | 當補償模式 ≠ off 時，正式 wav 應等於以 `compensated_audio` 處理後的音訊。 | G1、G4 | C3；`bin/_record_finalize.py:1108-1151` | `test_ms_audio_first.py::test_compensated_wav` |
| 4.2.5 | 若音訊階段之後的影片步驟失敗或逾時（回 5），則已發佈的正式 wav、`audio-ready.json` 與 `finalize.json` 第一階段應保留，`already_done` 不得判為完成（影片不在）；成功時 meeting-record §4.6.20 (ii)「`錄音/*.wav` 與 `影片/*.mov` 音訊軌 duration 差 ≤ 25 ms」仍應成立。 | G1、G4 | §6 第 23 條 | `test_ms_audio_first.py::test_video_failure_keeps_wav`；既有 `test_finalize.py` 的 §4.6.20 測試、`test_r3_finalize_guard.py::test_step_timeout_exits_5_and_keeps_segments`（不改） |
| 4.2.6 | 當正式 wav 已發佈、影片仍在收尾（收尾鎖被持有）時，`meeting.sh prep <場次>` 應照現行方式把該場當成一個場次處理（音源取 `錄音/` 第一層的正式 wav），結束碼照 §2。 | G1 | D2 | `test_ms_prep.py::test_prep_while_video_finalizing` |
| 4.2.7 | （修正輪刪除：正式 wav 直接發佈，不再有 `tracks/audio/` 暫存名稱要清。） | — | D2 | — |
| 4.2.8 | 當錄製器的 `FinalizeRunner` 逐行轉印 finalize 輸出、遇到 `isAudioReadyLine` 成立的一行時，應把該場狀態檔的 `audioReady` 設為 `true`（phase 維持 `finalizing`）。 | G1 | intent §7 Q2；`Capture/FinalizeRunner.swift:93-108` | `swift:testMSIsAudioReadyLine`；`test_ms_app_static.py::CaptureStatic::test_audio_ready_sets_status` |
| 4.2.9 | 當自動前處理開啟、某場狀態 `phase == .finalizing`、`audioReady == true`、`discarded != true`、runId 曾在進行中被看見且尚未排過時，`autoPrepPick` 應回 `.early`；同一 runId 排過 `.early` 之後，`phase == .done` 時不得再回 `.done`；沒排過 `.early` 的場次在 `.done` 時照 `shouldAutoPrep` 的條件回 `.done`。 | G1 | design §3 | `swift:testMSAutoPrepPickEarly`、`swift:testMSAutoPrepPickNoDoubleEnqueue`、`swift:testMSAutoPrepPickDoneFallback`；既有 `TriggerTests`（不改） |
| 4.2.10 | 當 `AutoPrepRunner` 執行 `.early` 或 `.done` 時，子程序指令應為現行的 `meeting.sh prep <場次>`，環境只多 `MH_PREP_RUN_ID=<uuid>`，不得設 `MH_PREP_EARLY`。 | G1、G5 | §3.7 | `test_ms_app_static.py::TriggerStatic::test_autoprep_run_id_env` |
| 4.2.11 | （修正輪刪除：`stages.audio` 出自已被 intent §7 取代的 §5 建議，§7 Q2 的對外呈現只有 `RecordStatus.audioReady`；不另加 stage。） | — | intent §7 Q2 | — |

### 4.3 冪等與中間態（C2）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.3.1 | 當 `record finish` 對已完成的場次再跑一次時，應回 0、印「已完成」，所有輸出檔的 mtime 與內容不變（meeting-record §4.6.6 照舊）。 | G1 | meeting-record §4.6.6 | 既有 `test_finalize.py::test_idempotent_second_run`（不改） |
| 4.3.2 | 當 `audio-ready.json` 的段落清單（檔名、大小、長度）與補償模式和這次相同、且正式 wav 存在時，finalize 不得重寫 wav（mtime 不變）、不得重寫 `finalize.json` 第一階段的 `finishedAt`，直接進影片步驟。 | G1 | §6 第 10 條 | `test_ms_audio_first.py::test_idempotent_mid_state` |
| 4.3.3 | 當 `audio-ready.json` 與這次的段落清單或補償模式不同時，finalize 應重寫正式 wav（先寫 `.part` 再 `os.replace`）、`audio-ready.json` 與 `finalize.json` 第一階段。 | G1 | 同上 | `test_ms_audio_first.py::test_ready_json_stale_rewritten` |
| 4.3.4 | 當 `finalize.json.verify.status == "failed"` 時，`already_done` 不得判為完成；舊 `finalize.json`（沒有 `verify` 鍵）應判為完成。 | G1 | §3.4 | `test_ms_video_copy.py::test_verify_failed_not_done`、`::test_old_finalize_json_is_done` |

### 4.4 影片：畫布鎖定與 copy 串接（Q3）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.4.1 | 開錄時，錄製器應把開錄當下會議視窗的偶數像素尺寸寫進 `record.meta.json.canvasLock`，之後每一段都以這個尺寸開檔；錄製中視窗尺寸改變時只寫一行 log（`視窗尺寸改變：A → B（畫布維持開錄時的 W×H，內容等比縮放）`），不得呼叫 `updateConfiguration` 改尺寸。 | G1 | intent §7 Q3；§6 第 1–3 條 | `test_ms_app_static.py::CaptureStatic::test_canvas_lock_written`、`::test_no_resize_update_configuration`、`::test_next_segment_size_logged`；既有 `test_static_rules.py` 的 `nextSegmentSize(` 檢查（不改） |
| 4.4.2 | 錄製器的 `SCStreamConfiguration` 應設 `scalesToFit = true` 且 `preservesAspectRatio = true`；`minimumFrameInterval` 與擷取尺寸上限依 §4.4.13 的使用者決定，決定前維持 1/60、不設尺寸上限（intent §7 Q3）。 | G1 | intent §7 Q3；D3 d | `test_ms_app_static.py::CaptureStatic::test_preserves_aspect_ratio`；既有 fps 相關測試（不改） |
| 4.4.3 | 當且僅當下列全部成立時，finalize 應走 copy 路徑：meta 有 `canvasLock`；每段都有影片且寬高等於 `canvasLock`；codec、profile、pix_fmt、time_base 全場相同；每段 extradata 雜湊相同；沒有完全相同 PTS 的重複影格。任一不成立時應整場走現行 normalize＋concat，不得逐段混用。 | G1 | adr-ms-video-copy | `test_ms_video_copy.py::test_copy_when_canvas_lock`、`::test_reencode_without_canvas_lock`、`::test_reencode_when_size_mismatch`、`::test_reencode_when_extradata_differs` |
| 4.4.4 | 在 copy 路徑上，`影片/*.mov` 的影片封包資料應與來源逐段相同（不重新編碼影片），`finalize.json.videoPath` 應為 `"copy"`；重編路徑應為 `"reencode"`。 | G1 | §3.4 | `test_ms_video_copy.py::test_copy_packets_identical`、`::test_finalize_json_video_path` |
| 4.4.5 | 在 copy 路徑上，meeting-record §4.6.3（影片與音訊軌 duration 差 < 100 ms）、§4.6.14 (i)(ii)(iii)(iv)（dts 嚴格遞增、解碼無錯、影格數不少於各段總和減重複、間隔 < 1 ms 為 0）、§4.6.20 (i)(ii)（≤ 25 ms）應成立。 | G1、G4 | meeting-record §4.6.3、§4.6.14、§4.6.20 | `test_ms_video_copy.py::test_copy_duration_within_100ms`、`::test_copy_dts_monotonic`、`::test_copy_audio_lengths_25ms` |
| 4.4.6 | concat 呼叫應保留 `-c:v copy`、`-c:a aac -b:a 256k`，且不得含 `+faststart`。 | G1 | design §4.2、§10；§6 第 12 條 | 既有 `test_static_rules.py:505-522`（不改）；`test_ms_video_copy.py::test_no_faststart` |
| 4.4.7 | finalize 對每一段的 ffprobe 呼叫次數應 ≤ 3（含封包掃描）。 | G1 | `b0-audit.md:34`；`bin/_record_finalize.py:619,1161-1162` | `test_ms_video_copy.py::test_probe_calls_per_segment`（計數替身） |
| 4.4.8 | 步驟名應維持 `normalize`／`concat`／`mix`／`probe`；驗證步驟的對象應記成 `verify:<影片檔名>`，抽音訊記成 `seg-NNNN`。 | G5 | `test_r3_finalize_guard.py:22` | 既有 `test_r3_finalize_guard`（不改）；`test_ms_video_copy.py::test_verify_step_label` |
| 4.4.9 | 沒有 `canvasLock` 的場次（含既有合成素材與 2026-10-20 的保留段落）應照現行重編路徑處理，meeting-record §4.6.10 的位元率與補邊判準照舊成立；正式 wav 仍依 §4.2.1 先於影片發佈，不受重編耗時影響。 | G1、G4 | adr-ms-video-copy 選項 B；D2 | 既有 `test_finalize.py`、`test_r2_finalize.py`（不改）；`test_ms_audio_first.py::test_wav_published_before_video` |
| 4.4.10 | （N-3）被中止的段落不得印「改用 libx264」；只有該段以 libx264 重編成功後才印。 | G9 | `b0-audit.md:35`；`bin/_record_finalize.py:855-857,884` | `test_ms_video_copy.py::test_x264_note_only_after_success` |
| 4.4.11 | 實機（test 段）：用新錄製器錄一場 ≥ 30 分鐘、錄製中至少縮放視窗兩次與跨一次 60 秒輪替，`e2e_check.py` 的 `video_format`、`video_covers_audio`、`one_audio_file`、`wav`、`c_canvas` 應 PASS，且 `finalize.json.videoPath == "copy"`；缺陷 B、F、N 的情境照 meeting-record 原判準重驗。 | G1、G4 | intent §7 Q3 | 人工（plan §4） |
| 4.4.12 | （D3 a）重編路徑（含 copy 不成立時的整場退回）的 `normalize` 補尾時，tpad 的補幀數不得只依 `r_frame_rate`／`link_fps` 推算：應以 `ceil((cap − last) × max(link_fps, TAIL_PAD_FPS_FLOOR)) + 1` 計算（`TAIL_PAD_FPS_FLOOR = 240`），多補的複製幀交給現行的夾 cap＋`select` 去重。當段落的 `link_fps` 低於 ffmpeg 實際連結影格率（例 58 對 60）、且最後一幀距段落結束 ≥ 1 秒時，正規化後最後一幀應落在 cap（± 1 tick），`check_norm` 通過、finalize 回 0。 | G4、G5 | `incident-2018-windowserver.md:22-28`；`bin/_record_finalize.py:1233,1254-1256` | `test_ms_video_copy.py::test_tail_pad_low_r_frame_rate`（60 fps 合成段落、末 9 秒靜止，以測試替換模組的 `link_fps` 回 58）；既有 `test_finalize.py` 補尾相關測試（不改） |
| 4.4.13 | （D3 d）擷取幀率（60 或 30 fps）與擷取尺寸上限**不在本 spec 預先定案**：`video-spike` 應量「60 fps 原尺寸」「30 fps 原尺寸」「60 fps＋尺寸上限」三種設定下 WindowServer 的 CPU 負擔，以及各設定的段落走 copy 串接的結果，寫進證據檔並以 `needs_decision` 回報；使用者決定前 `recorder-capture` 不得開工。使用者若選非 60 fps 或加尺寸上限，主 session 先修 §4.4.2 與對應新測試，並在 §6.1 記為 intent §7 Q3「維持 60 fps」的修訂，再派工。 | G1、G3 | D3 d；`incident-2018-windowserver.md:4,18` | `specs/meeting-speed/evidence/video-spike.md` 第 5 節；使用者決定（plan §4） |

### 4.5 驗證移到發佈之後（C9）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.5.1 | finalize 的影片發佈順序應為：影片 rename 進 `影片/` → `manifest.json` → `finalize.json` 第二階段（`videoPublishedAt`、`videoPath`、`verify.status: "pending"`）→ 印「成品就緒：」→ 背景驗證。正式 wav 已在 §4.2.1 發佈，不在這個順序裡、也不等影片。 | G1 | design §4.3；D2 | `test_ms_video_copy.py::test_publish_before_verify`（慢速驗證替身：驗證進行中時影片與正式 wav 都已存在） |
| 4.5.2 | 當驗證通過時，finalize 應把 `verify.status` 設為 `"ok"`、記 `record: done`、刪段落（keep-segments 時保留）、回 0。 | G1 | 同上 | `test_ms_video_copy.py::test_verify_ok_cleans_segments` |
| 4.5.3 | 若驗證失敗或逾時，則 finalize 應把影片改名為 `<同名>.verify-failed.mov`（不刪）、`verify` 記 `{"status":"failed","reason":…,"path":…}`、保留全部段落、stderr 印原因與 `meeting record finish` 提示、回 5；正式 wav 不動。 | G1、G5 | adr-ms-video-copy 選項 X | `test_ms_video_copy.py::test_verify_failed_renamed` |
| 4.5.4 | 當上一次是 copy 路徑驗證失敗、再跑 `record finish` 時，finalize 應強制走重編路徑。 | G1 | 同上 | `test_ms_video_copy.py::test_verify_failed_rerun_forces_reencode` |
| 4.5.5 | `record stop` 的等待語意與結束碼不變（仍等整個收尾含驗證）；驗證失敗時錄製器照現行 `completionOutcome` 寫 `phase=failed, code=5`。 | G1、G5 | intent §4.1 | 既有 `test_r3_lock`、`test_record_sh`（不改） |
| 4.5.6 | `.claude/skills/meeting-record/SKILL.md` 應寫明：正式 wav 先於影片出現（影片可能仍在收尾）、`.verify-failed.mov` 的意義與再跑 `meeting record finish` 的處理、畫布鎖定的代價（開錄後放大視窗不會提高解析度）。 | G1、G5 | 專案規則 7 | `test_ms_docs.py::test_record_skill_speed_notes` |

### 4.6 鐵則（G6）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.6.1 | `diarize.sh` 跑完後，場次資料夾內不得出現 `embeddings.json`；embedding 只存在 `mktemp` 建的暫存檔，聲紋比對結束（含失敗）時刪除。 | G6 | intent §7 embedding；adr-ms-embeddings-temp | `test_ms_iron_rules.py::test_no_embeddings_in_session`、`::test_embeddings_temp_removed`（`_diarize_pyannote.py` 以替身取代） |
| 4.6.2 | `speakers.map.json` 的套名判準只有一套：有 `apply` 聽 `apply`；沒有 `apply` 時 `confidence ≥ 0.7` 才套，**沒有 `confidence` 的 dict 視為未確認、不套**；字串值直接套。聲紋比對寫 `apply: true` 的條件是 cos ≥ `RENAME_TH`（預設 0.75），0.60–0.75 只寫線索、不套（專案規則 3 作用在 `apply` 的產生端）。`_merge_speakers.py` 與 `_render.py` 的判準一致。 | G6 | intent §5 預設 2；§6 第 15 條 | `test_ms_iron_rules.py::test_confidence_missing_not_applied`（兩支程式各驗）；既有 `test_r3_vtt_raw.py::test_render_copy_matches_merge`（不改） |
| 4.6.3 | 當 speakers.map 某講者的既有值是非空字串，或是 `evidence` 不以「聲紋庫比對」開頭的 dict 時，`_voiceprint.py match` 不得覆蓋它；只有上一次聲紋比對寫的 dict 可被信心更高的新結果取代。 | G6 | `bin/_voiceprint.py:115-118` | `test_ms_iron_rules.py::test_string_mapping_kept`、`::test_manual_dict_kept`、`::test_voiceprint_dict_replaced_by_higher` |
| 4.6.4 | 當 `_voiceprint.py add <場次> <SPEAKER_xx> <姓名>` 沒有 `--embeddings` 時，應先讀舊場次的 `錄音/embeddings.json`（只讀）；沒有就呼叫 `_diarize_pyannote.py --embed-speaker` 把該講者向量算到暫存檔，建檔後刪除；diarize venv 不在時回 2 並提示 `bash bin/setup-diarize.sh`。聲紋只寫進 `vault/voiceprints/`。 | G6 | adr-ms-embeddings-temp | `test_ms_iron_rules.py::test_add_recompute_temp_removed`（`MH_EMBED_SPEAKER_CMD` 替身）、`::test_add_reads_legacy_embeddings`；既有 `test_review_fixes.py`（不改） |
| 4.6.5 | `_voiceprint.py remove` 應拒絕含路徑分隔、`..` 或不在 `vault/voiceprints/` 內的名稱，回 2。 | G6 | `bin/_voiceprint.py:172` | `test_ms_iron_rules.py::test_remove_rejects_path` |
| 4.6.6 | `transcribe.sh` 不得改寫 `transcript.raw.md`（內容與 mtime 在 `_to_tw.py` 步驟前後相同）；正體版另存 `transcript.md`，只在 `transcript.md` 不存在時寫；`transcript.segments.json` 照舊轉字形。 | G6 | 鐵則 1；`bin/transcribe.sh:194-201` | `test_ms_asr_robust.py::test_raw_not_converted`、`::test_transcript_md_not_overwritten`、`::test_segments_still_converted`；SKILL 說明：`test_ms_docs.py::test_transcribe_skill_raw_policy`（`.claude/skills/meeting-transcribe/SKILL.md` 寫明 raw 不轉、`transcript.md` 是正體版） |
| 4.6.7 | `.claude/skills/meeting-speakers/SKILL.md` 應含 annotate 步驟（`_render.py <場次> --annotate-speakers`），並寫明舊 `embeddings.json` 的手動清法；`.claude/skills/meeting-summary/SKILL.md` 不得再寫 embedding 存在場次資料夾。 | G6 | `.claude/skills/meeting-speakers/SKILL.md:42-46` | `test_ms_docs.py::test_speakers_skill_annotate`、`::test_summary_skill_no_session_embeddings` |
| 4.6.8 | `.gitignore` 應含 `embeddings.json`、`speakers.map.json`、`transcript.quality.json`、`.pipeline-state.lock`。 | G6 | design §9 | `test_ms_iron_rules.py::test_gitignore_entries` |
| 4.6.9 | `_diarize_pyannote.py` 應在寫 `diarization.json` 之前設定 `meta["embeddings"]`。 | G6 | `research-code-contracts.md:54` | `test_ms_iron_rules.py::test_meta_embeddings_before_dump`（AST 檢查） |
| 4.6.10 | `config.json` 應有 `transcribe.incremental.enabled: true`；`diarize.note`（若有）不得再寫 embedding 存在場次資料夾或 `embeddings.json`。 | G2、G6 | §3.6；adr-ms-embeddings-temp | `test_ms_iron_rules.py::test_config_keys` |

### 4.7 ASR 失敗看得到（G5）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.7.1 | 當 ASR 引擎回 0、但工作目錄沒有非空的 `.json` 時，`transcribe.sh` 應判為該引擎失敗、清掉這次輸出、走既有退回鏈；全部引擎都失敗時照舊回 3。 | G5 | `b0-audit.md:43-44`；`bin/transcribe.sh:115-133` | `test_ms_asr_robust.py::test_exception_exit0_triggers_fallback`（`fakes/asr_exc0/mlx_whisper`） |
| 4.7.2 | ASR 引擎的完整輸出應寫到 `$WORKDIR/asr.log`；失敗時 stderr 印最後 30 行（不再 `| tail -8`）。 | G5 | `bin/transcribe.sh:132` | `test_ms_asr_robust.py::test_asr_log_tail_30` |
| 4.7.3 | `transcribe.sh` 應保留 mlx_whisper CLI 這道接縫；既有替身 `fakes/asr/mlx_whisper` 與四支 argv 斷言應不改而綠。 | G5 | intent §7 Q4 | 既有 `test_r3_transcript_vad`、`test_r3_vtt_raw`、`test_deliver_fixes`、`test_t7_fixes`（不改） |
| 4.7.4 | 當 `MH_ASR_SEGMENTS_JSON` 指向存在的 JSON 時，`transcribe.sh` 不得呼叫任何 ASR 引擎，raw 標頭、`transcript.segments.json`、正體保險栓與品質檔應走與整檔轉錄相同的程式產出。 | G1 | adr-ms-incremental-asr | `test_ms_asr_robust.py::test_segments_json_input_skips_asr` |

### 4.8 前處理並行與成敗判斷（G1、G5）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.8.1 | 當一場要做講者分離時，prep 應在轉錄開始前於背景啟動 `diarize.sh`，轉錄（與 OCR）結束後 `wait`，兩者都成功才 merge＋annotate。 | G1 | design §6 | `test_ms_prep.py::test_diarize_parallel_with_transcribe`（兩個替身各睡 2 秒，總耗時 < 3.5 秒，且 merge 在兩者之後） |
| 4.8.2 | 每次 prep 處理一場時，應先以 `state-begin` 寫 `prep: {runId, startedAt, expect}`，之後寫的每個 stage 都帶同一個 `runId`。 | G5、G7 | §3.5 | `test_ms_prep.py::test_state_begin_run_id`、`::test_stages_carry_run_id` |
| 4.8.3 | 當 `diarize.sh` 失敗時，prep 應寫 `diarize: failed`（現行只在 merge 失敗才寫）。 | G5 | `bin/meeting.sh:274` | `test_ms_prep.py::test_diarize_failure_recorded` |
| 4.8.4 | （§6 第 13、20 條，使用者 2026-10-21 核准）當 `meeting diarize`／prep 的分離步驟缺 `transcript.segments.json` 時，系統應印「✗ 缺 transcript.segments.json，先跑 meeting.sh prep <場次>（或 transcribe）再分離」、不呼叫 ASR、`run_diarize` 回 1 並記 `diarize: failed`。 | G5 | C8；`bin/meeting.sh:247-273` | `test_ms_prep.py::test_missing_segments_explicit_error`；修改後的 `test_r3_vtt_raw.py::test_diarize_keeps_raw`（第 20 條） |
| 4.8.5 | 不論轉錄、OCR、分離是否失敗，`meeting.sh prep` 的結束碼語意應與 `042c404` 相同（失敗仍回 0）。 | G5 | intent §4.5 | `test_ms_prep.py::test_prep_exit_zero_on_stage_failure` |
| 4.8.6 | `prepOutcome` 應在 `prep.runId` 等於這次、`expect` 的每個 stage 都是 `done` 且帶同一 `runId` 時回 `.ok`；有任何一個不是時回 `.failed([stage…])`（依 `expect` 順序）；讀不到檔、JSON 壞、`prep.runId` 不同時回 `.unknown`。 | G5 | design §6 選項 A | `swift:testMSPrepOutcomeOk`、`swift:testMSPrepOutcomeFailed`、`swift:testMSPrepOutcomeUnknown` |
| 4.8.7 | 當 `AutoPrepRunner` 的 prep 結束時，應讀該場 `.pipeline-state.json` 交給 `prepOutcome`，再用 `prepNotification` 決定通知標題與內文；只有 `.ok` 且結束碼 0 時發「前處理完成」。 | G5 | intent §4.5 | `swift:testMSPrepNotification`；`test_ms_app_static.py::TriggerStatic::test_prep_outcome_read` |
| 4.8.8 | （§6 第 14、19 條，使用者 2026-10-21 核准）輸入已是 16 kHz 單聲道 wav 時，`diarize.sh` 應跳過轉檔。 | G1 | design §14 | `test_ms_iron_rules.py::test_diarize_skips_16k_conversion` |

### 4.9 狀態檔加鎖（G7）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.9.1 | 所有寫 `.pipeline-state.json` 的程式（`meeting.sh state_set`、`_record_finalize.set_state_done`）應經 `_record_lib.update_pipeline_state`：取 `.pipeline-state.lock` 的 flock、讀後合併、mkstemp＋rename。 | G7 | `adr-r3-defaults-writers.md:26-30` | `test_ms_prep.py::test_state_set_atomic_flock`（20 個並發寫者各寫不同 stage，最後全部都在、JSON 合法）、`::test_finalize_set_state_uses_lock` |
| 4.9.2 | 若等鎖超過 5 秒，則 `update_pipeline_state` 應放棄該次寫入、stderr 印一行警告、回 `False`，呼叫端照常繼續。 | G7 | 同上 | `test_ms_prep.py::test_state_lock_timeout_warns` |
| 4.9.3 | 既有的 `_state.py`（`meeting status`）應能讀含 `prep` 鍵的新檔，照列所有 stage。 | G7 | `research-code-contracts.md:104` | `test_ms_prep.py::test_status_reads_new_state` |

### 4.10 preflight 與停止路徑（G5）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.10.1 | 當 preflight 的 probe stream 開不起來時，`audioProbeVerdict` 應回 `.deviceFailed`；第 5 項（`system_audio_rms`）的訊息應為 `audioDeviceFailedMessage(…)`，結束碼 4；第 6、12 項應記「略過（音訊裝置無法啟動）」而不是失敗。開得起來時應等於 `.check(systemAudioCheck(…))`。 | G5 | `b0-audit.md:6-11`；`Capture/PreflightRunner.swift:238,417-431`；`Core/Preflight.swift:87-92` | `swift:testMSAudioProbeDeviceFailed`、`swift:testMSAudioProbePassthrough`、`swift:testMSAudioDeviceFailedMessage`；`test_ms_app_static.py::CaptureStatic::test_preflight_device_failed`；既有 `PreflightTests`（不改） |
| 4.10.2 | 當 `startCapture` 失敗時，`record.log` 應記錄錯誤的 domain、code 與輸入／輸出裝置名稱。 | G5 | `RecordingSession.swift:206,216` | `test_ms_app_static.py::CaptureStatic::test_start_capture_error_logged` |
| 4.10.3 | `MenuBar.swift` 的 `stopRecording`、`performStop`、`cancelFinalize`、`cancelBackgroundFinalize`、`hudStop`，`HUD.swift` 的 `stopPressed`，`Onboarding.swift` 的 `sendStop`，與 `PreflightRunner.swift` 的兩處提早 return，每一個提早 return 前都應寫一行 `stopPathLogLine(…)` 的 log；`stopTargetDecision(` 的呼叫形狀不變。 | G5 | `b0-audit.md:12-16` | `swift:testMSStopPathLogLine`；`test_ms_app_static.py::TriggerStatic::test_stop_paths_logged`、`CaptureStatic::test_preflight_returns_logged`；既有 `test_r3_app_static.py`（不改） |

### 4.11 增量轉錄（Q5；G2、G4）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.11.1 | 當第一段收尾、`bin/lib/_asr_worker.py` 存在且 `config.json` 的 `transcribe.incremental.enabled` 不是 false 時，錄製器應以 `/usr/bin/nice -n 10 <record.defaults.json 的 python3> <harness>/bin/lib/_asr_worker.py run <場次>` 起 worker 一次（`qualityOfService = .utility`，不經 `zsh -l`）。 | G2 | adr-ms-incremental-asr | `swift:testMSAsrWorkerShouldStart`；`test_ms_app_static.py::CaptureStatic::test_worker_started_after_first_segment` |
| 4.11.2 | worker 應只處理 `manifest.json` 中 `finishedAt` 不是 null 的段落；同一場只能有一個 worker（`worker.lock`）。 | G2 | 同上 | `test_ms_incremental_asr.py::test_reads_finished_segments_only`、`::test_single_worker_lock` |
| 4.11.3 | 第 k 窗的切點應取第 k 段最後 8 秒內、以與整檔轉錄相同的 VAD 參數（`levels_intervals`）算出的兩個有聲區間之間最晚那個靜音區間的中點；找不到時在段尾硬切。窗與窗不得重疊，拼接時不去重。 | G2、G4 | intent §7 Q5 | `test_ms_incremental_asr.py::test_cut_at_silence`、`::test_cut_hard_when_no_silence`、`::test_windows_non_overlapping` |
| 4.11.4 | 在本場錄製期間，若 `droppedFrames` 大於 worker 起來時的值，則 worker 應不再開新窗、`state.json` 記 `paused`／`drops`，直到本場 phase 離開 `recording`／`stopping`；錄製中若有別場背景收尾的 pid 還活著，也不得開新窗（`otherFinalizing`）。 | G2 | intent §7 Q5；design §11 | `test_ms_incremental_asr.py::test_pause_on_drops_until_stop`、`::test_pause_when_other_finalizing` |
| 4.11.5 | 當本場 phase 變成 `finalizing`／`done`／`failed` 時，worker 應補完所有欠的窗，最後一窗延伸到最後一段結尾，寫 `state.json.status = "complete"` 後結束。 | G2 | 同上 | `test_ms_incremental_asr.py::test_completes_after_stop` |
| 4.11.6 | worker 在一次執行中只載入模型一次（`mlx_whisper.transcribe()` in-process）。 | G1 | `plan-approved.md:89` | `test_ms_incremental_asr.py::test_model_loaded_once`（`fakes/pymod/mlx_whisper` 計數） |
| 4.11.7 | `stitch` 應在下列全部成立時回 0 並寫出與 mlx_whisper 同 schema 的 JSON：`state.json.status == "complete"`；窗涵蓋的段落清單與 `audio-ready.json`（沒有時用 `finalize.json.inputs`）相同；`params` 與這次 `transcribe.sh` 會用的相同；補償模式為 off。worker 還活著且 60 秒內有心跳時應先等它完成。任一不成立應回 3 並印原因。 | G1、G4 | intent §7 Q5 | `test_ms_incremental_asr.py::test_stitch_ok_schema`、`::test_stitch_param_mismatch_exit3`、`::test_stitch_incomplete_exit3`、`::test_stitch_waits_live_worker` |
| 4.11.8 | 當 `stitch` 回 0 時，prep 應以 `MH_ASR_SEGMENTS_JSON` 交給 `transcribe.sh` 而不呼叫 ASR 引擎；回 3 或 worker 檔不存在時整檔轉錄。 | G1 | §3.9 | `test_ms_prep.py::test_prep_uses_stitched`、`::test_prep_falls_back_full` |
| 4.11.9 | **品質門檻（使用者 2026-10-21 核准，D5）**：以同一場整檔轉錄為參照，增量結果的字差異率（CER，去標點後逐字）≤ 5%，且對齊後每個字的時間差 ≤ 1.0 秒的比例 ≥ 95%。只在重放量測時離線比對，不是執行期的採用條件。 | G4 | intent §7 Q5；D5 | `tools/bench/replay.py --compare-full` 的 `cer`、`timeAlignedRatio`（plan §4）；計算邏輯 `test_ms_replay.py::test_compare_metrics` |
| 4.11.10 | 實機（test 段）：錄一場 ≥ 30 分鐘的會議，期間 worker 在跑，狀態檔最後的 `droppedFrames` 應為 0（或沒有這個鍵）；停止當下 `state.json` 欠的窗數記進 progress.md。 | G2 | intent §7 Q6 | 人工（plan §4） |

### 4.12 通知改用場次代號（G9）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.12.1 | `sessionCodeLabel` 的輸出應與 §3.10 字面相同；`backgroundJobLabel` 的輸出不變。 | G9 | `Core/BackgroundFinalize.swift:189-200` | `swift:testMSSessionCodeLabel`；既有 `R3xBackgroundTests`（不改） |
| 4.12.2 | 前處理的三則通知（完成、失敗、沒有執行）的標題與內文不得含場次名或路徑，內文以 `sessionCodeLabel` 開頭。 | G9 | intent §7；`Trigger/Completion.swift:132,138,172,180,182` | `swift:testMSPrepNotification`；`test_ms_app_static.py::TriggerStatic::test_prep_notifications_no_name`（`Completion.swift` 不得再用 `lastPathComponent` 組通知內文） |
| 4.12.3 | 錄製實例的完成通知（`RecordingSession.swift:1248-1250`）與 menu bar 的完成通知（`MenuBar.swift:1129`）的內文應為 `completionNotificationBody(…)`，不得含 `session.path`、`st.session` 或 `outcome.message`；`"會議錄製完成"` 字面與 `Notifier.post(` 照舊在同一函式（既有 `test_r3_skip_finalize` 不改）。「在 Finder 顯示」用的 `userInfo["session"]` 保留。 | G9 | intent §6、§7 | `swift:testMSCompletionNotificationBody`；`test_ms_app_static.py::CaptureStatic::test_completion_body_no_path`、`TriggerStatic::test_menubar_completion_body_no_session` |
| 4.12.4 | 實機（test 段）：一場錄製完成與自動前處理完成後，通知中心的兩則通知文字不含場次名、視窗標題或路徑。 | G9 | meeting-record §4.39.3 的理由 | 人工（plan §4） |

### 4.13 結構重構（G8；各檔擁有者在速度改動之後的獨立 refactor commit）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.13.1 | `wc -l` 判定：`MenuBar.swift` ≤ 1000、`RecordingSession.swift` ≤ 1000、`PreflightRunner.swift` 的 `run` 函式本體 ≤ 80 行、`bin/_record_finalize.py` ≤ 1300；`record.sh` 的 `cmd_control` 本體 ≤ 100 行；`transcribe.sh` 不再含品質檢查的 heredoc（搬到 `bin/lib/_transcript_quality.py`）。 | G8 | design §13 | `test_ms_refactor.py::test_line_limit_menubar`、`::test_line_limit_recording_session`、`::test_preflight_run_length`、`::test_line_limit_record_finalize`、`::test_cmd_control_length`、`::test_transcribe_no_quality_heredoc` |
| 4.13.2 | `bin/_record_finalize.py` 不得自行定義 `paused_total`、`write_json_atomic`、`load_json`、`record_home`，改由 `bin/lib/_record_lib.py` import（模組內名稱照舊可用）；範圍只到這一組（`b0-audit.md:56-62`）。**`paused_total` 以 `_record_finalize.py` 的算法為準（使用者 2026-10-21 決定，E4(3)）**：依序掃事件，`pause` 一律把起點設為該筆的 `t`（連續兩個 `pause` 取後一個），`resume` 有起點才累加 `resume.t − 起點` 並清掉起點；沒有前導 pause 的 resume、最後沒配對的 pause 不計；`t` 以 `float()` 解析、非有限值或解析失敗略過；小數 3 位（`bin/_record_finalize.py:570-575,749-762`）。`_record_lib.paused_total` 改成同一算法、不再經 `pause_pairs`；`pause_pairs`、`output_time` 與共用向量 `tests/record/vectors/output_time.json` 不變。**這是對 `_record_lib.paused_total` 呼叫端的行為變更**（連續兩個 pause 時由「先 pause 為起點」改為「後 pause 為起點」；`t` 是數字字串時由略過改為解析），受影響的呼叫端（`042c404`，`grep -rn "paused_total" bin tests tools`）：(1) `bin/_record_finalize.py:1537` 寫 `manifest.gapStats.pausedTotal`——改 import 後輸出與現行逐字相同；(2) `tests/record/test_r3_record_lib.py:127-134`——三組輸入都沒有連續 pause、`t` 都是數字，結果不變、不改；`bin/` 其他檔與 Swift 都不呼叫 `_record_lib.paused_total`（`bin/_render.py:410` 只用 `pause_pairs`）。另有兩份同名實作不在本條範圍、本輪不改：`tests/record/e2e_check.py:344`、Swift `Core/Control.swift:186` 的 `pausedTotal`（兩者都以先 pause 為起點，§7 疑慮 14）。順序：`red-py` 先寫鎖定 `_record_finalize.paused_total` 現行行為的測試（Red 層就綠）→ `prep-pipeline` 改 `_record_lib.paused_total` → `finalize-fast` 改 import。`harness_config` 三份合一**移出本 epic**（修正輪 2）：既有、不得改的 `tests/record/test_review_fixes.py:96-101` 的 `copy_with_config` 只把單支 `_profile.py`／`_voiceprint.py` 複製到暫存 `repo/bin/`，改 import `bin/lib/_harness.py` 後複製出去的腳本找不到模組；在各檔保留 fallback 又等於仍有多份定義，合一沒有意義。列為衍生工作（不編號）。`bin/_record_prompt.py:45` 的 `load_json` 本輪不併（衍生工作（不編號））；`meeting.sh` 的 HF token 檢查是 bash，不在範圍。 | G8 | `b0-audit.md:56-62`；`bin/_record_finalize.py:749-762`；`bin/lib/_record_lib.py:113-134`；`tests/record/test_review_fixes.py:96-101`；E4(3) | `test_ms_refactor.py::test_record_helpers_single_definition`（只看 `_record_finalize.py` 與 `_record_lib.py`）、`::test_paused_total_finalize_locked`（以 `[pause 10, pause 20, resume 50]`→30.0、`[pause 70, resume 100, pause 150]`→30.0、`[resume 5]`→0、`[]`→0、`t` 為 `"10"` 的字串等輸入鎖定 `_record_finalize.paused_total` 現行輸出；Red 層就綠）、`::test_paused_total_record_lib_matches_finalize`（同一組輸入，`_record_lib.paused_total` 的輸出與上一支的期望值相同）；既有 `test_r3_record_lib`、`test_review_fixes`（不改） |
| 4.13.3 | 重構以獨立 commit（`refactor(meeting-speed)`）做在同一子任務的速度／修正 commit 之後；重構 commit 前後該子任務的完成條件測試都應綠（行為不變）。被既有靜態測試釘住的函式與字面應留在原檔；重構不得需要改既有測試。若非改不可，該子任務停下回報，由主 session 一次送使用者核准（§6 第 22 條）。 | G8 | intent §2 G8、§7 Q4 | 全量測試；重構 commit 的 `git diff --diff-filter=M --name-only <commit>~ <commit> -- tests/ tools/MeetingRecorder/Tests/` 為空 |
| 4.13.4 | README 的流程圖應反映音訊先出、轉錄與分離並行、增量轉錄；`record.sh:973`、`transcribe.sh:3`、`_merge_speakers.py:3` 的過期註解更新（三支各自一個測試，對應各檔的擁有者）；`.claude/workflows/meeting-pipeline.js` 檔頭標示棄用並指向 `meeting-summary`。 | G8 | `plan-approved.md:105-106` | `test_ms_docs.py::test_readme_flow`、`::test_stale_comment_transcribe`、`::test_stale_comment_merge_speakers`、`::test_stale_comment_record_sh`、`::test_meeting_pipeline_js_deprecated` |

### 4.14 量測（G1、G2、G4）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.14.1 | `tools/bench/replay.py <段落目錄> [--speed N] [--no-worker] [--compare-full] [--legacy]` 應在暫存區建沙盒場次（名稱「[Stand-up] 範例專案」）與沙盒 `MH_RECORD_HOME`，依各段 `startedAt`／`finishedAt` 的間隔除以 N 依序放入段落並更新 manifest，最後一段放完算「停止」，起 `_record_finalize.py`；認到「音訊就緒：」就起 `meeting.sh prep <沙盒場次>`（只帶 `MH_PREP_RUN_ID`），`--legacy` 或沒有這一行時等收尾結束再起。`stopToWav` 取正式 wav 出現在 `錄音/` 第一層的時刻。 | G1 | intent §7 Q6 | `test_ms_replay.py::test_speed_schedule`、`::test_early_flow`、`::test_legacy_flow`（替身） |
| 4.14.2 | 報告應符合 §3.12，不得含任何路徑、場次名或來源目錄名。 | G1 | 公開 repo | `test_ms_replay.py::test_report_keys`、`::test_report_no_paths` |
| 4.14.3 | **每層量測（逐字稿線）**：每層合併後以 `--speed 10` 重放 2026-10-20 的 2 小時段落（121 段）一次，報告數字寫進 progress.md。這批段落沒有 `canvasLock`、影片走重編，`stopToVideo` 只記錄、不判定。 | G1 | intent §7 Q6；D2 | 主 session（plan §4） |
| 4.14.4 | **最終驗收（G1）。量法經使用者 2026-10-21 在閘門 2 前核准（D2）**，拆兩條線：(i) **逐字稿線**：`--speed 1` 重放 2026-10-20 的 2 小時段落（121 段）一次，`stopToSpeakersMd ≤ 300` 且 `stopToWav ≤ 300`（正式 wav 依 §4.2.1 先於影片發佈，舊段落走重編不影響這兩個數字）。(ii) **影片線**：用新錄製器（`record.meta.json` 有 `canvasLock`）錄的實錄段落量 `stopToVideo`；實錄不足 121 段時依段數線性外推：外推值＝實測 `stopToVideo` × 121 ÷ 實錄段數，外推值 ≤ 300；外推值 > 240 秒時再補錄一場 ≥ 2 小時的會議實測，以實測值為準（門檻使用者 2026-10-21 確認，E4(2)）。(i)(ii) 都成立才算 G1 達成。 | G1 | intent §7 Q1、Q6；D2 | 主 session＋使用者（plan §4） |

### 4.15 迴歸與 verify（D4：使用者 2026-10-21 核准）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.15.1 | 每個子任務完成時（有 refactor commit 的，在 refactor commit 之後）都應跑下列四件套，並符合 plan §2〈共通〉的判準：(a) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0；(b) `/bin/bash tools/MeetingRecorder/Tests/run.sh` 回 0；(c) Python 全量 `$PY -m unittest discover -s tests/record -t .` 沒有 `FAIL:`／`ERROR:`，輸出沒有 `ImportError`、`ModuleNotFoundError`、`SyntaxError`、`NameError`；(d) 名稱掃描：本子任務的 diff 與 commit 訊息以 `grep -qiF -f <client-names.txt>` 檢查，只回報有／沒有，結果須為「沒有」。**(b)(c) 的例外只有兩個，統稱「允許仍紅」（使用者 2026-10-21 核准，E3）**：(i) red-swift 階段——`MSCoreTests.swift` 已在本分支或本層開工時的 `feature/meeting-speed`、`ms-core` 尚未合併（Red 層的 `red-swift`，與第 1 層 `ms-core` 以外的子任務）——Swift `run.sh` 只因缺 §3.10 名稱而編譯失敗（每一行 `error:` 都是缺 §3.10 的名稱）；(ii) 每層開工時 plan §3 列的允許仍紅清單（Red 層的 `red-py` 與第 1 層用 R0、第 2 層用 R1、第 3 層用 R2）內、由本子任務以外的子任務（後續層或同層其他子任務）負責轉綠的測試允許仍紅；本子任務完成條件列的測試不得紅。清單外任何紅燈一律失敗。 | 全部 | intent.md:92-96（§2 末段「驗收時每個子任務都要過」）；D4；E3 | plan §2〈共通〉的四條指令 |
| 4.15.2 | 每層合併後，plan §3 該層列的指令都應回 0；全量的紅燈只能是 plan §3 該層「合併後允許仍紅」欄列的測試（也就是下一層的開工清單），Swift 編譯失敗只能出現在 Red 層合併後（例外 (i)）。 | 全部 | 專案規則 verify | plan §3 |
| 4.15.3 | 新增與修改的檔案、commit 訊息不得含 `client-names.txt` 列的名稱（只回報有／沒有）。 | 全部 | intent §4.1 | `test_ms_docs.py::test_no_client_names_in_ms_files`（不得 skipped） |

### 4.16 異常中止後的接手（D3 b、c；G5）

背景：2026-10-21 晚間 WindowServer 重啟、GUI session 重建，錄製器在收尾前結束；最後一段沒收尾、共享狀態停在 `stopping`（`incident-2018-windowserver.md:3-14`）。判定只用共享狀態檔 `record.status.json` 記錄的 `pid`、`phase`、`session`，**不依賴 `record.pid`**（使用者 2026-10-21 決定，E2）：`meeting record stop` 遇到 `record.pid` 的 pid 已死時會刪掉 `record.pid`（`bin/record.sh:822,829`），使用者先按停止、再跑 `finish` 或重開選單時 `record.pid` 往往已不在。不新增狀態檔或 phase；CLI 與選單用同一套條件。

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.16.1 | Core `abnormalStopSession` 的輸出應與 §3.10 字面相同（`phase == .stopping`、狀態檔記錄的 pid 已不在、場次目錄存在、段落待收尾才回場次路徑；不看 `record.pid`）。 | G5 | D3 b；E2；閘門 2 | `swift:testMSAbnormalStopDetected`、`swift:testMSAbnormalStopNotWhenAlive`、`swift:testMSAbnormalStopNotWhenOtherPhase`、`swift:testMSAbnormalStopNotWhenSessionMissing`、`swift:testMSAbnormalStopNotWhenNoStatus`、`swift:testMSAbnormalStopNotWhenNoPendingSegments` |
| 4.16.2 | 當選單 app 啟動時，應讀 `record.status.json`、以 `kill(status.pid, 0)` 判斷狀態檔記錄的程序是否還在、判斷 `status.session` 是否為存在的目錄、依 §3.10 判斷段落待收尾，交給 `abnormalStopSession`（不讀 `record.pid`）；回非 nil 時，應發一則 `abnormalStopNotification(label: sessionCodeLabel(…))` 的通知並提供「收尾」動作，按下才以現行執行 `meeting.sh` 的方式跑 `meeting.sh record finish <場次>`（不自動跑）；通知文字不得含場次名或路徑。 | G5、G9 | D3 b；E2；meeting-record §4.39.3 的理由 | `swift:testMSAbnormalStopNotification`；`test_ms_app_static.py::TriggerStatic::test_abnormal_stop_checked_on_launch`（`Trigger/` 有呼叫 `abnormalStopSession(` 與 `kill(`，且呼叫 `abnormalStopSession(` 的函式本體不含 `record.pid`）、`::test_abnormal_stop_notification_no_name` |
| 4.16.3 | 當 `meeting record finish` 不帶參數時，若 `<record home>/record.status.json` 的 `phase == "stopping"`、`pid` 是正整數且 `kill -0 <pid>` 失敗、`session` 是存在的目錄、且段落待收尾（定義同 §3.10），則應在 stderr 印一行「· 接手異常中止的場次：<路徑>」後照 `finish <場次>` 執行，結束碼照現行 {0,2,3,5}；`record.pid` 存在與否、內容為何都不影響判定（E2）；任一條件不成立時照舊印「✗ 少了場次目錄…」回 2。 | G5 | D3 c；E2；`bin/record.sh:822,829,1199-1202` | `test_ms_record_finish.py::test_no_arg_uses_abnormal_session`、`::test_no_arg_after_stop_removed_pid_file`（沒有 `record.pid`、狀態檔 pid 已死、phase＝stopping → 接手）、`::test_no_arg_without_status_exit2`、`::test_no_arg_live_pid_exit2`、`::test_no_arg_other_phase_exit2`、`::test_no_arg_session_missing_exit2`、`::test_no_arg_already_finalized_exit2`（段落還在但 `finalize.json` 的 `videoPublishedAt` 非 null → 回 2） |
| 4.16.4 | `record.sh` 的 usage 與子指令列不改（`finish <場次>` 照舊，既有 `test_docs`、`test_surface_parsers` 不改）；不帶參數的接手行為寫進 `.claude/skills/meeting-record/SKILL.md`。 | G5 | 專案規則 7 | `test_ms_docs.py::test_record_skill_finish_no_arg`；既有 `test_docs`、`test_surface_parsers`（不改） |

---

## 5. 影響系統

| 系統／檔案 | 改動 | 子任務 | 對外影響 |
|---|---|---|---|
| `bin/_record_finalize.py` | 音訊先出（正式 wav 先發佈、`finalize.json` 兩階段）、copy 路徑、驗證後移、ffprobe 合併、N-3、補尾幀數（D3 a） | finalize-fast（含拆檔） | stdout 多兩行；`finalize.json` 多三鍵；正式 wav 比影片早出現；結束碼不變 |
| `bin/meeting.sh` | prep 並行、`state-begin`、stitch 交棒、`diarize` 失敗記錄、C8 | prep-pipeline | 子指令與結束碼不變；`.pipeline-state.json` 多 `prep` 鍵 |
| `bin/lib/_record_lib.py` | `update_pipeline_state`、CLI `state-set`／`state-begin`；公開共用 helper；`paused_total` 改用 `_record_finalize` 的算法（§4.13.2） | prep-pipeline | 內部；`paused_total` 對連續兩個 pause 的結果改變（呼叫端只有 `_record_finalize.py` 與既有 `test_r3_record_lib`，兩者結果不變） |
| `bin/transcribe.sh` | 成功判準、`asr.log`、raw 不轉、`MH_ASR_SEGMENTS_JSON` | asr-robust（含 heredoc 抽出） | 結束碼不變；多寫 `transcript.md`（只在不存在時） |
| `bin/diarize.sh`、`_diarize_pyannote.py`、`_merge_speakers.py`、`_render.py`、`_voiceprint.py` | embedding 暫存、confidence、覆蓋規則、remove 過濾、16k 跳過（`harness_config` 合一移出本 epic，§4.13.2） | diarize-iron | 場次資料夾不再有 `embeddings.json`；沒有 confidence 的 dict 不再掛名 |
| `config.json` | 加 `transcribe.incremental.enabled`（預設 true）；`diarize.note` 不再寫 `embeddings.json` | diarize-iron | 多一個設定鍵 |
| `bin/lib/_asr_worker.py`（新） | 增量轉錄 | incremental-asr | 內部 |
| `tools/MeetingRecorder/Sources/Core/` | §3.10（含異常中止判定） | ms-core | 狀態檔 Optional 鍵 |
| `tools/MeetingRecorder/Sources/Capture/` | 畫布鎖定、`preservesAspectRatio`、`droppedFrames`、`audioReady`、起 worker、preflight 裝置失敗、停止路徑 log、完成通知；擷取幀率／尺寸上限依 §4.4.13 的決定 | recorder-capture（含拆 `RecordingSession.swift`、`PreflightRunner.run`） | 成品解析度停在開錄時視窗大小 |
| `tools/MeetingRecorder/Sources/Trigger/` | `.early` 觸發、`prepOutcome`、通知、停止路徑 log、啟動時偵測異常中止並一鍵收尾 | trigger-ui（含拆 `MenuBar.swift`） | 通知文字改用場次代號；多一則異常中止通知 |
| `.claude/skills/meeting-record/`、`meeting-transcribe/`、`meeting-speakers/`、`meeting-summary/` | 行為說明 | finalize-fast、asr-robust、diarize-iron | 改 repo 的 SKILL 等於改全域（專案規則 7） |
| `tools/bench/`（新） | 重放量測工具 | replay-bench | 測試工具，不是對外介面 |
| `.gitignore`、`README.md`、`.claude/workflows/meeting-pipeline.js` | 見 §4.6.8、§4.13.4 | diarize-iron、docs-cleanup | 無 |
| `bin/record.sh` | `finish` 不帶參數接手異常中止的場次（§4.16.3）；結構重構（`cmd_control` 拆函式、`record.sh:973` 註解） | record-sh-split | 子指令、usage 與結束碼集合不變 |
| 下游知識庫專案 | `summary.md` 格式不動 | — | 不必驗 `_missing_sections()`（`_render.py` 只改套名判準，不改輸出段落） |

---

## 6. 整合修訂與例外

### 6.1 被取代或修訂的 meeting-record 條文

第 1–17 條：使用者 2026-10-21 在閘門 2 前核准（D1）。第 23 條：使用者 2026-10-21 確認（E1）。第 24 條：使用者 2026-10-21 確認（E2）。

| 第 n 條 | 原條文（meeting-record） | 本 epic 的修訂 | 理由／出處 |
|---|---|---|---|
| 1 | §4.3.2：每段寬高＝該段開檔時會議視窗像素；輸出畫布＝各段最大寬高 | 有 `canvasLock` 的場次：每段寬高＝`canvasLock`（開錄當下視窗像素）；輸出畫布＝各段最大寬高（等於 `canvasLock`，e2e `c_canvas` 照舊成立）。沒有 `canvasLock` 的舊場次照原條文 | intent §7 Q3（修訂 D8 (i)） |
| 2 | §4.3.4：縮放後下一段反映新尺寸；收尾置中補邊不縮放 | **推翻**（新錄製器）：錄製中縮放視窗不改段落尺寸，內容由 SCK `scalesToFit`＋`preservesAspectRatio` 等比縮進固定畫布、補邊。代價（使用者在閘門 1 接受）：開錄後放大視窗，成品解析度停在開錄時的大小 | intent §7 Q3 |
| 3 | §6 第 5 條（D8）：每段用當下視窗像素、收尾統一成各段最大寬高 | 修訂 (i) 為「整場鎖開錄當下視窗像素」；(ii) 因各段一樣大而不必做；「畫布＝`displayPixelSize()`」仍作廢 | intent §7 Q3 |
| 4 | §6 第 63 條：幕前調度開啟時 preflight 只提醒、「錄製中尺寸跟隨不變」 | preflight 提醒不變；「尺寸跟隨」改為「鎖開錄當下尺寸」：若開錄當下會議視窗是側邊縮圖，整場都是縮圖尺寸（比原本更嚴重，§7 疑慮 5） | 由第 2 條連帶 |
| 5 | §6 第 16 條（D7）：整支重編、位元率 ≥ 原片最大值 × 1.5、下限 8 Mb/s | copy 路徑：影片不重編、位元率等於來源；重編退回路徑照原條文 | intent §7 Q3（修訂 D7） |
| 6 | §4.6.10：位元率 ≥ 各段最大值、H.264 high profile 等 | 只適用重編路徑；copy 路徑改以 §4.4.4（封包逐段相同）驗 | 同上 |
| 7 | `adr/adr-video-tail-pad.md:22-31` 選項 C（copy）不採 | 整場條件全部成立時採 copy；仍不逐段混用 | adr-ms-video-copy |
| 8 | `adr/adr-segment-writer.md:44`：每段以當下視窗像素開檔 | 同第 1 條 | adr-ms-video-copy |
| 9 | §4.6.5：wav 以同一檔案系統內的 rename 一次出現 | **修正輪撤回**：D2 之後正式 wav 直接以 `os.replace` 一次出現（不再用 hard link），§4.6.5 的 rename 字面照舊；時點提前的部分改記在第 23 條 | D2 |
| 10 | §4.6.6：兩個輸出都在才算已完成 | 另認中間態：`audio-ready.json` 與這次輸入相同、正式 wav 在、影片不在時不重寫 wav、只補影片；`verify.status == "failed"` 不算完成；沒有 `verify` 鍵的舊檔算完成 | C2；§4.3 |
| 11 | §4.6.20 與現行實作：wav 由串接結果抽出 | wav 改由各段 PCM 產出（補償時用 `compensated_audio`），判準 (ii) ≤ 25 ms 不變 | C3 |
| 12 | 現行實作（`bin/_record_finalize.py:1487-1509`）：串接帶 `+faststart`；解碼驗證失敗回 5、成品不發佈 | 拿掉 `+faststart`；驗證移到發佈之後，失敗時改名 `.verify-failed.mov`、回 5（§4.5）。meeting-record §6 第 65 條「`-c:a aac -b:a 256k` 一次編碼」不變 | C4（只取 `+faststart` 部分）、C9 |
| 13 | §4.29.3：缺 `transcript.segments.json` 時在暫存目錄重轉、之後 `segments.json` 要存在 | 改為明確報錯、不重轉（§4.8.4）。**使用者 2026-10-21 核准（D1）** | C8 |
| 14 | §4.12.4、§4.46.3：`diarize.sh`、`_merge_speakers.py` 與 `main` 完全相同 | 鐵則修正改在這兩支檔的源頭（§4.6.1、§4.6.2、§4.6.9）；`diarize.sh` 的 16k 跳過轉檔（§4.8.8）一併放行。**使用者 2026-10-21 核准（D1）**。D1 一併放行的 `MH_DIARIZE_AUDIO` 在修正輪已不需要（§3.7），`diarize.sh` 不加 | intent §7 Q4；D1 |
| 15 | §4.29.2：`_render.py` 照抄 `_merge_speakers.main` 的套名判準（`confidence` 預設 1.0 的行為隨之照抄） | 沒有 `confidence` 的 dict 視為未確認、不套名；兩支程式一起改。代價：舊場次重跑 render，原本沒有 confidence 的 dict 對應不再掛名 | intent §5 預設 2；§4.6.2 |
| 16 | meeting-record intent（`specs/meeting-record/intent.md:386-397`）：即時轉錄與拆檔本輪不做 | 已由使用者 2026-10-21 的決定取代（增量轉錄）；不需另行核准，僅記錄 | intent §4.2 末段 |
| 17 | §4.39.3、R3-§6 第 135 條：錄製中告警通知不得含場次名 | **擴大適用**到錄製完成、前處理完成／失敗／沒有執行、異常中止的通知（§4.12、§4.16.2）；原條文不變 | intent §7 R2 完成通知 |
| 23 | §4.6.5、R3-§6 第 140 條、`bin/_record_finalize.py:22`（模組說明第 7 步「最後才把 wav rename 進 錄音/——場次在這一刻才存在」）；intent §7 Q2「正式 wav 照舊在最後一刻 rename 進 `錄音/`」 | **使用者 2026-10-21 確認（E1）**：正式 wav 在音訊階段、任何影片步驟之前發佈（§4.2.1）；「先寫 `finalize.json`、wav 後出現」的順序不變（§4.2.3），`finalize.json` 改兩階段寫入，`finishedAt` 的意義改為「錄音成品發佈時刻」、另加 `videoPublishedAt`（§3.4）。「場次存在」從「收尾全部完成」改為「錄音成品就緒（影片可能仍在收尾）」；據此修訂 meeting-record §4.6.5、R3-§6 第 140 條，以及 intent §7 Q2「正式 wav 照舊在最後一刻 rename 進 `錄音/`」一句（intent.md 本身不改，以本條為準）。既有 `test_concurrency.py` 不改（它的 `published()` 讀 `finishedAt`＋`outputs.audio`，第一階段就成立）。代價：影片收尾期間 `meeting status`、`meeting prep <根>` 會列出該場（§7 疑慮 11） | D2（使用者 2026-10-21：正式 wav 必須先於影片發佈、不等影片）；E1（使用者 2026-10-21 確認本條） |
| 24 | meeting-record spec §2（`specs/meeting-record/spec.md:42`）：`record finish` 缺參數 → 2 | **使用者 2026-10-21 確認（E2）**：缺參數、且共享狀態檔記錄的 pid 已不在、phase＝stopping、場次目錄存在、段落待收尾（使用者 2026-10-21 閘門 2 加）時，stderr 印一行說明後接手該場次（§4.16.3；不依賴 `record.pid`）；沒有可接手的場次時照舊 2。結束碼集合 {0,2,3,5} 不變，usage 不改 | D3 c；E2 |

### 6.2 既有測試的修改（逐條；第 18–21 條使用者 2026-10-21 核准（D1），由 `red-py` 改，其他子任務一律不改）

| 第 n 條 | 測試 | 現行斷言 | 修改後 | 等價的新守門 | 核准狀態 |
|---|---|---|---|---|---|
| 18 | `tests/record/test_regression.py::test_diarize_and_merge_untouched` | `git diff --exit-code main -- bin/diarize.sh bin/_merge_speakers.py` 回 0 | 刪除這支斷言（函式整支移除） | `test_ms_iron_rules.py::test_diarize_merge_interface_kept`：兩支檔的結束碼集合（`diarize.sh` {0,2,3,4,5}）、參數形式與輸出檔名不變；既有 `test_r3_vtt_raw` 的 6 組套名 fixture 照舊綠 | 已核准（D1）。鐵則修正與 16k 跳過直接改 `diarize.sh`、`_merge_speakers.py`；不另設 `bin/lib/` 新入口 |
| 19 | 同上（16k 跳過，連帶第 14 條後段） | — | 隨第 18 條一併生效 | `test_ms_iron_rules.py::test_diarize_skips_16k_conversion` | 已核准（D1） |
| 20 | `tests/record/test_r3_vtt_raw.py::test_diarize_keeps_raw` | 缺 segments.json 時呼叫轉錄替身、之後段落檔存在、輸出目錄不是場次目錄、回 0 | 改為：raw 內容與 mtime 不變（保留）、**不呼叫**轉錄替身、`meeting diarize` 回 1、stdout 或 stderr 含「缺 transcript.segments.json」 | 新斷言仍守住鐵則 1（raw 不變）；另由 `test_ms_prep.py::test_missing_segments_explicit_error` 驗。這支只靠 `meeting.sh` 的 `run_diarize` 轉綠，歸 `prep-pipeline` 的完成條件 | 已核准（D1） |
| 21 | `tests/record/test_r3_lock.py::test_stop_wait_limit_covers_finalize_deadline` | `(100, 930, 932)`、`(3600, 11430, 11432)` | 改為 `(100, 930, 936)`、`(3600, 11430, 11436)` | 下限不變（仍守住 ≥ 3×elapsed＋630）；上限放寬的理由：`startedAt` 只到秒（`%S`），小數被截掉最多 1 秒，加上子程序啟動時間，`int(3 × elapsed ＋ 630)` 可多出 3 × (1＋啟動秒數)；+2 只容得下約 0.67 秒的總誤差。+6 容 2 秒 | 已核准（D1） |
| 22 | 結構重構（§4.13）要改的既有測試 | — | 預估 **0 條**（design §13 原則）。若 build 中發現非改不可，該子任務停下以 `needs_decision` 回報，主 session 把清單一次送使用者核准後，補記在本表 | — | 預留；未送核准前該處重構不做 |

`tests/record/test_r3x_parallel_finalize.py` 的 ResourceWarning（PIPE 沒關）**不在本輪修**，列為衍生工作（不編號）；`_lint.sh` 不加 `-W error::ResourceWarning`，所以不需要改測試。

---

## 7. 疑慮

1. **關鍵路徑餘裕不到 1 分鐘**：講者分離實測 infer 204.9 秒（`baseline.md` A 節），加上音訊就緒時間（未量測）與 merge，推算 4–4.5 分（design §2.2）；mlx 與 pyannote 並行搶 GPU 的影響未量測（intent §4.4）。回報點：第 2 層量測後 `stopToSpeakersMd > 300` 時，主 session 停下回報使用者，可選的下一步是 (a) 加大分離的 batch（`_diarize_pyannote.py` 參數，需另開子任務）、(b) 增量轉錄改在停止後暫停 worker 讓出 GPU、(c) 接受實測值。本 spec 不預先決定。
2. **影片 5 分鐘的量法**（D2 已核准，§4.14.4 (ii)）：2026-10-20 的保留段落是 D8 錄的（各段尺寸不同），走不到 copy 路徑；影片只能用新錄製器的段落量。實錄不足 121 段時以段數線性外推；copy remux 與 concat 主要是 I/O，線性假設合理但未驗證，所以外推值 > 240 秒時補一場 ≥ 2 小時的實錄（E4(2)）。
3. **`aac_at` 不採**（design §10）：若第 2 層量到影片超過 5 分而 `aac_at` 能補回，另開核准改 `test_static_rules.py:505-522`。
4. **錄製中的 `levels` 落盤時機**：`manifest.levels` 每 0.5 秒在記憶體累加（`RecordingSession.swift:715`），段落收尾時 `writeManifest()`（`:697`）一起落盤，所以 worker 讀得到該段結尾前的 levels；最後 0.5 秒窗可能還沒寫入，切點找不到時硬切（§4.11.3）。
5. **畫布鎖定的代價**：開錄後放大視窗，成品解析度停在開錄時；開錄當下視窗是幕前調度縮圖時整場都小（§6 第 4 條）。`preservesAspectRatio` 在 macOS 15 的預設與行為、SCK 段落（VFR、`time_base=1/600`）copy 串接是否乾淨，由 `video-spike` 先實測；實測不可行時 `finalize-fast`、`recorder-capture` 停下回報，不自行改做法。
6. **重算向量與分離當下的向量不會位元相同**（adr-ms-embeddings-temp）：同一模型、同一批時段，差異應很小，未量測；聲紋建檔後的比對率由使用者實際使用觀察。
7. **N-4（前景退回路徑沒有整合測試）不做**：前景退回在 Capture 層（`RecordingSession.swift:1180`），`Tests/run.sh` 只編 Core，要整合測試得先為 Capture 建測試骨架，超出本 epic；列為衍生工作。
8. **87 分鐘場收尾比 2 小時場久的原因未查**（`baseline.md` B 節）：第 1 層量測時拆開記 normalize 單段耗時；copy 路徑上線後不在關鍵路徑上。
9. **pyenv shim**：worker 用 `record.defaults.json` 的 python3、不經 `zsh -l`；但 `AutoPrepRunner` 跑的 prep（含 `stitch`）仍走 `zsh -l`，若 shim 卡住，prep 本身就會卡住（現況問題，衍生工作）。
10. **三方資源分配**：錄製 ＞ 背景收尾（錄製中平行度 2，沿用 R3x-D9）＞ worker（nice 10、有別場背景收尾就不開新窗、丟幀就暫停）。錄製中編碼負擔與 worker 搶 CPU／GPU 的實際影響只能靠 §4.11.10 的實錄確認。
11. **正式 wav 提早發佈的副作用**（§6 第 23 條）：影片收尾期間場次已可被 `meeting status`／`meeting prep <根>` 列出。若使用者或其他 session 在這段時間手動對整個根目錄跑 prep，會與自動前處理重複轉錄同一場（不會壞資料：raw 照鐵則 1 不原地改寫，`.pipeline-state.json` 有鎖；但浪費一次轉錄）。本 epic 不加互斥，列為觀察項。
12. **擷取幀率與尺寸上限未定**（§4.4.13）：WindowServer 高負載是 2026-10-21 異常中止的背景（`incident-2018-windowserver.md:4,18`），但降到 30 fps 會修訂 intent §7 Q3「維持 60 fps」。由 `video-spike` 量完回報使用者，`recorder-capture` 等決定才開工。
13. **早期模式拿掉**（§3.7）：D1 放行了「早期模式的 `MH_DIARIZE_AUDIO` 改 `diarize.sh`」，但 D2 讓正式 wav 在音訊階段就出現，prep 讀正式 wav 即可，早期模式（`tracks/audio/`、`MH_PREP_EARLY`、`MH_TRANSCRIBE_REC_DIR`、`MH_DIARIZE_AUDIO`）全部多餘。**使用者 2026-10-21 確認拿掉（E4(1)）**；連同 hard link 發佈一併不做。
14. **`paused_total` 仍有三種實作**（§4.13.2，E4(3)）：本輪把 `_record_lib` 統一成 `_record_finalize` 的算法（連續兩個 pause 取後一個），但 `tests/record/e2e_check.py:344` 與 Swift `Core/Control.swift:186` `pausedTotal` 仍以先 pause 為起點；錄製器在已暫停時不會再寫一筆 pause（`RecordingSession.swift:806` 的 `guard !gate.paused`；`Core/Control.swift:214-215` 的 `appendingPauseEvent` 遇到與最後一筆同種類的事件直接回原陣列），正常錄製不會產生連續兩個 pause，所以實際結果一致。改 `e2e_check.py` 要改既有測試工具、改 Swift 要動 `R3RecordLibVectorTests` 的共用向量，本輪不做，列為衍生工作（不編號）。
15. **異常中止通知重複（已處理）**（§4.16.2）：收尾成功不會改寫共享狀態檔，只看狀態檔會在收尾後重複通知；使用者 2026-10-21 閘門 2 決定 CLI 與選單都加「段落待收尾」條件（§3.10），收尾完成（`videoPublishedAt` 非 null）或段落已清掉後就不再通知、`finish` 不帶參數回 2。
16. **`kill -0` 的 pid 重用**（§4.16）：狀態檔記錄的 pid 若已被別的程序重用，`kill -0` 會成功、判為「還在」而不接手；這是安全側的錯失（使用者仍可用 `meeting record finish <場次>`），不另處理。

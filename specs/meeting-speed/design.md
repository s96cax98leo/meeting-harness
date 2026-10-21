# design：meeting-speed（停止錄製後 5 分鐘內就緒＋全專案重構）

- 上游：`specs/meeting-speed/intent.md`（閘門 1 已核准，2026-10-21；**§7 是決定全文，取代 §5 的建議**）。
- 下游：`spec.md`（驗收條件）、`plan.md`（子任務、檔案、測試對應）、`progress.md`、`adr/`（四則）。
- 狀態：**草稿，待閘門 2 核准**。
- 行號以 `042c404` 為準（`git log --oneline -1 origin/main`）；可用 `sed -n '<行>p' <檔>` 重跑核對。
- 本檔的 MS-D1…MS-D16 只是本檔內的決策編號，**不是任務編號**；G1–G9 沿用 intent §2 的目標代號，spec 用它們當 Story ID。
- 範例場次名一律用「[Stand-up] 範例專案」。
- `specs/_templates/` 不存在（`ls specs/` 只有 `meeting-record`、`meeting-speed`），四份文件沿用 `specs/meeting-record/` 的格式。

---

## 0. 結論先講

1. **關鍵路徑改成「音訊先出 → 前處理（轉錄與分離並行）」與「影片 copy 串接」兩條平行線**，驗證移到成品發佈之後。2 小時場的推算關鍵路徑見 §2；最緊的一段是講者分離（實測 204.9 秒，`baseline.md` A 節），5 分鐘的餘裕約 1 分鐘以內。
2. **錄製中的增量轉錄**由錄製器在開錄時起一個低優先權的 Python worker（`bin/lib/_asr_worker.py`），只讀 `manifest.json` 已收尾的段落，模型只載一次；停止後只剩最後一窗。
3. **閘門 1 的八項決定全部落成條文**（spec §4），被推翻或修訂的 meeting-record 條文逐條列在 spec §6.1（第 1–17 條）；要改的既有測試逐條列在 spec §6.2（第 18–22 條），全部標「待閘門 2 核准」（第 22 條是第 4 層的預留條，預估 0 條）。
4. **拆成 15 個子任務、Red＋4 層**（§1；明細在 `plan.md` §1）。同一層的檔案不重疊；跨層只有第 4 層兩個重構子任務接手前面層的檔案，以 `depends_on` 串成序列。
5. **契約夠用，沒有新端點**。新增的都是：狀態檔的 Optional 欄位、場次資料夾內的新檔、只給內部呼叫的環境變數、stdout 新增一行。`meeting.sh`／`record.sh`／`transcribe.sh`／`diarize.sh`／`_record_finalize.py` 的子指令與結束碼集合都不變（spec §2）。

---

## 1. 子任務拆分（MS-D1）

### 1.1 起點與調整

起點是 `plan-approved.md:35-107` 的 12 個子任務、4 層。依 intent §7 與檔案歸屬做了下列調整：

| 計畫原本 | 本設計 | 理由 |
|---|---|---|
| docs-cleanup 在第 4 層 | 移到第 3 層，只擁有 `README.md`、`.claude/workflows/meeting-pipeline.js` | 它擁有的檔沒有別人碰；過期註解交給各檔的擁有者（`transcribe.sh:3`＝asr-robust、`_merge_speakers.py:3`＝diarize-iron、`record.sh:973`＝split-scripts） |
| incremental-asr 改 `meeting.sh` 的 prep 讀取、改 `config.json` | `meeting.sh` 的 stitch 呼叫端由 `prep-pipeline` 寫（worker 檔不存在就跳過，spec §3.9）；`config.json` 的 `transcribe.incremental.enabled` 由 `diarize-iron` 一併加（它本來就要改 `diarize.note` 的 embedding 說明） | `incremental-asr` 只擁有新檔 `bin/lib/_asr_worker.py`，不必和第 1 層串鏈 |
| （沒有） | 新增 `red-py`、`red-swift`（Red 層，kind=test） | `sdlc-build` 先寫紅燈測試；派工單要求 test 子任務擁有 tests/ |
| preflight-diag、stop-gate、audio-first 的 Swift 部分各自改 Core | 新增 `ms-core`：獨佔 `Sources/Core/` | `Tests/run.sh` 一次編譯整個 Core（`research-code-contracts.md:137`），紅燈測試引用的 Core 名稱散在多個子任務就沒有任何一個子任務能單獨跑綠；R3 的 `r3-core` 是同一個理由（`specs/meeting-record/plan.md` §10.1） |
| state-lock、prep-parallel 分開，都改 `meeting.sh` | 合併成 `prep-pipeline` | 兩者改同一支 `meeting.sh` 的 prep 段，`state_set` 換成加鎖寫入正好是並行化的前提；分開就得串成鏈、多一層 |
| audio-first、video-copy 都改 `_record_finalize.py` | 合併成 `finalize-fast` | 音訊先出與影片 copy 都在 `finalize_locked`（`bin/_record_finalize.py:1379-1565`）同一個流程裡重排步驟；分開會在同一函式上序列改兩次 |
| video-copy 的錄製端、audio-first 的 Swift 端、preflight-diag 的 Capture 端 | 依目錄分成 `recorder-capture`（Capture/）與 `trigger-ui`（Trigger/） | `RecordingSession.swift`、`MenuBar.swift` 在速度層各只有一個擁有者，不必串鏈 |
| 計畫沒寫 | 新增 `video-spike`（kind=check） | intent §7 Q3：「`preservesAspectRatio` 和 copy 串接要先實測」 |
| 計畫沒寫 | 新增 `replay-bench`（重放量測工具） | intent §7 Q6：每一層都用加速重放量，最終做一次 1× |
| prep-parallel 的 `diarize.sh`、`_diarize_pyannote.py` | 併進 `diarize-iron` | 跟鐵則修正改同兩支檔；都受 `test_diarize_and_merge_untouched` 管（spec §6 第 18 條） |
| asr-robust 的 `meeting.sh:247-273` 靜默重轉 | 移到 `prep-pipeline` | 那段在 `meeting.sh`，`prep-pipeline` 才擁有它 |
| iron-rules 的 `_to_tw.py` 原地改寫 raw | 移到 `asr-robust` | 改的是 `transcribe.sh:194-201`，`asr-robust` 擁有 `transcribe.sh` |
| R2「完成通知含場次路徑」（衍生工作） | 併進 `recorder-capture`（`RecordingSession.complete`）與 `trigger-ui`（`MenuBar.postCompletion`、`Completion.swift`） | intent §7 最後一項：併進 G9 |
| stop-gate「StopGate.evaluate 取代 5 處 `stopTargetDecision(`」 | 改為只補 log，不改呼叫形狀 | `test_r3_app_static.py:128-137,209,320` 要求 `MenuBar.swift`、`HUD.swift` 原樣含 `stopTargetDecision(`；intent §7 Q4「速度與一般修正繞開既有測試」 |
| docs-cleanup 的 `_lint.sh` 加 `-W error::ResourceWarning` | 不做（衍生工作） | 疑似來源在測試檔（`b0-audit.md:208`），修它要改既有測試；本輪不修，列為衍生工作（spec §6.2 末段） |

數量從 12 變 15，增加的三個（`ms-core`、`video-spike`、`replay-bench`）與兩個紅燈子任務都說得出不能併進別人的理由；減少的兩個是合併（state-lock＋prep-parallel、audio-first＋video-copy 的 finalize 端）。

### 1.2 分層

| 層 | 子任務 | 相依 |
|---|---|---|
| Red | `red-py`、`red-swift` | — |
| 1 | `ms-core`、`asr-robust`、`diarize-iron`、`prep-pipeline`、`video-spike`、`replay-bench` | — |
| 2 | `finalize-fast`、`recorder-capture`、`trigger-ui` | 見 plan §1 |
| 3 | `incremental-asr`、`docs-cleanup` | `incremental-asr`：`finalize-fast`、`prep-pipeline`、`asr-robust`、`diarize-iron`；`docs-cleanup`：`finalize-fast`、`prep-pipeline` |
| 4（結構重構） | `split-swift`、`split-scripts` | 各自接手的檔案的前一個擁有者 |

**跨層接手**（只有第 4 層）：`bin/_record_finalize.py`＝finalize-fast(2) → split-scripts(4)；`bin/transcribe.sh`＝asr-robust(1) → split-scripts(4)；`bin/meeting.sh`、`bin/lib/_record_lib.py`＝prep-pipeline(1) → split-scripts(4)；`bin/_voiceprint.py`、`bin/_diarize_pyannote.py`＝diarize-iron(1) → split-scripts(4)；`MenuBar.swift`＝trigger-ui(2) → split-swift(4)；`RecordingSession.swift`、`PreflightRunner.swift`＝recorder-capture(2) → split-swift(4)。第 1–3 層之間沒有任何共用檔。

---

## 2. 關鍵路徑與 5 分鐘預算（G1）

### 2.1 新做法

```
錄製中   每段收尾 → manifest.json 寫 finishedAt → ASR worker 轉錄（nice 10；丟幀就暫停到停止）
停止 ─┬→ finalize：分析各段 → 逐段抽 PCM 混音 → 16k wav 寫進 錄音/tracks/audio/ → 印「音訊就緒：…」
      │      └→ 錄製器把 status.audioReady 設 true → menu bar 立刻排 prep（MH_PREP_EARLY=1）
      │             ├ 轉錄：worker 補最後一窗 → stitch → transcribe.sh 讀現成段落（MH_ASR_SEGMENTS_JSON）
      │             └ 講者分離：背景跑 diarize.sh（MH_DIARIZE_AUDIO 指向同一支 wav）
      │             → wait → merge → annotate → transcript.speakers.md
      └→ finalize 繼續：影片 -c:v copy（逐段 remux＋PCM）→ concat（-c:v copy -c:a aac）
             → 影片 rename 進 影片/、finalize.json、wav hard link 進 錄音/（成品就緒）
             → 背景驗證（整支解碼＋dts）→ 通過才刪段落、記 record: done
```

### 2.2 預算（推算；實測值待每層量測寫進 progress.md）

| 段 | 改之前（實測，`baseline.md` A 節） | 改之後（推算依據） |
|---|---|---|
| 停止 → 音訊就緒 | 約 20 分 16 秒（等收尾全部做完） | 分析 121 段（ffprobe 合併後每段 ≤ 3 次、平行 3）＋逐段抽音訊（只解音訊、平行 3）＋串 16k wav。**未量測**，`replay-bench` 第 1 次量時拆開記 |
| 轉錄 | 5 分 56 秒（整檔） | 只剩最後一窗（≤ 68 秒音訊，§5）＋stitch；worker 欠段時另計 |
| 講者分離 | infer 204.9 秒 | 不變（整場跑一次）；與轉錄並行，GPU 爭用的影響**未量測**（intent §4.4） |
| merge＋annotate | log 未單列 | 不變 |
| 影片 | normalize 16.5 分＋concat 149.1 秒＋驗證 48.7 秒 | copy 路徑：逐段 remux（不重編影片）＋concat（AAC 一次編、拿掉 `+faststart`）。**未量測**，`video-spike` 量 concat 部分 |

最緊的是「音訊就緒時間＋講者分離＋merge」。若第 2 層量完發現超過 5 分，spec §7 疑慮 1 列了回報點與可選的下一步（分離加大 batch、`MH_DIARIZE_EMB_BATCH`）。

---

## 3. 音訊先出（MS-D2；ADR `adr/adr-ms-audio-first.md`）

intent §7 Q2：wav 先寫到 `錄音/tracks/`，自動前處理直接讀它；正式 wav 照舊最後一刻進 `錄音/`；「場次存在＝錄製完成」不變。

- **位置**：`錄音/tracks/audio/<場次名> <YYYY-MM-DD HH.MM.SS>.wav`。檔名與正式 wav 相同（`session_stamp` 只看段落，`bin/_record_finalize.py:824`），所以逐字稿標頭的「來源」不必改寫。放進 `tracks/audio/` 子目錄而不是 `tracks/` 本層，因為 `transcribe.sh:65-70` 會數同一層的影音檔，`tracks/` 本層有 `seg-*.mov`，會被判成「多音檔」而不套 VAD。
- **伴隨檔** `錄音/tracks/audio/ready.json`：記下這支 wav 對應的段落清單（檔名＋大小＋長度＋在成品時間軸上的起點）、補償模式、stamp。冪等判斷與增量轉錄的對齊都靠它（spec §3.2）。
- **產法**：沿用 `audio_graph`（`bin/_record_finalize.py:894-915`）與正規化相同的原點與 `-t`，逐段抽出 48 kHz 雙聲道 PCM；補償模式 ≠ off 時沿用 `compensated_audio`（`:1108-1151`），它本來就只吃 `good`、`plan`、`work`、`total`，不依賴影片正規化結果，可以提前。整條 PCM 再轉 16 kHz 單聲道。影片的音軌照舊用同一份 PCM（copy 路徑由逐段 PCM 組 norm；重編退回路徑沿用現行 `normalize`），所以 §4.6.20 (ii) 的 ≤ 25 ms 判準仍適用。
- **對外呈現**：finalize 在 stdout 印一行 `音訊就緒：錄音/tracks/audio/<檔名>`；`FinalizeRunner` 逐行轉印時認出這一行，呼叫 `status.update { $0.audioReady = true }`（`Capture/FinalizeRunner.swift:93-108` 已在逐行讀）。Python 不寫狀態檔，維持 `research-code-contracts.md:101` 的單一寫者。`.pipeline-state.json` 加 `audio: done`。
- **觸發**：Core 新增 `autoPrepPick`，在 `phase == .finalizing && audioReady == true` 時回 `.early`；原本的 done 路徑保留（同一 runId 只排一次）。`AutoPrepRunner` 對 `.early` 加環境變數 `MH_PREP_EARLY=1`、`MH_PREP_RUN_ID=<uuid>`。
- **prep 怎麼吃**：`meeting.sh prep <場次>` 在 `MH_PREP_EARLY=1` 且 `錄音/` 第一層沒有音檔、`錄音/tracks/audio/ready.json` 存在時，把該場當成一個場次、音源取 `tracks/audio/` 那支 wav；轉錄時帶 `MH_TRANSCRIBE_REC_DIR=<場次>/錄音`（讓 VAD 讀得到 `tracks/manifest.json`），分離時帶 `MH_DIARIZE_AUDIO=<wav>`。沒有 `MH_PREP_EARLY` 時行為與現在完全相同（其他 session 呼叫不受影響）。
- **正式 wav**：finalize 發佈時用 `os.link` 把 `tracks/audio/` 那支 wav 掛到 `錄音/<同名>.wav`（同一檔案系統、一次出現，不複製資料）；`link` 失敗才退回「複製成 `.part` 再 rename」。prep（early 模式）結束時，若正式 wav 與 `tracks/audio/` 那支是同一個 inode（`os.path.samefile`），就移除 `tracks/audio/` 那個名稱（資料仍在正式 wav）；否則保留。
- **冪等的中間態**（C2）：`ready.json` 的段落清單、補償模式與這次相同、wav 存在 → 不重寫（mtime 不變），直接進影片步驟。影片失敗回 5 時，下一次 `record finish` 只補影片。

## 4. 影片 copy 路徑、畫布鎖定、驗證後移（MS-D3、MS-D4；ADR `adr/adr-ms-video-copy.md`）

intent §7 Q3：開錄時鎖定當下的視窗像素，整場固定，60 fps；全場符合條件就 `-c:v copy`、碼率等於來源；不符合就整場退回現行重編。

### 4.1 錄製端
- `RecordingSession.init` 已在開錄時算 `curSize`（`RecordingSession.swift:124`）。改成：之後每段都用這個尺寸開檔；`startNewSegment` 照舊呼叫 `nextSegmentSize(`（`test_static_rules.py:368-374` 釘住這個呼叫），算出的新尺寸只寫一行 log「視窗尺寸改變：A → B（畫布維持開錄時的 W×H，內容等比縮放）」，**不再** `updateConfiguration`（`:526-534`）。
- 設 `cfg.preservesAspectRatio = true`（`scalesToFit` 已是 true，`:176`）。目標 macOS 版本上這個屬性的行為由 `video-spike` 先實測。
- `record.meta.json` 加 Optional `canvasLock: {width, height}`（nil 省略鍵，照 `adr-r2-status-fields.md:35`）。**finalize 只對有 `canvasLock` 的場次考慮 copy 路徑**；舊場次（D8 錄的，或測試合成的段落）一律走現行重編。這樣既有 `test_finalize.py` 的合成素材全部照舊走重編路徑，§4.6.10 的「位元率 ≥ 各段最大值」等斷言不受影響（Q4：速度相關改動繞開既有測試）。

### 4.2 收尾端
- **copy 條件**（全部成立才走）：meta 有 `canvasLock`；每段都有影片、寬高等於 `canvasLock`；codec、profile、pix_fmt、time_base 全場相同；每段 extradata（SPS/PPS）雜湊相同（`ffprobe -show_streams -show_data_hash`）；沒有完全相同 PTS 的重複影格（`dups == 0`）。任一不成立 → 整場走現行 `normalize`＋concat（`b0-audit.md:201-202`：copy 段與重編段不能混用）。
- **逐段 remux**：影片 `-c:v copy`、以與音訊相同的原點平移時間戳、最後一個封包的長度補到段落長（`setts`），音訊取 §3 抽好的那一段 PCM（`-c:a copy`，仍是 `pcm_s16le`，§4.6.20 (iv) 成立）。
- **concat**：沿用現行呼叫（`-f concat … -c:v copy -c:a aac -b:a 256k`），拿掉 `-movflags +faststart`。`test_static_rules.py:505-522` 要的相鄰 `"-c:a", "aac"`、`"-c:v", "copy"` 都還在；**不改用 `aac_at`**（§10）。
- **ffprobe 合併**：每段的探測從約 6 次（`b0-audit.md:205`）降到 ≤ 3 次，`packets_by_stream` 同一條指令不重跑。
- **步驟名**維持 `normalize`／`concat`／`mix`／`probe`（`test_r3_finalize_guard.py:22`），以 `<對象>` 區分：抽音訊記 `mix（seg-NNNN）`、copy remux 記 `normalize（seg-NNNN）`、驗證記 `concat（verify:<影片檔名>）`。這修正了 log 把驗證記成 concat 而看不出來的問題（`baseline.md` A 節），又不碰 `TIMEOUT_STEPS`。
- **N-3**：`note_x264_fallback` 呼叫時機太早（`b0-audit.md:206`），被中止的段落也會印「改用 libx264」。改成只在該段真的以 libx264 重編成功後才印，補行為測試。

### 4.3 驗證移到發佈之後（C9）
- 發佈順序：影片 rename 進 `影片/` → manifest → `finalize.json`（含 `finishedAt`、`verify: {status: "pending"}`）→ wav hard link 進 `錄音/`（場次此刻存在；R3-§6 第 140 條「先寫 finalize.json、最後才讓 wav 出現」照舊）→ 印 `成品就緒：…` → 驗證。
- 驗證＝現行的整支 null 解碼＋兩次 dts 掃描（`bin/_record_finalize.py:1491-1499`），合併成一次 ffprobe。
- **通過**：`finalize.json.verify.status = "ok"`、記 `record: done`、刪段落（keep-segments 時保留）、回 0。
- **失敗或逾時**：影片改名為 `<同名>.verify-failed.mov`（不刪）、`finalize.json.verify = {status: "failed", reason, path: "copy"|"reencode"}`、**段落全部保留**、stderr 印原因與 `meeting record finish` 提示、回 5（集合不變）。wav 已發佈、不動。錄製器照現行 `completionOutcome` 寫 `phase=failed, code=5` 並發「會議錄製結束（有錯誤）」通知（內文改用場次代號，§9）。
- **重跑**：`already_done` 在 `verify.status == "failed"` 時不算完成；上次是 copy 路徑失敗時，這次強制走重編路徑。舊場次的 `finalize.json` 沒有 `verify` 鍵，視為通過（相容）。
- 驗證不計入 G1（intent §7 Q1）；`record stop` 的等待與結束碼語意不變（仍等整個收尾，含驗證）。

## 5. 增量轉錄（MS-D5；ADR `adr/adr-ms-incremental-asr.md`）

intent §7 Q5：切點取段尾附近的 VAD 靜音點；丟幀數一增加就暫停到停止；逐段結果不完整或參數不一致就退回整檔。

- **誰起**：錄製器在**第一段收尾後**（不在開錄當下，避免模型載入跟開錄搶資源）以 `/usr/bin/nice -n 10 <record.defaults.json 的 python3> <harness>/bin/lib/_asr_worker.py run <場次>` 起 worker，`qualityOfService = .utility`。直譯器沿用收尾用的那一支（`RecordingSession.swift:1220`），不經 `zsh -l`，避開 pyenv shim（intent §4.4）。`bin/lib/_asr_worker.py` 不存在時不起（`incremental-asr` 合併前的中間狀態）。
- **輸入**：只讀 `manifest.json` 中 `finishedAt` 不是 null 的段落（`segmentFinished` 已原子寫入，`RecordingSession.swift:691-705`）。不另開事件檔，狀態通道照舊只有狀態檔（`adr-control-channel.md:21-29`）。
- **音訊**：呼叫 `_record_finalize.segment_audio_pcm`（`finalize-fast` 新增的頂層函式，與音訊先出同一段程式）取得該段 PCM，再轉 16k。段落在成品時間軸上的起點＝前面可讀段落長度的總和，與 `ready.json` 用同一個算法，所以兩邊的時間軸一致。
- **窗**：窗 k＝[cut_{k−1}, cut_k]。cut_k 取第 k 段最後 8 秒內、`levels_intervals`（`bin/lib/_record_lib.py:180`，同一組 VAD 門檻、補、合併間隔）兩個有聲區間之間最晚的那個靜音區間的中點；找不到就在段尾硬切。窗內再依同一組 VAD 參數算 `clip_timestamps`，交給 `mlx_whisper.transcribe()`（模型只載一次）。窗不重疊，拼接時不必去重，raw 不會出現重複（鐵則 1）。
- **暫停**：每窗開始前讀狀態檔。`droppedFrames`（§3.1 新欄位）比 worker 起來時的值大 → 狀態記 `paused: drops`，到這一場 phase 離開 `recording`／`stopping` 為止不再開新窗；這一場錄製中、而另一場正在背景收尾（`finalizing/*.status.json` 的 pid 還活著）時，也先不開新窗。停止後兩個條件都不再擋，補做全部欠的窗。
- **停止後**：看到 phase 已是 `finalizing`／`done`／`failed`，處理完所有已收尾段落，最後一窗到最後一段結尾，寫 `state.json.status = "complete"` 後結束。
- **交棒**：prep（early 或一般）先跑 `_asr_worker.py stitch <場次> <out.json>`：worker 還活著且 60 秒內有心跳就等；`complete` 且段落清單與 `ready.json`（或 `finalize.json.inputs`）相同、參數與這次 `transcribe.sh` 會用的相同（模型、語言、提示詞、VAD 門檻／補／合併間隔／是否套用、補償模式為 off）→ 拼成與 mlx_whisper 同 schema 的 JSON，回 0；否則回 3 並印原因，prep 退回整檔轉錄。拼好的 JSON 經 `MH_ASR_SEGMENTS_JSON` 交給 `transcribe.sh`，後段（raw 標頭、segments.json、正體保險栓、品質檔）走同一條程式。
- **品質門檻**（G4，待閘門 2 核准，spec §4.11.9）：以整檔轉錄為參照，增量結果的字差異率 ≤ 5%；對齊上的字元時間差 ≤ 1.0 秒的比例 ≥ 95%。只在重放量測時離線比對，不是執行期的採用條件。
- **不做**：增量講者分離（intent §4.5）。

## 6. 前處理並行與「這一次」的結果（MS-D6）

- `prep` 每場：開始時呼叫 `_record_lib.py state-begin`，在 `.pipeline-state.json` 寫 `prep: {runId, startedAt, expect: [transcribe, slide-ocr?, diarize?]}`；之後每個 stage 都帶 `runId`。
- 要做分離的場次：轉錄前先在背景起 `diarize.sh`（只產 `diarization.json`），轉錄、OCR 做完後 `wait`，兩者都成功才 merge＋annotate。**修正 `bin/meeting.sh:274`**：`diarize.sh` 失敗時也寫 `diarize: failed`。
- 拿掉缺 `transcript.segments.json` 時的靜默重轉（`bin/meeting.sh:247-273`，C8）：改印「✗ 缺 transcript.segments.json，先跑 meeting.sh prep <場次>（或 transcribe）再分離」，`run_diarize` 回 1、記 `diarize: failed`。`meeting diarize` 的結束碼仍在 {0, 1, 2}。這條會讓 `test_r3_vtt_raw.py::test_diarize_keeps_raw` 變紅，列為 spec §6 第 26 條待核准；**不核准時的替代**：保留重轉，但改成先印一行明確的原因與耗時提示（不再靜默）。
- `prep` 的結束碼語意不變（失敗仍回 0，intent §4.5）。
- **`AutoPrepRunner` 判斷成敗**（G5）：prep 回 0 後讀該場 `.pipeline-state.json`，交給 Core `prepOutcome(pipelineState:runId:)`：`prep.runId` 與這次相同、`expect` 的每個 stage 都是 `done` 且 `runId` 相同 → `.ok`；有任何不是 → `.failed([stage…])`；讀不到或 runId 不同 → `.unknown`（當失敗處理，通知寫「無法確認」）。非 0 結束碼照舊算失敗。

### 6.1 選項（ADR 等級的取捨，記在這裡）

| 選項 | 做法 | 代價 |
|---|---|---|
| A（採用） | `.pipeline-state.json` 加 `prep.runId`、每個 stage 帶 `runId`；`AutoPrepRunner` 讀檔 | 狀態檔多兩個鍵；`_state.py` 照列所有 stage，不受影響（`research-code-contracts.md:104`） |
| B | prep 在 stdout 最後印一行機器可讀的摘要，`AutoPrepRunner` 從 log 認 | 解析 log 很脆；log 是 append 的共用檔，要另外切出這一次的範圍 |
| C | prep 失敗時回非 0 | 改變其他 session 依賴的結束碼語意（intent §4.5 列為本輪不做） |

## 7. 狀態檔加鎖（MS-D7）

- `bin/lib/_record_lib.py` 新增 `update_pipeline_state(sess, updates, timeout=5.0)`：`<場次>/.pipeline-state.lock` 取 flock、讀後合併、mkstemp＋rename、等鎖 5 秒逾時放棄（沿用 `adr-r3-defaults-writers.md:26-30` 與既有 `_acquire_lock`，`bin/lib/_record_lib.py:41-58`）；CLI 子指令 `state-set`、`state-begin`。
- 寫入者三方：`meeting.sh state_set`（改呼叫 CLI）、`_record_finalize.set_state_done` 與新的 `audio: done`（改呼叫函式）、`_asr_worker` 不寫這個檔。
- 逾時：印一行警告到 stderr、該次寫入放棄、呼叫端照常繼續（狀態檔只是紀錄；`AutoPrepRunner` 讀到缺 stage 會判失敗，比靜默寫壞好）。

## 8. 失敗看得到（MS-D8；G5）

- **ASR**：mlx_whisper CLI 出例外也回 0、writer 中途出錯只剩 txt（`b0-audit.md:215`）。`transcribe.sh` 的成功判準改成「結束碼 0 **且** WORKDIR 有非空的 `.json`」；不成立就清掉這次的輸出、走既有的退回鏈。完整輸出寫到 `$WORKDIR/asr.log`，失敗時印最後 30 行（取代 `| tail -8`，`bin/transcribe.sh:132`）。全部引擎都失敗時沒有 txt，照舊回 3（`:166-170`）。**保留 CLI 這道接縫**，`fakes/asr/mlx_whisper` 與四支 argv 斷言不受影響（intent §4.3）。
- **替身**：現有替身用非 0 表示失敗，與真實 CLI 相反（`b0-audit.md:235`）。不改它，另加一支「出例外回 0、只寫 txt」的替身 `fakes/asr_exc0/mlx_whisper`（新檔），驗新判準。
- **preflight**（`b0-audit.md:177-182`）：Core 新增 `audioProbeVerdict(opened:targetPeakDBFS:displayPeakDBFS:thresholdDBFS:)`；probe stream 開不起來時回 `.deviceFailed`，`PreflightRunner` 報「音訊裝置無法啟動（輸入：<名稱>／<transport>；輸出：<名稱>／<transport>）」，第 6、12 項改記「略過（音訊裝置無法啟動）」而不是誤報。仍是第 5 項 hard、結束碼 4（集合不變）。**不改既有 `SystemAudioCheck` enum**，避免第 1 層合併後 Capture 的 `switch` 不完整而建置失敗。
- **停止路徑**：`MenuBar.swift` 的 `stopRecording`、`performStop`、`cancelFinalize`、`cancelBackgroundFinalize`、`hudStop`，`HUD.swift` 的 `stopPressed`，`Onboarding.swift` 的 `sendStop`，以及 `PreflightRunner.swift` 的兩處（`b0-audit.md:184-187`）：每個提早 return 前寫一行 log（Core `stopPathLogLine(source:reason:)` 格式化）。`stopTargetDecision(` 呼叫形狀不動。
- **N-4（前景退回路徑沒有整合測試）**：**不做**。理由：前景退回在 `RecordingSession` 的排隊鎖分支（`RecordingSession.swift:1180`），屬 Capture 層，`Tests/run.sh` 只編 Core（`b0-audit.md:197`），要整合測試就得先為 Capture 建測試骨架，超出本 epic。列為衍生工作。

## 9. 鐵則（MS-D9；G6）與通知（MS-D11；G9）

- **embedding**（ADR `adr/adr-ms-embeddings-temp.md`）：`diarize.sh` 以 `mktemp` 建暫存檔給 `MH_EMBEDDINGS_OUT`，聲紋比對用完就刪（`trap`）；場次資料夾不再出現 `embeddings.json`。`_voiceprint.py match/add` 新增 `--embeddings <路徑>`；`add` 沒有給時，呼叫 `_diarize_pyannote.py --embed-speaker` 依 `diarization.json` 的該講者時段當場算一次向量（暫存、用完刪），使用者確認後才寫進 `vault/voiceprints/`。舊場次已存在的 `錄音/embeddings.json` 只讀不寫、不自動刪（刪資料要使用者同意）。`.gitignore` 補 `embeddings.json`、`speakers.map.json`、`transcript.quality.json`、`.pipeline-state.lock`。
- **confidence**：`_merge_speakers.py:78`、`_render.py:270` 的預設由 1.0 改成 0（沒有 confidence 的 dict 視為未確認、不套名）。**門檻只有一套**：speakers.map 有 `apply` 聽 `apply`、沒有就 `confidence ≥ 0.7`、字串值（人工確認）直接套；聲紋比對寫 `apply` 時以 cos ≥ `RENAME_TH`（預設 0.75，`bin/_voiceprint.py:38`）為準（專案規則第 3 條作用在 apply 的產生端）。0.7 與 0.75 量的是不同的東西（map 信心值與 cos），寫進 spec §4.6.2。
- **人工確認不被覆蓋**：`_voiceprint.py:115-118` 改成：既有值是非空字串，或是 dict 而 `evidence` 不是以「聲紋庫比對」開頭（人工或 agent 寫的）→ 一律不覆蓋；只有上一次聲紋比對寫的 dict 才可能被信心更高的新結果取代（現行規則）。
- **raw 不轉**：`transcribe.sh:194-201` 的 `_to_tw.py` 不再改 `transcript.raw.md`；正體版另存 `transcript.md`（只在它不存在時寫，與「精修另存 transcript.md」一致，`.claude/skills/meeting-transcribe/SKILL.md:39`）。`transcript.segments.json` 是機器用的衍生檔，照舊轉字形（不是 raw 逐字稿）。
- **其他**：`_voiceprint.py remove` 過濾檔名（`bin/_voiceprint.py:172`）；meeting-speakers SKILL 補 annotate 步驟；`meta["embeddings"]` 改在寫 `diarization.json` 之前設定（`research-code-contracts.md:122`）。
- **通知**：Core 新增 `sessionCodeLabel(startedAt:runId:timeZone:)`（`backgroundJobLabel` 改呼叫它，輸出不變，`Core/BackgroundFinalize.swift:189-200`）。前處理完成／失敗／沒有執行三則通知（`Trigger/Completion.swift:138,172,180,182`）、錄製實例的完成通知（`RecordingSession.swift:1248-1250`）、menu bar 的完成通知（`MenuBar.swift:1129`）內文一律改用場次代號，不含場次名或路徑。「在 Finder 顯示」用的 `userInfo.session` 不是顯示文字，保留。

## 10. 不採用 `aac_at`

intent §5 Q3 的建議是「先量 `aac_at` 的收益再決定要不要申請改 `test_static_rules`」，§7 沒有決定改它。本設計：concat 照舊用內建 `aac`（`test_static_rules.py:505-522` 不改）；`video-spike` 量 `aac` 與 `aac_at` 在 2 小時 PCM 上的耗時寫進證據檔。若第 2 層量測顯示影片超過 5 分而 `aac_at` 能補回，再以 spec §7 疑慮 3 回報、另開核准，不在本輪預先申請。

## 11. 三方資源分配（MS-D12；intent §4.1.1）

同一台機器可能同時有：這一場錄製、上一場背景收尾、這一場 ASR worker。優先順序：錄製 ＞ 背景收尾 ＞ worker。
- 錄製：不變。
- 背景收尾：沿用 R3x-D9，錄製中平行度降為 2（`bin/_record_finalize.py:93`）。
- worker：`nice -n 10`；錄製中只要有別場背景收尾還活著就不開新窗；丟幀就暫停到停止（§5）。
- 停止之後：這一場的收尾（平行度依現行規則）、prep 的分離、worker 補窗三者並行；GPU 爭用的實際影響由 `replay-bench` 量（intent §4.4）。

## 12. 量測（MS-D13；G1、G4）

- `tools/bench/replay.py`（新，測試用工具，不是對外介面）：給一個保留段落的目錄，在暫存區建沙盒場次（名稱用「[Stand-up] 範例專案」）與沙盒 `MH_RECORD_HOME`；依各段 `startedAt`／`finishedAt` 的間隔、乘上 `--speed` 倍率，逐段把段落放進 `tracks/` 並更新 manifest；起 worker（`--no-worker` 可關）；最後一段放完算「停止」，起 `_record_finalize.py`，認到「音訊就緒」就起 `meeting.sh prep`（`MH_PREP_EARLY=1`），沒有這一行時等收尾結束再起（量舊流程）。
- 報告（JSON）：`stopToAudioReady`、`stopToSpeakersMd`、`stopToVideo`、`stopToWav`、`stopToAllReady`（三者取最大）、`verifySeconds`、`workerBacklogAtStop`、`speed`、`segments`、`recordedSeconds`；**不記任何來源路徑或場次名**（公開 repo，數字可以抄進 progress.md）。
- 加速重放時 worker 追不上的段數會比實際多，量到的停止後時間偏大（誤差方向保守，intent §5 Q6）；報告記下停止當下欠幾窗。
- 品質比對：`replay.py --compare-full` 另跑一次整檔轉錄，依 §5 的兩個門檻算字差異率與時間差比例。
- 資料來源（C10）：保留段落的路徑由使用者在量測時提供或由主 session 量；子 agent 不讀 `~/.meeting-harness/`。2026-10-20 的段落是 D8 錄的（各段尺寸不同），影片部分只能走重編路徑；**影片的 5 分鐘要用新錄製器錄的段落量**（plan §4）。

## 13. 結構重構（MS-D14；G8）

- 排在速度層之後（第 4 層）。行為不變，以全量測試佐證。
- **原則：被靜態測試釘住的函式與字面留在原檔**（`test_r2_static.py`、`test_r3_app_static.py`、`test_r3x_app_static.py`、`test_static_rules.py`、`test_r3x_parallel_finalize.py` 的 `need()` 與模組全域，`research-code-contracts.md:127-135`）。可以搬的是沒被釘住的部分（例如 `MenuBar.swift` 的圖示繪製、`RecordingSession.swift` 的監看與落盤 helper、`_record_finalize.py` 的分析與補償函式），Swift 用 `extension` 放到新檔，Python 搬到 `bin/lib/` 再由原模組 import（可變全域不搬，避免副本問題）。
- 依這個原則，預估第 4 層要改的既有測試為 **0 條**（intent §7 Q4 的「第 3 層批次」）。build 中若發現非改不可，`split-*` 停下回報，由主 session 一次送使用者核准，不得自行改測試。
- 目標用行數判定（spec §4.13）：`MenuBar.swift`、`RecordingSession.swift` 各 ≤ 1000 行；`_record_finalize.py` ≤ 1300 行；`record.sh` 的 `cmd_control` ≤ 100 行；`transcribe.sh` 不再有品質檢查的 heredoc（搬到 `bin/lib/_transcript_quality.py`）。重複 helper 集中：`paused_total`、原子寫入、`load_json`、`record_home`、`harness_config`、HF token 讀取。

## 14. 測試策略（MS-D15；intent §7 Q4）

| 類別 | 做法 |
|---|---|
| 速度相關 | 一律繞開既有測試：保留 `nextSegmentSize(` 呼叫、concat 的 `-c:a aac`、步驟名集合、mlx_whisper CLI 接縫、`_record_finalize.py` 的頂層名稱；copy 路徑只對有 `canvasLock` 的場次生效 |
| 鐵則（源頭修正） | `diarize.sh`、`_merge_speakers.py` 直接改；`test_diarize_and_merge_untouched` 送核准（spec §6 第 18 條） |
| C8 靜默重轉 | `test_diarize_keeps_raw` 送核准（spec §6 第 13、20 條），附不核准時的替代 |
| `test_r3_lock` 容差 | 單獨送核准（spec §6 第 21 條；提議 +2 → +6 的理由見該條） |
| 第 4 層重構 | 原則上 0 條（spec §6 第 22 條預留）；`test_r3x_parallel_finalize.py` 的 ResourceWarning 不修（衍生工作） |
| 新測試 | `tests/record/test_ms_*.py`（Python）、`tools/MeetingRecorder/Tests/MSCoreTests.swift`（Swift），由 Red 層先寫 |

`test_diarize_and_merge_untouched` 若核准修改，同一支檔裡的 16k 跳過轉檔（速度）會連帶被允許；spec §6 第 19 條把這一點單獨列出，閘門 2 可以只核准鐵則、不核准速度那一項（不核准時 `diarize.sh` 的 16k 判斷不做，代價是多一次數秒的轉檔）。

## 15. 不做（MS-D16）

- AI 總結的速度（intent §7、使用者決定 1）。
- 增量講者分離 embedding（intent §4.5）。
- `meeting.sh prep` 失敗時回非 0（intent §4.5）。
- `aac_at`（§10）。
- pyannote 4 不傳 `return_embeddings`：本機 venv 在 `~/.meeting-harness`，不傳時是否仍回 `speaker_embeddings` 未能確認（intent §4.4），而這一項沒有速度收益；照舊傳，只刪 `except TypeError` 這段死碼要先實跑確認，本輪不動。
- N-4（§8）、`_lint.sh` 加 `-W error::ResourceWarning`（§1.1）。

## 16. 未能確認、要靠實測的事

| 事項 | 由誰、在哪裡確認 |
|---|---|
| `preservesAspectRatio` 在目標 macOS 版本的預設與行為 | `video-spike` |
| SCK 段落（VFR、`time_base=1/600`）走 copy 串接是否乾淨、`setts` 補尾能否通過 §4.6.3 與缺陷 B、F、N 的判準 | `video-spike`；test 段用新錄製器實錄重驗 |
| 錄製中 `manifest.json.levels` 是否隨段落收尾一起落盤（worker 取切點用） | 已讀碼確認：levels 每 0.5 秒在記憶體累加（`RecordingSession.swift:715`），段落收尾時 `writeManifest()`（`:697`）一起落盤；最後不到 0.5 秒的部分可能還沒寫，找不到切點就硬切（spec §7 疑慮 4） |
| mlx（Metal）與 pyannote（MPS）並行的實際加速 | `replay-bench` 第 2、3 層量測 |
| 87 分鐘場收尾比 2 小時場久的原因（`baseline.md` B 節） | 第 1 層量測拆開記 normalize 單段耗時；copy 路徑上線後不再是關鍵 |

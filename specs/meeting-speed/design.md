# design：meeting-speed（停止錄製後 5 分鐘內就緒＋全專案重構）

- 上游：`specs/meeting-speed/intent.md`（閘門 1 已核准，2026-10-21；**§7 是決定全文，取代 §5 的建議**）。
- 下游：`spec.md`（驗收條件）、`plan.md`（子任務、檔案、測試對應）、`progress.md`、`adr/`（四則）。
- 狀態：**修正輪 2 草稿，待閘門 2 核准**。使用者 2026-10-21 在閘門 2 前的決定 D1–D5、E1–E4 已落進本檔、spec、plan（逐條處理見 `_tpm/runs/20261021-sdlc-meeting-speed/design-revise-對照.md`）。
- 行號以 `042c404` 為準（`git log --oneline -1 origin/main`）；可用 `sed -n '<行>p' <檔>` 重跑核對。
- 本檔的 MS-D1…MS-D16 只是本檔內的決策編號，**不是任務編號**；G1–G9 沿用 intent §2 的目標代號，spec 用它們當 Story ID。
- 範例場次名一律用「[Stand-up] 範例專案」。
- `specs/_templates/` 不存在（`ls specs/` 只有 `meeting-record`、`meeting-speed`），四份文件沿用 `specs/meeting-record/` 的格式。

---

## 0. 結論先講

1. **關鍵路徑改成「音訊先出 → 前處理（轉錄與分離並行）」與「影片 copy 串接」兩條平行線**，驗證移到成品發佈之後。2 小時場的推算關鍵路徑見 §2；最緊的一段是講者分離（實測 204.9 秒，`baseline.md` A 節），5 分鐘的餘裕約 1 分鐘以內。
2. **錄製中的增量轉錄**由錄製器在開錄時起一個低優先權的 Python worker（`bin/lib/_asr_worker.py`），只讀 `manifest.json` 已收尾的段落，模型只載一次；停止後只剩最後一窗。
3. **閘門 1 的八項決定全部落成條文**（spec §4），被推翻或修訂的 meeting-record 條文逐條列在 spec §6.1；要改的既有測試列在 spec §6.2。第 1–21 條使用者已在閘門 2 前核准（D1）；修正輪依 D2、D3 新增的第 23 條（正式 wav 先於影片發佈）、第 24 條（`record finish` 不帶參數可接手）使用者 2026-10-21 已確認（E1、E2）；第 22 條是結構重構的預留條，預估 0 條。
4. **拆成 15 個子任務、Red＋3 層**（§1；明細在 `plan.md` §1）。所有子任務的檔案歸屬完全不重疊（跨層也不重疊）；結構重構由各檔的擁有者在速度 commit 之後另做 refactor commit（§13；D5：不另開第 4 層）。當晚錄製異常中止的 4 項修正依 D3 併進既有子任務，不新增子任務（§17）。
5. **契約夠用，沒有新端點**。新增的都是：狀態檔的 Optional 欄位、場次資料夾內的新檔、只給內部呼叫的環境變數、stdout 新增一行。`meeting.sh`／`record.sh`／`transcribe.sh`／`diarize.sh`／`_record_finalize.py` 的子指令與結束碼集合都不變（spec §2）。

---

## 1. 子任務拆分（MS-D1）

### 1.1 起點與調整

起點是 `plan-approved.md:35-107` 的 12 個子任務、4 層。依 intent §7 與檔案歸屬做了下列調整：

| 計畫原本 | 本設計 | 理由 |
|---|---|---|
| docs-cleanup 在第 4 層 | 移到第 3 層，只擁有 `README.md`、`.claude/workflows/meeting-pipeline.js` | 它擁有的檔沒有別人碰；過期註解交給各檔的擁有者（`transcribe.sh:3`＝asr-robust、`_merge_speakers.py:3`＝diarize-iron、`record.sh:973`＝record-sh-split） |
| split-swift、split-scripts 在第 4 層 | 拆掉，依檔案併進各檔的擁有者（`MenuBar.swift`＝trigger-ui；`RecordingSession.swift`、`PreflightRunner.swift`＝recorder-capture；`_record_finalize.py`＝finalize-fast；`transcribe.sh` heredoc＝asr-robust；共用 helper 的公開與 `paused_total` 統一＝prep-pipeline）；`record.sh` 沒有別的擁有者，獨立成 `record-sh-split`（第 1 層） | 重構要動的檔正好是速度層改的檔，另開子任務就一定兩個子任務擁有同一支檔（`check-envelope.sh` 擋檔案歸屬重疊）。G8「速度先、重構後」的理由是避免衝突；單一擁有者在自己的速度 commit 之後做 refactor commit，衝突來源不存在，順序也成立。代價：三個第 2 層子任務工作量變大 |
| incremental-asr 改 `meeting.sh` 的 prep 讀取、改 `config.json` | `meeting.sh` 的 stitch 呼叫端由 `prep-pipeline` 寫（worker 檔不存在就跳過，spec §3.9）；`config.json` 的 `transcribe.incremental.enabled` 由 `diarize-iron` 一併加（它本來就要改 `diarize.note` 的 embedding 說明） | `incremental-asr` 只擁有新檔 `bin/lib/_asr_worker.py`，不必和第 1 層串鏈 |
| （沒有） | 新增 `red-py`、`red-swift`（Red 層，kind=test） | `sdlc-build` 先寫紅燈測試；派工單要求 test 子任務擁有 tests/ |
| preflight-diag、stop-gate、audio-first 的 Swift 部分各自改 Core | 新增 `ms-core`：獨佔 `Sources/Core/` | `Tests/run.sh` 一次編譯整個 Core（`research-code-contracts.md:137`），紅燈測試引用的 Core 名稱散在多個子任務就沒有任何一個子任務能單獨跑綠；R3 的 `r3-core` 是同一個理由（`specs/meeting-record/plan.md` §10.1） |
| state-lock、prep-parallel 分開，都改 `meeting.sh` | 合併成 `prep-pipeline` | 兩者改同一支 `meeting.sh` 的 prep 段，`state_set` 換成加鎖寫入正好是並行化的前提；分開就得串成鏈、多一層 |
| audio-first、video-copy 都改 `_record_finalize.py` | 合併成 `finalize-fast` | 音訊先出與影片 copy 都在 `finalize_locked`（`bin/_record_finalize.py:1379-1565`）同一個流程裡重排步驟；分開會在同一函式上序列改兩次 |
| video-copy 的錄製端、audio-first 的 Swift 端、preflight-diag 的 Capture 端 | 依目錄分成 `recorder-capture`（Capture/）與 `trigger-ui`（Trigger/） | `RecordingSession.swift`、`MenuBar.swift` 在速度層各只有一個擁有者，不必串鏈 |
| 計畫沒寫 | 新增 `video-spike`（kind=check） | intent §7 Q3：「`preservesAspectRatio` 和 copy 串接要先實測」 |
| 計畫沒寫 | 新增 `replay-bench`（重放量測工具） | intent §7 Q6：每一層都用加速重放量，最終做一次 1× |
| prep-parallel 的 `diarize.sh`、`_diarize_pyannote.py` | 併進 `diarize-iron` | 跟鐵則修正改同兩支檔；都受 `test_diarize_and_merge_untouched` 管（spec §6 第 18 條，D1 已核准刪除這支斷言） |
| asr-robust 的 `meeting.sh:247-273` 靜默重轉 | 移到 `prep-pipeline` | 那段在 `meeting.sh`，`prep-pipeline` 才擁有它 |
| iron-rules 的 `_to_tw.py` 原地改寫 raw | 移到 `asr-robust` | 改的是 `transcribe.sh:194-201`，`asr-robust` 擁有 `transcribe.sh` |
| R2「完成通知含場次路徑」（衍生工作） | 併進 `recorder-capture`（`RecordingSession.complete`）與 `trigger-ui`（`MenuBar.postCompletion`、`Completion.swift`） | intent §7 最後一項：併進 G9 |
| stop-gate「StopGate.evaluate 取代 5 處 `stopTargetDecision(`」 | 改為只補 log，不改呼叫形狀 | `test_r3_app_static.py:128-137,209,320` 要求 `MenuBar.swift`、`HUD.swift` 原樣含 `stopTargetDecision(`；intent §7 Q4「速度與一般修正繞開既有測試」 |
| docs-cleanup 的 `_lint.sh` 加 `-W error::ResourceWarning` | 不做（衍生工作） | 疑似來源在測試檔（`b0-audit.md:37`；`tests/record/test_r3x_parallel_finalize.py:732-734`），修它要改既有測試；本輪不修，列為衍生工作（spec §6.2 末段） |
| 事故修正 (a) 補尾幀數（D3） | 併進 `finalize-fast` | 改的是 `_record_finalize.py` 的 `normalize`，`finalize-fast` 擁有這支檔；copy 路徑上線後退回重編仍會走到 |
| 事故修正 (b) 選單啟動偵測異常中止（D3） | 判定進 `ms-core`、偵測與通知進 `trigger-ui` | 判定是純函式，放 Core 才能被 `Tests/run.sh` 測；啟動流程在 `MenuBar.swift`，`trigger-ui` 擁有 |
| 事故修正 (c) `record finish` 不帶參數接手（D3） | 併進 `record-sh-split`（從純重構變成 feat＋refactor） | 改的是 `record.sh` 的 `cmd_finish`，`record-sh-split` 是 `record.sh` 唯一的擁有者 |
| 事故修正 (d) 擷取幀率／尺寸（D3） | `video-spike` 多量一節，結果交使用者決定 | D3 明定不在 spec 預先定案；`recorder-capture` 等決定才開工 |
| `harness_config` 合一（修正輪 1 擴成三份、`_profile.py` 歸 `diarize-iron`） | **修正輪 2 移出本 epic**，列衍生工作（不編號）；`bin/_profile.py` 不再列入任何子任務的 owns | 既有、不得改的 `tests/record/test_review_fixes.py:96-101` `copy_with_config` 只把單支 `_profile.py`／`_voiceprint.py` 複製到暫存 `repo/bin/` 執行；改 import `bin/lib/_harness.py` 後複製出去的腳本找不到模組。保留各檔 fallback 又等於仍有多份定義。另一種做法「改測試讓它連 `bin/lib/` 一起複製」違反「上游測試不改」 |
| `paused_total` 兩份「改 import、行為不變」 | 以 `_record_finalize` 的算法為準（連續兩個 pause 取後一個）；`red-py` 先寫鎖定測試，`prep-pipeline` 改 `_record_lib`，`finalize-fast` 再改 import（E4(3)） | 兩份在連續兩個 pause 時結果不同（`bin/_record_finalize.py:749-762` 取後一個；`bin/lib/_record_lib.py:113-134` 經 `pause_pairs` 取前一個），「行為不變」不成立 |
| 三支過期註解共用一支測試 | 拆成三支（`test_stale_comment_transcribe`／`_merge_speakers`／`_record_sh`） | 一支測試橫跨三個擁有者，沒有任何子任務能單獨轉綠 |

數量從 12 變 15：新增 `red-py`、`red-swift`、`ms-core`、`video-spike`、`replay-bench`、`record-sh-split`，各自說得出不能併進別人的理由；減少的是合併（state-lock＋prep-parallel、audio-first＋video-copy 的 finalize 端、split-swift 與 split-scripts 併進各檔擁有者）。

### 1.2 分層

| 層 | 子任務 | 相依 |
|---|---|---|
| Red | `red-py`、`red-swift` | — |
| 1 | `ms-core`、`asr-robust`、`diarize-iron`、`prep-pipeline`、`record-sh-split`、`video-spike`、`replay-bench` | — |
| 2 | `finalize-fast`、`recorder-capture`、`trigger-ui` | 見 plan §1 |
| 3 | `incremental-asr`、`docs-cleanup` | `incremental-asr`：`finalize-fast`、`prep-pipeline`、`asr-robust`、`diarize-iron`；`docs-cleanup`：`finalize-fast`、`prep-pipeline` |

**檔案歸屬**：每支檔從頭到尾只有一個擁有者，跨層也不重疊（`plan.md` §1）。

---

## 2. 關鍵路徑與 5 分鐘預算（G1）

### 2.1 新做法

```
錄製中   每段收尾 → manifest.json 寫 finishedAt → ASR worker 轉錄（nice 10；丟幀就暫停到停止）
停止 ─┬→ finalize：分析各段 → 逐段抽 PCM 混音 → 16k wav（.part）→ audio-ready.json → finalize.json 第一階段
      │      → wav os.replace 進 錄音/（正式 wav，不等影片）→ 印「音訊就緒：…」
      │      └→ 錄製器把 status.audioReady 設 true → menu bar 立刻排 prep（現行 meeting.sh prep <場次>）
      │             ├ 轉錄：worker 補最後一窗 → stitch → transcribe.sh 讀現成段落（MH_ASR_SEGMENTS_JSON）
      │             └ 講者分離：背景跑 diarize.sh（讀 錄音/ 第一層的正式 wav）
      │             → wait → merge → annotate → transcript.speakers.md
      └→ finalize 繼續：影片 -c:v copy（逐段 remux＋PCM）→ concat（-c:v copy -c:a aac）
             → 影片 rename 進 影片/、manifest、finalize.json 第二階段（成品就緒）
             → 背景驗證（整支解碼＋dts）→ 通過才刪段落、記 record: done
```

### 2.2 預算（推算；實測值待每層量測寫進 progress.md）

| 段 | 改之前（實測，`baseline.md` A 節） | 改之後（推算依據） |
|---|---|---|
| 停止 → 音訊就緒（＝正式 wav 出現） | 約 20 分 16 秒（等收尾全部做完） | 分析 121 段（ffprobe 合併後每段 ≤ 3 次、平行 3）＋逐段抽音訊（只解音訊、平行 3）＋串 16k wav。**未量測**，`replay-bench` 第 1 次量時拆開記。D2 之後舊段落（走重編）也適用，因為正式 wav 不等影片 |
| 轉錄 | 5 分 56 秒（整檔） | 只剩最後一窗（≤ 68 秒音訊，§5）＋stitch；worker 欠段時另計 |
| 講者分離 | infer 204.9 秒 | 不變（整場跑一次）；與轉錄並行，GPU 爭用的影響**未量測**（intent §4.4） |
| merge＋annotate | log 未單列 | 不變 |
| 影片 | normalize 16.5 分＋concat 149.1 秒＋驗證 48.7 秒 | copy 路徑：逐段 remux（不重編影片）＋concat（AAC 一次編、拿掉 `+faststart`）。**未量測**，`video-spike` 量 concat 部分 |

最緊的是「音訊就緒時間＋講者分離＋merge」。若第 2 層量完發現超過 5 分，spec §7 疑慮 1 列了回報點與可選的下一步（分離加大 batch、`MH_DIARIZE_EMB_BATCH`）。

---

## 3. 音訊先出（MS-D2；ADR `adr/adr-ms-audio-first.md`）

intent §7 Q2：wav 先寫到 `錄音/tracks/`，自動前處理直接讀它；「場次存在＝錄製完成」不變。**D2（使用者 2026-10-21，閘門 2 前）**：正式 wav 必須先於影片發佈、不等影片——取代 Q2「正式 wav 照舊在最後一刻 rename 進 `錄音/`」的那一句；「場次存在」改為錄音成品就緒（影片可能還在收尾），使用者 2026-10-21 確認（E1；spec §6 第 23 條）。

- **產法**：沿用 `audio_graph`（`bin/_record_finalize.py:894-915`）與正規化相同的原點與 `-t`，逐段抽出 48 kHz 雙聲道 PCM；補償模式 ≠ off 時沿用 `compensated_audio`（`:1108-1151`），它只吃 `good`、`plan`、`work`、`total`，不依賴影片正規化結果，可以提前。整條 PCM 再轉 16 kHz 單聲道，寫到現行暫存目錄 `錄音/tracks/.finalize/audio.wav.part`（`:1449,1502`；符合 Q2「wav 先寫到 `錄音/tracks/`」）。影片的音軌照舊用同一份 PCM，§4.6.20 (ii) 的 ≤ 25 ms 判準仍適用。
- **發佈**：`錄音/tracks/audio-ready.json`（段落清單＋大小＋長度＋起點、補償模式、stamp）→ `finalize.json` 第一階段（現行鍵＋`finishedAt`＋`videoPublishedAt: null`，`outputs.video` 是預定路徑）→ `os.replace` 成 `錄音/<同名>.wav` → stdout 印 `音訊就緒：錄音/<檔名>`。「先 `finalize.json`、wav 後出現」（R3-§6 第 140 條）照舊，所以既有 `test_concurrency.py::test_finalizing_session_not_listed` 不改也綠（它的 `published()` 只看 `finishedAt` 與 `outputs.audio`，`tests/record/test_concurrency.py:19-26`）。
- **對外呈現**：`FinalizeRunner` 逐行轉印時認出「音訊就緒：」，呼叫 `status.update { $0.audioReady = true }`（`Capture/FinalizeRunner.swift:93-108` 已在逐行讀）。Python 不寫狀態檔，維持 `research-code-contracts.md:101` 的單一寫者。不另加 `stages.audio`（intent §7 沒有要求；skeptic 第 6 點）。
- **觸發**：Core 新增 `autoPrepPick`，在 `phase == .finalizing && audioReady == true` 時回 `.early`；原本的 done 路徑保留（同一 runId 只排一次）。`AutoPrepRunner` 對 `.early`、`.done` 都只多帶 `MH_PREP_RUN_ID=<uuid>`。
- **prep 怎麼吃**：正式 wav 已在 `錄音/` 第一層，`meeting.sh prep <場次>` 照現行 `list_sessions`／`_combine_audio.py` 就讀得到（`bin/meeting.sh:287-298,321`）；轉錄的 VAD 以音源所在目錄（`錄音/`）找 `tracks/manifest.json`，分離以 `_combine_audio.py "$REC"` 取同一支 wav（`bin/diarize.sh:24`）。所以**不需要早期模式**。
- **為什麼拿掉早期模式**：前一版為了「正式 wav 最後才出現」設計了 `錄音/tracks/audio/` 暫存音檔、`MH_PREP_EARLY`、`MH_TRANSCRIBE_REC_DIR`、`MH_DIARIZE_AUDIO` 與 hard link 發佈。D2 讓正式 wav 在音訊階段就出現，這些都只剩繞路、沒有速度收益；D1 雖然放行了 `MH_DIARIZE_AUDIO` 改 `diarize.sh`，修正輪用不到。使用者 2026-10-21 確認拿掉（E4(1)；spec §7 疑慮 13）。
- **冪等的中間態**（C2）：`audio-ready.json` 的段落清單、補償模式與這次相同、正式 wav 存在 → 不重寫（mtime 不變），直接進影片步驟。影片失敗回 5 時，下一次 `record finish` 只補影片；`already_done` 看兩個成品檔都在才算完成（`bin/_record_finalize.py:735-746`），影片不在就不會誤判。
- **代價**：影片收尾期間場次已可被 `meeting status`／`meeting prep <根>` 列出（spec §7 疑慮 11）。

## 4. 影片 copy 路徑、畫布鎖定、驗證後移（MS-D3、MS-D4；ADR `adr/adr-ms-video-copy.md`）

intent §7 Q3：開錄時鎖定當下的視窗像素，整場固定，60 fps；全場符合條件就 `-c:v copy`、碼率等於來源；不符合就整場退回現行重編。

### 4.1 錄製端
- `RecordingSession.init` 已在開錄時算 `curSize`（`RecordingSession.swift:124`）。改成：之後每段都用這個尺寸開檔；`startNewSegment` 照舊呼叫 `nextSegmentSize(`（`test_static_rules.py:368-374` 釘住這個呼叫），算出的新尺寸只寫一行 log「視窗尺寸改變：A → B（畫布維持開錄時的 W×H，內容等比縮放）」，**不再** `updateConfiguration`（`:526-534`）。
- 設 `cfg.preservesAspectRatio = true`（`scalesToFit` 已是 true，`:176`）。目標 macOS 版本上這個屬性的行為由 `video-spike` 先實測。
- **擷取幀率與尺寸上限（D3 d）**：2026-10-21 晚間 WindowServer 高 CPU（取樣含 `WSCaptureStream`）後重啟、錄製器在收尾前結束（`incident-2018-windowserver.md:4-14`）；2992×1632@60fps 的擷取在 WindowServer 吃重（同檔 :18）。是否改 30 fps 或加尺寸上限，由 `video-spike` 量三種設定的 WindowServer 負擔與 copy 串接後回報使用者決定（spec §4.4.13），本設計不預先定案；決定前維持 intent §7 Q3 的 60 fps。
- `record.meta.json` 加 Optional `canvasLock: {width, height}`（nil 省略鍵，照 `adr-r2-status-fields.md:35`）。**finalize 只對有 `canvasLock` 的場次考慮 copy 路徑**；舊場次（D8 錄的，或測試合成的段落）一律走現行重編。這樣既有 `test_finalize.py` 的合成素材全部照舊走重編路徑，§4.6.10 的「位元率 ≥ 各段最大值」等斷言不受影響（Q4：速度相關改動繞開既有測試）。

### 4.2 收尾端
- **copy 條件**（全部成立才走）：meta 有 `canvasLock`；每段都有影片、寬高等於 `canvasLock`；codec、profile、pix_fmt、time_base 全場相同；每段 extradata（SPS/PPS）雜湊相同（`ffprobe -show_streams -show_data_hash`）；沒有完全相同 PTS 的重複影格（`dups == 0`）。任一不成立 → 整場走現行 `normalize`＋concat（`b0-audit.md:30-31`：copy 段與重編段不能混用）。
- **逐段 remux**：影片 `-c:v copy`、以與音訊相同的原點平移時間戳（影片晚於原點時把首幀拉到 0）、最後一個封包的長度補到段落長（`setts`，以 `floor(L/TB)` 換算；用 round 時 2 小時 120 段會累積數 ms 偏移，video-spike 證據 §2.2、§5.1），音訊取 §3 抽好的那一段 PCM（`-c:a copy`，仍是 `pcm_s16le`，§4.6.20 (iv) 成立）。
- **concat**：沿用現行呼叫（`-f concat … -c:v copy -c:a aac -b:a 256k`），拿掉 `-movflags +faststart`；copy 路徑另外**加 `-auto_convert 0`**（否則 §4.4.4 封包不相同），且**不加**現行「最後封包 1 tick」的 `setts`（照原樣在最後一段畫面靜止時 §4.6.3 FAIL、影片短約 8 秒；重編路徑照舊保留）。依據：`evidence/video-spike.md` §2.2、§5.1。`test_static_rules.py:505-522` 要的相鄰 `"-c:a", "aac"`、`"-c:v", "copy"` 都還在；**不改用 `aac_at`**（§10）。
- **ffprobe 合併**：每段的探測從約 6 次（`b0-audit.md:34`）降到 ≤ 3 次，`packets_by_stream` 同一條指令不重跑（`bin/_record_finalize.py:619,1161-1162`）。
- **步驟名**維持 `normalize`／`concat`／`mix`／`probe`（`test_r3_finalize_guard.py:22`），以 `<對象>` 區分：抽音訊記 `mix（seg-NNNN）`、copy remux 記 `normalize（seg-NNNN）`、驗證記 `concat（verify:<影片檔名>）`。這修正了 log 把驗證記成 concat 而看不出來的問題（`baseline.md` A 節），又不碰 `TIMEOUT_STEPS`。
- **N-3**：`note_x264_fallback` 呼叫時機太早（`b0-audit.md:35`；`bin/_record_finalize.py:855-857`），被中止的段落也會印「改用 libx264」。改成只在該段真的以 libx264 重編成功後才印，補行為測試。
- **補尾幀數（D3 a）**：`normalize` 以 `link_fps`（取自 `r_frame_rate`）算 tpad 的補幀數（`bin/_record_finalize.py:1233,1254-1256`）。2026-10-21 晚間救回時，某段 `r_frame_rate`＝58 而 ffmpeg 實際連結影格率＝60，n＝511 只補到 59.767，夾 cap（59.995）的條件沒觸發，`check_norm` 失敗（`incident-2018-windowserver.md:22-28`）。改成以 `max(link_fps, TAIL_PAD_FPS_FLOOR＝240)` 算補幀數，多補的幀交給現行的夾 cap＋`select` 去重（多出的複製幀在編碼前就被丟掉，成本只在濾鏡）。copy 路徑上線後這條只剩退回重編會走，仍要修（spec §4.4.12）。

### 4.3 驗證移到發佈之後（C9）
- 發佈順序（影片）：影片 rename 進 `影片/` → manifest → `finalize.json` 第二階段（`videoPublishedAt`、`videoPath`、`verify: {status: "pending"}`）→ 印 `成品就緒：…` → 驗證。正式 wav 已在 §3 的音訊階段發佈，不在這個順序裡（D2）；這也解掉前一版「正式 wav 在影片發佈後才出現」與「舊段落一律重編」兩者相乘、舊段落量不到 `stopToWav ≤ 300` 的矛盾（skeptic 第 1 點）。
- 驗證＝現行的整支 null 解碼＋兩次 dts 掃描（`bin/_record_finalize.py:1491-1499`），合併成一次 ffprobe。
- **通過**：`finalize.json.verify.status = "ok"`、記 `record: done`、刪段落（keep-segments 時保留）、回 0。
- **失敗或逾時**：影片改名為 `<同名>.verify-failed.mov`（不刪）、`finalize.json.verify = {status: "failed", reason, path: "copy"|"reencode"}`、**段落全部保留**、stderr 印原因與 `meeting record finish` 提示、回 5（集合不變）。wav 已發佈、不動。錄製器照現行 `completionOutcome` 寫 `phase=failed, code=5` 並發「會議錄製結束（有錯誤）」通知（內文改用場次代號，§9）。
- **重跑**：`already_done` 在 `verify.status == "failed"` 時不算完成；上次是 copy 路徑失敗時，這次強制走重編路徑。舊場次的 `finalize.json` 沒有 `verify` 鍵，視為通過（相容）。
- 驗證不計入 G1（intent §7 Q1）；`record stop` 的等待與結束碼語意不變（仍等整個收尾，含驗證）。

## 5. 增量轉錄（MS-D5；ADR `adr/adr-ms-incremental-asr.md`）

intent §7 Q5：切點取段尾附近的 VAD 靜音點；丟幀數一增加就暫停到停止；逐段結果不完整或參數不一致就退回整檔。

- **誰起**：錄製器在**第一段收尾後**（不在開錄當下，避免模型載入跟開錄搶資源）以 `/usr/bin/nice -n 10 <record.defaults.json 的 python3> <harness>/bin/lib/_asr_worker.py run <場次>` 起 worker，`qualityOfService = .utility`。直譯器沿用收尾用的那一支（`RecordingSession.swift:1220`），不經 `zsh -l`，避開 pyenv shim（intent §4.4）。`bin/lib/_asr_worker.py` 不存在時不起（`incremental-asr` 合併前的中間狀態）。
- **輸入**：只讀 `manifest.json` 中 `finishedAt` 不是 null 的段落（`segmentFinished` 已原子寫入，`RecordingSession.swift:691-705`）。不另開事件檔，狀態通道照舊只有狀態檔（`adr-control-channel.md:21-29`）。
- **音訊**：呼叫 `_record_finalize.segment_audio_pcm`（`finalize-fast` 新增的頂層函式，與音訊先出同一段程式）取得該段 PCM，再轉 16k。段落在成品時間軸上的起點＝前面可讀段落長度的總和，與 `audio-ready.json` 用同一個算法，所以兩邊的時間軸一致。
- **窗**：窗 k＝[cut_{k−1}, cut_k]。cut_k 取第 k 段最後 8 秒內、`levels_intervals`（`bin/lib/_record_lib.py:180`，同一組 VAD 門檻、補、合併間隔）兩個有聲區間之間最晚的那個靜音區間的中點；找不到就在段尾硬切。窗內再依同一組 VAD 參數算 `clip_timestamps`，交給 `mlx_whisper.transcribe()`（模型只載一次）。窗不重疊，拼接時不必去重，raw 不會出現重複（鐵則 1）。
- **暫停**：每窗開始前讀狀態檔。`droppedFrames`（§3.1 新欄位）比 worker 起來時的值大 → 狀態記 `paused: drops`，到這一場 phase 離開 `recording`／`stopping` 為止不再開新窗；這一場錄製中、而另一場正在背景收尾（`finalizing/*.status.json` 的 pid 還活著）時，也先不開新窗。停止後兩個條件都不再擋，補做全部欠的窗。
- **停止後**：看到 phase 已是 `finalizing`／`done`／`failed`，處理完所有已收尾段落，最後一窗到最後一段結尾，寫 `state.json.status = "complete"` 後結束。
- **交棒**：prep 先跑 `_asr_worker.py stitch <場次> <out.json>`：worker 還活著且 60 秒內有心跳就等；`complete` 且段落清單與 `audio-ready.json`（沒有時用 `finalize.json.inputs`）相同、參數與這次 `transcribe.sh` 會用的相同（模型、語言、提示詞、VAD 門檻／補／合併間隔／是否套用、補償模式為 off）→ 拼成與 mlx_whisper 同 schema 的 JSON，回 0；否則回 3 並印原因，prep 退回整檔轉錄。拼好的 JSON 經 `MH_ASR_SEGMENTS_JSON` 交給 `transcribe.sh`，後段（raw 標頭、segments.json、正體保險栓、品質檔）走同一條程式。
- **品質門檻**（G4，使用者 2026-10-21 核准，D5；spec §4.11.9）：以整檔轉錄為參照，增量結果的字差異率 ≤ 5%；對齊上的字元時間差 ≤ 1.0 秒的比例 ≥ 95%。只在重放量測時離線比對，不是執行期的採用條件。
- **不做**：增量講者分離（intent §4.5）。

## 6. 前處理並行與「這一次」的結果（MS-D6）

- `prep` 每場：開始時呼叫 `_record_lib.py state-begin`，在 `.pipeline-state.json` 寫 `prep: {runId, startedAt, expect: [transcribe, slide-ocr?, diarize?]}`；之後每個 stage 都帶 `runId`。
- 要做分離的場次：轉錄前先在背景起 `diarize.sh`（只產 `diarization.json`），轉錄、OCR 做完後 `wait`，兩者都成功才 merge＋annotate。**修正 `bin/meeting.sh:274`**：`diarize.sh` 失敗時也寫 `diarize: failed`。
- 拿掉缺 `transcript.segments.json` 時的靜默重轉（`bin/meeting.sh:247-273`，C8）：改印「✗ 缺 transcript.segments.json，先跑 meeting.sh prep <場次>（或 transcribe）再分離」，`run_diarize` 回 1、記 `diarize: failed`。`meeting diarize` 的結束碼仍在 {0, 1, 2}。這條會讓 `test_r3_vtt_raw.py::test_diarize_keeps_raw` 變紅，spec §6 第 13、20 條，使用者 2026-10-21 已核准（D1），由 `red-py` 照第 20 條改測試、`prep-pipeline` 轉綠。
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
- 寫入者：`meeting.sh state_set`（改呼叫 CLI）、`_record_finalize.set_state_done`（改呼叫函式，只寫 `record: done`；不另加 `audio` stage，spec §4.2.11 已刪）；`_asr_worker` 不寫這個檔。
- 逾時：印一行警告到 stderr、該次寫入放棄、呼叫端照常繼續（狀態檔只是紀錄；`AutoPrepRunner` 讀到缺 stage 會判失敗，比靜默寫壞好）。

## 8. 失敗看得到（MS-D8；G5）

- **ASR**：mlx_whisper CLI 出例外也回 0、writer 中途出錯只剩 txt（`b0-audit.md:43-44`）。`transcribe.sh` 的成功判準改成「結束碼 0 **且** WORKDIR 有非空的 `.json`」；不成立就清掉這次的輸出、走既有的退回鏈。完整輸出寫到 `$WORKDIR/asr.log`，失敗時印最後 30 行（取代 `| tail -8`，`bin/transcribe.sh:132`）。全部引擎都失敗時沒有 txt，照舊回 3（`:166-170`）。**保留 CLI 這道接縫**，`fakes/asr/mlx_whisper` 與四支 argv 斷言不受影響（intent §4.3）。
- **替身**：現有替身用非 0 表示失敗，與真實 CLI 相反（`b0-audit.md:64`）。不改它，另加一支「出例外回 0、只寫 txt」的替身 `fakes/asr_exc0/mlx_whisper`（新檔），驗新判準。
- **preflight**（`b0-audit.md:6-11`；`Capture/PreflightRunner.swift:238,417-431`）：Core 新增 `audioProbeVerdict(opened:targetPeakDBFS:displayPeakDBFS:thresholdDBFS:)`；probe stream 開不起來時回 `.deviceFailed`，`PreflightRunner` 報「音訊裝置無法啟動（輸入：<名稱>／<transport>；輸出：<名稱>／<transport>）」，第 6、12 項改記「略過（音訊裝置無法啟動）」而不是誤報。仍是第 5 項 hard、結束碼 4（集合不變）。**不改既有 `SystemAudioCheck` enum**，避免第 1 層合併後 Capture 的 `switch` 不完整而建置失敗。
- **停止路徑**：`MenuBar.swift` 的 `stopRecording`、`performStop`、`cancelFinalize`、`cancelBackgroundFinalize`、`hudStop`，`HUD.swift` 的 `stopPressed`，`Onboarding.swift` 的 `sendStop`，以及 `PreflightRunner.swift` 的兩處（`b0-audit.md:12-16`）：每個提早 return 前寫一行 log（Core `stopPathLogLine(source:reason:)` 格式化）。`stopTargetDecision(` 呼叫形狀不動。
- **N-4（前景退回路徑沒有整合測試）**：**不做**。理由：前景退回在 `RecordingSession` 的排隊鎖分支（`RecordingSession.swift:1180`），屬 Capture 層，`Tests/run.sh` 只編 Core（`b0-audit.md:26`），要整合測試就得先為 Capture 建測試骨架，超出本 epic。列為衍生工作。

## 9. 鐵則（MS-D9；G6）與通知（MS-D11；G9）

- **embedding**（ADR `adr/adr-ms-embeddings-temp.md`）：`diarize.sh` 以 `mktemp` 建暫存檔給 `MH_EMBEDDINGS_OUT`，聲紋比對用完就刪（`trap`）；場次資料夾不再出現 `embeddings.json`。`_voiceprint.py match/add` 新增 `--embeddings <路徑>`；`add` 沒有給時，呼叫 `_diarize_pyannote.py --embed-speaker` 依 `diarization.json` 的該講者時段當場算一次向量（暫存、用完刪），使用者確認後才寫進 `vault/voiceprints/`。舊場次已存在的 `錄音/embeddings.json` 只讀不寫、不自動刪（刪資料要使用者同意）。`.gitignore` 補 `embeddings.json`、`speakers.map.json`、`transcript.quality.json`、`.pipeline-state.lock`。
- **confidence**：`_merge_speakers.py:78`、`_render.py:270` 的預設由 1.0 改成 0（沒有 confidence 的 dict 視為未確認、不套名）。**門檻只有一套**：speakers.map 有 `apply` 聽 `apply`、沒有就 `confidence ≥ 0.7`、字串值（人工確認）直接套；聲紋比對寫 `apply` 時以 cos ≥ `RENAME_TH`（預設 0.75，`bin/_voiceprint.py:38`）為準（專案規則第 3 條作用在 apply 的產生端）。0.7 與 0.75 量的是不同的東西（map 信心值與 cos），寫進 spec §4.6.2。
- **人工確認不被覆蓋**：`_voiceprint.py:115-118` 改成：既有值是非空字串，或是 dict 而 `evidence` 不是以「聲紋庫比對」開頭（人工或 agent 寫的）→ 一律不覆蓋；只有上一次聲紋比對寫的 dict 才可能被信心更高的新結果取代（現行規則）。
- **raw 不轉**：`transcribe.sh:194-201` 的 `_to_tw.py` 不再改 `transcript.raw.md`；正體版另存 `transcript.md`（只在它不存在時寫，與「精修另存 transcript.md」一致，`.claude/skills/meeting-transcribe/SKILL.md:39`）。`transcript.segments.json` 是機器用的衍生檔，照舊轉字形（不是 raw 逐字稿）。
- **其他**：`_voiceprint.py remove` 過濾檔名（`bin/_voiceprint.py:172`）；meeting-speakers SKILL 補 annotate 步驟；`meta["embeddings"]` 改在寫 `diarization.json` 之前設定（`research-code-contracts.md:122`）。
- **通知**：Core 新增 `sessionCodeLabel(startedAt:runId:timeZone:)`（`backgroundJobLabel` 改呼叫它，輸出不變，`Core/BackgroundFinalize.swift:189-200`）。前處理完成／失敗／沒有執行三則通知（`Trigger/Completion.swift:138,172,180,182`）、錄製實例的完成通知（`RecordingSession.swift:1248-1250`）、menu bar 的完成通知（`MenuBar.swift:1129`）、異常中止通知（§17）內文一律改用場次代號，不含場次名或路徑。「在 Finder 顯示」用的 `userInfo.session` 不是顯示文字，保留。

## 10. 不採用 `aac_at`

intent §5 Q3 的建議是「先量 `aac_at` 的收益再決定要不要申請改 `test_static_rules`」，§7 沒有決定改它。本設計：concat 照舊用內建 `aac`（`test_static_rules.py:505-522` 不改）；`video-spike` 量 `aac` 與 `aac_at` 在 2 小時 PCM 上的耗時寫進證據檔。若第 2 層量測顯示影片超過 5 分而 `aac_at` 能補回，再以 spec §7 疑慮 3 回報、另開核准，不在本輪預先申請。

## 11. 三方資源分配（MS-D12；intent §4.1.1）

同一台機器可能同時有：這一場錄製、上一場背景收尾、這一場 ASR worker。優先順序：錄製 ＞ 背景收尾 ＞ worker。
- 錄製：不變。
- 背景收尾：沿用 R3x-D9，錄製中平行度降為 2（`bin/_record_finalize.py:93`）。
- worker：`nice -n 10`；錄製中只要有別場背景收尾還活著就不開新窗；丟幀就暫停到停止（§5）。
- 停止之後：這一場的收尾（平行度依現行規則）、prep 的分離、worker 補窗三者並行；GPU 爭用的實際影響由 `replay-bench` 量（intent §4.4）。

## 12. 量測（MS-D13；G1、G4）

- `tools/bench/replay.py`（新，測試用工具，不是對外介面）：給一個保留段落的目錄，在暫存區建沙盒場次（名稱用「[Stand-up] 範例專案」）與沙盒 `MH_RECORD_HOME`；依各段 `startedAt`／`finishedAt` 的間隔、乘上 `--speed` 倍率，逐段把段落放進 `tracks/` 並更新 manifest；起 worker（`--no-worker` 可關）；最後一段放完算「停止」，起 `_record_finalize.py`，認到「音訊就緒」就起 `meeting.sh prep <沙盒場次>`（只帶 `MH_PREP_RUN_ID`），沒有這一行時等收尾結束再起（量舊流程）。
- 報告（JSON）：`stopToAudioReady`、`stopToSpeakersMd`、`stopToVideo`、`stopToWav`（正式 wav 出現在 `錄音/` 第一層的時刻）、`stopToAllReady`（三者取最大）、`verifySeconds`、`workerBacklogAtStop`、`speed`、`segments`、`recordedSeconds`；**不記任何來源路徑或場次名**（公開 repo，數字可以抄進 progress.md）。
- 加速重放時 worker 追不上的段數會比實際多，量到的停止後時間偏大（誤差方向保守，intent §5 Q6）；報告記下停止當下欠幾窗。
- 品質比對：`replay.py --compare-full` 另跑一次整檔轉錄，依 §5 的兩個門檻算字差異率與時間差比例。
- **G1 拆兩條線量（D2，使用者 2026-10-21 核准；spec §4.14.4）**：逐字稿線（`stopToSpeakersMd`、`stopToWav`）用 2026-10-20 的 2 小時舊段落重放量——正式 wav 不等影片，舊段落走重編也不影響這兩個數字；影片線（`stopToVideo`）用新錄製器（有 `canvasLock`）的實錄量，實錄不足 121 段時依段數線性外推，外推值 > 240 秒時補錄一場 ≥ 2 小時的會議（E4(2)）。
- 資料來源（C10）：保留段落的路徑由使用者在量測時提供或由主 session 量；子 agent 不讀 `~/.meeting-harness/`。

## 13. 結構重構（MS-D14；G8）

- **誰做**：各檔的擁有者，在自己的速度／修正 commit 之後另做一個 `refactor(meeting-speed)` commit；`record.sh` 由 `record-sh-split` 在第 1 層做（速度改動不碰它）。分工見 §1.1。重構 commit 前後該子任務的完成條件測試都要綠（行為不變）。
- **原則：被靜態測試釘住的函式與字面留在原檔**（`test_r2_static.py`、`test_r3_app_static.py`、`test_r3x_app_static.py`、`test_static_rules.py`、`test_r3x_parallel_finalize.py` 的 `need()` 與模組全域，`research-code-contracts.md:127-135`）。可以搬的是沒被釘住的部分（例如 `MenuBar.swift` 的圖示繪製、`RecordingSession.swift` 的監看與落盤 helper、`_record_finalize.py` 的分析與補償函式），Swift 用 `extension` 放到新檔，Python 搬到 `bin/lib/` 再由原模組 import（可變全域不搬，避免副本問題）。
- 依這個原則，預估要改的既有測試為 **0 條**（intent §7 Q4 的「重構批次」，spec §6 第 22 條預留）。build 中若發現非改不可，該子任務停下回報，由主 session 一次送使用者核准，不得自行改測試。
- 目標用行數判定（spec §4.13.1）：`MenuBar.swift`、`RecordingSession.swift` 各 ≤ 1000 行；`PreflightRunner.run` ≤ 80 行；`_record_finalize.py` ≤ 1300 行；`record.sh` 的 `cmd_control` ≤ 100 行；`transcribe.sh` 不再有品質檢查的 heredoc（搬到 `bin/lib/_transcript_quality.py`）。
- 重複 helper（spec §4.13.2）：`paused_total`、`write_json_atomic`、`load_json`、`record_home` 由 `prep-pipeline` 在 `bin/lib/_record_lib.py` 公開、`finalize-fast` 改 import。`paused_total` 兩份在連續兩個 pause 時結果不同，以 `_record_finalize` 的算法（取後一個）為準（E4(3)）：`red-py` 先寫鎖定 `_record_finalize.paused_total` 現行輸出的測試，`prep-pipeline` 把 `_record_lib.paused_total` 改成同一算法（`pause_pairs`、`output_time` 不動），`finalize-fast` 再改 import；這是對 `_record_lib.paused_total` 呼叫端的行為變更，呼叫端清單在 spec §4.13.2。`harness_config` 三份合一移出本 epic（§1.1；衍生工作（不編號））。`bin/_record_prompt.py:45` 的 `load_json` 不併（衍生工作（不編號））；`meeting.sh` 的 HF token 檢查是 bash，不在範圍。

## 14. 測試策略（MS-D15；intent §7 Q4）

| 類別 | 做法 |
|---|---|
| 速度相關 | 一律繞開既有測試：保留 `nextSegmentSize(` 呼叫、concat 的 `-c:a aac`、步驟名集合、mlx_whisper CLI 接縫、`_record_finalize.py` 的頂層名稱；copy 路徑只對有 `canvasLock` 的場次生效 |
| 鐵則（源頭修正） | `diarize.sh`、`_merge_speakers.py` 直接改；`test_diarize_and_merge_untouched` 刪除（spec §6 第 18 條，D1 已核准） |
| C8 靜默重轉 | `test_diarize_keeps_raw` 照 spec §6 第 20 條改（D1 已核准），歸 `prep-pipeline` 的完成條件 |
| `test_r3_lock` 容差 | +2 → +6（spec §6 第 21 條，D1 已核准） |
| 結構重構 | 原則上 0 條（spec §6 第 22 條預留）；`test_r3x_parallel_finalize.py` 的 ResourceWarning 不修（衍生工作） |
| 新測試 | `tests/record/test_ms_*.py`（Python）、`tools/MeetingRecorder/Tests/MSCoreTests.swift`（Swift），由 Red 層先寫 |
| 每個子任務的驗收（D4） | lint＋doctor、Swift `run.sh`、Python 全量、名稱掃描四件套都跑（spec §4.15.1）；例外統稱「允許仍紅」（E3）：(i) red-swift 階段 Swift `run.sh` 只因缺 spec §3.10 名稱而編譯失敗；(ii) plan §3 每層開工清單（R0／R1／R2）內、由其他子任務負責的測試；清單外任何紅燈一律失敗。判定方式是比對 `FAIL:`／`ERROR:` 的測試 ID，可機械判定 |

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
| 擷取幀率／尺寸上限對 WindowServer 負擔的影響（D3 d） | `video-spike` 第 5 節；使用者決定 |

## 17. 當晚錄製異常中止的修正（MS-D17；D3）

背景（`_tpm/runs/20261021-sdlc-meeting-speed/incident-2018-windowserver.md`，不含客戶名稱）：WindowServer 高 CPU 後重啟、GUI session 重建，錄製器失去 WindowServer 連線就結束，收尾來不及跑；最後一段沒收尾、共享狀態停在 `stopping`。判斷不是 `RecordingSession` 停止流程的缺陷，所以修的是「事後接手」與「收尾的既有缺陷」，不改停止流程。

| 項 | 做法 | 子任務 | spec |
|---|---|---|---|
| (a) 補尾幀數 | §4.2 的「補尾幀數」 | `finalize-fast` | §4.4.12 |
| (b) 選單啟動偵測 | Core `abnormalStopSession(status:pidAlive:sessionExists:segmentsPending:)` 判定（`phase == .stopping`、共享狀態檔記錄的 pid 已不在、場次目錄存在；不看 `record.pid`，E2）；`MenuBar` 啟動時讀狀態檔、`kill(status.pid, 0)`、檢查場次目錄，成立就發通知並提供「收尾」動作，按下才跑 `meeting.sh record finish <場次>`（使用者一鍵，不自動跑：收尾會花數分鐘 CPU，且使用者可能想先看段落） | `ms-core`（判定）、`trigger-ui`（啟動、通知、動作） | §4.16.1–§4.16.2 |
| (c) `finish` 不帶參數 | `record.sh cmd_finish` 沒有參數時用同一套條件（bash 版：讀 `record.status.json` 的 `pid`／`phase`／`session`、`kill -0`、目錄存在）找可接手的場次；有就在 stderr 印一行說明後照 `finish <場次>` 跑，沒有就照舊回 2。結束碼集合與 usage 不改 | `record-sh-split` | §4.16.3–§4.16.4 |
| (d) 擷取幀率／尺寸 | `video-spike` 量三種設定，回報使用者 | `video-spike`；決定後才派 `recorder-capture` | §4.4.13 |

**判定為什麼不用 `record.pid`（E2）**：`meeting record stop` 遇到 `record.pid` 的 pid 已死時會刪掉 `record.pid`（`bin/record.sh:822,829`）。使用者常見的順序是「發現錄製怪怪的 → 先按停止 → 再收尾」，這時 `record.pid` 已經不在，若判定要求 `record.pid` 存在，`finish` 不帶參數與選單偵測都會落空。共享狀態檔 `record.status.json` 的 `pid` 欄（`Core/Records.swift` 的 `RecordStatus.pid`）不會被 `stop` 刪，所以改用它。

**判定為什麼是兩份（Swift 與 bash）**：選單 app 與 CLI 是兩個入口，現行的守門也是兩份（`Core/Lock.swift:56-57` 與 `bin/record.sh:19`）。兩份都只讀 `record.status.json` 一個檔、條件逐字寫在 spec §3.10 與 §4.16.3，由各自的測試釘住。

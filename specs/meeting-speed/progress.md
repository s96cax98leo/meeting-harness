# progress：meeting-speed

- 由主 session 依 integrator 的合併結果維護；子任務不得改本檔（plan §2 共通）。
- 子任務 id 是短名，不是任務編號。量測數字只抄 `tools/bench/replay.py` 的報告（不含路徑與場次名）。

## 閘門

- [x] 閘門 1（intent）：2026-10-21 使用者核准（`run.json` 的 `plan.approved`）
- [x] 閘門 2（design／spec／plan）：2026-10-21 使用者核准（`run.json` 的 `design.approved`）。閘門 2 前已決定 D1–D5（2026-10-21：§6 第 1–21 條核准、G1 拆兩條線量、事故 4 項併入、每子任務四件套、不開第 4 層與品質門檻）與 E1–E4（2026-10-21：§6 第 23 條確認；第 24 條確認、異常中止判定改用共享狀態檔的 pid；四件套例外統稱「允許仍紅」；拿掉早期模式、外推 > 240 秒補長錄、`paused_total` 以 `_record_finalize` 為準）；待整份核准
- [x] 擷取幀率／尺寸（spec §4.4.13）：使用者 2026-10-22 決定維持 60 fps；WindowServer 實測待實機
- [ ] 閘門 3（test）：2026-10-25 使用者接受 G1 逐字稿線與 CER 的實測值（spec §6 第 28 條）；閘門本身待核准
- [ ] 閘門 4（deliver）

## 子任務

### Red
- [x] `red-py`
- [x] `red-swift`

### 第 1 層
- [x] `ms-core`
- [x] `asr-robust`
- [x] `diarize-iron`（沒有 refactor commit；`harness_config` 合一移出本 epic）
- [x] `prep-pipeline`（含 `_record_lib.paused_total` 改用 `_record_finalize` 的算法）
- [x] `record-sh-split`（feat：`finish` 不帶參數接手，判定只讀共享狀態檔＋refactor commit）
- [x] `video-spike`（copy 結論：未定；擷取幀率／尺寸：待使用者決定）
- [x] `replay-bench`

### 第 2 層
- [x] `finalize-fast`（含 refactor commit）
- [x] `recorder-capture`（含 refactor commit）
- [x] `trigger-ui`（含 refactor commit）

### 第 3 層
- [x] `incremental-asr`
- [x] `docs-cleanup`

## 每層整合（plan §3）

| 層 | 合併點 | plan §3 指令 | 備註 |
|---|---|---|---|
| Red | — | — | |
| 第 1 層 | — | — | |
| 第 2 層 | — | — | |
| 第 3 層 | — | — | |

## 量測：逐字稿線（spec §4.14.3、§4.14.4 (i)；實際量的是 2026-10-21 的 2 小時 18 分場、141 段，見 §6 第 28 條）

改之前約 30 分（`baseline.md` A 節）。目標：最終 1× 重放 `stopToSpeakersMd ≤ 300` 且 `stopToWav ≤ 300` 秒。這批段落沒有 `canvasLock`，`stopToVideo`／`stopToAllReady` 只記錄、不判定。

| 時點 | speed | flow | stopToAudioReady | stopToSpeakersMd | stopToWav | stopToVideo | stopToAllReady | workerBacklogAtStop | videoPath |
|---|---|---|---|---|---|---|---|---|---|
| 基準（Red 後，`--legacy`） | 10 | legacy | | | | | | | |
| 第 1 層後 | — | 沒有逐層量（§6 第 28 條） | | | | | | | |
| 第 2 層後（前處理 glob 修正前，手動補量） | 100000 | early | 22.1 | 約 690（手動） | 22.2 | 2302.0 | 2412.0 | — | reencode |
| 第 3 層後（stitch 拒用最後一段） | 8 | early | 21.5 | 789.2 | 21.6 | 2298.3 | 2407.8 | 1 | reencode |
| asr-tail 後（HEAD 1aad87f，採用此值） | 8 | early | 20.9 | 332.4 | 21.0 | 2282.3 | 2392.2 | 1 | reencode |
| 最終（1×） | — | 未量；使用者接受上一列實測值（§6 第 28 條） | | | | | | | |

品質（spec §4.11.9，`--compare-full`；門檻 CER ≤ 5%、≥ 95%，D5 核准）：`cer` ＝ 0.0754（未達標，使用者 2026-10-25 接受）；`timeAlignedRatio` ＝ 0.9564。

## 量測：影片線（spec §4.14.4 (ii)；新錄製器實錄）

| 實錄段數 | 實測 stopToVideo | 外推到 121 段 | > 240 秒要補長錄？（E4(2)） | 補錄實測 |
|---|---|---|---|---|
| 40（2026-10-25 實錄，39 分 52 秒，`canvasLock` 2992×1876） | 54 秒（`videoPath`＝copy；concat 46.8 秒） | 163 秒（54 × 121 ÷ 40） | 否（≤ 240） | — |

## 實機（test 段，spec §4.4.11、§4.11.10、§4.12.4）

- [x] ≥ 30 分鐘實錄（2026-10-25，40 段）：`droppedFrames` ＝ 0；停止當下欠窗 ＝ 0（最後一窗在停止後 3 秒寫出）；`videoPath` ＝ copy；`stopToVideo` ＝ 54 秒；停止 → wav 6 秒；停止 → `transcript.speakers.md` 81 秒；錄製器的 python3（pyenv shim）可 import mlx_whisper
- [ ] `e2e_check.py`（2026-10-25 實錄）：§4.4.11 指定的 `video_format`、`video_covers_audio`（差 2 ms）、`one_audio_file`、`wav_format`、`canvas` 都 PASS；**`gap` FAIL**：第 2→3 段邊界 0.969 秒（門檻 0.5），其餘邊界 −0.007～0.016 秒。第 2 段音訊只有 59.03 秒，時間上與 ASR worker 第一次載入模型、轉第 1 窗（約 07:56:15–07:56:27）重疊，因果尚未證實；使用者 2026-10-25 記錄接受（spec §6 第 29 條）
- [ ] 缺陷 B、F、N 情境重驗（這場沒有刻意縮放視窗；未做）
- [ ] WindowServer 負擔實測、異常中止的「收尾」按鈕（未做）
- [x] 兩則通知文字不含場次名、視窗標題、路徑（2026-10-25 使用者確認：「會議錄製完成」「前處理完成」內文只有時間）

# progress：meeting-speed

- 由主 session 依 integrator 的合併結果維護；子任務不得改本檔（plan §2 共通）。
- 子任務 id 是短名，不是任務編號。量測數字只抄 `tools/bench/replay.py` 的報告（不含路徑與場次名）。

## 閘門

- [x] 閘門 1（intent）：2026-10-21 使用者核准（`run.json` 的 `plan.approved`）
- [ ] 閘門 2（design／spec／plan）：閘門 2 前已決定 D1–D5（2026-10-21：§6 第 1–21 條核准、G1 拆兩條線量、事故 4 項併入、每子任務四件套、不開第 4 層與品質門檻）與 E1–E4（2026-10-21：§6 第 23 條確認；第 24 條確認、異常中止判定改用共享狀態檔的 pid；四件套例外統稱「允許仍紅」；拿掉早期模式、外推 > 240 秒補長錄、`paused_total` 以 `_record_finalize` 為準）；待整份核准
- [ ] 擷取幀率／尺寸（spec §4.4.13）：等 `video-spike` 回報後由使用者決定（決定前 `recorder-capture` 不開工）
- [ ] 閘門 3（test）
- [ ] 閘門 4（deliver）

## 子任務

### Red
- [ ] `red-py`
- [ ] `red-swift`

### 第 1 層
- [ ] `ms-core`
- [ ] `asr-robust`
- [ ] `diarize-iron`（沒有 refactor commit；`harness_config` 合一移出本 epic）
- [ ] `prep-pipeline`（含 `_record_lib.paused_total` 改用 `_record_finalize` 的算法）
- [ ] `record-sh-split`（feat：`finish` 不帶參數接手，判定只讀共享狀態檔＋refactor commit）
- [ ] `video-spike`（copy 結論：未定；擷取幀率／尺寸：待使用者決定）
- [ ] `replay-bench`

### 第 2 層
- [ ] `finalize-fast`（含 refactor commit）
- [ ] `recorder-capture`（含 refactor commit）
- [ ] `trigger-ui`（含 refactor commit）

### 第 3 層
- [ ] `incremental-asr`
- [ ] `docs-cleanup`

## 每層整合（plan §3）

| 層 | 合併點 | plan §3 指令 | 備註 |
|---|---|---|---|
| Red | — | — | |
| 第 1 層 | — | — | |
| 第 2 層 | — | — | |
| 第 3 層 | — | — | |

## 量測：逐字稿線（spec §4.14.3、§4.14.4 (i)；2026-10-20 的 2 小時場、121 段重放）

改之前約 30 分（`baseline.md` A 節）。目標：最終 1× 重放 `stopToSpeakersMd ≤ 300` 且 `stopToWav ≤ 300` 秒。這批段落沒有 `canvasLock`，`stopToVideo`／`stopToAllReady` 只記錄、不判定。

| 時點 | speed | flow | stopToAudioReady | stopToSpeakersMd | stopToWav | stopToVideo | stopToAllReady | workerBacklogAtStop | videoPath |
|---|---|---|---|---|---|---|---|---|---|
| 基準（Red 後，`--legacy`） | 10 | legacy | | | | | | | |
| 第 1 層後 | 10 | | | | | | | | |
| 第 2 層後 | 10 | | | | | | | | |
| 第 3 層後 | 10 | | | | | | | | |
| 最終（1×） | 1 | early | | | | | | | |

品質（spec §4.11.9，`--compare-full`；門檻 CER ≤ 5%、≥ 95%，D5 核准）：`cer` ＝ ＿；`timeAlignedRatio` ＝ ＿。

## 量測：影片線（spec §4.14.4 (ii)；新錄製器實錄）

| 實錄段數 | 實測 stopToVideo | 外推到 121 段 | > 240 秒要補長錄？（E4(2)） | 補錄實測 |
|---|---|---|---|---|
| | | | | |

## 實機（test 段，spec §4.4.11、§4.11.10、§4.12.4）

- [ ] ≥ 30 分鐘實錄：`droppedFrames` ＝ ＿；停止當下欠窗 ＝ ＿；`videoPath` ＝ ＿；`stopToVideo` ＝ ＿
- [ ] 缺陷 B、F、N 情境重驗
- [ ] 兩則通知文字不含場次名、視窗標題、路徑

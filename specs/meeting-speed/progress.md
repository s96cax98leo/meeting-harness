# progress：meeting-speed

- 由主 session 依 integrator 的合併結果維護；子任務不得改本檔（plan §2 共通）。
- 子任務 id 是短名，不是任務編號。量測數字只抄 `tools/bench/replay.py` 的報告（不含路徑與場次名）。

## 閘門

- [x] 閘門 1（intent）：2026-10-21 使用者核准（`run.json` 的 `plan.approved`）
- [ ] 閘門 2（design／spec／plan）：spec §6 第 1–17 條、第 18–21 條（第 19、21 條可分開）、§4.11.9 品質門檻
- [ ] 閘門 3（test）
- [ ] 閘門 4（deliver）

## 子任務

### Red
- [ ] `red-py`
- [ ] `red-swift`

### 第 1 層
- [ ] `ms-core`
- [ ] `asr-robust`
- [ ] `diarize-iron`
- [ ] `prep-pipeline`
- [ ] `record-sh-split`
- [ ] `video-spike`（結論：未定）
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

## 量測（spec §4.14；2 小時場、121 段）

改之前約 30 分（`baseline.md` A 節）。目標：`stopToAllReady ≤ 300` 秒。

| 時點 | speed | flow | stopToAudioReady | stopToSpeakersMd | stopToWav | stopToVideo | stopToAllReady | workerBacklogAtStop | videoPath |
|---|---|---|---|---|---|---|---|---|---|
| 基準（Red 後，`--legacy`） | 10 | legacy | | | | | | | |
| 第 1 層後 | 10 | | | | | | | | |
| 第 2 層後 | 10 | | | | | | | | |
| 第 3 層後 | 10 | | | | | | | | |
| 最終（1×） | 1 | early | | | | | | | |

品質（spec §4.11.9，`--compare-full`）：`cer` ＝ ＿；`timeAlignedRatio` ＝ ＿。

## 實機（test 段，spec §4.4.11、§4.11.10、§4.12.4）

- [ ] ≥ 30 分鐘實錄：`droppedFrames` ＝ ＿；停止當下欠窗 ＝ ＿；`videoPath` ＝ ＿；`stopToVideo` ＝ ＿
- [ ] 缺陷 B、F、N 情境重驗
- [ ] 兩則通知文字不含場次名、視窗標題、路徑

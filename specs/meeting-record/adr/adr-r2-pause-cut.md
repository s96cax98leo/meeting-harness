# ADR：整段暫停的實作（R2，F2：暫停段在成品中剪掉、記下時間點）

- 狀態：提議（待 R2 閘門 2 核准）
- 日期：2026-10-12
- 範圍：`tools/MeetingRecorder/Sources/Capture/RecordingSession.swift`、`bin/_record_finalize.py`、`tests/record/e2e_check.py`
- 關係：沿用 `adr-segment-writer.md` 的「一條 stream 不停、每段一個 `AVAssetWriter`、新段第一個視訊 sample 落在邊界」（`adr-segment-writer.md:38-42`）

## 背景

- 使用者決定：「整段暫停時，暫停那段在成品中剪掉，但要記下時間點」（brief:14）；情境是「想暫時不錄（例如講私事）」（brief:5）。
- 錄製實例的換段機制已有「舊段轉 prev、只收 PTS < 邊界的 sample、1 秒或三路都過界後收尾」（`RecordingSession.swift:437-444`、`:523-527`）與「新段第一幀以最後一個 complete 幀重新打戳」（`:449-454`）。
- `ingest` 在 `cur == nil` 時會自動開新段並把原因記成 `.writerFailure`（`:356-361`），`maxEnd` 在換段判斷之前就更新（`:347`）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 暫停＝在停止點 E 收掉目前段落、期間丟棄 sample，繼續＝以第一個 sample 開新段（brief 定案） | 重用 prev 機制收段；`ingest` 加暫停閘門；新增 `SwitchReason.resume`；finalize 照常串接，暫停段自然不在成品裡 | 產生短於 60 秒的段與等於暫停長度的空隙，分段判準（`spec.md §4.4.3`、`§4.4.8`）要加排除；`levels` 時間軸要定義暫停期間怎麼寫 |
| B. 照常寫檔，finalize 依 `pauseEvents` 剪掉 | 錄製端只記事件 | **暫停期間的畫面與聲音會落盤**（`tracks/seg-*.mov`，且 `tracks/` 永不自動刪，`design.md:157`），與「講私事不想被錄」的目的相反；finalize 要多一段精確剪接（跨段、關鍵幀），新增失敗面 |
| C. 暫停時 `stopCapture`、繼續時 `startCapture` | 擷取端真的停 | t6 實測 `startCapture` 第一次失敗要重試（`design.md §7.6`，`startCaptureSettleSeconds`）；繼續要等數秒、可能失敗；SCK 停止期間偵測器、裝置監看都要另外處理；與「一條 stream 不停」的定案衝突 |

## 決定

採 **A**。理由：只有 A 同時做到「暫停內容不落盤」與「重用已驗過的換段機制」；B 違背使用者暫停的目的；C 引入 t6 已踩過的 `startCapture` 不穩定。

落實（細節在 `design.md` R2-D3、`spec.md` §4.18）：
1. 暫停：停止點 E＝當下的 `maxEnd`；若有 prev 先收掉；目前段轉成 prev（`prevEnd = E`），`cur = nil`、`nextBoundary` 失效、設暫停旗標。段落沒有任何內容（E ≤ 段起點或沒寫過 sample）就捨棄，與停止時相同。
2. 暫停中：`ingest` 在更新 `maxEnd` **之前**判斷暫停旗標——PTS < E 的晚到 sample 照 `routeSample` 寫進 prev，其餘丟棄；不得觸發 `cur == nil` 的自動開段；complete 幀仍更新 `lastFrame`（不寫入），供繼續時的新段首幀用。
3. 繼續：清暫停旗標並設「下一個 sample 開新段」；下一個 PTS ≥ E 的 sample 以它的 PTS 為邊界開新段（`SwitchReason.resume`），新段首幀照 `adr-segment-writer.md` 以最後一個 complete 幀重新打戳。
4. 事件：`record.meta.json.pauseEvents` 記 `{t, outputT, wallClock, kind}`；暫停的 `t`＝E − t0，繼續的 `t`＝新段 `startedAt`（同一把 sample 時鐘）。
5. finalize：串接不變；`gapStats` 對暫停邊界扣掉暫停長度並新增 `pausedTotal`；`e2e_check.py` 的 `gap`、`segment_cadence`、`stop_tail` 依 `pauseEvents` 排除或扣除。

## 後果

- 暫停中按停止：停止點沿用 E，最後一筆 `pauseEvents` 是沒配對的 `pause`；`stop_tail` 以它的 `t` 代替 `wallClock` 比對（`spec.md` §4.18.5）。
- **閘門 2 修正輪（2026-10-12）**：上面第 2、3 步的判斷（暫停旗標、sample 去向、開段原因）抽成 `Core/Segments.swift` 的純函式（`PauseGate`、`pauseRoute`、`openReason`），`SwitchReason` 從 Capture 的 private enum 搬到 Core 並加 `resume`；事件 append 與狀態欄位走 `Core/Control.swift`（`appendingPauseEvent`、`pauseStatusFields`）。理由：讓「resume 換段」能以 Swift Core 單元測試驗收（intent R2-2；`spec.md` §4.18.8、§4.18.9）。決定本身（A）不變。
- 暫停很久時 SCK 是否照常送 sample、會不會有其他行為，沒有本機數據（`research-specs-adr.md` R2-4）；t7 錄 30 秒暫停時觀察 `record.log` 的丟幀摘要。
- 暫停前後的兩段之間沒有轉場，成品在剪點是硬接（影片與音訊同時）；這是「剪掉」的直接結果。

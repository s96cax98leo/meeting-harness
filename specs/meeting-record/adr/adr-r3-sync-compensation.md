# ADR：S-C 依時段補償系統聲音的輸出延遲（R3）

- 狀態：提議（待 R3 閘門 2 核准）
- 日期：2026-10-13
- 範圍：`bin/_record_finalize.py`、`bin/record.sh`（`record sync`）、`tools/MeetingRecorder/Sources/Capture/RecordingSession.swift`（輸出裝置變更提前換段）、`Core/SyncLatency.swift`、`tests/record/e2e_check.py`
- 關係：依賴 `adr-r3-concat-then-mix.md`（混音流程）；沿用 `adr-segment-writer.md` 的段落模型

## 背景

- 一手證據：SCK 系統聲音的 PTS 約等於 render 時間，不含輸出裝置延遲；內建喇叭聲學回授 mic − sys 為 25–26 ms（`sync` §2.3）。
- 推論（未實測）：戴藍牙 A2DP 開會、播放端又補償了輸出延遲時，成品聲音會比畫面早約 150–185 ms，超過 ITU-R BT.1359 的 90 ms（`sync` §0 第 4 點）。
- 使用者決定 2：長期要重現「使用者當下看到與聽到的時間關係」；R3 先量測（S-A、S-B）再補償（S-C），S-C 預設 off，預設要不要開由實機驗收場 E2／E4 決定。
- 限制：方向或大小錯了，偏移會加倍（`sync` §6 風險第 1 點）；A2DP 與 HFP 的實測與回報值方向可能相反（intent R3-5 第 1 點）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. finalize 依時段補償，開關 off／reported／calibrated，預設 off（本案） | 錄製器在輸出裝置變更時提前換段，一段只對應一個輸出裝置；finalize 依每段生效的延遲把系統聲音往後放；開關放 `record.defaults.json`，CLI 寫、環境變數可覆寫 | 要改 D20 混音流程（另一則 ADR）；多一個 CLI 寫法；預設 off 時沒有使用者可見的改善 |
| B. 錄製中重新打戳（寫進段落時就把系統聲音 PTS 加 L_out） | 段落本身就是補償後的 | 改到 raw 段落，錯了救不回；`syn` §1.3 已列為不做 |
| C. 整檔 `-itsoffset` 一次平移 | 實作最少 | 中途換裝置（內建 ↔ 藍牙）時只能用一個值，另一半必錯；`syn` §1.3 已列為不做 |
| D. 不補償，只在文件說明 | 零風險 | 和使用者決定 2 的長期方向不一致 |

## 決定

採 **A**。理由：只有 A 能處理中途換裝置（依時段），而且不動 raw 段落（重跑 `meeting record finish` 可以換 mode 比較）；預設 off 符合「先量測、E2／E4 證實後才開」。

- 延遲值：`reported`＝(Latency＋SafetyOffset＋stream Latency＋BufferFrameSize) ÷ NominalSampleRate（S-B 記在 `record.meta.json.outputLatencies`）；`calibrated`＝`~/.meeting-harness/sync-calibration.json` 依輸出 uid 查表（查不到用 0）；一律夾在 [0, 0.5] 秒。
- 開關：`record.defaults.json.syncCompensation`（`meeting record sync <mode>` 寫，合併寫入，`adr-r3-defaults-writers.md`）；`MH_SYNC_COMPENSATION` 優先。不用純環境變數的理由：menu bar 停止時由 app 啟動收尾，讀不到使用者 shell 的環境變數。
- 記錄：`finalize.json.syncCompensation` 記每段套用的延遲與來源，`e2e_check.py --sync-player` 讀它報告。

## 後果

- 「輸出裝置變更提前換段」不論 mode 都會發生，所以 off 時段落切分可能和 R2 不同；off 的「等價」判準見 `spec.md` §4.37.3（e2e 判準相同、長度差 ≤ 0.1 秒、`--sync` 每個事件變化 ≤ 1 幀），不要求逐位元相同。
- `SwitchReason` 多一個 `.outputDeviceChange`，既有測試的列舉預期要改（`spec.md` §6 第 127 條）。
- 補償後，VAD 與標記從系統聲音推回成品時間要加 L_out：`_record_lib.output_time(..., l_out)` 預留參數，S-C 合併時啟用。
- 預設值的變更要另記 `spec.md` §6，並經使用者核准。

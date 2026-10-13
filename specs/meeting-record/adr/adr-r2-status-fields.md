# ADR：R2 新增的狀態與事件欄位放在哪裡

- 狀態：提議（待 R2 閘門 2 核准）；閘門 2 使用者決定 3（2026-10-12）選本 ADR 的建議（nil 省略鍵、`RecordsTests` 不改）
- 日期：2026-10-12
- 範圍：`tools/MeetingRecorder/Sources/Core/Records.swift`（`RecordStatus`、`RecordMeta`、`GapStats`）、`record.status.json`、`錄音/tracks/record.meta.json`、`manifest.json`

## 背景

- brief 定案：status 只加選用欄位（`paused`、`micMuted`、`pausedSeconds`、`markers`、`recentLevels`），不新增 `RecordPhase`（brief:36）；`record.meta.json` 新增 `pauseEvents`、`micMuteEvents`（brief:22-23）。
- `Core/Records.swift:3-4` 的慣例：Optional 為 nil 時寫 null、不省略鍵。
- 既有測試釘住鍵集合：`record.status.json` 恰為 12 個鍵（`tools/MeetingRecorder/Tests/RecordsTests.swift:112-113`）、`record.meta.json` 恰為 7 個鍵（`:58`）。
- 讀者相容性：Swift 舊版 `readStatus` 用 `JSONDecoder` 解，多出的鍵會被忽略、缺少的 Optional 鍵解成 nil；新增 enum 值才會失敗（`Sources/Capture/Support.swift:105-108`）。Python 讀者一律 `.get(...)`。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 加成 Optional、nil 時**省略鍵**（Swift 合成的 `encodeIfPresent`） | 錄製實例在 R2 錄製中一律寫入；舊狀態檔、測試的樣本沒有這些值就沒有這些鍵 | 違反 `Records.swift:3-4` 的「nil 寫 null」慣例，要在 spec 記為例外；讀者要把「鍵不存在」當成「沒有這項能力／資料」 |
| B. 加成 Optional、照慣例寫 null | 慣例一致 | 既有兩支鍵集合測試要改預期（`rules.md:37` 的例外，需使用者核准）；每個舊版錄製寫出的狀態檔與新版看起來不同，不易分辨「舊版」與「新版但沒有值」 |
| C. 另開 `record.live.json` 放錄製中的即時欄位 | 既有檔完全不動 | 偏離 brief「status 只加選用欄位」；menu bar 與 CLI 要多讀一個檔並處理兩檔不同步（例如 status 已 `done`、live 還是暫停中） |

## 決定

採 **A**。理由：不改既有測試、不偏離 brief、舊版讀者零影響；而且「鍵不存在」本身正好就是能力判斷——`controlVersion` 不存在＝舊版錄製器，不送 SIGUSR1（`adr-r2-control-file.md`）。B 的「null」反而會讓這個判斷多一種狀態。

範圍：
- `RecordStatus` 新增 8 個 Optional：`controlVersion`、`recordingStartedAt`、`paused`、`micMuted`、`pausedSeconds`、`pausedAt`、`markers`、`recentLevels`（`spec.md` R2 §3.10）。比 brief 多出的三個（`controlVersion`、`recordingStartedAt`、`pausedAt`）分別解決 SIGUSR1 能力判斷、計時起點早於開錄約 10 秒（`research-code-contracts.md` C8）、暫停中計時。
- `RecordMeta` 新增 2 個 Optional 陣列：`pauseEvents`、`micMuteEvents`；R2 錄製實例開錄時就寫空陣列，所以新場次的 meta 一定有這兩鍵。
- `GapStats` 新增 Optional `pausedTotal`（finalize 寫，沒有暫停時寫 0.0）。
- **巢狀型別內部仍照「nil 寫 null」**：`RecentLevels` 的 `system`／`mic` 為 nil 時寫 null（`Records.swift:3-4` 的慣例只在頂層新欄位破例）。

## 後果

- `spec.md` R2 §3.10 與 §6 第 79 條記錄此例外；既有 `testStatusJSONKeys`、`testMetaJSONKeys` 不改，另加 R2 測試驗「有值時鍵存在、無值時鍵不存在」。
- 以後若要再加狀態欄位，沿用本 ADR：頂層新欄位 Optional＋省略，不加 enum 值。

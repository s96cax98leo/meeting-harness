# ADR：音訊先出——早期 wav 放哪裡、前處理怎麼拿到

- 狀態：提議（待 meeting-speed 閘門 2 核准）
- 日期：2026-10-21
- 範圍：`bin/_record_finalize.py`、`bin/meeting.sh`（prep）、`bin/transcribe.sh`、`bin/diarize.sh`、`tools/MeetingRecorder/Sources/Capture/FinalizeRunner.swift`、`Core/Records.swift`、`Core/Control.swift`、`Trigger/Completion.swift`

## 背景

- intent §7 Q2（使用者決定）：wav 先寫到 `錄音/tracks/`，自動前處理直接讀它；正式 wav 照舊在最後一刻 rename 進 `錄音/`；「場次存在＝錄製完成」（meeting-record spec §4.6.5、R3-§6 第 140 條）不變；`RecordStatus` 加 Optional `audioReady`，不新增 phase。
- 限制一：`transcribe.sh:65-70` 數音源所在目錄的影音檔，超過 1 個就不套 VAD；`錄音/tracks/` 本層有 `seg-*.mov`。
- 限制二：`transcribe.sh` 的 VAD 以「音源所在目錄」當 `rec_dir` 去找 `tracks/manifest.json`（`bin/lib/_record_lib.py:244`）。
- 限制三：`diarize.sh` 以 `_combine_audio.py "$REC"` 取音源（`bin/diarize.sh:24`），`錄音/` 第一層沒有音檔就回 3。
- 限制四：`meeting.sh prep` 只認 `錄音/` 第一層有音檔的場次（`list_sessions`，`bin/meeting.sh:286-298`）。
- 限制五：Python 收尾子程序不寫狀態檔（`research-code-contracts.md:101`）；狀態通道只有狀態檔＋pid＋SIGTERM（`adr-control-channel.md:21-29`）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. `錄音/` 第一層用 `.` 開頭的隱藏檔名（例 `錄音/.<場次>.wav`），影片好了再 rename 成正式名 | `_combine_audio.py` 本來就排除隱藏檔（`bin/_combine_audio.py:16-17`），場次不會被列出 | prep 一樣要多一個輸入來源；rename 時 prep 可能正在讀同一個路徑（diarize 還沒開檔就會找不到）；第一層多一個隱藏大檔，`ls -a` 的使用者會困惑 |
| B. **`錄音/tracks/audio/<正式檔名>.wav`＋伴隨 `ready.json`；prep 以 `MH_PREP_EARLY=1` 選擇性讀它；正式 wav 以 hard link 一次出現** | 子目錄只有這一支音檔，`transcribe.sh` 不會誤判多音檔；檔名與正式 wav 相同，逐字稿標頭不用改；hard link 不複製資料，prep 讀的路徑在發佈後仍有效 | 要三個內部環境變數：`MH_PREP_EARLY`（prep 選擇讀它）、`MH_TRANSCRIBE_REC_DIR`（VAD 的 rec_dir）、`MH_DIARIZE_AUDIO`（分離的音源）；發佈從 rename 改成 link，meeting-record §4.6.5 的「rename」字面要修訂（仍是同一檔案系統、一次出現）；`tracks/audio/` 那個名稱要有人清（prep 結束時確認同 inode 才移除） |
| C. `meeting.sh prep` 新增顯式參數 `--audio <路徑>` | 語意最清楚 | 新增對外子指令選項，`meeting.sh` 是其他 session 用的介面，usage、SKILL、`surface.py` 都要動；自動前處理以外沒有人需要它 |

## 決定

採 **B**。理由：
1. 唯一同時滿足限制一到四而不改對外子指令的做法；三個環境變數只由 `AutoPrepRunner` 與 `meeting.sh` 內部設定，跟既有的 `MH_EMIT_SEGMENTS`、`MH_EMBEDDINGS_OUT` 同一類。
2. hard link 讓「prep 正在讀」與「正式發佈」互不干擾；A 的 rename 有路徑消失的競態。
3. 對外呈現照 intent §7：`audioReady: Bool?`（nil 省略鍵，沿用 `adr-r2-status-fields.md`），由 `FinalizeRunner` 認 stdout 的「音訊就緒：」一行後寫入，Python 不寫狀態檔。

## 後果

- meeting-speed spec §3.2（`tracks/audio/`、`ready.json`）、§3.7（環境變數）、§3.8（stdout 行）、§4.2、§4.3。
- meeting-speed spec §6 第 9 條：meeting-record §4.6.5 的「rename」修訂為「rename 或 hard link（同一檔案系統、一次出現）」。
- 沒有 `MH_PREP_EARLY` 時 `meeting.sh prep` 的行為逐字不變；其他 session 看不到 finalize 中的場次（`test_concurrency.py::test_finalizing_session_not_listed` 不改）。
- 冪等多一個中間態：`ready.json` 與這次輸入相同 → 不重寫 wav，只補影片（meeting-speed spec §4.3.2）。

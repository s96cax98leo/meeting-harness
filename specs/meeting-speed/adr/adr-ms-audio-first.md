# ADR：音訊先出——正式 wav 何時出現、前處理怎麼拿到

- 狀態：提議（待 meeting-speed 閘門 2 核准；修正輪 1 依使用者 D2 改採選項 D；修正輪 2：使用者 2026-10-21 確認 spec §6 第 23 條（E1）與拿掉早期模式（E4(1)））
- 日期：2026-10-21
- 範圍：`bin/_record_finalize.py`、`tools/MeetingRecorder/Sources/Capture/FinalizeRunner.swift`、`Core/Records.swift`、`Core/Control.swift`、`Trigger/Completion.swift`

## 背景

- intent §7 Q2（閘門 1）：wav 先寫到 `錄音/tracks/`，自動前處理直接讀它；正式 wav 照舊在最後一刻 rename 進 `錄音/`；「場次存在＝錄製完成」（meeting-record spec §4.6.5、R3-§6 第 140 條）不變；`RecordStatus` 加 Optional `audioReady`，不新增 phase。
- **D2（使用者 2026-10-21，閘門 2 前）**：G1 的逐字稿線用 2026-10-20 的舊段落重放量；正式 wav 必須先於影片發佈、不等影片。舊段落沒有 `canvasLock`、一律走重編（spec §4.4.9），若正式 wav 等影片，`stopToWav` 就包含整段重編，量不到 300 秒以內（skeptic 第 1 點）。
- 限制一：`transcribe.sh:65-70` 數音源所在目錄的影音檔，超過 1 個就不套 VAD。
- 限制二：`transcribe.sh` 的 VAD 以「音源所在目錄」當 `rec_dir` 去找 `tracks/manifest.json`（`bin/lib/_record_lib.py:244`）。
- 限制三：`diarize.sh` 以 `_combine_audio.py "$REC"` 取音源（`bin/diarize.sh:24`）。
- 限制四：`meeting.sh prep` 只認 `錄音/` 第一層有音檔的場次（`list_sessions`，`bin/meeting.sh:293-298`）。
- 限制五：Python 收尾子程序不寫狀態檔（`research-code-contracts.md:101`）；狀態通道只有狀態檔＋pid＋SIGTERM（`adr-control-channel.md:21-29`）。
- 限制六：既有 `test_concurrency.py::test_finalizing_session_not_listed` 不改；它把「`finalize.json` 有 `finishedAt` 且 `outputs.audio` 就是第一層那支音檔」視為已發佈（`tests/record/test_concurrency.py:19-26`）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. `錄音/` 第一層用 `.` 開頭的隱藏檔名，影片好了再 rename 成正式名 | `_combine_audio.py` 排除隱藏檔（`bin/_combine_audio.py:16-17`） | 正式 wav 仍等影片，違反 D2；prep 要多一個輸入來源；rename 時有路徑消失的競態 |
| B.（前一版採用）`錄音/tracks/audio/<正式檔名>.wav`＋`ready.json`；prep 以 `MH_PREP_EARLY=1` 讀它；正式 wav 在影片後以 hard link 出現 | 不改對外子指令；正式 wav 最後才出現，「場次存在＝錄製完成」字面不變 | 正式 wav 仍等影片，違反 D2；要三個內部環境變數（`MH_PREP_EARLY`、`MH_TRANSCRIBE_REC_DIR`、`MH_DIARIZE_AUDIO`）與一段 inode 清理邏輯 |
| C. `meeting.sh prep` 新增顯式參數 `--audio <路徑>` | 語意最清楚 | 新增對外子指令選項（`meeting.sh` 是其他 session 用的介面）；正式 wav 何時出現的問題沒解 |
| D. **音訊一備好就發佈正式 wav：`.part` 寫在 `錄音/tracks/.finalize/`，依序寫 `錄音/tracks/audio-ready.json`、`finalize.json` 第一階段，再 `os.replace` 進 `錄音/`；影片之後補 `finalize.json` 第二階段** | 符合 D2；prep 照現行方式讀 `錄音/` 第一層，限制一到四自動成立，不需要任何新環境變數；「先 `finalize.json`、wav 後出現」的順序不變，限制六成立 | 「場次存在」的意義從「收尾全部完成」變成「錄音成品就緒」（meeting-record §4.6.5、R3-§6 第 140 條、intent §7 Q2 那一句要修訂，spec §6 第 23 條）；影片收尾期間 `meeting status`、`meeting prep <根>` 會列出該場（spec §7 疑慮 11）；`finalize.json.finishedAt` 的意義改為錄音成品發佈時刻 |

## 決定

採 **D**。理由：
1. 只有 D 同時滿足 D2（正式 wav 不等影片）與限制六（`test_concurrency` 不改）。
2. 正式 wav 一出現在 `錄音/` 第一層，現行 prep、轉錄 VAD、分離取音源的路徑全部照舊可用，B 的三個環境變數與清理邏輯都成為多餘；D1 對 `MH_DIARIZE_AUDIO` 的放行因此用不到；使用者 2026-10-21 確認拿掉 B 的早期模式（E4(1)；spec §7 疑慮 13）。
3. 對外呈現照 intent §7 Q2：`audioReady: Bool?`（nil 省略鍵，沿用 `adr-r2-status-fields.md`），由 `FinalizeRunner` 認 stdout 的「音訊就緒：」一行後寫入，Python 不寫狀態檔。

## 後果

- meeting-speed spec §3.2（`audio-ready.json`、發佈順序）、§3.4（`finalize.json` 兩階段）、§3.7（拿掉三個環境變數）、§3.8（stdout 行）、§4.2、§4.3。
- meeting-speed spec §6 第 9 條撤回（不再用 hard link）；第 23 條記錄 meeting-record §4.6.5、R3-§6 第 140 條與 intent §7 Q2「最後一刻」一句的修訂（「場次存在」改為錄音成品就緒、影片可能還在收尾），使用者 2026-10-21 確認（E1）。
- 影片失敗或逾時回 5 時，正式 wav 與 `finalize.json` 第一階段保留；`already_done` 要兩個成品檔都在才算完成（`bin/_record_finalize.py:735-746`），下次 `record finish` 只補影片（spec §4.2.5、§4.3.2）。
- 冪等多一個中間態：`audio-ready.json` 與這次輸入相同、正式 wav 在 → 不重寫 wav，只補影片（spec §4.3.2）。

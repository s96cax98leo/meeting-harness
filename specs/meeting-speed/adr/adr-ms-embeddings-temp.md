# ADR：每場的講者 embedding 只存暫存檔，建聲紋時當場重算

- 狀態：提議（待 meeting-speed 閘門 2 核准）
- 日期：2026-10-21
- 範圍：`bin/diarize.sh`、`bin/_diarize_pyannote.py`、`bin/_voiceprint.py`、`.claude/skills/meeting-speakers/SKILL.md`、`.claude/skills/meeting-summary/SKILL.md`、`.gitignore`

## 背景

- 專案規則第 5 條（`.claude/teams/rules.md:66`）：聲紋只存 `vault/voiceprints/`、只由使用者確認過的對應才建檔。
- 現況：`embeddings.json` 寫在場次資料夾（`bin/diarize.sh:31`、`bin/_diarize_pyannote.py:223-240`），含沒確認過的講者；`.gitignore` 沒排除它。
- intent §7 最後一項（使用者決定）：每場 embedding 只在聲紋比對當下用 mktemp 暫存檔，比對完就刪；不落在場次資料夾、也不進 `vault/`；使用者確認對應之後才寫進 `vault/voiceprints/`。intent §5 預設第 3 條（放 `vault/` 底下的暫存目錄）作廢。
- 衝突點：`_voiceprint.py add <場次> <SPEAKER_xx> <姓名>` 需要那個講者的向量（`bin/_voiceprint.py:129`），而確認對應通常發生在 prep 之後很久（看完 speakers.md 才確認），那時暫存檔早就刪了。
- 既有測試 `test_review_fixes.py:40-108` 在場次資料夾放 `錄音/embeddings.json` 測 `match`、`add`。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. **`add` 沒給 embedding 時，依 `diarization.json` 該講者的時段當場重算一次向量（暫存、用完刪）** | 完全符合使用者決定的字面；不留任何每場 embedding | `add` 要能跑 pyannote 的 embedding 模型（需要 diarize venv，跟 prep 同一個前提）；重算的向量與分離當下的向量不會位元相同（同一模型、同一批時段，差異應很小，未量測） |
| B. 比對後把 embedding 留在 `vault/.session-embeddings/<場次代號>.json`，確認後再搬 | `add` 不必重算 | 使用者在閘門 1 明確否決（intent §7：不進 `vault/`） |
| C. `add` 時要求使用者重跑一次 `meeting diarize`（暫時保留 embedding 再建檔） | 程式最少 | 要重跑整場分離（2 小時場約 3.5 分）；`diarization.json` 冪等跳過，要先刪它才會重跑＝刪資料 |

## 決定

採 **A**。

- `diarize.sh`：`MH_EMBEDDINGS_OUT` 沒有被呼叫端指定時，改用 `mktemp` 建的暫存檔（`trap` 在結束時刪）；聲紋比對以 `--embeddings <暫存檔>` 呼叫 `_voiceprint.py match`。場次資料夾不再寫 `embeddings.json`。
- `_diarize_pyannote.py` 新增 `--embed-speaker <wav> <diarization.json> <SPEAKER_xx> <out.json>`：只取該講者的時段算一支向量。
- `_voiceprint.py`：`match`、`add` 新增 `--embeddings <路徑>`。`add` 沒給時，先看場次資料夾有沒有舊的 `錄音/embeddings.json`（舊場次，只讀），沒有就呼叫 `--embed-speaker` 重算到暫存檔、建檔後刪。`test_review_fixes.py` 的情境（舊檔存在）因此照舊通過。
- 舊場次已存在的 `錄音/embeddings.json` 不自動刪（刪資料要使用者同意）；meeting-speakers SKILL 寫明怎麼手動清。
- `.gitignore` 補 `embeddings.json`（第二道防線）。

## 後果

- meeting-speed spec §4.6；§6 第 14、18 條（刪除 `test_diarize_and_merge_untouched`，使用者 2026-10-21 已核准，D1）。
- 重算向量需要 diarize venv 就緒；沒有時 `add` 回 2 並提示 `bash bin/setup-diarize.sh`（結束碼沿用 `_voiceprint.py` 既有的 2）。
- 「重算與原始向量的差異」未量測，列為 spec §7 疑慮 6。

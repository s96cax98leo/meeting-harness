---
name: meeting-summary
description: 會議錄音/錄影 → 逐字稿 → 講者識別 → 結構化繁中會議紀錄（決議/依賴/風險/交辦）→ Word/wiki。全程本機（轉錄、OCR、講者分離都不出電腦）。給一個會議資料夾就能跑。當使用者要「整理會議/做會議紀錄/總結錄音/逐字稿+摘要」時使用。
---

# meeting-summary（會議紀錄總流程）

把一場會議的錄音／螢幕錄影（＋投影片截圖）變成可用的會議紀錄。
工具在 **`/Users/yuktang/Documents/Agent/meeting-harness`**（以下用 `$MH`），**任何工作目錄都能呼叫**。

```bash
MH=/Users/yuktang/Documents/Agent/meeting-harness
```

## 0. 先確認環境
```bash
bash "$MH/bin/meeting.sh" doctor
```
缺東西時它會直接告訴你裝什麼（轉錄模型、講者分離環境、HuggingFace 授權都在這裡檢查）。
完整指令表：`bash "$MH/bin/meeting.sh" help`

## 1. 本機前處理（轉錄 + 投影片 OCR + 講者分離）

**會議還沒開始、要錄下來？** 先用 **meeting-record** skill 錄會議視窗與雙路音訊，錄完的場次直接接下面的前處理。

**資料還沒分場**（錄影、截圖全丟在同一個資料夾）：
```bash
bash "$MH/bin/meeting.sh" ingest "<資料夾>" --dry-run   # 先看會怎麼分
bash "$MH/bin/meeting.sh" ingest "<資料夾>"             # 依時間戳分場（--split 可一檔一場）
```

**跑前處理**（可重跑、冪等；已有產物會 SKIP）：
```bash
bash "$MH/bin/meeting.sh" <型態> "<會議根目錄>"
```
型態決定講者數範圍與總結模板，會記在該場 `錄音/meeting.json`，之後不用再指定：

| 型態 | 場景 | 型態 | 場景 |
|---|---|---|---|
| `seminar` | 研討會／演講 | `1on1` | 一對一 |
| `internal` | 內部會議 | `workshop` | 工作坊 |
| `client` | 客戶會議（對外） | `interview` | 訪談／面談 |

產物（每場）：`錄音/transcript.raw.md`（原始逐字稿，**不要改它**）、`transcript.segments.json`、
`diarization.json`、`transcript.speakers.md`（帶講者名）、`照片/.ocr/*.txt`。
語者向量不落場次資料夾（只在分離時的暫存檔，比對完即刪）；舊場次留下的 `錄音/embeddings.json` 可手動清掉（見 meeting-speakers）。

## 2. 寫會議紀錄（這步是你要做的事）

讀 `錄音/transcript.speakers.md`（有講者標籤的版本）＋ `照片/.ocr/*.txt`，
**產出 `<場次>/meeting.record.json`**（schema：`$MH/schema/meeting-record.v1.json`），
不要自己手寫 summary.md。欄位怎麼填見 **meeting-notes** skill。

然後渲染：
```bash
bash "$MH/bin/meeting.sh" render "<場次目錄>"
```
一份 JSON 會產出：`summary.md`（人看的）、`actions.csv`、`actions.ics`（RFC 5545 待辦）、
`錄音/transcript.vtt`（WebVTT 字幕）。要改內容就改 record 再 render 一次——
**直接改 summary.md 會被下次 render 蓋掉。**

`summary.md` 固定含「一句話：」與 `## 決議 / ## 依賴 / ## 風險與未決 / ## 交辦 / ## 存疑`，
下游知識庫專案 的 `/ingest-meeting` 可以直接吃。

## 3. 發佈（選用）
Word／Obsidian wiki／術語表與會議索引 → 見 **meeting-publish** skill。

## 重要原則
- **原始逐字稿不動**：`transcript.raw.md` 是引擎原始輸出，不刪段、不改寫。精修另存 `transcript.md`。
- **不編造負責人與期限**：逐字稿沒明講就留空（會渲染成「（未指定）」），並列進 `uncertain[]`。
- **不確定的名字就別掛**：講者識別信心不足時維持 `SPEAKER_0x`，寫進存疑。寧可匿名也不掛錯人。
- **雜訊段照實標**：任何 ASR 在交談重疊/吵雜段都會出錯；`.QUALITY_WARNING` 檔會標出重複迴圈，
  那些段落在紀錄裡標「（聽不清）」，不要當成真的發言。

## 在 harness 專案裡執行時
`$MH/.claude/agents/` 有 8 個專職 subagent（transcribe / slide-ocr / slide-vision / summarizer /
meeting-notes / speaker-id / verifier / publisher），可以分派。在其他工作目錄就照本 skill 自己做。

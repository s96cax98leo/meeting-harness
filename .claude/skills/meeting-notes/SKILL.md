---
name: meeting-notes
description: 把逐字稿寫成結構化的繁中會議紀錄——決議、逐議題討論、交辦表格（負責人/期限/狀態）、依賴、風險與未決、存疑。六種會議型態各有模板。當需要 會議紀錄 / 會議總結 / 待辦整理 / 決議追蹤 時使用。
---

# meeting-notes（會議紀錄怎麼寫）

`MH=/Users/yuktang/Documents/Agent/meeting-harness`

## 輸入
- `錄音/transcript.speakers.md`（帶講者名的逐字稿；沒有就用 `transcript.md` / `transcript.raw.md`）
- `照片/slides.md` 或 `照片/.ocr/*.txt`（若有）
- `錄音/meeting.json`（型態、出席名單）
- `$MH/vault/術語表.md`（跨會議專名，統一寫法用）

## 輸出：`<場次>/meeting.record.json`（**不要自己寫 summary.md**）
依 `$MH/schema/meeting-record.v1.json`：

| 欄位 | 放什麼 |
|---|---|
| `summary.oneLiner` / `tldr` | 一句話結論 + 3–5 條重點 |
| `decisions[]` | **明確拍板或取得共識**的才算；`by` 填拍板人 |
| `topics[]` | 逐議題：`points` 寫討論要點，`speakers` 標發言者 |
| `actions[]` | 交辦：`owner`／`due` **只從逐字稿抽**，抽不到留空 |
| `dependencies[]` | 跨團隊的等待關係（**最常被漏**）：誰在等誰、什麼時候要 |
| `risks[]` | 風險／爭議／不同意見，標 `severity` 與各方立場 |
| `openQuestions[]` | 沒結論、要下次談、被擱置的 |
| `uncertain[]` | 聽不清的人名／專名／日期，附 `heardAs` |
| `glossary[]` | 本場新出現的專名 |

寫完渲染：
```bash
bash "$MH/bin/meeting.sh" render "<場次目錄>"
```
→ `summary.md`（依型態套模板）、`actions.csv`、`actions.ics`、`錄音/transcript.vtt`。
改內容＝改 record 再 render；**直接改 summary.md 會被蓋掉**。

## 各型態的重點
| 型態 | 紀錄重心 |
|---|---|
| `internal` | 決議 → 逐議題 → 交辦 |
| `client` | 決議 → 交辦 → **承諾了什麼、範圍講到哪裡**（對外文件，用詞要能見人） |
| `1on1` | 交辦導向：誰要做什麼、什麼時候回報 |
| `workshop` | 分組產出與共識 |
| `interview` | 問答逐題 |
| `seminar` | 議程／重點／技術細節；決議與交辦通常是空的，寫「（無）」不要刪標題 |

## 鐵則
- **不編造負責人與期限**。逐字稿沒明講就留空（渲染成「（未指定）」），並在 `uncertain[]` 提醒補。
  推測語氣（「應該是這週五吧」）要在 `detail` 寫明是推測，並降低 `confidence`。
- **決議 vs 討論分清楚**：沒拍板的歸 `openQuestions[]`，不要塞進 `decisions[]`。
- **講者歸屬要有依據**：有講者稿才把主張掛到人身上；信心不足的名字不要用，寫存疑。
- **逐字稿一定有聽錯**：人名、產品名、日期尤其。可疑的寫進 `uncertain[]` 附 `heardAs`，
  不要自己腦補成「看起來合理」的詞。
- 雜訊／交談重疊段（`.QUALITY_WARNING` 標出來的）標「（聽不清）」，不要當成真發言。

`summary.md` 固定含「一句話：」與 `## 決議 / ## 依賴 / ## 風險與未決 / ## 交辦 / ## 存疑`，
下游（下游知識庫專案 的 `/ingest-meeting`）是照這些標題找東西的，不要改標題名稱。

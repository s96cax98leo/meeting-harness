---
name: meeting-publish
description: 把會議紀錄發佈出去：Word（.docx）、Obsidian wiki 頁（frontmatter + wikilinks），並更新跨會議術語表與會議索引。當需要 轉 Word / 轉 docx / 發佈到 wiki / publish 會議紀錄 時使用。
---

# meeting-publish（發佈 Word / wiki）

`MH=/Users/yuktang/Documents/Agent/meeting-harness`

## Word
```bash
bash "$MH/bin/to-docx.sh" "<場次>/summary.md" "<輸出.docx>"
```
pandoc 為主。需要精細版面（樣式、頁首頁尾、圖表）時改用 officecli，並用「產出 → 看 → 修」的迴圈驗證。

## Obsidian wiki ＋ 長期記憶
```bash
python3 "$MH/bin/publish.py" "<場次目錄>" "$MH" "<會議名稱>"
```
- wiki 頁：`vault/wiki/<會議>/<場次>.md`（frontmatter + wikilinks），來源標註會自動移除
- 長期記憶：併入 `vault/術語表.md`（跨會議專名一致）與 `vault/會議索引.md`（一句話摘要那行）

## 發佈前檢查
- 紀錄內容是否都有逐字稿／投影片支撐？沒有佐證的要標「（存疑）」而不是寫死。
- 交辦的負責人／期限是不是真的有人講？沒講就是「（未指定）」。
- **對外文件**（客戶會議）發佈前再看一次「存疑」段，別把聽錯的人名或產品名送出去。

## 其他格式
`meeting.sh render` 已經產好 `actions.csv`（貼試算表）、`actions.ics`（RFC 5545，匯入行事曆／提醒事項）、
`錄音/transcript.vtt`（WebVTT 字幕）。不用另外轉。

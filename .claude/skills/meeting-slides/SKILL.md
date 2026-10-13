---
name: meeting-slides
description: 讀投影片照片／螢幕截圖裡的文字。sips 把 HEIC 轉 JPG，Apple Vision（ocrmac）做繁中+英文本機 OCR；架構圖/流程圖/表格再用視覺補讀語意。當需要 OCR / 讀圖片文字 / 投影片內容 / 截圖轉文字 時使用。
---

# meeting-slides（投影片／截圖讀取）

本機 OCR，離線。`MH=/Users/yuktang/Documents/Agent/meeting-harness`

```bash
bash "$MH/bin/ocr-slides.sh" "<照片目錄>"
```
- HEIC/HEIF → JPG（sips），既有 jpg/png 一併納入 → `照片/.jpg/`
- Apple Vision OCR（zh-Hant + en-US）→ `照片/.ocr/<原檔名>.txt`
- 回傳每張的字數；字太少或明顯是圖表的，列入 `needsVision`

## 視覺補讀（OCR 讀不出語意的那些）
架構圖、流程圖、表格、甘特圖 OCR 只會拿到零散字串。這些要**直接看圖**（Read 該圖片），
把元件、資料流、關係、表格欄位寫成文字，合併成 `照片/slides.md`。

寫的時候：
- 照實描述圖上有什麼，不要補腦沒畫出來的東西。
- 表格就寫成 Markdown 表格，欄位名保留原文。
- 讀不清楚的標「（圖上看不清）」。

## 產物
`照片/slides.md`——供會議紀錄引用（`refs` 的 `src` 填 `slides`）。

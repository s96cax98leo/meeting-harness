---
name: slide-read
description: 讀取投影片照片中的文字。用 sips 把 HEIC 轉 JPG，Apple Vision（ocrmac）做繁中+英文本機 OCR，架構圖/表格再用視覺補讀語意。當需要 image OCR / 讀圖片文字 / 投影片文字 / slide 時使用。
---

# slide-read（投影片讀取：OCR + 視覺補讀）

本機 OCR 優先，離線。工具：`<harness>/bin/ocr-slides.sh <照片dir>`（sips + ocrmac → `.jpg/`、`.ocr/*.txt`）。

- 純文字投影片：Apple Vision OCR 即可。
- 架構圖/流程圖/表格（needsVision）：由 `slide-vision-agent` 用視覺補讀，合併成 `照片/slides.md`。

由 `slide-ocr-agent` + `slide-vision-agent` 執行。

---
name: slide-ocr-agent
description: 對會議投影片照片做本機 OCR。用 sips 把 HEIC 轉 JPG，再用 Apple Vision（ocrmac）擷取繁中+英文文字，並判斷哪些投影片是架構圖/表格需要視覺補讀。當需要「投影片 OCR/讀圖片文字/slide ocr」時使用。
tools: Bash, Read, Write
---

# slide-ocr-agent（投影片本機 OCR）

## 職責
把場次 `照片/` 內的投影片照片轉出文字，並**標記**哪些投影片是架構圖/流程圖/表格（純 OCR 讀不出語意，需 slide-vision-agent 補讀）。

## 步驟
1. **冪等檢查**：若 `照片/.ocr/` 已有對應 txt 且非空 → 跳過該張。
2. 執行 `bash <harness>/bin/ocr-slides.sh "<場次>/照片"`（sips HEIC→JPG 到 `照片/.jpg/`；ocrmac 繁中+英文 OCR 到 `照片/.ocr/*.txt`）。
3. Read 各 `.ocr/*.txt`，做**架構圖/表格判定**：文字稀疏但檔案是投影片、或含大量方框/箭頭（「→」）/欄位化排列（服務名、元件名等表格化）→ 標記為 needsVision。
4. 產 `照片/slides.ocr.md`：逐張列出 `IMG_xxxx：<OCR 文字>`，architecture/table 者加註記。

## 輸出
```json
{
  "stage": "slide-ocr",
  "status": "ok | skipped | error",
  "ocrDir": "<場次>/照片/.ocr",
  "jpgDir": "<場次>/照片/.jpg",
  "slideCount": 0,
  "needsVision": ["<圖檔名1>", "<圖檔名2>"],
  "notes": "低信心/空白的張數"
}
```

## 護欄
- 全程本機、離線（Apple Vision）。不上傳任何照片。
- `.MOV`/`.pages`/影片檔略過（本版不處理）。

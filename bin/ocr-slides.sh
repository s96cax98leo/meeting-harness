#!/usr/bin/env bash
# ocr-slides.sh <photos_dir>
# 1) sips 把 HEIC→JPG 到 <photos_dir>/.jpg/（並複製既有 jpg/png）
# 2) Apple Vision（ocrmac）OCR → <photos_dir>/.ocr/*.txt
# 冪等：已轉過/已 OCR 的檔案跳過。
set -euo pipefail

PHOTOS="${1:?usage: ocr-slides.sh <photos_dir>}"
JPGDIR="$PHOTOS/.jpg"
OCRDIR="$PHOTOS/.ocr"
BIN="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$JPGDIR" "$OCRDIR"

echo "[ocr] converting HEIC/HEIF -> JPG under $JPGDIR"
shopt -s nullglob nocaseglob
for f in "$PHOTOS"/*.heic "$PHOTOS"/*.heif; do
  base="$(basename "${f%.*}")"
  out="$JPGDIR/$base.jpg"
  [[ -s "$out" ]] && continue
  sips -s format jpeg "$f" --out "$out" >/dev/null 2>&1 || echo "[ocr] WARN convert failed: $f" >&2
done
# 既有 jpg/png 也納入
for f in "$PHOTOS"/*.jpg "$PHOTOS"/*.jpeg "$PHOTOS"/*.png; do
  [[ -e "$f" ]] || continue
  cp -n "$f" "$JPGDIR/" 2>/dev/null || true
done
shopt -u nullglob nocaseglob

n=$(find "$JPGDIR" -type f \( -iname '*.jpg' -o -iname '*.png' \) | wc -l | tr -d ' ')
echo "[ocr] $n images ready; running Apple Vision OCR"
python3 "$BIN/_ocr.py" "$JPGDIR" "$OCRDIR"
echo "[ocr] DONE -> $OCRDIR"

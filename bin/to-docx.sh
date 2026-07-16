#!/usr/bin/env bash
# to-docx.sh <summary.md> <out.docx>
# 主：pandoc md→docx。備：若無 pandoc，提示改用 OfficeCLI 精細版面路徑。
set -euo pipefail

MD="${1:?usage: to-docx.sh <summary.md> <out.docx>}"
OUT="${2:?usage: to-docx.sh <summary.md> <out.docx>}"
mkdir -p "$(dirname "$OUT")"

if command -v pandoc >/dev/null 2>&1; then
  pandoc "$MD" -o "$OUT" --from gfm --standalone
  echo "[docx] DONE (pandoc) -> $OUT"
else
  echo "[docx] ERROR: pandoc 未安裝。請 brew install pandoc，或改用 OfficeCLI 精細版面路徑。" >&2
  exit 4
fi

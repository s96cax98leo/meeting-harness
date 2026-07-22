#!/usr/bin/env bash
# transcribe.sh <audio_file> <out_markdown> [language]
# 本機轉錄：優先 mlx-whisper large-v3（Apple Silicon），fallback openai-whisper medium。
# 冪等：若 out_markdown 已存在且非空則跳過。
set -euo pipefail

AUDIO="${1:?usage: transcribe.sh <audio> <out.md> [lang]}"
OUT="${2:?usage: transcribe.sh <audio> <out.md> [lang]}"
LANG_CODE="${3:-zh}"

if [[ -s "$OUT" ]]; then
  echo "[transcribe] SKIP (exists): $OUT"
  exit 0
fi

if [[ ! -f "$AUDIO" ]]; then
  echo "[transcribe] ERROR: audio not found: $AUDIO" >&2
  exit 2
fi

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# 領域術語提示（降低專名誤植；繁中語境）。
# 預設為通用提示；可用環境變數 MH_TRANSCRIBE_HINT 覆寫成你當場的領域術語以提升準確度。
HINT="${MH_TRANSCRIBE_HINT:-以下為一場繁體中文的技術演講/會議，內容含中英文混雜的專有名詞、產品名與技術術語。}"

# 講者分離需要段落時間戳 → MH_EMIT_SEGMENTS=1 時輸出 all（含 .json）
OUTFMT="txt"; [[ "${MH_EMIT_SEGMENTS:-0}" == "1" ]] && OUTFMT="all"

echo "[transcribe] engine=mlx-whisper model=large-v3 audio=$AUDIO (output=$OUTFMT)"
if command -v mlx_whisper >/dev/null 2>&1; then
  # mlx-whisper console script 輸出 .txt/.srt/.json 到 output-dir
  # --condition-on-previous-text False：關鍵防迴圈（講座有停頓/掌聲易觸發 whisper 重複迴圈）
  mlx_whisper "$AUDIO" \
    --model mlx-community/whisper-large-v3-mlx \
    --language "$LANG_CODE" \
    --initial-prompt "$HINT" \
    --condition-on-previous-text False \
    --compression-ratio-threshold 2.4 \
    --output-dir "$WORKDIR" \
    --output-format "$OUTFMT" \
    --verbose False 2>&1 | tail -8 || {
      echo "[transcribe] mlx-whisper failed, falling back to openai-whisper" >&2
      whisper "$AUDIO" --model medium --language "$LANG_CODE" \
        --initial_prompt "$HINT" --condition_on_previous_text False \
        --output_dir "$WORKDIR" --output_format "$OUTFMT" 2>&1 | tail -5
    }
else
  echo "[transcribe] mlx-whisper 未安裝，使用 openai-whisper medium"
  whisper "$AUDIO" --model medium --language "$LANG_CODE" \
    --initial_prompt "$HINT" --condition_on_previous_text False \
    --output_dir "$WORKDIR" --output_format "$OUTFMT" 2>&1 | tail -5
fi

# 取第一個 .txt，包成 markdown（僅原始逐字稿，標點/校對交由 agent 精修）
RAW="$(find "$WORKDIR" -name '*.txt' | head -1)"
if [[ -z "$RAW" || ! -s "$RAW" ]]; then
  echo "[transcribe] ERROR: no transcript produced" >&2
  exit 3
fi

mkdir -p "$(dirname "$OUT")"
{
  echo "# 逐字稿（原始，mlx-whisper large-v3）"
  echo
  echo "> 來源：$(basename "$AUDIO")　語言：$LANG_CODE"
  echo
  cat "$RAW"
} > "$OUT"

# 講者分離用：保留段落時間戳 JSON
if [[ "${MH_EMIT_SEGMENTS:-0}" == "1" ]]; then
  SEGJSON="$(find "$WORKDIR" -name '*.json' | head -1)"
  if [[ -n "$SEGJSON" && -s "$SEGJSON" ]]; then
    cp "$SEGJSON" "$(dirname "$OUT")/transcript.segments.json"
    echo "[transcribe] segments -> $(dirname "$OUT")/transcript.segments.json"
  else
    echo "[transcribe] WARN: 未取得 segments JSON（講者分離將無法對齊）" >&2
  fi
fi

# 自我驗證：偵測 whisper 重複迴圈（同一行連續重複過多 = 轉錄失敗）
# 用 awk 一次算完，避免 head 早關管線在 pipefail 下觸發 SIGPIPE
MAXREP=$(sort "$RAW" | uniq -c | sort -rn | awk 'NR==1{print $1+0}')
MAXREP=${MAXREP:-0}
TOTAL=$(grep -cve '^[[:space:]]*$' "$RAW" || true)
TOTAL=${TOTAL:-1}
if [[ "${MAXREP:-0}" -ge 30 ]]; then
  echo "[transcribe] ⚠️  偵測到重複迴圈：某行重複 $MAXREP 次（共 $TOTAL 行非空）。轉錄可能失敗。" >&2
  echo "[transcribe] 建議：確認已用 --condition-on-previous-text False；必要時重跑或分段轉錄。" >&2
  echo "REPETITION_LOOP_DETECTED maxrep=$MAXREP total=$TOTAL" > "$OUT.QUALITY_WARNING"
fi

echo "[transcribe] DONE -> $OUT ($(wc -l < "$OUT" | tr -d ' ') lines; max-line-repeat=$MAXREP)"

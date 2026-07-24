#!/usr/bin/env bash
# diarize.sh <session_dir>
# 講者分離：m4a→wav(16k mono) → Senko → 錄音/diarization.json
# 冪等：diarization.json 存在且非空就跳過。全程本機、免 HF token。
set -uo pipefail

SESS="${1:?usage: diarize.sh <session_dir>}"
VENV="${MH_SENKO_VENV:-$HOME/.meeting-harness/senko-venv}"
PY="$VENV/bin/python"
BIN="$(cd "$(dirname "$0")" && pwd)"

REC="$SESS/錄音"
OUT="$REC/diarization.json"
WAV="$REC/.audio16k.wav"

if [[ -s "$OUT" ]]; then
  echo "[diarize] SKIP（已存在）：$OUT"; exit 0
fi
if [[ ! -x "$PY" ]] || ! "$PY" -c "import senko" 2>/dev/null; then
  echo "[diarize] senko 未就緒，請先： bash $BIN/setup-senko.sh" >&2; exit 2
fi

# 與轉錄用同一音源（多檔會串接成 .combined.wav，確保時間戳對齊）
AUDIO="$(python3 "$BIN/_combine_audio.py" "$REC" 2>/dev/null)"
if [[ -z "$AUDIO" ]]; then echo "[diarize] 找不到音檔於 $REC" >&2; exit 3; fi

echo "[diarize] 轉 16k mono wav：$(basename "$AUDIO")"
ffmpeg -y -i "$AUDIO" -ar 16000 -ac 1 "$WAV" >/dev/null 2>&1 || { echo "[diarize] ffmpeg 失敗" >&2; exit 4; }

echo "[diarize] Senko 分離中（本機 CoreML）…"
"$PY" "$BIN/_diarize.py" "$WAV" "$OUT" || { echo "[diarize] senko 執行失敗" >&2; exit 5; }
rm -f "$WAV"
echo "[diarize] DONE -> $OUT"

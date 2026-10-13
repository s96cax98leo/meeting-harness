#!/usr/bin/env bash
# diarize.sh <session_dir>
# 講者分離：音源 → wav(16k mono) → pyannote community-1（Apple Silicon GPU/MPS）→ 錄音/diarization.json
# 冪等：diarization.json 存在且非空就跳過。模型首次下載後即可離線使用。
set -uo pipefail

SESS="${1:?usage: diarize.sh <session_dir>}"
VENV="${MH_DIARIZE_VENV:-$HOME/.meeting-harness/diarize-venv}"
PY="$VENV/bin/python"
BIN="$(cd "$(dirname "$0")" && pwd)"

REC="$SESS/錄音"
OUT="$REC/diarization.json"
WAV="$REC/.audio16k.wav"

if [[ -s "$OUT" ]]; then
  echo "[diarize] SKIP（已存在）：$OUT"; exit 0
fi
if [[ ! -x "$PY" ]] || ! "$PY" -c "import pyannote.audio" 2>/dev/null; then
  echo "[diarize] 分離環境未就緒，請先： bash $BIN/setup-diarize.sh" >&2; exit 2
fi

# 與轉錄用同一音源（多檔會串接成 .combined.wav，確保時間戳對齊）
AUDIO="$(python3 "$BIN/_combine_audio.py" "$REC" 2>/dev/null)"
if [[ -z "$AUDIO" ]]; then echo "[diarize] 找不到音檔於 $REC" >&2; exit 3; fi

echo "[diarize] 轉 16k mono wav：$(basename "$AUDIO")"
ffmpeg -y -i "$AUDIO" -ar 16000 -ac 1 "$WAV" >/dev/null 2>&1 || { echo "[diarize] ffmpeg 失敗" >&2; exit 4; }

# 語者向量輸出給聲紋庫用（比對／建檔）
export MH_EMBEDDINGS_OUT="${MH_EMBEDDINGS_OUT:-$REC/embeddings.json}"

echo "[diarize] pyannote 分離中（裝置：${MH_DIARIZE_DEVICE:-auto}）…"
"$PY" "$BIN/_diarize_pyannote.py" "$WAV" "$OUT"; rc=$?   # 先收 exit code：放在 `if !` 之後會被吃掉變成 0
if [[ "$rc" -ne 0 ]]; then
  echo "[diarize] 分離失敗（exit=${rc}）" >&2
  case "$rc" in
    2|3) echo "[diarize] → 環境問題： bash $BIN/setup-diarize.sh" >&2 ;;
    4|5) echo "[diarize] → HuggingFace 授權／token 問題，見上面訊息" >&2 ;;
    6)   echo "[diarize] → 音檔沒有偵測到語音；可試 MH_DIARIZE_DEVICE=cpu 再跑一次" >&2 ;;
  esac
  echo "[diarize] → 轉錄與其餘流程不受影響；修好後單獨補跑： meeting.sh diarize <場次>" >&2
  rm -f "$WAV"
  exit 5
fi
rm -f "$WAV"

# 聲紋庫比對：命中就寫進 錄音/speakers.map.json（信心 <0.7 的只當線索，不改名）
python3 "$BIN/_voiceprint.py" match "$SESS" 2>/dev/null | tail -1

echo "[diarize] DONE -> $OUT"

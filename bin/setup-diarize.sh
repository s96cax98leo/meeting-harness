#!/usr/bin/env bash
# setup-diarize.sh — 建立講者分離專用 venv（pyannote.audio 4，跑 Apple Silicon GPU / MPS）
#
# 為什麼要獨立 venv：pyannote 依賴 torch（約 2.5GB）與一整串 lightning 生態，
# 跟主環境的 mlx-whisper / numpy 版本容易打架。venv 放在專案外，不進版控。
#
# 冪等：venv 已存在且 import 得到 pyannote.audio 就跳過。
set -uo pipefail

VENV="${MH_DIARIZE_VENV:-$HOME/.meeting-harness/diarize-venv}"
PY="$VENV/bin/python"

if [[ -x "$PY" ]] && "$PY" -c "import pyannote.audio" 2>/dev/null; then
  echo "[diarize-setup] 已就緒：$VENV"
  "$PY" - <<'PYCHK'
import torch
print(f"[diarize-setup] torch {torch.__version__}　MPS 可用：{torch.backends.mps.is_available()}")
PYCHK
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[diarize-setup] 需要 uv：請先 brew install uv" >&2
  exit 2
fi

echo "[diarize-setup] 建立 venv：${VENV}"
mkdir -p "$(dirname "$VENV")"
uv venv --python 3.12 "$VENV" || { echo "[diarize-setup] uv venv 失敗" >&2; exit 3; }

echo "[diarize-setup] 安裝 pyannote.audio（含 torch，約 2.5GB，首次較久）"
VIRTUAL_ENV="$VENV" uv pip install --python "$PY" "pyannote.audio>=4.0" 2>&1 | tail -8 \
  || { echo "[diarize-setup] 安裝失敗" >&2; exit 4; }

if "$PY" -c "import pyannote.audio" 2>/dev/null; then
  "$PY" - <<'PYCHK'
import torch
print(f"[diarize-setup] ✓ 完成　torch {torch.__version__}　MPS 可用：{torch.backends.mps.is_available()}")
PYCHK
  cat <<'NEXT'

還差一次性的模型授權（gated，免費、按一下就好）：
  1. 開 https://huggingface.co/pyannote/speaker-diarization-community-1 按 "Agree and access repository"
  2. 確認已登入：hf auth whoami      （沒有 token 就 hf auth login，或把 token 放 ~/.meeting-harness/hf-token）
之後執行： meeting doctor
NEXT
else
  echo "[diarize-setup] ✗ import pyannote.audio 失敗，請檢查上面的安裝輸出" >&2
  exit 5
fi

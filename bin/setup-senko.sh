#!/usr/bin/env bash
# setup-senko.sh — 建立 senko 專屬 venv 並安裝（講者分離用；本機 CoreML、免 HF token）
# 冪等：venv 已存在且 import senko 成功就跳過。venv 放專案外，不進 repo。
set -uo pipefail

VENV="${MH_SENKO_VENV:-$HOME/.meeting-harness/senko-venv}"
PY="$VENV/bin/python"

if [[ -x "$PY" ]] && "$PY" -c "import senko" 2>/dev/null; then
  echo "[senko] 已就緒：$VENV"
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[senko] 需要 uv：請先 brew install uv" >&2
  exit 2
fi

echo "[senko] 建立 venv：${VENV} (Python 3.13)"
mkdir -p "$(dirname "$VENV")"
uv venv --python 3.13 "$VENV" || { echo "[senko] uv venv 失敗" >&2; exit 3; }

echo "[senko] 安裝 senko（首次會下載 CoreML 模型，稍候）"
VIRTUAL_ENV="$VENV" uv pip install --python "$PY" "git+https://github.com/narcotic-sh/senko.git" 2>&1 | tail -15 \
  || { echo "[senko] 安裝失敗" >&2; exit 4; }

if "$PY" -c "import senko" 2>/dev/null; then
  echo "[senko] ✓ 安裝完成：$VENV"
else
  echo "[senko] ✗ import senko 失敗，請檢查安裝輸出" >&2
  exit 5
fi

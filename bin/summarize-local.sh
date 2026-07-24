#!/usr/bin/env bash
# summarize-local.sh <session_dir> [mode] [--agenda FILE] [--title T] [--speaker S]
# 本機總結（ollama 本地模型）。內容不出電腦。缺模型時提示 ollama pull / 退回 fallback。
set -uo pipefail
HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
SESS="${1:?用法: summarize-local.sh <場次目錄> [talk|meeting|panel] [--agenda F] [--title T] [--speaker S]}"
shift || true
MODE="talk"
case "${1:-}" in talk|meeting|panel) MODE="$1"; shift || true;; esac

# 自動偵測 mode：有 .meeting → meeting；名稱含 Panel/座談 → panel
if [[ -f "$SESS/錄音/.meeting" ]]; then MODE="meeting"; fi
case "$(basename "$SESS")" in *Panel*|*座談*) [[ "$MODE" == "talk" ]] && MODE="panel";; esac

if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[local] ollama 未啟動：請先開 ollama（ollama serve）" >&2; exit 2
fi
echo "[local] 本機總結：$(basename "$SESS")  mode=$MODE"
python3 "$HARNESS/bin/summarize-local.py" "$SESS" "$HARNESS" --mode "$MODE" "$@"

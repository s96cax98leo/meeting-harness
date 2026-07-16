#!/usr/bin/env bash
# meeting.sh —— 會議總結快速啟動器（meeting-harness 前門）
#
# 用法：
#   meeting.sh <會議根目錄>        對每個場次跑「本機轉錄 + 投影片OCR」(可重跑/冪等)，再印出 AI 步驟指令
#   meeting.sh prep <會議根目錄>    同上（顯式）
#   meeting.sh status <會議根目錄>  顯示每場流水線狀態
#   meeting.sh doctor              檢查工具鏈是否齊備
#
# 場次 = 會議根目錄下、含 `錄音/*.m4a` 的子資料夾。
# AI 步驟（總結/驗證/發佈 wiki+docx）請在 Claude Code 執行： /meeting-summary <會議根目錄>
# 注意：批次執行不用 -e，讓單一場次失敗不中斷其餘場次（改以顯式 if 檢查）。
set -uo pipefail

HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$HARNESS/bin"

doctor() {
  echo "== meeting-harness doctor =="
  python3 -c "import mlx_whisper" 2>/dev/null && echo "✓ mlx-whisper" || echo "✗ mlx-whisper（pip install mlx-whisper）"
  python3 -c "from ocrmac import ocrmac" 2>/dev/null && echo "✓ ocrmac (Apple Vision)" || echo "✗ ocrmac（pip install ocrmac）"
  command -v pandoc >/dev/null && echo "✓ pandoc" || echo "✗ pandoc（brew install pandoc）"
  command -v sips >/dev/null && echo "✓ sips" || echo "✗ sips"
  command -v ffmpeg >/dev/null && echo "✓ ffmpeg" || echo "✗ ffmpeg"
  command -v npx >/dev/null && echo "✓ npx (find-skill: npx skills find)" || echo "✗ npx"
}

# 找出所有場次目錄（含 錄音/*.m4a）
list_sessions() {
  local root="$1"
  find "$root" -type d -name '錄音' -maxdepth 2 2>/dev/null | while read -r rec; do
    if ls "$rec"/*.m4a >/dev/null 2>&1 || ls "$rec"/*.mp3 >/dev/null 2>&1; then
      dirname "$rec"
    fi
  done | sort
}

state_set() { # <場次dir> <stage> <status>
  local sf="$1/.pipeline-state.json"
  [[ -f "$sf" ]] || echo '{}' > "$sf"
  python3 - "$sf" "$2" "$3" <<'PY'
import json,sys
sf,stage,status=sys.argv[1],sys.argv[2],sys.argv[3]
d=json.load(open(sf))
d.setdefault("stages",{})[stage]={"status":status}
json.dump(d,open(sf,"w"),ensure_ascii=False,indent=2)
PY
}

prep() {
  local root="${1:?用法: meeting.sh prep <會議根目錄>}"
  root="$(cd "$root" && pwd)"
  echo "== 會議根目錄：$root =="
  local n=0
  while IFS= read -r sess; do
    [[ -z "$sess" ]] && continue
    n=$((n+1))
    local name; name="$(basename "$sess")"
    local audio; audio="$(ls "$sess"/錄音/*.m4a "$sess"/錄音/*.mp3 2>/dev/null | head -1)"
    echo; echo "── [$n] $name ──"
    echo "  ▶ 轉錄：$audio"
    if bash "$BIN/transcribe.sh" "$audio" "$sess/錄音/transcript.raw.md" zh; then
      state_set "$sess" transcribe done
    else
      state_set "$sess" transcribe failed; echo "  ✗ 轉錄失敗"; fi
    if [[ -d "$sess/照片" ]]; then
      echo "  ▶ 投影片 OCR：$sess/照片"
      if bash "$BIN/ocr-slides.sh" "$sess/照片"; then
        state_set "$sess" slide-ocr done
      else state_set "$sess" slide-ocr failed; echo "  ✗ OCR 失敗"; fi
    fi
  done < <(list_sessions "$root")
  echo
  echo "════════════════════════════════════════════════════"
  echo "✅ 本機前處理完成（$n 場）：transcript.raw.md + 照片/.ocr/*.txt 已就緒。"
  echo
  echo "接著在 Claude Code 執行 AI 步驟（逐字稿精修→總結→驗證→發佈 wiki+docx）："
  echo
  echo "    /meeting-summary \"$root\""
  echo
  echo "或看狀態： meeting.sh status \"$root\""
  echo "════════════════════════════════════════════════════"
}

status() {
  local root="${1:?用法: meeting.sh status <會議根目錄>}"
  root="$(cd "$root" && pwd)"
  while IFS= read -r sess; do
    [[ -z "$sess" ]] && continue
    local name; name="$(basename "$sess")"
    local st="—"
    if [[ -f "$sess/.pipeline-state.json" ]]; then
      st="$(python3 "$BIN/_state.py" "$sess/.pipeline-state.json" 2>/dev/null || echo '—')"
    fi
    printf "• %-40s %s\n" "$name" "$st"
    [[ -s "$sess/錄音/transcript.md" ]] && echo "    ✓ transcript.md"
    [[ -s "$sess/照片/slides.md" ]] && echo "    ✓ slides.md"
    [[ -s "$sess/summary.md" ]] && echo "    ✓ summary.md"
    ls "$sess"/exports/*.docx >/dev/null 2>&1 && echo "    ✓ docx: $(ls "$sess"/exports/*.docx)"
  done < <(list_sessions "$root")
}

cmd="${1:-}"
case "$cmd" in
  doctor) doctor ;;
  status) status "${2:-}" ;;
  prep)   prep "${2:-}" ;;
  "" )    echo "用法: meeting.sh <會議根目錄> | prep <根> | status <根> | doctor"; exit 1 ;;
  * )     prep "$cmd" ;;   # 預設：把第一個參數當會議根目錄
esac

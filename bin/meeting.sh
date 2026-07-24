#!/usr/bin/env bash
# meeting.sh —— 會議總結快速啟動器（meeting-harness 前門）
#
# 用法：
#   meeting.sh <會議根目錄>        研討會/演講：轉錄 + 投影片OCR (可重跑/冪等)
#   meeting.sh notes <會議根目錄>   開會/討論：轉錄 + 講者分離 + 標記會議模式（AI 出「會議紀錄+待辦表格」）
#   meeting.sh prep <會議根目錄>    同第一個（顯式）
#   meeting.sh status <會議根目錄>  顯示每場流水線狀態
#   meeting.sh doctor              檢查工具鏈是否齊備
#   meeting.sh diarize <場次目錄>   對單一場次做講者分離 → 錄音/transcript.speakers.md
#   meeting.sh local <會議根目錄> [notes]  全離線：轉錄+OCR+分離+「本機 LLM 總結」+發佈（內容不出電腦）
#                                          加 notes → 會議紀錄模板（決議/行動項表格）+ 自動講者分離
#   meeting.sh summarize-local <場次> 單場用本機 LLM 產總結
#
# 總結後端：預設 Claude（在 Claude Code /meeting-summary）。地端混合＝MH_LLM=local（總結本機、resolver 可上網）。
#
# 講者分離（選用，預設關閉）：在某場 `錄音/` 放一個空的 `.diarize` 檔，或設環境變數
#   MH_DIARIZE=1，prep 時該場就會多跑分離。需先： brew install uv && bash bin/setup-senko.sh
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
  local sv="${MH_SENKO_VENV:-$HOME/.meeting-harness/senko-venv}"
  if [[ -x "$sv/bin/python" ]] && "$sv/bin/python" -c "import senko" 2>/dev/null; then
    echo "✓ senko (講者分離，選用)"
  else
    echo "◦ senko 未裝（選用；需要講者分離再： brew install uv && bash bin/setup-senko.sh）"
  fi
  # 地端總結（選用）
  local lm; lm="$(python3 -c "import json;print(json.load(open('$HARNESS/config.json'))['llm']['localModel'])" 2>/dev/null || echo qwen3.5:35b-mlx)"
  if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "$(echo "$lm"|cut -d: -f1)"; then
    echo "✓ 地端總結模型 ${lm} (ollama)"
  else
    echo "◦ 地端總結模型未備 (選用; 機密/離線總結再: ollama pull ${lm})"
  fi
}

# 是否對此場次做講者分離：有 .diarize 或 .meeting 標記 或 MH_DIARIZE=1（會議模式一律分離）
diarize_on() { [[ "${MH_DIARIZE:-0}" == "1" || -f "$1/錄音/.diarize" || -f "$1/錄音/.meeting" ]]; }

# 對單一場次做講者分離（需要時自動先補段落時間戳）
run_diarize() {
  local sess="$1"
  echo "  ▶ 講者分離（senko）"
  if [[ ! -s "$sess/錄音/transcript.segments.json" ]]; then
    local audio; audio="$(first_audio "$sess/錄音")"
    echo "    · 補段落時間戳（重轉一次）"
    rm -f "$sess/錄音/transcript.raw.md"
    MH_EMIT_SEGMENTS=1 bash "$BIN/transcribe.sh" "$audio" "$sess/錄音/transcript.raw.md" zh >/dev/null 2>&1
    [[ -s "$sess/錄音/transcript.md" ]] || cp "$sess/錄音/transcript.raw.md" "$sess/錄音/transcript.md" 2>/dev/null
  fi
  bash "$BIN/diarize.sh" "$sess" || { echo "    ✗ 分離失敗（senko 未就緒？）"; return 1; }
  python3 "$BIN/_merge_speakers.py" \
    "$sess/錄音/transcript.segments.json" "$sess/錄音/diarization.json" \
    "$sess/錄音/transcript.speakers.md" "$sess/錄音/speakers.map.json" \
    && { state_set "$sess" diarize done; echo "    ✓ transcript.speakers.md"; } \
    || { state_set "$sess" diarize failed; return 1; }
}

# 找出所有場次目錄（含 錄音/ 的音/視訊檔：m4a/mp3/wav/mov/mp4/m4v）
AUDIO_EXTS=(m4a mp3 wav mov mp4 m4v)
has_audio() { local d="$1" e; for e in "${AUDIO_EXTS[@]}"; do ls "$d"/*."$e" >/dev/null 2>&1 && return 0; done; return 1; }
first_audio() { local d="$1" e f; for e in "${AUDIO_EXTS[@]}"; do f="$(ls "$d"/*."$e" 2>/dev/null | head -1)"; [[ -n "$f" ]] && { echo "$f"; return; }; done; }
list_sessions() {
  local root="$1"
  find "$root" -type d -name '錄音' -maxdepth 2 2>/dev/null | while read -r rec; do
    if has_audio "$rec"; then dirname "$rec"; fi
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
    local audio; audio="$(first_audio "$sess/錄音")"
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
    if diarize_on "$sess"; then run_diarize "$sess"; fi
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

# 會議模式：標記每場為 .meeting（→ 用會議紀錄模板 + 自動講者分離），再跑 prep
notes() {
  local root="${1:?用法: meeting.sh notes <會議根目錄>}"
  root="$(cd "$root" && pwd)"
  echo "== 會議模式（開會/討論導向）：$root =="
  while IFS= read -r sess; do
    [[ -z "$sess" ]] && continue
    touch "$sess/錄音/.meeting"
  done < <(list_sessions "$root")
  prep "$root"
  echo
  echo "※ 已標記為【會議模式】：AI 步驟會用『會議紀錄』模板（結論/決議・行動項表格・未決・風險），並附講者分離。"
}

# 全離線流水線：prep（轉錄+OCR+分離）→ 本機總結 → 發佈，全程無雲端（不跑 resolver）
# 第 2 參數 notes/meeting → 用「會議紀錄」模板（決議/行動項表格）並自動講者分離
local_pipeline() {
  local root="${1:?用法: meeting.sh local <會議根目錄> [notes]}"
  local mode="${2:-}"
  root="$(cd "$root" && pwd)"
  if [[ "$mode" == "notes" || "$mode" == "meeting" ]]; then
    while IFS= read -r sess; do [[ -z "$sess" ]] && continue; touch "$sess/錄音/.meeting"; done < <(list_sessions "$root")
    echo "※ 會議模式：全離線產出【會議紀錄＋行動項表格】並自動講者分離"
  fi
  echo "== 全離線模式（總結走本機 LLM，內容不出電腦）：$root =="
  prep "$root"
  echo; echo "── 本機總結（ollama）──"
  while IFS= read -r sess; do
    [[ -z "$sess" ]] && continue
    if [[ -s "$sess/summary.md" ]]; then echo "  ⏭  已有 summary：$(basename "$sess")"; continue; fi
    bash "$BIN/summarize-local.sh" "$sess" \
      && { state_set "$sess" summarize "done(local)"; python3 "$BIN/publish.py" "$sess" "$HARNESS" "${MH_EVENT:-會議}" >/dev/null 2>&1 && state_set "$sess" publish done; echo "  ✓ $(basename "$sess")"; } \
      || echo "  ✗ 本機總結失敗：$(basename "$sess")"
  done < <(list_sessions "$root")
  echo; echo "✅ 全離線完成。（如要補查證：設定線上後對個別場次跑 resolver）"
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
    [[ -s "$sess/錄音/transcript.speakers.md" ]] && echo "    ✓ transcript.speakers.md（講者分離）"
    ls "$sess"/exports/*.docx >/dev/null 2>&1 && echo "    ✓ docx: $(ls "$sess"/exports/*.docx)"
  done < <(list_sessions "$root")
}

cmd="${1:-}"
case "$cmd" in
  doctor) doctor ;;
  status) status "${2:-}" ;;
  prep)   prep "${2:-}" ;;
  diarize) sess="$(cd "${2:?用法: meeting.sh diarize <場次目錄>}" && pwd)"; run_diarize "$sess" ;;
  notes)  notes "${2:-}" ;;
  summarize-local) sess="$(cd "${2:?用法: meeting.sh summarize-local <場次目錄>}" && pwd)"; shift 2 || true; bash "$BIN/summarize-local.sh" "$sess" "$@" ;;
  local)  local_pipeline "${2:-}" "${3:-}" ;;
  "" )    echo "用法: meeting.sh <根>（研討會） | notes <根>（開會） | local <根>（全離線總結） | status <根> | doctor | diarize <場次> | summarize-local <場次>"; exit 1 ;;
  * )     prep "$cmd" ;;   # 預設：把第一個參數當會議根目錄
esac

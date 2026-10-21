#!/usr/bin/env bash
# transcribe.sh <audio_file> <out_markdown> [language]
# 本機轉錄（Apple Silicon）：zh 預設 Breeze-ASR-25（mlx-whisper），失敗退回 whisper-large-v3，再退回 openai-whisper medium。
# 冪等：若 out_markdown 已存在且非空則跳過。raw 不轉字形；正體版另存 transcript.md（spec §4.6.6）。
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

# ── 模型選擇 ───────────────────────────────────────────────────────────
# zh 場次預設走 Breeze-ASR-25（MediaTek，台灣華語＋中英混雜微調，原生輸出繁體）；
# 其他語言或 Breeze 失敗 → whisper-large-v3；無 mlx → openai-whisper medium。
# 覆寫：MH_ASR_MODEL=<hf repo 或本機路徑>
HARNESS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cfg_model() { # <key>
  python3 - "$HARNESS_ROOT/config.json" "$1" <<'PYCFG' 2>/dev/null
import json,sys
try:
    m=json.load(open(sys.argv[1]))["transcribe"]["models"]
    print(m.get(sys.argv[2],""))
except Exception:
    print("")
PYCFG
}
MODEL_ZH="$(cfg_model zh)";           MODEL_ZH="${MODEL_ZH:-Kenji8000/Breeze-ASR-25-mlx}"
MODEL_DEFAULT="$(cfg_model default)"; MODEL_DEFAULT="${MODEL_DEFAULT:-mlx-community/whisper-large-v3-mlx}"
MODEL_FALLBACK="$(cfg_model fallback)"; MODEL_FALLBACK="${MODEL_FALLBACK:-mlx-community/whisper-large-v3-mlx}"

if [[ -n "${MH_ASR_MODEL:-}" ]]; then
  MODEL="$MH_ASR_MODEL"
elif [[ "$LANG_CODE" == "zh" ]]; then
  MODEL="$MODEL_ZH"
else
  MODEL="$MODEL_DEFAULT"
fi

# 領域術語提示（降低專名誤植；繁中語境）。
# 預設為通用提示；可用環境變數 MH_TRANSCRIBE_HINT 覆寫成你當場的領域術語以提升準確度。
HINT="${MH_TRANSCRIBE_HINT:-以下為一場繁體中文的技術演講/會議，內容含中英文混雜的專有名詞、產品名與技術術語。}"

# 段落時間戳（.json）一律輸出（spec §4.30.4）：講者分離、品質檔、VTT 都要用。
# MH_EMIT_SEGMENTS 已不需要設定；保留這個變數不會出錯，只是不再影響輸出。
OUTFMT="all"

# ── VAD：用錄製器的 levels 只把有聲區間交給 ASR（spec §3.18、§3.19、§4.30.1–§4.30.3）──
# 有聲區間由 _record_lib.py clip 算（成品時間軸、小數 3 位）；沒有 levels（ingest 的音檔）、
# 全場無聲、或 MH_VAD=0 時退回整檔，送 ASR 的參數與 R2 相同。
# 門檻、補、合併間隔可用 MH_VAD_THRESHOLD_DB／MH_VAD_PAD／MH_VAD_MERGE_GAP 覆寫。
# 多音檔（_combine_audio.py 串成 .combined.wav，或 錄音/ 第一層有超過 1 個音檔）時不套 VAD：
# levels 只屬於錄製器那一場，和串接後的時間軸對不上（spec §3.18、R3x §6 第 158 條；疑慮 63 選項 (a)）。
# 音檔的認定與 _combine_audio.py 相同：m4a/mp3/wav/mov/mp4/m4v、隱藏檔不算。
REC_DIR="$(cd "$(dirname "$AUDIO")" && pwd)"
CLIP_TS=""
N_AUDIO=0
for _f in "$REC_DIR"/*.m4a "$REC_DIR"/*.mp3 "$REC_DIR"/*.wav "$REC_DIR"/*.mov "$REC_DIR"/*.mp4 "$REC_DIR"/*.m4v; do
  if [[ -f "$_f" ]]; then N_AUDIO=$((N_AUDIO + 1)); fi
done
if [[ "${MH_VAD:-1}" == "0" ]]; then
  VAD_LINE="> VAD：未套用（MH_VAD=0）"
elif [[ "$(basename "$AUDIO")" == ".combined.wav" || "$N_AUDIO" -gt 1 ]]; then
  VAD_LINE="> VAD：未套用（多音檔）"
else
  CLIP_JSON=""; VAD_REASON=""
  if CLIP_JSON="$(python3 "$HARNESS_ROOT/bin/lib/_record_lib.py" clip "$REC_DIR" 2>"$WORKDIR/clip.err")"; then
    VAD_REASON="$(grep -m1 -E '^(沒有 levels|沒有有聲區間)$' "$WORKDIR/clip.err" || true)"
  else
    echo "[transcribe] WARN: VAD 計算失敗，退回整檔轉錄：$(tail -1 "$WORKDIR/clip.err")" >&2
    CLIP_JSON="null"
  fi
  # 其他警告（例如 MH_VAD_* 不是數字、改用預設）照樣轉給使用者看
  grep -vE '^(沒有 levels|沒有有聲區間)$' "$WORKDIR/clip.err" >&2 || true
  if [[ -n "$CLIP_JSON" && "$CLIP_JSON" != "null" ]]; then
    VAD_INFO="$(python3 - "$HARNESS_ROOT/bin/lib" "$CLIP_JSON" <<'PYVAD' 2>/dev/null
import json, sys
sys.path.insert(0, sys.argv[1])
import _record_lib as rl
clips = json.loads(sys.argv[2])
thr = rl._env_float("MH_VAD_THRESHOLD_DB", rl.VAD_THRESHOLD_DB)
pad = rl._env_float("MH_VAD_PAD", rl.VAD_PAD)
gap = rl._env_float("MH_VAD_MERGE_GAP", rl.VAD_MERGE_GAP)
print(",".join(f"{x:.3f}" for c in clips for x in c))
print(f"> VAD：clip {len(clips)} 段，門檻 {thr:g} dBFS，補 {pad:g} 秒，合併間隔 {float(gap)!r} 秒")
PYVAD
)" || VAD_INFO=""
    CLIP_TS="$(printf '%s\n' "$VAD_INFO" | sed -n 1p)"
    VAD_LINE="$(printf '%s\n' "$VAD_INFO" | sed -n 2p)"
    if [[ -z "$CLIP_TS" || -z "$VAD_LINE" ]]; then
      echo "[transcribe] WARN: clip 結果解析失敗，退回整檔轉錄" >&2
      CLIP_TS=""; VAD_REASON="沒有 levels"
    fi
  fi
  if [[ -z "$CLIP_TS" ]]; then
    VAD_LINE="> VAD：未套用（${VAD_REASON:-沒有 levels}）"
  fi
fi
# 依引擎組 clip 參數（退回整檔時兩者都是空陣列，不帶參數）
MLX_CLIP=(); OAI_CLIP=()
if [[ -n "$CLIP_TS" ]]; then
  MLX_CLIP=(--clip-timestamps "$CLIP_TS")
  OAI_CLIP=(--clip_timestamps "$CLIP_TS")
fi
echo "[transcribe] ${VAD_LINE#> }"

# ── ASR 引擎與退回鏈（spec §4.7）──────────────────────────────────────
# 引擎輸出寫到 $WORKDIR/out/；每次嘗試的完整 stdout／stderr 附加到 $WORKDIR/asr.log。
# 成功判準：引擎回 0 而且 out/ 有非空的 .json（引擎內部丟例外但 CLI 仍回 0、只留 .txt 的情況算失敗）。
# 失敗時清掉這次輸出、stderr 印該引擎輸出的最後 30 行，再走下一個引擎；全部失敗 → 下方回 3。
OUTDIR="$WORKDIR/out"
ASR_LOG="$WORKDIR/asr.log"
mkdir -p "$OUTDIR"
: > "$ASR_LOG"
run_engine() { # <名稱> <指令…>
  local label="$1"; shift
  local att="$WORKDIR/asr.attempt.log" rc=0 why
  rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"
  "$@" > "$att" 2>&1 || rc=$?
  { echo "── [transcribe] ${label}（結束碼 ${rc}）"; cat "$att"; } >> "$ASR_LOG"
  if [[ "$rc" -eq 0 ]] && [[ -n "$(find "$OUTDIR" -name '*.json' -size +0c | head -1)" ]]; then
    tail -8 "$att"
    return 0
  fi
  if [[ "$rc" -eq 0 ]]; then why="結束碼 0 但沒有非空的 .json"; else why="結束碼 $rc"; fi
  echo "[transcribe] $label 失敗（${why}）；引擎輸出最後 30 行：" >&2
  tail -30 "$att" >&2
  rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"
  return 1
}
mlx_cmd() { # <model>
  # --condition-on-previous-text False：關鍵防迴圈（講座有停頓/掌聲易觸發 whisper 重複迴圈）
  # 壓縮比門檻參數已移除（spec §4.29.4）：mlx_whisper CLI 只用單一溫度解碼、不做溫度回退，
  # 那個門檻不會觸發重解碼，帶了也沒有作用；疑似迴圈的段落由下方的重複偵測標記。
  mlx_whisper "$AUDIO" \
    --model "$1" \
    --language "$LANG_CODE" \
    --initial-prompt "$HINT" \
    --condition-on-previous-text False \
    --output-dir "$OUTDIR" \
    --output-format "$OUTFMT" \
    ${MLX_CLIP[@]+"${MLX_CLIP[@]}"} \
    --verbose False
}
oai_cmd() {
  whisper "$AUDIO" --model medium --language "$LANG_CODE" \
    --initial_prompt "$HINT" --condition_on_previous_text False \
    --output_dir "$OUTDIR" --output_format "$OUTFMT" \
    ${OAI_CLIP[@]+"${OAI_CLIP[@]}"}
}
run_oai() {
  USED_MODEL="openai-whisper medium"
  run_engine "openai-whisper medium" oai_cmd || true
}

# 現成段落 JSON（spec §3.7、§4.7.4；meeting.sh prep 在增量轉錄 stitch 成功時給）：
# 不呼叫任何 ASR 引擎，把它當成引擎輸出放進 out/，之後的 raw、段落檔、正體保險栓、品質檔走同一套程式。
SEG_INPUT=0
if [[ -n "${MH_ASR_SEGMENTS_JSON:-}" ]]; then
  STEM="$(basename "${AUDIO%.*}")"
  if [[ -s "$MH_ASR_SEGMENTS_JSON" ]] && python3 - "$MH_ASR_SEGMENTS_JSON" "$OUTDIR/$STEM.json" "$OUTDIR/$STEM.txt" <<'PYSEG' 2>"$WORKDIR/seg.err"
import json, shutil, sys
src, js, txt = sys.argv[1:4]
d = json.load(open(src, encoding="utf-8"))
segs = d.get("segments") if isinstance(d, dict) else None
if not isinstance(segs, list):
    sys.exit("沒有 segments 陣列")
shutil.copyfile(src, js)
with open(txt, "w", encoding="utf-8") as f:
    for s in segs:
        if isinstance(s, dict):
            f.write(str(s.get("text") or "").strip() + "\n")
PYSEG
  then
    SEG_INPUT=1
    USED_MODEL="${MODEL}（增量轉錄）"
    echo "[transcribe] 使用現成段落 JSON（MH_ASR_SEGMENTS_JSON），不呼叫 ASR 引擎；model=$MODEL audio=$AUDIO"
  else
    echo "[transcribe] WARN: MH_ASR_SEGMENTS_JSON 讀不了（$(tail -1 "$WORKDIR/seg.err" 2>/dev/null)），改為整檔轉錄" >&2
    rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"
  fi
fi

if [[ "$SEG_INPUT" -eq 0 ]]; then
  USED_MODEL="$MODEL"
  echo "[transcribe] engine=mlx-whisper model=$MODEL audio=$AUDIO (output=$OUTFMT)"
  if command -v mlx_whisper >/dev/null 2>&1; then
    if ! run_engine "$MODEL" mlx_cmd "$MODEL"; then
      if [[ "$MODEL" != "$MODEL_FALLBACK" ]]; then
        echo "[transcribe] $MODEL 失敗 → 退回 $MODEL_FALLBACK" >&2
        USED_MODEL="$MODEL_FALLBACK"
        if ! run_engine "$MODEL_FALLBACK" mlx_cmd "$MODEL_FALLBACK"; then
          echo "[transcribe] mlx-whisper failed, falling back to openai-whisper" >&2
          run_oai
        fi
      else
        echo "[transcribe] mlx-whisper failed, falling back to openai-whisper" >&2
        run_oai
      fi
    fi
  else
    echo "[transcribe] mlx-whisper 未安裝，使用 openai-whisper medium"
    run_oai
  fi
fi

# 取第一個 .txt，包成 markdown（僅原始逐字稿，標點/校對交由 agent 精修）
RAW="$(find "$OUTDIR" -name '*.txt' | head -1)"
if [[ -z "$RAW" || ! -s "$RAW" ]]; then
  echo "[transcribe] ERROR: no transcript produced" >&2
  exit 3
fi

mkdir -p "$(dirname "$OUT")"
{
  echo "# 逐字稿（原始，未經任何後處理）"
  echo
  echo "> 來源：$(basename "$AUDIO")　語言：${LANG_CODE}　模型：${USED_MODEL}"
  echo "$VAD_LINE"
  echo
  cat "$RAW"
} > "$OUT"

# 段落時間戳 JSON：一律保留（spec §4.30.4；講者分離、品質檔、VTT 用）
SEGOUT="$(dirname "$OUT")/transcript.segments.json"
SEGJSON="$(find "$OUTDIR" -name '*.json' | head -1)"
if [[ -n "$SEGJSON" && -s "$SEGJSON" ]]; then
  cp "$SEGJSON" "$SEGOUT"
  echo "[transcribe] segments -> $SEGOUT"
else
  echo "[transcribe] WARN: 未取得 segments JSON（講者分離將無法對齊、品質檔無從判斷）" >&2
fi

# 正體保險栓（spec §4.6.6，鐵則 1）：transcript.raw.md 是引擎的完整輸出，一律不轉字形、不改寫。
# 正體版另存 transcript.md（只在它不存在時寫，不覆寫人工精修過的版本）：
# Breeze-ASR-25 原生輸出繁體 → 照抄；其他引擎（large-v3 / openai-whisper）才轉字形。
# transcript.segments.json 照舊轉字形（講者分離、VTT 用）。
TWOUT="$(dirname "$OUT")/transcript.md"
NEED_TW=1
case "$USED_MODEL" in *Breeze*|*breeze*) NEED_TW=0 ;; esac
if [[ "$TWOUT" != "$OUT" && ! -e "$TWOUT" ]]; then
  cp "$OUT" "$TWOUT"
  if [[ "$NEED_TW" -eq 1 ]]; then
    python3 "$(dirname "$0")/_to_tw.py" "$TWOUT" 2>/dev/null || \
      echo "[transcribe] WARN: transcript.md 轉正體失敗（內容與 raw 相同）" >&2
  fi
  echo "[transcribe] 正體版 -> $TWOUT"
fi
if [[ "$NEED_TW" -eq 1 && -s "$SEGOUT" ]]; then
  python3 "$(dirname "$0")/_to_tw.py" "$SEGOUT" 2>/dev/null || true
fi

# 品質檔（spec §3.18、§4.30.5）：逐段標出可疑段落，只標記、不動 raw（鐵則 1）。
# 判準在 bin/lib/_transcript_quality.py；讀不到段落檔時寫 []（無從判斷），並已在上方警告。
python3 "$HARNESS_ROOT/bin/lib/_transcript_quality.py" "$SEGOUT" "$(dirname "$OUT")/transcript.quality.json" || \
  echo "[transcribe] WARN: transcript.quality.json 產生失敗" >&2

# 自我驗證：偵測 whisper 重複迴圈（同一行連續重複過多 = 轉錄失敗）
# 注意要算「連續」重複，不是整份檔案的出現次數——會議裡「好」「對」「是」本來就會出現幾十次，
# 用總次數判會一直誤報（實測 0908 某場會議：「好」全檔 35 次，但最長連續只有 2 次，是正常對話）。
MAXREP=$(python3 - "$RAW" <<'PYREP'
import sys
lines = [l.strip() for l in open(sys.argv[1], encoding="utf-8")]
best, cur, txt = 1, 1, ""
for a, b in zip(lines, lines[1:]):
    cur = cur + 1 if (a == b and a) else 1
    if cur > best:
        best, txt = cur, a
print(f"{best}\t{txt[:30]}")
PYREP
)
MAXREP_TXT="${MAXREP#*	}"; MAXREP="${MAXREP%%	*}"
MAXREP=${MAXREP:-1}
TOTAL=$(grep -cve '^[[:space:]]*$' "$RAW" || true)
TOTAL=${TOTAL:-1}
if [[ "${MAXREP:-0}" -ge 10 ]]; then
  echo "[transcribe] ⚠️  重複迴圈：同一行連續重複 ${MAXREP} 次（「${MAXREP_TXT}」，共 ${TOTAL} 行非空）" >&2
  echo "[transcribe] 該段多半是雜訊造成，raw 保留原樣；總結時請標為（聽不清）不要採信。" >&2
  echo "REPETITION_LOOP_DETECTED consecutive=${MAXREP} text=${MAXREP_TXT} total=${TOTAL}" > "$OUT.QUALITY_WARNING"
fi

# 行內重複迴圈偵測：上面那段只看「整行重複」，但迴圈也常發生在同一行之內
# （例：「我們所說的」連續 30 幾次）。這裡只警告、不動 raw，供人工覆核。
INLINE=$(python3 - "$RAW" <<'PYREP'
import sys
from collections import Counter
worst, where = 1, ""
for line in open(sys.argv[1], encoding="utf-8"):
    t = line.strip()
    if len(t) < 16:
        continue
    c = Counter(t[i:i+4] for i in range(len(t) - 3))
    n, g = c.most_common(1)[0][1], c.most_common(1)[0][0]
    if n > worst:
        worst, where = n, f"{g}×{n}：{t[:40]}"
print(f"{worst}	{where}")
PYREP
)
INLINE_N="${INLINE%%	*}"; INLINE_TXT="${INLINE#*	}"
if [[ "${INLINE_N:-1}" -ge 8 ]]; then
  echo "[transcribe] ⚠️  行內重複迴圈：同一段裡有 4 字片語重覆 ${INLINE_N} 次（${INLINE_TXT}）" >&2
  echo "[transcribe] 該段多半是雜訊/交談重疊造成，raw 保留原樣；總結時請標為（聽不清）不要採信。" >&2
  echo "INLINE_REPETITION_LOOP n=${INLINE_N} sample=${INLINE_TXT}" >> "$OUT.QUALITY_WARNING"
fi

# 產物健檢：只有標頭沒有內容 → 視為失敗（否則下游會拿空稿繼續跑）
BODY=$(grep -cve '^[[:space:]]*$' "$RAW" || true)
if [[ "${BODY:-0}" -eq 0 ]]; then
  echo "[transcribe] ERROR: 轉錄結果是空的（${USED_MODEL}）。已保留 ${OUT} 供檢查。" >&2
  exit 4
fi

echo "[transcribe] DONE -> $OUT ($(wc -l < "$OUT" | tr -d ' ') lines; max-line-repeat=$MAXREP)"

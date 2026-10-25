#!/usr/bin/env bash
# meeting.sh —— 會議總結快速啟動器（meeting-harness 前門）
#
# 用法：  meeting.sh help      （完整指令說明）
#        meeting.sh <會議根目錄>  本機前處理（轉錄＋投影片OCR＋講者分離，可重跑/冪等）
#
# 完整指令、會議型態、環境變數一律以 `meeting.sh help` 為準（本檔 usage() 函式）。
# 相容性：prep / notes / status / doctor / diarize / summarize-local / local 的
#         用法與語意都沒有變，舊腳本與舊標記檔（.meeting / .diarize）照舊可用。
#
# 總結後端：預設 Claude（在 Claude Code /meeting-summary）。地端混合＝MH_LLM=local（總結本機、resolver 可上網）。
#
# 講者分離（預設開啟，六種型態都跑）：config.json 的 diarize.enabled=false 可整個關掉；
#   關掉時仍可用 MH_DIARIZE=1 單次強制開。需先： brew install uv && bash bin/setup-diarize.sh
#
# 場次 = 會議根目錄下、含 `錄音/*.m4a` 的子資料夾。
# AI 步驟（總結/驗證/發佈 wiki+docx）請在 Claude Code 執行： /meeting-summary <會議根目錄>
# 注意：批次執行不用 -e，讓單一場次失敗不中斷其餘場次（改以顯式 if 檢查）。
set -uo pipefail

HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$HARNESS/bin"

usage() {
  cat <<'USAGE'
meeting — 會議錄音/錄影 → 逐字稿 → 會議紀錄（本機、離線；AI 總結另在 Claude Code 跑）

用法
  meeting <會議根目錄>                本機前處理：轉錄 + 投影片OCR + 講者分離（可重跑、冪等）
  meeting <型態> <會議根目錄>          指定會議型態後做前處理（型態會記住，下次不用再指定）
  meeting help                        顯示這份說明

會議型態（決定講者分離參數與總結模板）
  seminar     研討會／演講（1 對多＋Q&A）      internal    內部會議（多對多）
  client      客戶會議（多對多、對外）          1on1        一對一
  workshop    工作坊（多組討論）                interview   訪談／面談
  未指定型態＝沿用該場既有設定；從未設過則為 seminar。

其他指令
  meeting ingest <平坦資料夾> [--split] [--type <型態>] [--gap <分鐘>] [--dry-run]
                                      錄影/錄音/截圖全丟在一起時，依時間戳自動分成場次
  meeting type <型態> <根或場次目錄>    只設定型態，不跑前處理
  meeting prep <會議根目錄>            同「meeting <會議根目錄>」（顯式寫法）
  meeting status <會議根目錄>          顯示每場的流水線狀態與產物
  meeting diarize <場次目錄>           只對單一場次做講者分離
  meeting render <場次目錄>            由 meeting.record.json 重新產出 summary.md /
                                      actions.csv / actions.ics / 錄音/transcript.vtt
  meeting local <會議根目錄> [型態]     全離線：前處理＋本機 LLM 總結＋發佈（內容不出電腦）
  meeting summarize-local <場次目錄>   只對單一場次用本機 LLM 產總結
  meeting voiceprint add <場次> <SPEAKER_xx> <姓名>
                                      把「你確認過」的講者存進聲紋庫，之後每場自動認出同一個人
  meeting voiceprint list | remove <姓名>
                                      看／刪聲紋庫（存在 vault/voiceprints/，本機、不進版控）
  meeting search <會議根目錄> <關鍵字>  搜各場次的 summary／逐字稿／meeting.record.json（大小寫不分、照字面）
  meeting sync [off|reported|calibrated]
                                      看／設定系統聲音的延遲補償模式（預設 off；下一次收尾起生效）
  meeting doctor                      檢查工具鏈（ASR 模型、講者分離環境與模型授權）
  meeting version                     顯示版本（git commit）

錄製（meeting record；完整說明：meeting record help）
  meeting record [<根>]               開錄：問根目錄、場次、型態、出席者、要錄的視窗，檢查通過才錄
  meeting record windows              列出可錄的視窗（★＝會議視窗）
  meeting record preflight            只跑開錄前檢查（13 項），不錄
  meeting record stop                 停止錄製並收尾成 影片/*.mov 與 錄音/*.wav
  meeting record status               看錄製狀態（上次異常中止會提示 finish）
  meeting record finish <場次>        把已落盤的段落收尾（當機救援；可重跑）
  meeting record pause                暫停整段錄製（暫停的部分不進成品）
  meeting record resume               繼續錄製
  meeting record mute                 只靜音麥克風（系統聲音照錄）
  meeting record unmute               取消麥克風靜音
  meeting record mark                 在目前位置加一個標記（收尾時寫成 錄音/markers.json）
  meeting record help                 印出寫法、旗標與結束碼
  層旗標：--recorder（明確要錄製，略過 ./record 撞名檢查）、--yes（宣告沒有人可問）；record 之後任何位置都可以
  結束碼：0 成功、2 參數或前提不符、3 找不到目標、4 開錄前檢查失敗或權限、5 錄製或收尾出錯（段落保留）

資料擺法
  <會議根目錄>/<場次名>/錄音/*.m4a|mp3|wav|mov|mp4    ← 必要（同場多檔會自動串接）
                      /錄音/meeting.json             ← 選配：型態、出席名單
                      /錄音/轉文字.txt                ← 選配：現場粗轉錄（校對專名用）
                      /照片/*.HEIC|png|jpg            ← 選配：投影片／截圖
  場次＝會議根目錄下、`錄音/` 裡有音訊或影片檔的子資料夾。

兩步流程
  1) meeting <型態> "<會議根目錄>"        ← 本機、離線
  2) 在 Claude Code： /meeting-summary "<會議根目錄>"   ← 總結／驗證／發佈 wiki+docx

常用環境變數
  MH_ASR_MODEL          覆寫轉錄模型（預設 zh 用 Breeze-ASR-25，見 config.json）
  MH_TRANSCRIBE_HINT    當場領域術語提示，降低專名誤植
  MH_LLM=local          總結改走本機 LLM（逐字稿不出電腦）
  MH_MIN_SPEAKER_SEC    把總時長低於 N 秒的講者併入最近的主要講者（預設依型態）
  MH_MIN_OVERLAP_RATIO  逐字段與講者段重疊低於此比例就標 SPEAKER_?（預設 0.3）
  MH_DIARIZE=1          強制開啟講者分離
  MH_DIARIZE_DEVICE     講者分離裝置：auto（預設，有 MPS 就用）/ mps / cpu
  HF_TOKEN              HuggingFace token（也可放 ~/.meeting-harness/hf-token）
  MH_RECORDER_APP       錄製器 app 路徑（預設 ~/Applications/MeetingRecorder.app）
  MH_RECORD_HOME        錄製狀態檔目錄（預設 ~/.meeting-harness）
  MH_RECORD_OPEN        啟動錄製器的指令（預設 open；測試用替身）
  MH_FFMPEG             收尾用的 ffmpeg（預設 PATH 上的 ffmpeg）
  MH_RECORD_EST_MINUTES 估算磁碟需求的分鐘數（預設 120）

講者識別
  分離用 pyannote community-1，跑 Apple Silicon GPU（MPS）。首次需到 HuggingFace 按一次同意：
  https://huggingface.co/pyannote/speaker-diarization-community-1
  認人的順序：聲紋庫比對 → speaker-id-agent 依稱呼線索推定 → 都不確定就維持 SPEAKER_0x 並列入存疑。
  聲紋屬生物特徵資料：只存本機 vault/voiceprints/、只由你確認後建檔、可隨時 remove。

相容性：舊寫法 `meeting notes <根>`（＝internal）與舊標記檔 .meeting / .diarize 都仍可用。
USAGE
}

# 參數檢查：把「打錯指令」和「路徑不存在」講清楚，不要丟 cd 的原始錯誤給使用者
# 注意：本函式在 $( ) 裡執行，exit 只結束子 shell，呼叫端一定要接 `|| exit $?`
need_dir() { # <路徑> <這個指令要什麼>
  local d="${1:-}" what="${2:-目錄}"
  if [[ -z "$d" ]]; then
    echo "✗ 少了${what}。用法看： meeting.sh help" >&2; exit 2
  fi
  if [[ ! -d "$d" ]]; then
    echo "✗ 找不到${what}：$d" >&2
    echo "  （路徑有空白或中文時記得加引號）" >&2; exit 2
  fi
  (cd "$d" && pwd)
}

doctor() {
  echo "== meeting-harness doctor =="
  python3 -c "import mlx_whisper" 2>/dev/null && echo "✓ mlx-whisper" || echo "✗ mlx-whisper（pip install mlx-whisper）"
  python3 -c "from ocrmac import ocrmac" 2>/dev/null && echo "✓ ocrmac (Apple Vision)" || echo "✗ ocrmac（pip install ocrmac）"
  command -v pandoc >/dev/null && echo "✓ pandoc" || echo "✗ pandoc（brew install pandoc）"
  command -v sips >/dev/null && echo "✓ sips" || echo "✗ sips"
  command -v ffmpeg >/dev/null && echo "✓ ffmpeg" || echo "✗ ffmpeg"
  command -v npx >/dev/null && echo "✓ npx (find-skill: npx skills find)" || echo "✗ npx"
  # zh 主力 ASR 模型（Breeze-ASR-25）是否已在 HF 快取（首跑需下載約 3GB）
  local am; am="$(python3 -c "import json;print(json.load(open('$HARNESS/config.json'))['transcribe']['models']['zh'])" 2>/dev/null || echo "Kenji8000/Breeze-ASR-25-mlx")"
  local cachedir="$HOME/.cache/huggingface/hub/models--${am//\//--}"
  if [[ -d "$cachedir" ]]; then
    echo "✓ ASR 模型 ${am}（已快取 $(du -sh "$cachedir" 2>/dev/null | cut -f1)）"
  else
    echo "◦ ASR 模型 ${am} 未下載（首次轉錄會自動抓，約 3GB）"
  fi
  # 講者分離：pyannote.audio（跑 Apple Silicon GPU / MPS，不碰 ANE）
  local dv="${MH_DIARIZE_VENV:-$HOME/.meeting-harness/diarize-venv}"
  if [[ -x "$dv/bin/python" ]] && "$dv/bin/python" -c "import pyannote.audio" 2>/dev/null; then
    local dev; dev="$("$dv/bin/python" -c "import torch;print('MPS' if torch.backends.mps.is_available() else 'CPU')" 2>/dev/null)"
    echo "✓ pyannote.audio 講者分離（裝置：${dev:-?}）"
    # gated 模型是否已授權：只打 API，不下載
    local tok; tok="$(python3 - <<'PYTOK' 2>/dev/null
import os
for k in ("HF_TOKEN","HUGGING_FACE_HUB_TOKEN","HUGGINGFACE_TOKEN"):
    if os.environ.get(k): print(os.environ[k]); raise SystemExit
for p in ("~/.meeting-harness/hf-token","~/.cache/huggingface/token","~/.huggingface/token"):
    fp=os.path.expanduser(p)
    if os.path.isfile(fp):
        t=open(fp).read().strip()
        if t: print(t); raise SystemExit
PYTOK
)"
    if [[ -z "$tok" ]]; then
      echo "  ⚠ 找不到 HuggingFace token → hf auth login（或把 read token 放 ~/.meeting-harness/hf-token）"
    else
      local code; code="$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $tok" \
        "https://huggingface.co/api/models/pyannote/speaker-diarization-community-1/auth-check")"
      if [[ "$code" == "200" ]]; then
        echo "  ✓ 模型授權 OK（pyannote/speaker-diarization-community-1）"
      else
        echo "  ⚠ 模型尚未授權（HTTP ${code}）→ 開 https://huggingface.co/pyannote/speaker-diarization-community-1"
        echo "     按 Agree and access repository（免費、按一下就通過）"
      fi
    fi
  else
    echo "◦ 講者分離未裝（需要時： brew install uv && bash bin/setup-diarize.sh）"
  fi
  # 地端總結（選用）
  local lm; lm="$(python3 -c "import json;print(json.load(open('$HARNESS/config.json'))['llm']['localModel'])" 2>/dev/null || echo qwen3.5:35b-mlx)"
  if curl -s http://localhost:11434/api/tags 2>/dev/null | grep -q "$(echo "$lm"|cut -d: -f1)"; then
    echo "✓ 地端總結模型 ${lm} (ollama)"
  else
    echo "◦ 地端總結模型未備 (選用; 機密/離線總結再: ollama pull ${lm})"
  fi
  # 錄製器（選用；只用 ✓／◦／⚠，不出現 ✗——沒有 app 也要全綠。TCC 授權要啟動 app 才查得到，屬 preflight）
  local app="${MH_RECORDER_APP:-$HOME/Applications/MeetingRecorder.app}"
  if [[ -d "${app}" ]]; then
    echo "✓ 錄製器 MeetingRecorder.app（${app}；權限與訊號看 meeting record preflight）"
  else
    echo "◦ 錄製器 MeetingRecorder.app 未建置（選用；要錄會議時： bash tools/MeetingRecorder/build.sh）"
  fi
  local est_min="${MH_RECORD_EST_MINUTES:-120}" need
  need="$(python3 "$BIN/_record_estimate.py" --minutes "${est_min}" --human 2>/dev/null | tail -1)"
  echo "  ◦ 錄製 ${est_min} 分鐘的磁碟峰值需求：${need:-（無法估算）}（MH_RECORD_EST_MINUTES 可改）"
  echo "◦ 會議分頁標記（選用）：Chrome 會議分頁的 ★ 要允許 MeetingRecorder 送 Apple Events 控制 Chrome；不允許也能錄。doctor 查不到授權狀態，實際狀態看 meeting record preflight"
  return 0
}

# record 子指令（spec §2.3、§2.4.2、design.md §8.1）：
# 先依層旗標判斷 ./record 撞名，再把 record 之後任何位置的 --recorder、--yes 拿掉、其餘參數原序交給 record.sh。
# 未知選項的判斷與錄製參數的解析都在 record.sh（meeting.sh 不自己解析錄製參數）。
record_cmd() {
  local recorder=0 yes=0 a
  local rest=()
  for a in "$@"; do
    case "$a" in
      --recorder) recorder=1 ;;
      --yes)      yes=1 ;;
      *)          rest+=("$a") ;;
    esac
  done
  if [[ "${recorder}" -eq 0 && -d record ]]; then
    if [[ "${yes}" -eq 0 && -t 0 && -t 2 ]]; then
      local ans=""
      printf '%s\n' "目前目錄下有名為 record 的資料夾。要：" "  1) 開始錄製（meeting record）" "  2) 把 ./record 當會議根目錄跑前處理" >&2
      printf '%s' "請選 1 或 2：" >&2
      IFS= read -r ans || ans=""
      case "${ans}" in
        1) ;;
        2) prep record; return $? ;;
        *) echo "✗ 沒有選擇，什麼都沒做。" >&2; return 2 ;;
      esac
    else
      echo "✗ 目前目錄下有名為 record 的資料夾，沒有人可問要做哪一件事，所以什麼都沒做。請改用明確寫法：" >&2
      echo "  要錄製：    meeting.sh record --recorder …（例 meeting.sh record --recorder windows）" >&2
      echo "  要前處理：  meeting.sh prep ./record" >&2
      return 2
    fi
  fi
  bash "$BIN/record.sh" ${rest[@]+"${rest[@]}"}
}

# 載入該場次的會議型態 profile（型態→分離參數／總結模板／語言／LLM 後端）
# 匯出 MH_TYPE / MH_TEMPLATE / MH_DO_DIARIZE / MH_NUM_SPEAKERS / MH_MIN_SPEAKERS /
#      MH_MAX_SPEAKERS / MH_MIN_SPEAKER_SEC / MH_LANG / MH_LLM_BACKEND
load_profile() {
  local sess="$1" out
  out="$(python3 "$BIN/_profile.py" "$sess" 2>/dev/null)" || return 1
  eval "$out"
  export MH_NUM_SPEAKERS MH_MIN_SPEAKERS MH_MAX_SPEAKERS MH_MIN_SPEAKER_SEC
}

# 是否對此場次做講者分離：由 profile 決定（六種型態預設都開；舊 .diarize/.meeting 標記仍相容）
diarize_on() { [[ "${MH_DO_DIARIZE:-0}" == "1" ]]; }

# 對單一場次做講者分離。第 2 參數給了＝prep 已在背景跑完 diarize.sh（spec §4.8.1），只收結果、merge、annotate。
# 缺 transcript.segments.json 時明確報錯、不重轉（raw 不改，鐵則 1；meeting-speed spec §4.8.4、§6 第 13、20 條）。
run_diarize() { # <場次dir> [背景 diarize.sh 的結束碼]
  local sess="$1" pre_rc="${2:-}"
  [[ -z "${MH_TYPE:-}" ]] && load_profile "$sess"
  if [[ -z "$pre_rc" ]]; then
    echo "  ▶ 講者分離（pyannote；講者數=${MH_NUM_SPEAKERS:-${MH_MIN_SPEAKERS:-?}–${MH_MAX_SPEAKERS:-?}}）"
    require_segments "$sess" || return 1
    bash "$BIN/diarize.sh" "$sess"; pre_rc=$?
  fi
  if [[ "$pre_rc" -ne 0 ]]; then
    echo "    ✗ 分離失敗（見上面訊息）"; state_set "$sess" diarize failed; return 1
  fi
  require_segments "$sess" || return 1
  python3 "$BIN/_merge_speakers.py" \
    "$sess/錄音/transcript.segments.json" "$sess/錄音/diarization.json" \
    "$sess/錄音/transcript.speakers.md" "$sess/錄音/speakers.map.json" \
    || { state_set "$sess" diarize failed; return 1; }
  # 後處理（spec §4.31.10）：在 speakers.md 插註記與「（聽不清）」；沒有事件、沒有品質檔時不改檔。
  # 失敗只警告，speakers.md 維持 _merge_speakers.py 的原樣。
  python3 "$BIN/_render.py" "$sess" --annotate-speakers >/dev/null \
    || echo "    ⚠ speakers.md 註記後處理失敗（維持原樣）"
  state_set "$sess" diarize done; echo "    ✓ transcript.speakers.md"
}

# 分離要的段落時間戳不在就報錯、記 diarize: failed、回 1（不呼叫 ASR）
require_segments() { # <場次dir>
  [[ -s "$1/錄音/transcript.segments.json" ]] && return 0
  echo "    ✗ 缺 transcript.segments.json，先跑 meeting.sh prep <場次>（或 transcribe）再分離" >&2
  state_set "$1" diarize failed
  return 1
}

# 找出所有場次目錄（含 錄音/ 的音/視訊檔：m4a/mp3/wav/mov/mp4/m4v）
AUDIO_EXTS=(m4a mp3 wav mov mp4 m4v)
has_audio() { local d="$1" e; for e in "${AUDIO_EXTS[@]}"; do ls "$d"/*."$e" >/dev/null 2>&1 && return 0; done; return 1; }
first_audio() { local d="$1" e f; for e in "${AUDIO_EXTS[@]}"; do f="$(ls "$d"/*."$e" 2>/dev/null | head -1)"; [[ -n "$f" ]] && { echo "$f"; return; }; done; }
# 場次＝底下有「錄音/」且裡面有音訊或影片檔的資料夾。
# maxdepth 4：允許 <根>/<會議名>/<場次>/錄音 這種多一層的擺法
# （例：20260917/站會/站會場次/錄音——meeting ingest 對子資料夾跑就會長這樣）。
list_sessions() {
  local root="$1"
  find "$root" -maxdepth 4 -type d -name '錄音' 2>/dev/null | while read -r rec; do
    if has_audio "$rec"; then dirname "$rec"; fi
  done | sort
}

# 寫 .pipeline-state.json 一律經 _record_lib.update_pipeline_state（flock＋讀後合併＋原子寫入；meeting-speed spec §4.9）。
# prep 處理一場期間 PREP_RUN_ID 有值，寫的 stage 都帶同一個 runId（spec §4.8.2）；等鎖逾時只警告、照常繼續。
PREP_RUN_ID=""
state_set() { # <場次dir> <stage> <status>
  python3 "$BIN/lib/_record_lib.py" state-set "$1" "$2" "$3" ${PREP_RUN_ID:+--run-id "$PREP_RUN_ID"} || true
}

new_run_id() {
  uuidgen 2>/dev/null || python3 -c 'import uuid; print(str(uuid.uuid4()).upper())'
}

# 轉錄一場（spec §4.11.8）：有 bin/lib/_asr_worker.py 且 stitch 回 0 時，以 MH_ASR_SEGMENTS_JSON 交給 transcribe.sh，
# 不呼叫 ASR 引擎；stitch 回 3（不可用）或 worker 不存在時整檔轉錄。回 transcribe.sh 的結束碼。
transcribe_session() { # <場次dir> <音源> <MH_EMIT_SEGMENTS>
  local sess="$1" audio="$2" seg="$3" worker="$BIN/lib/_asr_worker.py" st rc
  if [[ -f "$worker" ]]; then
    st="$(mktemp -d)"
    # MH_LANG 是 load_profile 以 eval 設的（沒 export）：明確交給 stitch，與下面傳給 transcribe.sh 的語言相同
    if MH_LANG="${MH_LANG:-zh}" python3 "$worker" stitch "$sess" "$st/stitched.json" && [[ -s "$st/stitched.json" ]]; then
      echo "  · 用錄製中已完成的增量轉錄（不再整檔轉錄）"
      MH_ASR_SEGMENTS_JSON="$st/stitched.json" MH_EMIT_SEGMENTS=$seg \
        bash "$BIN/transcribe.sh" "$audio" "$sess/錄音/transcript.raw.md" "${MH_LANG:-zh}"; rc=$?
      rm -rf "$st"; return "$rc"
    fi
    rm -rf "$st"
    echo "  · 沒有可用的增量轉錄結果，整檔轉錄"
  fi
  MH_EMIT_SEGMENTS=$seg bash "$BIN/transcribe.sh" "$audio" "$sess/錄音/transcript.raw.md" "${MH_LANG:-zh}"
}

prep() {
  local root; root="$(need_dir "${1:-}" "會議根目錄")" || exit $?
  echo "== 會議根目錄：$root =="
  local n=0
  while IFS= read -r sess <&3; do
    [[ -z "$sess" ]] && continue
    n=$((n+1))
    local name; name="$(basename "$sess")"
    load_profile "$sess"
    local audio; audio="$(python3 "$BIN/_combine_audio.py" "$sess/錄音")"
    echo; echo "── [$n] $name ──"
    echo "  · 型態：${MH_TYPE:-seminar}（模板 ${MH_TEMPLATE:-seminar}；講者數=${MH_NUM_SPEAKERS:-${MH_MIN_SPEAKERS:-?}–${MH_MAX_SPEAKERS:-?}}）"
    # 本場這次 prep 的 runId 與應跑的 stage（spec §3.5、§4.8.2）：MH_PREP_RUN_ID 由錄製器給，沒給就自己產
    PREP_RUN_ID="${MH_PREP_RUN_ID:-$(new_run_id)}"
    local seg=0; diarize_on "$sess" && seg=1
    local expect=(transcribe); [[ -d "$sess/照片" ]] && expect+=(slide-ocr); [[ "$seg" -eq 1 ]] && expect+=(diarize)
    python3 "$BIN/lib/_record_lib.py" state-begin "$sess" "$PREP_RUN_ID" "${expect[@]}" || true
    # 要分離時在轉錄開始前於背景啟動 diarize.sh（spec §4.8.1）；輸出先收進暫存檔，wait 之後再印，不與轉錄交錯
    local dpid="" dlog=""
    if [[ "$seg" -eq 1 ]]; then
      echo "  ▶ 講者分離（pyannote，背景與轉錄並行；講者數=${MH_NUM_SPEAKERS:-${MH_MIN_SPEAKERS:-?}–${MH_MAX_SPEAKERS:-?}}）"
      dlog="$(mktemp)"
      bash "$BIN/diarize.sh" "$sess" >"$dlog" 2>&1 &
      dpid=$!
    fi
    echo "  ▶ 轉錄：$audio"
    # 若本場要做講者分離，轉錄時就一併輸出段落時間戳（避免之後重轉一次）
    if transcribe_session "$sess" "$audio" "$seg" \
       && [[ "$(grep -cve '^[[:space:]]*$' -e '^#' -e '^>' "$sess/錄音/transcript.raw.md" 2>/dev/null || echo 0)" -gt 0 ]]; then
      state_set "$sess" transcribe done
    else
      state_set "$sess" transcribe failed; echo "  ✗ 轉錄失敗（逐字稿為空或指令失敗）"; fi
    if [[ -d "$sess/照片" ]]; then
      echo "  ▶ 投影片 OCR：$sess/照片"
      if bash "$BIN/ocr-slides.sh" "$sess/照片"; then
        state_set "$sess" slide-ocr done
      else state_set "$sess" slide-ocr failed; echo "  ✗ OCR 失敗"; fi
    fi
    if [[ -n "$dpid" ]]; then
      local drc=0; wait "$dpid" || drc=$?
      echo "  ▶ 講者分離結果："; cat "$dlog"; rm -f "$dlog"
      run_diarize "$sess" "$drc"
    fi
    PREP_RUN_ID=""
  done 3< <(list_sessions "$root")
  if [[ "$n" -eq 0 ]]; then
    echo
    echo "✗ 這個目錄下找不到任何場次。" >&2
    echo "  場次＝根目錄下、「錄音/」裡有音訊或影片檔（m4a/mp3/wav/mov/mp4/m4v）的子資料夾。" >&2
    echo "  如果檔案都還平放在同一層，先跑： meeting.sh ingest \"$root\"" >&2
    exit 3
  fi
  echo
  # 結尾摘要（spec §4.8.10）：讀各場 .pipeline-state.json，列出這次 prep（prep.runId）失敗的 stage；
  # 有失敗時不印 ✅、改印 ⚠。結束碼不變（§4.8.5，失敗仍回 0）。
  local fails; fails="$(list_sessions "$root" | python3 -c '
import json, os, sys
for sess in (ln.rstrip("\n") for ln in sys.stdin):
    if not sess:
        continue
    try:
        with open(os.path.join(sess, ".pipeline-state.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        continue
    if not isinstance(st, dict):
        continue
    prep = st.get("prep") if isinstance(st.get("prep"), dict) else {}
    rid = prep.get("runId")
    stages = st.get("stages") if isinstance(st.get("stages"), dict) else {}
    bad = [k for k, v in stages.items()
           if isinstance(v, dict) and v.get("status") == "failed" and (not rid or v.get("runId") in (None, rid))]
    if bad:
        print(os.path.basename(sess) + "：" + "、".join(bad))
' 2>/dev/null || true)"
  echo "════════════════════════════════════════════════════"
  if [[ -n "$fails" ]]; then
    echo "⚠ 本機前處理完成，但有步驟失敗："
    printf '%s\n' "$fails" | sed 's/^/    /'
    echo "  詳見各場次的 .pipeline-state.json（stages 的 status）與上面的訊息。"
  else
    echo "✅ 本機前處理完成（$n 場）：transcript.raw.md + 照片/.ocr/*.txt 已就緒。"
  fi
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
  local root; root="$(need_dir "${1:-}" "會議根目錄")" || exit $?
  echo "== 會議模式（開會/討論導向）：$root =="
  while IFS= read -r sess <&3; do
    [[ -z "$sess" ]] && continue
    python3 "$BIN/_profile.py" "$sess" --set-type internal >/dev/null
    touch "$sess/錄音/.meeting"   # 舊標記，維持相容
  done 3< <(list_sessions "$root")
  prep "$root"
  echo
  echo "※ 已標記為【會議模式】：AI 步驟會用『會議紀錄』模板（結論/決議・行動項表格・未決・風險），並附講者分離。"
}

# 全離線流水線：prep（轉錄+OCR+分離）→ 本機總結 → 發佈，全程無雲端（不跑 resolver）
# 第 2 參數 notes/meeting → 用「會議紀錄」模板（決議/行動項表格）並自動講者分離
local_pipeline() {
  local root; root="$(need_dir "${1:-}" "會議根目錄")" || exit $?
  local mode="${2:-}"
  case "$mode" in
    notes|meeting)                                  # 舊寫法，等同 internal
      while IFS= read -r sess <&3; do [[ -z "$sess" ]] && continue
        python3 "$BIN/_profile.py" "$sess" --set-type internal >/dev/null
        touch "$sess/錄音/.meeting"
      done 3< <(list_sessions "$root")
      echo "※ 會議模式：全離線產出【會議紀錄＋行動項表格】並自動講者分離" ;;
    seminar|internal|client|1on1|workshop|interview)
      set_type "$mode" "$root" >/dev/null
      echo "※ 會議型態【${mode}】：全離線產出對應模板的紀錄並自動講者分離" ;;
    "") : ;;
    *)  echo "✗ 未知的型態：${mode}（可用：seminar internal client 1on1 workshop interview，或舊寫法 notes）" >&2; exit 2 ;;
  esac
  echo "== 全離線模式（總結走本機 LLM，內容不出電腦）：$root =="
  prep "$root"
  # 若根目錄有 agenda.md，總結時餵入以校正講者/標題
  local agenda_arg=(); [[ -f "$root/agenda.md" ]] && agenda_arg=(--agenda "$root/agenda.md")
  echo; echo "── 本機總結（ollama）──"
  while IFS= read -r sess <&3; do
    [[ -z "$sess" ]] && continue
    if [[ -s "$sess/summary.md" ]]; then echo "  ⏭  已有 summary：$(basename "$sess")"; continue; fi
    bash "$BIN/summarize-local.sh" "$sess" ${agenda_arg[@]+"${agenda_arg[@]}"} \
      && { state_set "$sess" summarize "done(local)"; python3 "$BIN/publish.py" "$sess" "$HARNESS" "${MH_EVENT:-會議}" >/dev/null 2>&1 && state_set "$sess" publish done; echo "  ✓ $(basename "$sess")"; } \
      || echo "  ✗ 本機總結失敗：$(basename "$sess")"
  done 3< <(list_sessions "$root")
  echo; echo "✅ 全離線完成。（如要補查證：設定線上後對個別場次跑 resolver）"
}

status() {
  local root; root="$(need_dir "${1:-}" "會議根目錄")" || exit $?
  while IFS= read -r sess <&3; do
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
  done 3< <(list_sessions "$root")
  return 0   # 最後一個 ls 沒找到 docx 時會讓整個 status 回非 0，對呼叫端沒意義
}

# 設定會議型態：可指向會議根目錄（套用到底下每一場）或單一場次目錄
set_type() { # <型態> <根或場次>
  local t="$1" target; target="$(need_dir "${2:-}" "會議根目錄或場次目錄")" || exit $?
  local n=0
  if [[ -d "$target/錄音" ]] && has_audio "$target/錄音"; then
    python3 "$BIN/_profile.py" "$target" --set-type "$t"; n=1
  else
    while IFS= read -r sess <&3; do
      [[ -z "$sess" ]] && continue
      python3 "$BIN/_profile.py" "$sess" --set-type "$t"; n=$((n+1))
    done 3< <(list_sessions "$target")
  fi
  if [[ "$n" -eq 0 ]]; then
    echo "✗ ${target} 底下找不到任何場次（場次＝「錄音/」裡有音訊或影片檔的子資料夾）" >&2
    echo "  檔案還沒分場的話先跑： meeting.sh ingest \"$target\"" >&2
    exit 3
  fi
  echo "$target"
}

# 指定會議型態後跑 prep：meeting.sh <型態> <根>
typed_prep() {
  local t="$1" root; root="$(set_type "$t" "${2:-}" | tail -1)" || exit $?
  echo "== 會議型態【${t}】：${root} =="
  prep "$root"
}

cmd="${1:-}"
case "$cmd" in
  help|-h|--help) usage ;;
  version|-v|--version)
    v="$(git -C "$HARNESS" describe --always --dirty 2>/dev/null || echo unknown)"
    echo "meeting-harness $v  ($HARNESS)" ;;
  doctor) doctor ;;
  status) status "${2:-}" ;;
  prep)   prep "${2:-}" ;;
  diarize) sess="$(need_dir "${2:-}" "場次目錄")" || exit $?; run_diarize "$sess" ;;
  notes)  notes "${2:-}" ;;
  type)
    t="${2:-}"
    case "$t" in
      seminar|internal|client|1on1|workshop|interview) ;;
      *) echo "✗ 用法: meeting.sh type <seminar|internal|client|1on1|workshop|interview> <根或場次目錄>" >&2; exit 2 ;;
    esac
    set_type "$t" "${3:-}" >/dev/null; echo "✓ 已設定型態：${t}（下次 prep 會沿用，不用再指定）" ;;
  seminar|internal|client|1on1|workshop|interview) typed_prep "$cmd" "${2:-}" ;;
  ingest) shift; python3 "$BIN/_scaffold.py" "$@" ;;
  voiceprint)
    shift
    sub="${1:-}"
    case "$sub" in
      add)
        sess="$(need_dir "${2:-}" "場次目錄")" || exit $?
        [[ -n "${3:-}" && -n "${4:-}" ]] || { echo "✗ 用法: meeting.sh voiceprint add <場次目錄> <SPEAKER_xx> <姓名>" >&2; exit 2; }
        python3 "$BIN/_voiceprint.py" add "$sess" "$3" "$4" --harness "$HARNESS" ;;
      match)
        sess="$(need_dir "${2:-}" "場次目錄")" || exit $?
        python3 "$BIN/_voiceprint.py" match "$sess" --harness "$HARNESS" ;;
      list)   python3 "$BIN/_voiceprint.py" list --harness "$HARNESS" ;;
      remove)
        [[ -n "${2:-}" ]] || { echo "✗ 用法: meeting.sh voiceprint remove <姓名>" >&2; exit 2; }
        python3 "$BIN/_voiceprint.py" remove "$2" --harness "$HARNESS" ;;
      *) echo "✗ 用法: meeting.sh voiceprint <add|match|list|remove> …" >&2; exit 2 ;;
    esac ;;
  render) sess="$(need_dir "${2:-}" "場次目錄")" || exit $?; shift 2 || true; python3 "$BIN/_render.py" "$sess" "$@" ;;
  summarize-local) sess="$(need_dir "${2:-}" "場次目錄")" || exit $?; shift 2 || true; bash "$BIN/summarize-local.sh" "$sess" "$@" ;;
  local)  local_pipeline "${2:-}" "${3:-}" ;;
  record) shift; record_cmd "$@"; exit $? ;;
  # R3 頂層子指令（spec R3-§2.2、§3.19）：search、sync、reminders 是保留字，不再當成根目錄
  # （名為 search 的根目錄要寫 meeting ./search；§7 疑慮 46）。
  search) shift; python3 "$BIN/lib/_search.py" "$@"; exit $? ;;
  sync)   shift; python3 "$BIN/lib/_record_lib.py" sync "$@"; exit $? ;;
  reminders)
    shift
    if [[ -f "$BIN/lib/_reminders.py" ]]; then
      python3 "$BIN/lib/_reminders.py" "$@"; exit $?
    fi
    echo "✗ meeting reminders 尚未提供（bin/lib/_reminders.py 不存在）。" >&2
    echo "  名為 reminders 的根目錄請寫： meeting.sh ./reminders" >&2
    exit 2 ;;
  "")     usage; exit 1 ;;
  -*)     echo "✗ 未知的選項：$cmd" >&2; echo "  指令說明： meeting.sh help" >&2; exit 2 ;;
  *)
    # 預設：把第一個參數當會議根目錄。不是目錄就當成打錯指令，直接講清楚。
    if [[ -d "$cmd" ]]; then
      prep "$cmd"
    else
      echo "✗ 「${cmd}」既不是已知指令，也不是存在的目錄。" >&2
      echo "  指令說明： meeting.sh help" >&2
      exit 2
    fi ;;
esac

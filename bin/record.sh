#!/usr/bin/env bash
# record.sh —— meeting record 的本體（由 meeting.sh 的 record) 分支呼叫；層旗標 --recorder／--yes 已被拿掉）
#
# 寫法、寫法旗標、結束碼的唯一定義：spec §2.4（本檔的 help 照 §2.4.3 輸出）。
#   record.sh [<根>] [--window <id>]      開錄（有 tty 就問答；沒有 tty 一定要帶 --window）
#   record.sh windows [--json]            列出可錄的視窗
#   record.sh preflight --window <id>     只跑開錄前檢查
#   record.sh stop | status               停止／看狀態
#   record.sh finish <場次>               把已落盤的段落收尾（冪等）
#   record.sh help | -h | --help          印出寫法、旗標與結束碼
#
# 錄製器一律用 open -n -a 啟動（TCC 的責任程序才會是 app 本身），不直接執行 app 裡的二進位；
# 測試以 MH_RECORD_OPEN 換成替身。app 的結果不經 open 回傳，只看 record.status.json（runId 相符才採信）。
# 本檔不改使用者的預設輸入／輸出裝置。
set -uo pipefail

HARNESS="$(cd "$(dirname "$0")/.." && pwd)"
BIN="${HARNESS}/bin"
REC_HOME="${MH_RECORD_HOME:-$HOME/.meeting-harness}"
APP="${MH_RECORDER_APP:-$HOME/Applications/MeetingRecorder.app}"
STATUS_FILE="${REC_HOME}/record.status.json"
PID_FILE="${REC_HOME}/record.pid"
DEFAULTS_FILE="${REC_HOME}/record.defaults.json"
FIRST_STATUS_SECONDS=20      # open 之後多久內要看到本次的狀態（spec §4.1.6）
ASK_AUTOMATION_SECONDS=120   # 帶 --ask-automation 時等 windows 輸出的上限（使用者要讀授權框，spec §3.5）

err() { echo "$*" >&2; }

usage_help() {
  cat <<'HELP'
meeting record — 錄下會議視窗與雙路音訊（系統聲音＋麥克風，全程本機）

寫法：
  meeting record [<根>]          結束碼 0 2 3 4 5
  meeting record windows         結束碼 0 2 4
  meeting record preflight       結束碼 0 2 3 4
  meeting record stop            結束碼 0 3 5
  meeting record status          結束碼 0 5
  meeting record finish <場次>   結束碼 0 2 3 5
  meeting record help            結束碼 0

旗標：
  meeting record [<根>]          --window <id>
  meeting record windows         --json
  meeting record preflight       --window <id>

meeting.sh 層旗標：
  --recorder  明確要錄製，略過 ./record 撞名檢查（record 之後任何位置都可以）
  --yes       宣告沒有人可問，只影響 ./record 撞名的判斷

結束碼：
  0  成功（status 含「沒有錄製在跑」；finish 含「已完成」）
  2  參數或前提不符（缺參數、根目錄不存在、app 未建置、場次撞名、已有錄製在跑、非互動又沒有 --window）；任何寫法遇到未知的選項、或 ./record 撞名而沒有人可問也回 2
  3  找不到目標（視窗不存在、沒有錄製在跑、該場次沒有段落）
  4  開錄前檢查的 hard 項失敗（權限、RMS、磁碟），或開錄後 20 秒內沒有任何狀態（多半是權限）
  5  錄製或收尾出錯，已落盤段落保留（用 meeting record finish 收尾）；status 回 5 表示上次錄製異常中止

說明：
  有 tty 時 meeting record 會依序問根目錄、場次名、會議型態、出席者、要錄的視窗（★ 列是預設）；
  沒有 tty 的呼叫者一定要帶 --window（id 從 meeting record windows 取得）。
  help 是保留字：根目錄剛好叫 help 時寫 meeting record ./help。
  record（錄製）和 meeting render（由 meeting.record.json 重出產物）無關。
  當機救回時，最後一段未收尾的 1 分鐘會丟。
HELP
}

# 未知選項（spec §2.2 通則、§2.4.2）：-- 開頭、又不在該寫法寫法旗標集合內的參數。
# 用法：check_unknown "<允許的旗標，空白分隔>" "<要帶值的旗標，空白分隔>" 參數…
check_unknown() {
  local allowed=" $1 " valued=" $2 " a skip=0
  shift 2
  for a in "$@"; do
    if [[ "${skip}" -eq 1 ]]; then skip=0; continue; fi
    case "$a" in
      --*)
        if [[ "${allowed}" != *" ${a} "* ]]; then
          err "✗ 未知的選項：${a}"
          err "  寫法與旗標： meeting.sh record help"
          return 2
        fi
        [[ "${valued}" == *" ${a} "* ]] && skip=1
        ;;
    esac
  done
  return 0
}

need_app() {
  if [[ ! -d "${APP}" ]]; then
    err "✗ 找不到錄製器：${APP}"
    err "  先建置： bash \"${HARNESS}/tools/MeetingRecorder/build.sh\"（或用 MH_RECORDER_APP 指定 app 路徑）"
    return 2
  fi
}

launch() { # 以 open -n -a 啟動錄製器；參數是 app 收到的 --args
  if [[ -n "${MH_RECORD_OPEN:-}" ]]; then
    if [[ -x "${MH_RECORD_OPEN}" ]]; then
      "${MH_RECORD_OPEN}" -n -a "${APP}" --args "$@"
    else
      bash "${MH_RECORD_OPEN}" -n -a "${APP}" --args "$@"
    fi
  else
    open -n -a "${APP}" --args "$@"
  fi
}

is_tty() { [[ -t 0 && -t 2 ]]; }

permission_hint() {
  err "  最可能的原因是螢幕錄製權限沒給、或授權後沒有重開 app。打開設定："
  err "    open \"x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture\""
  err "  授權後要完全結束 MeetingRecorder 再重開（例： osascript -e 'quit app \"MeetingRecorder\"'），然後重跑。"
}

min_free_bytes() {
  python3 "${BIN}/_record_estimate.py" --minutes "${MH_RECORD_EST_MINUTES:-120}" | head -1
}

pid_alive() { [[ -n "${1:-}" ]] && kill -0 "$1" 2>/dev/null; }

running_pid() { # 有錄製在跑就印 pid
  local pid
  [[ -f "${PID_FILE}" ]] || return 1
  pid="$(tr -cd '0-9' < "${PID_FILE}")"
  pid_alive "${pid}" && { echo "${pid}"; return 0; }
  return 1
}

# 讀狀態檔；runId 不符（或檔案不存在、解析失敗）時什麼都不印。
# 印出：<phase> <code>
status_of_run() { # <runId 或 *>
  python3 - "${STATUS_FILE}" "$1" <<'PY' 2>/dev/null
import json, sys
path, run = sys.argv[1], sys.argv[2]
try:
    st = json.load(open(path, encoding="utf-8"))
except Exception:
    sys.exit(0)
if run != "*" and st.get("runId") != run:
    sys.exit(0)
print(st.get("phase", ""), int(st.get("code", 0) or 0))
PY
}

# 把狀態檔的 preflight 結果與訊息印給人看（stderr）。mode：fail（hard 失敗）｜warn（warn 項）｜all
report_status() { # <mode>
  python3 - "${STATUS_FILE}" "$1" <<'PY' >&2
import json, sys
path, mode = sys.argv[1], sys.argv[2]
try:
    st = json.load(open(path, encoding="utf-8"))
except Exception:
    sys.exit(0)
NAMES = {"signing": "簽章身分", "screen_permission": "螢幕錄製權限", "relaunch_needed": "剛授權要重啟",
         "mic_permission": "麥克風權限", "system_audio_rms": "系統聲音", "mic_rms": "麥克風聲音",
         "disk": "磁碟空間", "window_exists": "目標視窗", "session_collision": "場次撞名", "power": "電源",
         "already_running": "已有錄製在跑", "window_minimized": "視窗最小化", "apple_events": "會議分頁標記（Apple Events）"}
for r in st.get("preflight") or []:
    if r.get("ok"):
        if mode == "all":
            print(f"  ✓ {NAMES.get(r.get('item'), r.get('item'))}")
        continue
    sev = r.get("severity")
    if mode == "fail" and sev != "hard":
        continue
    if mode == "warn" and sev != "warn":
        continue
    mark = "✗" if sev == "hard" else "⚠"
    msg = (r.get("message") or "").strip()
    print(f"  {mark} {NAMES.get(r.get('item'), r.get('item'))}" + (f"：{msg}" if msg else ""))
msg = (st.get("message") or "").strip()
if msg and mode != "warn":
    print(f"  {msg}")
PY
}

# 等本次（runId）的狀態：FIRST_STATUS_SECONDS 秒內沒有就回 4；之後等到 phase 落在「結束集合」。
# 印出最後的 <phase> <code>。
wait_phase() { # <runId> <結束 phase，空白分隔> <總上限秒>
  local run="$1" ends=" $2 " limit="$3" t0 now got="" phase code
  t0="$(date +%s)"
  while :; do
    got="$(status_of_run "${run}")"
    now="$(date +%s)"
    if [[ -n "${got}" ]]; then
      phase="${got% *}"; code="${got#* }"
      if [[ "${ends}" == *" ${phase} "* ]]; then echo "${phase} ${code}"; return 0; fi
      if (( now - t0 > limit )); then echo "${phase} ${code}"; return 1; fi
    elif (( now - t0 >= FIRST_STATUS_SECONDS )); then
      return 4
    fi
    sleep 0.2
  done
}

no_status_exit() {
  err "✗ 錄製器啟動後 ${FIRST_STATUS_SECONDS} 秒內沒有回報任何狀態。"
  permission_hint
  return 4
}

# 呼叫 app 的 windows，輸出寫到檔案；印出該檔路徑。失敗（沒有輸出）回 4。
fetch_windows() { # <json:0|1>
  local json="$1" log limit=${FIRST_STATUS_SECONDS} args=() t0 last=-1 size stable=0
  log="$(mktemp "${TMPDIR:-/tmp}/mh-record-windows.XXXXXX")" || return 2
  args=(windows)
  [[ "${json}" == "1" ]] && args+=(--json)
  if is_tty; then
    args+=(--ask-automation)
    limit=${ASK_AUTOMATION_SECONDS}
    err "（第一次可能會跳「允許控制 Google Chrome」的授權框：選用，用來標記 Chrome 的會議分頁；不允許也能錄）"
  fi
  launch "${args[@]}" --log "${log}" >/dev/null 2>&1
  t0="$(date +%s)"
  while :; do
    if [[ -s "${log}" ]]; then
      size="$(wc -c < "${log}" | tr -d ' ')"
      if [[ "${size}" == "${last}" ]]; then stable=$((stable + 1)); else stable=0; last="${size}"; fi
      if [[ "${stable}" -ge 2 ]]; then
        if [[ "${json}" != "1" ]] || python3 -c 'import json,sys;json.load(open(sys.argv[1],encoding="utf-8"))' "${log}" 2>/dev/null; then
          echo "${log}"; return 0
        fi
      fi
    fi
    if (( $(date +%s) - t0 >= limit )); then
      rm -f "${log}"
      err "✗ ${limit} 秒內取不到視窗清單。"
      permission_hint
      return 4
    fi
    sleep 0.2
  done
}

cmd_windows() {
  check_unknown "--json" "" "$@" || return 2
  local json=0 a log
  for a in "$@"; do [[ "$a" == "--json" ]] && json=1; done
  need_app || return 2
  log="$(fetch_windows "${json}")" || return $?
  cat "${log}"
  rm -f "${log}"
  return 0
}

window_arg() { # 從參數取 --window 的值；有 --window 但沒值回 2；沒有 --window 印空字串
  local prev="" a found=0
  for a in "$@"; do
    if [[ "${prev}" == "--window" ]]; then
      [[ "$a" == --* || -z "$a" ]] && { err "✗ --window 少了視窗 id（從 meeting record windows 取得）"; return 2; }
      echo "$a"; return 0
    fi
    [[ "$a" == "--window" ]] && found=1
    prev="$a"
  done
  if [[ "${found}" -eq 1 ]]; then err "✗ --window 少了視窗 id（從 meeting record windows 取得）"; return 2; fi
  echo ""
}

defaults_get() { # <鍵>：讀 record.defaults.json 的字串值
  python3 - "${DEFAULTS_FILE}" "$1" <<'PY' 2>/dev/null
import json, sys
try:
    v = json.load(open(sys.argv[1], encoding="utf-8")).get(sys.argv[2])
except Exception:
    v = None
print(v if isinstance(v, str) else "")
PY
}

cmd_preflight() {
  check_unknown "--window" "--window" "$@" || return 2
  local wid root session run got rc
  wid="$(window_arg "$@")" || return 2
  need_app || return 2
  if [[ -z "${wid}" ]]; then err "✗ 要帶 --window <id>（從 meeting record windows 取得）"; return 2; fi
  root="$(defaults_get root)"
  [[ -n "${root}" && -d "${root}" ]] || root="$(pwd)"
  session="${root}/$(date +%Y%m%d)/$(date +%H%M) 會議"
  run="$(uuidgen)"
  err "開錄前檢查中（約 10 秒；請對麥克風說一句話）…"
  launch preflight --window "${wid}" --session "${session}" --min-free-bytes "$(min_free_bytes)" \
    --run-id "${run}" --home "${REC_HOME}" >/dev/null 2>&1
  got="$(wait_phase "${run}" "done failed preflight_failed" 120)"
  rc=$?
  [[ "${rc}" -eq 4 ]] && { no_status_exit; return 4; }
  report_status all
  if [[ "${rc}" -ne 0 ]]; then err "✗ 開錄前檢查逾時沒有結束（停在 ${got% *}）。"; return 4; fi
  local code="${got#* }"
  if [[ "${code}" -eq 0 ]]; then echo "✓ 開錄前檢查通過（warn 項不擋開錄）"; return 0; fi
  return "${code}"
}

# 寫 meeting.json（spec §3.6：key 集合＝bin/_scaffold.py 寫的 7 個；expectedSpeakers 固定 null）。已存在就不動。
write_meeting_json() { # <場次> <型態> <出席者 JSON>
  python3 - "$1" "$2" "$3" <<'PY'
import json, os, sys, time
sess, mtype, attendees = sys.argv[1], sys.argv[2], json.loads(sys.argv[3] or "[]")
rec = os.path.join(sess, "錄音")
os.makedirs(rec, exist_ok=True)
p = os.path.join(rec, "meeting.json")
if not os.path.exists(p):
    data = {"type": mtype, "date": time.strftime("%Y-%m-%d"), "attendees": attendees,
            "expectedSpeakers": None, "language": "zh", "llm": "claude",
            "_note": "由 meeting record 開錄前建立的草稿。type 可改（可用型態見 meeting.sh help）；"
                     "attendees 是出席名單，只當講者命名與人數上限的參考。"}
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
PY
}

write_defaults() { # <根> <型態> <出席者 JSON> <minFreeBytes>
  python3 - "${DEFAULTS_FILE}" "$1" "$2" "$3" "$4" "${HARNESS}" "$(command -v python3)" "${MH_FFMPEG:-$(command -v ffmpeg)}" <<'PY'
import json, os, sys
path, root, mtype, attendees, minfree, harness, py, ff = sys.argv[1:9]
data = {"root": root, "type": mtype, "attendees": json.loads(attendees or "[]"), "harness": harness,
        "python3": py, "ffmpeg": ff, "minFreeBytes": int(minfree)}
os.makedirs(os.path.dirname(path), exist_ok=True)
tmp = path + ".tmp"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
os.replace(tmp, path)
PY
}

json_field() { # <JSON 字串> <鍵>：字串照印，其他型別印 JSON
  python3 -c 'import json,sys;v=json.loads(sys.argv[1]).get(sys.argv[2]);print(v if isinstance(v,str) else json.dumps(v,ensure_ascii=False))' "$1" "$2"
}

cleanup_new_session() { # 開錄沒成功時，把本次新建的空目錄與 meeting.json 收掉（有其他檔就不動）
  local sess="$1" day
  day="$(dirname "${sess}")"
  rm -f "${sess}/錄音/meeting.json"
  rmdir "${sess}/錄音/tracks" "${sess}/錄音" "${sess}" 2>/dev/null
  rmdir "${day}" 2>/dev/null
  return 0
}

cmd_start() {
  check_unknown "--window" "--window" "$@" || return 2
  local wid root="" prev="" a
  wid="$(window_arg "$@")" || return 2
  for a in "$@"; do
    if [[ "${prev}" != "--window" && "$a" != "--window" ]]; then
      if [[ -n "${root}" ]]; then err "✗ 多了參數：${a}（用法： meeting.sh record help）"; return 2; fi
      root="$a"
    fi
    prev="$a"
  done
  if [[ -z "${wid}" ]] && ! is_tty; then
    err "✗ 沒有終端機可以問答，要帶 --window <id>（id 從 meeting record windows 取得）："
    err "    meeting.sh record \"<會議根目錄>\" --window <id>"
    return 2
  fi
  if [[ -n "${root}" && ! -d "${root}" ]]; then
    err "✗ 找不到會議根目錄：${root}"
    return 2
  fi
  need_app || return 2
  if running_pid >/dev/null; then
    err "✗ 已有錄製在跑（pid $(running_pid)）。先 meeting record stop，或用 meeting record status 確認。"
    return 2
  fi

  local session_name mtype attendees="[]" bundle="" title="" identity=0
  if [[ -z "${wid}" ]]; then
    # 互動：先取視窗清單，再問答（_record_prompt.py 不寫檔；預設值由這裡組好交給它）
    local wlog dtmp answer rc
    wlog="$(fetch_windows 1)" || return $?
    dtmp="$(mktemp "${TMPDIR:-/tmp}/mh-record-defaults.XXXXXX")"
    python3 - "${DEFAULTS_FILE}" "${root}" "${dtmp}" <<'PY'
import json, os, sys
src, root, out = sys.argv[1:4]
try:
    d = json.load(open(src, encoding="utf-8"))
except Exception:
    d = {}
if not isinstance(d, dict):
    d = {}
if root:
    d["root"] = os.path.abspath(root)
json.dump(d, open(out, "w", encoding="utf-8"), ensure_ascii=False)
PY
    answer="$(python3 "${BIN}/_record_prompt.py" --windows-json "${wlog}" --defaults "${dtmp}")"
    rc=$?
    rm -f "${wlog}" "${dtmp}"
    [[ "${rc}" -ne 0 ]] && return "${rc}"
    root="$(json_field "${answer}" root)"
    session_name="$(json_field "${answer}" session)"
    mtype="$(json_field "${answer}" type)"
    attendees="$(json_field "${answer}" attendees)"
    wid="$(json_field "${answer}" windowID)"
    bundle="$(json_field "${answer}" bundleID)"
    title="$(json_field "${answer}" title)"
    identity=1
  else
    if [[ -z "${root}" ]]; then
      root="$(defaults_get root)"
      if [[ -z "${root}" || ! -d "${root}" ]]; then
        err "✗ 少了會議根目錄（也沒有上次的預設值）：meeting.sh record \"<會議根目錄>\" --window <id>"
        return 2
      fi
    fi
    session_name="$(date +%H%M) 會議"
    mtype="$(defaults_get type)"
    [[ -n "${mtype}" ]] || mtype="$(cd "${BIN}" && python3 -c 'import _profile;print(_profile.DEFAULT_TYPE)')"
    attendees="$(python3 - "${DEFAULTS_FILE}" <<'PY' 2>/dev/null || echo "[]"
import json, sys
try:
    a = json.load(open(sys.argv[1], encoding="utf-8")).get("attendees") or []
except Exception:
    a = []
print(json.dumps(a if isinstance(a, list) else [], ensure_ascii=False))
PY
)"
  fi
  root="$(cd "${root}" && pwd)" || return 2

  local sess="${root}/$(date +%Y%m%d)/${session_name}" existed=0 minfree run got rc code phase
  [[ -d "${sess}" ]] && existed=1
  write_meeting_json "${sess}" "${mtype}" "${attendees}" || { err "✗ 寫不進 ${sess}/錄音/meeting.json"; return 2; }
  minfree="$(min_free_bytes)"
  run="$(uuidgen)"
  local wargs=(--window "${wid}")
  [[ "${identity}" -eq 1 ]] && wargs+=(--window-bundle "${bundle}" --window-title "${title}")
  err "開錄前檢查中（約 10 秒）：請對麥克風說一句話，錄製器也會播兩次提示音…"
  launch start "${wargs[@]}" --session "${sess}" --min-free-bytes "${minfree}" --run-id "${run}" \
    --home "${REC_HOME}" --harness "${HARNESS}" >/dev/null 2>&1
  got="$(wait_phase "${run}" "recording preflight_failed failed done" 120)"
  rc=$?
  if [[ "${rc}" -eq 4 ]]; then
    [[ "${existed}" -eq 0 ]] && cleanup_new_session "${sess}"
    no_status_exit; return 4
  fi
  phase="${got% *}"; code="${got#* }"
  if [[ "${rc}" -ne 0 ]]; then
    err "✗ 開錄前檢查逾時沒有結束（停在 ${phase}）。用 meeting record status 看狀態。"
    return 4
  fi
  case "${phase}" in
    recording)
      report_status warn
      write_defaults "${root}" "${mtype}" "${attendees}" "${minfree}"
      echo "● 開始錄製：${sess}"
      echo "  停止： meeting.sh record stop　　狀態： meeting.sh record status"
      return 0 ;;
    preflight_failed)
      err "✗ 開錄前檢查沒通過，沒有開始錄製："
      report_status fail
      [[ "${existed}" -eq 0 ]] && cleanup_new_session "${sess}"
      [[ "${code}" -eq 0 ]] && code=4
      return "${code}" ;;
    *)
      err "✗ 錄製開始後中斷，已落盤的段落保留："
      report_status fail
      err "  收尾： meeting.sh record finish \"${sess}\""
      [[ "${phase}" == "done" && "${code}" -eq 0 ]] && return 0
      return 5 ;;
  esac
}

# stop 之後的摘要：黑畫面區間（mm:ss–mm:ss）與各類告警次數
stop_summary() {
  python3 - "${STATUS_FILE}" <<'PY'
import json, os, sys
from collections import Counter
try:
    st = json.load(open(sys.argv[1], encoding="utf-8"))
except Exception:
    sys.exit(0)
def mmss(t):
    t = int(t or 0)
    return f"{t // 60:02d}:{t % 60:02d}"
sess = st.get("session") or ""
msg = (st.get("message") or "").strip()
if sess:
    print(f"場次：{sess}")
if msg:
    print(msg)
black = []
try:
    mf = json.load(open(os.path.join(sess, "錄音", "tracks", "manifest.json"), encoding="utf-8"))
    black = mf.get("blackIntervals") or []
except Exception:
    pass
if black:
    print("黑畫面區間：" + "、".join(f"{mmss(b.get('start'))}–" + (mmss(b['end']) if b.get("end") is not None else "（未恢復）")
                                for b in black))
else:
    print("黑畫面區間：沒有")
NAMES = {"silence_system": "系統聲音靜音", "silence_mic": "麥克風靜音", "black": "畫面全黑",
         "suspended": "會議視窗暫停（例如最小化）", "disk_low": "磁碟空間不足",
         "device_change": "音訊裝置切換（只記錄）", "audio_format_change": "音訊格式改變（只記錄）"}
counts = Counter(w.get("kind") for w in st.get("warnings") or [])
if counts:
    print("告警次數：")
    for k, n in counts.items():
        print(f"  {NAMES.get(k, k)}：{n} 次")
else:
    print("告警次數：沒有")
PY
}

cmd_stop() {
  check_unknown "" "" "$@" || return 2
  if [[ $# -gt 0 ]]; then err "✗ stop 不接參數：$*"; return 2; fi
  local pid
  if ! pid="$(running_pid)"; then
    err "沒有錄製在跑。"
    return 3
  fi
  local started limit t0 got phase code logf lines=0 n
  limit="$(python3 - "${STATUS_FILE}" <<'PY' 2>/dev/null || echo 7200
import json, sys, time, datetime
try:
    st = json.load(open(sys.argv[1], encoding="utf-8"))
    t = datetime.datetime.strptime(st["startedAt"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
    print(int(2 * max(0, time.time() - t) + 120))
except Exception:
    print(7200)
PY
)"
  logf="${REC_HOME}/record.log"
  [[ -f "${logf}" ]] && lines="$(wc -l < "${logf}" | tr -d ' ')"
  kill -TERM "${pid}" 2>/dev/null
  echo "已送出停止，收尾中（整支重新編碼，長場次要等一下）…"
  t0="$(date +%s)"
  while :; do
    if [[ -f "${logf}" ]]; then  # 把收尾進度（例「正規化 12/95」）轉印出來
      n="$(wc -l < "${logf}" | tr -d ' ')"
      if [[ "${n}" -gt "${lines}" ]]; then
        sed -n "$((lines + 1)),${n}p" "${logf}" | grep -E '正規化|收尾|略過' || true
        lines="${n}"
      fi
    fi
    got="$(status_of_run '*')"
    phase="${got% *}"; code="${got#* }"
    if [[ "${phase}" == "done" || "${phase}" == "failed" ]]; then break; fi
    if ! pid_alive "${pid}" && [[ "${phase}" != "finalizing" ]]; then
      err "✗ 錄製器結束了，但狀態停在 ${phase:-（沒有狀態）}。用 meeting.sh record finish <場次> 收尾。"
      return 5
    fi
    if (( $(date +%s) - t0 > limit )); then
      err "✗ 等了 ${limit} 秒還沒收尾完。用 meeting.sh record status 看狀態。"
      return 5
    fi
    sleep 0.2
  done
  stop_summary
  if [[ "${phase}" == "done" && "${code}" -eq 0 ]]; then
    echo "✓ 已停止並收尾完成。"
    return 0
  fi
  err "✗ 停止了，但收尾失敗或錄製中出過錯；段落都還在，用 meeting.sh record finish <場次> 再收一次。"
  return 5
}

cmd_status() {
  check_unknown "" "" "$@" || return 2
  if [[ $# -gt 0 ]]; then err "✗ status 不接參數：$*"; return 2; fi
  if [[ ! -f "${STATUS_FILE}" ]]; then
    echo "沒有錄製在跑。"
    return 0
  fi
  python3 - "${STATUS_FILE}" "${PID_FILE}" <<'PY'
import datetime, json, os, sys, time
st_path, pid_path = sys.argv[1], sys.argv[2]
try:
    st = json.load(open(st_path, encoding="utf-8"))
except Exception:
    print("沒有錄製在跑（狀態檔讀不懂，忽略）。")
    sys.exit(0)
def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False
pid = st.get("pid")
try:
    pid = int(open(pid_path).read().strip() or pid)
except (OSError, ValueError):
    pass
phase, code, sess = st.get("phase"), st.get("code", 0), st.get("session") or ""
msg = (st.get("message") or "").strip()
LABEL = {"preflight": "開錄前檢查中", "recording": "錄製中", "stopping": "停止中", "finalizing": "收尾中"}
if phase in LABEL:
    if alive(pid):
        line = LABEL[phase]
        try:
            t = datetime.datetime.strptime(st["startedAt"], "%Y-%m-%dT%H:%M:%S%z").timestamp()
            e = int(time.time() - t)
            line += f" {e // 60:02d}:{e % 60:02d}"
        except Exception:
            pass
        print(f"{line}　場次：{sess}　已落盤 {st.get('segments', 0)} 段")
        alerts = [w for w in st.get("warnings") or [] if w.get("kind") not in ("device_change", "audio_format_change")]
        if alerts:
            print(f"  ⚠ 告警 {len(alerts)} 次；最新：{alerts[-1].get('message', '')}")
        sys.exit(0)
    if phase == "preflight":
        print("沒有錄製在跑（上次開錄前檢查中斷）。")
        sys.exit(0)
    print(f"✗ 上次錄製異常中止（錄製器已不在，狀態停在{LABEL[phase]}）。已落盤的段落還在，收尾：", file=sys.stderr)
    print(f"    meeting.sh record finish \"{sess}\"", file=sys.stderr)
    print("  （最後一段未收尾的 1 分鐘會丟）", file=sys.stderr)
    sys.exit(5)
print("沒有錄製在跑。")
if phase == "done" and not code:
    print(f"上次錄製：已完成　{sess}")
elif phase == "preflight_failed":
    print(f"上次開錄前檢查沒通過：{msg.splitlines()[0] if msg else ''}")
elif phase in ("done", "failed"):
    print(f"上次錄製出錯：{msg.splitlines()[0] if msg else ''}")
    if sess:
        print(f"  段落保留，收尾： meeting.sh record finish \"{sess}\"")
sys.exit(0)
PY
}

cmd_finish() {
  check_unknown "" "" "$@" || return 2
  local sess="${1:-}"
  if [[ -z "${sess}" ]]; then err "✗ 少了場次目錄：meeting.sh record finish <場次>"; return 2; fi
  if [[ $# -gt 1 ]]; then shift; err "✗ 多了參數：$*"; return 2; fi
  if [[ ! -d "${sess}" ]]; then err "✗ 找不到場次目錄：${sess}"; return 2; fi
  sess="$(cd "${sess}" && pwd)"
  if ! ls "${sess}/錄音/tracks"/seg-*.mov >/dev/null 2>&1; then
    err "✗ 這個場次沒有錄製段落（${sess}/錄音/tracks/seg-*.mov）。"
    return 3
  fi
  python3 "${BIN}/_record_finalize.py" "${sess}"
  case $? in
    0) return 0 ;;
    3) return 3 ;;
    *) err "✗ 收尾失敗；段落都還在，修好後可以再跑一次 meeting.sh record finish。"; return 5 ;;
  esac
}

sub="${1:-}"
case "${sub}" in
  help|-h|--help) shift; check_unknown "" "" "$@" || exit 2; usage_help; exit 0 ;;
  windows)   shift; cmd_windows "$@"; exit $? ;;
  preflight) shift; cmd_preflight "$@"; exit $? ;;
  stop)      shift; cmd_stop "$@"; exit $? ;;
  status)    shift; cmd_status "$@"; exit $? ;;
  finish)    shift; cmd_finish "$@"; exit $? ;;
  *)         cmd_start "$@"; exit $? ;;
esac

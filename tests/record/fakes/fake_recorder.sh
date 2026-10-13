#!/usr/bin/env bash
# fake_recorder.sh —— 模擬「正在錄製的 MeetingRecorder 實例」（給 record stop／status 測試用）
#
# 啟動後：在 MH_RECORD_HOME 寫 record.pid（自己的 pid）與 record.status.json（phase=recording），
# 收到 SIGTERM 時依 FAKE_STOP_CODE（預設 0）寫 phase=done code=0 或 phase=failed code=<碼>，
# 刪 record.pid 後結束。FAKE_SESSION 為場次目錄；FAKE_WARNINGS 為 warnings 的 JSON 陣列（選用）。
#
# R2（spec §4.16.5–§4.16.9、§4.16.11；plan §9.2 r2a）——以下變數都沒設時，行為與第一輪完全相同：
#   FAKE_CONTROL=1       狀態檔含 controlVersion 1、recordingStartedAt、paused false、micMuted false、markers 0；
#                        trap SIGUSR1 → 讀 <home>/record.control.json（runId 與狀態檔相同、schemaVersion 1 才採信）→
#                        依 paused／micMuted／markerSeq 更新狀態檔的 paused／pausedAt／micMuted／markers；
#                        每收到一次 SIGUSR1 就把 <home>/fake_usr1.count 加 1（測試用來數訊號次數）
#   FAKE_CONTROL=ignore  狀態檔含 controlVersion 1，但 trap '' USR1（忽略訊號、狀態不反映）
#   FAKE_CONTROL 未設定  舊版錄製器：狀態檔沒有 controlVersion，也不裝 SIGUSR1 處理（收到會被預設動作終止）
#   FAKE_PHASE           開始時寫的 phase（preflight／stopping／finalizing…；預設 recording）
#   FAKE_STATUS_EXTRA    JSON 物件，每次寫狀態檔時合併進去（例：{"markers": 2}、recordingStartedAt 等 R2 欄位）
#
# R3（spec §6 第 136 條、§4.27.6）：
#   FAKE_LOCK            預設 1：寫 record.status.json 與 record.pid 之前，由背景 python3 子程序以 fcntl.flock 持有
#                        <home>/record.lock（最多重試 5 秒）；子程序每 0.2 秒看父程序是否還在，父程序結束（含 SIGKILL）就退出放鎖；
#                        on_term 與正常結束時先結束該子程序。FAKE_LOCK=0 時不持鎖。
set -uo pipefail
home="${MH_RECORD_HOME:?fake_recorder.sh 需要 MH_RECORD_HOME}"
mkdir -p "${home}"

write_status() { # <phase> <code> <message>
  python3 - "${home}" "$1" "$2" "$3" "$$" <<'PY'
import json, os, sys, tempfile, time
home, phase, code, msg, pid = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], int(sys.argv[5])
now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
st = {"schemaVersion": 1, "runId": os.environ.get("FAKE_RUN_ID", "fake-run"), "pid": pid, "phase": phase,
      "code": code, "message": msg, "session": os.environ.get("FAKE_SESSION", ""),
      "startedAt": now, "updatedAt": now, "segments": 1, "preflight": [],
      "warnings": json.loads(os.environ.get("FAKE_WARNINGS", "[]"))}
control = os.environ.get("FAKE_CONTROL", "")
path = os.path.join(home, "record.status.json")
if control in ("1", "ignore"):
    prev = {}
    try:
        prev = json.load(open(path, encoding="utf-8"))
    except Exception:
        pass
    if prev.get("runId") == st["runId"] and prev.get("pid") == pid:
        # 同一個實例重寫：沿用開錄時刻與 R2 欄位
        st["startedAt"] = prev.get("startedAt", now)
        for k in ("controlVersion", "recordingStartedAt", "paused", "micMuted", "pausedSeconds", "pausedAt",
                  "markers"):
            if k in prev:
                st[k] = prev[k]
    else:
        iso = time.strftime("%Y-%m-%dT%H:%M:%S") + time.strftime("%z")[:3] + ":" + time.strftime("%z")[3:]
        st.update(controlVersion=1, recordingStartedAt=iso, paused=False, micMuted=False, pausedSeconds=0.0,
                  markers=0)
st.update(json.loads(os.environ.get("FAKE_STATUS_EXTRA", "{}") or "{}"))
fd, tmp = tempfile.mkstemp(dir=home, prefix=".record.status.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(st, fh, ensure_ascii=False)
os.replace(tmp, path)
PY
}

on_usr1() { # FAKE_CONTROL=1：依控制檔更新狀態檔
  python3 - "${home}" "$$" <<'PY'
import json, os, sys, tempfile, time
home, pid = sys.argv[1], int(sys.argv[2])
cnt = os.path.join(home, "fake_usr1.count")
try:
    n = int(open(cnt).read().strip() or 0)
except (OSError, ValueError):
    n = 0
with open(cnt, "w") as fh:
    fh.write(f"{n + 1}\n")
path = os.path.join(home, "record.status.json")
try:
    st = json.load(open(path, encoding="utf-8"))
    ctl = json.load(open(os.path.join(home, "record.control.json"), encoding="utf-8"))
except Exception:
    sys.exit(0)
if ctl.get("runId") != st.get("runId") or ctl.get("schemaVersion") != 1:
    sys.exit(0)
iso = time.strftime("%Y-%m-%dT%H:%M:%S") + time.strftime("%z")[:3] + ":" + time.strftime("%z")[3:]
paused = bool(ctl.get("paused"))
if paused and not st.get("paused"):
    st["pausedAt"] = iso
if not paused:
    st.pop("pausedAt", None)
st["paused"] = paused
st["micMuted"] = bool(ctl.get("micMuted"))
st["markers"] = max(int(st.get("markers") or 0), int(ctl.get("markerSeq") or 0))
st["updatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
fd, tmp = tempfile.mkstemp(dir=home, prefix=".record.status.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(st, fh, ensure_ascii=False)
os.replace(tmp, path)
PY
}

lock_pid=""
start_lock() { # FAKE_LOCK（預設 1）：背景子程序持有 <home>/record.lock，等它拿到鎖（或放棄）才回來
  [[ "${FAKE_LOCK:-1}" == "0" ]] && return 0
  local ready
  ready="$(mktemp "${TMPDIR:-/tmp}/fake_recorder.lock.XXXXXX")"
  rm -f "${ready}"
  python3 - "${home}/record.lock" "$$" "${ready}" <<'PY' &
import fcntl, os, sys, time
path, parent, ready = sys.argv[1], int(sys.argv[2]), sys.argv[3]
fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
held = False
deadline = time.monotonic() + 5
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = True
        break
    except OSError:
        if time.monotonic() > deadline:
            break
        time.sleep(0.05)
with open(ready, "w") as fh:
    fh.write("held\n" if held else "failed\n")
if not held:
    sys.exit(0)
while True:
    if os.getppid() != parent:
        break
    try:
        os.kill(parent, 0)
    except OSError:
        break
    time.sleep(0.2)
PY
  lock_pid=$!
  local i
  for i in $(seq 1 200); do
    [[ -s "${ready}" ]] && break
    sleep 0.05
  done
  rm -f "${ready}"
}
stop_lock() { # 結束持鎖子程序（放鎖）
  [[ -n "${lock_pid}" ]] || return 0
  kill "${lock_pid}" 2>/dev/null
  wait "${lock_pid}" 2>/dev/null
  lock_pid=""
}

on_term() {
  local code="${FAKE_STOP_CODE:-0}"
  stop_lock
  write_status stopping 0 ""
  if [[ "${code}" == "0" ]]; then
    write_status done 0 "已完成（範例訊息）"
  else
    write_status failed "${code}" "收尾失敗，段落保留（範例訊息）"
  fi
  rm -f "${home}/record.pid"
  exit 0
}
trap on_term TERM
case "${FAKE_CONTROL:-}" in
  1)      trap on_usr1 USR1 ;;
  ignore) trap '' USR1 ;;
esac

start_lock
write_status "${FAKE_PHASE:-recording}" 0 ""
echo "$$" > "${home}/record.pid"
# 等 SIGTERM；最多 120 秒後自行結束，避免殘留
for _ in $(seq 1 1200); do sleep 0.1; done
stop_lock
rm -f "${home}/record.pid"
exit 0

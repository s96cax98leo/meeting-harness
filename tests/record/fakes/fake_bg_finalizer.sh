#!/usr/bin/env bash
# fake_bg_finalizer.sh —— 背景收尾協定（spec R3x §3.23、§3.24）的可執行參考替身（spec §3.27）
#
# 給 record stop／status／finish 的測試用；bash 主程序（ps -o comm= 結尾是 bash，配 Sandbox.env 的 MH_RECORDER_COMM=bash）。
# 只寫 MH_RECORD_HOME 底下的檔，不讀 client-names.txt，不碰 ~/.meeting-harness。
#
# 啟動：背景 python3 子程序以 flock 持有 <home>/record.lock（同 fake_recorder.sh 的 FAKE_LOCK 寫法：最多重試 5 秒；
#   子程序每 0.2 秒看父程序是否還在，父程序結束即放），寫 record.status.json（phase recording、FAKE_RUN_ID、FAKE_SESSION）
#   與 record.pid（自己的 pid），然後等訊號。
# 收到 SIGTERM：<home>/fake_bg_<runId>.sigterm 的計數加 1；第一次時依序做 §3.23 第 2–7 步：
#   2. 每場鎖 <home>/finalizing/<runId>.lock 由另一個背景子程序持有到父程序結束；
#   3–4. 寫每場狀態檔 <home>/finalizing/<runId>.status.json 與共用狀態檔（phase finalizing、background true、queued true；
#        這時仍持有 record.lock，共用狀態檔無條件寫）；
#   5. record.pid 的內容是自己才刪；
#   6. 清掉 prunable 的每場檔（終態、updatedAt 超過 86400 秒、每場鎖沒人持有；或孤兒：finalizing、鎖沒人持有、場次目錄不存在）；
#   7. 結束持有 record.lock 的子程序（放開開錄鎖）。
#   之後以背景子程序每 0.5 秒試 <home>/finalize.queue.lock，取得後持有到父程序結束；取得時在 <home>/fake_bg.events 追加
#   「start <runId> <epoch 秒，小數 3 位>」，每場狀態檔改成沒有 queued（共用狀態檔照 §3.24 的條件）；睡 FAKE_FINALIZE_SECONDS
#   （預設 2）秒；依 FAKE_STOP_CODE（預設 0）寫最終狀態（0 → done／0；其他 → failed／該碼，message「收尾失敗（替身）」）到每場
#   狀態檔，共用狀態檔照 §3.24 的條件（1 秒內每 100 ms 試 record.lock，拿到而且共用狀態檔不存在或 runId 是自己才寫）；
#   追加「end <runId> <epoch>」；結束。第二次以後的 SIGTERM 只計數。
# FAKE_CRASH=<秒數>：做完第 7 步後再過該秒數（0＝立刻），對自己與所有持鎖子程序送 SIGKILL，每場狀態檔停在 finalizing。
set -uo pipefail
home="${MH_RECORD_HOME:?fake_bg_finalizer.sh 需要 MH_RECORD_HOME}"
run="${FAKE_RUN_ID:-fake-bg-run}"
sess="${FAKE_SESSION:-}"
case "${run}" in
  ""|*[!A-Za-z0-9._-]*) echo "fake_bg_finalizer.sh：FAKE_RUN_ID 只能含 [A-Za-z0-9._-]" >&2; exit 97 ;;
esac
mkdir -p "${home}"
fin_dir="${home}/finalizing"
bg_status="${fin_dir}/${run}.status.json"
bg_lock="${fin_dir}/${run}.lock"
shared="${home}/record.status.json"
counter="${home}/fake_bg_${run}.sigterm"
events="${home}/fake_bg.events"
holders="${home}/.fake_bg_${run}.holders"
started_at="$(date +%Y-%m-%dT%H:%M:%S%z)"
got_term=0
holder_pid=""

on_term() { # 每次 SIGTERM 計數加 1（tmp＋mv，讀的人不會看到半寫的檔）
  local n=0
  [[ -f "${counter}" ]] && n="$(cat "${counter}" 2>/dev/null)"
  [[ "${n}" =~ ^[0-9]+$ ]] || n=0
  printf '%s\n' "$((n + 1))" > "${counter}.tmp.$$" && mv -f "${counter}.tmp.$$" "${counter}"
  got_term=1
}
trap on_term TERM

nap() { # <秒數>：以 0.1 秒為單位睡（每 0.1 秒讓 trap 有機會執行）
  local n i
  n="$(python3 -c 'import sys; print(max(0, int(round(float(sys.argv[1]) * 10))))' "$1" 2>/dev/null || echo 0)"
  for ((i = 0; i < n; i++)); do sleep 0.1; done
}

write_state() { # <路徑> <phase> <code> <message> <background 0|1> <queued 0|1>：tmp＋rename 原子寫入
  python3 - "$1" "$2" "$3" "$4" "$5" "$6" "${run}" "${sess}" "${started_at}" "$$" <<'PY'
import json, os, sys, tempfile, time
path, phase, code, msg, bg, queued, run, sess, started, pid = sys.argv[1:11]
st = {"schemaVersion": 1, "runId": run, "pid": int(pid), "phase": phase, "code": int(code), "message": msg,
      "session": sess, "startedAt": started, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "segments": 1,
      "preflight": [], "warnings": []}
if bg == "1":
    st["background"] = True
if queued == "1":
    st["queued"] = True
d = os.path.dirname(path)
os.makedirs(d, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=d, prefix=".fake_bg.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(st, fh, ensure_ascii=False)
os.replace(tmp, path)
PY
}

copy_shared() { # 仍持有 record.lock 時：每場狀態檔的內容無條件寫到共用狀態檔
  python3 - "${bg_status}" "${shared}" <<'PY'
import os, sys, tempfile
src, dst = sys.argv[1:3]
data = open(src, encoding="utf-8").read()
fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dst), prefix=".record.status.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    fh.write(data)
os.replace(tmp, dst)
PY
}

shared_if_writable() { # §3.24：1 秒內每 100 ms 試 record.lock；拿到而且共用狀態檔不存在／讀不懂／runId 是自己才寫
  python3 - "${home}" "${run}" "${bg_status}" <<'PY'
import fcntl, json, os, sys, tempfile, time
home, run, src = sys.argv[1:4]
try:
    fd = os.open(os.path.join(home, "record.lock"), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
except OSError:
    sys.exit(0)
got = False
deadline = time.monotonic() + 1.0
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        got = True
        break
    except OSError:
        if time.monotonic() >= deadline:
            break
        time.sleep(0.1)
try:
    if not got:
        sys.exit(0)
    path = os.path.join(home, "record.status.json")
    try:
        cur = json.load(open(path, encoding="utf-8"))
        if not isinstance(cur, dict):
            cur = None
    except Exception:
        cur = None
    if cur is not None and cur.get("runId") != run:
        sys.exit(0)
    data = open(src, encoding="utf-8").read()
    tfd, tmp = tempfile.mkstemp(dir=home, prefix=".record.status.", suffix=".tmp")
    with os.fdopen(tfd, "w", encoding="utf-8") as fh:
        fh.write(data)
    os.replace(tmp, path)
finally:
    os.close(fd)
PY
}

event() { # <start|end>：追加一行到 <home>/fake_bg.events
  python3 - "${events}" "$1" "${run}" <<'PY'
import sys, time
path, kind, run = sys.argv[1:4]
with open(path, "a", encoding="utf-8") as fh:
    fh.write(f"{kind} {run} {time.time():.3f}\n")
PY
}

start_holder() { # <鎖檔> <now|poll> <ready 檔>：背景子程序持鎖到父程序結束；子程序 pid 放在 holder_pid
  # （不能用 $(…) 呼叫：子程序會變成 subshell 的子程序，父程序檢查就失效）
  # now：LOCK_NB 最多重試 5 秒（拿不到就寫 failed 後結束）；poll：每 0.5 秒試一次，直到拿到或父程序結束。
  python3 - "$1" "$2" "$3" "$$" <<'PY' >/dev/null 2>&1 &
import fcntl, os, sys, time
path, mode, ready, parent = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])

def parent_alive():
    if os.getppid() != parent:
        return False
    try:
        os.kill(parent, 0)
        return True
    except OSError:
        return False

os.makedirs(os.path.dirname(path), exist_ok=True)
fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
held = False
deadline = time.monotonic() + 5
while True:
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held = True
        break
    except OSError:
        if not parent_alive():
            break
        if mode == "now":
            if time.monotonic() > deadline:
                break
            time.sleep(0.05)
        else:
            time.sleep(0.5)
tmp = ready + ".tmp"
with open(tmp, "w") as fh:
    fh.write("held\n" if held else "failed\n")
os.replace(tmp, ready)
if not held:
    sys.exit(0)
while parent_alive():
    time.sleep(0.2)
PY
  holder_pid=$!
  echo "${holder_pid}" >> "${holders}"
}

wait_ready() { # <ready 檔>：等子程序回報（每 0.1 秒看一次，trap 照常執行）；回 0＝held
  local f="$1"
  until [[ -s "${f}" ]]; do sleep 0.1; done
  [[ "$(cat "${f}")" == "held" ]]
}

stop_holder() { # <pid>：結束持鎖子程序（放鎖）
  [[ -n "${1:-}" ]] || return 0
  kill "$1" 2>/dev/null
  wait "$1" 2>/dev/null
}

cleanup() {
  local p
  if [[ -f "${holders}" ]]; then
    for p in $(cat "${holders}"); do kill "${p}" 2>/dev/null; done
    rm -f "${holders}"
  fi
  rm -f "${home}/.fake_bg_${run}".*.ready "${home}/.fake_bg_${run}".*.ready.tmp
}

prune() { # §3.23 第 6 步：prunableBackgroundJob 為 true 的每場檔（終態 24 小時以上、或孤兒）刪掉狀態檔與鎖檔
  python3 - "${fin_dir}" "${run}" <<'PY'
import datetime, errno, fcntl, glob, json, os, sys, time
fin_dir, own = sys.argv[1:3]

def lock_held(path):
    try:
        fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)   # 旁觀者規則：不帶 O_CREAT
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except OSError as e:
        return e.errno in (errno.EWOULDBLOCK, errno.EAGAIN)
    finally:
        os.close(fd)

for p in glob.glob(os.path.join(fin_dir, "*.status.json")):
    run = os.path.basename(p)[:-len(".status.json")]
    if run == own:
        continue
    try:
        st = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    lock = os.path.join(fin_dir, run + ".lock")
    if lock_held(lock):
        continue
    phase = st.get("phase")
    sess = st.get("session") or ""
    prunable = False
    if phase == "finalizing":
        prunable = not (sess and os.path.isdir(sess))
    elif phase in ("done", "failed"):
        try:
            t = datetime.datetime.strptime(st.get("updatedAt"), "%Y-%m-%dT%H:%M:%S%z").timestamp()
            prunable = time.time() - t > 86400
        except Exception:
            prunable = False
    if prunable:
        for f in (p, lock):
            try:
                os.remove(f)
            except OSError:
                pass
PY
}

crash_timer() { # FAKE_CRASH：過 <秒數> 後對所有持鎖子程序與自己送 SIGKILL
  local secs="$1" me="$$"
  (
    sleep "${secs}"
    if [[ -f "${holders}" ]]; then
      for p in $(cat "${holders}"); do kill -KILL "${p}" 2>/dev/null; done
    fi
    kill -KILL "${me}" 2>/dev/null
  ) >/dev/null 2>&1 &
}

rm -f "${holders}"
trap 'cleanup' EXIT

# ---- 啟動：持有 record.lock、寫共用狀態檔與 record.pid、等 SIGTERM ----
rec_ready="${home}/.fake_bg_${run}.rec.ready"
rm -f "${rec_ready}"
start_holder "${home}/record.lock" now "${rec_ready}"
rec_holder="${holder_pid}"
wait_ready "${rec_ready}" || true
write_state "${shared}" recording 0 "" 0 0
echo "$$" > "${home}/record.pid"
for _ in $(seq 1 6000); do  # 最多 600 秒後自行結束，避免殘留
  [[ "${got_term}" -eq 1 ]] && break
  sleep 0.1
done
if [[ "${got_term}" -ne 1 ]]; then
  stop_holder "${rec_holder}"
  [[ "$(cat "${home}/record.pid" 2>/dev/null)" == "$$" ]] && rm -f "${home}/record.pid"
  exit 0
fi

# ---- §3.23 第 2 步：每場鎖 ----
mkdir -p "${fin_dir}"
bg_ready="${home}/.fake_bg_${run}.bg.ready"
rm -f "${bg_ready}"
start_holder "${bg_lock}" now "${bg_ready}"
wait_ready "${bg_ready}" || { echo "fake_bg_finalizer.sh：取不到每場鎖" >&2; exit 1; }
# ---- 第 3–4 步：每場狀態檔＋共用狀態檔（仍持有 record.lock，無條件寫）----
write_state "${bg_status}" finalizing 0 "收尾排隊中" 1 1
copy_shared
# ---- 第 5 步：record.pid 是自己才刪 ----
[[ "$(tr -cd '0-9' < "${home}/record.pid" 2>/dev/null)" == "$$" ]] && rm -f "${home}/record.pid"
# ---- 第 6 步：清理 ----
prune
# ---- 第 7 步：放開開錄鎖 ----
stop_holder "${rec_holder}"
if [[ -n "${FAKE_CRASH:-}" ]]; then
  crash_timer "${FAKE_CRASH}"
fi

# ---- 第 9 步：排隊鎖（每 0.5 秒試一次）----
q_ready="${home}/.fake_bg_${run}.queue.ready"
rm -f "${q_ready}"
start_holder "${home}/finalize.queue.lock" poll "${q_ready}"
wait_ready "${q_ready}" || exit 1
# ---- 第 10 步：取得排隊鎖 → 收尾中 ----
event start
write_state "${bg_status}" finalizing 0 "收尾中" 1 0
shared_if_writable
nap "${FAKE_FINALIZE_SECONDS:-2}"
# ---- 第 11 步：最終狀態 ----
code="${FAKE_STOP_CODE:-0}"
if [[ "${code}" == "0" ]]; then
  write_state "${bg_status}" done 0 "已完成（替身）" 1 0
else
  write_state "${bg_status}" failed "${code}" "收尾失敗（替身）" 1 0
fi
shared_if_writable
event end
exit 0

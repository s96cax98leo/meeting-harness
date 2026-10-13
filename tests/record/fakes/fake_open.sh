#!/usr/bin/env bash
# fake_open.sh —— MH_RECORD_OPEN 的替身（測試用，絕不啟動真的 MeetingRecorder）
#
# 呼叫方式與 open 相同，例如：
#   fake_open.sh -n -a <app> --args preflight --window 1 --session <dir> --run-id <uuid> --home <dir> …
#
# 1) 每次被呼叫都把 argv[1:] 逐次附加到 FAKE_OPEN_CALLS（預設 $MH_RECORD_HOME/fake_open.calls）：
#    格式為 <參數個數>\0<參數1>\0<參數2>\0…，可完整還原每個參數的邊界（tests/record/_helpers.py:read_calls）。
# 2) 依 --args 之後的子指令與 FAKE_SCENARIO 模擬 app 的輸出：
#    windows／diagnose-windows：把 FAKE_WINDOWS_JSON（檔案路徑或 JSON 字串；未設為 []）寫進 --log 指的檔
#    preflight／start：在 --home（沒有就用 MH_RECORD_HOME）寫 record.status.json（tmp＋rename），runId＝--run-id
#      recording        preflight → phase=done code=0；start → phase=recording code=0（pid＝呼叫者）
#      warn_only        同 recording，但 preflight 陣列含 power（warn）失敗
#      preflight_fail_4 phase=preflight_failed code=4（screen_permission 失敗）
#      window_missing_3 phase=preflight_failed code=3（window_exists 失敗）
#      collision_2      phase=preflight_failed code=2（session_collision 失敗）
#      stream_died_5    start → phase=failed code=5；preflight → 同 recording
#      stale_status     寫一份 runId 不相符的 phase=done code=0（record.sh 應忽略）
#      no_status        什麼都不寫（windows 也不寫 --log），模擬權限問題
# 結束碼一律 0（真的 open 不回傳 app 的結束碼）。
set -uo pipefail

home="${MH_RECORD_HOME:-}"
calls="${FAKE_OPEN_CALLS:-}"
if [[ -z "${calls}" ]]; then
  [[ -n "${home}" ]] || { echo "fake_open.sh：沒有 FAKE_OPEN_CALLS 也沒有 MH_RECORD_HOME，拒絕寫到真的家目錄" >&2; exit 97; }
  calls="${home}/fake_open.calls"
fi
mkdir -p "$(dirname "${calls}")"
printf '%s\0' "$#" "$@" >> "${calls}"

exec python3 - "$@" <<'PY'
import json, os, sys, tempfile, time

argv = sys.argv[1:]
app = argv[argv.index("--args") + 1:] if "--args" in argv else []
sub = app[0] if app else ""

def val(flag):
    if flag in app:
        i = app.index(flag)
        if i + 1 < len(app):
            return app[i + 1]
    return None

scenario = os.environ.get("FAKE_SCENARIO", "recording")
home = val("--home") or os.environ.get("MH_RECORD_HOME")

def windows_payload():
    src = os.environ.get("FAKE_WINDOWS_JSON")
    if not src:
        return "[]\n"
    if os.path.isfile(src):
        return open(src, encoding="utf-8").read()
    return src

if sub in ("windows", "diagnose-windows"):
    log = val("--log")
    if scenario != "no_status" and log:
        os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
        with open(log, "w", encoding="utf-8") as f:
            f.write(windows_payload())
    sys.exit(0)

if sub not in ("preflight", "start") or scenario == "no_status":
    sys.exit(0)
if not home:
    sys.stderr.write("fake_open.sh：沒有 --home 也沒有 MH_RECORD_HOME\n")
    sys.exit(97)

ITEMS = ["signing", "screen_permission", "relaunch_needed", "mic_permission", "system_audio_rms",
         "mic_rms", "disk", "window_exists", "session_collision", "power", "already_running",
         "window_minimized", "apple_events"]
WARN = {"signing", "power", "window_minimized", "apple_events"}
FAIL = {"preflight_fail_4": ("screen_permission", 4, "沒有螢幕錄製權限（範例訊息）"),
        "window_missing_3": ("window_exists", 3, "找不到要錄的視窗（範例訊息）"),
        "collision_2": ("session_collision", 2, "場次已存在（範例訊息）")}

def results(failed=None, warn_fail=None):
    out = []
    for it in ITEMS:
        sev = "warn" if it in WARN else "hard"
        ok, code, msg = True, 0, ""
        if failed and it == failed[0]:
            ok, code, msg = False, failed[1], failed[2]
        if warn_fail and it == warn_fail[0]:
            ok, msg = False, warn_fail[1]
        out.append({"item": it, "ok": ok, "severity": sev, "code": code, "message": msg})
    return out

now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
st = {"schemaVersion": 1, "runId": val("--run-id") or "", "pid": os.getppid(), "phase": "done",
      "code": 0, "message": "", "session": val("--session") or "", "startedAt": now, "updatedAt": now,
      "segments": 0, "preflight": results(), "warnings": []}

if scenario in FAIL:
    f = FAIL[scenario]
    st.update(phase="preflight_failed", code=f[1], message=f[2], preflight=results(failed=f))
elif scenario == "warn_only":
    st["preflight"] = results(warn_fail=("power", "用電池且電量低於 20%（範例訊息）"))
    if sub == "start":
        st.update(phase="recording")
elif scenario == "stale_status":
    st.update(runId="stale-" + (val("--run-id") or "x"))
    if sub == "start":
        st.update(phase="recording")
elif scenario == "stream_died_5" and sub == "start":
    st.update(phase="failed", code=5, message="串流中斷，已落盤的段落保留（範例訊息）")
elif sub == "start":
    st.update(phase="recording")

os.makedirs(home, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=home, prefix=".record.status.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(st, fh, ensure_ascii=False)
os.replace(tmp, os.path.join(home, "record.status.json"))
PY

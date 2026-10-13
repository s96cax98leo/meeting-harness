#!/usr/bin/env bash
# fake_recorder.sh —— 模擬「正在錄製的 MeetingRecorder 實例」（給 record stop／status 測試用）
#
# 啟動後：在 MH_RECORD_HOME 寫 record.pid（自己的 pid）與 record.status.json（phase=recording），
# 收到 SIGTERM 時依 FAKE_STOP_CODE（預設 0）寫 phase=done code=0 或 phase=failed code=<碼>，
# 刪 record.pid 後結束。FAKE_SESSION 為場次目錄；FAKE_WARNINGS 為 warnings 的 JSON 陣列（選用）。
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
fd, tmp = tempfile.mkstemp(dir=home, prefix=".record.status.", suffix=".tmp")
with os.fdopen(fd, "w", encoding="utf-8") as fh:
    json.dump(st, fh, ensure_ascii=False)
os.replace(tmp, os.path.join(home, "record.status.json"))
PY
}

on_term() {
  local code="${FAKE_STOP_CODE:-0}"
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

write_status recording 0 ""
echo "$$" > "${home}/record.pid"
# 等 SIGTERM；最多 120 秒後自行結束，避免殘留
for _ in $(seq 1 1200); do sleep 0.1; done
rm -f "${home}/record.pid"
exit 0

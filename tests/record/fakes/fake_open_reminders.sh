#!/usr/bin/env bash
# fake_open_reminders.sh —— `meeting reminders` 的 MH_RECORD_OPEN 替身（R3，spec §4.34.2；絕不啟動真的 MeetingRecorder）
#
# 呼叫方式與 open 相同：fake_open_reminders.sh -W -n -a <app> --args reminders --input <json> --list <名稱>
# 1) argv[1:] 以 fake_open.sh 相同的格式（<參數個數>\0<參數1>\0…）附加到 FAKE_OPEN_CALLS（tests/record/_helpers.py:read_calls）。
# 2) FAKE_REMINDERS_CODE 有值時，把 {"code", "created", "updated", "message"} 寫到 <--input>.result.json（tmp＋rename）；
#    未設時不寫結果檔（模擬 app 沒有回報，meeting reminders 應回 5）。
# 3) 把 --input 檔的內容複製到 <FAKE_OPEN_CALLS>.input.json，供測試比對交給 app 的項目。
# 結束碼一律 0（真的 open -W 不回傳 app 的結束碼）。
set -uo pipefail

calls="${FAKE_OPEN_CALLS:-}"
[[ -n "${calls}" ]] || { echo "fake_open_reminders.sh：沒有 FAKE_OPEN_CALLS，拒絕寫檔" >&2; exit 97; }
mkdir -p "$(dirname "${calls}")"
printf '%s\0' "$#" "$@" >> "${calls}"

exec python3 - "${calls}" "$@" <<'PY'
import json, os, shutil, sys, tempfile

calls, argv = sys.argv[1], sys.argv[2:]
inp = argv[argv.index("--input") + 1] if "--input" in argv and argv.index("--input") + 1 < len(argv) else None
if inp and os.path.isfile(inp):
    shutil.copyfile(inp, calls + ".input.json")
code = os.environ.get("FAKE_REMINDERS_CODE")
if inp and code not in (None, ""):
    items = json.load(open(inp, encoding="utf-8")) if os.path.isfile(inp) else []
    res = {"code": int(code), "created": len(items) if code == "0" else 0, "updated": 0,
           "message": "fake reminders 範例"}
    d = os.path.dirname(os.path.abspath(inp))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".fake-result-")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    os.replace(tmp, inp + ".result.json")
sys.exit(0)
PY

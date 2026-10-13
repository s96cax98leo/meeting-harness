#!/usr/bin/env python3
"""_record_prompt.py --windows-json <檔> --defaults <檔>

meeting record 開錄前的問答（spec §3.7）。依序問：根目錄、場次名、會議型態、出席者、要錄的視窗。
- 提示一律印到 stderr；最後在 stdout 印一行 JSON：
  {"root","session","type","attendees","windowID","bundleID","title"}
- 任何情況都不寫檔（record.defaults.json、meeting.json 由 record.sh 寫）。
- 使用者中斷（EOF／Ctrl-C）回 2；視窗清單是空的回 3。

視窗選單：照 --windows-json 陣列原順序（app 已依 spec §3.8.5 排好）每列印「<序號>) <label>」，
label 逐字照印、不自行組字；預設＝第一個 meeting 非 null 的列（★）；沒有 ★ 列就沒有預設，
空白輸入重問。型態選項取自 _profile.PROFILES（同目錄 import），不另抄清單。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _profile import DEFAULT_TYPE, PROFILES  # noqa: E402

AUTOMATION_NOTE = ("  註：Chrome 視窗沒有會議標記（★），是因為沒有允許 MeetingRecorder 控制 Chrome"
                   "（選用；系統設定 › 隱私權與安全性 › 自動化），不允許也能錄。")


class Abort(Exception):
    """使用者中斷（EOF／Ctrl-C）。"""


def say(text=""):
    sys.stderr.write(text + "\n")
    sys.stderr.flush()


def ask(prompt):
    sys.stderr.write(prompt)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if line == "":
        raise Abort()
    return line.strip()


def load_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return fallback


def with_default(label, default):
    return f"{label} [預設 {default}]：" if default not in (None, "") else f"{label}："


def ask_root(default):
    if default and not os.path.isdir(default):
        default = None
    while True:
        ans = ask(with_default("會議根目錄", default)) or (default or "")
        if not ans:
            say("  要輸入會議根目錄。")
            continue
        path = os.path.abspath(os.path.expanduser(ans))
        if os.path.isdir(path):
            return path
        say(f"  找不到這個目錄：{path}")


def ask_session():
    default = time.strftime("%H%M") + " 會議"
    while True:
        ans = ask(with_default("場次名", default)) or default
        if "/" in ans or ans in (".", ".."):
            say("  場次名不能含「/」。")
            continue
        return ans


def ask_type(default):
    types = list(PROFILES)
    if default not in PROFILES:
        default = DEFAULT_TYPE
    say("會議型態：" + "、".join(f"{i}) {t}" for i, t in enumerate(types, start=1)))
    while True:
        ans = ask(with_default("會議型態（序號或名稱）", default)) or default
        if ans in PROFILES:
            return ans
        if ans.isdigit() and 1 <= int(ans) <= len(types):
            return types[int(ans) - 1]
        say(f"  不是可用的型態：{ans}")


def names_of(attendees):
    out = []
    for a in attendees if isinstance(attendees, list) else []:
        n = a.get("name") if isinstance(a, dict) else a
        if isinstance(n, str) and n.strip():
            out.append(n.strip())
    return out


def ask_attendees(default):
    shown = "、".join(default)
    ans = ask(with_default("出席者（以「、」或逗號分隔，可留空）", shown))
    names = default if ans == "" else [x.strip() for x in ans.replace("，", "、").replace(",", "、").split("、")]
    return [{"name": n} for n in names if n]


def ask_window(rows):
    say("要錄哪個視窗：")
    for i, r in enumerate(rows, start=1):
        say(f"  {i}) {r.get('label', '')}")
    if any(r.get("meetingCheck") in ("not_authorized", "not_determined") for r in rows):
        say(AUTOMATION_NOTE)
    star = next((i for i, r in enumerate(rows, start=1) if r.get("meeting") is not None), None)
    prompt = f"輸入序號 [預設 {star}]：" if star else "輸入序號："
    while True:
        ans = ask(prompt)
        if ans == "" and star:
            return rows[star - 1]
        if ans.isdigit() and 1 <= int(ans) <= len(rows):
            return rows[int(ans) - 1]
        if ans:
            say(f"  要輸入 1–{len(rows)} 的序號。")


def main(argv=None):
    ap = argparse.ArgumentParser(description="meeting record 開錄前的問答")
    ap.add_argument("--windows-json", required=True)
    ap.add_argument("--defaults", required=True)
    a = ap.parse_args(argv)
    rows = load_json(a.windows_json, [])
    if not isinstance(rows, list) or not rows:
        say("✗ 沒有可以錄的視窗（清單是空的）。先開好會議視窗，或跑 meeting record windows 看看。")
        return 3
    d = load_json(a.defaults, {})
    if not isinstance(d, dict):
        d = {}
    try:
        root = ask_root(d.get("root"))
        session = ask_session()
        mtype = ask_type(d.get("type"))
        attendees = ask_attendees(names_of(d.get("attendees")))
        w = ask_window(rows)
    except (Abort, KeyboardInterrupt):
        say("\n已取消。")
        return 2
    print(json.dumps({"root": root, "session": session, "type": mtype, "attendees": attendees,
                      "windowID": w.get("windowID"), "bundleID": w.get("bundleID", ""),
                      "title": w.get("title", "")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

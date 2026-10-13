#!/usr/bin/env python3
"""_reminders.py — meeting reminders <場次> --list <名稱> [--dry-run]（spec §3.19、§4.34；R3-§2.2）。

- 讀 <場次>/meeting.record.json 的 actions[]，組出項目 {uid, title, notes, due, url}：
  - uid＝f"{meeting.get('id', meeting['title'])}-{aid}@meeting-harness"，與 _render.py 寫的 actions.ics 的 UID 相同；
    aid＝交辦的 id，沒有時依序 A-01、A-02…（同 actions.ics、actions.csv）。
  - title＝交辦內容；notes＝「負責人：<owner 或（未定）>」＋場次名；due＝期限（缺值 null，不補猜，鐵則 2）；
  - url＝meetingharness://action/<uid>（app 以它去重，重跑不重複寫入）。
- --dry-run：印 JSON 陣列、回 0，不啟動 app。
- 否則以 `open -W -n -a <app> --args reminders --input <暫存 json> --list <名稱>` 交給 app（MH_RECORD_OPEN 可換替身），
  以 app 寫的 <暫存>.result.json 的 code 為結束碼；沒有結果檔回 5。

結束碼：0 寫入完成（或 --dry-run 印完）；2 缺參數、場次沒有 meeting.record.json、app 未建置；
3 指定的提醒事項清單不存在；4 提醒事項權限被拒；5 寫入失敗（重跑會去重）。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

UNSET = "（未定）"
URL_PREFIX = "meetingharness://action/"
KNOWN_CODES = (0, 3, 4, 5)


def usage():
    print("用法：meeting reminders <場次目錄> --list <提醒事項清單名稱> [--dry-run]", file=sys.stderr)


def parse_args(argv):
    """回傳 (場次, 清單名稱, dry_run)；參數不對回 None。"""
    sess, name, dry = None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--dry-run":
            dry = True
        elif a == "--list":
            if i + 1 >= len(argv) or not argv[i + 1]:
                return None
            name = argv[i + 1]
            i += 1
        elif a.startswith("-"):
            return None
        elif sess is None:
            sess = a
        else:
            return None
        i += 1
    if not sess or not name:
        return None
    return sess, name, dry


def build_items(rec, sess_name):
    """依 meeting.record.json 組出提醒事項項目（uid 規則與 _render.py render_actions_ics 相同）。"""
    m = rec["meeting"]
    base = m.get("id", m["title"])
    items = []
    for i, a in enumerate(rec.get("actions") or [], 1):
        aid = a.get("id") or f"A-{i:02d}"
        uid = f"{base}-{aid}@meeting-harness"
        due = a.get("due")
        items.append({
            "uid": uid,
            "title": a["title"],
            "notes": f"負責人：{a.get('owner') or UNSET}\n場次：{sess_name}",
            "due": due if due else None,
            "url": URL_PREFIX + uid,
        })
    return items


def load_record(sess):
    path = os.path.join(sess, "meeting.record.json")
    if not os.path.isfile(path):
        print(f"✗ 場次沒有 meeting.record.json：{sess}", file=sys.stderr)
        return None
    try:
        with open(path, encoding="utf-8") as f:
            rec = json.load(f)
        if not isinstance(rec, dict) or not isinstance(rec.get("meeting"), dict):
            raise ValueError("缺 meeting 物件")
        return rec
    except (OSError, ValueError) as e:
        print(f"✗ 讀不了 meeting.record.json：{e}", file=sys.stderr)
        return None


def open_cmd(app, inp, name):
    tail = ["-W", "-n", "-a", app, "--args", "reminders", "--input", inp, "--list", name]
    opener = os.environ.get("MH_RECORD_OPEN")
    if opener:
        # 與 record.sh 相同：替身可執行就直接跑，否則交給 bash
        return ([opener] if os.access(opener, os.X_OK) else ["bash", opener]) + tail
    return ["open"] + tail


def run_app(items, name):
    app = os.environ.get("MH_RECORDER_APP") or os.path.expanduser("~/Applications/MeetingRecorder.app")
    if not os.path.isdir(app):
        print(f"✗ 錄製器 app 未建置：{app}（bash tools/MeetingRecorder/build.sh）", file=sys.stderr)
        return 2
    work = tempfile.mkdtemp(prefix="mh-reminders-")
    try:
        inp = os.path.join(work, "items.json")
        with open(inp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        res_path = inp + ".result.json"
        try:
            subprocess.run(open_cmd(app, inp, name), check=False)
        except OSError as e:
            print(f"✗ 無法啟動 app：{e}", file=sys.stderr)
            return 5
        if not os.path.isfile(res_path):
            print("✗ app 沒有寫回結果檔（寫入失敗；重跑會去重）", file=sys.stderr)
            return 5
        try:
            with open(res_path, encoding="utf-8") as f:
                res = json.load(f)
            code = int(res.get("code"))
        except (OSError, ValueError, TypeError, AttributeError) as e:
            print(f"✗ 結果檔格式不對：{e}", file=sys.stderr)
            return 5
        msg = res.get("message") or ""
        if code == 0:
            print(f"✓ 已寫入提醒事項「{name}」：新增 {res.get('created', 0)}、更新 {res.get('updated', 0)}")
        else:
            print(f"✗ {msg}" if msg else f"✗ 提醒事項寫入失敗（code {code}）", file=sys.stderr)
        return code if code in KNOWN_CODES else 5
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv):
    parsed = parse_args(argv)
    if parsed is None:
        usage()
        return 2
    sess, name, dry = parsed
    if not os.path.isdir(sess):
        print(f"✗ 場次目錄不存在：{sess}", file=sys.stderr)
        return 2
    rec = load_record(sess)
    if rec is None:
        return 2
    sess_name = os.path.basename(os.path.normpath(os.path.abspath(sess)))
    try:
        items = build_items(rec, sess_name)
    except (KeyError, TypeError) as e:
        print(f"✗ meeting.record.json 的交辦格式不對：{e}", file=sys.stderr)
        return 2
    if dry:
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return 0
    return run_app(items, name)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

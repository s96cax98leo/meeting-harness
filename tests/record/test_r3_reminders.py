"""meeting reminders（spec §4.34.1、§4.34.2；R3-§2.2、§3.19）。

非 dry-run 時 MH_RECORD_OPEN 指向 fakes/fake_open_reminders.sh（記參數、依 FAKE_REMINDERS_CODE 寫結果檔；絕不啟動 app）。
素材只在 TMPDIR；清單名稱用「範例清單」。
"""
import json
import re
import unittest
from pathlib import Path

from tests.record import _fixtures as fx
from tests.record._helpers import BIN, FAKES, Sandbox, read_calls

FAKE_OPEN_REMINDERS = FAKES / "fake_open_reminders.sh"
RENDER_PY = BIN / "_render.py"
LIST = "範例清單"
ACTIONS = [{"title": "範例交辦：整理需求清單", "owner": "範例甲", "due": "2026-10-20"},
           {"title": "範例交辦：確認測試環境"},
           {"id": "A-09", "title": "範例交辦三", "owner": "範例乙"}]


def make_session(root, *, record=True):
    sess = Path(root) / "20261011-範例專案"
    (sess / "錄音").mkdir(parents=True)
    if record:
        rec = fx.meeting_record(actions=ACTIONS)
        (sess / "meeting.record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return sess


def ics_uids(sb, sess):
    r = sb.run(["python3", RENDER_PY, sess, "--actions"])
    assert r.returncode == 0, r.stderr
    return re.findall(r"^UID:(.+?)\r?$", (sess / "actions.ics").read_text(encoding="utf-8"), re.M)


class TestR3Reminders(unittest.TestCase):
    def dry_run(self):
        sb = Sandbox(self)
        sess = make_session(sb.root)
        r = sb.meeting("reminders", sess, "--list", LIST, "--dry-run")
        return sb, sess, r

    # spec §4.34.1：--dry-run 印項目陣列、回 0、不呼叫 app；缺負責人「負責人：（未定）」、缺期限 due null
    def test_dry_run_items(self):
        sb, sess, r = self.dry_run()
        self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual(sb.read_calls(), [], "--dry-run 不得呼叫 app")
        items = json.loads(r.stdout)
        self.assertIsInstance(items, list)
        self.assertEqual(len(items), 3)
        mid = fx.meeting_record()["meeting"]["id"]
        for it, a, aid in zip(items, ACTIONS, ("A-01", "A-02", "A-09")):
            self.assertEqual(set(it), {"uid", "title", "notes", "due", "url"}, it)
            self.assertEqual(it["uid"], f"{mid}-{aid}@meeting-harness")
            self.assertEqual(it["title"], a["title"])
            self.assertEqual(it["url"], "meetingharness://action/" + it["uid"])
            self.assertIn(sess.name, it["notes"], "notes 含場次名")
            self.assertIn(f"負責人：{a.get('owner') or '（未定）'}", it["notes"])
            self.assertEqual(it["due"], a.get("due"), "缺期限時為 null，不補猜")

    # spec §4.34.1：uid 與同一場 actions.ics 的 UID: 完全相同
    def test_uid_matches_ics(self):
        sb, sess, r = self.dry_run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual([it["uid"] for it in json.loads(r.stdout)], ics_uids(sb, sess))

    # spec §4.34.2：以 open -W -n -a <app> --args reminders --input … --list … 呼叫；結果檔 code 為結束碼；沒有結果檔 5；
    # 場次沒有 meeting.record.json 回 2
    def test_invokes_app_and_maps_code(self):
        for code, want in (("0", 0), ("3", 3), ("4", 4), ("5", 5), (None, 5)):
            with self.subTest(result_code=code):
                sb = Sandbox(self)
                sess = make_session(sb.root)
                env = {"MH_RECORD_OPEN": FAKE_OPEN_REMINDERS}
                if code is not None:
                    env["FAKE_REMINDERS_CODE"] = code
                r = sb.meeting("reminders", sess, "--list", LIST, **env)
                self.assertEqual(r.returncode, want, f"stdout:{r.stdout}\nstderr:{r.stderr}")
                calls = sb.read_calls()
                self.assertEqual(len(calls), 1, "應恰呼叫 app 一次")
                c = calls[0]
                self.assertIn("-W", c[:c.index("--args")] if "--args" in c else c)
                self.assertIn("-n", c)
                self.assertEqual(c[c.index("-a") + 1], str(sb.app))
                self.assertEqual(c[c.index("--args") + 1], "reminders")
                self.assertEqual(c[c.index("--list") + 1], LIST)
                self.assertIn("--input", c)
                sent = json.loads(Path(str(sb.calls) + ".input.json").read_text(encoding="utf-8"))
                self.assertEqual([it["title"] for it in sent], [a["title"] for a in ACTIONS])
        sb = Sandbox(self)
        sess = make_session(sb.root, record=False)
        r = sb.meeting("reminders", sess, "--list", LIST, MH_RECORD_OPEN=FAKE_OPEN_REMINDERS)
        self.assertEqual(r.returncode, 2, "場次沒有 meeting.record.json 回 2")
        self.assertEqual(read_calls(sb.calls), [], "不得呼叫 app")


if __name__ == "__main__":
    unittest.main()

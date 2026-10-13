"""R2：meeting record pause／resume／mute／unmute／mark、status、stop 摘要（spec R2-§2.2、§4.16.5–§4.16.9、§4.16.11）。

錄製器一律以 fakes/fake_recorder.sh（FAKE_CONTROL）與 fakes/fake_open.sh 替身；不開真的 app、不送訊號給真的錄製器。
所有命令在沒有 record/ 的暫存工作目錄、MH_RECORD_HOME＝暫存目錄下執行。
"""
import datetime
import json
import os
import re
import subprocess
import time
import unittest

from tests.record import _fixtures as fx
from tests.record import _media as m
from tests.record._helpers import FAKE_RECORDER, UNKNOWN_OPTION, Sandbox, app_args

FORMS = ["pause", "resume", "mute", "unmute", "mark"]


def iso_ago(seconds):
    """現在 − seconds 的 ISO 8601（含時區冒號，同錄製器的 internet date time）。"""
    t = datetime.datetime.now().astimezone() - datetime.timedelta(seconds=seconds)
    return t.isoformat(timespec="seconds")


def start_fake(tc, sb, *, control=None, phase=None, session=None, extra=None, run_id=None):
    """啟動 fake_recorder.sh 並等它寫出 record.pid；回傳 Popen。"""
    env = {}
    if control is not None:
        env["FAKE_CONTROL"] = control
    if phase is not None:
        env["FAKE_PHASE"] = phase
    if session is not None:
        env["FAKE_SESSION"] = str(session)
    if extra is not None:
        env["FAKE_STATUS_EXTRA"] = json.dumps(extra, ensure_ascii=False)
    if run_id is not None:
        env["FAKE_RUN_ID"] = run_id
    p = subprocess.Popen(["bash", str(FAKE_RECORDER)], env=sb.env(**env), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tc.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
    deadline = time.monotonic() + 10
    while not ((sb.home / "record.pid").exists() and (sb.home / "record.status.json").exists()):
        if time.monotonic() > deadline:
            raise AssertionError("fake_recorder.sh 沒有寫出 record.pid／record.status.json")
        time.sleep(0.05)
    return p


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def usr1_count(sb):
    p = sb.home / "fake_usr1.count"
    return int(p.read_text().strip() or 0) if p.exists() else 0


class R2CliCase(unittest.TestCase):
    def control(self, sb):
        p = sb.home / "record.control.json"
        self.assertTrue(p.is_file(), "應寫出 <home>/record.control.json")
        return read_json(p)

    def status(self, sb):
        return read_json(sb.home / "record.status.json")

    def run_ok(self, sb, word):
        r = sb.meeting("record", word, timeout=60)
        self.assertEqual(r.returncode, 0, f"record {word} 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue((sb.home / "record.control.lock").exists(), f"record {word} 之後應有 record.control.lock")
        return r


class TestR2Control(R2CliCase):
    # spec §4.16.5
    def test_control_commands_with_fake_recorder(self):
        sb = Sandbox(self)
        start_fake(self, sb, control="1")
        r = self.run_ok(sb, "pause")
        self.assertIn("已暫停", r.stdout)
        ctl, st = self.control(sb), self.status(sb)
        self.assertEqual(set(ctl), {"schemaVersion", "runId", "paused", "micMuted", "markerSeq"}, "控制檔鍵恰為 5 個（§3.9）")
        self.assertIs(ctl["paused"], True)
        self.assertEqual(ctl["runId"], st["runId"], "控制檔 runId 應等於狀態檔的 runId")
        self.assertEqual(ctl["schemaVersion"], 1)
        self.assertEqual(usr1_count(sb), 1, "替身應恰收到 1 次 SIGUSR1")
        self.assertIs(st.get("paused"), True)
        steps = [("resume", "paused", False, "已繼續錄製"), ("mute", "micMuted", True, "麥克風已靜音"),
                 ("unmute", "micMuted", False, "麥克風已取消靜音")]
        for word, key, want, text in steps:
            with self.subTest(word=word):
                r = self.run_ok(sb, word)
                self.assertIn(text, r.stdout)
                ctl, st = self.control(sb), self.status(sb)
                self.assertIs(ctl[key], want, f"{word} 後控制檔 {key}")
                self.assertIs(st.get(key), want, f"{word} 後狀態檔 {key}（5 秒內反映）")
                self.assertEqual(ctl["runId"], st["runId"])
        self.assertEqual(usr1_count(sb), 4)

    # spec §4.16.5、R2-§2.2：本來就是目標狀態時不送訊號、直接回 0
    def test_control_idempotent_no_signal(self):
        sb = Sandbox(self)
        start_fake(self, sb, control="1")
        r = self.run_ok(sb, "resume")
        self.assertIn("本來就在錄製中", r.stdout)
        r = self.run_ok(sb, "unmute")
        self.assertIn("麥克風本來就沒有靜音", r.stdout)
        self.assertEqual(usr1_count(sb), 0, "本來就是目標狀態時不得送訊號")
        self.run_ok(sb, "pause")
        n = usr1_count(sb)
        self.assertEqual(n, 1)
        r = self.run_ok(sb, "pause")
        self.assertIn("已經是暫停中", r.stdout)
        self.assertEqual(usr1_count(sb), n, "第二次 pause 不得再送訊號")
        self.run_ok(sb, "mute")
        n = usr1_count(sb)
        r = self.run_ok(sb, "mute")
        self.assertIn("麥克風本來就是靜音", r.stdout)
        self.assertEqual(usr1_count(sb), n, "第二次 mute 不得再送訊號")

    # spec §4.16.5
    def test_mark_increments(self):
        sb = Sandbox(self)
        start_fake(self, sb, control="1")
        r1 = self.run_ok(sb, "mark")
        self.assertIn("已加標記 1", r1.stdout)
        r2 = self.run_ok(sb, "mark")
        self.assertIn("已加標記 2", r2.stdout)
        self.assertEqual(self.control(sb)["markerSeq"], 2)
        self.assertEqual(self.status(sb).get("markers"), 2)
        self.assertEqual(usr1_count(sb), 2)

    # spec §4.16.6
    def test_control_unavailable_exit_3(self):
        cases = [(None, "沒有錄製在跑"), ("preflight", "還在開錄前檢查"), ("stopping", "正在收尾"),
                 ("finalizing", "正在收尾")]
        for phase, text in cases:
            for word in FORMS:
                with self.subTest(phase=phase or "沒有 record.pid", word=word):
                    sb = Sandbox(self)
                    if phase is not None:
                        start_fake(self, sb, control="1", phase=phase)
                    ctl = sb.home / "record.control.json"
                    before = json.dumps({"schemaVersion": 1, "runId": "fake-run", "paused": False,
                                         "micMuted": False, "markerSeq": 0})
                    ctl.write_text(before, encoding="utf-8")
                    r = sb.meeting("record", word, timeout=60)
                    self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
                    self.assertIn(text, r.stderr)
                    self.assertEqual(ctl.read_text(encoding="utf-8"), before, "回 3 時不得改控制檔")
                    self.assertEqual(usr1_count(sb), 0)

    # spec §4.16.6：舊版錄製器（狀態檔沒有 controlVersion、沒裝 SIGUSR1 處理）不得被訊號殺掉
    def test_old_recorder_not_signalled(self):
        sb = Sandbox(self)
        p = start_fake(self, sb)
        self.assertNotIn("controlVersion", self.status(sb), "替身前提：舊版狀態檔沒有 controlVersion")
        for word in FORMS:
            with self.subTest(word=word):
                r = sb.meeting("record", word, timeout=60)
                self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
                self.assertIn("舊版錄製器", r.stderr)
                time.sleep(0.3)
                self.assertIsNone(p.poll(), "舊版錄製器不得被 SIGUSR1 殺掉")

    # spec §4.16.7
    def test_control_no_response_exit_3(self):
        sb = Sandbox(self)
        p = start_fake(self, sb, control="ignore")
        t0 = time.monotonic()
        r = sb.meeting("record", "pause", timeout=60)
        elapsed = time.monotonic() - t0
        self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("沒有回應", r.stderr)
        self.assertGreaterEqual(elapsed, 5, "應等滿 5 秒才判定沒有回應")
        self.assertLessEqual(elapsed, 10, "最多 10 秒內回 3")
        self.assertIsNone(p.poll())

    # spec §4.16.8
    def test_control_extra_args_exit_2(self):
        sb = Sandbox(self)
        start_fake(self, sb, control="1")
        for word in FORMS:
            with self.subTest(word=word, extra="x"):
                r = sb.meeting("record", word, "x", timeout=60)
                self.assertEqual(r.returncode, 2, f"stdout:{r.stdout}\nstderr:{r.stderr}")
            with self.subTest(word=word, extra="--no-such-flag"):
                r = sb.meeting("record", word, "--no-such-flag", timeout=60)
                self.assertEqual(r.returncode, 2, f"stdout:{r.stdout}\nstderr:{r.stderr}")
                self.assertIn(UNKNOWN_OPTION, r.stderr)
        self.assertEqual(usr1_count(sb), 0, "參數錯誤時不得送訊號")
        self.assertFalse(self.status(sb).get("paused"), "參數錯誤時不得改狀態")

    # spec §4.16.8：保留字的 ./ 寫法走開錄流程
    def test_reserved_words_dot_slash_root(self):
        for word in FORMS:
            with self.subTest(word=word):
                sb = Sandbox(self, scenario="recording", windows=fx.WINDOWS_WITH_STAR)
                (sb.cwd / word).mkdir()
                r = sb.meeting("record", f"./{word}", "--window", "41001", timeout=180)
                calls = [app_args(c) for c in sb.read_calls()]
                self.assertTrue(any(c[:1] in (["start"], ["preflight"]) for c in calls),
                                f"./{word} 應走開錄流程（替身應收到 start 或 preflight）：{calls}\n"
                                f"stdout:{r.stdout}\nstderr:{r.stderr}")
                self.assertFalse((sb.home / "record.control.json").exists(), f"./{word} 不得走控制流程")


class TestR2StatusStop(R2CliCase):
    # spec §4.16.9
    def test_status_shows_pause_mute_markers(self):
        sb = Sandbox(self)
        start_fake(self, sb, control="1",
                   extra={"recordingStartedAt": iso_ago(125), "pausedSeconds": 5.0})
        r = sb.meeting("record", "status", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        mo = re.search(r"錄製中 (\d\d):(\d\d)", r.stdout)
        self.assertIsNotNone(mo, f"應印「錄製中 mm:ss」：{r.stdout}")
        secs = int(mo.group(1)) * 60 + int(mo.group(2))
        self.assertTrue(119 <= secs <= 121, f"計時應為 02:00（±1 秒，扣 pausedSeconds 5）：{mo.group(0)}")
        for k in ("暫停中", "麥克風靜音中", "標記"):
            self.assertNotIn(k, r.stdout, f"沒有暫停／靜音／標記時不印「{k}」")

        sb = Sandbox(self)
        start_fake(self, sb, control="1",
                   extra={"recordingStartedAt": iso_ago(125), "pausedSeconds": 5.0, "paused": True,
                          "pausedAt": iso_ago(10), "micMuted": True, "markers": 2})
        r = sb.meeting("record", "status", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("暫停中", r.stdout)
        self.assertIn("麥克風靜音中", r.stdout)
        self.assertIn("標記 2 個", r.stdout)

        sb = Sandbox(self)  # 第一輪格式（沒有 R2 鍵）：輸出照第一輪
        start_fake(self, sb)
        r = sb.meeting("record", "status", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertRegex(r.stdout, r"(?m)^錄製中 \d\d:\d\d　場次：")
        for k in ("暫停中", "麥克風靜音中", "標記"):
            self.assertNotIn(k, r.stdout)

    # spec §4.16.11
    def test_stop_summary_pause_markers(self):
        def run_stop(pause_events, markers):
            sb = Sandbox(self)
            sess = m.make_record_session(sb.root, [dict(dur=1.0)])
            meta = sess / "錄音" / "tracks" / "record.meta.json"
            d = read_json(meta)
            if pause_events is not None:
                d["pauseEvents"] = pause_events
                d["micMuteEvents"] = []
            meta.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            extra = {} if markers is None else {"markers": markers}
            start_fake(self, sb, control="1" if pause_events is not None else None, session=sess, extra=extra)
            r = sb.meeting("record", "stop", timeout=180)
            self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
            return r.stdout

        ev = m.pause_events([(70.0, "pause"), (100.0, "resume"), (150.0, "pause")], 0.0)
        out = run_stop(ev, 2)
        self.assertIn("暫停 2 次、共 00:30；標記 2 個", out)
        self.assertEqual(out.count("次、共"), 1, "摘要只多印恰一行")
        out = run_stop([], 1)
        self.assertIn("暫停 0 次、共 00:00；標記 1 個", out)
        out = run_stop(None, None)  # 第一輪：meta 沒有 pauseEvents、狀態檔沒有 markers
        self.assertNotIn("次、共", out)


if __name__ == "__main__":
    unittest.main()

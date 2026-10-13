"""spec §2.4.7、§4.1.4、§4.1.6、§4.1.7、§4.2.3、§4.2.4、§4.5.5、§4.5.6、§4.15.13：bin/record.sh（經 meeting.sh）。

錄製器一律以 MH_RECORD_OPEN＝fakes/fake_open.sh 替身，不開真的 app。
"""
import json
import re
import subprocess
import time
import unittest

from tests.record import _fixtures as fx
from tests.record import _media as m
from tests.record._helpers import (FAILING_FFMPEG, FAKE_RECORDER, MEETING_SH, PromptResponder, Sandbox,
                                   app_args, dead_pid, flag_value, run_pty)
from tests.record.surface import F_FINISH, F_HELP, F_PREFLIGHT, F_ROOT, F_STATUS, F_STOP, F_WINDOWS, SURFACE, form_argv
from tests.record.surface import F_MARK, F_MUTE, F_PAUSE, F_RESUME, F_UNMUTE

W = ["--window", "41001"]


def case(form, expect, scenario=None, setup=None, extra_args=()):
    return {"form": form, "scenario": scenario, "setup": setup, "extra_args": list(extra_args), "expect": expect}


# spec §2.4.7：{(form, expect)} 必須等於 SURFACE.form_codes（32 組）；不含通則的 2（未知選項、./record 撞名）。
EXIT_CODE_CASES = [
    case(F_ROOT, 0, "recording", None, W),
    case(F_ROOT, 2, None, "app_missing", W),
    case(F_ROOT, 2, None, "root_missing", W),
    case(F_ROOT, 2, "recording", None, []),          # 非互動終端又沒有 --window
    case(F_ROOT, 3, "window_missing_3", None, W),
    case(F_ROOT, 4, "preflight_fail_4", None, W),
    case(F_ROOT, 5, "stream_died_5", None, W),
    case(F_WINDOWS, 0, "recording", None, []),
    case(F_WINDOWS, 0, "recording", None, ["--json"]),
    case(F_WINDOWS, 2, None, "app_missing", []),
    case(F_WINDOWS, 4, "no_status", None, ["--json"]),   # 取不到視窗清單（20 秒內沒有輸出）
    case(F_PREFLIGHT, 0, "recording", None, ["--window", "1"]),
    case(F_PREFLIGHT, 2, None, "app_missing", ["--window", "1"]),
    case(F_PREFLIGHT, 2, "recording", None, ["--window"]),   # --window 缺值
    case(F_PREFLIGHT, 3, "window_missing_3", None, ["--window", "1"]),
    case(F_PREFLIGHT, 4, "preflight_fail_4", None, ["--window", "1"]),
    case(F_STOP, 0, None, "running_stop_ok"),
    case(F_STOP, 3, None, None),
    case(F_STOP, 5, None, "running_stop_fails_5"),
    case(F_STATUS, 0, None, None),
    case(F_STATUS, 0, None, "running_stop_ok"),
    case(F_STATUS, 5, None, "crashed"),
    case(F_FINISH, 0, None, "session_with_segments"),
    case(F_FINISH, 2, None, "session_missing"),
    case(F_FINISH, 3, None, "session_no_segments"),
    case(F_FINISH, 5, None, "ffmpeg_fails"),
    case(F_HELP, 0),
    # R2（spec §4.16.5、§4.16.6、§6 第 77 條）：五個寫法 × 0／3；0＝替身以 FAKE_CONTROL=1 錄製中，3＝沒有錄製在跑
    case(F_PAUSE, 0, None, "running_controllable"),
    case(F_RESUME, 0, None, "running_controllable"),
    case(F_MUTE, 0, None, "running_controllable"),
    case(F_UNMUTE, 0, None, "running_controllable"),
    case(F_MARK, 0, None, "running_controllable"),
    case(F_PAUSE, 3, None, None),
    case(F_RESUME, 3, None, None),
    case(F_MUTE, 3, None, None),
    case(F_UNMUTE, 3, None, None),
    case(F_MARK, 3, None, None),
]


def start_fake_recorder(tc, sb, stop_code=0, session=None, warnings=None):
    env = sb.env(FAKE_STOP_CODE=stop_code, FAKE_SESSION=session or "",
                 FAKE_WARNINGS=json.dumps(warnings or [], ensure_ascii=False))
    p = subprocess.Popen(["bash", str(FAKE_RECORDER)], env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tc.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
    deadline = time.monotonic() + 10
    while not (sb.home / "record.pid").exists():
        if time.monotonic() > deadline:
            raise AssertionError("fake_recorder.sh 沒有寫出 record.pid")
        time.sleep(0.05)
    return p


def write_crashed_status(sb, session):
    pid = dead_pid()
    st = {"schemaVersion": 1, "runId": "old-run", "pid": pid, "phase": "recording", "code": 0, "message": "",
          "session": str(session), "startedAt": "2026-10-11T10:00:00+0800",
          "updatedAt": "2026-10-11T10:02:00+0800", "segments": 2, "preflight": [], "warnings": []}
    (sb.home / "record.status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    (sb.home / "record.pid").write_text(f"{pid}\n")


def run_exit_case(tc, c, timeout=180):
    """依 spec §2.4.7 組參數、在替身環境執行一筆 EXIT_CODE_CASES，回傳 CompletedProcess。"""
    setup = c["setup"]
    sb = Sandbox(tc, scenario=c["scenario"] or "recording", windows=fx.WINDOWS_WITH_STAR,
                 app=(setup != "app_missing"))
    root = sb.root if setup != "root_missing" else sb.base / "不存在的根"
    session = sb.base / "不存在的場次"
    env = {}
    if setup in ("session_with_segments", "ffmpeg_fails"):
        session = m.make_record_session(sb.root, [dict(dur=1.0), dict(dur=1.0)])
    elif setup == "session_no_segments":
        session = sb.root / m.DAY / m.SESSION_NAME
        (session / "錄音").mkdir(parents=True)
    elif setup == "running_stop_ok":
        start_fake_recorder(tc, sb, 0)
    elif setup == "running_stop_fails_5":
        start_fake_recorder(tc, sb, 5)
    elif setup == "running_controllable":  # R2 §4.16.5：可控制的錄製實例替身
        sb.extra_env["FAKE_CONTROL"] = "1"
        start_fake_recorder(tc, sb, 0)
    elif setup == "crashed":
        write_crashed_status(sb, sb.root / m.DAY / m.SESSION_NAME)
    elif setup not in (None, "app_missing", "root_missing", "session_missing"):
        raise AssertionError(f"未知的 setup：{setup}")
    if setup == "ffmpeg_fails":
        env["MH_FFMPEG"] = FAILING_FFMPEG
    assert not (sb.cwd / "record").exists()
    argv = form_argv(c["form"], root=root, session=session, extra=c["extra_args"], meeting_sh=str(MEETING_SH))
    return sb.run(argv, timeout=timeout, **env)


class TestRecordSh(unittest.TestCase):
    def test_exit_code_cases_cover_surface(self):
        for c in EXIT_CODE_CASES:
            self.assertEqual(set(c), {"form", "scenario", "setup", "extra_args", "expect"})
            names = {f.split(" ")[0] for form, f in SURFACE.form_flags if form == c["form"]}
            for a in c["extra_args"]:
                if a.startswith("--"):
                    self.assertIn(a, names, f"{c} 的 extra_args 只能用該寫法的寫法旗標")
        self.assertEqual({(c["form"], c["expect"]) for c in EXIT_CODE_CASES}, set(SURFACE.form_codes))

    # spec §4.1.4
    def test_exit_code_matrix(self):
        for c in EXIT_CODE_CASES:
            with self.subTest(form=c["form"], setup=c["setup"], scenario=c["scenario"], args=c["extra_args"]):
                r = run_exit_case(self, c)
                self.assertEqual(r.returncode, c["expect"], f"stdout:{r.stdout}\nstderr:{r.stderr}")

    # spec §4.1.6
    def test_no_status_within_timeout_exits_4(self):
        sb = Sandbox(self, scenario="no_status")
        t0 = time.monotonic()
        r = sb.meeting("record", "preflight", "--window", "1", timeout=120)
        elapsed = time.monotonic() - t0
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 4, out)
        self.assertGreaterEqual(elapsed, 19, "應等滿約 20 秒才判定沒有狀態")
        self.assertIn("Privacy_ScreenCapture", out, "應印出開啟螢幕錄製設定的指令")
        self.assertIn("完全結束", out)
        self.assertIn("重開", out)

    # spec §4.1.7
    def test_stale_status_ignored(self):
        sb = Sandbox(self, scenario="stale_status")
        old = {"schemaVersion": 1, "runId": "old-run", "pid": dead_pid(), "phase": "done", "code": 0,
               "message": "", "session": "", "startedAt": "", "updatedAt": "", "segments": 0, "preflight": [],
               "warnings": []}
        (sb.home / "record.status.json").write_text(json.dumps(old), encoding="utf-8")
        r = sb.meeting("record", "preflight", "--window", "1", timeout=120)
        self.assertEqual(r.returncode, 4, "runId 不符的狀態檔應被忽略（等不到本次狀態 → 4）\n" + r.stdout + r.stderr)

    # spec §4.2.3
    def test_hard_fail_does_not_start(self):
        sb = Sandbox(self, scenario="preflight_fail_4")
        r = sb.meeting("record", sb.root, *W, timeout=120)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(list(sb.root.rglob("seg-*.mov")), [])
        self.assertIn("沒有螢幕錄製權限（範例訊息）", r.stdout + r.stderr, "應轉述 hard 項的訊息")

    # spec §4.2.4
    def test_warn_only_starts_with_notice(self):
        sb = Sandbox(self, scenario="warn_only")
        r = sb.meeting("record", sb.root, *W, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("用電池且電量低於 20%（範例訊息）", r.stdout + r.stderr, "應列出 warn 項")

    # spec §4.5.5
    def test_stop_reports_code_5(self):
        sb = Sandbox(self)
        start_fake_recorder(self, sb, stop_code=5)
        r = sb.meeting("record", "stop", timeout=180)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)

    # spec §4.5.6
    def test_stop_prints_black_intervals(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=1.0)])
        mf = sess / "錄音" / "tracks" / "manifest.json"
        data = json.loads(mf.read_text(encoding="utf-8"))
        data["blackIntervals"] = [{"start": 860.0, "end": 1085.0}]
        mf.write_text(json.dumps(data), encoding="utf-8")
        warnings = [{"t": 100.0, "kind": "silence_mic", "message": "麥克風連續 15 秒沒有聲音"},
                    {"t": 400.0, "kind": "silence_mic", "message": "麥克風連續 15 秒沒有聲音"},
                    {"t": 865.0, "kind": "black", "message": "畫面全黑"}]
        start_fake_recorder(self, sb, 0, session=sess, warnings=warnings)
        r = sb.meeting("record", "stop", timeout=180)
        out = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(out, r"14:20\s*[–~-]+\s*18:05", "應列出黑畫面區間 mm:ss–mm:ss")
        lines = [l for l in out.split("\n") if ("silence_mic" in l or "麥克風" in l or "靜音" in l)]
        self.assertTrue(any(re.search(r"\b2\b", l) for l in lines), "應列出各類告警次數（麥克風靜音 2 次）")

    # spec §4.15.13
    def test_windows_ask_automation_only_with_tty(self):
        sb = Sandbox(self, scenario="recording", windows=fx.WINDOWS_WITH_STAR)
        rc, out = run_pty(["bash", MEETING_SH, "record", "windows"], env=sb.env(), cwd=sb.cwd,
                          responder=lambda full, new: None, timeout=180)
        self.assertEqual(rc, 0, out)
        tty_calls = [app_args(c) for c in sb.read_calls() if "windows" in app_args(c)]
        self.assertTrue(tty_calls, "應呼叫 app 的 windows")
        self.assertTrue(any("--ask-automation" in c for c in tty_calls), "tty 下應帶 --ask-automation")
        sb.reset_calls()
        r = sb.meeting("record", "windows", timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        calls = [app_args(c) for c in sb.read_calls() if "windows" in app_args(c)]
        self.assertTrue(calls)
        self.assertFalse(any("--ask-automation" in c for c in calls), "stdin 為 /dev/null 時不得帶 --ask-automation")

    # spec §4.15.13、§3.5
    def test_start_passes_window_identity(self):
        rows = fx.WINDOWS_MPLUS
        sb = Sandbox(self, scenario="recording", windows=rows)
        resp = PromptResponder([r["label"] for r in rows], ["\n"], root=sb.root)
        rc, out = run_pty(["bash", MEETING_SH, "record", sb.root], env=sb.env(), cwd=sb.cwd, responder=resp,
                          timeout=180)
        self.assertEqual(rc, 0, out)
        star = rows[0]
        calls = [app_args(c) for c in sb.read_calls() if app_args(c)[:1] in (["preflight"], ["start"])]
        self.assertTrue(calls, "互動開錄應呼叫 app 的 preflight／start")
        for c in calls:
            self.assertEqual(flag_value(c, "--window"), str(star["windowID"]), c)
            self.assertEqual(flag_value(c, "--window-bundle"), star["bundleID"], c)
            self.assertEqual(flag_value(c, "--window-title"), star["title"], c)


if __name__ == "__main__":
    unittest.main()

"""spec §2.3、§2.4、§4.1.1–4.1.3、§4.1.10–4.1.12：meeting.sh 的 record 接線。"""
import re
import unittest

from tests.record import _fixtures as fx
from tests.record._helpers import (EOF, MEETING_SH, RECORD_SH, UNKNOWN_OPTION, Sandbox, app_args, flag_value,
                                   is_subsequence, run_pty, snapshot)
from tests.record.surface import (SURFACE, USAGE_HEADER, assert_component_equal, form_argv, parse_help,
                                  parse_usage)

LAYER = SURFACE.layer_flags


def conflict_hint(text):
    return "--recorder" in text and "prep ./record" in text


def check_layer_calls(tc, calls, user_args, required, forbid=()):
    """spec §4.1.12 (i)–(iii)；不以整串相等斷言替身參數。"""
    tc.assertTrue(calls, "替身應被呼叫")
    for c in calls:  # (i)
        for lf in LAYER:
            tc.assertNotIn(lf, c, f"替身參數不得含層旗標 {lf}：{c}")
    sub = user_args[0]
    good = []
    for c in calls:
        if sub not in c or not is_subsequence(user_args, c):  # (ii)
            continue
        if "--window" in user_args and flag_value(c, "--window") != "1":
            continue
        ok = all(flag_value(c, f) is not None and not flag_value(c, f).startswith("--") for f in required)  # (iii)
        if ok and not any(f in c for f in forbid):
            good.append(c)
    tc.assertTrue(good, f"沒有任何一次呼叫同時滿足子序列 {user_args} 與必帶參數 {required}（不得含 {list(forbid)}）："
                        f"{calls}")


class TestCliDispatch(unittest.TestCase):
    # spec §4.1.1
    def test_record_dispatches_to_record_sh(self):
        src = MEETING_SH.read_text(encoding="utf-8").split("\n")
        rec = [i for i, l in enumerate(src) if re.match(r"^  record\)", l)]
        star = [i for i, l in enumerate(src) if re.match(r"^  \*\)$", l)]
        self.assertEqual(len(rec), 1, "meeting.sh 頂層應有一個 record) 分支")
        self.assertTrue(star and rec[0] < star[0], "record) 應在頂層 *) 之前")
        self.assertTrue(RECORD_SH.is_file())
        sb = Sandbox(self)
        via = sb.meeting("record", "status")
        direct = sb.run(["bash", RECORD_SH, "status"])
        self.assertEqual(via.returncode, direct.returncode)
        self.assertEqual(via.stdout, direct.stdout)

    # spec §4.1.2、§2.4.6
    def test_help_lists_record_forms(self):
        sb = Sandbox(self)
        r = sb.meeting("help")
        self.assertEqual(r.returncode, 0)
        lines = r.stdout.split("\n")
        heads = [i for i, l in enumerate(lines) if l == USAGE_HEADER]
        self.assertEqual(len(heads), 1, f"段頭行應恰好一行：{USAGE_HEADER}")
        assert_component_equal(self, "forms", parse_usage(r.stdout).forms, SURFACE.forms)
        h = heads[0]
        body = lines[h + 1:h + 1 + 7]
        self.assertEqual([re.split(r" {2,}", l[2:], 1)[0] for l in body], SURFACE.forms,
                         "段頭後應緊接 7 行寫法")
        for l in body:
            self.assertRegex(l, r"^  meeting record.* {2,}\S", "寫法後應接兩個以上空白與說明")
            self.assertNotRegex(re.split(r" {2,}", l[2:], 1)[0], r"--", "寫法後不得接旗標")
        layer = [l for l in lines if l.startswith("  層旗標：")]
        self.assertEqual(len(layer), 1)
        self.assertIn("--recorder", layer[0])
        self.assertIn("--yes", layer[0])
        codes = [l for l in lines if l.startswith("  結束碼：")]
        self.assertEqual(len(codes), 1)
        pos = [codes[0].find(f"{c} ") for c in ("0", "2", "3", "4", "5")]
        self.assertTrue(all(p >= 0 for p in pos) and pos == sorted(pos), codes[0])
        self.assertEqual(lines[h + 8], layer[0])
        self.assertEqual(lines[h + 9], codes[0])
        self.assertEqual(lines[h + 10], "", "record 段之後應接一個空行")

    # spec §4.1.3
    def test_existing_exit_codes_unchanged(self):
        sb = Sandbox(self)
        empty = sb.base / "空目錄"
        empty.mkdir()
        self.assertEqual(sb.meeting().returncode, 1)
        self.assertEqual(sb.meeting("--bogus").returncode, 2)
        self.assertEqual(sb.meeting("不存在的指令").returncode, 2)
        self.assertEqual(sb.meeting("render").returncode, 2)
        self.assertEqual(sb.meeting("status", empty).returncode, 0)
        self.assertEqual(sb.meeting("prep", empty).returncode, 3)

    def test_record_dir_explicit_prep_paths_unchanged(self):
        sb = Sandbox(self, cwd_record_dir=True)
        self.assertEqual(sb.meeting("prep", "./record").returncode, 3)
        self.assertEqual(sb.meeting("./record").returncode, 3)
        self.assertEqual(sb.meeting("record").returncode, 2)

    # spec §4.1.10 (a)
    def test_record_dir_conflict_noninteractive_exits_2(self):
        sb = Sandbox(self, cwd_record_dir=True, windows=fx.WINDOWS_WITH_STAR)
        for args in (["record"], ["record", "windows"], ["record", "status"], ["record", "help"]):
            with self.subTest(args=args):
                r = sb.meeting(*args)
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertTrue(conflict_hint(r.stdout + r.stderr), "應印出 --recorder 與 prep ./record 兩種寫法")
                self.assertNotIn("會議根目錄：", r.stdout, "不得跑 prep")
        self.assertEqual(sb.read_calls(), [], "不得啟動錄製器")

    def test_record_dir_conflict_yes_flag_exits_2(self):
        sb = Sandbox(self, cwd_record_dir=True, windows=fx.WINDOWS_WITH_STAR)
        for args in (["record", "--yes", "windows"], ["record", "windows", "--yes"]):
            with self.subTest(args=args):
                rc, out = run_pty(["bash", MEETING_SH, *args], env=sb.env(), cwd=sb.cwd,
                                  responder=lambda full, new: EOF, timeout=60)
                self.assertEqual(rc, 2, out)
                self.assertTrue(conflict_hint(out), out)
        self.assertEqual(sb.read_calls(), [])

    # spec §4.1.10 (b)
    def test_record_dir_conflict_interactive_choices(self):
        def answer(choice):
            state = {"sent": False}

            def responder(full, new):
                if not state["sent"] and "1)" in full and "2)" in full:
                    state["sent"] = True
                    return choice
                return None
            return responder

        sb = Sandbox(self, cwd_record_dir=True, windows=fx.WINDOWS_WITH_STAR)
        rc, out = run_pty(["bash", MEETING_SH, "record", "windows"], env=sb.env(), cwd=sb.cwd,
                          responder=answer("1\n"), timeout=180)
        self.assertEqual(rc, 0, out)
        self.assertTrue(any("windows" in app_args(c) for c in sb.read_calls()), "選 1 應交給 record.sh")
        sb.reset_calls()
        rc, out = run_pty(["bash", MEETING_SH, "record", "windows"], env=sb.env(), cwd=sb.cwd,
                          responder=answer("2\n"), timeout=60)
        ref = sb.meeting("prep", "record")
        self.assertEqual(rc, ref.returncode, out)
        self.assertEqual(rc, 3, "選 2 應與 meeting.sh prep record 相同（空的 record/ 找不到場次 → 3）")
        self.assertIn("找不到任何場次", out)
        self.assertEqual(sb.read_calls(), [])
        rc, out = run_pty(["bash", MEETING_SH, "record", "windows"], env=sb.env(), cwd=sb.cwd,
                          responder=answer("x\n"), timeout=60)
        self.assertEqual(rc, 2, out)
        self.assertEqual(sb.read_calls(), [])

    # spec §4.1.10 (c)
    def test_record_dir_conflict_explicit_recorder_flag(self):
        sb = Sandbox(self, cwd_record_dir=True, windows=fx.WINDOWS_WITH_STAR)
        r = sb.meeting("record", "--recorder", "windows")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(conflict_hint(r.stderr))
        calls = sb.read_calls()
        self.assertTrue(any("windows" in app_args(c) for c in calls))
        self.assertFalse(any("--recorder" in c for c in calls))

    # spec §4.1.11
    def test_record_help_prints_surface(self):
        sb = Sandbox(self)
        before = snapshot(sb.home)
        outs = []
        for spelling in ("help", "-h", "--help"):
            r = sb.meeting("record", spelling)
            self.assertEqual(r.returncode, 0, f"record {spelling}：{r.stderr}")
            outs.append(r.stdout)
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[0], outs[2])
        got = parse_help(outs[0])
        for k in ("forms", "form_flags", "form_codes", "layer_flags", "codes"):
            assert_component_equal(self, k, got[k], SURFACE[k])
        self.assertEqual(sb.read_calls(), [], "record help 不得呼叫錄製器")
        self.assertEqual(snapshot(sb.home), before, "MH_RECORD_HOME 下不得新增或修改任何檔")

    # spec §4.1.12：每一種寫法加 --no-such-flag
    def test_record_unknown_flag_exits_2(self):
        sb = Sandbox(self, windows=fx.WINDOWS_WITH_STAR)
        session = sb.root / "20261011" / "範例場次"
        (session / "錄音").mkdir(parents=True)
        for form in SURFACE.forms:
            with self.subTest(form=form):
                r = sb.run(form_argv(form, root=sb.root, session=session, extra=["--no-such-flag"]))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(UNKNOWN_OPTION, r.stderr)

    # spec §4.1.12 (i)：每個寫法各配一次層旗標，替身參數不得含層旗標
    def test_meeting_sh_layer_flags_stripped(self):
        flags = {f: fl for f, fl in SURFACE.form_flags}
        for lf in LAYER:
            for form in SURFACE.forms:
                with self.subTest(layer=lf, form=form):
                    sb = Sandbox(self, windows=fx.WINDOWS_WITH_STAR)
                    session = sb.root / "20261011" / "範例場次"
                    (session / "錄音").mkdir(parents=True)
                    r = sb.run(form_argv(form, root=sb.root, session=session, layer_flag=lf,
                                         form_flag=flags.get(form)))
                    self.assertNotIn(UNKNOWN_OPTION, r.stderr)
                    for c in sb.read_calls():
                        self.assertNotIn("--recorder", c)
                        self.assertNotIn("--yes", c)

    # spec §4.1.12 (a)：中間位置，cwd 有空的 record/
    def test_layer_flag_mid_position_stripped(self):
        sb = Sandbox(self, cwd_record_dir=True, scenario="recording")
        r = sb.run(["bash", MEETING_SH, "record", "preflight", "--recorder", "--window", "1"])
        self.assertNotIn(UNKNOWN_OPTION, r.stderr)
        self.assertFalse(conflict_hint(r.stdout + r.stderr), "--recorder 在中間也應略過撞名檢查")
        check_layer_calls(self, sb.read_calls(), ["preflight", "--window", "1"],
                          ["--session", "--min-free-bytes", "--run-id", "--home"])
        ref_sb = Sandbox(self, cwd_record_dir=True, scenario="recording")
        ref = ref_sb.run(["bash", MEETING_SH, "record", "--recorder", "preflight", "--window", "1"])
        self.assertEqual(r.returncode, ref.returncode, f"\n{r.stderr}\n---\n{ref.stderr}")

    # spec §4.1.12 (b)：結尾位置
    def test_layer_flag_trailing_position_stripped(self):
        sb = Sandbox(self, scenario="recording", windows=fx.WINDOWS_WITH_STAR)
        r = sb.run(["bash", MEETING_SH, "record", "windows", "--json", "--yes"])
        self.assertNotIn(UNKNOWN_OPTION, r.stderr)
        check_layer_calls(self, sb.read_calls(), ["windows", "--json"], ["--log"],
                          forbid=["--ask-automation"])
        ref_sb = Sandbox(self, scenario="recording", windows=fx.WINDOWS_WITH_STAR)
        ref = ref_sb.run(["bash", MEETING_SH, "record", "windows", "--json"])
        self.assertEqual(r.returncode, ref.returncode)
        sb2 = Sandbox(self, cwd_record_dir=True, scenario="recording", windows=fx.WINDOWS_WITH_STAR)
        r2 = sb2.run(["bash", MEETING_SH, "record", "windows", "--json", "--yes"])
        self.assertEqual(r2.returncode, 2, "結尾的 --yes 仍應生效：有 record/ 時回 2")
        self.assertTrue(conflict_hint(r2.stdout + r2.stderr))
        self.assertEqual(sb2.read_calls(), [])


if __name__ == "__main__":
    unittest.main()

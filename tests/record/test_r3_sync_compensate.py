"""S-C：依時段補償系統聲音（spec §4.37.2–§4.37.5、§4.37.7、§4.37.8；R3-D9；ADR adr-r3-concat-then-mix.md）。

合成場次以 tests/record/_media.py 的 build_sc_session 建（段落在錄製時鐘上緊接、麥克風為數位 0，成品音訊＝系統聲音）；
收尾以 python3 bin/_record_finalize.py <場次> 直接執行（MH_RECORD_HOME 指向暫存 home）。
R2 對照：git show 377dd92:bin/_record_finalize.py 取到暫存目錄執行。
finalize.json 的位置：spec §3.17 寫「錄音/finalize.json」，現行程式寫「錄音/tracks/finalize.json」，兩處都找。
"""
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

import tests.record.e2e_check as e2e
from tests.record import _media as m
from tests.record._helpers import BIN, tmpdir
from tests.record.surface import REPO

FINALIZE_PY = BIN / "_record_finalize.py"
E2E_PY = Path(__file__).resolve().parent / "e2e_check.py"
R2_REV = "377dd92"
DELAY_TOL = 0.005
A, B, C = "uid-範例-a", "uid-範例-b", "uid-範例-c"


def fin_json(sess):
    for p in (sess / "錄音" / "tracks" / "finalize.json", sess / "錄音" / "finalize.json"):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return None


def video_of(sess):
    vids = sorted((sess / "影片").glob("*.mov"))
    assert len(vids) == 1, vids
    return vids[0]


def offsets(sess):
    return [(round(t, 3), d) for t, d in e2e.sync_offsets(str(video_of(sess)))]


def length(sess):
    return e2e.stream_duration(str(video_of(sess)), "audio")


def windows_db(sess, win):
    samples, start = e2e.pcm_mono(str(video_of(sess)))
    return e2e.rms_db_windows(samples, 16000, win), start


def silent_runs(sess, lo, hi, win=0.001, floor=-60.0):
    """[lo, hi] 秒內 RMS ≤ floor 的連續區間（秒）。"""
    db, start = windows_db(sess, win)
    runs, cur = [], None
    for i, v in enumerate(db):
        t = start + i * win
        if t < lo or t > hi:
            continue
        if v <= floor:
            cur = [t, t + win] if cur is None else [cur[0], t + win]
        elif cur is not None:
            runs.append(tuple(cur))
            cur = None
    if cur is not None:
        runs.append(tuple(cur))
    return runs


class SCCase(unittest.TestCase):
    def setUp(self):
        self.base = tmpdir(self)
        self.home = self.base / "home"
        self.home.mkdir()

    def copy(self, sess, name):
        dst = self.base / name / sess.relative_to(sess.parents[1])
        shutil.copytree(sess, dst)
        return dst

    def finalize(self, sess, mode=None, script=FINALIZE_PY, home=None):
        env = dict(os.environ, MH_RECORD_HOME=str(home or self.home))
        for k in ("MH_SYNC_COMPENSATION", "MH_FINALIZE_STEP_TIMEOUT", "MH_KEEP_SEGMENTS", "MH_FFMPEG"):
            env.pop(k, None)
        if mode is not None:
            env["MH_SYNC_COMPENSATION"] = mode
        r = subprocess.run([sys.executable, str(script), str(sess)], capture_output=True, text=True, env=env,
                           timeout=300)
        self.assertEqual(r.returncode, 0, f"收尾失敗\nstdout:{r.stdout}\nstderr:{r.stderr}")
        return r

    def sc(self, sess):
        fin = fin_json(sess)
        self.assertIsInstance(fin, dict, "應寫 finalize.json")
        sc = fin.get("syncCompensation")
        self.assertIsInstance(sc, dict, "finalize.json 應有 syncCompensation")
        return sc

    def r2_script(self):
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{R2_REV}:bin/_record_finalize.py"], capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = self.base / "r2_record_finalize.py"
        p.write_text(r.stdout, encoding="utf-8")
        return p

    def off_and(self, sess, mode):
        """同一份 tracks/ 各收尾一次：off 與 mode。回傳 (off 場次, mode 場次)。"""
        off = self.copy(sess, "off")
        on = self.copy(sess, mode)
        self.finalize(off, "off")
        self.finalize(on, mode)
        return off, on

    def assert_shift(self, off, on, want, flash_range, label):
        o, n = dict(offsets(off)), dict(offsets(on))
        hits = [t for t in o if flash_range[0] <= t < flash_range[1]]
        self.assertTrue(hits, f"{label}：前提：範圍內應有閃白")
        for t in hits:
            self.assertIsNotNone(o[t], f"{label}：off 在 {t} 秒應量得到嗶聲")
            self.assertIn(t, n, f"{label}：補償後在 {t} 秒應有同一個閃白")
            self.assertIsNotNone(n[t], f"{label}：補償後在 {t} 秒應量得到嗶聲")
            self.assertAlmostEqual(n[t] - o[t], want, delta=DELAY_TOL, msg=f"{label}：{t} 秒的嗶聲延後量")

    def assert_segments(self, sc, want):
        segs = sc.get("segments")
        self.assertIsInstance(segs, list)
        self.assertEqual(len(segs), len(want), segs)
        for got, (f, uid, delay, source, clamped) in zip(segs, want):
            self.assertEqual(set(got), {"file", "outputUid", "delaySeconds", "source", "clamped"}, got)
            self.assertEqual(got["file"], f)
            self.assertEqual(got["outputUid"], uid)
            self.assertAlmostEqual(float(got["delaySeconds"]), delay, delta=0.0005)
            self.assertEqual(got["source"], source)
            self.assertIs(got["clamped"], clamped)


class TestR3SyncCompensate(SCCase):
    # spec §4.37.2：MH_SYNC_COMPENSATION 優先；否則 record.defaults.json；都沒有＝off；不認得＝off 並記一行
    def test_mode_resolution(self):
        sess = m.build_sc_session(self.base / "src", outputs=((A, 0.1),))
        cases = (("env 優先", "reported", {"syncCompensation": "off"}, "reported"),
                 ("defaults", None, {"syncCompensation": "calibrated"}, "calibrated"),
                 ("都沒有", None, None, "off"),
                 ("env 不認得", "範例錯值", None, "off"),
                 ("defaults 不認得", None, {"syncCompensation": "範例錯值"}, "off"))
        for i, (label, env_mode, defaults, want) in enumerate(cases):
            with self.subTest(case=label):
                home = self.base / f"home{i}"
                home.mkdir()
                if defaults is not None:
                    (home / "record.defaults.json").write_text(json.dumps(defaults, ensure_ascii=False),
                                                               encoding="utf-8")
                s = self.copy(sess, f"case{i}")
                r = self.finalize(s, env_mode, home=home)
                self.assertEqual(self.sc(s).get("mode"), want)
                if "不認得" in label:
                    log = r.stdout + r.stderr
                    if (home / "record.log").is_file():
                        log += (home / "record.log").read_text(encoding="utf-8")
                    self.assertTrue(any("範例錯值" in ln for ln in log.splitlines()), "不認得的值應記一行 log")

    # spec §4.37.3：off＝R2 的 D20 流程；成品長度差 ≤ 0.1 秒、--sync 每個事件差值變化 ≤ 1/60 秒、e2e 預設組結果相同
    def test_off_equivalent(self):
        sess = m.build_sc_session(self.base / "src", seglen=4.0, outputs=((A, 0.15), (B, 0.0)), flash_phase=1.0)
        r3 = self.copy(sess, "r3")
        r2 = self.copy(sess, "r2")
        self.finalize(r3, "off")
        self.finalize(r2, script=self.r2_script())
        self.assertEqual(self.sc(r3), {"mode": "off", "segments": []})
        self.assertLessEqual(abs(length(r3) - length(r2)), 0.1)
        o3, o2 = dict(offsets(r3)), dict(offsets(r2))
        self.assertEqual(sorted(o3), sorted(o2), "閃白時刻應相同")
        for t in o2:
            if o2[t] is not None:
                self.assertIsNotNone(o3[t])
                self.assertLessEqual(abs(o3[t] - o2[t]), 1 / 60, f"{t} 秒的事件差值變化")

        def default_checks(s):
            r = subprocess.run([sys.executable, str(E2E_PY), str(s), "--json"], capture_output=True, text=True,
                               timeout=300)
            self.assertIn(r.returncode, (0, 1), r.stderr)
            return {x["check"]: x["ok"] for x in json.loads(r.stdout)}

        self.assertEqual(default_checks(r3), default_checks(r2), "e2e_check.py 預設組的結果應與 R2 相同")

    # spec §4.37.4：兩段、延遲 0.0 與 0.150；第 2 段嗶聲晚 0.150、第 1 段不變；總長差 ≤ 0.1；段界一段 0.150 秒靜音
    def test_reported_delays_per_segment(self):
        sess = m.build_sc_session(self.base / "src", seglen=4.0, outputs=((A, 0.0), (B, 0.15)), flash_phase=1.0)
        off, on = self.off_and(sess, "reported")
        self.assert_shift(off, on, 0.0, (0.0, 4.0), "第 1 段")
        self.assert_shift(off, on, 0.15, (4.0, 8.0), "第 2 段")
        self.assertLessEqual(abs(length(on) - length(off)), 0.1)
        sc = self.sc(on)
        self.assertEqual(sc.get("mode"), "reported")
        self.assert_segments(sc, [("seg-0001.mov", A, 0.0, "reported", False),
                                  ("seg-0002.mov", B, 0.15, "reported", False)])
        runs = [r for r in silent_runs(on, 3.5, 4.5) if r[1] - r[0] >= 0.05]
        self.assertEqual(len(runs), 1, f"段界應恰有一段靜音：{runs}")
        self.assertAlmostEqual(runs[0][1] - runs[0][0], 0.15, delta=DELAY_TOL)
        self.assertEqual([r for r in silent_runs(on, 0.3, 3.5) + silent_runs(on, 4.5, length(on) - 0.3)
                          if r[1] - r[0] >= 0.05], [], "段界以外不得有靜音")

    # spec §4.37.4（修正輪 C）：三段、延遲都是 0.150、跨段連續 1 kHz：0.150 秒之後每 10 ms 窗 > -40 dBFS，嗶聲都晚 0.150
    def test_constant_delay_no_gaps(self):
        sess = m.build_sc_session(self.base / "src", seglen=2.0, outputs=((A, 0.15),) * 3, flash_phase=1.0, tone=True)
        off, on = self.off_and(sess, "reported")
        self.assert_shift(off, on, 0.15, (0.0, 6.0), "三段")
        total = length(on)
        self.assertLessEqual(abs(total - length(off)), 0.1)
        db, start = windows_db(on, 0.01)
        low = [round(start + i * 0.01, 2) for i, v in enumerate(db)
               if 0.16 <= start + i * 0.01 <= total - 0.02 and v <= -40.0]
        self.assertEqual(low, [], "段界不得有空洞或被截掉（每個 10 ms 窗 RMS 應 > -40 dBFS）")

    # spec §4.37.4：延遲變小（0.150 → 0）時截前一段的尾，不補靜音；第 2 段嗶聲與 off 相同
    def test_delay_decrease_trims_overlap(self):
        sess = m.build_sc_session(self.base / "src", seglen=4.0, outputs=((A, 0.15), (B, 0.0)), flash_phase=1.0,
                                  tone=True)
        off, on = self.off_and(sess, "reported")
        self.assert_shift(off, on, 0.15, (0.0, 4.0), "第 1 段")
        self.assert_shift(off, on, 0.0, (4.0, 8.0), "第 2 段")
        self.assertLessEqual(abs(length(on) - length(off)), 0.1)
        self.assert_segments(self.sc(on), [("seg-0001.mov", A, 0.15, "reported", False),
                                           ("seg-0002.mov", B, 0.0, "reported", False)])
        db, start = windows_db(on, 0.01)
        low = [round(start + i * 0.01, 2) for i, v in enumerate(db)
               if 0.16 <= start + i * 0.01 <= length(on) - 0.02 and v <= -40.0]
        self.assertEqual(low, [], "延遲變小時不得在段界留下空洞")

    # spec §4.37.5：calibrated：有 uid 用它（calibrated）、沒有 → 0（missing）、0.8 → 夾到 0.5（clamped）
    def test_calibrated_lookup_and_clamp(self):
        sess = m.build_sc_session(self.base / "src", seglen=2.0, outputs=((A, 0.0), (B, 0.0), (C, 0.0)))
        (self.home / "sync-calibration.json").write_text(json.dumps(
            {"schemaVersion": 1, "devices": {A: 0.12, C: 0.8}}, ensure_ascii=False), encoding="utf-8")
        self.finalize(sess, "calibrated")
        sc = self.sc(sess)
        self.assertEqual(sc.get("mode"), "calibrated")
        self.assert_segments(sc, [("seg-0001.mov", A, 0.12, "calibrated", False),
                                  ("seg-0002.mov", B, 0.0, "missing", False),
                                  ("seg-0003.mov", C, 0.5, "calibrated", True)])

    # spec §4.37.7：播放端延遲 0.150 的模擬（嗶聲比閃白早 0.150）：reported 收尾 → --sync-player PASS、off → FAIL
    def test_sync_player_with_compensation(self):
        sess = m.build_sc_session(self.base / "src", seglen=4.0, outputs=((A, 0.15), (A, 0.15)), flash_phase=1.0,
                                  beep_lead=0.15)
        off, on = self.off_and(sess, "reported")

        def player(s):
            r = subprocess.run([sys.executable, str(E2E_PY), "--sync-player", str(s), "--json"], capture_output=True,
                               text=True, timeout=300)
            self.assertIn(r.returncode, (0, 1), f"e2e_check.py --sync-player 回 {r.returncode}：{r.stderr}")
            res = [x for x in json.loads(r.stdout) if "player" in x["check"]]
            self.assertEqual(len(res), 1)
            return res[0]

        self.assertTrue(player(on)["ok"], "reported 收尾的成品應 PASS")
        self.assertFalse(player(off)["ok"], "off 收尾的成品應 FAIL")

    # spec §4.37.8：R3 的預設值維持 off（沒有環境變數、沒有 defaults）
    def test_default_off(self):
        sess = m.build_sc_session(self.base / "src", outputs=((A, 0.15),))
        self.finalize(sess)
        self.assertEqual(self.sc(sess), {"mode": "off", "segments": []})


if __name__ == "__main__":
    unittest.main()

"""R2：e2e_check.py 的暫停／麥克風靜音／標記判準自我測試（spec §4.17.5、§4.17.6、§4.17.8、§4.18.5–§4.18.7、
§4.18.11、§4.18.12、§4.19.4）。紅燈階段就要綠（e2e_check.py 是測試工具，plan §9.2 r2a）。

每個判準都有已知 PASS 與已知 FAIL 的合成場次；合成素材只在 TMPDIR 產生（spec §4.14.1）。
狀態檔一律以 --status 指定或把 MH_RECORD_HOME 指到暫存目錄，不讀真的 ~/.meeting-harness/。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.record import _media as m

E2E = Path(__file__).resolve().parent / "e2e_check.py"
DS_EVENTS = [(15.0, "output", "builtIn", "bluetooth"), (35.0, "output", "bluetooth", "builtIn")]
NINE = ["pause_events", "pause_cut", "mic_mute_zero", "mute_system_kept", "no_false_silence", "markers",
        "mute_timing", "no_false_black", "event_output_t"]
NOT_TRIGGERED = "情境未觸發"


class R2E2ECase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mh-r2-e2e-"))
        cls.empty_home = cls.tmp / "empty-home"
        cls.empty_home.mkdir()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def check(self, session, *args):
        env = dict(os.environ, MH_RECORD_HOME=str(self.empty_home))
        r = subprocess.run([sys.executable, str(E2E), str(session), "--json", *map(str, args)],
                           capture_output=True, text=True, timeout=600, env=env)
        if r.returncode not in (0, 1):
            raise AssertionError(f"e2e_check.py 回 {r.returncode}：{r.stderr}")
        return r.returncode, {x["check"]: x for x in json.loads(r.stdout)}

    def assert_fail(self, session, name, *args):
        rc, res = self.check(session, *args)
        self.assertIn(name, res, f"結果應含 {name}")
        self.assertFalse(res[name]["ok"], f"{name} 應判 FAIL：{res[name]['detail']}")
        self.assertEqual(rc, 1)
        return res[name]["detail"]

    def assert_pass(self, session, name, *args):
        _, res = self.check(session, *args)
        self.assertIn(name, res, f"結果應含 {name}")
        self.assertTrue(res[name]["ok"], f"{name} 應判 PASS：{res[name]['detail']}")
        return res[name]["detail"]

    def copy(self, src):
        dst = Path(tempfile.mkdtemp(prefix="mh-r2-mut-")) / "x" / src.name
        self.addCleanup(shutil.rmtree, dst.parents[1], True)
        shutil.copytree(src, dst)
        return dst

    def tracks(self, s):
        return s / "錄音" / "tracks"

    def edit_json(self, path, fn):
        d = json.loads(path.read_text(encoding="utf-8"))
        fn(d)  # fn 就地修改 d；回傳值不用
        path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def edit_meta(self, s, fn):
        self.edit_json(self.tracks(s) / "record.meta.json", fn)

    def status(self, s, warnings=()):
        p = Path(tempfile.mkdtemp(prefix="mh-r2-st-")) / "record.status.json"
        self.addCleanup(shutil.rmtree, p.parent, True)
        return m.write_status_for(s, p, warnings=warnings)

    @staticmethod
    def json_session(base, segs, pauses=(), mutes=(), black=(), raw_pauses=None, raw_mutes=None):
        """只有 manifest.json 與 record.meta.json 的場次（不需要媒體的判準用）。segs：[(startedAt, audioDuration)]。"""
        sess = Path(base) / m.DAY / m.SESSION_NAME
        tr = sess / "錄音" / "tracks"
        tr.mkdir(parents=True)
        first = segs[0][0]
        pev = m.pause_events(pauses, first) if raw_pauses is None else raw_pauses
        mev = m.mute_events(mutes, first, pev) if raw_mutes is None else raw_mutes
        recs = [{"file": f"seg-{i:04d}.mov", "requestedAt": max(st - 0.005, 0.0), "startedAt": st,
                 "finishedAt": round(st + ad, 3), "width": 160, "height": 120, "audioDuration": ad}
                for i, (st, ad) in enumerate(segs, start=1)]
        end = segs[-1][0] + segs[-1][1]
        manifest = {"schemaVersion": 1, "segmentSeconds": 60, "segments": recs,
                    "frameStatus": {"complete": 1, "idle": 0, "blank": 0, "suspended": 0, "started": 1, "stopped": 0},
                    "blackIntervals": [dict(start=a, end=b) for a, b in black],
                    "levels": {"windowSeconds": 0.5, "system": [-20.0] * int(end * 2), "mic": [-30.0] * int(end * 2)},
                    "gapStats": {"boundaries": [], "max": 0.0, "total": 0.0, "wallClock": end, "pausedTotal": 0.0},
                    "outputCanvas": {"width": 160, "height": 120}, "outputVideoBitrate": 1000000}
        (tr / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        meta = {"schemaVersion": 1, "window": {"windowID": 89596, "app": "Google Chrome",
                                               "bundleID": "com.google.Chrome", "title": "[Stand-up] 範例專案"},
                "config": dict(m.CONFIG_SNAPSHOT), "devices": {}, "preflight": [], "deviceEvents": [],
                "audioFormatEvents": [], "pauseEvents": pev, "micMuteEvents": mev}
        (tr / "record.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return sess


class TestR2E2ECheckMedia(R2E2ECase):
    """需要合成媒體的判準（麥克風數位 0、成品長度、markers、暫停邊界）。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        mk = lambda name, **kw: m.build_pause_mute_session(cls.tmp / name, **kw)
        two = [(0.0, 15.0), (15.01, 15.0)]
        mutes = [(10.0, True), (20.0, False)]
        cls.mute_ok = mk("mute_ok", segs=two, mic_zero=[(10.0, 20.0)], mutes=mutes)
        cls.mute_impulse = mk("mute_impulse", segs=two, mic_zero=[(10.0, 20.0)], impulses=[12.5], mutes=mutes)
        cls.mute_sys_silent = mk("mute_sys_silent", segs=two, mic_zero=[(10.0, 20.0)], sys_silent=[(10.0, 20.0)],
                                 mutes=mutes)
        cls.mute_early = mk("mute_early", segs=two, mic_zero=[(8.0, 20.0)], mutes=mutes)
        cls.mute_late = mk("mute_late", segs=two, mic_zero=[(10.0, 22.0)], mutes=mutes)
        cls.mute_from_start = mk("mute_from_start", segs=two, mic_zero=[(0.0, 20.0)], mutes=mutes)
        cls.mute_open = mk("mute_open", segs=two, mic_zero=[(25.0, 31.0)], mutes=[(25.0, True)])
        # 一次 30 秒暫停：seg-0001 [0, 2)、暫停 2.0 → 32.0、seg-0002 [32, 34)；標記 3 個（其中一個在暫停中）
        cls.pause_segs = [(0.0, 2.0), (32.0, 2.0)]
        cls.pause = mk("pause", segs=cls.pause_segs, pauses=[(2.0, "pause"), (32.0, "resume")],
                       markers=[1.0, 20.0, 33.0])
        # 暫停中停止：最後一筆是 pause，wallClock 比停止點晚 20 秒
        cls.pause_stopped = mk("pause_stopped", segs=cls.pause_segs,
                               pauses=[(2.0, "pause"), (32.0, "resume"), (34.0, "pause")], wall=54.0)
        cls.no_events = mk("no_events", segs=[(0.0, 2.0), (2.01, 2.0)])

    # spec §4.17.5
    def test_mic_mute_zero_check(self):
        self.assert_pass(self.mute_ok, "mic_mute_zero", "--pause-mute")
        self.assert_pass(self.mute_ok, "mute_system_kept", "--pause-mute")
        self.assert_pass(self.mute_open, "mic_mute_zero", "--pause-mute")  # 沒配對的靜音延伸到最後一段結束
        detail = self.assert_fail(self.mute_impulse, "mic_mute_zero", "--pause-mute")
        self.assertIn("非 0", detail)
        self.assert_fail(self.mute_sys_silent, "mute_system_kept", "--pause-mute")
        self.assert_pass(self.mute_sys_silent, "mic_mute_zero", "--pause-mute")
        s = self.copy(self.mute_ok)
        self.edit_meta(s, lambda d: d.update(micMuteEvents=[]))
        for name in ("mic_mute_zero", "mute_system_kept"):
            self.assertIn(NOT_TRIGGERED, self.assert_fail(s, name, "--pause-mute"))

    # spec §4.17.8
    def test_mute_timing_check(self):
        self.assert_pass(self.mute_ok, "mute_timing", "--pause-mute")
        self.assert_pass(self.mute_open, "mute_timing", "--pause-mute")
        self.assert_fail(self.mute_early, "mute_timing", "--pause-mute")   # mic 在 [8, 20) 為 0：事件記晚 2 秒
        self.assert_fail(self.mute_late, "mute_timing", "--pause-mute")    # mic 在 [10, 22) 為 0
        detail = self.assert_fail(self.mute_from_start, "mute_timing", "--pause-mute")
        self.assertIn("無法判定時刻", detail)
        self.assert_fail(self.mute_impulse, "mute_timing", "--pause-mute")
        s = self.copy(self.mute_ok)
        self.edit_meta(s, lambda d: d.update(micMuteEvents=[]))
        self.assertIn(NOT_TRIGGERED, self.assert_fail(s, "mute_timing", "--pause-mute"))

    # spec §4.18.5
    def test_pause_aware_segment_checks(self):
        for s in (self.pause, self.pause_stopped):
            with self.subTest(session=s.parents[1].name):
                self.assert_pass(s, "gap", "--segment-writer")
                self.assert_pass(s, "segment_cadence", "--segment-writer")
                self.assert_pass(s, "stop_tail", "--segment-writer")
        # resume.t 與 startedAt_2 相差 2 秒：不是暫停邊界 → gap 判 FAIL
        s = self.copy(self.pause)

        def shift(d):
            d["pauseEvents"][1]["t"] = 30.0
        self.edit_meta(s, shift)
        self.assert_fail(s, "gap", "--segment-writer")
        # 暫停中停止但不以最後一筆 pause.t 代替 wallClock 時會差 20 秒：拿掉最後一筆 pause → stop_tail 判 FAIL
        s2 = self.copy(self.pause_stopped)
        self.edit_meta(s2, lambda d: d.update(pauseEvents=d["pauseEvents"][:2]))
        self.assert_fail(s2, "stop_tail", "--segment-writer")
        # 沒有 pauseEvents 鍵的場次照第一輪判（30 秒的洞是 gap FAIL）
        s3 = self.copy(self.pause)
        self.edit_meta(s3, lambda d: (d.pop("pauseEvents"), d.pop("micMuteEvents")))
        self.assert_fail(s3, "gap", "--segment-writer")

    # spec §4.18.6
    def test_pause_cut_and_events_check(self):
        self.assert_pass(self.pause, "pause_events", "--pause-mute")
        self.assert_pass(self.pause, "pause_cut", "--pause-mute")
        self.assert_pass(self.pause_stopped, "pause_events", "--pause-mute")
        self.assert_pass(self.pause_stopped, "pause_cut", "--pause-mute")
        cases = {
            "pause 離段落結束 1 秒": lambda d: d["pauseEvents"][0].update(t=1.0),
            "resume 離段落開始 2 秒": lambda d: d["pauseEvents"][1].update(t=30.0),
            "沒有交替": lambda d: d["pauseEvents"][1].update(kind="pause"),
            "以 resume 開頭": lambda d: d.update(pauseEvents=d["pauseEvents"][1:]),
            "時間沒有遞增": lambda d: d.update(pauseEvents=list(reversed(d["pauseEvents"]))),
        }
        for label, fn in cases.items():
            with self.subTest(case=label):
                s = self.copy(self.pause)
                self.edit_meta(s, fn)
                self.assert_fail(s, "pause_events", "--pause-mute")
        s = self.copy(self.pause)  # 成品比（停止點 − startedAt_1 − pausedTotal）長 6 秒
        wav = next((s / "錄音").glob("*.wav"))
        m.ff("-f", "lavfi", "-i", "sine=f=440:sample_rate=16000:d=10", "-ac", 1, "-c:a", "pcm_s16le", "-f", "wav", wav)
        self.assert_fail(s, "pause_cut", "--pause-mute")
        self.assert_pass(s, "pause_events", "--pause-mute")

    # spec §4.18.6、§4.17.5、§4.17.8、§4.18.11、§4.18.12、§4.19.4：沒有事件時「情境未觸發」，不得判 PASS
    def test_pause_mute_requires_events(self):
        rc, res = self.check(self.no_events, "--pause-mute", "--status", self.status(self.no_events))
        self.assertEqual(rc, 1)
        for name in NINE:
            self.assertIn(name, res, f"--pause-mute 應含 {name}（共九項，spec §6 第 99 條）")
        for name in ("pause_events", "pause_cut", "mic_mute_zero", "mute_system_kept", "mute_timing",
                     "no_false_black", "event_output_t", "markers"):
            self.assertFalse(res[name]["ok"], f"{name} 沒有事件時應判 FAIL：{res[name]['detail']}")
            self.assertIn(NOT_TRIGGERED, res[name]["detail"], name)
        s = self.copy(self.no_events)  # 舊場次（沒有這兩個鍵）同樣不得判 PASS
        self.edit_meta(s, lambda d: (d.pop("pauseEvents"), d.pop("micMuteEvents")))
        _, res = self.check(s, "--pause-mute")
        for name in ("pause_events", "pause_cut"):
            self.assertFalse(res[name]["ok"], res[name]["detail"])
            self.assertIn(NOT_TRIGGERED, res[name]["detail"])
        # 不給 --pause-mute 時不跑這九項（第一輪的判準組不變）
        _, res = self.check(self.no_events)
        self.assertFalse(set(NINE) & set(res), f"沒給 --pause-mute 不得出現九項：{sorted(set(NINE) & set(res))}")
        h = subprocess.run([sys.executable, str(E2E), "--help"], capture_output=True, text=True)
        self.assertIn("--pause-mute", h.stdout)

    # spec §4.19.4
    def test_markers_check(self):
        self.assert_pass(self.pause, "markers", "--pause-mute")
        rec = lambda s: s / "錄音" / "markers.json"
        trk = lambda s: self.tracks(s) / "markers.json"

        def both(s, fn):
            for p in (rec(s), trk(s)):
                self.edit_json(p, fn)

        s = self.copy(self.pause)
        rec(s).unlink()
        self.assert_fail(s, "markers", "--pause-mute")
        s = self.copy(self.pause)
        rec(s).write_text(rec(s).read_text(encoding="utf-8") + "\n", encoding="utf-8")
        self.assert_fail(s, "markers", "--pause-mute")  # 與 tracks/markers.json 不同
        s = self.copy(self.pause)
        both(s, lambda d: d[0].update(label="標記 3"))
        self.assert_fail(s, "markers", "--pause-mute")
        s = self.copy(self.pause)
        both(s, lambda d: d[1].update(t=round(d[1]["t"] + 0.05, 3)))
        self.assert_fail(s, "markers", "--pause-mute")  # 與 outputTime(recordT) 差 0.05 秒
        s = self.copy(self.pause)
        both(s, lambda d: d[2].update(recordT=45.0, t=15.0))
        self.assert_fail(s, "markers", "--pause-mute")  # t 超過 wav 長度
        s = self.copy(self.pause)

        def swap(d):
            d[0], d[1] = d[1], d[0]
            d[0]["label"], d[1]["label"] = "標記 1", "標記 2"
        both(s, swap)
        self.assert_fail(s, "markers", "--pause-mute")  # t 遞減
        s = self.copy(self.pause)
        rec(s).unlink()
        trk(s).unlink()
        self.assertIn(NOT_TRIGGERED, self.assert_fail(s, "markers", "--pause-mute"))


class TestR2E2ECheckLevels(R2E2ECase):
    """spec §4.18.7：讀 levels 的判準排除暫停（兩路）與靜音（mic 路）區間。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ds = m.build_e2e_session(cls.tmp / "ds", dur=50, fps=10, size=(160, 120), device_events=DS_EVENTS,
                                     silences=[(15, 17), (35, 37)])
        cls.hfp = m.build_e2e_session(cls.tmp / "hfp", dur=40, fps=10, size=(160, 120), silences=[(15, 16.5)],
                                      format_events=[(15.0, "system", 48000, 16000)])

    def null_levels(self, s, a, b, tracks=("system", "mic")):
        def fn(d):
            lv = d["levels"]
            ws = lv["windowSeconds"]
            for k in tracks:
                lv[k] = [None if a <= i * ws < b else v for i, v in enumerate(lv[k])]
        self.edit_json(self.tracks(s) / "manifest.json", fn)

    def add_events(self, s, pauses=(), mutes=()):
        pev = m.pause_events(pauses, 0.0)
        self.edit_meta(s, lambda d: d.update(pauseEvents=pev, micMuteEvents=m.mute_events(mutes, 0.0, pev)))

    def test_levels_checks_exclude_pause_and_mute(self):
        self.assert_pass(self.ds, "device_switch", "--device-switch")
        # 5 秒 null（兩路）：不在任何區間 → FAIL；是暫停造成的 → PASS
        s = self.copy(self.ds)
        self.null_levels(s, 24.0, 29.0)
        self.assert_fail(s, "device_switch", "--device-switch")
        self.add_events(s, pauses=[(24.0, "pause"), (29.0, "resume")])
        self.assert_pass(s, "device_switch", "--device-switch")
        # 5 秒 null（只有 mic）：靜音造成的 → PASS；不在靜音區間 → FAIL
        s = self.copy(self.ds)
        self.null_levels(s, 24.0, 29.0, tracks=("mic",))
        self.assert_fail(s, "device_switch", "--device-switch")
        self.add_events(s, mutes=[(24.0, True), (29.0, False)])
        self.assert_pass(s, "device_switch", "--device-switch")
        # 靜音只排除 mic：系統聲音同時段 null 仍判 FAIL
        s = self.copy(self.ds)
        self.null_levels(s, 24.0, 29.0)
        self.add_events(s, mutes=[(24.0, True), (29.0, False)])
        self.assert_fail(s, "device_switch", "--device-switch")

        st = self.status(self.hfp)
        self.assert_pass(self.hfp, "hfp", "--hfp", "--status", st)
        s = self.copy(self.hfp)
        st = self.status(s)
        self.null_levels(s, 27.0, 32.0)
        self.assert_fail(s, "hfp", "--hfp", "--status", st)
        self.add_events(s, pauses=[(27.0, "pause"), (32.0, "resume")])
        self.assert_pass(s, "hfp", "--hfp", "--status", st)


class TestR2E2ECheckJson(R2E2ECase):
    """只讀 JSON 的判準：no_false_silence、no_false_black、event_output_t。"""

    def session(self, **kw):
        base = Path(tempfile.mkdtemp(prefix="mh-r2-json-"))
        self.addCleanup(shutil.rmtree, base, True)
        return self.json_session(base, **kw)

    # spec §4.17.6
    def test_no_false_silence_check(self):
        kw = dict(segs=[(0.0, 70.0), (100.0, 30.0)], pauses=[(70.0, "pause"), (100.0, "resume")],
                  mutes=[(10.0, True), (20.0, False)])
        s = self.session(**kw)
        w = lambda t, k: {"t": t, "kind": k, "message": "範例訊息"}
        self.assert_pass(s, "no_false_silence", "--pause-mute", "--status", self.status(s))
        self.assert_pass(s, "no_false_silence", "--pause-mute", "--status",
                         self.status(s, [w(22.0, "silence_mic"), w(15.0, "silence_system"), w(40.0, "silence_mic")]))
        for bad in (w(15.0, "silence_mic"), w(20.5, "silence_mic"), w(85.0, "silence_system"),
                    w(85.0, "silence_mic"), w(100.8, "silence_system")):
            with self.subTest(warning=bad):
                self.assert_fail(s, "no_false_silence", "--pause-mute", "--status", self.status(s, [bad]))
        detail = self.assert_fail(s, "no_false_silence", "--pause-mute")  # 找不到狀態檔
        self.assertIn("record.status.json", detail)
        # 沒配對的靜音延伸到最後一段結束
        s2 = self.session(segs=[(0.0, 70.0), (100.0, 30.0)], pauses=[(70.0, "pause"), (100.0, "resume")],
                          mutes=[(110.0, True)])
        self.assert_fail(s2, "no_false_silence", "--pause-mute", "--status",
                         self.status(s2, [w(125.0, "silence_mic")]))

    # spec §4.18.11
    def test_no_false_black_check(self):
        kw = dict(segs=[(0.0, 70.0), (100.0, 30.0)], pauses=[(70.0, "pause"), (100.0, "resume")])
        s = self.session(black=[(80.0, 85.0)], **kw)
        self.assert_fail(s, "no_false_black", "--pause-mute", "--status", self.status(s))
        s = self.session(black=[(120.0, 130.0)], **kw)
        self.assert_pass(s, "no_false_black", "--pause-mute", "--status", self.status(s))
        for kind, t in (("black", 90.0), ("suspended", 100.9)):
            with self.subTest(kind=kind):
                st = self.status(s, [{"t": t, "kind": kind, "message": "範例訊息"}])
                self.assert_fail(s, "no_false_black", "--pause-mute", "--status", st)
        st = self.status(s, [{"t": 120.0, "kind": "black", "message": "範例訊息"}])
        self.assert_pass(s, "no_false_black", "--pause-mute", "--status", st)
        detail = self.assert_fail(s, "no_false_black", "--pause-mute")  # 找不到狀態檔
        self.assertIn("record.status.json", detail)
        s = self.session(segs=[(0.0, 70.0)], pauses=[(70.0, "pause")], black=[(70.5, 71.0)])  # 暫停中停止
        self.assert_fail(s, "no_false_black", "--pause-mute", "--status", self.status(s))
        s = self.session(segs=[(0.0, 70.0)])
        self.assertIn(NOT_TRIGGERED, self.assert_fail(s, "no_false_black", "--pause-mute", "--status", self.status(s)))

    # spec §4.18.12
    def test_event_output_t_check(self):
        # spec §3.11 的範例（startedAt_1＝0.182）
        pev = [{"t": 70.012, "outputT": 69.830, "wallClock": "2026-10-12T21:01:10+08:00", "kind": "pause"},
               {"t": 100.004, "outputT": 69.830, "wallClock": "2026-10-12T21:01:40+08:00", "kind": "resume"}]
        mev = [{"t": 60.020, "outputT": 59.838, "wallClock": "2026-10-12T21:01:00+08:00", "muted": True}]
        segs = [(0.182, 69.830), (100.004, 30.0)]
        s = self.session(segs=segs, raw_pauses=pev, raw_mutes=mev)
        self.assert_pass(s, "event_output_t", "--pause-mute")
        bad = [dict(mev[0], outputT=59.900)]
        s = self.session(segs=segs, raw_pauses=pev, raw_mutes=bad)
        self.assert_fail(s, "event_output_t", "--pause-mute")
        s = self.session(segs=segs, raw_pauses=[pev[0], dict(pev[1], outputT=99.822)], raw_mutes=mev)
        self.assert_fail(s, "event_output_t", "--pause-mute")  # resume 的 outputT 沒扣暫停
        s = self.session(segs=segs, raw_pauses=[], raw_mutes=[])
        self.assertIn(NOT_TRIGGERED, self.assert_fail(s, "event_output_t", "--pause-mute"))

    # spec §3.11、§3.12 的範例數字（record_to_output 語意同 Core outputTime）
    def test_record_to_output_examples(self):
        import tests.record.e2e_check as e2e

        p = [{"t": 70, "kind": "pause"}, {"t": 100, "kind": "resume"}]
        self.assertEqual([e2e.record_to_output(t, 0.2, p) for t in (50, 80, 130, 0.1)], [49.8, 69.8, 99.8, 0.0])
        self.assertEqual(e2e.record_to_output(160, 0.2, p + [{"t": 150, "kind": "pause"}]), 119.8)
        ex = [{"t": 70.012, "kind": "pause"}, {"t": 100.004, "kind": "resume"}]
        self.assertEqual(e2e.record_to_output(125.700, 0.182, ex), 95.526)
        self.assertEqual(e2e.record_to_output(100.004, 0.182, ex), 69.830)
        self.assertEqual(e2e.paused_total(ex), 29.992)
        self.assertEqual(e2e.paused_total([{"t": 5, "kind": "resume"}]), 0)


if __name__ == "__main__":
    unittest.main()

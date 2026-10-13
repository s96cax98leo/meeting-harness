"""e2e_check.py 的判準自我測試（紅燈階段就要綠）：每個判準都有已知 PASS 與已知 FAIL 的合成場次。

合成素材只在 TMPDIR 產生（spec §4.14.1）。
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.record import _media as m

E2E = Path(__file__).resolve().parent / "e2e_check.py"
FINALIZE_PY = Path(__file__).resolve().parents[2] / "bin" / "_record_finalize.py"
BASE_ARGS = ["--expect-min", "1", "--expect-max", "10", "--fps-interval", "00:01-00:04",
             "--space-interval", "00:01-00:04"]
DS_EVENTS = [(15.0, "output", "builtIn", "bluetooth"), (35.0, "output", "bluetooth", "builtIn")]


def check(session, *args):
    r = subprocess.run([sys.executable, str(E2E), str(session), "--json", *map(str, args)],
                       capture_output=True, text=True, timeout=300)
    if r.returncode not in (0, 1):
        raise AssertionError(f"e2e_check.py 回 {r.returncode}：{r.stderr}")
    return r.returncode, {x["check"]: x for x in json.loads(r.stdout)}


class TestE2ECheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="mh-e2e-"))
        mk = lambda name, **kw: m.build_e2e_session(cls.tmp / name, **kw)
        cls.base = mk("base")
        cls.fps30 = mk("fps30", fps=30)
        cls.fps120 = mk("fps120", fps=120)
        cls.black = mk("black", black=(1, 5))
        cls.mixed = mk("mixed", seg_sizes=[(320, 240), (240, 180), (320, 200)])
        long = dict(dur=50, fps=10, size=(160, 120), device_events=DS_EVENTS)
        cls.ds_pass = mk("ds_pass", silences=[(15, 17), (35, 37)], **long)
        cls.ds_fail = mk("ds_fail", silences=[(15, 19), (35, 37)], **long)
        cls.ds_quiet = mk("ds_quiet", silences=[(2, 3), (15, 17), (35, 37)], **long)
        # t6 第三輪（缺陷 K (b)，spec §4.9.1）：切換以外的低音量停頓 2.5 秒判 PASS、3 秒判 FAIL
        cls.ds_pause25 = mk("ds_pause25", silences=[(2, 4.5), (15, 17), (35, 37)], **long)
        cls.ds_pause3 = mk("ds_pause3", silences=[(2, 5), (15, 17), (35, 37)], **long)
        hfp = dict(dur=40, fps=10, size=(160, 120))
        cls.hfp_pass = mk("hfp_pass", silences=[(15, 16.5)], format_events=[(15.0, "system", 48000, 16000)], **hfp)
        cls.hfp_none = mk("hfp_none", silences=[(15, 16.5)], **hfp)
        cls.hfp_long = mk("hfp_long", silences=[(15, 19)], format_events=[(15.0, "system", 48000, 16000)], **hfp)
        # t6 第三輪（缺陷 K (b)，spec §4.9.3）：格式變更後的低音量停頓 2.5 秒判 PASS、3 秒判 FAIL
        cls.hfp_pause25 = mk("hfp_pause25", silences=[(15, 16.5), (30, 32.5)],
                             format_events=[(15.0, "system", 48000, 16000)], **hfp)
        cls.hfp_pause3 = mk("hfp_pause3", silences=[(15, 16.5), (30, 33)],
                            format_events=[(15.0, "system", 48000, 16000)], **hfp)
        cls.sync_pass = mk("sync_pass", dur=8, sync_offset=0.0)
        cls.sync_fail = mk("sync_fail", dur=8, sync_offset=0.3)
        # t6 第三輪（缺陷 K (a)，spec §4.9.3）：疊上 1 kHz 附近有能量的雜訊（語音替身）；嗶聲晚 150 ms
        cls.sync_noise = mk("sync_noise", dur=8, sync_offset=0.0, sync_noise=True)
        cls.sync_late150 = mk("sync_late150", dur=8, sync_offset=0.15)
        cls.bt = mk("bt", dur=181, fps=5, size=(160, 120), input_transport="bluetooth",
                    output_transport="bluetoothLE")
        # D20（--segment-writer）：段落為影片＋系統聲音＋麥克風三軌
        cls.sw = mk("sw", dur=6, fps=10, size=(160, 120), two_tracks=True)
        cls.sw_hfp = mk("sw_hfp", silences=[(15, 16.5)], format_events=[(15.0, "system", 48000, 16000)],
                        two_tracks=True, **hfp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def copy(self, src):
        dst = Path(tempfile.mkdtemp(prefix="mh-e2e-mut-")) / "x" / src.name
        self.addCleanup(shutil.rmtree, dst.parents[1], True)
        shutil.copytree(src, dst)
        return dst

    def edit_json(self, path, fn):
        d = json.loads(path.read_text(encoding="utf-8"))
        fn(d)
        path.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    def tracks(self, s):
        return s / "錄音" / "tracks"

    def assert_fail(self, session, name, *args):
        rc, res = check(session, *args)
        self.assertIn(name, res)
        self.assertFalse(res[name]["ok"], f"{name} 應判 FAIL：{res[name]['detail']}")
        self.assertEqual(rc, 1)
        return res

    def assert_pass(self, session, name, *args):
        rc, res = check(session, *args)
        self.assertTrue(res[name]["ok"], f"{name} 應判 PASS：{res[name]['detail']}")
        return rc, res

    # ---- 已知 PASS：預設判準＋期望長度＋fps＋Space 區間全綠 ----
    def test_known_pass_session(self):
        rc, res = check(self.base, *BASE_ARGS)
        bad = {k: v["detail"] for k, v in res.items() if not v["ok"]}
        self.assertEqual(bad, {})
        self.assertEqual(rc, 0)
        for name in ("config_snapshot", "segment_files", "segment_sizes", "canvas", "video_format",
                     "video_covers_audio", "gap", "one_audio_file", "wav_format", "meeting_json", "levels",
                     "no_aggregate", "expect_duration", "fps_peak", "fps_min_interval", "space_interval"):
            self.assertIn(name, res)

    # spec §4.3.1
    def test_config_snapshot_check(self):
        s = self.copy(self.base)
        self.edit_json(self.tracks(s) / "record.meta.json", lambda d: d["config"].update(minimumFrameInterval="1/30"))
        self.assert_fail(s, "config_snapshot")
        s2 = self.copy(self.base)
        self.edit_json(self.tracks(s2) / "record.meta.json", lambda d: d["config"].pop("scalesToFit"))
        self.assert_fail(s2, "config_snapshot")

    # spec §4.3.2、§4.6.10：每段尺寸、輸出畫布＝各段最大寬高
    def test_canvas_check(self):
        rc, res = check(self.mixed)
        self.assertEqual(rc, 0, res)
        s = self.copy(self.base)
        self.edit_json(self.tracks(s) / "manifest.json", lambda d: d["outputCanvas"].update(width=999))
        self.assert_fail(s, "canvas")
        s2 = self.copy(self.base)
        self.edit_json(self.tracks(s2) / "manifest.json", lambda d: d["segments"][1].update(width=330))
        self.assert_fail(s2, "segment_sizes")
        self.assert_fail(s2, "canvas")

    # spec §4.3.3
    def test_fps_peak_check(self):
        self.assert_pass(self.base, "fps_peak", "--fps-interval", "00:01-00:04")
        self.assert_pass(self.base, "fps_min_interval", "--fps-interval", "00:01-00:04")
        self.assert_fail(self.fps30, "fps_peak", "--fps-interval", "00:01-00:04")
        self.assert_pass(self.fps120, "fps_peak", "--fps-interval", "00:01-00:04")
        self.assert_fail(self.fps120, "fps_min_interval", "--fps-interval", "00:01-00:04")

    # spec §4.3.3（t6 第三輪，發現 M；spec §6 第 68 條）：fps_min_interval 三條件
    # (i) 1 秒滑動窗 ≤ 61 格；(ii) 過近間隔數 ≤ 原始段落合計＋(段數 − 1)；(iii) 最小間隔 ≥ 1 ms
    def test_fps_min_interval_check(self):
        import tests.record.e2e_check as e2e

        in_seg = {30: 0.010, 150: 0.010, 270: 0.010}  # 最終片中三段各自原有的 10 ms 間隔（段內第 30 幀）

        def session(final_gaps):
            s = self.copy(self.base)
            for p in sorted(self.tracks(s).glob("seg-*.mov")):  # 原始段落：2 秒、60 fps，第 30 幀距前一幀 10 ms
                m.make_frame_timing_video(p, dur=2.0, gaps={30: 0.010})
            m.make_frame_timing_video(next((s / "影片").glob("*.mov")), dur=6.0, gaps=final_gaps)
            return s

        ok = session({**in_seg, 120: 0.00667})  # 只多 1 個邊界間隔（6.67 ms）
        seg = sorted(self.tracks(ok).glob("seg-*.mov"))[0]
        ts = sorted(e2e.frame_times(seg))
        self.assertEqual((e2e.close_intervals(ts), round(min(y - x for x, y in zip(ts, ts[1:])), 4)), (1, 0.01),
                         "合成素材前提：原始段落本身有 1 個 10 ms 間隔")
        _, res = self.assert_pass(ok, "fps_min_interval", "--fps-interval", "00:01-00:04")
        for k in ("(i)", "(ii)", "(iii)"):
            self.assertIn(k, res["fps_min_interval"]["detail"], "訊息應列出三個條件的數字")
        # (iii) 正規化把間隔擠成 < 1 ms（1/90000 秒，t6 缺陷 3 的樣子）
        self.assert_fail(session({**in_seg, 120: 1 / 90000}), "fps_min_interval", "--fps-interval", "00:01-00:04")
        # (ii) 過近間隔比原始多出段數以上（多 4 個 > 3 段的 2 個邊界）
        self.assert_fail(session({**in_seg, 60: 0.00667, 120: 0.00667, 240: 0.00667, 300: 0.00667}),
                         "fps_min_interval", "--fps-interval", "00:01-00:04")
        # (ii) 段落讀不到 → FAIL 並說明
        bad = self.copy(ok)
        m.truncate(self.tracks(bad) / "seg-0002.mov")
        res = self.assert_fail(bad, "fps_min_interval", "--fps-interval", "00:01-00:04")
        self.assertIn("seg-0002.mov", res["fps_min_interval"]["detail"])
        # fps120 由 (i) 擋（test_fps_peak_check 斷言判 FAIL）：1 秒窗 > 61 格，而 (ii) 本身不超過
        ts = sorted(e2e.frame_times(next((self.fps120 / "影片").glob("*.mov"))))
        self.assertGreater(e2e.window_peak(ts), 61)

    # spec §4.4.3
    def test_gap_check(self):
        self.assert_pass(self.base, "gap")
        s = self.copy(self.base)

        def widen(d):
            d["segments"][2]["startedAt"] += 0.6
            d.pop("gapStats")
        self.edit_json(self.tracks(s) / "manifest.json", widen)
        self.assert_fail(s, "gap")
        s2 = self.copy(self.base)
        self.edit_json(self.tracks(s2) / "manifest.json", lambda d: d["gapStats"].update(max=0.9))
        self.assert_fail(s2, "gap")

    # spec §4.8.1
    def test_expect_duration_check(self):
        self.assert_pass(self.base, "expect_duration", "--expect-min", "5", "--expect-max", "7")
        self.assert_fail(self.base, "expect_duration", "--expect-min", "60", "--expect-max", "125")
        self.assert_fail(self.base, "expect_duration", "--expect-max", "3")

    # spec §4.4.1、§4.4.4、§4.6.1–4.6.4、§4.5.7、§4.9.4 的預設判準：各一個已知 FAIL
    def test_default_criteria_fail_cases(self):
        s = self.copy(self.base)
        m.truncate(self.tracks(s) / "seg-0002.mov")
        self.assert_fail(s, "segment_files")
        s = self.copy(self.base)
        last = self.copy(self.base)
        m.truncate(self.tracks(last) / "seg-0003.mov")
        self.assert_pass(last, "segment_files")  # kill -9 時最後一段沒收尾是預期
        s = self.copy(self.base)
        v = next((s / "影片").glob("*.mov"))
        tmp = v.with_name("tmp.mov")
        m.ff("-i", v, "-map", "0:v", "-map", "0:a", "-map", "0:a", "-c", "copy", tmp)
        tmp.replace(v)
        self.assert_fail(s, "video_format")
        s = self.copy(self.base)
        v = next((s / "影片").glob("*.mov"))
        tmp = v.with_name("tmp.mov")
        m.ff("-t", "4", "-i", v, "-i", v, "-map", "0:v", "-map", "1:a", "-c", "copy", tmp)
        tmp.replace(v)
        self.assert_fail(s, "video_covers_audio")
        s = self.copy(self.base)
        wav = next((s / "錄音").glob("*.wav"))
        shutil.copy(wav, s / "錄音" / "多出來的.m4a")
        self.assert_fail(s, "one_audio_file")
        s = self.copy(self.base)
        wav = next((s / "錄音").glob("*.wav"))
        tmp = wav.with_name("tmp.wav")
        m.ff("-i", wav, "-ar", 44100, "-ac", 2, tmp)
        tmp.replace(wav)
        self.assert_fail(s, "wav_format")
        s = self.copy(self.base)
        wav = next((s / "錄音").glob("*.wav"))
        wav.rename(wav.with_name("沒有時間戳.wav"))
        self.assert_fail(s, "wav_format")
        s = self.copy(self.base)
        self.edit_json(s / "錄音" / "meeting.json", lambda d: d.pop("_note"))
        self.assert_fail(s, "meeting_json")
        s = self.copy(self.base)
        self.edit_json(s / "錄音" / "meeting.json", lambda d: d.update(expectedSpeakers=4))
        self.assert_fail(s, "meeting_json")
        s = self.copy(self.base)
        self.edit_json(self.tracks(s) / "manifest.json", lambda d: d["levels"].update(windowSeconds=1.0))
        self.assert_fail(s, "levels")
        s = self.copy(self.base)
        self.edit_json(self.tracks(s) / "record.meta.json",
                       lambda d: d["devices"]["output"].update(transport="aggregate"))
        self.assert_fail(s, "no_aggregate")

    # spec §4.9.1：2 秒中斷判 PASS、4 秒判 FAIL
    def test_device_switch_check(self):
        rc, res = check(self.ds_pass, "--device-switch")
        self.assertTrue(res["device_switch"]["ok"], res["device_switch"]["detail"])
        self.assertEqual(rc, 0, {k: v for k, v in res.items() if not v["ok"]})
        self.assert_fail(self.ds_fail, "device_switch", "--device-switch")
        # 切換以外的時間有 1 秒靜音：t6 第三輪（spec §6 第 66 條，使用者核准的測試修改）起不再判 FAIL
        self.assert_pass(self.ds_quiet, "device_switch", "--device-switch")
        s = self.copy(self.ds_pass)
        self.edit_json(self.tracks(s) / "record.meta.json", lambda d: d.update(deviceEvents=d["deviceEvents"][:1]))
        self.assert_fail(s, "device_switch", "--device-switch")  # 只有一次切換
        # t6 第三輪（缺陷 K (b)）：切換以外連續低音量 2.5 秒（5 個 0.5 秒時段）判 PASS、3 秒（6 個）判 FAIL
        self.assert_pass(self.ds_pause25, "device_switch", "--device-switch")
        res = self.assert_fail(self.ds_pause3, "device_switch", "--device-switch")
        self.assertIn("3 秒", res["device_switch"]["detail"])

    # spec §4.9.2
    def test_all_bluetooth_check(self):
        rc, res = check(self.bt, "--all-bluetooth")
        self.assertEqual(rc, 0, {k: v for k, v in res.items() if not v["ok"]})
        self.assert_fail(self.base, "all_bluetooth", "--all-bluetooth")
        self.assert_fail(self.base, "all_bluetooth_duration", "--all-bluetooth")

    # spec §4.9.3：HFP 格式事件與同步偏移
    def test_hfp_and_sync_check(self):
        def status_for(sess, warnings):
            p = sess.parent / "record.status.json"
            p.write_text(json.dumps({"session": str(sess), "warnings": warnings}, ensure_ascii=False),
                         encoding="utf-8")
            return p

        ok_status = status_for(self.copy(self.hfp_pass), [])
        sess = ok_status.parent / self.hfp_pass.name
        rc, res = check(sess, "--hfp", "--status", ok_status)
        self.assertTrue(res["hfp"]["ok"], res["hfp"]["detail"])
        self.assertEqual(rc, 0, {k: v for k, v in res.items() if not v["ok"]})
        res = self.assert_fail(self.hfp_none, "hfp", "--hfp")
        self.assertIn("情境未觸發", res["hfp"]["detail"])
        s = self.copy(self.hfp_pass)
        warn = status_for(s, [{"t": 20.0, "kind": "silence_mic", "message": "麥克風連續 15 秒沒有聲音"}])
        self.assert_fail(s, "hfp", "--hfp", "--status", warn)
        s = self.copy(self.hfp_long)
        self.assert_fail(s, "hfp", "--hfp", "--status", status_for(s, []))
        s = self.copy(self.hfp_pass)
        self.assert_fail(s, "hfp", "--hfp", "--status", s.parent / "不存在.json")
        rc, res = check(self.sync_pass, "--sync")
        self.assertTrue(res["sync"]["ok"], res["sync"]["detail"])
        self.assertEqual(rc, 0)
        self.assert_fail(self.sync_fail, "sync", "--sync")
        self.assert_fail(self.base, "sync", "--sync")  # 不是同步測試源：找不到閃白
        # t6 第三輪（缺陷 K (b)）：格式變更後的低音量停頓 2.5 秒判 PASS、3 秒判 FAIL
        s = self.copy(self.hfp_pause25)
        self.assert_pass(s, "hfp", "--hfp", "--status", status_for(s, []))
        s = self.copy(self.hfp_pause3)
        res = self.assert_fail(s, "hfp", "--hfp", "--status", status_for(s, []))
        self.assertIn("3 秒", res["hfp"]["detail"])
        # t6 第三輪（缺陷 K (a)）：疊上語音替身雜訊仍判 PASS；嗶聲晚 150 ms 判 FAIL
        import tests.record.e2e_check as e2e

        noisy = next((self.sync_noise / "影片").glob("*.mov"))
        f, b = e2e.flashes(noisy), e2e.beeps(noisy)
        old_worst = max(abs(min((x - t for x in b), key=abs)) for t in f) if f and b else None
        self.assertTrue(old_worst is None or old_worst >= 0.1,
                        f"合成素材前提：前一版全頻 RMS 量法在這份素材上會誤判（最大差 {old_worst}）")
        rc, res = check(self.sync_noise, "--sync")
        self.assertTrue(res["sync"]["ok"], res["sync"]["detail"])
        self.assertEqual(rc, 0, {k: v for k, v in res.items() if not v["ok"]})
        self.assert_fail(self.sync_late150, "sync", "--sync")
        late = [d for _, d in e2e.sync_offsets(next((self.sync_late150 / "影片").glob("*.mov"))) if d is not None]
        self.assertTrue(late and all(0.1 <= d < 0.2 for d in late), f"嗶聲晚 150 ms 應量得到約 150 ms：{late}")

    # spec §4.10.2、§4.15.16
    def test_space_interval_check(self):
        self.assert_pass(self.base, "space_interval", "--space-interval", "00:01-00:04")
        self.assert_fail(self.black, "space_interval", "--space-interval", "00:02-00:04")
        self.assert_pass(self.black, "space_interval", "--space-interval", "00:00-00:01")

    # ---- D20：--segment-writer（spec §6 第 53 條：不加進預設判準） ----

    def cadence60(self, d):
        """把 manifest 的 startedAt／finishedAt 改成 60 秒週期（合成段落只有 2 秒長，只核對時間欄位的判準用）。"""
        for i, r in enumerate(d["segments"]):
            r["startedAt"] = 60.0 * i + 0.012
            r["requestedAt"] = 60.0 * i + 0.010 if i else 0.0
            r["finishedAt"] = 60.0 * (i + 1) + 0.012 + 0.8
        d["gapStats"]["wallClock"] = d["segments"][0]["startedAt"] + sum(r["audioDuration"] for r in d["segments"])

    # spec §4.4.1：每段恰有 1 條 H.264 影片軌＋2 條 AAC 音軌（影片、系統聲音、麥克風）；
    # spec §4.4.3 (a)：gap 取各音軌最長、判 |g_i|
    def test_segment_tracks_check(self):
        rc, res = check(self.base)
        self.assertNotIn("segment_tracks", res, "D20 判準不得加進預設判準（spec §6 第 53 條）")
        self.assert_pass(self.sw, "segment_tracks", "--segment-writer")
        self.assert_fail(self.base, "segment_tracks", "--segment-writer")  # D20 之前的單音軌段落
        s = self.copy(self.sw)  # 順序錯：音軌在影片之前
        seg = self.tracks(s) / "seg-0002.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-i", seg, "-map", "0:a:0", "-map", "0:v:0", "-map", "0:a:1", "-c", "copy", tmp)
        tmp.replace(seg)
        self.assert_fail(s, "segment_tracks", "--segment-writer")
        s = self.copy(self.sw)  # 少了麥克風軌
        seg = self.tracks(s) / "seg-0001.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-i", seg, "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", tmp)
        tmp.replace(seg)
        self.assert_fail(s, "segment_tracks", "--segment-writer")
        self.assertIn("--segment-writer", subprocess.run([sys.executable, str(E2E), "--help"], capture_output=True,
                                                         text=True).stdout)
        # gap：兩條音軌時取較長者（系統聲音軌短 0.6 秒、麥克風軌完整 → 空隙仍小）
        self.assert_pass(self.sw, "gap")
        s = self.copy(self.sw)
        seg = self.tracks(s) / "seg-0001.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-i", seg, "-t", "1.4", "-i", seg, "-map", "0:v:0", "-map", "1:a:0", "-map", "0:a:1", "-c", "copy", tmp)
        tmp.replace(seg)
        ads = [float(x["duration"]) for x in m.streams(seg, "audio")]
        self.assertTrue(ads[0] < 1.5 < ads[1], f"合成素材前提：只有系統聲音軌被截短：{ads}")
        self.assert_pass(s, "gap")
        # gap：負的空隙（兩段重疊 0.6 秒）也要擋
        s = self.copy(self.base)

        def overlap(d):
            d["segments"][2]["startedAt"] -= 0.6
            d.pop("gapStats")
        self.edit_json(self.tracks(s) / "manifest.json", overlap)
        self.assert_fail(s, "gap")

    # spec §4.4.3 (b)(c)、§4.4.8：段落確實收尾、換段週期恰 60 秒、停止時最後一段寫到停止點
    def test_segment_finished_check(self):
        s = self.copy(self.sw)
        self.edit_json(self.tracks(s) / "manifest.json", self.cadence60)
        rc, res = check(s, "--segment-writer")
        for name in ("segment_finished", "segment_cadence", "stop_tail"):
            self.assertTrue(res[name]["ok"], f"{name} 應判 PASS：{res[name]['detail']}")
        # (b) 某段 finishedAt 為 null（t6 的失敗模式：各段都沒收尾）
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["segments"][1].update(finishedAt=None))
        self.assert_fail(f, "segment_finished", "--segment-writer")
        # (b) 最後一段在正常 stop 後也不得是 null
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["segments"][-1].update(finishedAt=None))
        self.assert_fail(f, "segment_finished", "--segment-writer")
        # (b) 舊段在換段後 5 秒以上才收尾
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json",
                       lambda d: d["segments"][0].update(finishedAt=d["segments"][1]["startedAt"] + 5.0))
        self.assert_fail(f, "segment_finished", "--segment-writer")
        # (c) 間隔 60.002 秒（超過 0.001 容許）
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json",
                       lambda d: d["segments"][1].update(startedAt=d["segments"][1]["startedAt"] + 0.002))
        self.assert_fail(f, "segment_cadence", "--segment-writer")
        # (c) 現行合成場次（2 秒一段）不是 60 秒週期
        self.assert_fail(self.sw, "segment_cadence", "--segment-writer")
        # (c) t6 的 SCRecordingOutput 段落：startedAt 為 null
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["segments"][1].update(startedAt=None))
        self.assert_fail(f, "segment_cadence", "--segment-writer")
        # §4.4.8 停止點之後被截掉：wallClock 比 startedAt_1 + Σ audioDuration 長 1 秒以上
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["gapStats"].update(wallClock=d["gapStats"]["wallClock"] + 1.5))
        self.assert_fail(f, "stop_tail", "--segment-writer")
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["gapStats"].pop("wallClock"))
        self.assert_fail(f, "stop_tail", "--segment-writer")
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "manifest.json", lambda d: d["gapStats"].update(wallClock=d["gapStats"]["wallClock"] - 0.9))
        self.assert_pass(f, "stop_tail", "--segment-writer")

    # spec §4.4.4：seg-0002 起每段含 video stream，影片軌 start_time ≤ 0.05 秒
    def test_segment_video_start_check(self):
        self.assert_pass(self.sw, "segment_video_start", "--segment-writer")
        s = self.copy(self.sw)  # 影片晚 0.3 秒才開始
        seg = self.tracks(s) / "seg-0002.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-itsoffset", "0.3", "-i", seg, "-i", seg, "-map", "0:v:0", "-map", "1:a:0", "-map", "1:a:1",
             "-c", "copy", tmp)
        tmp.replace(seg)
        self.assertGreater(float(m.stream(seg, "video")["start_time"]), 0.05, "合成素材前提：影片軌晚開始")
        self.assert_fail(s, "segment_video_start", "--segment-writer")
        s = self.copy(self.sw)  # 靜止視窗：第二段沒有 video stream
        seg = self.tracks(s) / "seg-0002.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-i", seg, "-map", "0:a:0", "-map", "0:a:1", "-c", "copy", tmp)
        tmp.replace(seg)
        self.assert_fail(s, "segment_video_start", "--segment-writer")
        s = self.copy(self.sw)  # 只有第一段影片晚開始不算（第一段影片從第一幀開始，design §7.2）
        seg = self.tracks(s) / "seg-0001.mov"
        tmp = seg.with_name("tmp.mov")
        m.ff("-itsoffset", "0.3", "-i", seg, "-i", seg, "-map", "0:v:0", "-map", "1:a:0", "-map", "1:a:1",
             "-c", "copy", tmp)
        tmp.replace(seg)
        self.assert_pass(s, "segment_video_start", "--segment-writer")
        one = self.copy(self.sw)  # 沒跨過換段
        for p in sorted(self.tracks(one).glob("seg-*.mov"))[1:]:
            p.unlink()
        self.assert_fail(one, "segment_video_start", "--segment-writer")

    # spec §4.9.3（D20）：格式變更提前換段；只在 --hfp 與 --segment-writer 同時給時才跑
    def test_format_rotation_check(self):
        def status_for(sess, warnings):
            p = sess.parent / "record.status.json"
            p.write_text(json.dumps({"session": str(sess), "warnings": warnings}, ensure_ascii=False),
                         encoding="utf-8")
            return p

        def rotate_at(t):
            def fn(d):
                d["segments"][1]["startedAt"] = t
            return fn

        s = self.copy(self.sw_hfp)
        self.edit_json(self.tracks(s) / "manifest.json", rotate_at(15.2))
        st = status_for(s, [])
        rc, res = check(s, "--hfp", "--status", st)
        self.assertNotIn("format_rotation", res, "只給 --hfp 時不跑 format_rotation（既有 --hfp 判準不變）")
        rc, res = check(s, "--segment-writer", "--status", st)
        self.assertNotIn("format_rotation", res, "只給 --segment-writer 時不跑 format_rotation")
        self.assert_pass(s, "format_rotation", "--hfp", "--segment-writer", "--status", st)
        # 邊界離格式變更 0.6 秒（≥ 0.5）
        f = self.copy(self.sw_hfp)
        self.edit_json(self.tracks(f) / "manifest.json", rotate_at(15.6))
        self.assert_fail(f, "format_rotation", "--hfp", "--segment-writer", "--status", status_for(f, []))
        # 沒有提前換段（原本的 2 秒週期剛好不在 15 秒附近）
        f = self.copy(self.sw_hfp)
        self.assert_fail(f, "format_rotation", "--hfp", "--segment-writer", "--status", status_for(f, []))
        # 同一路 1 秒內的第二筆變更不要求邊界；超過 1 秒的第二筆要
        f = self.copy(s)

        def add_event(t):
            def fn(d):
                d["audioFormatEvents"].append({"t": t, "source": "system", "from": d["audioFormatEvents"][0]["to"],
                                               "to": d["audioFormatEvents"][0]["from"]})
            return fn
        self.edit_json(self.tracks(f) / "record.meta.json", add_event(15.8))
        self.assert_pass(f, "format_rotation", "--hfp", "--segment-writer", "--status", status_for(f, []))
        f = self.copy(s)
        self.edit_json(self.tracks(f) / "record.meta.json", add_event(30.0))
        self.assert_fail(f, "format_rotation", "--hfp", "--segment-writer", "--status", status_for(f, []))
        # 出現 segment_write_failed
        f = self.copy(s)
        warn = status_for(f, [{"t": 20.0, "kind": "segment_write_failed", "message": "seg-0002.mov 寫檔失敗（範例）"}])
        self.assert_fail(f, "format_rotation", "--hfp", "--segment-writer", "--status", warn)
        # 找不到 record.status.json
        self.assert_fail(s, "format_rotation", "--hfp", "--segment-writer", "--status", s.parent / "不存在.json")
        # 情境未觸發：沒有 sampleRate 改變
        f = self.copy(self.sw)
        res = self.assert_fail(f, "format_rotation", "--hfp", "--segment-writer", "--status", status_for(f, []))
        self.assertIn("情境未觸發", res["format_rotation"]["detail"])

    # spec §4.4.3 (c)（t6 第二輪，缺陷 G）：提前換段（任何欄位的格式變更、或前一段 writer 失敗）不受 60.000 秒約束
    def test_segment_cadence_excludes_early_rotation(self):
        def fmt(rate=48000, ch=2, interleaved=False):
            return {"sampleRate": rate, "channels": ch, "interleaved": interleaved, "sampleType": "float32"}

        def session(starts, finished, events):
            s = self.copy(self.sw)
            tr = self.tracks(s)
            segs = sorted(tr.glob("seg-*.mov"))
            for k in range(len(segs), len(starts)):  # 補足段落檔（只核對時間欄位，內容沿用最後一段）
                shutil.copyfile(segs[-1], tr / f"seg-{k + 1:04d}.mov")

            def fn(d):
                base = d["segments"][-1]
                recs = []
                for k, (st, fin) in enumerate(zip(starts, finished)):
                    r = dict(d["segments"][k] if k < len(d["segments"]) else base)
                    r.update(file=f"seg-{k + 1:04d}.mov", requestedAt=max(st - 0.002, 0.0), startedAt=st,
                             finishedAt=fin)
                    recs.append(r)
                d["segments"] = recs
                d["gapStats"]["wallClock"] = starts[-1] + 60.0
            self.edit_json(tr / "manifest.json", fn)
            self.edit_json(tr / "record.meta.json", lambda d: d.update(audioFormatEvents=events))
            return s

        # 60 秒定期換段 → 只改 interleaved 的格式變更提前換段 → 緊接 sampleRate 改變的提前換段 → 60 秒定期換段
        starts = [0.012, 60.012, 72.312, 80.112, 140.112]
        finished = [60.8, 72.9, 80.7, 140.9, 150.0]
        events = [{"t": 72.2, "source": "mic", "from": fmt(), "to": fmt(interleaved=True)},
                  {"t": 80.0, "source": "system", "from": fmt(), "to": fmt(rate=16000, ch=1)}]
        _, res = self.assert_pass(session(starts, finished, events), "segment_cadence", "--segment-writer")
        # 前一段 writer 失敗（finishedAt 為 null）後的提前換段也不計
        _, res = self.assert_pass(session([0.012, 60.012, 75.512, 135.512], [60.8, None, 136.3, 150.0], []),
                                  "segment_cadence", "--segment-writer")
        # 45 秒間隔、附近沒有格式事件、前一段 finishedAt 非 null → FAIL
        res = self.assert_fail(session([0.012, 60.012, 105.012, 165.012], [60.8, 105.8, 165.8, 170.0], events),
                               "segment_cadence", "--segment-writer")
        self.assertIn("seg-0003.mov", res["segment_cadence"]["detail"])
        # 格式事件離邊界 ≥ 0.5 秒不算提前換段
        far = [{"t": 72.2 - 0.6, "source": "mic", "from": fmt(), "to": fmt(interleaved=True)}]
        self.assert_fail(session(starts[:3], finished[:3], far), "segment_cadence", "--segment-writer")
        # 提前換段只認「短於」60 秒：比 60.000 長的間隔照判 FAIL，即使附近有格式事件
        late = [{"t": 61.0, "source": "system", "from": fmt(), "to": fmt(rate=16000, ch=1)}]
        self.assert_fail(session([0.012, 61.012], [61.8, 70.0], late), "segment_cadence", "--segment-writer")

    # spec §4.6.19（t6 第二輪，缺陷 F2）：e2e_check.py 的 gap 與 finalize 的 gapStats 用同一把尺（§3.2 audioDuration）
    def test_gap_uses_finalize_audio_duration(self):
        import tests.record.e2e_check as e2e

        spec = importlib.util.spec_from_file_location("_record_finalize_ro", FINALIZE_PY)
        fin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fin)  # 只讀、不改 bin/_record_finalize.py
        work = Path(tempfile.mkdtemp(prefix="mh-e2e-f2-"))
        self.addCleanup(shutil.rmtree, work, True)
        amp = m.sine_amp(-20.0)
        late = work / "late_audio.mov"  # (1) 影片從 0 開始、兩條音軌分別晚 0.2 與 0.3 秒開始
        m.ff("-f", "lavfi", "-i", "testsrc2=s=160x120:r=10:d=3",
             "-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*440*t)':s=48000:c=stereo:d=2.8",
             "-f", "lavfi", "-i", f"aevalsrc='{amp}*sin(2*PI*1000*t)':s=48000:c=mono:d=2.7",
             "-filter_complex", "[1:a]adelay=200|200[a0];[2:a]adelay=300[a1]",
             "-map", "0:v", "-map", "[a0]", "-map", "[a1]", "-c:v", "libx264", "-preset", "ultrafast",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-ac:a:0", "2", "-ac:a:1", "1", "-f", "mov", late)
        frag = m.make_fragment_segment(work / "fragment.mov")  # (2) §4.6.15 的截斷 fragment 段落
        one = m.make_segment(work / "one_track.mov", dur=2.0)  # (3) 只有一條音軌
        self.assertEqual(len(m.streams(late, "audio")), 2, "合成素材前提：(1) 有兩條音軌")
        self.assertEqual(len(m.streams(one, "audio")), 1, "合成素材前提：(3) 只有一條音軌")
        self.assertGreater(e2e.longest_audio_duration(frag) - fin.analyze(str(frag))["audioDuration"], 0.01,
                           "合成素材前提：(2) 的 stream 層 duration 與 §3.2 算法不同（舊 gap 的量法會不一致）")
        for label, path in (("(1) 音軌晚開始", late), ("(2) 截斷 fragment", frag), ("(3) 單音軌", one)):
            with self.subTest(segment=label):
                got = e2e.segment_audio_duration(path)
                want = fin.analyze(str(path))["audioDuration"]
                self.assertIsNotNone(got, f"{label}：segment_audio_duration 應量得到長度")
                self.assertLessEqual(abs(got - want), 0.001,
                                     f"{label}：segment_audio_duration {got} 與 finalize analyze {want} 差應 ≤ 0.001 秒")

        # gap 判準：以 finalize 的量法寫回 gapStats 的場次，不得因定義不同出現「與實測不符」
        s = self.copy(self.sw)
        tr = self.tracks(s)
        shutil.copyfile(frag, tr / "seg-0001.mov")
        shutil.copyfile(late, tr / "seg-0002.mov")
        segs = sorted(tr.glob("seg-*.mov"))
        ads = [fin.analyze(str(p))["audioDuration"] for p in segs]

        def write_gapstats(d):
            t = d["segments"][0]["startedAt"]
            for r, ad in zip(d["segments"], ads):
                r["startedAt"] = round(t, 3)
                r["audioDuration"] = round(ad, 3)
                t += ad + 0.02
            st = [r["startedAt"] for r in d["segments"]]
            gaps = [st[i + 1] - st[i] - ads[i] for i in range(len(st) - 1)]
            d["gapStats"].update(boundaries=gaps, max=max(gaps), total=sum(gaps))
        self.edit_json(tr / "manifest.json", write_gapstats)
        _, res = self.assert_pass(s, "gap")
        self.assertNotIn("與實測不符", res["gap"]["detail"])

    def test_print_sync_source_and_usage(self):
        r = subprocess.run([sys.executable, str(E2E), "--print-sync-source"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(r.stdout.startswith("ffplay -f lavfi "), r.stdout)
        self.assertIn("[out0]", r.stdout)
        self.assertIn("[out1]", r.stdout)
        h = subprocess.run([sys.executable, str(E2E), "--help"], capture_output=True, text=True)
        self.assertEqual(h.returncode, 0)
        for opt in ("--device-switch", "--all-bluetooth", "--hfp", "--sync", "--fps-interval", "--space-interval",
                    "--expect-min", "--expect-max", "--print-sync-source", "--json"):
            self.assertIn(opt, h.stdout)
        self.assertEqual(subprocess.run([sys.executable, str(E2E)], capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, str(E2E), "/nonexistent/範例"],
                                        capture_output=True).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, str(E2E), str(self.base), "--fps-interval", "1-2"],
                                        capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()

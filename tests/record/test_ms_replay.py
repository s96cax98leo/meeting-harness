"""重放量測工具 tools/bench/replay.py（meeting-speed spec §3.12、§4.11.9、§4.14.1、§4.14.2；Story G1、G4）。

替身：在暫存區組一個假 harness（複製 repo 的 bin/、config.json 與 tools/bench/，再把 bin/_record_finalize.py 換成
fakes/ms_fake_finalize.py、bin/meeting.sh 換成 fakes/ms_fake_meeting.sh），執行假 harness 裡的 tools/bench/replay.py。
前提（本檔的假設，見 docstring）：replay.py 以自身位置找 harness 根（tools/bench/ 的上兩層），以 python3 執行
<根>/bin/_record_finalize.py、以 bash 執行 <根>/bin/meeting.sh。
段落目錄＝錄製器的 錄音/tracks/ 形狀：seg-*.mov、manifest.json、record.meta.json（段落內容不會被替身讀）。
比對的計算邏輯（§4.11.9）以模組函式 compare_metrics(full_segments, incremental_segments) 驗（本檔的假設）。
"""
import json
import os
import shutil
import subprocess
import time
import unittest

from tests.record import test_ms_support as s

REPORT_KEYS = {"speed", "segments", "recordedSeconds", "stopToAudioReady", "stopToSpeakersMd", "stopToWav",
               "stopToVideo", "stopToAllReady", "verifySeconds", "workerBacklogAtStop", "videoPath", "flow"}
SECOND_KEYS = ("recordedSeconds", "stopToAudioReady", "stopToSpeakersMd", "stopToWav", "stopToVideo",
               "stopToAllReady", "verifySeconds")
SOURCE_NAME = "範例來源段落-不得外洩的目錄名"


def segs(*pairs):
    return [{"start": a, "end": b, "text": t} for a, b, t in pairs]


class ReplayCase(unittest.TestCase):
    def setUp(self):
        self.assertTrue(s.REPLAY_PY.is_file(), "tools/bench/replay.py 不存在（replay-bench 負責）")
        self.base = s.tmpdir(self)
        self.harness = self.base / "harness"
        shutil.copytree(s.BIN, self.harness / "bin")
        shutil.copy2(s.REPO / "config.json", self.harness / "config.json")
        shutil.copytree(s.REPLAY_PY.parent, self.harness / "tools" / "bench")
        shutil.copy2(s.FAKES / "ms_fake_finalize.py", self.harness / "bin" / "_record_finalize.py")
        shutil.copy2(s.FAKES / "ms_fake_meeting.sh", self.harness / "bin" / "meeting.sh")
        self.fin_log = self.base / "fin.log"
        self.meet_log = self.base / "meeting.log"

    def source(self, n=3, interval=10.0):
        src = self.base / SOURCE_NAME
        src.mkdir()
        rows = []
        for i in range(n):
            f = f"seg-{i + 1:04d}.mov"
            (src / f).write_bytes(os.urandom(1024))
            rows.append({"file": f, "requestedAt": round(max(i * interval - 0.005, 0.0), 3),
                         "startedAt": round(i * interval, 3), "finishedAt": round((i + 1) * interval, 3),
                         "width": 320, "height": 240, "audioDuration": None})
        (src / "manifest.json").write_text(json.dumps({"schemaVersion": 1, "segmentSeconds": interval,
                                                       "segments": rows}, ensure_ascii=False), encoding="utf-8")
        (src / "record.meta.json").write_text(json.dumps({"schemaVersion": 1, "window": {"title": s.SESSION}},
                                                         ensure_ascii=False), encoding="utf-8")
        return src

    def replay(self, src, *args, timeout=180, **env):
        e = s.base_env(None, FAKE_FIN_LOG=self.fin_log, FAKE_MEETING_LOG=self.meet_log, **env)
        t0 = time.time()
        r = s.run([s.PY, self.harness / "tools" / "bench" / "replay.py", src, *args], e, timeout=timeout)
        return r, t0

    def report(self, r):
        self.assertEqual(r.returncode, 0, s.out_of(r))
        try:
            return json.loads(r.stdout)
        except ValueError:
            self.fail(f"stdout 應是一份 JSON 報告{s.out_of(r)}")

    def events(self, log):
        return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines() if x.strip()] if log.is_file() else []


class TestMSReplay(ReplayCase):
    # spec §4.14.1：依各段 startedAt／finishedAt 的間隔除以 N 依序放入段落，最後一段放完才起收尾
    def test_speed_schedule(self):
        src = self.source(3, 10.0)
        r, t0 = self.replay(src, "--speed", "10")
        rep = self.report(r)
        self.assertEqual(rep.get("speed"), 10)
        self.assertEqual(rep.get("segments"), 3)
        self.assertAlmostEqual(rep.get("recordedSeconds"), 30.0, delta=0.1)
        start = [e for e in self.events(self.fin_log) if e["event"] == "start"]
        self.assertEqual(len(start), 1, "收尾應只起一次")
        self.assertEqual(start[0]["segFiles"], ["seg-0001.mov", "seg-0002.mov", "seg-0003.mov"], "收尾時段落應都已放入")
        self.assertEqual((start[0]["manifestSegments"], start[0]["allFinished"]), (3, True), "manifest 應已更新到最後一段")
        slow = start[0]["t"] - t0
        self.assertGreaterEqual(slow, 1.8, f"--speed 10：段落間隔 10 秒 → 每 1 秒放一段，最後一段放完約 2 秒以上才停止：{slow:.2f}")

        shutil.rmtree(src)
        self.fin_log.unlink()
        src = self.source(3, 10.0)
        r, t0 = self.replay(src, "--speed", "100")
        self.report(r)
        fast = [e for e in self.events(self.fin_log) if e["event"] == "start"][0]["t"] - t0
        self.assertLess(fast, slow - 1.0, f"--speed 100 應比 --speed 10 早停止：{fast:.2f} 對 {slow:.2f}")

    # spec §4.14.1：認到「音訊就緒：」就起 meeting.sh prep（只帶 MH_PREP_RUN_ID），不等影片
    def test_early_flow(self):
        rep = self.report(self.replay(self.source(2, 1.0), "--speed", "10")[0])
        self.assertEqual(rep.get("flow"), "early")
        preps = [e for e in self.events(self.meet_log) if e["event"] == "prep"]
        self.assertEqual(len(preps), 1, preps)
        self.assertTrue(preps[0]["runId"], "應帶 MH_PREP_RUN_ID")
        self.assertEqual(preps[0]["early"], "", "不得設 MH_PREP_EARLY")
        self.assertEqual(preps[0]["videoExists"], 0, "early 流程：prep 應在影片發佈前就起")
        ready = [e for e in self.events(self.fin_log) if e["event"] == "ready"]
        self.assertTrue(ready and preps[0]["t"] >= ready[0]["t"], "prep 應在「音訊就緒：」之後起")
        self.assertLessEqual(rep["stopToAudioReady"], rep["stopToVideo"])

    # spec §4.14.1：--legacy 或收尾沒有印「音訊就緒：」時，等收尾結束才起 prep
    def test_legacy_flow(self):
        for label, args, env in (("--legacy", ("--legacy",), {}), ("沒有音訊就緒行", (), {"FAKE_FIN_NO_READY": "1"})):
            with self.subTest(case=label):
                for p in (self.fin_log, self.meet_log):
                    if p.exists():
                        p.unlink()
                moved = self.source(2, 1.0).rename(self.base / f"{label}-段落")
                rep = self.report(self.replay(moved, "--speed", "10", *args, **env)[0])
                self.assertEqual(rep.get("flow"), "legacy")
                preps = [e for e in self.events(self.meet_log) if e["event"] == "prep"]
                self.assertEqual(len(preps), 1, preps)
                self.assertEqual(preps[0]["videoExists"], 1, "legacy 流程：prep 應在收尾結束（影片已發佈）後才起")
                video = [e for e in self.events(self.fin_log) if e["event"] == "video"]
                self.assertTrue(video and preps[0]["t"] >= video[0]["t"])

    # spec §4.14.2、§3.12：報告的鍵恰為 §3.12 列的；秒數取小數 1 位
    def test_report_keys(self):
        rep = self.report(self.replay(self.source(2, 1.0), "--speed", "10")[0])
        self.assertEqual(set(rep), REPORT_KEYS)
        for k in SECOND_KEYS:
            v = rep[k]
            if v is not None:
                self.assertIsInstance(v, (int, float), k)
                self.assertEqual(round(v, 1), v, f"{k} 應取小數 1 位：{v}")
        self.assertEqual(rep["videoPath"], "reencode")

    # spec §4.14.2：報告不得含任何路徑、場次名或來源目錄名
    def test_report_no_paths(self):
        src = self.source(2, 1.0)
        r, _ = self.replay(src, "--speed", "10")
        self.report(r)
        for bad in ("/", SOURCE_NAME, s.SESSION, "範例專案", "Stand-up", str(self.base)):
            self.assertNotIn(bad, r.stdout, f"報告不得含「{bad}」")

    # spec §4.11.9：品質門檻的計算邏輯（字差異率去標點後逐字；對齊後時間差 ≤ 1.0 秒的比例）
    def test_compare_metrics(self):
        mod = s.load_module(s.REPLAY_PY, "_replay_ms_under_test")
        f = getattr(mod, "compare_metrics", None)
        self.assertTrue(callable(f), "tools/bench/replay.py 應有 compare_metrics(full_segments, incremental_segments)")
        twenty = "範例一二三四五六七八九十甲乙丙丁戊己庚辛"
        self.assertEqual(len(twenty), 20)
        ref = segs((0.0, 20.0, twenty))
        got = f(ref, ref)
        self.assertEqual((got["cer"], got["timeAlignedRatio"]), (0.0, 1.0), "完全相同：CER 0、比例 1")
        one_sub = segs((0.0, 20.0, twenty[:10] + "壬" + twenty[11:]))
        self.assertAlmostEqual(f(ref, one_sub)["cer"], 0.05, delta=1e-6, msg="20 字錯 1 字：CER 5%")
        self.assertEqual(f(segs((0.0, 4.0, "範例，內容。")), segs((0.0, 4.0, "範例內容")))["cer"], 0.0, "去標點後比")
        shifted = f(ref, segs((5.0, 25.0, twenty)))
        self.assertEqual(shifted["cer"], 0.0)
        self.assertEqual(shifted["timeAlignedRatio"], 0.0, "整段晚 5 秒：沒有字在 1.0 秒內")
        two = segs((0.0, 10.0, twenty[:10]), (10.0, 20.0, twenty[10:]))
        half = f(two, segs((0.0, 10.0, twenty[:10]), (15.0, 25.0, twenty[10:])))
        self.assertAlmostEqual(half["timeAlignedRatio"], 0.5, delta=0.01, msg="後半段晚 5 秒：比例 0.5")


if __name__ == "__main__":
    unittest.main()

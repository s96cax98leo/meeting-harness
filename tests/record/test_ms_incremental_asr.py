"""增量轉錄 worker 與 stitch（meeting-speed spec §3.6、§3.9、§4.11.2–§4.11.7；Story G2、G4、G1）。

`python3 bin/lib/_asr_worker.py run <場次>`、`… stitch <場次> <out.json>`；模型一律用 fakes/pymod/mlx_whisper
（PYTHONPATH 最前面；記錄匯入、載入模型與每次 transcribe() 呼叫）。錄製狀態由暫存 MH_RECORD_HOME 的
record.status.json 給（phase、droppedFrames）；別場背景收尾用 finalizing/<runId>.status.json（pid 活著＋持有 .lock）。
worker 不存在時每支測試以 assert 判 FAIL（incremental-asr 負責轉綠）。合成素材只在 TMPDIR；輪詢有上限、條件成立就繼續。
"""
import json
import os
import subprocess
import unittest

from tests.record import _media as m
from tests.record import test_ms_support as s

SEG = 10.0
WIN = 0.5
OTHER_RUN = "6F1C0000-0000-4000-8000-0000000C0002"


def silence_levels(n_segs, silences):
    """每段 10 秒、窗 0.5 秒的 levels：預設 -20 dBFS，silences＝[(起, 迄)]（成品秒）內為 -90 dBFS。"""
    n = int(n_segs * SEG / WIN)
    out = []
    for i in range(n):
        t = i * WIN
        out.append(-90.0 if any(a <= t < b for a, b in silences) else -20.0)
    return out


class WorkerCase(unittest.TestCase):
    def setUp(self):
        self.assertTrue(s.ASR_WORKER_PY.is_file(), "bin/lib/_asr_worker.py 不存在（incremental-asr 負責）")
        self.base = s.tmpdir(self)
        self.home = self.base / "home"
        self.home.mkdir()
        self.pylog = self.base / "pymod.log"
        self.procs = []

    def tearDown(self):
        for p in self.procs:
            s.kill_quietly(p)

    def session(self, n_segs=2, silences=(), unfinished=(), sub="根"):
        sess = s.record_session(self.base / sub, [dict(dur=SEG)] * n_segs, name=m.SESSION_NAME, gap=0.0)
        mp = s.tracks_of(sess) / "manifest.json"
        man = json.loads(mp.read_text(encoding="utf-8"))
        lv = silence_levels(n_segs, silences)
        man["levels"] = {"windowSeconds": WIN, "system": lv, "mic": list(lv)}
        for i in unfinished:
            man["segments"][i - 1]["finishedAt"] = None
        self.write_manifest(sess, man)
        return sess

    def write_manifest(self, sess, man):
        mp = s.tracks_of(sess) / "manifest.json"
        tmp = mp.with_name("manifest.json.tmp")
        tmp.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, mp)

    def finish_segment(self, sess, i):
        man = json.loads((s.tracks_of(sess) / "manifest.json").read_text(encoding="utf-8"))
        seg = man["segments"][i - 1]
        seg["finishedAt"] = round(seg["startedAt"] + SEG, 3)
        self.write_manifest(sess, man)

    def status(self, sess, phase, **extra):
        fields = dict(phase=phase, pid=os.getpid(), session=str(sess), droppedFrames=0)
        fields.update(extra)
        s.write_status(self.home, **fields)

    def env(self, **extra):
        return s.base_env(self.home, PYTHONPATH=s.PYMOD_DIR, FAKE_PYMOD_LOG=self.pylog, **extra)

    def start_worker(self, sess):
        p = subprocess.Popen([s.PY, str(s.ASR_WORKER_PY), "run", str(sess)], env=self.env(),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.procs.append(p)
        return p

    def run_worker(self, sess, timeout=120):
        r = s.run([s.PY, s.ASR_WORKER_PY, "run", sess], self.env(), timeout=timeout)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        return r

    def state(self, sess):
        p = s.tracks_of(sess) / "asr" / "state.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def windows(self, sess):
        return sorted((self.state(sess) or {}).get("windows") or [], key=lambda w: w["index"])

    def wait_windows(self, sess, n, timeout=60):
        ok = s.wait_until(lambda: len(self.windows(sess)) >= n, timeout=timeout)
        self.assertTrue(ok, f"{timeout} 秒內應完成 {n} 窗：{self.state(sess)}")

    def write_audio_ready(self, sess):
        tracks = s.tracks_of(sess)
        man = json.loads((tracks / "manifest.json").read_text(encoding="utf-8"))
        rows, start = [], 0.0
        for x in man["segments"]:
            d = round(x["finishedAt"] - x["startedAt"], 3)
            rows.append({"file": x["file"], "size": (tracks / x["file"]).stat().st_size, "duration": d,
                         "start": round(start, 3)})
            start += d
        (tracks / "audio-ready.json").write_text(json.dumps({
            "schemaVersion": 1, "wav": f"{m.SESSION_NAME} 2026-10-21 09.30.00.wav", "stamp": "2026-10-21 09.30.00",
            "compensation": "off", "segments": rows, "createdAt": "2026-10-21T11:30:12+08:00"}, ensure_ascii=False),
            encoding="utf-8")

    def stitch(self, sess, out, timeout=120):
        return s.run([s.PY, s.ASR_WORKER_PY, "stitch", sess, out], self.env(), timeout=timeout)

    def completed(self, n_segs=2, silences=()):
        sess = self.session(n_segs, silences)
        self.status(sess, "done")
        self.run_worker(sess)
        self.assertEqual((self.state(sess) or {}).get("status"), "complete")
        self.write_audio_ready(sess)
        return sess


class TestMSIncrementalAsr(WorkerCase):
    # spec §4.11.2：只處理 manifest 裡 finishedAt 不是 null 的段落
    def test_reads_finished_segments_only(self):
        sess = self.session(3, silences=[(4.0, 7.0), (14.0, 17.0)], unfinished=(3,))
        self.status(sess, "recording")
        self.start_worker(sess)
        self.wait_windows(sess, 2)
        st = self.state(sess)
        self.assertEqual(st.get("status"), "running", st)
        self.assertTrue(all(w["end"] <= 2 * SEG + 1e-3 for w in self.windows(sess)),
                        f"還沒收尾的第 3 段不得被轉錄：{self.windows(sess)}")
        self.assertFalse(s.wait_until(lambda: len(self.windows(sess)) > 2, timeout=3.0),
                         "第 3 段 finishedAt 為 null 時不得開第 3 窗")

    # spec §4.11.2：同一場只能有一個 worker（worker.lock）
    def test_single_worker_lock(self):
        sess = self.session(2, unfinished=(2,))
        self.status(sess, "recording")
        w1 = self.start_worker(sess)
        self.assertTrue(s.wait_until(lambda: self.state(sess) is not None, timeout=60), "第一個 worker 應寫 state.json")
        w2 = self.start_worker(sess)
        self.assertTrue(s.wait_until(lambda: w2.poll() is not None, timeout=30), "第二個 worker 拿不到 worker.lock 應立即結束")
        self.assertIsNone(w1.poll(), "第一個 worker 應仍在跑")
        self.assertTrue((s.tracks_of(sess) / "asr" / "worker.lock").exists())

    # spec §4.11.3：切點＝第 k 段最後 8 秒內、兩個有聲區間之間最晚那個靜音區間的中點（VAD 參數同整檔轉錄）
    def test_cut_at_silence(self):
        # 第 1 段 4–7 秒無聲：有聲 [0,4]、[7,…] 補 0.75 秒後的靜音區間是 [4.75, 6.25]，中點 5.5
        sess = self.completed(2, silences=[(4.0, 7.0)])
        w = self.windows(sess)
        self.assertGreaterEqual(len(w), 2, w)
        self.assertAlmostEqual(w[0]["start"], 0.0, delta=1e-3)
        self.assertAlmostEqual(w[0]["end"], 5.5, delta=0.01, msg=f"第 1 窗應切在靜音中點 5.5 秒：{w}")

    # spec §4.11.3：最後 8 秒內找不到靜音區間時在段尾硬切
    def test_cut_hard_when_no_silence(self):
        sess = self.completed(2)
        w = self.windows(sess)
        self.assertGreaterEqual(len(w), 2, w)
        self.assertAlmostEqual(w[0]["end"], SEG, delta=0.01, msg=f"沒有靜音時第 1 窗應在第 1 段結尾硬切：{w}")

    # spec §4.11.3：窗與窗不重疊、首尾相接，涵蓋整場
    def test_windows_non_overlapping(self):
        sess = self.completed(3, silences=[(4.0, 7.0), (24.0, 27.0)])
        w = self.windows(sess)
        self.assertEqual([x["index"] for x in w], list(range(w[0]["index"], w[0]["index"] + len(w))), "窗號應連續")
        self.assertAlmostEqual(w[0]["start"], 0.0, delta=1e-3)
        for a, b in zip(w, w[1:]):
            self.assertAlmostEqual(b["start"], a["end"], delta=1e-3, msg=f"窗應首尾相接、不重疊：{a} {b}")
            self.assertGreater(b["end"], b["start"])
        self.assertAlmostEqual(w[-1]["end"], 3 * SEG, delta=0.05, msg="最後一窗應延伸到最後一段結尾")

    # spec §4.11.4：錄製中 droppedFrames 大於 worker 起來時的值 → 不再開新窗、paused/drops，直到 phase 離開 recording/stopping
    def test_pause_on_drops_until_stop(self):
        sess = self.session(3, unfinished=(2, 3))
        self.status(sess, "recording", droppedFrames=0)
        self.start_worker(sess)
        self.wait_windows(sess, 1)
        self.status(sess, "recording", droppedFrames=3)
        ok = s.wait_until(lambda: (self.state(sess) or {}).get("status") == "paused", timeout=30)
        self.assertTrue(ok, f"丟幀數增加後應暫停：{self.state(sess)}")
        self.assertEqual(self.state(sess).get("pausedReason"), "drops")
        self.finish_segment(sess, 2)
        self.assertFalse(s.wait_until(lambda: len(self.windows(sess)) > 1, timeout=3.0), "暫停期間不得開新窗")
        self.status(sess, "stopping", droppedFrames=3)
        self.assertFalse(s.wait_until(lambda: len(self.windows(sess)) > 1, timeout=2.0), "stopping 期間仍暫停")
        self.finish_segment(sess, 3)
        self.status(sess, "finalizing", droppedFrames=3)
        ok = s.wait_until(lambda: (self.state(sess) or {}).get("status") == "complete", timeout=90)
        self.assertTrue(ok, f"phase 變成 finalizing 後應補完所有窗：{self.state(sess)}")
        self.assertAlmostEqual(self.windows(sess)[-1]["end"], 3 * SEG, delta=0.05)

    # spec §4.11.4：錄製中有別場背景收尾的 pid 還活著時不開新窗（otherFinalizing）
    def test_pause_when_other_finalizing(self):
        sess = self.session(2, unfinished=(2,))
        other = subprocess.Popen(["sleep", "120"])
        self.addCleanup(lambda: (other.poll() is None and other.kill(), other.wait()))
        fdir = self.home / "finalizing"
        fdir.mkdir()
        (fdir / f"{OTHER_RUN}.status.json").write_text(json.dumps({
            "schemaVersion": 1, "runId": OTHER_RUN, "pid": other.pid, "phase": "finalizing", "code": 0, "message": "",
            "session": str(self.base / "別場"), "startedAt": "2026-10-21T08:00:00+08:00",
            "updatedAt": "2026-10-21T09:00:00+08:00", "segments": 3}), encoding="utf-8")
        lock = s.HeldLock(fdir / f"{OTHER_RUN}.lock").acquire()
        self.addCleanup(lock.release)
        self.status(sess, "recording")
        self.start_worker(sess)
        ok = s.wait_until(lambda: (self.state(sess) or {}).get("pausedReason") == "otherFinalizing", timeout=30)
        self.assertTrue(ok, f"別場背景收尾還活著時應暫停（otherFinalizing）：{self.state(sess)}")
        self.assertEqual(self.windows(sess), [], "暫停期間不得開新窗")
        other.kill()
        other.wait()
        lock.release()
        (fdir / f"{OTHER_RUN}.status.json").unlink()
        self.wait_windows(sess, 1, timeout=60)

    # spec §4.11.5：phase 變成 finalizing／done／failed 時補完所有窗、最後一窗到最後一段結尾、status＝complete 後結束
    def test_completes_after_stop(self):
        sess = self.session(2, unfinished=(2,))
        self.status(sess, "recording")
        w = self.start_worker(sess)
        self.wait_windows(sess, 1)
        self.finish_segment(sess, 2)
        self.status(sess, "done")
        self.assertTrue(s.wait_until(lambda: w.poll() is not None, timeout=90), "停止後 worker 應補完並結束")
        self.assertEqual(w.returncode, 0)
        st = self.state(sess)
        self.assertEqual(st.get("status"), "complete", st)
        win = self.windows(sess)
        self.assertAlmostEqual(win[-1]["end"], 2 * SEG, delta=0.05)
        for x in win:
            self.assertTrue((s.tracks_of(sess) / "asr" / x["file"]).is_file(), f"每窗應有結果檔：{x}")

    # spec §4.11.6：一次執行只載入模型一次（in-process mlx_whisper.transcribe()）
    def test_model_loaded_once(self):
        sess = self.completed(3, silences=[(4.0, 7.0)])
        events = [json.loads(x) for x in self.pylog.read_text(encoding="utf-8").splitlines() if x.strip()]
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds.count("import"), 1, f"mlx_whisper 應只匯入一次（同一個程序）：{kinds}")
        self.assertEqual(kinds.count("load"), 1, f"模型應只載入一次：{kinds}")
        self.assertGreaterEqual(kinds.count("transcribe"), len(self.windows(sess)))
        self.assertEqual(len({e["pid"] for e in events}), 1, "全部在同一個程序內")

    # spec §4.11.7、§3.9：條件全部成立時 stitch 回 0，寫出與 mlx_whisper 同 schema 的 JSON
    def test_stitch_ok_schema(self):
        sess = self.completed(2, silences=[(4.0, 7.0)])
        out = self.base / "stitched.json"
        r = self.stitch(sess, out)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        d = json.loads(out.read_text(encoding="utf-8"))
        self.assertTrue({"text", "segments", "language"} <= set(d), d.keys())
        self.assertIsInstance(d["text"], str)
        segs = d["segments"]
        self.assertGreaterEqual(len(segs), 2)
        for x in segs:
            self.assertTrue({"start", "end", "text"} <= set(x), x)
        starts = [x["start"] for x in segs]
        self.assertEqual(starts, sorted(starts), "段落時間應遞增（已平移到成品時間軸）")
        self.assertAlmostEqual(segs[-1]["end"], 2 * SEG, delta=0.05)

    # spec §4.11.7：params 與這次 transcribe.sh 會用的不同 → 回 3 並印原因
    def test_stitch_param_mismatch_exit3(self):
        sess = self.completed(2)
        sp = s.tracks_of(sess) / "asr" / "state.json"
        st = json.loads(sp.read_text(encoding="utf-8"))
        st["params"]["model"] = "範例/其他模型"
        sp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        out = self.base / "stitched.json"
        r = self.stitch(sess, out)
        self.assertEqual(r.returncode, 3, s.out_of(r))
        self.assertTrue(r.stderr.strip(), "應印一行原因")
        self.assertFalse(out.exists(), "不可用時不得寫出結果")

    # spec §4.11.7：state.json 不是 complete、worker 也沒在跑（心跳超過 60 秒）→ 回 3
    def test_stitch_incomplete_exit3(self):
        sess = self.completed(2)
        sp = s.tracks_of(sess) / "asr" / "state.json"
        st = json.loads(sp.read_text(encoding="utf-8"))
        st["status"] = "running"
        st["heartbeat"] = "2026-10-21T00:00:00+08:00"
        sp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
        r = self.stitch(sess, self.base / "stitched.json", timeout=60)
        self.assertEqual(r.returncode, 3, s.out_of(r))
        self.assertTrue(r.stderr.strip())

    # spec §4.11.7：worker 還活著且 60 秒內有心跳時，stitch 先等它完成
    def test_stitch_waits_live_worker(self):
        sess = self.session(2, silences=[(4.0, 7.0)])
        self.status(sess, "recording")
        w = self.start_worker(sess)
        self.wait_windows(sess, 1)
        self.write_audio_ready(sess)
        out = self.base / "stitched.json"
        st = subprocess.Popen([s.PY, str(s.ASR_WORKER_PY), "stitch", str(sess), str(out)], env=self.env(),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.procs.append(st)
        self.assertFalse(s.wait_until(lambda: st.poll() is not None, timeout=2.0), "worker 還在跑時 stitch 應等待")
        self.status(sess, "done")
        self.assertTrue(s.wait_until(lambda: st.poll() is not None, timeout=120), "worker 完成後 stitch 應結束")
        o, e = st.communicate(timeout=10)
        self.assertEqual(st.returncode, 0, f"\nstdout:{o}\nstderr:{e}")
        self.assertTrue(out.is_file())
        self.assertTrue(s.wait_until(lambda: w.poll() is not None, timeout=30))


if __name__ == "__main__":
    unittest.main()

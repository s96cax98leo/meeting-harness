"""前處理：轉錄與分離並行、成敗判斷、runId、狀態檔加鎖、stitch 交棒（meeting-speed spec §4.1.2、§4.2.6、
§4.8.1–§4.8.5、§4.9、§4.11.8；Story G1、G5、G7）。

替身：轉錄 fakes/asr/mlx_whisper（慢速版 fakes/ms_asr/mlx_whisper）、分離 fakes/ms_diarize_venv（MH_DIARIZE_VENV）、
增量轉錄的模型 fakes/pymod/mlx_whisper（PYTHONPATH）。素材只在 TMPDIR。
場次名用「範例場次」：bin/_combine_audio.py 以 glob 找音檔，路徑含「[」會找不到（既有問題，列衍生工作）。
"""
import json
import os
import subprocess
import time
import unittest

from tests.record import _media as m
from tests.record import test_ms_support as s

RUN_ID = "6F1C0000-0000-4000-8000-0000000B0001"
EXPECTED_REC_FILES = {"diarization.json", "meeting.json", "transcript.quality.json", "transcript.raw.md",
                      "transcript.segments.json", "transcript.speakers.md"}
MISSING_SEGMENTS = "缺 transcript.segments.json"

CALL_SET_STATE_DONE = r'''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_rf_ms_state", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.set_state_done(sys.argv[2])
print("done", flush=True)
'''

CALL_UPDATE_STATE = r'''
import sys
sys.path.insert(0, sys.argv[1])
import _record_lib as lib
f = getattr(lib, "update_pipeline_state", None)
if f is None:
    print("MISSING")
    sys.exit(0)
print(f(sys.argv[2], {"stages": {"範例": {"status": "done"}}}))
'''


class PrepCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)
        self.root = self.base / "根"
        self.asr_log = self.base / "fake_asr.log"

    def env(self, asr_dir=None, **extra):
        env, _ = m.fake_asr_env(self.base)
        env.pop("PATH")
        over, self.diar_log = s.fake_diarize_env(self.base)
        env.update(over)
        env.update({k: str(v) for k, v in extra.items()})
        e = s.base_env(None, **env)
        # ms_asr/whisper 一律失敗：擋住機器上真的 openai-whisper（mlx 替身失敗時不得退回去載入真的模型）
        e["PATH"] = f"{asr_dir or m.FAKE_ASR_DIR}:{s.ASR_SLOW_DIR}:{e['PATH']}"
        return e

    def prep(self, target=None, asr_dir=None, timeout=240, **extra):
        return s.run(["bash", s.MEETING_SH, "prep", target or self.root], self.env(asr_dir, **extra), timeout=timeout)

    def asr_calls(self):
        return m.read_asr_calls(self.asr_log)

    def state(self, sess):
        st = s.pipeline_state(sess)
        self.assertIsInstance(st, dict, "應寫 .pipeline-state.json")
        return st


class TestMSPrep(PrepCase):
    # spec §4.1.2：沒有 §3.7 的環境變數時，介面與輸出檔集合與 042c404 相同（§4.6 的 embeddings.json 除外；
    # asr-robust 只在不存在時多寫 transcript.md；.pipeline-state.lock 是 §3.5 的鎖檔）
    def test_env_absent_unchanged(self):
        sess = s.audio_session(self.root)
        wav = s.wavs(sess)[0].name
        r = self.prep()
        self.assertEqual(r.returncode, 0, s.out_of(r))
        rec = {p.name for p in (sess / "錄音").iterdir()} - {"transcript.md"}
        self.assertEqual(rec, EXPECTED_REC_FILES | {wav}, "錄音/ 的輸出檔集合應與 042c404 相同（不含 embeddings.json）")
        top = {p.name for p in sess.iterdir()} - {".pipeline-state.lock"}
        self.assertEqual(top, {".pipeline-state.json", "錄音"})
        st = self.state(sess)
        self.assertEqual({k: v.get("status") for k, v in st["stages"].items()},
                         {"transcribe": "done", "diarize": "done"})
        self.assertIn("本機前處理完成（1 場）", r.stdout)

    # spec §4.2.6：正式 wav 已發佈、影片仍在收尾（收尾鎖被持有）時，prep 照現行方式處理該場
    def test_prep_while_video_finalizing(self):
        sess = s.audio_session(self.root)
        wav = s.wavs(sess)[0]
        tracks = s.tracks_of(sess)
        tracks.mkdir(parents=True)
        (tracks / "seg-0001.mov").write_bytes(b"\0" * 64)
        lock = s.HeldLock(tracks / ".finalize.lock").acquire()
        self.addCleanup(lock.release)
        r = self.prep()
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(self.state(sess)["stages"]["transcribe"]["status"], "done")
        self.assertTrue((sess / "錄音" / "transcript.raw.md").is_file())
        calls = self.asr_calls()
        self.assertTrue(calls, "應呼叫轉錄")
        self.assertTrue(any(os.path.basename(a) == wav.name for a in calls[0]), f"音源應是 錄音/ 第一層的正式 wav：{calls[0]}")

    # spec §4.8.1：要分離時 diarize.sh 在轉錄開始前於背景啟動，兩者都結束才 merge
    def test_diarize_parallel_with_transcribe(self):
        sess = s.audio_session(self.root)
        times = self.base / "asr.times"
        r = self.prep(asr_dir=s.ASR_SLOW_DIR, FAKE_ASR_SLEEP=2, FAKE_ASR_TIMES=times, FAKE_DIAR_SLEEP=2)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        marks = dict(ln.split() for ln in times.read_text(encoding="utf-8").splitlines()) if times.is_file() else {}
        self.assertIn("START", marks, "前提：慢速轉錄替身應被呼叫")
        a0, a1 = float(marks["START"]), float(marks["END"])
        d = s.diar_calls(self.diar_log)
        self.assertEqual(len(d), 1, d)
        d0, d1 = d[0]["start"], d[0]["end"]
        self.assertTrue(d0 < a1 and a0 < d1, f"轉錄 [{a0:.2f}, {a1:.2f}] 與分離 [{d0:.2f}, {d1:.2f}] 應重疊（並行）")
        self.assertLess(max(a1, d1) - min(a0, d0), 3.5, "兩個各睡 2 秒的替身並行，總耗時應 < 3.5 秒")
        md = sess / "錄音" / "transcript.speakers.md"
        self.assertTrue(md.is_file(), "兩者都成功後應 merge")
        self.assertGreaterEqual(md.stat().st_mtime, max(a1, d1) - 0.01, "merge 應在轉錄與分離都結束之後")

    # spec §4.8.2：每次 prep 先寫 prep: {runId, startedAt, expect}
    def test_state_begin_run_id(self):
        sess = s.audio_session(self.root)
        r = self.prep(MH_PREP_RUN_ID=RUN_ID)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        prep = self.state(sess).get("prep")
        self.assertIsInstance(prep, dict, "應有 prep 鍵")
        self.assertEqual(prep.get("runId"), RUN_ID)
        self.assertIsInstance(prep.get("startedAt"), str)
        self.assertRegex(prep["startedAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        self.assertEqual(prep.get("expect"), ["transcribe", "diarize"], "沒有 照片/、要分離 → expect＝transcribe、diarize")

        with self.subTest(case="沒給 MH_PREP_RUN_ID 時自己產 uuid"):
            sess2 = s.audio_session(self.base / "根2")
            r = self.prep(self.base / "根2")
            self.assertEqual(r.returncode, 0, s.out_of(r))
            rid = (self.state(sess2).get("prep") or {}).get("runId")
            self.assertRegex(str(rid), r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")

    # spec §4.8.2：prep 寫的每個 stage 都帶同一個 runId
    def test_stages_carry_run_id(self):
        sess = s.audio_session(self.root)
        r = self.prep(MH_PREP_RUN_ID=RUN_ID)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        stages = self.state(sess)["stages"]
        for k in ("transcribe", "diarize"):
            with self.subTest(stage=k):
                self.assertEqual(stages.get(k, {}).get("runId"), RUN_ID, stages)

    # spec §4.8.3：diarize.sh 失敗時寫 diarize: failed
    def test_diarize_failure_recorded(self):
        sess = s.audio_session(self.root)
        r = self.prep(FAKE_DIAR_EXIT=5)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(self.state(sess)["stages"].get("diarize", {}).get("status"), "failed",
                         f"diarize.sh 失敗時應記 diarize: failed{s.out_of(r)}")

    # spec §4.8.4、§6 第 13、20 條：缺 transcript.segments.json 時明確報錯、不重轉、回 1、記 diarize: failed
    def test_missing_segments_explicit_error(self):
        sess = s.audio_session(self.root)
        r = s.run(["bash", s.MEETING_SH, "diarize", sess], self.env(), timeout=180)
        self.assertEqual(self.asr_calls(), [], f"不得呼叫 ASR{s.out_of(r)}")
        self.assertEqual(r.returncode, 1, s.out_of(r))
        out = r.stdout + r.stderr
        self.assertIn(MISSING_SEGMENTS, out)
        self.assertIn("meeting.sh prep", out, "應提示先跑 meeting.sh prep <場次>（或 transcribe）")
        self.assertEqual(self.state(sess)["stages"].get("diarize", {}).get("status"), "failed")
        self.assertFalse((sess / "錄音" / "transcript.segments.json").exists())

        with self.subTest(case="prep 的分離步驟（轉錄失敗、沒有段落檔）"):
            sess2 = s.audio_session(self.base / "根2")
            r = self.prep(self.base / "根2", FAKE_ASR_EXIT=1)
            self.assertEqual(r.returncode, 0, s.out_of(r))
            self.assertIn(MISSING_SEGMENTS, r.stdout + r.stderr)
            self.assertEqual(self.state(sess2)["stages"].get("diarize", {}).get("status"), "failed")

    # spec §4.8.5：轉錄、分離失敗時 prep 仍回 0
    def test_prep_exit_zero_on_stage_failure(self):
        sess = s.audio_session(self.root)
        r = self.prep(FAKE_ASR_EXIT=1, FAKE_DIAR_EXIT=5)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(self.state(sess)["stages"]["transcribe"]["status"], "failed")

    # spec §4.9.1：state-set 經 update_pipeline_state（flock＋讀後合併＋mkstemp/rename）；20 個並發寫者都留下
    def test_state_set_atomic_flock(self):
        sess = s.audio_session(self.root)
        env = s.base_env(None)
        procs = [subprocess.Popen([s.PY, str(s.RECORD_LIB_PY), "state-set", str(sess), f"範例stage{i:02d}", "done",
                                   "--run-id", RUN_ID], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for i in range(20)]
        results = []
        for p in procs:
            out, err = p.communicate(timeout=60)
            results.append((p.returncode, err))
        self.assertEqual([rc for rc, _ in results], [0] * 20, f"state-set 應都回 0：{[e for _, e in results][:2]}")
        st = self.state(sess)
        stages = st.get("stages", {})
        for i in range(20):
            self.assertEqual(stages.get(f"範例stage{i:02d}"), {"status": "done", "runId": RUN_ID}, stages)
        leftovers = [p.name for p in sess.iterdir() if p.name.startswith(".pipeline-state.json.")]
        self.assertEqual(leftovers, [], "不得留下暫存檔")

    # spec §4.9.1：_record_finalize.set_state_done 也經 update_pipeline_state（鎖被持有時不得寫）
    def test_finalize_set_state_uses_lock(self):
        sess = s.audio_session(self.root)
        sf = sess / ".pipeline-state.json"
        sf.write_text(json.dumps({"prep": {"runId": RUN_ID, "startedAt": "2026-10-21T11:30:15+08:00",
                                           "expect": ["transcribe"]},
                                  "stages": {"transcribe": {"status": "done", "runId": RUN_ID}}}, ensure_ascii=False),
                      encoding="utf-8")
        before = sf.read_bytes()
        lock = s.HeldLock(sess / ".pipeline-state.lock").acquire()
        p = subprocess.Popen([s.PY, "-c", CALL_SET_STATE_DONE, str(s.FINALIZE_PY), str(sess)], env=s.base_env(None),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            exited_while_locked = s.wait_until(lambda: p.poll() is not None, timeout=1.5)
            self.assertFalse(exited_while_locked and sf.read_bytes() != before,
                             "鎖被持有時 set_state_done 不得寫 .pipeline-state.json")
            self.assertEqual(sf.read_bytes(), before, "鎖被持有時檔案不得改變")
        finally:
            lock.release()
        out, err = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 0, err)
        st = json.loads(sf.read_text(encoding="utf-8"))
        self.assertEqual(st["stages"].get("record"), {"status": "done"}, "放鎖後應記 record: done（不帶 runId）")
        self.assertEqual(st["stages"].get("transcribe"), {"status": "done", "runId": RUN_ID}, "讀後合併：其他 stage 保留")
        self.assertEqual(st.get("prep", {}).get("runId"), RUN_ID, "讀後合併：prep 鍵保留")

    # spec §4.9.2：等鎖超過 5 秒就放棄、stderr 印一行警告、回 False
    def test_state_lock_timeout_warns(self):
        sess = s.audio_session(self.root)
        sf = sess / ".pipeline-state.json"
        sf.write_text('{"stages": {}}', encoding="utf-8")
        lock = s.HeldLock(sess / ".pipeline-state.lock").acquire()
        self.addCleanup(lock.release)
        t0 = time.monotonic()
        r = s.run([s.PY, "-c", CALL_UPDATE_STATE, s.BIN / "lib", sess], s.base_env(None), timeout=60)
        elapsed = time.monotonic() - t0
        self.assertNotEqual(r.stdout.strip(), "MISSING", "bin/lib/_record_lib.py 應有 update_pipeline_state")
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(r.stdout.strip(), "False", f"逾時應回 False{s.out_of(r)}")
        self.assertTrue(r.stderr.strip(), "逾時應在 stderr 印一行警告")
        self.assertGreaterEqual(elapsed, 4.5, f"應等約 5 秒才放棄：{elapsed:.1f}")
        self.assertLess(elapsed, 10.0, f"應在約 5 秒放棄：{elapsed:.1f}")
        self.assertEqual(sf.read_text(encoding="utf-8"), '{"stages": {}}', "放棄寫入時檔案不得改變")

    # spec §4.9.3：meeting status 讀得懂含 prep 鍵的新檔，照列所有 stage
    def test_status_reads_new_state(self):
        sess = s.audio_session(self.root)
        (sess / ".pipeline-state.json").write_text(json.dumps({
            "prep": {"runId": RUN_ID, "startedAt": "2026-10-21T11:30:15+08:00", "expect": ["transcribe", "diarize"]},
            "stages": {"record": {"status": "done"}, "transcribe": {"status": "done", "runId": RUN_ID},
                       "diarize": {"status": "failed", "runId": RUN_ID}}}), encoding="utf-8")
        r = s.run(["bash", s.MEETING_SH, "status", self.root], s.base_env(None), timeout=60)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        for want in ("record:done", "transcribe:done", "diarize:failed"):
            self.assertIn(want, r.stdout)

    # spec §4.11.8：stitch 回 0 時 prep 以 MH_ASR_SEGMENTS_JSON 交給 transcribe.sh，不呼叫 ASR 引擎（incremental-asr 轉綠）
    def test_prep_uses_stitched(self):
        self.assertTrue(s.ASR_WORKER_PY.is_file(), "bin/lib/_asr_worker.py 不存在（incremental-asr 負責）")
        home = self.base / "home"
        sess = s.record_session(self.root, [dict(dur=3.0), dict(dur=3.0)], name=m.SESSION_NAME, gap=0.0)
        s.write_status(home, phase="done", pid=os.getpid(), session=str(sess), segments=2)
        env = self.env(MH_RECORD_HOME=home, PYTHONPATH=s.PYMOD_DIR, FAKE_PYMOD_LOG=self.base / "pymod.log")
        r = s.run([s.PY, s.ASR_WORKER_PY, "run", sess], env, timeout=180)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        st = json.loads((s.tracks_of(sess) / "asr" / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(st.get("status"), "complete", st)
        tracks = s.tracks_of(sess)
        segs = json.loads((tracks / "manifest.json").read_text(encoding="utf-8"))["segments"]
        start, rows = 0.0, []
        for x in segs:
            d = round(x["finishedAt"] - x["startedAt"], 3)
            rows.append({"file": x["file"], "size": (tracks / x["file"]).stat().st_size, "duration": d,
                         "start": round(start, 3)})
            start += d
        wav_name = f"{m.SESSION_NAME} 2026-10-21 09.30.00.wav"
        (tracks / "audio-ready.json").write_text(json.dumps({
            "schemaVersion": 1, "wav": wav_name, "stamp": "2026-10-21 09.30.00", "compensation": "off",
            "segments": rows, "createdAt": "2026-10-21T11:30:12+08:00"}, ensure_ascii=False), encoding="utf-8")
        m.make_wav(sess / "錄音" / wav_name, dur=6.0)
        r = s.run(["bash", s.MEETING_SH, "prep", self.root], env, timeout=240)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(self.asr_calls(), [], f"stitch 可用時不得呼叫 ASR 引擎{s.out_of(r)}")
        raw = (sess / "錄音" / "transcript.raw.md").read_text(encoding="utf-8")
        self.assertIn("範例增量第", raw, "raw 應來自增量轉錄的結果")
        self.assertEqual(self.state(sess)["stages"]["transcribe"]["status"], "done")

    # spec §4.11.8：沒有可用的增量結果（沒有 tracks/asr/、或 state.json 不是 complete）時整檔轉錄
    def test_prep_falls_back_full(self):
        for label, state in (("沒有 tracks/asr/", None), ("state.json 是 failed", {"schemaVersion": 1, "status": "failed"})):
            with self.subTest(case=label):
                root = self.base / label
                sess = s.audio_session(root)
                if state is not None:
                    d = s.tracks_of(sess) / "asr"
                    d.mkdir(parents=True)
                    (d / "state.json").write_text(json.dumps(state), encoding="utf-8")
                if self.asr_log.exists():
                    self.asr_log.unlink()
                r = self.prep(root)
                self.assertEqual(r.returncode, 0, s.out_of(r))
                self.assertTrue(self.asr_calls(), "應整檔轉錄（呼叫 ASR 引擎）")
                self.assertIn("範例內容", (sess / "錄音" / "transcript.raw.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

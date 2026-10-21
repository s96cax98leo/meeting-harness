"""音訊先出：正式 wav 在任何影片步驟之前發佈、audio-ready.json、finalize.json 兩階段、冪等中間態
（meeting-speed spec §3.2、§3.4、§4.2.1–§4.2.5、§4.3.2、§4.3.3、§4.4.9、§6 第 10、11、23 條；Story G1、G4）。

收尾以 python3 bin/_record_finalize.py <場次> 直接執行（MH_RECORD_HOME 指向暫存 home）；ffmpeg 經 MH_FFMPEG 接
fakes/ms_slow_ffmpeg.sh（記錄每次呼叫的分類與當下 錄音/ 有沒有 wav，可讓影片步驟變慢或失敗）。合成素材只在 TMPDIR。
"""
import json
import os
import re
import time
import unittest

from tests.record import _media as m
from tests.record import e2e_check as e2e
from tests.record import test_ms_support as s

THREE = [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)]
READY_KEYS = {"schemaVersion", "wav", "stamp", "compensation", "segments", "createdAt"}
SEG_KEYS = {"file", "size", "duration", "start"}
NAME_RE = re.compile(r"^" + re.escape(s.SESSION) + r" (\d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2})\.wav$")
DONE = "✓ 已完成"


class AudioFirstCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)
        self.home = self.base / "home"
        self.home.mkdir()
        self.log = self.base / "ffmpeg.log"

    def session(self, segments=THREE, canvas=None, sub="根"):
        return s.record_session(self.base / sub, segments, canvas=canvas)

    def fin(self, sess, **env):
        over = {"MH_FFMPEG": s.SLOW_FFMPEG, "MS_FFMPEG_LOG": self.log, "MS_FFMPEG_WATCH": sess / "錄音"}
        over.update(env)
        return s.finalize(sess, self.home, **over)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"收尾應回 0{s.out_of(r)}")

    def failed_video_run(self, sess):
        """影片步驟一律失敗的一次收尾（回 5）；回傳結果。"""
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="video")
        self.assertEqual(r.returncode, 5, f"影片步驟失敗時應回 5{s.out_of(r)}")
        return r


class TestMSAudioFirst(AudioFirstCase):
    # spec §4.2.1、§4.4.9：正式 wav 在任何影片步驟（copy remux、normalize、concat）之前出現，並印「音訊就緒：」
    def test_wav_published_before_video(self):
        for label, canvas in (("重編路徑（沒有 canvasLock）", None), ("copy 路徑", (320, 240))):
            with self.subTest(path=label):
                if self.log.exists():
                    self.log.unlink()
                sess = self.session(canvas=canvas, sub=label)
                r = self.fin(sess)
                self.ok(r)
                calls = s.ffmpeg_calls(self.log)
                video = [c for c in calls if c["cls"] == "video"]
                self.assertTrue(video, "前提：應有影片步驟的 ffmpeg 呼叫")
                early = [c["argv"][-1:] for c in video if c["wav"] != "1"]
                self.assertEqual(early, [], "正式 wav 出現前不得有任何影片步驟的 ffmpeg 呼叫")
                wav = s.wavs(sess)
                self.assertEqual(len(wav), 1)
                lines = r.stdout.splitlines()
                ready = [i for i, ln in enumerate(lines) if ln.strip() == f"音訊就緒：錄音/{wav[0].name}"]
                self.assertEqual(len(ready), 1, f"stdout 應恰印一次「音訊就緒：錄音/<檔名>.wav」{s.out_of(r)}")

    # spec §4.2.2、§3.2：正式 wav 16 kHz 單聲道、檔名照 meeting-record §4.6.2；audio-ready.json 的鍵與段落起點
    def test_ready_json_fields(self):
        sess = self.session()
        r = self.fin(sess, MH_KEEP_SEGMENTS=1)
        self.ok(r)
        wav = s.wavs(sess)
        self.assertEqual(len(wav), 1)
        mt = NAME_RE.match(wav[0].name)
        self.assertIsNotNone(mt, wav[0].name)
        a = m.stream(wav[0], "audio")
        self.assertEqual((int(a["sample_rate"]), int(a["channels"])), (16000, 1))
        ready = s.audio_ready_json(sess)
        self.assertIsInstance(ready, dict, "應有 錄音/tracks/audio-ready.json")
        self.assertEqual(set(ready), READY_KEYS)
        self.assertEqual(ready["schemaVersion"], 1)
        self.assertEqual(ready["wav"], wav[0].name)
        self.assertEqual(ready["stamp"], mt.group(1))
        self.assertEqual(ready["compensation"], "off")
        self.assertRegex(ready["createdAt"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        segs = ready["segments"]
        self.assertEqual([x["file"] for x in segs], ["seg-0001.mov", "seg-0002.mov", "seg-0003.mov"])
        total = 0.0
        for x in segs:
            self.assertEqual(set(x), SEG_KEYS, x)
            self.assertEqual(x["size"], (s.tracks_of(sess) / x["file"]).stat().st_size)
            self.assertGreater(x["duration"], 1.9)
            self.assertAlmostEqual(x["start"], total, delta=0.001, msg=f"{x['file']} 的 start 應等於前面各段 duration 的和")
            total += x["duration"]

    # spec §4.2.3、§6 第 23 條：finalize.json 第一階段（finishedAt、outputs.audio、videoPublishedAt: null）寫好之前，
    # 錄音/ 第一層不出現任何音源檔；之後正式 wav 才出現，且此時影片還沒發佈
    def test_finalize_json_before_wav(self):
        sess = self.session()
        p = s.finalize_popen(sess, self.home, MH_FFMPEG=s.SLOW_FFMPEG, MS_FFMPEG_LOG=self.log,
                             MS_FFMPEG_SLOW_ON="video", MS_FFMPEG_SLOW_SECONDS=1)
        self.addCleanup(s.kill_quietly, p)
        seen = None
        while p.poll() is None and seen is None:
            files = s.audio_files(sess)
            if files:
                seen = {"files": [f.name for f in files], "fin": s.finalize_json(sess), "videos": s.videos(sess)}
            else:
                time.sleep(0.02)
        out, err = p.communicate(timeout=300)
        self.assertEqual(p.returncode, 0, f"\nstdout:{out}\nstderr:{err}")
        self.assertIsNotNone(seen, "收尾進行中應觀察到正式 wav 出現（影片步驟還在跑時）")
        fin = seen["fin"]
        self.assertIsInstance(fin, dict, "正式 wav 出現時 finalize.json 應已存在")
        self.assertTrue(fin.get("finishedAt"), "第一階段應有 finishedAt")
        self.assertEqual((fin.get("outputs") or {}).get("audio"), f"錄音/{seen['files'][0]}")
        self.assertIn("videoPublishedAt", fin, "第一階段應有 videoPublishedAt 鍵")
        self.assertIsNone(fin["videoPublishedAt"], "第一階段的 videoPublishedAt 應為 null")
        self.assertEqual(seen["videos"], [], "正式 wav 不等影片：wav 出現時影片還沒發佈")
        self.assertEqual(len(seen["files"]), 1, f"錄音/ 第一層只能出現正式 wav：{seen['files']}")
        final = s.finalize_json(sess)
        self.assertTrue(final.get("videoPublishedAt"), "第二階段應補上 videoPublishedAt")
        self.assertEqual(final.get("finishedAt"), fin.get("finishedAt"), "第二階段不得改 finishedAt")

    # spec §4.2.4：補償模式 ≠ off 時正式 wav 是補償後的音訊（系統聲音延後 0.15 秒 → wav 開頭 0.15 秒靜音）
    def test_compensated_wav(self):
        sess = m.build_sc_session(self.base / "src", seglen=2.0, outputs=(("uid-範例-a", 0.15),) * 3,
                                  flash_phase=1.0, tone=True)
        r = s.finalize(sess, self.home, MH_SYNC_COMPENSATION="reported", MH_KEEP_SEGMENTS=1)
        self.ok(r)
        ready = s.audio_ready_json(sess)
        self.assertIsInstance(ready, dict, "應有 audio-ready.json")
        self.assertIn(ready.get("compensation"), ("constant", "variable"), "補償時 compensation 不得是 off")
        wav = s.wavs(sess)
        self.assertEqual(len(wav), 1)
        samples, _ = e2e.pcm_mono(str(wav[0]))
        db = e2e.rms_db_windows(samples, 16000, 0.01)
        self.assertTrue(all(v <= -60.0 for v in db[:13]), f"wav 開頭 0.13 秒應是補償延後留下的靜音：{db[:16]}")
        self.assertTrue(all(v > -40.0 for v in db[17:60]), "0.17 秒之後應有連續的底音")
        vid = s.videos(sess)
        self.assertEqual(len(vid), 1)
        self.assertLessEqual(abs(m.stream_duration(wav[0], "audio") - m.stream_duration(vid[0], "audio")), 0.025,
                             "wav 與影片音訊軌 duration 差應 ≤ 25 ms（meeting-record §4.6.20 (ii)）")

    # spec §4.2.5：影片步驟失敗（回 5）時正式 wav、audio-ready.json、finalize.json 第一階段保留；再跑不算已完成
    def test_video_failure_keeps_wav(self):
        sess = self.session()
        r = self.failed_video_run(sess)
        wav = s.wavs(sess)
        self.assertEqual(len(wav), 1, f"影片失敗時已發佈的正式 wav 應保留{s.out_of(r)}")
        self.assertIsInstance(s.audio_ready_json(sess), dict, "audio-ready.json 應保留")
        fin = s.finalize_json(sess)
        self.assertIsInstance(fin, dict)
        self.assertTrue(fin.get("finishedAt"))
        self.assertEqual((fin.get("outputs") or {}).get("audio"), f"錄音/{wav[0].name}")
        self.assertIsNone(fin.get("videoPublishedAt"))
        self.assertEqual(s.videos(sess), [], "影片不得發佈")
        self.assertEqual(len(s.segment_files(sess)), 3, "段落都應保留")
        r2 = self.fin(sess)
        self.ok(r2)
        self.assertNotIn(DONE, r2.stdout, "影片不在時 already_done 不得判為完成")
        self.assertEqual(len(s.videos(sess)), 1, "再跑應補出影片")

    # spec §4.3.2、§6 第 10 條：audio-ready.json 與這次輸入相同、正式 wav 在 → 不重寫 wav、不改 finishedAt，直接補影片
    def test_idempotent_mid_state(self):
        sess = self.session()
        self.failed_video_run(sess)
        wav = s.wavs(sess)
        self.assertEqual(len(wav), 1, "前提：第一次收尾已發佈正式 wav")
        os.utime(wav[0], (1_700_000_000, 1_700_000_000))
        before = (wav[0].stat().st_mtime_ns, wav[0].read_bytes())
        finished = (s.finalize_json(sess) or {}).get("finishedAt")
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(s.wavs(sess), wav, "不得換成另一個 wav")
        self.assertEqual((wav[0].stat().st_mtime_ns, wav[0].read_bytes()), before, "正式 wav 不得重寫（mtime 不變）")
        self.assertEqual((s.finalize_json(sess) or {}).get("finishedAt"), finished, "finishedAt 不得重寫")
        self.assertEqual(len(s.videos(sess)), 1)

    # spec §4.3.3：audio-ready.json 與這次的段落清單不同 → 重寫正式 wav（.part 後 os.replace）與 audio-ready.json
    def test_ready_json_stale_rewritten(self):
        sess = self.session()
        self.failed_video_run(sess)
        ready_p = s.tracks_of(sess) / "audio-ready.json"
        ready = s.audio_ready_json(sess)
        self.assertIsInstance(ready, dict, "前提：第一次收尾已寫 audio-ready.json")
        original = ready["segments"][0]["size"]
        ready["segments"][0]["size"] = original + 1
        ready_p.write_text(json.dumps(ready, ensure_ascii=False), encoding="utf-8")
        wav = s.wavs(sess)[0]
        os.utime(wav, (1_700_000_000, 1_700_000_000))
        old_mtime = wav.stat().st_mtime_ns
        r = self.fin(sess)
        self.ok(r)
        new = s.wavs(sess)
        self.assertEqual(len(new), 1)
        self.assertNotEqual(new[0].stat().st_mtime_ns, old_mtime, "段落清單不同時應重寫正式 wav")
        self.assertEqual(s.audio_ready_json(sess)["segments"][0]["size"], original,
                         "audio-ready.json 應重寫成這次的段落清單")

if __name__ == "__main__":
    unittest.main()

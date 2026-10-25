"""sdlc-deliver 審查（bugs-2）的回歸測試：音訊先出的第一階段改寫 finalize.json 後，影片步驟失敗，下一次收尾
不得把它當成已完成（meeting-speed spec §4.2.5、§4.3.4；Story G1）。

情境：上一次收尾已通過（verify ok、影片/ 有同名成品、段落保留）；這次換 mode 或段落有變而重跑，第一階段把
finalize.json 改寫成這次的 mode／inputs、videoPublishedAt: null，接著影片步驟失敗（回 5）。stamp 沿用上次的，
outputs.video 指向上一次留下的同名影片，所以只看「成品都在、inputs 相同」會誤判已完成。
判準與 record.sh、AbnormalStop.swift 一致：finalize.json 有 videoPublishedAt 鍵且值為 null ＝ 還沒收尾。

收尾以 python3 bin/_record_finalize.py <場次> 直接執行（MH_RECORD_HOME 指向暫存 home）；影片步驟失敗用
fakes/ms_slow_ffmpeg.sh 的 MS_FFMPEG_FAIL_ON=video 模擬。合成素材只在 TMPDIR。
"""
import importlib.util
import json
import os
import sys
import unittest

from tests.record import test_ms_support as s

THREE = [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)]
DONE = "✓ 已完成"


def load_state():
    lib = str(s.BIN / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    spec = importlib.util.spec_from_file_location("_finalize_state_review", s.BIN / "lib" / "_finalize_state.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FinalizeReviewCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)
        self.home = self.base / "home"
        self.home.mkdir()
        self.log = self.base / "ffmpeg.log"

    def session(self):
        return s.record_session(self.base / "根", THREE)

    def fin(self, sess, **env):
        over = {"MH_FFMPEG": s.SLOW_FFMPEG, "MS_FFMPEG_LOG": self.log, "MS_FFMPEG_WATCH": sess / "錄音",
                "MH_KEEP_SEGMENTS": 1}
        over.update(env)
        return s.finalize(sess, self.home, **over)

    def ok(self, r, what="收尾"):
        self.assertEqual(r.returncode, 0, f"{what}應回 0{s.out_of(r)}")

    def failed_video_run(self, sess, **env):
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="video", **env)
        self.assertEqual(r.returncode, 5, f"影片步驟失敗時應回 5{s.out_of(r)}")
        fin = s.finalize_json(sess)
        self.assertIsInstance(fin, dict)
        self.assertIn("videoPublishedAt", fin, "前提：第一階段寫了 videoPublishedAt 鍵")
        self.assertIsNone(fin["videoPublishedAt"], "前提：第一階段的 videoPublishedAt 為 null")
        self.assertEqual(len(s.videos(sess)), 1, "前提：上一次的同名影片還在 影片/")
        return r

    def assert_redone(self, sess, r, n_inputs):
        self.ok(r, "影片失敗後再跑一次")
        self.assertNotIn(DONE, r.stdout, f"第一階段後影片沒發佈，不得判為已完成{s.out_of(r)}")
        fin = s.finalize_json(sess)
        self.assertTrue(fin.get("videoPublishedAt"), "重跑應補上 videoPublishedAt")
        self.assertEqual((fin.get("verify") or {}).get("status"), "ok", "重跑應通過驗證")
        self.assertEqual(len(fin.get("inputs") or []), n_inputs)
        st = s.pipeline_state(sess) or {}
        self.assertEqual(((st.get("stages") or {}).get("record") or {}).get("status"), "done",
                         "重跑完成後應記 record: done")


class TestMSFinalizeReview(FinalizeReviewCase):
    # (1) 段落有變的重跑：第一階段寫完、影片步驟失敗後再跑一次，不得判為已完成
    def test_changed_segments_video_failure_not_done(self):
        sess = self.session()
        tracks = s.tracks_of(sess)
        aside = self.base / "seg-0003.mov"
        os.replace(tracks / "seg-0003.mov", aside)
        self.ok(self.fin(sess), "只有兩段時的第一次收尾")
        self.assertEqual(len(s.finalize_json(sess)["inputs"]), 2)
        os.replace(aside, tracks / "seg-0003.mov")
        self.failed_video_run(sess)
        (sess / ".pipeline-state.json").unlink(missing_ok=True)
        self.assert_redone(sess, self.fin(sess), 3)

    # (2) 換 mode 重跑：off 收尾通過後改 reported，影片步驟失敗；再用 reported 跑一次不得判為已完成
    def test_mode_change_video_failure_not_done(self):
        sess = self.session()
        self.ok(self.fin(sess), "mode off 的第一次收尾")
        self.failed_video_run(sess, MH_SYNC_COMPENSATION="reported")
        self.assertEqual((s.finalize_json(sess).get("syncCompensation") or {}).get("mode"), "reported")
        (sess / ".pipeline-state.json").unlink(missing_ok=True)
        self.assert_redone(sess, self.fin(sess, MH_SYNC_COMPENSATION="reported"), 3)

    # (3) 正常完成後第二次仍判已完成（冪等不變）
    def test_completed_second_run_still_done(self):
        sess = self.session()
        self.ok(self.fin(sess))
        video = s.videos(sess)
        self.assertEqual(len(video), 1)
        before = video[0].stat().st_mtime_ns
        r = self.fin(sess)
        self.ok(r, "第二次收尾")
        self.assertIn(DONE, r.stdout, f"正常完成後第二次應判已完成{s.out_of(r)}")
        self.assertEqual(video[0].stat().st_mtime_ns, before, "已完成時不得重寫影片")


class TestMSAlreadyDoneUnit(unittest.TestCase):
    """already_done 直接呼叫：videoPublishedAt 鍵存在且為 null → None；舊 schema（沒有該鍵）照舊判斷。"""

    def setUp(self):
        self.st = load_state()
        self.base = s.tmpdir(self)
        self.sess = self.base / "場次"
        self.tracks = self.sess / "錄音" / "tracks"
        self.tracks.mkdir(parents=True)
        (self.sess / "影片").mkdir()
        self.seg = self.tracks / "seg-0001.mov"
        self.seg.write_bytes(b"x" * 10)
        (self.sess / "影片" / "a.mov").write_bytes(b"v")
        (self.sess / "錄音" / "a.wav").write_bytes(b"w")

    def write_fin(self, **extra):
        fin = {"schemaVersion": 1, "stamp": "2026-10-25 09.00.00",
               "inputs": [{"file": "seg-0001.mov", "size": 10}], "skipped": [],
               "outputs": {"video": "影片/a.mov", "audio": "錄音/a.wav"}}
        fin.update(extra)
        (self.tracks / "finalize.json").write_text(json.dumps(fin, ensure_ascii=False), encoding="utf-8")

    def done(self):
        return self.st.already_done(str(self.sess), str(self.tracks), [str(self.seg)], "off")

    def test_first_phase_without_verify_not_done(self):
        self.write_fin(syncCompensation={"mode": "off", "segments": []}, finishedAt="x", videoPublishedAt=None)
        self.assertIsNone(self.done(), "videoPublishedAt 為 null 的第一階段不得判為已完成")

    def test_old_schema_still_done(self):
        self.write_fin()
        self.assertIsNotNone(self.done(), "沒有 videoPublishedAt 鍵的舊 schema 照舊判為已完成")

    def test_published_and_verified_done(self):
        self.write_fin(videoPublishedAt="2026-10-25T09:10:00", verify={"status": "ok", "path": "reencode"})
        self.assertIsNotNone(self.done())


if __name__ == "__main__":
    unittest.main()

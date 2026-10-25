"""影片：畫布鎖定的 copy 串接、驗證移到發佈之後、ffprobe 次數、步驟標籤、N-3、補尾幀數（meeting-speed spec §3.4、
§4.3.4、§4.4.3–§4.4.10、§4.4.12、§4.5.1–§4.5.4、§6 第 5–7、10、12 條；Story G1、G4、G5、G9）。

收尾以 python3 bin/_record_finalize.py <場次> 直接執行；ffmpeg 經 MH_FFMPEG 接 fakes/ms_slow_ffmpeg.sh（記錄、可讓
驗證或影片步驟變慢或失敗），ffprobe 經 MH_FFPROBE 接 fakes/ms_count_ffprobe.sh（計數）。copy 路徑的素材：
record.meta.json 有 canvasLock、各段同尺寸同編碼參數（同 extradata）。合成素材只在 TMPDIR。
"""
import json
import os
import re
import subprocess
import time
import unittest

from tests.record import _media as m
from tests.record import test_ms_support as s

COPY3 = [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)]
CANVAS = (320, 240)
STEP_RE = re.compile(r"^耗時 (\S+)（(.+)）：")
STEPS = {"normalize", "concat", "mix", "probe"}
DONE = "✓ 已完成"

TAIL_PAD_PATCHED = r'''
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_rf_ms_tail", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.link_fps = lambda stream: 58.0   # 段落的 r_frame_rate 被低報成 58（實際連結影格率 60），incident 的情境
sys.exit(mod.main([sys.argv[2]]))
'''


def packet_hashes(path):
    r = subprocess.run([s.REAL_FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=data_hash",
                        "-show_data_hash", "MD5", "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return [x.strip() for x in r.stdout.split() if x.strip()]


def step_lines(stdout):
    return [mt.groups() for mt in (STEP_RE.match(ln.strip()) for ln in stdout.splitlines()) if mt]


class VideoCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)
        self.home = self.base / "home"
        self.home.mkdir()
        self.log = self.base / "ffmpeg.log"

    def session(self, segments=COPY3, canvas=CANVAS, sub="根"):
        return s.record_session(self.base / sub, segments, canvas=canvas)

    def fin(self, sess, **env):
        over = {"MH_FFMPEG": s.SLOW_FFMPEG, "MS_FFMPEG_LOG": self.log, "MS_FFMPEG_WATCH": sess / "錄音"}
        over.update(env)
        return s.finalize(sess, self.home, **over)

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"收尾應回 0{s.out_of(r)}")

    def video_path(self, sess):
        fin = s.finalize_json(sess)
        self.assertIsInstance(fin, dict, "應寫 finalize.json")
        return fin.get("videoPath")

    def encode_calls(self):
        return [c for c in s.ffmpeg_calls(self.log) if any(x in ("h264_videotoolbox", "libx264") for x in c["argv"])]

    def the_video(self, sess):
        v = s.videos(sess)
        self.assertEqual(len(v), 1, f"影片/ 應恰有一個 .mov：{v}")
        return v[0]


class TestMSVideoCopy(VideoCase):
    # spec §4.4.3：canvasLock 在、各段同尺寸同參數同 extradata、沒有重複 PTS → copy 路徑（影片不重新編碼）
    def test_copy_when_canvas_lock(self):
        sess = self.session()
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "copy")
        self.assertEqual(self.encode_calls(), [], "copy 路徑不得以 h264_videotoolbox／libx264 重新編碼影片")

    # spec §4.4.3、§4.4.9：沒有 canvasLock 的場次照現行重編路徑
    def test_reencode_without_canvas_lock(self):
        sess = self.session(canvas=None)
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "reencode")
        self.assertTrue(self.encode_calls(), "重編路徑應重新編碼影片")

    # spec §4.4.3：有一段寬高不等於 canvasLock → 整場重編，不逐段混用
    def test_reencode_when_size_mismatch(self):
        sess = self.session([dict(dur=2.0), dict(dur=2.0, w=640, h=480), dict(dur=2.0)])
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "reencode")
        encoded = self.encode_calls()
        self.assertGreaterEqual(len(encoded), 3, "整場重編：每一段都要重新編碼（不得逐段混用 copy）")

    # spec §4.4.3：有一段 extradata 不同（同 codec、profile、pix_fmt、time_base）→ 整場重編
    def test_reencode_when_extradata_differs(self):
        sess = self.session()
        seg2 = s.tracks_of(sess) / "seg-0002.mov"
        seg2.unlink()
        m.ff("-f", "lavfi", "-i", "testsrc2=s=320x240:r=30:d=2", "-f", "lavfi", "-i", "sine=f=440:sample_rate=48000:d=2",
             "-c:v", "libx264", "-preset", "ultrafast", "-x264-params", "ref=2", "-pix_fmt", "yuv420p", "-b:v", "800k",
             "-ac", 2, "-ar", 48000, "-c:a", "aac", "-b:a", "128k", "-f", "mov", seg2)
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "reencode")

    # spec §4.4.4：copy 路徑的影片封包資料與來源逐段相同
    def test_copy_packets_identical(self):
        sess = self.session()
        src = []
        for p in s.segment_files(sess):
            src += packet_hashes(p)
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "copy")
        self.assertEqual(packet_hashes(self.the_video(sess)), src, "copy 路徑的影片封包應與來源逐段相同（不重新編碼）")

    # spec §4.4.4、§3.4：finalize.json.videoPath 為 copy／reencode；verify 記 status ok 與 path
    def test_finalize_json_video_path(self):
        for label, canvas, want in (("copy", CANVAS, "copy"), ("reencode", None, "reencode")):
            with self.subTest(path=label):
                sess = self.session(canvas=canvas, sub=label)
                r = self.fin(sess)
                self.ok(r)
                fin = s.finalize_json(sess)
                self.assertEqual(fin.get("videoPath"), want)
                self.assertEqual(fin.get("verify"), {"status": "ok", "path": want})
                self.assertTrue(fin.get("videoPublishedAt"))

    # spec §4.4.5（meeting-record §4.6.3）：copy 路徑影片軌與音訊軌 duration 差 < 100 ms
    def test_copy_duration_within_100ms(self):
        sess = self.session()
        self.ok(self.fin(sess))
        self.assertEqual(self.video_path(sess), "copy")
        v = self.the_video(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertLess(abs(vd - ad), 0.1, f"影片軌 {vd} 與音訊軌 {ad} 差應 < 100 ms")

    # spec §4.4.5（meeting-record §4.6.14 (i)–(iv)）：dts 嚴格遞增、解碼無錯、影格數不少於各段總和、間隔 < 1 ms 為 0
    def test_copy_dts_monotonic(self):
        sess = self.session()
        frames = sum(m.frame_count(p) for p in s.segment_files(sess))
        self.ok(self.fin(sess))
        self.assertEqual(self.video_path(sess), "copy")
        v = self.the_video(sess)
        for sel in ("v:0", "a:0"):
            dts = m.packet_dts(v, sel)
            self.assertTrue(dts, f"串流 {sel} 應有封包")
            self.assertTrue(all(b > a for a, b in zip(dts, dts[1:])), f"串流 {sel} 的 dts 應嚴格遞增")
        dec = subprocess.run([s.REAL_FFMPEG, "-v", "error", "-nostdin", "-i", str(v), "-enc_time_base", "demux",
                              "-f", "null", "-"], capture_output=True, text=True)
        self.assertEqual((dec.returncode, dec.stderr.strip()), (0, ""), "成品應可完整解碼")
        self.assertGreaterEqual(m.frame_count(v), frames, "影格數不得少於各段總和")
        ts = m.frame_times(v)
        self.assertEqual([round(b - a, 4) for a, b in zip(ts, ts[1:]) if b - a < 0.001], [], "不得有 < 1 ms 的影格間隔")

    # spec §4.4.5（meeting-record §4.6.20 (ii)）：錄音/*.wav 與影片音訊軌 duration 差 ≤ 25 ms
    def test_copy_audio_lengths_25ms(self):
        sess = self.session()
        self.ok(self.fin(sess))
        self.assertEqual(self.video_path(sess), "copy")
        wav = s.wavs(sess)
        self.assertEqual(len(wav), 1)
        diff = abs(m.stream_duration(wav[0], "audio") - m.stream_duration(self.the_video(sess), "audio"))
        self.assertLessEqual(diff, 0.025, f"wav 與影片音訊軌差 {diff:.4f} 秒，應 ≤ 25 ms")

    # spec §4.4.6、§6 第 12 條：concat 不得含 +faststart
    def test_no_faststart(self):
        srcs = [s.FINALIZE_PY] + sorted((s.BIN / "lib").glob("_finalize_*.py"))
        for p in srcs:
            self.assertFalse("+faststart" in p.read_text(encoding="utf-8"), f"{p.relative_to(s.REPO)} 不得含 +faststart")
        sess = self.session()
        self.ok(self.fin(sess))
        used = [c["argv"] for c in s.ffmpeg_calls(self.log) if any("faststart" in x for x in c["argv"])]
        self.assertEqual(used, [], "ffmpeg 呼叫不得帶 faststart")

    # spec §4.4.7：每一段的 ffprobe 呼叫 ≤ 3 次（含封包掃描）
    def test_probe_calls_per_segment(self):
        for label, canvas in (("copy", CANVAS), ("reencode", None)):
            with self.subTest(path=label):
                sess = self.session(canvas=canvas, sub=label)
                plog = self.base / f"{label}-ffprobe.log"
                self.ok(self.fin(sess, MH_FFPROBE=s.COUNT_FFPROBE, MS_FFPROBE_LOG=plog))
                calls = s.argv_log(plog)
                self.assertTrue(calls, "前提：ffprobe 應經計數替身")
                for i in range(1, 4):
                    name = f"seg-{i:04d}.mov"
                    n = sum(1 for a in calls if any(os.path.basename(x) == name for x in a))
                    self.assertLessEqual(n, 3, f"{name} 的 ffprobe 呼叫 {n} 次，應 ≤ 3")

    # spec §4.4.8：步驟名維持 normalize／concat／mix／probe；驗證的對象記 verify:<影片檔名>，抽音訊記 seg-NNNN
    def test_verify_step_label(self):
        sess = self.session()
        r = self.fin(sess)
        self.ok(r)
        lines = step_lines(r.stdout)
        self.assertTrue(lines, "前提：stdout 應有「耗時 <步驟>（<對象>）」行")
        self.assertEqual({st for st, _ in lines} - STEPS, set(), f"步驟名只能是 {sorted(STEPS)}")
        video = self.the_video(sess).name
        self.assertIn(f"verify:{video}", [t for _, t in lines], "驗證步驟的對象應記成 verify:<影片檔名>")
        self.assertTrue([1 for st, t in lines if st in ("mix", "normalize") and re.fullmatch(r"seg-\d{4}", t)],
                        "copy 路徑抽各段音訊的步驟對象應記成 seg-NNNN")

    # spec §4.4.10（N-3）：沒有任何一段以 libx264 重編成功時不得印「改用 libx264」；成功後才印
    def test_x264_note_only_after_success(self):
        sess = self.session(canvas=None, sub="都失敗")
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="videotoolbox,libx264", MH_FINALIZE_JOBS=3)
        self.assertEqual(r.returncode, 5, s.out_of(r))
        self.assertFalse("改用 libx264" in r.stdout + r.stderr, "libx264 沒有成功時不得印「改用 libx264」")
        sess = self.session(canvas=None, sub="退回成功")
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="videotoolbox", MH_FINALIZE_JOBS=3)
        self.ok(r)
        self.assertIn("改用 libx264", r.stdout, "以 libx264 重編成功後應印「改用 libx264」")

    # spec §4.5.1：影片 rename 進 影片/ → manifest → finalize.json 第二階段（verify pending）→「成品就緒：」→ 背景驗證
    def test_publish_before_verify(self):
        sess = self.session()
        p = s.finalize_popen(sess, self.home, MH_FFMPEG=s.SLOW_FFMPEG, MS_FFMPEG_LOG=self.log,
                             MS_FFMPEG_SLOW_ON="verify", MS_FFMPEG_SLOW_SECONDS=3)
        self.addCleanup(s.kill_quietly, p)

        def verifying():
            return any(c["cls"] == "verify" and c["end"] is None for c in s.ffmpeg_calls(self.log))

        seen = None
        while p.poll() is None and seen is None:
            if verifying():
                seen = {"videos": [v.name for v in s.videos(sess)], "wavs": [w.name for w in s.wavs(sess)],
                        "fin": s.finalize_json(sess)}
            else:
                time.sleep(0.05)
        out, err = p.communicate(timeout=300)
        self.assertEqual(p.returncode, 0, f"\nstdout:{out}\nstderr:{err}")
        self.assertIsNotNone(seen, "前提：應觀察到驗證進行中")
        self.assertEqual(len(seen["videos"]), 1, f"驗證進行中影片應已在 影片/：{seen}")
        self.assertEqual(len(seen["wavs"]), 1, "驗證進行中正式 wav 應已在 錄音/")
        fin = seen["fin"] or {}
        self.assertTrue(fin.get("videoPublishedAt"), "驗證前 finalize.json 第二階段應已寫好")
        self.assertEqual((fin.get("verify") or {}).get("status"), "pending")
        self.assertIn(f"成品就緒：影片/{seen['videos'][0]}", out)

    # spec §4.5.2：驗證通過 → verify.status ok、record: done、刪段落、回 0
    def test_verify_ok_cleans_segments(self):
        sess = self.session()
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(((s.finalize_json(sess) or {}).get("verify") or {}).get("status"), "ok")
        self.assertEqual(s.segment_files(sess), [], "驗證通過後應刪段落")
        self.assertEqual(((s.pipeline_state(sess) or {}).get("stages") or {}).get("record"), {"status": "done"})

    # spec §4.5.3：驗證失敗 → 影片改名 .verify-failed.mov、verify 記失敗原因、保留段落、stderr 提示 finish、回 5；wav 不動
    def test_verify_failed_renamed(self):
        sess = self.session()
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="verify")
        self.assertEqual(r.returncode, 5, s.out_of(r))
        vids = sorted(p.name for p in (sess / "影片").glob("*.mov")) if (sess / "影片").is_dir() else []
        self.assertEqual(len(vids), 1, vids)
        self.assertTrue(vids[0].endswith(".verify-failed.mov"), f"驗證失敗的影片應改名為 <同名>.verify-failed.mov：{vids}")
        verify = (s.finalize_json(sess) or {}).get("verify") or {}
        self.assertEqual(verify.get("status"), "failed")
        self.assertTrue(verify.get("reason"), "應記失敗原因")
        self.assertEqual(verify.get("path"), "copy")
        self.assertEqual(len(s.segment_files(sess)), 3, "段落都應保留")
        self.assertIn("meeting record finish", r.stderr)
        self.assertEqual(len(s.wavs(sess)), 1, "正式 wav 不動")

    # spec §4.5.4：上一次 copy 路徑驗證失敗，再跑 finish 時強制走重編
    def test_verify_failed_rerun_forces_reencode(self):
        sess = self.session()
        r = self.fin(sess, MS_FFMPEG_FAIL_ON="verify")
        self.assertEqual(r.returncode, 5, s.out_of(r))
        self.assertEqual(((s.finalize_json(sess) or {}).get("verify") or {}).get("path"), "copy", "前提：上一次是 copy 路徑")
        r = self.fin(sess)
        self.ok(r)
        self.assertEqual(self.video_path(sess), "reencode", "上一次 copy 驗證失敗，這次應強制重編")
        self.assertEqual(((s.finalize_json(sess) or {}).get("verify") or {}).get("status"), "ok")

    # spec §4.3.4：verify.status == failed 時 already_done 不得判為完成
    def test_verify_failed_not_done(self):
        sess = self.session()
        self.ok(self.fin(sess, MH_KEEP_SEGMENTS=1))
        fp = s.tracks_of(sess) / "finalize.json"
        fin = json.loads(fp.read_text(encoding="utf-8"))
        fin["verify"] = {"status": "failed", "reason": "範例原因", "path": fin.get("videoPath", "copy")}
        fp.write_text(json.dumps(fin, ensure_ascii=False), encoding="utf-8")
        r = self.fin(sess, MH_KEEP_SEGMENTS=1)
        self.ok(r)
        self.assertFalse(DONE in r.stdout, f"verify 失敗的場次不得判為已完成：{r.stdout.strip()[:200]}")

    # spec §4.3.4：舊 finalize.json（沒有 verify 鍵）判為完成
    def test_old_finalize_json_is_done(self):
        sess = self.session()
        self.ok(self.fin(sess, MH_KEEP_SEGMENTS=1))
        fp = s.tracks_of(sess) / "finalize.json"
        fin = json.loads(fp.read_text(encoding="utf-8"))
        for k in ("verify", "videoPath", "videoPublishedAt"):
            fin.pop(k, None)
        fp.write_text(json.dumps(fin, ensure_ascii=False), encoding="utf-8")
        v = self.the_video(sess)
        before = v.stat().st_mtime_ns
        r = self.fin(sess, MH_KEEP_SEGMENTS=1)
        self.ok(r)
        self.assertIn(DONE, r.stdout, "沒有 verify 鍵的舊 finalize.json 應判為完成")
        self.assertEqual(v.stat().st_mtime_ns, before)

    # spec §4.4.12（D3 a）：link_fps 低報（58 對實際 60）、最後一幀距段落結束 ≥ 1 秒時，補尾仍到 cap、finalize 回 0
    def test_tail_pad_low_r_frame_rate(self):
        sess = self.session([dict(dur=12.0, vdur=3.0, fps=60)], canvas=None)
        r = s.run([s.PY, "-c", TAIL_PAD_PATCHED, s.FINALIZE_PY, sess], s.base_env(self.home), timeout=300)
        self.assertEqual(r.returncode, 0, f"末 9 秒靜止、link_fps 回 58 時補尾應到 cap、回 0{s.out_of(r)}")
        v = self.the_video(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertLess(abs(vd - ad), 0.1, f"影片軌 {vd} 應補到音訊軌 {ad}（差 < 100 ms）")


if __name__ == "__main__":
    unittest.main()

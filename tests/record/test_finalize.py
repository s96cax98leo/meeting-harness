"""spec §4.6、§4.13.3：record finish（bin/_record_finalize.py）的產出。合成素材只在 TMPDIR。

D20（t6 中途修正輪）新增 §4.6.13–4.6.15 三支：兩條音軌混音、實機時間戳特性的串接、被中斷的 fragment 段落。
t6 第二輪（缺陷 B、F）新增 §4.6.17–4.6.18 兩支：尾幀不得被編得過長、稀疏 VFR 的最後一段。
t6 第三輪（缺陷 J）新增 §4.6.20 一支：串接不得讓音訊逐段延後。
t6 第三輪實機（缺陷 N）新增兩支：稀疏 VFR 段落最後一幀距段落結束 60–80 ms 時應補尾到 cap，不得回 5。
t6 第三輪實機回歸（0330 場次，§4.3.3 (ii)）新增一支：補尾不得在同一個段落邊界製造 2 個過近間隔。
"""
import importlib.util
import json
import math
import re
import statistics
import subprocess
import unittest
from pathlib import Path

from tests.record import _media as m
from tests.record._helpers import Sandbox, scaffold_meeting_json_keys, scaffold_ts_re, snapshot

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mov", ".mp4", ".m4v"}
E2E_PY = Path(__file__).resolve().parent / "e2e_check.py"
NAME_RE = re.compile(r"^" + re.escape(m.SESSION_NAME) + r" \d{4}-\d{2}-\d{2} \d{2}\.\d{2}\.\d{2}\.(wav|mov)$")


class FinalizeCase(unittest.TestCase):
    def finish(self, segments, **env):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, segments)
        r = sb.meeting("record", "finish", sess, timeout=300, **env)
        return sb, sess, r

    def audio_files(self, sess):
        rec = sess / "錄音"
        return sorted(p for p in rec.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS)

    def video_file(self, sess):
        vids = sorted((sess / "影片").glob("*.mov"))
        self.assertEqual(len(vids), 1, f"影片/ 應恰有一個 .mov：{vids}")
        return vids[0]

    def ok(self, r):
        self.assertEqual(r.returncode, 0, f"record finish 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")


class TestFinalize(FinalizeCase):
    THREE = [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)]

    # spec §4.6.1
    def test_exactly_one_audio_file(self):
        _, sess, r = self.finish(self.THREE)
        self.ok(r)
        self.assertEqual(len(self.audio_files(sess)), 1)

    # spec §4.6.2
    def test_wav_format_and_name(self):
        _, sess, r = self.finish(self.THREE)
        self.ok(r)
        files = self.audio_files(sess)
        self.assertEqual(len(files), 1)
        wav = files[0]
        self.assertEqual(wav.suffix, ".wav")
        self.assertRegex(wav.name, NAME_RE)
        self.assertIsNotNone(scaffold_ts_re().search(wav.name), "檔名應能被 _scaffold.py 的 TS_RE 比對")
        a = m.stream(wav, "audio")
        self.assertEqual(int(a["sample_rate"]), 16000)
        self.assertEqual(int(a["channels"]), 1)

    # spec §4.6.3：影片軌刻意比音訊短 2 秒
    def test_video_audio_duration_within_100ms(self):
        _, sess, r = self.finish([dict(dur=4.0, vdur=2.0), dict(dur=3.0)])
        self.ok(r)
        v = self.video_file(sess)
        self.assertRegex(v.name, NAME_RE)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertIsNotNone(vd)
        self.assertIsNotNone(ad)
        self.assertLess(abs(vd - ad), 0.1, f"影片軌 {vd} 與音訊軌 {ad} 差應 < 100 ms")

    # spec §4.6.4：key 集合＝_scaffold.py 寫的 7 個（ast 取得），expectedSpeakers 為 null
    def test_meeting_json_keys_match_scaffold(self):
        sb = Sandbox(self, scenario="recording")
        r = sb.meeting("record", sb.root, "--window", "41001", timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        found = list(sb.root.rglob("錄音/meeting.json"))
        self.assertEqual(len(found), 1, f"開錄後應在場次 錄音/ 寫 meeting.json：{found}")
        data = json.loads(found[0].read_text(encoding="utf-8"))
        self.assertEqual(set(data), scaffold_meeting_json_keys())
        self.assertIsNone(data["expectedSpeakers"])
        self.assertNotIn("鎖定", data.get("_note", ""), "_note 不得出現「鎖定人數」之意")

    # spec §4.6.6
    def test_idempotent_second_run(self):
        sb, sess, r = self.finish(self.THREE)
        self.ok(r)
        before = snapshot(sess)
        r2 = sb.meeting("record", "finish", sess, timeout=300)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("已完成", r2.stdout + r2.stderr)
        self.assertEqual(snapshot(sess), before, "第二次 finish 不得改動任何檔的內容或 mtime")

    # spec §6 第 111 條
    def test_segments_removed_after_success(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.THREE)
        tracks = sess / "錄音" / "tracks"
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        self.assertEqual(list(tracks.glob("seg-*.mov")), [], "收尾成功後原始段落應刪除")
        for keep in ("manifest.json", "record.meta.json", "finalize.json"):
            self.assertTrue((tracks / keep).is_file(), f"{keep} 應保留")
        self.assertTrue(self.video_file(sess).is_file())
        r2 = sb.meeting("record", "finish", sess, timeout=300)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("已完成", r2.stdout + r2.stderr)

    # spec §4.6.7
    def test_tracks_preserved(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.THREE)
        tracks = sess / "錄音" / "tracks"
        keep = {p.name: p.read_bytes() for p in tracks.glob("seg-*.mov")}
        # §6 第 111 條：預設收尾成功後刪原始段落；MH_KEEP_SEGMENTS=1（或 <home>/keep-segments）時保留且內容不變
        r = sb.meeting("record", "finish", sess, timeout=300, MH_KEEP_SEGMENTS="1")
        self.ok(r)
        for name, data in keep.items():
            self.assertTrue((tracks / name).is_file(), f"{name} 不得被刪")
            self.assertEqual((tracks / name).read_bytes(), data, f"{name} 內容不得改變")
        self.assertTrue((tracks / "manifest.json").is_file())
        self.assertTrue((tracks / "record.meta.json").is_file())
        fin = tracks / ".finalize"
        if fin.exists():
            self.assertEqual(sorted(p.name for p in fin.glob("norm-*")), [], ".finalize/ 的暫存應清掉")

    # spec §4.6.8
    def test_manifest_gapstats_written(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.THREE, gap=0.05)
        mf = sess / "錄音" / "tracks" / "manifest.json"
        orig = json.loads(mf.read_text(encoding="utf-8"))
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        out = json.loads(mf.read_text(encoding="utf-8"))
        for k in ("frameStatus", "blackIntervals", "levels", "segmentSeconds", "schemaVersion"):
            self.assertEqual(out[k], orig[k], f"{k} 應保留不動")
        gs = out["gapStats"]
        self.assertEqual(set(gs), {"boundaries", "max", "total", "wallClock"})
        segs = out["segments"]
        ads = [s["audioDuration"] for s in segs]
        self.assertTrue(all(isinstance(a, (int, float)) for a in ads), ads)
        st = [s["startedAt"] for s in segs]
        want = [st[i + 1] - st[i] - ads[i] for i in range(len(st) - 1)]
        self.assertEqual(len(gs["boundaries"]), len(want))
        for g, w in zip(gs["boundaries"], want):
            self.assertAlmostEqual(g, w, delta=0.002)
        self.assertAlmostEqual(gs["max"], max(want), delta=0.002)
        self.assertAlmostEqual(gs["total"], sum(want), delta=0.003)
        self.assertEqual(out["outputCanvas"], {"width": 320, "height": 240})
        self.assertIsInstance(out["outputVideoBitrate"], int)
        state = json.loads((sess / ".pipeline-state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["stages"]["record"]["status"], "done")

    # spec §4.6.9
    def test_skips_unreadable_segment(self):
        _, sess, r = self.finish([dict(dur=2.0), dict(dur=2.0, truncate=True), dict(dur=2.0)])
        self.ok(r)
        self.assertIn("seg-0002.mov", r.stdout + r.stderr, "應列出被略過的段落")
        wav = self.audio_files(sess)[0]
        self.assertAlmostEqual(m.stream_duration(wav, "audio"), 4.0, delta=0.15)

    # spec §4.6.10：畫布＝(各段寬最大值, 各段高最大值)，不縮放、置中補黑邊
    def test_mixed_sizes_padded_not_scaled(self):
        _, sess, r = self.finish([dict(w=1280, h=720, dur=2.0, video="red"),
                                  dict(w=960, h=600, dur=2.0, video="green")])
        self.ok(r)
        v = self.video_file(sess)
        vs = m.stream(v, "video")
        self.assertEqual((int(vs["width"]), int(vs["height"])), (1280, 720))
        W, H = 1280, 720
        first = m.frame_rgb(v, 1.0, W, H)
        self.assertGreater(m.pixel(first, W, 5, 5)[0], 150, "第一段填滿畫布，角落應為紅色")
        second = m.frame_rgb(v, 3.0, W, H)
        center = m.pixel(second, W, 640, 360)
        self.assertGreater(center[1], 100, f"第二段中心應為綠色：{center}")
        self.assertLess(center[0], 80)
        for x, y in ((5, 5), (W - 6, 5), (5, H - 6), (W - 6, H - 6), (150, 360), (640, 50)):
            px = m.pixel(second, W, x, y)
            self.assertLess(max(px), 40, f"({x},{y}) 應為補邊的黑色：{px}")
        inside = m.pixel(second, W, 160 + 8, 60 + 8)
        self.assertGreater(inside[1], 100, f"960×600 內容應原尺寸置中（不縮放）：{inside}")

    # spec §4.6.10：H.264 high、位元率 ≥ 各段最大值、不改 fps、可完整解碼
    def test_reencode_quality_and_fps_preserved(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0, fps=30), dict(dur=2.0, fps=30)])
        segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
        in_rate = max(int(m.stream(s, "video")["bit_rate"]) for s in segs)
        in_gap = min(b - a for s in segs for a, b in zip(m.frame_times(s), m.frame_times(s)[1:]))
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        v = self.video_file(sess)
        vs = m.stream(v, "video")
        self.assertEqual(vs["codec_name"], "h264")
        self.assertEqual(vs.get("profile"), "High")
        self.assertGreaterEqual(int(vs["bit_rate"]), in_rate)
        ts = m.frame_times(v)
        out_gap = min(b - a for a, b in zip(ts, ts[1:]))
        self.assertGreaterEqual(out_gap, in_gap - 0.001, "相鄰影格最小間隔不得小於輸入")
        dec = subprocess.run([m.FFMPEG, "-v", "error", "-i", str(v), "-f", "null", "-"],
                             capture_output=True, text=True)
        self.assertEqual(dec.stderr.strip(), "", "輸出應可完整解碼、沒有錯誤")

    # spec §4.6.11
    def test_segment_without_video_filled(self):
        _, sess, r = self.finish([dict(dur=2.0), dict(dur=2.0, video=None), dict(dur=2.0)])
        self.ok(r)
        v = self.video_file(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertAlmostEqual(ad, 6.0, delta=0.2)
        self.assertLess(abs(vd - ad), 0.1, "缺影片的段應被補上，影片軌涵蓋全程")

    # spec §4.6.12
    def test_mixed_audio_formats_concat(self):
        _, sess, r = self.finish([dict(dur=2.0, ar=48000, ac=2), dict(dur=2.0, ar=16000, ac=1)])
        self.ok(r)
        v = self.video_file(sess)
        a = m.stream(v, "audio")
        self.assertEqual(a["codec_name"], "aac")
        self.assertEqual(int(a["sample_rate"]), 48000)
        self.assertEqual(int(a["channels"]), 2)
        self.assertAlmostEqual(float(a["duration"]), 4.0, delta=0.05 * 2)

    # spec §4.6.13（D20）：兩條音軌（系統聲音 440 Hz 雙聲道、麥克風 1000 Hz 單聲道，各 -20 dBFS）等權混成一軌
    def test_two_audio_tracks_mixed(self):
        segs = [dict(recipe="two_tracks", dur=3.0, sys_freq=440, mic_freq=1000, level_db=-20.0)] * 2
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, segs)
        first = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))[0]
        self.assertEqual([x["codec_type"] for x in (m.probe(first) or {"streams": []})["streams"]],
                         ["video", "audio", "audio"], "合成素材前提：段落應為影片＋兩條音軌")
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        v = self.video_file(sess)
        self.assertEqual(len(m.streams(v, "audio")), 1, "影片/*.mov 應恰有一條音軌（混成一軌）")
        wav = self.audio_files(sess)[0]
        self.assertEqual(int(m.stream(wav, "audio")["channels"]), 1, "錄音/*.wav 應為單聲道")
        # 帶通量各頻率成分的 RMS；去掉頭尾 0.3 秒與段落邊界附近 0.3 秒，避開濾波器暫態與 AAC priming
        keep = [(0.3, 2.7), (3.3, 5.7)]
        for label, path in (("錄音/*.wav", wav), ("影片/*.mov", v)):
            for freq in (440, 1000):
                with self.subTest(file=label, freq=freq):
                    band = m.pcm_s16(path, af=f"bandpass=f={freq}:width_type=q:w=4,bandpass=f={freq}:width_type=q:w=4")
                    body = [x for a, b in keep for x in band[int(a * 16000):int(b * 16000)]]
                    db = m.rms_dbfs(body)
                    self.assertTrue(-23.0 <= db <= -17.0,
                                    f"{label} 的 {freq} Hz 成分 RMS 應在 -20 dBFS ± 3 dB（等權、不做 1/2 衰減）："
                                    f"實際 {db:.1f} dBFS")
        whole = m.pcm_s16(wav)
        pk = m.peak_dbfs(whole)
        self.assertLessEqual(pk, -1.0 + 0.1, f"整體峰值應 ≤ -1 dBFS（限幅）：實際 {pk:.2f} dBFS")

    # spec §4.6.14（D20，t6 缺陷 3）：先逐段正規化時間戳再串接
    def test_irregular_timestamps_concat(self):
        with self.subTest(recipe="A：VFR、time_base=1/600、B-frame"):
            sb = Sandbox(self)
            sess = m.make_record_session(sb.root, [dict(recipe="irregular", dur=4.0)] * 3)
            segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
            vs0 = m.stream(segs[0], "video")
            self.assertEqual((vs0.get("time_base"), int(vs0.get("has_b_frames") or 0)), ("1/600", 2),
                             "合成素材前提：影片軌 time_base=1/600、has_b_frames=2")
            in_frames, dups = 0, 0
            for seg in segs:
                ts = m.frame_times(seg)
                in_frames += len(ts)
                dups += len(ts) - len(set(ts))
            r = sb.meeting("record", "finish", sess, timeout=300)
            self.ok(r)
            v = self.video_file(sess)
            for kind in ("v:0", "a:0"):
                dts = m.packet_dts(v, kind)
                self.assertTrue(dts, f"{kind} 讀不到封包")
                bad = sum(1 for a, b in zip(dts, dts[1:]) if b <= a)
                self.assertEqual(bad, 0, f"(i) {kind} 的封包 dts 應嚴格遞增：{bad} 處不遞增")
            dec = subprocess.run([m.FFMPEG, "-v", "error", "-i", str(v), "-enc_time_base", "demux", "-f", "null", "-"],
                                 capture_output=True, text=True)
            self.assertEqual(dec.stderr.strip(), "", "(ii) 完整解碼檢查不得有錯誤輸出")
            out_ts = m.frame_times(v)
            self.assertGreaterEqual(len(out_ts), in_frames - dups,
                                    f"(iii) 輸出影格數 {len(out_ts)} 應 ≥ 輸入 {in_frames} − 重複 PTS {dups}（不得以丟幀換遞增）")
            tight = sum(1 for a, b in zip(out_ts, out_ts[1:]) if b - a < 0.001)
            self.assertEqual(tight, 0, f"(iv) 相鄰影格間隔 < 1 ms 的對數應為 0：{tight}")
            vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
            self.assertIsNotNone(vd)
            self.assertIsNotNone(ad)
            self.assertLess(abs(vd - ad), 0.1, f"(v) §4.6.3：影片軌 {vd} 與音訊軌 {ad} 差應 < 100 ms")

        with self.subTest(recipe="B：影片晚 0.2 秒開始、音訊負 start_time"):
            from tests.record.e2e_check import beeps, flashes

            sb = Sandbox(self)
            sess = m.make_record_session(sb.root, [dict(recipe="late_video_sync", dur=9.0)])
            seg = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))[0]
            self.assertGreaterEqual(float(m.stream(seg, "video").get("start_time") or 0), 0.15,
                                    "合成素材前提：影片軌晚開始")
            # ffmpeg 7 的 mov muxer 把負時間戳寫成 edit list，ffprobe 的 stream start_time 仍報 0；
            # 以「第一個音訊封包的 pts 為負」確認素材確實以負時間戳寫入
            first_pts = m.packet_pts(seg, "a:0")
            self.assertTrue(first_pts and first_pts[0] < 0, f"合成素材前提：音訊以負時間戳寫入（edit list）：{first_pts[:2]}")
            r = sb.meeting("record", "finish", sess, timeout=300)
            self.ok(r)
            v = self.video_file(sess)
            f, b = flashes(v), beeps(v)
            self.assertGreaterEqual(len(f), 3, f"應找到至少 3 次閃白：{f}")
            self.assertGreaterEqual(len(b), 3, f"應找到至少 3 次嗶聲：{b}")
            worst = max(abs(min((x - t for x in b), key=abs)) for t in f)
            self.assertLess(worst, 0.1, f"(vi) 段內閃白與嗶聲的時間差應 < 100 ms：最大 {worst * 1000:.0f} ms")

    # spec §4.6.15（D20）：被中斷的 fragment 段落應納入可讀部分，audioDuration 由封包算
    def test_truncated_fragment_segment_used(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0), dict(recipe="fragment", dur=10.0)])
        frag = sess / "錄音" / "tracks" / "seg-0002.mov"
        decoded = m.decoded_audio_end(frag)
        reported = m.stream_duration(frag, "audio")
        self.assertIsNotNone(decoded, "合成素材前提：fragment 段落應讀得到可解碼的音訊")
        self.assertIsNotNone(reported)
        self.assertGreater(reported - decoded, 0.5, "合成素材前提：stream 層 duration 應高報（比可解碼長度長）")
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        self.assertNotIn("seg-0002.mov", r.stdout + r.stderr, "被中斷的 fragment 段落不得被列為略過")
        mf = json.loads((sess / "錄音" / "tracks" / "manifest.json").read_text(encoding="utf-8"))
        ads = {x["file"]: x["audioDuration"] for x in mf["segments"]}
        self.assertIsNotNone(ads.get("seg-0002.mov"), "fragment 段落應有 audioDuration")
        self.assertAlmostEqual(ads["seg-0002.mov"], decoded, delta=0.1,
                               msg=f"audioDuration 應等於最後一個可解碼音訊封包的結束時間 {decoded:.3f}（stream 層回報 {reported:.3f}）")
        total = sum(a for a in ads.values() if a is not None)
        wav = self.audio_files(sess)[0]
        self.assertAlmostEqual(m.stream_duration(wav, "audio"), total, delta=0.05 * len(ads),
                               msg="輸出音訊長度應等於各段 audioDuration 總和（每段容許 50 ms）")
        self.assertFalse(math.isnan(total))

    def require_videotoolbox(self):
        ok, why = m.videotoolbox_h264_available()
        if not ok:
            self.skipTest(f"缺陷只在 h264_videotoolbox 出現，{why}")

    # spec §4.6.17（t6 第二輪，缺陷 B）：VFR、time_base=1/600、r_frame_rate 600、最後一幀距段落結束 < 0.01 秒
    def test_tail_frame_not_overlong(self):
        self.require_videotoolbox()
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(recipe="vfr_tail", dur=15.1988)])
        seg = sess / "錄音" / "tracks" / "seg-0001.mov"
        vs = m.stream(seg, "video")
        self.assertEqual((vs.get("time_base"), vs.get("r_frame_rate")), ("1/600", "600/1"),
                         "合成素材前提：影片軌 time_base=1/600、r_frame_rate=600")
        seglen = m.segment_length(seg)
        self.assertAlmostEqual(seglen, 15.199, delta=0.0005, msg="合成素材前提：段落長 15.199 秒")
        ts = m.frame_times(seg)
        self.assertLess(seglen - ts[-1], 0.01, "合成素材前提：最後一幀距段落結束 < 0.01 秒（不需補尾）")
        avg = len(ts) / ts[-1]
        self.assertTrue(8 <= avg <= 16, f"合成素材前提：平均影格率約 12 fps，實際 {avg:.1f}")
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        v = self.video_file(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertIsNotNone(vd)
        self.assertIsNotNone(ad)
        self.assertLessEqual(vd, seglen + 1 / 600 + 1e-6,
                             f"輸出影片軌 duration {vd:.3f} 應 ≤ 段落長 {seglen:.3f}＋1/600 秒（尾幀不得被編得過長）")
        self.assertLess(abs(vd - ad), 0.1, f"§4.6.3：影片軌 {vd:.3f} 與音訊軌 {ad:.3f} 差應 < 100 ms")

    # spec §4.6.18（t6 第二輪，缺陷 F）：最後一段影片只有少數幾幀、r_frame_rate 很低、影片比音訊早很多結束
    def test_sparse_vfr_last_segment_covers_audio(self):
        self.require_videotoolbox()
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(recipe="two_tracks", dur=5.0, fps=10),
                                               dict(recipe="sparse_vfr", dur=20.0)])
        segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
        self.assertEqual(len(segs), 2)
        last = m.stream(segs[1], "video")
        self.assertEqual((last.get("r_frame_rate"), int(last.get("nb_frames") or 0)), ("4/3", 8),
                         "合成素材前提：最後一段影片 r_frame_rate=4/3、只有 8 幀")
        self.assertLess(m.stream_duration(segs[1], "video"), m.stream_duration(segs[1], "audio") - 10,
                        "合成素材前提：最後一段影片比音訊早很多結束")
        lens = [m.segment_length(x) for x in segs]
        self.assertAlmostEqual(lens[1], 20.0, delta=0.001, msg="合成素材前提：seg-0002 段落長 20.0 秒")
        total = sum(lens)
        in_frames = sum(m.frame_count(x) for x in segs)
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        v = self.video_file(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertIsNotNone(vd)
        self.assertIsNotNone(ad)
        self.assertLess(abs(vd - ad), 0.1, f"§4.6.3：影片軌 {vd:.3f} 與音訊軌 {ad:.3f} 差應 < 100 ms")
        self.assertTrue(total - 0.05 <= vd <= total + 1 / 600 + 1e-6,
                        f"輸出影片軌 duration {vd:.3f} 應落在 [Σ段落長 {total:.3f} − 0.05, Σ段落長＋1/600]")
        out_frames = m.frame_count(v)
        self.assertGreaterEqual(out_frames, in_frames, f"輸出影格數 {out_frames} 應 ≥ 各段影格數總和 {in_frames}（不得以丟幀換長度）")

    # spec §4.6.20（t6 第三輪，缺陷 J）：≥ 3 段、段長不是 1024 樣本的整數倍、第一段音訊晚開始
    # （系統聲音前 50 ms 靜音）；不需 h264_videotoolbox（缺陷與影片編碼器無關），不得 skip
    def test_concat_no_audio_drift(self):
        spec = importlib.util.spec_from_file_location("e2e_check_ro", E2E_PY)
        e2e = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(e2e)  # 只讀：共用 §4.9.3 的 sync 量法
        lengths = m.DRIFT_LENGTHS
        bounds = [sum(lengths[:i]) for i in range(len(lengths) + 1)]
        self.assertTrue(all(round(L * 48000) % 1024 for L in lengths), "合成素材前提：段長都不是 1024 樣本的整數倍")
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, m.drift_segments(lengths), gap=0.0)
        segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
        self.assertEqual(len(segs), 4, "合成素材前提：4 段")
        mf = json.loads((sess / "錄音" / "tracks" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["startedAt"] for r in mf["segments"]], [round(b, 3) for b in bounds[:-1]],
                         "合成素材前提：startedAt 照累加段長")

        def medians(pairs, spans):
            """每段時距內「嗶聲 − 閃白」的中位數；離段落邊界 < 0.15 秒的閃白不計（邊界上的閃白歸屬不明）。"""
            inner = spans[1:-1]
            out = []
            for a, b in zip(spans, spans[1:]):
                vals = [d for t, d in pairs if d is not None and a <= t < b and all(abs(t - x) >= 0.15 for x in inner)]
                out.append(statistics.median(vals) if vals else None)
            return out

        orig = []
        for i, seg in enumerate(segs):
            pairs = e2e.sync_offsets(seg, 0)  # 系統聲音軌
            L = lengths[i]
            # 與 medians 同一規則：離相鄰段落的邊界 < 0.15 秒的閃白不計（第一段的起點與最後一段的終點不算邊界）
            vals = [d for t, d in pairs if d is not None and (i == 0 or t >= 0.15) and
                    (i == len(segs) - 1 or t <= L - 0.15)]
            self.assertTrue(vals, f"合成素材前提：seg-{i + 1:04d} 至少有一組閃白與嗶聲")
            orig.append(statistics.median(vals))
        first = e2e.sync_offsets(segs[0], 0)
        self.assertTrue(first and first[0][1] is not None and first[0][1] >= 0.04,
                        f"合成素材前提：第一段系統聲音前 50 ms 靜音（第一個閃白的嗶聲晚約 50 ms）：{first[:1]}")
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.ok(r)
        v = self.video_file(sess)
        wav = self.audio_files(sess)[0]
        ad = m.stream_duration(v, "audio")
        self.assertIsNotNone(ad)
        with self.subTest(check="(i) 解碼樣本數 ÷ 48000 與音訊軌 stream duration 差 ≤ 25 ms"):
            decoded = len(m.pcm_s16(v, rate=48000)) / 48000
            self.assertLessEqual(abs(decoded - ad), 0.025,
                                 f"影片/*.mov 音訊軌解碼長度 {decoded:.3f}s 與 stream duration {ad:.3f}s 差 "
                                 f"{(decoded - ad) * 1000:.0f} ms（應 ≤ 25 ms，§4.6.20 (i)）")
        with self.subTest(check="(ii) 錄音/*.wav 長度與影片音訊軌 stream duration 差 ≤ 25 ms"):
            wd = m.stream_duration(wav, "audio")
            self.assertIsNotNone(wd)
            self.assertLessEqual(abs(wd - ad), 0.025,
                                 f"錄音/*.wav {wd:.3f}s 與影片音訊軌 {ad:.3f}s 差 {(wd - ad) * 1000:.0f} ms（§4.6.20 (ii)）")
        with self.subTest(check="(iii) 各段時距內嗶聲 − 閃白中位數與原始段落差 ≤ 10 ms"):
            got = medians(e2e.sync_offsets(v), bounds)
            for i, (g, o) in enumerate(zip(got, orig)):
                self.assertIsNotNone(g, f"影片/*.mov 在 seg-{i + 1:04d} 的時距內找不到閃白與嗶聲")
                self.assertLessEqual(abs(g - o), 0.010,
                                     f"seg-{i + 1:04d} 時距：最終影片中位 {g * 1000:.0f} ms、原始段落 {o * 1000:.0f} ms，"
                                     f"差 {(g - o) * 1000:.0f} ms（應 ≤ 10 ms，§4.6.20 (iii)）；"
                                     f"全部：最終 {[round(x * 1000) if x is not None else None for x in got]}、"
                                     f"原始 {[round(x * 1000) for x in orig]}")

    def assert_sparse_tail_premise(self, seg):
        vs = m.stream(seg, "video")
        self.assertEqual((vs.get("time_base"), vs.get("r_frame_rate")), ("1/600", "600/1"),
                         "合成素材前提：影片軌 time_base=1/600、r_frame_rate=600")
        self.assertEqual(len(m.streams(seg, "audio")), 2, "合成素材前提：兩條 AAC 音軌")
        seglen = m.segment_length(seg)
        self.assertAlmostEqual(seglen, 10.177, delta=0.005, msg="合成素材前提：段落長約 10.18 秒")
        ts = m.frame_times(seg)
        self.assertAlmostEqual(ts[-1], 10.108, delta=0.001, msg="合成素材前提：最後一幀 PTS 10.108")
        self.assertTrue(0.06 <= seglen - ts[-1] <= 0.08,
                        f"合成素材前提：最後一幀距段落結束 60–80 ms，實際 {(seglen - ts[-1]) * 1000:.0f} ms")
        self.assertEqual(len(ts), 97, "合成素材前提：97 幀（同實機，最後一幀序號 96）")
        avg = len(ts) / ts[-1]
        self.assertTrue(9 <= avg <= 10.5, f"合成素材前提：平均影格率約 9–10 fps，實際 {avg:.2f}")
        return seglen

    def assert_sparse_tail_output(self, r, sess, total):
        self.assertEqual(r.returncode, 0,
                         f"缺陷 N：record finish 應回 0（不得回 5「正規化後 video 軌長 … 與段落長 … 不符」）\n"
                         f"stdout:{r.stdout}\nstderr:{r.stderr}")
        v = self.video_file(sess)
        vd, ad = m.stream_duration(v, "video"), m.stream_duration(v, "audio")
        self.assertIsNotNone(vd)
        self.assertIsNotNone(ad)
        ts = m.frame_times(v)
        self.assertLess(abs(vd - ad), 0.1, f"§4.6.3：影片軌 {vd:.3f} 與音訊軌 {ad:.3f} 差應 < 100 ms")
        self.assertLessEqual(total - ts[-1], 0.05,
                             f"最後一段影片最後一幀 PTS {ts[-1]:.3f} 距段落結束 {total:.3f} 應 ≤ 50 ms（尾端補幀，"
                             f"§4.6.17／§4.6.18），實際 {(total - ts[-1]) * 1000:.0f} ms")
        return v, ts

    # 缺陷 N（t6 第三輪實機；spec §4.6.3、§4.6.17／§4.6.18 的尾端補幀）：稀疏 VFR（time_base 1/600、
    # r_frame_rate 600、平均約 9.6 fps、97 幀）、最後一幀 10.108 距段落結束 10.177 約 68 ms
    def test_sparse_tail_gap_padded(self):
        self.require_videotoolbox()
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(recipe="sparse_tail", dur=10.1763)])
        seglen = self.assert_sparse_tail_premise(sess / "錄音" / "tracks" / "seg-0001.mov")
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.assert_sparse_tail_output(r, sess, seglen)

    # 缺陷 N 多段版：前一段正常 60 fps＋最後一段稀疏；補尾不得破壞 §4.6.10 的相鄰影格最小間隔
    def test_sparse_tail_gap_padded_multi_segment(self):
        self.require_videotoolbox()
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=3.0, fps=60),
                                               dict(recipe="sparse_tail", dur=10.1763)])
        segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
        self.assertEqual(len(segs), 2)
        self.assertEqual(m.stream(segs[0], "video").get("r_frame_rate"), "60/1", "合成素材前提：第一段 60 fps")
        self.assert_sparse_tail_premise(segs[1])
        lens = [m.segment_length(x) for x in segs]
        in_gap = min(b - a for s in segs for a, b in zip(m.frame_times(s), m.frame_times(s)[1:]))
        r = sb.meeting("record", "finish", sess, timeout=300)
        _, ts = self.assert_sparse_tail_output(r, sess, sum(lens))
        out_gap = min(b - a for a, b in zip(ts, ts[1:]))
        self.assertGreaterEqual(out_gap, in_gap - 0.001,
                                f"§4.6.10：相鄰影格最小間隔 {out_gap * 1000:.1f} ms 不得小於輸入 {in_gap * 1000:.1f} ms")

    # spec §4.3.3 (ii)（t6 第三輪實機回歸，0330 場次）：補尾不得在同一個段落邊界製造 2 個過近間隔
    # （< 1/60 秒 − 1 ms）。(a) tpad 第一個複製幀落在「最後一幀 PTS＋最後一幀長度」，距 cap 不到 1/60 秒卻沒被
    # 併進 cap（舊門檻 10 ms）；(b) 最後一幀距 cap 只有 10–15.67 ms，補一幀到 cap 本身就是過近間隔；(c) 最後一幀
    # 長度很短，第一個複製幀緊貼最後一幀。三者再加上 cap 與下一段首幀之間的 5 ms，同一個邊界就有 2 個過近間隔。
    def test_tail_pad_no_extra_close_interval(self):
        self.require_videotoolbox()
        close_max = 1 / 60 - 0.001
        # (段落長, 最後一幀長度 tick, 說明)；最後一幀 PTS 固定 10.108333（6065 tick）
        cases = [(10.163, 22, "複製幀 10.145 距 cap 10.1567 只有 11.7 ms"),
                 (10.126, 5, "最後一幀距 cap 10.12 只有 11.7 ms"),
                 (10.5, 4, "複製幀 10.115 距最後一幀 10.108 只有 6.7 ms（2254 場次 seg-0007）")]
        for dur, last_dur, why in cases:
            with self.subTest(case=why):
                sb = Sandbox(self)
                sess = m.make_record_session(sb.root, [dict(recipe="sparse_tail", dur=dur, last_dur=last_dur),
                                                       dict(dur=3.0, fps=60)])
                segs = sorted((sess / "錄音" / "tracks").glob("seg-*.mov"))
                self.assertEqual(len(segs), 2)
                ts0 = m.frame_times(segs[0])
                self.assertAlmostEqual(ts0[-1], 10.108, delta=0.001, msg="合成素材前提：最後一幀 PTS 10.108")
                seglen = m.segment_length(segs[0])
                self.assertAlmostEqual(seglen, dur, delta=0.002, msg=f"合成素材前提：段落長 {dur}")
                cap = seglen - 0.005
                self.assertTrue(0.01 <= cap - ts0[-1] < 1.0, "合成素材前提：最後一幀距 cap ≥ 10 ms（舊門檻會補尾）")

                def closes(ts):
                    return [(a, b - a) for a, b in zip(ts, ts[1:]) if b - a < close_max]

                orig = sum(len(closes(m.frame_times(s))) for s in segs)
                # 收尾後還要量段落長度：保留原始段落（§6 第 111 條）
                r = sb.meeting("record", "finish", sess, timeout=300, MH_KEEP_SEGMENTS="1")
                self.ok(r)
                ts = m.frame_times(self.video_file(sess))
                got = closes(ts)
                self.assertLessEqual(len(got), orig + len(segs) - 1,
                                     f"§4.3.3 (ii)：過近間隔 {len(got)} 處 {[(round(a, 4), round(d * 1000, 1)) for a, d in got]}"
                                     f"，上限＝原始段落 {orig}＋邊界 {len(segs) - 1}")
                self.assertGreaterEqual(min(b - a for a, b in zip(ts, ts[1:])), 0.001, "§4.3.3 (iii)：最小間隔 ≥ 1 ms")
                self.assertLessEqual(sum(m.segment_length(s) for s in segs) - ts[-1], 0.05,
                                     "§4.6.3：最後一幀距場次結束 ≤ 50 ms")

    # spec §4.13.3
    def test_status_lists_finalized_session(self):
        sb, sess, r = self.finish(self.THREE)
        self.ok(r)
        st = sb.meeting("status", sb.root)
        self.assertEqual(st.returncode, 0)
        self.assertIn(m.SESSION_NAME, st.stdout)


if __name__ == "__main__":
    unittest.main()

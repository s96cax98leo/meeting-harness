"""sdlc-deliver 四軸審查的修正（spec R3x §6 第 158 條；§4.33.1、§4.29.3、§3.18、§4.30.2）。

- search：錄製器的場次是 <根>/YYYYMMDD/HHMM 會議，排序要用相對路徑，不能只看 basename。
- diarize 補段落：段落檔被換掉時，transcript.quality.json 也要換成同一次重轉的版本（鐵則 4），raw 不動（鐵則 1）。
- transcribe：多音檔（.combined.wav 或 錄音/ 第一層超過 1 個音檔）時不套 VAD，VAD 行寫「未套用（多音檔）」。

素材只在 TMPDIR；轉錄一律用 fakes/asr/mlx_whisper 替身。範例名稱一律「[Stand-up] 範例專案」。
既有測試檔不改，只從中匯入輔助函式。
"""
import json
import os
import shutil
import unittest

from tests.record import _media as m
from tests.record._helpers import Sandbox, tmpdir
from tests.record.test_r3_search import make_session, parse
from tests.record.test_r3_transcript_vad import session as vad_session
from tests.record.test_r3_transcript_vad import transcribe, vad_line
from tests.record.test_r3_vtt_raw import DIAR

# 四段相同文字 → repeat_run（每段各一筆）；其餘兩段正常
QSEGS = [(0.0, 3.0, "第一段範例"), (3.0, 5.0, "重複的範例句"), (5.0, 7.0, "重複的範例句"), (7.0, 9.0, "重複的範例句"),
         (9.0, 11.0, "重複的範例句"), (12.0, 15.0, "最後一段範例")]


class TestSearchNestedOrder(unittest.TestCase):
    # spec §4.33.1：較新的場次在前；錄製器的巢狀結構 YYYYMMDD/HHMM 也要成立
    def test_nested_day_time_newest_first(self):
        sb = Sandbox(self)
        names = ["20261016/1500 [Stand-up] 範例專案", "20261017/0900 [Stand-up] 範例專案",
                 "20261017/1400 [Stand-up] 範例專案", "20261015/2300 [Stand-up] 範例專案"]
        for n in names:
            make_session(sb.root, n)
        r = sb.meeting("search", sb.root, "Stand-up")
        self.assertEqual(r.returncode, 0, r.stderr)
        order = []
        for h in parse(self, r.stdout):
            if not order or order[-1] != h["sess"]:
                order.append(h["sess"])
        self.assertEqual(order, ["20261017/1400 [Stand-up] 範例專案", "20261017/0900 [Stand-up] 範例專案",
                                 "20261016/1500 [Stand-up] 範例專案", "20261015/2300 [Stand-up] 範例專案"],
                         "較新的場次在前（以相對路徑排序，不是只看時刻）")


class TestDiarizeQualityFile(unittest.TestCase):
    # meeting-speed spec §4.8.4、§6 第 25 條（使用者 2026-10-22 核准）：缺段落檔、已有 diarization.json 時
    # diarize 不重轉——raw（內容與 mtime）不動、不呼叫轉錄替身、回 1、輸出含「缺 transcript.segments.json」、
    # 舊品質檔不被改動或刪除、不產生 transcript.speakers.md
    def test_quality_replaced_with_segments(self):
        sb = Sandbox(self)
        sess = m.make_audio_session(sb.root)
        rec = sess / "錄音"
        raw = rec / "transcript.raw.md"
        raw.write_text("# 逐字稿（原始，未經任何後處理）\n\n> 來源：範例.wav　語言：zh　模型：範例\n\n原始內容（不得被重寫）\n",
                       encoding="utf-8")
        os.utime(raw, (1_700_000_000, 1_700_000_000))
        raw_before = (raw.read_bytes(), raw.stat().st_mtime_ns)
        stale = [{"start": 99.0, "end": 100.0, "reason": "compression_ratio"}]
        qp = rec / "transcript.quality.json"
        qp.write_text(json.dumps(stale), encoding="utf-8")
        q_before = qp.read_bytes()
        (rec / "diarization.json").write_text(json.dumps(DIAR, ensure_ascii=False), encoding="utf-8")
        env, log = m.fake_asr_env(sb.base, QSEGS)
        r = sb.meeting("diarize", sess, timeout=180, **env)
        out = f"stdout:{r.stdout}\nstderr:{r.stderr}"
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), raw_before,
                         f"transcript.raw.md 的內容與 mtime 應不變\n{out}")
        self.assertEqual(m.read_asr_calls(log), [], f"缺 transcript.segments.json 時不得呼叫轉錄替身\n{out}")
        self.assertEqual(r.returncode, 1, out)
        self.assertIn("缺 transcript.segments.json", r.stdout + r.stderr)
        self.assertTrue(qp.is_file(), "舊的 transcript.quality.json 不得被刪除")
        self.assertEqual(qp.read_bytes(), q_before, "舊的 transcript.quality.json 內容不得被改動")
        self.assertFalse((rec / "transcript.speakers.md").exists(), "缺段落檔時不得產生 transcript.speakers.md")


class TestTranscribeMultiAudioNoVad(unittest.TestCase):
    def assert_no_vad(self, r, calls, raw):
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(calls, "應呼叫轉錄替身")
        self.assertNotIn("--clip-timestamps", calls[0], "多音檔時不得帶 clip")
        self.assertEqual(vad_line(raw.read_text(encoding="utf-8")), "> VAD：未套用（多音檔）")

    # spec §3.18（R3x §6 第 158 條）：錄音/ 第一層有超過 1 個音檔 → 不套 VAD
    def test_two_audio_files_skip_vad(self):
        d = tmpdir(self)
        _sess, rec, wav = vad_session(d)
        m.make_wav(rec / "zz 點評 範例.wav", dur=2.0)
        r, calls = transcribe(d, wav, rec / "transcript.raw.md")
        self.assert_no_vad(r, calls, rec / "transcript.raw.md")

    # spec §3.18（R3x §6 第 158 條）：音檔是 .combined.wav（_combine_audio.py 串接的成品）→ 不套 VAD
    def test_combined_wav_skip_vad(self):
        d = tmpdir(self)
        _sess, rec, wav = vad_session(d)
        combined = rec / ".combined.wav"
        shutil.copyfile(wav, combined)
        r, calls = transcribe(d, combined, rec / "transcript.raw.md")
        self.assert_no_vad(r, calls, rec / "transcript.raw.md")

    # 對照：只有一個音檔（隱藏檔不算）時照常套 VAD
    def test_single_audio_still_clips(self):
        d = tmpdir(self)
        _sess, rec, wav = vad_session(d)
        r, calls = transcribe(d, wav, rec / "transcript.raw.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--clip-timestamps", calls[0])
        self.assertTrue(vad_line((rec / "transcript.raw.md").read_text(encoding="utf-8")).startswith("> VAD：clip "))


if __name__ == "__main__":
    unittest.main()

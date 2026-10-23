"""prep 的可見性：場次路徑含 glob 特殊字元時照常找到音檔與圖檔、有步驟失敗時結尾不印 ✅
（meeting-speed spec §4.8.9、§4.8.10；Story G5）。

場次名一律用「[Stand-up] 範例專案」（tests/record/test_ms_support.py 的 SESSION）。
替身：轉錄 fakes/asr/mlx_whisper、分離 fakes/ms_diarize_venv（沿用 test_ms_prep.PrepCase 的環境）；
OCR 的 ocrmac 替身在測試的 TMPDIR 裡臨時產生（PYTHONPATH 前置），不載入 Apple Vision。素材只在 TMPDIR。
"""
import json
import re

from tests.record import _media as m
from tests.record import test_ms_support as s
from tests.record.test_ms_prep import PrepCase

OK_BANNER = "✅ 本機前處理完成"
WARN_BANNER = "⚠ 本機前處理完成，但有步驟失敗："
STATE_FILE = ".pipeline-state.json"
COMBINE_PY = s.BIN / "_combine_audio.py"
OCR_PY = s.BIN / "_ocr.py"
# spec §4.8.9：glob 特殊字元（[、]、*、?）
GLOB_NAMES = (s.SESSION, "範例*專案?")

FAKE_OCRMAC = '''
class OCR:
    def __init__(self, img, language_preference=None):
        self.img = img

    def recognize(self):
        return [("範例投影片文字", 1.0, (0, 0, 1, 1))]
'''


def bracket_session(root, name=s.SESSION):
    """只有一個 wav 的場次，場次名含方括號（預設「[Stand-up] 範例專案」）。"""
    return s.audio_session(root, name=name)


class TestPrepVisible(PrepCase):
    # spec §4.8.9：場次路徑含 [ ] * ? 時，_combine_audio.py 照常找到 錄音/ 第一層的音檔
    def test_combine_audio_bracket_path(self):
        for name in GLOB_NAMES:
            with self.subTest(name=name):
                rec = self.base / name / "錄音"
                wav = m.make_wav(rec / f"{name} 2026-10-11 21.00.00.wav", dur=1.0)
                r = s.run([s.PY, COMBINE_PY, rec], s.base_env(None), timeout=60)
                self.assertEqual(r.returncode, 0, f"場次路徑含 glob 特殊字元時應找到音檔{s.out_of(r)}")
                self.assertEqual(r.stdout.strip(), str(wav), s.out_of(r))

    # spec §4.8.9：場次路徑含 [ ] * ? 時，_ocr.py 照常找到圖檔（只有副檔名樣式保留萬用字元）
    def test_ocr_bracket_path(self):
        pymod = self.base / "pymod_ocr" / "ocrmac"
        pymod.mkdir(parents=True)
        (pymod / "__init__.py").write_text("", encoding="utf-8")
        (pymod / "ocrmac.py").write_text(FAKE_OCRMAC, encoding="utf-8")
        env = s.base_env(None, PYTHONPATH=pymod.parent)
        for name in GLOB_NAMES:
            with self.subTest(name=name):
                photos = self.base / name / "照片"
                photos.mkdir(parents=True)
                for fn in ("slide-01.jpg", "slide-02.png"):
                    (photos / fn).write_bytes(b"\0" * 16)
                out = photos / ".ocr"
                r = s.run([s.PY, OCR_PY, photos, out], env, timeout=60)
                self.assertEqual(r.returncode, 0, s.out_of(r))
                lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
                self.assertTrue(lines, f"_ocr.py 應印 JSON 摘要{s.out_of(r)}")
                summary = json.loads(lines[-1])
                self.assertEqual(summary.get("count"), 2, f"場次路徑含 glob 特殊字元時應找到 2 張圖{s.out_of(r)}")
                for stem in ("slide-01", "slide-02"):
                    txt = out / f"{stem}.txt"
                    self.assertTrue(txt.is_file(), f"應寫 {txt.name}")
                    self.assertIn("範例投影片文字", txt.read_text(encoding="utf-8"))

    # spec §4.8.9：場次名含 [ ] 時 prep 端到端照常跑完（替身 ASR／diarize），prep 後 transcript.speakers.md 存在
    def test_prep_bracket_session_end_to_end(self):
        sess = bracket_session(self.root)
        wav = s.wavs(sess)[0]
        r = self.prep()
        self.assertEqual(r.returncode, 0, s.out_of(r))
        calls = self.asr_calls()
        self.assertTrue(calls, f"應呼叫轉錄（不得收到空參數）{s.out_of(r)}")
        self.assertTrue(any(a == str(wav) or a.endswith("/" + wav.name) for a in calls[0]),
                        f"音源應是 錄音/ 第一層的 wav：{calls[0]}")
        stages = self.state(sess)["stages"]
        self.assertEqual(stages.get("transcribe", {}).get("status"), "done", stages)
        self.assertEqual(stages.get("diarize", {}).get("status"), "done", f"{stages}{s.out_of(r)}")
        self.assertTrue((sess / "錄音" / "transcript.speakers.md").is_file(),
                        f"prep 後應有 transcript.speakers.md{s.out_of(r)}")

    # spec §4.8.10：轉錄與分離都失敗時，結尾不印 ✅，改印 ⚠＋場次代號＋失敗 stage（以「、」連接），提示 .pipeline-state.json；
    # 結束碼照 §4.8.5 仍回 0
    def test_prep_banner_reports_failure(self):
        sess = bracket_session(self.root)
        name = sess.name
        r = self.prep(FAKE_ASR_EXIT=1, FAKE_DIAR_EXIT=5)
        self.assertEqual(r.returncode, 0, f"結束碼照 §4.8.5 不變（失敗仍回 0）{s.out_of(r)}")
        stages = self.state(sess)["stages"]
        self.assertEqual(stages.get("transcribe", {}).get("status"), "failed", stages)
        self.assertEqual(stages.get("diarize", {}).get("status"), "failed", stages)
        self.assertNotIn(OK_BANNER, r.stdout, f"有步驟失敗時不得印「{OK_BANNER}」{s.out_of(r)}")
        self.assertIn(WARN_BANNER, r.stdout, s.out_of(r))
        tail = r.stdout[r.stdout.index(WARN_BANNER):]
        found = [set(x.strip().split("、")) for x in re.findall(re.escape(name) + r"：([^\n]+)", tail)]
        self.assertIn({"transcribe", "diarize"}, found,
                      f"應有一行「{name}：<失敗 stage 以「、」連接>」{s.out_of(r)}")
        self.assertIn(STATE_FILE, tail, f"應提示看 {STATE_FILE}{s.out_of(r)}")

    # spec §4.8.10：全部成功時照舊印 ✅，不印 ⚠
    def test_prep_banner_ok_when_all_done(self):
        sess = bracket_session(self.root)
        r = self.prep()
        self.assertEqual(r.returncode, 0, s.out_of(r))
        stages = self.state(sess)["stages"]
        self.assertEqual({k: v.get("status") for k, v in stages.items()}, {"transcribe": "done", "diarize": "done"},
                         f"前提：全部成功{s.out_of(r)}")
        self.assertIn(f"{OK_BANNER}（1 場）", r.stdout, s.out_of(r))
        self.assertNotIn(WARN_BANNER, r.stdout, s.out_of(r))


if __name__ == "__main__":
    import unittest

    unittest.main()

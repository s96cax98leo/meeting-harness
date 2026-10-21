"""ASR 失敗看得到、raw 不轉字形、現成段落 JSON 不呼叫引擎（meeting-speed spec §4.6.6、§4.7.1、§4.7.2、§4.7.4；
Story G5、G6、G1）。

轉錄一律用替身（不載入模型）：fakes/asr/mlx_whisper（正常）、fakes/asr_exc0/（例外後回 0、只寫 .txt）。
直接執行 bash bin/transcribe.sh <音檔> <out.md> zh；素材只在 TMPDIR。
"""
import json
import os
import unittest

from tests.record import _media as m
from tests.record import test_ms_support as s

SIMPLIFIED = "这是简体内容"
TRADITIONAL = "這是簡體內容"
FALLBACK_MODEL = "mlx-community/whisper-large-v3-mlx"


class ASRCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)
        self.rec = self.base / "場次" / "錄音"
        self.wav = m.make_wav(self.rec / f"{s.SESSION} 2026-10-21 09.30.00.wav", dur=3.0)
        self.out = self.rec / "transcript.raw.md"
        self.log = self.base / "asr.log.jsonl"

    def transcribe(self, fake_dir, **env):
        over = {"FAKE_ASR_LOG": self.log}
        over.update(env)
        e = s.base_env(None, **over)
        e["PATH"] = f"{fake_dir}:{s.ASR_SLOW_DIR}:{e['PATH']}"  # ms_asr/whisper 擋住真的 openai-whisper
        return s.run(["bash", s.TRANSCRIBE_SH, self.wav, self.out, "zh"], e, timeout=180)

    def calls(self):
        if not self.log.is_file():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x.strip()]

    def models_called(self):
        out = []
        for c in self.calls():
            argv = c["argv"]
            out.append(argv[argv.index("--model") + 1] if "--model" in argv else c.get("engine", "?"))
        return out


class TestMSAsrRobust(ASRCase):
    # spec §4.7.1：引擎回 0 但沒有非空 .json → 判為失敗、走退回鏈；退回的引擎成功時採用它的結果
    def test_exception_exit0_triggers_fallback(self):
        r = self.transcribe(s.ASR_EXC0_DIR, FAKE_EXC0_OK_MODEL="whisper-large-v3")
        models = self.models_called()
        self.assertGreaterEqual(len(models), 2, f"第一個引擎回 0 但沒有 .json 時應退回下一個引擎：{models}{s.out_of(r)}")
        self.assertIn("Breeze", models[0], f"前提：zh 第一個引擎是 Breeze：{models}")
        self.assertEqual(models[1], FALLBACK_MODEL, f"應退回 {FALLBACK_MODEL}：{models}")
        self.assertEqual(r.returncode, 0, s.out_of(r))
        raw = self.out.read_text(encoding="utf-8")
        self.assertIn(f"模型：{FALLBACK_MODEL}", raw, "raw 標頭應記實際採用的退回引擎")
        self.assertNotIn("例外前的殘稿", raw, "失敗引擎的殘稿不得進 raw（應清掉這次輸出）")
        self.assertTrue((self.rec / "transcript.segments.json").is_file(), "退回引擎的段落 JSON 應保留")

        # 全部引擎都例外（mlx 兩個模型與 openai-whisper 都只寫 .txt）→ 照舊回 3、不寫 raw
        self.out.unlink()
        (self.rec / "transcript.segments.json").unlink()
        self.log.unlink()
        r = self.transcribe(s.ASR_EXC0_DIR)
        self.assertEqual(r.returncode, 3, f"全部引擎都失敗時應回 3{s.out_of(r)}")
        self.assertFalse(self.out.exists() and self.out.stat().st_size > 0, "全部失敗時不得寫出 raw")
        self.assertGreaterEqual(len(self.calls()), 3, f"應依序試過退回鏈上的每個引擎：{self.models_called()}")

    # spec §4.7.2：引擎完整輸出寫 $WORKDIR/asr.log；失敗時 stderr 印最後 30 行（不再 | tail -8）
    def test_asr_log_tail_30(self):
        r = self.transcribe(s.ASR_EXC0_DIR, FAKE_EXC0_LINES=50, FAKE_EXC0_EXIT=1)
        self.assertNotEqual(r.returncode, 0, s.out_of(r))
        first = self.models_called()[0] if self.calls() else "Breeze"
        self.assertIn(f"[{first}] 範例輸出行 50", r.stderr, f"stderr 應含失敗引擎輸出的最後一行{s.out_of(r)}")
        self.assertIn(f"[{first}] 範例輸出行 21", r.stderr, "stderr 應含最後 30 行（第 21–50 行）")
        self.assertNotIn(f"[{first}] 範例輸出行 20", r.stderr, "stderr 只印最後 30 行")

    # spec §4.6.6：transcript.raw.md 不轉字形（非 Breeze 引擎也一樣）；正體版另存 transcript.md
    def test_raw_not_converted(self):
        env, _ = m.fake_asr_env(self.base, [(0.0, 2.0, SIMPLIFIED)])
        env["MH_ASR_MODEL"] = "fake/whisper-範例"
        r = self.transcribe(m.FAKE_ASR_DIR, **{k: v for k, v in env.items() if k not in ("PATH", "FAKE_ASR_LOG")})
        self.assertEqual(r.returncode, 0, s.out_of(r))
        raw = self.out.read_text(encoding="utf-8")
        self.assertIn(SIMPLIFIED, raw, "raw 應保留引擎原始輸出（不轉字形，鐵則 1）")
        self.assertNotIn(TRADITIONAL, raw)
        md = self.rec / "transcript.md"
        self.assertTrue(md.is_file(), "transcript.md 不存在時應另存正體版")
        self.assertIn(TRADITIONAL, md.read_text(encoding="utf-8"), "transcript.md 應是正體版")

    # spec §4.6.6：transcript.md 已存在時不覆寫（內容與 mtime 不變）
    def test_transcript_md_not_overwritten(self):
        md = self.rec / "transcript.md"
        md.write_text("# 既有的正體版（人工精修，範例）\n", encoding="utf-8")
        os.utime(md, (1_700_000_000, 1_700_000_000))
        before = (md.read_bytes(), md.stat().st_mtime_ns)
        env, _ = m.fake_asr_env(self.base, [(0.0, 2.0, SIMPLIFIED)])
        env["MH_ASR_MODEL"] = "fake/whisper-範例"
        r = self.transcribe(m.FAKE_ASR_DIR, **{k: v for k, v in env.items() if k not in ("PATH", "FAKE_ASR_LOG")})
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual((md.read_bytes(), md.stat().st_mtime_ns), before, "既有 transcript.md 不得被覆寫")

    # spec §4.6.6：transcript.segments.json 照舊轉字形
    def test_segments_still_converted(self):
        env, _ = m.fake_asr_env(self.base, [(0.0, 2.0, SIMPLIFIED)])
        env["MH_ASR_MODEL"] = "fake/whisper-範例"
        r = self.transcribe(m.FAKE_ASR_DIR, **{k: v for k, v in env.items() if k not in ("PATH", "FAKE_ASR_LOG")})
        self.assertEqual(r.returncode, 0, s.out_of(r))
        segs = json.loads((self.rec / "transcript.segments.json").read_text(encoding="utf-8"))
        texts = "".join(x.get("text", "") for x in segs.get("segments", []))
        self.assertIn(TRADITIONAL, texts, "transcript.segments.json 應照舊轉成正體（需要 opencc）")

    # spec §4.7.4：MH_ASR_SEGMENTS_JSON 指向存在的 JSON 時不呼叫任何 ASR 引擎，其餘產出走同一套程式
    def test_segments_json_input_skips_asr(self):
        seg_json = self.base / "stitched.json"
        seg_json.write_text(json.dumps({
            "text": "範例增量第一窗範例增量第二窗", "language": "zh",
            "segments": [{"id": 0, "start": 0.0, "end": 1.5, "text": "範例增量第一窗"},
                         {"id": 1, "start": 1.5, "end": 3.0, "text": "範例增量第二窗"}]}, ensure_ascii=False),
            encoding="utf-8")
        r = self.transcribe(m.FAKE_ASR_DIR, MH_ASR_SEGMENTS_JSON=seg_json)
        self.assertEqual(self.calls(), [], f"給了 MH_ASR_SEGMENTS_JSON 就不得呼叫 ASR 引擎{s.out_of(r)}")
        self.assertEqual(r.returncode, 0, s.out_of(r))
        raw = self.out.read_text(encoding="utf-8")
        self.assertTrue(raw.startswith("# 逐字稿（原始，未經任何後處理）"), "raw 標頭應與整檔轉錄相同")
        self.assertIn("> 來源：", raw)
        self.assertIn("範例增量第一窗", raw)
        self.assertIn("範例增量第二窗", raw)
        segs = json.loads((self.rec / "transcript.segments.json").read_text(encoding="utf-8"))
        self.assertEqual([x["text"] for x in segs["segments"]], ["範例增量第一窗", "範例增量第二窗"])
        self.assertTrue((self.rec / "transcript.quality.json").is_file(), "品質檔應照常產出")


if __name__ == "__main__":
    unittest.main()

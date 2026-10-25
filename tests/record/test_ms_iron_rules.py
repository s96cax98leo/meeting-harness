"""五條鐵則：embedding 不落場次資料夾、人工確認不被覆蓋、套名判準一致、聲紋只寫 vault/（meeting-speed spec §4.6、
§4.8.8、§6 第 14、15、18、19 條；Story G6、G1）。

替身：分離用 fakes/ms_diarize_venv（MH_DIARIZE_VENV；不載入 pyannote）、diarize.sh 的裸 ffmpeg 用 fakes/ms_bin/ffmpeg
（PATH 最前面，記錄後交給真的 ffmpeg）、重算向量用 fakes/ms_embed_speaker.py（MH_EMBED_SPEAKER_CMD）。
聲紋庫一律用暫存的 --harness <根>（不讀 repo 的 vault/）。素材只在 TMPDIR；講者名一律「範例甲／乙／丙／丁」。
"""
import ast
import json
import os
import unittest

from tests.record import _media as m
from tests.record import test_ms_support as s
from tests.record.test_r3_vtt_raw import (MERGE_PY, RENDER_PY, WSEGS, run_py, speakers_md_names, vtt_cues,
                                          write_speaker_fixture)

REPO = s.REPO
FIRST = WSEGS[0][2]


def write_prints(harness, prints):
    d = harness / "vault" / "voiceprints"
    d.mkdir(parents=True, exist_ok=True)
    for name, vec in prints.items():
        (d / f"{name}.json").write_text(json.dumps({"name": name, "vector": vec, "dim": len(vec), "samples": 1,
                                                    "sources": ["範例來源場次"], "created": "2026-10-01",
                                                    "updated": "2026-10-01"}, ensure_ascii=False), encoding="utf-8")
    return d


class IronCase(unittest.TestCase):
    def setUp(self):
        self.base = s.tmpdir(self)

    def diarize(self, sess, **env):
        over, log = s.fake_diarize_env(self.base)
        over.update(env)
        r = s.run(["bash", s.DIARIZE_SH, sess], s.base_env(None, **over), timeout=180)
        return r, log

    def voiceprint(self, *args, **env):
        return s.run([s.PY, s.VOICEPRINT_PY, *args], s.base_env(None, **env), timeout=60)

    def match_fixture(self, existing):
        """場次＋暫存聲紋庫＋暫存 embedding 檔：SPEAKER_00 ≈ 範例乙、SPEAKER_01 ≈ 範例丙（cos > 0.99）。"""
        sess = self.base / "場次"
        rec = sess / "錄音"
        rec.mkdir(parents=True)
        if existing is not None:
            (rec / "speakers.map.json").write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
        harness = self.base / "harness"
        write_prints(harness, {"範例乙": [1.0, 0.0, 0.0], "範例丙": [0.0, 1.0, 0.0]})
        emb = self.base / "emb-暫存.json"
        emb.write_text(json.dumps({"model": "fake", "dim": 3, "speakers": {"SPEAKER_00": [1.0, 0.0, 0.01],
                                                                        "SPEAKER_01": [0.0, 1.0, 0.01]}}),
                       encoding="utf-8")
        return sess, harness, emb

    def run_match(self, existing):
        sess, harness, emb = self.match_fixture(existing)
        r = self.voiceprint("match", sess, "--embeddings", emb, "--harness", harness)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        mp = sess / "錄音" / "speakers.map.json"
        self.assertTrue(mp.is_file(), f"比對後應有 speakers.map.json{s.out_of(r)}")
        return json.loads(mp.read_text(encoding="utf-8")), r

    def assert_matched_other(self, got, r):
        e = got.get("SPEAKER_01")
        self.assertIsInstance(e, dict, f"--embeddings 給的向量應被拿來比對（SPEAKER_01 應命中範例丙）：{got}{s.out_of(r)}")
        self.assertEqual(e.get("name"), "範例丙")
        self.assertIs(e.get("apply"), True)


class TestMSIronRules(IronCase):
    # spec §4.6.1：diarize.sh 跑完，場次資料夾內不得出現 embeddings.json
    def test_no_embeddings_in_session(self):
        sess = s.audio_session(self.base / "根")
        r, log = self.diarize(sess)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertTrue((sess / "錄音" / "diarization.json").is_file(), "應寫出 diarization.json")
        found = [str(p.relative_to(sess)) for p in sess.rglob("embeddings.json")]
        self.assertEqual(found, [], "場次資料夾內不得出現 embeddings.json")
        calls = s.diar_calls(log)
        self.assertEqual(len(calls), 1, calls)
        emb = calls[0]["embeddingsOut"]
        self.assertTrue(emb, "應以 MH_EMBEDDINGS_OUT 指定暫存檔讓分離輸出向量")
        self.assertFalse(os.path.realpath(emb).startswith(os.path.realpath(sess) + os.sep),
                         f"embedding 暫存檔不得在場次資料夾內：{emb}")

    # spec §4.6.1：embedding 只存在 mktemp 的暫存檔，聲紋比對結束（含失敗）時刪除
    def test_embeddings_temp_removed(self):
        for label, extra, want_rc in (("成功", {}, 0), ("分離失敗", {"FAKE_DIAR_EXIT": "5"}, 5)):
            with self.subTest(case=label):
                sess = s.audio_session(self.base / label)
                r, log = self.diarize(sess, FAKE_DIAR_LOG=self.base / f"{label}.log", **extra)
                self.assertEqual(r.returncode, want_rc, s.out_of(r))
                calls = s.diar_calls(self.base / f"{label}.log")
                self.assertEqual(len(calls), 1, calls)
                emb = calls[0]["embeddingsOut"]
                self.assertTrue(emb, "應設 MH_EMBEDDINGS_OUT（mktemp 的暫存檔）")
                self.assertFalse(os.path.exists(emb), f"diarize.sh 結束後 embedding 暫存檔應已刪除：{emb}")
                self.assertEqual(list(sess.rglob("embeddings.json")), [])

    # spec §4.6.2、§6 第 15 條：沒有 confidence 的 dict 視為未確認、不套名（_merge_speakers.py 與 _render.py 各驗）
    def test_confidence_missing_not_applied(self):
        cases = (("沒有 confidence", {"SPEAKER_00": {"name": "範例甲"}}, False),
                 ("evidence 但沒有 confidence", {"SPEAKER_00": {"name": "範例甲", "evidence": "範例線索"}}, False),
                 ("confidence 0.8、沒有 apply", {"SPEAKER_00": {"name": "範例甲", "confidence": 0.8}}, True),
                 ("字串值", {"SPEAKER_00": "範例甲"}, True))
        for label, name_map, applied in cases:
            with self.subTest(case=label):
                sess = self.base / label / "場次"
                rec = write_speaker_fixture(sess, name_map)
                r = run_py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json",
                            rec / "transcript.speakers.md", rec / "speakers.map.json"])
                self.assertEqual(r.returncode, 0, r.stderr)
                md = speakers_md_names((rec / "transcript.speakers.md").read_text(encoding="utf-8"))
                r = run_py([RENDER_PY, sess, "--vtt"])
                self.assertEqual(r.returncode, 0, r.stderr)
                cues = vtt_cues((rec / "transcript.vtt").read_text(encoding="utf-8"))
                if applied:
                    self.assertEqual(md[FIRST], "範例甲", "_merge_speakers.py 應套名")
                    self.assertEqual(cues[FIRST], "範例甲", "_render.py 應套名")
                else:
                    self.assertEqual(md[FIRST], "SPEAKER_00", "_merge_speakers.py：沒有 confidence 的 dict 不得套名")
                    self.assertIsNone(cues[FIRST], "_render.py：沒有 confidence 的 dict 不得套名")

    # spec §4.6.3：既有值是非空字串時 match 不得覆蓋
    def test_string_mapping_kept(self):
        got, r = self.run_match({"SPEAKER_00": "範例甲"})
        self.assertEqual(got.get("SPEAKER_00"), "範例甲", "人工填的字串對應不得被聲紋比對覆蓋")
        self.assert_matched_other(got, r)

    # spec §4.6.3：evidence 不以「聲紋庫比對」開頭的 dict（人工／agent 填的）不得被覆蓋，即使新結果信心更高
    def test_manual_dict_kept(self):
        manual = {"name": "範例甲", "confidence": 0.5, "evidence": "人工確認（範例）"}
        got, r = self.run_match({"SPEAKER_00": manual})
        self.assertEqual(got.get("SPEAKER_00"), manual, "人工確認的 dict 不得被覆蓋")
        self.assert_matched_other(got, r)

    # spec §4.6.3：上一次聲紋比對寫的 dict 可被信心更高的新結果取代
    def test_voiceprint_dict_replaced_by_higher(self):
        old = {"name": "範例丁", "confidence": 0.65, "apply": False,
               "evidence": "聲紋庫比對（cos 0.65，聲紋建於 範例來源場次）——信心不足，僅供人工/agent 參考，未套用"}
        got, r = self.run_match({"SPEAKER_00": old})
        e = got.get("SPEAKER_00")
        self.assertIsInstance(e, dict, got)
        self.assertEqual(e.get("name"), "範例乙", f"聲紋比對寫的舊 dict 應被信心更高的結果取代：{got}")
        self.assertGreater(float(e.get("confidence", 0)), 0.65)
        self.assertTrue(str(e.get("evidence", "")).startswith("聲紋庫比對"))

    # spec §4.6.4：add 沒有 --embeddings、舊場次也沒有 embeddings.json → 經 --embed-speaker 重算到暫存檔，建檔後刪除；
    # diarize venv 不在時回 2 並提示 setup-diarize.sh
    def test_add_recompute_temp_removed(self):
        sess = s.audio_session(self.base / "根")
        (sess / "錄音" / "diarization.json").write_text(json.dumps(
            {"segments": [{"start": 0.0, "end": 4.0, "speaker": "SPEAKER_00"}]}), encoding="utf-8")
        harness = self.base / "harness"
        harness.mkdir()
        elog = self.base / "embed.log"
        r = self.voiceprint("add", sess, "SPEAKER_00", "範例甲", "--harness", harness,
                            MH_EMBED_SPEAKER_CMD=s.EMBED_SPEAKER, FAKE_EMBED_LOG=elog,
                            FAKE_EMBED_VECTOR="[0.0, 0.6, 0.8]", MH_DIARIZE_VENV=s.FAKE_VENV)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        vp = harness / "vault" / "voiceprints" / "範例甲.json"
        self.assertTrue(vp.is_file(), "聲紋應寫進 <harness>/vault/voiceprints/")
        self.assertEqual(json.loads(vp.read_text(encoding="utf-8"))["vector"], [0.0, 0.6, 0.8])
        calls = [json.loads(x) for x in elog.read_text(encoding="utf-8").splitlines()] if elog.is_file() else []
        self.assertEqual(len(calls), 1, f"應呼叫一次重算向量的指令：{calls}")
        out = calls[0]["out"]
        self.assertFalse(os.path.exists(out), f"重算的向量暫存檔應在建檔後刪除：{out}")
        self.assertFalse(os.path.realpath(out).startswith(os.path.realpath(sess) + os.sep), "暫存檔不得在場次資料夾內")
        self.assertEqual(list(sess.rglob("embeddings.json")), [], "場次資料夾內不得出現 embeddings.json")

        with self.subTest(case="diarize venv 不在"):
            r = self.voiceprint("add", sess, "SPEAKER_00", "範例乙", "--harness", harness,
                                MH_DIARIZE_VENV=self.base / "沒有這個-venv")
            self.assertEqual(r.returncode, 2, s.out_of(r))
            self.assertIn("setup-diarize.sh", r.stderr)
            self.assertFalse((harness / "vault" / "voiceprints" / "範例乙.json").exists())

    # spec §4.6.4：舊場次有 錄音/embeddings.json 時只讀它（不重算、不改它）
    def test_add_reads_legacy_embeddings(self):
        sess = s.audio_session(self.base / "根")
        legacy = sess / "錄音" / "embeddings.json"
        legacy.write_text(json.dumps({"model": "fake", "dim": 3, "speakers": {"SPEAKER_00": [0.6, 0.8, 0.0]}}),
                          encoding="utf-8")
        os.utime(legacy, (1_700_000_000, 1_700_000_000))
        before = (legacy.read_bytes(), legacy.stat().st_mtime_ns)
        harness = self.base / "harness"
        harness.mkdir()
        elog = self.base / "embed.log"
        r = self.voiceprint("add", sess, "SPEAKER_00", "範例甲", "--harness", harness,
                            MH_EMBED_SPEAKER_CMD=s.EMBED_SPEAKER, FAKE_EMBED_LOG=elog, MH_DIARIZE_VENV=s.FAKE_VENV)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertFalse(elog.exists(), "有舊 embeddings.json 時不得重算")
        vp = harness / "vault" / "voiceprints" / "範例甲.json"
        self.assertEqual(json.loads(vp.read_text(encoding="utf-8"))["vector"], [0.6, 0.8, 0.0])
        self.assertEqual((legacy.read_bytes(), legacy.stat().st_mtime_ns), before, "舊 embeddings.json 只讀")

    # spec §4.6.5：remove 拒絕含路徑分隔、.. 或不在 vault/voiceprints/ 內的名稱，回 2
    def test_remove_rejects_path(self):
        harness = self.base / "harness"
        for name in ("../範例外部", "..", "範例/甲", "../voiceprints/範例甲", "./範例甲"):
            with self.subTest(name=name):
                d = write_prints(harness, {"範例甲": [1.0, 0.0, 0.0]})
                outside = harness / "vault" / "範例外部.json"
                outside.write_text("{}", encoding="utf-8")
                r = self.voiceprint("remove", name, "--harness", harness)
                self.assertEqual(r.returncode, 2, s.out_of(r))
                self.assertTrue(outside.is_file(), "vault/voiceprints/ 以外的檔不得被刪")
                self.assertTrue((d / "範例甲.json").is_file(), "被拒絕的名稱不得刪到聲紋檔")
        d = write_prints(harness, {"範例甲": [1.0, 0.0, 0.0]})
        r = self.voiceprint("remove", "範例甲", "--harness", harness)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertFalse((d / "範例甲.json").exists())

    # spec §4.6.8：.gitignore 含 embeddings.json、speakers.map.json、transcript.quality.json、.pipeline-state.lock
    def test_gitignore_entries(self):
        lines = {ln.strip() for ln in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
        for entry in ("embeddings.json", "speakers.map.json", "transcript.quality.json", ".pipeline-state.lock"):
            self.assertIn(entry, lines, f".gitignore 應有一行 {entry}")

    # spec §4.6.9：_diarize_pyannote.py 在寫 diarization.json 之前設定 meta["embeddings"]（AST）
    def test_meta_embeddings_before_dump(self):
        tree = ast.parse(s.PYANNOTE_PY.read_text(encoding="utf-8"))
        main = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"), None)
        self.assertIsNotNone(main, "_diarize_pyannote.py 應有 main()")
        set_lines, dump_lines = [], []
        for n in ast.walk(main):
            if isinstance(n, ast.Assign):
                for t in n.targets:
                    if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) and t.value.id == "meta"
                            and isinstance(t.slice, ast.Constant) and t.slice.value == "embeddings"):
                        set_lines.append(n.lineno)
                    if (isinstance(t, ast.Name) and t.id == "meta" and isinstance(n.value, ast.Dict)
                            and any(isinstance(k, ast.Constant) and k.value == "embeddings" for k in n.value.keys)):
                        set_lines.append(n.lineno)
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "dump" and n.args
                    and isinstance(n.args[0], ast.Dict)
                    and any(isinstance(k, ast.Constant) and k.value == "segments" for k in n.args[0].keys)):
                dump_lines.append(n.lineno)
        self.assertTrue(dump_lines, "找不到寫 diarization.json（含 segments 鍵）的 json.dump")
        self.assertTrue(set_lines, "main() 應設定 meta[\"embeddings\"]")
        self.assertLess(min(set_lines), min(dump_lines), "meta[\"embeddings\"] 應在寫 diarization.json 之前設定")

    # spec §4.6.10：config.json 有 transcribe.incremental.enabled: true；diarize.note 不再寫 embeddings.json
    def test_config_keys(self):
        cfg = json.loads((REPO / "config.json").read_text(encoding="utf-8"))
        self.assertIs(((cfg.get("transcribe") or {}).get("incremental") or {}).get("enabled"), True,
                      "config.json 應有 transcribe.incremental.enabled: true")
        note = str((cfg.get("diarize") or {}).get("note", ""))
        self.assertNotIn("embeddings.json", note, "diarize.note 不得再寫 embeddings.json")

    # spec §4.8.8、§6 第 14、19 條：輸入已是 16 kHz 單聲道 wav 時 diarize.sh 跳過轉檔；其他格式照轉
    def test_diarize_skips_16k_conversion(self):
        for label, rate, ch, want_convert in (("16k 單聲道", 16000, 1, False), ("48k 雙聲道", 48000, 2, True)):
            with self.subTest(case=label):
                root = self.base / label
                sess = root / m.DAY / m.SESSION_NAME
                rec = sess / "錄音"
                rec.mkdir(parents=True)
                (rec / "meeting.json").write_text(json.dumps(m.MEETING_JSON, ensure_ascii=False), encoding="utf-8")
                wav = rec / f"{m.SESSION_NAME} 2026-10-21 09.30.00.wav"
                m.ff("-f", "lavfi", "-i", f"sine=f=440:sample_rate={rate}:d=3", "-ac", ch, "-c:a", "pcm_s16le",
                     "-f", "wav", wav)
                flog = self.base / f"{label}-ffmpeg.log"
                env = {"MS_FFMPEG_LOG": flog}
                over, dlog = s.fake_diarize_env(self.base, FAKE_DIAR_LOG=self.base / f"{label}-diar.log")
                env.update(over)
                e = s.base_env(None, **env)
                e["PATH"] = f"{s.FAKE_FFMPEG_BIN}:{e['PATH']}"
                r = s.run(["bash", s.DIARIZE_SH, sess], e, timeout=180)
                self.assertEqual(r.returncode, 0, s.out_of(r))
                conv = [a for a in s.argv_log(flog) if any(os.path.basename(x) == wav.name for x in a)]
                if want_convert:
                    self.assertTrue(conv, f"{label}：應轉成 16k 單聲道")
                else:
                    self.assertEqual(conv, [], f"{label}：已是 16 kHz 單聲道 wav，不得再呼叫 ffmpeg 轉檔")
                    calls = s.diar_calls(self.base / f"{label}-diar.log")
                    self.assertEqual(len(calls), 1, calls)

    # spec §6 第 18 條的等價守門：diarize.sh、_merge_speakers.py 的結束碼集合、參數形式與輸出檔名不變
    def test_diarize_merge_interface_kept(self):
        with self.subTest(case="diarization.json 已存在 → 0、SKIP"):
            sess = s.audio_session(self.base / "a")
            (sess / "錄音" / "diarization.json").write_text('{"segments": []}', encoding="utf-8")
            r, _ = self.diarize(sess)
            self.assertEqual(r.returncode, 0, s.out_of(r))
            self.assertIn("SKIP", r.stdout)
        with self.subTest(case="venv 不在 → 2"):
            sess = s.audio_session(self.base / "b")
            r, _ = self.diarize(sess, MH_DIARIZE_VENV=self.base / "沒有這個-venv")
            self.assertEqual(r.returncode, 2, s.out_of(r))
        with self.subTest(case="沒有音檔 → 3"):
            sess = self.base / "c" / "場次"
            (sess / "錄音").mkdir(parents=True)
            r, _ = self.diarize(sess)
            self.assertEqual(r.returncode, 3, s.out_of(r))
        with self.subTest(case="分離失敗 → 5"):
            sess = s.audio_session(self.base / "d")
            r, _ = self.diarize(sess, FAKE_DIAR_EXIT="4")
            self.assertEqual(r.returncode, 5, s.out_of(r))
        with self.subTest(case="成功 → 0、錄音/diarization.json"):
            sess = s.audio_session(self.base / "e")
            r, _ = self.diarize(sess)
            self.assertEqual(r.returncode, 0, s.out_of(r))
            self.assertTrue((sess / "錄音" / "diarization.json").is_file())
        with self.subTest(case="_merge_speakers.py 參數不足 → 2"):
            r = run_py([MERGE_PY, "a.json", "b.json"])
            self.assertEqual(r.returncode, 2, r.stderr)
        with self.subTest(case="_merge_speakers.py 四個參數 → 寫 <out.md>"):
            sess = self.base / "f" / "場次"
            rec = write_speaker_fixture(sess, {"SPEAKER_01": "範例乙"})
            out = rec / "範例輸出.speakers.md"
            r = run_py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json", out,
                        rec / "speakers.map.json"])
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(out.is_file())
        with self.subTest(case="_merge_speakers.py 沒有逐字段 → 3"):
            sess = self.base / "g" / "場次"
            rec = write_speaker_fixture(sess, None)
            (rec / "transcript.segments.json").write_text('{"segments": []}', encoding="utf-8")
            r = run_py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json", rec / "x.md"])
            self.assertEqual(r.returncode, 3, r.stderr)


if __name__ == "__main__":
    unittest.main()

"""sdlc-deliver 審查的兩個增量轉錄 bug（meeting-speed；Story G2、G4）。

1. 語言：worker 與 stitch 的 params.language 要與 meeting.sh 實際交給 transcribe.sh 的語言一致——
   環境變數 MH_LANG 優先，否則讀場次 錄音/meeting.json 的 language（同 bin/_profile.py），都沒有才是 zh；
   meeting.sh 的 transcribe_session 呼叫 stitch 時明確帶上 MH_LANG。
2. 捨棄錄製：錄音/ 已被移走（tracks 不在）或本場 record.status.json 的 discarded 為真時，worker 直接結束、回 0，
   不在原處重建任何目錄、不寫 state.json。

素材只在 TMPDIR；模型一律用 fakes/pymod/mlx_whisper；場次名用範例名稱。
"""
import json
import os
import subprocess
import unittest

from tests.record import test_ms_support as s
from tests.record.test_ms_incremental_asr import WorkerCase


class LangCase(WorkerCase):
    def env(self, **extra):
        e = super().env(**extra)
        if "MH_LANG" not in extra:
            e.pop("MH_LANG", None)
        return e

    def set_language(self, sess, lang):
        p = sess / "錄音" / "meeting.json"
        meta = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
        meta["language"] = lang
        p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


class TestLanguageFromMeetingJson(LangCase):
    # worker 結果以 zh 參數產出、meeting.json 改成 en → stitch 必須回 3（不得把 zh 結果當 en 用）
    def test_stitch_rejects_language_mismatch(self):
        sess = self.completed(2)
        self.assertEqual(self.state(sess)["params"]["language"], "zh", "前提：沒有 meeting.json 語言時 worker 用 zh")
        self.set_language(sess, "en")
        out = self.base / "stitched.json"
        r = self.stitch(sess, out)
        self.assertEqual(r.returncode, 3, f"meeting.json language=en、worker 以 zh 產出時 stitch 應回 3{s.out_of(r)}")
        self.assertFalse(out.exists(), "不可用時不得寫出結果")

    # 語言相同（meeting.json 也是 zh）→ stitch 回 0
    def test_stitch_ok_when_language_same(self):
        sess = self.completed(2)
        self.set_language(sess, "zh")
        r = self.stitch(sess, self.base / "stitched.json")
        self.assertEqual(r.returncode, 0, s.out_of(r))

    # worker 也讀 meeting.json 的 language：en 場次的 params 是 en＋非 zh 模型，stitch 回 0
    def test_worker_reads_meeting_json_language(self):
        sess = self.session(2)
        self.set_language(sess, "en")
        self.status(sess, "done")
        self.run_worker(sess)
        p = (self.state(sess) or {}).get("params") or {}
        self.assertEqual(p.get("language"), "en", f"worker 應讀 meeting.json 的 language：{p}")
        self.assertNotIn("Breeze", p.get("model", ""), f"en 場次不得用 zh 的 Breeze 模型：{p}")
        self.write_audio_ready(sess)
        r = self.stitch(sess, self.base / "stitched.json")
        self.assertEqual(r.returncode, 0, s.out_of(r))

    # 環境變數 MH_LANG 有值時優先於 meeting.json
    def test_env_lang_overrides_meeting_json(self):
        sess = self.session(2)
        self.set_language(sess, "en")
        self.status(sess, "done")
        r = s.run([s.PY, s.ASR_WORKER_PY, "run", sess], self.env(MH_LANG="zh"), timeout=120)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertEqual(self.state(sess)["params"]["language"], "zh", "MH_LANG 應優先於 meeting.json")


class TestMeetingShPassesLang(unittest.TestCase):
    # meeting.sh 的 MH_LANG 是 eval 設的（沒 export）；transcribe_session 呼叫 stitch 時必須明確帶上
    def test_transcribe_session_passes_lang_to_stitch(self):
        base = s.tmpdir(self)
        fake_bin = base / "bin"
        (fake_bin / "lib").mkdir(parents=True)
        seen = base / "stitch-lang.txt"
        (fake_bin / "lib" / "_asr_worker.py").write_text(
            "import os, sys\n"
            f"open({str(seen)!r}, 'w', encoding='utf-8').write(os.environ.get('MH_LANG', '<未設>'))\n"
            "sys.exit(3)\n", encoding="utf-8")
        (fake_bin / "transcribe.sh").write_text("exit 0\n", encoding="utf-8")
        sess = base / "場次"
        (sess / "錄音").mkdir(parents=True)
        script = (
            'eval "$(sed -n \'/^transcribe_session() {/,/^}/p\' "$1")"\n'
            'BIN="$2"\n'
            "MH_LANG=en\n"  # 與 load_profile 的 eval 相同：shell 變數、沒有 export
            'transcribe_session "$3" "$3/錄音/a.wav" 0\n')
        env = s.base_env(None)
        env.pop("MH_LANG", None)
        r = s.run(["bash", "-c", script, "bash", s.MEETING_SH, fake_bin, sess], env, timeout=60)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        self.assertTrue(seen.is_file(), f"應呼叫 stitch{s.out_of(r)}")
        self.assertEqual(seen.read_text(encoding="utf-8"), "en", "stitch 應拿到 meeting.sh 實際使用的語言")


if __name__ == "__main__":
    unittest.main()

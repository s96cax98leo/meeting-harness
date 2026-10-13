"""transcribe.sh 的 VAD clip、raw 標頭 VAD 行、段落檔一律輸出、transcript.quality.json（spec §4.30.1–§4.30.5、§4.45.3）。

轉錄一律用 fakes/asr/mlx_whisper 替身（記下收到的參數，不載入模型）；素材只在 TMPDIR。
clip_timestamps 的傳法：mlx_whisper CLI 的 --clip-timestamps（逗號分隔的 start,end,…，成品秒數）；本檔只取其中的數字兩兩成對比對。
"""
import json
import os
import re
import subprocess
import unittest

from tests.record import _fixtures as fx
from tests.record import _media as m
from tests.record._helpers import BIN, tmpdir
from tests.record.surface import REPO

TRANSCRIBE_SH = BIN / "transcribe.sh"
TRANSCRIBE_SKILL = REPO / ".claude" / "skills" / "meeting-transcribe" / "SKILL.md"
TOL = 0.0005


def levels_fixture(n=80, *, silent=False):
    """錄製時鐘 0–40 秒（每窗 0.5 秒），5–10 秒與 25–30 秒有聲（兩路交錯），其餘 ≤ -60 dBFS。"""
    sysl, mic = [], []
    for k in range(n):
        t = k * 0.5
        loud = not silent and (5.0 <= t < 10.0 or 25.0 <= t < 30.0)
        sysl.append(-20.0 if loud and k % 2 else -75.0)
        mic.append(-25.0 if loud and not k % 2 else -80.0)
    return sysl, mic


def session(base, *, levels=True, silent=False):
    sess = m.make_audio_session(base, dur=40.0)
    rec = sess / "錄音"
    if levels:
        s, mc = levels_fixture(silent=silent)
        fx.write_tracks_json(rec, [(0.0, 40.0)], system=s, mic=mc)
    wav = next(rec.glob("*.wav"))
    return sess, rec, wav


def transcribe(base, wav, out, segments=None, **env_over):
    env, log = m.fake_asr_env(base, segments, **env_over)
    e = dict(os.environ)
    for k in ("MH_VAD", "MH_VAD_THRESHOLD_DB", "MH_VAD_PAD", "MH_VAD_MERGE_GAP", "MH_EMIT_SEGMENTS"):
        e.pop(k, None)
    e.update(env)
    r = subprocess.run(["bash", str(TRANSCRIBE_SH), str(wav), str(out), "zh"], capture_output=True, text=True,
                       env=e, timeout=120)
    return r, m.read_asr_calls(log)


def vad_line(raw_text):
    lines = raw_text.splitlines()
    i = next((k for k, ln in enumerate(lines) if ln.startswith("> 來源：")), None)
    if i is None or i + 1 >= len(lines):
        return None
    return lines[i + 1]


def clip_arg(argv):
    if "--clip-timestamps" not in argv:
        return None
    v = argv[argv.index("--clip-timestamps") + 1]
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", v)]
    return [nums[i:i + 2] for i in range(0, len(nums), 2)]


def segments_file(rec):
    for name in ("transcript.segments.json", "segments.json"):
        if (rec / name).is_file():
            return rec / name
    return None


class TestR3TranscriptVad(unittest.TestCase):
    def assert_vad_clip(self, line, n, thr, pad, gap):
        self.assertIsNotNone(line, "raw 標頭應有 VAD 行（「> 來源：」的下一行）")
        mm = re.fullmatch(r"> VAD：clip (\d+) 段，門檻 (-?\d+(?:\.\d+)?) dBFS，補 (\d+(?:\.\d+)?) 秒，合併間隔 (\d+(?:\.\d+)?) 秒",
                          line)
        self.assertIsNotNone(mm, f"VAD 行格式不符：{line!r}")
        self.assertEqual(int(mm.group(1)), n)
        self.assertAlmostEqual(float(mm.group(2)), thr)
        self.assertAlmostEqual(float(mm.group(3)), pad)
        self.assertAlmostEqual(float(mm.group(4)), gap)

    def assert_clips(self, got, want):
        self.assertIsNotNone(got, "應以 --clip-timestamps 把 clip 交給 ASR")
        self.assertEqual(len(got), len(want), f"{got} vs {want}")
        for g, w in zip(got, want):
            self.assertAlmostEqual(g[0], w[0], delta=TOL)
            self.assertAlmostEqual(g[1], w[1], delta=TOL)

    # spec §4.30.1：有 levels → clip 交給 ASR；標頭「> VAD：clip 2 段，門檻 -60 dBFS，補 0.75 秒，合併間隔 2.0 秒」
    def test_clip_passed_to_asr(self):
        d = tmpdir(self)
        sess, rec, wav = session(d)
        r, calls = transcribe(d, wav, rec / "transcript.raw.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(calls)
        self.assert_clips(clip_arg(calls[0]), [[4.25, 10.75], [24.25, 30.75]])
        line = vad_line((rec / "transcript.raw.md").read_text(encoding="utf-8"))
        self.assertEqual(line, "> VAD：clip 2 段，門檻 -60 dBFS，補 0.75 秒，合併間隔 2.0 秒")

    # spec §4.30.2：沒有 levels／全部無聲／MH_VAD=0 → 不帶 clip，標頭寫原因
    def test_fallback_without_levels(self):
        cases = (("沒有 levels", dict(levels=False), {}),
                 ("沒有有聲區間", dict(silent=True), {}),
                 ("MH_VAD=0", {}, {"MH_VAD": "0"}))
        argvs = []
        for reason, kw, env in cases:
            with self.subTest(reason=reason):
                d = tmpdir(self)
                sess, rec, wav = session(d, **kw)
                r, calls = transcribe(d, wav, rec / "transcript.raw.md", **env)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertTrue(calls)
                self.assertNotIn("--clip-timestamps", calls[0], "退回整檔時不得帶 clip")
                argvs.append([a for a in calls[0] if not a.startswith("/")])
                line = vad_line((rec / "transcript.raw.md").read_text(encoding="utf-8"))
                self.assertEqual(line, f"> VAD：未套用（{reason}）")
        if len(argvs) == 3:
            self.assertTrue(argvs[0] == argvs[1] == argvs[2], "三種退回情形送 ASR 的參數應相同（與 R2 相同、只差路徑）")

    # spec §4.30.3：MH_VAD_THRESHOLD_DB／MH_VAD_PAD／MH_VAD_MERGE_GAP 覆寫並反映在標頭
    def test_vad_env_overrides(self):
        d = tmpdir(self)
        sess, rec, wav = session(d)
        r, calls = transcribe(d, wav, rec / "transcript.raw.md", MH_VAD_THRESHOLD_DB="-50", MH_VAD_PAD="0.5",
                              MH_VAD_MERGE_GAP="1.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(calls)
        self.assert_clips(clip_arg(calls[0]), [[4.5, 10.5], [24.5, 30.5]])
        self.assert_vad_clip(vad_line((rec / "transcript.raw.md").read_text(encoding="utf-8")), 2, -50, 0.5, 1.0)

    # spec §4.30.4：沒設 MH_EMIT_SEGMENTS 也輸出段落檔
    def test_segments_always_written(self):
        d = tmpdir(self)
        sess, rec, wav = session(d, levels=False)
        r, _ = transcribe(d, wav, rec / "transcript.raw.md", [(0.0, 2.0, "範例內容一"), (2.0, 4.0, "範例內容二")])
        self.assertEqual(r.returncode, 0, r.stderr)
        p = segments_file(rec)
        self.assertIsNotNone(p, "沒設 MH_EMIT_SEGMENTS 也應輸出段落檔")
        segs = json.loads(p.read_text(encoding="utf-8")).get("segments")
        self.assertEqual([s["text"].strip() for s in segs], ["範例內容一", "範例內容二"])

    # spec §4.30.5、§3.18：transcript.quality.json（no_speech_loop、compression_ratio、repeat_run×4），其餘段落不列；沒問題 → []
    def test_quality_file(self):
        loop = (10.0, 14.0, "好的好的好的好的")
        ratio = (20.0, 30.0, "我們先看範例專案的進度，接著確認測試環境，最後整理交辦事項。" * 4)
        run = [(40.0 + 2 * i, 41.5 + 2 * i, "謝謝大家") for i in range(4)]
        clean = [(0.0, 5.0, "今天先確認範例專案的時程。"), (5.0, 9.5, "測試環境下週一可以用。"),
                 (31.0, 38.0, "交辦事項會後再寄給大家。"), (50.0, 55.0, "那今天就先到這裡。")]
        segs = sorted([loop, ratio, *run, *clean])
        d = tmpdir(self)
        sess, rec, wav = session(d, levels=False)
        r, _ = transcribe(d, wav, rec / "transcript.raw.md", segs)
        self.assertEqual(r.returncode, 0, r.stderr)
        qf = rec / "transcript.quality.json"
        self.assertTrue(qf.is_file(), "應輸出 transcript.quality.json")
        q = json.loads(qf.read_text(encoding="utf-8"))
        self.assertIsInstance(q, list)
        for e in q:
            self.assertEqual(set(e), {"start", "end", "reason"}, e)
            self.assertIn(e["reason"], {"compression_ratio", "no_speech_loop", "repeat_run"})
        self.assertEqual([e["start"] for e in q], sorted(e["start"] for e in q), "依 start 遞增")
        by_start = {}
        for e in q:
            by_start.setdefault(round(e["start"], 3), set()).add(e["reason"])
        self.assertIn("no_speech_loop", by_start.get(10.0, set()), "「好的好的好的好的」應列 no_speech_loop")
        self.assertIn("compression_ratio", by_start.get(20.0, set()), "壓縮比 > 2.4 的段應列 compression_ratio")
        for a, _, _ in run:
            self.assertIn("repeat_run", by_start.get(round(a, 3), set()), f"連續 4 段相同文字，每段各一筆（{a}）")
        self.assertEqual(sum(1 for e in q if e["reason"] == "repeat_run"), 4)
        for a, _, _ in clean:
            self.assertNotIn(round(a, 3), by_start, f"沒有問題的段落不得列入（{a}）")

        d2 = tmpdir(self)
        sess2, rec2, wav2 = session(d2, levels=False)
        r, _ = transcribe(d2, wav2, rec2 / "transcript.raw.md", clean)
        self.assertEqual(r.returncode, 0, r.stderr)
        qf2 = rec2 / "transcript.quality.json"
        self.assertTrue(qf2.is_file(), "沒有問題時也應輸出（內容 []）")
        self.assertEqual(json.loads(qf2.read_text(encoding="utf-8")), [])

        # QUALITY_WARNING 的既有輸出格式不變（同一行連續 10 次）
        d3 = tmpdir(self)
        sess3, rec3, wav3 = session(d3, levels=False)
        r, _ = transcribe(d3, wav3, rec3 / "transcript.raw.md", [(float(i), i + 0.9, "嗯") for i in range(10)])
        self.assertEqual(r.returncode, 0, r.stderr)
        qw = (rec3 / "transcript.raw.md.QUALITY_WARNING").read_text(encoding="utf-8")
        self.assertRegex(qw.splitlines()[0], r"^REPETITION_LOOP_DETECTED consecutive=\d+ text=.* total=\d+$")

    # spec §4.45.3：meeting-transcribe SKILL.md 說明 VAD 與 transcript.quality.json
    def test_transcribe_skill_updated(self):
        text = TRANSCRIBE_SKILL.read_text(encoding="utf-8")
        missing = [k for k in ("VAD", "transcript.quality.json") if k not in text]
        self.assertEqual(missing, [], f"meeting-transcribe SKILL.md 缺少：{missing}")


if __name__ == "__main__":
    unittest.main()

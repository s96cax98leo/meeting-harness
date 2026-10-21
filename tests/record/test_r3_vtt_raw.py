"""VTT 講者與 _merge_speakers.py 一致、diarize 不重轉 raw、無效參數、--annotate-speakers 掛勾
（spec §4.29.1–§4.29.5、§4.31.10 的 r3-vtt-raw 部分）。

素材只在 TMPDIR；轉錄一律用 fakes/asr/mlx_whisper 替身（不載入模型）；diarization.json 事先放好，diarize.sh 會跳過 pyannote。
段落檔名：spec §3.18 稱 segments.json，現行程式寫 錄音/transcript.segments.json；本檔的 fixture 寫後者，
diarize 之後兩個名稱任一存在即可。
"""
import json
import os
import re
import subprocess
import sys
import unittest

from tests.record import _media as m
from tests.record._helpers import BIN, MEETING_SH, Sandbox, tmpdir
from tests.record.surface import REPO

RENDER_PY = BIN / "_render.py"
MERGE_PY = BIN / "_merge_speakers.py"
TRANSCRIBE_SH = BIN / "transcribe.sh"
TRANSCRIBE_SKILL = REPO / ".claude" / "skills" / "meeting-transcribe" / "SKILL.md"

# 逐字段（whisper）：s6 落在 exclusive 的空隙，只有 segmentsOverlapped 找得到講者
WSEGS = [(0.0, 4.0, "第一段範例"), (4.0, 9.0, "第二段範例"), (10.0, 15.0, "第三段範例"), (15.0, 19.0, "第四段範例"),
         (20.0, 21.5, "第五段範例"), (23.0, 26.0, "第六段範例")]
DIAR = {"segments": [{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"},
                     {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01"},
                     {"start": 20.0, "end": 22.0, "speaker": "SPEAKER_02"}],
        "segmentsOverlapped": [{"start": 0.0, "end": 10.0, "speaker": "SPEAKER_00"},
                               {"start": 10.0, "end": 20.0, "speaker": "SPEAKER_01"},
                               {"start": 20.0, "end": 22.0, "speaker": "SPEAKER_02"},
                               {"start": 22.5, "end": 26.0, "speaker": "SPEAKER_01"}]}

# §4.29.5：至少 6 組（apply true／false、沒有 apply 的 0.69 與 0.7、字串值、MH_MIN_SPEAKER_SEC=5、退到含重疊那份）
FIXTURES = [
    ("apply_true_false", {"SPEAKER_00": {"name": "範例甲", "confidence": 0.72, "apply": False},
                          "SPEAKER_01": {"name": "範例乙", "confidence": 0.81, "apply": True}}, {}),
    ("confidence_0_69", {"SPEAKER_00": {"name": "範例甲", "confidence": 0.69}}, {}),
    ("confidence_0_7", {"SPEAKER_00": {"name": "範例甲", "confidence": 0.7}}, {}),
    ("string_value", {"SPEAKER_01": "範例乙"}, {}),
    ("min_speaker_sec", {"SPEAKER_00": "範例甲", "SPEAKER_01": {"name": "範例乙", "apply": True}},
     {"MH_MIN_SPEAKER_SEC": "5"}),
    ("overlapped_fallback", {"SPEAKER_01": "範例乙"}, {}),
]


def write_speaker_fixture(sess, name_map):
    rec = sess / "錄音"
    rec.mkdir(parents=True, exist_ok=True)
    (rec / "transcript.segments.json").write_text(json.dumps(
        {"segments": [{"start": a, "end": b, "text": t} for a, b, t in WSEGS]}, ensure_ascii=False), encoding="utf-8")
    (rec / "diarization.json").write_text(json.dumps(DIAR, ensure_ascii=False), encoding="utf-8")
    if name_map is not None:
        (rec / "speakers.map.json").write_text(json.dumps(name_map, ensure_ascii=False), encoding="utf-8")
    return rec


def run_py(args, env=None, timeout=120):
    e = dict(os.environ)
    e.pop("MH_MIN_SPEAKER_SEC", None)
    e.update(env or {})
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, env=e, timeout=timeout)


def speakers_md_names(md):
    """transcript.speakers.md → 每個逐字段文字所屬 block 的講者顯示名。"""
    out, cur = {}, None
    texts = [t for _, _, t in WSEGS]
    for line in md.splitlines():
        h = re.match(r"^\*\*\[(.+?)\]\*\*", line)
        if h:
            cur = h.group(1)
            continue
        if cur is None:
            continue
        for t in texts:
            if t in line:
                out[t] = cur
    return out


def vtt_cues(vtt):
    """WebVTT → {逐字段文字: <v> 名稱或 None}（NOTE 區塊略過）。"""
    out = {}
    for block in re.split(r"\n\s*\n", vtt):
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines or lines[0].startswith("NOTE") or lines[0] == "WEBVTT":
            continue
        idx = next((i for i, ln in enumerate(lines) if "-->" in ln), None)
        if idx is None:
            continue
        body = " ".join(lines[idx + 1:])
        v = re.match(r"^<v ([^>]+)>(.*)$", body)
        name, text = (v.group(1), v.group(2)) if v else (None, body)
        for _, _, t in WSEGS:
            if t in text:
                out[t] = name
    return out


def is_real_name(n):
    return bool(n) and not n.startswith("SPEAKER_")


class TestR3VttRaw(unittest.TestCase):
    def merge_and_render(self, name_map, env):
        sess = tmpdir(self) / "場次"
        rec = write_speaker_fixture(sess, name_map)
        r = run_py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json",
                    rec / "transcript.speakers.md", rec / "speakers.map.json"], env)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = run_py([RENDER_PY, sess, "--vtt"], env)
        self.assertEqual(r.returncode, 0, r.stderr)
        md = (rec / "transcript.speakers.md").read_text(encoding="utf-8")
        vtt = (rec / "transcript.vtt").read_text(encoding="utf-8")
        return speakers_md_names(md), vtt_cues(vtt)

    def assert_consistent(self, md_names, cues, label):
        self.assertEqual(set(md_names), {t for _, _, t in WSEGS}, f"{label}：speakers.md 應含每一段")
        self.assertEqual(set(cues), {t for _, _, t in WSEGS}, f"{label}：VTT 應含每一段")
        for t, shown in md_names.items():
            if is_real_name(shown):
                self.assertEqual(cues[t], shown, f"{label}：「{t}」speakers.md 掛真名 {shown}，VTT 的 <v> 應相同")
            else:
                self.assertIsNone(cues[t], f"{label}：「{t}」speakers.md 是代號 {shown}，VTT 不得加 <v>")

    # spec §4.29.1：A（apply false、0.72）不掛真名、B（apply true、0.81）掛真名，VTT 與 speakers.md 一致
    def test_vtt_uses_merge_assignment(self):
        name_map, env = FIXTURES[0][1], FIXTURES[0][2]
        md_names, cues = self.merge_and_render(name_map, env)
        self.assertEqual(md_names["第一段範例"], "SPEAKER_00", "A 不掛真名，speakers.md 用代號")
        self.assertIsNone(cues["第一段範例"], "A 不掛真名，VTT 不加 <v>")
        self.assertEqual(md_names["第三段範例"], "範例乙")
        self.assertEqual(cues["第三段範例"], "範例乙")
        self.assert_consistent(md_names, cues, "apply_true_false")

    # spec §4.29.2：_render.py 沒有自己的 0.3 比例；以 importlib 載入 _merge_speakers.assign_speaker；註解寫出處行號
    def test_render_has_no_private_ratio(self):
        src = RENDER_PY.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[<>]=?\s*0\.3\b|\b0\.3\s*[<>]=?", src), "_render.py 不得有 0.3 的比例比較")
        self.assertIn("importlib", src, "應以 importlib 載入 bin/_merge_speakers.py")
        self.assertIn("_merge_speakers", src)
        self.assertIn("assign_speaker", src)
        self.assertRegex(src, r"_merge_speakers\.py:\d+", "照抄的判準要在註解寫明出處行號（_merge_speakers.py:<行>）")

    # spec §4.29.3，meeting-speed spec §6 第 20 條（使用者 2026-10-21 核准）：缺段落檔時 diarize 不動 raw
    # （內容與 mtime）、不呼叫轉錄替身、回 1、輸出含「缺 transcript.segments.json」
    def test_diarize_keeps_raw(self):
        sb = Sandbox(self)
        sess = m.make_audio_session(sb.root)
        rec = sess / "錄音"
        raw = rec / "transcript.raw.md"
        raw.write_text("# 逐字稿（原始，未經任何後處理）\n\n> 來源：範例.wav　語言：zh　模型：範例\n\n原始內容（不得被重寫）\n",
                       encoding="utf-8")
        os.utime(raw, (1_700_000_000, 1_700_000_000))
        before = (raw.read_bytes(), raw.stat().st_mtime_ns)
        (rec / "diarization.json").write_text(json.dumps(DIAR, ensure_ascii=False), encoding="utf-8")
        env, log = m.fake_asr_env(sb.base, WSEGS)
        r = sb.meeting("diarize", sess, timeout=180, **env)
        self.assertEqual((raw.read_bytes(), raw.stat().st_mtime_ns), before,
                         f"transcript.raw.md 的內容與 mtime 應不變\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual(m.read_asr_calls(log), [], "缺 transcript.segments.json 時不得呼叫轉錄替身")
        self.assertEqual(r.returncode, 1, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("缺 transcript.segments.json", r.stdout + r.stderr)

    # spec §4.29.5：6 組 fixture 的 VTT 與 _merge_speakers.py 對每一段掛的真名一致
    def test_render_copy_matches_merge(self):
        self.assertGreaterEqual(len(FIXTURES), 6)
        for label, name_map, env in FIXTURES:
            with self.subTest(fixture=label):
                md_names, cues = self.merge_and_render(name_map, env)
                self.assert_consistent(md_names, cues, label)

    # spec §4.29.4：transcribe.sh 不得有 --compression-ratio-threshold；SKILL.md 不得說它有作用
    def test_no_compression_flag(self):
        self.assertNotIn("--compression-ratio-threshold", TRANSCRIBE_SH.read_text(encoding="utf-8"))
        text = TRANSCRIBE_SKILL.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "compression-ratio-threshold" in line or "compression_ratio_threshold" in line:
                self.assertTrue(any(w in line for w in ("無效", "沒有作用", "已移除", "不再")),
                                f"meeting-transcribe SKILL.md 不得說這個參數有作用：{line}")

    # spec §4.31.10（r3-vtt-raw 部分）：run_diarize 在 _merge_speakers.py 之後呼叫 --annotate-speakers；沒有事件與品質檔時不改檔
    def test_annotate_hook_noop(self):
        sh = MEETING_SH.read_text(encoding="utf-8")
        body = sh[sh.index("run_diarize() {"):]
        body = body[:body.index("\n}\n")]
        self.assertIn("--annotate-speakers", body, "run_diarize 應呼叫 _render.py --annotate-speakers")
        self.assertLess(body.index("_merge_speakers.py"), body.index("--annotate-speakers"),
                        "--annotate-speakers 應在 _merge_speakers.py 之後")
        self.assertIn("--annotate-speakers", RENDER_PY.read_text(encoding="utf-8"))
        sess = tmpdir(self) / "場次"
        rec = write_speaker_fixture(sess, FIXTURES[0][1])
        r = run_py([MERGE_PY, rec / "transcript.segments.json", rec / "diarization.json",
                    rec / "transcript.speakers.md", rec / "speakers.map.json"])
        self.assertEqual(r.returncode, 0, r.stderr)
        md = rec / "transcript.speakers.md"
        before = (md.read_bytes(), md.stat().st_mtime_ns)
        r = run_py([RENDER_PY, sess, "--annotate-speakers"])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((md.read_bytes(), md.stat().st_mtime_ns), before, "沒有事件、沒有品質檔時不得改檔")


if __name__ == "__main__":
    unittest.main()

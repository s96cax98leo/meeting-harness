"""ultrareview（2026-10-13）確認屬實的發現：spec §6 第 112–116 條。"""
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.record import _media as m
from tests.record._helpers import Sandbox
from tests.record.surface import REPO

BIN = REPO / "bin"


def unit(v):
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v]


def with_cos(base, other, c):
    """回傳與 base 夾角餘弦為 c 的單位向量（在 base、other 張成的平面上）。"""
    b = unit(base)
    o = unit(other)
    d = sum(x * y for x, y in zip(b, o))
    perp = unit([y - d * x for x, y in zip(b, o)])
    s = math.sqrt(1 - c * c)
    return [c * x + s * y for x, y in zip(b, perp)]


class ReviewFixes(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def session(self, meeting=None, emb=None):
        sess = self.tmp / "場次"
        (sess / "錄音").mkdir(parents=True, exist_ok=True)
        if meeting is not None:
            (sess / "錄音" / "meeting.json").write_text(json.dumps(meeting, ensure_ascii=False), encoding="utf-8")
        if emb is not None:
            (sess / "錄音" / "embeddings.json").write_text(json.dumps({"speakers": emb}), encoding="utf-8")
        return sess

    # §6 第 112 條：_profile.py 的輸出給 eval，meeting.json 的值不得注入指令
    def test_profile_eval_no_injection(self):
        marker = self.tmp / "pwned"
        evil = f'zh"; touch {marker}; x="'
        sess = self.session({"type": "internal", "language": evil, "llm": "claude$(touch " + str(marker) + ")"})
        r = subprocess.run(["bash", "-c", 'eval "$(python3 "$0" "$1")"; printf "%s" "$MH_LANG"',
                            str(BIN / "_profile.py"), str(sess)], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(marker.exists(), "meeting.json 的 language／llm 不得在 eval 時執行指令")
        self.assertEqual(r.stdout, evil, "MH_LANG 應原樣保留 meeting.json 的字串")

    # §6 第 114 條：同一個名字由信心最高的 SPEAKER 拿到，不看 embeddings.json 的順序
    def test_voiceprint_match_assigns_by_confidence(self):
        alice = unit([1.0, 0.0, 0.0, 0.2])
        bob = unit([0.0, 1.0, 0.0, 0.1])
        a_low = with_cos(alice, [0.0, 0.0, 1.0, 0.0], 0.78)    # 先出現、但不是 Alice
        a_high = with_cos(alice, [0.0, 0.3, 0.0, 1.0], 0.95)   # 後出現、真的 Alice
        harness = self.tmp / "h"
        vp = harness / "vault" / "voiceprints"
        vp.mkdir(parents=True)
        for name, v in (("Alice", alice), ("Bob", bob)):
            (vp / f"{name}.json").write_text(json.dumps({"name": name, "vector": v, "dim": 4, "samples": 1,
                                                         "sources": ["x"]}), encoding="utf-8")
        sess = self.session(emb={"SPEAKER_00": a_low, "SPEAKER_01": a_high})
        r = subprocess.run([sys.executable, str(BIN / "_voiceprint.py"), "match", str(sess), "--harness", str(harness)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        mp = json.loads((sess / "錄音" / "speakers.map.json").read_text(encoding="utf-8"))
        self.assertEqual(mp.get("SPEAKER_01", {}).get("name"), "Alice", "Alice 應給信心最高的 SPEAKER_01")
        self.assertNotEqual(mp.get("SPEAKER_00", {}).get("name"), "Alice")

    # §6 第 115 條：維度不同的向量不得與既有聲紋平均
    def test_voiceprint_add_rejects_dim_mismatch(self):
        harness = self.tmp / "h"
        vp = harness / "vault" / "voiceprints"
        vp.mkdir(parents=True)
        rec = {"name": "Alice", "vector": [0.1, 0.2, 0.3, 0.4], "dim": 4, "samples": 1, "sources": ["x"]}
        (vp / "Alice.json").write_text(json.dumps(rec), encoding="utf-8")
        sess = self.session(emb={"SPEAKER_00": [0.5, 0.5]})
        r = subprocess.run([sys.executable, str(BIN / "_voiceprint.py"), "add", str(sess), "SPEAKER_00", "Alice",
                            "--harness", str(harness)], capture_output=True, text=True, timeout=60)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("維", r.stderr)
        self.assertEqual(json.loads((vp / "Alice.json").read_text(encoding="utf-8"))["vector"], rec["vector"])

    # §6 第 116 條：config.json 的 enabled 與門檻真的有作用（環境變數仍優先）
    def copy_with_config(self, script, cfg):
        root = self.tmp / "repo"
        (root / "bin").mkdir(parents=True, exist_ok=True)
        shutil.copy(BIN / script, root / "bin" / script)
        (root / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        return root / "bin" / script

    def test_config_diarize_enabled_false(self):
        script = self.copy_with_config("_profile.py", {"diarize": {"enabled": False}})
        sess = self.session({"type": "internal"})
        env = {k: v for k, v in os.environ.items() if k != "MH_DIARIZE"}
        r = subprocess.run([sys.executable, str(script), str(sess)], capture_output=True, text=True, env=env, timeout=60)
        self.assertIn("MH_DO_DIARIZE=0", r.stdout)
        env["MH_DIARIZE"] = "1"
        r = subprocess.run([sys.executable, str(script), str(sess)], capture_output=True, text=True, env=env, timeout=60)
        self.assertIn("MH_DO_DIARIZE=1", r.stdout, "MH_DIARIZE=1 仍可單次強制開")

    def test_config_voiceprint_enabled_false_and_thresholds(self):
        script = self.copy_with_config("_voiceprint.py", {"voiceprint": {"enabled": False}})
        sess = self.session(emb={"SPEAKER_00": [1.0, 0.0]})
        r = subprocess.run([sys.executable, str(script), "match", str(sess)], capture_output=True, text=True, timeout=60)
        self.assertIn("enabled", r.stdout)
        self.assertFalse((sess / "錄音" / "speakers.map.json").exists())
        src = (BIN / "_voiceprint.py").read_text(encoding="utf-8")
        self.assertIn('"renameThreshold"', src)
        self.assertIn('"hintThreshold"', src)
        self.assertIn('get("device"', (BIN / "_diarize_pyannote.py").read_text(encoding="utf-8"))


class PartialCleanup(unittest.TestCase):
    THREE = [dict(dur=2.0), dict(dur=2.0), dict(dur=2.0)]

    # §6 第 113 條：段落只刪掉一部分時，不得拿殘缺段落重做、覆蓋好的成品
    def test_partial_cleanup_does_not_refinalize(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, self.THREE)
        tracks = sess / "錄音" / "tracks"
        r = sb.meeting("record", "finish", sess, timeout=300, MH_KEEP_SEGMENTS="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        outs = sorted(list((sess / "影片").glob("*.mov")) + list((sess / "錄音").glob("*.wav")))
        before = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in outs}
        sorted(tracks.glob("seg-*.mov"))[0].unlink()      # 模擬上次清除只刪掉一個
        r2 = sb.meeting("record", "finish", sess, timeout=300)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertIn("已完成", r2.stdout + r2.stderr)
        self.assertEqual({p: (p.stat().st_size, p.stat().st_mtime_ns) for p in outs}, before, "成品不得被重做")
        self.assertEqual(list(tracks.glob("seg-*.mov")), [], "應重試清除剩下的段落")

    # nit：模組說明不得再寫段落永遠保留；meeting.sh 開頭不得再寫分離預設關閉
    def test_stale_comments_fixed(self):
        self.assertNotIn("段落永遠保留", (BIN / "_record_finalize.py").read_text(encoding="utf-8"))
        self.assertNotIn("預設關閉", (BIN / "meeting.sh").read_text(encoding="utf-8").split("\n", 30)[:30].__str__())


if __name__ == "__main__":
    unittest.main()

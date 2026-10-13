"""e2e_check.py 的 --sync-player、--sync-acoustic、--print-sync-file（spec §4.35.2–§4.35.4；D3、S-A）。

素材只在 TMPDIR（tests/record/_media.py 的 R3 合成函式）。--sync-player 的結果以 --json 輸出中檢查名含「player」的那一筆判讀
（spec 未定檢查名；只會有一筆）。
"""
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from tests.record import _media as m
from tests.record._helpers import tmpdir

E2E = Path(__file__).resolve().parent / "e2e_check.py"


def e2e(*args, cwd=None, timeout=300):
    return subprocess.run([sys.executable, str(E2E), *map(str, args)], capture_output=True, text=True,
                          timeout=timeout, cwd=cwd)


def player_result(tc, sess):
    r = e2e("--sync-player", sess, "--json")
    tc.assertIn(r.returncode, (0, 1), f"e2e_check.py --sync-player 回 {r.returncode}：{r.stderr}")
    res = [x for x in json.loads(r.stdout) if "player" in x["check"]]
    tc.assertEqual(len(res), 1, f"--json 應恰有一筆 sync-player 的結果：{[x['check'] for x in json.loads(r.stdout)]}")
    return r, res[0]


class TestR3SyncMeasure(unittest.TestCase):
    # spec §4.35.2：60 秒時段取差值中位數，|中位數| < 45 ms → PASS；一個 159 ms 離群值＋8 個 20 ms → PASS；全部 60 ms → FAIL；
    # 有 finalize.json.syncCompensation 時報告列出各段套用的延遲
    def test_sync_player_median(self):
        d = tmpdir(self)
        ok = m.build_sync_player_session(d / "pass", [0.020] * 4 + [0.159] + [0.020] * 4)
        _, res = player_result(self, ok)
        self.assertTrue(res["ok"], res["detail"])
        bad = m.build_sync_player_session(d / "fail", [0.060] * 9)
        _, res = player_result(self, bad)
        self.assertFalse(res["ok"], res["detail"])
        fin = ok / "錄音" / "tracks" / "finalize.json"
        fin.write_text(json.dumps({"schemaVersion": 1, "syncCompensation": {"mode": "reported", "segments": [
            {"file": "seg-0001.mov", "outputUid": "uid-範例-a", "delaySeconds": 0.0, "source": "reported",
             "clamped": False},
            {"file": "seg-0002.mov", "outputUid": "uid-範例-b", "delaySeconds": 0.15, "source": "reported",
             "clamped": False}]}}, ensure_ascii=False), encoding="utf-8")
        _, res = player_result(self, ok)
        self.assertTrue(any(s in res["detail"] for s in ("0.15", "150 ms", "150ms")),
                        f"報告應列出各段套用的延遲：{res['detail']}")

    # spec §4.35.3：每個 60 秒時段印 mic − sys 中位數（毫秒整數）與組數、回 0；沒有可配對的嗶聲時印「沒有可配對的嗶聲」、回 0
    def test_sync_acoustic_report(self):
        d = tmpdir(self)
        sess = m.build_acoustic_session(d / "有嗶聲", mic_delay=0.08)
        r = e2e("--sync-acoustic", sess)
        self.assertEqual(r.returncode, 0, r.stderr)
        nums = [int(x) for x in re.findall(r"(?<![\d.])-?\d+(?![\d.])", r.stdout)]
        self.assertTrue(any(78 <= n <= 82 for n in nums), f"應印出約 80 ms 的 mic − sys 中位數：{r.stdout}")
        self.assertIn("4", re.findall(r"\d+", r.stdout), f"應印出組數（4 組）：{r.stdout}")
        none = m.build_acoustic_session(d / "沒有嗶聲", sys_beeps=())
        r = e2e("--sync-acoustic", none)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("沒有可配對的嗶聲", r.stdout)

    # spec §4.35.4：--print-sync-file 只寫到指定路徑，ffprobe 讀得出影像與聲音兩軌
    def test_print_sync_file(self):
        d = tmpdir(self)
        out_dir, cwd = d / "輸出", d / "工作目錄"
        out_dir.mkdir()
        cwd.mkdir()
        target = out_dir / "sync-source.mov"
        r = e2e("--print-sync-file", target, cwd=cwd)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(target.is_file(), "應寫出指定的檔")
        self.assertEqual(sorted(p.name for p in out_dir.iterdir()), [target.name], "只寫指定路徑")
        self.assertEqual(list(cwd.iterdir()), [], "工作目錄不得留下任何檔")
        info = m.probe(target)
        self.assertIsNotNone(info, "ffprobe 應讀得出")
        kinds = {s["codec_type"] for s in info["streams"]}
        self.assertTrue({"video", "audio"} <= kinds, kinds)


if __name__ == "__main__":
    unittest.main()

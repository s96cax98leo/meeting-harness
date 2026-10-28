"""增量轉錄 stitch 只收窗範圍內的段落（2026-10-27 實錄回報）。

模型在某一窗的尾巴陷入重複時，吐出的段落時間會超過這個窗的結尾（甚至往回跳），
而同一段時間的真實內容在下一窗裡。stitch 若照收，逐字稿會在同一時段出現兩份（一份是重複迴圈）。
規則：段落的 start 落在 [窗 start, 窗 end) 之外就不收；w-*.json 本身不改（引擎原始輸出）。

素材只在 TMPDIR；模型一律用 fakes/pymod/mlx_whisper；場次名用範例名稱。
"""
import json

from tests.record import test_ms_support as s
from tests.record.test_ms_incremental_asr import WorkerCase


class TestStitchClipsToWindow(WorkerCase):
    def inject_loop(self, sess):
        """在第 1 窗結果檔尾端加上超出窗結尾的重複段落（時間往回跳，同實錄），回傳 (窗, 原始檔內容)。"""
        w = self.windows(sess)[0]
        p = s.tracks_of(sess) / "asr" / w["file"]
        d = json.loads(p.read_text(encoding="utf-8"))
        end = w["end"]
        loop = [{"start": round(end + 0.24 + k, 3), "end": round(end + 1.24 + k, 3), "text": "迴圈"} for k in range(6)]
        loop += [{"start": round(end + 0.24, 3), "end": round(end + 1.24, 3), "text": "迴圈"}]
        d["segments"] += loop
        d["text"] += "迴圈" * len(loop)
        raw = json.dumps(d, ensure_ascii=False)
        p.write_text(raw, encoding="utf-8")
        return w, raw

    def test_stitch_drops_segments_past_window_end(self):
        sess = self.completed(2)
        w, raw = self.inject_loop(sess)
        out = self.base / "stitched.json"
        r = self.stitch(sess, out)
        self.assertEqual(r.returncode, 0, s.out_of(r))
        d = json.loads(out.read_text(encoding="utf-8"))
        texts = [x["text"] for x in d["segments"]]
        self.assertNotIn("迴圈", texts, "超出窗結尾的段落不得收進 stitch 結果")
        self.assertNotIn("迴圈", d["text"])
        starts = [x["start"] for x in d["segments"]]
        self.assertEqual(starts, sorted(starts), "stitch 結果的段落時間應單調不減")
        self.assertEqual([x["id"] for x in d["segments"]], list(range(len(d["segments"]))), "id 應連續重編")
        self.assertEqual((s.tracks_of(sess) / "asr" / w["file"]).read_text(encoding="utf-8"), raw,
                         "w-*.json 是引擎原始輸出，stitch 不得改寫")

    def test_stitch_keeps_in_window_segments(self):
        sess = self.completed(2)
        before = self.base / "before.json"
        self.assertEqual(self.stitch(sess, before).returncode, 0)
        self.inject_loop(sess)
        after = self.base / "after.json"
        self.assertEqual(self.stitch(sess, after).returncode, 0)
        a = json.loads(before.read_text(encoding="utf-8"))
        b = json.loads(after.read_text(encoding="utf-8"))
        self.assertEqual(a, b, "只多了窗外段落時，stitch 結果應與沒有它們時完全相同")

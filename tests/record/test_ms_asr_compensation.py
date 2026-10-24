"""增量轉錄 stitch：影音延遲補償不是 off 時不可用（meeting-speed spec §4.11.7；Story G2、G4）。

收尾採用的補償模式（audio-ready.json 的 compensation）不是 off 時，成品 wav 的時間軸已被平移或伸縮，
各窗以未補償段落轉出的時間對不上；stitch 應回 3、印一行原因、不寫出結果，讓 prep 退回整檔轉錄。
"""
import json
import unittest

from tests.record import test_ms_support as s
from tests.record.test_ms_incremental_asr import WorkerCase


class TestMSAsrCompensation(WorkerCase):
    def _set_ready_compensation(self, sess, mode):
        p = s.tracks_of(sess) / "audio-ready.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        d["compensation"] = mode
        p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    # spec §4.11.7：其他條件都成立、只有收尾的補償模式不是 off → 回 3 並印原因
    def test_stitch_compensation_not_off_exit3(self):
        for mode in ("constant", "variable"):
            with self.subTest(compensation=mode):
                sess = self.session(2, silences=[(4.0, 7.0)], sub=mode)   # 每個 subTest 各用一個場次目錄
                self.status(sess, "done")
                self.run_worker(sess)
                self.assertEqual((self.state(sess) or {}).get("status"), "complete")
                self.write_audio_ready(sess)
                self._set_ready_compensation(sess, mode)
                out = self.base / f"stitched-{mode}.json"
                r = self.stitch(sess, out)
                self.assertEqual(r.returncode, 3, s.out_of(r))
                self.assertIn("補償", r.stderr, "原因應指出補償模式")
                self.assertFalse(out.exists(), "不可用時不得寫出結果")


if __name__ == "__main__":
    unittest.main()

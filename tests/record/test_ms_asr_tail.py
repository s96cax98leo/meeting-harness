"""增量轉錄 worker：異常中止後接手時，最後一段 finishedAt 為 null（meeting-speed spec §4.11.5、§4.16；Story G2、G5）。

錄製器在收尾前結束時，manifest 最後一段的 finishedAt 留 null，但檔案在、收尾照樣採用它。
worker 在 phase 已停止時應把這段也補進最後一窗，否則 stitch 會因段數不符回 3、prep 退回整檔轉錄。
"""
import unittest

from tests.record import test_ms_support as s
from tests.record.test_ms_incremental_asr import SEG, WorkerCase


class TestMSAsrTail(WorkerCase):
    # spec §4.11.5：停止後最後一窗延伸到最後一段結尾——最後一段 finishedAt 為 null 也一樣
    def test_completes_with_unfinished_last_segment(self):
        sess = self.session(2, unfinished=(2,))
        self.status(sess, "recording")
        w = self.start_worker(sess)
        self.wait_windows(sess, 1)
        self.status(sess, "done")   # 不呼叫 finish_segment：模擬錄製器沒寫 finishedAt 就結束
        self.assertTrue(s.wait_until(lambda: w.poll() is not None, timeout=90), "停止後 worker 應補完並結束")
        self.assertEqual(w.returncode, 0)
        st = self.state(sess)
        self.assertEqual(st.get("status"), "complete", st)
        win = self.windows(sess)
        files = [x["file"] for w_ in win for x in w_.get("segments") or []]
        self.assertIn("seg-0002.mov", files, f"最後一段應被涵蓋：{win}")
        self.assertAlmostEqual(win[-1]["end"], 2 * SEG, delta=0.05)

    # 錄製中（phase 還是 recording）finishedAt 為 null 的段落不得先處理
    def test_unfinished_segment_skipped_while_recording(self):
        sess = self.session(2, unfinished=(2,))
        self.status(sess, "recording")
        self.start_worker(sess)
        self.wait_windows(sess, 1)
        st = self.state(sess)
        self.assertEqual(st.get("status"), "running", st)
        files = [x["file"] for w_ in self.windows(sess) for x in w_.get("segments") or []]
        self.assertNotIn("seg-0002.mov", files, "錄製中不得處理還沒關檔的段落")


if __name__ == "__main__":
    unittest.main()

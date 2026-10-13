"""R2：record finish（bin/_record_finalize.py）的暫停扣除與 markers.json 複製（spec §3.11、§3.12、§4.18.4、§4.19.3）。

合成素材只在 TMPDIR；錄製器一律替身，不開真的 app。
"""
import json
import unittest

from tests.record import _media as m
from tests.record._helpers import Sandbox

GAP_KEYS_R1 = {"boundaries", "max", "total", "wallClock"}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class R2FinalizeCase(unittest.TestCase):
    def finish(self, sb, sess):
        r = sb.meeting("record", "finish", sess, timeout=300)
        self.assertEqual(r.returncode, 0, f"record finish 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        return r

    def manifest(self, sess):
        return read_json(sess / "錄音" / "tracks" / "manifest.json")

    def edit_json(self, path, fn):
        d = read_json(path)
        fn(d)
        path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

    def write_markers(self, sess, record_ts, pauses=()):
        items = m.marker_items(record_ts, 0.0, m.pause_events(pauses, 0.0))
        p = sess / "錄音" / "tracks" / "markers.json"
        p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        return p


class TestR2Finalize(R2FinalizeCase):
    # spec §4.18.4：seg-0001 約 10 秒（startedAt 0.0）、seg-0002 約 7 秒（startedAt 40.0）、暫停 10.0 → 40.0
    def test_gapstats_subtracts_pause(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=10.0, w=160, h=120), dict(dur=7.0, w=160, h=120)])
        tracks = sess / "錄音" / "tracks"

        def move(d):
            d["segments"][1].update(requestedAt=39.995, startedAt=40.0, finishedAt=47.0)
            n = int(47.0 / 0.5) + 1
            d["levels"] = {"windowSeconds": 0.5,
                           "system": [None if 10.0 <= k * 0.5 < 40.0 else -20.0 for k in range(n)],
                           "mic": [None if 10.0 <= k * 0.5 < 40.0 else -30.0 for k in range(n)]}
        self.edit_json(tracks / "manifest.json", move)
        pev = m.pause_events([(10.0, "pause"), (40.0, "resume")], 0.0)
        self.edit_json(tracks / "record.meta.json", lambda d: d.update(pauseEvents=pev, micMuteEvents=[]))
        self.finish(sb, sess)
        gs = self.manifest(sess).get("gapStats") or {}
        self.assertIn("pausedTotal", gs, "gapStats 應有 pausedTotal（§3.11）")
        self.assertAlmostEqual(gs["pausedTotal"], 30.0, delta=0.01)
        self.assertLess(abs(gs["boundaries"][0]), 0.05, f"暫停邊界的 g 應扣掉暫停長度：{gs['boundaries']}")
        self.assertLess(abs(gs["max"]), 0.05)
        wav = sorted((sess / "錄音").glob("*.wav"))
        self.assertEqual(len(wav), 1)
        d = m.stream_duration(wav[0], "audio")
        self.assertIsNotNone(d)
        self.assertLess(abs(d - 17.0), 0.5, f"成品長度應約 17 秒（暫停被剪掉）：{d}")

    # spec §4.18.4：沒有 pauseEvents 的場次 pausedTotal 為 0.0，其餘照 §3.2
    def test_gapstats_no_pause_unchanged(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0, w=160, h=120), dict(dur=2.0, w=160, h=120)])
        # R2 錄製器開錄就寫 pauseEvents: []（§3.11）；pausedTotal 只在 meta 有這個鍵時寫（§6 第 100 條）
        mp = sess / "錄音" / "tracks" / "record.meta.json"
        meta = json.loads(mp.read_text(encoding="utf-8"))
        meta["pauseEvents"] = []
        mp.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        self.finish(sb, sess)
        mf = self.manifest(sess)
        gs = mf.get("gapStats") or {}
        self.assertEqual(set(gs), GAP_KEYS_R1 | {"pausedTotal"}, "R2 場次 gapStats 應為第一輪 4 個鍵＋pausedTotal")
        self.assertEqual(gs["pausedTotal"], 0.0)
        recs = mf["segments"]
        want = [recs[i + 1]["startedAt"] - recs[i]["startedAt"] - recs[i]["audioDuration"] for i in range(len(recs) - 1)]
        for got, w in zip(gs["boundaries"], want):
            self.assertAlmostEqual(got, w, delta=0.002, msg="沒有暫停時 boundaries 照 §3.2")
        self.assertAlmostEqual(gs["max"], max(want), delta=0.002)

    # spec §4.19.3
    def test_markers_copied_and_idempotent(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0, w=160, h=120)])
        src = self.write_markers(sess, [0.5, 1.5])
        self.finish(sb, sess)
        dst = sess / "錄音" / "markers.json"
        self.assertTrue(dst.is_file(), "首次收尾應把 tracks/markers.json 複製成 錄音/markers.json")
        self.assertEqual(dst.read_bytes(), src.read_bytes(), "兩檔應逐位元組相同")
        mtime = dst.stat().st_mtime_ns
        self.finish(sb, sess)  # 已完成、冪等
        self.assertEqual(dst.stat().st_mtime_ns, mtime, "第二次 finish 不得重寫 錄音/markers.json")
        self.assertEqual(dst.read_bytes(), src.read_bytes())

    # spec §4.19.3：已完成的場次之後才出現 tracks/markers.json（或 錄音/markers.json 被刪）時，再跑 finish 應補上
    def test_markers_copied_on_already_done(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0, w=160, h=120)])
        self.finish(sb, sess)
        dst = sess / "錄音" / "markers.json"
        self.assertFalse(dst.exists())
        src = self.write_markers(sess, [1.0])
        self.finish(sb, sess)
        self.assertTrue(dst.is_file(), "已完成的場次再 finish 應補上 錄音/markers.json")
        self.assertEqual(dst.read_bytes(), src.read_bytes())
        dst.unlink()
        self.finish(sb, sess)
        self.assertTrue(dst.is_file(), "錄音/markers.json 被刪後再 finish 應補上")
        self.assertEqual(dst.read_bytes(), src.read_bytes())

    # spec §4.19.3
    def test_markers_absent_no_file(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0, w=160, h=120)])
        self.finish(sb, sess)
        self.assertFalse((sess / "錄音" / "markers.json").exists(), "沒有 tracks/markers.json 時不建 錄音/markers.json")

    # spec §4.19.3、§3.12：markers.json 不是音源副檔名，不影響場次判斷
    def test_markers_not_listed_as_session(self):
        sb = Sandbox(self)
        real = sb.root / m.DAY / "有音檔的場次" / "錄音"
        real.mkdir(parents=True)
        (real / "範例.wav").write_bytes(b"RIFF")
        only = sb.root / m.DAY / "只有標記的場次" / "錄音"
        only.mkdir(parents=True)
        (only / "markers.json").write_text(json.dumps(m.marker_items([1.0], 0.0, []), ensure_ascii=False),
                                           encoding="utf-8")
        r = sb.meeting("status", sb.root, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("有音檔的場次", r.stdout, "前提：有音源檔的場次應被列出")
        self.assertNotIn("只有標記的場次", r.stdout, "只有 錄音/markers.json 的資料夾不得被列為場次")


if __name__ == "__main__":
    unittest.main()

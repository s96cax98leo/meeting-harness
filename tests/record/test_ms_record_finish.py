"""`meeting record finish` 不帶參數時接手異常中止的場次（meeting-speed spec §4.16.3、§6 第 24 條；Story G5）。

判定只讀 `<record home>/record.status.json` 的 phase、pid、session，加上「段落待收尾」（spec §3.10）：
`<session>/錄音/tracks/` 有 seg-*.mov，且 finalize.json 不存在、或 videoPublishedAt 為 null、或（舊 schema）
兩個鍵都沒有；videoPublishedAt 非 null 或舊 schema 有 finishedAt 都算已收尾。`record.pid` 存在與否不影響判定（E2）。
條件成立時 stderr 印「· 接手異常中止的場次：<路徑>」後照 `finish <場次>` 執行；不成立照舊印「✗ 少了場次目錄…」回 2。
素材只在 TMPDIR；收尾用真的 ffmpeg 跑一段 2 秒的合成段落。
"""
import json
import os
import unittest

from tests.record import test_ms_support as s
from tests.record._helpers import Sandbox, dead_pid

TAKEOVER = "· 接手異常中止的場次："
MISSING = "✗ 少了場次目錄"


class TestMSRecordFinish(unittest.TestCase):
    def setup_session(self, *, phase="stopping", pid=None, session=None, pid_file=None):
        sb = Sandbox(self)
        sess = s.record_session(sb.root, [dict(dur=2.0)])
        s.write_status(sb.home, phase=phase, pid=dead_pid() if pid is None else pid,
                       session=str(sess if session is None else session), segments=1)
        if pid_file is not None:
            (sb.home / "record.pid").write_text(f"{pid_file}\n", encoding="utf-8")
        return sb, sess

    def finish(self, sb):
        return sb.meeting("record", "finish", timeout=300, PATH=s.py_path_env())

    def assert_takeover(self, r, sess):
        self.assertIn(f"{TAKEOVER}{sess}", r.stderr, f"stderr 應印接手的場次路徑{s.out_of(r)}")
        self.assertEqual(r.returncode, 0, f"接手後應照 finish <場次> 收尾成功（回 0）{s.out_of(r)}")
        self.assertEqual(len(s.videos(sess)), 1, "接手後應產出影片")
        self.assertEqual(len(s.wavs(sess)), 1, "接手後應產出錄音成品")

    def assert_not_taken(self, r, sess):
        self.assertEqual(r.returncode, 2, f"沒有可接手的場次時應照舊回 2{s.out_of(r)}")
        self.assertIn(MISSING, r.stderr, f"應照舊印「{MISSING}」{s.out_of(r)}")
        self.assertNotIn(TAKEOVER, r.stderr)
        self.assertEqual(s.videos(sess), [], "不得收尾")

    # spec §4.16.3：phase＝stopping、狀態檔 pid 已死、場次存在、段落待收尾 → 接手（record.pid 也指向已死的 pid）
    def test_no_arg_uses_abnormal_session(self):
        pid = dead_pid()
        sb, sess = self.setup_session(pid=pid, pid_file=pid)
        self.assert_takeover(self.finish(sb), sess)

    # spec §4.16.3（E2）：`record stop` 已刪掉 record.pid，只剩狀態檔 → 仍接手
    def test_no_arg_after_stop_removed_pid_file(self):
        sb, sess = self.setup_session()
        self.assertFalse((sb.home / "record.pid").exists(), "前提：沒有 record.pid")
        self.assert_takeover(self.finish(sb), sess)

    # spec §4.16.3：沒有狀態檔 → 照舊 2
    def test_no_arg_without_status_exit2(self):
        sb = Sandbox(self)
        sess = s.record_session(sb.root, [dict(dur=2.0)])
        self.assert_not_taken(self.finish(sb), sess)

    # spec §4.16.3：狀態檔記錄的 pid 還活著 → 照舊 2
    def test_no_arg_live_pid_exit2(self):
        sb, sess = self.setup_session(pid=os.getpid())
        self.assert_not_taken(self.finish(sb), sess)

    # spec §4.16.3：phase 不是 stopping → 照舊 2
    def test_no_arg_other_phase_exit2(self):
        for phase in ("recording", "finalizing", "done", "failed", "paused"):
            with self.subTest(phase=phase):
                sb, sess = self.setup_session(phase=phase)
                self.assert_not_taken(self.finish(sb), sess)

    # spec §4.16.3：狀態檔的 session 不是存在的目錄 → 照舊 2
    def test_no_arg_session_missing_exit2(self):
        sb = Sandbox(self)
        sess = s.record_session(sb.root, [dict(dur=2.0)])
        s.write_status(sb.home, phase="stopping", pid=dead_pid(), session=str(sb.root / "不存在的範例場次"))
        self.assert_not_taken(self.finish(sb), sess)

    # spec §4.16.3、§3.10、§7 疑慮 15：段落還在但已收尾（videoPublishedAt 非 null；舊 schema 有 finishedAt）→ 照舊 2；
    # 段落已清掉 → 照舊 2
    def test_no_arg_already_finalized_exit2(self):
        cases = {
            "videoPublishedAt 非 null": {"schemaVersion": 1, "finishedAt": "2026-10-21T11:31:00+08:00",
                                        "videoPublishedAt": "2026-10-21T11:33:00+08:00"},
            "舊 schema 有 finishedAt": {"schemaVersion": 1, "finishedAt": "2026-10-21T11:31:00+08:00"},
        }
        for label, fin in cases.items():
            with self.subTest(case=label):
                sb, sess = self.setup_session()
                (s.tracks_of(sess) / "finalize.json").write_text(json.dumps(fin, ensure_ascii=False), encoding="utf-8")
                self.assert_not_taken(self.finish(sb), sess)
        with self.subTest(case="段落已清掉"):
            sb, sess = self.setup_session()
            for p in s.segment_files(sess):
                p.unlink()
            self.assert_not_taken(self.finish(sb), sess)


if __name__ == "__main__":
    unittest.main()

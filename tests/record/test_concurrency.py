"""spec §4.4.2、§4.6.5、§4.7：錄製中與 finalize 中，場次不得被 meeting status／prep 列出。"""
import json
import os
import subprocess
import time
import unittest

from tests.record import _media as m
from tests.record._helpers import MEETING_SH, SLOW_FFMPEG, Sandbox

AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".mov", ".mp4", ".m4v")


def first_level_audio(sess):
    rec = sess / "錄音"
    return sorted(p.name for p in rec.iterdir() if p.is_file() and p.name.lower().endswith(AUDIO_EXTS))


def published(sess, audio):
    """spec §6 第 140 條：finalize.json 已有 finishedAt、且 outputs.audio 就是看到的音檔，才算已發佈（發佈後程序結束前的空窗不算違規）。"""
    try:
        fin = json.loads((sess / "錄音" / "tracks" / "finalize.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    out = os.path.basename(((fin.get("outputs") or {}).get("audio")) or "")
    return bool(fin.get("finishedAt")) and audio == [out]


class TestConcurrency(unittest.TestCase):
    # spec §4.4.2、§4.7.1：錄製中只有 tracks/ 與 meeting.json
    def test_recording_session_not_listed(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=1.0), dict(dur=1.0)])
        self.assertEqual(first_level_audio(sess), [])
        st = sb.meeting("status", sb.root)
        self.assertEqual(st.returncode, 0, st.stderr)
        self.assertNotIn(m.SESSION_NAME, st.stdout)
        prep = sb.meeting("prep", sb.root, timeout=120)
        self.assertEqual(prep.returncode, 3, "錄製中的場次不應被當成場次（prep 應找不到場次）")

    # spec §4.6.5、§4.7.2：finalize 期間（慢速 MH_FFMPEG）反覆跑 meeting.sh status
    def test_finalizing_session_not_listed(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=1.0), dict(dur=1.0)])
        env = sb.env(MH_FFMPEG=SLOW_FFMPEG, SLOW_FFMPEG_SECONDS="0.5")
        p = subprocess.Popen(["bash", str(MEETING_SH), "record", "finish", str(sess)],
                             cwd=str(sb.cwd), env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        polls, violations = 0, []
        deadline = time.monotonic() + 300
        while p.poll() is None and time.monotonic() < deadline:
            st = sb.meeting("status", sb.root)
            audio = first_level_audio(sess)
            if p.poll() is None and not published(sess, audio):
                polls += 1
                if m.SESSION_NAME in st.stdout:
                    violations.append("status 列出了 finalize 中的場次")
                if audio:
                    violations.append(f"錄音/ 第一層在 finalize 中出現音源檔：{audio}")
            time.sleep(0.2)
        out, err = p.communicate(timeout=60)
        self.assertEqual(p.returncode, 0, out + err)
        self.assertGreaterEqual(polls, 3, "finalize 期間應至少檢查 3 次（慢速 ffmpeg 替身沒有生效？）")
        self.assertEqual(violations, [])
        self.assertEqual(len(first_level_audio(sess)), 1)
        self.assertIn(m.SESSION_NAME, sb.meeting("status", sb.root).stdout, "finalize 完成後應列出場次")


if __name__ == "__main__":
    unittest.main()

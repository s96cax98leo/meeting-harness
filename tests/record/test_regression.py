"""迴歸與 verify：spec §4.12.4、§4.13.1、§4.13.2、§4.13.7、§4.15.14。"""
import json
import os
import re
import subprocess
import unittest

from tests.record._helpers import MEETING_SH
from tests.record.surface import REPO

RECORDER_WORDS = ("錄製器", "MeetingRecorder", "會議分頁標記")


def doctor_without_recorder():
    env = dict(os.environ)
    env["MH_RECORDER_APP"] = "/nonexistent/範例/MeetingRecorder.app"
    return subprocess.run(["bash", str(MEETING_SH), "doctor"], env=env, capture_output=True, text=True,
                          timeout=180)


class TestRegression(unittest.TestCase):
    # spec §4.13.1
    def test_lint_passes_26_files(self):
        r = subprocess.run(["bash", str(REPO / "bin" / "_lint.sh")], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        m = re.search(r"lint 通過（(\d+) 個檔）", r.stdout)
        self.assertIsNotNone(m, r.stdout)
        self.assertEqual(int(m.group(1)), 26)

    # spec §4.13.2
    def test_doctor_green_without_recorder(self):
        r = doctor_without_recorder()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.split("\n")
        rec = [l.strip() for l in lines if any(w in l for w in RECORDER_WORDS)]
        self.assertTrue(any("錄製器" in l and l.startswith("◦") for l in rec),
                        "沒有 app 時錄製器那一行應以「◦」開頭")
        self.assertFalse([l for l in rec if "✗" in l], "錄製器段不得出現「✗」")

    # spec §4.15.14
    def test_doctor_mentions_meeting_tab_marking(self):
        r = doctor_without_recorder()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        tab = [l.strip() for l in r.stdout.split("\n") if "會議分頁標記" in l]
        self.assertEqual(len(tab), 1, "錄製器段應恰有一行含「會議分頁標記」")
        self.assertTrue(tab[0].startswith("◦"))
        self.assertIn("Apple Events", tab[0])
        self.assertIn("選用", tab[0])

    # spec §4.12.4
    def test_diarize_and_merge_untouched(self):
        r = subprocess.run(["git", "-C", str(REPO), "diff", "--exit-code", "main", "--",
                            "bin/diarize.sh", "bin/_merge_speakers.py"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, "bin/diarize.sh、bin/_merge_speakers.py 應與 main 完全相同")

    # spec §4.13.7
    def test_git_governance_content(self):
        guard = json.loads((REPO / ".claude" / "teams" / "guard.config.json").read_text(encoding="utf-8"))
        self.assertEqual(guard.get("fork_repo"), "s96cax98leo/meeting-harness")
        wf = (REPO / "workflow.config").read_text(encoding="utf-8")
        self.assertRegex(wf, r"(?m)^FORK_REPO=[\"']?s96cax98leo/meeting-harness[\"']?\s*$")
        for f in ("CLAUDE.md", ".claude/teams/rules.md"):
            self.assertNotIn("沒有 remote", (REPO / f).read_text(encoding="utf-8"), f)
        for name in ("plan", "design", "design-revise", "build"):
            src = (REPO / ".claude" / "workflows" / f"sdlc-{name}.js").read_text(encoding="utf-8")
            trailers = re.findall(r"Co-Authored-By: [^<\n]*<[^>\n]*>", src)
            self.assertTrue(trailers, f"sdlc-{name}.js 應有署名行")
            for t in trailers:
                self.assertEqual(t.strip(), "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>",
                                 f"sdlc-{name}.js")


if __name__ == "__main__":
    unittest.main()

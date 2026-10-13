"""spec §3.7、§4.1.9：bin/_record_estimate.py 的公式與共用。"""
import re
import subprocess
import sys
import unittest
from fractions import Fraction
from math import ceil

from tests.record._helpers import BIN, MEETING_SH, RECORD_SH

EST = BIN / "_record_estimate.py"


def expected(minutes):
    # spec §3.7：ceil(N × (4 × 56,000,000 ＋ 1,920,000)) ＋ 2,000,000,000
    return ceil(Fraction(minutes) * (4 * 56_000_000 + 1_920_000)) + 2_000_000_000


def run(*args):
    return subprocess.run([sys.executable, str(EST), *args], capture_output=True, text=True, timeout=30)


class TestEstimate(unittest.TestCase):
    def test_formula(self):
        self.assertTrue(EST.is_file(), f"{EST} 不存在")
        for n in ("1", "120", "0.5", "7.3", "90"):
            with self.subTest(minutes=n):
                r = run("--minutes", n)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.strip().split("\n")[0].strip(), str(expected(n)))
        # 120 分鐘約 29.1 GB（spec §7 疑慮 8）
        self.assertEqual(expected("120"), 29_110_400_000)
        r = run("--minutes", "120", "--human")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(expected("120")), r.stdout)
        self.assertRegex(r.stdout, r"約 \d+\.\d GB")
        self.assertIn("約 29.1 GB", r.stdout)
        for bad in ("0", "-3", "abc"):
            with self.subTest(bad=bad):
                self.assertEqual(run("--minutes", bad).returncode, 2, f"N={bad} 應回 2")

    def test_shared_by_doctor_and_record_sh(self):
        sh = MEETING_SH.read_text(encoding="utf-8")
        m = re.search(r"^doctor\(\) \{\n(.*?)^\}", sh, re.S | re.M)
        self.assertIsNotNone(m, "bin/meeting.sh 找不到 doctor()")
        self.assertIn("_record_estimate.py", m.group(1), "doctor() 的錄製器段應呼叫 _record_estimate.py")
        self.assertTrue(RECORD_SH.is_file(), f"{RECORD_SH} 不存在")
        rec = RECORD_SH.read_text(encoding="utf-8")
        self.assertIn("_record_estimate.py", rec)
        self.assertIn("--min-free-bytes", rec)


if __name__ == "__main__":
    unittest.main()

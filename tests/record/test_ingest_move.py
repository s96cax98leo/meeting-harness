"""meeting ingest（bin/_scaffold.py）改為移動：原處不再留一份（使用者 2026-10-13 要求；spec §6 第 110 條）。"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.record.surface import REPO

SCAFFOLD = REPO / "bin" / "_scaffold.py"


def run(root, *flags):
    return subprocess.run([sys.executable, str(SCAFFOLD), str(root), *flags],
                          capture_output=True, text=True, timeout=120)


class IngestMove(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "20261013"
        self.root.mkdir()
        self.audio = self.root / "錄音 2026-10-13 09.00.00.m4a"
        self.audio.write_bytes(b"\0" * 4096)
        self.shot = self.root / "截圖 2026-10-13 09.05.00.png"
        self.shot.write_bytes(b"\x89PNG" + b"\0" * 100)

    def tearDown(self):
        self.tmp.cleanup()

    def test_moves_not_links(self):
        r = run(self.root, "--split")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.audio.exists(), "原檔應被移走，原處不得再留一份")
        self.assertFalse(self.shot.exists(), "截圖也應被移走")
        moved = list(self.root.glob("*/錄音/*.m4a"))
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0].stat().st_nlink, 1, "不得是硬連結")
        self.assertEqual(moved[0].stat().st_size, 4096)
        self.assertEqual(len(list(self.root.glob("*/照片/*.png"))), 1)
        self.assertIn("move", r.stdout)

    def test_dry_run_touches_nothing(self):
        before = sorted(p.name for p in self.root.iterdir())
        r = run(self.root, "--split", "--dry-run")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), before)
        self.assertIn("would-move", r.stdout)

    def test_existing_destination_is_skipped_not_overwritten(self):
        run(self.root, "--split")
        sess = next(self.root.glob("*/錄音")).parent
        # 同名檔再出現在原處：目的地已有 → 跳過、兩邊都不動
        self.audio.write_bytes(b"\1" * 10)
        r = run(self.root, "--split")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(self.audio.exists(), "目的地已有同名檔時原檔不得被刪")
        self.assertEqual((sess / "錄音" / self.audio.name).stat().st_size, 4096, "不得覆蓋目的地")


if __name__ == "__main__":
    unittest.main()

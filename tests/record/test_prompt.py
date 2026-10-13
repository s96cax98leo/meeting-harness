"""spec §3.7、§4.1.8、§4.15.12：bin/_record_prompt.py 的問答與輸出。"""
import ast
import json
import sys
import unittest

from tests.record import _fixtures as fx
from tests.record._helpers import (BIN, EOF, PromptResponder, drive_pipes, snapshot, tmpdir)

PROMPT = BIN / "_record_prompt.py"
OUT_KEYS = {"root", "session", "type", "attendees", "windowID", "bundleID", "title"}


def profiles():
    sys.path.insert(0, str(BIN))
    try:
        import importlib
        mod = importlib.import_module("_profile")
        return list(mod.PROFILES)
    finally:
        sys.path.remove(str(BIN))


class TestRecordPrompt(unittest.TestCase):
    def setUp(self):
        self.assertTrue(PROMPT.is_file(), f"{PROMPT} 不存在")

    def _run(self, rows, window_answers):
        d = tmpdir(self)
        root = d / "範例根"
        root.mkdir()
        wj = d / "windows.json"
        wj.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        dj = d / "record.defaults.json"
        dj.write_text(json.dumps({"root": str(root), "type": "internal", "attendees": []}, ensure_ascii=False),
                      encoding="utf-8")
        before = snapshot(d)
        resp = PromptResponder([r["label"] for r in rows], window_answers, root=root)
        rc, out, err = drive_pipes([sys.executable, PROMPT, "--windows-json", wj, "--defaults", dj],
                                   env=None, cwd=d, responder=resp, timeout=60)
        return rc, out, err, before, snapshot(d), resp

    def _json_line(self, out):
        lines = [l for l in out.split("\n") if l.strip()]
        self.assertEqual(len(lines), 1, f"stdout 應恰好一行 JSON，實際：{out!r}")
        return json.loads(lines[0])

    # spec §4.1.8
    def test_prompt_prints_json_and_writes_nothing(self):
        rc, out, err, before, after, _ = self._run(fx.WINDOWS_WITH_STAR, ["\n"])
        self.assertEqual(rc, 0, err)
        self.assertTrue(err.strip(), "問答提示應印到 stderr")
        data = self._json_line(out)
        self.assertEqual(set(data), OUT_KEYS)
        self.assertEqual(before, after, "執行前後暫存目錄內不得新增或修改任何檔")

    # spec §4.1.8：型態選項＝bin/_profile.py 的 PROFILES 鍵（以 import 取得）
    def test_prompt_types_come_from_profiles(self):
        rc, out, err, *_ = self._run(fx.WINDOWS_WITH_STAR, ["\n"])
        self.assertEqual(rc, 0, err)
        for t in profiles():
            self.assertIn(t, err, f"型態選項應含 {t}")
        src = PROMPT.read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = any(isinstance(n, ast.ImportFrom) and n.module == "_profile"
                       and any(a.name == "PROFILES" for a in n.names) for n in ast.walk(tree))
        self.assertTrue(imported, "_record_prompt.py 應 from _profile import PROFILES")
        hard = [t for t in profiles() if f'"{t}"' in src or f"'{t}'" in src]
        self.assertEqual(hard, [], "不得另抄型態清單")

    # spec §4.15.12 (a)
    def test_prompt_window_menu_labels_and_default(self):
        rows = fx.WINDOWS_WITH_STAR
        rc, out, err, _, _, resp = self._run(rows, ["\n"])
        self.assertEqual(rc, 0, err)
        pos = []
        for i, r in enumerate(rows, start=1):
            entry = f"{i}) {r['label']}"
            self.assertIn(entry, err, f"選單應逐字列出「{entry}」")
            pos.append(err.index(entry))
        self.assertEqual(pos, sorted(pos), "選單順序應同 --windows-json 陣列")
        first_star = next(i for i, r in enumerate(rows, start=1) if r["meeting"] is not None)
        self.assertIn(f"[預設 {first_star}]", err)
        data = self._json_line(out)
        self.assertEqual(data["windowID"], rows[first_star - 1]["windowID"], "只送 Enter 應選中預設的 ★ 列")

    # spec §4.15.12 (b)
    def test_prompt_no_default_without_meeting(self):
        rc, out, err, _, _, resp = self._run(fx.WINDOWS_NO_STAR, ["\n", EOF])
        self.assertGreaterEqual(len(resp.window_prompts), 2, "沒有 ★ 時只送 Enter 應重問")
        for w in resp.window_prompts:
            self.assertNotIn("預設", w.split(fx.WINDOWS_NO_STAR[-1]["label"])[-1],
                             "沒有 ★ 列時視窗提示不得有預設")
        self.assertEqual(rc, 2, "EOF 應回 2")
        self.assertEqual(out.strip(), "")

    # spec §4.15.12 (c)(d)
    def test_prompt_outputs_window_identity(self):
        rows = fx.WINDOWS_WITH_STAR
        rc, out, err, *_ = self._run(rows, ["3\n"])
        self.assertEqual(rc, 0, err)
        self.assertIn("自動化", err)
        self.assertIn("不允許也能錄", err)
        data = self._json_line(out)
        pick = rows[2]
        self.assertEqual((data["windowID"], data["bundleID"], data["title"]),
                         (pick["windowID"], pick["bundleID"], pick["title"]))


if __name__ == "__main__":
    unittest.main()

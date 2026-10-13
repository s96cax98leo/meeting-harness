"""meeting search 與 meeting sync（spec §4.33.1–§4.33.4、§4.37.1、§4.45.1；R3-§2.2、§3.19）。

場次目錄名一律日期在前（例 20261012-範例專案）；素材只在 TMPDIR。
輸出每行：<場次相對 <根> 的路徑>/<檔名>:<行號>: <該行>。<檔名> 是否帶「錄音/」spec 未明寫，本檔兩種都接受。
"""
import json
import os
import re
import unittest
from pathlib import Path

from tests.record._helpers import Sandbox

HIT_RE = re.compile(r"^(?P<sess>[^/]+(?:/[^/]+)*?)/(?P<file>(?:錄音/)?(?:summary\.md|transcript\.speakers\.md|"
                    r"transcript\.raw\.md|meeting\.record\.json)):(?P<line>\d+): (?P<text>.*)$")
SEARCH_FILES = ("summary.md", "錄音/transcript.speakers.md", "錄音/transcript.raw.md", "meeting.record.json")
LONG = "Stand-up 範例專案長行：" + "範例內容" * 40


def write(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def make_session(root, name, *, keyword_lines=True, long_line=False):
    sess = Path(root) / name
    body = "\n".join(["# 範例紀錄", "", "今天的 stand-up 範例專案進度", "沒有關鍵字的行"])
    if long_line:
        body += "\n" + LONG
    for f in SEARCH_FILES:
        if f.endswith(".json"):
            write(sess / f, json.dumps({"meeting": {"title": "[Stand-up] 範例專案" if keyword_lines else "範例"}},
                                       ensure_ascii=False, indent=2))
        else:
            write(sess / f, body if keyword_lines else "# 範例\n沒有關鍵字\n")
    write(sess / "錄音" / "notes.txt", "stand-up 不在搜尋範圍的檔\n")
    return sess


def parse(tc, stdout):
    hits = []
    for ln in stdout.splitlines():
        mm = HIT_RE.match(ln)
        tc.assertIsNotNone(mm, f"輸出格式不符 §3.19：{ln!r}")
        hits.append(mm.groupdict())
    return hits


def other_commands_section(text):
    lines = text.splitlines()
    i = next(k for k, ln in enumerate(lines) if ln.strip() == "其他指令")
    j = next(k for k, ln in enumerate(lines) if k > i and ln.startswith("錄製（meeting record"))
    return lines[i + 1:j]


class TestR3Search(unittest.TestCase):
    # spec §4.33.1：兩個場次都有 → 0；新的在前；同場次依檔名、行號；大小寫不分；.* 照字面；超過 120 字截斷加「…」
    def test_hits_sorted_and_literal(self):
        sb = Sandbox(self)
        make_session(sb.root, "20261010-範例專案")
        make_session(sb.root, "20261012-範例專案", long_line=True)
        r = sb.meeting("search", sb.root, "Stand-up")
        self.assertEqual(r.returncode, 0, r.stderr)
        hits = parse(self, r.stdout)
        sessions = [h["sess"] for h in hits]
        self.assertEqual(sorted(set(sessions)), ["20261010-範例專案", "20261012-範例專案"])
        first_old = sessions.index("20261010-範例專案")
        self.assertTrue(all(s == "20261012-範例專案" for s in sessions[:first_old]), "較新的場次在前")
        self.assertTrue(all(s == "20261010-範例專案" for s in sessions[first_old:]))
        for s in set(sessions):
            keys = [(h["file"], int(h["line"])) for h in hits if h["sess"] == s]
            self.assertEqual(keys, sorted(keys), f"{s}：同場次依檔名、行號遞增")
            self.assertEqual({k[0].split("/")[-1] for k in keys},
                             {"summary.md", "transcript.speakers.md", "transcript.raw.md", "meeting.record.json"},
                             "四種檔都要搜到")
        self.assertTrue(any("stand-up" in h["text"] for h in hits), "大小寫不分（Stand-up 搜得到 stand-up）")
        self.assertNotIn("notes.txt", r.stdout, "只搜四種檔")
        longs = [h["text"] for h in hits if h["text"].startswith("Stand-up 範例專案長行")]
        self.assertTrue(longs, "長行也要搜到")
        for t in longs:
            self.assertEqual(t, LONG[:120] + "…", "超過 120 字截斷加「…」")
        # .* 照字面比對
        write(sb.root / "20261011-範例專案" / "summary.md", "範例 a.*b 字面\n範例 axxb 不得被比對\n")
        r = sb.meeting("search", sb.root, "a.*b")
        self.assertEqual(r.returncode, 0, r.stderr)
        hits = parse(self, r.stdout)
        self.assertEqual([h["text"] for h in hits], ["範例 a.*b 字面"])

    # spec §4.33.2：沒有結果 1、stdout 空；缺參數或根目錄不存在 2
    def test_exit_codes(self):
        sb = Sandbox(self)
        make_session(sb.root, "20261012-範例專案")
        r = sb.meeting("search", sb.root, "不會出現的關鍵字範例")
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(r.stdout, "")
        for args in ((), (str(sb.root),), (str(sb.base / "不存在的根"), "範例")):
            with self.subTest(args=args):
                r = sb.meeting("search", *args)
                self.assertEqual(r.returncode, 2, f"stdout:{r.stdout}\nstderr:{r.stderr}")

    # spec §4.33.3：不讀根目錄以外的檔（symlink 進根目錄的檔與目錄都不得出現）
    def test_single_root_only(self):
        sb = Sandbox(self)
        make_session(sb.root, "20261012-範例專案")
        outside = sb.base / "根目錄外"
        make_session(outside, "20261013-外部場次")
        write(outside / "外部.md", "stand-up 根目錄外的唯一字串\n")
        linked = sb.root / "20261011-範例連結"
        linked.mkdir()
        os.symlink(outside / "外部.md", linked / "summary.md")
        os.symlink(outside / "20261013-外部場次", sb.root / "20261014-外部連結")
        r = sb.meeting("search", sb.root, "stand-up")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("根目錄外的唯一字串", r.stdout)
        self.assertNotIn("20261014-外部連結", r.stdout)
        self.assertNotIn("20261011-範例連結", r.stdout)
        self.assertTrue(all(h["sess"] == "20261012-範例專案" for h in parse(self, r.stdout)))

    # spec §4.33.4、§4.45.1：help 的其他指令段列出 search
    def test_usage_lists_search(self):
        sb = Sandbox(self)
        r = sb.meeting("help")
        self.assertEqual(r.returncode, 0)
        sec = other_commands_section(r.stdout)
        self.assertTrue(any(ln.strip().startswith("meeting search ") for ln in sec), "其他指令段應列出 meeting search")

    # spec §4.37.1：meeting sync 印模式、合併寫入、錯值與壞檔回 2 且檔案不變；help 的其他指令段列出 sync
    def test_meeting_sync_cli(self):
        sb = Sandbox(self)
        path = sb.home / "record.defaults.json"
        r = sb.meeting("sync")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "syncCompensation=off")
        seven = {"root": "/範例/根", "type": "internal", "attendees": ["範例甲"], "harness": "/範例/harness",
                 "python3": "/usr/bin/python3", "ffmpeg": "/usr/bin/ffmpeg", "minFreeBytes": 123, "x": {"y": 1}}
        path.write_text(json.dumps(seven, ensure_ascii=False), encoding="utf-8")
        r = sb.meeting("sync", "reported")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "syncCompensation=reported（下一次收尾起生效）")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), dict(seven, syncCompensation="reported"))
        r = sb.meeting("sync")
        self.assertEqual(r.stdout.strip(), "syncCompensation=reported")
        before = path.read_bytes()
        for args in (("foo",), ("off", "reported")):
            with self.subTest(args=args):
                r = sb.meeting("sync", *args)
                self.assertEqual(r.returncode, 2)
                self.assertEqual(path.read_bytes(), before, "錯值時檔案不變")
        path.write_text("[1, 2]", encoding="utf-8")
        before = path.read_bytes()
        r = sb.meeting("sync", "calibrated")
        self.assertEqual(r.returncode, 2, "record.defaults.json 不是 JSON 物件時回 2")
        self.assertEqual(path.read_bytes(), before)
        sec = other_commands_section(sb.meeting("help").stdout)
        self.assertTrue(any(ln.strip().startswith("meeting sync") for ln in sec), "其他指令段應列出 meeting sync")


if __name__ == "__main__":
    unittest.main()

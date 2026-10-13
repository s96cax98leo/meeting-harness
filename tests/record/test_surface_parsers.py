"""spec §2.4.3–2.4.8：surface.py 的解析器與參數組法本身（紅燈階段就要綠）。"""
import re
import unittest

from tests.record.surface import (
    BLOCK_BEGIN, BLOCK_END, MEETING_SH, REPO, SURFACE, SurfaceParseError,
    form_argv, parse_block, parse_help, parse_usage,
)

SPEC = REPO / "specs" / "meeting-record" / "spec.md"


def spec_help_example():
    """spec §2.4.3 的範例區塊，原樣取出。"""
    text = SPEC.read_text(encoding="utf-8")
    anchor = text.index("範例（結構是規範")
    m = re.compile(r"```\n(.*?)```", re.S).search(text, anchor)
    return m.group(1)


VALID_BLOCK = f"""前言

{BLOCK_BEGIN}
| 寫法 | 旗標 | 結束碼 |
|---|---|---|
| `meeting record [<根>]` | `--window <id>` | 0 2 3 4 5 |
| `meeting record windows` | `--json` | 0 2 4 |
| `meeting record preflight` | `--window <id>` | 0 2 3 4 |
| `meeting record stop` | — | 0 3 5 |
| `meeting record status` | — | 0 5 |
| `meeting record finish <場次>` | — | 0 2 3 5 |
| `meeting record help` | — | 0 |
{BLOCK_END}

層旗標 `--recorder`、`--yes` 寫在區塊外。
"""

VALID_USAGE = """meeting — 說明

其他指令
  meeting status <會議根目錄>          顯示每場的流水線狀態與產物

錄製（meeting record；完整說明：meeting record help）
  meeting record [<根>]          開始錄製
  meeting record windows         列出可錄的視窗
  meeting record preflight       只跑開錄前檢查
  meeting record stop            停止並收尾
  meeting record status          看錄製狀態
  meeting record finish <場次>   補做收尾
  meeting record help            完整說明
  層旗標：--recorder（明確要錄製）、--yes（沒有人可問）
  結束碼：0 成功、2 參數、3 找不到、4 檢查失敗、5 錄製出錯

常用環境變數
"""


class TestSurfaceParsers(unittest.TestCase):
    def test_surface_constant_shape(self):
        # spec §2.4.2：7 個寫法、3 組寫法旗標、22 組結束碼
        self.assertEqual(len(SURFACE.forms), 7)
        self.assertEqual(len(SURFACE.form_flags), 3)
        self.assertEqual(len(SURFACE.form_codes), 22)
        self.assertEqual(SURFACE.layer_flags, ["--recorder", "--yes"])
        self.assertEqual(SURFACE.codes, [0, 2, 3, 4, 5])
        self.assertEqual({c for f, c in SURFACE.form_codes if f == "meeting record status"}, {0, 5})

    def test_parse_help_accepts_spec_example(self):
        got = parse_help(spec_help_example())
        for k in ("forms", "layer_flags", "codes"):
            self.assertEqual(got[k], SURFACE[k], k)
        for k in ("form_flags", "form_codes"):
            self.assertEqual(set(got[k]), set(SURFACE[k]), k)

    def _mutate(self, old, new, count=1):
        text = spec_help_example()
        self.assertIn(old, text)
        return text.replace(old, new, count)

    def test_parse_help_rejects_grammar_errors(self):
        ex = spec_help_example()
        bad = {
            "段頭缺漏": self._mutate("\n旗標：\n", "\n旗標\n"),
            "段頭重複": ex + "\n寫法：\n",
            "段頭順序錯": self._mutate("寫法：", "XX").replace("旗標：", "寫法：", 1).replace("XX", "旗標：", 1),
            "欄位數錯": self._mutate("  meeting record stop            結束碼 0 3 5",
                                  "  meeting record stop  多一欄  結束碼 0 3 5"),
            "結束碼欄格式錯": self._mutate("結束碼 0 2 4", "結束碼 0,2,4"),
            "結束碼未遞增": self._mutate("結束碼 0 2 4", "結束碼 0 4 2"),
            "層旗標出現在旗標段": self._mutate("  meeting record windows         --json",
                                        "  meeting record windows         --json\n  meeting record windows         --recorder"),
            "旗標段第 1 欄不在 forms": self._mutate("  meeting record windows         --json",
                                             "  meeting record bogus           --json"),
            "結束碼段第 1 欄非數字": self._mutate("  0  成功", "  零  成功"),
        }
        for why, text in bad.items():
            with self.subTest(why=why):
                with self.assertRaises(SurfaceParseError) as cm:
                    parse_help(text)
                if why not in ("段頭缺漏", "段頭順序錯"):
                    self.assertRegex(str(cm.exception), r"第 \d+ 行")

    def test_parse_help_field_separator_two_spaces(self):
        # 欄位分隔＝兩個以上半形空白；單一空白不切
        got = parse_help(spec_help_example())
        self.assertIn("meeting record finish <場次>", got.forms)

    def test_parse_block_and_usage(self):
        b = parse_block(VALID_BLOCK)
        self.assertEqual(b.forms, SURFACE.forms)
        self.assertEqual(b.form_flags, SURFACE.form_flags)
        self.assertEqual(b.form_codes, SURFACE.form_codes)
        u = parse_usage(VALID_USAGE)
        self.assertEqual(u.forms, SURFACE.forms)
        # 區塊錯誤：begin 兩次、表頭錯、結束碼格式錯
        with self.assertRaises(SurfaceParseError):
            parse_block(VALID_BLOCK + "\n" + BLOCK_BEGIN + "\n")
        with self.assertRaises(SurfaceParseError):
            parse_block(VALID_BLOCK.replace("| 寫法 | 旗標 | 結束碼 |", "| 寫法 | 結束碼 |"))
        with self.assertRaises(SurfaceParseError):
            parse_block(VALID_BLOCK.replace("| 0 2 4 |", "| 0,2,4 |"))
        # 不在 record 段、但以 "  meeting record" 開頭以外的行不收
        self.assertEqual(parse_usage("  meeting status x  說明\n").forms, [])
        # 行尾沒有說明欄時取到行尾
        self.assertEqual(parse_usage("  meeting record help\n").forms, ["meeting record help"])

    def test_form_argv(self):
        root, sess = "/tmp/範例根", "/tmp/範例根/20261011/範例場次"
        sh = ["bash", MEETING_SH, "record"]
        self.assertEqual(form_argv("meeting record [<根>]", root=root, session=sess), sh + [root])
        self.assertEqual(form_argv("meeting record [<根>]", root=root, session=sess, form_flag="--window <id>"),
                         sh + [root, "--window", "1"])
        self.assertEqual(form_argv("meeting record windows", root=root, session=sess, form_flag="--json"),
                         sh + ["windows", "--json"])
        self.assertEqual(form_argv("meeting record finish <場次>", root=root, session=sess), sh + ["finish", sess])
        self.assertEqual(form_argv("meeting record stop", root=None, session=None, layer_flag="--recorder"),
                         ["bash", MEETING_SH, "record", "--recorder", "stop"])
        self.assertEqual(form_argv("meeting record preflight", root=None, session=None, layer_flag="--yes",
                                   form_flag="--window <id>", extra=["--no-such-flag"]),
                         ["bash", MEETING_SH, "record", "--yes", "preflight", "--window", "1", "--no-such-flag"])
        self.assertEqual(form_argv("meeting record help", root=None, session=None, extra="--no-such-flag"),
                         sh + ["help", "--no-such-flag"])
        for form in SURFACE.forms:
            with self.subTest(form=form):
                argv = form_argv(form, root=root, session=sess, extra=["--no-such-flag"])
                self.assertEqual(argv[:3], sh)
                self.assertEqual(argv[-1], "--no-such-flag")
        with self.assertRaises(ValueError):
            form_argv("meeting record stop", root=None, session=None, layer_flag="--bogus")
        with self.assertRaises(ValueError):
            form_argv("meeting record [<根>]", root=None, session=None)


if __name__ == "__main__":
    unittest.main()

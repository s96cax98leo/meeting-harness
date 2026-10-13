"""文件與實作一致性（D13；spec §4.3.5、§4.8.3、§4.11.4、§4.12）：以 surface.py 比對，不另抄清單。"""
import re
import subprocess
import unittest

from tests.record import _fixtures as fx
from tests.record._helpers import MEETING_SH, UNKNOWN_OPTION, Sandbox
from tests.record.surface import (REPO, SURFACE, assert_component_equal, extract_block, form_argv, parse_block,
                                  parse_help)
from tests.record.test_record_sh import EXIT_CODE_CASES, run_exit_case

SKILL = REPO / ".claude" / "skills" / "meeting-record" / "SKILL.md"
SUMMARY_SKILL = REPO / ".claude" / "skills" / "meeting-summary" / "SKILL.md"
README = REPO / "README.md"
MAIN_SWIFT = REPO / "tools" / "MeetingRecorder" / "Sources" / "main.swift"
SUBCOMMANDS = {"windows", "preflight", "stop", "status", "finish", "help"}
ALLOWED_FLAGS = {"--window", "--json", "--recorder", "--yes", "--help"}
SERVICES = ["M+ Meet", "Google Meet", "Teams", "Zoom", "Webex", "騰訊會議"]
CRASH_LOSS = "最後一段未收尾的 1 分鐘會丟"
SHORTCUT = "open -n -a MeetingRecorder --args quick-start"


def read(tc, path):
    tc.assertTrue(path.is_file(), f"{path.relative_to(REPO)} 不存在")
    return path.read_text(encoding="utf-8")


def frontmatter(text):
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return None
    end = lines.index("---", 1)
    return "\n".join(lines[:end + 1])


def sections(text):
    """依 markdown 標題切段：[(標題, 內文)]。"""
    out, head, buf = [], "", []
    for line in text.split("\n"):
        if re.match(r"^#{1,6} ", line):
            out.append((head, "\n".join(buf)))
            head, buf = line, []
        else:
            buf.append(line)
    out.append((head, "\n".join(buf)))
    return out


def outside_block(text):
    b = text.split("<!-- record-cli:begin -->")
    if len(b) != 2:
        return text
    return b[0] + b[1].split("<!-- record-cli:end -->", 1)[-1]


def paragraphs(text):
    """以空白行切段落（markdown 段落、引言區塊各算一段）。"""
    return [p for p in re.split(r"\n\s*\n", text) if p.strip()]


def record_section(text):
    """README 的「## 錄製會議」段（到下一個 ## 標題為止）；找不到回 None。"""
    m = re.search(r"(?m)^## 錄製會議.*$", text)
    if not m:
        return None
    nxt = re.search(r"(?m)^## ", text[m.end():])
    return text[m.end():m.end() + nxt.start()] if nxt else text[m.end():]


def record_help_stdout(tc):
    sb = Sandbox(tc)
    r = sb.meeting("record", "help")
    tc.assertEqual(r.returncode, 0, r.stderr)
    return r.stdout


class TestDocs(unittest.TestCase):
    # spec §4.12.1
    def test_skill_exists_and_sections(self):
        text = read(self, SKILL)
        fm = frontmatter(text)
        self.assertIsNotNone(fm, "SKILL.md 應有 frontmatter")
        self.assertRegex(fm, r"(?m)^name: meeting-record$")
        for must in ("meeting record", "preflight", "meeting record stop", "meeting record finish",
                     "錄音/", "影片/", "tracks/", "--recorder", "prep ./record"):
            self.assertIn(must, text, f"SKILL.md 應涵蓋「{must}」")
        self.assertTrue("重開" in text or "重啟" in text, "preflight 失敗的補救應含重啟")

    # spec §4.12.2
    def test_meeting_summary_frontmatter_unchanged(self):
        text = read(self, SUMMARY_SKILL)
        main = subprocess.run(["git", "-C", str(REPO), "show", "main:.claude/skills/meeting-summary/SKILL.md"],
                              capture_output=True, text=True, check=True).stdout
        self.assertEqual(frontmatter(text), frontmatter(main), "frontmatter 應與 main 相同")
        body = text[len(frontmatter(text)):]
        self.assertIn("meeting-record", body, "正文應有一行指向 meeting-record")

    # spec §4.12.3
    def test_readme_updated(self):
        text = read(self, README)
        for form in SURFACE.forms:
            self.assertIn(form.replace(" [<根>]", "").replace(" <場次>", ""), text)
        outside = outside_block(text)
        code_lines = "\n".join(l for l in outside.split("\n") if "結束碼" in l)
        self.assertIn("4", code_lines, "結束碼說明應含 4")
        self.assertIn("5", code_lines, "結束碼說明應含 5")
        loops = [l for l in text.split("\n") if l.startswith("for s in ") and "meeting-summary" in l]
        self.assertTrue(loops, "README 應有重裝 skill 的 for-loop")
        self.assertTrue(all("meeting-record" in l for l in loops), "重裝 for-loop 應含 meeting-record")
        self.assertTrue(any(l.startswith("|") and "meeting-record" in l for l in text.split("\n")),
                        "skill 表應有 meeting-record 一列")
        tree = [l for l in text.split("\n") if "skills/" in l and "#" in l and "個 skill" in l]
        self.assertTrue(tree and all("7 個 skill" in l for l in tree), "目錄樹註解應寫 7 個 skill")

    # spec §4.8.3（SKILL.md 的 finish 段）
    def test_crash_loss_documented(self):
        text = read(self, SKILL)
        self.assertIn(CRASH_LOSS, text)
        self.assertTrue(any("record finish" in (h + body) and CRASH_LOSS in body for h, body in sections(text)),
                        "finish 那一段應寫明最後一段未收尾的 1 分鐘會丟")

    # spec §4.11.4
    def test_shortcuts_instruction(self):
        text = read(self, SKILL)
        self.assertTrue("Shortcuts" in text or "捷徑" in text)
        blocks = re.findall(r"```[^\n]*\n(.*?)```", text, re.S)
        only = [b for b in blocks if [l.strip() for l in b.split("\n") if l.strip()] == [SHORTCUT]]
        self.assertTrue(only, f"捷徑內容應僅為一行：{SHORTCUT}")

    # spec §4.12.6
    def test_docs_cli_block_matches_spec(self):
        texts = {p.name: read(self, p) for p in (SKILL, README)}
        blocks = {n: extract_block(t) for n, t in texts.items()}
        self.assertEqual(blocks["SKILL.md"].encode("utf-8"), blocks["README.md"].encode("utf-8"),
                         "兩份文件 record-cli 區塊內容應逐位元組相同")
        for n, t in texts.items():
            got = parse_block(t)
            for k in ("forms", "form_flags", "form_codes"):
                assert_component_equal(self, f"{n} {k}", got[k], SURFACE[k])
            out = outside_block(t)
            for lf in SURFACE.layer_flags:
                self.assertIn(lf, out, f"{n} 區塊外應提到 {lf}")
            for i, line in enumerate(t.split("\n"), start=1):
                clean = line.replace("`", "")
                occ = list(re.finditer(r"meeting(?:\.sh)? record(?: +(\S+))?", clean))
                if not occ:
                    continue
                for mo in occ:
                    w = mo.group(1)
                    if w and "/" not in w:
                        lead = re.match(r"[a-z]+", w)
                        if lead:
                            self.assertIn(lead.group(0), SUBCOMMANDS, f"{n}:{i} 出現 spec 沒有的寫法：{line}")
                for fl in re.findall(r"--[a-z][a-z-]*", clean):
                    self.assertIn(fl, ALLOWED_FLAGS, f"{n}:{i} 出現 spec 沒有的旗標 {fl}：{line}")

    # spec §4.12.7
    def test_docs_cli_block_matches_help(self):
        got = parse_help(record_help_stdout(self))
        for p in (SKILL, README):
            doc = parse_block(read(self, p))
            for k in ("forms", "form_flags", "form_codes"):
                assert_component_equal(self, f"help vs {p.name} {k}", got[k], doc[k])
        assert_component_equal(self, "layer_flags", got.layer_flags, SURFACE.layer_flags)
        assert_component_equal(self, "codes", got.codes, SURFACE.codes)

    # spec §4.12.8 (a)(b)
    def test_docs_flags_match_behavior(self):
        doc = parse_block(read(self, SKILL))
        runs = [(form, fl, None) for form, fl in sorted(doc.form_flags)]
        runs += [(form, None, lf) for form in doc.forms for lf in SURFACE.layer_flags]
        self.assertEqual(len(runs), 17)
        for form, fl, lf in runs:
            with self.subTest(form=form, flag=fl, layer=lf):
                sb = Sandbox(self, windows=fx.WINDOWS_WITH_STAR)
                session = sb.root / "20261011" / "範例場次"
                (session / "錄音").mkdir(parents=True)
                r = sb.run(form_argv(form, root=sb.root, session=session, form_flag=fl, layer_flag=lf,
                                     meeting_sh=str(MEETING_SH)), timeout=180)
                self.assertNotIn(UNKNOWN_OPTION, r.stderr)
        for form in doc.forms:
            with self.subTest(form=form, flag="--no-such-flag"):
                sb = Sandbox(self, windows=fx.WINDOWS_WITH_STAR)
                session = sb.root / "20261011" / "範例場次"
                (session / "錄音").mkdir(parents=True)
                r = sb.run(form_argv(form, root=sb.root, session=session, extra=["--no-such-flag"],
                                     meeting_sh=str(MEETING_SH)))
                self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
                self.assertIn(UNKNOWN_OPTION, r.stderr)

    # spec §4.12.8 (c)
    def test_docs_exit_codes_match_behavior(self):
        doc = parse_block(read(self, SKILL))
        assert_component_equal(self, "EXIT_CODE_CASES vs SKILL.md form_codes",
                               {(c["form"], c["expect"]) for c in EXIT_CODE_CASES}, doc.form_codes)
        for c in EXIT_CODE_CASES:
            with self.subTest(form=c["form"], setup=c["setup"], scenario=c["scenario"], args=c["extra_args"]):
                r = run_exit_case(self, c)
                self.assertEqual(r.returncode, c["expect"], r.stdout + r.stderr)

    # spec §4.12.9
    def test_docs_app_args_exist_in_sources(self):
        text = read(self, SKILL)
        subs = set(re.findall(r"--args\s+([a-z][a-z-]*)", text.replace("`", "")))
        self.assertTrue(subs, "SKILL.md 應至少寫到一個 --args <子指令>（quick-start）")
        self.assertIn("quick-start", subs)
        src = read(self, MAIN_SWIFT)
        cases = set()
        for m in re.finditer(r"(?m)^\s*case\s+((?:\"[^\"]*\"\s*,?\s*)+):", src):
            cases.update(re.findall(r"\"([^\"]*)\"", m.group(1)))
        missing = sorted(subs - cases)
        self.assertEqual(missing, [], f"SKILL.md 的 --args 子指令不在 main.swift 的 dispatch：{missing}")

    # spec §4.12.10、§4.15.15
    def test_meeting_tab_marking_documented(self):
        text = read(self, SKILL)
        self.assertIn("★ 會議（", text)  # (a)
        for s in SERVICES:
            self.assertIn(s, text, f"應列出服務名 {s}")
        for s in ("Apple Events", "選用", "允許控制 Google Chrome", "自動化"):  # (b)
            self.assertIn(s, text)
        self.assertIn("不授權也能錄", text)  # (c)
        self.assertIn("quick-start", text)
        self.assertIn("唯一", text, "應說明 quick-start 可能因此找不到唯一的會議視窗")
        self.assertIn("作用中分頁", text)  # (d)
        self.assertIn("--args diagnose-windows", text.replace("`", ""))  # (e)
        self.assertNotIn("不要用 native 全螢幕", text)  # (f)
        readme = read(self, README)
        self.assertIn("會議視窗標記", readme, "README 錄製段應有一行指向 SKILL.md 的會議視窗標記說明")


    # spec §4.3.5（D19）：錄到的系統聲音範圍。判準：SKILL.md 有一個段落同時寫明「系統聲音」只錄
    # 「會議視窗所屬」的 app、同一個 app 的「分頁」會進來、「麥克風」照常，並提醒「同一個瀏覽器」不要再播「其他」有聲音的「分頁」；
    # README 的「## 錄製會議」段（record-cli 區塊外）有一個段落寫明同義的範圍（系統聲音、會議視窗所屬、app、分頁）。
    def test_audio_scope_documented(self):
        skill = read(self, SKILL)
        need_skill = ("系統聲音", "會議視窗所屬", "app", "分頁", "麥克風", "同一個瀏覽器", "其他")
        hits = [p for p in paragraphs(outside_block(skill)) if all(k in p for k in need_skill)]
        self.assertTrue(hits, f"SKILL.md 應有一段同時含 {need_skill} 的系統聲音範圍說明（§4.3.5）")
        self.assertTrue(any(re.search(r"同一個瀏覽器[^。\n]*不要[^。\n]*其他[^。\n]*分頁", p) for p in hits),
                        "SKILL.md 應提醒「同一個瀏覽器不要再播其他有聲音的分頁」")
        readme = read(self, README)
        sec = record_section(readme)
        self.assertIsNotNone(sec, "README 應有「## 錄製會議」段")
        need_readme = ("系統聲音", "會議視窗所屬", "app", "分頁")
        self.assertTrue(any(all(k in p for k in need_readme) for p in paragraphs(outside_block(sec))),
                        f"README 錄製段（record-cli 區塊外）應有一段含 {need_readme} 的同義說明（§4.3.5）")

    # spec §4.2.12（t6 第三輪，發現 I）：SKILL.md 與 README.md 錄製段各有一句含「幕前調度」與「縮圖」的說明；
    # README 的 record-cli 區塊不變（test_docs_cli_block_matches_spec 等既有測試保護），這裡只看區塊外。
    # 「一句」＝以空白行切段落後、再以「。」「！」「？」切出的句子（段落內的換行視為同一句）
    def test_stage_manager_documented(self):
        def sentences(text):
            return [x for para in paragraphs(text) for x in re.split(r"[。！？]", para.replace("\n", "")) if x.strip()]

        need = ("幕前調度", "縮圖")
        skill = read(self, SKILL)
        self.assertTrue(any(all(k in x for k in need) for x in sentences(outside_block(skill))),
                        f"SKILL.md 應有一句同時含 {need} 的幕前調度說明（§4.2.12）")
        sec = record_section(read(self, README))
        self.assertIsNotNone(sec, "README 應有「## 錄製會議」段")
        self.assertTrue(any(all(k in x for k in need) for x in sentences(outside_block(sec))),
                        f"README 錄製段（record-cli 區塊外）應有一句同時含 {need} 的幕前調度說明（§4.2.12）")

if __name__ == "__main__":
    unittest.main()

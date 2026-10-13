"""meeting record 的 CLI 表面（spec §2.4.8）：常數 SURFACE 與三種解析器、參數組法。

本檔是 test_docs.py、test_cli_dispatch.py、test_record_sh.py 共用的唯一定義；
SURFACE 逐字抄 spec §2.4.2，不從其他檔讀。檔名不以 test 開頭，unittest discover 不會收它。
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MEETING_SH = str(REPO / "bin" / "meeting.sh")


class Parsed(dict):
    """dict，也可用屬性取值（spec 寫 SURFACE.form_codes 與 SURFACE['form_codes'] 兩種都通）。"""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as e:
            raise AttributeError(name) from e


class SurfaceParseError(ValueError):
    """文法不符；訊息含「第 N 行」與該行內容。"""


F_ROOT = "meeting record [<根>]"
F_WINDOWS = "meeting record windows"
F_PREFLIGHT = "meeting record preflight"
F_STOP = "meeting record stop"
F_STATUS = "meeting record status"
F_FINISH = "meeting record finish <場次>"
# R2（spec §6 第 77 條）：pause、resume、mute、unmute、mark 五個寫法
F_PAUSE = "meeting record pause"
F_RESUME = "meeting record resume"
F_MUTE = "meeting record mute"
F_UNMUTE = "meeting record unmute"
F_MARK = "meeting record mark"
F_HELP = "meeting record help"

SURFACE = Parsed(
    forms=[F_ROOT, F_WINDOWS, F_PREFLIGHT, F_STOP, F_STATUS, F_FINISH, F_PAUSE, F_RESUME, F_MUTE, F_UNMUTE, F_MARK,
           F_HELP],
    form_flags={
        (F_ROOT, "--window <id>"),
        (F_WINDOWS, "--json"),
        (F_PREFLIGHT, "--window <id>"),
    },
    form_codes={
        (F_ROOT, 0), (F_ROOT, 2), (F_ROOT, 3), (F_ROOT, 4), (F_ROOT, 5),
        (F_WINDOWS, 0), (F_WINDOWS, 2), (F_WINDOWS, 4),
        (F_PREFLIGHT, 0), (F_PREFLIGHT, 2), (F_PREFLIGHT, 3), (F_PREFLIGHT, 4),
        (F_STOP, 0), (F_STOP, 3), (F_STOP, 5),
        (F_STATUS, 0), (F_STATUS, 5),
        (F_FINISH, 0), (F_FINISH, 2), (F_FINISH, 3), (F_FINISH, 5),
        (F_PAUSE, 0), (F_PAUSE, 3),
        (F_RESUME, 0), (F_RESUME, 3),
        (F_MUTE, 0), (F_MUTE, 3),
        (F_UNMUTE, 0), (F_UNMUTE, 3),
        (F_MARK, 0), (F_MARK, 3),
        (F_HELP, 0),
    },
    layer_flags=["--recorder", "--yes"],
    codes=[0, 2, 3, 4, 5],
)

HELP_HEADERS = ["寫法：", "旗標：", "meeting.sh 層旗標：", "結束碼："]
USAGE_HEADER = "錄製（meeting record；完整說明：meeting record help）"
BLOCK_BEGIN = "<!-- record-cli:begin -->"
BLOCK_END = "<!-- record-cli:end -->"
BLOCK_HEADER = "| 寫法 | 旗標 | 結束碼 |"
BLOCK_RULE = "|---|---|---|"

_FIELD_SEP = re.compile(r" {2,}")
_CONTENT_LINE = re.compile(r"^  [^ ]")
_CODES_FIELD = re.compile(r"^結束碼((?: \d)+)$")


def flag_name(flag):
    """`--window <id>` → `--window`。"""
    return flag.split(" ", 1)[0]


def _err(lineno, line, why):
    raise SurfaceParseError(f"第 {lineno} 行：{line!r}（{why}）")


def _ascending(codes):
    return all(a < b for a, b in zip(codes, codes[1:]))


def parse_help(text):
    """spec §2.4.3–2.4.4：`meeting.sh record help` 的 stdout → 五個成分。"""
    lines = text.split("\n")
    pos = {}
    for i, line in enumerate(lines):
        if line in HELP_HEADERS:
            if line in pos:
                _err(i + 1, line, "段頭重複")
            pos[line] = i
    for h in HELP_HEADERS:
        if h not in pos:
            raise SurfaceParseError(f"缺少段頭行：{h!r}")
    order = [pos[h] for h in HELP_HEADERS]
    if order != sorted(order):
        raise SurfaceParseError("段頭順序錯：應為 " + " → ".join(HELP_HEADERS))

    def section(h):
        out = []
        i = pos[h] + 1
        while i < len(lines) and _CONTENT_LINE.match(lines[i]):
            out.append((i + 1, lines[i], _FIELD_SEP.split(lines[i][2:])))
            i += 1
        return out

    forms, form_codes = [], set()
    for n, line, f in section("寫法："):
        if len(f) != 2:
            _err(n, line, f"「寫法：」段應有 2 個欄位，實際 {len(f)} 個")
        m = _CODES_FIELD.match(f[1])
        if not m:
            _err(n, line, "第 2 欄應為「結束碼 <碼> <碼> …」")
        codes = [int(c) for c in m.group(1).split()]
        if not _ascending(codes):
            _err(n, line, "結束碼應遞增")
        forms.append(f[0])
        form_codes.update((f[0], c) for c in codes)

    form_flags = set()
    for n, line, f in section("旗標："):
        if len(f) != 2:
            _err(n, line, f"「旗標：」段應有 2 個欄位，實際 {len(f)} 個")
        if f[0] not in forms:
            _err(n, line, "第 1 欄不是「寫法：」段列出的寫法")
        if flag_name(f[1]) in SURFACE.layer_flags:
            _err(n, line, "層旗標不得出現在「旗標：」段")
        if not f[1].startswith("--"):
            _err(n, line, "第 2 欄應為以 -- 開頭的寫法旗標")
        form_flags.add((f[0], f[1]))

    layer_flags = []
    for n, line, f in section("meeting.sh 層旗標："):
        if len(f) != 2:
            _err(n, line, f"「meeting.sh 層旗標：」段應有 2 個欄位，實際 {len(f)} 個")
        layer_flags.append(f[0])

    codes = []
    for n, line, f in section("結束碼："):
        if len(f) != 2:
            _err(n, line, f"「結束碼：」段應有 2 個欄位，實際 {len(f)} 個")
        if not re.fullmatch(r"\d", f[0]):
            _err(n, line, "第 1 欄應為一位數的結束碼")
        codes.append(int(f[0]))

    return Parsed(forms=forms, form_flags=form_flags, form_codes=form_codes,
                  layer_flags=layer_flags, codes=codes)


def extract_block(text):
    """回傳 begin 行與 end 行之間的原文（不含這兩行），供逐位元組比對。"""
    lines = text.split("\n")
    b = [i for i, l in enumerate(lines) if l == BLOCK_BEGIN]
    e = [i for i, l in enumerate(lines) if l == BLOCK_END]
    if len(b) != 1 or len(e) != 1:
        raise SurfaceParseError(
            f"{BLOCK_BEGIN} 應恰好 1 行（實際 {len(b)}）、{BLOCK_END} 應恰好 1 行（實際 {len(e)}）")
    if b[0] > e[0]:
        raise SurfaceParseError("record-cli 的 begin 行在 end 行之後")
    return "\n".join(lines[b[0] + 1:e[0]])


def _cells(lineno, line):
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        _err(lineno, line, "表格列應以 | 開頭與結尾")
    cells = [c.replace("`", "").strip() for c in s[1:-1].split("|")]
    if len(cells) != 3:
        _err(lineno, line, f"表格列應有 3 格，實際 {len(cells)} 格")
    return cells


def parse_block(text):
    """spec §2.4.5：文件中 record-cli 區塊的表 → forms、form_flags、form_codes。"""
    body = [l for l in extract_block(text).split("\n") if l.strip()]
    if len(body) < 2 or body[0].strip() != BLOCK_HEADER or body[1].strip() != BLOCK_RULE:
        raise SurfaceParseError(f"區塊的前兩行應為 {BLOCK_HEADER!r} 與 {BLOCK_RULE!r}")
    forms, form_flags, form_codes = [], set(), set()
    for n, line in enumerate(body[2:], start=3):
        form, flags, codes = _cells(n, line)
        forms.append(form)
        if flags != "—":
            for fl in flags.split("、"):
                fl = fl.strip()
                if not fl.startswith("--"):
                    _err(n, line, "旗標格應為 — 或以「、」分隔的 -- 旗標")
                form_flags.add((form, fl))
        if not re.fullmatch(r"\d( \d)*", codes):
            _err(n, line, "結束碼格應為以一個半形空白分隔的數字")
        nums = [int(c) for c in codes.split(" ")]
        if not _ascending(nums):
            _err(n, line, "結束碼應遞增")
        form_codes.update((form, c) for c in nums)
    return Parsed(forms=forms, form_flags=form_flags, form_codes=form_codes)


_USAGE_LINE = re.compile(r"^  meeting record( |$)")


def parse_usage(text):
    """spec §2.4.6：`meeting.sh help` 的輸出 → forms（依出現順序）。"""
    forms = []
    for line in text.split("\n"):
        if _USAGE_LINE.match(line):
            forms.append(_FIELD_SEP.split(line[2:], 1)[0])
    return Parsed(forms=forms)


def form_argv(form, *, root, session, form_flag=None, layer_flag=None, extra=None,
              meeting_sh=MEETING_SH):
    """spec §2.4.7：寫法 → 可執行的 argv（以 bash 執行 bin/meeting.sh）。"""
    words = form.split(" ")
    if words[:2] != ["meeting", "record"]:
        raise ValueError(f"不是 meeting record 的寫法：{form!r}")
    argv = ["bash", meeting_sh, "record"]
    if layer_flag is not None:
        if layer_flag not in SURFACE.layer_flags:
            raise ValueError(f"不是層旗標：{layer_flag!r}")
        argv.append(layer_flag)
    for w in words[2:]:
        if w == "[<根>]":
            if root is None:
                raise ValueError("這個寫法需要 root")
            argv.append(str(root))
        elif w == "<場次>":
            if session is None:
                raise ValueError("這個寫法需要 session")
            argv.append(str(session))
        else:
            argv.append(w)
    if form_flag is not None:
        for part in form_flag.split(" "):
            argv.append("1" if re.fullmatch(r"<[^>]+>", part) else part)
    if extra:
        argv.extend([extra] if isinstance(extra, str) else list(extra))
    return argv


def diff_message(name, got, want):
    """比對失敗時列出差集（spec §2.4.4）。list 另報順序。"""
    if isinstance(want, list):
        extra = [x for x in got if x not in want]
        missing = [x for x in want if x not in got]
        msg = f"{name} 不相等：多出 {extra}；缺少 {missing}"
        if not extra and not missing:
            msg += f"；順序不同：實際 {got}，應為 {want}"
        return msg
    return f"{name} 不相等：多出 {sorted(set(got) - set(want))}；缺少 {sorted(set(want) - set(got))}"


def assert_component_equal(tc, name, got, want):
    if isinstance(want, list):
        tc.assertEqual(list(got), list(want), diff_message(name, list(got), list(want)))
    else:
        tc.assertEqual(set(got), set(want), diff_message(name, set(got), set(want)))

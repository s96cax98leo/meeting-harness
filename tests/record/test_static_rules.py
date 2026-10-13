"""靜態規則：spec §4.1.5、§4.2.5、§4.3.6、§4.4.9、§4.4.10、§4.2.8、§4.2.11、§4.4.5、§4.9.4、§4.11.3、§4.11.5、§4.11.6、§4.11.8–§4.11.10、§4.14、§4.15.10、§4.15.11；
t6 第三輪：§4.2.12（幕前調度只讀）、§4.5.9（磁碟檢查不讀快取）、§4.6.20 (iv)（串接時音訊一次編碼）。"""
import ast
import os
import plistlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.record._helpers import RECORD_SH
from tests.record.surface import REPO

MR = REPO / "tools" / "MeetingRecorder"
SOURCES = MR / "Sources"
RESOURCES = MR / "Resources"
MEDIA_EXTS = (".mov", ".wav", ".m4a", ".mp4", ".m4v", ".mp3")
CLIENT_SCAN_DIRS = ["specs", "tests", "tools/MeetingRecorder/Tests"]


def swift_sources():
    return sorted(SOURCES.rglob("*.swift"))


def read_sources():
    return {p: p.read_text(encoding="utf-8") for p in swift_sources()}


MENUBAR_SWIFT = SOURCES / "Trigger" / "MenuBar.swift"
CORE_TRIGGER_SWIFT = SOURCES / "Core" / "Trigger.swift"
START_ITEM_TITLE = "開始錄製（用上次的設定）"


def require_menubar(tc):
    tc.assertTrue(MENUBAR_SWIFT.is_file(), f"{MENUBAR_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
    return MENUBAR_SWIFT.read_text(encoding="utf-8")


def strip_swift_comments(src):
    """去掉 // 行註解與 /* */ 區塊註解（字串內的 // 例如網址不受影響的簡化版：只去掉行首或空白後的 //）。"""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)(^|\s)//.*$", r"\1", src)


def swift_string_literals(src):
    """取出單行 Swift 字串字面值的內容（不含三引號字串）。"""
    return re.findall(r'"((?:[^"\\\n]|\\.)*)"', src)


def require_record_sh(tc):
    tc.assertTrue(RECORD_SH.is_file(), f"{RECORD_SH} 不存在（不得因檔案不存在而跳過）")
    return RECORD_SH.read_text(encoding="utf-8")


def swift_string_after(src, name):
    """取 Swift 常數 `let|var <name> = ...` 的字串內容（單行字串或三引號多行字串）。"""
    m = re.search(r"\b(?:let|var)\s+" + re.escape(name) + r"\b[^=]*=\s*", src)
    if not m:
        return None
    rest = src[m.end():]
    if rest.startswith('"""'):
        end = rest.find('"""', 3)
        return rest[3:end] if end >= 0 else None
    m2 = re.match(r'"((?:[^"\\]|\\.)*)"', rest)
    return m2.group(1) if m2 else None


PREFLIGHT_RUNNER_SWIFT = SOURCES / "Capture" / "PreflightRunner.swift"
RECORDING_SESSION_SWIFT = SOURCES / "Capture" / "RecordingSession.swift"
CAPTURE_DIR = SOURCES / "Capture"
# spec §4.4.5（D20）：正式錄製不得再用 SCRecordingOutput（probe 子指令保留，Probe.swift 例外）
SEGMENT_WRITER_FORBIDDEN = ("SCRecordingOutput", "addRecordingOutput", "removeRecordingOutput")
SEGMENT_WRITER_REQUIRED = ("AVAssetWriter(", "startSession(atSourceTime:", "endSession(atSourceTime:",
                           "markAsFinished()", "finishWriting", "movieFragmentInterval",
                           "AVVideoAllowFrameReorderingKey", "AVVideoScalingModeKey",
                           "expectsMediaDataInRealTime = true", "routeSample(", "segmentVideoBitRate(",
                           "segmentWriteFailed")
FINALIZE_PY = REPO / "bin" / "_record_finalize.py"
BIN_DIR = REPO / "bin"
# spec §4.2.12（t6 第三輪，發現 I）：錄製器與 bin/ 不得改寫任何系統設定
SETTINGS_WRITES = ("CFPreferencesSetAppValue", "CFPreferencesSetValue", "defaults write")


def call_constants(call):
    """ast.Call 的位置參數依序：字串常數照抄，其他（變數、*展開、f-string）記 None。"""
    return [a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else None for a in call.args]


def has_pair(args, a, b):
    """args 中是否有相鄰的 a、b（例 "-c:a", "aac"）。"""
    return any(x == a and y == b for x, y in zip(args, args[1:]))


# spec §4.2.11（D20，t6 缺陷 4）：preflight 到正式 startCapture 的等待與重試
START_CAPTURE_CONSTANTS = {"startCaptureSettleSeconds": 1.0, "startCaptureRetryDelaySeconds": 2.0}


def capture_sources(exclude=("Probe.swift",)):
    """Sources/Capture/ 下除 exclude 以外的 .swift（{路徑: 原文}）。"""
    return {p: p.read_text(encoding="utf-8") for p in sorted(CAPTURE_DIR.glob("*.swift")) if p.name not in exclude}


def blank_swift_strings(src):
    """把單行 Swift 字串字面值的內容換成等長空白（保留引號），讓大括號配對不受字串內容影響；位置不變。"""
    return re.sub(r'"((?:[^"\\\n]|\\.)*)"', lambda m: '"' + " " * len(m.group(1)) + '"', src)


def swift_functions(src):
    """回傳 {函式名: [函式本體, …]}（`func 名稱(` 起到配對的 `}`；同名多載各列一筆；巢狀函式也會被外層本體包含）。
    src 應已去掉註解；以 blank_swift_strings 後的副本找大括號，再從原文切出本體。"""
    masked = blank_swift_strings(src)
    out = {}
    for m in re.finditer(r"\bfunc\s+([A-Za-z_]\w*)\s*(?:<[^>]*>)?\s*\(", masked):
        open_i = masked.find("{", m.end())
        if open_i < 0:
            continue
        depth, i = 0, open_i
        while i < len(masked):
            ch = masked[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        out.setdefault(m.group(1), []).append(src[open_i:i + 1])
    return out


class TestStaticRules(unittest.TestCase):
    # spec §4.1.5（只掃 bin/record.sh）
    def test_no_direct_exec_of_recorder(self):
        src = require_record_sh(self)
        self.assertNotIn("Contents/MacOS/MeetingRecorder", src)
        self.assertTrue("open -n -a" in src or "MH_RECORD_OPEN" in src,
                        "record.sh 應以 open -n -a 或 MH_RECORD_OPEN 啟動錄製器")
        self.assertIn("MH_RECORD_OPEN", src)

    # spec §4.9.4（只掃 tools/MeetingRecorder/Sources/）
    def test_no_default_device_write_in_sources(self):
        srcs = read_sources()
        self.assertTrue(srcs, "Sources/ 沒有任何 .swift")
        for p, s in srcs.items():
            for bad in ("AudioObjectSetPropertyData", "BlackHole"):
                self.assertNotIn(bad, s, f"{p.relative_to(REPO)} 不得出現 {bad}")

    # spec §4.9.4（只掃 bin/record.sh；檔案不存在時失敗）
    def test_no_default_device_write_in_record_sh(self):
        src = require_record_sh(self)
        for bad in ("AudioObjectSetPropertyData", "BlackHole"):
            self.assertNotIn(bad, src)

    # spec §4.11.3
    def test_no_global_event_monitor(self):
        srcs = read_sources()
        self.assertTrue(srcs)
        for p, s in srcs.items():
            self.assertNotIn("addGlobalMonitorForEvents", s, str(p.relative_to(REPO)))

    def test_hotkey_uses_carbon(self):
        allsrc = "\n".join(read_sources().values())
        self.assertIn("RegisterEventHotKey", allsrc)
        self.assertRegex(allsrc, r"(?m)^import Carbon")

    # spec §4.11.3（D18）：HotKey(...) 回 nil 時在 record.log 寫一行含「快捷鍵」與「註冊失敗」的說明
    def test_hotkey_failure_logged(self):
        srcs = read_sources()
        self.assertTrue(srcs)
        hits = []
        for p, s in srcs.items():
            if p.relative_to(SOURCES).parts[0] != "Trigger":
                continue
            for lit in swift_string_literals(strip_swift_comments(s)):
                if "快捷鍵" in lit and "註冊失敗" in lit:
                    hits.append(p.relative_to(REPO).as_posix())
        self.assertTrue(hits, "Sources/Trigger/ 應有一行同時含「快捷鍵」與「註冊失敗」的 record.log 說明字串")

    # spec §4.11.6（D18）：「開始錄製（用上次的設定）」顯示 ⌃⌥⌘R
    #（keyEquivalent "r"、keyEquivalentModifierMask [.control, .option, .command]）
    def test_start_item_shows_hotkey(self):
        src = strip_swift_comments(require_menubar(self))
        m = re.search(r"\b(\w+)\s*(?::\s*NSMenuItem\s*)?=\s*NSMenuItem\(\s*title:\s*\"" + re.escape(START_ITEM_TITLE)
                      + r"\"([^\n]*)", src)
        self.assertIsNotNone(m, f"MenuBar.swift 應以 NSMenuItem(title: \"{START_ITEM_TITLE}\", …) 建立開始錄製項")
        var, init_args = m.group(1), m.group(2)
        key_in_init = re.search(r'keyEquivalent:\s*"r"', init_args)
        key_assigned = re.search(r"\b" + re.escape(var) + r'\.keyEquivalent\s*=\s*"r"', src)
        self.assertTrue(key_in_init or key_assigned, f"{var} 的 keyEquivalent 應為 \"r\"")
        mm = re.search(r"\b" + re.escape(var) + r"\.keyEquivalentModifierMask\s*=\s*\[([^\]]*)\]", src)
        self.assertIsNotNone(mm, f"{var}.keyEquivalentModifierMask 應明寫")
        mods = {x.strip() for x in mm.group(1).split(",") if x.strip()}
        self.assertEqual(mods, {".control", ".option", ".command"},
                         "開始錄製項的修飾鍵應恰為 ⌃⌥⌘（與 §4.11.3 的全域快捷鍵同一組）")

    # spec §4.11.8（D18）：狀態列以 attributedTitle 顯示 truncatedStatusTitle(statusLine, limit: 40)、前景色 labelColor
    def test_status_title_uses_label_color(self):
        src = strip_swift_comments(require_menubar(self))
        self.assertTrue(re.search(r"\.attributedTitle\s*=", src), "狀態列應以 attributedTitle 顯示")
        self.assertTrue(re.search(r"truncatedStatusTitle\([^)]*limit:\s*40\s*\)", src),
                        "狀態列文字應為 truncatedStatusTitle(…, limit: 40)")
        self.assertTrue(re.search(r"\.foregroundColor\b", src), "attributedTitle 應設前景色屬性")
        self.assertTrue(re.search(r"(?:NSColor)?\.labelColor\b", src), "狀態列前景色應為 NSColor.labelColor")
        for gray in ("disabledControlTextColor", "tertiaryLabelColor", "quaternaryLabelColor"):
            self.assertNotIn(gray, src, f"狀態列不得用系統灰色 {gray}")
        self.assertTrue(re.search(r"\.toolTip\s*=\s*[\w.]*statusLine\b", src), "狀態列選單項的 toolTip 應為完整 statusLine")

    # spec §4.11.9（D18）：選單展開時照常每秒更新——timer 加入 .common mode，或 menuWillOpen 時立即 refresh
    def test_menubar_refresh_while_menu_open(self):
        src = strip_swift_comments(require_menubar(self))
        self.assertTrue(re.search(r"forMode:\s*(?:RunLoop\.Mode)?\.common\b|\bmenuWillOpen\b", src),
                        "MenuBar.swift 應含 forMode: .common 或 menuWillOpen")

    # spec §4.11.10（D18）：menubar.lock 與 acquireMenuBarLock 只出現在 Core/Trigger.swift 與 Trigger/MenuBar.swift
    def test_menubar_lock_only_in_menubar(self):
        srcs = read_sources()
        self.assertTrue(srcs)
        allowed = {CORE_TRIGGER_SWIFT, MENUBAR_SWIFT}
        found = {"menubar.lock": set(), "acquireMenuBarLock": set()}
        for p, s in srcs.items():
            code = strip_swift_comments(s)
            for k in found:
                if k in code:
                    found[k].add(p)
        for k, files in found.items():
            extra = sorted(f.relative_to(REPO).as_posix() for f in files - allowed)
            self.assertEqual(extra, [], f"{k} 只能出現在 Core/Trigger.swift 與 Trigger/MenuBar.swift")
        self.assertTrue(found["menubar.lock"], "Sources/ 應有 menubar.lock（單一實例鎖檔名）")
        self.assertIn(CORE_TRIGGER_SWIFT, found["acquireMenuBarLock"], "acquireMenuBarLock 應定義在 Core/Trigger.swift")
        self.assertIn(MENUBAR_SWIFT, found["acquireMenuBarLock"], "Trigger/MenuBar.swift 應呼叫 acquireMenuBarLock")
        self.assertTrue(re.search(r"\bfunc\s+acquireMenuBarLock\s*\(", CORE_TRIGGER_SWIFT.read_text(encoding="utf-8")),
                        "Core/Trigger.swift 應定義 func acquireMenuBarLock")

    # t6 實機缺陷：WindowServer（CGS／SkyLight）連線第一次在非主執行緒被觸發時 assert（SCContentFilter 建構時 SIGABRT），
    # 所以 main.swift 必須在分派任何 Task 之前，於頂層（主執行緒）初始化連線
    def test_windowserver_connection_initialized_on_main_thread(self):
        main_swift = SOURCES / "main.swift"
        self.assertTrue(main_swift.is_file(), f"{main_swift.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        code = strip_swift_comments(main_swift.read_text(encoding="utf-8"))
        first_task = re.search(r"\bTask\s*\{", code)
        self.assertIsNotNone(first_task, "main.swift 應以 Task { … } 分派非同步子指令")
        init = re.search(r"\bNSApplication\.shared\b|\bCGMainDisplayID\s*\(\s*\)", code)
        self.assertIsNotNone(init, "main.swift 應在頂層呼叫 NSApplication.shared 或 CGMainDisplayID() 初始化 WindowServer 連線")
        self.assertLess(init.start(), first_task.start(),
                        "WindowServer 連線的初始化必須在第一個 Task { 之前（主執行緒），否則 SCContentFilter 會在背景執行緒觸發 SkyLight assert")
        # 不得包在函式或閉包裡（那樣不保證在主執行緒、也不保證先於分派執行）：該行必須是頂層（無縮排）
        line_start = code.rfind("\n", 0, init.start()) + 1
        self.assertFalse(code[line_start:init.start()].startswith((" ", "\t")),
                         "WindowServer 連線的初始化應寫在 main.swift 頂層（無縮排），不得包在函式或閉包裡")

    # spec §4.2.5（D19：第 5 項兩段式的實作形狀；(c) 的判定本身由 swift:PreflightTests.swift::testSystemAudioCheckTwoStage 驗）
    def test_preflight_system_audio_two_stage(self):
        self.assertTrue(PREFLIGHT_RUNNER_SWIFT.is_file(),
                        f"{PREFLIGHT_RUNNER_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        code = strip_swift_comments(PREFLIGHT_RUNNER_SWIFT.read_text(encoding="utf-8"))
        lits = swift_string_literals(code)
        # (c) 第 5 項的結果由 Core 的 systemAudioCheck 決定，呼叫端明寫門檻 -60
        self.assertTrue("systemAudioCheck(" in code, "第 5 項應呼叫 Core 的 systemAudioCheck(…) 判定（§4.2.5 (c)）")
        self.assertTrue(re.search(r"systemAudioCheck\(\s*targetPeakDBFS:[^)]*thresholdDBFS:\s*-60\b", code),
                        "systemAudioCheck 呼叫應明寫 thresholdDBFS: -60（§3.4）")
        self.assertTrue(re.search(r"\.warnTargetSilent\b", code),
                        "應處理 .warnTargetSilent 的情形")
        self.assertTrue(re.search(r"warnOnly:\s*true", code),
                        ".warnTargetSilent 應以 PreflightResult(…, warnOnly: true) 回報（§4.2.5 (c)）")
        # (b) display filter（excludingWindows: []）＋ afplay 子程序
        self.assertTrue(re.search(r"SCContentFilter\(\s*display:[^)]*excludingWindows:\s*\[\s*\]\s*\)", code),
                        "(b) 應另開 SCContentFilter(display:excludingWindows: []) 的 probe stream")
        self.assertIn("/usr/bin/afplay", lits, "(b) 的測試音應由 spawn /usr/bin/afplay 子程序播放")
        self.assertTrue(re.search(r"excludesCurrentProcessAudio\s*=\s*true", code),
                        "probe stream 應設 excludesCurrentProcessAudio = true")
        # (a) 目標視窗 probe 仍在
        self.assertTrue(re.search(r"SCContentFilter\(\s*desktopIndependentWindow:", code),
                        "(a) 應對目標視窗開 SCContentFilter(desktopIndependentWindow:) 的 probe stream")
        # (c) .warnTargetSilent 的訊息：三段文字都要是字串字面值裡的原文（不得靠插值拼出「15」）
        for must in ("會議 app 目前沒有聲音", "擷取權限正常", "15 秒"):
            self.assertTrue(any(must in l for l in lits),
                            f"第 5 項 warn 的訊息應含「{must}」（§4.2.5 (c)）")
        # (c) .fail 的訊息只含授權補救（t6 第二輪 D21；使用者核准的測試預期修改，spec §6 第 54 條）：
        #     ScreenCaptureKit 擷取系統聲音在輸出靜音之前，(b) 錄不到只可能是擷取權限問題
        for must in ("重新授權螢幕錄製", "完全結束 MeetingRecorder 再重開"):
            self.assertTrue(any(must in l for l in lits), f"第 5 項 hard fail 的訊息應含「{must}」（§4.2.5 (c)，D21）")
        for bad in ("取消輸出靜音", "把音量調大"):
            self.assertFalse(any(bad in l for l in lits),
                             f"PreflightRunner.swift 的字串字面值不得再含「{bad}」（§4.2.5 (c)，D21）")

        # 目標視窗那條 stream 不播測試音（§4.2.5 (a)「期間不播測試音」）。判準（函式層級，靜態可判的近似）：
        #   1. 「播測試音的函式」＝本體含 "/usr/bin/afplay" 字面值的函式（例：playTestSound）。
        #   2. 任何本體含 SCContentFilter(desktopIndependentWindow: 的函式，不得在本體裡含 "/usr/bin/afplay"，
        #      也不得直接呼叫第 1 點的函式（現行 ProbeMeter.measure 同一函式建目標視窗 filter 又排程 playTestSound，
        #      即違反此條）。
        #   3. 至少要有一個本體含 SCContentFilter(display:…excludingWindows: []) 的函式，也直接（或經第 1 點的函式）播測試音。
        # 限制：若實作把 filter 當參數傳進同一支共用量測函式、以布林參數決定播不播，本判準看不出旗標值；
        # 那部分由人工 §4.2.6 (iii)「會議 app 正在發聲 → pass、檢查期間不播測試音」把關。
        funcs = swift_functions(code)
        tone_funcs = {name for name, bodies in funcs.items() if any('"/usr/bin/afplay"' in b for b in bodies)}
        self.assertTrue(tone_funcs, "找不到本體含 \"/usr/bin/afplay\" 的函式")

        def plays_tone(body):
            if '"/usr/bin/afplay"' in body:
                return True
            masked = blank_swift_strings(body)
            return any(re.search(r"(?<!\w)" + re.escape(n) + r"\s*\(", masked) for n in tone_funcs)

        offenders = sorted({name for name, bodies in funcs.items() for b in bodies
                            if re.search(r"SCContentFilter\(\s*desktopIndependentWindow:", b)
                            and plays_tone(b) and name not in tone_funcs})
        offenders += sorted(n for n in tone_funcs
                            if any(re.search(r"SCContentFilter\(\s*desktopIndependentWindow:", b) for b in funcs[n]))
        self.assertEqual(offenders, [],
                         "建立目標視窗 filter（desktopIndependentWindow）的函式不得播測試音（§4.2.5 (a)）："
                         f"{offenders}")
        display_tone = sorted({name for name, bodies in funcs.items() for b in bodies
                               if re.search(r"SCContentFilter\(\s*display:[^)]*excludingWindows:\s*\[\s*\]", b)
                               and plays_tone(b)})
        self.assertTrue(display_tone,
                        "應有建立 display filter（excludingWindows: []）且播測試音的函式（§4.2.5 (b)）")

    # spec §4.4.5（D20）：自管 AVAssetWriter 分段寫檔的靜態約束
    def test_segment_writer_uses_assetwriter(self):
        self.assertTrue(CAPTURE_DIR.is_dir(), f"{CAPTURE_DIR.relative_to(REPO)} 不存在（不得因目錄不存在而跳過）")
        srcs = capture_sources()
        self.assertTrue(srcs, "Sources/Capture/ 除 Probe.swift 外沒有任何 .swift")
        # 「不得出現」照 spec 字面：連註解也算（Probe.swift 例外）
        hits = sorted(f"{p.relative_to(REPO)}：{bad}" for p, t in srcs.items()
                      for bad in SEGMENT_WRITER_FORBIDDEN if bad in t)
        self.assertEqual(hits, [], "Capture/ 除 Probe.swift 外不得出現 SCRecordingOutput 系列（spec §4.4.5）")
        # 「應出現」只認程式碼（去掉註解），而且不靠 Probe.swift 湊數
        code = "\n".join(strip_swift_comments(t) for t in srcs.values())
        missing = [need for need in SEGMENT_WRITER_REQUIRED if need not in code]
        self.assertEqual(missing, [], "Capture/（不含 Probe.swift、不含註解）缺少 D20 寫檔機制必備的字串（spec §4.4.5）")

    # spec §4.2.11（D20）：startCapture 前等 1.0 秒、失敗等 2.0 秒重建 SCStream 重試一次
    def test_start_capture_settle_and_retry(self):
        self.assertTrue(CAPTURE_DIR.is_dir(), f"{CAPTURE_DIR.relative_to(REPO)} 不存在（不得因目錄不存在而跳過）")
        code = {p: strip_swift_comments(t) for p, t in capture_sources(exclude=()).items()}
        allcode = "\n".join(code.values())
        masked = blank_swift_strings(allcode)
        for name, value in START_CAPTURE_CONSTANTS.items():
            with self.subTest(constant=name):
                defs = list(re.finditer(r"\b(?:let|var)\s+" + re.escape(name)
                                        + r"\s*(?::\s*[A-Za-z_][\w.]*\s*)?=\s*([0-9]+(?:\.[0-9]+)?)\b", masked))
                self.assertEqual(len(defs), 1, f"Capture/ 應恰有一處定義 {name}（spec §4.2.11）")
                self.assertEqual(float(defs[0].group(1)), value, f"{name} 應為 {value}（spec §4.2.11）")
                uses = len(re.findall(r"(?<![\w.])" + re.escape(name) + r"\b", masked)) + \
                    len(re.findall(r"\.\s*" + re.escape(name) + r"\b", masked))
                self.assertGreaterEqual(uses - 1, 1, f"{name} 除了定義以外應至少被引用一次（spec §4.2.11）")
        lits = swift_string_literals(allcode)
        self.assertTrue(any("startCapture 第一次失敗" in l for l in lits),
                        "第一次 startCapture 失敗時 record.log 應記一行含「startCapture 第一次失敗」（spec §4.2.11）")

    # spec §4.3.6（t6 第二輪，缺陷 A）：換段當下同步讀視窗尺寸的實作形狀；判定本身由 swift:SegmentsTests.swift::testNextSegmentSize 驗
    def test_segment_size_read_synchronously_at_boundary(self):
        self.assertTrue(RECORDING_SESSION_SWIFT.is_file(),
                        f"{RECORDING_SESSION_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        capture_code = "\n".join(strip_swift_comments(t) for t in capture_sources(exclude=()).values())
        for need in ("CGWindowListCreateDescriptionFromArray", "kCGWindowBounds"):
            self.assertTrue(need in capture_code, f"Sources/Capture/ 應以 {need} 同步讀視窗尺寸（spec §4.3.6）")
        raw = RECORDING_SESSION_SWIFT.read_text(encoding="utf-8")
        # 「不得再出現」照 spec 字面：連註解也算（邊界前 1 秒非同步查詢的做法整個移除）
        left = [n for n in ("pendingSize", "sizeQuery", "scheduleSizeQuery") if re.search(r"\b" + n + r"\b", raw)]
        self.assertEqual(left, [], "RecordingSession.swift 不得再出現邊界前非同步查詢尺寸的名稱（spec §4.3.6）")
        code = strip_swift_comments(raw)
        masked = blank_swift_strings(code)
        self.assertTrue(re.search(r"(?<![\w.])nextSegmentSize\s*\(", masked), "RecordingSession.swift 應呼叫 nextSegmentSize(（spec §4.3.6）")
        bodies = swift_functions(code).get("startNewSegment", [])
        self.assertTrue(bodies, "RecordingSession.swift 應有 func startNewSegment")
        for b in bodies:
            mb = blank_swift_strings(b)
            self.assertTrue(re.search(r"(?<![\w.])nextSegmentSize\s*\(", mb),
                             "startNewSegment 的本體應呼叫 nextSegmentSize(（換段當下決定新段尺寸，spec §4.3.6）")
            for bad, pat in (("await", r"\bawait\b"), ("Task {", r"\bTask\s*\{"),
                             ("shareableContent(", r"\bshareableContent\s*\(")):
                self.assertFalse(re.search(pat, mb), f"startNewSegment 的本體不得出現 {bad}（尺寸讀取必須同步，spec §4.3.6）")

    # spec §4.4.9（t6 第二輪，缺陷 D）：complete(finalizeCode:) 以 completionOutcome 決定最終結果；判定本身由 swift:RecordsTests.swift::testCompletionOutcome 驗
    def test_completion_uses_outcome(self):
        self.assertTrue(RECORDING_SESSION_SWIFT.is_file(),
                        f"{RECORDING_SESSION_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        code = strip_swift_comments(RECORDING_SESSION_SWIFT.read_text(encoding="utf-8"))
        masked = blank_swift_strings(code)
        sigs = list(re.finditer(r"\bfunc\s+complete\s*\(\s*finalizeCode\b", masked))
        self.assertEqual(len(sigs), 1, "RecordingSession.swift 應恰有一個 func complete(finalizeCode:)")
        body = swift_functions(code[sigs[0].start():])["complete"][0]
        self.assertTrue(re.search(r"(?<![\w.])completionOutcome\s*\(", blank_swift_strings(body)),
                         "complete(finalizeCode:) 的本體應呼叫 completionOutcome(（spec §4.4.9）")
        self.assertFalse(any("收尾失敗（" in l for l in swift_string_literals(body)),
                         "complete(finalizeCode:) 的本體不得再自行組「收尾失敗（」字串（交給 completionOutcome，spec §4.4.9）")

    # spec §4.4.10（t6 第二輪，缺陷 E／D22）：影片心跳的實作形狀；判定本身由 swift:SegmentsTests.swift::testShouldEmitVideoHeartbeat 驗
    def test_video_heartbeat_on_idle(self):
        self.assertTrue(CAPTURE_DIR.is_dir(), f"{CAPTURE_DIR.relative_to(REPO)} 不存在（不得因目錄不存在而跳過）")
        self.assertTrue(RECORDING_SESSION_SWIFT.is_file(),
                        f"{RECORDING_SESSION_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        allmasked = blank_swift_strings("\n".join(strip_swift_comments(t) for t in capture_sources(exclude=()).values()))
        name = "videoHeartbeatSeconds"
        defs = list(re.finditer(r"\b(?:let|var)\s+" + name + r"\s*(?::\s*[A-Za-z_][\w.]*\s*)?=\s*([0-9]+(?:\.[0-9]+)?)\b",
                                allmasked))
        self.assertEqual(len(defs), 1, f"Sources/Capture/ 應恰有一處定義 {name}（spec §4.4.10）")
        self.assertEqual(float(defs[0].group(1)), 1.0, f"{name} 應為 1.0（spec §4.4.10）")
        uses = len(re.findall(r"(?<![\w.])" + name + r"\b", allmasked)) + len(re.findall(r"\.\s*" + name + r"\b", allmasked))
        self.assertGreaterEqual(uses - 1, 1, f"{name} 除了定義以外應至少被引用一次（spec §4.4.10）")

        code = strip_swift_comments(RECORDING_SESSION_SWIFT.read_text(encoding="utf-8"))
        masked = blank_swift_strings(code)
        self.assertTrue(re.search(r"(?<![\w.])shouldEmitVideoHeartbeat\s*\(", masked),
                         "RecordingSession.swift 應呼叫 shouldEmitVideoHeartbeat(（spec §4.4.10）")
        retimed = re.findall(r"(?<![\w.])retimedVideoSample\s*\(", masked)
        self.assertGreaterEqual(len(retimed), 2,
                                "RecordingSession.swift 應至少兩處呼叫 retimedVideoSample(（換段首幀與心跳，spec §4.4.10）")
        funcs = swift_functions(code)

        def calls(body, fname):
            return re.search(r"(?<![\w.])" + re.escape(fname) + r"\s*\(", blank_swift_strings(body)) is not None

        hb = {n for n, bs in funcs.items() if any(calls(b, "shouldEmitVideoHeartbeat") for b in bs)}
        self.assertTrue(hb, "找不到本體呼叫 shouldEmitVideoHeartbeat( 的函式")
        callers = {n for n, bs in funcs.items() for b in bs for h in hb if n != h and calls(b, h)}
        idle_driven = sorted(n for n in hb | callers
                             if any(re.search(r"\.idle\b", blank_swift_strings(b)) for b in funcs[n]))
        self.assertTrue(idle_driven,
                        "呼叫 shouldEmitVideoHeartbeat 的函式或其呼叫者之中，至少一個的本體應出現 .idle"
                        "（心跳只由 idle sample 驅動，spec §4.4.10）")

    # spec §4.11.5
    def test_menubar_uses_template_image(self):
        allsrc = "\n".join(read_sources().values())
        self.assertIn("NSStatusItem", allsrc)
        for sym in ("record.circle", "record.circle.fill", "exclamationmark.triangle.fill"):
            self.assertIn(f'"{sym}"', allsrc, f"缺 SF Symbol {sym}")
        self.assertIn("systemSymbolName", allsrc)
        self.assertRegex(allsrc, r"isTemplate\s*=\s*true")

    # spec §4.11.8
    def test_menubar_sets_accessibility_label(self):
        allsrc = "\n".join(read_sources().values())
        self.assertIn("toolTip", allsrc)
        self.assertRegex(allsrc, r"setAccessibilityLabel|accessibilityLabel\s*=")

    # 設計審查 N-1／N-3、N-2（spec §6 第 73–75 條）
    def test_menubar_detail_tooltip_and_hotkey_fallback(self):
        src = MENUBAR_SWIFT.read_text(encoding="utf-8")
        self.assertRegex(src, r"setString\(model\.detailText",
                         "失敗類的完整訊息 detailText 應能從選單複製")
        self.assertRegex(src, r"if hotKey == nil[^}]*startItem\.keyEquivalent\s*=\s*\"\"",
                         "快捷鍵註冊失敗時應清掉選單上的 ⌃⌥⌘R")
        qs = (SOURCES / "Trigger" / "QuickStart.swift").read_text(encoding="utf-8")
        self.assertRegex(qs, r"notifyWarnings:\s*true", "quick-start 開錄時 preflight 的 warn 應送通知")
        cmd = (SOURCES / "Capture" / "Commands.swift").read_text(encoding="utf-8")
        self.assertIn("preflightWarnNotification(warnText:", cmd)

    # spec §4.2.8
    def test_entitlements_audio_and_apple_events(self):
        p = RESOURCES / "MeetingRecorder.entitlements"
        self.assertTrue(p.is_file(), f"{p} 不存在")
        ent = plistlib.loads(p.read_bytes())
        self.assertEqual(set(ent), {"com.apple.security.device.audio-input",
                                    "com.apple.security.automation.apple-events"})
        for k, v in ent.items():
            self.assertIs(v, True, f"{k} 應為 true")
        self.assertNotIn("com.apple.security.app-sandbox", ent)

    # spec §4.2.8、§4.15.11
    def test_info_plist_apple_events_usage(self):
        info = plistlib.loads((RESOURCES / "Info.plist").read_bytes())
        desc = info.get("NSAppleEventsUsageDescription", "")
        self.assertTrue(isinstance(desc, str) and desc.strip(), "NSAppleEventsUsageDescription 應非空")
        self.assertIn("Chrome", desc)
        self.assertIn("網址", desc)

    # spec §4.2.8
    def test_build_signs_with_entitlements(self):
        src = (MR / "build.sh").read_text(encoding="utf-8")
        joined = re.sub(r"\\\n\s*", " ", src)  # 接回續行
        calls = [l for l in joined.split("\n")
                 if re.search(r"codesign\s+--force", l) and not l.lstrip().startswith("#")]
        self.assertTrue(calls, "build.sh 應有 codesign --force 呼叫")
        for l in calls:
            self.assertIn("--entitlements", l, f"codesign --force 未帶 --entitlements：{l.strip()}")

    # spec §4.15.10
    def test_chrome_query_read_only(self):
        srcs = read_sources()
        defs = [p for p, s in srcs.items() if re.search(r"\b(?:let|var)\s+chromeTabsScript\b", s)]
        self.assertEqual(len(defs), 1, f"Sources/ 應恰有一檔定義 chromeTabsScript，實際：{defs}")
        p = defs[0]
        self.assertEqual(p.relative_to(SOURCES).as_posix(), "Capture/ChromeTabs.swift")
        s = srcs[p]
        script = swift_string_after(s, "chromeTabsScript")
        self.assertIsNotNone(script, "取不到 chromeTabsScript 的字串內容")
        self.assertTrue(script.strip())
        for bad in ("activate", "execute", "javascript", "make", "close", "set ", "reload", "open location"):
            self.assertNotIn(bad, script.lower(), f"chromeTabsScript 不得含 {bad!r}")
        self.assertIn("runningApplications(withBundleIdentifier", s)
        self.assertIn("AEDeterminePermissionToAutomateTarget", s)
        for q, t in srcs.items():
            self.assertNotIn("osascript", t, f"{q.relative_to(REPO)} 不得出現 osascript")

    # spec §4.6.20 (iv)（t6 第三輪，缺陷 J）：正規化時音訊寫 PCM；串接時影片 -c:v copy、音訊 -c:a aac 一次編碼，
    # 不得對音訊 -c copy／-c:a copy（concat demuxer 會丟掉各段 AAC 的 edit list，priming 與尾端補零變成真的音訊）
    def test_finalize_concat_reencodes_audio_once(self):
        self.assertTrue(FINALIZE_PY.is_file(), f"{FINALIZE_PY.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        tree = ast.parse(FINALIZE_PY.read_text(encoding="utf-8"))
        enc = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "encode"]
        self.assertEqual(len(enc), 1, "bin/_record_finalize.py 應恰有一個頂層 def encode（逐段正規化的編碼）")
        enc_calls = [call_constants(c) for c in ast.walk(enc[0]) if isinstance(c, ast.Call)]
        self.assertTrue(any(has_pair(a, "-c:a", "pcm_s16le") for a in enc_calls),
                        "正規化（encode）的音訊應寫 PCM：ffmpeg 參數應含相鄰的 \"-c:a\", \"pcm_s16le\"（spec §4.6.20 (iv)）")
        self.assertFalse(any(has_pair(a, "-c:a", "aac") for a in enc_calls),
                         "正規化（encode）不得再把音訊編成 AAC（音訊只在串接時編一次，spec §6 第 65 條）")
        calls = [call_constants(c) for c in ast.walk(tree) if isinstance(c, ast.Call)]
        concat = [a for a in calls if has_pair(a, "-f", "concat")]
        self.assertTrue(concat, "bin/_record_finalize.py 應有以 -f concat 串接的 ffmpeg 呼叫")
        for a in concat:
            self.assertTrue(has_pair(a, "-c:v", "copy"), f"串接應 -c:v copy（影片無損串接）：{a}")
            self.assertTrue(has_pair(a, "-c:a", "aac"), f"串接應 -c:a aac（音訊在這裡一次編碼，spec §4.6.20 (iv)）：{a}")
            for bad in (("-c", "copy"), ("-c:a", "copy")):
                self.assertFalse(has_pair(a, *bad), f"串接不得對音訊用 {' '.join(bad)}（spec §4.6.20 (iv)）：{a}")

    # spec §4.5.9（t6 第三輪，缺陷 L）：availableBytes 每次都讀新值，不沿用 URL 物件快取的 resourceValues
    def test_available_bytes_not_cached(self):
        self.assertTrue(PREFLIGHT_RUNNER_SWIFT.is_file(),
                        f"{PREFLIGHT_RUNNER_SWIFT.relative_to(REPO)} 不存在（不得因檔案不存在而跳過）")
        code = strip_swift_comments(PREFLIGHT_RUNNER_SWIFT.read_text(encoding="utf-8"))
        bodies = swift_functions(code).get("availableBytes", [])
        self.assertTrue(bodies, "PreflightRunner.swift 應有 func availableBytes")
        for b in bodies:
            mb = blank_swift_strings(b)
            self.assertTrue("removeAllCachedResourceValues" in mb or re.search(r"\bURL\s*\(\s*fileURLWithPath\s*:", mb),
                            "availableBytes 的本體應以 URL(fileURLWithPath:) 新建 URL 或呼叫 removeAllCachedResourceValues"
                            "（每次讀新值，spec §4.5.9）")

    # spec §4.2.12（t6 第三輪，發現 I）：只讀 com.apple.WindowManager 的 GloballyEnabled；不得改寫任何系統設定
    def test_stage_manager_read_only(self):
        srcs = read_sources()
        self.assertTrue(srcs, "Sources/ 沒有任何 .swift")
        code = "\n".join(strip_swift_comments(t) for t in srcs.values())
        for need in ("com.apple.WindowManager", "GloballyEnabled", "CFPreferencesCopyAppValue"):
            self.assertTrue(need in code, f"tools/MeetingRecorder/Sources/（不含註解）應出現 {need}（spec §4.2.12）")
        masked = blank_swift_strings(code)
        calls = [mt for mt in re.finditer(r"(?<!\w)stageManagerNotice\s*\(", masked)
                 if not re.search(r"\bfunc\s+$", masked[:mt.start()])]
        self.assertTrue(calls, "Sources/ 應呼叫 stageManagerNotice(（不只是定義，spec §4.2.12）")
        # 「不得出現」照 spec 字面：連註解也算；bin/ 下全部文字檔一起掃
        targets = dict(srcs)
        self.assertTrue(BIN_DIR.is_dir(), "bin/ 不存在（不得因目錄不存在而跳過）")
        for f in sorted(BIN_DIR.rglob("*")):
            if f.is_file():
                try:
                    targets[f] = f.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    continue
        hits = sorted(f"{q.relative_to(REPO)}：{bad}" for q, t in targets.items() for bad in SETTINGS_WRITES if bad in t)
        self.assertEqual(hits, [], "Sources/ 與 bin/ 不得改寫系統設定（spec §4.2.12）")

    # spec §4.14.1
    def test_no_media_in_repo(self):
        files = subprocess.run(["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True,
                               check=True).stdout.split("\n")
        st = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "-uall"], capture_output=True,
                            text=True, check=True).stdout.split("\n")
        bad = [f for f in files + st if f.strip().strip('"').lower().endswith(MEDIA_EXTS)]
        self.assertEqual(bad, [], "repo 內不得有媒體檔")

    # spec §4.14.2：以 git check-ignore 驗行為，不比對寫法
    def test_gitignore_media_rules(self):
        samples = ["範例根/20261011/範例場次/錄音/tracks/manifest.json",
                   "範例根/20261011/範例場次/影片/notes.txt",
                   "a.mov", "a.wav", "a.m4a", "a.mp4", "a.m4v", "a.mp3", "x/y/z.mov"]
        for s in samples:
            with self.subTest(path=s):
                r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", "--no-index", s])
                self.assertEqual(r.returncode, 0, f".gitignore 應忽略 {s}")

    # spec §4.14.3
    def test_no_client_names_in_repo_text(self):
        path = os.environ.get("MH_CLIENT_NAMES_FILE")
        if not path:
            self.skipTest("未設定 MH_CLIENT_NAMES_FILE，略過客戶名稱檢查")
        p = Path(path)
        self.assertTrue(p.is_file(), "MH_CLIENT_NAMES_FILE 指向的清單檔不存在")
        names = []
        for line in p.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                names.append(s)
        self.assertTrue(names, "名稱清單沒有任何有效行")
        tracked = subprocess.run(["git", "-C", str(REPO), "ls-files", "--error-unmatch", str(p.resolve())],
                                 capture_output=True)
        self.assertNotEqual(tracked.returncode, 0, "名稱清單檔不得被 git 追蹤")
        needles = [n.encode("utf-8") for n in names]
        hits = []
        for d in CLIENT_SCAN_DIRS:
            base = REPO / d
            if not base.exists():
                continue
            for f in sorted(base.rglob("*")):
                if not f.is_file() or f.resolve() == p.resolve():
                    continue
                for i, line in enumerate(f.read_bytes().split(b"\n"), start=1):
                    if any(n in line for n in needles):
                        hits.append(f"{f.relative_to(REPO).as_posix()}:{i}")
        # 只列路徑與行號，不印命中的字串
        self.assertFalse(hits, "repo 文字含名稱清單中的字串：\n" + "\n".join(hits))

    # 上一支的自我核對（函式名刻意不含 test_no_client_names_in_repo_text，-k 不會選到自己）
    def test_client_names_checker_self_check(self):
        def run_check(value):
            env = dict(os.environ)
            if value is None:
                env.pop("MH_CLIENT_NAMES_FILE", None)
            else:
                env["MH_CLIENT_NAMES_FILE"] = value
            return subprocess.run([sys.executable, "-m", "unittest", "-v",
                                   "tests.record.test_static_rules.TestStaticRules.test_no_client_names_in_repo_text"],
                                  cwd=str(REPO), env=env, capture_output=True, text=True, timeout=120)

        with tempfile.TemporaryDirectory() as d:
            one = Path(d) / "names.txt"
            one.write_text("範例專案\n", encoding="utf-8")
            r = run_check(str(one))
            self.assertNotEqual(r.returncode, 0, "清單含「範例專案」時應失敗")
            self.assertIn("specs/meeting-record/spec.md:", r.stderr)
            self.assertNotIn("範例專案", r.stderr, "失敗訊息不得印出命中的字串")
            empty = Path(d) / "empty.txt"
            empty.write_text("\n# 註解\n   \n", encoding="utf-8")
            self.assertNotEqual(run_check(str(empty)).returncode, 0, "清單沒有有效行時應失敗")
            self.assertNotEqual(run_check(str(Path(d) / "missing.txt")).returncode, 0, "清單檔不存在時應失敗")
        r = run_check(None)
        self.assertEqual(r.returncode, 0)
        self.assertIn("skipped", r.stderr)
        self.assertIn("未設定 MH_CLIENT_NAMES_FILE", r.stderr)


if __name__ == "__main__":
    unittest.main()

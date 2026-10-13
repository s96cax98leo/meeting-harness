"""R2 靜態規則（spec §4.16.4、§4.17.2、§4.18.2、§4.18.3、§4.19.2、§4.20.4–§4.20.6、§4.20.8、§4.21.3–§4.21.5、
§4.22.2、§4.22.4、§4.22.5、§4.23.2–§4.23.4）。

函式名前綴區分歸屬（design R2-D14）：test_capture_＝Sources/Capture/（r2e）、test_trigger_＝Sources/Trigger/（r2f）、
test_main_＝Sources/main.swift（r2f）；test_defaults_single_writer 掃整個 Sources/（紅燈階段就要綠）。
檔案不存在一律判 FAIL，不得跳過。
"""
import re
import unittest

from tests.record import test_static_rules as sr
from tests.record.surface import REPO

SOURCES = sr.SOURCES
CAPTURE = SOURCES / "Capture"
TRIGGER = SOURCES / "Trigger"
RECORDING_SESSION = CAPTURE / "RecordingSession.swift"
NOTIFIER = CAPTURE / "Notifier.swift"
MAIN_SWIFT = SOURCES / "main.swift"
MENUBAR = TRIGGER / "MenuBar.swift"
HOTKEY = TRIGGER / "HotKey.swift"
QUICKSTART = TRIGGER / "QuickStart.swift"
PREFERENCES = TRIGGER / "Preferences.swift"

# spec §4.20.6 的選單項標題（依序；收音指示列與狀態列沒有固定標題）
MENU_TITLES = ["複製完整訊息與補救指令", "開始錄製（用上次的設定）", "錄這個視窗", "存到", "暫停錄製", "麥克風靜音",
               "加標記", "停止錄製", "打開場次資料夾", "顯示上一場成品", "偏好設定…", "結束 MeetingRecorder 選單"]
CTRL_OPT_CMD = {".control", ".option", ".command"}


def rel(p):
    return p.relative_to(REPO).as_posix()


def code(tc, path):
    """去掉註解的原始碼；檔案不存在判 FAIL（不得跳過）。"""
    tc.assertTrue(path.is_file(), f"{rel(path)} 不存在（不得因檔案不存在而跳過）")
    return sr.strip_swift_comments(path.read_text(encoding="utf-8"))


def trigger_code(tc):
    files = sorted(TRIGGER.glob("*.swift"))
    tc.assertTrue(files, "Sources/Trigger/ 沒有任何 .swift")
    return "\n".join(sr.strip_swift_comments(p.read_text(encoding="utf-8")) for p in files)


def body(tc, src, name, must=None, where=""):
    """函式 name 的本體；同名多個時取含 must 的那一個。"""
    bodies = sr.swift_functions(src).get(name, [])
    if must is not None:
        bodies = [b for b in bodies if must in b]
    tc.assertTrue(bodies, f"{where} 找不到 func {name}" + (f"（含 {must}）" if must else ""))
    return bodies[0]


def objc_bodies(src):
    """@objc 函式的本體清單。"""
    funcs = sr.swift_functions(src)
    names = set(re.findall(r"@objc\b(?:\([^)]*\))?[^\n{]*?\bfunc\s+([A-Za-z_]\w*)", src))
    return [b for n in names for b in funcs.get(n, [])]


def assert_in_order(tc, src, needles, where):
    pos = []
    for n in needles:
        i = src.find(n)
        tc.assertGreaterEqual(i, 0, f"{where} 應含 {n!r}")
        pos.append(i)
    tc.assertEqual(pos, sorted(pos), f"{where} 中 {needles} 第一次出現的位置應依序遞增：{pos}")


def menu_item_var(tc, src, title):
    m = re.search(r"\b(\w+)\s*(?::\s*NSMenuItem\s*)?=\s*NSMenuItem\(\s*title:\s*\"" + re.escape(title)
                  + r"\"([^\n]*)", src)
    tc.assertIsNotNone(m, f"MenuBar.swift 應以 NSMenuItem(title: \"{title}\", …) 建立選單項")
    return m.group(1), m.group(2)


def assert_key(tc, src, title, key, mods):
    var, init_args = menu_item_var(tc, src, title)
    in_init = re.search(r'keyEquivalent:\s*"' + re.escape(key) + '"', init_args)
    assigned = re.search(r"\b" + re.escape(var) + r'\.keyEquivalent\s*=\s*"' + re.escape(key) + '"', src)
    tc.assertTrue(in_init or assigned, f"「{title}」的 keyEquivalent 應為 {key!r}")
    mm = re.search(r"\b" + re.escape(var) + r"\.keyEquivalentModifierMask\s*=\s*\[([^\]]*)\]", src)
    tc.assertIsNotNone(mm, f"「{title}」的 keyEquivalentModifierMask 應明寫")
    got = {x.strip() for x in mm.group(1).split(",") if x.strip()}
    tc.assertEqual(got, mods, f"「{title}」的修飾鍵")


class TestR2Static(unittest.TestCase):
    # 失敗訊息只列要找的字樣與說明，不把整段原始碼印出來
    def assert_has(self, needle, hay, msg=None):
        self.assertTrue(needle in hay, msg or f"應含 {needle!r}")

    def assert_hasnt(self, needle, hay, msg=None):
        self.assertFalse(needle in hay, msg or f"不得含 {needle!r}")

    def assert_re(self, text, pattern, msg=None):
        self.assertTrue(re.search(pattern, text), msg or f"應符合 /{pattern}/")

    def assert_no_re(self, text, pattern, msg=None):
        self.assertFalse(re.search(pattern, text), msg or f"不得符合 /{pattern}/")

    # ---------- Capture（r2e） ----------

    # spec §4.16.4
    def test_capture_sigusr1_handler_before_pid(self):
        src = code(self, RECORDING_SESSION)
        handlers = body(self, src, "installSignalHandlers", where="RecordingSession.swift")
        self.assert_has("SIGUSR1", handlers, "installSignalHandlers() 應加裝 SIGUSR1")
        self.assert_has("makeSignalSource", handlers, "SIGUSR1 應以與 SIGTERM 相同的 DispatchSource 模式處理")
        self.assert_re(handlers, r"queue:\s*q\b", "訊號處理應在序列佇列 q 上")
        for name in ("readControl(", "controlActions("):
            self.assert_has(name, src, f"收到 SIGUSR1 時應 {name}…")
        start = body(self, src, "start", must="installSignalHandlers()", where="RecordingSession.swift")
        assert_in_order(self, start, ["installSignalHandlers()", "resetControl(", "getpid()"],
                        "start() 本體（installSignalHandlers → resetControl → 寫 record.pid）")

    # spec §4.17.2
    def test_capture_mic_zeroed_before_rms(self):
        src = code(self, RECORDING_SESSION)
        cb = body(self, src, "stream", must="rmsDBFS(sampleBuffer:", where="RecordingSession.swift")
        assert_in_order(self, cb, ["zeroedAudioSample(", "rmsDBFS(sampleBuffer:"], "sample 回呼本體")
        self.assert_has("micSilence.reset()", src)
        self.assert_has("micMuteEvents", src)

    # spec §4.18.2
    def test_capture_pause_gate_before_maxend(self):
        src = code(self, RECORDING_SESSION)
        ingest = body(self, src, "ingest", where="RecordingSession.swift")
        self.assert_has("maxEnd =", ingest, "ingest 本體應含 maxEnd =")
        assert_in_order(self, ingest, ["pauseRoute(", "maxEnd ="], "ingest 本體（暫停閘門在 maxEnd 更新之前）")

    # spec §4.18.2、§4.18.3（閘門 2 修正輪）
    def test_capture_uses_core_pause_functions(self):
        for p in sorted(CAPTURE.glob("*.swift")):
            for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), start=1):
                self.assert_no_re(line, r"\benum\s+SwitchReason\b",
                                    f"{rel(p)}:{i} 不得宣告 enum SwitchReason（改用 Core/Segments.swift 的）")
        src = code(self, RECORDING_SESSION)
        for name in ("pausing(", "resuming(", "pauseRoute(", "segmentOpened(", "openReason(", "detectorFeed(",
                     ".interrupt(at:", "sysSilence.reset()", "micSilence.reset()", "appendingPauseEvent",
                     "pauseStatusFields", "applyingPauseFields", "appendingMuteEvent("):
            self.assert_has(name, src, f"RecordingSession.swift 應呼叫 Core 的 {name}")

    # spec §4.19.2
    def test_capture_markers_written(self):
        src = code(self, RECORDING_SESSION)
        for name in ('"markers.json"', "markerLabel(", "outputTime("):
            self.assert_has(name, src)

    # spec §4.23.3
    def test_capture_completion_notification_id(self):
        src = code(self, RECORDING_SESSION)
        comp = body(self, src, "complete", must="Notifier.post", where="RecordingSession.swift")
        self.assert_has("completionNotificationID(runId:", comp, "完成通知應以 completionNotificationID(runId:) 為識別碼")
        self.assert_has("identifier", code(self, NOTIFIER), "Notifier.post 應可指定識別碼")

    # ---------- main.swift（r2f） ----------

    # spec §4.16.4
    def test_main_ignores_sigusr1_before_dispatch(self):
        src = code(self, MAIN_SWIFT)
        m = re.search(r"signal\(\s*SIGUSR1\s*,\s*SIG_IGN\s*\)", src)
        self.assertIsNotNone(m, "main.swift 應 signal(SIGUSR1, SIG_IGN)")
        sw = re.search(r"(?m)^switch\b", src)
        self.assertIsNotNone(sw, "main.swift 應有頂層 switch 分派子指令")
        self.assertLess(m.start(), sw.start(), "signal(SIGUSR1, SIG_IGN) 應在子指令分派之前")

    # spec §4.22.2
    def test_main_launch_mode_dispatch(self):
        src = code(self, MAIN_SWIFT)
        self.assert_has("launchMode(arguments:", src, "main.swift 應以 launchMode(arguments:) 決定子指令")
        cases = re.findall(r"(?m)^\s*case\s+((?:\"[^\"]*\"\s*,?\s*)+):", src)
        labels = [re.findall(r"\"([^\"]*)\"", c) for c in cases]
        self.assertTrue(any("menubar" in ls for ls in labels), "應有 case \"menubar\"")
        helps = [ls for ls in labels if "help" in ls]
        self.assertTrue(helps, "help 仍印說明")
        for ls in helps:
            self.assert_hasnt("", ls, "無參數啟動應進 menubar，不再印 help")
            for h in ("-h", "--help"):
                self.assert_has(h, ls)

    # ---------- Trigger（r2f） ----------

    # spec §4.20.4
    def test_trigger_status_item_variable_length(self):
        src = code(self, MENUBAR)
        self.assert_re(src, r"\bvariableLength\b", "status item 應以 NSStatusItem.variableLength 建立")
        self.assert_hasnt("squareLength", src, "不得再用 squareLength")
        for k in ("monospacedDigitSystemFont", '"mic.slash"', "systemRed", "paletteColors", "symbolName",
                  "timerText"):
            self.assert_has(k, src, f"MenuBar.swift 應含 {k}")
        # t7（spec §6 第 107 條）：macOS 26 選單列上 template image＋contentTintColor 會畫成透明，紅色改用 paletteColors
        self.assert_hasnt("contentTintColor", src, "status item 不得用 contentTintColor 染色（macOS 26 會畫成透明）")

    # spec §4.20.5
    def test_trigger_hotkeys_distinct_ids(self):
        hk = code(self, HOTKEY)
        self.assert_no_re(hk, r"id:\s*1\)", "HotKey.swift 不得寫死 id: 1)")
        self.assert_re(hk, r"init\?\s*\([^)]*\bid:", "HotKey 應以呼叫端給的 id 註冊")
        for k in ("GetEventParameter", "kEventParamDirectObject", "typeEventHotKeyID", "eventNotHandledErr"):
            self.assert_has(k, hk, f"HotKey 的 handler 應以 {k} 比對事件 id")
        mb = code(self, MENUBAR)
        self.assert_has("r2HotKeys", mb, "menu bar 應依 r2HotKeys 註冊四組")

    # spec §4.20.6
    def test_trigger_menu_items_r2(self):
        src = code(self, MENUBAR)
        assert_in_order(self, src, MENU_TITLES, "Trigger/MenuBar.swift")
        for title, key in (("暫停錄製", "p"), ("麥克風靜音", "m"), ("加標記", "b")):
            with self.subTest(item=title):
                assert_key(self, src, title, key, CTRL_OPT_CMD)
        assert_key(self, src, "偏好設定…", ",", {".command"})
        self.assert_has("繼續錄製", src, "暫停中標題改「繼續錄製」")
        self.assert_has("canControl", src, "暫停、麥克風靜音、加標記的可用性＝canControl")
        self.assert_has("levelLine", src, "收音指示列")

    # spec §4.20.8
    def test_trigger_control_uses_availability(self):
        src = code(self, MENUBAR)
        for k in ("controlAvailability(", "requestControl(", "SIGUSR1"):
            self.assert_has(k, src)
        for i, line in enumerate(src.split("\n"), start=1):
            if "SIGUSR1" in line:
                for bad in ("st.pid", "status.pid", ".pid ??"):
                    self.assert_hasnt(bad, line, f"MenuBar.swift:{i} 送 SIGUSR1 的 pid 只能來自 .ready(pid:)")

    # spec §4.21.3
    def test_trigger_quick_start_explicit_window(self):
        src = code(self, QUICKSTART)
        for k in ("explicitWindowDecision(", "quickStartRoot(", "resolveWindow(", "quickStartDecision(",
                  "loadMenuBarPrefs("):
            self.assert_has(k, src, f"QuickStart.swift 應含 {k}")
        self.assert_no_re(src, r"askAutomation:\s*true", "quick-start 不得跳 Apple Events 授權框")

    # spec §4.21.4
    def test_trigger_window_list_via_open(self):
        mb = code(self, MENUBAR)
        for p in (MENUBAR, PREFERENCES):
            if p.is_file():
                s = code(self, p)
                for bad in ("SCShareableContent", "WindowListing.load("):
                    self.assert_hasnt(bad, s, f"{rel(p)} 不得呼叫 SCK（{bad}）")
        for k in ('"windows"', '"--json"', '"--log"', '"quick-start"', '"--window-bundle"', '"--window-title"',
                  "讀取視窗清單中…", "取不到視窗清單"):
            self.assert_has(k, mb, f"MenuBar.swift 應含 {k}")
        self.assert_re(mb, r"truncatedStatusTitle\([^)]*limit:\s*60\s*\)", "每列標題為 truncatedStatusTitle(label, limit: 60)")
        self.assert_hasnt("--ask-automation", mb, "子選單取清單不帶 --ask-automation")

    # spec §4.21.5
    def test_trigger_prefs_and_open_panel(self):
        src = trigger_code(self)
        for k in ("NSOpenPanel", "選擇資料夾…", "（找不到）", "updatedRecentRoots(", "saveMenuBarPrefs(",
                  "loadMenuBarPrefs("):
            self.assert_has(k, src, f"Sources/Trigger/ 應含 {k}")
        for k, v in (("canChooseDirectories", "true"), ("canChooseFiles", "false"), ("canCreateDirectories", "true")):
            self.assert_re(src, r"\." + k + r"\s*=\s*" + v + r"\b", f"NSOpenPanel 的 {k} 應為 {v}")
        self.assert_re(src, r"updatedRecentRoots\([^)]*limit:\s*5\s*\)", "recentRoots 最多 5 個")

    # spec §4.21.5（R2-Q3 使用者決定：record.defaults.json 維持 record.sh 單一寫者）——紅燈階段就要綠
    def test_defaults_single_writer(self):
        files = sorted(SOURCES.rglob("*.swift"))
        self.assertTrue(files)
        hits = []
        for p in files:
            for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), start=1):
                if ("writeJSONAtomically(" in line or ".write(to:" in line) and "defaults" in line.lower():
                    hits.append(f"{rel(p)}:{i}")
        self.assertEqual(hits, [], "Sources/ 不得寫 record.defaults.json")

    # spec §4.22.4
    def test_trigger_preferences_window(self):
        src = code(self, PREFERENCES)
        for k in ("MeetingRecorder 設定", "預設存檔位置", "更改…", "登入時自動開啟", "停止後自動跑前處理",
                  "打開系統設定的登入項目", "openSystemSettingsLoginItems", "loginItemDisplay(", "r2HotKeys",
                  "註冊失敗", "autoPrep"):
            self.assert_has(k, src, f"Trigger/Preferences.swift 應含 {k}")
        self.assert_hasnt(".resizable", src, "偏好設定視窗不可縮放")

    # 設計審查 R2 SF-2（spec §6 第 101 條）：app 沒有 main menu，偏好設定視窗要自己接 ⌘W 與 Esc
    def test_trigger_preferences_closes_with_cmd_w_and_esc(self):
        src = code(self, PREFERENCES)
        self.assert_has("cancelOperation", src, "Esc 應關閉偏好設定視窗")
        self.assert_has("performKeyEquivalent", src, "⌘W 應關閉偏好設定視窗")
        self.assert_hasnt("開機：", src, "標籤與勾選框用同一個詞「登入」")

    # spec §4.22.5
    def test_trigger_login_item_only_in_preferences(self):
        prefs = code(self, PREFERENCES)
        self.assert_has("SMAppService", prefs, "登入項目應在 Trigger/Preferences.swift 處理")
        for p in sorted(SOURCES.rglob("*.swift")):
            if p != PREFERENCES:
                self.assert_hasnt("SMAppService", sr.strip_swift_comments(p.read_text(encoding="utf-8")),
                                 f"SMAppService 只得出現在 Trigger/Preferences.swift：{rel(p)}")
        calls = re.findall(r"\.(?:un)?register\(\)", prefs)
        self.assert_has(".register()", calls)
        self.assert_has(".unregister()", calls)
        inside = sum(len(re.findall(r"\.(?:un)?register\(\)", b)) for b in objc_bodies(prefs))
        self.assertEqual(inside, len(calls), ".register()／.unregister() 只得在勾選框的 @objc 動作函式內呼叫")
        mb = code(self, MENUBAR)
        for fn in ("setup", "runMenuBar"):
            b = body(self, mb, fn, where="MenuBar.swift")
            self.assert_no_re(b, r"\bregister\(", f"MenuBar.swift 的 {fn} 不得註冊登入項目")

    # spec §4.23.2
    def test_trigger_autoprep_session_prep(self):
        src = trigger_code(self)
        for k in ('"prep"', "autoprep.log", "terminationHandler", "shouldAutoPrep(", "lastAutoPrepRunId",
                  "meeting.sh"):
            self.assert_has(k, src, f"Sources/Trigger/ 應含 {k}")
        self.assert_hasnt("waitUntilExit", code(self, MENUBAR), "主執行緒不得 waitUntilExit")

    # spec §4.23.3、§4.23.4
    def test_trigger_completion_notification_category(self):
        src = trigger_code(self)
        for k in ("completionNotificationID(", "completionCategoryID", "revealActionID", "在 Finder 顯示",
                  "UNUserNotificationCenterDelegate", "activateFileViewerSelecting", "顯示上一場成品",
                  "lastSession"):
            self.assert_has(k, src, f"Sources/Trigger/ 應含 {k}")


if __name__ == "__main__":
    unittest.main()

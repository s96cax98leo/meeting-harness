"""R3 app 端只能靜態檢查的實作形狀（spec §4.26–§4.44 測試欄的 test_r3_app_static.py::<類別>.<函式>）。

類別名對應子任務（不因子任務合併而改名）：LockStatic、MenuBarStatesStatic、FinalizeRunnerStatic、NotifyStatic、
RemindersStatic、LatencyLogStatic、HudStatic、DiscardStatic、MenuStagesStatic、SegmentSchedulerStatic、
OnboardingSettingsStatic、SyncCompensateStatic、MeetingDetectStatic。
只讀 tools/MeetingRecorder/ 的原始碼與資源（去掉註解後比對）；檔案不存在一律判 FAIL，不得跳過。
entitlements 的項數由 test_static_rules.py::test_entitlements_audio_and_apple_events 驗（§6 第 138 條），本檔不重複。
"""
import os
import plistlib
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.record import test_static_rules as sr
from tests.record.surface import REPO

MR = sr.MR
SOURCES = sr.SOURCES
RESOURCES = sr.RESOURCES
CAPTURE = SOURCES / "Capture"
TRIGGER = SOURCES / "Trigger"
CORE = SOURCES / "Core"
MAIN_SWIFT = SOURCES / "main.swift"
COMMANDS = CAPTURE / "Commands.swift"
PREFLIGHT_RUNNER = CAPTURE / "PreflightRunner.swift"
RECORDING_SESSION = CAPTURE / "RecordingSession.swift"
FINALIZE_RUNNER = CAPTURE / "FinalizeRunner.swift"
NOTIFIER = CAPTURE / "Notifier.swift"
REMINDERS = CAPTURE / "Reminders.swift"
AUDIO_MONITOR = CAPTURE / "AudioDeviceMonitor.swift"
MENUBAR = TRIGGER / "MenuBar.swift"
HUD = TRIGGER / "HUD.swift"
DISCARD = TRIGGER / "Discard.swift"
FAILURE_DETAIL = TRIGGER / "FailureDetail.swift"
LEVEL_METER = TRIGGER / "LevelMeterView.swift"
ONBOARDING = TRIGGER / "Onboarding.swift"
MEETING_DETECT = TRIGGER / "MeetingDetect.swift"
PREFERENCES = TRIGGER / "Preferences.swift"
INFO_PLIST = RESOURCES / "Info.plist"
APP_ICON = RESOURCES / "AppIcon.icns"
BUILD_SH = MR / "build.sh"
ICONSET = ["icon_16x16.png", "icon_16x16@2x.png", "icon_32x32.png", "icon_32x32@2x.png", "icon_128x128.png",
           "icon_128x128@2x.png", "icon_256x256.png", "icon_256x256@2x.png", "icon_512x512.png", "icon_512x512@2x.png"]


def rel(p):
    return p.relative_to(REPO).as_posix()


def code(tc, path):
    """去掉註解的原始碼；檔案不存在判 FAIL（不得跳過）。"""
    tc.assertTrue(path.is_file(), f"{rel(path)} 不存在（不得因檔案不存在而跳過）")
    return sr.strip_swift_comments(path.read_text(encoding="utf-8"))


def dir_code(tc, d):
    files = sorted(d.glob("*.swift"))
    tc.assertTrue(files, f"{rel(d)} 沒有任何 .swift")
    return "\n".join(sr.strip_swift_comments(p.read_text(encoding="utf-8")) for p in files)


def assert_has(tc, src, needles, where):
    missing = [n for n in needles if n not in src]
    tc.assertEqual(missing, [], f"{where} 缺少：{missing}")


def assert_lacks(tc, src, needles, where):
    found = [n for n in needles if n in src]
    tc.assertEqual(found, [], f"{where} 不得出現：{found}")


def bodies_containing(src, needle):
    return [b for bs in sr.swift_functions(src).values() for b in bs if needle in b]


def info_plist(tc):
    tc.assertTrue(INFO_PLIST.is_file(), f"{rel(INFO_PLIST)} 不存在")
    with open(INFO_PLIST, "rb") as f:
        return plistlib.load(f)


class LockStatic(unittest.TestCase):
    # spec §4.26.2：start／quick-start／preflight 在 StatusWriter( 之前 acquireRecordLock(；被持有時「已有錄製在跑」
    def test_lock_before_status_writer(self):
        for path in (COMMANDS, PREFLIGHT_RUNNER):
            with self.subTest(file=path.name):
                src = code(self, path)
                a = src.find("acquireRecordLock(")
                self.assertGreaterEqual(a, 0, f"{rel(path)} 應呼叫 acquireRecordLock(")
                s = src.find("StatusWriter(")
                if s >= 0:
                    self.assertLess(a, s, f"{rel(path)} 的 acquireRecordLock( 應早於 StatusWriter(")
        assert_has(self, dir_code(self, CAPTURE), ["已有錄製在跑", ".heldByOther"], "Sources/Capture/")

    # spec §4.26.6：RecordingSession.swift 含 pausedHeartbeatSeconds，暫停分支會呼叫狀態寫入
    def test_paused_heartbeat(self):
        src = code(self, RECORDING_SESSION)
        self.assertIn("pausedHeartbeatSeconds", src)
        hb = bodies_containing(src, "pausedHeartbeatSeconds")
        self.assertTrue(hb, "pausedHeartbeatSeconds 應在某個函式內使用")
        self.assertTrue(any("status.update" in b for b in hb), "暫停心跳的函式應呼叫 status.update 重寫狀態檔")


class MenuBarStatesStatic(unittest.TestCase):
    # spec §4.38.3、§4.38.7、§6 第 135 條：U1-C 錄製膠囊的自繪、token 取色、無障礙標籤
    def test_capsule_drawing(self):
        src = code(self, MENUBAR)
        assert_has(self, src, ["menuBarCapsuleStyle(", "NSImage(size:", "flipped:", "isTemplate = false",
                               "\"record.circle\"", "\"mic.slash\"", "paletteColors", "monospacedDigitSystemFont",
                               "DarkroomType.capsule", "DarkroomColor.", "effectiveAppearance",
                               "accessibilityDisplayShouldIncreaseContrast", "showTimer",
                               "menuBarAccessibilityLabel("], rel(MENUBAR))
        assert_lacks(self, src, ["systemRed", "contentTintColor"], rel(MENUBAR))
        for ln in src.splitlines():
            if "button.toolTip" in ln or "button.setAccessibilityLabel" in ln:
                self.assertNotIn("accessibilityText", ln, f"status item 的 toolTip／accessibilityLabel 應改用 "
                                                          f"menuBarAccessibilityLabel：{ln.strip()}")

    # spec §4.38.4：status item 設 autosaveName
    def test_autosave_name(self):
        self.assertIn("autosaveName", code(self, MENUBAR))

    # spec §4.27.4：停止與捨棄送 SIGTERM 前呼叫 stopTargetDecision；含 SIGTERM 的行不含 st.pid／status.pid／?? st
    def test_stop_uses_decision(self):
        src = code(self, MENUBAR)
        self.assertIn("stopTargetDecision(", src)
        for ln in src.splitlines():
            if "SIGTERM" in ln:
                for bad in ("st.pid", "status.pid", "?? st"):
                    self.assertNotIn(bad, ln, f"含 SIGTERM 的行不得含 {bad}：{ln.strip()}")
        for b in bodies_containing(src, "SIGTERM"):
            self.assertTrue("stopTargetDecision(" in b or ".signal(pid" in b,
                            "送 SIGTERM 的函式應經 stopTargetDecision 的 .signal(pid:) 決定")


class FinalizeRunnerStatic(unittest.TestCase):
    # spec §4.28.6：FinalizeRunner.swift 含 finalizeDeadline(、SIGKILL；requestStop 在收尾中不再直接 return（含取消分支）
    def test_deadline_and_cancel(self):
        fr = code(self, FINALIZE_RUNNER)
        assert_has(self, fr, ["finalizeDeadline(", "SIGKILL", "SIGTERM"], rel(FINALIZE_RUNNER))
        cap = dir_code(self, CAPTURE)
        assert_has(self, cap, ["收尾逾時", "收尾已取消", "meeting record finish"], "Sources/Capture/")
        rs = code(self, RECORDING_SESSION)
        bodies = sr.swift_functions(rs).get("requestStop", [])
        self.assertTrue(bodies, "RecordingSession.swift 應有 requestStop")
        b = bodies[0]
        self.assertIsNone(re.search(r"guard\s+!stopping\s+else\s*\{\s*return\s*\}", b),
                          "requestStop 在收尾中不得直接 return")
        self.assertTrue("取消" in b or "cancel" in b.lower(), "requestStop 應有收尾中取消的分支")
        self.assertIn("FinalizeRunner", rs, "RecordingSession.swift 應以 FinalizeRunner 執行收尾")


class NotifyStatic(unittest.TestCase):
    # spec §4.39.3：Notifier.swift 含 interruptionLevel、threadIdentifier；MenuBar.swift 呼叫 newAlertWarnings(
    def test_policy_applied(self):
        assert_has(self, code(self, NOTIFIER), ["interruptionLevel", "threadIdentifier"], rel(NOTIFIER))
        assert_has(self, code(self, MENUBAR), ["newAlertWarnings(", "notificationPolicy("], rel(MENUBAR))


class RemindersStatic(unittest.TestCase):
    # spec §4.34.3：EventKit 的形狀、main.swift 分派 reminders、Info.plist 的提醒事項權限說明含 iCloud
    def test_eventkit_shape(self):
        src = code(self, REMINDERS)
        assert_has(self, src, ["requestFullAccessToReminders", "fetchRemindersMatchingPredicate",
                               "meetingharness://action/", "saveReminder"], rel(REMINDERS))
        assert_lacks(self, src, ["saveCalendar"], rel(REMINDERS))
        self.assertRegex(code(self, MAIN_SWIFT), r'case\s+"reminders"', "main.swift 應分派 reminders")
        plist = info_plist(self)
        keys = [k for k in plist if re.fullmatch(r"NSReminders\w*UsageDescription", k)]
        self.assertTrue(keys, "Info.plist 應有提醒事項權限說明鍵（NSReminders…UsageDescription）")
        self.assertTrue(all("iCloud" in str(plist[k]) for k in keys), "提醒事項權限說明應提到 iCloud")


class LatencyLogStatic(unittest.TestCase):
    # spec §4.35.7：只用 AudioObjectGetPropertyData 讀四項延遲；AudioDeviceInfo 宣告不含 latency
    def test_latency_read_only(self):
        assert_has(self, code(self, AUDIO_MONITOR), ["kAudioDevicePropertyLatency", "kAudioDevicePropertySafetyOffset",
                                                     "kAudioStreamPropertyLatency",
                                                     "kAudioDevicePropertyBufferFrameSize",
                                                     "AudioObjectGetPropertyData"], rel(AUDIO_MONITOR))
        all_src = "\n".join(sr.strip_swift_comments(p.read_text(encoding="utf-8")) for p in SOURCES.rglob("*.swift"))
        self.assertNotIn("AudioObjectSetPropertyData", all_src)
        self.assertIn("outputLatencies", code(self, RECORDING_SESSION), "錄製實例應 append outputLatencies")
        core = dir_code(self, CORE)
        m = re.search(r"struct\s+AudioDeviceInfo\b[^{]*\{", core)
        self.assertIsNotNone(m, "Core 應有 struct AudioDeviceInfo")
        depth, i = 0, m.end() - 1
        while i < len(core):
            depth += {"{": 1, "}": -1}.get(core[i], 0)
            if depth == 0:
                break
            i += 1
        self.assertNotIn("latency", core[m.start():i + 1].lower(), "AudioDeviceInfo 的宣告區塊不得含 latency")


class HudStatic(unittest.TestCase):
    # spec §4.40.4：非啟用 NSPanel、所有桌面、不被分享、一律深色、兩路音量條、四顆按鈕走同一條控制路徑
    def test_panel_shape(self):
        src = code(self, HUD)
        assert_has(self, src, ["nonactivatingPanel", "sharingType = .none", "canJoinAllSpaces", "setAccessibilityLabel",
                               "hudPosition", "hudTabTopFraction", "levelFraction(", "darkAqua",
                               "controlAvailability(", "stopTargetDecision(", "\"錄製中\"", "\"已暫停\"", "\"已靜音\"",
                               "\"暫停\"", "\"繼續\"", "\"靜音\"", "\"取消靜音\"", "\"標記\"", "\"停止\""], rel(HUD))
        assert_lacks(self, src, ["systemRed", "場次"], rel(HUD))

    # spec §4.40.4：收合時貼螢幕邊緣的直立標籤、展開面板的尺寸與底色都取自 token
    def test_edge_tab(self):
        src = code(self, HUD)
        assert_has(self, src, ["hudTabWidth", "hudTabHeight", "hudTabCornerRadius", "hudTabDot", "hudTabTimer",
                               "visibleFrame", "NSScreen.main", "hudPanelWidth", "hudPanelPadding",
                               "hudPanelCornerRadius", "hudButtonHeight", "hudButtonCornerRadius", "hudButtonGap",
                               "hudCollapseDelaySeconds", "DarkroomColor.surface", "lineStrong", "0.94", "0.96"],
                   rel(HUD))

    # spec §4.40.5、§6 第 120 條：快捷鍵回饋依 feedbackRoute，只有 .notification 才發通知（hotkeyFeedback）
    def test_feedback_route_used(self):
        src = code(self, MENUBAR)
        assert_has(self, src, ["feedbackRoute(", ".hotkeyFeedback"], rel(MENUBAR))
        notify_lines = [i for i, ln in enumerate(src.splitlines()) if "controlFeedback(" in ln
                        and ("notify" in ln or "Notifier" in ln)]
        lines = src.splitlines()
        for i in notify_lines:
            ctx = "\n".join(lines[max(0, i - 8):i])
            self.assertIn(".notification", ctx, f"第 {i + 1} 行的回饋通知應在 feedbackRoute 為 .notification 的分支內")

    # spec §4.40.7：告警加強（外框 attention、自動展開 hudAlertExpandSeconds、告警膠囊）
    def test_alert_emphasis(self):
        src = code(self, HUD)
        assert_has(self, src, ["hudAlertExpandSeconds", "attention", "onAttention", "hudAlert"], rel(HUD))
        self.assertTrue("newAlertWarnings(" in src or "newAlertWarnings(" in code(self, MENUBAR),
                        "新告警由 newAlertWarnings( 判定（HUD.swift 或 MenuBar.swift）")

    # spec §4.40.8：無障礙標籤、按鈕字面、減少透明度／增加對比／減少動態效果
    def test_accessibility_modes(self):
        src = code(self, HUD)
        assert_has(self, src, ["錄製小窗：", "暫停錄製（⌃⌥⌘P）", "繼續錄製（⌃⌥⌘P）", "麥克風靜音（⌃⌥⌘M）",
                               "取消麥克風靜音（⌃⌥⌘M）", "加標記（⌃⌥⌘B）", "停止錄製並收尾", "toolTip",
                               "setAccessibilityValue", "accessibilityDisplayShouldReduceTransparency",
                               "accessibilityDisplayShouldIncreaseContrast", "accessibilityDisplayShouldReduceMotion",
                               "hudAnimationSeconds"], rel(HUD))


class DiscardStatic(unittest.TestCase):
    # spec §4.42.2：先 NSApp.activate 再 NSAlert；字面、預設鍵「繼續錄製」、破壞性按鈕沒有快捷鍵
    def test_confirm_then_request(self):
        src = code(self, DISCARD)
        assert_has(self, src, ["NSAlert", "NSApp.activate", "hasDestructiveAction", "keyEquivalent = \"\"",
                               "record.discard.json", "捨棄這次錄製？",
                               "會停止錄製、不收尾、不產生成品；這場的錄音資料夾會移到垃圾桶，可從垃圾桶復原。",
                               "\"繼續錄製\"", "\"捨棄並移到垃圾桶\"", "spokenDuration"], rel(DISCARD))
        a = src.find("addButton(withTitle: \"繼續錄製\"")
        b = src.find("addButton(withTitle: \"捨棄並移到垃圾桶\"")
        self.assertGreaterEqual(a, 0, "應 addButton(withTitle: \"繼續錄製\")")
        self.assertGreaterEqual(b, 0, "應 addButton(withTitle: \"捨棄並移到垃圾桶\")")
        self.assertLess(a, b, "「繼續錄製」應是第一顆（預設鍵）")
        self.assertLess(src.find("NSApp.activate"), src.find("runModal"), "先 NSApp.activate 再顯示對話框")

    # spec §4.42.3：trashItem 移到垃圾桶；不對場次路徑呼叫 removeItem(；discarded=true
    def test_trash_not_delete(self):
        cap = dir_code(self, CAPTURE)
        assert_has(self, cap, ["trashItem(at:", "resultingItemURL", "discardRequestValid(", "discarded = true"],
                   "Sources/Capture/")
        for ln in cap.splitlines():
            if "removeItem(" in ln:
                arg = ln[ln.index("removeItem("):]
                self.assertIsNone(re.search(r"sess|session|錄音|recDir|\brec\b", arg, re.I),
                                  f"不得對場次路徑呼叫 removeItem(：{ln.strip()}")

    # spec §4.42.4：無效請求照一般停止；開錄時殘留的 record.discard.json 會被刪除
    def test_stale_request_ignored(self):
        cap = dir_code(self, CAPTURE)
        self.assertIn("record.discard.json", cap)
        self.assertTrue(any("removeItem(" in ln and "discard" in ln.lower() for ln in cap.splitlines()),
                        "開錄時應刪除殘留的 record.discard.json")
        self.assertRegex(cap, r"(if|guard)[^\n{]*discardRequestValid\(", "應以 discardRequestValid( 判斷，無效時照一般停止")


class MenuStagesStatic(unittest.TestCase):
    NEW_TITLES = ["錄其他視窗", "停止錄製並收尾", "設定…", "捨棄這次錄製…", "取消收尾", "錯誤詳情…", "顯示錄製小窗",
                  "開始錄製：", "加標記（已有"]

    # spec §4.41.3：只顯示 menuItems(stage:) 的項目、組間分隔線、標題列與告警列
    def test_menu_built_from_stage(self):
        src = code(self, MENUBAR)
        self.assertTrue("menuItems(stage:" in src or "menuGroups(stage:" in src, "應以 menuItems／menuGroups(stage: 建選單")
        assert_has(self, src, ["isHidden", "MenuItemID", "NSMenuItem.separator()", "truncatedStatusTitle(",
                               "exclamationmark.triangle.fill", "attentionText", "attentionTextOnLight",
                               "attributedTitle", "LevelMeterView"], rel(MENUBAR))

    # spec §4.41.3、§6 第 134 條：U6-A 稿的標題字面；舊字面「錄這個視窗」「偏好設定…」不再出現
    def test_titles_r3(self):
        src = code(self, MENUBAR)
        assert_has(self, src, self.NEW_TITLES, rel(MENUBAR))
        assert_lacks(self, src, ["\"錄這個視窗\"", "\"偏好設定…\"", "\"停止錄製\""], rel(MENUBAR))

    # spec §4.41.4：自訂 LevelMeterView、accessibilityValue、levelFraction
    def test_level_meter_accessibility(self):
        src = code(self, LEVEL_METER)
        assert_has(self, src, ["setAccessibilityValue", "levelFraction(", "系統聲音", "麥克風", "有聲", "無聲", "已靜音",
                               "menuMeterWidth", "meterBarHeight", "meterLabelWidth", "menuMeterLabel"], rel(LEVEL_METER))
        self.assertIn("levelMeterRefreshSeconds", src + code(self, MENUBAR))

    # spec §4.41.5：失敗詳情小視窗
    def test_failure_detail(self):
        src = code(self, FAILURE_DETAIL)
        assert_has(self, src, ["錯誤詳情", "複製完整訊息與補救指令", "monospacedSystemFont", "cancelOperation",
                               ".titled", ".closable", "480"], rel(FAILURE_DETAIL))
        assert_lacks(self, src, [".resizable"], rel(FAILURE_DETAIL))

    # spec §4.41.6：「取消收尾」經 stopTargetDecision 送 SIGTERM
    def test_cancel_finalize(self):
        src = code(self, MENUBAR)
        assert_has(self, src, ["取消收尾", ".cancelFinalize", "stopTargetDecision("], rel(MENUBAR))


class SegmentSchedulerStatic(unittest.TestCase):
    # spec §4.36.10：RecordingSession 只依 SegmentScheduler.handle 的動作開段、寫入、收段
    def test_session_delegates_to_scheduler(self):
        src = code(self, RECORDING_SESSION)
        assert_has(self, src, ["SegmentScheduler", ".handle(", ".outputDeviceChange"], rel(RECORDING_SESSION))
        ingest = sr.swift_functions(src).get("ingest", [])
        self.assertTrue(ingest, "RecordingSession.swift 應有 ingest")
        for b in ingest:
            assert_lacks(self, b, ["openReason(", "routeSample(", "shouldSwitchForFormat("], "RecordingSession.ingest")


class SyncCompensateStatic(unittest.TestCase):
    # spec §4.37.6：輸出裝置變更時提前換段（不論 mode）
    def test_device_change_split(self):
        src = code(self, RECORDING_SESSION)
        bodies = bodies_containing(src, "deviceEvents.append")
        self.assertTrue(bodies, "RecordingSession.swift 應在某個函式 append deviceEvents")
        self.assertTrue(any("outputDeviceChange" in b for b in bodies),
                        "記錄輸出裝置變更的函式應交給 SegmentScheduler（.outputDeviceChange）提前換段")
        for b in bodies:
            self.assertNotIn("syncCompensation", b, "提前換段不論 mode")


class OnboardingSettingsStatic(unittest.TestCase):
    # spec §4.43.5、§6 第 139 條：U4-A 5 步精靈；試錄在 temporaryDirectory、removeItem 只刪試錄路徑
    def test_onboarding_flow_shape(self):
        src = code(self, ONBOARDING)
        assert_has(self, src, ["writeOnboardingDefaults(", "歡迎", "權限", "存檔位置", "選單列空間", "試錄",
                               "先給三個權限", "共 5 步", "DarkroomMetric.onboardingWidth", "temporaryDirectory",
                               "meeting-harness-trial-", "略過", "上一步", "下一步", "完成", "螢幕錄製", "麥克風", "通知",
                               "自動化（Chrome）", "選用", "已允許", "需要重新開啟", "尚未允許", "被拒，要到系統設定打開",
                               "改成一律顯示錄製小窗", "onboardingCompletedAt", "recentLevels"], rel(ONBOARDING))
        m = re.search(r"\b(?:let|var)\s+(\w+)\b[^\n]*meeting-harness-trial-", src)
        self.assertIsNotNone(m, "試錄路徑應存在一個變數（其值含 meeting-harness-trial-）")
        var = m.group(1)
        removes = re.findall(r"removeItem\(\s*at:\s*([^)\n]+)\)", src)
        self.assertTrue(removes, "試錄結束應以 removeItem 刪除暫存目錄")
        for arg in removes:
            self.assertEqual(arg.strip(), var, f"removeItem( 的參數只能是試錄路徑變數 {var}：{arg.strip()}")
        trig = {p.name: sr.strip_swift_comments(p.read_text(encoding="utf-8")) for p in TRIGGER.glob("*.swift")}
        callers = sorted(n for n, s in trig.items() if "writeOnboardingDefaults(" in s)
        self.assertEqual(callers, ["Onboarding.swift"], "Trigger 中呼叫 writeOnboardingDefaults 的只有 Onboarding.swift")

    # spec §4.43.6、§6 第 130 條：7 個工具列分頁、視窗標題跟著分頁、記住上次分頁
    def test_settings_tabs(self):
        src = code(self, PREFERENCES)
        assert_has(self, src, ["NSToolbar", "lastSettingsTab", "settingsTab(", "SettingsTab", "\"自動\"", "\"一律顯示\"",
                               "\"不要\"", "\"右邊緣\"", "\"左邊緣\"", "用時效性通知（可穿過專注模式）", "重新執行首次設定…",
                               "用 meeting sync 修改"], rel(PREFERENCES))
        assert_lacks(self, src, ["\"MeetingRecorder 設定\"", ".resizable"], rel(PREFERENCES))

    # spec §4.43.7：AppIcon.icns 的 10 張、CFBundleIconFile、build.sh 複製進 Contents/Resources/
    def test_app_icon_bundled(self):
        self.assertTrue(APP_ICON.is_file(), f"{rel(APP_ICON)} 不存在")
        d = Path(tempfile.mkdtemp(prefix="mh-iconset-"))
        self.addCleanup(shutil.rmtree, d, True)
        out = d / "AppIcon.iconset"
        r = subprocess.run(["iconutil", "--convert", "iconset", "--output", str(out), str(APP_ICON)],
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(p.name for p in out.iterdir()), sorted(ICONSET))
        self.assertEqual(info_plist(self).get("CFBundleIconFile"), "AppIcon")
        build = BUILD_SH.read_text(encoding="utf-8")
        self.assertIn("AppIcon.icns", build)
        self.assertTrue(any("AppIcon.icns" in ln and "Contents/Resources" in ln for ln in build.splitlines()),
                        "build.sh 應把 AppIcon.icns 複製進 Contents/Resources/")

    # spec §4.43.8：引導、設定、HUD、確認框、通知的字面不得含名稱清單（沒有清單時 skip）
    def test_no_client_names(self):
        path = os.environ.get("MH_CLIENT_NAMES_FILE")
        if not path:
            self.skipTest("未設定 MH_CLIENT_NAMES_FILE，略過客戶名稱檢查")
        p = Path(path)
        self.assertTrue(p.is_file(), "MH_CLIENT_NAMES_FILE 指向的清單檔不存在")
        names = [s.strip().casefold() for s in p.read_text(encoding="utf-8").splitlines()
                 if s.strip() and not s.strip().startswith("#")]
        self.assertTrue(names)
        hits = []
        for f in (ONBOARDING, PREFERENCES, HUD, DISCARD, NOTIFIER, MEETING_DETECT):
            lits = sr.swift_string_literals(code(self, f))
            if any(n in lit.casefold() for lit in lits for n in names):
                hits.append(rel(f))
        self.assertEqual(hits, [], "字面含名稱清單中的名稱（只列檔名）")

    # spec §4.43.9：字型不打包
    def test_no_bundled_fonts(self):
        all_src = "\n".join(sr.strip_swift_comments(p.read_text(encoding="utf-8")) for p in SOURCES.rglob("*.swift"))
        assert_lacks(self, all_src, ["JetBrains", "Space Grotesk", "Noto Sans", "NSFont(name:"], "Sources/")
        fonts = [rel(p) for p in RESOURCES.rglob("*") if p.suffix.lower() in (".ttf", ".otf", ".ttc")]
        self.assertEqual(fonts, [])
        self.assertNotIn("ATSApplicationFontsPath", info_plist(self))


class MeetingDetectStatic(unittest.TestCase):
    # spec §4.44.2：只讀 DeviceIsRunningSomewhere；不得開麥克風；record.lock 以試鎖判斷
    def test_read_only_detection(self):
        src = code(self, MEETING_DETECT)
        assert_has(self, src, ["kAudioDevicePropertyDeviceIsRunningSomewhere", "acquireRecordLock("],
                   rel(MEETING_DETECT))
        assert_lacks(self, src, ["AVCaptureDevice", "AVAudioEngine", "SCStream"], rel(MEETING_DETECT))

    # spec §4.44.3：F3-A 一般通知的字面與動作；只放 app 名稱、不取視窗標題
    def test_prompt_actions(self):
        src = code(self, MEETING_DETECT)
        assert_has(self, src, ["錄這個會議？", "正在使用麥克風。要開始錄製嗎？", "\"開始錄製\"", "\"這場不用\"", "會議 app",
                               "localizedName", "meetingPromptDecision(", ".meetingDetected"], rel(MEETING_DETECT))
        assert_lacks(self, src, ["kCGWindowName", "SCWindow", "CGWindowListCopyWindowInfo"], rel(MEETING_DETECT))

    # spec §4.44.4：設定的「回饋與通知」分頁可關閉偵測
    def test_toggle_in_settings(self):
        assert_has(self, code(self, PREFERENCES), ["偵測到會議 app 使用麥克風時問我要不要錄", "meetingDetect"],
                   rel(PREFERENCES))


if __name__ == "__main__":
    unittest.main()

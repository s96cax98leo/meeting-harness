"""錄製器 Swift 原始碼的靜態檢查（meeting-speed spec §4.1.5、§4.2.8、§4.2.10、§4.4.1、§4.4.2、§4.8.7、§4.10.1–§4.10.3、
§4.11.1、§4.12.2、§4.12.3、§4.16.2；Story G1、G2、G5、G9）。

一律掃整個目錄（Core/、Capture/、Trigger/）而不是單一檔：recorder-capture／trigger-ui 會以 extension 把
RecordingSession.swift、MenuBar.swift、PreflightRunner.swift 拆成多個檔（plan §2），檢查要在拆檔後仍成立。
Core 函式名與字面以 spec §3.10 為準。
"""
import re
import unittest

from tests.record.test_static_rules import SOURCES, blank_swift_strings, strip_swift_comments, swift_functions

CORE = SOURCES / "Core"
CAPTURE = SOURCES / "Capture"
TRIGGER = SOURCES / "Trigger"
STOP_PATH = {"MenuBar": ("stopRecording", "performStop", "cancelFinalize", "cancelBackgroundFinalize", "hudStop"),
             "HUD": ("stopPressed",), "Onboarding": ("sendStop",)}
STOP_PATH_NAMES = {n for names in STOP_PATH.values() for n in names}


def files(d, prefix=None, exclude=()):
    out = sorted(p for p in d.glob("*.swift") if p.name not in exclude)
    if prefix:
        out = [p for p in out if p.name == f"{prefix}.swift" or p.name.startswith(f"{prefix}+")]
    return out


def code(paths):
    """去掉註解後串起來的原文。"""
    return "\n".join(strip_swift_comments(p.read_text(encoding="utf-8")) for p in paths)


def functions(paths):
    out = {}
    for p in paths:
        for k, v in swift_functions(strip_swift_comments(p.read_text(encoding="utf-8"))).items():
            out.setdefault(k, []).extend(v)
    return out


def bodies_with(paths, needle):
    return [b for bs in functions(paths).values() for b in bs if needle in b]


def literals(src):
    return re.findall(r'"((?:[^"\\\n]|\\.)*)"', src)


def call_text(src, start):
    """src[start:] 以 `名稱(` 開頭；回傳到配對的 `)` 為止的呼叫原文（字串內容不影響配對）。"""
    masked = blank_swift_strings(src)
    i = masked.find("(", start)
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == "(":
            depth += 1
        elif masked[j] == ")":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
    return src[start:]


def body_argument(call):
    """呼叫原文中 `body:` 參數的原文（到下一個頂層 `, 標籤:` 或呼叫結尾）。"""
    m = re.search(r"\bbody\s*:", call)
    if not m:
        return None
    masked = blank_swift_strings(call)
    depth = 0
    for j in range(m.end(), len(masked)):
        ch = masked[j]
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return call[m.end():j]
            depth -= 1
        elif ch == "," and depth == 0 and re.match(r",\s*[A-Za-z_]\w*\s*:", masked[j:]):
            return call[m.end():j]
    return call[m.end():]


def bare_returns_unlogged(body, delegates=()):
    """函式本體中，所在區塊在 return 之前沒有 stopPathLogLine( 的裸 return（不帶值的 return）位置。
    區塊＝由 return 往回找到的第一個未配對 `{` 起算；區塊若呼叫另一個停止路徑函式（delegates）視為已記錄。"""
    masked = blank_swift_strings(body)
    bad = []
    for m in re.finditer(r"\breturn\b(?=\s*(?:\}|\n|$|;))", masked):
        depth, k = 0, m.start() - 1
        while k >= 0:
            if masked[k] == "}":
                depth += 1
            elif masked[k] == "{":
                if depth == 0:
                    break
                depth -= 1
            k -= 1
        block = body[k + 1:m.start()]
        # guard 的條件寫在 else 之前；把 guard 那一行也算進區塊（log 不可能寫在條件裡，所以只是讓訊息好讀）
        if "stopPathLogLine(" in block or any(re.search(r"\b" + d + r"\s*\(", block) for d in delegates):
            continue
        line = body[:m.start()].count("\n") + 1
        snippet = body[max(0, body.rfind("\n", 0, max(k, 0)) + 1):m.end()].strip().replace("\n", " ")
        bad.append(f"本體第 {line} 行：{snippet[-120:]}")
    return bad


class ShortMessages(unittest.TestCase):
    """原始碼很長：失敗訊息只印要找的東西，不印整份原始碼。"""

    def assertIn(self, member, container, msg=None):
        self.assertTrue(member in container, msg or f"找不到 {member!r}")

    def assertNotIn(self, member, container, msg=None):
        self.assertFalse(member in container, msg or f"不應出現 {member!r}")

    def assertRegex(self, text, regex, msg=None):
        self.assertTrue(re.search(regex, text), msg or f"找不到符合 {regex!r} 的寫法")

    def assertNotRegex(self, text, regex, msg=None):
        self.assertFalse(re.search(regex, text), msg or f"不應出現符合 {regex!r} 的寫法")


class CoreStatic(unittest.TestCase):
    # spec §4.1.5：Sources/Core/ 不得 import AppKit
    def test_core_no_appkit(self):
        paths = files(CORE)
        self.assertTrue(paths, "Sources/Core/ 沒有 .swift")
        bad = [p.name for p in paths
               if re.search(r"(?m)^\s*(?:@\w+\s+)*import\s+AppKit\b", strip_swift_comments(p.read_text(encoding="utf-8")))]
        self.assertEqual(bad, [], "Core 不得 import AppKit")


class CaptureStatic(ShortMessages):
    def setUp(self):
        self.capture = files(CAPTURE, exclude=("Probe.swift",))
        self.session = files(CAPTURE, "RecordingSession")
        self.preflight = [p for p in files(CAPTURE) if p.name.startswith("Preflight")]
        self.assertTrue(self.session and self.preflight, "Capture/ 應有 RecordingSession*.swift 與 Preflight*.swift")

    # spec §4.2.8：FinalizeRunner 逐行轉印時認到 isAudioReadyLine 就把狀態檔 audioReady 設 true
    def test_audio_ready_sets_status(self):
        src = code(self.capture)
        self.assertIn("isAudioReadyLine(", src, "Capture 應以 Core 的 isAudioReadyLine( 判斷「音訊就緒：」行")
        self.assertRegex(src, r"\baudioReady\s*=\s*true\b", "認到音訊就緒行時應把狀態檔 audioReady 設為 true")
        self.assertNotIn('"音訊就緒：', src, "判斷應交給 Core 的 isAudioReadyLine，Capture 不另寫字面比對")

    # spec §4.4.1：開錄當下的偶數像素尺寸寫進 record.meta.json.canvasLock
    def test_canvas_lock_written(self):
        src = code(self.capture)
        self.assertRegex(src, r"\bCanvasLock\s*\(\s*width\s*:", "開錄時應建立 CanvasLock(width:height:)")
        self.assertRegex(src, r"\.canvasLock\s*=", "應寫入 RecordMeta.canvasLock")

    # spec §4.4.1：錄製中視窗尺寸改變不得以 updateConfiguration 改尺寸（換麥克風裝置的 updateConfiguration 不在此限）
    def test_no_resize_update_configuration(self):
        bad = [next((x.strip() for x in b.splitlines() if "updateConfiguration(" in x), "")
               for b in bodies_with(self.capture, "updateConfiguration(")
               if re.search(r"\bcfg\.(?:width|height)\s*=", b) or "nextSegmentSize(" in b]
        self.assertEqual(bad, [], "改畫布尺寸（cfg.width／cfg.height）的函式不得呼叫 updateConfiguration")
        for b in bodies_with(self.session, "nextSegmentSize("):
            self.assertNotIn("updateConfiguration(", b)

    # spec §4.4.1：尺寸改變只寫一行 log「視窗尺寸改變：A → B（畫布維持開錄時的 W×H，內容等比縮放）」
    def test_next_segment_size_logged(self):
        bs = bodies_with(self.session, "nextSegmentSize(")
        self.assertTrue(bs, "RecordingSession 應仍呼叫 nextSegmentSize(（既有 test_static_rules 的檢查）")
        lits = [x for b in bs for x in literals(b)]
        hit = [x for x in lits if x.startswith("● 視窗尺寸改變：") or x.startswith("視窗尺寸改變：")]
        self.assertTrue(hit, f"呼叫 nextSegmentSize( 的函式應寫「視窗尺寸改變：A → B（畫布維持開錄時的 W×H，內容等比縮放）」：{lits}")
        self.assertTrue(any("→" in x and "（畫布維持開錄時的 " in x and "內容等比縮放）" in x for x in hit),
                        f"log 字面應含「→」「（畫布維持開錄時的 」「內容等比縮放）」：{hit}")
        self.assertFalse(any("本段起生效" in x for x in lits), "舊的「本段起生效」log 表示仍會改畫布")

    # spec §4.4.2：scalesToFit 與 preservesAspectRatio 都是 true；§4.4.13 決定前 minimumFrameInterval 維持 1/60
    def test_preserves_aspect_ratio(self):
        bs = [b for b in bodies_with(self.session, ".minimumFrameInterval") if re.search(r"\.minimumFrameInterval\s*=", b)]
        self.assertTrue(bs, "RecordingSession 應有設定 SCStreamConfiguration（minimumFrameInterval）的函式")
        b = "\n".join(bs)
        self.assertRegex(b, r"\.scalesToFit\s*=\s*true\b")
        self.assertRegex(b, r"\.preservesAspectRatio\s*=\s*true\b", "應設 preservesAspectRatio = true（內容等比縮放）")
        self.assertRegex(b, r"\.minimumFrameInterval\s*=\s*CMTime\(\s*value\s*:\s*1\s*,\s*timescale\s*:\s*60\s*\)",
                         "§4.4.13 使用者決定前維持 1/60（決定後由 red-py 改這條斷言）")

    # spec §4.10.1：probe stream 開不起來時走 audioProbeVerdict → .deviceFailed，第 6、12 項記「略過（音訊裝置無法啟動）」
    def test_preflight_device_failed(self):
        src = code(self.preflight)
        for needle in ("audioProbeVerdict(", ".deviceFailed", "audioDeviceFailedMessage("):
            self.assertIn(needle, src, f"Capture/Preflight*.swift 應有 {needle}")
        lits = literals(src) + literals(code(files(CORE)))
        self.assertTrue(any("略過（音訊裝置無法啟動）" in x for x in lits), "第 6、12 項應記「略過（音訊裝置無法啟動）」")

    # spec §4.10.2：startCapture 失敗時 record.log 記錯誤的 domain、code 與輸入／輸出裝置名稱
    def test_start_capture_error_logged(self):
        bs = [b for b in bodies_with(self.session, "startCapture()") if "catch" in b]
        self.assertTrue(bs, "RecordingSession 應有呼叫 startCapture() 並 catch 的函式")
        b = "\n".join(bs)
        self.assertRegex(b, r"\.domain\b", "startCapture 失敗的 log 應含錯誤的 domain")
        self.assertRegex(b, r"\.code\b", "startCapture 失敗的 log 應含錯誤的 code")
        lits = literals(b)
        self.assertTrue("audioDeviceFailedMessage(" in b
                        or (any("輸入" in x for x in lits) and any("輸出" in x for x in lits)),
                        "startCapture 失敗的 log 應含輸入／輸出裝置名稱")

    # spec §4.10.3：PreflightRunner 的兩處提早 return 前寫 stopPathLogLine(…)
    # （spec 沒指名是哪兩處；這裡只驗 Preflight*.swift 至少兩處呼叫，見交件的 open question）
    def test_preflight_returns_logged(self):
        n = len(re.findall(r"\bstopPathLogLine\s*\(", code(self.preflight)))
        self.assertGreaterEqual(n, 2, f"PreflightRunner 的兩處提早 return 前都應寫 stopPathLogLine(…)：目前 {n} 處")

    # spec §4.11.1：第一段收尾後以 nice -n 10 起 _asr_worker.py run <場次> 一次（.utility，不經 zsh -l）
    def test_worker_started_after_first_segment(self):
        src = code(self.capture)
        self.assertIn("asrWorkerShouldStart(", src, "應以 Core 的 asrWorkerShouldStart( 決定是否起 worker")
        bs = bodies_with(self.capture, "_asr_worker.py")
        self.assertTrue(bs, "Capture 應有起 bin/lib/_asr_worker.py 的函式")
        b = "\n".join(bs)
        self.assertIn('"/usr/bin/nice"', b)
        self.assertRegex(b, r'"-n"\s*,\s*"10"', "應為 nice -n 10")
        self.assertIn('"run"', b, "子指令應為 run <場次>")
        self.assertRegex(b, r"qualityOfService\s*=\s*\.utility\b")
        self.assertNotIn("zsh", b, "worker 不經 zsh -l")
        self.assertIn("bin/lib/_asr_worker.py", b)

    # spec §4.12.3：錄製實例的完成通知內文為 completionNotificationBody(…)，不含 session.path／outcome.message
    def test_completion_body_no_path(self):
        bs = bodies_with(self.capture, '"會議錄製完成"')
        self.assertTrue(bs, "Capture 應仍有「會議錄製完成」通知（既有 test_r3_skip_finalize）")
        for b in bs:
            starts = [m.start() for m in re.finditer(r"\bNotifier\.post\s*\(", b)]
            self.assertTrue(starts, "「會議錄製完成」與 Notifier.post( 應在同一函式")
            for st in starts:
                arg = body_argument(call_text(b, st)) or ""
                self.assertIn("completionNotificationBody(", arg, f"通知內文應為 completionNotificationBody(…)：{arg.strip()}")
                for bad in ("session.path", "outcome.message", ".path"):
                    self.assertNotIn(bad, arg, f"通知內文不得含 {bad}：{arg.strip()}")


class TriggerStatic(ShortMessages):
    def setUp(self):
        self.trigger = files(TRIGGER)
        self.assertTrue(self.trigger, "Sources/Trigger/ 沒有 .swift")

    def autoprep_class(self):
        for p in self.trigger:
            src = strip_swift_comments(p.read_text(encoding="utf-8"))
            m = re.search(r"\bclass\s+AutoPrepRunner\b", src)
            if m:
                open_i = src.find("{", m.end())
                masked = blank_swift_strings(src)
                depth = 0
                for j in range(open_i, len(masked)):
                    if masked[j] == "{":
                        depth += 1
                    elif masked[j] == "}":
                        depth -= 1
                        if depth == 0:
                            return src[m.start():j + 1]
        self.fail("Trigger/ 找不到 class AutoPrepRunner")

    # spec §4.2.10：AutoPrepRunner 的指令照舊 meeting.sh prep <場次>，環境只多 MH_PREP_RUN_ID，不設 MH_PREP_EARLY
    def test_autoprep_run_id_env(self):
        cls = self.autoprep_class()
        self.assertRegex(cls, r'\[\s*"MH_PREP_RUN_ID"\s*\]\s*=', "應在子程序環境設 MH_PREP_RUN_ID=<uuid>")
        self.assertRegex(cls, r'"prep"\s*,', "子程序指令應仍為 meeting.sh prep <場次>")
        self.assertNotIn("MH_PREP_EARLY", code(sorted(SOURCES.rglob("*.swift"))), "不得設 MH_PREP_EARLY")

    # spec §4.8.7：prep 結束時讀 .pipeline-state.json 交給 prepOutcome，再用 prepNotification 決定通知
    def test_prep_outcome_read(self):
        cls = self.autoprep_class()
        self.assertRegex(cls, r"\bprepOutcome\s*\(\s*pipelineState\s*:")
        self.assertRegex(cls, r"\bprepNotification\s*\(\s*outcome\s*:")
        self.assertTrue(any(".pipeline-state.json" in x for x in literals(cls)), "應讀該場的 .pipeline-state.json")
        self.assertFalse(any(x == "前處理完成" for x in literals(cls)), "標題應交給 prepNotification，不再寫死「前處理完成」")

    # spec §4.10.3：停止路徑每個提早 return 前都寫一行 stopPathLogLine(…)；stopTargetDecision( 呼叫形狀不變
    def test_stop_paths_logged(self):
        for prefix, names in STOP_PATH.items():
            fns = functions(files(TRIGGER, prefix))
            for name in names:
                with self.subTest(file=prefix, func=name):
                    self.assertIn(name, fns, f"{prefix}*.swift 應有 func {name}(")
                    for b in fns[name]:
                        bad = bare_returns_unlogged(b, delegates=STOP_PATH_NAMES - {name})
                        self.assertEqual(bad, [], f"{name} 的提早 return 前應寫 stopPathLogLine(…)")
        src = code(self.trigger)
        n = len(re.findall(r"\bstopTargetDecision\s*\(\s*lockHeld\s*:", src))
        self.assertGreaterEqual(n, 3, "stopTargetDecision(lockHeld:…) 的呼叫形狀不變（MenuBar 兩處、HUD、Onboarding）")

    # spec §4.12.2：前處理三則通知不得含場次名或路徑，內文以 sessionCodeLabel 開頭
    def test_prep_notifications_no_name(self):
        cls = self.autoprep_class()
        self.assertNotIn("lastPathComponent", cls, "Completion.swift 不得再用 lastPathComponent 組通知內文")
        self.assertIn("sessionCodeLabel(", cls, "通知內文應以 sessionCodeLabel(…) 開頭")
        for m in re.finditer(r"\bpost\s*\(\s*title\s*:", cls):
            arg = body_argument(call_text(cls, m.start())) or ""
            with self.subTest(body=arg.strip()[:80]):
                for bad in (".path", r"\(session", r"\(name"):
                    self.assertNotIn(bad, arg, f"通知內文不得含場次名或路徑（{bad}）")

    # spec §4.12.3：menu bar 完成通知的內文為 completionNotificationBody(…)；userInfo["session"] 保留
    def test_menubar_completion_body_no_session(self):
        bs = bodies_with(files(TRIGGER, "MenuBar"), '"會議錄製完成"')
        self.assertTrue(bs, "MenuBar 應仍有「會議錄製完成」通知")
        for b in bs:
            self.assertRegex(b, r"\.body\s*=\s*completionNotificationBody\s*\(", "內文應為 completionNotificationBody(…)")
            self.assertNotRegex(b, r"\.body\s*=\s*st\.session\b", "內文不得是 st.session")
            self.assertNotIn("outcome.message", b)
            self.assertRegex(b, r'userInfo\s*=\s*\[\s*"session"\s*:', "「在 Finder 顯示」用的 userInfo[\"session\"] 保留")

    # spec §4.16.2：啟動時讀 record.status.json、kill(status.pid, 0)，交給 abnormalStopSession（不讀 record.pid）
    def test_abnormal_stop_checked_on_launch(self):
        src = code(self.trigger)
        self.assertRegex(src, r"\babnormalStopSession\s*\(\s*status\s*:", "Trigger 應呼叫 abnormalStopSession(status:…)")
        self.assertRegex(src, r"\bkill\s*\(\s*[\w.?!]*pid\s*,\s*0\s*\)", "應以 kill(status.pid, 0) 判斷程序是否還在")
        bs = bodies_with(self.trigger, "abnormalStopSession(")
        self.assertTrue(bs)
        for b in bs:
            for bad in ("record.pid", "pidURL", "readPid("):
                self.assertNotIn(bad, b, f"呼叫 abnormalStopSession( 的函式不得讀 record.pid（{bad}；E2）")
        self.assertRegex(src, r'"record"\s*,\s*"finish"', "「收尾」動作應跑 meeting.sh record finish <場次>")
        self.assertTrue(any(x == "收尾" for x in literals(src)), "通知應提供「收尾」動作")

    # spec §4.16.2：異常中止通知的文字不得含場次名或路徑（label 用 sessionCodeLabel）
    def test_abnormal_stop_notification_no_name(self):
        bs = bodies_with(self.trigger, "abnormalStopNotification(")
        self.assertTrue(bs, "Trigger 應呼叫 abnormalStopNotification(label:…)")
        for b in bs:
            self.assertRegex(b, r"\babnormalStopNotification\s*\(\s*label\s*:")
            self.assertIn("sessionCodeLabel(", b, "label 應為 sessionCodeLabel(…)")
            self.assertNotIn("lastPathComponent", b)
        self.assertFalse(any("上次錄製異常中止" in x for x in literals(code(self.trigger))),
                         "通知字面應來自 Core 的 abnormalStopNotification，Trigger 不另寫")


if __name__ == "__main__":
    unittest.main()

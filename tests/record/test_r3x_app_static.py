"""R3x app 端只能靜態檢查的形狀（spec R3x §3.23、§3.24、§3.26、§4.48.4–§4.48.6、§4.49.3–§4.49.4、§4.50.1–§4.50.2、
§4.50.5、§4.50.9、§4.54.4–§4.54.7）。

類別名逐字照 spec 測試欄：BackgroundCaptureStatic（Capture/RecordingSession.swift、Commands.swift、FinalizeRunner.swift）、
StatusWriterStatic（Capture/PreflightRunner.swift）、MenuBarBackgroundStatic（Trigger/MenuBar.swift）。
只驗「Capture／Trigger 有呼叫 Core 純函式」的形狀；分支判斷本身由 swift:R3xBackgroundTests.swift 驗（修正輪 I9）。
只讀 tools/MeetingRecorder/Sources/（去掉註解後比對）；檔案不存在一律判 FAIL，不得跳過。
"""
import re
import unittest

from tests.record import test_static_rules as sr
from tests.record.test_r3_app_static import (CAPTURE, COMMANDS, FINALIZE_RUNNER, MENUBAR, PREFLIGHT_RUNNER,
                                             RECORDING_SESSION, assert_has, assert_lacks, code, rel)


def functions(src):
    return sr.swift_functions(src)


def one_body(tc, src, name, path, containing=None):
    """名為 name 的函式本體（有多個同名時取含 containing 的第一個）；找不到判 FAIL。"""
    bodies = functions(src).get(name, [])
    if containing is not None:
        bodies = [b for b in bodies if containing in b]
    tc.assertTrue(bodies, f"{rel(path)} 找不到 func {name}(" + (f"（含 {containing}）" if containing else ""))
    return bodies[0]


def block_after(src, start):
    """src[start:] 之後第一個 { 起到配對 } 的區塊（大括號以 blank_swift_strings 後的副本計）；找不到回 None。"""
    masked = sr.blank_swift_strings(src)
    i = masked.find("{", start)
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == "{":
            depth += 1
        elif masked[j] == "}":
            depth -= 1
            if depth == 0:
                return i, j + 1
    return None


def ordered(text, needles):
    """needles 各取第一次出現的位置，應嚴格遞增；回 (是否成立, 位置清單)。"""
    pos = [text.find(n) for n in needles]
    ok = all(p >= 0 for p in pos) and all(a < b for a, b in zip(pos, pos[1:]))
    return ok, dict(zip(needles, pos))


def reachable(src, root, depth=2):
    """root 函式本體＋它呼叫的同檔函式本體（最多 depth 層）。"""
    funcs = functions(src)
    seen, frontier, texts = {root}, [root], []
    for _ in range(depth + 1):
        nxt = []
        for name in frontier:
            for b in funcs.get(name, []):
                texts.append(b)
                for callee in re.findall(r"\b([A-Za-z_]\w*)\s*\(", b):
                    if callee in funcs and callee not in seen:
                        seen.add(callee)
                        nxt.append(callee)
        frontier = nxt
    return "\n".join(texts)


class BackgroundCaptureStatic(unittest.TestCase):
    # spec §4.48.4、§4.48.8、§3.23 第 1–10 步：beginFinalize 的本體依序出現各步
    def test_release_order(self):
        src = code(self, RECORDING_SESSION)
        body = one_body(self, src, "beginFinalize", RECORDING_SESSION)
        steps = ["if ctx.skipFinalize", "backgroundRunIdAllowed(", "tryFlock(at: backgroundLockURL(", "enterBackground(",
                 "shouldRemoveRecordPid(", "prunableBackgroundJob(", "releaseRecordLock()", "FinalizeRunner(",
                 "waitFinalizeQueue(", "runFinalize("]
        missing = [s for s in steps if s not in body]
        self.assertEqual(missing, [], f"{rel(RECORDING_SESSION)} 的 beginFinalize 缺少：{missing}")
        ok, pos = ordered(body, steps)
        self.assertTrue(ok, f"beginFinalize 的各步應依 §3.23 的順序出現（各取第一次）：{pos}")
        assert_has(self, body, ["已放開開錄鎖", "backgroundEntryDecision("], "beginFinalize")

    # spec §4.48.5、§3.22：releaseRecordLock 的定義；Capture/ 只在 beginFinalize 呼叫（--skip-finalize、finishDiscard、fail 不呼叫）
    def test_release_function(self):
        cmd = code(self, COMMANDS)
        self.assertTrue(re.search(r"\bfunc releaseRecordLock\(\)", cmd), f"{rel(COMMANDS)} 應有 func releaseRecordLock()")
        body = one_body(self, cmd, "releaseRecordLock", COMMANDS)
        assert_has(self, body, ["close(", "recordLockFD = nil"], "releaseRecordLock")
        calls = []
        for p in sorted(CAPTURE.glob("*.swift")):
            s = code(self, p)
            for mm in re.finditer(r"releaseRecordLock\(\)", s):
                if not s[max(0, mm.start() - 5):mm.start()].endswith("func "):
                    calls.append((p, s, mm.start()))
        self.assertTrue(calls, "Capture/ 應呼叫 releaseRecordLock()")
        rs = code(self, RECORDING_SESSION)
        begin = one_body(self, rs, "beginFinalize", RECORDING_SESSION)
        b0 = rs.find(begin)
        for p, s, at in calls:
            self.assertEqual(p, RECORDING_SESSION, f"只有 RecordingSession.swift 可以呼叫 releaseRecordLock()：{rel(p)}")
            self.assertTrue(b0 <= at < b0 + len(begin), "releaseRecordLock() 只能在 beginFinalize 內呼叫")
        for name in ("finishDiscard", "fail"):
            for b in functions(rs).get(name, []):
                self.assertFalse("releaseRecordLock()" in b, f"{name} 不得呼叫 releaseRecordLock()")
        skip = block_after(begin, begin.find("if ctx.skipFinalize"))
        self.assertIsNotNone(skip, "beginFinalize 應有 if ctx.skipFinalize { … } 分支")
        self.assertFalse("releaseRecordLock()" in begin[skip[0]:skip[1]], "--skip-finalize 分支不得呼叫 releaseRecordLock()")

    # spec §4.48.6、§3.23 第 10 步（修正輪 I5）：runFinalize 傳 MH_RECORD_HOME；背景路徑才加 MH_FINALIZE_WAIT_LOCK
    def test_finalize_env_home(self):
        src = code(self, RECORDING_SESSION)
        body = one_body(self, src, "runFinalize", RECORDING_SESSION)
        assert_has(self, body, ["MH_RECORD_HOME", "MH_FINALIZE_WAIT_LOCK", "backgroundLockFD"], "runFinalize")
        self.assertTrue(re.search(r"\bvar backgroundLockFD\s*:\s*Int32\?", code(self, PREFLIGHT_RUNNER)),
                         f"{rel(PREFLIGHT_RUNNER)} 應有全域 var backgroundLockFD: Int32?（§3.26）")

    # spec §4.49.4、§3.23 第 11 步：complete 刪 ctx.pidURL 的每一處都在 shouldRemoveRecordPid( 判斷之後
    def test_complete_keeps_next_pid(self):
        src = code(self, RECORDING_SESSION)
        body = one_body(self, src, "complete", RECORDING_SESSION, containing="finalizeCode")
        self.assertTrue("shouldRemoveRecordPid(" in body, "complete 應以 shouldRemoveRecordPid( 判斷要不要刪 record.pid")
        first = body.find("shouldRemoveRecordPid(")
        removes = [mm.start() for mm in re.finditer(r"removeItem\(at: ctx\.pidURL\)", body)]
        early = [at for at in removes if at < first]
        self.assertEqual(early, [], "complete 中刪 ctx.pidURL 的呼叫都應在 shouldRemoveRecordPid( 判斷之內")

    # spec §4.50.1、§3.22 排隊鎖：waitFinalizeQueue 的本體與簽名；不得用阻塞的 flock
    def test_queue_wait(self):
        src = code(self, RECORDING_SESSION)
        self.assertTrue(re.search(r"\bfunc waitFinalizeQueue\(_ runner: FinalizeRunner\) -> Bool", src),
                         "應有 private func waitFinalizeQueue(_ runner: FinalizeRunner) -> Bool（§3.26）")
        body = one_body(self, src, "waitFinalizeQueue", RECORDING_SESSION)
        assert_has(self, body, ["queueWaitStep(", "finalizeQueueLockURL(", "tryFlock(", "isCancelRequested",
                                "finalizeQueuePollSeconds", "排隊中"], "waitFinalizeQueue")
        assert_lacks(self, body, ["LOCK_EX)"], "waitFinalizeQueue（不得用阻塞的 flock 等待）")

    # spec §4.50.2、§3.23 第 9 步：isCancelRequested；排隊中被取消 → complete(… .cancelled)，不經 runFinalize(
    def test_cancel_while_queued(self):
        self.assertTrue(re.search(r"\bvar isCancelRequested\s*:\s*Bool", code(self, FINALIZE_RUNNER)),
                         f"{rel(FINALIZE_RUNNER)} 應有 isCancelRequested: Bool {{ get }}")
        src = code(self, RECORDING_SESSION)
        body = one_body(self, src, "beginFinalize", RECORDING_SESSION)
        w = body.find("waitFinalizeQueue(")
        self.assertGreaterEqual(w, 0, "beginFinalize 應呼叫 waitFinalizeQueue(")
        r = body.find("runFinalize(", w)
        self.assertGreater(r, w, "beginFinalize 應在 waitFinalizeQueue( 之後才呼叫 runFinalize(")
        between = body[w:r]
        assert_has(self, between, ["complete(", ".cancelled"],
                   "beginFinalize 在 waitFinalizeQueue( 回 false 的路徑（runFinalize( 之前）")


class StatusWriterStatic(unittest.TestCase):
    # spec §4.49.3、§3.24：StatusWriter.enterBackground(home:)；update（或它呼叫的私有函式）做條件式寫入
    def test_conditional_shared_write(self):
        src = code(self, PREFLIGHT_RUNNER)
        at = src.find("class StatusWriter")
        self.assertGreaterEqual(at, 0, f"{rel(PREFLIGHT_RUNNER)} 找不到 class StatusWriter")
        blk = block_after(src, at)
        self.assertIsNotNone(blk)
        cls = src[blk[0]:blk[1]]
        self.assertTrue(re.search(r"\bfunc enterBackground\(home: URL\)", cls), "StatusWriter 應有 func enterBackground(home: URL)")
        funcs = functions(cls)
        self.assertTrue("update" in funcs, "StatusWriter 應有 func update(")
        text = "\n".join(funcs["update"])
        for b in funcs["update"]:
            for callee in re.findall(r"\b([A-Za-z_]\w*)\s*\(", b):
                if callee in funcs and callee != "update":
                    text += "\n" + "\n".join(funcs[callee])
        assert_has(self, text, ["backgroundStatusURL(", "sharedStatusWritable(", "acquireRecordLock(", "recordLockFD",
                                "close("], "StatusWriter.update（含它呼叫的私有函式）")


class MenuBarBackgroundStatic(unittest.TestCase):
    # spec §4.50.5、§6 第 149 條：.backgroundFinalizing 階段的取消收尾改走背景路徑（backgroundCancelDecision）
    def test_cancel_uses_background_decision(self):
        src = code(self, MENUBAR)
        assert_has(self, src, ["backgroundCancelDecision(", "backgroundCancelCandidate(", "backgroundCancelPrompt("],
                   rel(MENUBAR))
        cancel = one_body(self, src, "cancelFinalize", MENUBAR)
        self.assertTrue("backgroundFinalizing" in cancel, "cancelFinalize 應依 .backgroundFinalizing 階段改走背景路徑")
        bodies = [b for bs in functions(src).values() for b in bs if "backgroundCancelDecision(" in b and "kill(" in b]
        self.assertTrue(bodies, "送 SIGTERM 的背景取消函式應經 backgroundCancelDecision(")
        for b in bodies:
            self.assertTrue(".signal(pid" in b, "只有 backgroundCancelDecision 回 .signal(pid:) 才送 SIGTERM")
        rl = "\n".join(functions(src).get("recordLockHeld", []))
        self.assertTrue("retrySeconds: 0" in rl, "recordLockHeld 以 acquireRecordLock(home:retrySeconds: 0) 試鎖")

    # spec §4.50.9（修正輪 I8）：同一個函式本體依序含候選、確認文字、runModal、決策、kill；確認後 kill 前重讀一次 job
    def test_cancel_confirms_target(self):
        src = code(self, MENUBAR)
        seq = ["backgroundCancelCandidate(", "backgroundCancelPrompt(", "runModal(", "backgroundCancelDecision(", "kill("]
        found = []
        for b in (b for bs in functions(src).values() for b in bs):
            pos, at = [], 0
            for n in seq:
                at = b.find(n, at)
                if at < 0:
                    break
                pos.append(at)
            if len(pos) == len(seq):
                reread = b.find("loadBackgroundJobs(", pos[2])
                found.append(0 <= reread < pos[4])
        self.assertTrue(found, f"{rel(MENUBAR)} 應有一個函式本體依序含 {seq}")
        self.assertTrue(any(found), "runModal( 之後、kill( 之前應再呼叫一次 loadBackgroundJobs(（確認後重讀）")

    # spec §4.54.4：refresh 讀每場狀態檔並在 menuBarModel( 之後疊上 applyBackgroundFinalize(；開始的可用性看 canStart
    def test_refresh_overlays_jobs(self):
        src = code(self, MENUBAR)
        body = one_body(self, src, "refresh", MENUBAR)
        assert_has(self, body, ["loadBackgroundJobs(", "applyBackgroundFinalize(", "menuBarModel("], "refresh")
        self.assertGreater(body.find("applyBackgroundFinalize("), body.find("menuBarModel("),
                           "applyBackgroundFinalize( 應晚於 menuBarModel(")
        for item in ("startItem.isEnabled", "windowsItem.isEnabled"):
            line = next((ln for ln in body.splitlines() if item in ln), "")
            self.assertTrue("canStart" in line, f"{item} 應照舊看 canStart（套用後的 model）")

    # spec §4.54.5、§6 第 150 條（修正輪 B1）：refresh 以 autoPrepCandidates 與 autoPrepEnqueued 去重；每場狀態檔也走 trackCompletion
    def test_auto_prep_reads_jobs(self):
        src = code(self, MENUBAR)
        self.assertTrue(re.search(r"private var autoPrepEnqueued\s*=\s*Set<String>\(\)", src),
                         "應有 private var autoPrepEnqueued = Set<String>()（§3.26）")
        text = reachable(src, "refresh")
        assert_has(self, text, ["autoPrepCandidates(", "autoPrepEnqueued"], "refresh（含它呼叫的私有函式）")
        self.assertTrue(re.search(r"trackCompletion\((?!raw\))", text),
                         "trackCompletion 的完成通知對每場狀態檔也應呼叫（不只共用狀態檔 raw）")
        self.assertTrue("completionPosted" in src, "同一 runId 只發一次完成通知（沿用 completionPosted）")

    # spec §4.54.6、§6 第 151 條：會議偵測的 recordingInProgress 不把 .backgroundFinalizing 算成錄製中
    def test_meeting_detect_not_blocked(self):
        src = code(self, MENUBAR)
        at = src.find("MeetingDetector(")
        self.assertGreaterEqual(at, 0, f"{rel(MENUBAR)} 應建立 MeetingDetector(")
        rp = src.find("recordingInProgress:", at)
        self.assertGreaterEqual(rp, 0, "MeetingDetector( 應帶 recordingInProgress: 閉包")
        blk = block_after(src, rp)
        self.assertIsNotNone(blk)
        self.assertFalse("backgroundFinalizing" in src[blk[0]:blk[1]], "recordingInProgress 閉包不得含 backgroundFinalizing")

    # spec §4.54.7（修正輪 I7）：cancelFinalizeItem.isEnabled 的指定式含 backgroundCancelCandidate( 或 backgroundFinalizing
    def test_cancel_item_enabled(self):
        src = code(self, MENUBAR)
        lines = src.splitlines()
        idx = [i for i, ln in enumerate(lines) if re.search(r"cancelFinalizeItem\.isEnabled\s*=", ln)]
        self.assertTrue(idx, f"{rel(MENUBAR)} 應指定 cancelFinalizeItem.isEnabled")
        for i in idx:
            expr = lines[i]
            j = i + 1
            while j < len(lines) and re.match(r"\s*(\|\||&&|\?|:|\.)", lines[j]):
                expr += "\n" + lines[j]
                j += 1
            self.assertTrue("backgroundCancelCandidate(" in expr or "backgroundFinalizing" in expr,
                            f"cancelFinalizeItem.isEnabled 的指定式應含 backgroundCancelCandidate( 或 backgroundFinalizing：{expr.strip()}")


if __name__ == "__main__":
    unittest.main()

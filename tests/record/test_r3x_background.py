"""R3x 背景收尾：record.sh 的 stop／status／finish 與開錄前告警（spec R3x-§2.2、§3.21–§3.24、§4.48.7、§4.49.5–§4.49.6、
§4.50.3、§4.51、§4.52、§4.53.1、§4.56.2；§6 第 146、147 條）。

錄製實例以替身代替：背景收尾協定（§3.23、§3.24）用 fakes/fake_bg_finalizer.sh（§3.27，協定的可執行參考），
一般錄製用既有的 fakes/fake_recorder.sh，開錄用 fakes/fake_open.sh（MH_RECORD_OPEN）。所有檔案都在 TMPDIR 的 sandbox
（MH_RECORD_HOME），不碰 ~/.meeting-harness，不啟動任何 app。
標「（協定參考）」的測試只驗替身與 record.sh 讀得懂檔案協定，不算錄製實例的紅轉綠（spec R3x 開頭〈紅轉綠怎麼算〉）。
範例場次名一律用「[Stand-up] 範例專案」。
"""
import fcntl
import json
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
import unittest

from tests.record import _media as m
from tests.record._helpers import FAILING_FFMPEG, FAKES, RECORD_SH, Sandbox, dead_pid, flag_value
from tests.record.test_r3_lock import cmd_stop_limit_python, hold_lock, run_stop, start_fake, try_lock_nb, write_status

FAKE_BG = FAKES / "fake_bg_finalizer.sh"
EXAMPLE = "[Stand-up] 範例專案"
DAY = "20261017"
WAIT_BG_HEADER = "沒有錄製在跑；等背景收尾完成（不送停止訊號）…"
BG_DONE = "✓ 背景收尾完成。"
DISK_WARNING = "  ⚠ 上一場收尾還在跑（{n} 場），會再用掉一些磁碟空間；開錄前檢查的剩餘空間沒有扣掉這部分"


def now_iso(offset=0.0):
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + offset))


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_pid_file(sb):
    try:
        return (sb.home / "record.pid").read_text().strip()
    except OSError:
        return ""


def until(pred, timeout, what):
    """每 50 ms 看一次 pred()；timeout 秒內沒成立就判 FAIL（不是固定等待）。"""
    deadline = time.monotonic() + timeout
    while True:
        v = pred()
        if v:
            return v
        if time.monotonic() > deadline:
            raise AssertionError(f"{timeout} 秒內沒有等到：{what}")
        time.sleep(0.05)


def session_dir(sb, tag):
    d = sb.root / DAY / f"{EXAMPLE} {tag}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bg_status_path(sb, run):
    return sb.home / "finalizing" / f"{run}.status.json"


def bg_lock_path(sb, run):
    return sb.home / "finalizing" / f"{run}.lock"


def lock_held_no_create(path):
    """旁觀者規則（§3.22）：O_RDWR 不帶 O_CREAT、LOCK_NB 試一次；檔不存在＝沒人持有。"""
    try:
        fd = os.open(str(path), os.O_RDWR)
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def write_bg_status(sb, run, phase, *, session, code=0, message="", queued=None, pid=None, started=None,
                    updated=None, lock_file=False):
    """直接寫一份每場狀態檔（§3.21 的形狀：RecordStatus＋background true）；lock_file=True 時另建一個沒人持有的鎖檔。"""
    st = {"schemaVersion": 1, "runId": run, "pid": pid if pid is not None else dead_pid(), "phase": phase, "code": code,
          "message": message, "session": str(session), "startedAt": started or now_iso(-60),
          "updatedAt": updated or now_iso(), "segments": 2, "preflight": [], "warnings": [], "background": True}
    if queued is not None:
        st["queued"] = queued
    d = sb.home / "finalizing"
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".test.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False)
    os.replace(tmp, bg_status_path(sb, run))
    if lock_file:
        bg_lock_path(sb, run).touch()
    return st


def write_shared(sb, st):
    fd, tmp = tempfile.mkstemp(dir=str(sb.home), prefix=".record.status.test.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False)
    os.replace(tmp, sb.home / "record.status.json")


def parse_events(sb):
    """<home>/fake_bg.events → {runId: [(kind, epoch), …]}。"""
    out = {}
    p = sb.home / "fake_bg.events"
    if not p.exists():
        return out
    for ln in p.read_text(encoding="utf-8").splitlines():
        parts = ln.split()
        if len(parts) == 3:
            out.setdefault(parts[1], []).append((parts[0], float(parts[2])))
    return out


def event_time(events, run, kind):
    ts = [t for k, t in events.get(run, []) if k == kind]
    return ts[0] if ts else None


def bash_functions(src):
    """record.sh 的頂層函式：{名稱: 本體}（`name() {` 起到行首的 `}`）。"""
    return {mm.group(1): mm.group(2)
            for mm in re.finditer(r"(?ms)^([A-Za-z_]\w*)\(\)\s*\{[^\n]*\n(.*?)^\}\n", src)}


def lines_in_loops(body):
    """bash 本體中位於 while／until／for 迴圈內的行（略過 heredoc 內容）。"""
    out, depth, term = [], 0, None
    for ln in body.splitlines():
        s = ln.strip()
        if term is not None:
            if s == term:
                term = None
            continue
        if re.match(r"^(while|until|for)\b", s):
            depth += 1
        if depth > 0:
            out.append(s)
        if re.match(r"^done\b", s) or re.search(r";\s*done\b", s):
            depth = max(0, depth - 1)
        hd = re.search(r"<<-?\s*'?([A-Za-z_]\w*)'?", s)
        if hd:
            term = hd.group(1)
    return out


class BgFake:
    """fake_bg_finalizer.sh 的一個實例（自己一個 session，測試結束整組 SIGKILL）。"""

    def __init__(self, tc, sb, run, tag, wait=True, **env):
        self.sb, self.run = sb, run
        self.session = session_dir(sb, tag)
        e = sb.env(FAKE_RUN_ID=run, FAKE_SESSION=str(self.session), **env)
        self.p = subprocess.Popen(["bash", str(FAKE_BG)], env=e, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
        tc.addCleanup(self.kill)
        if wait:
            self.wait_ready()

    @property
    def pid(self):
        return self.p.pid

    def ready(self):
        st = read_json(self.sb.home / "record.status.json")
        return read_pid_file(self.sb) == str(self.p.pid) and isinstance(st, dict) and st.get("runId") == self.run

    def wait_ready(self, timeout=15):
        until(self.ready, timeout, f"{self.run} 寫出 record.pid 與 record.status.json")

    def kill(self):
        try:
            os.killpg(self.p.pid, signal.SIGKILL)
        except OSError:
            pass
        self.p.wait()

    def sigterm(self):
        os.kill(self.p.pid, signal.SIGTERM)

    def count(self):
        try:
            return int((self.sb.home / f"fake_bg_{self.run}.sigterm").read_text().strip() or 0)
        except (OSError, ValueError):
            return 0

    def status(self):
        return read_json(bg_status_path(self.sb, self.run))

    def lock_held(self):
        return lock_held_no_create(bg_lock_path(self.sb, self.run))

    def alive(self):
        return self.p.poll() is None

    def in_background(self):
        st = self.status()
        return isinstance(st, dict) and st.get("phase") == "finalizing" and self.lock_held() \
            and read_pid_file(self.sb) != str(self.p.pid) and try_lock_nb(self.sb.home / "record.lock")

    def enter_background(self, timeout=10):
        """送 SIGTERM，等它做完 §3.23 第 2–7 步（每場鎖被持有、每場狀態檔 finalizing、record.pid 已刪、record.lock 已放）。"""
        self.sigterm()
        until(self.in_background, timeout, f"{self.run} 進入背景收尾")

    def wait_exit(self, timeout):
        try:
            return self.p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise AssertionError(f"{self.run} {timeout} 秒內沒有結束") from None


def run_status(sb):
    return sb.meeting("record", "status", timeout=60)


class TestR3xBackground(unittest.TestCase):
    # ---------- §4.48–§4.50：協定參考 ----------

    # spec §4.48.7（協定參考）：替身收到 SIGTERM 後 3 秒內 record.lock 可被取得、它仍在收尾；此時開下一場回 0
    def test_next_recording_starts_during_background_finalize(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.sigterm()
        until(lambda: try_lock_nb(sb.home / "record.lock"), 3.0, "收到 SIGTERM 後 3 秒內 record.lock 可被 LOCK_NB 取得")
        self.assertTrue(a.lock_held(), "放開開錄鎖後，每場鎖仍應被持有（還在收尾）")
        self.assertEqual((a.status() or {}).get("phase"), "finalizing", "每場狀態檔 phase 應為 finalizing")
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 0, f"背景收尾中應能開下一場\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertNotIn("已有錄製在跑", r.stdout + r.stderr)
        self.assertTrue(a.alive(), "開下一場時上一場應仍在背景收尾")

    # spec §4.49.5（協定參考）：A 放鎖後 B（fake_recorder.sh）開錄；A 收尾結束後不改寫 B 的共用狀態與 pid
    def test_previous_does_not_touch_next_state(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="3")
        a.enter_background()
        sess_b = session_dir(sb, "B")
        b = start_fake(self, sb, FAKE_RUN_ID="run-b", FAKE_SESSION=str(sess_b))
        until(lambda: read_pid_file(sb) == str(b.pid), 10, "B 寫出 record.pid")
        self.assertEqual(a.wait_exit(30), 0)
        st = read_json(sb.home / "record.status.json") or {}
        self.assertEqual((st.get("runId"), st.get("pid"), st.get("phase")), ("run-b", b.pid, "recording"),
                         "A 收尾結束後 record.status.json 應仍是 B 的 recording")
        self.assertEqual(read_pid_file(sb), str(b.pid), "record.pid 應仍是 B 的 pid")
        fa = a.status() or {}
        self.assertEqual((fa.get("phase"), fa.get("code")), ("done", 0), "finalizing/<A>.status.json 應為 done／0")
        until(lambda: not a.lock_held(), 2.0, "A 結束後 finalizing/<A>.lock 沒人持有")

    # spec §4.49.6（協定參考）：沒有 B 時，A 收尾結束後 record.status.json 是 A 的 done／0
    def test_shared_status_updated_when_untouched(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="1")
        a.enter_background()
        self.assertEqual(a.wait_exit(30), 0)
        st = read_json(sb.home / "record.status.json") or {}
        self.assertEqual((st.get("runId"), st.get("phase"), st.get("code")), ("run-a", "done", 0))

    # spec §4.50.3（協定參考）：兩場幾乎同時進背景，取得排隊鎖到寫最終狀態的區間不重疊；排隊中的那一場先 queued: true
    def test_queue_one_at_a_time(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="2")
        c = BgFake(self, sb, "run-c", "C", wait=False, FAKE_FINALIZE_SECONDS="2")  # 等 A 放開 record.lock 才寫得出狀態
        seen = {"run-a": [], "run-c": []}
        stop = threading.Event()

        def poll():
            while not stop.is_set():
                for f in (a, c):
                    st = f.status()
                    if isinstance(st, dict):
                        seen[f.run].append(dict(st))
                time.sleep(0.03)

        th = threading.Thread(target=poll, daemon=True)
        th.start()
        try:
            a.sigterm()
            c.wait_ready()
            c.sigterm()
            self.assertEqual(a.wait_exit(30), 0)
            self.assertEqual(c.wait_exit(30), 0)
        finally:
            stop.set()
            th.join(timeout=5)
        ev = parse_events(sb)
        spans = {}
        for run in ("run-a", "run-c"):
            s, e = event_time(ev, run, "start"), event_time(ev, run, "end")
            self.assertIsNotNone(s, f"{run} 應有 start 事件")
            self.assertIsNotNone(e, f"{run} 應有 end 事件")
            spans[run] = (s, e)
        (s1, e1), (s2, e2) = sorted(spans.values())
        self.assertLessEqual(e1, s2, f"兩場收尾的區間不得重疊：{spans}")
        second = max(spans, key=lambda r: spans[r][0])
        states = seen[second]
        first_unqueued = next((i for i, st in enumerate(states) if "queued" not in st), None)
        self.assertTrue(any(st.get("queued") is True for st in states[:first_unqueued]),
                        f"排隊中的 {second} 每場狀態檔應先是 queued: true")
        final = read_json(bg_status_path(sb, second)) or {}
        self.assertNotIn("queued", final, "取得排隊鎖後每場狀態檔不應有 queued 鍵")

    # ---------- §4.51 stop ----------

    # spec §4.51.1：A 背景收尾、B 錄製中 → stop 只對 B 送 SIGTERM、等 B（排在 A 後面也照等）、回 B 的結果
    def test_stop_waits_own_run(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="4")
        a.enter_background()
        b = BgFake(self, sb, "run-b", "B", FAKE_FINALIZE_SECONDS="1")
        ca = a.count()
        r = run_stop(self, sb, timeout=60)
        self.assertEqual(r.returncode, 0, f"B done／0 → stop 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual(a.count(), ca, "stop 不得對背景收尾中的 A 送 SIGTERM")
        self.assertEqual(b.count(), 1, "stop 應只對 B 送一次 SIGTERM")
        lines = r.stdout.splitlines()
        self.assertIn(f"場次：{b.session}", lines, "stdout 的「場次：」應是 B 的場次")
        self.assertNotIn(f"場次：{a.session}", lines, "stdout 的「場次：」不得是 A 的場次")
        fb = b.status() or {}
        self.assertEqual((fb.get("phase"), fb.get("code")), ("done", 0))
        ev = parse_events(sb)
        self.assertIsNotNone(event_time(ev, "run-b", "end"), "stop 回來時 B 應已收尾完成")
        self.assertGreaterEqual(event_time(ev, "run-b", "start"), event_time(ev, "run-a", "end") or 0,
                                "前提：B 排在 A 後面收尾")

    # spec §4.51.2：B 在背景收尾失敗（FAKE_STOP_CODE=5）→ stop 回 5、stderr 含 meeting.sh record finish
    def test_stop_own_run_failure(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="4")
        a.enter_background()
        BgFake(self, sb, "run-b", "B", FAKE_FINALIZE_SECONDS="1", FAKE_STOP_CODE="5")
        r = run_stop(self, sb, timeout=60)
        self.assertEqual(r.returncode, 5, f"B 收尾失敗 → stop 應回 5\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("meeting.sh record finish", r.stderr)

    def _background_only(self, code):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="2", FAKE_STOP_CODE=str(code))
        a.enter_background()
        self.assertFalse((sb.home / "record.pid").exists(), "前提：沒有 record.pid")
        self.assertTrue(try_lock_nb(sb.home / "record.lock"), "前提：record.lock 沒人持有")
        st = read_json(sb.home / "record.status.json") or {}
        self.assertEqual((st.get("runId"), st.get("background")), ("run-a", True), "前提：共用狀態檔是 A 自己")
        ca = a.count()
        r = run_stop(self, sb, timeout=60)
        self.assertEqual(a.count(), ca, "只剩背景收尾時 stop 不得送任何訊號")
        self.assertIn(WAIT_BG_HEADER, r.stdout, f"stdout 應說明在等背景收尾\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn((a.status() or {}).get("phase"), ("done", "failed"), "stop 回來時 A 應已結束")
        return sb, a, r

    # spec §4.51.3、R3x-§2.2：只剩背景收尾 A（done／0）→ 不送訊號、等 A、回 0，stdout 含 A 的場次與「✓ 背景收尾完成。」
    def test_stop_background_only_success(self):
        _, a, r = self._background_only(0)
        self.assertEqual(r.returncode, 0, f"A done／0 → 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn(str(a.session), r.stdout)
        self.assertIn(BG_DONE, r.stdout)

    # spec §4.51.3：只剩背景收尾 A（failed／5）→ 回 5，stderr 含「背景收尾失敗」與 meeting.sh record finish
    def test_stop_background_only_failure(self):
        _, a, r = self._background_only(5)
        self.assertEqual(r.returncode, 5, f"A failed／5 → 應回 5\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("背景收尾失敗", r.stderr)
        self.assertIn("meeting.sh record finish", r.stderr)

    # spec §4.51.4、design R3x-D13 決定 3：兩個活著的背景收尾 → 等兩者都結束；都成功 0，任一失敗 5
    def test_stop_background_waits_all(self):
        for code_c, want in ((0, 0), (5, 5)):
            with self.subTest(c_code=code_c):
                sb = Sandbox(self)
                a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="2")
                a.enter_background()
                c = BgFake(self, sb, "run-c", "C", FAKE_FINALIZE_SECONDS="2", FAKE_STOP_CODE=str(code_c))
                c.enter_background()
                ca, cc = a.count(), c.count()
                r = run_stop(self, sb, timeout=60)
                self.assertEqual(r.returncode, want, f"stdout:{r.stdout}\nstderr:{r.stderr}")
                self.assertEqual((a.count(), c.count()), (ca, cc), "不得送任何訊號")
                for f in (a, c):
                    self.assertIn((f.status() or {}).get("phase"), ("done", "failed"),
                                  f"stop 回來時 {f.run} 應已寫最終狀態（等全部結束）")

    # spec §4.51.5：等待中背景收尾當掉（FAKE_CRASH=2）→ 當掉後 5 秒內回 5，stderr 含「背景收尾異常中止」與 finish 指令
    def test_stop_background_crash_during_wait(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_CRASH="2", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        crashed = {}

        def watch():
            a.p.wait()
            crashed["t"] = time.monotonic()

        th = threading.Thread(target=watch, daemon=True)
        th.start()
        r = run_stop(self, sb, timeout=40)
        t_end = time.monotonic()
        self.assertEqual(r.returncode, 5, f"背景收尾當掉 → 應回 5\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("t", crashed, "前提：stop 回來時替身已當掉")
        self.assertLessEqual(t_end - crashed["t"], 5.0, "應在當掉後 5 秒內回來")
        self.assertIn("背景收尾異常中止", r.stderr)
        self.assertIn(f'meeting.sh record finish "{a.session}"', r.stderr)

    # spec §4.51.6：沒有錄製、只有當掉的每場狀態檔（FAKE_CRASH=0）→ 回 3，stderr 含「沒有錄製在跑」與 finish 指令
    def test_stop_background_crashed_returns_3(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_CRASH="0", FAKE_FINALIZE_SECONDS="10")
        a.sigterm()
        a.wait_exit(15)
        until(lambda: not a.lock_held(), 2.0, "當掉後每場鎖由核心放開")
        self.assertEqual((a.status() or {}).get("phase"), "finalizing", "前提：每場狀態檔停在 finalizing")
        r = run_stop(self, sb)
        self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("沒有錄製在跑", r.stderr)
        self.assertIn("meeting.sh record finish", r.stderr, "有當掉的背景收尾時 stderr 應另含 finish 指令")

    # spec §4.51.7、§6 第 147 條：cmd_stop 含 queued，等待迴圈內有一行重設起算點；仍恰有一個 limit 區塊
    def test_stop_limit_excludes_queue(self):
        src = RECORD_SH.read_text(encoding="utf-8")
        body, blocks = cmd_stop_limit_python(src)
        self.assertIsNotNone(body, "bin/record.sh 找不到 cmd_stop()")
        self.assertEqual(len(blocks), 1, "cmd_stop 內應恰有一個 limit=\"$(python3 … <<'PY' 區塊（§4.27.5）")
        self.assertTrue("queued" in body, "cmd_stop 應看目標狀態的 queued（排隊時間不計入上限）")
        self.assertTrue(any('t0="$(date +%s)"' in ln for ln in lines_in_loops(body)),
                        "cmd_stop 的等待迴圈內應有一行 t0=\"$(date +%s)\"（目標排隊中時重設起算點）")

    # spec §4.51.9、§4.51.10（修正輪 I1）：共用狀態檔 runId＝目標且沒有 background → 照 R3，不讀不試 finalizing/
    def test_stop_same_run_skips_lock_check(self):
        sb = Sandbox(self)
        sess = session_dir(sb, "同場")
        p = start_fake(self, sb, FAKE_PHASE="finalizing", FAKE_RUN_ID="run-same", FAKE_SESSION=str(sess))
        write_bg_status(sb, "run-other", "finalizing", session=session_dir(sb, "別場"), message="收尾中")
        before = sorted(x.name for x in (sb.home / "finalizing").iterdir())
        st = read_json(sb.home / "record.status.json")

        def finish_later():
            time.sleep(1.5)
            write_shared(sb, dict(st, phase="done", code=0, message="已完成（範例訊息）", updatedAt=now_iso()))

        th = threading.Thread(target=finish_later)
        th.start()
        r = run_stop(self, sb)
        th.join()
        self.assertEqual(r.returncode, 0, f"共用狀態檔改成 done／0 後 stop 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIsNone(p.poll(), "phase 已是 finalizing 時不得送 SIGTERM（替身收到會結束）")
        self.assertEqual(sorted(x.name for x in (sb.home / "finalizing").iterdir()), before,
                         "finalizing/ 內不得有新建的檔（不得試目標的每場鎖）")

    # spec §4.51.11（修正輪 N2）：等待背景收尾的函式（cmd_stop 之外）含 startedAt、630、7200、queued、重設起算點
    def test_stop_background_only_wait_limit(self):
        src = RECORD_SH.read_text(encoding="utf-8")
        needles = ("startedAt", "630", "7200", "queued", 't0="$(date +%s)"')
        funcs = bash_functions(src)
        self.assertIn("cmd_stop", funcs, "bin/record.sh 找不到 cmd_stop()")
        cands = [n for n, b in funcs.items() if n != "cmd_stop" and all(x in b for x in needles)]
        self.assertTrue(cands, f"bin/record.sh 應有 cmd_stop 之外、等待背景收尾的函式，本體含 {list(needles)}")
        _, blocks = cmd_stop_limit_python(src)
        self.assertEqual(len(blocks), 1, "cmd_stop 內仍應恰有一個 limit 區塊")

    # spec §4.51.12 (a)：沒有 record.pid、另一個程序持有 record.lock、有活著的背景收尾 → 回 3、不等 A
    def test_stop_lock_held_without_pid_returns_3(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        hold_lock(self, sb.home / "record.lock")
        self.assertFalse((sb.home / "record.pid").exists(), "前提：沒有 record.pid")
        ca = a.count()
        t0 = time.monotonic()
        r = run_stop(self, sb, timeout=30)
        took = time.monotonic() - t0
        self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("沒有錄製在跑", r.stderr)
        self.assertEqual(a.count(), ca, "不得對 A 送訊號")
        self.assertLess(took, 5.0, "不得等 A")
        self.assertTrue(a.alive(), "A 應仍在收尾（stop 沒有等它）")

    # spec §4.51.12 (b)：record.pid 的 pid 已死、共用狀態檔是那個 pid 的 recording → 照 R3 回 3（刪過時 pid）、不等 A
    def test_stop_dead_pid_in_progress_returns_3(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        dp = dead_pid()
        (sb.home / "record.pid").write_text(f"{dp}\n")
        write_status(sb, dp, phase="recording", run_id="run-dead")
        ca = a.count()
        t0 = time.monotonic()
        r = run_stop(self, sb, timeout=30)
        took = time.monotonic() - t0
        self.assertEqual(r.returncode, 3, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual(r.stderr.strip(), f"沒有錄製在跑：record.pid 的 pid {dp} 已經結束（已刪掉過時的 record.pid）。",
                         "stderr 應與 R3 相同")
        self.assertFalse((sb.home / "record.pid").exists(), "應刪掉過時的 record.pid")
        self.assertEqual(a.count(), ca)
        self.assertLess(took, 5.0, "不得等 A")
        self.assertTrue(a.alive())

    # spec §4.51.12 (d)（複查修正）：共用狀態檔是下一場的 preflight_failed、沒有 pid、鎖沒人持有 → 等 A，A 成功回 0
    def test_stop_after_preflight_failed_waits_background(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="2")
        a.enter_background()
        write_status(sb, dead_pid(), phase="preflight_failed", run_id="run-b", code=4,
                     message="沒有螢幕錄製權限（範例訊息）", session=str(session_dir(sb, "B")))
        self.assertFalse((sb.home / "record.pid").exists(), "前提：沒有 record.pid")
        ca = a.count()
        r = run_stop(self, sb, timeout=60)
        self.assertEqual(r.returncode, 0, f"應等 A 完成並回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual(a.count(), ca)
        self.assertIn(WAIT_BG_HEADER, r.stdout)
        self.assertEqual((a.status() or {}).get("phase"), "done", "stop 回來時 A 應已完成")

    # spec §4.51.13、§4.52.9、§4.53.4（修正輪 I10）：孤兒不算活著也不算當掉；stop 回 3 不提 finish；status 不變；孤兒檔不刪
    def test_orphan_ignored_by_stop_and_status(self):
        sb = Sandbox(self)
        orphan_status, orphan_lock = bg_status_path(sb, "run-orphan"), bg_lock_path(sb, "run-orphan")

        def make_orphan():
            write_bg_status(sb, "run-orphan", "finalizing", session=sb.base / "不存在的場次", message="收尾中",
                            lock_file=True)

        def clear():
            for f in (orphan_status, orphan_lock):
                f.unlink(missing_ok=True)
            if (sb.home / "finalizing").exists():
                (sb.home / "finalizing").rmdir()

        done = {"schemaVersion": 1, "runId": "run-prev", "pid": dead_pid(), "phase": "done", "code": 0,
                "message": "已完成（範例訊息）", "session": str(session_dir(sb, "上次")), "startedAt": now_iso(-600),
                "updatedAt": now_iso(-300), "segments": 1, "preflight": [], "warnings": []}
        for label, shared in (("沒有共用狀態檔", None), ("共用狀態檔是別場的 done", done)):
            with self.subTest(case=label):
                (sb.home / "record.status.json").unlink(missing_ok=True)
                if shared is not None:
                    write_shared(sb, shared)
                base = run_status(sb)
                make_orphan()
                r = run_status(sb)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (base.returncode, base.stdout, base.stderr),
                                 "只有孤兒時 status 的輸出與結束碼應與沒有 finalizing/ 時逐字相同")
                self.assertTrue(orphan_status.exists() and orphan_lock.exists(), "status 不得刪孤兒檔")
                clear()
        (sb.home / "record.status.json").unlink(missing_ok=True)
        make_orphan()
        r = run_stop(self, sb)
        self.assertEqual(r.returncode, 3, f"只有孤兒時 stop 應回 3\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertNotIn("meeting.sh record finish", r.stderr, "孤兒不算當掉，不得提示 finish")
        self.assertTrue(orphan_status.exists() and orphan_lock.exists(), "stop 不得刪孤兒檔")

    # ---------- §4.52 status ----------

    # spec §4.52.1：B 錄製中、A 背景收尾 → 回 0；錄製行之後多一行「上一場收尾中：<A>」（排隊中加「（排隊中）」）
    def test_status_shows_background_running(self):
        sb = Sandbox(self)
        qh = hold_lock(self, sb.home / "finalize.queue.lock")
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        self.assertIs((a.status() or {}).get("queued"), True, "前提：排隊鎖被佔著，A 在排隊")
        sess_b = session_dir(sb, "B")
        b = start_fake(self, sb, FAKE_RUN_ID="run-b", FAKE_SESSION=str(sess_b))
        until(lambda: read_pid_file(sb) == str(b.pid), 10, "B 寫出 record.pid")
        r = run_status(sb)
        self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        lines = r.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("錄製中") and str(sess_b) in lines[0],
                        f"第一行應是 R3 的錄製行：{lines[:1]}")
        want_q = f"  上一場收尾中：{a.session}（排隊中）"
        self.assertIn(want_q, lines[1:], f"錄製行之後應多一行 {want_q!r}\nstdout:{r.stdout}")
        qh.kill()
        qh.wait()
        until(lambda: "queued" not in (a.status() or {"queued": True}), 5.0, "A 取得排隊鎖、每場狀態檔沒有 queued")
        r2 = run_status(sb)
        self.assertEqual(r2.returncode, 0)
        lines2 = r2.stdout.splitlines()
        self.assertIn(f"  上一場收尾中：{a.session}", lines2[1:], f"stdout:{r2.stdout}")
        self.assertNotIn(want_q, lines2)

    # spec §4.52.2：B 錄製中、A 當掉 → 回 0，多一行 ⚠ 上一場收尾異常中止 與 finish 指令
    def test_status_crash_while_recording_returns_0(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_CRASH="0", FAKE_FINALIZE_SECONDS="10")
        a.sigterm()
        a.wait_exit(15)
        until(lambda: not a.lock_held(), 2.0, "當掉後每場鎖由核心放開")
        b = start_fake(self, sb, FAKE_RUN_ID="run-b", FAKE_SESSION=str(session_dir(sb, "B")))
        until(lambda: read_pid_file(sb) == str(b.pid), 10, "B 寫出 record.pid")
        r = run_status(sb)
        self.assertEqual(r.returncode, 0, f"錄製中＋上一場當掉 → 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        want = f'  ⚠ 上一場收尾異常中止：{a.session}；收尾： meeting.sh record finish "{a.session}"'
        self.assertIn(want, r.stdout.splitlines(), f"stdout:{r.stdout}")

    # spec §4.52.3、R3x-§2.2：沒有錄製（共用狀態檔是別場的 done）、A 當掉 → 回 5，stderr 兩行
    def test_status_crash_without_recording_returns_5(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_CRASH="0", FAKE_FINALIZE_SECONDS="10")
        a.sigterm()
        a.wait_exit(15)
        until(lambda: not a.lock_held(), 2.0, "當掉後每場鎖由核心放開")
        write_status(sb, dead_pid(), phase="done", run_id="run-b", session=str(session_dir(sb, "B")),
                     message="已完成（範例訊息）")
        r = run_status(sb)
        self.assertEqual(r.returncode, 5, f"沒有錄製＋背景收尾當掉 → 應回 5\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("✗ 上一場收尾異常中止（收尾程序已不在，狀態停在收尾中）。段落還在，收尾：", r.stderr)
        self.assertIn(f'    meeting.sh record finish "{a.session}"', r.stderr)

    # spec §4.52.4：共用狀態檔就是活著的背景收尾 A → 回 0；R3 的「收尾中 …」行加一行「背景收尾中，可以開始下一場」
    def test_status_background_self(self):
        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        st = read_json(sb.home / "record.status.json") or {}
        self.assertEqual((st.get("runId"), st.get("background")), ("run-a", True), "前提：共用狀態檔是 A 自己")
        r = run_status(sb)
        self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        lines = r.stdout.splitlines()
        self.assertTrue(lines and lines[0].startswith("收尾中"), f"第一行應是 R3 的「收尾中 …」行：{lines[:1]}")
        self.assertIn("  背景收尾中，可以開始下一場", lines)
        self.assertNotIn("上一場收尾中", r.stdout, "A 不得另印「上一場收尾中」")

    # spec §4.52.5、design R3x-D13 決定 1：A 已結束、共用狀態檔是別場 → A.updatedAt ≥ 共用 startedAt 才印完成／失敗行
    def test_status_background_finished_lines(self):
        sb = Sandbox(self)
        sess_a, sess_b = session_dir(sb, "A"), session_dir(sb, "B")
        write_status(sb, dead_pid(), phase="done", run_id="run-b", session=str(sess_b), message="已完成（範例訊息）",
                     startedAt=now_iso(-3600), updatedAt=now_iso(-3500))
        base = run_status(sb)
        cases = (
            ("成功", dict(phase="done", code=0, message="已完成（範例訊息）", updated=now_iso()),
             f"  上一場收尾完成：{sess_a}"),
            ("失敗", dict(phase="failed", code=5, message="收尾失敗（範例訊息）\n第二行", updated=now_iso()),
             f'  ⚠ 上一場收尾失敗：收尾失敗（範例訊息）；段落保留，收尾： meeting.sh record finish "{sess_a}"'),
        )
        for label, kw, want in cases:
            with self.subTest(case=label):
                write_bg_status(sb, "run-a", kw.pop("phase"), session=sess_a, **kw)
                r = run_status(sb)
                self.assertEqual(r.returncode, base.returncode, "結束碼應照 R3 現行（不因這一行改變）")
                self.assertIn(want, r.stdout.splitlines(), f"stdout:{r.stdout}")
        with self.subTest(case="A 比共用狀態檔的開錄還早結束"):
            write_bg_status(sb, "run-a", "done", session=sess_a, message="已完成（範例訊息）", updated=now_iso(-7200))
            r = run_status(sb)
            self.assertEqual((r.returncode, r.stdout), (base.returncode, base.stdout),
                             "A.updatedAt 早於共用狀態檔的 startedAt 時不印")

    # spec §4.52.6：沒有 <home>/finalizing/ 時 status 的輸出與結束碼與 R3 逐字相同
    def test_status_unchanged_without_background(self):
        sb = Sandbox(self)
        sess = str(session_dir(sb, "R3"))
        status_file = sb.home / "record.status.json"
        cases = [
            ("沒有狀態檔", None, 0, "沒有錄製在跑。\n", ""),
            ("done", dict(phase="done", message="已完成（範例訊息）"), 0, f"沒有錄製在跑。\n上次錄製：已完成　{sess}\n", ""),
            ("failed", dict(phase="failed", code=5, message="收尾失敗，段落保留（範例訊息）"), 0,
             f"沒有錄製在跑。\n上次錄製出錯：收尾失敗，段落保留（範例訊息）\n  段落保留，收尾： meeting.sh record finish \"{sess}\"\n",
             ""),
            ("preflight_failed", dict(phase="preflight_failed", code=4, message="沒有螢幕錄製權限（範例訊息）"), 0,
             "沒有錄製在跑。\n上次開錄前檢查沒通過：沒有螢幕錄製權限（範例訊息）\n", ""),
            ("preflight 中斷", dict(phase="preflight"), 0, "沒有錄製在跑（上次開錄前檢查中斷）。\n", ""),
            ("錄製器已不在", dict(phase="recording"), 5, "",
             "✗ 上次錄製異常中止（錄製器已不在，狀態停在錄製中）。已落盤的段落還在，收尾：\n"
             f"    meeting.sh record finish \"{sess}\"\n  （最後一段未收尾的 1 分鐘會丟）\n"),
        ]
        for label, st, rc, out, err in cases:
            with self.subTest(case=label):
                status_file.unlink(missing_ok=True)
                if st is not None:
                    st = dict(st)
                    write_status(sb, dead_pid(), phase=st.pop("phase"), run_id="run-r3", session=sess, **st)
                r = run_status(sb)
                self.assertEqual((r.returncode, r.stdout, r.stderr), (rc, out, err))
        self.assertFalse((sb.home / "finalizing").exists(), "status 不得建立 <home>/finalizing/")

    # spec §4.52.7、§3.22 旁觀者規則：判斷每場鎖時不得建立鎖檔；沒有鎖檔＝沒人持有 → 判為當掉
    def test_status_does_not_create_lock_files(self):
        sb = Sandbox(self)
        sess = session_dir(sb, "A")
        write_bg_status(sb, "run-a", "finalizing", session=sess, message="收尾中")
        lock = bg_lock_path(sb, "run-a")
        self.assertFalse(lock.exists(), "前提：沒有每場鎖檔")
        r = run_status(sb)
        self.assertFalse(lock.exists(), "status 不得建立每場鎖檔（O_RDWR 不帶 O_CREAT）")
        self.assertEqual(r.returncode, 5, f"沒有錄製、該場判為當掉 → 應回 5\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn("上一場收尾異常中止", r.stderr)

    # spec §4.52.8（修正輪 N3）：沒有錄製（共用狀態檔是 B 的 done）、A 還在跑 → 回 0，B 的行之後多「上一場收尾中」
    def test_status_no_recording_shows_running(self):
        sb = Sandbox(self)
        qh = hold_lock(self, sb.home / "finalize.queue.lock")
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="10")
        a.enter_background()
        sess_b = session_dir(sb, "B")
        write_status(sb, dead_pid(), phase="done", run_id="run-b", session=str(sess_b), message="已完成（範例訊息）")
        r = run_status(sb)
        self.assertEqual(r.returncode, 0, f"stdout:{r.stdout}\nstderr:{r.stderr}")
        lines = r.stdout.splitlines()
        self.assertEqual(lines[:2], ["沒有錄製在跑。", f"上次錄製：已完成　{sess_b}"], "先印 R3 現行對 B 的行")
        self.assertIn(f"  上一場收尾中：{a.session}（排隊中）", lines[2:], f"stdout:{r.stdout}")
        qh.kill()
        qh.wait()
        until(lambda: "queued" not in (a.status() or {"queued": True}), 5.0, "A 取得排隊鎖")
        r2 = run_status(sb)
        self.assertEqual(r2.returncode, 0)
        self.assertIn(f"  上一場收尾中：{a.session}", r2.stdout.splitlines()[2:], f"stdout:{r2.stdout}")

    # ---------- §4.53 finish ----------

    # spec §4.53.1、§3.21 清理 (2)：finish 回 0 後刪掉同場次、finalizing、鎖沒人持有的每場檔；其他不碰；失敗時一個都不刪
    def test_finish_clears_crashed_background_state(self):
        sb = Sandbox(self)
        sess = m.make_record_session(sb.root, [dict(dur=2.0), dict(dur=2.0)])
        other = session_dir(sb, "別場")
        write_bg_status(sb, "run-crash", "finalizing", session=sess, message="收尾中", lock_file=True)
        write_bg_status(sb, "run-other", "finalizing", session=other, message="收尾中", lock_file=True)
        write_bg_status(sb, "run-alive", "finalizing", session=sess, message="收尾中")
        hold_lock(self, bg_lock_path(sb, "run-alive"))
        write_bg_status(sb, "run-done", "done", session=sess, message="已完成（範例訊息）", lock_file=True)
        keep = [f(sb, r) for r in ("run-other", "run-alive", "run-done") for f in (bg_status_path, bg_lock_path)]
        crash = [bg_status_path(sb, "run-crash"), bg_lock_path(sb, "run-crash")]

        r = sb.meeting("record", "finish", sess, timeout=300, MH_FFMPEG=FAILING_FFMPEG)
        self.assertNotEqual(r.returncode, 0, "前提：替身 ffmpeg 一律失敗，finish 不回 0")
        self.assertEqual([p.name for p in crash + keep if not p.exists()], [], "finish 沒回 0 時一個都不得刪")

        r = sb.meeting("record", "finish", sess, timeout=300)
        self.assertEqual(r.returncode, 0, f"finish 應成功\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertEqual([p.name for p in crash if p.exists()], [], "同場次、當掉的每場狀態檔與鎖檔應被刪")
        self.assertEqual([p.name for p in keep if not p.exists()], [], "別場次、活著的、終態的都不得碰")

    # ---------- §4.56.2（閘門 2 決定 5 選 A：只告警） ----------

    # spec §4.56.2（修正輪 I11、§7 疑慮 76）：開錄前有活著的背景收尾 → stdout 多一行 ⚠；門檻、--min-free-bytes、結束碼不變
    def test_disk_warning_with_background(self):
        base = Sandbox(self)
        r0 = base.meeting("record", base.root, "--window", "1", timeout=60)
        self.assertEqual(r0.returncode, 0, f"stdout:{r0.stdout}\nstderr:{r0.stderr}")
        self.assertNotIn("上一場收尾還在跑", r0.stdout + r0.stderr, "沒有背景收尾時不得印")
        start0 = [c for c in base.read_calls() if "start" in c]
        self.assertEqual(len(start0), 1)

        sb = Sandbox(self)
        a = BgFake(self, sb, "run-a", "A", FAKE_FINALIZE_SECONDS="20")
        a.enter_background()
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, r0.returncode, f"結束碼不變\nstdout:{r.stdout}\nstderr:{r.stderr}")
        lines = r.stdout.splitlines()
        want = DISK_WARNING.format(n=1)
        self.assertIn(want, lines, f"有活著的背景收尾時 stdout 應多一行告警\nstdout:{r.stdout}")
        started = next((i for i, ln in enumerate(lines) if ln.startswith("● 開始錄製")), len(lines))
        self.assertLess(lines.index(want), started, "告警應在開錄（launch start）之前印")
        start1 = [c for c in sb.read_calls() if "start" in c]
        self.assertEqual(len(start1), 1)
        self.assertEqual(flag_value(start1[0], "--min-free-bytes"), flag_value(start0[0], "--min-free-bytes"),
                         "--min-free-bytes 的值不變（不扣背景收尾用量）")
        self.assertTrue(a.alive(), "前提：開錄時 A 仍在背景收尾")


if __name__ == "__main__":
    unittest.main()

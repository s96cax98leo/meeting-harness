"""R3 開錄鎖、preflight 互斥、stop 的 pid 確認、defaults 合併寫入（spec R3-§2.2、§3.15、§3.19、§4.26.3–§4.26.7、
§4.27.2、§4.27.3、§4.27.5、§4.27.6、§4.43.2、§4.43.3；§6 第 119、136 條）。

錄製器一律以 fakes/fake_open.sh（MH_RECORD_OPEN）與 fakes/fake_recorder.sh 替身；「別的程序持有鎖」由本檔起的
python3 子程序以 fcntl.flock 模擬。所有檔案都在 TMPDIR 的 sandbox（MH_RECORD_HOME），不碰 ~/.meeting-harness。
"""
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from tests.record._helpers import FAKE_RECORDER, MEETING_SH, RECORD_SH, Sandbox, dead_pid, tmpdir

REFUSED_RECORDING = "已有錄製在跑"
REFUSED_PREFLIGHT = "錄製中"
DEFAULT_KEYS = {"root", "type", "attendees", "harness", "python3", "ffmpeg", "minFreeBytes"}

HOLDER = r'''
import fcntl, os, sys, time
path, seconds = sys.argv[1], float(sys.argv[2])
fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
print("ready", flush=True)
end = time.monotonic() + seconds
while time.monotonic() < end:
    time.sleep(0.02)
fcntl.flock(fd, fcntl.LOCK_UN)
print("released", flush=True)
'''

# 「持鎖期間讀檔、睡、再寫回」的另一個寫者（spec §4.43.3）：沒有共用鎖的寫者會在它睡的時候寫入，然後被它覆蓋
STALE_WRITER = r'''
import fcntl, json, os, sys, tempfile, time
home, seconds = sys.argv[1], float(sys.argv[2])
fd = os.open(os.path.join(home, "record.defaults.lock"), os.O_CREAT | os.O_RDWR, 0o600)
fcntl.flock(fd, fcntl.LOCK_EX)
path = os.path.join(home, "record.defaults.json")
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    data = {}
print("ready", flush=True)
time.sleep(seconds)
data["x"] = 1
tfd, tmp = tempfile.mkstemp(dir=home)
with os.fdopen(tfd, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False)
os.replace(tmp, path)
fcntl.flock(fd, fcntl.LOCK_UN)
print("released", flush=True)
'''


def hold_lock(tc, path, seconds=60.0):
    """另一個程序持有 path 的 flock seconds 秒；回傳 Popen（已確認拿到鎖）。"""
    p = subprocess.Popen([sys.executable, "-c", HOLDER, str(path), str(seconds)], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    tc.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
    line = p.stdout.readline().strip()
    tc.assertEqual(line, "ready", "持鎖程序沒有拿到鎖")
    return p


def try_lock_nb(path):
    """不重試的 LOCK_NB 試鎖：拿到就放掉並回 True。"""
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    finally:
        os.close(fd)
    return True


def sleeper(tc, seconds=120):
    """一個無關的 sleep 程序（程序名 sleep，不是 MeetingRecorder，也不是 MH_RECORDER_COMM 預設的 bash）。

    由 bash 在背景起再脫離（不是本測試程序的子程序），被殺掉後由系統收屍，kill(pid, 0) 才看得出它已結束。回傳 pid。"""
    r = subprocess.run(["bash", "-c", f"sleep {int(seconds)} >/dev/null 2>&1 </dev/null & echo $!"],
                       capture_output=True, text=True, timeout=10)
    pid = int(r.stdout.strip())

    def cleanup():
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
    tc.addCleanup(cleanup)
    return pid


def pid_alive(pid, wait=0.0):
    """pid 是否還活著（等 wait 秒內是否結束）。"""
    deadline = time.monotonic() + wait
    while True:
        try:
            os.kill(pid, 0)
            ok = True
        except OSError:
            ok = False
        if not ok or time.monotonic() >= deadline:
            return ok
        time.sleep(0.05)


def run_stop(tc, sb, env=None, timeout=40, **over):
    """meeting record stop；逾時就判失敗（不讓測試卡住），並收掉整個程序群組。"""
    e = env if env is not None else sb.env(**over)
    p = subprocess.Popen(["bash", str(MEETING_SH), "record", "stop"], cwd=str(sb.cwd), env=e,
                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        out, err = p.communicate()
        tc.fail(f"record stop {timeout} 秒內沒有結束\nstdout:{out}\nstderr:{err}")
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def write_status(sb, pid, phase="recording", run_id="r3-lock-run", **extra):
    now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    st = {"schemaVersion": 1, "runId": run_id, "pid": pid, "phase": phase, "code": 0, "message": "",
          "session": "", "startedAt": now, "updatedAt": now, "segments": 1, "preflight": [], "warnings": []}
    st.update(extra)
    (sb.home / "record.status.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    return st


def start_fake(tc, sb, **env):
    """啟動 fake_recorder.sh（FAKE_LOCK 依 env，預設持鎖），等它寫出 record.pid 與 record.status.json。"""
    p = subprocess.Popen(["bash", str(FAKE_RECORDER)], env=sb.env(**env), stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    tc.addCleanup(lambda: (p.poll() is None and p.kill(), p.wait()))
    deadline = time.monotonic() + 15
    while not ((sb.home / "record.pid").exists() and (sb.home / "record.status.json").exists()):
        if time.monotonic() > deadline:
            raise AssertionError("fake_recorder.sh 沒有寫出 record.pid／record.status.json")
        time.sleep(0.05)
    return p


def kill_lock_holders(sb):
    """收掉 fake_open.sh（FAKE_OPEN_LOCK=1）分出的持鎖子程序。"""
    p = Path(str(sb.calls) + ".lockholders")
    if not p.exists():
        return
    for line in p.read_text().split():
        try:
            os.kill(int(line), signal.SIGKILL)
        except (OSError, ValueError):
            pass


def file_state(path):
    p = Path(path)
    if not p.exists():
        return None
    return (p.stat().st_mtime_ns, p.read_bytes())


def alive(p, wait=0.0):
    """Popen 是否還在跑（等 wait 秒內是否結束）。"""
    if wait > 0:
        try:
            p.wait(timeout=wait)
        except subprocess.TimeoutExpired:
            pass
    return p.poll() is None


def cmd_stop_limit_python(src):
    """record.sh 的 cmd_stop 內唯一的 limit="$(python3 … <<'PY' 區塊的 Python 原文（spec §4.27.5）。"""
    m = re.search(r"(?ms)^cmd_stop\(\)\s*\{\n(.*?)^\}\n", src)
    if not m:
        return None, None
    body = m.group(1)
    blocks = re.findall(r"limit=\"\$\(python3[^\n]*<<'PY'[^\n]*\n(.*?)\nPY\n", body, re.S)
    return body, blocks


class TestR3Lock(unittest.TestCase):
    # spec §4.26.3：record.lock 被別的程序持有 → 回 2、不啟動 app、狀態檔不動
    def test_record_refused_when_locked(self):
        sb = Sandbox(self)
        prev = write_status(sb, 4242, phase="done", run_id="previous-run")
        before = file_state(sb.home / "record.status.json")
        hold_lock(self, sb.home / "record.lock")
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 2, f"錄製中再開錄應回 2\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn(REFUSED_RECORDING, r.stderr)
        self.assertEqual(sb.read_calls(), [], "已有錄製在跑時不得啟動（替身）app")
        self.assertEqual(file_state(sb.home / "record.status.json"), before, "record.status.json 的內容與 mtime 不得改變")
        self.assertEqual(prev["runId"], json.loads((sb.home / "record.status.json").read_text())["runId"])

    # spec §4.26.4：record.lock 被持有時 preflight 回 2、stderr 含「錄製中」、不啟動 app、狀態檔不變（D14b-A）
    def test_preflight_refused_when_recording(self):
        sb = Sandbox(self)
        write_status(sb, 4242, phase="recording", run_id="other-run")
        before = file_state(sb.home / "record.status.json")
        hold_lock(self, sb.home / "record.lock")
        r = sb.meeting("record", "preflight", "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 2, f"錄製中跑 preflight 應回 2\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertIn(REFUSED_PREFLIGHT, r.stderr)
        self.assertEqual(sb.read_calls(), [], "錄製中不得啟動（替身）app 跑 13 項檢查")
        self.assertEqual(file_state(sb.home / "record.status.json"), before)

    # spec §4.26.5、§3.15：試鎖會建立 0600 的 record.lock、拿到立刻放；別人只持有 0.2 秒時 1 秒內重試拿得到
    def test_try_lock_releases(self):
        sb = Sandbox(self)
        lock = sb.home / "record.lock"
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 0, f"沒人持鎖時應照常開錄\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue(lock.is_file(), "record.sh 開錄前應試鎖 <home>/record.lock（O_CREAT）")
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600, "record.lock 權限應為 0600")
        self.assertTrue(try_lock_nb(lock), "record.sh 結束後 record.lock 應已放掉（另一個程序能馬上 LOCK_NB 拿到）")

        sb2 = Sandbox(self)
        holder = hold_lock(self, sb2.home / "record.lock", seconds=0.2)
        t0 = time.monotonic()
        r2 = sb2.meeting("record", sb2.root, "--window", "1", timeout=60)
        self.assertEqual(r2.returncode, 0,
                         f"別人只持有 0.2 秒時，試鎖應在 1 秒的重試內拿到、照常開錄\nstdout:{r2.stdout}\nstderr:{r2.stderr}")
        self.assertEqual(len([c for c in sb2.read_calls() if "start" in c]), 1, "應啟動一次（替身）app 的 start")
        holder.wait(timeout=10)
        self.assertLess(time.monotonic() - t0, 60)

    # spec §4.26.7（§7 疑慮 43）：兩個 record.sh 同時開錄，不得兩個都回 0；落敗者回 2 或 4
    def test_concurrent_record_only_one_wins(self):
        sb = Sandbox(self)
        self.addCleanup(kill_lock_holders, sb)
        env = sb.env(FAKE_OPEN_LOCK="1")
        root2 = sb.base / "根2"  # 兩個根目錄：場次路徑不同，勝負只由錄製實例的鎖決定（不是撞到同一個場次目錄）
        root2.mkdir()
        procs = [subprocess.Popen(["bash", str(MEETING_SH), "record", str(root), "--window", "1"], cwd=str(sb.cwd),
                                  env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True) for root in (sb.root, root2)]
        outs = [p.communicate(timeout=120) for p in procs]
        codes = sorted(p.returncode for p in procs)
        detail = "\n".join(f"rc={p.returncode} stdout:{o} stderr:{e}" for p, (o, e) in zip(procs, outs))
        self.assertEqual(codes[0], 0, f"應有一個開錄成功\n{detail}")
        self.assertIn(codes[1], (2, 4), f"另一個應回 2（已有錄製在跑）或 4（等不到本次狀態）\n{detail}")
        st = json.loads((sb.home / "record.status.json").read_text(encoding="utf-8"))
        starts = [c for c in sb.read_calls() if "start" in c]
        run_ids = [c[c.index("--run-id") + 1] for c in starts if "--run-id" in c]
        self.assertIn(st.get("runId"), run_ids, "狀態檔應屬於其中一個開錄")
        self.assertEqual(st.get("phase"), "recording")

    # spec §4.27.2：record.pid 指向無關的 sleep 程序（程序名不是 MeetingRecorder／MH_RECORDER_COMM）→ 回 3、不送訊號
    def test_stop_refuses_foreign_pid(self):
        sb = Sandbox(self)
        sl = sleeper(self)
        (sb.home / "record.pid").write_text(f"{sl}\n")
        write_status(sb, sl)
        hold_lock(self, sb.home / "record.lock")
        r = run_stop(self, sb)
        self.assertTrue(pid_alive(sl, wait=1.0), "stop 不得對無關程序送訊號（sleep 程序應仍活著）")
        self.assertEqual(r.returncode, 3, f"程序名不符時 stop 應回 3\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue(r.stderr.strip(), "stderr 應說明是哪一項不成立")

    # spec §4.27.2：record.pid 的 pid 已死 → 回 3，並刪掉過時的 record.pid
    def test_stop_cleans_dead_pid(self):
        sb = Sandbox(self)
        pid = dead_pid()
        (sb.home / "record.pid").write_text(f"{pid}\n")
        write_status(sb, pid)
        hold_lock(self, sb.home / "record.lock")
        r = run_stop(self, sb)
        self.assertEqual(r.returncode, 3, f"pid 已死時 stop 應回 3\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue(r.stderr.strip(), "stderr 應說明是哪一項不成立")
        self.assertFalse((sb.home / "record.pid").exists(), "pid 已死時應刪掉過時的 record.pid")

    # spec §4.27.2：record.lock 沒被持有 → 回 3、不送訊號（替身以 FAKE_LOCK=0 不持鎖；pid、狀態檔、程序名都相符）
    def test_stop_refuses_without_lock(self):
        sb = Sandbox(self)
        p = start_fake(self, sb, FAKE_LOCK="0")
        r = run_stop(self, sb)
        self.assertEqual(r.returncode, 3, f"沒有人持有 record.lock 時 stop 應回 3\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue(r.stderr.strip(), "stderr 應說明是哪一項不成立")
        self.assertTrue(alive(p, wait=1.0), "不得送 SIGTERM（替身應仍在錄）")
        st = json.loads((sb.home / "record.status.json").read_text(encoding="utf-8"))
        self.assertEqual(st.get("phase"), "recording")

    # spec §4.27.2、§3.19、§7 疑慮 59：MH_RECORDER_COMM 只在 MH_RECORD_OPEN 也有設時生效
    def test_comm_override_needs_record_open(self):
        sb = Sandbox(self)
        sl = sleeper(self)
        (sb.home / "record.pid").write_text(f"{sl}\n")
        write_status(sb, sl)
        hold_lock(self, sb.home / "record.lock")
        env = sb.env(MH_RECORDER_COMM="sleep")
        env.pop("MH_RECORD_OPEN", None)
        r = run_stop(self, sb, env=env)
        self.assertTrue(pid_alive(sl, wait=1.0), "沒有 MH_RECORD_OPEN 時不得對 sleep 送訊號")
        self.assertEqual(r.returncode, 3,
                         f"沒有 MH_RECORD_OPEN 時 MH_RECORDER_COMM 不得生效，對 sleep 應回 3\nstdout:{r.stdout}\nstderr:{r.stderr}")
        # 對照：兩個都設時旁路生效，sleep 會收到 SIGTERM
        r2 = run_stop(self, sb, MH_RECORDER_COMM="sleep")
        self.assertFalse(pid_alive(sl, wait=5.0),
                         f"MH_RECORD_OPEN 與 MH_RECORDER_COMM=sleep 都設時應送 SIGTERM\nstdout:{r2.stdout}\nstderr:{r2.stderr}")

    # spec §4.27.3：phase 為 finalizing 時 stop 不得再送 SIGTERM，照 R2 方式等結果
    def test_stop_does_not_resignal_while_finalizing(self):
        sb = Sandbox(self)
        p = start_fake(self, sb, FAKE_PHASE="finalizing")
        st = json.loads((sb.home / "record.status.json").read_text(encoding="utf-8"))

        def finish_later():
            time.sleep(1.5)
            done = dict(st, phase="done", code=0, message="已完成（範例訊息）",
                        updatedAt=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
            tmp = sb.home / ".record.status.test.tmp"
            tmp.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, sb.home / "record.status.json")

        th = threading.Thread(target=finish_later)
        th.start()
        r = run_stop(self, sb)
        th.join()
        self.assertEqual(r.returncode, 0, f"收尾完成後 stop 應回 0\nstdout:{r.stdout}\nstderr:{r.stderr}")
        self.assertTrue(alive(p), "收尾中不得再送 SIGTERM（替身收到 SIGTERM 會結束）")

    # spec §4.27.5：等待上限＝3 × max(0, now − startedAt) ＋ 630；讀不到 startedAt 時 7200
    def test_stop_wait_limit_covers_finalize_deadline(self):
        src = RECORD_SH.read_text(encoding="utf-8")
        body, blocks = cmd_stop_limit_python(src)
        self.assertIsNotNone(body, "bin/record.sh 找不到 cmd_stop()")
        self.assertFalse("2 * max(0" in body, "cmd_stop 不得再用 2 × 已錄秒數（2 * max(0）")
        self.assertEqual(len(blocks), 1, "cmd_stop 內應恰有一個 limit=\"$(python3 … <<'PY' 區塊")
        code = blocks[0]
        d = tmpdir(self)

        def limit_for(content):
            p = d / f"status-{abs(hash(content))}.json"
            p.write_text(content, encoding="utf-8")
            r = subprocess.run([sys.executable, "-c", code, str(p)], capture_output=True, text=True, timeout=30)
            return r.stdout.strip()

        def started(ago):
            t = time.time() - ago
            return json.dumps({"startedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))})

        for ago, lo, hi in ((100, 930, 932), (3600, 11430, 11432)):
            with self.subTest(ago=ago):
                out = limit_for(started(ago))
                self.assertRegex(out, r"^\d+$", f"上限應印整數秒：{out!r}")
                self.assertTrue(lo <= int(out) <= hi, f"startedAt＝now − {ago} 秒時上限應介於 {lo} 與 {hi}：{out}")
        self.assertEqual(limit_for("{壞檔"), "7200", "讀不到 startedAt 時應沿用 7200 秒")

    # spec §4.27.6、§6 第 136 條：替身預設持有 record.lock，被 SIGKILL 後 2 秒內釋放；FAKE_LOCK=0 不持有
    def test_fake_recorder_holds_lock(self):
        sb = Sandbox(self)
        p = start_fake(self, sb)
        self.assertFalse(try_lock_nb(sb.home / "record.lock"), "FAKE_LOCK 未設時替身存活期間 record.lock 應被持有")
        p.send_signal(signal.SIGKILL)
        p.wait(timeout=10)
        deadline = time.monotonic() + 2.0
        freed = False
        while time.monotonic() < deadline:
            if try_lock_nb(sb.home / "record.lock"):
                freed = True
                break
            time.sleep(0.05)
        self.assertTrue(freed, "替身被 SIGKILL 後 2 秒內 record.lock 應被釋放")

        sb2 = Sandbox(self)
        start_fake(self, sb2, FAKE_LOCK="0")
        self.assertTrue(try_lock_nb(sb2.home / "record.lock"), "FAKE_LOCK=0 時替身不得持有 record.lock")

    # spec §4.43.2：write_defaults 取 record.defaults.lock、讀後合併（不認得的鍵保留、7 鍵為新值）
    def test_write_defaults_merges(self):
        sb = Sandbox(self)
        old = {"root": "/不存在的舊根", "type": "seminar", "attendees": ["舊出席者"], "harness": "/舊/harness",
               "python3": "/舊/python3", "ffmpeg": "/舊/ffmpeg", "minFreeBytes": 1,
               "syncCompensation": "reported", "x": {"保留": True}}
        (sb.home / "record.defaults.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 0, f"開錄應成功\nstdout:{r.stdout}\nstderr:{r.stderr}")
        d = json.loads((sb.home / "record.defaults.json").read_text(encoding="utf-8"))
        self.assertEqual(d.get("syncCompensation"), "reported", "write_defaults 不得刪掉 syncCompensation")
        self.assertEqual(d.get("x"), {"保留": True}, "write_defaults 不得刪掉不認得的鍵")
        self.assertTrue(DEFAULT_KEYS <= set(d), f"7 鍵應都在：{sorted(d)}")
        self.assertEqual(Path(d["root"]).resolve(), sb.root.resolve(), "root 應為本次的新值")
        self.assertNotEqual(d["minFreeBytes"], 1, "minFreeBytes 應為本次的新值")
        self.assertNotEqual(d["harness"], "/舊/harness", "harness 應為本次的新值")
        self.assertTrue((sb.home / "record.defaults.lock").exists(), "write_defaults 應取 <home>/record.defaults.lock")

    # spec §4.43.2：record.defaults.json 不是 JSON 物件時不寫、stderr 報錯、開錄照常
    def test_write_defaults_refuses_broken_file(self):
        sb = Sandbox(self)
        p = sb.home / "record.defaults.json"
        for content in ("[1, 2]", "{壞檔"):
            with self.subTest(content=content):
                sb.reset_calls()
                p.write_text(content, encoding="utf-8")
                before = p.read_bytes()
                r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
                self.assertEqual(r.returncode, 0, f"defaults 只是記憶，壞檔不擋開錄\nstdout:{r.stdout}\nstderr:{r.stderr}")
                self.assertEqual(p.read_bytes(), before, "record.defaults.json 不是 JSON 物件時不得覆寫")
                self.assertIn("defaults", r.stderr.lower(), "stderr 應報 record.defaults.json 寫不進去")
                (sb.home / "record.pid").unlink(missing_ok=True)

    # spec §4.43.3、ADR adr-r3-defaults-writers：另一寫者持鎖 2 秒（持鎖期間讀、睡、寫回）時，合併寫入要等鎖放開
    def test_defaults_lock_serializes(self):
        sb = Sandbox(self)
        w = subprocess.Popen([sys.executable, "-c", STALE_WRITER, str(sb.home), "2"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
        self.addCleanup(lambda: (w.poll() is None and w.kill(), w.wait()))
        self.assertEqual(w.stdout.readline().strip(), "ready")
        r = sb.meeting("record", sb.root, "--window", "1", timeout=60)
        self.assertEqual(r.returncode, 0, f"開錄應成功\nstdout:{r.stdout}\nstderr:{r.stderr}")
        w.wait(timeout=30)
        d = json.loads((sb.home / "record.defaults.json").read_text(encoding="utf-8"))
        self.assertEqual(d.get("x"), 1, "另一寫者的鍵應保留")
        self.assertTrue(DEFAULT_KEYS <= set(d), f"record.sh 的 7 鍵應在另一寫者放鎖後合併寫入：{sorted(d)}")


if __name__ == "__main__":
    unittest.main()

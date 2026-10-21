"""tests/record 共用的執行輔助（不是測試模組）。

所有測試都在 TMPDIR 的暫存目錄跑，錄製器一律接 fakes/fake_open.sh（MH_RECORD_OPEN），
不得真的開 app、不得錄螢幕或麥克風。
"""
import hashlib
import json
import os
import pty
import select
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from tests.record.surface import REPO

BIN = REPO / "bin"
MEETING_SH = BIN / "meeting.sh"
RECORD_SH = BIN / "record.sh"
FAKES = Path(__file__).resolve().parent / "fakes"
FAKE_OPEN = FAKES / "fake_open.sh"
FAKE_RECORDER = FAKES / "fake_recorder.sh"
SLOW_FFMPEG = FAKES / "slow_ffmpeg.sh"
FAILING_FFMPEG = FAKES / "failing_ffmpeg.sh"

UNKNOWN_OPTION = "未知的選項"
DEFAULT_TIMEOUT = 90


def tmpdir(tc):
    """建立暫存目錄，測試結束自動清掉。"""
    d = Path(tempfile.mkdtemp(prefix="mh-record-test-"))
    tc.addCleanup(shutil.rmtree, d, True)
    return d


def make_app_stub(path):
    """假的 MeetingRecorder.app（只有目錄結構，不會被執行）。"""
    p = Path(path)
    (p / "Contents" / "MacOS").mkdir(parents=True, exist_ok=True)
    exe = p / "Contents" / "MacOS" / "MeetingRecorder"
    exe.write_text("#!/bin/sh\necho 'fake app must not be executed directly' >&2\nexit 99\n")
    exe.chmod(0o755)
    (p / "Contents" / "Info.plist").write_text("<plist/>\n")
    return p


class Sandbox:
    """一次測試的執行環境：home、calls 紀錄、假 app、乾淨的工作目錄。"""

    def __init__(self, tc, scenario="recording", windows=None, app=True, cwd_record_dir=False):
        self.base = tmpdir(tc)
        self.home = self.base / "home"
        self.home.mkdir()
        self.cwd = self.base / "cwd"
        self.cwd.mkdir()
        if cwd_record_dir:
            (self.cwd / "record").mkdir()
        self.calls = self.base / "fake_open.calls"
        self.app = self.base / "apps" / "MeetingRecorder.app"
        if app:
            make_app_stub(self.app)
        self.root = self.base / "根"
        self.root.mkdir()
        self.scenario = scenario
        self.windows_file = None
        if windows is not None:
            self.set_windows(windows)
        self.extra_env = {}

    def set_windows(self, rows):
        self.windows_file = self.base / "fake_windows.json"
        self.windows_file.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    def env(self, **over):
        env = dict(os.environ)
        env.update({
            "MH_RECORD_HOME": str(self.home),
            "MH_RECORD_OPEN": str(FAKE_OPEN),
            "MH_RECORDER_APP": str(self.app),
            "FAKE_OPEN_CALLS": str(self.calls),
            "FAKE_SCENARIO": self.scenario,
            "LC_ALL": env.get("LC_ALL", "en_US.UTF-8"),
            "MH_RECORDER_COMM": "bash",
        })
        if self.windows_file is not None:
            env["FAKE_WINDOWS_JSON"] = str(self.windows_file)
        env.update(self.extra_env)
        env.update({k: str(v) for k, v in over.items()})
        return env

    def run(self, argv, stdin=subprocess.DEVNULL, timeout=DEFAULT_TIMEOUT, cwd=None, **env_over):
        return subprocess.run([str(a) for a in argv], cwd=str(cwd or self.cwd), env=self.env(**env_over),
                              stdin=stdin, capture_output=True, text=True, timeout=timeout)

    def meeting(self, *args, **kw):
        return self.run(["bash", str(MEETING_SH), *args], **kw)

    def read_calls(self):
        return read_calls(self.calls)

    def reset_calls(self):
        if self.calls.exists():
            self.calls.unlink()


def read_calls(path):
    """fake_open.sh 的紀錄：每次呼叫一筆，格式為 <參數個數>\\0<參數1>\\0…（可還原參數邊界）。"""
    p = Path(path)
    if not p.exists():
        return []
    parts = p.read_bytes().split(b"\0")
    calls, i = [], 0
    while i < len(parts) and parts[i] != b"":
        n = int(parts[i])
        calls.append([x.decode("utf-8") for x in parts[i + 1:i + 1 + n]])
        i += 1 + n
    return calls


def app_args(call):
    """open 參數中 --args 之後的部分（app 實際收到的參數）；沒有 --args 時回整串。"""
    return call[call.index("--args") + 1:] if "--args" in call else call


def is_subsequence(needle, hay):
    it = iter(hay)
    return all(any(x == y for y in it) for x in needle)


def flag_value(call, flag):
    """flag 緊接的值；flag 不在或後面沒有值時回 None。"""
    if flag not in call:
        return None
    i = call.index(flag)
    return call[i + 1] if i + 1 < len(call) else None


def run_pty(argv, env, cwd, responder, timeout=DEFAULT_TIMEOUT, idle=0.4):
    """以 pty 當 stdin／stdout／stderr 執行（模擬終端機）。

    responder(full_output, new_output) 在輸出停頓 idle 秒時被呼叫，回傳要送出的字串、
    None（不送）或 EOF（送 Ctrl-D）。回傳 (returncode, 全部輸出)。
    """
    master, slave = pty.openpty()
    p = subprocess.Popen([str(a) for a in argv], cwd=str(cwd), env=env, stdin=slave, stdout=slave,
                         stderr=slave, close_fds=True, start_new_session=True)
    os.close(slave)
    out = b""
    seen = 0
    eof = False
    last = time.monotonic()
    deadline = time.monotonic() + timeout
    try:
        while True:
            if time.monotonic() > deadline:
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait()
                raise AssertionError(f"pty 執行逾時（{timeout} 秒）；輸出：\n{out.decode('utf-8', 'replace')}")
            r = [] if eof else select.select([master], [], [], 0.1)[0]
            if r:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    chunk = b""
                if chunk:
                    out += chunk
                    last = time.monotonic()
                    continue
                eof = True
            if p.poll() is not None:
                break
            if eof:
                time.sleep(0.05)
                continue
            if time.monotonic() - last >= idle and len(out) > seen:
                text = out.decode("utf-8", "replace")
                ans = responder(text, out[seen:].decode("utf-8", "replace"))
                seen = len(out)
                last = time.monotonic()
                try:
                    if ans is EOF:
                        os.write(master, b"\x04")
                    elif ans is not None:
                        os.write(master, ans.encode("utf-8"))
                except OSError:
                    pass
        # 子程序結束後把剩下的輸出讀完
        while not eof:
            r = select.select([master], [], [], 0.2)[0]
            if not r:
                break
            try:
                chunk = os.read(master, 4096)
            except OSError:
                break
            if not chunk:
                break
            out += chunk
    finally:
        os.close(master)
    return p.returncode, out.decode("utf-8", "replace")


EOF = object()


def snapshot(root):
    """目錄下每個檔的 (mtime_ns, sha256)。"""
    snap = {}
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            snap[str(p.relative_to(root))] = (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
    return snap


def dead_pid():
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def scaffold_meeting_json_keys():
    """以 ast 解析 bin/_scaffold.py 寫 meeting.json 的 dict（含 expectedSpeakers 那個），不另抄清單。"""
    import ast
    tree = ast.parse((BIN / "_scaffold.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
            if "expectedSpeakers" in keys:
                return set(keys)
    raise AssertionError("bin/_scaffold.py 找不到含 expectedSpeakers 的 dict")


def scaffold_ts_re():
    """bin/_scaffold.py 的 TS_RE（以 ast 取 pattern，避免 import 時跑主程式）。"""
    import ast
    import re
    tree = ast.parse((BIN / "_scaffold.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "TS_RE" for t in node.targets):
            return re.compile(node.value.args[0].value)
    raise AssertionError("bin/_scaffold.py 找不到 TS_RE")


class PromptResponder:
    """回答互動問答（_record_prompt.py 或 record.sh 經 pty）。

    問答的順序 spec 沒有規定，所以依內容判斷：
    - 輸出出現視窗選單（任一 label）或視窗提示被重問 → 依序送 window_answers（用完送 EOF）；
    - 其他提示第一次送 Enter（接受預設）；同一提示被重問時依關鍵字送值（根目錄、型態、出席者、場次名）。
    """

    def __init__(self, labels, window_answers, root=None):
        self.labels = list(labels)
        self.window_answers = list(window_answers)
        self.root = root
        self.last_prompt = None
        self.last_was_window = False
        self.window_prompts = []

    def fallback(self, prompt):
        if "根" in prompt and self.root:
            return f"{self.root}\n"
        if "型態" in prompt:
            return "internal\n"
        if "出席" in prompt:
            return "範例出席者\n"
        return "範例場次\n"

    def __call__(self, full, new):
        lines = [l.strip() for l in new.replace("\r", "").split("\n") if l.strip()]
        if not lines:
            return None
        last = lines[-1]
        is_menu = any(lab in new for lab in self.labels)
        window_reask = self.last_was_window and last == self.last_prompt
        if is_menu or window_reask:
            self.last_was_window = True
            self.last_prompt = last
            self.window_prompts.append(new)
            if not self.window_answers:
                return EOF
            return self.window_answers.pop(0)
        self.last_was_window = False
        ans = self.fallback(last) if last == self.last_prompt else "\n"
        self.last_prompt = last
        return ans


def drive_pipes(argv, env, cwd, responder, timeout=DEFAULT_TIMEOUT, idle=0.4):
    """以管線執行（stdin 不是 tty），提示在 stderr；停頓時交給 responder 回答。

    responder 回 EOF 時關閉 stdin。回傳 (returncode, stdout, stderr)。
    """
    p = subprocess.Popen([str(a) for a in argv], cwd=str(cwd), env=env, stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = b"", b""
    seen = 0
    last = time.monotonic()
    deadline = time.monotonic() + timeout
    fds = {p.stdout.fileno(): "out", p.stderr.fileno(): "err"}
    open_fds = set(fds)
    while open_fds:
        if time.monotonic() > deadline:
            p.kill()
            p.wait()
            raise AssertionError(f"執行逾時（{timeout} 秒）；stderr：\n{err.decode('utf-8', 'replace')}")
        r, _, _ = select.select(list(open_fds), [], [], 0.1)
        for fd in r:
            chunk = os.read(fd, 4096)
            if not chunk:
                open_fds.discard(fd)
                continue
            last = time.monotonic()
            if fds[fd] == "out":
                out += chunk
            else:
                err += chunk
        if not r and p.poll() is None and time.monotonic() - last >= idle and len(err) > seen:
            ans = responder(err.decode("utf-8", "replace"), err[seen:].decode("utf-8", "replace"))
            seen = len(err)
            last = time.monotonic()
            if ans is EOF:
                if not p.stdin.closed:
                    p.stdin.close()
            elif ans is not None and not p.stdin.closed:
                try:
                    p.stdin.write(ans.encode("utf-8"))
                    p.stdin.flush()
                except BrokenPipeError:
                    pass
    if not p.stdin.closed:
        p.stdin.close()
    p.stdout.close()
    p.stderr.close()
    p.wait(timeout=10)
    return p.returncode, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

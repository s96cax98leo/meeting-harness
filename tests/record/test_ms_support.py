"""meeting-speed 測試共用的輔助（本檔沒有測試；檔名以 test_ms_ 開頭只為落在 red-py 的檔案歸屬內）。

素材一律只在 TMPDIR；轉錄、分離、ffmpeg 一律可換成 fakes/ 的替身；範例場次名「[Stand-up] 範例專案」。
新模組（bin/lib/_asr_worker.py、tools/bench/replay.py）不存在時，測試以 assert 判 FAIL（不得 import 失敗、不得跳過）。
"""
import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tests.record import _media as m
from tests.record._helpers import BIN, FAKES, MEETING_SH, RECORD_SH, tmpdir
from tests.record.surface import REPO

PY = sys.executable
FINALIZE_PY = BIN / "_record_finalize.py"
RECORD_LIB_PY = BIN / "lib" / "_record_lib.py"
ASR_WORKER_PY = BIN / "lib" / "_asr_worker.py"
REPLAY_PY = REPO / "tools" / "bench" / "replay.py"
TRANSCRIBE_SH = BIN / "transcribe.sh"
DIARIZE_SH = BIN / "diarize.sh"
VOICEPRINT_PY = BIN / "_voiceprint.py"
MERGE_PY = BIN / "_merge_speakers.py"
RENDER_PY = BIN / "_render.py"
PYANNOTE_PY = BIN / "_diarize_pyannote.py"

SLOW_FFMPEG = FAKES / "ms_slow_ffmpeg.sh"
COUNT_FFPROBE = FAKES / "ms_count_ffprobe.sh"
FAKE_VENV = FAKES / "ms_diarize_venv"
FAKE_FFMPEG_BIN = FAKES / "ms_bin"
EMBED_SPEAKER = FAKES / "ms_embed_speaker.py"
ASR_EXC0_DIR = FAKES / "asr_exc0"
ASR_SLOW_DIR = FAKES / "ms_asr"
PYMOD_DIR = FAKES / "pymod"
VECTORS = Path(__file__).resolve().parent / "vectors"

REAL_FFMPEG = shutil.which("ffmpeg") or "ffmpeg"
REAL_FFPROBE = shutil.which("ffprobe") or "ffprobe"
SESSION = "[Stand-up] 範例專案"
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".mov", ".mp4", ".m4v"}


def py_path_env():
    """子程序的 PATH：本測試用的 python 所在目錄放最前面（bash 腳本裡的 python3 指向同一支，避免 pyenv shim 卡住）。"""
    return f"{Path(PY).parent}:{os.environ.get('PATH', '')}"


def base_env(home=None, **over):
    env = dict(os.environ)
    for k in ("MH_SYNC_COMPENSATION", "MH_FINALIZE_STEP_TIMEOUT", "MH_KEEP_SEGMENTS", "MH_FFMPEG", "MH_FFPROBE",
              "MH_FINALIZE_JOBS", "MH_FINALIZE_WAIT_LOCK", "MH_ASR_SEGMENTS_JSON", "MH_PREP_RUN_ID",
              "MH_EMBEDDINGS_OUT", "MH_EMBED_SPEAKER_CMD", "MH_VAD", "MH_ASR_MODEL", "PYTHONPATH"):
        env.pop(k, None)
    env["PATH"] = py_path_env()
    env["LC_ALL"] = env.get("LC_ALL", "en_US.UTF-8")
    env["MS_REAL_FFMPEG"] = REAL_FFMPEG
    env["MS_REAL_FFPROBE"] = REAL_FFPROBE
    env["MS_REAL_PYTHON"] = PY
    if home is not None:
        env["MH_RECORD_HOME"] = str(home)
    env.update({k: str(v) for k, v in over.items()})
    return env


def run(argv, env, timeout=300, cwd=None):
    return subprocess.run([str(a) for a in argv], env=env, capture_output=True, text=True, timeout=timeout,
                          cwd=str(cwd) if cwd else None)


def out_of(r):
    return f"\nrc={r.returncode}\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"


def load_module(path, name):
    """以檔案路徑載入模組（不經 sys.path、不寫 .pyc）。"""
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    dwb = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = dwb
    return mod


def load_record_lib():
    lib = str(BIN / "lib")
    added = lib not in sys.path
    if added:
        sys.path.insert(0, lib)
    try:
        return load_module(RECORD_LIB_PY, "_record_lib_ms_under_test")
    finally:
        if added:
            sys.path.remove(lib)


def load_vector(name):
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


# ---------- 場次 ----------

def record_session(root, segments, *, canvas=None, name=SESSION, gap=0.02):
    """錄完、還沒收尾的場次（_media.make_record_session）；canvas＝(w, h) 時在 record.meta.json 寫 canvasLock。"""
    sess = m.make_record_session(root, segments, name=name, gap=gap)
    if canvas is not None:
        set_canvas_lock(sess, canvas)
    return sess


def set_canvas_lock(sess, canvas):
    p = sess / "錄音" / "tracks" / "record.meta.json"
    meta = json.loads(p.read_text(encoding="utf-8"))
    meta["canvasLock"] = {"width": int(canvas[0]), "height": int(canvas[1])}
    p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def tracks_of(sess):
    return sess / "錄音" / "tracks"


def finalize_json(sess):
    p = tracks_of(sess) / "finalize.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def audio_ready_json(sess):
    p = tracks_of(sess) / "audio-ready.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def audio_files(sess):
    rec = sess / "錄音"
    return sorted(p for p in rec.iterdir() if p.is_file() and p.suffix.lower() in AUDIO_EXTS) if rec.is_dir() else []


def wavs(sess):
    return [p for p in audio_files(sess) if p.suffix == ".wav"]


def videos(sess):
    d = sess / "影片"
    return sorted(d.glob("*.mov")) if d.is_dir() else []


def segment_files(sess):
    return sorted(tracks_of(sess).glob("seg-*.mov"))


def finalize(sess, home, timeout=300, **env):
    """以 python3 bin/_record_finalize.py <場次> 直接收尾（MH_RECORD_HOME＝home）。"""
    return run([PY, FINALIZE_PY, sess], base_env(home, **env), timeout=timeout)


def finalize_popen(sess, home, **env):
    return subprocess.Popen([PY, str(FINALIZE_PY), str(sess)], env=base_env(home, **env), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)


# ---------- ffmpeg 替身紀錄 ----------

def ffmpeg_calls(log):
    """ms_slow_ffmpeg.sh 的紀錄 → [{"t", "cls", "wav", "argv", "end", "rc"}]（依開始順序）。"""
    calls, open_ = [], {}
    p = Path(log)
    if not p.is_file():
        return calls
    for ln in p.read_text(encoding="utf-8").splitlines():
        parts = ln.split(" ", 4)
        if len(parts) >= 4 and parts[1] == "START":
            argv = parts[4].split("\x1f")[:-1] if len(parts) == 5 else []
            c = {"t": float(parts[0]), "cls": parts[2], "wav": parts[3], "argv": argv, "end": None, "rc": None}
            calls.append(c)
            open_.setdefault(parts[2], []).append(c)
        elif len(parts) >= 4 and parts[1] == "END":
            pending = [c for c in open_.get(parts[2], []) if c["end"] is None]
            if pending:
                pending[0]["end"] = float(parts[0])
                pending[0]["rc"] = int(parts[3])
    return calls


def argv_log(log):
    """ms_count_ffprobe.sh／ms_bin/ffmpeg 的紀錄 → [argv]。"""
    p = Path(log)
    if not p.is_file():
        return []
    return [ln.split("\x1f")[:-1] for ln in p.read_text(encoding="utf-8").splitlines() if ln]


# ---------- 狀態檔 ----------

def write_status(home, **fields):
    st = {"schemaVersion": 1, "runId": "6F1C0000-0000-4000-8000-00000000A001", "pid": 0, "phase": "done", "code": 0,
          "message": "", "session": "", "startedAt": "2026-10-21T09:30:00+08:00",
          "updatedAt": "2026-10-21T11:30:00+08:00", "segments": 0, "preflight": [], "warnings": []}
    st.update(fields)
    p = Path(home) / "record.status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return p


def update_status(home, **fields):
    p = Path(home) / "record.status.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    st.update(fields)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


class HeldLock:
    """在測試程序內以 flock(LOCK_EX) 持有一個鎖檔。"""

    def __init__(self, path):
        self.path = Path(path)
        self.fd = None

    def acquire(self):
        self.fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def wait_until(pred, timeout=30.0, interval=0.05):
    """輪詢到 pred() 為真；逾時回 False（不是固定等待：條件成立就立刻回）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        v = pred()
        if v:
            return v
        time.sleep(interval)
    return pred()


def kill_quietly(p):
    if p is None or p.poll() is not None:
        return
    p.kill()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        pass
    for s in (p.stdout, p.stderr):
        if s is not None:
            s.close()


# ---------- 轉錄與分離替身 ----------

def fake_diarize_env(base, **extra):
    """bin/diarize.sh 用假 venv 的環境：MH_DIARIZE_VENV＝fakes/ms_diarize_venv、FAKE_DIAR_LOG。回傳 (env 覆寫, log)。"""
    log = Path(base) / "fake_diar.log"
    env = {"MH_DIARIZE_VENV": str(FAKE_VENV), "FAKE_DIAR_LOG": str(log), "MS_REAL_PYTHON": PY}
    env.update({k: str(v) for k, v in extra.items()})
    return env, log


def diar_calls(log):
    p = Path(log)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def audio_session(root, *, name=m.SESSION_NAME, dur=4.0, mtype="internal"):
    """只有一個 wav 的場次。場次名預設「範例場次」：bin/_combine_audio.py 以 glob 找音檔，路徑含「[」會找不到
    （既有問題，不在本 epic 範圍，列衍生工作），所以走轉錄／分離的測試不用含方括號的範例名。"""
    return m.make_audio_session(root, name=name, dur=dur, mtype=mtype)


def pipeline_state(sess):
    p = sess / ".pipeline-state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


__all__ = [n for n in dir() if not n.startswith("_")] + ["tmpdir", "MEETING_SH", "RECORD_SH", "REPO", "BIN", "FAKES"]

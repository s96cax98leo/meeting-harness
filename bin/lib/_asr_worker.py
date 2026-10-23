#!/usr/bin/env python3
"""_asr_worker.py — 錄製中的增量轉錄 worker 與 stitch（meeting-speed spec §3.6、§3.9、§4.11；ADR adr-ms-incremental-asr.md）。

子指令（內部介面，不是對外 CLI）：
- run <場次>：持 錄音/tracks/asr/worker.lock（flock）；輪詢 錄音/tracks/manifest.json，只處理 finishedAt 不是 null 的段落
  （由第一段起連續的那一串），逐窗以 in-process 的 mlx_whisper.transcribe() 轉錄（模型只載一次），結果寫
  錄音/tracks/asr/w-NNNN.json（時間戳已平移到成品時間軸），狀態寫 state.json（原子寫入、定期更新心跳）。
  - 窗 k＝[cut_{k−1}, cut_k]：cut_k 取第 k 段最後 8 秒內、以整檔轉錄同一組 VAD 參數（levels_intervals）算出的
    兩個有聲區間之間最晚那個靜音區間的中點；找不到時在段尾硬切。窗不重疊、首尾相接，拼接時不去重（鐵則 1）。
  - 本場錄製中（phase＝recording／stopping）丟幀數（record.status.json 的 droppedFrames）大於 worker 起來時的值
    → paused／drops，到 phase 離開 recording／stopping 為止不開新窗；別場背景收尾（finalizing/<runId>.status.json
    的 pid 活著且持有 <runId>.lock）還在跑 → paused／otherFinalizing。
  - 本場 phase 變成 finalizing／done／failed（或狀態檔已換成別場、錄製器 pid 不在）→ 補完所有窗，最後一窗延伸到
    最後一段結尾，state.json.status＝complete 後結束。
  - 結束碼：0 完成（或另一個 worker 正持有 worker.lock、config.json 關掉增量轉錄時直接結束）；2 參數錯或轉錄失敗
    （state.json.status＝failed）。
- stitch <場次> <out.json>：worker 還活著（持有 worker.lock）且 60 秒內有心跳時先等它結束；再檢查
  status＝complete、各窗涵蓋的段落（檔名＋大小）與 audio-ready.json（沒有時 finalize.json.inputs）相同、
  params 與這次 transcribe.sh 會用的相同、補償模式為 off——全部成立時把各窗結果拼成與 mlx_whisper
  --output-format json 同 schema 的 JSON 寫到 <out.json>，回 0；任一不成立回 3、stderr 印一行原因、不寫檔；參數錯 2。

段落音訊用 bin/_record_finalize.py 的 analyze()／segment_audio_pcm()（與音訊先出同一段程式）；段落在成品時間軸上的
起點＝前面可讀段落長度的和（與 audio-ready.json 同一個算法）。讀不到的段落不進任何窗（收尾也會略過它）。
環境變數：與 transcribe.sh 相同的 MH_ASR_MODEL、MH_LANG（預設 zh）、MH_TRANSCRIBE_HINT、MH_VAD、MH_VAD_THRESHOLD_DB、
MH_VAD_PAD、MH_VAD_MERGE_GAP；MH_RECORD_HOME（狀態檔所在）；MH_SYNC_COMPENSATION（同 _record_finalize）。
"""
import argparse
import datetime
import fcntl
import glob
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import threading
import time
import wave

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.dirname(LIB_DIR)
HARNESS = os.path.dirname(BIN_DIR)
if LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
import _record_lib as rl  # noqa: E402
from _record_lib import load_json, record_home, write_json_atomic  # noqa: E402

SCHEMA = 1
CUT_SEARCH_SECONDS = 8.0     # 切點只在每段最後這麼多秒內找（spec §4.11.3）
MIN_WINDOW_SECONDS = 0.05    # 比這短的窗不開，併進下一窗
POLL_SECONDS = 0.5
HEARTBEAT_SECONDS = 10.0
HEARTBEAT_STALE = 60.0       # stitch：超過這麼久沒心跳就當 worker 不在了（spec §4.11.7）
DURATION_TOL = 0.5           # stitch：窗的總長與 audio-ready.json 的總長差在這麼多秒內
PCM_RATE = 48000
STOPPED_PHASES = ("finalizing", "done", "failed", "preflight_failed")
LIVE_PHASES = ("recording", "stopping")
DEFAULT_MODELS = {"zh": "Kenji8000/Breeze-ASR-25-mlx", "default": "mlx-community/whisper-large-v3-mlx"}
DEFAULT_HINT = "以下為一場繁體中文的技術演講/會議，內容含中英文混雜的專有名詞、產品名與技術術語。"
AUDIO_EXTS = (".m4a", ".mp3", ".wav", ".mov", ".mp4", ".m4v")


def log(msg):
    sys.stdout.write(f"[asr-worker] {msg}\n")
    sys.stdout.flush()


def now_iso():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if math.isfinite(v) else None


_FIN = []


def finalize_mod():
    """bin/_record_finalize.py（analyze、segment_audio_pcm、ffmpeg、sync_mode）；第一次用到才載入。"""
    if not _FIN:
        path = os.path.join(BIN_DIR, "_record_finalize.py")
        spec = importlib.util.spec_from_file_location("_record_finalize_for_asr_worker", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _FIN.append(mod)
    return _FIN[0]


# ── 這次 transcribe.sh 會用的參數（spec §3.6 params；§4.11.7 的比對基準） ─────────────

def _default_hint():
    """transcribe.sh 的 HINT 預設值（直接讀腳本，兩邊不會各寫一份而漂移）；讀不到時用同一句常數。"""
    try:
        with open(os.path.join(BIN_DIR, "transcribe.sh"), encoding="utf-8") as f:
            m = re.search(r'^HINT="\$\{MH_TRANSCRIBE_HINT:-(.*)\}"\s*$', f.read(), re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return DEFAULT_HINT


def _cfg_model(key):
    cfg = load_json(os.path.join(HARNESS, "config.json"), {})
    try:
        v = cfg["transcribe"]["models"].get(key)
    except (KeyError, TypeError, AttributeError):
        v = None
    return v if isinstance(v, str) and v else DEFAULT_MODELS[key]


def transcribe_params():
    """與 transcribe.sh 同一套規則：MH_ASR_MODEL 優先；語言 MH_LANG（meeting.sh 預設 zh）；zh 用 config 的 zh 模型、
    其他用 default；提示詞 MH_TRANSCRIBE_HINT（空值＝預設）；VAD 門檻／補／合併間隔同 _record_lib；MH_VAD=0 不套用。"""
    lang = os.environ.get("MH_LANG") or "zh"
    model = os.environ.get("MH_ASR_MODEL") or _cfg_model("zh" if lang == "zh" else "default")
    return {
        "model": model,
        "language": lang,
        "initialPrompt": os.environ.get("MH_TRANSCRIBE_HINT") or _default_hint(),
        "vadThresholdDb": rl._env_float("MH_VAD_THRESHOLD_DB", rl.VAD_THRESHOLD_DB),
        "vadPad": rl._env_float("MH_VAD_PAD", rl.VAD_PAD),
        "vadMergeGap": rl._env_float("MH_VAD_MERGE_GAP", rl.VAD_MERGE_GAP),
        "vadApplied": os.environ.get("MH_VAD", "1") != "0",
        "compensation": finalize_mod().sync_mode(),
    }


def incremental_enabled():
    cfg = load_json(os.path.join(HARNESS, "config.json"), {})
    try:
        return cfg["transcribe"]["incremental"].get("enabled") is not False
    except (KeyError, TypeError, AttributeError):
        return True


# ── 場次與錄製狀態 ─────────────────────────────────────────────────────────────

def same_path(a, b):
    if not isinstance(a, str) or not a:
        return False
    try:
        return os.path.realpath(a) == os.path.realpath(b)
    except (OSError, ValueError):
        return False


def pid_alive(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def lock_held(path):
    """別的程序是否持有 path 上的 flock（檔案不存在＝沒人持有；不建檔）。"""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
    return False


def own_status(sess):
    """record.status.json 屬於本場時回它；已換成別場、檔案不在或壞檔時回 None。"""
    st = load_json(os.path.join(record_home(), "record.status.json"), None)
    if isinstance(st, dict) and same_path(st.get("session"), sess):
        return st
    return None


def recording_phase(sess):
    """本場的 phase；狀態檔已不屬本場、或錄製器 pid 不在了（非結束態）時回 "gone"（視同已停止）。"""
    st = own_status(sess)
    if st is None:
        return "gone", st
    ph = st.get("phase")
    if ph not in STOPPED_PHASES and not pid_alive(st.get("pid")):
        return "gone", st
    return ph, st


def other_finalizing(sess):
    """別場背景收尾還在跑：finalizing/<runId>.status.json 的 pid 活著且 <runId>.lock 被持有。"""
    d = os.path.join(record_home(), "finalizing")
    for p in sorted(glob.glob(os.path.join(glob.escape(d), "*.status.json"))):
        st = load_json(p, None)
        if not isinstance(st, dict) or same_path(st.get("session"), sess):
            continue
        lock = p[: -len(".status.json")] + ".lock"
        if pid_alive(st.get("pid")) and lock_held(lock):
            return True
    return False


def finished_segments(tracks):
    """manifest.json 中由第一段起、finishedAt 不是 null 且檔案在的連續段落；回 (段落清單, levels dict)。"""
    man = load_json(os.path.join(tracks, "manifest.json"), None)
    if not isinstance(man, dict):
        return [], {}
    out = []
    for s in man.get("segments") or []:
        if not isinstance(s, dict):
            break
        f, a, b = s.get("file"), num(s.get("startedAt")), num(s.get("finishedAt"))
        if not isinstance(f, str) or a is None or b is None or not os.path.isfile(os.path.join(tracks, f)):
            break
        out.append({"file": f, "startedAt": a, "finishedAt": b})
    lv = man.get("levels") if isinstance(man.get("levels"), dict) else {}
    return out, lv


def combined_levels(lv):
    sysl = lv.get("system") if isinstance(lv.get("system"), list) else []
    mic = lv.get("mic") if isinstance(lv.get("mic"), list) else []
    n = max(len(sysl), len(mic))
    return [rl._max_level(sysl[i] if i < len(sysl) else None, mic[i] if i < len(mic) else None) for i in range(n)]


def cut_point(lv, seg, params):
    """spec §4.11.3：第 k 段最後 8 秒內、兩個有聲區間之間最晚那個靜音區間的中點（錄製時鐘）；找不到回 None。
    只用這一段結尾以前的 levels（錄製中後面的 levels 還沒落盤，這樣錄製中與離線算出的切點相同）。"""
    window = num(lv.get("windowSeconds")) or rl.LEVEL_WINDOW
    if window <= 0:
        return None
    levels = combined_levels(lv)
    if not levels:
        return None
    a, b = seg["startedAt"], seg["finishedAt"]
    levels = levels[: int(math.ceil(b / window - 1e-9))]
    iv = rl.levels_intervals(levels, window, params["vadThresholdDb"], params["vadMergeGap"], params["vadPad"], b)
    lo = max(b - CUT_SEARCH_SECONDS, a)
    best = None
    for (_, x1), (y0, _) in zip(iv, iv[1:]):
        mid = (x1 + y0) / 2.0
        if lo <= mid <= b and mid > a:
            best = mid
    return best


# ── worker ────────────────────────────────────────────────────────────────────

class Worker:
    def __init__(self, sess):
        self.sess = os.path.abspath(sess)
        self.rec = os.path.join(self.sess, "錄音")
        self.tracks = os.path.join(self.rec, "tracks")
        self.asr = os.path.join(self.tracks, "asr")
        self.work = os.path.join(self.asr, ".work")
        self.state_path = os.path.join(self.asr, "state.json")
        self.lock = threading.Lock()
        self.state = None
        self.info = {}       # 段落檔名 → {"a": analyze 結果或 None, "start": 成品起點, "length": 長度, "size": 大小}
        self.order = []      # 已分析段落的檔名（依段號）
        self.pcm = {}        # 段落檔名 → 48 kHz PCM wav 路徑
        self.mlx = None
        self.drop_paused = False
        self.stop_beat = threading.Event()

    # 狀態檔
    def save(self, **fields):
        with self.lock:
            self.state.update(fields)
            self.state["heartbeat"] = now_iso()
            write_json_atomic(self.state_path, self.state)

    def heartbeat_loop(self):
        while not self.stop_beat.wait(HEARTBEAT_SECONDS):
            try:
                self.save()
            except OSError:
                pass

    # 段落
    def analyze_upto(self, segs, k):
        """分析 segs[0..k]（已分析的不重做），成品起點＝前面可讀段落長度的和。"""
        fin = finalize_mod()
        for s in segs[: k + 1]:
            f = s["file"]
            if f in self.info:
                continue
            path = os.path.join(self.tracks, f)
            a = fin.analyze(path)
            prev = self.info[self.order[-1]] if self.order else None
            start = (prev["start"] + prev["length"]) if prev else 0.0
            self.info[f] = {"a": a, "start": start, "length": a["length"] if a else 0.0,
                            "size": os.path.getsize(path)}
            self.order.append(f)
            if a is None:
                log(f"段落讀不到可解碼的封包，略過：{f}")

    def segment_pcm(self, f):
        if f not in self.pcm:
            os.makedirs(self.work, exist_ok=True)
            self.pcm[f] = finalize_mod().segment_audio_pcm(os.path.join(self.tracks, f), self.info[f]["a"], self.work)
        return self.pcm[f]

    def window_wav(self, ws, we, index):
        """[ws, we]（成品時間）的音訊：各段 PCM 依框數切片接起來，再轉 16 kHz 單聲道（同正式 wav 的轉法）。"""
        os.makedirs(self.work, exist_ok=True)
        files = []
        w48 = os.path.join(self.work, f"w-{index:04d}.48k.wav")
        with wave.open(w48, "wb") as out:
            out.setnchannels(2)
            out.setsampwidth(2)
            out.setframerate(PCM_RATE)
            for f in self.order:
                i = self.info[f]
                if i["a"] is None:
                    continue
                s0, s1 = i["start"], i["start"] + i["length"]
                a, b = max(ws, s0), min(we, s1)
                if b - a <= 1e-6:
                    continue
                files.append({"file": f, "size": i["size"]})
                with wave.open(self.segment_pcm(f), "rb") as r:
                    n = r.getnframes()
                    f0 = min(max(int(round((a - s0) * PCM_RATE)), 0), n)
                    f1 = min(max(int(round((b - s0) * PCM_RATE)), f0), n)
                    r.setpos(f0)
                    left = f1 - f0
                    while left > 0:
                        chunk = r.readframes(min(left, 1 << 18))
                        if not chunk:
                            break
                        out.writeframes(chunk)
                        left -= len(chunk) // 4
        w16 = os.path.join(self.work, f"w-{index:04d}.wav")
        finalize_mod().ffmpeg("-i", w48, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", w16,
                              what=f"窗 {index} 轉 16 kHz", step="mix", target=f"w-{index:04d}.wav", seconds=we - ws)
        os.remove(w48)
        return w16, files

    def drop_old_pcm(self, upto):
        """成品時間 upto 以前就結束的段落 PCM 用不到了，刪掉。"""
        for f in list(self.pcm):
            i = self.info[f]
            if i["start"] + i["length"] <= upto + 1e-6:
                try:
                    os.remove(self.pcm.pop(f))
                except OSError:
                    pass

    def window_clips(self, ws, we):
        """窗內的有聲區間（窗內時間）：整場以同一組 VAD 參數算 clip_timestamps 再與窗取交集。
        回 None＝整窗送 ASR（不套 VAD、沒有 levels 或全場無聲，同 transcribe.sh 退回整檔）；[]＝窗內沒有有聲區間。"""
        p = self.state["params"]
        if not p["vadApplied"]:
            return None
        clips = rl.clip_timestamps(self.rec, p["vadThresholdDb"], p["vadPad"], p["vadMergeGap"])
        if not clips:
            return None
        out = []
        for a, b in clips:
            a, b = max(a, ws), min(b, we)
            if b - a > 1e-3:
                out.append([round(a - ws, 3), round(b - ws, 3)])
        return out

    def transcribe(self, wav, clips):
        p = self.state["params"]
        if self.mlx is None:
            import mlx_whisper  # in-process：一次執行只匯入、只載入模型一次（spec §4.11.6）
            self.mlx = mlx_whisper
        kw = {"path_or_hf_repo": p["model"], "language": p["language"], "initial_prompt": p["initialPrompt"],
              "condition_on_previous_text": False}
        if clips:
            kw["clip_timestamps"] = ",".join(f"{x:.3f}" for c in clips for x in c)
        return self.mlx.transcribe(wav, **kw)

    def make_window(self, ws, we):
        index = len(self.state["windows"]) + 1
        clips = self.window_clips(ws, we)
        wav, files = self.window_wav(ws, we, index)
        try:
            if clips == []:
                res = {"text": "", "segments": [], "language": self.state["params"]["language"]}
            else:
                res = self.transcribe(wav, clips)
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass
        segs = []
        for s in res.get("segments") or []:
            if not isinstance(s, dict):
                continue
            s = dict(s)
            for k in ("start", "end"):
                if num(s.get(k)) is not None:
                    s[k] = round(s[k] + ws, 3)
            if isinstance(s.get("words"), list):
                s["words"] = [dict(w, **{k: round(w[k] + ws, 3) for k in ("start", "end") if num(w.get(k)) is not None})
                              if isinstance(w, dict) else w for w in s["words"]]
            segs.append(s)
        name = f"w-{index:04d}.json"
        write_json_atomic(os.path.join(self.asr, name), {"text": res.get("text") or "", "segments": segs,
                                                          "language": res.get("language") or
                                                          self.state["params"]["language"]})
        with self.lock:
            self.state["windows"].append({"index": index, "start": round(ws, 3), "end": round(we, 3),
                                          "segments": files, "file": name})
        self.save()
        self.drop_old_pcm(we)
        log(f"窗 {index}：{ws:.3f}–{we:.3f} 秒（{', '.join(x['file'] for x in files)}）")

    def covered(self):
        w = self.state["windows"]
        return w[-1]["end"] if w else 0.0

    def pause_reason(self, phase, st):
        live = phase in LIVE_PHASES
        if not live:
            self.drop_paused = False
            return None
        dropped = num((st or {}).get("droppedFrames")) or 0
        if dropped > self.state["droppedFramesAtStart"]:
            self.drop_paused = True
        if self.drop_paused:
            return "drops"
        if other_finalizing(self.sess):
            return "otherFinalizing"
        return None

    def run(self):
        os.makedirs(self.asr, exist_ok=True)
        fd = os.open(os.path.join(self.asr, "worker.lock"), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            log("另一個 worker 正在處理這一場（worker.lock 被持有），結束")
            os.close(fd)
            return 0
        params = transcribe_params()
        old = load_json(self.state_path, None)
        if isinstance(old, dict) and old.get("status") == "complete" and old.get("params") == params:
            log("這一場的增量轉錄已完成，不重做")
            return 0
        for p in glob.glob(os.path.join(glob.escape(self.asr), "w-*.json")):
            os.remove(p)
        shutil.rmtree(self.work, ignore_errors=True)
        _, st = recording_phase(self.sess)
        self.state = {"schemaVersion": SCHEMA, "status": "running", "pausedReason": None, "heartbeat": now_iso(),
                      "params": params, "windows": [],
                      "droppedFramesAtStart": int(num((st or {}).get("droppedFrames")) or 0)}
        self.save()
        beat = threading.Thread(target=self.heartbeat_loop, daemon=True)
        beat.start()
        try:
            self.loop()
        except Exception as e:  # noqa: BLE001 — 任何失敗都記進 state.json，stitch 會回 3、prep 改整檔轉錄
            self.stop_beat.set()
            self.save(status="failed", pausedReason=None, error=f"{type(e).__name__}: {e}"[:500])
            print(f"✗ 增量轉錄失敗：{type(e).__name__}: {e}", file=sys.stderr, flush=True)
            return 2
        finally:
            self.stop_beat.set()
            shutil.rmtree(self.work, ignore_errors=True)
        log(f"完成：{len(self.state['windows'])} 窗，涵蓋到 {self.covered():.3f} 秒")
        return 0

    def loop(self):
        next_seg = 0
        while True:
            phase, st = recording_phase(self.sess)   # 先讀 phase 再讀 manifest：已停止時 manifest 已是最後版本
            stopped = phase in STOPPED_PHASES or phase == "gone"
            segs, lv = finished_segments(self.tracks)
            reason = None if stopped else self.pause_reason(phase, st)
            if reason is not None:
                if self.state["status"] != "paused" or self.state["pausedReason"] != reason:
                    self.save(status="paused", pausedReason=reason)
                    log(f"暫停（{reason}）")
                time.sleep(POLL_SECONDS)
                continue
            if self.state["status"] == "paused":
                self.save(status="running", pausedReason=None)
                log("恢復")
            if next_seg < len(segs):
                k = next_seg
                self.analyze_upto(segs, k)
                f = segs[k]["file"]
                i = self.info[f]
                end = i["start"] + i["length"]
                last = stopped and k == len(segs) - 1
                cut = None if (last or i["a"] is None) else cut_point(lv, segs[k], self.state["params"])
                if cut is not None:
                    local = min(max(cut - segs[k]["startedAt"], 0.0), i["length"])
                    cut = i["start"] + local
                    if cut - self.covered() < MIN_WINDOW_SECONDS:
                        cut = None
                cut = end if cut is None else cut
                if cut - self.covered() >= MIN_WINDOW_SECONDS:
                    self.make_window(self.covered(), cut)
                next_seg += 1
                continue
            if stopped:
                if self.order:
                    f = self.order[-1]
                    end = self.info[f]["start"] + self.info[f]["length"]
                    if end - self.covered() >= MIN_WINDOW_SECONDS:
                        self.make_window(self.covered(), end)
                self.save(status="complete", pausedReason=None)
                return
            time.sleep(POLL_SECONDS)


# ── stitch ────────────────────────────────────────────────────────────────────

class Unusable(Exception):
    pass


def heartbeat_age(st):
    try:
        t = datetime.datetime.fromisoformat(str(st.get("heartbeat")))
    except (TypeError, ValueError):
        return math.inf
    if t.tzinfo is None:
        t = t.astimezone()
    return (datetime.datetime.now().astimezone() - t).total_seconds()


def wait_complete(asr):
    """worker 還活著（持有 worker.lock）且 60 秒內有心跳時等它；回最後讀到的 state.json。"""
    sp, lock = os.path.join(asr, "state.json"), os.path.join(asr, "worker.lock")
    while True:
        st = load_json(sp, None)
        if not isinstance(st, dict):
            raise Unusable("沒有 tracks/asr/state.json")
        if st.get("status") == "complete":
            return st
        if lock_held(lock) and heartbeat_age(st) <= HEARTBEAT_STALE:
            time.sleep(POLL_SECONDS)
            continue
        raise Unusable(f"增量轉錄沒有完成（status={st.get('status')}），worker 也沒在跑")


def expected_inputs(tracks):
    ready = load_json(os.path.join(tracks, "audio-ready.json"), None)
    if isinstance(ready, dict) and isinstance(ready.get("segments"), list):
        rows = ready["segments"]
        total = sum(num(r.get("duration")) or 0.0 for r in rows if isinstance(r, dict))
        return [(r.get("file"), r.get("size")) for r in rows if isinstance(r, dict)], total, ready
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    if isinstance(fin, dict) and isinstance(fin.get("inputs"), list):
        return [(r.get("file"), r.get("size")) for r in fin["inputs"] if isinstance(r, dict)], None, None
    raise Unusable("沒有 audio-ready.json 也沒有 finalize.json.inputs，無從比對段落")


def stitch(sess, out):
    sess = os.path.abspath(sess)
    rec = os.path.join(sess, "錄音")
    tracks = os.path.join(rec, "tracks")
    asr = os.path.join(tracks, "asr")
    st = wait_complete(asr)
    windows = sorted([w for w in st.get("windows") or [] if isinstance(w, dict)], key=lambda w: w.get("index", 0))
    if not windows:
        raise Unusable("state.json 沒有任何窗")
    prev = 0.0
    for w in windows:
        if num(w.get("start")) is None or num(w.get("end")) is None or abs(w["start"] - prev) > 1e-3:
            raise Unusable(f"窗 {w.get('index')} 與前一窗沒有首尾相接")
        prev = w["end"]
    covered = []
    for w in windows:
        for x in w.get("segments") or []:
            key = (x.get("file"), x.get("size")) if isinstance(x, dict) else (None, None)
            if not covered or covered[-1] != key:
                covered.append(key)
    want, total, ready = expected_inputs(tracks)
    if covered != want:
        raise Unusable(f"窗涵蓋的段落（{len(covered)} 段）與收尾採用的段落（{len(want)} 段）不同")
    if total is not None and abs(prev - total) > DURATION_TOL:
        raise Unusable(f"窗的總長 {prev:.3f} 秒與 audio-ready.json 的 {total:.3f} 秒不符")
    params = transcribe_params()
    if st.get("params") != params:
        old = st.get("params") if isinstance(st.get("params"), dict) else {}
        diff = sorted(k for k in set(old) | set(params) if old.get(k) != params.get(k))
        raise Unusable(f"參數與這次 transcribe.sh 會用的不同：{', '.join(diff)}")
    if params["compensation"] != "off" or (ready is not None and ready.get("compensation") != "off"):
        raise Unusable("影音延遲補償不是 off")
    wav = ready.get("wav") if isinstance(ready, dict) else None
    others = [f for f in sorted(os.listdir(rec)) if os.path.isfile(os.path.join(rec, f)) and not f.startswith(".")
              and os.path.splitext(f)[1].lower() in AUDIO_EXTS and f != wav]
    if others:
        raise Unusable(f"錄音/ 還有其他音檔（{len(others)} 個），transcribe.sh 會串接整檔")
    segs, texts = [], []
    for w in windows:
        d = load_json(os.path.join(asr, str(w.get("file"))), None)
        if not isinstance(d, dict) or not isinstance(d.get("segments"), list):
            raise Unusable(f"窗 {w.get('index')} 的結果檔讀不到：{w.get('file')}")
        for s in d["segments"]:
            if isinstance(s, dict):
                s = dict(s, id=len(segs))
                segs.append(s)
                texts.append(str(s.get("text") or ""))
    write_json_atomic(out, {"text": "".join(texts), "segments": segs, "language": params["language"]})
    return len(windows), len(segs)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(prog="_asr_worker.py",
                                 description="錄製中的增量轉錄 worker 與 stitch（meeting-speed spec §3.9、§4.11；內部介面）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="逐窗轉錄已收尾的段落，錄製停止後補完並結束（結束碼 0 完成、2 參數錯或失敗）")
    r.add_argument("session", help="場次目錄")
    s = sub.add_parser("stitch", help="把各窗結果拼成 mlx_whisper 同 schema 的 JSON（0 可用、3 不可用、2 參數錯）")
    s.add_argument("session", help="場次目錄")
    s.add_argument("out", help="輸出 JSON 路徑")
    a = ap.parse_args(argv)
    if not os.path.isdir(os.path.join(a.session, "錄音")):
        print(f"✗ 不是場次目錄（沒有 錄音/）：{a.session}", file=sys.stderr)
        return 2
    if a.cmd == "run":
        if not incremental_enabled():
            log("config.json 的 transcribe.incremental.enabled 是 false，不做增量轉錄")
            return 0
        if not os.path.isdir(os.path.join(a.session, "錄音", "tracks")):
            print(f"✗ 沒有 錄音/tracks/：{a.session}", file=sys.stderr)
            return 2
        return Worker(a.session).run()
    out_dir = os.path.dirname(os.path.abspath(a.out))
    if not os.path.isdir(out_dir):
        print(f"✗ 輸出目錄不存在：{out_dir}", file=sys.stderr)
        return 2
    try:
        n, m = stitch(a.session, a.out)
    except Unusable as e:
        print(f"增量轉錄不可用：{e}", file=sys.stderr)
        return 3
    except (OSError, ValueError) as e:
        print(f"增量轉錄不可用：{type(e).__name__}: {e}", file=sys.stderr)
        return 3
    print(f"增量轉錄可用：{n} 窗、{m} 段 → {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

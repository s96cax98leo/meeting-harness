#!/usr/bin/env python3
"""_record_finalize.py <場次目錄>

把錄製段落 錄音/tracks/seg-*.mov 收成：
  影片/<場次名> <YYYY-MM-DD HH.MM.SS>.mov   H.264 high＋AAC 48 kHz 雙聲道（會議視窗畫面＋混音）
  錄音/<場次名> <YYYY-MM-DD HH.MM.SS>.wav   16 kHz 單聲道（轉錄輸入）
做法照 design.md §7.4（D7 整支重編補尾、D8 統一尺寸，合成一次轉碼；D20 兩軌混音、時間戳正規化）：
  1. ffprobe 每段，各軌長度一律由「可解碼的封包」算（不採 stream／format 層 duration，被中斷的 fragment 檔會高報）；
     只有完全讀不到可解碼封包的段（例如沒有 moov 的非 fragment 檔）略過並列出；
  2. 畫布＝(各段寬最大值, 各段高最大值)；位元率＝max(各段影片位元率)×1.5、下限 8 Mb/s；
  3. 逐段正規化成 tracks/.finalize/norm-NNNN.mov：所有軌以同一原點平移（保留段內音影相對位置）、
     影片 -fps_mode passthrough -enc_time_base demux（不重取樣影格、不丟幀、時間基準不變粗）、重複 PTS 只留一個、
     pad 置中補黑邊（不縮放、不裁切）、影片短於段落時以最後一幀補尾、沒有影片的段以前一段最後一幀（第一段則黑畫面）補；
     系統聲音與麥克風兩軌等權混音＋限幅（-1 dBFS），音訊統一 48 kHz 雙聲道 PCM（pcm_s16le，不在這一步編 AAC；
     -t 微秒精度截在段落長，PCM 沒有 priming 也沒有封包補零，解碼長度＝時間戳長度）；正規化後條件不成立即失敗；
  4. 音訊先出（meeting-speed spec §3.2、§4.2）：各段以與正規化相同的原點與混音抽成 48 kHz PCM（segment_audio_pcm），
     接成一條（補償時用 compensated_audio 的結果）轉 16 kHz wav；依序寫 audio-ready.json → finalize.json 第一階段
     （finishedAt、videoPublishedAt: null）→ os.replace 成 錄音/<同名>.wav → 印「音訊就緒：」——正式 wav 不等影片；
     audio-ready.json 與這次的段落、補償相同且 wav 在時不重寫（§4.3.2）；
  5. 影片：copy 條件（canvasLock、同尺寸、同 codec／profile／pix_fmt／time_base、同 extradata、沒有重複 PTS，§4.4.3）
     全部成立且上次不是 copy 驗證失敗 → 逐段 remux（-c:v copy，首幀拉到 0、最後封包補到段長）；否則整場走第 3 步的
     正規化。concat demuxer 串接：影片 -c:v copy、音訊 -c:a aac 256k 全片一次編碼（缺陷 J，spec §4.6.20）；
  6. 影片 rename 進 影片/；manifest.json 寫回 gapStats（R2：暫停邊界扣暫停長度、pausedTotal，spec §3.11）、各段 audioDuration、
     outputCanvas、outputVideoBitrate（其他鍵不動）；finalize.json 第二階段（videoPublishedAt、videoPath、verify pending）；
     印「成品就緒：」；
  7. 驗證（整支解碼＋dts 嚴格遞增，記為 concat（verify:<影片檔名>））：通過 → verify ok、.pipeline-state.json 記 record: done
     （加鎖）、刪段落；失敗或逾時 → 影片改名 <同名>.verify-failed.mov、verify failed、段落保留、回 5（§4.5）。
R2：一開始（已完成判斷之前）把 tracks/markers.json 原樣複製成 錄音/markers.json（內容相同不重寫，spec §4.19.3）。
冪等：finalize.json 存在、兩個輸出都在、輸入段（檔名＋大小）相同、verify 不是 failed／pending → 印「已完成」回 0，不寫任何檔。
收尾成功後刪已併入成品的 tracks/seg-*.mov（manifest、record.meta.json、finalize.json 留著；keep-segments 或
MH_KEEP_SEGMENTS=1 時保留，spec §6 第 111 條）。
段落只刪掉一部分（刪檔失敗）的場次：剩下的段落都在 finalize.json 的輸入裡、成品都在 → 視為已完成並重試清除，不拿殘缺段落重做。
R3（spec §4.28、§3.17、R3-D3）：
  - 收尾鎖：開頭在 錄音/tracks/.finalize.lock 取 flock(LOCK_EX|LOCK_NB)，持有到程序結束；拿不到 → 結束碼 5、
    stderr「這個場次正在收尾」，不讀不寫其他檔；
  - 每個 ffmpeg／ffprobe 子程序都有逾時（step_timeout）；逾時 → 整個子程序群組 SIGTERM、5 秒後 SIGKILL，
    finalize.json 寫 timedOut: {step, seconds}，結束碼 5，段落全部保留；
  - 讀不到的段落搬到 tracks/unreadable/（撞名加 -1、-2），finalize.json 的 skipped[] 每筆是 {file, movedTo}
    （讀舊場次時字串視同 {file, movedTo: null}）；
  - 每一步的耗時印到 stdout：「耗時 <步驟>（<對象>）：<秒數> 秒」（spec §4.28.8）。
R3 S-C（spec §4.37、§3.17、R3-D9；ADR adr-r3-sync-compensation.md、adr-r3-concat-then-mix.md）：
  - mode：MH_SYNC_COMPENSATION 優先，否則 record.defaults.json 的 syncCompensation，都沒有＝off（預設 off）；
    不認得的值＝off 並記一行；
  - off：完全走上面的 D20 流程；finalize.json.syncCompensation＝{"mode": "off", "segments": []}；
  - reported／calibrated：影片照 D20；系統聲音與麥克風各自逐段解成 PCM、整條串接，系統聲音整條連續延後
    （相鄰且延遲相同的段併成區間，只在延遲改變處補靜音或截掉前一區間的尾，最後截回原總長），再混音、限幅，
    串接時一次編 AAC；混音一步的逾時記為 timedOut.step＝mix；
  - 暫停邊界不另處理：延後以串接後（不含暫停）的時間軸為準（spec §7 疑慮 58）；
  - 冪等：mode 與上次收尾不同時不算已完成（保留段落時可換 mode 重跑比較）。
R3x B（spec §3.25、§4.55、design R3x-D10）：
  - 第 1 步（分析）與第 3 步（逐段正規化）經 run_ordered 平行；平行度 MH_FINALIZE_JOBS（預設 3、上限 3、1＝串行、
    錄製中降為 2、退回 libx264 後為 1），每派一段前重算；段依段號嚴格遞增派出，不跳號；
  - 任一段失敗 → 停止派工、段號較大的在跑段以 SIGTERM 中止（SegmentAborted，不改試 libx264），回報段號最小的失敗；
  - 串接、解碼驗證、抽 wav、S-C 補償照串行；進度行「正規化 已完成 k/N」；
  - MH_FINALIZE_WAIT_LOCK=1：收尾鎖拿不到時等它放開再做冪等判斷（只有背景收尾會設，spec §6 第 156 條）。

結束碼：0 完成或已完成；2 參數錯；3 沒有段落或全部讀不到；5 失敗（段落保留）、該場次正在收尾（收尾鎖被持有）、
任一步逾時（spec §6 第 132 條）。
環境變數：MH_FFMPEG（ffmpeg 路徑，可為測試替身）、MH_FFPROBE、MH_RECORD_HOME（讀 record.defaults.json 的 ffmpeg 路徑）、
MH_FINALIZE_STEP_TIMEOUT（秒，正數；設了就一律用它當每一步的逾時，測試用）、MH_SYNC_COMPENSATION（off｜reported｜calibrated，
覆寫 record.defaults.json 的 syncCompensation）、MH_FINALIZE_JOBS（收尾平行度）、MH_FINALIZE_WAIT_LOCK（1＝等收尾鎖）。
"""
import contextlib
import fcntl
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import wave
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor
from concurrent.futures import wait as futures_wait

_LIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)
# bin/lib/ 要先進 sys.path（noqa: E402）。共用 helper 由 _record_lib 提供（meeting-speed spec §4.13.2），
# 不被測試釘住的純函式搬到 _finalize_*（§4.13.1）；模組內名稱照舊可用
from _record_lib import load_json, paused_total, record_home, update_pipeline_state, write_json_atomic  # noqa: E402,F401
from _finalize_media import (LIMIT, audio_graph, even_up, first_stream, now_iso, num,  # noqa: E402
                             stream_dts, stream_start, tick_floor)
from _finalize_sync import (COPY_CHUNK, SYNC_FRAME_BYTES, SYNC_MODES, SYNC_RATE, compensation_kind,  # noqa: E402
                            delay_ops, sync_plan, track_roles, write_zeros)
from _finalize_state import (already_done, audio_reusable, copy_markers, copy_plan, copy_verify_failed,  # noqa: E402
                             finalized_with_partial_cleanup, finalized_without_segments, input_list,
                             move_unreadable, ready_segments, session_stamp, unmerged_files, write_manifest)

AAC_RATE = "256k"
MIN_BITRATE = 8_000_000
VIDEO_TIMESCALE = "90000"
TAIL_PAD_MIN = 0.01       # 影片比段落短超過這麼多就以最後一幀複製補尾（§4.6.3）
CLOSE_GAP = 1 / 60 - 0.001  # 「過近」的相鄰影格間隔（spec §4.3.3 (ii)）：finalize 每個段落邊界最多只能製造 1 個
TAIL_SNAP = 0.01          # 依連結影格率下一幀落在段落結束前這麼多秒內就算已到結尾（grid_reaches_end）
CLONE_SNAP = 1 / 60       # 補尾的複製幀落在 cap 前這麼多秒內就併進 cap（複製幀與 cap 之間不留過近間隔）
TAIL_PAD_FPS_FLOOR = 240   # 補尾 tpad 的補幀數以 max(link_fps, 這個值) 推算（meeting-speed spec §4.4.12，D3 a）
TAIL_CAP_MARGIN = 0.005   # 補尾上限 cap＝段落長−5 ms（不依連結影格率，design.md §7.4 第 3 步、spec §4.6.17／§4.6.18）
LATE_VIDEO_MIN = 0.001    # 影片比原點 O 晚這麼多才把第一幀往前延到 0
NORM_START_MAX = 0.05     # 正規化後每條軌 start_time 必須在 [0, 0.05] 秒
NORM_LENGTH_TOL = 0.05    # 正規化後各軌長與段落長差必須 < 50 ms
KEYFRAME_EVERY = 2.0      # 正規化時每 2 秒強制一個關鍵幀（以時間計，VFR 也一致；兼顧拖曳定位）
GOP_FRAMES_MAX = 100000   # 以影格數計的 GOP 上限設到用不到，關鍵幀只由 KEYFRAME_EVERY 決定（缺陷 N）
KILL_GRACE = 5.0          # 逾時：SIGTERM 之後等這麼多秒仍在就 SIGKILL（R3-D3）
FINALIZE_JOBS_DEFAULT = 3     # 收尾平行度預設（spec §3.25；`pf` §2.3：瓶頸在 VideoToolbox，3 最佳）
FINALIZE_JOBS_MAX = 3
FINALIZE_JOBS_RECORDING = 2   # 錄製中的上限（design R3x-D9）
SIGTERM_RESCANS = 2           # on_sigterm 結束子程序群組後再重掃的次數（修正輪 I4）
SIGTERM_RESCAN_SECONDS = 0.05
WAIT_LOCK_POLL_SECONDS = 0.5  # MH_FINALIZE_WAIT_LOCK=1 時再試收尾鎖的間隔（修正輪 I5）
DISPATCH_POLL_SECONDS = 0.2   # run_ordered 主執行緒等結果的間隔（讓 SIGTERM handler 能在主執行緒上執行）


class FinalizeError(Exception):
    pass


class SegmentAborted(Exception):
    """這一段因為段號較小的段失敗（或收到 SIGTERM）而被中止：不是失敗，不得改試 libx264（spec §3.25 第 7 點）。
    刻意不繼承 FinalizeError，encode 的 except FinalizeError 接不到它。"""


class StepTimeout(FinalizeError):
    """某一步的 ffmpeg／ffprobe 超過 step_timeout（spec §4.28.3）。"""

    def __init__(self, step, seconds, target):
        self.step, self.seconds, self.target = step, seconds, target
        super().__init__(f"步驟逾時：{step}（{target}）超過 {seconds:g} 秒")


def step_timeout(step, seconds):
    """spec §4.28.4：每一步的逾時（秒）。MH_FINALIZE_STEP_TIMEOUT（正數）存在時一律用它；
    否則 ffprobe 30 秒、逐段正規化 max(120, 該段長度 × 10)、串接與混音 max(300, 全片長度 × 3)。"""
    env = num(os.environ.get("MH_FINALIZE_STEP_TIMEOUT"))
    if env is not None and env > 0:
        return env
    s = max(num(seconds) or 0.0, 0.0)
    if step == "probe":
        return 30.0
    if step == "normalize":
        return max(120.0, s * 10)
    return max(300.0, s * 3)


_ACTIVE = set()  # 正在跑的子程序（各自一個 process group）；收到 SIGTERM 時一併結束
_ACTIVE_LOCK = threading.Lock()   # 增刪 _ACTIVE、_SEG_PROCS、改 _ABORT_FROM 時持有；on_sigterm 不取這把鎖
_SEG_PROCS = {}                   # 段索引 → set(Popen)（空集合時刪鍵）；_ACTIVE_LOCK 保護
_ABORT_FROM = None                # 目前最小的失敗段索引；_ACTIVE_LOCK 保護
_ABORT_DISPATCH = threading.Event()  # 有段失敗後為 set，停止派工（一個收尾程序只收一場，不 clear）
_STOPPING = threading.Event()     # SIGTERM 後為 set
_SEG = threading.local()          # .index：本執行緒正在跑的段索引；主執行緒與串行路徑為 None
_X264_LOCK = threading.Lock()     # libx264 編碼同時最多 1 個
_SAY_LOCK = threading.Lock()      # say() 一次寫完一行
_X264_FALLBACK = threading.Event()  # 本次收尾已有段退回 libx264（之後派出的段平行度一律 1）
_FALLBACK_LOCK = threading.Lock()
_X264_NOTED = False               # 已印過「改用 libx264」（N-3：成功後才印）；_FALLBACK_LOCK 保護
_JOBS_LAST = 1                    # 最近一次算出的平行度（不含 libx264 退回）；決定要不要印「降為 1」


def kill_group(p):
    """結束子程序整個群組（slow_ffmpeg.sh 這類包裝腳本底下的真 ffmpeg 也一起）：SIGTERM，KILL_GRACE 秒後 SIGKILL。"""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(p.pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            p.communicate(timeout=KILL_GRACE)
            return
        except subprocess.TimeoutExpired:
            continue
    p.wait()


def step_target(path):
    """耗時行與逾時訊息裡的 <對象>：原始段落（tracks/seg-*.mov）寫主檔名（seg-0001），其他檔寫檔名。
    原始段落不寫完整檔名：stdout 出現完整段落檔名代表「略過讀不到的段落」（test_finalize.py:330 的判準）。"""
    name = os.path.basename(str(path))
    stem, ext = os.path.splitext(name)
    return stem if stem.startswith("seg-") and ext == ".mov" else name


def run_step(cmd, step, target, seconds=0.0):
    """執行一個 ffmpeg／ffprobe 子程序：帶逾時、耗時印到 stdout（spec §4.28.3、§4.28.8）。
    子程序放在自己的 process group，逾時時整組結束，不留殘留子程序。
    R3x（spec §3.25 第 4–6 點）：啟動前、登記後、結束後三處檢查中止條件，成立就丟 SegmentAborted。
    子程序只由這個執行緒回收（communicate，或逾時時 kill_group）。"""
    seg = getattr(_SEG, "index", None)

    def stop_now():
        if _STOPPING.is_set():
            return True
        cut = _ABORT_FROM
        return _ABORT_DISPATCH.is_set() and seg is not None and cut is not None and seg > cut

    if stop_now():
        raise SegmentAborted(f"{step}（{target}）未啟動：收尾已中止")
    limit = step_timeout(step, seconds)
    t0 = time.monotonic()
    p = subprocess.Popen([str(c) for c in cmd], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, start_new_session=True)
    with _ACTIVE_LOCK:
        _ACTIVE.add(p)
        if seg is not None:
            _SEG_PROCS.setdefault(seg, set()).add(p)
        late = stop_now()
        if late:  # 主執行緒取快照時這個子程序還沒登記：自己結束它
            try:
                os.killpg(p.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
    try:
        try:
            out, err = p.communicate(timeout=limit)
        except subprocess.TimeoutExpired:
            kill_group(p)
            if stop_now():
                raise SegmentAborted(f"{step}（{target}）已中止") from None
            raise StepTimeout(step, limit, target) from None
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(p)
            if seg is not None:
                procs = _SEG_PROCS.get(seg)
                if procs is not None:
                    procs.discard(p)
                    if not procs:
                        del _SEG_PROCS[seg]
        say(f"耗時 {step}（{target}）：{time.monotonic() - t0:.1f} 秒")
    if stop_now():
        raise SegmentAborted(f"{step}（{target}）已中止")
    return subprocess.CompletedProcess(p.args, p.returncode, out, err)


def on_sigterm(signum, frame):
    """錄製實例取消收尾（SIGTERM）：先結束正在跑的子程序群組，不讓 ffmpeg 留著寫 .finalize/，再以 5 結束。
    R3x（修正輪 I4）：先設 _STOPPING（worker 不再啟動新子程序），對 _ACTIVE 的快照送 SIGKILL，再重掃
    SIGTERM_RESCANS 次收掉剛登記的。在主執行緒執行，不取鎖、不經 stdout 的輸出函式（主執行緒可能正持有它們）。"""
    _STOPPING.set()
    sent = set()
    for k in range(SIGTERM_RESCANS + 1):
        if k:
            time.sleep(SIGTERM_RESCAN_SECONDS)
        for p in list(_ACTIVE):
            if p.pid in sent:
                continue
            sent.add(p.pid)
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    print("✗ 收尾被中止（SIGTERM）；段落都還在（錄音/tracks/）。", file=sys.stderr, flush=True)
    os._exit(5)


_LOCK_FD = None


def acquire_finalize_lock(tracks):
    """spec §3.15、§4.28.1：錄音/tracks/.finalize.lock 取 flock(LOCK_EX|LOCK_NB)，持有到程序結束。
    拿到回 True；被另一個程序持有回 False。鎖檔已存在時只開不寫（mtime 不變）。"""
    global _LOCK_FD
    fd = os.open(os.path.join(tracks, ".finalize.lock"), os.O_CREAT | os.O_RDWR | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False
    _LOCK_FD = fd
    return True


def finalize_jobs(raw, *, recording=False, fallback=False):
    """spec §3.25：MH_FINALIZE_JOBS 的有效平行度。正整數字串（前後空白忽略）；沒設、空字串、不是正整數 → 預設 3；
    大於上限 3 → 3。錄製中上限 2；本次收尾已退回 libx264 → 1。"""
    text = raw.strip() if isinstance(raw, str) else ""
    j = int(text) if text.isascii() and text.isdigit() and int(text) > 0 else FINALIZE_JOBS_DEFAULT
    j = min(j, FINALIZE_JOBS_MAX)
    if recording:
        j = min(j, FINALIZE_JOBS_RECORDING)
    if fallback:
        j = 1
    return j


def recording_in_progress(home=None):
    """design R3x-D9：有錄製在跑＝<home>/record.pid 的 pid 活著（kill 0；PermissionError 也算活著），而且
    record.status.json 的 pid 等於它、phase 為 recording。只讀不寫、不取任何鎖；讀不懂一律 False。"""
    home = home or record_home()
    try:
        with open(os.path.join(home, "record.pid"), encoding="utf-8") as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except PermissionError:
        pass
    except OSError:
        return False
    try:
        with open(os.path.join(home, "record.status.json"), encoding="utf-8") as f:
            st = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(st, dict):
        return False
    sp = st.get("pid")
    return isinstance(sp, int) and not isinstance(sp, bool) and sp == pid and st.get("phase") == "recording"


def normalize_deps(has_video):
    """spec §4.55.3：每段正規化依賴的段索引（0 起算）。沒有影片的段要取前一段 norm 的最後一幀 → 依賴前一段；
    第一段沒有影片時以黑畫面補，沒有依賴。"""
    return [None if v or k == 0 else k - 1 for k, v in enumerate(has_video)]


def run_ordered(count, fn, *, jobs, deps=None):
    """spec §3.25：依段號嚴格遞增派工、平行執行 fn(i)，回依索引排列的結果。
    jobs() 在每派一段之前呼叫（目前平行度）；第一次回 1 時不建 thread pool，在主執行緒依序呼叫 fn。
    deps[i] 是第 i 段依賴的索引：它還沒完成時第 i 段與之後的段都不派（不跳號）。
    任一段丟例外（SegmentAborted 除外）→ 停止派工、段號較大的在跑段由主執行緒對群組送 SIGTERM，
    KILL_GRACE 秒後仍登記在 _SEG_PROCS 的再送 SIGKILL；子程序一律由啟動它的 worker 回收。
    全部已派的段結束後丟出段號最小的例外。"""
    cap = jobs()
    if count <= 0:
        return []
    if cap <= 1:
        return [fn(i) for i in range(count)]

    results = [None] * count
    finished, errors, aborted = set(), {}, set()
    termed, killed = {}, set()

    def task(i):
        _SEG.index = i
        try:
            return fn(i)
        finally:
            _SEG.index = None

    def stop_higher(failed=None):
        """failed：剛失敗的段索引。在 _ACTIVE_LOCK 內更新 _ABORT_FROM、停止派工、取段號大於 _ABORT_FROM 的 Popen 快照；
        放鎖後先 SIGTERM，KILL_GRACE 秒後仍在表裡的再 SIGKILL 一次。"""
        global _ABORT_FROM
        with _ACTIVE_LOCK:
            if failed is not None:
                _ABORT_FROM = failed if _ABORT_FROM is None else min(_ABORT_FROM, failed)
                _ABORT_DISPATCH.set()
            cut = _ABORT_FROM
            snap = [] if cut is None else [p for k, ps in _SEG_PROCS.items() if k > cut for p in ps]
        now = time.monotonic()
        for p in snap:
            if p not in termed:
                termed[p] = now
                sig = signal.SIGTERM
            elif p not in killed and now - termed[p] >= KILL_GRACE:
                killed.add(p)
                sig = signal.SIGKILL
            else:
                continue
            try:
                os.killpg(p.pid, sig)
            except (ProcessLookupError, PermissionError):
                pass

    pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix="finalize")
    running, nxt, first = {}, 0, True
    try:
        while True:
            while nxt < count and not _ABORT_DISPATCH.is_set() and not _STOPPING.is_set():
                d = deps[nxt] if deps else None
                if d is not None and d not in finished:
                    break
                if not first:
                    cap = jobs()
                first = False
                if len(running) >= cap:
                    break
                running[pool.submit(task, nxt)] = nxt
                nxt += 1
            if not running:
                break
            done, _ = futures_wait(list(running), timeout=DISPATCH_POLL_SECONDS, return_when=FIRST_COMPLETED)
            for f in done:
                i = running.pop(f)
                exc = f.exception()
                if exc is None:
                    results[i] = f.result()
                    finished.add(i)
                elif isinstance(exc, SegmentAborted):
                    aborted.add(i)
                else:
                    errors[i] = exc
                    stop_higher(i)
            if _ABORT_DISPATCH.is_set():
                stop_higher()
    finally:
        pool.shutdown(wait=True)
    if errors:
        raise errors[min(errors)]
    if aborted or nxt < count:
        raise SegmentAborted("收尾已中止")
    return results


def wait_finalize_lock(tracks):
    """spec §3.25 收尾鎖等待（MH_FINALIZE_WAIT_LOCK=1）：收尾鎖被另一個程序持有時，每 WAIT_LOCK_POLL_SECONDS 秒再試，
    直到取得。等待沒有上限（由 app 的 finalizeDeadline 管；SIGTERM 照 on_sigterm 回 5）。"""
    say("● 這個場次正在收尾（另一個程序持有 錄音/tracks/.finalize.lock），等它完成…")
    while not acquire_finalize_lock(tracks):
        time.sleep(WAIT_LOCK_POLL_SECONDS)


def say(msg):
    """一次寫完一行（平行時各行完整、不交錯，修正輪 N5）。"""
    with _SAY_LOCK:
        sys.stdout.write(f"{msg}\n")
        sys.stdout.flush()


def keep_segments():
    """收尾成功後是否保留原始段落：MH_KEEP_SEGMENTS=1 或 <record home>/keep-segments 存在（實機驗收要用段落時）。"""
    return os.environ.get("MH_KEEP_SEGMENTS") == "1" or os.path.exists(os.path.join(record_home(), "keep-segments"))


def cleanup_segments(segs):
    """收尾成功（成品已通過長度檢查、wav 已原子出現）後刪掉原始段落：內容與 影片/ 重疊，空間加倍（spec §6 第 111 條）。
    manifest、record.meta.json、levels、finalize.json 留著。"""
    if keep_segments():
        say("  保留原始段落（keep-segments）")
        return
    removed = 0
    for p in segs:
        try:
            os.remove(p)
            removed += 1
        except OSError as e:
            say(f"  ⚠ 刪不掉 {os.path.basename(p)}：{e}")
    say(f"  已刪除原始段落 {removed} 個（成品已驗證；內容與 影片/ 重疊）")


def defaults_ffmpeg():
    home = record_home()
    try:
        with open(os.path.join(home, "record.defaults.json"), encoding="utf-8") as f:
            v = json.load(f).get("ffmpeg")
        return v if isinstance(v, str) and os.path.isfile(v) else None
    except (OSError, ValueError, AttributeError):
        return None


def find_tool(name, env):
    """MH_FFMPEG／MH_FFPROBE → record.defaults.json → PATH → Homebrew 常見路徑。
    錄製器由 GUI 啟動時 PATH 沒有 /opt/homebrew/bin，所以要有後面幾層。"""
    v = os.environ.get(env)
    if v:
        return v
    if name == "ffmpeg":
        d = defaults_ffmpeg()
        if d:
            return d
    elif name == "ffprobe":
        d = defaults_ffmpeg()
        if d and os.path.isfile(os.path.join(os.path.dirname(d), "ffprobe")):
            return os.path.join(os.path.dirname(d), "ffprobe")
    w = shutil.which(name)
    if w:
        return w
    for p in (f"/opt/homebrew/bin/{name}", f"/usr/local/bin/{name}"):
        if os.path.isfile(p):
            return p
    return name


FFMPEG = find_tool("ffmpeg", "MH_FFMPEG")
FFPROBE = find_tool("ffprobe", "MH_FFPROBE")


def ffmpeg(*args, what="", step="normalize", target="", seconds=0.0):
    cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    r = run_step(cmd, step, target or what, seconds)
    if r.returncode != 0:
        raise FinalizeError(f"ffmpeg 失敗（{what}）：{r.stderr.strip()[-800:]}")
    return r


def probe(path):
    # -show_data_hash：streams 多 extradata_hash（copy 條件比對 SPS/PPS，spec §4.4.3），不另跑一次 ffprobe（§4.4.7）
    r = run_step([FFPROBE, "-v", "error", "-show_streams", "-show_format", "-show_data_hash", "sha256",
                  "-of", "json", str(path)], "probe", step_target(path))
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except ValueError:
        return None


def probe_packets(path):
    """一次 ffprobe 掃出全部封包（stream_index、pts、dts、duration、flags）；packets_by_stream／packet_rows_dts 共用，
    同一個檔不重跑（meeting-speed spec §4.4.7）。讀不懂回 []。"""
    r = run_step([FFPROBE, "-v", "quiet", "-show_entries",
                  "packet=stream_index,pts_time,dts_time,duration_time,flags", "-of", "json", str(path)],
                 "probe", step_target(path))
    try:
        return json.loads(r.stdout or "{}").get("packets") or []
    except ValueError:
        return []


def packets_by_stream(path, keep_discard=False, pkts=None):
    """每條軌的封包（pts、duration、flags）；略過標了 D（discard，例如 AAC priming）或 C（corrupt，
    例如被中斷的 fragment 檔最後半個封包）的封包——只留「可解碼」的部分（design.md §7.4 第 1 步）。
    pkts：probe_packets 已掃好的結果（給了就不再跑 ffprobe）。"""
    out = {}
    if pkts is None:
        pkts = probe_packets(path)
    for k in pkts:
        flags = k.get("flags") or ""
        if "C" in flags or ("D" in flags and not keep_discard):
            continue
        pts = num(k.get("pts_time"))
        if pts is None:
            continue
        idx = k.get("stream_index")
        out.setdefault(idx, []).append((pts, num(k.get("duration_time")) or 0.0))
    return out


def analyze(path):
    """第 1 步：一段的軌道資訊。長度一律由封包算（最後一個可解碼封包的 pts＋duration − 起點），
    不採 stream／format 層的 duration（中斷的 fragment 檔會高報，spec §4.6.15）。
    完全讀不到可解碼封包的段回 None（略過，spec §4.6.9）。"""
    info = probe(path)
    if not info:
        return None
    pk = packets_by_stream(path)
    video, audios = None, []
    for s in info.get("streams", []):
        kind = s.get("codec_type")
        if kind not in ("video", "audio"):
            continue
        rows = pk.get(s.get("index")) or []
        if not rows:
            continue
        start = stream_start(s)
        first = min(p for p, _ in rows)
        if start is None:
            start = first
        end = max(p + d for p, d in rows)
        t = {"stream": s, "start": start, "end": end, "length": max(end - min(start, first), 0.0)}
        if kind == "video":
            if video is None:
                pts = [p for p, _ in rows]
                t["frames"] = len(pts)
                t["dups"] = len(pts) - len(set(pts))
                t["last_pts"] = max(pts)
                video = t
        else:
            audios.append(t)
    if video is None and not audios:
        return None
    tracks = ([video] if video else []) + audios
    origin = min(t["start"] for t in tracks)
    end = max(t["end"] for t in tracks)
    return {"info": info, "video": video, "audios": audios, "origin": origin, "length": end - origin,
            "audioDuration": max((t["length"] for t in audios), default=None)}


def link_fps(s):
    """ffmpeg 給解碼輸出連結的影格率（大致等於 av_guess_frame_rate：先取 r_frame_rate）。
    tpad 依這個影格率補幀，尾端補幀要以它推算要補幾幀（補尾上限 cap 不依它，見 normalize）。"""
    for k in ("r_frame_rate", "avg_frame_rate"):
        v = (s or {}).get(k, "")
        if "/" in v:
            a, b = v.split("/", 1)
            if num(a) and num(b):
                f = num(a) / num(b)
                if 1 <= f <= 1000:
                    return f
    return 30.0


def encoders():
    """videotoolbox 不能用時（例如沒有硬體編碼器的環境）退回 libx264，參數同為 high profile。
    關鍵幀一律以時間計（每 KEYFRAME_EVERY 秒強制一個），以影格數計的 GOP 設成用不到：h264_videotoolbox
    沒指定 -g 時預設每 12 幀一個關鍵幀，稀疏 VFR 段的關鍵幀位置隨影格數漂移（缺陷 N 的觸發條件之一）。
    不用 B 幀（-bf 0）：解碼順序＝呈現順序，最後一個封包就是最後一幀，encode() 才能可靠地設它的長度。"""
    gop = ["-g", GOP_FRAMES_MAX, "-bf", 0,
           "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_EVERY:g})"]
    return [["-c:v", "h264_videotoolbox", "-profile:v", "high", *gop],
            ["-c:v", "libx264", "-profile:v", "high", "-preset", "medium", *gop]]


def encode(inputs, graph, out, *, dur, bitrate, what="", target=""):
    """graph 輸出 [v] 與 [a]。影片 -fps_mode passthrough -enc_time_base demux：保留原始影格時間、
    編碼器沿用輸入 stream 的時間基準（不讓 ffmpeg 依影格率猜，t6 缺陷 3 的根因 (a)）。
    音訊寫 PCM（pcm_s16le）：AAC 只在第 4 步串接時全片編一次（缺陷 J，design.md §7.4 第 3 步）。
    影片最後一個封包的長度設到段落結束 dur（至少 1 tick）：mov muxer 以「最後一幀 PTS＋長度」寫 edit list，
    長度只有 1 tick 時 edit list（movie timescale 1/1000）在最後一幀的 PTS 就結束，最後一幀被標 discard；
    倒數第二幀又剛好是關鍵幀時，mov demuxer 在 edit list 結束後遇到關鍵幀就停止建索引，最後一幀
    （例如補尾的複製幀）整個讀不到（缺陷 N 的根因）。"""
    last_dur = f"setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,max(1\\,round({dur:.6f}/TB)-PTS)\\,DURATION)"
    last = None
    for enc in encoders():
        x264 = "libx264" in enc
        if x264:
            note_x264_fallback()
        # libx264 本身吃滿多核：同時最多 1 個（spec §3.25）；videotoolbox 不取鎖
        with _X264_LOCK if x264 else contextlib.nullcontext():
            try:
                ffmpeg(*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]",
                       *enc, "-b:v", bitrate, "-maxrate", 2 * bitrate, "-bufsize", 4 * bitrate, "-pix_fmt", "yuv420p",
                       "-fps_mode", "passthrough", "-enc_time_base:v", "demux", "-bsf:v", last_dur,
                       "-video_track_timescale", VIDEO_TIMESCALE,
                       "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le",
                       "-t", f"{dur:.6f}", "-f", "mov", out, what=what, step="normalize", target=target, seconds=dur)
                if x264:
                    note_x264_success()
                return
            except SegmentAborted:
                # 被中止的段不是失敗：只刪不完整的輸出、往上丟，不改試 libx264（spec §4.55.10）
                if os.path.exists(out):
                    os.remove(out)
                raise
            except StepTimeout:
                if os.path.exists(out):
                    os.remove(out)
                raise
            except FinalizeError as e:
                last = e
                if os.path.exists(out):
                    os.remove(out)
    raise last


def note_x264_fallback():
    """本次收尾第一次改試 libx264：之後派出的段平行度一律 1（spec §3.25）。這時還不印——被中止或失敗的段
    不算改用成功（N-3，meeting-speed spec §4.4.10）。"""
    _X264_FALLBACK.set()


def note_x264_success():
    """N-3（meeting-speed spec §4.4.10）：第一次有段以 libx264 重編成功後才印「改用 libx264」一行
    （平行度原本大於 1 時，spec §3.25）；整次收尾只印一次。"""
    global _X264_NOTED
    with _FALLBACK_LOCK:
        if _X264_NOTED:
            return
        _X264_NOTED = True
        if _JOBS_LAST > 1:
            say("改用 libx264，收尾平行度降為 1")


def sync_mode():
    """spec §4.37.2：MH_SYNC_COMPENSATION 有值時優先；否則 record.defaults.json 的 syncCompensation；
    都沒有＝off；不認得的值＝off 並記一行（stdout 由錄製實例逐行寫進 record.log）。預設 off（§4.37.8）。"""
    env = os.environ.get("MH_SYNC_COMPENSATION")
    if env:
        raw, src = env, "MH_SYNC_COMPENSATION"
    else:
        d = load_json(os.path.join(record_home(), "record.defaults.json"), {})
        raw = d.get("syncCompensation") if isinstance(d, dict) else None
        src = "record.defaults.json 的 syncCompensation"
        if raw is None:
            return "off"
    if isinstance(raw, str) and raw in SYNC_MODES:
        return raw
    say(f"⚠ 不認得的 {src}：{raw}；影音延遲補償以 off 處理")
    return "off"


def extract_track(i, seg, a, role_stream, work, kind):
    """補償路徑：一段的一條音軌解成 48 kHz 雙聲道 s16le raw，原點與 D20 正規化相同（輸入檔最早的 start_time），
    開頭與結尾補靜音到段落長；這段沒有這條音軌時整段靜音。回傳 raw 檔路徑。"""
    dur = a["length"]
    out = os.path.join(work, f"{kind}-{i:04d}.raw")
    if role_stream is None:
        ffmpeg("-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur:.6f}", "-c:a", "pcm_s16le",
               "-f", "s16le", out, what=f"補靜音 {kind} {os.path.basename(seg)}", step="normalize",
               target=step_target(seg), seconds=dur)
        return out
    ch = int(role_stream["stream"].get("channels") or 2)
    up = "pan=stereo|c0=c0|c1=c0" if ch == 1 else "aformat=channel_layouts=stereo"
    graph = (f"[0:{role_stream['stream']['index']}]aresample=48000,{up},"
             f"aresample=48000:async=1:first_pts=0,apad=whole_dur={dur:.6f}[a]")
    ffmpeg("-i", seg, "-filter_complex", graph, "-map", "[a]", "-ar", "48000", "-ac", "2", "-t", f"{dur:.6f}",
           "-c:a", "pcm_s16le", "-f", "s16le", out, what=f"解出 {kind} {os.path.basename(seg)}", step="normalize",
           target=step_target(seg), seconds=dur)
    return out


def copy_range(dst, src, start, nbytes):
    src.seek(start)
    while nbytes > 0:
        b = src.read(min(nbytes, COPY_CHUNK))
        if not b:
            raise FinalizeError("補償延遲時系統聲音的 PCM 比預期短")
        dst.write(b)
        nbytes -= len(b)


def compensated_audio(good, plan, work, total):
    """補償開啟時的音訊（ADR adr-r3-concat-then-mix.md）：兩軌各自逐段解成 PCM、整條串接；系統聲音整條連續延後
    （delay_ops）；再與麥克風混音、限幅，寫成 48 kHz 雙聲道 PCM（AAC 仍只在串接時編一次）。回傳混音後的 wav 路徑。"""
    sys_all, mic_all = os.path.join(work, "sys.raw"), os.path.join(work, "mic.raw")
    frames = []
    est = int(total * SYNC_RATE * SYNC_FRAME_BYTES * 3)
    say(f"  影音延遲補償：暫存 PCM 約 {est / 1e9:.2f} GB（{work}）")
    with open(sys_all, "wb") as fs, open(mic_all, "wb") as fm:
        for i, (p, a) in enumerate(good, start=1):
            st, mt = track_roles(a)
            sp = extract_track(i, p, a, st, work, "sys")
            mp = extract_track(i, p, a, mt, work, "mic")
            ns, nm = os.path.getsize(sp) // SYNC_FRAME_BYTES, os.path.getsize(mp) // SYNC_FRAME_BYTES
            n = min(ns, nm)  # 兩軌同長（同一段落長）；萬一差一兩個取樣框，取短的，兩軌對齊
            with open(sp, "rb") as fi:
                copy_range(fs, fi, 0, n * SYNC_FRAME_BYTES)
            with open(mp, "rb") as fi:
                copy_range(fm, fi, 0, n * SYNC_FRAME_BYTES)
            os.remove(sp)
            os.remove(mp)
            frames.append(n)
    delays = [int(round(x["delaySeconds"] * SYNC_RATE)) for x in plan]
    ops, intervals = delay_ops(frames, delays)
    for s, e, d in intervals:
        say(f"  補償區間：串接後 {s / SYNC_RATE:.3f}–{e / SYNC_RATE:.3f} 秒，系統聲音延後 {d / SYNC_RATE:.3f} 秒")
    sys_delayed = os.path.join(work, "sys-delayed.raw")
    with open(sys_all, "rb") as src, open(sys_delayed, "wb") as dst:
        for op in ops:
            if op[0] == "zero":
                write_zeros(dst, op[1] * SYNC_FRAME_BYTES)
            else:
                copy_range(dst, src, op[1] * SYNC_FRAME_BYTES, op[2] * SYNC_FRAME_BYTES)
    os.remove(sys_all)
    mixed = os.path.join(work, "mixed.wav")
    n_total = sum(frames)
    pcm_in = ["-f", "s16le", "-ar", str(SYNC_RATE), "-ac", "2", "-channel_layout", "stereo"]
    graph = (f"[0:a][1:a]amix=inputs=2:duration=longest:normalize=0,"
             f"alimiter=limit={LIMIT}:level=0:latency=1,apad=whole_len={n_total},atrim=end_sample={n_total}[a]")
    ffmpeg(*pcm_in, "-i", sys_delayed, *pcm_in, "-i", mic_all, "-filter_complex", graph, "-map", "[a]",
           "-ar", str(SYNC_RATE), "-ac", "2", "-c:a", "pcm_s16le", "-f", "wav", mixed,
           what="延遲補償混音", step="mix", target="mixed.wav", seconds=total)
    os.remove(sys_delayed)
    os.remove(mic_all)
    return mixed


def check_norm(path, seg, a, tail_padded, tail_at=None):
    """第 3 步正規化後必須成立的條件（design.md §7.4）；不成立即 FinalizeError（結束碼 5、段落保留）。
    tail_at：有補尾時補尾幀應在的 PTS（cap）；讀不到落在那裡的影片封包就明確報錯，不以長度容差帶過（缺陷 N）。"""
    name = os.path.basename(seg)
    info = probe(path)
    if not info:
        raise FinalizeError(f"正規化結果讀不到（{name}）")
    raw = probe_packets(path)
    pk = packets_by_stream(path, pkts=raw)
    all_rows = packets_by_stream(path, keep_discard=True, pkts=raw)
    v0 = first_stream(info, "video")
    if tail_at is not None and v0 is not None:
        vp = [p for p, _ in pk.get(v0.get("index")) or []]
        if not vp or max(vp) < tail_at - 0.001:  # 1 ms：只容許時間基準換算的捨入
            got = f"{max(vp):.3f}" if vp else "無"
            raise FinalizeError(f"正規化後補尾幀沒有可讀的封包：最後一幀 {got}，應在 {tail_at:.3f}（{name}）")
    for s in info.get("streams", []):
        st = stream_start(s)
        kind = s.get("codec_type")
        if st is None or not (-0.0005 <= st <= NORM_START_MAX):
            raise FinalizeError(f"正規化後 {kind} 軌起點 {st} 不在 [0, {NORM_START_MAX}] 秒（{name}）")
        rows = pk.get(s.get("index")) or []
        if not rows:
            continue
        # 影片軌長度以「最後一幀的 PTS」計（最後一幀的長度由編碼器與 muxer 決定，串接時再設成 1 tick，
        # 第 4 步），容差 50 ms、不再加一幀（design.md §7.4 第 3 步，t6 第二輪）
        if kind == "video":
            length = max((p for p, _ in all_rows.get(s.get("index"), rows)), default=0.0)
        else:
            length = max(p + d for p, d in rows) - st
        if abs(length - a["length"]) >= NORM_LENGTH_TOL:
            raise FinalizeError(f"正規化後 {kind} 軌長 {length:.3f} 與段落長 {a['length']:.3f} 不符（{name}）")
    v = first_stream(info, "video")
    if v is None:
        raise FinalizeError(f"正規化結果沒有影片軌（{name}）")
    dts = stream_dts(raw, v.get("index"))
    if any(y <= x for x, y in zip(dts, dts[1:])):
        raise FinalizeError(f"正規化後影片 dts 不是嚴格遞增（{name}）")
    if a["video"] is not None:
        # 不得以丟幀換取遞增：至少要有「輸入影格數 − 重複 PTS 數」；解碼器若已自行錯開重複 PTS，影格可以一張不少
        want = a["video"]["frames"] - a["video"]["dups"]
        got = len(dts)
        if got < want or (not tail_padded and got > a["video"]["frames"]):
            raise FinalizeError(f"正規化後影格數 {got} 與預期 {want} 不符（{name}）")


def normalize(i, seg, a, prev_norm, work, W, H, bitrate):
    """第 3 步：一段正規化成 norm-NNNN.mov。
    時間戳：ffmpeg 預設以輸入檔最早的 start_time（＝各軌起點最小值 O）為原點、所有軌同一個原點平移，
    保留段內音影相對位置；影片晚於 O 開始時把第一幀往前延到 0，音訊晚於 O 開始時前面補靜音；
    完全相同 PTS 的重複影格只留第一個。"""
    v, audios = a["video"], a["audios"]
    dur = a["length"]
    out = os.path.join(work, f"norm-{i:04d}.mov")
    pad = f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1"
    ag = audio_graph(audios, 0 if v is not None else 1, dur)
    tail_padded, tail_at = False, None
    if v is not None:
        inputs = ["-i", seg]
        # 尾端：補尾上限 cap＝段落長−5 ms（不依連結影格率；稀疏 VFR 段的 r_frame_rate 很低，
        # 舊算法 cap＝段落長−1/fps 會讓最後一段的影片早於音訊結束，缺陷 F）。不到 cap 時以 tpad 複製
        # 最後一幀補到 cap：tpad 依解碼輸出連結的影格率補幀（必須接在 setpts 之前，setpts 之後連結
        # 影格率未知、tpad 不會補），補出的幀 PTS 落在 cap 前 CLONE_SNAP 秒內或之後的一律夾成 cap，
        # 再由 select 丟掉重複 PTS（只留第一個）。影片軌的結束點由串接時把最後一個封包設成 1 tick 決定（第 4 步）。
        # 開頭：影片晚於原點 O 開始時，第一幀往前延到 0（以第一幀往前補）。
        # 一律加 setpts（沒有改動時 setpts=PTS）：實測 h264_videotoolbox 在 -fps_mode passthrough 且濾鏡鏈
        # 沒有 setpts 時，把最後一幀的長度記成 1/av_guess_frame_rate（r_frame_rate 很大而平均影格率低時
        # 改取平均影格率，例約 0.094 秒），正規化後影片軌被拉長而超出段落長（缺陷 B）；有 setpts 時最後一幀反而是短的。
        vi = v["stream"]["index"]
        fps = link_fps(v["stream"])
        cap = tick_floor(dur - TAIL_CAP_MARGIN, v["stream"])
        last = v["last_pts"] - a["origin"]
        late = v["start"] - a["origin"] > LATE_VIDEO_MIN
        exprs = []
        vf = f"[0:{vi}]"
        # 例外：依連結影格率下一幀本來就落在段落結束（前 TAIL_SNAP 秒內）或之後、且最後一幀已在
        # 正規化容差內時，沒有缺幀、不補——補出的幀會被夾到 cap，與下一段首幀只隔 5 ms，
        # 使相鄰影格間隔小於輸入（spec §4.6.10）。稀疏 VFR（缺陷 F）的下一幀遠在段落結束前，不受影響。
        grid_reaches_end = last + 1.0 / fps >= dur - TAIL_SNAP and dur - last < NORM_LENGTH_TOL
        # 例外二（spec §4.3.3 (ii)，t6 第三輪實機 0330 場次）：最後一幀距 cap 不到 CLOSE_GAP 時不補——
        # 補到 cap 的那一幀本身就是過近間隔，再加上 cap 與下一段首幀之間的 5 ms，同一個邊界就有 2 個。
        # 這時最後一幀距段落結束 < CLOSE_GAP＋5 ms，遠在正規化容差（50 ms）內。
        if cap - last >= max(TAIL_PAD_MIN, CLOSE_GAP) and not grid_reaches_end:
            # 補幀數不只依 link_fps（r_frame_rate 可能低報，例 58 對實際 60，incident 2018）：以
            # max(link_fps, TAIL_PAD_FPS_FLOOR) 推算，多補的複製幀由下面的夾 cap＋select 去重（spec §4.4.12）
            n = int(math.ceil((cap - last) * max(fps, TAIL_PAD_FPS_FLOOR))) + 1
            vf += f"tpad=stop_mode=clone:stop={n},"
            # 只動複製幀（PTS 晚於最後一幀；原始影格一律不動）：tpad 第一個複製幀落在「最後一幀 PTS＋
            # 最後一幀長度」，之後依連結影格率；落在 cap 前 CLONE_SNAP 秒內或之後的一律夾成 cap，
            # 複製幀與 cap 之間不會有過近間隔（舊門檻 10 ms 時，0330 場次 seg-0001 的複製幀 60.000 與
            # cap 60.0133 只隔 13.3 ms）。cap 已對齊輸入 time_base 的 tick；以 round 換算成 tick，
            # 避免浮點除法截斷到前一個 tick
            exprs.append((f"gt(PTS\\,round({last:.9f}/TB))*gt(PTS*TB\\,{cap - CLONE_SNAP:.6f})",
                          f"round({cap:.9f}/TB)"))
            tail_padded, tail_at = True, cap
        if late:
            exprs.insert(0, ("eq(N\\,0)", "0"))
        e = "PTS"
        for cond, val in reversed(exprs):
            e = f"if({cond}\\,{val}\\,{e})"
        vf += f"setpts='{e}',"
        # 去重：原始影格只丟完全相同 PTS 的重複幀；補尾的複製幀（PTS 晚於最後一幀）距前一個留下的影格
        # 不到 CLOSE_GAP 的一律丟掉（spec §4.3.3 (ii)：tpad 第一個複製幀落在「最後一幀 PTS＋最後一幀長度」，
        # 最後一幀很短時會緊貼最後一幀，2254 場次 seg-0007 只隔 6.7 ms；連結影格率很高時複製幀之間也會過近）。
        # 夾到 cap 的那一幀距最後一幀 ≥ CLOSE_GAP（上面的門檻）、距其他複製幀 ≥ CLONE_SNAP，一定留下。
        keep = "gt(pts\\,prev_selected_pts)"
        if tail_padded:
            keep = (f"if(gt(pts\\,round({last:.9f}/TB))\\,"
                    f"gte((pts-prev_selected_pts)*TB\\,{CLOSE_GAP - 1e-6:.9f})\\,{keep})")
        vf += f"select='isnan(prev_selected_pts)+{keep}',{pad}"
        vf += "[v]"
        if ag is None:  # 沒有音訊的段補靜音，讓串接後音訊軌連續
            inputs += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            ag = "[1:a]anull[a]"
        encode(inputs, vf + ";" + ag, out, dur=dur, bitrate=bitrate, what=f"正規化 {os.path.basename(seg)}",
               target=step_target(seg))
    else:
        fps = 30
        if prev_norm:
            still = os.path.join(work, f"still-{i:04d}.png")
            ffmpeg("-sseof", "-0.5", "-i", prev_norm, "-update", "1", "-frames:v", "1", still,
                   what=f"取前一段最後一幀（{os.path.basename(seg)}）", step="normalize",
                   target=step_target(seg), seconds=dur)
            vin = ["-loop", "1", "-framerate", fps, "-t", f"{dur:.3f}", "-i", still]
        else:
            vin = ["-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={fps}:d={dur:.3f}"]
        encode([*vin, "-i", seg], f"[0:v]{pad}[v];{ag}", out, dur=dur, bitrate=bitrate,
               what=f"補影片 {os.path.basename(seg)}", target=step_target(seg))
        tail_padded = True
    check_norm(out, seg, a, tail_padded, tail_at)
    return out


def segment_audio_pcm(seg_path, plan_row, work_dir):
    """音訊先出（meeting-speed spec §3.2、§3.11）：一段解成 48 kHz 雙聲道 pcm_s16le 的 wav，回傳路徑。
    原點、混音、限幅、結尾補靜音都與逐段正規化相同（audio_graph；ffmpeg 以輸入檔最早的 start_time 為原點），
    -t 截在段落長。plan_row 是 analyze() 對這一段的結果（None 時這裡自己分析；增量轉錄的 worker 也呼叫這個函式）。
    步驟記為 mix（seg-NNNN）。"""
    a = plan_row if plan_row is not None else analyze(seg_path)
    if a is None:
        raise FinalizeError(f"段落讀不到可解碼的封包（{os.path.basename(seg_path)}）")
    dur = a["length"]
    stem = os.path.splitext(os.path.basename(seg_path))[0]
    out = os.path.join(work_dir, f"{stem}.pcm.wav")
    ag = audio_graph(a["audios"], 0, dur)
    if ag is None:
        src = ["-f", "lavfi", "-t", f"{dur:.6f}", "-i", "anullsrc=r=48000:cl=stereo", "-map", "0:a"]
    else:
        src = ["-i", seg_path, "-filter_complex", ag, "-map", "[a]"]
    ffmpeg(*src, "-ar", "48000", "-ac", "2", "-c:a", "pcm_s16le", "-t", f"{dur:.6f}", "-bitexact", "-f", "wav", out,
           what=f"抽音訊 {os.path.basename(seg_path)}", step="mix", target=step_target(seg_path), seconds=dur)
    return out


def join_pcm(paths, out):
    """各段 48 kHz 雙聲道 PCM wav 依序接成一個 wav（純位元組串接，不經 ffmpeg 的 concat demuxer）。"""
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SYNC_RATE)
        for p in paths:
            with wave.open(p, "rb") as r:
                if (r.getnchannels(), r.getsampwidth(), r.getframerate()) != (2, 2, SYNC_RATE):
                    raise FinalizeError(f"段落 PCM 格式不符（{os.path.basename(p)}）")
                while True:
                    b = r.readframes(1 << 18)
                    if not b:
                        break
                    w.writeframes(b)
    return out


def remux_copy(i, seg, a, pcm, work):
    """copy 路徑（design §4.2、evidence/video-spike.md §2.2）：影片 -c:v copy，第一個封包拉到 0（影片晚於原點時），
    最後一個封包的長度補到段落長（以 floor(L/TB) 換算，不累積偏移）；音訊取 segment_audio_pcm 那一段 PCM（-c:a copy）。
    步驟記為 normalize（seg-NNNN）。"""
    dur = a["length"]
    out = os.path.join(work, f"norm-{i:04d}.mov")
    vi = a["video"]["stream"]["index"]
    bsf = (f"setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,max(1\\,floor({dur:.6f}/TB)-PTS)\\,DURATION)"
           f":pts=if(eq(N\\,0)\\,0\\,PTS):dts=if(eq(N\\,0)\\,0\\,DTS)")
    ffmpeg("-i", seg, "-i", pcm, "-map", f"0:{vi}", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
           "-bsf:v", bsf, "-t", f"{dur:.6f}", "-f", "mov", out, what=f"copy remux {os.path.basename(seg)}",
           step="normalize", target=step_target(seg), seconds=dur)
    return out


def verify_video(path, total):
    """發佈後的驗證（spec §4.5；design §4.3）：整支解碼無錯（-enc_time_base demux）＋一次 ffprobe 看每條軌 dts 嚴格遞增。
    兩步都記為 concat（verify:<影片檔名>）。通過回 None；不通過回原因。逾時丟 StepTimeout。"""
    target = "verify:" + os.path.basename(path)
    chk = run_step([FFMPEG, "-v", "error", "-nostdin", "-i", path, "-enc_time_base", "demux", "-f", "null", "-"],
                   "concat", target, total)
    if chk.returncode != 0 or chk.stderr.strip():
        return f"成品無法完整解碼：{chk.stderr.strip()[-800:]}"
    r = run_step([FFPROBE, "-v", "quiet", "-show_entries", "packet=stream_index,dts_time", "-of", "json", path],
                 "concat", target, total)
    try:
        pkts = json.loads(r.stdout or "{}").get("packets") or []
    except ValueError:
        pkts = []
    for idx, kind in ((0, "影片"), (1, "音訊")):
        dts = stream_dts(pkts, idx)
        if not dts or any(y <= x for x, y in zip(dts, dts[1:])):
            return f"成品{kind}軌的封包 dts 不是嚴格遞增"
    return None


def concat_list(norms, path):
    with open(path, "w", encoding="utf-8") as f:
        for p in norms:
            f.write("file '" + p.replace("'", "'\\''") + "'\n")


def set_state_done(sess):
    """.pipeline-state.json 記 record: done（不帶 runId）：經 _record_lib.update_pipeline_state 取
    <場次>/.pipeline-state.lock 後讀後合併（meeting-speed spec §4.9）；等鎖逾時只印警告、不擋收尾。"""
    update_pipeline_state(sess, {"stages": {"record": {"status": "done"}}})


def finalize(sess):
    sess = os.path.abspath(sess)
    name = os.path.basename(sess)
    rec = os.path.join(sess, "錄音")
    tracks = os.path.join(rec, "tracks")
    if not os.path.isdir(tracks):
        print(f"✗ 這個場次沒有 錄音/tracks/：{sess}", file=sys.stderr)
        return 3
    # 收尾鎖（spec §4.28.1）：拿不到就立刻結束，不讀不寫任何其他檔（連 finalize.json 都不碰）
    # MH_FINALIZE_WAIT_LOCK=1（只有背景收尾會設，spec §6 第 156 條）時改為等鎖放開，再由 finalize_locked 的冪等判斷決定
    if not acquire_finalize_lock(tracks):
        if os.environ.get("MH_FINALIZE_WAIT_LOCK") != "1":
            print(f"✗ 這個場次正在收尾（另一個程序持有 錄音/tracks/.finalize.lock）：{sess}", file=sys.stderr)
            return 5
        wait_finalize_lock(tracks)
    try:
        return finalize_locked(sess, name, rec, tracks)
    except StepTimeout as e:
        record_timeout(tracks, e)
        print(f"✗ {e}", file=sys.stderr)
        print("  段落都還在（錄音/tracks/），可以再跑一次 meeting record finish。", file=sys.stderr)
        return 5


def record_timeout(tracks, e):
    """spec §4.28.3、§3.17：逾時寫進 finalize.json 的 timedOut（保留既有鍵，例如上次成功的 outputs）。"""
    path = os.path.join(tracks, "finalize.json")
    fin = load_json(path, None)
    if not isinstance(fin, dict):
        fin = {"schemaVersion": 1}
    secs = e.seconds
    fin["timedOut"] = {"step": e.step, "seconds": int(secs) if float(secs).is_integer() else secs}
    try:
        write_json_atomic(path, fin)
    except OSError as err:
        print(f"  ⚠ 寫不進 finalize.json：{err}", file=sys.stderr)


def finalize_jobs_policy():
    """印開始時的「收尾平行度」與 MH_FINALIZE_JOBS 的告警行，回 run_ordered 用的 jobs()：每派一段前重算
    （錄製中降為 2、退回 libx264 後為 1；spec §3.25、design R3x-D9）。"""
    global _JOBS_LAST
    raw = os.environ.get("MH_FINALIZE_JOBS")
    given = raw is not None and raw.strip() != ""
    base = finalize_jobs(raw)
    say(f"收尾平行度：{base}" + (f"（MH_FINALIZE_JOBS={raw}）" if given else ""))
    if given:
        text = raw.strip()
        if not (text.isascii() and text.isdigit() and int(text) > 0):
            say(f"⚠ MH_FINALIZE_JOBS={raw} 不是正整數，改用預設 {FINALIZE_JOBS_DEFAULT}")
        elif int(text) > FINALIZE_JOBS_MAX:
            say(f"⚠ MH_FINALIZE_JOBS={raw} 超過上限 {FINALIZE_JOBS_MAX}，改用 {FINALIZE_JOBS_MAX}")
    noted = set()

    def jobs():
        global _JOBS_LAST
        rec = base > FINALIZE_JOBS_RECORDING and recording_in_progress()
        fb = _X264_FALLBACK.is_set()
        j = finalize_jobs(raw, recording=rec, fallback=fb)
        _JOBS_LAST = finalize_jobs(raw, recording=rec)
        if rec and not fb and "recording" not in noted:
            noted.add("recording")
            say(f"錄製中，收尾平行度降為 {FINALIZE_JOBS_RECORDING}")
        return j

    _JOBS_LAST = base
    return jobs


def finalize_locked(sess, name, rec, tracks):
    segs = sorted(os.path.join(tracks, f) for f in os.listdir(tracks)
                  if f.startswith("seg-") and f.endswith(".mov"))
    if not segs:
        done = finalized_without_segments(sess, tracks)
        if done:
            copy_markers(rec, tracks)
            say(f"✓ 已完成（不重做；原始段落已在收尾時清除）：{done[0]}")
            return 0
        print(f"✗ 這個場次沒有錄製段落（seg-*.mov）：{tracks}", file=sys.stderr)
        return 3

    copy_markers(rec, tracks)  # 在 already_done 之前（已完成的場次之後才出現 markers 也要補上，§4.19.3）
    stray = unmerged_files(tracks)
    if stray and finalized_without_segments(sess, tracks) \
            and all(os.path.basename(p) in stray for p in segs):
        # 剩下的只有上次記為讀不到、搬不動而留在原處的段落：成品都在，不拿它重做
        say(f"✓ 已完成（不重做；留在 tracks/ 的段落是上次讀不到的）：{finalized_without_segments(sess, tracks)[0]}")
        return 0
    partial = finalized_with_partial_cleanup(sess, tracks, [p for p in segs if os.path.basename(p) not in stray])
    if partial:
        say(f"✓ 已完成（不重做；上次清除原始段落只刪了一部分，重試清除）：{partial[0]}")
        cleanup_segments([p for p in segs if os.path.basename(p) not in stray])
        return 0
    mode = sync_mode()
    done = already_done(sess, tracks, segs, mode)
    if done:
        say(f"✓ 已完成（不重做）：{done[0]}")
        return 0

    jobs = finalize_jobs_policy()

    # 1. 篩掉完全讀不到可解碼封包的段（讀得到部分 fragment 的段照用，spec §4.6.9、§4.6.15）；
    #    各段的 probe 與封包分析可平行（spec §3.25），結果依段號排列
    good, skipped = [], []
    for p, a in zip(segs, run_ordered(len(segs), lambda k: analyze(segs[k]), jobs=jobs)):
        if a is None:
            skipped.append(p)
            continue
        good.append((p, a))
    if skipped:
        say("⚠ 略過無法讀取的段落：" + "、".join(os.path.basename(p) for p in skipped))
    if not good:
        print("✗ 所有段落都讀不到，沒有東西可以收尾。", file=sys.stderr)
        return 3

    manifest_path = os.path.join(tracks, "manifest.json")
    manifest = load_json(manifest_path, {})
    if not isinstance(manifest, dict):
        manifest = {}
    seg_meta = {s.get("file"): s for s in manifest.get("segments") or [] if isinstance(s, dict)}

    # 2. 輸出參數（重編路徑用；copy 路徑的畫布＝canvasLock、位元率＝來源）
    sizes = []
    rates = []
    for p, a in good:
        v = a["video"]["stream"] if a["video"] else None
        if v:
            sizes.append((int(v.get("width") or 0), int(v.get("height") or 0)))
            br = num(v.get("bit_rate"))
            if br:
                rates.append(br)
        else:
            m = seg_meta.get(os.path.basename(p)) or {}
            if m.get("width") and m.get("height"):
                sizes.append((int(m["width"]), int(m["height"])))
    W = even_up(max((w for w, _ in sizes), default=1280) or 1280)
    H = even_up(max((h for _, h in sizes), default=720) or 720)
    bitrate = int(max(MIN_BITRATE, (max(rates) if rates else 0) * 1.5))

    work = os.path.join(tracks, ".finalize")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    total = sum(a["length"] for _, a in good)
    plan = sync_plan(mode, good, tracks, seg_meta)
    say(f"影音延遲補償：{mode}" + ("" if mode == "off" else "（" + "、".join(
        f"{step_target(x['file'])} {x['delaySeconds']:.3f} 秒 {x['source']}" + ("、clamped" if x["clamped"] else "")
        for x in plan) + "）"))

    fin_path = os.path.join(tracks, "finalize.json")
    fin_old = load_json(fin_path, None)
    stamp = session_stamp([p for p, _ in good], fin_old)
    base = f"{name} {stamp}"
    vid_dir = os.path.join(sess, "影片")
    video_out = os.path.join(vid_dir, base + ".mov")
    wav_out = os.path.join(rec, base + ".wav")
    use_copy, why = copy_plan(tracks, good)
    if use_copy and copy_verify_failed(fin_old):
        use_copy, why = False, "上次 copy 路徑驗證失敗，這次強制重編"
    video_path = "copy" if use_copy else "reencode"
    say("影片：copy 串接（不重新編碼）" if use_copy else f"影片：重新編碼（{why}）")
    n_good, progress, progress_lock = len(good), [0], threading.Lock()

    def progressed(out):
        with progress_lock:
            progress[0] += 1
            say(f"正規化 已完成 {progress[0]}/{n_good}")
        return out

    try:
        # 3. 音訊先出（meeting-speed spec §3.2、§4.2）：各段 PCM → 正式 wav，在任何影片步驟之前發佈。
        #    順序：audio-ready.json → finalize.json 第一階段 → os.replace 成 錄音/<同名>.wav → 印「音訊就緒：」
        comp = compensation_kind(mode, plan)
        rsegs = ready_segments(good)
        reuse = not skipped and audio_reusable(tracks, fin_old, rsegs, comp, wav_out, mode, plan)
        pcms = None
        if use_copy or (not reuse and mode == "off"):
            pcms = run_ordered(n_good, lambda k: segment_audio_pcm(good[k][0], good[k][1], work), jobs=jobs)
        # 3b. 影音延遲補償（mode≠off，ADR adr-r3-concat-then-mix.md）：兩軌各自串接、系統聲音整條連續延後、
        #     再混音成一條 PCM；正式 wav 與串接的音訊都用它。off 時不走這一步（D20 原樣）
        mixed = compensated_audio(good, plan, work, total) if mode != "off" else None
        if reuse:
            say(f"  正式 wav 與 audio-ready.json 相同，不重寫：{wav_out}")
        else:
            full = mixed or join_pcm(pcms, os.path.join(work, "audio48.wav"))
            wav_tmp = os.path.join(work, "audio.wav.part")
            ffmpeg("-i", full, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", "-f", "wav", wav_tmp,
                   what="抽 wav", step="mix", target="audio.wav", seconds=total)
            # 讀不到的段落搬到 tracks/unreadable/（spec §4.28.7；inputs 照原本記搬移前的段落清單）
            inputs = input_list(segs)
            skipped_out = [{"file": os.path.basename(p), "movedTo": move_unreadable(tracks, p, say)} for p in skipped]
            for e in skipped_out:
                if e["movedTo"]:
                    say(f"  讀不到的段落已搬到 {e['movedTo']}")
            write_json_atomic(os.path.join(tracks, "audio-ready.json"), {
                "schemaVersion": 1, "wav": os.path.basename(wav_out), "stamp": stamp, "compensation": comp,
                "segments": rsegs, "createdAt": now_iso()})
            write_json_atomic(fin_path, {
                "schemaVersion": 1, "stamp": stamp, "inputs": inputs, "skipped": skipped_out,
                "outputs": {"video": os.path.relpath(video_out, sess), "audio": os.path.relpath(wav_out, sess)},
                "syncCompensation": {"mode": mode, "segments": plan},
                "finishedAt": now_iso(), "videoPublishedAt": None, "verify": {"status": "pending"}})
            os.replace(wav_tmp, wav_out)
        say(f"音訊就緒：錄音/{os.path.basename(wav_out)}")

        # 4. 逐段處理影片（可平行，spec §3.25）：copy 路徑 remux（design §4.2）；重編路徑正規化——沒有影片的段
        #    要等前一段的 norm 完成（normalize_deps）。每完成一段印一行「正規化 已完成 k/N」（§6 第 152 條）
        if use_copy:
            norms = run_ordered(n_good, lambda k: progressed(remux_copy(k + 1, good[k][0], good[k][1], pcms[k], work)),
                                jobs=jobs)
        else:
            def normalize_one(k):
                p, a = good[k]
                prev = os.path.join(work, f"norm-{k:04d}.mov") if k > 0 else None  # 前一段（第 k 段，1 起算）的輸出
                return progressed(normalize(k + 1, p, a, prev, work, W, H, bitrate))

            norms = run_ordered(n_good, normalize_one, jobs=jobs,
                                deps=normalize_deps([a["video"] is not None for _, a in good]))

        # 5. 串接：影片 -c:v copy；音訊（各段 PCM）在這裡一次編成 AAC（缺陷 J）。不把 moov 移到檔頭（不用 faststart，spec §4.4.6）。
        #    copy 路徑加 -auto_convert 0（不在關鍵幀前插 SPS/PPS，封包與來源逐段相同），且不設最後封包 1 tick
        #    （沒有 tpad 補尾，設了影片會在最後一幀結束，evidence/video-spike.md §2.2）；重編路徑照舊把最後一個封包
        #    的長度設成 1 tick，影片軌在最後一幀的 PTS 結束（design.md §7.4 第 4 步，缺陷 F）
        lst = os.path.join(work, "concat.txt")
        concat_list(norms, lst)
        video_tmp = os.path.join(work, "video.mov")
        audio_src = [] if mixed is None else ["-i", mixed, "-map", "0:v:0", "-map", "1:a:0"]
        auto = ["-auto_convert", "0"] if use_copy else []
        last_tick = [] if use_copy else ["-bsf:v", "setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,1\\,DURATION)"]
        ffmpeg(*auto, "-f", "concat", "-safe", "0", "-i", lst, *audio_src, "-c:v", "copy",
               "-c:a", "aac", "-b:a", AAC_RATE, *last_tick, video_tmp,
               what="串接", step="concat", target="video.mov", seconds=total)
    except StepTimeout:
        raise
    except FinalizeError as e:
        print(f"✗ {e}", file=sys.stderr)
        print("  段落都還在（錄音/tracks/），修好後可以再跑一次 meeting record finish。", file=sys.stderr)
        return 5

    # 6. 影片發佈（spec §4.5.1）：rename 進 影片/ → manifest → finalize.json 第二階段 → 印「成品就緒：」→ 驗證
    os.makedirs(vid_dir, exist_ok=True)
    os.replace(video_tmp, video_out)
    shutil.rmtree(work, ignore_errors=True)
    ads = {os.path.basename(p): a["audioDuration"] for p, a in good}
    gaps = write_manifest(manifest_path, manifest, tracks, ads,
                          (W, H) if not use_copy else (int(good[0][1]["video"]["stream"]["width"]),
                                                       int(good[0][1]["video"]["stream"]["height"])),
                          bitrate if not use_copy else int(max(rates) if rates else 0))
    fin = load_json(fin_path, None)
    fin = fin if isinstance(fin, dict) else {"schemaVersion": 1}
    fin.pop("timedOut", None)
    fin.update({"videoPublishedAt": now_iso(), "videoPath": video_path,
                "verify": {"status": "pending", "path": video_path}})
    write_json_atomic(fin_path, fin)
    say(f"成品就緒：影片/{os.path.basename(video_out)}")

    # 7. 驗證（不在關鍵路徑上）：通過才記 record: done、刪段落；失敗或逾時改名 .verify-failed.mov、段落全部保留、回 5
    try:
        reason = verify_video(video_out, total)
    except StepTimeout as e:
        record_timeout(tracks, e)
        reason = str(e)
    except FinalizeError as e:
        reason = str(e)
    fin = load_json(fin_path, None)
    fin = fin if isinstance(fin, dict) else {"schemaVersion": 1}
    if reason:
        failed = os.path.join(vid_dir, base + ".verify-failed.mov")
        os.replace(video_out, failed)
        fin["verify"] = {"status": "failed", "reason": reason, "path": video_path}
        write_json_atomic(fin_path, fin)
        print(f"✗ 成品驗證沒有通過：{reason}", file=sys.stderr)
        print(f"  影片已改名為 {failed}（不刪）；正式 wav 不受影響：{wav_out}", file=sys.stderr)
        print(f"  段落都還在（錄音/tracks/），可以再跑一次 meeting record finish \"{sess}\"（上次是 copy 時改走重新編碼）。",
              file=sys.stderr)
        return 5
    fin["verify"] = {"status": "ok", "path": video_path}
    write_json_atomic(fin_path, fin)
    set_state_done(sess)
    cleanup_segments([p for p, _ in good])  # 只刪已併入成品的段落（讀不到的已搬走或留在原處，spec §6 第 126 條）
    say(f"✓ 影片：{video_out}")
    say(f"✓ 錄音：{wav_out}")
    if gaps:
        say(f"  段落空隙：最大 {max(gaps):.3f} 秒、合計 {sum(gaps):.3f} 秒")
    return 0


def main(argv):
    if len(argv) != 1 or not argv[0]:
        print("✗ 用法：_record_finalize.py <場次目錄>", file=sys.stderr)
        return 2
    if not os.path.isdir(argv[0]):
        print(f"✗ 找不到場次目錄：{argv[0]}", file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, on_sigterm)
    try:
        return finalize(argv[0])
    except (OSError, FinalizeError, SegmentAborted) as e:
        print(f"✗ 收尾失敗：{e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""parallel_ffmpeg.py —— MH_FFMPEG 的替身：記錄正規化編碼的起訖，量收尾的平行度（spec R3x §3.27、§4.55）。

轉呼叫真的 ffmpeg（PAR_FFMPEG_REAL，預設 PATH 上的 ffmpeg）；子程序與自己同一個 process group
（被 killpg 時一起結束）。

參數含 -filter_complex（正規化編碼）或 -sseof（取前一段最後一幀）時：
  - 在 PAR_FFMPEG_LOG 追加「start <pid> <kind> <seg> <time.time()>」：
      kind＝vt（參數含 h264_videotoolbox）、x264（參數含 libx264）、still（-sseof）；
      seg＝參數中 seg-NNNN 的主檔名；still 時記輸出檔的主檔名 still-NNNN；
  - 睡 PAR_FFMPEG_SECONDS（預設 0）秒；
  - PAR_FFMPEG_FAIL_SEGS（逗號分隔的主檔名）含該段、或 PAR_FFMPEG_FAIL_VT=1 而 kind 是 vt 時：
    stderr 印「parallel_ffmpeg：模擬失敗」並以 1 結束；否則執行真的 ffmpeg；
  - 結束時追加「end <pid> <kind> <seg> <time> <rc>」。
被 SIGTERM／SIGKILL 時不保證有 end 行（測試以「沒有 end 且程序已不在」判為被結束）。
其他參數直接轉呼叫、不記錄。不寫 ~/.meeting-harness，不讀 client-names.txt。
"""
import os
import re
import shutil
import subprocess
import sys
import time

SEG_RE = re.compile(r"(seg-\d{4})")
STILL_RE = re.compile(r"(still-\d{4})")


def real_ffmpeg():
    return os.environ.get("PAR_FFMPEG_REAL") or shutil.which("ffmpeg") or "ffmpeg"


def classify(args):
    """回 (kind, seg)；不需記錄時回 (None, None)。"""
    if "-sseof" in args:
        still = next((m.group(1) for a in reversed(args) for m in [STILL_RE.search(os.path.basename(a))] if m), "")
        return "still", still or "still-????"
    if "-filter_complex" in args:
        if any("h264_videotoolbox" in a for a in args):
            kind = "vt"
        elif any("libx264" in a for a in args):
            kind = "x264"
        else:
            kind = "other"
        seg = next((m.group(1) for a in args for m in [SEG_RE.search(os.path.basename(a))] if m), "")
        return kind, seg or "seg-????"
    return None, None


def log(line):
    path = os.environ.get("PAR_FFMPEG_LOG")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main(args):
    kind, seg = classify(args)
    real = real_ffmpeg()
    if kind is None:
        os.execv(real, [real, *args])
    pid = os.getpid()
    log(f"start {pid} {kind} {seg} {time.time():.6f}")
    try:
        secs = float(os.environ.get("PAR_FFMPEG_SECONDS") or 0)
    except ValueError:
        secs = 0.0
    if secs > 0:
        time.sleep(secs)
    fail_segs = {s.strip() for s in (os.environ.get("PAR_FFMPEG_FAIL_SEGS") or "").split(",") if s.strip()}
    if seg in fail_segs or (os.environ.get("PAR_FFMPEG_FAIL_VT") == "1" and kind == "vt"):
        print("parallel_ffmpeg：模擬失敗", file=sys.stderr, flush=True)
        rc = 1
    else:
        rc = subprocess.call([real, *args])   # 同一個 process group（不另開 session）
    log(f"end {pid} {kind} {seg} {time.time():.6f} {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

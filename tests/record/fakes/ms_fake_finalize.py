#!/usr/bin/env python3
"""bin/_record_finalize.py 的替身（只放進 test_ms_replay.py 在暫存區組的假 harness；meeting-speed spec §4.14.1）。

用法同正本：_record_finalize.py <場次目錄>。不跑 ffmpeg：
1. 在 FAKE_FIN_LOG 記 {"event": "start", "t", "segFiles": [tracks/ 的 seg-*.mov], "manifestSegments", "allFinished"}。
2. 睡 FAKE_FIN_AUDIO_SECONDS（預設 0.3）秒；沒設 FAKE_FIN_NO_READY 時寫 錄音/<場次名> <stamp>.wav、印「音訊就緒：錄音/<檔名>」、
   記 {"event": "ready"}。
3. 睡 FAKE_FIN_VIDEO_SECONDS（預設 2.0）秒，寫 影片/<場次名> <stamp>.mov（設了 FAKE_FIN_NO_READY 時這時才寫 wav）、
   finalize.json（videoPath＝reencode、verify ok），印「成品就緒：影片/<檔名>」、記 {"event": "video"}，回 0。
"""
import json
import os
import sys
import time
import wave

sess = os.path.abspath(sys.argv[1])
name = os.path.basename(sess)
rec = os.path.join(sess, "錄音")
tracks = os.path.join(rec, "tracks")
stamp = "2026-10-21 09.30.00"
log = os.environ.get("FAKE_FIN_LOG")


def note(event, **kw):
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(dict(event=event, t=time.time(), **kw), ensure_ascii=False) + "\n")


def write_wav(path):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 16000)


try:
    man = json.load(open(os.path.join(tracks, "manifest.json"), encoding="utf-8"))
    segs = man.get("segments") or []
except (OSError, ValueError):
    segs = []
note("start", segFiles=sorted(f for f in os.listdir(tracks) if f.startswith("seg-") and f.endswith(".mov")),
     manifestSegments=len(segs), allFinished=all(s.get("finishedAt") is not None for s in segs))
wav = os.path.join(rec, f"{name} {stamp}.wav")
time.sleep(float(os.environ.get("FAKE_FIN_AUDIO_SECONDS", "0.3")))
no_ready = os.environ.get("FAKE_FIN_NO_READY") == "1"
if not no_ready:
    write_wav(wav)
    print(f"音訊就緒：錄音/{os.path.basename(wav)}", flush=True)
    note("ready")
time.sleep(float(os.environ.get("FAKE_FIN_VIDEO_SECONDS", "2.0")))
os.makedirs(os.path.join(sess, "影片"), exist_ok=True)
mov = os.path.join(sess, "影片", f"{name} {stamp}.mov")
with open(mov, "wb") as f:
    f.write(b"\0" * 1024)
if no_ready:
    write_wav(wav)
now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
with open(os.path.join(tracks, "finalize.json"), "w", encoding="utf-8") as f:
    json.dump({"schemaVersion": 1, "stamp": stamp, "finishedAt": now, "videoPublishedAt": now, "videoPath": "reencode",
               "verify": {"status": "ok", "path": "reencode"},
               "outputs": {"video": f"影片/{os.path.basename(mov)}", "audio": f"錄音/{os.path.basename(wav)}"}}, f,
              ensure_ascii=False)
print(f"成品就緒：影片/{os.path.basename(mov)}", flush=True)
note("video")
sys.exit(0)

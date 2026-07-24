#!/usr/bin/env python3
"""_combine_audio.py <錄音_dir>
回傳該場次要用的音源路徑（印到 stdout）：
- 只有 1 個音/視訊檔 → 直接回傳它。
- 多個 → 依檔名排序，各轉 16k mono wav 後串接成 <dir>/.combined.wav（主場在前、點評在後多半符合排序），回傳它。
冪等：.combined.wav 比所有來源新就重用。CJK 路徑安全（純 Python）。
"""
import sys, os, glob, subprocess, tempfile

EXTS = ("m4a", "mp3", "wav", "mov", "mp4", "m4v")

def audio_files(rec):
    fs = []
    for e in EXTS:
        fs += glob.glob(os.path.join(rec, f"*.{e}"))
    # 排除自己產生的 .combined.wav 與隱藏檔
    fs = [f for f in fs if not os.path.basename(f).startswith(".")]
    return sorted(fs)

def main():
    rec = sys.argv[1]
    fs = audio_files(rec)
    if not fs:
        sys.exit(1)
    if len(fs) == 1:
        print(fs[0]); return
    combined = os.path.join(rec, ".combined.wav")
    if os.path.exists(combined) and os.path.getmtime(combined) >= max(os.path.getmtime(f) for f in fs):
        print(combined); return
    with tempfile.TemporaryDirectory() as tmp:
        listf = os.path.join(tmp, "list.txt")
        with open(listf, "w") as lf:
            for i, f in enumerate(fs):
                w = os.path.join(tmp, f"p{i}.wav")
                subprocess.run(["ffmpeg", "-y", "-i", f, "-ar", "16000", "-ac", "1", w],
                               capture_output=True)
                lf.write(f"file '{w}'\n")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listf,
                        "-ar", "16000", "-ac", "1", combined], capture_output=True)
    if os.path.exists(combined):
        print(combined)
    else:
        print(fs[0])  # 退回第一個

if __name__ == "__main__":
    main()

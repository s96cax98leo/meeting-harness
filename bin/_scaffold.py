#!/usr/bin/env python3
"""_scaffold.py <平坦資料夾> [--split] [--type <型態>] [--gap <分鐘>] [--dry-run]

把一個「什麼都丟在一起」的資料夾（螢幕錄影 / 錄音 / 截圖）整理成 harness 要的場次結構：

    <資料夾>/<場次名>/錄音/*.mov|m4a…
                     /照片/*.png|jpg|HEIC
                     /錄音/meeting.json   ← 草稿（type 待確認）

分場規則：依「檔案修改時間」排序，前一段結束到下一段開始的間隔 < --gap（預設 15 分鐘）
視為同一場（中途暫停/分段錄影），否則另起一場。--split 則一律一檔一場。

檔案用**硬連結**搬進去（不佔額外空間、原檔留在原地）；已存在就跳過（冪等）。
"""
import sys, os, re, json, subprocess, datetime

AUDIO_EXTS = (".mov", ".mp4", ".m4v", ".m4a", ".mp3", ".wav")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".heic", ".heif")
TS_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[ _-]+(\d{2})[.:](\d{2})[.:](\d{2})")

def duration(path):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "csv=p=0", path], capture_output=True, text=True, timeout=60)
        return float(out.stdout.strip() or 0)
    except Exception:
        return 0.0

def stamp(path):
    """優先用檔名裡的時間戳，否則用 mtime。"""
    m = TS_RE.search(os.path.basename(path))
    if m:
        try:
            return datetime.datetime(*(int(x) for x in m.groups())).timestamp()
        except ValueError:
            pass
    return os.path.getmtime(path)

def link(src, dstdir, dry):
    dst = os.path.join(dstdir, os.path.basename(src))
    if os.path.exists(dst):
        return "skip"
    if dry:                      # --dry-run 不得在磁碟上留下任何東西
        return "would-link"
    os.makedirs(dstdir, exist_ok=True)
    try:
        os.link(src, dst)          # 同一顆磁碟：硬連結，不佔空間
    except OSError:
        import shutil; shutil.copy2(src, dst)
        return "copy"
    return "link"

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr); sys.exit(2)
    root = os.path.abspath(a[0])
    split = "--split" in a
    dry = "--dry-run" in a
    mtype = a[a.index("--type") + 1] if "--type" in a else None
    gap = float(a[a.index("--gap") + 1]) * 60 if "--gap" in a else 15 * 60

    files = [os.path.join(root, f) for f in sorted(os.listdir(root))
             if os.path.isfile(os.path.join(root, f)) and not f.startswith(".")]
    audio = sorted([f for f in files if f.lower().endswith(AUDIO_EXTS)], key=stamp)
    images = sorted([f for f in files if f.lower().endswith(IMAGE_EXTS)], key=stamp)
    if not audio:
        print(f"[scaffold] {root} 沒有音／視訊檔，無事可做"); sys.exit(0)

    # 分組
    groups, cur, cur_end = [], [], None
    for f in audio:
        st = stamp(f); en = st + duration(f)
        if cur and not split and cur_end is not None and st - cur_end <= gap:
            cur.append(f)
        else:
            if cur: groups.append((cur, cur_end))
            cur = [f]
        cur_end = en
    if cur: groups.append((cur, cur_end))

    day = os.path.basename(root)
    # 圖片歸屬：一張只進一場——取「開始時間 ≤ 截圖時間」中最晚的那場（沒有就給第一場）。
    starts = [stamp(g[0]) for g, _ in groups]
    img_of = {i: [] for i in range(len(groups))}
    for im in images:
        t = stamp(im)
        idx = max((i for i, st in enumerate(starts) if st - 300 <= t), default=0)
        img_of[idx].append(im)

    for i, (grp, end) in enumerate(groups, 1):
        t0 = datetime.datetime.fromtimestamp(stamp(grp[0]))
        name = f"{t0:%H%M}場次" if len(groups) > 1 else f"{day}場次"
        sess = os.path.join(root, name)
        rec = os.path.join(sess, "錄音")
        print(f"\n── [{i}] {name}　{t0:%H:%M}–{datetime.datetime.fromtimestamp(end):%H:%M}"
              f"（{len(grp)} 個檔，共 {sum(duration(f) for f in grp)/60:.0f} 分）")
        for f in grp:
            print(f"   {link(f, rec, dry):>10}  錄音/{os.path.basename(f)}")
        # 此場的截圖 → 照片/
        for im in img_of[i - 1]:
            print(f"   {link(im, os.path.join(sess, '照片'), dry):>10}  照片/{os.path.basename(im)}")
        # meeting.json 草稿
        mj = os.path.join(rec, "meeting.json")
        if not os.path.exists(mj) and not dry:
            os.makedirs(rec, exist_ok=True)
            json.dump({"type": mtype or "internal", "date": f"{t0:%Y-%m-%d}",
                       "attendees": [], "expectedSpeakers": None, "language": "zh", "llm": "claude",
                       "_note": "type 可改：seminar/internal/client/1on1/workshop/interview；"
                                "填 attendees 可讓講者命名與人數鎖定更準"},
                      open(mj, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            print(f"        wrote  錄音/meeting.json（type={mtype or 'internal'}，待確認）")

    print(f"\n✅ 分出 {len(groups)} 場。確認 meeting.json 的 type／attendees 後執行：")
    print(f'    bash bin/meeting.sh "{root}"')

if __name__ == "__main__":
    main()

"""_finalize_state.py — 收尾的檔案狀態：冪等判斷、讀不到的段落、markers、時間戳、gapStats、audio-ready.json、
copy 條件、manifest 寫回（meeting-speed spec §4.13；由 _record_finalize.py 搬出，行為不變）。不啟動子程序。"""
import datetime
import os
import tempfile

from _finalize_media import num
from _finalize_sync import SYNC_MODES
from _record_lib import load_json, paused_total, write_json_atomic

UNREADABLE_DIR = "unreadable"


def skipped_entries(fin):
    """spec §3.17：finalize.json 的 skipped[]；舊場次的字串 "x" 視同 {"file": "x", "movedTo": null}。"""
    raw = fin.get("skipped") if isinstance(fin, dict) else None
    out = []
    for e in raw if isinstance(raw, list) else []:
        if isinstance(e, str):
            out.append({"file": e, "movedTo": None})
        elif isinstance(e, dict) and isinstance(e.get("file"), str):
            mv = e.get("movedTo")
            out.append({"file": e["file"], "movedTo": mv if isinstance(mv, str) else None})
    return out


def recorded_inputs(fin):
    """finalize.json 的 inputs，扣掉已搬進 tracks/unreadable/ 的段落（它們不再出現在 tracks/seg-*.mov）。"""
    moved = {e["file"] for e in skipped_entries(fin) if e["movedTo"]}
    return [{"file": d.get("file"), "size": d.get("size")} for d in (fin or {}).get("inputs") or []
            if isinstance(d, dict) and d.get("file") not in moved]


def move_unreadable(tracks, path, log=print):
    """spec §4.28.7：讀不到的段落搬到 tracks/unreadable/（同名，撞名加 -1、-2；不覆蓋既有的檔）。
    回傳相對 錄音/ 的路徑；搬移失敗回 None（段落留在原處）。"""
    name = os.path.basename(path)
    dest_dir = os.path.join(tracks, UNREADABLE_DIR)
    stem, ext = os.path.splitext(name)
    try:
        os.makedirs(dest_dir, exist_ok=True)
        for k in range(0, 1000):
            cand = name if k == 0 else f"{stem}-{k}{ext}"
            dst = os.path.join(dest_dir, cand)
            if os.path.lexists(dst):
                continue
            try:
                os.link(path, dst)   # 不覆蓋：目的地已存在就失敗（FileExistsError），換下一個名字
                os.remove(path)
            except FileExistsError:
                continue
            except OSError:
                if os.path.lexists(dst):
                    continue
                os.rename(path, dst)
            return "/".join(("tracks", UNREADABLE_DIR, cand))
    except OSError as e:
        log(f"  ⚠ 搬不動 {name} 到 tracks/{UNREADABLE_DIR}/：{e}")
    return None


def finalized_without_segments(sess, tracks):
    """原始段落已在收尾成功後刪掉：finalize.json 記的成品都還在 → 已完成。"""
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    if not isinstance(fin, dict):
        return None
    outs = fin.get("outputs") or {}
    paths = [os.path.join(sess, outs.get(k, "")) for k in ("video", "audio")]
    if all(outs.get(k) for k in ("video", "audio")) and all(os.path.isfile(p) for p in paths):
        return paths
    return None


def finalized_with_partial_cleanup(sess, tracks, segs):
    """上次收尾成功、清除段落時只刪掉一部分：剩下的段落是 finalize.json 輸入的真子集、成品都在。
    這時不得用殘缺的段落重做收尾、覆蓋好的成品（ultrareview）。"""
    done = finalized_without_segments(sess, tracks)
    if not done:
        return None
    fin = load_json(os.path.join(tracks, "finalize.json"), None) or {}
    recorded = [(d["file"], d["size"]) for d in recorded_inputs(fin)]
    now = [(d["file"], d["size"]) for d in input_list(segs)]
    if now and len(now) < len(recorded) and set(now) <= set(recorded):
        return done
    return None


def unmerged_files(tracks):
    """上次收尾記為讀不到、仍留在原處的段落（搬移失敗）：不是成品的一部分，清除段落時不得刪（spec §4.28.7）。"""
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    return {e["file"] for e in skipped_entries(fin) if not e["movedTo"]}


def input_list(segs):
    return [{"file": os.path.basename(p), "size": os.path.getsize(p)} for p in segs]


def finalized_mode(fin):
    """上次收尾用的影音延遲補償 mode；R2 以前的場次（沒有 syncCompensation）視為 off。"""
    sc = fin.get("syncCompensation") if isinstance(fin, dict) else None
    m = sc.get("mode") if isinstance(sc, dict) else None
    return m if m in SYNC_MODES else "off"


def already_done(sess, tracks, segs, mode="off"):
    """段落還在時的冪等判斷；mode 與上次收尾不同時不算已完成（ADR adr-r3-sync-compensation.md：
    保留段落時可換 mode 重跑收尾比較）。"""
    fin = load_json(os.path.join(tracks, "finalize.json"), None)
    if not isinstance(fin, dict) or finalized_mode(fin) != mode:
        return None
    # meeting-speed spec §4.3.4：驗證沒有通過（failed，或驗證中斷而停在 pending）不算完成；沒有 verify 鍵的舊檔算通過
    verify = fin.get("verify")
    if isinstance(verify, dict) and verify.get("status") != "ok":
        return None
    # 音訊先出的第一階段（videoPublishedAt: null）＝影片還沒發佈：outputs.video 可能是上一次留下的同名影片，
    # 不得算完成（與 record.sh、AbnormalStop.swift 同判準）；沒有這個鍵的舊 schema 照舊判斷
    if "videoPublishedAt" in fin and fin["videoPublishedAt"] is None:
        return None
    outs = fin.get("outputs") or {}
    paths = [os.path.join(sess, outs.get(k, "")) for k in ("video", "audio")]
    if all(outs.get(k) for k in ("video", "audio")) and all(os.path.isfile(p) for p in paths) \
            and recorded_inputs(fin) == input_list(segs):
        return paths
    return None


def write_bytes_atomic(path, data):
    """同目錄 tempfile.mkstemp 建暫存檔，寫完 rename（spec §4.28.2；不用固定後綴，兩個寫者不會撞同一個暫存檔）。"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(path)),
                               prefix="." + os.path.basename(path) + ".", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def copy_markers(rec, tracks):
    """spec §3.12、§4.19.3：tracks/markers.json 原樣複製成 錄音/markers.json；內容相同就不重寫（mtime 不變）。"""
    src = os.path.join(tracks, "markers.json")
    if not os.path.isfile(src):
        return
    dst = os.path.join(rec, "markers.json")
    with open(src, "rb") as f:
        data = f.read()
    try:
        with open(dst, "rb") as f:
            if f.read() == data:
                return
    except OSError:
        pass
    write_bytes_atomic(dst, data)


def session_stamp(segs, fin_old):
    """輸出檔名的時間戳：沿用上次 finalize.json 的值，否則取第一段的建立時間（≈開錄時間）。"""
    if isinstance(fin_old, dict) and isinstance(fin_old.get("stamp"), str):
        return fin_old["stamp"]
    st = os.stat(segs[0])
    t = getattr(st, "st_birthtime", None) or st.st_mtime
    return datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d %H.%M.%S")


def pause_events_of(tracks):
    """record.meta.json 的 pauseEvents（R2，§3.11）；沒有或格式不對 → []。"""
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    ev = meta.get("pauseEvents") if isinstance(meta, dict) else None
    return [e for e in ev if isinstance(e, dict)] if isinstance(ev, list) else []


def has_pause_events_key(tracks):
    """record.meta.json 有 pauseEvents 鍵（R2 錄製器開錄就寫 []）。"""
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    return isinstance(meta, dict) and "pauseEvents" in meta


def pause_length_before(events, resume_t):
    """邊界上那筆 resume 的暫停長度（resume.t − 前一筆 pause.t）；找不到前導 pause → 0。"""
    for k, e in enumerate(events):
        if e.get("kind") == "resume" and num(e.get("t")) == resume_t:
            for prev in reversed(events[:k]):
                if prev.get("kind") == "pause" and num(prev.get("t")) is not None:
                    return resume_t - num(prev["t"])
                if prev.get("kind") == "resume":
                    return 0.0
            return 0.0
    return 0.0


def boundary_gaps(used, events):
    """spec §3.2＋§3.11：g_k＝startedAt_{k+1} − startedAt_k − audioDuration_k；暫停邊界（有 resume.t 與
    startedAt_{k+1} 相差 < 0.5 秒）再扣掉該次暫停長度。"""
    resumes = [num(e.get("t")) for e in events if e.get("kind") == "resume" and num(e.get("t")) is not None]
    gaps = []
    for k in range(len(used) - 1):
        nxt = used[k + 1]["startedAt"]
        g = nxt - used[k]["startedAt"] - used[k]["audioDuration"]
        near = [r for r in resumes if abs(r - nxt) < 0.5]
        if near:
            r = min(near, key=lambda x: abs(x - nxt))
            g -= pause_length_before(events, r)
        gaps.append(round(g, 3))
    return gaps


def ready_segments(good):
    """audio-ready.json 的 segments：檔名、大小、段長（finalize 採用的長度）、成品時間軸起點（＝前面各段 duration 的和）。"""
    out, start = [], 0.0
    for p, a in good:
        d = round(a["length"], 3)
        out.append({"file": os.path.basename(p), "size": os.path.getsize(p), "duration": d, "start": round(start, 3)})
        start += d
    return out


def audio_reusable(tracks, fin_old, rsegs, comp, wav_out, mode, plan):
    """spec §4.3.2：audio-ready.json 的段落清單與補償和這次相同、正式 wav 在、finalize.json 第一階段在 → 音訊不重寫。"""
    ready = load_json(os.path.join(tracks, "audio-ready.json"), None)
    if not isinstance(ready, dict) or not isinstance(fin_old, dict):
        return False
    return (ready.get("segments") == rsegs and ready.get("compensation") == comp
            and ready.get("wav") == os.path.basename(wav_out) and os.path.isfile(wav_out)
            and bool(fin_old.get("finishedAt"))
            and fin_old.get("syncCompensation") == {"mode": mode, "segments": plan})


def copy_plan(tracks, good):
    """spec §4.4.3：copy 路徑的條件全部成立回 (True, "")；否則 (False, 原因)，整場走重編。"""
    meta = load_json(os.path.join(tracks, "record.meta.json"), {})
    lock = meta.get("canvasLock") if isinstance(meta, dict) else None
    if not (isinstance(lock, dict) and all(isinstance(lock.get(k), int) and not isinstance(lock.get(k), bool)
                                           for k in ("width", "height"))):
        return False, "record.meta.json 沒有 canvasLock"
    want = (lock["width"], lock["height"])
    params, hashes = set(), set()
    for p, a in good:
        name = os.path.basename(p)
        v = a["video"]
        if v is None:
            return False, f"{name} 沒有影片"
        st = v["stream"]
        got = (int(st.get("width") or 0), int(st.get("height") or 0))
        if got != want:
            return False, f"{name} 尺寸 {got[0]}×{got[1]} 不等於畫布 {want[0]}×{want[1]}"
        if v["dups"]:
            return False, f"{name} 有完全相同 PTS 的重複影格"
        params.add(tuple(st.get(k) for k in ("codec_name", "profile", "pix_fmt", "time_base")))
        hashes.add(st.get("extradata_hash"))
    if len(params) != 1:
        return False, "各段的 codec／profile／pix_fmt／time_base 不一致"
    if len(hashes) != 1 or None in hashes:
        return False, "各段的 extradata 不一致"
    return True, ""


def copy_verify_failed(fin):
    """spec §4.5.4：上一次是 copy 路徑而驗證失敗。"""
    v = fin.get("verify") if isinstance(fin, dict) else None
    return isinstance(v, dict) and v.get("status") == "failed" and v.get("path") == "copy"


def write_manifest(manifest_path, manifest, tracks, ads, canvas, bitrate):
    """manifest.json 寫回各段 audioDuration、gapStats（R2：暫停邊界扣暫停長度、pausedTotal，spec §3.11）、
    outputCanvas、outputVideoBitrate（copy 路徑＝各段影片位元率的最大值，spec §3.4）；其他鍵不動。回 gaps。"""
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    for s in segments:
        if isinstance(s, dict) and s.get("file") in ads:
            s["audioDuration"] = round(ads[s["file"]], 3) if ads[s["file"]] is not None else None
    used = [s for s in segments if isinstance(s, dict) and s.get("file") in ads
            and num(s.get("startedAt")) is not None and s.get("audioDuration") is not None]
    pevents = pause_events_of(tracks)
    gaps = boundary_gaps(used, pevents)
    wall = num(segments[-1].get("finishedAt")) if segments and isinstance(segments[-1], dict) else None
    if wall is None:
        wall = round(sum(a for a in ads.values() if a), 3)
    manifest["gapStats"] = {"boundaries": gaps, "max": max(gaps) if gaps else 0.0,
                            "total": round(sum(gaps), 3), "wallClock": wall}
    # pausedTotal 只寫給 R2 錄製器的場次（meta 有 pauseEvents 鍵）；第一輪場次維持 4 個鍵（spec §6 第 100 條）
    if has_pause_events_key(tracks):
        manifest["gapStats"]["pausedTotal"] = paused_total(pevents)
    manifest["outputCanvas"] = {"width": canvas[0], "height": canvas[1]}
    manifest["outputVideoBitrate"] = bitrate
    write_json_atomic(manifest_path, manifest)
    return gaps

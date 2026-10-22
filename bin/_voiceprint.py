#!/usr/bin/env python3
"""_voiceprint.py — 跨會議聲紋庫（vault/voiceprints/）。

用途：同一批人常常每週開會。第一次由你確認「SPEAKER_01 就是 Kevin」之後，
把該講者的語者向量存起來，往後每場自動比對，同一個人直接標名字。

用法：
  _voiceprint.py match <場次目錄> [--embeddings <路徑>] [--harness <根>]
        用語者向量比對聲紋庫，命中就寫進 錄音/speakers.map.json。向量來源：--embeddings
        （diarize.sh 的暫存檔）；沒給時讀舊場次的 錄音/embeddings.json（只讀）
  _voiceprint.py add <場次目錄> <SPEAKER_xx> <姓名> [--embeddings <路徑>] [--harness <根>]
        把該講者的向量存進聲紋庫（同名已存在則累積平均）。向量來源依序：--embeddings →
        舊場次的 錄音/embeddings.json（只讀）→ 用 diarize venv 跑 _diarize_pyannote.py --embed-speaker
        重算到暫存檔（建檔後刪除；venv 不在回 2）
  _voiceprint.py list [--harness <根>]
  _voiceprint.py remove <姓名> [--harness <根>]

原則：
- **只有人工確認過的對應才 add**。自動建檔等於把猜錯的名字變成長期汙染。
- 比對結果一律附 confidence（＝餘弦相似度）與證據字串；
  ≥0.75 才會被 _merge_speakers.py 採用改名，0.60–0.75 只當線索留著。
- 聲紋是生物特徵資料：只存在本機 vault/（不進版控），可隨時 remove。
- 語者向量不落場次資料夾（meeting-speed spec §4.6.1、§4.6.4）：只讀舊場次留下的 embeddings.json，從不寫它。
- 人工確認不被覆蓋（§4.6.3）：speakers.map 既有值是非空字串、或 evidence 不以「聲紋庫比對」開頭的 dict，
  match 一律保留；只有上一次聲紋比對寫的 dict 可被信心更高的新結果取代。
"""
import sys, os, json, math, datetime, shlex, subprocess, tempfile

RENAME_TH_DEFAULT = 0.75   # 這之上才改名（_merge_speakers.py 的門檻是 0.7，留一點餘裕）
HINT_TH_DEFAULT = 0.60     # 這之上留作線索

def harness_config(section):
    """讀 repo 根的 config.json 的某一段（讀不到回 {}）；環境變數仍優先於這裡的值。"""
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f).get(section)
        return v if isinstance(v, dict) else {}
    except (OSError, ValueError):
        return {}


_VP = harness_config("voiceprint")
RENAME_TH = float(_VP.get("renameThreshold", RENAME_TH_DEFAULT))
HINT_TH = float(_VP.get("hintThreshold", HINT_TH_DEFAULT))
ENABLED = _VP.get("enabled", True) is not False

def vault_dir(harness):
    return os.path.join(harness, "vault", "voiceprints")

def load_prints(harness):
    d = vault_dir(harness)
    out = {}
    if not os.path.isdir(d):
        return out
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            rec = json.load(open(os.path.join(d, fn), encoding="utf-8"))
            if rec.get("vector"):
                out[rec.get("name") or fn[:-5]] = rec
        except Exception as e:
            print(f"[voiceprint] 略過壞檔 {fn}：{e}", file=sys.stderr)
    return out

def cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

VOICEPRINT_EVIDENCE = "聲紋庫比對"   # match 寫的 evidence 一律以此開頭；用來分辨「上一次聲紋比對」與人工填的


def load_embeddings(path):
    """讀語者向量檔（{"speakers": {SPEAKER_xx: [...]}}），讀不到回 {}。只讀不寫。"""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            sp = (json.load(f) or {}).get("speakers", {})
        return sp if isinstance(sp, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def legacy_embeddings_path(sess):
    """舊場次（meeting-speed 之前）留在場次資料夾的向量檔；新流程不再產生它。"""
    return os.path.join(sess, "錄音", "embeddings.json")


def session_embeddings(sess, embeddings=None):
    return load_embeddings(embeddings if embeddings else legacy_embeddings_path(sess))


def is_protected(prev):
    """人工／agent 填的對應：非空字串，或 evidence 不以「聲紋庫比對」開頭的 dict。match 不得覆蓋。"""
    if isinstance(prev, str):
        return bool(prev.strip())
    if isinstance(prev, dict):
        return not str(prev.get("evidence") or "").startswith(VOICEPRINT_EVIDENCE)
    return False


def prev_name(prev):
    if isinstance(prev, str):
        return prev.strip()
    if isinstance(prev, dict):
        return str(prev.get("name") or "").strip()
    return ""


def prev_confidence(prev):
    try:
        return float(prev.get("confidence", 0))
    except (TypeError, ValueError):
        return 0.0

def cmd_match(sess, harness, embeddings=None):
    if not ENABLED:   # config.json voiceprint.enabled=false：不比對（生物特徵資料，使用者可關掉）
        print(json.dumps({"status": "skip", "reason": "config.json 的 voiceprint.enabled 是 false"},
                         ensure_ascii=False)); return 0
    emb = session_embeddings(sess, embeddings)
    if not emb:
        reason = (f"語者向量檔讀不到或是空的：{embeddings}" if embeddings
                  else "沒有語者向量（用 --embeddings 指定；舊場次才有 錄音/embeddings.json）")
        print(json.dumps({"status": "skip", "reason": reason}, ensure_ascii=False)); return 0
    prints = load_prints(harness)
    if not prints:
        print(json.dumps({"status": "skip", "reason": "聲紋庫是空的（用 voiceprint add 建檔）"},
                         ensure_ascii=False)); return 0

    mp = os.path.join(sess, "錄音", "speakers.map.json")
    existing = {}
    if os.path.isfile(mp):
        try: existing = json.load(open(mp, encoding="utf-8")) or {}
        except Exception: existing = {}

    matched, hints = [], []
    # 人工確認過的講者整個跳過；它的名字也不再派給別的 SPEAKER（同一個人不會同時是兩個 SPEAKER）
    protected = {tag for tag, prev in existing.items() if is_protected(prev)}
    reserved = {prev_name(existing[tag]) for tag in protected} - {""}
    # 全域依信心由高到低指派（ultrareview）：同一個名字只給信心最高的 SPEAKER，
    # 被搶走的 SPEAKER 還可以拿自己的次佳名字；不再依 embeddings.json 的順序先到先得
    pairs = sorted(((cosine(vec, rec["vector"]), tag, name)
                    for tag, vec in emb.items() for name, rec in prints.items()),
                   key=lambda x: -x[0])
    used, done_tags = set(reserved), set(protected)
    for best_cos, tag, best in pairs:
        if best_cos < HINT_TH:
            break
        if tag in done_tags or best in used:      # 同一個人不會同時是兩個 SPEAKER
            continue
        done_tags.add(tag)
        src = prints[best].get("sources", ["?"])[0]
        # apply 明確標出「這個名字可不可以直接套用」。
        # 不用信心值自己去撞下游門檻——_merge_speakers.py 的門檻是 0.7，
        # 但聲紋比對要到 0.75 才算數，中間那段（0.70–0.75）如果只丟信心值過去會被誤用。
        entry = {"name": best, "confidence": round(best_cos, 3),
                 "apply": best_cos >= RENAME_TH,
                 "evidence": f"{VOICEPRINT_EVIDENCE}（cos {best_cos:.2f}，聲紋建於 {src}）"
                             + ("" if best_cos >= RENAME_TH else "——信心不足，僅供人工/agent 參考，未套用")}
        # 上一次聲紋比對寫的 dict：新結果信心更高才取代（人工填的已在 protected 跳過）
        prev = existing.get(tag)
        if isinstance(prev, dict) and prev_confidence(prev) >= best_cos:
            continue
        existing[tag] = entry
        used.add(best)
        (matched if best_cos >= RENAME_TH else hints).append(f"{tag}={best}({best_cos:.2f})")

    if matched or hints:
        json.dump(existing, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "renamed": matched, "hintsOnly": hints,
                      "mapPath": mp if (matched or hints) else None}, ensure_ascii=False))
    return 0

def diarize_venv():
    return os.path.expanduser(os.environ.get("MH_DIARIZE_VENV") or "~/.meeting-harness/diarize-venv")


def session_audio(sess):
    """該場的音源：交給同目錄的 _combine_audio.py（子程序，不 import；與 diarize.sh 同一個音源）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        r = subprocess.run([sys.executable, os.path.join(here, "_combine_audio.py"), os.path.join(sess, "錄音")],
                           capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.SubprocessError):
        return ""
    out = (r.stdout or "").strip().splitlines()
    return out[-1].strip() if r.returncode == 0 and out else ""


def recompute_vector(sess, tag):
    """用 diarize venv 跑 _diarize_pyannote.py --embed-speaker，把該講者向量算到暫存檔、讀出後刪掉。
    回 (向量 or None, 錯誤訊息)。測試可用 MH_EMBED_SPEAKER_CMD 取代指令（替身）。"""
    vpy = os.path.join(diarize_venv(), "bin", "python")
    if not os.access(vpy, os.X_OK):
        here = os.path.dirname(os.path.abspath(__file__))
        return None, (f"✗ 此場次沒有 {tag} 的語者向量，重算需要分離環境（{diarize_venv()} 不在）；"
                      f"先： bash {os.path.join(here, 'setup-diarize.sh')}")
    diar = os.path.join(sess, "錄音", "diarization.json")
    if not os.path.isfile(diar):
        return None, "✗ 此場次沒有 錄音/diarization.json，先跑 meeting.sh diarize <場次> 再建檔"
    audio = session_audio(sess)
    if not audio:
        return None, f"✗ 找不到此場次的音檔（{os.path.join(sess, '錄音')}）"
    custom = os.environ.get("MH_EMBED_SPEAKER_CMD", "").strip()
    here = os.path.dirname(os.path.abspath(__file__))
    cmd = shlex.split(custom) if custom else [vpy, os.path.join(here, "_diarize_pyannote.py")]
    fd, tmp = tempfile.mkstemp(prefix="mh-embed-", suffix=".json")
    os.close(fd)
    try:
        print(f"[voiceprint] 重算 {tag} 的語者向量（不寫進場次資料夾）…", file=sys.stderr)
        r = subprocess.run(cmd + ["--embed-speaker", audio, diar, tag, tmp], text=True)
        if r.returncode != 0:
            return None, f"✗ 重算 {tag} 的語者向量失敗（exit={r.returncode}）"
        try:
            with open(tmp, encoding="utf-8") as f:
                d = json.load(f) or {}
        except (OSError, ValueError):
            d = {}
        vec = d.get("vector") or (d.get("speakers") or {}).get(tag)
        if not vec:
            return None, f"✗ 重算結果沒有 {tag} 的語者向量"
        return [float(x) for x in vec], ""
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def cmd_add(sess, tag, name, harness, embeddings=None):
    emb = session_embeddings(sess, embeddings)
    if tag in emb:
        vec = [float(x) for x in emb[tag]]
    elif embeddings:
        print(f"✗ {embeddings} 沒有 {tag} 的語者向量（有的是：{', '.join(sorted(emb)) or '無'}）",
              file=sys.stderr); return 2
    else:
        vec, err = recompute_vector(sess, tag)
        if vec is None:
            print(err, file=sys.stderr); return 2
    d = vault_dir(harness); os.makedirs(d, exist_ok=True)
    safe = name.replace("/", "_").strip()
    p = os.path.join(d, f"{safe}.json")
    src = os.path.basename(sess)
    if os.path.isfile(p):
        rec = json.load(open(p, encoding="utf-8"))
        n = int(rec.get("samples", 1))
        old = rec["vector"]
        if len(old) != len(vec):   # 換了分離模型：維度不同不得硬平均（zip 會靜默截斷，ultrareview）
            print(f"✗ {name} 的聲紋是 {len(old)} 維，這個場次的語者向量是 {len(vec)} 維（分離模型不同）；"
                  f"先 voiceprint remove {name} 再重新建檔", file=sys.stderr)
            return 2
        rec["vector"] = [(o * n + v) / (n + 1) for o, v in zip(old, vec)]   # 累積平均
        rec["samples"] = n + 1
        rec.setdefault("sources", []).append(src)
        rec["updated"] = datetime.date.today().isoformat()
        action = "更新"
    else:
        rec = {"name": name, "vector": vec, "dim": len(vec), "samples": 1,
               "sources": [src], "created": datetime.date.today().isoformat(),
               "updated": datetime.date.today().isoformat()}
        action = "建立"
    json.dump(rec, open(p, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✓ 已{action}聲紋：{name}（{tag} @ {src}，累積 {rec['samples']} 場，{rec['dim']} 維）")
    print(f"  檔案：{p}（本機、不進版控，可隨時用 voiceprint remove 刪除）")
    return 0

def cmd_list(harness):
    prints = load_prints(harness)
    if not prints:
        print("（聲紋庫是空的）"); return 0
    print(f"聲紋庫：{vault_dir(harness)}")
    for name, rec in sorted(prints.items()):
        print(f"  • {name:<16} {rec.get('samples',1)} 場　{rec.get('dim')} 維　"
              f"更新 {rec.get('updated','?')}　來源 {', '.join(rec.get('sources',[])[:3])}")
    return 0

def cmd_remove(name, harness):
    # 名稱只能是 vault/voiceprints/ 底下的單一檔名：拒絕路徑分隔、. / ..，以及解析後跑出目錄的
    d = os.path.realpath(vault_dir(harness))
    p = os.path.join(vault_dir(harness), f"{name}.json")
    bad = (not name.strip() or name in (".", "..") or "/" in name or os.sep in name
           or (os.altsep and os.altsep in name) or "\0" in name
           or os.path.dirname(os.path.realpath(p)) != d)
    if bad:
        print(f"✗ 不接受這個名稱（不得含路徑分隔或 ..，只能是 vault/voiceprints/ 裡的聲紋名）：{name}",
              file=sys.stderr); return 2
    if not os.path.isfile(p):
        print(f"✗ 聲紋庫裡沒有：{name}", file=sys.stderr); return 2
    os.remove(p); print(f"✓ 已刪除聲紋：{name}"); return 0

def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__, file=sys.stderr); sys.exit(2)
    harness = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "--harness" in a:
        i = a.index("--harness"); harness = os.path.abspath(a[i + 1]); del a[i:i + 2]
    embeddings = None
    if "--embeddings" in a:
        i = a.index("--embeddings")
        if i + 1 >= len(a):
            print(__doc__, file=sys.stderr); sys.exit(2)
        embeddings = os.path.abspath(a[i + 1]); del a[i:i + 2]
    cmd = a[0]
    if cmd == "match" and len(a) >= 2:      sys.exit(cmd_match(os.path.abspath(a[1]), harness, embeddings))
    if cmd == "add" and len(a) >= 4:        sys.exit(cmd_add(os.path.abspath(a[1]), a[2], a[3], harness, embeddings))
    if cmd == "list":                       sys.exit(cmd_list(harness))
    if cmd == "remove" and len(a) >= 2:     sys.exit(cmd_remove(a[1], harness))
    print(__doc__, file=sys.stderr); sys.exit(2)

if __name__ == "__main__":
    main()

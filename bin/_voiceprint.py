#!/usr/bin/env python3
"""_voiceprint.py — 跨會議聲紋庫（vault/voiceprints/）。

用途：同一批人常常每週開會。第一次由你確認「SPEAKER_01 就是 Kevin」之後，
把該講者的語者向量存起來，往後每場自動比對，同一個人直接標名字。

用法：
  _voiceprint.py match <場次目錄> [--harness <根>]
        用該場的 錄音/embeddings.json 比對聲紋庫，命中就寫進 錄音/speakers.map.json
  _voiceprint.py add <場次目錄> <SPEAKER_xx> <姓名> [--harness <根>]
        把該講者的向量存進聲紋庫（同名已存在則累積平均）
  _voiceprint.py list [--harness <根>]
  _voiceprint.py remove <姓名> [--harness <根>]

原則：
- **只有人工確認過的對應才 add**。自動建檔等於把猜錯的名字變成長期汙染。
- 比對結果一律附 confidence（＝餘弦相似度）與證據字串；
  ≥0.75 才會被 _merge_speakers.py 採用改名，0.60–0.75 只當線索留著。
- 聲紋是生物特徵資料：只存在本機 vault/（不進版控），可隨時 remove。
"""
import sys, os, json, math, datetime

RENAME_TH = 0.75   # 這之上才改名（_merge_speakers.py 的門檻是 0.7，留一點餘裕）
HINT_TH = 0.60     # 這之上留作線索

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

def session_embeddings(sess):
    p = os.path.join(sess, "錄音", "embeddings.json")
    if not os.path.isfile(p):
        return {}
    return (json.load(open(p, encoding="utf-8")) or {}).get("speakers", {})

def cmd_match(sess, harness):
    emb = session_embeddings(sess)
    if not emb:
        print(json.dumps({"status": "skip", "reason": "此場次沒有 錄音/embeddings.json"},
                         ensure_ascii=False)); return 0
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
    used = set()
    for tag, vec in emb.items():
        best, best_cos = None, 0.0
        for name, rec in prints.items():
            c = cosine(vec, rec["vector"])
            if c > best_cos:
                best_cos, best = c, name
        if not best or best_cos < HINT_TH:
            continue
        if best in used:      # 同一個人不會同時是兩個 SPEAKER
            continue
        src = prints[best].get("sources", ["?"])[0]
        # apply 明確標出「這個名字可不可以直接套用」。
        # 不用信心值自己去撞下游門檻——_merge_speakers.py 的門檻是 0.7，
        # 但聲紋比對要到 0.75 才算數，中間那段（0.70–0.75）如果只丟信心值過去會被誤用。
        entry = {"name": best, "confidence": round(best_cos, 3),
                 "apply": best_cos >= RENAME_TH,
                 "evidence": f"聲紋庫比對（cos {best_cos:.2f}，聲紋建於 {src}）"
                             + ("" if best_cos >= RENAME_TH else "——信心不足，僅供人工/agent 參考，未套用")}
        # 人工／agent 已經填過且信心更高的就不覆蓋
        prev = existing.get(tag)
        if isinstance(prev, dict) and float(prev.get("confidence", 0)) >= best_cos:
            continue
        existing[tag] = entry
        used.add(best)
        (matched if best_cos >= RENAME_TH else hints).append(f"{tag}={best}({best_cos:.2f})")

    if matched or hints:
        json.dump(existing, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(json.dumps({"status": "ok", "renamed": matched, "hintsOnly": hints,
                      "mapPath": mp if (matched or hints) else None}, ensure_ascii=False))
    return 0

def cmd_add(sess, tag, name, harness):
    emb = session_embeddings(sess)
    if tag not in emb:
        print(f"✗ 此場次沒有 {tag} 的語者向量（有的是：{', '.join(sorted(emb)) or '無'}）",
              file=sys.stderr); return 2
    d = vault_dir(harness); os.makedirs(d, exist_ok=True)
    safe = name.replace("/", "_").strip()
    p = os.path.join(d, f"{safe}.json")
    vec = [float(x) for x in emb[tag]]
    src = os.path.basename(sess)
    if os.path.isfile(p):
        rec = json.load(open(p, encoding="utf-8"))
        n = int(rec.get("samples", 1))
        old = rec["vector"]
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
    p = os.path.join(vault_dir(harness), f"{name}.json")
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
    cmd = a[0]
    if cmd == "match" and len(a) >= 2:      sys.exit(cmd_match(os.path.abspath(a[1]), harness))
    if cmd == "add" and len(a) >= 4:        sys.exit(cmd_add(os.path.abspath(a[1]), a[2], a[3], harness))
    if cmd == "list":                       sys.exit(cmd_list(harness))
    if cmd == "remove" and len(a) >= 2:     sys.exit(cmd_remove(a[1], harness))
    print(__doc__, file=sys.stderr); sys.exit(2)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""summarize-local.py <session_dir> <harness_dir> [--mode talk|meeting|panel]
                       [--model M] [--title T] [--speaker S] [--agenda FILE] [--event E]

本機總結器：用 ollama 本地模型（預設 Qwen3.5-35B-mlx）把逐字稿(+投影片+講者分離)寫成
繁體中文結構化 summary.md。長稿自動 map-reduce。內容完全不出電腦（總結步驟本機）。
"""
import sys, os, json, argparse, urllib.request, re

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

def load_cfg(harness):
    try:
        c = json.load(open(os.path.join(harness, "config.json"), encoding="utf-8"))
        return c.get("llm", {})
    except Exception:
        return {}

def ollama_gen(model, prompt, num_ctx=32768, temperature=0.2):
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_ctx": num_ctx, "temperature": temperature},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.loads(r.read().decode("utf-8")).get("response", "")

def model_available(model):
    try:
        with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=10) as r:
            tags = [m["name"] for m in json.loads(r.read()).get("models", [])]
        return model in tags or any(t.split(":")[0] == model.split(":")[0] for t in tags)
    except Exception:
        return False

def read(p, limit=None):
    if p and os.path.exists(p):
        t = open(p, encoding="utf-8").read()
        return t[:limit] if limit else t
    return ""

def chunk_text(t, size=5000):
    lines, chunks, cur = t.splitlines(keepends=True), [], ""
    for ln in lines:
        if len(cur) + len(ln) > size and cur:
            chunks.append(cur); cur = ""
        cur += ln
    if cur.strip():
        chunks.append(cur)
    return chunks

MAP_PROMPT = """以下是一場會議逐字稿的其中一段。請把它濃縮成**繁體中文條列重點筆記**：
- 保留具體的產品/服務/公司/人名、數字、講者觀點、決議、步驟。
- **只根據內容，不要虛構**；聽不清或不確定的照實標「(不確定)」。
- 不要客套、不要總評，只輸出重點條列。

逐字稿片段：
\"\"\"
{chunk}
\"\"\"

重點筆記："""

def structure_block(mode):
    if mode == "panel":
        return """## 1. 一句話摘要與關鍵重點
## 2. 與談人與角色
## 3. 逐題討論（每個主持人議題 → 各與談人觀點/立場，標明是誰）
## 4. 共識與分歧
## 5. 給開發者的建議 / take-away
## 6. 名詞解釋
## 7. 未解 / 存疑"""
    if mode == "meeting":
        return """## 1. 結論摘要（一句話 + 關鍵決議）
## 2. 與會者
## 3. 討論議題與決議（議題 → 討論 → 決議/拍板人；未達成標「未決」）
## 4. 行動項 Action Items（表格：| # | 事項 | 負責人 | 期限 | 狀態 |；未指定就填（未指定），不編造）
## 5. 未決 / 待追蹤
## 6. 風險 / 爭議
## 7. 名詞解釋
## 8. 未解 / 存疑"""
    return """## 1. 一句話摘要（+ 3–5 條 TL;DR）
## 2. 議程大綱
## 3. 重點內容
## 4. 技術細節 / 架構（引用投影片）
## 5. 實作要點 / Demo
## 6. 待辦 / 後續行動
## 7. Q&A / 講者觀點
## 8. 名詞解釋
## 9. 未解 / 存疑"""

REDUCE_TMPL = """你是專業會議記錄員。根據下列材料，寫一份**繁體中文、結構化**的會議總結。
規則（重要）：
- **只根據提供內容**，不要虛構產品/服務/數字/結論；無法確認的用「（存疑）」標註。
- 專名以【術語表】與【投影片】為準統一寫法。
- **不要**加入「[逐字稿]」「[投影片 IMG_xxx]」這類來源標註。
- **不要**寫死時鐘時間（議程時間僅供參考）。
- 忽略逐字稿中零星重複的雜訊（demo/影片聲）。

【本場標題】{title}
【講者/與談人】{speaker}
{agenda_block}【術語表(統一專名)】
{glossary}

【投影片文字】
{slides}

【講者分離(誰在何時說，若有)】
{speakers}

【逐字稿重點】
{notes}

請輸出完整 Markdown（以 frontmatter 開頭），結構如下：
---
type: meeting-summary
title: {title}
speaker: {speaker}
event: {event}
date: {date}
---
# {title}
{structure}

現在開始輸出總結："""

def strip_fences(t):
    t = t.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n", "", t)
        t = re.sub(r"\n```$", "", t)
    return t

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("session"); ap.add_argument("harness")
    ap.add_argument("--mode", default="talk")
    ap.add_argument("--model", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--speaker", default="（未標明）")
    ap.add_argument("--agenda", default=None)
    ap.add_argument("--event", default="")
    ap.add_argument("--date", default="")
    a = ap.parse_args()

    cfg = load_cfg(a.harness)
    model = a.model or cfg.get("localModel", "qwen3.5:35b-mlx")
    fallback = cfg.get("fallbackModel", "gemma4:31b")
    num_ctx = int(cfg.get("num_ctx", 32768))
    if not model_available(model):
        if model_available(fallback):
            print(f"[local] {model} 不在，改用 fallback {fallback}", file=sys.stderr); model = fallback
        else:
            print(f"[local] 找不到 {model} 或 {fallback}，請先 ollama pull", file=sys.stderr); sys.exit(3)

    sess = a.session
    rec = os.path.join(sess, "錄音")
    transcript = read(os.path.join(rec, "transcript.md")) or read(os.path.join(rec, "transcript.raw.md"))
    if not transcript.strip():
        print("[local] 無逐字稿", file=sys.stderr); sys.exit(2)
    slides = read(os.path.join(sess, "照片", "slides.md"), 12000)
    speakers = read(os.path.join(rec, "transcript.speakers.md"), 16000)
    glossary = read(os.path.join(a.harness, "vault", "術語表.md"), 4000)
    agenda = read(a.agenda, 6000) if a.agenda else ""
    title = a.title or os.path.basename(sess)

    # map-reduce 決策：長稿先濃縮
    if len(transcript) > 12000:
        chunks = chunk_text(transcript, 5000)
        print(f"[local] map-reduce：{len(chunks)} 塊", file=sys.stderr)
        notes = []
        for i, ch in enumerate(chunks):
            print(f"[local]  map {i+1}/{len(chunks)}", file=sys.stderr)
            notes.append(ollama_gen(model, MAP_PROMPT.format(chunk=ch), num_ctx=8192))
        notes_text = "\n".join(notes)
    else:
        notes_text = transcript

    agenda_block = f"【議程對照(校正講者/標題，時間僅參考)】\n{agenda}\n\n" if agenda else ""
    prompt = REDUCE_TMPL.format(
        title=title, speaker=a.speaker, agenda_block=agenda_block,
        glossary=glossary or "（無）", slides=slides or "（無投影片）",
        speakers=speakers or "（無講者分離）", notes=notes_text,
        event=a.event, date=a.date, structure=structure_block(a.mode))
    print("[local] reduce（產生總結）…", file=sys.stderr)
    out = strip_fences(ollama_gen(model, prompt, num_ctx=num_ctx))

    dest = os.path.join(sess, "summary.md")
    open(dest, "w", encoding="utf-8").write(out + "\n")
    print(json.dumps({"status": "ok", "summaryPath": dest, "model": model,
                      "chars": len(out), "mode": a.mode}, ensure_ascii=False))

if __name__ == "__main__":
    main()

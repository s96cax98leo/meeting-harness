#!/usr/bin/env python3
"""publish.py <session_dir> <harness_dir> <event_name>
發佈單一場次：summary.md → wiki 頁（frontmatter + event 連結 + 相關 wikilinks）+ pandoc docx + 會議索引一行。
冪等：重跑會覆寫 wiki/docx、索引去重。長期術語表另由 orchestrator 依 termCandidates 併入。
"""
import os, sys, subprocess, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _strip_cit import strip_text  # 最終檔案移除來源標註

def main():
    if len(sys.argv) < 4:
        print("usage: publish.py <session_dir> <harness_dir> <event_name>", file=sys.stderr); sys.exit(2)
    sess, harness, event = sys.argv[1], sys.argv[2], sys.argv[3]
    name = os.path.basename(sess).strip()  # 去掉可能的前導空格
    summary_path = os.path.join(sess, "summary.md")
    if not os.path.exists(summary_path):
        print(f"ERROR: no summary.md in {sess}", file=sys.stderr); sys.exit(3)
    # summary.md 保留標註當稽核底稿；wiki/docx 走清理版（不顯示 [投影片 IMG]/[逐字稿]）
    summary = strip_text(open(summary_path, encoding="utf-8").read())

    # 事件資料夾（依 event 去除空格作為子目錄）
    ev_slug = event.replace(" ", "")
    wikidir = os.path.join(harness, "vault", "wiki", ev_slug)
    os.makedirs(wikidir, exist_ok=True)

    # wiki 頁 = frontmatter + event 連結 + body + 相關
    parts = summary.split("---", 2)
    if len(parts) == 3:
        header = f"\n> 會議：[[{event}]]　類型：#meeting-summary　由 meeting-harness 產生\n"
        related = (f"\n\n---\n## 相關\n- 會議首頁：[[{event}]]\n"
                   f"- 長期記憶：[[術語表]]、[[會議索引]]\n")
        page = "---" + parts[1] + "---" + header + parts[2] + related
    else:
        page = summary
    wiki_page = os.path.join(wikidir, name + ".md")
    open(wiki_page, "w", encoding="utf-8").write(page)

    # docx（pandoc，經 to-docx.sh）
    exports = os.path.join(sess, "exports")
    os.makedirs(exports, exist_ok=True)
    docx = os.path.join(exports, name + ".docx")
    clean_md = os.path.join(exports, ".summary.clean.md")  # 清理版供 pandoc（暫存）
    open(clean_md, "w", encoding="utf-8").write(summary)
    r = subprocess.run(["bash", os.path.join(harness, "bin", "to-docx.sh"), clean_md, docx],
                       capture_output=True, text=True)
    docx_ok = r.returncode == 0
    if not docx_ok:
        print("docx WARN:", r.stderr.strip(), file=sys.stderr)

    # 會議索引一行（一句話摘要取「一句話摘要」段首句，去 wikilink 干擾）
    one = ""
    m = re.search(r"一句話摘要\s*\n+([^\n]+)", summary)
    if m:
        one = re.sub(r"[〔\[].*?[〕\]]", "", m.group(1)).strip()[:60]
    idx_path = os.path.join(harness, "vault", "會議索引.md")
    if os.path.exists(idx_path):
        idx = open(idx_path, encoding="utf-8").read()
        if f"[[{name}]]" not in idx:
            row = f"| 2026-07-15 | {event} | [[{name}]] | {one} | [[{name}]] |"
            open(idx_path, "w", encoding="utf-8").write(idx.rstrip() + "\n" + row + "\n")

    # 更新 event MOC 的場次清單
    moc = os.path.join(wikidir, event + ".md")
    if os.path.exists(moc):
        mc = open(moc, encoding="utf-8").read()
        if f"[[{name}]]" not in mc:
            mc = mc.replace("<!-- 其餘", f"- [[{name}]] ✅\n<!-- 其餘")
            open(moc, "w", encoding="utf-8").write(mc)

    # 收尾：把 summary.md 也清成最終乾淨版（verify/resolve 已用過標註；出處仍在 transcript.md/slides.md）
    open(summary_path, "w", encoding="utf-8").write(summary)
    if os.path.exists(clean_md):
        os.remove(clean_md)

    print(f"OK {name}: wiki={wiki_page} docx={'ok' if docx_ok else 'FAIL'} (citations stripped)")

if __name__ == "__main__":
    main()

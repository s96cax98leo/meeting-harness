---
name: publish-docx
description: 把會議總結發佈到 Obsidian wiki（frontmatter + wikilinks）並用 pandoc 轉成 Word docx；同時更新跨會議術語表與會議索引。當需要 publish / 進 wiki / 轉 word / docx / OfficeCLI 時使用。
---

# publish-docx（發佈 wiki + 轉 Word）

- wiki：`summary.md` → `vault/wiki/<會議>/<場>.md`（frontmatter + wikilinks）。
- 長期記憶：併入 `vault/術語表.md`、`vault/會議索引.md`。
- Word：`<harness>/bin/to-docx.sh <summary.md> <out.docx>`（pandoc 為主；需精細版面時改 OfficeCLI）。

發佈前需 verifier `pass`。由 `publisher-agent` 執行。

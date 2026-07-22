---
name: summarize
description: 把逐字稿 + 投影片文字 + 術語表融合成結構化繁中會議總結（TL;DR、大綱、重點、技術細節、待辦、Q&A、名詞解釋），每條主張標來源。當需要 meeting summary / 會議總結 / 摘要時使用。
---

# summarize（結構化會議總結）

輸入：`錄音/transcript.md` + `照片/slides.md` + `vault/術語表.md`（＋若有 `錄音/transcript.speakers.md` 講者分離稿）。
輸出：`summary.md`（9 段結構，見 summarizer-agent）。多講者場請據 speakers 檔標明講者/提問者、區分 Q&A。

原則：忠於來源、每主張標 `[逐字稿]/[投影片]`、無佐證標「（存疑）」、注入術語表保持跨場一致。由 `summarizer-agent` 執行。

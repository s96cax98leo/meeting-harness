---
name: transcribe
description: 把會議/課程錄音（m4a/mp3/wav/mov）用本機 mlx-whisper large-v3 轉成繁中逐字稿，並用現場粗轉錄做術語校對、補標點斷句。當需要 transcription / 逐字稿 / 語音轉文字時使用。
---

# transcribe（本機語音轉逐字稿）

本機、離線、零 API。工具：`<harness>/bin/transcribe.sh <audio> <out.md> [lang]`。

1. mlx-whisper large-v3 產原始稿（失敗自動 fallback openai-whisper medium）。
2. 讀現場 `轉文字.txt` + `vault/術語表.md` 校對專名、補標點分段。
3. 輸出 `錄音/transcript.md` + 新術語候選。

由 `transcribe-agent` 執行。詳見該 agent 定義。

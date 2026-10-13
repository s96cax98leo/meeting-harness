---
name: meeting-transcribe
description: 把錄音/錄影（m4a/mp3/wav/mov/mp4）用本機模型轉成繁體中文逐字稿——中文場用 Breeze-ASR-25（台灣華語＋中英混雜、原生繁體、不會吐 YouTube 字幕幻覺），跑 Apple Silicon GPU。當需要 語音轉文字 / 逐字稿 / transcribe / 聽打 時使用。
---

# meeting-transcribe（本機語音轉逐字稿）

全程本機、離線、零 API。`MH=/Users/yuktang/Documents/Agent/meeting-harness`

```bash
bash "$MH/bin/transcribe.sh" "<音檔或影片>" "<輸出.md>" zh
```
整場會議（多場次、含投影片 OCR）請用 `meeting.sh`，見 **meeting-summary** skill。

## 模型（`$MH/config.json` → `transcribe.models`）

| 語言／情況 | 模型 |
|---|---|
| zh（預設） | `Kenji8000/Breeze-ASR-25-mlx`——聯發科 Breeze-ASR-25 的 MLX 版，Whisper-large-v2 針對台灣華語＋中英混雜微調，**原生輸出繁體**，60 分鐘音檔約 2 分鐘 |
| 其他語言／Breeze 失敗 | `mlx-community/whisper-large-v3-mlx`（此路徑會自動跑 OpenCC `s2twp` 轉正體） |
| 無 mlx 環境 | `openai-whisper medium` |

單次換模型：`export MH_ASR_MODEL="<hf repo>"`。
防迴圈的實際做法：`--condition-on-previous-text False`（不拿前文當提示），加上轉完後的重複偵測（見下方 `*.QUALITY_WARNING`）。
`--compression-ratio-threshold` 已移除：mlx-whisper CLI 的溫度只有單一值、沒有溫度回退，這個門檻沒有作用。
**VAD（只轉有聲區間）**：錄製器產的場次（`錄音/tracks/manifest.json` 有 `levels`）會先用
`_record_lib.py clip` 算出有聲區間（兩路取大聲者 > -60 dBFS、空隙 < 2.0 秒合併、前後各補 0.75 秒，成品時間軸），
以 `--clip-timestamps` 交給 mlx-whisper（openai-whisper 退路用 `--clip_timestamps`），長靜音段不送進模型、少掉幻覺。
沒有 levels（ingest 進來的音檔）、全場無聲、或 `MH_VAD=0` 時退回整檔轉錄。
參數覆寫：`MH_VAD_THRESHOLD_DB`、`MH_VAD_PAD`、`MH_VAD_MERGE_GAP`。raw 標頭第二行會寫出實際用了什麼，例：
`> VAD：clip 2 段，門檻 -60 dBFS，補 0.75 秒，合併間隔 2.0 秒`，或 `> VAD：未套用（沒有 levels）`。
領域術語提示（降低專名誤植）：`export MH_TRANSCRIBE_HINT="以下為一場關於 … 的繁體中文會議"`。

> 為什麼不用通用 whisper：同一場 60 分鐘會議實測，large-v3 有 **23.7% 簡體字**、在靜音段吐
> 「請不吝點贊 訂閱…明鏡與點點欄目」這類 YouTube 字幕幻覺 3 段、靜音段產出文字 217 段；
> Breeze 對應數字是 **0.6%／0／0**（剩下的還是 `台→臺` 這種誤判）。

## 產物與規矩
- `transcript.raw.md`：引擎原始輸出。**不刪段、不改寫**——要精修就另存 `transcript.md`。
- `transcript.segments.json`：段落時間戳，**一律輸出**（不必再設 `MH_EMIT_SEGMENTS=1`），講者分離、VTT 要用。
- `transcript.quality.json`：可疑段落清單，一律輸出（沒有就 `[]`）。每筆 `{"start", "end", "reason"}`，`reason` 為
  `compression_ratio`（該段 zlib 壓縮比 > 2.4）、`no_speech_loop`（同一句在段內連續重複 ≥3 次）、
  `repeat_run`（相鄰 ≥4 段文字相同，每段各一筆）。只標記不刪：raw 不動，衍生檔（`transcript.speakers.md`、VTT）
  在這些段落前加「（聽不清）」。
- `*.QUALITY_WARNING`：偵測到重複迴圈時產生（同一行連續重複 ≥10 次，或行內 4 字片語重複 ≥8 次）。
  這種段落是雜訊造成的，**標「（聽不清）」不要採信，但不要刪**。
- 同一場多個檔案會自動依檔名串接（`_combine_audio.py`），時間戳連續。

## 精修（選用）
以 raw 為主體，用現場 `錄音/轉文字.txt` 與 `$MH/vault/術語表.md` 校對專名、補標點分段 → 寫 `transcript.md`。
只做「更正＋標點＋分段」，不摘要、不增刪語意。

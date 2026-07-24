# meeting-harness — 會議總結 Agent Team（可沿用）

把一場會議/研討會/課程的**錄音 + 投影片照片**，一鍵變成：乾淨繁中逐字稿 → 投影片文字 → 結構化總結 → Obsidian wiki 頁 → Word（.docx）。獨立自包含、指向任一會議目錄即可執行，未來每場沿用。

## 目錄
```
meeting-harness/
├─ bin/                 # 可重跑的本機工具
│  ├─ meeting.sh        # ★ 前門啟動器（doctor / prep / status）
│  ├─ init-vault.sh     # 從 seeds/ 建立本機 vault
│  ├─ transcribe.sh     # mlx-whisper large-v3 → 逐字稿（fallback openai-whisper；含防迴圈偵測）
│  ├─ ocr-slides.sh + _ocr.py   # sips HEIC→JPG + Apple Vision(ocrmac) OCR
│  ├─ to-docx.sh        # pandoc md→docx
│  ├─ publish.py        # 發佈 wiki + docx + 索引（自動移除來源標註）
│  └─ _strip_cit.py, _state.py  # 內部小工具
├─ .claude/
│  ├─ agents/           # 8 個專職 subagent
│  ├─ skills/           # meeting-summary(orchestrator) + 5 子任務 skill（SKILL.md，npx skills find 可索引）
│  └─ workflows/meeting-pipeline.js   # 確定性編排引擎（可觀測/可恢復）
├─ seeds/               # 乾淨 vault 種子（術語表 / 會議索引 範本）
├─ vault/               # Obsidian wiki + 長期記憶（不進版控）
└─ config.json
```

## 流水線

```mermaid
flowchart TD
    A["📁 會議根目錄<br/>錄音 .m4a + 照片 .HEIC"] --> P{{"meeting.sh<br/>本機前處理"}}
    P -->|並行| T["🎙️ transcribe<br/>mlx-whisper large-v3"]
    P -->|並行| O["🖼️ slide-ocr<br/>Apple Vision OCR"]
    O --> V["👁️ slide-vision<br/>架構圖視覺補讀"]
    T --> S["📝 summarizer<br/>結構化繁中總結"]
    V --> S
    S --> C["✅ verifier<br/>逐條查核 pass/fail"]
    C -->|fail 回退| S
    C -->|pass| R["🔎 resolver<br/>上網查證補足存疑"]
    R --> Pub["📤 publisher<br/>wiki + docx + 索引"]
    Pub --> W["🗂️ Obsidian wiki"]
    Pub --> D["📄 Word .docx"]
    M["🧠 vault/術語表.md<br/>長期記憶"] -.注入.-> T
    M -.注入.-> S
```

## 一次性安裝
```bash
pip install mlx-whisper ocrmac      # Apple Silicon 本機、離線（首跑 large-v3 下載約 3GB）
brew install pandoc
# find-skill 用 npx，免安裝：npx skills find <關鍵字>
bash bin/init-vault.sh              # 從 seeds/ 建立本機 vault（wiki + 長期記憶）
bash bin/meeting.sh doctor          # 檢查工具鏈
```

> 注意：`vault/`（Obsidian wiki 與長期記憶，含實際會議內容）**不進版控**（見 `.gitignore`）——屬個人/機密資料，由 `init-vault.sh` 從 `seeds/` 在本機生成。

## 每場會議的資料擺法
```
<會議根目錄>/<場次名稱>/
├─ 錄音/<場次>.m4a          # 必要
├─ 錄音/轉文字.txt           # 選配：現場粗轉錄（用於術語校對）
└─ 照片/*.HEIC              # 投影片照片
```

## 用法（兩步）
```bash
# 1) 本機前處理（轉錄 + OCR，可重跑、冪等）
bash bin/meeting.sh "<會議根目錄>"

# 2) AI 步驟：在 Claude Code 執行（逐字稿精修→總結→驗證→發佈 wiki+docx）
#    /meeting-summary "<會議根目錄>"

# 看狀態
bash bin/meeting.sh status "<會議根目錄>"
```

## 範例輸出（示意，非真實會議）

**① 檢查工具鏈** — `meeting doctor`
```text
== meeting-harness doctor ==
✓ mlx-whisper
✓ ocrmac (Apple Vision)
✓ pandoc
✓ sips
✓ ffmpeg
✓ npx (find-skill: npx skills find)
```

**② 本機前處理** — `meeting "~/會議/2026-Q3-技術分享"`
```text
== 會議根目錄：~/會議/2026-Q3-技術分享 ==

── [1] 微服務可觀測性實作 ──
  ▶ 轉錄：.../錄音/微服務可觀測性實作.m4a
[transcribe] engine=mlx-whisper model=large-v3 ...
[transcribe] DONE -> .../錄音/transcript.raw.md (912 lines; max-line-repeat=6)
  ▶ 投影片 OCR：.../照片
[ocr] 24 images ready; running Apple Vision OCR
[ocr] DONE -> .../照片/.ocr

── [2] 資料管線重構 ──
  ▶ 轉錄：.../錄音/資料管線重構.m4a
[transcribe] DONE -> .../錄音/transcript.raw.md (1043 lines; max-line-repeat=8)
  ▶ 投影片 OCR：.../照片
[ocr] DONE -> .../照片/.ocr

════════════════════════════════════════════════════
✅ 本機前處理完成（2 場）。接著在 Claude Code 執行：
    /meeting-summary "~/會議/2026-Q3-技術分享"
════════════════════════════════════════════════════
```

**③ 進度** — `meeting status "~/會議/2026-Q3-技術分享"`
```text
• 微服務可觀測性實作   transcribe:done, slide-ocr:done, summarize:done, verify:pass, resolve:done, publish:done
    ✓ transcript.md
    ✓ slides.md
    ✓ summary.md
    ✓ docx: .../exports/微服務可觀測性實作.docx
• 資料管線重構        transcribe:done, slide-ocr:done, summarize:done, verify:pass, resolve:done, publish:done
    ✓ transcript.md ✓ slides.md ✓ summary.md ✓ docx
```

## 範例：產出的總結長什麼樣（骨架，示意內容）
每場 `summary.md`／wiki 頁的結構（來源標註在發佈時自動移除，只留 `（存疑）` 與 `（來源：URL）`）：
```markdown
---
type: meeting-summary
event: 2026 Q3 技術分享
session: 微服務可觀測性實作
date: 2026-07-16
tags: [可觀測性, tracing, metrics]
---

# 微服務可觀測性實作

## 1. 一句話摘要
<一句話 + 3–5 條 TL;DR>

## 2. 議程大綱        ## 3. 重點內容        ## 4. 技術細節/架構
## 5. 實作要點/Demo   ## 6. 待辦事項         ## 7. Q&A / 講者觀點
## 8. 名詞解釋（跨會議術語表累積）
## 9. 未解/存疑（resolver 已上網查證，附來源；查不到者誠實標註）
```

## 進階：提升轉錄準確度（選用）
轉錄預設用通用中文提示。若你知道當場的領域術語，設環境變數可降低專名誤植：
```bash
export MH_TRANSCRIBE_HINT="以下為一場關於 <你的領域/產品/技術術語…> 的繁體中文技術演講。"
```
術語表（`vault/術語表.md`）會跨會議累積，summarizer 也會用它統一專名。

## 兩種模式：研討會 vs 開會
| | 研討會/演講（預設） | 開會/討論 |
|---|---|---|
| 指令 | `meeting "<資料夾>"` | **`meeting notes "<資料夾>"`** |
| 總結重點 | 議程/重點/技術細節/投影片 | **結論與決議・行動項表格(負責人/期限/狀態)・未決・風險** |
| 講者分離 | 選用 | **自動開啟**（分辨誰主張/誰拍板） |

**開會用法（兩步）：**
```bash
# 1) 本機前處理（轉錄 + 講者分離 + 標記會議模式）
meeting notes "<會議資料夾>"

# 2) 在 Claude Code 產出會議紀錄（含待辦表格）
#    /meeting-summary "<會議資料夾>"
```
會議模式的 `summary.md` 會是：結論/決議 → 逐議題討論 → **行動項 `| 事項 | 負責人 | 期限 | 狀態 |`** → 未決/待追蹤 → 風險/爭議。負責人與期限只從逐字稿抽取，抽不到標「（未指定）」不編造。

## 總結後端：雲端 Claude / 地端混合 / 全離線
轉錄、OCR、講者分離**本來就全在本機**；只有「總結」預設走 Claude（雲端）。機密會議可改地端：
| 模式 | 總結 | resolver 查證 | 內容外流 | 指令 |
|---|---|---|---|---|
| **Claude（預設）** | Claude（品質最好） | 線上 | 總結時送 Claude | `/meeting-summary` |
| **地端混合** | **本機 Qwen** | 線上（只送存疑關鍵詞） | 逐字稿不出電腦 | `MH_LLM=local`；或 `meeting summarize-local <場次>` |
| **全離線** | 本機 Qwen | 不跑 | 完全不出電腦 | `meeting local "<會議根目錄>"` |

地端用你本機的 **ollama**（0.19+ 已是 MLX 後端），建議模型 **Qwen 3.5 35B-mlx**（繁中最佳、Apple Silicon 最佳化；`gemma4:31b` 作 fallback）：
```bash
ollama pull qwen3.5:35b-mlx     # ~21GB，一次性
bash bin/meeting.sh doctor       # 會顯示地端模型狀態
# 單場本機總結：
bash bin/meeting.sh summarize-local "<會議根目錄>/<場次>"
# 全離線一鍵：
bash bin/meeting.sh local "<會議根目錄>"
```
> 品質：Qwen3.5-35B 日常近 hosted Sonnet，但長稿忠實度/講者歸屬/存疑判斷仍略遜 Claude Opus——機密/離線走地端，公開會議可續用 Claude。長逐字稿會自動 map-reduce。

## 講者分離（選用，多講者場才需要）
單一演講不需要；**Q&A、對談、panel、多位講者**時可標出「誰說了什麼」。用 [Senko](https://github.com/narcotic-sh/senko)（本機 CoreML、免 HuggingFace token、英文＋國語最佳化、~秒級），**保留 mlx-whisper 逐字稿**只加講者標籤。
```bash
brew install uv
bash bin/setup-senko.sh          # 建 senko venv（首跑下載 CoreML 模型；venv 在專案外）

# 對某一場開啟：放一個空標記檔，之後 prep 會自動多跑分離
touch "<會議根目錄>/<場次>/錄音/.diarize"
bash bin/meeting.sh "<會議根目錄>"

# 或單獨對一場跑：
bash bin/meeting.sh diarize "<會議根目錄>/<場次>"
```
產出 `錄音/transcript.speakers.md`（`[SPEAKER_00] …`）。summarizer 看到它就會分辨提問/回答。
- **改真名**：放 `錄音/speakers.map.json`，例：`{"SPEAKER_00":"講者","SPEAKER_01":"提問者A"}`。
- **折疊零星插話**：`export MH_MIN_SPEAKER_SEC=30` 把總時長 <30 秒的講者併入最近主要講者（預設 0＝全保留）。
- 限制：標籤匿名、重疊講話/相似聲線會誤標；v1 段落級對齊。

## 方便啟用：加一個全域指令 `meeting`
```bash
echo 'alias meeting="bash $HOME/Documents/Agent/meeting-harness/bin/meeting.sh"' >> ~/.zshrc
source ~/.zshrc
# 之後任何地方： meeting "<會議根目錄>"  /  meeting doctor  /  meeting status "<根>"
```

## 沿用到新會議
資料照上面擺好 → `meeting "<新根目錄>"` → 在 Claude Code `/meeting-summary "<新根目錄>"`。術語表會跨會議自動累積。

## 授權
[MIT](LICENSE)

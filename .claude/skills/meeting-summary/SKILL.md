---
name: meeting-summary
description: 會議總結 orchestrator。給一個會議根目錄（內含多個場次，每場有 錄音/*.m4a + 轉文字.txt + 照片/*.HEIC），自動跑：轉錄→投影片OCR→架構圖視覺補讀→結構化繁中總結→驗證→發佈到 Obsidian wiki + 轉 Word。具短期/長期記憶、可觀測性、驗證與失敗恢復。當用戶要「總結會議/研討會/課程錄音+投影片」時使用。
metadata:
  reusable: true
  entrypoint: "/meeting-summary <會議根目錄>"
---

# meeting-summary（orchestrator 劇本 / SOP）

一套**可沿用**的會議總結流水線。指向任一會議根目錄即可執行；未來每場會議重複套用。

## 核心能力（本劇本落地）
編排=本 SOP + `meeting-pipeline.js`；多代理=7 個 subagent；溝通=JSON schema + `.pipeline-state.json`；記憶=`vault/術語表.md`(長期)+state(短期)；驗證=verifier 閘門；恢復=stage 冪等 + resume；可觀測性=`.pipeline-state.json`+`run.log`+`/workflows`；技能發現=`npx skills find`。

## 輸入
- `會議根目錄`：其下每個子資料夾是一個**場次**，含 `錄音/<場>.m4a`、選配 `錄音/轉文字.txt`、`照片/*.HEIC`。
- harness 根：本專案（含 `bin/`、`config.json`、`vault/`）。

## 前置（preflight）
1. 讀 `config.json`（vaultPath、模型、來源檔命名）。
2. 確認工具：`python3 -c "import mlx_whisper"`、`python3 -c "from ocrmac import ocrmac"`、`command -v pandoc`、`npx skills --help`。缺則先裝（見 README）。
3. **技能路由（find-skill）**：對每個子任務用 `npx skills find <關鍵字>`（transcription / image ocr / obsidian / docx）確認/挑選最適 skill；本專案已內建對應 skill，找不到外部更適者就用內建。
4. 建 `vault/`（若無）與各場 `exports/`；初始化每場 `.pipeline-state.json`。

## 逐場流水線（可用 Workflow 工具跑 `meeting-pipeline.js`，或由主 Claude 依序驅動 subagent）
每場獨立 context，兩路並行後匯流：

```
preflight
├─(A) transcribe-agent         # 錄音 → transcript.md
│      └─(選用) diarize         # 多講者場（錄音/.diarize 或 MH_DIARIZE=1）→ transcript.speakers.md（senko）
└─(B) slide-ocr-agent          # 照片 → .ocr/*.txt, slides.ocr.md, needsVision[]
      └─ slide-vision-agent    # needsVision → slides.md
                    ↓ (A、B 匯流)
        summarizer-agent        # transcript(+speakers) + slides + 術語表 → summary.md
        │  ★ 若場次有 錄音/.meeting 標記（開會/討論）→ 改用 meeting-notes-agent
        │    產「會議紀錄」：結論/決議・行動項表格(負責人/期限/狀態)・未決・風險
                    ↓
        verifier-agent          # pass/fail（fail → 回退 recoverStage 重跑）
                    ↓ pass
        resolver-agent          # 存疑補足：上網查證 + 前後文，能補則補、有佐證才升級
                    ↓
        publisher-agent         # wiki 頁 + 術語表/會議索引 + docx
```

## 可觀測性
- 每場 `.pipeline-state.json` 記錄各 stage：`pending|running|done|failed`、產物路徑、時間戳、重試次數。
- `run.log` 累積每步 stdout 摘要。
- 用 Workflow 工具時，`/workflows` 有即時樹、`journal.jsonl` 記每個 agent 回傳。

## 驗證與恢復
- **冪等**：每 stage 先檢查產物存在且有效 → 跳過（重跑安全）。
- **驗證閘門**：verifier `fail` → 依 `recoverStage` 只重跑該 stage 及其下游；`pass` 才 publish。
- **恢復**：中斷後重跑整個 SOP，已完成 stage 走快取；用 Workflow 則 `resumeFromRunId` 只重跑失敗 stage。

## 完成後
- `lint the wiki`（若裝 claude-obsidian）檢查死連結/孤兒頁。
- 首場跑完**人工快速校閱術語表**一次，之後自動累積。

## 未來沿用
新會議：把資料照 `場次/錄音/*.m4a(+轉文字.txt)` 與 `場次/照片/*.HEIC` 放好，執行 `/meeting-summary <新根目錄>` 即可。

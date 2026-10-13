# meeting-harness

各客戶（會議資料分別放在 ~/Documents/<客戶>/ 下，不交叉引用） 的專案工作區。這裡用 `agent-workflow` 的 agent team 做需求開發（AI-native SDLC）與事件處理。硬規則全文在 `.claude/teams/rules.md`，本檔只列每次都要記得的重點。

## 語言（強約束）
- 所有輸出一律使用 **繁體中文**：回覆、派工單、agent 之間的訊息、信封、文件、commit 訊息內文、推播通知。
- 程式碼識別字、指令、路徑、技術專有名詞保留原文。

## 先 plan、後動手
- 任何任務先列出模糊點與假設，確認後才動手；需求開發走 `sdlc-plan → sdlc-design → sdlc-build → sdlc-test → sdlc-deliver`。
- plan、design、test、deliver 四個閘門都要 使用者 核准，用 `python3 .claude/teams/tools/save_run.py approve` 記錄，並在對話裡列出重點。
- 使用者 的回覆照字面讀：「調整」不是「核准」。

## 不可逆節點
- push、開 PR、寫上游、刪資料、對外寄送：一律停下，等 使用者 當下同意；先前的同意不延伸到下一次。
- agent 不推送、不合併、不 approve；推送由主 session 在同意後執行。remote 是 `origin`（github.com/s96cax98leo/meeting-harness，**public**、`main` 未受保護），一次推送就直接改寫公開的 `main`。
- 需要決策時用選項式提問（2–3 個選項＋代價＋建議），並推播到手機。

## 機敏檔
- `.env`、金鑰、憑證不讀、不印、不提交；只能用 `grep -q` 判斷有無。
- push 前用 `grep -qF -f <機敏值清單> <diff>` 比對 diff 是否含機敏值，只報「有／沒有」。
- `.env` 是 symlink 時，會寫 `.env` 的工具會寫到原檔：先記 sha，收尾還原。

## 客戶資料邊界
- 只使用本工作區與 各客戶（會議資料分別放在 ~/Documents/<客戶>/ 下，不交叉引用） 的資料；不同客戶的目錄、資料、文件不得交叉引用。
- 禁止路徑（只能讀）：/Users/yuktang/Documents/Agent/PersonalAgent,/Users/yuktang/Documents/Agent/AgentWorkFlow。

## 任務編號
- 沒有上層任務系統，也沒有任務編號可引用：不要自編 `TASK-`／`ST-` 這類編號。衍生工作寫「衍生工作（不編號）」。

## 目錄
- 目標 repo：本工作區自己（`/Users/yuktang/Documents/Agent/meeting-harness`）；簡報：`_tpm/briefs/`；執行紀錄：`_tpm/runs/`（見該目錄的 README.md）。
- 守門設定：`.claude/teams/guard.config.json`；規則：`.claude/teams/rules.md`（含「專案規則」段）。

## commit 與分支
- Conventional Commits，scope 放 Story ID；結尾署名行：

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- 新分支用 `feature/<epic>`、子任務 `feature/<epic>--<sub>`，各開 worktree；不 force push、不 `--no-verify`。
- 測試失敗就改程式，不改測試；上游測試不改（例外要 使用者 核准並記錄在 spec）。

## 專案特定
- **這是什麼**：本機會議紀錄工具。流程：`ingest`（歸檔錄音與截圖）→ `transcribe`（Breeze-ASR-25／mlx-whisper）→ `diarize`（pyannote community-1 跑 MPS）＋聲紋比對 → 寫 `meeting.record.json` → `render` 成 `summary.md`／`actions.csv`／`actions.ics`／`transcript.vtt`。
- **verify**：`bash bin/_lint.sh && bash bin/meeting.sh doctor`（commit 前、合併後都跑）。
- **沒有畫面、沒有服務**：`has_ui`、`has_security` 一律 false，不需要 compose。
- **五條鐵則**：raw 逐字稿不改（只標記不清洗）／不編造負責人與期限／不確定的姓名不掛／雜訊段標「（聽不清）」／聲紋只留本機 `vault/`。
- **對外介面**：`bin/meeting.sh` 與 `~/.claude/skills/meeting-*`（symlink 回本 repo）其他 session 會用，子指令與結束碼不要破壞性變更。
- 完整的專案規則、禁區與既有定案見 `.claude/teams/rules.md` 的「專案規則」段。

<!-- agent-workflow：由 init.py 從模版產生（AgentWorkFlow 的 scaffold/CLAUDE.md.tmpl）；可以自由修改，重跑 init 不會覆蓋（加 --force 才會） -->
# meeting-harness

各客戶（會議資料分別放在 ~/Documents/<客戶>/ 下，不交叉引用） 的專案工作區，用 `agent-workflow` plugin 的 agent team 做需求開發（AI-native SDLC）與事件處理，入口是 `tpm-team` skill。本檔只列每次都要記得的重點：
- 硬規則全文：`.claude/teams/rules.md`
- 結構與工具：`.claude/teams/README.md`

## 語言（強約束）
- 所有輸出一律使用 **繁體中文**，包括回覆、派工單、agent 之間的訊息、信封、文件、commit 訊息內文、推播通知。
- 程式碼識別字、指令、路徑、技術專有名詞保留原文。

## 先 plan、後動手
- 任何任務先列出計畫、模糊點與假設，確認後才動手。
- 需求開發依序走：`sdlc-plan` → `sdlc-design` → `sdlc-build` → `sdlc-test` → `sdlc-deliver` → `sdlc-merge`。
- plan、design、test、deliver 四個閘門都要 使用者 核准。用 `python3 .claude/teams/tools/save_run.py approve` 記錄，並在對話裡列出重點，不能只依賴工具狀態。
- 使用者 的回覆照字面讀：「調整」不是「核准」，附帶的意見要先處理。
- workflow 回傳 `halted: true` 時，停下來交給 使用者，不要自行重跑繞過。

## 平行處理
- 計劃太大時，`sdlc-design` 會拆成子計劃，由多個 agent 平行規劃再彙整。
- `sdlc-build` 會讓沒有相依的子任務各自開 worktree 平行實作，再合併。
- 有子計劃時，`sdlc-test` 會分片平行驗證；修正也平行進行，再合併。
- 觸發門檻在 `.claude/teams/methodology.json` 的 `parallelism`。
- 團隊自己的 agent 可以加進 plan、design、test、deliver 任一段：用 `/add-agent` 設定，寫在 `methodology.json` 的 `extensions`，守門角色登記在 `guard.config.json` 的 `extension_agents`。

## 不可逆節點
- push、開 PR、寫上游（本 repo 沒有上游）、刪資料、對外寄送：一律停下，等 使用者 當下同意。先前的同意不延伸到下一次。
- agent 不推送，也不核准 PR。推送由主 session 在取得同意後執行；gh 寫入要明確寫 `--repo s96cax98leo/meeting-harness`。
- 合併：只有在 `guard.config.json` 的 `auto_merge` 啟用時，才可以由 `dev-merge-steward` 對照需求後合併，而且 `merge_gate.py` 要判定為 merge。其餘情況一律由人合併，主 session 也不合併。
- 需要決策時用選項式提問（2–3 個選項，附代價與建議），並推播到手機。

## 機敏檔
- `.env`、金鑰、憑證不讀、不印、不提交；只能用 `grep -q` 判斷有沒有。
- push 前用 `grep -qF -f <機敏值清單> <diff>` 比對 diff 是否含機敏值，只回報「有／沒有」。
- `.env` 是 symlink 時，會寫 `.env` 的工具會寫到原檔：先記下 sha，收尾時還原。

## 客戶資料邊界
- 只使用本工作區與 各客戶（會議資料分別放在 ~/Documents/<客戶>/ 下，不交叉引用） 的資料；不同客戶的目錄、資料、文件不得交叉引用。
- 禁止路徑（只能讀）：/Users/yuktang/Documents/Agent/PersonalAgent,/Users/yuktang/Documents/Agent/AgentWorkFlow。

## 任務編號
- 本 repo 沒有上層任務系統，也沒有任務編號可引用：不自己編。衍生工作寫成「衍生工作（不編號）」。

## 開發規範與慣例
- 開發規範 profile 是 `default`，實際內容在 `.claude/teams/methodology.json`（init 時依使用者的習慣產生）。各段做法（產出文件、需求寫法、測試時機、驗證方式）與慣例（code style、commit、分支命名、PR 大小、文件格式）都以它為準；模版只管工作流程。
- 改了 `methodology.json` 要重跑 `python3 .claude/teams/tools/build.py`，把新的 profile 內嵌進 workflow。

## commit 與分支
- commit 格式照 `methodology.json` 的 `conventions.commit`，結尾加署名行：

  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- 分支：epic 用 `feature/<epic>`，子任務用 `feature/<epic>--<sub>`，各自開 worktree。不 force push、不用 `--no-verify`。
- 測試失敗就改程式，不改測試。上游測試不改；要例外須經 使用者 核准，並記錄在 spec。

## 目錄
- 目標 repo：本工作區自己（`/Users/yuktang/Documents/Agent/meeting-harness`）
- 簡報：`_tpm/briefs/`
- 執行紀錄：`_tpm/runs/`（說明見該目錄的 README.md）
- 守門設定：`.claude/teams/guard.config.json`
- 硬規則：`.claude/teams/rules.md`（含〈專案規則〉段）

## 專案特定
見 `CLAUDE.md`〈專案特定〉與 `.claude/teams/rules.md`〈專案規則〉（verify 指令、五條鐵則、對外介面、既有定案）。

<!-- 本檔已偏離 init 模版（填入本 repo 的值）；下次 init.py --force 會蓋回模版，升級後要重新合回。 -->

# meeting-harness agent team 硬規則

所有 `tpm-*`、`dev-*` agent 與主 session 都遵守。能機械檢查的由 agent-workflow 的 hooks（設定：`.claude/teams/guard.config.json`）與 `.claude/teams/tools/check_rules.py` 強制。

本檔分兩部分：
- **通用規則**：模版內建，適用任何專案；要放寬某一條，請在「專案規則」寫明例外與核准人，不要直接刪。
- **專案規則**：init 後由專案填寫（目標 repo、禁區、審查規則、設計系統、verify 指令）。

---

## 通用規則

### 寫入與權限
1. **不寫入上游**：本專案目前沒有上游 repo（`upstream_repos` 空）。將來若 fork 了別人的 repo，要先把它填進 `guard.config.json` 的 `upstream_repos`，在那之前不得 push、不開 PR、不留言、不改狀態。
2. **推送一律要使用者當下同意。** remote 是 `origin`＝`s96cax98leo/meeting-harness`（`guard.config.json` 的 `fork_repo`），**public** 且 `main` 未受保護，推送沒有 PR 緩衝；加減 remote 也算不可逆動作。agent 一律不 push、不合併；推送由主 session 在同意後執行，`gh` 寫入動作要明確帶 `--repo <目標>`。
3. **不可逆節點一律停下**：push、開 PR、寫上游、刪資料、對外寄送，都要使用者當下同意；先前的同意不延伸到下一次。
4. **禁止路徑只能讀**：`guard.config.json` 的 `forbidden_paths`（/Users/yuktang/Documents/Agent/PersonalAgent,/Users/yuktang/Documents/Agent/AgentWorkFlow）不得寫入、移動、刪除。由 `guard-paths.sh`、`guard-bash.sh` 擋。
5. **機敏檔不讀、不印**：`.env`、金鑰、憑證不讀值、不印出、不提交，也不在本機搜尋或借用別處的 API key、token。要判斷有無只能用 `grep -q`；push 前用 `grep -qF -f <機敏值清單> <diff>` 比對 diff 是否含機敏值，只報「有／沒有」。
6. **核准與合併 PR 只能由人做**：agent 只留建議，不執行 `gh pr merge`、`gh pr review --approve`。
7. 改目標 repo 時，那個 repo 自己的規範（CLAUDE.md、分支規範、REVIEW.md、hooks）照樣適用；hooks 會轉呼叫 repo 自己的 `guard-git.sh`、`guard-paths.sh`。

### 內容
8. **不寫人天、人月、工時估算。** 費用只列項目與官方定價出處。
9. **不自編任務編號**：任務編號（`…`）只由 使用者 發。衍生工作寫進信封的 `derived_work` 或執行紀錄的「衍生工作（不編號，交 使用者 編）」。
10. **每個數字和結論都要能回查**：附 `路徑:行號` 或可重跑的指令；查不到就寫「未能確認」。
11. **不替使用者或使用者做決定**：列選項與代價，可以標建議並附理由。需要決策時用選項式提問，並推播到使用者的手機（PushNotification）。
12. **給決策者或對外的文件**：不寫內部編號，不評價人，技術名詞保留原文。`check_rules.py --audience owner|external` 檢查。
13. **客戶資料邊界**：不同客戶的目錄、資料、文件不得交叉引用。
14. 抓外部網站前先看 robots.txt；不做任何會改變對方狀態的動作。
15. **輸出語言（強約束）**：所有輸出一律使用 **繁體中文**，包括給使用者的回覆、agent 之間的訊息與派工單、SendMessage、信封的 summary／open_questions／derived_work、文件、commit 訊息內文、推播通知。程式碼識別字、指令、路徑、技術專有名詞保留原文。

### 流程
16. **先 plan、後動手**：開發走 AI-native SDLC：intent → design → spec → plan →（紅燈測試 → 實作）→ verifier →（設計／安全審查）→ PR 審查 → 人核准。plan、design、test、deliver 四個閘門都要使用者核准才進下一段，核准用 `save_run.py approve` 記錄，並在對話裡列重點，不只依賴工具狀態。
17. **決策者的回覆照字面讀**：「調整」不是「核准」；附帶意見要先處理再請求核准。
18. **commit**：Conventional Commits，scope 放 Story ID；結尾署名行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。`check_rules.py --git` 檢查。
19. **分支**：新分支只用 `guard.config.json` 的 `allowed_branch_prefixes`（feature/,bugfix/,hotfix/,release/,merge/）；子任務分支 `feature/<epic>--<sub>`，各開 worktree，檔案所有權不重疊；整合用整合分支，依相依順序合併。不 force push、不 `--no-verify`。建議的分支名不合規時改用允許的前綴並註明。
20. **測試失敗就改程式，不改測試**；不加 skip、fixme、retry，不放寬斷言。上游測試不改；例外要使用者核准，並記錄在 spec 的「整合修訂與例外」。
21. **改寫 commit 歷史前留備份分支**；改寫後更新文件中引用的 SHA。

### 交件
22. **每個 agent 都以 JSON 信封交件**（`.claude/teams/schemas/envelope.schema.json`）：
    - Workflow 裡由 `schema` 強制。
    - 用 Agent 工具派出時，回報最後要附一個 ```json 區塊，`check-envelope.sh` 會驗證。
23. **成果一律寫成檔案，信封只放路徑。** 有 blocking 問題時 `status` 不能是 `done`；blocking 問題要附 2–3 個選項與代價。
24. **審查者只讀，只看證據，不採信作者的自述。** 退回最多 2 次，超過交給人。
25. **派工單自足**：目標、依據檔、硬規則、驗收、回覆格式都寫在派工單裡，使用輸出語言。

---

## 專案規則

- **目標 repo**：`/Users/yuktang/Documents/Agent/meeting-harness` 本身就是目標 repo（`repos_dir` 空），主線分支 `main`。無上游；我方 remote 是 `origin`（`github.com/s96cax98leo/meeting-harness`，public）。本機領先遠端幾個 commit 請以 `git rev-list --count origin/main..main` 為準，不寫死在文件裡。推送一律要使用者當下同意。
- **禁區**：`/Users/yuktang/Documents/Agent/PersonalAgent`（只能讀：`tools/meetings.py` 的 `REQUIRED_SECTIONS` 與 `/ingest-meeting` 是本專案要相容的契約，改它會連帶影響別的流程）、`/Users/yuktang/Documents/Agent/AgentWorkFlow`（只能讀：本流程的模版來源，要改走它自己的 repo）。
- **會議資料目錄**（可寫，但不是 repo）：`~/Documents/<客戶>/<專案>/會議記錄/<日期>/<場次>/錄音/`。每個客戶一個目錄，**不同客戶的資料與文件不得交叉引用**。產出（`meeting.record.json`、`summary.md`、`actions.csv/.ics`、`transcript.vtt`）寫在該場次目錄裡，不進本 repo。
- **需求來源**：使用者在對話裡口述（沒有上層任務系統，`task_id_prefix` 空，所以也沒有任務編號可引用）。`_tpm/briefs/` 目前空著，有正式任務單時才放。
- **backlog 位置**：無。衍生工作寫進信封的 `derived_work` 與執行紀錄，不編號。
- **審查規則**：本 repo 沒有 `REVIEW.md`。PR 大小沿用通用規則（修改既有檔超過 300 行或 15 檔列 important）。必審的 lens：standards、spec、bugs、history；`bin/` 的 shell 腳本一律加 shell 慣用法審查（見下方 verify 指令，`_lint.sh` 專門擋 `$VAR` 緊接全形字與雙引號內反引號這兩個踩過三次的坑）。
- **設計系統 skill**：無（本專案沒有畫面，`dev-design-reviewer` 與 `has_ui` 一律 false）。
- **verify 指令**：`bash bin/_lint.sh && bash bin/meeting.sh doctor`。implementer commit 前與 integrator 合併後都要跑。**epic 的 `specs/<epic>/plan.md` §3 列有測試指令時，integrator 每合併完一層也要在整合分支全量跑一次那些指令**（同層子任務在各自 worktree 看不到彼此的檔，整合後的全量測試是唯一能抓到跨子任務落差的時點）；任何一條不綠就不得清 worktree、不得進下一層。`doctor` 會檢查 ASR 模型快取、diarize venv、MPS 與 gated 模型授權；**沒有錄音檔也要能全綠**，不綠就是環境壞了，不要改測試去配合。
- **demo 環境**：無 compose、無服務。跑轉錄或分離的測試時用獨立暫存目錄與固定 locale（`export TMPDIR="$(mktemp -d)"`、`export LC_ALL=en_US.UTF-8`）。長時間的轉錄用 `run_in_background`，不要用 sleep 等。
- **其他專案特定約定**（既有定案，不得推翻）：
  1. **raw 逐字稿絕對不修改**。幻覺、重複迴圈只能「偵測並標記」（寫 `$OUT.QUALITY_WARNING`），不得清洗、刪除或改寫 `transcript.raw.md`。要修正就修到來源（換模型、換參數），不是修輸出。
  2. **不編造負責人與期限**。逐字稿沒講的 owner／due 一律留空並列入「存疑」。
  3. **不確定的姓名不掛**。聲紋 cos ≥0.75 才改名、0.60–0.75 只當線索（`apply` 旗標），<0.60 不寫；推不出來就維持 `SPEAKER_0x`。
  4. **雜訊段標「（聽不清）」**，不當成真實發言引用。
  5. **聲紋是生物特徵資料**：只存 `vault/voiceprints/`（已 gitignore）、只在本機、只由使用者確認過的對應才建檔、可隨時刪。不得複製到 repo、run 目錄或任何對外文件。
  6. **下游知識庫專案 相容性是驗收條件**：`summary.md` 必須含「決議／依賴／風險／交辦」四段與 `一句話：`，改 `_render.py` 的輸出格式時要用 下游知識庫專案 自己的 `meetings._missing_sections()` 驗過。
  7. **`meeting.sh` 是對外介面**：其他 session 會呼叫，子指令與結束碼的語意不得破壞性變更；六個 `meeting-*` skill 以 symlink 裝在 `~/.claude/skills/`，改 repo 裡的 `SKILL.md` 等於改全域。

# meeting-harness agent team 硬規則

所有 `tpm-*`、`dev-*` agent 與主 session 都遵守。能機械檢查的由 agent-workflow 的 hooks（設定：`.claude/teams/guard.config.json`）與 `.claude/teams/tools/check_rules.py` 強制。

本檔分兩部分：
- **通用規則**：模版內建，適用任何專案；要放寬某一條，請在「專案規則」寫明例外與核准人，不要直接刪。
- **專案規則**：init 後由專案填寫（目標 repo、禁區、審查規則、設計系統、verify 指令）。

---

## 通用規則

### 寫入與權限
1. **不寫入上游**：本專案目前沒有上游 repo（`upstream_repos` 空）。將來若 fork 了別人的 repo，要先把它填進 `guard.config.json` 的 `upstream_repos`，在那之前不得 push、不開 PR、不留言、不改狀態；填進去之後只有使用者在當下明確同意的那一次例外，並由使用者自己執行。由 `awf_hook.py guard-shell` 擋（`upstream_repos`；Bash 與 PowerShell 都擋）。
2. **推送與開 PR 一律要使用者當下同意，agent 一律不 push。** remote 是 `origin`＝`s96cax98leo/meeting-harness`（`guard.config.json` 的 `fork_repo`），**public**；加減 remote 也算不可逆動作。推送由主 session 在使用者當下同意後執行；開 PR 用確定性工具 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/publisher python3 .claude/teams/tools/publish.py push …`（只推 fork 的功能分支、推送前掃機敏值、寫 `publish-audit.jsonl`），以 publisher App 身分開 PR，但每一次仍要使用者當下同意。本專案**不採**模版的「無人值守時，經 run.json 已核准的 deliver 段即可推送」：run.json 的閘門核准不能取代當下同意。主 session 不直接推到 `guard.config.json` 的 `protected_branches`（`main`），改推功能分支再開 PR。gh 寫入動作要明確寫 `--repo s96cax98leo/meeting-harness`；不用 curl、Invoke-RestMethod、Invoke-WebRequest 直接對 GitHub API 寫入。由 `awf_hook.py guard-shell` 擋（agent 執行 publish.py 也擋）；伺服器端由使用者設定的 ruleset 禁止直接推 main（步驟見 `specs/auto-merge/runbook.md`），ruleset 生效前推送沒有 PR 緩衝。
3. **不可逆節點一律停下**：push、開 PR、寫上游、刪資料、對外寄送、force push，都要使用者當下同意；先前的同意不延伸到下一次。push 與開 PR 依規則 2；合併依規則 6。
4. **禁止路徑只能讀**：`guard.config.json` 的 `forbidden_paths`（/Users/yuktang/Documents/Agent/PersonalAgent,/Users/yuktang/Documents/Agent/AgentWorkFlow）不得寫入、移動、刪除。由 `awf_hook.py` 的 `guard-paths`、`guard-shell` 擋。
5. **機敏檔不讀、不印**：`.env`、金鑰、憑證不讀值、不印出、不提交，也不在本機搜尋或借用別處的 API key、token。要判斷有無只能用 `grep -q`；push 前用 `grep -qF -f <機敏值清單> <diff>` 比對 diff 是否含機敏值，只報「有／沒有」。
6. **核准與合併 PR 依風險分級**：(a) **核准**：agent 與主 session 一律不核准（`gh pr review --approve`、API 送 APPROVE 都算），沒有例外。(b) **自動合併**：只有 `guard.config.json` 的 `auto_merge.enabled` 為 true 時，`auto_merge.merger_role`（預設 `agent-workflow:dev-merge-steward`，比對含命名空間的完整 agent_type）才能對 `auto_merge.repos` 白名單內、風險等級不超過上限的 PR 執行 `gh pr merge --match-head-commit <sha>`，而且 `merge_gate.py` 對同一個 head SHA 的最後判定必須是 merge、沒有凍結旗標（`auto_merge.freeze_file`）、上游 repo 要有 `upstream_authorized_by` 授權人。auto_merge 的設定變更只走 PR＋CODEOWNERS，由人核准。(c) **其餘一律由人合併**：auto_merge 未啟用、gate 判 hold／escalate、高風險路徑（CI、`.github/`、`.claude/`、hooks、依賴、migration、release、auth、CODEOWNERS）、上游未授權。主 session 一樣不合併；`gh api` 或 curl 打 merge 端點也算。由 `awf_hook.py guard-shell` 擋（Bash 與 PowerShell 都擋）；hook 只是輔助，真正的邊界是 GitHub ruleset 與綁定 gate App 的 required check，見 `docs/自動合併信任模型.md`（AgentWorkFlow 模版）。本專案的例外、核准紀錄與營運規則（身分、token、名稱掃描、測試數、交人合併、凍結）見〈專案規則〉的「自動合併（auto_merge）」條目。
7. 改目標 repo 時，那個 repo 自己的規範（CLAUDE.md、分支規範、REVIEW.md、hooks）照樣適用；hooks 會轉呼叫 repo 自己的 `guard-git`、`guard-paths`（`.py` 或 bash 腳本）。

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
16. **先 plan、後動手**：開發走 AI-native SDLC：intent → design → spec → plan →（測試與實作，先後依開發規範 profile）→ verifier →（設計／安全審查）→ PR 審查 → 人核准。各段做法（產出文件、需求寫法、測試時機、驗證方式）與專案慣例（code style、commit、分支命名、PR 大小、文件格式）由開發規範 profile（`.claude/teams/methodology.json`，init 時依使用者的習慣產生）決定，模版只管流程與閘門。本專案 plan、design、test、deliver 四個閘門都要使用者核准才進下一段，不用 `--by policy`（模版允許 design、test、deliver 在專案政策允許時改用政策核准，本專案不採）；之後的 merge 段不設人工閘門，由確定性的 `merge_gate.py` 判定，判定不是 merge 就交使用者；核准用 `save_run.py approve` 記錄，並在對話裡列重點，不只依賴工具狀態。
17. **決策者的回覆照字面讀**：「調整」不是「核准」；附帶意見要先處理再請求核准。
18. **commit**：格式照開發規範 profile 的 `conventions.commit`（預設 profile 是 Conventional Commits、scope 放 Story ID）；結尾署名行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。`check_rules.py --git` 檢查署名行；profile 有設 `check_regex` 時也檢查標題格式。本專案 epic 的 commit 在署名行之前加 `Spec-Epic: <epic>` trailer（merge gate 的 requirements adapter 依它找 spec，見〈專案規則〉的「自動合併（auto_merge）」條目）。
19. **分支**：新分支只用 `guard.config.json` 的 `allowed_branch_prefixes`（feature/,bugfix/,hotfix/,release/,merge/）；子任務分支 `feature/<epic>--<sub>`，各開 worktree，檔案所有權不重疊；整合用整合分支，依相依順序合併。不 force push、不 `--no-verify`。建議的分支名不合規時改用允許的前綴並註明。
20. **測試失敗就改程式，不改測試**；不加 skip、fixme、retry，不放寬斷言。上游測試不改；例外要使用者核准，並記錄在 spec 的「整合修訂與例外」。
21. **改寫 commit 歷史前留備份分支**；改寫後更新文件中引用的 SHA。

### 交件
22. **每個 agent 都以 JSON 信封交件**（`.claude/teams/schemas/envelope.schema.json`）：
    - Workflow 裡由 `schema` 強制。
    - 用 Agent 工具派出時，回報最後要附一個 ```json 區塊，`awf_hook.py envelope` 會驗證。
23. **成果一律寫成檔案，信封只放路徑。** 有 blocking 問題時 `status` 不能是 `done`；blocking 問題要附 2–3 個選項與代價。
24. **審查者只讀，只看證據，不採信作者的自述。** 慣例類的審查標準（PR 大小、code style、commit 格式、分支命名）引用開發規範 profile 的 `conventions`，profile 設為 null 的項目不檢查。 退回最多 2 次，超過交給人；無人值守時改為 park（寫進 run.json 並推播使用者，不等待）。合併通道裡不確定就 hold：agent 的發現只能讓結果變嚴，skeptic 不得推翻 blocker／important。
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
- **自動合併（auto_merge）**：規則 6 在本專案的例外與營運規則。核准人：使用者，2026-10-28（auto-merge epic 閘門 1、2；設定值與偏離見 `specs/auto-merge/spec.md` §3、§6 與 `specs/auto-merge/adr/`）。`auto_merge.enabled` 先維持 false，最後由人經 PR 與 code owner 核准改成 true。
  - **範圍**：`repos` 只有 `s96cax98leo/meeting-harness`，風險上限 `medium`（偏離信任模型的「只開 low」，見 `specs/auto-merge/adr/adr-am-ci-scope.md`）；`merge_method` 為 `merge`；`daily_cap` 為 3。
  - **身分**：steward 的四種寫入（`gh pr comment`、`gh pr merge`、`gh pr review --request-changes`、`gh pr ready --undo`）一律加前綴 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`，並明確帶 `--repo s96cax98leo/meeting-harness`；合併一律 `--merge --match-head-commit <40 碼>`；讀取指令不加前綴。主 session 開 PR 用 publisher 身分（規則 2）。
  - **token**：只有主 session 執行 `gh_app_token.py`（`tools/merge_gate_project/gh_app_token.py`；使用者當下同意的 sdlc-merge 或 publish 前 mint，結束後 revoke）。agent 不執行它；`~/.config/meeting-harness/gh/` 底下的檔 agent 不讀、不印、不複製（hook 擋不到，只能靠本規則）。私鑰只放 macOS Keychain，不落地成檔案。
  - **gate 輸入留言**：steward 先把留言寫到暫存檔，跑 `python3 tools/merge_gate_project/scan_names.py <檔>`；回 0 才貼，回 1 或 2 不貼、判 hold，回報時不印命中內容。名稱清單預設在主工作區 `_tpm/runs/client-names.txt`（不進 repo），由主 session 在使用者同意後一次性建立（`specs/auto-merge/runbook.md` 第 3 步）。
  - **驗證證據與測試數**：CI 綠不等於 verify 綠：required check `ci-ubuntu-subset` 只是 verify 的子集，merge 判定的驗證證據仍來自本機 verifier 跑的 verify 指令。`tests_before`／`tests_after` 是 `python3 -m unittest discover -s tests/record -t .` 與 `python3 -m unittest discover -s tests/governance -t .` 的 `Ran N tests` 相加；`tests/governance_once/` 與 Swift 測試不算。
  - **需求來源**：requirements adapter（`tools/merge_gate_project/reqs_from_spec.py`）依 `Spec-Epic` trailer 從 `origin/main` 讀 `specs/<epic>/spec.md`。沒有自己 spec 的 bugfix PR 以 `Spec-Epic` 指向它修的 epic，需求為該 epic 全部條目，不允許縮小（spec §4.3.13）。
  - **交人合併**：auto_merge 未啟用、或 gate 判 hold／escalate 時由人合併：使用者看過 PR，改到 CODEOWNERS 路徑的先以 code owner 核准，再以 admin 身分在 PR 合併畫面 bypass ruleset C 合併（merge commit；只限經 PR，ruleset A 不能 bypass）。程序見 `specs/auto-merge/runbook.md`。
  - **凍結**：凍結＝使用者 suspend merger App 的安裝（只停自動合併，人仍能手動合併，ruleset 不放寬）；解凍＝恢復安裝，由人執行。本機 `_tpm/runs/auto-merge.freeze.json` 只是 client 端減速帶。
  - **合併後**：主工作區不自動 pull（`~/.claude/skills/meeting-*` 是 symlink 回主工作區，pull 等於發佈全域 skill）；由使用者或主 session 在使用者同意後 pull。每次判定記在 `_tpm/runs/merge-audit.jsonl`；合併後跑 `event-post-merge`。
  - **守門設定**：`auto_merge.enabled` 為 true 後，主 session 也不直接改 `guard.config.json`、`merge-audit.jsonl`、`publish-audit.jsonl`；要改 `guard.config.json` 一律走 PR 與 code owner 核准。agent 任何時候都不改這三個檔。

### 規則 ↔ 強制方式

由 `/correct`（`correct` skill）維護：把重複出現的錯誤變成強制機制時加一列。層級：1 架構／確定性工具、2 schema／hook／lint、3 測試、4 文件；只能停在文件層的，強制方式寫「僅文件」。

| 規則 | 強制方式 | 層級 | 證明擋得住的指令 |
|---|---|---|---|

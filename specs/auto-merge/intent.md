# intent：auto-merge（PR 經 merge_gate 判定後由 dev-merge-steward 自動合併）

- epic：`auto-merge`；分支 `feature/auto-merge`，worktree `.worktrees/auto-merge`，從 `origin/main` @ `e72a9cb` 開（PR #10 合併點）。
- 狀態：**草稿（修正輪 1），待閘門 1 核准**。本輪依使用者 2026-10-28 在閘門 1 的決定（§5.1 D1–D4）與 skeptic 的六節判定修訂。核准後本檔不再改；要改就回報主 session。
- 需求來源：使用者在對話裡口述（本 repo 沒有上層任務系統，`.claude/teams/rules.md` 專案規則「需求來源」）。原話與出處整理在 run 目錄的 `research-requirement.md` §2：
  - 2026-10-25：「你可以合併」→「調整hook」→「走auto_merge」，並在選項式提問中選「#9 先手動合，auto_merge 開新 epic (Recommended)」（`research-requirement.md:23-29`）。
  - 2026-10-28：「核准，開始跑 (Recommended)」，核准的是開跑 sdlc-plan，**不是閘門 1**（`research-requirement.md:30-31`）。`run.json` 五段當時都是 `pending`，開跑核准只在對話裡（`research-requirement.md:129`）。
  - 2026-10-28：使用者在閘門 1 對 Q1–Q4 與方向做了決定（§5.1）；閘門 1 本身尚未核准。
- 規範來源（只讀）：AgentWorkFlow `docs/自動合併信任模型.md`（下稱「信任模型」，205 行）與 `docs/adr-agent-auto-merge.md`（下稱「上游 ADR」）。升級基準釘在 AgentWorkFlow `23174f0`（2026-10-26，merge_gate 最近一次改動；`research-upstream.md:48-49`）。
- 調研依據：run 目錄 `_tpm/runs/20261028-sdlc-auto-merge/` 的 `research-requirement.md`（136 行）、`research-specs-adr.md`（151 行）、`research-code-contracts.md`（152 行）、`research-upstream.md`（63 行）。run 目錄不在版控（`.gitignore:41`）。
- `specs/_templates/intent.md` 不存在（`ls specs/` 只有 `auto-merge`、`meeting-record`、`meeting-speed`），本檔用 fallback 五節格式。
- 本檔的 G1–G8（目標）、D-1–D-9（既有決策）、D1–D4（使用者閘門 1 決定）、C1–C8（衝突）、Q1–Q7（問題）只是本檔內引用，**不是任務編號**。
- 行號以 main @ `e72a9cb` 與 AgentWorkFlow @ `23174f0` 為準；引用 research-*.md 的行號已逐條以 `wc -l`、`grep -n` 重新核對。範例場次名一律用「[Stand-up] 範例專案」。

---

## 1. 問題

### 1.1 每個 PR 都要使用者自己到 GitHub 按合併

- 現行規則禁止 agent 合併：`.claude/teams/rules.md:15`（通用規則 2，推送要使用者當下同意）、`:19`（通用規則 6「核准與合併 PR 只能由人做」）、`CLAUDE.md:16`〈不可逆節點〉「agent 不推送、不合併、不 approve」。2026-10-25 主 session 要合併 PR #9 時被 hook 擋下（`research-requirement.md:24`）。
- 使用者的動機是「不必每次自己去 GitHub 按合併」（`research-requirement.md:33`）。使用者**沒有**給數值目標（自動合併比例、每日上限）；風險等級上限由使用者在閘門 1 定為 medium（D1）。

### 1.2 本工作區的 scaffold 版本太舊，沒有 auto-merge 的元件

- 缺 `merge_gate.py`、`publish.py`、`checklist.py`、`sdlc-merge.js`、`event-post-merge.js`、`merge-decision` 等 3 個 schema、`methodology.json`（`research-code-contracts.md:10`、`:22-26`）。
- `guard.config.json` 缺 `protected_branches`、`main_session_github_rules`、`team_agent_namespaces`、`extension_agents`、`auto_merge`、`requirements` 六組鍵（`research-code-contracts.md:28`）。
- 只補新檔不夠：新 `merge_gate.py:401` 依賴新版 `schemalib`（`compose("merge-decision")`、`merge_decision_errors`），本地 `schemalib.py` 差 141 行，會新舊混用（`research-code-contracts.md:68`）。

### 1.3 伺服器端是空白狀態

- 沒有 ruleset、main 沒有 branch protection、沒有任何 Actions workflow、沒有 `.github/`、`allow_auto_merge=false`、`delete_branch_on_merge=false`（`research-upstream.md:31-40`）。
- 信任模型明寫「hook 只是輔助，伺服器端才是邊界。沒有完成第 2 節的 ruleset 與 App 設定前，不要啟用 `auto_merge`」（信任模型:15）。
- merge_gate 在沒有任何 required check 時判 hold（`merge_gate.py:482-483`）。本 repo 沒有 CI，所以就算啟用，每個 PR 也都會 hold。

### 1.4 本 repo 的條件和信任模型的預設不完全對得上

調研找到八個結構性落差（C1–C8），詳見 §4.3；這裡只列結論：
- 依風險分級，就算白名單開到 medium（D1），改到 `.claude/`、`.github/` 的 PR 仍一律 escalate；本 repo 的產品檔就在 `.claude/skills/meeting-*`（C1）。
- 單人個人帳號下，CODEOWNERS 與「作者不能核准自己的 PR」會互卡，D3 以 publisher App 解（C2）。
- 既有測試與 verify 指令大多要 macOS、MPS、本機模型與名稱清單，GitHub-hosted ubuntu 跑不了；`bin/_lint.sh` 在 ubuntu 上第一天就會紅（C4）。
- requirements adapter 的預設格式對不到本 repo 的 spec（C5）。

---

## 2. 期望結果

閘門 1 核准的是「做什麼」；做法（逐檔對照、ruleset JSON、adapter 腳本與解析規則、CI YAML、私鑰保管）由 design 段決定。

- **G1 scaffold 升級到 AgentWorkFlow `23174f0`**，而且不無聲推翻本地定案：
  - `rules.md` 的〈專案規則〉段（`rules.md:50-68`）與本地改寫過的規則逐條保留或明確修訂（`research-code-contracts.md:27`、`:52`）。
  - `sdlc-build.js` 本地修正「implementer 不改 progress.md」（D-8）要保留或經使用者核准後改掉（`research-specs-adr.md:54-56`、`:64-68`）。
  - `meeting-pipeline.js` 不被動到（`research-code-contracts.md:26`、`:60`）。
  - 升級產出可審查的 diff，不是無聲整檔覆蓋。升級方式見 Q6。
- **G2 GitHub-hosted ubuntu 上至少一個 Actions job 當 required check**（D2），在 public repo 上可持續跑綠，而且不需要客戶名稱清單離開本機（D-2）：
  - 只跑明確列出的子集：修好的 `bin/_lint.sh`，加上在 Linux 實測會綠的測試；`meeting.sh doctor`、Swift 測試、mlx 路徑、名稱掃描不進 CI。
  - **required check ≠ 專案 verify**：CI 綠不代表 `bash bin/_lint.sh && bash bin/meeting.sh doctor` 綠，merge 判定的驗證證據仍來自本機 verifier（D-3）。
  - **前置（在本 epic 範圍內）**：修 `bin/_lint.sh` 的兩個問題——`grep -nP`（`bin/_lint.sh:14`、`:16`）在 macOS BSD grep 上靜默失效，以及自身 `:15`、`:20` 的 `$f：` 寫法在 GNU grep 上會命中自己（C4）。
- **G3 requirements adapter 能為每個要走 gate 的 PR 取得對應 spec 的驗收條件清單**，輸出 `merge_gate.py` 可用的格式；C5、C6 列出的本 repo spec 結構特性都要有明確的處理方式。解析規則與讀取來源由 design 段定（讀取來源暫定見 Q5）。
- **G4 伺服器端設定到位**，照信任模型 §2–§4 做；做不到或決定偏離的地方寫 ADR 說明偏離與理由：
  - ruleset（形式見 Q7）、**gate、merger、publisher 三個 App**（D3）、CODEOWNERS，並開 Require review from Code Owners（D3）；
  - App 擁有者、私鑰保管人、撤銷人、事故聯絡人寫進 ADR（信任模型:45）；
  - 三把私鑰怎麼保管、本機怎麼取 installation token，以及這和「金鑰不讀、不印」硬規則（`CLAUDE.md`〈機敏檔〉）的關係，由 design 段定（D3）。
- **G5 `guard.config.json` 的 `auto_merge` 與 `requirements` 鍵**依 D1–D4、Q5 設定：
  - `repos` 白名單 `{"s96cax98leo/meeting-harness": "medium"}`（D1，偏離信任模型:79、:202，寫 ADR）；
  - `merger_role="agent-workflow:dev-merge-steward"`；
  - `merge_method="merge"`（D4）；
  - `daily_cap`、`freeze_file` 用保守值，數值由 design 段定；
  - `requirements` 指向 G3 的 adapter；
  - `enabled` 先維持 false，最後一步由人經 PR＋CODEOWNERS 改成 true（G8）。
  - 這些鍵 agent 寫不了（任何位置的 `.claude/teams/guard.config.json` 都一樣，含 worktree，`research-code-contracts.md:92`），只能由主 session 在啟用前改，或由人改。
- **G6 合併路徑**：`dev-merge-steward` 經 `sdlc-merge` 跑 `merge_gate.py`，判 merge 才執行 `gh pr merge --match-head-commit <40 字元 SHA> --merge`；每次判定寫 `_tpm/runs/merge-audit.jsonl`（欄位見信任模型 §5；hook 放行的 8 個條件見 `research-requirement.md:64-73`）。
- **G7 啟用後的權限邊界寫進規則**：主 session 不再執行 `gh pr merge`、不直接改 `guard.config.json` 與稽核紀錄（信任模型:58）。`rules.md` 規則 2、6 與 `CLAUDE.md`〈不可逆節點〉同步改寫，例外與核准人寫在〈專案規則〉（`rules.md:6` 要求放寬時寫明例外與核准人）。
- **G8 啟用前檢查清單 11 項逐項有證據**（信任模型:193-203），全部在本 epic 範圍內，包括：
  - :200「merge 與 release 脫鉤」：寫明合併到 `origin/main` 後，本機主工作區由誰、何時 pull（見 §3 對 `~/.claude/skills/meeting-*` 的說明）；
  - :201「合併後訊號存在（main CI），`event-post-merge` 能讀到」：main 上要有 post-merge 的 CI 訊號，`event-post-merge` 能讀到；
  - :202「`repos` 只開 low」：依 D1 改為 medium，證據是 ADR 的偏離紀錄與使用者決定；
  - :203「經 PR＋CODEOWNERS 把 `enabled` 改成 true」是最後一步，由人執行。
  - 預期第一個實際走 gate 的是一個測試 PR（純文件、≤100 行）。驗收判準：該 PR 跑出 `agent-merge-gate/decision`，並由 steward 合併；或依 gate 判定 hold／escalate，結果與 `merge-audit.jsonl` 一致。

**預期覆蓋範圍（依 D1，白名單開到 medium）**：
- `risk_tier`（`merge_gate.py:339-356`）：改到 SENSITIVE 路徑（`merge_gate.py:74-90`，含 `.github/`、`.claude/`、`guard.config.json`、CODEOWNERS）或超過 400 行／20 檔判 high；全是文件或全是測試、而且合計 ≤100 行判 low（`:354`）；其餘判 medium。
- 回推近期 PR（`research-requirement.md:103-106`、`research-code-contracts.md:136`）：
  - #9（README，25 行）是 low → 在自動合併範圍；
  - #10（`bin/lib/_asr_worker.py`＋測試，59 行）是 medium → 在自動合併範圍；
  - #8（meeting-speed epic，改 `.claude/skills/meeting-*`、行數大）是 high → 仍要人合併；
  - 任何改 `.github/`、`.claude/` 的 PR（含本 epic 自己的所有 PR、所有改 `.claude/skills/meeting-*` 的功能 PR）→ 一律 escalate，仍要人合併。
- 「在自動合併範圍」不等於一定自動合：gate 還要求需求清單讀得到（信任模型:178）、有 required check 且全綠、有本機驗證證據。像 #10 這種沒有 spec 的 bugfix，需求清單讀不到時一律 hold；能不能納入，取決於 design 段對「無 spec PR」的處理（C5）。

---

## 3. 受影響的使用者與系統

| 對象 | 影響 | 依據 |
|---|---|---|
| 使用者（唯一的人類維護者，`s96cax98leo`） | 在個人帳號下建立 gate、merger、publisher 三個 App 並保管三把私鑰；設定 ruleset；以 code owner 身分核准 publisher 開的治理檔 PR；啟用後 high 等級與被 escalate 的 PR 仍手動合併 | 信任模型:36-45；D1、D3 |
| 主 session | 啟用後不能 `gh pr merge`、不能 approve、不能直接 push main、不能直接改 `guard.config.json` 與稽核紀錄；開 PR 改經 publisher App 身分 | 信任模型:58、:197；D3 |
| `agent-workflow:dev-merge-steward`（新角色） | 唯一能執行 `gh pr merge` 的身分，以 merger App 身分合併；它的定義在 AgentWorkFlow `plugin/agents/dev-merge-steward.md`（禁區，只讀） | 信任模型:92-101；`dev-merge-steward.md:26` |
| `publish.py`（模版檔，升級後新增） | 依 D3 改用 publisher App 身分開 PR（現行用 `gh` 的使用者身分，`research-requirement.md:110`）；它是模版檔，在本 repo 怎麼改或包裝由 design 段定；team agent 不能執行它（`guard.py:921-922`） | D3 |
| `.claude/teams/`（rules.md、guard.config.json、tools/、schemas/、golden-set/、methodology.json） | init 升級新增或覆蓋；rules.md 要手動合回專案內容 | `research-code-contracts.md:22-28`、`:36-68` |
| `.claude/workflows/sdlc-*.js`、`event-*.js` | 13 支更新、新增 `sdlc-merge.js`、`event-post-merge.js`；`meeting-pipeline.js` 不動 | `research-code-contracts.md:26`、`:58-60` |
| `CLAUDE.md` | 〈不可逆節點〉要改寫；init 會在結尾追加 `@.claude/teams/agent-workflow.CLAUDE.md` | `research-code-contracts.md:30`、`:62` |
| `bin/_lint.sh` | 本 epic 修正（G2 前置）：`grep -nP` 在 macOS 靜默失效，自身 `:15`、`:20` 的 `$f：` | `research-code-contracts.md:128-129`；`bin/_lint.sh:14-20` |
| `.github/`（新增） | CI workflow、`agent-merge-gate.yml`（`--with-merge-gate`）、`CODEOWNERS` | `research-code-contracts.md:32` |
| `specs/*/spec.md` | adapter 的讀取對象；spec 格式不改（D-7 的 §6 例外要能被讀到） | `research-code-contracts.md:100-103` |
| GitHub repo 設定 | ruleset、三個 App 的安裝、Actions secret／variable；`allow_auto_merge`、`delete_branch_on_merge` 是否要改另議 | `research-upstream.md:31-40` |
| `~/.claude/skills/meeting-*` | 介面語意不變；但六個 skill 是 symlink 指回主工作區，改 repo 裡的 `SKILL.md` 等於改全域（`rules.md:68`）。自動合併只改 `origin/main`，主工作區不 pull 就不會變；**若「合併後自動 pull」，就等於 steward 合併一個 PR 即自動發佈到全域 skill**，違反信任模型:200「merge 與 release 脫鉤」。所以 G8 要寫明 pull 由誰、何時做；本 intent 的方向是合併後不自動 pull | `research-requirement.md:131`；信任模型:200 |
| **不受影響** | `bin/meeting.sh` 子指令與結束碼、五條鐵則、`vault/` | `research-code-contracts.md:18` |

---

## 4. 限制

### 4.1 硬限制（不得推翻）

1. **伺服器端先於 client 端**：ruleset 與 App 沒完成前，`auto_merge.enabled` 維持 false（信任模型:15、:194-196）。
2. **agent 不寫守門設定**：`guard.config.json`、`merge-audit.jsonl`、凍結檔一律不由 agent 寫（`guard.py:917-918`、`:983-986`；主 session 在啟用後也不能寫，`:919-920`、`:987-988`）。design 拆子任務時，這幾項要排給主 session（啟用前）或人。
3. **不可逆節點不變**：push、開 PR、改 GitHub 設定、建 App 一律由使用者當下同意（`CLAUDE.md`〈不可逆節點〉）。本 epic 的 build、test 只在本機與 worktree 做；伺服器端設定寫成操作步驟，由使用者執行或當下逐步同意。
4. **客戶名稱清單不離開本機**（D-2）：清單只放 run 目錄（`specs/meeting-record/spec.md:770` §4.14.3），不放 GitHub secret，也不放進 CI。
5. **機敏檔**：私鑰、`.env` 不讀、不印、不提交；agent 不碰 App 私鑰（`CLAUDE.md`〈機敏檔〉）。
6. **AgentWorkFlow、PersonalAgent 只讀**（`rules.md:53`）：模版本身的問題只回報，不改；這包括 `plugin/agents/dev-merge-steward.md` 與 `plugin/hooks/guard.py`。
7. **對外介面不破壞**：`bin/meeting.sh` 子指令與結束碼、`~/.claude/skills/meeting-*` 語意不變（`rules.md:68` 專案規則 7）。
8. **測試修改要逐條核准**（D-6，`rules.md:37`）：CI 子集排除某些測試時，只能「不放進 CI 清單」，不能改測試本身。

### 4.2 本 epic 會推翻或修訂的既有定案（閘門 1 核准本 intent 時一併確認；spec §6 逐條寫明取代關係）

| # | 既有定案 | 修訂方向 | 依據 |
|---|---|---|---|
| D-1 | 合併只能由人做（`rules.md:15`、`:19`、`CLAUDE.md:16`） | 改成「依風險分級：白名單內（≤medium，D1）、gate 判 merge 的 PR 由 steward 合併；其餘由人合併」，與模版新版規則 6 對齊 | 模版 `scaffold/.claude/teams/rules.md:19-20`；`research-specs-adr.md:21-25` |
| D-3 | verify＝`_lint.sh && meeting.sh doctor`，全靠本機 | verify 指令不變；新增「CI required check 是 verify 的子集」，**CI 綠不等於本 repo 的驗收綠**（D2） | `specs/meeting-record/intent.md:115`；`research-specs-adr.md:70-81` |
| D-5 | main 用 merge commit，progress 引用的子任務 SHA 可回查 | **不推翻**（D4）：`merge_method="merge"` | `research-specs-adr.md:42-45`、`:120-123` |
| D-8 | `sdlc-build.js` 的 implementer 不改 progress.md（本地修正 `7c9a3a0`） | 預設保留本地修正（升級後重套）；要跟模版改由使用者決定 | `research-specs-adr.md:54-56` |
| — | 通用規則 2「推送要使用者當下同意」 | 不放寬推送：steward 只合併，不 push；開 PR 改由 publisher App 身分執行，仍要使用者當下同意 | `rules.md:15`；`guard.py:921-922`；D3 |

### 4.3 結構性衝突（design 段要給解法，或寫 ADR 說明偏離）

- **C1 收益範圍**：見 §2「預期覆蓋範圍」。白名單開到 medium 後，`bin/`、`tools/` 的小改動進入範圍，但所有 `.claude/` 改動仍 high（`merge_gate.py:77`）。另外，5 支檔已有 `# noqa`／`type: ignore`，之後新增這類註解會觸發「放寬閘門」escalate（`research-specs-adr.md:117`）。
- **C2 個人帳號的 App 與 CODEOWNERS**（D3 已定方向）：
  - 信任模型要求「由組織擁有的 GitHub App」（:36），本 repo 是個人帳號；D3 決定三個 App 都建在個人帳號下，寫 ADR 說明偏離。
  - code owner 只有使用者本人；作者不能核准自己的 PR（GitHub 一般行為，文件出處未能確認，`research-requirement.md:110`）。D3 由 publisher App 開 PR，使 PR 作者 ≠ code owner，使用者才能核准。
  - CODEOWNERS 的涵蓋範圍要限在信任模型:198 列的治理路徑；若含萬用路徑，所有 PR 都要人核准，自動通道（required approvals 0，信任模型:22）就失效。具體路徑由 design 段定。
- **C3 ruleset 內部互斥**：信任模型:28「bypass list 留空，admin 也不例外」和 :29「Restrict updates 只讓 merger App 與人更新 main」衝突；GitHub 文件說 Restrict updates 只放行 bypass 名單。「經 PR 合併算不算 update」未能確認，要在測試 PR 上實測（`research-code-contracts.md:121`）。怎麼處理見 Q7。
- **C4 hosted CI 跑不了既有驗收**：
  - `doctor` 要本機模型與 MPS；Swift 測試要 macOS；`test_ms_docs.py::test_no_client_names_in_ms_files` 沒有清單就 FAIL（`tests/record/test_ms_docs.py:45-49`），而且依規定不得 skipped（`specs/meeting-speed/spec.md:389-395`）。D2 決定這些都不進 CI。
  - `bin/_lint.sh:14` 的 `grep -nP` 在 macOS 一直靜默失效；到了 GNU grep 上會命中自身 `:15`、`:20`，ubuntu 上必紅（`research-code-contracts.md:128-129`）。本 epic 修（G2 前置）。
  - 17 個測試檔初篩看起來不依賴 macOS、mlx、ffmpeg 與清單，但沒在 Linux 實跑過，未能確認（`research-code-contracts.md:131`）；CI 清單只收實測會綠的。
- **C5 adapter 對不到 spec**：
  - `DEFAULT_ID_PATTERN`（`merge_gate.py:106`）只認 `AC-1`／`REQ-1` 這類 ID，本 repo 用 `4.1.1` 表格列。
  - 靜態 `requirements.path` 只能指一份 spec，本 repo 每個 epic 一份。
  - 兩份 spec 條號互撞（都有 4.1.1）；meeting-record 一份 spec 累積多輪；有「（修正輪刪除）」與「（選做）」列；§6〈整合修訂與例外〉有已核准例外。
  - 沒有 spec 的 PR（如 #10 bugfix）讀不到需求就 hold（`research-specs-adr.md:90-110`）。
- **C6 CI 讀不到新 epic 的需求**：CI gate 從 base 分支讀需求（`agent-merge-gate.yml.tmpl:28-30`、checkout base `:89-92`），本 repo 的慣例是 spec 與實作同一個 PR 進 main，所以首個 PR 一定 hold（`research-code-contracts.md:115`）。→ Q5（暫定）。
- **C7 gate 輸入留言公開**：steward 在執行模式以 merger App 身分把 merge-decision、驗證證據、findings 貼成 PR 留言（`agent-merge-gate.yml.tmpl:32-36`、`dev-merge-steward.md:26`），在 public PR 上可能洩漏場次或名稱（`research-specs-adr.md:125-128`）。模版沒有名稱比對這一步。
  - 候選解法（由 design 段評估，不是本 intent 的限制）：(a) 貼留言前用本機清單做名稱比對，命中就 hold；(b) 限制留言內容只放 run 代號與數字等最低必要欄位。
  - 可行性未確認：`dev-merge-steward` 定義在 AgentWorkFlow（禁區，只讀），本 repo 不能改它。本 repo 能用什麼方式擴充（例如本 repo 的 workflow、專案規則或包裝腳本）、steward 會不會遵守，交 design 段查。
- **C8 凍結與每日上限只在本機有效**：
  - 凍結檔與 `merge-audit.jsonl` 在被 gitignore 的 `_tpm/runs/`，CI 的 gate 看不到。
  - CI 把 `--runs-dir` 指到 `$RUNNER_TEMP`（`agent-merge-gate.yml.tmpl:154`），每日上限永遠從 0 算（`research-code-contracts.md:119`）。
  - 信任模型把 hook 定為「低：client 端減速帶」（信任模型:13），凍結在本 repo 等於只剩低信任層。

### 4.4 範圍邊界

- **在範圍內**：G1–G8，含 `bin/_lint.sh` 修正（G2 前置）、`event-post-merge` 與 main 的 post-merge CI 訊號（G8，信任模型:201）、「merge 與 release 脫鉤」的本機 pull 規則（G8，信任模型:200）。
- **不在範圍內，列為衍生工作或後續**：
  - 把 `repos` 等級從 medium 再往上調（走 PR＋CODEOWNERS 另行升級）；
  - 上游 repo 授權（本 repo 沒有上游）；
  - 修 AgentWorkFlow 模版本身的問題（禁區）。
- **由 design 段定數值或細節**：`daily_cap` 數值；`delete_branch_on_merge`；CI 測試清單；adapter 解析規則；三把私鑰的保管方式。
- **未能確認、要在實作時實測**：
  - merger App（及 publisher App）的 installation token 在本機怎麼取得、私鑰放在哪：AgentWorkFlow 的 steward 定義、`sdlc-merge.js`、文件都沒有寫（`research-requirement.md:128`）；
  - gate App 權限，文件寫 Checks: write（信任模型:40），GitHub ruleset 頁寫 `statuses:write`（`research-requirement.md:114`）。
- **時序**：ruleset 上線前要確認沒有開著的 PR（調研時 0 個，`research-upstream.md:10`、`:56`）。

---

## 5. 問題與決定

### 5.1 已決（使用者 2026-10-28 決定）

- **D1 方向（原 Q3）——使用者 2026-10-28 決定**：繼續做；`repos` 白名單開到 **medium**，不是信任模型冷啟動建議的 low。
  - 這是**偏離信任模型 :79「冷啟動期只開 low」**（同時偏離 :22「自動合併通道只限最低風險等級」與 :202 檢查清單「`repos` 只開 low」）的決定，要寫進 ADR，核准人是使用者。
  - 代價：初期誤合併風險較高——`bin/`、`tools/` 的程式改動在沒有人審的情況下進 main，判定品質完全倚賴需求對照、本機驗證證據與 CI 子集；而 CI 子集不含 `doctor`、Swift、mlx（D2）。
  - 預期覆蓋範圍：依 `merge_gate.py:339-356` 回推，#9（low）、#10（medium）在自動合併範圍；#8（high）與任何改 `.github/`、`.claude/` 的 PR 仍要人合（詳見 §2「預期覆蓋範圍」，含「無 spec PR 會 hold」的但書）。
- **D2 CI（原 Q1）——使用者 2026-10-28 決定**：GitHub-hosted ubuntu，只跑明確列出的子集（修好的 `bin/_lint.sh`＋在 Linux 實測會綠的測試）；`doctor`、Swift、mlx、名稱掃描不進 CI。**required check ≠ 專案 verify**。macOS hosted runner 與 self-hosted runner 不採用（self-hosted 在 public repo 上會讓 fork 的 PR 在存有會議資料的 Mac 上執行程式，`research-code-contracts.md:124`）。
- **D3 App（原 Q2）——使用者 2026-10-28 決定**：在個人帳號下建三個 App——**gate、merger、publisher**。publisher 開 PR，使用者以 code owner 身分核准；開 **Require review from Code Owners**。
  - 偏離信任模型 :36「由組織擁有」，寫 ADR。
  - App 擁有者、私鑰保管人、撤銷人、事故聯絡人都是使用者本人，寫進 ADR；外洩時先撤銷 App 安裝再輪換金鑰（信任模型:45）。
  - **design 段要定**：三把私鑰的保管方式，以及 steward／publish 流程在本機取 token 時，怎麼和「金鑰不讀、不印」硬規則（`CLAUDE.md`〈機敏檔〉）相容。
- **D4 merge_method（原 Q4）——使用者 2026-10-28 決定**：`merge`（merge commit），不用 squash；D-5 不推翻，`specs/*/progress.md` 引用子任務 SHA 的慣例不變。

### 5.2 暫定（閘門 1 核准時可改）

#### Q5 CI gate 從哪裡讀新 epic 的需求（**暫定 A，閘門 1 核准時可改**）

使用者尚未回答，先採建議。

| 選項 | 代價 |
|---|---|
| A. 新 epic 的 spec 先單獨開 PR 合進 main，之後的實作 PR 再走 gate；command adapter 從 base 讀 spec（**暫定採用**） | 每個 epic 多一個 PR，也多一道順序；但需求由已合併的 base 決定，PR 不能自己改驗收條件 |
| B. command adapter 從 PR head 讀 spec | 流程不變；但等於 PR 自己決定自己的驗收條件，gate 的信任度下降 |
| C. spec-md 寫死 path | 不用寫腳本；但每換一個 epic 就要經 PR＋CODEOWNERS 改 `guard.config.json`，而且多輪 spec 會把所有輪次一起當成需求 |

註：spec PR 改的是 `specs/<epic>/*.md`，若全是文件且 ≤100 行屬 low，否則可能 medium 或 high；它在 D1 白名單內時也可能被自動合併，但 base 上還沒有這個 epic 的需求，gate 會 hold，實際仍由人合併。

### 5.3 待決（閘門 1 請使用者決定）

#### Q6 scaffold 怎麼升級：要不要用 `init.py --force`

`init.py --force` 會整份覆蓋 `rules.md`（含〈專案規則〉段）、`guard.config.json`（依 `workflow.config` 重新渲染）、`_tpm/runs/README.md` 與所有帶模版標記的 workflow、tools（AgentWorkFlow `init.py:15-17`；`research-code-contracts.md:11`、`:50-64`）。不加 `--force` 只補新檔，會新舊混用（`research-code-contracts.md:68`）。

| 選項 | 內容 | 代價 |
|---|---|---|
| A. 在 epic worktree 由主 session 跑 `init.py --force --with-merge-gate`（**建議**） | 先記 git 基準；以 AgentWorkFlow `23174f0` 為基準覆蓋；再把 `rules.md`〈專案規則〉段、本地改寫的規則、D-8 修正、`guard.config.json` 既有值逐條合回；重跑 `build.py` 與 golden-set；整個結果以 git diff 交使用者審 | 覆蓋面大，漏合一條就會無聲推翻本地定案，審查要逐條對照；`guard.config.json` agent 寫不了，覆蓋與合回都要主 session 做 |
| B. 不加 `--force`，只補新檔，再手動更新相依檔 | init 只新增 `merge_gate.py` 等；`schemalib.py`、`build.py`、`save_run.py`、`check_workflows.mjs` 手動從模版搬 | 不碰 `rules.md`、`guard.config.json`；但要自己判斷哪些檔有相依，漏搬一支就新舊混用，問題可能到合併時才出現 |
| C. 不用 init.py，逐檔從 `23174f0` 手動搬 | 完全手控 | 工作量最大；失去 init 的一致性（模版標記、methodology 渲染），之後再升級更難 |

建議 A：一次對齊模版，所有改動都在 worktree 的 diff 裡可審；合回清單在 spec 逐條列出，審查時逐條勾。

#### Q7 ruleset 怎麼滿足信任模型 §2 第 3、4 點（牽涉「admin 也不例外」）

信任模型:28 要 bypass 清空、admin 也不例外；:29 要 Restrict updates 只讓 merger App 與人更新 main；GitHub 的 Restrict updates 只放行 bypass 名單（C3）。三者不能在同一條 ruleset 同時成立。

| 選項 | 內容 | 代價 |
|---|---|---|
| A. 拆兩條 ruleset（**建議**） | ruleset A：Require PR、Code Owners、Dismiss stale、required check 綁 gate App，bypass 清空；ruleset B：Restrict updates、Block force pushes、Restrict deletions，bypass＝merger App＋admin | ruleset B 給 admin bypass，字面上偏離 :28「admin 也不例外」，要寫 ADR；不過 ruleset A 沒有 bypass，admin 仍要走 PR，偏離只限 B 那幾條。「經 PR 合併算不算 update」要在測試 PR 上實測，結果可能讓 ruleset B 的 bypass 名單要調整 |
| B. 只設一條 ruleset，不開 Restrict updates | ruleset A 的內容加上 Block force pushes、Restrict deletions，bypass 清空 | 符合 :28；偏離 :29。因為 Require PR 已擋直接推送，實際差異是「任何有 write 權限、能經 PR 合併的身分」都能更新 main；本 repo 只有使用者與三個 App |
| C. 一條 ruleset，bypass 只給 merger App | 符合 :29 的字面 | merger App 可繞過 PR 與 gate check 直接推送 main，偏離 :28 最嚴重；merger 私鑰外洩時衝擊最大。不建議 |

建議 A，並在測試 PR 上實測後把結果寫進 ADR；若實測顯示選項 B 的實際保護與選項 A 相同，再回報使用者改採選項 B。

### 5.4 不問、由 design 依預設處理的模糊點（閘門 1 可以推翻）

- **名稱掃描**：不上 CI，維持本機推送前做（D-2）。gate 輸入留言的處理見 C7 候選解法，由 design 段查可行性。
- **凍結**：伺服器端凍結先用「暫時停用 ruleset A 的 gate 規則或 App 安裝」的人工程序，design 段評估更好的機制（C8）。
- **本機 pull**：合併後主工作區不自動 pull；由使用者或主 session 在使用者同意後 pull（§3、G8）。
- **`rules.md` 引用的 hook 名稱**：舊名 `guard-paths.sh` 等，升級時順便改成實際的 `awf_hook.py`（`research-specs-adr.md:140-143`）。

---

## 6. 衍生工作（不編號）

- 衍生工作（不編號）：AgentWorkFlow `plugin/hooks/guard.py:921-922` 的 `publish.py` 比對會連帶擋到本 repo 的 `bin/publish.py`（meeting-publish skill）（禁區，只回報；`research-code-contracts.md:141`）。
- 衍生工作（不編號）：回饋 AgentWorkFlow，信任模型 §2 第 3、4 點（bypass 清空 vs restrict updates）與「組織擁有 App」在個人帳號的落地方式，以及 steward 貼留言前沒有名稱比對（C7）（禁區，只回報；`research-code-contracts.md:142`）。
- 衍生工作（不編號）：補 `.github/pull_request_template.md`；評估 `delete_branch_on_merge`（`research-upstream.md:61-62`）。
- 衍生工作（不編號）：建 App 後，用 App JWT 確認安裝狀態（使用者 token 查不到，`research-upstream.md:40`、`:63`）。

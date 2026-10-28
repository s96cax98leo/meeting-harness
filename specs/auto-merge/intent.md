# intent：auto-merge（PR 經 merge_gate 判定後由 dev-merge-steward 自動合併）

- epic：`auto-merge`；分支 `feature/auto-merge`，worktree `.worktrees/auto-merge`，從 `origin/main` @ `e72a9cb` 開（PR #10 合併點）。
- 狀態：**草稿，待閘門 1 核准**。核准後本檔不再改；要改就回報主 session。
- 需求來源：使用者在對話裡口述（本 repo 沒有上層任務系統，`.claude/teams/rules.md` 專案規則「需求來源」）。原話與出處整理在 run 目錄的 `research-requirement.md` §2：
  - 2026-10-25：「你可以合併」→「調整hook」→「走auto_merge」，並在選項式提問中選「#9 先手動合，auto_merge 開新 epic (Recommended)」（`research-requirement.md:24-31`）。
  - 2026-10-28：「核准，開始跑 (Recommended)」，核准的是開跑 sdlc-plan，**不是閘門 1**（`research-requirement.md:32-33`）。`run.json` 五段目前都是 `pending`，開跑核准只在對話裡（`research-requirement.md` §4 第 11 點）。
- 規範來源（只讀）：AgentWorkFlow `docs/自動合併信任模型.md`（下稱「信任模型」，205 行）與 `docs/adr-agent-auto-merge.md`（下稱「上游 ADR」）。升級基準建議釘在 AgentWorkFlow `23174f0`（2026-10-26，merge_gate 最近一次改動；`research-upstream.md:351-352`）。
- 調研依據：run 目錄 `_tpm/runs/20261028-sdlc-auto-merge/` 的 `research-requirement.md`、`research-specs-adr.md`、`research-code-contracts.md`、`research-upstream.md`。run 目錄不在版控（`.gitignore:41`）。
- `specs/_templates/intent.md` 不存在（`ls specs/` 只有 `meeting-record`、`meeting-speed`），本檔用 fallback 五節格式。
- 本檔的 G1–G8（目標）、D-1–D-9（既有決策）、C1–C8（衝突）、Q1–Q5（待決問題）只是本檔內引用，**不是任務編號**。
- 行號以 main @ `e72a9cb` 與 AgentWorkFlow @ `23174f0` 為準。範例場次名一律用「[Stand-up] 範例專案」。

---

## 1. 問題

### 1.1 每個 PR 都要使用者自己到 GitHub 按合併

- 現行規則禁止 agent 合併：`.claude/teams/rules.md:15`（通用規則 2「agent 一律不 push、不合併」）、`:19`（通用規則 6「核准與合併 PR 只能由人做」）、`CLAUDE.md`〈不可逆節點〉。2026-10-25 主 session 要合併 PR #9 時被 hook 擋下（`research-requirement.md:26`）。
- 使用者的動機是「不必每次自己去 GitHub 按合併」（`research-requirement.md:35`）。使用者**沒有**給任何數值目標（自動合併比例、每日上限、風險等級）。

### 1.2 本工作區的 scaffold 版本太舊，沒有 auto-merge 的元件

- 缺 `merge_gate.py`、`publish.py`、`checklist.py`、`sdlc-merge.js`、`event-post-merge.js`、`merge-decision` 等 3 個 schema、`methodology.json`（`research-code-contracts.md:173-177`）。
- `guard.config.json` 缺 `protected_branches`、`main_session_github_rules`、`team_agent_namespaces`、`extension_agents`、`auto_merge`、`requirements` 六組鍵（`research-code-contracts.md:179`）。
- 只補新檔不夠：新 `merge_gate.py:401` 依賴新版 `schemalib`（`compose("merge-decision")`、`merge_decision_errors`），本地 `schemalib.py` 差 141 行，會新舊混用（`research-code-contracts.md:217-219`）。

### 1.3 伺服器端是空白狀態

- 沒有 ruleset、main 沒有 branch protection、沒有任何 Actions workflow、沒有 `.github/`、`allow_auto_merge=false`、`delete_branch_on_merge=false`（`research-upstream.md:331-343`）。
- 信任模型明寫「hook 只是輔助，伺服器端才是邊界。沒有完成第 2 節的 ruleset 與 App 設定前，不要啟用 `auto_merge`」（信任模型:15）。
- merge_gate 在沒有任何 required check 時判 hold（`merge_gate.py:482-483`）。本 repo 沒有 CI，所以就算啟用，每個 PR 也都會 hold。

### 1.4 本 repo 的條件和信任模型的預設不完全對得上

調研找到八個結構性落差（C1–C8），詳見 §4.3；這裡只列結論：
- 照風險分級，冷啟動只開 low 時，近三個 PR 只有 #9 能自動合併（C1）。
- 單人個人帳號下，CODEOWNERS 加上 bypass 清空可能讓治理檔 PR 永遠合不了（C2）。
- 既有測試與 verify 指令大多要 macOS、MPS、本機模型與名稱清單，GitHub-hosted ubuntu 跑不了；`bin/_lint.sh` 在 ubuntu 上第一天就會紅（C3、C4）。
- requirements adapter 的預設格式對不到本 repo 的 spec（C5）。

---

## 2. 期望結果

閘門 1 核准的是「做什麼」；做法（逐檔對照、ruleset JSON、adapter 腳本、CI YAML）由 design 段決定。

- **G1 scaffold 升級到 AgentWorkFlow `23174f0`**，而且不無聲推翻本地定案：
  - `rules.md` 的〈專案規則〉段（`rules.md:50-68`）與本地改寫過的規則（1、2、4、6、7、9、11、15、16、18–20、24）逐條保留或明確修訂（`research-code-contracts.md:178`、`:203`）。
  - `sdlc-build.js` 本地修正「implementer 不改 progress.md」（D-8）要保留或經使用者核准後改掉（`research-specs-adr.md:54-56`、`:64-68`）。
  - `meeting-pipeline.js` 不被動到（`research-code-contracts.md:177`）。
  - 升級產出可審查的 diff，不是無聲整檔覆蓋。
- **G2 至少一個 GitHub Actions job 當 required check**，在 public repo 上可持續跑綠，而且不需要客戶名稱清單離開本機（D-2）。CI 範圍由 Q1 決定。前置：修好 `bin/_lint.sh` 的 `grep -P` 問題（C4）。
- **G3 requirements adapter 能從 `specs/<epic>/spec.md` 讀出驗收條件**：
  - 表格條號格式是 `4.x.y`，排除「（修正輪刪除）」列，並處理「（選做）」列；
  - 只取該 PR 所屬輪次；
  - §6〈整合修訂與例外〉的已核准例外不被判成未達成（C5）。
- **G4 伺服器端設定到位**，照信任模型 §2–§4 做；做不到的地方寫 ADR 說明偏離與理由：
  - ruleset、gate App、merger App、CODEOWNERS；
  - App 擁有者、私鑰保管人、撤銷人、事故聯絡人寫進 ADR（信任模型:45）。
- **G5 `guard.config.json` 的 `auto_merge` 與 `requirements` 鍵**：
  - `enabled`；
  - `repos` 白名單 `{"s96cax98leo/meeting-harness": "low"}`（冷啟動只開 low，信任模型:79）；
  - `merger_role="agent-workflow:dev-merge-steward"`；
  - `merge_method` 依 Q4；
  - `daily_cap`、`freeze_file` 用保守值。
  - 這些鍵 agent 寫不了（任何位置的 `.claude/teams/guard.config.json` 都一樣，含 worktree，`research-code-contracts.md:243`），只能由主 session 在啟用前改，或由人改。
- **G6 合併路徑**：`dev-merge-steward` 經 `sdlc-merge` 跑 `merge_gate.py`，判 merge 才執行 `gh pr merge --match-head-commit <40 字元 SHA> <merge_method 旗標>`；每次判定寫 `_tpm/runs/merge-audit.jsonl`（欄位見信任模型 §5；hook 放行的 8 個條件見 `research-requirement.md` §3.6）。
- **G7 啟用後的權限邊界寫進規則**：主 session 不再執行 `gh pr merge`、不直接改 `guard.config.json` 與稽核紀錄（信任模型:58）。`rules.md` 規則 2、6 與 `CLAUDE.md`〈不可逆節點〉同步改寫，例外與核准人寫在〈專案規則〉（`rules.md:6` 要求放寬時寫明例外與核准人）。
- **G8 啟用前檢查清單 11 項逐項有證據**（信任模型:193-203）。其中「以 PR＋CODEOWNERS 把 `enabled` 改成 true」是最後一步，而且由人執行。
  - 預期第一個實際走 gate 的是一個測試 PR（純文件、≤100 行）。
  - 驗收判準：該 PR 跑出 `agent-merge-gate/decision`，並由 steward 合併；或依 gate 判定 hold／escalate，結果與 `merge-audit.jsonl` 一致。

**預期效果（要讓使用者在閘門 1 確認）**：
- 照 `merge_gate.py:339-356` 的分級，只有「全部是文件或全部是測試、而且合計 ≤100 行」的 PR 是 low。
- 回推近期 PR：#9（README，25 行）是 low；#10（`bin/lib/_asr_worker.py`＋測試，59 行）是 medium；#8（meeting-speed epic）是 high（`research-requirement.md` §4 第 1 點、`research-code-contracts.md:287`）。
- 任何 `.claude/` 改動一律 high→escalate（`merge_gate.py:73-90`），但本 repo 的產品檔就在 `.claude/skills/meeting-*`（D-9）。
- **所以冷啟動後，多數功能與 bugfix PR 仍要人合併，本 epic 自己的 PR 也全部要人合併**（`research-specs-adr.md:112-118`、`:130-133`）。

---

## 3. 受影響的使用者與系統

| 對象 | 影響 | 依據 |
|---|---|---|
| 使用者（唯一的人類維護者，`s96cax98leo`） | 要在 GitHub 網頁建立 2 個（或 3 個，見 Q2）App、保管私鑰、設定 ruleset、核准治理檔 PR；啟用後 low 以外的 PR 仍手動合併 | 信任模型:36-45；`research-code-contracts.md:273` |
| 主 session | 啟用後不能 `gh pr merge`、不能 approve、不能直接 push main、不能直接改 `guard.config.json` 與稽核紀錄 | 信任模型:58、:197 |
| `agent-workflow:dev-merge-steward`（新角色） | 唯一能執行 `gh pr merge` 的身分，以 merger App 身分合併 | 信任模型:92-101 |
| `.claude/teams/`（rules.md、guard.config.json、tools/、schemas/、golden-set/、methodology.json） | init 升級新增或覆蓋；rules.md 要手動合回專案內容 | `research-code-contracts.md` §2 |
| `.claude/workflows/sdlc-*.js`、`event-*.js` | 13 支更新、新增 `sdlc-merge.js`、`event-post-merge.js`；`meeting-pipeline.js` 不動 | `research-code-contracts.md:177`、`:209-211` |
| `CLAUDE.md` | 〈不可逆節點〉要改寫；init 會在結尾追加 `@.claude/teams/agent-workflow.CLAUDE.md` | `research-code-contracts.md:181`、`:213` |
| `bin/_lint.sh` | 修 `grep -P` 在 macOS 靜默失效，以及自身第 15、20 行的 `$f：` | `research-code-contracts.md:279-280` |
| `.github/`（新增） | CI workflow、`agent-merge-gate.yml`（`--with-merge-gate`）、`CODEOWNERS` | `research-code-contracts.md:183` |
| `specs/*/spec.md` | adapter 的讀取對象；spec 格式不改（D-7 的 §6 例外要能被讀到） | `research-code-contracts.md:249-254` |
| GitHub repo 設定 | ruleset、App 安裝、Actions secret／variable；`allow_auto_merge`、`delete_branch_on_merge` 是否要改另議 | `research-upstream.md:331-343` |
| **不受影響** | `bin/meeting.sh` 子指令與結束碼、`~/.claude/skills/meeting-*`、五條鐵則、`vault/` | `research-code-contracts.md:169` |

---

## 4. 限制

### 4.1 硬限制（不得推翻）

1. **伺服器端先於 client 端**：ruleset 與 App 沒完成前，`auto_merge.enabled` 維持 false（信任模型:15、:194-196）。
2. **agent 不寫守門設定**：`guard.config.json`、`merge-audit.jsonl`、凍結檔一律不由 agent 寫（`guard.py:917-920`、`:983-986`）。design 拆子任務時，這幾項要排給主 session（啟用前）或人。
3. **不可逆節點不變**：push、開 PR、改 GitHub 設定、建 App 一律由使用者當下同意（`CLAUDE.md`〈不可逆節點〉）。本 epic 的 build、test 只在本機與 worktree 做；伺服器端設定寫成操作步驟，由使用者執行或當下逐步同意。
4. **客戶名稱不離開本機**（D-2）：清單只放 run 目錄（`specs/meeting-record/spec.md:770` §4.14.3），不放 GitHub secret。gate 輸入留言會公開貼在 public PR 上（`agent-merge-gate.yml.tmpl:31-36`），steward 貼留言前要先做名稱比對，命中就 hold（C7）。
5. **機敏檔**：私鑰、`.env` 不讀、不印、不提交；agent 不碰 App 私鑰（`CLAUDE.md`〈機敏檔〉）。
6. **AgentWorkFlow、PersonalAgent 只讀**（`rules.md:53`）：模版本身的問題只回報，不改。
7. **對外介面不破壞**：`bin/meeting.sh` 子指令與結束碼、`~/.claude/skills/meeting-*` 語意不變（`rules.md:68` 專案規則 7）。
8. **測試修改要逐條核准**（D-6，`rules.md:37`）：CI 子集排除某些測試時，只能「不放進 CI 清單」，不能改測試本身。

### 4.2 本 epic 會推翻或修訂的既有定案（閘門 1 核准本 intent 時一併確認；spec §6 逐條寫明取代關係）

| # | 既有定案 | 修訂方向 | 依據 |
|---|---|---|---|
| D-1 | 合併只能由人做（`rules.md:15`、`:19`、`CLAUDE.md`〈不可逆節點〉） | 改成「依風險分級：白名單內、gate 判 merge 的 PR 由 steward 合併；其餘由人合併」，與模版新版規則 6 對齊 | 模版 `scaffold/.claude/teams/rules.md:19-20`；`research-specs-adr.md:21-25` |
| D-3 | verify＝`_lint.sh && meeting.sh doctor`，全靠本機 | verify 指令不變；新增「CI required check 是 verify 的子集」，**CI 綠不等於本 repo 的驗收綠**，merge 判定的驗證證據仍來自本機 verifier | `specs/meeting-record/intent.md:115`；`research-specs-adr.md:70-81` |
| D-5 | main 用 merge commit，progress 引用的子任務 SHA 可回查 | 依 Q4：沿用 merge，或改 squash 並改引用慣例 | `research-specs-adr.md:42-45`、`:120-123` |
| D-8 | `sdlc-build.js` 的 implementer 不改 progress.md（本地修正 `7c9a3a0`） | 預設保留本地修正（升級後重套）；要跟模版改由使用者決定 | `research-specs-adr.md:54-56` |
| — | 通用規則 2「agent 一律不 push」 | 不放寬推送：steward 只合併，不 push；publish.py 開 PR 仍要使用者當下同意 | `rules.md:15`；`guard.py:921-922` |

### 4.3 結構性衝突（design 段要給解法，或寫 ADR 說明偏離）

- **C1 收益範圍小**：見 §2「預期效果」。另外，5 支檔已有 `# noqa`／`type: ignore`，之後新增這類註解會觸發「放寬閘門」escalate（`research-specs-adr.md:117`）。
- **C2 個人帳號的 App 與 CODEOWNERS**：
  - 信任模型要求「由組織擁有的 GitHub App」（:36），本 repo 是個人帳號。
  - code owner 與 PR 作者都是使用者本人，作者不能核准自己的 PR（GitHub 一般行為，文件出處未能確認，`research-requirement.md` §4 第 3 點）。
  - 開了 Require review from Code Owners，bypass 又清空時，改到 `.github/`、`.claude/` 的 PR 可能沒人能核准。→ Q2。
- **C3 ruleset 內部互斥**：信任模型:28「bypass list 留空」和:29「Restrict updates 只讓 merger App 與人更新 main」衝突。GitHub 文件說 Restrict updates 只放行 bypass 名單。可行的做法是拆成兩條 ruleset：A 不設 bypass，B 只做 restrict updates，bypass 給 merger App 與 admin。「經 PR 合併算不算 update」未能確認，要在測試 PR 上實測（`research-code-contracts.md:272`）。
- **C4 hosted CI 跑不了既有驗收**：
  - `doctor` 要本機模型與 MPS；Swift 測試要 macOS；`test_ms_docs.py::test_no_client_names_in_ms_files` 沒有清單就 FAIL，而且依規定不得 skipped（`specs/meeting-speed/spec.md:389-395`）。
  - `bin/_lint.sh:14` 的 `grep -nP` 在 macOS 一直靜默失效；到了 GNU grep 上會命中自身 `:15`、`:20`，ubuntu 上必紅（`research-code-contracts.md:279-280`）。
  - 17 個測試檔初篩看起來不依賴 macOS、mlx、ffmpeg 與清單，但沒在 Linux 實跑過，未能確認（`research-code-contracts.md:282`）。→ Q1。
- **C5 adapter 對不到 spec**：
  - `DEFAULT_ID_PATTERN`（`merge_gate.py:106`）只認 `AC-1`／`REQ-1` 這類 ID，本 repo 用 `4.1.1` 表格列。
  - 靜態 `requirements.path` 只能指一份 spec，本 repo 每個 epic 一份。
  - 兩份 spec 條號互撞（都有 4.1.1）；meeting-record 一份 spec 累積多輪。
  - 沒有 spec 的 PR（如 #10 bugfix）一律 hold（`research-specs-adr.md:90-110`）。
- **C6 CI 讀不到新 epic 的需求**：CI gate 從 base 分支讀需求（`agent-merge-gate.yml.tmpl:28-30`、`:86-91`），本 repo 的慣例是 spec 與實作同一個 PR 進 main，所以首個 PR 一定 hold（`research-code-contracts.md:264-266`）。→ Q5。
- **C7 gate 輸入留言公開**：留言含 merge-decision、evidence、findings，在 public PR 上可能外洩場次或名稱（`research-specs-adr.md:125-128`）。模版沒有名稱比對這一步，要在本 repo 擴充。
- **C8 凍結與每日上限只在本機有效**：
  - 凍結檔與 `merge-audit.jsonl` 在被 gitignore 的 `_tpm/runs/`，CI 的 gate 看不到。
  - CI 把 `--runs-dir` 指到 `$RUNNER_TEMP`，每日上限永遠從 0 算（`research-code-contracts.md:270`）。
  - 信任模型把 hook 定為「低：client 端減速帶」（信任模型:13），凍結在本 repo 等於只剩低信任層。

### 4.4 範圍邊界

- **在範圍內**：G1–G8。
- **不在範圍內，列為衍生工作或後續**：
  - 把 `repos` 等級從 low 往上調（信任模型要求走 PR＋CODEOWNERS 另行升級）；
  - 上游 repo 授權（本 repo 沒有上游）；
  - 修 AgentWorkFlow 模版本身的問題（禁區）。
- **待 design 段確認是否納入**（使用者沒提、派工單也沒涵蓋，但信任模型清單有列）：
  - `event-post-merge` 與 main 的 post-merge CI 訊號（信任模型:201）；
  - 「merge 與 release 脫鉤」：合併後本機 `main` 由誰、何時 pull，因為 `~/.claude/skills/meeting-*` symlink 指向主工作區，自動 pull 等於自動發佈到全域 skill（`research-requirement.md` §4 第 13 點）；
  - `daily_cap` 數值；
  - `delete_branch_on_merge`。
- **未能確認、要在實作時實測**：
  - merger App 的 installation token 在本機怎麼取得、私鑰放在哪：AgentWorkFlow 的 steward 定義、`sdlc-merge.js`、文件都沒有寫（`research-requirement.md` §4 第 10 點）；
  - gate App 權限，文件寫 Checks: write，GitHub ruleset 頁寫 `statuses:write`（`research-requirement.md` §4 第 5 點）。
- **時序**：ruleset 上線前要確認沒有開著的 PR（目前 0 個，`research-upstream.md:313`、`:359`）。

---

## 5. 待解問題（閘門 1 請使用者決定）

Q1–Q3 是派工單指定要問的三題；Q4、Q5 是調研發現、會影響範圍或驗收的兩題。都是選項式，附代價與建議。

### Q1 CI 範圍：required check 在哪裡跑、跑哪些

| 選項 | 內容 | 代價 |
|---|---|---|
| A. GitHub-hosted ubuntu，只跑明確列名的子集（**建議**） | `_lint.sh`（先修 C4）＋經 Linux 實跑確認可綠的測試清單；名稱掃描留在本機推送前做 | 免費、無本機風險；但 CI 只涵蓋一小部分，`doctor`、Swift、mlx、名稱掃描都不在 CI，「CI 綠」能證明的有限 |
| B. 另加 GitHub-hosted macOS arm64（macos-14） | 子集再加 Swift 測試與 ffmpeg 路徑；不支援 MPS，`doctor` 與真模型仍跑不了 | public repo 免費，但慢、排隊久；Swift 能否在 hosted 綠未實測 |
| C. self-hosted runner（使用者的 Mac） | 能跑完整 verify | GitHub 文件明說 public repo「幾乎不該」用 self-hosted：fork 的 PR 可在這台 Mac 上執行任意程式，而這台 Mac 有會議錄音、`vault/` 聲紋與客戶資料；違反鐵則 5 與客戶資料邊界的精神 |

建議 A。理由：B 增加的覆蓋不包含真正的瓶頸（MPS、模型），C 的風險落在最敏感的資料上。B 可列為後續。

### Q2 GitHub App 怎麼建、私鑰誰保管、CODEOWNERS 卡死怎麼解

信任模型要求兩個「組織擁有」的 App（gate App、merger App），而且 merger App 必須和 PR 作者不同身分（信任模型:36-43）。本 repo 是個人帳號、只有一位人類。

| 選項 | 內容 | 代價 |
|---|---|---|
| A. 個人帳號擁有兩個 App；使用者保管私鑰；不開「Require review from Code Owners」，治理檔 PR 靠 gate 一律 escalate 交人合併 | gate App 私鑰放 Actions secret；merger App 私鑰放本機 macOS Keychain，steward 取 token 的方式由 design 定 | 只要建 2 個 App；但少了伺服器端「code owner 核准」這道保證，偏離信任模型 §2、§4，要寫 ADR |
| B. 建第三個 publisher App 開 PR，使用者以 code owner 身分核准治理檔 PR（**建議**） | 同 A，另加 publisher App；`publish.py` 改用它的身分開 PR | 3 個 App、3 把私鑰，保管與輪換負擔最高；`publish.py` 是模版檔，改它要評估是否在本 repo 擴充 |
| C. 建一個 GitHub Organization，把 repo 轉進去，由組織擁有 App | 最貼近信任模型 | 要轉移 repo（URL 改變，`~/.claude/skills` 與 remote 都要調整）；單人組織仍有 CODEOWNERS 自我核准問題，還是要 A 或 B 的解法 |

所有選項的共同點：
- App 擁有者、私鑰保管人、撤銷人、事故聯絡人都是使用者本人，寫進 ADR。
- agent 不讀、不印私鑰。
- 外洩時先撤銷 App 安裝再輪換金鑰（信任模型:45）。

建議 B：它是唯一能同時保留「merger 身分 ≠ PR 作者」與「治理檔有人審」的做法。如果使用者覺得 3 把鑰匙負擔太大，退回 A，並寫 ADR。

### Q3 啟用後，所有 PR 只能走 sdlc-merge 或由人手動合併

啟用後主 session 不能再 `gh pr merge`（即使 `main_session_github_rules=false`，信任模型:197），也不能直接改 `guard.config.json`（信任模型:58）。這等於正式推翻 D-1，並改寫 `CLAUDE.md`〈不可逆節點〉。

| 選項 | 內容 | 代價 |
|---|---|---|
| A. 照信任模型啟用，白名單只開 low（**建議**） | low PR 由 steward 經 gate 合併；其餘（多數功能、bugfix、所有 `.claude/` 改動）由使用者在 GitHub 手動合併 | 自動化覆蓋率低（近三個 PR 只有 #9 符合）；「不必每次自己按」只在純文件或純測試的小 PR 上實現 |
| B. 只建好基礎設施，`enabled` 維持 false | 完成 G1–G6、G8 的前置項，先讓 gate 在 CI 上「只記錄、不合併」一段時間，再決定是否啟用 | 短期內使用者仍要每次自己按；好處是先看 gate 判定的實際分布，再決定白名單 |
| C. 啟用並把白名單開到 medium | `bin/`、`tools/` 的小改動也能自動合併 | 偏離信任模型冷啟動建議（信任模型:79）；`.claude/` 改動仍是 high，所以 epic 級 PR 還是要人合併 |

建議 A。理由：符合信任模型，使用者也能依 `merge-audit.jsonl` 的實績，之後經 PR 升級白名單。如果使用者想先觀察，選 B。

### Q4 `merge_method`：squash（模版預設）還是 merge

| 選項 | 代價 |
|---|---|
| A. `merge`（merge commit，沿用現況，**建議**） | main 歷史較雜；但 `specs/*/progress.md` 引用的 47 處以上子任務 SHA 仍可從 main 回查（D-5、規則 21），既有慣例不用改 |
| B. `squash`（模版預設，也是派工單寫的預設） | 歷史乾淨；但功能分支刪除後子任務 SHA 無法回查，progress 要改成引用 PR 編號加 squash SHA；squash 訊息也要符合 Conventional Commits 與署名行（`check_rules.py --git`） |

建議 A：本 repo 的 spec 與 progress 大量引用子任務 SHA（`research-specs-adr.md:42-45`）。

### Q5 CI gate 從哪裡讀新 epic 的需求

| 選項 | 代價 |
|---|---|
| A. 每個 epic 的 spec 先單獨開 PR 合進 main（純 `.md`），之後的實作 PR 再走 gate；adapter 用 command 腳本從 base 讀 `specs/<epic>/spec.md`（**建議**） | 每個 epic 多一個 PR，也多一道順序；但需求由已合併的 base 決定，PR 不能自己改驗收條件 |
| B. command adapter 用 `git show "$AWF_HEAD_SHA:specs/<epic>/spec.md"` 讀 PR head | 流程不變；但等於 PR 自己決定自己的驗收條件，gate 的信任度下降 |
| C. spec-md 寫死 path | 不用寫腳本；但每換一個 epic 就要經 PR＋CODEOWNERS 改 `guard.config.json`，而且多輪 spec 會把所有輪次一起當成需求 |

建議 A，搭配 command adapter。沒有 spec 的 bugfix PR（如 #10）會 hold、交人合併，這和 Q3-A 的預期一致。

### 不問、由 design 依預設處理的模糊點（閘門 1 可以推翻）

- **升級路線**：
  1. 先記錄 git 基準；
  2. 用 `init.py --force --with-merge-gate`，以 AgentWorkFlow `23174f0` 為基準；
  3. 把 `rules.md` 的〈專案規則〉段、本地改寫的規則、D-8 修正逐條合回；
  4. 重跑 `build.py` 與 golden-set。
  - 依據 `research-code-contracts.md:219`。init.py 由主 session 在 build 段執行，本段沒有執行。
- **名稱掃描**：不上 CI，維持本機推送前做（D-2）。steward 貼 gate 輸入留言前加名稱比對，命中就 hold（C7）。
- **ruleset**：拆成兩條（C3），實測後寫 ADR。
- **凍結**：伺服器端凍結先用「暫時停用 ruleset A 的 gate 規則或 App 安裝」的人工程序，design 段評估更好的機制（C8）。
- **`rules.md` 引用的 hook 名稱**：舊名 `guard-paths.sh` 等，升級時順便改成實際的 `awf_hook.py`（`research-specs-adr.md:140-143`）。

---

## 6. 衍生工作（不編號）

- 衍生工作（不編號）：`bin/_lint.sh` 的 `grep -P` 在 macOS 靜默失效，自身 `:15`、`:20` 的 `$f：` 要改成 `${f}：`。這是既有缺陷，可以獨立成 bugfix；G2 依賴它。
- 衍生工作（不編號）：AgentWorkFlow `plugin/hooks/guard.py:921` 的 `publish.py` 比對會連帶擋到本 repo 的 `bin/publish.py`（meeting-publish skill）（禁區，只回報）。
- 衍生工作（不編號）：回饋 AgentWorkFlow，信任模型 §2 第 3、4 點（bypass 清空 vs restrict updates）與「組織擁有 App」在個人帳號的落地方式（禁區，只回報）。
- 衍生工作（不編號）：補 `.github/pull_request_template.md`；評估 `delete_branch_on_merge`（`research-upstream.md:364-365`）。
- 衍生工作（不編號）：建 App 後，用 App JWT 確認安裝狀態（使用者 token 查不到，`research-upstream.md:343`）。

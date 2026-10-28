# design：auto-merge

- 上游：`intent.md`（閘門 1 已核准，`_tpm/runs/20261028-sdlc-auto-merge/run.json` 的 `plan.approved`，2026-10-28）。
- 狀態：**修正輪 1，待閘門 2 核准**。使用者 2026-10-28 在閘門 2 前的決定 E1–E6 已寫入（對照表：`_tpm/runs/20261028-sdlc-auto-merge/design-revise-對照.md`）。
- ADR：`adr/adr-am-rulesets.md`（ruleset 拆法，修訂 D6；E1：使用者 2026-10-28 決定採三條）、`adr/adr-am-app-identity.md`（App、私鑰、token、凍結、C7）、`adr/adr-am-requirements.md`（adapter；E3：bugfix 採 N1）、`adr/adr-am-ci-scope.md`（CI 範圍、medium、數字輸入）。
- 行號以 main @ `e72a9cb`、AgentWorkFlow @ `23174f0` 為準；AgentWorkFlow 的檔案寫成 `scaffold/…` 或 `plugin/…`（相對 AgentWorkFlow 根目錄）。範例場次名一律用「[Stand-up] 範例專案」。
- G1–G8、D1–D7、C1–C8 沿用 intent 的代號，不是任務編號。

---

## 1. 為什麼要寫 design

有新介面（requirements adapter 的輸入輸出、token 工具的 CLI、steward 的指令格式）、跨系統（本機 hook、CI、GitHub ruleset、三個 App），而且有四組取捨（ADR）。

## 2. 全貌

```
                 ┌──────────── GitHub（伺服器端，真正的邊界）────────────┐
 publisher App ──┤ PR ─► ruleset A：要 PR、Code Owners 核准、禁 force/刪除（無 bypass）
 （主 session 開）│      ruleset C：required checks（bypass：admin，只限經 PR）
                 │        ├ ci-ubuntu-subset（GitHub Actions；pull_request 觸發）
                 │        └ agent-merge-gate/decision（gate App；pull_request_target＋留言觸發）
                 │      ruleset B：restrict updates（bypass：merger App、admin）
 merger App ─────┤ gate 輸入留言、gh pr merge --merge --match-head-commit
                 └──────────────────────────────────────────────────────┘
 本機：主 session ─ gh_app_token.py mint ─► ~/.config/meeting-harness/gh/<app>/hosts.yml（1 小時）
       sdlc-merge ─ dev-merge-steward（GH_CONFIG_DIR=…/merger gh …）─ merge_gate.py ─ reqs_from_spec.py
       hook（awf_hook.py）：只放行 steward、白名單、audit 最後一筆 merge、--merge、沒凍結
```

## 3. 元件與歸屬

| 元件 | 新／改 | 誰產出 | 依據 |
|---|---|---|---|
| scaffold 升級（`init.py --force --with-merge-gate` @ `23174f0`；含 `agent-workflow.CLAUDE.md`、`settings.json` 深度合併、`settings.README.md`、`.mcp.json.example`、`.mcp.README.md`、`_tpm/runs/README.md` 覆蓋） | 改 | 主 session（Build 前置 `m-upgrade`，plan §0 白名單檢查） | D5；`research-code-contracts.md:36-68`；`init.py:500-518` |
| `guard.config.json` 合回＋`auto_merge`、`requirements` 鍵 | 改 | 主 session（`m-upgrade`；agent 一律寫不了，`plugin/hooks/guard.py:917-918`、`:983-986`、`:500-502`） | G5；intent §4.1 第 2 條 |
| `rules.md`、`.claude/teams/README.md`、`CLAUDE.md` 合回與改寫 | 改 | `rules-merge` | G1、G7 |
| `methodology.json` merge 指引、commit trailer；`sdlc-build.js` 重套 D-8；`build.py` 重新內嵌 | 改 | `flow-merge` | G1、G6 |
| `bin/_lint.sh` | 改 | `lint-fix` | G2 前置 |
| `tools/merge_gate_project/reqs_from_spec.py` | 新 | `reqs-adapter` | G3 |
| `tools/merge_gate_project/gh_app_token.py`、`scan_names.py` | 新 | `app-tools` | G4、C7 |
| `.github/workflows/ci.yml`、`.github/CODEOWNERS` | 新 | `ci` | G2、G4 |
| `.github/workflows/agent-merge-gate.yml` | 新（模版原樣） | `m-upgrade`（`--with-merge-gate`） | G4 |
| `specs/auto-merge/runbook.md` | 新 | `runbook` | G4、G8 |
| `tests/governance/`（長期有效、CI 跑）、`tests/governance_once/`（升級當下才成立、只在本 epic 驗收時跑，E2） | 新 | `red-gov` | 全部 |
| GitHub：三個 App、Actions vars／secret、三條 ruleset、測試 PR、啟用 PR | 設定 | 使用者（主 session 只在使用者當下同意時協助讀回） | G4、G8；intent §4.1 第 3 條 |

**為什麼 dev agent 能改 `.claude/` 底下的檔**：hook 對 `dev-*` 的寫入範圍是「工作區相對路徑不以 `.claude/` 開頭」（`plugin/hooks/guard.py:996-1000`，`repos_dir` 空）；子任務 worktree 的路徑是 `.worktrees/auto-merge--<id>/.claude/…`，不受這條擋。唯一例外是任何位置的 `.claude/teams/guard.config.json`（`guard.py:500-502`），所以它只排給主 session。

**為什麼 Build 前置與伺服器端步驟用 `check`／`decision` 子任務、而且實作子任務不寫它們當 depends_on**：`sdlc-build.js` 只處理 `test`、`code`、`doc`（`.claude/workflows/sdlc-build.js:28-31`），分層時把其他 kind 的 id 當成「存在但未完成」，寫進 depends_on 會直接丟「相依有循環或缺項」（`:38-39`）。所以 `m-upgrade` 的先後關係寫在 plan §0（sdlc-build 開跑前由主 session 完成並 commit），不寫進 depends_on。

## 4. 合併路徑（G6）

1. 主 session（使用者當下同意）：`git fetch origin`；`gh_app_token.py mint --app merger`；複製名稱清單到 `_tpm/runs/client-names.txt`（一次性）。
2. 派 `sdlc-merge`（args 帶 `epic`、`requirements` 不帶，走 guard.config 的 command adapter）。
3. steward 分析：`reqs_from_spec.py` 從 `origin/main` 讀 `specs/<epic>/spec.md` → 逐條對照 → merge-decision。skeptic 挑戰。
4. steward 執行（methodology.json 的 merge 指引補上本 repo 的做法）：
   1. `gh pr checks <n> --repo s96cax98leo/meeting-harness --required --json name,state`：`agent-merge-gate/decision` 以外都完成才往下；沒完成就 `gh pr checks … --required --watch` 等。
   2. 留言寫到 `mktemp -d` → `python3 tools/merge_gate_project/scan_names.py <檔>`；回 0 才 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr comment <n> --repo s96cax98leo/meeting-harness --body-file <檔>`；回 1 或 2 不貼、判 hold、回報「留言含疑似名稱（或清單讀不到）」，不印命中內容。
   3. 本機 `merge_gate.py check`，`--checks` 用上一步的 JSON 去掉 `agent-merge-gate/decision`；`--tests-before`／`--tests-after` 依 `adr-am-ci-scope.md` 的定義。
   4. exit 0：等 `agent-merge-gate/decision` 對目前 head 轉 `SUCCESS`（`gh pr checks … --watch`），再 `GH_CONFIG_DIR=…/merger gh pr merge <n> --repo s96cax98leo/meeting-harness --merge --match-head-commit <sha>`；讀回 `gh pr view --json state,mergedAt,mergeCommit`。gate check 沒轉綠就不合併、判 hold。
   5. exit 1／3：照模版退回（request-changes、轉 draft，都帶 `GH_CONFIG_DIR=…/merger`）。
5. 主 session：`gh_app_token.py revoke --app merger`；跑 `event-post-merge`。

hook 這一層（`plugin/hooks/guard.py:411-447`）：`GH_CONFIG_DIR=<絕對路徑>` 前綴不含 `$(`、反引號、`<(`、`${`（`:289`），`_gh_pr` 用 shlex 切 token 後在任何位置找 `gh pr merge`（`:304-323`），預期放行；`ops-apps` 以實際 hook 判定驗證（spec §4.7.3）。

## 5. 交人合併的路徑

- 主 session 用 publisher 身分開 PR（`GH_CONFIG_DIR=…/publisher python3 .claude/teams/tools/publish.py push …`，使用者當下同意）。
- gate 判 hold／escalate → `agent-merge-gate/decision` 紅 → 使用者看過，改到 CODEOWNERS 路徑的先以 code owner 核准（PR 作者是 publisher App，使用者可以核准），再以 admin 身分在合併畫面 bypass ruleset C 合併（merge commit）。
- 這條路徑在 D6 原案下不存在（`adr/adr-am-rulesets.md`〈背景〉）；使用者 2026-10-28 決定採三條 ruleset（E1），admin 只能在經 PR 合併時 bypass C，A（含 Code Owners 核准）不能略過。
- 伺服器端效果的實測：直接推 main 被 A、B 同時擋（spec §4.7.11）；merger 合 gate 紅的 PR 被 C 擋（§4.7.8）；admin 經 PR bypass C 合併、順帶實測「經 PR 合併算不算 update」（§4.7.12）；Code Owners 核准不能被 admin 略過（§4.7.13）。

## 6. 上線順序（runbook 的骨架，G8）

| 步 | 誰 | 內容 | 不可逆？ |
|---|---|---|---|
| 1 | 使用者 | 合併本 epic 的 PR（此時還沒有 ruleset；`enabled=false`） | 是（推送、合併） |
| 2 | 使用者 | 建 gate、merger、publisher 三個 App，只安裝到本 repo；匯入私鑰；建 `gh-apps.json`；設 Actions vars／secret | 是（GitHub 設定） |
| 3 | 主 session（同意後） | `mint`／`gh api /installation/repositories` 讀回、hook 判定讀回（spec §4.7.1–§4.7.3） | 否（只讀＋本機） |
| 4 | 使用者 | 確認沒有開著的 PR，建 ruleset A、B、C（E1）；Actions 不准建立或核准 PR | 是 |
| 5 | 主 session（同意後）＋使用者 | 讀回 ruleset JSON 對照 spec §4.7.4；通過後使用者做探測推送（§4.7.11） | 讀回否；探測推送是（ruleset 設錯時會進公開 main） |
| 6 | 主 session＋使用者 | 測試 PR（`ops-trial`，spec §4.7.5–§4.7.8）；merger 試合被拒後，使用者以 admin bypass 合併（§4.7.12，不得關閉） | 是（推送、開 PR、留言、合併） |
| 7 | 主 session（同意後）＋使用者 | 開啟用 PR：`enabled: true`＋`specs/auto-merge/evidence/g8-checklist.md`；核准前 admin 合併應被拒（§4.7.13）；使用者以 code owner 核准、bypass C 合併 | 是 |
| 8 | 使用者 | 本機主工作區 pull（合併後不自動 pull，信任模型 :200） | — |

## 7. 威脅與剩餘風險

| 威脅 | 擋法 | 剩下的 |
|---|---|---|
| agent 冒充 steward 或改用 API 合併 | hook（`guard.py:411-447`）＋ruleset C（merger 不在 bypass） | hook 是低信任層；伺服器端仍要 gate 綠 |
| PR 改 gate、adapter、CI 或設定來放行自己 | CI 從 base 跑 gate 與 adapter（`agent-merge-gate.yml.tmpl:89-94`）；這些路徑一律 escalate（`merge_gate.py:74-91`）＋CODEOWNERS | 人 bypass 合併時沒看清楚 |
| gate 輸入留言洩漏名稱（C7） | `scan_names.py` 在貼之前比對 | steward 不照指引做（定義在禁區，只能靠規則與抽查）；清單沒涵蓋到的名稱 |
| token 被讀走 | 1 小時有效、每次 revoke、權限限縮到本 repo、檔案 0600 | 同一使用者的其他程序讀得到；agent 有 Read 工具，只能靠規則 |
| 自動合併後 main 壞掉 | `ci.yml` 在 push main 跑；`event-post-merge` 歸因；凍結＝suspend merger 安裝（D7） | CI 子集不含 doctor、Swift；本機 freeze 檔只是減速帶 |
| 合併即發佈全域 skill | 主工作區不自動 pull（rules.md〈專案規則〉） | 人 pull 前沒看合併內容 |

## 8. 子任務數量的理由

13 個：Build 前置 1（`m-upgrade`）、Red 1、實作 7（兩層）、伺服器端 4（明細見 plan §1）。

- 實作拆成 7 個是因為檔案歸屬天然分開而且能並行：`lint-fix`（`bin/`）、`reqs-adapter` 與 `app-tools`（同一目錄的不同檔，關注點不同，前者 CI 會執行、後者只在本機）、`rules-merge`（三份規則文件，同一批合回語意）、`flow-merge`（methodology 與 workflows：`build.py` 會重寫全部 `.claude/workflows/*.js`，必須同一個擁有者）、`runbook`（純文件）、`ci`（要等前面都合進來才能在容器裡實測子集，所以單獨一層）。
- `rules-merge` 不和 `flow-merge` 合併：一個是給人與 agent 讀的規則文字，一個是會被 `build.py` 重寫的機器檔，審查方式不同，而且能並行。
- 測試只開一個 `red-gov`，擁有整個 `tests/governance/`，避免同目錄多擁有者。
- 伺服器端四步（`ops-apps`、`ops-rulesets`、`ops-trial`、`ops-enable`）由使用者執行，sdlc-build 不處理；分成四個是因為各自有獨立的讀回證據與不可逆節點。

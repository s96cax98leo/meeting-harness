# ADR：main 的 ruleset 拆法與「交人合併」的通道

- 狀態：已決定（E1：使用者 2026-10-28 在 auto-merge 閘門 2 前決定採 B＋P1；本 ADR 修訂同日的 D6）
- 日期：2026-10-28
- 範圍：GitHub repo `s96cax98leo/meeting-harness` 的 rulesets（伺服器端設定，不在 repo 檔案裡）；操作步驟寫在 `specs/auto-merge/runbook.md`（build 段 `runbook` 子任務產出）。
- 偏離：信任模型（AgentWorkFlow `docs/自動合併信任模型.md`）:28「bypass list 留空，admin 也不例外」→ 本 repo 的 admin 可以略過 required check（ruleset C），只限經 PR 合併；:23「Require approval of the most recent reviewable push」→ ruleset A 不開。兩項偏離由使用者 2026-10-28 核准（E1）。

## 背景

- D6（intent §5.1）：拆兩條 ruleset。A 不設 bypass，含 Require a pull request、required status check（`agent-merge-gate/decision` 綁 gate App，加上 D2 的 CI job）、Require review from Code Owners、Block force pushes、Restrict deletions；B 只放 Restrict updates，bypass 給 merger App 與 admin。
- design 段讀程式後發現 D6 的 A 會讓「交人合併」整條路徑卡死：
  - CI 的 gate 把結果寫成 check run，`conclusion` 只有 gate exit 0（merge）時才是 `success`，hold（1）與 escalate（3）都是 `failure`（AgentWorkFlow `scaffold/.github/workflows/agent-merge-gate.yml.tmpl:177`、`:191`）。
  - hold 優先於 escalate（`scaffold/.claude/teams/tools/merge_gate.py:538`），`auto_merge.enabled=false` 時一律加一條 escalation（`merge_gate.py:515-516`）。
  - 所以 required check 綁 `agent-merge-gate/decision`、又沒有任何 bypass 時，**gate 判 hold／escalate 的 PR 誰都合不了**，包括人。本 epic 自己之後要合的「把 `enabled` 改成 true」PR（改 `guard.config.json`，`merge_gate.py:79` 判 SENSITIVE → escalate）就合不進去；啟用後所有 high 等級與改 `.claude/`、`.github/` 的 PR 也一樣（intent §2「預期覆蓋範圍」要它們「仍要人合併」）。
  - 信任模型本身同時要求「escalate 交人」與「admin 也不能 bypass」，兩者互斥；這是模版文件的問題（AgentWorkFlow 禁區，只回報，見衍生工作）。
- 另一個卡點：「Require approval of the most recent reviewable push」要求最後一次 push 由**別人**核准（GitHub 規則語意）。本 repo 的 push 一律由使用者的 git 身分做（agent 不 push，`guard.py:883-884`；publish.py 用本機 git 認證推送），使用者是唯一的 code owner，自己推的 commit 自己不能核准 → 改到 CODEOWNERS 路徑的 PR 永遠合不了。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 照 D6 兩條 ruleset（required check 放在無 bypass 的 A） | 和信任模型 :28 最接近 | gate 判 hold／escalate 的 PR 永遠合不了（含啟用 PR、所有 high 等級 PR）；等於要嘛不能上線，要嘛上線後只能靠暫停 ruleset 才能合，而暫停 ruleset 會放寬全部保護（D7 已拒絕這種做法） |
| B. **三條 ruleset**：A（無 bypass）只放 PR、Code Owners 核准、Block force pushes、Restrict deletions；B（Restrict updates，bypass＝merger App＋admin，模式 pull_request）；C（required status checks：`agent-merge-gate/decision` 綁 gate App、`ci-ubuntu-subset` 綁 GitHub Actions，strict；bypass＝admin，模式 pull_request） | 不改模版的 gate；steward（merger App）不在 C 的 bypass 內，一定要 gate 與 CI 都過；使用者以 admin 身分在 GitHub 合併畫面勾「bypass rules」就能合 escalate 的 PR，bypass 會留在 rule insights | admin 可以略過 required check（偏離 :28）；放寬只限「經 PR 合併」，A 仍擋直接 push、force push、刪 main，且 Code Owners 核准不能略過 |
| C. 兩條 ruleset，但改 CI 的 gate：PR 在目前 head 有 code owner 的 APPROVED review 時，把 escalate 的 check run 寫成 success | 不需要任何 bypass，和 :28 一致 | 要改 `.github/workflows/agent-merge-gate.yml`（模版檔，之後 `init.py --force --with-merge-gate` 會蓋回去，要每次重套）；gate 的判定邏輯搬進 YAML，違反範本「判定邏輯都在 merge_gate.py，不要搬進 YAML」（`agent-merge-gate.yml.tmpl:37`）；改了 gate 本身的信任根，審查成本最高 |

「最後一次 push 要別人核准」另外處理（三個選項都適用）：

| 選項 | 做法 | 代價 |
|---|---|---|
| P1. **不開** Require approval of the most recent reviewable push；保留 Dismiss stale approvals | 單一人類的 repo 下，「別人」不存在；新 commit 進來時舊核准仍會被撤銷，效果大致相同 | 偏離 :23 |
| P2. 開著，但所有 push 改由 publisher App 身分做 | 和 :23 一致 | publish.py 的 `git push` 用本機 git 認證（模版檔，`publish.py` 不在本 repo 改）；要另外設 git credential helper 讀 publisher token，等於讓 App token 進 git 設定，範圍擴大 |

## 決定

採 **B＋P1**（E1，使用者 2026-10-28）。

- **偏離信任模型 :28 的範圍**：admin（使用者本人）可以在 GitHub 合併畫面或以 gh 的 admin 合併選項略過 ruleset C 的 required check，但只限經 PR 合併（`bypass_mode: pull_request`）；ruleset A 沒有任何 bypass，所以直接 push、force push、刪 main、略過 Code Owners 核准都做不到。理由：gate 判 hold／escalate 時 check run 一律是 failure（`agent-merge-gate.yml.tmpl:177`），不留這個通道，escalate 的 PR 誰都合不了。每次略過都記在 rule insights，事後可查。

- ruleset A（`main-baseline`，無 bypass）：`pull_request`（required approvals 0、`require_code_owner_review: true`、`dismiss_stale_reviews_on_push: true`、`require_last_push_approval: false`）、`non_fast_forward`、`deletion`。
- ruleset B（`main-restrict-updates`）：`update`；bypass＝merger App（Integration）與 Repository admin role，`bypass_mode: pull_request`。
- ruleset C（`main-required-checks`）：`required_status_checks`（`strict_required_status_checks_policy: true`；`agent-merge-gate/decision` 的 `integration_id`＝gate App ID；`ci-ubuntu-subset` 的 `integration_id`＝GitHub Actions）；bypass＝Repository admin role，`bypass_mode: pull_request`。
- 三條都 `enforcement: active`、`target: branch`、`conditions.ref_name.include: ["~DEFAULT_BRANCH"]`。
- Actions 設定維持「不允許 GitHub Actions 建立或核准 pull request」（信任模型 :30）。
- 交人合併的流程（runbook 寫細節）：PR 由 publisher App 開 → gate 判 hold／escalate（check run 紅）→ 使用者看過 → 改到 CODEOWNERS 路徑的先以 code owner 核准 → 在 GitHub 合併畫面以 admin 身分 bypass C 合併（merge commit）。

## 後果

- steward 能合併的條件不變：C 的兩個 check 都要綠（merger App 不在 C 的 bypass），A 的 Code Owners 核准也不能略過。
- 人能合併任何 PR，但每次略過都要在合併畫面明確勾選，並記在 rule insights；這等於把「人是最後一道關」寫成伺服器端事實。
- 「經 PR 合併算不算 Restrict updates 的 update」（`research-code-contracts.md:121`，未能確認）：B 對 merger App 與 admin 都給 bypass，所以兩種答案下合併都能進行；答案只影響「沒有 bypass 的身分能不能合併」，在本 repo 沒有這種身分要合併。實測方式寫成可判定的驗收（spec §4.7）：
  - §4.7.11：admin 直接推 main 被拒，rule suite 同時有 A 的 `pull_request` 與 B 的 `update` 評估失敗（B 對 admin 只在經 PR 時放行、A 沒有 bypass）。
  - §4.7.8：merger App 的 token 直接呼叫 REST `PUT /repos/{owner}/{repo}/pulls/{n}/merge`（帶 head `sha`）合 gate 為 failure 的測試 PR，伺服器回 4xx、回應指出 required status check（`agent-merge-gate/decision`）沒有滿足、沒有提到 A 的規則，且試合前後 PR 都是 `OPEN`、試合前 `mergeStateStatus` 為 `BLOCKED`；merger 在 B 的 bypass 內、A 不要求核准，所以擋下的只能是 C。不用 `gh pr merge`，因為 gh 在 PR 為 `BLOCKED` 時先在 client 端擋下、不送請求。rule suite 的 C 評估失敗只當佐證。這一步打 merge 端點，hook 擋主 session 與 agent，由使用者在 Claude Code 以外的終端機執行。
  - §4.7.12：測試 PR 由 admin 經 PR bypass 合併（不得關閉），rule suite 結果是 `bypass`；B 的 `update` 評估結果原樣記入 g8-checklist，就是「經 PR 合併算不算 update」的答案。
  - §4.7.13：啟用 PR 在 code owner 核准前，admin 合併被拒（A 不能略過）。
- 不採選項 A 的原因：照 D6 原案，本 epic 只能交付到「ruleset 已設、`enabled` 仍為 false」為止，G8 最後一步（經 PR 把 `enabled` 改成 true）在伺服器端做不到。

# ADR：main 的 ruleset 拆法與「交人合併」的通道

- 狀態：提議（待 auto-merge 閘門 2 核准；**本 ADR 修訂使用者 2026-10-28 的 D6，要使用者重新決定**）
- 日期：2026-10-28
- 範圍：GitHub repo `s96cax98leo/meeting-harness` 的 rulesets（伺服器端設定，不在 repo 檔案裡）；操作步驟寫在 `specs/auto-merge/runbook.md`（build 段 `runbook` 子任務產出）。
- 偏離：信任模型（AgentWorkFlow `docs/自動合併信任模型.md`）:28「bypass list 留空，admin 也不例外」、:23「Require approval of the most recent reviewable push」。

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

## 決定（建議，待使用者在閘門 2 確認）

採 **B＋P1**。

- ruleset A（`main-baseline`，無 bypass）：`pull_request`（required approvals 0、`require_code_owner_review: true`、`dismiss_stale_reviews_on_push: true`、`require_last_push_approval: false`）、`non_fast_forward`、`deletion`。
- ruleset B（`main-restrict-updates`）：`update`；bypass＝merger App（Integration）與 Repository admin role，`bypass_mode: pull_request`。
- ruleset C（`main-required-checks`）：`required_status_checks`（`strict_required_status_checks_policy: true`；`agent-merge-gate/decision` 的 `integration_id`＝gate App ID；`ci-ubuntu-subset` 的 `integration_id`＝GitHub Actions）；bypass＝Repository admin role，`bypass_mode: pull_request`。
- 三條都 `enforcement: active`、`target: branch`、`conditions.ref_name.include: ["~DEFAULT_BRANCH"]`。
- Actions 設定維持「不允許 GitHub Actions 建立或核准 pull request」（信任模型 :30）。
- 交人合併的流程（runbook 寫細節）：PR 由 publisher App 開 → gate 判 hold／escalate（check run 紅）→ 使用者看過 → 改到 CODEOWNERS 路徑的先以 code owner 核准 → 在 GitHub 合併畫面以 admin 身分 bypass C 合併（merge commit）。

## 後果

- steward 能合併的條件不變：C 的兩個 check 都要綠（merger App 不在 C 的 bypass），A 的 Code Owners 核准也不能略過。
- 人能合併任何 PR，但每次略過都要在合併畫面明確勾選，並記在 rule insights；這等於把「人是最後一道關」寫成伺服器端事實。
- 「經 PR 合併算不算 Restrict updates 的 update」（`research-code-contracts.md:121`，未能確認）：B 對 merger App 與 admin 都給 bypass，所以兩種答案下合併都能進行；答案只影響「沒有 bypass 的身分能不能合併」，在本 repo 沒有這種身分要合併。runbook 的 `ops-trial` 用 merger App 身分試合一個 gate 為 failure 的 PR，預期被 C 擋下（證明 C 綁得住 merger App）。
- 若使用者維持 D6 原案（選項 A），本 epic 只能交付到「ruleset 已設、`enabled` 仍為 false」為止，G8 最後一步（經 PR 把 `enabled` 改成 true）在伺服器端做不到，要另外決定。

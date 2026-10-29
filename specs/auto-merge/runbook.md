# runbook：auto-merge 上線、凍結、私鑰外洩、交人合併

- 上游：`spec.md` §4.7（伺服器端與啟用前檢查）、`design.md` §5（交人合併）與 §6（上線順序）、`adr/adr-am-rulesets.md`、`adr/adr-am-app-identity.md`。
- 用途：deliver 之後，使用者照本檔把自動合併上線（G4、G8），以及之後的凍結與解凍、私鑰外洩、交人合併三段日常程序。
- 本檔不寫任何 App ID、installation ID、token 的實際值；一律用 `<gate App ID>`、`<merger App ID>` 這類佔位。實際值只存在 GitHub、使用者的 `~/.config/meeting-harness/gh-apps.json` 與 Keychain。
- 範例場次名一律用「[Stand-up] 範例專案」；證據檔、留言、PR 內文不得出現真實會議名稱、客戶名稱或視窗標題。

## 0. 共用約定

### 0.1 變數

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
REPO=s96cax98leo/meeting-harness
RUN=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/<本次上線的 run 目錄>
MERGER_DIR=/Users/yuktang/.config/meeting-harness/gh/merger
PUBLISHER_DIR=/Users/yuktang/.config/meeting-harness/gh/publisher
```

- 指令都在主工作區 `/Users/yuktang/Documents/Agent/meeting-harness` 執行，除非該步另外寫明。
- 讀回的輸出一律存進 `$RUN`（檔名寫在各步），不貼進 repo；存檔前確認不含 token（`gh api -i` 的回應標頭不含 token，但仍不要存 `hosts.yml` 的內容）。

### 0.2 角色與不可逆節點

- 「使用者」：`s96cax98leo` 本人；三個 App 的擁有者、私鑰保管人、撤銷人、事故聯絡人（`adr/adr-am-app-identity.md`〈角色〉）。
- 「主 session」：Claude Code 的主對話。它只在使用者**當下**同意後做讀回與本機操作；先前的同意不延伸到下一步。
- agent 不參與本檔任何一步。
- 「是否不可逆」寫「是」的步驟，執行前主 session 要停下，用選項式提問取得使用者當下同意。
- 打 GitHub 合併端點（`gh pr merge`、`gh api … /merge`）的動作，hook 對主 session 與所有 agent 一律擋；本檔凡是這類動作都由使用者在 **Claude Code 以外的終端機**執行。

### 0.3 執行順序（G8）

上線分 8 步（＝design §6）。spec §4.7 的條號是撰寫順序，**實際執行照 spec §4.7 開頭的「執行順序」表**，不照條號數字：

§4.7.1 → §4.7.2 → §4.7.3 → §4.7.4 → §4.7.11 → §4.7.5 → §4.7.6 → §4.7.7 → §4.7.8 → §4.7.12 → §4.7.9 → §4.7.10 → §4.7.13

| 步 | 條號 | 對應子任務 |
|---|---|---|
| 第 1 步 | （無） | — |
| 第 2 步 | （無；設定由下一步讀回） | `ops-apps` |
| 第 3 步 | §4.7.1、§4.7.2、§4.7.3 | `ops-apps` |
| 第 4 步 | （無；設定由下一步讀回） | `ops-rulesets` |
| 第 5 步 | §4.7.4、§4.7.11 | `ops-rulesets` |
| 第 6 步 | §4.7.5、§4.7.6、§4.7.7、§4.7.8、§4.7.12 | `ops-trial` |
| 第 7 步 | §4.7.9、§4.7.10、§4.7.13 | `ops-enable` |
| 第 8 步 | （無） | — |

任何一步的讀回不符：停在該步，不往下做；把讀回存進 `$RUN`，以選項式提問交使用者決定。

---

## 1. 上線順序

### 第 1 步：合併本 epic 的 PR

此時 GitHub 上還沒有 ruleset，`auto_merge.enabled` 是 false。

- **誰做**：使用者（合併）；主 session 只在使用者同意後讀回。
- **指令或畫面路徑**：
  - 畫面：GitHub → `s96cax98leo/meeting-harness` → Pull requests → 本 epic 的 PR → Merge pull request（選 **Create a merge commit**）。
  - 或使用者在 Claude Code 以外的終端機：`gh pr merge <n> --repo $REPO --merge`。
- **讀回方式**：
  - `gh pr view <n> --repo $REPO --json state,mergedBy,mergeCommit` 的 `state` 為 `MERGED`。
  - `git fetch origin && git show origin/main:specs/auto-merge/runbook.md | head -1` 印出本檔標題（確認本檔已在 main）。
  - `gh run list --repo $REPO --branch main --limit 3` 看得到 `ci.yml` 在 push main 觸發的 run。
  - 存檔：`$RUN/step1-pr-view.json`。
- **是否不可逆**：是（合併進公開的 `main`）。合併後**不要**在主工作區 pull，等第 8 步。

### 第 2 步：建三個 App、匯入私鑰、設 Actions

App 的權限與用途照 `adr/adr-am-app-identity.md`〈App 權限〉。

- **誰做**：使用者。
- **指令或畫面路徑**：
  1. 建 App（做三次：gate、merger、publisher）。畫面：GitHub 右上頭像 → Settings → Developer settings → GitHub Apps → New GitHub App。
     - Webhook：取消勾選 Active。
     - Where can this GitHub App be installed：Only on this account。
     - Repository permissions：
       - gate：Checks: Read and write、Pull requests: Read-only、Contents: Read-only、Metadata: Read-only。
       - merger：Contents: Read and write、Pull requests: Read and write、Metadata: Read-only。
       - publisher：Pull requests: Read and write、Contents: Read-only、Metadata: Read-only。
     - 建好後在 App 頁 → Install App → 只選 `meeting-harness`（Only select repositories）。
     - App 頁 → Private keys → Generate a private key，下載 `.pem`。
  2. 匯入 merger、publisher 的私鑰到 Keychain（使用者自己的終端機；匯入後刪除下載的 `.pem`）：

     ```
     security add-generic-password -U -a "$USER" -s meeting-harness.gh-app.merger -w "$(cat <下載的 merger .pem>)"
     security add-generic-password -U -a "$USER" -s meeting-harness.gh-app.publisher -w "$(cat <下載的 publisher .pem>)"
     rm <下載的 merger .pem> <下載的 publisher .pem>
     ```

  3. 建非機敏設定 `~/.config/meeting-harness/gh-apps.json`（App ID 在各 App 頁的 About 段）：

     ```
     {"merger": {"app_id": <merger App ID>}, "publisher": {"app_id": <publisher App ID>}}
     ```

  4. Actions vars／secret。畫面：repo → Settings → Secrets and variables → Actions：
     - Variables：`AGENT_GATE_APP_ID`＝`<gate App ID>`；`AGENT_MERGER_BOT`＝`<merger App 的 slug>[bot]`。
     - Secrets：`AGENT_GATE_APP_PRIVATE_KEY`＝gate 的 `.pem` 全文（貼完刪除下載的 `.pem`；gate 私鑰不進 Keychain）。
  5. Actions 不准建立或核准 PR。畫面：repo → Settings → Actions → General → Workflow permissions → 取消勾選「Allow GitHub Actions to create and approve pull requests」→ Save。
- **讀回方式**：本步的設定由第 3 步讀回。使用者本步自己先確認：
  - `security find-generic-password -s meeting-harness.gh-app.merger -w | head -c 26` 印出 `-----BEGIN RSA PRIVATE KEY` 或 `-----BEGIN PRIVATE KEY---`（只看開頭，不印私鑰本體；若印出十六進位字串，表示匯入格式不對，先停下）。publisher 同樣做一次。
  - `ls ~/Downloads/*.private-key.pem 2>/dev/null` 沒有輸出（下載的 `.pem` 已刪）。
- **是否不可逆**：是（GitHub 設定；私鑰一旦產生就要依〈私鑰外洩〉段管理）。

### 第 3 步：讀回 token、Actions 設定與 hook 判定

- **誰做**：主 session（使用者當下同意後）；`mint`／`revoke` 只有主 session 執行，agent 不執行、不讀 `~/.config/meeting-harness/gh/`。
- **指令或畫面路徑**：
  1. §4.7.1：token 取得與撤銷。

     ```
     $PY tools/merge_gate_project/gh_app_token.py mint --app merger
     GH_CONFIG_DIR=$MERGER_DIR gh api /installation/repositories --jq '.total_count'
     $PY tools/merge_gate_project/gh_app_token.py revoke --app merger
     GH_CONFIG_DIR=$MERGER_DIR gh api /installation/repositories --jq '.total_count'
     ```

     publisher 照做一次（`--app publisher`、`$PUBLISHER_DIR`）。
  2. §4.7.2：Actions vars／secret 與 workflow 權限。

     ```
     gh variable list --repo $REPO
     gh secret list --repo $REPO
     gh api repos/$REPO/actions/permissions/workflow
     ```

  3. §4.7.3：hook 判定。準備一個暫存專案目錄 `$T`（`mktemp -d`），在 `$T/.claude/teams/` 放一份守門設定（`auto_merge.enabled: true`、`merge_method: merge`，其餘照 main 上的版本），在 `$T/_tpm/runs/merge-audit.jsonl` 放一筆 `repo`＝`$REPO`、`pr`＝1、`head_sha`＝`<40 碼>`、`decision: merge` 的紀錄。hook 會擋 Claude Code 內寫入守門設定檔，所以 `$T` 由使用者在 Claude Code 以外的終端機準備，主 session 只執行下面的判定。三份 hook 輸入（`tool_name: Bash`，`cwd`＝`$T`）：
     - (a) `agent_type`＝`agent-workflow:dev-merge-steward`，`command`＝`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr merge 1 --repo s96cax98leo/meeting-harness --merge --match-head-commit <40 碼>`。
     - (b) 同 (a)，`--merge` 改 `--squash`。
     - (c) 同 (a)，`agent_type` 改成其他值（例如 `agent-workflow:dev-implementer`）。

     ```
     CLAUDE_PROJECT_DIR=$T $PY <agent-workflow plugin 目錄>/hooks/awf_hook.py guard-shell < $T/hook-a.json; echo "exit=$?"
     ```

     （b）、（c）照做。`<agent-workflow plugin 目錄>` 用 Claude Code `/plugin` 列出的安裝路徑。
  4. 名稱清單（一次性）：主 session 在使用者當下同意後，把現有的客戶名稱清單複製到**主工作區**的 `_tpm/runs/client-names.txt`（`scan_names.py` 的預設位置；`.gitignore` 的 `/_tpm/runs/*` 已排除，不進 repo）。不讀出、不印出清單內容。
- **讀回方式**：
  - §4.7.1：`mint` 後印 `1`；`revoke` 後同一指令失敗（非 0 結束碼）。存檔：`$RUN/step3-4.7.1.txt`（只存 `total_count` 與結束碼，不存 `mint` 以外的輸出）。
  - §4.7.2：variables 含 `AGENT_GATE_APP_ID`、`AGENT_MERGER_BOT`；secrets 含 `AGENT_GATE_APP_PRIVATE_KEY`（只看名稱）；`can_approve_pull_request_reviews` 為 `false`。存檔：`$RUN/step3-4.7.2.txt`。
  - §4.7.3：(a) `exit=0`；(b)、(c) `exit=2`。存檔：`$RUN/step3-4.7.3.txt`。
  - 名稱清單：`test -s _tpm/runs/client-names.txt; echo $?` 印 `0`，`git check-ignore -q _tpm/runs/client-names.txt; echo $?` 印 `0`。只用這兩個指令判斷，不讀內容。沒有這個檔時，第 6 步與啟用後 steward 的 gate 輸入留言一律被 `scan_names.py` 擋下（回 2、判 hold）。
- **是否不可逆**：否（只讀與本機；token 1 小時內失效，且本步最後已 `revoke`）。

### 第 4 步：建 ruleset A、B、C

ruleset 的內容照 `adr/adr-am-rulesets.md`〈決定〉（E1，B＋P1）。三條都是 `enforcement: active`、`target: branch`、`conditions.ref_name.include: ["~DEFAULT_BRANCH"]`。

- **誰做**：使用者（建立）；主 session 只在使用者同意後做開工前檢查。
- **指令或畫面路徑**：
  1. 開工前：`gh pr list --repo $REPO --state open` 應為空（有開著的 PR 就先處理，避免建 ruleset 當下有 PR 卡住）。
  2. 取得 GitHub Actions 的 integration id（給 C 用）：從第 1 步 main 上的 CI run 讀回 `gh api "repos/$REPO/commits/$(git rev-parse origin/main)/check-runs" --jq '.check_runs[]|{name,app:.app.slug,id:.app.id}'`，取 `ci-ubuntu-subset` 那一列的 `app.id`。
  3. 建三條 ruleset。畫面：repo → Settings → Rules → Rulesets → New ruleset → New branch ruleset；或使用者在自己的終端機把下面的 JSON 填入佔位後存成 `$RUN/ruleset-A.json` 等三個檔，執行 `gh api -X POST repos/$REPO/rulesets --input $RUN/ruleset-A.json`（B、C 同）。
     - **ruleset A `main-baseline`（沒有 bypass）**：Require a pull request before merging（Required approvals 0、勾 Require review from Code Owners、勾 Dismiss stale pull request approvals when new commits are pushed、**不勾** Require approval of the most recent reviewable push）、Block force pushes、Restrict deletions。

       ```
       {"name": "main-baseline", "target": "branch", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [],
        "rules": [
         {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "require_code_owner_review": true,
          "dismiss_stale_reviews_on_push": true, "require_last_push_approval": false, "required_review_thread_resolution": false}},
         {"type": "non_fast_forward"},
         {"type": "deletion"}]}
       ```

     - **ruleset B `main-restrict-updates`**：只有 Restrict updates；Bypass list 加 merger App 與 Repository admin role，兩筆都選 **For pull requests only**（`bypass_mode: pull_request`）。

       ```
       {"name": "main-restrict-updates", "target": "branch", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [
         {"actor_id": <merger App ID>, "actor_type": "Integration", "bypass_mode": "pull_request"},
         {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
        "rules": [{"type": "update"}]}
       ```

     - **ruleset C `main-required-checks`**：只有 Require status checks to pass（勾 Require branches to be up to date before merging）；兩個 check：`agent-merge-gate/decision` 的來源選 gate App、`ci-ubuntu-subset` 的來源選 GitHub Actions；Bypass list 只加 Repository admin role，選 **For pull requests only**。merger App **不得**出現在 C 的 bypass。

       ```
       {"name": "main-required-checks", "target": "branch", "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
        "rules": [{"type": "required_status_checks", "parameters": {"strict_required_status_checks_policy": true,
          "required_status_checks": [
           {"context": "agent-merge-gate/decision", "integration_id": <gate App ID>},
           {"context": "ci-ubuntu-subset", "integration_id": <GitHub Actions 的 integration id>}]}}]}
       ```

       `RepositoryRole` 的 `actor_id` 5 是 Repository admin；以 GitHub 畫面選到的值與第 5 步讀回為準。
- **讀回方式**：本步的設定由第 5 步的 §4.7.4 逐條讀回；本步只確認 `gh api repos/$REPO/rulesets --jq '.[].name'` 列出三個名稱。
- **是否不可逆**：是（GitHub 設定；建好後直接推 main 就會被擋）。

### 第 5 步：讀回 ruleset，通過後做探測推送

- **誰做**：讀回由主 session（使用者當下同意後）；探測推送由使用者在自己的終端機執行（另一次當下同意）。
- **指令或畫面路徑**：
  1. §4.7.4 讀回：

     ```
     gh api repos/$REPO/rulesets > $RUN/step5-rulesets.json
     gh api repos/$REPO/rulesets --jq '.[].id' | while read -r id; do gh api repos/$REPO/rulesets/$id; done > $RUN/step5-ruleset-detail.json
     ```

     逐條對照 spec §4.7.4：恰有 A、B、C 三條；A 的 `bypass_actors` 為空、`rules[].type` 恰為 `pull_request`、`non_fast_forward`、`deletion`、四個 `pull_request.parameters` 值相符；B 的 `rules[].type` 恰為 `update`、`bypass_actors` 恰為 merger App（`Integration`）與 admin（`RepositoryRole`）兩筆且 `bypass_mode` 都是 `pull_request`；C 的 `rules[].type` 恰為 `required_status_checks`、兩個 context 與 `integration_id` 相符、`strict_required_status_checks_policy` true、`bypass_actors` 恰為 admin 一筆且 `bypass_mode` `pull_request`。
  2. §4.7.11 探測推送（§4.7.4 全符合後才做）：

     ```
     git fetch origin
     BEFORE=$(git ls-remote origin refs/heads/main)
     git switch --detach origin/main
     git commit --allow-empty -m "chore(auto-merge): ruleset 探測推送（應被拒）"
     git push origin HEAD:refs/heads/main 2> $RUN/step5-probe-push.stderr
     AFTER=$(git ls-remote origin refs/heads/main)
     test "$BEFORE" = "$AFTER" && echo 相同
     git switch -
     ```

     被拒後這個空 commit 不在任何分支上，不必另外刪；不要 force push。
  3. rule suite 讀回：`gh api "repos/$REPO/rulesets/rule-suites?ref=refs/heads/main"` 找到這次推送的 id，再 `gh api repos/$REPO/rulesets/rule-suites/<id> > $RUN/step5-rule-suite.json`。
- **讀回方式**：
  - §4.7.4：上面的逐條對照全符合；不符就停下（不做探測推送），修 ruleset 後重做本步。
  - §4.7.11：推送被拒（stderr 有伺服器回的規則違反訊息）；`BEFORE`／`AFTER` 相同；rule suite 的 `result` 為 `fail`（不是 `bypass`），且 `rule_evaluations` 同時有 A 的 `pull_request` 為 `fail` 與 B 的 `update` 為 `fail`。沒有 rule suite 紀錄時，以推送 stderr 裡伺服器回的違反規則清單為準（spec §7 第 9 點 (b)）。
- **是否不可逆**：讀回否；探測推送**是**（ruleset 設錯時空 commit 會直接進公開的 `main`，不 force push 就撤不回）。

### 第 6 步：測試 PR（gate 判定、輸入留言、REST 試合被拒、admin bypass 合併）

測試 PR 只改 `specs/auto-merge/evidence/` 下的文件（≤ 100 行），不碰 CODEOWNERS 路徑；分支 `feature/auto-merge-trial`；commit 帶 `Spec-Epic: auto-merge` trailer。內文的範例場次名只用「[Stand-up] 範例專案」。

- **誰做**：主 session（使用者當下同意後：推分支、以 publisher 開 PR、以 merger 貼留言、讀回）；使用者（§4.7.8 的 REST 試合、admin bypass 合併）。
- **指令或畫面路徑**：
  1. §4.7.5 開 PR（publisher 身分）：

     ```
     $PY tools/merge_gate_project/gh_app_token.py mint --app publisher
     GH_CONFIG_DIR=$PUBLISHER_DIR $PY .claude/teams/tools/publish.py push …
     $PY tools/merge_gate_project/gh_app_token.py revoke --app publisher
     gh pr checks <n> --repo $REPO --required --watch
     ```

  2. §4.7.6 讀 gate 的 Actions log：`gh run list --repo $REPO --workflow agent-merge-gate.yml --limit 3`，再 `gh run view <run id> --repo $REPO --log > $RUN/step6-gate-log.txt`，找 gate 的 result JSON。
  3. §4.7.7 貼 gate 輸入留言（merger 身分，先過名稱掃描）：

     ```
     $PY tools/merge_gate_project/gh_app_token.py mint --app merger
     $PY tools/merge_gate_project/scan_names.py <留言暫存檔>
     GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr comment <n> --repo s96cax98leo/meeting-harness --body-file <留言暫存檔>
     $PY .claude/teams/tools/merge_gate.py check …
     ```

     `scan_names.py` 印「有」或「名稱清單讀不到」就不貼、停下。gate 重跑後再讀一次 log（`$RUN/step6-gate-log-2.txt`），並對照 `_tpm/runs/merge-audit.jsonl` 同一 head 的最後一筆。
  4. §4.7.8 REST 試合（三件事依序做）：
     - (1) 試合前讀回（主 session）：`gh pr view <n> --repo $REPO --json state,mergeStateStatus,headRefOid,statusCheckRollup,files > $RUN/step6-4.7.8-before.json`；`git ls-remote origin refs/heads/main > $RUN/step6-4.7.8-lsremote-before.txt`。
     - (2) 試合：**由使用者在 Claude Code 以外的終端機執行**（hook 擋主 session 與所有 agent 打合併端點），主 session 不執行這條、也不代為組指令執行。使用者先在自己的終端機執行 `gh_app_token.py mint --app merger`（或沿用上一小步主 session 取得、尚未撤銷的 merger token），再：

       ```
       GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh api -i -X PUT repos/$REPO/pulls/<n>/merge -f sha=<(1) 的 headRefOid> -f merge_method=merge > $RUN/step6-4.7.8-rest.txt 2>&1
       ```

       結果由使用者存檔或貼回。不要用 `gh pr merge` 試合（gh 在 PR 為 `BLOCKED` 時先在 client 端擋下，不送請求，證明不了伺服器端）。
     - (3) 試合後讀回（主 session）：同 (1) 再讀一次存成 `…-after.json`、`…-lsremote-after.txt`；有這次呼叫的 rule suite 就一併存。
     - 之後主 session `revoke --app merger`。
  5. §4.7.12 admin bypass 合併（§4.7.8 通過之後；不得改成關閉 PR）：使用者在 PR 頁 → Merge pull request 旁勾選 bypass rules（「Merge without waiting for requirements to be met」）→ Create a merge commit；或在 Claude Code 以外的終端機 `gh pr merge <n> --repo $REPO --merge --admin`。
- **讀回方式**：
  - §4.7.5：`ci-ubuntu-subset` 為 success，且有 `agent-merge-gate/decision` check run（`gh pr checks <n> --repo $REPO > $RUN/step6-4.7.5.txt`，記 check run URL）。
  - §4.7.6：result JSON 的 `requirements_source` 以 `command` 開頭；reasons 不含「需求清單指令」「沒有需求來源」，含「auto_merge 未啟用」；`decision` 為 `hold` 或 `escalate` 都算符合。
  - §4.7.7：重跑的 log 不含「沒有 merger App 貼的 gate 輸入」；本機 `merge-audit.jsonl` 的 `decision` 與 CI 的 decision 相同。
  - §4.7.8：(1) `state` `OPEN`、`mergeStateStatus` `BLOCKED`、rollup 裡 `agent-merge-gate/decision` 為 `FAILURE` 且 `ci-ubuntu-subset` 為 `SUCCESS`、`files` 都在 `specs/auto-merge/evidence/` 下；(2) HTTP 4xx（預期 405；409、422 也算拒絕），`message` 指出 required status check 沒有滿足（含 `agent-merge-gate/decision`，或只寫 required status check 一類字樣而 (1) 的 rollup 顯示未成功的 required check 只有它），不得提到 review、code owner、pull request 規則；(3) `state` 仍為 `OPEN`，`git ls-remote` 前後相同。判不出時照 spec §7 第 9 點 (a) 的備案停下以選項式提問交使用者，不拿 `gh pr merge` 的 client 端訊息當證據。若這次呼叫竟然合併成功：§4.7.8 判不符、§4.7.12 無法做，停下回報，修 C 後另開測試 PR 從 §4.7.5 重做。
  - §4.7.12：`gh pr view <n> --repo $REPO --json state,mergedBy,mergeCommit > $RUN/step6-4.7.12.json` 的 `state` 為 `MERGED`、`mergedBy.login` 為 `s96cax98leo`；合併 commit 有 2 個 parent（`git cat-file -p <mergeCommit.oid>` 有兩行 `parent`，先 `git fetch origin`）；這次合併的 rule suite `result` 為 `bypass` 且含 C 的 `required_status_checks` 評估；B 的 `update` 評估結果（`pass`／`fail`／沒有評估）原樣記下，供第 7 步寫進 g8-checklist。
- **是否不可逆**：是（推送分支、開 PR、留言、打合併端點、合併進公開的 `main`）。每個小步各自要使用者當下同意。

### 第 7 步：g8-checklist、啟用 PR、核准前合併被拒、核准後合併

- **誰做**：主 session（使用者當下同意後：寫 g8-checklist、推分支、以 publisher 開 PR、讀回）；使用者（code owner 核准、兩次合併嘗試）。
- **指令或畫面路徑**：
  1. §4.7.9 在分支 `feature/auto-merge-enable` 寫 `specs/auto-merge/evidence/g8-checklist.md`：逐項對應信任模型 :193-203 的 11 項，每項附證據（指令與結果，或 URL）；ruleset 那一項引用 §4.7.4、§4.7.8、§4.7.11、§4.7.12 的結果（含 §4.7.12 記下的 B `update` 評估）；:202 寫 `medium` 與 ADR 偏離；:200 寫「合併後不自動 pull」與 pull 由誰做（第 8 步）。不寫 App ID、installation ID、token 的實際值。
  2. 同一分支把守門設定的 `auto_merge.enabled` 由 false 改成 true（只改這一個值）。hook 擋 Claude Code 內寫守門設定檔，所以這一個值由使用者在自己的編輯器改並 commit；commit 帶 `Spec-Epic: auto-merge`。
  3. §4.7.10 以 publisher 身分開 PR（同第 6 步第 1 小步的 `mint`→`publish.py push`→`revoke`）。
  4. §4.7.13 核准前合併：使用者在 Claude Code 以外的終端機 `gh pr merge <n> --repo $REPO --merge --admin`，應失敗。
  5. 使用者以 code owner 核准：PR 頁 → Files changed → Review changes → Approve → Submit review。
  6. 核准後合併：使用者在 PR 頁勾 bypass rules 以 merge commit 合併，或在 Claude Code 以外的終端機 `gh pr merge <n> --repo $REPO --merge --admin`。
- **讀回方式**：
  - §4.7.9：g8-checklist 11 項齊全、每項有證據；`$PY tools/merge_gate_project/scan_names.py specs/auto-merge/evidence/g8-checklist.md` 印「沒有」。
  - §4.7.10：`gh pr diff <n> --repo $REPO --name-only` 只有守門設定檔與 `specs/auto-merge/evidence/g8-checklist.md`；`gh pr diff <n> --repo $REPO` 裡守門設定只有 `enabled` 一行由 false 改 true；`gh pr view <n> --repo $REPO --json author` 的作者是 publisher App；核准後 `gh pr view <n> --repo $REPO --json reviews` 有 `s96cax98leo` 的 `APPROVED`。
  - §4.7.13：核准前那次 `gh pr merge` 失敗，`gh pr view <n> --repo $REPO --json state` 仍為 `OPEN`；核准後合併成功，該次 rule suite 的 `result` 為 `bypass` 且 A 的評估都是 `pass`。結果存進 `$RUN/step7-4.7.13.txt`（合併後才有的證據不進 g8-checklist）。
  - 合併後主 session 只讀確認 main 上的 `auto_merge.enabled` 為 true，並在 main 的乾淨 worktree 跑一次 `$PY -m unittest discover -s tests/governance -t .`（應全綠）。
- **是否不可逆**：是（推送、開 PR、核准、合併；合併後自動合併正式啟用）。

### 第 8 步：本機主工作區 pull

合併後**不自動 pull**（信任模型 :200：merge 與 release 脫鉤）。主工作區的 `.claude/skills/meeting-*` 是全域 skill 的 symlink 來源，pull 等於發佈。

- **誰做**：使用者；或主 session 在使用者當下同意後執行。
- **指令或畫面路徑**：先看要進來的內容，再 pull：

  ```
  git -C /Users/yuktang/Documents/Agent/meeting-harness fetch origin
  git -C /Users/yuktang/Documents/Agent/meeting-harness log --oneline HEAD..origin/main
  git -C /Users/yuktang/Documents/Agent/meeting-harness diff --stat HEAD origin/main
  git -C /Users/yuktang/Documents/Agent/meeting-harness pull --ff-only origin main
  ```

- **讀回方式**：`git -C /Users/yuktang/Documents/Agent/meeting-harness rev-parse HEAD` 等於 `git -C /Users/yuktang/Documents/Agent/meeting-harness rev-parse origin/main`；之後跑 verify：`bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。
- **是否不可逆**：否（只改本機；但 pull 後全域 skill 立即改變，pull 前要看過 diff）。

---

## 2. 凍結與解凍

凍結＝**停用（suspend）merger App 的安裝**（D7、`adr/adr-am-app-identity.md`〈凍結〉）。效果：`gh_app_token.py mint --app merger` 失敗（exit 2）、已發出的 merger token 失效、steward 無法貼 gate 輸入留言或合併、CI gate 收不到輸入就 hold；人仍可照〈交人合併〉合併；ruleset 不放寬。**不要**用停用 ruleset 來凍結（會放寬全部保護）。

本機的 `auto_merge.freeze_file`（`_tpm/runs/auto-merge.freeze.json`）由 `event-post-merge` 的 freeze_writers 寫，只是 client 端減速帶；伺服器端的凍結以 suspend 為準。

### 2.1 什麼時候凍結

- 自動合併後 main 的 CI 紅、或 `event-post-merge` 判定由某次自動合併引起。
- 懷疑 merger token 或私鑰外洩（同時走〈私鑰外洩〉段）。
- 看到 steward 以使用者身分（不是 merger App）合併（spec §7 第 1 點）。
- 使用者想暫停自動合併的任何理由。

### 2.2 凍結步驟

- **誰做**：使用者（主 session 只讀回）。
- **畫面路徑**：GitHub 右上頭像 → Settings → Applications → Installed GitHub Apps → merger App → Configure → 頁面下方 Danger zone → Suspend。
- **讀回**：主 session 在使用者同意後執行 `$PY tools/merge_gate_project/gh_app_token.py mint --app merger`，應 exit 2（stderr 指出安裝已停用或 403）；本機 `$MERGER_DIR/hosts.yml` 不存在（若存在就 `revoke --app merger`）。在 `$RUN`（或當次事件的 run 目錄）記下凍結時間與理由。
- **是否不可逆**：否（可解凍），但凍結期間所有 PR 都要人合併。

### 2.3 解凍步驟

- **誰做**：使用者；先在 run 紀錄寫解凍理由（造成凍結的問題已修好、main 的 CI 已綠）。
- **畫面路徑**：同上 → merger App → Configure → Unsuspend。
- **讀回**：主 session 在使用者同意後 `mint --app merger`，`GH_CONFIG_DIR=$MERGER_DIR gh api /installation/repositories --jq '.total_count'` 印 `1`，再 `revoke --app merger`。若本機凍結檔是 `{"frozen": true, …}`，由使用者決定是否一併清除（agent 不寫）。
- **是否不可逆**：否。

---

## 3. 私鑰外洩

適用：merger、publisher、gate 任一 App 的私鑰（或 installation token）疑似外洩，例如 `.pem` 留在下載目錄被同步、出現在 log、終端機紀錄或任何 repo 檔。處理順序照信任模型 :45：**先撤銷安裝或停用，再輪換金鑰**。

- **誰做**：使用者（私鑰保管人、撤銷人、事故聯絡人都是使用者）；主 session 只讀回與記錄。
- **指令或畫面路徑**：
  1. 止血：對外洩的 App 執行 suspend（畫面路徑同〈凍結與解凍〉2.2）；外洩的是 merger 時，這一步同時就是凍結。
  2. 輪換：App 設定頁（Settings → Developer settings → GitHub Apps → 該 App → General → Private keys）→ Generate a private key → 刪除（Delete）舊私鑰。
  3. 更新保管處：
     - merger、publisher：`security add-generic-password -U -a "$USER" -s meeting-harness.gh-app.<app> -w "$(cat <新的 .pem>)"`，然後刪除 `.pem`。
     - gate：repo → Settings → Secrets and variables → Actions → `AGENT_GATE_APP_PRIVATE_KEY` → Update，貼新的 `.pem` 全文，然後刪除 `.pem`。
  4. 若外洩的是 installation token（`hosts.yml`）：`$PY tools/merge_gate_project/gh_app_token.py revoke --app <app>`；token 本身 1 小時內也會失效。
  5. 查影響：rule insights（repo → Settings → Rules → Insights）與 `gh api "repos/$REPO/rulesets/rule-suites?ref=refs/heads/main"` 看外洩期間有沒有非預期的合併或 bypass；`gh pr list --repo $REPO --state all --limit 20 --json number,author,mergedBy,mergedAt` 看合併者。
  6. 恢復：確認無異常後 unsuspend（〈凍結與解凍〉2.3）。
- **讀回方式**：
  - App 設定頁的 Private keys 只剩新的一把（看指紋，不記私鑰內容）。
  - merger、publisher：`mint` 成功、`gh api /installation/repositories --jq '.total_count'` 印 `1`、`revoke`；`security find-generic-password -s meeting-harness.gh-app.<app> -w | head -c 26` 只看開頭格式。
  - gate：下一個 PR 的 `agent-merge-gate/decision` check run 正常出現。
  - 事件經過（時間、哪把鑰匙、處理步驟、影響查核結果）記在當次事件的 run 目錄；不記私鑰、token 的值。
- **是否不可逆**：是（舊私鑰刪除後無法復原；suspend 期間自動合併停止）。

---

## 4. 交人合併

適用：gate 判 hold 或 escalate（`agent-merge-gate/decision` 為紅）、`auto_merge.enabled` 為 false、高風險路徑（`.claude/`、`.github/`、hooks、`tools/merge_gate_project/`、守門設定、依賴等）、凍結期間。路徑照 design §5、`adr/adr-am-rulesets.md`〈決定〉的交人合併流程。

- **誰做**：PR 由主 session 以 publisher 身分開（使用者當下同意）；審查、核准、合併由使用者。主 session 與 agent 不核准、不合併。
- **指令或畫面路徑**：
  1. 開 PR：`$PY tools/merge_gate_project/gh_app_token.py mint --app publisher` → `GH_CONFIG_DIR=$PUBLISHER_DIR $PY .claude/teams/tools/publish.py push …` → `revoke --app publisher`。
  2. 使用者看 gate 的 reasons：`gh pr checks <n> --repo $REPO`，點 `agent-merge-gate/decision` 的詳情，或讀 Actions log。
  3. 改到 CODEOWNERS 路徑（守門設定、`.claude/teams/tools/`、`.claude/hooks/`、`.github/`、`tools/merge_gate_project/`）的 PR：使用者先以 code owner 核准（PR 頁 → Files changed → Review changes → Approve）。PR 作者是 publisher App，使用者可以核准；ruleset A 不能略過這一步。
  4. 合併：PR 頁 → Merge pull request 旁勾選 bypass rules → **Create a merge commit**（不用 squash、rebase）；或在 Claude Code 以外的終端機 `gh pr merge <n> --repo $REPO --merge --admin`。這只略過 ruleset C 的 required check，限經 PR 合併。
  5. 合併後不自動 pull；要更新主工作區時照第 8 步。
- **讀回方式**：`gh pr view <n> --repo $REPO --json state,mergedBy,mergeCommit` 的 `state` 為 `MERGED`、`mergedBy.login` 為 `s96cax98leo`；rule insights 有這次的 `bypass` 紀錄。main 的 CI（`ci.yml` 在 push main 觸發）為綠；紅就照〈凍結與解凍〉判斷是否凍結並開修正 PR。
- **是否不可逆**：是（合併進公開的 `main`）。

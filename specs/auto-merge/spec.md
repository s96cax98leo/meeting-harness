# spec：auto-merge（PR 經 merge_gate 判定後由 dev-merge-steward 自動合併）

- 上游：`intent.md`（閘門 1 已核准，2026-10-28）、`design.md`、`adr/`。
- 狀態：**草稿，待閘門 2 核准**。§6 第 2、4、5 條與 `adr/adr-am-rulesets.md` 要使用者在閘門 2 決定。
- Story 欄用 intent 的目標代號 G1–G8（本 repo 沒有 Story ID；不是任務編號）。commit scope 用 `auto-merge`。
- 條號 `4.x.y` 的格式就是本 epic 的 requirements adapter 要讀的格式（`adr/adr-am-requirements.md`）；本檔之後會被 `ops-trial` 的測試 PR 當成需求清單讀取。
- 指令前綴（plan §3 同）：`PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`；`REPO=s96cax98leo/meeting-harness`。
- 行號以 main @ `e72a9cb`、AgentWorkFlow @ `23174f0` 為準。範例場次名一律用「[Stand-up] 範例專案」。

---

## 1. 範圍

- 在範圍內：G1–G8（intent §2）。實作檔：`.claude/teams/`（升級與合回）、`.claude/workflows/`、`CLAUDE.md`、`bin/_lint.sh`、`tools/merge_gate_project/`（新）、`.github/`（新）、`tests/governance/`（新）、`specs/auto-merge/runbook.md`（新）。伺服器端設定與啟用由使用者執行（§4.7）。
- 不在範圍內：`bin/meeting.sh` 子指令與結束碼、`.claude/skills/meeting-*`、`.claude/workflows/meeting-pipeline.js`、五條鐵則、`vault/`；AgentWorkFlow 本身；`repos` 往 high 調；`delete_branch_on_merge`、`allow_auto_merge`（維持現值 false，`research-upstream.md:33-35`）。

## 2. 介面

### 2.1 `tools/merge_gate_project/reqs_from_spec.py`（requirements command adapter）

- 呼叫者：`merge_gate.py`（`cwd`＝專案根，`scaffold/.claude/teams/tools/merge_gate.py:176-191`）。沒有命令列參數。
- 環境變數：`AWF_REPO`、`AWF_PR`、`AWF_HEAD_SHA`（必填，`merge_gate.py:609`）；`AWF_REQ_BASE`（選填，預設 `origin/main`）。
- stdout（exit 0）：`{"requirements": [{"id": "4.1.1", "text": "<條號之後的整列原文>", "source": "specs/<epic>/spec.md:<行號>@<base 前 12 碼>"}], "epic": "<epic>", "base": "<base 40 碼>"}`。
- exit 2：任何讀不到或判不出的情況；原因寫 stderr（中文、≤300 字、不含 spec 全文）。adapter 不執行 `git fetch`、不寫任何檔。
- 解析規則：`adr/adr-am-requirements.md`〈決定〉第 1–8 點，本檔 §4.3 逐條驗收。

### 2.2 `tools/merge_gate_project/gh_app_token.py`

```
python3 tools/merge_gate_project/gh_app_token.py mint   --app merger|publisher [--config <gh-apps.json>] [--out-dir <目錄>]
python3 tools/merge_gate_project/gh_app_token.py revoke --app merger|publisher [--out-dir <目錄>]
```

- `--config` 預設 `~/.config/meeting-harness/gh-apps.json`（`{"merger": {"app_id": N}, "publisher": {"app_id": N}}`）；`--out-dir` 預設 `~/.config/meeting-harness/gh/<app>`。
- 私鑰：`security find-generic-password -s meeting-harness.gh-app.<app> -w`；測試用 `MH_GH_APP_SECURITY` 指定替身執行檔。簽章用 `openssl dgst -sha256 -sign /dev/stdin`（PEM 走 stdin）；測試用 `MH_GH_APP_OPENSSL` 可換。API 根 `https://api.github.com`，測試用 `MH_GH_API_BASE` 換。
- mint 的請求：`GET /app`（取 slug）、`GET /repos/s96cax98leo/meeting-harness/installation`、`POST /app/installations/<id>/access_tokens`，body `{"repositories": ["meeting-harness"], "permissions": <§4.4.3>}`。
- mint 的輸出：`<out-dir>/hosts.yml`（目錄 0700、檔 0600、先寫暫存檔再 rename），內容：

```
github.com:
    oauth_token: <token>
    user: <slug>[bot]
    git_protocol: https
```

  stdout 一行 JSON：`{"app": "merger", "config_dir": "<out-dir>", "expires_at": "<API 回的值>"}`。
- revoke：讀 `hosts.yml` 的 token 打 `DELETE /installation/token`，再刪 `hosts.yml`；檔不存在時 exit 0。
- exit：0 成功；2 任何錯誤（stderr 寫原因，不含 token、JWT、PEM）。

### 2.3 `tools/merge_gate_project/scan_names.py`

```
python3 tools/merge_gate_project/scan_names.py [--names-file <清單>] <檔案>...
```

- 清單：`--names-file` → `MH_CLIENT_NAMES_FILE` → `<repo 根>/_tpm/runs/client-names.txt`（以腳本位置推 repo 根）。每行一個名稱，空白行忽略，大小寫不分的固定字串比對（等同 `grep -qiF -f`）。
- 輸出與 exit：沒命中印「沒有」exit 0；命中印「有」exit 1；清單讀不到或沒有任何非空行印「名稱清單讀不到」exit 2。任何情況都不印名單內容、命中字或命中行。

### 2.4 steward 與主 session 的指令格式（寫進 rules.md〈專案規則〉與 methodology.json 的 merge 指引）

- steward 的四種寫入一律加前綴 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`，並明確帶 `--repo s96cax98leo/meeting-harness`：`gh pr comment <n> … --body-file <暫存檔>`、`gh pr merge <n> … --merge --match-head-commit <40 碼>`、`gh pr review <n> … --request-changes --body …`、`gh pr ready <n> … --undo`。讀取指令不加前綴。
- 主 session 開 PR：`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/publisher python3 .claude/teams/tools/publish.py push …`。
- CI job 名稱：`ci-ubuntu-subset`；gate check run 名稱：`agent-merge-gate/decision`（模版原樣）。

## 3. 設定值

`m-upgrade` 由主 session 寫入 `.claude/teams/guard.config.json`（agent 寫不了，`plugin/hooks/guard.py:500-502`、`:917-918`）：

```json
"protected_branches": ["main"],
"auto_merge": {
  "enabled": false,
  "repos": {"s96cax98leo/meeting-harness": "medium"},
  "merger_role": "agent-workflow:dev-merge-steward",
  "merge_method": "merge",
  "freeze_writers": ["agent-workflow:tpm-writer", "agent-workflow:dev-release-watcher"],
  "daily_cap": 3,
  "upstream_authorized_by": {},
  "freeze_file": "_tpm/runs/auto-merge.freeze.json",
  "small_lines": 100, "large_lines": 400, "large_files": 20,
  "carry_verdict_on_rebase": false
},
"requirements": {"source": "command", "command": ["python3", "tools/merge_gate_project/reqs_from_spec.py"], "path": "", "id_pattern": ""}
```

`main_session_github_rules`、`team_agent_namespaces`、`extension_agents` 用 `init.py` 渲染的值（`init.py` 的「主 session 會直接合併嗎」答「不會」）；`e72a9cb` 版已有的鍵與值全部保留（§4.1.9）。

## 4. 驗收條件

表格欄位：條號｜條文（EARS）｜Story｜依據｜驗法。`tests/governance/` 底下的測試由 `red-gov` 寫；§4.7 是 deliver 之後由使用者做的伺服器端步驟，test 段判 `not_verifiable` 屬預期，證據收在 `specs/auto-merge/evidence/g8-checklist.md`（`ops-enable` 產出）。

### 4.1 scaffold 升級與合回

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.1.1 | `.claude/teams/tools/` 應有 `merge_gate.py`、`publish.py`、`checklist.py`，且 `$PY .claude/teams/tools/merge_gate.py --selftest` 應回 0 並印出「全部通過」。 | G1 | intent §1.2；`merge_gate.py:38` | `test_upgrade.py::test_gate_selftest` |
| 4.1.2 | `.claude/workflows/` 應有 `sdlc-merge.js`、`event-post-merge.js`；`$PY .claude/teams/tools/build.py --check` 與 `node .claude/teams/tools/check_workflows.mjs` 都應回 0。 | G1 | intent §3；`build.py` docstring | `test_flow_merge.py::test_build_check`、`::test_check_workflows` |
| 4.1.3 | `.claude/workflows/meeting-pipeline.js` 應與 `e72a9cb` 逐位元相同。 | G1 | intent §2 G1 | `test_upgrade.py::test_meeting_pipeline_untouched` |
| 4.1.4 | `e72a9cb` 版 `.claude/teams/rules.md` 第 52–68 行的每一行，都應原文出現在新版「## 專案規則」段內。 | G1 | intent §2 G1、D5 | `test_rules_merge.py::test_project_rules_kept` |
| 4.1.5 | 新版 `rules.md` 的通用規則應符合 §6 第 1 條的處置表：規則 1 含「本專案目前沒有上游 repo」；規則 2 含「public」「當下同意」「publish.py」「publisher」；規則 3 含「push、開 PR」；規則 16 含「四個閘門都要使用者核准」與「不用 `--by policy`」；規則 24 含「合併通道裡不確定就 hold」；全檔不含 `guard-paths.sh`、`guard-bash.sh`、`check-envelope.sh`、`{{`。 | G1、G7 | `research-specs-adr.md:140-143`；§6 第 1 條 | `test_rules_merge.py::test_general_rules_merged` |
| 4.1.6 | `.claude/workflows/sdlc-build.js` 給 implementer 的派工字串應含「不要改 progress.md」，且全檔不含「更新 progress.md 對應項」。 | G1 | D-8；`.claude/workflows/sdlc-build.js:91`；`scaffold/.claude/workflows/sdlc-build.js:140` | `test_flow_merge.py::test_d8_kept` |
| 4.1.7 | `e72a9cb` 版 `.claude/teams/README.md` 中含 `meeting` 的每一行，都應原文出現在新版。 | G1 | `research-code-contracts.md:55` | `test_rules_merge.py::test_teams_readme_kept` |
| 4.1.8 | `CLAUDE.md` 應含 `@.claude/teams/agent-workflow.CLAUDE.md`；`e72a9cb` 版 `CLAUDE.md`「## 不可逆節點」段以外的每一行都應原文保留。 | G1 | `research-code-contracts.md:30` | `test_rules_merge.py::test_claude_md_kept` |
| 4.1.9 | `e72a9cb` 版 `guard.config.json` 的每個頂層鍵都應存在，且除 §3 列出的鍵以外，值都應相同。 | G1、G5 | D5 | `test_upgrade.py::test_guard_config_preserved` |
| 4.1.10 | `git log e72a9cb..feature/auto-merge` 應有一個只含 `init.py` 輸出的 commit 與一個只改 `guard.config.json` 的 commit，兩者內文都寫 AgentWorkFlow `23174f0` 與實際執行的 `init.py` 指令列。 | G1 | D5「以 git diff 交使用者審」 | verifier：`git log --format=%B`、`git show --stat` |

### 4.2 lint 與 CI 子集

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.2.1 | 當 `bin/` 的某支 `.sh` 有一行出現 `$名稱` 緊接非 ASCII 字元時，`bash bin/_lint.sh` 應回 1，並印出該檔名與行號。 | G2 | C4；`bin/_lint.sh:14-17` | `test_lint.py::test_detects_fullwidth_after_var` |
| 4.2.2 | 在本 repo 的 `bin/` 上，`bash bin/_lint.sh` 應回 0。 | G2 | C4；`bin/_lint.sh:15`、`:20` | `test_lint.py::test_repo_bin_clean` |
| 4.2.3 | `bin/_lint.sh` 應不含 `grep -P`、`grep -nP`。 | G2 | `adr/adr-am-ci-scope.md` L1 | `test_lint.py::test_no_grep_p` |
| 4.2.4 | 當 `.sh` 有雙引號字串內含反引號時，`bash bin/_lint.sh` 應回 1（既有第 2 項檢查行為不變）。 | G2 | `bin/_lint.sh:19-23` | `test_lint.py::test_backtick_check_kept` |
| 4.2.5 | `.github/workflows/ci.yml` 的觸發應只有 `pull_request` 與 `push`（`branches: [main]`）；應不含 `pull_request_target`、`secrets.`、`MH_CLIENT_NAMES_FILE`、`meeting.sh`、`doctor`、`swift`、`mlx`；`permissions` 應只有 `contents: read`；每個 `uses:` 應以 40 碼 SHA 釘版；job 的 `name` 應為 `ci-ubuntu-subset`；`runs-on` 應以 `ubuntu-` 開頭；checkout 應設 `fetch-depth: 0` 與 `persist-credentials: false`。 | G2 | D2；`adr/adr-am-ci-scope.md` T1 | `test_ci_static.py::test_ci_shape` |
| 4.2.6 | `ci.yml` 應依序執行 `bash bin/_lint.sh`、`python3 -m unittest discover -s tests/governance -t .`、以明確模組清單執行的 `python3 -m unittest tests.record.<模組> …`；清單應不含 `test_ms_docs`、`test_r3_docs`，也不含任何原始碼出現 `MH_CLIENT_NAMES_FILE` 的模組。 | G2 | D2、D-2；`tests/record/test_ms_docs.py:45-49`、`test_r3_docs.py:60-63` | `test_ci_static.py::test_subset_excludes_name_tests` |
| 4.2.7 | 在 `ubuntu:24.04` 容器（python3.12、git、bash、openssl、nodejs，不裝 ffmpeg，不設 `MH_CLIENT_NAMES_FILE`）內，以 `ci.yml` 的三條指令連續執行 3 次都應回 0，且 `tests.record` 子集的 `Ran N tests` 應 ≥ 1。 | G2 | C4「CI 清單只收實測會綠的」 | plan §3 第 5 條指令（`ci` 子任務與 verifier 各跑一次） |

### 4.3 requirements adapter

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.3.1 | 當 merge-base..head 之間有 commit 帶 `Spec-Epic: <e>` trailer、且 base 有 `specs/<e>/spec.md` 時，adapter 應 exit 0 並輸出 §2.1 的 JSON，`epic` 為 `<e>`、`base` 為 base 的 40 碼 SHA。 | G3 | `adr/adr-am-requirements.md` 第 2 點 | `test_reqs_from_spec.py::test_trailer_resolves` |
| 4.3.2 | 當沒有 trailer、但 diff 只碰到一個 `specs/<e>/` 而且 base 有該 spec 時，adapter 應解析出 `<e>`。 | G3 | 同上 | `test_reqs_from_spec.py::test_diff_path_resolves` |
| 4.3.3 | 當 epic 候選為 0 個時，adapter 應 exit 2 且 stderr 含「沒有指出 epic」；為 2 個以上時應 exit 2 且 stderr 含「多個 epic」。 | G3 | 同上 | `test_reqs_from_spec.py::test_zero_or_many_epics` |
| 4.3.4 | 當候選 epic 的 `spec.md` 不在 base 時，adapter 應 exit 2 且 stderr 含「不在 base」；當 PR head 改了 base 已有的 spec 時，輸出應是 base 版本的條文。 | G3 | Q5-A；C6 | `test_reqs_from_spec.py::test_reads_base_not_head` |
| 4.3.5 | 當 `AWF_HEAD_SHA` 不是本機已有的 commit，或 `AWF_REQ_BASE` 解析不出 commit，或必填環境變數缺漏時，adapter 應 exit 2；adapter 應不執行 `git fetch`。 | G3 | fail-closed（信任模型 :178） | `test_reqs_from_spec.py::test_missing_objects` |
| 4.3.6 | 當 spec 有 `## R<數字>` 開頭的標題時，adapter 應只取最後一個這種標題之後第一個含「驗收」的標題段；沒有時應取第一個含「驗收」的 2–4 級標題段；段落到下一個同級或更高級標題為止。 | G3 | C5；`specs/meeting-record/spec.md:950`、`:1382`、`:1982`、`:2190` | `test_reqs_from_spec.py::test_round_selection` |
| 4.3.7 | adapter 應排除第二欄以「（修正輪刪除」或「（選做）」開頭的列；條號重複或一條都沒有時應 exit 2。 | G3 | C5；`specs/meeting-speed/spec.md:247`、`:251`；`specs/meeting-record/spec.md:2343` | `test_reqs_from_spec.py::test_row_filters` |
| 4.3.8 | 當同一範圍的「整合修訂與例外」段有表格列出現 `§<條號>` 時，該條 `text` 應附上「〔整合修訂與例外第 <n> 條提到本條，見 specs/<e>/spec.md:<行號>〕」，且不抄該列內容。 | G3 | D-7；intent §3 `specs/*/spec.md` 列 | `test_reqs_from_spec.py::test_exception_pointer` |
| 4.3.9 | 以 `AWF_REQ_BASE=e72a9cb` 對 `meeting-speed` 執行時，輸出條數應等於該 spec「## 4. 驗收條件」段的條號列數減 2，且不含 `4.2.7`、`4.2.11`；對 `meeting-record` 執行時，所有 id 應以 `4.48.`–`4.58.` 開頭且不含 `4.58.6`。 | G3 | C5 | `test_reqs_from_spec.py::test_real_specs` |
| 4.3.10 | 每筆 `source` 應為 `specs/<e>/spec.md:<行號>@<base 前 12 碼>`，且該行號在 base 版 spec 裡就是該條號所在列。 | G3 | 規則 10（可回查） | `test_reqs_from_spec.py::test_source_points_to_row` |
| 4.3.11 | 當 `guard.config.json` 的 `requirements` 是 §3 的 command 設定時，`merge_gate.py check` 的輸出 `requirements_source` 應以 `command` 開頭、reasons 應不含「需求清單指令」；adapter exit 2 時 gate 應判 `hold`。 | G3 | `merge_gate.py:176-191`、`:235-244` | `test_gate_adapter_integration.py::test_gate_reads_adapter`、`::test_adapter_failure_holds` |

### 4.4 App token 與名稱掃描

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.4.1 | 當以替身 `security` 與替身 API 執行 `gh_app_token.py mint --app merger` 時，應寫出 §2.2 格式的 `hosts.yml`（目錄 0700、檔 0600，`user` 為 `<slug>[bot]`），stdout 應恰為一個 JSON 物件且鍵只有 `app`、`config_dir`、`expires_at`。 | G4 | D3；`adr/adr-am-app-identity.md` A | `test_app_token.py::test_mint_writes_hosts` |
| 4.4.2 | mint 與 revoke 執行後，stdout、stderr、以及 `TMPDIR` 與 `--out-dir` 以外的任何新檔，都應不含 token 字串、JWT 或 `PRIVATE KEY`；`TMPDIR` 內應沒有含 `PRIVATE KEY` 的檔。 | G4 | `CLAUDE.md`〈機敏檔〉 | `test_app_token.py::test_no_secret_leak` |
| 4.4.3 | access_tokens 請求的 `permissions`：merger 應恰為 `{"contents": "write", "pull_requests": "write"}`，publisher 應恰為 `{"contents": "read", "pull_requests": "write"}`；`repositories` 應恰為 `["meeting-harness"]`；JWT 的 `iss` 應等於 `gh-apps.json` 的 `app_id`、`exp - iat` 應 ≤ 600、`alg` 應為 `RS256`，且簽章可用對應公鑰驗證。 | G4 | 信任模型 :38-41；`adr/adr-am-app-identity.md`〈App 權限〉 | `test_app_token.py::test_request_shape` |
| 4.4.4 | 當 `--app` 是 `gate` 或未知值、`security` 失敗、或 API 回 4xx（含 403 installation suspended）時，`gh_app_token.py` 應 exit 2，且不留下 `hosts.yml`。 | G4 | D7 | `test_app_token.py::test_failures` |
| 4.4.5 | `revoke --app merger` 應以 `hosts.yml` 的 token 送出 `DELETE /installation/token` 並刪除 `hosts.yml`；`hosts.yml` 不存在時應 exit 0 且不送請求。 | G4 | 信任模型 :45 | `test_app_token.py::test_revoke` |
| 4.4.6 | `scan_names.py` 應依 §2.3 回 0／1／2，比對不分大小寫、忽略空白行，輸出只有「沒有」「有」「名稱清單讀不到」三種之一。 | G6 | C7 (a) | `test_scan_names.py::test_exit_codes`、`::test_output_never_leaks` |
| 4.4.7 | 沒給 `--names-file` 時，`scan_names.py` 應先讀 `MH_CLIENT_NAMES_FILE`，再讀 `<repo 根>/_tpm/runs/client-names.txt`。 | G6 | D-2 | `test_scan_names.py::test_default_path` |

### 4.5 設定與 merge 流程

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.5.1 | `guard.config.json` 的 `auto_merge` 應等於 §3 的值（`enabled` 為 false）。 | G5 | D1、D4；intent §2 G5 | `test_upgrade.py::test_auto_merge_values` |
| 4.5.2 | `guard.config.json` 的 `requirements` 應等於 §3 的 command 設定，`protected_branches` 應含 `main`。 | G5 | G3 | `test_upgrade.py::test_requirements_config` |
| 4.5.3 | `methodology.json` 的 `stages.merge.guidance` 應含 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`、`--merge`、`scan_names.py`、`agent-merge-gate/decision`、`--watch`、`tests/governance`。 | G6 | design §4；`adr/adr-am-ci-scope.md`〈後果〉 | `test_flow_merge.py::test_merge_guidance` |
| 4.5.4 | `methodology.json` 的 `conventions.commit.format` 應含 `Spec-Epic: <epic>`；`.claude/workflows/sdlc-merge.js` 內嵌的 `METHODOLOGY` 應含 §4.5.3 的 guidance 原文。 | G3、G6 | `adr/adr-am-requirements.md`；`scaffold/.claude/workflows/sdlc-merge.js:23`、`:53` | `test_flow_merge.py::test_trailer_convention`、`::test_guidance_embedded` |
| 4.5.5 | `.github/workflows/agent-merge-gate.yml` 應存在、含 `pull_request_target` 與 `agent-merge-gate/decision`，且不含 `{{`。 | G4 | D5（`--with-merge-gate`）；`adr/adr-am-rulesets.md` B（不改 gate） | `test_ci_static.py::test_gate_workflow_present` |
| 4.5.6 | `.github/CODEOWNERS` 應恰有 `/.claude/teams/guard.config.json`、`/.claude/teams/tools/`、`/.claude/hooks/`、`/.github/`、`/tools/merge_gate_project/` 五條，擁有者都是 `@s96cax98leo`，不得有 `*` 或 `/` 這類萬用路徑。 | G4 | 信任模型 :49-56、:198；C2 | `test_ci_static.py::test_codeowners` |

### 4.6 規則文字

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.6.1 | `rules.md` 規則 6 應寫明：核准一律不做；合併只在 `auto_merge.enabled` 為 true 時由 `agent-workflow:dev-merge-steward` 在 gate 判 merge 後執行；其餘由人合併；並指向〈專案規則〉的「自動合併（auto_merge）」條目。 | G7 | D-1；`scaffold/.claude/teams/rules.md:19` | `test_rules_merge.py::test_rule6` |
| 4.6.2 | 「## 專案規則」段應有以 `- **自動合併（auto_merge）**` 開頭的條目，含：核准人「使用者」與「2026-10-28」；`medium`；`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`；「只有主 session 執行 `gh_app_token.py`」；`~/.config/meeting-harness/gh/`（agent 不讀）；`scan_names.py`；`tests/governance`（測試數定義）；「bypass」（交人合併）；「suspend」（凍結）；「不自動 pull」；`merge-audit.jsonl`；「CI 綠不等於 verify 綠」。 | G7、G8 | intent §2 G7、§5.3；`rules.md:6` | `test_rules_merge.py::test_auto_merge_project_rule` |
| 4.6.3 | `CLAUDE.md`「## 不可逆節點」應不含「agent 不推送、不合併、不 approve」整句，應寫明 agent 不推送、不 approve、合併只由 steward 在 `auto_merge.enabled` 為 true 且 gate 判 merge 時執行；應不含「`main` 未受保護」。 | G7 | `CLAUDE.md:16` | `test_rules_merge.py::test_claude_md_irreversible` |
| 4.6.4 | `$PY .claude/teams/tools/check_rules.py` 應回 0；`rules.md`、`CLAUDE.md`、`.claude/teams/README.md` 應不含 `{{`。 | G1、G7 | 規則 12 | `test_rules_merge.py::test_check_rules` |
| 4.6.5 | `specs/auto-merge/runbook.md` 應有 §6 design 上線順序的 8 步，每步寫「誰做」「指令或畫面路徑」「讀回方式」「是否不可逆」；並含凍結與解凍、私鑰外洩、交人合併三段程序。 | G4、G8 | design §6；`adr/adr-am-app-identity.md` | `test_runbook.py::test_sections` |

### 4.7 伺服器端與啟用前檢查（deliver 之後，使用者執行）

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.7.1 | 對 merger 與 publisher 各執行 `gh_app_token.py mint` 後，`GH_CONFIG_DIR=<該目錄> gh api /installation/repositories --jq '.total_count'` 應印 `1`；執行 `revoke` 後同一指令應失敗。 | G4 | D3 | `ops-apps` |
| 4.7.2 | `gh variable list --repo $REPO` 應含 `AGENT_GATE_APP_ID`、`AGENT_MERGER_BOT`；`gh secret list --repo $REPO` 應含 `AGENT_GATE_APP_PRIVATE_KEY`（只看名稱）；`gh api repos/$REPO/actions/permissions/workflow` 的 `can_approve_pull_request_reviews` 應為 false。 | G4 | 信任模型 :30、:45 | `ops-apps` |
| 4.7.3 | 以暫存的專案目錄（`guard.config.json` 設 `enabled: true`、`merge_method: merge`；`merge-audit.jsonl` 有一筆對應的 `decision: merge`）執行 `awf_hook.py guard-shell` 時，steward 送 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr merge 1 --repo s96cax98leo/meeting-harness --merge --match-head-commit <40 碼>` 應放行；同一指令改 `--squash`、或 `agent_type` 不是 `agent-workflow:dev-merge-steward` 時應被擋。 | G6 | `plugin/hooks/guard.py:289`、`:304-323`、`:411-447` | `ops-apps` |
| 4.7.4 | `gh api repos/$REPO/rulesets` 與逐條讀回的 JSON 應符合 `adr/adr-am-rulesets.md`〈決定〉採用的方案（預設三條：A 的 `bypass_actors` 為空、`require_code_owner_review` true、`require_last_push_approval` false、`required_approving_review_count` 0；B 只有 `update`、bypass 為 merger App 與 admin；C 的兩個 context 各有 `integration_id`、`strict_required_status_checks_policy` true、bypass 只有 admin）。 | G4 | D6（待閘門 2 重新決定）；C3 | `ops-rulesets` |
| 4.7.5 | 測試 PR（publisher App 開、只改文件、≤ 100 行、commit 帶 `Spec-Epic: auto-merge`）上，`ci-ubuntu-subset` 應為 success，且應出現 `agent-merge-gate/decision` check run。 | G2、G8 | 信任模型 :196 | `ops-trial` |
| 4.7.6 | 該 check run 對應的 Actions log 中，gate 的 result JSON 的 `requirements_source` 應以 `command` 開頭，reasons 應不含「需求清單指令」「沒有需求來源」，且應含「auto_merge 未啟用」。 | G3、G8 | 信任模型 :199；§6 第 4 條 | `ops-trial` |
| 4.7.7 | 主 session 以 merger 身分（先過 `scan_names.py`）貼出 gate 輸入留言後，gate 重跑的 log 應不含「沒有 merger App 貼的 gate 輸入」；同一 head、同一份輸入在本機執行 `merge_gate.py check` 寫進 `merge-audit.jsonl` 的 `decision`，應與 CI 的 decision 相同。 | G6、G8 | intent §2 G8 測試 PR 段；C7 | `ops-trial` |
| 4.7.8 | 使用者在自己的終端機以 merger 身分對 gate 為 failure 的測試 PR 執行合併時應被伺服器拒絕；之後測試 PR 由使用者以 admin bypass 合併或關閉，結果記入 g8-checklist。 | G4、G8 | `adr/adr-am-rulesets.md`〈後果〉 | `ops-trial` |
| 4.7.9 | `specs/auto-merge/evidence/g8-checklist.md` 應逐項對應信任模型 :193-203 的 11 項，每項附證據（指令與結果，或 URL）；:202 寫 `medium` 與 ADR 偏離；:200 寫「合併後不自動 pull」與 pull 由誰做。 | G8 | intent §2 G8 | `ops-enable` |
| 4.7.10 | 啟用 PR 的 diff 應只有 `guard.config.json` 的 `auto_merge.enabled` 由 false 改 true 與新增 `g8-checklist.md`；PR 作者應為 publisher App，並有使用者的 code owner 核准。 | G5、G8 | 信任模型 :203 | `ops-enable` |

### 4.8 迴歸

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.8.1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` 應回 0。 | G1–G8 | `rules.md:59` | plan §3 第 1 條 |
| 4.8.2 | `$PY -m unittest discover -s tests/record -t .`（帶 `MH_CLIENT_NAMES_FILE`）應 0 個 `FAIL:`／`ERROR:`；`git diff --diff-filter=M --name-only e72a9cb HEAD -- tests/` 應為空。 | G1–G8 | intent §4.1 第 8 條 | plan §3 第 3 條 |
| 4.8.3 | `git diff --quiet e72a9cb HEAD -- bin/meeting.sh .claude/skills/` 應回 0。 | G1–G8 | intent §4.1 第 7 條 | verifier |
| 4.8.4 | `git diff e72a9cb HEAD` 與 `git log e72a9cb..HEAD --format=%B` 分別以 `grep -qiF -f <名稱清單>` 比對都應回 1（只報有／沒有）。 | G1–G8 | D-2；`CLAUDE.md`〈客戶資料邊界〉 | plan §3 第 4 條 |
| 4.8.5 | `$PY -m unittest discover -s tests/governance -t .` 應 0 個 `FAIL:`／`ERROR:`、0 個 `skipped`。 | G1–G8 | 規則 20 | plan §3 第 2 條 |

## 5. 影響系統

| 系統 | 變動 | 對外介面影響 |
|---|---|---|
| `bin/_lint.sh` | 全形字檢查改 python、修 `$f：` | verify 指令不變；macOS 上第一次真的在檢查 |
| `.claude/teams/`（tools、schemas、golden-set、methodologies、methodology.json、rules.md、README.md、guard.config.json） | 升級到 `23174f0`＋合回 | agent 的行為規則改變（規則 2、6、16、〈專案規則〉） |
| `.claude/workflows/sdlc-*.js`、`event-*.js` | 升級、重新內嵌 methodology、D-8 重套；新增 `sdlc-merge.js`、`event-post-merge.js` | 新增兩個 workflow |
| `.claude/settings.json` | init 深度合併 | 使用者既有 permissions 保留 |
| `CLAUDE.md` | 〈不可逆節點〉改寫；結尾多一行 `@` 引用 | — |
| `tools/merge_gate_project/`（新） | adapter、token 工具、名稱掃描 | CI 會執行 adapter（base 版本） |
| `.github/`（新） | `ci.yml`、`agent-merge-gate.yml`、`CODEOWNERS` | PR 會多兩個 check |
| `tests/governance/`（新） | 驗收測試 | 測試數定義改為 record＋governance |
| GitHub 設定 | 三個 App、vars／secret、三條 ruleset | 直接 push main 被擋；PR 合併要 check 綠或 admin bypass |
| `bin/meeting.sh`、`.claude/skills/meeting-*`、`meeting-pipeline.js`、`vault/` | 不變 | 不變 |

## 6. 整合修訂與例外

| 第 n 條 | 原條文或既有定案 | 本 epic 的修訂 | 理由／出處 | 核准 |
|---|---|---|---|---|
| 1 | `e72a9cb` 版 `rules.md` 通用規則（本地改寫版） | 合回處置：規則 1 用本地文字；規則 2 用本地事實（origin、public、每次當下同意）＋模版的 publish.py 與「不直接推 protected_branches」，**不採**模版的「無人值守經 run.json 核准即可推送」，開 PR 改用 publisher 身分但仍要當下同意；規則 3 用本地文字並補模版的 force push；規則 4、7、22 改用模版的 `awf_hook.py` 名稱；規則 5、8、10、12–14、17、21、23、25 照模版（與本地相同）；規則 6、24 用模版文字，規則 6 加指向〈專案規則〉的例外；規則 9、11、15、19、20 是同一模版的渲染結果；規則 16 用模版文字，但本專案四個閘門都要使用者核准、不用 `--by policy`；規則 18 用模版文字並補 `Spec-Epic` trailer；模版新增的「規則 ↔ 強制方式」節保留 | D5「逐條合回」；`research-code-contracts.md:27`、`:52` | 閘門 2 |
| 2 | D6：兩條 ruleset，A（無 bypass）含 required status check | 改為三條：required checks 移到 C，C 給 admin（只限經 PR）bypass；A 不開 Require approval of the most recent reviewable push | `adr/adr-am-rulesets.md`：D6 原案下 gate 判 hold／escalate 的 PR 誰都合不了（`agent-merge-gate.yml.tmpl:177`、`merge_gate.py:538`） | **待使用者在閘門 2 決定** |
| 3 | 信任模型 :28「admin 也不例外」、:23「最後一次 push 要核准」、:36「組織擁有的 App」、:79／:202「只開 low」 | 依第 2 條、D3、D1 偏離 | `adr/` 四份 | D1、D3：2026-10-28 使用者；其餘隨第 2 條 |
| 4 | intent §2 G8「測試 PR 預期判定是 escalate」 | 改為：判定可為 hold 或 escalate，驗收看 §4.7.6（需求讀到、reasons 含「auto_merge 未啟用」）與 §4.7.7（輸入留言被採用、與本機 audit 一致） | `merge_gate.py:538` hold 優先於 escalate；測試 PR 的驗證證據不是該 head 的 verifier 結果、本 spec 的 §4.7 條目在啟用前也拿不到證據，必有 hold 理由 | **待使用者在閘門 2 決定**（intent 已核准，本條是對 intent 驗收的修正） |
| 5 | 審查規則「修改既有檔超過 300 行或 15 檔列 important」（`rules.md:57`） | 本 epic 的 PR 預期超過（`init.py --force` 覆蓋十多支模版檔）；以 commit 分段審（§4.1.10），不拆 PR | 升級是機械覆蓋，拆 PR 會讓中間狀態新舊混用（`research-code-contracts.md:68`） | 待使用者在閘門 2 核准 |
| 6 | D-3：verify 指令 | 不變；新增「CI required check 是子集」與 gate 測試數定義（record＋governance） | D2 | D2：2026-10-28 使用者 |

## 7. 疑慮

1. **steward 是否照 merge 指引做**（`GH_CONFIG_DIR` 前綴、貼留言前名稱掃描、`--checks` 排除 gate、等 check 完成）：定義在 AgentWorkFlow（禁區），本 repo 只能透過 methodology.json 與 rules.md 要求；漏掉前綴時 gh 用使用者身分寫入（hook 仍放行合併，因為 hook 不看身分），伺服器端 ruleset B 的 bypass 也含 admin，**這種情況會以使用者身分合併成功**。建議 deliver 段之後的首次合併由使用者看 PR 時間軸確認合併者是 merger App；長期解法是回饋 AgentWorkFlow 讓 steward 原生支援 App 身分（衍生工作）。
2. **`hosts.yml` 格式與 `GH_CONFIG_DIR`**：gh 2.96 對多帳號的 `hosts.yml` 結構可能要求 `users:` 子鍵；未能確認，`ops-apps`（§4.7.1）實測，不行就改格式（只改 `gh_app_token.py` 與其測試）。
3. **`openssl dgst -sign /dev/stdin`**：macOS 上 `/opt/homebrew/bin/openssl` 與系統 LibreSSL 行為可能不同；`app-tools` 子任務用測試金鑰實測，不行就改成 `-sign` 讀 0600 暫存檔並在 finally 刪除（要回報並更新 §4.4.2）。
4. **CI 子集在 x86_64 與 aarch64 的差異**：本機 docker 是 linux/aarch64，GitHub 的 `ubuntu-latest` 是 x86_64；§4.2.7 在 aarch64 綠不保證 x86_64 綠，`ops-trial` 的 §4.7.5 是最終證據。
5. **gate 輸入留言的剩餘洩漏面**：名稱清單沒涵蓋到的名字、或證據裡的檔名與路徑仍可能透露資訊；`sdlc-merge` 的 Record 段會留下留言內容在本機 run 目錄，使用者抽查。
6. **測試數定義會因新增 `tests/governance` 而在本 epic 合併當下跳升**：之後的 PR 以合併後的數字為基準，不影響 gate 判定。
7. **bugfix PR（N1）多半 hold**：D1 開到 medium 的收益在 bugfix 上拿不到；是否改 N2 列為閘門 2 的非 blocking 問題。
8. **`init.py --force` 的實際輸出未實測**（派工單禁止 design 段執行）：`m-upgrade` 若發現覆蓋清單與 `research-code-contracts.md:50-64` 不同，主 session 先停下回報，再決定合回範圍。

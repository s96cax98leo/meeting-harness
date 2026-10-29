# spec：auto-merge（PR 經 merge_gate 判定後由 dev-merge-steward 自動合併）

- 上游：`intent.md`（閘門 1 已核准，2026-10-28）、`design.md`、`adr/`。
- 狀態：**閘門 1–3 已核准（2026-10-28／29），deliver 中**。§6 第 2、4、5 條、`adr/adr-am-rulesets.md`、bugfix 的 N1、App 角色已由使用者 2026-10-28 在閘門 2 前決定（E1–E6，見 `_tpm/runs/20261028-sdlc-auto-merge/design-revise-對照.md`）。
- 驗法欄寫法：`governance/<檔>::<函式>` 指 `tests/governance/<檔>` 的測試函式（長期有效、CI 跑）；`governance_once/<檔>::<函式>` 指 `tests/governance_once/<檔>`（只在升級當下成立、只在本 epic 驗收時跑，CI 不跑，見 §4.2.6、§4.8.6）；其他寫法是 plan §3 的指令或人工步驟。
- Story 欄用 intent 的目標代號 G1–G8（本 repo 沒有 Story ID；不是任務編號）。commit scope 用 `auto-merge`。
- 條號 `4.x.y` 的格式就是本 epic 的 requirements adapter 要讀的格式（`adr/adr-am-requirements.md`）；本檔之後會被 `ops-trial` 的測試 PR 當成需求清單讀取。
- 指令前綴（plan §3 同）：`PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`；`REPO=s96cax98leo/meeting-harness`。
- 行號以 main @ `e72a9cb`、AgentWorkFlow @ `23174f0` 為準。範例場次名一律用「[Stand-up] 範例專案」。

---

## 1. 範圍

- 在範圍內：G1–G8（intent §2）。實作檔：`.claude/teams/`（升級與合回，含新增的 `agent-workflow.CLAUDE.md`）、`.claude/workflows/`、`.claude/settings.json`（init 深度合併）、`.claude/settings.README.md`、`.mcp.json.example`、`.mcp.README.md`（init `--force` 覆蓋的模版說明檔）、`_tpm/runs/README.md`（init `--force` 覆蓋，`.gitignore` 例外追蹤）、`CLAUDE.md`、`bin/_lint.sh`、`tools/merge_gate_project/`（新）、`.github/`（新）、`tests/governance/`（新）、`tests/governance_once/`（新）、`specs/auto-merge/runbook.md`（新）、`specs/auto-merge/evidence/g8-checklist.md`（新，`ops-enable` 在啟用 PR 加入）。伺服器端設定與啟用由使用者執行（§4.7）。
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

表格欄位：條號｜條文（EARS）｜Story｜依據｜驗法。`tests/governance/` 與 `tests/governance_once/` 底下的測試都由 `red-gov` 寫。兩者的分界（E2，使用者 2026-10-28）：只在升級當下成立、以 `e72a9cb` 為基準或斷言 `enabled` 為 false 的斷言放 `governance_once`，其餘放 `governance`；`ops-enable` 把 `enabled` 改成 true 之後 `governance` 仍要全綠（§4.2.8）。§4.7 是 deliver 之後由使用者做的伺服器端步驟，test 段判 `not_verifiable` 屬預期，證據收在 run 目錄與 `specs/auto-merge/evidence/g8-checklist.md`（`ops-enable` 產出）。

### 4.1 scaffold 升級與合回

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.1.1 | `.claude/teams/tools/` 應有 `merge_gate.py`、`publish.py`、`checklist.py`，且 `$PY .claude/teams/tools/merge_gate.py --selftest` 應回 0 並印出「全部通過」。 | G1 | intent §1.2；`merge_gate.py:38` | `governance/test_upgrade.py::test_gate_selftest` |
| 4.1.2 | `.claude/workflows/` 應有 `sdlc-merge.js`、`event-post-merge.js`；`$PY .claude/teams/tools/build.py --check` 與 `node .claude/teams/tools/check_workflows.mjs` 都應回 0（check_workflows 要以 `--agents-dir` 或 `AWF_PLUGIN_DIR` 指向 plugin 的 agents/；沒有 plugin 時（例如 CI）以暫存空角色定義檔執行，只做乾跑，閘門 3 核准的解讀）。 | G1 | intent §3；`build.py` docstring | `governance/test_flow_merge.py::test_build_check`、`governance/test_flow_merge.py::test_check_workflows` |
| 4.1.3 | `.claude/workflows/meeting-pipeline.js` 應與 `e72a9cb` 逐位元相同。 | G1 | intent §2 G1 | `governance_once/test_upgrade_once.py::test_meeting_pipeline_untouched` |
| 4.1.4 | `e72a9cb` 版 `.claude/teams/rules.md` 第 52–68 行的每一行，都應原文出現在新版「## 專案規則」段內。 | G1 | intent §2 G1、D5 | `governance_once/test_upgrade_once.py::test_project_rules_kept` |
| 4.1.5 | 新版 `rules.md` 的通用規則應符合 §6 第 1 條的處置表：規則 1 含「本專案目前沒有上游 repo」；規則 2 含「public」「當下同意」「publish.py」「publisher」；規則 3 含「push、開 PR」；規則 16 含「四個閘門都要使用者核准」與「不用 `--by policy`」；規則 24 含「合併通道裡不確定就 hold」；全檔不含 `guard-paths.sh`、`guard-bash.sh`、`check-envelope.sh`、`{{`。 | G1、G7 | `research-specs-adr.md:140-143`；§6 第 1 條 | `governance/test_rules_merge.py::test_general_rules_merged` |
| 4.1.6 | `.claude/workflows/sdlc-build.js` 給 implementer 的派工字串應含「不要改 progress.md」，且全檔不含「更新 progress.md 對應項」。 | G1 | D-8；`.claude/workflows/sdlc-build.js:91`；`scaffold/.claude/workflows/sdlc-build.js:140` | `governance/test_flow_merge.py::test_d8_kept` |
| 4.1.7 | `e72a9cb` 版 `.claude/teams/README.md` 中含 `meeting` 的每一行，都應原文出現在新版。 | G1 | `research-code-contracts.md:55` | `governance_once/test_upgrade_once.py::test_teams_readme_kept` |
| 4.1.8 | `CLAUDE.md` 應含一行 `@.claude/teams/agent-workflow.CLAUDE.md`，且 `.claude/teams/agent-workflow.CLAUDE.md` 應存在（長期）；`e72a9cb` 版 `CLAUDE.md`「## 不可逆節點」段以外的每一行都應原文保留（升級當下）。 | G1 | `init.py:464-466`（結尾追加一個空行、一行 HTML 註解、一行 `@` 引用）；`research-code-contracts.md:30` | `governance/test_rules_merge.py::test_claude_md_import`、`governance_once/test_upgrade_once.py::test_claude_md_kept` |
| 4.1.9 | `e72a9cb` 版 `guard.config.json` 的每個頂層鍵都應存在，且除 §3 列出的鍵以外，值都應相同（以底線開頭的說明鍵如 `_說明` 只檢查存在、不比值，閘門 3 核准的解讀）。 | G1、G5 | D5 | `governance_once/test_upgrade_once.py::test_guard_config_preserved` |
| 4.1.10 | `git log e72a9cb..feature/auto-merge` 應有一個只含 `init.py` 輸出的 commit 與一個只改 `guard.config.json` 的 commit，兩者內文都寫 AgentWorkFlow `23174f0` 與實際執行的 `init.py` 指令列。 | G1 | D5「以 git diff 交使用者審」 | verifier：`git log --format=%B`、`git show --stat` |
| 4.1.11 | `e72a9cb` 版 `.claude/settings.json` 的 `$schema` 值應相同，`permissions.allow` 與 `permissions.deny` 的每個元素都應出現在新版同名清單內（順序不拘）。 | G1 | `init.py:342-354`（深度合併、使用者值優先）；§5 `.claude/settings.json` 列 | `governance_once/test_upgrade_once.py::test_settings_permissions_kept` |

### 4.2 lint 與 CI 子集

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.2.1 | 當 `bin/` 的某支 `.sh` 有一行出現 `$名稱` 緊接非 ASCII 字元時，`bash bin/_lint.sh` 應回 1，並印出該檔名與行號。 | G2 | C4；`bin/_lint.sh:14-17` | `governance/test_lint.py::test_detects_fullwidth_after_var` |
| 4.2.2 | 在本 repo 的 `bin/` 上，`bash bin/_lint.sh` 應回 0。 | G2 | C4；`bin/_lint.sh:15`、`:20` | `governance/test_lint.py::test_repo_bin_clean` |
| 4.2.3 | `bin/_lint.sh` 應不含 `grep -P`、`grep -nP`。 | G2 | `adr/adr-am-ci-scope.md` L1 | `governance/test_lint.py::test_no_grep_p` |
| 4.2.4 | 當 `.sh` 有雙引號字串內含反引號時，`bash bin/_lint.sh` 應回 1（既有第 2 項檢查行為不變）。 | G2 | `bin/_lint.sh:19-23` | `governance/test_lint.py::test_backtick_check_kept` |
| 4.2.5 | `.github/workflows/ci.yml` 的觸發應只有 `pull_request` 與 `push`（`branches: [main]`）；應不含 `pull_request_target`、`secrets.`、`MH_CLIENT_NAMES_FILE`、`meeting.sh`、`doctor`、`swift`、`mlx`；`permissions` 應只有 `contents: read`；每個 `uses:` 應以 40 碼 SHA 釘版；job 的 `name` 應為 `ci-ubuntu-subset`；`runs-on` 應以 `ubuntu-` 開頭；checkout 應設 `fetch-depth: 0` 與 `persist-credentials: false`。 | G2 | D2；`adr/adr-am-ci-scope.md` T1 | `governance/test_ci_static.py::test_ci_shape` |
| 4.2.6 | `ci.yml` 應依序執行 `bash bin/_lint.sh`、`python3 -m unittest discover -s tests/governance -t .`、以明確模組清單執行的 `python3 -m unittest tests.record.<模組> …`；全檔應不含 `governance_once`；模組清單應不含 `test_ms_docs`、`test_r3_docs`，也不含任何原始碼出現 `MH_CLIENT_NAMES_FILE` 的模組。gate 的測試數（`tests_before`／`tests_after`）＝`tests/record` 全量與 `tests/governance` 的 `Ran N tests` 相加，不含 `tests/governance_once`。 | G2 | D2、D-2、E2；`tests/record/test_ms_docs.py:45-49`、`test_r3_docs.py:60-63` | `governance/test_ci_static.py::test_subset_excludes_name_tests` |
| 4.2.7 | 在 `ubuntu:24.04` 容器（python3.12、git、bash、openssl、nodejs，不裝 ffmpeg，不設 `MH_CLIENT_NAMES_FILE`）內，以 `ci.yml` 的三條指令連續執行 3 次都應回 0，且 `tests.record` 子集的 `Ran N tests` 應 ≥ 1。 | G2 | C4「CI 清單只收實測會綠的」 | plan §3 第 5 條 |
| 4.2.8 | `tests/governance/` 讀守門設定一律經 `tests/governance/support.py` 的 `guard_config_path()`（環境變數 `MH_GUARD_CONFIG`，未設時為 `.claude/teams/guard.config.json`）：`grep -rl 'guard.config.json' tests/governance` 應只列出 `support.py`；需要這個字串的測試（§4.3.11 在暫存專案目錄寫守門設定、§4.5.6 比對 CODEOWNERS 的 `/.claude/teams/guard.config.json` 那一條、§4.6.6 比對含該檔名的規則句）一律從 `support.py` 的常數 `GUARD_CONFIG_NAME`（檔名）與 `GUARD_CONFIG_REL`（`.claude/teams/guard.config.json`）組出，不在測試檔寫字面值；`grep -rn e72a9cb tests/governance` 應恰好一行，且是 §4.3.9 用的 `REAL_SPECS_BASE` 常數定義。以 `$PY tests/governance/support.py flip-enabled <輸出檔>` 產生 `auto_merge.enabled` 為 true 的設定副本，再以 `MH_GUARD_CONFIG=<輸出檔>` 執行 `python3 -m unittest discover -s tests/governance -t .` 時，應 0 個 `FAIL:`／`ERROR:`。 | G2、G5 | E2（`ops-enable` 改 true 後 CI 仍綠）；`plugin/hooks/guard.py:508-520`（agent 的 shell 指令同一段出現該檔名與寫入動作會被擋，所以副本不用該檔名、指令列也不寫該檔名） | plan §3 第 7 條 |

### 4.3 requirements adapter

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.3.1 | 當 merge-base..head 之間有 commit 帶 `Spec-Epic: <e>` trailer、且 base 有 `specs/<e>/spec.md` 時，adapter 應 exit 0 並輸出 §2.1 的 JSON，`epic` 為 `<e>`、`base` 為 base 的 40 碼 SHA。 | G3 | `adr/adr-am-requirements.md` 第 2 點 | `governance/test_reqs_from_spec.py::test_trailer_resolves` |
| 4.3.2 | 當沒有 trailer、但 diff 只碰到一個 `specs/<e>/` 而且 base 有該 spec 時，adapter 應解析出 `<e>`。 | G3 | 同上 | `governance/test_reqs_from_spec.py::test_diff_path_resolves` |
| 4.3.3 | 當 epic 候選為 0 個時，adapter 應 exit 2 且 stderr 含「沒有指出 epic」；為 2 個以上時應 exit 2 且 stderr 含「多個 epic」。 | G3 | 同上 | `governance/test_reqs_from_spec.py::test_zero_or_many_epics` |
| 4.3.4 | 當候選 epic 的 `spec.md` 不在 base 時，adapter 應 exit 2 且 stderr 含「不在 base」；當 PR head 改了 base 已有的 spec 時，輸出應是 base 版本的條文。 | G3 | Q5-A；C6 | `governance/test_reqs_from_spec.py::test_reads_base_not_head` |
| 4.3.5 | 當 `AWF_HEAD_SHA` 不是本機已有的 commit，或 `AWF_REQ_BASE` 解析不出 commit，或必填環境變數缺漏時，adapter 應 exit 2；以 `PATH` 前置一支會記錄參數再轉呼叫真 `git` 的替身執行時，記錄裡應沒有任何一次的子指令是 `fetch`、`pull`、`clone`、`remote`。 | G3 | fail-closed（信任模型 :178）；§2.1「不執行 `git fetch`」 | `governance/test_reqs_from_spec.py::test_missing_objects`、`governance/test_reqs_from_spec.py::test_no_network_git` |
| 4.3.6 | 當 spec 有 `## R<數字>` 開頭的標題時，adapter 應只取最後一個這種標題之後第一個含「驗收」的標題段；沒有時應取第一個含「驗收」的 2–4 級標題段；段落到下一個同級或更高級標題為止。 | G3 | C5；`specs/meeting-record/spec.md:950`、`:1382`、`:1982`、`:2190` | `governance/test_reqs_from_spec.py::test_round_selection` |
| 4.3.7 | adapter 應排除第二欄以「（修正輪刪除」或「（選做）」開頭的列；條號重複或一條都沒有時應 exit 2。 | G3 | C5；`specs/meeting-speed/spec.md:247`、`:251`；`specs/meeting-record/spec.md:2343` | `governance/test_reqs_from_spec.py::test_row_filters` |
| 4.3.8 | 當同一範圍的「整合修訂與例外」段有表格列出現 `§<條號>` 時，該條 `text` 應附上「〔整合修訂與例外第 <n> 條提到本條，見 specs/<e>/spec.md:<行號>〕」，且不抄該列內容。 | G3 | D-7；intent §3 `specs/*/spec.md` 列 | `governance/test_reqs_from_spec.py::test_exception_pointer` |
| 4.3.9 | 以 `AWF_REQ_BASE=e72a9cb` 對 `meeting-speed` 執行時，輸出條數應等於該 spec「## 4. 驗收條件」段的條號列數減 2，且不含 `4.2.7`、`4.2.11`；對 `meeting-record` 執行時，所有 id 應以 `4.48.`–`4.58.` 開頭且不含 `4.58.6`。（`e72a9cb` 是 main 的永久祖先，本條長期有效。） | G3 | C5 | `governance/test_reqs_from_spec.py::test_real_specs` |
| 4.3.10 | 每筆 `source` 應為 `specs/<e>/spec.md:<行號>@<base 前 12 碼>`，且該行號在 base 版 spec 裡就是該條號所在列。 | G3 | 規則 10（可回查） | `governance/test_reqs_from_spec.py::test_source_points_to_row` |
| 4.3.11 | 當 `guard.config.json` 的 `requirements` 是 §3 的 command 設定時，`merge_gate.py check` 的輸出 `requirements_source` 應以 `command` 開頭、reasons 應不含「需求清單指令」；adapter exit 2 時 gate 應判 `hold`。 | G3 | `merge_gate.py:176-191`、`:235-244` | `governance/test_gate_adapter_integration.py::test_gate_reads_adapter`、`governance/test_gate_adapter_integration.py::test_adapter_failure_holds` |
| 4.3.12 | adapter 在暫存 repo 內以 exit 0 與 exit 2 各執行一次後，該 repo 的 `git status --porcelain --ignored` 應與執行前相同，`TMPDIR` 與 cwd 應沒有新增檔案或目錄。 | G3 | §2.1「不寫任何檔」 | `governance/test_reqs_from_spec.py::test_writes_nothing` |
| 4.3.13 | 當 merge-base..head 的 commit 另帶 `Spec-Reqs: <條號,…>` 或其他非 `Spec-Epic` 的 trailer 時，adapter 的輸出應與不帶這些 trailer 時逐位元相同（需求＝該 epic 最後一輪全部條目，不允許縮小）。 | G3 | E3（N1，使用者 2026-10-28）；`adr/adr-am-requirements.md` | `governance/test_reqs_from_spec.py::test_no_narrowing_trailer` |

### 4.4 App token 與名稱掃描

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.4.1 | 當以替身 `security` 與替身 API 執行 `gh_app_token.py mint --app merger` 時，應寫出 §2.2 格式的 `hosts.yml`（目錄 0700、檔 0600，`user` 為 `<slug>[bot]`），stdout 應恰為一個 JSON 物件且鍵只有 `app`、`config_dir`、`expires_at`。 | G4 | D3；`adr/adr-am-app-identity.md` A | `governance/test_app_token.py::test_mint_writes_hosts` |
| 4.4.2 | mint 與 revoke 執行後，stdout、stderr、以及 `TMPDIR` 與 `--out-dir` 以外的任何新檔，都應不含 token 字串、JWT 或 `PRIVATE KEY`；`TMPDIR` 內應沒有含 `PRIVATE KEY` 的檔。 | G4 | `CLAUDE.md`〈機敏檔〉 | `governance/test_app_token.py::test_no_secret_leak` |
| 4.4.3 | access_tokens 請求的 `permissions`：merger 應恰為 `{"contents": "write", "pull_requests": "write"}`，publisher 應恰為 `{"contents": "read", "pull_requests": "write"}`；`repositories` 應恰為 `["meeting-harness"]`；JWT 的 `iss` 應等於 `gh-apps.json` 的 `app_id`、`exp - iat` 應 ≤ 600、`alg` 應為 `RS256`，且簽章可用對應公鑰驗證。 | G4 | 信任模型 :38-41；`adr/adr-am-app-identity.md`〈App 權限〉 | `governance/test_app_token.py::test_request_shape` |
| 4.4.4 | 當 `--app` 是 `gate` 或未知值、`security` 失敗、或 API 回 4xx（含 403 installation suspended）時，`gh_app_token.py` 應 exit 2，且不留下 `hosts.yml`。 | G4 | D7 | `governance/test_app_token.py::test_failures` |
| 4.4.5 | `revoke --app merger` 應以 `hosts.yml` 的 token 送出 `DELETE /installation/token` 並刪除 `hosts.yml`；`hosts.yml` 不存在時應 exit 0 且不送請求。 | G4 | 信任模型 :45 | `governance/test_app_token.py::test_revoke` |
| 4.4.6 | `scan_names.py` 應依 §2.3 回 0／1／2，比對不分大小寫、忽略空白行，輸出只有「沒有」「有」「名稱清單讀不到」三種之一。 | G6 | C7 (a) | `governance/test_scan_names.py::test_exit_codes`、`governance/test_scan_names.py::test_output_never_leaks` |
| 4.4.7 | 沒給 `--names-file` 時，`scan_names.py` 應先讀 `MH_CLIENT_NAMES_FILE`，再讀 `<repo 根>/_tpm/runs/client-names.txt`。 | G6 | D-2 | `governance/test_scan_names.py::test_default_path` |

### 4.5 設定與 merge 流程

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.5.1 | 升級當下，`guard.config.json` 的 `auto_merge` 應等於 §3 的值（`enabled` 為 false）。 | G5 | D1、D4；intent §2 G5 | `governance_once/test_upgrade_once.py::test_auto_merge_values` |
| 4.5.2 | `guard.config.json` 的 `requirements` 應等於 §3 的 command 設定，`protected_branches` 應含 `main`。 | G5 | G3 | `governance/test_upgrade.py::test_requirements_config` |
| 4.5.3 | `methodology.json` 的 `stages.merge.guidance` 應含 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`、`--merge`、`scan_names.py`、`agent-merge-gate/decision`、`--watch`、`tests/governance`。 | G6 | design §4；`adr/adr-am-ci-scope.md`〈後果〉 | `governance/test_flow_merge.py::test_merge_guidance` |
| 4.5.4 | `methodology.json` 的 `conventions.commit.format` 應含 `Spec-Epic: <epic>`；`.claude/workflows/sdlc-merge.js` 內嵌的 `METHODOLOGY` 應含 §4.5.3 的 guidance 原文。 | G3、G6 | `adr/adr-am-requirements.md`；`scaffold/.claude/workflows/sdlc-merge.js:23`、`:53` | `governance/test_flow_merge.py::test_trailer_convention`、`governance/test_flow_merge.py::test_guidance_embedded` |
| 4.5.5 | `.github/workflows/agent-merge-gate.yml` 應存在、含 `pull_request_target` 與 `agent-merge-gate/decision`，且不含未替換的 init 佔位，即前面不是 `$` 的 `{{`（`${{ … }}` 是 Actions 運算式，不算；閘門 3 核准的解讀）。 | G4 | D5（`--with-merge-gate`）；`adr/adr-am-rulesets.md`（不改 gate） | `governance/test_ci_static.py::test_gate_workflow_present` |
| 4.5.6 | `.github/CODEOWNERS` 應恰有 `/.claude/teams/guard.config.json`、`/.claude/teams/tools/`、`/.claude/hooks/`、`/.github/`、`/tools/merge_gate_project/` 五條，擁有者都是 `@s96cax98leo`，不得有 `*` 或 `/` 這類萬用路徑。 | G4 | 信任模型 :49-56、:198；C2 | `governance/test_ci_static.py::test_codeowners` |
| 4.5.7 | `guard.config.json` 的 `auto_merge` 應含 §3 列出的全部鍵；`enabled` 應為布林（不檢查值）；`merge_method` 應為 `merge`；`merger_role` 應為 `agent-workflow:dev-merge-steward`；`repos` 應恰為 `{"s96cax98leo/meeting-harness": "medium"}`。 | G5 | D1、D4；E2（長期有效的部分） | `governance/test_upgrade.py::test_auto_merge_shape` |

### 4.6 規則文字

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.6.1 | `rules.md` 規則 6 應寫明：核准一律不做；合併只在 `auto_merge.enabled` 為 true 時由 `agent-workflow:dev-merge-steward` 在 gate 判 merge 後執行；其餘由人合併；並指向〈專案規則〉的「自動合併（auto_merge）」條目。 | G7 | D-1；`scaffold/.claude/teams/rules.md:19` | `governance/test_rules_merge.py::test_rule6` |
| 4.6.2 | 「## 專案規則」段應有以 `- **自動合併（auto_merge）**` 開頭的條目，含：核准人「使用者」與「2026-10-28」；`medium`；`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger`；「只有主 session 執行 `gh_app_token.py`」；`~/.config/meeting-harness/gh/`（agent 不讀）；`scan_names.py`；`tests/governance`（測試數定義）；「bypass」（交人合併）；「suspend」（凍結）；「不自動 pull」；`merge-audit.jsonl`；「CI 綠不等於 verify 綠」；「沒有自己 spec 的 bugfix PR 以 `Spec-Epic` 指向它修的 epic，需求為該 epic 全部條目」。 | G7、G8 | intent §2 G7、§5.3；`rules.md:6`；E3 | `governance/test_rules_merge.py::test_auto_merge_project_rule` |
| 4.6.3 | `CLAUDE.md`「## 不可逆節點」應不含「agent 不推送、不合併、不 approve」整句，應寫明 agent 不推送、不 approve、合併只由 steward 在 `auto_merge.enabled` 為 true 且 gate 判 merge 時執行；應不含「`main` 未受保護」。 | G7 | `CLAUDE.md:16` | `governance/test_rules_merge.py::test_claude_md_irreversible` |
| 4.6.4 | `$PY .claude/teams/tools/check_rules.py` 應回 0；`rules.md`、`CLAUDE.md`、`.claude/teams/README.md` 應不含 `{{`。 | G1、G7 | 規則 12 | `governance/test_rules_merge.py::test_check_rules` |
| 4.6.5 | `specs/auto-merge/runbook.md` 應有 design §6 上線順序的 8 步，每步寫「誰做」「指令或畫面路徑」「讀回方式」「是否不可逆」；並含凍結與解凍、私鑰外洩、交人合併三段程序；全檔應不含「待閘門 2」「重新決定」「推論」（未決標記；不用「待使用者」這類會誤中「等待使用者」的字串）。 | G4、G8 | design §6；`adr/adr-am-app-identity.md`；E1、E5 | `governance/test_runbook.py::test_sections` |
| 4.6.6 | 〈專案規則〉的「自動合併（auto_merge）」條目應逐字含這一句：「`auto_merge.enabled` 為 true 後，主 session 也不直接改 `guard.config.json`、`merge-audit.jsonl`、`publish-audit.jsonl`；要改 `guard.config.json` 一律走 PR 與 code owner 核准。」 | G7 | intent §2 G7；信任模型 :58 | `governance/test_rules_merge.py::test_main_session_no_direct_edit` |

### 4.7 伺服器端與啟用前檢查（deliver 之後，使用者執行）

ruleset 名稱（E1，`adr/adr-am-rulesets.md`〈決定〉）：A＝`main-baseline`、B＝`main-restrict-updates`、C＝`main-required-checks`。下文「rule suite」指 `gh api "repos/$REPO/rulesets/rule-suites?ref=refs/heads/main"` 列出、再以 `gh api repos/$REPO/rulesets/rule-suites/<id>` 讀回的評估紀錄；欄位以讀回值為準（§7 第 9 點）。

**執行順序不照條號**。本節條號是撰寫順序；實際執行一律照下表（＝design §6 上線順序第 1–8 步），runbook 的 G8 段、progress、plan §1 的分層都以這張表為準：

| 執行序 | design §6 步 | 條號 | 子任務 | 為什麼排在這裡 |
|---|---|---|---|---|
| — | 1 | （合併本 epic 的 PR，沒有條號） | — | — |
| — | 2 | （建三個 App、匯入私鑰、`gh-apps.json`、Actions vars／secret、Actions 不准建立或核准 PR，沒有條號） | `ops-apps` | §4.7.2 要讀回這些設定 |
| 1 | 3 | §4.7.1 | `ops-apps` | — |
| 2 | 3 | §4.7.2 | `ops-apps` | 讀回第 2 步的設定 |
| 3 | 3 | §4.7.3 | `ops-apps` | — |
| — | 4 | （確認沒有開著的 PR、建 ruleset A／B／C，沒有條號） | `ops-rulesets` | — |
| 4 | 5 | §4.7.4 | `ops-rulesets` | 讀回 ruleset；通過才做下一步 |
| 5 | 5 | §4.7.11 | `ops-rulesets` | 探測推送是不可逆節點，要在 §4.7.4 通過之後（§7 第 10 點） |
| 6 | 6 | §4.7.5 | `ops-trial` | — |
| 7 | 6 | §4.7.6 | `ops-trial` | — |
| 8 | 6 | §4.7.7 | `ops-trial` | — |
| 9 | 6 | §4.7.8 | `ops-trial` | 要在 §4.7.11 之後（確認 ruleset 生效才打 merge 端點，§7 第 12 點）、§4.7.12 之前（PR 還開著） |
| 10 | 6 | §4.7.12 | `ops-trial` | 測試 PR 的最後一步（不得關閉） |
| 11 | 7 | §4.7.9 | `ops-enable` | g8-checklist 要引用 §4.7.4、§4.7.8、§4.7.11、§4.7.12 的結果，所以排在它們全部之後 |
| 12 | 7 | §4.7.10 | `ops-enable` | 啟用 PR 開出後讀回 diff 與作者 |
| 13 | 7 | §4.7.13 | `ops-enable` | 核准前合併被拒 → 核准 → 合併 |
| — | 8 | （本機主工作區 pull，沒有條號） | — | — |

依序寫成一行（runbook 完成條件用）：§4.7.1 → §4.7.2 → §4.7.3 → §4.7.4 → §4.7.11 → §4.7.5 → §4.7.6 → §4.7.7 → §4.7.8 → §4.7.12 → §4.7.9 → §4.7.10 → §4.7.13。

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.7.1 | 對 merger 與 publisher 各執行 `gh_app_token.py mint` 後，`GH_CONFIG_DIR=<該目錄> gh api /installation/repositories --jq '.total_count'` 應印 `1`；執行 `revoke` 後同一指令應失敗。 | G4 | D3 | `ops-apps` |
| 4.7.2 | `gh variable list --repo $REPO` 應含 `AGENT_GATE_APP_ID`、`AGENT_MERGER_BOT`；`gh secret list --repo $REPO` 應含 `AGENT_GATE_APP_PRIVATE_KEY`（只看名稱）；`gh api repos/$REPO/actions/permissions/workflow` 的 `can_approve_pull_request_reviews` 應為 false（這三項都由 `ops-apps` 在 design §6 第 2 步設定，同一子任務讀回）。 | G4 | 信任模型 :30、:45 | `ops-apps` |
| 4.7.3 | 以暫存的專案目錄（`guard.config.json` 設 `enabled: true`、`merge_method: merge`；`merge-audit.jsonl` 有一筆對應的 `decision: merge`）執行 `awf_hook.py guard-shell` 時，steward 送 `GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr merge 1 --repo s96cax98leo/meeting-harness --merge --match-head-commit <40 碼>` 應放行；同一指令改 `--squash`、或 `agent_type` 不是 `agent-workflow:dev-merge-steward` 時應被擋。 | G6 | `plugin/hooks/guard.py:289`、`:304-323`、`:411-447` | `ops-apps` |
| 4.7.4 | `gh api repos/$REPO/rulesets` 應恰有 A、B、C 三條（`enforcement` 都是 `active`、`target` 都是 `branch`、`conditions.ref_name.include` 都是 `["~DEFAULT_BRANCH"]`），逐條讀回：A 的 `bypass_actors` 為空，`rules[].type` 恰為 `pull_request`、`non_fast_forward`、`deletion`，`pull_request.parameters` 的 `require_code_owner_review` true、`require_last_push_approval` false、`dismiss_stale_reviews_on_push` true、`required_approving_review_count` 0；B 的 `rules[].type` 恰為 `update`，`bypass_actors` 恰為 merger App（`actor_type` `Integration`）與 admin 角色（`actor_type` `RepositoryRole`）兩筆、`bypass_mode` 都是 `pull_request`；C 的 `rules[].type` 恰為 `required_status_checks`，兩個 context 為 `agent-merge-gate/decision`（`integration_id`＝gate App ID）與 `ci-ubuntu-subset`（`integration_id`＝GitHub Actions），`strict_required_status_checks_policy` true，`bypass_actors` 恰為 admin 角色一筆、`bypass_mode` `pull_request`。 | G4 | E1（使用者 2026-10-28）；C3 | `ops-rulesets` |
| 4.7.5 | 測試 PR（publisher App 開、只改 `specs/auto-merge/evidence/` 下的文件、≤ 100 行、commit 帶 `Spec-Epic: auto-merge`）上，`ci-ubuntu-subset` 應為 success，且應出現 `agent-merge-gate/decision` check run。 | G2、G8 | 信任模型 :196 | `ops-trial` |
| 4.7.6 | 該 check run 對應的 Actions log 中，gate 的 result JSON 的 `requirements_source` 應以 `command` 開頭，reasons 應不含「需求清單指令」「沒有需求來源」，且應含「auto_merge 未啟用」；`decision` 為 `hold` 或 `escalate` 都符合本條。 | G3、G8 | 信任模型 :199；E4；§6 第 4 條 | `ops-trial` |
| 4.7.7 | 主 session 以 merger 身分（先過 `scan_names.py`）貼出 gate 輸入留言後，gate 重跑的 log 應不含「沒有 merger App 貼的 gate 輸入」；同一 head、同一份輸入在本機執行 `merge_gate.py check` 寫進 `merge-audit.jsonl` 的 `decision`，應與 CI 的 decision 相同。 | G6、G8 | intent §2 G8 測試 PR 段；C7；E4 | `ops-trial` |
| 4.7.8 | 在 §4.7.11 通過之後，對 gate 為 failure 的測試 PR 依序做三件事，三件都符合才算通過。(1) 試合前讀回：`gh pr view <n> --repo $REPO --json state,mergeStateStatus,headRefOid,statusCheckRollup,files` 的 `state` 為 `OPEN`、`mergeStateStatus` 為 `BLOCKED`；`statusCheckRollup` 裡 `agent-merge-gate/decision` 的 `conclusion` 為 `FAILURE`、`ci-ubuntu-subset` 為 `SUCCESS`；`files` 都在 `specs/auto-merge/evidence/` 下（不碰 CODEOWNERS 路徑，A 不要求 code owner 核准）。(2) 以 merger App 的 installation token 直接呼叫 REST 合併端點：`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh api -i -X PUT repos/$REPO/pulls/<n>/merge -f sha=<(1) 的 headRefOid> -f merge_method=merge`，應回 HTTP 4xx 拒絕（預期 405；409、422 也算拒絕），回應的 `message`（或同義欄位）應指出 required status check 沒有滿足：含 `agent-merge-gate/decision`，或只寫 required status check 一類字樣而 (1) 的 rollup 顯示未成功的 required check 只有 `agent-merge-gate/decision`；回應不得提到 review、code owner、pull request 規則（A 的規則）。(3) 試合後讀回：同 (1) 的 `state` 仍為 `OPEN`，`git ls-remote origin refs/heads/main` 與試合前相同。判定理由：merger App 在 B 的 bypass 內，A 的 `required_approving_review_count` 為 0 且這個 PR 不需要 code owner 核准，所以能擋下這次呼叫的只剩 C，證明 C 綁得住 merger App。rule suite 若有這次呼叫的紀錄，C 的 `required_status_checks` 評估應為 `fail`、A 沒有 `fail`（佐證，不是必要條件）。不用 `gh pr merge` 試合：gh 2.96 在 PR 為 `BLOCKED` 時先在 client 端擋下（只印「the base branch policy prohibits the merge」，不送合併請求、不列 check 名稱），證明不了伺服器端。執行者：(2) 打的是 merge 端點，hook 對主 session 與所有 agent 一律擋（`plugin/hooks/guard.py:248-254` 的 `is_merge_cmd`、`:871` 本專案 `main_session_github_rules` 為 true、`:904-907`），所以由使用者當下決定後在 Claude Code 以外的終端機自己執行；主 session 只在使用者同意後做 (1)、(3) 的讀回。欄位名以實測讀回為準（§7 第 9 點）。 | G4、G8 | E1；`adr/adr-am-rulesets.md`〈後果〉 | `ops-trial` |
| 4.7.9 | `specs/auto-merge/evidence/g8-checklist.md` 應逐項對應信任模型 :193-203 的 11 項，每項附證據（指令與結果，或 URL）；ruleset 那一項應引用 §4.7.4、§4.7.8、§4.7.11、§4.7.12 的結果；:202 寫 `medium` 與 ADR 偏離；:200 寫「合併後不自動 pull」與 pull 由誰做。 | G8 | intent §2 G8 | `ops-enable` |
| 4.7.10 | 啟用 PR 的 diff 應只有 `guard.config.json` 的 `auto_merge.enabled` 由 false 改 true 與新增 `g8-checklist.md`；PR 作者應為 publisher App，並有使用者的 code owner 核准。 | G5、G8 | 信任模型 :203 | `ops-enable` |
| 4.7.11 | 在 §4.7.4 通過之後，使用者在自己的終端機從 `origin/main` 建一個空 commit 執行 `git push origin HEAD:refs/heads/main` 時應被拒絕，`git ls-remote origin refs/heads/main` 應與推送前相同；這次推送的 rule suite `result` 應為 `fail`（不是 `bypass`），且應同時有 A 的 `pull_request` 評估 `fail` 與 B 的 `update` 評估 `fail`（證明 B 對 admin 只在經 PR 時放行、A 沒有 bypass）。 | G4 | E1 | `ops-rulesets` |
| 4.7.12 | 測試 PR 在 §4.7.8 之後應由使用者以 admin bypass 合併（不得改成關閉）：`gh pr view <n> --json state,mergedBy,mergeCommit` 的 `state` 為 `MERGED`、`mergedBy.login` 為 `s96cax98leo`，合併 commit 有 2 個 parent；這次合併的 rule suite `result` 應為 `bypass`，且含 C 的 `required_status_checks` 評估；B 的 `update` 評估結果（`pass`／`fail`／沒有評估）原樣記入 g8-checklist，作為「經 PR 合併算不算 update」的實測答案。 | G4、G8 | E1；`research-code-contracts.md:121`（未能確認，要實測） | `ops-trial` |
| 4.7.13 | 啟用 PR 在使用者核准之前，使用者執行 `gh pr merge <n> --repo $REPO --merge --admin` 應失敗且 PR 仍為 `OPEN`（A 沒有 bypass，Code Owners 核准不能略過）；核准之後以 admin bypass 合併應成功，該次 rule suite 的 `result` 為 `bypass`，且 A 的評估都是 `pass`。結果存進 run 目錄（合併後才有的證據不進 g8-checklist）。 | G4、G5、G8 | E1；信任模型 :58、:203 | `ops-enable` |

### 4.8 迴歸

| # | 條文 | Story | 依據 | 驗法 |
|---|---|---|---|---|
| 4.8.1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` 應回 0。 | G1–G8 | `rules.md:59` | plan §3 第 1 條 |
| 4.8.2 | `$PY -m unittest discover -s tests/record -t .`（帶 `MH_CLIENT_NAMES_FILE`）應 0 個 `FAIL:`／`ERROR:`；`git diff --diff-filter=M --name-only e72a9cb HEAD -- tests/` 應為空。 | G1–G8 | intent §4.1 第 8 條 | plan §3 第 3 條 |
| 4.8.3 | `git diff --quiet e72a9cb HEAD -- bin/meeting.sh .claude/skills/` 應回 0。 | G1–G8 | intent §4.1 第 7 條 | verifier |
| 4.8.4 | `git diff e72a9cb HEAD` 與 `git log e72a9cb..HEAD --format=%B` 分別以 `grep -qiF -f <名稱清單>` 比對都應回 1（只報有／沒有）。 | G1–G8 | D-2；`CLAUDE.md`〈客戶資料邊界〉 | plan §3 第 4 條 |
| 4.8.5 | `$PY -m unittest discover -s tests/governance -t .` 應 0 個 `FAIL:`／`ERROR:`、0 個 `skipped`，`Ran N tests` 的 N ≥ 1。 | G1–G8 | 規則 20 | plan §3 第 2 條 |
| 4.8.6 | 本 epic 驗收時（`ops-enable` 之前），`$PY -m unittest discover -s tests/governance_once -t .` 應 0 個 `FAIL:`／`ERROR:`、0 個 `skipped`，`Ran N tests` 的 N ≥ 1。 | G1、G5 | E2 | plan §3 第 6 條 |

## 5. 影響系統

| 系統 | 變動 | 對外介面影響 |
|---|---|---|
| `bin/_lint.sh` | 全形字檢查改 python、修 `$f：` | verify 指令不變；macOS 上第一次真的在檢查 |
| `.claude/teams/`（tools、schemas、golden-set、methodologies、methodology.json、rules.md、README.md、guard.config.json） | 升級到 `23174f0`＋合回 | agent 的行為規則改變（規則 2、6、16、〈專案規則〉） |
| `.claude/teams/agent-workflow.CLAUDE.md`（新） | init 寫出的模版說明，由 `CLAUDE.md` 的 `@` 引用載入 | 每個 session 多載入一份模版說明 |
| `.claude/workflows/sdlc-*.js`、`event-*.js` | 升級、重新內嵌 methodology、D-8 重套；新增 `sdlc-merge.js`、`event-post-merge.js` | 新增兩個 workflow |
| `.claude/settings.json` | init 深度合併（`init.py:342-354`，使用者值優先、只補缺的鍵） | `e72a9cb` 版的 `$schema` 與 `permissions.allow`／`deny` 全部保留（§4.1.11） |
| `.claude/settings.README.md`、`.mcp.json.example`、`.mcp.README.md` | init `--force` 覆蓋成模版版本（與 `e72a9cb` 版各差 2–10 行） | 只是說明與範例檔 |
| `_tpm/runs/README.md` | init `--force` 覆蓋成模版版本（`.gitignore:42` 例外追蹤，會進 diff） | run 目錄說明文字改變 |
| `CLAUDE.md` | 〈不可逆節點〉改寫；結尾追加一個空行、一行 HTML 註解、一行 `@.claude/teams/agent-workflow.CLAUDE.md`（`init.py:464-466`，兩行非空） | — |
| `tools/merge_gate_project/`（新） | adapter、token 工具、名稱掃描 | CI 會執行 adapter（base 版本） |
| `.github/`（新） | `ci.yml`、`agent-merge-gate.yml`、`CODEOWNERS` | PR 會多兩個 check |
| `tests/governance/`（新） | 長期有效的驗收測試，CI 跑 | 測試數定義改為 record＋governance |
| `tests/governance_once/`（新） | 只在升級當下成立的驗收測試，只在本 epic 驗收時跑 | 不進 CI、不進測試數 |
| `specs/auto-merge/runbook.md`（新） | 上線 8 步與凍結、外洩、交人合併程序 | — |
| `specs/auto-merge/evidence/g8-checklist.md`（新，啟用 PR 加入） | 信任模型 :193-203 的逐項證據 | — |
| GitHub 設定 | 三個 App、vars／secret、三條 ruleset | 直接 push main 被擋；PR 合併要 check 綠，或 admin 經 PR bypass |
| `bin/meeting.sh`、`.claude/skills/meeting-*`、`meeting-pipeline.js`、`vault/` | 不變 | 不變 |

## 6. 整合修訂與例外

| 第 n 條 | 原條文或既有定案 | 本 epic 的修訂 | 理由／出處 | 核准 |
|---|---|---|---|---|
| 1 | `e72a9cb` 版 `rules.md` 通用規則（本地改寫版） | 合回處置：規則 1 用本地文字；規則 2 用本地事實（origin、public、每次當下同意）＋模版的 publish.py 與「不直接推 protected_branches」，**不採**模版的「無人值守經 run.json 核准即可推送」，開 PR 改用 publisher 身分但仍要當下同意；規則 3 用本地文字並補模版的 force push；規則 4、7、22 改用模版的 `awf_hook.py` 名稱；規則 5、8、10、12–14、17、21、23、25 照模版（與本地相同）；規則 6、24 用模版文字，規則 6 加指向〈專案規則〉的例外；規則 9、11、15、19、20 是同一模版的渲染結果；規則 16 用模版文字，但本專案四個閘門都要使用者核准、不用 `--by policy`；規則 18 用模版文字並補 `Spec-Epic` trailer；模版新增的「規則 ↔ 強制方式」節保留 | D5「逐條合回」；`research-code-contracts.md:27`、`:52` | 隨閘門 2 核准 |
| 2 | D6：兩條 ruleset，A（無 bypass）含 required status check | 改為三條：A 無 bypass（要 PR、Require review from Code Owners、Block force pushes、Restrict deletions，不開 last push approval）；B 只放 Restrict updates，bypass 給 merger App 與 admin；C 放 required checks，只有 admin 能 bypass、且只限經 PR 合併 | `adr/adr-am-rulesets.md`：D6 原案下 gate 判 hold／escalate 的 PR 誰都合不了（`agent-merge-gate.yml.tmpl:177`、`merge_gate.py:538`）；admin 可略過 required check 偏離信任模型 :28，記在該 ADR | E1：使用者 2026-10-28 |
| 3 | 信任模型 :28「admin 也不例外」、:23「最後一次 push 要核准」、:36「組織擁有的 App」、:79／:202「只開 low」 | 依第 2 條、D3、D1 偏離 | `adr/` 四份 | D1、D3、E1：2026-10-28 使用者 |
| 4 | intent §2 G8「測試 PR 預期判定是 escalate」 | 改為：判定可為 hold 或 escalate，驗收看 §4.7.6（需求讀到、reasons 含「auto_merge 未啟用」）與 §4.7.7（輸入留言被採用、與本機 audit 一致） | `merge_gate.py:538` hold 優先於 escalate；測試 PR 的驗證證據不是該 head 的 verifier 結果、本 spec 的 §4.7 條目在啟用前也拿不到證據，必有 hold 理由 | E4：使用者 2026-10-28（intent 不改，本條是對 intent 驗收的修正） |
| 5 | 審查規則「修改既有檔超過 300 行或 15 檔列 important」（`rules.md:57`） | 本 epic 的 PR 超過（`init.py --force` 覆蓋十多支模版檔）；不拆 PR，按 commit 分段審（§4.1.10、plan §5） | 升級是機械覆蓋，拆 PR 會讓中間狀態新舊混用（`research-code-contracts.md:68`） | E6：使用者 2026-10-28 |
| 6 | D-3：verify 指令 | 不變；新增「CI required check 是子集」與 gate 測試數定義（record＋governance，不含 governance_once） | D2；E2 | D2、E2：2026-10-28 使用者 |
| 7 | intent §2 末段、C5：沒有 spec 的 bugfix PR 怎麼取需求 | N1：需求＝它修的那個 epic 最後一輪全部條目，不允許 trailer 縮小（§4.3.13） | `adr/adr-am-requirements.md` | E3：使用者 2026-10-28 |

## 7. 疑慮

1. **steward 是否照 merge 指引做**（`GH_CONFIG_DIR` 前綴、貼留言前名稱掃描、`--checks` 排除 gate、等 check 完成）：定義在 AgentWorkFlow（禁區），本 repo 只能透過 methodology.json 與 rules.md 要求；漏掉前綴時 gh 用使用者身分寫入（hook 仍放行合併，因為 hook 不看身分），伺服器端 ruleset B 的 bypass 也含 admin，**這種情況會以使用者身分合併成功**。建議 deliver 段之後的首次合併由使用者看 PR 時間軸確認合併者是 merger App；長期解法是回饋 AgentWorkFlow 讓 steward 原生支援 App 身分（衍生工作）。
2. **`hosts.yml` 格式與 `GH_CONFIG_DIR`**：gh 2.96 對多帳號的 `hosts.yml` 結構可能要求 `users:` 子鍵；未能確認，`ops-apps`（§4.7.1）實測，不行就改格式（只改 `gh_app_token.py` 與其測試）。
3. **`openssl dgst -sign /dev/stdin`**：macOS 上 `/opt/homebrew/bin/openssl` 與系統 LibreSSL 行為可能不同；`app-tools` 子任務用測試金鑰實測，不行就改成 `-sign` 讀 0600 暫存檔並在 finally 刪除（要回報並更新 §4.4.2）。
4. **CI 子集在 x86_64 與 aarch64 的差異**：本機 docker 是 linux/aarch64，GitHub 的 `ubuntu-latest` 是 x86_64；§4.2.7 在 aarch64 綠不保證 x86_64 綠，`ops-trial` 的 §4.7.5 是最終證據。
5. **gate 輸入留言的剩餘洩漏面**：名稱清單沒涵蓋到的名字、或證據裡的檔名與路徑仍可能透露資訊；`sdlc-merge` 的 Record 段會留下留言內容在本機 run 目錄，使用者抽查。
6. **測試數定義會因新增 `tests/governance` 而在本 epic 合併當下跳升**：之後的 PR 以合併後的數字為基準，不影響 gate 判定。
7. **bugfix PR（N1）多半 hold**：使用者已決定採 N1（E3）；D1 開到 medium 的收益在 bugfix 上拿不到，屬已接受的代價。
8. **`init.py --force` 的實際輸出未實測**（派工單禁止 design 段執行）：plan §0 第 3 步以白名單判定，白名單外有檔被改就停下回報。
9. **rule suite 與 REST 回應的欄位**：§4.7.11–§4.7.13 依 GitHub rule insights API 的 `result`（`pass`／`fail`／`bypass`）與 `rule_evaluations[].rule_source`、`rule_type`、`result` 判定；§4.7.8 以伺服器端的 REST 回應（HTTP 狀態與 `message`／`errors`）加上 `gh pr view` 的 `mergeStateStatus`、`statusCheckRollup` 讀回判定，rule suite 只當佐證。這些欄位名與「被 API 擋下的合併嘗試會不會留 rule suite 紀錄」design 段未能實測，讀回欄位不同時以同一語意的實際欄位對應、在 g8-checklist 註明。備案：(a) §4.7.8 的 REST 回應若只有籠統的「Repository rule violations」、沒有指出 required status check，而 rule suite 有這次紀錄，以 rule suite 的 C `fail`、A 沒有 `fail` 為準；兩者都沒有指出 C 時判「不能判定」，停下以選項式提問交使用者（例如：再以 `gh api repos/$REPO/rules/branches/main` 讀回 main 上生效的規則，確認 `required_status_checks` 生效且 C 的 bypass 不含 merger App，以「拒絕＋設定讀回」結案；或接受只以 (1) 的 `BLOCKED` 讀回結案，並在 g8-checklist 註明證據較弱），不得改用 `gh pr merge` 的 client 端訊息當證據。(b) §4.7.11 沒有 rule suite 紀錄時，以推送 stderr 裡伺服器回的違反規則清單為準（那是伺服器端訊息，不是 client 端判斷）。
10. **§4.7.11 的探測推送是不可逆節點**：ruleset 設錯時，空 commit 會直接進公開的 `main`（內容無害，但不 force push 就撤不回）。所以排在 §4.7.4 讀回通過之後，並要使用者當下同意。
11. **`tests/governance_once/` 在啟用後必紅**（`enabled` 已是 true）：它只在本 epic 驗收時跑，CI 與測試數都不含，保留作為升級紀錄。之後若有人從 repo 根執行不帶 `-s` 的 `unittest discover`，會把它掃進來而失敗；目錄內放 `README.md` 說明。
12. **§4.7.8 的 REST 試合是不可逆節點**：C 設錯（例如 merger App 誤入 C 的 bypass、或 context 名稱不符）時，這次呼叫會真的把測試 PR 合進公開的 `main`（內容只在 `specs/auto-merge/evidence/`，無害但撤不回）。所以排在 §4.7.4、§4.7.11 通過之後，並先讀回 `mergeStateStatus` 為 `BLOCKED` 才呼叫；帶 `sha` 只會合指定的 head。真的合進去時 §4.7.8 判不符、§4.7.12 無法做，停下回報，修 C 後另開測試 PR 重做 §4.7.5–§4.7.8、§4.7.12。

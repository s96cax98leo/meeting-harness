# 驗證報告：auto-merge（sdlc-test 第 2 輪）

- 驗證對象：`feature/auto-merge` @ `1c09c5a0b72ce1add0c864f79caa7558665d3473`（worktree `.worktrees/auto-merge`）。開工時與寫本檔前各查一次 HEAD，兩次相同；除了本檔（未追蹤）以外 worktree 是乾淨的
- 比對基準：`origin/main` ＝ `e72a9cb`（也是 merge-base）。反作弊與名稱掃描的範圍是 `e72a9cb..HEAD`（87 個檔，+8167／−235）
- 驗收依據：`specs/auto-merge/spec.md` §4.1–§4.8，共 71 條；另有 §6 整合修訂與例外 7 條
- 上一輪：第 1 輪在 `a593430` 判 §4.1.10 fail（缺陷 D1），其他條目 pass 57、not_verifiable 13。本輪所有檢查都在新 HEAD 自己重跑，沒有沿用第 1 輪的輸出
- 環境：macOS（Darwin 25.6.0，arm64）。指令都在 scratchpad 底下的獨立 `TMPDIR` 跑，並帶 `LC_ALL=en_US.UTF-8`；Python 用 `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`；容器用本機 docker `ubuntu:24.04`（linux/aarch64）。名稱清單只交給 `grep -qiF -f` 與 `MH_CLIENT_NAMES_FILE`，沒有讀出內容
- 安全邊界：沒有讀 `.env`、金鑰、`~/.meeting-harness`、`vault/`；沒有 push、沒有開 PR、沒有改 GitHub 設定、沒有執行 `init.py`，也沒有寫入守門設定。有一次指令列含 `ls …/publish.py`（只是列檔），被 hook 擋下；改用 `grep` 計數重跑，沒有執行 `publish.py`。突變抽查在 scratchpad 的 `git clone` 複本上做，每項做完都 `git checkout` 還原
- 寫檔範圍：只寫了本檔
- verifier 格式檢查腳本：repo 裡沒有（`.claude/teams/tools/` 底下沒有這類腳本），所以沒跑

## 0. 修正輪 1 的內容與核對

修正的是 D1（§4.1.10）。做法是用 `git filter-branch --msg-filter`，只改寫原 `386509a`（guard.config.json 合回）的 commit 訊息，再加一個 commit `1c09c5a`，在 `progress.md` 記下這次改寫。

| 核對項 | 指令 | 結果 |
|---|---|---|
| 改寫前有留備份分支（規則 21） | `git rev-parse feature/auto-merge--backup-pre-fix1` | `a593430…`，也就是第 1 輪驗證的 HEAD |
| 改寫只動訊息 | run 目錄 `fix1-sha-map.txt` 列出 17 對新舊 commit，逐對比 tree、作者／日期／committer、訊息 | 17 對的 tree 全部相同，meta 也全部相同；訊息只有 `386509a→f97bbda` 不同，其他 16 對相同 |
| 改寫的訊息差異 | `diff <(git log -1 --format=%B 386509a) <(git log -1 --format=%B f97bbda)` | 只多了「指令（…）」一段與完整的 `init.py` 指令列，內容和 `11b351e` 的指令列一致 |
| 整體內容不變 | `git diff --stat a593430 HEAD` | 只差 `specs/auto-merge/progress.md` 多一行 |
| 拓樸 | `git log --format='%h %p' e72a9cb..HEAD` | merge 結構保留（每個 merge 還是 2 個 parent），commit 數 24＝24 |
| 文件裡的舊 SHA 有沒有更新（規則 21 後半） | 用 sha-map 的 17 個舊短 SHA 跑 `git grep HEAD`（排除本檔） | 沒有命中 |
| 沒被推上去 | `git branch -r --contains 386509a`、`… f97bbda` | 兩個都沒有輸出，改寫只發生在本機 |

## 1. 機械檢查（在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0。印出 `✓ lint 通過（26 個檔）`；doctor 的 `✗` 是 0 個（`◦` 是選用項） |
| V2 | `$PY -m unittest discover -s tests/governance -t . -v` | rc=0，`Ran 48 tests`、`OK`；`FAIL:`／`ERROR:` 0、`skipped` 0 |
| V3 | `$PY -m unittest discover -s tests/governance_once -t . -v` | rc=0，`Ran 7 tests`、`OK`；`skipped` 0 |
| V4 | `MH_CLIENT_NAMES_FILE=<清單> caffeinate -i $PY -m unittest discover -s tests/record -t .` | rc=0，`Ran 532 tests in 953.905s`、`OK`；`FAIL:`／`ERROR:` 0、`skipped` 0 |
| V5 | `$PY tests/governance/support.py flip-enabled <tmp>/flipped.json`，再用 `MH_GUARD_CONFIG=<tmp>/flipped.json` 跑 tests/governance | 副本的 `auto_merge.enabled` 讀回是 `True`；`Ran 48 tests`、`OK`，`FAIL:`／`ERROR:` 0 |
| V6 | `$PY .claude/teams/tools/merge_gate.py --selftest`；`$PY .claude/teams/tools/build.py --check` | 前者印「merge_gate selftest：全部通過」，rc=0；後者印「16 支 workflow…全部一致」，rc=0 |
| V7 | `node .claude/teams/tools/check_workflows.mjs` | 不帶參數時 rc=1：預設去找專案的 `.claude/agents`，本 repo 沒有這個目錄，報「定義檔不存在」。設 `AWF_PLUGIN_DIR=<AgentWorkFlow>/plugin` 時 rc=0「workflow 檢查：全部通過」；設了同一個環境變數再跑 `test_flow_merge`，6 個測試都 ok。見 §3 解讀 (2) |
| V8 | 容器：`ubuntu:24.04` 裝 python3、git、openssl、nodejs（不裝 ffmpeg、不設 `MH_CLIENT_NAMES_FILE`）。掛載的是 HEAD 的 `git clone` 複本（唯讀，在容器內複製一份再跑），照 ci.yml 跑三條指令，連跑 3 次 | 3 次都是 lint=0、governance=0（`Ran 48`）、record 子集=0（`Ran 26 tests`、`OK`）；容器內沒有 `ffmpeg`、沒有 `MH_CLIENT_NAMES_FILE`；Python 3.12.3 |
| V9 | `$PY .claude/teams/tools/check_rules.py`；`check_rules.py --git . origin/main..HEAD` | 兩個都印「規則檢查：通過」，rc=0 |
| V10 | 名稱掃描：`git diff e72a9cb HEAD` 與 `git log e72a9cb..HEAD --format=%B` 各用 `grep -qiF -f <清單>` 比對；diff 裡新增或修改、目前仍存在的檔也逐一掃 | diff：沒有（rc=1）；commit 訊息：沒有（rc=1；改寫後的 `f97bbda` 也包含在內）；檔案：命中 0 個 |
| V11 | 本輪重新做的突變抽查，4 個（§4） | 4 個都被測試擋下 |

## 2. 逐條結果

結果只用三種：pass、fail、not_verifiable。表格裡的測試在 V2／V3 都是 ok。

**統計**：71 條。**pass 58**、**fail 0**、**not_verifiable 13**。not_verifiable 的是 §4.7.1–§4.7.13：這些是 deliver 之後由 `ops-*` 子任務執行的伺服器端步驟，spec §4 前言已註明本段判 not_verifiable 屬預期。

### 2.1 scaffold 升級與合回（§4.1）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.1.1 | pass | `test_upgrade::test_gate_selftest`；V6 自己重跑 `--selftest`，印「全部通過」；`merge_gate.py`、`publish.py`、`checklist.py` 三個檔都在（`grep -c` 計得 3） |
| 4.1.2 | pass | `sdlc-merge.js`、`event-post-merge.js` 都在；`test_flow_merge::test_build_check`、`::test_check_workflows`；V6、V7。照解讀 (2) 判定，見 §3 |
| 4.1.3 | pass | `governance_once/test_upgrade_once::test_meeting_pipeline_untouched` |
| 4.1.4 | pass | `::test_project_rules_kept` |
| 4.1.5 | pass | `test_rules_merge::test_general_rules_merged` |
| 4.1.6 | pass | `test_flow_merge::test_d8_kept` |
| 4.1.7 | pass | `::test_teams_readme_kept` |
| 4.1.8 | pass | `test_rules_merge::test_claude_md_import`、`governance_once::test_claude_md_kept` |
| 4.1.9 | pass | `::test_guard_config_preserved`。自己逐鍵比對：舊版頂層鍵沒有缺；值不同的只有 `_說明`（說明文字，`init.sh` 改成 `init.py`，並補了說明）；新增的鍵正好是 §3 列出的 6 個。照解讀 (3) 判定，見 §3 |
| 4.1.10 | **pass**（第 1 輪是 fail，本輪已修正） | 只含 init 輸出的 commit 是 `11b351e`：53 個檔裡有 30 個和 AgentWorkFlow `23174f0` 的 `scaffold/` 逐位元相同；其餘 23 個是佔位替換（`{{AGENT_NS}}`、`{{RUNS_DIR}}`、`{{FORK_REPO}}` 等）、內嵌 methodology，或是 init 新產生的檔，抽查 `save_run.py`、`sdlc-test.js`、`event-brief.js`、`sdlc-merge.js` 的差異都屬於這幾類。只改 `guard.config.json` 的 commit 是 `f97bbda`（`git show --stat` 只有 1 個檔）。兩者的內文都寫了「AgentWorkFlow 23174f0」和完整的 `…/init.py --target … --config … --answers … --force --with-merge-gate` 指令列 |
| 4.1.11 | pass | `::test_settings_permissions_kept` |

### 2.2 lint 與 CI 子集（§4.2）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.2.1 | pass | `test_lint::test_detects_fullwidth_after_var`；突變 M9 會被它擋下 |
| 4.2.2 | pass | `test_lint::test_repo_bin_clean`；V1 |
| 4.2.3 | pass | `test_lint::test_no_grep_p`；`bin/_lint.sh` 的 diff 裡 `grep -nP` 已改成 python |
| 4.2.4 | pass | `test_lint::test_backtick_check_kept` |
| 4.2.5 | pass | `test_ci_static::test_ci_shape`。讀檔確認：觸發只有 `pull_request` 與 `push: branches: [main]`；`permissions: contents: read`；兩個 `uses:` 都釘 40 碼 SHA；`runs-on: ubuntu-24.04`；checkout 設了 `fetch-depth: 0`、`persist-credentials: false` |
| 4.2.6 | pass | `test_ci_static::test_subset_excludes_name_tests`；自己核對 8 個模組都不含 `MH_CLIENT_NAMES_FILE`，ci.yml 也不含 `governance_once` |
| 4.2.7 | pass | V8：3 次都回 0，`tests.record` 子集 `Ran 26 tests` ≥ 1。這是 aarch64 的結果；x86_64 的最終證據在 §4.7.5（spec §7 第 4 點） |
| 4.2.8 | pass | `grep -rl 'guard.config.json' tests/governance` 只列出 `support.py`；`grep -rn e72a9cb tests/governance` 正好一行，`test_reqs_from_spec.py:16:REAL_SPECS_BASE = "e72a9cb"`；V5 翻轉後 `FAIL:`／`ERROR:` 0 個 |

### 2.3 requirements adapter（§4.3）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.3.1 | pass | `test_reqs_from_spec::test_trailer_resolves` |
| 4.3.2 | pass | `::test_diff_path_resolves` |
| 4.3.3 | pass | `::test_zero_or_many_epics` |
| 4.3.4 | pass | `::test_reads_base_not_head` |
| 4.3.5 | pass | `::test_missing_objects`、`::test_no_network_git` |
| 4.3.6 | pass | `::test_round_selection` |
| 4.3.7 | pass | `::test_row_filters`；突變 M6（拿掉「（選做）」排除）會被它和 `::test_real_specs` 擋下 |
| 4.3.8 | pass | `::test_exception_pointer` |
| 4.3.9 | pass | `::test_real_specs`（容器裡用 clone 複本跑也綠） |
| 4.3.10 | pass | `::test_source_points_to_row` |
| 4.3.11 | pass | `test_gate_adapter_integration::test_gate_reads_adapter`、`::test_adapter_failure_holds`（真的跑 `merge_gate.py check`，沒有 mock） |
| 4.3.12 | pass | `::test_writes_nothing` |
| 4.3.13 | pass | `::test_no_narrowing_trailer` |

### 2.4 App token 與名稱掃描（§4.4）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.4.1 | pass | `test_app_token::test_mint_writes_hosts` |
| 4.4.2 | pass | `::test_no_secret_leak` |
| 4.4.3 | pass | `::test_request_shape` |
| 4.4.4 | pass | `::test_failures` |
| 4.4.5 | pass | `::test_revoke` |
| 4.4.6 | pass | `test_scan_names::test_exit_codes`、`::test_output_never_leaks` |
| 4.4.7 | pass | `::test_default_path` |

### 2.5 設定與 merge 流程（§4.5）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.5.1 | pass | `governance_once::test_auto_merge_values`；自己讀回 `auto_merge`，去掉 `_說明` 後和 §3 逐鍵相等（`True`），`enabled` 是 false |
| 4.5.2 | pass | `test_upgrade::test_requirements_config`；讀回的 `requirements` 是 §3 的 command 設定，`protected_branches` 是 `["main"]` |
| 4.5.3 | pass | `test_flow_merge::test_merge_guidance` |
| 4.5.4 | pass | `::test_trailer_convention`、`::test_guidance_embedded` |
| 4.5.5 | pass | `test_ci_static::test_gate_workflow_present`；照解讀 (1) 判定，見 §3；突變 M7 會被它擋下 |
| 4.5.6 | pass | `test_ci_static::test_codeowners`；讀檔：正好 5 條，擁有者都是 `@s96cax98leo`，沒有萬用路徑 |
| 4.5.7 | pass | `test_upgrade::test_auto_merge_shape` |

### 2.6 規則文字（§4.6）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.6.1 | pass | `test_rules_merge::test_rule6` |
| 4.6.2 | pass | `::test_auto_merge_project_rule` |
| 4.6.3 | pass | `::test_claude_md_irreversible` |
| 4.6.4 | pass | `::test_check_rules`；V9 |
| 4.6.5 | pass | `test_runbook::test_sections` |
| 4.6.6 | pass | `test_rules_merge::test_main_session_no_direct_edit` |

### 2.7 伺服器端與啟用前檢查（§4.7）

全部判 **not_verifiable**。這些是 deliver（本 epic 的 PR 合併）之後，由使用者與主 session 執行的伺服器端步驟，要建 App、ruleset、測試 PR；本段不得改 GitHub 設定、不得 push、不得開 PR。執行順序照 spec §4.7 的執行序表，證據收在 run 目錄與 `specs/auto-merge/evidence/g8-checklist.md`。

| 節 | 結果 | 由哪個子任務執行 |
|---|---|---|
| 4.7.1 | not_verifiable | `ops-apps` |
| 4.7.2 | not_verifiable | `ops-apps` |
| 4.7.3 | not_verifiable | `ops-apps` |
| 4.7.4 | not_verifiable | `ops-rulesets` |
| 4.7.5 | not_verifiable | `ops-trial` |
| 4.7.6 | not_verifiable | `ops-trial` |
| 4.7.7 | not_verifiable | `ops-trial` |
| 4.7.8 | not_verifiable | `ops-trial`；(2) 由使用者在 Claude Code 以外的終端機執行 |
| 4.7.9 | not_verifiable | `ops-enable` |
| 4.7.10 | not_verifiable | `ops-enable` |
| 4.7.11 | not_verifiable | `ops-rulesets`；探測推送由使用者執行 |
| 4.7.12 | not_verifiable | `ops-trial` |
| 4.7.13 | not_verifiable | `ops-enable` |

### 2.8 迴歸（§4.8）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.8.1 | pass | V1 |
| 4.8.2 | pass | V4：`Ran 532 tests`，`FAIL:`／`ERROR:` 0 個；`git diff --diff-filter=M --name-only e72a9cb HEAD -- tests/` 是空的（`--diff-filter=D` 也是空的） |
| 4.8.3 | pass | `git diff --quiet e72a9cb HEAD -- bin/meeting.sh .claude/skills/` rc=0 |
| 4.8.4 | pass | V10：兩者都 rc=1（沒有） |
| 4.8.5 | pass | V2：`Ran 48 tests`，`FAIL:`／`ERROR:` 0、`skipped` 0 |
| 4.8.6 | pass | V3：`Ran 7 tests`，`FAIL:`／`ERROR:` 0、`skipped` 0 |

### 缺陷

本輪沒有缺陷。第 1 輪的 D1（§4.1.10）已經修正，核對過程見 §0 與 §2.1。

## 3. build 期間 agent 自行採用的三項解讀（派工單要求逐項核對）

| # | 條號 | 解讀 | 核對 | 判定 |
|---|---|---|---|---|
| (1) | §4.5.5 | 「不含 `{{`」改用 `(?<!\$)\{\{` 判斷有沒有未替換的佔位 | `agent-merge-gate.yml` 共有 25 個 `{{`，25 個都是 GitHub Actions 運算式 `${{`。`grep -nP '(?<!\$)\{\{'` 沒有輸出，python 計數也是 0。檔案與 AgentWorkFlow `23174f0` 的 `scaffold/.github/workflows/agent-merge-gate.yml.tmpl` 逐位元相同。測試在紅燈 commit `1720a2b` 就已經這樣寫（`test_ci_static.py:112`）。若照字面要求「完全不含 `{{`」，任何用到 `${{ }}` 的 Actions workflow 都過不了，所以字面寫法有瑕疵。突變 M7（加一行 `# {{FORK_REPO}}`）會被擋下，表示這個解讀仍然抓得到真正的佔位 | 解讀合理，判 pass。建議把 spec 條文改成「不含未替換的 init 佔位（`{{` 前面不是 `$`）」（衍生工作） |
| (2) | §4.1.2 | 沒有 plugin 時，`check_workflows.mjs` 改用暫存的空角色定義檔 | `test_flow_merge.py:33-50`：有 `AWF_PLUGIN_DIR`／`CLAUDE_PLUGIN_ROOT` 時用 plugin 的 `agents/`，會真的檢查定義檔存不存在。沒有時，在暫存目錄為 workflow 提到的每個 `tpm-*`／`dev-*` 角色放一個空檔，所以**這條路徑驗不到「定義檔存在」**，只驗 meta、schema 和乾跑。本 session 兩個環境變數都沒設（V2 走的是空檔路徑）；我另外設了 `AWF_PLUGIN_DIR=/Users/yuktang/Documents/Agent/AgentWorkFlow/plugin` 跑真檢查，rc=0，`test_flow_merge` 6 個測試都 ok。條文字面的 `node .claude/teams/tools/check_workflows.mjs`（不帶參數）在本機 rc=1，原因是它預設找專案的 `.claude/agents`，而本 repo 的角色定義在 plugin 裡，不在 repo 中 | 以「plugin 在場時真檢查 rc=0」判 pass。已知限制：CI 容器裡只會走空檔路徑，所以定義檔存不存在在 CI 不受檢查。建議在 spec 條文補上 `--agents-dir <plugin>/agents` 或 `AWF_PLUGIN_DIR`（衍生工作） |
| (3) | §4.1.9 | 底線開頭的說明鍵不比對值 | 逐鍵比對：值不同的舊鍵只有 `_說明`，舊值 109 字、新值 449 字。內容是模版說明（`init.sh`→`init.py`，並補上 agent 不能改本檔、namespace 規則等說明），不是設定值；其他舊鍵的值都相同。測試用 `strip_notes(old)` 排除說明鍵（`test_upgrade_once.py:66`）。突變 M8（把 `forbidden_trailers` 改成 `["Co-Authored-By"]`）會被擋下。照字面「除 §3 列出的鍵以外，值都應相同」來看，`_說明` 不在 §3，字面不成立 | 解讀合理（D5 的目的是保留設定值），判 pass。字面差異列在信封的 open_questions（不 blocking），請使用者確認，或在 spec 補一句「說明鍵不比」 |

## 4. 反作弊檢查（`git diff e72a9cb...HEAD`）

| 項目 | 結果 |
|---|---|
| 測試被 skip、only、fixme、expectedFailure 或刪除 | 沒有。`tests/` 新增的 `+` 行沒有 skip、expectedFailure 這類字樣；既有測試檔沒有被修改或刪除（`--diff-filter=M`、`D` 都是空的）；V2–V4 的 `skipped` 都是 0 |
| 紅燈 commit 之後驗收測試被改 | 沒有。`git log 1720a2b..HEAD -- tests/` 是空的（`1720a2b` 是紅燈測試 commit，改寫前為 `90bbb46`，兩者 tree 相同）。修正輪 1 沒有碰 `tests/` |
| 斷言放寬 | 沒有發現。測試沒有被改過；三項解讀都是紅燈階段就寫進測試的 |
| 被測物被 mock | 沒有。`unittest.mock`、`MagicMock`、`patch(` 都沒有使用；替身只用在外部邊界（`security`、git 記錄器、假 GitHub API） |
| 錯誤被吞掉或加了 retry | 新增程式只有一處 `except Exception`：`gh_app_token.py` 從 HTTP 錯誤本文抽 `message`，之後一定 `raise Fail`（exit 2），不算吞掉錯誤。沒有 retry、`continue-on-error`、`\|\| true` |
| 新增壓制註解 | 1 處：`tools/merge_gate_project/reqs_from_spec.py:54` 的 `# pragma: no cover`（沒有 buffer 的串流分支）。本 repo 沒有覆蓋率門檻，列為觀察，不判作弊。diff 裡另有 `# noqa: E402`，出在 `.claude/teams/` 底下的 scaffold 工具與 golden-set（`11b351e` 的 init 原樣輸出，屬於上游模版），不是本 epic 寫的 |
| lint／測試設定放寬 | 沒有。`bin/_lint.sh` 的全形字檢查從 `grep -P` 改成 python：macOS 的 BSD grep 沒有 `-P`，以前這項檢查會靜默略過，所以這次改動是變嚴；沒有 python3 時函式回非 0，會判為失敗（fail-closed）。CI 是新增的，沒有放寬任何既有門檻 |
| 證據的 commit 不是 HEAD | 不是問題：全部證據都在 `1c09c5a` 自己重跑。容器用的 clone 複本 HEAD 也是 `1c09c5a` |
| 上游既有測試被改 | 沒有 |
| 改寫歷史 | 修正輪 1 用 filter-branch 改寫了本機 17 個 commit 的 SHA。改寫前留了備份分支，17 對的 tree 都相同，只有一則訊息變了，也沒有推上 remote（見 §0）。符合規則 21，不判作弊 |
| 突變抽查（本輪新做，在 scratchpad 的 clone 上） | M6 拿掉「（選做）」排除 → `test_row_filters`、`test_real_specs` FAIL；M7 在 gate workflow 加 `{{FORK_REPO}}` → `test_gate_workflow_present` FAIL；M8 在設定副本把 `forbidden_trailers` 改掉 → `test_guard_config_preserved` FAIL；M9 lint 全形檢查一律回 0 → `test_detects_fullwidth_after_var` FAIL。突變前 baseline 全綠，突變後都已還原 |

## 5. 觀察（不影響判定）

1. `methodology.json` 的 commit 慣例要求 epic commit 結尾加 `Spec-Epic: <epic>`。`e72a9cb..HEAD` 的非 merge commit 裡，有這個 trailer 的只有 6 個（`4bc392b`、`071ed99`、`06ffed4`、`ec3571b`、`1720a2b`、`9daf54f`）；修正 commit `1c09c5a` 也沒有。這不影響 adapter 解析本 PR（diff 只碰 `specs/auto-merge/`）。本 epic 的 PR 合併時 base 還沒有 `specs/auto-merge/spec.md`，gate 會判 hold，本來就由人合併，屬預期
2. `check_workflows.mjs` 不帶參數在本機 rc=1，原因見 §3 (2)。之後若有人照條文字面跑，會誤以為壞了
3. 備份分支 `feature/auto-merge--backup-pre-fix1` 仍在本機。何時刪除由主 session 決定（刪除屬不可逆節點）

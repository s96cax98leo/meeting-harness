# plan：auto-merge

- 上游：`intent.md`（閘門 1 已核准）、`design.md`、`spec.md`、`adr/`。
- 狀態：**草稿，待閘門 2 核准**。
- 子任務 id 是短名，**不是任務編號**；分支 `feature/auto-merge--<id>`，各開 worktree，從當層開工時的 `feature/auto-merge` 開。
- commit：`test(auto-merge)`／`feat(auto-merge)`／`fix(auto-merge)`／`docs(auto-merge)`／`chore(auto-merge)`，內文寫 spec 條號，trailer 依序 `Spec-Epic: auto-merge`、`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

---

## 0. Build 前置（主 session，sdlc-build 開跑前完成）

`m-upgrade` 由主 session 在 `.worktrees/auto-merge`（分支 `feature/auto-merge`）執行，因為 agent 一律不能寫 `guard.config.json`（`plugin/hooks/guard.py:500-502`、`:917-918`、`:983-986`），而且 `init.py` 由主 session 跑（D5）。它是 `check` 子任務，sdlc-build 不處理；實作子任務**不**把它寫進 depends_on（design §3），改由這一節保證先後：

1. 確認 AgentWorkFlow HEAD 是 `23174f0`、工作樹乾淨；確認 `feature/auto-merge` 乾淨。
2. 寫 answers 檔到 run 目錄（methodology profile `default`；「主 session 會直接合併嗎」答「不會」），執行 `$PY /Users/yuktang/Documents/Agent/AgentWorkFlow/init.py --target /Users/yuktang/Documents/Agent/meeting-harness/.worktrees/auto-merge --config /Users/yuktang/Documents/Agent/meeting-harness/.worktrees/auto-merge/workflow.config --answers <answers 檔> --force --with-merge-gate`。
3. 對照 `research-code-contracts.md:50-64` 的覆蓋清單；有清單外的檔被改，停下回報。
4. `git add -A` 後 commit 1：`chore(auto-merge): init.py --force --with-merge-gate 升級 scaffold 到 AgentWorkFlow 23174f0（未合回）`，內文寫完整指令列與 answers 內容（spec §4.1.10）。
5. 以 `e72a9cb` 版為底，把 §3 的鍵寫進 `.claude/teams/guard.config.json`（其他舊鍵與值保留）；commit 2：`chore(auto-merge): guard.config.json 合回並加 auto_merge、requirements（enabled=false）`。
6. 跑 `$PY -c "import json;json.load(open('.claude/teams/guard.config.json'))"` 與 `$PY .claude/teams/tools/merge_gate.py --selftest`，都要過。

**注意**：commit 1 會把 `rules.md`、`.claude/teams/README.md`、`methodology.json`、`.claude/workflows/*.js`、`CLAUDE.md` 改成模版版本；它們之後歸 `rules-merge`、`flow-merge` 擁有，由那兩個子任務合回。

---

## 1. 子任務與分層

| 層 | id | kind | owns（只能改這些） | depends_on | Story |
|---|---|---|---|---|---|
| 前置 | `m-upgrade` | check | `.claude/teams/guard.config.json`；`init.py` 寫出的模版檔（只在 commit 1 寫一次）：`.claude/teams/tools/`、`.claude/teams/schemas/`、`.claude/teams/golden-set/`、`.claude/teams/methodologies/`、`.claude/teams/agent-workflow.CLAUDE.md`、`.claude/settings.json`、`.github/workflows/agent-merge-gate.yml`、`_tpm/runs/README.md` | — | G1、G5 |
| Red | `red-gov` | test | `tests/governance/`（新，整個目錄） | — | G1–G8 |
| 1 | `lint-fix` | code | `bin/_lint.sh` | `red-gov` | G2 |
| 1 | `reqs-adapter` | code | `tools/merge_gate_project/reqs_from_spec.py`（新） | `red-gov` | G3 |
| 1 | `app-tools` | code | `tools/merge_gate_project/gh_app_token.py`（新）、`tools/merge_gate_project/scan_names.py`（新） | `red-gov` | G4、G6 |
| 1 | `rules-merge` | doc | `.claude/teams/rules.md`、`.claude/teams/README.md`、`CLAUDE.md` | `red-gov` | G1、G7 |
| 1 | `flow-merge` | code | `.claude/teams/methodology.json`、`.claude/workflows/sdlc-*.js`、`.claude/workflows/event-*.js`（`meeting-pipeline.js` 除外） | `red-gov` | G1、G3、G6 |
| 1 | `runbook` | doc | `specs/auto-merge/runbook.md`（新） | `red-gov` | G4、G8 |
| 2 | `ci` | code | `.github/workflows/ci.yml`（新）、`.github/CODEOWNERS`（新） | `red-gov`、`lint-fix`、`reqs-adapter`、`app-tools`、`rules-merge`、`flow-merge` | G2、G4 |
| 後 | `ops-apps` | check | GitHub App 三個與安裝、Actions vars／secret（repo 外）；`~/.config/meeting-harness/`（repo 外）；`_tpm/runs/client-names.txt` | `ci`、`runbook` | G4、G6 |
| 後 | `ops-rulesets` | check | GitHub ruleset A／B／C、Actions 的 PR 權限設定（repo 外） | `ops-apps` | G4 |
| 後 | `ops-trial` | check | 測試 PR 分支 `feature/auto-merge-trial` 與其 PR | `ops-rulesets` | G2、G3、G6、G8 |
| 後 | `ops-enable` | decision | 啟用 PR 分支 `feature/auto-merge-enable`：`.claude/teams/guard.config.json`（只改 `enabled`）、`specs/auto-merge/evidence/g8-checklist.md`（新） | `ops-trial` | G5、G8 |

**檔案歸屬**：同一時間只有一個擁有者。`m-upgrade` 在 sdlc-build 之前一次寫完；之後 `rules.md`、`.claude/teams/README.md`、`CLAUDE.md` 歸 `rules-merge`，`methodology.json` 與 workflows 歸 `flow-merge`（`build.py` 會重寫全部 workflows，所以整組歸它）。`guard.config.json` 在 `m-upgrade` 之後只有 `ops-enable` 會再改（那時已在 main，走新分支＋PR＋CODEOWNERS）。`progress.md` 由主 session 維護，不屬任何子任務。

**分層理由**：第 1 層六個互不相依的檔案群並行；`ci` 要在容器裡對整合後的分支跑 `tests/governance`（它涵蓋第 1 層全部產出），所以單獨一層。後四步由使用者在 deliver 之後執行（不可逆節點，intent §4.1 第 3 條）。

## 2. 各子任務要點與完成條件（可機械判定）

### 共通

- 只改 `owns`；不改 `progress.md`；不改任何既有測試（`git diff --diff-filter=M --name-only "$BASE" HEAD -- tests/record` 為空）。
- 每個子任務 commit 前跑 §3 第 1、2、4 條；第 2 條只允許「本子任務以外的子任務負責轉綠」的測試仍紅，且要在信封列出測試 ID 與負責的子任務。
- 名稱掃描結果只寫「有／沒有」。

### 各子任務

- **red-gov**：(1) spec §4.1–§4.6、§4.8.5 驗法欄列的測試函式都存在（`grep -n "def <名稱>"`），檔名照驗法欄；(2) 測試只用標準庫＋`git`、`bash`、`openssl`、`node`（`check_workflows.mjs`）；`gh_app_token` 的測試以 `openssl genrsa` 在執行時產生測試金鑰，不 commit 任何金鑰檔；替身 `security`、替身 API（`http.server` 執行緒）放在 `tests/governance/` 內；(3) 不含 `skip`、`skipIf`、`expectedFailure`；(4) 在 `feature/auto-merge`（`m-upgrade` 之後）跑一次，紅燈理由是「缺檔或缺字串」而不是語法或匯入錯誤（`grep -E 'SyntaxError|NameError' ` 沒有輸出）。
- **lint-fix**：`$PY -m unittest tests.governance.test_lint -v` 全過；`bash bin/_lint.sh` 回 0。
- **reqs-adapter**：`$PY -m unittest tests.governance.test_reqs_from_spec tests.governance.test_gate_adapter_integration -v` 全過；腳本只用標準庫，不呼叫網路、不寫檔（`grep -nE 'urllib|requests|open\([^)]*[\"\x27][wa]' tools/merge_gate_project/reqs_from_spec.py` 沒有輸出）。
- **app-tools**：`$PY -m unittest tests.governance.test_app_token tests.governance.test_scan_names -v` 全過；在本機 macOS 以測試金鑰手動跑一次 `openssl dgst -sha256 -sign /dev/stdin` 路徑（spec §7 第 3 點），結果寫進信封。
- **rules-merge**：`$PY -m unittest tests.governance.test_rules_merge -v` 全過；`$PY .claude/teams/tools/check_rules.py` 回 0。
- **flow-merge**：`$PY -m unittest tests.governance.test_flow_merge -v` 全過；`$PY .claude/teams/tools/build.py --check` 回 0；`git diff --quiet e72a9cb HEAD -- .claude/workflows/meeting-pipeline.js`。
- **runbook**：`$PY -m unittest tests.governance.test_runbook -v` 全過；runbook 裡的範例場次名只用「[Stand-up] 範例專案」，不寫任何 App ID、installation ID、token 的實際值。
- **ci**：`$PY -m unittest tests.governance.test_ci_static -v` 全過；§3 第 5 條容器指令連續 3 次回 0；`ci.yml` 的 `tests.record` 清單＝實測 3 次全綠的模組（從 `research-code-contracts.md:131` 的 17 個候選開始），在 `ci.yml` 註解寫實測日期與映像；`uses:` 的 SHA 是 `actions/checkout`、`actions/setup-python` 官方 release tag 對到的 commit（信封附查詢指令）。
- **ops-apps**：spec §4.7.1–§4.7.3 的指令輸出存進 run 目錄；`_tpm/runs/client-names.txt` 存在（只用 `test -s` 判斷）。
- **ops-rulesets**：開工前 `gh pr list --repo $REPO --state open` 為空；spec §4.7.4 的讀回 JSON 存進 run 目錄。
- **ops-trial**：spec §4.7.5–§4.7.8 的證據（check run URL、log 摘錄、`merge-audit.jsonl` 對應行）存進 run 目錄。
- **ops-enable**：spec §4.7.9、§4.7.10；PR 由使用者核准並合併後，主 session 讀回 `guard.config.json` 的 `auto_merge.enabled` 為 true（只讀）。

## 3. 測試指令（integrator 每合併完一層在 `feature/auto-merge` 全量跑；verifier 同）

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
export TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8
export MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt
BASE="$(git merge-base origin/main HEAD)"
```

1. `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。
2. `$PY -m unittest discover -s tests/governance -t . > "$TMPDIR/gov.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/gov.log"` 沒有輸出；`grep -c 'skipped' "$TMPDIR/gov.log"` 為 0。
3. `$PY -m unittest discover -s tests/record -t . > "$TMPDIR/rec.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/rec.log"` 沒有輸出。
4. 名稱掃描：`git diff "$BASE" HEAD | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 與 `git log "$BASE"..HEAD --format=%B | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 都回 1。
5. 容器（第 2 層 `ci` 之後才有意義）：worktree 的 `.git` 指向主 repo 的絕對路徑，所以把主 repo 以同一個絕對路徑掛進去：`M=/Users/yuktang/Documents/Agent/meeting-harness; docker run --rm -v "$M":"$M":ro -w "$PWD" ubuntu:24.04 bash -c 'apt-get update -qq && apt-get install -y -qq python3 git openssl nodejs >/dev/null && git config --global --add safe.directory "*" && <ci.yml 的三條指令>'`，連跑 3 次都回 0（唯讀掛載，容器內沒有 `MH_CLIENT_NAMES_FILE`、不連 GitHub；測試的暫存檔一律寫容器的 `/tmp`）。第 1 層時跳過本條。
6. `$PY .claude/teams/tools/merge_gate.py --selftest` 與 `$PY .claude/teams/tools/build.py --check` 回 0（`m-upgrade` 之後）。

## 4. spec 條號 ↔ 測試 ↔ 子任務

| spec | 測試檔 | 轉綠的子任務 |
|---|---|---|
| §4.1.1、§4.1.3、§4.1.9、§4.5.1、§4.5.2 | `test_upgrade.py` | `m-upgrade`（Red 時就應綠；紅表示前置沒做完） |
| §4.1.2、§4.1.6、§4.5.3、§4.5.4 | `test_flow_merge.py` | `flow-merge` |
| §4.1.4、§4.1.5、§4.1.7、§4.1.8、§4.6.1–§4.6.4 | `test_rules_merge.py` | `rules-merge` |
| §4.1.10 | —（verifier 讀 git log） | `m-upgrade` |
| §4.2.1–§4.2.4 | `test_lint.py` | `lint-fix` |
| §4.2.5、§4.2.6、§4.5.5、§4.5.6 | `test_ci_static.py` | `ci`（§4.5.5 由 `m-upgrade` 轉綠） |
| §4.2.7 | §3 第 5 條 | `ci` |
| §4.3.1–§4.3.10 | `test_reqs_from_spec.py` | `reqs-adapter` |
| §4.3.11 | `test_gate_adapter_integration.py` | `reqs-adapter` |
| §4.4.1–§4.4.5 | `test_app_token.py` | `app-tools` |
| §4.4.6、§4.4.7 | `test_scan_names.py` | `app-tools` |
| §4.6.5 | `test_runbook.py` | `runbook` |
| §4.7.1–§4.7.10 | —（使用者操作，證據進 run 目錄與 g8-checklist） | `ops-*` |
| §4.8.1–§4.8.5 | §3 第 1–4 條 | 全部 |

**開工時允許仍紅**：Red 層與第 1 層開工時，除 `test_upgrade.py` 以外的 `tests/governance` 測試都允許紅，由上表的子任務負責轉綠；第 2 層開工時只允許 `test_ci_static.py` 中 §4.2.5、§4.2.6、§4.5.6 的測試紅。

# plan：auto-merge

- 上游：`intent.md`（閘門 1 已核准）、`design.md`、`spec.md`、`adr/`。
- 狀態：**修正輪 1，待閘門 2 核准**（使用者 2026-10-28 的 E1–E6 已寫入；處理對照見 `_tpm/runs/20261028-sdlc-auto-merge/design-revise-對照.md`）。
- 子任務 id 是短名，**不是任務編號**；分支 `feature/auto-merge--<id>`，各開 worktree，從當層開工時的 `feature/auto-merge` 開。
- commit：`test(auto-merge)`／`feat(auto-merge)`／`fix(auto-merge)`／`docs(auto-merge)`／`chore(auto-merge)`，內文寫 spec 條號，trailer 依序 `Spec-Epic: auto-merge`、`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。

---

## 0. Build 前置（主 session，sdlc-build 開跑前完成）

`m-upgrade` 由主 session 在 `.worktrees/auto-merge`（分支 `feature/auto-merge`）執行，因為 agent 一律不能寫 `guard.config.json`（`plugin/hooks/guard.py:500-502`、`:508-510`、`:917-918`、`:983-986`），而且 `init.py` 由主 session 跑（D5）。它是 `check` 子任務，sdlc-build 不處理；實作子任務**不**把它寫進 depends_on（design §3），改由這一節保證先後：

1. 確認 AgentWorkFlow HEAD 是 `23174f0`、工作樹乾淨；確認 `feature/auto-merge` 乾淨。
2. 寫 answers 檔到 run 目錄（methodology profile `default`；「主 session 會直接合併嗎」答「不會」），執行 `$PY /Users/yuktang/Documents/Agent/AgentWorkFlow/init.py --target /Users/yuktang/Documents/Agent/meeting-harness/.worktrees/auto-merge --config /Users/yuktang/Documents/Agent/meeting-harness/.worktrees/auto-merge/workflow.config --answers <answers 檔> --force --with-merge-gate`。
3. **白名單檢查**（取代原本「對照 `research-code-contracts.md:50-64`」的寫法；該清單漏了 `schemas/`、`golden-set/`、`methodologies/`、`agent-workflow.CLAUDE.md`、`.claude/settings.README.md`、`.mcp.json.example`、`.mcp.README.md`，照字面會誤停）。白名單依 `init.py:500-518`（`dest_for`）與 AgentWorkFlow `scaffold/` 的實際檔案樹（`.claude/teams/{tools,schemas,golden-set,methodologies}`、`rules.md`、`README.md`、`guard.config.json.tmpl`；`.claude/workflows/{sdlc,event}-*.js`；`.claude/settings.json.tmpl`、`settings.README.md`；`.mcp.json.tmpl`→`.mcp.json.example`、`.mcp.README.md`；`CLAUDE.md.tmpl`→追加引用；`_runs/README.md`→`_tpm/runs/README.md`；`.github/workflows/agent-merge-gate.yml.tmpl`）：

   ```
   git status --porcelain --untracked-files=all | cut -c4- | grep -vE '^(\.claude/teams/|\.claude/workflows/(sdlc|event)-[a-z-]+\.js$|\.claude/settings\.(json|README\.md)$|CLAUDE\.md$|\.mcp\.json\.example$|\.mcp\.README\.md$|_tpm/runs/README\.md$|\.github/workflows/agent-merge-gate\.yml$)'
   ```

   沒有輸出才往下；有任何輸出（例如 `meeting-pipeline.js`、`bin/`、`tools/`、`tests/`、`.claude/skills/`、`.claude/hooks/`、`.mcp.json`）就停下，回報清單外的路徑（只列路徑），等使用者決定。
4. `git add -A` 後 commit 1：`chore(auto-merge): init.py --force --with-merge-gate 升級 scaffold 到 AgentWorkFlow 23174f0（未合回）`，內文寫完整指令列與 answers 內容（spec §4.1.10）。
5. 以 `e72a9cb` 版為底，把 spec §3 的鍵寫進 `.claude/teams/guard.config.json`（其他舊鍵與值保留）；commit 2：`chore(auto-merge): guard.config.json 合回並加 auto_merge、requirements（enabled=false）`。
6. 跑 `$PY .claude/teams/tools/merge_gate.py --selftest`，並用 `$PY -m json.tool` 讀一次守門設定確認是合法 JSON，都要過。

**注意**：commit 1 會把 `rules.md`、`.claude/teams/README.md`、`methodology.json`、`.claude/workflows/*.js`、`CLAUDE.md` 改成模版版本；它們之後歸 `rules-merge`、`flow-merge` 擁有，由那兩個子任務合回。`.claude/settings.README.md`、`.mcp.json.example`、`.mcp.README.md`、`_tpm/runs/README.md` 接受模版版本（與 `e72a9cb` 各差 2–21 行，沒有專案內容），不合回。

---

## 1. 子任務與分層

| 層 | id | kind | owns（只能改這些） | depends_on | Story |
|---|---|---|---|---|---|
| 前置 | `m-upgrade` | check | `.claude/teams/guard.config.json`；`init.py` 寫出的模版檔（只在 commit 1 寫一次）：`.claude/teams/tools/`、`.claude/teams/schemas/`、`.claude/teams/golden-set/`、`.claude/teams/methodologies/`、`.claude/teams/agent-workflow.CLAUDE.md`、`.claude/settings.json`、`.claude/settings.README.md`、`.mcp.json.example`、`.mcp.README.md`、`.github/workflows/agent-merge-gate.yml`、`_tpm/runs/README.md` | — | G1、G5 |
| Red | `red-gov` | test | `tests/governance/`（新，整個目錄）、`tests/governance_once/`（新，整個目錄） | — | G1–G8 |
| 1 | `lint-fix` | code | `bin/_lint.sh` | `red-gov` | G2 |
| 1 | `reqs-adapter` | code | `tools/merge_gate_project/reqs_from_spec.py`（新） | `red-gov` | G3 |
| 1 | `app-tools` | code | `tools/merge_gate_project/gh_app_token.py`（新）、`tools/merge_gate_project/scan_names.py`（新） | `red-gov` | G4、G6 |
| 1 | `rules-merge` | doc | `.claude/teams/rules.md`、`.claude/teams/README.md`、`CLAUDE.md` | `red-gov` | G1、G7 |
| 1 | `flow-merge` | code | `.claude/teams/methodology.json`、`.claude/workflows/sdlc-*.js`、`.claude/workflows/event-*.js`（`meeting-pipeline.js` 除外） | `red-gov` | G1、G3、G6 |
| 1 | `runbook` | doc | `specs/auto-merge/runbook.md`（新） | `red-gov` | G4、G8 |
| 2 | `ci` | code | `.github/workflows/ci.yml`（新）、`.github/CODEOWNERS`（新） | `red-gov`、`lint-fix`、`reqs-adapter`、`app-tools`、`rules-merge`、`flow-merge` | G2、G4 |
| 後 | `ops-apps` | check | GitHub App 三個與安裝、Actions vars／secret（repo 外）；`~/.config/meeting-harness/`（repo 外）；`_tpm/runs/client-names.txt` | `ci`、`runbook` | G4、G6 |
| 後 | `ops-rulesets` | check | GitHub ruleset A／B／C、Actions 的 PR 權限設定（repo 外）；§4.7.11 的探測推送（不落地，被拒後刪除本機的空 commit） | `ops-apps` | G4 |
| 後 | `ops-trial` | check | 測試 PR 分支 `feature/auto-merge-trial` 與其 PR；`specs/auto-merge/evidence/trial-pr.md`（新，只在測試 PR 裡） | `ops-rulesets` | G2、G3、G4、G6、G8 |
| 後 | `ops-enable` | decision | 啟用 PR 分支 `feature/auto-merge-enable`：`.claude/teams/guard.config.json`（只改 `enabled`）、`specs/auto-merge/evidence/g8-checklist.md`（新） | `ops-trial` | G4、G5、G8 |

**檔案歸屬**：同一時間只有一個擁有者。`m-upgrade` 在 sdlc-build 之前一次寫完；之後 `rules.md`、`.claude/teams/README.md`、`CLAUDE.md` 歸 `rules-merge`，`methodology.json` 與 workflows 歸 `flow-merge`（`build.py` 會重寫全部 workflows，所以整組歸它）。`guard.config.json` 在 `m-upgrade` 之後只有 `ops-enable` 會再改（那時已在 main，走新分支＋PR＋CODEOWNERS）。`progress.md` 由主 session 維護，不屬任何子任務。

**分層理由**：第 1 層六個互不相依的檔案群並行；`ci` 要在容器裡對整合後的分支跑 `tests/governance`（它涵蓋第 1 層全部產出），所以單獨一層。後四步由使用者在 deliver 之後執行（不可逆節點，intent §4.1 第 3 條）；`ops-rulesets` 的 §4.7.11 探測推送排在 §4.7.4 讀回之後，`ops-trial` 的 admin bypass 合併（§4.7.12）排在 merger 試合被拒（§4.7.8）之後。

## 2. 各子任務要點與完成條件（可機械判定）

### 共通

- 只改 `owns`；不改 `progress.md`；不改任何既有測試（`git diff --diff-filter=M --name-only "$BASE" HEAD -- tests/record` 為空）。
- 每個子任務 commit 前跑 §3 第 1、2、4 條；第 2 條只允許「本子任務以外的子任務負責轉綠」的測試仍紅，且要在信封列出測試 ID 與負責的子任務。
- 名稱掃描結果只寫「有／沒有」。

### 各子任務

- **red-gov**：
  1. spec §4 驗法欄的每個 `governance/…::…`、`governance_once/…::…` 都有對應的測試函式，下面這段指令**沒有輸出**（§4.8.5、§4.8.6 的驗法是 §3 的指令、§4.7 是人工步驟，本來就不在清單內）：

     ```
     grep -oE 'governance(_once)?/test_[a-z0-9_]+\.py::test_[a-z0-9_]+' specs/auto-merge/spec.md | sort -u | while IFS= read -r x; do f="tests/${x%%::*}"; fn="${x##*::}"; grep -qE "def ${fn}\(" "$f" 2>/dev/null || echo "缺 $x"; done
     ```
  2. `tests/governance/support.py` 提供 `guard_config_path()` 與 `flip-enabled <輸出檔>` 子指令（spec §4.2.8）；`grep -rl 'guard.config.json' tests/governance` 只列出 `support.py`；`grep -rn e72a9cb tests/governance` 恰好一行（`REAL_SPECS_BASE`）。
  3. 所有以 `e72a9cb` 為基準或斷言 `enabled` 為 false 的測試都在 `tests/governance_once/`（spec §4.1.3、§4.1.4、§4.1.7、§4.1.8 後半、§4.1.9、§4.1.11、§4.5.1）；`tests/governance_once/README.md` 寫明「只在 auto-merge epic 驗收時跑、CI 不跑、啟用後必紅」。兩個目錄都有 `__init__.py`。
  4. 測試只用標準庫＋`git`、`bash`、`openssl`、`node`（`check_workflows.mjs`）；`gh_app_token` 的測試以 `openssl genrsa` 在執行時產生測試金鑰，不 commit 任何金鑰檔；替身 `security`、替身 API（`http.server` 執行緒）、記錄參數的替身 `git` 放在 `tests/governance/` 內。
  5. `grep -rnE 'skip|expectedFailure' tests/governance tests/governance_once` 沒有輸出。
  6. 在 `feature/auto-merge`（`m-upgrade` 之後）跑 §3 第 2、6 條各一次，`grep -E 'SyntaxError|NameError|ImportError' "$TMPDIR/gov.log" "$TMPDIR/once.log"` 沒有輸出；`Ran N tests` 的 N ≥ 1。
- **lint-fix**：`$PY -m unittest tests.governance.test_lint -v` 全過；`bash bin/_lint.sh` 回 0。
- **reqs-adapter**：
  1. `$PY -m unittest tests.governance.test_reqs_from_spec tests.governance.test_gate_adapter_integration -v` 全過（含 §4.3.5 的 `test_no_network_git`：替身 `git` 記錄裡沒有 `fetch`／`pull`／`clone`／`remote`；§4.3.12 的 `test_writes_nothing`；§4.3.13 的 `test_no_narrowing_trailer`）。
  2. 只用標準庫、不碰網路：下面這段回 0（以 AST 列出 import，白名單外的模組一律不准；不用字串 grep，避免把 stderr 提示文字「請先 git fetch」誤判成呼叫）：

     ```
     $PY -c "import ast,sys;t=ast.parse(open('tools/merge_gate_project/reqs_from_spec.py',encoding='utf-8').read());m={a.name.split('.')[0] for n in ast.walk(t) if isinstance(n,ast.Import) for a in n.names}|{(n.module or '').split('.')[0] for n in ast.walk(t) if isinstance(n,ast.ImportFrom)};bad=sorted(m-{'__future__','json','os','re','subprocess','sys','typing','pathlib'});print(bad);sys.exit(1 if bad else 0)"
     ```
  3. 「不執行 `git fetch`」「不寫檔」由第 1 點的行為測試判定，不另做字串比對。
- **app-tools**：`$PY -m unittest tests.governance.test_app_token tests.governance.test_scan_names -v` 全過；在本機 macOS 以測試金鑰手動跑一次 `openssl dgst -sha256 -sign /dev/stdin` 路徑（spec §7 第 3 點），結果寫進信封。
- **rules-merge**：`$PY -m unittest tests.governance.test_rules_merge -v` 全過；`$PY -m unittest tests.governance_once.test_upgrade_once -v` 全過（其餘測試在 `m-upgrade` 後就已綠）；`$PY .claude/teams/tools/check_rules.py` 回 0。
- **flow-merge**：`$PY -m unittest tests.governance.test_flow_merge -v` 全過；`$PY .claude/teams/tools/build.py --check` 回 0；`git diff --quiet e72a9cb HEAD -- .claude/workflows/meeting-pipeline.js`。
- **runbook**：`$PY -m unittest tests.governance.test_runbook -v` 全過；ruleset 段照 `adr/adr-am-rulesets.md`〈決定〉的三條（E1），G8 段照 spec §4.7.4–§4.7.13 的順序；`grep -cE '待閘門 2|重新決定|推論' specs/auto-merge/runbook.md` 為 0；範例場次名只用「[Stand-up] 範例專案」，不寫任何 App ID、installation ID、token 的實際值。
- **ci**：`$PY -m unittest tests.governance.test_ci_static -v` 全過；§3 第 5 條容器指令連續 3 次回 0；`ci.yml` 的 `tests.record` 清單＝實測 3 次全綠的模組（從 `research-code-contracts.md:131` 的 17 個候選開始），在 `ci.yml` 註解寫實測日期與映像；`grep -c governance_once .github/workflows/ci.yml` 為 0；`uses:` 的 SHA 是 `actions/checkout`、`actions/setup-python` 官方 release tag 對到的 commit（信封附查詢指令）。
- **ops-apps**：spec §4.7.1–§4.7.3 的指令輸出存進 run 目錄；`_tpm/runs/client-names.txt` 存在（只用 `test -s` 判斷）。
- **ops-rulesets**：開工前 `gh pr list --repo $REPO --state open` 為空；spec §4.7.4 的讀回 JSON 存進 run 目錄；§4.7.4 全符合後（使用者當下同意）做 §4.7.11 的探測推送，推送 stderr、`git ls-remote` 前後值、rule suite 讀回存進 run 目錄。
- **ops-trial**：spec §4.7.5–§4.7.8、§4.7.12 的證據（check run URL、log 摘錄、`merge-audit.jsonl` 對應行、merger 試合的 stderr、rule suite 讀回、`gh pr view` 讀回）存進 run 目錄；測試 PR 最後是 `MERGED`（不得關閉）。
- **ops-enable**：spec §4.7.9、§4.7.10、§4.7.13；PR 由使用者核准並合併後，主 session 讀回 main 上守門設定的 `auto_merge.enabled` 為 true（只讀），並在 main 上跑一次 §3 第 2 條（`tests/governance` 應全綠）。

## 3. 測試指令（integrator 每合併完一層在 `feature/auto-merge` 全量跑；verifier 同）

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
export TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8
export MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt
BASE="$(git merge-base origin/main HEAD)"
```

1. `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。
2. `$PY -m unittest discover -s tests/governance -t . > "$TMPDIR/gov.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/gov.log"` 沒有輸出；`grep -c 'skipped' "$TMPDIR/gov.log"` 為 0；`grep -E '^Ran [1-9]' "$TMPDIR/gov.log"` 有輸出。
3. `$PY -m unittest discover -s tests/record -t . > "$TMPDIR/rec.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/rec.log"` 沒有輸出。
4. 名稱掃描：`git diff "$BASE" HEAD | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 與 `git log "$BASE"..HEAD --format=%B | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 都回 1。
5. 容器（第 2 層 `ci` 之後才有意義）：worktree 的 `.git` 指向主 repo 的絕對路徑，所以把主 repo 以同一個絕對路徑掛進去：`M=/Users/yuktang/Documents/Agent/meeting-harness; docker run --rm -v "$M":"$M":ro -w "$PWD" ubuntu:24.04 bash -c 'apt-get update -qq && apt-get install -y -qq python3 git openssl nodejs >/dev/null && git config --global --add safe.directory "*" && <ci.yml 的三條指令>'`，連跑 3 次都回 0（唯讀掛載，容器內沒有 `MH_CLIENT_NAMES_FILE`、不連 GitHub；測試的暫存檔一律寫容器的 `/tmp`）。第 1 層時跳過本條。
6. 一次性測試（只在本 epic 驗收時跑，CI 不跑；`ops-enable` 之後不再跑）：`$PY -m unittest discover -s tests/governance_once -t . > "$TMPDIR/once.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/once.log"` 沒有輸出；`grep -c 'skipped' "$TMPDIR/once.log"` 為 0；`grep -E '^Ran [1-9]' "$TMPDIR/once.log"` 有輸出。
7. 啟用後仍綠（spec §4.2.8）：`$PY tests/governance/support.py flip-enabled "$TMPDIR/flipped.json"`；`MH_GUARD_CONFIG="$TMPDIR/flipped.json" $PY -m unittest discover -s tests/governance -t . > "$TMPDIR/flip.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/flip.log"` 沒有輸出。（不在指令列寫守門設定的檔名，避免 hook 把整段當成寫入守門設定擋下，`guard.py:508-520`。）
8. `$PY .claude/teams/tools/merge_gate.py --selftest` 與 `$PY .claude/teams/tools/build.py --check` 回 0（`m-upgrade` 之後）。

## 4. spec 條號 ↔ 測試 ↔ 子任務

| spec | 測試檔 | 轉綠的子任務 |
|---|---|---|
| §4.1.1、§4.5.2、§4.5.7 | `governance/test_upgrade.py` | `m-upgrade`（Red 時就應綠；紅表示前置沒做完） |
| §4.1.3、§4.1.9、§4.1.11、§4.5.1 | `governance_once/test_upgrade_once.py` | `m-upgrade`（Red 時就應綠） |
| §4.1.4、§4.1.7、§4.1.8 後半 | `governance_once/test_upgrade_once.py` | `rules-merge` |
| §4.1.2、§4.1.6、§4.5.3、§4.5.4 | `governance/test_flow_merge.py` | `flow-merge` |
| §4.1.5、§4.1.8 前半、§4.6.1–§4.6.4、§4.6.6 | `governance/test_rules_merge.py` | `rules-merge` |
| §4.1.10 | —（verifier 讀 git log） | `m-upgrade` |
| §4.2.1–§4.2.4 | `governance/test_lint.py` | `lint-fix` |
| §4.2.5、§4.2.6、§4.5.5、§4.5.6 | `governance/test_ci_static.py` | `ci`（§4.5.5 由 `m-upgrade` 轉綠） |
| §4.2.7 | §3 第 5 條 | `ci` |
| §4.2.8 | §3 第 7 條（`support.py` 由 `red-gov` 寫） | `red-gov`；整層合併後由 integrator 確認 |
| §4.3.1–§4.3.10、§4.3.12、§4.3.13 | `governance/test_reqs_from_spec.py` | `reqs-adapter` |
| §4.3.11 | `governance/test_gate_adapter_integration.py` | `reqs-adapter` |
| §4.4.1–§4.4.5 | `governance/test_app_token.py` | `app-tools` |
| §4.4.6、§4.4.7 | `governance/test_scan_names.py` | `app-tools` |
| §4.6.5 | `governance/test_runbook.py` | `runbook` |
| §4.7.1–§4.7.3 | —（使用者操作） | `ops-apps` |
| §4.7.4、§4.7.11 | —（使用者操作） | `ops-rulesets` |
| §4.7.5–§4.7.8、§4.7.12 | —（使用者操作） | `ops-trial` |
| §4.7.9、§4.7.10、§4.7.13 | —（使用者操作） | `ops-enable` |
| §4.8.1–§4.8.5 | §3 第 1–4 條（§4.8.5＝第 2 條） | 全部 |
| §4.8.6 | §3 第 6 條 | 全部（驗收時） |

**開工時允許仍紅**：Red 層與第 1 層開工時，除 `governance/test_upgrade.py` 與上表標為 `m-upgrade` 轉綠的 `governance_once` 測試以外，都允許紅，由上表的子任務負責轉綠；第 2 層開工時只允許 `governance/test_ci_static.py` 中 §4.2.5、§4.2.6、§4.5.6 的測試紅。

## 5. PR 大小與審查分段（E6：不拆 PR，按 commit 分段審）

- 修改的既有檔估計超過 30 個（`init.py --force` 覆蓋的 `.claude/teams/tools/` 6 支、workflows 13 支、`rules.md`、`.claude/teams/README.md`、`settings.json`、`settings.README.md`、`.mcp.json.example`、`.mcp.README.md`、`_tpm/runs/README.md`、`CLAUDE.md`、`bin/_lint.sh`，加上 `schemas/`、`golden-set/` 的既有檔）；實際數字以 deliver 段 `git diff --diff-filter=M --name-only e72a9cb HEAD | wc -l` 為準。超過 `rules.md:57` 的 15 檔上限，使用者已接受不拆（spec §6 第 5 條，E6）。
- 拆 PR 的替代方案與不採用的理由：分 2 包（包 1＝`m-upgrade` 兩個 commit＋`rules-merge`＋`flow-merge`；包 2＝其餘）會讓包 1 合進 main 後、包 2 合進前，main 處於「新 scaffold、有 `auto_merge` 鍵、但沒有 adapter 與 CI」的中間狀態（`research-code-contracts.md:68`）；E6 已決定不採。
- 審查分段（deliver 段的 PR 說明照這個順序列 commit 範圍，審查者逐段 `git diff <前>..<後>`）：
  1. `m-upgrade` commit 1：機械覆蓋，對照 AgentWorkFlow `23174f0` 的 `scaffold/`，只看有沒有白名單外的路徑（§0 第 3 步）。
  2. `m-upgrade` commit 2：只有守門設定，對照 spec §3。
  3. `red-gov`：`tests/governance/`、`tests/governance_once/`。
  4. 第 1 層六個子任務的合併 commit，各自一段（`rules-merge` 重點看 spec §6 第 1 條的處置表）。
  5. 第 2 層 `ci`。
  6. 文件：`specs/auto-merge/`（spec、plan、design、adr、runbook）。

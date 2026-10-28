# ADR：hosted CI 的範圍、白名單等級與 gate 的數字輸入

- 狀態：提議（待 auto-merge 閘門 2 核准）
- 日期：2026-10-28
- 範圍：`.github/workflows/ci.yml`（新）、`bin/_lint.sh`、`.claude/teams/guard.config.json` 的 `auto_merge`、`.claude/teams/rules.md`〈專案規則〉。
- 依據：intent §5.1 D1、D2；§4.3 C1、C4、C8；§4.4「時序」。
- 偏離：信任模型 :79、:202「冷啟動只開 low」與 :22「自動合併通道只限最低風險等級」→ 本 repo 開到 medium（D1，使用者 2026-10-28 決定）。

## 背景

- D2：GitHub-hosted ubuntu，只跑明確列出的子集；`meeting.sh doctor`、Swift、mlx、名稱掃描不進 CI；required check ≠ 專案 verify。
- `bin/_lint.sh:14`、`:16` 的 `grep -nP` 在 macOS BSD grep 回「invalid option -- P」、被 `>/dev/null 2>&1` 吞掉，第 1 項檢查一直沒跑；GNU grep 上會命中 `_lint.sh` 自己 `:15`、`:20` 的 `$f：`（`research-code-contracts.md:128-129`）。
- 會讀客戶名稱清單的測試：`test_ms_docs.py::test_no_client_names_in_ms_files` 沒清單就 FAIL（`tests/record/test_ms_docs.py:45-49`），`test_r3_docs.py::test_no_client_names_in_r3_files` 沒清單就 skip（`tests/record/test_r3_docs.py:60-63`）。
- gate 一定要有至少一個 required check 且全部通過（`merge_gate.py:482-486`）；CI 的 gate 收「全部 check run」（排除自己，`agent-merge-gate.yml.tmpl:119`），本機 steward 用 `gh pr checks --required`（`sdlc-merge.js:104`）。

## 選項（`_lint.sh` 的全形字檢查）

| 選項 | 做法 | 代價 |
|---|---|---|
| L1. **改用 python3 做這項比對**（逐行套 `\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7F]`），並把 `$f：` 改成 `${f}：` | macOS 與 ubuntu 行為一致；python3 本來就是 `_lint.sh` 的依賴（`bin/_lint.sh:27`、`:30`） | 每個 `.sh` 多起一次 python（26 個檔，毫秒級） |
| L2. 偵測 `grep -P` 可不可用，不能用就失敗 | 改動最小 | macOS 上 lint 直接紅，等於 verify 指令在本機永遠不綠，除非另裝 GNU grep（新的本機依賴） |
| L3. `LC_ALL=C grep -E` 搭配位元組範圍 | 不起 python | BSD 與 GNU 對高位元組範圍的處理不同，正確性難證明 |

採 **L1**。

## 選項（CI 跑什麼）

| 選項 | 做法 | 代價 |
|---|---|---|
| T1. **一個 job `ci-ubuntu-subset`**：`bash bin/_lint.sh`；`python3 -m unittest discover -s tests/governance -t .`；`tests/record/` 只跑清單內的模組（在 `ubuntu:24.04` 容器實測連續 3 次全綠者，且排除任何會讀 `MH_CLIENT_NAMES_FILE` 的模組） | 清單明確；fork 的 PR 也能安全地跑（`pull_request` 觸發、只讀權限、不用 secret） | 子集外的退化（Swift、mlx、doctor）只能靠本機 verifier 抓；清單要人維護 |
| T2. 全部 `tests/record/` 都跑、失敗的加 skip | 覆蓋面看起來大 | 違反規則 20（不加 skip），而且 `test_ms_docs` 依規定不得 skip（`specs/meeting-speed/spec.md:389-395`） |
| T3. macOS hosted 或 self-hosted runner | 能跑 doctor、Swift | D2 已排除（self-hosted 在 public repo 讓 fork 的 PR 在存有會議資料的 Mac 上執行，`research-code-contracts.md:124`） |

採 **T1**。

- 觸發：`pull_request`（不用 `pull_request_target`，PR 程式碼在無 secret、`contents: read` 的環境跑）與 `push` 到 `main`（給 `event-post-merge` 讀的合併後訊號，信任模型 :201；`event-post-merge.js` 用 `gh run list --branch main`）。
- `actions/checkout`、`actions/setup-python` 以 40 碼 commit SHA 釘版；`fetch-depth: 0`（`tests/governance` 要讀 `e72a9cb` 的舊檔做合回比對）。
- job 名稱固定 `ci-ubuntu-subset`，ruleset C 以這個名稱、來源 GitHub Actions 列為 required check（`adr-am-rulesets.md`）。

## gate 的數字輸入

- `tests_before`／`tests_after`＝下面兩條指令輸出的 `Ran N tests` 相加，分別在 base 與 head 上由 verifier 在本機跑：`python3 -m unittest discover -s tests/record -t .`、`python3 -m unittest discover -s tests/governance -t .`。Swift 測試另外跑、不算進這個數字（它沒有統一的計數輸出，`tools/MeetingRecorder/Tests/run.sh`）。
- `daily_cap`＝3。依據：近 8 天合進 main 的 PR 是 #7–#10 共 4 個（`research-upstream.md:15-22`），一天 3 個已高於實際節奏；只在本機有效（C8）。
- 其餘門檻沿用預設（`small_lines` 100、`large_lines` 400、`large_files` 20、`carry_verdict_on_rebase` false）。

## 白名單等級（D1）

- `auto_merge.repos`＝`{"s96cax98leo/meeting-harness": "medium"}`。核准人：使用者（2026-10-28 閘門 1 決定 D1）。
- 代價（使用者已接受）：`bin/`、`tools/` 的程式改動可能在沒有人審的情況下進 main；判定品質倚賴需求對照、本機驗證證據與 CI 子集，而 CI 子集不含 doctor、Swift、mlx。
- 實際範圍仍受下列限制：任何 `.claude/`、`.github/`、`tools/merge_gate_project/` 改動 escalate（`merge_gate.py:74-91`）；> 400 行或 > 20 檔 escalate；需求讀不到 hold；bugfix 依 `adr-am-requirements.md` N1 多半 hold。
- 往上調（high）不在本 epic 範圍，走 PR＋CODEOWNERS。

## 後果

- CI 綠只代表 lint 與子集測試綠，不代表 `bash bin/_lint.sh && bash bin/meeting.sh doctor` 綠；merge 判定的驗證證據仍來自本機 verifier（rules.md〈專案規則〉寫明）。
- 時序：CI job 沒跑完時 gate 看到 `in_progress` 判 hold（`agent-merge-gate.yml.tmpl:119`、`merge_gate.py:71`、`:484-486`）。處理：steward 等非 gate 的 required check 都完成才貼 gate 輸入留言（留言觸發 gate 重跑，`agent-merge-gate.yml.tmpl:44-45`）；本機 gate 的 `--checks` 排除 `agent-merge-gate/decision` 本身（和 CI 的作法一致）；合併前再等 gate 的 check run 轉綠，沒轉綠就不合併（伺服器端也會擋）。寫進 methodology.json 的 merge 指引。

# meeting-harness agent team

主 session 本身就是執行者：用 agent 平行處理事件、開發需求，agent 之間用 JSON 信封交接。agents、skills、slash commands 與 hooks 來自 `agent-workflow` plugin；本目錄放專案自己的規則、schema、檢查工具與設定。入口是 `tpm-team` skill。

## 結構

| 位置 | 內容 |
|---|---|
| plugin `agents/dev-*.md` | 開發角色：spec-author、acceptance-tester、implementer、integrator、verifier、design-reviewer、security-reviewer、pr-reviewer |
| plugin `agents/tpm-*.md` | 通用角色：planner、researcher、upstream-analyst、reviewer、skeptic、writer |
| plugin `hooks/` | `guard-bash.sh`、`guard-paths.sh`（轉呼叫目標 repo 的 guard）、`check-envelope.sh`，以及測試 |
| `.claude/workflows/sdlc-*.js`（6） | 需求開發走 AI-native SDLC，每段一支，段與段之間由人核准（Workflow 工具只讀專案的 `.claude/workflows`） |
| `.claude/workflows/event-*.js`（7） | 簡報、上游變動、會議、PR 審查、需求變動、決策落地、Demo 前檢查 |
| `.claude/teams/guard.config.json` | 守門設定：run 目錄、repo 目錄、上游、fork、禁止路徑、允許的分支前綴、任務編號前綴、署名行 |
| `.claude/teams/schemas/` | 交件信封＋7 種 payload（schema 唯一來源） |
| `.claude/teams/tools/` | `build.py`（把 schema 內嵌進 workflow）、`check_envelope.py`、`check_rules.py`、`save_run.py`、`check_agents.py`、`check_workflows.mjs`、`schemalib.py` |
| `.claude/teams/golden-set/` | schema 的正反例，與官方 jsonschema 交叉比對 |
| `.claude/teams/rules.md` | 硬規則：通用規則＋專案規則 |
| `_tpm/runs/<YYYYMMDD>-<事件>-<短名>/` | 每次執行的信封、筆記與 `run.json`（記錄閘門核准），見 `_tpm/runs/README.md` |

## hooks 只註冊一次

hooks 有兩種安裝方式，**只能選一種**，否則同一個事件會跑兩次：

| 方式 | hooks 從哪裡來 | 專案 `.claude/settings.json` |
|---|---|---|
| plugin（預設，`init.sh --hooks plugin`） | `agent-workflow` plugin 的 `hooks/hooks.json`（`${CLAUDE_PLUGIN_ROOT}`） | 只放權限與專案設定，**不放 hooks** |
| 專案內（`init.sh --hooks project`） | 複製到專案 `.claude/hooks/`（`${CLAUDE_PROJECT_DIR}`） | 註冊 hooks；**不要再安裝或啟用 plugin 的 hooks** |

兩種方式都讀同一份設定 `.claude/teams/guard.config.json`；沒有這份設定時，hooks 只套用角色規則（tpm-*／dev-* 不 push、不對 GitHub 寫入、只寫自己的範圍），不擋主 session。

## 需求開發：AI-native SDLC

```
sdlc-plan ──[intent 核准]──> sdlc-design ──[spec＋plan 核准]──> sdlc-build ──> sdlc-test ──[結果確認]──> sdlc-deliver ──[推送／PR 由決策者決定]
  4 個 researcher 平行          spec-author                       紅燈測試（平行）       verifier                  4 軸 pr-reviewer
  spec-author 寫 intent         2 個 skeptic 平行檢查一致性        各層 implementer 平行   design／security reviewer  逐則 skeptic 反駁
  skeptic 挑錯                  （要修時跑 sdlc-design-revise）   （各自 worktree）       平行；fail 修 ≤2 輪       writer：PR 草稿＋執行紀錄
                                                                   integrator 逐層合併
```

- **worktree**：
  - epic：`<repo>/.worktrees/<epic>`，分支 `feature/<epic>`。
  - 子任務：`<repo>/.worktrees/<epic>--<task>`，分支 `feature/<epic>--<task>`。
  - `.worktrees/` 要在目標 repo 的 `.gitignore` 排除。
- **產出**：寫在目標 repo 的 `specs/<epic>/`，有 `specs/_templates/` 就照範本：intent、design、spec、plan、progress、verifier、design-review、security-review。
- **閘門紀錄**：`python3 .claude/teams/tools/save_run.py init|stage|approve|status <run_dir> …`。
- **Maintain 段**：上游變動、需求變動、決策落地、Demo 前檢查發現要開發的事，會產出 intent 草稿，回到 `sdlc-plan`。

## 交接：JSON 信封

- **信封格式**（`schemas/envelope.schema.json`）：`status`（done、blocked、needs_decision）、`summary`、`artifacts`、`evidence[{claim, source, result}]`、`confidence`（0–1）、`open_questions[{question, blocking, options[{choice, cost}], recommendation, default_applied}]`、`derived_work`（不編號）、`payload`（依角色而定）。
- **payload**：`subtasks`、`findings`、`verdicts`、`criteria`、`build-result`、`items`、`docs`。
- **強制方式**：
  - Workflow 裡的 `agent({agentType, schema})`：schema 由 `build.py` 從 `schemas/` 內嵌，驗證失敗會自動重試。
  - 用 Agent 工具派出時：回報最後要附一個 ```json 區塊，`check-envelope.sh` 會在 PreToolUse(SubagentHandback) 與 SubagentStop 檢查。
  - Agent Teams：任務描述寫 `output: _tpm/runs/<run>/<檔>.json`，由 `TaskCompleted` 檢查。
- **語意規則**（schema 表達不了的部分，在 `schemalib.semantic_errors`）：有 blocking 問題就不能 done；blocking 問題要附 ≥2 個選項；不自編任務編號（`task_id_prefix`）；子任務的檔案所有權不重疊，相依不指向不存在的子任務。

## 守門（guard.config.json）

- 擋 tpm-*／dev-* push 與對 GitHub 的寫入動作；推送一律由主 session 在決策者同意後執行。
- 擋推到 `upstream_repos`、對它做 gh 寫入；gh 寫入要明確寫 `--repo <fork_repo>`。
- 擋寫入、移動、刪除 `forbidden_paths`。
- 新分支只能用 `allowed_branch_prefixes`；不 force push、不 `--no-verify`（`main_session_git_rules` 為 true 時也套用到主 session）。
- 角色寫入範圍：tpm-writer 只寫 `writer_dirs` 與 repo 的 `specs/<epic>/*.md`；其他 tpm-* 只寫 `runs_dir`；dev-* 只寫 `repos_dir`（空字串＝工作區本身，`.claude/` 除外）與 `runs_dir`。
- 轉呼叫目標 repo（或 worktree）自己的 `guard-git.sh`、`guard-paths.sh`：角色名依 `role_map` 轉換（例如 `dev-implementer` → `implementer`）；轉呼叫前去掉 git 的 `-C` 等全域選項；worktree 裡沒有 guard 時改用主 repo 的。

## 驗證指令

```bash
python3 .claude/teams/tools/build.py --check                                   # 內嵌的 schema 和 schemas/ 一致
uv run --no-project --with jsonschema python3 .claude/teams/golden-set/run.py  # 正反例，與官方 jsonschema 交叉比對
node .claude/teams/tools/check_workflows.mjs --agents-dir <plugin>/agents      # workflow 乾跑
python3 .claude/teams/tools/check_agents.py --plugin-dir <plugin>              # agent 的格式
bash <plugin>/hooks/tests/run.sh --project .                                   # hook 測試
```

## 新增一種事件
1. 照 `event-*.js` 的骨架寫 workflow：拆工或固定角度 → 平行 → skeptic → writer。schema 用 `/*@schema:<payload>*/ null /*@end*/` 標記，agentType 寫 `NS + 'tpm-…'`。
2. 跑 `build.py`、`check_workflows.mjs`。
3. 在 `tpm-team` skill 的對照表加一列。
4. 需要新的 payload：放到 `schemas/payloads/`，並在 `golden-set/` 補正反例。

## 已知限制
- **Workflow 跑到一半不能等人輸入**，所以 SDLC 每段一支 workflow，閘門由主 session 處理。
- **Workflow 會把使用者訊息當授權轉給 subagent**：敏感流程（推送、對外）改用 Agent 工具逐段派。
- **Agent Teams 是實驗功能**：預設不開；開了之後，有名字的 subagent 會變成 teammate；`-p` 不能用。

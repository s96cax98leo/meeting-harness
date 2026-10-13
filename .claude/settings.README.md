# `.claude/settings.json` 與 hooks

init.sh 依 `--hooks` 從兩份範本挑一份產生 `.claude/settings.json`：

| `--hooks` | 範本 | 內容 | 前提 |
|---|---|---|---|
| `plugin`（預設） | `settings.json.tmpl` | 只有權限 | 安裝並啟用 `agent-workflow` plugin，hooks 由 plugin 的 `hooks/hooks.json` 註冊 |
| `project` | `settings.project-hooks.json.tmpl` | 權限＋hooks（指向 `.claude/hooks/`） | init.sh 會把 plugin 的 hooks 複製到 `.claude/hooks/`；**不要再啟用 plugin 的 hooks** |

**同一個 hook 只能註冊一次。** 兩邊都註冊時，每次 Bash／Edit／交件都會檢查兩次，擋下訊息也會重複出現。檢查方式：在 Claude Code 裡跑 `/hooks`，`guard-bash.sh` 應該只出現一次。

個人的權限放 `.claude/settings.local.json`（不提交），不要改這份共用設定。

## 如何放寬讀取限制

`permissions.deny` 預設擋 `.env*`、`*.pem`、`*.key`，安全優先。如果專案有非機敏的 `.key` 檔要讓 Claude 讀（例如本地化字串、範例金鑰格式說明）：

1. **優先用個人設定**：在 `.claude/settings.local.json`（不提交）加 `"allow": ["Read(./path/to/sample.key)"]`，只放行那個檔，不要刪共用的 deny。
2. 要全團隊放寬時，改共用 `settings.json`，把 `Read(**/*.key)` 換成更窄的規則（例如 `Read(./secrets/**/*.key)`），並在 rules.md 的「專案規則」記下原因與核准人。
3. `.env` 與 `*.pem` 不要放寬；要判斷有無機敏值只用 `grep -q`。

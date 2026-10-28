# ADR：三個 GitHub App 的身分、私鑰保管、本機取 token 與凍結

- 狀態：已決定（D3、D7：使用者 2026-10-28；角色由使用者 2026-10-28 確認，E5）
- 日期：2026-10-28
- 範圍：`tools/merge_gate_project/gh_app_token.py`（新）、`tools/merge_gate_project/scan_names.py`（新）、`.claude/teams/rules.md`〈專案規則〉、`.claude/teams/methodology.json` 的 merge 指引；GitHub 上的三個 App 與 Actions 設定（不在 repo）。
- 依據：intent §5.1 D3、D7；§4.1 第 2、5 條；C7、C8。
- 偏離：信任模型 :36「由組織擁有的 GitHub App」（D3 已決定，本 ADR 記錄）。

## 角色（E5：使用者 2026-10-28 確認）

| 角色 | 人 | 依據 |
|---|---|---|
| 三個 App 的擁有者 | 使用者（`s96cax98leo` 個人帳號） | D3；已確認（E5，使用者 2026-10-28） |
| 私鑰保管人 | 使用者 | 已確認（E5，使用者 2026-10-28） |
| 撤銷人 | 使用者 | 已確認（E5，使用者 2026-10-28） |
| 事故聯絡人 | 使用者 | 已確認（E5，使用者 2026-10-28） |

外洩處理（信任模型 :45）：先在 GitHub 停用（suspend）或移除該 App 的安裝，再到 App 設定頁產生新私鑰、刪除舊私鑰，最後更新 Keychain（merger、publisher）或 Actions secret（gate）。

## App 權限

| App | 權限（repository） | 誰用、在哪裡用 |
|---|---|---|
| gate | Checks: write、Pull requests: read、Contents: read、Metadata: read | 只在 CI（`.github/workflows/agent-merge-gate.yml`）用 `actions/create-github-app-token` 取 token，寫 `agent-merge-gate/decision` check run（`agent-merge-gate.yml.tmpl:63-68`、`:190`） |
| merger | Contents: write、Pull requests: write、Metadata: read | 本機 steward 的四種 gh 寫入：`gh pr comment`（gate 輸入留言）、`gh pr merge`、`gh pr review --request-changes`、`gh pr ready --undo`（`guard.py:456`） |
| publisher | Pull requests: write、Contents: read、Metadata: read | 本機主 session 呼叫 `publish.py` 時的 `gh pr create`；`git push` 仍用使用者本機的 git 認證 |

gate App 的權限文件寫 Checks: write（信任模型 :40），ruleset 頁有 `statuses:write` 的說法（intent §4.4）；CI 範本用的是 check-runs API（`agent-merge-gate.yml.tmpl:190`），所以只給 Checks: write；`ops-trial` 以 check run 出現與 ruleset C 綁得住來源為準。

## 選項（私鑰保管與 token 交付）

| 選項 | 做法 | 代價 |
|---|---|---|
| A. **gate 私鑰只放 Actions secret；merger、publisher 私鑰放 macOS Keychain；主 session 用 `gh_app_token.py mint` 取 1 小時的 installation token，寫進專用的 `GH_CONFIG_DIR`（`hosts.yml`，0600）；steward／publish 的 gh 寫入以 `GH_CONFIG_DIR=<固定絕對路徑> gh …` 前綴執行** | 私鑰不落地成 repo 或 run 目錄的檔案，不經過 agent；token 不出現在指令列、環境變數展開或輸出裡；hook 的合併放行條件看得懂這種寫法（`guard.py:289` 只擋 `$(`、反引號、`<(`、`${`，`_gh_pr` 在 token 串裡找 `gh pr <sub>`，`guard.py:304-323`） | token 檔在本機磁碟存活最多 1 小時，任何能讀家目錄的程序都讀得到（agent 有 Read 工具，只能靠規則禁止）；要寫一支小工具並測；steward 的派工單要多一段指引 |
| B. 私鑰 `.pem` 放家目錄、`GH_TOKEN` 環境變數 | 不用寫工具 | `.pem` 長期落地；steward 指令要帶 `GH_TOKEN=$(…)` 會被 hook 擋（`guard.py:417-418`），改成在 `.claude/settings.json` 的 `env` 設，則整個 session（含主 session）都變成 merger 身分，主 session 開的 PR 作者會是 merger，steward 不能對自己的 PR request changes（信任模型 :43） |
| C. 不用 merger App，steward 用使用者自己的 gh 身分合併 | 最簡單 | merger 身分＝PR 核准人＝admin，ruleset B 的 bypass 只剩 admin，D3 與信任模型 :41 的「merger App 是 restrict updates 白名單裡唯一的機器身分」都不成立 |

## 決定

採 **A**。

- Keychain 項目：service `meeting-harness.gh-app.merger`、`meeting-harness.gh-app.publisher`，值是 PEM 全文；由使用者在自己的終端機用 `security add-generic-password` 匯入，匯入後刪除下載的 `.pem`。gate 的私鑰只貼進 Actions secret `AGENT_GATE_APP_PRIVATE_KEY`，不進 Keychain。
- 非機敏設定 `~/.config/meeting-harness/gh-apps.json`：`{"merger": {"app_id": <數字>}, "publisher": {"app_id": <數字>}}`，使用者建立；不進 repo（App ID 改了不必走 PR）。
- `gh_app_token.py mint --app merger|publisher`：讀 App ID → 用 `security find-generic-password -w` 取 PEM 進程序記憶體 → `openssl dgst -sha256 -sign /dev/stdin` 簽 RS256 JWT（PEM 由 stdin 餵，不寫檔）→ `GET /repos/s96cax98leo/meeting-harness/installation` 取 installation id → `POST /app/installations/<id>/access_tokens`（限縮到本 repo 與上表權限）→ 寫 `~/.config/meeting-harness/gh/<app>/hosts.yml`（目錄 0700、檔 0600、原子替換）。stdout 只印 `{"app","config_dir","expires_at"}`。`revoke --app <app>` 撤銷 token 並刪 `hosts.yml`。
- 只有主 session 執行 `gh_app_token.py`（使用者當下同意的 sdlc-merge 或 publish 前），agent 不執行、不讀 `~/.config/meeting-harness/gh/`。這條寫進 rules.md〈專案規則〉；hook 擋不到（只能靠規則，屬信任模型 :13 的「低」層）。
- steward 的寫入指令格式（寫進 rules.md 與 methodology.json 的 merge 指引）：`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/merger gh pr <comment|merge|review|ready> <n> --repo s96cax98leo/meeting-harness …`；讀取（`gh pr view`、`gh pr checks`）用預設身分。
- 主 session 開 PR：`GH_CONFIG_DIR=/Users/yuktang/.config/meeting-harness/gh/publisher python3 .claude/teams/tools/publish.py push …`，仍要使用者當下同意（rules.md 規則 2 不放寬）。

## gate 輸入留言的名稱外洩（C7）

- 選項 (a) 貼留言前用本機清單比對、命中就不貼並判 hold；(b) 只放最低必要欄位。
- (b) 做不到：CI 的 gate 要整份 merge-decision、驗證證據、測試數與 findings（`agent-merge-gate.yml.tmpl:32-36`、`:136-141`），少了就 hold。
- 採 (a)：`scan_names.py --names-file <清單> <檔案>`，回 0（沒有）／1（有）／2（清單讀不到，視同有）；只印「有／沒有」。清單預設 `_tpm/runs/client-names.txt`（gitignore，主 session 從 `_tpm/runs/20261010-sdlc-meeting-record/client-names.txt` 複製一次）。steward 不能改（`dev-merge-steward.md` 在禁區），只能經 methodology.json 的 merge 指引與 rules.md〈專案規則〉要求它照做；是否遵守由 `sdlc-merge` 的 Record 段與使用者抽查。剩餘風險寫進 spec §7。

## 凍結（D7、C8）

- 凍結＝使用者在 GitHub 把 merger App 的安裝設成 suspended。效果：`gh_app_token.py mint --app merger` 失敗（exit 2）；已發出的 token 失效；steward 無法貼留言或合併，CI gate 收不到輸入就 hold；人仍可合併；ruleset 不放寬。
- 解凍＝使用者恢復安裝，並在 run 紀錄寫理由。
- 本機 `auto_merge.freeze_file`（`_tpm/runs/auto-merge.freeze.json`）照舊由 `event-post-merge` 的 freeze_writers 寫，作為 client 端減速帶。
- CI 的每日上限永遠從 0 算（`agent-merge-gate.yml.tmpl:154`），每日上限只在本機有效；`daily_cap=3`（spec §4.5）。

## 後果

- 使用者要做一次性的設定：建三個 App、安裝到本 repo、匯入兩把私鑰、建 `gh-apps.json`、設 Actions 的 `AGENT_GATE_APP_ID`、`AGENT_GATE_APP_PRIVATE_KEY`、`AGENT_MERGER_BOT`（runbook）。
- token 檔在磁碟上最多存活 1 小時；每次 sdlc-merge 結束由主 session `revoke`。
- `GH_CONFIG_DIR` 前綴是否被 hook 放行、`hosts.yml` 格式是否被 gh 2.96 接受，`ops-apps` 與 `ops-trial` 實測（spec §4.7）。

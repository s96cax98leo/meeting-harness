# progress：auto-merge

- 由主 session 依 integrator 的合併結果與使用者的操作結果維護；子任務不得改本檔（plan §2 共通）。
- 子任務 id 是短名，不是任務編號。伺服器端的 App ID、installation ID、token 不寫進本檔。

## 閘門

- [x] 閘門 1（intent）：2026-10-28 使用者核准（`run.json` 的 `plan.approved`）
- [ ] 閘門 2（design／spec／plan）：修正輪 1 已寫入使用者 2026-10-28 的決定 E1（三條 ruleset）、E2（一次性測試拆到 `tests/governance_once/`）、E3（bugfix 採 N1）、E4（測試 PR 驗收看 §4.7.6、§4.7.7）、E5（App 角色都是使用者）、E6（不拆 PR、按 commit 分段審）；閘門 2 本身待核准
- [ ] 閘門 3（test）
- [ ] 閘門 4（deliver）

## 子任務

### Build 前置（主 session）
- [ ] `m-upgrade`：commit 1（init 原樣）
- [ ] `m-upgrade`：commit 2（guard.config.json 合回＋`auto_merge`、`requirements`）

### Red
- [ ] `red-gov`

### 第 1 層
- [ ] `lint-fix`
- [ ] `reqs-adapter`
- [ ] `app-tools`
- [ ] `rules-merge`
- [ ] `flow-merge`
- [ ] `runbook`

### 第 2 層
- [ ] `ci`

### 驗收時（verifier）
- [ ] `tests/governance_once` 全綠（spec §4.8.6，`ops-enable` 之前）

### deliver 之後（使用者執行，不可逆節點逐步同意）
- [ ] `ops-apps`：三個 App、Keychain、`gh-apps.json`、Actions vars／secret、名稱清單複製
- [ ] `ops-rulesets`：確認沒有開著的 PR → ruleset A／B／C → 讀回（§4.7.4）→ 探測推送被拒（§4.7.11）
- [ ] `ops-trial`：測試 PR、gate 輸入留言、本機 audit 對照、merger 試合被拒（§4.7.8）→ 使用者以 admin bypass 合併（§4.7.12，不關閉）
- [ ] `ops-enable`：啟用 PR（`enabled: true`＋g8-checklist）→ 核准前合併被拒（§4.7.13）→ 使用者核准並合併 → 主工作區由使用者決定何時 pull

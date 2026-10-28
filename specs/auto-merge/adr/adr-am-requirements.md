# ADR：requirements adapter（從 base 的 `specs/<epic>/spec.md` 取驗收條件）

- 狀態：已決定（A：隨 auto-merge 閘門 2 核准；N1：E3，使用者 2026-10-28）
- 日期：2026-10-28
- 範圍：`tools/merge_gate_project/reqs_from_spec.py`（新）、`.claude/teams/guard.config.json` 的 `requirements`、`.claude/teams/methodology.json` 的 commit 慣例（`Spec-Epic` trailer）。
- 依據：intent §2 G3、§4.3 C5、C6、§5.2 Q5（暫定 A，隨 intent 一起核准）。

## 背景

- `merge_gate.py` 的需求來源有 json、command、spec-md 三種（`merge_gate.py:176-212`）；guard.config.json 有設 `path` 或 `command` 時以它為準（`:235-244`）。
- command adapter 以 `cwd=<專案根>` 執行，帶 `AWF_REPO`、`AWF_PR`、`AWF_HEAD_SHA`，120 秒逾時，exit 非 0 或輸出不是 JSON 都當成讀不到需求 → hold（`:176-191`、`:609`）。
- CI 從受保護的 base checkout 執行 gate 與 adapter（`agent-merge-gate.yml.tmpl:89-94`），PR head 只被 fetch 成 `refs/remotes/pr/head` 當資料（`:104`）；gate 那一步的環境沒有 `GH_TOKEN`（`:146-150`），adapter 不能打 API，只能用 git。
- 本 repo spec 的驗收條件是表格列，條號 `4.1.1` 這種多段數字（`specs/meeting-speed/spec.md:229`）；有「（修正輪刪除：…）」列（`:247`、`:251`）與「（選做）」列（`specs/meeting-record/spec.md:2343`）；meeting-record 一份 spec 有四輪（`## R2`、`## R3`、`## R3 補充輪` 標題在 `:950`、`:1382`、`:1982`）。
- commit scope 不能拿來找 epic：meeting-speed 的 commit 用 `fix(G1)`、`docs(G2)` 這類目標代號（`git log` 2026-10-25 前後）。

## 選項（需求來源）

| 選項 | 做法 | 代價 |
|---|---|---|
| A. **command adapter**：從 base 讀 `specs/<epic>/spec.md`，epic 由 PR 自己指出（commit trailer `Spec-Epic: <epic>`，或 diff 裡的 `specs/<epic>/` 路徑），只取最後一輪的驗收條件段、排除刪除列與選做列 | 一份設定涵蓋所有 epic；需求由已合併的 base 決定（Q5-A）；用 git 就能做，CI 不用 token | 要寫一支腳本＋測試；PR 能選「拿哪個 epic 的需求來比」（但要全部條目都對得上證據，選錯 epic 只會 hold） |
| B. spec-md＋自訂 `id_pattern`、`path` 寫死一份 spec | 不用寫程式 | 每換 epic 都要經 PR＋CODEOWNERS 改 `guard.config.json`；刪除列、選做列、多輪全部當需求（`research-code-contracts.md:109`） |
| C. 每個 epic 多產一份 `specs/<epic>/requirements.json` | 最確定 | 同 B 的 path 寫死問題；spec-author 多一份要同步的檔，兩份可能不一致 |

## 選項（沒有自己 spec 的 bugfix PR，intent §2 末段、C5）

| 選項 | 做法 | 代價 |
|---|---|---|
| N1. **不縮小**：bugfix PR 也用 `Spec-Epic` 指向它修的 epic，需求＝該 epic 最後一輪全部驗收條件 | 不讓 PR 自己挑需求；fail-closed | 像 #10 這種修 meeting-speed 的 bugfix，steward 要對 meeting-speed 全部條目（約 97 條）拿出目前 head 的證據，實務上會 hold → 交人合併；D1 開到 medium 的收益在 bugfix 上大多拿不到 |
| N2. 允許 trailer `Spec-Reqs: 4.11.2,4.11.7` 縮小到列出的條號（條號必須存在於 base 的 spec） | bugfix 也能自動合併 | PR 自己決定要被檢查哪幾條，gate 的信任度下降；被改壞但沒列到的條目只能靠 CI 子集與 verifier 抓 |
| N3. bugfix 先開一個小 epic（`specs/<bugfix>/spec.md`）單獨合進 main，再開實作 PR | 和 Q5-A 同一套 | 每個 bugfix 多兩道 PR 與一輪 plan／design |

## 決定

採 **A＋N1**（N1：E3，使用者 2026-10-28 決定；沒有自己 spec 的 bugfix PR，需求就是它修的那個 epic 的全部條目，不允許 trailer 縮小，spec §4.3.13）。

- 設定：`"requirements": {"source": "command", "command": ["python3", "tools/merge_gate_project/reqs_from_spec.py"], "path": "", "id_pattern": ""}`。
- 腳本放 `tools/merge_gate_project/`：路徑含 `merge_gate`，改到它的 PR 會被 `merge_gate.py:79` 判 SENSITIVE → escalate；另外列進 CODEOWNERS。
- 解析規則（spec §4.3 逐條定義，摘要）：
  1. base＝`AWF_REQ_BASE`（預設 `origin/main`）；head＝`AWF_HEAD_SHA`；兩者都要是本機有的 commit，merge-base 算得出來。
  2. epic 候選＝`git log <merge-base>..<head>` 的 `Spec-Epic` trailer 值 ∪ `git diff --name-only <merge-base>...<head>` 裡 `specs/<epic>/` 的 `<epic>`（排除 `_templates`）。候選要**恰好一個**，而且 base 上有 `specs/<epic>/spec.md`；否則 exit 2。
  3. 只讀 base 版本（`git show <base>:specs/<epic>/spec.md`），不讀 PR head 的 spec。
  4. 有 `## R<數字>` 開頭的二級標題時，只看最後一個這種標題到檔尾；沒有就看整份。
  5. 驗收段＝範圍內第一個文字含「驗收」的 2–4 級標題，到下一個同級或更高級標題為止。
  6. 條目＝驗收段內 `| <條號> | …` 的表格列（條號 `^\d+(\.\d+)+[a-z]?$`）；第二欄以「（修正輪刪除」或「（選做）」開頭的列排除；條號重複就 exit 2；一條都沒有也 exit 2。
  7. `text`＝該列條號之後的內容原文（去掉頭尾的 `|` 與空白）；同一範圍內「整合修訂與例外」段的表格列若出現 `§<條號>`，在 `text` 後面附「〔整合修訂與例外第 <n> 條提到本條，見 <spec 路徑>:<行號>〕」，只給指標、不抄內容（避免把別份 spec 的同號條文誤當成本條的例外）。
  8. 輸出 `{"requirements": [{"id", "text", "source": "specs/<epic>/spec.md:<行號>@<base 前 12 碼>"}], "epic": "<epic>", "base": "<40 碼>"}`；錯誤訊息寫 stderr（`merge_gate.py:186` 只取最後 300 字）。
- 本機與 CI 用同一支腳本：本機由 steward 呼叫 `merge_gate.py check` 時以主 checkout 為專案根（`CLAUDE_PROJECT_DIR`）；主 session 在派 sdlc-merge 前先 `git fetch origin`，PR head 不在本機時 adapter exit 2（不自己 fetch）。
- commit 慣例：`.claude/teams/methodology.json` 的 `conventions.commit.format` 加「epic 的 commit 結尾（署名行之前）加 `Spec-Epic: <epic>` trailer」。

## 後果

- 新 epic 一律先把 spec 單獨開 PR 合進 main（Q5-A），實作 PR 才讀得到需求；spec PR 本身 base 上沒有需求，會 hold，由人合併（intent §5.2 註）。
- meeting-record 之後若再開新輪，要開新 epic，或接受只檢查最後一輪。
- 本 epic 的 spec 也照這套格式寫（條號 `4.x.y`），`ops-trial` 的測試 PR 用 `Spec-Epic: auto-merge` 讀它（G8、信任模型 :199）。

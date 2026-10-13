# plan：meeting-record

- 上游：`intent.md`（已核准）、`design.md`、`spec.md`、`adr/`；修正輪對照：`_tpm/runs/20261010-sdlc-meeting-record/design-revise-對照.md`（第一至七輪）
- **D13 文件先寫**（使用者在閘門 2 第三修正輪的決定）：t5 文件排在 build 第 1 層、先於 t3／t4；文件是 t3／t4 的契約（§1 拆分理由、spec §2.4、§6 第 29 條）
- **CLI 表面只有一套定義**（第四修正輪）：寫法數（7）、寫法旗標、層旗標、寫法結束碼、`record help` 的文法、`usage()` 的 record 段、文件區塊格式、解析與參數組法，全部以 spec §2.4.1–2.4.8 為準；t1 的 `tests/record/surface.py` 照它實作、t4 的 help／`usage()` 照它輸出、t5 的區塊照它撰寫，三方不各自詮釋
- **build 段的啟動方式**：以 `scriptPath` 指向 **worktree** 的 `.worktrees/meeting-record/.claude/workflows/sdlc-build.js` 啟動；主工作目錄那份還沒有 `7c9a3a0` 的修正（`diff` 兩份檔案在第 91 行不同），用錯會讓 implementer 被要求改 `progress.md`
- **integrator 每層全量跑測試**：依 `rules.md:59` 的 verify 規則（主 session 於 `544df94` 寫入），integrator 每合併完一層要在 `feature/meeting-record` 跑本 plan §3「每層整合後的測試指令」，任何一條不綠就不得清 worktree、不得進下一層
- **D15／D16 視窗清單與會議標記**（第六修正輪，閘門 2 核准後、build 前補進）：spec §3.8 是唯一契約，驗收在 spec §4.15；工作併入既有子任務、不新增子任務、owns 不變——Core 純函式與 Apple Events 查詢在 t3（`tools/MeetingRecorder/Sources/`、`Resources/`），Swift 測試在 t2（`WindowListTests.swift`），prompt 選單、`record.sh` 參數、doctor 一行在 t4，文件說明在 t5，Python 側測試在 t1，實機驗收在 t6。不另拆子任務的理由：Core 的 `WindowList.swift` 與 `main.swift` 的 dispatch、`Resources/` 都已屬 t3，拆出去會讓兩個子任務擁有同一檔
- **客戶資料邊界**（第七修正輪，`CLAUDE.md`〈客戶資料邊界〉、`rules.md` 通用規則 13；repo 為 public）：specs、測試檔與測試範例一律不得出現真實客戶名稱、真實會議名稱、使用者的真實視窗／分頁標題或簡報檔名；範例標題用中性名稱（M+ 會議視窗用「[Stand-up] 範例專案」，spec §4.15 前言）。spec §4.14.3 以 `test_static_rules.py::test_no_client_names_in_repo_text` 機械擋，名稱清單放 run 目錄 `client-names.txt`、以 `MH_CLIENT_NAMES_FILE` 傳入、不進 repo。歷史 commit 的處理見 §5「推送前必辦」
- 分支：epic `feature/meeting-record`（worktree `.worktrees/meeting-record`）；子任務 `feature/meeting-record--<id>`，各開 worktree（`rules.md:36`）
- 子任務 id（t1…t6）只是本 plan 內的短代號，**不是任務編號**
- **t6 第三次中途修正輪（§8，2026-10-12，定案）**：I、J、K、L、M 與 §4.8.1 上限；依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議選項定案，使用者可於醒來後改選（spec §6 第 63–70 條）；子任務 p1–p5 同樣只是短代號
- 所有子任務 commit 前跑 verify：`bash bin/_lint.sh && bash bin/meeting.sh doctor`；另跑各自的測試指令（§3）
- 署名行：`Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`（`rules.md:35`）；不 push
- **`progress.md` 由主 session 維護**：不屬於任何子任務的 owns；主 session 在每層合併、每個閘門之後更新勾選（修正 skeptic 問題 1：原本讓 5 個子任務共用同一檔）。build workflow 這一側已由主 session 在 commit `7c9a3a0` 對齊：`.claude/workflows/sdlc-build.js:91` 給 `dev-implementer` 的指示改為「不要改 progress.md（它由主 session 依 integrator 的合併結果維護，不屬於任何子任務的 owns）」；同檔其餘提到 progress.md 的只有 `:21` 的 CTX（列為可讀的 spec 文件），沒有任何派工要求子任務寫它（第二輪 skeptic 問題 5；本 plan 不再改 workflow）

---

## 1. 子任務

| id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec |
|---|---|---|---|---|---|
| t1 | test | shell／Python 層紅燈測試＋端到端核對工具（含自我測試） | `tests/record/` | — | §4.1、4.2.3–4.2.4、4.2.8（靜態）、4.4.2、4.5.5–4.5.6、4.6、4.7、4.8、4.9.4（靜態）、4.11.3–4.11.5、4.11.8（靜態）、4.12（含 4.12.10）、4.13.1–4.13.3、4.13.7、4.14、4.15.10–4.15.15；`e2e_check.py` 支援 §4.3、4.4.3、4.4.4、4.8.1、4.9、4.10、4.15.16、4.15.18 |
| t2 | test | Swift 核心紅燈測試＋測試執行器 | `tools/MeetingRecorder/Tests/` | — | §3.4、3.8、4.2.1、4.2.2、4.2.5、4.2.7、4.3.2、4.4.1、4.4.3（計算）、4.5.1–4.5.4、4.5.7、4.5.8、4.11.1、4.11.2、4.11.5–4.11.8、4.15.1–4.15.9 |
| t3 | code | MeetingRecorder.app：preflight（13 項）、擷取（每段依視窗尺寸）、分段、監看（含音訊格式變更與音量紀錄）、停止、finalize 觸發、quick-start、menu bar、快捷鍵、視窗清單與會議標記（Apple Events 唯讀查 Chrome）、視窗認回、`diagnose-windows`；以 t5 的文件為準 | `tools/MeetingRecorder/Sources/`、`tools/MeetingRecorder/build.sh`、`tools/MeetingRecorder/Resources/`（含新增的 `MeetingRecorder.entitlements`）、`tools/MeetingRecorder/probe.sh` | t1、t2、t5 | §3.1、3.3、3.4（含 3.4.1）、3.5、3.8、§4.2（含 4.2.8）、4.3、4.4.1、4.5、4.9.4（Sources 部分）、4.11.1–4.11.3、4.11.5–4.11.8、4.12.9、4.15.1–4.15.11 |
| t4 | code | CLI 層：`record.sh`（含 `record help`、`--ask-automation`、視窗認回參數）、prompt（視窗選單與 ★ 預設）、finalize（逐段正規化）、estimate、`meeting.sh` 接線（含 `./record` 撞名、拿掉 `--recorder`／`--yes`、doctor 的「◦ 會議分頁標記」）、`config.json`；以 t5 的文件為準 | `bin/record.sh`、`bin/_record_prompt.py`、`bin/_record_finalize.py`、`bin/_record_estimate.py`、`bin/meeting.sh`、`config.json` | t1、t5 | §2（含 2.4）、§3.2、3.5（`record.sh` 端）、3.6、3.7、§4.1（含 4.1.11、4.1.12）、4.2.3、4.2.4、4.4.2、4.5.5、4.5.6、4.6、4.7、4.8.1、4.8.2、4.9.4（`record.sh` 部分）、4.12.7、4.12.8、4.13.1–4.13.3、4.15.12–4.15.14 |
| t5 | doc | skill、README、meeting-summary 指路、`.gitignore`（**文件先寫**，只依 spec／design 定案內容；含 spec §2.4 的 `record-cli` 區塊與會議視窗標記說明） | `.claude/skills/meeting-record/`、`.claude/skills/meeting-summary/SKILL.md`、`README.md`、`.gitignore` | t1 | §2.4（文件側）、§4.8.3、4.10.3（說明）、4.11.4、4.12.1–4.12.3、4.12.6、4.12.10、4.14.2、4.15.15 |
| t6 | check | 人工端到端驗收（test 段，與使用者一起做；第一步是量測閘門） | （無檔案；結果與截圖寫 run 目錄） | t3、t4、t5 | §4.2.6（13 項）、4.2.8（重新授權後 preflight 第 4、6 項）、4.3、4.4.3、4.4.4、4.5.4、4.5.5、4.7.1、4.8.1、4.9、4.10、4.11.1–4.11.3、4.11.7、4.13.4、4.13.5、4.15.16–4.15.18 |

**拆分理由**（數量最小化）：
- t1／t2 分開：兩種語言、兩套執行器，彼此不讀對方的檔；並行。
- t3／t4 分開：Swift 與 shell／Python 只經 `record.status.json`、`manifest.json`、`record.meta.json` 與 §3.5 的參數相接，契約已在 spec §3 釘住；並行。
- t3 不再拆第 2 階段：menu bar、quick-start 都要改 `Sources/main.swift` 的 dispatch，拆開會讓兩個子任務擁有同一檔。
- t3 相依 t1：t3 的完成條件要跑 t1 寫的幾支靜態檢查（§3 表中標「t3 轉綠」的 `test_static_rules.py` 函式）。Red 層 t1、t2 都完成後才進實作層，所以不增加等待。
- **同層 t3／t4 的靜態檢查不跨界**（第二輪 skeptic 問題 4）：t3 與 t4 在第 2 層平行、各自的 worktree 看不到對方的檔。所以每一支靜態檢查只掃**單一子任務擁有的路徑**：原本同時掃 `Sources/` 與 `bin/record.sh` 的 `test_no_default_device_write` 拆成 `_in_sources`（t3 轉綠）與 `_in_record_sh`（t4 轉綠）。不採「檔案不存在就跳過」，因為那會讓 `record.sh` 還沒寫時假綠。integrator 合併完第 2 層後在 `feature/meeting-record` 上全量重跑兩支測試指令（§3 末），確認兩半合起來也綠。
- **t5 先於 t3、t4（D13，第三輪 skeptic 問題 1）**：使用者決定文件先寫、文件是實作的契約。t5 只相依 t1——t1 的 `test_docs.py` 要先存在，t5 才有可跑的完成條件；t5 不讀 Swift 測試，所以不相依 t2。t3、t4 改相依 t5：它們的 worktree 從第 1 層合併後的 `feature/meeting-record` 開出（`sdlc-build.js:55` 以 `feature/meeting-record` 為基底），看得到 t5 的文件，`test_docs.py` 的一致性檢查（spec §4.12.7–4.12.9）在 t3／t4 自己的 worktree 就能跑。
- **為什麼不讓 t5 與 t2 同層**：`sdlc-build.js:28-29` 只把 `kind=test` 的子任務放進 Red 層，`doc` 一律進實作層；實作層的第一層就是 Red 之後最早能開始的時點。所以「t5 在 Red 之後的第 1 層、獨自一層」已是 t5 最早能做的位置，與 t2 同層在 workflow 上做不到，也沒有收益（t5 要等 t1 的 `test_docs.py`，而 t1 本來就與 t2 同屬 Red）。代價是多一層序列等待（t5 很小，只有文件）。
- **文件是契約、程式照文件做**：t3、t4 的派工單必須明寫「`meeting.sh record help`、子指令、旗標、結束碼、`--args` 子指令以 t5 的文件為準；不一致時改程式不改文件；真的需要改文件就以 `needs_decision` 回報」（spec §6 第 29 條）。t3、t4 不得改 t5 擁有的檔（owns 不重疊）；t5 也只能寫 spec §2.4 封閉清單內的寫法與旗標（spec §4.12.6 機械擋）。
- t6 是 test 段的人工項目，build 段不處理（`sdlc-build.js` 只跑 test／code／doc）。
- progress.md 不派給子任務：它只記進度，不是交付物；由主 session 統一維護最不會衝突。

**實作分層**（sdlc-build 依相依分層，`sdlc-build.js:33-43`）：Red：t1＋t2 → 第 1 層：t5 → 第 2 層：t3＋t4（平行）→（test 段）t6。

---

## 2. 各子任務要點

### t1 tests/record/
- `test_cli_dispatch.py`、`test_record_sh.py`、`test_prompt.py`、`test_estimate.py`、`test_finalize.py`、`test_concurrency.py`、`test_regression.py`、`test_static_rules.py`、`test_docs.py`、`test_e2e_check.py`
- `surface.py`（第四修正輪，spec §2.4.8）：模組層常數 `SURFACE`（`forms` 7 個、`form_flags` 3 組、`form_codes` 22 組、`layer_flags`＝`--recorder`、`--yes`、`codes`＝0 2 3 4 5，逐字抄 spec §2.4.2）與 `parse_help`（§2.4.3–2.4.4）、`parse_block`（§2.4.5）、`parse_usage`（§2.4.6）、`form_argv`（§2.4.7）。`test_docs.py`、`test_cli_dispatch.py`、`test_record_sh.py` 都 `from tests.record.surface import …`，不各自另抄清單或解析邏輯。解析器本身由下方 `test_surface_parsers.py` 在紅燈階段驗
- `test_docs.py`（D13 一致性檢查，spec §4.12.6–4.12.9；第三輪 skeptic 問題 2）：以 `surface.py` 比對。測試函式：
  - 文件側（t5 轉綠）：`test_skill_exists_and_sections`、`test_meeting_summary_frontmatter_unchanged`、`test_readme_updated`、`test_crash_loss_documented`（只檢查 SKILL.md 的文字，§4.8.3 的「`record finish` 的說明」指 SKILL.md 的 finish 段）、`test_shortcuts_instruction`、`test_docs_cli_block_matches_spec`、`test_meeting_tab_marking_documented`（第六修正輪，§4.12.10）
  - 程式側（t4 轉綠）：`test_docs_cli_block_matches_help`（解析 `meeting.sh record help` 的 stdout，與兩份文件的區塊比集合、失敗時印差集）、`test_docs_flags_match_behavior`（§4.12.8 (a)(b)）、`test_docs_exit_codes_match_behavior`（§4.12.8 (c)：從 `tests.record.test_record_sh` import `EXIT_CODE_CASES`，先比組合集合、再逐一執行）
  - 錄製器側（t3 轉綠）：`test_docs_app_args_exist_in_sources`（SKILL.md 的每個 `--args <子指令>` 都是 `Sources/main.swift` dispatch 的 case）
  - 以上函式名彼此都不是子字串，`unittest -k` 不會誤選
- `test_surface_parsers.py`（第四修正輪新增；只測 t1 自己的 `surface.py`，**紅燈階段就要綠**）：`test_parse_help_accepts_spec_example`（spec §2.4.3 範例 → 五個成分等於 `SURFACE`）、`test_parse_help_rejects_grammar_errors`（段頭缺漏／重複／順序錯、欄位數錯、`結束碼` 欄格式錯、層旗標出現在「旗標：」段，各一例都要報錯）、`test_parse_block_and_usage`（依 §2.4.5、§2.4.6 寫的合法樣本得到 `SURFACE` 的對應成分；反引號會被刪除）、`test_form_argv`（7 種寫法×有無寫法旗標／層旗標／`--no-such-flag` 的組法照 §2.4.7）。理由：t4 與 t5 都要對著這些解析器轉綠，解析器本身錯了會讓兩邊一起卡住，所以先在 Red 層用 spec 的範例把它釘住
- `test_record_sh.py` 要定義模組層常數 `EXIT_CODE_CASES`：結構與限制照 spec §2.4.7（dict，鍵 `form`／`scenario`／`setup`／`extra_args`／`expect`；`{(form, expect)}` 恰等於 `SURFACE.form_codes` 的 22 組；不含通則的 2——未知選項與 `./record` 撞名另由 `test_cli_dispatch.py` 驗）；`test_exit_code_matrix` 與 `test_docs_exit_codes_match_behavior` 共用它
- `test_cli_dispatch.py` 另加 `test_help_lists_record_forms`（§4.1.2：`parse_usage(meeting.sh help).forms == SURFACE.forms`，加層旗標行與結束碼行；前一版名為 `test_help_lists_six_record_forms`，第四修正輪改名）、`test_record_help_prints_surface`（§4.1.11：`help`／`-h`／`--help` 三者 stdout 相同、`parse_help` 五個成分等於 `SURFACE`）、`test_record_unknown_flag_exits_2`（§4.1.12：7 種寫法各加 `--no-such-flag`）、`test_meeting_sh_layer_flags_stripped`（§4.1.12；以 `MH_RECORD_OPEN` 替身把收到的參數寫進暫存檔來驗證）、`test_layer_flag_mid_position_stripped`（§4.1.12 (a)：`record preflight --recorder --window 1`，cwd 有 `record/`）、`test_layer_flag_trailing_position_stripped`（§4.1.12 (b)：`record windows --json --yes`，cwd 有無 `record/` 各一次）——後兩支是第五修正輪新增，argv 寫死、不經 `form_argv`。**第七修正輪**：兩支對替身參數**不得**斷言「恰為」，改照 spec §4.1.12 (i)–(iii)：每次呼叫都不含 `--recorder`／`--yes`；使用者給的參數（拿掉層旗標後）依原序是某次呼叫參數的子序列、`--window` 緊接 `1`；同一次呼叫含 §3.5 的必帶參數（preflight：`--session`、`--min-free-bytes`、`--run-id`、`--home` 各接一個值；windows：`--log` 接一個值、stdin＝`/dev/null` 時不含 `--ask-automation`）。這樣 t4 照 §3.5 補必帶參數不會讓這兩支紅；`test_meeting_sh_layer_flags_stripped` 只斷言 (i)
- `test_cli_dispatch.py` 的 `./record` 撞名測試：在 `TMPDIR` 建工作目錄與空的 `record/`；非互動用 `subprocess`（stdin 為 `/dev/null`）；互動用 Python `pty.fork()` 模擬終端機並送「1」「2」；`record.sh` 一律接 `MH_RECORD_OPEN` 替身，不得真的開 app
- `fakes/fake_open.sh`：`MH_RECORD_OPEN` 替身，每次被呼叫都把 `argv[1:]` 記成一筆（逐次附加、可還原每個參數的邊界，例如每筆一行、參數以 NUL 分隔），供 §4.1.12、§4.15.13 判定；依 `FAKE_SCENARIO`（`recording`／`preflight_fail_4`／`window_missing_3`／`collision_2`／`no_status`／`stale_status`／`warn_only`／`stream_died_5`）寫 `record.status.json`
- `fakes/slow_ffmpeg.sh`：`MH_FFMPEG` 替身，轉呼叫真 ffmpeg 前後各睡一段，用來在 finalize 期間插入 `meeting.sh status`
- 合成素材：測試內用 `ffmpeg -f lavfi`（`testsrc2`、`sine`、`anullsrc`）在 `TMPDIR` 產段落：一般 3 段；影片軌刻意短 2 秒；截掉尾巴模擬沒有 moov；兩種尺寸（如 1280×720 與 960×600）；缺 video stream；48 kHz 雙聲道與 16 kHz 單聲道混用
- `e2e_check.py <場次> [--expect-min S --expect-max S] [--device-switch] [--all-bluetooth] [--hfp] [--sync] [--fps-interval mm:ss-mm:ss] [--space-interval mm:ss-mm:ss] [--json] [--print-sync-source]`：讀 `record.meta.json`、`manifest.json`、`ffprobe`／`ffmpeg` 結果，逐條印 PASS／FAIL（`--json` 印機器可讀結果），全 PASS 回 0；`--print-sync-source` 印出產生同步測試源（持續低音量底音＋每 2 秒一次閃白與嗶聲）的 `ffplay` 指令
- `test_e2e_check.py`：用合成場次（已知 PASS 一組、每個判準各一組已知 FAIL）驗 `e2e_check.py` 的判讀，涵蓋 config 快照、畫布、fps 尖峰、gap、期望長度、裝置切換中斷（2 秒 PASS／4 秒 FAIL）、HFP 格式事件與同步偏移、Space 區間非黑比例（修正 skeptic 問題 11）。**這支在紅燈階段就要綠**（它只測 t1 自己的工具）
- **第六修正輪新增（D15、D16，spec §4.15）**：
  - `test_static_rules.py`：`test_entitlements_audio_input_only` **改名**為 `test_entitlements_audio_and_apple_events`（斷言鍵集合恰為 `{com.apple.security.device.audio-input, com.apple.security.automation.apple-events}`、值皆 true、沒有 `app-sandbox`；舊名不得保留）；新增 `test_info_plist_apple_events_usage`（§4.15.11）、`test_chrome_query_read_only`（§4.15.10：只讀 `chromeTabsScript` 常數的字串內容檢查禁用字，`Sources/` 恰一檔定義它、該檔含 `runningApplications(withBundleIdentifier` 與 `AEDeterminePermissionToAutomateTarget`、`Sources/` 無 `osascript`）
  - `test_prompt.py`：`test_prompt_window_menu_labels_and_default`、`test_prompt_no_default_without_meeting`、`test_prompt_outputs_window_identity`（§4.15.12；`--windows-json` 用測試內手寫的 §3.8.7 格式樣本，含 ★ 列、無標題列、`meetingCheck: not_authorized` 的 Chrome 列）
  - `test_record_sh.py`：`test_windows_ask_automation_only_with_tty`（pty 與 `/dev/null` 各一次，替身記錄參數）、`test_start_passes_window_identity`（互動開錄時替身收到的 `preflight`／`start` 參數含 `--window-bundle`、`--window-title`）；`fakes/fake_open.sh` 加 `windows` 情境：依 `FAKE_WINDOWS_JSON` 把指定的 JSON 寫進 `--log` 指的檔
  - `test_regression.py`：`test_doctor_mentions_meeting_tab_marking`（§4.15.14）
  - `test_docs.py`：`test_meeting_tab_marking_documented`（§4.12.10、§4.15.15；t5 轉綠）→ `test_docs.py` 共 **11** 支函式
  - `e2e_check.py` 不需新判準：§4.15.16 的切 Space 區間沿用 `--space-interval`，§4.15.18 (b) 沿用 `e2e_check.py <場次>`
- **第七修正輪新增（客戶資料邊界，spec §4.14.3、§4.15 前言）**：
  - `test_static_rules.py::test_no_client_names_in_repo_text`：讀 `MH_CLIENT_NAMES_FILE` 指的清單，掃 `specs/`、`tests/`、`tools/MeetingRecorder/Tests/` 下實際存在的每個檔；命中只印 `<相對路徑>:<行號>`、不印字串；清單檔不存在或無有效行 → 失敗；清單檔被 git 追蹤 → 失敗；未設定 → `skipTest`（訊息含「未設定 MH_CLIENT_NAMES_FILE」）。紅燈階段就要綠（本輪已把 specs 清乾淨）
  - 所有測試檔中的視窗標題、會議名稱、檔名一律用中性範例（M+ 視窗「[Stand-up] 範例專案」），不得寫任何真實客戶名稱或使用者的真實視窗標題；清單內容不得寫進 `tests/` 任何檔（測試只讀環境變數）
- 不得讀取任何客戶會議資料；不得在 repo 內留下媒體檔

### t2 tools/MeetingRecorder/Tests/
- `run.sh`（修正 skeptic 問題 4）：
  ```bash
  #!/bin/bash
  set -euo pipefail
  cd "$(dirname "$0")"
  shopt -s nullglob
  core=(../Sources/Core/*.swift)
  out="${TMPDIR:-/tmp}/mr-tests.$$"
  # bash 3.2 在 set -u 下展開空陣列 "${core[@]}" 會報 unbound variable 並結束，swiftc 根本不會執行
  swiftc -target arm64-apple-macosx15.0 ${core[@]+"${core[@]}"} *Tests.swift main.swift -o "$out"
  "$out"
  ```
  可從任何目錄執行；**必須在 macOS 內建 `/bin/bash`（3.2.57）下可跑**（第二輪 skeptic 問題 1：本機 `/bin/bash --version` 為 3.2.57，`set -u` 下 `"${core[@]}"` 對空陣列會 `core[@]: unbound variable`，已在本機重現；改用 `${core[@]+"${core[@]}"}` 後空陣列展開為零個參數，swiftc 照常執行並報 `cannot find 'segmentFileName' in scope`，亦已重現）。紅燈階段 `Sources/Core/` 不存在時 swiftc 報的是「cannot find '…' in scope」（缺符號），不是「no such file」，也不是「unbound variable」
- `main.swift`（極簡斷言執行器，失敗回非 0）、`AudioLevelTests.swift`、`DetectorsTests.swift`、`PreflightTests.swift`、`RecordsTests.swift`、`SegmentsTests.swift`、`TriggerTests.swift`、`WindowListTests.swift`（第六修正輪，spec §4.15.1–4.15.9：`testExclusionReasons`、`testMeetingServiceFromURL`、`testMeetingAppService`、`testChromeWindowMatching`、`testWindowRowsOrderingAndMarks`、`testWindowRowLabel`、`testFullScreenSized`、`testRowsWithoutAutomation`、`testWindowRowJSONKeys`、`testAutomationStatusMapping`、`testResolveWindow`、`testDiagnoseIncludesExcluded`；只以手建的 `WindowCandidate`／`ChromeWindowInfo` 餵 Core，不呼叫 SCK 與 Apple Events）
- **第七修正輪（客戶資料邊界，spec §4.15 前言）**：`WindowListTests.swift` 等測試的視窗標題一律用中性範例——§4.15.4／§4.15.5 的 M+ 列標題用「[Stand-up] 範例專案」，§3.8.6 的例子逐字照 spec（已是中性名稱）；不得寫真實客戶名稱、真實會議名稱或使用者的真實視窗標題。由 t1 的 `test_no_client_names_in_repo_text`（掃 `tools/MeetingRecorder/Tests/`）在 Red 層合併後擋
- `PreflightTests.swift` 的 `testTwelveItemsAndSeverity` 改名為 `testPreflightItemsAndSeverity`（13 項、4 個 warn，spec §4.2.1；舊名不得保留）
- 測試只引用 spec §3.4 的名稱與參數標籤；雙聲道非交錯、16 kHz 單聲道 Int16、24 kHz 交錯 Float32 的 `CMSampleBuffer` 要在測試內自己建（`d2:38-39`、D6）
- `RecordsTests` 以 `JSONSerialization` 讀回編碼結果，比對 spec §3.1–3.3 範例的鍵集合

### t3 MeetingRecorder.app
- 把 `main.swift` 的 `nonBlackRatio`、`frameStatus` 等移進 `Core/`（簽名照 spec §3.4）；`probe` 子指令保留
- `build.sh`：編 `Sources/**/*.swift`；簽章身分判斷用 `security find-identity -p codesigning`（**不加 `-v`**）比對 SHA-1 `5E249F84A9EC2F2D2B3914120906DF29FB4DF348`，有就 `codesign --force --options runtime --entitlements "${HERE}/Resources/MeetingRecorder.entitlements" --sign 5E249F84A9EC2F2D2B3914120906DF29FB4DF348`，沒有才退回 ad-hoc（ad-hoc 分支也帶同一個 `--entitlements`，不帶 runtime）
- 新增 `Resources/MeetingRecorder.entitlements`：恰為 `com.apple.security.device.audio-input = true` 與 `com.apple.security.automation.apple-events = true` 兩項，不得加 `com.apple.security.app-sandbox`（`design.md §9.1`、spec §4.2.8；第二輪 skeptic 問題 2：改用固定身分後 app 第一次以 hardened runtime 執行，沒有麥克風 entitlement 麥克風會被拒；第六修正輪 skeptic 問題 2：沒有 Apple Events entitlement，查 Chrome 會被拒且可能不跳框）；`Resources/Info.plist` 加 `NSAppleEventsUsageDescription`（繁中，含「Chrome」與「網址」，`design.md §9.1` 有文字例）
- **視窗清單（D15、D16，spec §3.8）**：`Core/WindowList.swift` 照 spec §3.4 的名稱實作；`Capture/ChromeTabs.swift` 放 `chromeTabsScript` 常數與 Apple Events 權限判斷／查詢（先 `NSRunningApplication` 確認 Chrome 在跑、`NSAppleScript` 程序內執行、逾時 5 秒、網址不落地）；`windows` 改用 `buildWindowRows`，移除原型的 `meetingBundleIDs`（含 Chrome、Safari）與「標題非空」篩選；`--ask-automation` 才跳授權框；`preflight`／`start` 用 `resolveWindow` 判第 8 項並接受 `--window-bundle`、`--window-title`；preflight 加第 13 項 `apple_events`（warn）；`quick-start` 以 ★ 列算 `starredWindowIDs`、不跳框、code 3 時通知說明 Apple Events；新增 dispatch `diagnose-windows`（spec §3.8.9），app 的 help 列出它
- 驗收時建 app 一律用 `MH_RECORDER_DEST=$(mktemp -d)`，不覆蓋使用者 `~/Applications` 裡的 app（覆蓋會換 cdhash，TCC 授權要在 t6 才重給）
- 畫布：每段開檔前重抓視窗尺寸、必要時 `updateConfiguration`（`design.md §7.1`）
- 音訊：每緩衝讀格式、`audioFormatEvents`、`levels`、裝置 `transport`（`design.md §7.3`、`§7.5`）；不得呼叫 `AudioObjectSetPropertyData`
- menu bar 依 `design.md §8.2`，狀態對映照 spec §3.4.1 表 M1–M10 與 M6a（D17；`preflight_failed` 歸告警態）；判斷邏輯全在 `Core/Trigger.swift`
- **不做量測閘門**（移到 t6，見 `design.md §7.2`）；build 段只要編得過、Swift 測試綠、靜態檢查綠
- **以 t5 的文件為準**（D13）：SKILL.md 寫到的 `--args <子指令>`（至少 `quick-start`）、menu bar 選單項與 quick-start 行為照文件做；不一致時改程式不改文件，真的需要改文件以 `needs_decision` 回報（spec §6 第 29 條）

### t4 CLI 層
- `meeting.sh`：`record)` 插在頂層 `-*)` 與 `*)` 之前，最前面處理 `--recorder` 與 `./record` 撞名（`design.md §8.1`）；`doctor()` 錄製器段＋結尾 `return 0`；`usage()` 加子指令、`--recorder` 與 `MH_RECORD_HOME`／`MH_RECORDER_APP`／`MH_RECORD_OPEN`／`MH_FFMPEG`／`MH_RECORD_EST_MINUTES`
- `_record_prompt.py`：`from _profile import PROFILES`（同目錄 import），不另抄型態清單；介面照 spec §3.7——視窗選單逐字印 `label`、預設＝第一個 ★ 列、沒有 ★ 就沒有預設、`meetingCheck` 為 `not_authorized`／`not_determined` 時多印一行授權說明、輸出 JSON 加 `bundleID`、`title`
- `record.sh`（第六修正輪）：stdin 與 stderr 都是 tty 時呼叫 app `windows` 才加 `--ask-automation`，此時等輸出至少 120 秒；互動開錄把 prompt 輸出的 `bundleID`、`title` 以 `--window-bundle`、`--window-title` 傳給 app 的 `preflight`／`start`（spec §3.5）
- `meeting.sh doctor()` 錄製器段加一行「◦ 會議分頁標記（選用）：要允許 Apple Events……狀態看 meeting record preflight」（必含「會議分頁標記」「Apple Events」「選用」，spec §3.8.4、§4.15.14）
- `_record_estimate.py`：公式照 spec §3.7；`doctor` 與 `record.sh` 都呼叫它
- `_record_finalize.py`：照 `design.md §7.4` 八步（逐段正規化、concat copy、wav 最後一步 `os.replace`）
- `config.json`：`sourceLayout` 加 `videoDir`、`recordTracks`、`recordStatus`
- `record help`（`-h`、`--help`）照 spec §2.4.3 的文法輸出（四個段頭、欄位以兩個以上空白分隔、「旗標：」段不放層旗標、「寫法：」段每行帶 `結束碼 …`）；`usage()` 加 spec §2.4.6 結構的 record 段（段頭行、7 行寫法、`  層旗標：` 行、`  結束碼：` 行）；`meeting.sh` 在交給 `record.sh` 前把 `record` 之後**任何位置**的 `--recorder`、`--yes` 拿掉、其餘參數原序交出；未知選項（spec §2.2 通則／§2.4.2／design §8.1 同一句定義：拿掉層旗標之後仍不屬於該寫法寫法旗標集合的 `--` 開頭參數）一律回 2 並印「未知的選項」；`record status` 除通則外不回 2
- **以 t5 的文件為準**（D13）：`meeting.sh record help`、`usage()` 的 record 段、子指令、旗標、結束碼與 t5 寫成的 SKILL.md／README.md `record-cli` 區塊逐項一致；不一致時改程式不改文件，真的需要改文件（例如發現 spec §2.4 少了一個非加不可的旗標）以 `needs_decision` 回報，不得自行加旗標

### t5 文件（第 1 層，先於程式）
- **只依 spec／design 的定案內容寫**，不得寫 spec 沒有的功能；寫法、旗標、結束碼只能是 spec §2.4.2 的封閉清單，並在 SKILL.md 與 README.md 各放一個內容相同的 `record-cli` 區塊（格式照 spec §2.4.5：7 列、不含層旗標、`status` 的結束碼是 `0 5`）；`--recorder`、`--yes` 寫在區塊外的說明裡；含 `meeting record` 的行不要同時寫 `--args …`（spec §4.12.6 (d) 會把 `--args` 判為表外旗標）
- 結束碼的語意照 spec §2.2；preflight 各項的補救照 `design.md §6` 表；menu bar 選單項字樣照 spec §4.11.6；quick-start 照 `design.md §8`
- SKILL.md 必含：何時用（會議開始前）、`meeting record` 流程、preflight 每項失敗的補救（重啟 app 的步驟；含第 13 項 `apple_events` 是 warn）、`stop`／`status`／`finish`、crash 時最後 1 分鐘會丟、Shortcuts 捷徑建立步驟、`./record` 撞名時的兩種明確寫法（無 tty 呼叫者用 `--recorder`）、`record` 與 `render`／`meeting.record.json` 的區別
- **會議視窗標記（第六修正輪，D16，spec §4.12.10）**：★ 的兩個來源與服務名（M+ Meet、Google Meet、Teams、Zoom、Webex、騰訊會議）、只看作用中分頁、清單每列欄位的意思、Apple Events 是**選用**（第一次在終端機跑 `meeting record` 會跳「允許控制 Google Chrome」，在「自動化」可改）、**不授權也能錄**但 Chrome 視窗不會有 ★、quick-start 因此可能找不到唯一的會議視窗、排錯指令 `open -n -a MeetingRecorder --args diagnose-windows --log <檔>`（獨立一行，不與 `meeting record` 同行）。**不得**再寫「會議視窗不要用 native 全螢幕」（第六修正輪 skeptic 問題 1：Chrome 會議頁 native 全螢幕已實測可錄）；README 錄製段加一行指向 SKILL.md 的「會議視窗標記」
- README 的 for-loop 補 `meeting-record`；不要建立 `~/.claude/skills/` 下的 symlink（見 §4）

### t6 人工驗收（test 段）
順序：
1. 使用者對新簽章的 `MeetingRecorder.app` 重新授權（螢幕錄製、麥克風、文件資料夾），完全結束後重開；接著跑一次 `meeting record preflight`，第 4 項（麥克風權限）與第 6 項（麥克風 RMS）都要 pass——這是 hardened runtime＋entitlement 的實機驗證（spec §4.2.8）；不過就停下以 `needs_decision` 回報；
2. **量測閘門**：§4.4.3 空隙、§4.3.4 縮放、§4.4.4 靜止跨段（記錄）——§4.4.3 或 §4.3.4 不過就停下以 `needs_decision` 回報；
3. preflight 13 項各失敗一次（§4.2.6；第 13 項＝在「自動化」不允許 MeetingRecorder 控制 Chrome，應為 warn、照常開錄）；
4. 3 分鐘端到端（Teams 自我通話）＋Space 切走＋最小化＋Teams native 全螢幕／Mission Control 觀察（§4.10）；
4a. **視窗清單與會議標記（D15、D16，§4.15.16–4.15.18）**：(i) 以 `tccutil reset AppleEvents com.meetingharness.recorder` 清掉紀錄後在終端機跑 `meeting record windows`，驗第一次授權框、按允許；(ii) 使用者開 M+ Meet 會議頁並按綠色按鈕進全螢幕，`meeting record windows` 與互動選單第一列是該視窗、label 以「★ 會議（M+ Meet）」開頭且含「全螢幕尺寸」、是預設選項；選它開錄、切到別的 Space ≥ 30 秒，`e2e_check.py --space-interval` PASS；(iii) 開著 LINE 通話時，LINE 通話視窗出現在清單（`untitled == true`、「（無標題）」）；(iv) 在「自動化」關掉授權，清單照常、Chrome 列沒有 ★、最後一行有 Apple Events 說明，錄 1 分鐘 Chrome 會議視窗並 stop，`e2e_check.py <場次>` 回 0；(v) 跑一次 `open -n -a MeetingRecorder --args diagnose-windows --log <檔>`，輸出含被濾掉的 Chrome 工具列（`excludedBy` 含 `size`）；
5. fps 尖峰（§4.3.3）；
6. 藍牙三項（§4.9.1–4.9.3，必驗）與 §4.9.4；
7. `kill -9` 救援與冪等（§4.8.1）；錄製中並發（§4.7.1）；磁碟不足（§4.5.5）；
8. quick-start、menu bar、快捷鍵（§4.11.1–4.11.3、§4.11.7），並截 menu bar 三態（淺色／深色）與三態選單共 9 張給設計審查；
9. 迴歸（§4.13.4、§4.13.5）。

錄檔放 `~/.meeting-harness/e2e/` 或使用者指定的客戶目錄，不進 repo、不進 run 目錄；截圖只截 menu bar 區域，放 run 目錄。

---

## 3. 測試對應

| spec 節 | 自動測試 | 寫測試 | 讓它轉綠 | 人工 |
|---|---|---|---|---|
| 4.1.1–4.1.3、4.1.10 | `test_cli_dispatch.py`（4.1.2＝`::test_help_lists_record_forms`） | t1 | t4 | — |
| 2.4.3–2.4.7（解析器本身） | `test_surface_parsers.py` | t1 | t1（紅燈階段即綠） | — |
| 4.1.4、4.1.6、4.1.7 | `test_record_sh.py` | t1 | t4 | — |
| 4.1.5 | `test_static_rules.py::test_no_direct_exec_of_recorder` | t1 | t4 | — |
| 4.1.8 | `test_prompt.py` | t1 | t4 | — |
| 4.1.9 | `test_estimate.py` | t1 | t4 | — |
| 4.1.11、4.1.12 | `test_cli_dispatch.py::test_record_help_prints_surface`、`::test_record_unknown_flag_exits_2`、`::test_meeting_sh_layer_flags_stripped`、`::test_layer_flag_mid_position_stripped`、`::test_layer_flag_trailing_position_stripped` | t1 | t4 | — |
| 4.2.1、4.2.2 | `PreflightTests.swift`（4.2.1＝`::testPreflightItemsAndSeverity`，13 項） | t2 | t3 | — |
| 4.2.3、4.2.4 | `test_record_sh.py` | t1 | t4 | t6 |
| 4.2.5、4.2.7 | `AudioLevelTests.swift`；4.2.5 另有 `PreflightTests.swift::testSystemAudioCheckTwoStage`、`test_static_rules.py::test_preflight_system_audio_two_stage`（D19 新增） | t2、t1 | t3 | t6 |
| 4.2.9（D19） | `PreflightTests.swift::testSystemAudioCheckTwoStage`、`::testSystemAudioWarnOnlyResult` | t2 | t3 | — |
| 4.2.10 | `test_static_rules.py::test_windowserver_connection_initialized_on_main_thread`（`b16a375`，已綠於 `413eb50`） | t1 | t3 | t6 |
| 4.2.6 | — | — | t3＋t4 | t6 |
| 4.2.8 | `test_static_rules.py::test_entitlements_audio_and_apple_events`、`::test_info_plist_apple_events_usage`、`::test_build_signs_with_entitlements`；t3 完成條件的 `codesign` 檢查（兩項 entitlement） | t1 | t3 | t6（第一步、§4.15.18） |
| 4.3.1、4.3.3 | `e2e_check.py`（判準自測 `test_e2e_check.py`） | t1 | t3、t4 | t6 |
| 4.3.2 | `SegmentsTests.swift::testEvenPixelSize`；`e2e_check.py` | t2、t1 | t3、t4 | t6 |
| 4.3.4 | `e2e_check.py` | t1 | t3、t4 | t6（閘門） |
| 4.3.5（D19） | `test_docs.py::test_audio_scope_documented` | t1 | t5（本次 docs commit 已寫） | t6 |
| 4.4.1 | `SegmentsTests.swift::testSegmentFileName` | t2 | t3 | t6 |
| 4.4.2 | `test_concurrency.py::test_recording_session_not_listed` | t1 | t4 | t6 |
| 4.4.3 | `SegmentsTests.swift::testBoundaryGaps`；`e2e_check.py` | t2、t1 | t3、t4 | t6（閘門） |
| 4.4.4 | `e2e_check.py` | t1 | t3、t4 | t6（閘門，記錄） |
| 4.5.1–4.5.3 | `DetectorsTests.swift` | t2 | t3 | t6 |
| 4.5.4 | `RecordsTests.swift::testMetaJSONKeys` | t2 | t3 | t6 |
| 4.5.5、4.5.6 | `test_record_sh.py` | t1 | t4（＋t3 寫 code 5） | t6 |
| 4.5.7、4.5.8 | `AudioLevelTests.swift`、`DetectorsTests.swift` | t2 | t3 | t6 |
| 4.6.1–4.6.12 | `test_finalize.py` | t1 | t4 | t6 |
| 4.7.1、4.7.2 | `test_concurrency.py` | t1 | t4 | t6 |
| 4.8.1、4.8.2 | `test_finalize.py`；`e2e_check.py` | t1 | t4 | t6 |
| 4.8.3 | `test_docs.py::test_crash_loss_documented` | t1 | t5 | — |
| 4.9.1–4.9.3 | `e2e_check.py`（判準自測 `test_e2e_check.py`） | t1 | t3、t4 | t6（必驗） |
| 4.9.4 | `test_static_rules.py::test_no_default_device_write_in_sources`；`::test_no_default_device_write_in_record_sh` | t1 | t3（`_in_sources`）；t4（`_in_record_sh`） | t6 |
| 4.10.1–4.10.4 | `e2e_check.py` | t1 | t3、t4 | t6 |
| 4.11.1、4.11.2 | `TriggerTests.swift`（`testMenuBarStateMapping` 涵蓋 spec §3.4.1 M1–M10 與 M6a，M2 含 code 2／3／4） | t2 | t3 | t6 |
| 4.11.3 | `test_static_rules.py::test_no_global_event_monitor`、`::test_hotkey_uses_carbon` | t1 | t3 | t6 |
| 4.11.4 | `test_docs.py::test_shortcuts_instruction` | t1 | t5 | — |
| 4.11.5、4.11.8 | `TriggerTests.swift`；`test_static_rules.py::test_menubar_uses_template_image`、`::test_menubar_sets_accessibility_label` | t2、t1 | t3 | 設計審查 |
| 4.11.6、4.11.7 | `TriggerTests.swift` | t2 | t3 | t6；設計審查 |
| 4.12.1–4.12.3 | `test_docs.py::test_skill_exists_and_sections`、`::test_meeting_summary_frontmatter_unchanged`、`::test_readme_updated` | t1 | t5 | — |
| 4.12.4 | `test_regression.py::test_diarize_and_merge_untouched` | t1 | （保持不動） | — |
| 4.12.5 | — | — | 主 session（deliver 後） | 主 session |
| 4.12.6 | `test_docs.py::test_docs_cli_block_matches_spec` | t1 | t5 | — |
| 4.12.7 | `test_docs.py::test_docs_cli_block_matches_help` | t1 | t4（照 t5 的文件） | — |
| 4.12.8 | `test_docs.py::test_docs_flags_match_behavior`、`::test_docs_exit_codes_match_behavior` | t1 | t4（照 t5 的文件） | — |
| 4.12.9 | `test_docs.py::test_docs_app_args_exist_in_sources` | t1 | t3（照 t5 的文件） | — |
| 4.13.1、4.13.2、4.13.7 | `test_regression.py` | t1 | t4（4.13.7 已由 `3f47b65` 滿足，紅燈階段即綠） | — |
| 4.13.3 | `test_finalize.py::test_status_lists_finalized_session` | t1 | t4 | t6 |
| 4.13.4、4.13.5 | — | — | — | t6 |
| 4.13.6 | `check_rules.py --git` | — | 全部 | integrator |
| 4.14.1 | `test_static_rules.py::test_no_media_in_repo` | t1 | 全部 | — |
| 4.14.2 | `test_static_rules.py::test_gitignore_media_rules` | t1 | t5 | — |
| 4.14.3 | `test_static_rules.py::test_no_client_names_in_repo_text`（帶 `MH_CLIENT_NAMES_FILE`） | t1 | t1、t2（紅燈階段即綠；之後每層都要維持綠） | 主 session（推送前必辦，§5） |
| 4.12.10、4.15.15 | `test_docs.py::test_meeting_tab_marking_documented` | t1 | t5 | — |
| 4.15.1–4.15.9 | `WindowListTests.swift`（12 支，見 §2 t2） | t2 | t3 | t6（4.15.9 的 `diagnose-windows` 實跑一次） |
| 4.15.10、4.15.11 | `test_static_rules.py::test_chrome_query_read_only`、`::test_info_plist_apple_events_usage` | t1 | t3 | — |
| 4.15.12 | `test_prompt.py::test_prompt_window_menu_labels_and_default`、`::test_prompt_no_default_without_meeting`、`::test_prompt_outputs_window_identity` | t1 | t4 | t6 |
| 4.15.13 | `test_record_sh.py::test_windows_ask_automation_only_with_tty`、`::test_start_passes_window_identity` | t1 | t4 | t6 |
| 4.15.14 | `test_regression.py::test_doctor_mentions_meeting_tab_marking` | t1 | t4 | — |
| 4.15.16–4.15.18 | `e2e_check.py --space-interval`、`e2e_check.py <場次>` | t1 | t3、t4 | t6（必驗） |

**歸屬 t3 的測試函式**（t4 的完成條件排除它們；每支只掃 t3 擁有的路徑或 t3＋已合併的 t5 文件）：`test_static_rules.py` 的 `test_no_global_event_monitor`、`test_hotkey_uses_carbon`、`test_no_default_device_write_in_sources`、`test_menubar_uses_template_image`、`test_menubar_sets_accessibility_label`、`test_entitlements_audio_and_apple_events`、`test_build_signs_with_entitlements`、`test_info_plist_apple_events_usage`、`test_chrome_query_read_only`；`test_docs.py` 的 `test_docs_app_args_exist_in_sources`。**歸屬 t4**：`test_no_default_device_write_in_record_sh`、`test_no_direct_exec_of_recorder`（只掃 `bin/record.sh`）；`test_docs.py` 的 `test_docs_cli_block_matches_help`、`test_docs_flags_match_behavior`、`test_docs_exit_codes_match_behavior`；第六修正輪的 `test_prompt_window_menu_labels_and_default`、`test_prompt_no_default_without_meeting`、`test_prompt_outputs_window_identity`、`test_windows_ask_automation_only_with_tty`、`test_start_passes_window_identity`、`test_doctor_mentions_meeting_tab_marking`。**歸屬 t5**：`test_gitignore_media_rules`；`test_docs.py` 的 `test_skill_exists_and_sections`、`test_meeting_summary_frontmatter_unchanged`、`test_readme_updated`、`test_crash_loss_documented`、`test_shortcuts_instruction`、`test_docs_cli_block_matches_spec`、`test_meeting_tab_marking_documented`。`unittest -k` 是子字串比對；上列函式名沒有一支是另一支的子字串，所以 t3 用 `-k test_no_default_device_write_in_sources` 不會選到 t4 那支。

測試指令：
- `python3 -m unittest discover -s tests/record -t .`
- `bash tools/MeetingRecorder/Tests/run.sh`
- 兩者都要在 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8` 下跑（`rules.md:60`），並帶 `MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`（spec §4.14.3）；`run.sh` 一律用 `/bin/bash` 執行
- **每層整合後的測試指令**（`rules.md:59` 所說「plan §3 列的測試指令」即本表；integrator 每合併完一層，在 `feature/meeting-record` 依該層這一列**全部**跑過、全部回 0 才能清 worktree、進下一層；一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8`，第七修正輪起再加 `MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`，否則 §4.14.3 會被 skip 成假綠）。分層列出的理由：Red 與第 1 層合併時 t3／t4 尚未實作，兩支全量指令依設計必然是紅的，若照字面要求全綠，build 會在第 1 層停下；所以前兩層只列「此時應該已綠」的子集，最後一層才是兩支全量指令（這是同層子任務彼此看不到對方檔案時的補位，第二輪 skeptic 問題 4；D13 一致性檢查也在這一步由全量測試跑到，第三輪 skeptic 問題 2）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red（t1＋t2） | `python3 -m unittest tests.record.test_e2e_check tests.record.test_surface_parsers`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（輸出不得含 `skipped`）；`python3 -m unittest discover -s tests/record -t . -k test_git_governance_content -k test_diarize_and_merge_untouched` | 兩支全量指令（紅燈原因須為功能不存在，不是 ImportError、語法錯誤或 `unbound variable`） |
| 第 1 層（t5） | Red 那一列；加 `python3 -m unittest discover -s tests/record -t . -k test_skill_exists_and_sections -k test_meeting_summary_frontmatter_unchanged -k test_readme_updated -k test_crash_loss_documented -k test_shortcuts_instruction -k test_docs_cli_block_matches_spec -k test_gitignore_media_rules -k test_meeting_tab_marking_documented` | 兩支全量指令（剩下的都屬 t3／t4） |
| 第 2 層（t3＋t4，最後一層） | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`（兩支全量，含 `test_docs.py` 全部 11 支函式與 `WindowListTests.swift`） | 無；任何一支不綠就停下交人 |

---

## 4. 不屬於任何子任務、需要主 session 或使用者做的事

| 事項 | 時點 | 理由 |
|---|---|---|
| 建立 `_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`（每行一個真實客戶名稱、會議名稱或視窗標題；run 目錄不進版控） | 閘門 2 核准後、啟動 build 前 | spec §4.14.3 的清單；不得放進 repo，也不得由子任務建立（子任務 owns 不含 run 目錄）；清單內容不寫進任何派工單、信封或 commit 訊息 |
| 推送前客戶名稱掃描與歷史處理（§5「推送前必辦」） | 任何推送之前 | 改寫歷史與推送都是不可逆節點，需使用者當下核准 |
| 維護 `progress.md` | 每層合併後、每個閘門後 | 進度紀錄不是交付物，統一由主 session 改，避免平行衝突；build workflow 已在 `7c9a3a0` 改成不讓 implementer 改它（`.claude/workflows/sdlc-build.js:91`） |
| 鑰匙圈 `MeetingHarness Dev` 設成信任（選用） | test 段前 | 簽章不需要信任；只有使用者想讓 `-v` 也列出它時才做，需 GUI 操作 |
| 對 `MeetingRecorder.app` 重新授權螢幕錄製、麥克風、文件資料夾 | t6 第一步 | 簽章身分從 ad-hoc 換成固定身分後，TCC 紀錄可能失效；只能由使用者在系統設定操作。量測閘門因此排在它之後 |
| test 段平行派 `dev-design-reviewer`（`has_ui=true`） | t6 截圖完成後 | D12；依據 spec §4.11.5–4.11.8 |
| 建 `~/.claude/skills/meeting-record` symlink | deliver 閘門核准後 | 改全域 skill（`rules.md:68`） |
| 推送、開 PR | 使用者當下同意後 | 不可逆節點（`CLAUDE.md:15`） |

---

## 5. 拆 PR 規劃（修改既有檔超過 15 個）

整個 epic 對 `main` **修改既有檔**的數量：已在分支上的 9 個（`git diff --diff-filter=M --name-only main...HEAD`：`guard.config.json`、`rules.md`、4 支 `sdlc-*.js`、`.gitignore`、`CLAUDE.md`、`workflow.config`；`544df94` 改的 `rules.md` 已在其中）＋ build 段預計 7 個（`bin/meeting.sh`、`config.json`、`tools/MeetingRecorder/Sources/main.swift`、`build.sh`、`Resources/Info.plist`、`.claude/skills/meeting-summary/SKILL.md`、`README.md`；`.gitignore` 重複不另計；`probe.sh` 視 t3 需要再 +1）＝ **16–17 個**，超過 `rules.md:57` 的 15 檔門檻。D13 之後檔案集合沒有變，變的是 build 的先後；第六修正輪（D15、D16）也沒有增加修改既有檔——`Info.plist`、`main.swift`、`meeting.sh` 原本就在清單內，新增的 `Core/WindowList.swift`、`Capture/ChromeTabs.swift`、`Tests/WindowListTests.swift`、`adr/adr-meeting-window-marking.md` 都是新檔，不計入；仍分三包，**合併順序 1 → 2 → 3**：

| 包 | 內容 | 範圍 | 修改既有檔 |
|---|---|---|---|
| 1 | GIT 管控修正＋ specs（intent、design、spec、plan、progress、ADR）＋ workflow／rules 調整 | `main..`第五修正輪的 commit（`89cbd28`、`ca211b0`、`3f47b65`、`8d25eec`、`cb2eb55`、`7c9a3a0`、`61c3461`、`544df94`、`b1fbadf`、`22617a0`、`bcec2a2`、第六修正輪 `0d680c4`、第七修正輪） | 9 |
| 2 | 錄製器本體（t2、t3） | Red 層 t2 的 commit ＋ 第 2 層 t3 的 commit | `main.swift`、`build.sh`、`Info.plist`（＋`probe.sh`）≤ 4；`MeetingRecorder.entitlements` 是新增檔，不計入 |
| 3 | CLI 層、測試、文件（t1、t5、t4） | Red 層 t1、第 1 層 t5、第 2 層 t4 的 commit | `meeting.sh`、`config.json`、`meeting-summary/SKILL.md`、`README.md`、`.gitignore` = 5 |

**理由（第三輪 skeptic 問題 3：前一版「第 3 包的 t5 寫的是第 2 包的 help 文字，所以第 2 包先合」在依賴反轉後不成立，以下重算）**：
- **t5 與 t4、t1 必須同一包**：D13 的一致性檢查（spec §4.12.7、§4.12.8）同時讀 t5 的文件、t4 的 `meeting.sh`／`record.sh` 與 t1 的 `test_docs.py`。拆到不同包，先合的那包在審查時一定有紅燈或缺檔，也就失去「文件與實作逐項一致」的審查證據。
- **t5 不單獨先合**：build 裡 t5 最先寫，但若把它單獨做成一包先合進 `main`，`main` 的 README 與 skill 會描述一個還不存在的 `meeting record`；其他 session 經 skill 讀到會照著呼叫而失敗（`CLAUDE.md`〈對外介面〉）。build 順序（契約先行）與合併順序（文件與程式一起上線）是兩件事。
- **第 2 包仍先於第 3 包**：理由從「help 文字」改為**執行期相依**——第 3 包的 `record.sh` 以 `open -n -a MeetingRecorder` 啟動第 2 包的 app，`doctor` 檢查 app；`test_docs_app_args_exist_in_sources`（§4.12.9）讀第 2 包的 `Sources/main.swift`；SKILL.md 描述的 quick-start、menu bar 也是第 2 包的行為。第 2 包單獨合進 `main` 時沒有任何對外入口（`meeting.sh` 還沒有 `record)`），不會讓既有使用者看到半套功能。
- **代價**：第 2 包審查時看不到 t1 對 `Sources/` 的靜態檢查（它們在第 3 包）；第 3 包合併前會在整合分支全量跑，屆時一併驗。若要減少一次 PR，可把第 2、3 包合成一包（修改既有檔 ≤ 9，仍低於門檻），代價是 Swift 與 shell 兩種審查混在同一個 PR；本 plan 預設分開。

- 第 2、3 包各自開分支 `feature/meeting-record-app`、`feature/meeting-record-cli`（允許的前綴），由 integrator 從 `feature/meeting-record` 依**檔案範圍**揀出各子任務的非合併 commit（`git cherry-pick`）：第 2 包從 `main`（已含第 1 包）開出，揀 t2、t3；第 3 包從第 2 包開出，揀 t1、t5、t4。t3 的 commit 雖然是在已有 t5 文件的基底上做的，但只改 `tools/MeetingRecorder/`，與 t5 的檔不重疊，揀到沒有 t5 的第 2 包不會衝突。
- 若 t3 對 `main.swift` 的修改（多半是搬移到 `Core/`）超過 300 行，第 2 包在 PR 說明標 important（`rules.md:57`），不再細拆——同一檔拆兩包反而無法單獨審。
- 推送與開 PR 都是不可逆節點，由使用者當下同意後主 session 執行；本規劃不構成同意。

### 5.1 推送前必辦：客戶名稱掃描（第七修正輪，使用者在閘門 2 的決定 3）

第六修正輪的 `0d680c4` 把真實會議名稱寫進了 specs；本輪只讓 HEAD 乾淨，歷史仍有。repo 為 public（`origin`＝`s96cax98leo/meeting-harness`），所以**任何一包推送前**，主 session 都要依序做：

1. **掃描範圍**：`git log -p origin/main..main`（`main` 上尚未推送的 commit，含第 0 階段的 `9a76c83`）、`git log -p main..feature/meeting-record`，以及拆包後的 `feature/meeting-record-app`、`feature/meeting-record-cli`；另以 `git grep` 掃每個要推送分支的 HEAD 樹（不只 specs）。比對清單一律用 run 目錄的 `client-names.txt`（`grep -F -f <清單>`），**只報命中的 commit 與檔名、不印命中字串**（與機敏值比對同一做法，`CLAUDE.md`〈機敏檔〉）。
2. **第七修正輪 spec-author 的預掃結果**（只記 commit 與檔，不記字串）：`main..feature/meeting-record` 命中 `0d680c4`；`origin/main..main` 命中 `46e58c5`、`30a7adf`；`main` 的 HEAD 樹命中 `README.md`。`9a76c83` 以本輪已知名稱掃描為 0 筆，但清單建立後仍要重掃。
3. **命中就先停**：以選項式提問交使用者決定，選項至少含 (a) 改寫歷史（`git rebase -i` 改訊息與內容或 `git filter-repo --replace-text`）、(b) 從乾淨的 HEAD 重做一個 squash commit 取代該段歷史、(c) 不推送該段。**動手前先留備份分支**（例 `backup/meeting-record-pre-scrub-<日期>`，只留本機、不推送），經使用者當下核准才改寫；改寫後重跑步驟 1 直到 0 筆，再請使用者核准推送。`main` 上的命中（含 `README.md` 的 HEAD 內容）同樣在範圍內，但修改 `main` 的 `README.md` 不屬於本 epic 的子任務，由使用者決定是否另開工作處理。
4. 本節不授權任何改寫或推送；agent 不得自行執行步驟 3 的任何一個選項。

---

## 6. t6 中途修正輪（D20，2026-10-11）

**起因**：t6 量測閘門 §4.4.3 不過——`SCRecordingOutput` 不能在執行中的 stream 上輪替（每次約 10.5 秒空隙、各段未收尾）；同時發現 finalize 串接實機段落失敗（`non monotonically increasing dts`）與一次 `startCapture`「無法開始音訊串流」。使用者決定 D20「自己管 AVAssetWriter（建議）」，並要求 spec／design 修訂後**重新核准**才實作（`gate1-decisions.md` D20）。依據：`adr/adr-segment-writer.md`、`design.md §7.2`、`§7.4`、`§7.5`、`§7.6`；驗收：spec §3.2（段落欄位新定義）、§3.4（新增 `SampleRoute`、`routeSample`、`segmentVideoBitRate`、`WarningKind.segmentWriteFailed`）、§4.2.11、§4.4.1、§4.4.3–4.4.8、§4.6.9、§4.6.13–4.6.16、§4.8.4、§4.9.3（D20 句）、§6 第 47–53 條。

**本輪一併實作 D19**：`c5022d4` 的 spec（§4.2.5、§4.2.9、§4.3.5）與 `09e6f05` 的紅燈測試（`PreflightTests.swift::testSystemAudioCheckTwoStage`、`::testSystemAudioWarnOnlyResult`、`test_static_rules.py::test_preflight_system_audio_two_stage`）尚未實作，歸 m3；`test_docs.py::test_audio_scope_documented` 已綠。

**子任務**（m1–m4 只是本節的短代號，**不是任務編號**；分支 `feature/meeting-record--m1` …，各開 worktree，從本輪 docs commit 之後的 `feature/meeting-record` 開出）：

| id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec |
|---|---|---|---|---|---|
| m1 | test | Python 側紅燈測試＋`e2e_check.py` 新判準 | `tests/record/` | — | §4.2.11（靜態）、§4.4.1、§4.4.3–4.4.5（靜態與 e2e）、§4.4.8、§4.6.9、§4.6.13–4.6.15、§4.8.4（`--expect-min` 已有）、§4.9.3（`format_rotation`）、§6 第 53 條 |
| m2 | test | Swift 紅燈測試 | `tools/MeetingRecorder/Tests/` | — | §3.4（D20 新增名稱）、§4.4.6 |
| m3 | code | 錄製器：自管 `AVAssetWriter` 換段、停止收尾、writer 失敗、格式變更提前換段、`startCapture` 等待與重試、D19 第 5 項兩段式 | `tools/MeetingRecorder/Sources/`、`tools/MeetingRecorder/build.sh`、`tools/MeetingRecorder/Resources/` | m1、m2 | §3.2（錄製器寫的欄位）、§3.4、§4.2.5、§4.2.9、§4.2.11、§4.3.5、§4.4.1、§4.4.3–4.4.8、§4.9.3（D20 句） |
| m4 | code | finalize：兩軌混音、時間戳正規化、fragment 段落、`audioDuration` 由封包算 | `bin/_record_finalize.py` | m1 | §3.2（finalize 寫的欄位）、§4.6.1–4.6.16 |
| t6 | check | t6 接續（人工，與使用者一起做） | （無檔案；結果寫 run 目錄） | m3、m4 | 見下〈t6 接續順序〉 |

**分層**：Red：m1＋m2（平行）→ 第 2 層：m3＋m4（平行）→ t6 接續。文件（SKILL.md 的段落雙音軌說明）已在本輪 docs commit 寫好，不另設子任務。

**拆分理由**（數量最小化）：
- m1／m2 分開：兩種語言、兩套執行器，檔案不重疊；平行。
- m3 不再拆（例如把 D19 的 `PreflightRunner.swift` 與寫檔分給兩人）：`Tests/run.sh` 把 `Core/*.swift` 與全部 `*Tests.swift` 編成**一支**執行檔，同層兩個 Swift 子任務在各自 worktree 都看不到對方新增的 Core 名稱，`run.sh` 會編譯失敗，誰都無法以「`run.sh` 全綠」完成；而且 §7.6 的等待與重試落在 preflight 與正式錄製的交界（`Capture/Commands.swift:126` 的 `runPreflightThenRecord`），兩邊都會碰。
- m3／m4 分開：Swift 與 Python 只經 §3.2 的 `manifest.json` 與段落檔格式（§4.4.1：影片、系統聲音、麥克風三軌）相接，契約已釘住；平行。
- m4 只相依 m1：finalize 的測試全是 Python 合成素材，不需要 Swift 端。

### m1 要點（tests/record/）
- `test_static_rules.py`：`test_segment_writer_uses_assetwriter`（spec §4.4.5 的字串清單；只掃 `Sources/Capture/`，`Probe.swift` 例外）、`test_start_capture_settle_and_retry`（§4.2.11：常數名稱、數值 1.0／2.0、定義以外各至少引用一次）。兩支歸 m3 轉綠。
- `test_finalize.py`：`test_two_audio_tracks_mixed`（§4.6.13）、`test_irregular_timestamps_concat`（§4.6.14，配方 (A) 與 (B)）、`test_truncated_fragment_segment_used`（§4.6.15）。合成素材的產生函式放 `tests/record/_media.py`（或 `_fixtures.py`），一律 `TMPDIR` 下現場產生，不提交媒體檔。三支歸 m4 轉綠。
- `e2e_check.py`：新增旗標 `--segment-writer`，啟用 `segment_tracks`（§4.4.1）、`segment_finished`／`segment_cadence`（§4.4.3 (b)(c)）、`segment_video_start`（§4.4.4）、`stop_tail`（§4.4.8）；與 `--hfp` 同時給時加 `format_rotation`（§4.9.3）。`gap` 改取各音軌最長並判 `|g_i|`（§4.4.3 (a)），單一音軌時結果須與前一版相同。**不改預設判準**（spec §6 第 53 條）。
- `test_e2e_check.py`：新增 `test_segment_tracks_check`、`test_segment_finished_check`（含 cadence 與 stop_tail）、`test_segment_video_start_check`、`test_format_rotation_check`，各用一組會 PASS、一組會 FAIL 的合成場次；既有 12 支的預期不得改。
- **完成條件**：(1) 上列新測試在 m1 分支上都失敗，且失敗原因是「功能不存在」（finalize 回 5 或判準不成立、靜態檢查缺字串），不是 ImportError、語法錯誤；`test_irregular_timestamps_concat` 的 (A) 必須在現行 finalize 上回 5（spec §4.6.14 已驗證配方）；(2) `e2e_check.py` 的新判準與 `test_e2e_check.py` 全部綠（工具與自我測試都在 m1）；(3) 全量 `python3 -m unittest discover -s tests/record -t .` 的失敗集合**恰為** {本輪 5 支新紅燈（靜態 2、finalize 3）、`test_preflight_system_audio_two_stage`}；(4) `-k test_no_client_names_in_repo_text` 綠且不得 `skipped`。

### m2 要點（tools/MeetingRecorder/Tests/）
- `SegmentsTests.swift`：`testRouteSample`、`testSegmentVideoBitRate`（spec §4.4.6 的全部案例）；`RecordsTests.swift`：`testSegmentWriteFailedWarningKind`（raw value、`isAlert`、`RecordWarning` JSON 往返，並重驗既有七個 kind 不變）。新增的測試函式要登記進該檔開頭的測試清單（照既有慣例，例 `PreflightTests.swift:9`）。
- **完成條件**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 失敗，且失敗原因只有「缺少 D19／D20 的 Core 名稱」（`systemAudioCheck`、`SystemAudioCheck`、`warnOnly`、`SampleRoute`、`routeSample`、`segmentVideoBitRate`、`segmentWriteFailed` 的編譯錯誤），沒有其他編譯錯誤。

### m3 要點（錄製器）
- `Core/Segments.swift` 加 `SampleRoute`、`routeSample`、`segmentVideoBitRate`；`Core/Records.swift` 的 `WarningKind` 加 `segmentWriteFailed`（`isAlert` true）；`Core/Preflight.swift` 加 D19 的 `SystemAudioCheck`、`systemAudioCheck`、`PreflightResult.warnOnly`（spec §3.4，名稱照抄、不得改名）。
- 新增 `Capture/SegmentWriter.swift`：一段一個 `AVAssetWriter`（三個 input、固定順序、`design.md §7.2` 的輸出設定、`movieFragmentInterval` 10 秒、`overallDurationHint` 60 秒）、`append`（未 ready 就丟並計數、視訊 PTS 必須嚴格遞增）、`finish(at:)`（`endSession`＋`markAsFinished`＋`finishWriting`，完成回呼回報 completed／failed）。
- `Capture/RecordingSession.swift`：拿掉 `SCRecordingOutput`、`SCRecordingOutputDelegate` 與 10 秒等回呼的邏輯；第一段在第一個 sample 到時開；以 sample 時鐘每 60 秒換段（`routeSample` 分流、新段首幀重新打戳、舊 writer 非同步收尾）；邊界前 1 秒查視窗尺寸；格式變更提前換段（同一路 1 秒內不重複）；writer 失敗處理；停止順序照 `design.md §7.4`（停止點 `E` → `stopCapture` → 排空佇列 → 收尾目前與所有舊 writer → finalize）；`manifest.json` 的欄位照 spec §3.2 新定義；第一個 sample 時把 PTS 與 host clock 的偏移寫進 `record.log`。
- `Capture/PreflightRunner.swift`：D19 第 5 項兩段式（spec §4.2.5；`09e6f05` 的靜態檢查要求的字串照它）。
- `Capture/Commands.swift`（`runPreflightThenRecord`）與 `RecordingSession.start()`：§7.6 的 `startCaptureSettleSeconds = 1.0`、`startCaptureRetryDelaySeconds = 2.0`，重試時重建 `SCStream`。
- `Probe.swift` 不動（`probe` 子指令保留 `SCRecordingOutput`）。不得呼叫 `AudioObjectSetPropertyData`（§4.9.4）。
- **完成條件**：(1) `/bin/bash tools/MeetingRecorder/Tests/run.sh` 全綠；(2) `python3 -m unittest discover -s tests/record -t . -k test_segment_writer_uses_assetwriter -k test_start_capture_settle_and_retry -k test_preflight_system_audio_two_stage` 全綠，§3「歸屬 t3 的測試函式」清單也全綠；(3) 以 `MH_RECORDER_DEST=$(mktemp -d)` 建 app 成功，`codesign -dvv` 的 flags 含 `runtime`、`codesign -d --entitlements -` 含兩項 entitlement；**不得覆蓋** `~/Applications/MeetingRecorder.app`（重新安裝在 t6 接續第 1 步、經使用者同意）；(4) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。實機量測不在 m3（在 t6）。

### m4 要點（finalize）
- 照 `design.md §7.4`：第 1 步各軌長度一律由封包算、只略過完全讀不到可解碼封包的段；第 3 步同一原點平移、影片 `-fps_mode passthrough -enc_time_base demux`、重複 PTS 只留一個、`-avoid_negative_ts make_zero`、正規化後判準不成立即 `FinalizeError`；兩條音軌等權混音＋限幅、單軌直接用、無音軌補靜音；第 4 步完整解碼檢查加 `-enc_time_base demux` 並以 `ffprobe` 驗 dts 嚴格遞增；`audioDuration` 寫回取各音軌最長。
- 根因與已驗證的修法見 `design.md §7.4` 第 3 步（兩處 `-enc_time_base demux`）；其餘（原點平移、混音、fragment）是本輪新增的設計，照 spec 驗收做。
- **完成條件**：(1) `python3 -m unittest discover -s tests/record -t . -k test_finalize -k test_concurrency` 全綠（含既有 §4.6.1–4.6.12 的測試，預期不得改）；(2) 全量 Python 測試中，除 m3 歸屬的 3 支（`test_segment_writer_uses_assetwriter`、`test_start_capture_settle_and_retry`、`test_preflight_system_audio_two_stage`）外全綠；(3) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0；(4) 不得在 repo 內產生媒體檔（§4.14.1）。

### 每層整合後的測試指令（本輪；integrator 照此跑，一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red（m1＋m2） | `python3 -m unittest tests.record.test_e2e_check tests.record.test_surface_parsers`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 全量 Python 指令（失敗集合恰為 m1 完成條件 (3) 的 6 支）；`run.sh`（只因缺 D19／D20 Core 名稱而編譯失敗） |
| 第 2 層（m3＋m4） | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 無；任何一支不綠就停下交人 |

### t6 接續順序（m3、m4 合併後；需使用者在場）
1. **重新安裝**：以 `build.sh` 覆蓋 `~/Applications/MeetingRecorder.app`（**要使用者當下同意**）；固定身分簽章，TCC 授權預期沿用，跑一次 `meeting record preflight` 確認；不過就請使用者重新授權。
2. **實機段落回歸**（§4.6.16）：對 t6 保留、先前 finalize 失敗的 4 段場次跑 `meeting record finish`。
3. **量測閘門重跑**：§4.4.3（3 分鐘，`e2e_check.py <場次> --segment-writer`）、§4.4.4（靜止視窗 70 秒以上）、§4.3.4（錄製中縮放）；另記錄 `record.log` 的丟幀數與時鐘偏移（spec §7 疑慮 21）。不過就停下以 `needs_decision` 回報。
4. **§4.2.11**（輸入輸出都用藍牙耳機連開 5 次）；**§4.2.6 第 5 項三步**（D19）。
5. **§4.4.7**（`chmod a-w tracks/` 注入 writer 失敗）；**§4.8.4**（錄 90 秒以上 `kill -9`）與 §4.8.1、§4.8.2。
6. **寫檔機制改變後要重跑的既有項目**：§4.3.1–4.3.3、§4.9.2（全程藍牙 ≥ 3 分鐘；第一次 18.6 秒未達時長、第二次閘門不過）、§4.9.3（HFP，加 `--segment-writer` 查提前換段）、§4.9.1、§4.10.1–4.10.4（含使用者聽寫兩邊聲音的時間點，§4.10.4）。
7. 原 t6 順序（§2 t6）中尚未做的其餘項目照原順序接續；完成與否以主 session 維護的 `progress.md` 為準。

## 7. t6 第二次中途修正輪（D21、D22，2026-10-12）

**起因**：t6 接續（D20 修正輪 `ec71657` 之後）實機發現缺陷 A–G 與觀察 H（`_tpm/runs/20261010-sdlc-meeting-record/t6-results.md`〈t6 接續〉；A／B／E 根因 `t6-rca-ABE.md`；F 與 F2 的根因由 spec-author 以場次複本在 repo 外重現，`design.md §7.4` 第 3 步）。使用者決定 D21（靜音只 warn）、D22（當機 fragment 先修，修不好再放寬），並決定 A、B 與 C（D21）在 t6 其他項目測完後同一輪修。本輪只有文件 commit；實作要等使用者核准本輪 spec＋plan 後才開始。

**對應 spec**：§3.2（`audioDuration` 算法釐清）、§3.4（新增 `nextSegmentSize`、`shouldEmitVideoHeartbeat`、`CompletionOutcome`、`completionOutcome`；`routeSample` 註解更正）、§4.2.5／§4.2.6（D21）、§4.3.4、§4.3.6（A）、§4.4.3 (c)（G）、§4.4.7、§4.4.9（D）、§4.4.10、§4.8.4（E／D22）、§4.6.14 (B) 補充、§4.6.17（B）、§4.6.18（F）、§4.6.19（F2）、§6 第 54–62 條、§7 疑慮 25–29。觀察 H 不修（§7 疑慮 25）。

**子任務**（n1–n4 只是本節的短代號，**不是任務編號**；分支 `feature/meeting-record--n1` …，各開 worktree，從本輪 docs commit 之後的 `feature/meeting-record` 開出）：

| id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec |
|---|---|---|---|---|---|
| n1 | test | Python 側：紅燈測試、D21 的測試預期修改、`e2e_check.py` 判準修正（G、F2） | `tests/record/` | — | §4.2.5（`.fail` 訊息，§6 第 54 條）、§4.3.6、§4.4.3 (c)、§4.4.9、§4.4.10（以上三條的靜態檢查）、§4.6.17、§4.6.18、§4.6.19 |
| n2 | test | Swift 紅燈測試 | `tools/MeetingRecorder/Tests/` | — | §3.4（本輪新增名稱）、§4.3.6、§4.4.9、§4.4.10 |
| n3 | code | 錄製器：換段當下同步讀尺寸（A）、最終訊息（D）、影片心跳（E）、第 5 項 `.fail` 訊息（D21） | `tools/MeetingRecorder/Sources/` | n1、n2 | §3.4、§4.2.5、§4.3.4、§4.3.6、§4.4.7、§4.4.9、§4.4.10、§4.8.4 |
| n4 | code | finalize：尾端長度（B、F） | `bin/_record_finalize.py` | n1 | §4.6.3、§4.6.17、§4.6.18（§4.6.1–4.6.16 不得退步） |
| t6 | check | t6 第二輪重測（人工，與使用者一起做） | （無檔案；結果寫 run 目錄） | n3、n4 | 見下〈t6 第二輪重測順序〉 |

**分層**：Red：n1＋n2（平行）→ 第 2 層：n3＋n4（平行）→ t6 第二輪重測。SKILL.md 的 D21 句子已在本輪 docs commit 寫好，不另設子任務。

**拆分理由**（數量最小化，沿用 §6 的理由）：
- n1／n2 分開：兩種語言、兩套執行器，檔案不重疊；平行。`e2e_check.py` 的判準修改（G、F2）是 `tests/record/` 的工具與自我測試，與紅燈同屬 n1，不另拆。
- n3 不拆：A、D、E 都改 `RecordingSession.swift`，D21 只改 `PreflightRunner.swift` 一句字串；而且 `Tests/run.sh` 把 `Core/*.swift` 與全部測試編成一支執行檔，同層兩個 Swift 子任務看不到對方的 Core 名稱、`run.sh` 會編譯失敗（§6 同一理由）。
- n3／n4 分開：Swift 與 Python 只經段落檔與 `manifest.json` 相接，本輪沒有改契約；平行。
- n4 只相依 n1：finalize 的測試全是 Python 合成素材。

### n1 要點（tests/record/）
- `test_static_rules.py`：
  - **修改既有預期（使用者核准的例外，spec §6 第 54 條，依據 D21）**：`test_preflight_system_audio_two_stage` 第 261–263 行那一組，改為「`PreflightRunner.swift` 的字串字面值中應含『重新授權螢幕錄製』與『完全結束 MeetingRecorder 再重開』，且任何字面值都不得含『取消輸出靜音』『把音量調大』」。同一測試的其他斷言**一字不改**；commit 訊息內文寫明「D21 核准的測試預期修改，spec §6 第 54 條」。
  - 新增 `test_segment_size_read_synchronously_at_boundary`（§4.3.6 的實作形狀）、`test_completion_uses_outcome`（§4.4.9）、`test_video_heartbeat_on_idle`（§4.4.10）。函式本體的切法沿用檔內既有的 `swift_functions`、`strip_swift_comments`、`blank_swift_strings`。三支歸 n3 轉綠。
- `test_finalize.py`：新增 `test_tail_frame_not_overlong`（§4.6.17）、`test_sparse_vfr_last_segment_covers_audio`（§4.6.18）；素材產生函式放 `tests/record/_media.py`，一律在 `TMPDIR` 下現場產生、不提交媒體檔。沒有 `h264_videotoolbox` 時 `skipTest` 並寫明原因（缺陷只在該編碼器出現）。兩支歸 n4 轉綠。
- `e2e_check.py`：
  - `segment_cadence`（缺陷 G，§4.4.3 (c)）：提前換段的判定改為「任何欄位的 `audioFormatEvents` 與 `startedAt_{i+1}` 相差 < 0.5 秒」或「第 i 段 `finishedAt` 為 `null`」，且間隔 < 60.000 − 0.001；只判定期換段。`format_rotation` 不動。
  - 新增 `segment_audio_duration(path)`（§3.2 算法），`gap` 改用它（缺陷 F2，§4.6.19）。
- `test_e2e_check.py`：新增 `test_segment_cadence_excludes_early_rotation`（合成場次：60 秒定期換段、一次只改 `interleaved` 的格式變更提前換段、緊接一次 `sampleRate` 改變的提前換段、再接 60 秒定期換段 → PASS；另一組有一個 45 秒間隔、附近沒有格式事件且前一段 `finishedAt` 非 `null` → FAIL）、`test_gap_uses_finalize_audio_duration`（§4.6.19 的三種段落；以 `importlib` 載入 `bin/_record_finalize.py` 的 `analyze`，只讀、不改該檔）。**既有 `test_e2e_check.py` 的預期一律不得改**；若 `gap` 換算法讓既有合成場次結果改變，停下以 `needs_decision` 回報（spec §6 第 61 條）。
- **完成條件**：(1) 上列 6 支紅燈（靜態 4：含改了預期的 `test_preflight_system_audio_two_stage`；finalize 2）在 n1 分支上失敗，且原因是「功能不存在」：靜態檢查缺字串或仍有禁止字串、finalize 素材在現行程式上 §4.6.17 回 5、§4.6.18 影音差 > 100 ms——不是 ImportError、語法錯誤；(2) `e2e_check.py` 的修改與 `test_e2e_check.py` 全部綠（含 2 支新的與既有全部）；(3) 全量 `python3 -m unittest discover -s tests/record -t .` 的失敗集合**恰為**上述 6 支；(4) `-k test_no_client_names_in_repo_text` 綠且不得 `skipped`；(5) 把 2254 場次的 `tracks/` 複製到 `TMPDIR`（只複製 `manifest.json`、`record.meta.json` 與段落檔，用完刪除，正本不動），以新版 `e2e_check.py --segment-writer` 跑，`segment_cadence` 應 PASS（4 個提前換段被排除、定期換段 60.000 秒），結果寫進信封的 evidence，不寫進 repo。

### n2 要點（tools/MeetingRecorder/Tests/）
- `SegmentsTests.swift`：`testNextSegmentSize`（§4.3.6 全部案例）、`testShouldEmitVideoHeartbeat`（§4.4.10 全部案例）；`RecordsTests.swift`：`testCompletionOutcome`（§4.4.9 全部案例，含「停止原因開頭、收尾失敗附在後面」）。新函式登記進各檔開頭的測試清單。
- **完成條件**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 失敗，且原因只有「缺少本輪 Core 名稱」（`nextSegmentSize`、`shouldEmitVideoHeartbeat`、`CompletionOutcome`、`completionOutcome` 的編譯錯誤），沒有其他編譯錯誤。

### n3 要點（錄製器）
- `Core/Segments.swift` 加 `nextSegmentSize`、`shouldEmitVideoHeartbeat`；`Core/Records.swift` 加 `CompletionOutcome`、`completionOutcome`（spec §3.4，名稱照抄、不得改名、不得改既有名稱）。
- **A**（`design.md §7.1`）：`RecordingSession` 加可替換屬性 `windowPointSize: (UInt32) -> CGSize?`，預設以 `CGWindowListCreateDescriptionFromArray` 讀 `kCGWindowBounds`；`startNewSegment` 同步讀、經 `nextSegmentSize` 決定新段尺寸；刪 `pendingSize`、`sizeQuery`、`scheduleSizeQuery` 及 `requestStop` 裡的 `sizeQuery?.cancel()`。
- **D**（`design.md §7.2`〈writer 失敗〉）：`complete(finalizeCode:)` 改以 `completionOutcome` 決定 `phase`／`code`／`message`，`record.log` 最後一行與通知照它寫。
- **E**（`design.md §7.2`〈當機〉）：`Capture/` 定義 `videoHeartbeatSeconds = 1.0`；`.screen` 收到 `idle` 且 PTS 有效時，在序列佇列上 `videoHeartbeat(pts)`：`shouldEmitVideoHeartbeat(...)` 為 true 就以 `retimedVideoSample(lastFrame, pts:)` 走與一般視訊 sample 相同的路寫入，**不更新** `lastFrame`、不計入 `frameStatus.complete`。
- **D21**：`PreflightRunner.swift` 第 5 項 `.fail` 訊息改為只含授權補救（spec §4.2.5）。
- 不得呼叫 `AudioObjectSetPropertyData`（§4.9.4）；`Probe.swift` 不動。
- **完成條件**：(1) `run.sh` 全綠；(2) `python3 -m unittest discover -s tests/record -t . -k test_preflight_system_audio_two_stage -k test_segment_size_read_synchronously_at_boundary -k test_completion_uses_outcome -k test_video_heartbeat_on_idle` 全綠，且 `test_static_rules.py` 其餘測試仍綠；(3) 以 `MH_RECORDER_DEST=$(mktemp -d)` 建 app 成功，`codesign -dvv` 的 flags 含 `runtime`、`codesign -d --entitlements -` 含兩項 entitlement；**不得覆蓋** `~/Applications/MeetingRecorder.app`、不得啟動 app、不得觸發 TCC 授權框；(4) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。實機行為（縮放、`kill -9`、chmod）在 t6 驗。

### n4 要點（finalize）
- 照 `design.md §7.4` 第 3、4 步：補尾上限 `cap = 段落長 − 5 ms`（不依連結影格率）；一律加 `setpts`（沒有改動時 `setpts=PTS`），並把「只在需要時才加 setpts」的註解改成實測行為（缺陷 B 根因）；正規化後影片軌長以最後一幀 PTS 判、容差 50 ms；串接加 `-bsf:v setts=duration=if(eq(NEXT_PTS\,NOPTS)\,1\,DURATION)`。不改 `link_fps` 的容差來掩蓋漂移；`audioDuration` 的算法不動（§3.2 已改成照現行實作寫）。
- **完成條件**：(1) `python3 -m unittest discover -s tests/record -t . -k test_finalize -k test_concurrency` 全綠（含既有 §4.6.1–4.6.16 的測試，預期不得改）；(2) 全量 Python 測試中，除 n3 歸屬的 4 支靜態測試外全綠；(3) 把 2254、1650 兩個場次的 `tracks/`（只複製段落檔、`manifest.json`、`record.meta.json`）複製到 `TMPDIR` 跑新版 finalize：兩者都回 0，`e2e_check.py <複本> --segment-writer` 的 `video_covers_audio` PASS（repo 外驗證值：2254 差約 28 ms、1650 差約 30 ms）；用完刪除，正本不動，數字寫進信封的 evidence；(4) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0；(5) 不得在 repo 內產生媒體檔（§4.14.1）。

### 每層整合後的測試指令（本輪；integrator 照此跑，一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red（n1＋n2） | `python3 -m unittest tests.record.test_e2e_check tests.record.test_surface_parsers`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 全量 Python 指令（失敗集合恰為 n1 完成條件 (1) 的 6 支）；`run.sh`（只因缺本輪 Core 名稱而編譯失敗） |
| 第 2 層（n3＋n4） | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 無；任何一支不綠就停下交人 |

### t6 第二輪重測順序（n3、n4 合併後；需使用者在場）
1. **重新安裝**：以 `build.sh` 覆蓋 `~/Applications/MeetingRecorder.app`（**先問使用者，當下同意才做**）；固定身分簽章，TCC 授權預期沿用，跑一次 `meeting record preflight` 確認。
2. **2254、1650 場次重新收尾**（§4.6.18、§4.6.19）：1650 先前 rc 5、沒有輸出，直接 `meeting record finish <場次>`；2254 已有輸出與 `tracks/finalize.json`（冪等會直接回「已完成」），要先把既有的 `影片/*.mov`、`錄音/*.wav`、`tracks/finalize.json` **移到備份目錄**再跑——動到使用者的資料，**先問使用者**。兩場都跑 `e2e_check.py <場次> --segment-writer`：`video_covers_audio` 應 PASS（< 100 ms）、`gap` 不得出現「與實測不符」、2254 的 `segment_cadence` 應 PASS。
3. **§4.3.4 縮放**（A）：錄製中縮小視窗、跨一個邊界、再放大、再跨一個邊界；縮放後第一個邊界開出的段落就要是新尺寸（逐段 `ffprobe` 對 `manifest.json`）。
4. **`kill -9`（§4.8.4，E／D22）**：會議視窗保持靜止、會議 app 有聲音，錄 90 秒以上 `kill -9`，`record finish` 後 wav ≥ 經過秒數 − 21 秒、不得「略過無法讀取的段落」；另做一次「會議 app 沒聲音」只記錄（§7 疑慮 27）。仍不過 → 依 D22 以 `needs_decision` 回報（選項含放寬為「當機最多丟 1 段（60 秒）」）。
5. **chmod 寫檔失敗（§4.4.7，D）**：同 t6 做法；確認自動停止後 `record.status.json.message` 與 `record.log` 最後一行以「段落連續寫檔失敗」開頭（收尾失敗附在後面）；`chmod u+w` 後 `record finish` 回 0。
6. **§4.9.3 嚴格版**：輸出用藍牙耳機、被錄的就是播同步測試源的視窗（`e2e_check.py --print-sync-source`，§4.3.5）、中途切輸入到同一副耳機的麥克風並**持續說話**，再錄 ≥ 60 秒；`e2e_check.py --hfp --sync --segment-writer`。裝置切換後第一次 preflight 的第 6 項數值要記下（觀察 H，§7 疑慮 25）。
7. **其餘 t6 項目**：§4.2.6 第 5 項 (i) 依 D21 再確認一次（輸出靜音＋會議 app 沒聲音 → warn、照常開錄、訊息不再叫人取消靜音）；§4.9.1、§4.9.2（全程藍牙 ≥ 3 分鐘、使用者說話時長足夠）、§4.10、§4.11、§4.15、§4.3.3、§4.7.1、§4.5.5、§4.13.4–4.13.5 等尚未完成的項目，照 §2 t6 與 §6〈t6 接續順序〉接續；完成與否以 `progress.md` 為準。

## 8. t6 第三次中途修正輪（I、J、K、L、M、§4.8.1；2026-10-12，定案）

**起因**：t6 第二輪重測（`_tpm/runs/20261010-sdlc-meeting-record/t6-results.md`「t6 第二輪重測」「t6 第二輪 7」）發現 I（幕前調度縮圖）、缺陷 J（串接後音訊逐段延後）、K（sync 嗶聲偵測與 `hfp`／`device_switch` 判準）、L（錄製中磁碟檢查讀到快取值）、M（§4.3.3 影格間隔判準過嚴），以及 §4.8.1 wav 上限過時。I、K、M、§4.8.1 依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議選項定案（I＝A preflight 提醒；K＝A「不得連續 ≥ 3 秒 ≤ -60」＋1 kHz 帶通；M＝三條件；§4.8.1 上限＝開錄到 `kill -9` 的秒數＋1 秒），使用者可於醒來後改選（spec §6 第 63–70 條、§7 疑慮 34）。J 的根因與修法已以場次複本驗證（`design.md §7.4`〈缺陷 J〉）。

**對應 spec**：§3.4（新增 `stageManagerNotice`）、§4.2.12（I）、§4.3.3（M）、§4.5.9（L）、§4.6.12（字面）、§4.6.20、§4.6.21（J）、§4.8.1（上限）、§4.9.1、§4.9.3（K）、§6 第 63–70 條、§7 疑慮 29（結案）、30–34。

**子任務**（p1–p5 只是本節的短代號，**不是任務編號**；分支 `feature/meeting-record--p1` …，各開 worktree，從本輪 docs commit 之後的 `feature/meeting-record` 開出）：

| id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec |
|---|---|---|---|---|---|
| p1 | test | Python 側：紅燈測試＋`e2e_check.py` 判準修正（K、M）與自我測試 | `tests/record/` | — | §4.2.12（靜態、文件）、§4.3.3、§4.5.9（靜態）、§4.6.20、§4.9.1、§4.9.3 |
| p2 | test | Swift 紅燈測試 | `tools/MeetingRecorder/Tests/` | — | §3.4、§4.2.12 |
| p3 | code | 錄製器：幕前調度提醒（I）、磁碟檢查不讀快取（L） | `tools/MeetingRecorder/Sources/` | p1、p2 | §3.4、§4.2.12、§4.5.5、§4.5.9 |
| p4 | code | finalize：音訊 PCM 正規化、串接時一次編 AAC（J） | `bin/_record_finalize.py` | p1 | §4.6.12、§4.6.20、§4.6.21（§4.6.1–4.6.19 不得退步） |
| p5 | docs | SKILL.md、README 補幕前調度一句 | `.claude/skills/meeting-record/SKILL.md`、`README.md`（不得動 `record-cli` 區塊） | p1 | §4.2.12（文件） |
| t6 | check | t6 第三輪驗證（多數離線、不需使用者） | （無檔案；結果寫 run 目錄） | p3、p4、p5 | 見下〈t6 第三輪驗證順序〉 |

**分層**：Red：p1＋p2（平行）→ 第 2 層：p3＋p4＋p5（平行）→ t6 第三輪驗證。

**拆分理由**（數量最小化，沿用 §6、§7）：
- p1／p2 分開：兩種語言、兩套執行器，檔案不重疊。`e2e_check.py` 的判準修改（K、M）是 `tests/record/` 的工具與自我測試，與紅燈同屬 p1。
- p3 不拆：I 與 L 都在 `PreflightRunner.swift`，`Tests/run.sh` 把 `Core/*.swift` 與全部測試編成一支執行檔（§6 同一理由）。
- p4 獨立：只改 `bin/_record_finalize.py`，與 Swift 只經段落檔相接，本輪不改契約。
- p5 獨立：文件檔與 p3 的 Swift 原始碼、p4 的 Python 不重疊；只依賴 p1 的 `test_docs.py` 新測試。若 integrator 想少開一個 worktree，可在 p3 之後由同一人做，但不得併進 p3 的 owns。

### p1 要點（tests/record/）
- **紅燈（新增）**：
  - `test_finalize.py::test_concat_no_audio_drift`（§4.6.20 (i)–(iii)）：素材照 spec 的配方由 `tests/record/_media.py` 現場產生（4 段 10.017／3.3／7.0／5.013 秒；影片每 2 秒閃白 0.1 秒；系統聲音雙聲道 AAC 同時 1 kHz 嗶聲、第一段前 50 ms 靜音；麥克風單聲道 AAC 低音量雜訊；閃白與嗶聲的相位依段落起點接續；`manifest.json` 的 `startedAt` 照累加段長寫）。量法共用 `e2e_check.py` 的新 sync 函式（帶通＋局部起點），以 `importlib` 載入、只讀。現行程式上的預期失敗：(i) 解碼長度比時間戳長約 106 ms（> 25 ms），(iii) 第 4 段中位比原始段多約 100 ms（> 10 ms；scratchpad 實測修前 93 ms 對原始約 −11 ms）。沒有 `h264_videotoolbox` 時用 libx264 也能重現（缺陷與影片編碼器無關），不得 skip。
  - `test_static_rules.py::test_finalize_concat_reencodes_audio_once`（§4.6.20 (iv)）：`bin/_record_finalize.py` 的正規化編碼參數含 `pcm_s16le`；串接那一次 `ffmpeg` 呼叫含 `-c:v` `copy` 與 `-c:a` `aac`，且整個檔不得出現把音訊 `-c copy`／`-c:a copy` 用在 concat 的組合。
  - `test_static_rules.py::test_available_bytes_not_cached`（§4.5.9）：`PreflightRunner.swift` 的 `availableBytes` 函式本體（沿用 `swift_functions`、`strip_swift_comments`、`blank_swift_strings`）含 `removeAllCachedResourceValues` 或 `URL(fileURLWithPath:`。
  - `test_static_rules.py::test_stage_manager_read_only`（§4.2.12）：`tools/MeetingRecorder/Sources/` 含 `com.apple.WindowManager` 與 `GloballyEnabled`、呼叫 `stageManagerNotice(`；`Sources/` 與 `bin/` 不得出現 `CFPreferencesSetAppValue`、`CFPreferencesSetValue`、`defaults write`。
  - `test_docs.py::test_stage_manager_documented`（§4.2.12）：SKILL.md 與 README.md 錄製段各有一句含「幕前調度」與「縮圖」；README 的 `record-cli` 區塊不變（既有測試已保護）。
- **`e2e_check.py` 判準修改（本身要綠）**：
  - `sync`（K (a)，§4.9.3）：嗶聲改為兩次 `bandpass=f=1000:width_type=h:w=100`、48 kHz 單聲道、1 ms 窗 RMS 包絡；每個閃白在 ±0.3 秒內取包絡最大值、第一個 ≥ 50% 的窗為起點；每個「嗶聲 − 閃白」絕對值 < 100 ms、閃白與嗶聲各 ≥ 3。把這組函式做成可被測試載入的公開函式（例 `sync_offsets(path)`），供 `test_concat_no_audio_drift` 共用。
  - `device_switch`、`hfp`（K (b)，§4.9.1、§4.9.3）：「其餘時間／格式變更後」的低音量判定改為「連續 ≥ 6 個 0.5 秒時段（≥ 3 秒）≤ -60 dBFS 或 `null`」才 FAIL；切換中斷 < 3 秒的判定不變。
  - `fps_min_interval`（M，§4.3.3）：改為 (i) 1 秒滑動窗影格數最大值 ≤ 61、(ii) 最終片 < 1/60 − 1 ms 的間隔數 ≤ 各段 `seg-*.mov` 同條件的合計＋(段數 − 1)、(iii) 最小間隔 ≥ 1 ms；訊息列出三個數字。段落讀不到時 (ii) 判 FAIL 並說明。
- **`test_e2e_check.py`（使用者核准的測試修改，spec §6 第 66、68 條；commit 訊息內文寫明條號）**：既有預期中與新判準衝突的部分照新判準改（只改衝突的那幾個斷言，其餘一字不改）；新增：`sync` 素材疊上 1 kHz 附近有能量的雜訊（語音替身）仍 PASS、嗶聲晚 150 ms 判 FAIL；`hfp`／`device_switch` 有 2.5 秒低音量停頓判 PASS、3 秒判 FAIL；`fps_min_interval` 新增 `test_fps_min_interval_check`（原始段落有 10 ms 間隔、最終片只多 1 個邊界間隔 → PASS；擠成 < 1 ms → FAIL；過近間隔比原始多出段數以上 → FAIL）；`fps120` 仍判 `fps_min_interval` FAIL（由 (i) 擋）。
- **完成條件**：(1) 上列 5 支紅燈在 p1 分支上失敗，且原因是「功能不存在」（finalize 素材在現行程式上 (i) 或 (iii) 不成立；靜態檢查缺字串；文件缺句子）——不是 ImportError、語法錯誤；(2) `python3 -m unittest tests.record.test_e2e_check` 全綠；(3) 全量 `python3 -m unittest discover -s tests/record -t .` 的失敗集合**恰為**上述 5 支；(4) `-k test_no_client_names_in_repo_text` 綠且不得 `skipped`；(5) 把 t6r2-HFP2 場次的 `錄音/tracks/` 與 `影片/*.mov` 複製到 `TMPDIR`（正本不動，用完刪），新版 `e2e_check.py <複本> --sync --fps-interval 00:05-00:55` 的結果寫進信封 evidence：`sync` 預期 FAIL（最大約 140 ms，缺陷 J 未修的影片）、`fps_min_interval` 預期 PASS（59／243 ≤ 243／6.67 ms）。

### p2 要點（tools/MeetingRecorder/Tests/）
- `PreflightTests.swift::testStageManagerNotice`（§4.2.12：true → 含「幕前調度」「縮圖」「目前舞台」；false、nil → nil）。新函式登記進該檔開頭的測試清單。
- **完成條件**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 失敗，且原因只有「缺少 `stageManagerNotice`」的編譯錯誤。

### p3 要點（錄製器）
- `Core/Preflight.swift` 加 `stageManagerNotice(globallyEnabled:)`（spec §3.4，名稱照抄）。
- **I**（`design.md §6` 第 12 項、§7.1〈幕前調度〉）：`PreflightRunner` 以 `CFPreferencesCopyAppValue("GloballyEnabled" as CFString, "com.apple.WindowManager" as CFString)` 只讀；第 12 項 `window_minimized` 在「疑似最小化」或「幕前調度開啟」任一成立時 `ok: false`，message 依 spec §4.2.12 串接；`start`／`quick-start` 開錄時同一句寫一行進 `record.log`。`PreflightItem` 不加項目。不得寫任何 defaults。
- **L**（`design.md §7.3` 磁碟列）：`availableBytes` 讀前以 `URL(fileURLWithPath: existingAncestor(url).path)` 新建 URL 並 `removeAllCachedResourceValues()`；退回 `volumeAvailableCapacity` 的邏輯不變。
- **完成條件**：(1) `run.sh` 全綠；(2) `python3 -m unittest discover -s tests/record -t . -k test_available_bytes_not_cached -k test_stage_manager_read_only` 綠，`test_static_rules.py` 其餘仍綠；(3) 以 `MH_RECORDER_DEST=$(mktemp -d)` 建 app 成功、`codesign` 檢查同 §7 n3；**不得覆蓋** `~/Applications/MeetingRecorder.app`、不得啟動 app、不得觸發 TCC 授權框；(4) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。

### p4 要點（finalize）
- 照 `design.md §7.4` 第 3–5 步與〈缺陷 J〉：`encode()` 的音訊改 `-c:a pcm_s16le`（不再 `-b:a`），`-t` 用 `{dur:.6f}`；串接改 `-c:v copy -c:a aac -b:a 256k`，保留既有 `-bsf:v setts=…`、`-movflags +faststart`、串接後的解碼與 dts 檢查；`check_norm` 的音訊長度判定對 PCM 照常成立（封包算）。模組 docstring 第 3、4 步同步改寫。scratchpad 已驗證的改動就只有這兩處參數（`design.md §7.4`〈缺陷 J〉驗證）。
- **完成條件**：(1) `python3 -m unittest discover -s tests/record -t . -k test_finalize -k test_concurrency -k test_finalize_concat_reencodes_audio_once` 全綠（含既有 §4.6.1–4.6.19，預期不得改）；(2) 全量 Python 測試中，除 p3、p5 歸屬的 3 支外全綠；(3) §4.6.21：把 t6r2-HFP2、2254、1650、t6r2-AE、t6r2-E2、t6r2-E3 六場的 `錄音/tracks/` 段落檔、`manifest.json`、`record.meta.json`（有 `meeting.json` 一併）複製到 `TMPDIR`，以新版 finalize 收尾：全部 rc 0；`e2e_check.py <複本> --segment-writer` 的 `video_covers_audio`、`gap` 全 PASS，其餘結果與修前相同；六場「解碼樣本數 ÷ 48000 − 音訊軌 stream `duration`」≤ 25 ms；HFP2 以新 `sync` 量法 PASS、各段時距中位數與段內原始差 ≤ 10 ms（參考值：修後 32.0／33.4／22.4 對原始 30.8／32.7／23.5 ms）；數字寫進信封 evidence，複本用完刪、正本不動；(4) `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0；(5) 不得在 repo 內產生媒體檔（§4.14.1）。

### p5 要點（文件）
- SKILL.md 錄製注意事項加一句（例：「開著幕前調度時，會議視窗不在目前舞台會被縮成縮圖，錄到的畫面也會變小；錄會議時讓會議視窗留在舞台上，或先關閉幕前調度。」）；README 錄製段加同義一句。
- **完成條件**：`python3 -m unittest tests.record.test_docs` 全綠；`-k test_no_client_names_in_repo_text` 綠且不得 `skipped`；`bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。

### 每層整合後的測試指令（本輪；integrator 照此跑，一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red（p1＋p2） | `python3 -m unittest tests.record.test_e2e_check tests.record.test_surface_parsers`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 全量 Python 指令（失敗集合恰為 p1 完成條件 (1) 的 5 支）；`run.sh`（只因缺 `stageManagerNotice` 而編譯失敗） |
| 第 2 層（p3＋p4＋p5） | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 無；任何一支不綠就停下交人 |

### t6 第三輪驗證順序（p3、p4、p5 合併後）
1. **重新安裝**：以 `build.sh` 覆蓋 `~/Applications/MeetingRecorder.app`（Swift 有改）。覆蓋前確認使用者的同意範圍（前兩輪皆為使用者當下選「覆蓋（建議）」；本輪由主 session 依使用者「剩下的你自己做」的指示判斷並在 `progress.md` 記錄依據）；固定身分簽章，TCC 授權預期沿用，跑一次 `meeting record preflight` 確認第 12 項在幕前調度關閉時為 ok。
2. **離線（不需使用者、不需錄製器）**：(a) §4.6.21 六場複本重新收尾（同 p4 完成條件 (3)，主 session 在整合分支再跑一次）；(b) §4.9.3：HFP2 複本收尾後的影片跑 `e2e_check.py --sync --hfp --segment-writer --status <複本的 status 檔或略過 warnings 核對>`——`sync` 應 PASS（< 100 ms），`hfp` 以新判準應 PASS（格式變更後只有 123.0、123.5 兩個時段 ≤ -60，< 3 秒）；`format_rotation`／`hfp` 若因找不到該場次的 `record.status.json` 而 FAIL，依 t6 第二輪紀錄的 warnings（沒有 silence 告警）人工判讀並註明；(c) §4.3.3：HFP2 收尾後 `e2e_check.py --fps-interval 00:05-00:55` 的 `fps_peak`、`fps_min_interval` 都應 PASS；(d) §4.8.1：t6r2-auto/collide 場次（133 秒 `kill -9`、wav 130.1 秒）以 `--expect-min 60 --expect-max 134` 應 PASS。
3. **§4.5.5 錄製中磁碟不足（L）**：同 t6 第二輪 7 的做法（35 GB sparse image 為根、開錄後填到 < 2 GB）；60 秒內應自動停止、`record.status.json.code` 5、訊息含磁碟原因；收尾後卸載 image。
4. **§4.2.12 幕前調度提醒（I）**：需要開啟幕前調度＝改使用者系統設定，**主 session 與 agent 不得代為切換**；留給使用者醒來後自行開啟、跑一次 `meeting record preflight` 看第 12 項 warn、再自行關閉。未做前以 Swift 單元測試與靜態檢查為準，`progress.md` 註明「人工未驗」。
5. **既有使用者場次的重新收尾**（缺陷 J 影響已出的影片與 wav，spec §7 疑慮 30）：會動到使用者的輸出檔，**不自動做**，列為給使用者的選項。

---

## 9. R2 第二輪（2026-10-12）：靜音、暫停、選單選視窗與位置、計時、標記、偏好設定

- 上游：`intent.md`〈R2 第二輪功能〉〈R2 閘門 1 使用者決定〉（已核准）、`design.md`〈R2 第二輪設計〉、`spec.md` 檔尾〈R2 第二輪〉（§3.9–§3.14、§4.16–§4.25、R2-§6 第 77–97 條、R2-§7 疑慮 35–42）、`adr/adr-r2-*.md` 四則。**本節以上的第一輪計畫一字不改。**
- 第一輪基準點：本機 tag `meeting-record-r1-baseline`（＝`f084765`）。R2 的 commit 全部疊在它之後，第一輪可單獨核准、單獨拆 PR（R2-Q1 使用者決定）；R2 的拆包規劃見 §9.5（閘門 2 修正輪補寫），不改 §5。
- **閘門 2 修正輪（2026-10-12）**：依使用者在閘門 2 的四項決定與 skeptic 8 條問題修正本節：§9.1 的「對應 spec」欄逐條列出（不再用範圍），並與派工 JSON 的 `story_ids` 逐條相同；新增驗收 §4.16.11、§4.17.7、§4.17.8、§4.18.8–§4.18.12 分到 r2a、r2b、r2d、r2e、r2g；新增 §9.5 拆 PR 規劃。使用者決定 4：複查沒有新問題就視為閘門 2 核准、直接進 build。
- R2 各段的紀錄與核准以 `r2-` 前綴的 stage 鍵記在同一個 run 目錄（`r2-design`、`r2-build`、`r2-test`；R2-Q2 使用者決定）。
- 子任務 id（`r2a`…`r2g`、`r2t7`）只是本節的短代號，**不是任務編號**。分支 `feature/meeting-record--r2a` …，各開 worktree，從本輪 design commit 之後的 `feature/meeting-record` 開出。
- 約束照舊：不 push、不改 `main`、不改寫歷史、不刪 tag；不得啟動 `~/Applications/MeetingRecorder.app`、不得覆蓋它、不得觸發 TCC 授權框或改使用者系統設定（建置一律 `MH_RECORDER_DEST=$(mktemp -d)`）；public repo 不寫真實名稱，範例用「[Stand-up] 範例專案」；不讀 run 目錄的 `client-names.txt` 內容（只以 `MH_CLIENT_NAMES_FILE` 傳路徑給測試）。
- 所有子任務 commit 前跑 verify：`bash bin/_lint.sh && bash bin/meeting.sh doctor`；署名行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；`progress.md` 由主 session 維護。

### 9.1 子任務

| id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec |
|---|---|---|---|---|---|
| r2a | test | Python 側：R2 紅燈測試、`e2e_check.py` 的暫停／靜音判準與自我測試、替身、§6 第 77 條核准的測試預期修改 | `tests/record/` | — | §4.16.4、§4.16.5、§4.16.6、§4.16.7、§4.16.8、§4.16.9、§4.16.11、§4.17.2、§4.17.5、§4.17.6、§4.17.8、§4.18.2、§4.18.3、§4.18.4、§4.18.5、§4.18.6、§4.18.7、§4.18.11、§4.18.12、§4.19.2、§4.19.3、§4.19.4、§4.20.4、§4.20.5、§4.20.6、§4.20.8、§4.21.3、§4.21.4、§4.21.5、§4.22.2、§4.22.4、§4.22.5、§4.23.2、§4.23.3、§4.23.4、§4.24.1、§4.24.2、§4.24.3、§4.24.4、R2-§6 第 77 條 |
| r2b | test | Swift 側：R2 Core 紅燈測試 | `tools/MeetingRecorder/Tests/` | — | §3.14、§3.14.1、§4.16.1、§4.16.2、§4.16.3、§4.16.10、§4.17.1、§4.17.3、§4.17.4、§4.17.7、§4.18.1、§4.18.2、§4.18.3、§4.18.8、§4.18.9、§4.18.10、§4.19.1、§4.20.1、§4.20.2、§4.20.3、§4.20.5、§4.20.7、§4.21.1、§4.21.2、§4.22.1、§4.22.3、§4.23.1 |
| r2c | doc | 文件先寫：SKILL.md、README 的 R2 說明與 12 列 `record-cli` 區塊 | `.claude/skills/meeting-record/SKILL.md`、`README.md` | r2a | §2.4.5、§4.24.2、§4.24.3、§4.24.4 |
| r2d | code | Swift `Core/`：`Control.swift` 新增；`Records`、`Detectors`、`AudioLevel`、`Trigger`、`Segments` 增補 | `tools/MeetingRecorder/Sources/Core/` | r2b | §3.14、§3.14.1、§4.16.1、§4.16.2、§4.16.3、§4.16.10、§4.17.1、§4.17.3、§4.17.4、§4.17.7、§4.18.1、§4.18.8、§4.18.9、§4.18.10、§4.19.1、§4.20.1、§4.20.2、§4.20.3、§4.20.5、§4.20.7、§4.21.1、§4.21.2、§4.22.1、§4.22.3、§4.23.1 |
| r2e | code | 錄製端：SIGUSR1、控制檔重設、暫停閘門、mic 歸零、偵測器重設、標記、事件、狀態欄位、完成通知識別碼 | `tools/MeetingRecorder/Sources/Capture/` | r2a、r2b、r2d | §4.16.4、§4.17.2、§4.18.2、§4.18.3、§4.19.2、§4.23.3 |
| r2f | code | 觸發層：menu bar（變寬計時、收音列、新選單、子選單、控制、完成通知、自動前處理）、HotKey 多組、quick-start `--window`／`--root`、偏好設定與登入項目、無參數啟動 | `tools/MeetingRecorder/Sources/Trigger/`、`tools/MeetingRecorder/Sources/main.swift`、`tools/MeetingRecorder/Resources/`、`tools/MeetingRecorder/build.sh` | r2a、r2b、r2c、r2d | §4.16.4、§4.20.4、§4.20.5、§4.20.6、§4.20.7、§4.20.8、§4.21.3、§4.21.4、§4.21.5、§4.22.2、§4.22.4、§4.22.5、§4.23.2、§4.23.3、§4.23.4 |
| r2g | code | CLI 與 finalize：`record.sh` 五個子指令、`status`／`stop` 摘要、help；`meeting.sh` usage；finalize 的 `gapStats` 扣暫停與 `markers.json` 複製 | `bin/record.sh`、`bin/meeting.sh`、`bin/_record_finalize.py` | r2a、r2c | R2-§2.2、§4.16.5、§4.16.6、§4.16.7、§4.16.8、§4.16.9、§4.16.11、§4.18.4、§4.19.3、§4.24.2、§4.24.5 |
| r2t7 | check | 實機 t7（使用者在場）＋設計審查截圖 | （無檔案；結果與截圖寫 run 目錄） | r2e、r2f、r2g | §4.22.6、§4.25.1、§4.25.2、§4.25.3、§4.25.4、§4.25.5 |

「對應 spec」欄＝派工 JSON 的 `story_ids`（每項前加「spec 」，逐條相同、不用範圍）。r2b 收所有「測試」欄有**新增** `swift:` 測試的節（`swift:TriggerTests.swift` 這類既有、不改的不算）；r2a 收所有「測試」欄有 Python 測試（新增或 §6 第 77 條修改）的節；同一節兩邊都有就兩邊都列。只用既有、不改的測試驗收的節，列給完成條件要跑它的子任務：§4.24.4（客戶名稱守門）列 r2a、r2c，§4.24.5（lint 檔數與 verify）列 r2g。

**分層**（`sdlc-build.js` 依相依分層）：Red：r2a＋r2b（平行）→ 第 1 層：r2c＋r2d（平行）→ 第 2 層：r2e＋r2f＋r2g（平行）→（test 段）r2t7。

**拆分理由**（數量最小化）：
- **r2a／r2b 分開**：兩種語言、兩套執行器，彼此不讀對方的檔；`kind=test` 一律進 Red 層。`e2e_check.py` 的判準修改與自我測試同屬 `tests/record/`（第一輪 p1 先例），由 r2a 一併做，且它在 Red 層就要綠。
- **r2c 文件先寫（D13 先例）**：CLI 表面 12 寫法的區塊與 R2 說明是 r2f、r2g 的契約；r2c 只相依 r2a（`test_docs.py`、`test_r2_docs.py` 要先存在），不讀 Swift 測試。
- **Core（r2d）獨立一層**：`Capture/` 與 `Trigger/` 都要用 §3.14 的新名稱；先把 Core 合進整合分支，r2e、r2f 才能各自在 worktree 編得過，並且平行。Core 單獨可驗（`Tests/run.sh` 只編 `Core/` 與測試）。不把 Core 併進 r2e 或 r2f：兩者都要用，併進任一個都會讓另一個等。
- **Capture（r2e）與 Trigger（r2f）分開、平行**：兩者只經 Core 名稱、狀態檔與控制檔相接（契約在 spec §3.9–§3.14）；檔案不重疊。`main.swift` 歸 r2f（SIGUSR1 忽略、`launchMode` 都是 dispatch 的事）；`Notifier.swift` 歸 r2e（錄製實例的完成通知識別碼），r2f 的可點通知在 `Trigger/` 內自建，不改 `Notifier.post` 的既有簽名。
- **偏好設定不另拆**：偏好設定視窗、登入項目、自動前處理開關都由 menu bar 程序開啟與讀寫 `menubar.prefs.json`，與 `MenuBar.swift` 的接線分不開；拆出去會讓兩個平行子任務互相等對方的型別才編得過。
- **r2g 一個子任務**：`record.sh`、`meeting.sh`、`_record_finalize.py` 都是 shell／Python、測試都在 r2a，與 Swift 只經檔案相接；三檔各自小幅修改，拆開沒有收益。
- **同層靜態檢查不跨界**（第一輪 §1 的教訓）：`test_r2_static.py` 的函式以 `test_capture_`（只掃 `Sources/Capture/`，r2e 轉綠）、`test_trigger_`（只掃 `Sources/Trigger/`，r2f 轉綠）、`test_main_`（只掃 `Sources/main.swift`，r2f 轉綠）開頭；`test_defaults_single_writer` 是守門檢查（掃全部 `Sources/`，Red 時就綠，任何子任務弄紅它都不得合併）。

### 9.2 各子任務要點

#### r2a 要點（tests/record/）
- **新增測試檔**（函式名照 spec §4.16–§4.24 的「測試」欄，逐字）：`test_r2_cli.py`、`test_r2_finalize.py`、`test_r2_e2e_check.py`、`test_r2_static.py`、`test_r2_docs.py`。全部在沒有 `record/` 的暫存工作目錄、`MH_RECORD_HOME`＝暫存目錄、`MH_RECORD_OPEN`＝替身下跑；不啟動真的 app、不產生任何媒體檔到 repo。
- **替身**：`fakes/fake_recorder.sh` 加 `FAKE_CONTROL`：`1`＝狀態檔含 `controlVersion` 1 與 `recordingStartedAt`，`trap` SIGUSR1 → 讀 `record.control.json`（`runId` 相符才採信）→ 依 `paused`／`micMuted`／`markerSeq` 更新狀態檔的 `paused`／`pausedAt`／`micMuted`／`markers`，並把收到 SIGUSR1 的次數記進 `<home>/fake_usr1.count`；`ignore`＝`trap '' USR1`、不更新；未設定＝第一輪行為（不裝 SIGUSR1 處理）。`FAKE_PHASE` 可指定狀態檔的 `phase`（preflight／stopping／finalizing）。既有情境的行為一字不改。
- **閘門 2 修正輪新增的其他 Python 測試**：`test_r2_cli.py::test_stop_summary_pause_markers`（§4.16.11；替身最終狀態要能帶 `markers`，場次 `tracks/record.meta.json` 由測試寫 `pauseEvents`）；`test_r2_static.py::test_capture_uses_core_pause_functions`（§4.18.2、§4.18.3 的實作形狀：`Sources/Capture/` 不得宣告 `enum SwitchReason`、`RecordingSession.swift` 含 §4.18.2／§4.18.3 列的 Core 名稱）；`test_capture_pause_gate_before_maxend` 改為檢查 `pauseRoute(` 在 `maxEnd =` 之前。
- **`EXIT_CODE_CASES`**（`test_record_sh.py`）：新增 10 筆（五個寫法 × 0／3）；0 用 `setup = "running_controllable"`（以 `FAKE_CONTROL=1` 啟動替身），3 用沒有錄製在跑。既有筆不動。
- **`e2e_check.py`**：依 spec §4.17.5、§4.17.6、§4.18.5–4.18.7、§4.19.4 修改與新增（`--pause-mute` 選項與 `pause_events`、`pause_cut`、`mic_mute_zero`、`mute_system_kept`、`no_false_silence`、`markers` 六項；`gap`、`segment_cadence`、`stop_tail`、`device_switch`、`hfp` 的暫停／靜音排除）；新增一個公開函式 `record_to_output(t, session)` 供混音軌量測換算（語意同 Core `outputTime`）。**閘門 2 修正輪**：`--pause-mute` 再加 `mute_timing`（§4.17.8）、`no_false_black`（§4.18.11）、`event_output_t`（§4.18.12），共九項，各有自我測試（`test_mute_timing_check`、`test_no_false_black_check`、`test_event_output_t_check`）。合成場次由 `_media.py` 現場產生（含麥克風軌數位 0 的段落、30 秒暫停邊界、`pauseEvents`、`micMuteEvents`、`markers.json`）。
- **§6 第 77 條核准的修改**（只改列出的斷言與常數，commit 內文寫「spec R2-§6 第 77 條，使用者核准的測試預期修改」）：`surface.py` 的 `SURFACE`；`test_surface_parsers.py:60-63`（§2.4.3 範例由該檔直接讀 spec，不用改）；`test_cli_dispatch.py:63-65`；`test_docs.py:16`、`:172`；`test_record_sh.py:24` 註解。
- **完成條件**：
  1. `python3 -m unittest tests.record.test_surface_parsers tests.record.test_e2e_check tests.record.test_r2_e2e_check` 全綠（`e2e_check.py` 是 r2a 自己的工具；既有 `test_e2e_check.py` 一字不改且全綠）；
  2. `python3 -m unittest discover -s tests/record -t . -k test_defaults_single_writer -k test_no_client_names_in_repo_text` 綠，後者不得 `skipped`；
  3. 全量 `python3 -m unittest discover -s tests/record -t .` 的失敗與錯誤只出現在 §9.3 表 Red 列「預期仍紅」的模組；輸出中不得出現 `ImportError`、`ModuleNotFoundError`、`SyntaxError`、`NameError`（紅燈原因必須是「功能不存在」：斷言不成立、結束碼不符、找不到字串）；
  4. `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。

#### r2b 要點（tools/MeetingRecorder/Tests/）
- 新增 `ControlTests.swift`（§4.16.1–4.16.3、4.16.10、§4.17.1、4.17.3、4.17.4、4.17.7、§4.18.1、4.18.8–4.18.10（§4.18.2、4.18.3 的 swift 欄指向這三條的同一組函式）、§4.19.1、§4.20.1；閘門 2 修正輪新增 `testAppendingMuteEvent`、`testPauseGateAndSwitchReason`、`testPauseEventsAndStatusFields`、`testDetectorFeed`）與 `MenuBarR2Tests.swift`（§4.20.2、4.20.3、4.20.5、4.20.7、§4.21.1、4.21.2、§4.22.1、4.22.3、§4.23.1），函式名照 spec 逐字；兩個 suite 登記進 `Tests/main.swift` 的 `mrtSuites`。測試狀態檔與事件一律用中性範例（場次名「[Stand-up] 範例專案」）。檔案 I/O 測試只用暫存目錄。
- 既有測試檔（`TriggerTests.swift`、`RecordsTests.swift` 等）一字不改；`Tests/main.swift` 只在 `mrtSuites` 加兩行登記。
- **完成條件**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 失敗，且 `error:` 行全部是「找不到 spec §3.14 列的名稱」類的編譯錯誤（`cannot find '…' in scope`、`has no member '…'`、`extra argument '…'`、`incorrect argument label`），每一行都提到 §3.14 的某個名稱；沒有其他種類的錯誤。

#### r2c 要點（文件）
- SKILL.md：R2 功能說明（spec §4.24.3 列的字樣）、四組快捷鍵、暫停會剪掉並記 `pauseEvents`、靜音只把麥克風變成無聲（系統聲音照錄）、`markers.json` 的位置與 `t` 是成品時間、選單新項目、偏好設定、登入項目要在系統設定允許、自動前處理預設關、舊版錄製器不支援控制、五個保留字的 `./` 寫法；`record-cli` 區塊照 spec §2.4.5 改成 12 列（兩份文件 begin／end 之間逐位元組相同）。只寫 spec 定案的行為（D13）；範例名稱用「[Stand-up] 範例專案」。
- README.md：錄製段同步 12 列區塊，並加一句 R2 摘要（含「⌃⌥⌘P」「麥克風靜音」「markers.json」）與一行指向 SKILL.md；不得引述 README 既有的任何真實名稱。
- **完成條件**：`python3 -m unittest tests.record.test_r2_docs` 全綠；`python3 -m unittest tests.record.test_docs -k test_skill_exists_and_sections -k test_readme_updated -k test_docs_cli_block_matches_spec -k test_meeting_tab_marking_documented -k test_shortcuts_instruction -k test_crash_loss_documented -k test_stage_manager_documented` 全綠；`-k test_no_client_names_in_repo_text` 綠且不得 `skipped`；verify 回 0。

#### r2d 要點（Core/）
- 照 spec §3.14 逐字實作名稱、簽名、預設值；`RecordStatus`／`RecordMeta`／`GapStats` 的新欄位一律 `var x: T? = nil`（合成的 memberwise init 不必改呼叫端；合成的 Codable 對 nil 省略鍵）；`RecentLevels`、`MenuBarPrefs` 自訂 `encode(to:)` 讓 nil 寫 null（沿用 `Records.swift` 既有寫法）。`MenuBarState` 加 `paused`、`symbol(for:)` 加一列；`menuBarModel` 依 §3.14.1 加 M6b 與 R2 欄位，第一輪各列的行為不變。`requestControl`／`resetControl` 用 `flock`（同 `acquireMenuBarLock` 的寫法）＋`writeJSONAtomically`。**閘門 2 修正輪**：`Segments.swift` 加 `SwitchReason`（含 `resume`）、`PauseGate`、`PauseSampleRoute`、`pausing`、`resuming`、`pauseRoute`、`segmentOpened`、`openReason`；`Control.swift` 加 `appendingPauseEvent`、`PauseStatusFields`、`pauseStatusFields`、`applyingPauseFields`、`appendingMuteEvent`；`Detectors.swift` 加 `DetectorFeed`、`detectorFeed`。Capture 原本的 private `SwitchReason` 會遮蔽 Core 的同名型別，所以 r2d 合併後既有 Capture 仍編得過；刪除是 r2e 的事。
- 不改 `Capture/`、`Trigger/`、`main.swift`（新增的 Optional 與 enum case 不會讓既有呼叫端編不過；若會，以 `needs_decision` 回報，不得順手改別人的檔）。
- **完成條件**：(1) `/bin/bash tools/MeetingRecorder/Tests/run.sh` 全綠（含第一輪全部 suite）；(2) `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 成功（既有的 Capture／Trigger 對新 Core 編得過）；(3) `python3 -m unittest discover -s tests/record -t . -k test_defaults_single_writer` 綠；(4) verify 回 0。

#### r2e 要點（Capture/）
- 照 design R2-D2–R2-D6：`installSignalHandlers` 加 SIGUSR1；`start()` 順序 `installSignalHandlers()` → `resetControl(` → 寫 `record.pid`；`phase` 轉 `recording` 時寫 R2 狀態欄位與 `pauseEvents`／`micMuteEvents` 空陣列；SIGUSR1 → `readControl` → `controlActions` → 套用（靜音、暫停／繼續、標記，順序：靜音 → 暫停／繼續 → 標記）；`ingest` 的暫停閘門在 `maxEnd` 更新之前；`SwitchReason` 加 `resume`；mic 回呼在 `rmsDBFS` 之前歸零；`closeLevels` 暫停中不餵偵測器、靜音中不餵 `micSilence`、每秒最多寫一次 `recentLevels`；繼續與取消靜音時重設偵測器；標記寫 `tracks/markers.json`；完成通知以 `completionNotificationID(runId:)` 為識別碼（`Notifier.post` 加 `identifier: String? = nil` 參數，既有呼叫端不改）。
- **閘門 2 修正輪**：刪掉 `RecordingSession.swift:28` 的 private `SwitchReason`，改用 Core 的；`ingest` 先算 `pauseRoute(`（在 `maxEnd =` 之前），prevOnly／drop 不更新 `maxEnd`，開段原因一律由 `openReason(` 決定（定期與格式變更換段的既有判斷不動），開段後 `segmentOpened(`；暫停／繼續以 `pausing(`／`resuming(` 轉移；事件與狀態欄位一律經 `appendingPauseEvent(`、`pauseStatusFields(`、`applyingPauseFields(`、`appendingMuteEvent(`；偵測器餵送依 `detectorFeed(`（`closeLevels` 與影格處理兩處）。
- 不改 `Core/`、`Trigger/`、`main.swift`。
- **完成條件**：(1) `run.sh` 全綠；(2) `python3 -m unittest discover -s tests/record -t . -k test_capture_` 全綠（含 `test_capture_uses_core_pause_functions`），`tests.record.test_static_rules` 全綠；(3) 以 `MH_RECORDER_DEST=$(mktemp -d)` 建 app 成功，`codesign -d --entitlements - <app>` 仍恰為兩項（§4.2.8 不變）；**不得覆蓋** `~/Applications/MeetingRecorder.app`、不得啟動 app；(4) verify 回 0。

#### r2f 要點（Trigger/、main.swift、Resources/、build.sh）
- 照 design R2-D7–R2-D10：status item 變寬與計時、四態圖示與紅點、`mic.slash`、收音指示列、§4.20.6 的選單與快速鍵、`HotKey` 多組（建構子加 `id:` 參數，handler 比對 id）、`TriggerDebouncer`、控制送出（`controlAvailability` → `requestControl` → `kill(pid, SIGUSR1)`）、「錄這個視窗 ▸」（`open -n -a … windows --json --log`）、「存到 ▸」（`NSOpenPanel`、`menubar.prefs.json`）、quick-start 的 `--window`／`--root`（`explicitWindowDecision`、`quickStartRoot`、`resolveWindow`）、`Preferences.swift`（設定視窗、`SMAppService.mainApp` 只在勾選動作內 `register()`／`unregister()`）、完成通知 category 與 delegate、「顯示上一場成品」、自動前處理（`shouldAutoPrep`、`terminationHandler`、`autoprep.log`、排隊）；`main.swift` 在 `switch` 前 `signal(SIGUSR1, SIG_IGN)`、以 `launchMode(arguments:)` 分派。`Info.plist` 與 entitlements 原則上不改（`SMAppService`、`NSOpenPanel`、通知在非 sandbox app 不需要新 entitlement，`cc:` §3）；若實作發現需要，以 `needs_decision` 回報，不自行加。
- 不改 `Core/`、`Capture/`。文件是契約：`--args` 子指令與行為以 r2c 的 SKILL.md 為準，不一致改程式不改文件。
- **完成條件**：(1) `run.sh` 全綠；(2) `python3 -m unittest discover -s tests/record -t . -k test_trigger_ -k test_main_` 全綠，`tests.record.test_static_rules` 全綠，`python3 -m unittest tests.record.test_docs -k test_docs_app_args_exist_in_sources` 綠；(3) 以 `MH_RECORDER_DEST=$(mktemp -d)` 建 app 成功、entitlements 仍恰為兩項；**不得**覆蓋或啟動 app、不得註冊登入項目、不得觸發 TCC 授權框；(4) verify 回 0。

#### r2g 要點（bin/）
- `record.sh`：`*)` 之前加 `pause|resume|mute|unmute|mark`，共用 `cmd_control`（`check_unknown "" ""`、多餘參數回 2、同一段 Python 做 `controlAvailability` 同語意的前提檢查、`fcntl.flock` 取 `record.control.lock`、`requestControl` 同語意的寫入、`kill -USR1 <record.pid>`、最多 5 秒輪詢狀態反映）；`usage_help` 照更新後的 §2.4.3（12 行寫法、說明段加保留字的 `./` 寫法）；`cmd_status` 照 §4.16.9、`stop_summary` 照 §4.16.11（閘門 2 修正輪補的驗收；第一輪的摘要行不動）。`meeting.sh`：`usage()` 照 §2.4.6 改 12 行（`record_cmd` 不改）。`_record_finalize.py`：照 design R2-D12（`markers.json` 複製在 `already_done` 之前、`gapStats` 扣暫停、`pausedTotal`）。不新增 `bin/` 檔；`$VAR` 緊接全形字與雙引號內反引號兩個坑照 `_lint.sh` 守。
- **完成條件**：(1) `python3 -m unittest tests.record.test_r2_cli tests.record.test_r2_finalize tests.record.test_record_sh tests.record.test_cli_dispatch tests.record.test_docs tests.record.test_finalize tests.record.test_concurrency tests.record.test_regression` 全綠（`test_docs` 依賴第 1 層已合併的 r2c 文件）；(2) `bash bin/_lint.sh` 通過且檔數 26；(3) verify 回 0。

#### r2t7 要點（test 段，使用者在場）
- 順序：(1) 主 session 先問使用者是否以新版覆蓋 `~/Applications/MeetingRecorder.app`（不可代為決定），覆蓋後由使用者重開 menu bar；(2) spec §4.25.1 劇本＋`e2e_check.py --segment-writer --pause-mute --status …`（`--pause-mute` 九項，含閘門 2 修正輪新增的 `mute_timing`、`no_false_black`、`event_output_t`）；(3) §4.25.2 選單與截圖（淺色、深色）；(4) §4.25.3 選視窗、換位置；(5) §4.25.4 偏好設定、登入自動開（使用者自己登出再登入）、自動前處理、通知動作；(6) §4.25.5 第一輪剩下的實機項目；(7) test 段平行派 `dev-design-reviewer`（`has_ui=true`，§6 第 92 條）。結果寫 run 目錄，截圖不進 repo（§4.14.1）。

**design commit 之後、Red 層合併之前的已知紅燈**：spec §2.4 已就地更新為 12 寫法，而 `tests/record/surface.py` 的 `SURFACE` 要到 r2a 才更新，所以這段期間 `test_surface_parsers.py::test_parse_help_accepts_spec_example` 在 `feature/meeting-record` 上是紅的（spec 先行，屬預期）；Red 層合併後必須轉綠（§9.3 Red 列）。

### 9.3 每層整合後的測試指令（integrator 照此跑，一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red（r2a＋r2b） | `python3 -m unittest tests.record.test_surface_parsers tests.record.test_e2e_check tests.record.test_r2_e2e_check`；`python3 -m unittest discover -s tests/record -t . -k test_defaults_single_writer -k test_no_client_names_in_repo_text`（後者不得 `skipped`）；`bash bin/_lint.sh && bash bin/meeting.sh doctor` | 全量 Python：失敗只在 `test_r2_cli`、`test_r2_finalize`、`test_r2_static`（`test_defaults_single_writer` 除外）、`test_r2_docs`、`test_docs`、`test_cli_dispatch`、`test_record_sh`；`run.sh`（只因缺 §3.14 名稱而編譯失敗） |
| 第 1 層（r2c＋r2d） | `/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest tests.record.test_r2_docs tests.record.test_surface_parsers tests.record.test_e2e_check tests.record.test_r2_e2e_check`；`python3 -m unittest discover -s tests/record -t . -k test_defaults_single_writer -k test_no_client_names_in_repo_text`（不得 `skipped`）；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；verify | 全量 Python：失敗只在 `test_r2_cli`、`test_r2_finalize`、`test_r2_static`、`test_docs` 的程式側三支（`test_docs_cli_block_matches_help`、`test_docs_flags_match_behavior`、`test_docs_exit_codes_match_behavior`）、`test_cli_dispatch`、`test_record_sh` |
| 第 2 層（r2e＋r2f＋r2g） | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names_in_repo_text`（不得 `skipped`）；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 並以 `codesign -d --entitlements -` 確認恰為兩項；`python3 .claude/teams/tools/check_rules.py --git . meeting-record-r1-baseline..feature/meeting-record`；verify | 無；任何一支不綠就停下交人 |

### 9.4 不屬於任何子任務、需要主 session 或使用者做的事（R2）

| 事項 | 時點 | 理由 |
|---|---|---|
| 以 `save_run.py approve` 記 `r2-design` 核准 | 使用者核准本輪 spec＋plan 後 | R2-Q2 使用者決定；不覆寫第一輪的 `design` 鍵 |
| 維護 `progress.md` 的 R2 節 | 每層合併後、每個閘門後 | 同第一輪 §4 |
| 覆蓋安裝 `~/Applications/MeetingRecorder.app` | r2t7 開始前 | 會改使用者的 app，要使用者當下同意 |
| 登入項目、通知權限、快捷鍵、選單互動的實機操作與截圖 | r2t7 | 派工約束：agent 不得啟動 app、不得改系統設定 |
| R2 的拆包（§9.5）與推送前客戶名稱掃描 | deliver 段 | 照 §9.5 與 §5.1；推送與開 PR 要使用者當下同意 |

### 9.5 拆 PR 規劃（R2；修改既有檔超過 15 個，閘門 2 修正輪補寫）

R2 相對 `meeting-record-r1-baseline` 預計**修改既有檔**（新增檔不計）：
- 錄製器 app：`Core/Records.swift`、`Detectors.swift`、`AudioLevel.swift`、`Trigger.swift`、`Segments.swift`；`Capture/RecordingSession.swift`、`PreflightRunner.swift`、`Notifier.swift`；`Trigger/MenuBar.swift`、`HotKey.swift`、`QuickStart.swift`；`Sources/main.swift`；`Tests/main.swift`＝**13**（`build.sh`、`Resources/` 原則上不改；若經核准要改，最多 15）。
- CLI、finalize、測試、文件、specs：`bin/record.sh`、`bin/meeting.sh`、`bin/_record_finalize.py`；`.claude/skills/meeting-record/SKILL.md`、`README.md`；`tests/record/surface.py`、`test_surface_parsers.py`、`test_cli_dispatch.py`、`test_docs.py`、`test_record_sh.py`、`e2e_check.py`、`fakes/fake_recorder.sh`、`_media.py`（`_helpers.py`／`_fixtures.py` 視需要再 +2）；`specs/meeting-record/` 的 `intent.md`、`design.md`、`spec.md`、`plan.md`、`progress.md`＝**18–20**。
- 合計 31–35 個，超過 `rules.md`〈專案規則〉審查規則的 15 檔門檻。R2 排在第一輪三包（§5）之後，分兩包，**合併順序 R2-1 → R2-2**：

| 包 | 內容 | 範圍（依檔案揀 commit） | 修改既有檔 |
|---|---|---|---|
| R2-1 | 錄製器 app（Swift） | r2b、r2d、r2e、r2f 的 commit（`tools/MeetingRecorder/`） | 13（≤ 15） |
| R2-2 | CLI、finalize、Python 測試與 e2e 工具、文件、specs | R2 的 specs commit（intent、design、spec、plan、progress、ADR，含本修正輪）＋ r2a、r2c、r2g 的 commit；主 session 更新 `progress.md` 的 commit 也歸這包 | 18–20（PR 說明標 important） |

**理由**：
- **R2-1 先合**：R2-2 的 CLI 寫法要錄製器有 `controlVersion` 才能控制（§4.16.3）、`test_r2_static.py` 掃 R2-1 的 `Sources/`、SKILL.md 描述 R2-1 的 menu bar 行為——都是執行期或檢查期依賴 R2-1。R2-1 單獨進 `main` 時：既有 7 個 CLI 寫法與結束碼不變，舊 `record.sh` 照常開錄（新 app 只是多寫選用欄位、多聽 SIGUSR1，§3.10 nil 省略鍵讓舊讀者不受影響），menu bar 的新功能自成一體，不會讓其他 session 看到半套的對外介面（`CLAUDE.md`〈對外介面〉）。
- **R2-2 不再細拆**：spec §2.4（封閉清單）、`surface.py`、`test_surface_parsers.py`（直接讀 spec 的 §2.4.3 範例）、`record.sh` 的 help、`meeting.sh` 的 usage、SKILL.md／README 的 `record-cli` 區塊互相一致性檢查（§4.24.1、§4.24.2；第一輪 §5「t5 與 t4、t1 必須同一包」同一理由）；拆開時先合的那包在 `main` 上一定有紅燈。specs 放 R2-2 而不是 R2-1，也是因為 spec §2.4 已更新而 `surface.py` 在 R2-2，放 R2-1 會讓 `test_parse_help_accepts_spec_example` 在兩包之間紅。
- **代價**：R2-1 審查時 spec 還不在 `main`，PR 說明要附 `feature/meeting-record` 上 `specs/meeting-record/spec.md` R2 節的連結（推送後才有）；R2-1 的 Capture／Trigger 靜態檢查（`test_r2_static.py`）在 R2-2 才進 `main`，R2-2 合併前在整合分支全量跑時一併驗。若要少一次 PR，可兩包合一（31–35 檔，標 important），本 plan 預設分開。
- **做法**：分支 `feature/meeting-record-r2-app`（從已含第一輪三包的 `main` 開出，揀 r2b、r2d、r2e、r2f）、`feature/meeting-record-r2-cli`（從 R2-1 開出，揀 specs 與 r2a、r2c、r2g）；子任務的 `owns` 不重疊，依檔案範圍揀 commit 不會衝突。每包推送前照 §5.1 做客戶名稱掃描（範圍加上這兩個分支）。推送與開 PR 都是不可逆節點，由使用者當下同意後主 session 執行；本規劃不構成同意。

## 10. R3 第三輪（2026-10-13）：錄製穩定、逐字稿源頭、狀態可見、UI 重設計、會前會後、影音一致

- 上游：`intent.md`〈R3 第三輪〉（閘門 1 已核准）、`design.md`〈R3 第三輪設計〉、`spec.md`〈R3 第三輪〉（§3.15–§3.20、§4.26–§4.47、§6 第 117–135 條）；選定設計稿 `design-r3/`（`README.md`＋原始稿）。
- epic 分支 `feature/meeting-record-r3`（worktree `.worktrees/meeting-record-r3`）；子任務分支 `feature/meeting-record-r3--<id>`、worktree `.worktrees/meeting-record-r3--<id>`（`sdlc-build` 的命名）。`<id>` 是描述性 slug，**不是任務編號**。
- 大小只寫相對大小 S／M／L（`.claude/teams/rules.md:23`，不寫人天、工時）。
- 分層由 `depends_on` 機械算出（`sdlc-build`：test 子任務先在 Red 平行做完；其餘每層取「相依都已完成」的子任務）。**同一層的 `owns` 不重疊**；改同一支檔的子任務一律以 `depends_on` 串成序列鏈（`design.md` R3-D1）。
- 與 intent R3-8 的差異（理由見 `design.md` R3-D1）：新增 `r3-core`（Swift 測試執行器全編全過的限制）與 `r3-docs`（文件先寫）；`r3-lock`、`r3-menubar-states` 因依賴 `r3-core` 移到第 2 層；`SegmentScheduler` 的純狀態機併入 `r3-core`，`r3-segment-scheduler` 只做接線。
- **UI 子任務的外觀依據**（2026-10-13 稿已選定，`design.md` R3-D21）：`spec.md` 的外觀條文（§4.38.3、§4.38.5–§4.38.8、§4.40.4、§4.40.7–§4.40.8、§4.41.2–§4.41.5、§4.41.7、§4.42.2、§4.43.5–§4.43.7、§4.43.9、§4.44.3）與 `design-r3/README.md`。設計 token 與膠囊樣式表是 Core 常數（`r3-core` 做、`R3DesignTokenTests` 驗）；AppKit 子任務只畫，不得自訂色值、字級、尺寸或字面。

### 10.1 子任務與分層

| 層 | id | kind | 標題 | 擁有（只能改） | 相依 | 對應 spec | 大小 |
|---|---|---|---|---|---|---|---|
| Red | `r3-red-py` | test | Python 紅燈測試、共用向量、替身、§6 核准的既有測試修改（含第 129、130、134 條） | `tests/record/test_r3_*.py`（新）、`tests/record/vectors/`（新）、`tests/record/fakes/`（只加）、`tests/record/_media.py`、`_helpers.py`、`_fixtures.py`（只加）、`surface.py`、§6 第 117、118、120、121、122、123、125 條列的既有測試檔（`test_surface_parsers.py`、`test_cli_dispatch.py`、`test_docs.py`、`test_record_sh.py`、`test_r2_static.py`、`test_t7_fixes.py`、`test_regression.py`） | — | §4.26–§4.46 的 Python 測試欄；§6 第 117–125、129、130、134 條 | L |
| Red | `r3-red-swift` | test | Swift 紅燈測試 | `tools/MeetingRecorder/Tests/R3LockTests.swift`、`R3MenuBarTests.swift`、`R3SegmentSchedulerTests.swift`、`R3SyncTests.swift`、`R3RecordLibVectorTests.swift`、`R3DesignTokenTests.swift`（新）、`Tests/main.swift`（`mrtSuites` 登記）、`Tests/ControlTests.swift`（§6 第 127 條） | — | §3.20；§4.26–§4.44 的 `swift:` 測試欄 | M |
| 1 | `r3-core` | code | R3 全部 Core 純函式與型別（含 `DesignTokens.swift`） | `tools/MeetingRecorder/Sources/Core/` | — | §3.20；§4.26.1、§4.27.1、§4.28.5、§4.32.1–2（Swift）、§4.35.5–6、§4.36.1–9、§4.38.1–2、§4.38.5–8、§4.39.1–2、§4.40.1–3、§4.40.6、§4.41.1–2、§4.41.4（`levelFraction`）、§4.41.7、§4.42.1、§4.42.5、§4.43.1、§4.43.4、§4.43.6（`SettingsTab`）、§4.44.1 | L |
| 1 | `r3-vtt-raw` | code | T1 VTT 同一套歸屬、T2 不刪 raw、T3 拿掉無效參數 | `bin/_render.py`、`bin/_merge_speakers.py`、`bin/meeting.sh`、`bin/transcribe.sh`、`.claude/skills/meeting-transcribe/SKILL.md` | — | §4.29.1–4 | M |
| 1 | `r3-record-lib` | code | `bin/_record_lib.py`（Q9a） | `bin/_record_lib.py`（新） | — | §3.19（clip CLI）、§4.32.1–4 | S–M |
| 1 | `r3-finalize-guard` | code | 收尾鎖、mkstemp、逐步逾時、unreadable、耗時 log | `bin/_record_finalize.py` | — | §4.28.1–4、§4.28.7–8；§6 第 126、132 條 | M |
| 1 | `r3-sync-measure` | code | S-A：`--sync-acoustic`、`--sync-player`、`--print-sync-file` | `tests/record/e2e_check.py` | — | §4.35.1–4；§6 第 124 條 | S |
| 1 | `r3-docs` | doc | README 與 meeting-record SKILL.md（CLI 區塊 13 寫法、R3 行為說明） | `README.md`、`.claude/skills/meeting-record/SKILL.md` | — | §4.34.4、§4.42.6、§4.45.1（文件側）、§4.45.3（meeting-record 部分）、§4.46.4 | S |
| 2 | `r3-lock` | code | 開錄鎖、preflight 互斥、心跳、`stop` 四項確認、`write_defaults` 合併、`record sync` | `bin/record.sh`、`tools/MeetingRecorder/Sources/Capture/Commands.swift`、`Capture/PreflightRunner.swift`、`Capture/RecordingSession.swift` | `r3-core` | §4.26.2–7、§4.27.2–3、§4.37.1、§4.43.2–3、§4.45.1–2（`record.sh help` 側）；§6 第 117（程式側）、119 條 | L |
| 2 | `r3-menubar-states` | code | U1 錄製膠囊 8 種（自繪）、VoiceOver 字面、Q5 的 menu bar 停止確認、`autosaveName` | `tools/MeetingRecorder/Sources/Trigger/MenuBar.swift` | `r3-core` | §4.27.4、§4.38.1–4、§4.38.7（接線）；§6 第 128、129、135 條 | S–M |
| 2 | `r3-search` | code | F1 `meeting search`；`usage()` 加 `record sync` 與 `./sync` 說明 | `bin/meeting.sh`、`bin/_search.py`（新） | `r3-vtt-raw` | §4.33.1–4、§4.45.1（`usage()` 側） | S |
| 2 | `r3-transcript-vad` | code | T4 VAD clip、T5 品質檔與 `segments.json` 一律輸出 | `bin/transcribe.sh`、`.claude/skills/meeting-transcribe/SKILL.md` | `r3-record-lib`、`r3-vtt-raw` | §4.30.1–5、§4.45.3（meeting-transcribe 部分） | L |
| 2 | `r3-annotations` | code | T6 標示、T7 標記、T5 的「（聽不清）」、schema `markers[]`、summary 兩段 | `bin/_render.py`、`bin/_merge_speakers.py`、`schema/meeting-record.v1.json`、`.claude/skills/meeting-notes/SKILL.md` | `r3-record-lib`、`r3-vtt-raw` | §4.30.6、§4.31.1–8、§4.45.3（meeting-notes 部分）；§6 第 122 條 | L |
| 3 | `r3-finalize-runner` | code | Q3 Swift 端：總期限、取消、SIGTERM→SIGKILL | `Capture/RecordingSession.swift`、`Capture/FinalizeRunner.swift`（新） | `r3-lock`、`r3-finalize-guard` | §4.28.6 | M |
| 3 | `r3-notify` | code | U3 通知分級、thread、新告警通知；`discarded` 不自動前處理的接線 | `Capture/Notifier.swift`、`Trigger/MenuBar.swift`、`Trigger/Completion.swift` | `r3-menubar-states` | §4.39.3–4 | S |
| 3 | `r3-reminders` | code | F5：`meeting reminders`、`_reminders.py`、app `reminders` 子指令、EventKit | `bin/meeting.sh`、`bin/_reminders.py`（新）、`Capture/Reminders.swift`（新）、`Sources/main.swift`、`Resources/Info.plist` | `r3-search`、`r3-core` | §3.19、§4.34.1–3；§6 第 125 條（第 29 個檔） | M |
| 4 | `r3-latency-log` | code | S-B：輸出延遲唯讀記錄 | `Capture/RecordingSession.swift`、`Capture/AudioDeviceMonitor.swift` | `r3-finalize-runner` | §4.35.7 | S |
| 4 | `r3-hud` | code | U2 HUD（螢幕邊緣標籤、滑過展開、告警加強）、快捷鍵回饋路徑、持續的遮擋偵測 | `Trigger/MenuBar.swift`、`Trigger/HUD.swift`（新） | `r3-notify`、`r3-lock` | §4.40.4–5、§4.40.7–8；§6 第 120、121 條 | M |
| 5 | `r3-discard` | code | F2 捨棄：確認框（預設「繼續錄製」）、請求檔、跳過收尾、移到垃圾桶 | `Capture/RecordingSession.swift`、`Trigger/MenuBar.swift`、`Trigger/Discard.swift`（新） | `r3-latency-log`、`r3-hud`、`r3-finalize-runner` | §4.42.2–4 | M |
| 6 | `r3-menu-stages` | code | U6 依階段選單（分組、新字面、告警列、顯示錄製小窗）、音量條、失敗詳情、取消收尾 | `Trigger/MenuBar.swift`、`Trigger/FailureDetail.swift`（新）、`Trigger/LevelMeterView.swift`（新） | `r3-discard` | §4.41.3–7；§6 第 118、134 條 | M |
| 6 | `r3-segment-scheduler` | code | Q6：`RecordingSession` 改由 `SegmentScheduler` 驅動、輸出裝置變更事件 | `Capture/RecordingSession.swift` | `r3-discard` | §4.36.10 | L |
| 7 | `r3-onboarding-settings` | code | U4 首次引導 5 步（含 defaults 兩鍵）、U5 設定 7 分頁（含 HUD 與 F3 開關）、U7 app 圖示、字型不打包 | `Trigger/Preferences.swift`、`Trigger/Onboarding.swift`（新）、`Trigger/MenuBar.swift`、`Resources/Info.plist`、`Resources/AppIcon.icns`（新）、`tools/MeetingRecorder/build.sh` | `r3-menu-stages`、`r3-notify`、`r3-reminders` | §4.43.5–9、§4.44.4；§6 第 123、130 條 | L |
| 7 | `r3-sync-compensate` | code | S-C：mode 解析、依時段延遲混音、`finalize.json` 記錄、提前換段、`--sync-player` 讀補償 | `bin/_record_finalize.py`、`Capture/RecordingSession.swift`、`tests/record/e2e_check.py` | `r3-segment-scheduler`、`r3-latency-log`、`r3-sync-measure`、`r3-finalize-guard`、`r3-record-lib`、`r3-lock` | §4.37.2–8 | M |
| 8 | `r3-meeting-detect` | code | F3 會議偵測提示 | `Trigger/MeetingDetect.swift`（新）、`Trigger/MenuBar.swift`、`Capture/Notifier.swift` | `r3-onboarding-settings`、`r3-notify`、`r3-lock` | §4.44.2–3 | M |

（表中 `Capture/`、`Trigger/`、`Resources/`、`Sources/main.swift` 都在 `tools/MeetingRecorder/` 底下。）

**序列鏈檢查**（同檔的子任務都有相依路徑，不會同層）：`RecordingSession.swift`＝lock(2) → finalize-runner(3) → latency-log(4) → discard(5) → segment-scheduler(6) → sync-compensate(7)；`MenuBar.swift`＝menubar-states(2) → notify(3) → hud(4) → discard(5) → menu-stages(6) → onboarding-settings(7) → meeting-detect(8)；`_record_finalize.py`＝finalize-guard(1) → sync-compensate(7)；`e2e_check.py`＝sync-measure(1) → sync-compensate(7)；`_render.py`／`_merge_speakers.py`＝vtt-raw(1) → annotations(2)；`meeting.sh`＝vtt-raw(1) → search(2) → reminders(3)；`transcribe.sh`、meeting-transcribe SKILL.md＝vtt-raw(1) → transcript-vad(2)；`Notifier.swift`＝notify(3) → meeting-detect(8)；`Info.plist`＝reminders(3) → onboarding-settings(7)。

**拆分理由（能一個做完的不拆兩個）**：`r3-core` 不拆，因為 Swift 測試全編全過；`r3-lock` 把 Q1、Q2、Q5、D14b、R3-Q5、`record sync` 合在一起，因為都改 `record.sh` 與同一組鎖；`r3-annotations` 吸收 T5 的「（聽不清）」，因為同改 `_render.py`／`_merge_speakers.py`；`r3-onboarding-settings` 合併 U4、U5、U7，因為同改 `Info.plist`、`MenuBar.swift` 且共用設定檔。`r3-latency-log` 與 `r3-sync-compensate` 分開，因為 S-B 只讀、可以先上線量資料，S-C 要等 Scheduler 與量測。

### 10.2 各子任務要點與完成條件（可機械判定）

共通：只改 `owns`；不改 `progress.md`；verify（`bash bin/_lint.sh && bash bin/meeting.sh doctor`）全綠才 commit；commit 訊息 `test(<Story>)`／`feat(<Story>)`／`docs(<Story>)`，scope 用 `meeting-record`，結尾署名行；commit 前照 intent R3-4 第 8 點掃名稱（只回報有／沒有）。測試指令一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=<run 目錄>/client-names.txt`。

- **r3-red-py**：(1) spec §4.26–§4.46 測試欄列的 Python 測試函式與類別都存在（逐字）；(2) `python3 -m unittest discover -s tests/record -t .` 的輸出沒有 `ImportError`、`ModuleNotFoundError`、`SyntaxError`、`NameError`；(3) 失敗只出現在 §10.3「Red」列允許的測試；(4) §6 第 117–125、129、130、134 條的既有測試修改只動列出的斷言（`git diff` 只碰那些行；`test_static_rules.py`、`test_r2_docs.py` 不改），commit 內文寫條號；(5) `tests/record/vectors/*.json` 存在且是合法 JSON；(6) 新增的 fixture、向量、替身不得含真實名稱（`test_r3_docs.py::test_no_client_names_in_r3_files` 綠、不得 skipped）。
- **r3-red-swift**：(1) 六支 `R3*Tests.swift`（含 `R3DesignTokenTests.swift`，§4.38.5–§4.38.8、§4.41.4 的 `levelFraction`、§4.43.6 的 `SettingsTab`）存在並登記在 `mrtSuites`；(2) `run.sh` 只因缺 §3.20 名稱而編譯失敗（錯誤訊息都是 `cannot find … in scope` 類）；(3) `ControlTests.swift` 只改 §6 第 127 條那兩處。`R3RecordLibVectorTests` 讀 `r3-red-py` 寫的 `tests/record/vectors/`（同在 Red 層平行做，兩者先照 spec §4.32 的檔名與欄位寫，Red 層整合後才一起可跑）。
- **r3-core**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 全綠（含既有 `TriggerTests`、`MenuBarR2Tests`、`RecordsTests` 不改；`R3DesignTokenTests` 綠）；§3.20 的名稱與簽名逐字存在（含 `DesignTokens.swift` 的 34 個色 token 與表列值）；Core 不得 import AppKit。
- **r3-vtt-raw**：`python3 -m unittest tests.record.test_r3_vtt_raw` 綠；既有 `test_prompt`、`test_regression`（§6 第 122 條後）綠。
- **r3-record-lib**：`python3 -m unittest tests.record.test_r3_record_lib` 綠；`bash bin/_lint.sh` 檔數 27。
- **r3-finalize-guard**：`python3 -m unittest tests.record.test_r3_finalize_guard tests.record.test_finalize tests.record.test_r2_finalize` 綠。
- **r3-sync-measure**：`python3 -m unittest tests.record.test_r3_sync_measure tests.record.test_e2e_check tests.record.test_r2_e2e_check` 綠（後兩者一字不改）。
- **r3-docs**：`python3 -m unittest tests.record.test_r3_docs` 綠；`test_docs.py::test_docs_cli_block_matches_spec` 綠；`test_r2_docs` 綠（不改；選單新名稱與 R2 舊稱並列，§6 第 134 條）。
- **r3-lock**：`python3 -m unittest tests.record.test_r3_lock tests.record.test_record_sh tests.record.test_r2_cli tests.record.test_concurrency` 綠；`test_r3_app_static.LockStatic` 綠；`run.sh` 綠；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 成功。
- **r3-menubar-states**：`test_r3_app_static.MenuBarStatesStatic` 綠（含 `test_capsule_drawing`）；`test_r2_static.test_trigger_status_item_variable_length` 綠（§6 第 129 條後）；`test_static_rules.test_menubar_uses_template_image`、`::test_start_item_shows_hotkey`、`::test_menubar_sets_accessibility_label` 綠（不改）；`grep -c systemRed tools/MeetingRecorder/Sources/Trigger/MenuBar.swift` 為 0；`run.sh` 綠；建置成功。
- **r3-search**：`python3 -m unittest tests.record.test_r3_search tests.record.test_cli_dispatch` 綠；`bash bin/_lint.sh` 檔數 28。
- **r3-transcript-vad**：`python3 -m unittest tests.record.test_r3_transcript_vad` 綠；既有轉錄相關測試綠。
- **r3-annotations**：`python3 -m unittest tests.record.test_r3_annotations` 綠（`test_downstream_missing_sections` 不得 skipped；下游專案只讀）；既有 `test_regression` 綠。
- **r3-finalize-runner**：`test_r3_app_static.FinalizeRunnerStatic` 綠；`run.sh` 綠；建置成功。
- **r3-notify**：`test_r3_app_static.NotifyStatic` 綠；建置後 `codesign -d --entitlements -` 恰為兩項。
- **r3-reminders**：`python3 -m unittest tests.record.test_r3_reminders` 綠、`test_r3_app_static.RemindersStatic` 綠；`bash bin/_lint.sh` 檔數 29、`test_regression.test_lint_passes_26_files` 綠；開工前先確認 §7 疑慮 45 的 plist 鍵名。
- **r3-latency-log**：`test_r3_app_static.LatencyLogStatic` 綠；`test_static_rules.py::test_no_default_device_write_in_sources` 綠。
- **r3-hud**：`test_r3_app_static.HudStatic` 綠（`test_panel_shape`、`test_edge_tab`、`test_alert_emphasis`、`test_accessibility_modes`、`test_feedback_route_used`）；`test_t7_fixes` 綠（§6 第 120、121 條後）；`HUD.swift` 沒有 `systemRed`。
- **r3-discard**：`test_r3_app_static.DiscardStatic` 綠（`test_confirm_then_request` 驗 §4.42.2 的四段字面與按鈕順序）；Swift 原始碼對場次路徑沒有 `removeItem(`。
- **r3-menu-stages**：`test_r3_app_static.MenuStagesStatic` 綠（含 `test_titles_r3`）；`test_r2_static.test_trigger_menu_items_r2` 綠（§6 第 118、134 條後）；`test_static_rules.test_start_item_shows_hotkey`、`::test_status_title_uses_label_color` 綠（不改）。
- **r3-segment-scheduler**：`test_r3_app_static.SegmentSchedulerStatic` 綠；`run.sh` 綠；`python3 -m unittest tests.record.test_static_rules tests.record.test_review_fixes` 綠（既有的段落靜態檢查不得因搬移而失敗，失敗就改程式）。
- **r3-onboarding-settings**：`test_r3_app_static.OnboardingSettingsStatic` 綠（含 `test_no_bundled_fonts`）；`test_r2_static` 全部綠（§6 第 123、130 條後）；建置後 bundle 內有 `AppIcon.icns`、`iconutil --convert iconset` 展開恰 10 張（§4.43.7）、entitlements 恰為兩項。
- **r3-sync-compensate**：`python3 -m unittest tests.record.test_r3_sync_compensate` 綠、`test_r3_app_static.SyncCompensateStatic` 綠；`test_finalize`、`test_r2_finalize`、`test_e2e_check`、`test_r2_e2e_check` 綠。
- **r3-meeting-detect**：`test_r3_app_static.MeetingDetectStatic` 綠（字面「錄這個會議？」「開始錄製」「這場不用」）；全量 Python 與 Swift 綠。

### 10.3 每層整合後的測試指令（integrator 照此跑，一律加 `TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt`）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red | `bash bin/_lint.sh && bash bin/meeting.sh doctor`；`python3 -m unittest tests.record.test_e2e_check tests.record.test_r2_e2e_check tests.record.test_finalize` | 全量 Python：失敗只在 `test_r3_*`（全部）、`test_surface_parsers`、`test_cli_dispatch`、`test_docs`、`test_record_sh`（§6 第 117 條）、`test_r2_static` 的 `test_trigger_menu_items_r2`、`test_defaults_single_writer`、`test_trigger_status_item_variable_length`、`test_trigger_preferences_window`（§6 第 129、130 條）、`test_t7_fixes` 的兩支（§6 第 120、121 條）、`test_regression.test_lint_passes_26_files`；`run.sh`（只因缺 §3.20 名稱） |
| 第 1 層 | `/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest tests.record.test_r3_vtt_raw tests.record.test_r3_record_lib tests.record.test_r3_finalize_guard tests.record.test_r3_sync_measure tests.record.test_r3_docs`；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；verify | 全量 Python：失敗只在第 2 層以後子任務的 `test_r3_*` 與 `test_r3_app_static` 各類別、`test_cli_dispatch`（`usage()`）、`test_record_sh`（`sync`）、`test_docs` 的程式側三支、`test_surface_parsers` 的 help 比對、上一列的 `test_r2_static`、`test_t7_fixes`、`test_regression.test_lint_passes_26_files` |
| 第 2 層 | 上一層全部；`python3 -m unittest tests.record.test_r3_lock tests.record.test_r3_search tests.record.test_r3_transcript_vad tests.record.test_r3_annotations tests.record.test_surface_parsers tests.record.test_cli_dispatch tests.record.test_docs tests.record.test_record_sh`；`python3 -m unittest tests.record.test_r3_app_static.LockStatic tests.record.test_r3_app_static.MenuBarStatesStatic tests.record.test_r2_static.TestR2Static.test_trigger_status_item_variable_length tests.record.test_static_rules` | `test_r3_reminders`、`test_r3_sync_compensate`、`test_r3_app_static` 其餘類別、`test_r2_static` 三支（`menu_items_r2`、`defaults_single_writer`、`preferences_window`）、`test_t7_fixes` 兩支、`test_regression.test_lint_passes_26_files` |
| 第 3 層 | 上一層全部；`python3 -m unittest tests.record.test_r3_reminders tests.record.test_regression`；`test_r3_app_static` 的 `FinalizeRunnerStatic`、`NotifyStatic`、`RemindersStatic`；建置後 entitlements 恰為兩項 | `test_r3_sync_compensate`、`test_r3_app_static` 第 4 層以後類別、`test_r2_static` 三支、`test_t7_fixes` 兩支 |
| 第 4 層 | 上一層全部；`LatencyLogStatic`、`HudStatic`；`python3 -m unittest tests.record.test_t7_fixes` | `test_r3_sync_compensate`、第 5 層以後類別、`test_r2_static` 三支 |
| 第 5 層 | 上一層全部；`DiscardStatic` | `test_r3_sync_compensate`、第 6 層以後類別、`test_r2_static` 三支 |
| 第 6 層 | 上一層全部；`MenuStagesStatic`、`SegmentSchedulerStatic`；`test_r2_static.test_trigger_menu_items_r2` | `test_r3_sync_compensate`、`OnboardingSettingsStatic`、`SyncCompensateStatic`、`MeetingDetectStatic`、`test_r2_static.test_defaults_single_writer`、`test_r2_static.test_trigger_preferences_window` |
| 第 7 層 | 上一層全部；`python3 -m unittest tests.record.test_r3_sync_compensate`；`OnboardingSettingsStatic`、`SyncCompensateStatic`；`test_r2_static` 全部 | `MeetingDetectStatic` |
| 第 8 層 | `python3 -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`python3 -m unittest discover -s tests/record -t . -k test_no_client_names`（不得 skipped）；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 並以 `codesign -d --entitlements -` 確認恰為兩項；`python3 .claude/teams/tools/check_rules.py --git . 377dd92..feature/meeting-record-r3`；verify | 無；任何一支不綠就停下交人 |

### 10.4 不屬於任何子任務、需要主 session 或使用者做的事（R3）

- **閘門 2 前**（已完成，2026-10-13）：Claude Design 出稿 → 使用者挑稿（`r3-design-choices.md`）→ 存 `specs/meeting-record/design-r3/`（存前後掃名稱：沒有）→ spec 的外觀條文、§6 第 129、130、134、135 條補完（`design.md` R3-D21、R3-D22）。
- **閘門 2**：使用者核准 spec §6 第 117–135 條（含既有測試修改）與 §7 疑慮 52–54 的預設選項（膠囊字放大、F2 用 `NSAlert`、字型不打包），`save_run.py approve`，stage 鍵 `r3-design`。
- `r3-reminders` 開工前查 Apple 文件確認提醒事項權限的 plist 鍵名（§7 疑慮 45）。
- **test 段 `r3-field-check`**（使用者在場）：`spec.md` §4.47 全部；結果寫 run 目錄；S-C 預設由使用者依 §4.47.2 決定（改預設要另列 §6）。
- 推送前照 `plan.md §5.1` 的做法掃 `origin/main..feature/meeting-record-r3`（只回報有／沒有）；推送、開 PR 一律等使用者當下同意。

### 10.5 拆 PR 規劃（R3）

修改的既有檔遠超過 15 個，建議拆兩包（主 session 在 deliver 段依實際 diff 決定，先問使用者）：

- **R3-1（CLI、Python、逐字稿、文件、specs）**：`bin/`、`schema/`、`tests/record/`、`.claude/skills/`、`README.md`、`specs/meeting-record/`。
- **R3-2（app）**：`tools/MeetingRecorder/`（Core、Capture、Trigger、Resources、Tests、build.sh）。
- 依賴：R3-2 的 `r3-lock` 與 R3-1 的 `record.sh` 屬同一個子任務、測試互相引用，所以兩包要依序合併（R3-1 先），或改成一包；由使用者決定。

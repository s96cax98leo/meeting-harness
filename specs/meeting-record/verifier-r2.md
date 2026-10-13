# 驗證報告：meeting-record R2（test 段第 3 輪派工）

- 驗證對象：`feature/meeting-record` @ `59d40478f0d6dc470dfc4436f30c718ae2f6fe99`（HEAD；開工、全量測試跑完、寫本檔前各查一次，三次相同）。反作弊範圍 `meeting-record-r1-baseline`（＝`f084765`）`..HEAD`，共 22 個 commit
- 驗收依據：`specs/meeting-record/spec.md` 的 R2 節（§3.9–§3.14、§4.16–§4.24、R2-§6 第 77–100 條）。§4.25 實機 t7 要使用者在場，全部列 not_verifiable。第一輪 §4.1–§4.15 只做回歸確認
- 寫檔範圍：只寫本檔。派工單本文寫的是 `verifier.md`，但授權補充明定第一輪 `verifier.md`（ecf2819）不得覆寫、本輪寫到 `verifier-r2.md`，本檔照授權補充。`verifier.md`、`design-review.md`、`design-review-r2.md`、`evidence/design-review-r2-*.txt` 都沒動。worktree 原本已有一份未提交的 `verifier-r2.md`，本檔整份覆寫，數字和結論都來自本輪自己重跑
- 環境：macOS（Darwin 25.6.0，arm64）。測試指令都帶 `TMPDIR=$(mktemp -d) LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=<run 目錄>/client-names.txt`（`<run 目錄>`＝`_tpm/runs/20261010-sdlc-meeting-record`）。名稱清單沒有讀出，也沒有寫進任何檔
- 安全邊界：錄製器只建到 `MH_RECORDER_DEST=$(mktemp -d)`；沒有啟動 MeetingRecorder.app、沒有送訊號給任何 MeetingRecorder 程序、沒有觸發 TCC、沒有註冊登入項目。開工和收尾各做一次快照（`pgrep -x MeetingRecorder`、`~/Applications/MeetingRecorder.app` 的 mtime、`~/.meeting-harness/` 第一層 10 個項目的大小與 mtime），兩次相同（唯一差別是 `~` 本身的 mtime，不在 `~/.meeting-harness/` 內）。手動跑 CLI 時 `MH_RECORD_HOME` 指到暫存目錄

## 1. 機械檢查（本輪在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0；doctor 輸出 `✗` 0 個 |
| V2 | `python3 -m unittest discover -s tests/record -t . -v` | `Ran 178 tests in 425.783s`、`OK`、rc=0；`... ok` 178 支，FAIL／ERROR／skipped 0。`tests/record/test_*.py` 的 `def test` 也是 178 個。`test_no_client_names_in_repo_text` 是 `ok`，不是 skip |
| V3 | `/bin/bash tools/MeetingRecorder/Tests/run.sh` | rc=0，`共 78 支，失敗 0 支`；`Tests/*.swift` 的 `func test` 也是 78 個 |
| V4 | `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`，再跑 `codesign -d --entitlements -`、`codesign -dvv` | rc=0。entitlements 恰為兩項：`com.apple.security.automation.apple-events`、`com.apple.security.device.audio-input`；`Identifier=com.meetingharness.recorder`、`flags=0x10000(runtime)`、`Authority=MeetingHarness Dev`。`~/Applications/MeetingRecorder.app` 的 mtime 建置前後相同 |
| V5 | `python3 .claude/teams/tools/check_rules.py --git . meeting-record-r1-baseline..feature/meeting-record` | rc=0，`規則檢查：通過` |
| V6 | 從 spec §4.16–§4.24 表格的「測試」欄抽出所有 `test*` 名稱（測試模組名除外），逐一對 V2、V3 的 ok 清單 | 92 個名稱，沒找到或沒通過的 0 個 |
| V7 | 名稱掃描：`grep -qF -f <清單>` 比對 `git diff`、`git log --format=%B`（同一範圍），再逐一掃 `git ls-files` | diff：沒有；commit 訊息：沒有。追蹤檔命中 2 個，就是派工單點名的兩個既有檔，本檔不引述。本檔與 `design-review-r2.md`：沒有 |
| V8 | 暫存 `MH_RECORD_HOME` 下手動跑 `meeting.sh record pause｜resume｜mute｜unmute｜mark`（沒有錄製）、`record pause x`、`record mark --no-such-flag`、`record help`、`meeting.sh help` | 五個寫法都是 rc=3「✗ 沒有錄製在跑。」；`pause x` rc=2「✗ pause 不接參數：x」；未知旗標 rc=2「✗ 未知的選項：--no-such-flag」；`record help` rc=0；`meeting.sh help` 有 12 行 `  meeting record`。跑完暫存 home 是空的（回 3 時不建控制檔） |

## 2. 逐條結果

只用 pass、fail、not_verifiable。同一條有自動部分、也有人工 t7 或截圖部分時拆成兩列。

### 2.1 資料契約 §3.9–§3.14

| 節 | 結果 | 證據 |
|---|---|---|
| 3.9 控制檔與鎖 | pass | V3 `testRequestAndResetControlFile`、`testApplyingCommands`、`testControlActions` ok；V2 `test_control_commands_with_fake_recorder` ok |
| 3.10 status 的 R2 欄位 | pass | V3 `testStatusR2Keys`、`testPauseEventsAndStatusFields` ok；第一輪 `RecordsTests` 不在 R2 diff 內，全綠 |
| 3.11 事件、`pausedTotal`、`levels` | pass | V3 `testMetaR2EventKeys`、`testPausedTotalAndOutputTime`、`testAppendingMuteEvent` ok；V2 `test_gapstats_subtracts_pause`、`test_gapstats_no_pause_unchanged`、`test_levels_checks_exclude_pause_and_mute` ok；`pausedTotal` 只寫給 meta 有 `pauseEvents` 鍵的場次（`bin/_record_finalize.py:689-691`，依第 100 條）；突變 M2、M3 |
| 3.12 markers | pass | V3 `testMarkerShape`；V2 `test_markers_copied_and_idempotent`、`test_markers_copied_on_already_done`、`test_markers_absent_no_file`、`test_markers_not_listed_as_session`、`test_markers_check` ok |
| 3.13 menubar prefs、通知識別碼 | pass | V3 `testMenuBarPrefsFile`、`testNotificationIDs`；V2 `test_defaults_single_writer` ok |
| 3.14／3.14.1 Swift 名稱、M6b | pass | V3 能編譯且全綠（`ControlTests.swift`、`MenuBarR2Tests.swift` 用到的 §3.14 名稱都在）；`testMenuBarR2Rows` ok；第一輪 `TriggerTests.swift` 沒改，全綠 |

### 2.2 §4.16 控制通道與 CLI

| 節 | 結果 | 證據 |
|---|---|---|
| 4.16.1–4.16.3 | pass | V3 `testApplyingCommands`、`testControlActions`、`testRequestAndResetControlFile`、`testControlAvailability` ok；突變 M1 |
| 4.16.4 | pass | V2 `test_capture_sigusr1_handler_before_pid`、`test_main_ignores_sigusr1_before_dispatch` ok；`Sources/main.swift:54` `signal(SIGUSR1, SIG_IGN)` |
| 4.16.5 | pass | V2 `test_control_commands_with_fake_recorder`、`test_control_idempotent_no_signal`、`test_mark_increments`、`test_exit_code_matrix` ok |
| 4.16.6 | pass | V2 `test_control_unavailable_exit_3`、`test_old_recorder_not_signalled` ok；V8 |
| 4.16.7 | pass | V2 `test_control_no_response_exit_3` ok；突變 M4 |
| 4.16.8 | pass | V2 `test_control_extra_args_exit_2`、`test_reserved_words_dot_slash_root`、`test_record_unknown_flag_exits_2` ok；V8 |
| 4.16.9 | pass | V2 `test_status_shows_pause_mute_markers` ok |
| 4.16.10 | pass | V3 `testStatusR2Keys` ok |
| 4.16.11 | pass | V2 `test_stop_summary_pause_markers`、`test_stop_prints_black_intervals` ok |

### 2.3 §4.17 只靜音麥克風

| 節 | 結果 | 證據 |
|---|---|---|
| 4.17.1 | pass | V3 `testZeroedAudioSample` ok |
| 4.17.2（自動） | pass | V2 `test_capture_mic_zeroed_before_rms` ok |
| 4.17.2（實機） | not_verifiable | 人工 t7（§4.25） |
| 4.17.3、4.17.4、4.17.7 | pass | V3 `testMetaR2EventKeys`、`testDetectorResets`、`testAppendingMuteEvent` ok |
| 4.17.5、4.17.6、4.17.8（判準自我測試） | pass | V2 `test_mic_mute_zero_check`、`test_no_false_silence_check`、`test_mute_timing_check` ok |
| 4.17.5、4.17.6、4.17.8（實機場次） | not_verifiable | 人工 t7；沒有 R2 實錄場次 |

### 2.4 §4.18 整段暫停／繼續

| 節 | 結果 | 證據 |
|---|---|---|
| 4.18.1 | pass | V3 `testPausedTotalAndOutputTime` ok；突變 M2 |
| 4.18.2（自動） | pass | V2 `test_capture_pause_gate_before_maxend`、`test_capture_uses_core_pause_functions`；V3 `testPauseGateAndSwitchReason`、`testDetectorFeed` ok |
| 4.18.2（實機） | not_verifiable | 人工 t7 |
| 4.18.3（自動） | pass | V3 `testPauseEventsAndStatusFields` ok |
| 4.18.3（實機） | not_verifiable | 人工 t7 |
| 4.18.4 | pass | V2 `test_gapstats_subtracts_pause`、`test_gapstats_no_pause_unchanged` ok；第一輪 `test_finalize.py` 沒改，全綠；突變 M3 |
| 4.18.5 | pass | V2 `test_pause_aware_segment_checks` ok；第一輪 `test_e2e_check.py` 沒改，全綠 |
| 4.18.6、4.18.11、4.18.12（判準自我測試） | pass | V2 `test_pause_cut_and_events_check`、`test_pause_mute_requires_events`、`test_no_false_black_check`、`test_event_output_t_check` ok |
| 4.18.6、4.18.11、4.18.12（實機場次） | not_verifiable | 人工 t7 |
| 4.18.7 | pass | V2 `test_levels_checks_exclude_pause_and_mute` ok |
| 4.18.8–4.18.10 | pass | V3 `testPauseGateAndSwitchReason`、`testPauseEventsAndStatusFields`、`testDetectorFeed` ok |

### 2.5 §4.19 標記

| 節 | 結果 | 證據 |
|---|---|---|
| 4.19.1 | pass | V3 `testMarkerShape` ok |
| 4.19.2（自動） | pass | V2 `test_capture_markers_written` ok |
| 4.19.2（實機） | not_verifiable | 人工 t7 |
| 4.19.3 | pass | V2 `test_markers_copied_and_idempotent`、`test_markers_copied_on_already_done`、`test_markers_absent_no_file`、`test_markers_not_listed_as_session` ok |
| 4.19.4（判準自我測試） | pass | V2 `test_markers_check` ok |
| 4.19.4（實機場次） | not_verifiable | 人工 t7 |

### 2.6 §4.20 menu bar

| 節 | 結果 | 證據 |
|---|---|---|
| 4.20.1–4.20.3 | pass | V3 `testRecordedSecondsAndClockText`、`testMenuBarR2Rows`、`testLevelIndicator` ok |
| 4.20.4（靜態） | pass | V2 `test_trigger_status_item_variable_length`、`test_menubar_uses_template_image` ok |
| 4.20.4（設計審查截圖） | not_verifiable | 要 t7 截圖 |
| 4.20.5（自動） | pass | V3 `testHotKeySpecs`；V2 `test_trigger_hotkeys_distinct_ids`、`test_hotkey_uses_carbon`、`test_hotkey_failure_logged` ok |
| 4.20.5（實機） | not_verifiable | 人工 t7 |
| 4.20.6（靜態） | pass | V2 `test_trigger_menu_items_r2`、`test_start_item_shows_hotkey` ok |
| 4.20.6（截圖與實機） | not_verifiable | 人工 t7 |
| 4.20.7（自動） | pass | V3 `testTriggerDebouncer` ok |
| 4.20.7（實機） | not_verifiable | 人工 t7 |
| 4.20.8 | pass | V2 `test_trigger_control_uses_availability` ok；`Trigger/MenuBar.swift:395` 的 `kill(pid, SIGUSR1)` |

### 2.7 §4.21 選單選視窗與存檔位置、quick-start

| 節 | 結果 | 證據 |
|---|---|---|
| 4.21.1、4.21.2 | pass | V3 `testQuickStartRootAndExplicitWindow`、`testUpdatedRecentRoots`、`testMenuBarPrefsFile` ok |
| 4.21.3（自動） | pass | V2 `test_trigger_quick_start_explicit_window`；V3 `testQuickStartDecision` ok |
| 4.21.4、4.21.5（靜態） | pass | V2 `test_trigger_window_list_via_open`、`test_trigger_prefs_and_open_panel`、`test_defaults_single_writer` ok |
| 4.21.3–4.21.5（實機） | not_verifiable | 人工 t7 |

### 2.8 §4.22 偏好設定、登入項目、無參數啟動

| 節 | 結果 | 證據 |
|---|---|---|
| 4.22.1、4.22.3 | pass | V3 `testLaunchMode`、`testLoginItemDisplay` ok |
| 4.22.2 | pass | V2 `test_main_launch_mode_dispatch`、`test_docs_app_args_exist_in_sources` ok |
| 4.22.4（靜態） | pass | V2 `test_trigger_preferences_window` ok |
| 4.22.4（設計審查截圖） | not_verifiable | 要 t7 截圖 |
| 4.22.5 | pass | V2 `test_trigger_login_item_only_in_preferences` ok；`register()`／`unregister()` 只出現在 `Trigger/Preferences.swift:162,164` |
| 4.22.6 | not_verifiable | 人工 t7（登出再登入） |

### 2.9 §4.23 自動前處理、完成通知、上一場成品

| 節 | 結果 | 證據 |
|---|---|---|
| 4.23.1 | pass | V3 `testShouldAutoPrep`、`testNotificationIDs` ok |
| 4.23.2–4.23.4（靜態） | pass | V2 `test_trigger_autoprep_session_prep`、`test_capture_completion_notification_id`、`test_trigger_completion_notification_category` ok |
| 4.23.2–4.23.4（實機） | not_verifiable | 人工 t7 |

### 2.10 §4.24 文件與 CLI 表面

| 節 | 結果 | 證據 |
|---|---|---|
| 4.24.1 | pass | V2 `test_surface_parsers.py` 全部 ok（12 個寫法、32 組結束碼） |
| 4.24.2 | pass | V2 `test_help_lists_record_forms`、`test_record_help_prints_surface`、`test_docs_cli_block_matches_spec`、`test_docs_cli_block_matches_help`、`test_docs_flags_match_behavior`、`test_docs_exit_codes_match_behavior` ok；V8 |
| 4.24.3 | pass | V2 `test_r2_docs.py` 全部 ok |
| 4.24.4 | pass | V2 帶清單跑，`test_no_client_names_in_repo_text` ok；V7 |
| 4.24.5 | pass | V1；V2 `test_lint_passes_26_files` ok |

### 2.11 §4.25 實機 t7

| 節 | 結果 | 證據 |
|---|---|---|
| 4.25.1–4.25.5 | not_verifiable | spec §4.25 規定要使用者在場；派工約束不准啟動 app、不准觸發 TCC |

### 2.12 R2-§6 第 77–100 條

| 條 | 結果 | 證據 |
|---|---|---|
| 77、93 | pass | 既有測試修改逐行對過第 77 條（見 §4）；V2 全綠；V8 `help` 12 行 |
| 78 | pass | V8：多餘參數回 2 |
| 79、97 | pass | V3 `testStatusR2Keys`、`testMetaR2EventKeys`；第一輪 `testStatusJSONKeys` 等沒改，全綠 |
| 80–86、90、91、94、96 | pass（自動部分）；實機部分 not_verifiable | 對應 §4.20–§4.23 與 §4.16.9 各列 |
| 87、88、89、95、98、99 | pass | 對應 §4.18、§4.19、§3.11、§3.12 各列；`SwitchReason` 在 `Core/Segments.swift`，`testPauseGateAndSwitchReason` 涵蓋 |
| 92 | not_verifiable | 流程規定（test 段 `has_ui=true`、派設計審查），歸設計審查，不是本檔能驗的產品行為 |
| 100 | pass | `bin/_record_finalize.py:689-691`；V2 `test_gapstats_no_pause_unchanged` 與第一輪 `test_finalize.py` 都綠；突變 M3 |

### 2.13 第一輪回歸（§4.1–§4.15）

| 範圍 | 結果 | 證據 |
|---|---|---|
| 第一輪全部自動測試 | pass | V2 178 支、V3 78 支都包含第一輪測試，全部 ok；V1、V4 綠。第一輪實機項目本輪沒重驗，以 `verifier.md`（ecf2819）為準 |

**統計**：fail 0；not_verifiable 都是人工 t7／t7 截圖部分、§4.25 全部、第 92 條；其餘 pass。

## 3. 缺陷

沒有（fail 0）。

## 4. 反作弊檢查（`meeting-record-r1-baseline..HEAD`）

| 項目 | 結果 | 依據 |
|---|---|---|
| 既有測試被改 | 有，都在第 77、100 條範圍內 | `git diff --name-status` 的既有測試修改檔：`surface.py`（只加 5 個寫法常數、10 組結束碼）、`test_surface_parsers.py`（`VALID_BLOCK`／`VALID_USAGE` 各加五列；`:60-63` 7→12、22→32）、`test_cli_dispatch.py`（`:63-65` 7→12，0970c5f；`:77-79` h+8/9/10→h+13/14/15，b04120b）、`test_docs.py`（`:16` 加五字、`:172` 17→27）、`test_record_sh.py`（`EXIT_CODE_CASES` 只新增 10 筆、`:24` 註解 22→32）、`Tools/.../Tests/main.swift`（只登記兩個新 suite）。`test_finalize.py`、`test_e2e_check.py`、`test_static_rules.py`、`test_regression.py`、`TriggerTests.swift`、`RecordsTests.swift` 不在 diff 內 |
| 第 77 條字面沒列的附帶修改 | 有，判定為支撐性修改 | `test_record_sh.py` 多一行 import 與 `run_exit_case` 的 `running_controllable` setup 分支；只讓核准的 10 筆新案例能跑，沒改既有斷言或分支 |
| R2 新測試在紅燈後被改 | 只有第 100 條那處 | `test_r2_finalize.py`：`b04120b` 在 `test_gapstats_no_pause_unchanged` 的場次 meta 補 `pauseEvents: []`，斷言集合不變（只改訊息字串）；`59d4047` 只改註解條號 98→100 |
| 測試被刪 | 沒有 | diff 中沒有 `-def test`／`-func test` |
| skip、fixme、only、expectedFailure、XCTSkip | 沒有 | 新增行掃描只命中 `e2e_check.py` 的 `skip=` 參數（§4.18.7 規定排除暫停／靜音區間的判準參數，不是跳過測試）；V2 skipped 0 |
| 斷言被放寬 | 沒有 | 第一輪判準常數（`AROUND`、`STOP_TAIL_TOL` 等）沒有任何 `-` 行；`e2e_check.py` 只新增 R2 常數。`longest_low`／`quiet_outside` 加 `skip` 只在有暫停／靜音區間時生效，第一輪 `test_e2e_check.py` 沒改、全綠 |
| 被測物被 mock | 沒有 | CLI 測試用 `fake_recorder.sh` 代替錄製器 app（§4.16.5 規定），被測的 `bin/record.sh` 是真的；替身新行為只在 `FAKE_CONTROL` 有設時生效 |
| 錯誤被吞、加 retry | 沒有實質問題 | 產品 diff 的 `except Exception:` 兩處在 `_record_finalize.py` stop 摘要／status 顯示路徑（讀選用 meta 失敗當空、`startedAt` 解析失敗不印時間），不影響結束碼或成品；`record.sh` 等狀態檔反映的迴圈是 R2-§2.2 規定的等待時限，超時回 3（突變 M4 證明有測試擋） |
| 證據 commit 是否為 HEAD | 是 | 三次查 HEAD 都是 `59d4047`；主 session 說的數字（Python 178、Swift 78）與本輪重跑相符，但本檔只用自己重跑的結果 |
| 上游既有測試被改 | 不適用 | 本 repo 沒有上游 |
| commit 引用核准條號 | 部分 | 0970c5f 內文寫「第 77 條」；b04120b 內文寫「屬 R2-Q5…（使用者核准）」與第 100 條內容，但沒有字面寫「第 77 條」。不判 fail，列在 §5 |

### 4.1 突變抽查（在 scratchpad 的複本上改，repo 內沒動，用完已刪）

| # | 突變 | 結果 |
|---|---|---|
| M1 | `Core/Control.swift:129` `controlVersion ?? 0` 改 `?? 1`（舊版錄製器被當可控制） | `run.sh` 78 支失敗 1：`ControlTests.testControlAvailability` |
| M2 | `Core/Control.swift:187` `pausedTotal` 每段多加 0.5 秒 | `run.sh` 失敗 2：`testPausedTotalAndOutputTime`、`testPauseEventsAndStatusFields` |
| M3 | `bin/_record_finalize.py:690` 拿掉 `has_pause_events_key` 守衛（一律寫 `pausedTotal`） | `test_finalize` 紅 1：`test_manifest_gapstats_written`（第一輪 4 鍵契約被擋住） |
| M4 | `bin/record.sh` 控制命令逾時從 `sys.exit(3)` 改 `sys.exit(0)` | `test_control_no_response_exit_3` 紅 |

結論：抽查的四個關鍵行為測試都擋得住。

### 4.2 文件與實作落差（不判 fail）

- §4.18.4 正文仍寫「沒有 `pauseEvents` 的場次 `pausedTotal` 為 0.0」（`spec.md:1227`），已被第 100 條（`spec.md:1353`）改掉。依 R2 節「第一輪內容不就地改、以 §6 為準」的慣例說得通，但只讀 §4.18.4 的人會誤解
- 第 100 條與第 77 條 build 段補記的核准，只記在 spec §6 和 commit `b04120b` 內文；`run.json` 的 `r2-build` 沒有 `approved` 紀錄（`r2-plan`、`r2-design` 有）。本檔只能確認 spec 有記錄

## 5. 待決（都不 blocking）

- 請使用者確認第 100 條與第 77 條 build 段補記（`VALID_BLOCK`／`VALID_USAGE` 樣本、`test_cli_dispatch.py:77-79`）是自己核准的；需要的話用 `save_run.py` 補記
- §4.25 實機 t7 要等使用者在場；在那之前 R2 的實機與截圖部分維持 not_verifiable

## 6. 範圍

- **涵蓋**：§3.9–§3.14、§4.16–§4.24 每條的自動部分（Python 178、Swift 78、check_rules、暫存建置與 entitlement）；R2-§6 第 77–100 條；CLI 五個新寫法在暫存 home 下的結束碼與訊息；spec 引用的 92 個測試名逐一對 ok 清單；反作弊（既有測試逐行 diff、紅燈後修改、skip、mock、例外處理、commit 條號）；四個突變抽查；名稱掃描（只報有／沒有）；第一輪全量自動測試回歸
- **未涵蓋（not_verifiable）**：§4.25 全部；§4.17–§4.23 標「人工 t7」或「t7 截圖」的部分；第 92 條。原因：要使用者在場、要啟動 app 或觸發 TCC，派工約束不允許
- **未涵蓋（其他）**：沒有實錄；沒有對 `~/.meeting-harness/e2e/` 的場次重跑 `e2e_check.py`（沒有 R2 實錄場次）；§7 疑慮 35、37、39 只能靠 t7 驗；HIG 審查歸設計審查

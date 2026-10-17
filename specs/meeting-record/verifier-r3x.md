# 驗證報告：meeting-record R3x（背景收尾與收尾平行化，sdlc-test 段）

- 驗證對象：`feature/meeting-record-r3` @ `2cb31f25b1e9ee308c4e0a46bf5fce742bc22644`（worktree `.worktrees/meeting-record-r3`）。開工、兩輪全量跑完、寫本檔前各查一次 HEAD，三次相同，worktree 乾淨
- R3x 範圍：`03b6f48..HEAD`（實作）；Red 從 `768a236` 起（`cfbb7a3` Swift、`7e99e34` Python）；反作弊與名稱掃描範圍 `ac88ad4..HEAD`（21 個 commit）
- 驗收依據：`spec.md`〈R3 補充輪（R3x）〉§4.48–§4.58（91 條）、R3x-§6 第 145–157 條、〈Red 層補字面〉(1)–(4)；`design.md` R3x-D1–D15。閘門 2 決定（R3x-D13）：決定 1–5 都選 A，I5 選 A，I7 在 `.failed` 時也進背景收尾階段
- 環境：macOS（Darwin 25.6.0，arm64）。每個指令都帶 `TMPDIR=$(mktemp -d) LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=<run 目錄>/client-names.txt`（`<run 目錄>`＝`_tpm/runs/20261010-sdlc-meeting-record`）。日誌寫在 `$TMPDIR`。名稱清單只交給 `grep -f` 與測試，沒有讀出內容
- 安全邊界：建置只建到 `MH_RECORDER_DEST=$(mktemp -d)`，用完即刪。`~/Applications/MeetingRecorder.app` 的 mtime 建置前後相同（`1791639618`）。沒有啟動 app，沒有對任何錄製器程序送訊號，沒有寫 `~/.meeting-harness`（只讀了 `record.defaults.json` 的鍵名，以及 `harness` 的 worktree 名稱），沒有用 git stash。突變抽查在 `git archive HEAD` 解出的暫存複本上做，跑完即刪
- 寫檔範圍：只寫本檔

## 1. 機械檢查（在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0。輸出 `✓ lint 通過（26 個檔）`，doctor 的 `✗` 為 0 個（§4.57.1：`bin/` 頂層維持 26 檔） |
| V2 | `python3 -m unittest discover -v -s tests/record -t .`，跑 2 輪 | 第 1 輪 `Ran 378 tests in 743.699s`、`OK`；第 2 輪 `Ran 378 tests in 742.251s`、`OK`。兩輪 rc 都是 0，FAIL、ERROR、skipped 都是 0。`tests/record/test_*.py` 的 `def test_` 共 378 個（`ac88ad4` 時是 312 個，R3x 新增 66 個：`test_r3x_background` 28、`test_r3x_parallel_finalize` 24、`test_r3x_app_static` 13、`test_r3x_docs` 1）。條件式測試（`test_no_client_names_in_r3_files`、`test_no_client_names_in_repo_text`、`test_downstream_missing_sections`）都是 `ok`，沒有被 skip |
| V3 | `/bin/bash tools/MeetingRecorder/Tests/run.sh` | rc=0，`共 139 支，失敗 0 支`。`ac88ad4` 時是 123 支，R3x 新增 `R3xBackgroundTests` 16 支 |
| V4 | `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`，再跑 `codesign -d --entitlements - --xml`、`codesign -dvv` | rc=0，編譯 40 個檔。entitlements 恰為 3 項：`automation.apple-events`、`device.audio-input`、`personal-information.calendars`。另有 `Identifier=com.meetingharness.recorder`、`flags=0x10000(runtime)`、`Authority=MeetingHarness Dev`（§4.57.2） |
| V5 | `python3 .claude/teams/tools/check_rules.py --git . ac88ad4..HEAD` | rc=0，`規則檢查：通過` |
| V6 | 從 spec §4.48–§4.57 的測試欄抽出全部 `檔::函式`（含 `::` 續寫），逐一對 V2 第 1、2 輪與 V3 的 ok 清單 | 91 列、91 個測試引用，找不到或沒通過的都是 0。有 5 支的 `ok` 被測試清理時的 `ResourceWarning` 擠到下一行，逐支確認過是 `ok`（見 §6 N-2） |
| V7 | 名稱掃描：`grep -qiF -f <清單>` 比對 `git diff ac88ad4..HEAD`、`git log --format=%B ac88ad4..HEAD`，並逐一掃 `git ls-files` 的每個檔 | diff：沒有；commit 訊息：沒有；追蹤檔：沒有（§4.57.4） |
| V8 | 突變抽查 10 個（見 §5.3） | 8 個被測試擋下；M2 只被形狀測試擋下；M2b 是等價突變（有深度防禦） |

## 2. 逐條結果（§4.48–§4.58，91 條）

結果只用四種：PASS、PASS＋需實機、需實機、FAIL。同一條有自動部分、也有實機部分時寫「PASS＋需實機」：自動部分已通過，實機部分排進 §7 的劇本。「協定參考」欄標 ● 的條目只驗替身 `fake_bg_finalizer.sh` 加上 `record.sh`，**不算** Swift 錄製實例或 menu bar 的紅轉綠（spec R3x 前言、修正輪 I9）。Swift 實作與替身是否一致，另外讀碼核對（§3）。

**統計**：共 91 條。**PASS 67**、**PASS＋需實機 17**、**需實機 7**（4.54.8、4.58.1–4.58.6）、**FAIL 0**。其中協定參考 4 條（4.48.7、4.49.5、4.49.6、4.50.3），都列在 PASS＋需實機。

### §4.48 放鎖時機與每場狀態

| 節 | 結果 | 協定參考 | 證據（測試全部 ok；讀碼位置以 HEAD 為準） |
|---|---|---|---|
| 4.48.1 | PASS | | `swift:R3xBackgroundTests.swift::testBackgroundPaths`；`Core/BackgroundFinalize.swift:6-38` |
| 4.48.2 | PASS | | `swift:…::testTryFlock`；`BackgroundFinalize.swift:54-64`（`O_CLOEXEC`、只試一次、EWOULDBLOCK 時先 close） |
| 4.48.3 | PASS | | `swift:…::testRecordStatusBackgroundKeys`；`Core/Records.swift` 新增兩個 `Bool?` 欄位 |
| 4.48.4 | PASS＋需實機 | | `test_r3x_app_static.py::BackgroundCaptureStatic.test_release_order`；讀碼 `Capture/RecordingSession.swift:1080-1125`，順序是 skipFinalize → 試每場鎖 → enterBackground → 寫狀態 → 刪 pid → 清理 → 放鎖 → 記一行 log。實機看 4.58.1 |
| 4.48.5 | PASS | | `…::test_release_function`；`Capture/Commands.swift:122-128` |
| 4.48.6 | PASS＋需實機 | | `…::test_finalize_env_home`；`RecordingSession.swift:1214-1219`（背景路徑才設 `MH_FINALIZE_WAIT_LOCK=1`，前景路徑主動 `removeValue`）。實機確認收尾子程序讀到同一個 home（§7.1 第 9 步） |
| 4.48.8 | PASS | | `swift:…::testBackgroundEntryDecision`；`BackgroundFinalize.swift:141-149` |
| 4.48.7 | PASS＋需實機 | ● | `test_r3x_background.py::test_next_recording_starts_during_background_finalize`。實機看 4.58.2 |

### §4.49 上一場不改寫、不刪除下一場的共用狀態與 pid

| 節 | 結果 | 協定參考 | 證據 |
|---|---|---|---|
| 4.49.1 | PASS | | `swift:…::testSharedStatusWritable`；突變 M8 會被它擋下 |
| 4.49.2 | PASS | | `swift:…::testShouldRemoveRecordPid` |
| 4.49.3 | PASS＋需實機 | | `test_r3x_app_static.py::StatusWriterStatic.test_conditional_shared_write`；讀碼 `Capture/PreflightRunner.swift:51-87`（每場狀態檔一定寫；共用狀態檔在持有 `record.lock` 時直接寫，否則以 1 秒重試取鎖，`sharedStatusWritable` 為 true 才寫，寫完 close）。實機看 4.58.3 |
| 4.49.4 | PASS＋需實機 | | `…::test_complete_keeps_next_pid`；`RecordingSession.swift:1240-1244`。實機看 4.58.3 的「`record.pid` 仍是 B」 |
| 4.49.5 | PASS＋需實機 | ● | `test_r3x_background.py::test_previous_does_not_touch_next_state` |
| 4.49.6 | PASS＋需實機 | ● | `…::test_shared_status_updated_when_untouched`。實機看 §7.4（沒有 B 時 A 收完） |

### §4.50 背景收尾排隊、取消

| 節 | 結果 | 協定參考 | 證據 |
|---|---|---|---|
| 4.50.1 | PASS | | `…BackgroundCaptureStatic.test_queue_wait`；`RecordingSession.swift:1165-1187`（每輪用 `queueWaitStep`，`usleep` 0.5 秒，沒有阻塞式 flock） |
| 4.50.7 | PASS | | `swift:…::testQueueWaitStep` |
| 4.50.2 | PASS | | `…::test_cancel_while_queued`；`RecordingSession.swift:1141-1144`（回 false → `complete(finalizeCode: 5, aborted: .cancelled)`，不經 `runFinalize`） |
| 4.50.3 | PASS＋需實機 | ● | `test_r3x_background.py::test_queue_one_at_a_time`。實機看 §7.3（選做） |
| 4.50.4 | PASS | | `swift:…::testBackgroundCancelDecision`。Red 層補字面 (1) 已照做：`BackgroundFinalize.swift:256` 判斷的是 `phase == .finalizing` |
| 4.50.5 | PASS＋需實機 | | `…MenuBarBackgroundStatic.test_cancel_uses_background_decision`；既有 `test_r3_app_static.py::MenuBarStatesStatic.test_stop_uses_decision`、`MenuStagesStatic.test_cancel_finalize` 都 ok（沒改）。讀碼 `Trigger/MenuBar.swift:869-876`、`:900-945`。實機看 4.58.6 |
| 4.50.8 | PASS | | `swift:…::testBackgroundJobLabel` |
| 4.50.9 | PASS＋需實機 | | `…::test_cancel_confirms_target`；`MenuBar.swift:923`（`runModal`）→ `:927`（重讀 `loadBackgroundJobs`）→ `:943`（`kill`）。實機看 4.58.6 |
| 4.50.6 | PASS＋需實機 | | 只有 4.50.2 的靜態測試。讀碼：`FinalizeRunner.cancel()` 在子程序還沒啟動時只記下 `cancelRequested`（`FinalizeRunner.swift:51-58`），下一輪 `queueWaitStep` 回 `.cancelled`，不取排隊鎖。實機看 §7.3 第 5 步（選做） |

### §4.51 `record.sh stop` 等的是自己那一場

| 節 | 結果 | 證據 |
|---|---|---|
| 4.51.1 | PASS＋需實機 | `test_r3x_background.py::test_stop_waits_own_run`；`bin/record.sh:949`（送訊號前記下目標 runId）、`:981`。突變 M7 會被它擋下。實機看 4.58.4 |
| 4.51.2 | PASS | `…::test_stop_own_run_failure` |
| 4.51.3 | PASS | `…::test_stop_background_only_success`、`…::test_stop_background_only_failure`；`record.sh:754-799`、`:813-835` |
| 4.51.4 | PASS | `…::test_stop_background_waits_all`（D13 決定 3 選 A：等全部） |
| 4.51.5 | PASS | `…::test_stop_background_crash_during_wait` |
| 4.51.6 | PASS | `…::test_stop_background_crashed_returns_3` |
| 4.51.7 | PASS | `…::test_stop_limit_excludes_queue`；既有 `test_r3_lock.py::test_stop_wait_limit_covers_finalize_deadline` ok。`cmd_stop` 內恰有 1 個 `limit="$(python3` 區塊（`record.sh:950`），排隊時重設起算點在 `:984` |
| 4.51.9 | PASS | `…::test_stop_same_run_skips_lock_check`；`record.sh:679-724`（共用狀態檔的 runId＝目標、又沒有 `background` 時直接回 `shared`，不碰 `finalizing/`） |
| 4.51.10 | PASS | 既有 `test_r3_lock.py::test_stop_does_not_resignal_while_finalizing` 兩輪都 ok，檔案沒改 |
| 4.51.11 | PASS | `…::test_stop_background_only_wait_limit`（只驗形狀，spec 寫明不實跑逾時）；`record.sh:758-772` |
| 4.51.12 | PASS | `…::test_stop_lock_held_without_pid_returns_3`、`…::test_stop_dead_pid_in_progress_returns_3`、`…::test_stop_after_preflight_failed_waits_background`。突變 M4 會被擋下 |
| 4.51.13 | PASS | `…::test_orphan_ignored_by_stop_and_status` |
| 4.51.8 | PASS | 既有 `test_record_sh`、`test_r2_cli`、`test_r3_lock` 全綠，檔案沒改 |

### §4.52 `record.sh status` 多出的行

| 節 | 結果 | 證據 |
|---|---|---|
| 4.52.1 | PASS＋需實機 | `…::test_status_shows_background_running`。實機看 4.58.2 |
| 4.52.2 | PASS | `…::test_status_crash_while_recording_returns_0` |
| 4.52.3 | PASS | `…::test_status_crash_without_recording_returns_5`。突變 M5 會被擋下 |
| 4.52.4 | PASS＋需實機 | `…::test_status_background_self`。實機看 4.58.1 |
| 4.52.5 | PASS | `…::test_status_background_finished_lines`（D13 決定 1 選 A） |
| 4.52.6 | PASS | `…::test_status_unchanged_without_background`；既有 `test_record_sh.py::test_exit_code_matrix` ok |
| 4.52.7 | PASS | `…::test_status_does_not_create_lock_files`；`record.sh:559-622` 開檔不帶 `O_CREAT` |
| 4.52.8 | PASS | `…::test_status_no_recording_shows_running` |
| 4.52.9 | PASS | `…::test_orphan_ignored_by_stop_and_status` |

### §4.53 `finish`、當掉檔與孤兒檔

| 節 | 結果 | 證據 |
|---|---|---|
| 4.53.1 | PASS | `…::test_finish_clears_crashed_background_state`；`record.sh:1161-1199`、`:1213`。突變 M6 會被擋下 |
| 4.53.2 | PASS | `swift:…::testPrunableBackgroundJob` |
| 4.53.3 | PASS | `swift:…::testBackgroundJobState`、`::testLoadBackgroundJobs` |
| 4.53.4 | PASS | 4.53.2 的行為測試；`RecordingSession.swift:1117-1122`；`…::test_orphan_ignored_by_stop_and_status` |

### §4.54 menu bar

| 節 | 結果 | 證據 |
|---|---|---|
| 4.54.1 | PASS | `swift:…::testApplyBackgroundFinalize`；`BackgroundFinalize.swift:280-322`。`bgCopy` 逐欄複製了 `MenuBarModel` 的全部 16 個欄位（`Core/Trigger.swift` 的 struct）。突變 M9 會被擋下 |
| 4.54.2 | PASS | `swift:…::testMenuStageBackground` |
| 4.54.3 | PASS | `swift:…::testMenuGroupsBackground` |
| 4.54.4 | PASS＋需實機 | `…MenuBarBackgroundStatic.test_refresh_overlays_jobs`；`MenuBar.swift:262`、`:275` |
| 4.54.5 | PASS＋需實機 | `swift:…::testAutoPrepCandidates`、`…::test_auto_prep_reads_jobs`；`MenuBar.swift:263-265`、`:1110-1122`。實機看 4.58.3（自動前處理只觸發一次） |
| 4.54.6 | PASS | `…::test_meeting_detect_not_blocked`；`MenuBar.swift:201-204`（閉包看的是 `.recording`／`.finalizing`；背景收尾階段的 `menuStage` 是 `.backgroundFinalizing`，`canStop` 是 false） |
| 4.54.7 | PASS＋需實機 | `…::test_cancel_item_enabled`；`MenuBar.swift:338-340` |
| 4.54.8 | 需實機 | 劇本 §7.1 第 4、6 步 |

### §4.55 平行正規化

| 節 | 結果 | 證據（全部在 `test_r3x_parallel_finalize.py`） |
|---|---|---|
| 4.55.1 | PASS | `test_finalize_jobs_values`；`bin/_record_finalize.py:258-268` |
| 4.55.2 | PASS | `test_recording_in_progress`；`:271-296` |
| 4.55.3 | PASS | `test_normalize_deps`；`:299-302` |
| 4.55.4 | PASS | `test_default_runs_three` |
| 4.55.5 | PASS | `test_jobs_env`；`:1348-1376` |
| 4.55.6 | PASS | `test_recording_lowers_to_two` |
| 4.55.7 | PASS | `test_x264_fallback_serial`；`:884-892` |
| 4.55.8 | PASS | `test_missing_video_waits_previous`；既有 `test_finalize.py::test_segment_without_video_filled` ok。突變 M1 會被擋下 |
| 4.55.9 | PASS | `test_reports_lowest_failed_segment` |
| 4.55.10 | PASS | `test_failure_stops_dispatch`；`:868-872`（`except SegmentAborted` 排在 `except FinalizeError` 之前）。另見 §5.3 的 M2、M2b |
| 4.55.11 | PASS | 既有 `test_r3_finalize_guard.py::test_step_timeout_exits_5_and_keeps_segments` 在預設平行度下 ok（沒改） |
| 4.55.12 | PASS | `test_sigterm_kills_all_groups` |
| 4.55.13 | PASS | `test_progress_lines` |
| 4.55.14 | PASS | `test_parallel_matches_serial_criteria`（Red 層補字面 (4)：先寫入同一個 `stamp`） |
| 4.55.15 | PASS | `test_parallel_analysis_keeps_order`；`:1414` |
| 4.55.16 | PASS | `test_parallel_shape` |
| 4.55.17 | PASS | 既有的 `test_finalize`、`test_r2_finalize`、`test_r3_finalize_guard`、`test_r3_sync_compensate`、`test_concurrency`、`test_static_rules`、`test_review_fixes` 兩輪全綠。疑慮 71 的 `test_concurrency.py::test_finalizing_session_not_listed` 也是 ok |
| 4.55.18 | PASS | `test_run_ordered_strict_order`、`test_run_ordered_lowest_failure`、`test_run_ordered_aborts_higher`、`test_run_ordered_checks_before_popen`、`test_run_ordered_serial_no_pool`；`:305-391` |
| 4.55.19 | PASS | `test_parallel_shape`。我另外用 tokenize 去掉字串與註解後重驗：`run_ordered` 不含 `.communicate`、`.wait(`、`.poll`、`kill_group` |
| 4.55.20 | PASS | `test_parallel_shape`、`test_sigterm_kills_all_groups`；`:220-238` |
| 4.55.21 | PASS | `test_say_lines_atomic`；`:402-406` |
| 4.55.22 | PASS | `test_wait_lock_then_idempotent`、`test_wait_lock_then_finalize`、`test_wait_lock_sigterm`；`:1319-1325`、`:394-399`。突變 M3 會被擋下 |

### §4.56–§4.58

| 節 | 結果 | 證據 |
|---|---|---|
| 4.56.1 | PASS | `test_r3x_docs.py::test_docs_mention_background_finalize`；既有 `test_docs`、`test_r2_docs`、`test_r3_docs` 都 ok |
| 4.56.2 | PASS | `test_r3x_background.py::test_disk_warning_with_background`；`record.sh:506-511`（D13 決定 5 選 A：只告警，印在 `launch start` 之前，門檻不變） |
| 4.57.1 | PASS | V1；`test_regression.py::test_lint_passes_26_files` ok |
| 4.57.2 | PASS | V2、V3、V4 |
| 4.57.3 | PASS | §5.1 |
| 4.57.4 | PASS | V7；`test_r3_docs.py::test_no_client_names_in_r3_files` ok |
| 4.58.1–4.58.6 | 需實機 | 劇本 §7.1–§7.5 |

## 3. 協定參考替身與 Swift 產品實作的一致性（讀碼）

`fake_bg_finalizer.sh` 是 `record.sh` 測試用的錄製實例替身。下表逐項比對它和 Swift 產品碼（`RecordingSession.swift`、`PreflightRunner.swift`、`BackgroundFinalize.swift`）。

| 協定點 | 替身 | Swift 產品 | 一致？ |
|---|---|---|---|
| 放鎖時機（§3.23 第 2–7 步） | `fake_bg_finalizer.sh:288-302`：每場鎖 → 寫每場狀態檔與共用狀態檔（finalizing／background／queued）→ pid 是自己才刪 → 清理 → 放 `record.lock` | `RecordingSession.swift:1088-1125`：順序相同；第 4 步寫入時仍持有 `record.lock`（`PreflightRunner.swift:74-77` 直接寫） | 一致 |
| 條件式寫入（§3.24） | `:89-128`：1 秒內每 100 ms 試 `record.lock`；共用狀態檔不存在、讀不懂或 runId 是自己才寫 | `PreflightRunner.swift:73-87`：`acquireRecordLock(retrySeconds: 1.0)`（重試間隔 `lockRetryInterval`）→ `readStatus`（讀不懂回 nil）→ `sharedStatusWritable` → close | 一致；重試間隔可能不同，不影響語意 |
| 只刪自己的 pid | `:298`：`tr -cd '0-9'` 後比對 `$$` | `BackgroundFinalize.swift:216-221`：去前後空白後必須全為數字。`record.pid` 只有 app 自己寫（`RecordingSession.swift:197`，內容是 `String(getpid())`），`record.sh` 不寫這個檔 | 一致（替身的寬鬆比對不會造成差異） |
| 排隊（§3.22） | `:307-311`：背景子程序每 0.5 秒 `LOCK_NB` 試一次，持有到父程序結束 | `RecordingSession.swift:1165-1187`：`queueWaitStep`＋`tryFlock`（`O_CLOEXEC`）每 0.5 秒試一次；fd 存在 `queueLockFD`，持有到程序結束 | 一致。替身沒有實作「排隊中被取消」與 `.unavailable`，這兩條只由 Core 行為測試（`testQueueWaitStep`）與靜態測試覆蓋，要靠實機 §7.3 |
| `MH_FINALIZE_WAIT_LOCK` | 替身不跑 Python | `RecordingSession.swift:1215-1219`：只在 `backgroundLockFD != nil` 時設 `1`，前景路徑主動移除；Python 端在 `_record_finalize.py:1321` 判斷 | 產品端一致；替身不涉及 |
| 清理（第 6 步） | `:207-254`：跳過自己那一場；鎖被持有的不碰 | `RecordingSession.swift:1117-1122`：`prunableBackgroundJob`（自己那一場持有每場鎖，`ownerAlive` 為 true，所以不會被清），另加 `backgroundRunIdAllowed` 防止路徑穿越 | 一致（產品多一道防護） |
| 進背景失敗時退回前景 | 替身沒有 | `RecordingSession.swift:1091-1099`、`:1126-1133`：不放 `record.lock`、不寫每場檔、訊息照 R3 | 只有 Core `testBackgroundEntryDecision` 與讀碼證據，沒有行為測試，也不在 §4.58 之內（見 §6 N-4） |

## 4. R3x-§6 第 145–157 條：實際狀態與條文的對照

| # | 狀態 | 證據 |
|---|---|---|
| 145 | 一致 | `releaseRecordLock()` 只在 `beginFinalize` 的背景分支呼叫（`RecordingSession.swift:1124`）。`--skip-finalize`（`:1080-1084`）、捨棄、前景退回都不放鎖；`preflight` 子指令不進收尾。`test_r3_lock.py` 沒改，全綠 |
| 146 | 一致 | `cmd_stop` 在沒有 `record.pid` 或 pid 已死時改走 `stop_without_recorder`（`record.sh:913-920`、`:813-835`）；三項條件見 `:726-748` 與 `record_lock_state`（`:152-176`） |
| 147 | 一致 | 上限算法與 `limit` 區塊沒變（`record.sh:950`，`cmd_stop` 內只有 1 個）；`queued` 時重設 `t0`（`:984`） |
| 148 | 一致 | `MenuStage` 加 `backgroundFinalizing`；`RecordStatus` 加 `background`、`queued`；`MenuBarModel` 加 `backgroundFinalizing`（`git diff ac88ad4..HEAD -- Core/Trigger.swift` 只多 2 行）。`menuBarModel` 本身沒改 |
| 149 | 一致 | `.finalizing` 照 R3（`MenuBar.swift:877-891`）；`.backgroundFinalizing` 走 `cancelBackgroundFinalize`（`:900-945`）；`.recording` 階段的分組沒改（`R3MenuBarTests` ok） |
| 150 | 一致 | `enqueueAutoPrep` 用 `autoPrepCandidates`＋`autoPrepEnqueued`，`lastAutoPrepRunId` 照舊寫入（`MenuBar.swift:1110-1122`）；`shouldAutoPrep` 的簽名沒改 |
| 151 | 一致 | `MenuBar.swift:201-204` |
| 152 | 一致（有 1 項小落差） | 進度行改為 `正規化 已完成 k/N`（`_record_finalize.py:1462-1469`）；`record.sh stop` 的轉印規則 `grep -E '正規化\|收尾\|略過'` 沒變（`record.sh:976`）。但 `record.sh:973` 的註解還是舊例「正規化 12/95」，見 §6 N-1 |
| 153 | 一致 | `FinalizeRunner.run` 啟動子程序之後才開始等 `deadlineSeconds`（`FinalizeRunner.swift`，`p.run()` 之後才 `exited.wait(timeout:)`），排隊時間在 `run` 之前，不算進總期限 |
| 154 | 一致 | §5.1 |
| 155 | 一致 | `menuBarModel` 沒改；背景收尾由 `applyBackgroundFinalize` 疊上（`MenuBar.swift:273-275`）；舊版錄製器寫的 `finalizing`（沒有 `background`）不會進 (a)（`BackgroundFinalize.swift:284-285`） |
| 156 | 一致 | Python 只在 `MH_FINALIZE_WAIT_LOCK == "1"` 時等鎖（`_record_finalize.py:1321`）；`record.sh` 和 `meeting.sh` 都沒有設這個變數（`grep -n MH_FINALIZE_WAIT_LOCK bin/*.sh` 沒有結果） |
| 157 | 一致 | `applyBackgroundFinalize` 的「沒有錄製在跑」包含 `.idle`、`.failed`（`BackgroundFinalize.swift:284`）；`detailText` 在 `.failed` 時保留原錯誤（`:305`） |

Red 層補字面 (1)–(4)：(1) `BackgroundFinalize.swift:256`；(2)(3)(4) 都是測試端的讀法，對應的測試 ok，測試在 Red 之後沒改過（§5.1）。

## 5. 反作弊

### 5.1 既有測試零修改

- `git diff --diff-filter=M --name-only ac88ad4..HEAD -- tests/ tools/MeetingRecorder/Tests/` 只列出 `tools/MeetingRecorder/Tests/main.swift`。它的 diff 只多一列 `("R3xBackgroundTests", mrtR3xBackgroundTests),`，沒有刪除的行（§4.57.3、§6 第 154 條）
- `git diff --diff-filter=DR ac88ad4..HEAD` 沒有結果：沒有刪除或改名的檔
- 新增的測試檔只有 7 個：`tests/record/fakes/fake_bg_finalizer.sh`、`fakes/parallel_ffmpeg.py`、`test_r3x_app_static.py`、`test_r3x_background.py`、`test_r3x_docs.py`、`test_r3x_parallel_finalize.py`、`Tests/R3xBackgroundTests.swift`
- **Red 之後測試零修改**：`git diff --stat 9468daf..HEAD -- tests/ tools/MeetingRecorder/Tests/` 沒有結果；`768a236..HEAD` 期間碰過測試路徑的 commit 只有 `cfbb7a3`、`7e99e34`（Red 本身）與 merge `9468daf`。`03b6f48`（補字面）只改 `spec.md`
- skip、only、fixme、retry：兩輪的 `OK` 行都沒有 `skipped=`，0 skip。R3x 新測試只有一處條件式 `skipTest`：`test_r3x_parallel_finalize.py:165-168` 的 `require_videotoolbox`，本機沒有 `h264_videotoolbox` 時才跳過，本機兩輪都沒有觸發。其他機器上它可能讓平行度的測試假綠，因為那時 spec §3.25 規定平行度一律是 1，量不出平行效果。這是有理由的環境守門，不算作弊。沒有 `expectedFailure`，也沒有 retry
- mock 被測物：替身只替換「錄製器」（`fake_bg_finalizer.sh`）與「ffmpeg」（`parallel_ffmpeg.py`，會轉呼叫真的 ffmpeg）。被測物 `record.sh`、`_record_finalize.py`、Core 函式都是真的在跑
- 吞錯誤：`record.sh` 的 `bg_jobs`、`bg_job_state`、`stop_target_state`、`clear_crashed_background` 都有 `2>/dev/null`，失敗時退回安全值（`[]`、`missing 0 0 0`、`none - 0 0 -`、不刪）。這些都是旁觀者讀取的退路，不會把失敗變成成功。`_record_finalize.py` 沒有新增寬泛的 `except`；`main` 只多接一個 `SegmentAborted`，並回 5（`:1576-1578`）

### 5.2 靜態測試的字面要在去掉字串常值後仍在

- Swift：先用 `test_static_rules.strip_swift_comments` 去註解、`blank_swift_strings` 去字串，再逐函式比對 `test_r3x_app_static.py` 的程式字面：`beginFinalize` 13 個、`releaseRecordLock` 2 個、`runFinalize` 的 `backgroundLockFD`、`complete` 2 個、`waitFinalizeQueue` 5 個、`StatusWriter` 6 個、`cancelFinalize`、`cancelBackgroundFinalize` 7 個、`refresh` 5 個、`enqueueAutoPrep` 2 個、`recordLockHeld` 的 `retrySeconds: 0`。缺少的是 0 個
- 只會出現在字串裡的字面：`已放開開錄鎖`、`排隊中`（log 文字）、`MH_RECORD_HOME`、`MH_FINALIZE_WAIT_LOCK`（環境變數鍵）。它們本來就是字串，對應的行為由 4.55.22 與實機覆蓋
- Python：用 tokenize 去掉字串與註解後，比對 `run_step`、`on_sigterm`、`encode`、`finalize_locked`、`run_ordered`、`say` 的 `test_parallel_shape` 字面，全部仍在；`on_sigterm` 不含 `_ACTIVE_LOCK`、`say(`；`run_ordered` 不含 `.communicate`、`.wait(`、`.poll`、`kill_group`
- `record.sh` 的形狀字面（`queued`、`t0="$(date +%s)"`、`startedAt`、`630`、`7200`）在 bash 本體或內嵌 Python 的程式裡（`record.sh:758-773`、`:984`），不是只出現在 echo 字串

### 5.3 突變抽查（暫存複本，跑完即還原並刪除）

| # | 突變（產品碼） | 跑的測試 | 結果 |
|---|---|---|---|
| M1 | `run_ordered` 不等依賴（`if d is not None and d not in finished:` → `if False:`） | `test_run_ordered_strict_order`、`test_missing_video_waits_previous` | 2 支都 FAIL，擋下 |
| M2 | `class SegmentAborted(Exception)` → 繼承 `FinalizeError` | `test_failure_stops_dispatch`、`test_parallel_shape` | 只有 `test_parallel_shape` FAIL，擋下。行為測試沒紅，原因是 `encode` 的 `except SegmentAborted` 排在前面，行為上等價 |
| M2b | M2 再加上刪掉 `encode` 的 `except SegmentAborted` 區塊（也就是 I2 原本的缺陷） | `test_failure_stops_dispatch`、`test_run_ordered_aborts_higher` | 2 支都 ok：**等價突變（深度防禦）**。被中止的段會進到 libx264 那一輪，但 `run_step` 在 `Popen` 前又檢查一次中止條件（`_record_finalize.py:180-181`），再丟 `SegmentAborted`，所以 x264 從頭到尾沒有啟動，符合 4.55.10。唯一可觀察的差別是 `note_x264_fallback` 會多印一行「改用 libx264，收尾平行度降為 1」，spec 沒有規定這一行（§6 N-3） |
| M3 | 收尾鎖等待失效（`!= "1"` 判斷 → `if True:`） | `test_wait_lock_then_idempotent`、`test_wait_lock_then_finalize` | 2 支都 FAIL，擋下 |
| M4 | `stop_without_recorder` 不看 `record.lock`（`[[ $? -eq 0 ]] && ok=1` → `ok=1`） | `test_stop_lock_held_without_pid_returns_3` | FAIL，擋下 |
| M5 | `status` 在沒有錄製、有當掉檔時不回 5（`rc = 5` → `rc = rc`） | `test_status_crash_without_recording_returns_5` | FAIL，擋下 |
| M6 | `clear_crashed_background` 連活著的每場檔也刪 | `test_finish_clears_crashed_background_state` | FAIL，擋下 |
| M7 | `cmd_stop` 不依目標 runId（`stop_target_state "${target}"` → `""`） | `test_stop_waits_own_run` | FAIL，擋下 |
| M8 | `sharedStatusWritable` 一律回 true | Swift `R3xBackgroundTests` | `testSharedStatusWritable` FAIL，擋下 |
| M9 | 背景收尾階段不開放開錄（`canStart: true` → `m.canStart`） | Swift `R3xBackgroundTests` | `testApplyBackgroundFinalize` FAIL，擋下 |

## 6. R3 前景收尾、`--skip-finalize` 試錄、`meeting record finish` 的回歸風險（讀碼）

- **前景收尾**（runId 不合格、每場鎖取不到或開不了）：`RecordingSession.swift:1126-1133` 寫 phase `finalizing`、message「收尾中」，記「● 收尾中（n 段）」，與 R3 逐字相同。不放 `record.lock`、不寫每場檔，`runFinalize` 會移除 `MH_FINALIZE_WAIT_LOCK`。和 R3 相比只有兩處不同：(a) 多傳 `MH_RECORD_HOME=<ctx.home>`。實機的 `ctx.home` 就是 `record.sh` 傳進來的 `--home`，也就是 `~/.meeting-harness`，和 Python 預設的 `record_home()` 相同，所以實際值不變；(b) `complete` 刪 `record.pid` 前會先比對內容。`record.pid` 只有 app 自己寫（`:197`，內容是自己的 pid），比對一定成立，行為和 R3 相同。**注意**：實機上 runId 一律是 `uuidgen`（合格），所以 R3x 起正常路徑是背景收尾，前景只剩退路。
- **`--skip-finalize`**：`:1080-1084` 在 R3x 步驟之前就 return，沒有改；鎖持有到 `exit`；`complete` 的 pid 比對同上。首次引導試錄的行為不變（全量測試兩輪都綠）。
- **`meeting record finish`**：`cmd_finish`（`record.sh:1200-1216`）只在 rc 0 時多呼叫 `clear_crashed_background`。它只刪 `finalizing/` 裡同場次、phase 為 `finalizing`、而且每場鎖沒人持有的檔。結束碼 0／3／5 的對映沒變。Python 端有兩項變化：預設平行度 3（錄製中 2），以及多了「收尾平行度：3」這行和進度行的新寫法；`MH_FINALIZE_WAIT_LOCK` 沒設，照 §4.28.1 立刻回 5。
- **`status`／`stop` 在沒有 `finalizing/` 時**：`cmd_status` 的主體只把 `sys.exit` 換成 `finish(…)`。`JOBS` 為空時 `finish` 就是 `sys.exit(rc)`，所以輸出逐字不變（4.52.6 的測試 ok）。`cmd_stop` 的 `stop_target_state` 在共用狀態檔的 runId 就是目標、又沒有 `background` 時回 `shared`，等同 R3 的 `status_of_run`。

**沒驗、但值得記下的觀察（都不 blocking）**：

- **N-1**：`bin/record.sh:973` 的註解還是「正規化 12/95」。§6 第 152 條把它列為「同一範例」，但沒有規定要改。只是文件落差，衍生工作（不編號）。
- **N-2**：`test_r3x_background` 4 支、`test_r3x_parallel_finalize` 1 支在 cleanup 時有 `ResourceWarning: unclosed file`。這是測試端的資源清理問題，不影響結果。改它等於修改 R3x 測試，屬衍生工作（不編號）。
- **N-3**：見 M2b。目前沒有測試斷言「被中止的段不會印『改用 libx264』」。產品碼現在不會印這一行（有 `except SegmentAborted`），只是缺一道擋回歸的測試。
- **N-4**：前景退回路徑（`backgroundEntryDecision` 回 `.foreground`）只有純函式測試與靜態形狀，沒有整合行為測試，也不在 §4.58 之內。實機上要遇到它，得 runId 不合格或每場鎖被占，正常操作碰不到。
- **N-5**：`record.log` 每行沒有時間戳（`Capture/Support.swift:28-34` 的 `Logger.line` 只寫原文），4.58.1 的「≤ 15 秒」沒辦法事後從 log 算出來。劇本 §7.1 改用加時間戳的 `tail` 當場量。
- **N-6**：`~/.meeting-harness/record.defaults.json` 的 `harness` 目前指向 `.worktrees/meeting-record`（不是 R3 epic worktree）。新版 app 用的是 `harness` 底下的 `_record_finalize.py`，所以不先改 `harness`，平行正規化與收尾鎖等待在實機都不會生效（spec §4.58 前置 2 已寫明）。

## 7. 實機劇本（§4.58 ＋ R3 尚未做的 verifier-r3.md §7.2–§7.11，合成一份）

以下 `<wt>`＝`/Users/yuktang/Documents/Agent/meeting-harness/.worktrees/meeting-record-r3`。整場只用 `<wt>/bin/meeting.sh`，不要用 `~/.claude/skills` 指到的主線版本。實機期間也請不要讓其他 session 開錄。結果寫進 run 目錄，只寫 run 代號與數字，不寫會議名、場次名或視窗標題。截圖若含場次名，不放進 repo。

### 7.0 前置（每一步都是不可逆或會改使用者設定，要使用者當下同意才做）

1. 確認沒有錄製在跑，上一場也收完了：`bash <wt>/bin/meeting.sh record status`。
2. **（要同意）備份**：`cp -p ~/.meeting-harness/record.defaults.json ~/.meeting-harness/record.defaults.json.bak-r3x`。記下鍵名（只看鍵）：`python3 -c "import json,os;print(sorted(json.load(open(os.path.expanduser('~/.meeting-harness/record.defaults.json')))))"`。目前的鍵是 `attendees, ffmpeg, harness, minFreeBytes, python3, root, type`。
3. **（要同意）只改 `harness` 鍵**，指到 `<wt>`，其他鍵不動：
   ```
   python3 - <<'PY'
   import json, os, tempfile
   p = os.path.expanduser('~/.meeting-harness/record.defaults.json')
   d = json.load(open(p, encoding='utf-8'))
   before = os.path.basename(d.get('harness', '').rstrip('/'))
   d['harness'] = '/Users/yuktang/Documents/Agent/meeting-harness/.worktrees/meeting-record-r3'
   fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p)); os.write(fd, json.dumps(d, ensure_ascii=False, indent=2).encode()); os.close(fd); os.replace(tmp, p)
   print('harness:', before, '->', os.path.basename(d['harness']), '| keys:', sorted(d))
   PY
   ```
   預期印出 `harness: meeting-record -> meeting-record-r3`，鍵名不變。
4. **（要同意）覆蓋安裝 app**：`bash <wt>/tools/MeetingRecorder/build.sh`（預設裝到 `~/Applications`；cdhash 會變，螢幕錄製、麥克風、Apple Events 的授權可能要重給）。結束舊的 menu bar，再重開 `~/Applications/MeetingRecorder.app`。
5. **（要同意）** `touch ~/.meeting-harness/keep-segments`（7.2 要用 A 的段落）。
6. `bash <wt>/bin/meeting.sh record windows`，再 `bash <wt>/bin/meeting.sh record preflight --window <id>`：13 項 hard 都要通過。
7. 開一個終端 T3 專門量時間（只濾兩種行，不會印出場次路徑）：
   ```
   tail -n0 -F ~/.meeting-harness/record.log | while IFS= read -r l; do case "$l" in *收到停止訊號*|*已放開開錄鎖*|*等上一場收尾完成*|*"● 收尾中"*) printf '%s %s\n' "$(date +%H:%M:%S)" "${l%%：*}";; esac; done
   ```

### 7.1 R3x 主場：A 停止 → 立刻開 B → A 背景收完 → B 正常（§4.58.1–§4.58.4、§4.54.8、§4.52.1、§4.52.4、§4.52.5、§4.49.3–§4.49.5、§4.48.4、§4.48.6、§4.54.4、§4.54.5、§4.54.7、§4.51.1）

1. 若要驗 §4.58.3 的自動前處理，先在設定確認「停止後自動前處理」是開著的。
2. 開錄 A（選單「開始錄製」，或在 T1 跑 `bash <wt>/bin/meeting.sh record <根> --window <id>`），錄 ≥ 10 分鐘，讓會議 app 持續有聲音。
3. **停止 A**：在 T1 跑 `bash <wt>/bin/meeting.sh record stop`。它會一直等到 A 背景收完，所以讓它在 T1 掛著。
   - 判準 4.58.1：T3 上「收到停止訊號」到「已放開開錄鎖」相差 ≤ 15 秒。記下秒數。
4. 放鎖後在 T2 跑 `bash <wt>/bin/meeting.sh record status`：要有 R3 的「收尾中 …」行，加一行「  背景收尾中，可以開始下一場」，rc 0（4.52.4）。打開選單：膠囊是收尾中（處理紫）；選單有「開始錄製」「錄其他視窗」「存到」「取消收尾」；狀態列是「背景收尾中…・<場次名>」（4.54.8、4.54.7）。截圖留在本機。
5. **立刻開 B**：在 T2 跑 `bash <wt>/bin/meeting.sh record <根> --window <id>`。用 CLI 開是為了同時看到 4.56.2 那一行。
   - stdout 在開錄前多一行「  ⚠ 上一場收尾還在跑（1 場），會再用掉一些磁碟空間；…」（4.56.2）。
   - B 開錄成功，沒有「已有錄製在跑」（4.48.7 的實機版）。
   - `record status`：先印 B 的錄製行，下面一行「  上一場收尾中：<A>」；A 排隊中時結尾是「（排隊中）」（4.52.1）。
   - 選單狀態列結尾是「（上一場收尾中）」（4.54.8）。
6. **等 A 收完**：
   - T1 的 `stop` 回 0。stdout 的「場次：」是 A，印「✓ 已停止並收尾完成。」（4.51.1 的實機版）。
   - `python3 -c "import json,glob,os;[print(os.path.basename(p), (lambda s:(s['phase'],s['code']))(json.load(open(p)))) for p in glob.glob(os.path.expanduser('~/.meeting-harness/finalizing/*.status.json'))]"`：A 那一場是 `('done', 0)`（4.58.3）。
   - A 的 `影片/`、`錄音/` 成品都在（只記「在／不在」）。
   - `python3 -c "import json,os;h=os.path.expanduser('~/.meeting-harness');s=json.load(open(h+'/record.status.json'));print(s['phase'], s['pid']==int(open(h+'/record.pid').read()))"` 印 `recording True`：共用狀態檔與 `record.pid` 仍是 B 的（4.49.4、4.49.5 的實機版）。
   - 完成通知只出現一次；自動前處理（若有開）對 A 只觸發一次，看 `~/.meeting-harness/autoprep.log` 裡 A 的 runId 只出現一次排入（只數次數，不記內容；4.54.5）。
   - 選單狀態列的「（上一場收尾中）」消失；`record status` 多一行「  上一場收尾完成：<A>」（4.52.5）。
   - T3 有 A 的「● 收尾中」。若 A 的收尾 log 有「收尾平行度：2」或「錄製中，收尾平行度降為 2」，就確認了 `MH_RECORD_HOME` 傳到子程序、`recording_in_progress` 也看得到 B（4.48.6）。
7. **B 錄 ≥ 10 分鐘後停止**：在 T1 跑 `bash <wt>/bin/meeting.sh record stop`，要回 0（4.58.4）。
   - 從 `record.log` 抓 B 各段的段落收尾行，算「未 ready 丟棄 影片／系統聲音／麥克風」與「影片 PTS 非遞增丟棄」的合計（只記數字）：`grep -oE '未 ready 丟棄 影片 [0-9]+／系統聲音 [0-9]+／麥克風 [0-9]+，影片 PTS 非遞增丟棄 [0-9]+' ~/.meeting-harness/record.log | tail -n <B 的段數>`。
   - 和 `bg` §8 的基準比：318 行中只有 1 行非零、影片丟 1 個。
   - 用 T3 的時間找出 B 錄製期間和 A 收尾重疊的時段。若這段時間的影片丟棄數 > 該時段影格數的 1%，就是 §7 疑慮 64 成立，要用選項式提問：(a) 錄製中降為 1；(b) 收尾子程序改用 `.utility` 或 `nice`；(c) 錄製中暫停背景收尾。

### 7.2 收尾時間：調整前後各量一次（§4.58.5）

前提：沒有錄製在跑（不然平行度會被降成 2）。

1. 複製 A（段落有保留）到暫存場次。暫存目錄用通用名稱，不帶場次名：
   ```
   B0="$(mktemp -d)/r3x-bench"; cp -R "<A 的場次>" "$B0"
   reset(){ rm -rf "$B0/影片"/* "$B0/錄音/tracks/finalize.json" "$B0/錄音/tracks/.finalize"; find "$B0/錄音" -maxdepth 1 -type f \( -name '*.wav' -o -name '*.m4a' -o -name '*.mov' \) -delete; }
   ```
2. 串行：`reset; /usr/bin/time -p env MH_FINALIZE_JOBS=1 bash <wt>/bin/meeting.sh record finish "$B0" > "$TMPDIR/j1.log" 2>&1`。
3. 預設：`reset; /usr/bin/time -p bash <wt>/bin/meeting.sh record finish "$B0" > "$TMPDIR/j3.log" 2>&1`。
4. 每份 log 都記牆鐘秒數（`real`）與 normalize 耗時合計：`grep -oE '^耗時 normalize（[^）]+）：[0-9.]+' "$TMPDIR/j1.log" | awk -F'：' '{s+=$2} END {print s}'`。也確認 `j3.log` 有「收尾平行度：3」、`j1.log` 有「收尾平行度：1（MH_FINALIZE_JOBS=1）」。
5. 判準：預設比 `MH_FINALIZE_JOBS=1` 快就是 PASS（預期約快 15–20%）；預設較慢判 FAIL 並回報。
6. 量完 `rm -rf "$(dirname "$B0")"`。

### 7.3 （選做）兩場都在背景時的排隊與排隊中取消（§4.50.3、§4.50.6、§4.51.4、疑慮 67）

1. 錄 A 約 3 分鐘，停止（用選單，不用等）。A 收尾中時開 B，B 錄約 1 分鐘就停止。
2. B 停止後 `record status` 應該看到 B 的「收尾中 …」與「背景收尾中，可以開始下一場」，A 列為「上一場收尾中」。`record.log`（T3）出現「等上一場收尾完成（排隊中）」。
3. 兩場都收完以後，T3 上 B 的「● 收尾中」時間要晚於 A 結束（兩段收尾不重疊）。
4. 在 T1 跑 `record stop`（兩場都在背景、沒有 `record.pid` 時）：印「沒有錄製在跑；等背景收尾完成（不送停止訊號）…」，等兩場都結束，回 0（4.51.4）。
5. （選做 4.50.6）再做一次步驟 1，在 B 還排隊時按選單「取消收尾」。注意：取消的對象是 `backgroundCancelCandidate`，也就是正在跑的 A，不是排隊中的 B（4.50.4 的設計）。要測排隊中取消，得等 A 收完前、只剩 B 排隊時才做得到，實際上很難湊；做不到就記「未做」。

### 7.4 （選做）取消背景收尾（§4.58.6、§4.50.5、§4.50.9、§4.49.6）

1. 錄 A 約 2 分鐘，停止。不開下一場。
2. A 背景收尾中，按選單「取消收尾」：確認框的內文只有「要取消「M/d HH:mm 開始的場次」的收尾嗎？段落會保留，之後可以用 meeting record finish 收完。」，沒有會議名；預設鍵是「繼續收尾」，按 Return 不會取消。
3. 再按一次，選「取消收尾」：A 的每場狀態檔變成 `failed`、code 5，訊息含「收尾已取消」。沒有下一場時，共用狀態檔也是 A 的 `failed`（4.49.6 的實機版）。段落都在。
4. `bash <wt>/bin/meeting.sh record finish "<A 的場次>"` 回 0。

### 7.5 R3 尚未做的實機項目（verifier-r3.md §7.2–§7.11，指令改用 `<wt>/bin/meeting.sh`）

R3x 對這些項目的影響已標在各條後面。

- **7.5.1 首次引導與試錄**（verifier-r3.md §7.1；§4.47.8、§4.47.13）：照原劇本做。`--skip-finalize` 不受 R3x 影響，試錄會照 R3 持鎖到結束。
- **7.5.2 F3 會議偵測**（§7.2；§4.47.6、§4.44.3）：照原劇本做。R3x 加一步：A 背景收尾中、沒有錄製時，開一個會議 app 並讓它用麥克風，應該**會**提示「錄這個會議？」（§6 第 151 條、4.54.6）。
- **7.5.3 錄製中綜合場**（§7.3；§4.47.3、§4.47.4、§4.47.12(a)、§4.26.2、§4.26.6、§4.37.6、§4.38.3、§4.38.4、§4.40.4、§4.40.7、§4.40.8、§4.41.4）：第 1–10 步照原劇本。**第 11 步要改**：R3x 起停止後就進背景收尾，選單是「背景收尾中」階段，「取消收尾」會先跳確認框（7.4 的流程），不是 R3 那種直接取消。要驗 R3 的前景取消（§4.28.6），只能等前景退回路徑，正常操作碰不到（§6 N-4）。所以第 11 步以 7.4 的結果代替，判準不變：`failed`、code 5、「收尾已取消」、`finish` 回 0。
- **7.5.4 圖示被擋住與快捷鍵回饋**（§7.4；§4.47.12(b)、§4.40.3、§4.40.5）：照原劇本做。
- **7.5.5 F2 捨棄**（§7.5；§4.47.7、§4.42.2、§4.42.3）：照原劇本做。捨棄不會進背景，`finalizing/` 不應多出檔案：做前後各 `ls ~/.meeting-harness/finalizing/ | wc -l` 比一次。
- **7.5.6 E4 聲學回授**（§7.6；§4.47.1、§4.35.3）：照原劇本做。這幾場收尾會走背景路徑，`record stop` 照樣會等到收完。
- **7.5.7 E2 補償型播放端，決定 S-C 預設**（§7.7；§4.47.2、§4.37.7、§4.37.8）：照原劇本做，用 `<wt>/bin/meeting.sh sync …` 與 `record finish`。最後要使用者決定 S-C 預設與疑慮 60。
- **7.5.8 提醒事項**（§7.8；§4.47.5、§4.34.3）：照原劇本做。
- **7.5.9 真實多人會議**（§7.9；§4.47.9、疑慮 50、63）：照原劇本做。可以和 7.1 合併：讓 7.1 的 A 或 B 就是真實會議，結果只寫數字。
- **7.5.10 全套 e2e 迴歸**（§7.10；§4.47.10、§4.36.10、§4.25.1）：照原劇本做。再加一次 `MH_FINALIZE_JOBS=1 bash <wt>/bin/meeting.sh record finish <場次>`，跑完再過 `e2e_check.py` 一次，確認串行和平行的判準相同（4.55.14 的實機版）。
- **7.5.11 設計審查截圖**（§7.11；§4.47.11 等）：原清單加上 R3x 的畫面——「背景收尾中」階段的選單、錄製中狀態列的「（上一場收尾中）」、背景取消確認框、`.failed`＋背景收尾時 toolTip 的錯誤內容（疑慮 77）。

### 7.6 收尾（要使用者決定）

1. `harness` 要還原還是保留，由使用者決定。還原：`cp -p ~/.meeting-harness/record.defaults.json.bak-r3x ~/.meeting-harness/record.defaults.json`，再用 7.0-2 的指令看鍵名；保留則刪掉備份檔。
2. 刪 `~/.meeting-harness/keep-segments`；跑 `bash <wt>/bin/meeting.sh sync off`；`hudMode` 改回使用者要的值。
3. `~/.meeting-harness/finalizing/` 的終態檔會在 24 小時後由下一場清掉，不用手動刪。
4. 結果寫進 run 目錄後，進閘門。

## 8. 待決（都不 blocking）

- N-3：「被中止的段不印『改用 libx264』」沒有測試擋回歸。選項：(a) 接受，spec 沒有規定這一行，x264 也確實不會啟動（建議）；(b) 衍生工作：新增一支測試（不改既有測試），在 4.55.10 的情境斷言 stdout 不含「改用 libx264」，代價是多一支約 3 秒的測試
- N-1、N-2：衍生工作（不編號）
- N-4：前景退回路徑沒有整合行為測試。選項：(a) 接受，只有 runId 不合格或每場鎖被占才會走到（建議）；(b) 衍生工作：用替身模擬每場鎖被占，驗 `record.sh stop` 照 R3 等共用狀態檔
- 實機前置 7.0 第 2–5 步都要使用者當下同意

## 9. 範圍

- **涵蓋**：§4.48–§4.57 每條的自動部分。具體包括：Python 378 支跑 2 輪、Swift 139 支、暫存建置與 entitlements、verify、check_rules；spec 引用的 91 個測試逐一對 ok；R3x-§6 第 145–157 條與 Red 層補字面逐條對實際狀態；替身與 Swift 協定逐點讀碼；既有測試修改逐行對條文；Red 之後測試沒動；skip、mock、吞錯誤、湊字面檢查（Swift 46 個、Python 21 個程式字面，去字串後重驗）；10 個突變；前景收尾、`--skip-finalize`、`finish` 的回歸讀碼；名稱掃描（只報有或沒有）
- **未涵蓋（需實機）**：§4.58 全部、§4.54.8，以及 §2 標「PASS＋需實機」的 17 條的實機部分。原因：要使用者在場、要啟動 app 或觸發 TCC，派工約束不允許
- **未涵蓋（其他）**：沒有實錄，也沒有在暫存 home 手動跑 CLI，`record.sh` 的新行為只由 `test_r3x_background.py` 的替身場景與讀碼覆蓋；前景退回路徑只有純函式與讀碼證據（N-4）

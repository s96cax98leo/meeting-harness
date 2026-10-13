# 驗證報告：meeting-record R3（sdlc-test 段）

- 驗證對象：`feature/meeting-record-r3` @ `091d7757e2744c927dd8caa6bb9ff62ccf099a42`（worktree `.worktrees/meeting-record-r3`；開工、全量測試跑完、寫本檔前各查一次 HEAD，三次相同）。反作弊範圍 `377dd92`（`origin/main`）`..091d775`
- 驗收依據：`specs/meeting-record/spec.md` 檔尾〈R3 第三輪〉§4.26–§4.46 逐條；R3-§6 第 117–141 條（撤回的 117、122、125 只確認「既有測試沒改」）。§4.47 實機驗收場要使用者在場，本段不驗，只排成劇本（本檔 §7）
- 背景資料：plan §10、design R3-D1–D30、`adr/adr-r3-*.md`、`progress.md`
- 環境：macOS（Darwin 25.6.0，arm64）。每個指令都帶 `TMPDIR=$(mktemp -d) LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=<run 目錄>/client-names.txt`（`<run 目錄>`＝`_tpm/runs/20261010-sdlc-meeting-record`），日誌寫在各自的 `$TMPDIR`。名稱清單沒有讀出，也沒有寫進任何檔
- 安全邊界：錄製器只建到 `MH_RECORDER_DEST=$(mktemp -d)`，用完即刪；沒有啟動 app、沒有安裝到 `~/Applications`（建置前後 mtime 相同）、沒有觸發 TCC、沒有對任何 MeetingRecorder 程序送訊號；手動 CLI 一律 `MH_RECORD_HOME=$(mktemp -d)`。突變抽查在 `git archive HEAD` 解出的暫存複本上做，repo 內沒動
- 寫檔範圍：只寫本檔

## 1. 機械檢查（本輪在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0；`✓ lint 通過（26 個檔）`；doctor 輸出 `✗` 0 個 |
| V2 | `python3 -m unittest discover -v -s tests/record -t .`，跑 3 輪 | 第 1 輪 `Ran 304 tests in 591.8s`、`OK`；第 2 輪 597.8s `OK`；第 3 輪 622.0s `OK`；三輪 rc 都是 0，FAIL／ERROR／skipped 都是 0，沒有偶發失敗。`tests/record/test_*.py` 的 `def test_` 也是 304 個。條件式的 4 支（`test_downstream_missing_sections`、`OnboardingSettingsStatic.test_no_client_names`、`test_no_client_names_in_r3_files`、`test_no_client_names_in_repo_text`）都是 `ok`，不是 skip |
| V3 | `/bin/bash tools/MeetingRecorder/Tests/run.sh` | rc=0，`共 123 支，失敗 0 支`；`Tests/*.swift` 的 `func test` 也是 123 個 |
| V4 | `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`，再 `codesign -d --entitlements - --xml`、`codesign -dvv` | rc=0，編譯 39 個檔。entitlements **恰為 3 項**：`automation.apple-events`、`device.audio-input`、`personal-information.calendars`，值都是 true；`Identifier=com.meetingharness.recorder`、`flags=0x10000(runtime)`、`Authority=MeetingHarness Dev`；bundle 內有 `Contents/Resources/AppIcon.icns`、`CFBundleIconFile`＝`AppIcon` |
| V5 | `python3 .claude/teams/tools/check_rules.py --git . 377dd92..HEAD` | rc=0，`規則檢查：通過` |
| V6 | 從 spec §4.26–§4.46 測試欄抽出全部 `檔::函式`，逐一對 V2 第 1 輪與 V3 的 ok 清單 | 135 列（含撤回的 4.45.2）、166 個測試引用；找不到或沒通過的 0 個 |
| V7 | 名稱掃描：`grep -qiF -f <清單>` 比對 `git diff 377dd92..HEAD`、`git log --format=%B 377dd92..HEAD`，再逐一掃 `git ls-files` 與 R3 改動的每個檔 | diff：沒有；commit 訊息：沒有；追蹤檔：沒有；R3 改動檔：沒有 |
| V8 | 暫存 `MH_RECORD_HOME` 下手動跑 `meeting sync`／`sync reported`／`sync foo`／`sync a b`／壞檔後 `sync off`、`meeting search`（缺參數、根不存在、沒結果）、`meeting reminders`（缺參數）、`meeting record stop`（沒有錄製）、`meeting record help`、`meeting help` | `sync` rc=0 印 `syncCompensation=off`；`sync reported` rc=0 印「（下一次收尾起生效）」、檔案只有 `syncCompensation` 一鍵；`sync foo`、`sync a b` rc=2；`record.defaults.json` 為 `[1]` 時 `sync off` rc=2、檔案不變；`search` 缺參數 rc=2、根不存在 rc=2、沒結果 rc=1 且 stdout 空；`reminders` 缺參數 rc=2；`record stop` rc=3（stderr 見缺陷 D1）；`record help` rc=0；`meeting help` 的「其他指令」段有 `meeting search `、`meeting sync` 兩行，`  meeting record` 行仍是 12 行 |
| V9 | 突變抽查 7 個（見 §5.1） | 6 個被測試擋下；1 個是等價突變 |

## 2. 逐條結果（§4.26–§4.46）

結果只用 PASS、FAIL、需實機。同一條有自動部分、也有實機或設計審查部分時寫「PASS＋需實機」：自動部分已通過，實機部分列進 §7 的劇本。「測試」欄每一支都經 V6 對到 ok；靜態測試另外讀產品碼確認字面是真的被呼叫（§5）。

**統計**：共 135 列，其中 4.45.2 已撤回（既有測試照舊通過）。有效 134 條：**PASS 115**、**PASS＋需實機 18**、**需實機 1**（4.39.4，只有設計審查）、**FAIL 0**。

### §4.26 開錄鎖、preflight 互斥、暫停心跳（Q1、Q2、D14b）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.26.1 | PASS | `swift:R3LockTests.swift::testAcquireRecordLock` | — |
| 4.26.2 | PASS＋需實機 | `test_r3_app_static.py::LockStatic.test_lock_before_status_writer` | 實機：錄製中再開一個錄製實例被拒、log 有「已有錄製在跑」 |
| 4.26.3 | PASS | `test_r3_lock.py::test_record_refused_when_locked` | — |
| 4.26.4 | PASS | `test_r3_lock.py::test_preflight_refused_when_recording` | — |
| 4.26.5 | PASS | `test_r3_lock.py::test_try_lock_releases` | — |
| 4.26.6 | PASS＋需實機 | `swift:R3LockTests.swift::testPausedHeartbeatConstant`、`test_r3_app_static.py::LockStatic.test_paused_heartbeat` | 實機：暫停 30 秒，`updatedAt` 至少前進 5 次 |
| 4.26.7 | PASS | `test_r3_lock.py::test_concurrent_record_only_one_wins` | — |

### §4.27 `stop` 只停錄製器（Q5）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.27.1 | PASS | `swift:R3LockTests.swift::testStopTargetDecision` | — |
| 4.27.2 | PASS | `test_r3_lock.py::test_stop_refuses_foreign_pid`、`test_r3_lock.py::test_stop_cleans_dead_pid`、`test_r3_lock.py::test_stop_refuses_without_lock`、`test_r3_lock.py::test_comm_override_needs_record_open` | — |
| 4.27.3 | PASS | `test_r3_lock.py::test_stop_does_not_resignal_while_finalizing` | — |
| 4.27.5 | PASS | `test_r3_lock.py::test_stop_wait_limit_covers_finalize_deadline` | — |
| 4.27.6 | PASS | `test_r3_lock.py::test_fake_recorder_holds_lock` | — |
| 4.27.4 | PASS | `test_r3_app_static.py::MenuBarStatesStatic.test_stop_uses_decision` | — |

### §4.28 收尾鎖、逾時、取消、讀不到的段落（Q4、Q3、D12、D14a）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.28.1 | PASS | `test_r3_finalize_guard.py::test_second_finalize_refused` | — |
| 4.28.2 | PASS | `test_r3_finalize_guard.py::test_atomic_write_uses_mkstemp` | — |
| 4.28.3 | PASS | `test_r3_finalize_guard.py::test_step_timeout_exits_5_and_keeps_segments` | — |
| 4.28.4 | PASS | `test_r3_finalize_guard.py::test_step_timeout_values` | — |
| 4.28.5 | PASS | `swift:R3LockTests.swift::testFinalizeDeadline` | — |
| 4.28.6 | PASS＋需實機 | `test_r3_app_static.py::FinalizeRunnerStatic.test_deadline_and_cancel` | 實機：收尾中按「取消收尾」 |
| 4.28.7 | PASS | `test_r3_finalize_guard.py::test_unreadable_moved_not_deleted` | — |
| 4.28.8 | PASS | `test_r3_finalize_guard.py::test_step_durations_logged` | — |

### §4.29 VTT 講者、raw 不重轉、無效參數（T1、T2、T3）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.29.1 | PASS | `test_r3_vtt_raw.py::test_vtt_uses_merge_assignment` | — |
| 4.29.2 | PASS | `test_r3_vtt_raw.py::test_render_has_no_private_ratio` | — |
| 4.29.3 | PASS | `test_r3_vtt_raw.py::test_diarize_keeps_raw` | — |
| 4.29.5 | PASS | `test_r3_vtt_raw.py::test_render_copy_matches_merge` | — |
| 4.29.4 | PASS | `test_r3_vtt_raw.py::test_no_compression_flag` | — |

### §4.30 VAD clip 與品質檔（T4、T5）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.30.1 | PASS | `test_r3_transcript_vad.py::test_clip_passed_to_asr` | — |
| 4.30.2 | PASS | `test_r3_transcript_vad.py::test_fallback_without_levels` | — |
| 4.30.3 | PASS | `test_r3_transcript_vad.py::test_vad_env_overrides` | — |
| 4.30.4 | PASS | `test_r3_transcript_vad.py::test_segments_always_written` | — |
| 4.30.5 | PASS | `test_r3_transcript_vad.py::test_quality_file` | — |
| 4.30.6 | PASS | `test_r3_annotations.py::test_unclear_marked_in_derived_only` | — |

### §4.31 標示與標記（T6、T7、D11）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.31.1 | PASS | `test_r3_annotations.py::test_annotations_in_speakers_and_vtt` | — |
| 4.31.2 | PASS | `test_r3_annotations.py::test_long_silence_threshold` | — |
| 4.31.3 | PASS | `test_r3_annotations.py::test_marker_alignment` | — |
| 4.31.4 | PASS | `test_r3_annotations.py::test_schema_markers_optional` | — |
| 4.31.5 | PASS | `test_r3_annotations.py::test_summary_sections`、`test_r3_annotations.py::test_summary_unchanged_without_events` | — |
| 4.31.6 | PASS | `test_r3_annotations.py::test_markers_source_precedence` | — |
| 4.31.7 | PASS | `test_r3_annotations.py::test_no_device_names` | — |
| 4.31.9 | PASS | `test_r3_annotations.py::test_local_summary_sections` | — |
| 4.31.10 | PASS | `test_r3_vtt_raw.py::test_annotate_hook_noop`、`test_r3_annotations.py::test_speakers_post_process`、`test_r3_annotations.py::test_speakers_post_process_idempotent` | — |
| 4.31.8 | PASS | `test_r3_annotations.py::test_downstream_missing_sections` | — |

### §4.32 `_record_lib.py` 與共用向量（Q9a）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.32.1 | PASS | `test_r3_record_lib.py::test_output_time_vectors`、`swift:R3RecordLibVectorTests.swift::testOutputTimeVectors` | — |
| 4.32.2 | PASS | `test_r3_record_lib.py::test_levels_intervals_vectors`、`swift:R3RecordLibVectorTests.swift::testLevelsIntervalsVectors` | — |
| 4.32.3 | PASS | `test_r3_record_lib.py::test_paused_total_and_clip_none` | — |
| 4.32.4 | PASS | `test_r3_record_lib.py::test_cli_clip` | — |
| 4.32.5 | PASS | `test_r3_record_lib.py::test_bin_lib_syntax`、`test_regression.py::test_lint_passes_26_files` | — |
| 4.32.6 | PASS | `test_r3_record_lib.py::test_merge_defaults` | — |

### §4.33 `meeting search`（F1）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.33.1 | PASS | `test_r3_search.py::test_hits_sorted_and_literal` | — |
| 4.33.2 | PASS | `test_r3_search.py::test_exit_codes` | — |
| 4.33.3 | PASS | `test_r3_search.py::test_single_root_only` | — |
| 4.33.4 | PASS | `test_r3_search.py::test_usage_lists_search` | — |

### §4.34 提醒事項（F5）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.34.1 | PASS | `test_r3_reminders.py::test_dry_run_items`、`test_r3_reminders.py::test_uid_matches_ics` | — |
| 4.34.2 | PASS | `test_r3_reminders.py::test_invokes_app_and_maps_code` | — |
| 4.34.3 | PASS＋需實機 | `test_r3_app_static.py::RemindersStatic.test_eventkit_shape` | 實機：權限框、寫入兩次第二次 created=0（§4.47.5） |
| 4.34.4 | PASS | `test_r3_docs.py::test_reminders_documented` | — |

### §4.35 影音一致的量測與延遲紀錄（S-A、D3、S-B）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.35.1 | PASS | 既有 `test_e2e_check.py::test_hfp_and_sync_check` ok；該檔不在 R3 diff | — |
| 4.35.2 | PASS | `test_r3_sync_measure.py::test_sync_player_median` | — |
| 4.35.3 | PASS | `test_r3_sync_measure.py::test_sync_acoustic_report` | — |
| 4.35.4 | PASS | `test_r3_sync_measure.py::test_print_sync_file` | — |
| 4.35.5 | PASS | `swift:R3SyncTests.swift::testReportedLatency` | — |
| 4.35.6 | PASS | `swift:R3SyncTests.swift::testOutputLatenciesOmittedWhenNil` | — |
| 4.35.7 | PASS | `test_r3_app_static.py::LatencyLogStatic.test_latency_read_only` | — |

### §4.36 `SegmentScheduler`（Q6）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.36.1 | PASS | `swift:R3SegmentSchedulerTests.swift::testFirstSample` | — |
| 4.36.2 | PASS | `swift:R3SegmentSchedulerTests.swift::testPeriodicSwitchAndPrevClose` | — |
| 4.36.3 | PASS | `swift:R3SegmentSchedulerTests.swift::testPrevTimeout` | — |
| 4.36.4 | PASS | `swift:R3SegmentSchedulerTests.swift::testPauseResume`、`swift:R3SegmentSchedulerTests.swift::testPauseEmptySegmentCancelled` | — |
| 4.36.5 | PASS | `swift:R3SegmentSchedulerTests.swift::testStopFinishOrCancel` | — |
| 4.36.6 | PASS | `swift:R3SegmentSchedulerTests.swift::testWriterFailureRepeated` | — |
| 4.36.7 | PASS | `swift:R3SegmentSchedulerTests.swift::testFormatChange` | — |
| 4.36.8 | PASS | `swift:R3SegmentSchedulerTests.swift::testOutputDeviceChange` | — |
| 4.36.9 | PASS | `swift:R3SyncTests.swift::testSwitchReasonCases`、`ControlTests.swift::testPauseGateAndSwitchReason` | — |
| 4.36.10 | PASS＋需實機 | `test_r3_app_static.py::SegmentSchedulerStatic.test_session_delegates_to_scheduler` | 實機：全套 e2e 迴歸（§4.47.10） |
| 4.36.11 | PASS | `test_r2_static.py::test_capture_pause_gate_before_maxend`、`test_r2_static.py::test_capture_uses_core_pause_functions`、`test_static_rules.py::test_segment_writer_uses_assetwriter` | — |

### §4.37 S-C：依時段補償系統聲音

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.37.1 | PASS | `test_r3_search.py::test_meeting_sync_cli` | — |
| 4.37.2 | PASS | `test_r3_sync_compensate.py::test_mode_resolution` | — |
| 4.37.3 | PASS | `test_r3_sync_compensate.py::test_off_equivalent` | — |
| 4.37.4 | PASS | `test_r3_sync_compensate.py::test_reported_delays_per_segment`、`test_r3_sync_compensate.py::test_constant_delay_no_gaps`、`test_r3_sync_compensate.py::test_delay_decrease_trims_overlap` | — |
| 4.37.5 | PASS | `test_r3_sync_compensate.py::test_calibrated_lookup_and_clamp` | — |
| 4.37.6 | PASS＋需實機 | `test_r3_app_static.py::SyncCompensateStatic.test_device_change_split` | 實機：換輸出裝置後段界與 `deviceEvents.t` 差 < 0.5 秒 |
| 4.37.7 | PASS | `test_r3_sync_compensate.py::test_sync_player_with_compensation` | — |
| 4.37.8 | PASS | `test_r3_sync_compensate.py::test_default_off` | — |

### §4.38 選單列圖示 8 種外觀（U1）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.38.1 | PASS | `swift:R3MenuBarTests.swift::testAppearanceMapping` | — |
| 4.38.2 | PASS | `swift:R3MenuBarTests.swift::testSpokenDuration` | — |
| 4.38.3 | PASS＋需實機 | `test_r3_app_static.py::MenuBarStatesStatic.test_capsule_drawing`、`test_r2_static.py::test_trigger_status_item_variable_length` | 設計審查截圖（§4.47.11） |
| 4.38.4 | PASS＋需實機 | `test_r3_app_static.py::MenuBarStatesStatic.test_autosave_name` | 實機：拖動圖示後重開仍保留位置 |
| 4.38.5 | PASS | `swift:R3DesignTokenTests.swift::testCapsuleStyleTable` | — |
| 4.38.6 | PASS | `swift:R3DesignTokenTests.swift::testCapsuleContrast`、`swift:R3DesignTokenTests.swift::testCapsuleShapesDistinct`、`swift:R3DesignTokenTests.swift::testContrastRatio` | — |
| 4.38.7 | PASS | `swift:R3DesignTokenTests.swift::testMenuBarAccessibilityLabel`、`test_r3_app_static.py::MenuBarStatesStatic.test_capsule_drawing` | — |
| 4.38.8 | PASS | `swift:R3DesignTokenTests.swift::testColorTokens`、`swift:R3DesignTokenTests.swift::testTypeAndMetricTokens` | — |

### §4.39 通知分級（U3）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.39.1 | PASS | `swift:R3MenuBarTests.swift::testNotificationPolicy` | — |
| 4.39.2 | PASS | `swift:R3MenuBarTests.swift::testNewAlertWarnings` | — |
| 4.39.3 | PASS＋需實機 | `test_r3_app_static.py::NotifyStatic.test_policy_applied` | 實機：Time Sensitive 是否生效、通知不含場次名與視窗標題（§4.47.4） |
| 4.39.4 | 需實機 | — | 設計審查（通知為系統原生外觀，沒有自動測試） |

### §4.40 HUD（U2；推翻 §6 第 105、106 條）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.40.1 | PASS | `swift:R3MenuBarTests.swift::testHudVisible` | — |
| 4.40.2 | PASS | `swift:R3MenuBarTests.swift::testFeedbackRoute` | — |
| 4.40.3 | PASS | `swift:R3MenuBarTests.swift::testObscuredAction` | — |
| 4.40.4 | PASS＋需實機 | `test_r3_app_static.py::HudStatic.test_panel_shape`、`test_r3_app_static.py::test_edge_tab` | 設計審查；實機：分享整個螢幕時 HUD 是否被分享（§4.47.3） |
| 4.40.5 | PASS＋需實機 | `test_r3_app_static.py::HudStatic.test_feedback_route_used` | 實機觀察：HUD 上加標記沒有可見回饋、`never` 時的快捷鍵通知（§4.47.12） |
| 4.40.6 | PASS | `swift:R3LockTests.swift::testMenuBarSettingsDefaults` | — |
| 4.40.7 | PASS＋需實機 | `test_r3_app_static.py::HudStatic.test_alert_emphasis` | 實機：拔麥克風觸發告警時 HUD 自動展開（§4.47.4 同場） |
| 4.40.8 | PASS＋需實機 | `test_r3_app_static.py::HudStatic.test_accessibility_modes` | 設計審查（減少透明度、增加對比、減少動態效果） |

### §4.41 選單依階段（U6；推翻 §4.20.6 的「灰掉不隱藏」）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.41.1 | PASS | `swift:R3MenuBarTests.swift::testMenuStage` | — |
| 4.41.2 | PASS | `swift:R3MenuBarTests.swift::testMenuItemsPerStage` | — |
| 4.41.3 | PASS | `test_r3_app_static.py::MenuStagesStatic.test_menu_built_from_stage`、`test_r3_app_static.py::test_titles_r3`、`test_r2_static.py::test_trigger_menu_items_r2`、`test_static_rules.py::test_start_item_shows_hotkey` | — |
| 4.41.4 | PASS＋需實機 | `test_r3_app_static.py::MenuStagesStatic.test_level_meter_accessibility`、`swift:R3DesignTokenTests.swift::testLevelFraction` | 實機：鍵盤導覽與 VoiceOver |
| 4.41.5 | PASS | `test_r3_app_static.py::MenuStagesStatic.test_failure_detail` | — |
| 4.41.6 | PASS | `test_r3_app_static.py::MenuStagesStatic.test_cancel_finalize` | — |
| 4.41.7 | PASS | `swift:R3MenuBarTests.swift::testMenuGroups` | — |

### §4.42 捨棄這次錄製（F2）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.42.1 | PASS | `swift:R3LockTests.swift::testDiscardRequestValid` | — |
| 4.42.2 | PASS | `test_r3_app_static.py::DiscardStatic.test_confirm_then_request` | — |
| 4.42.3 | PASS＋需實機 | `test_r3_app_static.py::DiscardStatic.test_trash_not_delete` | 實機：垃圾桶中可「放回原處」（§4.47.7） |
| 4.42.4 | PASS | `test_r3_app_static.py::DiscardStatic.test_stale_request_ignored` | — |
| 4.42.5 | PASS | `swift:R3LockTests.swift::testDiscardedNoAutoPrep` | — |
| 4.42.6 | PASS | `test_r3_docs.py::test_no_discard_cli` | — |

### §4.43 首次引導、設定分頁、app 圖示（U4、U5、U7；推翻 R2-Q3）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.43.1 | PASS | `swift:R3LockTests.swift::testMergedDefaults` | — |
| 4.43.2 | PASS | `test_r3_lock.py::test_write_defaults_merges`、`test_r3_lock.py::test_write_defaults_refuses_broken_file` | — |
| 4.43.3 | PASS | `test_r3_lock.py::test_defaults_lock_serializes` | — |
| 4.43.4 | PASS | `swift:R3LockTests.swift::testMenuBarSettingsDefaults`、`swift:R3LockTests.swift::testMenuBarSettingsRoundTrip` | — |
| 4.43.5 | PASS＋需實機 | `test_r3_app_static.py::OnboardingSettingsStatic.test_onboarding_flow_shape`、`test_r2_static.py::test_defaults_single_writer` | 實機：引導 5 步（§4.47.8）、試錄通知（§4.47.13） |
| 4.43.6 | PASS | `test_r3_app_static.py::OnboardingSettingsStatic.test_settings_tabs`、`swift:R3DesignTokenTests.swift::testSettingsTabs`、`test_r2_static.py::test_trigger_preferences_window` | — |
| 4.43.7 | PASS＋需實機 | `test_r3_app_static.py::OnboardingSettingsStatic.test_app_icon_bundled` | 設計審查：16／32／128 px 截圖 |
| 4.43.8 | PASS | `test_r3_app_static.py::OnboardingSettingsStatic.test_no_client_names` | — |
| 4.43.9 | PASS | `test_r3_app_static.py::OnboardingSettingsStatic.test_no_bundled_fonts` | — |

### §4.44 會議偵測提示（F3；推翻 R2「會議自動偵測在範圍外」）

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.44.1 | PASS | `swift:R3MenuBarTests.swift::testMeetingPromptDecision` | — |
| 4.44.2 | PASS | `test_r3_app_static.py::MeetingDetectStatic.test_read_only_detection` | — |
| 4.44.3 | PASS＋需實機 | `test_r3_app_static.py::MeetingDetectStatic.test_prompt_actions` | 實機：F3 提示（§4.47.6） |
| 4.44.4 | PASS | `test_r3_app_static.py::MeetingDetectStatic.test_toggle_in_settings` | — |

### §4.45 文件與 CLI 表面

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.45.1 | PASS | `test_r3_search.py::test_usage_lists_search` | — |
| 4.45.2 | 撤回 | `test_record_sh.py::test_exit_code_matrix`；撤回；既有 `test_record_sh.py::test_exit_code_matrix` ok、該檔不在 R3 diff | — |
| 4.45.3 | PASS | `test_r3_docs.py::test_record_skill_r3`、`test_r3_transcript_vad.py::test_transcribe_skill_updated`、`test_r3_annotations.py::test_notes_skill_updated` | — |

### §4.46 迴歸與 verify

| 節 | 結果 | 測試（全部 ok） | 實機／設計審查部分 |
|---|---|---|---|
| 4.46.1 | PASS | `test_regression.py::test_lint_passes_26_files` | — |
| 4.46.2 | PASS | V2 三輪 304／304 ok、V3 123／123 ok、V4 建置 rc=0 | — |
| 4.46.3 | PASS | `test_regression.py::test_diarize_and_merge_untouched` | — |
| 4.46.4 | PASS | `test_r3_docs.py::test_no_client_names_in_r3_files` | — |

## 3. R3-§6 第 117–141 條的實際狀態

| 條 | 狀態 | 證據 |
|---|---|---|
| 117 | 撤回，確認一致 | `surface.py`、`test_surface_parsers.py`、`test_cli_dispatch.py`、`test_docs.py`、`test_record_sh.py` 都不在 R3 diff；V8 `meeting help` 的 `meeting record` 仍 12 行；`meeting record sync` 不是寫法 |
| 118 | 一致 | `test_r2_static.py` 的 `MENU_TITLES` 改成「每個都出現」＋`menuItems(stage:` 被呼叫；`assert_key` 快捷鍵、「繼續錄製」「canControl」斷言不變；`levelLine`→`LevelMeterView`。`MenuBar.swift:274` 以 `menuItems(stage:)` 決定 `isHidden` |
| 119 | 一致 | `bin/record.sh` 的 `cmd_preflight` 試鎖被持有回 2；`test_preflight_refused_when_recording` ok；既有 preflight 測試沒改 |
| 120 | 一致 | `test_t7_fixes.py` 只新增斷言、原斷言不動；`MenuBar.swift:738-745` 只在 `.notification` 分支發回饋通知 |
| 121 | 一致 | `test_t7_fixes.py` 只新增 `obscuredCheckSeconds`、`obscuredAction(` 兩個斷言；`MenuBar.swift:169` 以 `obscuredCheckSeconds` 重複計時、`:986` 呼叫 `obscuredAction(` |
| 122 | 撤回，確認一致 | `bin/_merge_speakers.py`、`bin/diarize.sh` 不在 R3 diff；`test_regression.py` 不在 diff、`test_diarize_and_merge_untouched` ok |
| 123 | 一致 | `test_defaults_single_writer` 改法同條文；寫 `record.defaults.json` 的 Swift 只有 `Core/Settings.swift`（`rename` 寫入），其他檔只讀；`writeOnboardingDefaults(` 的呼叫端只有 `Trigger/Onboarding.swift:949`（讀碼確認，見 §6 第 4 點） |
| 124 | 一致 | `test_e2e_check.py` 不在 diff；`test_hfp_and_sync_check` ok；`--sync-player` 新增在 `e2e_check.py` |
| 125 | 撤回，確認一致 | `bin/` 頂層沒有新檔（新檔都在 `bin/lib/`）；V1 26 個檔；`test_lint_passes_26_files` ok |
| 126 | 一致 | `test_finalize.py` 不在 diff；`test_unreadable_moved_not_deleted` ok |
| 127 | 一致 | `ControlTests.swift` 只改 `expectedReasons` 一項與訊息「恰為六個」 |
| 128 | 一致 | `MenuBarState`、`symbolName` 保留；`TriggerTests.swift` 不在 diff |
| 129 | 一致 | `test_r2_static.py:191` 的 tuple 只把 `systemRed` 換成 `menuBarCapsuleStyle(`；`test_menubar_uses_template_image` 不在 diff 的改動範圍；`MenuBar.swift` 沒有 `systemRed`、`contentTintColor` |
| 130 | 一致 | `test_r2_static.py:275` 的 tuple 只把「MeetingRecorder 設定」換成 `settingsTab(`；`test_start_item_shows_hotkey` 沒改 |
| 131 | 一致 | F3 只提示（`MeetingDetect.swift` 不開錄）、F2 移垃圾桶；`Reminders.swift` 不建立清單（沒有 `saveCalendar`） |
| 132 | 一致 | 收尾鎖被持有回 5（`test_second_finalize_refused`）、逐步逾時回 5（`test_step_timeout_exits_5_and_keeps_segments`）；`finish` 的結束碼集合仍是 `0 2 3 5` |
| 133 | 一致 | `RecordsTests.swift` 不在 diff；`testOutputLatenciesOmittedWhenNil`、`testDiscardedNoAutoPrep` ok |
| 134 | 一致 | `MENU_TITLES` 三個字面與 `:214` 改法同條文；`test_r2_docs.py` 不在 diff 且 ok |
| 135 | 一致 | `MenuBar.swift:405` 起 `menuBarAccessibilityLabel(` 用於 status item 的 toolTip 與 VoiceOver；`test_menubar_sets_accessibility_label` 沒改 |
| 136 | 一致 | `record.sh:178-184` 的 `recorder_comm` 只在 `MH_RECORDER_COMM` 與 `MH_RECORD_OPEN` 都有值時用前者；`fake_recorder.sh` 只新增 `FAKE_LOCK` 段落、`_helpers.py` 只加一鍵 `MH_RECORDER_COMM=bash`；突變 M1 證明測試擋得住 |
| 137 | 一致 | 三支測試只改讀取的檔與名稱清單分組；`RecordingSession.swift` 不含 `pauseRoute(`、`openReason(`、`routeSample(`、`shouldSwitchForFormat(`（grep 0 筆）；這些呼叫都在 `Core/SegmentScheduler.swift:88-120` |
| 138 | 一致 | entitlements 檔與 V4 建置結果都是 3 項；`test_entitlements_audio_and_apple_events` 只加一鍵 |
| 139 | 一致 | `Onboarding.swift:504` 試錄目錄在 `temporaryDirectory`／`meeting-harness-trial-<runId>`；`removeItem(` 只有 `:645` 一處、參數是 `trialDir` |
| 140 | 一致 | `test_concurrency.py` 只加 `published()` 與判斷條件，`polls ≥ 3` 與其他斷言不變；三輪全綠 |
| 141 | 一致（待閘門 3 追認） | `MenuBar.swift:274-282` 失敗階段依 `menuItems(stage: .failed)` 一律顯示 `copyDiagnostics`；既有測試沒改 |

## 4. 缺陷

逐條驗收沒有 FAIL。下面一則不對應任何 §4 條文的 FAIL，但行為比 R2 差，列出來：

**D1（低，非 blocking）：沒有錄製時 `meeting record stop` 的 stderr 多一行 bash 錯誤**
- 重現：`MH_RECORD_HOME=$(mktemp -d) bash bin/meeting.sh record stop`
- 預期：同 R2，stderr 只有「沒有錄製在跑。」，rc=3
- 實際：rc=3 正確，但 stderr 先印一行 `bin/record.sh: line 611: <home>/record.pid: No such file or directory`，再印「沒有錄製在跑。」
- 環境：HEAD `091d775`，macOS、bash 3.2
- 原因：`bin/record.sh:611` 的 `pid="$(tr -cd '0-9' < "${PID_FILE}" 2>/dev/null)"`，輸入重導向在 `2>/dev/null` 之前處理，開檔失敗的訊息照樣進 stderr（R2 的 `running_pid` 先檢查 `[[ -f "${PID_FILE}" ]]`）
- 建議修法：改成 `pid="$( { tr -cd '0-9' < "${PID_FILE}"; } 2>/dev/null )"`，或先 `[[ -f "${PID_FILE}" ]]`。補一支測試斷言「沒有 `record.pid` 時 stderr 不含 `No such file`」

## 5. 反作弊檢查（`377dd92..091d775`）

| 項目 | 結果 | 依據 |
|---|---|---|
| 指定不得修改的 7 支 | 沒動 | `surface.py`、`test_surface_parsers.py`、`test_cli_dispatch.py`、`test_docs.py`、`test_record_sh.py`、`test_regression.py` 都不在 `git diff --name-status`；`e2e_check.py` 只有 `9988f3c`（r3-sync-measure）動過，176 行新增、1 行刪除（刪的是 usage 字串，改寫成含 `--sync-player` 的同一行），既有判準與常數沒有 `-` 行 |
| 既有測試的修改 | 都在第 118、120、121、123、127、129、130、134、136、137、138、140 條範圍內，只動條文列出的斷言 | 逐行對過 `test_r2_static.py`、`test_static_rules.py`、`test_t7_fixes.py`、`test_concurrency.py`、`ControlTests.swift`（§3 表）。`_helpers.py`、`fake_recorder.sh`、`fake_open.sh`（`FAKE_OPEN_LOCK`，預設關）、`_fixtures.py`、`_media.py`、`Tests/main.swift` 都只有新增行 |
| commit 寫明條號 | 有 | `13502e1` 內文逐條列第 118、120、121、123、129、130、134、136、137、138 條；`6ad5365` 第 127 條；`842d2e6` 第 140 條 |
| 紅燈後再改 R3 測試 | 沒有 | `test_r3_*.py`、`R3*Tests.swift`、`vectors/`、`fakes/`、`_media.py`、`_fixtures.py` 在 R3 範圍內只被 `13502e1`、`6ad5365` 兩個紅燈 commit 動過 |
| 測試被刪 | 沒有 | diff 中沒有 `-def test`／`-func test` |
| skip、expectedFailure、條件式跳過 | 只有 spec 允許的 3 處，本輪都有執行 | `test_downstream_missing_sections`（下游不存在才 skip）、兩支名稱檢查（沒設 `MH_CLIENT_NAMES_FILE` 才 skip）；V2 三輪 skipped 0 |
| 環境變數旁路 | 只在 `MH_RECORD_OPEN` 也有值時生效 | `record.sh:179`；`test_comm_override_needs_record_open` 有反向對照（兩者都設時 sleep 會收到 SIGTERM）；突變 M1 被擋下。`MH_RECORDER_COMM` 不在 README、SKILL.md（疑慮 59） |
| `RecordingSession.swift` 殘留 `pauseRoute(`／`openReason(`／`routeSample(` | 沒有 | grep 0 筆；`ingest` 改走 `scheduler.handle`（`:426`），非 sample 事件走 `dispatch`（`:473`），輸出裝置變更 `:756` `dispatch(.outputDeviceChange)` |
| 靜態測試的字面是否真的被使用 | 是，有 1 處例外 | 讀碼確認：`acquireRecordLock(` 早於 `StatusWriter(`（`Commands.swift:111`、`:149`）、`stopTargetDecision(` 擋在每個 `kill(…, SIGTERM)` 前（`MenuBar.swift:788`、`:832`、`:858`）、`feedbackRoute(`、`obscuredAction(`、`newAlertWarnings(`、`notificationPolicy(`、`menuBarCapsuleStyle(`、`FinalizeRunner`、`trashItem`、`discardRequestValid(`、HUD 的 `sharingType = .none` 等都在會被執行的路徑上；`HUDController`、`FailureDetailController`、`OnboardingWindowController`、`MeetingDetector`、`LevelMeterView` 都由 `MenuBar.swift` 建立，`main.swift:84` 分派 `reminders`。以腳本檢查 179 個「應出現」字面：去掉字串常值後就消失的只有 3 個，都本來就是字串（`record.discard.json`、`exclamationmark.triangle.fill`、`meeting-harness-trial-`）。**例外**：`RemindersStatic.test_eventkit_shape`（`test_r3_app_static.py:168`）要的 `fetchRemindersMatchingPredicate`、`saveReminder` 只出現在錯誤訊息字串（`Reminders.swift:116`、`:152`）；真正的呼叫是 Swift 改名後的 `store.fetchReminders(matching:)`（`:114`）與 `store.save(r, commit: false)`（`:150`），行為存在，但測試其實沒有驗到呼叫。見 §8 |
| 被測物被 mock | 沒有 | CLI 測試以替身 app（`MH_RECORD_OPEN`）與替身 ASR（`fakes/asr/mlx_whisper`）代替外部程式，被測的 `record.sh`、`meeting.sh`、`transcribe.sh`、`_render.py`、`_record_finalize.py` 都是真的 |
| 錯誤被吞、加 retry | 沒有實質問題 | 產品 diff 的 `except …: pass` 都在清理暫存檔或對已結束的程序送訊號後照常丟出或結束；重試只有 spec 規定的取鎖重試（§3.15）。`write_defaults` 的 `|| true` 是 §4.43.2 規定的「defaults 寫不進不擋開錄」，stderr 有報錯 |
| 證據 commit 是否為 HEAD | 是 | 三次查 HEAD 都是 `091d775`；`progress.md` 記的數字（Python 304、Swift 123）與本輪重跑相符，本檔只用自己重跑的結果 |
| 五條鐵則 | 守住 | (1) raw 不改：`run_diarize` 改在暫存目錄重轉、只在原本沒有 raw 時補（`bin/meeting.sh:243-263`）；`（聽不清）` 只進衍生檔，`test_unclear_marked_in_derived_only` 逐位元比對 raw；突變 M2b 被擋下。(2) 不編造負責人與期限：`_reminders.py` 缺負責人寫「（未定）」、缺期限 `null`；app 端 `reminderDueComponents` 只接 `YYYY-MM-DD`、其他原文放 notes；突變 M3 被擋下。(3) 不確定的姓名不掛：VTT 用 `_merge_speakers.py` 的同一套歸屬與門檻，6 組 fixture 一致性測試；突變 M5（門檻 0.7→0.6）被擋下。(4) 雜訊段標「（聽不清）」：§4.30.6、§4.31.10 的測試。(5) 聲紋只在 `vault/`：R3 diff 的 `bin/`、`tools/` 沒有任何 `vault`、embedding、聲紋相關新增行 |
| 對外介面相容 | 只有新增 | `record.sh` 子指令清單不變，結束碼只新增 spec R3-§2.2 列的情況（數字集合不變，`test_exit_code_matrix`、`test_existing_exit_codes_unchanged` 沒改且 ok）。`meeting.sh` 新增頂層 `search`、`sync`、`reminders`；代價是名為這三個字的根目錄要寫 `./search`（§7 疑慮 46，已在 spec 核准） |

### 5.1 突變抽查（暫存複本，跑完即刪）

| # | 突變 | 結果 |
|---|---|---|
| M1 | `record.sh` 的 `recorder_comm` 拿掉「`MH_RECORD_OPEN` 也要有值」 | `test_comm_override_needs_record_open` FAIL |
| M2b | `run_diarize` 重轉前清空 `transcript.raw.md` | `test_diarize_keeps_raw` FAIL |
| M3 | `_reminders.py` 缺期限時補 `2026-12-31` | `test_dry_run_items` FAIL |
| M4 | `step_timeout("normalize")` 的倍數 10 改 5 | `test_step_timeout_values` FAIL |
| M5 | `_render.py` 套名門檻 `confidence ≥ 0.7` 改 0.6 | `test_render_copy_matches_merge`（fixture `confidence_0_69`）FAIL |
| M6 | `Core/Lock.swift` 的 `stopTargetDecision` 拿掉 pid 不符的判斷 | `run.sh` 123 支失敗 1 |
| M7 | `SegmentScheduler.ingest` 把 `.drop` 路由當成 `.normal` | 全綠。另寫探針確認：暫停後目前段已轉 prev、下一個邊界不存在，越過 60 秒邊界或輸出裝置變更後的 sample 在原碼與突變後都回 `[drop]`；差別只有內部 `maxEnd`，對外動作序列相同，屬等價突變，不算測試缺口 |

## 6. 文件與實作落差、其他觀察（都不判 FAIL）

1. **menu bar 試鎖不重試、在主執行緒**：§3.15 寫「所有取鎖與試鎖一律在 1 秒內每 100 ms 重試」「menu bar 不得在主執行緒上試鎖」；`Trigger/MenuBar.swift:893` 與 `Trigger/MeetingDetect.swift:99` 都用 `acquireRecordLock(home:, retrySeconds: 0)`，`stopRecording` 等選單動作在主執行緒呼叫。`retrySeconds: 0` 不會睡，所以不會卡主執行緒；誤判方向是「被持有」，停止時後面還有 pid 三項確認，偵測時只是少提示一次，安全目的沒有破。但與 §3.15 字面不符，建議閘門 3 決定：(a) spec 補一句「menu bar 的試鎖以 `retrySeconds: 0` 做，不重試」；(b) 改成背景執行緒、1 秒重試，代價是停止與偵測多最多 1 秒延遲
2. **Reminders 字面只在錯誤訊息**（§5 例外）：`test_eventkit_shape` 的兩個字面是 Objective-C selector 名，Swift 原始碼裡不可能以呼叫的形式出現，實作把它們寫進錯誤訊息來讓測試通過。行為本身存在。若要讓測試驗到呼叫，要改 R3 紅燈測試（`fetchReminders(matching:`、`.save(`），屬既有測試修改，要使用者核准；不改的話，EventKit 的實際行為由 §4.47.5 實機確認
3. **spec 測試欄筆誤**：§4.40.4 的 `test_r3_app_static.py::test_edge_tab` 少了類別名，實際是 `HudStatic.test_edge_tab`
4. **`test_defaults_single_writer` 的偵測面有限**：只抓同一行有 `writeJSONAtomically(`／`.write(to:` 且含 `defaults` 的寫法；`Core/Settings.swift` 用 `rename()` 寫，測試抓不到。本輪讀碼確認其他 Swift 檔只 `RecordDefaults.load` 讀 defaults。之後若有人用別的 API 寫 defaults，這支測試擋不住
5. **測試衛生**：`test_r3_lock.py:63` 的 `hold_lock` 以 `stdout=PIPE` 起持鎖程序、沒關 pipe，跑 `test_r3_lock`、`test_merge_defaults` 時印 10 次 `ResourceWarning: unclosed file`，不影響結果
6. **驗證期間觀察到使用者自己的錄製收尾**：開工時已有兩個 MeetingRecorder 程序（`~/Applications` 的版本，一個 menu bar、一個 17:59 開錄的錄製實例）。驗證期間該錄製實例收到 SIGTERM、進入收尾（`~/.meeting-harness/record.status.json` 的 `phase` 變 `finalizing`、`record.log` 多了收尾行，沒有任何測試標記）。本輪所有手動 CLI 都指向暫存 `MH_RECORD_HOME`；會跑 `record stop` 的測試（`test_r3_lock.py:117`、`test_record_sh.py:181`、`:196`、`test_r2_cli.py:256`）都經 sandbox 的 `MH_RECORD_HOME`，測試裡的 `os.kill` 只對測試自己起的 pid。判斷不是本輪造成，但請使用者確認是自己停的

## 7. §4.47 實機驗收場劇本（使用者在場）

結果照 spec 寫進 run 目錄（只寫 run 代號、不寫會議名）。每一步都標了對應的 §4.47 條目與 §4.26–§4.46 的實機部分。下列指令的 `<場次>` 是當場產生的場次資料夾。

### 7.0 前置（不可逆節點，要使用者當下同意）

1. 確認目前沒有錄製在跑（`meeting record status`），上一場收尾已完成。
2. 備份：記下 `~/.meeting-harness/record.defaults.json` 的鍵名清單（只看鍵、不看值）：`python3 -c "import json,os;print(sorted(json.load(open(os.path.expanduser('~/.meeting-harness/record.defaults.json')))))"`。
3. **使用者同意後**覆蓋安裝：`bash tools/MeetingRecorder/build.sh`（預設裝到 `~/Applications`；cdhash 會變，TCC 授權可能要重給），結束舊的 menu bar 後重開。
4. `bash bin/meeting.sh record windows` → `bash bin/meeting.sh record preflight --window <id>`，13 項 hard 都過。

### 7.1 首次引導與試錄（§4.47.8、§4.47.13；§4.43.5、§4.43.6）

1. 新安裝的 app 沒有 `menubar.settings.json`，menu bar 啟動時應出現首次引導；已有該檔時刪掉 `onboardingCompletedAt` 鍵後重開。
2. 依序走完 5 步：歡迎 → 權限（四列狀態字與按鈕；狀態不只靠顏色）→ 存檔位置 → 選單列空間（被瀏海擋住時有「改成一律顯示錄製小窗」）→ 試錄。另開一次測「全部略過」與 Esc／⌘W 關閉。
3. 試錄：錄 5 秒自動停止，畫面顯示兩路是否有聲。**觀察**：「會議錄製結束（有錯誤）」通知有沒有閃一下（疑慮 62）；試錄後暫存目錄 `meeting-harness-trial-*` 已刪、會議根目錄沒有新場次。
4. 用步驟 7.0-2 的指令再看一次鍵名：原有鍵都在，只有 `harness`、`root` 可能變。
5. 設定視窗 7 個分頁：標題跟著分頁變、重開記得上次分頁；權限分頁 5 列（含「提醒事項」選用）；進階分頁 `syncCompensation` 唯讀。

### 7.2 F3 會議偵測（§4.47.6；§4.44.3）

1. 開一個 ★ 清單的會議 app 並讓它用麥克風：只出現一次「錄這個會議？」，內文只有 app 名稱、沒有視窗標題。
2. 按「這場不用」：同一個 episode 不再提示；結束通話再開一次，會再提示一次。
3. 按「開始錄製」：走 quick-start，開錄後偵測不再提示。停止並收尾。

### 7.3 錄製中綜合場（約 6 分鐘，內建喇叭；§4.47.3、§4.47.4、§4.47.12(a)；§4.26.2、§4.26.6、§4.37.6、§4.38.3、§4.38.4、§4.40.4、§4.40.7、§4.40.8、§4.41.4）

1. 先建 `~/.meeting-harness/keep-segments`（保留段落供 7.7 與 e2e 用）。開錄（會議 app 持續有聲音）。
2. 選單列膠囊：錄製中顯示紅點＋計時；拖動圖示位置，之後重開 menu bar 確認位置保留（§4.38.4）。
3. 錄製中再跑一次 `meeting record <根> --window <id>`：`record.sh` 層回 2、stderr 含「已有錄製在跑」。app 層（§4.26.2）另以 `open -n -a ~/Applications/MeetingRecorder.app --args preflight --window <id>` 直接起第二個實例：`record.log` 多一行含「已有錄製在跑」，`record.pid` 與 `record.status.json` 都沒被改（先記下兩者的 mtime 再比）。
4. **HUD 分享**（§4.47.3）：在會議 app 分享整個螢幕，請對方或第二台裝置確認 HUD 有沒有出現在分享畫面；有的話記錄並以選項式提問決定改預設或加說明。
5. **HUD 標記**（§4.47.12(a)）：HUD 顯示中按 ⌃⌥⌘B，記錄使用者是否察覺標記已加。
6. **暫停 30 秒**（§4.26.6）：期間每隔幾秒看 `record.status.json` 的 `updatedAt`，30 秒內至少前進 5 次；HUD 狀態字變「已暫停」、膠囊變暫停樣式。繼續。
7. 靜音 30 秒後取消：膠囊變靜音分段、HUD 麥克風那行「已靜音」。
8. **告警**（§4.47.4、§4.40.7）：拔掉外接麥克風（或換到沒聲音的輸入）觸發告警。記錄：通知是否以 Time Sensitive 呈現（疑慮 44）、通知標題與內文不含場次名與視窗標題、HUD 自動展開 8 秒並顯示告警膠囊、收合標籤外框改 `attention`、選單出現告警列。
9. **換輸出裝置**（§4.37.6）：錄製中把輸出從內建喇叭切到藍牙耳機再切回。停止後看 `錄音/tracks/manifest.json` 的段界與 `record.meta.json` 的 `deviceEvents[].t` 相差 < 0.5 秒，`outputLatencies` 有開錄與每次切換各一筆。
10. 選單四階段（§4.41）：錄製中、收尾中、失敗、待機各打開一次選單截圖；鍵盤導覽與 VoiceOver 讀音量條（§4.41.4）。
11. 停止。進入收尾後在選單按「取消收尾」（§4.28.6）：狀態 `failed`、code 5、訊息含「收尾已取消」與 `meeting record finish`。再跑 `bash bin/meeting.sh record finish <場次>`，回 0。

### 7.4 圖示被擋住與快捷鍵回饋（§4.47.12(b)；§4.40.3、§4.40.5）

1. 設定 → 回饋與通知 → 錄製小窗「不要」（`hudMode=never`）。
2. 開很多選單列圖示，讓 MeetingRecorder 的圖示被瀏海擋住；開錄。
3. 按 ⌃⌥⌘P、⌃⌥⌘M、⌃⌥⌘B：記錄是否收到快捷鍵回饋通知；`record.log` 沒有「圖示看不到」的行。
4. 改回「自動」，圖示仍被擋時 5 秒內 HUD 出現；把其他圖示移開後 HUD 收起。停止。

### 7.5 F2 捨棄（§4.47.7；§4.42.2、§4.42.3）

1. 開錄 30 秒，選單「捨棄這次錄製…」。對話框：預設鍵是「繼續錄製」，按 Return 不會捨棄；不顯示場次名。
2. 再開一次按「捨棄並移到垃圾桶」：`錄音/` 進垃圾桶、可「放回原處」，沒有跑收尾，`record.status.json` 有 `discarded: true`，沒有自動前處理。

### 7.6 E4 聲學回授（§4.47.1；§4.35.3）

1. `python3 tests/record/e2e_check.py --print-sync-file <暫存路徑>/sync.mp4`。
2. 內建喇叭：開錄、全螢幕播放 sync.mp4 約 3 分鐘、停止（keep-segments 已開，段落會保留）。`python3 tests/record/e2e_check.py --sync-acoustic <場次>`，記下各時段 mic − sys 中位數。
3. 藍牙耳機（喇叭模式）重做一次。把兩者的中位數寫成 `sync-calibration.json` 的候選值，由使用者決定是否採用。

### 7.7 E2 補償型播放端，決定 S-C 預設（§4.47.2；§4.37.7、§4.37.8）

1. 用 7.6 藍牙那一場（段落還在）：`bash bin/meeting.sh sync off` → `bash bin/meeting.sh record finish <場次>` → `python3 tests/record/e2e_check.py <場次> --sync-player`，記 PASS／FAIL 與各時段中位數。
2. `bash bin/meeting.sh sync reported` → 再 `record finish <場次>`（mode 改變會重做收尾）→ 再跑 `--sync-player`。`錄音/tracks/finalize.json` 的 `syncCompensation.segments[]` 列出各段延遲與 `source`。
3. 用 QuickTime 與 Chrome 各播一次成品，主觀確認嘴型。
4. **使用者決定** S-C 預設（維持 off 或改），改預設要另列 §6；同時決定疑慮 60（標記與 VAD 換算是否加 `L_out`）。驗完 `meeting sync off` 還原。

### 7.8 提醒事項（§4.47.5；§4.34.3）

1. 在提醒事項 app 建一個測試清單。對 7.3 的場次（先跑完前處理，有 `meeting.record.json`）：`bash bin/meeting.sh reminders <場次> --list <清單> --dry-run`，確認缺負責人寫「（未定）」、缺期限 `due: null`。
2. 不帶 `--dry-run` 跑一次：第一次出權限框（記錄權限框是否出現、文字含 iCloud），寫入後 rc=0。
3. 再跑一次：結果 `created=0`，項目沒有重複。另把同場 `actions.ics` 匯入，比對 UID。
4. 指定不存在的清單：rc=3、沒有代建清單。

### 7.9 真實多人會議（§4.47.9；疑慮 50、63）

1. keep-segments 開著錄一場真實多人會議。結果只寫數字：VAD clip 段數、`transcript.quality.json` 筆數、輕聲是否被切掉（必要時 `MH_VAD_THRESHOLD_DB` 調整後重轉）。
2. 若該場 `錄音/` 有多個音檔，確認 VAD 時間軸（疑慮 63）。

### 7.10 全套 e2e 迴歸（§4.47.10；§4.36.10、§4.25.1）

1. 照 §4.25.1 劇本錄約 4 分鐘（1:00 靜音 30 秒、2:00 暫停 30 秒、之後加兩個標記），停止。
2. `python3 tests/record/e2e_check.py <場次> --segment-writer --pause-mute --status <該場的 record.status.json>`：§4.25.1 列的判準全 PASS，成品長度與「錄製時間 − 30 秒」相差 < 1 秒。
3. 再跑第一輪的預設組，結果與 R2 一致。

### 7.11 設計審查（§4.47.11；§4.38.3、§4.39.4、§4.40.4、§4.40.8、§4.43.7）

截圖清單：8 種選單列膠囊（深色桌布、淺色桌布＋半透明選單列各一張、「增加對比」一張、灰階一張；記錄實際選單列的對比，疑慮 55）、HUD（收合、展開、暫停、靜音、告警自動展開、「減少透明度」「增加對比」「減少動態效果」）、選單四階段、錯誤詳情、捨棄確認框、引導 5 步、設定 7 分頁、app 圖示 16／32／128 px、通知外觀。可以在 7.1–7.5 進行中順手截。

### 7.12 收尾

刪 `~/.meeting-harness/keep-segments`、`meeting sync off`、`hudMode` 改回使用者要的值；結果寫 run 目錄後進閘門 3。

## 8. 待決（都不 blocking）

- 閘門 3 追認 §6 第 141 條；決定 §7 疑慮 61（同名 `MeetingDetect.swift` 的建置做法）
- §6 第 1 點：menu bar 試鎖 `retrySeconds: 0` 與 §3.15 字面不符。選項 (a) spec 補字面（建議，零程式改動）；(b) 改背景執行緒＋1 秒重試，停止與偵測多最多 1 秒延遲
- §6 第 2 點：`RemindersStatic` 的兩個字面只在錯誤訊息。選項 (a) 接受，靠 §4.47.5 實機確認（建議）；(b) 改測試字面成 Swift 名稱，屬既有測試修改、要核准
- D1：`record stop` 多一行 bash 錯誤，衍生工作（不編號），一行修法
- §6 第 6 點：請使用者確認驗證期間那場錄製是自己停的

## 9. 範圍

- **涵蓋**：§4.26–§4.46 每條的自動部分（Python 304 支跑 3 輪、Swift 123 支、暫存建置與 entitlements、verify、check_rules）；spec 引用的 166 個測試逐一對 ok；R3-§6 第 117–141 條逐條對實際狀態；既有測試修改逐行對條文；紅燈後修改、skip、旁路、mock、吞錯誤、湊字面（179 個靜態字面）檢查；7 個突變抽查；五條鐵則；`record.sh`／`meeting.sh` 子指令與結束碼相容性；暫存 home 下手動跑新 CLI；名稱掃描（只報有／沒有）
- **未涵蓋（需實機）**：§4.47 全部；§2 表中標「PASS＋需實機」的 18 條的實機部分與 4.39.4。原因：要使用者在場、要啟動 app 或觸發 TCC，派工約束不允許
- **未涵蓋（其他）**：沒有實錄；沒有對 `~/.meeting-harness/e2e/` 的場次重跑 `e2e_check.py`；HIG 與外觀審查歸設計審查；下游知識庫專案只經 `test_downstream_missing_sections` 唯讀載入

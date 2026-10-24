# 驗證報告：meeting-speed（sdlc-test 第 1 輪）

- 驗證對象：`feature/meeting-speed` @ `1aad87fd61787a50bd9dfd152107e4574a6b2481`（worktree `.worktrees/meeting-speed`）。開工時、兩輪全量跑完後、寫本檔前各查了一次 HEAD，三次都相同，worktree 也都是乾淨的
- 比對基準：`origin/main` ＝ `042c404`（等於 merge-base）。反作弊與名稱掃描的範圍是 `042c404..HEAD`（96 個檔，+10791／−1920）
- 驗收依據：`specs/meeting-speed/spec.md` §4.1–§4.16，共 99 列，其中 §4.2.7、§4.2.11 已在修正輪刪除，不計，實際 97 條；另有 §6.1、§6.2 的整合修訂與例外
- 環境：macOS（Darwin 25.6.0，arm64），在 agent sandbox 內執行。每個指令都帶 `TMPDIR=$(mktemp -d) LC_ALL=en_US.UTF-8`；Python 用 `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`。名稱清單只交給 `grep -f` 與 `MH_CLIENT_NAMES_FILE`，內容沒有讀出來
- **環境限制**：sandbox 內的 `h264_videotoolbox` 無法建立 compression session（`-12908`）。所以兩輪各有 11 支既有的條件式測試被 skip（§1 V2），§4.4.14 的 VideoToolbox 計時也無法自行重跑
- 安全邊界：沒有讀 `~/Documents` 底下任何真實會議資料、`.env`、`~/.meeting-harness`、`vault/`。沒有啟動錄製器或選單 app，沒有觸發 TCC，沒有用 git stash。建置只建到 `MH_RECORDER_DEST=$(mktemp -d)`，用完即刪；`~/Applications/MeetingRecorder.app` 的 mtime 建置前後都是 `1791639618`。突變抽查在 `git archive HEAD` 解出的暫存複本上做，跑完即刪
- 寫檔範圍：只寫了本檔

## 1. 機械檢查（在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0。`✓ lint 通過（26 個檔）`；doctor 沒有 `✗`。有一則 `⚠ 模型尚未授權（HTTP 000）`，是 sandbox 不能連網造成的 |
| V2 | `MH_CLIENT_NAMES_FILE=<client-names.txt> caffeinate -i $PY -m unittest discover -s tests/record -t .`，跑 2 輪（第 2 輪加 `-v`） | 第 1 輪 `Ran 514 tests in 912.310s`、`OK (skipped=11)`；第 2 輪 `Ran 514 tests in 889.630s`、`OK (skipped=11)`。兩輪 rc 都是 0，`FAIL:`／`ERROR:` 都是 0，`ImportError`、`ModuleNotFoundError`、`SyntaxError`、`NameError` 都沒有出現。11 支 skip 都是 origin/main 既有的條件式 skip，理由都是「這台機器的 ffmpeg 不能用 h264_videotoolbox 編碼」：`test_finalize` 5 支（`test_sparse_tail_gap_padded`、`test_sparse_tail_gap_padded_multi_segment`、`test_sparse_vfr_last_segment_covers_audio`、`test_tail_frame_not_overlong`、`test_tail_pad_no_extra_close_interval`），`test_r3x_parallel_finalize` 6 支。本 epic 沒有新增任何 skip |
| V3 | `bash tools/MeetingRecorder/Tests/run.sh` | rc=0，`共 168 支，失敗 0 支`（含 `MSCoreTests` 全部） |
| V4 | `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` | rc=0，`編譯（53 個檔）`，沒有 `error:`。entitlements 恰為 3 項：`automation.apple-events`、`device.audio-input`、`personal-information.calendars`。`Tests/run.sh` 只編 Core，這一步補驗了 Capture 與 Trigger 都能編譯 |
| V5 | spec §4 驗法欄抽出的全部測試引用（`檔::函式`、`swift:`、`::` 續寫）逐一對 V2 第 2 輪與 V3 的 ok 清單 | 97 條、162 個測試引用，找不到或沒有 ok 的都是 0（`/tmp/ms_refs.py`、`/tmp/ms_map.py` 的方法：先解析 spec 表格，再比對 `-v` 輸出） |
| V6 | 名稱掃描：`grep -qiF -f <client-names.txt>` 比對 `git diff origin/main...HEAD`、`git log --format=%B origin/main..HEAD`，並逐一掃 `git ls-files` 的每個檔 | diff：沒有；commit 訊息：沒有；追蹤檔：命中 0 個 |
| V7 | `python3 .claude/teams/tools/check_rules.py --git . origin/main..HEAD` | rc=1，1 項違規：`R4 commit 5773498：缺 Co-Authored-By trailer`。這個 commit 是 git 預設訊息的 merge commit（`Merge branch 'feature/meeting-speed' into feature/meeting-speed--finalize-fast`），見 §4 |
| V8 | 突變抽查 6 個（§3.3） | 5 個被擋下；M2（§4.11.7 的補償條件）存活 |

## 2. 逐條結果

結果只用三種：pass、fail、not_verifiable。測試欄的測試在 V2 兩輪與 V3 都是 ok。

**統計**：計入的有 97 條，**pass 87**、**fail 3**（§4.11.9、§4.14.3、§4.15.2）、**not_verifiable 7**（§4.4.11、§4.4.13、§4.4.14、§4.11.10、§4.12.4、§4.14.4、§4.15.1）。另外列兩項派工單指定的實機項目（§2.17），都是 not_verifiable。

### 2.1 介面與相容性（§4.1）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.1.1 | pass | 既有的 `test_surface_parsers` 6/6、`test_cli_dispatch` 13/13、`test_docs` 13/13、`test_record_sh` 10/10、`test_r2_cli` 10/10 都 ok，而且這 5 個檔在 `042c404..HEAD` 都沒有修改（`git diff --name-status`） |
| 4.1.2 | pass | `test_ms_prep::test_env_absent_unchanged`；既有 `test_r3_transcript_vad` 6/6、`test_t7_fixes` 7/7 都沒改。`test_deliver_fixes` 5/5 ok，其中 `test_quality_replaced_with_segments` 照 §6.2 第 25 條（使用者 2026-10-22 核准）修改過 |
| 4.1.3 | pass | `swift:testMSStatusFieldsOmittedWhenNil`、`testMSCanvasLockCodable`、`testMSOldStatusDecodes` |
| 4.1.4 | pass | V1 `✓ lint 通過（26 個檔）`；`git ls-files bin` 在 `bin/lib/` 以外有 26 個 |
| 4.1.5 | pass | `test_ms_app_static::CoreStatic::test_core_no_appkit` |

### 2.2 音訊先出（§4.2）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.2.1 | pass | `test_ms_audio_first::test_wav_published_before_video`；讀碼 `bin/_record_finalize.py:1144-1176`，順序是 `audio-ready.json` → `finalize.json` 第一階段 → `os.replace` → 印「音訊就緒：」，影片步驟在 `:1212` 之後 |
| 4.2.2 | pass | `test_ms_audio_first::test_ready_json_fields` |
| 4.2.3 | pass | 既有 `test_concurrency::test_finalizing_session_not_listed`（檔案沒改）；`test_ms_audio_first::test_finalize_json_before_wav` |
| 4.2.4 | pass | `test_ms_audio_first::test_compensated_wav` |
| 4.2.5 | pass | `test_ms_audio_first::test_video_failure_keeps_wav`；`test_r3_finalize_guard::test_step_timeout_exits_5_and_keeps_segments`（這個檔只有 `test_atomic_write_uses_mkstemp` 照 §6.2 第 27 條改過）；`test_finalize` 的 §4.6.20 測試 ok |
| 4.2.6 | pass | `test_ms_prep::test_prep_while_video_finalizing` |
| 4.2.7 | — | 修正輪刪除，不計 |
| 4.2.8 | pass | `swift:testMSIsAudioReadyLine`；`CaptureStatic::test_audio_ready_sets_status` |
| 4.2.9 | pass | `swift:testMSAutoPrepPickEarly`、`NoDoubleEnqueue`、`DoneFallback`；既有 `TriggerTests` 沒改，V3 全部 ok |
| 4.2.10 | pass | `TriggerStatic::test_autoprep_run_id_env` |
| 4.2.11 | — | 修正輪刪除，不計 |

### 2.3 冪等（§4.3）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.3.1 | pass | 既有 `test_finalize::test_idempotent_second_run`（檔案沒改） |
| 4.3.2 | pass | `test_ms_audio_first::test_idempotent_mid_state` |
| 4.3.3 | pass | `test_ms_audio_first::test_ready_json_stale_rewritten` |
| 4.3.4 | pass | `test_ms_video_copy::test_verify_failed_not_done`、`::test_old_finalize_json_is_done` |

### 2.4 影片（§4.4）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.4.1 | pass | `CaptureStatic::test_canvas_lock_written`、`::test_no_resize_update_configuration`、`::test_next_segment_size_logged`；`test_static_rules` 31/31（檔案沒改） |
| 4.4.2 | pass | `CaptureStatic::test_preserves_aspect_ratio`；依 §4.4.13 的決定，維持 1/60、不設尺寸上限 |
| 4.4.3 | pass | `test_ms_video_copy` 的 4 支：`test_copy_when_canvas_lock`、`test_reencode_without_canvas_lock`、`test_reencode_when_size_mismatch`、`test_reencode_when_extradata_differs` |
| 4.4.4 | pass | `::test_copy_packets_identical`、`::test_finalize_json_video_path` |
| 4.4.5 | pass | `::test_copy_duration_within_100ms`、`::test_copy_dts_monotonic`（照 §6.2 第 26 條修正參數，使用者 2026-10-23 核准）、`::test_copy_audio_lengths_25ms` |
| 4.4.6 | pass | `::test_no_faststart`；`test_static_rules` 沒改、全綠 |
| 4.4.7 | pass | `::test_probe_calls_per_segment` |
| 4.4.8 | pass | `::test_verify_step_label`；`test_r3_finalize_guard` 6/6 |
| 4.4.9 | pass | `test_ms_audio_first::test_wav_published_before_video`；`test_r2_finalize` 6/6。**注意**：`test_finalize` 23 支裡有 5 支補尾相關測試因 VideoToolbox 不可用而 skip（V2），這 5 支在本環境沒有驗到 |
| 4.4.10 | pass | `::test_x264_note_only_after_success` |
| 4.4.11 | not_verifiable | 實機：用新錄製器錄一場 ≥ 30 分鐘，看 `e2e_check.py` 的 5 項與 `videoPath == "copy"`，並重驗缺陷 B、F、N。agent 不得啟動錄製器，列為待實機驗收 |
| 4.4.12 | pass | `::test_tail_pad_low_r_frame_rate`；突變 M5（拿掉 `TAIL_PAD_FPS_FLOOR`）會被它擋下。注意事項同 4.4.9：既有 `test_finalize` 的 5 支補尾測試在本環境被 skip |
| 4.4.13 | not_verifiable | 決定的部分已記錄：spec 第 278 行記載使用者 2026-10-22 決定先維持 60 fps 與原生像素；`video-spike.md` 第 5 節存在。第 5.3 節寫明 WindowServer 三種設定「還沒有數字」，這要使用者在場實測。待實機驗收 |
| 4.4.14 | not_verifiable | `evidence/reencode-regress.md` 表 1 宣稱：修正後 HEAD 與 042c404 相比在 0.87～1.03 倍之間，合成段落各跑 3 次取中位數。驗法形式符合條文，`test_ms_video_copy` 全綠。但 sandbox 內 `h264_videotoolbox` 不可用，我無法重跑計時，依「不採信別人貼的輸出」判 not_verifiable。另外，主 session 2026-10-23 的重放仍是 `stopToVideo=2282.3`（條文寫的修正前是 2302 秒），真實段落上每段約 48 秒的成本沒有降。證據檔 §6 自己也把「在同一批真實段落上做同一段對照」列為衍生工作 |

### 2.5 驗證移到發佈之後（§4.5）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.5.1 | pass | `test_ms_video_copy::test_publish_before_verify`；讀碼 `bin/_record_finalize.py:1212-1229` |
| 4.5.2 | pass | `::test_verify_ok_cleans_segments` |
| 4.5.3 | pass | `::test_verify_failed_renamed`；`bin/_record_finalize.py:1240-1241` |
| 4.5.4 | pass | `::test_verify_failed_rerun_forces_reencode` |
| 4.5.5 | pass | `test_r3_lock` 14/14（只有 §6.2 第 21 條的容差改過，已核准）、`test_record_sh` 10/10（沒改） |
| 4.5.6 | pass | `test_ms_docs::test_record_skill_speed_notes` |

### 2.6 鐵則（§4.6）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.6.1 | pass | `test_ms_iron_rules::test_no_embeddings_in_session`、`::test_embeddings_temp_removed` |
| 4.6.2 | pass | `::test_confidence_missing_not_applied`；`test_r3_vtt_raw::test_render_copy_matches_merge`。突變 M1（沒有 confidence 時預設套名）被擋下，兩個 subTest 失敗 |
| 4.6.3 | pass | `::test_string_mapping_kept`、`::test_manual_dict_kept`、`::test_voiceprint_dict_replaced_by_higher` |
| 4.6.4 | pass | `::test_add_recompute_temp_removed`、`::test_add_reads_legacy_embeddings`；`test_review_fixes` 7/7（沒改） |
| 4.6.5 | pass | `::test_remove_rejects_path` |
| 4.6.6 | pass | `test_ms_asr_robust::test_raw_not_converted`、`::test_transcript_md_not_overwritten`、`::test_segments_still_converted`；`test_ms_docs::test_transcribe_skill_raw_policy` |
| 4.6.7 | pass | `test_ms_docs::test_speakers_skill_annotate`、`::test_summary_skill_no_session_embeddings` |
| 4.6.8 | pass | `::test_gitignore_entries` |
| 4.6.9 | pass | `::test_meta_embeddings_before_dump` |
| 4.6.10 | pass | `::test_config_keys` |

### 2.7 ASR 失敗看得到（§4.7）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.7.1 | pass | `test_ms_asr_robust::test_exception_exit0_triggers_fallback`；`bin/transcribe.sh:126-142`（`run_engine` 判斷非空 `.json`） |
| 4.7.2 | pass | `::test_asr_log_tail_30` |
| 4.7.3 | pass | `test_r3_transcript_vad`、`test_t7_fixes` 沒改、全綠。`test_r3_vtt_raw`（只改了 §6.2 第 20 條那支）6/6、`test_deliver_fixes`（只改了第 25 條那支）5/5 |
| 4.7.4 | pass | `::test_segments_json_input_skips_asr` |

### 2.8 前處理（§4.8）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.8.1 | pass | `test_ms_prep::test_diarize_parallel_with_transcribe`（兩輪都 ok） |
| 4.8.2 | pass | `::test_state_begin_run_id`、`::test_stages_carry_run_id` |
| 4.8.3 | pass | `::test_diarize_failure_recorded` |
| 4.8.4 | pass | `::test_missing_segments_explicit_error`；修改後的 `test_r3_vtt_raw::test_diarize_keeps_raw`（§6.2 第 20 條） |
| 4.8.5 | pass | `::test_prep_exit_zero_on_stage_failure` |
| 4.8.6 | pass | `swift:testMSPrepOutcomeOk`、`Failed`、`Unknown` |
| 4.8.7 | pass | `swift:testMSPrepNotification`；`TriggerStatic::test_prep_outcome_read` |
| 4.8.8 | pass | `test_ms_iron_rules::test_diarize_skips_16k_conversion` |
| 4.8.9 | pass | `test_ms_prep_visible::test_combine_audio_bracket_path`、`::test_ocr_bracket_path`、`::test_prep_bracket_session_end_to_end` |
| 4.8.10 | pass | `::test_prep_banner_reports_failure`、`::test_prep_banner_ok_when_all_done`。突變 M3（失敗時仍印 ✅）被擋下。**用詞落差**：條文寫「<場次代號>：…」，但實作（`bin/meeting.sh:385-391`）與測試（`test_ms_prep_visible.py:103`）都用場次資料夾名（`basename`）。本 repo 的「場次代號」在 intent §7 與 §4.12 是指不含場次名的 `sessionCodeLabel`。這是終端機輸出，不是通知，prep 其他行本來就印場次名，所以判 pass；條文是否改字面，見 §5 第 3 題 |

### 2.9 狀態檔加鎖（§4.9）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.9.1 | pass | `test_ms_prep::test_state_set_atomic_flock`、`::test_finalize_set_state_uses_lock` |
| 4.9.2 | pass | `::test_state_lock_timeout_warns`；呼叫端 `bin/meeting.sh` 的 `state-set … \|\| true` 正是條文要求的「呼叫端照常繼續」 |
| 4.9.3 | pass | `::test_status_reads_new_state` |

### 2.10 preflight 與停止路徑（§4.10）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.10.1 | pass | `swift:testMSAudioProbeDeviceFailed`、`Passthrough`、`testMSAudioDeviceFailedMessage`；`CaptureStatic::test_preflight_device_failed`；既有 `PreflightTests` 沒改 |
| 4.10.2 | pass | `CaptureStatic::test_start_capture_error_logged` |
| 4.10.3 | pass | `swift:testMSStopPathLogLine`；`TriggerStatic::test_stop_paths_logged`、`CaptureStatic::test_preflight_returns_logged`；`test_r3_app_static` 32/32（沒改） |

### 2.11 增量轉錄（§4.11）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.11.1 | pass | `swift:testMSAsrWorkerShouldStart`；`CaptureStatic::test_worker_started_after_first_segment`。`record.defaults.json` 的 python3 實際能不能 import `mlx_whisper`，另列 §2.17 實機-A |
| 4.11.2 | pass | `test_ms_incremental_asr::test_reads_finished_segments_only`、`::test_single_worker_lock`。**條文與實作有落差**：asr-tail 修正（`aa08c80`，`bin/lib/_asr_worker.py:215-232`）在本場停止後，把 manifest 最後一列 `finishedAt` 為 null 的段落也算進來；但 §4.11.2 的字面仍是「只處理 `finishedAt` 不是 null 的段落」，spec 沒有補記這個例外。錄製中照舊不處理（`test_ms_asr_tail::test_unfinished_segment_skipped_while_recording` ok），所以判 pass，spec 補記見 §5 第 4 題 |
| 4.11.3 | pass | `::test_cut_at_silence`、`::test_cut_hard_when_no_silence`、`::test_windows_non_overlapping` |
| 4.11.4 | pass | `::test_pause_on_drops_until_stop`、`::test_pause_when_other_finalizing` |
| 4.11.5 | pass | `::test_completes_after_stop`；`test_ms_asr_tail::test_completes_with_unfinished_last_segment`。突變 M6（還原 asr-tail 修正）被擋下 |
| 4.11.6 | pass | `::test_model_loaded_once` |
| 4.11.7 | pass | `::test_stitch_ok_schema`、`::test_stitch_param_mismatch_exit3`、`::test_stitch_incomplete_exit3`、`::test_stitch_waits_live_worker`。讀碼 `bin/lib/_asr_worker.py:605-606` 有補償 ≠ off 時回 3 的判斷。**測試缺口**：突變 M2 把這個判斷改成 `if False:`，`test_ms_incremental_asr` 13 支全部仍綠，代表「補償模式為 off」這個子條件沒有測試守住（衍生工作） |
| 4.11.8 | pass | `test_ms_prep::test_prep_uses_stitched`、`::test_prep_falls_back_full` |
| 4.11.9 | **fail** | 計算邏輯 `test_ms_replay::test_compare_metrics` 是 ok。但品質門檻沒有達到，見下方缺陷 D1 |
| 4.11.10 | not_verifiable | 實機：≥ 30 分鐘實錄的 `droppedFrames`，以及停止當下欠的窗數。待實機驗收 |

**缺陷 D1（§4.11.9）**
- 重現步驟：主 session 在 HEAD `1aad87f` 執行 `tools/bench/replay.py <舊段落> --speed 8 --compare-full`，重放一場 2 小時 18 分、141 段的舊段落（數字由派工單轉述，agent 依規定不得自行重放真實段落）
- 預期：`cer ≤ 0.05`，而且 `timeAlignedRatio ≥ 0.95`
- 實際：`cer = 0.0754`（超出門檻 2.54 個百分點），`timeAlignedRatio = 0.9564`（達標）
- 環境：主 session 的本機；量法與 plan §4 指定的不同（plan 指定 2026-10-20 那場 121 段、`--speed 1`）。CER 比的是逐窗轉錄與整檔轉錄的文字，只看窗的切法與模型，與重放速度無關（推論，未實測），所以判 fail 而不是 not_verifiable
- 處理：依派工單，修正輪不改程式，交閘門 3（§5 第 1 題）

### 2.12 通知（§4.12）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.12.1 | pass | `swift:testMSSessionCodeLabel`；`R3xBackgroundTests` 沒改，V3 ok |
| 4.12.2 | pass | `swift:testMSPrepNotification`；`TriggerStatic::test_prep_notifications_no_name` |
| 4.12.3 | pass | `swift:testMSCompletionNotificationBody`；`CaptureStatic::test_completion_body_no_path`、`TriggerStatic::test_menubar_completion_body_no_session`；`test_r3_skip_finalize` 7/7（沒改） |
| 4.12.4 | not_verifiable | 實機：看通知中心兩則通知的文字。待實機驗收 |

### 2.13 結構重構（§4.13）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.13.1 | pass | `test_ms_refactor` 6 支都 ok。`wc -l` 自查：`MenuBar.swift` 994、`RecordingSession.swift` 913、`bin/_record_finalize.py` 1276，`transcribe.sh` 沒有 `<<'PY'` heredoc |
| 4.13.2 | pass | `::test_record_helpers_single_definition`、`::test_paused_total_finalize_locked`、`::test_paused_total_record_lib_matches_finalize`；`test_r3_record_lib` 6/6、`test_review_fixes` 7/7（沒改） |
| 4.13.3 | pass | 6 個 `refactor(meeting-speed)` commit（`7468dd4`、`24caf43`、`7393583`、`1302180`、`23ca291`、`113b445`）逐一跑 `git diff --diff-filter=M --name-only <c>~ <c> -- tests/ tools/MeetingRecorder/Tests/`，都是空的；HEAD 全量綠 |
| 4.13.4 | pass | `test_ms_docs` 的 5 支：`test_readme_flow`、`test_stale_comment_*` 3 支、`test_meeting_pipeline_js_deprecated` |

### 2.14 量測（§4.14）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.14.1 | pass | `test_ms_replay::test_speed_schedule`、`::test_early_flow`、`::test_legacy_flow` |
| 4.14.2 | pass | `::test_report_keys`、`::test_report_no_paths` |
| 4.14.3 | **fail** | 見缺陷 D2 |
| 4.14.4 | not_verifiable | 見下方說明 N1。**唯一的現有數據超標**，依 spec 第 481 行交閘門 3 |

**缺陷 D2（§4.14.3）**
- 重現步驟：`sed -n '/## 量測：逐字稿線/,/## 量測：影片線/p' specs/meeting-speed/progress.md`
- 預期：每層合併後用 `--speed 10` 重放 2026-10-20 的 121 段，數字寫進 progress.md（「基準」「第 1 層後」「第 2 層後」「第 3 層後」四列）
- 實際：四列都是空的；progress.md 的閘門與子任務勾選也停在閘門 2 前的草稿狀態（例如「閘門 2 … 待整份核准」沒有勾，但 `run.json` 的 `design.approved` 是 2026-10-21）。run 目錄裡也找不到任何含 `stopToSpeakersMd` 的檔（`grep -rl stopToSpeakersMd _tpm/runs/20261021-sdlc-meeting-speed` 是空的）
- 環境：HEAD `1aad87f`
- 處理：progress.md 由主 session 維護（plan §2 共通：子任務不得改），這不是程式缺陷，修正輪的 dev-implementer 不該動它

**說明 N1（§4.14.4，G1 最終驗收）**
- 條文：(i) 以 `--speed 1` 重放 2026-10-20 的 121 段，`stopToSpeakersMd ≤ 300` 而且 `stopToWav ≤ 300`；(ii) 影片線用新錄製器實錄的 `stopToVideo` 外推，外推值 ≤ 300。兩者都成立才算 G1 達成
- 現有唯一的數據：主 session 2026-10-23 在 HEAD `1aad87f` 用 `--speed 8 --compare-full` 重放另一場 2 小時 18 分、141 段的舊段落：`stopToSpeakersMd=332.4`（**超過 300 共 32.4 秒**）、`stopToWav=21.0`（達標）、`stopToAudioReady=20.9`、`workerBacklogAtStop=1`、`stopToVideo=2282.3`（`videoPath=reencode`，舊段落走重編，不代表影片線）
- 量法差異：速度 8 對 1，段落 141 段（2 小時 18 分）對 121 段（2 小時），場次也不同；(ii) 影片線完全沒有量（要新錄製器的實錄）
- 判定：條文指定的量測沒有做，agent 也不得自行重放，所以判 not_verifiable。但不是「待量」而已：在僅有的數據下，(i) 的 `stopToSpeakersMd` 超標。依 spec §7 疑慮 1（第 481 行）「`stopToSpeakersMd > 300` 時主 session 停下回報使用者」，交閘門 3 決定（§5 第 1 題）

### 2.15 迴歸與 verify（§4.15）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.15.1 | not_verifiable | 這條要的是「每個子任務完成時」的四件套，屬於歷史時點，無法在 HEAD 重現。能驗的部分：HEAD 上 (a) V1 rc=0；(b) V3 rc=0；(c) V2 兩輪都沒有 `FAIL:`／`ERROR:`，也沒有 4 種錯誤字樣；(d) V6 整段 diff 與 commit 訊息都是「沒有」，等於涵蓋所有子任務的 diff |
| 4.15.2 | **fail** | 第 3 層（最後一層）合併後就是 HEAD，所以 plan §3 第 3 層那一列的指令可以在 HEAD 重跑。其中兩條沒有通過，見缺陷 D3。其餘指令都綠：全量 Python（V2）、Swift `run.sh`（V3）、`test_ms_docs -k test_no_client_names`（ok，沒有 skip）、`build.sh`（V4）、verify（V1）。第 1、2 層合併當下屬於歷史時點，無法重現；progress.md 的〈每層整合〉表是空的 |
| 4.15.3 | pass | `test_ms_docs::test_no_client_names_in_ms_files` ok，沒有被 skip（`MH_CLIENT_NAMES_FILE` 有設）；V6 是「沒有」 |

**缺陷 D3（§4.15.2，plan §3 第 3 層）**
- 重現步驟：(1) `git diff --diff-filter=M --name-only 042c404..HEAD -- tests/ tools/MeetingRecorder/Tests/`；(2) `python3 .claude/teams/tools/check_rules.py --git . 042c404..HEAD`
- 預期：(1) 恰為 `test_regression.py`、`test_r3_vtt_raw.py`、`test_r3_lock.py`、`main.swift` 這 4 個檔（`plan.md:92`）；(2) rc=0
- 實際：(1) 有 6 個檔，多出 `test_deliver_fixes.py` 與 `test_r3_finalize_guard.py`。這兩個檔的修改分別經 §6.2 第 25 條（2026-10-22）、第 27 條（2026-10-23）由使用者核准，但 plan §3 沒有跟著更新，所以是**文件落差，不是違規改測試**；(2) rc=1，`R4 commit 5773498：缺 Co-Authored-By trailer`
- 環境：HEAD `1aad87f`，本機 sandbox
- 處理：(1) 由主 session 把 plan §3 第 3 層的清單補成 6 個檔；(2) 見 §5 第 2 題（要改就得改寫歷史，必須由使用者決定）。這兩項都不是 dev-implementer 改程式能修的

### 2.16 異常中止後的接手（§4.16）

| 節 | 結果 | 證據 |
|---|---|---|
| 4.16.1 | pass | `swift:testMSAbnormalStop*` 6 支 |
| 4.16.2 | pass | `swift:testMSAbnormalStopNotification`；`TriggerStatic::test_abnormal_stop_checked_on_launch`、`::test_abnormal_stop_notification_no_name`。實際按「收尾」按鈕的效果另列 §2.17 實機-B |
| 4.16.3 | pass | `test_ms_record_finish` 7 支；突變 M4（不看 `videoPublishedAt`）被 `test_no_arg_already_finalized_exit2` 擋下 |
| 4.16.4 | pass | `test_ms_docs::test_record_skill_finish_no_arg`；`test_docs`、`test_surface_parsers` 沒改、全綠 |

### 2.17 派工單指定的實機項目

| 項 | 結果 | 說明 |
|---|---|---|
| 實機-A | not_verifiable | `record.defaults.json` 指定的 python3 能不能 import `mlx_whisper`（§4.11.1 的 worker 實際能否啟動）。agent 不讀 `~/.meeting-harness`，待實機驗收 |
| 實機-B | not_verifiable | 異常中止通知的「收尾」按鈕實際會執行 `meeting.sh record finish <場次>`（§4.16.2）。agent 不啟動選單 app，待實機驗收 |
| 實機-C | not_verifiable | WindowServer 三種擷取設定的實測（§4.4.13，同 2.4 節） |
| 實機-D | not_verifiable | ≥ 30 分鐘實錄（§4.4.11、§4.11.10、§4.12.4，同上） |

## 3. 反作弊（`git diff origin/main...HEAD`）

### 3.1 既有測試的修改

| 檔 | 改動 | 是否核准 |
|---|---|---|
| `tests/record/test_regression.py` | 整支刪掉 `test_diarize_and_merge_untouched` | §6.2 第 18 條，D1 已核准；替代守門 `test_ms_iron_rules::test_diarize_merge_interface_kept` ok |
| `tests/record/test_r3_vtt_raw.py::test_diarize_keeps_raw` | 改成：不呼叫轉錄、回 1、輸出含「缺 transcript.segments.json」；raw 不變的斷言保留 | §6.2 第 20 條，D1 已核准，字面相符 |
| `tests/record/test_r3_lock.py` | 上限從 932／11432 改成 936／11436，下限不變 | §6.2 第 21 條，D1 已核准，數字相符 |
| `tests/record/test_deliver_fixes.py::test_quality_replaced_with_segments` | 改成：不重轉、回 1、舊品質檔不變、不產生 speakers.md；raw 不變的斷言保留 | §6.2 第 25 條，使用者 2026-10-22 核准，字面相符 |
| `tests/record/test_r3_finalize_guard.py::test_atomic_write_uses_mkstemp` | 改到 `_record_lib.write_json_atomic`，並加上「`_record_finalize` 必須 import 它」的斷言；`.tmp` 字面的禁止照舊 | §6.2 第 27 條，使用者 2026-10-23 核准，字面相符 |
| `tools/MeetingRecorder/Tests/main.swift` | 套件清單多 1 行 `("MSCoreTests", mrtMSCoreTests)` | 只是註冊新套件，沒有改任何斷言。plan §3 第 3 層把它列為預期修改的檔（`plan.md:92`），不是放寬 |

其他既有測試檔在 `042c404..HEAD` 都沒有修改。

### 3.2 其他反作弊檢查

- skip、fixme、only、`expectedFailure`、retry：diff 裡新增的測試行（`^\+`）比對 `skipTest|unittest\.skip|skipIf|skipUnless|expectedFailure|fixme|xfail|\.only\(|retry`，命中 0 個。`git grep` 的 skip 數在 origin/main 與 HEAD 都是 6 處，都是既有的條件式 skip
- mock 被測物：diff 新增的測試沒有用 `mock.`、`patch(`、`MagicMock`。替身都是外部工具（`fakes/ms_bin/ffmpeg`、`fakes/pymod/mlx_whisper`、`ms_fake_meeting.sh`、`ms_embed_speaker.py` 等）。`test_tail_pad_low_r_frame_rate` 把 `link_fps` 換成回 58，是 spec §4.4.12 驗法欄明文指定的做法
- 錯誤被吞掉：產品碼 diff 裡的 `|| true`、`2>/dev/null`、`try?` 逐一看過。`state-set … || true` 是 §4.9.2 要求的「呼叫端照常繼續」；`run_oai … || true`、`_voiceprint.py match … 2>/dev/null` 在 `042c404` 就有，只是搬了位置；Swift 的 `try?` 屬於既有的讀檔與清理模式。沒有發現新的、會遮掉失敗判準的吞錯
- 證據的 commit：本檔所有證據都在 HEAD `1aad87f` 上自己跑出來。例外是派工單轉述的主 session 量測（也是 HEAD `1aad87f`），以及 `reencode-regress.md` 的數字（基準是 `8fe98fb`，本環境無法重跑），兩者都已在對應條目註明
- 上游既有測試：本 repo 沒有上游（`upstream_repos` 空）

### 3.3 突變抽查（`git archive HEAD` 解出的暫存複本，跑完已刪）

| # | 突變 | 跑的測試 | 結果 |
|---|---|---|---|
| M1 | `_merge_speakers.py`：沒有 `confidence` 的 dict 預設套名 | `test_ms_iron_rules::test_confidence_missing_not_applied` | 擋下（2 個 subTest 失敗） |
| M2 | `_asr_worker.py:605`：補償 ≠ off 的判斷改成 `if False:` | `test_ms_incremental_asr`（13 支） | **存活**（13 支全綠），§4.11.7 的補償子條件沒有測試 |
| M3 | `meeting.sh`：有失敗時仍印 ✅ | `test_ms_prep_visible` | 擋下 |
| M4 | `record.sh`：異常中止判定不看 `videoPublishedAt` | `test_ms_record_finish` | 擋下（`test_no_arg_already_finalized_exit2`） |
| M5 | `_record_finalize.py`：`max(fps, TAIL_PAD_FPS_FLOOR)` 改成 `fps` | `test_ms_video_copy::test_tail_pad_low_r_frame_rate` | 擋下 |
| M6 | `_asr_worker.py`：還原 asr-tail 修正 | `test_ms_asr_tail` | 擋下（`test_completes_with_unfinished_last_segment`） |

## 4. 其他發現（不影響逐條判定）

1. **commit 規則**：`5773498` 是 git 預設訊息的 merge commit，缺 `Co-Authored-By` 署名行，也不是 Conventional Commits 格式（V7），因此 §4.15.2 判 fail（D3）。要修就得改寫歷史，依通用規則 21 要先留備份分支，由使用者決定（§5 第 2 題）
2. **spec 與實作的落差**：一是 §4.11.2 沒有補記 asr-tail 的停止後例外；二是 §4.8.10 的「場次代號」用詞與實作不一致（見 2.8、2.11 節）
3. **測試缺口**：§4.11.7 的補償子條件（M2）
4. **環境**：sandbox 裡 VideoToolbox 不可用，11 支既有條件式測試被 skip，§4.4.14 無法重跑計時。要補，得在可用 VideoToolbox 的環境（主 session）用 `-v` 重跑一次 `test_finalize` 與 `test_r3x_parallel_finalize`，確認 skip 數是 0
5. **progress.md** 整份停在閘門 2 前的草稿（見 D2）

## 5. 交閘門 3 的問題

1. **G1 時間與增量品質沒有達標（§4.14.4、§4.11.9；blocking）**：在現有數據下，`stopToSpeakersMd=332.4 > 300`、`cer=0.0754 > 0.05`。選項（取自 spec 疑慮 1）：
   - (a) 加大分離的 batch，另開子任務
   - (b) 停止後暫停 worker、讓出 GPU
   - (c) 接受實測值或調整門檻（要修 spec 並記入 §6.1）
   - 另外，任何選項之前都可以先照 spec 量法補跑 `--speed 1`、121 段，以及影片線實錄，再決定
   - 建議：先補跑條文指定的量法。CER 超標與速度無關，要另外決定是接受，還是調整切窗或參數
2. **merge commit 缺署名（非 blocking）**：
   - (a) 不改歷史，在 deliver 的 PR 說明註記
   - (b) 留備份分支後改寫這個 merge commit 的訊息
   - 建議 (a)：改寫歷史的風險大於收益
3. **§4.8.10 用詞（非 blocking）**：
   - (a) 把條文的「場次代號」改成「場次名」，與實作和測試一致
   - (b) 改實作，用不含場次名的代號
   - 建議 (a)：這是終端機輸出，不是通知
4. **§4.11.2 補記 asr-tail 例外（非 blocking）**：建議由主 session 在 spec 補一句：「本場停止後，manifest 最後一列 `finishedAt` 為 null 但檔案在的段落也處理」

## 6. 衍生工作（不編號）

- 為 §4.11.7 的「補償模式不是 off 時 stitch 回 3」補一支測試（M2 存活）
- 在可用 VideoToolbox 的環境補跑 11 支條件式測試，以及 §4.4.14 在真實段落上的「同一段」對照（`reencode-regress.md` §6）
- progress.md 補上每層量測、閘門與子任務的勾選
- plan §3 第 3 層的「預期修改的既有測試」清單補上 `test_deliver_fixes.py`、`test_r3_finalize_guard.py`（§6.2 第 25、27 條）

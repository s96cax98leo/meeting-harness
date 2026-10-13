# 驗證報告：meeting-record（test 段重驗第 3 輪：t6 三輪中途修正之後）

- 驗證對象：`feature/meeting-record` @ `af91ec09ebfa12b89b6563c3cbac424355845220`（HEAD；比對基準 `main`，merge-base `9a76c83`，`git rev-list --count main..HEAD`＝71）
- 派工單寫的 HEAD 是 `cb417b4`，開工時已前進到 `af91ec0`（fix：§4.3.3 (ii) 補尾不得在同一個段落邊界製造 2 個過近間隔）。本輪一律以 `af91ec0` 為準。`cb417b4..af91ec0` 只動了 `bin/_record_finalize.py`（+24／−6）、`tests/record/test_finalize.py`（新增 1 支，+41／−0）、`progress.md` 一行
- 開工時 worktree 已有一份未提交的 `verifier.md` 草稿（也是在 `af91ec0` 驗的，來源不明）。本檔只把它當成待查清單，所有數字都是自己在 HEAD 重跑後覆寫的
- 驗收依據：`specs/meeting-record/spec.md` §4（4.1–4.15）；例外依據 §6
- 驗證者：dev-verifier。只寫本檔，不改程式、測試或其他文件。worktree 另有 4 個未提交的設計審查檔（`design-review.md`、`evidence/design-review-*.txt`），本檔沒動，也沒引用它們的結論
- 順序：先跑機械檢查，再核對證據，最後做對抗性抽查
- 環境：macOS（Darwin 25.6.0，arm64）、`/bin/bash` 3.2、ffmpeg 有 `h264_videotoolbox`。所有測試指令都帶 `TMPDIR=$(mktemp -d) LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=<run 目錄>/client-names.txt`（`<run 目錄>`＝`_tpm/runs/20261010-sdlc-meeting-record`）。名稱清單沒有讀出，也沒有寫進任何檔
- 安全邊界：錄製器只建到 `MH_RECORDER_DEST=$(mktemp -d)`，沒有啟動 MeetingRecorder.app，也沒有觸發 TCC 授權框。建置前後 `pgrep -x MeetingRecorder` 都是同一個既有的 menubar 實例（pid 57580，不是本輪啟動的）；`~/Applications/MeetingRecorder.app` 的 mtime 前後都是 `1791639618`。`~/.meeting-harness/e2e/` 只讀：每場用 `cp -Rp` 複製 `錄音/tracks/`（刪掉複本裡的 `finalize.json`）和 `錄音/meeting.json` 到獨立暫存目錄，`MH_RECORD_HOME` 也指到暫存目錄。跑之前和跑之後對 `e2e/` 下 191 個檔做 `stat`（mtime、大小）比對，完全相同；複本用完已刪
- 人工驗收證據：run 目錄的 `t6-results.md`（主 session 的實機紀錄）。能用場次複本在 HEAD 重跑的，以本輪重跑結果為準；只能靠當時操作才看得到的，以該檔為證並註明

## 1. 機械檢查（在 HEAD 自己重跑）

| # | 指令 | 結果 |
|---|---|---|
| V1 | `bash bin/_lint.sh && bash bin/meeting.sh doctor` | rc=0。`✓ lint 通過（26 個檔）`；doctor 全綠（地端總結模型是選用項，顯示 ◦；會議分頁標記那一行是 ◦，含「Apple Events」「選用」） |
| V2 | `python3 -m unittest discover -s tests/record -t . -v` | `Ran 127 tests in 370.369s`、`OK`、rc=0。127 支都是 `ok`，0 skipped、0 FAIL、0 ERROR；`tests/record/test_*.py` 的 `def test` 也是 127 個。`test_no_client_names_in_repo_text`、`test_tail_frame_not_overlong`、`test_tail_pad_no_extra_close_interval`、`test_sparse_tail_gap_padded`、`test_sparse_tail_gap_padded_multi_segment` 都是 `ok`，不是 skip。開跑前後 HEAD 都是 `af91ec0` |
| V3 | `/bin/bash tools/MeetingRecorder/Tests/run.sh` | rc=0，`共 50 支，失敗 0 支`；`Tests/*.swift` 的 `func test` 也是 50 個 |
| V4 | `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` | rc=0。`codesign -dvv`：`Identifier=com.meetingharness.recorder`、`flags=0x10000(runtime)`、`Authority=MeetingHarness Dev`；entitlements 只有 `com.apple.security.automation.apple-events`、`com.apple.security.device.audio-input` |
| V5 | `python3 .claude/teams/tools/check_rules.py --git . main..feature/meeting-record` | rc=0，`規則檢查：通過` |
| V6 | 腳本取出 spec §4（`## 4. 驗收條件` 到 `## 5. 影響系統`）測試欄引用的每個 `::test…` 名稱，比對 V2、V3 的 `ok` 清單 | 共引用 159 個名稱，缺少或沒通過的 0 個 |
| V7 | 名稱掃描：`grep -qF -f <清單>` 比對 `git diff main...HEAD`、`git log --format=%B main..HEAD`，再逐一掃 `git ls-files` | diff：沒有；commit 訊息：沒有。追蹤檔命中 2 個，就是派工單已知的兩個範圍外檔案；`git show main:<檔> \| grep -cF -f <清單>` 與 HEAD 的命中行數相同（各 1 行），是 `main` 上本來就有的，本檔不引述 |
| V8 | `git ls-files` 依媒體副檔名過濾；`git diff --quiet main HEAD -- bin/diarize.sh bin/_merge_speakers.py bin/_combine_audio.py bin/transcribe.sh`；`meeting.sh` 不帶參數、帶 `--bogus`；`record help` 與 `record --help` 用 `cmp` 比對 | 媒體檔 0 筆；diarize 等四檔 rc=0（沒改）；不帶參數 rc=1、`--bogus` rc=2；help 兩種寫法都 rc=0、輸出相同；`git diff --numstat main...HEAD -- bin/meeting.sh` 是 +63／−0 |
| V9 | **實機段落回歸（HEAD）**：t6 保留的 9 場（HFP2、2254、1650、AE、E2、E3、0330、collide、1340）各複製一份，用 HEAD 的 `meeting.sh record finish` 收尾，再跑 `e2e_check.py <複本> --json`。前 8 場加 `--segment-writer --fps-interval 00:05-00:55`；另外 HFP2 加 `--hfp --sync`、2254 加 `--device-switch`、1650 加 `--all-bluetooth`、0330 加 `--all-bluetooth --sync`、collide 加 `--expect-min 60 --expect-max 134`；1340 只跑預設判準 | 9 場 finish 都 rc 0，`e2e_check` 都沒有 stderr。**`fps_min_interval` 8 場全部 PASS**，(ii) 實測／上限：HFP2 241／243、2254 27／27、1650 49／49、AE 74／74、E2 1／1、E3 9／9、0330 3／3、collide 122／123；(iii) 最小間隔 1.67–6.67 ms，都 ≥ 1 ms。`video_covers_audio` 9 場差 5–9 ms；`gap` 前 8 場 PASS（max\|g\| 0.050–0.224 秒）。仍然 FAIL 的只有已知、與本輪修正無關的項目：2254 的 `no_aggregate`、`device_switch`；AE、E2、E3、collide 被 `kill -9` 那一段的 `segment_finished`；HFP2 的 `hfp`、`format_rotation`（唯一原因是複本沒有當時的 `record.status.json`，見 §4.9.3）；1340 的 `gap`（舊版錄製器的 10.425 秒）；以及畫面不是持續 60 fps 的場次的 `fps_peak`（2254 51 格、1650 16 格、E2 1 格、0330 12 格；只有播 60 fps 測試源時才有意義，見 §4.3.3） |
| V10 | §4.6.20 (i)(ii)：6 場（HFP2、2254、1650、AE、E2、E3）複本用 HEAD 收尾，`ffmpeg -map 0:a:0 -ar 48000 -f s16le` 解碼 `影片/*.mov` 音軌算樣本數，與 stream 層 `duration` 比；再拿 `錄音/*.wav` 的 format `duration` 和同一音軌比 | 全部 rc 0。(i)：HFP2 13.3、2254 19.0、1650 21.0、AE 2.3、E2 10.0、E3 19.0 ms；(ii) 與 (i) 相同。全部 ≤ 25 ms |
| V11 | §4.6.20 (iii)／§4.6.21：HFP2 複本用 HEAD 收尾後，以 `e2e_check.sync_offsets`（§4.9.3 量法）分段量「嗶聲 − 閃白」的中位數，和各段原始 `seg-*.mov` 第 0 條音軌（系統聲音）比 | seg-0001 36.0／35.8 ms（+0.2）、seg-0002 38.4／37.7（+0.7）、seg-0003 28.2／28.5（−0.3）、seg-0004 20.7／21.0（−0.3）；差都 ≤ 10 ms。全片 `sync` 64 組，最大 81 ms，PASS（V9） |
| V12 | **突變抽查**（`git archive HEAD` 解到 scratchpad，只換 `bin/_record_finalize.py`，repo 內的檔沒動；用完已刪） | (a) 整支換回 `cb417b4` 的版本：`test_tail_pad_no_extra_close_interval` 3 個子案例全紅，都是「過近間隔 2 處 > 上限 1」。(b) 只關掉 select 對複製幀的去重（`if tail_padded:` 改成 `if False:`）：只有子案例「複製幀 10.115 距最後一幀 10.108 只有 6.7 ms」紅。新測試有牙齒 |
| V13 | 1340 複本收尾後放進一個暫存根目錄，跑 `meeting.sh status <根>` | finish rc 0；status rc 0，輸出有列出這個場次 |
| V14 | §4.9.3 warnings 補查：`~/.meeting-harness/record.log`（只讀）中 HFP2 那一場（第 803 行 `── start 2026-10-12T01:59:11+08:00 ──` 到收尾「✓ 已完成」） | 「連續 15 秒」靜音告警 0 行、「寫檔失敗」0 行；4 段都有「收尾」行，丟棄計數全 0；「麥克風格式變更，提前換段」後開 seg-0003（起點 71.492 秒） |

## 2. 逐條結果

圖例：pass、fail、not_verifiable。同一條有自動部分和實機部分時拆成兩列。實機部分的判定規則：(1) 能用 t6 保留場次的複本在 HEAD 重跑的，以本輪重跑為準；(2) 只能靠當時操作才看得到的，`t6-results.md` 有明確 PASS 紀錄、內容對得上驗收句，才判 pass；(3) 沒做、只做一部分、或要使用者在場的，一律 not_verifiable。

### 4.1 介面與相容性

| 節 | 結果 | 證據 |
|---|---|---|
| 4.1.1–4.1.12 | pass | V2：spec 列的 `test_cli_dispatch.py`、`test_record_sh.py`、`test_static_rules.py::test_no_direct_exec_of_recorder`、`test_prompt.py`、`test_estimate.py` 全部 ok；V8：不帶參數 rc=1、`--bogus` rc=2、help 兩種寫法輸出相同 |

### 4.2 preflight

| 節 | 結果 | 證據 |
|---|---|---|
| 4.2.1、4.2.2 | pass | V3 `testPreflightItemsAndSeverity`、`testFailCodesAndPrecedence`、`testResultJSONKeys` ok |
| 4.2.3（替身） | pass | V2 `test_hard_fail_does_not_start` ok |
| 4.2.3（實機） | not_verifiable | t6 有 hard fail 的結束碼紀錄，但沒有記到「沒有寫任何 `seg-*.mov`、狀態為 `preflight_failed`」 |
| 4.2.4 | pass | V2 `test_warn_only_starts_with_notice` ok |
| 4.2.5（自動） | pass | V3 `testPeakWindowJudgement`、`testSystemAudioCheckTwoStage`；V2 `test_preflight_system_audio_two_stage` ok |
| 4.2.5（實機） | pass | `t6-results.md`：(a) 視窗有聲 -11.8／-12.0／-11.7 dBFS 直接 pass、log 沒有 afplay；(a) 為 -∞ 時走 (b)，測試音 -17.2／-17.4 dBFS → warn 後照常開錄（含 D21 輸出靜音的情形）。`record.log`（只讀）也有多筆「會議 app 目前沒有聲音…系統聲音擷取權限正常（測試音 …）」的 warn 行 |
| 4.2.6 | not_verifiable | 13 項中 t6 有紀錄的：第 5 項 (i)(ii)(iii)、第 6 項（沒說話、輸入音量 0）、磁碟（1 GB sparse image，rc 4）、目標視窗不存在（rc 3）、已有錄製在跑（rc 2）、場次撞名（rc 2）。沒做的：撤銷螢幕錄製權限、授權後沒重開的訊息區分、撤銷麥克風權限、電池 < 20%、最小化會議視窗、ad-hoc 簽章、Apple Events 不允許。多數要使用者在場或改系統設定／TCC |
| 4.2.7 | pass | V3 `testNonInterleavedStereoBuffer` ok |
| 4.2.8（靜態＋建置） | pass | V2 三支靜態測試 ok；V4 確認 runtime flag 與兩項 entitlement |
| 4.2.8（實機） | not_verifiable | t6 第 1 步：第 4、6 項 pass；「第一次以 `--ask-automation` 執行 `windows` 時跳出允許控制 Chrome 的授權框」沒有紀錄（同 §4.15.18） |
| 4.2.9 | pass | V3 `testSystemAudioCheckTwoStage`、`testSystemAudioWarnOnlyResult` ok |
| 4.2.10 | pass | 自動：V2 `test_windowserver_connection_initialized_on_main_thread` ok。實機：`t6-results.md` 缺陷 1 修正後 preflight、start（多場）、quick-start 都沒有再當掉 |
| 4.2.11（自動） | pass | V2 `test_start_capture_settle_and_retry` ok |
| 4.2.11（實機） | pass | `t6-results.md`：全程藍牙連續 5 次開錄 10 秒＋stop，5 次都成功，「startCapture 第一次失敗」0 次（另兩次是第 6 項正確擋下，不計入） |
| 4.2.12（自動） | pass | V3 `testStageManagerNotice`；V2 `test_stage_manager_read_only`、`test_stage_manager_documented` ok |
| 4.2.12（實機） | not_verifiable | 要使用者自己開關幕前調度，agent 不得代為切換 |

### 4.3 擷取設定

| 節 | 結果 | 證據 |
|---|---|---|
| 4.3（判準自測） | pass | V2 `test_config_snapshot_check`、`test_canvas_check`、`test_fps_peak_check`、`test_fps_min_interval_check` ok；V3 `testEvenPixelSize` ok |
| 4.3.1 | pass | V9：8 場實錄場次的 `config_snapshot` 全部 PASS（「與 spec §3.3 相同」） |
| 4.3.2 | pass | V9：9 場的 `segment_sizes`（±2 px）與 `canvas` 全部 PASS |
| 4.3.3 | pass | `config_snapshot` PASS（含 `minimumFrameInterval`）。持續變化前提的場次（HFP2，60 fps 同步測試源）：`fps_peak` 5–55 秒最大 59 格（≥ 55）；`video_format` h264、1 條音軌。全片三條件：V9 8 場 `fps_min_interval` 全部 PASS（HFP2：(i) 59 ≤ 61、(ii) 241 ≤ 243、(iii) 5.00 ms）。**前一輪在 `cb417b4` 的 fail（0330 的 (ii) 4 處 > 3）在 HEAD 已修正**：本輪 0330 為 3／3；V12 證明新測試擋得住修前版本。其他場次的 `fps_peak` FAIL 都不符合「目標視窗持續變化（播 60 fps 測試畫面）」的前提，不計入 |
| 4.3.4 | pass | `t6-results.md`：t6r2-AE 約 0:30 縮小，60 秒邊界起的 seg-0002 是新尺寸；t6r2-HFP 三次尺寸變化（含變大）都在下一個邊界生效。V9 AE 複本的 `segment_sizes`、`canvas` PASS |
| 4.3.5（自動） | pass | V2 `test_audio_scope_documented` ok |
| 4.3.5（實機） | not_verifiable | 「另一個 app 播音樂不會進 wav、同一個 Chrome 的另一分頁會進」沒有實測紀錄（D19 的 -10.2／-∞ dBFS 是 preflight 的觀察，不是錄成的 wav） |
| 4.3.6 | pass | V3 `testNextSegmentSize`；V2 `test_segment_size_read_synchronously_at_boundary` ok；實機見 §4.3.4 |

### 4.4 分段落盤

| 節 | 結果 | 證據 |
|---|---|---|
| 4.4.1 | pass | 自動：V3 `testSegmentFileName`、V2 `test_segment_tracks_check` ok。實機：V9 8 場的 `segment_files`、`segment_tracks` 全部 PASS |
| 4.4.2 | pass | 自動：V2 `test_recording_session_not_listed` ok；實機見 §4.7.1 |
| 4.4.3 | pass | 自動：V3 `testBoundaryGaps`；V2 `test_gap_check`、`test_segment_finished_check`、`test_segment_cadence_excludes_early_rotation` ok。量測閘門（V9，3 分鐘以上的 0330、1650、2254、HFP2）：`gap` max\|g\| 0.050／0.181／0.224／0.059 秒，都 < 0.5；`segment_cadence` 定期換段都是 60.000 秒（提前換段有正確排除）；這幾場 `segment_finished` PASS |
| 4.4.4 | pass | V2 `test_segment_video_start_check` ok；V9 8 場的 `segment_video_start` 全部 PASS（含靜止視窗的 E2） |
| 4.4.5 | pass | V2 `test_segment_writer_uses_assetwriter` ok |
| 4.4.6 | pass | V3 `testRouteSample`、`testSegmentVideoBitRate`、`testSegmentWriteFailedWarningKind` ok |
| 4.4.7 | pass | `t6-results.md`：t6r2-D 40 秒 `chmod a-w` → 自動停止、code 5，最終訊息以「段落連續寫檔失敗，已停止並收尾；已落盤段落保留」開頭、後接收尾失敗原因；`chmod u+w` 後 finish rc 0 |
| 4.4.8 | pass | V2 `test_segment_finished_check` ok；V9 正常 stop 的場次 `stop_tail` 差都 < 1 秒（HFP2 0.170、2254 0.491、1650 0.285、0330 0.161 秒） |
| 4.4.9 | pass | V3 `testCompletionOutcome`、V2 `test_completion_uses_outcome` ok；實機見 §4.4.7 |
| 4.4.10 | pass | V3 `testShouldEmitVideoHeartbeat`、V2 `test_video_heartbeat_on_idle` ok；實機見 §4.8.4 |

### 4.5 錄製中監看

| 節 | 結果 | 證據 |
|---|---|---|
| 4.5.1、4.5.2 | pass | V3 `testSilenceDetector15s`、`testBlackDetector5s`、`testNonBlackRatio` ok |
| 4.5.3（自動） | pass | V3 `testSuspendedDetector` ok |
| 4.5.3（實機） | not_verifiable | 最小化 10 秒後出現 `suspended` 沒有實測（同 §4.10.3） |
| 4.5.4 | pass | 自動：V3 `testMetaJSONKeys` ok。實機：2254 的 `deviceEvents` 記到輸入、輸出各次切換（V9 `--device-switch` 就是讀這些事件） |
| 4.5.5 | pass | 替身：V2 `test_stop_reports_code_5` ok。實機：`t6-results.md` t6 第三輪，缺陷 L 修後 35 GB sparse image 填到剩 1.70 GB，35 秒後自動停止，phase failed、code 5，訊息寫明磁碟原因 |
| 4.5.6 | pass | V2 `test_stop_prints_black_intervals` ok |
| 4.5.7 | pass | V3 `testPeakWindowEmptyWindowIsNegInf` ok；V9 9 場的 `levels` PASS |
| 4.5.8 | pass | V3 對應三支 ok |
| 4.5.9 | pass | V2 `test_available_bytes_not_cached` ok；實機見 §4.5.5 |

### 4.6 停止與 finalize

| 節 | 結果 | 證據 |
|---|---|---|
| 4.6.1–4.6.13 | pass | V2：spec 列的 `test_finalize.py` 各支與 `test_concurrency.py::test_finalizing_session_not_listed` 全部 ok；V9 的 `one_audio_file`、`wav_format`、`meeting_json`、`video_format`、`video_covers_audio` 全部 PASS |
| 4.6.14 | pass | V2 `test_irregular_timestamps_concat` ok |
| 4.6.15 | pass | V2 `test_truncated_fragment_segment_used` ok |
| 4.6.16 | pass | V9：1340（`SCRecordingOutput` 段落，4 段）複本用 HEAD 收尾 rc 0；`video_format`、`video_covers_audio`（差 6 ms）、`one_audio_file`、`wav_format` PASS；`gap` 10.425 秒 FAIL（當時的空隙，spec 允許只記錄） |
| 4.6.17 | pass | V2 `test_tail_frame_not_overlong` ok（有執行，不是 skip） |
| 4.6.18 | pass | 自動：V2 `test_sparse_vfr_last_segment_covers_audio` ok。實機：V9 2254、1650 複本 rc 0，`video_covers_audio` 差 5、9 ms |
| 4.6.19 | pass | V2 `test_gap_uses_finalize_audio_duration` ok；V9 的 `gap` 備註都沒有「與實測不符」 |
| 4.6.20 | pass | V2 `test_concat_no_audio_drift`、`test_finalize_concat_reencodes_audio_once` ok；V10 實錄 6 場 (i)(ii) 都 ≤ 21 ms；V11 (iii) HFP2 分段差 −0.3 到 +0.7 ms |
| 4.6.21 | pass | 本輪自己重跑（V9、V10、V11）：六場 rc 0；`video_covers_audio`、`gap` 全 PASS；其他 `--segment-writer` 判準只有已知的 2254 `no_aggregate`、AE／E2／E3 `segment_finished` FAIL；(i) 六場都成立；HFP2 分段中位數差 ≤ 0.7 ms |

### 4.7 並發安全

| 節 | 結果 | 證據 |
|---|---|---|
| 4.7.1 | pass | 自動：V2 `test_recording_session_not_listed` ok。實機：`t6-results.md`「t6 第二輪 7」錄製中 `meeting prep <根>` 回「找不到任何場次」rc 3 |
| 4.7.2 | pass | V2 `test_finalizing_session_not_listed` ok |

### 4.8 crash 救援

| 節 | 結果 | 證據 |
|---|---|---|
| 4.8.1 | pass | 自動：V2 `test_expect_duration_check` ok。實機：`t6-results.md` collide 場次 02:08:27 開錄、02:10:40 `kill -9`（133 秒），`record status` rc 5 並提示 finish，finish rc 0；V9 本輪複本用 HEAD 收尾 rc 0，`expect_duration` wav 130.0 秒，在 [60, 134] 內，PASS |
| 4.8.2 | pass | V2 `test_idempotent_second_run` ok；`t6-results.md` collide 再跑 finish「已完成（不重做）」rc 0 |
| 4.8.3 | pass | V2 `test_crash_loss_documented` ok |
| 4.8.4 | pass | `t6-results.md` t6 第二輪：AE（有畫面，110 秒 `kill -9`）、E2（靜止視窗）、E3（靜止且會議 app 沒聲音）的 finish 都沒有略過段落。本輪複本（V9）的音訊軌 109.97／100.28／100.33 秒，都 ≥ 110 − 21 ＝ 89 秒 |

### 4.9 裝置切換與藍牙耳機

spec §4.9 規定 §4.9.1–4.9.3 在 test 段不得標 not_verifiable。本輪 §4.9.1 仍然沒有合格的實機場次，見第 5 節 Q1（blocking）。

| 節 | 結果 | 證據 |
|---|---|---|
| 4.9.1（自動） | pass | V2 `test_device_switch_check` ok（含 2.5 秒 PASS、3 秒 FAIL 的邊界案例） |
| 4.9.1（實機） | not_verifiable | 唯一有切換的 2254 不符合前提：(1) 切換順序不是「內建 → 藍牙 → 內建」各約一分鐘，且途中經過 aggregate／unknown 中間狀態；(2) 系統聲音在 43–178.5 秒沒有緩衝（影片停了）。V9 用 HEAD 判準跑 `--device-switch` 仍 FAIL（161.3 秒處系統聲音 20.5 秒、麥克風 9.0 秒、混音 6.7 秒），原因是前提不成立，既不能當錄製器 fail，也不能當 pass。要使用者戴藍牙耳機重做 |
| 4.9.2（機械） | pass | V9 1650（全程藍牙輸入與輸出、255 秒、使用者在場）用 HEAD 收尾：`all_bluetooth`、`all_bluetooth_duration`、`no_aggregate` PASS，`e2e_check` 中只有 `fps_peak` FAIL（前提不符，見 §4.3.3）。0330（190 秒）也 PASS，但那場是夜間無人錄的 |
| 4.9.2（聆聽） | not_verifiable | 「使用者聽 `影片/*.mov`，記下遠端與自己聲音各一個時間點」沒有紀錄 |
| 4.9.3 | pass | V9 HFP2 複本：70.10 秒輸入切到藍牙麥克風、`audioFormatEvents` 有 `sampleRate` 改變，71.492 秒提前換段；格式變更時系統聲音中斷 1.5 秒、麥克風 2.5 秒（< 3 秒）；`sync` 64 組最大 81 ms；`video_covers_audio` 差 5 ms。`e2e_check` 的 `hfp`、`format_rotation` 判 FAIL，**唯一原因**是複本找不到當時的 `record.status.json`、無法核對 warnings；改以 V14 查 `record.log` 中該場：沒有靜音告警、沒有寫檔失敗，4 段正常收尾 |
| 4.9.4（靜態） | pass | V2 `test_no_default_device_write_in_sources`、`test_no_default_device_write_in_record_sh` ok |
| 4.9.4（實機） | not_verifiable | 「不需開啟音訊 MIDI 設定」沒有紀錄；§4.9.1 的場次還沒做；2254 的 `devices` 出現過 `aggregate`（使用者在系統設定切換途中經過的中間狀態） |

### 4.10 端到端

| 節 | 結果 | 證據 |
|---|---|---|
| 4.10.1 | not_verifiable | 情境是「通話 app 自我通話＋有聲影片＋自己說話」。0330（3 分鐘）用 HEAD 收尾後，對應 §4.3.1–4.3.2、§4.4.3、§4.6.1–4.6.4 的判準全部 PASS（V9），但那場是夜間用同步測試源錄的，沒有通話也沒人說話，情境不符 |
| 4.10.2 | not_verifiable | Space 切走 30 秒沒有實測；`test_space_interval_check` 是綠的 |
| 4.10.3 | not_verifiable | 最小化、Mission Control、native 全螢幕都沒有實測；`test_meeting_tab_marking_documented` 是綠的 |
| 4.10.4 | not_verifiable | 要使用者實際去聽 |

### 4.11 觸發層與 menu bar

`git diff --stat cb417b4 HEAD` 沒有碰到 `tools/MeetingRecorder/`，自動部分以 V2、V3 重跑結果為準。

| 節 | 結果 | 證據 |
|---|---|---|
| 4.11.1（自動） | pass | V3 `testQuickStartDecision` ok |
| 4.11.1（實機） | not_verifiable | t6 只做了「3 個 ★ → 通知、不開錄、不跳授權框」的 code 3 分支；「恰好一個 ★ 時以預設值開錄」與 code 2 分支沒有紀錄 |
| 4.11.2–4.11.9（自動與靜態） | pass | V3 `TriggerTests.swift` 各支 ok；V2 `test_no_global_event_monitor`、`test_hotkey_uses_carbon`、`test_hotkey_failure_logged`、`test_shortcuts_instruction`、`test_menubar_uses_template_image`、`test_start_item_shows_hotkey`、`test_menubar_sets_accessibility_label`、`test_status_title_uses_label_color`、`test_menubar_refresh_while_menu_open` ok |
| 4.11.2、4.11.3、4.11.5–4.11.9（實機與截圖） | not_verifiable | 三態的實際顯示、按快捷鍵、選單展開時的秒數、有／無告警各停一次、截圖，都要使用者在場；設計審查的截圖留給使用者 |
| 4.11.10 | pass | 自動：V3 `testMenuBarLockSingleInstance`、V2 `test_menubar_lock_only_in_menubar` ok。實機：`t6-results.md` 連開兩次 `--args menubar` 只留一個實例，第二個寫 log「已有 MeetingRecorder 選單在執行，本實例結束」 |

### 4.12 skill 與文件

| 節 | 結果 | 證據 |
|---|---|---|
| 4.12.1–4.12.4、4.12.6–4.12.10 | pass | V2 `test_docs.py` 各支與 `test_diarize_and_merge_untouched` ok；V8 diarize 等四檔沒改 |
| 4.12.5 | not_verifiable | symlink 由主 session 在 deliver 閘門之後建立 |

### 4.13 迴歸與 verify

| 節 | 結果 | 證據 |
|---|---|---|
| 4.13.1、4.13.2、4.13.7 | pass | V1；V2 `test_lint_passes_26_files`、`test_doctor_green_without_recorder`、`test_git_governance_content` ok |
| 4.13.3 | pass | 自動：V2 `test_status_lists_finalized_session` ok；實機：V13 |
| 4.13.4 | pass | `t6-results.md`：HFP2 場次 prep rc 0，`transcript.raw.md` 1105 bytes 非空，`diarization.json`、`transcript.speakers.md` 都存在（模型執行本輪沒有重跑） |
| 4.13.5 | pass | `t6-results.md`：既有已完成場次的複本用現行 diarize 連跑兩次，逐秒一致率 100%；V8 確認 diarize 相關四檔對 `main` 零修改 |
| 4.13.6 | pass | V5 |

### 4.14 資料邊界

| 節 | 結果 | 證據 |
|---|---|---|
| 4.14.1、4.14.2 | pass | V2 `test_no_media_in_repo`、`test_gitignore_media_rules` ok；V8 媒體檔 0 筆 |
| 4.14.3 | pass | V2 帶清單環境變數跑，`test_no_client_names_in_repo_text` ok（不是 skip）；V7 |

### 4.15 視窗清單與會議標記

| 節 | 結果 | 證據 |
|---|---|---|
| 4.15.1–4.15.8 | pass | V3 `WindowListTests.swift` 各支 ok |
| 4.15.9 | pass | V3 `testDiagnoseIncludesExcluded` ok（`diagnose-windows` 實際執行要螢幕錄製授權，本輪不跑） |
| 4.15.10–4.15.15 | pass | V2 對應測試全部 ok；V1 doctor 有會議分頁標記那一行 |
| 4.15.16–4.15.18 | not_verifiable | 會議頁 native 全螢幕、通話 app 視窗、Apple Events 授權兩條路，都要使用者實機操作；t6 沒有紀錄 |

**統計**：fail 0。not_verifiable 都是要使用者在場、要改系統設定或 TCC、或要等 deliver 之後才能做的項目（清單見第 6 節）。其餘都是 pass。其中 §4.9.1 實機屬於 spec 規定「test 段不得標 not_verifiable」的項目，見 Q1。

## 3. 缺陷

本輪沒有新的缺陷（fail 0）。

前一輪在 `cb417b4` 的 §4.3.3 (ii) fail（0330 過近間隔 4 處 > 上限 3）已由 `af91ec0` 修正。有效的證據：V9（HEAD 的 8 場 `fps_min_interval` 全 PASS，0330 為 3／3）、V12（新測試擋得住修前版本，也擋得住只拿掉複製幀去重的局部退回）。

## 4. 反作弊檢查

### 4.1 本輪（`cb417b4..HEAD`，即 `af91ec0`）

| 項目 | 結果 | 依據 |
|---|---|---|
| 測試被 skip／fixme／only／刪除 | 沒有 | `af91ec0` 對測試只有新增（`test_finalize.py` +41／−0）。新測試開頭的 `require_videotoolbox()` 是既有的 skip 條件（§4.6.17 明文允許）；本機有這個編碼器，V2 實際執行並 ok |
| 斷言被放寬 | 沒有 | 沒有刪改既有斷言；`e2e_check.py` 本輪沒改 |
| 紅燈與修正在同一個 commit | 有，不影響判定 | 新測試和修正在同一個 fix commit，沒有獨立紅燈 commit。以 V12 補證：finalize 換回修前版本，新測試 3 個子案例全紅 |
| 被測物被 mock | 沒有 | 新測試用真的 ffmpeg 合成段落，跑真的 `meeting.sh record finish` |
| 錯誤被吞、加 retry | 沒有 | diff 只改 ffmpeg 濾鏡運算式（`setpts`、`select`）與補尾門檻，沒有新增 `try`／`except`／重試 |
| 修正只動補尾的複製幀 | 是 | `setpts` 與 `select` 的新條件都以 `gt(PTS, round(last/TB))` 限定在最後一幀之後的複製幀；原始影格仍只丟完全相同 PTS 的重複幀。V9 中其他判準的結果與 `t6-results.md` 記的修前結果一致 |
| 證據的 commit 是不是 HEAD | 是 | V2 開跑前後、V9 開跑前、寫本檔前都查過 HEAD＝`af91ec0`。progress.md 記的「Python 127 全綠」與本輪重跑相符，但本檔只用自己重跑的數字 |
| 上游既有測試被改 | 不適用 | 本 repo 沒有上游；`main` 上沒有任何 `tests/` 或 `Tests/` 測試檔，本 epic 的測試檔全是新增（`git diff --name-status main...HEAD` 都是 `A`） |

### 4.2 整個 epic（`main..HEAD`，複查）

| 項目 | 結果 | 依據 |
|---|---|---|
| 既有斷言被刪或放寬 | 有，都有 spec §6 紀錄 | 掃過所有動到測試的非合併 commit 的刪除行（排除註解與空行），含斷言或判準的有 3 個：(1) `e97c445`：`TriggerTests.swift` 的「M7：stopping、有告警類 → warning」改成 M6a 的預期，對應 §6 第 41 條（test 段使用者核准）。(2) `ec3ed88`：`test_static_rules.py` 刪掉「`.fail` 訊息應保留『取消輸出靜音』『把音量調大』」，對應 §6 第 54 條（使用者核准，D21）。(3) `731bd00`：`test_e2e_check.py` 的 `ds_quiet` 由 `assert_fail` 改判 PASS（另新增 2.5 秒 PASS、3 秒 FAIL 的邊界案例），以及 `e2e_check.py` 的 `device_switch`、`hfp`、`fps_min_interval`、`sync` 判準改寫，對應 §6 第 64、66、68 條。**注意**：第 63–70 條的核准來源是主 session 依使用者「剩下的你自己做」代為定案、註明「使用者可於醒來後改選」，不是使用者對這幾條的直接核准，見 Q2 |
| skip／fixme／only／expectedFailure | 沒有違規 | 全 repo 只有兩個 `skipTest`：`test_finalize.py:329`（沒有 `h264_videotoolbox` 才略過，§4.6.17 允許；本機有）、`test_static_rules.py:568`（沒設名稱清單才略過，§4.14.3；本輪有設）。V2 0 skipped |
| retry、sleep | 不算作弊 | 測試 diff 中的 `time.sleep(0.05)`／`(0.2)` 是輪詢替身程序狀態；`test_start_capture_settle_and_retry` 測的是產品規格 §4.2.11 的重試行為，不是測試本身重跑 |

### 4.3 文件和實作的落差（不判 fail）

- 缺陷 N 的修正（`94f54d2`）與 `af91ec0` 的補尾規則（複製幀落在 cap 前 1/60 秒內併進 cap；最後一幀距 cap 不到 1/60 − 1 ms 不補尾；複製幀距前一個留下的影格不到 1/60 − 1 ms 就丟）都沒有寫進 spec §6 或 `design.md §7.4`：`grep -c '缺陷 N'` 在 spec.md、design.md 都是 0，`CLONE_SNAP`／`CLOSE_GAP` 也是 0。行為有 `test_tail_pad_no_extra_close_interval`、`test_sparse_tail_gap_padded*` 保護，但文件沒跟上，列為衍生工作
- 2254、1650、AE、E2、E3、0330 的 `fps_min_interval` (ii) 都剛好等於上限（每個邊界恰好 1 處），符合字面要求但沒有餘裕；collide 的 (iii) 最小間隔 1.67 ms，離 1 ms 下限也不遠

## 5. 待決（需要使用者決定）

- **Q1（blocking）：§4.9.1 沒有合格的實機場次**。spec 規定 §4.9.1–4.9.3 在 test 段不得標 not_verifiable。§4.9.3 已用 HFP2 複本驗過，§4.9.2 的機械部分已用 1650 驗過；§4.9.1 唯一的 2254 場次不符合前提。
  - 選項 A：使用者戴藍牙耳機重錄一場 3 分鐘（內建 → 藍牙 → 內建，各約 1 分鐘；被錄的視窗持續有聲、本人持續說話），再跑 `e2e_check.py --device-switch`。代價：使用者要在場約 10 分鐘。**建議選這個**：使用者今晚就要戴耳機開會，錄製中切耳機是最可能遇到、也最值得實測的情境
  - 選項 B：在 spec §6 記一條例外，把 §4.9.1 改成 deliver 之後補驗。代價：上線前沒驗過錄製中切換耳機
  - 選項 C：拿 2254 的部分證據（`deviceEvents` 有記到；輸出切換時系統聲音只斷 0.5 秒）當作通過。代價：違反 §4.9 對前提的定義，不建議
- **Q2（不阻擋，在閘門 3 一併確認）**：spec §6 第 63–70 條（幕前調度、sync 量法、缺陷 J 修法、3 秒連續低音量、磁碟快取、fps 三條件、§4.8.1 上限）是主 session 在使用者睡覺時依建議選項代為定案的；其中第 66、68 條放寬了 `test_e2e_check.py` 一個既有預期與 `e2e_check.py` 的判準。請使用者在閘門 3 明確核准或改選，並把核准人寫回 §6
- **延續**：§4.2.12 的實機確認（使用者自己開關幕前調度）、既有使用者場次要不要用修後的 finalize 重新收尾（spec §7 疑慮 30），都要等使用者決定

## 6. 範圍

- **涵蓋**：spec §4.1–§4.15 每一條的自動部分（127 支 Python、50 支 Swift、check_rules）；在暫存目錄建錄製器並檢查簽章與 entitlement；9 場 t6 實錄場次的複本用 HEAD 收尾並跑 `e2e_check.py`（含 `--segment-writer`、`--fps-interval`、`--hfp --sync`、`--all-bluetooth`、`--device-switch`、`--expect-*`）；§4.6.20 (i)(ii)(iii) 的量測；1340 複本的 `meeting.sh status`；finalize 修法的整支與局部突變抽查；HFP2 那一場的 `record.log` 告警補查；反作弊（本輪 diff、整個 epic 的測試檔歷史）；名稱掃描（只報有或沒有）
- **未涵蓋（not_verifiable）**：§4.2.3 實機、§4.2.6、§4.2.8 實機（Apple Events 授權框）、§4.2.12 實機、§4.3.5 實機、§4.5.3 實機、§4.9.1 實機、§4.9.2 聆聽、§4.9.4 實機、§4.10.1–4.10.4、§4.11.1 實機（預設開錄與 code 2）、§4.11.2／4.11.3／4.11.5–4.11.9 的實機與截圖、§4.12.5、§4.15.16–4.15.18。原因：要使用者在場、要改系統設定或 TCC、或要等 deliver 之後
- **未涵蓋（其他）**：沒有啟動錄製器，沒有做新的實錄；`kill -9` 當下 `record status` 的回傳、prep 與 diarize 的模型執行、§4.4.7／§4.5.5 的錄製中操作，以 `t6-results.md` 為證，沒有重跑；沒有用修前版本的 finalize 對 9 場做逐條對照（只用合成素材做突變抽查）；跨 process 的 menubar 鎖、HotKey 註冊失敗路徑本輪沒有另做 probe（`Sources/` 本輪沒改，以 V3 單元測試為準）。HIG 設計審查由設計審查負責

## 7. 本檔自檢

寫完本檔後重跑了 `test_no_client_names_in_repo_text`（帶清單）與 `python3 .claude/teams/tools/check_rules.py specs/meeting-record/verifier.md`，結果記在本輪信封。

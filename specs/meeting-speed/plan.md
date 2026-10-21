# plan：meeting-speed

- 上游：`intent.md`（閘門 1 已核准，§7 為準）、`design.md`、`spec.md`、`adr/`。
- 狀態：**草稿，待閘門 2 核准**。
- 子任務 id 是短名，**不是任務編號**；分支 `feature/meeting-speed--<id>`，各開 worktree，從 `feature/meeting-speed` 開。
- 起點：`_tpm/runs/20261021-sdlc-meeting-speed/plan-approved.md:35-107` 的 12 個子任務、4 層；調整理由見 `design.md` §1.1。

---

## 1. 子任務與分層

| 層 | id | kind | owns（只能改這些） | depends_on | Story |
|---|---|---|---|---|---|
| Red | `red-py` | test | `tests/record/test_ms_*.py`（新）、`tests/record/fakes/asr_exc0/`（新）、`tests/record/fakes/pymod/`（新）、`tests/record/fakes/ms_*`（新）、`tests/record/vectors/ms-*.json`（新）；**§6 核准後才可改**：`tests/record/test_regression.py`（第 18 條）、`tests/record/test_r3_vtt_raw.py`（第 20 條）、`tests/record/test_r3_lock.py`（第 21 條） | — | G1–G9 |
| Red | `red-swift` | test | `tools/MeetingRecorder/Tests/MSCoreTests.swift`（新）、`tools/MeetingRecorder/Tests/main.swift`（只加一列） | — | G1、G2、G5、G9 |
| 1 | `ms-core` | code | `tools/MeetingRecorder/Sources/Core/` | `red-swift` | G1、G2、G5、G9 |
| 1 | `asr-robust` | code | `bin/transcribe.sh`、`bin/lib/_transcript_quality.py`（新）、`.claude/skills/meeting-transcribe/` | `red-py` | G5、G6、G1、G8 |
| 1 | `diarize-iron` | code | `bin/diarize.sh`、`bin/_diarize_pyannote.py`、`bin/_merge_speakers.py`、`bin/_render.py`、`bin/_voiceprint.py`、`bin/lib/_harness.py`（新）、`.claude/skills/meeting-speakers/`、`.claude/skills/meeting-summary/`、`.gitignore`、`config.json` | `red-py` | G6、G1、G2、G8 |
| 1 | `prep-pipeline` | code | `bin/meeting.sh`、`bin/lib/_record_lib.py` | `red-py` | G1、G5、G7、G8 |
| 1 | `record-sh-split` | code | `bin/record.sh` | `red-py` | G8 |
| 1 | `video-spike` | check | `specs/meeting-speed/evidence/video-spike.md`（新） | — | G1、G4 |
| 1 | `replay-bench` | code | `tools/bench/`（新） | `red-py` | G1、G4 |
| 2 | `finalize-fast` | code | `bin/_record_finalize.py`、`bin/lib/_finalize_*.py`（新）、`.claude/skills/meeting-record/` | `red-py`、`prep-pipeline`、`video-spike` | G1、G4、G5、G8、G9 |
| 2 | `recorder-capture` | code | `tools/MeetingRecorder/Sources/Capture/` | `red-py`、`ms-core`、`video-spike` | G1、G2、G5、G8、G9 |
| 2 | `trigger-ui` | code | `tools/MeetingRecorder/Sources/Trigger/` | `red-py`、`ms-core` | G1、G5、G8、G9 |
| 3 | `incremental-asr` | code | `bin/lib/_asr_worker.py`（新） | `finalize-fast`、`prep-pipeline`、`asr-robust`、`diarize-iron` | G2、G4、G1 |
| 3 | `docs-cleanup` | doc | `README.md`、`.claude/workflows/meeting-pipeline.js` | `finalize-fast`、`prep-pipeline` | G8 |

**檔案歸屬**：所有子任務的 owns 完全不重疊，跨層也不重疊；每支檔從頭到尾只有一個擁有者。派工單點名會被多個子任務碰的四支檔：`MenuBar.swift`＝`trigger-ui`（停止路徑 log、`.early` 觸發、通知、拆檔都在這裡）；`RecordingSession.swift`＝`recorder-capture`（畫布鎖定、丟幀、起 worker、preflight 錯誤 log、完成通知、拆檔）；`_record_finalize.py`＝`finalize-fast`（音訊先出＋影片 copy＋驗證後移＋拆檔）；`meeting.sh`＝`prep-pipeline`（含 stitch 交棒的呼叫端，所以 `incremental-asr` 不必碰它，見 spec §3.9）。

**結構重構（G8）怎麼排**：計畫原本把重構放在最後一層（split-swift、split-scripts、docs-cleanup），理由是「速度改完再重構，避免衝突」（intent §2 G8）。但重構要動的檔正好是速度層改的檔，分成兩個子任務就一定兩個子任務擁有同一支檔（`check-envelope.sh` 會擋）。本 plan 改成：**每支檔的擁有者在自己的速度／修正 commit 之後，另做一個 `refactor(meeting-speed)` commit**。衝突的來源（兩個人同時改同一支檔）因此不存在，「速度先、重構後」在子任務內部仍成立；`record.sh` 不被速度改動碰，獨立成 `record-sh-split` 在第 1 層並行。代價：`finalize-fast`、`recorder-capture`、`trigger-ui` 的工作量變大（見 design §1.1）。

**數量**：15 個、Red＋3 層（計畫 12 個、4 層）。合併：state-lock＋prep-parallel → `prep-pipeline`；audio-first＋video-copy 的 finalize 端 → `finalize-fast`；split-swift、split-scripts 依檔案併進各檔的擁有者。新增：`red-py`、`red-swift`（紅燈層）、`ms-core`（Core 一次編譯，散在多個子任務就沒人能單獨跑綠）、`video-spike`（intent §7 Q3 要求先實測）、`replay-bench`（intent §7 Q6）、`record-sh-split`（`record.sh` 沒有別的擁有者）。preflight-diag 與 stop-gate 依目錄併進 `recorder-capture`、`trigger-ui`、`ms-core`。

---

## 2. 各子任務要點與完成條件（可機械判定）

**共通**：只改 `owns`；不改 `progress.md`；**不改任何既有測試與既有替身**（§6 第 18、20、21 條核准後由 `red-py` 改，其他人一律不改）；verify（`bash bin/_lint.sh && bash bin/meeting.sh doctor`）全綠才 commit；`bin/` 頂層檔數維持 26；commit 訊息 `test(meeting-speed)`／`feat(meeting-speed)`／`docs(meeting-speed)`，內文寫 spec 節號，結尾署名行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`；commit 前以 `grep -qiF -f <client-names.txt>` 掃 diff 與 commit 訊息（只回報有／沒有）。測試指令一律加前綴：

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8 MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt
```

（pyenv shim 會卡住，Python 一律用 `$PY`。）

- **red-py**：(1) spec §4 驗法欄列的 `tests/record/test_ms_*.py` 函式與類別都存在（逐字）；(2) 替身：`fakes/asr_exc0/mlx_whisper`（例外時回 0、只寫 txt）、`fakes/pymod/mlx_whisper/__init__.py`（`transcribe()` 計數載入次數、依輸入回固定段落）、`fakes/ms_slow_ffmpeg.sh`（記錄呼叫順序、可讓驗證步驟變慢或失敗）、`fakes/ms_count_ffprobe.sh`（計數）；(3) `$PY -m unittest discover -s tests/record -t .` 的輸出沒有 `ImportError`、`ModuleNotFoundError`、`SyntaxError`、`NameError`；(4) 失敗只出現在 §3「Red」列允許的測試；(5) `git diff --diff-filter=M --name-only HEAD~ -- tests/` 只列 §6 已核准條目對應的檔，且只動該條列出的斷言（commit 內文寫條號）；未核准時為空；(6) 新檔不得含真實名稱，`test_ms_docs.py::test_no_client_names_in_ms_files` 綠且不得 skipped。
- **red-swift**：(1) `MSCoreTests.swift` 有 spec §4 列的全部 `swift:` 函式（逐字），陣列名 `mrtMSCoreTests`；(2) `Tests/main.swift` 只多一列 `("MSCoreTests", mrtMSCoreTests),`；(3) `/bin/bash tools/MeetingRecorder/Tests/run.sh` 只因缺 spec §3.10 名稱而編譯失敗（錯誤都是 `cannot find … in scope`、缺成員或缺 enum case 類）。
- **ms-core**：`/bin/bash tools/MeetingRecorder/Tests/run.sh` 全綠（既有 `TriggerTests`、`PreflightTests`、`RecordsTests`、`R3xBackgroundTests` 不改）；spec §3.10 名稱與簽名逐字存在；`Sources/Core/` 不 import AppKit；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 成功（Capture／Trigger 未改也要能編：不改既有 `SystemAudioCheck`、`shouldAutoPrep` 的簽名）。
- **asr-robust**：`$PY -m unittest tests.record.test_ms_asr_robust tests.record.test_r3_transcript_vad tests.record.test_r3_vtt_raw tests.record.test_deliver_fixes tests.record.test_t7_fixes` 綠（`test_r3_vtt_raw::test_diarize_keeps_raw` 依 §3 的條件例外）；重構 commit 後 `$PY -m unittest tests.record.test_ms_refactor -k test_transcribe_no_quality_heredoc` 綠；`transcribe.sh:3` 的過期註解更新（spec §4.13.4）；`meeting-transcribe` SKILL 寫明 raw 不轉、`transcript.md` 是正體版。
- **diarize-iron**：`$PY -m unittest tests.record.test_ms_iron_rules tests.record.test_r3_vtt_raw tests.record.test_review_fixes tests.record.test_r3_annotations` 綠（`test_ms_iron_rules::test_diarize_skips_16k_conversion` 只在 §6 第 19 條核准時要求綠，不核准時這支由 `red-py` 不寫）；`test_ms_docs.py` 的 `test_speakers_skill_annotate`、`test_summary_skill_no_session_embeddings` 綠；`git grep -n embeddings.json -- bin/diarize.sh` 不再出現寫入場次資料夾的路徑；`_merge_speakers.py:3` 註解更新；`config.json` 加 `transcribe.incremental.enabled: true`、`diarize.note` 不再寫 `embeddings.json`；重構 commit 後 `$PY -m unittest tests.record.test_ms_refactor -k test_harness_config_single_definition` 綠；§6 第 18 條**未核准**時改走 `bin/lib/` 新入口、`git diff --exit-code main -- bin/diarize.sh bin/_merge_speakers.py` 回 0。
- **prep-pipeline**：`$PY -m unittest tests.record.test_ms_prep tests.record.test_concurrency tests.record.test_r3_record_lib tests.record.test_surface_parsers tests.record.test_cli_dispatch` 綠（例外見 §3）；`tests.record.test_regression` 綠；prep 的結束碼集合 {0,2,3}；`_record_lib` 公開 `load_json`、`write_json_atomic`、`record_home`（spec §3.11）。
- **record-sh-split**：`$PY -m unittest tests.record.test_ms_refactor -k test_cmd_control_length` 綠；`$PY -m unittest tests.record.test_record_sh tests.record.test_r2_cli tests.record.test_r3_lock tests.record.test_r3x_background tests.record.test_surface_parsers tests.record.test_cli_dispatch` 綠（`test_r3_lock`、`test_r3x_background` 不改：`cmd_stop` 不動）；`record.sh:973` 的過期註解更新；只做 `refactor(meeting-speed)`，行為不變。
- **video-spike**：`specs/meeting-speed/evidence/video-spike.md` 存在，含四節且每節有可重跑的指令與實測數字：(1) macOS 15 SDK 的 `SCStreamConfiguration.preservesAspectRatio` 宣告與可用版本（`grep` SDK 標頭，附路徑:行號）；(2) 以 `tests/record/_media.py` 同款的 SCK 特性合成段落（VFR、`time_base=1/600`、同尺寸、同 extradata）跑 copy remux＋concat，spec §4.4.5 的判準逐項 PASS／FAIL；(3) 2 小時 PCM 上 `aac` 與 `aac_at` 的編碼耗時；(4) 結論「可行／不可行」。不可行時信封 `status` 用 `needs_decision`，`finalize-fast`、`recorder-capture` 不得開工。不得讀 `~/.meeting-harness/`；實機段落只在使用者提供路徑時使用，文件不寫路徑與場次名。
- **replay-bench**：`$PY -m unittest tests.record.test_ms_replay` 綠；`$PY tools/bench/replay.py --help` 回 0；報告鍵與 spec §3.12 相同。
- **finalize-fast**：`$PY -m unittest tests.record.test_ms_audio_first tests.record.test_ms_video_copy tests.record.test_finalize tests.record.test_r2_finalize tests.record.test_r3_finalize_guard tests.record.test_r3_sync_compensate tests.record.test_r3x_parallel_finalize tests.record.test_concurrency tests.record.test_static_rules tests.record.test_review_fixes tests.record.test_e2e_check tests.record.test_r2_e2e_check` 綠；`$PY -m unittest tests.record.test_ms_prep -k test_finalize_set_state_uses_lock` 綠；`segment_audio_pcm` 是 `_record_finalize` 的頂層名稱；`meeting-record` SKILL 寫明音訊先出、`.verify-failed.mov`、畫布鎖定的代價。重構 commit（拆到 `bin/lib/_finalize_*.py`，被 `test_r3x_parallel_finalize.py` 讀寫的模組全域與靜態測試釘住的名稱留在原模組）後：`$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_record_finalize -k test_record_helpers_single_definition` 綠，上列測試仍綠。
- **recorder-capture**：`$PY -m unittest tests.record.test_ms_app_static -k CaptureStatic` 綠；重構 commit（以 `extension` 拆到 `Capture/RecordingSession+*.swift`、`Capture/PreflightChecks.swift`）後 `$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_recording_session -k test_preflight_run_length` 綠；既有 `test_r3_app_static`、`test_r3x_app_static`、`test_r3_skip_finalize`、`test_r2_static`、`test_static_rules`、`test_t7_fixes` 綠（不改）；`run.sh` 綠；建置成功。
- **trigger-ui**：`$PY -m unittest tests.record.test_ms_app_static -k TriggerStatic` 綠；重構 commit（拆出 `Trigger/MenuBar+*.swift`）後 `$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_menubar` 綠；既有 `test_r3_app_static`、`test_r3x_app_static`、`test_r2_static`、`test_t7_fixes`、`test_static_rules` 綠（不改）；建置成功；`grep -n lastPathComponent tools/MeetingRecorder/Sources/Trigger/Completion.swift` 不得出現在組通知內文的路徑上（由 `TriggerStatic::test_prep_notifications_no_name` 判）。
- **incremental-asr**：`$PY -m unittest tests.record.test_ms_incremental_asr tests.record.test_ms_prep tests.record.test_r3_record_lib` 綠；`$PY bin/lib/_asr_worker.py --help` 回 0；`bash bin/_lint.sh` 檔數維持 26。
- **docs-cleanup**：`$PY -m unittest tests.record.test_ms_docs -k test_readme_flow -k test_meeting_pipeline_js_deprecated` 綠；`tests.record.test_docs`、`test_r2_docs`、`test_r3_docs`、`test_r3x_docs` 綠（不改）。
- **重構共通**：重構 commit 的 `git diff --diff-filter=M --name-only <commit>~ <commit> -- tests/ tools/MeetingRecorder/Tests/` 為空；非改既有測試不可時，停下以 `needs_decision` 回報（spec §6 第 22 條），不得自行改測試。

---

## 3. 每層整合後的測試指令（integrator 照此跑，一律加 §2 的前綴）

| 層 | 合併後必須回 0 的指令 | 預期仍紅、只記錄不阻擋 |
|---|---|---|
| Red | `bash bin/_lint.sh && bash bin/meeting.sh doctor`；`$PY -m unittest tests.record.test_finalize tests.record.test_r2_finalize tests.record.test_surface_parsers tests.record.test_cli_dispatch tests.record.test_docs tests.record.test_record_sh tests.record.test_r2_cli tests.record.test_concurrency tests.record.test_static_rules` | 全量 Python：失敗只在 `test_ms_*`（全部，`test_ms_docs::test_no_client_names_in_ms_files` 除外，它要綠）；第 20 條核准時 `test_r3_vtt_raw::test_diarize_keeps_raw`；Swift `run.sh` 編譯失敗（缺 §3.10 名稱） |
| 第 1 層 | 上一列全部；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`$PY -m unittest tests.record.test_ms_asr_robust tests.record.test_ms_iron_rules tests.record.test_ms_replay tests.record.test_r3_transcript_vad tests.record.test_deliver_fixes tests.record.test_t7_fixes tests.record.test_review_fixes tests.record.test_r3_annotations tests.record.test_r3_record_lib tests.record.test_regression tests.record.test_r3_lock tests.record.test_r3x_background`；`$PY -m unittest tests.record.test_ms_prep`（除下欄）；`$PY -m unittest tests.record.test_r3_vtt_raw`（第 20 條核准時含 `test_diarize_keeps_raw`）；`$PY -m unittest tests.record.test_ms_refactor -k test_transcribe_no_quality_heredoc -k test_harness_config_single_definition -k test_cmd_control_length`；`$PY -m unittest tests.record.test_ms_docs -k test_stale_comments_updated -k test_speakers_skill_annotate -k test_summary_skill_no_session_embeddings`；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；`video-spike` 結論為「可行」 | `test_ms_audio_first`、`test_ms_video_copy`、`test_ms_incremental_asr`、`test_ms_app_static`（全部類別）、`test_ms_refactor` 的 `test_line_limit_*`、`test_preflight_run_length`、`test_record_helpers_single_definition`、`test_ms_prep` 的 `test_finalize_set_state_uses_lock`、`test_prep_uses_stitched`、`test_ms_docs` 的 `test_readme_flow`、`test_meeting_pipeline_js_deprecated` |
| 第 2 層 | 上一層全部；`$PY -m unittest tests.record.test_ms_audio_first tests.record.test_ms_video_copy tests.record.test_ms_app_static tests.record.test_ms_refactor tests.record.test_r2_static tests.record.test_r3_app_static tests.record.test_r3x_app_static tests.record.test_r3_skip_finalize tests.record.test_r3_sync_compensate tests.record.test_r3x_parallel_finalize tests.record.test_r3_finalize_guard tests.record.test_e2e_check tests.record.test_r2_e2e_check`；`$PY -m unittest tests.record.test_ms_prep -k test_finalize_set_state_uses_lock`；建置成功 | `test_ms_incremental_asr`、`test_ms_prep::test_prep_uses_stitched`、`test_ms_docs` 的 `test_readme_flow`、`test_meeting_pipeline_js_deprecated` |
| 第 3 層 | `$PY -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`$PY -m unittest discover -s tests/record -t . -k test_no_client_names`（不得 skipped）；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；`git diff --diff-filter=M --name-only 042c404..HEAD -- tests/ tools/MeetingRecorder/Tests/` 只列 `Tests/main.swift` 與 §6 已核准條目對應的測試檔；`python3 .claude/teams/tools/check_rules.py --git . 042c404..HEAD`；verify | 無；任何一支不綠就停下交人 |

每層合併後，主 session 另跑 §4 的重放量測，數字寫進 `progress.md`（不阻擋下一層，但第 2 層後 `stopToSpeakersMd > 300` 時依 spec §7 疑慮 1 停下回報）。

---

## 4. 不屬於任何子任務、需要主 session 或使用者做的事

- **閘門 2**：使用者核准 spec §6 第 1–17 條（被取代或修訂的 meeting-record 條文）與第 18–21 條（既有測試修改，第 19 條可與第 18 條分開、第 21 條單獨），以及 spec §4.11.9 的品質門檻數字；`save_run.py approve`。未核准的條目照 spec 寫的「不核准時」分支走，`red-py`、`diarize-iron`、`prep-pipeline` 的派工單要寫明決定結果。
- **每層量測**（spec §4.14.3）：保留段落的路徑由使用者在量測時提供（子 agent 不讀 `~/.meeting-harness/`）；主 session 跑 `tools/bench/replay.py <路徑> --speed 10`，把報告 JSON 的數字抄進 `progress.md`（報告本身不含路徑）。第 0 次（改之前的基準）在 Red 層合併後以 `--legacy` 跑。
- **最終驗收**（spec §4.14.4）：`--speed 1` 重放一次（約 2 小時，`run_in_background`）；`--compare-full` 一次算 spec §4.11.9 的兩個數字。
- **test 段實機**（使用者在場，spec §4.4.11、§4.11.10、§4.12.4）：覆蓋安裝新錄製器、改 harness 指向本 epic 版，每一步先問使用者、當下同意才做；錄一場 ≥ 30 分鐘（錄製中縮放視窗兩次），記下 `droppedFrames`、停止當下 worker 欠的窗數、`videoPath`、`stopToVideo`；檢查兩則通知文字不含場次名、視窗標題、路徑。結果寫 run 目錄，只寫 run 代號與數字。
- 推送與開 PR 一律等使用者當下同意；推送前掃名稱（只回報有／沒有）。

---

## 5. 測試對應（spec 條 → 子任務 → 測試）

| spec | 實作子任務 | 測試（red 子任務寫） |
|---|---|---|
| §4.1.1–§4.1.2 | 全部 | 既有 CLI 測試；`test_ms_prep::test_early_env_absent_unchanged` |
| §4.1.3、§4.1.5 | `ms-core` | `swift:testMSStatusFieldsOmittedWhenNil`、`testMSCanvasLockCodable`、`testMSOldStatusDecodes`；`test_ms_app_static::CoreStatic` |
| §4.2.1–§4.2.5、§4.2.11 | `finalize-fast` | `test_ms_audio_first` |
| §4.2.6–§4.2.7 | `prep-pipeline` | `test_ms_prep::test_early_*` |
| §4.2.8 | `recorder-capture`（`ms-core` 提供 `isAudioReadyLine`） | `swift:testMSIsAudioReadyLine`；`CaptureStatic::test_audio_ready_sets_status` |
| §4.2.9–§4.2.10 | `ms-core`、`trigger-ui` | `swift:testMSAutoPrepPick*`；`TriggerStatic::test_early_autoprep_env` |
| §4.3 | `finalize-fast` | `test_ms_audio_first::test_idempotent_mid_state`、`::test_ready_json_stale_rewritten`；`test_ms_video_copy::test_verify_failed_not_done`、`::test_old_finalize_json_is_done` |
| §4.4.1–§4.4.2 | `recorder-capture` | `CaptureStatic::test_canvas_lock_written`、`::test_no_resize_update_configuration`、`::test_next_segment_size_logged`、`::test_preserves_aspect_ratio` |
| §4.4.3–§4.4.10 | `finalize-fast` | `test_ms_video_copy` |
| §4.5 | `finalize-fast` | `test_ms_video_copy::test_publish_before_verify`、`::test_verify_*` |
| §4.6.1–§4.6.5、§4.6.8–§4.6.9 | `diarize-iron` | `test_ms_iron_rules` |
| §4.6.6 | `asr-robust` | `test_ms_asr_robust::test_raw_not_converted` 等 |
| §4.6.7 | `diarize-iron` | `test_ms_docs::test_speakers_skill_annotate`、`::test_summary_skill_no_session_embeddings` |
| §4.7 | `asr-robust` | `test_ms_asr_robust` |
| §4.8.1–§4.8.5 | `prep-pipeline` | `test_ms_prep` |
| §4.8.6–§4.8.7 | `ms-core`、`trigger-ui` | `swift:testMSPrepOutcome*`、`testMSPrepNotification`；`TriggerStatic::test_prep_outcome_read` |
| §4.8.8 | `diarize-iron`（條件式） | `test_ms_iron_rules::test_diarize_skips_16k_conversion` |
| §4.9 | `prep-pipeline`、`finalize-fast` | `test_ms_prep::test_state_*`、`::test_finalize_set_state_uses_lock`、`::test_status_reads_new_state` |
| §4.10.1–§4.10.2 | `ms-core`、`recorder-capture` | `swift:testMSAudioProbe*`、`testMSAudioDeviceFailedMessage`；`CaptureStatic::test_preflight_device_failed`、`::test_start_capture_error_logged` |
| §4.10.3 | `ms-core`、`trigger-ui`、`recorder-capture` | `swift:testMSStopPathLogLine`；`TriggerStatic::test_stop_paths_logged`；`CaptureStatic::test_preflight_returns_logged` |
| §4.11.1 | `ms-core`、`recorder-capture` | `swift:testMSAsrWorkerShouldStart`；`CaptureStatic::test_worker_started_after_first_segment` |
| §4.11.2–§4.11.7 | `incremental-asr` | `test_ms_incremental_asr` |
| §4.11.8 | `prep-pipeline`（呼叫端）＋`incremental-asr`（worker） | `test_ms_prep::test_prep_uses_stitched`、`::test_prep_falls_back_full` |
| §4.11.9、§4.14 | `replay-bench`；量測由主 session | `test_ms_replay` |
| §4.12.1–§4.12.3 | `ms-core`、`trigger-ui`、`recorder-capture` | `swift:testMSSessionCodeLabel`、`testMSPrepNotification`、`testMSCompletionNotificationBody`；`TriggerStatic::test_prep_notifications_no_name`、`::test_menubar_completion_body_no_session`；`CaptureStatic::test_completion_body_no_path` |
| §4.13.1–§4.13.3 | `trigger-ui`（MenuBar）、`recorder-capture`（RecordingSession、PreflightRunner）、`finalize-fast`（_record_finalize、record helper）、`record-sh-split`（cmd_control）、`asr-robust`（heredoc）、`diarize-iron`（harness_config） | `test_ms_refactor` |
| §4.13.4 | `docs-cleanup`、`asr-robust`（`transcribe.sh:3`）、`diarize-iron`（`_merge_speakers.py:3`）、`record-sh-split`（`record.sh:973`） | `test_ms_docs::test_readme_flow`、`::test_stale_comments_updated`、`::test_meeting_pipeline_js_deprecated` |
| §4.15.3 | `red-py` | `test_ms_docs::test_no_client_names_in_ms_files` |
| §4.4.11、§4.11.10、§4.12.4、§4.14.3–§4.14.4 | 主 session＋使用者 | 人工（§4） |

---

## 6. 拆 PR 規劃

修改的既有檔超過 15 個，建議拆兩包（主 session 在 deliver 段依實際 diff 決定，先問使用者）：

- **MS-1（CLI、Python、文件、specs）**：`bin/`、`tests/record/`、`tools/bench/`、`.claude/skills/`、`.claude/workflows/meeting-pipeline.js`、`README.md`、`config.json`、`.gitignore`、`specs/meeting-speed/`。
- **MS-2（app）**：`tools/MeetingRecorder/`（Core、Capture、Trigger、Tests）。
- 依賴：MS-2 的錄製器認 MS-1 `_record_finalize.py` 印的「音訊就緒：」行、起 MS-1 的 `_asr_worker.py`；兩包各自都能獨立運作（找不到這一行或 worker 檔就走舊流程），但要同時拿到速度收益必須兩包都合併。

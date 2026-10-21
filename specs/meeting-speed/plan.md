# plan：meeting-speed

- 上游：`intent.md`（閘門 1 已核准，§7 為準）、`design.md`、`spec.md`、`adr/`。
- 狀態：**修正輪 2 草稿，待閘門 2 核准**。使用者 2026-10-21 在閘門 2 前的決定已落進本檔：D1：spec §6 第 1–21 條核准；D2：G1 拆兩條線量；D3：事故 4 項修正併入；D4：每個子任務跑四件套；D5：不另開第 4 層、品質門檻核准；E1：spec §6 第 23 條確認；E2：§6 第 24 條確認、異常中止判定改用共享狀態檔的 pid；E3：四件套的兩個例外統稱「允許仍紅」（§2〈共通〉）；E4：拿掉早期模式、影片線外推值 > 240 秒補長錄、`paused_total` 以 `_record_finalize` 的算法為準。
- 子任務 id 是短名，**不是任務編號**；分支 `feature/meeting-speed--<id>`，各開 worktree，從當層開工時的 `feature/meeting-speed` 開。
- 起點：`_tpm/runs/20261021-sdlc-meeting-speed/plan-approved.md:35-107` 的 12 個子任務、4 層；調整理由見 `design.md` §1.1、§17。

---

## 1. 子任務與分層

| 層 | id | kind | owns（只能改這些） | depends_on | Story |
|---|---|---|---|---|---|
| Red | `red-py` | test | `tests/record/test_ms_*.py`（新）、`tests/record/fakes/asr_exc0/`（新）、`tests/record/fakes/pymod/`（新）、`tests/record/fakes/ms_*`（新）、`tests/record/vectors/ms-*.json`（新）、`tests/record/test_regression.py`（spec §6 第 18 條）、`tests/record/test_r3_vtt_raw.py`（第 20 條）、`tests/record/test_r3_lock.py`（第 21 條） | — | G1–G9 |
| Red | `red-swift` | test | `tools/MeetingRecorder/Tests/MSCoreTests.swift`（新）、`tools/MeetingRecorder/Tests/main.swift`（只加一列） | — | G1、G2、G5、G9 |
| 1 | `ms-core` | code | `tools/MeetingRecorder/Sources/Core/` | `red-swift` | G1、G2、G5、G9 |
| 1 | `asr-robust` | code | `bin/transcribe.sh`、`bin/lib/_transcript_quality.py`（新）、`.claude/skills/meeting-transcribe/` | `red-py` | G5、G6、G1、G8 |
| 1 | `diarize-iron` | code | `bin/diarize.sh`、`bin/_diarize_pyannote.py`、`bin/_merge_speakers.py`、`bin/_render.py`、`bin/_voiceprint.py`、`.claude/skills/meeting-speakers/`、`.claude/skills/meeting-summary/`、`.gitignore`、`config.json` | `red-py` | G6、G1、G2、G8 |
| 1 | `prep-pipeline` | code | `bin/meeting.sh`、`bin/lib/_record_lib.py` | `red-py` | G1、G5、G7、G8 |
| 1 | `record-sh-split` | code | `bin/record.sh` | `red-py` | G5、G8 |
| 1 | `video-spike` | check | `specs/meeting-speed/evidence/video-spike.md`（新） | — | G1、G3、G4 |
| 1 | `replay-bench` | code | `tools/bench/`（新） | `red-py` | G1、G4 |
| 2 | `finalize-fast` | code | `bin/_record_finalize.py`、`bin/lib/_finalize_*.py`（新）、`.claude/skills/meeting-record/` | `red-py`、`prep-pipeline`、`video-spike` | G1、G4、G5、G8、G9 |
| 2 | `recorder-capture` | code | `tools/MeetingRecorder/Sources/Capture/` | `red-py`、`ms-core`、`video-spike` | G1、G2、G5、G8、G9 |
| 2 | `trigger-ui` | code | `tools/MeetingRecorder/Sources/Trigger/` | `red-py`、`ms-core` | G1、G5、G8、G9 |
| 3 | `incremental-asr` | code | `bin/lib/_asr_worker.py`（新） | `finalize-fast`、`prep-pipeline`、`asr-robust`、`diarize-iron` | G2、G4、G1 |
| 3 | `docs-cleanup` | doc | `README.md`、`.claude/workflows/meeting-pipeline.js` | `finalize-fast`、`prep-pipeline` | G8 |

**檔案歸屬**：所有子任務的 owns 完全不重疊，跨層也不重疊；每支檔從頭到尾只有一個擁有者。會被多個需求碰的檔：`MenuBar.swift`＝`trigger-ui`（停止路徑 log、`.early` 觸發、通知、啟動時偵測異常中止、拆檔）；`RecordingSession.swift`＝`recorder-capture`（畫布鎖定、丟幀、起 worker、preflight 錯誤 log、完成通知、擷取幀率／尺寸、拆檔）；`_record_finalize.py`＝`finalize-fast`（音訊先出＋影片 copy＋驗證後移＋補尾幀數＋拆檔）；`meeting.sh`＝`prep-pipeline`（含 stitch 交棒的呼叫端，所以 `incremental-asr` 不必碰它，spec §3.9）；`record.sh`＝`record-sh-split`（`finish` 不帶參數接手＋拆 `cmd_control`）；`config.json`＝`diarize-iron`（spec §5 同）；`bin/lib/_record_lib.py`＝`prep-pipeline`（含 `paused_total` 改算法，spec §4.13.2）。`bin/_profile.py` 不屬任何子任務（`harness_config` 合一修正輪 2 移出本 epic，spec §4.13.2）。

**結構重構（G8）怎麼排（D5：不另開第 4 層）**：每支檔的擁有者在自己的速度／修正 commit 之後，另做一個 `refactor(meeting-speed)` commit（理由見 design §1.1、§13）。「速度先、重構後」在子任務內部成立；兩個子任務擁有同一支檔的情況不存在。

**事故修正（D3）怎麼排**：不新增子任務。(a) 補尾幀數 → `finalize-fast`；(b) 選單啟動偵測 → 判定 `ms-core`、偵測與通知 `trigger-ui`；(c) `finish` 不帶參數 → `record-sh-split`（從純重構變成 feat＋refactor，Story 加 G5）；(d) 擷取幀率／尺寸 → `video-spike` 多量一節、使用者決定後才派 `recorder-capture`（design §17）。

**數量**：15 個、Red＋3 層（計畫 12 個、4 層）。合併與新增的理由見 design §1.1；修正輪 1、2 都沒有增減子任務（修正輪 2 只調整 `diarize-iron` 的 owns 與完成條件、`prep-pipeline` 多兩支測試）。

---

## 2. 各子任務要點與完成條件（可機械判定）

### 共通

- 只改 `owns`；不改 `progress.md`；**不改任何既有測試與既有替身**（spec §6 第 18、20、21 條已核准，只由 `red-py` 改）；`bin/` 頂層檔數維持 26。
- commit 訊息 `test(meeting-speed)`／`feat(meeting-speed)`／`fix(meeting-speed)`／`refactor(meeting-speed)`／`docs(meeting-speed)`，內文寫 spec 節號，結尾署名行 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。
- 指令前綴（pyenv shim 會卡住，Python 一律用 `$PY`）：

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
export TMPDIR="$(mktemp -d)" LC_ALL=en_US.UTF-8
export MH_CLIENT_NAMES_FILE=/Users/yuktang/Documents/Agent/meeting-harness/_tpm/runs/20261010-sdlc-meeting-record/client-names.txt
BASE="$(git merge-base feature/meeting-speed HEAD)"
```

- **四件套（D4；spec §4.15.1）**：每個子任務完成時都要跑，有 refactor commit 的在 refactor commit 之後再跑一次。判準：
  1. `bash bin/_lint.sh && bash bin/meeting.sh doctor` 回 0。
  2. `/bin/bash tools/MeetingRecorder/Tests/run.sh` 回 0。
  3. `$PY -m unittest discover -s tests/record -t . > "$TMPDIR/full.log" 2>&1`；`grep -E '^(FAIL|ERROR): ' "$TMPDIR/full.log"` 沒有輸出；`grep -E 'ImportError|ModuleNotFoundError|SyntaxError|NameError' "$TMPDIR/full.log"` 沒有輸出。
  4. 名稱掃描：`git diff "$BASE" HEAD | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 與 `git log "$BASE"..HEAD --format=%B | grep -qiF -f "$MH_CLIENT_NAMES_FILE"` 都回 1；信封只寫「名稱掃描：沒有」，不得讀出或引用名單內容。
  - **允許仍紅（使用者 2026-10-21 核准，E3；與 spec §4.15.1 同一個詞）**：上面第 2、3 條的例外只有兩個，清單外任何紅燈一律失敗。
    - (i) **red-swift 階段**：`MSCoreTests.swift` 已在本分支或本層開工時的 `feature/meeting-speed`、`ms-core` 尚未合併時（Red 層的 `red-swift`；第 1 層 `ms-core` 以外的子任務），第 2 條可以編譯失敗，但 `run.sh` 輸出的每一行 `error:` 都只能是缺 spec §3.10 名稱（`cannot find '…' in scope`、`has no member`、缺 enum case）。`ms-core` 與第 2、3 層的子任務沒有這個例外。
    - (ii) **開工清單**：第 3 條 `FAIL:`／`ERROR:` 的每個測試 ID 都必須在 §3 本層「開工時允許仍紅」欄（Red 層的 `red-py` 與第 1 層用 R0、第 2 層用 R1、第 3 層用 R2）內，而且由本子任務以外的子任務（後續層或同層其他子任務）負責轉綠（`red-py` 自己寫的紅燈測試由實作子任務負責轉綠，算在內）；本子任務完成條件列的測試一律不得紅。`red-swift` 的分支沒有 `red-py` 的新測試，第 3 條必須 0 個。
- **重構共通**：refactor commit 的 `git diff --diff-filter=M --name-only <commit>~ <commit> -- tests/ tools/MeetingRecorder/Tests/` 為空；非改既有測試不可時，停下以 `needs_decision` 回報（spec §6 第 22 條），不得自行改測試。

### 各子任務

- **red-py**：(1) spec §4 驗法欄與 §5 列的 `tests/record/test_ms_*.py` 測試函式與類別都存在（逐字，`grep -n "def <名稱>\|class <名稱>"`）；(2) 替身：`fakes/asr_exc0/mlx_whisper`（例外時回 0、只寫 txt）、`fakes/pymod/mlx_whisper/__init__.py`（`transcribe()` 計數載入次數、依輸入回固定段落）、`fakes/ms_slow_ffmpeg.sh`（記錄呼叫順序、可讓影片或驗證步驟變慢或失敗）、`fakes/ms_count_ffprobe.sh`（計數）；(3) `git diff --diff-filter=M --name-only "$BASE" HEAD -- tests/` 恰為 `tests/record/test_regression.py`、`tests/record/test_r3_vtt_raw.py`、`tests/record/test_r3_lock.py`，且只動 spec §6 第 18、20、21 條列的斷言（commit 內文寫條號）；(4) `$PY -m unittest tests.record.test_ms_docs -k test_no_client_names_in_ms_files -v` 的輸出含 `ok`、不含 `skipped`；(5) `$PY -m unittest tests.record.test_ms_refactor -k test_paused_total_finalize_locked` 回 0（鎖定 `_record_finalize.paused_total` 現行行為，spec §4.13.2；E4(3)「先補鎖定該行為的測試」）；(6) 四件套：Swift `run.sh` 回 0（本子任務不碰 Swift），Python 紅燈 ⊆ R0（允許仍紅 (ii)）。
- **red-swift**：(1) `MSCoreTests.swift` 有 spec §4 列的全部 `swift:` 函式（逐字，含 §4.16.1、§4.16.2 的 `testMSAbnormalStop*`），陣列名 `mrtMSCoreTests`；(2) `git diff "$BASE" HEAD -- tools/MeetingRecorder/Tests/main.swift` 只多一列 `("MSCoreTests", mrtMSCoreTests),`；(3) 四件套：Swift `run.sh` 只因缺 spec §3.10 名稱而編譯失敗（允許仍紅 (i)）；Python 全量 0 個 `FAIL:`／`ERROR:`（本分支沒有 `red-py` 的新測試）。
- **ms-core**：(1) `/bin/bash tools/MeetingRecorder/Tests/run.sh` 回 0（既有 `TriggerTests`、`PreflightTests`、`RecordsTests`、`R3xBackgroundTests` 不改）；(2) spec §3.10 名稱與簽名逐字存在（含 `abnormalStopSession(status:pidAlive:sessionExists:)`、`abnormalStopNotification`；判定不讀 `record.pid`，E2）；(3) `$PY -m unittest tests.record.test_ms_app_static -k CoreStatic` 回 0；(4) `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 回 0（不改既有 `SystemAudioCheck`、`shouldAutoPrep` 的簽名，Capture／Trigger 未改也能編）；(5) 四件套。
- **asr-robust**：(1) `$PY -m unittest tests.record.test_ms_asr_robust tests.record.test_r3_transcript_vad tests.record.test_deliver_fixes tests.record.test_t7_fixes` 回 0；(2) `$PY -m unittest tests.record.test_r3_vtt_raw` 的 `FAIL:`／`ERROR:` 只能是 `test_diarize_keeps_raw`（它靠 `meeting.sh` 轉綠，歸 `prep-pipeline`）；(3) `$PY -m unittest tests.record.test_ms_docs -k test_stale_comment_transcribe -k test_transcribe_skill_raw_policy` 回 0；(4) refactor commit 後 `$PY -m unittest tests.record.test_ms_refactor -k test_transcribe_no_quality_heredoc` 回 0，(1)(2)(3) 仍成立；(5) 四件套。
- **diarize-iron**：(1) `$PY -m unittest tests.record.test_ms_iron_rules tests.record.test_review_fixes tests.record.test_r3_annotations` 回 0（含 `test_diarize_skips_16k_conversion`、`test_config_keys`；第 18、19 條已核准）；(2) `$PY -m unittest tests.record.test_r3_vtt_raw` 的 `FAIL:`／`ERROR:` 只能是 `test_diarize_keeps_raw`（skeptic 第 8 點：這支依賴 `meeting.sh`，`diarize-iron` 不負責）；(3) `$PY -m unittest tests.record.test_ms_docs -k test_speakers_skill_annotate -k test_summary_skill_no_session_embeddings -k test_stale_comment_merge_speakers` 回 0；(4) `harness_config` 不合一（修正輪 2 移出，spec §4.13.2），`bin/_voiceprint.py` 不得新增對 `bin/lib/` 或 `bin/` 其他模組的 import（既有 `test_review_fixes.py:96-101` 的 `copy_with_config` 只複製單支腳本，(1) 會擋）；本子任務沒有 refactor commit；(5) 不加 `MH_DIARIZE_AUDIO`（spec §3.7）；(6) 四件套。
- **prep-pipeline**：(1) `$PY -m unittest tests.record.test_ms_prep` 的 `FAIL:`／`ERROR:` 只能是 `test_finalize_set_state_uses_lock`（`finalize-fast`）與 `test_prep_uses_stitched`（`incremental-asr`）；(2) `$PY -m unittest tests.record.test_r3_vtt_raw tests.record.test_concurrency tests.record.test_r3_record_lib tests.record.test_surface_parsers tests.record.test_cli_dispatch tests.record.test_regression` 回 0（含照第 20 條改過的 `test_diarize_keeps_raw`）；(3) `$PY -c "import sys; sys.path.insert(0, 'bin/lib'); import _record_lib as m; [getattr(m, n) for n in ('load_json', 'write_json_atomic', 'record_home', 'paused_total', 'update_pipeline_state')]"` 回 0；(4) `$PY -m unittest tests.record.test_ms_refactor -k test_paused_total_finalize_locked -k test_paused_total_record_lib_matches_finalize` 回 0（`_record_lib.paused_total` 改成 `_record_finalize` 的算法，`pause_pairs`、`output_time` 不動；spec §4.13.2，E4(3)），`$PY -m unittest tests.record.test_r3_record_lib` 仍回 0；`test_record_helpers_single_definition` 不在本子任務要求（`finalize-fast` 改 import 後才綠）；(5) 四件套。
- **record-sh-split**：(1) feat commit 後 `$PY -m unittest tests.record.test_ms_record_finish` 回 0（含 `test_no_arg_after_stop_removed_pid_file`：判定只讀 `record.status.json`，不依賴 `record.pid`，spec §4.16.3，E2）；(2) `$PY -m unittest tests.record.test_record_sh tests.record.test_r2_cli tests.record.test_r3_lock tests.record.test_r3x_background tests.record.test_surface_parsers tests.record.test_cli_dispatch tests.record.test_docs` 回 0（`cmd_stop` 不動、usage 不改）；(3) refactor commit 後 `$PY -m unittest tests.record.test_ms_refactor -k test_cmd_control_length` 與 `$PY -m unittest tests.record.test_ms_docs -k test_stale_comment_record_sh` 回 0，(1)(2) 仍成立；(4) `git log "$BASE"..HEAD --format=%s` 恰有一個 `feat(meeting-speed)` 與一個 `refactor(meeting-speed)`；(5) 四件套。
- **video-spike**：`specs/meeting-speed/evidence/video-spike.md` 存在，含下列五節，每節有可重跑的指令與實測數字（或明寫「待使用者在場實測」＋指令）：(1) macOS SDK 的 `SCStreamConfiguration.preservesAspectRatio` 宣告與可用版本（`grep` SDK 標頭，附路徑:行號）；(2) 以 `tests/record/_media.py` 同款的 SCK 特性合成段落（VFR、`time_base=1/600`、同尺寸、同 extradata）跑 copy remux＋concat，spec §4.4.5 的判準逐項 PASS／FAIL；(3) 2 小時 PCM 上 `aac` 與 `aac_at` 的編碼耗時；(4) **WindowServer 負擔（D3 d，spec §4.4.13）**：「60 fps 原尺寸」「30 fps 原尺寸」「60 fps＋尺寸上限」三種擷取設定下，`ps -o %cpu= -p "$(pgrep -x WindowServer)"` 每秒取樣 120 秒的平均與 p95，以及各設定錄出的段落走 (2) 的 copy 串接是否 PASS——要跑錄製器時只能由主 session 在使用者當下同意後執行，agent 不自行啟動已安裝的錄製器；(5) 結論：copy「可行／不可行」，以及 (4) 的數字與建議（建議不是決定）。信封 `status` 一律 `needs_decision`（擷取幀率／尺寸由使用者決定）；copy 不可行時 `finalize-fast`、`recorder-capture` 都不得開工。不得讀 `~/.meeting-harness/`；文件不寫路徑、場次名、視窗標題。四件套照跑（本子任務只新增一份文件）。
- **replay-bench**：(1) `$PY -m unittest tests.record.test_ms_replay` 回 0；(2) `$PY tools/bench/replay.py --help` 回 0；(3) 報告鍵與 spec §3.12 相同（由 `test_ms_replay.py::test_report_keys` 判）；(4) 四件套。
- **finalize-fast**：開工前提：`video-spike` 結論 copy「可行」。(1) `$PY -m unittest tests.record.test_ms_audio_first tests.record.test_ms_video_copy tests.record.test_finalize tests.record.test_r2_finalize tests.record.test_r3_finalize_guard tests.record.test_r3_sync_compensate tests.record.test_r3x_parallel_finalize tests.record.test_concurrency tests.record.test_static_rules tests.record.test_review_fixes tests.record.test_e2e_check tests.record.test_r2_e2e_check` 回 0（含 `test_tail_pad_low_r_frame_rate`，D3 a）；(2) `$PY -m unittest tests.record.test_ms_prep -k test_finalize_set_state_uses_lock` 回 0；(3) `$PY -m unittest tests.record.test_ms_docs -k test_record_skill_speed_notes -k test_record_skill_finish_no_arg` 回 0；(4) `$PY -c "import ast; t = ast.parse(open('bin/_record_finalize.py', encoding='utf-8').read()); assert any(isinstance(n, ast.FunctionDef) and n.name == 'segment_audio_pcm' for n in t.body); assert any(isinstance(n, ast.Assign) and any(getattr(x, 'id', '') == 'TAIL_PAD_FPS_FLOOR' for x in n.targets) for n in t.body)"` 回 0；(5) refactor commit（拆到 `bin/lib/_finalize_*.py`，被 `test_r3x_parallel_finalize.py` 讀寫的模組全域與靜態測試釘住的名稱留在原模組）後 `$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_record_finalize -k test_record_helpers_single_definition -k test_paused_total_finalize_locked -k test_paused_total_record_lib_matches_finalize` 回 0（`paused_total` 改由 `_record_lib` import，輸出不變），(1)–(4) 仍成立；(6) 四件套。
- **recorder-capture**：開工前提：`video-spike` 結論 copy「可行」，且使用者已對 spec §4.4.13（擷取幀率／尺寸）做決定並由主 session 寫回 spec。(1) `$PY -m unittest tests.record.test_ms_app_static -k CaptureStatic` 回 0；(2) 既有 `test_r3_app_static`、`test_r3x_app_static`、`test_r3_skip_finalize`、`test_r2_static`、`test_static_rules`、`test_t7_fixes` 回 0（不改）；(3) refactor commit（以 `extension` 拆到 `Capture/RecordingSession+*.swift`、`Capture/PreflightChecks.swift`）後 `$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_recording_session -k test_preflight_run_length` 回 0，(1)(2) 仍成立；(4) `MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh` 回 0；(5) 四件套（`run.sh` 必須回 0）。
- **trigger-ui**：(1) `$PY -m unittest tests.record.test_ms_app_static -k TriggerStatic` 回 0（含 `test_abnormal_stop_checked_on_launch`——啟動偵測讀 `record.status.json`、`kill(status.pid, 0)`、不讀 `record.pid`，E2——、`test_abnormal_stop_notification_no_name`、`test_autoprep_run_id_env`，D3 b）；(2) 既有 `test_r3_app_static`、`test_r3x_app_static`、`test_r2_static`、`test_t7_fixes`、`test_static_rules` 回 0（不改）；(3) refactor commit（拆出 `Trigger/MenuBar+*.swift`）後 `$PY -m unittest tests.record.test_ms_refactor -k test_line_limit_menubar` 回 0，(1)(2) 仍成立；(4) 建置回 0；(5) 四件套（`run.sh` 必須回 0）。
- **incremental-asr**：(1) `$PY -m unittest tests.record.test_ms_incremental_asr tests.record.test_ms_prep tests.record.test_r3_record_lib` 回 0；(2) `$PY bin/lib/_asr_worker.py --help` 回 0；(3) 四件套。
- **docs-cleanup**：(1) `$PY -m unittest tests.record.test_ms_docs -k test_readme_flow -k test_meeting_pipeline_js_deprecated` 回 0；(2) `$PY -m unittest tests.record.test_docs tests.record.test_r2_docs tests.record.test_r3_docs tests.record.test_r3x_docs` 回 0（不改）；(3) 四件套。

---

## 3. 每層的仍紅清單與整合指令（一律加 §2 的前綴）

「開工時允許仍紅」＝本層子任務的 worktree 開工時（上一層已合併）的允許仍紅清單；子任務完成時，全量的 `FAIL:`／`ERROR:` 只能落在這一欄、且由本子任務以外的子任務負責（§2〈共通〉允許仍紅 (ii)）。「合併後允許仍紅」＝本層全部合併後仍允許失敗的測試，也就是下一層的「開工時允許仍紅」。Swift 編譯失敗只在 red-swift 階段允許（§2〈共通〉允許仍紅 (i)）。兩欄與 spec §4.15.1 用同一個詞。

| 層 | 開工時允許仍紅 | 合併後必須回 0 的指令 | 合併後允許仍紅 |
|---|---|---|---|
| Red | 無（Python 全量、Swift `run.sh` 都綠） | `bash bin/_lint.sh && bash bin/meeting.sh doctor`；`$PY -m unittest tests.record.test_finalize tests.record.test_r2_finalize tests.record.test_surface_parsers tests.record.test_cli_dispatch tests.record.test_docs tests.record.test_record_sh tests.record.test_r2_cli tests.record.test_concurrency tests.record.test_static_rules tests.record.test_regression tests.record.test_r3_lock`；`$PY -m unittest tests.record.test_ms_docs -k test_no_client_names_in_ms_files`；`$PY -m unittest tests.record.test_ms_refactor -k test_paused_total_finalize_locked` | **R0**：`tests.record.test_ms_*` 全部（`test_ms_docs.test_no_client_names_in_ms_files` 與 `test_ms_refactor.test_paused_total_finalize_locked` 除外）；`tests.record.test_r3_vtt_raw` 的 `test_diarize_keeps_raw`；Swift 編譯失敗（缺 spec §3.10 名稱） |
| 第 1 層 | R0 | 上一列全部；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；`$PY -m unittest tests.record.test_ms_asr_robust tests.record.test_ms_iron_rules tests.record.test_ms_replay tests.record.test_ms_record_finish tests.record.test_r3_vtt_raw tests.record.test_r3_transcript_vad tests.record.test_deliver_fixes tests.record.test_t7_fixes tests.record.test_review_fixes tests.record.test_r3_annotations tests.record.test_r3_record_lib tests.record.test_r3x_background`；`$PY -m unittest tests.record.test_ms_app_static -k CoreStatic`；`$PY -m unittest tests.record.test_ms_refactor -k test_transcribe_no_quality_heredoc -k test_cmd_control_length -k test_paused_total_finalize_locked -k test_paused_total_record_lib_matches_finalize`；`$PY -m unittest tests.record.test_ms_docs -k test_stale_comment_transcribe -k test_stale_comment_merge_speakers -k test_stale_comment_record_sh -k test_transcribe_skill_raw_policy -k test_speakers_skill_annotate -k test_summary_skill_no_session_embeddings`；`video-spike` 結論 copy「可行」 | **R1**：`test_ms_audio_first`、`test_ms_video_copy`、`test_ms_incremental_asr` 全部；`test_ms_app_static` 的 `CaptureStatic`、`TriggerStatic`；`test_ms_refactor` 的 `test_record_helpers_single_definition`、`test_line_limit_record_finalize`、`test_line_limit_recording_session`、`test_preflight_run_length`、`test_line_limit_menubar`；`test_ms_prep` 的 `test_finalize_set_state_uses_lock`、`test_prep_uses_stitched`；`test_ms_docs` 的 `test_record_skill_speed_notes`、`test_record_skill_finish_no_arg`、`test_readme_flow`、`test_meeting_pipeline_js_deprecated` |
| 第 2 層 | R1 | 上一層全部；`$PY -m unittest tests.record.test_ms_audio_first tests.record.test_ms_video_copy tests.record.test_ms_app_static tests.record.test_ms_refactor tests.record.test_r2_static tests.record.test_r3_app_static tests.record.test_r3x_app_static tests.record.test_r3_skip_finalize tests.record.test_r3_sync_compensate tests.record.test_r3x_parallel_finalize tests.record.test_r3_finalize_guard tests.record.test_e2e_check tests.record.test_r2_e2e_check`；`$PY -m unittest tests.record.test_ms_prep -k test_finalize_set_state_uses_lock`；`$PY -m unittest tests.record.test_ms_docs -k test_record_skill_speed_notes -k test_record_skill_finish_no_arg`；建置回 0 | **R2**：`test_ms_incremental_asr` 全部；`test_ms_prep.test_prep_uses_stitched`；`test_ms_docs` 的 `test_readme_flow`、`test_meeting_pipeline_js_deprecated` |
| 第 3 層 | R2 | `$PY -m unittest discover -s tests/record -t .`；`/bin/bash tools/MeetingRecorder/Tests/run.sh`；`$PY -m unittest tests.record.test_ms_docs -k test_no_client_names -v`（不得 skipped）；`MH_RECORDER_DEST=$(mktemp -d) bash tools/MeetingRecorder/build.sh`；`git diff --diff-filter=M --name-only 042c404..HEAD -- tests/ tools/MeetingRecorder/Tests/` 恰為 `tests/record/test_regression.py`、`tests/record/test_r3_vtt_raw.py`、`tests/record/test_r3_lock.py`、`tools/MeetingRecorder/Tests/main.swift`；`python3 .claude/teams/tools/check_rules.py --git . 042c404..HEAD`；verify | 無；任何一支不綠就停下交人 |

每層合併後，主 session 另跑 §4 的重放量測（逐字稿線），數字寫進 `progress.md`（不阻擋下一層；第 2 層後 `stopToSpeakersMd > 300` 時依 spec §7 疑慮 1 停下回報）。

---

## 4. 不屬於任何子任務、需要主 session 或使用者做的事

- **閘門 2**：D1–D5、E1–E4 已在閘門 2 前決定（spec §6 第 23、24 條、拿掉早期模式、外推門檻 > 240 秒都已確認）；閘門 2 只剩整份 design／spec／plan 的核准，另請使用者看 spec §7 疑慮 15（異常中止通知在收尾後可能重複，要不要加「段落還在」條件）。`save_run.py approve`。
- **擷取幀率／尺寸決定（D3 d）**：`video-spike` 回 `needs_decision` 後，主 session 把第 4、5 節的數字與建議推給使用者，用選項式提問（維持 60 fps／改 30 fps／加尺寸上限）；第 4 節若要跑已安裝的錄製器，每一次啟動都先問使用者、當下同意才做。決定非 60 fps 或加尺寸上限時，先修 spec §4.4.2、§6.1（記為 intent §7 Q3 的修訂）與 `test_ms_app_static.CaptureStatic` 對應斷言（由 `red-py` 補一個 commit），再派 `recorder-capture`。
- **每層量測（逐字稿線，spec §4.14.3）**：保留段落的路徑由使用者在量測時提供（子 agent 不讀 `~/.meeting-harness/`）；主 session 跑 `tools/bench/replay.py <路徑> --speed 10`，把報告 JSON 的數字抄進 `progress.md`（報告本身不含路徑）。第 0 次（改之前的基準）在 Red 層合併後以 `--legacy` 跑。
- **最終驗收（spec §4.14.4，D2 核准的量法）**：(i) 逐字稿線：`--speed 1` 重放 2026-10-20 的 121 段一次（約 2 小時，`run_in_background`），判 `stopToSpeakersMd`、`stopToWav`；`--compare-full` 一次算 spec §4.11.9 的兩個數字。(ii) 影片線：test 段的新錄製器實錄量 `stopToVideo`，依段數外推到 121 段；外推值 > 240 秒時再請使用者補錄一場 ≥ 2 小時的會議（E4(2)）。
- **test 段實機**（使用者在場，spec §4.4.11、§4.11.10、§4.12.4）：覆蓋安裝新錄製器、改 harness 指向本 epic 版，每一步先問使用者、當下同意才做；錄一場 ≥ 30 分鐘（錄製中縮放視窗兩次），記下 `droppedFrames`、停止當下 worker 欠的窗數、`videoPath`、`stopToVideo`（影片線的實錄數字就從這一場取）；檢查兩則通知文字不含場次名、視窗標題、路徑。結果寫 run 目錄，只寫 run 代號與數字。
- 推送與開 PR 一律等使用者當下同意；推送前掃名稱（只回報有／沒有）。

---

## 5. 測試對應（spec 條 → 子任務 → 測試）

| spec | 實作子任務 | 測試（red 子任務寫） |
|---|---|---|
| §4.1.1–§4.1.2 | 全部 | 既有 CLI 測試；`test_ms_prep::test_env_absent_unchanged` |
| §4.1.3、§4.1.5 | `ms-core` | `swift:testMSStatusFieldsOmittedWhenNil`、`testMSCanvasLockCodable`、`testMSOldStatusDecodes`；`test_ms_app_static::CoreStatic` |
| §4.2.1–§4.2.5 | `finalize-fast` | `test_ms_audio_first`（`test_wav_published_before_video`、`test_ready_json_fields`、`test_finalize_json_before_wav`、`test_compensated_wav`、`test_video_failure_keeps_wav`） |
| §4.2.6 | `prep-pipeline` | `test_ms_prep::test_prep_while_video_finalizing` |
| §4.2.8 | `recorder-capture`（`ms-core` 提供 `isAudioReadyLine`） | `swift:testMSIsAudioReadyLine`；`CaptureStatic::test_audio_ready_sets_status` |
| §4.2.9–§4.2.10 | `ms-core`、`trigger-ui` | `swift:testMSAutoPrepPick*`；`TriggerStatic::test_autoprep_run_id_env` |
| §4.3 | `finalize-fast` | `test_ms_audio_first::test_idempotent_mid_state`、`::test_ready_json_stale_rewritten`；`test_ms_video_copy::test_verify_failed_not_done`、`::test_old_finalize_json_is_done` |
| §4.4.1–§4.4.2 | `recorder-capture` | `CaptureStatic::test_canvas_lock_written`、`::test_no_resize_update_configuration`、`::test_next_segment_size_logged`、`::test_preserves_aspect_ratio` |
| §4.4.3–§4.4.10、§4.4.12 | `finalize-fast` | `test_ms_video_copy`（含 `test_tail_pad_low_r_frame_rate`） |
| §4.4.13 | `video-spike`＋使用者決定 | 證據檔第 4、5 節 |
| §4.5.1–§4.5.5 | `finalize-fast` | `test_ms_video_copy::test_publish_before_verify`、`::test_verify_*` |
| §4.5.6 | `finalize-fast` | `test_ms_docs::test_record_skill_speed_notes` |
| §4.6.1–§4.6.5、§4.6.8–§4.6.10 | `diarize-iron` | `test_ms_iron_rules` |
| §4.6.6 | `asr-robust` | `test_ms_asr_robust::test_raw_not_converted` 等；`test_ms_docs::test_transcribe_skill_raw_policy` |
| §4.6.7 | `diarize-iron` | `test_ms_docs::test_speakers_skill_annotate`、`::test_summary_skill_no_session_embeddings` |
| §4.7 | `asr-robust` | `test_ms_asr_robust` |
| §4.8.1–§4.8.5 | `prep-pipeline` | `test_ms_prep`；修改後的 `test_r3_vtt_raw::test_diarize_keeps_raw`（第 20 條） |
| §4.8.6–§4.8.7 | `ms-core`、`trigger-ui` | `swift:testMSPrepOutcome*`、`testMSPrepNotification`；`TriggerStatic::test_prep_outcome_read` |
| §4.8.8 | `diarize-iron` | `test_ms_iron_rules::test_diarize_skips_16k_conversion` |
| §4.9 | `prep-pipeline`、`finalize-fast` | `test_ms_prep::test_state_*`、`::test_finalize_set_state_uses_lock`、`::test_status_reads_new_state` |
| §4.10.1–§4.10.2 | `ms-core`、`recorder-capture` | `swift:testMSAudioProbe*`、`testMSAudioDeviceFailedMessage`；`CaptureStatic::test_preflight_device_failed`、`::test_start_capture_error_logged` |
| §4.10.3 | `ms-core`、`trigger-ui`、`recorder-capture` | `swift:testMSStopPathLogLine`；`TriggerStatic::test_stop_paths_logged`；`CaptureStatic::test_preflight_returns_logged` |
| §4.11.1 | `ms-core`、`recorder-capture` | `swift:testMSAsrWorkerShouldStart`；`CaptureStatic::test_worker_started_after_first_segment` |
| §4.11.2–§4.11.7 | `incremental-asr` | `test_ms_incremental_asr` |
| §4.11.8 | `prep-pipeline`（呼叫端）＋`incremental-asr`（worker） | `test_ms_prep::test_prep_uses_stitched`、`::test_prep_falls_back_full` |
| §4.11.9、§4.14 | `replay-bench`；量測由主 session | `test_ms_replay` |
| §4.12.1–§4.12.3 | `ms-core`、`trigger-ui`、`recorder-capture` | `swift:testMSSessionCodeLabel`、`testMSPrepNotification`、`testMSCompletionNotificationBody`；`TriggerStatic::test_prep_notifications_no_name`、`::test_menubar_completion_body_no_session`；`CaptureStatic::test_completion_body_no_path` |
| §4.13.1–§4.13.3 | `trigger-ui`（MenuBar）、`recorder-capture`（RecordingSession、PreflightRunner）、`finalize-fast`（_record_finalize、record helper）、`prep-pipeline`（`_record_lib.paused_total` 改算法）、`record-sh-split`（cmd_control）、`asr-robust`（heredoc）；`harness_config` 合一移出本 epic | `test_ms_refactor`（`test_paused_total_finalize_locked` 由 `red-py` 在 Red 層就綠） |
| §4.13.4 | `docs-cleanup`（README、meeting-pipeline.js）、`asr-robust`（`transcribe.sh:3`）、`diarize-iron`（`_merge_speakers.py:3`）、`record-sh-split`（`record.sh:973`） | `test_ms_docs::test_readme_flow`、`::test_meeting_pipeline_js_deprecated`、`::test_stale_comment_transcribe`、`::test_stale_comment_merge_speakers`、`::test_stale_comment_record_sh` |
| §4.15.1 | 全部 | §2 共通的四件套 |
| §4.15.3 | `red-py` | `test_ms_docs::test_no_client_names_in_ms_files` |
| §4.16.1 | `ms-core` | `swift:testMSAbnormalStopDetected`、`::NotWhenAlive`、`::NotWhenOtherPhase`、`::NotWhenSessionMissing`、`::NotWhenNoStatus` |
| §4.16.2 | `ms-core`（通知字面）、`trigger-ui`（啟動偵測、動作） | `swift:testMSAbnormalStopNotification`；`TriggerStatic::test_abnormal_stop_checked_on_launch`、`::test_abnormal_stop_notification_no_name` |
| §4.16.3 | `record-sh-split` | `test_ms_record_finish`（含 `test_no_arg_after_stop_removed_pid_file`、`test_no_arg_session_missing_exit2`） |
| §4.16.4 | `finalize-fast`（SKILL）、`record-sh-split`（usage 不改） | `test_ms_docs::test_record_skill_finish_no_arg`；既有 `test_docs`、`test_surface_parsers` |
| §4.4.11、§4.11.10、§4.12.4、§4.14.3–§4.14.4 | 主 session＋使用者 | 人工（§4） |

---

## 6. 拆 PR 規劃（修改的既有檔約 33 個，超過 15 個）

修改的既有檔估計：`bin/` 10 支（`_record_finalize.py`、`meeting.sh`、`lib/_record_lib.py`、`transcribe.sh`、`diarize.sh`、`_diarize_pyannote.py`、`_merge_speakers.py`、`_render.py`、`_voiceprint.py`、`record.sh`；修正輪 2 起 `_profile.py` 不改）、`config.json`、`.gitignore`、`README.md`、`.claude/workflows/meeting-pipeline.js`、SKILL 4 份、既有測試 3 支、Swift 約 12 支（Core 4、Capture 3、Trigger 4、`Tests/main.swift`）。建議拆三包（MS-1 15 支、MS-2 6 支、MS-3 約 12 支）；依序合併，前一包合併後才開下一包（主 session 在 deliver 段依實際 diff 決定，先問使用者）：

| 包 | 內容（修改的既有檔） | 子任務 | 新檔 | 依賴 |
|---|---|---|---|---|
| MS-1 前處理與鐵則 | `bin/transcribe.sh`、`bin/diarize.sh`、`bin/_diarize_pyannote.py`、`bin/_merge_speakers.py`、`bin/_render.py`、`bin/_voiceprint.py`、`bin/meeting.sh`、`bin/lib/_record_lib.py`、`config.json`、`.gitignore`、`.claude/skills/meeting-transcribe/SKILL.md`、`meeting-speakers/SKILL.md`、`meeting-summary/SKILL.md`、`tests/record/test_regression.py`、`tests/record/test_r3_vtt_raw.py`（15 支；其中 2 支既有測試只改 spec §6 第 18、20 條的斷言，必須和 `diarize.sh`、`meeting.sh` 的改動同包，所以不再細拆） | `asr-robust`、`diarize-iron`、`prep-pipeline` | `bin/lib/_transcript_quality.py`；`test_ms_asr_robust.py`、`test_ms_iron_rules.py`、替身 | — |
| MS-2 收尾、CLI、量測、文件 | `bin/_record_finalize.py`、`bin/record.sh`、`.claude/skills/meeting-record/SKILL.md`、`tests/record/test_r3_lock.py`、`README.md`、`.claude/workflows/meeting-pipeline.js` | `finalize-fast`、`record-sh-split`、`replay-bench`、`incremental-asr`、`docs-cleanup` | `bin/lib/_finalize_*.py`、`bin/lib/_asr_worker.py`、`tools/bench/`；`test_ms_audio_first.py`、`test_ms_video_copy.py`、`test_ms_prep.py`、`test_ms_incremental_asr.py`、`test_ms_replay.py`、`test_ms_record_finish.py`、`test_ms_docs.py`；`specs/meeting-speed/` | MS-1（`_record_lib` 的共用 helper 與加鎖寫入） |
| MS-3 app | `tools/MeetingRecorder/Sources/Core/`、`Capture/`、`Trigger/` 約 11 支、`Tests/main.swift` | `ms-core`、`recorder-capture`、`trigger-ui` | `Tests/MSCoreTests.swift`、拆出的 `extension` 檔；`test_ms_app_static.py`、`test_ms_refactor.py` | MS-2（錄製器認 `_record_finalize.py` 印的「音訊就緒：」、起 `_asr_worker.py`；找不到這一行或 worker 檔就走舊流程，所以 MS-3 晚合併不會壞） |

橫跨多包的新測試檔放在「讓它全綠的最後一包」：`test_ms_prep.py`、`test_ms_docs.py` 放 MS-2；`test_ms_app_static.py`、`test_ms_refactor.py` 放 MS-3。速度收益要三包都合併才完整。

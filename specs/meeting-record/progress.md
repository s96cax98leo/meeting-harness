# progress：meeting-record

從 `plan.md` 拆出。**本檔由主 session 維護**（每層合併、每個閘門之後更新），不屬於任何子任務的 owns；子任務不要改本檔（`plan.md` 開頭）。

## Design
- [x] design.md、spec.md、plan.md、progress.md、adr/ 三則
- [x] 修正輪：依 D6–D12 與 skeptic 14 條修正（對照表在 run 目錄 `design-revise-對照.md`）
- [x] 第二修正輪：skeptic 5 條（run.sh 的 bash 3.2、麥克風 entitlement、menu bar `preflight_failed` 對映、`test_no_default_device_write` 拆分、progress.md 與 `7c9a3a0`）
- [x] 第三修正輪：D13 文件先寫（t5 移到第 1 層、t3／t4 依賴 t5、spec §2.4 封閉清單與 §4.12.6–4.12.9 一致性驗收、拆 PR 重排）、D14 告警停到下次開錄（維持）
- [x] 第四修正輪：skeptic 2 條（CLI 表面統一成 spec §2.4.1–2.4.8 單一定義：層旗標獨立、通則結束碼 2、help／`usage()`／文件區塊的文法與解析規則、`surface.py`；§1 與 §4.1.2 改成七種寫法、`test_help_lists_record_forms`）
- [x] 第五修正輪：skeptic 1 條（層旗標在 `record` 之後任何位置都拿掉；未知選項在 spec §2.2、§2.4.2、design §8.1 用同一句定義；新增中間／結尾兩支測試）
- [x] 閘門 2 使用者核准（`bcec2a2`，2026-10-11）——build 前發現漏項（D15），核准版本需重新核准
- [x] 第六修正輪：D15（視窗清單認不出會議視窗、移除「標題非空」、視窗認回、`diagnose-windows`）、D16（Apple Events 唯讀讀 Chrome 分頁網址標「★ 會議（<服務名>）」、entitlements 改兩項、preflight 第 13 項 warn）＋skeptic 2 條；spec 新增 §3.8、§4.12.10、§4.15、§6 第 32–38 條；新增 `adr/adr-meeting-window-marking.md`
- [x] 第七修正輪：skeptic 2 條（第六輪寫進 specs 的真實會議名稱換成中性範例「[Stand-up] 範例專案」、新增 spec §4.14.3 客戶名稱靜態檢查與 §4.15 前言的中性範例規定、plan §5.1 推送前必辦；§4.1.12 替身參數改為「層旗標不在＋子序列＋§3.5 必帶參數存在」）；spec §6 第 39、40 條、§7 疑慮 19
- [x] 閘門 2（第七修正輪版本）使用者再核准（`c280755`，2026-10-11）
- [x] 主 session 建立 run 目錄 `client-names.txt`（spec §4.14.3；build 前）

## Build（2026-10-11 完成，整合分支 HEAD `082dacb`）
- Red：t1 `ca9871f`、t2 `6b14908` → 合併 `9844c05`；第 1 層：t5 `c27ca67` → `82bd2ce`；第 2 層：t3 `4f61a4c`、t4 `a52e122` → `082dacb`
- 主 session 在整合分支重跑：lint 26 檔通過、doctor 回 0、Python 94 支 OK（含名稱檢查，未 skip）、Swift 38 支失敗 0、`check_rules.py --git` 通過、`diarize.sh`／`_merge_speakers.py` 無差異
- 名稱掃描：build 新增的 commit 0 命中；既有命中（main 帶來的 2 處檔案、spec 修訂輪 4 個 commit）照 plan §5.1 推送前處理

分層：Red（t1＋t2）→ 第 1 層 t5 → 第 2 層 t3＋t4 →（test 段）t6；每層整合後的測試指令見 `plan.md §3`

## t1 tests/record/（test）
- [x] `surface.py`＋`test_surface_parsers.py`（spec §2.4.8；`SURFACE` 與四個解析／組參數函式，自我測試紅燈階段就綠）
- [x] `test_cli_dispatch.py`（§4.1.1–4.1.3、4.1.10–4.1.12，含 `./record` 撞名與 pty 互動、`test_help_lists_record_forms`、`record help`、未知選項、`--recorder`／`--yes` 拿掉，含中間／結尾位置的 `test_layer_flag_mid_position_stripped`、`test_layer_flag_trailing_position_stripped`）
- [x] `test_record_sh.py`＋`fakes/fake_open.sh`（§4.1.4、4.1.6、4.1.7、4.2.3、4.2.4、4.5.5、4.5.6；模組層常數 `EXIT_CODE_CASES` 照 §2.4.7，恰等於 `SURFACE.form_codes` 的 22 組）
- [x] `test_prompt.py`、`test_estimate.py`（§4.1.8、4.1.9）
- [x] `test_finalize.py`（§4.6.1–4.6.12、4.8.2、4.13.3）
- [x] `test_concurrency.py`＋`fakes/slow_ffmpeg.sh`（§4.4.2、4.7）
- [x] `test_regression.py`（§4.12.4、4.13.1、4.13.2、4.13.7）
- [x] `test_static_rules.py`（§4.1.5、4.2.8（`test_entitlements_audio_and_apple_events`、`test_info_plist_apple_events_usage`）、4.9.4 拆成 `_in_sources`／`_in_record_sh`、4.11.3、4.11.5、4.11.8、4.14、4.15.10 `test_chrome_query_read_only`）
- [x] `test_docs.py`（§4.8.3、4.11.4、4.12.1–4.12.3、4.12.6–4.12.10；11 支函式（含 `test_meeting_tab_marking_documented`），`SURFACE` 與解析器 import 自 `surface.py`）
- [x] 第六修正輪：`test_prompt.py` 視窗選單 3 支、`test_record_sh.py` 的 `--ask-automation`／認回參數 2 支、`test_regression.py::test_doctor_mentions_meeting_tab_marking`、`fake_open.sh` 的 `windows` 情境（§4.15.12–4.15.14）
- [x] 第七修正輪：`test_static_rules.py::test_no_client_names_in_repo_text`（§4.14.3，帶 `MH_CLIENT_NAMES_FILE` 紅燈階段即綠）；`test_layer_flag_mid_position_stripped`／`_trailing_` 改用 §4.1.12 (i)–(iii)；`fake_open.sh` 逐次記錄 `argv[1:]`；測試範例標題一律中性
- [x] `e2e_check.py`＋`test_e2e_check.py`（自我測試綠）
- [x] 紅燈確認：失敗原因是「功能不存在」而非測試本身錯誤

## t2 tools/MeetingRecorder/Tests/（test）
- [x] `run.sh`（cd＋nullglob＋`${core[@]+"${core[@]}"}`，在 `/bin/bash` 3.2 下可跑）、`main.swift` 執行器
- [x] `AudioLevelTests.swift`（§4.2.5、4.2.7、4.5.7、4.5.8）
- [x] `DetectorsTests.swift`（§4.5.1–4.5.3、4.5.8）
- [x] `PreflightTests.swift`（§4.2.1 `testPreflightItemsAndSeverity` 13 項、4.2.2）
- [x] `WindowListTests.swift`（§4.15.1–4.15.9，12 支；範例標題一律中性，M+ 列用「[Stand-up] 範例專案」）
- [x] `RecordsTests.swift`（§3.1–3.3 鍵名、§4.5.4）
- [x] `SegmentsTests.swift`（§4.3.2、4.4.1、4.4.3）
- [x] `TriggerTests.swift`（§3.4.1 M1–M10、§4.11.1、4.11.2、4.11.5–4.11.8）
- [x] 紅燈確認：因 `Sources/Core/` 尚無對應符號而編譯失敗（cannot find … in scope）

## t3 MeetingRecorder.app（code）
- [x] 切出 `Core/`、`Capture/`、`Trigger/`；`probe` 保留
- [x] `build.sh` 編多檔、以 SHA-1 簽章、判斷不加 `-v`、帶 `--entitlements`；新增 `MeetingRecorder.entitlements`（audio-input＋automation.apple-events）、`Info.plist` 加 `NSAppleEventsUsageDescription`（§4.2.8）
- [x] preflight 13 項（第 8 項用 `resolveWindow` 認回、第 13 項 `apple_events` warn）
- [x] 視窗清單：`Core/WindowList.swift`、`Capture/ChromeTabs.swift`（唯讀、Chrome 沒開不送 Apple Events、只有 `--ask-automation` 跳框）、`windows` 改用 `buildWindowRows`、`diagnose-windows`（spec §3.8）
- [x] 擷取設定＋`record.meta.json` 快照（含 devices）
- [x] 60 秒輪替＋每段依視窗尺寸＋`manifest.json`
- [x] 監看：黑畫面、suspended、雙路靜音、音量紀錄、音訊格式變更、裝置變更、磁碟
- [x] SIGTERM 優雅停止＋spawn finalize＋狀態檔
- [x] quick-start、menu bar（HIG 對照，對映照 §3.4.1）、`RegisterEventHotKey`
- [x] Swift 測試全綠、歸屬 t3 的靜態檢查全綠、`test_docs_app_args_exist_in_sources` 綠（以 t5 文件為準）

## t4 CLI 層（code）
- [x] `meeting.sh`：`record)`（含 `--recorder`／`--yes` 任何位置都拿掉、`./record` 撞名）、`usage()`（spec §2.4.6 的 record 段）、`doctor()`＋`return 0`
- [x] `record.sh` 七種寫法（含 `help`，文法照 spec §2.4.3）與結束碼（以 t5 文件為準）
- [x] `test_docs_cli_block_matches_help`、`test_docs_flags_match_behavior`、`test_docs_exit_codes_match_behavior` 綠
- [x] `_record_prompt.py`（視窗選單逐字印 label、★ 預設、輸出加 `bundleID`／`title`）、`_record_estimate.py`
- [x] `record.sh` 只在 tty 時帶 `--ask-automation`、傳 `--window-bundle`／`--window-title`；doctor 加「◦ 會議分頁標記」一行
- [x] `_record_finalize.py`（逐段正規化、原子提交、冪等、保留 tracks）
- [x] `config.json` `sourceLayout`
- [x] lint 26 檔、doctor 綠、`tests/record` 中屬 t4 的測試全綠

## t5 文件（doc，第 1 層，先於 t3／t4）
- [x] `.claude/skills/meeting-record/SKILL.md`（含 `record-cli` 區塊、會議視窗標記與 Apple Events 選用說明、`diagnose-windows` 排錯；不寫「不要用 native 全螢幕」）
- [x] `meeting-summary/SKILL.md` 正文指路（frontmatter 不動）
- [x] `README.md`（含相同的 `record-cli` 區塊）
- [x] `.gitignore`
- [x] 歸屬 t5 的 8 支測試綠（`test_docs.py` 文件側 7 支＋`test_gitignore_media_rules`）

## test 段（2026-10-11）
- [x] verifier：自動部分 pass 18、fail 0、not_verifiable 13（交 t6）；設計審查（靜態）should-fix 3、nit 3（`dc9c2b1`）
- [x] D17（停止時顯示「收尾中…（告警 N 則）」，新增 M6a）、D18（t6 前先修 SF-1、SF-3 與 3 則 nit）：spec 修訂 `f25d28c`
- [x] D17／D18 紅燈測試（`testMenuBarStateMapping` 改預期、`testAccessibilityTextPrefix`、`testTruncatedStatusTitle`、`testMenuBarLockSingleInstance`、5 支靜態測試）
- [x] D17／D18 實作（`Core/Trigger.swift`、`Trigger/MenuBar.swift`、`runMenuBar`）＋全量重跑＋verifier 複驗（`e97c445`、`aff7c05`；複驗 pass 23、fail 0、not_verifiable 12，`5a49f79`）
- [x] t6 中途修正輪（D19 兩段式、D20 自管 AVAssetWriter）：m1 `dc98b54`、m2 `db021f6`、m3 `a4f6800`、m4 `b11ac11`，整合到 `ec71657`；主 session 重跑全量 Python 111 支、Swift 46 支全綠，verify 回 0，名稱掃描沒有命中
- [x] t6 接續（plan §6 順序）：已做的項目與缺陷 A–G、觀察 H 見 run 目錄 `t6-results.md`〈t6 接續〉；使用者決定 D21、D22
- [x] t6 第二次中途修正輪：spec／design／plan 修訂（本 commit；plan §7）
- [x] 使用者核准 t6 第二輪的 spec＋plan（核准前不實作） （2026-10-12 00:20 核准）
- [x] n1 Python 紅燈＋D21 測試預期修改＋`e2e_check.py` 判準（G、F2）（plan §7 n1 完成條件 (1)–(5)） `ec3ed88`
- [x] n2 Swift 紅燈（`testNextSegmentSize`、`testShouldEmitVideoHeartbeat`、`testCompletionOutcome`） `03fa8f9`
- [x] Red 層整合＋測試指令（plan §7 表） `eb92138`
- [x] n3 錄製器：A 換段當下同步讀尺寸、D 最終訊息、E 影片心跳、D21 `.fail` 訊息 `b9b2230`
- [x] n4 finalize：B／F 尾端長度（`cap`、一律 `setpts`、串接最後封包 1 tick）；2254、1650 複本回 0 且 `video_covers_audio` PASS `cb4b791`（另加「下一幀已在段落結束處且最後一幀在容差內不補尾」例外，保 §4.6.10；衍生工作（不編號）：補進 design §7.4）
- [x] 第 2 層整合＋全量 Python、Swift、verify、名稱掃描 `5a6744f`；主 session 重跑 Python 118、Swift 49 全綠，verify 0，名稱掃描沒有命中
- [x] t6 第二輪重測 1：重新安裝（先問使用者） （2026-10-12 完成）
- [x] t6 第二輪重測 2：2254（先問使用者，既有輸出移到備份）、1650 重新收尾＋`e2e_check.py --segment-writer`（§4.6.18、§4.6.19、§4.4.3 (c)） （2254 差 28 ms、1650 rc 0 差 30 ms）
- [x] t6 第二輪重測 3：§4.3.4 縮放（A） （PASS）
- [x] t6 第二輪重測 4：`kill -9`（§4.8.4，E／D22；另記會議 app 沒聲音的一次） （有畫面 110→110 s、靜止 110→100.4 s、靜止無聲 110→100.4 s，皆 PASS）
- [x] t6 第二輪重測 5：chmod 寫檔失敗（§4.4.7 訊息，D） （PASS）
- [x] t6 第二輪重測 6（HFP2 0159：切換中斷 1.5／2.5 s、提前換段、sync 依新量法 PASS；缺陷 J、K、發現 I、M）：§4.9.3 嚴格版（同步測試源＋持續說話；記裝置切換後第一次 preflight 第 6 項，觀察 H）
- [~] t6 第二輪重測 7（自動可測部分完成，見 run 目錄 t6-results.md；需使用者在場的項目列在晨間報告）：其餘 t6 項目（含 §4.2.6 第 5 項 (i) 依 D21 再確認）
- [ ] 閘門 3（等 t6 實測 §4.9.1–4.9.3 後）

## t6 人工驗收（check，test 段）
- [ ] 使用者重新授權（螢幕錄製、麥克風、文件資料夾）；preflight 第 4、6 項 pass（§4.2.8）
- [ ] 量測閘門 §4.4.3、§4.3.4（§4.4.4 記錄）
- [ ] preflight 13 項各失敗一次（§4.2.6）
- [ ] 3 分鐘端到端＋Space 切走＋最小化＋Teams 全螢幕觀察（§4.10）
- [ ] 視窗清單：Apple Events 第一次授權、M+ Meet 全螢幕第一列「★ 會議（M+ Meet）」且為預設並錄得到、LINE 通話出現在清單、不授權仍可錄、`diagnose-windows` 實跑（§4.15.16–4.15.18）
- [ ] fps 尖峰（§4.3.3）
- [ ] 藍牙：錄製中切換（§4.9.1）、全程藍牙（§4.9.2）、HFP（§4.9.3）、不碰預設裝置（§4.9.4）
- [ ] `kill -9` 救援與冪等（§4.8）；並發（§4.7.1）；磁碟不足（§4.5.5）
- [ ] menu bar、quick-start、快捷鍵（§4.11）＋ 9 張截圖給設計審查；D17／D18 實機點：選單展開時秒數在走（§4.11.9）、⌃⌥⌘R 顯示且一次只開一場（§4.11.6）、快捷鍵被佔用時寫 log（§4.11.3）、狀態列 labelColor 與截斷（§4.11.8）、VoiceOver 前綴、連開兩次只一個圖示（§4.11.10）、有／無告警各停止一次（§4.11.7）
- [ ] prep 與 diarize 一致率迴歸（§4.13.4、4.13.5）
- [ ] 實機缺陷：`preflight --window` 在 `SCContentFilter(desktopIndependentWindow:)` SIGABRT（SkyLight 連線第一次在背景執行緒建立而 assert）。紅燈 `b16a375`（`test_windowserver_connection_initialized_on_main_thread`）；修正：`main.swift` 分派 Task 前於主執行緒 `NSApplication.shared`＋`.accessory`＋`CGMainDisplayID()`（fix commit 同本行）；待主 session 實機複驗 preflight／start／quick-start

## t6 第三次中途修正輪（D23，2026-10-12 使用者睡眠期間依指示由主 session 定案）
- [x] spec／design／plan §8（`326494c`）：I（幕前調度 warn）、J（串接一次編 AAC）、K（3 秒連續低音量、sync 1 kHz 帶通）、L（磁碟檢查不讀快取）、M（fps_min_interval 三條件）、§4.8.1 上限
- [x] p1 `731bd00`、p2 `a8f0105`、p3 `5a841f8`、p4 `e2496de`、p5 `09fd921`，整合 `7c31fd2`；主 session 重跑 Python 124、Swift 50 全綠
- [x] 缺陷 N（稀疏 VFR 尾幀讀不到）：紅燈 `4b81f68`、修 `94f54d2`；Python 126、Swift 50 全綠；7 場實機複本 finalize 全回 0
- [x] 重新安裝（依使用者指示）、§4.5.5 磁碟不足 35 s 自動停止 PASS、3 分鐘端到端 0330 重新收尾 PASS（差 6 ms、sync 94 ms）
- [ ] 閘門 3（使用者；含 spec §6 第 63–75 條追認）

## t6 第四輪與設計審查小意見（2026-10-12 白天，使用者在場）
- [x] test 段第三輪（`ecf2819`）：verifier 0 fail；設計審查無 Blocker、3 則 Nit
- [x] 設計審查 N-1–N-3：紅燈 `9b58bb4`、修 `dfba24d`（收尾失敗短句＋「複製完整訊息與補救指令」、quick-start 有 warn 送通知、快捷鍵失敗不顯示 ⌃⌥⌘R；spec §6 第 73–75 條）；SKILL.md 當機損失補實測 `0ef7da9`；Python 128、Swift 52 全綠；重新安裝、menu bar 重啟
- [ ] §4.9.1 錄製中切換（e2e/t6r4-SW/…/1442）：segment_*、gap、video_covers_audio 都 PASS；device_switch FAIL（麥克風真正沒緩衝 1.5 s，其餘是沒說話的低音量，前提不成立）、sync FAIL 118 ms（輸出切到藍牙後原始段落就晚約 100 ms，未分辨是測試源還是擷取）。重測：麥克風旁持續放音樂、輸入輸出一起切（使用者晚上在場）
- [ ] 晚上實機：§4.3.5 系統聲音範圍、§4.2.3 hard fail 不留段落、§4.11.1 quick-start code 2／3／開錄、新 menu bar 實機確認與截圖

## test 段（主 session）
- [x] 平行派 `dev-design-reviewer`（has_ui=true；靜態兩輪，截圖留 t6）
- [x] 修正第 1 輪（fix1，§4.3.3 (ii) 0330 場次過近間隔 4 處 > 上限 3）：根因＝補尾的 tpad 第一個複製幀落在「最後一幀 PTS＋最後一幀長度」，距 cap 13.3 ms 卻沒被併進 cap（舊門檻 10 ms），同一邊界 2 個過近間隔；同類另兩種（最後一幀距 cap 10–15.67 ms、複製幀緊貼最後一幀，2254 場次 seg-0007）一併修。紅燈＋修正見 fix commit；`test_finalize.py::test_tail_pad_no_extra_close_interval` 三個案例；Python 127 全綠；7 場實機複本 `fps_min_interval` 全 PASS（修前 0330、t6r2-AE、t6r2-E3、2254 FAIL），其餘判準與修前相同

## 推送前（主 session，plan §5.1）
- [ ] 以 `client-names.txt` 掃 `origin/main..main`、`main..feature/meeting-record`（與拆包分支）的 `git log -p` 及各分支 HEAD 樹；命中就留備份分支、以選項式提問交使用者決定，核准後才改寫與推送

## deliver 後（主 session）
- [ ] `~/.claude/skills/meeting-record` symlink（§4.12.5）

## R2 第二輪（2026-10-12；plan §9）

### R2 Design
- [x] intent R2 節與閘門 1（`a93f2ac`、`975971b`；`run.json` 的 `r2-plan` 已核准）；本機 tag `meeting-record-r1-baseline`＝`f084765`
- [x] design.md〈R2 第二輪設計〉、spec.md §2.4 就地更新＋檔尾〈R2 第二輪〉（§3.9–§3.14、§4.16–§4.25、§6 第 77–97 條、§7 疑慮 35–42）、plan §9、ADR 四則（`adr-r2-*.md`）
- [x] skeptic 一致性檢查（第一次：8 條問題，run 目錄 `r2-design-issues.json`）
- [x] 閘門 2 使用者決定（2026-10-12）：(1) 時間軸選項 A；(2) 自動前處理先不讓路、t7 觀察；(3) 新欄位 nil 省略鍵、`RecordsTests` 不改；(4) skeptic 問題全部修正，複查沒有新問題就視為閘門 2 核准、直接進 build
- [x] 閘門 2 修正輪：spec §3.12 範例、§3.14（`Segments.swift` 的 `PauseGate`／`SwitchReason`、`Control.swift` 的事件 append 與狀態欄位、`detectorFeed`）、新增 §4.16.11、§4.17.7–§4.17.8、§4.18.8–§4.18.12，改 §4.18.2、§4.18.3、§4.25.1、R2-§5、R2-§6（第 79、95、96 條依據；新增第 98、99 條）、§7 疑慮 38；design R2-D3a 等；plan §9.1 story 逐條、§9.2、新增 §9.5 拆 PR；對照表 run 目錄 `design-revise-對照.md`〈R2 閘門 2 修正輪〉
- [ ] skeptic 複查（使用者決定 4：沒有新問題即視為閘門 2 核准）
- [ ] 閘門 2 核准記錄（`save_run.py approve`，stage 鍵 `r2-design`；含 §6 第 77 條的測試預期修改）

### R2 Build（plan §9.1、§9.3）
- [ ] Red：r2a（tests/record/）
- [ ] Red：r2b（tools/MeetingRecorder/Tests/）
- [ ] Red 層整合＋測試指令（plan §9.3）
- [ ] 第 1 層：r2c（SKILL.md、README）
- [ ] 第 1 層：r2d（Core/）
- [ ] 第 1 層整合＋測試指令
- [ ] 第 2 層：r2e（Capture/）
- [ ] 第 2 層：r2f（Trigger/、main.swift）
- [ ] 第 2 層：r2g（bin/）
- [ ] 第 2 層整合＋全量 Python、Swift、建置（暫存目錄）、`check_rules.py --git`、verify、名稱掃描
- [ ] deliver：照 plan §9.5 拆 R2-1（app）、R2-2（CLI、測試、文件、specs）兩包；推送前照 §5.1 掃描

### R2 Test（r2t7，使用者在場）
- [ ] 使用者同意後覆蓋安裝、重開 menu bar
- [ ] §4.25.1 4 分鐘劇本＋`e2e_check.py --segment-writer --pause-mute`（九項，含 `mute_timing`、`no_false_black`、`event_output_t`）
- [ ] §4.25.2 選單、計時、收音指示＋截圖（淺色／深色）
- [ ] §4.25.3 選單選視窗、換存檔位置
- [ ] §4.25.4 偏好設定、登入自動開（重新登入）、自動前處理、通知「在 Finder 顯示」
- [ ] §4.25.5 第一輪剩下的實機項目（§4.9.1 重錄、§4.3.5、§4.2.3、§4.11.1）
- [ ] 設計審查（`has_ui=true`，§6 第 92 條）
- [ ] 閘門 3（R2；與第一輪閘門 3 分開記錄）

## R3 第三輪（2026-10-13；plan §10）

### R3 Plan／Design
- [x] intent〈R3 第三輪〉與閘門 1（`56aacca`；`run.json` 的 `r3-plan` 已核准；R3-Q1＝A、R3-Q8＝B，其餘預設）
- [x] design.md〈R3 第三輪設計〉（R3-D1–R3-D20）、spec.md 檔尾〈R3 第三輪〉（修正輪起 §2.4 不再就地更新，`sync` 改頂層 `meeting sync`）（§3.15–§3.20、§4.26–§4.47、§6 第 117–133 條、§7 疑慮 43–51）、plan §10、ADR 四則（`adr-r3-*.md`）、run 目錄 `r3-subtasks.json`
- [x] Claude Design 出稿 → 使用者挑稿（U1＝C、U2＝C、U4＝A、U5＝A、U6＝A、U7＝A、F2＝A、F3＝A；設計語言「暗房」）→ 存 `design-r3/`（`README.md`＋9 個原始稿；存前後掃名稱：沒有）
- [x] 補 spec 的 UI 外觀條文（§3.20 `DesignTokens.swift`、§4.38.3／5–8、§4.40.4／7–8、§4.41.2–5／7、§4.42.2、§4.43.5–7／9、§4.44.3–4）、§6 第 129、130 條的新舊字面、新增第 134、135 條、§7 疑慮 52–56；design.md R3-D21（設計稿定案）、R3-D22（字型不打包）
- [x] 使用者決定（閘門 2，2026-10-13）：疑慮 52 採 (a) 14pt bold、53 用 `NSAlert`、54 字型不打包、57 選 (b) 現在加行事曆 entitlement（§6 第 138 條生效，entitlements 恰為三項）
- [ ] 確認提醒事項權限的 Info.plist 鍵名（§7 疑慮 45）
- [x] skeptic 一致性檢查（兩個 skeptic；修正輪 A–J 已改，`design.md` R3-D30）
- [x] 修正輪複查：改由 integrator 合併後驗證（層檢查 0 問題、verify、相關 unittest、check_rules、名稱掃描）取代，使用者於閘門 2 核准
- [x] 閘門 2 使用者核准（2026-10-13；`save_run.py approve`，stage 鍵 `r3-design`；含 §6 第 117–139 條的既有測試修改，撤回的 117、122、125 除外；第 136、137、139 條核准，第 138 條依疑慮 57 生效）

### R3 Build（plan §10.1、§10.3；修正輪 6 層）

| 層 | 子任務 | 狀態 | 合併 commit |
|---|---|---|---|
| Red | `r3-red-py` | 已合併 | `b4c8ae1` |
| Red | `r3-red-swift` | 已合併 | `9b347c5` |
| 1 | `r3-core` | 已合併 | `1d89f0b` |
| 1 | `r3-vtt-raw` | 已合併 | `0154b59` |
| 1 | `r3-record-lib` | 已合併 | `a2cb1e8` |
| 1 | `r3-finalize-guard` | 已合併 | `2751571` |
| 1 | `r3-sync-measure` | 已合併 | `cb6f933` |
| 1 | `r3-docs` | 已合併 | `6fd631a` |
| 2 | `r3-lock` | 已合併（併入原 r3-latency-log） | `db49336` |
| 2 | `r3-menubar-states` | 已合併（併入原 r3-notify；entitlements 3 項的驗收待第 3 層 r3-reminders 合併後確認） | `8f0ccc4` |
| 2 | `r3-search` | 已合併 | `34f6766` |
| 2 | `r3-transcript-vad` | 已合併 | `004c83d` |
| 2 | `r3-annotations` | 已合併 | `79d5b0c` |
| 3 | `r3-finalize-runner` | 未開始 | |
| 3 | `r3-hud` | 未開始 | |
| 3 | `r3-reminders` | 未開始（entitlement 依疑慮 57） | |
| 4 | `r3-discard` | 未開始 | |
| 5 | `r3-segment-scheduler` | 未開始 | |
| 5 | `r3-menu-stages` | 未開始 | |
| 6 | `r3-sync-compensate` | 未開始 | |
| 6 | `r3-onboarding-settings` | 未開始（併入原 r3-meeting-detect） | |

- [ ] 每層整合＋plan §10.3 的測試指令
- [ ] 第 6 層：全量 Python、Swift、建置（暫存目錄）、entitlements 項數（依疑慮 57）、`check_rules.py --git`、verify、名稱掃描

### R3 Test（`r3-field-check`，使用者在場；spec §4.47）
- [ ] 使用者同意後覆蓋安裝、重開 menu bar
- [ ] §4.47.1 E4、§4.47.2 E2（決定 S-C 預設）
- [ ] §4.47.3 HUD `sharingType`、§4.47.4 Time Sensitive
- [ ] §4.47.5 提醒事項、§4.47.6 F3、§4.47.7 F2、§4.47.8 首次引導
- [ ] §4.47.9 `keep-segments` 真實多人會議（調 VAD 門檻）
- [ ] §4.47.10 全套 e2e 迴歸、§4.47.11 設計審查
- [ ] 閘門 3（R3，stage 鍵 `r3-test`）

### R3 Deliver
- [ ] 依 plan §10.5 拆包（先問使用者）；推送前掃名稱（只回報有／沒有）
- [ ] 閘門 4（stage 鍵 `r3-deliver`）

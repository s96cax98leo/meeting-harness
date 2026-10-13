# design：meeting-record（錄製器本體＋觸發層）

- epic：`meeting-record`；上游文件：`specs/meeting-record/intent.md`（已核准，不改）
- 需求正本：`_tpm/runs/20261010-sdlc-meeting-record/requirement.md`（本機、非版控；以下簡寫 `req:<行>`）
- D1–D16：`_tpm/runs/20261010-sdlc-meeting-record/gate1-decisions.md`（D6 藍牙、D7–D12 為閘門 2 前的使用者決定；D13「文件先寫」、D14「告警停到下次開錄」為閘門 2 第三修正輪的使用者決定；D15「先診斷，再補進 spec」、D16「讀瀏覽器分頁網址來標記」為閘門 2 核准後、build 前的使用者決定）；D2 實測：同目錄 `d2-audio-experiment.md`（以下簡寫 `d2:<行>`）；視窗清單診斷：同目錄 `window-filter-diagnosis.md`（run 目錄、不進版控；specs 只引行號與實測數字，不抄其中的真實視窗標題；以下簡寫 `wfd:<行>`）
- 修正輪對照：`_tpm/runs/20261010-sdlc-meeting-record/design-revise-對照.md`（第一輪 D6–D12＋skeptic 14 條；第二輪 skeptic 5 條；第三輪 D13、D14＋skeptic 3 條；第四輪 skeptic 2 條；第五輪 skeptic 1 條；第六輪 D15、D16＋skeptic 2 條；第七輪 skeptic 2 條：客戶會議名稱換成中性範例、§4.1.12 替身參數改為子序列斷言）
- 架構取捨（ADR）：`specs/meeting-record/adr/` 下四則（第六修正輪新增 `adr-meeting-window-marking.md`），本檔只摘結論
- 本檔回答 intent §5「留給 Design 段定案」的 Q4、Q6–Q9，以及 intent §3 點名的 finalize 競態、§4 點名的空隙量法與補幀；修正輪另回答 D6（錄製中音訊格式變更）、D8（每段依視窗大小開檔）、D11（`./record` 目錄撞名）、D12（menu bar 設計審查依據）、D15／D16（視窗清單認不出會議視窗、無標題視窗被濾掉、會議分頁標記，§8.3）
- **Swift `Core/` 的名稱、參數標籤與型別只以 `spec.md §3.4` 為準**，本檔不重抄簽名（修正 skeptic 問題 5、9：兩處寫法不一致）
- **t6 中途修正輪（D20，2026-10-11）**：t6 實機量測閘門不過（`SCRecordingOutput` 不能在執行中的 stream 上輪替），使用者選「自己管 AVAssetWriter（建議）」。本輪改寫 §2 架構圖、§3.3、§7.1 換尺寸、§7.2 換段（全改）、§7.4 停止與 finalize（混音、時間戳正規化、fragment 段落）、§7.5 落盤，新增 §7.6（preflight 到正式 `startCapture` 之間的等待與重試）；決定與實機紀錄見 `adr/adr-segment-writer.md`。D19（preflight 第 5 項兩段式，`c5022d4`）不受影響，紅燈 `09e6f05` 併入本輪實作
- **t6 第二次中途修正輪（2026-10-12；D21、D22）**：t6 接續的實機缺陷與使用者決定（`_tpm/runs/20261010-sdlc-meeting-record/t6-results.md`〈t6 接續〉、`gate1-decisions.md` D21／D22、`t6-rca-ABE.md`）。本輪改寫：§6 第 5 項（D21：靜音只 warn、`.fail` 訊息只留授權補救）、§7.1（缺陷 A：換段當下同步讀視窗尺寸）、§7.2〈當機〉（缺陷 E／D22：影片心跳）、§7.2〈writer 失敗〉與 §7.4 停止第 4 步（缺陷 D：停止原因不被收尾失敗蓋掉）、§7.4 finalize 第 3、4 步（缺陷 B、F：尾端長度；F2：`gapStats` 與 `e2e_check.py` 同一把尺），並追認 m3、m4 與 design 字面不同的實作選擇（§7.2、§7.4）。`e2e_check.py` 判準的修正（缺陷 G）見 `spec.md §4.4.3` (c)
- **t6 第三次中途修正輪（2026-10-12，定案）**：t6 第二輪重測的發現 I、缺陷 J、K、L 與發現 M（`t6-results.md`「t6 第二輪重測」「t6 第二輪 7」）。依使用者 2026-10-12 指示「明天一早就要完成所有功能開發與驗證」由主 session 依建議定案，使用者可於醒來後改選（`spec.md §6` 第 63–70 條）。本輪改寫：§6 第 12 項（I：幕前調度提醒）、§7.1 新增〈幕前調度〉、§7.3 磁碟列（L）、§7.4 finalize 第 3–5 步與新增〈缺陷 J〉、§10 測試策略（K、M 的量法）；之後補記〈缺陷 N〉與補尾過近間隔（`spec.md §6` 第 71、72 條）

---

## 1. 依據摘要（先證據、後結論）

| 事實 | 依據 |
|---|---|
| 沒有服務、沒有 HTTP 端點；對外契約只有 CLI、資料夾擺法、skill 三類 | `research-code-contracts.md:8-15` |
| `open` 派送後立刻回 0，不轉傳 app 結束碼 → 需要檔案式狀態通道 | `req:207`；`tools/MeetingRecorder/probe.sh:88-92` |
| 場次判定只看 `錄音/` 第一層有沒有六種副檔名，不檢查寫完沒有 | `bin/meeting.sh:193-204` |
| 多檔是串接不是混音；glob 非遞迴、點號檔排除 | `bin/_combine_audio.py:12-18`、`:30-39` |
| preflight 系統聲音：錄製器 spawn 的子程序 `afplay` 在 `excludesCurrentProcessAudio=true` 下錄得到；自己 `NSSound.play()` 錄不到 | `d2:17`、`d2:19`（實驗 C1、D） |
| 判定用 0.5 秒時段峰值，不用中位數；「沒聲音」與「沒授權」都呈現 -∞ 但回呼照常到 | `d2:23-29` |
| **單一視窗 filter 只錄得到擁有該視窗的 app 的聲音**：Chrome 播影片時，對該 Chrome 視窗 preflight 系統聲音 -10.2 dBFS、同一時間對終端機視窗 -∞；錄製器 spawn 的 `afplay` 在單一視窗 filter 下錄不到（D2 實驗 D 錄得到是因為用 display filter，`d2:7`）。所以第 5 項改兩段式（§6）、錄製的系統聲音範圍見 §7.1 | t6 實機（`gate1-decisions.md` D19 列）；`spec.md §4.2.5`、`§4.3.5` |
| **`SCRecordingOutput` 不能在執行中的 stream 上輪替**：拔掉後等 `recordingOutputDidFinishRecording`，4 次輪替回呼都沒來（每次約 10.5 秒＝10 秒逾時，各段 `finishedAt`／`audioDuration` 全 `null`）；拔掉後不等就掛新段 → 整條 stream 中斷（ReplayKit `RPRecordingErrorDomain -5814`）；先 `stopCapture` 再拔，回呼仍未在 10 秒內到。對照：`stopCapture` 之後才拔，三次都收到回呼；單一段落的影片、wav、音影對齊都正確。→ 改自管 `AVAssetWriter`（D20，§7.2） | t6 實機（`t6-results.md`，run 目錄）；`adr/adr-segment-writer.md`〈t6 實機結果〉 |
| 實機 SCK 多段串接時 ffmpeg 報 `non monotonically increasing dts to muxer in stream 0`，finalize rc=5、影片與 wav 未產出；以 `lavfi` 合成素材的測試沒抓到 → finalize 要先逐段正規化時間戳再串接（§7.4） | t6 實機（`t6-results.md`「缺陷 3」）；`spec.md §4.6.14` |
| preflight 13 項通過後立刻開正式 stream，一次 `startCapture` 失敗「無法開始音訊串流」，重開即正常；當時輸入、輸出都是藍牙耳機，推測 preflight 的 probe stream 剛停、藍牙麥克風還沒釋放 → 正式 `startCapture` 前等待、失敗重試一次（§7.6） | t6 實機（`t6-results.md`「缺陷 4」）；`spec.md §4.2.11` |
| SCK 的 sample PTS 與 `CMClockGetHostTimeClock()` 同一個時鐘：現行程式以 `pts.seconds − t0`（`t0`＝`startCapture` 前一刻的 host clock）算時間，`levels`、`blackIntervals` 都依它，t6 的 levels 與事件時間對得上 | `tools/MeetingRecorder/Sources/Capture/RecordingSession.swift:5`、`:13`、`:351-353`；t6 levels（`t6-results.md`） |
| WindowServer 連線第一次在 Swift concurrency 背景執行緒建立時，建 `SCContentFilter` 會因 SkyLight assert 而 SIGABRT；`main.swift` 分派 Task 前在主執行緒 `NSApplication.shared`＋`.accessory`＋`CGMainDisplayID()` 即可避免 | t6 第 1 步實機；`b16a375`、`413eb50`；`spec.md §4.2.10` |
| 系統聲音是非交錯立體聲，用 `MemoryLayout<AudioBufferList>.size` 配置會靜默失敗、看起來像沒授權；要用 `CMSampleBuffer.withAudioBufferList` | `d2:34-39` |
| 影片在最後一次畫面變化處結束，影片軌比音訊軌短 | `tools/MeetingRecorder/PROBE-REPORT.md:27-29` |
| 第 0 階段畫布鎖顯示器 2992×1934；被錄的 Chrome 視窗是 1496×938 pt，2x 即 2992×1876，正是 `req:57` 舊錄檔的尺寸 | `PROBE-REPORT.md:4`、`:15`；`req:57` |
| `SCContentFilter` 在 macOS 14 起提供 `contentRect` 與 `pointPixelScale`；`SCStream.updateConfiguration(_:)` 可在串流執行中換設定 | Apple SDK 標頭（`ScreenCaptureKit/SCStream.h`）；D20 後換尺寸改由新 writer 以新尺寸開檔（§7.1），`AVVideoScalingModeKey` 的實際行為未實測，列 test 段量測 |
| 本機 ffmpeg 7.1.1，支援 `-fps_mode` | `ffmpeg -version`；`ffmpeg -h full | grep -c fps_mode` |
| 簽章身分「MeetingHarness Dev」**已存在且與私鑰成對，但不受信任**：`security find-identity -p codesigning` 回 `1) 5E249F84A9EC2F2D2B3914120906DF29FB4DF348 "MeetingHarness Dev" (CSSMERR_TP_NOT_TRUSTED)`，加 `-v` 才是 0；D2 的 spike app 已用它簽成功（`codesign -dvv ~/.meeting-harness/spike/AudioProbeSpike.app` 回 `Authority=MeetingHarness Dev`） | 本段指令可重跑；`tools/MeetingRecorder/build.sh:32` 用 `-v` 判斷，所以退回 ad-hoc。修正：`build.sh` 以 SHA-1 `5E249F84A9EC2F2D2B3914120906DF29FB4DF348` 簽（`codesign --sign <SHA-1>`），判斷有無改用不加 `-v` 的 `find-identity` 比對該 SHA-1 |
| **hardened runtime 從未真正啟用過**：現行 `build.sh:33` 在固定身分分支才加 `--options runtime`，但 `build.sh:32` 的 `-v` 判斷讓它一直走 ad-hoc 分支（`build.sh:36`，不帶 runtime）；D2 spike 雖用固定身分簽，但沒有 runtime（`codesign -dvv ~/.meeting-harness/spike/AudioProbeSpike.app` 回 `flags=0x0(none)`）。改用 SHA-1 簽章後 app **第一次**以 hardened runtime 執行；Apple 規定 hardened runtime 的程式要有 `com.apple.security.device.audio-input` entitlement 才能用麥克風，repo 目前沒有任何 entitlements 檔（`ls tools/MeetingRecorder/Resources/` 只有 `Info.plist`） | 本段指令可重跑；Apple Developer 文件〈Hardened Runtime〉的 Resource Access 清單。修正見 §9.1（第二輪 skeptic 問題 2） |
| 藍牙耳機啟用麥克風時 macOS 改走 HFP，輸出取樣率中途改變（常見 48→16 或 24 kHz） | D6 使用者描述；**本機未實測**，由 `spec.md §4.9.3` 在 test 段驗；使用者配對過的耳機：XROUND FORGE NC、XROUND FORGE PRO |
| 本機 ffmpeg 有 `h264_videotoolbox` | `ffmpeg -hide_banner -encoders | grep videotoolbox` |
| 使用者說「清單裡根本沒有那個視窗」時要錄的是 Chrome 裡的 M+ Meet；該視窗**被現行篩選納入**，但網頁標題是會議名稱（真實會議名稱不寫進 repo，下文一律以中性範例「[Stand-up] 範例專案」代稱，原文只在 run 目錄的診斷報告），清單只顯示「Google Chrome — <會議名稱>」，與其他 7 個 Chrome 視窗混在一起認不出來 | `wfd:9-10`、`wfd:31-32`、`wfd:37` |
| 「標題非空」篩選把 LINE 通話視窗（500×500、layer 0）與 PowerPoint（1197×840、layer 0）濾掉；Chrome 全螢幕時的工具列／浮層（1496×81～158、1016×87～139）由尺寸規則濾掉是正確的 | `wfd:18-20`；`main.swift:122-129` |
| 同一個 M+ 視窗的 windowID 由 81837 變成 89596；**前一版 spec 沒有任何「認回」規則**（preflight 第 8 項只判 windowID 存在） | `wfd:33`、`wfd:38`；本輪前 `grep -n '認回' spec.md design.md` 無結果 |
| M+ 視窗按綠色按鈕進 native 全螢幕後切到別的 Space，`desktopIndependentWindow` 擷取 complete 3／idle 14、0 張全黑 | `wfd:17`、`wfd:40` |
| 以 AppleScript 唯讀查 Chrome 各分頁網址可以定位會議分頁所在的視窗（診斷時就是這樣找到 M+ 視窗的）；Chrome 的 AppleScript 視窗 `id` 是 Chrome 自己的編號，不是 `CGWindowID`，所以要以標題與位置對應 | `wfd:31`；Chrome scripting dictionary（`window` 的 `id`、`title`、`bounds`、`active tab`） |
| 原型把 `com.google.Chrome`、`com.apple.Safari` 整個 app 當會議 app，8 個 Chrome 視窗會全部標 ★，quick-start 的「★ 恰好一個」永遠不成立 | `main.swift:106-112`、`:116`；`wfd:37` |
| hardened runtime 下送 Apple Events 需要 `com.apple.security.automation.apple-events` entitlement，且 `Info.plist` 要有 `NSAppleEventsUsageDescription`；缺 entitlement 時請求會被拒且可能不跳授權框（與麥克風同類的靜默失效） | Apple〈Hardened Runtime〉Resource Access；Apple〈NSAppleEventsUsageDescription〉；第六修正輪 skeptic 問題 2 |

---

## 2. 元件與責任

```
                       ┌───────────────── 終端機 ─────────────────┐
 meeting record …  ──▶ │ bin/meeting.sh  record) ─▶ bin/record.sh │
                       │   ├─ _record_prompt.py（問答，印 JSON，不寫檔）
                       │   ├─ _record_estimate.py（磁碟需求）       │
                       │   └─ open -n -a MeetingRecorder.app --args … ──┐
                       └──────────────────────────────────────────┘    │
 Shortcuts 快捷鍵 ── open -n -a MeetingRecorder --args quick-start ─────┤
 menu bar 常駐實例（--args menubar）── 開始：同上 quick-start；停止：SIGTERM ─┤
                                                                        ▼
            MeetingRecorder.app（錄製實例，每次錄製一個 process）
              preflight → SCStream（desktopIndependentWindow）
                ├─ .screen output ──┐（frame status＋像素抽樣監看；同一個 sample 也寫檔）
                ├─ .audio output ───┼─▶ SegmentWriter：每段一個 AVAssetWriter（video＋系統聲音＋麥克風三軌）
                ├─ .microphone ─────┘   寫 tracks/seg-NNNN.mov，每 60 秒在 sample 時鐘上無縫換段（D20）
                ├─ RMS／格式偵測（監看）
                ├─ Core Audio 預設裝置 listener、磁碟 30 秒檢查
                └─ 收到 SIGTERM／磁碟不足 → 優雅停止 → spawn finalize
                        │
     ~/.meeting-harness/record.status.json ◀── 唯一的狀態契約（原子寫入）
     ~/.meeting-harness/record.pid / record.log / record.defaults.json
                        ▼
            bin/_record_finalize.py <場次>（也可由 meeting record finish 單獨跑，冪等）
```

| 元件 | 責任 | 不做的事 |
|---|---|---|
| `bin/record.sh` | 子指令 dispatch（含 `help`，輸出文法照 `spec.md §2.4.3`）、互動流程、寫 `meeting.json`、寫 `record.defaults.json`、用 `open -n -a` 啟動、輪詢狀態檔推導 0／2／3／4／5、`stop` 送 SIGTERM 並等 finalize | 不直接 exec 錄製二進位（`req:205`） |
| `bin/_record_prompt.py` | 讀 `record windows --json` 的輸出與上次預設值，問根目錄、場次名、型態、出席者、視窗（逐字印 app 算好的 `label`，預設＝第一個 ★ 列，`spec.md §3.7`）；答案 JSON（含所選視窗的 `bundleID`、`title`）印到 stdout、提示印到 stderr | 不寫任何檔（`req:217`）；型態清單 import `_profile.PROFILES`，不另抄一份；不自己判斷 ★、不重組 label |
| `bin/_record_estimate.py` | 依分鐘數算峰值磁碟需求；`doctor` 與 `record.sh` 共用（`req:219`）；公式見 §5 Q7 | 不碰檔案系統以外的狀態 |
| `bin/meeting.sh` `record)` 分支 | 轉交 `record.sh`；**先處理 `./record` 目錄撞名**（§8.1，D11） | 不自己解析錄製參數 |
| `bin/_record_finalize.py` | `tracks/` → `影片/<名> <時間戳>.mov`＋`錄音/<名> <時間戳>.wav`；空隙統計；逐段正規化（統一尺寸、補尾、統一音訊格式，D7／D8）；原子提交；冪等 | 不刪 `tracks/`（見 §5 Q7）；不縮放畫面 |
| `MeetingRecorder.app` | preflight、擷取、分段、監看、優雅停止、finalize 觸發、menu bar、全域快捷鍵；視窗清單（篩選、會議標記、排序、label、認回、`diagnose-windows`，§8.3） | 不碰逐字稿與認人；對 Chrome 只讀（不切分頁、不執行 JavaScript、不開 Chrome） |
| `.claude/skills/meeting-record/SKILL.md` | 第七個 skill：何時用、失敗時怎麼救（權限、重啟、finish） | 不改 `meeting-summary` 的 frontmatter |

---

## 3. 狀態契約（`record.sh` ↔ `MeetingRecorder.app`）

選這個做法的取捨見 `adr/adr-control-channel.md`。

### 3.1 檔案

| 路徑（`~/.meeting-harness/` 下，可用 `MH_RECORD_HOME` 覆寫，測試用） | 寫者 | 內容 |
|---|---|---|
| `record.status.json` | app（tmp＋rename 原子寫入） | 見 §3.2 |
| `record.pid` | app（開錄時寫、正常結束時刪） | 錄製實例的 pid |
| `record.log` | app（`Logger`，`main.swift:24-41`） | 人看的流水帳 |
| `record.cdhash` | app（preflight 第 1 項；build 段 t3 實作時新增，`spec.md §6` 第 42 條） | 上次的 cdhash，用來偵測簽章身分改變 |
| `menubar.lock` | app 的 menubar 模式（`flock(LOCK_EX)` 持有到 process 結束；D18） | 空檔；只用來保證 menubar 單一實例（`spec.md §4.11.10`） |
| `record.defaults.json` | `record.sh`（每次成功開錄後覆寫） | 上次的根目錄、型態、出席者、`harness` 路徑、`python3`／`ffmpeg` 絕對路徑、`minFreeBytes`；`quick-start` 只讀這個 |

### 3.2 `record.status.json` 欄位（`schemaVersion: 1`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `schemaVersion` | int | 固定 1 |
| `runId` | string | `record.sh` 用 `--run-id` 傳入的 UUID；`record.sh` 只採信 runId 相符的狀態，避免讀到上一次的殘檔 |
| `pid` | int | 錄製實例 pid |
| `phase` | enum | `preflight` → `preflight_failed` ｜ `recording` → `stopping` → `finalizing` → `done` ｜ `failed` |
| `code` | int | 該 phase 對應的結束碼（§4 表）；`recording` 時為 0 |
| `message` | string | 給人看的一句話（失敗時含補救步驟） |
| `session` | string | 場次目錄絕對路徑 |
| `startedAt`／`updatedAt` | string | ISO 8601（本地時區，含偏移） |
| `segments` | int | 已收尾的段數 |
| `preflight` | array | 13 項結果（D1 的 12 項＋D16 的 `apple_events`）：`{item, ok, severity: hard|warn, code, message}` |
| `warnings` | array | `{t, kind, message}`；`kind` 取值見 `spec.md §3.4` 的 `WarningKind`。`silence_system`／`silence_mic`／`black`／`suspended`／`disk_low` 屬**告警類**（menu bar 轉告警態）；`device_change`、`audio_format_change` 屬**紀錄類**（只記錄、不轉告警態，HFP 切換是正常行為） |

### 3.3 場次內的檔案（`req:132-157` 的擺法，加註本設計的定案）

```
<根>/<YYYYMMDD>/<場次名>/
├── 錄音/
│   ├── <場次名> <YYYY-MM-DD HH.MM.SS>.wav   ← finalize 最後一步原子 rename 進來（場次在這一刻才存在）
│   ├── meeting.json                         ← record.sh 開錄前寫（不是音源副檔名，不會讓場次提早出現）
│   └── tracks/
│       ├── seg-0001.mov …                   ← 錄製器以 AVAssetWriter 寫入（D20），每 60 秒一段；每段 1 條影片軌＋2 條音軌（系統聲音、麥克風，順序固定）
│       ├── manifest.json                    ← 段落清單（requested/started/finished 時間、每段像素尺寸）、frame status 統計、黑畫面區間、雙路音量時段峰值、空隙統計、輸出畫布
│       ├── record.meta.json                 ← 視窗、串流設定快照、起始音訊裝置、裝置變更事件、音訊格式變更事件、preflight 結果
│       ├── finalize.json                    ← finalize 完成標記（輸入段清單＋大小、輸出路徑、完成時間）
│       └── .finalize/                       ← finalize 暫存（點號開頭、在子目錄，雙重掃不到）；正規化後的段落與串接結果，提交成功後由 finalize 清掉（自己產生的暫存，不是使用者資料）
├── 影片/
│   └── <場次名> <YYYY-MM-DD HH.MM.SS>.mov   ← 帶時間戳（修正 research-requirement R-11：ingest 補救時分場才對）
└── 照片/
```

`manifest.json` 與 `record.meta.json` 的欄位在 `spec.md §3` 定義，驗收要能用程式讀。

---

## 4. 結束碼

既有約定：`2`＝缺參數／路徑不存在／未知選項／前提不成立，`3`＝找不到目標（`req:83`、`req:224`；`bin/meeting.sh:93,97,251,346,399,407`）。`4`／`5` 雖然在 `bin/diarize.sh:28,44`、`bin/transcribe.sh:190`、`bin/setup-diarize.sh:33,49`、`bin/to-docx.sh:15` 已被使用，但那些都是內部腳本；經 `meeting.sh` 對外時 `run_diarize` 失敗回 1（`bin/meeting.sh:184`），所以 `meeting.sh` 的對外面上 `4`／`5` 目前**沒有語意**，本 epic 只在 `record` 子指令上賦予語意。全域對映表寫在 `spec.md §2`。

preflight 多項同時失敗時的優先序：`4` ＞ `3` ＞ `2`（權限與訊號問題最急，會議要開始了）。

---

## 5. 留給 Design 段的問題：定案與理由

| # | 定案 | 理由（依據） | 代價 |
|---|---|---|---|
| Q4 has_ui | **test 段 `has_ui=true`**（D12「要派」），平行派 `dev-design-reviewer` 審 menu bar；repo 沒有設計系統 skill，審查依據改用 macOS Human Interface Guidelines 的 menu bar extra 慣例，對照項寫成 `spec.md §4.11.5–4.11.8` | D12；`rules.md:58` 的「一律 false」是 init 時的預設，本 epic 由使用者決定例外，記在 `spec.md §6` | 審查者需要三態截圖（淺色／深色各一）；截圖只截 menu bar 區域，由 t6 產出 |
| Q6 meeting.json | **寫 7 個 key**，key 集合與 `bin/_scaffold.py:107-110` 的 dict 完全相同（含 `_note`）；`expectedSpeakers` 固定 `null`；`_note` 文字改為錄製器專用且不承諾「鎖人數」 | `req:269` 字面要求「完全相同」；`_scaffold.py:109-110` 的 `_note` 原文說「人數鎖定」，與 `bin/_profile.py:76-79` 只調上限的實際行為相反，不能照抄值 | 驗收以「key 集合」比對，值不比 |
| Q7 tracks/ 去留 | **finalize 後保留 `tracks/`，程式永不自動刪**；刪除由使用者手動做。`.finalize/` 是 finalize 自己的暫存，提交成功後清掉 | 刪資料是不可逆節點，要使用者當下同意（`CLAUDE.md:15`）；冪等要求保留輸入（`req:218`） | 磁碟峰值＝段落 1 份＋正規化段落約 1.5 份（D7 高碼率，§7.4）＋串接輸出約 1.5 份 ≈ **4 倍**；`_record_estimate.py`：`minFreeBytes = ceil(分鐘 × (4 × 56 MB ＋ 1.92 MB)) ＋ 2 GB`。單位一律十進位：1 MB＝10^6 bytes、**2 GB＝2,000,000,000 bytes**（照 `req:199` 字面「2 GB」；修正 skeptic 問題 14 的 GB／GiB 混用） |
| Q8 doctor | doctor 新增「錄製器」段，只用 `✓`／`◦`／`⚠`，**不出現 `✗`**；函式結尾明寫 `return 0`；TCC 不在 doctor 查（要啟動 app 才查得到，屬 preflight） | `rules.md:59`「沒有錄音檔也要全綠」；既有 pyannote／ollama 就是「◦ 未裝（選用）」語意（`bin/meeting.sh:148`、`:155`）；`doctor()` 沒有 `return 0`（`research-code-contracts.md:27`） | doctor 不會擋「錄製器壞了」；那件事由 `meeting record preflight` 的 exit 4 擋 |
| Q9 第 0 階段四個未驗情境 | **Teams 通話中＋切到別的 Space 進第 1 階段驗收**（`spec.md §4.10.2`，人工）；**最小化**進驗收但只驗「產生 `suspended` 告警」；**native 全螢幕、Mission Control** 只記觀察結果，不判 pass/fail，native 全螢幕失敗就照 `req:249` 寫進使用說明。三者都列進 t6 驗收（修正 skeptic 問題 10） | Teams 是主要懷疑對象（`req:24`、`PROBE-REPORT.md:35`），而端到端劇本本來就用 Teams 自我通話（`req:261`）；最小化是官方承認會暫停的唯一情形（`req:17`） | 四項都需要人操作，test 段要排使用者時間 |

---

## 6. preflight 13 項（D1 分級的 12 項＋D16 的第 13 項）

| # | 項目 | 判定方式 | 等級 | 失敗結束碼 |
|---|---|---|---|---|
| 1 | 簽章身分 | 讀自身 `codesign -dv`：ad-hoc → warn；與上次記錄的 cdhash 不同 → warn「重建過，若擷取失敗請重新授權」 | **warn**（D1：憑證建好前） | — |
| 2 | 螢幕錄製權限 | `CGPreflightScreenCaptureAccess()` 為 false | hard | 4 |
| 3 | 剛授權要重啟 | `CGPreflightScreenCaptureAccess()` 為 true 但 `SCShareableContent` 失敗 → 訊息明確說「已授權，請完全結束 MeetingRecorder 再重開」，與第 2 項分開報（`PROBE-REPORT.md:51-53`） | hard | 4 |
| 4 | 麥克風權限 | `AVCaptureDevice.authorizationStatus(for: .audio)`：`.denied`／`.restricted` → fail；`.notDetermined` → 觸發請求並 fail（要重開）。hardened runtime 下沒有 `com.apple.security.device.audio-input` entitlement 時麥克風取不到，會表現為本項或第 6 項失敗；entitlement 由 `build.sh` 簽入（§9.1），不在執行期另查 | hard | 4 |
| 5 | 系統聲音 RMS | **兩段式（D19）**，時段判定皆為「任一 0.5 秒時段峰值 > -60 dBFS」（`d2:23-27`）：(a) 對**目標視窗**的 3 秒 probe stream（與正式錄製同一組設定，`excludesCurrentProcessAudio=true`；與第 6、12 項共用同一條），**不播測試音**，有聲即 pass；(b) (a) 沒過時才另開 `SCContentFilter(display:excludingWindows: [])` 的 3 秒 probe stream，期間由錄製器 spawn 子程序 `/usr/bin/afplay /System/Library/Sounds/Ping.aiff` 兩次（`d2:19`）：有聲 → 第 5 項 **warn**（訊息：會議 app 目前沒有聲音；擷取權限正常；開錄後若持續靜音 15 秒會告警），照常開錄；仍無聲 → hard fail，訊息只給授權補救：重新授權螢幕錄製；若剛授權，完全結束 MeetingRecorder 再重開（**D21**：ScreenCaptureKit 擷取系統聲音在系統輸出靜音之前，輸出靜音不影響錄音——t6：靜音＋影片播放 (a) -11.8 dBFS pass；靜音＋影片暫停 (a) -∞、(b) 測試音 -17.4 dBFS → warn。所以「靜音＋會議 app 沒聲音」走的是 warn，`.fail` 只可能是擷取權限問題，前一版「取消輸出靜音、把音量調大」的補救拿掉）。由 Core `systemAudioCheck`（`spec.md §3.4`）決定結果，warn 以 `PreflightResult.warnOnly` 表達（JSON 的 `severity` 為 `warn`、`code` 0），分級表本身不變 | hard（單筆可降為 warn，D19） | 4 |
| 6 | 麥克風 RMS | 第 5 項 (a) 那條 probe stream 的 `.microphone` output，同一判定（D19 不影響本項）；`record.sh` 在 preflight 前提示「請說一句話」 | hard | 4 |
| 7 | 磁碟空間（含目標目錄可寫） | 目標根目錄可用空間 ≥ `minFreeBytes`（由 `_record_estimate.py` 算）；並在 `tracks/` 建／刪一個探測檔（app 寫 `~/Documents` 下需要「文件」TCC，失敗模式同樣是靜默的） | hard | 4 |
| 8 | 目標視窗存在 | `resolveWindow`（`spec.md §3.8.8`）：windowID 在 `SCShareableContent.windows` 裡；找不到時，若 `record.sh` 帶了 `--window-bundle`／`--window-title`，在通過篩選的視窗中以 (bundleID, 標題) **唯一**認回（實測 windowID 會變，`wfd:33`）；認不回或不唯一 → fail | hard | 3 |
| 9 | 場次撞名 | `<場次>/錄音/` 已有音源檔或 `tracks/` 已存在 | hard | 2 |
| 10 | 電源 | 用電池且電量 < 20% → warn；其他情形 pass | warn | — |
| 11 | 已有錄製在跑 | `record.pid` 存在且 `kill -0` 成功 | hard | 2 |
| 12 | 視窗是否最小化（t6 第三輪：含幕前調度提醒） | 沒有公開 API（`req:293`）；probe stream 3 秒內只收到 `suspended` 或完全沒有 `.screen` 幀 → warn「會議視窗可能被最小化」。**t6 第三輪（發現 I）**：另以 `CFPreferencesCopyAppValue("GloballyEnabled", "com.apple.WindowManager")` 只讀幕前調度是否開啟，開啟 → 同一項 warn，訊息為 Core `stageManagerNotice(globallyEnabled: true)`（兩者同時成立時以「；」串接）；開錄時同一句寫進 `record.log`（§7.1〈幕前調度〉） | **warn**（D1） | — |
| 13 | Apple Events（Chrome 會議分頁標記） | `AEDeterminePermissionToAutomateTarget`（`askUserIfNeeded: false`，不跳框）：`authorized` → pass；沒授權、未決定、Chrome 沒開、錯誤 → warn「會議分頁不會標記，不影響錄製」＋開啟路徑（`spec.md §3.8.4`） | **warn**（D16，永不 hard） | — |

`req:197`「任何 fail 一律不開錄」依 D1 改為「任何 hard fail 不開錄」，記在 `spec.md §6`。

---

## 7. 擷取與分段

### 7.1 串流設定（`req:173-185`，第 0 階段實測與 D8 修正）

`SCContentFilter(desktopIndependentWindow:)`、`onScreenWindowsOnly=false`（`main.swift:102-104`）、`scalesToFit=true`、`minimumFrameInterval=1/60`、`pixelFormat=420v`、`capturesAudio=true`、`sampleRate=48000`、`channelCount=2`、`captureMicrophone=true`、`microphoneCaptureDeviceID=nil`（預設輸入變更時改設新裝置 UID，§7.3）、`excludesCurrentProcessAudio=true`、容器 `.mov`、`videoCodecType=.h264`。開錄當下把實際設定值寫進 `record.meta.json.config`，驗收直接讀這份快照。

**錄到的系統聲音範圍（D19，`spec.md §4.3.5`）**：單一視窗 filter 的 `capturesAudio` 只收**擁有該視窗的 app** 的聲音（t6 實機：Chrome 播影片時對該 Chrome 視窗 -10.2 dBFS、同時對終端機視窗 -∞）。所以錄 Chrome 裡的會議時，同一個 Chrome 所有分頁的聲音都會進來，別的 app 的通知音、音樂不會；麥克風（`captureMicrophone`）不受 filter 影響、照常錄。這是想要的行為（別的 app 的雜音不進會議錄音），不改用 display filter；display filter 只在 preflight 第 5 項 (b) 用來驗擷取權限（§6）。端到端量測（`spec.md §4.9`、`§4.10`）的系統聲音來源要由被錄的 app 播放。

**畫布＝當下會議視窗的像素大小（D8，取代原本鎖顯示器 `displayPixelSize()` 的做法）**：
- 量法：`pixel = evenPixelSize(points: SCWindow.frame.size, scale: filter.pointPixelScale)`——point × 比例後各自向下取偶數（H.264 要求偶數寬高）。`SCWindow.frame` 每次從 `SCShareableContent` 重新抓（`main.swift:102-104` 的同一呼叫），不沿用開錄時的快照。`evenPixelSize` 是 Core 純函式（`spec.md §3.4`），可單元測試。
- **換段當下同步讀一次**（t6 第二輪改寫，缺陷 A）：`RecordingSession.startNewSegment` 在錄製器的序列佇列上、建新 writer 之前，**同步**呼叫 `windowPointSize(windowID)` 取會議視窗目前的大小（point），交 Core `nextSegmentSize(windowPoints:scale:previous:)`（`spec.md §3.4`、`§4.3.6`）決定新段尺寸：讀到就套用（`evenPixelSize`），讀不到（視窗被關掉、寬高 ≤ 0）沿用上一段。`windowPointSize` 是 `RecordingSession` 的一個可替換屬性（型別 `(UInt32) -> CGSize?`），預設實作以 `CFArrayCreate` 裝 windowID 的 raw pointer，呼叫 `CGWindowListCreateDescriptionFromArray` 讀 `kCGWindowBounds`（`CGRect(dictionaryRepresentation:)`）——單一視窗約 0.16 ms、不觸發 TCC（只讀 bounds，不讀標題），不會拖慢換段。新尺寸與上一段不同就呼叫 `stream.updateConfiguration(新 config)`（不等完成），新 writer 直接以新尺寸開檔，video input 設 `AVVideoScalingModeKey = AVVideoScalingModeResizeAspect`——`updateConfiguration` 生效前還在送的舊尺寸幀（含換段時重新打戳的那一幀）等比縮進新畫布、留黑邊、不裁切。每段的 writer 尺寸寫進 `manifest.json.segments[i].width／height`，一個檔從頭到尾只有一種尺寸。
  - **前一版的做法與 t6 缺陷 A 的根因**（`t6-rca-ABE.md`〈A〉，信心 0.6）：前一版在邊界前 1 秒以 host clock 計時器呼叫 `SCShareableContent`（`onScreenWindowsOnly: false`，約 1000 個視窗）非同步重抓尺寸並暫存在 `pendingSize`。實機上這個查詢常晚於邊界才回來，或丟例外被 `try?` 吞掉；換段時 `pendingSize` 被清掉，晚回來的值落到下一段，`sizeQuery?.cancel()` 也取消不了已經在跑的 `Task`——結果是縮放「慢一段才生效」（t6：約 1:10 縮小，120 秒開的 seg-0003 仍是 2992×1876，180 秒的 seg-0004 才是 2770×1736）。時鐘基準本身沒問題。本輪刪除 `pendingSize`、`sizeQuery`、`scheduleSizeQuery`，不再有任何非同步尺寸查詢。
  - **SCWindow 與 CGWindow 的大小同一把尺**：`SCWindow.frame` 與 `kCGWindowBounds` 都是全域座標的 point，乘上 `filter.pointPixelScale` 得像素；開錄時的第一段仍以 preflight 取得的 `SCWindow.frame` 為準（開錄前已經有了，不必另讀）。
- 段內視窗被縮放：`scalesToFit=true` 讓內容等比縮進該段固定的畫布（不裁切、留邊），在**縮放完成後的第一個邊界**換成新尺寸（≤ 60 秒）。
- 視窗在換段時讀不到（被關掉）：沿用上一段尺寸，`warnings[]` 不另加（`window_exists` 只在 preflight 判）。
- **可行性未實測**：`AVVideoScalingModeKey` 對尺寸不同的 pixel buffer 是否照預期等比縮放、`updateConfiguration` 換尺寸需要幾幀才生效，都沒有本機數據。量法：test 段量測閘門（`spec.md §4.3.4`）在錄製中把視窗縮小再放大，各跨一次換段，用 `ffprobe -select_streams v:0 -show_entries stream=width,height` 逐段比對 `manifest.json.segments[i]` 與當時的視窗像素尺寸；空隙照 §7.2 一起量。不過時以 `needs_decision` 回報，退回選項：(1) 每段仍照開錄時的尺寸（只靠 `scalesToFit` 留邊）；(2) 尺寸不符的幀丟棄並計數，直到新尺寸的幀到達（新段開頭可能短暫沒有畫面，由 finalize 以前一幀補，§7.4）。
- finalize 統一尺寸：輸出畫布＝(各段寬的最大值, 各段高的最大值)，每段**不縮放**，只以 `pad` 置中補黑邊（等比、不裁切，像素保留原解析度），細節見 §7.4。

**幕前調度（Stage Manager）與縮圖（t6 第三輪，發現 I）**：
- **事實**（`t6-results.md`「t6 第二輪重測」第 6 項，t6r2-HFP 場次）：使用者開著幕前調度，被錄的 ffplay 視窗不在目前舞台時被縮成左側縮圖 105×99 pt；SCK 單視窗擷取送來的內容是縮圖尺寸（段落 210×198 px），換段時讀的 `kCGWindowBounds` 也是縮圖尺寸，錄製器照 §4.3.4（spec）跟隨，錄成縮圖解析度，中間回到舞台的那一段才是 1280×776。關掉幕前調度後的 t6r2-HFP2 場次全程 2560×1496。
- **查證（不碰 TCC：只讀 `defaults`、`CGWindowListCopyWindowInfo`，不呼叫 SCK）**：(1) `defaults read com.apple.WindowManager GloballyEnabled` 可讀，本機目前為 0（使用者為測試已關閉；另有 `GloballyEnabledEver = 1`）；讀這個值不需任何授權，App 內可用 `CFPreferencesCopyAppValue` 讀同一個值。(2) `kCGWindowBounds` 回的是 WindowServer 目前畫在螢幕上的框；幕前調度把背景視窗以變形（transform）畫成縮圖，bounds 跟著變小——t6 實測與 `SCWindow.frame` 同為縮圖尺寸。CGWindow 字典沒有「原始（未縮）尺寸」欄位；SCK 也沒有公開 API 取得未變形的內容（單視窗擷取拿到的就是縮圖的像素）。(3) 要親眼看縮圖狀態下的值必須開啟幕前調度，那是改使用者系統設定，本輪不做；結論以 t6 實測為準（信心 0.7：「SCK 內容是縮圖」由段落像素尺寸與畫面直接證實，「無任何公開 API 拿得到原始內容」是查無而非證偽）。
- **選項與代價**：
  | 選項 | 做法 | 代價 |
  |---|---|---|
  | **A（定案）** preflight 提醒 | preflight 只讀 `GloballyEnabled`，開啟時第 12 項 warn、照常開錄，`record.log` 記一行；SKILL.md／README 各一句 | 改動最小（一個 Core 純函式＋preflight 一處＋文件），不改系統設定、不改錄製行為；使用者忽略提醒時仍會錄到縮圖（`spec.md §7` 疑慮 31） |
  | B 尺寸只增不減 | 錄製中尺寸取「見過的最大尺寸」，縮圖期間 `scalesToFit` 放大填滿 | 畫質仍是縮圖（只是放大成模糊的大畫面）、檔案變大；改變 §4.3.4 對「使用者主動縮小視窗」的語意（縮小後不再跟隨）；要改 `nextSegmentSize` 與既有測試 |
  | C 開錄時關閉幕前調度 | 錄製器寫 `GloballyEnabled = false`、錄完還原 | 改使用者系統設定，違反 intent §2「不改使用者的系統設定」；當機時還原不了；寫別的 app 的 defaults 是否立即生效也未驗 |
- **定案 A**（`spec.md §4.2.12`、§6 第 63 條）：在 preflight 的第 12 項（「會議視窗可能看不到完整畫面」這一類）附帶提醒，不加第 14 項，`PreflightItem` 與既有結果 JSON 不變。錄製中**不**偵測縮圖、不改尺寸跟隨。

### 7.2 分段換段（D3：60 秒；D20：自管 `AVAssetWriter`）

做法的取捨與 t6 實機結果見 `adr/adr-segment-writer.md`。正式錄製**不再使用 `SCRecordingOutput`**（`probe` 子指令保留它）；`Capture/SegmentWriter.swift`（新增）包一個段落的 `AVAssetWriter`，`RecordingSession` 負責分流與換段。

**時間基準**：
- **sample 時鐘**：SCK 送來的 `.screen`、`.audio`、`.microphone` sample 的 PTS 都在 host clock 上（§1）。所有 writer 的 session 時間軸**直接用 sample 的 PTS**，不另外換算；三路之間的對齊因此只靠同一個時鐘，不靠任何回呼。
- **manifest 的秒數**：沿用現行定義「自 `t0` 起算」，`t0`＝`startCapture` 前一刻的 host clock（`RecordingSession.swift:5`）。PTS 換成 manifest 秒數＝`PTS.seconds − t0`，與 `levels`、`blackIntervals`、`deviceEvents` 同一把尺。錄製器在收到第一個 sample 時把 `PTS − 當下 host clock` 寫進 `record.log`（應在 ±1 秒內）；超出時記一行警告，供 t6 判讀，不改行為。

**writer 設定（每段一個 `AVAssetWriter(outputURL: seg-NNNN.mov, fileType: .mov)`）**：
| input（順序固定） | 輸出設定 | 說明 |
|---|---|---|
| 0：video | `AVVideoCodecType.h264`、寬高＝該段的 `evenPixelSize`、`AVVideoScalingModeKey = AVVideoScalingModeResizeAspect`、`AVVideoCompressionPropertiesKey`：`AVVideoProfileLevelKey = AVVideoProfileLevelH264HighAutoLevel`、`AVVideoAverageBitRateKey = segmentVideoBitRate(width:height:)`（`spec.md §3.4`；2992×1876 為 7,016,240 b/s）、`AVVideoExpectedSourceFrameRateKey = 60`、`AVVideoMaxKeyFrameIntervalDurationKey = 2`、`AVVideoAllowFrameReorderingKey = false` | fps 上限仍由 SCK 的 `minimumFrameInterval = 1/60` 決定（§7.1），writer 不重新取樣影格。不開 B-frame：dts 與 pts 一致、單調遞增，finalize 串接時少一個出錯點（§7.4）。位元率公式讓 2992×1876 每分鐘約 52.6 MB，加兩條音軌約 55 MB，與磁碟估算的 56 MB／分鐘一致（§5 Q7） |
| 1：系統聲音 | AAC（`kAudioFormatMPEG4AAC`）、48,000 Hz、2 聲道、192 kb/s | 輸入是 SCK 的 LPCM（格式以每個緩衝自己的 ASBD 為準，§7.5） |
| 2：麥克風 | AAC、48,000 Hz、1 聲道、128 kb/s | 同上 |

三個 input 都 `expectsMediaDataInRealTime = true`；`writer.movieFragmentInterval = 10 秒`、`overallDurationHint = 60 秒`、`shouldOptimizeForNetworkUse = false`。某個 input `isReadyForMoreMediaData == false` 時**丟掉該 sample、不阻塞擷取佇列**，每段的丟棄數寫進 `record.log`。

**第一段**：`startCapture` 成功後，**第一個到達的 sample（任一路）**的 PTS 就是 `B_1`；此時建 writer、`startWriting()`、`startSession(atSourceTime: B_1)`，`startedAt_1 = B_1 − t0`、`requestedAt_1 = 0`。視訊可能比音訊晚幾十毫秒才有第一幀，該段影片軌就從第一幀開始；finalize 以第一幀往前補（§7.4 第 3 步）。

**換段（每 60 秒）**：
1. 下一個邊界 `B_{i+1} = B_i + 60 秒`（sample 時鐘，不是 host 計時器；格式變更時提前，§7.5）。（前一版在邊界前 1 秒觸發非同步尺寸查詢，t6 第二輪刪除，§7.1。）
2. **第一個越過 `B_{i+1}` 的 sample（任一路）到達時**切換——「越過」＝PTS ≥ `B_{i+1}`，**或**音訊緩衝跨過邊界（PTS < `B_{i+1}` < PTS＋duration；m3 實作，t6 第二輪追認：讓這個緩衝依第 4 步兩段都寫，不會只進舊段而在新段開頭留下約 20 ms 空隙）：記 `requestedAt_{i+1}`＝當下 host clock − `t0`；以換段當下同步讀到的視窗尺寸（§7.1）建新 writer、`startWriting()`、`startSession(atSourceTime: B_{i+1})`；`startedAt_{i+1} = B_{i+1} − t0`。若尺寸改變，同時呼叫 `updateConfiguration`（不等完成）。
3. **新段第一個視訊 sample**：若觸發換段的正是一個 PTS 恰等於 `B_{i+1}` 的 complete 視訊 sample，直接寫它；否則把最後一個 complete 幀的影像以 `B_{i+1}` 重新打戳（`CMSampleBufferCreateCopyWithNewTiming` 或以同一 `CVPixelBuffer` 重建 sample）寫進新 writer 的 video input。這一幀就是邊界當下螢幕上的畫面；之後真實幀照常寫入。同一個 writer 的視訊 sample PTS 必須嚴格遞增，PTS ≤ 上一個已寫入視訊 PTS 的 sample 丟掉並計數（`AVAssetWriterInput` 不收非遞增的 PTS）。錄製以來還沒收過任何 complete 幀（例如視窗一開始就最小化）時略過，該段影片軌從第一個真實幀開始。
4. **分流**：之後每個 sample 以 `routeSample(start:end:boundary: B_{i+1})`（`spec.md §3.4`）決定去向（判定順序：start ≥ 邊界 → `.new`；否則 end ≤ 邊界 → `.old`；否則 `.both`；t6 第二輪把 `spec.md §3.4` 的註解更正成這個順序）——視訊以 `end = start` 呼叫；音訊的 `end = PTS + duration`。`.old` 寫舊 writer、`.new` 寫新 writer、`.both`（跨邊界的音訊緩衝）兩邊都寫：舊 writer 的 `endSession(atSourceTime: B_{i+1})` 裁掉邊界之後的部分，新 writer 的 session 起點裁掉邊界之前的部分，所以呈現時間上**無空隙、不重疊**。舊 writer 只收 PTS < 邊界的 sample；同一路的 sample 依 PTS 順序到達，所以某一路一旦出現 PTS ≥ 邊界的 sample，之後不會再有屬於舊段的 sample。
5. **舊 writer 收尾（非同步，切換不等它）**：舊 writer 的三個 input 都已看到 PTS ≥ `B_{i+1}` 的 sample，或切換後滿 1 秒（host clock），兩者先到者 → `endSession(atSourceTime: B_{i+1})` → 三個 input `markAsFinished()` → `finishWriting { … }`。完成回呼裡 `status == .completed` → 記 `finishedAt_i`＝當下 host clock − `t0`、`record.status.json.segments` 加一、log「✓ seg-NNNN.mov 收尾」；`status == .failed` → 依下面〈writer 失敗〉。
6. 換段時不碰 `SCStream`（除非尺寸改變要 `updateConfiguration`）：stream 從 `startCapture` 到停止只有一條、不中斷。

**writer 失敗**：`append` 回 `false`、`startWriting()` 回 `false`、或 `finishWriting` 完成時 `status == .failed`，都視為該段 writer 失敗：
- `record.log` 記 `✗ seg-NNNN.mov 寫檔失敗：<writer.error>`；`warnings[]` 加告警類 `segment_write_failed`（`spec.md §3.4` 新增的 `WarningKind`，menu bar 進告警態，§3.4.1 M7）；`hadError = true`——錄製結束時 `record.status.json.code = 5`、訊息「錄製中出過錯（見 record.log），已收尾；段落保留」（現行語意，`RecordingSession.swift` 的 `complete(finalizeCode:)`）。
- 該段檔案**不刪**（可能可以讀到失敗前最後一個 fragment），`finishedAt` 維持 `null`；finalize 照 §7.4 第 1 步判斷能不能用。
- 錄製中途的 writer 失敗 → **立刻提前換段**（以下一個 sample 的 PTS 當邊界開新段），錄製繼續；新段若在 10 秒內又失敗（或新 writer 連 `startWriting()` 都失敗）→ 以 `forced = (5, "段落連續寫檔失敗，已停止並收尾；已落盤段落保留")` 走優雅停止（§7.4），不無限重試。
- **最終訊息**（t6 第二輪，缺陷 D）：錄製結束時 `record.status.json` 的 `phase`／`code`／`message` 與 `record.log` 最後一行一律由 Core `completionOutcome(finalizeCode:forcedCode:forcedMessage:hadError:sessionPath:)`（`spec.md §3.4`、`§4.4.9`）決定。有停止原因（`forced`，例如「段落連續寫檔失敗」「磁碟可用空間低於 2 GB」「擷取串流中斷」）時，即使 finalize 也失敗，訊息仍以停止原因開頭、收尾失敗附在其後——t6 §4.4.7 實測：`tracks/` 仍唯讀時 finalize 必然回 5，前一版 `complete(finalizeCode:)` 先判 `rc != 0`，把「段落連續寫檔失敗」整句蓋掉，使用者只看到「收尾失敗」。

**當機（`kill -9`、斷電）最多丟 1 段的保證**（t6 第二輪改寫，缺陷 E／D22）：
- 已收尾的段落是完整的一般 `.mov`，不受影響。
- 正在寫的段落與（剛換段、還在收尾中的）舊段落，靠 `movieFragmentInterval = 10 秒` 把 10 秒前的內容寫成完整 fragment；ffmpeg 讀得到最後一個完整 fragment 為止。最壞情形是兩個 writer 各丟最後未滿 10 秒的 fragment，合計 < 20 秒 < 1 段（60 秒），`spec.md §4.8.4` 以 21 秒判。
- **t6 實測不成立與根因**（`t6-rca-ABE.md`〈E〉，信心 0.85）：`kill -9` 後 seg-0002.mov 只有 `ftyp`、`wide`、`mdat`（size 0、延伸到檔尾），全檔沒有 `moov`／`moof`／`mvex`。`AVAssetWriter` 要**所有軌**的 sample 都越過下一個 fragment 邊界才寫出 fragment；會議視窗靜止時 SCK 的 `.screen` 只送 `idle`（沒有 image buffer，§7.2 不寫），影片軌停在最後一個 complete 幀不前進，於是整段一直沒有 fragment。repo 外合成重現：畫面靜止 → 讀不到；畫面持續變化 → 20.1 秒內讀得到；畫面靜止但每 1 秒重送最後一幀 → 20.06 秒內讀得到。`initialMovieFragmentInterval`、改 `.mp4`、`overallDurationHint` 都無效。
- **影片心跳**（修法，信心 0.8）：`.screen` 收到 `idle` 且 PTS 有效時，在錄製器的序列佇列上呼叫 `videoHeartbeat(pts)`：若 `shouldEmitVideoHeartbeat(samplePTS: pts, lastVideoPTS: 目前段落最後一個已寫入的視訊 PTS, hasLastFrame: 有最後一個 complete 幀, interval: videoHeartbeatSeconds)`（`spec.md §3.4`、`§4.4.10`；`videoHeartbeatSeconds = 1.0` 定義在 `Capture/`）為 true，就把最後一個 complete 幀以 `retimedVideoSample(_, pts:)` 重新打戳成 idle 的 PTS，走與一般視訊 sample 相同的路（停止點、換段判斷、`routeSample` 分流、PTS 嚴格遞增檢查）寫入。重送的幀**不更新** `lastFrame`（之後的換段首幀與心跳仍以真實的最後一個 complete 幀為準）、不計入 `frameStatus.complete`。代價：靜止畫面時每秒多一幀（H.264 對重複畫面的位元數很小），fps 尖峰量測（`spec.md §4.3.3`）不受影響。
- **殘留風險**（`spec.md §7` 疑慮 27）：(a) 視窗最小化時 SCK 只送 `suspended`、沒有 `idle`，心跳不會發；(b) 會議 app 沒聲音時 SCK 不送系統聲音緩衝，系統聲音軌一樣不前進（t6 2254 場次 43–178.5 秒沒有系統聲音緩衝），影片心跳補不到這一路。t6 第二輪重測 §4.8.4 時另記一次「會議 app 沒聲音」的結果。
- **修不好時**（D22）：實機 `kill -9` 仍讀不到正在寫的段落 → 以 `needs_decision` 回報，選項之一是把 `spec.md §4.8.4` 放寬為「當機最多丟 1 段（60 秒）」（退化保證：丟正在寫的那一段；若當機落在換段後舊段收尾完成前，實測約 1 秒內，舊段也可能丟）。
- 使用者文件維持「最後一段未收尾的 1 分鐘會丟」（上限說法，`spec.md §4.8.3`）。

**空隙量法（intent §4 要求說明；D20 後的定義）**：
- 以**音訊軌**長度量，不用影片軌。段落有兩條音軌時取**兩條的 stream duration 較長者**為 `audioDuration_i`（finalize 寫回 manifest）。
- 第 i 個邊界的空隙 `g_i = startedAt_{i+1} − startedAt_i − audioDuration_i`（公式不變，Core `boundaryGaps`）。D20 的做法下 `startedAt_{i+1} − startedAt_i` 恰為 60 秒（或格式變更時的實際段長），`audioDuration_i` 由 `endSession` 裁成同一長度，`g_i` 預期只剩 AAC 封包邊界的誤差（± 約 21 ms，1024 樣本／48 kHz），可能是負值。
- **單一邊界門檻**：`max(|g_i|) < 0.5 秒`（`req:201`；D3「空隙門檻沿用 0.5 秒」）。取絕對值是因為負值代表兩段重疊（同一段聲音出現兩次），也要擋。
- **累積損失**：`Σ g_i` 記進 `manifest.json.gapStats.total`，並與 `wallClock − Σ audioDuration_i` 互相核對（`req:268`）。3 分鐘端到端驗收照 `req:268` 字面要求 `Σ g_i < 0.5 秒`；長場次只判單一邊界、累積值只報不判。
- **段落確實收尾**（D20 新增，t6 的失敗模式就是「每段都沒收尾」）：除了錄製結束時最後一段以外，每段的 `finishedAt` 都不得是 `null`，且 `finishedAt_i − startedAt_{i+1} < 5 秒`（舊 writer 在換段後 5 秒內收尾完成）；最後一段在正常 `stop` 時也要非 `null`（§7.4）。

**量測閘門仍在 test 段（t6）**：理由同前（簽章換身分後 TCC 要使用者在場重給；量法要用 finalize 與 `e2e_check.py`）。t6 中途修正輪實作完成、重新安裝後，閘門重跑：(a) 3 分鐘錄製的空隙與收尾（`spec.md §4.4.3`）；(b) 靜止視窗跨過一次換段，第二段應有 video stream（`§4.4.4`，D20 後改為必驗）；(c) 錄製中縮放視窗（`§4.3.4`，D8）。(a) 或 (c) 不過，以 `needs_decision` 回報，**不自行換做法**。

### 7.3 監看（從同一批 sample 算數值，不另寫分路音檔）

| 監看 | 規則 | 依據 |
|---|---|---|
| 黑畫面 | 每秒抽一幀算 64 點非黑比例（`main.swift:239-265` 的函式移進 Core）；連續 5 秒 < 0.01 → 開一個黑畫面區間，恢復時關閉；區間寫進 `manifest.json.blackIntervals`，只告警不改行為 | `req:189-191` |
| suspended | 連續 5 秒只收到 `suspended` → `warnings[]` 加 `suspended` | `req:293` |
| 靜音 | 系統聲音、麥克風**分別**算 RMS，經 `PeakWindow`（0.5 秒時段峰值）收斂後餵 `SilenceDetector`；任一路連續 15 秒 < -60 dBFS → `warnings[]` 加 `silence_system`／`silence_mic`。**15 秒是告警門檻，不是裝置切換的驗收門檻**（切換驗收是每次 < 3 秒，D10，`spec.md §4.9`） | `req:199` |
| 音量紀錄 | 兩路的 0.5 秒時段峰值寫進 `manifest.json.levels`（`null` 表示 -∞ 或該時段沒有任何緩衝），每段收尾時隨 manifest 原子重寫一次；只存數字，不存任何音訊 | D6／D10 的「每路中斷 < 3 秒」需要分路證據，混音音軌分不出是哪一路斷；`req:199`「只用於監看、不寫檔」解讀為不另寫分路音檔，記在 `spec.md §6` |
| 裝置變更 | Core Audio listener：`kAudioHardwarePropertyDefaultInputDevice`、`…DefaultOutputDevice`（只**讀**與監聽，程式裡不得出現 `AudioObjectSetPropertyData`——不改使用者的預設裝置，intent §2）；事件連同裝置 `uid`／`name`／`transport`（`kAudioDevicePropertyTransportType`：builtIn／bluetooth／bluetoothLE／usb／aggregate／virtual／unknown）寫 `record.meta.json.deviceEvents[]`；開錄當下的輸入、輸出裝置寫 `record.meta.json.devices`；預設輸入變更時以新預設裝置 UID 呼叫 `updateConfiguration`（SCK 是否自動跟隨未知，`req:292`） | `req:199`、`req:271` |
| 音訊格式變更 | 見 §7.5 | D6 |
| 磁碟 | 每 30 秒；可用空間 < 2 GB（2,000,000,000 bytes）→ 優雅停止，`phase=done` 但 `code=5`，`message` 說明。**t6 第三輪（缺陷 L）**：`PreflightRunner.availableBytes` 前一版對同一個 `URL` 物件重複 `resourceValues(forKeys:)`，Foundation 把第一次的值快取在該 `URL` 上，之後每 30 秒讀到的都是開錄時的值，永遠不會 < 2 GB（t6：sparse image 填到剩 1.71 GB，90 秒以上沒停；離線重現：同一 URL 寫入 300 MB 後仍回舊值）。修法：每次讀前以 `URL(fileURLWithPath: existingAncestor(url).path)` 新建 URL，並呼叫 `removeAllCachedResourceValues()`（兩者都做，任一即足以清快取）；`volumeAvailableCapacityForImportantUsage` ≤ 0 時退回 `volumeAvailableCapacity` 不變（sparse image 上前者回 0） | `req:199`；`spec.md §4.5.9` |

RMS 一律經 `CMSampleBuffer.withAudioBufferList` 取緩衝（`d2:34-39`）。靜音告警的對象是 §7.1 範圍內的系統聲音：會議 app 一直沒聲音時，15 秒後告警 `silence_system`（preflight 第 5 項 warn 的訊息會預告這件事）。

### 7.4 停止與 finalize

- `meeting record stop`：讀 `record.pid` → `kill -TERM` → 輪詢狀態檔直到 `phase ∈ {done, failed}`（逾時 = 錄製長度的 2 倍＋120 秒）。
- app 收到 SIGTERM（`DispatchSource.makeSignalSource`）、磁碟不足、串流中斷或段落連續寫檔失敗，都走同一條優雅停止（D20 改寫，最後一段的收尾）：
  1. `phase=stopping`；記停止點 `E`＝三路已收到的 sample **結束點**的最大值（視訊為 PTS，音訊為 PTS＋duration；m3 實作，t6 第二輪追認——用起點會把最後一個音訊緩衝裁掉）；之後 PTS ≥ `E` 的 sample 一律不寫；
  2. `stopCapture()`（等它回來，最多 10 秒）；再對三個 sample 佇列各送一個空的同步工作，確保已排進佇列的 sample 都處理完；
  3. 目前的段落若**完全沒有內容**（`E` 不晚於段落起點，或三路都沒寫進任何 sample），就 `cancelWriting()` 捨棄（會刪掉檔）並從 `manifest.json.segments` 移除，不當成寫檔失敗（m3 實作，t6 第二輪追認；例：剛換段就收到停止）；否則目前的 writer `endSession(atSourceTime: E)` → 三個 input `markAsFinished()` → `finishWriting`，等完成回呼（最多 10 秒）；同時等所有還在收尾中的舊 writer（各最多 10 秒）。全部到終態（completed／failed／逾時）才往下——finalize 不會讀到收尾到一半的段落。逾時或 failed 依 §7.2〈writer 失敗〉記 `segment_write_failed`、`hadError = true`（結束碼 5），段落保留；
  4. `phase=finalizing` → spawn `"<python3>" "<harness>/bin/_record_finalize.py" "<場次>"`（路徑取自 `record.defaults.json`；子程序的 TCC 責任程序是 app，可寫 `~/Documents`）→ 依 finalize 結束碼與停止原因，由 `completionOutcome`（§7.2〈writer 失敗〉的〈最終訊息〉）寫 `phase`／`code`／`message`：finalize 回 0 為 `done`、非 0 為 `failed`（`code` 5），有停止原因時訊息一律以停止原因開頭（t6 第二輪，缺陷 D）。
- `kill -9`、斷電：狀態檔停在 `recording`，`record.pid` 殘留；`meeting record status` 以 `kill -0` 判定為異常中止並提示 `meeting record finish <場次>`（exit 5）。

**`_record_finalize.py` 步驟**（全部先寫在 `tracks/.finalize/`，最後一步才碰 `錄音/` 第一層）。D7 定案「整支重新編碼補尾」，D8 定案「統一成同一尺寸」，兩者合成一次轉碼，做法是**逐段正規化再無損串接**（取捨見 `adr/adr-video-tail-pad.md`）：
1. 列出 `seg-*.mov`，以 `ffprobe` 篩掉無法讀的段，記下每段的寬高、影片軌長、各音軌長、音軌數、影片位元率。D20 後被 `kill -9` 中斷的段落是 fragment 檔，`ffprobe` 讀得到、但 stream／format 層可能沒有 duration：此時以最後一個封包的 `pts_time + duration_time` 當該軌長度；**只有完全讀不到任何可解碼封包的段才略過**（例如沒有 moov 的非 fragment 檔）；
2. 決定輸出參數：畫布 `W×H`＝(各段寬最大值, 各段高最大值)；影片位元率 `B`＝max(各段實測影片位元率) × 1.5，下限 8 Mb/s（`req:57` 舊錄檔 7,737 kb/s 為參考）；
3. **逐段正規化**成 `.finalize/norm-NNNN.mov`（D20 補強：**先把每段的時間戳正規化，再串接**；t6 實機段落 finalize 報 `non monotonically increasing dts`，`spec.md §4.6.14`）：
   - **t6 缺陷 3 的根因（spec-author 以 t6 保留段落的副本在 repo 外重現，2026-10-11）**：SCK 段落的影片軌是 VFR、`time_base=1/600`、`has_b_frames=2`、開頭 dts 為負（約 -0.98 秒）、平均約 4.7 fps。(a) 正規化時 `-fps_mode passthrough` 但沒指定編碼器時間基準，ffmpeg 依影格率猜測取時間基準，原本相隔約 0.1 秒的影格被兩兩擠到相隔 1/90000 秒（第 1 段 285 幀中 114 個間隔 < 10 ms）；改用 `-fps_mode vfr` 會改成丟掉 111 幀，也不行。(b) 第 4 步的完整解碼檢查 `ffmpeg -v error -i video.mov -f null -` 對**任何** VFR 輸入都會由 null muxer 報 `non monotonically increasing dts`——連 SCK 原始段落本身都會（98 行），而 finalize 把「stderr 非空」當失敗。兩處都加 `-enc_time_base demux`（編碼器沿用輸入 stream 的時間基準）後，4 段實機段落 finalize 回 0、輸出影片 dts 嚴格遞增、影格數不少；以 `spec.md §4.6.14` 的合成素材配方造的兩段也從 rc=5 變 0（同樣只在 repo 外驗證，repo 的程式未改）；
   - **時間戳**：以該段各軌的最早呈現時間（套用 edit list 之後的 `start_time`，可能是負值，例如 AAC priming）的最小值為原點 `O`，**所有軌同一個原點平移**（保留段內音影的相對位置）；影片比 `O` 晚開始時以第一幀往前補（`tpad=start_mode=clone`），音訊比 `O` 晚開始時前面補靜音（例 `aresample=48000:async=1:first_pts=0`）；影片編碼 `-fps_mode passthrough -enc_time_base demux`（不重新取樣影格、不丟幀、時間基準不變粗）；完全相同 PTS 的重複影格只留第一個；輸出**不加** `-avoid_negative_ts make_zero`（t6 第二輪追認 m4：加了以後 AAC priming 的 1024 樣本不再被 edit list 隱藏，每段多出約 21 ms 的音訊、影片跟著平移 21 ms，且讓既有 `spec.md §4.6.10` 的不帶參數解碼檢查報錯；不加時 mov muxer 以 edit list 處理負時間戳，各軌 `start_time` 已在 [0, 0.05] 秒內）。**正規化後必須成立**：每條軌 `start_time` 在 [0, 0.05] 秒內、影片封包 dts 嚴格遞增、影格數＝輸入影格數減去被丟的重複 PTS 數（補尾時可多）、音訊軌長度（封包算）與該段長度（`O` 到最晚一軌結束）差 < 50 ms、**影片軌長度以「最後一幀的 PTS」計**與該段長度差 < 50 ms（t6 第二輪；m4 實作原為「stream 層長度與最後一幀 PTS＋1/連結影格率取大者、容差 50 ms＋一幀」，那一幀的放寬是為了遷就下面的補尾上限，上限改掉後不再需要）；不成立即 `FinalizeError`（結束碼 5、段落保留）；
   - **混音**（D20：系統聲音與麥克風分兩軌錄、在這裡混成一軌）：段落有兩條音軌時，兩軌各自重取樣到 48 kHz 雙聲道後等權相加（`amix=inputs=2:duration=longest:normalize=0`，不做 1/2 衰減），再過限幅防爆音（例 `alimiter=limit=0.891:level=0:latency=1`，上限 -1 dBFS、不自動調整音量、補償 lookahead 延遲）；某一軌缺（只有一條音軌的舊段落，例如 t6 期間 `SCRecordingOutput` 錄的段落已是混好的單軌）→ 直接用那一軌；兩軌都沒有 → 補靜音；
   - 影片：`pad=W:H:(ow-iw)/2:(oh-ih)/2:black,setsar=1`（不縮放、不裁切）；**尾端**（t6 第二輪改寫，缺陷 B、F）：補尾上限 `cap = 段落長 − 5 ms`（**不再依連結影格率**）；最後一幀距 `cap` ≥ 0.01 秒（`TAIL_PAD_MIN`，m4 實作的 0.01 秒，前一版字面 0.1 秒）時，以 `tpad=stop_mode=clone` 複製最後一幀補到 `cap`（`tpad` 依解碼輸出連結的影格率補幀，必須接在 `setpts` 之前），補出的幀 PTS 落在 `cap` 前 0.01 秒內或之後的一律夾成 `cap`，再由 `select` 丟掉重複 PTS；**一律加 `setpts`**（沒有夾值或開頭往前延時為 `setpts=PTS`）；
     - **缺陷 B 的根因**（`t6-rca-ABE.md`〈B〉，信心 0.85）：`h264_videotoolbox` 在 `-fps_mode passthrough` 且濾鏡鏈裡**沒有** `setpts` 時，把最後一幀的長度記成 1/`av_guess_frame_rate`——`r_frame_rate` > 210 且平均影格率 < 70 時改取平均影格率（1650 場次 seg-0005：約 10.6 fps → 0.094 秒），正規化後影片軌長 15.284 秒對段落長 15.199 秒，超過容差 → rc 5。前一版只在「需要補尾或開頭往前延」時才加 `setpts`，而該段最後一幀距 `cap` 只有 7 ms（< 補尾門檻），剛好走到沒有 `setpts` 的分支；seg-0001～0004 都走補尾＋`setpts` 分支所以沒觸發。前一版程式註解「只在需要時才加 setpts：它會改掉影格長度，沒必要時不碰原始時間」是錯的推論——**有** `setpts` 時最後一幀反而是短的，本輪把該註解改成說明這個實測行為。不採「改 `link_fps` 放寬容差」：那會把真正的漂移藏起來。
     - **缺陷 F 的根因**（spec-author 以 2254 場次 8 段的複本在 repo 外重現，2026-10-12）：前一版 `cap = 段落長 − 1/連結影格率`，假設編碼器會把最後一幀記成 1/連結影格率長、正好補滿到段落結束；連結影格率取 `ffprobe` 的 `r_frame_rate`。稀疏的 VFR 段（靜止畫面只有少數幾幀）`r_frame_rate` 很低：seg-0008 只有 8 幀、`r_frame_rate` 4/3，`cap` 比段落結束早 0.75 秒；而有 `setpts` 時編碼後最後一幀的長度並不是 0.75 秒（norm-0008 的最後一個封包 0.375 秒、stream 層長度截在最後一幀 PTS 39.890 秒），串接後輸出最後一幀長 0.354 秒，影片在 307.060 秒結束，比音訊（307.456 秒）短 0.750 − 0.354 = 0.396 秒——正是 t6 量到的差。中間的段落也各短 1/連結影格率（seg-0002、0005：1/15 秒；seg-0004：12/193 秒；seg-0006：1/57 秒），但 concat demuxer 以每個檔的 format 長度（＝音訊長度）排下一段，缺口被前一幀的顯示時間吸收，只有**最後一段**的缺口留在結尾。**已排除的假設**：(1) 提前換段時新舊段重疊——各段 `startedAt` 與段長一致，各段正規化後影音起點都是 0，串接沒有位移；(2) 短段影片只有 1 幀（seg-0005）——正規化時已補成 18 幀、長度正確；(3) 心跳缺失——是背景（靜止畫面才會稀疏），但不是直接原因，加了心跳（約 1 fps）之後 `r_frame_rate` 只會更低，舊算法更糟；(4) 段落長的定義——`O` 到最晚一軌結束，與音訊長度一致。
     - **修法與驗證**：`cap` 改成 `段落長 − 5 ms`＋一律 `setpts`（本步）＋串接時把整支影片最後一個封包設為 1 tick（第 4 步）。repo 外以現行 `_record_finalize.py` 的複本驗證：2254 場次 rc 0、影片 307.428／音訊 307.456 秒（差 28 ms，前一版 396 ms）、影格數 3931 ≥ 前一版 3927；1650 場次 rc 0（前一版 rc 5）、255.202／255.232 秒（差 30 ms）；`spec.md §4.6.17` 素材前一版 rc 5、修後 rc 0（15.197／15.220）；`§4.6.18` 素材前一版差 521 ms、修後 26 ms。只改 `cap` 而不改第 4 步時，2254 場次的影片反而**長** 347 ms（最後一幀封包長 0.375 秒被串接沿用），兩處都要改；
   - 影片編碼：`-c:v h264_videotoolbox -profile:v high -b:v B -maxrate 2B -bufsize 4B`；`-fps_mode passthrough -enc_time_base demux`（保留原始影格時間，不改 fps；前一版少了 `-enc_time_base demux`，見上）；
   - 該段沒有 video stream（D20 後的新段落每段都有首幀，§7.2 換段第 3 步；這條留給舊段落與「錄製以來沒收過任何幀」的情形）：用前一段最後一幀（`-sseof -0.5 -frames:v 1` 抽出）`-loop 1 -t <音訊長>` 補成影片，再走同一組參數；第一段就沒有影片時用 `W×H` 黑畫面；
   - 音訊：混音後一律 48 kHz、`-ac 2`，**t6 第三輪（缺陷 J）起寫成 PCM（`-c:a pcm_s16le`），不在這一步編 AAC**；`-t` 以微秒精度（`{dur:.6f}`）截在段落長，PCM 沒有 priming 也沒有封包補零，解碼長度＝時間戳長度。HFP 讓各段的音訊格式可能不同（§7.5），統一後才能串接；AAC 編碼移到第 4 步、全片一次（`spec.md §6` 第 16、65 條）；
4. concat demuxer 串接全部 `norm-*.mov` 成 `.finalize/video.mov`：**影片 `-c:v copy`、音訊 `-c:a aac -b:a 256k`（t6 第三輪，缺陷 J：音訊在這裡一次編碼，不得 `-c copy`）**，影片加 `-bsf:v setts=duration=if(eq(NEXT_PTS\,NOPTS)\,1\,DURATION)`（t6 第二輪，缺陷 F：只把整支影片**最後一個**封包的長度設為 1 tick，讓影片軌在最後一幀的 PTS 結束；其他封包不動。`setts=duration=0` 無效——mov muxer 會自行估長度）（每段用同一編碼器、同一組參數、同一尺寸，SPS／PPS 一致；與 ADR 選項 C 的「混用 copy 與重編」不同），並以 `ffmpeg -v error -i video.mov -enc_time_base demux -f null -` 確認可完整解碼（D20 補強：加 `-enc_time_base demux`，否則 VFR 輸入一律誤報）、以 `ffprobe -show_entries packet=dts` 確認每條軌的 dts 嚴格遞增；
5. 從 `video.mov` 抽 `-ar 16000 -ac 1 -c:a pcm_s16le -f wav` 成 `.finalize/audio.wav.part`（第 4 步之後整條音軌只有開頭一個 AAC priming，由 edit list 正確略過，wav 長度與影片音訊軌時間戳一致，`spec.md §4.6.20` (ii)）；

   **缺陷 J（t6 第三輪）：串接後音訊每個段落邊界晚約 21–37 ms、逐段累積**
   - **現象**（t6r2-HFP2：同步測試源每 2 秒閃白 0.1 秒＋1 kHz 嗶聲；4 段：seg-0001 起點 0.049、seg-0002 60.049、seg-0003 71.492（HFP 格式變更提前換段）、seg-0004 131.492）：段內原始（只取系統聲音軌）「嗶聲 − 閃白」的中位數 seg-0001 30.8、seg-0002 32.7、seg-0003 23.5 ms；最終影片同一量法（`spec.md §4.9.3` 的帶通量法前身，1 ms 窗）0–60 s 中位 32.0、60–72 s 69.7、72 s 後 81.7 ms → 第 2 段起多 37 ms、第 3 段起多 58 ms。
   - **逐步拆解**（scratchpad 複本，`_record_finalize.py` 保留 `.finalize/`）：(1) `norm-0001`～`0003` 段內中位 32.0／32.7／23.5 ms——**正規化保住了同步**（含第一段音訊比影片晚 47 ms 開始、以 `aresample=async=1:first_pts=0` 前面補靜音；混音、`alimiter latency=1` 都沒有引入偏移）；(2) 偏移出現在第 4 步串接。最終影片的音訊封包在 60.032 s 有一個 `duration` 只有 1 樣本、旗標從 `KD_` 變成 `K__` 的封包——那是 `norm-0002` 的 AAC priming 封包（原本由 edit list 標成丟棄）；整支影片的影片軌 `start_time` 是 0.021（`norm-0001` 的 priming 讓 concat demuxer 把整支往後推 21 ms）。(3) 機制：concat demuxer `-c copy` 只搬封包，**每個檔的 edit list（開頭略過 1024 樣本 priming、結尾截掉最後一個 AAC 封包的補零）都丟了**；時間戳上各段影音同一個位移，但解碼器照樣輸出每個封包的 1024 樣本，所以解碼出來的音訊每個邊界多出「1024 樣本 priming（21.3 ms）＋前一段最後一個封包超出段落長的部分（0–21 ms；seg-0001 段落長 60.017 s → 最後封包多約 15 ms）」。預測第 2 段 +21.3＋15 ≈ 36 ms、第 3 段再 +21.3＋1 ≈ 58 ms，與實測 37、58 ms 相符。(4) 旁證：最終影片解碼樣本數 ÷ 48000＝133.952 s，音訊軌時間戳長 133.853 s，多 99 ms；2254 場次（8 段）多 235 ms——**逐段累積**，1 小時約 1.3–2.6 秒，`錄音/*.wav` 也由同一份音訊解出，逐字稿時間軸同樣偏晚。`spec.md §7` 疑慮 29（短段正規化後音訊多約 42 ms）是同一件事；疑慮 26（`g_1` 含音訊晚開始的時間）是 `gapStats` 的定義問題，與 J 無關、不受本修法影響。
   - **修法**：第 3 步音訊寫 PCM、第 4 步音訊在串接時一次編 AAC（影片仍 `-c:v copy`＋既有 `setts`）。PCM 的長度精確到樣本、沒有 priming，concat demuxer 以各檔 format 長度（＝段落長）接下一段時影音同步位移；整條音軌只有開頭一個 priming，由 mov muxer 的 edit list 處理。
   - **驗證**（scratchpad 複本，修前／修後同一支程式只差上述兩處）：t6r2-HFP2 各段時距中位數修前 32.0／69.7／81.7 ms → 修後 32.0／33.4／22.4 ms（與段內原始 30.8／32.7／23.5 ms 差 ≤ 1.2 ms）；以 `spec.md §4.9.3` 的新量法，修後最大 81 ms（修前 140 ms）。解碼長度 − 時間戳長度：HFP2 99 → 13 ms、2254 235 → 20 ms、1650 149 → 21 ms、t6r2-AE 45 → 2 ms、t6r2-E2 53 → 10 ms、t6r2-E3 41 → 19 ms。六場 `video_covers_audio` 修前差 26–30 ms、修後 5–9 ms，全部 PASS；`gap` 不變；`e2e_check.py --segment-writer` 其餘結果修前修後相同（2254 `no_aggregate`、AE／E2／E3 `segment_finished` 的已知 FAIL 不變）。合成素材（`spec.md §4.6.20` 的配方：4 段 10.017／3.3／7.0／5.013 秒）修前各段中位 6／16／53／93 ms（逐段累積、超過段內原始），修後 5／−11／−11／−11 ms（與原始段一致；−11 ms 是合成素材 30 fps 影格格點造成、原始段落本身就是 −12 ms）。
   - **不採**：(a) `-c copy` 串接後再以 `aresample=async=1` 修時間戳——priming 封包已失去丟棄旗標，修不回內容；(b) 用 `concat` 濾鏡全部重新解碼串接——影片也要重編一次，違反「逐段正規化、無損串接」（`adr/adr-video-tail-pad.md`）；(c) 每段 AAC 改用 `-c:a copy` 但先把 priming 去掉——mov／AAC 沒有不帶 priming 的編碼方式，結尾補零也去不掉。
   - **代價**：`norm-*.mov` 的音訊暫存由約 1.9 MB／分變成約 11.5 MB／分（`spec.md §7` 疑慮 32）；串接一步多一次音訊編碼（全片只有這一次，原本是每段各一次），時間可忽略。
   **缺陷 N（t6 第三輪後）：稀疏 VFR 段落補尾的複製幀讀不到**
   - **現象**：t6r3-e2e 0330 場次 finalize rc 5，正規化的長度檢查報影片軌比段落短；`norm-*.mov` 的 `stsz` 有補尾的複製幀，`ffprobe` 卻讀不到。
   - **根因**：正規化輸出的最後一個影片封包長度只有 1 tick，mov muxer 寫的 edit list（movie timescale 1/1000）在最後一幀的 PTS 就結束，最後一幀被標成丟棄；倒數第二幀剛好是關鍵幀時（`h264_videotoolbox` 沒指定 `-g` 時預設每 12 幀一個關鍵幀），mov demuxer 在 edit list 結束後遇到關鍵幀就停止建索引。
   - **修法**（`94f54d2`）：第 3 步以 `setts` bsf 把影片最後一個封包的長度設到段落結束（至少 1 tick）；兩個編碼器都改 `-g 100000 -bf 0`，關鍵幀以 `-force_key_frames expr:gte(t,n_forced*2)` 每 2 秒一個（VFR 也一致）；`cap` 往下對齊輸入 time_base 的 tick，`setpts` 用 `round(cap/TB)`；`check_norm()` 有補尾時確認補尾幀有可讀封包（容差 1 ms），否則明確報錯。回歸測試 `test_finalize.py` 的稀疏尾端配方（`_media.py` `sparse_tail`）。
   - **補尾的過近間隔**（`af91ec0`，test 段 verifier 抓到 §4.3.3 (ii) 在 0330 為 4 > 3）：`tpad` 第一個複製幀落在「最後一幀 PTS＋最後一幀長度」，舊程式只把 `cap` 前 10 ms 內的複製幀併進 `cap`，同一個邊界因此有 2 個 < 1/60 秒 − 1 ms 的間隔。改為：(1) 複製幀落在 `cap` 前 1/60 秒內就併進 `cap`（`CLONE_SNAP`；`grid_reaches_end` 仍用 10 ms）；(2) 最後一幀距 `cap` 不到 1/60 秒 − 1 ms 時不補尾（仍在 50 ms 容差內）；(3) `select` 去重時，複製幀距前一個留下的影格不到 1/60 秒 − 1 ms 就丟掉。只動複製幀，原始影格不動。回歸測試 `test_finalize.py::test_tail_pad_no_extra_close_interval`（三種情形，修前全紅）；9 場實機複本重新收尾，`fps_min_interval` 8 場 PASS（餘裕小：多場 (ii) 剛好等於上限，之後改 finalize 要特別注意）。

6. `os.replace` 影片到 `影片/<名> <ts>.mov`；寫 `manifest.json` 的 `gapStats`、各段 `audioDuration`（算法照 `spec.md §3.2`：封包算、略過 `D`／`C` 旗標、起點取 min(stream `start_time`, 第一個可解碼封包 pts)、各音軌取最大；**缺陷 F2**：`e2e_check.py` 的 `gap` 前一版用 stream 層 `duration` 量，與這裡寫回的 `gapStats` 不一致——2254、1650 場次複本重新收尾後分別是 0.181 對 0.224、0.117 對 0.181 秒，`gap` 判「與實測不符」FAIL；t6 第二輪讓 `e2e_check.py` 改用同一算法，`spec.md §4.6.19`）、`outputCanvas`、`outputVideoBitrate`；寫 `finalize.json`；
7. **最後** `os.replace(.finalize/audio.wav.part, 錄音/<名> <ts>.wav)`——`tracks/` 在 `錄音/` 底下，同一個檔案系統，rename 是原子的；**場次在這一刻才存在**，所以「場次存在」與「錄製完成」同一瞬間（`req:156`）在 finalize 期間也成立；
8. 清掉 `.finalize/` 裡的 `norm-*.mov`（finalize 自己的暫存）；`state_set` 等價：在 `.pipeline-state.json` 寫 `record: done`（`bin/_state.py` 無 stage 白名單，`research-code-contracts.md:46`）。

長場次的全片重編會讓 `record stop` 等比較久：`record stop` 每段正規化完成就印一行進度（`正規化 12/95`）。

冪等：`finalize.json` 存在、輸出兩檔都在、輸入段清單（檔名＋大小）相同 → 印「已完成」直接回 0，不重寫任何檔。

### 7.5 錄製中途的音訊格式變更（D6：藍牙 HFP）

情境：藍牙耳機的麥克風一被選為輸入，macOS 會把耳機切到 HFP，輸出取樣率可能在錄製中途從 48 kHz 掉到 16 或 24 kHz、聲道數變 1。錄製器的處理原則是**不假設格式固定，每個緩衝自己帶格式**：

| 環節 | 做法 |
|---|---|
| 偵測 | 每個 `.audio`／`.microphone` 緩衝以 `CMSampleBufferGetFormatDescription` → `CMAudioFormatDescriptionGetStreamBasicDescription` 讀出 `AudioFormat`（取樣率、聲道數、是否交錯、樣本型別）；與該路上一個緩衝不同 → `record.meta.json.audioFormatEvents[]` 追加 `{t, source, from, to}`，`warnings[]` 加紀錄類 `audio_format_change`（不轉告警態） |
| RMS | `rmsDBFS(sampleBuffer:)` 依**該緩衝自己的** ASBD 取樣：Float32 或 Int16、交錯或非交錯、任意聲道數；對所有聲道、所有 frame 一起算均方根。一律經 `CMSampleBuffer.withAudioBufferList` 取緩衝（`d2:34-39`）。不支援的樣本型別回 `nil`（記一次 log），不當成 -∞——避免把「讀不懂」誤判成「沒聲音」 |
| PeakWindow | 時段以緩衝的**呈現時間（PTS，秒）**切，不以樣本數切，所以取樣率、聲道數改變不影響 0.5 秒時段的邊界；每 0.5 秒由主機時鐘呼叫一次 `close(upTo:)` 收斂時段，**沒有收到任何緩衝的時段記為 -∞**——HFP 重新協商期間緩衝中斷會被算成中斷，不會被跳過 |
| SilenceDetector | 吃 PeakWindow 收斂後的時段峰值，不直接吃緩衝；所以格式變更本身不會造成誤報，真正的中斷 ≥ 15 秒才告警 |
| 麥克風跟隨 | 預設輸入變更 → 以新裝置 UID `updateConfiguration`（§7.3）；`SCStreamConfiguration.sampleRate／channelCount` 只約束系統聲音，麥克風路的格式以緩衝為準 |
| 落盤（D20 改寫） | 自管 `AVAssetWriter`（§7.2）。**某一路偵測到格式變更就提前換段**：以第一個新格式緩衝的 PTS 為邊界 `B_{i+1}`（其他路照 `routeSample` 分流），之後的 60 秒週期從這個新邊界重新起算；讓每段的每一路只有一種輸入格式，不賭 `AVAssetWriterInput` 能否在同一軌中途吃不同格式的 LPCM。換段本身無空隙（§7.2），所以提前換段沒有代價。同一路 1 秒內再變一次格式時不再提前換段（避免 HFP 協商抖動時連續開檔），該段可能混到兩種格式；寫入因此失敗就走 §7.2〈writer 失敗〉（提前換段、錄製繼續）。`AVAssetWriterInput` 能否把 16／24 kHz 單聲道 LPCM 轉成 48 kHz AAC 輸出**未實測**，由 `spec.md §4.9.3` 驗；不行時退回「每段的 AAC 輸出取樣率／聲道數跟隨該段開頭的輸入格式」（finalize 本來就會統一格式），以 `needs_decision` 回報 |
| finalize | 每段兩條音軌各自重取樣成 48 kHz 2 聲道後混成一軌（§7.4 第 3 步），不同段的格式差異在串接前消除 |

### 7.6 開錄：preflight 到正式 `startCapture`（t6 缺陷 4）

`start` 在同一個 process 裡先跑 preflight（會開、停 probe stream，第 5 項 (b) 還會再開一條 display filter 的 probe stream），通過後才建正式 stream。t6 有一次 preflight 13 項通過後，正式 `startCapture` 立刻失敗「無法開始音訊串流」、重開就好；當時輸入、輸出都是藍牙耳機。推測是 probe stream 剛停、音訊裝置（尤其藍牙在 A2DP／HFP 之間）還在釋放或重新協商。處理：

1. **等待**：preflight 最後一條 probe stream 的 `stopCapture()` 回來之後，等 `startCaptureSettleSeconds = 1.0` 秒才呼叫正式 `startCapture()`。1 秒的理由：macOS 切換音訊路由與藍牙 profile 的重新協商通常在 1 秒內完成（t6 的 HFP 情境 preflight 量麥克風時就已進 HFP，正式 stream 開不起來是釋放的時間差，不是重新配對）；這 1 秒對使用者是「按下開錄到開始錄」多 1 秒，可以接受。
2. **重試一次**：`startCapture()` 丟錯 → `record.log` 記 `⚠ startCapture 第一次失敗（<錯誤>），2 秒後重試`，丟掉這條 `SCStream`（`stopCapture` 忽略錯誤），等 `startCaptureRetryDelaySeconds = 2.0` 秒，用同一個 filter 與 config **重建** `SCStream`、重新掛三個 output 後再 `startCapture()` 一次。重建而不是對同一條 stream 再呼叫一次，是因為失敗過的 `SCStream` 狀態沒有文件保證。2 秒＝第一次等待的兩倍，涵蓋較慢的藍牙協商；只重試一次，避免真的沒授權或裝置壞掉時拖太久。
3. **仍失敗**：照現行行為回 `record.status.json` `phase=failed`、`code=5`，訊息「startCapture 失敗：<錯誤>」（`RecordingSession.swift` 的 `fail(code: 5, …)`，`spec.md §2.2` `record` 列的 5）。
4. writer 在第一個 sample 到達時才建（§7.2），所以失敗的那次嘗試**不會留下任何 `seg-*.mov`**；重試成功時 `t0` 以重試那次 `startCapture` 前一刻重新取。
5. 兩個常數定義在 `Capture/`（`spec.md §4.2.11` 以靜態檢查認它們）；不加旗標、不改 CLI。

---

## 8. 觸發層（第 2 階段）

| 機制 | 做法 | TCC 影響 |
|---|---|---|
| Shortcuts 全域快捷鍵 | 使用說明教使用者建一個捷徑，內容一行 `open -n -a MeetingRecorder --args quick-start`（`req:255`） | 無（不碰需授權 API） |
| `quick-start` | 讀 `record.defaults.json`（沒有 → 通知「先在終端機跑一次 meeting record」並結束，code 2）；場次名 `<HHMM> 會議`；視窗：`buildWindowRows` 的結果裡**恰好一個** ★ 列（`spec.md §3.8.2`）才自動選，否則通知「請用 meeting record 選視窗」並結束（code 3），**不猜**；quick-start 不跳 Apple Events 授權框，沒授權時 Chrome 會議分頁沒有 ★，通知要說明這一點。判斷邏輯是 Core 純函式 `quickStartDecision`（`spec.md §3.4`），可單元測試 | 錄製實例本身 |
| menu bar 常駐實例 | `--args menubar`：`LSUIElement`（`Info.plist:23-24` 已就位）、`NSStatusItem`，每秒讀狀態檔與 `kill -0 record.pid`，交給 Core 純函式 `menuBarModel` 算出圖示、狀態列文字與選單可用性（§8.2）；**單一實例**：啟動時先以 `acquireMenuBarLock` 取 `menubar.lock`，已被別的 menubar 實例持有就在建立 `NSStatusItem` 之前結束（D18，`spec.md §4.11.10`）；「開始錄製」＝ `open -n -a` 自己帶 `quick-start`；「停止錄製」＝ SIGTERM 給 `record.pid` | menu bar 實例自己不擷取 |
| app 內快捷鍵 | ⌃⌥⌘R；menu bar 實例用 Carbon `RegisterEventHotKey` 註冊，註冊失敗寫一行 `record.log`、選單照常可用（D18）；**禁用** `NSEvent.addGlobalMonitorForEvents`（要「輔助使用」授權，`req:255`） | 無 |

快捷鍵與 menu bar 都直接 `open` app，**不經 `meeting.sh`**，所以 §8.1 的 `./record` 撞名只發生在終端機與其他 session（例如 skill 透過 Bash 工具呼叫，沒有 tty）呼叫 `meeting.sh record …` 時。

### 8.1 `./record` 目錄撞名（D11）

原本 `meeting.sh record`（目前目錄下剛好有 `record/`）會走 `*)` 把 `record` 當會議根目錄跑 `prep`（`bin/meeting.sh:400-402`）；新增 `record)` 分支後同一行會變成錄製子指令。D11 定案**不默默選邊**，在 `meeting.sh` 的 `record)` 分支最前面判斷：

| 條件 | 行為 |
|---|---|
| 參數任何位置含 `--recorder` | 明確要錄製：不檢查 `./record`，照下方「層旗標拿掉」交給 `record.sh` |
| （所有情況）參數任何位置含 `--yes` | `--yes` 只用於下面兩列的判斷；交給 `record.sh` 前一律拿掉（`spec.md §2.4.1–2.4.2` 的「層旗標」、§6 第 28 條），`record.sh` 不認得也不需要它 |
| 目前目錄**沒有** `record` 目錄（`[[ ! -d record ]]`） | 照常交給 `record.sh` |
| 有 `record` 目錄，且 stdin 與 stderr 都是 tty，且參數裡沒有 `--yes` | 在 stderr 問：「目前目錄下有名為 record 的資料夾。要 1) 開始錄製 2) 把 ./record 當會議根目錄跑前處理？」；選 1 → 交給 `record.sh`；選 2 → `prep record`（與舊行為完全相同）；其他輸入或 EOF → 結束碼 2 |
| 有 `record` 目錄，但沒有人可問（stdin 或 stderr 不是 tty，或參數含 `--yes`） | 不做任何事，印出兩種明確寫法後結束碼 **2**：錄製用 `meeting.sh record --recorder …`；前處理用 `meeting.sh prep ./record`（或 `meeting.sh ./record`，`./record` 不等於 `record`，會走既有 `*)`） |

層旗標拿掉與未知選項（與 `spec.md §2.2` 通則、§2.4.2 同一句定義）：**未知選項**＝`meeting.sh` 先把 `record` 之後任何位置出現的層旗標 `--recorder`、`--yes`（每個出現處）拿掉、其餘參數維持原序交給 `record.sh`；拿掉層旗標之後，仍不屬於該寫法寫法旗標集合（§2.4.2 表第二欄的旗標名）的 `--` 開頭參數，即為未知選項，回通則結束碼 2。判斷範圍：寫法本身的字（含 `help` 同義字 `-h`、`--help`）與寫法旗標之值不參與判斷；只以單一 `-` 開頭的參數不算未知選項，照一般參數處理（`spec.md §6` 第 31 條）。層旗標名不在任何寫法的寫法旗標集合內（`spec.md §2.4.2`），拿掉時不會與寫法旗標衝突。中間與結尾位置的案例見 `spec.md §4.1.12`。

結束碼 2 沿用既有語意（前提不成立，`bin/meeting.sh:93,97`）。這是對 intent「既有行為零變更」的偏離，記在 `spec.md §6`，迴歸測試見 `spec.md §4.1.3`、`§4.1.10`。

### 8.2 menu bar 的設計依據（D12）

repo 沒有設計系統 skill（`rules.md:58`），審查依據改用 macOS Human Interface Guidelines 的 menu bar extra 慣例。落實成下列規則，逐條寫成 `spec.md §4.11.5–4.11.8` 給 `dev-design-reviewer` 對照：

| 主題 | 規則 |
|---|---|
| 圖示 | 一律 SF Symbols 的 template image（`isTemplate = true`，隨淺色／深色 menu bar 自動反白）；三態以**形狀**區分，不只靠顏色：待機 `record.circle`、錄製中 `record.circle.fill`、告警 `exclamationmark.triangle.fill`。只有告警態可加系統紅色（`req:191`「menu bar 變紅」），形狀已能區分，色盲使用者也看得出來 |
| 寬度 | menu bar 上只放圖示，不放文字（不顯示計時），避免佔 menu bar 寬度 |
| 可讀性 | status item 按鈕設 `toolTip` 與 `accessibilityLabel`，內容＝`MenuBarModel.accessibilityText`：非待機狀態在 `statusLine` 前加「MeetingRecorder：」（例「MeetingRecorder：錄製中 12:34・<場次名>」），VoiceOver 掃 menu bar 時聽得出是哪個 app；待機的 `statusLine` 本身已含 app 名，不重複加（D18，設計審查 N-2）。選單的狀態列不可點但用 `labelColor`（不用系統灰色），超過 40 字截斷並在該選單項的 toolTip 放完整內容（D18，設計審查 N-3） |
| 即時性 | 每秒 refresh 的 timer 加入 `RunLoop.main` 的 `.common` mode（只排在 `.default` mode 的 timer 在選單展開、run loop 進 event tracking mode 時不會觸發），或以 `NSMenuDelegate.menuWillOpen(_:)` 開選單時立即 refresh；選單展開期間經過時間與狀態照常更新（D18，設計審查 SF-1） |
| 單一實例 | 一個 app 只放一個 menu bar extra：menubar 模式用 `menubar.lock` 的 `flock` 判斷，已有實例就直接結束；鎖由系統在 process 結束時釋放，crash 不留殘鎖；不影響 `quick-start` 等其他模式（`SKILL.md` 教的 `open -n -a … --args menubar` 照舊可用，重複執行不會多一個圖示）（D18，設計審查 SF-3） |
| 選單結構 | 第一行＝不可點的狀態列（待機／錄製中 mm:ss・<場次名>／收尾中…／告警：<最新告警一句話>）→ 分隔線 →「開始錄製（用上次的設定）」（顯示快速鍵 ⌃⌥⌘R，D18）→「停止錄製」→「打開場次資料夾」→ 分隔線 →「結束 MeetingRecorder 選單」（⌘Q）。不能用的項目**灰掉而不是隱藏**，讓使用者知道功能存在 |
| 停止行為 | 「停止錄製」只在 `phase=recording` 且 pid 活著時可點；點下立即送 SIGTERM、選單狀態列改「收尾中…」（有告警類 warning 時為「收尾中…（告警 N 則）」，D17），`stopping`／`finalizing` 期間「停止錄製」灰掉避免重送；完成後送一則通知（場次路徑），圖示回待機或（`code≠0` 時）告警 |
| 結束選單 | 「結束 MeetingRecorder 選單」只結束 menu bar 實例，**不停止**正在進行的錄製（錄製是另一個 process）；選單項文字要寫出這一點 |

狀態對映（`menuBarModel` 的規則）：**完整對映表只寫在 `spec.md §3.4.1`**（由上而下取第一個成立的列，逐列可單元測試），本節只說原則：
- 沒有狀態檔、或上一場 `phase=done` 且 `code=0` → 待機；
- **`phase=preflight_failed` 一律歸告警態**（第二輪 skeptic 問題 3：它必定伴隨 hard 失敗的 code 2／3／4，前一版寫「`preflight_failed` 且 `code=0` → 待機」是不會發生的組合，真正常見的情境反而沒有對映）。狀態列寫「開錄前檢查沒通過」加上 `message` 第一行（含補救步驟），「開始錄製」可點，讓使用者照補救做完直接重試；
- `phase=failed`、`phase=done` 且 `code≠0`、進行中但 pid 已死（異常中止）→ 告警；
- 進行中且 pid 活著：`stopping`／`finalizing` 一律 → 錄製中、狀態列「收尾中…」（有告警類 warning 時附「（告警 N 則）」，`spec.md §3.4.1` M6a、M10；D17：按了停止就要看得到收尾中，告警數保留可見）；其他 phase 有告警類 warning → 告警，否則 → 錄製中。

告警態會停留到下一次開始錄製（狀態檔被新的 `runId` 覆蓋）為止（使用者在閘門 2 以 D14 確認）；menu bar 不自行清除狀態檔，因為那是 `record.sh` 與錄製實例之間的契約檔（`adr/adr-control-channel.md`）。

### 8.3 視窗清單與會議標記（D15、D16）

取捨見 `adr/adr-meeting-window-marking.md`；行為規則的唯一正本是 `spec.md §3.8`，本節只說結構與理由。

**問題（D15 診斷）**：使用者說「清單裡根本沒有那個視窗」，實際是 M+ Meet 的 Chrome 視窗有被納入、但標題是會議名稱，清單上與其他 7 個 Chrome 視窗長得一樣（`wfd:37`）；另外「標題非空」把 LINE 通話視窗濾掉是真 bug（`wfd:39`）。所以修法分兩半：**讓會議視窗認得出來**（★＋更多欄位），以及**不要濾掉無標題視窗**。前一版 spec 把 native 全螢幕當成錄製行為問題、SKILL.md 退路是「不要用 native 全螢幕」，等於繞開；實測 native 全螢幕＋切 Space 錄得到（`wfd:40`），該退路刪除（`spec.md §6` 第 36 條）。

**資料流**：

```
SCShareableContent.windows ──▶ [WindowCandidate]（Capture/：抄 windowID、app、bundleID、title、layer、frame、isOnScreen、isActive）
NSRunningApplication（Chrome 在跑？）──▶ AEDeterminePermissionToAutomateTarget ──▶ AutomationStatus
                                         └─ authorized ─▶ NSAppleScript(chromeTabsScript) ─▶ [ChromeWindowInfo]（只在記憶體）
                       ▼
Core/WindowList.swift：buildWindowRows = exclusionReasons 篩選 → meetingAppService／matchChromeWindow＋meetingService 標 ★
                       → 排序（★、前景、面積、windowID）→ windowRowLabel
                       ▼
windows（文字／--json）、_record_prompt.py 選單（逐字印 label）、quick-start（★ 恰好一個）、diagnose-windows（含被濾掉的）
```

| 決定 | 理由 | 代價 |
|---|---|---|
| 篩選只留 layer 0 與 400×300 兩條，移除「標題非空」 | 無標題的 LINE 通話視窗是會議視窗（`wfd:18`）；Chrome 內部工具列靠尺寸就濾得掉（`wfd:20`） | 清單可能多出幾個無標題的大視窗（例如 PowerPoint 編輯視窗）；以「<app 名>（無標題）」標示，使用者看得出是什麼 |
| ★ 只有兩個來源：原生會議 app 的 bundleID、作用中分頁是會議網址的 Chrome 視窗；Chrome／Safari 不再整個 app 標 ★ | 整個瀏覽器標 ★ 等於沒標（`main.swift:106-112`）；D16 指定以網址判斷 | Safari、Edge、Arc 等的會議分頁沒有 ★（衍生工作）；LINE 通話不標 ★（不在 D16 的清單，使用者自己選即可） |
| 只看作用中分頁 | 單視窗擷取只錄得到正在顯示的分頁；會議分頁在背景時標 ★ 會讓 quick-start 錄到錯的畫面 | 會議分頁不在前景時沒有 ★，只有 label 提示；`spec.md §7` 疑慮 17 |
| Chrome 視窗對應：標題完全相同優先，同名時才用 bounds（±2 pt）分辨；對不上就不標 | Chrome AppleScript 的視窗 `id` 不是 `CGWindowID`；native 全螢幕時 bounds 與 SCWindow frame 是否一致未實測，標題（＝作用中分頁標題）兩邊一定一致 | 兩個同名且同 bounds 的視窗會 `.ambiguous`、都不標 ★ |
| Apple Events 只在 `windows --ask-automation`（`record.sh` 有 tty 時才加）跳授權框 | 第一次授權要有人在場讀框；quick-start、menu bar 由快捷鍵觸發，跳框會卡住；其他 session 經 skill 無 tty 呼叫也不能卡 | 沒在終端機跑過 `meeting record` 的使用者，quick-start 永遠沒有 Chrome 的 ★；SKILL.md 寫明（`spec.md §4.12.10`） |
| 查詢前先確認 Chrome 在跑；只用 `get`；網址不落地 | `tell application` 會把沒開的 Chrome 開起來；D16 要求唯讀；網址可能含會議 ID 與 token（M+ 的 `shortUrl`） | 每次列清單多一次 Apple Events 往返（逾時上限 5 秒） |
| `NSAppleScript` 在程序內執行，不 spawn `osascript` | TCC 的「自動化」授權要記在 MeetingRecorder 名下（與 `req:205` 不直接 exec 的理由相同：責任程序要是 app） | `NSAppleScript` 不是 thread-safe，查詢要在主執行緒或序列佇列上做 |
| 每列顯示 app 名、標題（或「（無標題）」）、尺寸、是否全螢幕尺寸、前景／背景／不在畫面上、★ 服務名；`label` 由 app 算好，prompt 逐字照印 | D15 3(b)；只有一個地方組字，文字與 JSON、終端機與選單不會不一致 | `label` 是 JSON 的一部分，改字要同時改 Swift 測試 |
| 視窗認回：windowID 優先，找不到才以 (bundleID, 標題) 在通過篩選的視窗中唯一認回 | 實測 windowID 會變（`wfd:33`）；前一版 spec 沒有這條（`spec.md §6` 第 37 條） | 只在 preflight／start 時認回，錄製中途改變不處理（`spec.md §7` 疑慮 15） |
| app 層診斷子指令 `diagnose-windows`（取代 stash 的 `probe --all`），不加 `meeting.sh` 寫法 | 下次「清單沒有我的視窗」可直接用 repo 內的 app 診斷，不必再靠 repo 外的 spike（`wfd:5`）；不進 `spec.md §2.4` 封閉清單，D13 的文件一致性檢查不受影響 | t3 多一個 dispatch case；SKILL.md 排錯段多一行（`§4.12.9` 驗它存在） |
| preflight 第 13 項 `apple_events` 為 warn；doctor 只印一行「◦」說明 | D16「不得 hard fail」；doctor 不啟動 app、查不到 TCC（同 §5 Q8） | D1 的「12 項」變 13 項（`spec.md §6` 第 34 條） |

## 9. Swift 原始碼切分（讓核心邏輯可以單獨編譯測試）

```
tools/MeetingRecorder/
├── Sources/
│   ├── main.swift                 子指令 dispatch：windows｜diagnose-windows｜probe｜preflight｜start｜quick-start｜menubar｜help
│   ├── Core/                      純邏輯，不呼叫 SCK 的執行期 API，可與 Tests/ 一起 swiftc
│   │   ├── AudioLevel.swift       RMS、AudioFormat、PeakWindow
│   │   ├── Detectors.swift        SilenceDetector、BlackDetector、SuspendedDetector、nonBlackRatio
│   │   ├── Preflight.swift        PreflightItem、Severity、PreflightResult、exitCode
│   │   ├── Records.swift          RecordStatus／Manifest／RecordMeta 與其子型別（Codable）、writeJSONAtomically
│   │   ├── Segments.swift         segmentFileName、boundaryGaps、evenPixelSize；D20 新增 SampleRoute、routeSample、segmentVideoBitRate
│   │   ├── Trigger.swift          MenuBarState、MenuBarModel（含 accessibilityText）、menuBarModel、truncatedStatusTitle、MenuBarLockResult、acquireMenuBarLock、QuickStartDecision、quickStartDecision
│   │   └── WindowList.swift       篩選、會議標記、Chrome 視窗對應、排序、label、認回、診斷（D15、D16，`spec.md §3.8`）
│   ├── Capture/                   SCK、Core Audio、磁碟、signal、finalize spawn、既有 probe；ChromeTabs.swift（Apple Events 權限判斷與 `chromeTabsScript` 唯讀查詢）；SegmentWriter.swift（D20 新增：一段的 AVAssetWriter、三個 input、收尾）；正式錄製（RecordingSession.swift 等）不得再用 SCRecordingOutput，只有 Probe.swift 保留
│   └── Trigger/                   MenuBar.swift、HotKey.swift、QuickStart.swift（只做 AppKit／Carbon 接線，判斷交給 Core/Trigger.swift）
├── Tests/                         run.sh：先 cd 到自己的目錄、nullglob，把 ../Sources/Core/*.swift ＋ *Tests.swift ＋ main.swift 編成一支執行檔並執行；必須在 macOS 內建 /bin/bash 3.2 下可跑（`set -u` 時空陣列用 `${core[@]+"${core[@]}"}` 展開）
├── build.sh                       改成編 Sources/**/*.swift（Info.plist 另加 NSAppleEventsUsageDescription）；以 SHA-1 5E249F84A9EC2F2D2B3914120906DF29FB4DF348 簽章，帶 --options runtime 與 --entitlements（§9.1）
└── Resources/
    ├── Info.plist
    └── MeetingRecorder.entitlements   新增：恰為 com.apple.security.device.audio-input 與 com.apple.security.automation.apple-events 兩項 = true（§9.1）
```

`Core/` 每個公開名稱的完整簽名、參數標籤、預設值與欄位型別**只寫在 `spec.md §3.4`**，本節只列檔案歸屬。test 子任務依 §3.4 寫紅燈測試；build 段不得改名（要改就回報）。

### 9.1 簽章、hardened runtime 與 entitlements（第二輪 skeptic 問題 2）

改用固定身分簽章後，app 第一次以 hardened runtime 執行（§1）。逐項對照 Apple〈Hardened Runtime〉的 entitlement 清單，判斷本 app 需要哪些：

| entitlement | 本 app 用到的功能 | 要不要 | 理由 |
|---|---|---|---|
| `com.apple.security.device.audio-input` | `SCStreamConfiguration.captureMicrophone`、preflight 第 4、6 項的 `AVCaptureDevice` | **要** | hardened runtime 下沒有它，麥克風存取會被拒，preflight 第 4／6 項失敗（code 4），正式錄製的麥克風路全靜音 |
| （螢幕錄製、系統聲音） | ScreenCaptureKit 的畫面與 `.audio` output | 不要 | 由 TCC「螢幕與系統錄音」授權管，清單裡沒有對應的 hardened runtime entitlement |
| `com.apple.security.device.camera` | 無 | 不要 | 不用相機 |
| `com.apple.security.automation.apple-events` | 視窗清單以 Apple Events 唯讀查 Google Chrome 各視窗分頁網址（D16，§8.3） | **要**（第六修正輪改） | hardened runtime 下沒有它，送給 Chrome 的 Apple Events 會被拒、且可能不跳授權框——與麥克風同類的靜默失效，只會表現成「Chrome 視窗永遠沒有 ★」；另需 `Info.plist` 的 `NSAppleEventsUsageDescription`（繁中說明用途）。「打開場次資料夾」仍用 `NSWorkspace`，不送 Apple Events |
| `com.apple.security.cs.disable-library-validation`、`allow-dyld-environment-variables`、`allow-jit`、`allow-unsigned-executable-memory` | 無 | 不要 | 只連結系統 framework 與系統 Swift runtime；`MH_*` 環境變數不是 dyld 變數；spawn 的 `afplay`、`python3` 是獨立程序，不受父程序 library validation 限制 |
| `com.apple.security.app-sandbox` | — | **不得加** | sandbox 會擋寫 `~/Documents/<客戶>/…` 與 spawn harness 的 `python3`；本 app 不上架 |

落實：
- 新增 `tools/MeetingRecorder/Resources/MeetingRecorder.entitlements`（plist），**恰為**兩項：`com.apple.security.device.audio-input = true`、`com.apple.security.automation.apple-events = true`；`Resources/Info.plist` 加 `NSAppleEventsUsageDescription`，文字例：「讀取 Google Chrome 各視窗目前分頁的網址，用來在錄製視窗清單中標出會議頁（例如 M+ Meet、Google Meet）。只讀網址、不操作瀏覽器，也不會傳出這台電腦。」；
- `build.sh` 兩個簽章分支都帶 `--entitlements "${HERE}/Resources/MeetingRecorder.entitlements"`；固定身分分支另帶 `--options runtime`（ad-hoc 分支維持不帶 runtime，行為與現在相同）；
- 驗證：t1 寫靜態檢查（entitlements 檔的鍵集合恰為上表「要」的兩項、`Info.plist` 有 `NSAppleEventsUsageDescription`、`build.sh` 的每個 `codesign --force` 都帶 `--entitlements`）；t3 完成條件在暫存目錄建一次 app，用 `codesign -d --entitlements - <app>` 確認兩項都在，用 `codesign -dvv <app>` 確認 flags 含 `runtime`；t6 第一步重新授權後跑一次 preflight，第 4、6 項都要 pass，並驗 Apple Events 第一次授權與不授權兩條路（`spec.md §4.2.8`、`§4.15.18`）。
- 「其他 entitlement 都不需要」是依文件判斷、未實測；若 t6 發現 SCK 擷取在 hardened runtime 下另有失敗，以 `needs_decision` 回報，不自行加 entitlement。

## 10. 測試策略

| 層 | 位置 | 怎麼跑 | 涵蓋 |
|---|---|---|---|
| Swift 核心單元測試 | `tools/MeetingRecorder/Tests/` | `bash tools/MeetingRecorder/Tests/run.sh`（可從任何目錄執行；以 macOS 內建 `/bin/bash` 3.2.57 為準） | RMS（雙聲道非交錯、單聲道 16 kHz Int16、交錯 24 kHz，`d2:38-39`、D6）、PeakWindow 跨取樣率與缺緩衝時段、三個偵測器、preflight 分級與結束碼（含第 5 項兩段式 `systemAudioCheck` 與 `warnOnly`，`spec.md §4.2.9`）、狀態檔／manifest／meta 編解碼與 JSON 鍵名、段名、空隙計算、偶數像素尺寸、menu bar 狀態對映、quick-start 判斷；視窗清單（篩選、網址與 app 的會議判定、Chrome 視窗對應、排序與 label、沒授權時的行為、JSON 鍵、認回、診斷，`WindowListTests.swift`，`spec.md §4.15.1–4.15.9`） |
| shell／Python 自動測試 | `tests/record/` | `python3 -m unittest discover -s tests/record -t .` | `meeting.sh` dispatch、`./record` 撞名（含以 pty 模擬互動）與既有結束碼迴歸、`record.sh` 各子指令結束碼（用 `MH_RECORD_OPEN` 替身取代 `open -n -a`、`MH_RECORD_HOME` 指向暫存目錄）、prompt、estimate、finalize（用 ffmpeg `lavfi` 現場合成不同尺寸、不同音訊取樣率、缺 video stream、影片軌偏短的段落；D20 再加兩條音軌、時間戳不規則（負 `start_time`、edit list、影音起點不同、重複 PTS、B-frame）、fragment 截斷的段落；不放任何真實錄音）、finalize 期間的並發、冪等、doctor 在沒有 app 時回 0（含「◦ 會議分頁標記」一行）、GIT 管控設定內容、prompt 的視窗選單與預設、`record.sh` 只在 tty 時帶 `--ask-automation` 並傳視窗認回參數、Chrome 查詢唯讀與 `Info.plist` 用途說明的靜態檢查（`spec.md §4.15.10–4.15.14`）、`specs/`／`tests/`／`tools/MeetingRecorder/Tests/` 不含客戶名稱的靜態檢查（`spec.md §4.14.3`；清單由 `MH_CLIENT_NAMES_FILE` 指向 run 目錄的檔，不進 repo） |
| 端到端核對工具的自我測試 | `tests/record/test_e2e_check.py` | 同上 | 用合成場次（已知會 PASS 與已知會 FAIL 的各一組）驗 `e2e_check.py` 每一項判準的判讀正確（修正 skeptic 問題 11）。**t6 第三輪**：`sync` 改用 1 kHz 帶通＋每個閃白的局部最大值起點（`spec.md §4.9.3`，缺陷 K (a)：全頻 RMS 會把持續說話當嗶聲）；`device_switch`、`hfp` 改為「不得連續 ≥ 3 秒 ≤ -60 dBFS」（缺陷 K (b)）；`fps_min_interval` 改為三條件（`spec.md §4.3.3`，發現 M）；自我測試各加一組會因舊判準誤判、新判準正確的合成場次 |
| 端到端（人工＋機械核對） | `tests/record/e2e_check.py <場次>` | test 段由使用者操作錄製後執行 | `spec.md §4.3`、`§4.4.3`、`§4.6`、`§4.8.1`、`§4.9`、`§4.10` 的可機械判定部分；「兩邊都聽得到」由使用者聽寫時間點覆核 |
| 文件與實作一致性 | `tests/record/test_docs.py`（共用 `tests/record/surface.py`：`SURFACE` 常數與 `parse_help`／`parse_block`／`parse_usage`／`form_argv`，`spec.md §2.4.8`） | 同 shell／Python 自動測試；build 全部合併後由 integrator 的全量測試跑 | D13 文件先寫：SKILL.md、README.md 的 `record-cli` 區塊對 `spec.md §2.4`（t5 時即可綠）、對 `meeting.sh record help` 的輸出與 `meeting.sh` 實際的旗標接受與結束碼（t4 合併後才綠）、對錄製器 `main.swift` 的 dispatch（t3 合併後才綠）；`spec.md §4.12.6–4.12.9`。help、`usage()`、文件區塊三種來源用同一組解析規則（`spec.md §2.4.4`）比到同一個 `SURFACE`；層旗標與通則結束碼 2 各有獨立歸類，不混進寫法的集合（第四修正輪） |
| 設計審查 | `dev-design-reviewer`（test 段平行派） | menu bar 三態截圖（淺色／深色）＋選單截圖 | `spec.md §4.11.5–4.11.8`，依據 macOS HIG menu bar extra 慣例 |

verify 指令維持 `bash bin/_lint.sh && bash bin/meeting.sh doctor` 不變（`rules.md:59`）；上述兩支測試是本 epic 子任務的完成條件，不併入 verify 指令本身；但 `rules.md` 的 verify 規則已（主 session 於 `544df94`）要求 integrator 每合併完一層，在整合分支全量跑 epic `plan.md §3` 列的測試指令，任何一條不綠不得進下一層。測試一律用 `TMPDIR="$(mktemp -d)"`、`LC_ALL=en_US.UTF-8`（`rules.md:60`），**不在 repo 內產生任何媒體檔**。

`MH_RECORD_OPEN`、`MH_RECORD_HOME`、`MH_RECORDER_APP`、`MH_FFMPEG` 只是測試接縫與路徑覆寫，在 `usage()` 的環境變數段落列出，不是新子指令。`MH_CLIENT_NAMES_FILE` 只給 `tests/record/test_static_rules.py` 讀（`spec.md §4.14.3`），`bin/` 不讀它，也不列進 `usage()`。

---

## 11. 不在本設計範圍

分軌（`req:257`）、行事曆提醒（`req:300`）、常駐第二條保險 stream（條件未成立，`PROBE-REPORT.md:16`）、收斂四份副檔名清單、`config.json:34` 的既有錯誤說明、把 `tools/**/*.sh` 納入 `_lint.sh`、Safari 與其他 Chromium 瀏覽器的會議分頁標記、LINE 通話標 ★、錄製中途 windowID 改變時重新掛載視窗 —— 皆列為衍生工作（不編號）。

---

## R2 第二輪設計（2026-10-12）

- 性質：R2 增補。**本節以上的第一輪內容一字不改**；本節的決定若取代第一輪定案，逐條記在 `spec.md` 檔尾〈R2-§6 整合修訂與例外（續）〉第 77 條起。
- 上游：`intent.md`〈R2 第二輪功能〉與〈R2 閘門 1 使用者決定〉（已核准）；需求正本 `_tpm/runs/20261010-sdlc-meeting-record/r2-brief.md`（本機、不在版控；簡寫 `brief:<行>`）；調研 `research-code-contracts.md`（簡寫 `cc:`，R2 節 :1-252）、`research-specs-adr.md`（`sa:`，:153 起）、`research-requirement.md`（`rq:`，:226 起）。
- 第一輪基準點：本機 tag `meeting-record-r1-baseline`（＝`f084765`，R2-Q1）；程式行號以該點為準。
- 範例名稱一律用「[Stand-up] 範例專案」；不寫任何真實客戶、會議或視窗標題。
- 架構取捨（ADR，本輪新增四則）：`adr/adr-r2-control-file.md`（控制通道）、`adr/adr-r2-pause-cut.md`（暫停剪掉）、`adr/adr-r2-status-fields.md`（新欄位放哪）、`adr/adr-r2-login-item.md`（登入自動開與無參數啟動）。本節只摘結論。
- **Swift `Core/` 的 R2 新名稱只以 `spec.md` 檔尾 R2 §3.14 為準**（沿用第一輪 `design.md §9` 的規則，本節不重抄簽名）。
- **閘門 2 修正輪（2026-10-12）**：使用者在閘門 2 決定 (1) 時間軸照 R2-D5 原案（選項 A）、(2) 自動前處理先不讓路、t7 觀察（R2-D10）、(3) 新欄位 nil 省略鍵、`RecordsTests` 不改（R2-D6）、(4) skeptic 問題全部修正。本輪對設計的實質變更只有 R2-D3 的「暫停閘門與換段原因純函式化」（新增 R2-D3a）、R2-D11 的 `stop` 摘要有了驗收、R2-D12 的 `--pause-mute` 由六項增為九項；其餘是依據與對照的補記。細節見 R2-D15 末的〈閘門 2 使用者決定〉表。

### R2-D1 元件與資料流

```
                ┌─────────── menu bar（常駐，--args menubar；無參數啟動也進這裡）──────────┐
 ⌃⌥⌘R/M/P/B ──▶ │ HotKey（每組不同 id）→ TriggerDebouncer → 動作                               │
 選單         ──▶ │  ├ 暫停／靜音／標記：controlAvailability → requestControl（flock）→ kill(SIGUSR1) │
                │  ├ 錄這個視窗 ▸：open -n -a 自己 --args windows --json --log <暫存> → 子選單     │
                │  ├ 存到 ▸／偏好設定：menubar.prefs.json（只有 menu bar 寫）                      │
                │  ├ 開始：open -n -a 自己 --args quick-start [--window … --root …]               │
                │  └ 看到 done：完成通知（在 Finder 顯示）、停止後自動前處理（meeting.sh prep 場次） │
                └───────────────────────────────▲──────────────────────────────────────────────┘
                                                │ 每秒讀 record.status.json（新選用欄位：計時、暫停、靜音、標記數、收音）
 meeting record pause|resume|mute|unmute|mark ──┤（bin/record.sh：同一套前提檢查＋flock＋SIGUSR1，等狀態反映）
                                                ▼
 錄製實例（start／quick-start）：SIGUSR1 → readControl → controlActions → 暫停閘門／mic 歸零／標記
   └ 寫 record.status.json（選用欄位）、tracks/record.meta.json（pauseEvents、micMuteEvents）、tracks/markers.json
 finalize：串接（暫停段自然不在成品）→ gapStats 扣暫停、pausedTotal → 複製 markers.json 到 錄音/（在 already_done 之前）
```

### R2-D2 控制通道（R2-Q4、R2-Q11；ADR `adr-r2-control-file.md`）

| 決定 | 理由 | 代價 |
|---|---|---|
| 控制檔存「目標狀態」`{schemaVersion, runId, paused, micMuted, markerSeq}`，錄製實例以 `controlActions` 算差異 | 重複寫、訊號合併都冪等（brief:35「切換是冪等的」）；`markerSeq` 差值＝要加幾個標記 | menu bar 的「切換」要先由目前狀態算出目標再寫 |
| 錄製實例在 `installSignalHandlers()`（加裝 SIGUSR1）之後、寫 `record.pid` 之前呼叫 `resetControl` | 解決控制檔殘留（`cc:` C10）：上一場暫停中當機，下一場不會一開就暫停 | 開錄多一次寫檔 |
| 送 SIGUSR1 的前提：`record.pid` 活著、等於 `status.pid`、`phase == recording`、`controlVersion ≥ 1`；pid 只取 `record.pid` | SIGUSR1 預設會終止程序（`cc:` C1）；舊版錄製實例沒有 `controlVersion` | 舊版開的錄製只能停止（回 3 並說明） |
| `main.swift` dispatch 前 `signal(SIGUSR1, SIG_IGN)` | 新版任何模式（preflight 中的 quick-start 程序等）誤收都不會被殺 | 無 |
| 寫者取 `<home>/record.control.lock` 的 `flock(LOCK_EX)` | menu bar 與 CLI 同時寫不互相蓋掉（快捷鍵連按加標記不丟） | 多一個鎖檔 |
| CLI 寫完送訊號後，最多等 5 秒看 `record.status.json` 反映（`paused`／`micMuted`／`markers`）才回 0；沒反映回 3 | 讓其他 session 拿到確定的結果，不是「已送出」 | 錄製器忙時最多多等 5 秒 |

### R2-D3 整段暫停（F2；R2-Q9、R2-Q16；ADR `adr-r2-pause-cut.md`）

錄製實例（只在序列佇列 `q` 上）：

1. **暫停**：E＝`maxEnd`（沒有任何 sample 時為目前段起點）；有 prev 先 `closePrev()`；目前段若沒有內容（E ≤ 段起點或沒寫過 sample）就 `cancel()` 並從 manifest 移除，否則轉成 prev（`prevEnd = E`、1 秒後或三路都越過 E 時收尾）；`cur = nil`、`nextBoundary` 失效、`switchOnNextSample = false`、`paused = true`；記 `pauseEvents{kind: pause, t: E − t0}`；偵測器停餵（`BlackDetector.interrupt(at:)` 收掉開著的黑畫面區間）。
2. **暫停中**：`ingest` 的第一個判斷（在 `maxEnd` 更新之前）：`paused` 時，PTS < E 的 sample 照 `routeSample` 寫進 prev，其餘丟棄、**不更新 `maxEnd`、不觸發 `cur == nil` 的自動開段**；complete 幀仍更新 `lastFrame`（不寫入）；影片心跳因 `cur == nil` 自然停；`closeLevels` 照常每 0.5 秒補時段（沒有 feed＝null），但不餵靜音偵測器；每 30 秒的磁碟檢查照常（低於 2 GB 照 `spec.md §4.5.5` 停止收尾）。
3. **繼續**：`paused = false`、設 `resumeOnNextSample`；下一個 PTS ≥ E 的 sample 以它的 PTS 為邊界開新段（`SwitchReason.resume`，加在 `RecordingSession.swift:28` 的 private enum），新段首幀以最後一個 complete 幀重新打戳（沿用 `:449-454`）。**閘門 2 修正輪**：`SwitchReason` 改搬到 `Core/Segments.swift` 並加 `resume`，Capture 刪掉 private 宣告（R2-D3a）；記 `pauseEvents{kind: resume, t: 新段 startedAt}`；`SilenceDetector`、`SuspendedDetector` 一律 `reset()`（暫停前的連續計時不得接到繼續後）。
4. **暫停中按停止**：`requestStop` 的停止點＝`maxEnd`＝E（暫停中不前進），`drainWriters` 沒有 `cur`；`pauseEvents` 最後一筆是沒配對的 `pause`。
5. **靜音中暫停、暫停中靜音**：兩個旗標互相獨立；暫停中切靜音只記事件，繼續後照目前的靜音旗標處理 mic。
6. **暫停中加標記**：允許；`outputT` 落在剪點（＝該次暫停的 `outputT`）。

`pausedSeconds`（status）＝已配對暫停的 Σ（resume.t − pause.t），用 sample 時鐘算，小數 3 位。

### R2-D3a 暫停閘門與換段原因純函式化（閘門 2 修正輪；skeptic 問題 1、2、7）

| 決定 | 理由 | 代價 |
|---|---|---|
| 暫停／繼續的狀態轉移（`PauseGate`、`pausing`、`resuming`、`segmentOpened`）、每個 sample 的去向（`pauseRoute` → normal／prevOnly／drop／resumeBoundary）與開段原因（`openReason`）放 `Core/Segments.swift`；`SwitchReason` 從 `RecordingSession.swift:28` 的 private enum 搬來並加 `resume` | intent R2-2 要求「Swift Core 單元測試涵蓋 resume 換段」；`Tests/run.sh` 只編 `Core/`，留在 Capture 的邏輯只能靠字串形狀檢查與 t7 | `ingest` 多一層呼叫；r2e 要刪掉 private enum（同名會遮蔽 Core 型別，靜態檢查擋） |
| 事件 append 與狀態欄位（`appendingPauseEvent`、`appendingMuteEvent`、`pauseStatusFields`、`applyingPauseFields`）放 `Core/Control.swift` | `pauseEvents` 冪等、`outputT` 換算、`pausedAt` 繼續時刪鍵、`pausedSeconds` 更新原本只有 t7 驗（skeptic 問題 7） | Capture 不能自己組事件，一律呼叫 Core |
| 偵測器餵送規則 `detectorFeed(paused:micMuted:)` 放 `Core/Detectors.swift`；Capture 在 `closeLevels` 與影格處理處都依它決定餵不餵 | F2「暫停期間不誤報黑畫面」原本只有 `.interrupt(at:` 字串形狀（skeptic 問題 2）；另在 `e2e_check.py` 加 `no_false_black` 做 t7 機械核對 | 多一個小型別 |

語意與第一輪一致的地方：route 為 normal 時，`openReason` 只處理「`cur == nil` 或 writer 失敗後換段」那一支，定期換段與格式變更換段仍是 `ingest` 原本的判斷（第一輪行為不動）；route 為 resumeBoundary 但從沒開過段（暫停發生在第一個 sample 之前）時原因是 `first`，避免對不存在的段重新打戳。暫停前沒有任何 sample 時 `cutPoint` 為 nil、pause 事件的 `t` 記 0.000。

### R2-D4 只靜音麥克風（F1）

- **做法：改寫成數位 0，不停寫**。在 micQ 的 sample 回呼裡、算 `rmsDBFS` **之前**（`RecordingSession.swift:276` 之前）判斷靜音旗標，成立就以 `zeroedAudioSample(_:)`（Core，深拷貝 `CMBlockBuffer` 後全部清 0，時間與格式不變）取代原緩衝，之後照常算 RMS（得 -∞ → levels 的 mic 寫 null）與寫檔。不能用 `retimedVideoSample` 那種共用資料的淺拷貝（`Capture/SegmentWriter.swift:164-171`），也不能改 SCK 給的原緩衝。
- **不採「停寫 mic 軌」**：finalize 對缺封包的音軌只部分處理（`bin/_record_finalize.py:174-175`、`:318-328`），停寫會讓那段 mic 軌變短、串接與混音的對齊要另外處理（brief:22）。
- 靜音旗標由 `q` 寫、micQ 讀：以鎖或 atomic 保護的單一 Bool（實作選擇，不進契約）。
- 偵測器：靜音期間 `closeLevels` 不餵 `micSilence`；取消靜音時 `micSilence.reset()`。系統聲音路照常。
- 事件：`record.meta.json.micMuteEvents{t, outputT, wallClock, muted}`（brief 的 `{t, muted}` 加兩個欄位，`spec.md` §6 第 97 條）；append 一律經 Core `appendingMuteEvent`（閘門 2 修正輪，`spec.md` §4.17.7）。t7 以 `mute_timing`（麥克風軌數位 0 區段的起訖對事件時刻 ±0.5 秒）與 `event_output_t` 核對時間（`spec.md` §4.17.8、§4.18.12）。

### R2-D5 時間軸（R2-Q8）

| 資料 | `t` 用哪把尺 | 另附 |
|---|---|---|
| 既有：`levels`、`blackIntervals`、`deviceEvents`、`audioFormatEvents`、`warnings[].t`、`segments[].startedAt` | **錄製時鐘**（sample／host 時鐘 − t0，含暫停時間），不改 | — |
| `pauseEvents`、`micMuteEvents`（`record.meta.json`） | 錄製時鐘 | `outputT`（成品時間）、`wallClock`（ISO 8601） |
| `markers.json`（`tracks/` 與 `錄音/` 同內容） | **成品時間**（brief:27「錄到的時間，扣掉暫停」；下游 summary 要對逐字稿，用成品時間） | `recordT`（錄製時鐘）、`wallClock` |

閘門 2 使用者決定 1（2026-10-12）：採本表（選項 A）。

- 換算只有一個函式：`outputTime(recordT:firstSegmentStart:pauses:)`（Core）＝recordT − startedAt_1 − 已結束的暫停長度；落在暫停區間內的時刻夾到該次暫停點。段落邊界的微小空隙（< 0.5 秒）不計，所以 `outputT` 與成品實際位置的誤差上限是累積空隙（t7 容許 ±1 秒）。
- `levels` 的暫停期間：照常每 0.5 秒補一個時段、兩路都是 null（沒有 feed）——保持「索引 × 0.5＝錄製時鐘」不變；靜音期間 mic 是 null（數位 0 的 RMS 是 -∞）。null 不再只代表「-∞ 或沒有緩衝」，所有讀 `levels` 的判準（`e2e_check.py` 的 `device_switch`、`hfp`、`interruption_report` 等）都要先排除 `pauseEvents` 的暫停區間（兩路）與 `micMuteEvents` 的靜音區間（mic 路）。混音軌（成品）上的量測要先把事件的錄製時鐘換成成品時間。

### R2-D6 狀態欄位與計時（R2-Q10、R2-Q12；ADR `adr-r2-status-fields.md`）

- `record.status.json` 新增 8 個頂層 Optional，**nil 時省略鍵**（`Records.swift:3-4` 慣例的例外）：`controlVersion`、`recordingStartedAt`、`paused`、`micMuted`、`pausedSeconds`、`pausedAt`、`markers`、`recentLevels`。錄製實例在 `phase` 轉 `recording`（`RecordingSession.swift:179-183`）時一次寫入 `controlVersion = 1`、`recordingStartedAt = isoNow()`、`paused = false`、`micMuted = false`、`pausedSeconds = 0`、`markers = 0`。
- **計時**：`recordedSeconds(recordingStartedAt:pausedSeconds:pausedAt:now:)`＝now − recordingStartedAt − pausedSeconds −（暫停中再扣 now − pausedAt），向下取整、不小於 0；顯示 `clockText(seconds:)`：< 60 分鐘 `mm:ss`、≥ 60 分鐘 `h:mm:ss`（與第一輪 M9 的格式相同）。起點改用 `recordingStartedAt`，修掉 `startedAt` 早於開錄約 10 秒的既有偏差（`cc:` C8）；舊狀態檔沒有這個鍵時沿用第一輪的 `startedAt` 算法。
- **收音指示（F9）**：錄製實例每 0.5 秒 `closeLevels` 後算 `recentLevels = {windowSeconds: 3, system, mic}`（各路最後 6 個時段的最大值，全 null 為 null；靜音中 mic 為 null；暫停中不寫此鍵），**每秒最多寫一次**狀態檔。menu bar 用 `levelIndicatorLine(recent:micMuted:paused:thresholdDBFS: -60)` 組字，「超過」＝嚴格大於 -60（與 `systemAudioCheck` 一致）。
- 寫入頻率：第一輪狀態檔只在事件時寫；R2 錄製中每秒最多一次（tmp＋rename，檔很小）。
- 閘門 2 使用者決定 3（2026-10-12）：nil 省略鍵、`RecordsTests` 不改（選項 A，`spec.md` §6 第 79 條）。

### R2-D7 menu bar（F5、F9、R2-Q7；取代 D12 的「只放圖示」）

| 主題 | R2 規則 | 取代／延伸 |
|---|---|---|
| 寬度與文字 | status item 改 `NSStatusItem.variableLength`；錄製中與暫停中在圖示右側顯示計時（`MenuBarModel.timerText`），字型 `NSFont.monospacedDigitSystemFont`（每秒更新寬度不抖）；其他狀態只放圖示 | 取代 `design.md §8.2`「寬度」列（D12）——使用者 R2 決定「紅點＋計時」（brief:13、:26） |
| 圖示 | 待機 `record.circle`、錄製中 `record.circle.fill`（**系統紅色**＝「紅點」）、暫停中 `pause.circle.fill`（template、不加色）、告警 `exclamationmark.triangle.fill`（系統紅色）；麥克風靜音時計時前多一個 `mic.slash`（template）。形狀可區分四態，不只靠顏色 | 延伸 §8.2「圖示」列（原本只有告警態可加紅色）；新增 `MenuBarState.paused` |
| 狀態對映 | `spec.md §3.4.1` 新增 M6b（錄製中且暫停 → 暫停態，排在 M7 之前，否則舊告警會蓋掉暫停狀態）；M9 的計時改用 `recordedSeconds`、靜音時狀態列加「麥克風靜音中」 | 列名不重編號（沿用 M6a 先例） |
| 收音指示列 | 狀態列下方一行不可點的「收音：系統聲音 ● 有聲　麥克風 ○ 無聲」；靜音中麥克風顯示「⊘ 已靜音」、暫停中整行「收音：暫停中」；只在錄製中（`phase == recording` 且 pid 活著）顯示，其他狀態隱藏（資訊列不適用「灰掉不隱藏」） | 新增 |
| 選單結構 | 見 `spec.md` §4.20.6 的順序；暫停／靜音／標記在「停止錄製」之前；「麥克風靜音」用打勾狀態（`NSControl.StateValue.on`）；「暫停錄製」暫停中改名「繼續錄製」；新項目照「灰掉不隱藏」 | 取代 §8.2「選單結構」列與 `spec.md §4.11.6` |
| 快捷鍵 | ⌃⌥⌘R 開始、⌃⌥⌘M 麥克風靜音、⌃⌥⌘P 暫停／繼續、⌃⌥⌘B 加標記（brief:22-27）；`HotKey` 每組不同 `EventHotKeyID.id`（1–4），handler 以 `GetEventParameter(kEventParamDirectObject, typeEventHotKeyID)` 比對自己的 id，不是自己的回 `eventNotHandledErr`（`cc:` C2）；每組註冊失敗各寫一行 log、清掉該選單項的 `keyEquivalent`（沿用 `spec.md §4.11.3`、§6 第 75 條） | 延伸 §4.11.3 |
| 重複觸發 | 選單展開時快速鍵與 Carbon hot key 可能各觸發一次（`Trigger/MenuBar.swift:22-24`）：暫停與靜音寫「目標狀態」（由目前狀態算出），同一次按鍵觸發兩次結果相同；另以 `TriggerDebouncer`（同一動作 1 秒內第二次忽略）擋加標記與快速連按；開始錄製沿用 2 秒去抖 | 新增 |
| 即時性 | 沿用 `.common` mode 的每秒 refresh（`spec.md §4.11.9`），計時與收音列在選單展開時照常走 | 不變 |

### R2-D8 選單選視窗與存檔位置（F3、F4；R2-Q3、R2-Q15）

- **設定檔分工（R2-Q3 使用者決定：另開 menu bar 專用設定檔）**：新增 `~/.meeting-harness/menubar.prefs.json`，**只有 menu bar 寫**（偏好設定視窗屬於 menu bar 程序）；`record.defaults.json` 維持 `record.sh` 單一寫者（`bin/record.sh:315-327`），Swift 端只讀。鍵：`schemaVersion`、`root`（「存到 ▸」打勾的位置＝偏好設定的「預設存檔位置」，同一個設定在兩處顯示；nil＝沿用 `record.defaults.json` 的 `root`）、`recentRoots`（最多 5 個，最近的在前）、`autoPrep`（預設 false）、`lastSession`、`lastAutoPrepRunId`。
- **quick-start 的存檔位置**：`quickStartRoot(argRoot:prefsRoot:defaultsRoot:isDirectory:)`——`--root` ＞ `menubar.prefs.json.root` ＞ `record.defaults.json.root`；選到的不是現存目錄 → code 2 並通知。⌃⌥⌘R、選單「開始錄製」、Shortcuts 捷徑都走 quick-start，所以三個入口一致。終端機 `meeting record` 不讀 prefs（照舊問根目錄，預設值是 `record.defaults.json.root`）。
- **沒有完整 defaults**：`record.defaults.json` 不存在或沒有 `harness` 時，「錄這個視窗 ▸」「存到 ▸」灰掉，toolTip「先在終端機跑一次 meeting record」（`cc:` C9：只有 root 的 defaults 會讓收尾因 `harness` 缺值回 127）。
- **列視窗（R2-Q15）**：menu bar **不在自己程序裡呼叫 SCK**，照 `record.sh` 的 `fetch_windows`（`bin/record.sh:204-234`）以 `open -n -a <自己> --args windows --json --log <暫存檔>` 另開短命程序列清單（不帶 `--ask-automation`，不跳 Apple Events 授權框），子選單打開時先顯示不可點的「讀取視窗清單中…」，讀到後換成清單（★ 列已由 app 排在前面，標題以 `truncatedStatusTitle(label, limit: 60)` 截斷、完整 label 放 toolTip），逾時 10 秒顯示「取不到視窗清單（螢幕錄製權限？）」。理由：沿用已實測的路徑、維持「menu bar 實例自己不擷取」（`design.md §8` 表）；代價是打開子選單要等約 1 秒。
- **點視窗開錄**：`open -n -a <自己> --args quick-start --home <home> --window <id> --window-bundle <bundleID> --window-title <title> [--root <root>]`；quick-start 有 `--window` 時以 `resolveWindow`（`spec.md §3.8.8`）在通過篩選的視窗中認回，再交 `explicitWindowDecision(hasDefaults:resolution:)`——**略過 ★ 恰好一個的判斷**（使用者已明確選了，不是猜）；沒帶 `--window` 時行為與 `spec.md §4.11.1` 完全相同。
- **存到 ▸**：子選單列 `root`（打勾）與 `recentRoots`（不存在的目錄灰掉並標「（找不到）」）、分隔線、「選擇資料夾…」（`NSOpenPanel`：只能選資料夾、可建新資料夾；開之前 `NSApp.activate`）；選定後寫 `root` 並以 `updatedRecentRoots(_:adding:limit: 5)` 更新清單。錄製中也可以改（影響下一場）。

### R2-D9 偏好設定、登入自動開、無參數啟動（F7、R2-Q6；ADR `adr-r2-login-item.md`）

- 偏好設定視窗（`Sources/Trigger/Preferences.swift`，選單「偏好設定…」⌘,）：一個不可縮放的小視窗，標題「MeetingRecorder 設定」，改了立即生效（沒有「確定」按鈕，HIG 的 settings window 慣例），⌘W 關閉。內容依序：
  1. 預設存檔位置：路徑（過長中間省略）＋「更改…」（同「存到 ▸」的 `NSOpenPanel`）；
  2. 快捷鍵一覽（唯讀）：四組各一行「⌃⌥⌘R　開始錄製（用上次的設定）」…，註冊失敗的那組加「（註冊失敗，可能被別的 app 佔用）」；
  3. 「登入時自動開啟」勾選框＋`loginItemDisplay` 的說明文字；`.requiresApproval` 時多一顆「打開系統設定的登入項目」；
  4. 「停止後自動跑前處理（轉錄；講者分離依會議型態）」勾選框，預設關。
- 無參數啟動：`launchMode(arguments:)`——沒有參數或只有 `-psn_` 開頭的參數 → `menubar`；`help`／`-h`／`--help` 照舊。menubar 的單一實例鎖（`spec.md §4.11.10`）擋住重複圖示。
- 只在使用者勾選時呼叫 `SMAppService.mainApp.register()`；任何自動流程都不得呼叫（不改使用者系統設定）。

### R2-D10 停止後自動前處理與完成通知（F8、R2-Q13、R2-Q14）

- **執行者：menu bar**。錄製實例收尾完就 `exit`（`RecordingSession.swift:770`），不能等數分鐘的轉錄；menu bar 常駐、每秒讀狀態。判斷交 Core `shouldAutoPrep(...)`：`autoPrep` 開、`phase == done` 且 `code == 0`、該 `runId` 在本次 menu bar 執行期間曾被看到處於進行中（避免重開 menu bar 時對舊場次補跑）、且不等於 `lastAutoPrepRunId`。
- **指令**：`/bin/bash <record.defaults.json.harness>/bin/meeting.sh prep <場次目錄>`——明確傳**場次目錄**（傳根目錄會重跑整個根目錄，`sa:` C14）；`PATH` 照 `runFinalize`（`RecordingSession.swift:731`）；stdout／stderr append 到 `<home>/autoprep.log`；以 `terminationHandler` 非同步等結束（不阻塞主執行緒）；同時只跑一個，後到的排隊。結束時通知「前處理完成：<場次名>」或「前處理失敗（結束碼 N），見 autoprep.log」。說法是「跑既有前處理」——講者分離只在 `MH_DO_DIARIZE=1`（依會議型態）時跑（`bin/meeting.sh:232`），驗收看 `錄音/transcript.raw.md`。不碰逐字稿內容（五條鐵則）。
- **與下一場錄製的資源競爭**：不讓路、不自動停（閘門 2 使用者決定 2，2026-10-12：選項 A，t7 實機觀察）。理由：自動停會讓「一條龍」變成不確定；ASR 跑 GPU（MPS）、錄製用 SCK 與硬體編碼器，衝突程度沒有本機數據。列為疑慮（`spec.md` R2-§7），t7 觀察丟幀摘要。
- **完成通知與「在 Finder 顯示」（R2-Q14）**：錄製實例照舊發完成通知，但識別碼固定為 `completionNotificationID(runId:)`；menu bar 看到同一個 `runId` 轉 `done` 時，以**同一個識別碼**再發一次帶 category（動作「在 Finder 顯示」）的通知——同 id 的通知會取代前一則，所以使用者只留一則可點的。menu bar 是 `UNUserNotificationCenter` 的 delegate，按下動作後 `NSWorkspace.activateFileViewerSelecting` 選取 `影片/*.mov`（沒有就選場次目錄）。menu bar 沒開時只有錄製實例那則（不能點動作），保底入口是選單「顯示上一場成品」（`lastSession`，或狀態檔 `phase == done` 的 `session`）。

### R2-D11 CLI（R2-Q5 使用者決定「全面更新子指令」）

- `meeting record pause|resume|mute|unmute|mark`：不接參數、沒有寫法旗標；寫法結束碼 `0 3`。0＝已套用（含「本來就是這個狀態」的冪等情形，不送訊號、印「已經是暫停中」之類）；3＝沒有可控制的錄製（沒在錄、還在開錄前檢查、正在收尾、舊版錄製器、5 秒內沒有回應），stderr 一句說明原因；多餘的位置參數回 2（與 `stop` 現行行為相同，`bin/record.sh:509`；不列入寫法結束碼）；未知選項回通則 2。
- 五個字比照 `help` 成為保留字：根目錄剛好叫這幾個字時寫 `meeting record ./pause`（`spec.md` R2-§7）。
- `bin/record.sh` 在 `*)` 之前加五個 case，共用一個 `cmd_control <動作>`；鎖、讀寫控制檔、前提檢查在同一段 Python（與 Swift 的 `controlAvailability`、`requestControl` 同語意，各自有測試）。`bin/meeting.sh` 只改 `usage()`（`record_cmd` 會透傳新子指令，`cc:` §1.4）。不新增 `bin/` 檔（`_lint.sh` 檔數維持 26）。
- `meeting record status`：錄製中改用 `recordingStartedAt` 與暫停扣除算計時，並多印「暫停中」「麥克風靜音中」「標記 N 個」（有才印）；`stop` 的摘要多一行「暫停 N 次、共 mm:ss；標記 N 個」（有才印）；N、共、標記數的來源與「有才印」的條件以 `spec.md` §4.16.11 為準（閘門 2 修正輪補驗收）。

### R2-D12 finalize 與 `e2e_check.py`

- `bin/_record_finalize.py`：(1) 在 `already_done` 判斷**之前**把 `tracks/markers.json` 複製到 `錄音/markers.json`（內容相同就不覆寫；來源不存在就不建；`cc:` C14）；(2) `gapStats`：讀 `record.meta.json.pauseEvents`，邊界 k→k+1 若有 `resume` 的 `t` 與 `startedAt_{k+1}` 相差 < 0.5 秒，該邊界的 g 扣掉這次暫停長度；新增 `pausedTotal`（沒有暫停寫 0.0）；`wallClock` 定義不變。串接不變（暫停段本來就不在任何段落裡）。
- `tests/record/e2e_check.py`：既有判準在沒有 `pauseEvents`／`micMuteEvents` 的場次上結果**完全不變**（既有自我測試的預期不改）；有事件時：`gap` 扣暫停、`wall <= 240` 的短場次分界改用（wall − pausedTotal）；`segment_cadence` 把 resume 邊界列為提前換段；`stop_tail` 加 `pausedTotal`、停止時仍在暫停則以最後一筆 pause 的 `t` 代替 `wallClock`；讀 `levels` 的判準排除暫停與靜音區間，讀混音軌的判準先把錄製時鐘換成成品時間。新增 `--pause-mute` 一組判準（`spec.md` §4.17.5、§4.18.6、§4.19.4）；閘門 2 修正輪再加 `mute_timing`、`no_false_black`、`event_output_t`（`spec.md` §4.17.8、§4.18.11、§4.18.12），共九項：`pause_events`、`pause_cut`、`mic_mute_zero`、`mute_system_kept`、`no_false_silence`、`markers`、`mute_timing`、`no_false_black`、`event_output_t`。

### R2-D13 Swift 原始碼切分（增補 `design.md §9`）

```
Sources/Core/Control.swift      新增：控制檔型別與讀寫（flock）、controlActions、controlAvailability、暫停／靜音事件、
                                     markers、outputTime、計時、收音指示、menubar.prefs.json、quick-start 的 root 與指定視窗判斷、
                                     launchMode、loginItemDisplay、shouldAutoPrep、通知識別碼、HotKeySpec、TriggerDebouncer
Sources/Core/Records.swift      RecordStatus／RecordMeta／GapStats 加 Optional 欄位（nil 省略）、RecentLevels
Sources/Core/Detectors.swift    SilenceDetector.reset()、SuspendedDetector.reset()、BlackDetector.interrupt(at:)、detectorFeed（閘門 2 修正輪）
Sources/Core/Segments.swift     SwitchReason（自 Capture 搬入＋resume）、PauseGate、pauseRoute、openReason 等（閘門 2 修正輪，R2-D3a）
Sources/Core/AudioLevel.swift   zeroedAudioSample(_:)
Sources/Core/Trigger.swift      MenuBarState.paused、MenuBarModel 新欄位（有預設值）、M6b、M9 計時
Sources/Capture/                RecordingSession（SIGUSR1、呼叫 Core 的暫停閘門、mic 歸零、標記、事件、狀態欄位；刪 private SwitchReason）、PreflightRunner（RunContext.controlURL）、
                                     Notifier（可指定識別碼）
Sources/Trigger/                MenuBar（變寬、計時、新選單、子選單、控制、完成通知、自動前處理）、HotKey（多組）、QuickStart（--window／--root）、
                                     Preferences.swift（新增）
Sources/main.swift              SIGUSR1 → SIG_IGN、launchMode
```

`Tests/run.sh` 把 `Core/*.swift` 一起編，新檔不用改執行器；新的測試檔要登記在 `Tests/main.swift` 的 `mrtSuites`。

### R2-D14 測試策略增補與設計審查

- Swift：新增 `ControlTests.swift`、`MenuBarR2Tests.swift`（`spec.md` §4.16–§4.23 的 Core 項）。
- Python：新增 `tests/record/test_r2_cli.py`、`test_r2_finalize.py`、`test_r2_e2e_check.py`、`test_r2_static.py`、`test_r2_docs.py`；`fakes/fake_recorder.sh` 加 `FAKE_CONTROL` 情境（接 SIGUSR1 並依控制檔改狀態、忽略、或舊版不接）。靜態檢查一律只掃**單一子任務擁有的路徑**（第一輪的教訓，`plan.md §1`），函式名以 `test_capture_`、`test_trigger_`、`test_main_` 開頭區分歸屬。
- **既有測試預期的修改**只有 R2-Q5 核准的 CLI 封閉清單那幾處（`spec.md` §6 第 77、93 條逐條列出），其餘既有測試一字不改；`RecordsTests` 的鍵集合測試不改（ADR `adr-r2-status-fields.md`）。既有的**測試工具與替身**（`e2e_check.py`、`fakes/fake_recorder.sh`、`_media.py`，必要時 `_helpers.py`／`_fixtures.py` 只加不改）與 `Tests/main.swift` 的 `mrtSuites` 登記會修改，完整清單在 `spec.md` R2-§5（閘門 2 修正輪補列）。
- **`has_ui`**：R2 多了真正的視窗（偏好設定）與變寬的 status item。延伸第一輪 D12 的例外：R2 的 test 段 `has_ui=true`，派 `dev-design-reviewer`，依據 macOS HIG 的 menu bar extra 與 settings window 慣例（`spec.md` §4.20.4、§4.20.6、§4.22.4），截圖由使用者在 t7 截（agent 不得啟動 app）。`has_security` 維持 false。

### R2-D15 R2-Q3～Q16 定案總表

| # | 定案 | 理由（細節見上） |
|---|---|---|
| R2-Q3 | （使用者決定）`menubar.prefs.json` 另開；`root` 一個設定兩處顯示；沒有完整 defaults 時兩個子選單灰掉 | R2-D8 |
| R2-Q4 | 只送 `record.pid`；四項前提；`controlVersion`；`main.swift` SIG_IGN；不成立回 3 | R2-D2 |
| R2-Q5 | （使用者決定）五個子指令、保留字、封閉清單 12 寫法；結束碼 `0 3`，冪等回 0 | R2-D11 |
| R2-Q6 | 無參數＝menubar；`SMAppService.mainApp` 無法帶參數（依 API 形狀，未實測） | R2-D9、ADR |
| R2-Q7 | 每組不同 id、handler 比對 id；失敗各自記 log、清選單快速鍵 | R2-D7 |
| R2-Q8 | meta 事件用錄製時鐘＋`outputT`；`markers.json` 的 `t`＝成品時間（brief 原文）＋`recordT`；`levels` 暫停補 null、判準以事件排除 | R2-D5 |
| R2-Q9 | 暫停＝目前段轉 prev（停止點 E）；`gapStats` 扣暫停＋`pausedTotal`；§4.4.3／§4.4.8 加排除 | R2-D3、R2-D12 |
| R2-Q10 | 頂層 Optional、nil 省略鍵；既有鍵集合測試不改 | R2-D6、ADR |
| R2-Q11 | 控制檔帶 `runId`；開錄時 `resetControl`；`markerSeq` 以 `runId` 為範圍 | R2-D2 |
| R2-Q12 | `recordingStartedAt`＋`pausedSeconds`＋`pausedAt`；≥ 60 分鐘 `h:mm:ss`；等寬數字 | R2-D6 |
| R2-Q13 | menu bar 執行、傳場次目錄、排隊單一執行、不讓路（疑慮） | R2-D10 |
| R2-Q14 | 同識別碼取代；menu bar 當 delegate；「顯示上一場成品」保底 | R2-D10 |
| R2-Q15 | menu bar 以 `open -n -a … windows --json --log` 列視窗，不在常駐程序呼叫 SCK；登入項目前提只能 t7 驗 | R2-D8、R2-D9 |
| R2-Q16 | 暫停中停止、靜音×暫停、暫停中標記、繼續重設偵測器、暫停中磁碟檢查照跑、markers 在 `already_done` 前複製、`recentLevels` 形狀、t7 容許誤差（成品長度 ±1 秒、短場次分界用扣暫停後的時長） | R2-D3、R2-D6、R2-D12、`spec.md` §4.25 |

#### 閘門 2 使用者決定（2026-10-12）

| # | 決定 | 落在哪裡 |
|---|---|---|
| 1 | `markers.json` 的 `t` 用成品時間、另附 `recordT`；`record.meta.json` 事件 `t` 用錄製時鐘、另附 `outputT`（選項 A） | R2-D5；`spec.md` §3.11、§3.12、§6 第 95 條 |
| 2 | 停止後自動前處理遇到下一場開錄時先不讓路，t7 實機觀察（選項 A） | R2-D10；`spec.md` §6 第 96 條、§7 疑慮 38 |
| 3 | `record.status.json`／`record.meta.json` 新欄位 nil 時省略鍵、`RecordsTests` 不改（選項 A，使用者接受主 session 依建議） | R2-D6；`spec.md` §3.10、§6 第 79 條 |
| 4 | skeptic 問題全部修正；resume 換段要有自動測試（換段判斷抽到 Core 純函式） | R2-D3a；`spec.md` §3.14、§4.16.11、§4.17.7–§4.17.8、§4.18.8–§4.18.12、R2-§5、§6 第 98、99 條；`plan.md` §9 |

### R2-D16 不在 R2 範圍

brief:32 的範圍外清單（開錄倒數、選麥克風裝置、會議自動偵測與行事曆提醒、捨棄這次錄製、Sparkle、Dock 備用入口）；summary 端使用 `markers.json`；標記自訂文字（public repo 與 `spec.md §4.14` 的考量，label 一律「標記 N」）；自動前處理在下一場開錄時讓路——皆列為衍生工作（不編號）。

## R3 第三輪設計（2026-10-13）

- 性質：R3 增補。**本節以上的第一輪與 R2 內容一字不改**；本節的決定若取代既有定案，逐條記在 `spec.md` 檔尾〈R3-§6 整合修訂與例外（續）〉第 117 條起。修正輪（skeptic 意見）起**沒有就地修改**：原本 `spec.md §2.4` 加 `meeting record sync` 的就地修改已還原，改為頂層 `meeting sync`（§6 第 117 條撤回；R3-D30）。
- 上游：`intent.md`〈R3 第三輪〉（第 312 行起；閘門 1 已核准，`run.json` 的 `r3-plan`）。閘門 1 的決定：R3-Q1＝A（納入 Q6 `SegmentScheduler`，排在 S-C 之前）、R3-Q8＝B（U1、U2 也走 Claude Design 設計稿）；D3、D4、D7、D9、D11、D12、D13、D14a、D14b 照預設採用。調研引用沿用 intent 的簡寫（`syn`、`sync`、`tr`、`feat`、`ui`、`q`），另加 `brief`＝run 目錄的 `r3-design-brief.md`（UI 方向與設計 token）。
- 程式行號以 `377dd92`（origin/main）為準；本節新查證的行號直接標在各條。
- 範例名稱一律用「[Stand-up] 範例專案」；不寫任何真實客戶、組織、會議或視窗標題。
- 架構取捨（ADR，本輪新增四則）：`adr/adr-r3-sync-compensation.md`（S-C 補償的量與開關）、`adr/adr-r3-concat-then-mix.md`（D20「逐段混音、串接一次編 AAC」在補償開啟時的改寫）、`adr/adr-r3-defaults-writers.md`（`record.defaults.json` 改成兩個寫者）、`adr/adr-r3-menu-stages.md`（推翻 §4.20.6「灰掉不隱藏」）。本節只摘結論。
- **Swift `Core/` 的 R3 新名稱只以 `spec.md` R3-§3.20 為準**（沿用第一輪 `design.md §9` 的規則）。
- **UI 外觀**：U1、U2、U4、U5、U6、U7、F2 的確認框、F3 的通知，外觀依使用者選定的設計稿（2026-10-13 定案，R3-D21、R3-D22；稿與規則存在 `design-r3/`）。

### R3-D1 元件與資料流（增補）

```
                       ┌──────────── ~/.meeting-harness/（MH_RECORD_HOME）───────────────┐
 record.sh ──try-lock──▶ record.lock（新，flock）◀── 錄製實例（start／quick-start／preflight）
   │  write_defaults ──▶ record.defaults.lock（新，flock）──▶ record.defaults.json ◀── app 首次引導（只寫 2 鍵）
   │  meeting sync <mode> ─▶ 同上（只寫 syncCompensation；兩者都經 bin/lib/_record_lib.py 的 merge_defaults）
   │                     menubar.settings.json（新；app 唯一寫者）  sync-calibration.json（新；使用者／實機驗收場手寫）
   ▼
 錄製實例 ──SegmentScheduler（Core，純）──▶ AVAssetWriter 段落 ──▶ tracks/seg-*.mov
   │  meta.outputLatencies（S-B，只讀 Core Audio）
   │  收尾：FinalizeRunner（逾時、取消）──▶ _record_finalize.py（tracks/.finalize.lock、逐步逾時、unreadable/、S-C）
   │  捨棄：record.discard.json ──▶ 跳過收尾、移到垃圾桶
   ▼
 meeting prep：transcribe.sh（VAD clip、segments.json、transcript.quality.json）──▶ _merge_speakers.py（不改）──▶ _render.py --annotate-speakers（speakers.md 後處理）──▶ _render.py（VTT 同一套歸屬、標示、## 標記、## 錄製註記；summarize-local.py 共用兩段）
 meeting search（bin/lib/_search.py）  meeting reminders（bin/lib/_reminders.py ──▶ MeetingRecorder reminders ──▶ EventKit）
 bin/lib/_record_lib.py：merge_defaults、output_time／paused_total／levels_intervals／clip_timestamps（Swift Core 共用測試向量 tests/record/vectors/）
```

序列鏈（同一支檔的子任務一律以 `depends_on` 串起來，`plan.md §10`；修正輪改為 6 層，R3-D30）：`RecordingSession.swift`＝lock（併入 latency-log）→ finalize-runner → discard → segment-scheduler → sync-compensate；`MenuBar.swift`＝menubar-states（併入 notify）→ hud → discard → menu-stages → onboarding-settings（併入 meeting-detect）；`Notifier.swift`＝menubar-states → onboarding-settings；`_record_finalize.py`＝finalize-guard → sync-compensate；`_render.py`＝vtt-raw → annotations；`bin/meeting.sh`＝vtt-raw → search → reminders；`Info.plist`＝reminders → onboarding-settings。同層 `owns` 不重疊由程式驗證（`plan.md §10.1`）。

**與 intent R3-8 分層的差異**（理由都是 Swift 測試執行器的限制或檔案歸屬）：

1. 新增第 1 層的 `r3-core`：`Tests/run.sh` 把 `Sources/Core/*.swift` 與全部 `*Tests.swift` 一起編，紅燈測試只要引用一個還不存在的 Core 名稱，整個 Swift 套件就編不過（R2 的 `r2d` 先例）。所以 R3 全部 Core 純函式（含 `SegmentScheduler` 狀態機、`MenuBarAppearance`、鎖與 stop 的判斷）集中在一個子任務先做，之後的子任務只做 Capture／Trigger 的接線。`r3-lock`、`r3-menubar-states` 因此從 intent 的第 0／1 層移到第 2 層。
2. 新增第 1 層的 `r3-docs`：README 與 meeting-record SKILL.md 的 CLI 區塊先寫（第一輪 D13「文件先寫」），`meeting sync`、`meeting search`、`meeting reminders` 的說明也在這裡（區塊外）；`meeting-transcribe`／`meeting-notes` 的 SKILL.md 跟著改它們行為的子任務走。
3. `r3-segment-scheduler` 只改 `RecordingSession.swift`（純狀態機在 `r3-core`），所以不碰任何 UI 檔，和 `r3-menu-stages` 同層平行不衝突。
4. `r3-menubar-states` 承接 Q5 在 `MenuBar.swift` 的那一半（停止前的 pid 確認，`MenuBar.swift:428-431`），`r3-lock` 只改 CLI 與 Capture 端，兩者同層不同檔。
5. （修正輪）`r3-latency-log` 併入 `r3-lock`、`r3-notify` 併入 `r3-menubar-states`、`r3-meeting-detect` 併入 `r3-onboarding-settings`，`r3-discard` 排在 `r3-segment-scheduler` 之前；8 層縮成 6 層（R3-D30）。

### R3-D2 開錄鎖、`stop` 的 pid 確認、preflight 互斥（Q1、Q2、Q5、D14b）

- **鎖檔**：`<home>/record.lock`（`<home>`＝`MH_RECORD_HOME`，預設 `~/.meeting-harness`），`flock(LOCK_EX|LOCK_NB)`，`open` 帶 `O_CLOEXEC`（不讓子程序 ffmpeg／python 繼承鎖）。錄製實例的 `start`、`quick-start`、`preflight` 三個子指令在**寫任何狀態檔之前**取鎖（`Capture/Commands.swift:126` 的 `runPreflightThenRecord` 目前先建 `StatusWriter` 寫 `phase=preflight`，改成先取鎖），持有到程序結束（核心在程序結束時自動釋放，當機也不會留下死鎖）。試鎖者（`record.sh`、menu bar 的 stop 確認與 F3 偵測）拿到鎖會立刻放掉，但那一瞬間錄製實例可能剛好要取鎖；所以取鎖與試鎖一律在 1 秒內每 100 ms 重試，1 秒內都拿不到才判定被持有（`spec.md` §3.15）。取不到：不寫狀態檔、不寫 pid 檔、`record.log` 記一行「已有錄製在跑，這次不開錄」，程序結束碼 2。鎖檔本身內容不讀（只有 flock 有意義），所以舊版殘留的鎖檔不影響判斷。
- **為什麼用 flock 不用 pid 檔**：pid 檔（`record.pid`）在 `start()` 的 `:181` 才寫，preflight 期間沒有，而且 pid 會被重用（`q` ★2、★5）；flock 跟著程序生命週期、核心保證互斥。R2 的 menu bar 單一實例已經用同樣做法（`Core/Trigger.swift` 的 `acquireMenuBarLock`），R3 沿用同一個形狀（新函式 `acquireRecordLock(home:)`，回傳既有的 `MenuBarLockResult`）。
- **`record.sh`**：`record`（開錄）在啟動 app 之前用 Python 試鎖（`fcntl.flock` LOCK_EX|LOCK_NB，成功就立刻放掉）：拿不到 → 結束碼 2、stderr「已有錄製在跑（meeting record status 查看；meeting record stop 停止）」，不啟動 app、不碰狀態檔。`preflight` 同樣先試鎖，拿不到 → 結束碼 2、stderr「錄製中，不跑開錄前檢查」，不跑 13 項、不啟動 app（D14b-A）。試鎖成功到 app 取鎖之間有空窗，兩個 `record.sh` 同時過了試鎖時，由 app 端的鎖決定：後到的 app 取不到鎖、不寫狀態檔，該 `record.sh` 等不到本次 `runId` 的狀態，照第一輪 §4.1.6 回 4——這是可接受的退化（不會有兩個實例在錄），記 §7 疑慮 43。
- **暫停中心跳**：暫停期間 `updateRecentLevels` 直接 return（`RecordingSession.swift:640`），狀態檔不再更新。改成暫停中每 5 秒重寫一次狀態檔（只更新 `updatedAt`，其他欄位不變），不加新鍵（R2-Q10 的鍵集合不動）。`record status` 與 menu bar 因此能用 `updatedAt` 判斷實例是否還活著。
- **`stop` 的 pid 確認（Q5）**：`record.sh stop` 與 menu bar 的「停止錄製」送 SIGTERM 前，四項都要成立：(1) `record.lock` 正被持有（試鎖失敗）；(2) `record.pid` 的 pid 活著；(3) `record.status.json.pid` 等於 `record.pid`；(4) `ps -o comm= -p <pid>` 的結尾是 `MeetingRecorder`。任一不成立 → 不送訊號、結束碼 3、stderr 說明哪一項不成立；(2) 不成立時順手刪掉過時的 `record.pid`。menu bar 端的判斷抽成 Core 純函式 `stopTargetDecision`（`spec.md` R3-§3.20），`MenuBar.swift` 不再用 `readPid ?? st.pid`。
- **`stop` 在收尾中**：`phase` 是 `stopping`／`finalizing` 時，`record.sh stop` 不再送 SIGTERM，照現行等待結果（避免第二次 SIGTERM 被當成取消收尾，R3-D3）。
- **`stop` 的等待上限**（修正輪 G）：`record.sh stop` 現行等 2 × 已錄秒數 ＋ 120 秒（`bin/record.sh:560`），比錄製實例的收尾總期限（×3＋600，R3-D3）短，長會議會在 app 還在合法收尾時就回 5。改成 3 × max(0, now − `startedAt`) ＋ 630 秒（多 30 秒給 SIGTERM→SIGKILL 與寫狀態檔），由 `r3-lock` 一起改（`spec.md` §4.27.5）。
- **測試替身與 stop 檢查**（修正輪 A）：既有 stop／status 測試的替身 `fake_recorder.sh` 是 `bash` 程序、不持鎖，四項確認上線後會被拒。採用：第 (4) 項的比對字串可由 `MH_RECORDER_COMM` 覆寫（只在 `MH_RECORD_OPEN` 也有設時生效，與 `MH_RECORD_OPEN` 同類的測試旁路）；替身加 `FAKE_LOCK`（預設開，背景子程序持鎖、父程序一死就放）；`Sandbox.env` 預設帶 `MH_RECORDER_COMM=bash`。既有斷言一字不改（`spec.md` §6 第 136 條，閘門 2 待核准）。其他方案：把替身複製成名為 `MeetingRecorder` 的執行檔——要複製系統的 bash、行為依賴 macOS 的 `p_comm` 規則，不採。
- 其他方案：(a) 只靠 pid 檔加 `kill -0`：pid 重用與 preflight 空窗都擋不住；(b) 用 `O_EXCL` 建鎖檔：當機會留下死鎖、要另寫清理。都不採。

### R3-D3 收尾互斥、逾時、取消、讀不到的段落（Q4、Q3、D12、D14a）

- **收尾鎖（Q4）**：`_record_finalize.py` 開頭在 `錄音/tracks/.finalize.lock` 取 `flock(LOCK_EX|LOCK_NB)`，持有到結束；取不到 → 結束碼 5、stderr「這個場次正在收尾」，不讀不寫任何其他檔（連 `finalize.json` 都不碰）。`write_json_atomic` 的暫存檔改用 `tempfile.mkstemp(dir=同目錄)`，不再用固定的 `.tmp` 後綴。
- **逐步逾時（Q3 的 Python 端）**：每個 `ffmpeg()`／`probe()` 呼叫都帶 `timeout`：`ffprobe` 30 秒；逐段正規化 max(120, 該段長度 × 10) 秒；串接與混音 max(300, 全片長度 × 3) 秒。`MH_FINALIZE_STEP_TIMEOUT`（秒，正數）存在時一律用它（測試用）。逾時：先 `terminate`、5 秒後 `kill`，`finalize.json` 寫 `timedOut: {step, seconds}`，結束碼 5，段落全部保留。每一步的耗時寫進 `record.log`（intent R3-9 的衍生工作併入，也替 D14a 的上限提供依據）。
- **總上限與取消（Q3 的 Swift 端）**：錄製實例跑收尾改由新檔 `Capture/FinalizeRunner.swift` 負責：以 `Process` 啟動、設總期限＝錄製長度（`recordedSeconds`，扣暫停）× 3 ＋ 600 秒（D14a-A；純函式 `finalizeDeadline(recordedSeconds:)`）。逾時或收到取消時對子程序送 SIGTERM、5 秒後 SIGKILL，狀態寫 `phase=failed`、`code=5`，message 含「收尾逾時」或「收尾已取消」與「段落保留，可用 meeting record finish <場次> 重跑」。**取消**＝收尾中再收到一次 SIGTERM（`requestStop` 目前 `guard !stopping` 直接忽略，`RecordingSession.swift:818`；改成 `phase==finalizing` 時轉成取消）；menu bar 在收尾階段提供「取消收尾」（R3-D12）。
- **讀不到的段落（D12-A）**：`skipped` 的段落不再被 `cleanup_segments` 刪掉，改搬到 `錄音/tracks/unreadable/`（同名，撞名加 `-1`、`-2`），`finalize.json` 的 `skipped[]` 每筆加 `movedTo`（相對 `錄音/` 的路徑）。成功收尾後仍只刪可讀且已併入成品的段落（§6 第 111 條改寫，§6 第 126 條）。
- 其他方案：只做 Swift 總上限、Python 不設逐步逾時——`meeting record finish`（CLI 直接跑 Python，沒有 Swift 包著）就仍然會卡死，不採。

### R3-D4 逐字稿源頭（T1、T2、T3、T4、T5）

- **T1**（修正輪 E 改寫）：`_render.py` 產 VTT 時改用和 `_merge_speakers.py` 相同的歸屬：以 `importlib` 載入它**既有**的 `assign_speaker`、`load_speaker_segments`、`UNKNOWN`（`bin/_merge_speakers.py:20`、`:45`、`:47`，模組層函式，有 `__main__` 保護，可直接匯入）；`main()` 裡的套名判準（`:71-81`：有 `apply` 聽 `apply`，沒有就 `confidence` ≥ 0.7）、`MH_MIN_SPEAKER_SEC` 併入（`:93-111`）與退到含重疊那份（`:113-119`）照抄，一致性測試（`spec.md` §4.29.5）保證兩邊對每一段掛的真名相同。對不到名字的講者，VTT 不加 `<v>`（不再用 `_render.py:232-273` 自己的 0.3 比例規則）。`bin/_merge_speakers.py` 一字不改（§4.12.4 照舊，原 §6 第 122 條撤回）。
- **T2**：`run_diarize`（`bin/meeting.sh:247`）不再刪 `transcript.raw.md`。缺 `segments.json` 時，改在暫存目錄重轉一次只為了取得 `segments.json`，raw 與既有衍生檔一律不動；暫存目錄結束時刪除。
- **T3**：`bin/transcribe.sh` 拿掉沒有作用的 `--compression-ratio-threshold 2.4`；`meeting-transcribe` SKILL.md 對應的描述改成實際行為。
- **T4（VAD clip）**：有聲判斷＝同一個 0.5 秒時段 max(系統聲音, 麥克風) > -60 dBFS（`null` 視為無聲）；相鄰有聲區間的空隙 < 2.0 秒就合併；每段前後各補 0.75 秒（不超出 0 與全長）；暫停區間先依 `pauseEvents` 換成成品時間（`_record_lib.output_time`），所以 clip 是成品時間軸上的區間。送給 ASR 的參數是 `clip_timestamps`。環境變數：`MH_VAD`（`0` 關閉，預設開）、`MH_VAD_THRESHOLD_DB`（預設 -60）、`MH_VAD_PAD`（預設 0.75）、`MH_VAD_MERGE_GAP`（預設 2.0）。沒有 `manifest.json.levels`（ingest 進來的舊檔、非錄製器產的音檔）或全場都沒有有聲區間時，退回現行做法（整檔送）。raw 標頭在 `> 來源：… 模型：…` 之後多一行 `> VAD：clip <N> 段，門檻 <x> dBFS，補 <p> 秒，合併間隔 <g> 秒`（沒套用時寫 `> VAD：未套用（<原因>）`）。實際門檻要用 R3 實機驗收場的 `keep-segments` 真實多人會議調（D13），預設值只是起點。
- **T5（品質檔）**：`segments.json` 一律輸出（不再只在 `MH_EMIT_SEGMENTS=1` 時）。新增 `transcript.quality.json`：陣列，每筆 `{start, end, reason}`，`reason` ∈ `compression_ratio`（該段 zlib 壓縮比 > 2.4）、`no_speech_loop`（同一句連續重複 ≥ 3 次）、`repeat_run`（相鄰 ≥ 4 段文字相同）；沒有問題就寫 `[]`。`QUALITY_WARNING` 的既有格式（`transcribe.sh:141-184`）保留。衍生檔（`transcript.speakers.md`、VTT）裡被列入品質檔的段落，文字前加「（聽不清）」，raw 不改（鐵則 1、4）。`speakers.md` 的部分由 `_render.py --annotate-speakers` 後處理加（R3-D5），所以由 `r3-annotations` 做（排在 `r3-vtt-raw` 之後，intent R3-8 的要求）。

### R3-D5 標示與標記（T6、T7、D11）

- **來源**：`record.meta.json` 的 `pauseEvents`、`micMuteEvents`、`deviceEvents`，`manifest.json.levels`（兩路都 ≤ -60 dBFS 連續 ≥ 30 秒為「長靜音」），`錄音/markers.json`（R2，`t` 已是成品時間）。全部先換成成品時間。
- **`speakers.md` 改成後處理**（修正輪 E）：`_merge_speakers.py` 不改，`run_diarize` 在它成功後呼叫 `python3 "$BIN/_render.py" <場次> --annotate-speakers`。後處理用 T1 同一套歸屬重建 block（知道每個 block 由哪些段落組成、各段文字在 block 文字中的位置），只插入註記行與「（聽不清）」；重建結果與檔案對不上的 block 不動並記 stderr；冪等。`r3-vtt-raw` 先在 `meeting.sh` 接好掛勾與空的 `--annotate-speakers`，`r3-annotations` 補內容（兩者本來就是序列鏈）。
- **寫到哪裡**（只寫衍生檔，raw 不動）：`transcript.speakers.md` 與 VTT 在對應時間插入註記行（例「〔暫停 02:10–03:40，這段沒有錄〕」「〔麥克風靜音 05:00–05:30〕」「〔輸出裝置切換：內建 → 藍牙〕」「〔標記 1〕」）；VTT 的註記用 `NOTE` 區塊，不佔 cue。
- **對齊規則**：標記與事件時間 t 落在某段 `start ≤ t < end` 就掛在該段；落在兩段之間就掛到下一段；離最近一段超過 2 秒就獨立成一行。
- **`meeting.record.json`**：v1 加選用 `markers[]`，每筆 `{label, t, speaker?, note?}`（`t` 為成品秒數）；`schema/meeting-record.v1.json` 加這個選用屬性，`required` 不變（D11-A）。
- **summary**：`_render.py` 在五個必備段之後加「## 標記」（有標記才出現）與「## 錄製註記」（有暫停、靜音、裝置切換或長靜音才出現）。資料先取 `meeting.record.json.markers`，沒有就取 `錄音/markers.json`／meta。`bin/summarize-local.py` 的地端 summary 也接上這兩段（呼叫 `_render.py` 的同一個函式，修正輪 J；歸 `r3-annotations`），雲端與地端的 `summary.md` 段落一致（`summarize-local.py:68-71` 原本就要求兩邊長得一樣）。「一句話：」與決議、依賴、風險、交辦四段不動；下游知識庫專案的 `meetings._missing_sections()` 只檢查四段必備標題存在，多出段落不影響（`spec.md` §4.31.8 用它實測）。

### R3-D6 `bin/lib/_record_lib.py` 與共用測試向量（Q9a）

- 位置（修正輪 E）：`bin/lib/_record_lib.py`（新目錄 `bin/lib/`；`_search.py`、`_reminders.py` 同）。`bin/` 頂層不新增檔，`_lint.sh` 檔數維持 26、`test_lint_passes_26_files` 不改；`_lint.sh` 不掃子目錄，語法另由 `test_r3_record_lib.py::test_bin_lib_syntax` 驗（`spec.md` §4.32.5）。
- 函式：`merge_defaults(home, updates, timeout=5.0)`（`record.defaults.json` 的取鎖讀後合併寫入，`record.sh` 的 `write_defaults` 與 `meeting sync` 共用，`spec.md` §3.19）；`output_time(t, first_start, pauses, l_out=0.0)`（語意同 Swift `outputTime`；`l_out` 是 S-C 預留：系統聲音在成品裡再晚 `l_out` 秒時，從系統聲音推回成品時間要加上它；預設 0 時結果與 `e2e_check.record_to_output` 完全相同）、`paused_total(pauses)`、`levels_intervals(levels, window, threshold_db, merge_gap, pad, total)`、`clip_timestamps(rec_dir)`（讀 `tracks/manifest.json` 與 `tracks/record.meta.json`，回成品時間的有聲區間；資料不足回 `None`）。CLI：`python3 bin/lib/_record_lib.py clip <錄音目錄>` 印 JSON（`null` 表示退回整檔），結束碼 0；目錄不存在 2；`python3 bin/lib/_record_lib.py sync [mode]` 是 `meeting sync` 的實作（`spec.md` §3.19）。
- 共用向量：`tests/record/vectors/output_time.json`、`levels_intervals.json`，Python 與 Swift（`R3RecordLibVectorTests` 讀同一份檔）各跑一遍，保證兩邊語意一致（`q` ★9）。`e2e_check.py` 的 `record_to_output` 不改（避免動到既有判準），由向量測試保證兩者相等。

### R3-D7 搜尋與提醒事項（F1、F5；R3-Q3 定案）

- **F1**：`meeting search <根> <關鍵字>`（`bin/lib/_search.py`）。只搜單一根目錄底下各場次的 `summary.md`、`transcript.speakers.md`、`transcript.raw.md`、`meeting.record.json`（大小寫不分、純文字比對，不用 regex）；輸出每筆「場次相對路徑:行號: 該行（前後截到 120 字）」，依場次日期新到舊。結束碼：0 有結果、1 沒有、2 參數錯或根目錄不存在。不跨根目錄（客戶資料邊界）。
- **F5（R3-Q3 定案：app 寫、CLI 觸發）**：TCC 權限跟著 app bundle，所以 EventKit 寫入由 MeetingRecorder 的新子指令 `reminders --input <json> --list <名稱>` 做；`meeting reminders <場次> --list <清單名> [--dry-run]` 由 `bin/lib/_reminders.py` 從 `meeting.record.json.actions[]` 組出待寫項目（UID 用和 `actions.ics` 同一個組法 `f"{id 或 title}-{aid}@meeting-harness"`，抽成 `_reminders.py` 自己的函式並以測試保證與 `_render.py` 結果相同，不改 `_render.py`），再以 `open -W -n -a … --args reminders …` 交給 app。去重：每個提醒事項的 `URL` 設為 `meetingharness://action/<uid>`，寫入前先 `fetchRemindersMatchingPredicate` 讀出該清單已有的 URL，有就更新標題與備註、沒有就新增，所以可重跑。負責人或期限缺值：期限不設、負責人寫「（未定）」，不補猜（鐵則 2）。清單不存在不代建（結束碼 3）；權限被拒 4；寫入失敗 5；`--dry-run` 只印項目不啟動 app，回 0。API 已在本機 SDK 標頭查到：`requestFullAccessToRemindersWithCompletion:`（macOS 14 起）、`saveReminder:commit:error:`、`fetchRemindersMatchingPredicate:completion:`、`predicateForRemindersInCalendars:`、`EKCalendarItem.URL`；Info.plist 的 `NSRemindersFullAccessUsageDescription` 鍵名不在標頭裡，要查 Apple 文件確認（§7 疑慮 45）。說明文字要寫「清單開了 iCloud 同步時，內容會離開本機」。**hardened runtime**（修正輪 D）：固定身分簽章帶 `--options runtime`，EventKit 可能還要 `com.apple.security.personal-information.calendars`；加不加由閘門 2 決定（`spec.md` §7 疑慮 57、§6 第 138 條）。

### R3-D8 影音一致：量測與延遲紀錄（S-A、D3、S-B）

- **S-A**：`e2e_check.py` 的 `--sync`／`c_sync`（ffplay 路徑、每個閃白與嗶聲 < 100 ms）**保留不改**，改名義為「錄製器沒有引入額外偏移」的迴歸檢查。新增 `--sync-acoustic`：用喇叭外放的同步測試源，量每個嗶聲在麥克風路與系統聲音路的時間差（mic − sys），輸出各 60 秒時段的中位數，供 S-C 校正用（只報數字，不判 PASS／FAIL）。新增 `--sync-player`：以補償型播放端的判準（D3-A）判定——每個 60 秒時段的閃白／嗶聲差取中位數，|中位數| 全部 < 45 ms 為 PASS；成品若有 `finalize.json.syncCompensation` 就把套用的延遲算進去。另加 `--print-sync-file <輸出路徑>` 產生給 QuickTime／Chrome 播放的同步測試檔（只寫到指定路徑）。§4.9.3 的 sync 判準由 D3 改寫（§6 第 124 條）。
- **S-B**：開錄時與每次 `deviceEvents` 寫入時，另外讀一次輸出裝置的 `kAudioDevicePropertyLatency`、`kAudioDevicePropertySafetyOffset`、第一個 output stream 的 `kAudioStreamPropertyLatency`、`kAudioDevicePropertyBufferFrameSize`、`kAudioDevicePropertyNominalSampleRate`（都只讀；本機 SDK 標頭已確認存在），寫到 `record.meta.json.outputLatencies[]`（新的選用欄位，nil 省略鍵）。**不放進 `AudioDeviceInfo`**：那個結構是 Equatable，裝置監看用 `now != before` 判斷要不要記 deviceEvent（`AudioDeviceMonitor.swift:84`），延遲值在 A2DP↔HFP 會變，放進去會多出假的 deviceEvent。讀取失敗的欄位寫 null，不影響錄製。

### R3-D9 S-C：finalize 依時段補償系統聲音（ADR `adr-r3-sync-compensation.md`、`adr-r3-concat-then-mix.md`）

- **開關**：`record.defaults.json` 的 `syncCompensation` ∈ `off`｜`reported`｜`calibrated`，缺鍵＝`off`；環境變數 `MH_SYNC_COMPENSATION` 有值時優先（實機驗收場用來對同一場次重跑比較）。寫入由 CLI 新寫法 `meeting sync [off|reported|calibrated]` 做（不帶參數＝印目前值；R3-Q6 定案；修正輪由 `meeting record sync` 改為頂層，R3-D30），app 不寫。**預設 off**，要不要改預設由 R3 實機驗收場 E2／E4 的結果決定（使用者決定 2）。
- **延遲值**：`reported`＝(Latency ＋ SafetyOffset ＋ stream Latency ＋ BufferFrameSize) ÷ NominalSampleRate（取該時段生效的那筆 `outputLatencies`）；`calibrated`＝讀 `~/.meeting-harness/sync-calibration.json` 的 `{"<輸出裝置 uid>": 秒數}`，查不到的裝置用 0（並在 `finalize.json` 記 `source: "missing"`）。值限制在 [0, 0.5] 秒，超出就夾住並記 `clamped: true`。
- **依時段**：錄製器在輸出裝置變更時一律提前換段（新的 `SwitchReason.outputDeviceChange`；off 也換，所以段落切分可能和現行不同，intent R3-4 第 6 點）。因此「一段只對應一個輸出裝置」，延遲以段為單位套用。
- **混音流程（只在非 off 時改）**：off 時走現行 D20 流程，程式路徑完全不變。非 off 時：影片照現行逐段正規化；系統聲音與麥克風各自逐段解成 PCM、整條串接；系統聲音**整條連續延後**（修正輪 C）：把相鄰且 L 相同的段落併成一個區間，第一個區間前補 L_1 秒靜音，之後只在 L 改變處調整——L 變大補 (L_k − L_{k−1}) 秒靜音、L 變小截掉前一區間的尾 (L_{k−1} − L_k) 秒（重疊的部分），最後截到與 off 相同的總長；每 60 秒的定期換段 L 不變，所以段界沒有空洞也不掉聲音。再與麥克風混音、限幅、一次編 AAC。（前一版寫「段內延後 L_i、段尾截掉 L_i」，每 60 秒會掉 L_i 秒系統聲音，已改。）`finalize.json` 加 `syncCompensation: {mode, segments: [{file, outputUid, delaySeconds, source, clamped}]}`。
- **off 的「等價」判準**（intent 要求由 design 定、test 段驗）：同一份 `tracks/` 在 off 下收尾，與現行版本比較：(1) 全套 e2e 迴歸判準全部 PASS；(2) 成品長度差 ≤ 0.1 秒；(3) `--sync` 的閃白／嗶聲差與現行版本相比，每個事件的變化 ≤ 1 個視訊幀（1/60 秒）。不要求逐位元相同（輸出裝置變更時的提前換段會改變切分）。
- 其他方案與取捨見兩則 ADR。

### R3-D10 `SegmentScheduler`（Q6；R3-Q1＝A）

- 把 `RecordingSession` 目前散在 `ingest`（`:392`）、`startNewSegment`（`:474`）、`writerFailed`（`:560`）、prev 收尾的編排決策抽成 Core 的純狀態機 `SegmentScheduler`：輸入是事件（sample 到達含起訖時間、來源與是否格式變更、暫停、繼續、輸出裝置變更、writer 失敗、prev 收尾逾時、停止），輸出是動作清單（`open(reason:boundary:)`、`write(to: cur|prev)`、`drop`、`finishPrev`、`finishCurrent`、`cancel(segment:)`）。`PauseGate`／`pauseRoute`／`openReason`（R2-D3a）由它呼叫，不改語意。
- `RecordingSession` 只負責執行動作（`AVAssetWriter` 的建立、寫入、收尾），不再自己判斷。行為測試用假 writer 在 Core 測試裡跑事件序列：暫停／繼續、停止時目前段是空的、writer 連續失敗、prev 收尾逾時（1 秒）、格式變更、輸出裝置變更。
- 這是熱路徑的重構：`r3-segment-scheduler` 合併後要用全套 e2e 迴歸重驗（R3 實機驗收場最後一項）。
- **既有靜態測試**（修正輪 B）：`test_r2_static.py` 的 `test_capture_pause_gate_before_maxend`、`test_capture_uses_core_pause_functions` 與 `test_static_rules.py::test_segment_writer_uses_assetwriter` 要求暫停閘門與 `routeSample(` 出現在 `RecordingSession.swift`／`Capture/`；接手後它們在 `Core/SegmentScheduler.swift`。替代寫法（在 `RecordingSession` 留一份呼叫湊字面）會讓檢查失去意義，所以改綁到新檔（`spec.md` §6 第 137 條，閘門 2 待核准），`SegmentScheduler` 照 §4.36.11 的形狀寫（`ingest`、`maxEnd`），`r3-core` 合併後就綠、`r3-segment-scheduler` 的完成條件要跑 `test_r2_static` 的 `test_capture_*`。

### R3-D11 選單列圖示、通知、HUD（U1、U3、U2、D4）

- **U1**：保留 `MenuBarState` 與 `symbolName`（既有測試與相容），新增 `MenuBarAppearance` 8 種：`idle`、`preparing`、`recording`、`recordingMuted`、`recordingAlert`、`paused`、`finalizing`、`failed`；由 `menuBarModel` 的列決定（M1／M5→idle；M8→preparing；M9→recording，`micMuted` 時 recordingMuted；M7→recordingAlert；M6b→paused，有告警時 `alertBadge=true`；M6a／M10→finalizing；M2／M3／M4／M6→failed）。準備中與收尾中不再用紅點。8 種只看形狀就分得出來（不靠顏色）；外觀定案為 U1-C 錄製膠囊（R3-D21），形狀與色彩由 Core 的 `menuBarCapsuleStyle` 決定。`MenuBarModel` 加 `appearance`、`alertBadge`、`spokenDuration`（VoiceOver 讀的「已錄 1 小時 2 分」，不讀「01:02:00」）。status item 設 `autosaveName`（intent R3-9 衍生工作併入）。
- **U3**：新的 Core 純函式 `notificationPolicy(kind:runId:)` 回 `(interruptionLevel, threadIdentifier)`：錄製中告警（`WarningKind.isAlert` 的新告警）＝`timeSensitive`、其餘＝`active`；`threadIdentifier`＝`runId`（沒有 runId 的 app 層通知用 `"mh.app"`）。`newAlertWarnings(previous:current:)` 只回新增的告警，同一則告警不重複發。**不加 Time Sensitive entitlement**：`UNUserNotificationCenter.h:31` 註明要 entitlement，但 §4.2.8 規定 entitlements 恰為 2 項、自簽下加 entitlement 可能讓 app 啟動失敗；本輪只設 `interruptionLevel`，系統不給時退回一般通知，由實機驗收場確認（§7 疑慮 44）。通知內容預設不露出場次名或視窗標題（intent R3-4 第 8 點）。
- **U2（HUD）**：`HUDMode` ∈ `auto`（預設，D4-A）、`always`、`never`。`hudVisible(mode:obscured:phase:)`：只在錄製中或暫停中顯示；auto 時 `obscured` 為 true 才顯示。HUD 內容：紅點（或暫停／靜音狀態）、計時、系統聲音與麥克風兩格音量條；滑鼠移上去出現暫停／靜音／標記／停止四個按鈕（走與選單相同的控制路徑）。外觀定案為 U2-C 收在螢幕邊緣，告警時標籤變注意色並自動展開 8 秒（R3-D21）。`NSPanel` 非啟用、所有桌面可見、`sharingType = .none`（能否擋住其他 app 的分享由實機驗收場確認，intent R3-5 第 5 點）。
- **快捷鍵回饋改走 HUD**（推翻 §6 第 105 條）：`feedbackRoute(hudVisible:iconVisible:)`＝HUD 看得到→`hud`；HUD 看不到但圖示看得到→`none`（圖示本身會變）；兩者都看不到→`notification`。**圖示被擋住的偵測改成持續進行**（推翻 §6 第 106 條「只發一次」）：每 5 秒檢查一次 `statusItemObscured`，結果決定 auto 模式的 HUD 與上面的回饋路徑；`obscuredAction(previous:current:mode:)` 只在狀態改變時動作。

### R3-D12 選單依階段顯示（U6；ADR `adr-r3-menu-stages.md`）

- `menuStage(model)` ∈ `idle`、`recording`（含準備中與暫停中）、`finalizing`、`failed`；`menuItems(stage:)` 回該階段的項目清單（純函式，`spec.md` R3-§3.20 有完整表）。不屬於目前階段的項目**隱藏**，不再灰掉（推翻 §4.20.6；ADR）。階段內仍可能有暫時不能用的項目（例：錄製中 `canControl` 為 false 時的暫停），這些照舊灰掉。
- 收音改成即時音量條（自訂 `NSMenuItem.view`，兩條、每 0.5 秒更新），VoiceOver 讀「系統聲音有聲／無聲、麥克風有聲／無聲／已靜音」；macOS 26 的鍵盤導覽與 VoiceOver 行為未確認，先做原型（intent R3-5 第 9 點）。
- 失敗改成詳情小視窗（`Trigger/FailureDetail.swift`）：顯示 message、補救指令、`record.log` 位置與「複製完整訊息與補救指令」按鈕；選單的「錯誤詳情…」打開它。
- 收尾階段有「取消收尾」（R3-D3）。

### R3-D13 捨棄這次錄製（F2；R3-Q2 定案）

- 只在選單的錄製階段提供「捨棄這次錄製…」；**不加 CLI 對等子指令**（R3-Q2：避免其他 session 刪資料；沒有 tty 的路徑一律不存在）。
- 流程：確認對話框（F2-A：系統 `NSAlert`，預設按鈕是「繼續錄製」，破壞性按鈕「捨棄並移到垃圾桶」要明確點、沒有快捷鍵；文字說明「會停止錄製、不收尾，這場的錄音資料夾會移到垃圾桶，可從垃圾桶復原」；字面見 `spec.md` §4.42.2）→ 使用者確認後 menu bar 寫 `<home>/record.discard.json` `{schemaVersion:1, runId, requestedAt}`（tmp＋rename）→ 照 R3-D2 的 pid 確認送 SIGTERM。
- 錄製實例收到 SIGTERM 時讀 `record.discard.json`：`runId` 相符且 `requestedAt` 在 30 秒內 → 停止擷取、取消 writer、**跳過收尾**，用 `FileManager.trashItem(at:resultingItemURL:)` 把 `<場次>/錄音/` 移到垃圾桶；之後 `<場次>` 若只剩 `meeting.json`（與 `.DS_Store`），把 `<場次>` 也移到垃圾桶。**從不硬刪**。狀態 `phase=done`、`code=0`、message「已捨棄，錄音已移到垃圾桶」，新選用欄位 `discarded: true`（nil 省略鍵）。移到垃圾桶失敗 → `phase=failed`、`code=5`、檔案原地保留。`runId` 不符或過期的 `record.discard.json` 當作沒有，照一般停止收尾；開錄時（`resetControl` 同一處）刪掉殘留的 `record.discard.json`。
- `shouldAutoPrep` 對 `discarded` 為 true 的結果不觸發前處理。

### R3-D14 首次引導、設定分頁、app 圖示（U4、U5、U7、D7；ADR `adr-r3-defaults-writers.md`）

- **新設定檔** `<home>/menubar.settings.json`（app 唯一寫者）：`showTimer`、`hudMode`、`hudPosition`、`timeSensitiveAlerts`、`lastSettingsTab`、`onboardingCompletedAt`、`meetingDetect`。R2 的 `menubar.prefs.json`（6 鍵，`MenuBarR2Tests.swift:258` 斷言）不動，避免改既有鍵集合測試。
- **U4 首次引導**（U4-A 分步精靈 5 步，R3-D21）：`onboardingCompletedAt` 為 nil 時，menu bar 啟動後顯示引導視窗，步驟：歡迎 → 權限（螢幕錄製、麥克風、通知、自動化〔選用〕；按鈕只觸發 TCC 授權框或打開系統設定，不做其他系統設定變更）→ 存檔位置（含 harness）→ 選單列空間（提示圖示可能被瀏海擋住、HUD 的作用，可一鍵改成一律顯示 HUD）→ 試錄（含四組快捷鍵說明；試錄走既有 quick-start，錄 5 秒後自動停止並捨棄——用 R3-D13 的路徑，移到垃圾桶）。每一步可略過；完成或略過全部時寫 `onboardingCompletedAt`。
- **app 寫 `record.defaults.json`**（推翻 R2-Q3）：只在引導的「存檔位置與 harness」一步，以 `writeOnboardingDefaults(home:harness:root:)` 寫 `harness` 與 `root` 兩個鍵：取 `<home>/record.defaults.lock` 的 flock → 讀現有內容 → 只改這兩鍵、其他鍵原樣保留 → `mkstemp`＋rename。`record.sh` 的 `write_defaults`（`bin/record.sh:329-341`）改成拿同一把鎖、讀後合併（保留 app 與 `record sync` 寫的鍵），由 `r3-lock` 先做。
- **U5 設定視窗**改成 7 個工具列分頁（U5-A：一般、錄製、回饋與通知、快捷鍵、錄完之後、權限、進階；R3-D21）；快捷鍵分頁只顯示、不能改（D7-A）；回饋與通知分頁含 HUD 模式與位置、F3 的開關與 Time Sensitive 說明；進階分頁顯示 `syncCompensation` 目前值（唯讀，改要用 CLI）。視窗標題跟著分頁變（HIG；推翻「MeetingRecorder 設定」，`spec.md` §6 第 130 條）。
- **U7 app 圖示**：`Resources/AppIcon.icns`（U7-A 錄製點＋聲波，幾何比例見 `design-r3/README.md` §6.4），`Info.plist` 加 `CFBundleIconFile`，`build.sh` 把它複製進 bundle。
- 引導與設定的文字不得含真實名稱；範例用「[Stand-up] 範例專案」。

### R3-D15 會議偵測提示（F3；R3-Q4 定案）

- 條件全部成立才提示：(1) `menubar.settings.json.meetingDetect` 為 true（預設 true）；(2) 預設輸入裝置的 `kAudioDevicePropertyDeviceIsRunningSomewhere` 為 true（只讀屬性，不開麥克風，不會讓藍牙切到 HFP）；(3) 前景 app 的 bundle ID 在 ★ 清單（沿用 `Core/WindowList.swift` 的會議 app 清單）；(4) `record.lock` 沒被持有（排除本工具自己的 preflight 與錄製）；(5) 同一個 episode 還沒提示過。episode＝輸入裝置從「沒在用」變成「在用」到變回「沒在用」為止；每 3 秒輪詢一次。
- 通知「錄這個會議？」（F3-A 一般通知，內文只放 app 名稱：「<app 名稱> 正在使用麥克風。要開始錄製嗎？」）兩個動作：「開始錄製」→ 走既有 quick-start（用上次的設定）；「這場不用」→ 本 episode 不再提示。**不自動開錄**。通知內容不放視窗標題。
- 決策抽成 Core 純函式 `meetingPromptDecision`，episode 狀態也是純值。

### R3-D16 UI 設計稿流程（R3-Q7；R3-Q8＝B）

- design 段先用 Claude Design 依 `ui` §4 與 `brief` 的設計 token 出稿：D1（U1 圖示 8 種）、D2–D6（U6 選單各階段、音量條、失敗詳情）、D7（U2 HUD）、D8（U5 設定分頁）、D9（U6）、D10（U4 引導）、D11（U3 通知，系統原生外觀，只定文字）、D12（U7 圖示）；F2 的確認對話框與 F3 的通知也一併出稿。`brief` 的建議方向：U1-B、U2-A、U6-A、F2-A、F3-A、U4-A、U5-A、U7-A。
- 使用者挑定後存到 `specs/meeting-record/design-r3/`（存之前照 intent R3-4 第 8 點掃名稱），再把 spec 的外觀佔位換成稿的路徑與要點（SF Symbol 名、顏色 token、尺寸、文字）。**2026-10-13 已完成**（R3-D21）。**這一步是 UI 子任務開工的前提**：`r3-menubar-states`、`r3-hud`、`r3-menu-stages`、`r3-onboarding-settings`、`r3-discard`（確認框）、`r3-meeting-detect`（通知）的外觀相關靜態測試，要等稿挑定才寫得出字面。行為、狀態機、無障礙與結束碼不等稿。

### R3-D17 Swift 原始碼切分（增補 `design.md §9`、R2-D13）

```
Sources/Core/Lock.swift            新增：acquireRecordLock、stopTargetDecision、finalizeDeadline、discardRequestValid
Sources/Core/Appearance.swift      新增：MenuBarAppearance、menuStage、menuItems、HUDMode、hudVisible、feedbackRoute、obscuredAction、
                                        NotificationKind、notificationPolicy、newAlertWarnings、spokenDuration
Sources/Core/Settings.swift        新增：MenuBarSettings（menubar.settings.json）、mergedDefaults、writeOnboardingDefaults
Sources/Core/SegmentScheduler.swift 新增：SegmentScheduler 狀態機（事件 → 動作）
Sources/Core/SyncLatency.swift     新增：OutputLatency、reportedLatencySeconds、outputTime 的 lOut 版本（共用向量）
Sources/Core/MeetingDetect.swift   新增：MeetingEpisode、meetingPromptDecision
Sources/Core/DesignTokens.swift    新增：DarkroomColor／DarkroomType／DarkroomMetric、contrastRatio、CapsuleStyle、menuBarCapsuleStyle（R3-D21）
Sources/Core/Records.swift         RecordMeta.outputLatencies、RecordStatus.discarded（Optional，nil 省略鍵）
Sources/Core/Segments.swift        SwitchReason.outputDeviceChange
Sources/Core/Trigger.swift         MenuBarModel 加 appearance、alertBadge、spokenDuration（有預設值）
Sources/Capture/                   Commands（先取鎖）、PreflightRunner（同）、RecordingSession（心跳、取消、S-B、捨棄、Scheduler 接線、提前換段）、
                                        AudioDeviceMonitor（延遲讀取）、FinalizeRunner.swift（新）、Reminders.swift（新）
Sources/Trigger/                   MenuBar（外觀、通知、HUD、捨棄、階段選單、引導入口、偵測）、HUD.swift、Discard.swift、FailureDetail.swift、
                                        LevelMeterView.swift、Onboarding.swift、MeetingDetect.swift（新）、Preferences（分頁）
Sources/main.swift                 新子指令 reminders
Resources/                         Info.plist（提醒事項權限說明、CFBundleIconFile）、AppIcon.icns（新）
```

### R3-D18 測試策略增補

- Python：每個子任務一支 `tests/record/test_r3_<slug>.py`（例 `test_r3_lock.py`），所以每層「預期轉綠」的測試可以機械列出（`plan.md §10.3`）；app 端只能做靜態檢查的子任務集中在 `test_r3_app_static.py`，以類別名區分歸屬（`LockStatic`、`FinalizeRunnerStatic`……）。
- Swift：`R3LockTests`、`R3MenuBarTests`、`R3SegmentSchedulerTests`、`R3SyncTests`、`R3RecordLibVectorTests`，登記在 `Tests/main.swift` 的 `mrtSuites`；Core 全部由 `r3-core` 一次轉綠。
- 既有測試預期的修改只有 `spec.md` R3-§6 列出、經使用者核准的那幾條（第 117 條起；第 117、122、125 條已撤回），其餘一字不改。
- 替身與 helper（修正輪 A）：`fakes/fake_recorder.sh` 加 `FAKE_LOCK`（預設開）、`fakes/fake_open.sh` 的取鎖模擬用 `FAKE_OPEN_LOCK`（預設關）、`_helpers.Sandbox.env` 加 `MH_RECORDER_COMM=bash`，都只加不改既有行為（`spec.md` §6 第 136 條）。
- `bin/lib/*.py` 不在 `_lint.sh` 掃描範圍，語法由 `test_r3_record_lib.py::test_bin_lib_syntax` 驗。
- **`has_ui`**：R3 有 HUD、引導、設定分頁、失敗詳情、確認框與新圖示，test 段 `has_ui=true`，派 `dev-design-reviewer`，以挑定的設計稿與 macOS HIG 為依據；截圖由使用者在實機驗收場截（agent 不得啟動 app）。`has_security` 維持 false（F5 的 TCC 權限與 F2 的垃圾桶都只在本機，不涉及服務）。

### R3-D19 R3 待決問題定案總表

| # | 定案 | 理由（細節見上） |
|---|---|---|
| R3-Q1 | （閘門 1 使用者決定 A）納入 `r3-segment-scheduler`，排在 `r3-sync-compensate` 之前 | R3-D10 |
| R3-Q2 | F2 只在選單；不加 CLI `discard` | R3-D13 |
| R3-Q3 | EventKit 由 app 子指令 `reminders` 寫；CLI `meeting reminders` 組資料、觸發 | R3-D7 |
| R3-Q4 | 開錄鎖排除本工具；只在 ★ 清單前景 app 時提示；一個 episode 一次 | R3-D15 |
| R3-Q5 | 兩個寫者共用 `record.defaults.lock`、讀後合併；`r3-lock` 先改 `record.sh` | R3-D14、ADR |
| R3-Q6 | `syncCompensation` 鍵＋`meeting sync`（修正輪改為頂層）；`calibrated` 讀 `sync-calibration.json` | R3-D9、ADR、R3-D30 |
| R3-Q7 | 設計稿存 `design-r3/`，挑定後才補 spec 的外觀字面；UI 子任務等稿 | R3-D16 |
| R3-Q8 | （閘門 1 使用者決定 B）U1、U2 也走設計稿 | R3-D16 |
| 設計稿 | （design 段使用者選定）U1＝C、U2＝C、U4＝A、U5＝A、U6＝A、U7＝A、F2＝A、F3＝A；設計語言「暗房」 | R3-D21 |
| 字型 | 預設不打包，退回系統字；打包待決（`spec.md` §7 疑慮 54） | R3-D22 |
| D3 | A：補償型播放端按時段中位數 \|d\| < 45 ms；ffplay 的 `--sync` 保留為迴歸 | R3-D8 |
| D4 | A：HUD 預設 auto | R3-D11 |
| D7 | A：快捷鍵不開放自訂 | R3-D14 |
| D9 | A：「我方（本機麥克風）」不直接掛本人姓名（雙軌歸屬延後） | 本輪不實作雙軌歸屬 |
| D11 | A：v1 加選用 `markers[]` | R3-D5 |
| D12 | A：讀不到的段落搬到 `tracks/unreadable/` | R3-D3 |
| D13 | A：一場實機驗收（使用者在場） | `spec.md` §4.47 |
| D14a | A：錄製長度 × 3 ＋ 600 秒 | R3-D3 |
| D14b | A：錄製中 preflight 回 2 | R3-D2 |

### R3-D21 設計稿定案：設計語言「暗房」（2026-10-13，使用者選定）

- 依據：run 目錄 `r3-design-choices.md`（使用者選定）與設計稿原始檔；稿與實作規則存在 `specs/meeting-record/design-r3/`（`README.md`＋9 個 `*.dc.html`，存前後都掃過名稱）。設計稿的私人連結不寫進 repo。
- 使用者指定：不用 macOS 原生風格、不用既有設計系統，採自訂的「暗房」：深石墨底（墨 `#0F1115`／面 `#171A21`／浮 `#1F232C`；淺色 `#F6F5F2`），單一訊號色（錄製 `#FF4D4F`、注意 `#F5A524`、處理 `#8B7CF6`、完成 `#2DD4BF`，亮度也拉開，灰階可分）。
- 各畫面：U1＝C 錄製膠囊（含麥克風靜音分段膠囊）；U2＝C 收在螢幕邊緣；U4＝A 分步精靈 5 步；U5＝A 7 個工具列分頁；U6＝A 依階段整份換掉；U7＝A 錄製點＋聲波；F2＝A 確認對話框、錄製照常、預設鍵「繼續錄製」；F3＝A 一般通知、內文只放 app 名稱。
- **token 放 Core**：色、字級、間距與選單列膠囊的樣式表都是 `Core/DesignTokens.swift` 的常數與純函式（`spec.md` §3.20），用 Swift 單元測試驗值、驗 WCAG 對比、驗 8 種外觀灰階可分（§4.38.5–§4.38.8）；AppKit 端只負責把 token 畫出來。理由：自訂外觀代表大量自訂 `NSView`，外觀規則若散在 AppKit 檔裡，只能靠截圖審查；放在 Core 才能機械判定。
- **自訂與標準的界線**：自訂＝選單列膠囊（自繪圖）、HUD 整個面板、選單的音量條、引導的步驟條／權限列／主按鈕；標準＝`NSMenu` 本身、設定視窗的控制項、失敗詳情視窗、F2 的 `NSAlert`、F3 的系統通知。界線的理由：選單與 alert 用自訂 view 會失去系統的鍵盤導覽、高亮、VoiceOver 朗讀順序（`spec.md` §7 疑慮 53、56）。
- **深淺色與無障礙規則**：選單列膠囊跟選單列的深淺（`effectiveAppearance`），淺色與「增加對比」用深一階的訊號色（對比補正，稿上沒有；`design-r3/README.md` §1.1）；HUD 一律深色；引導、設定、失敗詳情跟系統深淺色。「增加對比」：膠囊換深一階底、HUD 外框 2pt；「減少透明度」：HUD 不透明；「減少動態效果」：HUD 不做動畫、選單列本來就沒有動畫。VoiceOver 字面見 `spec.md` §4.38.7、§4.40.8、§4.41.4、§4.43.5。
- **與稿不同的地方**（都為了可及性或既有定案）：膠囊字 13→14pt bold（白字對紅 3.27:1，只過大字門檻；§7 疑慮 52）、有告警加角標（稿只換框色，灰階分不出）、F2 用 `NSAlert`、選單不做紅底列、不採用 ⌃⌥⌘R 停止、F2 說明照實際只移 `錄音/`；清單在 `design-r3/README.md` §7。
- **U2-C 的告警加強**（使用者要求「告警時要加強」）：新告警時標籤外框改注意色並維持到本場結束、HUD 自動展開一次 8 秒並顯示告警膠囊（`spec.md` §4.40.7）；8 秒取「讀完一行 20 字左右的告警」與「不長時間遮住內容」的折衷。HUD 不在畫面上時不強制顯示，告警仍走通知（U3）與選單列的告警膠囊。被擋住偵測照 D4＝A：auto 模式下圖示被擋住才自動顯示 HUD（`spec.md` §4.40.1、§4.40.3）。

### R3-D22 字型：預設不打包，退回系統字

- 稿用 Noto Sans TC（介面）、Space Grotesk＋Noto Sans TC 粗體（標題）、JetBrains Mono（計時）。**決定：預設不打包任何字型**，對應到系統字：介面與標題＝`NSFont.systemFont(ofSize:weight:)`（中文落到 PingFang TC、西文 SF Pro）；計時＝`monospacedDigitSystemFont`（SF Pro 等寬數字，R2 已在用）；指令與路徑＝`monospacedSystemFont`（SF Mono）。字級與字重照稿（`DarkroomType`）。`spec.md` §4.43.9 以靜態測試確保沒有偷偷打包。
- 理由：(1) 現況 app 沒有任何字型資源，打包要改 `build.sh`、`Info.plist`（`ATSApplicationFontsPath`）並附授權全文；(2) Noto Sans TC 的中文字集讓 app 明顯變大（實際大小未量）；(3) 選單列與系統通知本來就只能用系統字，打包後 app 內會出現兩套中文字形；(4) 三套字的授權都是 SIL OFL 1.1（可散布，但本輪未從發行頁逐一查證版本與授權）。
- 待決（`spec.md` §7 疑慮 54）：(A) 不打包（預設）；(B) 只打包 JetBrains Mono 給計時（檔小、計時最像稿；代價是仍要改 `build.sh`、`Info.plist` 與附授權，系統通知裡的時間仍是系統字）；(C) 三套都打包（最像稿，代價是 app 變大與授權附檔）。

### R3-D20 不在 R3 範圍、衍生工作（不編號）

- 不在範圍：照 intent R3-2〈不做（本輪）〉（T8 另存兩軌、雙軌歸屬、即時轉錄、T9、Q7–Q10、F4／F6／F7、行事曆會前提醒、靜默自動開錄等）。
- 衍生工作（不編號）：`bin/_profile.py` 的註解名稱疑慮——intent R3-9 已在本 worktree 以兩份清單掃過、結束碼皆為 1，本輪結案不再追；Swift 與 Python 同時寫控制檔時 `markerSeq` 不掉號的整合測試（`q` §6）；設計審查 R2 未處理的 N-2、N-4、N-5、N-6 併入 UI 子任務並由設計稿涵蓋；`meeting search` 與 `meeting reminders` 成為 `meeting` 頂層的保留字（根目錄叫 `search`／`reminders` 要寫 `./search`），記 §7 疑慮 46。

### R3-D30 修正輪（兩個 skeptic 的意見，2026-10-13）

本節列修正輪的決定與理由；細節已改進上面各節與 `spec.md`、`plan.md §10`、ADR。新增的 §6 條號從 136 起、§7 疑慮從 57 起（134、135 與 52–56 屬 UI 設計稿條文）。

**E：三處可避免改既有測試的寫法（評估後全部採用「不改既有測試」）**

| 項 | 原寫法（要改既有測試） | 替代寫法 | 取捨 | 採用 |
|---|---|---|---|---|
| 新 Python 檔 | 放 `bin/`，`test_lint_passes_26_files` 26→29（§6 第 125 條） | 放 `bin/lib/`，`bin/` 頂層不增檔，檔數維持 26 | `_lint.sh` 不掃子目錄（`bin/_lint.sh:12`、`:26` 只掃 `bin/*.sh`、`bin/*.py`），`req:280` 的「新增檔要過檢查」改由 `test_bin_lib_syntax` 涵蓋；三支新檔都是 Python，`_lint.sh` 對 Python 本來也只做 `ast.parse`，涵蓋面相同 | 替代；§6 第 125 條撤回；§4.24.5 照舊成立 |
| T1／T5／T6／T7 | 改 `bin/_merge_speakers.py`（抽函式、加標示），`test_diarize_and_merge_untouched` 拿掉該檔（§6 第 122 條） | `_render.py` 匯入既有的 `assign_speaker` 等，`main()` 的判準照抄＋一致性測試；`speakers.md` 改後處理 | 多一份照抄的判準（約 20 行），由 §4.29.5 的一致性測試鎖住；換來「不動 `_merge_speakers.py`」這條第一輪起的保證（`req` 的 diarize 逐秒一致）完整保留 | 替代；§6 第 122 條撤回 |
| `syncCompensation` 開關 | `meeting record sync`，進 §2.4 封閉清單，改 `surface.py` 與 4 支既有測試（§6 第 117 條） | 頂層 `meeting sync`，不進 `record` 封閉清單 | 頂層多一個保留字 `sync`（與 `search`、`reminders` 同一類，§7 疑慮 46）；語意上「收尾怎麼混音」屬整個工具的設定、不只錄製器，放頂層也說得通；§2.4 的就地修改還原，`test_surface_parsers` 回綠 | 替代；§6 第 117 條撤回，§4.45.2 撤回 |

實作位置：`meeting sync` 的分派在 `bin/meeting.sh`（`r3-search`，它本來就改 `usage()`），寫入用 `bin/lib/_record_lib.py` 的 `merge_defaults`（`r3-record-lib`，第 1 層），`record.sh` 的 `write_defaults` 也改用它（`r3-lock`）。與 intent 的差異：intent R3-3 列的 `bin/_record_lib.py`、`bin/_search.py` 路徑與「要改 `_merge_speakers.py`」改成本節寫法；intent 核准後不改，差異記在此處。

**H：分層 8 層 → 6 層**

| 層 | 子任務 |
|---|---|
| Red | `r3-red-py`、`r3-red-swift` |
| 1 | `r3-core`、`r3-vtt-raw`、`r3-record-lib`、`r3-finalize-guard`、`r3-sync-measure`、`r3-docs` |
| 2 | `r3-lock`（併入 `r3-latency-log`）、`r3-menubar-states`（併入 `r3-notify`）、`r3-search`、`r3-transcript-vad`、`r3-annotations` |
| 3 | `r3-finalize-runner`、`r3-hud`、`r3-reminders` |
| 4 | `r3-discard` |
| 5 | `r3-segment-scheduler`、`r3-menu-stages` |
| 6 | `r3-sync-compensate`、`r3-onboarding-settings`（併入 `r3-meeting-detect`） |

- 合併理由：`r3-latency-log` 只動 `RecordingSession.swift` 的兩處與 `AudioDeviceMonitor.swift`，和 `r3-lock` 同檔，拆開只會多一層；`r3-notify` 與 `r3-menubar-states` 都是 `MenuBar.swift` 的狀態接線；`r3-meeting-detect` 與 `r3-onboarding-settings` 共用設定檔（`meetingDetect` 開關在設定分頁）且都改 `MenuBar.swift`、`Notifier.swift`。
- 排序：`r3-discard` 放在 `r3-segment-scheduler` 之前（兩者都改 `RecordingSession.swift`，捨棄是「停止時跳過收尾」，與 Scheduler 的接線不相依；排前面才能讓 `MenuBar.swift` 鏈與 `RecordingSession.swift` 鏈都在 6 層內走完）。`meeting.sh` 鏈（vtt-raw → search → reminders）與第 1 層不變。
- 同層 `owns` 不重疊以程式驗證（`plan.md §10.1` 的檢查腳本，跑在 run 目錄的 `r3-subtasks.fix.json`）。

**其他**

- C（S-C 混音）：改成整條時間軸連續延後，只在 L 改變處補靜音或截重疊（R3-D9、ADR `adr-r3-concat-then-mix.md`、`spec.md` §4.37.4）。
- D（F5 entitlement）：§7 疑慮 57、§6 第 138 條（條件式）；plan 的「entitlements 恰兩項」改成依疑慮 57 的結果。
- F（`test_regression` 整支綠的時間點）：E 撤回第 122、125 條後，`test_regression.py` 不改、`bin/` 頂層檔數不變，整支自 Red 層起每一層都應綠，各子任務的完成條件與 `plan.md §10.3` 一致改寫。
- G（stop 等待上限）：R3-D2。
- I-1（ADR `adr-r3-menu-stages.md` 背景）：拿掉沒有出處的「t7 時在灰色項目裡找停止」，改成 intent R3-1 第 3 點有出處的敘述（18 項扁平清單、全部灰掉不隱藏；t7 的實測是圖示看不到、快捷鍵連按 9 次）。
- I-2（首次引導的試錄）：試錄改放暫存目錄、錄完直接刪，不移垃圾桶、不加確認框（`spec.md` §6 第 139 條，覆寫 §4.43.5 與 R3-D14 的「走 F2 的捨棄路徑」；閘門 2 待核准）。理由：試錄是引導為驗權限產生的暫存，不是使用者資料、不在使用者的根目錄；每次引導往垃圾桶丟一個資料夾只增加雜訊；確認框對使用者沒有保護作用。刪除範圍限定在本程序剛建立的 `temporaryDirectory/meeting-harness-trial-<runId>/`。
- J（地端 summary）：`bin/summarize-local.py` 也接上「## 標記」「## 錄製註記」，歸 `r3-annotations`（`spec.md` §4.31.9）。

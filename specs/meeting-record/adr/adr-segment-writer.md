# ADR：分段落盤的寫檔機制

- 狀態：**已改決定**（D20，2026-10-11）：由選項 A（`SCRecordingOutput` 輪替）改採選項 B（自管 `AVAssetWriter`）。待使用者在 t6 中途修正輪重新核准 spec／design 後才實作
- 日期：2026-10-11（初版；同日修正輪：量測閘門移到 test 段、併入 D8 每段換尺寸與 D6 格式變更；同日 t6 實機後依 D20 改決定）
- 範圍：`tools/MeetingRecorder/Sources/Capture/`、`tools/MeetingRecorder/Sources/Core/Segments.swift`、`bin/_record_finalize.py`

## 背景

- 需求要求分段落盤、每段獨立可播，crash 後能救回（`req:200`）；D3 把分段長度定為 60 秒。
- 一條 stream 只支援一個 `SCRecordingOutput`（`req:201`、`req:295`），輪替時可能有空隙；門檻 0.5 秒（`req:201`、`req:268`；D3「空隙門檻沿用 0.5 秒」）。
- 第 0 階段只掛過單一 `SCRecordingOutput`，沒有輪替過，空隙大小**沒有本機數據**（`research-requirement.md:220`）。
- 影片只在畫面有變化時寫幀（`tools/MeetingRecorder/PROBE-REPORT.md:27`）→ 靜止的投影片跨過一次輪替時，新段可能完全沒有 video stream（未驗證的推論）。
- D8：每段要以當下視窗大小開檔，換尺寸要在輪替時做（`design.md §7.1`）。

## 選項

| 選項 | 做法 | 好處 | 代價 |
|---|---|---|---|
| A. `SCRecordingOutput` 輪替 | 每 60 秒 `remove` → 等 finish callback →（尺寸變了才）`updateConfiguration` → `add` 新 URL | 系統負責落盤、收尾與混音（`mixesAudioWithMicrophone` 預設混音，`req:161`）；程式碼最少；換尺寸的時點天然落在「沒有 output 掛著」的空檔 | 空隙大小未知，換尺寸可能再拉長空隙；每小時 59 次輪替；靜止畫面跨段可能缺 video stream；HFP 格式變更時的行為未知。**t6 實機：不可行**（見下節） |
| B. 自管 `AVAssetWriter` | 同一條 `SCStream` 不停，`.screen`／`.audio`／`.microphone` 的 sample 由錄製器寫進 `AVAssetWriter`；每段一個 writer，換段時新 writer 從邊界時間接著寫，舊 writer 非同步收尾 | 可無縫輪替；可以保證每段都有首幀；格式變更時自己決定怎麼切段；收尾成敗可觀測（`finishWriting` 的完成回呼與 `status`） | 要自己對齊三路 PTS、處理 `markAsFinished`／`finishWriting` 的順序與失敗——正是需求刻意避開的風險（`req:163` 附近「三個 writer 的音影時間軸對齊」）；混音改到 finalize 用 ffmpeg 做 |
| C. 不分段 | 單一 `SCRecordingOutput` 錄完整場 | 沒有空隙、最簡單 | SIGKILL／斷電丟整場（`req:201`），與「消除漏錄」的目標衝突；D3 的救回驗收必然不過；也無法照 D8 中途換尺寸 |

## 初版決定（已被取代）

初版採 **A**，並在 test 段開頭（t6）設量測閘門；第 1 或第 2 項不過就以 `needs_decision` 回報，由使用者選 B、C 或接受 A 的實測數字。這個流程照做了：t6 量測閘門不過、回報、使用者選 B（D20）。

## t6 實機結果（2026-10-11，`_tpm/runs/20261010-sdlc-meeting-record/t6-results.md`）

1. **A 照設計做（拔掉 → 等 `recordingOutputDidFinishRecording` → 掛新段）**：3 分 16 秒錄製、4 次輪替，`requestedAt → startedAt` 每次約 10.5 秒（最大 10.426、合計 31.179 秒）＝finish 回呼一直沒來、10 秒逾時後才繼續；4 段的 `finishedAt`／`audioDuration` 全是 `null`。§4.4.3（`max(g_i) < 0.5 秒`）**不過**。
2. **實驗 B（拔掉後不等回呼、立刻掛新段）**：整條 stream 中斷，ReplayKit `RPRecordingErrorDomain -5814`（「應用程式連線中斷」），之後什麼都沒錄到。
3. **實驗 C（輪替時先 `stopCapture` 再拔）**：拔掉後 finish 回呼仍未在 10 秒內到（該次實驗另被一個未關乾淨的背景工作中斷，結論只採「回呼沒來」這一點）。
4. **對照**：第 0 階段 probe「`stopCapture` 之後才 `removeRecordingOutput`」三次都收到 didFinish；單一段落（18 秒場次、某場的第一段）產出的影片、wav、音影對齊都正確。結論：`SCRecordingOutput` 只適合「整條 stream 結束時收尾」，不能在執行中的 stream 上輪替。

## 決定（D20）

改採 **B：自管 `AVAssetWriter`**。使用者原話「自己管 AVAssetWriter（建議）」（`gate1-decisions.md` D20）。做法的唯一正本是 `design.md §7.2`（換段）、`§7.4`（停止與 finalize）、`§7.5`（格式變更）、`§7.6`（開錄）；驗收在 `spec.md §4.4`、`§4.6.13–4.6.16`、`§4.8.4`。要點：

- **一條 stream 不停**，正式錄製不再掛 `SCRecordingOutput`（`probe` 子指令保留它，第 0 階段量測可重跑）。
- **每段一個 writer、三個 input、固定順序**：video（H.264，`AVVideoAllowFrameReorderingKey = false`）、系統聲音（AAC 48 kHz 雙聲道）、麥克風（AAC 48 kHz 單聲道）。系統聲音與麥克風**分成兩條音軌**寫進同一個 `.mov`，**finalize 用 ffmpeg 混成一軌**（混成一軌的使用者決定不變，只是混音的時點從錄製中移到 finalize）。分軌而不在錄製中自己混的理由：自己混要做兩路的取樣率轉換、時間對齊與緩衝等待，錄製中出錯會毀掉兩路；分軌寫入時每路只管自己的 PTS，錯了也只壞一路，混音交給 ffmpeg（`amix`）且可重跑（`record finish` 冪等）。
- **邊界時間在 sample 時鐘上決定，不依賴任何回呼**：段 i 的起點 `B_i`（`startSession(atSourceTime:)`），段 i+1 的起點 `B_{i+1} = B_i + 60 秒`；第一個 PTS ≥ `B_{i+1}` 的 sample 一到就切換。所有 sample 依 PTS 分流（`routeSample`，`spec.md §3.4`）：結束 ≤ 邊界 → 舊 writer；開始 ≥ 邊界 → 新 writer；跨邊界的音訊緩衝兩邊都寫、由舊 writer 的 `endSession(atSourceTime: 邊界)` 與新 writer 的 session 起點各自裁掉不屬於自己的部分——兩段在呈現時間上**無空隙、不重疊**。
- **新段的第一個視訊 sample 就在邊界上**：新 writer 開始時，把「目前畫面」（最後一個 complete 幀的影像）以邊界時間重新打戳寫入。派工單原寫「在某個視訊 sample 的 PTS 邊界切換」；本 ADR 的做法是讓邊界本身就是一個視訊 sample 的 PTS，而不是等下一個真實幀——理由：畫面靜止時 SCK 不送新幀（`PROBE-REPORT.md:27`），等下一幀會讓換段延後到畫面變化為止（可能好幾分鐘，段長失控、D3 的當機損失上限失效），且要多一條「等不到幀」的備援路徑；重新打戳的那一幀就是邊界當下螢幕上的畫面，內容完全正確。附帶效果：每段都有 video stream（舊 §4.4.4「可能缺 video stream」不再發生）。
- **切換不等舊 writer**：新 writer 立刻 `startWriting`／`startSession`；舊 writer 在它的每個 input 都已看到 PTS ≥ 邊界的 sample（或邊界後 1 秒）之後 `endSession`＋`markAsFinished`＋`finishWriting`，完成回呼才記 `finishedAt`。
- **當機保護**：writer 設 `movieFragmentInterval = 10 秒`（`overallDurationHint = 60 秒`），寫到一半被 `kill -9` 的段落仍可讀到最後一個完整 fragment；正常收尾的段落是一般（非 fragment）的 `.mov`。
- **段落尺寸**：照 D8，換段時才套用新尺寸——段落邊界前約 1 秒先查視窗大小，尺寸不同就在換段時 `updateConfiguration`，新 writer 以新尺寸開檔、`AVVideoScalingModeKey = AVVideoScalingModeResizeAspect`（過渡期舊尺寸的幀等比縮進新畫布、不裁切）。
- **finalize 補兩件事**：(1) 兩條音軌混成一軌；(2) **逐段先把時間戳正規化再串接**（t6 另一個缺陷：實機段落 finalize 時 ffmpeg 報 `non monotonically increasing dts`，`spec.md §4.6.14`；根因是正規化與完整解碼檢查都沒指定編碼器時間基準，對 VFR、`time_base=1/600` 的 SCK 段落會擠壓或誤報時間戳，已在 repo 外以實機段落副本重現並驗證修法，見 `design.md §7.4` 第 3 步）。另外，preflight 到正式 `startCapture` 之間加等待與一次重試（t6 缺陷 4，`design.md §7.6`），與寫檔機制無關，一併在本輪修。

## 後果

- `manifest.json.segments[]` 的時間欄位改成新定義（`spec.md §3.2`）：`requestedAt`＝錄製器決定換段的時刻、`startedAt`＝該段 session 起點（sample 時鐘）、`finishedAt`＝`finishWriting` 成功完成的時刻（失敗或當機為 `null`）、`audioDuration`＝finalize 量到的各音軌最長 duration。欄位名稱與型別不變（`SegmentRecord` 不改）。
- 量測閘門 §4.4.3 的門檻不變（D3：`max(g_i) < 0.5 秒`、3 分鐘場次 `Σ g_i < 0.5 秒`），另加「段落確實收尾」的判準（`finishedAt` 非 `null`、收尾延遲 < 5 秒）。
- finalize 要能容忍：最後一段只有部分 fragment、段落有兩條或一條音軌（t6 期間 `SCRecordingOutput` 錄下的舊段落是一條混好的音軌）、時間戳不從 0 起或有 edit list、各段尺寸與音訊格式不同（`spec.md §4.6.9–4.6.16`）。
- 錄製器自己做 H.264 編碼（VideoToolbox），CPU／功耗與 `SCRecordingOutput` 相近（同一個硬體編碼器），但 sample 回呼佇列上多了 append 的工作；`isReadyForMoreMediaData == false` 時丟該 sample 並計數（不阻塞擷取佇列）。
- **未實測、t6 要驗**：(1) `AVAssetWriterInput` 對取樣率／聲道數不同的 LPCM 輸入能否照 AAC 48 kHz 輸出設定轉換（HFP 情境，`spec.md §4.9.3`）；不行時退回「每段輸出格式跟隨該段開頭的輸入格式」（finalize 已會統一格式）。(2) `AVVideoScalingModeKey` 對尺寸不同的 pixel buffer 是否照預期等比縮放（`spec.md §4.3.4`）；不行時退回「尺寸不符的幀丟棄並計數，直到新尺寸的幀到達」。(3) ffmpeg 能否讀被 `kill -9` 中斷的 fragment 段落（`spec.md §4.8.4`）。三項不過都以 `needs_decision` 回報，不在 build 或 test 段自行換做法。

## 後註（t6 接續與第二次中途修正輪，2026-10-12）
- 〈後果〉未實測 (3) 的結果：**不成立**。會議視窗靜止時 SCK 只送 `idle`，影片軌不前進，`AVAssetWriter` 要所有軌越過 fragment 邊界才寫 fragment，`kill -9` 後段落只有 `ftyp`／`wide`／`mdat`。使用者決定 D22「修正輪先試著修，修不好再放寬」：加影片心跳（`idle` 時距上一個視訊 PTS ≥ 1 秒就重送最後一幀），見 `design.md §7.2`〈當機〉、`spec.md §4.4.10`、`§4.8.4`。仍不成立時以 `needs_decision` 回報，選項之一是把當機保證放寬為「最多丟 1 段（60 秒）」；本 ADR 的選項 B 不變。
- 量測閘門：1650 場次 §4.4.3 PASS（max |g| 0.117 秒、每段都收尾、定期換段間隔都是 60.000 秒），選項 B 的「無縫換段」實機成立。

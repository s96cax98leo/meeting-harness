# ADR：錄製中增量轉錄的 worker 由誰起、怎麼知道段落收尾

- 狀態：提議（待 meeting-speed 閘門 2 核准）
- 日期：2026-10-21
- 範圍：`bin/lib/_asr_worker.py`（新）、`tools/MeetingRecorder/Sources/Capture/RecordingSession.swift`、`bin/meeting.sh`（prep 呼叫 `stitch`）、`bin/transcribe.sh`（讀現成段落）

## 背景

- intent §7 Q5：切點取段尾附近的 VAD 靜音點；丟幀數一增加就暫停到停止、錄製中不恢復；逐段結果不完整或參數不一致就退回整檔；品質門檻由 design 訂、閘門 2 核准。
- 使用者決定 2（`plan-approved.md:10`）：背景工作低優先權，一出現丟幀就暫停，停止後補做。
- 速度來源：模型只載一次、逐段轉錄（`plan-approved.md:89`）；mlx_whisper CLI 每次呼叫都重新載模型，所以 worker 必須在 Python 內呼叫 `mlx_whisper.transcribe()`。
- 段落收尾時 `segmentFinished` 已原子寫 `manifest.json`（`RecordingSession.swift:691-705`）。
- 錄製器啟動收尾子程序用 `record.defaults.json` 的 `python3`（`RecordingSession.swift:1220`）；`AutoPrepRunner` 走 `zsh -l` 會帶進 pyenv shim（intent §4.4）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. **錄製器在第一段收尾後起 worker；worker 輪詢 `manifest.json` 的 `finishedAt`** | 錄製器本來就知道場次與 python3 路徑；不用新的事件通道；CLI 開錄（`record.sh start` 也是啟動 app）與選單開錄走同一條 | `RecordingSession.swift` 要多一段起子程序；worker 要自己判斷「錄製已停止」（讀狀態檔 phase） |
| B. menu bar 看到 phase＝recording 時起 worker | 錄製器不動 | menu bar 不一定在跑（CLI 開錄時可能沒有）；直譯器來源要另找；menu bar 重啟會漏起或重起 |
| C. 錄製器每段收尾寫一個事件檔（例如 `tracks/events/seg-NNNN.closed`），worker 監看目錄 | 事件明確 | 多一個通道，與 `adr-control-channel.md` 的「只有狀態檔＋pid＋SIGTERM」相違；manifest 已經有同樣的資訊 |

## 決定

採 **A**。

- 起法：`/usr/bin/nice -n 10 <defaults.python3> <harness>/bin/lib/_asr_worker.py run <場次>`，`qualityOfService = .utility`，stdout／stderr 寫 `錄音/tracks/asr/worker.log`；`bin/lib/_asr_worker.py` 不存在或 `config.json` 的 `transcribe.incremental.enabled` 是 false 時不起（worker 自己也檢查）。第一段收尾後才起，避免模型載入與開錄搶資源。
- worker 持有 `錄音/tracks/asr/worker.lock`（flock），同一場只會有一個；`state.json` 每窗更新心跳。
- 窗不重疊、拼接不去重（鐵則 1：raw 只能換來源，不能清洗）。
- 交棒：prep 呼叫 `_asr_worker.py stitch`，回 0 就把結果經 `MH_ASR_SEGMENTS_JSON` 交給 `transcribe.sh`；回 3 就退回整檔轉錄。後段處理只有一份程式。
- 品質門檻（字差異率 ≤ 5%、時間差 ≤ 1.0 秒的比例 ≥ 95%，使用者 2026-10-21 核准，D5）只在重放量測時離線比對。

## 後果

- meeting-speed spec §3.6（`tracks/asr/` 檔案）、§3.9（worker CLI）、§4.11。
- 狀態檔加 Optional `droppedFrames`（沿用 `adr-r2-status-fields.md`），worker 用它判斷丟幀。
- 錄製中 worker 遇到另一場背景收尾還在跑就不開新窗（design §11 的資源分配）。
- 增量講者分離不做（intent §4.5）。

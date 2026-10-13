# ADR：影片軌比音訊軌短時，怎麼滿足「duration 差 < 100 ms」

- 狀態：選項由使用者選定（D7「整支重新編碼補尾」），做法待閘門 2 核准
- 日期：2026-10-11（修正輪：併入 D7、D8）
- 範圍：`bin/_record_finalize.py`

## 背景

- 驗收要求影片與音訊 duration 差 < 100 ms（`req:267`）。
- 影片在最後一次畫面變化處結束，影片軌會比音訊軌短（`tools/MeetingRecorder/PROBE-REPORT.md:27-29`）；intent §4 把「finalize 補幀」列為 design 要定的工作項。
- `SCRecordingOutput` 由系統寫檔，錄製中無法補幀；只能在 finalize 用 ffmpeg 處理。（後註，D20：寫檔已改為自管 `AVAssetWriter`，每段開頭會以段落起點補一幀、`endSession` 讓最後一幀延續到段尾，見 `adr-segment-writer.md`；本 ADR 的整支重編與補尾仍保留，處理舊段落與殘餘的影音長度差。）本機有 `h264_videotoolbox`（`ffmpeg -encoders`），ffmpeg 7.1.1 支援 `-fps_mode`。
- D8：每段以當下視窗大小開檔，段與段尺寸可能不同，finalize 要統一成同一尺寸；D6：HFP 可能讓段與段的音訊格式不同。兩者本來就迫使 finalize 至少重編一次，與補尾合併處理。

## 選項

| 選項 | 做法 | 好處 | 代價 |
|---|---|---|---|
| A. 整支重新編碼補尾 | 每段都重編：`pad` 到統一畫布（不縮放）、影片偏短時 `tpad` 補尾、音訊統一 48 kHz 雙聲道；再以 concat demuxer `-c copy` 串接（各段同編碼器、同參數、同尺寸） | 滿足字面驗收；同時解決 D8 的尺寸統一與 D6 的音訊格式差異；每段各自補尾，段內的音影偏差不會累積 | 一次轉碼損失；長場次 finalize 變慢；磁碟峰值升到約 4 倍（`design.md §5 Q7`） |
| B. 只 `-c copy`，驗收改成比檔案層 duration | mov 的 format duration 取最長的軌（音訊），兩檔天然相符 | 最快、零轉碼 | 等於改寫 `req:267`；而且 D8 的段落尺寸不同、D6 的音訊格式不同時 `-c copy` 串接不可行 |
| C. 只重編最後一段再 copy 串接 | 只對最後一段 tpad 重編，其餘段 copy | 轉碼量最小 | 混用「原段 copy」與「重編段」，SPS／PPS 不一致，串接後可能無法解碼；也解決不了 D8、D6 |

## 決定

採 **A**（使用者 D7 選定）。轉碼參數（`design.md §7.4`）：
- 影片：`h264_videotoolbox`、`-profile:v high`、`-b:v B -maxrate 2B -bufsize 4B`，`B`＝各段實測影片位元率最大值 × 1.5、下限 8 Mb/s；
- 不縮放：`pad=W:H:(ow-iw)/2:(oh-ih)/2:black`，`W×H`＝各段寬、高的最大值（D8：等比、不裁切，各段像素保留原解析度）；
- 不改 fps：`-fps_mode passthrough`，保留原始影格時間；
- 補尾：該段影片軌比音訊軌短 ≥ 0.1 秒時 `tpad=stop_mode=clone:stop_duration=<差>`；該段沒有 video stream 時以前一段最後一幀補；
- 音訊：`aresample=48000`、`-ac 2`、AAC 256 kb/s。

這是一次轉碼，與使用者先前「保留原樣全解析度」（`req:123`）相比有轉碼損失；使用者在知情下選擇，記在 `spec.md §6` 第 16 條。B、C 不採用。

## 後果

- finalize 的「場次出現」時間點在全部段落正規化並串接完成之後（`design.md §7.4` 第 7 步）；`record stop` 逐段印進度。
- `e2e_check.py` 以 `ffprobe -select_streams v:0／a:0 -show_entries stream=duration` 比兩軌，不比 format duration；另驗輸出寬高、位元率、fps 尖峰（`spec.md §4.3.3`、`§4.6.10`）。
- `_record_estimate.py` 的係數由 3 倍改為 4 倍。

## 後註（t6 第二次中途修正輪，2026-10-12）
- 補尾的做法不變（整支重編、最後一幀複製補尾），但「補到哪裡」改了：前一版以 `段落長 − 1/連結影格率` 為上限，靠編碼器把最後一幀記成 1/連結影格率長來補滿；實機的稀疏 VFR 段 `r_frame_rate` 很低（4/3），而且有 `setpts` 時編碼器並不照這個長度記（t6 缺陷 F，差 396 ms），沒有 `setpts` 時又會記成 1/平均影格率（缺陷 B，rc 5）。改為上限 `段落長 − 5 ms`、一律 `setpts`、串接時把最後一個封包設為 1 tick，詳見 `design.md §7.4` 第 3、4 步與 `spec.md §4.6.17`、`§4.6.18`。本 ADR 的選項取捨不受影響。

## 後註（t6 第三次中途修正輪，2026-10-12）
- 「逐段正規化、無損串接」只對**影片**成立；音訊改為逐段正規化成 PCM、串接時全片一次編 AAC。理由（t6 缺陷 J）：concat demuxer `-c copy` 丟掉每個 AAC 檔的 edit list，每個段落邊界多出 1024 樣本 priming 與前一段最後一個封包的補零，解碼後的音訊每段晚約 21–37 ms、逐段累積（2254 場次 8 段累積 235 ms）。音訊仍只有一次有損編碼。細節與驗證數字見 `design.md §7.4`〈缺陷 J〉、`spec.md §4.6.20`、§6 第 65 條。

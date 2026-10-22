# video-spike 證據：SCK 擷取設定、copy 串接、AAC 編碼耗時、WindowServer 負擔

- 子任務：`video-spike`（kind=check；plan §2、spec §4.4.13、ADR `adr/adr-ms-video-copy.md`〈後果〉）
- 日期：2026-10-21；分支 `feature/meeting-speed--video-spike`（自 `feature/meeting-speed` `05e58b6`）
- 機器：Apple M3 Max（16 核）、macOS 26.6（25G72）、Xcode SDK `MacOSX.sdk` 27.0、Swift 6.4
- 工具：`/opt/homebrew/bin/ffmpeg` 7.1.1（PATH 上那支；`bin/_record_finalize.py` 的 `find_tool` 在沒有 `MH_FFMPEG`／`record.defaults.json` 時找到的就是它）
- 範圍：只用合成素材；**沒有**啟動錄製器、`MeetingRecorder`、螢幕擷取或任何會觸發 TCC 的程式；沒有讀 `~/.meeting-harness/`、`vault/`、`.env`。暫存檔都在 `mktemp -d` 目錄，做完已刪。
- 範例場次名一律用「[Stand-up] 範例專案」；本文不含使用者家目錄路徑、真實場次名、視窗標題。

---

## 1. SDK 宣告

### 1.1 標頭位置與行號

`xcrun --show-sdk-path` 回 `/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk`（以下記為 `$SDK`）。宣告在 `$SDK/System/Library/Frameworks/ScreenCaptureKit.framework/Headers/SCStream.h`（共 571 行）：

| 屬性 | 行號 | 宣告（節錄） | 可用版本 | 標頭註解重點 |
|---|---|---|---|---|
| `width` | 230 | `@property(nonatomic, assign) size_t width` | macOS 12.3 | 輸出寬（像素），macOS 預設 1920 |
| `height` | 235 | `@property(nonatomic, assign) size_t height` | macOS 12.3 | 輸出高（像素），macOS 預設 1080 |
| `minimumFrameInterval` | 240 | `@property(nonatomic, assign) CMTime minimumFrameInterval` | macOS 12.3 | 預設 1/60（「at or up to 60fps」）；設 `kCMTimeZero` 取顯示器原生更新率 |
| `scalesToFit` | 259 | `@property(nonatomic, assign) BOOL scalesToFit` | macOS 12.3 | 單視窗擷取用；true＝放大縮小都會縮放到給定寬高，false＝只縮小 |
| `preservesAspectRatio` | 264 | `@property(nonatomic, assign) BOOL preservesAspectRatio` | **macOS 14.0** | 「By default the aspect ratio is preserved」（預設就是保留長寬比） |
| `queueDepth` | 299 | `@property(nonatomic, assign) NSInteger queueDepth` | macOS 12.3 | — |
| `captureResolution` | 345 | `@property(nonatomic, assign) SCCaptureResolutionType captureResolution` | macOS 14.0 | `Automatic`／`Best`／`Nominal`（enum 在 83–87 行） |

重跑：

```
SDK="$(xcrun --show-sdk-path)"
grep -n -E 'preservesAspectRatio|scalesToFit|size_t (width|height)|minimumFrameInterval|captureResolution|queueDepth' \
  "$SDK/System/Library/Frameworks/ScreenCaptureKit.framework/Headers/SCStream.h"
```

- `.swiftinterface`：`ScreenCaptureKit.framework/Versions/A/Modules/ScreenCaptureKit.swiftmodule/arm64e-apple-macos.swiftinterface` 存在，但 `grep -n preservesAspectRatio` 沒有結果——這幾個屬性是 Objective-C 標頭經 Clang importer 匯入 Swift，不在 swiftinterface 裡，以 `SCStream.h` 為準。

### 1.2 編譯期驗證（只 typecheck，不執行、不擷取）

把下面這段存成 `t.swift`，以錄製器的建置目標（`tools/MeetingRecorder/build.sh:28` 的 `arm64-apple-macosx15.0`）只做型別檢查：

```
import ScreenCaptureKit
let c = SCStreamConfiguration()
c.width = 2992; c.height = 1632
c.scalesToFit = true
c.preservesAspectRatio = true
c.minimumFrameInterval = CMTime(value: 1, timescale: 30)
print(c.preservesAspectRatio)
```

| 指令 | 結果 |
|---|---|
| `swiftc -typecheck -target arm64-apple-macosx15.0 t.swift` | 回 0（沒有診斷） |
| `swiftc -typecheck -target arm64-apple-macosx13.0 t.swift` | `error: 'preservesAspectRatio' is only available in macOS 14.0 or newer`（佐證可用版本） |

### 1.3 對 spec §4.4.2 的意義

- 錄製器目標是 macOS 15.0，`preservesAspectRatio = true` 可以直接寫，不需要 `if #available`。
- 標頭明說預設就是保留長寬比，所以 spec §4.4.2 明寫 `preservesAspectRatio = true` 是把預設值釘住（給靜態測試看、也防日後預設改變），行為上不會跟現行錄製器不同。
- 「視窗放大縮小後內容等比縮放、畫布維持 `canvasLock`」這件事，標頭只保證長寬比不變；縮放後**留黑邊的位置與顏色**標頭沒寫，要在 test 段實錄看（spec §4.4.11）。
- `width`／`height` 是擷取輸出的像素尺寸；「尺寸上限」（§4.4.13）就是在開錄時把 `canvasLock` 等比縮到上限內再寫進這兩個屬性（`scalesToFit = true` 讓視窗內容縮放到它）。

---

## 2. 合成段落的 copy 串接

### 2.1 合成段落（模擬錄製器的 `seg-*.mov`）

依 `tools/MeetingRecorder/Sources/Capture/SegmentWriter.swift:50-91` 與 `Core/Segments.swift:49-52` 的寫入參數做 5 段，每段約 60 秒：

| 項目 | 合成值 | 對應的錄製器設定 |
|---|---|---|
| 尺寸 | 2992×1632（全段相同；incident 當晚的畫布） | `canvasLock` 鎖定後每段同尺寸（spec §4.4.1） |
| 影片編碼 | `h264_videotoolbox`、High profile、`-bf 0`、每 2 秒強制關鍵幀、6.1 Mb/s（＝2992×1632×5/4） | `AVVideoProfileLevelH264HighAutoLevel`、`AllowFrameReordering=false`、`MaxKeyFrameIntervalDuration=2`、`segmentVideoBitRate` |
| 時間戳 | `time_base=1/600`、`-fps_mode passthrough`；60 fps 網格去掉約 22% 的影格（`n mod 7 == 3` 或 `n mod 13 == 5`）造出 VFR：平均約 47.5 fps、最小間隔 1.67 ms、最大間隔 50 ms | SCK 只在畫面變動時送幀、AVAssetWriter timescale 600 |
| 影片晚開始 | 每段影片比音訊晚 1/30 秒（mov edit list） | 段內影片晚於音訊開始（meeting-record §4.6.14 (vi) 的實機特性） |
| 畫面靜止 | 第 3 段最後 2.5 秒、第 5 段（最後一段）最後 8 秒沒有任何影格 | 畫面不動時 SCK 不送新幀；incident 當晚末段約 9 秒靜止（spec §4.4.12） |
| 音訊 | 2 條 AAC（`aac_at`）、48 kHz：系統聲音雙聲道 192 kb/s、麥克風單聲道 128 kb/s | `aacSettings(channels: 2, bitRate: 192_000)`／`(channels: 1, bitRate: 128_000)` |
| 段長 | 依 finalize `analyze()`（`bin/_record_finalize.py:612-649`）算：各軌最後封包結束的最大值 − 原點，約 60.06–60.09 秒，都不是 1024 樣本的整數倍 | — |

產生指令（每段一支；`L` 為段長、`CUT` 為該段最後有影格的時刻，沒有靜止尾段時省略 `*lt(t\,CUT)`）：

```
ffmpeg -y -f lavfi -i testsrc2=s=2992x1632:r=60:d=$L \
  -f lavfi -i sine=f=440:r=48000:d=$L -f lavfi -i anoisesrc=c=pink:a=0.02:r=48000:d=$L \
  -filter_complex "[0:v]setpts='(N*10+mod(N*7\,3))/600/TB',select='not(eq(mod(n\,7)\,3))*not(eq(mod(n\,13)\,5))*lt(t\,$CUT)'[v];[1:a]aformat=channel_layouts=stereo[s];[2:a]aformat=channel_layouts=mono[m]" \
  -map '[v]' -map '[s]' -map '[m]' -c:v h264_videotoolbox -profile:v high -b:v 6103680 -bf 0 -g 100000 \
  -force_key_frames 'expr:gte(t,n_forced*2)' -pix_fmt yuv420p -fps_mode passthrough -enc_time_base 1/600 \
  -video_track_timescale 600 -c:a aac_at -b:a:0 192k -b:a:1 128k -t $L raw.mov
# 影片晚 1/30 秒開始
ffmpeg -y -itsoffset 0.033333 -i raw.mov -i raw.mov -map 0:v:0 -map 1:a:0 -map 1:a:1 -c copy -video_track_timescale 600 seg-000k.mov
```

### 2.2 copy 路徑做法（照 design §4、ADR〈決定〉，含本次找到的必要調整：首幀拉到 0、補尾用 floor、concat 不設 1 tick 並加 `-auto_convert 0`）

1. **抽 PCM（音訊先出那一步，§3.2）**：每段以現行 `audio_graph`（`bin/_record_finalize.py:894-915`）的混音式子解成 48 kHz 雙聲道 `pcm_s16le`，補到段長：
   `ffmpeg -i seg -filter_complex "<audio_graph(L)>" -map '[a]' -c:a pcm_s16le -t L -f wav pcm-k.wav`
2. **逐段 remux（影片不重編）**：
   `ffmpeg -i seg -i pcm-k.wav -map 0:v:0 -map 1:a:0 -c:v copy -c:a copy -bsf:v "setts=duration=if(eq(NEXT_PTS\,NOPTS)\,max(1\,floor(L/TB)-PTS)\,DURATION):pts=if(eq(N\,0)\,0\,PTS):dts=if(eq(N\,0)\,0\,DTS)" -t L -f mov norm-k.mov`
   - `duration=…`：最後一個封包的長度補到段長（ADR〈決定〉寫的 `setts`）；用 `floor` 不用 `round`，理由見 2.4 觀察 3。
   - `pts=/dts=if(eq(N\,0)\,0\,…)`：**調整一**——影片晚於原點開始時把第一個封包拉到 0（等同現行 `normalize` 的「第一幀往前延到 0」，`bin/_record_finalize.py:1236,1258`）。不拉時 mov 會寫 edit list，見 2.4 的 `nopull` 結果。
3. **concat**：
   `ffmpeg -auto_convert 0 -f concat -safe 0 -i list.txt -c:v copy -c:a aac -b:a 256k out.mov`
   - **調整二**：不加現行重編路徑那個「最後封包長度設 1 tick」的 `-bsf:v setts=duration=if(eq(NEXT_PTS\,NOPTS)\,1\,DURATION)`（`bin/_record_finalize.py:1489`）。copy 路徑沒有 tpad 補尾，最後一段畫面靜止時，設 1 tick 會讓影片軌在最後一幀就結束，影片比音訊短整段靜止的長度（2.4 的 A 組：短 8 秒，§4.6.3 FAIL）。
   - `-auto_convert 0`：concat demuxer 預設會對 H.264 自動套 bitstream filter，在**每個關鍵幀**前面插入 SPS/PPS（實測每個關鍵幀多 23 bytes，153 個關鍵幀全中），封包資料就不再與來源逐段相同（§4.4.4 字面要求）。關掉後封包 MD5 全部相同。插入 SPS/PPS 不影響解碼，只影響 §4.4.4 的驗法。
   - 沒有 `+faststart`（spec §4.4.6）；`-c:v copy`、`-c:a aac -b:a 256k` 相鄰成對，`test_static_rules.py:505-522` 照樣成立（該測試只檢查 `-f concat` 那支呼叫的這兩組參數，不看 `setts`／`-auto_convert`）。
4. **wav**：各段 PCM 以 concat demuxer 串起來轉 16 kHz 單聲道（§3.2 正式 wav 的來源，§6 第 11 條）。

### 2.3 判準（spec §4.4.5 引用的 meeting-record 條文）

| 代號 | 判準 | 量法 |
|---|---|---|
| §4.6.3 | 影片軌與音訊軌 stream 層 duration 差 < 100 ms | `ffprobe -show_streams` 的 `duration` |
| §4.6.14 (i) | 每條軌封包 dts 嚴格遞增 | `ffprobe -show_entries packet=dts_time` |
| §4.6.14 (ii) | `ffmpeg -v error -i out -enc_time_base demux -f null -` 沒有任何錯誤輸出 | 同左 |
| §4.6.14 (iii) | 輸出影格數 ≥ 各段影格數總和 − 完全相同 PTS 的重複數 | `ffprobe -count_frames`（輸出）對 各段封包數 |
| §4.6.14 (iv) | 相鄰影格間隔 < 1 ms 的對數為 0 | 輸出影片封包 pts 排序後相鄰差 |
| §4.6.20 (i) | 音訊軌實際解碼樣本數 ÷ 48000 與 stream duration 差 ≤ 25 ms | 解成 s16le 數位元組 |
| §4.6.20 (ii) | `錄音/*.wav` 長度與影片音訊軌 duration 差 ≤ 25 ms | wav `format=duration` |
| §4.4.4 | 影片封包資料與來源逐段相同 | `ffmpeg -i X -map 0:v:0 -c copy -f framemd5 -` 的 MD5 序列逐一比對 |
| 段界 | 第 k 段第一幀在輸出中的時刻 − （前面各段長總和＋該段首幀相對原點） | 輸出封包 pts |

§4.4.3 的 copy 條件另外逐項看：尺寸、codec、profile、pix_fmt、time_base 全場各一種；`ffprobe -show_streams -show_data_hash sha256` 的 `extradata_hash` 全場一種；重複 PTS 數 0。

### 2.4 結果

組別：A＝現行 concat 呼叫原樣（含最後封包 1 tick、`auto_convert` 預設開）；B＝拿掉 1 tick；C＝B＋`-auto_convert 0`（**建議做法**）；C-at＝C 但音訊改 `aac_at`（第 3 節用）。變體：`pull`＝remux 時首幀拉到 0（建議）；`nopull`＝不拉；`frag`＝段落是 fragmented mov（每 10 秒一個 fragment，同 `SegmentWriter.swift:51` 的 `movieFragmentInterval`；ffmpeg 寫 fragmented mov 時不保留影片晚開始，所以這組影片從 0 開始）；`x264`＝段落改用 libx264 編；`heartbeat`＝靜止尾段改成錄製器 idle 心跳（每 1 秒重送一幀，`Core/Segments.swift:54-57`）；`long`＝120 段、約 2 小時（160×90，時間戳行為與尺寸無關），用來看逐段累積。

**5 段、2992×1632（`pull`，C 組）——§4.4.5 全部 PASS：**

| 判準 | 數字 | 結果 |
|---|---|---|
| §4.4.3 copy 條件 | 尺寸 1 種、h264／High／yuv420p／`1/600` 各 1 種、`extradata_hash` 1 種、重複 PTS 0 | 成立 |
| §4.6.3 | 影片 300.380 s／音訊 300.379 s，差 1.0 ms | PASS |
| §4.6.14 (i) | 影片 13748 個、音訊 14082 個封包，非遞增 0 | PASS |
| §4.6.14 (ii) | rc=0、stderr 0 字元（解碼檢查 4.6 s） | PASS |
| §4.6.14 (iii) | 輸出 13748 ≥ 各段 13748 − 重複 0 | PASS |
| §4.6.14 (iv) | < 1 ms 的相鄰間隔 0 對（最小 1.67 ms） | PASS |
| §4.6.20 (i) | 解碼 300.3947 s 對 duration 300.3790 s，差 15.7 ms | PASS（≤ 25） |
| §4.6.20 (ii) | wav 300.3787 s 對 300.3790 s，差 0.3 ms | PASS |
| §4.4.4 | 13748 個影片封包 MD5 與來源逐一相同 | PASS |
| 段界 | 第 2–5 段首幀誤差 0.0／0.0／+0.67／+0.67 ms（round 版；floor 版見下） | — |

**各組別與變體一覽（§4.4.5 七項；列出不是全 PASS 的項目與關鍵數字）：**

| 變體 | A（現行原樣） | B | C（建議） | C-at |
|---|---|---|---|---|
| pull | **§4.6.3 FAIL**（影片短 8023.9 ms）；§4.4.4 不同 | 全 PASS（差 1.0 ms）；§4.4.4 不同 | **全 PASS**；§4.4.4 相同 | 全 PASS（§4.6.3 差 16.0 ms、§4.6.20 (ii) 17.3 ms） |
| nopull | **§4.6.3 FAIL**（8057.6 ms） | 全 PASS，但 §4.6.3 差 65.7 ms | 全 PASS，§4.6.3 差 65.7 ms | 全 PASS，§4.6.3 差 82.7 ms |
| frag（＋pull） | **§4.6.3 FAIL**（8034.0 ms） | 全 PASS（0.7 ms） | 全 PASS（0.7 ms）、§4.4.4 相同 | 全 PASS（5.7 ms） |
| x264（＋pull） | **§4.6.3 FAIL**（8023.6 ms） | 全 PASS（0.3 ms） | 全 PASS（0.3 ms）、§4.4.4 相同 | 全 PASS（19.3 ms） |
| heartbeat（＋pull） | PASS（59.3 ms：最後一幀距結尾 < 1 秒） | 全 PASS（1.0 ms） | 全 PASS（1.0 ms）、§4.4.4 相同 | 全 PASS（23.0 ms） |
| long 120 段（＋pull、floor） | **§4.6.3 FAIL**（8024.3 ms） | 全 PASS（1.0 ms） | 全 PASS（1.0 ms）、§4.4.4 相同（341353 個封包） | 全 PASS（5.0 ms） |

觀察：

1. **A 組在最後一段畫面靜止時一律 FAIL §4.6.3**（影片比音訊短整段靜止長度）。現行 concat 的 1 tick 是給重編路徑用的（重編時 tpad 已補幀到 cap），copy 路徑沒有補幀，所以 copy 路徑的 concat 必須拿掉它。只有錄製器心跳讓最後一幀落在結尾 1 秒內時 A 才剛好過（59.3 ms，餘裕很小；心跳在停止錄製後不會再送）。
2. **nopull 時 §4.6.3 只剩 34 ms 餘裕**（65.7 ms；`aac_at` 時 82.7 ms）：影片晚開始的 1/30 秒被 mov 寫成 edit list，ffmpeg 的 mov muxer 又把最後一個 sample 的長度扣掉同樣的 33 ms，兩者疊加。拉首幀後兩個都消失（1.0 ms）。實機影片若晚開始更多（例如 ≥ 50 ms），不拉就會 FAIL。
3. **補尾要用 floor 而不是 round**：`setts` 的運算在影片 time_base（1/600）上，`round(L/TB)` 會讓影片結束點捨入到最近的 1/600 秒，可能比音訊長；concat demuxer 依每個檔「最長那條軌」的長度接下一段，音訊（AAC 一次編、時間戳連續）不跟著移，影片就逐段偏移。120 段實測：**round 版累積到 +3.7 ms**，**floor 版最大 0.1 ms**（floor 讓影片結束點 ≤ 段長，每段長度由 PCM 音訊決定，1/48000 精確）。5 段版看不出來（0.67 ms），2 小時才明顯；以 §4.6.20 (iii) 的 10 ms 判準看，round 版在更長或段長分布更不利時有超標風險。附錄 A 的腳本預設 floor（`SPIKE_ROUND=1` 為對照）。
4. **`-auto_convert 0`**：沒有它時，每個關鍵幀被插入 SPS/PPS（+23 bytes），§4.4.4 的「封包逐段相同」不成立（解碼不受影響）。
5. **fragmented 段落、libx264 段落、錄製器心跳**都不改變結論；extradata 在同尺寸同參數下每段相同（videotoolbox 與 libx264 都是）。
6. `cond.avg_frame_rate` 各段不同、`r_frame_rate` 都是 60/1：§4.4.3 沒把影格率列入條件，實測也不需要。

**耗時（2992×1632、5 段 300 秒；M3 Max；同時有其他測試在跑，數字偏保守）：**

| 步驟 | 5 段實測 | 按段數外推到 2 小時（120 段） |
|---|---|---|
| 抽 PCM（音訊先出那步，copy 路徑不另計） | 0.15 s／段 | 18 s（序列）；平行度 4 約 5 s |
| 逐段 remux（`-c:v copy`） | 0.12–0.17 s／段（約 48 MB／段） | 14–20 s（序列）；平行 5 段實測 0.27–0.33 s／5 段 → 約 7 s |
| wav（各段 PCM 串接轉 16 kHz） | 0.30 s | 約 7 s |
| concat（`aac`） | 3.2–3.4 s | **120 段實測 76.7–88.5 s**（160×90；全尺寸 5 段 ×24 ≈ 77–82 s，兩種算法一致，影片 copy 的 I/O 不是主要成本） |
| concat（`aac_at`） | 1.8–1.9 s | **120 段實測 40.8–42.0 s** |
| 發佈後驗證（解碼檢查，不在關鍵路徑） | 4.4–7.8 s | 約 110–190 s（×24 外推） |

對照 design §2 的現行影片線（normalize 16.5 分＋concat 149.1 秒＋驗證 48.7 秒），copy 路徑在成品發佈前約 **1.5–2 分鐘**（remux 約 10–20 s＋concat 約 80 s），在影片 5 分內。

---

## 3. `aac` 與 `aac_at` 的串接音訊編碼耗時

### 3.1 2 小時 PCM 直接量（不外推）

素材：7200 秒、48 kHz 雙聲道 `pcm_s16le` wav（1,382,400,078 bytes），內容是 440 Hz 正弦＋粉紅雜訊混音（合成、不含真實錄音）。指令見附錄 A.3：

```
ffmpeg -nostdin -y -i pcm2h.wav -f null -                      # 讀檔基線
ffmpeg -nostdin -y -i pcm2h.wav -c:a aac    -b:a 256k aac.m4a
ffmpeg -nostdin -y -i pcm2h.wav -c:a aac_at -b:a 256k aac_at.m4a
```

| 編碼器 | 第 1 次 | 第 2 次 | 輸出位元率（ffprobe） |
|---|---|---|---|
| 讀檔基線（`-f null`） | 0.33 s | 0.33 s | — |
| `aac`（ffmpeg 內建，現行） | 70.63 s | 70.31 s | 240 kb/s |
| `aac_at`（AudioToolbox） | 40.81 s | 41.52 s | 256 kb/s |

`aac_at` 約快 **29.3 秒（−42%）**。第 2 節的 120 段 concat 實測同一個差距（`aac` 76.7–88.5 s 對 `aac_at` 40.8–42.0 s），可見 2 小時 concat 的時間幾乎都是 AAC 編碼。

### 3.2 `aac_at` 的副作用（合成段落實測）

- 編碼器延遲較長：§4.6.3 的差從 1.0 ms 變 16.0 ms（pull、5 段）、§4.6.20 (ii) 從 0.3 ms 變 17.3 ms（heartbeat 組 21.3 ms），§4.6.20 (i) 約 19–20 ms。都在判準內，但 §4.6.20 的 25 ms 只剩 4–8 ms 餘裕。
- 改用 `aac_at` 要改 `test_static_rules.py:505-522` 的 `"-c:a", "aac"` 斷言（design §10、spec §7 疑慮 3：另開核准）。

### 3.3 判斷

copy 路徑上 2 小時影片收尾約 1.5–2 分鐘，用 `aac` 已在 5 分內，**本輪不值得為了約 30 秒去改既有測試**；照 design §10 保留：若第 2 層量測顯示影片線超過 5 分，再拿本節數字另開核准。

---

## 4. WindowServer 負擔：三種擷取設定（D3 d、spec §4.4.13）

**待使用者在場實測。** 本子任務依派工限制沒有啟動錄製器、`MeetingRecorder`、螢幕擷取或任何會觸發 TCC 的程式，所以本節沒有實測數字，只寫主 session 照著跑的步驟。每一次啟動錄製器（含暫時建置的版本）都要先問使用者、當下同意才做（plan §4）。

### 4.1 三種設定與怎麼做出來

| 代號 | 設定 | 怎麼做出來 |
|---|---|---|
| S0 | 基線：不錄製 | 會議視窗照常顯示、畫面有動靜（例如會議中有人分享畫面或播放影片），不開錄製器 |
| S1 | 60 fps、原生像素（現行） | 已安裝的錄製器照常 `meeting record --window <id>`（`RecordingSession.swift:174-177`：畫布＝視窗像素、`minimumFrameInterval = 1/60`） |
| S2 | 30 fps、原生像素 | 暫時建置：只把 `RecordingSession.swift:177` 的 `CMTime(value: 1, timescale: 60)` 改成 `timescale: 30` |
| S3 | 60 fps＋尺寸上限 | 暫時建置：開錄時（`:124` 算出 `curSize` 之後）與換段時（`:525` `nextSegmentSize` 之後）把尺寸等比縮到長邊 ≤ 1920 px、取偶數（例：2992×1632 → 1920×1048）；`cfg.width/height` 與段落寫入器都用縮過的尺寸 |

- S2、S3 的暫時建置**不提交**：在 repo 外的暫存 worktree 或暫存複本改，`MH_RECORDER_DEST="$(mktemp -d)" bash tools/MeetingRecorder/build.sh` 建到暫存目錄，錄製時以 `MH_RECORDER_APP=<暫存目錄>/MeetingRecorder.app` 指給 `meeting.sh`（`bin/record.sh:28`），不覆蓋 `~/Applications` 裡的正式版。
- 暫時建置是 ad-hoc 簽章、身分與正式版不同，第一次擷取時 macOS 會再要一次「螢幕錄製」權限（TCC），使用者要在場按允許；量完可在「系統設定 → 隱私權與安全性 → 螢幕與系統錄音」移除該項。
- 只想先比 60／30 fps、不在乎段落時，可用已安裝 app 的 `probe` 子指令（`tools/MeetingRecorder/probe.sh`、`Probe.swift:72-110`，`--fps N --seconds N`）。但它的畫布是整個顯示器的像素、走 `SCRecordingOutput` 而不是錄製器的 60 秒段落，數字只能當參考，不能代替 S2；也做不出 S3。

### 4.2 量測條件（四種都一樣）

- 同一台機器、同一個會議視窗、同一個顯示器與縮放設定、視窗大小不動（記下 `record.meta.json.canvasLock` 或 log 的「畫布 W×H px」）；電源接上、關掉其他會吃 GPU 的程式。
- 畫面要有動靜（靜態畫面時 SCK 合法地不送新幀，負擔會被低估）；建議同一段會議錄影在會議視窗裡播放，四種設定都播同一段。
- 每種設定：開錄後等 log 出現「● 開始錄製」再等 10 秒才開始取樣；取樣 120 秒；之後**繼續錄到至少跨過 3 次 60 秒輪替**（總長 ≥ 4 分鐘）再停止，讓第 2 節的 copy 驗證有 ≥ 4 段可用；其中一段的最後幾秒讓畫面靜止（暫停播放）。
- 順序建議 S0 → S1 → S2 → S3 → S0（頭尾兩次基線，看溫度漂移）；每種之間等 60 秒讓 WindowServer 回穩。

### 4.3 取樣指令

主 session 在另一個終端機跑（只讀 `ps`／`top`，不需要權限、不會觸發 TCC）。`LABEL` 換成 S0／S1／S2／S3，輸出放暫存目錄、不要寫進 repo：

```
OUT="$(mktemp -d)"; LABEL=S1
WS="$(pgrep -x WindowServer)"
# (a) plan 指定的量法：ps 每秒取樣 120 次
for i in $(seq 120); do ps -o %cpu= -p "$WS"; sleep 1; done > "$OUT/$LABEL.ps.txt"
# (b) 對照：top 的逐秒區間值（第一筆是開機以來的平均，丟掉）
top -l 121 -s 1 -pid "$WS" -stats cpu | awk '/^[0-9.]+$/' | tail -n +2 > "$OUT/$LABEL.top.txt"
```

（a）與（b）擇一或同時跑都可以；同時跑時各自開一個終端機。macOS 的 `ps %cpu` 是核心算的衰減平均，比 `top` 的逐秒區間值平滑，p95 會偏低；兩者都記下，判斷以同一種量法的設定間差異為準。

算平均與 p95（nearest-rank）：

```
/Library/Frameworks/Python.framework/Versions/3.12/bin/python3 - "$OUT/$LABEL.ps.txt" <<'PY'
import math, statistics, sys
xs = sorted(float(l) for l in open(sys.argv[1]) if l.strip())
p95 = xs[max(0, math.ceil(0.95 * len(xs)) - 1)]
print(f"n={len(xs)} mean={statistics.fmean(xs):.1f} p95={p95:.1f} max={xs[-1]:.1f}")
PY
```

同一段時間也記下錄製器 log 的丟幀（新錄製器才有 `record.status.json.droppedFrames`，現行版看 log）與「視窗尺寸改變」行數。

### 4.4 記錄格式（寫進 run 目錄，只寫代號與數字）

| 設定 | 畫布 px | fps 上限 | ps 平均 % | ps p95 % | top 平均 % | top p95 % | 丟幀 | 段數 | copy 驗證（第 2 節 C 做法） |
|---|---|---|---|---|---|---|---|---|---|
| S0 | — | — | | | | | — | — | — |
| S1 | | 60 | | | | | | | |
| S2 | | 30 | | | | | | | |
| S3 | | 60 | | | | | | | |
| S0（尾） | — | — | | | | | — | — | — |

### 4.5 每種設定錄出的段落怎麼驗 copy 串接

錄完照常 `meeting record stop`（現行 finalize 照舊重編，不影響本驗證）。finalize 不刪 `錄音/tracks/seg-*.mov` 時，把附錄 A 的 `spike.py`、`summ.py` 存到暫存目錄，對**段落目錄唯讀**跑第 2 節的建議做法（逐段 remux：首幀拉到 0＋最後封包補到段長；concat：`-auto_convert 0`、不設最後封包 1 tick），所有中間檔寫進暫存目錄：

```
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
W="$(mktemp -d)"
"$PY" -I spike.py "$W/work" real "<場次>/錄音/tracks" --pull > "$W/S1-copy.json"
"$PY" -I summ.py "$W/S1-copy.json"     # 印 §4.4.3 條件與 §4.4.5 各項 PASS／FAIL
rm -rf "$W/work"
```

- 判讀：看 `cond`（尺寸只有一種、codec／profile／pix_fmt／time_base 各一種、`extradata_hash_distinct == 1`、`dups == 0`＝§4.4.3 的 copy 條件），再看 `C-no-1tick-noconv` 那一組七項是否全 PASS、`packetsIdentical == true`。
- 現行錄製器（S1）沒有 `canvasLock`，視窗沒縮放時各段尺寸本來就相同，可以拿來驗；錄製中縮放過視窗的場次段落尺寸不同，`cond.size` 會有兩種以上——那是預期的「不走 copy」，不算失敗。
- 腳本的段落長取各段音軌 duration 的最大值；finalize 實際用的段長可能略有不同（例：被中止的段），差異在 ±1 個 AAC 封包內時判讀不受影響。
- JSON 只含數字與 PASS／FAIL，不含路徑；寫進 run 目錄前仍照例掃一次名稱。

---

## 5. 結論與建議（建議不是決定）

### 5.1 copy 路徑：**可行**（以合成段落為據；實錄待驗）

- 依據：第 2 節的建議做法在 6 種變體（含 2 小時 120 段、fragmented、libx264、錄製器心跳）上，spec §4.4.5 引用的七項判準與 §4.4.4 封包逐段相同全部 PASS；§4.4.3 的 copy 條件在同尺寸段落上全部成立；2 小時影片收尾外推約 1.5–2 分鐘。
- **但「沿用現行 concat 呼叫」（design §4、ADR〈決定〉）原樣不可行**：最後一段畫面靜止時 §4.6.3 FAIL（短 8 秒）。`finalize-fast` 實作 copy 路徑時要照第 2.2 節做，三處與 design 字面不同，都不碰既有測試：
  1. copy 路徑的 concat **不加**最後封包 1 tick 的 `setts`（重編路徑照舊保留）。
  2. concat 加 `-auto_convert 0`（否則 §4.4.4 封包不相同）。
  3. 逐段 remux 的補尾用 `floor(L/TB)`，並在影片晚於原點時把首幀拉到 0（否則 2 小時累積數 ms 偏移、§4.6.3 餘裕剩 34 ms）。
  這三點是實作細節、沒有改 spec 條文（§4.4.6 只要求 `-c:v copy`／`-c:a aac -b:a 256k`／不含 `+faststart`）；主 session 可決定是否補進 design §4 讓 `finalize-fast` 照做。
- 實錄待驗（第 4.5 節、spec §4.4.11）：AVAssetWriter 每段的 extradata 是否真的相同、實機影片晚開始的幅度、段落在錄製中縮放視窗後的尺寸（新錄製器有 `canvasLock` 才會相同）、閃白／嗶聲的段內同步（§4.6.14 (vi)、§4.6.20 (iii)，本次合成素材沒有驗）。影片早於音訊開始的段落本次也沒有合成。

### 5.2 `aac_at`：**目前不值得**

快約 30 秒（2 小時 70.5 s → 41.2 s），但 copy 路徑已在 5 分內，且要改既有靜態測試、§4.6.20 餘裕變小。維持 design §10；第 2 層量測若影片線超過 5 分再另開核准。

### 5.3 §4.4.13（擷取幀率／尺寸上限）：待使用者決定

- 現況：第 4 節三種設定的 WindowServer 負擔**還沒有數字**（agent 不得啟動錄製器）。以下是「先量再決定」的選項，不是預先定案。
- 與 copy 的關係：copy 可不可行不受幀率影響（合成段落是 60 fps 網格的 VFR，30 fps 只是更稀疏）；尺寸上限也只改 `canvasLock` 的數值，copy 條件照樣成立。所以本節的決定只看 WindowServer 負擔與畫質取捨。

| 選項 | 做法 | 代價 | 適用 |
|---|---|---|---|
| A. 維持 60 fps、原生像素（現行、intent §7 Q3） | 不改 spec §4.4.2 | 不解決 2026-10-21 晚間 WindowServer 高負載的風險；段落最大（2992×1632 約 48 MB／分） | 第 4 節量出 S1 與 S0 差距小（例如平均增加 < 10 個百分點、p95 不尖） |
| B. 改 30 fps、原生像素 | `minimumFrameInterval = 1/30`；修 §4.4.2、§6.1 記為 intent §7 Q3 修訂、`red-py` 補測試 | 捲動、游標、影片內容的流暢度減半；螢幕分享的小字清晰度不變 | S2 比 S1 明顯降低 WindowServer 負擔 |
| C. 60 fps＋尺寸上限（例：長邊 ≤ 1920 px） | 開錄時把 `canvasLock` 等比縮到上限 | 高 DPI 畫面縮小約 36%，螢幕分享的小字（程式碼、表格）可能看不清；縮放在 WindowServer 端做，負擔不一定下降 | S3 明顯低於 S1、且 S2 不夠 |

- **建議**：先由主 session 在使用者在場時跑第 4 節（約 30 分鐘：五輪各 120 秒取樣＋每輪錄滿 4 段）。量完之前不改，維持 A（spec §4.4.2 的現行規定）。量完後的建議判讀：S2 比 S1 平均降低 ≥ 25% 時選 **B**（會議紀錄用途不需要 60 fps，又保留文字清晰度）；S2 不夠、S3 才夠時選 C；兩者都沒有明顯差異時維持 A，WindowServer 的問題另查（例如其他擷取程式）。
- 使用者決定非 A 時，照 plan §4：主 session 先修 spec §4.4.2、§6.1 與 `CaptureStatic` 的斷言（`red-py` 補一個 commit），再派 `recorder-capture`。

### 5.4 開工前提（plan §2）

- `finalize-fast`：copy「可行」→ 可開工（附第 5.1 節三點）。
- `recorder-capture`：還要等使用者對 §4.4.13 的決定。

衍生工作（不編號）：(1) 實錄段落跑第 4.5 節的 copy 驗證，並補合成「影片早於音訊開始」與閃白／嗶聲同步的 copy 案例；(2) 若採第 5.1 節三點，補 design §4 的文字。

---

## 附錄 A：重跑用腳本

存到同一個暫存目錄（不要放進 repo）。`spike.py <工作目錄> <main|frag|x264|heartbeat> [--pull]` 產生合成段落並跑完 2.4 的全部組合；`spike.py <工作目錄> real <段落目錄> --pull` 只讀實錄段落跑同一套驗證；`summ.py <結果.json>` 印出逐項 PASS／FAIL。影片尺寸可用環境變數 `SPIKE_W`／`SPIKE_H` 改小做快速試驗（時間戳行為與尺寸無關）。

### A.1 `spike.py`

```python
"""video-spike：合成 SCK 特性段落 → copy remux → concat，逐項驗 spec §4.4.5。
用法：python3 spike.py <workdir> <variant> [--pull]
variant: main | frag | x264 | heartbeat | real <段落目錄>
"""
import concurrent.futures as cf
import glob
import json
import os
import subprocess
import sys
import time

FF, FP = "ffmpeg", "ffprobe"
W, H = int(os.environ.get("SPIKE_W", 2992)), int(os.environ.get("SPIKE_H", 1632))
LENS = [60.012, 59.987, 60.021, 60.004, 60.017]
if os.environ.get("SPIKE_N"):
    # 長場次：N 段、段長 59.95–60.05 秒之間的偽亂數（可重現）
    LENS = [round(59.95 + ((k * 37 + 11) % 101) / 1000, 3) for k in range(int(os.environ["SPIKE_N"]))]
CUT = {2: 2.5, len(LENS) - 1: 8.0}
VIDEO_LATE_TICKS = 20
BITRATE = W * H * 5 // 4


def run(cmd, check=True):
    t = time.monotonic()
    r = subprocess.run(cmd, capture_output=True, text=True)
    dt = time.monotonic() - t
    if check and r.returncode != 0:
        raise SystemExit("FAILED " + " ".join(cmd) + "\n" + r.stderr[-2000:])
    return r, dt


def ffp(*a):
    r, _ = run([FP, "-v", "error", *a])
    return r.stdout


def gen_segment(work, k, variant):
    L = LENS[k]
    out = os.path.join(work, "seg-%04d.mov" % (k + 1))
    cut = L - CUT[k] if k in CUT else 1e9
    sel = "not(eq(mod(n\\,7)\\,3))*not(eq(mod(n\\,13)\\,5))*lt(t\\,%.3f)" % cut
    if variant == "heartbeat" and k in CUT:
        sel = ("not(eq(mod(n\\,7)\\,3))*not(eq(mod(n\\,13)\\,5))*"
               "if(lt(t\\,%.3f)\\,1\\,eq(mod(n\\,60)\\,0))" % cut)
    vf = ("[0:v]setpts='(N*10+mod(N*7\\,3)+%d)/600/TB',select='%s'[v];"
          "[1:a]aformat=channel_layouts=stereo[s];[2:a]aformat=channel_layouts=mono[m]" % (0, sel))
    if variant == "x264":
        venc = ["-c:v", "libx264", "-profile:v", "high", "-preset", "veryfast"]
    else:
        venc = ["-c:v", "h264_videotoolbox", "-profile:v", "high"]
    frag = ["-frag_duration", "10000000"] if variant == "frag" else []
    cmd = [FF, "-hide_banner", "-v", "error", "-y",
           "-f", "lavfi", "-i", "testsrc2=s=%dx%d:r=60:d=%s" % (W, H, L),
           "-f", "lavfi", "-i", "sine=f=440:r=48000:d=%s" % L,
           "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.02:r=48000:d=%s" % L,
           "-filter_complex", vf, "-map", "[v]", "-map", "[s]", "-map", "[m]",
           *venc, "-b:v", str(BITRATE), "-bf", "0", "-g", "100000",
           "-force_key_frames", "expr:gte(t,n_forced*2)", "-pix_fmt", "yuv420p",
           "-fps_mode", "passthrough", "-enc_time_base", "1/600", "-video_track_timescale", "600",
           "-c:a", "aac_at", "-b:a:0", "192k", "-b:a:1", "128k", *frag, "-t", str(L), out + ".raw.mov"]
    _, dt = run(cmd)
    if variant == "frag":
        os.replace(out + ".raw.mov", out)
        return out, dt
    # 影片比音訊晚 VIDEO_LATE_TICKS/600 秒開始（mov 寫成 edit list），模擬 AVAssetWriter 先收到音訊
    run([FF, "-hide_banner", "-v", "error", "-y", "-itsoffset", "%.6f" % (VIDEO_LATE_TICKS / 600),
         "-i", out + ".raw.mov", "-i", out + ".raw.mov", "-map", "0:v:0", "-map", "1:a:0", "-map", "1:a:1",
         "-c", "copy", "-video_track_timescale", "600", out])
    os.remove(out + ".raw.mov")
    return out, dt


def streams(path):
    return json.loads(ffp("-show_streams", "-show_format", "-show_data_hash", "sha256", "-of", "json", path))


def vstream(info):
    return [s for s in info["streams"] if s["codec_type"] == "video"][0]


def astreams(info):
    return [s for s in info["streams"] if s["codec_type"] == "audio"]


def pkts(path, sel):
    out = ffp("-select_streams", sel, "-show_entries", "packet=pts_time,dts_time,duration_time,flags",
              "-of", "csv=p=0", path)
    rows = []
    for line in out.splitlines():
        p = line.split(",")
        rows.append((float(p[0]), float(p[1]), float(p[2]) if p[2] not in ("", "N/A") else 0.0, p[3]))
    return rows


def pkt_hashes(path):
    r, _ = run([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "framemd5", "-"])
    return [l.rsplit(",", 1)[-1].strip() for l in r.stdout.splitlines() if l and not l.startswith("#")]


def audio_graph(L):
    return ("[0:a:0]aresample=48000,aformat=channel_layouts=stereo,aresample=48000:async=1:first_pts=0[a0];"
            "[0:a:1]aresample=48000,pan=stereo|c0=c0|c1=c0,aresample=48000:async=1:first_pts=0[a1];"
            "[a0][a1]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.891:level=0:latency=1,"
            "apad=whole_dur=%.6f[a]" % L)


def seg_len(info, path):
    # 同 bin/_record_finalize.py analyze()：段長＝各軌最後封包結束（pts＋duration）的最大值 − 原點（各軌起點最小值）
    ends, starts = [], []
    for k, s in enumerate(info["streams"]):
        rows = pkts(path, str(k))
        if rows:
            starts.append(min(r[0] for r in rows))
            ends.append(max(r[0] + r[2] for r in rows))
    return max(ends) - min(starts)


def remux(work, k, seg, L, pull_first):
    pcm = os.path.join(work, "pcm-%04d.wav" % (k + 1))
    _, t_pcm = run([FF, "-hide_banner", "-v", "error", "-y", "-i", seg, "-filter_complex", audio_graph(L),
                    "-map", "[a]", "-c:a", "pcm_s16le", "-t", "%.6f" % L, "-f", "wav", pcm])
    norm = os.path.join(work, "norm-%04d.mov" % (k + 1))
    # 最後封包補到段長：floor（預設）讓影片結束點 ≤ 段長，concat 依音訊（PCM，1/48000 精確）的長度接下一段，
    # 不會因捨入到 1/600 而逐段累積影音偏移；SPIKE_ROUND=1 改用 round（對照組）
    rnd = "round" if os.environ.get("SPIKE_ROUND") == "1" else "floor"
    bsf = "setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,max(1\\,%s(%.6f/TB)-PTS)\\,DURATION)" % (rnd, L)
    if pull_first:
        bsf += ":pts=if(eq(N\\,0)\\,0\\,PTS):dts=if(eq(N\\,0)\\,0\\,DTS)"
    _, t_mux = run([FF, "-hide_banner", "-v", "error", "-y", "-i", seg, "-i", pcm,
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "copy",
                    "-bsf:v", bsf, "-t", "%.6f" % L, "-f", "mov", norm])
    return pcm, norm, t_pcm, t_mux


def concat(work, norms, name, last_tick, aenc="aac", noconv=False):
    lst = os.path.join(work, "list-%s.txt" % name)
    with open(lst, "w") as f:
        for p in norms:
            f.write("file '%s'\n" % p)
    out = os.path.join(work, "out-%s.mov" % name)
    cmd = [FF, "-hide_banner", "-v", "error", "-nostdin", "-y", *(["-auto_convert", "0"] if noconv else []), "-f", "concat", "-safe", "0", "-i", lst,
           "-c:v", "copy", "-c:a", aenc, "-b:a", "256k"]
    if last_tick:
        cmd += ["-bsf:v", "setts=duration=if(eq(NEXT_PTS\\,NOPTS)\\,1\\,DURATION)"]
    cmd += [out]
    _, dt = run(cmd)
    return out, dt


def decoded_samples(path):
    r = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "1", "-c:a", "pcm_s16le",
                        "-f", "s16le", "-"], capture_output=True)
    return len(r.stdout) // 2


from operator import lt, le, ge


def check(out, seg_frames, seg_dups, lens, wav, first_pts):
    res = {}
    info = streams(out)
    v, a = vstream(info), astreams(info)[0]
    dv, da = float(v["duration"]), float(a["duration"])
    res["4.6.3"] = (lt(abs(dv - da), 0.1), "video %.3f s / audio %.3f s / diff %.1f ms" % (dv, da, abs(dv - da) * 1000))
    ok_dts, detail = True, []
    for sel in ("v:0", "a:0"):
        d = [p[1] for p in pkts(out, sel)]
        bad = sum(1 for x, y in zip(d, d[1:]) if le(y, x))
        ok_dts = ok_dts and bad == 0
        detail.append("%s packets %d, non-increasing %d" % (sel, len(d), bad))
    res["4.6.14(i)"] = (ok_dts, "; ".join(detail))
    t = time.monotonic()
    r = subprocess.run([FF, "-v", "error", "-nostdin", "-i", out, "-enc_time_base", "demux", "-f", "null", "-"],
                       capture_output=True, text=True)
    err = r.stderr.strip()
    res["4.6.14(ii)"] = (r.returncode == 0 and not err,
                         "rc=%d, stderr %d chars, %.1f s %s" % (r.returncode, len(err), time.monotonic() - t, err[:200]))
    nf = int(ffp("-select_streams", "v:0", "-count_frames", "-show_entries", "stream=nb_read_frames",
                 "-of", "csv=p=0", out).strip().strip(","))
    need = sum(seg_frames) - sum(seg_dups)
    res["4.6.14(iii)"] = (ge(nf, need), "out %d, segs %d - dups %d = %d" % (nf, sum(seg_frames), sum(seg_dups), need))
    vp = sorted(p[0] for p in pkts(out, "v:0"))
    gaps = [y - x for x, y in zip(vp, vp[1:])]
    close = sum(1 for g in gaps if lt(g, 0.001))
    res["4.6.14(iv)"] = (close == 0, "%d pairs; min gap %.2f ms" % (close, min(gaps) * 1000))
    ns = decoded_samples(out)
    res["4.6.20(i)"] = (le(abs(ns / 48000 - da), 0.025), "%.4f s vs %.4f s, diff %.1f ms" % (ns / 48000, da, abs(ns / 48000 - da) * 1000))
    wd = float(ffp("-show_entries", "format=duration", "-of", "csv=p=0", wav).strip())
    res["4.6.20(ii)"] = (le(abs(wd - da), 0.025), "wav %.4f s vs %.4f s, diff %.1f ms" % (wd, da, abs(wd - da) * 1000))
    bounds, acc = [], 0.0
    for k, L in enumerate(lens):
        exp = acc + first_pts[k]
        got = min((p for p in vp if ge(p, acc - 0.001)), default=None)  # 容許 1 ms 內的捨入（輸出 timescale 與 1/600 不同）
        lb = max((p for p in vp if lt(p, acc - 0.001)), default=None)
        bounds.append(dict(seg=k + 1, boundary=round(acc, 4), expectFirst=round(exp, 4),
                           gotFirst=None if got is None else round(got, 4),
                           errMs=None if got is None else round((got - exp) * 1000, 2),
                           lastBefore=None if lb is None else round(lb, 4)))
        acc += L
    res["boundaries"] = bounds
    res["sumLens"] = round(sum(lens), 4)
    res["vlast"] = round(vp[-1], 4)
    res["maxGapMs"] = round(max(gaps) * 1000, 1)
    return res


def uniq(xs):
    return sorted(set(xs), key=str)


def main():
    work, variant = sys.argv[1], sys.argv[2]
    pull_first = "--pull" in sys.argv
    work = os.path.abspath(work)
    os.makedirs(work, exist_ok=True)
    T = dict()
    t0 = time.monotonic()
    if variant == "real":
        # 實錄段落：第 3 個參數是段落所在目錄（只讀；不複製、不改）
        seg_paths = sorted(glob.glob(os.path.join(sys.argv[3], "seg-*.mov")))
    else:
        with cf.ThreadPoolExecutor(8) as ex:
            segs = [f.result() for f in [ex.submit(gen_segment, work, k, variant) for k in range(len(LENS))]]
        seg_paths = [s for s, _ in segs]
    T["generate_wall"] = round(time.monotonic() - t0, 1)
    infos = [streams(p) for p in seg_paths]
    lens = [seg_len(i, p) for i, p in zip(infos, seg_paths)]
    vs = [vstream(i) for i in infos]
    cond = dict(
        size=uniq("%sx%s" % (s["width"], s["height"]) for s in vs),
        codec=uniq(s["codec_name"] for s in vs),
        profile=uniq(str(s.get("profile")) for s in vs),
        pix_fmt=uniq(s["pix_fmt"] for s in vs),
        time_base=uniq(s["time_base"] for s in vs),
        extradata_hash_distinct=len(set(s.get("extradata_hash") for s in vs)),
        has_b_frames=uniq(s.get("has_b_frames") for s in vs),
        r_frame_rate=uniq(s.get("r_frame_rate") for s in vs),
        avg_frame_rate=uniq(s.get("avg_frame_rate") for s in vs),
    )
    return work, variant, pull_first, T, seg_paths, infos, lens, cond


def main2():
    work, variant, pull_first, T, seg_paths, infos, lens, cond = main()
    seg_frames, seg_dups, first_pts, seg_meta = [], [], [], []
    for p, i, L in zip(seg_paths, infos, lens):
        pts = [x[0] for x in pkts(p, "v:0")]
        seg_frames.append(len(pts))
        seg_dups.append(len(pts) - len(set(pts)))
        origin = min(float(s.get("start_time", 0)) for s in i["streams"])
        first_pts.append(0.0 if pull_first else min(pts) - origin)
        gaps = [y - x for x, y in zip(pts, pts[1:])]
        seg_meta.append(dict(frames=len(pts), firstPts=round(min(pts), 4), lastPts=round(max(pts), 4),
                             minGapMs=round(min(gaps) * 1000, 2), maxGapMs=round(max(gaps) * 1000, 1),
                             audio=[(s["codec_name"], s["channels"], s.get("start_time"), s["duration"]) for s in astreams(i)],
                             len=L, sizeMB=round(os.path.getsize(p) / 1e6, 1)))
    cond["dups"] = sum(seg_dups)
    src_hash = []
    for p in seg_paths:
        src_hash += pkt_hashes(p)
    t0 = time.monotonic()
    with cf.ThreadPoolExecutor(5) as ex:
        rm = [f.result() for f in [ex.submit(remux, work, k, p, lens[k], pull_first) for k, p in enumerate(seg_paths)]]
    T["remux_wall_parallel"] = round(time.monotonic() - t0, 2)
    T["pcm_each"] = [round(x[2], 2) for x in rm]
    T["remux_each"] = [round(x[3], 2) for x in rm]
    norms = [x[1] for x in rm]
    wl = os.path.join(work, "pcm-list.txt")
    with open(wl, "w") as f:
        for x in rm:
            f.write("file '%s'\n" % x[0])
    wav = os.path.join(work, "audio.wav")
    _, dtw = run([FF, "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", wl, "-ar", "16000", "-ac", "1",
                  "-c:a", "pcm_s16le", wav])
    T["wav"] = round(dtw, 2)
    return work, variant, pull_first, T, lens, cond, seg_frames, seg_dups, first_pts, seg_meta, src_hash, norms, wav


def main3():
    (work, variant, pull_first, T, lens, cond, seg_frames, seg_dups, first_pts, seg_meta,
     src_hash, norms, wav) = main2()
    norm_info = []
    for n, L in zip(norms, lens):
        i = streams(n)
        v, a = vstream(i), astreams(i)[0]
        norm_info.append(dict(len=round(L, 4), v_start=v.get("start_time"), v_dur=v["duration"],
                              a_start=a.get("start_time"), a_dur=a["duration"], a_codec=a["codec_name"],
                              fmt_dur=i["format"]["duration"]))
    out = dict(variant=variant, pullFirst=pull_first, cond=cond, segments=seg_meta, norm=norm_info,
               times=T, results=dict())
    for name, last_tick, aenc, noconv in (("A-current-1tick", True, "aac", False), ("B-no-1tick", False, "aac", False),
                                          ("C-no-1tick-noconv", False, "aac", True),
                                          ("C-no-1tick-noconv-aac_at", False, "aac_at", True)):
        o, dt = concat(work, norms, name, last_tick, aenc, noconv)
        r = check(o, seg_frames, seg_dups, lens, wav, first_pts)
        r["concatSeconds"] = round(dt, 2)
        r["packetsIdentical"] = pkt_hashes(o) == src_hash
        r["outSizeMB"] = round(os.path.getsize(o) / 1e6, 1)
        out["results"][name] = dict((k, list(v) if isinstance(v, tuple) else v) for k, v in r.items())
    print(json.dumps(out, ensure_ascii=False, indent=1))


main3()
```

### A.2 `summ.py`

```python
import json, sys
d = json.load(open(sys.argv[1]))
print("variant", d["variant"], "pull", d["pullFirst"], "segments", len(d["segments"]))
print("cond", json.dumps(d["cond"]))
for s in d["segments"][:5]:
    print("seg", s["frames"], s["firstPts"], s["lastPts"], s["minGapMs"], s["maxGapMs"], round(s["len"], 4), s["sizeMB"])
print("times", json.dumps(d["times"])[:400])
for name, r in d["results"].items():
    print("==", name, "concat", r["concatSeconds"], "s; identical", r["packetsIdentical"], "; vlast", r["vlast"], "sum", r["sumLens"], "maxGap", r["maxGapMs"])
    for k in ("4.6.3", "4.6.14(i)", "4.6.14(ii)", "4.6.14(iii)", "4.6.14(iv)", "4.6.20(i)", "4.6.20(ii)"):
        print("  ", k, "PASS" if r[k][0] else "FAIL", r[k][1])
    errs = [b["errMs"] for b in r["boundaries"] if b["errMs"] is not None]
    print("   boundary err ms: max|err|", max(abs(e) for e in errs), "last", errs[-1], "first5", errs[:5])
```

### A.3 `aac.py`（第 3 節）

```python
import os, subprocess, sys, time, json
D = sys.argv[1]
os.makedirs(D, exist_ok=True)
pcm = os.path.join(D, "pcm2h.wav")
t = time.monotonic()
subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y",
                "-f", "lavfi", "-i", "sine=f=440:r=48000:d=7200",
                "-f", "lavfi", "-i", "anoisesrc=c=pink:a=0.05:r=48000:d=7200",
                "-filter_complex", "[0:a]aformat=channel_layouts=stereo[s];[1:a]pan=stereo|c0=c0|c1=c0[m];[s][m]amix=inputs=2:normalize=0[a]",
                "-map", "[a]", "-c:a", "pcm_s16le", pcm], check=True)
res = dict(genSeconds=round(time.monotonic() - t, 1), pcmBytes=os.path.getsize(pcm))
def timed(args, out):
    t = time.monotonic()
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-nostdin", "-y", "-i", pcm, *args, out], check=True)
    return round(time.monotonic() - t, 2)
res["decode_null"] = [timed(["-f", "null"], "-") for _ in range(2)]
for enc in ("aac", "aac_at"):
    o = os.path.join(D, enc + ".m4a")
    res[enc] = [timed(["-c:a", enc, "-b:a", "256k"], o) for _ in range(2)]
    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=duration,bit_rate", "-of", "csv=p=0", o], capture_output=True, text=True).stdout.strip()
    res[enc + "_probe"] = pr
print(json.dumps(res))
```

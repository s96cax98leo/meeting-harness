# ADR：影片 copy 串接的適用條件與驗證後移

- 狀態：提議（待 meeting-speed 閘門 2 核准；修正輪 1 補 D3 (a)(d)）
- 日期：2026-10-21
- 範圍：`tools/MeetingRecorder/Sources/Capture/RecordingSession.swift`（擷取設定）、`Core/Records.swift`（`RecordMeta.canvasLock`）、`bin/_record_finalize.py`
- 修訂：meeting-record 的 D8 (i)、D7（`specs/meeting-record/adr/adr-segment-writer.md:44`、`adr-video-tail-pad.md:22-31`）；推翻 meeting-record spec §4.3.4。

## 背景

- intent §7 Q3（使用者決定）：開錄時鎖定當下視窗像素、整場固定、60 fps；全場符合條件就 `-c:v copy`、碼率等於來源；不符合就整場退回現行重編；用缺陷 B、F、N 的情境重驗；`preservesAspectRatio` 與 copy 串接要先實測。
- intent §7 Q1：終點含影片成品，背景驗證不計；驗證失敗要標記並通知，處理方式交 design（C9）。
- `adr-video-tail-pad.md` 選項 C（copy）不採的理由是「copy 段與重編段混用 SPS/PPS 不一致」；`b0-audit.md:30-31` 也指出整場 SPS/PPS 要一致。
- 既有 `test_finalize.py` 的合成段落沒有錄製器的 meta 標記，§4.6.10 要求「位元率 ≥ 各段最大值」（`tests/record/test_finalize.py:192-211`）。intent §7 Q4：速度相關改動繞開既有測試。

## 選項（適用條件）

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 只看段落本身：尺寸、codec 參數、extradata 都相同就 copy | 舊場次只要剛好同尺寸也能加速 | 既有合成素材（兩段同尺寸）會改走 copy，`test_reencode_quality_and_fps_preserved` 的位元率斷言可能變紅，等於改既有測試；D8 錄的舊場次若剛好同尺寸，行為悄悄改變 |
| B. **錄製器在 `record.meta.json` 寫 `canvasLock`；只有帶這個標記、且段落條件全部成立的場次才 copy** | 舊場次與合成素材一律走現行重編，既有測試不受影響；新場次的行為由新測試定義 | 舊場次拿不到加速（2026-10-20 的保留段落量不到影片的 5 分，要用新錄的段落量，intent §2 G1 已列為缺口） |
| C. 逐段判斷，可 copy 的段 copy、其他段重編 | 理論上最快 | 正是 `adr-video-tail-pad.md` 不採的混用；intent §7 明定「不符合條件時整場退回」 |

## 選項（驗證失敗時）

| 選項 | 做法 | 代價 |
|---|---|---|
| X. **影片改名 `<同名>.verify-failed.mov`、`finalize.json.verify` 記失敗、段落保留、回 5；下次 `record finish` 強制走重編** | 壞檔不會被當成正式成品；段落還在，可以重做；不刪任何資料 | `影片/` 會留一支 `.verify-failed.mov`，要使用者自己決定刪不刪 |
| Y. 原名保留，只在 `finalize.json` 記失敗 | 最簡單 | 使用者與下游會直接拿到壞檔；重跑時覆蓋同名檔＝刪資料 |
| Z. 驗證失敗就刪影片 | 乾淨 | 刪資料要使用者當下同意（CLAUDE.md「不可逆節點」），不能自動做 |

## 決定

採 **B＋X**。

- copy 條件（全部成立）：meta 有 `canvasLock`；每段都有影片且寬高等於 `canvasLock`；codec、profile、pix_fmt、time_base 全場相同；每段 extradata 雜湊相同；沒有完全相同 PTS 的重複影格。
- copy 路徑逐段 remux（影片 `-c:v copy`、與音訊同一原點、最後一個封包長度補到段落長；音訊放音訊先出時抽好的 PCM），串接沿用現行 concat 呼叫（`-c:v copy -c:a aac -b:a 256k`），拿掉 `+faststart`。
- 發佈後才驗證；驗證逾時也當失敗處理（不走 `timedOut` 的「成品未發佈」路徑）。
- `finalize.json` 加 `videoPath: "copy"|"reencode"` 與 `verify: {status, reason?, path?}`；`manifest.json.outputVideoBitrate` 在 copy 路徑寫各段影片位元率的最大值（資訊用，實際就是來源）。

## 後果

- meeting-speed spec §3.3、§3.4、§4.4、§4.5；§6 第 1–8、10–12 條記修訂與推翻的 meeting-record 條文。
- `preservesAspectRatio` 的行為與 SCK 段落 copy 串接的乾淨度由 `video-spike` 先實測；實測不可行時，`finalize-fast` 與 `recorder-capture` 停下回報（不自行改做法）。
- 開錄後把視窗放大，成品解析度停在開錄時的大小（intent §5 Q3 (a) 的代價，使用者已在閘門 1 接受）。
- 正式 wav 不等影片（D2，`adr-ms-audio-first.md` 選項 D）：影片走 copy 或重編都不影響錄音成品的發佈時刻。
- 退回重編路徑仍會走到 `normalize`，所以 D3 (a) 的補尾幀數修正（不再只依 `r_frame_rate` 推算，spec §4.4.12）照樣要做。
- 擷取幀率（60／30 fps）與尺寸上限由 `video-spike` 量 WindowServer 負擔後交使用者決定（D3 (d)，spec §4.4.13）；決定前維持 intent §7 Q3 的 60 fps。

# 第 0 階段實測報告：切換 Space 時單視窗擷取會不會黑畫面

日期：2026-10-10　機器：MacBook Pro 16"（M3 Max）、macOS 26.6（build 25G72）
工具：`tools/MeetingRecorder`（Swift 6.4，`-target arm64-apple-macosx15.0`），`SCContentFilter(desktopIndependentWindow:)`，2 fps，畫布鎖 2992×1934 px

## 結論

**可以。Chromium 系的視窗在別的 Space 上，單視窗擷取仍然錄到真實內容，不是黑畫面。**

原本的黑畫面問題確定不是 ScreenCaptureKit 的限制。既然自己呼叫 SCK 就錄得到，問題出在 macOS 26 全新的 ⇧⌘5「錄製所選視窗」（Apple 官方文件寫 "available in macOS Tahoe 26 or later"，內部實作無公開文件）。

## 量測結果

| 情境 | 視窗 | onScreen / active | 幀狀態 | 非黑比例 | 判定 |
|---|---|---|---|---|---|
| **在別的 Space**（核心問題） | Google Chrome「[Stand-up] 範例專案」（Chromium，1496×938） | **false / false** | complete 3（12%）、idle 22（88%） | **0.766**，0 幀全黑 | **通過** |
| 前景持續重繪（基線） | 終端機（1496×938） | true / true | complete 17（**100%**） | 1.000，0 幀全黑 | 通過，probe 本身驗證無誤 |

錄出來的影片獨立覆核（不只看 probe 自己的數字）：Chrome 那場的最後一幀 **平均亮度 205.7/255、非黑像素 83.8%** —— 內容是真的。

基線那場 8 秒擷取產出 8.09 秒、17 幀、2 fps，數字完全對得上，所以 probe 的計數與時間軸可信。

## 兩個順帶發現

**1. `onScreenWindowsOnly: false` 是必要的，而且有效。** 視窗清單裡絕大多數視窗此刻都標「不在畫面上」（它們在別的 Space），給 `true` 的話這些全部會從清單消失 —— 那正是「要錄的會議視窗挑不到」的來源。Apple 官方 sample 用 `true`，WWDC22 建單視窗 filter 時用 `false`，我們必須跟後者。

**2. 影片在最後一次畫面變化處結束，不是時間軸被壓縮。** Chrome 那場擷取 12 秒卻只產出 1.49 秒影片：3 個 `complete` 幀的 PTS 落在 t=0.3/0.8/1.3 秒（**正確的實際時間**），之後畫面沒變就沒有新幀。所以不是壓縮，是「沒有新內容就不寫」。

含音訊錄製時的影響：影片軌會比音訊軌短，播放器定住最後一幀。這要在第 1 階段用「影片與音訊 duration 差 < 100 ms」那條驗收去量，必要時在 finalize 補幀。

## 還沒驗、要在第一場真實會議補的

| # | 情境 | 為什麼還沒驗 |
|---|---|---|
| 1 | **Teams 在通話中**、視窗在別的 Space | Teams 當時沒開。Chrome 與 Teams 同屬 Chromium，所以「Chromium 在非作用中 Space 停止重繪」的疑慮已大幅降低，但 Electron 的 app 層行為仍可能不同 |
| 2 | **native 全螢幕**後切到別的 Space | 社群記載 fullscreen Space 不被 window server 合成。需要人去操作 |
| 3 | 視窗**最小化** | 官方承認的唯一會暫停情形，預期看到 `suspended`。需要人去操作 |
| 4 | Mission Control 開著 | 需要人去操作 |

量測指令：

```bash
bash tools/MeetingRecorder/probe.sh windows              # 挑 windowID
bash tools/MeetingRecorder/probe.sh <windowID> 30 <情境標籤>
```

受測 app 必須真的在通話中或畫面有動靜 —— 靜態視窗會合法地回 `idle`，那樣就分不出「app 停止重繪」與「畫面本來就沒變」。

## 一個踩到的坑（已證實官方說法）

第一次跑時回「使用者拒絕應用程式、視窗、顯示器擷取的TCC」，但查 TCC 資料庫發現 `kTCCServiceScreenCapture | com.meetingharness.recorder | 2`（**已允許**）。

這就是 Apple 官方 sample 明寫的那件事：**授權對已經啟動的程式不生效，必須完全結束 app 再重開。** 失敗訊息長得像「被拒絕」，很容易誤判成權限沒給。`probe.sh` 因此每次啟動前都先 `osascript -e 'quit app'`，preflight 也必須把這個情形與「真的沒授權」分開來報。

## 現在的簽章狀態

ad-hoc（`codesign -s -`），所以每次重建 CDHash 都會變，可能掉授權。要建一張固定的自簽憑證：

1. 開「鑰匙圈存取」→ 選單「鑰匙圈存取 → 憑證輔助程式 → 製作憑證…」
2. 名稱 `MeetingHarness Dev`，身分類型「自簽根憑證」，憑證類型「程式碼簽署」
3. 重跑 `bash tools/MeetingRecorder/build.sh`，它會自動改用那張憑證

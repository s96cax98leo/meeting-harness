# ADR：登入時自動開啟 menu bar（R2，F7）

- 狀態：提議（待 R2 閘門 2 核准）
- 日期：2026-10-12
- 範圍：`tools/MeetingRecorder/Sources/main.swift`、`Sources/Trigger/Preferences.swift`、`Resources/`、`build.sh`

## 背景

- 使用者要「偏好設定加登入自動開」（brief:13、:28），brief 指定 `SMAppService.mainApp`，狀態是 `.requiresApproval` 時引導到系統設定的登入項目。
- menu bar 目前要以 `open -n -a MeetingRecorder --args menubar` 啟動（`design.md §8`）；app **無參數**時印 help 後 `exit(0)`（`Sources/main.swift:73-75`）。
- `SMAppService.mainApp` 的 API 只有 `register()`／`unregister()`／`status`，沒有傳參數的介面；登入時系統以 app 本身啟動，依 API 形狀推論不帶任何參數（未實測，依約束不得在 agent 端註冊或啟動 app，`research-specs-adr.md` R2-4）。
- 點通知、Finder 雙擊 app 也是無參數啟動（`research-code-contracts.md` C3）。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. `SMAppService.mainApp`＋**無參數改進 menubar 模式** | `main.swift` 以 `launchMode(arguments:)` 決定模式：沒有參數（或只有 `-psn_` 開頭的參數）→ `menubar`；`help`／`-h`／`--help` 照舊印說明 | 改變「無參數印 help」的既有行為（沒有測試釘住、沒有呼叫端依賴，`grep` 無結果）；從終端機直接執行二進位不帶參數會開出 menu bar（單一實例鎖會擋重複） |
| B. `SMAppService.agent(plistName:)`，在 `Contents/Library/LaunchAgents/` 放帶 `menubar` 參數的 plist | 參數由 plist 帶 | `build.sh` 要多放一個檔並納入簽章；launchd agent 在使用者登出前會由 launchd 管理重啟策略，與「結束選單」的語意要另外對齊；與 brief 指定的 API 不同 |
| C. 不自己註冊，只在偏好設定提供「打開系統設定的登入項目」並教使用者手動加入 | 程式最少 | 手動加入的登入項目同樣是無參數啟動，仍需 A 的改動才會出現 menu bar；使用者體驗差 |

## 決定

採 **A**。理由：改動最小、符合 brief 指定的 API；同一個改動也修好「從 Finder 點 app 沒反應」與「點通知重新啟動 app 卻沒有 menu bar」。

落實：
- `launchMode(arguments:)` 是 Core 純函式（`spec.md` R2 §3.14），`main.swift` 只照它分派。
- 偏好設定的「登入時自動開啟」：勾選呼叫 `SMAppService.mainApp.register()`、取消呼叫 `unregister()`；顯示依 `loginItemDisplay(_:)`；`.requiresApproval` 時顯示說明並提供「打開系統設定的登入項目」按鈕（`SMAppService.openSystemSettingsLoginItems()`，只打開設定畫面，不代改）。
- `register()` 只在使用者按下勾選時呼叫，app 啟動、menu bar 建立時都不得自動註冊（不改使用者系統設定）。

## 後果

- `spec.md §4.12.9` 的 dispatch 清單多了「無參數＝menubar」，記 §6。
- `SMAppService` 對 app 位置（`~/Applications`）、簽章身分改變（重建）後登入項目是否仍有效，**未能確認**；只能由使用者在 t7 驗（重新登入後 menu bar 出現；重建後再登入一次）。若不成立，退回 B 或 C 屬使用者決定。

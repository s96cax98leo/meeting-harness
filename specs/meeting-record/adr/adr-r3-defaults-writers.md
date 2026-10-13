# ADR：`record.defaults.json` 改為兩個寫者、共用鎖、讀後合併（R3，推翻 R2-Q3）

- 狀態：提議（待 R3 閘門 2 核准）
- 日期：2026-10-13
- 範圍：`bin/record.sh`（`write_defaults`，`:329-341`；呼叫點 `:460`）、`bin/lib/_record_lib.py`（`merge_defaults`；頂層寫法 `meeting sync`，修正輪由 `meeting record sync` 改名）、`tools/MeetingRecorder/Sources/Core/Settings.swift`（`writeOnboardingDefaults`、`mergedDefaultsJSON`）、`Trigger/Onboarding.swift`
- 關係：推翻 R2-Q3「`record.defaults.json` 維持 `record.sh` 單一寫者」（`intent.md:278`、`:306`）

## 背景

- 只用選單列 app 的人，要先在終端機跑一次 `meeting record` 才有 `harness` 與 `root`，選單才能開錄（`ui` §3.7，P1-4）。使用者決定 1（D6 取 A）：app 在首次引導寫這兩個鍵。
- 現行 `write_defaults` 整檔覆寫 7 個鍵；app 或 `meeting sync` 寫的其他鍵會被下一次開錄洗掉。
- R2 的 `test_r2_static.py::test_defaults_single_writer` 斷言 Swift 不得寫 defaults 檔。

## 選項

| 選項 | 做法 | 代價 |
|---|---|---|
| A. 兩個寫者共用 `record.defaults.lock`（flock），一律「讀 → 只改自己的鍵 → mkstemp＋rename」；app 只寫 `harness`、`root`，只在首次引導（本案） | 引導可以直接完成設定；`meeting sync` 寫的 `syncCompensation` 不會被洗掉 | 推翻 R2-Q3、改既有靜態測試（`spec.md` §6 第 123 條）；多一個共用的合併函式（`bin/lib/_record_lib.py` 的 `merge_defaults`） |
| B. 維持單一寫者：app 引導時呼叫 `meeting record` 的某個 CLI 去寫 | 寫者仍只有一個 | app 要找到並執行 harness 的 `bin/meeting.sh`，但引導時還不知道 harness 在哪（正是要設定的東西），循環依賴 |
| C. app 另開自己的檔（例如 `menubar.settings.json` 裡放 root、harness），`record.sh` 不讀 | 不碰 defaults | 同一個設定兩處存放、兩邊不同步；R2 已定案「root 一個設定兩處顯示」（R2-Q3），C 等於推翻得更多 |

## 決定

採 **A**。理由：B 有循環依賴、C 造成設定分裂；A 的代價只是一把鎖和合併寫入，而且同一個合併寫法也解決了 `syncCompensation` 被洗掉的問題（R3-Q5、R3-Q6）。

規則：
1. 任何寫者都不得刪除自己不認得的鍵；檔案不是 JSON 物件時不寫、報錯（不覆寫壞檔）。
2. 鎖等待最多 5 秒，逾時放棄寫入並報錯（`record.sh` 照常開錄，defaults 只是記憶）。
3. app 寫 defaults 的程式只有 `Core/Settings.swift` 的 `writeOnboardingDefaults` 一處，呼叫端只有 `Trigger/Onboarding.swift`（靜態測試鎖住）。
4. 合併函式 `merge_defaults` 先做（`r3-record-lib`，第 1 層），`record.sh` 的 `write_defaults`（`r3-lock`）與 `meeting sync`（`r3-search`）都呼叫它；app 端後做（`r3-onboarding-settings`）。

## 後果

- `spec.md` §6 第 123 條改既有測試預期；§3.16 記兩個寫者與新鍵。
- 舊版 `record.sh`（R3 之前）仍會整檔覆寫；本機只有一份 harness，合併後就不再有舊版寫者。

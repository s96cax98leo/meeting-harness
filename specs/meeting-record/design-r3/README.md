# R3 設計稿定案：設計語言「暗房」

- 日期：2026-10-13。性質：使用者在 R3 design 段選定的設計方向，由 spec-author 寫成可實作的規則。**本檔是 `spec.md` R3 段 UI 外觀條文（§4.38–§4.44）的依據**；兩者不一致時以 `spec.md` 為準，並回報。
- 原始稿：本目錄的 `*.dc.html`（9 個畫板，從設計工具匯出的原始檔，未修改）。稿裡的 `./support.js` 與 Google Fonts 連結是設計工具的執行環境，**不是** app 的資源；app 不載入任何外部字型或網路資源。
- 選定（使用者）：U1＝C 錄製膠囊（含麥克風靜音分段膠囊）；U2＝C 收在螢幕邊緣；U4＝A 分步精靈；U5＝A 7 個工具列分頁；U6＝A 依階段整份換掉；U7＝A 錄製點＋聲波；F2＝A 確認對話框、錄製照常進行（預設鍵「繼續錄製」）；F3＝A 一般通知（內文只放 app 名稱）。
- 公開 repo：稿與本檔只有「Teams」等通用 app 名稱與「[Stand-up] 範例專案」；複製前後都以 run 目錄的名稱清單掃過（結果：沒有）。

## 0. 讀稿方式

| 畫板 | 內容 | 要看的地方 |
|---|---|---|
| `Main.dc.html` | 設計語言：底色、訊號色、字、狀態圖示 | 色值的唯一來源 |
| `U1-MenuBar.dc.html` | 8 種狀態 × 3 個方向 × 深淺選單列 | **只看 C 列**（「C ✓ 錄製膠囊」深、淺兩列）；`muteCap` 是靜音分段膠囊 |
| `U2-HUD.dc.html` | 三個方向 | **只看 C 欄**（「收在螢幕邊緣」）；底下三張狀態條（告警、暫停、完成）共用 |
| `U6-Menu.dc.html` | 四個選單 | 只看兩張「A ★」（待機、錄製中） |
| `F2-Discard.dc.html`、`F3-Detect.dc.html`、`U4-Onboarding.dc.html`、`U5-Settings.dc.html`、`U7-AppIcon.dc.html` | 三個方向 | 只看「A ★」 |

稿的 px 一律當 pt 讀（稿是 1× 畫板）。

## 1. 設計 token（Core 常數，`Sources/Core/DesignTokens.swift`）

**規則**：色值、字級、間距都是 `Core/` 的常數（Core 不 import AppKit，色值用 `"#RRGGBB"` 大寫字串，AppKit 端轉成 `NSColor`）；`swift:R3DesignTokenTests.swift` 逐一驗值。AppKit 端不得自己寫色值或改用系統色（`systemRed` 等），要換色只改 Core。名稱與簽名見 `spec.md` §3.20。

### 1.1 色彩

| token（`DarkroomColor.`） | 值 | 稿上的名字／出處 | 用途 |
|---|---|---|---|
| `ink` | `#0F1115` | 墨（Main） | 深色視窗底、亮按鈕上的字 |
| `surface` | `#171A21` | 面（Main） | HUD、引導視窗、設定視窗的面 |
| `raised` | `#1F232C` | 浮（Main） | 列、次要按鈕底 |
| `light` | `#F6F5F2` | 淺色（Main） | 淺色外觀的視窗底 |
| `line` | `#2A2F3A` | Main 卡片框 | 分隔、音量條軌道 |
| `lineStrong` | `#3A404D` | U2 外框 | HUD 外框、次要按鈕框 |
| `text` | `#ECEEF2` | Main 字 | 主文字（深色） |
| `textSecondary` | `#C3C9D4` | Main 次字 | 說明 |
| `textTertiary` | `#9AA3B2` | Main 標籤 | 註記、快捷鍵提示 |
| `textDisabled` | `#5B6372` | U6 灰掉項 | 停用、待機點 |
| `recording` | `#FF4D4F` | 錄製（Main） | 錄製中紅點、錄製膠囊、停止鈕 |
| `attention` | `#F5A524` | 注意（Main） | 告警、暫停 |
| `processing` | `#8B7CF6` | 處理（Main） | 準備中、收尾中 |
| `done` | `#2DD4BF` | 完成（Main） | 已允許、麥克風音量條 |
| `recordingText` | `#FF6B6E` | U1 C「需處理」字 | 深底上的紅字 |
| `attentionText` | `#F7C46C` | U2 暫停條字 | 深底上的黃字 |
| `processingText` | `#B9AEFF` | U1 C「檢查中」字 | 深底上的紫字 |
| `doneText` | `#5EE6D2` | U2 完成條連結 | 深底上的青字 |
| `onAttention` | `#1A1206` | U1 C 暫停膠囊字 | 黃底上的字 |
| `mutedSegment` | `#1A0B0C` | U1 C `muteCap` 左段 | 靜音分段膠囊左段 |
| `onSignal` | `#FFFFFF` | U1 C 膠囊白字 | 紅、紫底上的字 |
| `menuBarDark` | `#1E2129` | U1 深色選單列 | **只當對比計算的參考底**（實際選單列是半透明，見 §7） |
| `menuBarLight` | `#E9E7E2` | U1 淺色選單列 | 同上；也是淺色外觀的「面」 |
| `textOnLight` | `#1A1C21` | U1 淺色列字 | 淺色外觀主文字 |
| `lineOnLight` | `#C9C6BF` | U1 淺色列軌道 | 淺色外觀分隔與軌道 |

**對比補正（稿上沒有，spec-author 依 WCAG 補的；數字可用 §1.4 的公式重算）**：稿只把膠囊畫在深色選單列上的顏色直接搬到淺色列，淺色列上紫字 `#B9AEFF` 只有 1.61:1、紅字 `#FF6B6E` 2.24:1、黃底 `#F5A524` 對選單列 1.65:1；所以淺色外觀與「增加對比」另有深一階的色：

| token | 值 | 用在 | 對比（對誰） |
|---|---|---|---|
| `recordingOnLight` | `#D92D30` | 淺色列的錄製膠囊底 | 對淺色列 3.89；白字 4.81 |
| `processingOnLight` | `#6D5BD0` | 淺色列的收尾中膠囊底；深色「增加對比」的收尾中底 | 對淺色列 4.19；對深色列 3.11；白字 5.18 |
| `processingTextOnLight` | `#5E4BC4` | 淺色列的「檢查中」框與字；淺色「增加對比」的收尾中底 | 對淺色列 5.18；白字 6.40 |
| `failedTextOnLight` | `#B42318` | 淺色列的「需處理」框與字 | 對淺色列 5.32 |
| `attentionTextOnLight` | `#8A5A00` | 淺色列暫停膠囊的外框；淺色選單的告警列字 | 對淺色列 4.80 |
| `doneOnLight` | `#0F766E` | 淺色外觀的麥克風音量條、已允許 | 對淺色列 4.43 |
| `recordingHighContrast` | `#CC2F32` | 深色「增加對比」的錄製膠囊底 | 對深色列 3.08；白字 5.22 |
| `recordingHighContrastOnLight` | `#C42B2E` | 淺色「增加對比」的錄製膠囊底 | 對淺色列 4.55；白字 5.63 |

### 1.2 字（預設不打包字型，見 §8）

| token（`DarkroomType.`） | pt／字重 | 稿上的值 | 用途 |
|---|---|---|---|
| `capsule` | 14／bold | 稿 13／600 | 選單列膠囊的計時與「檢查中」等字（**放大到 14 bold**：白字對紅底 3.27:1，只有 WCAG 大字〔14pt 粗體以上〕門檻 3:1 過得去；見 §7 第 1 點） |
| `hudTabTimer` | 13／semibold | 13／600 | HUD 收合標籤的直排計時 |
| `hudTimer` | 18／semibold | 18／600 | HUD 展開區計時 |
| `hudLabel` | 13／regular | 13 | HUD 展開區的「錄製中」與音量標籤 |
| `hudButton` | 12／regular（停止鈕 bold） | 12 | HUD 四顆按鈕 |
| `hudAlert` | 12／bold | 12／700 | HUD 告警膠囊 |
| `menuMeterLabel` | 12／regular | 12 | 選單音量條標籤 |
| `onboardingTitle` | 26／bold | 26／700 | 引導步驟標題 |
| `onboardingBody` | 15／regular | 15 | 引導說明 |
| `rowTitle` | 15／bold | 15／700 | 權限列名稱 |
| `rowDetail` | 13／regular | 13 | 權限列說明與狀態 |
| `button` | 14／bold（次要鈕 regular） | 14 | 引導底部按鈕 |
| `stepLabel` | 12／regular | 12 | 引導步驟指示 |
| `settingsTabLabel` | 12／regular | 12 | 設定分頁標籤 |
| `settingsRowLabel` | 14／regular | 14 | 設定列標籤 |
| `caption` | 12／regular | 12 | 設定說明文字 |

字型對應：介面字（稿的 Noto Sans TC）＝`NSFont.systemFont(ofSize:weight:)`（中文由系統落到 PingFang TC）；標題（稿的 Space Grotesk＋Noto Sans TC 粗體）＝同上 bold；計時（稿的 JetBrains Mono）＝`NSFont.monospacedDigitSystemFont(ofSize:weight:)`（SF Pro 等寬數字）；指令與路徑等純等寬文字＝`NSFont.monospacedSystemFont(ofSize:weight:)`（SF Mono）。

### 1.3 間距與尺寸（pt）

| token（`DarkroomMetric.`） | 值 | 出處 |
|---|---|---|
| `spacing` | `[4, 8, 12, 16, 24]` | 稿的間距（4／6／8／10／12／14／16／22／28）收斂成 4 的倍數階梯；元件內另列的值以下表為準 |
| `capsuleHeight` | 20 | U1 C（字 13＋上下 4，放大字後取 20，選單列 24 內） |
| `capsulePaddingH` | 10 | U1 C `padding: 4px 10px` |
| `capsuleGap` | 6 | U1 C `gap: 6px` |
| `capsuleDot` | 8 | U1 C 紅點 r=4 |
| `capsuleBorder` | 1.5 | U1 C `border: 1.5px` |
| `muteSegmentPaddingLeading`、`muteSegmentPaddingTrailing` | 9、7 | U1 C `muteCap` 左段 `padding: 4px 7px 4px 9px` |
| `badgeDiameter`、`badgeStroke` | 7、1.5 | Main「錄製中有告警」角標（r=4 縮到 16pt 圖示的比例） |
| `hudTabWidth`、`hudTabHeight`、`hudTabCornerRadius` | 34、120、14 | U2 C 收合標籤 |
| `hudTabDot` | 10 | U2 C 紅點 r=5 |
| `hudTabTopFraction` | 0.25 | 標籤頂端距可見區頂端＝可見區高度 × 0.25（稿只畫了大約位置；避開選單列與瀏海） |
| `hudPanelWidth`、`hudPanelPadding`、`hudPanelCornerRadius` | 230、16、16 | U2 C 展開區 |
| `hudButtonHeight`、`hudButtonCornerRadius`、`hudButtonGap` | 44、10、6 | U2 C 按鈕（2×2） |
| `meterBarHeight`、`meterLabelWidth`、`menuMeterWidth` | 5、40、240 | U6 A 音量條 |
| `onboardingWidth`、`onboardingHeight` | 620、560 | U4 A（固定尺寸） |
| `onboardingPaddingH`、`onboardingPaddingV` | 32、28 | U4 A |
| `rowPaddingH`、`rowPaddingV`、`rowCornerRadius`、`rowGap` | 16、14、14、10 | U4 A 權限列 |
| `buttonHeight`、`buttonCornerRadius` | 44、12 | U4 A 底部按鈕 |
| `settingsWidth`、`settingsTabWidth` | 600、76 | U5 A（寬固定、高跟內容） |

### 1.4 對比的計算（可重跑）

`contrastRatio(a, b)`＝WCAG 2.x 相對亮度公式：每個通道 `c/255`，`c ≤ 0.04045` 時 `c/12.92`，否則 `((c+0.055)/1.055)^2.4`；`L = 0.2126R + 0.7152G + 0.0722B`；比值 `(L亮+0.05)/(L暗+0.05)`。門檻：一般文字 4.5、大字（14pt 粗體以上）與非文字元素 3.0（WCAG 1.4.3、1.4.11）。§1.1 的數字都用這個公式算，`R3DesignTokenTests` 用同一個函式驗。

## 2. U1 選單列：C 錄製膠囊（8 種外觀）

自訂繪製（**自訂**：`NSImage(size:flipped:drawingHandler:)` 畫成非 template 圖，設給 status item 的 `button.image`）；只有待機用 SF Symbol template。所有顏色來自 `menuBarCapsuleStyle(…)`（`spec.md` §3.20），依 `button.effectiveAppearance` 是否深色、`NSWorkspace.shared.accessibilityDisplayShouldIncreaseContrast` 取值。紅色一律非 template（spec §6 第 107 條）。

| # | 外觀 | 形狀 | 內容 | 深色選單列 | 淺色選單列 | 「增加對比」 | VoiceOver（`menuBarAccessibilityLabel`） |
|---|---|---|---|---|---|---|---|
| 1 | 待機 | SF Symbol `record.circle`，template | 無字 | 系統上色 | 系統上色 | 系統 | 「MeetingRecorder：待機中」 |
| 2 | 準備中 | 外框膠囊 | 「檢查中」 | 框 `processing`、字 `processingText` | 框與字 `processingTextOnLight` | 同左 | 「MeetingRecorder：開錄前檢查中」 |
| 3 | 錄製中 | 實心膠囊 | 白點＋計時 | 底 `recording`、字 `onSignal` | 底 `recordingOnLight` | 底 `recordingHighContrast`／`…OnLight` | 「MeetingRecorder：錄製中，已錄 12 分 34 秒」 |
| 4 | 錄製中・麥克風靜音 | **分段膠囊**：左段 `mutedSegment` 底＋`mic.slash`（palette 白，非 template）；右段同 #3 | 左：麥克風斜線；右：白點＋計時 | 整顆加 1pt `recording` 外框（深色列上左段才看得出邊界） | 同 #3 | 同 #3 | 「…錄製中，已錄 12 分 34 秒，麥克風靜音」 |
| 5 | 錄製中・有告警 | 同 #3，加 1.5pt `attention` 外框，**右上角加角標** | 白點＋計時＋角標 | 角標：直徑 7、底 `attention`、1.5pt `onAttention` 描邊 | 同左 | 同左 | 「…錄製中，已錄 12 分 34 秒，有告警：<最新告警訊息>」 |
| 6 | 已暫停 | 實心膠囊 | 暫停符號（兩條）＋停住的計時 | 底 `attention`、字與符號 `onAttention` | 加 1pt `attentionTextOnLight` 外框 | 同左 | 「…已暫停，已錄 12 分 34 秒」（有告警時加「，有告警」） |
| 7 | 收尾中 | 實心膠囊 | 「收尾中」 | 底 `processing`、字 `onSignal` | 底 `processingOnLight` | 底 `processingOnLight`／`processingTextOnLight` | 「MeetingRecorder：收尾中」 |
| 8 | 需要處理 | 外框膠囊 | 「需處理」 | 框 `recording`、字 `recordingText` | 框與字 `failedTextOnLight` | 同左 | 「MeetingRecorder：需要處理：<狀態句>」 |

- **與稿不同的兩處（都是為了可及性，§7 第 1、2 點）**：(1) 有告警在稿上只換外框顏色（黃框紅底 1.60:1，灰階下與錄製中分不出來），補上 Main 畫板「錄製中有告警」的角標；(2) 字從 13 放大到 14 bold。
- 暫停＋告警（M6b 且 `alertBadge`）：暫停外觀，仍帶角標（角標的深色描邊在黃底上看得到）。
- 計時：`timerText`（`9:59`／`59:59`／`1:00:00` 三種寬度），等寬數字；設定「選單列計時」關掉時，#3–#6 只留點或符號，膠囊照畫。
- 灰階可分：8 種的（形狀、符號、固定字、是否有計時、是否有角標）兩兩不同（`R3DesignTokenTests` 驗）。
- 寬度：膠囊是最寬的選單列外觀（錄製中約 70–80pt），最容易被瀏海擠掉；依 D4＝A，偵測到被擋住時自動顯示 U2（`spec.md` §4.40.1、§4.40.3）。
- 動態：不加 Breathe／Pulse（選單列每秒重畫一次已足夠；「減少動態效果」下行為相同）。

## 3. U2 錄製中小窗：C 收在螢幕邊緣

整個 HUD 是**自訂** `NSPanel`（`.nonactivatingPanel`、`sharingType = .none`、所有桌面可見）。**HUD 一律用深色**（暗房；不跟系統淺色），HIG 的 HUD 面板本來就是深色。

| 狀態 | 外觀 |
|---|---|
| 收合（預設） | 貼在螢幕右緣（`hudPosition = right`；`left` 時鏡像）的直立標籤 34×120、內側圓角 14；底 `surface` 不透明度 0.94、1pt `lineStrong` 外框（貼邊那側無框）；內容：直徑 10 的 `recording` 點、間距 10、計時直排（字轉 90°，`hudTabTimer`）。**自訂**繪製直排字 |
| 展開（滑鼠移入標籤） | 從同一邊緣長出 230 寬的面板（頂端對齊標籤頂端），內距 16、內側圓角 16、底 `surface` 0.96；第 1 行：「錄製中」（`hudLabel`、`textSecondary`）＋右側計時（`hudTimer`）；第 2–3 行：系統、麥克風兩條音量條（取 A 稿的樣式：軌道 `line`、系統 `text`、麥克風 `done`，高 6）；底下 2×2 四顆按鈕「暫停」「靜音」「標記」「停止」（高 44、圓角 10、間距 6；前三顆底 `raised`、框 `lineStrong`、字 `text`；停止底 `recording`、白字 bold） |
| 收合時機 | 滑鼠離開面板 0.6 秒後收合；點一下標籤固定展開，再點一下取消固定 |
| 暫停 | 標籤紅點換成兩條 `attention` 暫停符號、計時字色 `attentionText`；展開區「錄製中」改「已暫停」、「暫停」鈕改「繼續」 |
| 麥克風靜音 | 標籤計時下方加 12pt `mic.slash`（白）；展開區麥克風條換成「已靜音」字；「靜音」鈕改「取消靜音」並以選取樣式（底 `text`、字 `ink`）顯示 |
| **告警（加強）** | 有新的告警類 warning（`newAlertWarnings` 非空）時：(1) 標籤外框改 2pt `attention`，並維持到本場結束（`warnings` 只累加）；(2) **自動展開一次 `hudAlertExpandSeconds`＝8 秒**，展開區第 1 行下方出現告警膠囊（底 `attention`、字 `onAttention`、`hudAlert`，例「麥克風 15 秒沒有聲音」），8 秒後若滑鼠不在面板內就收合；之後同一則告警不再自動展開 |
| 位置 | 有選單列圖示的那個螢幕（`statusItem.button.window.screen`，取不到用 `NSScreen.main`）的可見區；標籤頂端＝可見區頂端往下 25% |
| 不顯示 | 場次名稱、視窗標題 |

- 稿 C 收合時沒有音量條（依稿不放）；音量條只在展開區（取 A 稿樣式）。
- 「減少透明度」：底改不透明（alpha 1.0）。「增加對比」：外框改 2pt `text`（告警時仍是 `attention`）。「減少動態效果」：展開、收合、自動展開都不做滑動，直接出現與消失；正常時動畫 0.2 秒。
- VoiceOver：標籤 `accessibilityLabel`＝「錄製小窗：」＋`menuBarAccessibilityLabel` 去掉前綴的部分；按鈕「暫停錄製（⌃⌥⌘P）」／「繼續錄製（⌃⌥⌘P）」、「麥克風靜音（⌃⌥⌘M）」／「取消麥克風靜音（⌃⌥⌘M）」、「加標記（⌃⌥⌘B）」、「停止錄製並收尾」（toolTip 同字）；音量條的 `accessibilityValue` 同選單音量條。
- 完成卡片（稿下方「錄製完成・42 分鐘」）：**不做**——`spec.md` §4.40.1 規定收尾中與之後 HUD 不顯示，完成改由既有完成通知。

## 4. U6 選單：A 依階段整份換掉

選單本身維持系統 `NSMenu`（外觀由系統決定，HIG「Display a menu — not a popover」）；稿上「開始錄製」「停止錄製並收尾」的紅底醒目列**不做**（要每列換自訂 view，會失去系統的鍵盤導覽與高亮）。自訂的只有：

- **標題列**（`status`）：`attributedTitle`（`menuFont` bold、`labelColor`）＋左側 10pt 圓點圖：待機 `textDisabled`、錄製中家族 `recording`（暫停時 `attention`）、收尾中 `processing`、失敗為 `recording` 空心環。
- **音量條**（`levels`，**自訂** `LevelMeterView`，240×44）：兩行「系統」「麥克風」（標籤寬 40、`menuMeterLabel`），條高 5、圓角 2.5；深色：軌道 `line`、系統 `text`、麥克風 `done`；淺色：軌道 `lineOnLight`、系統 `textOnLight`、麥克風 `doneOnLight`；長度＝`levelFraction(dBFS:)`；靜音時麥克風那行改「已靜音」字。每 0.5 秒更新、不可聚焦。
- **告警列**（`alert`，只在有告警類 warning 時顯示）：圖 `exclamationmark.triangle.fill`（palette `attention`），字為最新告警訊息（40 字截斷、完整放 toolTip），字色深色外觀 `attentionText`、淺色 `attentionTextOnLight`。

項目與分組（分組之間一條分隔線；`menuGroups(stage:)`）：

| 階段 | 組 1 | 組 2 | 組 3 | 組 4 | 組 5 |
|---|---|---|---|---|---|
| 待機 | 標題「待機中」 | 開始錄製 ⌃⌥⌘R、錄其他視窗 ▸、存到：<資料夾> ▸ | 打開場次資料夾、顯示上一場成品 | 設定… ⌘,、結束 MeetingRecorder 選單 ⌘Q | — |
| 錄製中 | 標題、音量條、告警列 | 暫停錄製 ⌃⌥⌘P、麥克風靜音 ⌃⌥⌘M、加標記（已有 N 個）⌃⌥⌘B | 停止錄製並收尾、捨棄這次錄製… | 顯示錄製小窗、打開場次資料夾 | 設定… ⌘,、結束 MeetingRecorder 選單 ⌘Q |
| 收尾中 | 標題 | 取消收尾 | 打開場次資料夾 | 設定…、結束 MeetingRecorder 選單 | — |
| 失敗 | 標題 | 錯誤詳情…、複製完整訊息與補救指令 | 開始錄製、錄其他視窗、存到 | 打開場次資料夾、顯示上一場成品 | 設定…、結束 MeetingRecorder 選單 |

- 字面的新舊（`spec.md` §6 第 134 條）：「錄這個視窗」→「錄其他視窗」；「停止錄製」→「停止錄製並收尾」；「偏好設定…」→「設定…」（設計審查 R2 N-4）；新增「顯示錄製小窗」。「開始錄製（用上次的設定）」建立時的字面不變，快取的視窗清單裡**恰有一個 ★** 時改顯示「開始錄製：<app 名稱>」（例「開始錄製：Teams」）。
- 與稿不同：稿的錄製中選單沒有「結束」、待機沒有「打開場次資料夾」，依 `spec.md` §4.41.2（ADR `adr-r3-menu-stages.md`）保留；稿把「停止錄製並收尾」標成 ⌃⌥⌘R，但 ⌃⌥⌘R 只做開始（`r2HotKeys`，D7＝A 不改快捷鍵），**不採用**；稿的「上一場：10/13 14:05・42 分鐘」需要新的上一場資料來源，本輪維持「顯示上一場成品」（衍生工作）；「結束 MeetingRecorder 選單」保留「選單」兩字（只結束 menu bar、不停錄製，比稿的字面準確）。

## 5. F2 捨棄這次錄製：A 確認對話框，錄製照常進行

用系統 `NSAlert`（外觀由系統決定；稿 A 的深色卡片是示意，取其文字、按鈕順序與預設鍵）。打開前先 `NSApp.activate`（accessory app 不先帶到前面，對話框會被其他視窗蓋住）。

| 元素 | 字面 |
|---|---|
| 標題（`messageText`） | 「捨棄這次錄製？」 |
| 說明（`informativeText`） | 「<spokenDuration>。會停止錄製、不收尾、不產生成品；這場的錄音資料夾會移到垃圾桶，可從垃圾桶復原。」例：「已錄 42 分 7 秒。會停止錄製、…」 |
| 第一顆按鈕（預設，Return） | 「繼續錄製」 |
| 第二顆按鈕 | 「捨棄並移到垃圾桶」，`hasDestructiveAction = true`、`keyEquivalent = ""`（Return、Esc 都按不到） |
| 圖示 | app 圖示（U7） |

- 與稿不同：稿的說明寫「整個場次資料夾移到垃圾桶」，實際只移 `錄音/`（`spec.md` §4.42.3、§7 疑慮 51），照實際改寫。
- 對話框打開期間錄製照常；按「繼續錄製」沒有任何副作用。不顯示場次名稱與路徑。

## 6. 其他畫面

### 6.1 F3 錄這個會議？：A 一般通知
系統通知外觀。標題「錄這個會議？」；內文「<app 名稱> 正在使用麥克風。要開始錄製嗎？」（app 名稱＝前景 app 的 `localizedName`，取不到用「會議 app」；**不放視窗標題**）；動作「開始錄製」「這場不用」；`interruptionLevel` `.active`、`threadIdentifier` `"mh.app"`（`spec.md` §4.39.1）。

### 6.2 U4 首次引導：A 分步精靈 5 步
固定 620×560 視窗（跟系統深淺色；深色用 `ink`／`surface`／`raised`，淺色用 `light`／`menuBarLight`／`textOnLight`）。上方 5 段步驟條（高 4、間距 8；已完成 `done`、目前 `text`、未到 `line`）與標籤「歡迎」「權限」「存檔位置」「選單列空間」「試錄」。底部「略過」（文字鈕）、「上一步」（外框）、「下一步」（主鈕：底 `text`、字 `ink`；最後一步「完成」）。**自訂**：步驟條、權限列、主鈕。

| 步 | 標題 | 內容 |
|---|---|---|
| 1 歡迎 | 「錄會議，全部留在這台電腦」 | 「錄指定的會議視窗、系統聲音與麥克風，全部留在本機。」 |
| 2 權限 | 「先給三個權限」 | 副標「錄影、聲音與通知都只留在這台電腦。」；四列：螢幕錄製「錄下你指定的會議視窗」、麥克風「錄你自己的聲音」、通知「錄製告警與完成提醒」、自動化（Chrome）「只有要錄 Chrome 分頁時才需要」（選用）。每列：狀態點＋狀態字＋按鈕。狀態：已允許（點 `done`、字 `doneText`、鈕「已完成」停用）、需要重新開啟（點 `attention`、字 `attentionText`、鈕「重新開啟」底 `attention`）、尚未允許（點 `textDisabled`、鈕「允許」主鈕）、被拒（點 `recording`、字「被拒，要到系統設定打開」、鈕「打開系統設定」）、選用（鈕「允許」外框） |
| 3 存檔位置 | 「錄好的檔案放哪裡」 | 存檔資料夾＋「更改…」；meeting-harness 路徑（自動偵測，找不到才請使用者指定）；這一步才呼叫 `writeOnboardingDefaults` |
| 4 選單列空間 | 「確認看得到選單列圖示」 | 即時顯示「看得到」或「被擋住」；被擋住時說明「按住 ⌘ 拖動圖示」與「系統設定 › 選單列」，並提供「改成一律顯示錄製小窗」按鈕（寫 `hudMode = always`） |
| 5 試錄 | 「試錄 5 秒」 | 四組快捷鍵（唯讀）；「試錄 5 秒」按鈕；結果：未試／試錄中／兩路都有聲／某一路沒有聲音（附補救）。試錄放在暫存目錄、錄完直接刪除，不移垃圾桶（`spec.md` §6 第 139 條） |

狀態不只靠顏色：每列都有狀態字。VoiceOver：步驟條讀「第 2 步，共 5 步：權限」；Return＝主鈕；Esc 與 ⌘W 關閉＝全部略過（寫 `onboardingCompletedAt`，沿用設定視窗的實體鍵碼判斷）。「減少動態效果」：換步不做轉場動畫。

### 6.3 U5 設定視窗：A 7 個工具列分頁
寬 600 固定、高跟內容（不可縮放）。工具列分頁（標準 `NSToolbar`，標籤 12）：一般 `gearshape`、錄製 `record.circle`、回饋與通知 `bell.badge`、快捷鍵 `command`、錄完之後 `checkmark.circle`、權限 `lock.shield`、進階 `slider.horizontal.3`。**視窗標題跟著分頁變**（例「回饋與通知」，HIG：Update the window's title to reflect the currently visible pane）；記住上次分頁（`lastSettingsTab`）。控制項用標準 AppKit（勾選框、`NSSegmentedControl`、按鈕），只有視窗底色用 token（跟系統深淺色）。

| 分頁 | 內容 |
|---|---|
| 一般 | 預設存檔位置＋「更改…」、最近用過的位置、登入時自動開啟（＋「打開系統設定的登入項目」）、meeting-harness 路徑（唯讀） |
| 錄製 | 預設會議類型與與會者（唯讀，「要改請在終端機跑 meeting record」）、★ 快速開錄規則說明 |
| 回饋與通知 | 選單列計時「錄製中顯示 12:34」；錄製小窗「自動／一律顯示／不要」＋說明「自動：選單列圖示被瀏海擋住時才出現」；錄製小窗位置「右邊緣／左邊緣」；錄製中告警「用時效性通知（可穿過專注模式）」；會議偵測「偵測到會議 app 使用麥克風時問我要不要錄」；通知授權（狀態點＋狀態字＋「打開通知設定」） |
| 快捷鍵 | 四組 `r2HotKeys` 的 `display` 與動作（唯讀）；註冊失敗就地顯示「（註冊失敗，請改用選單）」 |
| 錄完之後 | 停止後自動跑前處理；`autoprep.log` 位置 |
| 權限 | 螢幕錄製、麥克風、通知、自動化（Chrome）：狀態點＋狀態字＋「打開系統設定」；「重新執行首次設定…」 |
| 進階 | `syncCompensation` 目前值（唯讀）＋「用 meeting sync 修改」；`record.log`、`autoprep.log` 位置；版本 |

### 6.4 U7 app 圖示：A 錄製點＋聲波
以下比例都相對於圓角方塊（tile）的邊長 `s`：

| 元素 | 大尺寸（> 32 px） | 小尺寸（≤ 32 px，聲波減成兩條） |
|---|---|---|
| tile | 底 `surface`、圓角 0.236·s、描邊 `#2E333E` 0.014·s | 同左，無描邊 |
| 紅點 | 中心 (0.375, 0.5)·s、半徑 0.153·s、`recording` | 中心 (0.375, 0.5)·s、半徑 0.181·s |
| 聲波 | 三條直線、`text`、圓頭、粗 0.049·s：x＝0.625／0.708／0.792，y 範圍 0.403–0.597／0.333–0.667／0.431–0.569 | 兩條、粗 0.111·s：x＝0.667／0.806，y 範圍 0.361–0.639／0.403–0.597 |

1024 母版的 tile 依 macOS 圖示格線放 824×824 置中。`.icns` 含 16、32、128、256、512 的 1×／2× 共 10 張。深色、tinted 變體與 Icon Composer 格式不在本輪（衍生工作）。

## 7. 與稿不同、需要使用者知道的地方

1. **膠囊白字對比**：稿的白字對 `#FF4D4F` 只有 3.27:1、對 `#8B7CF6` 3.33:1，13pt 不到 WCAG 一般文字的 4.5:1。預設做法：字放大到 14pt bold（大字門檻 3:1）、淺色與「增加對比」換深一階的底色。其他做法列在 `spec.md` §7 疑慮 52。
2. **有告警的形狀**：稿只換外框顏色，灰階分不出，補了角標（取自 Main 畫板）。
3. **F2 用系統 `NSAlert`**：不做稿上的深色卡片（`spec.md` §7 疑慮 53）。
4. **選單的醒目紅底列、⌃⌥⌘R 停止、「上一場：…」字面**：不做（§4）。
5. **HUD 完成卡片**：不做（§3）。
6. **選單列背景是半透明**：稿與本檔的對比都以稿上的選單列色（`menuBarDark`／`menuBarLight`）計算；實際桌布會讓底色變化，由實機設計審查確認（`spec.md` §4.47.11）。

## 8. 字型

預設**不打包**任何字型：app 只用系統字（§1.2 的對應），`Sources/` 不得出現 `JetBrains`、`Space Grotesk`、`Noto Sans`，`Resources/` 不得有 `.ttf`／`.otf`（`spec.md` §4.43.9）。要不要打包列為待決（`spec.md` §7 疑慮 54）。

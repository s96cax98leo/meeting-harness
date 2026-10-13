// Capture/WindowSource.swift —— 從 ScreenCaptureKit 取視窗與顯示器，轉成 Core 的 WindowCandidate
import CoreGraphics
import Foundation
@preconcurrency import ScreenCaptureKit

// onScreenWindowsOnly 必須給 false：視窗切到別的 Space 之後就不是 on-screen，
// 給 true 會讓它從清單消失（WWDC22 建單視窗 filter 時用的也是 false）。
func shareableContent() async throws -> SCShareableContent {
    try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
}

/// 同步讀單一視窗目前的大小（point，全域座標；與 SCWindow.frame 同一把尺）。讀不到（視窗已關）回 nil。
/// 只讀 kCGWindowBounds、不讀標題，不觸發 TCC；單一視窗約 0.16 ms（design §7.1，t6 第二輪缺陷 A）。
func cgWindowPointSize(_ windowID: UInt32) -> CGSize? {
    guard let idPtr = UnsafeRawPointer(bitPattern: UInt(windowID)) else { return nil }
    var values: [UnsafeRawPointer?] = [idPtr]
    guard let ids = CFArrayCreate(kCFAllocatorDefault, &values, 1, nil),
          let descs = CGWindowListCreateDescriptionFromArray(ids) as? [[String: Any]],
          let bounds = descs.first?[kCGWindowBounds as String],
          CFGetTypeID(bounds as CFTypeRef) == CFDictionaryGetTypeID(),
          let rect = CGRect(dictionaryRepresentation: bounds as! CFDictionary) else { return nil }
    return rect.size
}

func windowCandidate(_ w: SCWindow) -> WindowCandidate {
    WindowCandidate(windowID: w.windowID,
                    app: w.owningApplication?.applicationName ?? "?",
                    bundleID: w.owningApplication?.bundleIdentifier ?? "",
                    title: w.title ?? "",
                    layer: w.windowLayer,
                    frame: w.frame,
                    onScreen: w.isOnScreen,
                    active: w.isActive)
}

func windowCandidates(_ content: SCShareableContent) -> [WindowCandidate] {
    content.windows.map(windowCandidate)
}

func displayRects(_ content: SCShareableContent) -> [CGRect] {
    content.displays.map { $0.frame }
}

// SCDisplay 只給 point 尺寸，實際像素直接問 CGDisplayMode。Retina 下 point×2 才是像素。
func displayPixelSize(_ displayID: CGDirectDisplayID) -> (w: Int, h: Int) {
    if let mode = CGDisplayCopyDisplayMode(displayID) {
        return (mode.pixelWidth, mode.pixelHeight)
    }
    return (CGDisplayPixelsWide(displayID), CGDisplayPixelsHigh(displayID))
}

/// 視窗清單：查 Apple Events 狀態（askUserIfNeeded 只有 windows --ask-automation 為 true），
/// 有授權才讀 Chrome 分頁（只在記憶體），再交給 Core 算列。
struct WindowListing {
    let content: SCShareableContent
    let candidates: [WindowCandidate]
    let displays: [CGRect]
    let automation: AutomationStatus
    let chrome: [ChromeWindowInfo]

    var rows: [WindowListRow] {
        buildWindowRows(candidates: candidates, displays: displays, chrome: chrome, automation: automation)
    }
    var diagnosed: [DiagnosedWindow] {
        diagnoseWindows(candidates: candidates, displays: displays, chrome: chrome, automation: automation)
    }

    static func load(askAutomation: Bool) async throws -> WindowListing {
        let content = try await shareableContent()
        var automation = await chromeAutomationStatus(askUserIfNeeded: askAutomation)
        var chrome: [ChromeWindowInfo] = []
        if automation == .authorized {
            if let got = await queryChromeWindows() {
                chrome = got
            } else {
                automation = .error
            }
        }
        return WindowListing(content: content, candidates: windowCandidates(content),
                             displays: displayRects(content), automation: automation, chrome: chrome)
    }
}

/// 有任何 Chrome 列因 Apple Events 沒標記時要加的說明（spec §3.8.7、§3.7）。
func chromeAutomationHint(_ rows: [WindowListRow], include: Set<String>) -> Bool {
    rows.contains { $0.bundleID == chromeBundleID && include.contains($0.meetingCheck ?? "") }
}

let automationHintLine = "◦ Chrome 視窗沒有會議分頁標記（★）：會議分頁標記要允許 MeetingRecorder 以 Apple Events 讀 Chrome 分頁網址（選用，不授權也能錄）。"
    + "開啟方式：系統設定 › 隱私權與安全性 › 自動化 › MeetingRecorder › Google Chrome"

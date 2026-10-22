// Trigger/MenuBar+Support.swift —— menu bar 各檔共用的小工具：DarkroomColor 轉 NSColor、深色判斷、程序路徑、
// 停止／取消被拒與告警通知的固定句、「錄其他視窗」每列的資訊。
// meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出（private 改為模組內可見），行為不變。
import AppKit

// MARK: - 膠囊與通知的小工具

/// 告警類中 t 最大的一筆的訊息（menuBarAccessibilityLabel 的 alertText；§4.38.7）
func latestAlertMessage(_ st: RecordStatus?) -> String? {
    st?.warnings.filter { $0.kind.isAlert }.max(by: { $0.t < $1.t })?.message
}

/// DarkroomColor 的 "#RRGGBB" → sRGB NSColor（Core 不 import AppKit，只放字串；spec §3.20）。格式不對時用 labelColor。
func darkroomColor(_ hex: String) -> NSColor {
    let digits = hex.hasPrefix("#") ? String(hex.dropFirst()) : hex
    guard digits.count == 6, let v = UInt32(digits, radix: 16) else { return .labelColor }
    return NSColor(srgbRed: CGFloat((v >> 16) & 0xFF) / 255, green: CGFloat((v >> 8) & 0xFF) / 255,
                   blue: CGFloat(v & 0xFF) / 255, alpha: 1)
}

/// TypeToken.weight（"regular"／"semibold"／"bold"）→ NSFont.Weight
func darkroomFontWeight(_ w: String) -> NSFont.Weight {
    switch w {
    case "bold": return .bold
    case "semibold": return .semibold
    default: return .regular
    }
}

/// 選單列是否深色（含「增加對比」的深色外觀）
func isDarkAppearance(_ a: NSAppearance) -> Bool {
    let match = a.bestMatch(from: [.aqua, .darkAqua, .accessibilityHighContrastAqua, .accessibilityHighContrastDarkAqua])
    return match == .darkAqua || match == .accessibilityHighContrastDarkAqua
}

/// 程序的執行檔完整路徑（等同 ps -o comm=；stopTargetDecision 的 command）；取不到回 nil
func executablePath(_ pid: Int32) -> String? {
    var buf = [CChar](repeating: 0, count: Int(MAXPATHLEN) * 4)
    let n = proc_pidpath(pid, &buf, UInt32(buf.count))
    return n > 0 ? String(cString: buf) : nil
}

/// 停止被拒的說明（不含場次名）
func stopRefusalText(_ r: StopRefusal) -> String {
    switch r {
    case .noLock: return "找不到正在錄製的實例（record.lock 沒有被持有），沒有送出停止"
    case .noPid: return "找不到 record.pid，沒有送出停止"
    case .pidDead: return "record.pid 的程序已經不在，請執行 meeting record finish 收尾"
    case .pidMismatch: return "record.pid 與狀態檔的 pid 不一致，為了安全沒有送出停止"
    case .notRecorder: return "record.pid 指向的不是 MeetingRecorder，為了安全沒有送出停止"
    }
}

/// 背景收尾取消被拒的說明（spec §3.26 BackgroundCancelRefusal；不含場次名）
func backgroundCancelRefusalText(_ r: BackgroundCancelRefusal) -> String {
    switch r {
    case .recording: return "正在錄製下一場，不能取消上一場的收尾（停止這場後再取消）"
    case .noJob: return "找不到背景收尾中的場次，沒有送出取消"
    case .ownerGone: return "這場的收尾程序已經不在，請執行 meeting record finish 收尾"
    case .pidDead: return "這場收尾的程序已經不在，請執行 meeting record finish 收尾"
    case .notRecorder: return "這場收尾的 pid 指向的不是 MeetingRecorder，為了安全沒有送出取消"
    }
}

/// 告警通知的內文（spec §4.39.3）：依種類用固定句，不帶場次名、視窗標題或檔名
func alertNotificationBody(_ kind: WarningKind) -> String {
    switch kind {
    case .silenceSystem: return "系統聲音已連續 15 秒幾乎沒有聲音：檢查會議 app 的輸出與音量"
    case .silenceMic: return "麥克風已連續 15 秒幾乎沒有聲音：檢查麥克風是否被拔掉或靜音"
    case .black: return "會議視窗畫面已連續 5 秒全黑：確認會議畫面是否正常（錄製照常進行）"
    case .suspended: return "會議視窗的擷取已暫停超過 5 秒（多半是被最小化）：把視窗還原"
    case .diskLow: return "磁碟可用空間低於 2 GB，已自動停止並收尾"
    case .segmentWriteFailed: return "段落寫檔失敗，檔案保留；詳見 record.log"
    case .deviceChange, .audioFormatChange: return "錄製中有新狀況，打開選單看詳情"
    }
}

/// 「錄其他視窗」每一列帶的視窗資訊
final class WindowChoice: NSObject {
    let windowID: UInt32
    let bundleID: String
    let title: String
    init(windowID: UInt32, bundleID: String, title: String) {
        self.windowID = windowID
        self.bundleID = bundleID
        self.title = title
    }
}

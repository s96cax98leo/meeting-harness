// Core/MeetingDetect.swift —— 會議偵測提示的判斷（spec §3.20、§4.44.1；F3）。純函式：只看輸入裝置是否被使用、
// 前景 app 的 bundle ID（★ 清單＝WindowList.swift 的 meetingAppService）、record.lock 是否被持有、設定開關。
import Foundation

/// 一次「輸入裝置被使用」的期間（episode）。輸入停用時重設，同一個 episode 只提示一次。
struct MeetingEpisode: Equatable {
    var inputRunning = false
    var prompted = false
    var dismissed = false
}

enum MeetingPrompt: Equatable { case none, prompt }

/// inputRunning false → episode 重設、.none；enabled false 或 recordLockHeld → .none；
/// 前景不在 ★ 清單 → .none；同一 episode 已提示或被按「這場不用」→ .none；否則 .prompt 並記 prompted。
func meetingPromptDecision(_ ep: MeetingEpisode, inputRunning: Bool, frontmostBundleID: String?, recordLockHeld: Bool,
                           enabled: Bool) -> (MeetingEpisode, MeetingPrompt) {
    guard inputRunning else { return (MeetingEpisode(), .none) }
    var e = ep
    e.inputRunning = true
    guard enabled, !recordLockHeld else { return (e, .none) }
    guard let bid = frontmostBundleID, meetingAppService(bundleID: bid) != nil else { return (e, .none) }
    guard !e.prompted, !e.dismissed else { return (e, .none) }
    e.prompted = true
    return (e, .prompt)
}

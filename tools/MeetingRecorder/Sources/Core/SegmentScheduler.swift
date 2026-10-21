// Core/SegmentScheduler.swift —— 換段排程的純狀態機（spec §3.20、§4.36.1–§4.36.9、§4.36.11；design R3-D10，Q6）。
// 輸入事件（sample 到達、暫停、繼續、輸出裝置變更、writer 失敗、prev 收尾逾時、停止），輸出動作清單；
// 不碰 AVAssetWriter、不碰時鐘。PauseGate／pauseRoute／openReason／routeSample 照 R2 語意由這裡呼叫。
// 時間單位為秒（錄製時鐘，與 sample PTS 同一把尺）；段號從 1 起編。
import Foundation

enum SchedulerTrack: String, CaseIterable, Equatable { case video, system, mic }

enum SchedulerEvent: Equatable {
    case sample(track: SchedulerTrack, start: Double, end: Double, formatChanged: Bool)
    case pause, resume, outputDeviceChange, writerFailed(segment: Int), prevTimeout(segment: Int), stop
}

enum SchedulerAction: Equatable {
    case open(segment: Int, reason: SwitchReason, boundary: Double)
    case write(segment: Int, track: SchedulerTrack)
    case drop(track: SchedulerTrack)
    case finish(segment: Int)
    case cancel(segment: Int)
}

struct SegmentScheduler {
    let segmentSeconds: Double

    /// 目前段（新 sample 預設寫入的段）；writer 失敗、暫停、停止後為 nil。
    private(set) var current: Int?
    /// 剛換段、還收邊界前 sample 的舊段。
    private(set) var prev: Int?
    /// 暫停閘門（R2-D3a）。
    private(set) var gate = PauseGate()

    /// 已處理 sample 的最大 end（prevOnly、drop 不更新；spec §4.18.2）。
    private var maxEnd: Double?
    private var lastIndex = 0
    private var everOpened = false
    private var switchOnNextSample = false            // writer 失敗：以下一個 sample 開新段
    private var outputDeviceChangePending = false     // 輸出裝置變更：以下一個 sample 開新段（R3-D9）
    private var currentStart: Double?
    private var currentHasContent = false
    private var lastSegmentStart: Double?
    private var nextBoundary: Double?
    private var prevEnd: Double = 0
    private var prevSawPast: Set<SchedulerTrack> = []
    private var lastFormatChange: [SchedulerTrack: Double] = [:]
    private var stopped = false

    init(segmentSeconds: Double = 60) {
        self.segmentSeconds = segmentSeconds
    }

    mutating func handle(_ e: SchedulerEvent) -> [SchedulerAction] {
        switch e {
        case let .sample(track, start, end, formatChanged):
            return ingest(track: track, start: start, end: end, formatChanged: formatChanged)
        case .pause:
            return pauseCurrent()
        case .resume:
            if stopped { return [] }
            gate = resuming(gate)
            return []
        case .outputDeviceChange:
            // 暫停中（含已繼續、還沒開段）發生的變更由 resume 的換段吸收，不另開段
            if !stopped, !gate.paused, !gate.resumePending { outputDeviceChangePending = true }
            return []
        case let .writerFailed(segment):
            if segment == current {
                current = nil
                currentStart = nil
                currentHasContent = false
                nextBoundary = nil
                if !stopped { switchOnNextSample = true }
            }
            if segment == prev { prev = nil }
            return []
        case let .prevTimeout(segment):
            guard let p = prev, p == segment else { return [] }
            prev = nil
            return [.finish(segment: p)]
        case .stop:
            return stopAll()
        }
    }

    /// 一個 sample 進來：暫停閘門 → 更新 maxEnd → 必要時開新段 → 以 routeSample 分流寫進舊段／新段。
    private mutating func ingest(track: SchedulerTrack, start: Double, end: Double, formatChanged: Bool) -> [SchedulerAction] {
        if stopped { return [.drop(track: track)] }
        // 暫停閘門（spec §4.18.2）：在 maxEnd 更新之前判斷；prevOnly、drop 不更新 maxEnd、不自動開段
        let route = pauseRoute(gate, sampleStart: start)
        switch route {
        case .prevOnly:
            if let p = prev { return [.write(segment: p, track: track)] }     // 停止點 E 之前晚到的 sample 只進舊段
            return [.drop(track: track)]
        case .drop:
            return [.drop(track: track)]
        case .normal, .resumeBoundary:
            break
        }
        if end > (maxEnd ?? -Double.infinity) { maxEnd = end }

        var actions: [SchedulerAction] = []
        if let reason = openReason(route: route, hasCurrent: current != nil, everOpened: everOpened,
                                   switchOnNextSample: switchOnNextSample) {
            // 第一段：第一個 sample 的起點；writer 失敗後：下一個 sample 的起點，但不早於上一段起點；
            // 繼續：第一個起點 ≥ 停止點 E 的 sample。
            let b = lastSegmentStart.map { max($0, start) } ?? start
            actions += openSegment(boundary: b, reason: reason)
            if route == .resumeBoundary { gate = segmentOpened(gate) }
        } else if formatChanged, let cs = currentStart, formatSwitchAllowed(track, at: start), start > cs {
            // 格式變更提前換段：以第一個新格式 sample 的起點為邊界（design §7.5）
            actions += openSegment(boundary: start, reason: .formatChange)
        } else if outputDeviceChangePending, let cs = currentStart, start >= cs {
            // 輸出裝置變更：下一個 sample 提前換段（R3-D9）
            actions += openSegment(boundary: max(start, cs), reason: .outputDeviceChange)
        } else if let nb = nextBoundary, start >= nb || end > nb {
            // 定期換段：第一個越過邊界的 sample（起點 ≥ 邊界，或音訊緩衝跨過邊界）到達時切換
            actions += openSegment(boundary: nb, reason: .periodic)
        }

        if let p = prev, let c = current {
            let r = routeSample(start: start, end: end, boundary: prevEnd)
            if r == .old || r == .both { actions.append(.write(segment: p, track: track)) }
            if r == .new || r == .both { actions.append(.write(segment: c, track: track)); currentHasContent = true }
            if r != .old {
                prevSawPast.insert(track)
                if prevSawPast.count == SchedulerTrack.allCases.count {
                    prev = nil
                    actions.append(.finish(segment: p))     // write 在前、finish 在後（spec §4.36.2）
                }
            }
        } else if let c = current {
            actions.append(.write(segment: c, track: track))
            currentHasContent = true
        } else {
            actions.append(.drop(track: track))
        }
        return actions
    }

    /// 開新段：目前段（若有）轉成 prev（原本的 prev 先收掉）；回傳 finish（若有）與 open。
    private mutating func openSegment(boundary b: Double, reason: SwitchReason) -> [SchedulerAction] {
        var actions: [SchedulerAction] = []
        switchOnNextSample = false
        outputDeviceChangePending = false
        if let old = current {
            if let p = prev { actions.append(.finish(segment: p)) }
            prev = old
            prevEnd = b
            prevSawPast = []
        }
        lastIndex += 1
        everOpened = true
        current = lastIndex
        currentStart = b
        currentHasContent = false
        lastSegmentStart = b
        nextBoundary = b + segmentSeconds
        actions.append(.open(segment: lastIndex, reason: reason, boundary: b))
        return actions
    }

    /// 同一路 1 秒內再變一次格式時不再提前換段（避免 HFP 協商抖動時連續開檔，design §7.5）。
    private mutating func formatSwitchAllowed(_ track: SchedulerTrack, at t: Double) -> Bool {
        defer { lastFormatChange[track] = t }
        if let last = lastFormatChange[track], t - last < 1.0 { return false }
        return true
    }

    /// 暫停（R2-D3 第 1 步）：停止點 E＝maxEnd ?? 目前段起點；目前段有內容 → 轉成 prev（只收 E 之前晚到的 sample）；
    /// 沒有內容 → cancel（防禦性分支）。沒有目前段時不開段、不 cancel。
    private mutating func pauseCurrent() -> [SchedulerAction] {
        guard !stopped, !gate.paused else { return [] }
        gate = pausing(gate, maxEnd: maxEnd, segmentStart: currentStart)
        var actions: [SchedulerAction] = []
        if let c = current {
            if currentHasContent {
                if let p = prev { actions.append(.finish(segment: p)) }
                prev = c
                prevEnd = gate.cutPoint ?? currentStart ?? 0
                prevSawPast = []
            } else {
                actions.append(.cancel(segment: c))
            }
        }
        current = nil
        currentStart = nil
        currentHasContent = false
        nextBoundary = nil
        switchOnNextSample = false
        outputDeviceChangePending = false
        return actions
    }

    /// 停止：prev 與有內容的目前段 finish；目前段沒有內容 → cancel（防禦性分支）。之後任何 sample → drop。
    private mutating func stopAll() -> [SchedulerAction] {
        guard !stopped else { return [] }
        stopped = true
        var actions: [SchedulerAction] = []
        if let p = prev { actions.append(.finish(segment: p)) }
        if let c = current { actions.append(currentHasContent ? .finish(segment: c) : .cancel(segment: c)) }
        prev = nil
        current = nil
        currentStart = nil
        currentHasContent = false
        nextBoundary = nil
        return actions
    }
}

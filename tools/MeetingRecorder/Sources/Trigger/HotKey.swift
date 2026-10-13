// Trigger/HotKey.swift —— app 內全域快捷鍵（Carbon RegisterEventHotKey；spec §4.11.3、§4.20.5）
// 不用 NSEvent 的全域事件監看：那要「輔助使用」授權（req:255）。Carbon 的 hot key 不需要任何授權。
// R2 有四組（r2HotKeys）：每組以呼叫端給的 id 註冊；每個實例各裝一個 handler，
// handler 以 GetEventParameter 取出事件的 EventHotKeyID，不是自己的就回 eventNotHandledErr 讓下一個 handler 處理。
import Carbon
import Foundation

final class HotKey {
    /// 'MHRC'：四組共用同一個 signature，以 id 區分
    static let signature = OSType(0x4D48_5243)

    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private let hotKeyID: UInt32
    private let action: () -> Void

    /// keyCode 例 kVK_ANSI_R；modifiers 例 controlKey | optionKey | cmdKey；id 例 r2HotKeys 的 id（1–4，不得重複）。
    /// 註冊失敗（被別的 app 佔用）回 nil。
    init?(keyCode: Int, modifiers: Int, id: UInt32, action: @escaping () -> Void) {
        self.hotKeyID = id
        self.action = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let me = Unmanaged.passUnretained(self).toOpaque()
        let installed = InstallEventHandler(GetApplicationEventTarget(), { _, event, userData -> OSStatus in
            guard let event, let userData else { return OSStatus(eventNotHandledErr) }
            let hk = Unmanaged<HotKey>.fromOpaque(userData).takeUnretainedValue()
            var got = EventHotKeyID()
            let st = GetEventParameter(event, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID),
                                       nil, MemoryLayout<EventHotKeyID>.size, nil, &got)
            guard st == noErr, got.signature == HotKey.signature, got.id == hk.hotKeyID else {
                return OSStatus(eventNotHandledErr)
            }
            DispatchQueue.main.async { hk.action() }
            return noErr
        }, 1, &spec, me, &handler)
        guard installed == noErr else { return nil }
        let eid = EventHotKeyID(signature: HotKey.signature, id: id)
        let st = RegisterEventHotKey(UInt32(keyCode), UInt32(modifiers), eid, GetApplicationEventTarget(), 0, &ref)
        guard st == noErr else {
            if let handler { RemoveEventHandler(handler) }
            return nil
        }
    }

    deinit {
        if let ref { UnregisterEventHotKey(ref) }
        if let handler { RemoveEventHandler(handler) }
    }
}

/// r2HotKeys 的 key（"r"、"m"、"p"、"b"）對應的虛擬鍵碼；不認得的回 nil。
func hotKeyCode(_ key: String) -> Int? {
    switch key {
    case "r": return kVK_ANSI_R
    case "m": return kVK_ANSI_M
    case "p": return kVK_ANSI_P
    case "b": return kVK_ANSI_B
    default: return nil
    }
}

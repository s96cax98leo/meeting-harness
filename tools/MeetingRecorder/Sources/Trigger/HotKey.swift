// Trigger/HotKey.swift —— app 內全域快捷鍵（Carbon RegisterEventHotKey；spec §4.11.3）
// 不用 NSEvent 的全域事件監看：那要「輔助使用」授權（req:255）。Carbon 的 hot key 不需要任何授權。
import Carbon
import Foundation

final class HotKey {
    private var ref: EventHotKeyRef?
    private var handler: EventHandlerRef?
    private let action: () -> Void

    /// keyCode 例 kVK_ANSI_R；modifiers 例 controlKey | optionKey | cmdKey。註冊失敗（被別的 app 佔用）回 nil。
    init?(keyCode: Int, modifiers: Int, action: @escaping () -> Void) {
        self.action = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        let me = Unmanaged.passUnretained(self).toOpaque()
        let installed = InstallEventHandler(GetApplicationEventTarget(), { _, _, userData -> OSStatus in
            guard let userData else { return noErr }
            let hk = Unmanaged<HotKey>.fromOpaque(userData).takeUnretainedValue()
            DispatchQueue.main.async { hk.action() }
            return noErr
        }, 1, &spec, me, &handler)
        guard installed == noErr else { return nil }
        let id = EventHotKeyID(signature: OSType(0x4D48_5243), id: 1)    // 'MHRC'
        let st = RegisterEventHotKey(UInt32(keyCode), UInt32(modifiers), id, GetApplicationEventTarget(), 0, &ref)
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

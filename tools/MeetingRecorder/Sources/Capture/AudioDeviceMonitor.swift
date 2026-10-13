// Capture/AudioDeviceMonitor.swift —— 讀系統預設輸入／輸出裝置並監聽變更（design §7.3；spec §4.5.4、§4.9.4）
//
// 只「讀」與「監聽」：本檔與整個錄製器都不改使用者的預設裝置（不呼叫任何寫入 Core Audio 屬性的 API），
// 也不依賴虛擬音訊裝置或多重輸出裝置。
import CoreAudio
import Foundation

private func readProperty<T>(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector,
                             scope: AudioObjectPropertyScope = kAudioObjectPropertyScopeGlobal,
                             initial: T) -> T? {
    var addr = AudioObjectPropertyAddress(mSelector: selector, mScope: scope, mElement: kAudioObjectPropertyElementMain)
    var value = initial
    var size = UInt32(MemoryLayout<T>.size)
    let st = withUnsafeMutablePointer(to: &value) { p in
        AudioObjectGetPropertyData(object, &addr, 0, nil, &size, p)
    }
    return st == noErr ? value : nil
}

private func readString(_ object: AudioObjectID, _ selector: AudioObjectPropertySelector) -> String? {
    var addr = AudioObjectPropertyAddress(mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
                                          mElement: kAudioObjectPropertyElementMain)
    var ref: Unmanaged<CFString>?
    var size = UInt32(MemoryLayout<Unmanaged<CFString>?>.size)
    let st = withUnsafeMutablePointer(to: &ref) { p in
        AudioObjectGetPropertyData(object, &addr, 0, nil, &size, p)
    }
    guard st == noErr, let s = ref?.takeRetainedValue() else { return nil }
    return s as String
}

func transportName(_ t: UInt32) -> String {
    switch t {
    case kAudioDeviceTransportTypeBuiltIn: return "builtIn"
    case kAudioDeviceTransportTypeBluetooth: return "bluetooth"
    case kAudioDeviceTransportTypeBluetoothLE: return "bluetoothLE"
    case kAudioDeviceTransportTypeUSB: return "usb"
    case kAudioDeviceTransportTypeAggregate, kAudioDeviceTransportTypeAutoAggregate: return "aggregate"
    case kAudioDeviceTransportTypeVirtual: return "virtual"
    default: return "unknown"
    }
}

func defaultDeviceID(_ kind: DeviceKind) -> AudioDeviceID? {
    let sel = kind == .input ? kAudioHardwarePropertyDefaultInputDevice : kAudioHardwarePropertyDefaultOutputDevice
    guard let id = readProperty(AudioObjectID(kAudioObjectSystemObject), sel, initial: AudioDeviceID(0)), id != 0
    else { return nil }
    return id
}

func deviceInfo(_ id: AudioDeviceID) -> AudioDeviceInfo {
    AudioDeviceInfo(uid: readString(id, kAudioDevicePropertyDeviceUID) ?? "",
                    name: readString(id, kAudioObjectPropertyName) ?? "",
                    transport: transportName(readProperty(id, kAudioDevicePropertyTransportType, initial: UInt32(0)) ?? 0))
}

func currentDevices() -> AudioDevices {
    AudioDevices(input: defaultDeviceID(.input).map(deviceInfo), output: defaultDeviceID(.output).map(deviceInfo))
}

/// 監聽系統預設輸入／輸出裝置變更；回呼在指定佇列上執行。
final class AudioDeviceMonitor {
    private let queue: DispatchQueue
    private let onChange: (DeviceKind, AudioDeviceInfo?, AudioDeviceInfo?) -> Void
    private var last: [DeviceKind: AudioDeviceInfo?] = [:]
    private var blocks: [(AudioObjectPropertyAddress, AudioObjectPropertyListenerBlock)] = []

    init(queue: DispatchQueue, onChange: @escaping (DeviceKind, AudioDeviceInfo?, AudioDeviceInfo?) -> Void) {
        self.queue = queue
        self.onChange = onChange
    }

    func start(initial: AudioDevices) {
        last[.input] = initial.input
        last[.output] = initial.output
        for kind in [DeviceKind.input, .output] {
            var addr = AudioObjectPropertyAddress(
                mSelector: kind == .input ? kAudioHardwarePropertyDefaultInputDevice : kAudioHardwarePropertyDefaultOutputDevice,
                mScope: kAudioObjectPropertyScopeGlobal, mElement: kAudioObjectPropertyElementMain)
            let block: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
                guard let self else { return }
                let now = defaultDeviceID(kind).map(deviceInfo)
                let before = self.last[kind] ?? nil
                guard now != before else { return }
                self.last[kind] = now
                self.onChange(kind, before, now)
            }
            if AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &addr, queue, block) == noErr {
                blocks.append((addr, block))
            }
        }
    }

    func stop() {
        for (a, b) in blocks {
            var addr = a
            AudioObjectRemovePropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &addr, queue, b)
        }
        blocks.removeAll()
    }
}

// Trigger/MenuBar+SaveTo.swift —— menu bar 的「存到」子選單（spec §4.21.5）。
// meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出，行為不變。
import AppKit

extension MenuBarController {
    /// 「存到」目前的位置：menubar.prefs.json 的 root，沒有就用 record.defaults.json 的 root
    func effectiveRoot() -> String? {
        if let r = prefsStore.current.root, !r.isEmpty { return r }
        return RecordDefaults.load(defaultsURL)?.root
    }

    func rebuildSaveToMenu() {
        saveToMenu.removeAllItems()
        let current = effectiveRoot()
        var list: [String] = []
        if let current { list.append(current) }
        for r in prefsStore.current.recentRoots where !list.contains(where: { sameRoot($0, r) }) { list.append(r) }
        for path in list {
            let exists = isDirectoryPath(path)
            let shown = (path as NSString).abbreviatingWithTildeInPath
            let i = NSMenuItem(title: exists ? shown : "\(shown)（找不到）", action: #selector(chooseRoot(_:)),
                               keyEquivalent: "")
            i.target = self
            i.representedObject = path
            i.toolTip = path
            i.state = (current.map { sameRoot($0, path) } ?? false) ? .on : .off
            i.isEnabled = exists
            saveToMenu.addItem(i)
        }
        if !list.isEmpty { saveToMenu.addItem(.separator()) }
        let pick = NSMenuItem(title: "選擇資料夾…", action: #selector(pickRootFolder), keyEquivalent: "")
        pick.target = self
        saveToMenu.addItem(pick)
    }

    @objc func chooseRoot(_ sender: NSMenuItem) {
        guard let path = sender.representedObject as? String else { return }
        prefsStore.setRoot(path)
        refresh()
    }

    @objc func pickRootFolder() {
        guard let path = chooseFolder(startingAt: effectiveRoot()) else { return }
        prefsStore.setRoot(path)
        refresh()
    }
}

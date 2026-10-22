// Trigger/MenuBar+Session.swift —— 打開場次、上一場成品、設定、首次引導、錯誤詳情、結束選單
// （spec §4.23.4、§4.41.5、§4.43.5）。meeting-speed 結構重構（spec §4.13.1）：由 MenuBar.swift 原樣搬出，行為不變。
// R3（spec §4.43.5）：menubar.settings.json 的 onboardingCompletedAt 為 nil 時，啟動後顯示首次引導（Trigger/Onboarding.swift）；
//   設定視窗的「重新執行首次設定…」也從這裡開。
import AppKit

extension MenuBarController {
    /// 開首次引導；已開就帶到前面
    func showOnboarding() {
        let o = onboarding ?? OnboardingWindowController(home: home, prefsStore: prefsStore, failedHotKeyIDs: failedHotKeyIDs,
                                                         iconObscured: { [weak self] in self?.statusIconObscuredNow() })
        onboarding = o
        o.present()
    }

    @objc func showFailureDetail() {
        let c = failureDetail ?? FailureDetailController()
        failureDetail = c
        c.present(FailureDetailContent(detailText: model.detailText, sessionPath: status?.session ?? "",
                                       logPath: logURL.path))
    }

    @objc func openSession() {
        guard let s = status?.session, !s.isEmpty else { return }
        NSWorkspace.shared.open(nearestExistingDirectory(s))
    }

    /// 狀態檔是收尾完成的場次時優先（最新），否則用 menubar.prefs.json 的 lastSession（spec §4.23.4）
    func lastSessionPath() -> String? {
        if let st = status, st.phase == .done, !st.session.isEmpty { return st.session }
        if let s = prefsStore.current.lastSession, !s.isEmpty { return s }
        return nil
    }

    @objc func showLastSession() {
        guard let s = lastSessionPath() else { return }
        revealSessionProduct(s)
    }

    @objc func openPreferences() {
        let p = preferences ?? PreferencesWindowController(home: home, prefsStore: prefsStore,
                                                           failedHotKeyIDs: failedHotKeyIDs,
                                                           onRerunOnboarding: { [weak self] in self?.showOnboarding() })
        preferences = p
        p.present()
    }

    /// 只結束 menu bar 實例；錄製是另一個 process，不受影響。
    @objc func quitMenu() {
        NSApp.terminate(nil)
    }
}

import AppKit
import SwiftUI

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.setActivationPolicy(.regular)
        NSApp.activate(ignoringOtherApps: true)
    }
}

@main
@MainActor
struct StockResearcherApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @State private var store = AppStore()

    var body: some Scene {
        WindowGroup("股票研报", id: "main") {
            ContentView(store: store)
                .frame(minWidth: 980, minHeight: 680)
                .task {
                    await store.bootstrap()
                }
        }
        .defaultSize(width: 1280, height: 820)

        Settings {
            SettingsView(store: store)
        }
    }
}

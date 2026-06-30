import AppKit
import SwiftUI

struct ContentView: View {
    let store: AppStore
    @State private var showingNewReport = false

    var body: some View {
        NavigationSplitView {
            SidebarView(store: store)
        } detail: {
            Group {
                if let report = store.selectedReport {
                    ReportDetailView(store: store, report: report)
                } else {
                    ContentUnavailableView {
                        Label("暂无研报", systemImage: "doc.text.magnifyingglass")
                    } description: {
                        Text("创建第一份研报，或连接已有的研究服务。")
                    } actions: {
                        Button("新建研报") { showingNewReport = true }
                            .buttonStyle(.borderedProminent)
                    }
                }
            }
            .toolbar {
                ToolbarItemGroup {
                    Button {
                        showingNewReport = true
                    } label: {
                        Label("新建研报", systemImage: "plus")
                    }
                    .keyboardShortcut("n", modifiers: .command)

                    SettingsLink {
                        Label("设置", systemImage: "gearshape")
                    }
                }
            }
        }
        .navigationSplitViewStyle(.balanced)
        .sheet(isPresented: $showingNewReport) {
            NewReportView(store: store, isPresented: $showingNewReport)
        }
        .alert(
            "操作失败",
            isPresented: Binding(
                get: { store.errorMessage != nil },
                set: { if !$0 { store.errorMessage = nil } }
            )
        ) {
            Button("好", role: .cancel) { store.errorMessage = nil }
        } message: {
            Text(store.errorMessage ?? "未知错误")
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)) { _ in
            store.backend.stop()
        }
    }
}

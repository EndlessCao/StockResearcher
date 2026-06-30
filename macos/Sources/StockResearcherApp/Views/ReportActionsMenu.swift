import SwiftUI

struct ReportActionsMenu: View {
    let store: AppStore
    let report: Report
    @State private var showingRename = false
    @State private var showingDelete = false
    @State private var renameTitle = ""

    var body: some View {
        Menu {
            Button(report.isPinned ? "取消置顶" : "置顶") {
                Task { await store.togglePinned(report) }
            }
            Button("重命名…") {
                renameTitle = report.title
                showingRename = true
            }
            Divider()
            Button("删除…", role: .destructive) {
                showingDelete = true
            }
        } label: {
            Label("研报操作", systemImage: "ellipsis.circle")
        }
        .help("研报操作")
        .alert("重命名研报", isPresented: $showingRename) {
            TextField("研报标题", text: $renameTitle)
            Button("取消", role: .cancel) {}
            Button("保存") {
                Task { _ = await store.renameReport(report, title: renameTitle) }
            }
        }
        .confirmationDialog(
            "确定删除“\(report.title)”？",
            isPresented: $showingDelete
        ) {
            Button("删除研报", role: .destructive) {
                Task { await store.deleteReport(report) }
            }
            Button("取消", role: .cancel) {}
        } message: {
            Text("该操作无法撤销。")
        }
    }
}

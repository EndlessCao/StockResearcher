import SwiftUI

struct SidebarView: View {
  let store: AppStore
  @State private var query = ""
  @State private var reportToRename: Report?
  @State private var renameTitle = ""
  @State private var reportToDelete: Report?

  private var filteredReports: [Report] {
    let keyword = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !keyword.isEmpty else { return store.reports }
    return store.reports.filter {
      $0.title.localizedCaseInsensitiveContains(keyword)
        || ($0.stockCode?.localizedCaseInsensitiveContains(keyword) == true)
    }
  }

  var body: some View {
    List(
      selection: Binding(
        get: { store.selectedReportID },
        set: { store.selectedReportID = $0 }
      )
    ) {
      if !store.generationTasks.isEmpty {
        Section("生成队列") {
          ForEach(store.generationTasks) { task in
            HStack(spacing: 10) {
              ProgressView()
                .controlSize(.small)
                .frame(width: 16)
              VStack(alignment: .leading, spacing: 2) {
                Text(task.topic)
                  .lineLimit(1)
                Text(task.status == "pending" ? "等待生成" : "正在生成")
                  .font(.caption)
                  .foregroundStyle(.secondary)
              }
            }
            .contextMenu {
              Button("取消生成", role: .destructive) {
                Task { await store.cancelGeneration(task) }
              }
            }
          }
        }
      }

      Section("研报") {
        ForEach(filteredReports) { report in
          HStack(spacing: 10) {
            Image(systemName: report.isPinned ? "pin.fill" : "doc.text")
              .foregroundStyle(.secondary)
              .frame(width: 16)
            VStack(alignment: .leading, spacing: 2) {
              Text(report.title)
                .lineLimit(1)
              Text(report.stockCode ?? formattedDate(report.createdAt))
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
          }
          .tag(report.id)
          .contextMenu {
            Button(report.isPinned ? "取消置顶" : "置顶") {
              Task { await store.togglePinned(report) }
            }
            Button("重命名…") {
              renameTitle = report.title
              reportToRename = report
            }
            Divider()
            Button("删除…", role: .destructive) {
              reportToDelete = report
            }
          }
        }
      }
    }
    .listStyle(.sidebar)
    .searchable(text: $query, prompt: "搜索标题或代码")
    .navigationTitle("股票研究")
    .alert(
      "重命名研报",
      isPresented: Binding(
        get: { reportToRename != nil },
        set: { if !$0 { reportToRename = nil } }
      )
    ) {
      TextField("研报标题", text: $renameTitle)
      Button("取消", role: .cancel) { reportToRename = nil }
      Button("保存") {
        guard let report = reportToRename else { return }
        reportToRename = nil
        Task { _ = await store.renameReport(report, title: renameTitle) }
      }
    }
    .confirmationDialog(
      "确定删除“\(reportToDelete?.title ?? "")”？",
      isPresented: Binding(
        get: { reportToDelete != nil },
        set: { if !$0 { reportToDelete = nil } }
      )
    ) {
      Button("删除研报", role: .destructive) {
        guard let report = reportToDelete else { return }
        reportToDelete = nil
        Task { await store.deleteReport(report) }
      }
      Button("取消", role: .cancel) { reportToDelete = nil }
    } message: {
      Text("该操作会删除研报记录、对话和项目管理的研报文件，无法撤销。")
    }
    .safeAreaInset(edge: .bottom) {
      HStack(spacing: 8) {
        Circle()
          .fill(store.health == nil ? Color.red : Color.green)
          .frame(width: 8, height: 8)
        Text(store.health == nil ? "服务未连接" : "服务已连接")
          .font(.caption)
          .foregroundStyle(.secondary)
        Spacer()
        if store.isLoading {
          ProgressView().controlSize(.small)
        } else {
          Button {
            Task {
              _ = await store.refreshHealth(silent: true)
              await store.loadReports()
            }
          } label: {
            Image(systemName: "arrow.clockwise")
          }
          .buttonStyle(.plain)
          .help("刷新")
        }
      }
      .padding(.horizontal, 12)
      .padding(.vertical, 9)
      .background(.bar)
    }
  }

  private func formattedDate(_ value: String) -> String {
    guard let date = ISO8601DateFormatter().date(from: value) else { return value }
    return date.formatted(date: .abbreviated, time: .omitted)
  }
}

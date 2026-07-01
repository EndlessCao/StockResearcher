import AppKit
import SwiftUI

struct ReportDetailView: View {
  let store: AppStore
  let report: Report
  @State private var selectedTab = DetailTab.report

  enum DetailTab: String, CaseIterable, Identifiable {
    case report = "研报"
    case chat = "问答"
    var id: String { rawValue }
  }

  var body: some View {
    VStack(spacing: 0) {
      Picker("内容", selection: $selectedTab) {
        ForEach(DetailTab.allCases) { tab in
          Text(tab.rawValue).tag(tab)
        }
      }
      .pickerStyle(.segmented)
      .labelsHidden()
      .frame(width: 220)
      .padding(.vertical, 10)

      Divider()

      switch selectedTab {
      case .report:
        ReportReaderView(report: report)
      case .chat:
        ChatView(store: store, report: report)
      }
    }
    .navigationTitle(report.title)
    .toolbar {
      ToolbarItem {
        ReportActionsMenu(store: store, report: report)
      }
      ToolbarItem {
        Button {
          NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: report.path)])
        } label: {
          Label("在 Finder 中显示", systemImage: "folder")
        }
        .help("在 Finder 中显示 Markdown 文件")
      }
    }
  }
}

private struct ReportReaderView: View {
  let report: Report

  var body: some View {
    ScrollViewReader { proxy in
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          VStack(alignment: .leading, spacing: 8) {
            Text(report.title)
              .font(.largeTitle.weight(.semibold))
              .textSelection(.enabled)
            HStack(spacing: 12) {
              if let stockCode = report.stockCode {
                Label(stockCode, systemImage: "chart.line.uptrend.xyaxis")
              }
              if let cutoff = report.dataCutoff {
                Label("数据截至 \(cutoff)", systemImage: "calendar")
              }
              Label("\(report.citations.count) 个来源", systemImage: "link")
            }
            .font(.callout)
            .foregroundStyle(.secondary)
          }

          if !report.qaWarnings.isEmpty {
            DisclosureGroup("质量检查：\(report.qaWarnings.count) 条告警") {
              VStack(alignment: .leading, spacing: 6) {
                ForEach(report.qaWarnings, id: \.self) { warning in
                  Text("• \(warning)")
                }
              }
              .padding(.top, 8)
            }
            .padding(12)
            .background(.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 10))
          }

          MarkdownDocumentView(
            markdown: report.content,
            omittingTitle: report.title,
            onOpenAnchor: { identifier in
              withAnimation(.easeInOut(duration: 0.2)) {
                proxy.scrollTo(identifier, anchor: .top)
              }
            }
          )

          if !report.citations.isEmpty {
            Divider()
            DisclosureGroup("引用来源") {
              VStack(alignment: .leading, spacing: 10) {
                ForEach(report.citations) { citation in
                  if let rawURL = citation.url,
                    let url = URL(string: rawURL),
                    !rawURL.isEmpty
                  {
                    Link(destination: url) {
                      Label(citation.title ?? citation.id, systemImage: "link")
                    }
                  } else {
                    Label(citation.title ?? citation.id, systemImage: "doc")
                  }
                }
              }
              .padding(.top, 8)
            }
          }
        }
        .frame(maxWidth: 900, alignment: .leading)
        .padding(28)
        .frame(maxWidth: .infinity, alignment: .center)
      }
    }
  }
}

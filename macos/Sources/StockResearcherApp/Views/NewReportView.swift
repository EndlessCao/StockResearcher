import SwiftUI
import UniformTypeIdentifiers

struct NewReportView: View {
    let store: AppStore
    @Binding var isPresented: Bool

    @State private var topic = ""
    @State private var stockCode = ""
    @State private var mode = UserDefaults.standard.string(forKey: PreferenceKeys.defaultMode)
        ?? AppDefaults.defaultMode
    @State private var webSearch = UserDefaults.standard.bool(forKey: PreferenceKeys.defaultWebSearch)
    @State private var maxResults = UserDefaults.standard.integer(forKey: PreferenceKeys.defaultMaxResults)
    @State private var useDataCutoff = false
    @State private var dataCutoff = Date()
    @State private var sources: [String] = []
    @State private var showingImporter = false

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section("研究目标") {
                    TextField("例如：分析英伟达未来三年的增长潜力", text: $topic, axis: .vertical)
                        .lineLimit(2...4)
                    TextField("证券代码（可选）", text: $stockCode)
                }

                Section("生成策略") {
                    Picker("研报深度", selection: $mode) {
                        Text("快速").tag("quick")
                        Text("标准").tag("standard")
                        Text("深度").tag("deep")
                    }
                    Toggle("启用网络检索", isOn: $webSearch)
                    if webSearch {
                        Stepper("最多 \(maxResults) 条检索结果", value: $maxResults, in: 0...20)
                    }
                    Toggle("指定数据截止日", isOn: $useDataCutoff)
                    if useDataCutoff {
                        DatePicker("数据截止日", selection: $dataCutoff, displayedComponents: .date)
                    }
                }

                Section("本地资料") {
                    if sources.isEmpty {
                        Text("未选择文件或目录")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(sources, id: \.self) { source in
                            HStack {
                                Text(URL(fileURLWithPath: source).lastPathComponent)
                                Spacer()
                                Button {
                                    sources.removeAll { $0 == source }
                                } label: {
                                    Image(systemName: "xmark.circle.fill")
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                    Button("添加文件或目录…") { showingImporter = true }
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                if store.isGenerating {
                    ProgressView()
                    Text("正在生成，深度研报可能需要数分钟…")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button("取消") { isPresented = false }
                    .keyboardShortcut(.cancelAction)
                    .disabled(store.isGenerating)
                Button("生成研报") { generate() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(topic.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || store.isGenerating)
            }
            .padding(16)
        }
        .frame(width: 620, height: 650)
        .fileImporter(
            isPresented: $showingImporter,
            allowedContentTypes: [.item],
            allowsMultipleSelection: true
        ) { result in
            if case let .success(urls) = result {
                for url in urls where !sources.contains(url.path) {
                    sources.append(url.path)
                }
            }
        }
    }

    private func generate() {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"

        let request = CreateReportRequest(
            topic: topic.trimmingCharacters(in: .whitespacesAndNewlines),
            sources: sources,
            webSearch: webSearch,
            maxSearchResults: maxResults,
            mode: mode,
            stockCode: stockCode.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            dataCutoff: useDataCutoff ? formatter.string(from: dataCutoff) : nil,
            sourceTypes: AppDefaults.selectedSourceTypes
        )
        Task {
            if await store.createReport(request) {
                isPresented = false
            }
        }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}

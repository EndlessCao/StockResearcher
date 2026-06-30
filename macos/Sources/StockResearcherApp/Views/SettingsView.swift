import SwiftUI

struct SettingsView: View {
    let store: AppStore

    @AppStorage(PreferenceKeys.apiBaseURL) private var apiBaseURL = AppDefaults.apiBaseURL
    @AppStorage(PreferenceKeys.backendDirectory) private var backendDirectory = AppDefaults.backendDirectory
    @AppStorage(PreferenceKeys.autoStartBackend) private var autoStartBackend = true
    @AppStorage(PreferenceKeys.defaultMode) private var defaultMode = AppDefaults.defaultMode
    @AppStorage(PreferenceKeys.defaultWebSearch) private var defaultWebSearch = true
    @AppStorage(PreferenceKeys.defaultMaxResults) private var defaultMaxResults = 6
    @AppStorage(PreferenceKeys.sourceAnnualReport) private var sourceAnnualReport = true
    @AppStorage(PreferenceKeys.sourceQuarterlyReport) private var sourceQuarterlyReport = true
    @AppStorage(PreferenceKeys.sourceAnnouncement) private var sourceAnnouncement = true
    @AppStorage(PreferenceKeys.sourceResearch) private var sourceResearch = true

    var body: some View {
        TabView {
            Form {
                Section("研究服务") {
                    TextField("API 地址", text: $apiBaseURL)
                    TextField("项目目录", text: $backendDirectory)
                    Toggle("启动应用时自动启动本地服务", isOn: $autoStartBackend)
                }

                Section {
                    HStack {
                        Circle()
                            .fill(store.health == nil ? Color.red : Color.green)
                            .frame(width: 8, height: 8)
                        Text(store.health == nil ? "未连接" : "已连接 · v\(store.health?.version ?? "")")
                        Spacer()
                        if store.backend.isManagedProcessRunning {
                            Button("停止本地服务") {
                                store.backend.stop()
                                store.health = nil
                            }
                        }
                        Button("应用并重连") {
                            Task { await store.restartConnection() }
                        }
                        .buttonStyle(.borderedProminent)
                    }
                } footer: {
                    Text("模型、搜索和向量服务密钥继续从项目目录下的 .env 读取。")
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("服务", systemImage: "server.rack") }

            Form {
                Picker("默认研报深度", selection: $defaultMode) {
                    Text("快速").tag("quick")
                    Text("标准").tag("standard")
                    Text("深度").tag("deep")
                }
                Toggle("默认启用网络检索", isOn: $defaultWebSearch)
                Stepper("默认最多 \(defaultMaxResults) 条检索结果", value: $defaultMaxResults, in: 0...20)

                Section("允许的资料类型") {
                    Toggle("年报", isOn: $sourceAnnualReport)
                    Toggle("季报", isOn: $sourceQuarterlyReport)
                    Toggle("公告", isOn: $sourceAnnouncement)
                    Toggle("研究资料", isOn: $sourceResearch)
                }
            }
            .formStyle(.grouped)
            .tabItem { Label("研报", systemImage: "doc.text") }

            EnvironmentSettingsView(store: store)
                .tabItem { Label("模型与数据", systemImage: "key.horizontal") }
        }
        .frame(width: 700, height: 640)
    }
}

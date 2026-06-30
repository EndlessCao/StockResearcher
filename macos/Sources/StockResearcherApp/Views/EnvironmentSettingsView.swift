import SwiftUI

struct EnvironmentSettingsView: View {
    let store: AppStore
    @State private var values: [String: String] = [:]

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section("大模型") {
                    SecureField("OpenAI API Key", text: binding("OPENAI_API_KEY"))
                    TextField("OpenAI Base URL", text: binding("OPENAI_BASE_URL"))
                    TextField("OpenAI Model", text: binding("OPENAI_MODEL"))
                    TextField("LiteLLM Model", text: binding("LITELLM_MODEL"))
                }

                Section("网络检索") {
                    SecureField("Tavily API Keys", text: binding("TAVILY_API_KEYS"))
                    SecureField("Brave API Keys", text: binding("BRAVE_API_KEYS"))
                    SecureField("SerpAPI API Keys", text: binding("SERPAPI_API_KEYS"))
                }

                Section("向量与重排") {
                    SecureField("Embedding API Key", text: binding("EMBEDDING_API_KEY"))
                    TextField("Embedding Base URL", text: binding("EMBEDDING_BASE_URL"))
                    TextField("Embedding Model", text: binding("EMBEDDING_MODEL"))
                    SecureField("Rerank API Key", text: binding("RERANK_API_KEY"))
                    TextField("Rerank Base URL", text: binding("RERANK_BASE_URL"))
                    TextField("Rerank Model", text: binding("RERANK_MODEL"))
                }

                Section("行情与扩展") {
                    SecureField("Alpaca API Key", text: binding("ALPACA_API_KEY"))
                    SecureField("Alpaca Secret Key", text: binding("ALPACA_SECRET_KEY"))
                    TextField("Alpaca Data Base URL", text: binding("ALPACA_DATA_BASE_URL"))
                    TextField("Alpaca Data Feed", text: binding("ALPACA_DATA_FEED"))
                    SecureField("Social Sentiment API Key", text: binding("SOCIAL_SENTIMENT_API_KEY"))
                    TextField("Social Sentiment API URL", text: binding("SOCIAL_SENTIMENT_API_URL"))
                    TextField("日志级别（INFO=DEBUG 开启详细日志）", text: binding("INFO"))
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack(spacing: 12) {
                if store.isLoadingConfiguration || store.isSavingConfiguration {
                    ProgressView().controlSize(.small)
                }
                VStack(alignment: .leading, spacing: 2) {
                    Text(store.environmentConfig?.path ?? "项目 .env")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                    if let message = store.configurationMessage {
                        Text(message)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer()
                Button("重新载入") {
                    Task { await load() }
                }
                .disabled(store.isLoadingConfiguration || store.isSavingConfiguration)
                Button("保存配置") {
                    Task { _ = await store.saveEnvironmentConfiguration(values) }
                }
                .buttonStyle(.borderedProminent)
                .disabled(values.isEmpty || store.isLoadingConfiguration || store.isSavingConfiguration)
            }
            .padding(14)
        }
        .task {
            if values.isEmpty { await load() }
        }
    }

    private func binding(_ key: String) -> Binding<String> {
        Binding(
            get: { values[key, default: ""] },
            set: { values[key] = $0 }
        )
    }

    private func load() async {
        if await store.loadEnvironmentConfiguration() {
            values = store.environmentConfig?.values ?? [:]
        }
    }
}

import SwiftUI

struct ChatView: View {
    let store: AppStore
    let report: Report
    @State private var question = ""

    private var messages: [ChatMessage] {
        store.chatMessages[report.id, default: []]
    }

    private var isAnswering: Bool {
        store.answeringReportIDs.contains(report.id)
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 14) {
                        if messages.isEmpty {
                            ContentUnavailableView {
                                Label("基于研报提问", systemImage: "bubble.left.and.text.bubble.right")
                            } description: {
                                Text("回答会结合研报正文、原始资料和可用的网络检索。")
                            }
                            .padding(.top, 100)
                        }

                        ForEach(messages) { message in
                            ChatBubble(message: message)
                                .id(message.id)
                        }

                        if isAnswering {
                            HStack {
                                ProgressView()
                                Text("正在分析研报与证据…")
                                    .foregroundStyle(.secondary)
                                Spacer()
                            }
                            .id("answering")
                        }
                    }
                    .padding(20)
                }
                .onChange(of: messages.count) {
                    if let id = messages.last?.id {
                        withAnimation { proxy.scrollTo(id, anchor: .bottom) }
                    }
                }
                .onChange(of: isAnswering) {
                    if isAnswering {
                        withAnimation { proxy.scrollTo("answering", anchor: .bottom) }
                    }
                }
            }

            Divider()

            HStack(alignment: .bottom, spacing: 10) {
                TextField("询问核心逻辑、风险或证据…", text: $question, axis: .vertical)
                    .lineLimit(1...5)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit(send)
                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .buttonStyle(.plain)
                .disabled(question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isAnswering)
                .keyboardShortcut(.return, modifiers: .command)
            }
            .padding(14)
        }
    }

    private func send() {
        let submitted = question
        question = ""
        Task { await store.ask(reportID: report.id, question: submitted) }
    }
}

private struct ChatBubble: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.role == .user { Spacer(minLength: 100) }
            VStack(alignment: .leading, spacing: 8) {
                Text(message.role == .user ? "你" : "研究助手")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Text(message.content)
                    .textSelection(.enabled)
                if !message.citations.isEmpty {
                    Text("依据：\(message.citations.map(\.id).joined(separator: "、"))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            .padding(12)
            .background(
                message.role == .user ? Color.accentColor.opacity(0.14) : Color.secondary.opacity(0.10),
                in: RoundedRectangle(cornerRadius: 12)
            )
            if message.role == .assistant { Spacer(minLength: 100) }
        }
    }
}

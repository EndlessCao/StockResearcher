import Foundation

struct HealthStatus: Codable, Sendable {
    let status: String
    let version: String
    let llmConfigured: Bool
    let searchProvider: String
    let vectorDatabase: String
    let embeddingConfigured: Bool
    let rerankConfigured: Bool
}

struct Citation: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let title: String?
    let url: String?
    let sourceType: String?
    let reliability: String?

    init(
        id: String,
        title: String? = nil,
        url: String? = nil,
        sourceType: String? = nil,
        reliability: String? = nil
    ) {
        self.id = id
        self.title = title
        self.url = url
        self.sourceType = sourceType
        self.reliability = reliability
    }
}

struct Report: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let taskId: String
    let title: String
    let content: String
    let path: String
    let citations: [Citation]
    let qaWarnings: [String]
    let stockCode: String?
    let dataCutoff: String?
    let sourceTypes: [String]
    let createdAt: String
    let isPinned: Bool
}

struct UpdateReportRequest: Codable, Sendable {
    let title: String?
    let isPinned: Bool?
}

struct CreateReportRequest: Codable, Sendable {
    let topic: String
    let sources: [String]
    let webSearch: Bool
    let maxSearchResults: Int
    let mode: String
    let stockCode: String?
    let dataCutoff: String?
    let sourceTypes: [String]
}

struct ChatRequest: Codable, Sendable {
    let question: String
}

struct ChatResponse: Codable, Sendable {
    let answer: String
    let citations: [Citation]
}

struct ChatMessage: Identifiable, Hashable, Sendable {
    enum Role: Sendable {
        case user
        case assistant
    }

    let id: UUID
    let role: Role
    let content: String
    let citations: [Citation]

    init(role: Role, content: String, citations: [Citation] = []) {
        self.id = UUID()
        self.role = role
        self.content = content
        self.citations = citations
    }
}

struct APIErrorPayload: Codable, Sendable {
    let detail: String
}

struct EnvironmentConfig: Codable, Sendable {
    let path: String
    let values: [String: String]
}

struct EnvironmentConfigUpdate: Codable, Sendable {
    let values: [String: String]
}

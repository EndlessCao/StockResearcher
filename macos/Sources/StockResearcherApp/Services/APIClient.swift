import Foundation

enum APIClientError: LocalizedError {
  case invalidBaseURL
  case invalidResponse
  case server(status: Int, message: String)

  var errorDescription: String? {
    switch self {
    case .invalidBaseURL:
      return "服务地址无效，请在设置中检查 API 地址。"
    case .invalidResponse:
      return "服务返回了无法识别的响应。"
    case .server(let status, let message):
      return "服务错误（\(status)）：\(message)"
    }
  }
}

struct APIClient: Sendable {
  private let baseURL: URL
  private let session: URLSession

  init(baseURLString: String) throws {
    guard let url = URL(string: baseURLString),
      let scheme = url.scheme,
      ["http", "https"].contains(scheme),
      url.host != nil
    else {
      throw APIClientError.invalidBaseURL
    }
    self.baseURL = url

    let configuration = URLSessionConfiguration.default
    configuration.timeoutIntervalForRequest = 1_800
    configuration.timeoutIntervalForResource = 1_800
    self.session = URLSession(configuration: configuration)
  }

  func health() async throws -> HealthStatus {
    try await send(path: "health", method: "GET", body: Optional<String>.none)
  }

  func listReports() async throws -> [Report] {
    try await send(path: "api/v1/reports?limit=100", method: "GET", body: Optional<String>.none)
  }

  func createReport(_ request: CreateReportRequest) async throws -> Report {
    try await send(path: "api/v1/reports", method: "POST", body: request)
  }

  func submitReportTask(_ request: CreateReportRequest) async throws -> ResearchTask {
    try await send(path: "api/v1/tasks", method: "POST", body: request)
  }

  func listActiveTasks() async throws -> [ResearchTask] {
    try await send(
      path: "api/v1/tasks?limit=100&active_only=true",
      method: "GET",
      body: Optional<String>.none
    )
  }

  func getTask(taskID: String) async throws -> ResearchTask {
    try await send(
      path: "api/v1/tasks/\(escapedPathComponent(taskID))",
      method: "GET",
      body: Optional<String>.none
    )
  }

  func cancelTask(taskID: String) async throws -> ResearchTask {
    try await send(
      path: "api/v1/tasks/\(escapedPathComponent(taskID))/cancel",
      method: "POST",
      body: Optional<String>.none
    )
  }

  func updateReport(
    reportID: String, title: String? = nil, isPinned: Bool? = nil
  ) async throws -> Report {
    let escapedID = escapedPathComponent(reportID)
    return try await send(
      path: "api/v1/reports/\(escapedID)",
      method: "PATCH",
      body: UpdateReportRequest(title: title, isPinned: isPinned)
    )
  }

  func deleteReport(reportID: String) async throws {
    let escapedID = escapedPathComponent(reportID)
    try await sendWithoutResponse(path: "api/v1/reports/\(escapedID)", method: "DELETE")
  }

  func chat(reportID: String, question: String) async throws -> ChatResponse {
    let escapedID = escapedPathComponent(reportID)
    return try await send(
      path: "api/v1/reports/\(escapedID)/chat",
      method: "POST",
      body: ChatRequest(question: question)
    )
  }

  func conversationMessages(reportID: String, limit: Int = 200) async throws
    -> [ConversationMessage]
  {
    let escapedID = escapedPathComponent(reportID)
    return try await send(
      path: "api/v1/reports/\(escapedID)/messages?limit=\(limit)",
      method: "GET",
      body: Optional<String>.none
    )
  }

  func loadEnvironmentConfig() async throws -> EnvironmentConfig {
    try await send(
      path: "api/v1/config/environment",
      method: "GET",
      body: Optional<String>.none
    )
  }

  func saveEnvironmentConfig(_ values: [String: String]) async throws -> EnvironmentConfig {
    try await send(
      path: "api/v1/config/environment",
      method: "PUT",
      body: EnvironmentConfigUpdate(values: values)
    )
  }

  private func send<Response: Decodable & Sendable, Body: Encodable & Sendable>(
    path: String,
    method: String,
    body: Body?
  ) async throws -> Response {
    guard let url = URL(string: path, relativeTo: baseURL.appendingPathComponent("/")) else {
      throw APIClientError.invalidBaseURL
    }

    var request = URLRequest(url: url)
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    if let body {
      let encoder = JSONEncoder()
      encoder.keyEncodingStrategy = .convertToSnakeCase
      request.httpBody = try encoder.encode(body)
      request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }

    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIClientError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
      let decoder = JSONDecoder()
      let payload = try? decoder.decode(APIErrorPayload.self, from: data)
      let fallback = String(data: data, encoding: .utf8) ?? "未知错误"
      throw APIClientError.server(
        status: httpResponse.statusCode, message: payload?.detail ?? fallback)
    }

    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(Response.self, from: data)
  }

  private func sendWithoutResponse(path: String, method: String) async throws {
    guard let url = URL(string: path, relativeTo: baseURL.appendingPathComponent("/")) else {
      throw APIClientError.invalidBaseURL
    }
    var request = URLRequest(url: url)
    request.httpMethod = method
    request.setValue("application/json", forHTTPHeaderField: "Accept")
    let (data, response) = try await session.data(for: request)
    guard let httpResponse = response as? HTTPURLResponse else {
      throw APIClientError.invalidResponse
    }
    guard (200..<300).contains(httpResponse.statusCode) else {
      let payload = try? JSONDecoder().decode(APIErrorPayload.self, from: data)
      let fallback = String(data: data, encoding: .utf8) ?? "未知错误"
      throw APIClientError.server(
        status: httpResponse.statusCode,
        message: payload?.detail ?? fallback
      )
    }
  }

  private func escapedPathComponent(_ value: String) -> String {
    value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
  }
}

import Foundation
import Testing

@testable import StockResearcher

struct APIModelsTests {
  @Test
  func defaultAppDirectoryLivesUnderUserHome() {
    let expected = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent(".stock_researcher", isDirectory: true)
      .path
    #expect(AppDefaults.backendDirectory == expected)
  }

  @Test
  func decodesQueuedResearchTask() throws {
    let payload = """
      {"id":"task_1","topic":"测试生成","status":"running","error":null,"report_id":null,"created_at":"2026-06-30T00:00:00+00:00","completed_at":null}
      """
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase

    let task = try decoder.decode(ResearchTask.self, from: Data(payload.utf8))

    #expect(task.isActive)
    #expect(task.topic == "测试生成")
  }

  @Test
  func decodesPersistedConversationMessage() throws {
    let payload = """
      {"id":12,"role":"assistant","content":"历史回答","citations":[{"id":"S1"}],"created_at":"2026-07-01T00:00:00+00:00"}
      """
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase

    let persisted = try decoder.decode(ConversationMessage.self, from: Data(payload.utf8))
    let message = ChatMessage(conversation: persisted)

    #expect(persisted.id == 12)
    #expect(message.role == .assistant)
    #expect(message.content == "历史回答")
    #expect(message.citations.first?.id == "S1")
  }

  @Test
  func parsesBlockMarkdownForReportRendering() throws {
    let markdown = """
      # 标题

      > **核心判断**：增长可持续。

      - 风险一
      - 风险二

      <a id="chapter-table"></a>

      | 指标 | 2025 |
      | --- | ---: |
      | 收入 | 100 |
      """

    let blocks = MarkdownParser.parse(markdown)

    #expect(blocks.contains(.heading(level: 1, text: "标题")))
    #expect(blocks.contains(.blockquote("**核心判断**：增长可持续。")))
    #expect(blocks.contains(.unorderedList(["风险一", "风险二"])))
    #expect(blocks.contains(.anchor("chapter-table")))
    #expect(blocks.contains(.table(headers: ["指标", "2025"], rows: [["收入", "100"]])))
  }

  @Test
  func decodesBackendReportPayload() throws {
    let payload = """
      {
        "id": "report_1",
        "task_id": "task_1",
        "title": "示例研报",
        "content": "# 示例",
        "path": "/tmp/report.md",
        "citations": [{"id": "S1", "title": "公告", "url": "https://example.com", "source_type": "announcement", "reliability": "high"}],
        "qa_warnings": [],
        "stock_code": "NVDA",
        "data_cutoff": "2026-06-30",
        "source_types": ["announcement"],
        "created_at": "2026-06-30T00:00:00+00:00",
        "is_pinned": true
      }
      """
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase

    let report = try decoder.decode(Report.self, from: Data(payload.utf8))

    #expect(report.taskId == "task_1")
    #expect(report.citations.first?.sourceType == "announcement")
    #expect(report.stockCode == "NVDA")
    #expect(report.isPinned == true)
  }

  @Test
  func encodesCreateRequestForFastAPI() throws {
    let request = CreateReportRequest(
      topic: "测试主题",
      sources: [],
      webSearch: true,
      maxSearchResults: 6,
      mode: "standard",
      stockCode: nil,
      dataCutoff: nil,
      sourceTypes: ["annual_report"]
    )
    let encoder = JSONEncoder()
    encoder.keyEncodingStrategy = .convertToSnakeCase
    let object = try #require(
      JSONSerialization.jsonObject(with: encoder.encode(request)) as? [String: Any]
    )

    #expect(object["web_search"] as? Bool == true)
    #expect(object["max_search_results"] as? Int == 6)
    #expect(object["source_types"] as? [String] == ["annual_report"])
  }
}

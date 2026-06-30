import Foundation
import Testing
@testable import StockResearcher

struct APIModelsTests {
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

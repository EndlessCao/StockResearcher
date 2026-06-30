from collections import Counter
from pathlib import Path

from research_agent.config import Settings
from research_agent.models import ReportChapter, SourceDocument
from research_agent.retrieval import ChromaHybridRetriever


def _source(
    source_id: str,
    title: str,
    content: str,
    document_type: str,
    published_at: str,
) -> SourceDocument:
    return SourceDocument(
        id=source_id,
        source_type="pdf",
        title=title,
        url=f"https://example.com/{source_id}",
        content=content,
        metadata={
            "document_type": document_type,
            "published_at": published_at,
            "source_reliability": "external",
        },
    )


def test_chapter_questions_include_financial_metrics_and_counter_view() -> None:
    chapter = ReportChapter(title="财务表现", focus="分析盈利质量")
    questions = ChromaHybridRetriever.chapter_questions("贵州茅台", chapter)
    assert len(questions) == 4
    assert "营业收入和归母净利润" in questions[0]
    assert "毛利率和经营现金流" in questions[1]
    assert "反方观点" in questions[-1]


def test_hybrid_retrieval_filters_metadata_and_limits_document_chunks(tmp_path: Path) -> None:
    config = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        openai_api_key="",
        embedding_api_key="",
        rerank_api_key="",
        chunk_size=120,
        chunk_overlap=10,
        retrieval_candidates=30,
        retrieval_evidence_blocks=6,
        retrieval_max_chunks_per_document=2,
    )
    retriever = ChromaHybridRetriever(config)
    repeated_financials = "。".join(
        [
            "贵州茅台2023年营业收入增长，归母净利润提升，毛利率保持稳定，经营现金流改善"
            for _ in range(16)
        ]
    )
    sources = [
        _source("annual", "贵州茅台2023年年度报告", repeated_financials, "annual_report", "2024-03-31"),
        _source(
            "research",
            "贵州茅台盈利质量研究",
            "收入增长放缓与渠道库存相关。反方观点认为需求承压和批价波动可能影响现金流。" * 8,
            "research",
            "2025-05-01",
        ),
        _source("kline", "贵州茅台日线行情", "开盘价收盘价成交量K线" * 20, "market_data", "2025-05-01"),
        _source("future", "贵州茅台未来年度报告", "未来数据不应进入报告", "annual_report", "2027-01-01"),
    ]
    retriever.index_documents(
        "task-filter",
        sources,
        "600519",
        {source.id: f"S{index}" for index, source in enumerate(sources, 1)},
    )
    chapter = ReportChapter(
        title="财务表现",
        focus="分析收入、利润率、现金流、放缓原因和风险",
        retrieval_questions=ChromaHybridRetriever.chapter_questions("贵州茅台", ReportChapter(title="财务表现", focus="")),
    )
    packet, diagnostics = retriever.retrieve_chapter(
        "task-filter",
        chapter,
        "600519",
        "2025-12-31",
        ["annual_report", "quarterly_report", "announcement", "research"],
    )

    source_counts = Counter(item["source_id"] for item in diagnostics)
    assert "营业收入" in packet
    assert "反方观点" in packet
    assert "日线行情" not in packet
    assert "未来数据" not in packet
    assert max(source_counts.values()) <= 2
    assert len(diagnostics) <= 6


def test_metadata_where_contains_stock_date_and_source_filters() -> None:
    where = ChromaHybridRetriever._where(
        "task-1", "600519", 123456.0, ["annual_report", "research"]
    )
    assert {"stock_code": {"$eq": "600519"}} in where["$and"]
    assert {"published_ts": {"$lte": 123456.0}} in where["$and"]
    assert {"source_type": {"$in": ["annual_report", "research"]}} in where["$and"]

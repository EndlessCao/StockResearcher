from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.api import app
from research_agent.config import Settings
from research_agent.models import ReportRequest
from research_agent.orchestrator import ResearchOrchestrator
from research_agent.report_writer import ProfessionalReportWriter


def test_local_report_and_chat_without_external_services(tmp_path: Path) -> None:
    source = tmp_path / "evidence.md"
    source.write_text(
        "某公司2025年营收增长20%。主要风险是客户集中度较高。", encoding="utf-8"
    )
    config = Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    agent = ResearchOrchestrator(config)

    report = agent.create_report(
        ReportRequest(topic="某公司增长分析", sources=[str(source)], web_search=False)
    )

    assert Path(report.path).exists()
    assert "某公司2025年营收增长20%" in report.content
    assert report.citations[0]["id"] == "S1"
    assert "## 目录" in report.content
    assert "## 可信评估" in report.content
    assert "## 参考来源" in report.content
    assert "## 免责声明" in report.content
    plan = agent._fallback_plan("某公司增长分析", "standard")
    assert ProfessionalReportWriter.validate(report.content, plan, report.citations) == []

    response = agent.chat(report.id, "主要风险是什么？")
    assert "客户集中度" in response.answer
    assert response.citations


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_litellm_model_prefix_is_normalized() -> None:
    config = Settings(
        _env_file=None,
        openai_api_key="test",
        openai_model="ignored",
        litellm_model="openai/deepseek-v4-pro",
    )
    assert config.model_name == "deepseek-v4-pro"


def test_report_degrades_when_llm_fails(tmp_path: Path) -> None:
    source = tmp_path / "evidence.txt"
    source.write_text("可验证资料", encoding="utf-8")
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )

    class FailingLLM:
        available = True

        def json(self, *_args, **_kwargs):
            raise TimeoutError

        def complete(self, *_args, **_kwargs):
            raise TimeoutError

    agent.llm = FailingLLM()
    report = agent.create_report(
        ReportRequest(topic="降级测试", sources=[str(source)], web_search=False)
    )
    assert "已自动降级为证据摘要版" in report.content
    assert agent.storage.get_task(report.task_id).status == "completed"


def test_report_modes_have_expected_chapter_counts(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    assert len(agent.plan("测试主题", "quick").chapters) == 6
    assert len(agent.plan("测试主题", "standard").chapters) == 8
    assert len(agent.plan("测试主题", "deep").chapters) == 10


def test_incomplete_model_chapter_is_rejected(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    chapter = agent._fallback_plan("测试主题", "quick").chapters[0]
    assert not ProfessionalReportWriter._chapter_is_valid(
        1, chapter, "> 只有结论，没有预定子节和引用。"
    )

from pathlib import Path

from fastapi.testclient import TestClient

from research_agent.api import app
from research_agent.config import Settings
from research_agent.env_config import EnvironmentConfigService
from research_agent.models import ReportRequest
from research_agent.orchestrator import ResearchOrchestrator
from research_agent.report_writer import ProfessionalReportWriter
from research_agent.text import report_filename


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
    assert Path(report.path).name == report_filename(report.title)
    assert "某公司2025年营收增长20%" in report.content
    assert report.citations[0]["id"] == "S1"
    assert "## 目录" in report.content
    assert "> **研究问题**：某公司增长分析" in report.content
    assert "## 1. 核心判断" in report.content
    assert "## 参考来源与证据" in report.content
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


def test_report_can_be_renamed_pinned_and_deleted(tmp_path: Path) -> None:
    source = tmp_path / "evidence.md"
    source.write_text("可验证资料", encoding="utf-8")
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    report = agent.create_report(
        ReportRequest(topic="管理测试", sources=[str(source)], web_search=False, mode="quick")
    )
    report_path = Path(report.path)

    updated = agent.storage.update_report(report.id, title="新的标题", is_pinned=True)

    assert updated is not None
    assert updated.title == "新的标题"
    assert updated.is_pinned is True
    assert agent.storage.list_reports()[0].id == report.id
    assert agent.storage.delete_report(report.id) is True
    assert agent.storage.get_report(report.id) is None
    assert agent.storage.get_task(report.task_id) is None
    assert report_path.exists() is False


def test_environment_config_preserves_unmanaged_content(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# existing comment\nUNMANAGED=value\nOPENAI_MODEL=old-model\n",
        encoding="utf-8",
    )
    service = EnvironmentConfigService(env_path)

    values = service.update(
        {"OPENAI_MODEL": "new model", "OPENAI_API_KEY": 'secret"value'}
    )
    content = env_path.read_text(encoding="utf-8")

    assert values["OPENAI_MODEL"] == "new model"
    assert values["OPENAI_API_KEY"] == 'secret"value'
    assert "# existing comment" in content
    assert "UNMANAGED=value" in content
    assert 'OPENAI_MODEL="new model"' in content
    assert 'OPENAI_API_KEY="secret\\"value"' in content


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
    assert any("已降级" in warning for warning in report.qa_warnings)
    assert agent.storage.get_task(report.task_id).status == "completed"
    assert agent.storage.get_report(report.id).qa_warnings == report.qa_warnings


def test_report_modes_have_expected_chapter_counts(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    assert len(agent.plan("测试主题", "quick").chapters) == 6
    assert len(agent.plan("测试主题", "standard").chapters) == 8
    assert len(agent.plan("测试主题", "deep").chapters) == 10


def test_outline_json_fences_and_chapter_fill(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    payload = agent._parse_outline_json(
        '```json\n{"title":"测试报告","chapters":[{"title":"自定义章","focus":"验证重点"}]}\n```'
    )
    chapters = agent._normalize_outline_chapters("测试主题", "quick", payload["chapters"])
    assert payload["title"] == "测试报告"
    assert len(chapters) == 6
    assert chapters[0].focus == "验证重点"
    oversized = [{"title": f"章{i}", "focus": "重点"} for i in range(20)]
    assert len(agent._normalize_outline_chapters("测试主题", "quick", oversized)) == 6


def test_invalid_outline_falls_back_completely(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )

    class InvalidOutlineLLM:
        available = True

        def complete(self, *_args, **_kwargs):
            return "这不是 JSON"

    agent.llm = InvalidOutlineLLM()
    plan = agent.plan("测试主题", "quick")
    assert plan.title == "测试主题深度研究报告"
    assert [chapter.title for chapter in plan.chapters][-2:] == ["风险与反方观点", "结论与判断边界"]


def test_missing_citation_rewrites_only_once(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    plan = agent._fallback_plan("测试主题", "quick")

    class RewriteLLM:
        available = True

        def __init__(self):
            self.calls = 0

        def complete(self, *_args, **_kwargs):
            self.calls += 1
            return "> 判断\n\n第二次包含事实引用[S1]。" if self.calls == 2 else "> 判断\n\n没有引用。"

    llm = RewriteLLM()
    writer = ProfessionalReportWriter(agent.config, llm)
    content, rewritten = writer._write_one_chapter(1, 6, plan.chapters[0], "[S1] 证据", plan)
    assert rewritten is True
    assert llm.calls == 2
    assert "[S1]" in content


def test_invalid_citation_is_warning_not_replaced(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    plan = agent._fallback_plan("测试主题", "quick")
    report = ProfessionalReportWriter._assemble(
        "测试主题", plan, ["> 判断[S99]" for _ in plan.chapters], [{"id": "S1", "title": "证据", "url": ""}]
    )
    warnings = ProfessionalReportWriter.validate(report, plan, [{"id": "S1"}])
    assert "[[S99]](#ref-s99)" in report
    assert "引用不存在：[S99]" in warnings


def test_markdown_citations_link_to_source_anchors(tmp_path: Path) -> None:
    agent = ResearchOrchestrator(
        Settings(_env_file=None, openai_api_key="", data_dir=tmp_path / "data")
    )
    plan = agent._fallback_plan("测试主题", "quick")
    report = ProfessionalReportWriter._assemble(
        "测试主题",
        plan,
        ["> 判断包含事实[S1]。" for _ in plan.chapters],
        [{"id": "S1", "title": "证据", "url": "https://example.com"}],
    )
    assert "[[S1]](#ref-s1)" in report
    assert '<a id="ref-s1"></a>' in report


def test_report_title_becomes_safe_filename() -> None:
    assert report_filename('公司/A: "深度"研究?') == "公司_A_ _深度_研究_.md"


def test_info_logs_require_info_debug() -> None:
    assert Settings(_env_file=None, info="").info_logging_enabled is False
    assert Settings(_env_file=None, info="INFO").info_logging_enabled is False
    assert Settings(_env_file=None, info="debug").info_logging_enabled is True

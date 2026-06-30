from types import SimpleNamespace

from research_agent.chat_agent import ReportChatAgent
from research_agent.config import Settings
from research_agent.models import ReportRecord, SourceDocument


class FakeToolCall:
    def __init__(self, name: str, arguments: str):
        self.id = f"call-{name}"
        self.function = SimpleNamespace(name=name, arguments=arguments)

    def model_dump(self):
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


class FakeCompletions:
    def __init__(self, tool_name: str, arguments: str, final_answer: str):
        self.responses = [
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="", tool_calls=[FakeToolCall(tool_name, arguments)]
                        )
                    )
                ]
            ),
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=final_answer, tool_calls=None)
                    )
                ]
            ),
        ]
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeStorage:
    def recent_messages(self, _report_id, limit=10):
        return [
            {"role": "user", "content": "上一轮问题"},
            {"role": "assistant", "content": "上一轮回答"},
        ][-limit:]

    def retrieve(self, *_args, **_kwargs):
        return []


class FakeRetriever:
    def retrieve_query(self, *_args, **_kwargs):
        return (
            "[S1] 年报证据：营业收入增长。",
            [
                {
                    "citation_id": "S1",
                    "title": "年度报告",
                    "url": "https://example.com/annual",
                    "source_type": "annual_report",
                }
            ],
        )


class FakeSearch:
    provider = "test"

    def search(self, _queries, _limit):
        return [
            SourceDocument(
                id="web-1",
                source_type="web",
                title="最新公告新闻",
                url="https://example.com/news",
                content="公司发布最新公告。",
            )
        ]


def _report() -> ReportRecord:
    return ReportRecord(
        id="report-1",
        task_id="task-1",
        title="测试研报",
        content="# 测试研报\n\n核心观点。",
        path="/tmp/report.md",
        citations=[{"id": "S1", "title": "年度报告", "url": "https://example.com/annual"}],
        stock_code="600519",
        data_cutoff="2026-06-30",
        source_types=["annual_report", "research"],
        created_at="2026-06-30T00:00:00+00:00",
    )


def _agent(tool_name: str, arguments: str, final_answer: str):
    completions = FakeCompletions(tool_name, arguments, final_answer)
    llm = SimpleNamespace(
        available=True,
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions)),
    )
    config = Settings(
        _env_file=None,
        openai_api_key="test",
        openai_model="test-model",
        data_dir="/tmp/chat-agent-test",
    )
    return (
        ReportChatAgent(config, llm, FakeStorage(), FakeRetriever(), FakeSearch()),
        completions,
    )


def test_chat_agent_uses_rag_and_preserves_history() -> None:
    agent, completions = _agent("rag_search", '{"query":"营业收入变化"}', "收入保持增长[S1]。")
    response = agent.answer(_report(), "展开财务表现")

    assert response.answer == "收入保持增长[S1]。"
    assert response.citations[0]["id"] == "S1"
    first_messages = completions.calls[0]["messages"]
    assert any(item.get("content") == "上一轮问题" for item in first_messages)
    assert any(tool["function"]["name"] == "rag_search" for tool in completions.calls[0]["tools"])


def test_chat_agent_can_call_web_search() -> None:
    agent, _ = _agent("web_search", '{"query":"最新公告","max_results":3}', "最新信息见[W1]。")
    response = agent.answer(_report(), "研报之后有什么新消息？")

    assert response.citations == [
        {
            "id": "W1",
            "title": "最新公告新闻",
            "url": "https://example.com/news",
            "source_type": "web_search",
        }
    ]


def test_web_citation_numbers_continue_across_turns() -> None:
    agent, completions = _agent(
        "web_search", '{"query":"后续消息","max_results":1}', "新增信息见[W4]。"
    )

    class HistoryStorage(FakeStorage):
        def recent_messages(self, _report_id, limit=10):
            return [
                {
                    "role": "assistant",
                    "content": "上一轮信息见[W3]。",
                    "citations": [
                        {"id": "W3", "title": "旧消息", "url": "https://example.com/old"}
                    ],
                }
            ]

    agent.storage = HistoryStorage()
    response = agent.answer(_report(), "继续搜索")

    assert response.citations[0]["id"] == "W4"
    assert completions.calls

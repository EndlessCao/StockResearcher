from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceDocument(BaseModel):
    id: str
    source_type: str
    title: str
    url: str = ""
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportChapter(BaseModel):
    title: str
    focus: str
    retrieval_questions: list[str] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    topic: str
    title: str = ""
    report_type: str = "公司/产品研究"
    depth_mode: Literal["quick", "standard", "deep"] = "standard"
    target_year: int | None = None
    time_anchor: Literal["latest", "relaxed", "user_specified"] = "latest"
    stock_code: str | None = None
    data_cutoff: str | None = None
    source_types: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    chapters: list[ReportChapter] = Field(default_factory=list)


class ReportRequest(BaseModel):
    topic: str
    sources: list[str] = Field(default_factory=list)
    web_search: bool = True
    max_search_results: int = Field(default=6, ge=0, le=20)
    mode: Literal["quick", "standard", "deep"] = "standard"
    stock_code: str | None = None
    data_cutoff: str | None = None
    source_types: list[str] = Field(
        default_factory=lambda: [
            "annual_report",
            "quarterly_report",
            "announcement",
            "research",
        ]
    )


class ChatRequest(BaseModel):
    question: str


class TaskRecord(BaseModel):
    id: str
    topic: str
    status: Literal["pending", "running", "completed", "failed", "cancelled"]
    error: str | None = None
    report_id: str | None = None
    created_at: str
    completed_at: str | None = None


class ReportRecord(BaseModel):
    id: str
    task_id: str
    title: str
    content: str
    path: str
    citations: list[dict[str, Any]]
    qa_warnings: list[str] = Field(default_factory=list)
    stock_code: str | None = None
    data_cutoff: str | None = None
    source_types: list[str] = Field(default_factory=list)
    created_at: str
    is_pinned: bool = False


class ReportUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None


class EnvironmentConfigRecord(BaseModel):
    path: str
    values: dict[str, str]


class EnvironmentConfigUpdate(BaseModel):
    values: dict[str, str]


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ConversationMessage(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str

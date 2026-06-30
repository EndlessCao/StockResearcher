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


class ResearchSubQuestion(BaseModel):
    question: str
    search_keywords: list[str] = Field(default_factory=list)
    counter_keywords: list[str] = Field(default_factory=list)
    data_targets: list[str] = Field(default_factory=list)
    priority: Literal["high", "medium", "low"] = "medium"


class ReportChapter(BaseModel):
    title: str
    description: str
    sections: list[str] = Field(default_factory=list)
    sub_questions: list[ResearchSubQuestion] = Field(default_factory=list)


class ResearchPlan(BaseModel):
    topic: str
    title: str = ""
    report_type: str = "公司/产品研究"
    depth_mode: Literal["quick", "standard", "deep"] = "standard"
    target_year: int | None = None
    time_anchor: Literal["latest", "relaxed", "user_specified"] = "latest"
    questions: list[str] = Field(default_factory=list)
    chapters: list[ReportChapter] = Field(default_factory=list)


class ReportRequest(BaseModel):
    topic: str
    sources: list[str] = Field(default_factory=list)
    web_search: bool = True
    max_search_results: int = Field(default=6, ge=0, le=20)
    mode: Literal["quick", "standard", "deep"] = "standard"


class ChatRequest(BaseModel):
    question: str


class TaskRecord(BaseModel):
    id: str
    topic: str
    status: Literal["pending", "running", "completed", "failed"]
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
    created_at: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[dict[str, Any]] = Field(default_factory=list)

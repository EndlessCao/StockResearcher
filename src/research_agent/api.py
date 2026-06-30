from __future__ import annotations

from fastapi import FastAPI, HTTPException

from . import __version__
from .config import settings
from .models import ChatRequest, ChatResponse, ReportRecord, ReportRequest, TaskRecord
from .observability import configure_logging
from .orchestrator import ResearchOrchestrator


configure_logging(settings.log_level)

app = FastAPI(
    title="Stock Research Agent API",
    description="本地优先的金融深度研究、研报生成与上下文问答 API",
    version=__version__,
)
agent = ResearchOrchestrator()


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "llm_configured": agent.llm.available,
        "search_provider": agent.search.provider,
    }


@app.post("/api/v1/reports", response_model=ReportRecord)
def create_report(request: ReportRequest) -> ReportRecord:
    try:
        return agent.create_report(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/reports", response_model=list[ReportRecord])
def list_reports(limit: int = 50) -> list[ReportRecord]:
    return agent.storage.list_reports(max(1, min(limit, 100)))


@app.get("/api/v1/reports/{report_id}", response_model=ReportRecord)
def get_report(report_id: str) -> ReportRecord:
    report = agent.storage.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    return report


@app.post("/api/v1/reports/{report_id}/chat", response_model=ChatResponse)
def chat(report_id: str, request: ChatRequest) -> ChatResponse:
    try:
        return agent.chat(report_id, request.question)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    task = agent.storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task

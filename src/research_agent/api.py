from __future__ import annotations

import logging
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from ipaddress import ip_address
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, HTTPException, Request, Response, status

from . import __version__
from .config import settings
from .env_config import EnvironmentConfigService
from .exceptions import ResearchCancelled
from .models import (
    ChatRequest,
    ChatResponse,
    ConversationMessage,
    EnvironmentConfigRecord,
    EnvironmentConfigUpdate,
    ReportRecord,
    ReportRequest,
    ReportUpdateRequest,
    TaskRecord,
)
from .observability import configure_logging
from .orchestrator import ResearchOrchestrator


configure_logging(settings.info_logging_enabled)

app = FastAPI(
    title="Stock Research Agent API",
    description="本地优先的金融深度研究、研报生成与上下文问答 API",
    version=__version__,
)
agent = ResearchOrchestrator()
agent.storage.fail_incomplete_tasks()
environment_config = EnvironmentConfigService(Path(".env"))
generation_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="report-generation")
generation_futures: dict[str, Future[object]] = {}
generation_lock = Lock()
logger = logging.getLogger(__name__)


def _run_generation(task_id: str, report_request: ReportRequest) -> None:
    try:
        agent.create_report(report_request, task_id=task_id)
    except ResearchCancelled:
        pass
    except Exception:
        logger.exception("后台研报任务失败 task_id=%s", task_id)


def _forget_generation(task_id: str) -> None:
    with generation_lock:
        generation_futures.pop(task_id, None)


def _require_local_request(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host == "testclient":
        return
    try:
        if ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(status_code=403, detail="配置接口仅允许本机访问")


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "llm_configured": agent.llm.available,
        "search_provider": agent.search.provider,
        "vector_database": "chroma",
        "embedding_configured": agent.retriever.embedding.remote_enabled,
        "rerank_configured": agent.retriever.reranker.enabled,
    }


@app.post("/api/v1/reports", response_model=ReportRecord)
def create_report(request: ReportRequest) -> ReportRecord:
    try:
        return agent.create_report(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/tasks", response_model=TaskRecord, status_code=status.HTTP_202_ACCEPTED)
def submit_report_task(request: ReportRequest) -> TaskRecord:
    task_id = f"task_{uuid.uuid4().hex[:12]}"
    task = agent.storage.create_task(task_id, request.topic)
    future = generation_executor.submit(_run_generation, task_id, request)
    with generation_lock:
        generation_futures[task_id] = future
    future.add_done_callback(lambda _future: _forget_generation(task_id))
    return task


@app.get("/api/v1/reports", response_model=list[ReportRecord])
def list_reports(limit: int = 50) -> list[ReportRecord]:
    return agent.storage.list_reports(max(1, min(limit, 100)))


@app.get("/api/v1/reports/{report_id}", response_model=ReportRecord)
def get_report(report_id: str) -> ReportRecord:
    report = agent.storage.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    return report


@app.patch("/api/v1/reports/{report_id}", response_model=ReportRecord)
def update_report(report_id: str, request: ReportUpdateRequest) -> ReportRecord:
    if request.title is None and request.is_pinned is None:
        raise HTTPException(status_code=422, detail="至少提供一个要修改的字段")
    try:
        report = agent.storage.update_report(
            report_id, title=request.title, is_pinned=request.is_pinned
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not report:
        raise HTTPException(status_code=404, detail="研报不存在")
    return report


@app.delete("/api/v1/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: str) -> Response:
    if not agent.storage.delete_report(report_id):
        raise HTTPException(status_code=404, detail="研报不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/v1/reports/{report_id}/chat", response_model=ChatResponse)
def chat(report_id: str, request: ChatRequest) -> ChatResponse:
    try:
        return agent.chat(report_id, request.question)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get(
    "/api/v1/reports/{report_id}/messages",
    response_model=list[ConversationMessage],
)
def get_conversation_messages(report_id: str, limit: int = 200) -> list[ConversationMessage]:
    if not agent.storage.get_report(report_id):
        raise HTTPException(status_code=404, detail="研报不存在")
    rows = agent.storage.conversation_messages(report_id, max(1, min(limit, 500)))
    return [ConversationMessage.model_validate(row) for row in rows]


@app.get("/api/v1/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str) -> TaskRecord:
    task = agent.storage.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.get("/api/v1/tasks", response_model=list[TaskRecord])
def list_tasks(limit: int = 50, active_only: bool = False) -> list[TaskRecord]:
    return agent.storage.list_tasks(
        max(1, min(limit, 100)), active_only=active_only
    )


@app.post("/api/v1/tasks/{task_id}/cancel", response_model=TaskRecord)
def cancel_task(task_id: str) -> TaskRecord:
    task = agent.storage.cancel_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="生成任务不存在")
    with generation_lock:
        future = generation_futures.get(task_id)
        if future:
            future.cancel()
    return task


@app.get("/api/v1/config/environment", response_model=EnvironmentConfigRecord)
def get_environment_config(request: Request) -> EnvironmentConfigRecord:
    _require_local_request(request)
    return EnvironmentConfigRecord(
        path=str(environment_config.path), values=environment_config.read()
    )


@app.put("/api/v1/config/environment", response_model=EnvironmentConfigRecord)
def update_environment_config(
    request: Request, update: EnvironmentConfigUpdate
) -> EnvironmentConfigRecord:
    _require_local_request(request)
    try:
        values = environment_config.update(update.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return EnvironmentConfigRecord(path=str(environment_config.path), values=values)

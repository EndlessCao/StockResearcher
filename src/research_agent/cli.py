from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional
from typing import Literal

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from .config import settings
from .models import ReportRequest
from .observability import configure_logging
from .orchestrator import ResearchOrchestrator


app = typer.Typer(help="本地优先的金融深度研究 Agent", no_args_is_help=True)
console = Console()
configure_logging(settings.log_level)


@app.command()
def report(
    topic: str = typer.Option(..., "--topic", "-t", help="研究主题"),
    sources: Optional[list[str]] = typer.Option(None, "--sources", "-s", help="本地文件、目录或 URL，可重复"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="额外复制到指定 Markdown 路径"),
    web: bool = typer.Option(True, "--web/--no-web", help="是否自动网络检索"),
    max_results: int = typer.Option(6, "--max-results", min=0, max=20),
    mode: Literal["quick", "standard", "deep"] = typer.Option(
        "standard", "--mode", help="研报深度：quick / standard / deep"
    ),
) -> None:
    """创建研究任务并生成 Markdown 研报。"""
    agent = ResearchOrchestrator()
    with console.status("正在规划、检索并生成研报..."):
        result = agent.create_report(
            ReportRequest(
                topic=topic,
                sources=sources or [],
                web_search=web,
                max_search_results=max_results,
                mode=mode,
            )
        )
    destination = Path(result.path)
    if output:
        output = output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(destination, output)
        destination = output
    console.print(f"[green]研报已生成[/green]  ID: {result.id}")
    console.print(f"文件: {destination}")
    console.print(f"引用来源: {len(result.citations)}")
    if result.qa_warnings:
        console.print(f"[yellow]QA 告警: {len(result.qa_warnings)} 条[/yellow]")
        for warning in result.qa_warnings:
            console.print(f"  - {warning}")


@app.command()
def chat(
    question: str = typer.Option(..., "--question", "-q", help="针对研报的问题"),
    report_id: Optional[str] = typer.Option(None, "--report-id", help="数据库中的研报 ID"),
    report: Optional[Path] = typer.Option(None, "--report", help="已有 Markdown 研报路径"),
) -> None:
    """基于已生成或已有研报进行问答。"""
    if not report_id and not report:
        raise typer.BadParameter("必须提供 --report-id 或 --report")
    agent = ResearchOrchestrator()
    if not report_id:
        report_id = agent.import_report(str(report)).id
    response = agent.chat(report_id, question)
    console.print(response.answer)
    if response.citations:
        console.print("\n[dim]检索依据：" + ", ".join(item["id"] for item in response.citations) + "[/dim]")


@app.command("list")
def list_reports(limit: int = typer.Option(20, "--limit", min=1, max=100)) -> None:
    """列出本地研报。"""
    reports = ResearchOrchestrator().storage.list_reports(limit)
    table = Table("ID", "标题", "创建时间", "路径")
    for item in reports:
        table.add_row(item.id, item.title, item.created_at, item.path)
    console.print(table)


@app.command()
def status(task_id: str = typer.Argument(..., help="研究任务 ID")) -> None:
    """查询研究任务状态。"""
    task = ResearchOrchestrator().storage.get_task(task_id)
    if not task:
        raise typer.BadParameter(f"任务不存在：{task_id}")
    console.print_json(task.model_dump_json())


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """启动 FastAPI 服务。"""
    uvicorn.run("research_agent.api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path

from .config import Settings, settings
from .exceptions import ResearchCancelled
from .chat_agent import ReportChatAgent
from .connectors import DocumentConnector, SearchConnector
from .llm import LLMClient
from .models import (
    ChatResponse,
    ReportChapter,
    ReportRecord,
    ReportRequest,
    ResearchPlan,
    SourceDocument,
    utc_now,
)
from .report_writer import MODE_LIMITS, ProfessionalReportWriter
from .retrieval import ChromaHybridRetriever
from .storage import Storage
from .text import report_filename


logger = logging.getLogger(__name__)


class ResearchOrchestrator:
    def __init__(self, config: Settings | None = None):
        self.config = config or settings
        self.storage = Storage(self.config)
        self.llm = LLMClient(self.config)
        self.documents = DocumentConnector(self.config)
        self.search = SearchConnector(self.config)
        self.retriever = ChromaHybridRetriever(self.config)
        self.chat_agent = ReportChatAgent(
            self.config, self.llm, self.storage, self.retriever, self.search
        )

    def plan(self, topic: str, mode: str = "standard") -> ResearchPlan:
        logger.info("研报规划开始 topic=%r mode=%s", topic, mode)
        fallback = self._fallback_plan(topic, mode)
        if not self.llm.available:
            logger.info("研报规划使用本地兜底大纲 reason=llm_not_configured chapters=%d", len(fallback.chapters))
            return fallback
        try:
            raw = self.llm.complete(
                "你是证券研究规划员。只返回 JSON，不写解释，不陈述未经检索的事实。",
                f"""为“{topic}”设计中文研报大纲。建议生成 {MODE_LIMITS[mode]['chapters']} 章。
必须严格返回以下结构，字段只能是 title、chapters、chapters[].title、chapters[].focus：
{{
  "title": "报告标题",
  "chapters": [
    {{"title": "章节标题", "focus": "写作重点"}}
  ]
}}
章节应覆盖核心判断、研究边界、行业与市场、商业与财务、竞争、风险与反方观点、最终判断。""",
                temperature=0,
                max_tokens=2500,
            )
            result = self._parse_outline_json(raw)
            chapters = self._normalize_outline_chapters(topic, mode, result["chapters"])
            questions = [f"{topic} {chapter.title} {chapter.focus} 最新数据与反方证据" for chapter in chapters]
            plan = ResearchPlan(
                topic=topic,
                title=str(result.get("title") or f"{topic}深度研究报告"),
                depth_mode=mode,
                target_year=int(result.get("target_year") or datetime.now().year),
                questions=questions,
                chapters=chapters,
            )
            logger.info(
                "研报规划完成 title=%r chapters=%d questions=%d",
                plan.title,
                len(plan.chapters),
                len(plan.questions),
            )
            return plan
        except Exception as exc:
            logger.warning("研报规划失败，使用本地兜底大纲 error=%s", type(exc).__name__)
            return fallback

    @staticmethod
    def _parse_outline_json(raw: str) -> dict:
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        payload = json.loads(cleaned)
        if not isinstance(payload, dict) or not isinstance(payload.get("title"), str):
            raise ValueError("大纲缺少有效 title")
        if set(payload) != {"title", "chapters"}:
            raise ValueError("大纲只能包含 title 和 chapters")
        if not isinstance(payload.get("chapters"), list):
            raise ValueError("大纲缺少有效 chapters")
        for chapter in payload["chapters"]:
            if not isinstance(chapter, dict) or not isinstance(chapter.get("title"), str) or not isinstance(chapter.get("focus"), str):
                raise ValueError("章节必须包含字符串 title 和 focus")
            if set(chapter) != {"title", "focus"}:
                raise ValueError("章节只能包含 title 和 focus")
        return payload

    @staticmethod
    def _fixed_chapters(topic: str, mode: str) -> list[ReportChapter]:
        templates = [
            ("核心判断", "提炼最重要的结论、关键变量及其证据边界。"),
            ("研究对象与口径", "定义研究对象、业务边界、时间范围和指标口径。"),
            ("行业与市场空间", "分析需求驱动、市场规模、增速和周期位置。"),
            ("商业模式与经营质量", "分析收入结构、盈利机制、现金流和经营效率。"),
            ("竞争格局与壁垒", "比较主要对手、市场份额、竞争优势及其可持续性。"),
            ("财务表现与关键指标", "核查增长、利润、现金流和资产负债表表现。"),
            ("估值与情景假设", "区分实际数据、机构预期和不同情景下的估值假设。"),
            ("风险与反方观点", "呈现反方证据、下行风险和核心逻辑的证伪条件。"),
            ("催化因素与跟踪指标", "识别可能改变判断的事件和持续跟踪指标。"),
            ("结论与判断边界", "形成结论，同时明确不确定性和不构成投资承诺的边界。"),
        ]
        if mode == "quick":
            templates = [templates[index] for index in (0, 1, 2, 4, 7, 9)]
        elif mode == "standard":
            templates = [templates[index] for index in (0, 1, 2, 3, 4, 5, 7, 9)]
        return [ReportChapter(title=title, focus=f"围绕{topic}，{focus}") for title, focus in templates]

    @classmethod
    def _normalize_outline_chapters(cls, topic: str, mode: str, raw_chapters: list[dict]) -> list[ReportChapter]:
        target = MODE_LIMITS[mode]["chapters"]
        chapters = [ReportChapter(title=item["title"].strip(), focus=item["focus"].strip()) for item in raw_chapters]
        existing = {chapter.title for chapter in chapters}
        for chapter in cls._fixed_chapters(topic, mode):
            if len(chapters) >= target:
                break
            if chapter.title not in existing:
                chapters.append(chapter)
                existing.add(chapter.title)
        normalized = chapters[:target]
        return [
            chapter.model_copy(
                update={"retrieval_questions": ChromaHybridRetriever.chapter_questions(topic, chapter)}
            )
            for chapter in normalized
        ]

    @classmethod
    def _fallback_plan(cls, topic: str, mode: str) -> ResearchPlan:
        chapters = cls._normalize_outline_chapters(topic, mode, [])
        return ResearchPlan(
            topic=topic,
            title=f"{topic}深度研究报告",
            report_type="公司/产品研究",
            depth_mode=mode,
            target_year=datetime.now().year,
            time_anchor="latest",
            questions=[f"{topic} {chapter.title} {chapter.focus} 最新数据与反方证据" for chapter in chapters],
            chapters=chapters,
        )

    def create_report(
        self, request: ReportRequest, task_id: str | None = None
    ) -> ReportRecord:
        task_id = task_id or f"task_{uuid.uuid4().hex[:12]}"
        logger.info(
            "研报任务开始 task_id=%s topic=%r mode=%s web_search=%s local_sources=%d max_search_results=%d",
            task_id,
            request.topic,
            request.mode,
            request.web_search,
            len(request.sources),
            request.max_search_results,
        )
        if not self.storage.get_task(task_id):
            self.storage.create_task(task_id, request.topic)
        self._check_cancelled(task_id)
        self.storage.update_task(task_id, status="running", error=None, completed_at=None)
        report: ReportRecord | None = None
        try:
            plan = self.plan(request.topic, request.mode)
            self._check_cancelled(task_id)
            logger.info("资料收集开始 task_id=%s", task_id)
            sources = self._collect_sources(request, plan)
            self._check_cancelled(task_id)
            if not sources:
                raise RuntimeError("没有可用资料：请配置搜索 API，或通过 --sources 提供本地文件/URL")
            logger.info("资料收集完成 task_id=%s sources=%d", task_id, len(sources))
            for source in sources:
                self._check_cancelled(task_id)
                self.storage.add_source(task_id, source)
            logger.info("资料切分与入库完成 task_id=%s sources=%d", task_id, len(sources))
            logger.info("研报写作开始 task_id=%s chapters=%d", task_id, len(plan.chapters))
            report = self._write_report(task_id, request.topic, plan, sources, request)
            self._check_cancelled(task_id)
            logger.info(
                "研报写作完成 task_id=%s report_id=%s content_chars=%d",
                task_id,
                report.id,
                len(report.content),
            )
            self.storage.save_report(report)
            logger.info("研报及上下文入库完成 task_id=%s report_id=%s", task_id, report.id)
            self.storage.update_task(
                task_id, status="completed", report_id=report.id, completed_at=utc_now()
            )
            logger.info(
                "研报任务完成 task_id=%s report_id=%s path=%s citations=%d",
                task_id,
                report.id,
                report.path,
                len(report.citations),
            )
            return report
        except ResearchCancelled:
            if report:
                report_path = Path(report.path).expanduser().resolve()
                reports_dir = self.config.reports_dir.expanduser().resolve()
                if report_path.is_relative_to(reports_dir) and report_path.is_file():
                    report_path.unlink()
            self.storage.cleanup_task_artifacts(task_id)
            self.storage.update_task(
                task_id,
                status="cancelled",
                error="用户取消生成",
                completed_at=utc_now(),
            )
            logger.info("研报任务已取消 task_id=%s", task_id)
            raise
        except Exception as exc:
            current_task = self.storage.get_task(task_id)
            if current_task and current_task.status == "cancelled":
                self.storage.cleanup_task_artifacts(task_id)
                raise ResearchCancelled("研报生成已取消") from exc
            self.storage.update_task(
                task_id, status="failed", error=str(exc), completed_at=utc_now()
            )
            logger.exception("研报任务失败 task_id=%s error=%s", task_id, type(exc).__name__)
            raise

    def _check_cancelled(self, task_id: str) -> None:
        task = self.storage.get_task(task_id)
        if task and task.status == "cancelled":
            raise ResearchCancelled("研报生成已取消")

    def _collect_sources(self, request: ReportRequest, plan: ResearchPlan) -> list[SourceDocument]:
        sources: list[SourceDocument] = []
        for location in request.sources:
            sources.extend(self.documents.load(location))
        if request.web_search:
            logger.info(
                "网络检索开始 provider=%s questions=%d", self.search.provider, len(plan.questions)
            )
            search_docs = self.search.search(plan.questions, request.max_search_results)
            logger.info("网络检索结果获取完成 results=%d，开始抓取正文", len(search_docs))
            # Grab full text for a few results. A blocked page falls back to its search snippet.
            for item in search_docs[:4]:
                try:
                    loaded = self.documents.load(item.url)[0]
                    loaded.metadata.update(item.metadata)
                    sources.append(loaded)
                except Exception as exc:
                    logger.warning(
                        "网页正文抓取失败，保留搜索摘要 source_id=%s error=%s",
                        item.id,
                        type(exc).__name__,
                    )
                    sources.append(item)
            sources.extend(search_docs[4:])
        deduped: dict[str, SourceDocument] = {}
        for source in sources:
            key = source.url or source.id
            if source.content.strip() and key not in deduped:
                deduped[key] = source
        result = list(deduped.values())
        logger.info("资料去重完成 before=%d after=%d", len(sources), len(result))
        return result

    def _write_report(
        self,
        task_id: str,
        topic: str,
        plan: ResearchPlan,
        sources: list[SourceDocument],
        request: ReportRequest,
    ) -> ReportRecord:
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        logger.info(
            "专业研报写作器启动 report_id=%s mode=%s chapters=%d sources=%d",
            report_id,
            plan.depth_mode,
            len(plan.chapters),
            len(sources),
        )
        citations = [
            {
                "id": f"S{index}",
                "title": source.title,
                "url": source.url,
                "source_type": source.source_type,
                "reliability": source.metadata.get("source_reliability", "unknown"),
            }
            for index, source in enumerate(sources, 1)
        ]
        citation_ids = {source.id: f"S{index}" for index, source in enumerate(sources, 1)}
        data_cutoff = request.data_cutoff or datetime.now().astimezone().date().isoformat()
        try:
            datetime.fromisoformat(data_cutoff)
        except ValueError as exc:
            raise ValueError("data_cutoff 必须使用 YYYY-MM-DD 格式") from exc
        plan = plan.model_copy(
            update={
                "stock_code": request.stock_code,
                "data_cutoff": data_cutoff,
                "source_types": request.source_types,
            }
        )
        evidence_packets: list[str] | None = []
        retrieval_diagnostics = []
        retrieval_warning: str | None = None
        try:
            self.retriever.index_documents(task_id, sources, request.stock_code, citation_ids)
            for chapter in plan.chapters:
                packet, diagnostics = self.retriever.retrieve_chapter(
                    task_id,
                    chapter,
                    request.stock_code,
                    data_cutoff,
                    request.source_types,
                )
                evidence_packets.append(packet)
                retrieval_diagnostics.append(diagnostics)
                logger.info(
                    "章节混合检索完成 title=%r questions=%d evidence_blocks=%d",
                    chapter.title,
                    len(chapter.retrieval_questions),
                    len(diagnostics),
                )
        except Exception as exc:
            evidence_packets = None
            retrieval_warning = f"远程向量检索失败，已回退本地章节证据池：{type(exc).__name__}"
            logger.warning(
                "章节混合检索失败，回退本地证据池 error=%s",
                type(exc).__name__,
                exc_info=True,
            )
        content, qa_warnings = ProfessionalReportWriter(
            self.config,
            self.llm,
            is_cancelled=lambda: (
                (task := self.storage.get_task(task_id)) is not None
                and task.status == "cancelled"
            ),
        ).write(
            topic, plan, sources, citations, evidence_packets=evidence_packets
        )
        if retrieval_warning:
            qa_warnings.insert(0, retrieval_warning)
        report_title = plan.title or f"{topic}研究报告"
        path = self.config.reports_dir / report_filename(report_title)
        path.write_text(content, encoding="utf-8")
        logger.info("Markdown 研报文件写入完成 report_id=%s path=%s", report_id, path.resolve())
        return ReportRecord(
            id=report_id,
            task_id=task_id,
            title=report_title,
            content=content,
            path=str(path.resolve()),
            citations=citations,
            qa_warnings=qa_warnings,
            stock_code=request.stock_code,
            data_cutoff=data_cutoff,
            source_types=request.source_types,
            created_at=utc_now(),
        )

    def chat(self, report_id: str, question: str) -> ChatResponse:
        report = self.storage.get_report(report_id)
        if not report:
            raise KeyError(f"研报不存在：{report_id}")
        response = self.chat_agent.answer(report, question)
        self.storage.add_message(report_id, "user", question)
        self.storage.add_message(report_id, "assistant", response.answer, response.citations)
        return response

    def import_report(self, path: str) -> ReportRecord:
        file_path = Path(path).expanduser().resolve()
        content = file_path.read_text(encoding="utf-8")
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        report_id = f"report_{uuid.uuid4().hex[:12]}"
        self.storage.create_task(task_id, file_path.stem)
        report = ReportRecord(
            id=report_id, task_id=task_id, title=file_path.stem, content=content,
            path=str(file_path), citations=[], created_at=utc_now(),
        )
        self.storage.save_report(report)
        self.storage.update_task(
            task_id, status="completed", report_id=report.id, completed_at=utc_now()
        )
        return report

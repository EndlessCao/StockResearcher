from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from .config import Settings, settings
from .connectors import DocumentConnector, SearchConnector
from .llm import LLMClient
from .models import (
    ChatResponse,
    ReportChapter,
    ReportRecord,
    ReportRequest,
    ResearchPlan,
    ResearchSubQuestion,
    SourceDocument,
    utc_now,
)
from .report_writer import MODE_LIMITS, ProfessionalReportWriter
from .storage import Storage


class ResearchOrchestrator:
    def __init__(self, config: Settings | None = None):
        self.config = config or settings
        self.storage = Storage(self.config)
        self.llm = LLMClient(self.config)
        self.documents = DocumentConnector(self.config)
        self.search = SearchConnector(self.config)

    def plan(self, topic: str, mode: str = "standard") -> ResearchPlan:
        fallback = self._fallback_plan(topic, mode)
        if not self.llm.available:
            return fallback
        try:
            result = self.llm.json(
                """你是严谨的证券研究规划员。只设计研究结构，不陈述未经检索的事实。只输出合法 JSON。""",
                f"""为“{topic}”设计 {mode} 模式中文专业研报大纲，目标年份为 {datetime.now().year}。
章节数量必须为 {MODE_LIMITS[mode]['chapters']}，标题必须包含判断而不是“行业概况”式空标题。
第一章给核心判断，最后两章覆盖风险/反方观点与投资判断边界。每章 2-4 个子节。
每章至少一个可独立搜索的子问题，涉及市场、财务、份额、估值时列出具体 data_targets。
至少一个子问题带 counter_keywords。不得编造任何数据。

返回：
{{"title":"标题","report_type":"公司/产品研究","target_year":{datetime.now().year},"time_anchor":"latest","chapters":[
{{"title":"判断式标题","description":"本章要验证的判断","sections":["子节标题"],"sub_questions":[
{{"question":"问题","search_keywords":["关键词"],"counter_keywords":[],"data_targets":["指标"],"priority":"high"}}
]}}
]}}""",
            )
            chapters = [ReportChapter.model_validate(item) for item in result.get("chapters", [])]
            if len(chapters) != MODE_LIMITS[mode]["chapters"]:
                return fallback
            questions = [
                question.question
                for chapter in chapters
                for question in chapter.sub_questions
                if question.question.strip()
            ]
            return ResearchPlan(
                topic=topic,
                title=str(result.get("title") or f"{topic}深度研究报告"),
                report_type=str(result.get("report_type") or "公司/产品研究"),
                depth_mode=mode,
                target_year=int(result.get("target_year") or datetime.now().year),
                time_anchor=result.get("time_anchor", "latest"),
                questions=questions or fallback.questions,
                chapters=chapters,
            )
        except Exception:
            return fallback

    @staticmethod
    def _fallback_plan(topic: str, mode: str) -> ResearchPlan:
        templates = [
            ("核心判断：增长质量取决于需求、供给与兑现能力", ["核心结论", "关键变量", "争议焦点"]),
            ("研究边界：先统一对象、口径与可比范围", ["对象定义", "业务边界", "数据口径"]),
            ("行业空间：结构性需求决定增长上限", ["需求驱动", "市场空间", "周期位置"]),
            ("商业模式：收入增长需要利润与现金流验证", ["收入结构", "盈利机制", "现金流质量"]),
            ("竞争格局：领先优势取决于可持续壁垒", ["主要对手", "竞争壁垒", "份额变化"]),
            ("经营兑现：战略价值最终回到财务结果", ["增长表现", "利润表现", "经营效率"]),
            ("估值框架：预期差比静态倍数更关键", ["估值口径", "关键假设", "敏感性"]),
            ("风险与反方：核心逻辑存在可证伪条件", ["下行风险", "反方证据", "证伪指标"]),
            ("催化与跟踪：边际变化决定观点调整", ["潜在催化", "跟踪指标", "情景变化"]),
            ("投资判断：结论必须服从证据边界", ["基准情景", "乐观与悲观情景", "判断边界"]),
        ]
        chapter_count = MODE_LIMITS[mode]["chapters"]
        if mode == "quick":
            selected = [templates[i] for i in (0, 1, 2, 4, 7, 9)]
        elif mode == "standard":
            selected = [templates[i] for i in (0, 1, 2, 3, 4, 5, 7, 9)]
        else:
            selected = templates
        chapters = []
        for title, sections in selected[:chapter_count]:
            is_counter = "风险" in title or "反方" in title
            question = ResearchSubQuestion(
                question=f"{topic} {title}需要哪些最新事实与量化指标验证？",
                search_keywords=[f"{topic} {section} {datetime.now().year}" for section in sections[:2]],
                counter_keywords=[f"{topic} 风险 反方观点"] if is_counter else [],
                data_targets=sections,
                priority="high" if is_counter or "核心" in title else "medium",
            )
            chapters.append(
                ReportChapter(
                    title=title,
                    description=f"围绕“{title}”检验证据、因果机制与判断边界。",
                    sections=sections,
                    sub_questions=[question],
                )
            )
        return ResearchPlan(
            topic=topic,
            title=f"{topic}深度研究报告",
            report_type="公司/产品研究",
            depth_mode=mode,
            target_year=datetime.now().year,
            time_anchor="latest",
            questions=[item.question for chapter in chapters for item in chapter.sub_questions],
            chapters=chapters,
        )

    def create_report(self, request: ReportRequest) -> ReportRecord:
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        self.storage.create_task(task_id, request.topic)
        self.storage.update_task(task_id, status="running")
        try:
            plan = self.plan(request.topic, request.mode)
            sources = self._collect_sources(request, plan)
            if not sources:
                raise RuntimeError("没有可用资料：请配置搜索 API，或通过 --sources 提供本地文件/URL")
            for source in sources:
                self.storage.add_source(task_id, source)
            report = self._write_report(task_id, request.topic, plan, sources)
            self.storage.save_report(report)
            self.storage.update_task(
                task_id, status="completed", report_id=report.id, completed_at=utc_now()
            )
            return report
        except Exception as exc:
            self.storage.update_task(
                task_id, status="failed", error=str(exc), completed_at=utc_now()
            )
            raise

    def _collect_sources(self, request: ReportRequest, plan: ResearchPlan) -> list[SourceDocument]:
        sources: list[SourceDocument] = []
        for location in request.sources:
            sources.extend(self.documents.load(location))
        if request.web_search:
            search_docs = self.search.search(plan.questions, request.max_search_results)
            # Grab full text for a few results. A blocked page falls back to its search snippet.
            for item in search_docs[:4]:
                try:
                    loaded = self.documents.load(item.url)[0]
                    loaded.metadata.update(item.metadata)
                    sources.append(loaded)
                except Exception:
                    sources.append(item)
            sources.extend(search_docs[4:])
        deduped: dict[str, SourceDocument] = {}
        for source in sources:
            key = source.url or source.id
            if source.content.strip() and key not in deduped:
                deduped[key] = source
        return list(deduped.values())

    def _write_report(
        self, task_id: str, topic: str, plan: ResearchPlan, sources: list[SourceDocument]
    ) -> ReportRecord:
        report_id = f"report_{uuid.uuid4().hex[:12]}"
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
        content = ProfessionalReportWriter(self.config, self.llm).write(
            topic, plan, sources, citations
        )
        path = self.config.reports_dir / f"{report_id}.md"
        path.write_text(content, encoding="utf-8")
        return ReportRecord(
            id=report_id,
            task_id=task_id,
            title=plan.title or f"{topic}研究报告",
            content=content,
            path=str(path.resolve()),
            citations=citations,
            created_at=utc_now(),
        )

    def chat(self, report_id: str, question: str) -> ChatResponse:
        report = self.storage.get_report(report_id)
        if not report:
            raise KeyError(f"研报不存在：{report_id}")
        chunks = self.storage.retrieve(report_id, question, limit=8)
        citations = []
        context_blocks = []
        for index, chunk in enumerate(chunks, 1):
            citation = {
                "id": f"C{index}",
                "source_id": chunk.get("source_id"),
                "title": chunk["source_title"],
            }
            citations.append(citation)
            context_blocks.append(f"[C{index}] {chunk['source_title']}\n{chunk['content']}")
        history = self.storage.recent_messages(report_id)
        if self.llm.available:
            try:
                answer = self.llm.complete(
                    """你是研报问答助手。仅依据给定上下文回答，关键结论标注 [C1] 形式引用。
若资料不足，直接说明。区分研报原文、外部证据与推断。""",
                    f"研报：{report.title}\n历史对话：{history}\n问题：{question}\n\n"
                    + "\n\n".join(context_blocks),
                    temperature=0.1,
                    max_tokens=1800,
                )
            except Exception as exc:
                answer = f"模型问答失败（{type(exc).__name__}），以下是相关原文片段：\n\n" + "\n\n".join(
                    f"[C{index}] {chunk['content'][:500]}"
                    for index, chunk in enumerate(chunks, 1)
                )
        else:
            answer = "未配置模型，以下是与问题最相关的原文片段：\n\n" + "\n\n".join(
                f"[C{index}] {chunk['content'][:500]}" for index, chunk in enumerate(chunks, 1)
            )
        self.storage.add_message(report_id, "user", question)
        self.storage.add_message(report_id, "assistant", answer, citations)
        return ChatResponse(answer=answer, citations=citations)

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

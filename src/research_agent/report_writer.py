from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Callable

from .config import Settings
from .exceptions import ResearchCancelled
from .llm import LLMClient
from .models import ReportChapter, ResearchPlan, SourceDocument
from .text import chunk_text, query_terms


MODE_LIMITS = {
    "quick": {"chapters": 6, "max_chars": 15_000},
    "standard": {"chapters": 8, "max_chars": 25_000},
    "deep": {"chapters": 10, "max_chars": 45_000},
}
logger = logging.getLogger(__name__)


class ProfessionalReportWriter:
    def __init__(
        self,
        config: Settings,
        llm: LLMClient,
        is_cancelled: Callable[[], bool] | None = None,
    ):
        self.config = config
        self.llm = llm
        self.is_cancelled = is_cancelled or (lambda: False)

    def _check_cancelled(self) -> None:
        if self.is_cancelled():
            raise ResearchCancelled("研报生成已取消")

    def write(
        self,
        topic: str,
        plan: ResearchPlan,
        sources: list[SourceDocument],
        citations: list[dict[str, Any]],
        evidence_packets: list[str] | None = None,
    ) -> tuple[str, list[str]]:
        self._check_cancelled()
        packets = evidence_packets or [
            self._build_evidence_packet(chapter, sources) for chapter in plan.chapters
        ]
        chapters, warnings = self._write_chapters(plan, packets)
        self._check_cancelled()
        report = self._assemble(topic, plan, chapters, citations)
        warnings.extend(self.validate(report, plan, citations))
        return report.replace("\ufeff", "").replace("\ufffd", ""), list(dict.fromkeys(warnings))

    def _write_chapters(
        self, plan: ResearchPlan, packets: list[str]
    ) -> tuple[list[str], list[str]]:
        if not self.llm.available:
            chapters = []
            for index, chapter in enumerate(plan.chapters, 1):
                self._check_cancelled()
                chapters.append(self._fallback_chapter(chapter, packets[index - 1]))
            return chapters, ["LLM 未配置，全部章节使用证据摘要模式"]

        results: dict[int, str] = {}
        warnings: list[str] = []
        workers = max(1, min(self.config.report_writer_workers, len(plan.chapters)))
        executor = ThreadPoolExecutor(max_workers=workers)
        cancelled = False
        try:
            futures = {
                executor.submit(
                    self._write_one_chapter,
                    index,
                    len(plan.chapters),
                    chapter,
                    packets[index - 1],
                    plan,
                ): (index, chapter)
                for index, chapter in enumerate(plan.chapters, 1)
            }
            for future in as_completed(futures):
                if self.is_cancelled():
                    cancelled = True
                    for pending in futures:
                        pending.cancel()
                    raise ResearchCancelled("研报生成已取消")
                index, chapter = futures[future]
                try:
                    content, rewritten = future.result()
                    results[index] = self._normalize_chapter(chapter, content)
                    if rewritten:
                        warnings.append(f"第 {index} 章首次无引用，已重写一次")
                except ResearchCancelled:
                    cancelled = True
                    raise
                except Exception as exc:
                    results[index] = self._fallback_chapter(chapter, packets[index - 1])
                    warnings.append(f"第 {index} 章模型失败，已降级：{type(exc).__name__}")
        finally:
            executor.shutdown(wait=not cancelled, cancel_futures=True)
        return [results[index] for index in range(1, len(plan.chapters) + 1)], warnings

    def _write_one_chapter(
        self,
        index: int,
        total: int,
        chapter: ReportChapter,
        evidence: str,
        plan: ResearchPlan,
    ) -> tuple[str, bool]:
        self._check_cancelled()
        content = self._request_chapter(index, total, chapter, evidence, plan, strict=False)
        self._check_cancelled()
        if re.search(r"\[S\d+\]", content):
            return content, False
        logger.warning("章节无引用，执行一次严格重写 chapter=%d title=%r", index, chapter.title)
        content = self._request_chapter(index, total, chapter, evidence, plan, strict=True)
        self._check_cancelled()
        return content, True

    def _request_chapter(
        self,
        index: int,
        total: int,
        chapter: ReportChapter,
        evidence: str,
        plan: ResearchPlan,
        strict: bool,
    ) -> str:
        per_chapter_chars = MODE_LIMITS[plan.depth_mode]["max_chars"] // max(total, 1)
        strict_requirement = (
            "上一次输出完全没有来源引用。本次每一段包含数字或可核查事实时，都必须紧跟证据池中真实存在的 [Sx]；若没有证据，明确写资料未覆盖。"
            if strict
            else ""
        )
        return self.llm.complete(
            """你是严谨的证券研究员。只使用证据池，不得编造数字、事实或来源。
数字和可核查事实后标注证据池中存在的 [S1] 形式引用。
必须区分已公布的实际数据、机构预期和作者设置的情景假设。
第一行用 Markdown 引用块 > 给出核心判断，之后依次写事实、因果分析和判断。
必须包含反方观点或使本章结论失效的条件。不要重复章节标题。只输出章节正文。""",
            f"""报告：{plan.title}
章节序号：{index}/{total}
章节标题：{chapter.title}
写作重点：{chapter.focus}
目标篇幅：约 {per_chapter_chars} 字符；证据不足时不要凑字数。
{strict_requirement}

证据池：
{evidence[:12000]}""",
            temperature=0.1 if strict else 0.15,
            max_tokens=max(1200, min(3200, per_chapter_chars // 2)),
        )

    def _build_evidence_packet(
        self, chapter: ReportChapter, sources: list[SourceDocument]
    ) -> str:
        terms = query_terms(f"{chapter.title} {chapter.focus}")
        candidates: list[tuple[int, int, str]] = []
        for source_index, source in enumerate(sources, 1):
            for chunk in chunk_text(source.content, 1800, 120):
                lowered = chunk.lower()
                score = sum(min(lowered.count(term.lower()), 3) for term in terms if term)
                candidates.append((score, source_index, chunk))
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = [item for item in candidates if item[0] > 0][:8] or candidates[:5]
        return "\n\n".join(
            f"[S{source_index}] {sources[source_index - 1].title}\n"
            f"URL：{sources[source_index - 1].url or '本地资料'}\n{chunk}"
            for _, source_index, chunk in selected
        ) or "本章没有可用证据。"

    @staticmethod
    def _fallback_chapter(chapter: ReportChapter, evidence: str) -> str:
        return (
            f"> **核心判断**：{chapter.focus}\n\n"
            "以下仅整理证据池原文，不进行证据之外的推断。\n\n"
            f"{evidence}\n\n"
            "**反方观点与判断边界**：现有证据可能存在样本、时间和统计口径限制；缺少交叉来源时，不应形成确定性判断。"
        )

    @staticmethod
    def _normalize_chapter(chapter: ReportChapter, content: str) -> str:
        content = content.strip().lstrip("\ufeff")
        content = re.sub(r"^#{1,3}\s+[^\n]+\n+", "", content)
        if not content.startswith(">"):
            content = f"> **核心判断**：{chapter.focus}\n\n{content}"
        return content

    @staticmethod
    def _assemble(
        topic: str,
        plan: ResearchPlan,
        chapters: list[str],
        citations: list[dict[str, Any]],
    ) -> str:
        now = datetime.now().astimezone()
        title = plan.title or f"{topic}研究报告"
        toc = "\n".join(
            f"- [{index}. {chapter.title}](#chapter-{index})"
            for index, chapter in enumerate(plan.chapters, 1)
        )
        body = "\n\n".join(
            f'<a id="chapter-{index}"></a>\n\n## {index}. {chapter.title}\n\n'
            + re.sub(
                r"(?<!\[)\[(S\d+)\](?!\])",
                lambda match: f"[[{match.group(1)}]](#ref-{match.group(1).lower()})",
                content,
            )
            for index, (chapter, content) in enumerate(zip(plan.chapters, chapters), 1)
        )
        source_lines = "\n".join(
            f'<a id="ref-{item["id"].lower()}"></a>\n\n'
            + (f'- [{item["id"]}] [{item["title"]}]({item["url"]})'
            if item["url"]
            else f'- [{item["id"]}] {item["title"]}（本地资料）')
            for item in citations
        )
        return f"""# {title}

> **元数据**：生成时间 {now:%Y-%m-%d %H:%M:%S %z} · 数据截至 {plan.data_cutoff or now.strftime('%Y-%m-%d')} · 调研模式 {plan.depth_mode} · 证券代码 {plan.stock_code or '未指定'} · 来源 {len(citations)} 个
>
> **研究问题**：{topic}

## 目录

{toc}

{body}

## 参考来源与证据

{source_lines}

## 免责声明

本报告由自动化研究工具基于公开资料及用户提供材料生成，仅用于信息整理与研究参考，不构成证券研究报告、投资建议、收益承诺或交易依据。数据可能存在滞后、口径差异和抓取误差，任何决策均应以法定披露和独立核验为准。
"""

    @staticmethod
    def validate(report: str, plan: ResearchPlan, citations: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        required = ("# ", "**元数据**", "**研究问题**", "## 目录", "## 参考来源与证据", "## 免责声明")
        for marker in required:
            if marker not in report:
                warnings.append(f"缺少结构：{marker}")
        for index, chapter in enumerate(plan.chapters, 1):
            if f"## {index}. {chapter.title}" not in report:
                warnings.append(f"缺少章节：{index}")
        valid_ids = {item["id"] for item in citations}
        body = report.split("## 参考来源与证据", 1)[0]
        used_ids = set(re.findall(r"\[(S\d+)\]", body))
        for invalid in sorted(used_ids - valid_ids):
            warnings.append(f"引用不存在：[{invalid}]")
        for index, block in enumerate(re.split(r"\n## \d+\. ", body)[1:], 1):
            if not re.search(r"\[S\d+\]", block):
                warnings.append(f"第 {index} 章重写后仍无引用")
        if "\ufffd" in report:
            warnings.append("报告包含编码替换字符")
        return warnings

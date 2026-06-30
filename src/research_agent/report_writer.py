from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any

from .config import Settings
from .llm import LLMClient
from .models import ReportChapter, ResearchPlan, SourceDocument
from .text import chunk_text, query_terms


MODE_LIMITS = {
    "quick": {"chapters": 6, "max_chars": 15_000, "min_paragraphs": 4},
    "standard": {"chapters": 8, "max_chars": 25_000, "min_paragraphs": 5},
    "deep": {"chapters": 10, "max_chars": 45_000, "min_paragraphs": 6},
}
CHINESE_NUMERALS = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]
FORBIDDEN_FILLERS = ("近年来", "值得注意的是", "综上所述", "总而言之")


class ProfessionalReportWriter:
    """Evidence-bounded, chapter-based report writer inspired by deep-research."""

    def __init__(self, config: Settings, llm: LLMClient):
        self.config = config
        self.llm = llm

    def write(
        self,
        topic: str,
        plan: ResearchPlan,
        sources: list[SourceDocument],
        citations: list[dict[str, Any]],
    ) -> str:
        evidence_packets = [
            self._build_evidence_packet(chapter, sources) for chapter in plan.chapters
        ]
        chapters = self._write_chapters(plan, evidence_packets)
        report = self._assemble(topic, plan, chapters, citations)
        return self._repair_mechanical_issues(report, plan, citations)

    def _write_chapters(
        self, plan: ResearchPlan, evidence_packets: list[str]
    ) -> list[str]:
        if not self.llm.available:
            return [
                self._fallback_chapter(index, chapter, evidence_packets[index - 1])
                for index, chapter in enumerate(plan.chapters, 1)
            ]
        results: dict[int, str] = {}
        workers = max(1, min(self.config.report_writer_workers, len(plan.chapters)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._write_one_chapter,
                    index,
                    len(plan.chapters),
                    chapter,
                    evidence_packets[index - 1],
                    plan,
                ): (index, chapter)
                for index, chapter in enumerate(plan.chapters, 1)
            }
            for future in as_completed(futures):
                index, chapter = futures[future]
                try:
                    normalized = self._normalize_chapter(index, chapter, future.result())
                    if not self._chapter_is_valid(index, chapter, normalized):
                        raise ValueError("章节结构或引用不完整")
                    results[index] = normalized
                except Exception as exc:
                    results[index] = self._fallback_chapter(
                        index,
                        chapter,
                        evidence_packets[index - 1],
                        note=f"本章模型生成失败（{type(exc).__name__}），已自动降级为证据摘要版。",
                    )
        return [results[index] for index in range(1, len(plan.chapters) + 1)]

    def _write_one_chapter(
        self,
        index: int,
        total: int,
        chapter: ReportChapter,
        evidence: str,
        plan: ResearchPlan,
    ) -> str:
        limits = MODE_LIMITS[plan.depth_mode]
        per_chapter_chars = limits["max_chars"] // max(total, 1)
        sections = "\n".join(f"- {index}.{i} {title}" for i, title in enumerate(chapter.sections, 1))
        return self.llm.complete(
            """你是券商研究员兼严谨编辑。只依据证据包写一章中文研报，不得使用证据包外的数据。
写作必须遵循：结论先行；事实层→因果层→判断层；预测值明确写预计/预测；矛盾数据并排呈现；
关键事实使用证据包内的 [S1] 形式引用；不用“近年来、值得注意的是、综上所述、总而言之”等套话；
不作收益承诺，不使用 LaTeX。输出仅包含本章正文，不写章级标题。""",
            f"""报告：{plan.title or plan.topic}
章节：{chapter.title}（第 {index}/{total} 章）
本章核心判断：{chapter.description}
严格使用以下子节，不增减：
{sections}

要求：
1. 第一行必须是以 > 开头的本章核心判断。
2. 子节标题格式必须为 ### {index}.x 标题，并且标题本身包含判断。
3. 每个子节依次写明结论、证据、因果机制、限定条件或反方视角。
4. 全章至少 {limits['min_paragraphs']} 个实质段落；数据适合对比时使用 Markdown 表格并解释口径。
5. 目标篇幅约 {per_chapter_chars} 个中文字符，但证据不足时明确写“公开资料未充分覆盖”，不得凑字数。
6. 写完后静默自检：数字有引用、预测有措辞、引用编号均存在于证据包。

证据包：
{evidence[:12000]}""",
            temperature=0.15,
            max_tokens=max(1200, min(3200, per_chapter_chars // 2)),
        )

    def _build_evidence_packet(
        self, chapter: ReportChapter, sources: list[SourceDocument]
    ) -> str:
        query = " ".join(
            [chapter.title, chapter.description, *chapter.sections]
            + [item.question for item in chapter.sub_questions]
            + [keyword for item in chapter.sub_questions for keyword in item.search_keywords]
        )
        terms = query_terms(query)
        candidates: list[tuple[int, int, str]] = []
        for source_index, source in enumerate(sources, 1):
            for chunk in chunk_text(source.content, 1800, 120):
                lowered = chunk.lower()
                score = sum(min(lowered.count(term.lower()), 3) for term in terms if term)
                candidates.append((score, source_index, chunk))
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected = [item for item in candidates if item[0] > 0][:8] or candidates[:5]
        blocks = []
        for _, source_index, chunk in selected:
            source = sources[source_index - 1]
            data_type = source.metadata.get("data_type", "unknown")
            blocks.append(
                f"[S{source_index}] {source.title}\n"
                f"来源类型：{source.source_type}；数据属性：{data_type}；URL：{source.url or '本地资料'}\n"
                f"{chunk}"
            )
        return "\n\n".join(blocks) or "公开资料未充分覆盖本章问题。"

    def _fallback_chapter(
        self,
        index: int,
        chapter: ReportChapter,
        evidence: str,
        note: str = "模型未启用，本章展示与研究问题最相关的证据摘要。",
    ) -> str:
        sections = chapter.sections or ["证据概览", "判断边界"]
        excerpts = evidence.split("\n\n")
        body = [f"> **核心判断**：{chapter.description}", "", f"> {note}"]
        for section_index, title in enumerate(sections, 1):
            excerpt = excerpts[(section_index - 1) % len(excerpts)] if excerpts else "公开资料未充分覆盖。"
            body.extend(
                [
                    "",
                    f"### {index}.{section_index} {title}：现有证据给出有限但可追溯的判断",
                    "",
                    excerpt,
                    "",
                    "现有材料可以支持事实层整理，但因果关系与前瞻判断仍需更多交叉来源验证。",
                ]
            )
        return "\n".join(body).strip()

    @staticmethod
    def _normalize_chapter(index: int, chapter: ReportChapter, content: str) -> str:
        content = content.strip().lstrip("\ufeff")
        content = re.sub(rf"^##\s+(?:{CHINESE_NUMERALS[index - 1]}、)?[^\n]+\n+", "", content)
        if not content.startswith(">"):
            content = f"> **核心判断**：{chapter.description}\n\n{content}"
        return content

    @staticmethod
    def _chapter_is_valid(index: int, chapter: ReportChapter, content: str) -> bool:
        if len(content) < 300 or not content.startswith(">"):
            return False
        if any(f"### {index}.{section_index}" not in content for section_index in range(1, len(chapter.sections) + 1)):
            return False
        return bool(re.search(r"\[S\d+\]", content))

    def _assemble(
        self,
        topic: str,
        plan: ResearchPlan,
        chapters: list[str],
        citations: list[dict[str, Any]],
    ) -> str:
        now = datetime.now().astimezone()
        title = plan.title or f"{topic}研究报告"
        chapter_blocks = []
        toc = []
        for index, (chapter, content) in enumerate(zip(plan.chapters, chapters), 1):
            numeral = CHINESE_NUMERALS[index - 1]
            toc.append(f"- [{numeral}、{chapter.title}](#chapter-{index})")
            chapter_blocks.append(
                f'<a id="chapter-{index}"></a>\n\n## {numeral}、{chapter.title}\n\n{content}'
            )
        source_names = "、".join(item["title"] for item in citations[:3]) or "无"
        sources = "\n".join(
            f'<a id="ref-{item["id"].lower()}"></a>\n\n'
            + (
                f'- [{item["id"]}] [{item["title"]}]({item["url"]})'
                if item["url"]
                else f'- [{item["id"]}] {item["title"]}（本地资料）'
            )
            for item in citations
        )
        body = "\n\n".join(chapter_blocks)
        draft = f"""# {title}

> **元数据**：总字数 {{word_count}} · 阅读时间 {{reading_minutes}} 分钟 · 数据截至 {now:%Y-%m} · 报告生成 {now:%Y-%m-%d %H:%M:%S %z} · 调研模式 {plan.depth_mode} · 写作规范 deep-research v3.0
>
> **参考来源**：{source_names} 等 · 共引用 {len(citations)} 个来源

## 目录

{chr(10).join(toc)}

{body}

## 可信评估

**覆盖情况**：本报告基于 {len(citations)} 个可追溯来源，并按章节检索相关证据。引用表示材料支持，不等于观点已获独立验证。

**判断边界**：公开资料未覆盖、口径冲突或仅有预测值的部分，正文应明确使用限定性措辞；投资者应复核公司公告、监管披露和原始财务数据。

## 参考来源

{sources}

## 免责声明

本报告由自动化研究工具基于公开资料及用户提供材料生成，仅用于信息整理与研究参考，不构成证券研究报告、投资建议、收益承诺或交易依据。数据可能存在滞后、口径差异和抓取误差，任何决策均应以法定披露和独立核验为准。

---

报告生成时间：{now:%Y-%m-%d %H:%M:%S %z}
"""
        word_count = len(re.sub(r"\s+", "", draft))
        reading_minutes = max(1, round(word_count / 500))
        return draft.replace("{word_count}", str(word_count)).replace(
            "{reading_minutes}", str(reading_minutes)
        )

    @staticmethod
    def validate(report: str, plan: ResearchPlan, citations: list[dict[str, Any]]) -> list[str]:
        issues = []
        if not report.startswith("# "):
            issues.append("missing_title")
        for marker in ("**元数据**", "## 目录", "## 可信评估", "## 参考来源", "## 免责声明"):
            if marker not in report:
                issues.append(f"missing:{marker}")
        if report.count("## 目录") != 1:
            issues.append("toc_count")
        for index, chapter in enumerate(plan.chapters, 1):
            if f'<a id="chapter-{index}"></a>' not in report:
                issues.append(f"missing_chapter:{index}")
            chapter_start = report.find(f'<a id="chapter-{index}"></a>')
            next_start = report.find(f'<a id="chapter-{index + 1}"></a>')
            chapter_text = report[chapter_start : next_start if next_start > 0 else None]
            if not re.search(r"\n>\s+", chapter_text):
                issues.append(f"missing_chapter_judgement:{index}")
        valid_ids = {item["id"] for item in citations}
        body = report.split("## 参考来源", 1)[0]
        used_ids = set(re.findall(r"(?:\[|\[\()(S\d+)(?:\]|\)\])", body))
        if used_ids - valid_ids:
            issues.append("invalid_citations")
        if citations and not used_ids:
            issues.append("no_body_citations")
        if any(filler in report for filler in FORBIDDEN_FILLERS):
            issues.append("filler_language")
        if "\ufffd" in report:
            issues.append("encoding")
        return issues

    def _repair_mechanical_issues(
        self, report: str, plan: ResearchPlan, citations: list[dict[str, Any]]
    ) -> str:
        valid_ids = {item["id"] for item in citations}
        report = re.sub(
            r"\[(S\d+)\]",
            lambda match: match.group(0) if match.group(1) in valid_ids else "[来源待核验]",
            report,
        )
        body, separator, tail = report.partition("## 参考来源")
        body = re.sub(
            r"\[(S\d+)\]",
            lambda match: f"[({match.group(1)})](#ref-{match.group(1).lower()})",
            body,
        )
        report = body + separator + tail
        replacements = {
            "近年来": "过去数年",
            "值得注意的是": "",
            "综上所述": "据此",
            "总而言之": "据此",
        }
        for original, replacement in replacements.items():
            report = report.replace(original, replacement)
        report = re.sub(r"(?<!\\)\$", r"\\$", report)
        report = report.replace("\ufeff", "").replace("\ufffd", "")
        return report

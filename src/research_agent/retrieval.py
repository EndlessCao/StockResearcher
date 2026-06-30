from __future__ import annotations

import hashlib
import logging
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import chromadb
import httpx

from .config import Settings
from .models import ReportChapter, SourceDocument
from .text import chunk_text


logger = logging.getLogger(__name__)


def _endpoint(base_url: str, resource: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith(f"/{resource}"):
        return base
    if base.endswith("/v1"):
        return f"{base}/{resource}"
    return f"{base}/v1/{resource}"


def _tokens(text: str) -> list[str]:
    latin = re.findall(r"[a-zA-Z0-9_.%-]{2,}", text.lower())
    chinese_groups = re.findall(r"[\u4e00-\u9fff]+", text)
    chinese = [group[i : i + 2] for group in chinese_groups for i in range(len(group) - 1)]
    return latin + chinese


def _parse_timestamp(value: Any, fallback: float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except ValueError:
            match = re.search(r"(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", text)
            if match:
                return datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3) or 1),
                    tzinfo=timezone.utc,
                ).timestamp()
    return fallback


def _semantic_source_type(source: SourceDocument) -> str:
    configured = source.metadata.get("document_type") or source.metadata.get("source_type")
    if configured in {"annual_report", "quarterly_report", "announcement", "research", "news", "market_data"}:
        return str(configured)
    text = f"{source.title} {source.url}".lower()
    if any(word in text for word in ("年报", "annual report", "10-k", "20-f")):
        return "annual_report"
    if any(word in text for word in ("季报", "季度报告", "quarterly", "10-q")):
        return "quarterly_report"
    if any(word in text for word in ("公告", "announcement", "filing")):
        return "announcement"
    news_domains = (
        "reuters.com", "bloomberg.com", "finance.yahoo.com", "36kr.com",
        "thepaper.cn", "huxiu.com",
    )
    if any(domain in text for domain in news_domains):
        return "news"
    if source.source_type == "financial_api":
        return "market_data"
    return "research"


class EmbeddingClient:
    def __init__(self, config: Settings):
        self.config = config

    @property
    def remote_enabled(self) -> bool:
        return bool(
            self.config.embedding_api_key
            and self.config.embedding_base_url
            and self.config.embedding_model
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.remote_enabled:
            return [self._hash_embedding(text) for text in texts]
        response = httpx.post(
            _endpoint(self.config.embedding_base_url, "embeddings"),
            headers={"Authorization": f"Bearer {self.config.embedding_api_key}"},
            json={"model": self.config.embedding_model, "input": texts, "encoding_format": "float"},
            timeout=self.config.llm_timeout,
        )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda item: item["index"])
        return [row["embedding"] for row in rows]

    @staticmethod
    def _hash_embedding(text: str, dimensions: int = 256) -> list[float]:
        vector = [0.0] * dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            vector[index] += 1.0 if digest[4] % 2 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class RerankClient:
    def __init__(self, config: Settings):
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.rerank_api_key and self.config.rerank_base_url and self.config.rerank_model)

    def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        if not documents:
            return []
        if not self.enabled:
            return [(index, 0.0) for index in range(len(documents))]
        response = httpx.post(
            _endpoint(self.config.rerank_base_url, "rerank"),
            headers={"Authorization": f"Bearer {self.config.rerank_api_key}"},
            json={
                "model": self.config.rerank_model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
                "return_documents": False,
            },
            timeout=self.config.llm_timeout,
        )
        response.raise_for_status()
        return [
            (int(item["index"]), float(item["relevance_score"]))
            for item in response.json().get("results", [])
        ]


@dataclass
class Candidate:
    id: str
    text: str
    metadata: dict[str, Any]
    vector_score: float = 0.0
    lexical_score: float = 0.0
    fusion_score: float = 0.0
    final_score: float = 0.0
    query_hits: set[int] = field(default_factory=set)
    query_scores: dict[int, float] = field(default_factory=dict)

class ChromaHybridRetriever:
    def __init__(self, config: Settings):
        self.config = config
        self.embedding = EmbeddingClient(config)
        self.reranker = RerankClient(config)
        model_key = config.embedding_model if self.embedding.remote_enabled else "hash-256"
        suffix = hashlib.sha256(model_key.encode()).hexdigest()[:10]
        client = chromadb.PersistentClient(path=str(config.chroma_path))
        self.collection = client.get_or_create_collection(
            name=f"source_documents_{suffix}", metadata={"hnsw:space": "cosine"}
        )

    @staticmethod
    def chapter_questions(topic: str, chapter: ReportChapter) -> list[str]:
        focus = chapter.focus.rstrip("。")
        if "财务" in chapter.title:
            return [
                f"{topic}最近三年营业收入和归母净利润",
                f"{topic}毛利率和经营现金流变化",
                f"{topic}收入增长放缓或加速原因",
                f"{topic}财务风险和反方观点",
            ]
        return [
            f"{topic}{chapter.title}的最新事实、数据和具体案例",
            f"{topic}{chapter.title}的变化趋势与关键指标",
            f"{topic}{chapter.title}背后的原因和影响机制",
            f"{topic}{chapter.title}的风险、争议和反方观点",
        ]

    def index_documents(
        self,
        task_id: str,
        sources: list[SourceDocument],
        stock_code: str | None,
        citation_ids: dict[str, str],
    ) -> int:
        now = datetime.now(timezone.utc).timestamp()
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for source in sources:
            published_value = source.metadata.get("published_at") or source.title
            published_known = bool(
                source.metadata.get("published_at")
                or re.search(r"20\d{2}", source.title)
            )
            published_ts = _parse_timestamp(published_value, now)
            source_type = _semantic_source_type(source)
            domain = urlparse(source.url).netloc or "local"
            for chunk_index, chunk in enumerate(
                chunk_text(source.content, self.config.chunk_size, self.config.chunk_overlap)
            ):
                ids.append(f"{task_id}:{source.id}:{chunk_index}")
                documents.append(chunk)
                metadatas.append(
                    {
                        "task_id": task_id,
                        "source_id": source.id,
                        "document_id": source.id,
                        "citation_id": citation_ids[source.id],
                        "title": source.title,
                        "url": source.url,
                        "domain": domain,
                        "stock_code": stock_code or "",
                        "published_at": datetime.fromtimestamp(published_ts, timezone.utc).date().isoformat(),
                        "published_ts": published_ts,
                        "published_known": published_known,
                        "source_type": source_type,
                        "source_reliability": str(source.metadata.get("source_reliability", "unknown")),
                        "chunk_index": chunk_index,
                    }
                )
        if not documents:
            return 0
        for start in range(0, len(documents), 32):
            batch_documents = documents[start : start + 32]
            self.collection.upsert(
                ids=ids[start : start + 32],
                documents=batch_documents,
                metadatas=metadatas[start : start + 32],
                embeddings=self.embedding.embed(batch_documents),
            )
        logger.info("Chroma 索引完成 task_id=%s chunks=%d", task_id, len(documents))
        return len(documents)

    def retrieve_chapter(
        self,
        task_id: str,
        chapter: ReportChapter,
        stock_code: str | None,
        data_cutoff: str,
        source_types: list[str],
    ) -> tuple[str, list[dict[str, Any]]]:
        return self._retrieve_questions(
            task_id,
            chapter.retrieval_questions,
            stock_code,
            data_cutoff,
            source_types,
        )

    def retrieve_query(
        self,
        task_id: str,
        query: str,
        stock_code: str | None,
        data_cutoff: str,
        source_types: list[str],
    ) -> tuple[str, list[dict[str, Any]]]:
        return self._retrieve_questions(
            task_id,
            [query, f"{query} 支持证据", f"{query} 风险 反方观点"],
            stock_code,
            data_cutoff,
            source_types,
        )

    def _retrieve_questions(
        self,
        task_id: str,
        questions: list[str],
        stock_code: str | None,
        data_cutoff: str,
        source_types: list[str],
    ) -> tuple[str, list[dict[str, Any]]]:
        cutoff_dt = datetime.fromisoformat(data_cutoff).replace(tzinfo=timezone.utc)
        cutoff_ts = cutoff_dt.replace(hour=23, minute=59, second=59).timestamp()
        where = self._where(task_id, stock_code, cutoff_ts, source_types)
        candidates: dict[str, Candidate] = {}
        all_rows = self.collection.get(where=where, include=["documents", "metadatas"])
        if not all_rows["ids"]:
            return "本章没有满足元数据过滤条件的证据。", []
        query_embeddings = self.embedding.embed(questions)
        per_query = min(
            len(all_rows["ids"]),
            max(8, self.config.retrieval_candidates // max(len(questions), 1)),
        )
        for query_index, embedding in enumerate(query_embeddings):
            result = self.collection.query(
                query_embeddings=[embedding],
                n_results=per_query,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
            for item_id, text, metadata, distance in zip(
                result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
            ):
                candidate = candidates.setdefault(item_id, Candidate(item_id, text, metadata))
                similarity = max(0.0, 1.0 - float(distance))
                candidate.vector_score = max(candidate.vector_score, similarity)
                candidate.query_hits.add(query_index)
                candidate.query_scores[query_index] = similarity

        lexical = self._bm25(questions, all_rows["ids"], all_rows["documents"])
        for item_id, score in lexical[: self.config.retrieval_candidates]:
            if item_id not in candidates:
                index = all_rows["ids"].index(item_id)
                candidates[item_id] = Candidate(
                    item_id, all_rows["documents"][index], all_rows["metadatas"][index]
                )
            candidates[item_id].lexical_score = score

        ranked = self._fuse(list(candidates.values()), cutoff_ts)
        ranked = ranked[: self.config.retrieval_candidates]
        if self.reranker.enabled and ranked:
            try:
                reranked = self.reranker.rerank("\n".join(questions), [item.text for item in ranked])
                for index, score in reranked:
                    ranked[index].final_score = 0.3 * ranked[index].fusion_score + 0.7 * score
                ranked.sort(key=lambda item: item.final_score, reverse=True)
            except (httpx.HTTPError, KeyError, ValueError, IndexError) as exc:
                logger.warning("Rerank 调用失败，保留融合排序 error=%s", type(exc).__name__)
        selected = self._diversify(ranked, len(questions) - 1)
        packet = "\n\n".join(
            f"[{item.metadata['citation_id']}] {item.metadata['title']} | "
            f"{item.metadata['source_type']} | {item.metadata['published_at']}\n{item.text}"
            for item in selected
        )
        diagnostics = [
            {
                "chunk_id": item.id,
                "source_id": item.metadata["source_id"],
                "citation_id": item.metadata["citation_id"],
                "title": item.metadata["title"],
                "url": item.metadata["url"],
                "source_type": item.metadata["source_type"],
                "score": round(item.final_score or item.fusion_score, 4),
            }
            for item in selected
        ]
        return packet or "本章没有满足元数据过滤条件的证据。", diagnostics

    @staticmethod
    def _where(
        task_id: str, stock_code: str | None, cutoff_ts: float, source_types: list[str]
    ) -> dict[str, Any]:
        conditions: list[dict[str, Any]] = [
            {"task_id": {"$eq": task_id}},
            {"published_ts": {"$lte": cutoff_ts}},
        ]
        if stock_code:
            conditions.append({"stock_code": {"$eq": stock_code}})
        if source_types:
            conditions.append({"source_type": {"$in": source_types}})
        return {"$and": conditions}

    @staticmethod
    def _bm25(queries: list[str], ids: list[str], documents: list[str]) -> list[tuple[str, float]]:
        if not documents:
            return []
        query_tokens = _tokens(" ".join(queries))
        tokenized = [_tokens(document) for document in documents]
        document_frequency = Counter(token for tokens in tokenized for token in set(tokens))
        average_length = sum(len(tokens) for tokens in tokenized) / len(tokenized) or 1.0
        scores = []
        for item_id, tokens in zip(ids, tokenized):
            counts = Counter(tokens)
            score = 0.0
            for token in query_tokens:
                df = document_frequency.get(token, 0)
                idf = math.log(1 + (len(documents) - df + 0.5) / (df + 0.5))
                frequency = counts.get(token, 0)
                denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
                score += idf * frequency * 2.5 / denominator if denominator else 0.0
            scores.append((item_id, score))
        max_score = max((score for _, score in scores), default=1.0) or 1.0
        return sorted(((item_id, score / max_score) for item_id, score in scores), key=lambda item: item[1], reverse=True)

    def _fuse(self, candidates: list[Candidate], cutoff_ts: float) -> list[Candidate]:
        half_life = max(1, self.config.retrieval_time_half_life_days) * 86400
        for item in candidates:
            age = max(0.0, cutoff_ts - float(item.metadata["published_ts"]))
            time_score = (
                math.exp(-math.log(2) * age / half_life)
                if item.metadata.get("published_known")
                else 0.5
            )
            authority = self._authority(item.metadata)
            item.fusion_score = (
                0.4 * item.vector_score
                + 0.3 * item.lexical_score
                + 0.15 * time_score
                + 0.15 * authority
            )
            item.final_score = item.fusion_score
        return sorted(candidates, key=lambda item: item.fusion_score, reverse=True)

    @staticmethod
    def _authority(metadata: dict[str, Any]) -> float:
        source_type = metadata.get("source_type")
        if source_type in {"annual_report", "quarterly_report", "announcement"}:
            return 1.0
        if metadata.get("source_reliability") == "user":
            return 0.9
        domain = str(metadata.get("domain", ""))
        if domain.endswith((".gov", ".edu", ".org")):
            return 0.9
        return 0.7 if source_type == "research" else 0.4

    def _diversify(self, ranked: list[Candidate], counter_query_index: int) -> list[Candidate]:
        limit = self.config.retrieval_evidence_blocks
        per_document = self.config.retrieval_max_chunks_per_document
        selected: list[Candidate] = []
        counts: defaultdict[str, int] = defaultdict(int)

        counter_candidates = sorted(
            [item for item in ranked if counter_query_index in item.query_hits],
            key=lambda item: item.query_scores.get(counter_query_index, 0.0),
            reverse=True,
        )
        if counter_candidates:
            first = counter_candidates[0]
            selected.append(first)
            counts[first.metadata["document_id"]] += 1
        for item in ranked:
            if item in selected:
                continue
            document_id = item.metadata["document_id"]
            if counts[document_id] >= per_document:
                continue
            selected.append(item)
            counts[document_id] += 1
            if len(selected) >= limit:
                break
        return selected

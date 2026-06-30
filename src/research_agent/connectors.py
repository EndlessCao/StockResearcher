from __future__ import annotations

import hashlib
import io
import json
import logging
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import Settings
from .models import SourceDocument, utc_now
from .text import clean_text


logger = logging.getLogger(__name__)


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


def safe_url(url: str) -> str:
    """Remove query parameters and fragments before writing URLs to logs."""
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


class DocumentConnector:
    extensions = {".md", ".txt", ".csv", ".json", ".pdf"}

    def __init__(self, config: Settings):
        self.config = config

    def load(self, location: str) -> list[SourceDocument]:
        logged_location = (
            safe_url(location)
            if location.startswith(("http://", "https://"))
            else location
        )
        logger.info("资料加载开始 location=%s", logged_location)
        if location.startswith(("http://", "https://")):
            return [self._load_url(location)]
        path = Path(location).expanduser().resolve()
        paths = (
            [item for item in path.rglob("*") if item.suffix.lower() in self.extensions]
            if path.is_dir()
            else [path]
        )
        documents = [self._load_file(item) for item in paths if item.is_file()]
        logger.info("本地资料加载完成 location=%s documents=%d", location, len(documents))
        return documents

    def _load_file(self, path: Path) -> SourceDocument:
        logger.info("本地文件解析开始 path=%s", path)
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            content = path.read_text(encoding="utf-8", errors="ignore")
        document = SourceDocument(
            id=stable_id("file", str(path)),
            source_type=path.suffix.lower().lstrip(".") or "file",
            title=path.name,
            url=path.as_uri(),
            content=clean_text(content)[: self.config.max_document_chars],
            metadata={"path": str(path), "retrieved_at": utc_now(), "source_reliability": "user"},
        )
        logger.info(
            "本地文件解析完成 path=%s type=%s content_chars=%d",
            path,
            document.source_type,
            len(document.content),
        )
        return document

    def _load_url(self, url: str) -> SourceDocument:
        logger.info("网页 API 调用开始 method=GET url=%s", safe_url(url))
        with httpx.Client(timeout=self.config.request_timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "ResearchAgent/0.1"})
            response.raise_for_status()
        logger.info(
            "网页 API 调用完成 method=GET url=%s status=%d bytes=%d",
            safe_url(str(response.url)),
            response.status_code,
            len(response.content),
        )
        content_type = response.headers.get("content-type", "")
        if "pdf" in content_type or urlparse(url).path.lower().endswith(".pdf"):
            reader = PdfReader(io.BytesIO(response.content))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
            title = Path(urlparse(url).path).name or url
            source_type = "pdf"
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                tag.decompose()
            title = soup.title.get_text(" ", strip=True) if soup.title else url
            content = soup.get_text("\n", strip=True)
            source_type = "web"
        document = SourceDocument(
            id=stable_id("web", str(response.url)),
            source_type=source_type,
            title=title,
            url=str(response.url),
            content=clean_text(content)[: self.config.max_document_chars],
            metadata={"retrieved_at": utc_now(), "source_reliability": "external"},
        )
        logger.info(
            "网页正文解析完成 url=%s type=%s content_chars=%d",
            safe_url(document.url),
            document.source_type,
            len(document.content),
        )
        return document


class SearchConnector:
    def __init__(self, config: Settings):
        self.config = config

    @property
    def provider(self) -> str | None:
        if self.config.first_key(self.config.tavily_api_keys):
            return "tavily"
        if self.config.first_key(self.config.brave_api_keys):
            return "brave"
        if self.config.first_key(self.config.serpapi_api_keys):
            return "serpapi"
        return None

    def search(self, queries: Iterable[str], limit: int = 6) -> list[SourceDocument]:
        if not self.provider or limit <= 0:
            logger.info("搜索 API 跳过 provider=%s limit=%d", self.provider, limit)
            return []
        query_list = list(queries)[:4]
        logger.info(
            "搜索阶段开始 provider=%s queries=%d result_limit=%d",
            self.provider,
            len(query_list),
            limit,
        )
        results: list[dict[str, str]] = []
        per_query = max(2, min(5, limit))
        for query in query_list:
            try:
                results.extend(self._search_one(query, per_query))
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                logger.warning(
                    "搜索 API 调用失败 provider=%s query=%r error=%s",
                    self.provider,
                    query,
                    type(exc).__name__,
                )
                continue
        documents: list[SourceDocument] = []
        seen: set[str] = set()
        for result in results:
            url = result.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            snippet = clean_text(result.get("content") or result.get("snippet") or "")
            documents.append(
                SourceDocument(
                    id=stable_id("search", url),
                    source_type="web",
                    title=result.get("title") or url,
                    url=url,
                    content=snippet,
                    metadata={
                        "provider": self.provider,
                        "published_at": result.get("published_at"),
                        "retrieved_at": utc_now(),
                        "source_reliability": "unverified",
                    },
                )
            )
            if len(documents) >= limit:
                break
        logger.info(
            "搜索阶段完成 provider=%s raw_results=%d deduplicated_results=%d",
            self.provider,
            len(results),
            len(documents),
        )
        return documents

    def _search_one(self, query: str, limit: int) -> list[dict[str, str]]:
        timeout = self.config.request_timeout
        logger.info(
            "搜索 API 调用开始 provider=%s query=%r limit=%d", self.provider, query, limit
        )
        if self.provider == "tavily":
            response = httpx.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.config.first_key(self.config.tavily_api_keys),
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": limit,
                    "include_answer": False,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            logger.info(
                "搜索 API 调用完成 provider=tavily status=%d results=%d",
                response.status_code,
                len(results),
            )
            return results
        if self.provider == "brave":
            response = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit},
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self.config.first_key(self.config.brave_api_keys),
                },
                timeout=timeout,
            )
            response.raise_for_status()
            results = response.json().get("web", {}).get("results", [])
            logger.info(
                "搜索 API 调用完成 provider=brave status=%d results=%d",
                response.status_code,
                len(results),
            )
            return results
        response = httpx.get(
            "https://serpapi.com/search.json",
            params={
                "q": query,
                "api_key": self.config.first_key(self.config.serpapi_api_keys),
                "num": limit,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in response.json().get("organic_results", [])
        ]
        logger.info(
            "搜索 API 调用完成 provider=serpapi status=%d results=%d",
            response.status_code,
            len(results),
        )
        return results


class AlpacaConnector:
    """Optional market snapshot connector; failures do not abort research."""

    def __init__(self, config: Settings):
        self.config = config

    def latest_bar(self, symbol: str) -> SourceDocument | None:
        if not (self.config.alpaca_api_key and self.config.alpaca_secret_key):
            logger.info("Alpaca API 调用跳过 symbol=%s reason=not_configured", symbol)
            return None
        logger.info("Alpaca API 调用开始 symbol=%s feed=%s", symbol, self.config.alpaca_data_feed)
        response = httpx.get(
            f"{self.config.alpaca_data_base_url.rstrip('/')}/v2/stocks/{symbol}/bars/latest",
            params={"feed": self.config.alpaca_data_feed},
            headers={
                "APCA-API-KEY-ID": self.config.alpaca_api_key,
                "APCA-API-SECRET-KEY": self.config.alpaca_secret_key,
            },
            timeout=self.config.request_timeout,
        )
        response.raise_for_status()
        payload = response.json()
        logger.info(
            "Alpaca API 调用完成 symbol=%s status=%d", symbol, response.status_code
        )
        return SourceDocument(
            id=stable_id("alpaca", f"{symbol}:{payload}"),
            source_type="financial_api",
            title=f"{symbol} Alpaca 最新行情快照",
            url="",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            metadata={"provider": "alpaca", "symbol": symbol, "retrieved_at": utc_now()},
        )

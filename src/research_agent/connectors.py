from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader

from .config import Settings
from .models import SourceDocument, utc_now
from .text import clean_text


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:16]}"


class DocumentConnector:
    extensions = {".md", ".txt", ".csv", ".json", ".pdf"}

    def __init__(self, config: Settings):
        self.config = config

    def load(self, location: str) -> list[SourceDocument]:
        if location.startswith(("http://", "https://")):
            return [self._load_url(location)]
        path = Path(location).expanduser().resolve()
        paths = (
            [item for item in path.rglob("*") if item.suffix.lower() in self.extensions]
            if path.is_dir()
            else [path]
        )
        return [self._load_file(item) for item in paths if item.is_file()]

    def _load_file(self, path: Path) -> SourceDocument:
        if path.suffix.lower() == ".pdf":
            reader = PdfReader(str(path))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            content = path.read_text(encoding="utf-8", errors="ignore")
        return SourceDocument(
            id=stable_id("file", str(path)),
            source_type=path.suffix.lower().lstrip(".") or "file",
            title=path.name,
            url=path.as_uri(),
            content=clean_text(content)[: self.config.max_document_chars],
            metadata={"path": str(path), "retrieved_at": utc_now(), "source_reliability": "user"},
        )

    def _load_url(self, url: str) -> SourceDocument:
        with httpx.Client(timeout=self.config.request_timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "ResearchAgent/0.1"})
            response.raise_for_status()
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
        return SourceDocument(
            id=stable_id("web", str(response.url)),
            source_type=source_type,
            title=title,
            url=str(response.url),
            content=clean_text(content)[: self.config.max_document_chars],
            metadata={"retrieved_at": utc_now(), "source_reliability": "external"},
        )


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
            return []
        results: list[dict[str, str]] = []
        per_query = max(2, min(5, limit))
        for query in list(queries)[:4]:
            try:
                results.extend(self._search_one(query, per_query))
            except (httpx.HTTPError, KeyError, ValueError):
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
        return documents

    def _search_one(self, query: str, limit: int) -> list[dict[str, str]]:
        timeout = self.config.request_timeout
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
            return response.json().get("results", [])
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
            return response.json().get("web", {}).get("results", [])
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
        return [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in response.json().get("organic_results", [])
        ]


class AlpacaConnector:
    """Optional market snapshot connector; failures do not abort research."""

    def __init__(self, config: Settings):
        self.config = config

    def latest_bar(self, symbol: str) -> SourceDocument | None:
        if not (self.config.alpaca_api_key and self.config.alpaca_secret_key):
            return None
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
        return SourceDocument(
            id=stable_id("alpaca", f"{symbol}:{payload}"),
            source_type="financial_api",
            title=f"{symbol} Alpaca 最新行情快照",
            url="",
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            metadata={"provider": "alpaca", "symbol": symbol, "retrieved_at": utc_now()},
        )


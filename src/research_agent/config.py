from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = ""
    openai_base_url: str | None = None
    openai_model: str = "gpt-4.1-mini"
    litellm_model: str | None = None

    tavily_api_keys: str = ""
    brave_api_keys: str = ""
    serpapi_api_keys: str = ""

    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_data_base_url: str = "https://data.alpaca.markets"
    alpaca_data_feed: str = "iex"

    social_sentiment_api_key: str = ""
    social_sentiment_api_url: str = ""

    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = ""
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = ""

    data_dir: Path = Field(default=Path("data"))
    request_timeout: float = 25.0
    llm_timeout: float = 180.0
    max_document_chars: int = 30_000
    chunk_size: int = 1_200
    chunk_overlap: int = 160
    report_writer_workers: int = 3
    retrieval_candidates: int = 30
    retrieval_evidence_blocks: int = 10
    retrieval_max_chunks_per_document: int = 3
    retrieval_time_half_life_days: int = 365
    chat_tool_rounds: int = 4
    chat_history_messages: int = 10
    chat_report_context_chars: int = 50_000
    chat_search_results: int = 5
    info: str = ""

    @property
    def info_logging_enabled(self) -> bool:
        return self.info.strip().upper() == "DEBUG"

    @property
    def model_name(self) -> str:
        name = self.litellm_model or self.openai_model
        # LITELLM_MODEL is often written as "provider/model". This prototype
        # talks directly to the configured OpenAI-compatible endpoint, whose
        # model parameter normally expects the suffix only.
        if "/" in name and name.split("/", 1)[0] in {"openai", "deepseek"}:
            return name.split("/", 1)[1]
        return name

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @property
    def chroma_path(self) -> Path:
        return self.data_dir / "chroma"

    @staticmethod
    def first_key(value: str) -> str:
        return next((item.strip() for item in value.split(",") if item.strip()), "")

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_path.mkdir(parents=True, exist_ok=True)


settings = Settings()

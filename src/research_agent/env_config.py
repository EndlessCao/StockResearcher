from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path

from dotenv import dotenv_values


ALLOWED_ENV_KEYS = (
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_MODEL",
    "LITELLM_MODEL",
    "TAVILY_API_KEYS",
    "BRAVE_API_KEYS",
    "SERPAPI_API_KEYS",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "ALPACA_DATA_BASE_URL",
    "ALPACA_DATA_FEED",
    "SOCIAL_SENTIMENT_API_KEY",
    "SOCIAL_SENTIMENT_API_URL",
    "EMBEDDING_API_KEY",
    "EMBEDDING_BASE_URL",
    "EMBEDDING_MODEL",
    "RERANK_API_KEY",
    "RERANK_BASE_URL",
    "RERANK_MODEL",
    "INFO",
)


class EnvironmentConfigService:
    assignment_pattern = re.compile(
        r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*="
    )

    def __init__(self, path: Path):
        self.path = path.expanduser().resolve()

    def read(self) -> dict[str, str]:
        parsed = dotenv_values(self.path) if self.path.exists() else {}
        return {key: str(parsed.get(key) or "") for key in ALLOWED_ENV_KEYS}

    def update(self, values: dict[str, str]) -> dict[str, str]:
        unsupported = sorted(set(values) - set(ALLOWED_ENV_KEYS))
        if unsupported:
            raise ValueError(f"不支持的配置项：{', '.join(unsupported)}")

        normalized = {key: str(value) for key, value in values.items()}
        lines = self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []
        output: list[str] = []
        written: set[str] = set()

        for line in lines:
            match = self.assignment_pattern.match(line)
            key = match.group(1) if match else None
            if key not in normalized:
                output.append(line)
                continue
            if key not in written:
                output.append(f"{key}={self._quote(normalized[key])}")
                written.add(key)

        missing = [key for key in ALLOWED_ENV_KEYS if key in normalized and key not in written]
        if missing and output and output[-1].strip():
            output.append("")
        output.extend(f"{key}={self._quote(normalized[key])}" for key in missing)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        original_mode = stat.S_IMODE(self.path.stat().st_mode) if self.path.exists() else 0o600
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                handle.write("\n".join(output).rstrip() + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.chmod(temp_path, original_mode)
            os.replace(temp_path, self.path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()
        return self.read()

    @staticmethod
    def _quote(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'

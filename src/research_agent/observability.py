from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure application logs without exposing request bodies or credentials."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("research_agent").setLevel(numeric_level)
    # Third-party HTTP clients may log full query strings containing API keys.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)

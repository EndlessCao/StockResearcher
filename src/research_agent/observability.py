from __future__ import annotations

import logging


def configure_logging(info_enabled: bool = False) -> None:
    """Enable application INFO logs only when explicitly requested."""
    numeric_level = logging.INFO if info_enabled else logging.WARNING
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

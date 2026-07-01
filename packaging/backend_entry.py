from __future__ import annotations

import argparse

import uvicorn

from research_agent.api import app
from research_agent.config import settings
from research_agent.observability import configure_logging


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Researcher bundled backend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    configure_logging(settings.info_logging_enabled)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

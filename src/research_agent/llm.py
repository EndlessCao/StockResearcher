from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from openai import OpenAI

from .config import Settings


logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: Settings):
        self.config = config
        self.available = bool(config.openai_api_key)
        self.client = (
            OpenAI(
                api_key=config.openai_api_key,
                base_url=config.openai_base_url or None,
                timeout=config.llm_timeout,
                max_retries=0,
            )
            if self.available
            else None
        )

    def complete(
        self, system: str, user: str, temperature: float = 0.2, max_tokens: int = 6000
    ) -> str:
        if not self.client:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        started_at = time.perf_counter()
        logger.info(
            "LLM API 调用开始 model=%s input_chars=%d max_tokens=%d temperature=%.2f",
            self.config.openai_model,
            len(system) + len(user),
            max_tokens,
            temperature,
        )
        try:
            response = self.client.chat.completions.create(
                model=self.config.openai_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except Exception:
            logger.exception(
                "LLM API 调用失败 model=%s elapsed=%.2fs",
                self.config.openai_model,
                time.perf_counter() - started_at,
            )
            raise
        content = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        logger.info(
            "LLM API 调用完成 model=%s elapsed=%.2fs output_chars=%d prompt_tokens=%s completion_tokens=%s",
            self.config.openai_model,
            time.perf_counter() - started_at,
            len(content),
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return content

    def json(self, system: str, user: str) -> dict[str, Any]:
        logger.info("LLM JSON 响应解析开始")
        text = self.complete(system, user, temperature=0)
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("模型未返回 JSON 对象")
        result = json.loads(match.group(0))
        logger.info("LLM JSON 响应解析完成 keys=%s", sorted(result.keys()))
        return result

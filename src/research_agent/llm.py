from __future__ import annotations

import json
import re
from typing import Any

from openai import OpenAI

from .config import Settings


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
        response = self.client.chat.completions.create(
            model=self.config.model_name,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    def json(self, system: str, user: str) -> dict[str, Any]:
        text = self.complete(system, user, temperature=0)
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise ValueError("模型未返回 JSON 对象")
        return json.loads(match.group(0))

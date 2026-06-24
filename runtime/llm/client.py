"""DeepSeek chat client (OpenAI-compatible API)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from runtime.llm.config import LLMSettings, llm_settings

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    pass


class DeepSeekClient:
    def __init__(self, settings: Optional[LLMSettings] = None):
        self.settings = settings or llm_settings()

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        json_mode: bool = False,
    ) -> str:
        if not self.settings.api_key:
            raise LLMClientError("DEEPSEEK_API_KEY is not configured")

        url = f"{self.settings.base_url}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.settings.temperature,
            "max_tokens": max_tokens or self.settings.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self.settings.timeout_seconds) as client:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise LLMClientError(f"DeepSeek API error {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            raise LLMClientError(f"DeepSeek request failed: {exc}") from exc

        try:
            content = data["choices"][0]["message"]["content"]
            return str(content).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(f"Unexpected DeepSeek response: {data}") from exc

    @staticmethod
    def parse_json(text: str) -> Dict[str, Any]:
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        parsed: Dict[str, Any] = json.loads(text)
        return parsed


def get_client() -> DeepSeekClient:
    return DeepSeekClient()

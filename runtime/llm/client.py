"""DeepSeek chat client (OpenAI-compatible API)."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from runtime.llm.config import LLMSettings, llm_settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS = frozenset({429, 502, 503, 504})
_MAX_ATTEMPTS = 3
_INITIAL_BACKOFF_SECONDS = 0.5

_shared_http_client: Optional[httpx.Client] = None
_shared_http_lock = __import__("threading").Lock()


class LLMClientError(Exception):
    pass


def _get_shared_client(timeout_seconds: float) -> httpx.Client:
    """Reuse a single httpx client per process (connection pooling)."""
    global _shared_http_client
    with _shared_http_lock:
        if _shared_http_client is None:
            _shared_http_client = httpx.Client(
                timeout=httpx.Timeout(timeout_seconds, connect=10.0),
            )
        return _shared_http_client


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

        client = _get_shared_client(self.settings.timeout_seconds)
        last_exc: Optional[Exception] = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                    return str(content).strip()
                except (KeyError, IndexError, TypeError) as exc:
                    raise LLMClientError("Unexpected DeepSeek response shape") from exc

            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status in _RETRYABLE_STATUS and attempt < _MAX_ATTEMPTS:
                    backoff = _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "DeepSeek API %s (attempt %d/%d), retry in %.1fs",
                        status, attempt, _MAX_ATTEMPTS, backoff,
                    )
                    time.sleep(backoff)
                    last_exc = exc
                    continue
                detail = exc.response.text[:300]
                raise LLMClientError(
                    f"DeepSeek API error {status}: {detail}"
                ) from exc

            except httpx.RequestError as exc:
                if attempt < _MAX_ATTEMPTS:
                    backoff = _INITIAL_BACKOFF_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "DeepSeek request failed (attempt %d/%d), retry in %.1fs: %s",
                        attempt, _MAX_ATTEMPTS, backoff, exc,
                    )
                    time.sleep(backoff)
                    last_exc = exc
                    continue
                raise LLMClientError(f"DeepSeek request failed: {exc}") from exc

        raise LLMClientError(f"DeepSeek request failed after {_MAX_ATTEMPTS} attempts") from last_exc

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

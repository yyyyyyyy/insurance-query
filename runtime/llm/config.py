"""LLM configuration — loaded from environment variables.

Environment variables are read at first ``llm_settings()`` call (cached).
Set env vars before process start, or call ``clear_llm_settings_cache()``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    api_key: str
    base_url: str
    model: str
    enabled: bool
    intent_enabled: bool
    answer_enabled: bool
    timeout_seconds: float
    max_tokens: int
    temperature: float

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and self.enabled

    @property
    def intent_llm_active(self) -> bool:
        return self.is_configured and self.intent_enabled

    @property
    def answer_llm_active(self) -> bool:
        return self.is_configured and self.answer_enabled


@lru_cache(maxsize=1)
def llm_settings() -> LLMSettings:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    explicit_enabled = _env_bool("LLM_ENABLED", default=False)
    # Auto-enable when API key is present unless LLM_ENABLED=false
    enabled = explicit_enabled or (bool(api_key) and os.environ.get("LLM_ENABLED", "").strip().lower() != "false")

    return LLMSettings(
        provider=os.environ.get("LLM_PROVIDER", "deepseek"),
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        enabled=enabled,
        intent_enabled=_env_bool("LLM_INTENT_ENABLED", default=True),
        answer_enabled=_env_bool("LLM_ANSWER_ENABLED", default=True),
        timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        max_tokens=int(os.environ.get("LLM_MAX_TOKENS", "2048")),
        temperature=float(os.environ.get("LLM_TEMPERATURE", "0.3")),
    )


def clear_llm_settings_cache() -> None:
    """Clear cached LLM settings (for tests or hot env reload)."""
    llm_settings.cache_clear()

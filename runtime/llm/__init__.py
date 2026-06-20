"""LLM plugin layer — optional DeepSeek integration with rule-based fallback."""

from runtime.llm.config import llm_settings
from runtime.llm.plugin import classify_intent_auto, compose_answer_auto, generate_plan_auto

__all__ = [
    "llm_settings",
    "classify_intent_auto",
    "generate_plan_auto",
    "compose_answer_auto",
]

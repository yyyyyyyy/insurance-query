"""LLM-based answer composition grounded in tool outputs and evidence."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from runtime.llm.client import DeepSeekClient, LLMClientError, get_client
from runtime.llm.config import llm_settings

logger = logging.getLogger(__name__)

ANSWER_SYSTEM_PROMPT = """你是专业的保险顾问助手。请根据提供的工具输出和证据回答用户问题。

严格要求：
1. 只能使用提供的 tool_outputs 和 evidence 中的事实，禁止编造
2. 若证据不足，明确说明"根据现有资料无法确定"
3. 使用清晰的中文 Markdown 格式
4. 在文末注明"本回答基于 N 条证据"（N 为证据条数）
5. 不要输出 JSON，直接输出面向用户的回答正文
"""


def _build_answer_context(
    query_text: str,
    intent_type: str,
    tool_outputs: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> str:
    evidence_brief = [
        {
            "source": e.get("source_type", e.get("source", "")),
            "clause": e.get("clause", ""),
            "content": (e.get("content") or "")[:400],
        }
        for e in evidence[:15]
    ]
    return json.dumps(
        {
            "query": query_text,
            "intent": intent_type,
            "tool_outputs": tool_outputs,
            "evidence": evidence_brief,
            "evidence_count": len(evidence),
        },
        ensure_ascii=False,
        indent=2,
    )


def llm_compose_answer(
    query_text: str,
    intent_type: str,
    tool_outputs: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    client: DeepSeekClient | None = None,
) -> str:
    client = client or get_client()
    context = _build_answer_context(query_text, intent_type, tool_outputs, evidence)
    return client.chat(
        [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"请回答以下查询：\n\n{context}"},
        ],
        temperature=0.2,
    )


def _template_answer(query_text, intent_type, tool_outputs, evidence):
    from runtime.engine.engine import _compose_answer
    return _compose_answer(query_text, intent_type, tool_outputs, evidence)


def compose_answer_auto(
    query_text: str,
    intent_type: str,
    tool_outputs: Dict[str, Any],
    evidence: List[Dict[str, Any]],
) -> str:
    settings = llm_settings()
    if not settings.answer_llm_active:
        return _template_answer(query_text, intent_type, tool_outputs, evidence)

    try:
        return llm_compose_answer(query_text, intent_type, tool_outputs, evidence)
    except (LLMClientError, ValueError, TypeError) as exc:
        logger.warning("LLM answer composition failed, using templates: %s", exc)
        return _template_answer(query_text, intent_type, tool_outputs, evidence)

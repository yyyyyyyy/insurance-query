"""LLM-based answer composition grounded in tool outputs and evidence."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

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
    process_result: Optional[Dict[str, Any]] = None,
    rule_evaluation: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
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
            "process_result": process_result,
            "matched_rules": (rule_evaluation or {}).get("top_decisions", []),
            "memory_context": memory_context,
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
    process_result: Optional[Dict[str, Any]] = None,
    rule_evaluation: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
) -> str:
    client = client or get_client()
    context = _build_answer_context(
        query_text, intent_type, tool_outputs, evidence,
        process_result, rule_evaluation, memory_context,
    )
    return client.chat(
        [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": f"请回答以下查询：\n\n{context}"},
        ],
        temperature=0.2,
    )


def _template_answer(
    query_text: str,
    intent_type: str,
    tool_outputs: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    process_result: Optional[Dict[str, Any]] = None,
    rule_evaluation: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Template-based answer composition (self-contained, no cross-file imports)."""
    lines = [f"查询: {query_text}", ""]

    if memory_context:
        prev = memory_context.get("previous_products", [])
        if prev and prev[0] not in query_text:
            lines.append(f"*上下文产品: {', '.join(prev[:2])}*")
            lines.append("")

    if intent_type == "product_comparison":
        comp = tool_outputs.get("compare", {}).get("comparison", {})
        if comp:
            lines.append("## 产品对比结果")
            products = comp.get("products", [])
            if products:
                names = " vs ".join(p["name"] for p in products)
                lines.append(f"对比产品: {names}")
                lines.append("")
            for row in comp.get("rows", []):
                dim = row["dimension"]
                unit = row.get("unit", "")
                vals = []
                for p in (comp.get("products") or []):
                    pid = p["id"]
                    val = row.get(pid)
                    if val is not None:
                        vals.append(f"{p['name']}: {val}{unit}")
                lines.append(f"- **{dim}**: {' | '.join(vals)}")

    elif intent_type == "coverage_question":
        lines.append("## 保障范围查询结果")
        doc_data = tool_outputs.get("document_search", {})
        for chunk in doc_data.get("chunks", []):
            lines.append(f"> [{chunk.get('clause', '')}] {chunk.get('content', '')}")
            lines.append("")

    elif intent_type == "regulation_lookup":
        reg_data = tool_outputs.get("regulation_search", {})
        for reg in reg_data.get("regulations", []):
            lines.append(f"### {reg['title']}")
            for chunk in reg.get("chunks", []):
                lines.append(f"- **{chunk.get('clause', '')}**: {chunk.get('content', '')}")
            lines.append("")

    elif intent_type == "price_inquiry":
        lines.append("## 价格查询")
        prod_data = tool_outputs.get("product_search", {})
        attr_data = tool_outputs.get("attribute_extraction", {}).get("results", {})
        for prod in prod_data.get("products", []):
            attrs = attr_data.get(prod["product_id"], {})
            prem = attrs.get("premium_reference", {})
            lines.append(f"- **{prod['name']}**: 年保费 {prem.get('age_30', 'N/A')}元(30岁), "
                         f"范围 {attrs.get('premium_min', '?')}-{attrs.get('premium_max', '?')}元/年")

    elif intent_type == "claim_process":
        doc_data = tool_outputs.get("document_search", {})
        for chunk in doc_data.get("chunks", []):
            lines.append(chunk.get("content", ""))

    elif intent_type == "eligibility_check":
        lines.append("## 投保资格")
        eligibility_data = tool_outputs.get("eligibility_check", {})
        lines.append(f"结果: {'符合' if eligibility_data.get('eligible') else '不符合'}")
        for reason in eligibility_data.get("reasons", []):
            lines.append(f"- {reason}")

    else:
        lines.append("## 查询结果")
        prod_data = tool_outputs.get("product_search", {})
        for prod in prod_data.get("products", []):
            lines.append(f"- {prod['name']} ({prod.get('product_type','')}) — {prod.get('company','')}")

    if process_result and process_result.get("outcome"):
        lines.append("")
        lines.append("## 流程结论")
        lines.append(process_result.get("outcome", ""))

    matched_rules: List[Dict[str, Any]] = []
    if rule_evaluation:
        matched_rules = rule_evaluation.get("top_decisions", []) or []
    if matched_rules:
        lines.append("")
        lines.append("## 规则判定")
        for r in matched_rules[:5]:
            reason = r.get("reason", r.get("message", r.get("decision", "")))
            lines.append(f"- {reason}")

    if evidence:
        lines.append("")
        lines.append("---")
        lines.append(f"*本回答基于 {len(evidence)} 条证据*")

    return "\n".join(lines)


def _format_citations(evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format evidence into structured citations."""
    citations = []
    seen = set()
    for item in evidence:
        key = str(item.get("document_id") or item.get("product_id") or
                  item.get("chunk_id") or item.get("source", ""))
        if key not in seen:
            seen.add(key)
            citations.append({
                "source": item.get("source_type", item.get("source", "unknown")),
                "reference": key,
                "content": item.get("content", "")[:100],
                "clause": item.get("clause", ""),
            })
    return citations


def _compute_confidence(intent_result: Dict[str, Any], evidence: List[Dict[str, Any]]) -> float:
    """Compute answer confidence from intent confidence and evidence strength.

    Blends three signals:
      - intent classification confidence (40%)
      - evidence count saturation (35%): capped at 5 items
      - mean evidence relevance score (25%): uses ``score``/``relevance``
        fields when present so high-quality but few-item answers are not
        penalized as harshly as pure count-based scoring would.
    """
    intent_conf = intent_result.get("confidence", 0.5)

    if not evidence:
        # No evidence — the answer is essentially ungrounded. Keep the
        # floor at 0.0 so downstream consumers cannot read a hallucinated
        # answer as "the system is somewhat confident".
        return 0.0

    count_factor = min(len(evidence) / 5.0, 1.0)

    # Collect per-item relevance scores (0..1) when available.
    scores = []
    for ev in evidence:
        s = ev.get("score", ev.get("relevance_score"))
        if s is None:
            continue
        try:
            val = float(s)
            if 0.0 <= val <= 1.0:
                scores.append(val)
            elif val > 1.0:
                # BM25-style raw scores; normalize softly.
                scores.append(min(val / 10.0, 1.0))
        except (TypeError, ValueError):
            continue
    score_factor = (sum(scores) / len(scores)) if scores else 0.5

    confidence = intent_conf * 0.4 + count_factor * 0.35 + score_factor * 0.25
    return float(round(max(0.0, min(confidence, 1.0)), 2))


def compose_answer_auto(
    query_text: str,
    intent_type: str,
    tool_outputs: Dict[str, Any],
    evidence: List[Dict[str, Any]],
    process_result: Optional[Dict[str, Any]] = None,
    rule_evaluation: Optional[Dict[str, Any]] = None,
    memory_context: Optional[Dict[str, Any]] = None,
) -> str:
    settings = llm_settings()
    kwargs = {
        "process_result": process_result,
        "rule_evaluation": rule_evaluation,
        "memory_context": memory_context,
    }
    if not settings.answer_llm_active:
        return _template_answer(
            query_text, intent_type, tool_outputs, evidence, **kwargs,
        )

    try:
        return llm_compose_answer(
            query_text,
            intent_type,
            tool_outputs,
            evidence,
            process_result=process_result,
            rule_evaluation=rule_evaluation,
            memory_context=memory_context,
        )
    except (LLMClientError, ValueError, TypeError) as exc:
        logger.warning("LLM answer composition failed, using templates: %s", exc)
        return _template_answer(
            query_text, intent_type, tool_outputs, evidence, **kwargs,
        )

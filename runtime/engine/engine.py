"""
Runtime Engine — Core orchestrator, Sprint 2 (Real Tool Execution).

ARCHITECTURE:
    UserQuery -> Intent -> Plan -> ToolDispatcher -> Real Tools -> Evidence -> Answer

SPRINT 2 CHANGE: Replaced mock execute_tool() with ToolDispatcher + ToolRegistry.
All tools are now real deterministic implementations per 06-Tool-Contracts.md.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from runtime.engine.event_store import (
    EventStore,
    answer_generated_event,
    evidence_found_event,
    intent_classified_event,
    plan_created_event,
    tool_called_event,
    user_query_event,
)
from runtime.llm.plugin import classify_intent_auto, compose_answer_auto, generate_plan_auto
from runtime.engine.reducer import replay_state
from runtime.engine.state import RuntimeState
from runtime.tools.base import ToolResult
from runtime.tools.registry import ToolDispatcher, create_default_registry


class InsureQueryEngine:
    """Core runtime engine for insurance query processing.

    SPRINT 2: Uses ToolDispatcher with real tools instead of mock execute_tool().
    """

    def __init__(self, event_store: Optional[EventStore] = None,
                 dispatcher: Optional[ToolDispatcher] = None):
        self.event_store = event_store or EventStore()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        session_id = session_id or str(uuid.uuid4())
        seq = 0

        seq += 1
        self.event_store.append(user_query_event(session_id, seq, query_text))

        intent_result = classify_intent_auto(query_text)
        seq += 1
        self.event_store.append(intent_classified_event(
            session_id, seq, intent=intent_result["intent"],
            confidence=intent_result["confidence"], entities=intent_result["entities"],
        ))

        plan = generate_plan_auto(query_text, intent_result)
        seq += 1
        self.event_store.append(plan_created_event(
            session_id, seq, plan=plan,
            reasoning=f"Template-based plan for intent: {intent_result['intent']}",
        ))

        all_evidence: List[Dict[str, Any]] = []
        tool_outputs: Dict[str, Any] = {}

        for step in plan:
            tool_name = step["tool_name"]
            params = step.get("input_params", {})
            if "query" not in params:
                params["query"] = query_text

            seq += 1
            self.event_store.append(tool_called_event(
                session_id, seq, tool_name=tool_name, input_params=params,
            ))

            result: ToolResult = self.dispatcher.dispatch(tool_name, params)

            if result.success:
                tool_outputs[tool_name] = result.data
                evidence_dicts = [e.to_dict() for e in result.evidence]
                all_evidence.extend(evidence_dicts)

                seq += 1
                self.event_store.append(evidence_found_event(
                    session_id, seq, tool_name=tool_name,
                    evidence=evidence_dicts, output=result.data,
                    duration_ms=result.duration_ms,
                ))

        answer = self._generate_answer(query_text, intent_result, plan, tool_outputs, all_evidence)

        seq += 1
        self.event_store.append(answer_generated_event(
            session_id, seq, answer=answer["text"],
            citations=answer.get("citations", []),
            confidence=answer.get("confidence"),
        ))

        state = replay_state(self.event_store, session_id)

        return {
            "session_id": session_id,
            "answer": answer,
            "trace": [e.to_dict() for e in self.event_store.get_session_events(session_id)],
            "state": state.to_dict(),
        }

    def _generate_answer(self, query_text, intent_result, plan, tool_outputs, evidence):
        intent_type = intent_result["intent"]
        citations = _format_citations(evidence)
        answer_text = compose_answer_auto(query_text, intent_type, tool_outputs, evidence)
        return {
            "text": answer_text, "citations": citations,
            "confidence": _compute_confidence(intent_result, evidence),
            "intent": intent_type,
            "tools_used": [s["tool_name"] for s in plan],
            "evidence_count": len(evidence),
        }

    def replay_session(self, session_id: str) -> RuntimeState:
        return replay_state(self.event_store, session_id)

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.event_store.get_session_events(session_id)]


def _compose_answer(query_text, intent_type, tool_outputs, evidence):
    lines = [f"查询: {query_text}", ""]

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
            lines.append(f"- {prod['name']} ({prod['product_type']}) — {prod['company']}")

    if evidence:
        lines.append("")
        lines.append("---")
        srcs = set()
        for e in evidence:
            src = e.get("source_type", e.get("source", ""))
            if src:
                srcs.add(src)
        lines.append(f"*本回答基于 {len(evidence)} 条证据*")

    return "\n".join(lines)


def _format_citations(evidence):
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


def _compute_confidence(intent_result, evidence):
    intent_conf = intent_result.get("confidence", 0.5)
    evidence_factor = min(len(evidence) / 5.0, 1.0) if evidence else 0.3
    return round(intent_conf * 0.4 + evidence_factor * 0.6, 2)

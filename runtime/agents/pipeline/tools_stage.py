"""Pipeline stage: tool execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, TYPE_CHECKING

from runtime.engine.event_store import (
    evidence_found_event,
    memory_updated_event,
    tool_called_event,
    tool_executed_event,
)
from runtime.agents.pipeline._helpers import EventSequencer, send_agent

if TYPE_CHECKING:
    from runtime.agents.bus import AgentContext
    from runtime.agents.orchestrator import MultiAgentEngine


@dataclass
class ToolsStageResult:
    tool_data: Dict[str, Any]
    all_evidence: List[Dict[str, Any]]
    tools_attempted: List[str]
    agent_results: Dict[str, Any]


def run_tools_stage(
    engine: "MultiAgentEngine",
    ctx: "AgentContext",
    seq: EventSequencer,
    *,
    trace_id: str,
    resolved_query: str,
    plan: List[Dict[str, Any]],
    retrieval_chunks: List[Dict[str, Any]],
) -> ToolsStageResult:
    resp = send_agent(
        engine, ctx, seq, "tool", "task",
        {
            "plan": plan,
            "query": resolved_query,
            "retrieval_context": retrieval_chunks[:5],
        },
        trace_id,
    )
    agent_results = resp.payload.get("results", {})
    ctx.execution_graph.append({"agent": "tool", "tools": list(agent_results.keys())})

    tool_data: Dict[str, Any] = {}
    all_evidence: List[Dict[str, Any]] = []
    tools_attempted: List[str] = []

    for tname, ar_dict in agent_results.items():
        tools_attempted.append(tname)
        status = ar_dict.get("status", "")
        seq.append(
            tool_called_event,
            tool_name=tname,
            input_params=ar_dict.get("metadata", {}),
        )
        duration = 0.0
        if status == "success" and ar_dict.get("result"):
            r = ar_dict["result"]
            tool_data[tname] = r.get("data", {})
            evidence = r.get("evidence", [])
            all_evidence.extend(evidence)
            duration = r.get("duration_ms", 0)
            seq.append(
                evidence_found_event,
                tool_name=tname,
                evidence=evidence,
                output=r.get("data", {}),
                duration_ms=duration,
            )
        fact_keys = _collect_fact_keys_for_tool(tname, ctx.memory_facts)
        seq.append(
            tool_executed_event,
            tool_name=tname,
            status=status,
            duration_ms=duration,
            fact_keys=fact_keys,
        )

    ctx.tool_results = tool_data
    ctx.evidence = all_evidence

    if ctx.memory_facts:
        seq.append(memory_updated_event, action="write", facts=ctx.memory_facts)

    return ToolsStageResult(
        tool_data=tool_data,
        all_evidence=all_evidence,
        tools_attempted=tools_attempted,
        agent_results=agent_results,
    )


def _collect_fact_keys_for_tool(tname: str, memory_facts: Dict[str, Any]) -> List[str]:
    """Collect fact keys that were written by a specific tool."""
    if not memory_facts:
        return []
    keys = []
    for fkey, fval in memory_facts.items():
        if isinstance(fval, dict) and fval.get("source_tool") == tname:
            keys.append(fkey)
    return keys

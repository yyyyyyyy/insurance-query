"""Pipeline stage: process runner and rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from runtime.engine.event_store import process_executed_event, rule_evaluated_event

if TYPE_CHECKING:
    from runtime.agents.bus import AgentContext
    from runtime.agents.orchestrator import MultiAgentEngine
    from runtime.agents.pipeline._helpers import EventSequencer
    from runtime.process.base import ProcessResult


@dataclass
class ProcessRulesResult:
    process_result: Optional["ProcessResult"]
    rule_eval: Any
    matched: List[Dict[str, Any]]
    intent_type: str


def run_process_rules_stage(
    engine: "MultiAgentEngine",
    ctx: "AgentContext",
    seq: "EventSequencer",
    *,
    session_id: str,
    resolved_query: str,
    intent_type: str,
    tool_data: Dict[str, Any],
    all_evidence: List[Dict[str, Any]],
) -> ProcessRulesResult:
    preliminary_rules = engine._evaluate_rules(
        resolved_query, intent_type, tool_data, all_evidence,
    )
    rule_decisions_pre = [d.to_dict() for d in preliminary_rules.decisions]

    process_result = engine.process_runner.run(
        intent=intent_type,
        tool_results=tool_data,
        rule_decisions=rule_decisions_pre,
        memory_facts=ctx.memory_facts,
        query_text=resolved_query,
    )
    if process_result:
        ctx.process_result = process_result.to_dict()
        seq.append(
            process_executed_event,
            process_name=process_result.process_name,
            path=process_result.path,
            terminal_state=process_result.terminal_state,
            outcome=process_result.outcome,
        )
        if engine.working_memory:
            engine.working_memory.set_active_process(session_id, process_result.process_name)

    rule_eval = preliminary_rules
    ctx.rule_evaluation = rule_eval.to_dict()
    matched = [d.to_dict() for d in rule_eval.decisions if d.matched][:5]
    seq.append(
        rule_evaluated_event,
        rules_evaluated=rule_eval.rules_evaluated,
        rules_matched=rule_eval.rules_matched,
        top_decisions=matched,
        summary=rule_eval.summary,
    )

    return ProcessRulesResult(
        process_result=process_result,
        rule_eval=rule_eval,
        matched=matched,
        intent_type=intent_type,
    )

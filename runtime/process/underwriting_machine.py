"""Underwriting process state machine — simplified executable path."""

from __future__ import annotations

from typing import Any, Dict, List

from runtime.process.base import ProcessContext, ProcessStateMachine
from runtime.process.loader import load_process_graph


class UnderwritingStateMachine(ProcessStateMachine):
    """Simplified underwriting: health → honesty → risk → terminal."""

    def __init__(self, graph: Dict[str, Any] | None = None):
        super().__init__(
            "underwriting_lifecycle",
            graph or load_process_graph("underwriting"),
        )

    def _get_execution_order(self) -> List[str]:
        return [
            "idle",
            "application_submitted",
            "health_declaration",
            "honesty_check",
            "risk_assessment",
        ]

    def evaluate_decision(
        self, decision_id: str, state: str, ctx: ProcessContext
    ) -> bool:
        if decision_id == "D_honesty":
            elig = ctx.tool_results.get("eligibility_check", {})
            if elig:
                return bool(elig.get("eligible", True))
            return True
        if decision_id == "D_risk":
            return ctx.eligibility_passed() and not ctx.has_reject_rule()
        if decision_id == "D_premium":
            attr = ctx.tool_results.get("attribute_extraction", {})
            results = attr.get("results", {}) if isinstance(attr, dict) else {}
            for fields in results.values():
                if isinstance(fields, dict) and (
                    fields.get("premium_reference") or fields.get("premium_min")
                ):
                    return True
            return True
        if decision_id == "D_exclusion_uw":
            return not ctx.has_reject_rule()
        return True

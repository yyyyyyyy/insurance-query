"""Claim process state machine — simplified executable path."""

from __future__ import annotations

from typing import Any, Dict, List

from runtime.process.base import ProcessContext, ProcessStateMachine
from runtime.process.loader import load_process_graph


class ClaimProcessStateMachine(ProcessStateMachine):
    """Simplified claim lifecycle: coverage → liability → exclusion → evaluate → terminal."""

    def __init__(self, graph: Dict[str, Any] | None = None):
        super().__init__(
            "claim_lifecycle",
            graph or load_process_graph("claim"),
        )

    def _get_execution_order(self) -> List[str]:
        return [
            "idle",
            "accident_occurred",
            "claim_reported",
            "coverage_verification",
            "liability_check",
            "exclusion_check",
            "claim_evaluated",
        ]

    def evaluate_decision(
        self, decision_id: str, state: str, ctx: ProcessContext
    ) -> bool:
        if decision_id == "D_coverage":
            # Default yes unless explicit reject in rules
            return not ctx.has_reject_rule()
        if decision_id == "D_liability":
            doc_search = ctx.tool_results.get("document_search", {})
            chunks = doc_search.get("chunks", doc_search.get("results", []))
            return len(chunks) > 0 or not ctx.has_reject_rule()
        if decision_id == "D_exclusion":
            return ctx.has_reject_rule()
        if decision_id == "D_evaluate":
            return not ctx.has_reject_rule()
        if decision_id == "D_docs":
            return True
        return True

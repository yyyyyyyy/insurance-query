"""ProcessRunner — drives state machines based on intent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime.process.base import ProcessContext, ProcessResult
from runtime.process.claim_machine import ClaimProcessStateMachine
from runtime.process.underwriting_machine import UnderwritingStateMachine


class ProcessRunner:
    """Select and execute process state machines by intent."""

    CLAIM_INTENTS = frozenset({"claim_process", "coverage_question"})
    UW_INTENTS = frozenset({"eligibility_check"})

    def __init__(self):
        self.claim_machine = ClaimProcessStateMachine()
        self.underwriting_machine = UnderwritingStateMachine()

    def run(
        self,
        intent: str,
        tool_results: Dict[str, Any],
        rule_decisions: Optional[List[Dict[str, Any]]] = None,
        memory_facts: Optional[Dict[str, Any]] = None,
        query_text: str = "",
    ) -> Optional[ProcessResult]:
        ctx = ProcessContext(
            intent=intent,
            tool_results=tool_results,
            rule_decisions=rule_decisions or [],
            memory_facts=memory_facts or {},
            query_text=query_text,
        )

        if intent in self.CLAIM_INTENTS:
            return self.claim_machine.run_to_terminal(ctx)
        if intent in self.UW_INTENTS:
            return self.underwriting_machine.run_to_terminal(ctx)
        return None

"""Process state machine base — executable insurance business processes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, cast


@dataclass
class ProcessContext:
    """Runtime context passed through state machine decisions."""
    intent: str = ""
    tool_results: Dict[str, Any] = field(default_factory=dict)
    rule_decisions: List[Dict[str, Any]] = field(default_factory=list)
    memory_facts: Dict[str, Any] = field(default_factory=dict)
    query_text: str = ""

    def has_reject_rule(self) -> bool:
        return any(
            d.get("matched") and d.get("decision") in ("reject", "exclusion")
            for d in self.rule_decisions
        )

    def eligibility_passed(self) -> bool:
        elig = self.tool_results.get("eligibility_check", {})
        if elig:
            return bool(elig.get("eligible", True))
        return True


@dataclass
class ProcessResult:
    process_name: str
    path: List[str] = field(default_factory=list)
    terminal_state: str = ""
    decisions: List[Dict[str, Any]] = field(default_factory=list)
    outcome: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_name": self.process_name,
            "path": self.path,
            "terminal_state": self.terminal_state,
            "decisions": self.decisions,
            "outcome": self.outcome,
        }


class ProcessStateMachine(ABC):
    """Base class for executable process state machines."""

    def __init__(self, process_name: str, graph: Dict[str, Any]):
        self.process_name = process_name
        self.graph = graph
        self.initial_state = graph.get("initial_state", "idle")
        self.terminal_states = set(graph.get("terminal_states", []))
        self._transitions = self._index_transitions(graph.get("transitions", []))
        self._decisions = {d["id"]: d for d in graph.get("decisions", [])}

    @staticmethod
    def _index_transitions(transitions: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        idx: Dict[str, List[Dict[str, Any]]] = {}
        for t in transitions:
            idx.setdefault(t["from"], []).append(t)
        return idx

    @abstractmethod
    def evaluate_decision(
        self, decision_id: str, state: str, ctx: ProcessContext
    ) -> bool:
        """Return True for 'yes' branch, False for 'no' branch."""

    def run_to_terminal(self, ctx: ProcessContext) -> ProcessResult:
        """Execute simplified path until a terminal state is reached."""
        current = self.initial_state
        path = [current]
        decisions_log: List[Dict[str, Any]] = []

        # Simplified execution: walk through key states in order
        execution_order = self._get_execution_order()
        for step in execution_order:
            if current in self.terminal_states:
                break
            if step != current:
                current = step
                path.append(current)

            # Check if there's a decision at this state
            decision = self._decision_at_state(current)
            if decision:
                yes = self.evaluate_decision(decision["id"], current, ctx)
                branch = "yes" if yes else "no"
                next_state = decision.get(branch, current)
                decisions_log.append({
                    "decision_id": decision["id"],
                    "state": current,
                    "question": decision.get("question", ""),
                    "branch": branch,
                    "next_state": next_state,
                })
                if next_state != current:
                    current = next_state
                    path.append(current)
                if current in self.terminal_states:
                    break

        outcome = self._outcome_label(current)
        return ProcessResult(
            process_name=self.process_name,
            path=path,
            terminal_state=current,
            decisions=decisions_log,
            outcome=outcome,
        )

    def _decision_at_state(self, state: str) -> Optional[Dict[str, Any]]:
        for d in self._decisions.values():
            if d.get("node") == state:
                return cast(Dict[str, Any], d)
        return None

    @abstractmethod
    def _get_execution_order(self) -> List[str]:
        """Ordered list of states to traverse (simplified sub-path)."""

    def _outcome_label(self, terminal_state: str) -> str:
        for s in self.graph.get("states", []):
            if s.get("id") == terminal_state:
                return str(s.get("label", terminal_state))
        return terminal_state

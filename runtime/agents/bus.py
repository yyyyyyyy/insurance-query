"""Multi-Agent Runtime — AgentBus + 5 specialized agents."""

from __future__ import annotations

import threading
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEGRADED = "degraded"


@dataclass
class AgentMessage:
    msg_id: str
    sender: str
    recipient: str
    msg_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "msg_type": self.msg_type,
            "payload": self.payload,
            "trace_id": self.trace_id,
        }


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
        self.status = AgentStatus.IDLE
        self.execution_count = 0
        self.failure_count = 0
        self._stats_lock = threading.Lock()

    @abstractmethod
    def handle(self, msg: AgentMessage, ctx: "AgentContext") -> AgentMessage:
        ...

    def _set_ctx_status(self, ctx: Optional["AgentContext"], status: AgentStatus) -> None:
        with self._stats_lock:
            self.status = status
        if ctx is not None:
            ctx.agent_statuses[self.name] = status

    def _record_success(self, ctx: Optional["AgentContext"]) -> None:
        with self._stats_lock:
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
        if ctx is not None:
            ctx.agent_statuses[self.name] = AgentStatus.COMPLETED

    def _record_failure(
        self,
        ctx: Optional["AgentContext"],
        status: AgentStatus = AgentStatus.FAILED,
    ) -> None:
        with self._stats_lock:
            self.failure_count += 1
            self.status = status
        if ctx is not None:
            ctx.agent_statuses[self.name] = status

    def status_dict(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                "name": self.name,
                "status": self.status.value,
                "executions": self.execution_count,
                "failures": self.failure_count,
            }


@dataclass
class AgentContext:
    session_id: str
    query: str
    trace_id: str = ""
    intent: Dict[str, Any] = field(default_factory=dict)
    plan: List[Dict[str, Any]] = field(default_factory=list)
    ontology_context: List[str] = field(default_factory=list)
    retrieval_results: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    answer: Dict[str, Any] = field(default_factory=dict)
    evaluation: Dict[str, Any] = field(default_factory=dict)
    agent_statuses: Dict[str, AgentStatus] = field(default_factory=dict)
    execution_graph: List[Dict[str, Any]] = field(default_factory=list)
    failure_recovery_path: List[str] = field(default_factory=list)
    system_health: Dict[str, Any] = field(default_factory=dict)
    cache_state: Dict[str, Any] = field(default_factory=dict)
    degraded_mode: bool = False
    memory_context: Dict[str, Any] = field(default_factory=dict)
    memory_facts: Dict[str, Any] = field(default_factory=dict)
    process_result: Dict[str, Any] = field(default_factory=dict)
    rule_evaluation: Dict[str, Any] = field(default_factory=dict)
    retrieval_weights: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "trace_id": self.trace_id,
            "intent": self.intent,
            "plan": self.plan,
            "execution_graph": self.execution_graph,
            "failure_recovery_path": self.failure_recovery_path,
            "degraded_mode": self.degraded_mode,
        }


class AgentBus:
    MAX_LOG = 1000

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._log: List[AgentMessage] = []
        self._lock = threading.Lock()

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def send(self, msg: AgentMessage, ctx: Optional[AgentContext] = None) -> AgentMessage:
        with self._lock:
            self._log.append(msg)
            if len(self._log) > self.MAX_LOG:
                self._log = self._log[-self.MAX_LOG:]
        agent = self._agents.get(msg.recipient)
        if not agent:
            return AgentMessage(
                str(uuid.uuid4()),
                msg.recipient,
                msg.sender,
                "error",
                {"error": f"Agent not found: {msg.recipient}"},
            )
        active_ctx = ctx or AgentContext(session_id="", query="")
        return agent.handle(msg, active_ctx)

    def get_agent(self, name: str) -> Optional[BaseAgent]:
        return self._agents.get(name)

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def agent_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Last-known agent stats (dashboard); may reflect latest concurrent turn."""
        with self._lock:
            return {name: agent.status_dict() for name, agent in self._agents.items()}

    def agent_statuses_from_context(self, ctx: Optional[AgentContext]) -> Dict[str, Dict[str, Any]]:
        """Per-turn agent statuses merged with cumulative execution counters."""
        with self._lock:
            result: Dict[str, Dict[str, Any]] = {}
            for name, agent in self._agents.items():
                if ctx and name in ctx.agent_statuses:
                    st = ctx.agent_statuses[name]
                    status_val = st.value if isinstance(st, AgentStatus) else str(st)
                else:
                    status_val = agent.status.value
                sd = agent.status_dict()
                result[name] = {
                    "name": name,
                    "status": status_val,
                    "executions": sd["executions"],
                    "failures": sd["failures"],
                }
            return result

    def message_log(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [m.to_dict() for m in self._log]

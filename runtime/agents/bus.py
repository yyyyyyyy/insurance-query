"""Multi-Agent Runtime — AgentBus + 5 specialized agents."""

from __future__ import annotations
import time, uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

class AgentStatus(str, Enum):
    IDLE="idle"; RUNNING="running"; COMPLETED="completed"
    FAILED="failed"; DEGRADED="degraded"

@dataclass
class AgentMessage:
    msg_id: str; sender: str; recipient: str; msg_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    trace_id: str = ""
    def to_dict(self): return {"msg_id":self.msg_id,"sender":self.sender,
        "recipient":self.recipient,"msg_type":self.msg_type,"payload":self.payload,"trace_id":self.trace_id}

class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name=name; self.status=AgentStatus.IDLE
        self.execution_count=0; self.failure_count=0
    @abstractmethod
    def handle(self, msg: AgentMessage, ctx: "AgentContext") -> AgentMessage: ...
    def status_dict(self): return {"name":self.name,"status":self.status.value,
        "executions":self.execution_count,"failures":self.failure_count}

@dataclass
class AgentContext:
    session_id: str; query: str; trace_id: str = ""
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
    def to_dict(self): return {"session_id":self.session_id,"query":self.query,
        "trace_id":self.trace_id,"intent":self.intent,"plan":self.plan,
        "execution_graph":self.execution_graph,"failure_recovery_path":self.failure_recovery_path,
        "degraded_mode":self.degraded_mode}

class AgentBus:
    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._log: List[AgentMessage] = []
    def register(self, a: BaseAgent): self._agents[a.name] = a
    def send(self, msg: AgentMessage, ctx: Optional["AgentContext"] = None) -> AgentMessage:
        self._log.append(msg)
        a = self._agents.get(msg.recipient)
        if not a: return AgentMessage(str(uuid.uuid4()),msg.recipient,msg.sender,"error",{"error":f"Agent not found: {msg.recipient}"})
        return a.handle(msg, ctx)
    def get_agent(self, n): return self._agents.get(n)
    def list_agents(self): return list(self._agents.keys())
    def agent_statuses(self): return {n:a.status_dict() for n,a in self._agents.items()}
    def message_log(self): return [m.to_dict() for m in self._log]

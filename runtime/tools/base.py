"""
Base Tool Contract — InsureQuery Runtime Sprint 2.

ARCHITECTURE RULE #4: Tools are deterministic execution units.
No LLM reasoning inside tools. No hidden state.

Every tool MUST:
  - Define Pydantic input_schema
  - Define Pydantic output_schema
  - Return evidence (RULE #2)
  - Be stateless (no session dependency)
  - Be deterministic (same input -> same output)

Tool Contract from 06-Tool-Contracts.md:
  - P1: Deterministic Output
  - P2: Evidence Mandatory
  - P3: No Free Text Reasoning
  - P4: Stateless Execution
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from pydantic import BaseModel

from runtime.evidence.contract import EvidenceItem

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class ToolStatus:
    SUCCESS = "SUCCESS"
    EMPTY = "EMPTY"
    PARTIAL = "PARTIAL"
    ERROR = "ERROR"


@dataclass
class ToolResult:
    """Standardized tool execution result.

    Follows output schema from 06-Tool-Contracts.md 4.2:
      status: SUCCESS | EMPTY | PARTIAL | ERROR
      data: tool-specific output
      evidence: list of EvidenceItem
      error: optional error info
    """

    tool_name: str
    status: str = ToolStatus.SUCCESS
    data: Dict[str, Any] = field(default_factory=dict)
    evidence: List[EvidenceItem] = field(default_factory=list)
    error: Optional[Dict[str, str]] = None
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "data": self.data,
            "evidence": [e.to_dict() for e in self.evidence],
            "error": self.error,
            "duration_ms": self.duration_ms,
        }

    @property
    def success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence) > 0


class BaseTool(ABC, Generic[InputT, OutputT]):
    """Abstract base class for all InsureQuery tools.

    Subclasses implement:
      name: unique tool identifier
      description: what the tool does
      input_schema: Pydantic model for input validation
      output_schema: Pydantic model for output structure
      execute(input) -> ToolResult: actual deterministic execution logic

    ARCHITECTURE CONSTRAINTS:
      execute() MUST be deterministic
      execute() MUST NOT use LLM/prompt internally
      execute() MUST return evidence
      execute() MUST NOT depend on session state
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_schema(self) -> Type[InputT]: ...

    @property
    @abstractmethod
    def output_schema(self) -> Type[OutputT]: ...

    @abstractmethod
    def execute(self, input_data: InputT) -> ToolResult: ...

    def run(self, raw_input: Dict[str, Any]) -> ToolResult:
        start = time.perf_counter()
        try:
            validated = self.input_schema(**raw_input)
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error={"code": "VALIDATION_ERROR", "message": str(exc)},
            )
        try:
            result = self.execute(validated)
            result.duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return result
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            return ToolResult(
                tool_name=self.name,
                status=ToolStatus.ERROR,
                error={"code": "EXECUTION_ERROR", "message": str(exc)},
                duration_ms=duration_ms,
            )

    def describe(self) -> Dict[str, Any]:
        return {
            "tool_name": self.name,
            "description": self.description,
            "input_schema": self.input_schema.model_json_schema(),
            "output_schema": self.output_schema.model_json_schema(),
        }

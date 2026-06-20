"""
Tool Registry and Dispatcher — InsureQuery Runtime Sprint 2.

The Dispatcher is the single point of tool invocation:
  - Validates tool existence
  - Routes to the correct tool
  - Standardizes output format
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from runtime.tools.base import BaseTool, ToolResult, ToolStatus


class ToolRegistry:
    """Registry of all available tools, registered by name at startup."""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())

    def describe_all(self) -> List[Dict[str, Any]]:
        return [tool.describe() for tool in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools


class ToolDispatcher:
    """Central tool execution dispatcher.

    Routes tool calls to the correct tool, standardizes error handling,
    and tracks execution metadata.
    """

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self._call_count: Dict[str, int] = {}

    def dispatch(self, tool_name: str, params: Dict[str, Any]) -> ToolResult:
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                error={"code": "UNKNOWN_TOOL", "message": f"Tool not found: {tool_name}"},
            )
        self._call_count[tool_name] = self._call_count.get(tool_name, 0) + 1
        return tool.run(params)

    def call_count(self, tool_name: Optional[str] = None) -> int:
        if tool_name:
            return self._call_count.get(tool_name, 0)
        return sum(self._call_count.values())

    def describe_tools(self) -> List[Dict[str, Any]]:
        return self.registry.describe_all()

    def list_available(self) -> List[str]:
        return self.registry.list_tools()


def create_default_registry() -> ToolRegistry:
    """Factory: create a ToolRegistry with all Sprint 2 tools registered."""
    from runtime.tools.retrieval import (
        DocumentSearchTool,
        ProductSearchTool,
        RegulationSearchTool,
    )
    from runtime.tools.extraction import AttributeExtractionTool, ClauseParserTool
    from runtime.tools.reasoning import CompareTool, EligibilityCheckTool
    from runtime.tools.graph import EntityLookupTool, RelationTraversalTool

    registry = ToolRegistry()
    registry.register(ProductSearchTool())
    registry.register(DocumentSearchTool())
    registry.register(RegulationSearchTool())
    registry.register(AttributeExtractionTool())
    registry.register(ClauseParserTool())
    registry.register(CompareTool())
    registry.register(EligibilityCheckTool())
    registry.register(EntityLookupTool())
    registry.register(RelationTraversalTool())
    return registry

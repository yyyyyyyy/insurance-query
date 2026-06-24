"""Pipeline stage: memory resolution."""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from runtime.memory.resolver import resolve_query

if TYPE_CHECKING:
    from infra.db.session_store import WorkingMemory


def resolve_turn_memory(
    working_memory: Optional["WorkingMemory"],
    session_id: str,
    query: str,
) -> Dict[str, Any]:
    return resolve_query(working_memory, session_id, query)

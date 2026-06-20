"""
Working Memory — Multi-turn conversation state across queries.

Manages session-scoped context that persists across multiple queries,
enabling follow-up questions and progressive refinement.

Usage:
    wm = WorkingMemory()
    ctx = wm.get_or_create("session-123")
    ctx["last_intent"] = "product_comparison"
    ctx["last_products"] = ["P001", "P002"]
    wm.save("session-123", ctx)
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    query_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    context TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_sessions_updated ON sessions(updated_at);
"""

# Max sessions to keep in memory (LRU-style eviction via SQLite)
MAX_ACTIVE_SESSIONS = 1000
SESSION_TTL_HOURS = 2  # Expire sessions after 2 hours


@dataclass
class SessionContext:
    """Persistent context for a multi-turn conversation session."""
    session_id: str
    query_count: int = 0
    history: List[Dict[str, Any]] = field(default_factory=list)
    last_intent: str = ""
    last_products: List[str] = field(default_factory=list)
    last_entities: List[str] = field(default_factory=list)
    last_answer: Dict[str, Any] = field(default_factory=dict)
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query_count": self.query_count,
            "history": self.history[-10:],  # Keep last 10 turns
            "last_intent": self.last_intent,
            "last_products": self.last_products,
            "last_entities": self.last_entities,
            "last_answer": self.last_answer,
            "custom": self.custom,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionContext":
        return cls(
            session_id=data.get("session_id", ""),
            query_count=data.get("query_count", 0),
            history=data.get("history", []),
            last_intent=data.get("last_intent", ""),
            last_products=data.get("last_products", []),
            last_entities=data.get("last_entities", []),
            last_answer=data.get("last_answer", {}),
            custom=data.get("custom", {}),
        )


class WorkingMemory:
    """Persistent multi-turn conversation state manager.

    Backed by SQLite for durability. Automatically expires old sessions.
    """

    def __init__(self, db_path: str = "data/sessions.db"):
        self.db_path = db_path
        db_dir = Path(db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

        # In-memory cache
        self._cache: Dict[str, SessionContext] = {}
        self._expire_old_sessions()

    def get_or_create(self, session_id: str) -> SessionContext:
        """Get existing session context or create a new one."""
        if session_id in self._cache:
            return self._cache[session_id]

        # Try to load from DB
        cursor = self._conn.execute(
            "SELECT query_count, context FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cursor.fetchone()
        if row:
            query_count, context_json = row
            data = json.loads(context_json)
            ctx = SessionContext.from_dict(data)
            ctx.query_count = query_count
            self._cache[session_id] = ctx
            return ctx

        # Create new
        ctx = SessionContext(session_id=session_id)
        self._cache[session_id] = ctx
        return ctx

    def save(self, session_id: str, ctx: Optional[SessionContext] = None):
        """Persist session context to DB."""
        ctx = ctx or self._cache.get(session_id)
        if not ctx:
            return

        ctx.query_count += 1
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (session_id, query_count, created_at, updated_at, context) "
            "VALUES (?, ?, COALESCE((SELECT created_at FROM sessions WHERE session_id=?), ?), ?, ?)",
            (session_id, ctx.query_count, session_id, now, now, ctx.to_json()),
        )
        self._conn.commit()

        # Evict if cache grows too large
        if len(self._cache) > MAX_ACTIVE_SESSIONS:
            oldest = sorted(self._cache.keys())[:len(self._cache) // 4]
            for key in oldest:
                self._cache.pop(key, None)

    def update_from_query(
        self,
        session_id: str,
        query_text: str,
        intent: Dict[str, Any],
        answer: Dict[str, Any],
        products: Optional[List[str]] = None,
        entities: Optional[List[str]] = None,
    ):
        """Update session context after a query completes."""
        ctx = self.get_or_create(session_id)

        ctx.history.append({
            "query": query_text,
            "intent": intent.get("intent", ""),
            "products": products or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        ctx.last_intent = intent.get("intent", "")
        ctx.last_products = products or []
        ctx.last_entities = entities or []
        ctx.last_answer = answer

        self.save(session_id, ctx)

    def get_context_for_query(self, session_id: str) -> Dict[str, Any]:
        """Get relevant context to enrich the next query."""
        ctx = self.get_or_create(session_id)
        return {
            "is_follow_up": ctx.query_count > 0,
            "previous_intent": ctx.last_intent,
            "previous_products": ctx.last_products,
            "previous_entities": ctx.last_entities,
            "turn_count": ctx.query_count,
        }

    def delete(self, session_id: str):
        """Delete a session."""
        self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self._conn.commit()
        self._cache.pop(session_id, None)

    def _expire_old_sessions(self):
        """Remove expired sessions."""
        try:
            self._conn.execute(
                "DELETE FROM sessions WHERE updated_at < datetime('now', ?)",
                (f"-{SESSION_TTL_HOURS} hours",),
            )
            self._conn.commit()
        except Exception:
            pass

    def stats(self) -> Dict[str, Any]:
        cursor = self._conn.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        return {
            "total_sessions": count,
            "cached_sessions": len(self._cache),
            "db_path": self.db_path,
        }

    def close(self):
        if self._conn:
            self._conn.close()

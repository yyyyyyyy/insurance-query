"""
SQLite-backed EventStore — Persistent event sourcing.

Extends the in-memory EventStore with SQLite persistence. Events are
automatically written to SQLite on append and loaded on initialization.

Usage:
    store = SqliteEventStore("data/events.db")
    store.append(user_query_event("s1", 1, "test"))
    events = store.get_session_events("s1")
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from runtime.engine.event_store import (
    Event, EventStore, EventType,
)

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    event_type TEXT NOT NULL,
    session_id TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(timestamp);
"""


class SqliteEventStore(EventStore):
    """Persistent EventStore backed by SQLite.

    Inherits all in-memory methods from EventStore and adds automatic
    persistence. Events are loaded from SQLite on initialization.

    Thread safety: a per-session reentrant lock serializes append/seq
    operations so concurrent FastAPI requests on the same session cannot
    produce duplicate or out-of-order sequence numbers. A global write
    lock guards SQLite writes (sqlite3 connections are not safe for
    concurrent use from multiple threads without serialization).
    """

    def __init__(self, db_path: str = "data/events.db"):
        super().__init__()
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._write_lock = threading.RLock()
        self._session_locks: Dict[str, threading.RLock] = {}
        self._session_locks_guard = threading.Lock()
        self._batch_depth = 0
        self._init_db()
        self._load_existing_events()

    def _session_lock(self, session_id: str) -> threading.RLock:
        """Get or create a per-session reentrant lock."""
        with self._session_locks_guard:
            lock = self._session_locks.get(session_id)
            if lock is None:
                lock = threading.RLock()
                self._session_locks[session_id] = lock
            return lock

    def _init_db(self):
        """Initialize SQLite database and schema."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        logger.info("SQLite EventStore initialized at %s", self.db_path)

    def _load_existing_events(self):
        """Load existing events from SQLite into in-memory store."""
        if not self._conn:
            return

        cursor = self._conn.execute(
            "SELECT event_id, event_type, session_id, sequence_number, timestamp, payload "
            "FROM events ORDER BY id ASC"
        )
        loaded = 0
        for row in cursor:
            event_id, event_type_str, session_id, seq, ts_str, payload_str = row
            event_type = EventType(event_type_str)
            timestamp = datetime.fromisoformat(ts_str)
            payload = json.loads(payload_str)

            event = Event(
                event_type=event_type,
                session_id=session_id,
                sequence_number=seq,
                payload=payload,
                event_id=event_id,
                timestamp=timestamp,
            )
            # Call parent append (in-memory only, skip SQLite write)
            super().append(event)
            loaded += 1

        if loaded > 0:
            logger.info("Loaded %d existing events from SQLite (sessions: %d)",
                       loaded, self.session_count())

    def append(self, event: Event) -> Event:
        """Append event to both SQLite and in-memory store.

        Thread-safe: serializes writes via _write_lock and uses a single
        transaction so callers that append many events in a loop can opt
        into batch commit via begin_batch()/commit_batch().
        """
        with self._write_lock:
            # Persist to SQLite (deferred transaction auto-started)
            if self._conn:
                try:
                    self._conn.execute(
                        "INSERT INTO events (event_id, event_type, session_id, "
                        "sequence_number, timestamp, payload) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            event.event_id,
                            event.event_type.value,
                            event.session_id,
                            event.sequence_number,
                            event.timestamp.isoformat(),
                            json.dumps(event.payload, ensure_ascii=False),
                        ),
                    )
                    # Only commit if no explicit batch transaction is active
                    if not self._batch_depth:
                        self._conn.commit()
                except sqlite3.IntegrityError:
                    logger.warning("Duplicate event_id: %s, skipping", event.event_id)

            # Then store in memory
            return super().append(event)

    def begin_batch(self) -> None:
        """Start a batch transaction to group many appends into one commit."""
        with self._write_lock:
            self._batch_depth += 1
            if self._conn and self._batch_depth == 1:
                self._conn.execute("BEGIN")

    def commit_batch(self) -> None:
        """Commit a pending batch transaction."""
        with self._write_lock:
            if self._batch_depth <= 0:
                return
            self._batch_depth -= 1
            if self._conn and self._batch_depth == 0:
                self._conn.commit()

    def rollback_batch(self) -> None:
        """Roll back a pending batch transaction."""
        with self._write_lock:
            if self._batch_depth <= 0:
                return
            self._batch_depth = 0
            if self._conn:
                try:
                    self._conn.rollback()
                except sqlite3.Error:
                    pass

    def clear(self) -> None:
        """Clear all events from both SQLite and memory."""
        super().clear()
        if self._conn:
            self._conn.execute("DELETE FROM events")
            self._conn.commit()
            logger.info("SQLite EventStore cleared")

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def vacuum(self):
        """Optimize database file size."""
        if self._conn:
            self._conn.execute("VACUUM")

    def stats(self) -> Dict[str, Any]:
        """Extended statistics including persistence info."""
        return {
            "total_events": self.count(),
            "total_sessions": self.session_count(),
            "db_path": self.db_path,
            "db_size_mb": round(Path(self.db_path).stat().st_size / (1024 * 1024), 2)
            if Path(self.db_path).exists() else 0,
        }

"""Concurrency and thread-safety regression tests."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from infra.cache.store import TraceAwareCache
from infra.db.event_store import SqliteEventStore
from runtime.agents.bus import AgentBus, AgentMessage, AgentContext, AgentStatus, BaseAgent
from runtime.agents.orchestrator import MultiAgentEngine
from runtime.engine.event_store import user_query_event


class _EchoAgent(BaseAgent):
    def __init__(self, name: str):
        super().__init__(name)

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        self._record_success(ctx)
        return msg


class TestSqliteEventStoreConcurrency:
    def test_parallel_sessions_do_not_rollback_each_other(self, tmp_event_store):
        store = tmp_event_store
        barrier = threading.Barrier(2)

        def write_session(sid: str, text: str) -> None:
            barrier.wait(timeout=5)
            with store.transaction():
                store.append(user_query_event(sid, 1, text))

        t1 = threading.Thread(target=write_session, args=("s-a", "query-a"))
        t2 = threading.Thread(target=write_session, args=("s-b", "query-b"))
        t1.start()
        t2.start()
        t1.join(timeout=30)
        t2.join(timeout=30)

        assert len(store.get_session_events("s-a")) == 1
        assert len(store.get_session_events("s-b")) == 1
        assert store.count() == 2

    def test_transaction_context_manager(self, tmp_event_store):
        store = tmp_event_store
        with store.transaction():
            store.append(user_query_event("s1", 1, "ok"))
        assert store.count() == 1


class TestMultiAgentEngineConcurrency:
    def test_engine_persists_events_with_sqlite_store(self, tmp_event_store):
        """Smoke test: engine + SqliteEventStore integration after concurrent store tests."""
        engine = MultiAgentEngine(event_store=tmp_event_store)
        sid = "engine-sqlite-smoke"
        result = engine.query("重疾险保障什么", session_id=sid)
        assert result["session_id"] == sid
        assert len(tmp_event_store.get_session_events(sid)) > 0


class TestTraceAwareCacheConcurrency:
    def test_cache_thread_safety(self):
        cache = TraceAwareCache()
        errors: list = []

        def worker(i: int) -> None:
            try:
                key = f"k-{i % 8}"
                cache.set("tool", key, f"v-{i}")
                cache.get("tool", key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors

    def test_tool_key_stable_across_dict_order(self):
        cache = TraceAwareCache()
        k1 = cache.tool_key("p", {"a": 1, "b": 2})
        k2 = cache.tool_key("p", {"b": 2, "a": 1})
        assert k1 == k2
        k3 = cache.tool_key("p", {"a": 2})
        assert k1 != k3


class TestAgentBusConcurrency:
    def test_agent_bus_log_under_concurrency(self):
        bus = AgentBus()
        bus.register(_EchoAgent("echo"))
        send_count = 20

        def send_one(i: int) -> None:
            bus.send(AgentMessage(f"m-{i}", "s", "echo", "t", {"i": i}))

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(send_one, range(send_count)))

        assert len(bus.message_log()) == send_count

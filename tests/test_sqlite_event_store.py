"""SqliteEventStore persistence and batch atomicity tests."""

import pytest

from runtime.engine.event_store import user_query_event
from infra.db.event_store import SqliteEventStore


class TestSqliteEventStore:
    def test_batch_rollback_truncates_memory(self, tmp_event_store):
        store = tmp_event_store
        with pytest.raises(Exception):
            with store.transaction():
                store.append(user_query_event("s1", 1, "first"))
                store.append(user_query_event("s1", 2, "second"))
                assert store.count() == 2
                raise RuntimeError("abort turn")
        assert store.count() == 0

    def test_batch_commit_persists(self, tmp_event_store):
        store = tmp_event_store
        store.begin_batch()
        store.append(user_query_event("s1", 1, "committed"))
        store.commit_batch()
        assert store.count() == 1
        reloaded = SqliteEventStore(store.db_path)
        assert reloaded.count() == 1
        reloaded.close()

    def test_integrity_error_skips_memory(self, tmp_event_store):
        store = tmp_event_store
        ev = user_query_event("s1", 1, "dup")
        store.append(ev)
        store.begin_batch()
        dup = user_query_event("s1", 2, "dup2")
        dup.event_id = ev.event_id
        with pytest.raises(Exception):
            store.append(dup)
        store.rollback_batch()
        assert store.count() == 1

    def test_clear_requires_testing_guard(self, tmp_event_store):
        store = tmp_event_store
        store.append(user_query_event("s1", 1, "keep"))
        with pytest.raises(RuntimeError):
            store.clear()
        assert store.count() == 1
        store.clear(_testing_only=True)
        assert store.count() == 0

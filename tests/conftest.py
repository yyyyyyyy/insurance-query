"""Pytest defaults — skip heavy embedding models and live LLM in test runs."""

import copy
import os

import pytest

os.environ.setdefault("EMBEDDING_FAST_MODE", "1")
os.environ.setdefault("LLM_ENABLED", "false")

from runtime.tools import document_data as _document_data

_ORIGINAL_DOCUMENT_STORE = copy.deepcopy(_document_data.DOCUMENT_STORE)


@pytest.fixture(autouse=True)
def _reset_document_store():
    """Restore built-in document fixtures; orchestrator tests may replace them per run."""
    _document_data.DOCUMENT_STORE.clear()
    _document_data.DOCUMENT_STORE.extend(copy.deepcopy(_ORIGINAL_DOCUMENT_STORE))
    yield


@pytest.fixture(autouse=True)
def _clean_vectordb(tmp_path, monkeypatch):
    """Use an isolated ChromaDB directory per test to avoid dimension drift."""
    vdir = tmp_path / "vectordb"
    vdir.mkdir()
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(vdir))
    yield


@pytest.fixture
def tmp_event_store(tmp_path):
    """Isolated SQLite event store for persistence tests."""
    from infra.db.event_store import SqliteEventStore
    db_path = tmp_path / "events.db"
    store = SqliteEventStore(str(db_path))
    yield store
    store.close()


@pytest.fixture
def tmp_working_memory(tmp_path):
    """Isolated working memory database."""
    from infra.db.session_store import WorkingMemory
    db_path = tmp_path / "sessions.db"
    wm = WorkingMemory(str(db_path))
    yield wm


@pytest.fixture
def minimal_catalog(tmp_path, monkeypatch):
    """Minimal product catalog for tests that patch knowledge pack root."""
    import runtime.tools.data_loader as dl

    pack = tmp_path / "knowledge_pack" / "products"
    pack.mkdir(parents=True)
    catalog = {
        "meta": {"version": "test", "total_products": 2},
        "products": [
            {
                "product_id": "P001",
                "name": "测试医疗险",
                "company": "平安健康保险",
                "category": "百万医疗险",
                "deductible": "年度1万元",
                "waiting_period": "30天",
                "premium_reference": {"age_30": 380},
                "max_age": 65,
                "min_age": 0,
            },
            {
                "product_id": "P012",
                "name": "平安福",
                "company": "平安人寿保险",
                "category": "重疾险",
                "min_age": 18,
                "max_age": 55,
            },
        ],
    }
    catalog_path = pack / "catalog.json"
    catalog_path.write_text(
        __import__("json").dumps(catalog, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(dl, "_KNOWLEDGE_PACK_ROOT", tmp_path / "knowledge_pack")
    return catalog_path

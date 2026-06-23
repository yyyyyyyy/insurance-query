"""Tests for policy PDF/TXT ingestion pipeline."""

import json
from pathlib import Path

import pytest

from knowledge.ingestion.policy_ingest import (
    ManifestEntry,
    ingest_manifest_entry,
    init_manifest_from_catalog,
    load_ingested_documents,
    merge_documents,
)
from knowledge.ingestion.pipeline import _split_long_text, chunk_document

ROOT = Path(__file__).resolve().parents[1]

SAMPLE_CLAUSE_TEXT = """
第一条 等待期：自本合同生效日起30日为等待期。
第二条 一般医疗保险金：年度累计给付限额为400万元。
第三条 重大疾病医疗保险金：无免赔额。
第四条 免赔额：年度1万元。
第五条 保证续保：20年保证续保。
第六条 责任免除：既往症、美容整形。
""".strip()


class TestPolicyIngest:
    def test_chunk_clause_text(self):
        chunks = chunk_document(SAMPLE_CLAUSE_TEXT, "DOC_TEST")
        assert len(chunks) >= 2
        assert any("等待期" in c.content for c in chunks)

    def test_split_long_text_whitespace_does_not_loop(self):
        text = " " * 2000 + "正文。" + " " * 2000
        chunks = _split_long_text(text, chunk_size=500, overlap=50)
        assert chunks
        assert any("正文" in c for c in chunks)
        assert len(chunks) < 50

    def test_prune_preserves_unscanned_scope(self, monkeypatch):
        import knowledge.ingestion.policy_ingest as pi

        product_doc = {"document_id": "DOC_P001", "chunks": []}
        reg_doc = {"document_id": "DOC_R001", "chunks": []}
        merged = [product_doc, reg_doc]

        monkeypatch.setattr(pi, "load_manifest", lambda: [
            pi.ManifestEntry(
                file="p.pdf", document_id="DOC_P001", title="P", product_id="P001",
            ),
        ])
        monkeypatch.setattr(pi, "load_regulation_manifest", lambda: [
            pi.ManifestEntry(
                file="documents/r.txt", document_id="DOC_R001", title="R",
                document_type="regulation", regulation_id="R001",
            ),
        ])
        monkeypatch.setattr(
            pi, "_active_document_ids",
            lambda **kwargs: {"DOC_P001"} if kwargs.get("include_products") else set(),
        )

        kept, pruned = pi._prune_stale_documents(
            merged, include_products=True, include_regulations=False,
        )
        assert pruned == 0
        assert {d["document_id"] for d in kept} == {"DOC_P001", "DOC_R001"}

    def test_ingest_inline_file(self, tmp_path):
        sample = tmp_path / "clause.txt"
        sample.write_text(SAMPLE_CLAUSE_TEXT, encoding="utf-8")
        entry = ManifestEntry(
            file="clause.txt",
            document_id="DOC_TEST",
            title="测试条款",
            product_id="P001",
        )
        import knowledge.ingestion.policy_ingest as pi
        original_resolve = pi._resolve_file_path

        def _resolve(entry, base_dir=None):
            return sample

        pi._resolve_file_path = lambda e, base_dir=None: sample
        try:
            result = ingest_manifest_entry(entry, ignore_enabled=True)
        finally:
            pi._resolve_file_path = original_resolve

        assert result.status == "success"
        assert result.chunk_count >= 2
        assert result.document is not None

    def test_merge_documents_by_id(self):
        a = {"document_id": "D1", "chunks": [{"chunk_id": "C1"}]}
        b = {"document_id": "D1", "chunks": [{"chunk_id": "C2"}]}
        c = {"document_id": "D2", "chunks": []}
        merged = merge_documents([a, c], [b])
        assert len(merged) == 2
        d1 = next(d for d in merged if d["document_id"] == "D1")
        assert d1["chunks"][0]["chunk_id"] == "C2"

    def test_ingested_output_optional(self):
        path = ROOT / "knowledge_pack/chunks/ingested_documents.json"
        if not path.exists():
            pytest.skip("No ingested documents yet")
        data = load_ingested_documents()
        assert "documents" in data

    def test_init_manifest_from_catalog(self, tmp_path, monkeypatch):
        import knowledge.ingestion.policy_ingest as pi

        catalog = tmp_path / "knowledge_pack" / "products" / "catalog.json"
        catalog.parent.mkdir(parents=True)
        catalog.write_text(json.dumps({
            "products": [
                {"product_id": "P001", "name": "产品A", "category": "百万医疗险"},
                {"product_id": "P002", "name": "产品B", "category": "重疾险"},
            ]
        }), encoding="utf-8")
        manifest = tmp_path / "policy_documents" / "manifest.json"
        monkeypatch.setattr(pi, "ROOT", tmp_path)
        monkeypatch.setattr(pi, "MANIFEST_PATH", manifest)
        monkeypatch.setattr(pi, "POLICY_DOCS_DIR", tmp_path / "policy_documents")
        entries = init_manifest_from_catalog(overwrite=True)
        assert len(entries) == 2

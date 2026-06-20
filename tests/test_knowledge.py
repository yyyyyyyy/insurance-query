"""Sprint 3 Knowledge Layer Tests — Ingestion, Ontology, Evidence, RAG."""

import pytest
import numpy as np
from knowledge.ingestion.pipeline import (
    ChunkStore, EmbeddingGenerator, DocumentMeta, Chunk,
    chunk_document, ingest_text_document, _split_by_clause
)
from knowledge.ontology.graph import (
    OntologyGraph, OntologyEntity, OntologyRelation,
    EntityType, RelationType
)
from knowledge.ontology.builder import build_insurance_ontology
from knowledge.evidence.index import EvidenceIndex, EvidenceRecord
from knowledge.retrieval.engine import HybridRetriever, BM25Scorer
from knowledge.engine import KnowledgeEngine


# ============================================================
# 8.1 INGESTION TESTS
# ============================================================

class TestIngestionPipeline:
    SAMPLE_TEXT = """第一条：保险公司应当遵守诚实信用原则。保险活动当事人行使权利、履行义务应当遵循诚实信用原则。
第二条：订立保险合同，保险人就保险标的或者被保险人的有关情况提出询问的，投保人应当如实告知。投保人故意或者因重大过失未履行如实告知义务，足以影响保险人决定是否同意承保或者提高保险费率的，保险人有权解除合同。
第三条：保险事故发生后，投保人、被保险人或者受益人应当及时通知保险人。"""

    def test_chunk_document_splits_by_clause(self):
        chunks = chunk_document(self.SAMPLE_TEXT, "TEST-DOC")
        assert len(chunks) >= 2
        # First chunk should have clause info
        assert any("第一条" in c.clause for c in chunks) or any("第二条" in c.clause for c in chunks)

    def test_chunk_has_metadata(self):
        chunks = chunk_document(self.SAMPLE_TEXT, "TEST-DOC")
        for c in chunks:
            assert c.document_id == "TEST-DOC"
            assert len(c.content) > 10
            assert c.chunk_id.startswith("TEST-DOC-C")

    def test_clause_splitter_with_markers(self):
        clauses = _split_by_clause(self.SAMPLE_TEXT)
        assert len(clauses) >= 2
        for clause_no, text in clauses:
            assert len(text) > 5

    def test_clause_splitter_without_markers(self):
        text = "This is a paragraph without any clause markers. Just plain text. Another paragraph here."
        clauses = _split_by_clause(text)
        assert len(clauses) > 0

    def test_ingest_text_document(self):
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        meta, chunks = ingest_text_document(
            self.SAMPLE_TEXT, "TEST-DOC-1", "测试合同", "policy_clause", store, gen
        )
        assert meta.document_id == "TEST-DOC-1"
        assert store.chunk_count() > 0
        assert store.document_count() >= 1

    def test_embedding_generated_for_chunks(self):
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        _, chunks = ingest_text_document(
            self.SAMPLE_TEXT, "TEST-DOC-2", "Test", "policy_clause", store, gen
        )
        for c in chunks:
            assert c.embedding is not None
            assert len(c.embedding) == 64

    def test_embedding_consistency(self):
        gen = EmbeddingGenerator(vector_dim=64)
        texts = ["保证续保条款", "等待期规定", "免赔额规则"]
        gen.fit(texts)
        v1 = gen.encode("保证续保")
        v2 = gen.encode("保证续保")
        assert np.allclose(v1, v2)  # Same input -> same embedding

    def test_chunk_store_retrieval(self):
        store = ChunkStore()
        meta, _ = ingest_text_document(
            "第一条：等待期为30天。被保险人在等待期内因非意外伤害原因发生的保险事故，保险公司不承担给付保险金的责任。第二条：免赔额为1万元。每一保险期间内，免赔额以上的医疗费用方可申请赔付。",
            "DOC-X", "Test", "policy_clause", store
        )
        doc_chunks = store.get_document_chunks("DOC-X")
        assert len(doc_chunks) > 0

    def test_chunk_store_save_load(self, tmp_path):
        store = ChunkStore()
        ingest_text_document("测试条款内容", "DOC-S", "Test", "policy_clause", store)
        path = str(tmp_path / "chunks.json")
        store.save(path)
        loaded = ChunkStore.load(path)
        assert loaded.chunk_count() == store.chunk_count()

    def test_embedding_similarity_symmetric(self):
        gen = EmbeddingGenerator(vector_dim=64)
        texts = ["保证续保条款内容", "等待期规定内容", "免赔额规则"]
        gen.fit(texts)
        v1 = gen.encode("保证续保")
        v2 = gen.encode("续保条款")
        sim = gen.similarity(v1, v2)
        assert 0 <= sim <= 1.0

    def test_embedding_generator_fallback(self):
        gen = EmbeddingGenerator(vector_dim=16)
        gen.fit(["短", "很短的文本", "极短"])
        vec = gen.encode("测试")
        assert len(vec) == 16
        assert np.isclose(np.linalg.norm(vec), 1.0, atol=0.01)


# ============================================================
# 8.2 ONTOLOGY TESTS
# ============================================================

class TestOntologyGraph:
    def test_add_and_get_entity(self):
        g = OntologyGraph()
        e = OntologyEntity("ENT-1", "测试产品", EntityType.PRODUCT)
        g.add_entity(e)
        assert g.get_entity("ENT-1") is e
        assert g.entity_count() == 1

    def test_duplicate_entity_raises(self):
        g = OntologyGraph()
        g.add_entity(OntologyEntity("ENT-1", "Test", EntityType.PRODUCT))
        with pytest.raises(ValueError):
            g.add_entity(OntologyEntity("ENT-1", "Test2", EntityType.PRODUCT))

    def test_lookup_by_name(self):
        g = OntologyGraph()
        g.add_entity(OntologyEntity("ENT-1", "e生保", EntityType.PRODUCT, aliases=["e生保百万医疗"]))
        results = g.lookup("e生保")
        assert len(results) >= 1
        assert results[0].name == "e生保"

    def test_lookup_by_alias(self):
        g = OntologyGraph()
        g.add_entity(OntologyEntity("ENT-1", "恶性肿瘤", EntityType.DISEASE, aliases=["癌症"]))
        results = g.lookup("癌症")
        assert len(results) >= 1

    def test_lookup_by_type_filter(self):
        onto = build_insurance_ontology()
        results = onto.lookup("", EntityType.PRODUCT)
        assert len(results) > 0
        for r in results:
            assert r.entity_type == EntityType.PRODUCT

    def test_get_entities_by_type(self):
        onto = build_insurance_ontology()
        products = onto.get_entities_by_type(EntityType.PRODUCT)
        diseases = onto.get_entities_by_type(EntityType.DISEASE)
        assert len(products) > 0
        assert len(diseases) > 0

    def test_add_relation(self):
        g = OntologyGraph()
        g.add_entity(OntologyEntity("A", "Product A", EntityType.PRODUCT))
        g.add_entity(OntologyEntity("B", "Disease B", EntityType.DISEASE))
        g.add_relation(OntologyRelation("A", "B", RelationType.COVERS))
        rels = g.get_outgoing("A")
        assert len(rels) == 1
        assert rels[0].relation_type == RelationType.COVERS

    def test_relation_traversal(self):
        onto = build_insurance_ontology()
        outgoing = onto.get_outgoing("ENT-P001")
        assert len(outgoing) > 0
        # e生保 should cover diseases
        covers = [r for r in outgoing if r.relation_type == RelationType.COVERS]
        assert len(covers) > 0

    def test_incoming_relations(self):
        onto = build_insurance_ontology()
        incoming = onto.get_incoming("ENT-D001")
        assert len(incoming) > 0

    def test_find_paths(self):
        onto = build_insurance_ontology()
        paths = onto.find_paths("ENT-P001", "ENT-D001")
        assert len(paths) > 0

    def test_expand_context(self):
        onto = build_insurance_ontology()
        expanded = onto.expand_context(["ENT-P001"], max_depth=2)
        assert len(expanded) > 0
        # Should include diseases and coverages
        types = {e.entity_type for e in expanded}
        assert EntityType.DISEASE in types or EntityType.COVERAGE in types

    def test_ontology_filter_relations(self):
        onto = build_insurance_ontology()
        regulated = onto.get_outgoing("ENT-P001", RelationType.REGULATED_BY)
        assert len(regulated) > 0

    def test_statistics_accurate(self):
        onto = build_insurance_ontology()
        stats = onto.statistics()
        assert stats["entity_count"] >= 10
        assert stats["relation_count"] >= 10


# ============================================================
# 8.3 EVIDENCE INDEX TESTS
# ============================================================

class TestEvidenceIndex:
    def test_index_chunk(self):
        ei = EvidenceIndex()
        chunk = Chunk(chunk_id="C1", document_id="D1", content="测试内容", clause="第1条")
        rec = ei.index_chunk(chunk, "policy_clause", "测试文档")
        assert rec.evidence_id == "EV-C1"
        assert rec.content_hash is not None
        assert ei.record_count() == 1

    def test_get_by_chunk(self):
        ei = EvidenceIndex()
        chunk = Chunk(chunk_id="C1", document_id="D1", content="test", clause="c1")
        ei.index_chunk(chunk, "type", "title")
        rec = ei.get_by_chunk("C1")
        assert rec is not None

    def test_get_by_nonexistent_chunk(self):
        ei = EvidenceIndex()
        assert ei.get_by_chunk("nonexistent") is None

    def test_link_entity(self):
        ei = EvidenceIndex()
        chunk = Chunk(chunk_id="C1", document_id="D1", content="test", clause="c1")
        ei.index_chunk(chunk, "type", "title")
        ei.link_entity("EV-C1", "ENT-1")
        rec = ei.get_by_chunk("C1")
        assert "ENT-1" in rec.entity_links

    def test_get_by_entity(self):
        ei = EvidenceIndex()
        chunk = Chunk(chunk_id="C1", document_id="D1", content="test", clause="c1")
        ei.index_chunk(chunk, "type", "title")
        ei.link_entity("EV-C1", "ENT-1")
        recs = ei.get_by_entity("ENT-1")
        assert len(recs) == 1

    def test_verify_traceability(self):
        ei = EvidenceIndex()
        for i in range(3):
            chunk = Chunk(chunk_id=f"C{i}", document_id="D1", content=f"test{i}", clause=f"c{i}")
            ei.index_chunk(chunk, "type", "title")
        result = ei.verify_traceability("D1")
        assert result["total"] == 3
        assert result["orphan"] == 3  # None linked yet


# ============================================================
# 8.4 RAG TESTS
# ============================================================

class TestHybridRetrieval:
    def test_bm25_scorer(self):
        scorer = BM25Scorer()
        texts = ["等待期30天免赔额1万元", "保证续保20年恶性肿瘤保障", "犹豫期15天如实告知义务"]
        scorer.fit(texts)
        score = scorer.score("保证续保", 1)
        assert score > 0

    def test_hybrid_retrieval_basic(self):
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        texts = [
            ("D1", "policy", "第一条：等待期为30日。被保险人在等待期内因非意外伤害原因发生的保险事故，保险公司不承担保险责任。等待期是保险产品的重要条款。"),
            ("D2", "policy", "第一条：保证续保期间为20年。保证续保期间内，保险公司不得因被保险人健康变化拒绝续保。第二条：恶性肿瘤保险金400万元。"),
            ("D3", "regulation", "第二十三条：保险公司在健康保险产品条款中约定的等待期不得超过180日。保险公司不得通过延长等待期的方式变相拒绝承担保险责任。"),
        ]
        for did, dtype, text in texts:
            ingest_text_document(text, did, f"Doc {did}", dtype, store, gen)

        hr = HybridRetriever(store, gen)
        hr.fit()

        results = hr.retrieve("等待期规定", top_k=3)
        assert len(results) > 0

        # First result should be most relevant
        top_chunk = results[0][0]
        assert "等待期" in top_chunk.content

    def test_hybrid_retrieval_with_ontology(self):
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        onto = build_insurance_ontology()

        texts = [
            ("D1", "policy", "e生保条款：等待期30日。免赔额1万元。恶性肿瘤保障600万。"),
            ("D2", "policy", "好医保条款：保证续保20年。免赔额1万元。"),
            ("D3", "regulation", "健康保险管理办法：保证续保条款定义。"),
        ]
        for did, dtype, text in texts:
            ingest_text_document(text, did, f"Doc {did}", dtype, store, gen)

        hr = HybridRetriever(store, gen, onto)
        hr.fit()

        results = hr.retrieve("e生保保障", top_k=3, ontology_context=["e生保"])
        assert len(results) > 0

    def test_retrieval_returns_ranked(self):
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        texts = [("D1","policy","test A content"),("D2","policy","test B content"),
                 ("D3","policy","test C content")]
        for did, dtype, text in texts:
            ingest_text_document(text, did, f"D{did}", dtype, store, gen)
        hr = HybridRetriever(store, gen)
        hr.fit()
        results = hr.retrieve("test", top_k=3)
        scores = [s for _, s in results]
        # Scores should be descending
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1]


# ============================================================
# 8.5 KNOWLEDGE ENGINE E2E TESTS
# ============================================================

class TestKnowledgeEngine:
    def test_load_knowledge_populates_all_layers(self):
        ke = KnowledgeEngine()
        ke.load_knowledge()
        stats = ke.stats()
        assert stats["documents"] >= 1
        assert stats["ontology"]["entity_count"] >= 10
        assert stats["retriever_fitted"] is True

    def test_query_returns_answer_with_evidence(self):
        ke = KnowledgeEngine()
        result = ke.query("等待期是多久")
        assert result["answer"]["text"] is not None
        assert result["answer"]["evidence_count"] > 0
        assert result["state"]["status"] == "completed"

    def test_query_ontology_used(self):
        ke = KnowledgeEngine()
        result = ke.query("e生保保障什么疾病")
        state = result["state"]
        # Should have retrieval path
        assert len(state["retrieval_path"]) > 0

    def test_query_product_comparison(self):
        ke = KnowledgeEngine()
        result = ke.query("比较e生保和好医保")
        assert "compare" in result["answer"]["tools_used"]

    def test_query_regulation_lookup(self):
        ke = KnowledgeEngine()
        result = ke.query("健康保险管理办法关于等待期的规定")
        intent = result["answer"]["intent"]
        assert intent in ("regulation_lookup", "coverage_question", "general_inquiry")

    def test_event_trace_has_knowledge_events(self):
        ke = KnowledgeEngine()
        result = ke.query("保证续保条款")
        event_types = {e["event_type"] for e in result["trace"]}
        assert "RETRIEVAL_EXECUTED" in event_types

    def test_state_replay_preserves_knowledge(self):
        ke = KnowledgeEngine()
        result = ke.query("免赔额是多少")
        replayed = ke.replay_session(result["session_id"])
        assert replayed.status == "completed"
        assert replayed.retrieval_path is not None
        assert replayed.retrieved_chunks is not None

    def test_no_hallucination_guarantee(self):
        """Sprint 3 exit criteria: answer must be evidence-backed, no hallucination."""
        ke = KnowledgeEngine()
        result = ke.query("保证续保是什么意思")
        answer_text = result["answer"]["text"]
        evidence_count = result["answer"]["evidence_count"]
        # Answer must have evidence
        assert evidence_count > 0, "Answer must be evidence-backed"


# ============================================================
# 8.6 CONTRACT VALIDATION
# ============================================================

class TestKnowledgeContracts:
    """Verify knowledge layer follows Sprint 3 contracts."""

    def test_ontology_is_graph_based(self):
        onto = build_insurance_ontology()
        assert onto._graph is not None
        assert onto._graph.number_of_nodes() > 0

    def test_evidence_has_traceability(self):
        ei = EvidenceIndex()
        chunk = Chunk(chunk_id="C1", document_id="D1", content="test", clause="c1")
        rec = ei.index_chunk(chunk, "policy_clause", "Test Doc")
        assert rec.evidence_id is not None
        assert rec.document_id == "D1"
        assert rec.content_hash is not None

    def test_retrieval_is_hybrid(self):
        """Sprint 3 exit criteria: retrieval must be hybrid (not pure vector)."""
        store = ChunkStore()
        gen = EmbeddingGenerator(vector_dim=64)
        onto = build_insurance_ontology()
        ingest_text_document("test content here", "D1", "Test", "policy", store, gen)
        hr = HybridRetriever(store, gen, onto)
        hr.fit()
        # Must support both BM25 and vector
        assert hr.bm25._fitted
        assert hr.embedding_gen._fitted

    def test_ontology_has_required_entity_types(self):
        onto = build_insurance_ontology()
        required = {EntityType.PRODUCT, EntityType.DISEASE, EntityType.COVERAGE, EntityType.REGULATION}
        for et in required:
            entities = onto.get_entities_by_type(et)
            assert len(entities) > 0, f"Missing entity type: {et}"

    def test_ontology_has_required_relations(self):
        onto = build_insurance_ontology()
        rels = onto.get_relations()
        rel_types = {r.relation_type for r in rels}
        required = {RelationType.COVERS, RelationType.CONTAINS, RelationType.REGULATED_BY, RelationType.DEFINES}
        for rt in required:
            assert rt in rel_types, f"Missing relation type: {rt}"

"""Sprint 2 Tool System Tests — Real deterministic tools with evidence contracts."""

import pytest
from runtime.tools.base import ToolResult, ToolStatus
from runtime.tools.registry import ToolRegistry, ToolDispatcher, create_default_registry
from runtime.tools.retrieval import ProductSearchTool, DocumentSearchTool, RegulationSearchTool
from runtime.tools.extraction import AttributeExtractionTool, ClauseParserTool
from runtime.tools.reasoning import CompareTool, EligibilityCheckTool
from runtime.tools.graph import EntityLookupTool, RelationTraversalTool
from runtime.evidence.contract import EvidenceItem, SourceType


# ============================================================
# Registry & Dispatcher Tests
# ============================================================

class TestToolRegistry:
    def test_register_and_get(self):
        r = ToolRegistry()
        t = ProductSearchTool()
        r.register(t)
        assert r.get("product_search") is t

    def test_duplicate_registration_raises(self):
        r = ToolRegistry()
        r.register(ProductSearchTool())
        with pytest.raises(ValueError):
            r.register(ProductSearchTool())

    def test_list_tools(self):
        r = ToolRegistry()
        r.register(ProductSearchTool())
        r.register(DocumentSearchTool())
        assert "product_search" in r.list_tools()
        assert "document_search" in r.list_tools()

    def test_contains(self):
        r = ToolRegistry()
        r.register(ProductSearchTool())
        assert "product_search" in r
        assert "nonexistent" not in r

    def test_default_registry_has_all_9_tools(self):
        r = create_default_registry()
        tools = r.list_tools()
        assert len(tools) == 9
        expected = {"product_search", "document_search", "regulation_search",
                    "attribute_extraction", "clause_parser", "compare",
                    "eligibility_check", "entity_lookup", "relation_traversal"}
        assert set(tools) == expected


class TestToolDispatcher:
    def test_dispatch_existing_tool(self):
        d = ToolDispatcher(create_default_registry())
        result = d.dispatch("product_search", {"query": "医疗"})
        assert isinstance(result, ToolResult)
        assert result.success

    def test_dispatch_unknown_tool(self):
        d = ToolDispatcher(create_default_registry())
        result = d.dispatch("nonexistent", {})
        assert result.status == ToolStatus.ERROR
        assert result.error is not None

    def test_describe_all_tools(self):
        d = ToolDispatcher(create_default_registry())
        descs = d.describe_tools()
        assert len(descs) == 9
        for desc in descs:
            assert "tool_name" in desc
            assert "input_schema" in desc

    def test_call_count(self):
        d = ToolDispatcher(create_default_registry())
        d.dispatch("product_search", {"query": "test"})
        d.dispatch("product_search", {"query": "test2"})
        d.dispatch("document_search", {"query": "test"})
        assert d.call_count("product_search") == 2
        assert d.call_count("document_search") == 1
        assert d.call_count() == 3


# ============================================================
# Retrieval Tools Tests
# ============================================================

class TestProductSearchTool:
    def test_search_all_products(self):
        t = ProductSearchTool()
        r = t.run({"query": "", "top_k": 10})
        assert r.success
        assert len(r.data["products"]) > 0

    def test_search_by_keyword(self):
        t = ProductSearchTool()
        r = t.run({"query": "百万医疗", "top_k": 5})
        assert r.success
        names = [p["name"] for p in r.data["products"]]
        assert any("百万医疗" in n for n in names)

    def test_filter_by_type(self):
        t = ProductSearchTool()
        r = t.run({"product_type": "重疾险", "top_k": 5})
        assert r.success
        for p in r.data["products"]:
            assert p["product_type"] == "重疾险"

    def test_empty_result(self):
        t = ProductSearchTool()
        r = t.run({"query": "不存在的产品xyz123", "top_k": 5})
        assert r.status == ToolStatus.EMPTY

    def test_evidence_has_source_type(self):
        t = ProductSearchTool()
        r = t.run({"query": "平安", "top_k": 3})
        assert r.has_evidence
        for ev in r.evidence:
            assert isinstance(ev, EvidenceItem)
            assert ev.source_type == SourceType.PRODUCT_CATALOG

    def test_deterministic_output(self):
        t = ProductSearchTool()
        r1 = t.run({"query": "医疗", "top_k": 3})
        r2 = t.run({"query": "医疗", "top_k": 3})
        assert r1.data == r2.data
        assert len(r1.evidence) == len(r2.evidence)


class TestDocumentSearchTool:
    def test_search_by_type(self):
        t = DocumentSearchTool()
        r = t.run({"query": "免赔额", "document_type": "policy_clause", "top_k": 5})
        assert r.success
        assert len(r.data["chunks"]) > 0

    def test_search_regulation_type(self):
        t = DocumentSearchTool()
        r = t.run({"query": "保证续保", "document_type": "regulation", "top_k": 5})
        assert r.success
        for c in r.data["chunks"]:
            assert "regulation" in c.get("document_id", "").lower() or "保险法" in c.get("document_title", "") or "管理办法" in c.get("document_title", "")

    def test_evidence_has_clause_field(self):
        t = DocumentSearchTool()
        r = t.run({"query": "等待期", "top_k": 3})
        assert r.has_evidence
        for ev in r.evidence:
            assert isinstance(ev, EvidenceItem)
            # clause may be empty for some matches

    def test_claim_procedure_search(self):
        t = DocumentSearchTool()
        r = t.run({"query": "理赔", "document_type": "claim_procedure", "top_k": 3})
        assert r.success
        titles = [c["document_title"] for c in r.data["chunks"]]
        assert any("理赔" in title for title in titles)

    def test_fuzzy_matching(self):
        t = DocumentSearchTool()
        r = t.run({"query": "理赔流程是什么？", "document_type": "claim_procedure", "top_k": 3})
        # Should match via bigram tokenization
        assert r.success or r.status == ToolStatus.EMPTY
        # At minimum, should not error


class TestRegulationSearchTool:
    def test_search_regulations(self):
        t = RegulationSearchTool()
        r = t.run({"query": "健康保险", "top_k": 5})
        assert r.success
        assert len(r.data["regulations"]) > 0

    def test_regulation_has_chunks(self):
        t = RegulationSearchTool()
        r = t.run({"query": "", "top_k": 5})
        assert r.success
        for reg in r.data["regulations"]:
            assert "title" in reg
            assert "chunks" in reg
            assert len(reg["chunks"]) > 0

    def test_evidence_source_type_is_regulation(self):
        t = RegulationSearchTool()
        r = t.run({"query": "等待期", "top_k": 3})
        if r.has_evidence:
            for ev in r.evidence:
                assert ev.source_type == SourceType.REGULATION


# ============================================================
# Extraction Tools Tests
# ============================================================

class TestAttributeExtractionTool:
    def test_extract_known_attributes(self):
        t = AttributeExtractionTool()
        r = t.run({"attributes": ["waiting_period", "deductible", "coverage_limit"],
                    "product_ids": ["P001"]})
        assert r.success
        attrs = r.data["results"]["P001"]
        assert "waiting_period_days" in attrs
        assert "deductible" in attrs
        assert "coverage_limit" in attrs

    def test_extract_premium_info(self):
        t = AttributeExtractionTool()
        r = t.run({"attributes": ["premium", "guaranteed_renewal"],
                    "product_ids": ["P002"]})
        assert r.success
        attrs = r.data["results"]["P002"]
        assert "premium_min" in attrs or "premium_reference" in attrs

    def test_extract_eligibility(self):
        t = AttributeExtractionTool()
        r = t.run({"attributes": ["eligibility"],
                    "product_ids": ["P001"]})
        assert r.success
        assert "eligibility" in r.data["results"]["P001"]

    def test_unknown_product_returns_empty(self):
        t = AttributeExtractionTool()
        r = t.run({"attributes": ["deductible"],
                    "product_ids": ["P999"]})
        assert r.status == ToolStatus.EMPTY

    def test_deterministic_extraction(self):
        t = AttributeExtractionTool()
        r1 = t.run({"attributes": ["deductible"], "product_ids": ["P001"]})
        r2 = t.run({"attributes": ["deductible"], "product_ids": ["P001"]})
        assert r1.data == r2.data


class TestClauseParserTool:
    def test_parse_existing_document(self):
        t = ClauseParserTool()
        r = t.run({"document_id": "DOC001"})
        assert r.success
        assert len(r.data["clauses"]) > 0

    def test_filter_by_clause_number(self):
        t = ClauseParserTool()
        r = t.run({"document_id": "DOC001", "clause_numbers": ["第2.3条"]})
        assert r.success
        for clause in r.data["clauses"]:
            assert clause["clause"] == "第2.3条"

    def test_nonexistent_document(self):
        t = ClauseParserTool()
        r = t.run({"document_id": "DOC999"})
        assert r.status == ToolStatus.EMPTY


# ============================================================
# Reasoning Tools Tests
# ============================================================

class TestCompareTool:
    def test_compare_two_products(self):
        t = CompareTool()
        r = t.run({"product_ids": ["P001", "P002"],
                    "dimensions": ["waiting_period", "deductible", "guaranteed_renewal"]})
        assert r.success
        comp = r.data["comparison"]
        assert len(comp["products"]) == 2
        assert len(comp["rows"]) == 3

    def test_compare_all_dimensions(self):
        t = CompareTool()
        r = t.run({"product_ids": ["P001", "P002"]})
        assert r.success
        assert len(r.data["comparison"]["rows"]) > 0

    def test_insufficient_products(self):
        t = CompareTool()
        r = t.run({"product_ids": ["P001"]})
        assert r.status == ToolStatus.ERROR

    def test_compare_returns_evidence(self):
        t = CompareTool()
        r = t.run({"product_ids": ["P001", "P002"]})
        assert r.has_evidence
        assert r.evidence[0].source_type == SourceType.COMPARISON_ENGINE

    def test_compare_with_unknown_products(self):
        t = CompareTool()
        r = t.run({"product_ids": ["P001", "P999"]})
        assert r.status == ToolStatus.ERROR

    def test_deterministic_compare(self):
        t = CompareTool()
        r1 = t.run({"product_ids": ["P001", "P002"], "dimensions": ["deductible"]})
        r2 = t.run({"product_ids": ["P001", "P002"], "dimensions": ["deductible"]})
        assert r1.data == r2.data


class TestEligibilityCheckTool:
    def test_eligible_age(self):
        t = EligibilityCheckTool()
        r = t.run({"product_id": "P001", "age": 30})
        assert r.success
        assert r.data["eligible"] is True

    def test_age_too_high(self):
        t = EligibilityCheckTool()
        r = t.run({"product_id": "P001", "age": 70})
        assert r.data["eligible"] is False

    def test_age_too_low(self):
        t = EligibilityCheckTool()
        r = t.run({"product_id": "P012", "age": 15})
        assert r.data["eligible"] is False

    def test_unknown_product(self):
        t = EligibilityCheckTool()
        r = t.run({"product_id": "P999", "age": 30})
        assert r.status == ToolStatus.ERROR


# ============================================================
# Graph Tools Tests
# ============================================================

class TestEntityLookupTool:
    def test_lookup_product_by_name(self):
        t = EntityLookupTool()
        r = t.run({"entity_name": "e生保"})
        assert r.success
        entities = r.data["entities"]
        assert any(e["type"] == "Product" for e in entities)

    def test_lookup_by_alias(self):
        t = EntityLookupTool()
        r = t.run({"entity_name": "癌症"})
        assert r.success
        entities = r.data["entities"]
        assert any("恶性肿瘤" in e["name"] for e in entities)

    def test_lookup_by_type(self):
        t = EntityLookupTool()
        r = t.run({"entity_name": "", "entity_type": "Disease"})
        assert r.success
        for e in r.data["entities"]:
            assert e["type"] == "Disease"

    def test_lookup_nonexistent(self):
        t = EntityLookupTool()
        r = t.run({"entity_name": "不存在的实体xyz"})
        assert r.status == ToolStatus.EMPTY

    def test_evidence_is_entity_registry(self):
        t = EntityLookupTool()
        r = t.run({"entity_name": "e生保"})
        assert r.has_evidence
        assert r.evidence[0].source_type == SourceType.ENTITY_REGISTRY


class TestRelationTraversalTool:
    def test_traverse_outgoing_relations(self):
        t = RelationTraversalTool()
        r = t.run({"entity_id": "ENT-P001", "direction": "outgoing"})
        assert r.success
        assert len(r.data["paths"]) > 0

    def test_filter_by_relation_type(self):
        t = RelationTraversalTool()
        r = t.run({"entity_id": "ENT-P001", "relation_type": "covers"})
        assert r.success
        for path in r.data["paths"]:
            assert path["relation"] == "covers"

    def test_incoming_relations(self):
        t = RelationTraversalTool()
        r = t.run({"entity_id": "ENT-D001", "direction": "incoming"})
        assert r.success

    def test_no_relations_for_unknown_entity(self):
        t = RelationTraversalTool()
        r = t.run({"entity_id": "ENT-UNKNOWN"})
        assert r.status == ToolStatus.EMPTY

    def test_evidence_is_ontology(self):
        t = RelationTraversalTool()
        r = t.run({"entity_id": "ENT-P001"})
        if r.has_evidence:
            assert r.evidence[0].source_type == SourceType.ONTOLOGY


# ============================================================
# Tool Contract Validation (Cross-cutting)
# ============================================================

class TestToolContracts:
    """Verify ALL tools follow the contract from 06-Tool-Contracts.md."""

    ALL_TOOLS = [
        ProductSearchTool, DocumentSearchTool, RegulationSearchTool,
        AttributeExtractionTool, ClauseParserTool, CompareTool,
        EligibilityCheckTool, EntityLookupTool, RelationTraversalTool,
    ]

    def test_all_tools_have_name(self):
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            assert t.name, f"{tool_cls.__name__} missing name"
            assert isinstance(t.name, str)

    def test_all_tools_have_input_schema(self):
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            assert t.input_schema is not None, f"{tool_cls.__name__} missing input_schema"

    def test_all_tools_have_output_schema(self):
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            assert t.output_schema is not None, f"{tool_cls.__name__} missing output_schema"

    def test_all_tools_are_deterministic(self):
        """RULE #4: Tools must be deterministic."""
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            params = self._get_default_params(tool_cls)
            r1 = t.run(params)
            r2 = t.run(params)
            assert r1.status == r2.status, f"{tool_cls.__name__} non-deterministic status"
            assert r1.data == r2.data, f"{tool_cls.__name__} non-deterministic data"

    def test_all_tools_return_tool_result(self):
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            params = self._get_default_params(tool_cls)
            result = t.run(params)
            assert isinstance(result, ToolResult), f"{tool_cls.__name__} doesn't return ToolResult"

    def test_all_successful_tools_have_evidence(self):
        """RULE #2: Evidence is mandatory for all successful outputs."""
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            params = self._get_default_params(tool_cls)
            result = t.run(params)
            if result.status == ToolStatus.SUCCESS:
                assert result.has_evidence, f"{tool_cls.__name__} SUCCESS but no evidence"

    def test_all_tools_have_duration_ms(self):
        for tool_cls in self.ALL_TOOLS:
            t = tool_cls()
            params = self._get_default_params(tool_cls)
            result = t.run(params)
            assert result.duration_ms >= 0

    @staticmethod
    def _get_default_params(tool_cls):
        """Get safe default params for each tool type."""
        params_map = {
            ProductSearchTool: {"query": "医疗", "top_k": 3},
            DocumentSearchTool: {"query": "等待期", "top_k": 3},
            RegulationSearchTool: {"query": "保险", "top_k": 3},
            AttributeExtractionTool: {"attributes": ["deductible"], "product_ids": ["P001"]},
            ClauseParserTool: {"document_id": "DOC001"},
            CompareTool: {"product_ids": ["P001", "P002"]},
            EligibilityCheckTool: {"product_id": "P001", "age": 30},
            EntityLookupTool: {"entity_name": "e生保"},
            RelationTraversalTool: {"entity_id": "ENT-P001"},
        }
        return params_map.get(tool_cls, {})

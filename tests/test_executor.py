"""
Tests for Executor (Sprint 1.3 — Tool Execution).

Covers:
- All 7 tools produce valid outputs
- Evidence is included in every tool output
- Tools are deterministic (same input -> same output)
- Unknown tools return error
"""

import pytest

from runtime.engine.executor import (
    execute_tool,
    execute_product_search,
    execute_document_search,
    execute_regulation_search,
    execute_compare,
    execute_attribute_extraction,
    execute_entity_lookup,
    execute_relation_traversal,
    TOOL_EXECUTORS,
)


class TestToolExecution:
    """Test individual tool functions."""

    def test_product_search_finds_products(self):
        result = execute_tool("product_search", {"query": "医疗", "top_k": 5})
        assert result["success"] is True
        output = result["output"]
        assert "results" in output
        assert len(output["results"]) > 0
        assert output["total_found"] > 0

    def test_product_search_returns_evidence(self):
        result = execute_tool("product_search", {"query": "", "top_k": 3})
        assert len(result["evidence"]) > 0
        for ev in result["evidence"]:
            assert "source" in ev

    def test_document_search_by_type(self):
        result = execute_tool("document_search", {"doc_type": "coverage_clause", "top_k": 3})
        assert result["success"] is True
        output = result["output"]
        for doc in output["results"]:
            assert doc["type"] == "coverage_clause"

    def test_document_search_returns_chunks(self):
        result = execute_tool("document_search", {"doc_type": "", "top_k": 3})
        output = result["output"]
        for doc in output["results"]:
            assert "chunks" in doc
            assert len(doc["chunks"]) > 0

    def test_regulation_search_returns_regulations(self):
        result = execute_tool("regulation_search", {"top_k": 5})
        assert result["success"] is True
        output = result["output"]
        assert len(output["results"]) > 0
        for reg in output["results"]:
            assert "title" in reg
            assert "issuer" in reg
            assert "key_provisions" in reg

    def test_compare_returns_structured_comparison(self):
        result = execute_tool("compare", {
            "comparison_mode": "structured",
            "products": [{"id": "P001"}, {"id": "P002"}]
        })
        assert result["success"] is True
        comp = result["output"]["comparison"]
        assert comp["products_compared"] == 2
        assert "dimensions" in comp

    def test_attribute_extraction_extracts_attributes(self):
        result = execute_tool("attribute_extraction", {
            "attributes": ["coverage", "price", "eligibility"],
            "product_ids": ["P001", "P002"]
        })
        assert result["success"] is True
        output = result["output"]
        assert "results" in output
        assert "P001" in output["results"]

    def test_entity_lookup_finds_products(self):
        result = execute_tool("entity_lookup", {
            "entity_type": "product",
            "max_results": 3
        })
        assert result["success"] is True
        output = result["output"]
        assert len(output["results"]) <= 3
        for r in output["results"]:
            assert "id" in r
            assert "name" in r

    def test_relation_traversal_finds_regulations(self):
        result = execute_tool("relation_traversal", {
            "relation_type": "regulated_by"
        })
        assert result["success"] is True
        output = result["output"]
        assert len(output["relations"]) > 0
        for rel in output["relations"]:
            assert "relation" in rel
            assert rel["relation"] == "regulated_by"

    def test_unknown_tool_returns_error(self):
        result = execute_tool("nonexistent_tool", {})
        assert result["success"] is False
        assert "error" in result
        assert len(result["evidence"]) == 0

    def test_tools_are_deterministic(self):
        """ARCHITECTURE RULE #4: Same input must produce same output."""
        params = {"query": "医疗", "top_k": 5}
        result1 = execute_tool("product_search", params)
        result2 = execute_tool("product_search", params)
        assert result1["output"] == result2["output"]
        assert result1["evidence"] == result2["evidence"]

    def test_all_registered_tools_work(self):
        """Verify every registered tool can be executed without error."""
        for tool_name in TOOL_EXECUTORS:
            result = execute_tool(tool_name, {})
            assert result["success"] is True, f"Tool {tool_name} failed"
            assert "evidence" in result, f"Tool {tool_name} missing evidence"

    def test_evidence_has_source_field(self):
        for tool_name in TOOL_EXECUTORS:
            result = execute_tool(tool_name, {})
            for ev in result["evidence"]:
                assert "source" in ev, f"Tool {tool_name}: evidence missing 'source' field"

    def test_duration_ms_is_present(self):
        result = execute_tool("product_search", {"top_k": 3})
        assert "duration_ms" in result
        assert result["duration_ms"] >= 0  # May be 0 for very fast operations

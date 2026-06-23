"""Tests for catalog → runtime product conversion."""

from runtime.tools.data_loader import _catalog_to_runtime


class TestCatalogToRuntime:
    def test_deductible_preserved_when_present(self):
        p = _catalog_to_runtime({
            "product_id": "P001",
            "name": "测试",
            "category": "百万医疗险",
            "deductible": "年度1万元",
        })
        assert p["deductible"] == 10000

    def test_missing_deductible_marked_unknown(self):
        p = _catalog_to_runtime({
            "product_id": "P002",
            "name": "测试2",
            "category": "重疾险",
        })
        assert p["deductible"] == "unknown"

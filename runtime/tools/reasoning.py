"""Reasoning Tools for Sprint 2 — CompareTool and EligibilityCheckTool."""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from runtime.evidence.contract import make_evidence, SourceType
from runtime.tools.base import BaseTool, ToolResult, ToolStatus
from runtime.tools.data import PRODUCT_CATALOG


from runtime.tools.field_maps import COMPARE_DIMENSIONS
class CompareInput(BaseModel):
    product_ids: List[str] = Field(default_factory=list, min_length=2)
    dimensions: List[str] = Field(default_factory=list)


class CompareOutput(BaseModel):
    comparison: Dict[str, Any] = Field(default_factory=dict)


class CompareTool(BaseTool[CompareInput, CompareOutput]):
    @property
    def name(self) -> str: return "compare"
    @property
    def description(self) -> str: return "结构化对比保险产品"
    @property
    def input_schema(self): return CompareInput
    @property
    def output_schema(self): return CompareOutput

    def execute(self, input_data: CompareInput) -> ToolResult:
        products: List[Dict[str, Any]] = []
        for pid in input_data.product_ids:
            product = next(
                (prod for prod in PRODUCT_CATALOG if prod["product_id"] == pid),
                None,
            )
            if product is not None:
                products.append(product)
        if len(products) < 2:
            return ToolResult(tool_name=self.name, status=ToolStatus.ERROR,
                             error={"code": "INSUFFICIENT_PRODUCTS", "message": "Need 2+ products"})

        dims = input_data.dimensions or list(COMPARE_DIMENSIONS.keys())
        comparison_rows = []
        for dim in dims:
            dim_config = COMPARE_DIMENSIONS.get(dim)
            if not dim_config:
                continue
            row = {"dimension": dim, "unit": dim_config.get("unit", ""),
                   "category": dim_config.get("category", "")}
            fmt_fn = dim_config.get("format")
            for p in products:
                val = self._get_value(p, dim_config)
                if fmt_fn and val is not None:
                    try:
                        val = fmt_fn(val)
                    except Exception:
                        pass
                row[p["product_id"]] = val
                row[f"{p['product_id']}_name"] = p["name"]
            comparison_rows.append(row)

        evidence = [make_evidence("COMPARE_ENGINE", f"compare_{pid}"[:20],
                    "Product comparison result", SourceType.COMPARISON_ENGINE)
                    for pid in input_data.product_ids]

        return ToolResult(tool_name=self.name, status=ToolStatus.SUCCESS,
                         data={"comparison": {"products": [{"id": p["product_id"], "name": p["name"]}
                                                  for p in products],
                                             "rows": comparison_rows}},
                         evidence=evidence)

    @staticmethod
    def _get_value(product: Dict[str, Any], config: Dict[str, Any]) -> Any:
        if "field" in config:
            field = config["field"]
            if "." in field:
                parts = field.split(".")
                val: Any = product
                for part in parts:
                    val = val.get(part, None) if isinstance(val, dict) else None
                    if val is None:
                        return None
                return val
            return product.get(field)
        if "fields" in config:
            return [product.get(f) for f in config["fields"]]
        return None


class EligibilityCheckInput(BaseModel):
    product_id: str
    age: Optional[int] = Field(default=None)
    has_pre_existing: bool = Field(default=False)


class EligibilityCheckOutput(BaseModel):
    eligible: bool = Field(default=False)
    reasons: List[str] = Field(default_factory=list)
    conditions: Dict[str, Any] = Field(default_factory=dict)


class EligibilityCheckTool(BaseTool[EligibilityCheckInput, EligibilityCheckOutput]):
    @property
    def name(self) -> str: return "eligibility_check"
    @property
    def description(self) -> str: return "检查投保资格"
    @property
    def input_schema(self): return EligibilityCheckInput
    @property
    def output_schema(self): return EligibilityCheckOutput

    def execute(self, input_data: EligibilityCheckInput) -> ToolResult:
        product = next((p for p in PRODUCT_CATALOG if p["product_id"] == input_data.product_id), None)
        if not product:
            return ToolResult(tool_name=self.name, status=ToolStatus.ERROR,
                             error={"code": "PRODUCT_NOT_FOUND", "message": f"Unknown product: {input_data.product_id}"})

        reasons = []
        eligible = True
        eligibility = product.get("eligibility", {})

        if input_data.age is not None:
            min_age = eligibility.get("min_age", 0)
            max_age = eligibility.get("max_age", 999)
            if input_data.age < min_age:
                eligible = False
                reasons.append(f"Age {input_data.age} below minimum {min_age}")
            elif input_data.age > max_age:
                eligible = False
                reasons.append(f"Age {input_data.age} exceeds maximum {max_age}")
            else:
                reasons.append(f"Age {input_data.age} within range [{min_age}, {max_age}]")

        if input_data.has_pre_existing:
            exclusions = product.get("exclusions", [])
            if "既往症" in exclusions or eligibility.get("pre_existing_excluded", True):
                eligible = False
                reasons.append("Pre-existing condition excluded by product terms")

        evidence = [make_evidence(input_data.product_id, input_data.product_id,
                    f"Eligibility check: {'eligible' if eligible else 'not eligible'}",
                    SourceType.PRODUCT_CATALOG, document_title=product["name"])]

        return ToolResult(tool_name=self.name,
                         status=ToolStatus.SUCCESS,
                         data={"eligible": eligible, "reasons": reasons,
                              "conditions": eligibility},
                         evidence=evidence)

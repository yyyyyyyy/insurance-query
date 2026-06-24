"""Memory facts — structured facts written by tools and consumed by planner/retrieval."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class MemoryFact:
    key: str
    value: Any
    source_tool: str = ""
    fact_type: str = "generic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "source_tool": self.source_tool,
            "fact_type": self.fact_type,
        }


def extract_facts_from_tool(tool_name: str, tool_data: Dict[str, Any]) -> List[MemoryFact]:
    """Extract memory facts from successful tool output."""
    facts: List[MemoryFact] = []

    if tool_name == "product_search":
        products = tool_data.get("products", [])
        for p in products[:3]:
            pid = p.get("product_id", "")
            name = p.get("name", "")
            if pid:
                facts.append(MemoryFact(f"product:{pid}", name, tool_name, "product"))
            if name:
                facts.append(MemoryFact(f"product_name:{name}", pid, tool_name, "product"))

    elif tool_name == "compare":
        comp = tool_data.get("comparison", {})
        products = comp.get("products", [])
        ids = [
            p.get("id") or p.get("product_id")
            for p in products
            if p.get("id") or p.get("product_id")
        ]
        if ids:
            facts.append(MemoryFact("last_compared_products", ids, tool_name, "comparison"))
        if products:
            names = [p.get("name", "") for p in products]
            facts.append(MemoryFact("last_compared_names", names, tool_name, "comparison"))

    elif tool_name == "attribute_extraction":
        results = tool_data.get("results", {})
        product_ids = list(results.keys()) if isinstance(results, dict) else tool_data.get("product_ids", [])
        if product_ids:
            facts.append(MemoryFact("last_product_ids", product_ids, tool_name, "attributes"))
        if isinstance(results, dict):
            for pid, attrs in results.items():
                if isinstance(attrs, dict):
                    for k, v in attrs.items():
                        facts.append(MemoryFact(f"attr:{pid}:{k}", v, tool_name, "attribute"))

    elif tool_name == "eligibility_check":
        result = tool_data.get("eligible")
        product_id = tool_data.get("product_id", "")
        if product_id:
            facts.append(MemoryFact("last_eligibility_product", product_id, tool_name, "eligibility"))
        facts.append(MemoryFact("last_eligibility_result", result, tool_name, "eligibility"))

    elif tool_name == "entity_lookup":
        entities = tool_data.get("entities", [])
        for e in entities[:5]:
            eid = e.get("entity_id", "")
            name = e.get("name", "")
            if eid:
                facts.append(MemoryFact(f"entity:{eid}", name, tool_name, "entity"))

    return facts


def merge_facts(existing: Dict[str, Any], new_facts: List[MemoryFact]) -> Dict[str, Any]:
    """Merge new facts into session facts dict."""
    merged = dict(existing)
    for f in new_facts:
        merged[f.key] = f.to_dict()
    return merged


def extract_product_ids_from_facts(facts: Dict[str, Any]) -> List[str]:
    """Extract product IDs from session facts.

    Single source of truth for deriving ``previous_product_ids`` from a
    facts dict. Recognizes:
      - ``product:<pid>`` keys (dict-valued)
      - ``last_compared_products`` (dict with ``value`` list)
      - ``last_product_ids`` (dict with ``value`` list)

    Returns de-duplicated IDs preserving first-seen order.
    """
    ids: List[str] = []
    for key, val in (facts or {}).items():
        if key.startswith("product:") and isinstance(val, dict):
            pid = key.split(":", 1)[1]
            if pid:
                ids.append(pid)
        if key == "last_compared_products" and isinstance(val, dict):
            ids.extend(val.get("value", []) or [])
        if key == "last_product_ids" and isinstance(val, dict):
            ids.extend(val.get("value", []) or [])
    return list(dict.fromkeys(ids))

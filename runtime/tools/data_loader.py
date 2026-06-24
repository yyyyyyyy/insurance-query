"""
Data Loader — Load knowledge assets from knowledge_pack/ into runtime format.

Replaces hardcoded PRODUCT_CATALOG with dynamic loading from
knowledge_pack/products/catalog.json. Also supports FAQ and rule loading.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

logger = logging.getLogger(__name__)

_KNOWLEDGE_PACK_ROOT = Path(__file__).resolve().parents[2] / "knowledge_pack"


def _read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return cast(Dict[str, Any], json.load(f))


# ============================================================
# Product Loading
# ============================================================

# Default fields for runtime tools (set when catalog lacks them)
DEFAULT_PRODUCT_TEMPLATE: Dict[str, Any] = {
    "product_type": "",
    "company_short": "",
    "is_guaranteed_renewal": False,
    "guaranteed_renewal_years": 0,
    "max_renewal_age": 100,
    "waiting_period_days": 30,
    "deductible": 10000,
    "coverage_limit": 3000000,
    "critical_illness_limit": 3000000,
    "outpatient_limit": 0,
    "premium_min": 200,
    "premium_max": 1500,
    "premium_reference": {"age_30": 350, "age_40": 550, "age_50": 900},
    "eligibility": {"min_age": 0, "max_age": 65, "health_check_required": True},
    "covered_diseases": [],
    "exclusions": [],
    "special_services": [],
}


def _catalog_to_runtime(product_entry: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a product entry from catalog.json to the runtime format used by tools."""
    p = dict(DEFAULT_PRODUCT_TEMPLATE)
    p["product_id"] = product_entry.get("product_id", "")
    p["name"] = product_entry.get("name", "")

    # Category mapping
    category = product_entry.get("category", "")
    p["product_type"] = _resolve_product_type(category)
    p["company"] = product_entry.get("company", "")
    p["company_short"] = _resolve_company_short(p["company"])

    # Guaranteed renewal
    gr = product_entry.get("guaranteed_renewal", "")
    if gr and "保证续保" in str(gr):
        p["is_guaranteed_renewal"] = True
        # Attempt to extract years
        import re
        m = re.search(r"(\d+)年", str(gr))
        if m:
            p["guaranteed_renewal_years"] = int(m.group(1))

    # Deductible
    if "deductible" in product_entry:
        deductible_num = _parse_deductible(str(product_entry["deductible"]))
        if deductible_num is not None:
            p["deductible"] = deductible_num

    # Waiting period
    if "waiting_period" in product_entry:
        import re
        m = re.search(r"(\d+)", str(product_entry["waiting_period"]))
        if m:
            p["waiting_period_days"] = int(m.group(1))

    # Coverage limits
    coverage = product_entry.get("coverage")
    if isinstance(coverage, dict) and coverage:
        for key in coverage:
            val = str(coverage[key])
            nums = _extract_number(val)
            if nums is None:
                continue
            if key in ("general_hospitalization", "coverage_limit"):
                p["coverage_limit"] = max(p["coverage_limit"], nums)
            if "critical" in key:
                p["critical_illness_limit"] = max(p["critical_illness_limit"], nums)

    # Premium
    prem = product_entry.get("premium_reference", {})
    if isinstance(prem, dict) and prem:
        p["premium_reference"] = {k: v for k, v in prem.items() if isinstance(v, (int, float))}
        vals = [v for v in prem.values() if isinstance(v, (int, float))]
        if vals:
            p["premium_min"] = min(vals)
            p["premium_max"] = max(vals) * 2  # rough upper bound

    # Age
    p["eligibility"] = {
        "min_age": product_entry.get("min_age", 0) or 0,
        "max_age": product_entry.get("max_age", 65) or 65,
        "health_check_required": True,
    }

    # Exclusions
    exclusions = product_entry.get("exclusions", [])
    if isinstance(exclusions, list):
        p["exclusions"] = exclusions

    # Diseases (derive from category and coverage)
    p["covered_diseases"] = _resolve_diseases_for_category(category)

    if "deductible" not in product_entry:
        p["deductible"] = "unknown"
    if "coverage" not in product_entry:
        p["coverage_limit"] = "unknown"
        p["critical_illness_limit"] = "unknown"
    if "premium_reference" not in product_entry:
        p["premium_reference"] = {}
        p["premium_min"] = "unknown"
        p["premium_max"] = "unknown"

    return p


def _resolve_product_type(category: str) -> str:
    mapping = {
        "百万医疗险": "医疗险",
        "重疾险": "重疾险",
        "意外险": "意外险",
        "定期寿险": "定期寿险",
        "年金险": "年金险",
    }
    for key, val in mapping.items():
        if key in category:
            return val
    return category if category else "医疗险"


def _resolve_company_short(company: str) -> str:
    mapping = {
        "平安健康保险": "平安健康",
        "人保健康": "人保健康",
        "太平洋健康险": "太平洋健康",
        "人保寿险": "人保寿险",
        "众安保险": "众安保险",
        "泰康在线": "泰康在线",
        "平安人寿保险": "平安人寿",
        "中国人寿": "中国人寿",
        "信泰人寿": "信泰人寿",
        "复星联合": "复星联合",
    }
    for key, val in mapping.items():
        if key in company:
            return val
    return company[:4]


def _parse_deductible(deductible_str: str) -> Optional[int]:
    """Parse deductible string like '年度1万元' or '0免赔(1万以下报30%)'."""
    import re
    m = re.search(r"(\d+)\s*万", deductible_str)
    if m:
        return int(m.group(1)) * 10000
    m = re.search(r"0\s*免赔", deductible_str)
    if m:
        return 0
    m = re.search(r"(\d+)\s*元", deductible_str)
    if m:
        return int(m.group(1))
    return None


def _extract_number(text: str) -> Optional[int]:
    """Extract a number like 400万 or 1000万 from text."""
    import re
    m = re.search(r"(\d+)\s*万", text)
    if m:
        return int(m.group(1)) * 10000
    m = re.search(r"(\d+)", text)
    if m:
        return int(m.group(1))
    return None


def _resolve_diseases_for_category(category: str) -> List[str]:
    if "重疾" in category:
        return ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症", "重大器官移植术",
                "冠状动脉搭桥术", "终末期肾病", "多个肢体缺失", "严重烧伤",
                "瘫痪", "深度昏迷"]
    if "医疗" in category:
        return ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症", "重大器官移植术",
                "冠状动脉搭桥术", "终末期肾病"]
    if "意外" in category:
        return ["意外身故", "意外伤残", "意外医疗"]
    return ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症"]


def load_product_catalog() -> List[Dict[str, Any]]:
    """Load all products from knowledge_pack/products/catalog.json.

    Returns a list of product dicts in the runtime format used by tools.
    """
    path = _KNOWLEDGE_PACK_ROOT / "products" / "catalog.json"
    try:
        data = _read_json(path)
        products = data.get("products", [])
        result = [_catalog_to_runtime(p) for p in products]
        logger.info("Loaded %d products from catalog.json", len(result))
        return result
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load product catalog: %s. Returning empty catalog.", exc)
        return []


# ============================================================
# FAQ Loading
# ============================================================

def _load_document_bundle(path: Path, key: str = "documents") -> List[Dict[str, Any]]:
    """Load a JSON bundle that contains a list of documents under *key*."""
    try:
        data = _read_json(path)
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load documents from %s: %s", path.name, exc)
        return []
    docs = data.get(key, [])
    if not isinstance(docs, list):
        return []
    return [d for d in docs if isinstance(d, dict) and d.get("chunks")]


def load_ingested_documents() -> List[Dict[str, Any]]:
    """Load imported documents from knowledge_pack/chunks/ingested_documents.json."""
    path = _KNOWLEDGE_PACK_ROOT / "chunks" / "ingested_documents.json"
    docs = _load_document_bundle(path)
    if docs:
        total_chunks = sum(len(d.get("chunks", [])) for d in docs)
        logger.info(
            "Loaded %d ingested documents (%d chunks) from %s",
            len(docs), total_chunks, path.name,
        )
    return docs


def load_ingested_policy_documents() -> List[Dict[str, Any]]:
    """Backward-compatible alias."""
    return load_ingested_documents()


# ============================================================
# Rule Loading
# ============================================================

def load_rules() -> List[Dict[str, Any]]:
    """Load all 45 decision rules from knowledge_pack/rules/*.json.

    Returns a flat list of rule dicts.
    """
    rules_dir = _KNOWLEDGE_PACK_ROOT / "rules"
    rule_files = [
        "underwriting_rules.json", "claim_rules.json",
        "eligibility_rules.json", "clause_rules.json",
    ]

    all_rules: List[Dict[str, Any]] = []
    for fname in rule_files:
        path = rules_dir / fname
        try:
            data = _read_json(path)
            rules = data.get("rules", [])
            all_rules.extend(rules)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load rules from %s: %s", fname, exc)

    logger.info("Loaded %d rules from %d files", len(all_rules), len(rule_files))
    return all_rules


def find_matching_rules(intent_type: str, rules: List[Dict[str, Any]],
                        limit: int = 5) -> List[Dict[str, Any]]:
    """Find rules relevant to a given intent type.

    Mapping:
      coverage_question, product_comparison → claim + clause rules
      eligibility_check → eligibility + underwriting rules
      regulation_lookup → all rules with regulatory_document source
      claim_process → claim rules
      general_inquiry → all rules
    """
    domain_map = {
        "coverage_question": ["claim", "clause"],
        "product_comparison": ["claim", "clause"],
        "eligibility_check": ["eligibility", "underwriting"],
        "regulation_lookup": [],  # will filter by source below
        "claim_process": ["claim"],
        "price_inquiry": ["claim", "clause"],
        "general_inquiry": [],
    }

    domains = domain_map.get(intent_type, [])

    if intent_type == "regulation_lookup":
        matching = [r for r in rules if r.get("source") == "regulatory_document"]
        return matching[:limit]

    if domains:
        matching = [r for r in rules if r.get("domain") in domains]
    else:
        matching = list(rules)

    return matching[:limit]

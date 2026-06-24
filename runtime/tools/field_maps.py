"""Unified field maps for compare and attribute extraction tools."""

from __future__ import annotations

from typing import Any, Dict

COMPARE_DIMENSIONS: Dict[str, Dict[str, Any]] = {
    "waiting_period": {"field": "waiting_period_days", "unit": "天", "category": "保障条款"},
    "deductible": {"field": "deductible", "unit": "元", "category": "费用相关"},
    "coverage_limit": {"field": "coverage_limit", "unit": "元", "category": "保障额度"},
    "critical_illness_limit": {"field": "critical_illness_limit", "unit": "元", "category": "保障额度"},
    "guaranteed_renewal": {
        "field": "is_guaranteed_renewal", "unit": "", "category": "续保条款",
        "format": lambda v: "保证续保" if v else "不保证续保",
    },
    "guaranteed_renewal_years": {"field": "guaranteed_renewal_years", "unit": "年", "category": "续保条款"},
    "outpatient_coverage": {"field": "outpatient_limit", "unit": "元", "category": "保障额度"},
    "premium_30": {"field": "premium_reference.age_30", "unit": "元/年", "category": "保费"},
    "premium_40": {"field": "premium_reference.age_40", "unit": "元/年", "category": "保费"},
    "premium_50": {"field": "premium_reference.age_50", "unit": "元/年", "category": "保费"},
    "max_age": {"field": "eligibility.max_age", "unit": "岁", "category": "投保条件"},
    "min_age": {"field": "eligibility.min_age", "unit": "岁", "category": "投保条件"},
    "premium_min": {"field": "premium_min", "unit": "元/年", "category": "保费"},
    "premium_max": {"field": "premium_max", "unit": "元/年", "category": "保费"},
    "premium_range": {"fields": ["premium_min", "premium_max"], "unit": "元/年", "category": "保费"},
    "company": {"field": "company", "unit": "", "category": "基本信息"},
    "product_type": {"field": "product_type", "unit": "", "category": "基本信息"},
    "health_check": {
        "field": "eligibility.health_check_required", "unit": "", "category": "投保条件",
        "format": lambda v: "需要健康告知" if v else "无需健康告知",
    },
    "covered_diseases_count": {
        "field": "covered_diseases", "unit": "种", "category": "保障范围",
        "format": lambda v: len(v) if isinstance(v, (list, dict)) else 0,
    },
}

EXTRACTION_PATTERNS: Dict[str, list] = {
    "waiting_period": ["waiting_period_days"],
    "deductible": ["deductible"],
    "coverage_limit": ["coverage_limit"],
    "critical_illness_limit": ["critical_illness_limit"],
    "outpatient_limit": ["outpatient_limit"],
    "premium": ["premium_min", "premium_max", "premium_reference"],
    "guaranteed_renewal": ["is_guaranteed_renewal", "guaranteed_renewal_years"],
    "eligibility": ["eligibility"],
    "covered_diseases": ["covered_diseases"],
    "exclusions": ["exclusions"],
    "special_services": ["special_services"],
}

"""
Structured Knowledge Store — Embedded data for Sprint 2 tools.

Products are loaded from knowledge_pack/products/catalog.json at import time.
Falls back to 4 hardcoded products if the JSON file is unavailable.
"""

from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

# Legacy fallback (4 products) — used when catalog.json is unavailable
_LEGACY_PRODUCT_CATALOG: List[Dict[str, Any]] = [
    {
        "product_id": "P001", "name": "e生保·百万医疗", "product_type": "医疗险",
        "company": "平安健康保险", "company_short": "平安健康",
        "is_guaranteed_renewal": False, "max_renewal_age": 99,
        "waiting_period_days": 30, "deductible": 10000,
        "coverage_limit": 3000000, "critical_illness_limit": 6000000,
        "outpatient_limit": 50000,
        "premium_min": 200, "premium_max": 1500,
        "premium_reference": {"age_30": 356, "age_40": 569, "age_50": 1098},
        "eligibility": {"min_age": 0, "max_age": 65, "health_check_required": True},
        "covered_diseases": ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症", "重大器官移植术", "冠状动脉搭桥术", "终末期肾病"],
        "exclusions": ["既往症", "美容整形", "牙科治疗", "生育相关费用", "故意自伤"],
        "special_services": ["就医绿色通道", "二次诊疗", "住院垫付"],
    },
    {
        "product_id": "P002", "name": "好医保·长期医疗", "product_type": "医疗险",
        "company": "人保健康保险", "company_short": "人保健康",
        "is_guaranteed_renewal": True, "guaranteed_renewal_years": 20,
        "max_renewal_age": 100, "waiting_period_days": 30, "deductible": 10000,
        "coverage_limit": 4000000, "critical_illness_limit": 4000000,
        "outpatient_limit": 0,
        "premium_min": 180, "premium_max": 1200,
        "premium_reference": {"age_30": 289, "age_40": 458, "age_50": 876},
        "eligibility": {"min_age": 0, "max_age": 60, "health_check_required": True},
        "covered_diseases": ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症", "重大器官移植术", "冠状动脉搭桥术"],
        "exclusions": ["既往症", "生育相关费用"],
        "special_services": ["住院垫付", "专家问诊"],
    },
    {
        "product_id": "P003", "name": "平安福·重疾险", "product_type": "重疾险",
        "company": "平安人寿保险", "company_short": "平安人寿",
        "is_guaranteed_renewal": False,
        "waiting_period_days": 90, "deductible": 0,
        "coverage_limit": 500000, "critical_illness_limit": 500000,
        "mild_illness_limit": 100000, "moderate_illness_limit": 200000,
        "death_benefit": 500000,
        "premium_min": 5000, "premium_max": 15000,
        "premium_reference": {"age_30": 8500, "age_40": 12000, "age_50": 14500},
        "eligibility": {"min_age": 18, "max_age": 55, "health_check_required": True},
        "covered_diseases": {"critical": 100, "mild": 50, "moderate": 20},
        "exclusions": ["故意伤害", "战争", "核辐射", "吸毒", "酒驾"],
        "special_services": ["保费豁免", "身故返还"],
    },
    {
        "product_id": "P004", "name": "微医保·百万医疗", "product_type": "医疗险",
        "company": "泰康在线", "company_short": "泰康在线",
        "is_guaranteed_renewal": False, "max_renewal_age": 100,
        "waiting_period_days": 30, "deductible": 10000,
        "coverage_limit": 3000000, "critical_illness_limit": 6000000,
        "outpatient_limit": 0,
        "premium_min": 150, "premium_max": 1000,
        "premium_reference": {"age_30": 245, "age_40": 398, "age_50": 756},
        "eligibility": {"min_age": 0, "max_age": 65, "health_check_required": True},
        "covered_diseases": ["恶性肿瘤", "急性心肌梗塞", "脑中风后遗症"],
        "exclusions": ["既往症", "美容整形"],
        "special_services": ["在线问诊"],
    },
]


def _load_products() -> List[Dict[str, Any]]:
    """Load products from catalog.json, with fallback to legacy data."""
    try:
        from runtime.tools.data_loader import load_product_catalog
        products = load_product_catalog()
        if products and len(products) > 0:
            logger.info("Loaded %d products from catalog.json", len(products))
            return products
    except Exception as exc:
        logger.warning("Failed to load catalog.json: %s. Using legacy data.", exc)
    logger.info("Using legacy PRODUCT_CATALOG (%d products)", len(_LEGACY_PRODUCT_CATALOG))
    return list(_LEGACY_PRODUCT_CATALOG)


PRODUCT_CATALOG: List[Dict[str, Any]] = _load_products()

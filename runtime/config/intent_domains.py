"""Shared intent → rule domain mapping for planner, rules engine, and data loader."""

from __future__ import annotations

from typing import Dict, List

INTENT_DOMAIN_MAP: Dict[str, List[str]] = {
    "product_comparison": ["claim", "clause"],
    "coverage_question": ["claim", "clause"],
    "claim_process": ["claim"],
    "eligibility_check": ["eligibility", "underwriting"],
    "regulation_lookup": [],  # filtered by regulatory_document source
    "price_inquiry": ["claim", "clause"],
    "general_inquiry": [],
}

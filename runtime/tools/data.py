"""
Structured Knowledge Store — products loaded from knowledge_pack/products/catalog.json.
"""

from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)


def _load_products() -> List[Dict[str, Any]]:
    try:
        from runtime.tools.data_loader import load_product_catalog
        products = load_product_catalog()
        logger.info("Loaded %d products from catalog.json", len(products))
        return products
    except Exception as exc:
        logger.warning("Failed to load catalog.json: %s", exc)
        return []


PRODUCT_CATALOG: List[Dict[str, Any]] = _load_products()

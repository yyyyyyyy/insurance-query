"""Shared filename conventions for policy document fetch and ingest."""

from __future__ import annotations

import re
from typing import Any, Dict


def safe_product_name(name: str) -> str:
    return name.replace("·", "_").replace("/", "_")


def product_output_filename(product: Dict[str, Any], ext: str = ".pdf") -> str:
    """Canonical on-disk filename for a product clause document."""
    pid = product["product_id"]
    safe_name = safe_product_name(product.get("name", pid))
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{pid}_{safe_name}{ext}"


def regulation_output_filename(regulation: Dict[str, Any], ext: str = ".txt") -> str:
    """Canonical filename for a regulation document under regulations/documents/."""
    rid = regulation["regulation_id"]
    title = regulation.get("title", rid)
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:40]
    if not ext.startswith("."):
        ext = f".{ext}"
    return f"{rid}_{safe_title}{ext}"

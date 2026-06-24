"""Memory resolver — follow-up query enrichment and pronoun resolution."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from infra.db.session_store import WorkingMemory

# Pronouns / deixis that signal a follow-up question referring to a
# previous turn's subject. ``其`` alone is too common in Chinese (means
# "its/their" in many unrelated contexts), so we require the explicit
# compounds ``其中`` / ``其它`` / ``其他`` instead. ``还有`` was removed
# because it appears frequently in non-anaphoric questions (e.g.
# "还有没有别的险种") and produced too many false positives.
FOLLOW_UP_MARKERS = re.compile(
    r"(它|那个|这个|刚才|上一个|之前|前述|该产?品|其中|其它|其他|同样)"
)

PRODUCT_REF_MARKERS = re.compile(
    r"(免赔额|等待期|保费|续保|理赔|除外)"
)


def expand_query_for_retrieval(base_query: str, memory_context: Dict[str, Any]) -> str:
    """Expand retrieval query with memory products, IDs, and facts."""
    parts = [base_query.strip()]
    seen = {base_query.strip()}

    for prod in memory_context.get("previous_products", [])[:2]:
        if prod and prod not in seen:
            parts.append(prod)
            seen.add(prod)

    for ent in memory_context.get("previous_entities", [])[:2]:
        if ent and ent not in seen:
            parts.append(ent)
            seen.add(ent)

    for pid in memory_context.get("previous_product_ids", [])[:2]:
        token = f"product_id:{pid}"
        if token not in seen:
            parts.append(token)
            seen.add(token)

    facts = memory_context.get("facts", {}) or {}
    for key, val in facts.items():
        if key == "last_compared_products" and isinstance(val, dict):
            for pid in val.get("value", [])[:2]:
                token = f"product_id:{pid}"
                if token not in seen:
                    parts.append(token)
                    seen.add(token)
        if key.startswith("attr:") and isinstance(val, dict):
            snippet = f"{key.split(':', 1)[-1]}:{val.get('value', '')}"
            if snippet not in seen:
                parts.append(snippet)
                seen.add(snippet)

    return " ".join(parts)


def resolve_query(
    working_memory: Optional["WorkingMemory"],
    session_id: str,
    query: str,
) -> Dict[str, Any]:
    """Resolve follow-up references using session working memory.

    Returns:
        resolved_query: possibly enriched query text
        injected_entities: entities to merge into intent
        is_follow_up: whether this is a follow-up turn
        memory_context: context dict for planner/retrieval
    """
    memory_context: Dict[str, Any] = {
        "is_follow_up": False,
        "previous_intent": "",
        "previous_products": [],
        "previous_entities": [],
        "previous_product_ids": [],
        "turn_count": 0,
        "facts": {},
        "active_process": None,
    }
    injected_entities: List[Dict[str, Any]] = []
    resolved_query = query

    if not working_memory:
        retrieval_query = expand_query_for_retrieval(resolved_query, memory_context)
        return {
            "resolved_query": resolved_query,
            "retrieval_query": retrieval_query,
            "injected_entities": injected_entities,
            "is_follow_up": False,
            "memory_context": memory_context,
        }

    memory_context = working_memory.get_context_for_query(session_id)
    ctx = working_memory.get_or_create(session_id)
    memory_context["facts"] = dict(ctx.facts)
    memory_context["active_process"] = ctx.active_process
    memory_context["previous_product_ids"] = _extract_product_ids(ctx)

    turn_count = memory_context.get("turn_count", 0)
    is_follow_up = bool(
        turn_count > 0
        and (
            FOLLOW_UP_MARKERS.search(query)
            or PRODUCT_REF_MARKERS.search(query)
        )
    )
    memory_context["is_follow_up"] = is_follow_up

    if not is_follow_up:
        retrieval_query = expand_query_for_retrieval(resolved_query, memory_context)
        return {
            "resolved_query": resolved_query,
            "retrieval_query": retrieval_query,
            "injected_entities": injected_entities,
            "is_follow_up": False,
            "memory_context": memory_context,
        }

    # Inject previous products as entities
    prev_products = memory_context.get("previous_products", [])
    prev_entities = memory_context.get("previous_entities", [])
    prev_ids = memory_context.get("previous_product_ids", [])

    primary_product = prev_products[0] if prev_products else (
        prev_entities[0] if prev_entities else ""
    )

    if not primary_product and prev_ids:
        try:
            from runtime.tools.data import PRODUCT_CATALOG
            for pid in prev_ids[:2]:
                prod = next(
                    (p for p in PRODUCT_CATALOG if p.get("product_id") == pid),
                    None,
                )
                if prod and prod.get("name"):
                    primary_product = prod["name"]
                    break
        except Exception:
            pass

    if primary_product:
        try:
            from runtime.tools.data import PRODUCT_CATALOG
            known = {
                p["product_id"] for p in PRODUCT_CATALOG
            } | {p.get("name", "") for p in PRODUCT_CATALOG}
            if primary_product not in known and not any(
                primary_product in p.get("name", "") for p in PRODUCT_CATALOG
            ):
                primary_product = ""
        except Exception:
            pass

    if primary_product:
        injected_entities.append({
            "type": "product",
            "value": primary_product,
            "source": "memory",
        })
        # Enrich query text for intent classifier
        if primary_product not in query:
            resolved_query = f"{query}（指{primary_product}）"

    for pid in prev_ids[:2]:
        injected_entities.append({
            "type": "product_id",
            "value": pid,
            "source": "memory",
        })

    retrieval_query = expand_query_for_retrieval(resolved_query, memory_context)
    return {
        "resolved_query": resolved_query,
        "retrieval_query": retrieval_query,
        "injected_entities": injected_entities,
        "is_follow_up": is_follow_up,
        "memory_context": memory_context,
    }


def _extract_product_ids(ctx) -> List[str]:
    """Extract product IDs from session facts and history.

    Delegates to the shared helper in runtime.memory.facts to avoid
    divergent implementations across the codebase.
    """
    from runtime.memory.facts import extract_product_ids_from_facts
    facts = getattr(ctx, "facts", {}) or {}
    return extract_product_ids_from_facts(facts)


def merge_entities_into_intent(
    intent: Dict[str, Any],
    injected: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge memory-injected entities into intent result."""
    if not injected:
        return intent
    existing = list(intent.get("entities", []))
    seen = {(e.get("type"), e.get("value")) for e in existing}
    for ent in injected:
        key = (ent.get("type"), ent.get("value"))
        if key not in seen:
            existing.append(ent)
            seen.add(key)
    intent = dict(intent)
    intent["entities"] = existing
    if any(e.get("source") == "memory" for e in injected):
        intent["memory_enriched"] = True
    return intent

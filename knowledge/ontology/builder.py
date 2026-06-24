"""
Ontology Builder — Populates OntologyGraph from knowledge_pack catalogs.

Products: loaded from knowledge_pack/products/catalog.json (single source of truth).
Diseases, coverages, regulations, rules: static reference entities aligned with
knowledge_pack/regulations/catalog.json where applicable.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from knowledge.ontology.graph import (
    EntityType,
    OntologyEntity,
    OntologyGraph,
    OntologyRelation,
    RelationType,
)

_ROOT = Path(__file__).resolve().parents[2]


def _load_json(rel_path: str) -> Dict[str, Any]:
    path = _ROOT / rel_path
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _product_aliases(name: str, category: str) -> List[str]:
    aliases: List[str] = []
    if "·" in name:
        aliases.append(name.split("·", 1)[0])
    short = re.sub(r"\(.*?\)", "", name).strip()
    if short and short != name:
        aliases.append(short)
    if category and category not in name:
        aliases.append(category)
    return list(dict.fromkeys(a for a in aliases if a))


def _map_category_to_product_type(category: str) -> str:
    if "医疗" in category:
        return "医疗险"
    if "重疾" in category:
        return "重疾险"
    if "意外" in category:
        return "意外险"
    if "寿险" in category or "定期" in category:
        return "寿险"
    return category or "保险"


def _add_products_from_catalog(g: OntologyGraph) -> List[str]:
    catalog = _load_json("knowledge_pack/products/catalog.json")
    product_ids: List[str] = []
    for p in catalog.get("products", []):
        pid = p["product_id"]
        eid = f"ENT-{pid}"
        category = p.get("category", "")
        aliases = _product_aliases(p.get("name", pid), category)
        props: Dict[str, Any] = {
            "product_type": _map_category_to_product_type(category),
            "company": p.get("company", ""),
            "category": category,
        }
        gr = p.get("guaranteed_renewal", "")
        if gr and "保证续保" in str(gr):
            props["guaranteed_renewal"] = True
            m = re.search(r"(\d+)年", str(gr))
            if m:
                props["guaranteed_renewal_years"] = int(m.group(1))
        else:
            props["guaranteed_renewal"] = False
        g.add_entity(OntologyEntity(
            eid, p.get("name", pid), EntityType.PRODUCT,
            aliases=aliases, properties=props,
        ))
        product_ids.append(eid)
    return product_ids


def _add_static_entities(g: OntologyGraph) -> None:
    diseases = [
        ("ENT-D001", "恶性肿瘤", ["癌症", "肿瘤"], "重大疾病"),
        ("ENT-D002", "急性心肌梗塞", ["心肌梗塞", "心梗"], "重大疾病"),
        ("ENT-D003", "脑中风后遗症", ["脑中风", "中风"], "重大疾病"),
        ("ENT-D004", "冠状动脉搭桥术", ["冠脉搭桥"], "重大疾病"),
        ("ENT-D005", "糖尿病", ["II型糖尿病"], "慢性病"),
    ]
    for eid, name, aliases, cat in diseases:
        g.add_entity(OntologyEntity(
            eid, name, EntityType.DISEASE, aliases=aliases,
            properties={"category": cat},
        ))

    coverages: List[tuple[str, str, List[str], Dict[str, Any]]] = [
        ("ENT-C001", "住院医疗保险金", ["住院医疗", "住院保障"], {}),
        ("ENT-C002", "重大疾病保险金", ["重疾保障", "重疾赔付"], {}),
        ("ENT-C003", "门诊手术医疗保险金", ["门诊手术", "门诊保障"], {}),
        ("ENT-C004", "轻度疾病保险金", ["轻症保障", "轻症"], {}),
        ("ENT-C005", "身故保险金", ["身故保障", "死亡赔付"], {}),
        ("ENT-C006", "保证续保", ["保证续保条款", "续保保障"], {"category": "续保条款"}),
    ]
    for eid, name, aliases, props in coverages:
        g.add_entity(OntologyEntity(eid, name, EntityType.COVERAGE, aliases=aliases, properties=props))

    try:
        reg_catalog = _load_json("knowledge_pack/regulations/catalog.json")
        for reg in reg_catalog.get("regulations", [])[:30]:
            rid = reg.get("regulation_id", "")
            if not rid:
                continue
            eid = f"ENT-{rid}"
            title = reg.get("title", rid)
            aliases = [title[:10]] if len(title) > 10 else []
            g.add_entity(OntologyEntity(
                eid, title, EntityType.REGULATION, aliases=aliases,
                properties={
                    "issuer": reg.get("agency", reg.get("issuer", "")),
                    "year": reg.get("year"),
                    "regulation_id": rid,
                },
            ))
    except (FileNotFoundError, json.JSONDecodeError):
        fallback_regs: List[tuple[str, str, List[str], Dict[str, Any]]] = [
            ("ENT-REG001", "健康保险管理办法", ["健康险管理办法"], {"issuer": "银保监会", "year": 2019}),
            ("ENT-REG002", "重大疾病保险疾病定义使用规范", ["重疾定义规范"], {"year": 2020}),
            ("ENT-REG003", "中华人民共和国保险法", ["保险法"], {"year": 2015}),
        ]
        for eid, name, aliases, reg_props in fallback_regs:
            g.add_entity(OntologyEntity(eid, name, EntityType.REGULATION, aliases=aliases, properties=reg_props))

    rules: List[tuple[str, str, List[str], Dict[str, Any]]] = [
        ("ENT-RL001", "等待期", ["等待期规则"], {"max_days": 180}),
        ("ENT-RL002", "免赔额", ["免赔额规则", "起付线"], {}),
        ("ENT-RL003", "犹豫期", ["冷静期"], {"min_days": 15}),
        ("ENT-RL004", "如实告知", ["健康告知", "如实告知义务"], {}),
    ]
    for eid, name, aliases, rule_props in rules:
        g.add_entity(OntologyEntity(eid, name, EntityType.RULE, aliases=aliases, properties=rule_props))


def _add_relations(g: OntologyGraph, product_ids: List[str]) -> None:
    medical = [eid for eid in product_ids if eid in g._entities and "医疗" in g._entities[eid].properties.get("product_type", "")]
    critical = [eid for eid in product_ids if eid in g._entities and g._entities[eid].properties.get("product_type") == "重疾险"]

    for pid in medical[:8]:
        for cid in ("ENT-C001", "ENT-C002", "ENT-C003"):
            if pid in g._entities:
                g.add_relation(OntologyRelation(pid, cid, RelationType.CONTAINS))
        for did in ("ENT-D001", "ENT-D002", "ENT-D003"):
            g.add_relation(OntologyRelation(pid, did, RelationType.COVERS))
        if "ENT-REG001" in g._entities:
            g.add_relation(OntologyRelation(pid, "ENT-REG001", RelationType.REGULATED_BY))

    for pid in critical[:8]:
        for cid in ("ENT-C002", "ENT-C004", "ENT-C005"):
            g.add_relation(OntologyRelation(pid, cid, RelationType.CONTAINS))
        g.add_relation(OntologyRelation(pid, "ENT-D001", RelationType.COVERS))
        if "ENT-REG002" in g._entities:
            g.add_relation(OntologyRelation(pid, "ENT-REG002", RelationType.REGULATED_BY))

    if "ENT-REG001" in g._entities:
        g.add_relation(OntologyRelation("ENT-REG001", "ENT-RL001", RelationType.DEFINES))
        g.add_relation(OntologyRelation("ENT-REG001", "ENT-RL003", RelationType.DEFINES))
        g.add_relation(OntologyRelation("ENT-REG001", "ENT-C006", RelationType.DEFINES))
    if "ENT-REG003" in g._entities:
        g.add_relation(OntologyRelation("ENT-REG003", "ENT-RL004", RelationType.DEFINES))
    if "ENT-REG002" in g._entities:
        g.add_relation(OntologyRelation("ENT-D001", "ENT-REG002", RelationType.DEFINES))

    for pid in medical:
        if "ENT-P002" in pid or (pid in g._entities and g._entities[pid].properties.get("guaranteed_renewal")):
            if "ENT-C006" in g._entities:
                g.add_relation(OntologyRelation(pid, "ENT-C006", RelationType.CONTAINS))
            break


def build_insurance_ontology() -> OntologyGraph:
    g = OntologyGraph()
    product_ids = _add_products_from_catalog(g)
    _add_static_entities(g)
    _add_relations(g, product_ids)
    return g

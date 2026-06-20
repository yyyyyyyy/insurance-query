"""Ontology registry data for Sprint 2 tools."""
from typing import Any, Dict, List, Optional

ONTOLOGY_ENTITIES: Dict[str, List[Dict[str, Any]]] = {
    "Product": [
        {"entity_id": "ENT-P001", "name": "e生保·百万医疗", "type": "Product", "aliases": ["e生保"]},
        {"entity_id": "ENT-P002", "name": "好医保·长期医疗", "type": "Product", "aliases": ["好医保"]},
        {"entity_id": "ENT-P003", "name": "平安福·重疾险", "type": "Product", "aliases": ["平安福"]},
    ],
    "Disease": [
        {"entity_id": "ENT-D001", "name": "恶性肿瘤", "type": "Disease", "category": "重大疾病", "aliases": ["癌症"]},
        {"entity_id": "ENT-D002", "name": "急性心肌梗塞", "type": "Disease", "category": "重大疾病", "aliases": ["心梗"]},
        {"entity_id": "ENT-D003", "name": "脑中风后遗症", "type": "Disease", "category": "重大疾病", "aliases": ["中风"]},
    ],
    "Regulation": [
        {"entity_id": "ENT-R001", "name": "健康保险管理办法", "type": "Regulation", "issuer": "银保监会", "year": 2019},
        {"entity_id": "ENT-R002", "name": "重疾定义使用规范", "type": "Regulation", "issuer": "保险行业协会", "year": 2020},
    ],
}

ONTOLOGY_RELATIONS: List[Dict[str, Any]] = [
    {"source": "ENT-P001", "target": "ENT-D001", "relation": "covers", "evidence": "DOC001-C003"},
    {"source": "ENT-P001", "target": "ENT-R001", "relation": "regulated_by"},
    {"source": "ENT-P003", "target": "ENT-R002", "relation": "regulated_by"},
]


def get_entity_by_name(entity_type: str, name: str) -> Optional[Dict[str, Any]]:
    entities = ONTOLOGY_ENTITIES.get(entity_type, [])
    name_lower = name.lower()
    for e in entities:
        if e["name"].lower() == name_lower:
            return e
        for alias in e.get("aliases", []):
            if alias.lower() == name_lower:
                return e
    return None

"""
Tool Executor for InsureQuery Runtime.

Sprint 1: Mock tool execution with deterministic, schema-compliant outputs.
Sprint 2: Replace with real tool implementations while keeping the same interface.

ARCHITECTURE RULE #4: Tools are deterministic execution units.
No LLM reasoning inside tools.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

MOCK_PRODUCT_DB = [
    {
        "id": "P001",
        "name": "e生保·百万医疗",
        "type": "医疗险",
        "provider": "平安健康",
        "coverage": {
            "general_hospitalization": "300万",
            "critical_illness": "600万",
            "outpatient": "5万",
        },
        "price": {"annual_premium": 356, "age_group": "30-35岁"},
        "exclusions": ["既往症", "美容整形", "牙科"],
        "eligibility": {"min_age": 0, "max_age": 65, "health_required": True},
    },
    {
        "id": "P002",
        "name": "好医保·长期医疗",
        "type": "医疗险",
        "provider": "人保健康",
        "coverage": {
            "general_hospitalization": "400万",
            "critical_illness": "400万",
            "outpatient": "0",
        },
        "price": {"annual_premium": 289, "age_group": "30-35岁"},
        "exclusions": ["既往症", "生育相关"],
        "eligibility": {"min_age": 0, "max_age": 60, "health_required": True},
    },
    {
        "id": "P003",
        "name": "平安福·重疾险",
        "type": "重疾险",
        "provider": "平安人寿",
        "coverage": {
            "critical_illness": "50万",
            "mild_illness": "10万",
            "death_benefit": "50万",
        },
        "price": {"annual_premium": 8500, "age_group": "30-35岁"},
        "exclusions": ["故意伤害", "战争", "核辐射"],
        "eligibility": {"min_age": 18, "max_age": 55, "health_required": True},
    },
]

MOCK_DOCUMENTS = [
    {
        "id": "DOC001",
        "title": "e生保保险条款",
        "type": "coverage_clause",
        "chunks": [
            {"id": "C001", "text": "一般医疗保险金：年度限额300万元，免赔额1万元。涵盖住院医疗费用、特殊门诊医疗费用、门诊手术医疗费用、住院前后门急诊费用。", "page": 3},
            {"id": "C002", "text": "重大疾病医疗保险金：年度限额600万元，0免赔。涵盖恶性肿瘤、急性心肌梗塞、脑中风后遗症等100种重大疾病。", "page": 5},
        ],
    },
    {
        "id": "DOC002",
        "title": "健康保险管理办法",
        "type": "regulation",
        "chunks": [
            {"id": "C003", "text": "第二十一条：保险公司应当根据健康保险产品的精算原理、赔付经验和经营成本等因素，科学合理确定保险费。", "page": 8},
            {"id": "C004", "text": "第十五条：长期健康保险产品应当设置犹豫期，犹豫期不得少于15日。", "page": 6},
        ],
    },
    {
        "id": "DOC003",
        "title": "理赔流程指南",
        "type": "claim_procedure",
        "chunks": [
            {"id": "C005", "text": "理赔流程：1) 出险后48小时内报案；2) 准备理赔材料（身份证、诊断证明、费用清单）；3) 提交理赔申请；4) 保险公司审核（一般3-15个工作日）；5) 理赔款到账。", "page": 1},
        ],
    },
]

MOCK_REGULATIONS = [
    {
        "id": "REG001",
        "title": "健康保险管理办法（2019修订版）",
        "issuer": "银保监会",
        "effective_date": "2019-12-01",
        "key_provisions": [
            "保险公司不得强制捆绑销售健康保险产品",
            "保证续保条款须明确写入合同",
            "保险公司应当建立健康保险理赔服务标准",
        ],
    },
    {
        "id": "REG002",
        "title": "重大疾病保险的疾病定义使用规范（2020修订版）",
        "issuer": "中国保险行业协会",
        "effective_date": "2021-02-01",
        "key_provisions": [
            "规范了28种重大疾病和3种轻度疾病的定义",
            "甲状腺癌TNM分期为I期或更轻分期的归入轻度疾病",
        ],
    },
]


def execute_product_search(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search for insurance products (mock implementation)."""
    query = params.get("query", "")
    top_k = params.get("top_k", 5)

    results = []
    for product in MOCK_PRODUCT_DB:
        if query and query not in product["name"] and query not in product["type"]:
            continue
        results.append({"id": product["id"], "name": product["name"],
                        "type": product["type"], "provider": product["provider"]})
        if len(results) >= top_k:
            break

    evidence = [
        {"product_id": r["id"], "source": "product_catalog", "citation": f"产品编号: {r['id']}"}
        for r in results
    ]

    return {"results": results, "evidence": evidence, "total_found": len(MOCK_PRODUCT_DB)}


def execute_document_search(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search documents (mock implementation)."""
    doc_type = params.get("doc_type", "")
    top_k = params.get("top_k", 3)

    results = []
    for doc in MOCK_DOCUMENTS:
        if doc_type and doc["type"] != doc_type:
            continue
        results.append({"id": doc["id"], "title": doc["title"],
                        "type": doc["type"], "chunks": doc["chunks"]})
        if len(results) >= top_k:
            break

    evidence = [
        {"document_id": r["id"], "title": r["title"],
         "source": "document_store", "chunk_count": len(r["chunks"])}
        for r in results
    ]

    return {"results": results, "evidence": evidence, "total_found": len(results)}


def execute_regulation_search(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search regulations (mock implementation)."""
    top_k = params.get("top_k", 5)

    results = MOCK_REGULATIONS[:top_k]

    evidence = [
        {"regulation_id": r["id"], "title": r["title"],
         "issuer": r["issuer"], "source": "regulation_db"}
        for r in results
    ]

    return {"results": results, "evidence": evidence, "total_found": len(results)}


def execute_compare(params: Dict[str, Any]) -> Dict[str, Any]:
    """Compare insurance products (mock implementation)."""
    comparison_mode = params.get("comparison_mode", "structured")

    products = params.get("products", [
        {"id": "P001", "name": "e生保"},
        {"id": "P002", "name": "好医保"},
    ])

    comparison = {
        "mode": comparison_mode,
        "products_compared": len(products),
        "dimensions": {
            "coverage": "e生保涵盖门诊保障(5万)，好医保无门诊保障",
            "price": "e生保年保费356元 vs 好医保289元",
            "hospitalization_limit": "e生保300万(一般)+600万(重疾) vs 好医保400万(一般+重疾合并)",
            "eligibility": "e生保最高投保年龄65岁 vs 好医保60岁",
        },
    }

    evidence = [
        {"product_ids": [p["id"] for p in products],
         "comparison_dimensions": list(comparison["dimensions"].keys()),
         "source": "product_comparison_engine"},
    ]

    return {"comparison": comparison, "evidence": evidence}


def execute_attribute_extraction(params: Dict[str, Any]) -> Dict[str, Any]:
    """Extract attributes from products (mock implementation)."""
    raw_attrs = params.get("attributes", [])
    attributes: List[str] = (
        [str(a) for a in raw_attrs] if isinstance(raw_attrs, list) else []
    )
    product_refs = params.get("product_ids", ["P001"])

    results = {}
    for pid in product_refs:
        product = next((p for p in MOCK_PRODUCT_DB if p["id"] == pid), None)
        if product:
            extracted = {}
            for attr in attributes:
                if attr in product:
                    extracted[attr] = product[attr]
                else:
                    coverage = product.get("coverage", {})
                    if isinstance(coverage, dict) and attr in coverage:
                        extracted[attr] = coverage[attr]
                    else:
                        eligibility = product.get("eligibility", {})
                        if isinstance(eligibility, dict) and attr in eligibility:
                            extracted[attr] = eligibility[attr]
            results[pid] = extracted

    evidence = [
        {"product_id": pid, "extracted_attributes": list(attrs.keys()),
         "source": "product_catalog"}
        for pid, attrs in results.items()
    ]

    return {"results": results, "evidence": evidence}


def execute_entity_lookup(params: Dict[str, Any]) -> Dict[str, Any]:
    """Look up entities (mock implementation)."""
    entity_type = params.get("entity_type", "")
    max_results = params.get("max_results", 5)

    if entity_type == "product":
        results = [{"id": p["id"], "name": p["name"], "type": p["type"]}
                   for p in MOCK_PRODUCT_DB[:max_results]]
    elif entity_type == "claim_rule":
        results = [{"id": "CR001", "rule": "48小时内报案", "source": "理赔流程指南"}]
    else:
        results = []

    evidence = [
        {"entity_type": entity_type, "entity_id": r.get("id", "N/A"),
         "source": "entity_registry"}
        for r in results
    ]

    return {"results": results, "evidence": evidence}


def execute_relation_traversal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Traverse ontology relations (mock implementation)."""
    relation_type = params.get("relation_type", "")

    if relation_type == "regulated_by":
        relations = [
            {"source": "百万医疗险", "relation": "regulated_by",
             "target": "健康保险管理办法", "evidence": "REG001"},
            {"source": "重疾险", "relation": "regulated_by",
             "target": "重疾定义使用规范", "evidence": "REG002"},
        ]
    else:
        relations = []

    evidence = [{"relation": r, "source": "ontology_graph"} for r in relations]

    return {"relations": relations, "evidence": evidence}


# --- Tool Registry ---

TOOL_EXECUTORS = {
    "product_search": execute_product_search,
    "document_search": execute_document_search,
    "regulation_search": execute_regulation_search,
    "compare": execute_compare,
    "attribute_extraction": execute_attribute_extraction,
    "entity_lookup": execute_entity_lookup,
    "relation_traversal": execute_relation_traversal,
}


def execute_tool(tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a tool by name with given parameters.

    Returns a dict with:
    - success: bool
    - output: tool-specific output
    - evidence: list of evidence objects (ARCHITECTURE RULE #2)
    - duration_ms: execution time

    ARCHITECTURE RULE #4: Tools are deterministic. Same input always produces same output.
    """
    executor = TOOL_EXECUTORS.get(tool_name)
    if not executor:
        return {
            "success": False,
            "output": {},
            "evidence": [],
            "error": f"Unknown tool: {tool_name}",
            "duration_ms": 0.0,
        }

    start = time.perf_counter()
    try:
        result = executor(params)
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "success": True,
            "output": result,
            "evidence": result.get("evidence", []),
            "duration_ms": round(duration_ms, 2),
        }
    except Exception as exc:
        duration_ms = (time.perf_counter() - start) * 1000
        return {
            "success": False,
            "output": {},
            "evidence": [],
            "error": str(exc),
            "duration_ms": round(duration_ms, 2),
        }

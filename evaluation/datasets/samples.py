"""Evaluation Dataset System — Ground truth for quality measurement."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

@dataclass
class EvalSample:
    sample_id: str
    question: str
    expected_intent: str
    expected_evidence: List[str] = field(default_factory=list)
    expected_ontology_path: List[str] = field(default_factory=list)
    category: str = "general"
    min_evidence_count: int = 1
    min_tools_used: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {"sample_id":self.sample_id,"question":self.question,
                "expected_intent":self.expected_intent,"category":self.category}

# ============================================================
# SPRINT 4 EVALUATION DATASET
# ============================================================

EVAL_DATASET: List[EvalSample] = [
    # --- Product Comparison ---
    EvalSample("E001","比较e生保和好医保的保障范围",
        expected_intent="product_comparison",
        expected_evidence=["DOC001","DOC002"],
        expected_ontology_path=["ENT-P001","ENT-P002"], category="product_comparison",
        min_evidence_count=2, min_tools_used=2),
    EvalSample("E002","e生保和好医保哪个免赔额更低",
        expected_intent="product_comparison", category="product_comparison",
        min_evidence_count=2, min_tools_used=3),
    EvalSample("E003","平安福和国寿福重疾保障对比",
        expected_intent="product_comparison", category="product_comparison",
        min_evidence_count=1, min_tools_used=2),

    # --- Coverage Questions ---
    EvalSample("E004","重疾险保障哪些疾病",
        expected_intent="coverage_question",
        expected_evidence=["DOC003"],
        expected_ontology_path=["ENT-P003","ENT-D001"], category="coverage",
        min_evidence_count=1, min_tools_used=2),
    EvalSample("E005","e生保的门诊手术费用怎么报销",
        expected_intent="coverage_question",
        expected_evidence=["DOC001"], category="coverage",
        min_evidence_count=1, min_tools_used=2),
    EvalSample("E006","百万医疗险的住院保障额度是多少",
        expected_intent="coverage_question", category="coverage",
        min_evidence_count=1, min_tools_used=1),

    # --- Regulation Questions ---
    EvalSample("E007","健康保险管理办法对等待期的规定是什么",
        expected_intent="regulation_lookup",
        expected_evidence=["DOC004"],
        expected_ontology_path=["ENT-R001","ENT-RL001"], category="regulation",
        min_evidence_count=1, min_tools_used=2),
    EvalSample("E008","保险法对如实告知义务的规定",
        expected_intent="regulation_lookup",
        expected_evidence=["DOC006"], category="regulation",
        min_evidence_count=1, min_tools_used=2),
    EvalSample("E009","保证续保条款的监管要求是什么",
        expected_intent="regulation_lookup",
        expected_evidence=["DOC004","DOC002"], category="regulation",
        min_evidence_count=2, min_tools_used=2),

    # --- Multi-hop Reasoning ---
    EvalSample("E010","保证续保是什么意思？e生保和好医保哪个有保证续保",
        expected_intent="product_comparison",
        expected_evidence=["DOC004","DOC001","DOC002"],
        expected_ontology_path=["ENT-R001","ENT-P001","ENT-P002","ENT-C006"], category="multi_hop",
        min_evidence_count=3, min_tools_used=3),
    EvalSample("E011","如果得了癌症，e生保和好医保分别能赔多少",
        expected_intent="product_comparison",
        expected_evidence=["DOC001","DOC002"],
        expected_ontology_path=["ENT-D001","ENT-P001","ENT-P002"], category="multi_hop",
        min_evidence_count=2, min_tools_used=3),
    EvalSample("E012","重疾险的等待期是多少天？监管有什么限制？",
        expected_intent="regulation_lookup",
        expected_evidence=["DOC003","DOC004"], category="multi_hop",
        min_evidence_count=2, min_tools_used=3),

    # --- Hallucination Tests ---
    EvalSample("E013","e生保是否覆盖太空旅行意外",
        expected_intent="coverage_question", category="hallucination",
        min_evidence_count=0, min_tools_used=1),
    EvalSample("E014","某产品4999年版本条款",
        expected_intent="general_inquiry", category="hallucination",
        min_evidence_count=0, min_tools_used=1),
]

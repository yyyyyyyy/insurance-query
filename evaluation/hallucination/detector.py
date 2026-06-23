"""
Hallucination Detector — Self-diagnosis of unsupported claims.

MUST DETECT:
  CASE 1: Unsupported Claim — answer contains info not in evidence_graph
  CASE 2: Missing Evidence — claims exist without citation
  CASE 3: Ontology Mismatch — entity used but not in ontology expansion path
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set
from evaluation.trace.capture import QueryTrace

@dataclass
class Violation:
    violation_type: str  # unsupported_claim | missing_evidence | ontology_mismatch
    description: str
    severity: str  # LOW | MEDIUM | HIGH
    location: str = ""
    evidence: Dict[str, Any] = field(default_factory=dict)

@dataclass
class HallucinationReport:
    hallucination_score: float  # 0.0=no hallucination, 1.0=severe
    violations: List[Violation] = field(default_factory=list)
    severity: str = "NONE"  # NONE | LOW | MEDIUM | HIGH
    def to_dict(self) -> Dict[str, Any]:
        return {"hallucination_score":self.hallucination_score,
                "violations":[{"type":v.violation_type,"description":v.description,
                               "severity":v.severity} for v in self.violations],
                "severity":self.severity}

class HallucinationDetector:
    def detect(self, trace: QueryTrace) -> HallucinationReport:
        violations: List[Violation] = []
        violations.extend(self._check_unsupported_claims(trace))
        violations.extend(self._check_missing_evidence(trace))
        violations.extend(self._check_ontology_mismatch(trace))

        score = self._compute_score(violations)
        severity = self._compute_severity(violations)
        return HallucinationReport(
            hallucination_score=round(score, 2),
            violations=violations,
            severity=severity)

    def _check_unsupported_claims(self, trace: QueryTrace) -> List[Violation]:
        violations = []
        answer = trace.final_answer
        answer_text = answer.get("text", "") if answer else ""
        ev_items = trace.evidence_items

        if not answer_text:
            violations.append(Violation("unsupported_claim", "Empty answer", "HIGH"))
            return violations

        # Extract key entities from answer
        answer_entities = self._extract_entities(answer_text)
        evidence_entities = set()
        for ev in ev_items:
            content = ev.get("content", "")
            evidence_entities.update(self._extract_entities(content))

        # Check if answer entities appear in evidence
        unsupported = answer_entities - evidence_entities
        if unsupported and not evidence_entities:
            violations.append(Violation(
                "unsupported_claim",
                f"Answer entities not backed by evidence: {list(unsupported)[:5]}",
                "HIGH"))
        elif unsupported:
            violations.append(Violation(
                "unsupported_claim",
                f"Some entities not in evidence: {list(unsupported)[:3]}",
                "MEDIUM"))
        return violations

    def _check_missing_evidence(self, trace: QueryTrace) -> List[Violation]:
        violations = []
        answer = trace.final_answer
        citations = answer.get("citations", []) if answer else []
        ev_count = trace.evidence_count

        if ev_count == 0:
            violations.append(Violation("missing_evidence",
                           "Answer generated with zero evidence items", "HIGH"))
        if not citations:
            violations.append(Violation("missing_evidence",
                           "Answer lacks structured citations", "MEDIUM"))
        return violations

    def _check_ontology_mismatch(self, trace: QueryTrace) -> List[Violation]:
        violations = []
        onto_context = trace.ontology_expansion.get("context", [])
        ev_graph = trace.evidence_graph

        # Check if evidence graph nodes align with ontology context
        graph_nodes = set(ev_graph.get("nodes", []))
        onto_set = set(onto_context)
        if onto_set and graph_nodes and not (onto_set & graph_nodes):
            violations.append(Violation(
                "ontology_mismatch",
                "Evidence graph nodes do not overlap with ontology expansion",
                "LOW"))
        return violations

    @staticmethod
    def _extract_entities(text: str) -> Set[str]:
        # Extract Chinese noun phrases (2-4 chars, common insurance terms)
        patterns = [
            r'(?:保证续保|等待期|免赔额|犹豫期|恶性肿瘤|重疾|轻症|中症|住院医疗|门诊手术)',
            r'[\u4e00-\u9fff]{2,4}(?:险|金|期|额|症|病|保)',
        ]
        entities = set()
        for pat in patterns:
            for m in re.findall(pat, text):
                if len(m) >= 2:
                    entities.add(m)
        return entities

    def _compute_score(self, violations: List[Violation]) -> float:
        if not violations:
            return 0.0
        weights = {"HIGH": 0.5, "MEDIUM": 0.25, "LOW": 0.1}
        score = sum(weights.get(v.severity, 0.1) for v in violations)
        return min(score, 1.0)

    def _compute_severity(self, violations: List[Violation]) -> str:
        if not violations:
            return "NONE"
        sev_order = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        max_sev = max(sev_order.get(v.severity, 0) for v in violations)
        return {3: "HIGH", 2: "MEDIUM", 1: "LOW"}.get(max_sev, "LOW")

"""
System Feedback Loop — Convert evaluation into improvement signals.

Generates actionable system improvement signals from evaluation results.
Each signal targets a specific module with a concrete fix suggestion.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from evaluation.engine.scorer import EvaluationResult
from evaluation.hallucination.detector import HallucinationReport

@dataclass
class FeedbackSignal:
    issue_type: str  # retrieval_quality | tool_routing | ontology_coverage | planner_quality | evidence_quality
    root_cause: str
    fix_suggestion: str
    affected_module: str
    severity: str = "MEDIUM"
    metadata: Dict[str, Any] = field(default_factory=dict)
    def to_dict(self) -> Dict[str, Any]:
        return {"issue_type":self.issue_type,"root_cause":self.root_cause,
                "fix_suggestion":self.fix_suggestion,"affected_module":self.affected_module,
                "severity":self.severity}

class FeedbackLoop:
    def generate(self, eval_result: EvaluationResult,
                 hallucination: HallucinationReport) -> List[FeedbackSignal]:
        signals = []
        signals.extend(self._retrieval_feedback(eval_result))
        signals.extend(self._tool_routing_feedback(eval_result))
        signals.extend(self._answer_quality_feedback(eval_result, hallucination))
        signals.extend(self._ontology_feedback(eval_result, hallucination))
        signals.extend(self._efficiency_feedback(eval_result))
        return signals

    def _retrieval_feedback(self, er: EvaluationResult) -> List[FeedbackSignal]:
        signals = []
        rdim = er.dimensions.get("retrieval")
        if not rdim: return signals
        n = rdim.normalized()
        if n < 0.5:
            signals.append(FeedbackSignal(
                "retrieval_quality","Low retrieval performance",
                "Increase hybrid retrieval weight toward BM25; expand top_k to 20",
                "knowledge.retrieval.engine", "HIGH"))
        onto_rate = rdim.details.get("ontology_hit_rate", 0)
        if onto_rate < 0.3:
            signals.append(FeedbackSignal(
                "retrieval_quality","Ontology not influencing retrieval enough",
                "Boost ontology_boost weight in HybridRetriever from 0.2 to 0.4",
                "knowledge.retrieval.engine", "MEDIUM"))
        return signals

    def _tool_routing_feedback(self, er: EvaluationResult) -> List[FeedbackSignal]:
        signals = []
        tdim = er.dimensions.get("tool")
        if not tdim: return signals
        tools = tdim.details.get("tools_used", [])
        if len(tools) < 2:
            signals.append(FeedbackSignal(
                "tool_routing","Insufficient tool diversity",
                "Planner should include at least 3 tools per query",
                "runtime.engine.planner", "MEDIUM"))
        return signals

    def _answer_quality_feedback(self, er: EvaluationResult,
                                  hal: HallucinationReport) -> List[FeedbackSignal]:
        signals = []
        if hal.severity in ("HIGH", "MEDIUM"):
            signals.append(FeedbackSignal(
                "evidence_quality",f"Hallucination detected: {hal.severity}",
                "Force evidence_before_answer gate; reject answers with <3 evidence items",
                "knowledge.engine", "HIGH"))
        adim = er.dimensions.get("answer")
        if adim:
            citations = adim.details.get("citation_count", 0)
            if citations == 0:
                signals.append(FeedbackSignal(
                    "evidence_quality","Answer lacks citations",
                    "Answer generator must emit structured citations for every claim",
                    "runtime.engine.engine", "HIGH"))
        return signals

    def _ontology_feedback(self, er: EvaluationResult,
                           hal: HallucinationReport) -> List[FeedbackSignal]:
        signals = []
        onto_violations = [v for v in hal.violations if v.violation_type == "ontology_mismatch"]
        if onto_violations:
            signals.append(FeedbackSignal(
                "ontology_coverage","Ontology expansion does not cover query entities",
                "Add missing entity relations in ontology builder; run ontology expansion validation",
                "knowledge.ontology.builder", "MEDIUM"))
        return signals

    def _efficiency_feedback(self, er: EvaluationResult) -> List[FeedbackSignal]:
        signals = []
        edim = er.dimensions.get("efficiency")
        if not edim: return signals
        latency = edim.details.get("latency_ms", 0)
        if latency > 3000:
            signals.append(FeedbackSignal(
                "planner_quality",f"High latency ({latency:.0f}ms)",
                "Reduce tool calls; cache frequent retrieval results",
                "runtime.engine.engine", "LOW"))
        return signals

"""
Evaluation Engine — 5-dimension quality scoring.

Dimensions:
  1. Retrieval Quality (recall, precision, ontology hit rate)
  2. Tool Quality (correctness, efficiency, determinism)
  3. Reasoning Quality (plan correctness, tool chain optimality)
  4. Answer Quality (groundedness, hallucination, completeness)
  5. System Efficiency (latency, cost, tool count)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from evaluation.trace.capture import QueryTrace
from evaluation.datasets.samples import EvalSample

@dataclass
class DimensionScore:
    name: str
    score: float
    max_score: float
    details: Dict[str, Any] = field(default_factory=dict)
    failure_points: List[str] = field(default_factory=list)
    def normalized(self) -> float:
        return self.score / max(self.max_score, 0.001)

@dataclass
class EvaluationResult:
    trace_id: str
    session_id: str
    total_score: float
    dimensions: Dict[str, DimensionScore] = field(default_factory=dict)
    breakdown: Dict[str, float] = field(default_factory=dict)
    failure_points: List[str] = field(default_factory=list)
    diagnosis: str = ""
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id":self.trace_id,"session_id":self.session_id,
            "total_score":self.total_score,
            "dimensions":{k:v.score for k,v in self.dimensions.items()},
            "breakdown":self.breakdown,
            "failure_points":self.failure_points,
            "diagnosis":self.diagnosis,
        }

class EvaluationEngine:
    """5-dimension quality evaluation engine."""
    def __init__(self):
        self.dimension_weights = {
            "retrieval":0.25,"tool":0.15,"reasoning":0.20,
            "answer":0.30,"efficiency":0.10}

    def evaluate(self, trace: QueryTrace,
                 expected: Optional[EvalSample] = None) -> EvaluationResult:
        dims = {}
        dims["retrieval"] = self._score_retrieval(trace, expected)
        dims["tool"] = self._score_tools(trace, expected)
        dims["reasoning"] = self._score_reasoning(trace, expected)
        dims["answer"] = self._score_answer(trace, expected)
        dims["efficiency"] = self._score_efficiency(trace)

        total = sum(dims[k].normalized() * self.dimension_weights[k] for k in dims) * 100
        eff_failures = dims["efficiency"].failure_points
        if eff_failures:
            total -= min(25.0, len(eff_failures) * 8.0)
        total = round(max(0.0, total), 1)

        failures = []
        for d in dims.values():
            failures.extend(d.failure_points)

        diagnosis = self._generate_diagnosis(dims, failures)

        return EvaluationResult(
            trace_id=trace.trace_id, session_id=trace.session_id,
            total_score=total, dimensions=dims,
            breakdown={k:v.normalized() for k,v in dims.items()},
            failure_points=failures, diagnosis=diagnosis)

    def _score_retrieval(self, trace: QueryTrace, expected: Optional[EvalSample] = None) -> DimensionScore:
        # Positive scoring: start at 0, earn points for each good property.
        score = 0.0
        failures = []
        details: Dict[str, Any] = {}
        ev_count = trace.evidence_count
        accepted = trace.accepted_evidence_count
        rr = trace.retrieval_results

        # Evidence must exist (prefer accepted count from EVIDENCE_SELECTED)
        effective_count = accepted if accepted > 0 else ev_count
        if effective_count == 0:
            failures.append("No evidence retrieved")
        else:
            # +2 for having any accepted evidence, +1 extra when rich set.
            score += 2.0
            if effective_count >= 3:
                score += 1.0
            elif effective_count < 3:
                failures.append("Low evidence count")

        # Ontology hit rate (+1 if >50% of retrievals used ontology)
        onto_hits = sum(1 for r in rr if r.get("ontology_used", False))
        onto_rate = onto_hits / max(len(rr), 1)
        details["ontology_hit_rate"] = round(onto_rate, 2)
        details["accepted_evidence_count"] = accepted
        if onto_rate >= 0.5:
            score += 1.0

        # Result count (+1 for non-zero retrieval results)
        total_retrieved = sum(r.get("result_count", 0) for r in rr)
        details["total_retrieved"] = total_retrieved
        if total_retrieved > 0 or rr:
            score += 1.0
        else:
            failures.append("Zero retrieval results")

        return DimensionScore("retrieval", min(score, 5.0), 5.0, details, failures)

    def _score_tools(self, trace: QueryTrace, expected: Optional[EvalSample] = None) -> DimensionScore:
        score = 0.0
        failures = []
        details: Dict[str, Any] = {}
        tc = trace.tool_call_count

        if tc == 0:
            failures.append("No tools called")
        else:
            # +2 for having tools, +1 extra when 2+ tools used (diversity).
            score += 2.0
            if tc >= 2:
                score += 1.0

        # Tool diversity
        tools_used = {c.get("tool_name","") for c in trace.tool_calls}
        details["tools_used"] = sorted(tools_used)
        details["tool_count"] = tc

        # +1 when compare tool is paired with attribute_extraction
        if "compare" in tools_used and "attribute_extraction" in tools_used:
            score += 1.0
        elif "compare" in tools_used and "attribute_extraction" not in tools_used:
            failures.append("Compare tool called without attribute extraction")

        # +1 when 3+ distinct tools were used (broad coverage)
        if len(tools_used) >= 3:
            score += 1.0

        return DimensionScore("tool", min(score, 5.0), 5.0, details, failures)

    def _score_reasoning(self, trace: QueryTrace, expected: Optional[EvalSample] = None) -> DimensionScore:
        score = 0.0
        failures = []
        details: Dict[str, Any] = {}
        plan = trace.plan_steps

        if not plan:
            failures.append("No execution plan")
        else:
            # +2 for any plan, +1 extra when plan has 2+ steps.
            score += 2.0
            if len(plan) >= 2:
                score += 1.0
            else:
                failures.append("Plan too short")

        details["plan_length"] = len(plan)

        # Ontology expansion quality (+1 when entities used, +1 for depth)
        onto_entities = trace.ontology_entities_used
        details["ontology_entities"] = onto_entities
        # ``ontology_entities_used`` is an int (count), not a list.
        if isinstance(onto_entities, int):
            if onto_entities > 0:
                score += 1.0
            if onto_entities >= 3:
                score += 1.0
        elif onto_entities:  # tolerate list/tuple form
            score += 1.0
            if len(onto_entities) >= 3:
                score += 1.0

        return DimensionScore("reasoning", min(score, 5.0), 5.0, details, failures)

    def _score_answer(self, trace: QueryTrace, expected: Optional[EvalSample] = None) -> DimensionScore:
        score = 0.0
        failures = []
        details: Dict[str, Any] = {}
        answer = trace.final_answer
        answer_text = answer.get("text", "") if answer else ""
        ev_count = trace.evidence_count

        # Groundedness: answer must have evidence (+2)
        if ev_count == 0:
            failures.append("HALLUCINATION: Answer has zero evidence")
        else:
            score += 2.0
            if ev_count >= 2:
                score += 0.5
            else:
                failures.append("Low evidence linkage")

        # Completeness (+1 for non-trivial answer length)
        if answer_text and len(answer_text) >= 20:
            score += 1.0
        else:
            failures.append("Answer too short or empty")

        # Citation check (+1)
        citations = answer.get("citations", []) if answer else []
        details["citation_count"] = len(citations)
        details["evidence_count"] = ev_count
        if citations:
            score += 1.0
        else:
            failures.append("No citations in answer")

        # +0.5 bonus for multiple citations (thorough sourcing)
        if len(citations) >= 2:
            score += 0.5

        # Compare with expected if available (+0.5)
        if expected and expected.expected_evidence:
            overlap = len(set(e[:20] for e in expected.expected_evidence) &
                          set(e.get("chunk_id","")[:20] for e in trace.evidence_items))
            details["expected_evidence_overlap"] = overlap
            if overlap > 0:
                score += 0.5
            else:
                failures.append("No overlap with expected evidence")

        return DimensionScore("answer", min(score, 5.0), 5.0, details, failures)

    def _score_efficiency(self, trace: QueryTrace) -> DimensionScore:
        score = 0.0
        failures = []
        details: Dict[str, Any] = {}
        latency = trace.total_latency_ms
        tc = trace.tool_call_count

        details["latency_ms"] = latency
        details["tool_calls"] = tc

        # Latency (+2 fast, +1 moderate, 0 slow)
        if 0 < latency <= 2000:
            score += 2.0
        elif latency <= 5000:
            score += 1.0
            failures.append("Moderate latency")
        elif latency > 5000:
            failures.append("High latency")

        # Tool call sanity (+2 reasonable, +1 borderline, 0 excessive)
        if 0 < tc <= 10:
            score += 2.0
        elif tc == 0:
            pass  # already penalized in _score_tools
        else:
            score += 1.0
            failures.append("Excessive tool calls")

        # +1 baseline credit for completing the turn at all
        score += 1.0

        return DimensionScore("efficiency", min(score, 5.0), 5.0, details, failures)

    def _generate_diagnosis(self, dims: Dict[str, DimensionScore], failures: List[str]) -> str:
        if not failures:
            return "All quality checks passed. System performing optimally."
        parts = [f"Issues detected ({len(failures)}):"]
        for f in failures:
            parts.append(f"  - {f}")
        lowest = min(dims, key=lambda k: dims[k].normalized())
        parts.append(f"Lowest dimension: {lowest} (score: {dims[lowest].normalized():.2f})")
        return "\n".join(parts)

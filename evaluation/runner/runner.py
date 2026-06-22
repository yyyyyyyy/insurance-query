"""Evaluation Runner — Batch evaluation + replay comparison."""

from __future__ import annotations
import time
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from evaluation.trace.capture import TraceCapture
from evaluation.engine.scorer import EvaluationEngine
from evaluation.hallucination.detector import HallucinationDetector
from evaluation.feedback.loop import FeedbackLoop
from evaluation.datasets.samples import EvalSample, EVAL_DATASET
from runtime.agents.orchestrator import MultiAgentEngine
from runtime.engine.reducer import replay_state

@dataclass
class BatchEvalResult:
    run_id: str
    total_samples: int
    passed: int
    failed: int
    avg_score: float
    avg_latency_ms: float
    per_sample: List[Dict[str, Any]] = field(default_factory=list)
    system_feedback: List[Dict[str, Any]] = field(default_factory=list)
    def to_dict(self) -> Dict[str, Any]:
        return {"run_id":self.run_id,"total":self.total_samples,"passed":self.passed,
                "failed":self.failed,"avg_score":self.avg_score,"avg_latency_ms":self.avg_latency_ms,
                "per_sample":self.per_sample,"system_feedback":self.system_feedback}

class EvalRunner:
    def __init__(self, engine: MultiAgentEngine):
        self.engine = engine
        self.trace_capture = TraceCapture()
        self.eval_engine = EvaluationEngine()
        self.hal_detector = HallucinationDetector()
        self.feedback_loop = FeedbackLoop()

    def run_batch(self, samples: Optional[List[EvalSample]] = None,
                  verbose: bool = False) -> BatchEvalResult:
        import uuid
        samples = samples or EVAL_DATASET
        run_id = f"RUN-{uuid.uuid4().hex[:8]}"
        per_sample = []
        scores = []
        latencies = []
        all_feedback = []
        passed = 0
        failed = 0

        for sample in samples:
            try:
                t0 = time.perf_counter()
                result = self.engine.query(sample.question)
                latency = (time.perf_counter() - t0) * 1000

                events = result.get("event_trace", [])
                state = replay_state(self.engine.event_store, result["session_id"]).to_dict()

                trace = self.trace_capture.capture(
                    result["session_id"], sample.question,
                    events, state, latency)

                eval_result = self.eval_engine.evaluate(trace, sample)
                hal_report = self.hal_detector.detect(trace)
                feedback = self.feedback_loop.generate(eval_result, hal_report)

                scores.append(eval_result.total_score)
                latencies.append(latency)

                ok = (eval_result.total_score >= 50 and
                      hal_report.severity in ("NONE","LOW"))
                if ok:
                    passed += 1
                else:
                    failed += 1

                all_feedback.extend(f.to_dict() for f in feedback)
                per_sample.append({
                    "sample_id":sample.sample_id,"question":sample.question[:50],
                    "score":eval_result.total_score,
                    "hallucination_score":hal_report.hallucination_score,
                    "hallucination_severity":hal_report.severity,
                    "latency_ms":round(latency,1),"passed":ok,
                    "evidence_count":result["answer"]["evidence_count"],
                    "diagnosis":eval_result.diagnosis[:100],
                })
                if verbose:
                    status = "PASS" if ok else "FAIL"
                    print(f"  [{status}] {sample.sample_id}: score={eval_result.total_score:.0f} hal={hal_report.severity}")

            except Exception as e:
                failed += 1
                per_sample.append({"sample_id":sample.sample_id,"error":str(e),"passed":False})

        return BatchEvalResult(
            run_id=run_id, total_samples=len(samples),
            passed=passed, failed=failed,
            avg_score=round(sum(scores)/max(len(scores),1),1),
            avg_latency_ms=round(sum(latencies)/max(len(latencies),1),1),
            per_sample=per_sample, system_feedback=all_feedback)

"""Observability System — Structured logging, metrics, system health dashboard."""

from __future__ import annotations
import time
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("insurequery")

@dataclass
class StageMetrics:
    name: str
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

class SystemMetrics:
    """Aggregated system performance metrics."""
    def __init__(self):
        self._latencies: Dict[str, List[float]] = defaultdict(list)
        self._tool_failures: Dict[str, int] = defaultdict(int)
        self._tool_successes: Dict[str, int] = defaultdict(int)
        self._hallucination_scores: List[float] = []
        self._retrieval_hits: int = 0
        self._retrieval_misses: int = 0
        self._query_count: int = 0
        self._total_latency: float = 0.0
        self._evaluation_scores: List[float] = []
        self._last_n_traces: List[Dict[str, Any]] = []

    def record_query(self, latency_ms: float, trace_id: str):
        self._query_count += 1
        self._total_latency += latency_ms
        self._last_n_traces.append({"trace_id":trace_id,"latency_ms":latency_ms,"ts":time.time()})
        if len(self._last_n_traces) > 50:
            self._last_n_traces.pop(0)

    def record_stage(self, stage: str, duration_ms: float):
        self._latencies[stage].append(duration_ms)

    def record_tool(self, tool_name: str, success: bool):
        if success:
            self._tool_successes[tool_name] += 1
        else:
            self._tool_failures[tool_name] += 1

    def record_hallucination(self, score: float):
        self._hallucination_scores.append(score)

    def record_evaluation(self, score: float):
        self._evaluation_scores.append(score)

    def record_retrieval(self, hit: bool):
        if hit:
            self._retrieval_hits += 1
        else:
            self._retrieval_misses += 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "queries": {"total":self._query_count,
                "avg_latency_ms":round(self._total_latency/max(self._query_count,1),1)},
            "retrieval": {"hits":self._retrieval_hits,"misses":self._retrieval_misses,
                "hit_rate":round(self._retrieval_hits/max(self._retrieval_hits+self._retrieval_misses,1),3)},
            "tools": [{"tool":t,"successes":self._tool_successes.get(t,0),
                "failures":self._tool_failures.get(t,0),
                "failure_rate":round(self._tool_failures.get(t,0)/max(self._tool_successes.get(t,0)+self._tool_failures.get(t,0),1),3)}
                for t in set(list(self._tool_successes)+list(self._tool_failures))],
            "hallucination": {"count":len(self._hallucination_scores),
                "avg":round(sum(self._hallucination_scores)/max(len(self._hallucination_scores),1),3) if self._hallucination_scores else 0},
            "evaluation": {"count":len(self._evaluation_scores),
                "avg_score":round(sum(self._evaluation_scores)/max(len(self._evaluation_scores),1),1) if self._evaluation_scores else 0},
            "stages": {s:{"count":len(v),"avg_ms":round(sum(v)/len(v),1)} for s,v in self._latencies.items()},
        }

class ObservabilityLayer:
    """Structured logging, metric collection, and trace visualization."""
    def __init__(self):
        self.metrics = SystemMetrics()
        self._event_log: List[Dict[str, Any]] = []

    def log_event(self, event_type: str, payload: Dict[str, Any], level: str = "info"):
        entry = {"ts":time.time(),"type":event_type,"payload":payload,"level":level}
        self._event_log.append(entry)
        if level == "error":
            logger.error(f"[{event_type}] {payload}")
        elif level == "warn":
            logger.warning(f"[{event_type}] {payload}")
        else:
            logger.info(f"[{event_type}] {json.dumps(payload,ensure_ascii=False)[:200]}")

    def trace_pipeline(self, trace_id: str, stages: List[StageMetrics]):
        for s in stages:
            self.metrics.record_stage(s.name, s.duration_ms)
        self.log_event("pipeline_trace", {"trace_id":trace_id,"stages":[{"name":s.name,"duration_ms":s.duration_ms,"success":s.success} for s in stages]})

    def health_check(self) -> Dict[str, Any]:
        return {"status":"healthy","metrics":self.metrics.snapshot(),
                "recent_traces":self.metrics._last_n_traces[-5:]}

    def dashboard(self) -> str:
        m = self.metrics.snapshot()
        lines = ["="*50,"INSUREQUERY SYSTEM DASHBOARD","="*50,
            f"Queries: {m['queries']['total']}, avg latency: {m['queries']['avg_latency_ms']}ms",
            f"Retrieval hit rate: {m['retrieval']['hit_rate']}",
            f"Avg evaluation score: {m['evaluation']['avg_score']}",
            f"Avg hallucination: {m['hallucination']['avg']}",
            "Stages:"]
        for s, d in m["stages"].items():
            lines.append(f"  {s}: count={d['count']}, avg={d['avg_ms']}ms")
        lines.append("Tools:")
        for t in m["tools"]:
            lines.append(f"  {t['tool']}: success={t['successes']}, failed={t['failures']}, rate={t['failure_rate']}")
        lines.append("="*50)
        return "\n".join(lines)

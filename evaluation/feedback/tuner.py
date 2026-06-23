"""
Self-Tuning Feedback Loop — Auto-applies evaluation feedback to improve pipeline.

Connects evaluation signals to retrieval parameter adjustments and plan
template modifications. Runs after each query evaluation.

Signal types and their actions:
  - retrieval_quality → adjust BM25/vector/ontology weights
  - tool_routing → suggest tool chain adjustments
  - evidence_quality → lower/higher retrieval thresholds
  - ontology_coverage → expand ontology expansion depth
  - planner_quality → adjust plan template selection
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {"bm25": 0.4, "vector": 0.4, "ontology": 0.2}
WEIGHT_ADJUST_STEP = 0.05
WEIGHT_MIN = 0.1
WEIGHT_MAX = 0.7
# EMA smoothing factor for score signals. Lower = smoother but slower to
# react. 0.3 means new observation contributes 30%, history contributes 70%.
SCORE_EMA_ALPHA = 0.3
# Minimum observations before the tuner starts adjusting weights — avoids
# overreacting to noisy single-sample scores on cold start.
MIN_SAMPLES_FOR_ADJUST = 3


@dataclass
class TuningConfig:
    """Auto-tuned retrieval and planning parameters."""
    bm25_weight: float = 0.4
    vector_weight: float = 0.4
    ontology_weight: float = 0.2
    ontology_depth: int = 2
    top_k: int = 10
    plan_templates_boost: Dict[str, float] = field(default_factory=dict)
    evidence_threshold: float = 0.1
    total_queries: int = 0
    last_adjustment: str = ""
    # EMA-smoothed quality signals — persisted across runs so the tuner
    # doesn't reset its memory on restart. ``-1.0`` flags "uninitialized".
    retrieval_score_ema: float = -1.0
    answer_score_ema: float = -1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bm25_weight": self.bm25_weight,
            "vector_weight": self.vector_weight,
            "ontology_weight": self.ontology_weight,
            "ontology_depth": self.ontology_depth,
            "top_k": self.top_k,
            "evidence_threshold": self.evidence_threshold,
            "total_queries": self.total_queries,
            "last_adjustment": self.last_adjustment,
            "retrieval_score_ema": round(self.retrieval_score_ema, 4),
            "answer_score_ema": round(self.answer_score_ema, 4),
        }


class SelfTuner:
    """Applies evaluation feedback to auto-tune retrieval and planning parameters.

    Maintains a persistent tuning config in data/tuning.json. Adjusts weights
    based on evaluation dimension scores after each query.
    """

    def __init__(self, config_path: str = "data/tuning.json"):
        self.config_path = config_path
        self._lock = threading.RLock()
        self.config = self._load_config()

    def _load_config(self) -> TuningConfig:
        with self._lock:
            try:
                path = Path(self.config_path)
                if path.exists():
                    data = json.loads(path.read_text())
                    return TuningConfig(**{k: v for k, v in data.items()
                                           if k in TuningConfig.__dataclass_fields__})
            except Exception:
                pass
            return TuningConfig()

    def _save_config(self):
        with self._lock:
            try:
                Path(self.config_path).parent.mkdir(parents=True, exist_ok=True)
                Path(self.config_path).write_text(
                    json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False)
                )
            except Exception as exc:
                logger.warning("Failed to save tuning config: %s", exc)

    def apply_evaluation(
        self,
        evaluation: Dict[str, Any],
        feedback_signals: Optional[List[Dict[str, Any]]] = None,
    ) -> TuningConfig:
        """Apply evaluation results to adjust tuning parameters.

        Uses EMA-smoothed retrieval/answer scores so a single noisy
        evaluation does not flip the weights back and forth. Adjustments
        are skipped until at least ``MIN_SAMPLES_FOR_ADJUST`` samples
        have been observed.
        """
        with self._lock:
            self.config.total_queries += 1

            dims = evaluation.get("dimensions", {})
            total_score = evaluation.get("total_score", 50)

            if feedback_signals:
                for signal in feedback_signals:
                    stype = signal.get("type", signal.get("signal_type", ""))
                    if stype == "retrieval_quality":
                        self.config.top_k = min(self.config.top_k + 1, 20)
                    elif stype == "evidence_quality":
                        self.config.evidence_threshold = min(
                            self.config.evidence_threshold + 0.02, 0.3,
                        )
                    elif stype == "ontology_coverage":
                        self.config.ontology_depth = min(self.config.ontology_depth + 1, 4)

            # Update EMA-smoothed scores. First observation seeds the EMA.
            retrieval_score_raw = dims.get("retrieval", 50) / 100.0
            answer_score_raw = dims.get("answer", 50) / 100.0
            if self.config.retrieval_score_ema < 0:
                self.config.retrieval_score_ema = retrieval_score_raw
            else:
                self.config.retrieval_score_ema = (
                    SCORE_EMA_ALPHA * retrieval_score_raw
                    + (1 - SCORE_EMA_ALPHA) * self.config.retrieval_score_ema
                )
            if self.config.answer_score_ema < 0:
                self.config.answer_score_ema = answer_score_raw
            else:
                self.config.answer_score_ema = (
                    SCORE_EMA_ALPHA * answer_score_raw
                    + (1 - SCORE_EMA_ALPHA) * self.config.answer_score_ema
                )

            reason = "weights stable (warmup)"

            if self.config.total_queries >= MIN_SAMPLES_FOR_ADJUST:
                retrieval_score = self.config.retrieval_score_ema
                answer_score = self.config.answer_score_ema

                if retrieval_score < 0.5:
                    self.config.bm25_weight = min(
                        self.config.bm25_weight + WEIGHT_ADJUST_STEP, WEIGHT_MAX
                    )
                    self.config.vector_weight = max(
                        self.config.vector_weight - WEIGHT_ADJUST_STEP * 0.5, WEIGHT_MIN
                    )
                    reason = f"boosted BM25 (retrieval_ema={retrieval_score:.2f})"
                elif answer_score < 0.5:
                    self.config.vector_weight = min(
                        self.config.vector_weight + WEIGHT_ADJUST_STEP, WEIGHT_MAX
                    )
                    self.config.bm25_weight = max(
                        self.config.bm25_weight - WEIGHT_ADJUST_STEP * 0.5, WEIGHT_MIN
                    )
                    reason = f"boosted vector (answer_ema={answer_score:.2f})"
                elif retrieval_score > 0.8 and answer_score > 0.8:
                    self.config.ontology_weight = min(
                        self.config.ontology_weight + WEIGHT_ADJUST_STEP * 0.3, 0.3
                    )
                    reason = "boosted ontology (scores high)"
                else:
                    reason = "weights stable"

                total_w = (
                    self.config.bm25_weight
                    + self.config.vector_weight
                    + self.config.ontology_weight
                )
                if total_w > 0:
                    self.config.bm25_weight /= total_w
                    self.config.vector_weight /= total_w
                    self.config.ontology_weight /= total_w

            if self.config.total_queries >= MIN_SAMPLES_FOR_ADJUST:
                onto_score = dims.get("reasoning", 50) / 100.0
                if onto_score < 0.4:
                    self.config.ontology_depth = min(self.config.ontology_depth + 1, 4)

            hallucination_score = evaluation.get("hallucination_score", 0)
            if hallucination_score > 0.3:
                self.config.evidence_threshold = min(
                    self.config.evidence_threshold + 0.05, 0.3
                )
                reason += " | raised evidence threshold"

            self.config.last_adjustment = reason
            self._save_config()

            if self.config.total_queries % 10 == 0:
                logger.info(
                    "SelfTuner adjusted (query #%d): %s | weights: bm25=%.2f vector=%.2f onto=%.2f",
                    self.config.total_queries,
                    reason,
                    self.config.bm25_weight,
                    self.config.vector_weight,
                    self.config.ontology_weight,
                )

            return self.config

    def get_retrieval_params(self) -> Dict[str, Any]:
        """Get current optimal retrieval parameters."""
        return {
            "bm25_weight": self.config.bm25_weight,
            "vector_weight": self.config.vector_weight,
            "ontology_boost": self.config.ontology_weight,
            "top_k": self.config.top_k,
            "ontology_depth": self.config.ontology_depth,
        }

    def get_evidence_threshold(self) -> float:
        return self.config.evidence_threshold

    def stats(self) -> Dict[str, Any]:
        return self.config.to_dict()

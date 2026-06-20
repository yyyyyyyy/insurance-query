"""
Knowledge-Aware Runtime Engine — Sprint 3 Orchestrator.

Integrates: Ingestion → Ontology → Hybrid Retrieval → Tool Execution → Answer

Pipeline:
  User Query → Intent → Ontology Expansion → Hybrid Retrieval
  → Tools (consume ontology + evidence) → Evidence Graph → Answer

DEPRECATED: This engine has been superseded by MultiAgentEngine
(runtime/agents/orchestrator.py), which now includes EventStore + full evaluation
event tracing. Use MultiAgentEngine for all new code.
KnowledgeEngine will be removed in a future version.
"""

from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from knowledge.ingestion.pipeline import ChunkStore, EmbeddingGenerator, ingest_text_document
from knowledge.ontology.builder import build_insurance_ontology
from knowledge.evidence.index import EvidenceIndex
from knowledge.retrieval.engine import HybridRetriever

from runtime.engine.event_store import (
    EventStore, answer_generated_event, evidence_found_event,
    intent_classified_event, plan_created_event, tool_called_event,
    user_query_event, ontology_expanded_event, retrieval_executed_event,
    # Sprint 4
    trace_captured_event, evaluation_completed_event,
    hallucination_detected_event, system_feedback_generated_event,
)
from runtime.llm.plugin import classify_intent_auto, compose_answer_auto, generate_plan_auto
from runtime.engine.reducer import replay_state
from runtime.engine.state import RuntimeState
from runtime.tools.base import ToolResult
from runtime.tools.registry import ToolDispatcher, create_default_registry


class KnowledgeEngine:
    """Knowledge-aware runtime engine — Sprint 3.

    Unlike Sprint 2's tool-driven engine, this engine:
    - Ingests documents into a chunk store
    - Builds an ontology graph
    - Uses hybrid retrieval (BM25 + vector + ontology)
    - Links evidence to ontology entities
    - Passes structured knowledge to tools
    """

    def __init__(self, event_store: Optional[EventStore] = None,
                 dispatcher: Optional[ToolDispatcher] = None):
        import warnings
        warnings.warn("KnowledgeEngine is deprecated, use MultiAgentEngine instead", DeprecationWarning, stacklevel=2)
        self.event_store = event_store or EventStore()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())

        # Knowledge layer
        self.chunk_store = ChunkStore()
        self.ontology = build_insurance_ontology()
        self.evidence_index = EvidenceIndex()
        self.embedding_gen = EmbeddingGenerator(vector_dim=256)
        self.retriever: Optional[HybridRetriever] = None
        self._knowledge_loaded = False

    def load_knowledge(self):
        """Ingest all embedded documents and build retrieval index."""
        if self._knowledge_loaded:
            return

        from runtime.tools.document_data import DOCUMENT_STORE
        for doc in DOCUMENT_STORE:
            raw_text = "\n\n".join(
                f"[{c.get('clause','')}] {c['content']}"
                for c in doc.get("chunks", [])
            )
            _, chunks = ingest_text_document(
                text=raw_text, document_id=doc["document_id"],
                title=doc["title"], document_type=doc.get("document_type", "policy_clause"),
                chunk_store=self.chunk_store, embedding_gen=self.embedding_gen,
                product_id=doc.get("product_id"),
            )
            # Index chunks in evidence index
            for chunk in chunks:
                rec = self.evidence_index.index_chunk(
                    chunk, doc.get("document_type", "policy_clause"), doc["title"]
                )

        # Build retriever
        self.retriever = HybridRetriever(
            self.chunk_store, self.embedding_gen, self.ontology
        )
        self.retriever.fit()
        self._knowledge_loaded = True

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self.load_knowledge()
        session_id = session_id or str(uuid.uuid4())
        seq = 0

        # Step 1: User query
        seq += 1
        self.event_store.append(user_query_event(session_id, seq, query_text))

        # Step 2: Intent classification
        intent_result = classify_intent_auto(query_text)
        seq += 1
        self.event_store.append(intent_classified_event(
            session_id, seq, intent=intent_result["intent"],
            confidence=intent_result["confidence"], entities=intent_result["entities"],
        ))

        # Step 3: Ontology expansion
        seed_entities = intent_result.get("entities", [])
        seed_names = [e.get("value", e.get("name", "")) for e in seed_entities if e.get("value") or e.get("name")]
        ontology_matches = []
        for name in seed_names:
            entities = self.ontology.lookup(name)
            ontology_matches.extend(e.entity_id for e in entities)

        if ontology_matches:
            expanded = self.ontology.expand_context(ontology_matches, max_depth=2, max_results=15)
            expanded_ids = [e.entity_id for e in expanded]
            seq += 1
            self.event_store.append(ontology_expanded_event(
                session_id, seq, seed_entities=ontology_matches,
                expanded_entities=expanded_ids,
            ))

        # Step 4: Plan generation (ontology-guided)
        plan = generate_plan_auto(query_text, intent_result)
        seq += 1
        self.event_store.append(plan_created_event(session_id, seq, plan=plan,
            reasoning=f"Ontology-guided plan for: {intent_result['intent']}"))

        # Step 5: Hybrid retrieval
        retrieval_results = self.retriever.retrieve(
            query_text, top_k=10,
            ontology_context=seed_names,
        ) if self.retriever else []

        seq += 1
        self.event_store.append(retrieval_executed_event(
            session_id, seq, query=query_text,
            result_count=len(retrieval_results),
            ontology_used=len(ontology_matches) > 0,
        ))

        # Link retrieval results to evidence
        retrieval_evidence = []
        for chunk, score in retrieval_results:
            ev_rec = self.evidence_index.index_chunk(
                chunk, "hybrid_retrieval",
                self.chunk_store.get_document_meta(chunk.document_id).title
                if self.chunk_store.get_document_meta(chunk.document_id) else ""
            )
            retrieval_evidence.append({
                "chunk_id": chunk.chunk_id, "document_id": chunk.document_id,
                "content": chunk.content[:150], "clause": chunk.clause,
                "score": round(score, 4), "evidence_id": ev_rec.evidence_id,
            })

        # Step 6: Execute tools with retrieval evidence
        all_evidence = list(retrieval_evidence)
        tool_outputs: Dict[str, Any] = {}

        for step in plan:
            tool_name = step["tool_name"]
            params = dict(step.get("input_params", {}))
            if "query" not in params:
                params["query"] = query_text
            # Inject retrieval context into tool params
            params["_retrieval_context"] = [
                {"chunk_id": r["chunk_id"], "clause": r["clause"], "content": r["content"]}
                for r in retrieval_evidence[:5]
            ]

            seq += 1
            self.event_store.append(tool_called_event(session_id, seq, tool_name=tool_name, input_params=params))

            result: ToolResult = self.dispatcher.dispatch(tool_name, params)
            if result.success:
                tool_outputs[tool_name] = result.data
                evidence_dicts = [e.to_dict() for e in result.evidence]
                all_evidence.extend(evidence_dicts)
                seq += 1
                self.event_store.append(evidence_found_event(
                    session_id, seq, tool_name=tool_name,
                    evidence=evidence_dicts, output=result.data,
                    duration_ms=result.duration_ms,
                ))

        # Step 7: Generate answer
        answer = self._generate_answer(query_text, intent_result, plan, tool_outputs, all_evidence)
        seq += 1
        self.event_store.append(answer_generated_event(
            session_id, seq, answer=answer["text"],
            citations=answer.get("citations", []), confidence=answer.get("confidence"),
        ))

        # Step 8: Evaluation (SPRINT 4)
        evaluation = self._run_evaluation(session_id, query_text, answer,
                                          all_evidence, ontology_matches)

        state = replay_state(self.event_store, session_id)
        return {
            "session_id": session_id, "answer": answer,
            "trace": [e.to_dict() for e in self.event_store.get_session_events(session_id)],
            "state": state.to_dict(),
            "evaluation": evaluation,
        }

    def _run_evaluation(self, session_id, query_text, answer, evidence, onto_matches):
        """Run full evaluation pipeline after answer generation (SPRINT 4)."""
        from evaluation.trace.capture import TraceCapture
        from evaluation.engine.scorer import EvaluationEngine
        from evaluation.hallucination.detector import HallucinationDetector
        from evaluation.feedback.loop import FeedbackLoop

        trace_capture = TraceCapture()
        eval_engine = EvaluationEngine()
        hal_detector = HallucinationDetector()
        feedback_loop = FeedbackLoop()

        events = [e.to_dict() for e in self.event_store.get_session_events(session_id)]
        state = replay_state(self.event_store, session_id)

        # Capture trace
        trace = trace_capture.capture(session_id, query_text, events, state.to_dict())
        seq = len(events) + 1
        self.event_store.append(trace_captured_event(session_id, seq, trace.trace_id))

        # Evaluate
        result = eval_engine.evaluate(trace)
        seq += 1
        self.event_store.append(evaluation_completed_event(
            session_id, seq, total_score=result.total_score,
            dimensions={k: v.score for k, v in result.dimensions.items()},
            diagnosis=result.diagnosis))

        # Detect hallucination
        hal = hal_detector.detect(trace)
        seq += 1
        self.event_store.append(hallucination_detected_event(
            session_id, seq, hallucination_score=hal.hallucination_score,
            severity=hal.severity,
            violations=[{"type": v.violation_type, "description": v.description, "severity": v.severity}
                        for v in hal.violations]))

        # Generate feedback
        feedback = feedback_loop.generate(result, hal)
        seq += 1
        self.event_store.append(system_feedback_generated_event(
            session_id, seq,
            signals=[f.to_dict() for f in feedback]))

        return {
            "trace_id": trace.trace_id,
            "total_score": result.total_score,
            "dimensions": {k: v.score for k, v in result.dimensions.items()},
            "hallucination_score": hal.hallucination_score,
            "hallucination_severity": hal.severity,
            "diagnosis": result.diagnosis,
            "feedback_count": len(feedback),
        }

    def _generate_answer(self, query_text, intent_result, plan, tool_outputs, evidence):
        from runtime.engine.engine import _format_citations, _compute_confidence
        intent_type = intent_result["intent"]
        citations = _format_citations(evidence)
        answer_text = compose_answer_auto(query_text, intent_type, tool_outputs, evidence)
        return {
            "text": answer_text, "citations": citations,
            "confidence": _compute_confidence(intent_result, evidence),
            "intent": intent_type,
            "tools_used": [s["tool_name"] for s in plan],
            "evidence_count": len(evidence),
        }

    def replay_session(self, session_id: str) -> RuntimeState:
        return replay_state(self.event_store, session_id)

    def stats(self) -> Dict[str, Any]:
        return {
            "ontology": self.ontology.statistics(),
            "chunks": self.chunk_store.chunk_count(),
            "documents": self.chunk_store.document_count(),
            "evidence_records": self.evidence_index.record_count(),
            "retriever_fitted": self.retriever is not None and self.retriever._fitted,
        }

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.event_store.get_session_events(session_id)]

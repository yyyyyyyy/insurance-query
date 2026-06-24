"""Insurance Runtime Kernel v3 — MultiAgentEngine (唯一运行时入口).

Pipeline:
  Memory resolve → Intent → Plan → Retrieval (tuner-weighted)
  → Tools (write facts) → Process → Rules → Answer
  → Evaluation → SelfTuner → Event Store
"""

from __future__ import annotations
import threading
import time
import uuid
from contextlib import nullcontext as _nullcontext
from typing import Any, Dict, List, Optional

from runtime.agents.bus import AgentBus, AgentMessage, AgentContext
from runtime.agents.agents import (
    PlannerAgent, RetrievalAgent, ToolAgent, EvaluationAgent, SupervisorAgent
)
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.execution.executor import create_default_executor
from runtime.engine.event_store import (
    EventStore, answer_generated_event,
    user_query_event,
    evidence_selected_event,
    cache_hit_event, cache_miss_event,
    memory_updated_event,
    evaluation_completed_event,
    hallucination_detected_event,
    trace_captured_event,
)
from runtime.agents.pipeline.memory import resolve_turn_memory
from runtime.agents.pipeline._helpers import EventSequencer, send_agent
from runtime.agents.pipeline.planning import run_planning_stage
from runtime.agents.pipeline.retrieval_stage import run_retrieval_stage
from runtime.agents.pipeline.tools_stage import run_tools_stage
from runtime.agents.pipeline.process_rules import run_process_rules_stage
from runtime.agents.pipeline.evidence import run_evidence_stage
from runtime.agents.pipeline.answer import build_answer_payload, run_answer_stage
from runtime.agents.pipeline.evaluation_stage import run_evaluation_stage
from runtime.process.runner import ProcessRunner
from infra.cache.store import TraceAwareCache
from infra.observability.monitor import ObservabilityLayer
from infra.observability.telemetry import get_tracer
from knowledge.ingestion.pipeline import ChunkStore
from knowledge.ontology.graph import OntologyGraph
from knowledge.retrieval.engine import HybridRetriever


class MultiAgentEngine:
    """Insurance Runtime Kernel v3 — unified decision runtime."""

    def __init__(
        self,
        dispatcher: Optional[ToolDispatcher] = None,
        cache: Optional[TraceAwareCache] = None,
        event_store: Optional[EventStore] = None,
        working_memory=None,
        tuner=None,
        process_runner: Optional[ProcessRunner] = None,
    ):
        self.bus = AgentBus()
        self.cache = cache or TraceAwareCache()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = create_default_executor()
        self.event_store = event_store or EventStore()
        self.working_memory = working_memory
        self.process_runner = process_runner or ProcessRunner()

        from evaluation.feedback.tuner import SelfTuner
        self.tuner = tuner if tuner is not None else SelfTuner()

        self._onto: Optional[OntologyGraph] = None
        self._retriever: Optional[HybridRetriever] = None
        self._chunk_store: Optional[ChunkStore] = None
        self._embedding_gen = None
        self._vector_store = None

        self.bus.register(PlannerAgent())
        self.bus.register(RetrievalAgent())
        self.bus.register(ToolAgent(self.dispatcher, self.async_exec))
        self.bus.register(EvaluationAgent())
        self.bus.register(SupervisorAgent())

        self._knowledge_loaded = False
        self._knowledge_lock = threading.Lock()
        self._rules: List[Dict[str, Any]] = []
        self.observability = ObservabilityLayer()

    def _acquire_session_lock(self, session_id: str):
        """Return the per-session lock if the store provides one, else None.

        Holding this lock across one full query() turn serializes concurrent
        turns on the same session, preventing duplicate sequence numbers and
        event-store races (S1).
        """
        getter = getattr(self.event_store, "_session_lock", None)
        if callable(getter):
            return getter(session_id)
        return None

    def _send_agent(self, *args, **kwargs):
        """Backward-compatible wrapper around pipeline send_agent."""
        return send_agent(self, *args, **kwargs)

    def _stage_span(self, name: str, **attrs):
        tracer = get_tracer()
        return tracer.start_as_current_span(name, attributes=attrs)

    def _materialize_cache_hit_response(
        self,
        *,
        session_id: str,
        query_text: str,
        trace_id: str,
        qkey: str,
        cached_val: Dict[str, Any],
        source_trace_id: str,
        memory_context: Dict[str, Any],
        memory_resolution: Dict[str, Any],
        resolved_query: str,
        retrieval_query: str,
        t0: float,
    ) -> Dict[str, Any]:
        """Append causal replay events for cache hit (I1) without re-running pipeline."""
        seq = EventSequencer(self.event_store, session_id)

        seq.append(user_query_event, query_text)
        seq.append(
            memory_updated_event,
            action="read",
            facts=memory_context.get("facts", {}),
            is_follow_up=memory_resolution.get("is_follow_up", False),
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 1)
        seq.append(
            cache_hit_event,
            store="query",
            key=qkey,
            source_trace_id=source_trace_id,
            source_session_id=cached_val.get("session_id", ""),
            replay_projection=True,
            latency_ms=latency_ms,
        )

        answer = dict(cached_val.get("answer") or {})
        canonical = answer.get("canonical_evidence") or {}
        accepted_ids = list(answer.get("accepted_evidence_ids") or canonical.get("accepted_ids") or [])

        if accepted_ids or canonical.get("items"):
            seq.append(
                evidence_selected_event,
                accepted_ids=accepted_ids,
                rejected_ids=list(canonical.get("rejected_ids") or []),
                threshold=self.tuner.get_evidence_threshold(),
                snapshot=list(canonical.get("items") or []),
                from_cache=True,
            )

        seq.append(
            answer_generated_event,
            answer=answer.get("text", ""),
            citations=answer.get("citations", []),
            confidence=answer.get("confidence"),
            from_cache=True,
        )

        evaluation = cached_val.get("evaluation") or {}
        if evaluation:
            seq.append(
                evaluation_completed_event,
                total_score=float(evaluation.get("total_score", 0)),
                dimensions=evaluation.get("dimensions", {}),
                diagnosis=evaluation.get("diagnosis", ""),
                from_cache=True,
            )
            seq.append(
                hallucination_detected_event,
                hallucination_score=float(evaluation.get("hallucination_score", 0)),
                severity=evaluation.get("severity", "NONE"),
                violations=evaluation.get("violations", []),
                from_cache=True,
            )

        seq.append(trace_captured_event, trace_id=trace_id, from_cache=True)

        result = {**cached_val}
        result.update({
            "session_id": session_id,
            "trace_id": trace_id,
            "query": query_text,
            "resolved_query": resolved_query,
            "retrieval_query": retrieval_query,
            "cached": True,
            "latency_ms": latency_ms,
            "cache_hit": {
                "source_trace_id": source_trace_id,
                "cache_key": qkey,
            },
            "event_trace": [
                e.to_dict() for e in self.event_store.get_session_events(session_id)
            ],
        })

        if self.working_memory and answer:
            self.working_memory.update_from_query(
                session_id=session_id,
                query_text=query_text,
                intent={"intent": answer.get("intent", "general_inquiry"), "entities": []},
                answer=answer,
            )
            result["working_memory"] = self.working_memory.get_context_for_query(session_id)

        return result

    def _ensure_knowledge(self):
        if self._knowledge_loaded:
            return
        with self._knowledge_lock:
            if self._knowledge_loaded:
                return
            self._load_knowledge()

    def _load_knowledge(self):
        from knowledge.ontology.builder import build_insurance_ontology
        from knowledge.retrieval.embeddings import EmbeddingFactory
        from knowledge.ingestion.pipeline import ingest_text_document, Chunk
        from knowledge.evidence.index import EvidenceIndex
        from runtime.tools.document_data import DOCUMENT_STORE
        from runtime.tools.data_loader import load_ingested_documents, load_rules
        from infra.vector.store import ChromaVectorStore
        import logging
        logger = logging.getLogger(__name__)

        self._onto = build_insurance_ontology()
        self.dispatcher.registry.wire_ontology(self._onto)
        self._chunk_store = ChunkStore()
        ei = EvidenceIndex()

        self._embedding_gen = EmbeddingFactory.create()
        logger.info(
            "Embedding provider: %s",
            "sentence-transformers"
            if self._embedding_gen.using_sentence_transformer
            else "TF-IDF fallback",
        )

        self._vector_store = ChromaVectorStore()

        ingested_docs = load_ingested_documents()
        if ingested_docs:
            DOCUMENT_STORE.clear()
            DOCUMENT_STORE.extend(ingested_docs)
            logger.info("Loaded %d documents into retrieval index", len(ingested_docs))
        else:
            logger.warning(
                "No ingested documents; using DOCUMENT_STORE fallback (%d docs)",
                len(DOCUMENT_STORE),
            )

        for doc in DOCUMENT_STORE:
            existing_chunks = doc.get("chunks", [])
            if existing_chunks:
                for c in existing_chunks:
                    chunk = Chunk(
                        chunk_id=c["chunk_id"],
                        document_id=doc["document_id"],
                        content=c["content"],
                        page=c.get("page"),
                        clause=c.get("clause", ""),
                        section_title=c.get("section_title", ""),
                        chunk_index=c.get("chunk_index", 0),
                    )
                    self._chunk_store.add_chunk(chunk)
                    ei.index_chunk(
                        chunk, doc.get("document_type", "policy_clause"), doc["title"],
                    )
                continue
            raw_text = (doc.get("content") or doc.get("text") or "").strip()
            if not raw_text:
                logger.warning(
                    "Skipping document %s: no chunks and no raw content",
                    doc.get("document_id", "?"),
                )
                continue
            _, chunks = ingest_text_document(
                raw_text, doc["document_id"], doc["title"],
                doc.get("document_type", "policy_clause"),
                self._chunk_store, self._embedding_gen,
            )
            for chunk in chunks:
                ei.index_chunk(chunk, doc.get("document_type", "policy_clause"), doc["title"])

        self._retriever = HybridRetriever(
            self._chunk_store, self._embedding_gen, self._onto,
            vector_store=self._vector_store,
        )
        self._retriever.fit()
        self.dispatcher.registry.wire_retriever(self._retriever)
        self._rules = load_rules()

        ra = self.bus.get_agent("retrieval")
        if ra:
            ra.retriever = self._retriever
        self._knowledge_loaded = True

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_knowledge()
        session_id = session_id or str(uuid.uuid4())
        trace_id = f"TRC-{uuid.uuid4().hex[:12]}"
        t0 = time.perf_counter()

        # Serialize concurrent turns on the same session (S1) and batch all
        # event-store writes into a single transaction (S2).
        session_lock = self._acquire_session_lock(session_id)
        batch_ctx = _nullcontext()
        if session_lock is not None:
            batch_ctx = session_lock

        with batch_ctx:
            with self.event_store.transaction():
                return self._run_query(
                    query_text, session_id, trace_id, t0,
                )

    def _run_query(
        self,
        query_text: str,
        session_id: str,
        trace_id: str,
        t0: float,
    ) -> Dict[str, Any]:
        # --- Memory resolve (before cache — session-aware key) ---
        memory_resolution = resolve_turn_memory(self.working_memory, session_id, query_text)
        resolved_query = memory_resolution["resolved_query"]
        retrieval_query = memory_resolution.get("retrieval_query", resolved_query)
        memory_context = memory_resolution["memory_context"]
        injected_entities = memory_resolution["injected_entities"]

        ctx = AgentContext(
            session_id=session_id,
            query=resolved_query,
            trace_id=trace_id,
            memory_context=memory_context,
        )

        qkey = self.cache.query_key(query_text, session_id, memory_context)
        cached_val, was_hit = self.cache.get("query", qkey)
        if was_hit and cached_val:
            entry_meta = self.cache.get_entry_meta("query", qkey)
            source_trace_id = entry_meta.get("trace_id") or cached_val.get("trace_id", "")
            return self._materialize_cache_hit_response(
                session_id=session_id,
                query_text=query_text,
                trace_id=trace_id,
                qkey=qkey,
                cached_val=cached_val,
                source_trace_id=source_trace_id,
                memory_context=memory_context,
                memory_resolution=memory_resolution,
                resolved_query=resolved_query,
                retrieval_query=retrieval_query,
                t0=t0,
            )

        seq = EventSequencer(self.event_store, session_id)
        seq.append(user_query_event, query_text)
        seq.append(
            memory_updated_event,
            action="read",
            facts=memory_context.get("facts", {}),
            is_follow_up=memory_resolution.get("is_follow_up", False),
        )
        seq.append(cache_miss_event, store="query", key=qkey)

        # Supervisor health check — write response into ctx.system_health
        health_resp = self.bus.send(AgentMessage(
            str(uuid.uuid4()), "orchestrator", "supervisor", "control",
            {"action": "health_check"}, trace_id=trace_id,
        ), ctx)
        ctx.system_health = health_resp.payload.get("health", {})

        t_plan = time.perf_counter()
        with self._stage_span("stage.planning", session_id=session_id):
            planning = run_planning_stage(
                self, ctx, seq,
                session_id=session_id,
                trace_id=trace_id,
                resolved_query=resolved_query,
                memory_context=memory_context,
                injected_entities=injected_entities,
            )
        self.observability.metrics.record_stage(
            "planning", (time.perf_counter() - t_plan) * 1000,
        )

        intent = planning.intent
        plan = planning.plan
        intent_type = planning.intent_type

        t_retr = time.perf_counter()
        with self._stage_span("stage.retrieval", session_id=session_id):
            retrieval = run_retrieval_stage(
                self, ctx, seq,
                trace_id=trace_id,
                resolved_query=resolved_query,
                retrieval_query=retrieval_query,
                intent=intent,
            )
        self.observability.metrics.record_stage(
            "retrieval", (time.perf_counter() - t_retr) * 1000,
        )
        retrieval_chunks = retrieval.retrieval_chunks
        retrieval_weights = retrieval.retrieval_weights

        t_tools = time.perf_counter()
        with self._stage_span("stage.tools", session_id=session_id):
            tools_out = run_tools_stage(
                self, ctx, seq,
                trace_id=trace_id,
                resolved_query=resolved_query,
                plan=plan,
                retrieval_chunks=retrieval_chunks,
            )
        self.observability.metrics.record_stage(
            "tools", (time.perf_counter() - t_tools) * 1000,
        )

        t_proc = time.perf_counter()
        with self._stage_span("stage.process_rules", session_id=session_id):
            proc_rules = run_process_rules_stage(
                self, ctx, seq,
                session_id=session_id,
                resolved_query=resolved_query,
                intent_type=intent_type,
                tool_data=tools_out.tool_data,
                all_evidence=tools_out.all_evidence,
            )
        self.observability.metrics.record_stage(
            "process_rules", (time.perf_counter() - t_proc) * 1000,
        )

        process_result = proc_rules.process_result
        rule_eval = proc_rules.rule_eval
        matched = proc_rules.matched

        evidence_threshold = self.tuner.get_evidence_threshold()
        t_ev = time.perf_counter()
        with self._stage_span("stage.evidence", session_id=session_id):
            evidence_out = run_evidence_stage(
                seq,
                agent_results=tools_out.agent_results,
                retrieval_chunks=retrieval_chunks,
                matched_rules=matched,
                process_result=process_result.to_dict() if process_result else None,
                memory_context=memory_context,
                evidence_threshold=evidence_threshold,
                intent_type=intent_type,
                force_accept_sources={"rule"} if matched else set(),
            )
        self.observability.metrics.record_stage(
            "evidence", (time.perf_counter() - t_ev) * 1000,
        )

        t_ans = time.perf_counter()
        with self._stage_span("stage.answer", session_id=session_id):
            answer = build_answer_payload(
                resolved_query, intent_type, intent, tools_out.tool_data,
                evidence_out.accepted_evidence,
                process_result=ctx.process_result or None,
                rule_evaluation=ctx.rule_evaluation or None,
                memory_context=memory_context,
                tools_attempted=tools_out.tools_attempted,
                matched_rules=matched,
                rule_eval_dict=rule_eval.to_dict(),
                accepted_ids=evidence_out.accepted_ids,
                canonical_payload=evidence_out.ces.to_event_payload(),
            )
            run_answer_stage(
                seq, answer,
                accepted_ids=evidence_out.accepted_ids,
                canonical_payload=evidence_out.ces.to_event_payload(),
            )
        ctx.answer = answer
        self.observability.metrics.record_stage(
            "answer", (time.perf_counter() - t_ans) * 1000,
        )

        t_eval = time.perf_counter()
        with self._stage_span("stage.evaluation", session_id=session_id):
            run_evaluation_stage(
                self, ctx, seq,
                session_id=session_id,
                trace_id=trace_id,
                resolved_query=resolved_query,
            )
        self.observability.metrics.record_stage(
            "evaluation", (time.perf_counter() - t_eval) * 1000,
        )
        self.bus.send(AgentMessage(
            str(uuid.uuid4()), "orchestrator", "supervisor", "control",
            {"action": "final_check", "health": ctx.system_health},
            trace_id=trace_id,
        ), ctx)

        latency = round((time.perf_counter() - t0) * 1000, 1)
        self.observability.metrics.record_query(latency, trace_id)
        result = {
            "session_id": session_id,
            "trace_id": trace_id,
            "query": query_text,
            "resolved_query": resolved_query,
            "retrieval_query": retrieval_query,
            "answer": answer,
            "evaluation": ctx.evaluation,
            "execution_graph": ctx.execution_graph,
            "agent_statuses": self.bus.agent_statuses_from_context(ctx),
            "message_log": self.bus.message_log(),
            "event_trace": [e.to_dict() for e in self.event_store.get_session_events(session_id)],
            "memory_context": memory_context,
            "memory_facts": ctx.memory_facts,
            "process_result": ctx.process_result,
            "retrieval": {
                "weights": retrieval_weights,
                "chunks": retrieval_chunks,
                "total": len(retrieval_chunks),
            },
            "tuning": self.tuner.stats(),
            "observability": self.observability.metrics.snapshot(),
            "latency_ms": latency,
            "cached": False,
        }

        self.cache.set("query", qkey, result, trace_id=trace_id)

        if self.working_memory:
            products = [
                e.get("value", "") for e in intent.get("entities", [])
                if e.get("type") == "product"
            ]
            if not products and ctx.memory_facts:
                for key, val in ctx.memory_facts.items():
                    if key.startswith("product:") and isinstance(val, dict):
                        name = val.get("value", "")
                        if name:
                            products.append(name)
            self.working_memory.update_from_query(
                session_id=session_id,
                query_text=query_text,
                intent=intent,
                answer=answer,
                products=products,
                entities=[e.get("value", "") for e in intent.get("entities", [])],
            )
            if ctx.memory_facts:
                self.working_memory.add_facts(session_id, ctx.memory_facts)
            result["working_memory"] = self.working_memory.get_context_for_query(session_id)

        return result

    def shutdown(self) -> None:
        """Release async executor resources."""
        if hasattr(self.async_exec, "shutdown"):
            self.async_exec.shutdown(wait=False)

    def _evaluate_rules(self, query_text, intent_type, tool_data, all_evidence):
        from knowledge.rules.engine import RuleEngine
        if not self._rules:
            return RuleEngine([]).evaluate(query_text, intent_type, tool_data, all_evidence)
        return RuleEngine(self._rules).evaluate(
            query_text=query_text,
            intent=intent_type,
            tool_results=tool_data,
            evidence=all_evidence,
        )

    def _ontology_expand(self, seed_names: List[str]) -> List[str]:
        if not self._onto or not seed_names:
            return []
        matches: List[str] = []
        for name in seed_names:
            entities = self._onto.lookup(name)
            matches.extend(e.entity_id for e in entities)
        return list(dict.fromkeys(matches))

    def stats(self) -> Dict[str, Any]:
        return {
            "agents": self.bus.agent_statuses(),
            "async_exec": self.async_exec.stats(),
            "cache": self.cache.stats(),
            "observability": self.observability.metrics.snapshot(),
            "event_store": {
                "total_events": self.event_store.count(),
                "sessions": self.event_store.session_count(),
            },
            "vector_store": self._vector_store.stats() if self._vector_store else {"enabled": False},
            "embedding": (
                "sentence-transformers"
                if (self._embedding_gen and self._embedding_gen.using_sentence_transformer)
                else "TF-IDF"
            ),
            "tuning": self.tuner.stats(),
        }

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.event_store.get_session_events(session_id)]

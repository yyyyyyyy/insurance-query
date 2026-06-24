"""Insurance Runtime Kernel v3 — MultiAgentEngine (唯一运行时入口).

Pipeline:
  Memory resolve → Intent → Plan → Retrieval (tuner-weighted)
  → Tools (write facts) → Process → Rules → Answer
  → Evaluation → SelfTuner → Event Store
"""

from __future__ import annotations
import os
import threading
import time
import uuid
from contextlib import nullcontext as _nullcontext
from typing import Any, Dict, List, Optional

from runtime.agents.bus import AgentBus, AgentMessage, AgentContext, AgentStatus
from runtime.agents.agents import (
    PlannerAgent, RetrievalAgent, ToolAgent, EvaluationAgent, SupervisorAgent
)
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.execution.executor import create_default_executor
from runtime.engine.event_store import (
    EventStore, answer_generated_event, evidence_found_event,
    intent_classified_event, ontology_expanded_event, plan_created_event,
    tool_called_event, user_query_event, retrieval_executed_event,
    trace_captured_event, evaluation_completed_event,
    hallucination_detected_event, system_feedback_generated_event,
    memory_updated_event, tool_executed_event, process_executed_event,
    rule_evaluated_event, tuning_applied_event, evidence_selected_event,
    cache_hit_event, cache_miss_event,
    agent_assigned_event, agent_completed_event, system_degraded_event,
)
from runtime.evidence.canonical import CanonicalEvidenceSet
from runtime.evidence.selector import select_evidence_for_answer
from runtime.evidence.adapters import (
    tool_evidence_to_candidates,
    hybrid_chunks_to_candidates,
    rules_to_candidates,
    process_to_candidates,
    memory_to_candidates,
)
from runtime.agents.pipeline.memory import resolve_turn_memory
from runtime.process.runner import ProcessRunner
from infra.cache.store import TraceAwareCache
from knowledge.ingestion.pipeline import ChunkStore
from knowledge.ontology.graph import OntologyGraph
from knowledge.retrieval.engine import HybridRetriever


class _EventSequencer:
    """Monotonic per-session event sequence allocator."""

    def __init__(self, event_store: EventStore, session_id: str):
        self._store = event_store
        self._session_id = session_id
        events = event_store.get_session_events(session_id)
        self._next = (max(e.sequence_number for e in events) + 1) if events else 1

    def append(self, factory, *args, **kwargs) -> None:
        seq = self._next
        self._next += 1
        self._store.append(factory(self._session_id, seq, *args, **kwargs))


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

    def _send_agent(
        self,
        ctx: AgentContext,
        session_id: str,
        seq: _EventSequencer,
        recipient: str,
        msg_type: str,
        payload: Dict[str, Any],
        trace_id: str,
        *,
        emit_events: bool = True,
    ) -> AgentMessage:
        """Dispatch to an agent, optionally recording agent lifecycle events."""
        if emit_events:
            seq.append(agent_assigned_event, recipient, {"msg_type": msg_type})

        resp = self.bus.send(AgentMessage(
            str(uuid.uuid4()), "orchestrator", recipient, msg_type,
            payload, trace_id=trace_id,
        ), ctx)

        agent = self.bus.get_agent(recipient)
        turn_status = ctx.agent_statuses.get(recipient) if ctx else None
        if turn_status is None and agent:
            turn_status = agent.status

        if emit_events and agent and turn_status is not None:
            status_val = turn_status.value if isinstance(turn_status, AgentStatus) else str(turn_status)
            seq.append(
                agent_completed_event,
                recipient,
                {"msg_type": resp.msg_type, "status": status_val},
            )
            if turn_status == AgentStatus.FAILED:
                ctx.degraded_mode = True
                seq.append(
                    system_degraded_event,
                    reason=f"agent:{recipient}:failed",
                )

        return resp

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
        seq = _EventSequencer(self.event_store, session_id)

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

        qkey = self.cache.query_key(query_text, session_id)
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

        seq = _EventSequencer(self.event_store, session_id)
        seq.append(user_query_event, query_text)

        seq.append(
            memory_updated_event,
            action="read",
            facts=memory_context.get("facts", {}),
            is_follow_up=memory_resolution.get("is_follow_up", False),
        )

        seq.append(cache_miss_event, store="query", key=qkey)

        self.bus.send(AgentMessage(
            str(uuid.uuid4()), "orchestrator", "supervisor", "control",
            {"action": "health_check"}, trace_id=trace_id,
        ), ctx)

        # --- Intent + Plan (with memory) ---
        resp = self._send_agent(
            ctx, session_id, seq, "planner", "task",
            {
                "query": resolved_query,
                "memory_context": memory_context,
                "injected_entities": injected_entities,
            },
            trace_id,
        )
        intent = resp.payload.get("intent", {})
        plan = resp.payload.get("plan", resp.payload.get("fallback_plan", []))
        ctx.intent = intent
        ctx.plan = plan
        ctx.execution_graph.append({
            "agent": "planner", "intent": intent.get("intent"), "plan_len": len(plan),
        })

        seq.append(
            intent_classified_event,
            intent=intent.get("intent", "general_inquiry"),
            confidence=intent.get("confidence", 0.5),
            entities=intent.get("entities", []),
        )
        seq.append(
            plan_created_event,
            plan=plan,
            reasoning=f"Plan for intent: {intent.get('intent', 'general_inquiry')}",
        )

        # --- Retrieval (tuner-weighted) ---
        retrieval_weights = self.tuner.get_retrieval_params()
        retrieval_weights["min_score"] = 0.0
        ctx.retrieval_weights = retrieval_weights

        seed_names = [e.get("value", "") for e in intent.get("entities", [])]
        onto_matches = self._ontology_expand(seed_names)
        ctx.ontology_context = onto_matches

        if onto_matches:
            seq.append(
                ontology_expanded_event,
                seed_entities=onto_matches, expanded_entities=onto_matches,
            )

        resp = self._send_agent(
            ctx, session_id, seq, "retrieval", "task",
            {
                "query": retrieval_query,
                "ontology_context": seed_names,
                "memory_context": memory_context,
                "retrieval_weights": retrieval_weights,
            },
            trace_id,
        )
        retrieval_chunks = resp.payload.get("chunks", [])
        decision_trace = resp.payload.get("decision_trace", [])
        ctx.retrieval_results = retrieval_chunks
        ctx.execution_graph.append({"agent": "retrieval", "chunks": len(retrieval_chunks)})

        seq.append(
            retrieval_executed_event,
            query=retrieval_query,
            result_count=len(retrieval_chunks),
            ontology_used=len(onto_matches) > 0,
            weights=retrieval_weights,
            base_query=resolved_query,
            decision_trace=decision_trace,
            chunks=retrieval_chunks[:10],
        )

        # --- Tool execution ---
        resp = self._send_agent(
            ctx, session_id, seq, "tool", "task",
            {
                "plan": plan, "query": resolved_query,
                "retrieval_context": retrieval_chunks[:5],
            },
            trace_id,
        )
        agent_results = resp.payload.get("results", {})
        tool_memory_facts = resp.payload.get("memory_facts", {})
        ctx.execution_graph.append({"agent": "tool", "tools": list(agent_results.keys())})

        tool_data: Dict[str, Any] = {}
        all_evidence: List[Dict[str, Any]] = []
        tools_attempted: List[str] = []
        for tname, ar_dict in agent_results.items():
            tools_attempted.append(tname)
            status = ar_dict.get("status", "")
            seq.append(
                tool_called_event,
                tool_name=tname,
                input_params=ar_dict.get("metadata", {}),
            )
            duration = 0.0
            fact_keys: List[str] = []
            if status == "success" and ar_dict.get("result"):
                r = ar_dict["result"]
                tool_data[tname] = r.get("data", {})
                evidence = r.get("evidence", [])
                all_evidence.extend(evidence)
                duration = r.get("duration_ms", 0)
                seq.append(
                    evidence_found_event,
                    tool_name=tname,
                    evidence=evidence, output=r.get("data", {}),
                    duration_ms=duration,
                )
            if tname in tool_memory_facts:
                fact_keys.append(tname)
            seq.append(
                tool_executed_event,
                tool_name=tname, status=status,
                duration_ms=duration, fact_keys=fact_keys,
            )

        ctx.tool_results = tool_data
        ctx.evidence = all_evidence

        # MEMORY_UPDATED (write facts from tools)
        if ctx.memory_facts:
            seq.append(memory_updated_event, action="write", facts=ctx.memory_facts)

        # --- Process execution ---
        intent_type = intent.get("intent", "general_inquiry")
        preliminary_rules = self._evaluate_rules(
            resolved_query, intent_type, tool_data, all_evidence,
        )
        rule_decisions_pre = [d.to_dict() for d in preliminary_rules.decisions]

        process_result = self.process_runner.run(
            intent=intent_type,
            tool_results=tool_data,
            rule_decisions=rule_decisions_pre,
            memory_facts=ctx.memory_facts,
            query_text=resolved_query,
        )
        if process_result:
            ctx.process_result = process_result.to_dict()
            seq.append(
                process_executed_event,
                process_name=process_result.process_name,
                path=process_result.path,
                terminal_state=process_result.terminal_state,
                outcome=process_result.outcome,
            )
            if self.working_memory:
                self.working_memory.set_active_process(session_id, process_result.process_name)

        # --- Rule evaluation (strict) ---
        rule_eval = preliminary_rules
        ctx.rule_evaluation = rule_eval.to_dict()
        matched = [d.to_dict() for d in rule_eval.decisions if d.matched][:5]
        seq.append(
            rule_evaluated_event,
            rules_evaluated=rule_eval.rules_evaluated,
            rules_matched=rule_eval.rules_matched,
            top_decisions=matched,
            summary=rule_eval.summary,
        )

        # --- Canonical evidence selection ---
        ces = CanonicalEvidenceSet()
        evidence_threshold = self.tuner.get_evidence_threshold()
        for tname, ar_dict in agent_results.items():
            if ar_dict.get("status") == "success" and ar_dict.get("result"):
                ev_list = ar_dict["result"].get("evidence", [])
                ces.add_candidates(tool_evidence_to_candidates(tname, ev_list))
        ces.add_candidates(hybrid_chunks_to_candidates(retrieval_chunks))
        ces.add_candidates(rules_to_candidates(matched))
        if process_result:
            ces.add_candidates(process_to_candidates(process_result.to_dict()))
        ces.add_candidates(memory_to_candidates(memory_context))

        accepted_ids, rejected_ids = select_evidence_for_answer(
            ces,
            evidence_threshold=evidence_threshold,
            intent=intent_type,
            force_accept_sources={"rule"} if matched else set(),
        )
        accepted_evidence = ces.to_evidence_dicts(accepted_only=True)
        ces.mark_used_in_answer(accepted_ids)

        seq.append(
            evidence_selected_event,
            accepted_ids=accepted_ids,
            rejected_ids=rejected_ids,
            threshold=evidence_threshold,
            snapshot=[i.to_dict() for i in ces.all_items()],
        )

        # --- Answer ---
        from runtime.llm.answer import _format_citations, _compute_confidence
        from runtime.llm.plugin import compose_answer_auto
        answer_text = compose_answer_auto(
            resolved_query, intent_type, tool_data, accepted_evidence,
            process_result=ctx.process_result or None,
            rule_evaluation=ctx.rule_evaluation or None,
            memory_context=memory_context,
        )
        citations = _format_citations(accepted_evidence)
        confidence = _compute_confidence(intent, accepted_evidence)
        answer = {
            "text": answer_text,
            "citations": citations,
            "confidence": confidence,
            "intent": intent_type,
            "evidence_count": len(accepted_evidence),
            "tools_used": tools_attempted,
            "rule_evaluation": rule_eval.to_dict(),
            "matched_rules": matched,
            "rule_count": rule_eval.rules_matched,
            "accepted_evidence_ids": accepted_ids,
            "canonical_evidence": ces.to_event_payload(),
        }
        if process_result:
            answer["process_result"] = process_result.to_dict()
        ctx.answer = answer

        seq.append(
            answer_generated_event,
            answer=answer["text"],
            citations=answer.get("citations", []),
            confidence=answer.get("confidence"),
            accepted_evidence_ids=accepted_ids,
            used_in_answer_ids=accepted_ids,
            canonical_evidence_snapshot=ces.to_event_payload(),
        )

        # --- Evaluation (event_store truth only) ---
        events_for_eval = [e.to_dict() for e in self.event_store.get_session_events(session_id)]
        resp = self._send_agent(
            ctx, session_id, seq, "evaluation", "task",
            {
                "session_id": session_id,
                "query": resolved_query,
                "events": events_for_eval,
            },
            trace_id,
        )
        ctx.evaluation = resp.payload
        eval_result = ctx.evaluation
        if ctx.agent_statuses.get("evaluation") == AgentStatus.DEGRADED:
            ctx.degraded_mode = True
            seq.append(system_degraded_event, reason="evaluation:degraded")

        seq.append(
            evaluation_completed_event,
            total_score=float(eval_result.get("total_score", 0)),
            dimensions=eval_result.get("dimensions", {}),
            diagnosis=eval_result.get("diagnosis", ""),
        )
        seq.append(
            hallucination_detected_event,
            hallucination_score=float(eval_result.get("hallucination_score", 0)),
            severity=eval_result.get("severity", "NONE"),
            violations=eval_result.get("violations", []),
        )
        feedback_signals = eval_result.get("feedback", [])
        if feedback_signals:
            seq.append(system_feedback_generated_event, signals=feedback_signals)

        # --- SelfTuner闭环 ---
        tuning_config = self.tuner.apply_evaluation(eval_result, feedback_signals)
        seq.append(
            tuning_applied_event,
            weights={
                "bm25_weight": tuning_config.bm25_weight,
                "vector_weight": tuning_config.vector_weight,
                "ontology_weight": tuning_config.ontology_weight,
            },
            reason=tuning_config.last_adjustment,
        )

        seq.append(trace_captured_event, trace_id=trace_id)

        self.bus.send(AgentMessage(
            str(uuid.uuid4()), "orchestrator", "supervisor", "control",
            {"action": "final_check", "health": ctx.system_health},
            trace_id=trace_id,
        ), ctx)

        latency = round((time.perf_counter() - t0) * 1000, 1)
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
            "latency_ms": latency,
            "cached": False,
        }

        self.cache.set("query", qkey, result, trace_id=trace_id)

        if self.working_memory:
            self.working_memory.update_from_query(
                session_id=session_id,
                query_text=query_text,
                intent=intent,
                answer=answer,
                products=[
                    e.get("value", "") for e in intent.get("entities", [])
                    if e.get("type") == "product"
                ],
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

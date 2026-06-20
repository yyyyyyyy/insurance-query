"""Multi-Agent Orchestrator — Coordinates 5 agents through the query pipeline.

Pipeline:
  Supervisor (health check)
    → PlannerAgent (intent + plan)
    → RetrievalAgent (hybrid retrieval + ontology)
    → ToolAgent (parallel tool execution)
    → Answer Generator
    → EvaluationAgent (quality scoring)
    → SupervisorAgent (final health check)
"""

from __future__ import annotations
import time
import uuid
from typing import Any, Dict, List, Optional
from runtime.agents.bus import AgentBus, AgentMessage, AgentContext
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
)
from infra.cache.store import TraceAwareCache
from knowledge.ingestion.pipeline import ChunkStore
from knowledge.ontology.graph import OntologyGraph
from knowledge.retrieval.engine import HybridRetriever

class MultiAgentEngine:
    """Production multi-agent runtime engine.

    Coordinates 5 agents through a central message bus. Each query is processed
    by the full agent chain with retry, fallback, and health monitoring.
    """

    def __init__(self, dispatcher: Optional[ToolDispatcher] = None,
                 cache: Optional[TraceAwareCache] = None,
                 event_store: Optional[EventStore] = None,
                 working_memory=None):
        self.bus = AgentBus()
        self.cache = cache or TraceAwareCache()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = create_default_executor()
        self.event_store = event_store or EventStore()
        self.working_memory = working_memory  # Optional WorkingMemory for multi-turn

        # Knowledge layer (lazy loaded)
        self._onto: Optional[OntologyGraph] = None
        self._retriever: Optional[HybridRetriever] = None
        self._chunk_store: Optional[ChunkStore] = None
        self._embedding_gen = None  # Lazy init from EmbeddingFactory
        self._vector_store = None   # Optional ChromaDB vector store

        # Register agents
        self.bus.register(PlannerAgent())
        self.bus.register(RetrievalAgent())
        self.bus.register(ToolAgent(self.dispatcher, self.async_exec))
        self.bus.register(EvaluationAgent())
        self.bus.register(SupervisorAgent())

        self._knowledge_loaded = False
        self._rules: List[Dict[str, Any]] = []

    def _ensure_knowledge(self):
        if self._knowledge_loaded:
            return
        from knowledge.ontology.builder import build_insurance_ontology
        from knowledge.retrieval.engine import HybridRetriever
        from knowledge.retrieval.embeddings import EmbeddingFactory
        from knowledge.ingestion.pipeline import ChunkStore, ingest_text_document
        from knowledge.evidence.index import EvidenceIndex
        from runtime.tools.document_data import DOCUMENT_STORE
        from runtime.tools.data_loader import load_faqs_as_documents, load_rules
        from infra.vector.store import ChromaVectorStore
        import logging
        logger = logging.getLogger(__name__)

        self._onto = build_insurance_ontology()
        self._chunk_store = ChunkStore()
        ei = EvidenceIndex()

        # Initialize embedding (sentence-transformers or TF-IDF fallback)
        self._embedding_gen = EmbeddingFactory.create()
        logger.info("Embedding provider: %s",
                    "sentence-transformers" if self._embedding_gen.using_sentence_transformer
                    else "TF-IDF fallback")

        # Initialize optional ChromaDB vector store
        self._vector_store = ChromaVectorStore()

        # Load FAQ documents into store
        faq_docs = load_faqs_as_documents()
        if faq_docs:
            for faq_doc in faq_docs:
                DOCUMENT_STORE.append(faq_doc)
            logger.info("Loaded %d FAQ documents into retrieval index", len(faq_docs))

        for doc in DOCUMENT_STORE:
            raw = "\n\n".join(f"[{c.get('clause','')}] {c['content']}" for c in doc.get("chunks",[]))
            _, chunks = ingest_text_document(raw, doc["document_id"], doc["title"],
                doc.get("document_type","policy_clause"), self._chunk_store, self._embedding_gen)
            for chunk in chunks:
                ei.index_chunk(chunk, doc.get("document_type","policy_clause"), doc["title"])
        self._retriever = HybridRetriever(self._chunk_store, self._embedding_gen, self._onto,
                                          vector_store=self._vector_store)
        self._retriever.fit()

        # Load rules for answer enrichment
        self._rules = load_rules()

        # Wire retriever into RetrievalAgent
        ra = self.bus.get_agent("retrieval")
        if ra:
            ra.retriever = self._retriever
        self._knowledge_loaded = True

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_knowledge()
        session_id = session_id or str(uuid.uuid4())
        trace_id = f"TRC-{uuid.uuid4().hex[:12]}"
        ctx = AgentContext(session_id=session_id, query=query_text, trace_id=trace_id)
        t0 = time.perf_counter()
        seq = 0

        # Check cache
        qkey = self.cache.query_key(query_text)
        cached_val, was_hit = self.cache.get("query", qkey)
        if was_hit:
            ctx.cache_state["query_hit"] = True
            cached_val["cached"] = True
            cached_val["trace_id"] = trace_id
            return cached_val
        ctx.cache_state["query_hit"] = False

        # Event: USER_QUERY
        seq += 1
        self.event_store.append(user_query_event(session_id, seq, query_text))

        # Step 1: Supervisor pre-check
        self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","supervisor","control",{"action":"health_check"},trace_id=trace_id), ctx)

        # Step 2: Planner
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","planner","task",{"query":query_text},trace_id=trace_id), ctx)
        intent = resp.payload.get("intent",{})
        plan = resp.payload.get("plan",resp.payload.get("fallback_plan",[]))
        ctx.intent = intent
        ctx.plan = plan
        ctx.execution_graph.append({"agent":"planner","intent":intent.get("intent"),"plan_len":len(plan)})

        # Event: INTENT_CLASSIFIED
        seq += 1
        self.event_store.append(intent_classified_event(
            session_id, seq, intent=intent.get("intent","general_inquiry"),
            confidence=intent.get("confidence",0.5), entities=intent.get("entities",[])))

        # Event: PLAN_CREATED
        seq += 1
        self.event_store.append(plan_created_event(session_id, seq, plan=plan,
            reasoning=f"Plan for intent: {intent.get('intent','general_inquiry')}"))

        # Step 3: Retrieval
        seed_names = [e.get("value","") for e in intent.get("entities",[])]
        onto_matches = self._ontology_expand(seed_names)
        ctx.ontology_context = onto_matches

        # Event: ONTOLOGY_EXPANDED
        if onto_matches:
            seq += 1
            self.event_store.append(ontology_expanded_event(
                session_id, seq, seed_entities=onto_matches,
                expanded_entities=onto_matches))

        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","retrieval","task",{"query":query_text,"ontology_context":seed_names},trace_id=trace_id), ctx)
        retrieval_chunks = resp.payload.get("chunks",[])
        ctx.retrieval_results = retrieval_chunks
        ctx.execution_graph.append({"agent":"retrieval","chunks":len(retrieval_chunks)})

        # Event: RETRIEVAL_EXECUTED
        seq += 1
        self.event_store.append(retrieval_executed_event(
            session_id, seq, query=query_text, result_count=len(retrieval_chunks),
            ontology_used=len(onto_matches) > 0))

        # Step 4: Tool execution
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","tool","task",{"plan":plan,"query":query_text,"retrieval_context":retrieval_chunks[:5]},trace_id=trace_id), ctx)
        agent_results = resp.payload.get("results",{})
        ctx.execution_graph.append({"agent":"tool","tools":list(agent_results.keys())})

        # Collect tool outputs and evidence
        tool_data: Dict[str, Any] = {}
        all_evidence: List[Dict[str, Any]] = []
        for tname, ar_dict in agent_results.items():
            status = ar_dict.get("status","")
            seq += 1
            self.event_store.append(tool_called_event(session_id, seq, tool_name=tname,
                input_params=ar_dict.get("metadata",{})))
            if status == "success" and ar_dict.get("result"):
                r = ar_dict["result"]
                tool_data[tname] = r.get("data",{})
                evidence = r.get("evidence",[])
                all_evidence.extend(evidence)
                seq += 1
                self.event_store.append(evidence_found_event(
                    session_id, seq, tool_name=tname,
                    evidence=evidence, output=r.get("data",{}),
                    duration_ms=r.get("duration_ms",0)))

        ctx.tool_results = tool_data
        ctx.evidence = all_evidence

        # Step 5: Answer generation
        from runtime.llm.answer import _format_citations, _compute_confidence
        from runtime.llm.plugin import compose_answer_auto
        answer_text = compose_answer_auto(query_text, intent.get("intent","general_inquiry"), tool_data, all_evidence)
        citations = _format_citations(all_evidence)
        confidence = _compute_confidence(intent, all_evidence)
        answer = {"text":answer_text,"citations":citations,"confidence":confidence,
                  "intent":intent.get("intent",""),"evidence_count":len(all_evidence)}
        ctx.answer = answer

        # Enrich answer with rule engine evaluation
        if self._rules:
            from knowledge.rules.engine import RuleEngine
            rule_engine = RuleEngine(self._rules)
            rule_eval = rule_engine.evaluate(
                query_text=query_text,
                intent=intent.get("intent", "general_inquiry"),
                tool_results=tool_data,
                evidence=all_evidence,
            )
            answer["rule_evaluation"] = rule_eval.to_dict()
            answer["matched_rules"] = [d.to_dict() for d in rule_eval.decisions if d.matched][:5]
            answer["rule_count"] = rule_eval.rules_matched

        # Event: ANSWER_GENERATED
        seq += 1
        self.event_store.append(answer_generated_event(
            session_id, seq, answer=answer["text"],
            citations=answer.get("citations",[]),
            confidence=answer.get("confidence")))

        # Step 6: Evaluation
        trace_data = {
            "session_id": session_id, "query": query_text,
            "events": [{"event_type":"USER_QUERY","payload":{"query_text":query_text}},
                       {"event_type":"INTENT_CLASSIFIED","payload":intent},
                       {"event_type":"PLAN_CREATED","payload":{"plan":plan}},
                       *[{"event_type":"TOOL_CALLED","payload":{"tool_name":tn}} for tn in agent_results],
                       *[{"event_type":"EVIDENCE_FOUND","payload":{"evidence":all_evidence}}],
                       {"event_type":"ANSWER_GENERATED","payload":{"answer":answer_text}}],
            "state": {"intent":intent,"answer":answer,"evidence_graph":{"nodes":[]},
                      "ontology_context":ctx.ontology_context,"retrieval_path":[]},
        }
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","evaluation","task",{"trace":trace_data},trace_id=trace_id), ctx)
        ctx.evaluation = resp.payload

        # Evaluation events (migrated from KnowledgeEngine)
        eval_result = ctx.evaluation
        seq += 1
        self.event_store.append(evaluation_completed_event(
            session_id, seq, total_score=float(eval_result.get("total_score",0)),
            dimensions=eval_result.get("dimensions",{}),
            diagnosis=eval_result.get("diagnosis","")))

        hal_score = float(eval_result.get("hallucination_score",0))
        hal_severity = eval_result.get("severity","NONE")
        seq += 1
        self.event_store.append(hallucination_detected_event(
            session_id, seq, hallucination_score=hal_score,
            severity=hal_severity, violations=[]))

        feedback_signals = eval_result.get("feedback",[])
        if feedback_signals:
            seq += 1
            self.event_store.append(system_feedback_generated_event(
                session_id, seq, signals=feedback_signals))

        # Event: TRACE_CAPTURED
        seq += 1
        self.event_store.append(trace_captured_event(session_id, seq, trace_id=trace_id))

        # Step 7: Supervisor post-check
        self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","supervisor","control",{"action":"final_check","health":ctx.system_health},trace_id=trace_id), ctx)

        latency = round((time.perf_counter() - t0) * 1000, 1)
        result = {
            "session_id": session_id, "trace_id": trace_id,
            "query": query_text, "answer": answer,
            "evaluation": ctx.evaluation,
            "execution_graph": ctx.execution_graph,
            "agent_statuses": self.bus.agent_statuses(),
            "message_log": self.bus.message_log(),
            "event_trace": [e.to_dict() for e in self.event_store.get_session_events(session_id)],
            "latency_ms": latency,
            "cached": False,
        }

        # Cache result
        self.cache.set("query", qkey, result, trace_id=trace_id)

        # Update working memory for multi-turn context
        if self.working_memory:
            self.working_memory.update_from_query(
                session_id=session_id,
                query_text=query_text,
                intent=intent,
                answer=answer,
                products=[e.get("value", "") for e in intent.get("entities", [])
                          if e.get("type") == "product"],
                entities=[e.get("value", "") for e in intent.get("entities", [])],
            )
            result["working_memory"] = self.working_memory.get_context_for_query(session_id)

        return result

    def _ontology_expand(self, seed_names: List[str]) -> List[str]:
        if not self._onto or not seed_names:
            return []
        matches = []
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
            "embedding": "sentence-transformers" if (self._embedding_gen and self._embedding_gen.using_sentence_transformer) else "TF-IDF",
        }

    def get_session_trace(self, session_id: str) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self.event_store.get_session_events(session_id)]

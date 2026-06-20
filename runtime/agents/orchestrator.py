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
import time, uuid
from typing import Any, Dict, List, Optional
from runtime.agents.bus import AgentBus, AgentMessage, AgentContext, AgentStatus
from runtime.agents.agents import (
    PlannerAgent, RetrievalAgent, ToolAgent, EvaluationAgent, SupervisorAgent
)
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.execution.executor import AsyncExecutor, create_default_executor
from infra.cache.store import TraceAwareCache
from knowledge.ingestion.pipeline import ChunkStore, EmbeddingGenerator
from knowledge.ontology.graph import OntologyGraph
from knowledge.ontology.builder import build_insurance_ontology
from knowledge.retrieval.engine import HybridRetriever

class MultiAgentEngine:
    """Production multi-agent runtime engine.

    Coordinates 5 agents through a central message bus. Each query is processed
    by the full agent chain with retry, fallback, and health monitoring.
    """

    def __init__(self, dispatcher: Optional[ToolDispatcher] = None,
                 cache: Optional[TraceAwareCache] = None):
        self.bus = AgentBus()
        self.cache = cache or TraceAwareCache()
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = create_default_executor()

        # Knowledge layer (lazy loaded)
        self._onto: Optional[OntologyGraph] = None
        self._retriever: Optional[HybridRetriever] = None
        self._chunk_store: Optional[ChunkStore] = None
        self._embedding_gen = EmbeddingGenerator(vector_dim=256)

        # Register agents
        self.bus.register(PlannerAgent())
        self.bus.register(RetrievalAgent())
        self.bus.register(ToolAgent(self.dispatcher, self.async_exec))
        self.bus.register(EvaluationAgent())
        self.bus.register(SupervisorAgent())

        self._knowledge_loaded = False

    def _ensure_knowledge(self):
        if self._knowledge_loaded: return
        from knowledge.ontology.builder import build_insurance_ontology
        from knowledge.retrieval.engine import HybridRetriever
        from knowledge.ingestion.pipeline import ChunkStore, EmbeddingGenerator, ingest_text_document
        from knowledge.evidence.index import EvidenceIndex
        from runtime.tools.document_data import DOCUMENT_STORE

        self._onto = build_insurance_ontology()
        self._chunk_store = ChunkStore()
        ei = EvidenceIndex()
        for doc in DOCUMENT_STORE:
            raw = "\n\n".join(f"[{c.get('clause','')}] {c['content']}" for c in doc.get("chunks",[]))
            _, chunks = ingest_text_document(raw, doc["document_id"], doc["title"],
                doc.get("document_type","policy_clause"), self._chunk_store, self._embedding_gen)
            for chunk in chunks:
                ei.index_chunk(chunk, doc.get("document_type","policy_clause"), doc["title"])
        self._retriever = HybridRetriever(self._chunk_store, self._embedding_gen, self._onto)
        self._retriever.fit()

        # Wire retriever into RetrievalAgent
        ra = self.bus.get_agent("retrieval")
        if ra: ra.retriever = self._retriever
        self._knowledge_loaded = True

    def query(self, query_text: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        self._ensure_knowledge()
        session_id = session_id or str(uuid.uuid4())
        trace_id = f"TRC-{uuid.uuid4().hex[:12]}"
        ctx = AgentContext(session_id=session_id, query=query_text, trace_id=trace_id)
        t0 = time.perf_counter()

        # Check cache
        qkey = self.cache.query_key(query_text)
        cached_val, was_hit = self.cache.get("query", qkey)
        if was_hit:
            ctx.cache_state["query_hit"] = True
            cached_val["cached"] = True
            cached_val["trace_id"] = trace_id
            return cached_val
        ctx.cache_state["query_hit"] = False

        # Step 1: Supervisor pre-check
        self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","supervisor","control",{"action":"health_check"},trace_id=trace_id))

        # Step 2: Planner
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","planner","task",{"query":query_text},trace_id=trace_id))
        intent = resp.payload.get("intent",{})
        plan = resp.payload.get("plan",resp.payload.get("fallback_plan",[]))
        ctx.intent = intent; ctx.plan = plan
        ctx.execution_graph.append({"agent":"planner","intent":intent.get("intent"),"plan_len":len(plan)})

        # Step 3: Retrieval
        seed_names = [e.get("value","") for e in intent.get("entities",[])]
        onto_matches = self._ontology_expand(seed_names)
        ctx.ontology_context = onto_matches

        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","retrieval","task",{"query":query_text,"ontology_context":seed_names},trace_id=trace_id))
        retrieval_chunks = resp.payload.get("chunks",[])
        ctx.retrieval_results = retrieval_chunks
        ctx.execution_graph.append({"agent":"retrieval","chunks":len(retrieval_chunks)})

        # Step 4: Tool execution
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","tool","task",{"plan":plan,"query":query_text,"retrieval_context":retrieval_chunks[:5]},trace_id=trace_id))
        agent_results = resp.payload.get("results",{})
        ctx.execution_graph.append({"agent":"tool","tools":list(agent_results.keys())})

        # Collect tool outputs and evidence
        tool_data: Dict[str, Any] = {}
        all_evidence: List[Dict[str, Any]] = []
        for tname, ar_dict in agent_results.items():
            status = ar_dict.get("status","")
            if status == "success" and ar_dict.get("result"):
                r = ar_dict["result"]
                tool_data[tname] = r.get("data",{})
                all_evidence.extend(r.get("evidence",[]))

        ctx.tool_results = tool_data
        ctx.evidence = all_evidence

        # Step 5: Answer generation
        from runtime.engine.engine import _format_citations, _compute_confidence
        from runtime.llm.plugin import compose_answer_auto
        answer_text = compose_answer_auto(query_text, intent.get("intent","general_inquiry"), tool_data, all_evidence)
        citations = _format_citations(all_evidence)
        confidence = _compute_confidence(intent, all_evidence)
        answer = {"text":answer_text,"citations":citations,"confidence":confidence,
                  "intent":intent.get("intent",""),"evidence_count":len(all_evidence)}
        ctx.answer = answer

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
        resp = self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","evaluation","task",{"trace":trace_data},trace_id=trace_id))
        ctx.evaluation = resp.payload

        # Step 7: Supervisor post-check
        self.bus.send(AgentMessage(str(uuid.uuid4()),"orchestrator","supervisor","control",{"action":"final_check","health":ctx.system_health},trace_id=trace_id))

        latency = round((time.perf_counter() - t0) * 1000, 1)
        result = {
            "session_id": session_id, "trace_id": trace_id,
            "query": query_text, "answer": answer,
            "evaluation": ctx.evaluation,
            "execution_graph": ctx.execution_graph,
            "agent_statuses": self.bus.agent_statuses(),
            "message_log": self.bus.message_log(),
            "latency_ms": latency,
            "cached": False,
        }

        # Cache result
        self.cache.set("query", qkey, result, trace_id=trace_id)
        return result

    def _ontology_expand(self, seed_names: List[str]) -> List[str]:
        if not self._onto or not seed_names: return []
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
        }

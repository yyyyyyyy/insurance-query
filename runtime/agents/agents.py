"""5 Specialized Agents: Planner, Retrieval, Tool, Evaluation, Supervisor."""

from __future__ import annotations
import uuid
from typing import Any, Dict
from runtime.agents.bus import BaseAgent, AgentMessage, AgentContext, AgentStatus
from runtime.llm.plugin import classify_intent_auto, generate_plan_auto
from runtime.memory.resolver import merge_entities_into_intent
from runtime.memory.facts import extract_facts_from_tool, merge_facts
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.execution.executor import create_default_executor

# ============================================================
# 1. PlannerAgent
# ============================================================

class PlannerAgent(BaseAgent):
    """Decomposes query, classifies intent, builds tool execution graph.
    Uses working memory context to enrich intent and plan."""
    def __init__(self): super().__init__("planner")
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            query = msg.payload.get("query", ctx.query if ctx else "")
            memory_context = msg.payload.get("memory_context", {})
            injected = msg.payload.get("injected_entities", [])

            intent = classify_intent_auto(query)
            if injected:
                intent = merge_entities_into_intent(intent, injected)

            # Enrich plan from memory product IDs
            if memory_context.get("previous_product_ids"):
                for ent in memory_context["previous_product_ids"]:
                    injected.append({"type": "product_id", "value": ent, "source": "memory"})
                intent = merge_entities_into_intent(intent, injected)

            plan = generate_plan_auto(query, intent)

            # Apply memory product IDs to plan steps
            prev_ids = memory_context.get("previous_product_ids", [])
            if not prev_ids:
                facts = memory_context.get("facts", {})
                for key, val in facts.items():
                    if key == "last_compared_products" and isinstance(val, dict):
                        prev_ids = val.get("value", [])
                    if key == "last_product_ids" and isinstance(val, dict):
                        prev_ids = val.get("value", [])

            if prev_ids:
                for step in plan:
                    params = step.get("input_params", {})
                    if "product_ids" in params:
                        params["product_ids"] = prev_ids[:2] if len(prev_ids) >= 2 else prev_ids
                    if "product_id" in params and prev_ids:
                        params["product_id"] = prev_ids[0]

            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"planner","orchestrator","result",
                {"intent":intent,"plan":plan},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1
            self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"planner","orchestrator","error",
                {"error":str(e),"fallback_plan":generate_plan_auto(msg.payload.get("query",""),{"intent":"general_inquiry","confidence":0.5,"entities":[]})},trace_id=msg.trace_id)

# ============================================================
# 2. RetrievalAgent
# ============================================================

class RetrievalAgent(BaseAgent):
    """Executes hybrid retrieval with tuner-weighted scoring."""
    def __init__(self, retriever=None):
        super().__init__("retrieval")
        self.retriever = retriever
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            query = msg.payload.get("query","")
            onto_ctx = list(msg.payload.get("ontology_context",[]))
            memory_context = msg.payload.get("memory_context", {})
            retrieval_weights = msg.payload.get("retrieval_weights", {})

            # Merge memory entities into ontology context
            for prod in memory_context.get("previous_products", []):
                if prod and prod not in onto_ctx:
                    onto_ctx.append(prod)
            for ent in memory_context.get("previous_entities", []):
                if ent and ent not in onto_ctx:
                    onto_ctx.append(ent)

            bm25_w = retrieval_weights.get("bm25_weight", 0.4)
            vector_w = retrieval_weights.get("vector_weight", 0.4)
            onto_w = retrieval_weights.get("ontology_boost", 0.2)
            top_k = retrieval_weights.get("top_k", 10)
            min_score = float(retrieval_weights.get("min_score", 0.0))

            decision_trace = []
            if self.retriever:
                results = self.retriever.retrieve(
                    query, top_k=top_k, ontology_context=onto_ctx,
                    bm25_weight=bm25_w, vector_weight=vector_w,
                    ontology_boost=onto_w, min_score=min_score,
                )
                chunks = []
                for rank, (c, s, fc) in enumerate(results):
                    chunks.append({
                        "chunk_id": c.chunk_id,
                        "document_id": c.document_id,
                        "content": c.content[:150],
                        "clause": c.clause,
                        "score": round(s, 4),
                        "feature_contribution": fc,
                    })
                    decision_trace.append({
                        "chunk_id": c.chunk_id,
                        "rank": rank,
                        "score": round(s, 4),
                        "feature_contribution": fc,
                    })
            else:
                chunks = []
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"retrieval","orchestrator","result",
                {"chunks":chunks,"total":len(chunks),"weights_used":retrieval_weights,
                 "decision_trace": decision_trace},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1
            self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"retrieval","orchestrator","error",
                {"error":str(e),"chunks":[]},trace_id=msg.trace_id)

# ============================================================
# 3. ToolAgent
# ============================================================

class ToolAgent(BaseAgent):
    """Executes tool chains deterministically via dispatcher + async executor.
    Writes memory facts on successful tool execution."""
    def __init__(self, dispatcher=None, async_exec=None):
        super().__init__("tool")
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = async_exec or create_default_executor()
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            plan = msg.payload.get("plan",[])
            hints = msg.payload.get("retrieval_context", [])
            tool_results = {}
            memory_facts_written: Dict[str, Any] = {}
            for step in plan:
                tool_name = step.get("tool_name","")
                params = dict(step.get("input_params",{}))
                params["query"] = msg.payload.get("query","")
                if hints:
                    params["_retrieval_hints"] = hints
                result = self.async_exec.execute(tool_name, self.dispatcher.dispatch, params)
                tool_results[tool_name] = result
                if result.success and result.result:
                    facts = extract_facts_from_tool(tool_name, result.result.data)
                    ctx.memory_facts = merge_facts(ctx.memory_facts, facts)
                    for f in facts:
                        memory_facts_written[f.key] = f.to_dict()
                if not result.success:
                    ctx.failure_recovery_path.append(f"tool:{tool_name}:{result.status.value}")
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"tool","orchestrator","result",
                {"results":{k:v.to_dict() for k,v in tool_results.items()},
                 "memory_facts": memory_facts_written},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1
            self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"tool","orchestrator","error",
                {"error":str(e),"results":{}},trace_id=msg.trace_id)

# ============================================================
# 4. EvaluationAgent
# ============================================================

class EvaluationAgent(BaseAgent):
    """Runs evaluation pipeline from event_store truth (no synthetic trace)."""
    def __init__(self): super().__init__("evaluation")
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            from evaluation.engine.scorer import EvaluationEngine
            from evaluation.hallucination.detector import HallucinationDetector
            from evaluation.feedback.loop import FeedbackLoop
            from evaluation.trace.capture import TraceCapture

            events = msg.payload.get("events")
            if not events:
                self.status = AgentStatus.DEGRADED
                return AgentMessage(str(uuid.uuid4()),"evaluation","orchestrator","result",
                    {"total_score":0,"diagnosis":"No event_store events"},trace_id=msg.trace_id)

            tc = TraceCapture()
            sid = ctx.session_id if ctx else msg.payload.get("session_id", "unknown")
            q = ctx.query if ctx else msg.payload.get("query", "")
            state = msg.payload.get("state", {})
            if not state.get("intent") and ctx:
                state = {
                    "intent": ctx.intent,
                    "answer": ctx.answer,
                    "ontology_context": ctx.ontology_context,
                    "process_result": ctx.process_result,
                    "rule_evaluation": ctx.rule_evaluation,
                }
            trace = tc.capture(sid, q, events, state)
            ee = EvaluationEngine()
            hd = HallucinationDetector()
            fl = FeedbackLoop()
            er = ee.evaluate(trace)
            hal = hd.detect(trace)
            fb = fl.generate(er, hal)
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"evaluation","orchestrator","result",{
                "total_score":er.total_score,"dimensions":{k:v.score for k,v in er.dimensions.items()},
                "hallucination_score":hal.hallucination_score,"severity":hal.severity,
                "violations":[{"type":v.violation_type,"description":v.description,
                               "severity":v.severity} for v in hal.violations],
                "diagnosis":er.diagnosis,"feedback":[f.to_dict() for f in fb]
            },trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1
            self.status = AgentStatus.DEGRADED
            return AgentMessage(str(uuid.uuid4()),"evaluation","orchestrator","error",
                {"error":str(e),"degraded":True},trace_id=msg.trace_id)

# ============================================================
# 5. SupervisorAgent
# ============================================================

class SupervisorAgent(BaseAgent):
    """Monitors system behavior, handles failures, triggers re-planning."""
    def __init__(self): super().__init__("supervisor")
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        health = {"overall":"healthy","issues":[]}
        if ctx:
            for aname, astatus in ctx.agent_statuses.items():
                if isinstance(astatus, AgentStatus) and astatus == AgentStatus.FAILED:
                    health["issues"].append(f"Agent {aname} failed")
            health["degraded"] = ctx.degraded_mode
            if len(ctx.failure_recovery_path) > 2:
                health["overall"] = "degrading"
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
        return AgentMessage(str(uuid.uuid4()),"supervisor","orchestrator","result",
            {"health":health,"recovery_actions":["retry_failed_agents","enable_fallbacks"] if health["issues"] else []},
            trace_id=msg.trace_id)

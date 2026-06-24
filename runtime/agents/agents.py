"""5 Specialized Agents: Planner, Retrieval, Tool, Evaluation, Supervisor."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from runtime.agents.bus import BaseAgent, AgentMessage, AgentContext, AgentStatus
from runtime.llm.plugin import classify_intent_auto, generate_plan_auto
from runtime.memory.resolver import merge_entities_into_intent
from runtime.memory.facts import extract_facts_from_tool, merge_facts
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.execution.executor import create_default_executor


class PlannerAgent(BaseAgent):
    """Decomposes query, classifies intent, builds tool execution graph."""

    def __init__(self):
        super().__init__("planner")

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        try:
            query = msg.payload.get("query", ctx.query if ctx else "")
            memory_context = msg.payload.get("memory_context", {})
            injected = msg.payload.get("injected_entities", [])

            intent = classify_intent_auto(query)
            if injected:
                intent = merge_entities_into_intent(intent, injected)

            if memory_context.get("previous_product_ids"):
                for ent in memory_context["previous_product_ids"]:
                    injected.append({"type": "product_id", "value": ent, "source": "memory"})
                intent = merge_entities_into_intent(intent, injected)

            plan = generate_plan_auto(query, intent)

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

            self._record_success(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "planner", "orchestrator", "result",
                {"intent": intent, "plan": plan},
                trace_id=msg.trace_id,
            )
        except Exception as e:
            self._record_failure(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "planner", "orchestrator", "error",
                {
                    "error": str(e),
                    "fallback_plan": generate_plan_auto(
                        msg.payload.get("query", ""),
                        {"intent": "general_inquiry", "confidence": 0.5, "entities": []},
                    ),
                },
                trace_id=msg.trace_id,
            )


class RetrievalAgent(BaseAgent):
    """Executes hybrid retrieval with tuner-weighted scoring."""

    def __init__(self, retriever=None):
        super().__init__("retrieval")
        self.retriever = retriever

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        try:
            query = msg.payload.get("query", "")
            onto_ctx = list(msg.payload.get("ontology_context", []))
            memory_context = msg.payload.get("memory_context", {})
            retrieval_weights = msg.payload.get("retrieval_weights", {})

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

            self._record_success(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "retrieval", "orchestrator", "result",
                {
                    "chunks": chunks,
                    "total": len(chunks),
                    "weights_used": retrieval_weights,
                    "decision_trace": decision_trace,
                },
                trace_id=msg.trace_id,
            )
        except Exception as e:
            self._record_failure(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "retrieval", "orchestrator", "error",
                {"error": str(e), "chunks": []},
                trace_id=msg.trace_id,
            )


class ToolAgent(BaseAgent):
    """Executes tool chains via dispatcher + async executor."""

    def __init__(self, dispatcher=None, async_exec=None):
        super().__init__("tool")
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = async_exec or create_default_executor()

    @staticmethod
    def _plan_layers(plan: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        if not plan:
            return []
        if not any(step.get("depends_on") for step in plan):
            return [plan]
        completed: set = set()
        remaining = list(plan)
        layers: List[List[Dict[str, Any]]] = []
        while remaining:
            layer = [
                s for s in remaining
                if all(dep in completed for dep in s.get("depends_on", []))
            ]
            if not layer:
                layer = remaining
                remaining = []
            else:
                remaining = [s for s in remaining if s not in layer]
            layers.append(layer)
            for step in layer:
                sid = step.get("step_id")
                if sid is not None:
                    completed.add(sid)
        return layers

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        try:
            plan = msg.payload.get("plan", [])
            hints = msg.payload.get("retrieval_context", [])
            tool_results = {}
            memory_facts_written: Dict[str, Any] = {}

            for layer in self._plan_layers(plan):
                parallel_calls = []
                for step in layer:
                    tool_name = step.get("tool_name", "")
                    params = dict(step.get("input_params", {}))
                    params["query"] = msg.payload.get("query", "")
                    if hints:
                        params["_retrieval_hints"] = hints
                    parallel_calls.append((tool_name, params))

                async_results = (
                    self.async_exec.execute_parallel(parallel_calls, self.dispatcher.dispatch)
                    if parallel_calls else []
                )

                for async_result in async_results:
                    tool_name = async_result.tool_name
                    result = async_result
                    tool_results[tool_name] = result
                    if result.success and result.result:
                        facts = extract_facts_from_tool(tool_name, result.result.data)
                        ctx.memory_facts = merge_facts(ctx.memory_facts, facts)
                        for f in facts:
                            memory_facts_written[f.key] = f.to_dict()
                    if not result.success:
                        ctx.failure_recovery_path.append(
                            f"tool:{tool_name}:{result.status.value}",
                        )

            self._record_success(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "tool", "orchestrator", "result",
                {
                    "results": {k: v.to_dict() for k, v in tool_results.items()},
                    "memory_facts": memory_facts_written,
                },
                trace_id=msg.trace_id,
            )
        except Exception as e:
            self._record_failure(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "tool", "orchestrator", "error",
                {"error": str(e), "results": {}},
                trace_id=msg.trace_id,
            )


class EvaluationAgent(BaseAgent):
    """Runs evaluation pipeline from event_store truth."""

    def __init__(self):
        super().__init__("evaluation")

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        try:
            from evaluation.engine.scorer import EvaluationEngine
            from evaluation.hallucination.detector import HallucinationDetector
            from evaluation.feedback.loop import FeedbackLoop
            from evaluation.trace.capture import TraceCapture

            events = msg.payload.get("events")
            if not events:
                self._record_failure(ctx, AgentStatus.DEGRADED)
                return AgentMessage(
                    str(uuid.uuid4()), "evaluation", "orchestrator", "result",
                    {"total_score": 0, "diagnosis": "No event_store events"},
                    trace_id=msg.trace_id,
                )

            tc = TraceCapture()
            sid = ctx.session_id if ctx else msg.payload.get("session_id", "unknown")
            q = ctx.query if ctx else msg.payload.get("query", "")
            trace = tc.capture(sid, q, events, {})
            ee = EvaluationEngine()
            hd = HallucinationDetector()
            fl = FeedbackLoop()
            er = ee.evaluate(trace)
            hal = hd.detect(trace)
            fb = fl.generate(er, hal)
            self._record_success(ctx)
            return AgentMessage(
                str(uuid.uuid4()), "evaluation", "orchestrator", "result",
                {
                    "total_score": er.total_score,
                    "dimensions": {k: v.score for k, v in er.dimensions.items()},
                    "hallucination_score": hal.hallucination_score,
                    "severity": hal.severity,
                    "violations": [
                        {
                            "type": v.violation_type,
                            "description": v.description,
                            "severity": v.severity,
                        }
                        for v in hal.violations
                    ],
                    "diagnosis": er.diagnosis,
                    "feedback": [f.to_dict() for f in fb],
                },
                trace_id=msg.trace_id,
            )
        except Exception as e:
            self._record_failure(ctx, AgentStatus.DEGRADED)
            return AgentMessage(
                str(uuid.uuid4()), "evaluation", "orchestrator", "error",
                {"error": str(e), "degraded": True},
                trace_id=msg.trace_id,
            )


class SupervisorAgent(BaseAgent):
    """Monitors system behavior and handles failures."""

    def __init__(self):
        super().__init__("supervisor")

    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self._set_ctx_status(ctx, AgentStatus.RUNNING)
        health: Dict[str, Any] = {"overall": "healthy", "issues": []}
        recovery_actions: List[str] = []
        if ctx:
            for aname, astatus in ctx.agent_statuses.items():
                if isinstance(astatus, AgentStatus) and astatus == AgentStatus.FAILED:
                    health["issues"].append(f"Agent {aname} failed")
                    if aname == "planner":
                        recovery_actions.append("retry_template_plan")
            if ctx.agent_statuses.get("planner") == AgentStatus.FAILED:
                from runtime.engine.planner import generate_plan
                recovery_actions.append("fallback_general_inquiry_plan")
                health["fallback_plan"] = generate_plan(
                    ctx.query, {"intent": "general_inquiry", "entities": []},
                )
            health["degraded"] = ctx.degraded_mode
            if len(ctx.failure_recovery_path) > 2:
                health["overall"] = "degrading"
            if health["issues"]:
                health["overall"] = "degraded"
            self._record_success(ctx)
        return AgentMessage(
            str(uuid.uuid4()), "supervisor", "orchestrator", "result",
            {"health": health, "recovery_actions": recovery_actions},
            trace_id=msg.trace_id,
        )

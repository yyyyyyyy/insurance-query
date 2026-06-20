"""5 Specialized Agents: Planner, Retrieval, Tool, Evaluation, Supervisor."""

from __future__ import annotations
import time, uuid
from typing import Any, Dict, List, Optional
from runtime.agents.bus import BaseAgent, AgentMessage, AgentContext, AgentStatus
from runtime.llm.plugin import classify_intent_auto, generate_plan_auto
from runtime.tools.registry import ToolDispatcher, create_default_registry
from runtime.tools.base import ToolResult, ToolStatus
from runtime.execution.executor import AsyncExecutor, AsyncResult, ExecutionStatus, create_default_executor
from infra.cache.store import TraceAwareCache

# ============================================================
# 1. PlannerAgent
# ============================================================

class PlannerAgent(BaseAgent):
    """Decomposes query, classifies intent, builds tool execution graph.
    Uses ontology context + evaluation feedback to improve plan quality."""
    def __init__(self): super().__init__("planner")
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            query = msg.payload.get("query", ctx.query if ctx else "")
            intent = classify_intent_auto(query)
            plan = generate_plan_auto(query, intent)
            self.execution_count += 1
            self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"planner","orchestrator","result",
                {"intent":intent,"plan":plan},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1; self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"planner","orchestrator","error",
                {"error":str(e),"fallback_plan":generate_plan_auto(msg.payload.get("query",""),{"intent":"general_inquiry","confidence":0.5,"entities":[]})},trace_id=msg.trace_id)

# ============================================================
# 2. RetrievalAgent
# ============================================================

class RetrievalAgent(BaseAgent):
    """Executes hybrid retrieval, ranks evidence, returns ranked chunks."""
    def __init__(self, retriever=None):
        super().__init__("retrieval"); self.retriever = retriever
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            query = msg.payload.get("query","")
            onto_ctx = msg.payload.get("ontology_context",[])
            if self.retriever:
                results = self.retriever.retrieve(query, top_k=10, ontology_context=onto_ctx)
                chunks = [{"chunk_id":c.chunk_id,"document_id":c.document_id,"content":c.content[:150],"clause":c.clause,"score":round(s,4)} for c,s in results]
            else:
                chunks = []
            self.execution_count += 1; self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"retrieval","orchestrator","result",
                {"chunks":chunks,"total":len(chunks)},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1; self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"retrieval","orchestrator","error",
                {"error":str(e),"chunks":[]},trace_id=msg.trace_id)

# ============================================================
# 3. ToolAgent
# ============================================================

class ToolAgent(BaseAgent):
    """Executes tool chains deterministically via dispatcher + async executor."""
    def __init__(self, dispatcher=None, async_exec=None):
        super().__init__("tool")
        self.dispatcher = dispatcher or ToolDispatcher(create_default_registry())
        self.async_exec = async_exec or create_default_executor()
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            plan = msg.payload.get("plan",[])
            tool_results = {}
            for step in plan:
                tool_name = step.get("tool_name","")
                params = dict(step.get("input_params",{}))
                params["query"] = msg.payload.get("query","")
                result = self.async_exec.execute(tool_name, self.dispatcher.dispatch, params)
                tool_results[tool_name] = result
                if not result.success:
                    ctx.failure_recovery_path.append(f"tool:{tool_name}:{result.status.value}")
            self.execution_count += 1; self.status = AgentStatus.COMPLETED
            return AgentMessage(str(uuid.uuid4()),"tool","orchestrator","result",
                {"results":{k:v.to_dict() for k,v in tool_results.items()}},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1; self.status = AgentStatus.FAILED
            return AgentMessage(str(uuid.uuid4()),"tool","orchestrator","error",
                {"error":str(e),"results":{}},trace_id=msg.trace_id)

# ============================================================
# 4. EvaluationAgent
# ============================================================

class EvaluationAgent(BaseAgent):
    """Runs evaluation pipeline asynchronously after answer generation."""
    def __init__(self): super().__init__("evaluation")
    def handle(self, msg: AgentMessage, ctx: AgentContext) -> AgentMessage:
        self.status = AgentStatus.RUNNING
        try:
            from evaluation.engine.scorer import EvaluationEngine
            from evaluation.hallucination.detector import HallucinationDetector
            from evaluation.feedback.loop import FeedbackLoop
            from evaluation.trace.capture import TraceCapture
            trace_data = msg.payload.get("trace")
            if trace_data:
                tc = TraceCapture()
                sid = ctx.session_id if ctx else msg.payload.get("session_id", "unknown")
                q = ctx.query if ctx else msg.payload.get("query", "")
                trace = tc.capture(sid, q,
                    trace_data.get("events", []), trace_data.get("state", {}))
                ee = EvaluationEngine(); hd = HallucinationDetector(); fl = FeedbackLoop()
                er = ee.evaluate(trace); hal = hd.detect(trace)
                fb = fl.generate(er, hal)
                self.execution_count += 1; self.status = AgentStatus.COMPLETED
                return AgentMessage(str(uuid.uuid4()),"evaluation","orchestrator","result",{
                    "total_score":er.total_score,"dimensions":{k:v.score for k,v in er.dimensions.items()},
                    "hallucination_score":hal.hallucination_score,"severity":hal.severity,
                    "diagnosis":er.diagnosis,"feedback":[f.to_dict() for f in fb]
                },trace_id=msg.trace_id)
            self.status = AgentStatus.DEGRADED
            return AgentMessage(str(uuid.uuid4()),"evaluation","orchestrator","result",
                {"total_score":0,"diagnosis":"No trace data"},trace_id=msg.trace_id)
        except Exception as e:
            self.failure_count += 1; self.status = AgentStatus.DEGRADED
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
        # Check agent statuses
        if ctx:
            for aname, astatus in ctx.agent_statuses.items():
                if isinstance(astatus, AgentStatus) and astatus == AgentStatus.FAILED:
                    health["issues"].append(f"Agent {aname} failed")
            health["degraded"] = ctx.degraded_mode
            if len(ctx.failure_recovery_path) > 2:
                health["overall"] = "degrading"
        self.execution_count += 1; self.status = AgentStatus.COMPLETED
        return AgentMessage(str(uuid.uuid4()),"supervisor","orchestrator","result",
            {"health":health,"recovery_actions":["retry_failed_agents","enable_fallbacks"] if health["issues"] else []},
            trace_id=msg.trace_id)

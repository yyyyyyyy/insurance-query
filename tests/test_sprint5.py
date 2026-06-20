
"""Sprint 5 Tests - Multi-Agent, Async, Cache, Observability."""
from runtime.agents.bus import AgentBus, AgentMessage, AgentContext, BaseAgent
from runtime.agents.agents import PlannerAgent, ToolAgent
from runtime.agents.orchestrator import MultiAgentEngine
from runtime.execution.executor import AsyncExecutor, ExecutionConfig
from infra.cache.store import TraceAwareCache
from infra.observability.monitor import ObservabilityLayer, StageMetrics
from runtime.tools.registry import ToolDispatcher, create_default_registry

class TestAgentBus:
    def test_register(self):
        bus=AgentBus()
        class A(BaseAgent):
            def __init__(s): super().__init__("a")
            def handle(s,m,c): return m
        bus.register(A())
        assert "a" in bus.list_agents()
    def test_send(self):
        bus=AgentBus()
        class E(BaseAgent):
            def __init__(s): super().__init__("e")
            def handle(s,m,c): return AgentMessage("r","e","s","r",{"e":m.payload})
        bus.register(E())
        r=bus.send(AgentMessage("m","s","e","t",{"d":"x"}))
        assert r.payload=={"e":{"d":"x"}}
    def test_msg_log(self):
        bus=AgentBus()
        class N(BaseAgent):
            def __init__(s): super().__init__("n")
            def handle(s,m,c): return m
        bus.register(N())
        bus.send(AgentMessage("m","s","n","t",{}))
        assert len(bus.message_log())==1
    def test_statuses(self):
        bus=AgentBus()
        class S(BaseAgent):
            def __init__(s): super().__init__("s")
            def handle(s,m,c): return m
        bus.register(S())
        assert "s" in bus.agent_statuses()

class TestPlanner:
    def test_plan(self):
        a=PlannerAgent()
        r=a.handle(AgentMessage("m","o","p","t",{"query":"test"}),AgentContext("s","test"))
        assert r.msg_type=="result"
        assert "plan" in r.payload
    def test_fallback(self):
        a=PlannerAgent()
        r=a.handle(AgentMessage("m","o","p","t",{"query":""}),AgentContext("s",""))
        assert r.payload.get("intent") is not None

class TestTool:
    def test_exec(self):
        d=ToolDispatcher(create_default_registry())
        a=ToolAgent(dispatcher=d)
        r=a.handle(AgentMessage("m","o","t","t",{"plan":[{"step_id":1,"tool_name":"product_search","input_params":{"top_k":2}}],"query":"test"}),AgentContext("s","t"))
        assert r.msg_type=="result"
        assert "results" in r.payload

class TestEngine:
    def test_full_pipeline(self):
        e=MultiAgentEngine()
        r=e.query("重疾险保障什么")
        assert r["trace_id"]
        assert r["answer"]["text"]
        assert r["evaluation"] is not None
    def test_exec_graph(self):
        e=MultiAgentEngine()
        r=e.query("比较e生保和好医保")
        assert len(r["execution_graph"])>=2
    def test_cache(self):
        e=MultiAgentEngine()
        e.query("cachetest")
        r2=e.query("cachetest")
        assert r2.get("cached") is True
    def test_agent_statuses(self):
        e=MultiAgentEngine()
        e.query("test")
        s=e.bus.agent_statuses()
        assert "planner" in s
        assert "tool" in s

class TestAsync:
    def test_exec(self):
        x = AsyncExecutor()
        d = ToolDispatcher(create_default_registry())
        r = x.execute("product_search", d.dispatch, {"query":"医疗","top_k":3})
        assert r.success
        assert r.attempts == 1
    def test_parallel(self):
        x = AsyncExecutor(ExecutionConfig(max_workers=4))
        d = ToolDispatcher(create_default_registry())
        res = x.execute_parallel([("product_search",{"query":"医疗","top_k":2}),("document_search",{"query":"等待期","top_k":2})], d.dispatch)
        assert len(res)==2
    def test_stats(self):
        x = AsyncExecutor()
        d = ToolDispatcher(create_default_registry())
        x.execute("product_search", d.dispatch, {"query":"医疗"})
        assert x.stats()["total"]>=1

class TestCache:
    def test_get_set(self):
        c = TraceAwareCache()
        c.set("tool", "k1", "v1", trace_id="TRC-1")
        v, h = c.get("tool", "k1")
        assert h
        assert v=="v1"
    def test_miss(self):
        c = TraceAwareCache()
        _, h = c.get("tool", "nx")
        assert not h
    def test_deterministic_key(self):
        c = TraceAwareCache()
        k1 = c.tool_key("p", {"a": 1})
        k2 = c.tool_key("p", {"a": 1})
        assert k1==k2
    def test_invalidate(self):
        c = TraceAwareCache()
        c.set("tool", "k1", "v1")
        c.set("tool", "k2", "v2")
        assert c.invalidate("tool") == 2
        _,h=c.get("tool","k1")
        assert not h
    def test_stats(self):
        c = TraceAwareCache()
        c.set("query", "k1", "v")
        c.set("query", "k2", "v2")
        c.get("query", "k1")
        c.get("query", "k3")
        s=c.stats()
        assert s["total_hits"]>=1
        assert s["total_misses"]>=1
        assert s["hit_rate"]<=1.0

class TestObservability:
    def test_metrics(self):
        o=ObservabilityLayer()
        o.log_event("start",{"q":"t"})
        o.metrics.record_query(100,"TRC-1")
        o.metrics.record_tool("t",True)
        s=o.metrics.snapshot()
        assert s["queries"]["total"]==1
    def test_dashboard(self):
        o=ObservabilityLayer()
        o.metrics.record_query(100,"TRC-1")
        d=o.dashboard()
        assert "INSUREQUERY" in d
    def test_health(self):
        o=ObservabilityLayer()
        h=o.health_check()
        assert h["status"]=="healthy"
    def test_stage_metrics(self):
        sm=StageMetrics("r",45.0,True)
        assert sm.name=="r"
        assert sm.duration_ms==45.0

class TestS5Events:
    def test_types(self):
        from runtime.engine.event_store import EventType
        for t in ["AGENT_ASSIGNED","CACHE_HIT","SYSTEM_RETRY","SYSTEM_DEGRADED"]:
            assert getattr(EventType,t)
    def test_factories(self):
        from runtime.engine.event_store import agent_assigned_event, cache_hit_event
        e1=agent_assigned_event("s",1,"p",{"q":"t"})
        assert e1.event_type.value=="AGENT_ASSIGNED"
        e2=cache_hit_event("s",1,"q","k")
        assert e2.event_type.value=="CACHE_HIT"

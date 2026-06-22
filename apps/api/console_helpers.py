"""Helpers to build Runtime Console payloads from engine state."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_trace_graph(
    events: List[Dict[str, Any]],
    execution_graph: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build nodes/edges for React Flow from event trace."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    for i, ev in enumerate(events):
        etype = ev.get("event_type", "UNKNOWN")
        seq = ev.get("sequence_number", i + 1)
        node_id = f"evt-{seq}"
        nodes.append({
            "id": node_id,
            "type": "event",
            "position": {"x": 80, "y": i * 72},
            "data": {
                "label": etype,
                "sequence": seq,
                "payload": ev.get("payload", {}),
                "timestamp": ev.get("timestamp", ""),
            },
        })
        if i > 0:
            prev_id = f"evt-{events[i - 1].get('sequence_number', i)}"
            edges.append({
                "id": f"e-{prev_id}-{node_id}",
                "source": prev_id,
                "target": node_id,
                "animated": True,
            })

    if execution_graph:
        base_y = len(events) * 72 + 40
        for j, step in enumerate(execution_graph):
            nid = f"agent-{j}"
            agent = step.get("agent", "step")
            nodes.append({
                "id": nid,
                "type": "agent",
                "position": {"x": 320, "y": base_y + j * 64},
                "data": {"label": agent, **step},
            })

    return {"events": events, "nodes": nodes, "edges": edges}


def extract_retrieval_from_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract retrieval weights from RETRIEVAL_EXECUTED / TUNING_APPLIED events."""
    weights = {"bm25_weight": 0.4, "vector_weight": 0.4, "ontology_weight": 0.2}
    topk: List[Dict[str, Any]] = []
    for ev in events:
        et = ev.get("event_type")
        payload = ev.get("payload", {})
        if et == "RETRIEVAL_EXECUTED":
            if payload.get("weights"):
                weights = {
                    "bm25_weight": payload["weights"].get("bm25_weight", weights["bm25_weight"]),
                    "vector_weight": payload["weights"].get("vector_weight", weights["vector_weight"]),
                    "ontology_weight": payload["weights"].get("ontology_boost", weights["ontology_weight"]),
                }
            if payload.get("chunks"):
                topk = list(payload["chunks"])
            elif payload.get("decision_trace"):
                topk = [
                    {
                        "chunk_id": d.get("chunk_id", ""),
                        "score": d.get("score", 0),
                        "feature_contribution": d.get("feature_contribution", {}),
                    }
                    for d in payload["decision_trace"]
                ]
        if et == "TUNING_APPLIED" and payload.get("weights"):
            w = payload["weights"]
            weights = {
                "bm25_weight": w.get("bm25_weight", weights["bm25_weight"]),
                "vector_weight": w.get("vector_weight", weights["vector_weight"]),
                "ontology_weight": w.get("ontology_weight", weights["ontology_weight"]),
            }
    return {"weights": weights, "topk": topk}


def extract_process_from_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract process execution from PROCESS_EXECUTED events."""
    state = ""
    transitions: List[Dict[str, Any]] = []
    process_name = ""
    for ev in events:
        if ev.get("event_type") == "PROCESS_EXECUTED":
            p = ev.get("payload", {})
            process_name = p.get("process_name", "")
            path = p.get("path", [])
            state = p.get("terminal_state", "")
            for i in range(len(path) - 1):
                transitions.append({
                    "from": path[i],
                    "to": path[i + 1],
                    "index": i,
                })
    return {
        "process_name": process_name,
        "state": state,
        "transitions": transitions,
    }


def extract_memory_from_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract memory snapshots from MEMORY_UPDATED events."""
    facts: Dict[str, Any] = {}
    active_process: Optional[str] = None
    reads: List[Dict[str, Any]] = []
    writes: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "MEMORY_UPDATED":
            continue
        p = ev.get("payload", {})
        action = p.get("action", "")
        snap = {"seq": ev.get("sequence_number"), "facts": p.get("facts", {})}
        if action == "read":
            reads.append(snap)
        elif action == "write":
            writes.append(snap)
            facts.update(p.get("facts", {}))
    return {
        "facts": facts,
        "active_process": active_process,
        "reads": reads,
        "writes": writes,
    }


def extract_tuner_history(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build tuner weight evolution from TUNING_APPLIED events."""
    history: List[Dict[str, Any]] = []
    for ev in events:
        if ev.get("event_type") != "TUNING_APPLIED":
            continue
        p = ev.get("payload", {})
        w = p.get("weights", {})
        history.append({
            "sequence": ev.get("sequence_number"),
            "timestamp": ev.get("timestamp", ""),
            "bm25_weight": w.get("bm25_weight", 0),
            "vector_weight": w.get("vector_weight", 0),
            "ontology_weight": w.get("ontology_weight", 0),
            "reason": p.get("reason", ""),
        })
    return history


def build_console_payload(
    query_result: Dict[str, Any],
    working_memory_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize engine query result into console-friendly shape."""
    events = query_result.get("event_trace", [])
    execution_graph = query_result.get("execution_graph", [])
    trace = build_trace_graph(events, execution_graph)

    retrieval = query_result.get("retrieval") or extract_retrieval_from_events(events)
    if isinstance(retrieval, dict):
        chunks = retrieval.get("chunks") or retrieval.get("topk") or []
        if chunks:
            retrieval = {**retrieval, "topk": chunks}

    process_data = query_result.get("process_result") or {}
    process = {
        "process_name": process_data.get("process_name", ""),
        "state": process_data.get("terminal_state", ""),
        "path": process_data.get("path", []),
        "transitions": process_data.get("decisions", []),
        "outcome": process_data.get("outcome", ""),
    }
    if not process["state"]:
        process.update(extract_process_from_events(events))

    wm = working_memory_ctx or query_result.get("working_memory") or {}
    memory = {
        "facts": {**extract_memory_from_events(events).get("facts", {}), **wm.get("facts", {})},
        "active_process": wm.get("active_process"),
        "last_products": wm.get("previous_products", query_result.get("memory_context", {}).get("previous_products", [])),
        "last_entities": wm.get("previous_entities", query_result.get("memory_context", {}).get("previous_entities", [])),
        "context": query_result.get("memory_context", {}),
        "memory_facts": query_result.get("memory_facts", {}),
        "reads": extract_memory_from_events(events).get("reads", []),
        "writes": extract_memory_from_events(events).get("writes", []),
    }

    tuner_stats = query_result.get("tuning", {})
    tuner = {
        "weights": {
            "bm25_weight": tuner_stats.get("bm25_weight", retrieval["weights"].get("bm25_weight", 0.4)),
            "vector_weight": tuner_stats.get("vector_weight", retrieval["weights"].get("vector_weight", 0.4)),
            "ontology_weight": tuner_stats.get("ontology_weight", retrieval["weights"].get("ontology_weight", 0.2)),
        },
        "history": extract_tuner_history(events),
        "stats": tuner_stats,
    }

    return {
        "session_id": query_result.get("session_id", ""),
        "trace_id": query_result.get("trace_id", ""),
        "query": query_result.get("query", ""),
        "resolved_query": query_result.get("resolved_query", ""),
        "answer": query_result.get("answer", {}),
        "evaluation": query_result.get("evaluation", {}),
        "execution_graph": execution_graph,
        "latency_ms": query_result.get("latency_ms", 0),
        "cached": query_result.get("cached", False),
        "trace": trace,
        "memory": memory,
        "retrieval": retrieval,
        "process": process,
        "tuner": tuner,
        "event_trace": events,
    }

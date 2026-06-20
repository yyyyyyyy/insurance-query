# InsureQuery — Developer Guide

> How to run, extend, and debug the Insurance Cognitive Decision Runtime.

---

## 1. Quick Start

### Prerequisites
- Python 3.11+
- pip

### Install
```bash
pip install -r requirements.txt
```

### Run API Server
```bash
python -m apps.api.main
# Server starts at http://localhost:8000
```

### Run Tests
```bash
pytest tests/ -q          # All 257 tests
pytest tests/test_tools.py -q  # Tool system only
pytest tests/test_knowledge.py -q  # Knowledge layer only
```

### Query via API
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "e生保的等待期是多少天？"}'
```

### View System Stats
```bash
curl http://localhost:8000/stats
curl http://localhost:8000/dashboard
```

---

## 2. Adding New Product Data

### Step 1: Add to product catalog
Edit `knowledge_pack/products/catalog.json`, add a new product entry:

```json
{
  "product_id": "P021",
  "name": "新产品的完整名称",
  "company": "承保公司全称",
  "category": "百万医疗险",
  "sub_category": "长期医疗",
  "guaranteed_renewal": "20年保证续保",
  "coverage": {
    "general_hospitalization": "年度400万",
    "critical_illness": "年度400万"
  },
  "deductible": "年度1万元",
  "waiting_period": "30天",
  "exclusions": ["既往症", "美容整形"],
  "premium_reference": {"age_30": 350, "age_40": 550},
  "max_age": 65,
  "min_age": 0,
  "source_url": "https://..."
}
```

### Step 2: Add to runtime product catalog (for tools)
Edit `runtime/tools/data.py`, append to `PRODUCT_CATALOG`:

```python
# Append to PRODUCT_CATALOG list
PRODUCT_CATALOG.append({
    "product_id": "P021",
    "name": "...",
    "product_type": "医疗险",
    "company": "...",
    # ... full structured attributes
})
```

### Step 3: Run tests to verify
```bash
pytest tests/test_tools.py::TestProductSearchTool -v
```

---

## 3. Adding New Regulations

Edit `knowledge_pack/regulations/catalog.json`:

```json
{
  "regulation_id": "REG031",
  "title": "新法规标题",
  "agency": "发文机构",
  "effective_date": "YYYY-MM-DD",
  "topics": ["主题1", "主题2"],
  "source_url": "https://..."
}
```

For runtime use, add relevant chunks to `runtime/tools/document_data.py` `DOCUMENT_STORE`.

---

## 4. Adding New Decision Rules

### Rule Structure Template
```json
{
  "rule_id": "UW-015",
  "domain": "underwriting",
  "description": "简明描述（一句话）",
  "if": {
    "conditions": [
      {"field": "field_name", "operator": "equals|gte|lte|in|contains", "value": "..."}
    ]
  },
  "then": {
    "decision": "standard_accept|reject|exclusion|extra_premium|approve|eligible|...",
    "action": "action_description"
  },
  "confidence": "HIGH|MEDIUM|LOW",
  "source": "insurance_product_clause|underwriting_manual|regulatory_document|claim_guideline",
  "source_ref": "DOCxxx or REGxxx",
  "ontology_mapping": {
    "entities": ["ENT-xxx", "ENT-yyy"],
    "relations": ["covers", "excludes", "applies_to"]
  },
  "process_mapping": {
    "process": "underwriting_lifecycle|claim_lifecycle|policy_lifecycle",
    "node": "state_id from process graph",
    "trigger_event": "E_xxx from process graph events"
  }
}
```

### Add to the right domain file
- `knowledge_pack/rules/underwriting_rules.json` — Health underwriting rules
- `knowledge_pack/rules/claim_rules.json` — Claim adjudication rules
- `knowledge_pack/rules/eligibility_rules.json` — Policy eligibility rules
- `knowledge_pack/rules/clause_rules.json` — Clause interpretation rules

### Regenerate Rules Graph
```bash
python3 -c "
import json
# Rebuild rules_graph.json by loading all 4 rule files
# (or re-run the graph generation script)
"
```

---

## 5. Extending Process Graphs

### Add a new state
Edit the process JSON (e.g., `knowledge_pack/process_models/claim/claim_process_graph.json`):

```json
// In "states" array:
{
  "id": "new_state_id",
  "label": "中文标签",
  "description": "状态含义"
}

// In "events" array:
{
  "id": "E_new_event",
  "label": "事件名称",
  "description": "触发条件"
}

// In "transitions" array:
{
  "from": "existing_state",
  "event": "E_new_event",
  "to": "new_state_id"
}
```

### Add a new decision node
```json
// In "decisions" array:
{
  "id": "D_new_decision",
  "node": "state_where_decision_occurs",
  "question": "决策问题？",
  "yes": "state_if_yes",
  "no": "state_if_no",
  "rule_based": true,
  "evidence_refs": ["REGxxx"],
  "evidence_type": "regulation"
}
```

### Verify consistency
```bash
python3 -c "
import json
with open('knowledge_pack/process_models/claim/claim_process_graph.json') as f:
    g = json.load(f)
# Check all transitions reference valid states
state_ids = {s['id'] for s in g['states']}
for t in g['transitions']:
    assert t['from'] in state_ids, f'Unknown from state: {t[\"from\"]}'
    assert t['to'] in state_ids, f'Unknown to state: {t[\"to\"]}'
print('All transitions valid')
"
```

---

## 6. Adding New Deterministic Functions

### Step 1: Define input/output schemas
```python
from pydantic import BaseModel, Field
from typing import Any, Dict, List

class MyToolInput(BaseModel):
    param1: str = Field(default="")
    param2: int = Field(default=10, ge=1, le=100)

class MyToolOutput(BaseModel):
    results: List[Dict[str, Any]] = Field(default_factory=list)
```

### Step 2: Implement the function
```python
from runtime.tools.base import BaseTool, ToolResult, ToolStatus
from runtime.evidence.contract import make_evidence, SourceType

class MyNewTool(BaseTool[MyToolInput, MyToolOutput]):
    @property
    def name(self) -> str: return "my_new_tool"
    @property
    def description(self) -> str: return "What this tool does"
    @property
    def input_schema(self): return MyToolInput
    @property
    def output_schema(self): return MyToolOutput

    def execute(self, input_data: MyToolInput) -> ToolResult:
        # Deterministic logic — same input always produces same output
        results = [...]  # your logic

        evidence = [
            make_evidence("DOC-REF", "CHUNK-REF", "evidence text",
                         SourceType.PRODUCT_CATALOG)
        ]
        return ToolResult(
            tool_name=self.name,
            status=ToolStatus.SUCCESS,
            data={"results": results},
            evidence=evidence,
        )
```

### Step 3: Register
In `runtime/tools/registry.py`, add to `create_default_registry()`:
```python
from runtime.tools.your_module import MyNewTool
# ...
registry.register(MyNewTool())
```

### Step 4: Add to plan templates (if applicable)
In `runtime/engine/planner.py`, add to `PLAN_TEMPLATES` for relevant intent types.

---

## 7. Debugging Event Replay

### Inspect a session's events
```python
from runtime.agents.orchestrator import MultiAgentEngine
engine = MultiAgentEngine()
r = engine.query("test query")
trace_id = r["trace_id"]

# View message log
for msg in engine.bus.message_log():
    print(f"{msg['sender']} → {msg['recipient']}: {msg['msg_type']}")

# View execution graph
for step in r["execution_graph"]:
    print(step)
```

### Replay state from events
```python
from runtime.engine.event_store import EventStore
from runtime.engine.reducer import replay_state

# Reconstruct state from event log
state = replay_state(engine.event_store, session_id)
print(f"Query: {state.query}")
print(f"Status: {state.status}")
print(f"Evidence: {len(state.evidence_graph.get('edges',[]))} edges")
```

### Check cache hits/misses
```python
print(engine.cache.stats())
# {"total_hits": 3, "total_misses": 5, "hit_rate": 0.375, "stores": {...}}
```

---

## 8. Running Evaluations

### Run a single query with evaluation
```python
r = engine.query("e生保的保障范围")
print(f"Score: {r['evaluation']['total_score']}")
print(f"Hallucination: {r['evaluation']['hallucination_score']}")
print(f"Diagnosis: {r['evaluation']['diagnosis']}")
```

### Run batch evaluation
```python
from evaluation.runner.runner import EvalRunner
from evaluation.datasets.samples import EVAL_DATASET

runner = EvalRunner(engine)
result = runner.run_batch(EVAL_DATASET, verbose=True)
print(f"Avg score: {result.avg_score}")
print(f"Passed: {result.passed}/{result.total_samples}")
```

### View evaluation dashboard
```bash
curl http://localhost:8000/dashboard
```

---

## 9. Common Pitfalls

### "async" is a Python keyword
The async execution module was renamed to `runtime/execution/`. All imports should use `runtime.execution.executor`.

### Tool parameter names
Plan templates in `planner.py` must use the exact Pydantic field names from the tool's `input_schema`. If a tool expects `document_type`, the plan must pass `"document_type"`, not `"doc_type"`.

### Evidence is mandatory
Every tool MUST return evidence via `make_evidence()`. Tests will fail otherwise (`test_all_successful_tools_have_evidence`).

### Deterministic execution
Same input must produce same output. Tools must not use random, time-dependent, or external-API-dependent logic without explicit versioning.

---

## 10. Testing

```bash
# All tests
pytest tests/ -q

# Specific layers
pytest tests/test_event_system.py -v  # Event sourcing
pytest tests/test_tools.py -v         # Tool contracts
pytest tests/test_knowledge.py -v     # Knowledge layer
pytest tests/test_evaluation.py -v    # Evaluation system
pytest tests/test_sprint5.py -v       # Multi-node + infra

# Single test
pytest tests/test_tools.py::TestToolContracts::test_all_tools_are_deterministic -v
```

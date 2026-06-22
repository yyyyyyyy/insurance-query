# 开发者指南

> 扩展产品、规则、工具与数据。决策语义见 [语义规范](specification.md)；启动与测试见 [运维与启动](operations.md)。

## 1. 扩展新产品

### knowledge_pack

编辑 `knowledge_pack/products/catalog.json`，添加完整产品条目（`product_id`、`coverage`、`deductible` 等）。

### 运行时目录

编辑 `runtime/tools/data.py`，向 `PRODUCT_CATALOG` 追加对应结构化记录（工具直接读取）。

### 验证

```bash
pytest tests/test_tools.py::TestProductSearchTool -v
```

---

## 2. 扩展法规与条款

- 元数据：`knowledge_pack/regulations/catalog.json`
- 全文检索：向 `runtime/tools/document_data.py` 的 `DOCUMENT_STORE` 添加分块文档

---

## 3. 扩展决策规则

按领域编辑：

- `knowledge_pack/rules/underwriting_rules.json`
- `knowledge_pack/rules/claim_rules.json`
- `knowledge_pack/rules/eligibility_rules.json`
- `knowledge_pack/rules/clause_rules.json`

规则经 `RuleEngine` 评估后作为 **rule candidates** 进入证据采纳门；matched 规则可强制 `accepted`。规则结构需含 `rule_id`、`if`/`then`、`source`、`source_ref`。

---

## 4. 扩展流程图

编辑 `knowledge_pack/process_models/{claim,underwriting,policy}/` 下 JSON：states、events、transitions、decisions。

运行时由 `ProcessRunner` 执行，产出 **process candidates**（见规范 §4）。

---

## 5. 新增确定性工具

1. 在 `runtime/tools/` 定义 `BaseTool` 子类（Pydantic input/output）
2. `execute()` 必须返回 `ToolResult` + `make_evidence()` 证据
3. 在 `runtime/tools/registry.py` 的 `create_default_registry()` 注册
4. 在 planner 模板中挂到对应 intent

**约束（I3）**：工具不得被 retrieval 跳过；证据进入 **candidate** 状态，由 Selector 采纳。

---

## 6. 数据灌入

### 结构化数据（Path A）

| 资产 | 位置 | 运行时 |
|------|------|--------|
| 产品目录 | `knowledge_pack/products/` | `runtime/tools/data.py` |
| 法规元数据 | `knowledge_pack/regulations/` | 元数据索引 |
| 规则 | `knowledge_pack/rules/` | `load_rules()` → RuleEngine |
| FAQ | `knowledge_pack/faq_dataset/` | 主要用于评测样本 |

### 文档灌入（Path B）

```
文档 → ingest_text_document / ingest_document
     → ChunkStore + Embedding
     → HybridRetriever (BM25 + Vector + Ontology)
```

首次 `MultiAgentEngine.query()` 时 `_ensure_knowledge()` 懒加载 `DOCUMENT_STORE` 并构建检索索引。

程序化灌入示例：

```python
from knowledge.ingestion.pipeline import ChunkStore, EmbeddingGenerator, ingest_document

store = ChunkStore()
gen = EmbeddingGenerator(vector_dim=256)
meta, chunks = ingest_document(
    file_path="path/to/clause.pdf",
    document_id="DOC008",
    title="产品条款",
    document_type="policy_clause",
    chunk_store=store,
    embedding_gen=gen,
)
```

### 双份维护注意

`knowledge_pack/` 为资产清单；`runtime/tools/` 为运行时实际读取源，扩展时 often 需同步两处。

---

## 7. 调试与事件重放

### 查看决策回合

```python
from runtime.agents.orchestrator import MultiAgentEngine

engine = MultiAgentEngine()
r = engine.query("重疾险保障范围")

# 真值：event_trace
for e in r["event_trace"]:
    print(e["sequence_number"], e["event_type"])

# 采纳门
sel = next(e for e in r["event_trace"] if e["event_type"] == "EVIDENCE_SELECTED")
print(sel["payload"]["accepted_ids"])
```

### Reducer 重放

```python
from runtime.engine.reducer import replay_state

state = replay_state(engine.event_store, r["session_id"])
print(state.accepted_evidence_ids)
print(state.cache_state)  # CACHE_HIT 元数据
```

### Runtime Console

启动见 [operations.md](operations.md)。Console 为投影层；审计以 `event_trace` 为准。

---

## 8. 评测

```python
r = engine.query("e生保的保障范围")
print(r["evaluation"]["total_score"], r["evaluation"]["diagnosis"])
```

批量：`evaluation.runner.runner.EvalRunner` + `EVAL_DATASET`。

Evaluation 基于 **event_store 重放**，非运行时临时对象。

---

## 9. 闭环回归

修改证据、事件、缓存或 Selector 后必须跑：

```bash
set LLM_ENABLED=false
pytest tests/test_closed_loop.py -q
pytest tests/ -q
```

---

## 10. 常见陷阱

| 问题 | 说明 |
|------|------|
| 证据缺失 | 工具必须 `make_evidence()` |
| 参数名不一致 | Plan 字段须与 tool `input_schema` 一致 |
| 非确定性 | 同输入必须同输出 |
| 绕过 Selector | 禁止将 retrieval chunk 直接写入 Answer |
| 合成 trace | Evaluation 必须读 event_store |

---

## 11. 测试分层

```bash
pytest tests/test_closed_loop.py -v   # S1–S8 闭环
pytest tests/test_event_system.py -v  # 事件溯源
pytest tests/test_tools.py -v         # 工具契约
pytest tests/test_knowledge.py -v     # 检索
pytest tests/test_evaluation.py -v    # 评测
pytest tests/test_v2_kernel.py -v     # 内核集成
```

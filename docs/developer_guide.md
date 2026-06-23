# 开发者指南

> 扩展产品、规则、工具与数据。决策语义见 [语义规范](specification.md)；启动与测试见 [运维与启动](operations.md)。

## 1. 扩展新产品

### knowledge_pack

编辑 `knowledge_pack/products/catalog.json`，添加完整产品条目（`product_id`、`coverage`、`deductible` 等）。

### 运行时加载

产品目录唯一入口：`knowledge_pack/products/catalog.json`。运行时通过 `runtime/tools/data_loader.load_product_catalog()` 加载，**无需**再编辑 `runtime/tools/data.py` 中的硬编码列表。

### 验证

```bash
pytest tests/test_tools.py::TestProductSearchTool -v
```

---

## 2. 文档数据（采集 + 导入）

文档检索数据**仅**来自 `ingest_documents.py` 的输出。完整流程见 [DATA.md](../knowledge_pack/DATA.md)。

```bash
# 可选：从保司官网 / 监管网站采集
python scripts/fetch_documents.py --init
python scripts/fetch_documents.py --all

# 必须：导入（支持手动放置的 PDF/TXT）
python scripts/ingest_documents.py --init
python scripts/ingest_documents.py --all
```

- 产品条款文件：`knowledge_pack/policy_documents/`
- 监管文件：`knowledge_pack/regulations/documents/`
- 运行时加载：`load_ingested_bundle()` / `load_ingested_documents()` → `ingested_documents.json`

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

## 6. 数据资产

### 结构化数据（产品 / 规则 / 评测）

| 资产 | 位置 | 运行时 |
|------|------|--------|
| 产品目录 | `knowledge_pack/products/` | `load_product_catalog()` |
| 法规元数据 | `knowledge_pack/regulations/catalog.json` | 元数据 |
| 规则 | `knowledge_pack/rules/` | `load_rules()` |
| FAQ | `knowledge_pack/faq_dataset/` | 评测样本 |

### 文档数据（条款 / 监管正文）

```
采集（可选）  fetch_documents.py  →  policy_documents/ / regulations/documents/
导入（必须）  ingest_documents.py →  chunks/ingested_documents.json
运行时        load_ingested_documents() → HybridRetriever
```

首次 `MultiAgentEngine.query()` 时 `_ensure_knowledge()` 加载 `ingested_documents.json` 并构建检索索引。

详见 [DATA.md](../knowledge_pack/DATA.md)。

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

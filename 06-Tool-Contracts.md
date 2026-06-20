# 06 - Tool Contract Document

# InsureQuery Runtime

Version 1.0

Status: Draft

---

# 1. Purpose

定义 InsureQuery 系统中所有 Agent 可调用工具的标准接口契约。

---

## Goals

### G1 Tool Is System Boundary

工具是 Runtime 与 Knowledge 的边界。

---

### G2 Deterministic Execution

工具必须：

* 输入确定
* 输出确定
* 不依赖 Prompt

---

### G3 Evidence-Centric

所有工具必须返回：

```text id="t3kq8a"
可追溯证据
```

---

### G4 No Hidden Logic

工具内部不得包含隐式推理。

---

# 2. Tool System Overview

```text id="v1q8z7"
Planner
   ↓
Tool Dispatcher
   ↓
Tools
   ↓
Evidence Layer
   ↓
Runtime State
```

---

# 3. Tool Categories

系统工具分为五类：

---

## 3.1 Retrieval Tools

负责知识检索

* ProductSearchTool
* DocumentSearchTool
* RegulationSearchTool

---

## 3.2 Extraction Tools

负责结构化信息抽取

* AttributeExtractionTool
* DiseaseDefinitionTool
* ClauseParserTool

---

## 3.3 Reasoning Tools

负责确定性计算

* CompareTool
* RuleEvaluationTool
* EligibilityCheckTool

---

## 3.4 Graph Tools

负责 Ontology 查询

* EntityLookupTool
* RelationTraversalTool

---

## 3.5 Utility Tools

* TextNormalizeTool
* SynonymMapTool

---

# 4. Tool Contract Standard

所有工具必须遵循统一结构：

---

## 4.1 Input Schema

```json id="q3xw8v"
{
  "tool_name": "",
  "version": "",
  "input": {}
}
```

---

## 4.2 Output Schema

```json id="r7p2mz"
{
  "status": "SUCCESS | ERROR | PARTIAL",

  "data": {},

  "evidence": [
    {
      "document_id": "",
      "chunk_id": "",
      "clause": "",
      "content": ""
    }
  ],

  "error": {
    "code": "",
    "message": ""
  }
}
```

---

## 4.3 Tool Principles

### P1 Deterministic Output

相同输入 → 相同输出

---

### P2 Evidence Mandatory

所有 output 必须绑定 evidence

---

### P3 No Free Text Reasoning

工具不能生成自然语言解释

---

### P4 Stateless Execution

工具不能依赖 session state

---

# 5. Core Tools Specification

---

# 5.1 ProductSearchTool

## Purpose

检索保险产品

---

## Input

```json id="x4m8zq"
{
  "query": "",
  "filters": {
    "product_type": "",
    "company": "",
    "constraints": {}
  }
}
```

---

## Output

```json id="k9d2xw"
{
  "products": [
    {
      "product_id": "",
      "name": "",
      "company": ""
    }
  ],

  "evidence": []
}
```

---

# 5.2 DocumentSearchTool

## Purpose

检索条款或监管文件

---

## Input

```json id="n6q1tp"
{
  "query": "",
  "document_type": "policy | regulation"
}
```

---

## Output

```json id="u3v9kf"
{
  "chunks": [],
  "evidence": []
}
```

---

# 5.3 RegulationSearchTool

## Purpose

专门检索监管规则

---

## Output 必须包含：

* 法规条文原文
* 文号
* 章节

---

# 5.4 CompareTool

## Purpose

结构化对比保险产品

---

## Input

```json id="c8x2mz"
{
  "products": ["A","B"],
  "dimensions": [
    "waiting_period",
    "deductible",
    "guaranteed_renewal"
  ]
}
```

---

## Output

```json id="f4p8qv"
{
  "comparison": [
    {
      "dimension": "waiting_period",
      "A": "",
      "B": ""
    }
  ],

  "evidence": []
}
```

---

## Rules

* 禁止 LLM 主观解释
* 只能结构化输出

---

# 5.5 AttributeExtractionTool

## Purpose

从条款中抽取结构化属性

---

## Example

```text id="a8k3pz"
等待期为90天
```

---

Output:

```json id="p7v3xq"
{
  "attribute": "waiting_period",
  "value": 90,
  "unit": "day"
}
```

---

# 5.6 ClauseParserTool

## Purpose

解析保险条款结构

---

输出：

```json id="b2q8mz"
{
  "clauses": [
    {
      "clause_no": "",
      "title": "",
      "content": ""
    }
  ]
}
```

---

# 5.7 EntityLookupTool

## Purpose

查询 Ontology Entity

---

Input:

```json id="z8m3qx"
{
  "entity_name": ""
}
```

---

Output:

```json id="t9v2kp"
{
  "entity_id": "",
  "type": "Disease | Coverage | Rule | Regulation | Product"
}
```

---

# 5.8 RelationTraversalTool

## Purpose

查询关系链

---

Example：

```text id="q1m8pz"
严重心肌炎 → defined_by → 监管规范
```

---

Output:

```json id="k3v9qx"
{
  "path": []
}
```

---

# 6. Tool Execution Rules

---

## R1 Tool Must Be Called Before Reasoning

禁止：

```text id="m8v3qz"
LLM直接回答
```

---

必须：

```text id="p4x8mz"
Tool → Evidence → Answer
```

---

## R2 Tool Output Is Ground Truth

禁止修改 tool output

---

## R3 Tools Are Composable

支持：

```text id="v9k3qz"
Search → Extract → Compare
```

---

# 7. Tool Failure Handling

---

## Case 1: No Result

```json id="n8q3vz"
{
  "status":"EMPTY"
}
```

---

## Case 2: Partial Result

```json id="k2x9mz"
{
  "status":"PARTIAL"
}
```

---

## Case 3: Error

```json id="p7v2qx"
{
  "status":"ERROR"
}
```

---

# 8. Tool Composition Patterns

---

## Pattern 1: Query → Retrieve

```text id="r8m3vz"
User Query
↓
Search Tool
↓
Answer
```

---

## Pattern 2: Query → Extract → Compare

```text id="x3v9qz"
Search
↓
Extraction
↓
Compare
```

---

## Pattern 3: Query → Ontology → Evidence

```text id="k9m3xz"
EntityLookup
↓
RelationTraversal
↓
Document Evidence
```

---

# 9. Tool vs LLM Boundary

---

## Tools负责：

* 事实
* 结构化数据
* 计算
* 检索

---

## LLM负责：

* 编排
* 语言生成
* 总结
* 表达

---

# 10. Critical Design Decision

## Decision 1

Tools must NOT reason

---

## Decision 2

LLM must NOT hallucinate facts

---

## Decision 3

Evidence is required for all outputs

---

# 11. System Evolution

V1

Simple tools

---

V2

Composable tool chains

---

V3

Auto tool selection

---

V4

Multi-agent tool orchestration

---

# Final Principle

工具不是能力增强器。

工具是：

```text id="o3q8mz"
系统事实执行层（Execution Layer）
```

Runtime 是：

```text id="k9x3vz"
决策层（Decision Layer）
```

LLM 是：

```text id="p8v2qz"
语言层（Language Layer）
```

三者严格分离，系统才可控。

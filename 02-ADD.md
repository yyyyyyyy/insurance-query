# Architecture Design Document

# InsureQuery Runtime

Insurance Knowledge Reasoning System

Version 1.0

---

# 1. Overview

## Goal

构建一个保险知识推理系统。

系统能够：

* 理解保险问题
* 检索条款
* 检索监管依据
* 对比产品责任
* 输出可追溯答案

系统不依赖大模型生成事实。

系统仅允许大模型组织语言。

---

# 2. Architecture Principles

## P1 Grounded First

所有事实必须来源于证据。

禁止模型编造。

---

## P2 Tool Before Reasoning

先调用工具。

后推理。

---

## P3 Structured Before Vector

优先结构化数据。

其次向量检索。

---

## P4 Runtime Centric

Runtime是系统核心。

模型只是Runtime中的组件。

---

# 3. High Level Architecture

```text
┌──────────────────────┐
│      Frontend        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      API Layer       │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Insurance Runtime    │
└──────────┬───────────┘
           │
 ┌─────────┼─────────┐
 ▼         ▼         ▼

Planner   State    Evaluator

 ▼
 Tool Dispatcher

 ▼

Tools

 ▼

Knowledge Layer
```

---

# 4. Runtime Design

Runtime负责：

* 理解问题
* 规划执行路径
* 调用工具
* 管理状态
* 生成答案

---

## Runtime Loop

```text
Input

↓

Plan

↓

Act

↓

Observe

↓

Evaluate

↓

Finish
```

---

## Runtime State

```json
{
  "session_id": "...",
  "query": "...",
  "intent": "...",
  "selected_products": [],
  "selected_regulations": [],
  "evidence": [],
  "tool_calls": [],
  "final_answer": null
}
```

---

State是唯一真相源。

任何阶段禁止直接修改回答。

只能修改State。

---

# 5. Planner

Planner负责制定执行计划。

---

## Input

用户问题

---

## Output

```json
{
  "intent": [
    "product_query",
    "regulation_query"
  ],
  "plan": [
    "search_product",
    "search_regulation",
    "generate_answer"
  ]
}
```

---

## Intent Types

```text
PRODUCT_QUERY

REGULATION_QUERY

COMPARE

DEFINITION

TRACE

FILTER
```

---

# 6. Tool Dispatcher

负责：

选择工具

执行工具

写入State

---

工具必须：

纯函数

无副作用

可测试

---

# 7. Tool Contracts

---

## ProductSearchTool

### Input

```json
{
  "query": "保证续保"
}
```

### Output

```json
{
  "documents": [],
  "chunks": []
}
```

---

## RegulationSearchTool

### Input

```json
{
  "query": "保证续保"
}
```

### Output

```json
{
  "regulations": []
}
```

---

## CompareTool

### Input

```json
{
  "products": [
    "A",
    "B"
  ],
  "dimension": "renewal"
}
```

### Output

```json
{
  "differences": []
}
```

---

## TraceTool

### Output

```json
{
  "document": "...",
  "page": 12,
  "clause": "3.2.1"
}
```

---

# 8. Knowledge Architecture

## Layer 1

Raw Documents

---

存储：

PDF

HTML

监管文件

---

## Layer 2

Chunk Layer

用于语义检索。

---

## Layer 3

Metadata Layer

结构化数据。

---

例如：

```json
{
  "company": "平安",
  "type": "医疗险",
  "waiting_period": 90
}
```

---

## Layer 4

Ontology Layer

领域知识层。

---

# 9. Insurance Ontology

核心资产。

---

## Product

保险产品

---

## Coverage

保障责任

---

## Disease

疾病定义

---

## Regulation

监管规则

---

## Rule

赔付规则

---

## Relationship

```text
Product

↓

Coverage

↓

Disease

↓

Rule

↓

Regulation
```

---

# 10. Structured Coverage Model

所有产品映射到统一Schema。

---

```json
{
  "product_id": "",
  "waiting_period": 90,
  "deductible": 10000,
  "renewal_years": 20,
  "social_security_required": true
}
```

---

Compare Tool直接比较Schema。

不依赖LLM。

---

# 11. Retrieval Strategy

采用三阶段检索。

---

## Phase 1

Metadata Filter

---

先缩小候选集。

---

## Phase 2

Vector Retrieval

---

向量召回。

---

## Phase 3

Rerank

---

重排序。

---

返回Top K。

---

# 12. Answer Generation

LLM禁止直接生成事实。

---

Prompt输入：

```json
{
  "question": "...",
  "evidence": [...],
  "comparison": [...],
  "regulations": [...]
}
```

---

模型职责：

组织语言。

生成解释。

---

禁止：

编造数字。

编造条款。

---

# 13. Evaluation Layer

所有回答必须经过评估。

---

## Citation Check

是否存在出处。

---

## Hallucination Check

回答内容是否超出证据。

---

## Completeness Check

是否回答所有问题。

---

# 14. Event Model

所有操作事件化。

---

## UserQueryEvent

```json
{
  "type": "user_query"
}
```

---

## ToolCallEvent

```json
{
  "type": "tool_call"
}
```

---

## EvidenceFoundEvent

```json
{
  "type": "evidence_found"
}
```

---

## AnswerGeneratedEvent

```json
{
  "type": "answer_generated"
}
```

---

# 15. Persistence

采用：

Event Sourcing

事件溯源

---

状态通过事件重建。

---

```text
Events

↓

Reducer

↓

State
```

---

State不直接持久化。

---

# 16. Future Evolution

V1

Insurance Runtime

---

V2

Knowledge Graph

---

V3

Multi-Agent Runtime

---

V4

Insurance Operating System

```

用户查询

↓

保险知识推理

↓

保险业务辅助

↓

产品设计辅助

↓

监管监测

```

---

最终目标：

将保险行业知识从静态文档升级为可执行知识系统（Executable Knowledge System）。

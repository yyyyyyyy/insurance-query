# Data Architecture Design Document

# InsureQuery Runtime

Version 1.0

Author: YaoChou

Status: Draft

---

# 1. Introduction

## 1.1 Purpose

本文档定义 InsureQuery Runtime 的数据架构设计。

目标：

构建保险知识推理系统的数据基础设施。

支持：

* 条款知识库
* 监管知识库
* 产品责任比较
* Insurance Ontology
* Runtime State
* Event Sourcing
* Evaluation

---

## 1.2 Design Goals

### G1 Knowledge First

知识优先。

系统核心资产是知识。

不是 Prompt。

不是模型。

---

### G2 Runtime First

Runtime 为系统中心。

数据库支持 Runtime 运行。

而不是单纯支持检索。

---

### G3 Structured First

优先结构化数据。

其次向量检索。

---

### G4 Explainability

所有回答必须可追溯。

必须能够定位原始条款。

---

# 2. High Level Architecture

```text
                ┌─────────────────┐
                │     Runtime     │
                └────────┬────────┘
                         │

      ┌──────────────────┼──────────────────┐

      ▼                  ▼                  ▼

Knowledge Layer    Runtime Layer     Evaluation Layer

      │                  │                  │

      ▼                  ▼                  ▼

Documents         Events            Eval Cases

Ontology          State             Scores

Metadata          Sessions          Feedback
```

---

# 3. Data Domains

系统划分为三个领域。

---

## Domain 1

Knowledge

知识域

---

负责：

保险知识管理。

包括：

* 条款
* 产品
* 监管文件
* Ontology

---

## Domain 2

Runtime

运行时域

---

负责：

Agent Runtime 状态管理。

包括：

* Session
* Event
* State

---

## Domain 3

Evaluation

评测域

---

负责：

系统质量管理。

包括：

* 测试集
* 回归测试
* 用户反馈

---

# 4. Knowledge Domain

---

## 4.1 Documents

原始事实来源。

### documents

一个 Document 可以是：

* 产品条款
* 监管文件
* 通知
* 指引

### Core Fields

```text
id

title

source_type

document_type

issuer

publish_date

effective_date

version
```

---

### Example

```text
平安e生保2026版

document_type=policy
```

---

```text
健康保险管理办法

document_type=regulation
```

---

## 4.2 Document Chunks

用于语义检索。

### document_chunks

每个 Document 被切分为多个 Chunk。

保存：

```text
页码

章节

内容

Embedding
```

---

Chunk 不参与业务逻辑。

仅参与检索。

---

# 5. Metadata Domain

## 5.1 Insurance Products

保险产品实体。

### insurance_products

```text
company_name

product_name

product_type

filing_number
```

---

## 5.2 Attribute Definitions

责任定义字典。

### attribute_definitions

例如：

```text
waiting_period

deductible

guaranteed_renewal

social_security_required
```

---

定义：

```text
编码

名称

类型

单位
```

---

## 5.3 Product Attributes

产品责任实例。

### product_attributes

采用 EAV 模型。

(Entity Attribute Value)

---

原因：

保险责任不断变化。

固定列模型无法扩展。

---

Example

```text
product_id = e生保

attribute = waiting_period

value = 90
```

---

```text
product_id = e生保

attribute = deductible

value = 10000
```

---

# 6. Insurance Ontology

## Purpose

构建保险知识图谱。

支持：

* 定义查询
* 监管映射
* 推理分析

---

## 6.1 Entities

### ontology_entities

支持：

```text
PRODUCT

COVERAGE

DISEASE

RULE

REGULATION
```

---

Examples

```text
e生保

严重心肌炎

保证续保

健康保险管理办法
```

---

## 6.2 Relations

### ontology_relations

描述实体之间关系。

---

Examples

```text
e生保

contains

保证续保
```

---

```text
严重心肌炎

defined_by

重大疾病定义规范
```

---

```text
保证续保

regulated_by

健康保险管理办法
```

---

# 7. Evidence Model

## Goal

保证回答可追溯。

---

### evidences

Evidence 是 Runtime 使用的最小事实单元。

保存：

```text
document

page

clause

content
```

---

Example

```text
Document

平安e生保

Clause

3.2.1

Content

保证续保期间为20年
```

---

# 8. Runtime Domain

## Design Principle

采用 Event Sourcing。

---

状态不是直接存储。

状态由事件重建。

---

## Event Flow

```text
Events

↓

Reducer

↓

Runtime State
```

---

# 8.1 Sessions

### sessions

表示一次会话。

---

## 8.2 Runtime Events

### runtime_events

系统核心表。

---

事件类型：

```text
USER_QUERY

PLAN_CREATED

TOOL_CALLED

EVIDENCE_FOUND

ANSWER_GENERATED
```

---

Example

```json
{
  "type":"TOOL_CALLED",
  "tool":"CompareTool"
}
```

---

## 8.3 Runtime State

逻辑概念。

不直接持久化。

---

由 Event Replay 重建。

---

Example

```json
{
  "query":"比较A和B",

  "intent":["COMPARE"],

  "selected_products":[
    "A",
    "B"
  ],

  "evidence":[]
}
```

---

## 8.4 Checkpoints

用于加速恢复。

---

### runtime_checkpoints

定期保存 State Snapshot。

---

# 9. Answer Model

## answers

保存最终回答。

---

## answer_evidences

保存：

回答

↓

证据

映射关系

---

实现：

```text
点击答案

↓

查看出处

↓

跳转条款
```

---

# 10. Evaluation Domain

## Purpose

建立持续评估体系。

---

## 10.1 Eval Cases

标准测试集。

---

Examples

```text
严重心肌炎定义是什么？
```

---

```text
比较A和B的等待期
```

---

## 10.2 Eval Runs

保存评测结果。

---

Metrics

```text
Accuracy

Citation Rate

Completeness

Latency
```

---

# 11. Runtime Query Flow

Example:

比较 e生保 和 好医保 的保证续保

---

Step 1

Planner

识别：

```text
COMPARE
```

---

Step 2

Runtime

调用：

```text
ProductSearchTool
```

---

Step 3

获取：

```text
Product Attributes
```

---

Step 4

调用：

```text
CompareTool
```

---

Step 5

获取：

```text
Evidence
```

---

Step 6

生成回答。

---

最终输出：

```text
Answer

+

Evidence

+

Regulation
```

---

# 12. Physical Storage

## PostgreSQL

负责：

```text
Metadata

Ontology

Runtime

Evaluation
```

---

## Vector Database

Qdrant

负责：

```text
Chunk Retrieval
```

---

## Object Storage

MinIO

负责：

```text
PDF

HTML

Raw Documents
```

---

# 13. Future Evolution

## V1

Document + Metadata

---

## V1.5

Structured Coverage Model

---

## V2

Insurance Ontology

---

## V3

Knowledge Graph

---

## V4

Multi-Agent Runtime

---

# 14. Key Architectural Decisions

## ADR-001

Runtime First

系统核心是 Runtime。

不是 LLM。

---

## ADR-002

Structured Before Vector

优先结构化责任模型。

其次向量检索。

---

## ADR-003

Ontology As Core Asset

保险领域本体是长期壁垒。

---

## ADR-004

Event Sourcing

Runtime 状态由事件重建。

---

## ADR-005

Evidence Required

所有回答必须提供出处。

---

# Final Vision

从：

Document Search System

演化为：

Insurance Knowledge Runtime

最终实现：

Executable Insurance Knowledge System

（可执行保险知识系统）

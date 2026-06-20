# 04 - Ontology Design Document

# Insurance Ontology Specification

InsureQuery Runtime

Version 1.0

Status: Draft

---

# 1. Introduction

## 1.1 Purpose

定义 InsureQuery Runtime 的领域知识模型（Ontology）。

本体（Ontology）用于统一描述保险领域中的核心概念及其关系。

为以下能力提供基础：

* 知识检索
* 条款解析
* 产品比较
* 监管关联
* Runtime 推理
* Knowledge Graph

---

## 1.2 Design Goals

### Goal 1

统一保险领域语言。

避免：

```text
严重心肌炎

疾病？

责任？

定义？

监管术语？
```

产生歧义。

---

### Goal 2

支持推理。

不仅能够搜索。

还能够回答：

```text
为什么赔？

为什么不赔？

监管依据是什么？
```

---

### Goal 3

支持结构化比较。

避免依赖 LLM 从文本中比较。

---

### Goal 4

支持未来知识图谱演进。

---

# 2. Ontology Principles

## P1

Document Is Not Knowledge

文档不是知识。

文档只是知识来源。

---

## P2

Entity First

先识别实体。

再关联文档。

---

## P3

Relationship Is Knowledge

关系比实体更重要。

---

例如：

```text
严重心肌炎
```

只是实体。

---

而：

```text
严重心肌炎

defined_by

重大疾病定义规范
```

才是知识。

---

## P4

Ontology Before Vector

优先使用领域关系。

其次使用向量检索。

---

# 3. Top Level Entity Model

系统定义五类核心实体。

```text
Product

Coverage

Disease

Rule

Regulation
```

---

# 4. Product

## Definition

保险产品。

面向消费者销售的保险合同。

---

## Examples

```text
平安e生保

蓝医保

尊享e生

好医保
```

---

## Attributes

```text
product_name

company_name

product_type

filing_number

effective_date
```

---

## Anti Examples

以下不属于 Product

```text
保证续保

严重心肌炎

健康保险管理办法
```

---

# 5. Coverage

## Definition

保险责任。

保险公司承诺承担的风险范围。

---

## Examples

```text
重大疾病责任

医疗责任

身故责任

轻症责任

豁免责任
```

---

## Attributes

```text
coverage_name

coverage_type

description
```

---

## Anti Examples

```text
严重心肌炎
```

属于 Disease。

不是 Coverage。

---

# 6. Disease

## Definition

疾病定义。

保险责任判定的医学对象。

---

## Examples

```text
恶性肿瘤

急性心肌梗死

严重心肌炎

脑中风后遗症
```

---

## Attributes

```text
disease_name

icd_code

definition_text
```

---

## Notes

Disease 是保险行业最重要实体之一。

未来需要维护统一定义。

---

# 7. Rule

## Definition

保险合同中的业务规则。

---

## Examples

```text
等待期

保证续保

赔付比例

免赔额

观察期

现金价值计算规则
```

---

## Attributes

```text
rule_name

rule_type

rule_value
```

---

## Notes

Rule 不属于 Coverage。

Rule 描述 Coverage 如何执行。

---

# 8. Regulation

## Definition

监管规则。

由监管机构发布。

---

## Examples

```text
健康保险管理办法

重大疾病保险定义规范

互联网保险业务监管办法
```

---

## Attributes

```text
title

issuer

publish_date

document_number
```

---

# 9. Relationship Model

关系是 Ontology 核心。

---

# 9.1 Product -> Coverage

## Relation

contains

---

Example

```text
好医保

contains

医疗责任
```

---

# 9.2 Coverage -> Disease

## Relation

covers

---

Example

```text
重大疾病责任

covers

严重心肌炎
```

---

# 9.3 Product -> Rule

## Relation

implements

---

Example

```text
e生保

implements

保证续保
```

---

# 9.4 Disease -> Regulation

## Relation

defined_by

---

Example

```text
严重心肌炎

defined_by

重大疾病保险定义规范
```

---

# 9.5 Rule -> Regulation

## Relation

regulated_by

---

Example

```text
保证续保

regulated_by

健康保险管理办法
```

---

# 9.6 Product -> Regulation

## Relation

complies_with

---

Example

```text
e生保

complies_with

健康保险管理办法
```

---

# 10. Relationship Matrix

```text
Product
 ├── contains ─────► Coverage
 ├── implements ───► Rule
 └── complies_with ► Regulation

Coverage
 └── covers ───────► Disease

Disease
 └── defined_by ───► Regulation

Rule
 └── regulated_by ─► Regulation
```

---

# 11. Ontology Graph Example

用户提问：

```text
严重心肌炎赔吗？
```

---

Runtime 不直接检索文档。

优先走 Ontology。

---

```text
严重心肌炎

↓

Disease

↓

defined_by

↓

重大疾病保险定义规范

↓

covers

↓

重大疾病责任

↓

contains

↓

具体产品
```

---

得到：

```text
疾病定义

↓

责任范围

↓

产品实现

↓

监管依据
```

---

# 12. Canonical Concepts

统一术语库。

避免同义词问题。

---

## Example

Canonical Concept

```text
保证续保
```

---

Aliases

```text
续保保证

长期续保

Guaranteed Renewal
```

---

系统内部统一映射：

```text
GUARANTEED_RENEWAL
```

---

# 13. Ontology IDs

每个实体拥有稳定ID。

---

Example

```text
PRODUCT_0001

平安e生保
```

---

```text
DISEASE_0032

严重心肌炎
```

---

```text
RULE_0010

保证续保
```

---

ID 永不复用。

---

# 14. Future Extensions

Version 2

增加：

```text
Insurance Company

Hospital

Drug
```

---

Version 3

增加：

```text
Claim

Underwriting Rule

Risk Factor
```

---

Version 4

扩展为完整 Insurance Knowledge Graph。

---

# 15. Architectural Decisions

## ADR-001

Disease 独立建模。

不嵌入 Coverage。

---

## ADR-002

Rule 独立建模。

不嵌入 Product。

---

## ADR-003

Regulation 为一级实体。

不是文档标签。

---

## ADR-004

Relationship 为核心资产。

实体只是节点。

---

## ADR-005

Ontology 优先于 Chunk Retrieval。

Runtime 优先查询 Ontology。

必要时再检索文档。

---

# Final Vision

从：

```text
Document
↓
Chunk
↓
Embedding
↓
Answer
```

演进为：

```text
Document
↓
Ontology
↓
Knowledge Graph
↓
Runtime Reasoning
↓
Answer
```

最终实现：

Executable Insurance Knowledge

（可执行保险知识系统）

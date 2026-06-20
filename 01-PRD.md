# InsureQuery Runtime

## 保险知识推理系统（Insurance Knowledge Reasoning System）

Version 2.0

---

# 1. 产品定位

## 产品名称

InsureQuery Runtime

---

## 产品定义

一个面向保险从业者的专业知识推理系统。

通过保险条款、监管文件、保险领域本体（Ontology）与确定性规则引擎，帮助用户完成：

* 条款查询
* 监管检索
* 产品比较
* 责任分析
* 定义溯源
* 合规验证

系统不提供投保建议。

系统提供的是：

保险知识推理能力。

---

## 核心理念

不是：

```text
Question
→ LLM
→ Answer
```

而是：

```text
Question

↓

Runtime Planner

↓

Knowledge Tools

↓

Evidence Collection

↓

Grounded Generation

↓

Answer
```

LLM负责组织语言。

事实由知识系统提供。

---

# 2. 产品愿景

成为保险行业的：

第二大脑（Second Brain）

与

知识操作系统（Knowledge OS）

帮助保险从业者在数秒内完成原本需要几十分钟甚至数小时的条款检索与监管分析工作。

---

# 3. 核心用户

## 一级用户

保险经纪人

保险代理人

保险产品经理

核保人员

核赔人员

---

## 二级用户

专业消费者

保险自媒体

保险培训机构

---

# 4. 核心价值

## Value 1

可信答案

所有结论必须附带出处。

---

## Value 2

产品与监管联动

回答产品问题时自动关联监管依据。

---

## Value 3

结构化比较

支持跨产品责任对比。

---

## Value 4

知识推理

不仅找到条款。

还要解释：

为什么这样设计。

是否符合监管要求。

---

# 5. 领域模型（Insurance Ontology）

系统核心资产。

---

## Product

保险产品

例如：

* 好医保
* e生保
* 蓝医保

---

## Coverage

保障责任

例如：

* 重疾责任
* 医疗责任
* 身故责任

---

## Disease

疾病定义

例如：

* 恶性肿瘤
* 心肌梗死
* 严重心肌炎

---

## Rule

赔付规则

例如：

* 等待期
* 赔付比例
* 保证续保

---

## Regulation

监管依据

例如：

* 健康保险管理办法
* 重大疾病定义规范

---

## Relationship

```text
产品

↓

保障责任

↓

疾病定义

↓

赔付规则

↓

监管依据
```

形成统一知识图谱。

---

# 6. 数据层设计

## Layer 1

原始文档层

Raw Documents

存储：

* PDF
* HTML
* 公告

---

## Layer 2

Chunk Layer

文档切片

用于向量检索。

---

## Layer 3

Metadata Layer

结构化元数据。

例如：

```json
{
  "company": "平安",
  "product_type": "医疗险",
  "waiting_period": 90,
  "guaranteed_renewal": 20
}
```

---

## Layer 4

Ontology Layer

领域知识层。

构建产品与监管关系。

---

# 7. Runtime 架构

## Runtime职责

负责：

理解问题

制定计划

调用工具

管理状态

生成答案

---

## Runtime流程

```text
User Query

↓

Intent Analysis

↓

Plan Generation

↓

Tool Selection

↓

Evidence Collection

↓

Verification

↓

Grounded Generation

↓

Answer
```

---

# 8. Tool System

## Tool 1

Product Search

产品检索

---

## Tool 2

Regulation Search

监管检索

---

## Tool 3

Ontology Search

本体查询

---

## Tool 4

Coverage Compare

责任对比

---

## Tool 5

Definition Resolver

定义解析

例如：

用户问：

严重心肌炎

Runtime自动：

疾病定义

↓

监管定义

↓

产品定义

↓

差异比较

---

## Tool 6

Evidence Resolver

出处定位

返回：

产品

条款号

页码

原文

---

# 9. MVP范围

坚持极度聚焦。

---

## 产品范围

仅支持：

医疗险

---

## 产品数量

5款

例如：

* 好医保
* e生保
* 蓝医保
* 长相安
* 尊享e生

---

## 监管文件

仅支持：

* 健康保险管理办法
* 互联网保险管理办法
* 医疗保险相关通知

---

## 支持能力

### Query

问答

### Regulation

监管查询

### Trace

出处溯源

### Compare

两款产品比较

---

不做：

用户系统

支付系统

高级筛选

报告导出

---

# 10. V1.5

增加：

## Structured Coverage Model

统一责任Schema。

例如：

```json
{
  "waiting_period": 90,
  "deductible": 10000,
  "renewal_years": 20,
  "social_security_required": true
}
```

---

所有产品映射到统一结构。

---

Runtime直接比较。

不依赖LLM推理。

---

# 11. V2.0

## Knowledge Graph

知识图谱

---

## Regulatory Monitoring

监管变更监测

---

## API开放平台

向保险CRM提供API。

---

## 企业版

保险公司

保险经代平台

保险培训机构

---

# 12. 成功指标

## Accuracy

引用准确率

≥99%

---

## Coverage

覆盖：

50+

主流产品

---

## Retrieval Recall

召回率

≥95%

---

## User Satisfaction

NPS

≥50

---

# 13. 技术架构

```text
Frontend

↓

API Layer

↓

Insurance Runtime

↓

Tool Layer

    Product Search
    Regulation Search
    Compare
    Ontology Search

↓

Knowledge Layer

    PostgreSQL
    Qdrant
    Ontology Store

↓

Document Layer

    PDF
    HTML
```

---

# 14. 产品壁垒

不是模型。

不是Prompt。

而是：

## Insurance Ontology

保险领域本体

---

## Structured Coverage Dataset

结构化责任数据集

---

## Regulation Mapping

监管映射关系

---

## Runtime

保险知识运行时

---

最终目标：

把保险知识从“文档”变成“可推理系统”。

让用户不是在搜索条款。

而是在询问一个能够理解保险规则的专业系统。

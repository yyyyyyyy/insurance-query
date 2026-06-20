# 05 - Runtime Specification

# InsureQuery Runtime

Version 1.0

Status: Draft

---

# 1. Purpose

定义 InsureQuery Runtime 的运行时行为。

Runtime 是系统核心。

负责：

* 理解问题
* 规划执行
* 调用工具
* 收集证据
* 生成答案
* 验证结果

---

# 2. Design Principles

## RP-001

LLM Is Not Runtime

LLM 不是 Runtime。

LLM 只是 Runtime 的一个组件。

---

## RP-002

State Is Source Of Truth

状态是唯一真相源。

---

## RP-003

Evidence Before Answer

先找到证据。

后生成答案。

---

## RP-004

Tools Before Reasoning

优先调用工具。

避免纯 Prompt 推理。

---

## RP-005

Every Answer Must Be Traceable

所有答案必须可追溯。

---

# 3. Runtime Architecture

```text
User Query
    │
    ▼
Intent Analyzer
    │
    ▼
Planner
    │
    ▼
Tool Dispatcher
    │
    ▼
Evidence Collector
    │
    ▼
Evaluator
    │
    ▼
Answer Generator
```

---

# 4. Runtime Lifecycle

Runtime 采用：

Plan → Act → Observe → Evaluate → Finish

模式。

---

## Step 1

Receive Query

---

用户输入：

```text
比较 e生保 和 好医保 的保证续保
```

生成：

```json
{
  "query":"比较 e生保 和 好医保 的保证续保"
}
```

---

## Step 2

Intent Analysis

识别用户意图。

---

输出：

```json
{
  "intent":[
    "COMPARE"
  ]
}
```

---

## Step 3

Planning

生成执行计划。

---

输出：

```json
{
  "steps":[
    "LocateProducts",
    "ExtractRenewalRule",
    "CompareRules",
    "FindRegulation",
    "GenerateAnswer"
  ]
}
```

---

## Step 4

Tool Execution

按计划执行工具。

---

## Step 5

Evidence Collection

收集所有证据。

---

## Step 6

Evaluation

检查结果是否满足要求。

---

## Step 7

Answer Generation

生成最终回答。

---

# 5. Runtime State

State 是 Runtime 核心对象。

---

## State Schema

```json
{
  "session_id":"",

  "query":"",

  "intent":[],

  "plan":[],

  "selected_products":[],

  "selected_regulations":[],

  "tool_calls":[],

  "evidence":[],

  "comparison":null,

  "final_answer":null,

  "status":"RUNNING"
}
```

---

# 6. Event Model

Runtime 基于 Event Sourcing。

---

## UserQueryEvent

```json
{
  "type":"USER_QUERY",
  "query":"..."
}
```

---

## IntentRecognizedEvent

```json
{
  "type":"INTENT_RECOGNIZED",
  "intent":[]
}
```

---

## PlanCreatedEvent

```json
{
  "type":"PLAN_CREATED",
  "plan":[]
}
```

---

## ToolCalledEvent

```json
{
  "type":"TOOL_CALLED",
  "tool":"CompareTool"
}
```

---

## EvidenceFoundEvent

```json
{
  "type":"EVIDENCE_FOUND",
  "evidence_id":"..."
}
```

---

## AnswerGeneratedEvent

```json
{
  "type":"ANSWER_GENERATED"
}
```

---

# 7. Reducer

Reducer 负责：

Event

↓

State

转换。

---

Example

```text
USER_QUERY

↓

state.query
```

---

```text
PLAN_CREATED

↓

state.plan
```

---

```text
EVIDENCE_FOUND

↓

state.evidence
```

---

# 8. Planner

Planner 是 Runtime 大脑。

---

## Responsibilities

### Intent Detection

识别用户目标。

---

### Tool Selection

决定调用哪些工具。

---

### Plan Generation

生成执行步骤。

---

# 9. Intent Types

系统定义：

---

## PRODUCT_QUERY

查询产品条款。

---

## REGULATION_QUERY

查询监管规则。

---

## COMPARE

比较产品。

---

## DEFINITION

查询定义。

---

## TRACE

定位出处。

---

## FILTER

筛选产品。

---

# 10. Planning Examples

---

用户：

```text
严重心肌炎是什么意思
```

---

Plan：

```json
[
  "FindDisease",
  "FindDefinition",
  "FindRegulation",
  "GenerateAnswer"
]
```

---

用户：

```text
比较A和B等待期
```

---

Plan：

```json
[
  "LocateProducts",
  "ExtractWaitingPeriod",
  "Compare",
  "GenerateAnswer"
]
```

---

# 11. Tool Dispatcher

负责：

执行工具。

---

输入：

```json
{
  "tool":"CompareTool"
}
```

---

输出：

```json
{
  "result":{}
}
```

---

Tool 不直接修改状态。

---

Tool 返回结果。

---

Reducer 更新状态。

---

# 12. Evidence Model

所有回答必须基于 Evidence。

---

Evidence Schema

```json
{
  "document":"",

  "page":1,

  "clause":"",

  "content":""
}
```

---

# 13. Evidence Requirements

最低要求：

---

PRODUCT_QUERY

至少 1 个 Evidence

---

COMPARE

每个产品至少 1 个 Evidence

---

REGULATION_QUERY

至少 1 个 Regulation Evidence

---

# 14. Reflection

Runtime 支持自检。

---

## Missing Evidence

如果证据不足：

```text
Evidence Count < Threshold
```

---

触发：

```text
Replan
```

---

Example

```text
检索不到监管文件

↓

再次检索

↓

扩大召回范围
```

---

# 15. Replanning

以下情况允许重新规划：

---

Tool Failure

---

Evidence Missing

---

Product Not Found

---

Ambiguous Question

---

# 16. Ambiguity Handling

Example

```text
心肌炎赔吗？
```

---

问题不完整。

---

Runtime：

```text
Disease = 心肌炎 ?

Product = Unknown
```

---

策略：

```text
Ask Clarification
```

---

而不是编造答案。

---

# 17. Termination Rules

Runtime 满足以下条件结束。

---

Condition 1

Plan Completed

---

Condition 2

Evidence Sufficient

---

Condition 3

Answer Generated

---

Condition 4

Evaluation Passed

---

# 18. Evaluation Gate

答案生成前必须检查。

---

## Citation Check

是否有出处。

---

## Completeness Check

是否回答问题。

---

## Consistency Check

答案是否与 Evidence 一致。

---

# 19. Failure Modes

---

## Product Not Found

返回：

```text
无法找到对应产品
```

---

## Regulation Not Found

返回：

```text
未找到相关监管依据
```

---

## Insufficient Evidence

返回：

```text
证据不足
```

---

禁止猜测。

---

# 20. Runtime Example

用户：

```text
比较 e生保 与 好医保 的保证续保
并说明监管依据
```

---

Intent

```json
["COMPARE","REGULATION_QUERY"]
```

---

Plan

```json
[
  "LocateProducts",
  "ExtractRenewalRule",
  "CompareRules",
  "FindRegulation",
  "GenerateAnswer"
]
```

---

Tool Calls

```text
ProductSearchTool

CompareTool

RegulationSearchTool
```

---

Evidence

```text
e生保条款

好医保条款

健康保险管理办法
```

---

Output

```text
比较结果

+

监管依据

+

出处
```

---

# 21. Future Evolution

V1

Single Runtime

---

V2

Runtime Memory

---

V3

Multi-Step Reflection

---

V4

Multi-Agent Runtime

```text
Planner Agent

Retriever Agent

Compare Agent

Compliance Agent
```

---

# Final Principle

Runtime 不负责知道事实。

Knowledge Layer 负责事实。

Runtime 负责：

```text
Plan

Act

Observe

Verify

Answer
```

最终目标：

构建一个可验证、可追溯、可演进的 Insurance Runtime。

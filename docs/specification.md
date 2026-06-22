# Closed-Loop Decision Runtime — 语义规范

> **文档类型**：形式化决策系统规范（v3.0）  
> **非目标**：模块手册、API 参考、实现指南

---

## 1. SYSTEM OVERVIEW

### 1.1 决策问题

在可审计约束下，将自然语言保险查询转化为 **有证据支撑的决策性回答**，并产出可重放因果记录。

每次有效决策须同时包含：

- **Answer** — 用户可见投影（非真值）
- **Accepted Evidence** — 经 Selector 采纳的依据
- **Event Trace** — `event_store` 中的 append-only 序列（唯一执行真值）

### 1.2 闭环定义

```
Decision → Events → Replay Evaluation → Tuner → Next Retrieval Ranking → Next Decision
```

闭环指反馈改变 **下一轮候选生成与采纳**，而非仅「模块均已执行」。

### 1.3 有效输出

| 条件 | 要求 |
|------|------|
| E1 | 存在单调递增的 append-only 事件序列 |
| E2 | 存在 `EVIDENCE_SELECTED`（含 `accepted_ids`） |
| E3 | `ANSWER_GENERATED` 仅引用 `accepted` 且 `used_in_answer=true` |
| E4 | Answer 不得作为 Evaluation / Replay 真值来源 |
| E5 | Cache 快捷路径须产生 `CACHE_HIT` + `source_trace_id` 及 replay 投影链 |

---

## 2. SYSTEM CONTRACT（不变量）

### I1 — Single Truth

执行真值 **仅** 存在于 `event_store`。运行时上下文、执行图、缓存、Console 均为投影。Evaluation 必须从事件序列重建，禁止合成 trace。

### I2 — Evidence Lifecycle

```
candidate → accepted | rejected → used_in_answer
```

Retrieval / Tool / Process / Rule 产出 **candidate**；**Evidence Selector** 为唯一决策门；Answer 只读 `accepted`。

### I3 — No Bypass

规划内 Tool **必须执行**。Retrieval 并行产生 candidate，不得替代 Tool 执行。

### I4 — Immutability

事件仅追加。Selection 结果固化为 `EVIDENCE_SELECTED`，不可在 Answer 生成后静默改写。

---

## 3. DECISION MODEL

```
Query
 → Memory Expansion
 → Retrieval (hybrid candidates + decision_trace)
 → Tool Execution (tool candidates)
 → Process / Rules (structured candidates)
 → Evidence Selector
 → Accepted Evidence
 → Answer (projection)
 → Event Store
 → Evaluation (replay)
 → Tuner
 → (next query) Retrieval ranking
```

| 阶段 | 产出类型 | 是否真值 |
|------|----------|----------|
| Candidate 生成 | `stage=candidate` | 否 |
| Evidence Selector | `accepted` / `rejected` | **决策点** |
| Answer | 自然语言 | 否（投影） |
| event_store | 事件序列 | **是** |

---

## 4. EVIDENCE SYSTEM

> **Evidence is a state machine, not a data container.**

### CanonicalEvidenceSet

单次查询的统一证据决策空间。成员含：`canonical_id`、`source`、`stage`、`relevance_score`、`used_in_answer`、`payload`、`provenance`。

### Source Types

| Source | 语义 |
|--------|------|
| `tool` | 工具执行片段 |
| `hybrid` | 检索排序 chunk（含 `feature_contribution`） |
| `process` | 流程状态机结论 |
| `rule` | 规则匹配判定 |
| `memory` | 会话上下文候选 |

### Selection Rules

1. 按 `relevance_score` 降序；低于 `evidence_threshold` → `rejected`
2. 容量上限 `max_accepted`
3. **强制采纳**：`rule` 且 matched；claim/uw intent 下 `process`
4. 结果写入 `EVIDENCE_SELECTED`

---

## 5. EVENT SYSTEM

> **Evaluation is event replay, not runtime inspection.**

### 决策关键事件

| 事件 | 语义 |
|------|------|
| `USER_QUERY` | 回合开始 |
| `MEMORY_UPDATED` | 记忆读/写 |
| `CACHE_MISS` / `CACHE_HIT` | 缓存路径（HIT 含 `source_trace_id`） |
| `RETRIEVAL_EXECUTED` | 检索 + `decision_trace` |
| `TOOL_EXECUTED` | 工具完成（I3 可审计） |
| `EVIDENCE_SELECTED` | **决策门** |
| `ANSWER_GENERATED` | Answer 投影 |
| `EVALUATION_COMPLETED` | 重放评分 |
| `TUNING_APPLIED` | 反馈调参 |
| `TRACE_CAPTURED` | 回合边界 |

### 顺序约束

`EVIDENCE_SELECTED` **必须先于** `ANSWER_GENERATED`。

### Cache Replay

`CACHE_HIT` 不重新执行 pipeline，但须追加完整 replay 投影事件链，并通过 `source_trace_id` 链接原始决策 trace。

---

## 6. EXECUTION LAYER（角色模型）

| 角色 | 职责 |
|------|------|
| Decision Coordinator | 编排回合；物化事件；守护 I1–I4 |
| Memory Resolver | 消解指代；扩展 `retrieval_query` |
| Retrieval Generator | hybrid candidates + `decision_trace` |
| Tool Executor | 执行全部计划工具 |
| Process / Rule Engines | 结构化 candidates |
| Evidence Selector | **唯一决策门** |
| Answer Projector | 只读 accepted |
| Evaluation Replayer | 从事件评分 |
| Tuner | 跨回合调整 retrieval 权重 |

**可观测层**（Console、execution_graph 摘要）不得作为 Evaluation 输入。

---

## 7. FAILURE MODES

| 模式 | 原因 | 闭环破坏 |
|------|------|----------|
| Cache Bypass | Hit 不写事件 | 本 session 不可证明 |
| Selector Weakening | Chunk 直进 Answer | 候选=采纳，反馈失真 |
| Tool Bypass | Skip execute | I3 违反 |
| Synthetic Trace | Evaluation 非 event_store | Tuner 错误信号 |
| Memory Decoupling | 未扩展 retrieval_query | Memory 仅润色 Answer |
| Retrieval–Answer Decoupling | Ranking 不进 accepted | Tuner 无效应 |
| Answer as Truth | 从 citations 反推 | 可证明性丧失 |

### 验证契约（S1–S8）

见 `tests/test_closed_loop.py`：hybrid 采纳、process/rule 进 Answer、event_store 评估、memory 影响 retrieval、tuner 因果链、tool 无 skip。

# 07 - Evaluation Design Document (EDD)

# InsureQuery Runtime Evaluation System

Version 1.0

Status: Draft (Industrial Grade)

---

# 1. Purpose

本评测体系用于统一评估 InsureQuery 系统的整体质量，包括：

* 模型选型（Model Selection）
* RAG 检索效果（Retrieval Quality）
* Tool 执行质量（Tool Reliability）
* Runtime 决策能力（Planning Quality）
* Ontology 一致性（Knowledge Consistency）

---

# 2. Core Philosophy

## P1 System-Level Evaluation

不评估“答案”。

评估：

```text id="m3k8q1"
系统行为链（System Behavior Chain）
```

---

## P2 No Single Metric

不存在单一准确率。

只有多维评分系统。

---

## P3 Evidence-Centric Evaluation

所有评分必须基于：

```text id="k9p2x7"
Evidence Trace
```

---

## P4 Replayable Evaluation

所有测试必须可回放：

```text id="r2x9k3"
Input → Runtime Trace → Output → Score
```

---

# 3. Evaluation Dimensions

系统评估拆为 5 大维度：

---

# 3.1 Retrieval Quality (RAG)

评估检索能力。

---

## Metrics

### Recall@K

```text id="v3k8p2"
是否召回正确条款
```

---

### Precision@K

```text id="m8q2x9"
是否召回无关内容
```

---

### MRR

```text id="q2k9x1"
正确证据排名
```

---

### Evidence Hit Rate

```text id="x9p3k7"
最终答案引用的证据是否正确
```

---

# 3.2 Tool Quality

评估工具执行能力。

---

## Metrics

### Tool Success Rate

```text id="k2x9q3"
工具调用成功率
```

---

### Tool Determinism

```text id="p8k3x1"
相同输入输出一致性
```

---

### Tool Coverage

```text id="x3k9p2"
是否选择正确工具
```

---

### Tool Efficiency

```text id="q9x3k8"
调用次数是否最优
```

---

# 3.3 Runtime Reasoning Quality

评估 Planner / Agent。

---

## Metrics

### Plan Correctness

```text id="m9k2x8"
计划是否正确
```

---

### Plan Efficiency

```text id="x2p8k3"
步骤是否冗余
```

---

### Replanning Rate

```text id="k8x3p9"
是否频繁重规划
```

---

### Intent Accuracy

```text id="p3k9x2"
意图识别准确率
```

---

# 3.4 Answer Quality

评估最终输出。

---

## Metrics

### Factual Accuracy

```text id="x8k2p9"
是否与证据一致
```

---

### Completeness

```text id="k3p9x8"
是否回答完整问题
```

---

### Groundedness

```text id="p9x2k8"
是否所有结论都有证据
```

---

### Hallucination Rate

```text id="x2k9p3"
是否生成未支持内容
```

---

# 3.5 System Efficiency

评估系统性能。

---

## Metrics

### Latency

```text id="k9p3x2"
响应时间
```

---

### Tool Calls per Query

```text id="x3p9k2"
工具调用数量
```

---

### Cost per Query

```text id="p2k9x3"
模型 + API 成本
```

---

# 4. Evaluation Dataset Design

---

# 4.1 Dataset Types

评测集分为三类：

---

## Type A: Product Questions

```text id="k3x9p1"
比较 e生保 和 好医保
```

---

## Type B: Regulation Questions

```text id="x9k3p2"
保证续保监管要求是什么
```

---

## Type C: Definition Questions

```text id="p3x9k2"
严重心肌炎定义
```

---

## Type D: Complex Multi-Hop

```text id="k9p2x3"
对比A和B，并说明监管依据
```

---

# 4.2 Gold Standard Structure

每条数据必须包含：

```json id="x8p3k9"
{
  "question": "",

  "expected_entities": [],

  "expected_evidence": [],

  "expected_intent": [],

  "rubric": {}
}
```

---

# 5. Rubric Scoring System

---

## Score Range

```text id="k2p9x3"
0 - 5
```

---

## 5.1 Factual Correctness

```text id="p9k3x2"
是否与证据一致
```

---

## 5.2 Evidence Alignment

```text id="x3k9p2"
是否正确引用条款
```

---

## 5.3 Reasoning Validity

```text id="k9x3p2"
推理是否合理
```

---

## 5.4 Completeness

```text id="p2k9x3"
是否完整回答
```

---

## Final Score

```text id="x9p2k3"
Score = weighted sum
```

---

# 6. Model Selection Framework

---

## 6.1 Evaluation Matrix

模型评估不是单维度。

---

```text id="k3p9x2"
Model
×
Retrieval System
×
Tool System
×
Runtime Strategy
```

---

## 6.2 Model Comparison Dimensions

### Accuracy

---

### Hallucination Rate

---

### Tool Following Ability

```text id="x9k3p2"
是否正确调用工具
```

---

### Long Context Stability

---

### Instruction Adherence

---

### Cost Efficiency

---

# 7. RAG Evaluation System

---

## 7.1 Chunk Quality

```text id="k2x9p3"
chunk 是否语义完整
```

---

## 7.2 Embedding Quality

```text id="x9p3k2"
相似性是否合理
```

---

## 7.3 Retrieval Robustness

```text id="p3k9x2"
query 改写后是否稳定
```

---

## 7.4 Noise Sensitivity

```text id="k9x2p3"
是否被无关chunk干扰
```

---

# 8. Tool Evaluation System

---

## 8.1 Tool Selection Accuracy

```text id="x3p9k2"
是否选对 tool
```

---

## 8.2 Tool Composition Efficiency

```text id="k9p2x3"
tool chain 是否最短路径
```

---

## 8.3 Tool Failure Recovery

```text id="p2x9k3"
失败后是否重试/重规划
```

---

## 8.4 Determinism Test

```text id="x9k2p3"
同输入是否一致输出
```

---

# 9. Runtime Trace Evaluation

---

系统必须记录：

```text id="k3x9p2"
USER → PLAN → TOOL → EVIDENCE → ANSWER
```

---

## 9.1 Trace Scoring

评估：

* 是否漏步骤
* 是否多余步骤
* 是否错误路径

---

## 9.2 Replay Testing

```text id="p9k2x3"
历史请求可重复执行
```

---

# 10. Hallucination Detection System

---

## 10.1 Evidence Gap Detection

```text id="x2p9k3"
Answer claims not in evidence
```

---

## 10.2 Unsupported Entity Detection

```text id="k9x3p2"
提到产品但无检索记录
```

---

## 10.3 Regulation Mismatch

```text id="p3k9x2"
监管引用错误
```

---

# 11. A/B Testing Framework

---

## 11.1 Model Comparison

```text id="x9p3k2"
GPT vs Qwen vs DeepSeek
```

---

## 11.2 Retrieval Comparison

```text id="k3p9x2"
BM25 vs Vector vs Hybrid
```

---

## 11.3 Tooling Comparison

```text id="p2k9x3"
Rule-based vs LLM-based tool selection
```

---

# 12. Production Monitoring Metrics

---

## 12.1 Live Metrics

* Avg latency
* Tool failure rate
* Hallucination proxy score

---

## 12.2 Business Metrics

* Answer usefulness score
* Expert rating
* Query resolution rate

---

# 13. Feedback Loop System

---

用户反馈进入：

```text id="x9k2p3"
Eval Dataset
```

---

错误案例自动变成：

```text id="k9p3x2"
Gold Test Case
```

---

形成闭环：

```text id="p3k9x2"
Production → Eval → Improvement → Production
```

---

# 14. System-Level Evaluation Architecture

```text id="x2k9p3"
             ┌──────────────┐
             │ Production    │
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ Runtime Trace │
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ Evaluation    │
             └──────┬───────┘
                    ▼
             ┌──────────────┐
             │ Model/RAG/Tune│
             └──────────────┘
```

---

# 15. Key Design Decisions

---

## D1

Evaluation is system-level, not model-level.

---

## D2

No answer is evaluated without evidence trace.

---

## D3

Runtime logs are first-class training data.

---

## D4

Evaluation dataset evolves from production failures.

---

## D5

Tool behavior is a first-class metric.

---

# Final Vision

从：

```text id="k9p3x2"
Model Evaluation System
```

升级为：

```text id="x3k9p2"
AI Runtime Evaluation OS
```

---

最终目标：

构建一个可以回答问题的系统，

同时也是一个可以自我优化的系统。

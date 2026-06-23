# InsureQuery — Closed-Loop Decision Runtime

> 事件溯源、证据驱动、闭环反馈的保险领域 **认知决策运行时**（v3.0）。

## 是什么

将保险自然语言查询转化为 **可审计的决策回合**：候选证据 → 采纳门 → 投影回答 → 事件固化 → 重放评估 → 调参反馈。

| 是 | 不是 |
|----|------|
| 认知决策运行时 | 聊天机器人 |
| 证据状态机 + 事件真值 | 纯 RAG 演示 |
| 可重放闭环系统 | 黑盒 LLM 应用 |

## 快速启动

```bash
pip install -r requirements.txt
python -m apps.api.main          # API :8000

cd apps/web && npm install && npm run dev   # Console :5173
```

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "e生保和好医保的免赔额分别是多少？"}'
```

详见 [运维与启动](docs/operations.md)。

## 文档

| 文档 | 说明 |
|------|------|
| [docs/README.md](docs/README.md) | **文档索引** |
| [语义规范](docs/specification.md) | 决策语义、不变量、证据与事件真值（主规范） |
| [架构参考](docs/architecture.md) | 分层与决策流概览 |
| [开发者指南](docs/developer_guide.md) | 扩展产品、规则、工具、数据 |
| [Runtime Console](apps/web/README.md) | 调试台 |

## 核心不变量

- **I1** — `event_store` 为唯一执行真值
- **I2** — 证据：`candidate → accepted → used_in_answer`
- **I3** — Tool 必须执行，Retrieval 不替代执行
- **I4** — 事件 append-only
- **并发** — 同 session 串行；EventStore 单 turn 事务原子提交

## 测试

```bash
set LLM_ENABLED=false
pytest tests/ -q
```

基线 331+ passed，含 `tests/test_closed_loop.py` 闭环门禁。

## 仓库结构（摘要）

```
apps/api/          API 入口
apps/web/          Runtime Console（可观测层）
runtime/           决策运行时（orchestrator、evidence、agents、process）
knowledge/         检索、本体、灌入
evaluation/        重放评测与 Tuner
infra/             缓存、DB、可观测性
knowledge_pack/    领域资产（产品、规则、流程）
docs/              规范与指南
tests/             回归与闭环测试
```

## 版本

- **Kernel** v3.0 — CanonicalEvidence + Selector + event_store 评估真值
- **Console** v1.0 — Trace / Memory / Retrieval / Process / Tuner UI

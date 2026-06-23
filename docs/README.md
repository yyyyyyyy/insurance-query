# InsureQuery 文档索引

> **Insurance Closed-Loop Decision Runtime** — 事件溯源、证据驱动、闭环反馈的保险领域决策运行时。

## 阅读顺序

| 文档 | 受众 | 内容 |
|------|------|------|
| [语义规范](specification.md) | 架构师、审计、内核开发者 | **主文档**：决策语义、不变量、证据状态机、事件真值模型 |
| [架构参考](architecture.md) | 全体开发者 | 分层能力概览与决策流（不含实现细节） |
| [运维与启动](operations.md) | 运维、联调 | 后端 / Console 启动、API、测试门禁 |
| [开发者指南](developer_guide.md) | 业务扩展 | 扩展产品、规则、数据灌入 |

## 其他资料

| 文档 | 说明 |
|------|------|
| [根目录 README](../README.md) | 项目入口与能力摘要 |
| [Runtime Console](../apps/web/README.md) | 前端调试台 |
| [Knowledge Pack 数据流程](../knowledge_pack/DATA.md) | 采集与导入（唯一入口） |

## 文档原则

1. **决策语义优先** — 规范描述「系统如何决策」，不以文件目录为主结构。
2. **真值在 event_store** — 运行时投影、缓存、UI 均非执行真值。
3. **证据是状态机** — `candidate → accepted → used_in_answer`，Answer 仅为投影。

## 版本

- **Runtime Kernel**：v3.0（闭环认知运行时）
- **Console**：v1.0（可观测层，非决策真值）

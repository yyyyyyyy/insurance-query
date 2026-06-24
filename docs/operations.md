# 运维与启动

## 环境要求

- Python 3.11+
- Node.js 18+（仅 Console）
- `pip install -r requirements.txt`

## 后端 API

```bash
python -m apps.api.main
# http://localhost:8000
```

### 常用端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/query` | 执行决策回合，返回 Console payload |
| GET | `/trace/{session_id}` | 按 session 重放 |
| GET | `/sessions/{session_id}` | Session 详情 + 事件 |
| GET | `/health` | 健康检查 |
| GET | `/stats` | 运行时统计（需 `DEBUG_ENDPOINTS=1`） |
| GET | `/dashboard` | 可观测性仪表盘（需 `DEBUG_ENDPOINTS=1`） |

### 示例

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "e生保的等待期是多少天？"}'
```

## Runtime Console（前端）

```bash
cd apps/web
npm install
npm run dev
# http://localhost:5173  →  /api 代理到 :8000
```

Console 展示 event trace、证据采纳、检索权重等 **投影**；执行真值以 `event_store` 为准。

## 测试

```bash
# 全量（建议 LLM 关闭以保证确定性）
set LLM_ENABLED=false   # Windows
pytest tests/ -q

# 闭环门禁
pytest tests/test_closed_loop.py -q
```

当前基线：**342 passed**（`LLM_ENABLED=false`，含 S1–S8 闭环用例）。

## 环境变量

| 变量 | 说明 |
|------|------|
| `LLM_ENABLED` | `false` 强制规则/模板模式（测试推荐） |
| `DEBUG_ENDPOINTS` | `1` 启用 `/stats`、`/dashboard`、`/events` 调试端点 |
| `DEEPSEEK_API_KEY` | 可选，启用 LLM 意图与回答 |
| `USE_CANONICAL_EVIDENCE` | 默认 `1`；`0` 仅紧急回退旧证据路径 |

## 持久化

- 事件：`data/events.db`（若使用 SqliteEventStore）
- 会话记忆：`data/sessions.db`
- Tuner：`data/tuning.json`

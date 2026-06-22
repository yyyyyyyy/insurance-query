# Insurance Runtime Console

AI Runtime Debugging Console for Insurance Runtime Kernel v2.

## Prerequisites

- Backend running at `http://localhost:8000`
- Node.js 18+

## Development

```bash
cd apps/web
npm install
npm run dev
```

Open http://localhost:5173

API requests are proxied to `http://localhost:8000` via `/api`.

## Pages

| Path | Purpose |
|------|---------|
| `/` | Query Workspace — execute queries, view execution graph + timeline |
| `/trace/:sessionId` | Full event trace replay |
| `/memory/:sessionId` | Memory facts + diff |
| `/retrieval/:sessionId` | Retrieval weights + top-k |
| `/process/:sessionId` | Process state machine (React Flow) |
| `/tuner/:sessionId` | SelfTuner weight evolution |

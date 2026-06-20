# InsureQuery AI Runtime Kernel

> **An Insurance Cognitive Decision Runtime — not a chatbot, not a RAG demo.**

---

## What Is This?

InsureQuery is a **domain-specific cognitive runtime system** for insurance reasoning. It processes insurance queries through a structured pipeline of events, state transitions, deterministic functions, and rule evaluations — producing evidence-backed, traceable decisions.

### What It Is NOT

| NOT | Because |
|---|---|
| ❌ Chatbot | No free-form dialogue; every output is structured and rule-grounded |
| ❌ RAG System | Retrieval is one tool among many, not the system architecture |
| ❌ LLM Application | LLM is intentionally absent — the system is a runtime, not a prompt chain |
| ❌ Agent Framework | No autonomous reasoning; decisions are deterministic and rule-based |

### What It IS

| IS | Role |
|---|---|
| ✅ Cognitive Runtime | Event → State → Decision → Evidence → Trace |
| ✅ Decision System | 45 structured rules across 4 domains, all with legal/contract sources |
| ✅ Process Engine | 3 executable state machines (Claim, Underwriting, Policy) |
| ✅ Knowledge System | Product catalog, regulation library, ontology graph, FAQ dataset |
| ✅ Self-Evaluating | 5-dimension scoring, hallucination detection, feedback loop |

---

## System Architecture (6 Layers)

```
┌──────────────────────────────────────────────────────┐
│  Layer 6: EVALUATION                                  │
│  Scoring(5-dim) + Hallucination Detector + Feedback   │
├──────────────────────────────────────────────────────┤
│  Layer 5: RUNTIME                                     │
│  Multi-Node Engine + Event Store + Reducer + Executor │
├──────────────────────────────────────────────────────┤
│  Layer 4: DECISION                                    │
│  45 Rules (UW/Claim/Eligibility/Clause) + Graph      │
├──────────────────────────────────────────────────────┤
│  Layer 3: PROCESS                                     │
│  3 Process State Machines (Claim/UW/Policy Lifecycle) │
├──────────────────────────────────────────────────────┤
│  Layer 2: ONTOLOGY                                    │
│  22 Entities + 26 Relations (NetworkX Graph)          │
├──────────────────────────────────────────────────────┤
│  Layer 1: KNOWLEDGE                                   │
│  20 Products + 30 Regulations + 983 FAQs + Chunks     │
└──────────────────────────────────────────────────────┘
```

---

## Data Flow

```
User Query
  │
  ▼
Intent Router ──→ Intent + Plan
  │
  ▼
Ontology Expansion ──→ Related Entities
  │
  ▼
Hybrid Retrieval ──→ Ranked Evidence Chunks
  │
  ▼
Deterministic Functions (9 tools) ──→ Structured Output + Evidence
  │
  ▼
Rule Engine (45 rules) ──→ Decision (approve/reject/exclude/...)
  │
  ▼
Answer Composition ──→ Evidence-backed Decision
  │
  ▼
Evaluation ──→ Score + Hallucination Report + Feedback
  │
  ▼
Trace Capture ──→ Immutable Execution Record
```

---

## Data Ingestion (数据灌入)

Knowledge enters the system through **two parallel paths**: structured data (direct tool lookup) and unstructured documents (chunk → embed → retrieve). There is no single ETL job — ingestion is layered and mostly lazy-loaded at first query.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA SOURCES                                                    │
├──────────────────────┬──────────────────────────────────────────┤
│  Structured (JSON)   │  Unstructured (Documents)                │
│  ─────────────────   │  ─────────────────────────               │
│  knowledge_pack/     │  runtime/tools/document_data.py          │
│    products/         │  PDF / TXT / MD files                    │
│    regulations/      │                                          │
│    rules/            │                                          │
│    faq_dataset/      │                                          │
├──────────────────────┴──────────────────────────────────────────┤
│  RUNTIME EMBEDDED DATA (tools read directly)                      │
│    runtime/tools/data.py          → PRODUCT_CATALOG (4 products)│
│    runtime/tools/document_data.py → DOCUMENT_STORE (6 documents)  │
└─────────────────────────────────────────────────────────────────┘
         │                                    │
         │ direct lookup                      │ ingest pipeline
         ▼                                    ▼
   product_search / compare          Extract → Chunk → Embed → Store
   regulation_search (metadata)              │
   document_search (keyword)                ▼
                                    ChunkStore + EvidenceIndex
                                            │
                                            ▼
                                    HybridRetriever (BM25 + Vector + Ontology)
```

### Path A: Structured Data (no chunking)

Field-level JSON / Python dicts queried directly by deterministic tools. **Does not** go through the ingestion pipeline.

| Asset | Location | Runtime usage |
|---|---|---|
| Product catalog (20) | `knowledge_pack/products/catalog.json` | Tools read `runtime/tools/data.py` (`PRODUCT_CATALOG`, 4 products in runtime) |
| Regulation catalog (30) | `knowledge_pack/regulations/catalog.json` | Metadata index; full-text retrieval uses `DOCUMENT_STORE` |
| FAQ dataset (983) | `knowledge_pack/faq_dataset/faqs.json` | Evaluation only — **not indexed for retrieval** |
| Decision rules (45) | `knowledge_pack/rules/*.json` | Rule definitions — not auto-loaded into runtime pipeline |
| Process models (3) | `knowledge_pack/process_models/` | State machine graphs |

> **Note:** `knowledge_pack/` is the full asset inventory; `runtime/tools/` is what the running system actually reads. Adding data often requires updating **both** (see Developer Guide).

### Path B: Document Ingestion Pipeline

Implemented in `knowledge/ingestion/pipeline.py`:

```
Raw Document (PDF / Text)
  → Text Extractor        extract_text_from_file()
  → Clause-aware Chunker  chunk_document()  — splits by 第X条 / 第X章, with overlap
  → Embedding Generator   EmbeddingGenerator — TF-IDF (char n-gram), hash fallback
  → Chunk Store           ChunkStore — in-memory index, optional JSON persist
```

**Design rule:** every chunk must be traceable to `document_id` + `clause` (source document and article number).

Two public entry points:

| Function | Input | Use case |
|---|---|---|
| `ingest_document(file_path, ...)` | PDF / TXT / MD file on disk | Batch or scripted ingestion |
| `ingest_text_document(text, ...)` | In-memory string | Runtime bootstrap from `DOCUMENT_STORE` |

ChunkStore supports `save(path)` / `load(path)` for JSON persistence, but the default runtime path keeps everything **in memory** and rebuilds on restart.

### Runtime Bootstrap (lazy load)

On the **first query**, `MultiAgentEngine._ensure_knowledge()`:

1. Reads pre-chunked documents from `runtime/tools/document_data.py` (`DOCUMENT_STORE`, 6 docs)
2. Re-assembles chunk text and runs `ingest_text_document()` (re-chunk + embed)
3. Indexes each chunk in `EvidenceIndex` (chunk ↔ evidence mapping)
4. Builds `HybridRetriever` (BM25 40% + vector 40% + ontology boost 20%)
5. Wires retriever into `RetrievalAgent`

`KnowledgeEngine.load_knowledge()` follows the same flow.

### Ingested vs. knowledge_pack Coverage

| Asset | In knowledge_pack | Loaded at runtime |
|---|---|---|
| 20 products | ✅ `catalog.json` | ⚠️ 4 in `data.py` (tool direct lookup) |
| 6 clause documents | partial | ✅ `document_data.py` → ingestion pipeline |
| 30 regulations | ✅ metadata | ⚠️ 3 full-text docs in `DOCUMENT_STORE` |
| 983 FAQs | ✅ | ❌ not indexed |
| 45 rules | ✅ | ❌ not auto-wired to runtime |

### Adding New Data

**New product**

1. Add entry to `knowledge_pack/products/catalog.json`
2. Add matching structured record to `runtime/tools/data.py` → `PRODUCT_CATALOG`

**New regulation / clause document**

1. Add pre-chunked content to `runtime/tools/document_data.py` → `DOCUMENT_STORE`
2. Or call `ingest_document()` programmatically for a PDF/TXT file

**New PDF file (programmatic)**

```python
from knowledge.ingestion.pipeline import ChunkStore, EmbeddingGenerator, ingest_document

store = ChunkStore()
gen = EmbeddingGenerator(vector_dim=256)
meta, chunks = ingest_document(
    file_path="path/to/clause.pdf",
    document_id="DOC008",
    title="产品条款标题",
    document_type="policy_clause",  # policy_clause | regulation | claim_procedure
    chunk_store=store,
    embedding_gen=gen,
    product_id="P001",
)
store.save("data/chunk_store.json")  # optional persist
```

**New decision rule / process**

Edit `knowledge_pack/rules/*.json` or `knowledge_pack/process_models/` — see [Developer Guide](docs/developer_guide.md).

### Current Limitations

- **In-memory only** — restart clears ChunkStore; no SQLite / vector DB yet
- **TF-IDF embeddings** — deterministic but weaker than sentence-transformers for semantic search
- **Dual maintenance** — `knowledge_pack/` and `runtime/tools/` must be kept in sync manually
- **No batch CLI** — no `python -m ingest --all`; ingestion is code-driven or lazy at startup
- **Ontology not auto-extracted** — `knowledge/ontology/builder.py` is hand-authored, not derived from ingested docs
- **FAQ & most regulations** — stored as assets but not fully indexed for retrieval

---

## Core Capabilities

| Capability | Layer | Description |
|---|---|---|
| **Product Comparison** | Knowledge + Decision | Compare multiple insurance products across dimensions (deductible, coverage, premium, renewal) |
| **Claim Adjudication** | Process + Decision + Rule | Walk through claim lifecycle; determine approve/reject/partial based on coverage, exclusion, waiting period |
| **Underwriting Decision** | Process + Rule | Evaluate health declaration → risk assessment → standard/extra-premium/exclusion/reject |
| **Clause Interpretation** | Rule + Knowledge | Map clause text to covered/not-covered decisions with legal source |
| **Regulation Lookup** | Knowledge + Ontology | Retrieve applicable regulations with article-level citation |
| **Rule-Based Inference** | Decision + Process | Chain multiple rules through process state machines to reach structured decisions |

---

## System State

### Completed ✅

| Module | Status | Detail |
|---|---|---|
| Event Store | ✅ | 22 event types, append-only immutable log |
| State Reducer | ✅ | Pure function, deterministic replay |
| Async Executor | ✅ | Parallel + timeout + retry |
| Runtime Nodes (5) | ✅ | IntentRouter, Retrieval, DeterministicFunction, Evaluation, Supervisor |
| Tool System (9) | ✅ | All with Pydantic input/output schemas |
| Knowledge Pack | ✅ | 20 products, 30 regulations, 983 FAQs |
| Ontology Graph | ✅ | 22 entities, 26 relations (NetworkX) |
| Process Models (3) | ✅ | Claim(16S/5D), UW(15S/4D), Policy(17S/4D) |
| Decision Rules (45) | ✅ | 4 domains, 13 decision types |
| Evaluation Engine | ✅ | 5-dimension scoring + hallucination detection |
| Feedback Loop | ✅ | 5 signal types |
| Tracing | ✅ | Immutable QueryTrace |
| Observability | ✅ | Structured logs + Metrics + Dashboard |
| Caching | ✅ | 4-tier trace-aware cache |
| API | ✅ | FastAPI: POST /query, GET /stats, GET /dashboard |
| LLM Plugin | ✅ | DeepSeek intent + answer composition with rule-based fallback |
| Tests | ✅ | 257 passing |

### Partially Complete ⚠️

| Module | Gap |
|---|---|
| Ontology → Process → Rule Integration | Layers exist independently; linking is manual |
| Working Memory | Single-query sessions; no multi-turn intermediate state reuse |
| Rule Execution Engine | Rules defined but not yet auto-loaded into the runtime pipeline |
| Self-Tuning | Feedback signals generated but not automatically applied |

### Missing ❌

| Module | Reason |
|---|---|
| Durable Event Store (SQLite/Postgres) | In-memory only; restart loses all state |
| OpenTelemetry Span Export | Metrics collected but not exported to OTLP |
| Rate Limiting / Circuit Breaker | Production hardening not done |
| Docker / CI/CD | Deployment not containerized |

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure DeepSeek LLM (optional — falls back to rules without API key)
cp .env.example .env
# Edit .env and set DEEPSEEK_API_KEY=your_key

# Run API server
python -m apps.api.main

# Run tests
pytest tests/ -q

# Query via API
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "e生保和好医保的免赔额分别是多少？"}'

# View dashboard
curl http://localhost:8000/dashboard
```

### LLM Configuration (DeepSeek)

Copy `.env.example` to `.env` and set your API key:

| Variable | Default | Description |
|---|---|---|
| `DEEPSEEK_API_KEY` | — | DeepSeek API key (required to enable LLM) |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base URL |
| `DEEPSEEK_MODEL` | `deepseek-chat` | Model name |
| `LLM_ENABLED` | auto | Set `false` to force rule-based mode |
| `LLM_INTENT_ENABLED` | `true` | LLM intent classification |
| `LLM_ANSWER_ENABLED` | `true` | LLM answer composition |

Without API key, the system uses rule-based intent + template answers (existing behavior).

Check LLM status: `curl http://localhost:8000/health`

---

## Documentation

- **[System Architecture](docs/system_architecture.md)** — 6-layer architecture deep dive
- **[Developer Guide](docs/developer_guide.md)** — How to extend the system (products, regulations, rules)
- **[System Map](docs/system_map.md)** — Visual map of all components and data flows
- **[Knowledge Pack Report](knowledge_pack/knowledge_pack_report.md)** — Knowledge asset inventory
- **Data Ingestion** — see [Data Ingestion (数据灌入)](#data-ingestion-数据灌入) above; pipeline code in `knowledge/ingestion/pipeline.py`

---

## Project Structure

```
insure-query/
├── apps/api/              # FastAPI entry point
├── runtime/
│   ├── engine/            # Event Store, Reducer, State, Intent Router
│   ├── llm/               # DeepSeek plugin (intent + answer, rule fallback)
│   ├── agents/            # Runtime Node bus + 5 nodes + orchestrator
│   ├── execution/         # Async executor (parallel + timeout + retry)
│   ├── tools/             # 9 deterministic functions with schemas
│   └── evidence/          # Evidence contract model
├── knowledge/
│   ├── ingestion/         # Document pipeline (PDF → Chunk → Embed)
│   ├── ontology/          # NetworkX graph + builder
│   ├── evidence/          # Evidence index (chunk ↔ entity)
│   ├── retrieval/         # Hybrid retriever (BM25 + vector + ontology)
│   └── engine.py          # Knowledge-aware runtime engine
├── evaluation/
│   ├── trace/             # Immutable query trace capture
│   ├── engine/            # 5-dimension scoring engine
│   ├── hallucination/     # Hallucination detector (3 violation types)
│   ├── feedback/          # System improvement signal loop
│   ├── datasets/          # 14 evaluation samples
│   └── runner/            # Batch evaluation runner
├── infra/
│   ├── cache/             # 4-tier trace-aware cache
│   └── observability/     # Logging + metrics + dashboard
├── knowledge_pack/
│   ├── products/          # 20 products (structured JSON)
│   ├── regulations/       # 30 regulations
│   ├── faq_dataset/       # 983 FAQ questions
│   ├── process_models/    # 3 executable process graphs
│   └── rules/             # 45 decision rules + graph
├── docs/                  # System documentation
└── tests/                 # 257 tests across 10 files
```

---

## Key Design Decisions

1. **Event Sourcing over Mutable State** — Every state change is an immutable event; state is reconstructed by a pure-function reducer. This enables deterministic replay and full auditability.

2. **Deterministic Functions over LLM Reasoning** — All tool executions are deterministic: same input → same output. No LLM is used inside any function.

3. **Rule-Based over Probabilistic** — All decisions are rule-grounded with explicit legal/contract source references. Confidence levels (HIGH/MEDIUM/LOW) are declared, not inferred.

4. **Cognitive Runtime over Agent Framework** — The system is a state machine runtime, not an autonomous agent. The "agent" in the codebase should be understood as "runtime node" — a component in a deterministic pipeline.

5. **Layer Separation** — Knowledge, Ontology, Process, Decision, Runtime, and Evaluation are distinct layers. Each can be upgraded independently.

---

## License & Contact

InsureQuery AI Runtime Kernel — Built for insurance reasoning research and production deployment.

Version: 1.0.0 (Sprint 1-5 complete)

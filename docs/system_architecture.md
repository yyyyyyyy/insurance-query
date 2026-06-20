# InsureQuery — System Architecture

> **Version**: 1.0.0
> **Type**: Insurance Cognitive Decision Runtime
> **Status**: Six-layer architecture, production-ready core

---

## 1. Architecture Overview

InsureQuery is organized into six layers, each with a distinct responsibility and interface contract.

```
┌─────────────────────────────────────────────────────────────┐
│                  EVALUATION LAYER                            │
│  5-Dim Scoring · Hallucination Detection · Feedback Loop    │
├─────────────────────────────────────────────────────────────┤
│                    RUNTIME LAYER                             │
│  Runtime Nodes · Event Store · Reducer · Async Executor     │
├─────────────────────────────────────────────────────────────┤
│                   DECISION LAYER                             │
│  45 Rules (UW/Claim/Eligibility/Clause) · Rules Graph       │
├─────────────────────────────────────────────────────────────┤
│                   PROCESS LAYER                              │
│  Claim Lifecycle · Underwriting Lifecycle · Policy Lifecycle│
├─────────────────────────────────────────────────────────────┤
│                   ONTOLOGY LAYER                             │
│  22 Entities · 26 Relations · NetworkX Graph                │
├─────────────────────────────────────────────────────────────┤
│                  KNOWLEDGE LAYER                             │
│  Products(20) · Regulations(30) · FAQs(983) · Chunks(23)    │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Layer 1: Knowledge Layer

### Responsibility
Raw facts, documents, and structured data about the insurance domain. Acts as the foundational data substrate.

### Input
- Insurance product brochures and terms (PDF/Text)
- Regulatory documents (from government sources)
- FAQ data (from community platforms)
- Chunked document text with embeddings

### Output
- Product catalog (20 products with structured attributes)
- Regulation library (30 regulations with topics and article references)
- FAQ dataset (983 questions across 7 task types)
- Chunk store with TF-IDF embeddings (23 chunks from 6 documents)

### Key Components
| Component | File | Description |
|---|---|---|
| Document Ingestion Pipeline | `knowledge/ingestion/pipeline.py` | PDF→Text→Chunk→Embed→Store |
| Product Catalog | `knowledge_pack/products/catalog.json` | 20 products with coverage/exclusions/premium |
| Regulation Library | `knowledge_pack/regulations/catalog.json` | 30 regulations with source URLs |
| FAQ Dataset | `knowledge_pack/faq_dataset/faqs.json` | 983 user questions from community platforms |
| Chunk Store | `knowledge/ingestion/pipeline.py` → `ChunkStore` | In-memory chunk index with JSON persistence |

### Dependencies
- Sinks into Ontology Layer for entity extraction
- Sinks into Retrieval Engine for search

### Current Limitations
- Only 6 full-text documents ingested (need 100+ for production)
- Embeddings use TF-IDF (lower accuracy than modern sentence-transformers)
- No PDF parser for binary PDFs (PyPDF2 optional)
- FAQ data stored but not yet ingested into evidence index

---

## 3. Layer 2: Ontology Layer

### Responsibility
Formal domain model connecting insurance entities (Product, Disease, Coverage, Regulation, Rule) through typed relationships.

### Input
- Product catalog entities
- Disease definitions
- Regulation references
- Coverage types

### Output
- 22 typed entities across 5 categories
- 26 directed relationships across 7 relation types
- Deterministic graph traversal (NetworkX)

### Key Components
| Component | File | Description |
|---|---|---|
| OntologyGraph | `knowledge/ontology/graph.py` | NetworkX-backed directed graph |
| Ontology Builder | `knowledge/ontology/builder.py` | Populates graph from product catalog |
| Entity Types | `EntityType` enum | Product, Coverage, Disease, Rule, Regulation, Clause, Exclusion |
| Relation Types | `RelationType` enum | contains, covers, defines, implements, regulated_by, excludes, references |

### Entity Inventory (22)
| Type | Count | Examples |
|---|---|---|
| Product | 4 | e生保, 好医保, 平安福, 微医保 |
| Coverage | 6 | 住院医疗保险金, 重疾保险金, 门诊手术, 轻症, 身故, 保证续保 |
| Disease | 5 | 恶性肿瘤, 急性心梗, 脑中风后遗症, 冠脉搭桥, 糖尿病 |
| Regulation | 3 | 健康保险管理办法, 重疾定义规范, 保险法 |
| Rule | 4 | 等待期, 免赔额, 犹豫期, 如实告知 |

### Core Operations
- `lookup(name, entity_type)` — Find entities by name or alias
- `get_outgoing(entity_id)` — Get all downstream relations
- `expand_context(seed_entities)` — Discover related entities up to N hops
- `find_paths(source, target)` — All paths between two entities

### Dependencies
- Populated from Knowledge Layer (product catalog)
- Queried by Process Layer for entity context
- Queried by Decision Layer for rule condition matching

### Current Limitations
- No InsuranceCompany entity type (products reference companies as text strings)
- No ClaimCondition entity type
- Disease inventory limited to 5 (real coverage is 100+ diseases)
- Missing: age_range, occupation_category as typed entities

---

## 4. Layer 3: Process Layer

### Responsibility
Executable state machines modeling real insurance business processes (Claim, Underwriting, Policy Lifecycle). Each process defines states, events, transitions, and decision nodes.

### Input
- Trigger events (e.g., "保险事故发生", "提交投保申请")
- Current state
- Decision parameters

### Output
- Next state
- Decision outcome (approve/reject/exclude/etc.)
- Evidence references

### Process Inventory

| Process | States | Events | Transitions | Decisions | File |
|---|---|---|---|---|---|
| **Claim Lifecycle** | 16 | 19 | 20 | 5 | `process_models/claim/` |
| **Underwriting Lifecycle** | 15 | 17 | 20 | 4 | `process_models/underwriting/` |
| **Policy Lifecycle** | 17 | 21 | 25 | 4 | `process_models/policy/` |

### Decision Nodes (13 total)

| Decision | Process | Question | Outcomes |
|---|---|---|---|
| D_coverage | Claim | 事故是否在保障期间内？ | yes→liability_check / no→reject |
| D_liability | Claim | 事故是否属于保险责任？ | yes→exclusion_check / no→reject |
| D_exclusion | Claim | 是否属于免责条款？ | yes→reject / no→document_collection |
| D_docs | Claim | 材料是否齐全？ | yes→review / no→need_supplement |
| D_evaluate | Claim | 是否符合赔付条件？ | yes→approve / no→reject |
| D_honesty | Underwriting | 健康告知是否真实？ | yes→risk_assessment / no→decline |
| D_risk | Underwriting | 标准体还是次标准体？ | standard→accept / substandard→premium/exclusion/decline |
| D_premium | Underwriting | 接受加费条件？ | yes→accept / no→exclusion_eval |
| D_exclusion_uw | Underwriting | 接受除外责任条件？ | yes→accept / no→decline |
| D_cooling | Policy | 犹豫期内是否退保？ | yes→surrender / no→waiting_period |
| D_waiting | Policy | 事故是否在等待期内（非意外）？ | yes→不赔付 / no→赔付 |
| D_renewal | Policy | 是否为保证续保产品？ | yes→auto_renew / no→assess |
| D_grace | Policy | 宽限期内是否补缴？ | yes→active / no→lapsed |

### Cross-Process Links
- Policy Lifecycle references Underwriting Lifecycle as a sub-process at the `underwriting` state
- Claim Lifecycle depends on Policy Lifecycle's `active` state for coverage period verification

### Dependencies
- Queries Ontology Layer for entity context
- Feeds Decision Layer for rule evaluation triggers
- Consumed by Runtime Layer as execution plans

### Current Limitations
- Claim: appeal→arbitration→litigation sub-flow not modeled
- Underwriting: health questionnaire library and smart underwriting rules not integrated
- Policy: policy loan, beneficiary change, endorsement change not modeled
- Decision nodes are structurally defined but not yet linked to runtime tool dispatch

---

## 5. Layer 4: Decision Layer

### Responsibility
Structured, source-grounded decision rules that evaluate conditions and produce deterministic outcomes.

### Input
- Condition parameters (disease, age, occupation, coverage_type, etc.)
- Process state context
- Ontology entity bindings

### Output
- Decision outcome (13 unique types)
- Action instruction
- Source reference (clause/manual/regulation/guideline)
- Ontology and process mappings

### Rule Inventory (45 total)

| Domain | Rules | Decision Types |
|---|---|---|
| **Underwriting (UW)** | 14 | reject, standard_accept, exclusion, extra_premium |
| **Claim (CL)** | 13 | approve, reject, partial_approve, request_more_docs |
| **Eligibility (EL)** | 10 | eligible, not_eligible, conditional_eligible |
| **Clause (CI)** | 8 | covered, not_covered, partially_covered |

### Rule Structure
```json
{
  "rule_id": "UW-003",
  "domain": "underwriting",
  "if": {
    "conditions": [
      {"field": "disease", "operator": "equals", "value": "恶性肿瘤"},
      {"field": "tnm_stage", "operator": "gte", "value": "II"}
    ]
  },
  "then": {
    "decision": "reject",
    "action": "permanent_decline"
  },
  "confidence": "HIGH",
  "source": "underwriting_manual",
  "source_ref": "UW_MANUAL-MALIGNANCY-01",
  "ontology_mapping": {
    "entities": ["ENT-D001", "ENT-P001"],
    "relations": ["covers"]
  },
  "process_mapping": {
    "process": "underwriting_lifecycle",
    "node": "risk_assessment",
    "trigger_event": "E_assess_risk"
  }
}
```

### Source Distribution
| Source | Count | Examples |
|---|---|---|
| insurance_product_clause | 22 | PRODUCT_CATALOG-covered_diseases, DOC001-C007 |
| underwriting_manual | 11 | UW_MANUAL-MALIGNANCY-01 |
| regulatory_document | 9 | REG003-第十六条, REG001-第二十三条 |
| claim_guideline | 3 | REG012-理赔服务 |

### Confidence Distribution
| Level | Count | Meaning |
|---|---|---|
| HIGH | 36 (80%) | Clear legal/contractual basis; no ambiguity |
| MEDIUM | 8 (18%) | Depends on product-specific terms or insurer discretion |
| LOW | 1 (2%) | Guideline-level; significant insurer discretion |

### Rules Graph
- 204 nodes (rule + condition + decision + ontology + process)
- 330 edges (condition_of, decides, depends_on_entity, triggers_in_process)

### Dependencies
- Binds to Ontology Layer entities
- Triggers on Process Layer state transitions
- Consumed by Runtime Layer for decision execution

### Current Limitations
- Rules defined but not auto-loaded into runtime pipeline
- No payout calculation rules (amount computation)
- No multi-disease joint risk assessment rules
- No product comparison rules (rules operate on single product only)

---

## 6. Layer 5: Runtime Layer

### Responsibility
The core execution engine. Manages event sourcing, state reconstruction, asynchronous function dispatch, and inter-node coordination.

### Key Components

#### 6.1 Event Store
- 22 event types covering 5 sprints (core, knowledge, evaluation, production)
- Append-only immutable log
- Session-indexed for per-query trace replay
- Pure-Python in-memory storage

#### 6.2 State Reducer
- Pure function: `reduce(session_id, events[]) → RuntimeState`
- 20+ event handler functions
- Deterministic replay — same events always produce same state
- State machine lifecycle: `created → planning → executing → answering → completed`

#### 6.3 Runtime Nodes (5)
| Node | Role | Key Output |
|---|---|---|
| IntentRouter (planner) | Classifies intent, generates execution plan | Intent + Plan steps |
| Retrieval (retrieval) | Hybrid retrieval (BM25+vector+ontology) | Ranked evidence chunks |
| DeterministicFunction (tool) | Executes tool chains via async executor | Tool results + evidence |
| Evaluation (evaluation) | 5-dim quality scoring + hallucination detection | Score + diagnosis + feedback |
| Supervisor (supervisor) | Health monitoring, failure recovery | System health report |

**Note**: These are "runtime nodes" in a deterministic pipeline, not autonomous "agents". The node bus (`AgentBus`) is a message router, not an agent discovery/scheduling system.

#### 6.4 Async Executor
- ThreadPoolExecutor with configurable workers (default: 4)
- Per-function timeout (default: 10s)
- Automatic retry (max_retries: 2, delay: 0.5s)
- Fallback/degraded execution mode

#### 6.5 Tool System (9 Deterministic Functions)
| Category | Function | Schema |
|---|---|---|
| Retrieval | product_search | ProductSearchInput/Output |
| Retrieval | document_search | DocumentSearchInput/Output |
| Retrieval | regulation_search | RegulationSearchInput/Output |
| Extraction | attribute_extraction | AttributeExtractionInput/Output |
| Extraction | clause_parser | ClauseParserInput/Output |
| Reasoning | compare | CompareInput/Output |
| Reasoning | eligibility_check | EligibilityCheckInput/Output |
| Graph | entity_lookup | EntityLookupInput/Output |
| Graph | relation_traversal | RelationTraversalInput/Output |

### Runtime State Model (RuntimeState)
```
RuntimeState:
  # Core (Sprint 1-2)
  session_id, query, intent, plan, tool_results, answer, status, error
  
  # Knowledge (Sprint 3)
  ontology_context, retrieved_chunks, evidence_graph, retrieval_path
  
  # Evaluation (Sprint 4)
  trace_id, evaluation_result, hallucination_report, diagnosis, feedback_signals
  
  # Production (Sprint 5)
  agent_execution_graph, cache_state, system_health, failure_recovery_path
```

### Dependencies
- Dispatches to Process Layer for execution plans
- Dispatches to Decision Layer for rule evaluation
- Receives from Evaluation Layer for post-answer scoring
- Uses Infrastructure layer (cache, observability)

### Current Limitations
- Event Store is in-memory (no durable persistence)
- Runtime Nodes use a fixed pipeline, not dynamic scheduling
- No working memory across queries within a session

---

## 7. Layer 6: Evaluation Layer

### Responsibility
Post-answer quality assessment, error detection, and system improvement signal generation.

### Key Components

#### 7.1 Trace Capture
- Immutable `QueryTrace` per query session
- Records: intent, ontology expansion, retrieval results, plan steps, tool calls, evidence, answer, events
- Unique `trace_id` for every query

#### 7.2 Evaluation Engine (5 Dimensions)
| Dimension | Weight | What It Measures |
|---|---|---|
| retrieval | 25% | evidence_count, ontology_hit_rate, result_count |
| tool | 15% | tool_call_count, tool_diversity, chain validity |
| reasoning | 20% | plan_length, ontology_entities_used |
| answer | 30% | groundedness (evidence_linkage), citations, completeness |
| efficiency | 10% | latency_ms, tool_call_count |

#### 7.3 Hallucination Detector (3 Violation Types)
| Violation | Detection Method |
|---|---|
| unsupported_claim | Answer entities not found in evidence |
| missing_evidence | Zero evidence items or no citations |
| ontology_mismatch | Evidence graph nodes don't overlap with ontology expansion |

#### 7.4 Feedback Loop (5 Signal Types)
| Signal | Affected Module |
|---|---|
| retrieval_quality | knowledge.retrieval.engine |
| tool_routing | runtime.engine.planner |
| evidence_quality | knowledge.engine |
| ontology_coverage | knowledge.ontology.builder |
| planner_quality | runtime.engine.engine |

### Evaluation Dataset
- 14 evaluation samples across 5 categories:
  - product_comparison (3), coverage (3), regulation (3), multi_hop (3), hallucination (2)
- Each sample has expected_intent, expected_evidence, expected_ontology_path

### Dependencies
- Receives output from Runtime Layer
- Produces feedback signals for system improvement
- Records results in Trace for observability

---

## 8. Infrastructure

### 8.1 Cache Layer
- 4-tier trace-aware cache: query, retrieval, tool, evaluation
- TTL-based expiry
- Hit/miss tracking per store
- Cache key generation by content hash

### 8.2 Observability
- Structured logging (Python logging)
- SystemMetrics aggregation (6 metric dimensions)
- Text-based dashboard
- Pipeline stage tracking with latency

### 8.3 API Layer
- FastAPI service
- Endpoints: POST /query, GET /stats, GET /dashboard, GET /health, GET /sessions/{id}
- Pydantic request/response validation

---

## 9. System Boundaries

### What the System IS
- A **cognitive runtime** — executes event-sourced state transitions through a deterministic pipeline
- A **decision engine** — evaluates 45 structured rules against insurance knowledge
- A **process executor** — walks users through real insurance business processes
- A **self-evaluating system** — scores its own outputs and generates improvement signals

### What the System is NOT
- **NOT an LLM application** — No prompt engineering, no function calling, no LLM reasoning
- **NOT a RAG system** — Retrieval is one tool, not the architecture
- **NOT a chatbot** — No conversational memory, no free-form dialogue
- **NOT an agent framework** — Nodes are deterministic, not autonomous
- **NOT a LangGraph/CrewAI/AutoGen alternative** — Different paradigm entirely

### Where LLM Fits (Future)
The system architecture reserves a clear boundary for LLM integration as a **plugin**:
- LLM as Intent Router replacement (prompt → plan)
- LLM as Answer Composer (evidence → natural language)
- LLM must NOT bypass the Tool → Evidence → Rule pipeline
- LLM must NOT reason without evidence grounding

# InsureQuery — System Map

> A visual and structural map of the entire Insurance Cognitive Decision Runtime.
> Use this document to understand how all components connect.

---

## 1. Six-Layer Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                        USER QUERY                             │
│            "e生保和好医保的免赔额分别是多少？"                  │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L1: KNOWLEDGE LAYER                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ Products │ │Regulations│ │   FAQs   │ │Chunks+Embeds │   │
│  │  (20)    │ │   (30)   │ │  (983)   │ │    (23)      │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬───────┘   │
│       └─────────────┴────────────┴──────────────┘           │
│                           │                                   │
│          Raw facts, documents, structured data                │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L2: ONTOLOGY LAYER                                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              NetworkX Directed Graph                  │   │
│  │  Product(4)──covers──→Disease(5)                      │   │
│  │  Product(4)──contains─→Coverage(6)                    │   │
│  │  Product(4)──regulated_by─→Regulation(3)              │   │
│  │  Regulation(3)──defines─→Rule(4)                      │   │
│  │                                                       │   │
│  │  22 Entities · 26 Relations · 7 Entity Types          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│          Formal domain model, typed relationships             │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L3: PROCESS LAYER                                           │
│  ┌──────────────────┐┌──────────────────┐┌──────────────────┐│
│  │  Claim Lifecycle ││   UW Lifecycle   ││ Policy Lifecycle ││
│  │  16S·19E·20T·5D  ││  15S·17E·20T·4D  ││ 17S·21E·25T·4D  ││
│  │                  ││                  ││                  ││
│  │ idle→accident→   ││ idle→apply→     ││ idle→apply→    ││
│  │ report→verify→   ││ health→risk→    ││ UW→issued→     ││
│  │ review→evaluate→ ││ standard/       ││ cooling→wait→  ││
│  │ approve/reject   ││ premium/excl/   ││ active→        ││
│  │                  ││ decline         ││ renew/terminate ││
│  └──────────────────┘└──────────────────┘└──────────────────┘│
│                                                               │
│          Executable state machines (states+events+transitions) │
│          + 13 decision nodes with yes/no branching            │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L4: DECISION LAYER                                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  45 Structured Rules across 4 domains:                │   │
│  │                                                       │   │
│  │  Underwriting (14)  Claim (13)  Eligibility (10)     │   │
│  │  Clause Interp (8)                                    │   │
│  │                                                       │   │
│  │  Each rule: if(conditions) → then(decision+action)   │   │
│  │  Each rule: source_ref · ontology_map · process_map   │   │
│  │                                                       │   │
│  │  Rules Graph: 204 nodes · 330 edges                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│          Condition → Decision logic with legal grounding      │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L5: RUNTIME LAYER                                           │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ┌─────────────┐  ┌──────────┐  ┌───────────────┐   │   │
│  │  │ Event Store │  │ Reducer  │  │ AsyncExecutor │   │   │
│  │  │ 22 types    │  │ pure fn  │  │ parallel+retry│   │   │
│  │  │ append-only │  │ replay   │  │ timeout+fallbk│   │   │
│  │  └──────┬──────┘  └────┬─────┘  └───────┬───────┘   │   │
│  │         └──────────────┴────────────────┘           │   │
│  │                                                     │   │
│  │  Runtime Nodes (5):                                 │   │
│  │  IntentRouter → Retrieval → DeterministicFunction   │   │
│  │  → Evaluation → Supervisor                          │   │
│  │                                                     │   │
│  │  9 Deterministic Functions (tools with schemas)      │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│          Event-sourced state machine + deterministic dispatch │
└──────────────────────────┬───────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│  L6: EVALUATION LAYER                                        │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  TraceCapture → EvaluationEngine(5-dim)              │   │
│  │               → HallucinationDetector(3 violations)  │   │
│  │               → FeedbackLoop(5 signal types)         │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                               │
│          Self-assessment + improvement signal generation      │
└───────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────┐
│                     ANSWER + EVALUATION                       │
│  { answer, evidence, score, hallucination, feedback }        │
└──────────────────────────────────────────────────────────────┘
```

---

## 2. Three Core Loops

### Loop 1: Query Loop (Per-Request)
```
                            ┌──────────────┐
                            │  User Query   │
                            └──────┬───────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │      Intent Router          │
                    │  classify → plan template   │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼────────┐  ┌───────▼────────┐  ┌───────▼────────┐
    │ Ontology Expand  │  │ Hybrid Retrieve│  │ Tool Dispatch  │
    │ lookup+expand    │  │ BM25+Vec+Onto  │  │ (9 functions)  │
    └─────────┬────────┘  └───────┬────────┘  └───────┬────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     Answer Composer          │
                    │  template + evidence + cite  │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │     Evaluation Engine        │
                    │  score · hallucination · fb  │
                    └──────────────┬──────────────┘
                                   │
                            ┌──────▼───────┐
                            │   Answer     │
                            │ + Trace      │
                            │ + Evaluation │
                            └──────────────┘
```

### Loop 2: Decision Loop (Per-Domain)
```
┌──────────────┐     ┌──────────────┐     ┌───────────────┐
│  Knowledge   │────▶│   Ontology   │────▶│    Process    │
│  (facts)     │     │  (entities)  │     │  (states)     │
└──────────────┘     └──────────────┘     └───────┬───────┘
                                                   │
                    ┌──────────────────────────────┘
                    │
            ┌───────▼───────┐
            │   Condition   │  ← "disease=恶性肿瘤 AND tnm≥II"
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │   Decision    │  ← "reject: permanent_decline"
            │   (Rule)      │
            └───────┬───────┘
                    │
            ┌───────▼───────┐
            │   Evidence    │  ← "source: UW_MANUAL-MALIGNANCY-01"
            │   Trace       │
            └───────────────┘
```

### Loop 3: Learning Loop (Cross-Query)
```
┌──────────────┐     ┌───────────────┐     ┌────────────────┐
│   Query      │────▶│   Evaluation   │────▶│   Feedback     │
│   + Answer   │     │   Engine       │     │   Signals      │
└──────────────┘     │ 5-dim scoring  │     │ 5 signal types │
                     │ halluc detect  │     └───────┬────────┘
                     └───────────────┘             │
                                                   │
                     ┌─────────────────────────────┘
                     │
         ┌───────────┼───────────┬──────────────┐
         │           │           │              │
   ┌─────▼─────┐ ┌──▼────┐ ┌────▼────┐ ┌──────▼──────┐
   │Retrieval  │ │Tool   │ │Ontology│ │Planner      │
   │Tuning     │ │Routing│ │Coverage│ │Adjustment   │
   └───────────┘ └───────┘ └────────┘ └─────────────┘
         │           │           │              │
         └───────────┴───────────┴──────────────┘
                     │
               ┌─────▼─────┐
               │ Next Query│ (uses improved system)
               └───────────┘
```

---

## 3. Data Flow Diagram (End-to-End)

```
External Data Sources                    Internal Processing
─────────────────────                    ───────────────────

Insurance Product PDFs ──→ Ingestion Pipeline ──→ Chunk Store
                                                     │
Regulatory Documents ────→ Text Extraction ─────────┤
                                                     │
Community FAQ Data ──────→ FAQ Dataset ─────────────┤
                                                     │
                                              ┌──────▼──────┐
                                              │  Evidence   │
                                              │  Index      │
                                              └──────┬──────┘
                                                     │
User Query ──────────────→ Intent Router ────────────┤
                                │                    │
                         ┌──────▼──────┐     ┌───────▼──────┐
                         │  Ontology   │────▶│   Hybrid     │
                         │  Expansion  │     │  Retrieval   │
                         └─────────────┘     └───────┬──────┘
                                                     │
                                              ┌──────▼──────┐
                                              │  Ranked     │
                                              │  Evidence   │
                                              └──────┬──────┘
                                                     │
                         ┌───────────────────────────┤
                         │                           │
                  ┌──────▼──────┐            ┌───────▼──────┐
                  │  Process    │            │  Decision    │
                  │  State      │───────────▶│  Rule        │
                  │  Machine    │  triggers  │  Evaluation  │
                  └──────┬──────┘            └───────┬──────┘
                         │                           │
                         └───────────┬───────────────┘
                                     │
                              ┌──────▼──────┐
                              │   Answer    │
                              │ + Evidence  │
                              │ + Citations │
                              └──────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │  Evaluation │
                              │  + Trace    │
                              └─────────────┘
```

---

## 4. Component Dependency Map

```
infra/cache ──────────────┐
infra/observability ──────┤
                          ├──▶ runtime/agents/orchestrator (MultiAgentEngine)
                          │         │
runtime/execution/ ───────┤    ┌────┴─────────────────────────┐
runtime/tools/ ───────────┤    │  runtime/agents/bus           │
runtime/engine/ ──────────┤    │  (AgentBus + AgentContext)    │
                          │    └────┬─────────────────────────┘
knowledge/engine ─────────┤         │
knowledge/ingestion/ ─────┤    ┌────┴─────────────────────────┐
knowledge/ontology/ ──────┤    │  runtime/agents/agents       │
knowledge/retrieval/ ─────┤    │  (5 Runtime Nodes)           │
knowledge/evidence/ ──────┤    └──────────────────────────────┘
                          │
evaluation/trace/ ────────┤
evaluation/engine/ ───────┤
evaluation/hallucination/ ┤
evaluation/feedback/ ─────┤
evaluation/runner/ ───────┤
                          │
apps/api/ ────────────────┘
```

---

## 5. State Machine (Runtime Perspective)

```
                    ┌─────────┐
                    │ created  │
                    └────┬────┘
                         │ USER_QUERY
                    ┌────▼────┐
                    │planning │
                    └────┬────┘
                         │ INTENT_CLASSIFIED
                         │ PLAN_CREATED
                    ┌────▼────┐
                    │executing│
                    └────┬────┘
                         │ TOOL_CALLED × N
                         │ EVIDENCE_FOUND × N
                    ┌────▼────┐
                    │answering│
                    └────┬────┘
                         │ ANSWER_GENERATED
                    ┌────▼────┐
                    │completed│
                    └─────────┘
                         │
                    ┌────▼────────────────────┐
                    │ Evaluation + Trace       │
                    │ (post-answer pipeline)   │
                    └─────────────────────────┘
```

---

## 6. Key Metrics at a Glance

| Metric | Value |
|---|---|
| Code modules | ~45 Python files |
| Tests | 257 passing |
| Event types | 22 |
| Entity types | 7 |
| Relation types | 7 |
| Deterministic functions (tools) | 9 |
| Runtime nodes | 5 |
| Decision rules | 45 |
| Decision types | 13 |
| Process state machines | 3 |
| Process states total | 48 |
| Process decisions total | 13 |
| Knowledge products | 20 |
| Knowledge regulations | 30 |
| Knowledge FAQs | 983 |

---

## 7. Terminology Map (Unified)

| Code Name | Unified Term | Category |
|---|---|---|
| Agent (PlannerAgent etc.) | Runtime Node | Runtime Layer |
| Planner | Intent Router | Runtime Layer |
| Tool (ProductSearchTool etc.) | Deterministic Function | Runtime Layer |
| EventStore | Event Store | Runtime Layer |
| Reducer | State Reducer | Runtime Layer |
| AgentBus | Runtime Node Bus | Runtime Layer |
| OntologyGraph | Ontology Graph | Ontology Layer |
| ChunkStore | Knowledge Store | Knowledge Layer |
| EvidenceIndex | Evidence Index | Knowledge Layer |
| EvaluationEngine | Evaluation Engine | Evaluation Layer |
| HallucinationDetector | Hallucination Detector | Evaluation Layer |
| FeedbackLoop | Feedback Loop | Evaluation Layer |
| QueryTrace | Execution Trace | Evaluation Layer |
| ProcessGraph | Process State Machine | Process Layer |
| DecisionRule | Decision Rule | Decision Layer |

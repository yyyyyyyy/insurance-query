import type { TraceGraph } from './trace'
import type { MemoryState } from './memory'
import type { ProcessState } from './process'
import type { ExecutionStep } from './trace'

export interface RetrievalWeights {
  bm25_weight: number
  vector_weight: number
  ontology_weight: number
}

export interface RetrievalChunk {
  chunk_id: string
  document_id: string
  content: string
  clause: string
  score: number
}

export interface RetrievalState {
  weights: RetrievalWeights
  topk: RetrievalChunk[]
  total?: number
  chunks?: RetrievalChunk[]
}

export interface TunerHistoryPoint {
  sequence: number
  timestamp: string
  bm25_weight: number
  vector_weight: number
  ontology_weight: number
  reason: string
}

export interface TunerState {
  weights: RetrievalWeights
  history: TunerHistoryPoint[]
  stats: Record<string, unknown>
}

export interface ConsoleAnswer {
  text: string
  citations?: unknown[]
  confidence?: number
  intent?: string
  evidence_count?: number
  tools_used?: string[]
  process_result?: ProcessState
  rule_evaluation?: Record<string, unknown>
}

export interface ConsolePayload {
  session_id: string
  trace_id: string
  query: string
  resolved_query?: string
  answer: ConsoleAnswer
  evaluation: Record<string, unknown>
  execution_graph: ExecutionStep[]
  latency_ms: number
  cached: boolean
  trace: TraceGraph
  memory: MemoryState
  retrieval: RetrievalState
  process: ProcessState
  tuner: TunerState
  event_trace: import('./trace').TraceEvent[]
}

export interface QueryRequest {
  query: string
  session_id?: string
}

export interface SessionListResponse {
  sessions: string[]
  count: number
}

export interface TraceEvent {
  event_id: string
  event_type: string
  session_id: string
  sequence_number: number
  timestamp: string
  payload: Record<string, unknown>
}

export interface TraceNode {
  id: string
  type?: string
  position: { x: number; y: number }
  data: Record<string, unknown>
}

export interface TraceEdge {
  id: string
  source: string
  target: string
  animated?: boolean
}

export interface TraceGraph {
  events: TraceEvent[]
  nodes: TraceNode[]
  edges: TraceEdge[]
}

export interface ExecutionStep {
  agent: string
  intent?: string
  plan_len?: number
  chunks?: number
  tools?: string[]
}

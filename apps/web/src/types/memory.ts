export interface MemoryState {
  facts: Record<string, unknown>
  active_process?: string | null
  last_products: string[]
  last_entities: string[]
  context: Record<string, unknown>
  memory_facts: Record<string, unknown>
  reads: Array<{ seq: number; facts: Record<string, unknown> }>
  writes: Array<{ seq: number; facts: Record<string, unknown> }>
}

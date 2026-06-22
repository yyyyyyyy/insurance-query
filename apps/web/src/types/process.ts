export interface ProcessTransition {
  from?: string
  to?: string
  index?: number
  decision_id?: string
  state?: string
  branch?: string
}

export interface ProcessState {
  process_name: string
  state: string
  path: string[]
  transitions: ProcessTransition[]
  outcome: string
}

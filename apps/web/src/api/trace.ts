import { apiFetch } from './client'
import type { ConsolePayload, QueryRequest } from '../types/api'

export async function postQuery(body: QueryRequest): Promise<ConsolePayload> {
  return apiFetch<ConsolePayload>('/query', {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export async function getTrace(sessionId: string): Promise<ConsolePayload> {
  return apiFetch<ConsolePayload>(`/trace/${sessionId}`)
}

export async function getSession(sessionId: string): Promise<ConsolePayload & { session_history?: unknown[] }> {
  return apiFetch(`/sessions/${sessionId}`)
}

export async function listSessions(): Promise<{ sessions: string[]; count: number }> {
  return apiFetch('/sessions')
}

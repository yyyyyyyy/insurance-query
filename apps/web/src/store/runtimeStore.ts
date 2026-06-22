import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ConsolePayload } from '../types/api'
import { postQuery, getTrace } from '../api/trace'

interface SessionRecord {
  sessionId: string
  query: string
  timestamp: string
}

interface RuntimeState {
  currentSessionId: string | null
  query: string
  sessionIdInput: string
  loading: boolean
  error: string | null
  payload: ConsolePayload | null
  sessionHistory: SessionRecord[]

  setQuery: (q: string) => void
  setSessionIdInput: (id: string) => void
  runQuery: () => Promise<void>
  loadSession: (sessionId: string) => Promise<void>
  clearError: () => void
}

export const useRuntimeStore = create<RuntimeState>()(
  persist(
    (set, get) => ({
      currentSessionId: null,
      query: '',
      sessionIdInput: '',
      loading: false,
      error: null,
      payload: null,
      sessionHistory: [],

      setQuery: (q) => set({ query: q }),
      setSessionIdInput: (id) => set({ sessionIdInput: id }),
      clearError: () => set({ error: null }),

      runQuery: async () => {
        const { query, sessionIdInput } = get()
        if (!query.trim()) return
        set({ loading: true, error: null })
        try {
          const payload = await postQuery({
            query: query.trim(),
            session_id: sessionIdInput.trim() || undefined,
          })
          const record: SessionRecord = {
            sessionId: payload.session_id,
            query: payload.query,
            timestamp: new Date().toISOString(),
          }
          const history = [
            record,
            ...get().sessionHistory.filter((s) => s.sessionId !== payload.session_id),
          ].slice(0, 50)
          set({
            payload,
            currentSessionId: payload.session_id,
            sessionIdInput: payload.session_id,
            sessionHistory: history,
            loading: false,
          })
        } catch (e) {
          set({ error: (e as Error).message, loading: false })
        }
      },

      loadSession: async (sessionId: string) => {
        set({ loading: true, error: null })
        try {
          const payload = await getTrace(sessionId)
          set({
            payload,
            currentSessionId: sessionId,
            sessionIdInput: sessionId,
            query: payload.query,
            loading: false,
          })
        } catch (e) {
          set({ error: (e as Error).message, loading: false })
        }
      },
    }),
    {
      name: 'runtime-console-sessions',
      partialize: (s) => ({ sessionHistory: s.sessionHistory }),
    },
  ),
)

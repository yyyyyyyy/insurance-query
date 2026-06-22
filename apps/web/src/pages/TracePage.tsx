import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getTrace } from '../api/trace'
import type { ConsolePayload } from '../types/api'
import { TraceTimeline, EventViewer } from '../components/TraceTimeline'

export function TracePage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [payload, setPayload] = useState<ConsolePayload | null>(null)
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!sessionId) return
    getTrace(sessionId)
      .then(setPayload)
      .catch((e) => setError((e as Error).message))
  }, [sessionId])

  const selectedEvent = payload?.event_trace?.find((e) => e.sequence_number === selectedSeq) ?? null

  if (error) return <div className="p-4 text-runtime-err font-mono">{error}</div>
  if (!payload) return <div className="p-4 text-runtime-muted font-mono">Loading trace…</div>

  return (
    <div className="p-3 h-[calc(100vh-48px)] flex flex-col gap-3">
      <div className="panel p-3 font-mono text-sm">
        <div className="label">Session Replay</div>
        <div className="text-runtime-accent">{payload.session_id}</div>
        <div className="text-runtime-muted text-xs mt-1">{payload.query}</div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-0">
        <TraceTimeline
          events={payload.event_trace}
          selectedSeq={selectedSeq}
          onSelect={setSelectedSeq}
        />
        <EventViewer event={selectedEvent} />
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getTrace } from '../api/trace'
import type { ConsolePayload } from '../types/api'
import { TunerDashboard } from '../components/TunerDashboard'

export function TunerPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [payload, setPayload] = useState<ConsolePayload | null>(null)

  useEffect(() => {
    if (sessionId) getTrace(sessionId).then(setPayload)
  }, [sessionId])

  if (!payload) return <div className="p-4 text-runtime-muted font-mono">Loading…</div>

  return (
    <div className="p-3">
      <div className="label mb-3">Tuner Dashboard · {sessionId?.slice(0, 16)}…</div>
      <TunerDashboard tuner={payload.tuner} />
    </div>
  )
}

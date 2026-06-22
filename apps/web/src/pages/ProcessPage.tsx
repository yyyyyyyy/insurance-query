import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getTrace } from '../api/trace'
import type { ConsolePayload } from '../types/api'
import { ProcessGraph } from '../components/ProcessGraph'

export function ProcessPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [payload, setPayload] = useState<ConsolePayload | null>(null)

  useEffect(() => {
    if (sessionId) getTrace(sessionId).then(setPayload)
  }, [sessionId])

  if (!payload) return <div className="p-4 text-runtime-muted font-mono">Loading…</div>

  return (
    <div className="p-3 h-[calc(100vh-48px)]">
      <div className="label mb-3">Process Viewer · {sessionId?.slice(0, 16)}…</div>
      <ProcessGraph process={payload.process} />
    </div>
  )
}

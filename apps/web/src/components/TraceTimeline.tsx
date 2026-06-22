import { useState } from 'react'
import type { TraceEvent } from '../types/trace'

const EVENT_COLORS: Record<string, string> = {
  USER_QUERY: 'border-runtime-accent',
  INTENT_CLASSIFIED: 'border-blue-400',
  PLAN_CREATED: 'border-blue-300',
  MEMORY_UPDATED: 'border-purple-400',
  RETRIEVAL_EXECUTED: 'border-cyan-400',
  TOOL_EXECUTED: 'border-yellow-500',
  PROCESS_EXECUTED: 'border-orange-400',
  RULE_EVALUATED: 'border-pink-400',
  ANSWER_GENERATED: 'border-runtime-ok',
  EVALUATION_COMPLETED: 'border-green-400',
  TUNING_APPLIED: 'border-violet-400',
}

interface Props {
  events: TraceEvent[]
  selectedSeq?: number | null
  onSelect?: (seq: number) => void
}

export function TraceTimeline({ events, selectedSeq, onSelect }: Props) {
  const sorted = [...events].sort((a, b) => a.sequence_number - b.sequence_number)

  return (
    <div className="panel p-3 h-full overflow-auto font-mono text-sm">
      <div className="label mb-3">Event Timeline ({sorted.length})</div>
      <div className="space-y-1">
        {sorted.map((ev) => {
          const color = EVENT_COLORS[ev.event_type] ?? 'border-runtime-border'
          const active = selectedSeq === ev.sequence_number
          return (
            <button
              key={ev.event_id}
              type="button"
              onClick={() => onSelect?.(ev.sequence_number)}
              className={`w-full text-left px-2 py-1.5 border-l-2 ${color} hover:bg-white/5 ${
                active ? 'bg-white/10' : ''
              }`}
            >
              <span className="text-runtime-muted">#{ev.sequence_number}</span>{' '}
              <span className="text-runtime-accent">{ev.event_type}</span>
              <span className="text-runtime-muted text-xs ml-2">
                {ev.timestamp?.slice(11, 19)}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}

interface EventViewerProps {
  event: TraceEvent | null
}

export function EventViewer({ event }: EventViewerProps) {
  const [expanded, setExpanded] = useState(true)
  if (!event) {
    return (
      <div className="panel p-4 text-runtime-muted font-mono text-sm">
        Select an event from the timeline
      </div>
    )
  }
  return (
    <div className="panel p-3 font-mono text-sm overflow-auto">
      <div className="flex items-center justify-between mb-2">
        <div>
          <span className="label">Event </span>
          <span className="text-runtime-accent">{event.event_type}</span>
          <span className="text-runtime-muted ml-2">seq={event.sequence_number}</span>
        </div>
        <button
          type="button"
          className="text-xs text-runtime-muted hover:text-white"
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? 'collapse' : 'expand'}
        </button>
      </div>
      {expanded && (
        <pre className="text-xs text-gray-300 whitespace-pre-wrap break-all bg-black/30 p-3 rounded">
          {JSON.stringify(event.payload, null, 2)}
        </pre>
      )}
    </div>
  )
}

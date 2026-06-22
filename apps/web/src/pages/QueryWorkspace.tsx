import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import { useRuntimeStore } from '../store/runtimeStore'
import { ExecutionGraph } from '../components/ProcessGraph'
import { TraceTimeline, EventViewer } from '../components/TraceTimeline'

export function QueryWorkspace() {
  const {
    query, setQuery, sessionIdInput, setSessionIdInput,
    runQuery, loadSession, loading, error, payload, sessionHistory,
  } = useRuntimeStore()
  const [selectedSeq, setSelectedSeq] = useState<number | null>(null)

  const selectedEvent = payload?.event_trace?.find((e) => e.sequence_number === selectedSeq) ?? null

  return (
    <div className="flex flex-col h-[calc(100vh-48px)] gap-3 p-3">
      <div className="panel p-3 flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-[280px]">
          <label className="label block mb-1">Query</label>
          <input
            className="w-full bg-black/40 border border-runtime-border rounded px-3 py-2 font-mono text-sm focus:border-runtime-accent outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runQuery()}
            placeholder="e.g. e生保和好医保哪个好"
          />
        </div>
        <div className="w-64">
          <label className="label block mb-1">Session ID (optional)</label>
          <input
            className="w-full bg-black/40 border border-runtime-border rounded px-3 py-2 font-mono text-xs focus:border-runtime-accent outline-none"
            value={sessionIdInput}
            onChange={(e) => setSessionIdInput(e.target.value)}
            placeholder="auto-generated if empty"
          />
        </div>
        <button
          type="button"
          onClick={() => runQuery()}
          disabled={loading}
          className="px-4 py-2 bg-runtime-accent/20 border border-runtime-accent text-runtime-accent font-mono text-sm hover:bg-runtime-accent/30 disabled:opacity-50"
        >
          {loading ? 'RUNNING...' : 'EXECUTE'}
        </button>
        {payload && (
          <div className="text-xs font-mono text-runtime-muted">
            session: <span className="text-runtime-accent">{payload.session_id.slice(0, 12)}…</span>
            {' · '}{payload.latency_ms}ms
            {payload.cached && ' · CACHED'}
          </div>
        )}
      </div>

      {error && (
        <div className="panel p-2 text-runtime-err font-mono text-sm border-runtime-err">{error}</div>
      )}

      <div className="flex gap-2 text-xs font-mono overflow-x-auto">
        {sessionHistory.map((s) => (
          <button
            key={s.sessionId}
            type="button"
            onClick={() => loadSession(s.sessionId)}
            className="px-2 py-1 border border-runtime-border hover:border-runtime-accent text-runtime-muted hover:text-white whitespace-nowrap"
          >
            {s.query.slice(0, 20)}…
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 flex-1 min-h-0">
        <ExecutionGraph steps={payload?.execution_graph ?? []} />
        <div className="panel p-3 overflow-auto text-sm">
          <div className="label mb-2">Answer</div>
          {payload ? (
            <>
              <div className="text-xs text-runtime-muted mb-2 font-mono">
                intent: {payload.answer.intent} · confidence: {payload.answer.confidence?.toFixed(2)}
                · evidence: {payload.answer.evidence_count}
              </div>
              <div className="markdown-body text-gray-300 text-sm leading-relaxed">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {payload.answer.text}
                </ReactMarkdown>
              </div>
              {typeof payload.evaluation?.total_score === 'number' ? (
                <div className="mt-3 pt-3 border-t border-runtime-border text-xs font-mono">
                  eval score: {payload.evaluation.total_score} · hal:{' '}
                  {String(payload.evaluation.hallucination_score ?? '-')}
                </div>
              ) : null}
              <div className="mt-2 flex gap-2 text-xs font-mono">
                <Link to={`/trace/${payload.session_id}`} className="text-runtime-accent hover:underline">trace</Link>
                <Link to={`/memory/${payload.session_id}`} className="text-runtime-accent hover:underline">memory</Link>
                <Link to={`/retrieval/${payload.session_id}`} className="text-runtime-accent hover:underline">retrieval</Link>
                <Link to={`/process/${payload.session_id}`} className="text-runtime-accent hover:underline">process</Link>
                <Link to={`/tuner/${payload.session_id}`} className="text-runtime-accent hover:underline">tuner</Link>
              </div>
            </>
          ) : (
            <div className="text-runtime-muted">Execute a query to see runtime output</div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 h-64 min-h-[200px]">
        <TraceTimeline
          events={payload?.event_trace ?? []}
          selectedSeq={selectedSeq}
          onSelect={setSelectedSeq}
        />
        <EventViewer event={selectedEvent} />
      </div>
    </div>
  )
}

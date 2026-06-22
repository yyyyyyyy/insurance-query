import type { MemoryState } from '../types/memory'

interface Props {
  memory: MemoryState | null
  resolvedQuery?: string
  originalQuery?: string
}

export function MemoryInspector({ memory, resolvedQuery, originalQuery }: Props) {
  if (!memory) {
    return <div className="panel p-4 text-runtime-muted font-mono text-sm">No memory data</div>
  }

  const facts = { ...memory.facts, ...memory.memory_facts }

  return (
    <div className="space-y-4 font-mono text-sm">
      {(resolvedQuery && originalQuery && resolvedQuery !== originalQuery) && (
        <div className="panel p-3">
          <div className="label mb-2">Query Diff (memory enrichment)</div>
          <div className="text-runtime-err line-through opacity-70">{originalQuery}</div>
          <div className="text-runtime-ok mt-1">{resolvedQuery}</div>
        </div>
      )}

      <div className="panel p-3">
        <div className="label mb-2">Active Process</div>
        <div className="text-runtime-accent">{memory.active_process || '—'}</div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="panel p-3">
          <div className="label mb-2">last_products</div>
          <ul className="text-xs space-y-1">
            {memory.last_products?.length
              ? memory.last_products.map((p) => <li key={p}>{p}</li>)
              : <li className="text-runtime-muted">empty</li>}
          </ul>
        </div>
        <div className="panel p-3">
          <div className="label mb-2">last_entities</div>
          <ul className="text-xs space-y-1">
            {memory.last_entities?.length
              ? memory.last_entities.map((e) => <li key={e}>{e}</li>)
              : <li className="text-runtime-muted">empty</li>}
          </ul>
        </div>
      </div>

      <div className="panel p-3 overflow-auto max-h-64">
        <div className="label mb-2">Facts ({Object.keys(facts).length})</div>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-runtime-muted border-b border-runtime-border">
              <th className="text-left py-1">key</th>
              <th className="text-left py-1">value</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(facts).map(([k, v]) => (
              <tr key={k} className="border-b border-runtime-border/50">
                <td className="py-1 pr-2 text-runtime-accent">{k}</td>
                <td className="py-1 text-gray-400 truncate max-w-xs">
                  {typeof v === 'object' ? JSON.stringify(v) : String(v)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {memory.reads?.length > 0 && (
        <div className="panel p-3">
          <div className="label mb-2">Memory Reads ({memory.reads.length})</div>
          {memory.reads.map((r) => (
            <div key={r.seq} className="text-xs text-runtime-muted mb-1">seq #{r.seq}</div>
          ))}
        </div>
      )}
      {memory.writes?.length > 0 && (
        <div className="panel p-3">
          <div className="label mb-2">Memory Writes ({memory.writes.length})</div>
          {memory.writes.map((w) => (
            <div key={w.seq} className="text-xs mb-1">
              <span className="text-runtime-muted">#{w.seq}</span>{' '}
              {Object.keys(w.facts).join(', ')}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

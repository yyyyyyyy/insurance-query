import ReactECharts from 'echarts-for-react'
import type { RetrievalState } from '../types/api'

interface Props {
  retrieval: RetrievalState | null
}

export function RetrievalPanel({ retrieval }: Props) {
  if (!retrieval) {
    return <div className="panel p-4 text-runtime-muted font-mono text-sm">No retrieval data</div>
  }

  const w = retrieval.weights
  const chunks = retrieval.topk?.length ? retrieval.topk : retrieval.chunks ?? []

  const pieOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        label: { color: '#8b949e', fontFamily: 'monospace' },
        data: [
          { name: 'BM25', value: w.bm25_weight },
          { name: 'Vector', value: w.vector_weight },
          { name: 'Ontology', value: w.ontology_weight },
        ],
        itemStyle: {
          color: (p: { name: string }) =>
            p.name === 'BM25' ? '#58a6ff' : p.name === 'Vector' ? '#3fb950' : '#d29922',
        },
      },
    ],
  }

  const barOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 16, top: 24, bottom: 60 },
    xAxis: {
      type: 'category',
      data: chunks.slice(0, 10).map((c) => c.chunk_id?.slice(0, 12) ?? ''),
      axisLabel: { color: '#8b949e', rotate: 30, fontSize: 10 },
    },
    yAxis: { type: 'value', axisLabel: { color: '#8b949e' }, splitLine: { lineStyle: { color: '#30363d' } } },
    series: [
      {
        type: 'bar',
        data: chunks.slice(0, 10).map((c) => c.score),
        itemStyle: { color: '#58a6ff' },
      },
    ],
  }

  return (
    <div className="space-y-4 font-mono text-sm">
      <div className="grid grid-cols-3 gap-3">
        <div className="panel p-3 text-center">
          <div className="label">BM25</div>
          <div className="text-2xl text-runtime-accent">{(w.bm25_weight * 100).toFixed(1)}%</div>
        </div>
        <div className="panel p-3 text-center">
          <div className="label">Vector</div>
          <div className="text-2xl text-runtime-ok">{(w.vector_weight * 100).toFixed(1)}%</div>
        </div>
        <div className="panel p-3 text-center">
          <div className="label">Ontology</div>
          <div className="text-2xl text-runtime-warn">{(w.ontology_weight * 100).toFixed(1)}%</div>
        </div>
      </div>

      <div className="panel p-3">
        <div className="label mb-2">Weight Distribution</div>
        <ReactECharts option={pieOption} style={{ height: 220 }} />
      </div>

      <div className="panel p-3">
        <div className="label mb-2">Top-K Scores ({chunks.length})</div>
        <ReactECharts option={barOption} style={{ height: 240 }} />
      </div>

      <div className="panel p-3 overflow-auto max-h-48">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-runtime-muted border-b border-runtime-border">
              <th className="text-left py-1">chunk</th>
              <th className="text-left py-1">clause</th>
              <th className="text-right py-1">score</th>
            </tr>
          </thead>
          <tbody>
            {chunks.map((c) => (
              <tr key={c.chunk_id} className="border-b border-runtime-border/30">
                <td className="py-1 text-runtime-accent">{c.chunk_id}</td>
                <td className="py-1 text-gray-500">{c.clause}</td>
                <td className="py-1 text-right">{c.score?.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

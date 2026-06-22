import ReactECharts from 'echarts-for-react'
import type { TunerState } from '../types/api'

interface Props {
  tuner: TunerState | null
}

export function TunerDashboard({ tuner }: Props) {
  if (!tuner) {
    return <div className="panel p-4 text-runtime-muted font-mono text-sm">No tuner data</div>
  }

  const history = tuner.history ?? []
  const w = tuner.weights

  const lineOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['BM25', 'Vector', 'Ontology'], textStyle: { color: '#8b949e' } },
    grid: { left: 48, right: 24, top: 40, bottom: 32 },
    xAxis: {
      type: 'category',
      data: history.length
        ? history.map((h) => `#${h.sequence}`)
        : ['current'],
      axisLabel: { color: '#8b949e' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 1,
      axisLabel: { color: '#8b949e' },
      splitLine: { lineStyle: { color: '#30363d' } },
    },
    series: [
      {
        name: 'BM25',
        type: 'line',
        data: history.length ? history.map((h) => h.bm25_weight) : [w.bm25_weight],
        itemStyle: { color: '#58a6ff' },
      },
      {
        name: 'Vector',
        type: 'line',
        data: history.length ? history.map((h) => h.vector_weight) : [w.vector_weight],
        itemStyle: { color: '#3fb950' },
      },
      {
        name: 'Ontology',
        type: 'line',
        data: history.length ? history.map((h) => h.ontology_weight) : [w.ontology_weight],
        itemStyle: { color: '#d29922' },
      },
    ],
  }

  return (
    <div className="space-y-4 font-mono text-sm">
      <div className="panel p-3">
        <div className="label mb-2">Current Retrieval Strategy</div>
        <div className="grid grid-cols-3 gap-4 text-center">
          <div>
            <div className="text-runtime-muted text-xs">bm25_weight</div>
            <div className="text-xl text-runtime-accent">{w.bm25_weight.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-runtime-muted text-xs">vector_weight</div>
            <div className="text-xl text-runtime-ok">{w.vector_weight.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-runtime-muted text-xs">ontology_weight</div>
            <div className="text-xl text-runtime-warn">{w.ontology_weight.toFixed(4)}</div>
          </div>
        </div>
        {tuner.stats?.last_adjustment != null ? (
          <div className="mt-3 text-xs text-runtime-muted">
            last: {String(tuner.stats.last_adjustment)}
          </div>
        ) : null}
      </div>

      <div className="panel p-3">
        <div className="label mb-2">Weight Evolution</div>
        <ReactECharts option={lineOption} style={{ height: 280 }} />
      </div>

      {history.length > 1 && (
        <div className="panel p-3">
          <div className="label mb-2">Before / After (last adjustment)</div>
          <div className="grid grid-cols-2 gap-4 text-xs">
            <div>
              <div className="text-runtime-muted mb-1">before (#{history[history.length - 2]?.sequence})</div>
              <pre className="bg-black/30 p-2 rounded">
                {JSON.stringify({
                  bm25: history[history.length - 2]?.bm25_weight,
                  vector: history[history.length - 2]?.vector_weight,
                  ontology: history[history.length - 2]?.ontology_weight,
                }, null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-runtime-muted mb-1">after (#{history[history.length - 1]?.sequence})</div>
              <pre className="bg-black/30 p-2 rounded">
                {JSON.stringify({
                  bm25: history[history.length - 1]?.bm25_weight,
                  vector: history[history.length - 1]?.vector_weight,
                  ontology: history[history.length - 1]?.ontology_weight,
                  reason: history[history.length - 1]?.reason,
                }, null, 2)}
              </pre>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

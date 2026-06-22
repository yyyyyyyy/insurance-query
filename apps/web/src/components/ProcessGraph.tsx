import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  MarkerType,
  type Node,
  type Edge,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { ProcessState } from '../types/process'
import type { ExecutionStep } from '../types/trace'

interface ProcessGraphProps {
  process: ProcessState | null
}

export function ProcessGraph({ process }: ProcessGraphProps) {
  const { nodes, edges } = useMemo(() => {
    if (!process?.path?.length) {
      return { nodes: [] as Node[], edges: [] as Edge[] }
    }
    const path = process.path
    const current = process.state
    const ns: Node[] = path.map((stateId, i) => ({
      id: stateId,
      position: { x: i * 180, y: 80 },
      data: { label: stateId },
      style: {
        background: stateId === current ? '#238636' : '#21262d',
        color: stateId === current ? '#fff' : '#c9d1d9',
        border: stateId === current ? '2px solid #3fb950' : '1px solid #30363d',
        borderRadius: 4,
        fontSize: 11,
        fontFamily: 'monospace',
        padding: '8px 12px',
        minWidth: 120,
      },
    }))
    const es: Edge[] = []
    for (let i = 0; i < path.length - 1; i++) {
      es.push({
        id: `${path[i]}-${path[i + 1]}`,
        source: path[i],
        target: path[i + 1],
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: '#58a6ff' },
        style: { stroke: '#58a6ff' },
      })
    }
    return { nodes: ns, edges: es }
  }, [process])

  if (!process?.path?.length) {
    return (
      <div className="panel h-full flex items-center justify-center text-runtime-muted font-mono text-sm">
        No process execution for this session
      </div>
    )
  }

  return (
    <div className="panel h-full min-h-[280px]">
      <div className="label px-3 pt-2">
        {process.process_name} → {process.outcome || process.state}
      </div>
      <div style={{ height: 'calc(100% - 28px)', minHeight: 250 }}>
        <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false}>
          <Background color="#30363d" gap={16} />
          <Controls />
          <MiniMap nodeColor={() => '#21262d'} maskColor="rgba(0,0,0,0.6)" />
        </ReactFlow>
      </div>
    </div>
  )
}

interface ExecutionGraphProps {
  steps: ExecutionStep[]
}

export function ExecutionGraph({ steps }: ExecutionGraphProps) {
  const { nodes, edges } = useMemo(() => {
    const ns: Node[] = steps.map((step, i) => ({
      id: `step-${i}`,
      position: { x: 40, y: i * 90 },
      data: {
        label: (
          <div className="font-mono text-xs">
            <div className="text-runtime-accent font-semibold">{step.agent}</div>
            {step.intent && <div className="text-runtime-muted">intent: {step.intent}</div>}
            {step.tools && <div className="text-runtime-muted">tools: {step.tools.join(', ')}</div>}
            {step.chunks != null && <div className="text-runtime-muted">chunks: {step.chunks}</div>}
          </div>
        ),
      },
      style: {
        background: '#161b22',
        border: '1px solid #30363d',
        borderRadius: 4,
        padding: 8,
        width: 200,
      },
    }))
    const es: Edge[] = steps.slice(1).map((_, i) => ({
      id: `e-${i}`,
      source: `step-${i}`,
      target: `step-${i + 1}`,
      animated: true,
      style: { stroke: '#58a6ff' },
    }))
    return { nodes: ns, edges: es }
  }, [steps])

  return (
    <div className="h-full min-h-[300px] border border-runtime-border rounded-sm bg-runtime-panel">
      <div className="label px-3 pt-2">Execution Graph</div>
      <div style={{ height: 'calc(100% - 28px)', minHeight: 270 }}>
        <ReactFlow nodes={nodes} edges={edges} fitView nodesDraggable={false}>
          <Background color="#30363d" gap={20} />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  )
}

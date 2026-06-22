import { Link, Route, Routes, useLocation } from 'react-router-dom'
import { QueryWorkspace } from './pages/QueryWorkspace'
import { TracePage } from './pages/TracePage'
import { MemoryPage } from './pages/MemoryPage'
import { RetrievalPage } from './pages/RetrievalPage'
import { ProcessPage } from './pages/ProcessPage'
import { TunerPage } from './pages/TunerPage'

const NAV = [
  { to: '/', label: 'Query' },
]

function Shell() {
  const loc = useLocation()
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-runtime-border bg-runtime-panel px-4 py-2 flex items-center gap-6">
        <div className="font-mono text-sm font-semibold text-runtime-accent">
          Insurance Runtime Console
        </div>
        <nav className="flex gap-4 text-xs font-mono">
          {NAV.map((n) => (
            <Link
              key={n.to}
              to={n.to}
              className={loc.pathname === n.to ? 'text-runtime-accent' : 'text-runtime-muted hover:text-white'}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto text-xs font-mono text-runtime-muted">v1 · kernel-v2</div>
      </header>
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<QueryWorkspace />} />
          <Route path="/trace/:sessionId" element={<TracePage />} />
          <Route path="/memory/:sessionId" element={<MemoryPage />} />
          <Route path="/retrieval/:sessionId" element={<RetrievalPage />} />
          <Route path="/process/:sessionId" element={<ProcessPage />} />
          <Route path="/tuner/:sessionId" element={<TunerPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return <Shell />
}

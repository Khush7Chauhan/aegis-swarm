import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, BrainCircuit, ChevronRight, Database, LockKeyhole, RotateCcw, Shield, Skull, Terminal, Zap } from 'lucide-react'
import Graph from './components/Graph'
import './App.css'

const API = (import.meta.env?.VITE_API_BASE || 'http://localhost:8000').replace(/\/+$/, '')
const POLL_INTERVAL_MS = 1500
const REQUEST_TIMEOUT_MS = 8000
const COMMAND_TIMEOUT_MS = 30000
const EMPTY_GRAPH = { nodes: [], edges: [], metrics: {} }

// Brutalist control: transparent, hairline border, solid white on hover.
const BTN = 'flex items-center justify-center gap-2 border border-[#27272a] px-4 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[#e4e4e7] transition-colors hover:border-white hover:bg-white hover:text-black disabled:pointer-events-none disabled:opacity-30'
// Accent controls mirror the red/blue agent semantics at the action layer.
const RED_BTN = 'flex items-center justify-center gap-2 border border-[#ff4444] bg-[#ff4444]/5 px-4 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[#ff4444] transition-colors hover:bg-[#ff4444] hover:text-black disabled:pointer-events-none disabled:opacity-30'
const BLUE_BTN = 'flex items-center justify-center gap-2 border border-[#3b82f6] bg-[#3b82f6]/5 px-4 py-3 font-mono text-[10px] uppercase tracking-[0.2em] text-[#3b82f6] transition-colors hover:bg-[#3b82f6] hover:text-black disabled:pointer-events-none disabled:opacity-30'

async function fetchJson(path, options = {}) {
  const { timeoutMs = REQUEST_TIMEOUT_MS, ...init } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const response = await fetch(`${API}${path}`, { ...init, signal: controller.signal })
    if (!response.ok) {
      let detail = `${init.method || 'GET'} ${path} failed (HTTP ${response.status})`
      try {
        const body = await response.json()
        if (body?.detail) detail = body.detail
      } catch {
        /* non-JSON error body, keep the status message */
      }
      throw new Error(detail)
    }
    return await response.json()
  } finally {
    clearTimeout(timeout)
  }
}

function normalizeGraph(payload) {
  return {
    nodes: Array.isArray(payload?.nodes) ? payload.nodes : [],
    edges: Array.isArray(payload?.edges) ? payload.edges : [],
    metrics: payload?.metrics && typeof payload.metrics === 'object' ? payload.metrics : {},
  }
}

function sourceLabel(source) {
  if (source === 'computed') return 'COMPUTED'
  if (source === 'seed') return 'SEEDED'
  return 'UNKNOWN'
}

function App() {
  const [graph, setGraph] = useState(EMPTY_GRAPH)
  const [feed, setFeed] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [connected, setConnected] = useState(false)
  const [hydrated, setHydrated] = useState(false)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [notice, setNotice] = useState(null)
  const [pollRate, setPollRate] = useState('0.0')
  const [showMemory, setShowMemory] = useState(false)
  const [simulation, setSimulation] = useState({ running: false, status: 'IDLE' })
  const [isSwarmActive, setIsSwarmActive] = useState(false)
  const feedRef = useRef(null)
  const requestsRef = useRef([])
  const pollRef = useRef(null)
  const showMemoryRef = useRef(false)

  const refresh = useCallback(async () => {
    // Cancel any in-flight poll so a manual command always re-fetches immediately.
    pollRef.current?.abort()
    const controller = new AbortController()
    pollRef.current = controller

    const now = Date.now()
    requestsRef.current = [...requestsRef.current.filter((stamp) => now - stamp < 1000), now]
    setPollRate(requestsRef.current.length.toFixed(1))

    const graphUrl = `${API}/api/graph${showMemoryRef.current ? '?include_memory=true' : ''}`
    try {
      const [graphResponse, feedResponse, simResponse] = await Promise.all([
        fetch(graphUrl, { signal: controller.signal }),
        fetch(`${API}/api/feed`, { signal: controller.signal }),
        fetch(`${API}/api/simulation/status`, { signal: controller.signal }),
      ])
      if (!graphResponse.ok || !feedResponse.ok) throw new Error('Telemetry link unavailable')
      const nextGraph = normalizeGraph(await graphResponse.json())
      const nextFeed = await feedResponse.json()
      setGraph(nextGraph)
      setFeed(Array.isArray(nextFeed) ? nextFeed : [])
      setConnected(true)
      setError(null)
      setSelectedNode((current) => (current ? nextGraph.nodes.find((node) => node.id === current.id) ?? null : null))
      if (simResponse.ok) {
        const simBody = await simResponse.json()
        const running = Boolean(simBody?.running)
        setIsSwarmActive(running)
        setSimulation({ running, status: simBody?.status || 'IDLE' })
      }
    } catch (err) {
      if (err?.name === 'AbortError') return
      setConnected(false)
      setError(err?.message || 'Telemetry link unavailable')
    } finally {
      setHydrated(true)
    }
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, POLL_INTERVAL_MS)
    return () => {
      clearInterval(timer)
      pollRef.current?.abort()
    }
  }, [refresh])

  // Re-fetch immediately when the forensic memory overlay is toggled.
  useEffect(() => {
    if (showMemoryRef.current === showMemory) return
    showMemoryRef.current = showMemory
    refresh()
  }, [showMemory, refresh])

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [feed])

  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), 6000)
    return () => clearTimeout(timer)
  }, [notice])

  const command = useCallback(
    async (path) => {
      setBusy(path)
      setError(null)
      try {
        const body = await fetchJson(path, { method: 'POST', timeoutMs: COMMAND_TIMEOUT_MS })
        setNotice(body?.message || 'Command acknowledged')
        await refresh()
      } catch (err) {
        setError(err?.message || 'Command rejected by backend')
      } finally {
        setBusy(null)
      }
    },
    [refresh],
  )

  const toggleSwarm = useCallback(async () => {
    const next = !isSwarmActive
    const path = next ? '/api/simulation/start' : '/api/simulation/stop'
    // Optimistic flip so the toggle responds instantly, then reconcile.
    setIsSwarmActive(next)
    setSimulation({ running: next, status: next ? 'ACTIVE' : 'IDLE' })
    setBusy(path)
    setError(null)
    try {
      const body = await fetchJson(path, { method: 'POST', timeoutMs: COMMAND_TIMEOUT_MS })
      setIsSwarmActive(Boolean(body?.running))
      setSimulation({
        running: Boolean(body?.running),
        status: body?.sim_status || (body?.running ? 'ACTIVE' : 'IDLE'),
      })
      setNotice(body?.message || 'Autonomous command acknowledged')
      await refresh()
    } catch (err) {
      setIsSwarmActive(!next) // revert the optimistic flip
      setError(err?.message || 'Autonomous command rejected by backend')
    } finally {
      setBusy(null)
    }
  }, [isSwarmActive, refresh])

  const toggleMemory = useCallback(() => setShowMemory((current) => !current), [])

  const compromised = graph.nodes.filter((node) => node.status === 'COMPROMISED').length
  const severed = graph.edges.filter((edge) => edge.status === 'SEVERED').length
  const memoryCount = graph.nodes.filter((node) => node.type === 'IncidentReport').length
  const defcon = compromised > 1 ? 'DEFCON 2' : compromised ? 'DEFCON 3' : 'DEFCON 5'
  const controlsDisabled = Boolean(busy) || !connected
  const linkLabel = connected ? 'FALKORDB LINKED' : hydrated ? 'LINK OFFLINE' : 'LINKING...'
  const linkTone = connected ? 'bg-white' : hydrated ? 'bg-[#ff4444]' : 'bg-[#71717a]'

  return <main className="min-h-screen bg-[#050505] font-sans text-[#e4e4e7]">
    <div className="mx-auto max-w-[1600px] border-x border-[#27272a]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#27272a] px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="h-2 w-2 bg-white" />
          <h1 className="text-[11px] font-medium uppercase tracking-[0.25em] text-[#e4e4e7]">Fig. 01 // Aegis Swarm // Live Topology Model</h1>
        </div>
        <div className="flex flex-wrap items-center gap-x-6 gap-y-1 font-mono text-[10px] uppercase tracking-widest text-[#71717a]">
          <span>Scan 01 / 000%</span>
          <span>Yaw 036 / Pitch 32</span>
          <span className="flex items-center gap-2"><i className={`h-1.5 w-1.5 ${linkTone}`} />{linkLabel}</span>
        </div>
      </header>

      <section className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b border-[#27272a] px-5 py-3 font-mono text-[10px] uppercase tracking-widest text-[#71717a]">
        <span className="flex items-center gap-2"><AlertTriangle size={12} className={compromised ? 'text-[#ff4444]' : 'text-[#71717a]'} />Threat posture</span>
        <span className={compromised ? 'text-[#ff4444]' : 'text-[#e4e4e7]'}>{compromised ? 'Active breach detected' : 'Monitoring active'}</span>
        <span className="ml-auto flex flex-wrap gap-x-4 gap-y-1">
          <span>{graph.nodes.length} assets / {graph.edges.length} links</span>
          <span>{severed} severed</span>
          <span>{memoryCount} memory</span>
        </span>
      </section>

      <AutonomyBanner simulation={simulation} />

      {(error || notice) && <section className={`flex items-center gap-2 border-b px-5 py-2.5 font-mono text-[10px] uppercase tracking-widest ${error ? 'border-[#ff4444]/40 text-[#ff4444]' : 'border-[#27272a] text-[#71717a]'}`} role={error ? 'alert' : 'status'}>
        {error ? <AlertTriangle size={12} /> : <Activity size={12} />}
        <span className="truncate">{error ? `Backend error // ${error}` : notice}</span>
        {error && <button onClick={() => refresh()} className="ml-auto border border-[#27272a] px-2 py-1 text-[9px] transition-colors hover:border-white hover:bg-white hover:text-black">Retry</button>}
      </section>}

      <section className="grid grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="border-b border-[#27272a] lg:border-b-0 lg:border-r">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#27272a] px-5 py-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-[#e4e4e7]">02 // Live attack graph</span>
            <MemoryToggle enabled={showMemory} count={memoryCount} onToggle={toggleMemory} disabled={!connected} />
          </div>
          <div className="h-[520px] lg:h-[660px]">
            <Graph graph={graph} selectedNode={selectedNode} onSelectNode={setSelectedNode} showMemory={showMemory} />
          </div>
        </div>

        <aside className="flex flex-col divide-y divide-[#27272a]">
          <Inspector node={selectedNode} metrics={graph.metrics} onSever={() => command('/api/blue/defend')} disabled={controlsDisabled} busy={busy === '/api/blue/defend'} />
          <Feed events={feed} feedRef={feedRef} />
        </aside>
      </section>

      <ControlDeck busy={controlsDisabled} onCommand={command} defcon={defcon} pollRate={pollRate} isSwarmActive={isSwarmActive} onToggleSwarm={toggleSwarm} />
    </div>

    <footer className="mx-auto flex max-w-[1600px] flex-wrap justify-between gap-2 border-t border-[#27272a] px-5 py-4 font-mono text-[9px] uppercase tracking-widest text-[#71717a]">
      <span>Aegis // FalkorDB shared-state blackboard</span>
      <span>Fig. 05 // End of sheet</span>
    </footer>
  </main>
}

function AutonomyBanner({ simulation }) {
  const status = simulation?.status || 'IDLE'
  if (status === 'IDLE') return null
  const running = Boolean(simulation?.running)
  const tone = status === 'BREACHED'
    ? 'border-[#ff4444] text-[#ff4444]'
    : status === 'CONTAINED'
      ? 'border-[#e4e4e7] text-[#e4e4e7]'
      : 'border-[#71717a] text-[#e4e4e7]'
  const label = status === 'BREACHED'
    ? 'Crown jewel breached — swarm halted'
    : status === 'CONTAINED'
      ? 'Swarm containment achieved — all routes severed'
      : 'Autonomous stigmergy engaged'
  return <section className={`flex flex-wrap items-center gap-3 border-b px-5 py-2.5 font-mono text-[10px] uppercase tracking-[0.2em] ${tone}`} role="status" aria-live="polite">
    <span className={`h-1.5 w-1.5 ${running ? 'blink bg-white' : status === 'BREACHED' ? 'bg-[#ff4444]' : 'bg-[#e4e4e7]'}`} />
    <Zap size={12} />
    <span>{label}</span>
    <span className="ml-auto text-[9px] tracking-widest text-[#71717a]">{running ? 'Red 2.0s / Blue 2.5s cadence' : 'Loop terminated'}</span>
  </section>
}

function MemoryToggle({ enabled, count, onToggle, disabled }) {
  return <button
    type="button"
    role="switch"
    aria-checked={enabled}
    disabled={disabled}
    onClick={onToggle}
    title="Render FalkorDB IncidentReport memory nodes"
    className={`flex items-center gap-2 border px-3 py-1.5 font-mono text-[9px] uppercase tracking-[0.2em] transition-colors disabled:pointer-events-none disabled:opacity-30 ${enabled ? 'border-white bg-white text-black' : 'border-[#27272a] text-[#71717a] hover:border-white hover:text-white'}`}
  >
    <BrainCircuit size={12} />
    <span className="hidden sm:inline">Show agent memory graph</span><span className="sm:hidden">Memory</span>
    <span>[{enabled ? 'ON' : 'OFF'}]</span>
    {enabled && <span>{count}</span>}
  </button>
}

function StatRow({ label, value, accent }) {
  return <div className="flex items-center justify-between gap-3 border-b border-[#27272a] py-3 font-mono text-[12px] uppercase tracking-widest">
    <span className="text-[#a1a1aa]">{label}</span>
    <span className={accent || 'text-[#e4e4e7]'}>{value}</span>
  </div>
}

function CentralityBar({ value, compromised }) {
  const width = Math.min(Math.max(Number(value) || 0, 0) * 100, 100)
  return <div className="mt-2 h-[2px] w-full bg-[#27272a]"><div className={`h-[2px] ${compromised ? 'bg-[#ff4444]' : 'bg-white'}`} style={{ width: `${width}%` }} /></div>
}

function Inspector({ node, metrics, onSever, disabled, busy }) {
  const centrality = Number(node?.centrality)
  const pagerank = Number(node?.pagerank)
  const centralitySource = sourceLabel(metrics?.centrality_source)
  const pagerankSource = sourceLabel(metrics?.pagerank_source)
  const computedLive = metrics?.pagerank_source === 'computed' || metrics?.centrality_source === 'computed'
  const defendButton = <button onClick={onSever} disabled={disabled} className={`${BLUE_BTN} mt-5 w-full`}><LockKeyhole size={15} />{busy ? 'Defending...' : 'Run blue defense'}</button>

  if (node?.type === 'IncidentReport') {
    return <section className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <span className="flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.2em] text-[#e4e4e7]"><BrainCircuit size={15} />03 // Forensic memory node</span>
        <span className="font-mono text-[11px] uppercase tracking-widest text-[#a1a1aa]">FalkorDB // episodic</span>
      </div>
      <div className="border-l border-[#e4e4e7] pl-3">
        <p className="font-mono text-[12px] tracking-widest text-[#a1a1aa]">{node.id}</p>
        <h2 className="mt-1 text-xl font-medium text-[#e4e4e7]">{node.agent || 'Blue Sentinel'}</h2>
        <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-[#a1a1aa]">{node.type} // {node.severity || 'HIGH'}</p>
      </div>
      <div className="mt-5">
        <StatRow label="Recorded at" value={formatTimestamp(node.timestamp)} accent="text-[#e4e4e7]" />
      </div>
      <p className="mt-4 font-mono text-[11px] uppercase tracking-widest text-[#a1a1aa]">Timestamped agent reasoning</p>
      <p className="mt-2 whitespace-pre-wrap border-l border-[#27272a] pl-3 font-mono text-[14px] leading-relaxed text-[#e4e4e7]">{node.reasoning || '// no reasoning recorded'}</p>
      {defendButton}
    </section>
  }

  return <section className="p-5">
    <div className="mb-4 flex items-center justify-between">
      <span className="flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.2em] text-[#e4e4e7]"><Database size={15} />03 // Node inspector</span>
      <span className="font-mono text-[11px] uppercase tracking-widest text-[#a1a1aa]">{node ? 'Selected' : 'No target'}</span>
    </div>
    {node ? <>
      <div className="border-l border-[#e4e4e7] pl-3">
        <p className="font-mono text-[12px] tracking-widest text-[#a1a1aa]">{node.id}</p>
        <h2 className="mt-1 text-xl font-medium text-[#e4e4e7]">{node.name}</h2>
        <p className={`mt-1 font-mono text-[11px] uppercase tracking-widest ${node.status === 'COMPROMISED' ? 'text-[#ff4444]' : 'text-[#a1a1aa]'}`}>{node.type} // {node.status}</p>
      </div>
      <div className="mt-5">
        <StatRow label={`Architectural centrality · ${centralitySource}`} value={Number.isFinite(centrality) ? centrality.toFixed(2) : '0.00'} accent={node.status === 'COMPROMISED' ? 'text-[#ff4444]' : 'text-[#e4e4e7]'} />
        <CentralityBar value={centrality} compromised={node.status === 'COMPROMISED'} />
        <div className="mt-3"><StatRow label={`PageRank · ${pagerankSource}`} value={Number.isFinite(pagerank) ? pagerank.toFixed(2) : '0.00'} /></div>
      </div>
      <p className="mt-3 font-mono text-[10px] uppercase tracking-widest text-[#a1a1aa]">{computedLive ? 'Derived from live graph topology' : 'Seeded architectural risk baseline (not live analytics)'}</p>
      {defendButton}
    </> : <div className="grid min-h-[180px] place-items-center text-center font-mono text-[12px] uppercase tracking-widest text-[#a1a1aa]">
      <span><ChevronRight className="mx-auto mb-2" size={15} />Select a graph node<br />to inspect telemetry</span>
    </div>}
  </section>
}

function formatTimestamp(timestamp) {
  const parsed = new Date(timestamp)
  return Number.isNaN(parsed.getTime()) ? '--:--:--' : parsed.toLocaleTimeString()
}

function agentTone(agent) {
  if (agent === 'RED') return 'text-[#ff4444]'
  if (agent === 'BLUE') return 'text-[#3b82f6]'
  return 'text-[#a1a1aa]'
}

function agentBorder(agent) {
  if (agent === 'RED') return 'border-[#ff4444]'
  if (agent === 'BLUE') return 'border-[#3b82f6]'
  return 'border-[#27272a]'
}

function decisionTone(source) {
  if (source === 'openai') return 'text-[#e4e4e7]'
  if (source === 'fallback') return 'text-[#a1a1aa]'
  return 'text-[#71717a]'
}

function Feed({ events, feedRef }) {
  return <section className="flex min-h-[260px] flex-1 flex-col">
    <div className="flex items-center justify-between border-b border-[#27272a] px-5 py-3">
      <span className="flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.2em] text-[#e4e4e7]"><Terminal size={15} />04 // Agent cognitive feed</span>
      <span className="font-mono text-[11px] uppercase tracking-widest text-[#a1a1aa]">{events.length} events</span>
    </div>
    <div ref={feedRef} className="max-h-[420px] flex-1 space-y-4 overflow-y-auto p-5 font-mono text-[13px] leading-relaxed">
      {events.length ? events.map((event, index) => (
        <div key={`${event.timestamp ?? 'event'}-${index}`} className={`border-l pl-3 ${agentBorder(event.agent)}`}>
          <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-widest">
            <span className={agentTone(event.agent)}>[{event.agent ?? 'SYS'}]</span>
            <time className="text-[#a1a1aa]">{formatTimestamp(event.timestamp)}</time>
            {event.type && <span className="text-[#a1a1aa]">{event.type}</span>}
            {event.decision_source && <span className={decisionTone(event.decision_source)}>{event.decision_source.toUpperCase()}</span>}
          </div>
          <p className="mt-1 text-[#e4e4e7]">{event.message}</p>
          {event.reasoning && event.reasoning !== event.message && <p className="mt-1 text-[#a1a1aa]">{event.reasoning}</p>}
        </div>
      )) : <p className="text-[#a1a1aa]">// Awaiting agent telemetry...</p>}
    </div>
  </section>
}

function SwarmToggle({ isSwarmActive, busy, onToggleSwarm }) {
  const SWARM_IDLE = 'border border-[#27272a] text-[#71717a] hover:text-[#e4e4e7] hover:border-[#e4e4e7] font-mono text-[11px] tracking-widest uppercase px-4 py-2 transition-colors'
  const SWARM_ACTIVE = 'border border-[#ff4444] bg-[#ff4444]/10 text-[#ff4444] font-mono text-[11px] tracking-widest uppercase px-4 py-2 animate-pulse'
  return <button
    type="button"
    disabled={busy}
    aria-pressed={isSwarmActive}
    onClick={onToggleSwarm}
    className={`${isSwarmActive ? SWARM_ACTIVE : SWARM_IDLE} disabled:pointer-events-none disabled:opacity-40`}
  >
    {isSwarmActive ? '[DISENGAGE SWARM] ACTIVE' : '[ENGAGE AUTONOMOUS SWARM]'}
  </button>
}

function ControlDeck({ busy, onCommand, defcon, pollRate, isSwarmActive, onToggleSwarm }) {
  return <section className="grid grid-cols-1 gap-3 border-t border-[#27272a] p-4 sm:grid-cols-2 xl:grid-cols-[repeat(4,minmax(0,1fr))_auto] xl:items-stretch">
    <button disabled={busy} onClick={() => onCommand('/api/red/step')} className={RED_BTN}><Skull size={15} />Step red attack</button>
    <button disabled={busy} onClick={() => onCommand('/api/blue/defend')} className={BLUE_BTN}><Shield size={15} />Engage blue defense</button>
    <button disabled={busy} onClick={() => onCommand('/api/reset')} className={BTN}><RotateCcw size={13} />Reset topology</button>
    <SwarmToggle isSwarmActive={isSwarmActive} busy={busy} onToggleSwarm={onToggleSwarm} />
    <div className="flex items-center justify-between gap-6 border border-[#27272a] px-4 py-3 font-mono text-[9px] uppercase tracking-widest text-[#71717a] xl:justify-end">
      <span className="text-right"><b className={`block text-[11px] ${compromisedTone(defcon)}`}>{defcon}</b>Threat level</span>
      <span className="text-right"><b className="block text-[11px] text-[#e4e4e7]">{pollRate}</b>Poll rate</span>
    </div>
  </section>
}

function compromisedTone(defcon) {
  if (defcon === 'DEFCON 2') return 'text-[#ff4444]'
  if (defcon === 'DEFCON 3') return 'text-[#e4e4e7]'
  return 'text-[#71717a]'
}

export default App

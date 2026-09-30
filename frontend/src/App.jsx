import { useEffect, useRef, useState } from 'react'
import { Activity, AlertTriangle, ChevronRight, Database, LockKeyhole, RotateCcw, Shield, Skull, Terminal } from 'lucide-react'
import Graph from './components/Graph'
import './App.css'

const API = 'http://localhost:8000'
const emptyGraph = { nodes: [], edges: [] }

function App() {
  const [graph, setGraph] = useState(emptyGraph)
  const [feed, setFeed] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [connected, setConnected] = useState(false)
  const [busy, setBusy] = useState(false)
  const [qps, setQps] = useState('0.0')
  const feedRef = useRef(null)
  const requestsRef = useRef([])

  const refresh = async () => {
    const now = Date.now()
    requestsRef.current = [...requestsRef.current.filter((stamp) => now - stamp < 1000), now]
    setQps(requestsRef.current.length.toFixed(1))
    try {
      const [graphResponse, feedResponse] = await Promise.all([fetch(`${API}/api/graph`), fetch(`${API}/api/feed`)] )
      if (!graphResponse.ok || !feedResponse.ok) throw new Error('Telemetry unavailable')
      const nextGraph = await graphResponse.json()
      setGraph(nextGraph)
      setFeed(await feedResponse.json())
      setConnected(true)
      setSelectedNode((current) => current ? nextGraph.nodes.find((node) => node.id === current.id) || null : null)
    } catch {
      setConnected(false)
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 1500)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (feedRef.current) feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [feed])

  const command = async (path) => {
    setBusy(true)
    try {
      const response = await fetch(`${API}${path}`, { method: 'POST' })
      if (!response.ok) throw new Error('Command rejected')
      await refresh()
    } finally {
      setBusy(false)
    }
  }

  const compromised = graph.nodes.filter((node) => node.status === 'COMPROMISED').length
  const defcon = compromised > 1 ? 'DEFCON 2' : compromised ? 'DEFCON 3' : 'DEFCON 5'

  return <main className="min-h-screen bg-[#02060d] text-slate-300 selection:bg-cyan-400/20">
    <header className="mx-auto flex max-w-[1600px] items-center justify-between border-b border-cyan-950/70 px-5 py-4 lg:px-8">
      <div className="flex items-center gap-3"><div className="border border-cyan-700/70 p-2 text-cyan-300 shadow-[0_0_22px_rgba(34,211,238,.18)]"><Shield size={21} /></div><div><h1 className="text-sm font-semibold tracking-[.25em] text-slate-100">AEGIS SWARM</h1><p className="font-mono text-[9px] tracking-[.22em] text-slate-500">AUTONOMOUS GRAPH IMMUNE SYSTEM</p></div></div>
      <div className="hidden items-center gap-5 font-mono text-[10px] uppercase tracking-widest md:flex"><span className="flex items-center gap-2 text-slate-500"><i className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-cyan-400 shadow-[0_0_8px_#22d3ee]' : 'bg-rose-500'}`} />{connected ? 'FalkorDB linked' : 'Link offline'}</span><span className="text-slate-600">Node 01 / Sector 7</span></div>
    </header>

    <div className="mx-auto max-w-[1600px] px-5 lg:px-8"><section className="flex items-center gap-3 border-b border-rose-950/60 py-3 font-mono text-[10px] uppercase tracking-[.17em] text-rose-400"><AlertTriangle size={14} /><span>Threat posture: {compromised ? 'active breach detected' : 'monitoring active'}</span><span className="ml-auto text-slate-600">{graph.nodes.length} assets / {graph.edges.length} links</span></section>
      <section className="grid grid-cols-1 gap-4 border-b border-cyan-950/70 py-5 lg:grid-cols-[minmax(0,7fr)_minmax(290px,3fr)]">
        <div className="min-w-0"><div className="mb-3 flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.2em] text-cyan-400"><Activity size={14} />Live attack graph</span><span className="font-mono text-[9px] uppercase tracking-widest text-slate-600">Radial topology / {graph.nodes.length ? 'streaming' : 'awaiting'}</span></div><div className="h-130 lg:h-162.5"><Graph graph={graph} selectedNode={selectedNode} onSelectNode={setSelectedNode} /></div></div>
        <aside className="flex min-h-130 flex-col gap-4 lg:min-h-0"><Inspector node={selectedNode} onSever={() => command('/api/blue/defend')} disabled={busy || !connected} /><Feed events={feed} feedRef={feedRef} /></aside>
      </section>
      <ControlDeck busy={busy || !connected} onCommand={command} defcon={defcon} qps={qps} />
    </div>
    <footer className="mx-auto flex max-w-[1600px] justify-between px-5 py-4 font-mono text-[9px] uppercase tracking-widest text-slate-600 lg:px-8"><span>AEGIS // FALKORDB SHARED-STATE BLACKBOARD</span><span>Encrypted telemetry <i className="ml-2 inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" /></span></footer>
  </main>
}

function Inspector({ node, onSever, disabled }) {
  return <section className="border border-cyan-950/70 bg-[#050d15]/90 p-4"><div className="mb-5 flex items-center justify-between"><span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.2em] text-slate-200"><Database size={14} className="text-cyan-400" />Node inspector</span><span className="font-mono text-[9px] text-slate-600">{node ? 'SELECTED' : 'NO TARGET'}</span></div>{node ? <><div className="mb-5 border-l-2 border-cyan-400 pl-3"><p className="font-mono text-[10px] text-cyan-400">{node.id}</p><h2 className="mt-1 text-lg font-medium text-slate-100">{node.name}</h2><p className="mt-1 font-mono text-[9px] uppercase tracking-widest text-slate-500">{node.type} // {node.status}</p></div><Score label="BETWEENNESS CENTRALITY" value={node.centrality} /><div className="mt-4 flex items-end justify-between border-t border-cyan-950/70 pt-4"><span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">PageRank score</span><strong className="font-mono text-xl text-cyan-300">{Number(node.pagerank).toFixed(2)}</strong></div><button onClick={onSever} disabled={disabled} className="mt-5 flex w-full items-center justify-center gap-2 border border-rose-800/70 bg-rose-950/20 py-3 font-mono text-[10px] uppercase tracking-widest text-rose-400 transition hover:bg-rose-900/30 disabled:cursor-not-allowed disabled:opacity-40"><LockKeyhole size={14} /> Sever edge</button></> : <div className="grid min-h-45 place-items-center text-center font-mono text-[10px] uppercase tracking-widest text-slate-600"><span><ChevronRight className="mx-auto mb-2 text-cyan-700" />Select a graph node<br />to inspect telemetry</span></div>}</section>
}

function Score({ label, value }) { return <div><div className="mb-2 flex justify-between font-mono text-[9px] uppercase tracking-widest text-slate-500"><span>{label}</span><span className="text-cyan-300">{Number(value).toFixed(2)}</span></div><div className="h-1 bg-slate-800"><div className="h-full bg-cyan-400 shadow-[0_0_10px_#22d3ee]" style={{ width: `${Math.min(Number(value) * 100, 100)}%` }} /></div></div> }

function Feed({ events, feedRef }) { return <section className="flex min-h-62.5 flex-1 flex-col border border-cyan-950/70 bg-[#030a11]"><div className="flex items-center justify-between border-b border-cyan-950/70 px-4 py-3"><span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[.2em] text-slate-200"><Terminal size={14} className="text-cyan-400" />Agent cognitive feed</span><span className="font-mono text-[9px] text-slate-600">{events.length} events</span></div><div ref={feedRef} className="flex-1 space-y-3 overflow-y-auto p-4 font-mono text-[10px] leading-relaxed">{events.length ? events.map((event, index) => <div key={`${event.timestamp}-${index}`} className="border-l border-cyan-900/70 pl-3"><div className="flex gap-2 text-[9px]"><span className={event.agent === 'RED' ? 'text-rose-400' : event.agent === 'BLUE' ? 'text-cyan-400' : 'text-amber-400'}>[{event.agent}]</span><time className="text-slate-600">{new Date(event.timestamp).toLocaleTimeString()}</time></div><p className="mt-1 text-slate-400">{event.message}</p></div>) : <p className="text-slate-600">// Awaiting agent telemetry...</p>}</div></section> }

function ControlDeck({ busy, onCommand, defcon, qps }) { return <section className="grid gap-3 border-x border-b border-cyan-950/70 bg-[#050d15] p-4 md:grid-cols-[1fr_1fr_1fr_auto] md:items-center"><button disabled={busy} onClick={() => onCommand('/api/red/step')} className="flex items-center justify-center gap-2 border border-rose-800/70 bg-rose-950/20 px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-rose-400 transition hover:bg-rose-900/30 disabled:opacity-40"><Skull size={15} />Step red attack</button><button disabled={busy} onClick={() => onCommand('/api/blue/defend')} className="flex items-center justify-center gap-2 border border-cyan-700/70 bg-cyan-950/20 px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-cyan-300 transition hover:bg-cyan-900/30 disabled:opacity-40"><Shield size={15} />Engage blue defense</button><button disabled={busy} onClick={() => onCommand('/api/reset')} className="flex items-center justify-center gap-2 border border-slate-700 px-4 py-3 font-mono text-[10px] uppercase tracking-widest text-slate-400 transition hover:bg-slate-800 disabled:opacity-40"><RotateCcw size={14} />Reset topology</button><div className="flex justify-end gap-5 font-mono text-[9px] uppercase tracking-widest text-slate-500"><span><b className="block text-rose-400">{defcon}</b>Threat level</span><span><b className="block text-cyan-300">{qps}</b>Cypher QPS</span></div></section> }

export default App

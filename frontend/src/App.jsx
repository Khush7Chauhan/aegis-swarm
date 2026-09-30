import { useEffect, useState } from 'react'
import { Activity, AlertTriangle, Bot, Database, LockKeyhole, Network, Play, Radio, RotateCcw, ShieldCheck, Skull, Zap } from 'lucide-react'
import './App.css'

const API = 'http://localhost:8000/api'
const positions = { internet: [8, 50], vpn: [25, 23], web: [25, 76], identity: [47, 17], workstation: [47, 50], api: [47, 83], jump: [69, 29], database: [88, 50] }

const initialGraph = { nodes: [], edges: [] }

function App() {
  const [graph, setGraph] = useState(initialGraph)
  const [feed, setFeed] = useState([])
  const [busy, setBusy] = useState(false)
  const [connected, setConnected] = useState(false)
  const [lastAction, setLastAction] = useState('Awaiting telemetry')

  const refresh = async () => {
    try {
      const [graphResponse, feedResponse] = await Promise.all([fetch(`${API}/graph`), fetch(`${API}/feed`)] )
      if (!graphResponse.ok) throw new Error('API unavailable')
      setGraph(await graphResponse.json())
      setFeed(await feedResponse.json())
      setConnected(true)
    } catch {
      setConnected(false)
    }
  }

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [])

  const act = async (path, label) => {
    setBusy(true)
    try {
      const response = await fetch(`${API}${path}`, { method: 'POST' })
      if (!response.ok) throw new Error('Action failed')
      const payload = await response.json()
      setGraph(payload.graph || payload)
      setLastAction(payload.message || label)
      await refresh()
    } catch {
      setLastAction('Action unavailable: connect to the command API')
    } finally {
      setBusy(false)
    }
  }

  const compromised = graph.nodes.filter((node) => node.status === 'COMPROMISED').length
  const isolated = graph.nodes.filter((node) => node.status === 'ISOLATED').length

  return (
    <main className="console-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark"><ShieldCheck size={22} /></div><div><strong>AEGIS SWARM</strong><span>AUTONOMOUS GRAPH IMMUNE SYSTEM</span></div></div>
        <div className="header-status"><span className={`status-dot ${connected ? 'online' : ''}`} /> {connected ? 'FALKORDB LINKED' : 'LINK OFFLINE'} <span className="divider" /> <span className="mono">NODE 01 / SECTOR 7</span></div>
      </header>

      <section className="alert-strip"><AlertTriangle size={15} /><span>TACTICAL MONITORING ACTIVE</span><b>{compromised ? `${compromised} ASSETS COMPROMISED` : 'NO ACTIVE BREACHES'}</b><span className="alert-line" /></section>

      <section className="dashboard-grid">
        <aside className="side-panel left-panel">
          <PanelTitle icon={<Activity size={15} />} title="Mission telemetry" />
          <div className="metric-grid"><Metric value={graph.nodes.length || '--'} label="ASSETS" /><Metric value={graph.edges.length || '--'} label="LINKS" /><Metric value={compromised} label="BREACHED" danger /><Metric value={isolated} label="ISOLATED" /></div>
          <div className="section-label">AGENT STATUS</div>
          <AgentRow icon={<Skull size={16} />} name="RED / ATTACKER" state={compromised ? 'INTRUSION ACTIVE' : 'STANDBY'} danger />
          <AgentRow icon={<ShieldCheck size={16} />} name="BLUE / SENTINEL" state="AUTONOMOUS DEFENSE" />
          <div className="section-label">SYSTEM SIGNAL</div>
          <div className="signal-row"><span>GRAPH CONSISTENCY</span><b>99.8%</b></div><div className="signal-track"><i /></div>
          <div className="signal-row"><span>DEFENSE READINESS</span><b className="cyan">OPTIMAL</b></div><div className="signal-track cyan-track"><i /></div>
        </aside>

        <section className="network-panel">
          <div className="panel-heading"><PanelTitle icon={<Network size={15} />} title="Live attack graph" /><span className="live-label"><span className="pulse" /> LIVE TOPOLOGY</span></div>
          <div className="graph-canvas">
            <div className="scanline" />
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Enterprise network topology">
              {graph.edges.map((edge) => { const start = positions[edge.source]; const end = positions[edge.target]; return start && end ? <line key={`${edge.source}-${edge.target}`} x1={start[0]} y1={start[1]} x2={end[0]} y2={end[1]} className={`edge ${edge.status === 'ATTACK_VECTOR' ? 'attack-edge' : edge.status === 'ISOLATED' ? 'isolated-edge' : ''}`} /> : null })}
            </svg>
            {graph.nodes.map((node) => { const pos = positions[node.id] || [50, 50]; const isDb = node.type === 'DATABASE'; return <div key={node.id} className={`node ${node.status.toLowerCase()} ${isDb ? 'crown-jewel' : ''}`} style={{ left: `${pos[0]}%`, top: `${pos[1]}%` }}><div className="node-core">{isDb ? <Database size={16} /> : node.status === 'COMPROMISED' ? <AlertTriangle size={15} /> : <div className="node-glyph" />}</div><span>{node.name}</span><small>{node.status}</small></div> })}
            {!graph.nodes.length && <div className="graph-empty"><Radio size={24} />Waiting for FalkorDB telemetry</div>}
          </div>
          <div className="graph-legend"><span><i className="legend-dot healthy" /> HEALTHY</span><span><i className="legend-dot breach" /> COMPROMISED</span><span><i className="legend-line" /> ATTACK VECTOR</span><span className="coordinates">X: 42.018 / Y: 77.442</span></div>
        </section>

        <aside className="side-panel right-panel">
          <PanelTitle icon={<Zap size={15} />} title="Command deck" />
          <p className="command-copy">Direct agent control. Each action mutates the shared graph state.</p>
          <button className="command-button red-button" disabled={busy || !connected} onClick={() => act('/red/step', 'Red advanced one hop')}><Skull size={17} /><span><b>RED AGENT</b><small>EXECUTE NEXT INTRUSION HOP</small></span><Play size={15} /></button>
          <button className="command-button blue-button" disabled={busy || !connected} onClick={() => act('/blue/defend', 'Blue deployed defense')}><ShieldCheck size={17} /><span><b>BLUE SENTINEL</b><small>IDENTIFY & SEVER CHOKEPOINT</small></span><Play size={15} /></button>
          <button className="reset-button" disabled={busy || !connected} onClick={() => act('/reset', 'Topology reset')}><RotateCcw size={14} /> RESET SIMULATION</button>
          <div className="action-result"><span>LAST ACTION</span><p>{lastAction}</p></div>
          <div className="lock-note"><LockKeyhole size={14} /> MUTATIONS REQUIRE ACTIVE LINK</div>
        </aside>
      </section>

      <section className="feed-panel"><div className="feed-header"><PanelTitle icon={<Bot size={15} />} title="Agent reasoning feed" /><span className="mono">{feed.length} EVENTS / CHRONOLOGICAL</span></div><div className="feed-list">{feed.slice().reverse().slice(0, 6).map((event, index) => <div className="feed-event" key={`${event.timestamp}-${index}`}><span className={`agent-tag ${event.agent.toLowerCase()}`}>{event.agent}</span><time>{new Date(event.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</time><p>{event.message}</p><span className={`event-type ${event.type.toLowerCase()}`}>{event.type}</span></div>)}{!feed.length && <div className="feed-empty">No agent events received.</div>}</div></section>
      <footer><span>AEGIS SWARM // FALKORDB SHARED-STATE BLACKBOARD</span><span className="mono">ENCRYPTED TELEMETRY CHANNEL <span className="status-dot online" /></span></footer>
    </main>
  )
}

function PanelTitle({ icon, title }) { return <div className="panel-title">{icon}<span>{title}</span></div> }
function Metric({ value, label, danger }) { return <div className={`metric ${danger ? 'danger' : ''}`}><strong>{value}</strong><span>{label}</span></div> }
function AgentRow({ icon, name, state, danger }) { return <div className="agent-row">{icon}<div><b>{name}</b><span className={danger ? 'red' : 'cyan'}>{state}</span></div><span className={`agent-indicator ${danger ? 'red-bg' : ''}`} /></div> }

export default App

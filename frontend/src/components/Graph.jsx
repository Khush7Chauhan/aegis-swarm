import { Database, Globe2, Network, Server, ShieldAlert } from 'lucide-react'

const layers = {
  Internet: [{ x: 95, y: 350 }],
  Gateway: [{ x: 290, y: 245 }, { x: 290, y: 455 }],
  Microservice: [{ x: 510, y: 205 }, { x: 510, y: 495 }],
  Database: [{ x: 760, y: 350 }],
}

const fallbackPositions = { 'gw-1': [95, 350], 'web-1': [290, 350], 'api-billing': [510, 205], 'api-users': [510, 495], 'db-core': [760, 350] }

function nodePosition(node, index) {
  if (fallbackPositions[node.id]) return fallbackPositions[node.id]
  const layer = layers[node.type] || layers.Microservice
  const point = layer[index % layer.length]
  return [point.x, point.y]
}

function NodeIcon({ type, compromised }) {
  if (compromised) return <ShieldAlert size={19} />
  if (type === 'Internet') return <Globe2 size={19} />
  if (type === 'Database') return <Database size={19} />
  if (type === 'Gateway') return <Network size={19} />
  return <Server size={19} />
}

export default function Graph({ graph, onSelectNode, selectedNode }) {
  const positions = Object.fromEntries(graph.nodes.map((node, index) => [node.id, nodePosition(node, index)]))

  return (
    <div className="relative h-full min-h-130 overflow-hidden rounded-sm border border-cyan-950/70 bg-[#030b13] tactical-grid">
      <div className="scanline pointer-events-none z-10" />
      <div className="absolute left-5 top-4 z-10 font-mono text-[10px] uppercase tracking-[0.24em] text-cyan-500/70">Autonomous attack surface // graph projection</div>
      <div className="absolute bottom-4 left-5 z-10 flex gap-4 font-mono text-[9px] uppercase tracking-widest text-slate-500">
        <span><i className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" />Healthy</span>
        <span><i className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-rose-500" />Compromised</span>
        <span><i className="mr-1 inline-block h-3 w-5 border-t border-dashed border-rose-500" />Severed</span>
      </div>
      <svg viewBox="0 0 850 700" className="absolute inset-0 h-full w-full" role="img" aria-label="Radial enterprise attack graph">
        <defs>
          <filter id="bloom-cyan" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="4" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <filter id="bloom-red" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="5" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
          <radialGradient id="core-halo"><stop offset="0" stopColor="#22d3ee" stopOpacity=".2" /><stop offset="1" stopColor="#22d3ee" stopOpacity="0" /></radialGradient>
        </defs>
        <circle cx="760" cy="350" r="140" fill="url(#core-halo)" />
        <circle cx="760" cy="350" r="94" fill="none" stroke="#164e63" strokeDasharray="2 9" opacity=".8" />
        {graph.edges.map((edge) => {
          const source = positions[edge.source]
          const target = positions[edge.target]
          if (!source || !target) return null
          const severed = edge.status === 'SEVERED'
          const attack = edge.status === 'ATTACK_VECTOR'
          return <line key={`${edge.source}-${edge.target}`} x1={source[0]} y1={source[1]} x2={target[0]} y2={target[1]} stroke={severed || attack ? '#f43f5e' : '#155e75'} strokeWidth={attack ? 3 : 1.5} strokeDasharray={severed || attack ? '8 7' : undefined} className={attack ? 'dash-flow' : ''} opacity={severed ? .8 : 1} filter={attack ? 'url(#bloom-red)' : undefined} />
        })}
        {graph.nodes.map((node, index) => {
          const [x, y] = positions[node.id]
          const compromised = node.status === 'COMPROMISED'
          const selected = selectedNode?.id === node.id
          return <g key={node.id} transform={`translate(${x} ${y})`} className="cursor-pointer" onClick={() => onSelectNode(node)}>
            {compromised && <circle r="34" fill="none" stroke="#f43f5e" strokeWidth="2" opacity=".8" className="animate-ping" />}
            <circle r={selected ? 28 : 23} fill="#06141d" stroke={compromised ? '#f43f5e' : '#22d3ee'} strokeWidth={selected ? 3 : 1.5} filter={`url(#${compromised ? 'bloom-red' : 'bloom-cyan'})`} />
            <foreignObject x="-12" y="-12" width="24" height="24" className={compromised ? 'text-rose-400' : 'text-cyan-300'}><div className="grid h-full place-items-center"><NodeIcon type={node.type} compromised={compromised} /></div></foreignObject>
            <text y="42" textAnchor="middle" className="fill-slate-200 text-[12px] font-medium">{node.name}</text>
            <text y="57" textAnchor="middle" className={`font-mono text-[9px] uppercase tracking-widest ${compromised ? 'fill-rose-400' : 'fill-slate-500'}`}>{node.status}</text>
            {index === 0 && <text x="-10" y="-39" textAnchor="middle" className="fill-slate-600 font-mono text-[9px] uppercase tracking-[.2em]">Ingress</text>}
          </g>
        })}
      </svg>
      {!graph.nodes.length && <div className="absolute inset-0 grid place-items-center font-mono text-xs uppercase tracking-widest text-slate-600">Awaiting graph telemetry</div>}
      <div className="absolute right-5 top-4 z-10 font-mono text-[9px] uppercase tracking-widest text-slate-600">X 42.018 / Y 77.442</div>
    </div>
  )
}

const layers = {
  Internet: [{ x: 95, y: 350 }],
  Gateway: [{ x: 290, y: 245 }, { x: 290, y: 455 }],
  Microservice: [{ x: 510, y: 205 }, { x: 510, y: 495 }],
  Database: [{ x: 760, y: 350 }],
}

const fallbackPositions = { 'gw-1': [95, 350], 'web-1': [290, 350], 'api-billing': [510, 205], 'api-users': [510, 495], 'db-core': [760, 350] }

const INK = '#e4e4e7'
const MUTED = '#71717a'
const FAINT = '#3f3f46'
const RED = '#ff4444'
const BLUE = '#3b82f6'
const AMBER = '#d97706'
const MEMORY = '#a1a1aa'

// Derived visual states. The backend never lies: a node stays `COMPROMISED`
// once Red infects it. The UI, however, reads each node's topological context
// so an isolated (contained) threat no longer reads as an active failure.
const NODE_STATES = {
  HEALTHY: {
    label: 'HEALTHY',
    point: '#ffffff',
    accent: MUTED,
    labelColor: '#a1a1aa',
    radius: 5,
    pointOpacity: 1,
    bracket: false,
    animated: false,
    warning: null,
  },
  COMPROMISED: {
    label: 'COMPROMISED',
    point: RED,
    accent: RED,
    labelColor: RED,
    radius: 7,
    pointOpacity: 1,
    bracket: true,
    animated: true,
    warning: null,
  },
  QUARANTINED: {
    label: 'QUARANTINED',
    point: AMBER,
    accent: AMBER,
    labelColor: AMBER,
    radius: 6,
    pointOpacity: 0.6,
    bracket: true,
    animated: false,
    warning: null,
  },
  ERR_BREACH: {
    label: 'COMPROMISED',
    point: RED,
    accent: RED,
    labelColor: RED,
    radius: 7,
    pointOpacity: 1,
    bracket: true,
    animated: true,
    warning: '[CRITICAL_BREACH]',
  },
}

function nodePosition(node, index) {
  if (fallbackPositions[node.id]) return fallbackPositions[node.id]
  const layer = layers[node.type] || layers.Microservice
  const point = layer[index % layer.length]
  return [point.x, point.y]
}

// Four corner ticks forming strict square brackets [ ].
function bracketPath(half, len) {
  const s = half
  const l = len
  return [
    `M ${-s} ${-s + l} L ${-s} ${-s} L ${-s + l} ${-s}`,
    `M ${s - l} ${-s} L ${s} ${-s} L ${s} ${-s + l}`,
    `M ${s} ${s - l} L ${s} ${s} L ${s - l} ${s}`,
    `M ${-s + l} ${s} L ${-s} ${s} L ${-s} ${s - l}`,
  ].join(' ')
}

// Instrument crosshair marking a precise lidar data point.
function Crosshair({ size = 11, color = MUTED }) {
  return <g stroke={color} strokeWidth={0.5} opacity={0.75}>
    <line x1={-size} y1={0} x2={-5} y2={0} />
    <line x1={5} y1={0} x2={size} y2={0} />
    <line x1={0} y1={-size} x2={0} y2={-5} />
    <line x1={0} y1={5} x2={0} y2={size} />
  </g>
}

export default function Graph({ graph, onSelectNode, selectedNode, showMemory = false }) {
  const nodes = Array.isArray(graph?.nodes) ? graph.nodes : []
  const edges = Array.isArray(graph?.edges) ? graph.edges : []

  // IncidentReport nodes are memory annotation, not physical topology: keep
  // them out of the structural layout so the existing geometry is untouched.
  const coreNodes = nodes.filter((node) => node.type !== 'IncidentReport')
  const memoryNodes = showMemory ? nodes.filter((node) => node.type === 'IncidentReport') : []
  const structuralEdges = edges.filter((edge) => edge.status !== 'MEMORY_LINK')
  const memoryLinks = showMemory ? edges.filter((edge) => edge.status === 'MEMORY_LINK') : []
  const severedCount = structuralEdges.filter((edge) => edge.status === 'SEVERED').length

  const positions = Object.fromEntries(coreNodes.map((node, index) => [node.id, nodePosition(node, index)]))

  // Topological context: outbound edge statuses per source node.
  const outboundStatuses = {}
  structuralEdges.forEach((edge) => {
    if (!outboundStatuses[edge.source]) outboundStatuses[edge.source] = []
    outboundStatuses[edge.source].push(edge.status)
  })

  // DERIVED VISUAL STATE -- computed purely from node status + outbound edges.
  // 1. HEALTHY      : node is not compromised.
  // 2. ERR_BREACH   : the crown-jewel Database is compromised.
  // 3. QUARANTINED  : compromised, but every outbound edge is severed.
  // 4. COMPROMISED  : compromised, with at least one active/attack outbound.
  const deriveNodeState = (node) => {
    if (node.status !== 'COMPROMISED') return 'HEALTHY'
    if (node.type === 'Database') return 'ERR_BREACH'
    const outbound = outboundStatuses[node.id] || []
    const hasActiveOutbound = outbound.some((status) => status === 'ACTIVE' || status === 'ATTACK_VECTOR')
    return hasActiveOutbound ? 'COMPROMISED' : 'QUARANTINED'
  }

  // Anchor each memory node to the compromised node it was generated from.
  const memoryParents = {}
  memoryLinks.forEach((edge) => { memoryParents[edge.target] = edge.source })
  const siblingCount = {}
  const memoryPositions = {}
  memoryNodes.forEach((node) => {
    const base = positions[memoryParents[node.id]]
    if (!base) return
    const index = siblingCount[memoryParents[node.id]] ?? 0
    siblingCount[memoryParents[node.id]] = index + 1
    const angle = -Math.PI / 2 + index * (Math.PI / 3.5)
    const radius = 66 + (index % 2) * 18
    const x = Math.min(812, Math.max(38, base[0] + radius * Math.cos(angle)))
    const y = Math.min(652, Math.max(34, base[1] + radius * Math.sin(angle)))
    memoryPositions[node.id] = [x, y]
  })

  const select = (node) => { if (typeof onSelectNode === 'function') onSelectNode(node) }

  return (
    <div className="lidar-grid relative h-full min-h-[520px] overflow-hidden">
      <div className="scan-field pointer-events-none absolute inset-0" />

      <div className="pointer-events-none absolute left-4 top-3 z-10 font-mono text-[9px] uppercase tracking-[0.22em] text-[#71717a]">Fig. 02 // Topology point cloud</div>
      <div className="pointer-events-none absolute right-4 top-3 z-10 space-y-1 text-right font-mono text-[9px] uppercase tracking-[0.22em] text-[#71717a]">
        <div>Scan 01 / 000%</div>
        <div>Yaw 036 / Pitch 32</div>
      </div>

      <div className="pointer-events-none absolute bottom-3 left-4 z-10 flex flex-wrap gap-4 font-mono text-[9px] uppercase tracking-widest text-[#71717a]">
        <span><i className="mr-1 inline-block h-1.5 w-1.5 bg-white align-middle" />Healthy</span>
        <span><i className="mr-1 inline-block h-1.5 w-1.5 bg-[#ff4444] align-middle" />Compromised</span>
        <span><i className="mr-1 inline-block h-1.5 w-1.5 bg-[#d97706] align-middle" />Quarantined</span>
        <span><i className="mr-1 inline-block h-3 w-4 border-t border-dashed border-[#3b82f6] align-middle" />Severed</span>
        <span><i className="mr-1 inline-block h-3 w-4 border-t-2 border-[#ff4444] align-middle" />Attack vector</span>
        {showMemory && <span><i className="mr-1 inline-block h-1.5 w-1.5 border border-[#a1a1aa] align-middle" />Memory</span>}
      </div>

      <svg viewBox="0 0 850 700" className="absolute inset-0 h-full w-full" role="img" aria-label="Architectural lidar point cloud of the enterprise attack surface">
        {structuralEdges.map((edge, index) => {
          const source = positions[edge.source]
          const target = positions[edge.target]
          if (!source || !target) return null
          const severed = edge.status === 'SEVERED'
          const attack = edge.status === 'ATTACK_VECTOR'
          const stroke = severed ? BLUE : attack ? RED : INK
          return <line
            key={`${edge.source}-${edge.target}-${index}`}
            x1={source[0]} y1={source[1]} x2={target[0]} y2={target[1]}
            stroke={stroke}
            strokeWidth={attack ? 0.9 : severed ? 0.6 : 0.5}
            strokeOpacity={severed ? 0.6 : attack ? 0.85 : 0.4}
            strokeDasharray={severed ? '2 4' : undefined}
          />
        })}

        {memoryLinks.map((edge, index) => {
          const source = positions[edge.source]
          const target = memoryPositions[edge.target]
          if (!source || !target) return null
          return <line
            key={`memory-${edge.source}-${edge.target}-${index}`}
            x1={source[0]} y1={source[1]} x2={target[0]} y2={target[1]}
            stroke={FAINT} strokeWidth={0.5} strokeDasharray="2 3" strokeOpacity={0.9}
          />
        })}

        {coreNodes.map((node) => {
          const position = positions[node.id]
          if (!position) return null
          const [x, y] = position
          const stateName = deriveNodeState(node)
          const visual = NODE_STATES[stateName]
          const selected = selectedNode?.id === node.id
          const ingress = node.type === 'Internet'
          return <g
            key={node.id}
            transform={`translate(${x} ${y})`}
            className="cursor-pointer outline-none"
            role="button" tabIndex={0}
            aria-label={`Inspect ${node.name}: ${visual.label}`}
            aria-pressed={selected}
            onClick={() => select(node)}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(node) } }}
          >
            {visual.bracket && (visual.animated
              ? <g className="breach-bracket"><path d={bracketPath(20, 9)} fill="none" stroke={visual.accent} strokeWidth={0.75} /></g>
              : <path d={bracketPath(20, 9)} fill="none" stroke={visual.accent} strokeWidth={0.75} opacity={0.85} />)}
            {selected && <path d={bracketPath(16, 6)} fill="none" stroke={INK} strokeWidth={0.75} />}
            <Crosshair size={11} color={visual.accent} />
            <circle r={visual.radius} fill={visual.point} opacity={visual.pointOpacity} className={visual.animated ? 'node-pulse' : undefined} />
            {visual.warning && <text y={-26} textAnchor="middle" className="blink font-mono text-[10px] tracking-[0.15em] fill-[#ff4444]">{visual.warning}</text>}
            <text y={33} textAnchor="middle" className="font-mono text-[15px] font-medium tracking-wide fill-[#ffffff]">{node.name}</text>
            <text y={48} textAnchor="middle" className="font-mono text-[10px] uppercase tracking-widest" style={{ fill: visual.labelColor }}>{visual.label}</text>
            {ingress && <text x={-14} y={-28} textAnchor="middle" className="font-mono text-[10px] uppercase tracking-[0.2em] fill-[#a1a1aa]">Ingress</text>}
          </g>
        })}

        {memoryNodes.map((node) => {
          const position = memoryPositions[node.id]
          if (!position) return null
          const [x, y] = position
          const selected = selectedNode?.id === node.id
          return <g
            key={node.id}
            transform={`translate(${x} ${y})`}
            className="cursor-pointer outline-none"
            role="button" tabIndex={0}
            aria-label={`Inspect memory ${node.name} from ${node.agent}: ${node.reasoning}`}
            aria-pressed={selected}
            onClick={() => select(node)}
            onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(node) } }}
          >
            {selected && <path d={bracketPath(16, 6)} fill="none" stroke={INK} strokeWidth={0.75} />}
            <rect x={-6} y={-6} width={12} height={12} fill="none" stroke={MEMORY} strokeWidth={1.25} />
            <text y={26} textAnchor="middle" className="font-mono text-[12px] tracking-widest fill-[#a1a1aa]">{node.name}</text>
          </g>
        })}
      </svg>

      {!nodes.length && <div className="absolute inset-0 grid place-items-center font-mono text-[10px] uppercase tracking-widest text-[#71717a]">Awaiting graph telemetry</div>}
      <div className="pointer-events-none absolute right-4 bottom-3 z-10 flex gap-4 font-mono text-[9px] uppercase tracking-[0.22em] text-[#71717a]">
        <span>Pts {coreNodes.length}</span>
        <span>Links {structuralEdges.length}</span>
        {severedCount ? <span className="text-[#3b82f6]">Severed {severedCount}</span> : null}
      </div>
    </div>
  )
}

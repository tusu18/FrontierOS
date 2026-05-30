/* ResearchRadar — Knowledge Graph (force-directed, interactive) */
const NODE_COLORS = {
  paper: 'var(--n-paper)', method: 'var(--n-method)', dataset: 'var(--n-dataset)',
  benchmark: 'var(--n-benchmark)', claim: 'var(--n-claim)', limitation: 'var(--n-limitation)',
  future: 'var(--n-future)', gap: 'var(--n-gap)', author: 'var(--n-author)', institution: 'var(--n-inst)',
};
const NODE_HEX = {
  paper: '#5b9bff', method: '#a78bfa', dataset: '#2fcf9e', benchmark: '#34d9e0', claim: '#f4cf4a',
  limitation: '#f2607d', future: '#f4a52a', gap: '#ff8fc7', author: '#9aa6b2', institution: '#d8dee6',
};
const TYPE_LABEL = {
  paper: 'Paper', method: 'Method', dataset: 'Dataset', benchmark: 'Benchmark', claim: 'Claim',
  limitation: 'Limitation', future: 'Future Work', gap: 'Research Gap', author: 'Author', institution: 'Institution',
};

function useForceSim(graph, W, H) {
  const stateRef = useRef(null);
  const [, tick] = useState(0);

  if (!stateRef.current) {
    const nodes = graph.nodes.map((n, i) => ({
      ...n,
      x: W / 2 + Math.cos(i) * 140 + (Math.random() - .5) * 60,
      y: H / 2 + Math.sin(i) * 140 + (Math.random() - .5) * 60,
      vx: 0, vy: 0,
      r: n.type === 'paper' ? 11 : 6 + Math.min(7, Math.sqrt(n.freq) * 1.3),
    }));
    const idx = Object.fromEntries(nodes.map((n, i) => [n.id, i]));
    const links = graph.links.map(([a, b]) => ({ a: idx[a], b: idx[b] }));
    stateRef.current = { nodes, links, idx, alpha: 1 };
  }

  useEffect(() => {
    let raf;
    const step = () => {
      const st = stateRef.current;
      if (!st) return;
      const { nodes, links } = st;
      st.alpha *= 0.992;
      const k = 0.04 + st.alpha * 0.06;
      // repulsion
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const A = nodes[i], B = nodes[j];
          let dx = A.x - B.x, dy = A.y - B.y;
          let d2 = dx * dx + dy * dy || 1;
          const f = 4400 / d2;
          const d = Math.sqrt(d2);
          const fx = (dx / d) * f, fy = (dy / d) * f;
          A.vx += fx; A.vy += fy; B.vx -= fx; B.vy -= fy;
        }
      }
      // springs
      for (const l of links) {
        const A = nodes[l.a], B = nodes[l.b];
        let dx = B.x - A.x, dy = B.y - A.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d - 118) * 0.012;
        const fx = (dx / d) * f, fy = (dy / d) * f;
        A.vx += fx; A.vy += fy; B.vx -= fx; B.vy -= fy;
      }
      // center gravity + integrate
      for (const n of nodes) {
        if (n.fixed) { n.vx = 0; n.vy = 0; continue; }
        n.vx += (W / 2 - n.x) * 0.0015;
        n.vy += (H / 2 - n.y) * 0.0015;
        n.vx *= 0.86; n.vy *= 0.86;
        n.x += n.vx * k * 6; n.y += n.vy * k * 6;
        n.x = Math.max(n.r + 6, Math.min(W - n.r - 6, n.x));
        n.y = Math.max(n.r + 6, Math.min(H - n.r - 6, n.y));
      }
      tick(t => t + 1);
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [W, H]);

  return stateRef.current;
}

function KnowledgeGraph() {
  const { GRAPH } = window.RR_DATA;
  const W = 1000, H = 620;
  const sim = useForceSim(GRAPH, W, H);
  const [sel, setSel] = useState(null);
  const [hover, setHover] = useState(null);
  const [view, setView] = useState({ x: 0, y: 0, z: 1 });
  const [filter, setFilter] = useState('all');
  const [depth, setDepth] = useState(2);
  const dragRef = useRef(null);
  const panRef = useRef(null);
  const stageRef = useRef(null);

  // neighbor set for highlight
  const neighbors = useMemo(() => {
    const focus = sel || hover;
    if (focus == null) return null;
    const adj = new Set([focus]);
    let frontier = [focus];
    for (let d = 0; d < depth; d++) {
      const next = [];
      for (const l of GRAPH.links) {
        const a = sim.idx[l[0]], b = sim.idx[l[1]];
        if (adj.has(a) && !adj.has(b)) { adj.add(b); next.push(b); }
        if (adj.has(b) && !adj.has(a)) { adj.add(a); next.push(a); }
      }
      frontier = next;
    }
    return adj;
  }, [sel, hover, depth, sim]);

  const selNode = sel != null ? sim.nodes[sel] : null;
  const connectedPapers = useMemo(() => {
    if (sel == null) return [];
    const out = new Set();
    for (const l of GRAPH.links) {
      const a = sim.idx[l[0]], b = sim.idx[l[1]];
      if (a === sel && sim.nodes[b].type === 'paper') out.add(sim.nodes[b].label);
      if (b === sel && sim.nodes[a].type === 'paper') out.add(sim.nodes[a].label);
    }
    return [...out];
  }, [sel, sim]);

  function onNodeDown(e, i) {
    e.stopPropagation();
    const n = sim.nodes[i];
    n.fixed = true;
    dragRef.current = { i, startX: e.clientX, startY: e.clientY, nx: n.x, ny: n.y };
    setSel(i);
  }
  function onMove(e) {
    if (dragRef.current) {
      const d = dragRef.current; const n = sim.nodes[d.i];
      n.x = d.nx + (e.clientX - d.startX) / view.z;
      n.y = d.ny + (e.clientY - d.startY) / view.z;
    } else if (panRef.current) {
      const p = panRef.current;
      setView(v => ({ ...v, x: p.vx + (e.clientX - p.sx), y: p.vy + (e.clientY - p.sy) }));
    }
  }
  function onUp() {
    if (dragRef.current) sim.nodes[dragRef.current.i].fixed = false;
    dragRef.current = null; panRef.current = null;
  }
  function onStageDown(e) { panRef.current = { sx: e.clientX, sy: e.clientY, vx: view.x, vy: view.y }; }
  function zoom(dz) { setView(v => ({ ...v, z: Math.max(0.4, Math.min(2.4, v.z + dz)) })); }

  const types = ['all', ...Object.keys(TYPE_LABEL)];

  return (
    <div className="page wide fade-in">
      <PageHead crumb="Research Memory" title="Knowledge Graph"
        sub="Explore how papers, methods, datasets, claims, limitations and research gaps connect over time. Drag nodes, click to inspect, scroll the legend to filter.">
        <button className="btn" onClick={() => { setSel(null); setView({ x: 0, y: 0, z: 1 }); }}><Icon name="reset" size={14} /> Reset view</button>
      </PageHead>

      <div className="controls">
        <div className="search-field" style={{ maxWidth: 280, flex: 'none' }}>
          <Icon name="search" size={15} stroke="var(--d-text-3)" />
          <input placeholder="Search entity…" />
        </div>
        <select className="ctl" value={filter} onChange={e => setFilter(e.target.value)}>
          {types.map(t => <option key={t} value={t}>{t === 'all' ? 'All entity types' : TYPE_LABEL[t]}</option>)}
        </select>
        <select className="ctl" value={depth} onChange={e => setDepth(+e.target.value)}>
          <option value={1}>Depth · 1 hop</option>
          <option value={2}>Depth · 2 hops</option>
          <option value={3}>Depth · 3 hops</option>
        </select>
        <span className="mono-label" style={{ color: 'var(--d-text-3)', marginLeft: 'auto' }}>
          {GRAPH.nodes.length} entities · {GRAPH.links.length} relationships
        </span>
      </div>

      <div className="split" style={{ gridTemplateColumns: '1fr 340px' }}>
        <div className="graph-stage" ref={stageRef}
          onMouseDown={onStageDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
          onWheel={e => { e.preventDefault(); zoom(-e.deltaY * 0.0012); }}>
          <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet">
            <g transform={`translate(${view.x} ${view.y}) scale(${view.z})`} style={{ transformOrigin: 'center' }}>
              {sim.links.map((l, i) => {
                const A = sim.nodes[l.a], B = sim.nodes[l.b];
                const dim = neighbors && !(neighbors.has(l.a) && neighbors.has(l.b));
                return <line key={i} className="glink" x1={A.x} y1={A.y} x2={B.x} y2={B.y}
                  style={{ opacity: dim ? 0.06 : 0.5, stroke: (neighbors && !dim) ? 'var(--accent)' : 'var(--d-border-2)' }} />;
              })}
              {sim.nodes.map((n, i) => {
                const dimType = filter !== 'all' && n.type !== filter;
                const dim = (neighbors && !neighbors.has(i)) || dimType;
                const isSel = sel === i;
                return (
                  <g key={n.id} className="gnode" transform={`translate(${n.x} ${n.y})`}
                    style={{ opacity: dim ? 0.18 : 1 }}
                    onMouseDown={e => onNodeDown(e, i)}
                    onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                    <circle r={n.r + (isSel ? 4 : 0)} fill={NODE_HEX[n.type]}
                      stroke={isSel ? '#fff' : 'rgba(0,0,0,.3)'} strokeWidth={isSel ? 2 : 1} />
                    {(n.r > 9 || isSel || hover === i) &&
                      <text x={n.r + 5} y={4} style={{ fontSize: 11, fontWeight: isSel ? 600 : 400, fill: isSel ? '#fff' : 'var(--d-text-2)' }}>{n.label}</text>}
                  </g>
                );
              })}
            </g>
          </svg>

          <div className="graph-tools">
            <button className="icon-btn" onClick={() => zoom(0.2)}><Icon name="plus" size={15} /></button>
            <button className="icon-btn" onClick={() => zoom(-0.2)}><Icon name="minus" size={15} /></button>
          </div>

          <div className="graph-legend">
            {Object.keys(TYPE_LABEL).map(t => (
              <div className="lg" key={t} onClick={() => setFilter(filter === t ? 'all' : t)} style={{ cursor: 'pointer', opacity: filter !== 'all' && filter !== t ? .4 : 1 }}>
                <i style={{ background: NODE_HEX[t] }}></i>{TYPE_LABEL[t]}
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="card entity-panel">
            {selNode ? (
              <div className="fade-in">
                <span className="etype" style={{ color: NODE_HEX[selNode.type] }}>{TYPE_LABEL[selNode.type]}</span>
                <h3>{selNode.label}</h3>
                <p style={{ color: 'var(--d-text-2)', fontSize: 14, lineHeight: 1.5, margin: '0 0 8px' }}>
                  {selNode.type === 'gap' ? 'An unresolved research direction recurring across multiple papers and categories.'
                    : selNode.type === 'method' ? 'A technique appearing across the corpus, linked to the papers that employ it.'
                    : selNode.type === 'paper' ? 'A paper in research memory, connected to its methods, datasets, claims and gaps.'
                    : 'An entity in the shared research memory graph.'}
                </p>
                <div className="entity-stat"><span>Frequency in memory</span><b>{selNode.freq}×</b></div>
                <div className="entity-stat"><span>First seen</span><b>2026-04-11</b></div>
                <div className="entity-stat"><span>Last seen</span><b>2026-05-29</b></div>
                <div className="entity-stat"><span>Connected papers</span><b>{connectedPapers.length}</b></div>
                {connectedPapers.length > 0 && (
                  <div style={{ marginTop: 14 }}>
                    <div className="sb-cap" style={{ padding: '0 0 8px' }}>Connected papers</div>
                    {connectedPapers.map(p => (
                      <div key={p} style={{ fontSize: 13, color: 'var(--d-text-2)', padding: '7px 0', borderTop: '1px solid var(--d-border)', display: 'flex', gap: 8 }}>
                        <span style={{ color: 'var(--n-paper)' }}>●</span>{p}
                      </div>
                    ))}
                  </div>
                )}
                <button className="btn btn-accent btn-sm" style={{ marginTop: 16, width: '100%', justifyContent: 'center' }}>Expand neighborhood</button>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '30px 0', color: 'var(--d-text-3)' }}>
                <div className="stub-ic" style={{ margin: '0 auto 16px' }}><Icon name="graph" size={26} /></div>
                <p style={{ fontSize: 14, lineHeight: 1.5 }}>Click any node to inspect an entity, its frequency, and connected papers.</p>
              </div>
            )}
          </div>

          <div className="card card-pad" style={{ marginTop: 16 }}>
            <div className="section-title" style={{ fontSize: 15 }}>Top connected entities</div>
            {[...GRAPH.nodes].filter(n => n.type !== 'paper').sort((a, b) => b.freq - a.freq).slice(0, 6).map(n => (
              <div key={n.id} className="trend-row" onClick={() => setSel(sim.idx[n.id])} style={{ cursor: 'pointer' }}>
                <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}><i style={{ width: 8, height: 8, borderRadius: '50%', background: NODE_HEX[n.type], display: 'inline-block' }}></i>{n.label}</span>
                <b>{n.freq}×</b>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { KnowledgeGraph, NODE_HEX, TYPE_LABEL });

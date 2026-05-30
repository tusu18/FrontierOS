/* ResearchRadar — pages (dashboard, daily, deep dive, trends, gaps) */

/* =================== DASHBOARD =================== */
function DashboardPage({ setPage, onOpen, onAction }) {
  const { KPIS, INTEL, PAPERS, META } = window.RR_DATA;
  const [toast, setToast] = React.useState('');
  const [busy, setBusy] = React.useState('');

  async function doAction(endpoint, label) {
    if (busy) return;
    setBusy(label);
    try {
      const res = await fetch(`/api/actions/${endpoint}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const d = await res.json();
      setToast(d.message || 'Done');
      setTimeout(() => setToast(''), 3000);
    } catch(e) { setToast('Error — check console'); setTimeout(() => setToast(''), 3000); }
    setBusy('');
  }

  return (
    <div className="page fade-in">
      {toast && <div style={{ position:'fixed',bottom:26,left:'50%',transform:'translateX(-50%)',background:'var(--d-elev-2)',border:'1px solid var(--accent)',color:'var(--d-text)',padding:'12px 20px',borderRadius:999,fontSize:14,zIndex:200 }} className="fade-in">{toast}</div>}
      <div className="cmd-hero">
        <div className="mono-label" style={{ color: 'var(--accent)', marginBottom: 14 }}>Research command center</div>
        <h2>Today's CS research, ranked by novelty, impact, reproducibility, and opportunity.</h2>
        <p>{META && META.today > 0 ? `${META.today} new papers analyzed and folded into your research memory. Here's what's worth your attention.` : 'Click "Fetch today\'s papers" to start loading arXiv papers into your research memory.'}</p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="btn btn-accent" onClick={() => doAction('fetch', 'fetch')} disabled={!!busy}><Icon name="feed" size={15} /> {busy==='fetch' ? 'Fetching…' : "Fetch today's papers"}</button>
          <button className="btn" onClick={() => doAction('summarize', 'summarize')} disabled={!!busy}><Icon name="report" size={15} /> {busy==='summarize' ? 'Summarizing…' : 'Summarize papers'}</button>
          <button className="btn" onClick={() => doAction('build-kg', 'kg')} disabled={!!busy}><Icon name="spark" size={15} /> {busy==='kg' ? 'Building KG…' : 'Build Knowledge Graph'}</button>
          <button className="btn btn-ghost" onClick={() => setPage('memory')}><Icon name="spark" size={15} /> Ask Research Memory</button>
        </div>
        <div className="status">
          <div>Last updated<b>{META ? META.last_updated : '—'}</b></div>
          <div>Papers analyzed today<b>{META ? META.today : 0}</b></div>
          <div>Papers in memory<b>{META ? META.total_papers.toLocaleString() : 0}</b></div>
          <div>Graph entities<b>{META ? META.kg_entities.toLocaleString() : 0}</b></div>
          <div>Graph relationships<b>{META ? META.kg_edges.toLocaleString() : 0}</b></div>
        </div>
      </div>

      <div style={{ height: 22 }} />
      <div className="kpi-grid">{KPIS.map(k => <KpiCard key={k.label} kpi={k} />)}</div>

      <div style={{ height: 30 }} />
      <div className="section-title">Today's intelligence</div>
      <div className="intel-strip">
        {INTEL.map(it => (
          <div key={it.k} className="card intel">
            <div className="ik">{it.k}</div>
            <div className="iv">{it.v}</div>
          </div>
        ))}
      </div>

      <div style={{ height: 30 }} />
      <div className="section-title">Top papers today <span className="count">ranked by opportunity</span>
        <button className="btn btn-sm btn-ghost" style={{ marginLeft: 'auto' }} onClick={() => setPage('daily')}>View all 50 <Icon name="arrow" size={13} /></button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {[...PAPERS].sort((a, b) => b.scores.opportunity - a.scores.opportunity).slice(0, 4).map(p => (
          <PaperCard key={p.id} paper={p} onOpen={onOpen} onAction={onAction} />
        ))}
      </div>
    </div>
  );
}

/* =================== DAILY PAPERS =================== */
function DailyPapersPage({ onOpen, onAction, activeCats }) {
  const { PAPERS, CATS } = window.RR_DATA;
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('all');
  const [sort, setSort] = useState('opportunity');
  const [onlyCode, setOnlyCode] = useState(false);
  const [colab, setColab] = useState(false);

  const list = useMemo(() => {
    let r = PAPERS.filter(p =>
      (cat === 'all' || p.cat === cat) &&
      (!onlyCode || p.code) && (!colab || p.colab) &&
      (q === '' || (p.title + p.summary + p.tags.join()).toLowerCase().includes(q.toLowerCase()))
    );
    const key = { opportunity: 'opportunity', novelty: 'novelty', impact: 'impact', build: 'build' }[sort];
    if (sort === 'date') r = [...r].sort((a, b) => b.date.localeCompare(a.date));
    else if (sort === 'reprod') r = [...r].sort((a, b) => a.scores.reprod.localeCompare(b.scores.reprod));
    else r = [...r].sort((a, b) => b.scores[key] - a.scores[key]);
    return r;
  }, [q, cat, sort, onlyCode, colab]);

  return (
    <div className="page fade-in">
      <PageHead crumb="Feed" title="Daily Papers" sub={`${list.length} CS papers ranked by research opportunity.`} />
      <div className="controls">
        <div className="search-field">
          <Icon name="search" size={15} stroke="var(--d-text-3)" />
          <input placeholder="Search papers…" value={q} onChange={e => setQ(e.target.value)} />
        </div>
        <select className="ctl" value={cat} onChange={e => setCat(e.target.value)}>
          <option value="all">All categories</option>
          {CATS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
        <select className="ctl" value={sort} onChange={e => setSort(e.target.value)}>
          <option value="opportunity">Sort · Opportunity</option>
          <option value="novelty">Sort · Novelty</option>
          <option value="impact">Sort · Impact</option>
          <option value="reprod">Sort · Reproducibility</option>
          <option value="build">Sort · Buildability</option>
          <option value="date">Sort · Date</option>
        </select>
        <span className={`toggle-chip${onlyCode ? ' on' : ''}`} onClick={() => setOnlyCode(v => !v)}><span className="sw"></span> Only with code</span>
        <span className={`toggle-chip${colab ? ' on' : ''}`} onClick={() => setColab(v => !v)}><span className="sw"></span> Colab-friendly</span>
      </div>
      <div style={{ display: 'grid', gap: 16 }}>
        {list.map(p => <PaperCard key={p.id} paper={p} onOpen={onOpen} onAction={onAction} />)}
        {list.length === 0 && <div className="card card-pad" style={{ textAlign: 'center', color: 'var(--d-text-3)' }}>No papers match these filters.</div>}
      </div>
    </div>
  );
}

/* =================== PAPER DEEP DIVE =================== */
function DeepDivePage({ paper, onAction, setPage }) {
  const { PAPERS } = window.RR_DATA;
  const p = paper || PAPERS[0];
  const [tab, setTab] = useState('Summary');
  const tabs = ['Summary', 'Method', 'Claims', 'Datasets', 'Limitations', 'Future Work', 'Related', 'Memory', 'Code'];
  const s = p.scores;

  const claims = [
    { claim: 'Outperforms baseline on multi-step tasks', dataset: p.datasets[0] || 'HotpotQA', metric: 'Success@1', base: '61.2', imp: '+8.4', ev: 'Table 3', conf: 'High' },
    { claim: 'Reduces failure repetition', dataset: p.datasets[1] || 'BEIR', metric: 'Repeat-err', base: '14.1%', imp: '−9.3pp', ev: 'Fig 5', conf: 'Medium' },
    { claim: 'Maintains latency budget', dataset: 'Internal', metric: 'p95 ms', base: '820', imp: '+6%', ev: 'App. B', conf: 'Medium' },
  ];
  const limits = [
    { l: 'Evaluated mostly on English benchmarks', ev: 'Datasets section', sev: 'Medium', ext: 'Multilingual long-horizon eval suite' },
    { l: 'Compute cost grows with memory size', ev: 'Section 6', sev: 'High', ext: 'Adaptive memory pruning' },
  ];

  const Pane = () => {
    switch (tab) {
      case 'Summary': return (<div className="fade-in">
        <DDBlock t="One-line summary" v={p.summary} />
        <DDBlock t="Problem" v={p.problem} />
        <DDBlock t="Main contribution" v={p.contribution} />
        <DDBlock t="Why it matters" v={p.matters} />
        <DDBlock t="Who should read this" v={p.who} />
      </div>);
      case 'Method': return (<div className="fade-in">
        <DDBlock t="Main technical idea" v={p.contribution} />
        <DDBlock t="Architecture" v={`A ${p.methods[0]} module feeds a downstream policy; inputs are encoded, routed through ${p.methods[1] || 'the core component'}, and decoded into actions.`} />
        <DDBlock t="Key methods" v={p.methods.join(' · ')} />
        <DDBlock t="Inputs → outputs" v="Natural-language task + context → structured plan + verified tool calls → final response." />
      </div>);
      case 'Claims': return (<div className="fade-in card" style={{ overflow: 'hidden' }}>
        <table className="rr"><thead><tr><th>Claim</th><th>Dataset</th><th>Metric</th><th>Baseline</th><th>Improve</th><th>Evidence</th><th>Conf.</th></tr></thead>
          <tbody>{claims.map((c, i) => <tr key={i}><td><b>{c.claim}</b></td><td>{c.dataset}</td><td>{c.metric}</td><td>{c.base}</td><td style={{ color: 'var(--green-300)' }}>{c.imp}</td><td>{c.ev}</td><td>{c.conf}</td></tr>)}</tbody>
        </table></div>);
      case 'Datasets': return (<div className="fade-in" style={{ display: 'grid', gap: 12 }}>
        {p.datasets.map(d => <div key={d} className="card card-pad" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><div><b style={{ fontFamily: 'var(--font-display)' }}>{d}</b><div style={{ fontSize: 12.5, color: 'var(--d-text-3)', marginTop: 4 }}>Used for evaluation · public</div></div><Badge variant="green">in memory</Badge></div>)}
      </div>);
      case 'Limitations': return (<div className="fade-in" style={{ display: 'grid', gap: 12 }}>
        {limits.map((l, i) => <div key={i} className="card card-pad" style={{ borderLeft: '2px solid var(--rose)' }}>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>{l.l}</div>
          <div className="entity-stat" style={{ borderTop: 'none', padding: '4px 0' }}><span>Evidence</span><b>{l.ev}</b></div>
          <div className="entity-stat" style={{ padding: '4px 0' }}><span>Severity</span><b>{l.sev}</b></div>
          <div className="entity-stat" style={{ padding: '4px 0' }}><span>Possible extension</span><b style={{ color: 'var(--accent)' }}>{l.ext}</b></div>
        </div>)}
      </div>);
      case 'Future Work': return (<div className="fade-in"><DDBlock t="Authors' stated directions" v="Scaling the memory router to multi-agent settings; learning when to forget; benchmarking long-horizon reliability." /><DDBlock t="ResearchRadar extension" v="Combine with a typed-contract tool layer to bound failure modes during long-horizon execution." /></div>);
      case 'Related': return (<div className="fade-in" style={{ display: 'grid', gap: 12 }}>{PAPERS.filter(x => x.id !== p.id).slice(0, 4).map(x => <div key={x.id} className="card card-pad" style={{ cursor: 'pointer' }} onClick={() => onAction('open', x)}><b style={{ fontFamily: 'var(--font-display)' }}>{x.title}</b><div style={{ fontSize: 12.5, color: 'var(--d-text-3)', marginTop: 6 }}>{x.cat} · shares {x.methods[0]}</div></div>)}</div>);
      case 'Memory': return (<div className="fade-in">
        <div className="kpi-grid" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
          {[['Similar papers', 12], ['Shared methods', 5], ['Shared datasets', 3], ['Repeated limitations', 4], ['Related research gaps', 2], ['Co-authors in memory', 7]].map(([k, v]) =>
            <div key={k} className="card kpi"><span className="k-label">{k}</span><div className="k-val">{v}</div></div>)}
        </div>
        <button className="btn btn-accent" style={{ marginTop: 18 }} onClick={() => setPage('graph')}><Icon name="graph" size={15} /> View in knowledge graph</button>
      </div>);
      case 'Code': return (<div className="fade-in card card-pad" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--d-text-2)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
        <span style={{ color: 'var(--accent)' }}>{'# generate a runnable skeleton from this paper'}</span>{`\nfrom researchradar import MemoryRouter, Planner\n\nrouter = MemoryRouter(index="`}{p.datasets[0] || 'corpus'}{`")\nplanner = Planner(router=router, tools=[...])\n\nplan = planner.solve(task, max_steps=12)`}
        <div style={{ marginTop: 16 }}><button className="btn btn-accent btn-sm" onClick={() => setPage('p2c')}>Open in Paper-to-Code <Icon name="arrow" size={13} /></button></div>
      </div>);
      default: return null;
    }
  };

  return (
    <div className="page fade-in">
      <PageHead crumb="Paper Deep Dive" title={p.title} />
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 18 }}>
        {['arXiv', 'PDF', 'Official Code', 'Project Page', 'Hugging Face'].map(l => <button key={l} className="btn btn-sm">{l} <Icon name="external" size={12} /></button>)}
      </div>
      <div className="split">
        <div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 18 }}>
            <Badge variant="blue">{p.cat}</Badge>{p.tags.map(t => <Badge key={t} variant="gray">{t}</Badge>)}{p.badges.map(b => <Badge key={b}>{b}</Badge>)}
          </div>
          <div className="tabs">{tabs.map(t => <button key={t} className={`tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>{t}</button>)}</div>
          <Pane />
        </div>
        <div>
          <div className="card card-pad">
            <div className="sb-cap" style={{ padding: '0 0 12px' }}>Scores</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <Score label="Novelty" value={s.novelty} /><Score label="Impact" value={s.impact} />
              <Score label="Reprod." value={s.reprod} /><Score label="Build" value={s.build} /><Score label="Opp." value={s.opportunity} />
            </div>
            <div style={{ margintop: 16, display: 'grid', gap: 8, marginTop: 18 }}>
              <button className="btn btn-accent" onClick={() => setPage('p2c')}><Icon name="code" size={15} /> Generate code</button>
              <button className="btn" onClick={() => onAction('save', p)}><Icon name="bookmark" size={15} /> Add to library</button>
              <button className="btn" onClick={() => setPage('builder')}><Icon name="build" size={15} /> Build a project</button>
            </div>
          </div>
          <div className="card card-pad" style={{ marginTop: 16 }}>
            <div className="sb-cap" style={{ padding: '0 0 10px' }}>Graph links</div>
            {p.methods.concat(p.datasets).slice(0, 6).map(m => <div key={m} className="trend-row" style={{ cursor: 'pointer' }} onClick={() => setPage('graph')}><span>{m}</span><Icon name="chevron" size={13} /></div>)}
          </div>
        </div>
      </div>
    </div>
  );
}
function DDBlock({ t, v }) {
  return <div style={{ marginBottom: 20 }}><div className="sb-cap" style={{ padding: '0 0 7px', color: 'var(--accent)' }}>{t}</div><p style={{ margin: 0, fontSize: 15.5, lineHeight: 1.6, color: 'var(--d-text)' }}>{v}</p></div>;
}

/* =================== TREND RADAR =================== */
function TrendRadarPage({ setPage }) {
  const { TRENDS } = window.RR_DATA;
  const maxPapers = Math.max(...TRENDS.map(t => t.papers));
  return (
    <div className="page fade-in">
      <PageHead crumb="Intelligence" title="Trend Radar" sub="Where computer-science research is moving — velocity, saturation, and open opportunity across tracked categories." />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 28 }}>
        <div className="card card-pad">
          <div className="section-title" style={{ fontSize: 15 }}>Topic velocity <span className="count">week over week</span></div>
          <div className="barchart">
            {[...TRENDS].sort((a, b) => b.velocity - a.velocity).map(t => (
              <div className="bc-row" key={t.name}>
                <span className="bc-label">{t.name}</span>
                <div className="bc-track"><div className="bc-fill" style={{ width: `${Math.min(100, Math.abs(t.velocity) * 1.4)}%`, background: t.velocity < 0 ? 'var(--rose)' : 'var(--accent)' }}></div></div>
                <span className="bc-val" style={{ color: t.velocity < 0 ? 'var(--rose)' : 'var(--green-300)' }}>{t.velocity > 0 ? '+' : ''}{t.velocity}%</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card card-pad">
          <div className="section-title" style={{ fontSize: 15 }}>Novelty vs. saturation</div>
          <div className="scatter">
            <span className="sc-axis" style={{ left: 8, top: 6 }}>↑ novelty</span>
            <span className="sc-axis" style={{ right: 8, bottom: 6 }}>saturation →</span>
            {TRENDS.map(t => {
              const sx = { Low: 18, Medium: 50, High: 82 }[t.saturation];
              return <div key={t.name} className="sc-pt" title={`${t.name} · ${t.saturation} saturation`}
                style={{ left: `${sx}%`, bottom: `${(t.novelty / 10) * 88 + 6}%`, background: t.opportunity === 'High' ? 'var(--accent)' : t.opportunity === 'Medium' ? 'var(--amber)' : 'var(--d-text-3)', boxShadow: t.opportunity === 'High' ? '0 0 12px var(--accent)' : 'none' }} />;
            })}
          </div>
          <div style={{ display: 'flex', gap: 16, marginTop: 12, fontSize: 12, color: 'var(--d-text-3)' }}>
            <span><i style={{ color: 'var(--accent)' }}>●</i> High opp.</span><span><i style={{ color: 'var(--amber)' }}>●</i> Medium</span><span><i style={{ color: 'var(--d-text-3)' }}>●</i> Low</span>
          </div>
        </div>
      </div>
      <div className="section-title">Trend cards</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(320px,1fr))', gap: 16 }}>
        {TRENDS.map(t => (
          <div key={t.name} className="card trend-card">
            <h4>{t.name}<span className={`vel ${t.velocity < 0 ? 'down' : 'up'}`}>{t.velocity > 0 ? '+' : ''}{t.velocity}%</span></h4>
            <div className="trend-row"><span>Saturation</span><b>{t.saturation}</b></div>
            <div className="trend-row"><span>Opportunity</span><b style={{ color: t.opportunity === 'High' ? 'var(--accent)' : 'var(--d-text-2)' }}>{t.opportunity}</b></div>
            <div className="trend-row"><span>Related papers</span><b>{t.papers}</b></div>
            <div style={{ fontSize: 12.5, color: 'var(--d-text-3)', margin: '10px 0 4px' }}>Methods: {t.methods.join(', ')}</div>
            <div style={{ fontSize: 12.5, color: 'var(--d-text-3)' }}>Open gaps: {t.gaps.join(', ')}</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
              <button className="btn btn-sm" onClick={() => setPage('daily')}>View papers</button>
              <button className="btn btn-sm btn-ghost" onClick={() => setPage('builder')}>Research ideas</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* =================== RESEARCH GAPS =================== */
function GapsPage({ setPage }) {
  const { GAPS } = window.RR_DATA;
  return (
    <div className="page fade-in">
      <PageHead crumb="Intelligence" title="Research Gap Finder" sub="High-opportunity, under-served directions surfaced from repeated limitations and unsolved future work across the corpus." />
      <div style={{ display: 'grid', gap: 16 }}>
        {GAPS.map(g => (
          <div key={g.gap} className="card gap-card">
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 20, flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 280 }}>
                <div style={{ display: 'flex', gap: 7, marginBottom: 12, flexWrap: 'wrap' }}>{g.cats.map(c => <Badge key={c} variant="blue">{c}</Badge>)}<Badge variant="orange">Difficulty · {g.difficulty}</Badge></div>
                <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 21, letterSpacing: '-.01em', margin: '0 0 14px' }}>{g.gap}</h3>
                <div className="sb-cap" style={{ padding: '0 0 8px', color: 'var(--accent)' }}>Evidence</div>
                {g.evidence.map(e => <div key={e} style={{ fontSize: 13.5, color: 'var(--d-text-2)', padding: '5px 0', display: 'flex', gap: 8 }}><span style={{ color: 'var(--accent)' }}>→</span>{e}</div>)}
                <div className="sb-cap" style={{ padding: '14px 0 6px', color: 'var(--accent)' }}>Possible project</div>
                <p style={{ margin: 0, fontSize: 14.5, color: 'var(--d-text)', lineHeight: 1.55 }}>{g.project}</p>
              </div>
              <div style={{ textAlign: 'center', minWidth: 120 }}>
                <div className="sb-cap" style={{ padding: 0 }}>Opportunity</div>
                <div className="opp">{g.score}</div>
                <div style={{ display: 'grid', gap: 8, marginTop: 16 }}>
                  <button className="btn btn-accent btn-sm" onClick={() => setPage('builder')}>Generate project</button>
                  <button className="btn btn-sm" onClick={() => setPage('daily')}>Related papers</button>
                  <button className="btn btn-sm btn-ghost">Add to ideas</button>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { DashboardPage, DailyPapersPage, DeepDivePage, TrendRadarPage, GapsPage });

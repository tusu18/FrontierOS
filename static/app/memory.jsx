/* FrontierOS — Ask Research Memory (simulated streaming) + stubs */

function MemoryPage() {
  const chips = [
    'What are the fastest-growing RAG topics this week?',
    'Which LLM agent papers have code?',
    'What are unresolved gaps in multimodal reasoning?',
    'Which datasets are overused in cs.CL?',
    'Find papers combining robotics and language models.',
    'Generate a thesis idea from recent AI papers.',
  ];
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [searchMode, setSearchMode] = useState('keyword/hybrid-lite');
  const endRef = useRef(null);

  useEffect(() => { endRef.current && endRef.current.scrollTo({ top: 1e6 }); });

  function answerFor(q) {
    const ql = q.toLowerCase();
    if (ql.includes('rag') || ql.includes('retriev')) return {
      lead: 'Agentic RAG is the fastest-growing retrieval theme this week, up +42% in paper volume. The momentum is concentrated in planning and memory, not in raw retrieval quality.',
      bullets: ['Tool-use + retrieval planning appears in 18 papers, vs 11 last week.', 'Late-interaction retrieval is displacing two-stage re-ranking for throughput.', 'Evaluation remains the dominant open gap — few papers benchmark long-horizon reliability.'],
      papers: ['Memory-Routed Agents (cs.CL)', 'Retrieval Without Re-ranking (cs.IR)', 'Verifiable Tool Use (cs.SE)'],
      ents: ['Retrieval Planning', 'Tool-Use Agents', 'Long-horizon agent eval'],
      next: ['Open the Trend Radar for velocity detail', 'Generate a reproduction plan for Memory-Routed Agents'],
    };
    if (ql.includes('gap') || ql.includes('multimodal')) return {
      lead: 'The clearest unresolved gap in multimodal reasoning is cross-frame consistency — models are scored in aggregate, which hides systematic temporal failures.',
      bullets: ['Mentioned across 9 papers, concentrated in cs.CV with no shared protocol.', 'CrossModal-Eval proposes a 9-class failure taxonomy but stops short of a temporal-consistency suite.', 'Opportunity score 8.4 / difficulty Hard.'],
      papers: ['CrossModal-Eval (cs.CV)'],
      ents: ['Cross-frame consistency', 'Failure taxonomy', 'MMMU'],
      next: ['Open Research Gaps for the full evidence trail', 'Send this gap to Project Builder'],
    };
    if (ql.includes('thesis') || ql.includes('idea') || ql.includes('project')) return {
      lead: 'A strong, scoped thesis direction from this week: a benchmark for multi-step agent reliability with a failure taxonomy.',
      bullets: ['Sits on a 9.1 opportunity gap recurring in 14 papers across cs.CL / cs.AI / cs.SE.', 'Buildable on a single GPU using existing agent traces.', 'Pairs naturally with typed-contract tool use to bound failure modes.'],
      papers: ['Memory-Routed Agents (cs.CL)', 'Verifiable Tool Use (cs.SE)'],
      ents: ['Long-horizon agent eval', 'Agent reliability benchmark'],
      next: ['Open Project Builder to scope an MVP', 'Generate a reproduction plan'],
    };
    return {
      lead: 'Here is what research memory found across 10K+ indexed papers, weighted toward the last 7 days.',
      bullets: ['Three papers this week ship runnable code with buildability ≥ 8.', 'Small-model reasoning is rising (+38%) and remains low-saturation.', 'LLM benchmarking is saturating (−12%) — diminishing returns for new entrants.'],
      papers: ['Sub-Billion Reasoners (cs.LG)', 'Verifiable Tool Use (cs.SE)'],
      ents: ['Distillation', 'Tool-Use Agents'],
      next: ['Open Daily Papers filtered to code-ready', 'Ask a follow-up to narrow by category'],
    };
  }

  function stream(a) {
    const full = a.lead;
    let i = 0;
    const iv = setInterval(() => {
      i += 2;
      setMsgs(m => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], streamed: full.slice(0, i) }; return c; });
      if (i >= full.length) { clearInterval(iv); setMsgs(m => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], done: true }; return c; }); setBusy(false); }
    }, 16);
  }

  function ask(q) {
    if (!q.trim() || busy) return;
    setMsgs(m => [...m, { role: 'user', text: q }, { role: 'ai', a: { lead: '', bullets: [], papers: [], ents: [], next: [] }, streamed: '' }]);
    setInput(''); setBusy(true);

    // Query the live research memory; fall back to the local heuristic on error.
    fetch('/api/memory/query', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, limit: 15 }),
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(d => {
        if (d.search_mode) setSearchMode(d.search_mode);
        const a = {
          lead:    d.lead || 'No relevant items found in research memory yet.',
          bullets: d.bullets || [],
          papers:  d.papers || [],
          ents:    d.ents || [],
          next:    d.next || [],
        };
        setMsgs(m => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], a }; return c; });
        stream(a);
      })
      .catch(() => {
        const a = answerFor(q);
        setMsgs(m => { const c = [...m]; c[c.length - 1] = { ...c[c.length - 1], a }; return c; });
        stream(a);
      });
  }

  return (
    <div className="page fade-in">
      <PageHead crumb="Agentic query" title="Ask Research Memory" sub="Every answer is grounded in papers from your local research database, with connected graph entities and suggested next actions.">
        <span style={{ fontSize: 11, color: 'var(--d-text-3)', border: '1px solid var(--d-border)', borderRadius: 6, padding: '3px 8px' }}>
          Search mode: {searchMode}
        </span>
      </PageHead>
      <div className="chat-wrap" ref={endRef} style={{ maxHeight: 'calc(100vh - 280px)', overflowY: 'auto', paddingRight: 6 }}>
        {msgs.length === 0 && (
          <div className="chips-row">{chips.map(c => <span key={c} className="prompt-chip" onClick={() => ask(c)}>{c}</span>)}</div>
        )}
        {msgs.map((m, i) => m.role === 'user'
          ? <div key={i} className="msg user"><div className="role">You</div><div className="bubble">{m.text}</div></div>
          : <div key={i} className="msg ai"><div className="role">◎ Research Memory</div>
              <div className="bubble">
                <p>{m.streamed}{!m.done && <span className="cursor-blink"></span>}</p>
                {m.done && <div className="fade-in">
                  {m.a.bullets.map((b, j) => <div key={j} className="ev">{b} <span className="cite">[{j + 1}]</span></div>)}
                  <div style={{ marginTop: 14 }}><div className="sb-cap" style={{ padding: '0 0 8px', color: 'var(--accent)' }}>Relevant papers</div>
                    {m.a.papers.map(p => <div key={p} style={{ fontSize: 13.5, padding: '5px 0', color: 'var(--d-text-2)', display: 'flex', gap: 8 }}><span style={{ color: 'var(--n-paper)' }}>●</span>{p}</div>)}
                  </div>
                  <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginTop: 12 }}>{m.a.ents.map(e => <Badge key={e} variant="purple">{e}</Badge>)}</div>
                  <div style={{ marginTop: 14 }}><div className="sb-cap" style={{ padding: '0 0 8px', color: 'var(--accent)' }}>Suggested next actions</div>
                    {m.a.next.map(n => <div key={n} style={{ fontSize: 13.5, padding: '5px 0', color: 'var(--d-text-2)', display: 'flex', gap: 8 }}><Icon name="arrow" size={14} stroke="var(--accent)" />{n}</div>)}
                  </div>
                </div>}
              </div>
            </div>
        )}
      </div>
      <div className="chat-wrap">
        <div className="composer">
          <Icon name="spark" size={18} stroke="var(--accent)" />
          <input placeholder="Ask anything about your research memory…" value={input}
            onChange={e => setInput(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') ask(input); }} />
          <button className="send-btn" onClick={() => ask(input)}><Icon name="arrow" size={17} stroke="#042b23" /></button>
        </div>
      </div>
    </div>
  );
}

/* =================== PAPER-TO-CODE =================== */
function PaperToCodePage() {
  const { PAPERS } = window.RR_DATA;
  const [paper, setPaper] = useState(PAPERS[0].id);
  const [mode, setMode] = useState('PyTorch skeleton');
  const [tab, setTab] = useState('Code');
  const [out, setOut] = useState('');
  const [gen, setGen] = useState(false);
  const p = PAPERS.find(x => x.id === paper);
  const modes = ['Pseudocode', 'PyTorch skeleton', 'Training pipeline', 'Dataset preparation', 'Evaluation script', 'Reproduction plan', 'Minimal prototype', 'Colab notebook', 'GitHub README'];

  const code = `# ${p.title}\n# mode: ${mode} · generated by FrontierOS\n\nimport torch, torch.nn as nn\nfrom frontieros import MemoryRouter, Planner\n\nclass ${p.methods[0].replace(/[^a-z]/gi,'')}(nn.Module):\n    def __init__(self, dim=768):\n        super().__init__()\n        self.router = MemoryRouter(dim)\n        self.policy = nn.TransformerDecoder(...)\n\n    def forward(self, task, context):\n        plan = self.router.retrieve(task)        # ${p.methods[1] || 'retrieval'}\n        return self.policy(plan, context)\n\nif __name__ == "__main__":\n    model = ${p.methods[0].replace(/[^a-z]/gi,'')}()\n    # train on ${p.datasets.join(', ')}`;

  function generate() {
    setGen(true); setOut('');
    let i = 0;
    const iv = setInterval(() => { i += 6; setOut(code.slice(0, i)); if (i >= code.length) { clearInterval(iv); setGen(false); } }, 12);
  }

  return (
    <div className="page fade-in">
      <PageHead crumb="Build" title="Paper-to-Code" sub="Turn a method section into runnable scaffolding scoped to your compute budget." />
      <div className="split" style={{ gridTemplateColumns: '300px 1fr' }}>
        <div>
          <div className="card card-pad">
            <div className="sb-cap" style={{ padding: '0 0 8px' }}>Select paper</div>
            <select className="ctl" style={{ width: '100%' }} value={paper} onChange={e => setPaper(e.target.value)}>
              {PAPERS.map(x => <option key={x.id} value={x.id}>{x.title.slice(0, 40)}…</option>)}
            </select>
            <div className="sb-cap" style={{ padding: '16px 0 8px' }}>Code mode</div>
            <select className="ctl" style={{ width: '100%' }} value={mode} onChange={e => setMode(e.target.value)}>
              {modes.map(m => <option key={m}>{m}</option>)}
            </select>
            <div className="sb-cap" style={{ padding: '16px 0 8px' }}>Options</div>
            {['Use full PDF text', 'Use related papers from memory', 'Prefer Colab-friendly', 'Assume single GPU'].map((o, i) =>
              <label key={o} style={{ display: 'flex', gap: 9, fontSize: 13, color: 'var(--d-text-2)', padding: '6px 0', cursor: 'pointer' }}>
                <input type="checkbox" defaultChecked={i < 2} /> {o}</label>)}
            <button className="btn btn-accent" style={{ width: '100%', justifyContent: 'center', marginTop: 16 }} onClick={generate}>
              <Icon name="code" size={15} /> {gen ? 'Generating…' : 'Generate'}</button>
          </div>
        </div>
        <div>
          <div className="tabs">{['Implementation Plan', 'Code', 'Dataset', 'Evaluation', 'README', 'Risks'].map(t => <button key={t} className={`tab${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>{t}</button>)}</div>
          <div className="card card-pad" style={{ fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.7, color: 'var(--d-text-2)', whiteSpace: 'pre-wrap', minHeight: 360 }}>
            {tab === 'Code'
              ? (out || <span style={{ color: 'var(--d-text-3)' }}>{'// press Generate to scaffold an implementation from this paper'}</span>)
              : <span style={{ color: 'var(--d-text-3)' }}>{`// ${tab} for "${p.title}"\n// generated content appears here after running the agent`}</span>}
            {gen && <span className="cursor-blink"></span>}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 14 }}>
            <button className="btn btn-sm"><Icon name="download" size={13} /> Download .py</button>
            <button className="btn btn-sm"><Icon name="download" size={13} /> README.md</button>
            <button className="btn btn-sm"><Icon name="download" size={13} /> Colab outline</button>
            <button className="btn btn-sm btn-ghost"><Icon name="bookmark" size={13} /> Save to library</button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* =================== STUBS =================== */
function ProjectBuilderPage() {
  return <StubPage icon="build" crumb="Build" title="Project Builder"
    desc="Turn a paper, research gap, or trend into a scoped project — from MVP and architecture to dataset plan, evaluation, and a novelty angle."
    feats={['Source: paper / gap / trend', 'Type: thesis · repo · prototype', 'Time & compute budget', 'Repo structure + risk analysis']} />;
}
function ReportsPage() {
  const reports = ['Daily Research Brief', 'Weekly Trend Report', 'Monthly CS Landscape', 'Category Report', 'Research Gap Report', 'Personalized Reading Report'];
  return (
    <div className="page fade-in">
      <PageHead crumb="Publication studio" title="Reports" sub="Generated research briefs you can read, regenerate, and export." />
      <div className="card card-pad" style={{ marginBottom: 18, borderLeft: '2px solid var(--accent)' }}>
        <div className="sb-cap" style={{ padding: 0, color: 'var(--accent)' }}>Featured</div>
        <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 22, margin: '10px 0 14px' }}>Daily AI Research Brief — May 29, 2026</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 12, marginBottom: 16 }}>
          {[['Top papers', 5], ['Top trends', 5], ['Research gaps', 3], ['Buildable projects', 3]].map(([k, v]) =>
            <div key={k} className="card kpi" style={{ background: 'var(--d-bg-2)' }}><span className="k-label">{k}</span><div className="k-val">{v}</div></div>)}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-accent btn-sm"><Icon name="doc" size={13} /> View</button>
          <button className="btn btn-sm"><Icon name="reset" size={13} /> Regenerate</button>
          <button className="btn btn-sm"><Icon name="download" size={13} /> Markdown</button>
          <button className="btn btn-sm btn-ghost"><Icon name="download" size={13} /> Export PDF</button>
        </div>
      </div>
      <div className="section-title">All report types</div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(280px,1fr))', gap: 14 }}>
        {reports.map(r => <div key={r} className="card card-pad" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}>
          <div><b style={{ fontFamily: 'var(--font-display)', fontWeight: 500 }}>{r}</b><div style={{ fontSize: 12, color: 'var(--d-text-3)', marginTop: 4 }}>Auto-generated</div></div>
          <Icon name="chevron" size={16} stroke="var(--d-text-3)" /></div>)}
      </div>
    </div>
  );
}
function CollectionsPage() {
  const cols = [['Reading List', 12], ['Reproduce Later', 5], ['Thesis Ideas', 8], ['Project Ideas', 6], ['Literature Review', 3], ['Favorite Papers', 21]];
  return (
    <div className="page fade-in">
      <PageHead crumb="Workspace" title="Collections" sub="Curated paper sets you can annotate, summarize, and turn into literature reviews.">
        <button className="btn btn-accent"><Icon name="plus" size={14} /> New collection</button>
      </PageHead>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(260px,1fr))', gap: 16 }}>
        {cols.map(([c, n]) => (
          <div key={c} className="card card-pad" style={{ cursor: 'pointer' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Icon name="bookmark" size={18} stroke="var(--accent)" /><span className="mono-label" style={{ color: 'var(--d-text-3)' }}>{n} papers</span>
            </div>
            <h3 style={{ fontFamily: 'var(--font-display)', fontWeight: 500, fontSize: 18, margin: '16px 0 6px' }}>{c}</h3>
            <div style={{ fontSize: 12.5, color: 'var(--d-text-3)' }}>Add · summarize · export · review</div>
          </div>
        ))}
      </div>
    </div>
  );
}
function SettingsPage() {
  const sections = [
    ['Model Settings', ['OpenRouter model', 'Max tokens', 'Temperature', 'Request timeout']],
    ['arXiv Settings', ['Categories', 'Papers per day', 'Fetch schedule', 'Full-text extraction']],
    ['Research Profile', ['Interests', 'Preferred conferences', 'Compute budget', 'Project preference']],
    ['Memory Settings', ['Enable knowledge graph', 'Enable semantic memory', 'Embedding model', 'Memory cleanup']],
    ['Export Settings', ['Markdown', 'PDF', 'CSV', 'JSON']],
  ];
  return (
    <div className="page fade-in">
      <PageHead crumb="Configuration" title="Settings" />
      <div style={{ display: 'grid', gap: 16, maxWidth: 760 }}>
        <PersonalMemoryPanel />
        {sections.map(([t, items]) => (
          <div key={t} className="card card-pad">
            <div className="section-title" style={{ fontSize: 15 }}>{t}</div>
            {items.map(it => (
              <div key={it} className="entity-stat" style={{ alignItems: 'center' }}>
                <span style={{ color: 'var(--d-text-2)' }}>{it}</span>
                <span className="toggle-chip on" style={{ pointerEvents: 'none', border: 'none', background: 'none', padding: 0 }}><span className="sw"></span></span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

// Browser-local personal memory controls (Dexie-backed)
function PersonalMemoryPanel() {
  const [stats, setStats] = React.useState({ saved: 0, ignored: 0, interactions: 0 });
  const [msg, setMsg] = React.useState('');

  const refresh = React.useCallback(() => {
    if (window.PersonalGraph && window.PersonalGraph.available) {
      window.PersonalGraph.counts().then(setStats).catch(() => {});
    }
  }, []);
  React.useEffect(refresh, [refresh]);

  const exportJson = async () => {
    if (!window.PersonalGraph?.available) return;
    const data = await window.PersonalGraph.exportPersonalGraph();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'researchradar-personal-memory.json'; a.click();
    URL.revokeObjectURL(url);
    setMsg('Exported personal memory to JSON');
    setTimeout(() => setMsg(''), 2500);
  };

  const clearAll = async () => {
    if (!window.PersonalGraph?.available) return;
    if (!window.confirm('Clear all browser-local personal memory? This cannot be undone.')) return;
    await window.PersonalGraph.clearPersonalGraph();
    refresh();
    setMsg('Personal memory cleared');
    setTimeout(() => setMsg(''), 2500);
  };

  const available = window.PersonalGraph && window.PersonalGraph.available;

  return (
    <div className="card card-pad">
      <div className="section-title" style={{ fontSize: 15 }}>My Personal Memory</div>
      <div style={{ fontSize: 13, color: 'var(--d-text-3)', marginBottom: 14 }}>
        Your research graph is stored privately in this browser. Only a compact context is shared with agents.
      </div>
      {!available && <div style={{ color: '#f87171', fontSize: 13 }}>Personal graph unavailable (Dexie not loaded).</div>}
      {available && (
        <>
          <div style={{ display: 'flex', gap: 24, marginBottom: 16 }}>
            <div><div style={{ fontSize: 24, fontWeight: 700, color: 'var(--accent)' }}>{stats.saved}</div><div style={{ fontSize: 12, color: 'var(--d-text-3)' }}>Saved papers</div></div>
            <div><div style={{ fontSize: 24, fontWeight: 700, color: 'var(--d-text)' }}>{stats.ignored}</div><div style={{ fontSize: 12, color: 'var(--d-text-3)' }}>Ignored</div></div>
            <div><div style={{ fontSize: 24, fontWeight: 700, color: 'var(--d-text)' }}>{stats.interactions}</div><div style={{ fontSize: 12, color: 'var(--d-text-3)' }}>Interactions</div></div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-sm" onClick={exportJson}>Export JSON</button>
            <button className="btn btn-sm btn-ghost" onClick={clearAll}>Clear memory</button>
            <button className="btn btn-sm btn-ghost" onClick={refresh}>Refresh</button>
          </div>
          {msg && <div style={{ marginTop: 10, fontSize: 12, color: 'var(--accent)' }}>{msg}</div>}
        </>
      )}
    </div>
  );
}

Object.assign(window, { MemoryPage, PaperToCodePage, ProjectBuilderPage, ReportsPage, CollectionsPage, SettingsPage, PersonalMemoryPanel });

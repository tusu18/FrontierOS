/* ResearchRadar — shared UI components */
const { useState, useEffect, useRef, useMemo } = React;

/* ---- Brand mark (radar) ---- */
function Mark({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 30 30" fill="none">
      <circle cx="15" cy="15" r="14" stroke="var(--accent)" strokeWidth="1.3" opacity=".5" />
      <circle cx="15" cy="15" r="8.5" stroke="var(--accent)" strokeWidth="1.3" opacity=".8" />
      <circle cx="15" cy="15" r="3" fill="var(--accent)" />
      <path d="M15 15 L27 6" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/* ---- Badge ---- */
const BADGE_VARIANT = {
  'High Opportunity': 'purple', 'Code Potential': 'cyan', 'Easy Reproduce': 'green',
  'High Compute': 'orange', 'Weak Evidence': 'rose', 'New Benchmark': 'cyan', 'Saturated Topic': 'gray',
};
function Badge({ children, variant }) {
  const v = variant || BADGE_VARIANT[children] || 'gray';
  return <span className={`badge badge-${v}`}>{children}</span>;
}

/* ---- Score pill ---- */
function Score({ label, value }) {
  const num = typeof value === 'number';
  const hi = num && value >= 8;
  return <span className={`score${hi ? ' hi' : ''}`}>{label} <b>{value}</b></span>;
}

/* ---- Sparkline ---- */
function Spark({ data, w = 70, hgt = 22, color = 'var(--accent)' }) {
  const min = Math.min(...data), max = Math.max(...data);
  const rng = max - min || 1;
  const pts = data.map((d, i) => `${(i / (data.length - 1)) * w},${hgt - ((d - min) / rng) * (hgt - 3) - 1.5}`).join(' ');
  return (
    <svg className="spark" width={w} height={hgt}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

/* ---- KPI card ---- */
function KpiCard({ kpi }) {
  return (
    <div className="card kpi">
      <div className="k-top">
        <span className="k-label">{kpi.label}</span>
        <Spark data={kpi.spark} color={kpi.dir === 'down' ? 'var(--rose)' : 'var(--accent)'} />
      </div>
      <div className="k-val">{kpi.value}</div>
      <span className={`k-delta ${kpi.dir}`}>{kpi.dir === 'up' ? '▲' : '▼'} {kpi.delta} today</span>
    </div>
  );
}

/* ---- Sidebar ---- */
function Sidebar({ page, setPage, cats, activeCats, toggleCat }) {
  const { NAV } = window.RR_DATA;
  const profile = ['LLM Agents', 'RAG', 'ML Systems', 'Computer Vision', 'Model Compression'];
  return (
    <aside className="sidebar">
      <div className="sb-brand"><Mark /> ResearchRadar</div>

      <nav className="sb-section">
        {NAV.map(n => (
          <button key={n.id} className={`nav-item${page === n.id ? ' active' : ''}`} onClick={() => setPage(n.id)}>
            <span className="ni-ic"><Icon name={n.icon} size={16} /></span>
            {n.label}
          </button>
        ))}
      </nav>

      <div className="sb-section">
        <div className="sb-cap">Tracked Categories</div>
        <div className="sb-chips">
          {cats.map(c => (
            <span key={c} className={`cat-chip${activeCats.includes(c) ? ' on' : ''}`} onClick={() => toggleCat(c)}>{c}</span>
          ))}
        </div>
      </div>

      <div className="sb-section">
        <div className="sb-cap">Research Profile</div>
        <div className="sb-chips">
          {profile.map(p => <span key={p} className="cat-chip" style={{ cursor: 'default' }}>{p}</span>)}
        </div>
      </div>

      <div className="sb-profile">
        <div className="av">AR</div>
        <div className="who"><b>Avery Reese</b><span>ML Research · Pro</span></div>
      </div>
    </aside>
  );
}

/* ---- Topbar ---- */
function Topbar({ onSearch }) {
  return (
    <header className="topbar">
      <div className="global-search" onClick={e => e.currentTarget.querySelector('input').focus()}>
        <Icon name="search" size={16} stroke="var(--d-text-3)" />
        <input placeholder='Ask Research Memory anything — “Find RAG papers with code from this week”'
          onKeyDown={e => { if (e.key === 'Enter' && e.target.value.trim()) onSearch(e.target.value.trim()); }} />
        <kbd>⌘K</kbd>
      </div>
      <div className="top-right">
        <span className="top-date">May 29, 2026 · 06:00 UTC</span>
        <span className="model-badge"><span className="led"></span> GPT-4o mini · OpenRouter</span>
        <button className="icon-btn"><Icon name="bell" size={16} /></button>
      </div>
    </header>
  );
}

/* ---- Paper card ---- */
function PaperCard({ paper, onOpen, onAction }) {
  const s = paper.scores;
  return (
    <div className="card paper-card" onClick={() => onOpen(paper)}>
      <div className="pc-badges">
        <Badge variant="blue">{paper.cat}</Badge>
        {paper.tags.map(t => <Badge key={t} variant="gray">{t}</Badge>)}
        {paper.badges.map(b => <Badge key={b}>{b}</Badge>)}
        {paper.code && <Badge variant="cyan">Code · {s.build}</Badge>}
      </div>
      <h3>{paper.title}</h3>
      <p className="pc-sum">{paper.summary}</p>
      <div className="pc-meta">{paper.authors.join(', ')} · {paper.date} · arXiv:{paper.id}</div>
      <div className="pc-scores">
        <Score label="Novelty" value={s.novelty} />
        <Score label="Impact" value={s.impact} />
        <Score label="Reprod." value={s.reprod} />
        <Score label="Build" value={s.build} />
        <Score label="Opp." value={s.opportunity} />
      </div>
      <div className="pc-tax"><b>Methods:</b> {paper.methods.join(', ')}</div>
      <div className="pc-tax"><b>Datasets:</b> {paper.datasets.join(', ')}</div>
      <div className="pc-actions" onClick={e => e.stopPropagation()}>
        <button className="btn btn-accent btn-sm" onClick={() => onOpen(paper)}><Icon name="doc" size={14} /> Deep Dive</button>
        <button className="btn btn-sm" onClick={() => onAction('code', paper)}><Icon name="code" size={14} /> Generate Code</button>
        <button className="btn btn-sm" onClick={() => onAction('save', paper)}><Icon name="bookmark" size={14} /> Add to Library</button>
        <button className="btn btn-sm btn-ghost" onClick={() => onAction('compare', paper)}><Icon name="compare" size={14} /> Compare</button>
      </div>
    </div>
  );
}

/* ---- Page header ---- */
function PageHead({ crumb, title, sub, children }) {
  return (
    <div className="page-head">
      {crumb && <div className="crumb">{crumb}</div>}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 20, flexWrap: 'wrap' }}>
        <div>
          <h1>{title}</h1>
          {sub && <p>{sub}</p>}
        </div>
        {children && <div style={{ display: 'flex', gap: 10 }}>{children}</div>}
      </div>
    </div>
  );
}

/* ---- Stub page ---- */
function StubPage({ icon, crumb, title, desc, feats }) {
  return (
    <div className="page fade-in">
      <PageHead crumb={crumb} title={title} />
      <div className="stub">
        <div>
          <div className="stub-ic"><Icon name={icon} size={28} /></div>
          <h2>{title} workspace</h2>
          <p>{desc}</p>
          <div className="feats">{feats.map(f => <span key={f}>{f}</span>)}</div>
          <div style={{ marginTop: 24 }}>
            <button className="btn btn-accent">Open {title} <Icon name="arrow" size={14} /></button>
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { Mark, Badge, Score, Spark, KpiCard, Sidebar, Topbar, PaperCard, PageHead, StubPage });

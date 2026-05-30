/* ResearchRadar — app root, routing, tweaks */
const { useState, useEffect, useCallback } = React;

const ACCENTS = {
  'Signal green': { a: '#2fcf9e', d: '#66e0bb' },
  'Deep teal': { a: '#14b8a6', d: '#5eead4' },
  'Electric violet': { a: '#a78bfa', d: '#c4b5fd' },
  'Arctic cyan': { a: '#34d9e0', d: '#7eebf0' },
};

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "accent": "Signal green",
  "theme": "dark",
  "display": "Space Grotesk",
  "density": "regular",
  "radius": 14
}/*EDITMODE-END*/;

function Toast({ msg }) {
  if (!msg) return null;
  return <div style={{ position: 'fixed', bottom: 26, left: '50%', transform: 'translateX(-50%)', background: 'var(--d-elev-2)', border: '1px solid var(--accent)', color: 'var(--d-text)', padding: '12px 20px', borderRadius: 999, fontSize: 14, zIndex: 200, boxShadow: '0 10px 30px rgba(0,0,0,.4)' }} className="fade-in"><Icon name="check" size={15} stroke="var(--accent)" /> {msg}</div>;
}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);

  // Parse URL params for deep-linking from landing page
  const _params = new URLSearchParams(window.location.search);
  const _initPage = _params.get('page') || 'dashboard';
  const _initAuth = _params.get('signup') === '1' ? 'signup' : _params.get('signin') === '1' ? 'login' : null;
  const _initPlan = _params.get('plan') || null;
  const _initCode = _params.get('code') || null;  // demo access code from landing page

  const [page, setPage] = useState(_initPage);
  const [paper, setPaper] = useState(null);
  const [activeCats, setActiveCats] = useState(['cs.CL', 'cs.AI', 'cs.LG', 'cs.CV']);
  const [toast, setToast] = useState('');
  // Show code-login modal if ?code= param present, otherwise show normal auth modal
  const [showAuthModal, setShowAuthModal] = useState(!!_initAuth || !!_initCode);
  const [authModalMode, setAuthModalMode] = useState(_initCode ? 'code' : (_initAuth || 'login'));
  const [showUpgradeModal, setShowUpgradeModal] = useState(!!_initPlan);

  // Pre-fill demo code into localStorage so AuthModal can pick it up
  useEffect(() => {
    if (_initCode && !localStorage.getItem('rr_token')) {
      // Auto-login with code
      fetch('/auth/login-with-code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: _initCode }),
      }).then(r => r.json()).then(data => {
        if (data.token) {
          localStorage.setItem('rr_token', data.token);
          localStorage.setItem('rr_user', JSON.stringify({
            id: data.user_id, email: data.email, full_name: data.full_name || '',
            is_admin: data.is_admin || false, plan: data.plan || 'free',
          }));
          window.location.href = '/app';
        }
      }).catch(() => {});
    }
  }, []);
  const { CATS } = window.RR_DATA;

  // apply tweaks
  useEffect(() => {
    const ac = ACCENTS[t.accent] || ACCENTS['Signal green'];
    const r = document.documentElement.style;
    r.setProperty('--accent', ac.a);
    r.setProperty('--n-dataset', ac.a);
    document.body.classList.toggle('light', t.theme === 'light');
    r.setProperty('--font-display', `'${t.display}', 'Space Grotesk', sans-serif`);
    r.setProperty('--radius-md', t.radius + 'px');
    r.setProperty('--pad', t.density === 'compact' ? '14px' : t.density === 'comfy' ? '26px' : '20px');
  }, [t]);

  const flash = useCallback((m) => { setToast(m); setTimeout(() => setToast(''), 1900); }, []);
  const openPaper = useCallback((p) => { setPaper(p); setPage('deepdive'); window.scrollTo(0, 0); }, []);
  const goto = useCallback((pg) => { setPage(pg); window.scrollTo(0, 0); }, []);

  // Records an interaction both to the browser-local personal graph and,
  // when signed in, to the server so recommendations can learn.
  // localId is used for the personal graph (string ok); dbId (integer) for the API.
  const recordInteraction = useCallback((localId, dbId, type, value = 1, meta = {}) => {
    try {
      if (window.PersonalGraph && window.PersonalGraph.available) {
        window.PersonalGraph.recordInteraction(localId, type, value, meta);
      }
    } catch (_) {}
    const token = localStorage.getItem('rr_token');
    if (token && Number.isInteger(dbId)) {
      fetch(`/papers/${dbId}/interaction`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body: JSON.stringify({ interaction_type: type, interaction_value: value, metadata: meta }),
      }).catch(() => {});
    }
  }, []);

  const onAction = useCallback((kind, p) => {
    const localId = p && (p.id || p.arxiv_id || p.db_id);
    const dbId    = p && (typeof p.db_id === 'number' ? p.db_id : (typeof p._db_id === 'number' ? p._db_id : null));
    const pid     = localId;
    const rec     = (type, value, meta) => recordInteraction(localId, dbId, type, value, meta);
    if (kind === 'open') {
      rec('viewed', 1, { title: p.title });
      openPaper(p);
    } else if (kind === 'code') {
      rec('generated_code', 2, { title: p.title });
      setPaper(p); goto('p2c');
    } else if (kind === 'save') {
      if (window.PersonalGraph?.available) window.PersonalGraph.savePaper(p);
      rec('saved', 2, { title: p.title });
      flash(`Saved "${(p.title || '').slice(0, 32)}…" to your library`);
    } else if (kind === 'ignore') {
      if (window.PersonalGraph?.available) window.PersonalGraph.ignorePaper(p);
      rec('ignored', -1, { title: p.title });
      flash('Paper hidden from your feed');
    } else if (kind === 'more') {
      if (window.PersonalGraph?.available) window.PersonalGraph.moreLikeThis(p);
      rec('more_like_this', 2, { title: p.title });
      flash('More like this — noted');
    } else if (kind === 'less') {
      if (window.PersonalGraph?.available) window.PersonalGraph.lessLikeThis(p);
      rec('less_like_this', -2, { title: p.title });
      flash('Less like this — noted');
    } else if (kind === 'compare') {
      flash('Added to comparison tray');
    } else if (kind === 'pdf' || kind === 'arxiv') {
      rec(kind === 'pdf' ? 'clicked_pdf' : 'clicked_arxiv', 1, { title: p.title });
    }
  }, [recordInteraction]);

  const toggleCat = (c) => setActiveCats(a => a.includes(c) ? a.filter(x => x !== c) : [...a, c]);
  const onSearch = (q) => { goto('memory'); flash('Asking research memory…'); };

  let view;
  switch (page) {
    case 'dashboard':   view = <DashboardPage setPage={goto} onOpen={openPaper} onAction={onAction} />; break;
    case 'daily':       view = <DailyPapersPage onOpen={openPaper} onAction={onAction} activeCats={activeCats} />; break;
    case 'deepdive':    view = <DeepDivePage paper={paper} onAction={onAction} setPage={goto} />; break;
    case 'memory':      view = <MemoryPage />; break;
    case 'graph':       view = <KnowledgeGraph />; break;
    case 'trends':      view = <TrendRadarPage setPage={goto} />; break;
    case 'gaps':        view = <GapsPage setPage={goto} />; break;
    case 'p2c':         view = <PaperToCodePage />; break;
    case 'builder':     view = <ProjectBuilderPage />; break;
    case 'reports':     view = <ReportsPage />; break;
    case 'collections': view = <CollectionsPage />; break;
    case 'settings':    view = <SettingsPage />; break;
    // ── v2 pages (plan-gated) ─────────────────────────────────────────────
    case 'foryou':      view = <ForYouPageGated onOpen={openPaper} onAction={onAction} />; break;
    case 'alerts':      view = <AlertsPageGated />; break;
    case 'digest':      view = <DigestPageGated />; break;
    case 'profile':     view = <ProfilePage />; break;
    case 'trust':       view = <TrustPageGated paper={paper} />; break;
    case 'admin':       view = <AdminPage />; break;
    case 'orchestrator': view = <OrchestratorPage />; break;
    case 'topics':      view = <SavedTopicsPage />; break;
    default:            view = <DashboardPage setPage={goto} onOpen={openPaper} onAction={onAction} />;
  }

  // Gate opens in signup mode if landing sent ?signup=1, else login
  const gateMode = _initAuth === 'signup' ? 'signup' : (_initCode ? 'code' : 'login');

  return (
    <AuthProvider>
      <AuthGate initialMode={gateMode}>
      <div className="app-shell">
        <Sidebar page={page} setPage={goto} cats={CATS} activeCats={activeCats} toggleCat={toggleCat} />
        <div className="main">
          <Topbar onSearch={onSearch} extra={<><PlanBadge /><AuthButton /></>} />
          {view}
        </div>
        <Toast msg={toast} />
        {showUpgradeModal && (
          <UpgradeModal currentPlan="free" onClose={() => setShowUpgradeModal(false)} onUpgraded={() => setShowUpgradeModal(false)} />
        )}

        <TweaksPanel>
          <TweakSection label="Theme" />
          <TweakColor label="Accent" value={(ACCENTS[t.accent] || {}).a}
            options={Object.values(ACCENTS).map(x => x.a)}
            onChange={(v) => { const name = Object.keys(ACCENTS).find(k => ACCENTS[k].a === v); setTweak('accent', name || 'Signal green'); }} />
          <TweakRadio label="Mode" value={t.theme} options={['dark', 'light']} onChange={(v) => setTweak('theme', v)} />
          <TweakSection label="Typography" />
          <TweakSelect label="Display font" value={t.display}
            options={['Space Grotesk', 'Hanken Grotesk', 'JetBrains Mono']} onChange={(v) => setTweak('display', v)} />
          <TweakSection label="Layout" />
          <TweakRadio label="Density" value={t.density} options={['compact', 'regular', 'comfy']} onChange={(v) => setTweak('density', v)} />
          <TweakSlider label="Card radius" value={t.radius} min={4} max={24} unit="px" onChange={(v) => setTweak('radius', v)} />
        </TweaksPanel>
      </div>
      </AuthGate>
    </AuthProvider>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

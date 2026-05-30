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
  const [page, setPage] = useState('dashboard');
  const [paper, setPaper] = useState(null);
  const [activeCats, setActiveCats] = useState(['cs.CL', 'cs.AI', 'cs.LG', 'cs.CV']);
  const [toast, setToast] = useState('');
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

  const onAction = useCallback((kind, p) => {
    if (kind === 'open') openPaper(p);
    else if (kind === 'code') { setPaper(p); goto('p2c'); }
    else if (kind === 'save') flash(`Added “${p.title.slice(0, 32)}…” to library`);
    else if (kind === 'compare') flash('Added to comparison tray');
  }, []);

  const toggleCat = (c) => setActiveCats(a => a.includes(c) ? a.filter(x => x !== c) : [...a, c]);

  const onSearch = (q) => { goto('memory'); flash('Asking research memory…'); };

  let view;
  switch (page) {
    case 'dashboard': view = <DashboardPage setPage={goto} onOpen={openPaper} onAction={onAction} />; break;
    case 'daily': view = <DailyPapersPage onOpen={openPaper} onAction={onAction} activeCats={activeCats} />; break;
    case 'deepdive': view = <DeepDivePage paper={paper} onAction={onAction} setPage={goto} />; break;
    case 'memory': view = <MemoryPage />; break;
    case 'graph': view = <KnowledgeGraph />; break;
    case 'trends': view = <TrendRadarPage setPage={goto} />; break;
    case 'gaps': view = <GapsPage setPage={goto} />; break;
    case 'p2c': view = <PaperToCodePage />; break;
    case 'builder': view = <ProjectBuilderPage />; break;
    case 'reports': view = <ReportsPage />; break;
    case 'collections': view = <CollectionsPage />; break;
    case 'settings': view = <SettingsPage />; break;
    default: view = <DashboardPage setPage={goto} onOpen={openPaper} onAction={onAction} />;
  }

  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={goto} cats={CATS} activeCats={activeCats} toggleCat={toggleCat} />
      <div className="main">
        <Topbar onSearch={onSearch} />
        {view}
      </div>
      <Toast msg={toast} />

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
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);

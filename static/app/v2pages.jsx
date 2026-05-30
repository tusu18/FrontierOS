/* ResearchRadar v2 — new pages: ForYou, Alerts, Digest, Profile, Trust, Admin */
/* All pages use the same design system as pages.jsx */

// ─── Auth utilities ────────────────────────────────────────────────────────

const AuthCtx = React.createContext({ user: null, token: null, setUser: () => {}, logout: () => {} });
const useAuth = () => React.useContext(AuthCtx);

function AuthProvider({ children }) {
  const [user, setUserState] = React.useState(() => {
    try { return JSON.parse(localStorage.getItem('rr_user') || 'null'); } catch { return null; }
  });
  const [token, setToken] = React.useState(() => localStorage.getItem('rr_token') || null);

  const setUser = React.useCallback((u, t) => {
    setUserState(u);
    setToken(t);
    if (u) {
      localStorage.setItem('rr_user', JSON.stringify(u));
      localStorage.setItem('rr_token', t);
    }
  }, []);

  const logout = React.useCallback(() => {
    setUserState(null);
    setToken(null);
    localStorage.removeItem('rr_user');
    localStorage.removeItem('rr_token');
  }, []);

  // Validate token on mount — if expired/invalid, clear it (SDC: never trust stale client state)
  const [validated, setValidated] = React.useState(!token);
  React.useEffect(() => {
    if (!token) { setValidated(true); return; }
    fetch('/me', { headers: { 'Authorization': `Bearer ${token}` } })
      .then(r => {
        if (!r.ok) throw new Error('invalid');
        return r.json();
      })
      .then(d => {
        // refresh stored user with authoritative server values
        const fresh = { id: d.id, email: d.email, full_name: d.full_name || '', is_admin: d.is_admin || false, plan: d.plan || 'free' };
        setUserState(fresh);
        localStorage.setItem('rr_user', JSON.stringify(fresh));
      })
      .catch(() => { logout(); })
      .finally(() => setValidated(true));
  }, []); // run once

  return (
    <AuthCtx.Provider value={{ user, token, setUser, logout, validated }}>
      {children}
    </AuthCtx.Provider>
  );
}

// ─── Auth Gate — blocks the whole app until authenticated ──────────────────
// Implements secure-by-design access control: the dashboard never renders
// for an unauthenticated visitor, regardless of how they reached /app.
function AuthGate({ children, initialMode = 'login' }) {
  const { user, validated } = useAuth();

  if (!validated) {
    return (
      <div style={{ position: 'fixed', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--d-bg)', color: 'var(--d-text-3)', fontSize: 14 }}>
        Verifying session…
      </div>
    );
  }

  if (user) return children;

  // Not authenticated — show branded gate with a non-dismissable auth modal
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'var(--d-bg)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 24 }}>
      <div style={{ maxWidth: 460, marginBottom: 28 }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 10, marginBottom: 18 }}>
          <Mark />
          <span style={{ fontSize: 22, fontWeight: 800, color: 'var(--d-text)' }}>FrontierOS</span>
        </div>
        <h2 style={{ color: 'var(--d-text)', fontSize: 24, margin: '0 0 10px', fontWeight: 700 }}>Access is invite-only</h2>
        <p style={{ color: 'var(--d-text-3)', fontSize: 15, lineHeight: 1.6, margin: 0 }}>
          FrontierOS is in private beta. Sign in, create an account, or enter the access code we emailed you to continue.
        </p>
      </div>
      <AuthModal dismissable={false} initialMode={initialMode} onClose={() => {}} />
    </div>
  );
}

// Fetch with auth token
function apiFetch(path, opts = {}, token = null) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return fetch(path, { ...opts, headers });
}

// ─── Login / Signup modal ─────────────────────────────────────────────────

function AuthModal({ onClose, initialMode = 'login', dismissable = true }) {
  // mode: 'login' | 'signup' | 'code'
  const [mode, setMode] = React.useState(initialMode);
  const [email, setEmail]       = React.useState('');
  const [password, setPassword] = React.useState('');
  const [fullName, setFullName] = React.useState('');
  const [code, setCode]         = React.useState('');
  const [error, setError]       = React.useState('');
  const [loading, setLoading]   = React.useState(false);
  const [demoCode, setDemoCode] = React.useState(null); // shown after signup
  const { setUser } = useAuth();

  const tabStyle = (active) => ({
    flex: 1, padding: '8px 0', background: 'none', border: 'none',
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    color: active ? 'var(--accent)' : 'var(--d-text-3)',
    cursor: 'pointer', fontSize: 13, fontWeight: 600, transition: 'all .2s',
  });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError('');
    try {
      let url, body;
      if (mode === 'code') {
        url  = '/auth/login-with-code';
        body = { code: code.trim().toUpperCase() };
      } else if (mode === 'login') {
        url  = '/auth/login';
        body = { email, password };
      } else {
        url  = '/auth/signup';
        body = { email, password, full_name: fullName };
      }
      const res  = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');

      const userData = { id: data.user_id, email: data.email, full_name: data.full_name || '', is_admin: data.is_admin || false, plan: data.plan || 'free' };
      if (mode === 'signup' && data.demo_code) {
        setDemoCode(data.demo_code);
        setUser(userData, data.token);
        return; // keep modal open to show the code
      }
      setUser(userData, data.token);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const codeBannerStyle = {
    background: 'rgba(47,207,158,.1)', border: '1px solid var(--accent)',
    borderRadius: 12, padding: 20, textAlign: 'center', marginBottom: 4,
  };

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={(e) => { if (dismissable && e.target === e.currentTarget) onClose(); }}
    >
      <div style={{ background: 'var(--d-elev-1)', border: '1px solid var(--d-border)', borderRadius: 18, padding: 32, width: 400, maxWidth: '92vw' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--d-text)' }}>FrontierOS</div>
          {dismissable && (
            <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--d-text-3)', cursor: 'pointer', fontSize: 18 }}>×</button>
          )}
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', marginBottom: 24, borderBottom: '1px solid var(--d-border)' }}>
          {[['login','Sign in'],['signup','Sign up'],['code','Access code']].map(([m, label]) => (
            <button key={m} style={tabStyle(mode === m)} onClick={() => { setMode(m); setError(''); setDemoCode(null); }}>{label}</button>
          ))}
        </div>

        {/* After signup: show the demo code prominently */}
        {demoCode && (
          <div>
            <div style={codeBannerStyle}>
              <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginBottom: 8, letterSpacing: '0.05em', textTransform: 'uppercase' }}>Your Demo Access Code</div>
              <div style={{ fontFamily: 'monospace', fontSize: 28, fontWeight: 800, color: 'var(--accent)', letterSpacing: '0.15em' }}>{demoCode}</div>
              <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginTop: 8 }}>Save this code — use it to log in without a password</div>
            </div>
            <button className="btn btn-accent" style={{ width: '100%', marginTop: 16 }} onClick={onClose}>Enter FrontierOS →</button>
          </div>
        )}

        {/* Form */}
        {!demoCode && (
          <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {mode === 'code' ? (
              <>
                <div style={{ fontSize: 13, color: 'var(--d-text-3)', marginBottom: 4 }}>
                  Enter your access code (e.g. <span style={{ fontFamily: 'monospace', color: 'var(--accent)' }}>FO-ABC123</span>)
                </div>
                <input
                  type="text" placeholder="FO-XXXXXX" value={code}
                  onChange={e => setCode(e.target.value)} required
                  style={{ ...inputStyle, fontFamily: 'monospace', fontSize: 16, letterSpacing: '0.1em', textAlign: 'center' }}
                />
              </>
            ) : (
              <>
                {mode === 'signup' && (
                  <input type="text" placeholder="Full name" value={fullName} onChange={e => setFullName(e.target.value)} style={inputStyle} />
                )}
                <input type="email" placeholder="Email" value={email} onChange={e => setEmail(e.target.value)} required style={inputStyle} />
                <input type="password" placeholder="Password" value={password} onChange={e => setPassword(e.target.value)} required style={inputStyle} />
              </>
            )}
            {error && <div style={{ color: '#f87171', fontSize: 13, padding: '6px 10px', background: 'rgba(248,113,113,.1)', borderRadius: 6 }}>{error}</div>}
            <button type="submit" disabled={loading} className="btn btn-accent" style={{ marginTop: 4 }}>
              {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : mode === 'signup' ? 'Create account & get code' : 'Enter with code'}
            </button>
          </form>
        )}

        {!demoCode && mode === 'login' && (
          <div style={{ marginTop: 14, textAlign: 'center', fontSize: 12, color: 'var(--d-text-3)' }}>
            No account? <button onClick={() => setMode('signup')} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>Sign up</button>
            {' · '}
            <button onClick={() => setMode('code')} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer' }}>Use access code</button>
          </div>
        )}
      </div>
    </div>
  );
}

const inputStyle = {
  background: 'var(--d-elev-2)', border: '1px solid var(--d-border)',
  borderRadius: 8, padding: '10px 14px', color: 'var(--d-text)',
  fontSize: 14, outline: 'none', width: '100%', boxSizing: 'border-box'
};

// ─── Auth guard button ─────────────────────────────────────────────────────

function AuthButton() {
  const { user, logout } = useAuth();
  const [showModal, setShowModal] = React.useState(false);
  if (user) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 13, color: 'var(--d-text-2)' }}>{user.email}</span>
        <button className="btn btn-sm btn-ghost" onClick={logout}>Sign out</button>
      </div>
    );
  }
  return (
    <>
      <button className="btn btn-accent btn-sm" onClick={() => setShowModal(true)}>Sign in</button>
      {showModal && <AuthModal onClose={() => setShowModal(false)} />}
    </>
  );
}

// ─── useApi hook ───────────────────────────────────────────────────────────

function useApi(url, { deps = [], token = null, method = 'GET', body = null } = {}) {
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    setLoading(true);
    setError(null);
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);
    fetch(url, opts)
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(setData)
      .catch(e => setError(e.detail || String(e)))
      .finally(() => setLoading(false));
  }, deps); // eslint-disable-line

  return { data, loading, error };
}

// ─── Shared confidence badge ───────────────────────────────────────────────

const confidenceColors = {
  high_confidence:   { bg: 'rgba(47,207,158,.15)', color: '#2fcf9e', label: 'High confidence' },
  medium_confidence: { bg: 'rgba(251,191,36,.15)', color: '#fbbf24', label: 'Medium confidence' },
  low_confidence:    { bg: 'rgba(248,113,113,.15)', color: '#f87171', label: 'Low confidence' },
  missing_evidence:  { bg: 'rgba(148,163,184,.1)',  color: '#94a3b8', label: 'Missing evidence' },
  llm_inferred:      { bg: 'rgba(167,139,250,.15)', color: '#a78bfa', label: 'LLM inferred' },
};

function ConfidenceBadge({ label }) {
  const c = confidenceColors[label] || confidenceColors.medium_confidence;
  return (
    <span style={{
      background: c.bg, color: c.color, borderRadius: 4, padding: '2px 8px',
      fontSize: 11, fontWeight: 600, letterSpacing: '0.03em'
    }}>{c.label}</span>
  );
}

// ─── FOR YOU page ─────────────────────────────────────────────────────────

function ForYouPage({ onOpen, onAction }) {
  const { user, token } = useAuth();
  const [showAuth, setShowAuth] = React.useState(false);
  const [feed, setFeed] = React.useState([]);
  const [loading, setLoading] = React.useState(true);
  const [genLoading, setGenLoading] = React.useState(false);
  const [msg, setMsg] = React.useState('');

  // Re-rank server candidates using the browser-local personal graph:
  //   final = global*0.55 + topic_match*0.25 + saved_sim*0.10 + more_boost*0.10 - ignored - seen
  const rerank = React.useCallback(async (items) => {
    if (!window.PersonalGraph || !window.PersonalGraph.available) return items;
    try {
      const ctx = await window.PersonalGraph.getPersonalContextForAgent();
      const ignored = new Set((ctx.ignored_paper_ids || []).map(String));
      const topics  = (ctx.saved_topics || []).map((t) => t.toLowerCase());
      const seen     = new Set((ctx.recent_interactions || []).filter(r => r.type === 'viewed').map(r => String(r.paperId)));

      const scored = items
        .filter((rec) => !ignored.has(String(rec.paper_id)) && !ignored.has(String(rec.db_id)))
        .map((rec) => {
          const paper = window.RR_DATA.PAPERS.find(p => p.db_id === rec.paper_id || p.id === rec.paper_id) || {};
          const tags = (paper.tags || []).concat(paper.methods || []).map((t) => (t || '').toLowerCase());
          const topicMatch = topics.length ? tags.filter((t) => topics.some((tp) => t.includes(tp) || tp.includes(t))).length / Math.max(topics.length, 1) : 0;
          const global = rec.score || 0;
          const seenPenalty = seen.has(String(rec.paper_id)) ? 0.1 : 0;
          const local_final = global * 0.55 + topicMatch * 0.25 + (rec.saved_sim || 0) * 0.10 - seenPenalty;
          const reasons = (rec.reasons || []).slice();
          if (topicMatch > 0) reasons.push('matches your saved topics');
          return { ...rec, score: Math.max(0, Math.min(1, local_final)), reasons, _personalized: topicMatch > 0 };
        })
        .sort((a, b) => b.score - a.score);
      return scored;
    } catch (_) {
      return items;
    }
  }, []);

  const load = React.useCallback(() => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    apiFetch('/papers/for-you?limit=20', {}, token)
      .then(r => r.json())
      .then(async (items) => setFeed(await rerank(Array.isArray(items) ? items : [])))
      .catch(() => setFeed([]))
      .finally(() => setLoading(false));
  }, [token, rerank]);

  React.useEffect(load, [load]);

  const runRecs = async () => {
    if (!token) { setShowAuth(true); return; }
    setGenLoading(true);
    try {
      const res = await apiFetch('/api/actions/fetch', { method: 'POST', body: JSON.stringify({}) }, token);
      setMsg('Fetched new papers. Scoring recommendations…');
      await load();
    } catch { setMsg('Error generating recommendations.'); }
    setGenLoading(false);
  };

  const feedback = async (paperId, type) => {
    if (!token) { setShowAuth(true); return; }
    await apiFetch(`/papers/${paperId}/interaction`, {
      method: 'POST', body: JSON.stringify({ interaction_type: type })
    }, token);
    setMsg(`Marked as ${type}`);
    setTimeout(() => setMsg(''), 2000);
  };

  if (!user) return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="For You" sub="Your personalized research feed powered by ResearchRadar Memory." />
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        
        <h3 style={{ color: 'var(--d-text)', marginBottom: 8 }}>Sign in to unlock your personal feed</h3>
        <p style={{ color: 'var(--d-text-3)', marginBottom: 24 }}>
          ResearchRadar learns what you read, save, and build — then surfaces the most relevant papers.
        </p>
        <button className="btn btn-accent" onClick={() => setShowAuth(true)}>Sign in / Create account</button>
      </div>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </div>
  );

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="For You" sub="Personalized papers ranked by your interests, behavior, and global trends." />
      {msg && <div style={{ background: 'rgba(47,207,158,.1)', border: '1px solid var(--accent)', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: 'var(--accent)' }}>{msg}</div>}
      <div style={{ marginBottom: 20, display: 'flex', gap: 10 }}>
        <button className="btn btn-accent" onClick={runRecs} disabled={genLoading}>
          {genLoading ? 'Scoring…' : 'Refresh recommendations'}
        </button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--d-text-3)' }}>Scoring papers for you…</div>
      ) : feed.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--d-text-3)' }}>
          No recommendations yet. Fetch papers and build the knowledge graph first.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {feed.map(rec => (
            <RecCard key={rec.paper_id} rec={rec} onOpen={onOpen} onFeedback={feedback} />
          ))}
        </div>
      )}
    </div>
  );
}

function RecCard({ rec, onOpen, onFeedback }) {
  const paper = window.RR_DATA.PAPERS.find(p => p.db_id === rec.paper_id || p.id === rec.paper_id) || {
    id: rec.paper_id, title: rec.title || `Paper #${rec.paper_id}`, summary: '', tags: [], scores: {}
  };
  const score = Math.round(rec.score * 100);
  const scoreColor = score >= 75 ? '#2fcf9e' : score >= 50 ? '#fbbf24' : '#94a3b8';

  return (
    <div className="card" style={{ borderRadius: 12, padding: 18, cursor: 'pointer' }}>
      <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
        <div style={{ flexShrink: 0, width: 52, height: 52, borderRadius: 10, background: 'var(--d-elev-2)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', border: `2px solid ${scoreColor}` }}>
          <span style={{ fontSize: 16, fontWeight: 700, color: scoreColor }}>{score}</span>
          <span style={{ fontSize: 9, color: 'var(--d-text-3)', letterSpacing: '0.05em' }}>MATCH</span>
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--d-text)', marginBottom: 4, lineHeight: 1.4 }}
            onClick={() => onOpen && onOpen(paper)}>
            {paper.title}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {(rec.reasons || []).map((r, i) => (
              <span key={i} style={{ background: 'rgba(47,207,158,.1)', color: 'var(--accent)', fontSize: 11, padding: '2px 8px', borderRadius: 4 }}>✓ {r}</span>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-sm btn-ghost" onClick={() => onFeedback(rec.paper_id, 'liked')}>More like this</button>
            <button className="btn btn-sm btn-ghost" onClick={() => onFeedback(rec.paper_id, 'ignored')}>Less like this</button>
            <button className="btn btn-sm btn-ghost" onClick={() => onFeedback(rec.paper_id, 'saved')}>Save</button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── ALERTS page ──────────────────────────────────────────────────────────

function AlertsPage() {
  const { user, token } = useAuth();
  const [showAuth, setShowAuth] = React.useState(false);
  const [alerts, setAlerts] = React.useState([]);
  const [ruleCount, setRuleCount] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [running, setRunning] = React.useState(false);
  const [initRules, setInitRules] = React.useState(false);

  const loadAlerts = React.useCallback(() => {
    if (!token) { setLoading(false); return; }
    setLoading(true);
    Promise.all([
      apiFetch('/alerts', {}, token).then(r => r.json()).catch(() => []),
      apiFetch('/alerts/rules', {}, token).then(r => r.json()).catch(() => []),
    ]).then(([a, rules]) => {
      setAlerts(Array.isArray(a) ? a : []);
      setRuleCount(Array.isArray(rules) ? rules.length : 0);
    }).finally(() => setLoading(false));
  }, [token]);

  React.useEffect(loadAlerts, [loadAlerts]);

  const createDefaultRules = async () => {
    setInitRules(true);
    await apiFetch('/alerts/ensure-default-rules', { method: 'POST' }, token);
    await loadAlerts();
    setInitRules(false);
  };

  const markRead = async (id) => {
    await apiFetch(`/alerts/${id}/mark-read`, { method: 'POST' }, token);
    setAlerts(prev => prev.map(a => a.id === id ? { ...a, read: true } : a));
  };

  const runAgent = async () => {
    setRunning(true);
    await apiFetch('/alerts/run', { method: 'POST' }, token).catch(() => {});
    await loadAlerts();
    setRunning(false);
  };

  const typeIcon = { topic_spike: '', paper_match: '', research_gap: '', code_available: '' };
  const typeColor = { topic_spike: '#2fcf9e', paper_match: '#a78bfa', research_gap: '#fbbf24', code_available: '#38bdf8' };

  if (!user) return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Alerts" sub="Get notified when topics spike, papers match, or gaps emerge." />
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        
        <h3 style={{ color: 'var(--d-text)', marginBottom: 8 }}>Sign in to manage alerts</h3>
        <button className="btn btn-accent" onClick={() => setShowAuth(true)}>Sign in</button>
      </div>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </div>
  );

  const unread = alerts.filter(a => !a.read).length;

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Alerts"
        sub={`${unread} unread alert${unread !== 1 ? 's' : ''}. Powered by topic velocity and paper matching.`} />
      {ruleCount === 0 && (
        <div className="card" style={{ padding: 16, borderRadius: 12, marginBottom: 16, border: '1px solid #fbbf24' }}>
          <div style={{ fontSize: 14, color: 'var(--d-text-2)', marginBottom: 10 }}>
            Default alert rules are not initialized.
          </div>
          <button className="btn btn-accent btn-sm" onClick={createDefaultRules} disabled={initRules}>
            {initRules ? 'Creating…' : 'Create Default Alert Rules'}
          </button>
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
        <button className="btn btn-accent" onClick={runAgent} disabled={running}>
          {running ? 'Running…' : 'Run alert scan'}
        </button>
        <button className="btn btn-ghost" onClick={loadAlerts}>Refresh</button>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--d-text-3)' }}>Loading alerts…</div>
      ) : alerts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--d-text-3)' }}>
          No alerts yet. Set interests in your profile, then run the alert scan.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {alerts.map(a => {
            const ic = typeIcon[a.type] || '';
            const col = typeColor[a.type] || 'var(--accent)';
            return (
              <div key={a.id} className="card" style={{ borderRadius: 12, padding: 16, opacity: a.read ? 0.6 : 1, borderLeft: `3px solid ${col}` }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <span style={{ fontSize: 16 }}>{ic}</span>
                      <span style={{ fontWeight: 600, color: 'var(--d-text)', fontSize: 14 }}>{a.title}</span>
                      {!a.read && <span style={{ background: col, borderRadius: 99, padding: '1px 7px', fontSize: 10, color: '#000', fontWeight: 700 }}>NEW</span>}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--d-text-3)' }}>{a.message}</div>
                    <div style={{ fontSize: 11, color: 'var(--d-text-3)', marginTop: 4 }}>{a.created_at}</div>
                  </div>
                  {!a.read && (
                    <button className="btn btn-sm btn-ghost" onClick={() => markRead(a.id)}>Mark read</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ─── DIGEST page ──────────────────────────────────────────────────────────

function DigestPage() {
  const { user, token } = useAuth();
  const [showAuth, setShowAuth] = React.useState(false);
  const [digest, setDigest] = React.useState(null);
  const [generating, setGenerating] = React.useState(false);
  const [digestType, setDigestType] = React.useState('daily');

  const loadLatest = React.useCallback(() => {
    if (!token) return;
    apiFetch('/digests/daily', {}, token).then(r => r.json()).then(setDigest).catch(() => {});
  }, [token]);

  React.useEffect(loadLatest, [loadLatest]);

  const generate = async () => {
    if (!token) { setShowAuth(true); return; }
    setGenerating(true);
    try {
      const res = await apiFetch(`/digests/generate?digest_type=${digestType}`, { method: 'POST' }, token);
      const data = await res.json();
      setDigest(data);
    } catch { /* ignore */ }
    setGenerating(false);
  };

  if (!user) return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Digest" sub="Your personalized daily and weekly research briefing." />
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        
        <h3 style={{ color: 'var(--d-text)', marginBottom: 8 }}>Sign in for your digest</h3>
        <button className="btn btn-accent" onClick={() => setShowAuth(true)}>Sign in</button>
      </div>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </div>
  );

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Digest" sub="Your personalized daily and weekly research briefing." />
      <div style={{ display: 'flex', gap: 10, marginBottom: 24, alignItems: 'center' }}>
        <select value={digestType} onChange={e => setDigestType(e.target.value)}
          style={{ ...inputStyle, width: 'auto', padding: '8px 14px' }}>
          <option value="daily">Daily digest</option>
          <option value="weekly">Weekly "What changed in your field"</option>
        </select>
        <button className="btn btn-accent" onClick={generate} disabled={generating}>
          {generating ? 'Generating…' : 'Generate digest'}
        </button>
      </div>

      {digest ? (
        <div className="card" style={{ padding: 28, borderRadius: 14 }}>
          {digest.subject && (
            <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--d-text)', marginBottom: 16, lineHeight: 1.3 }}>
              {digest.subject}
            </div>
          )}
          <div style={{ fontFamily: 'monospace', fontSize: 13, color: 'var(--d-text-2)', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
            {digest.content || digest.content_markdown || 'No content yet.'}
          </div>
        </div>
      ) : (
        <div style={{ textAlign: 'center', padding: 60, color: 'var(--d-text-3)' }}>
          No digest yet. Generate your first one above.
        </div>
      )}
    </div>
  );
}

// ─── PROFILE page ─────────────────────────────────────────────────────────

const INTEREST_OPTIONS = [
  'LLM Agents', 'RAG', 'NLP', 'Computer Vision', 'Robotics',
  'AI Safety', 'ML Systems', 'Model Compression', 'Inference Optimization',
  'Databases', 'Security', 'Software Engineering', 'Theory',
  'HCI', 'Multimodal AI', 'Reinforcement Learning',
];

const GOAL_OPTIONS = [
  'Read important papers', 'Find research gaps', 'Build portfolio projects',
  'Generate code from papers', 'Track my research area',
  'Prepare literature reviews', 'Find thesis ideas', 'Find startup ideas',
];

const COMPUTE_OPTIONS = ['CPU only', 'Colab free', 'Single GPU', 'Multi-GPU', 'Cloud budget available'];

function ProfilePage() {
  const { user, token, logout } = useAuth();
  const [showAuth, setShowAuth] = React.useState(false);
  const [profile, setProfile] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    if (!token) return;
    apiFetch('/me', {}, token).then(r => r.json()).then(setProfile).catch(() => {});
  }, [token]);

  const toggle = (field, val) => {
    setProfile(p => {
      const arr = p[field] || [];
      return { ...p, [field]: arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val] };
    });
  };

  const save = async () => {
    setSaving(true);
    await apiFetch('/me/profile', {
      method: 'PUT',
      body: JSON.stringify({
        interests: profile.interests,
        preferred_topics: profile.preferred_topics,
        research_goals: profile.research_goals,
        ignored_topics: profile.ignored_topics,
        compute_budget: profile.compute_budget,
        alert_frequency: profile.alert_frequency,
        digest_frequency: profile.digest_frequency,
      }),
    }, token);
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  if (!user) return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Profile" sub="Your research interests, goals, and notification settings." />
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        
        <h3 style={{ color: 'var(--d-text)', marginBottom: 8 }}>Sign in to manage your profile</h3>
        <button className="btn btn-accent" onClick={() => setShowAuth(true)}>Sign in</button>
      </div>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </div>
  );

  if (!profile) return (
    <div className="page fade-in" style={{ textAlign: 'center', padding: 60, color: 'var(--d-text-3)' }}>Loading profile…</div>
  );

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Research Profile" sub={`${user.email} · Personalize your ResearchRadar experience.`} />

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, maxWidth: 800 }}>
        {/* Interests */}
        <div className="card" style={{ padding: 20, borderRadius: 12, gridColumn: '1 / -1' }}>
          <div style={{ fontWeight: 600, color: 'var(--d-text)', marginBottom: 12 }}>Research Interests</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {INTEREST_OPTIONS.map(opt => (
              <button key={opt}
                onClick={() => toggle('interests', opt)}
                style={{
                  border: `1px solid ${profile.interests?.includes(opt) ? 'var(--accent)' : 'var(--d-border)'}`,
                  background: profile.interests?.includes(opt) ? 'rgba(47,207,158,.15)' : 'var(--d-elev-2)',
                  color: profile.interests?.includes(opt) ? 'var(--accent)' : 'var(--d-text-3)',
                  borderRadius: 6, padding: '6px 12px', fontSize: 12, cursor: 'pointer',
                }}>
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* Goals */}
        <div className="card" style={{ padding: 20, borderRadius: 12 }}>
          <div style={{ fontWeight: 600, color: 'var(--d-text)', marginBottom: 12 }}>Research Goals</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {GOAL_OPTIONS.map(opt => (
              <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', color: 'var(--d-text-2)', fontSize: 13 }}>
                <input type="checkbox" checked={profile.research_goals?.includes(opt)} onChange={() => toggle('research_goals', opt)} />
                {opt}
              </label>
            ))}
          </div>
        </div>

        {/* Compute + Notifications */}
        <div className="card" style={{ padding: 20, borderRadius: 12 }}>
          <div style={{ fontWeight: 600, color: 'var(--d-text)', marginBottom: 12 }}>Compute Budget</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 20 }}>
            {COMPUTE_OPTIONS.map(opt => (
              <label key={opt} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', color: 'var(--d-text-2)', fontSize: 13 }}>
                <input type="radio" name="compute" checked={profile.compute_budget === opt} onChange={() => setProfile(p => ({ ...p, compute_budget: opt }))} />
                {opt}
              </label>
            ))}
          </div>
          <div style={{ fontWeight: 600, color: 'var(--d-text)', marginBottom: 10 }}>Digest Frequency</div>
          <select value={profile.digest_frequency || 'daily'} onChange={e => setProfile(p => ({ ...p, digest_frequency: e.target.value }))}
            style={{ ...inputStyle, width: '100%' }}>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="never">Never</option>
          </select>
        </div>
      </div>

      <div style={{ marginTop: 20, display: 'flex', gap: 12 }}>
        <button className="btn btn-accent" onClick={save} disabled={saving}>
          {saving ? 'Saving…' : saved ? '✓ Saved!' : 'Save profile'}
        </button>
        <button className="btn btn-ghost" onClick={logout}>Sign out</button>
      </div>
    </div>
  );
}

// ─── TRUST & EVIDENCE page ────────────────────────────────────────────────

function TrustPage({ paper = null }) {
  const { PAPERS } = window.RR_DATA;
  const [selectedId, setSelectedId] = React.useState(paper?.id || null);
  const [evidence, setEvidence] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [extracting, setExtracting] = React.useState(false);
  const { token } = useAuth();

  const loadEvidence = React.useCallback((pid) => {
    if (!pid) return;
    setLoading(true);
    fetch(`/papers/${pid}/evidence`)
      .then(r => r.json()).then(setEvidence).catch(() => setEvidence([]))
      .finally(() => setLoading(false));
  }, []);

  React.useEffect(() => { if (selectedId) loadEvidence(selectedId); }, [selectedId, loadEvidence]);

  const extract = async () => {
    if (!selectedId) return;
    setExtracting(true);
    await apiFetch(`/papers/${selectedId}/extract-evidence`, { method: 'POST' }, token)
      .catch(() => {});
    await loadEvidence(selectedId);
    setExtracting(false);
  };

  const selectedPaper = PAPERS.find(p => p.id === selectedId);

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Trust & Evidence" sub="See the evidence behind every claim ResearchRadar makes." />

      <div style={{ marginBottom: 16 }}>
        <select value={selectedId || ''} onChange={e => setSelectedId(Number(e.target.value))}
          style={{ ...inputStyle, maxWidth: 500 }}>
          <option value="">Select a paper…</option>
          {PAPERS.map(p => <option key={p.id} value={p.id}>{p.title?.slice(0, 80)}</option>)}
        </select>
      </div>

      {selectedPaper && (
        <div className="card" style={{ padding: 16, borderRadius: 10, marginBottom: 16, borderLeft: '3px solid var(--accent)' }}>
          <div style={{ fontWeight: 600, color: 'var(--d-text)' }}>{selectedPaper.title}</div>
          <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginTop: 4 }}>{selectedPaper.cat} · {selectedPaper.date}</div>
        </div>
      )}

      {selectedId && (
        <div style={{ display: 'flex', gap: 10, marginBottom: 20 }}>
          <button className="btn btn-accent" onClick={extract} disabled={extracting}>
            {extracting ? 'Extracting…' : 'Extract evidence'}
          </button>
          <button className="btn btn-ghost" onClick={() => loadEvidence(selectedId)}>↺ Refresh</button>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--d-text-3)' }}>Loading evidence…</div>
      ) : evidence.length === 0 && selectedId ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--d-text-3)' }}>
          No evidence spans yet. Click "Extract evidence" to analyze this paper.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {evidence.map((e, i) => (
            <EvidenceCard key={i} span={e} />
          ))}
        </div>
      )}
    </div>
  );
}

function EvidenceCard({ span }) {
  const [open, setOpen] = React.useState(false);
  return (
    <div className="card" style={{ borderRadius: 12, overflow: 'hidden' }}>
      <div style={{ padding: '14px 18px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
        onClick={() => setOpen(o => !o)}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', color: 'var(--accent)', textTransform: 'uppercase' }}>{span.field}</span>
            <ConfidenceBadge label={span.uncertainty} />
          </div>
          <div style={{ fontSize: 14, color: 'var(--d-text)', lineHeight: 1.4 }}>{span.claim}</div>
        </div>
        <span style={{ color: 'var(--d-text-3)', fontSize: 16, marginLeft: 12 }}>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid var(--d-border)', padding: '14px 18px', background: 'var(--d-elev-2)' }}>
          <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginBottom: 6 }}>Why does ResearchRadar say this?</div>
          {span.evidence ? (
            <blockquote style={{ borderLeft: '3px solid var(--accent)', paddingLeft: 12, margin: '0 0 10px', color: 'var(--d-text-2)', fontSize: 13, fontStyle: 'italic', lineHeight: 1.6 }}>
              "{span.evidence}"
            </blockquote>
          ) : (
            <div style={{ color: 'var(--d-text-3)', fontSize: 13 }}>No direct quote found in abstract.</div>
          )}
          <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--d-text-3)' }}>
            <span>Section: {span.section}</span>
            <span>Confidence: {Math.round((span.confidence || 0) * 100)}%</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── ADMIN page ───────────────────────────────────────────────────────────

// Admin System Health — holistic status of every subsystem.
function SystemHealthPanel() {
  const [h, setH] = React.useState(null);
  const [emailMsg, setEmailMsg] = React.useState('');
  const load = () => fetch('/admin/system-health').then(r => r.json()).then(setH).catch(() => {});
  React.useEffect(load, []);

  const testEmail = async () => {
    setEmailMsg('Sending…');
    try {
      const r = await fetch('/admin/test-email', { method: 'POST' });
      const d = await r.json();
      setEmailMsg(d.message || (d.ok ? 'Test email sent' : 'Send failed'));
    } catch (e) { setEmailMsg('Error: ' + e.message); }
  };

  if (!h) return null;

  const dot = (ok) => ({ display: 'inline-block', width: 9, height: 9, borderRadius: 999, background: ok ? '#2fcf9e' : '#f87171', marginRight: 7 });
  const integ = h.integrations || {};
  const data  = h.data || {};
  const rows = [
    ['Database', `${h.database?.backend}`, h.database?.connected],
    ['OpenRouter (LLM)', integ.openrouter_reachable ? 'reachable' : (integ.openrouter_note || (integ.openrouter_configured ? 'key set, API failing' : 'missing')), integ.openrouter_reachable],
    ['SMTP email', integ.smtp_configured ? integ.smtp_host : 'not configured (code shown in UI)', integ.smtp_configured],
    ['Memory backend', integ.memory_backend, true],
    ['Qdrant', integ.memory_backend === 'qdrant' ? (integ.qdrant_reachable ? 'reachable' : 'unreachable') : 'not used', integ.memory_backend !== 'qdrant' || integ.qdrant_reachable],
    ['Local embeddings', integ.local_embeddings ? 'on' : 'off (keyword/hybrid-lite)', true],
  ];
  const metrics = [
    ['Papers', data.papers], ['Summaries pending', data.summaries_pending],
    ['Evidence spans', data.evidence_spans], ['KG entities', data.kg_entities],
    ['KG edges', data.kg_edges], ['Alert rules', data.alert_rules],
    ['Alerts', data.alerts], ['Interactions', data.user_interactions],
  ];

  return (
    <div className="card" style={{ padding: 20, borderRadius: 12, marginBottom: 24 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
        <div style={{ fontWeight: 600, color: 'var(--d-text)' }}>System Health</div>
        <button className="btn btn-sm btn-ghost" onClick={load}>Refresh</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px,1fr))', gap: 8, marginBottom: 16 }}>
        {rows.map(([label, val, ok]) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', fontSize: 13 }}>
            <span style={dot(ok)}></span>
            <span style={{ color: 'var(--d-text-2)' }}>{label}:</span>
            <span style={{ color: 'var(--d-text-3)', marginLeft: 6 }}>{val}</span>
          </div>
        ))}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
        {metrics.map(([label, val]) => (
          <div key={label} style={{ background: 'var(--d-elev-2)', borderRadius: 8, padding: '10px 12px', textAlign: 'center' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: label === 'Summaries pending' && val > 0 ? '#fbbf24' : 'var(--d-text)' }}>{val ?? '—'}</div>
            <div style={{ fontSize: 11, color: 'var(--d-text-3)' }}>{label}</div>
          </div>
        ))}
      </div>
      {h.integrations?.smtp_configured && (
        <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
          <button className="btn btn-sm" onClick={testEmail}>Send test email</button>
          {emailMsg && <span style={{ fontSize: 12, color: 'var(--d-text-3)' }}>{emailMsg}</span>}
        </div>
      )}
      {h.orchestrator?.last_run_at && (
        <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginTop: 12 }}>
          Last orchestrator run: {new Date(h.orchestrator.last_run_at).toLocaleString()} · Failed jobs: {h.orchestrator.failed_jobs}
        </div>
      )}
    </div>
  );
}

function AdminPage() {
  const [queueData, setQueueData]   = React.useState(null);
  const [kgStats, setKgStats]       = React.useState(null);
  const [loading, setLoading]       = React.useState(true);
  const [fetchLimit, setFetchLimit] = React.useState(100);
  const [fetching, setFetching]     = React.useState(false);
  const [analyzing, setAnalyzing]   = React.useState(false);
  const [running, setRunning]       = React.useState(false);
  const [pending, setPending]       = React.useState(null);
  const [processing, setProcessing] = React.useState(false);
  const [msg, setMsg]               = React.useState('');
  const [msgType, setMsgType]       = React.useState('ok'); // 'ok' | 'err'

  const notify = (text, type = 'ok') => { setMsg(text); setMsgType(type); };

  const load = () => {
    setLoading(true);
    Promise.all([
      fetch('/admin/fetch-queue').then(r => r.json()).catch(() => null),
      fetch('/admin/kg-stats').then(r => r.json()).catch(() => null),
      fetch('/api/actions/pending-count').then(r => r.json()).catch(() => null),
    ]).then(([q, kg, pc]) => { setQueueData(q); setKgStats(kg); setPending(pc?.pending ?? null); setLoading(false); });
  };
  React.useEffect(load, []);

  const processPending = async () => {
    setProcessing(true);
    try {
      const res  = await fetch('/api/actions/summarize?limit=25', { method: 'POST' });
      const data = await res.json();
      notify(`Processed ${data.processed}: ${data.summarized} summarized, ${data.evidence_extracted} evidence, ${data.kg_extracted} KG.`);
      load();
    } catch (e) { notify('Error: ' + e.message, 'err'); }
    setProcessing(false);
  };

  const ensureRules = async () => {
    try {
      const res  = await fetch('/admin/ensure-alert-rules', { method: 'POST' });
      const data = await res.json();
      notify(`Alert rules: created ${data.rules_created} for ${data.users_updated} users.`);
    } catch (e) { notify('Error: ' + e.message, 'err'); }
  };

  const fetchMore = async () => {
    setFetching(true);
    try {
      const res  = await fetch('/admin/fetch-more', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ limit: fetchLimit }) });
      const data = await res.json();
      notify(data.message || 'Done.');
      load();
    } catch (e) { notify('Error: ' + e.message, 'err'); }
    setFetching(false);
  };

  const runAnalysis = async () => {
    setAnalyzing(true);
    try {
      const res  = await fetch('/admin/run-analysis', { method: 'POST' });
      const data = await res.json();
      notify(data.message || 'Analysis complete.');
      load();
    } catch (e) { notify('Error: ' + e.message, 'err'); }
    setAnalyzing(false);
  };

  const runAllAgents = async () => {
    setRunning(true);
    try {
      const res  = await fetch('/admin/run-all-agents', { method: 'POST' });
      const data = await res.json();
      const parts = Object.entries(data).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(' | ');
      notify('Agents done. ' + parts);
      load();
    } catch (e) { notify('Error: ' + e.message, 'err'); }
    setRunning(false);
  };

  const reprocess = async () => {
    const res  = await fetch('/admin/reprocess-failed', { method: 'POST' });
    const data = await res.json();
    notify(`Reset ${data.reset} failed items.`);
    load();
  };

  const stats = queueData?.stats || {};
  const statusColors = { queued: '#94a3b8', fetched: '#38bdf8', summarized: '#a78bfa', kg_extracted: '#2fcf9e', failed: '#f87171', skipped_duplicate: '#fbbf24' };
  const msgColor = msgType === 'err' ? '#f87171' : 'var(--accent)';
  const msgBg    = msgType === 'err' ? 'rgba(248,113,113,.1)' : 'rgba(47,207,158,.1)';

  return (
    <div className="page fade-in">
      <PageHead crumb="Admin" title="Admin · Control Panel" sub="Monitor system health, process pending papers, and run agents." />
      {msg && <div style={{ background: msgBg, border: `1px solid ${msgColor}`, borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 13, color: msgColor }}>{msg}</div>}

      <SystemHealthPanel />

      {/* Pending papers */}
      <div className="card" style={{ padding: 20, borderRadius: 12, marginBottom: 24 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--d-text)' }}>Pending Papers</div>
            <div style={{ fontSize: 13, color: 'var(--d-text-3)', marginTop: 4 }}>
              {pending === null ? 'Loading…' : pending === 0 ? 'All papers processed.' : `${pending} papers awaiting summarization.`}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-accent" onClick={processPending} disabled={processing || pending === 0}>
              {processing ? 'Processing…' : 'Process Pending Papers'}
            </button>
            <button className="btn btn-ghost" onClick={ensureRules}>Create default alert rules</button>
          </div>
        </div>
      </div>

      {/* KG Stats */}
      {kgStats && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 12, color: 'var(--d-text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Knowledge Graph</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
            {[['Entities', kgStats.entities, '#2fcf9e'], ['Edges', kgStats.edges, '#38bdf8'], ['Trend records', kgStats.trends, '#a78bfa'], ['Semantic chunks', kgStats.semantic, '#fbbf24']].map(([label, val, color]) => (
              <div key={label} className="card" style={{ padding: '14px 16px', borderRadius: 10, textAlign: 'center', borderTop: `3px solid ${color}` }}>
                <div style={{ fontSize: 24, fontWeight: 700, color }}>{val ?? '—'}</div>
                <div style={{ fontSize: 11, color: 'var(--d-text-3)', textTransform: 'uppercase', marginTop: 4 }}>{label}</div>
              </div>
            ))}
          </div>
          {kgStats.top_entities?.length > 0 && (
            <div className="card" style={{ borderRadius: 10, padding: '14px 18px', marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--d-text-3)', marginBottom: 8, fontWeight: 600 }}>Top KG entities</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {kgStats.top_entities.map(e => (
                  <span key={e.name} style={{ background: 'var(--d-elev-2)', borderRadius: 6, padding: '3px 10px', fontSize: 12, color: 'var(--d-text-2)' }}>
                    {e.name} <span style={{ color: 'var(--d-text-3)' }}>×{e.freq}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Controls */}
      <div className="card" style={{ padding: 20, borderRadius: 12, marginBottom: 24 }}>
        <div style={{ fontWeight: 600, color: 'var(--d-text)', marginBottom: 14 }}>Pipeline Controls</div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 13, color: 'var(--d-text-3)' }}>Fetch limit</span>
            <input type="number" value={fetchLimit} onChange={e => setFetchLimit(Number(e.target.value))} min={10} max={500}
              style={{ ...inputStyle, width: 80 }} />
          </div>
          <button className="btn btn-accent" onClick={fetchMore} disabled={fetching}>
            {fetching ? '⏳ Fetching…' : '⬇ Fetch papers'}
          </button>
          <button className="btn btn-accent" onClick={runAnalysis} disabled={analyzing}
            style={{ background: 'rgba(167,139,250,.15)', borderColor: '#a78bfa', color: '#a78bfa' }}>
            {analyzing ? 'Analysing…' : 'Refresh KG'}
          </button>
          <button className="btn btn-accent" onClick={runAllAgents} disabled={running}
            style={{ background: 'rgba(56,189,248,.15)', borderColor: '#38bdf8', color: '#38bdf8' }}>
            {running ? 'Running…' : 'Run all agents'}
          </button>
          <button className="btn btn-ghost" onClick={reprocess}>Reprocess failed</button>
          <button className="btn btn-ghost" onClick={load}>↺ Refresh</button>
        </div>
      </div>

      {/* Queue stats */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 12, color: 'var(--d-text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 10 }}>Fetch Queue</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
          {Object.entries(stats).filter(([k]) => k !== 'total').map(([k, v]) => (
            <div key={k} className="card" style={{ padding: '12px 14px', borderRadius: 10, textAlign: 'center', borderTop: `3px solid ${statusColors[k] || 'var(--accent)'}` }}>
              <div style={{ fontSize: 20, fontWeight: 700, color: statusColors[k] || 'var(--accent)' }}>{v}</div>
              <div style={{ fontSize: 10, color: 'var(--d-text-3)', textTransform: 'uppercase', marginTop: 3, letterSpacing: '0.04em' }}>{k.replace(/_/g, ' ')}</div>
            </div>
          ))}
          <div className="card" style={{ padding: '12px 14px', borderRadius: 10, textAlign: 'center', borderTop: '3px solid var(--accent)' }}>
            <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--accent)' }}>{stats.total || 0}</div>
            <div style={{ fontSize: 10, color: 'var(--d-text-3)', textTransform: 'uppercase', marginTop: 3 }}>TOTAL</div>
          </div>
        </div>
      </div>

      {/* Queue table */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40, color: 'var(--d-text-3)' }}>Loading…</div>
      ) : (
        <div className="card" style={{ borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ background: 'var(--d-elev-2)', borderBottom: '1px solid var(--d-border)' }}>
                  {['ID', 'arXiv ID', 'Status', 'Category', 'Priority', 'Attempts', 'Created'].map(h => (
                    <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--d-text-3)', fontWeight: 600, letterSpacing: '0.04em' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(queueData?.items || []).map(item => (
                  <tr key={item.id} style={{ borderBottom: '1px solid var(--d-border)' }}>
                    <td style={{ padding: '9px 14px', color: 'var(--d-text-3)' }}>{item.id}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--accent)', fontFamily: 'monospace' }}>{item.arxiv_id}</td>
                    <td style={{ padding: '9px 14px' }}>
                      <span style={{ color: statusColors[item.status] || 'var(--d-text)', fontSize: 11, fontWeight: 600 }}>{item.status}</span>
                    </td>
                    <td style={{ padding: '9px 14px', color: 'var(--d-text-2)' }}>{item.category}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--d-text-3)' }}>{item.priority}</td>
                    <td style={{ padding: '9px 14px', color: item.attempts > 2 ? '#f87171' : 'var(--d-text-3)' }}>{item.attempts}</td>
                    <td style={{ padding: '9px 14px', color: 'var(--d-text-3)', fontFamily: 'monospace', fontSize: 11 }}>{item.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── SAVED TOPICS page ────────────────────────────────────────────────────

function SavedTopicsPage() {
  const { user, token } = useAuth();
  const [showAuth, setShowAuth] = React.useState(false);
  const [topics, setTopics] = React.useState([]);
  const [newTopic, setNewTopic] = React.useState('');
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(() => {
    if (!token) { setLoading(false); return; }
    apiFetch('/topics/saved', {}, token).then(r => r.json()).then(setTopics).catch(() => setTopics([]))
      .finally(() => setLoading(false));
  }, [token]);

  React.useEffect(load, [load]);

  const addTopic = async () => {
    if (!newTopic.trim() || !token) return;
    await apiFetch('/topics/save', { method: 'POST', body: JSON.stringify({ topic_name: newTopic }) }, token);
    setNewTopic('');
    load();
  };

  const deleteTopic = async (id) => {
    await apiFetch(`/topics/${id}`, { method: 'DELETE' }, token);
    setTopics(prev => prev.filter(t => t.id !== id));
  };

  const { TRENDS, GAPS } = window.RR_DATA;

  if (!user) return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Saved Topics" sub="Track research topics and get notified when they spike." />
      <div style={{ textAlign: 'center', padding: '60px 0' }}>
        
        <button className="btn btn-accent" onClick={() => setShowAuth(true)}>Sign in</button>
      </div>
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </div>
  );

  return (
    <div className="page fade-in">
      <PageHead crumb="v2" title="Saved Topics" sub="Track research topics and get notified when they spike." />

      <div style={{ display: 'flex', gap: 10, marginBottom: 24 }}>
        <input type="text" placeholder="Add a topic (e.g. RAG, LLM Agents, LoRA)" value={newTopic}
          onChange={e => setNewTopic(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addTopic()}
          style={{ ...inputStyle, maxWidth: 320 }} />
        <button className="btn btn-accent" onClick={addTopic}>+ Add</button>
      </div>

      {topics.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 24 }}>
          {topics.map(t => (
            <div key={t.id} style={{ background: 'var(--d-elev-1)', border: '1px solid var(--d-border)', borderRadius: 8, padding: '8px 14px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ color: 'var(--d-text)', fontSize: 13 }}>{t.topic}</span>
              {t.alert_enabled && <span style={{ color: 'var(--accent)', fontSize: 11 }}></span>}
              <button onClick={() => deleteTopic(t.id)} style={{ background: 'none', border: 'none', color: 'var(--d-text-3)', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>✕</button>
            </div>
          ))}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
        <div>
          <div className="section-title" style={{ marginBottom: 12 }}>Trending Topics in Your Areas</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(TRENDS || []).slice(0, 8).map((tr, i) => (
              <div key={i} className="card" style={{ padding: '10px 14px', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--d-text)' }}>{tr.name}</span>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span style={{ fontSize: 11, color: tr.trend > 0 ? '#2fcf9e' : '#f87171' }}>
                    {tr.trend > 0 ? '+' : ''}{tr.trend || 0}%
                  </span>
                  <button className="btn btn-sm btn-ghost" onClick={() => setNewTopic(tr.name)}>+ Track</button>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="section-title" style={{ marginBottom: 12 }}>Open Research Gaps</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {(GAPS || []).slice(0, 8).map((g, i) => (
              <div key={i} className="card" style={{ padding: '10px 14px', borderRadius: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: 13, color: 'var(--d-text)' }}>{g.title}</span>
                <button className="btn btn-sm btn-ghost" onClick={() => setNewTopic(g.title?.slice(0, 40))}>+ Track</button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
// PLAN / FREEMIUM LAYER
// ═══════════════════════════════════════════════════════════════════════════

// Plan feature matrix
const PLAN_FEATURES = {
  free: {
    label: 'Free',
    price: '$0',
    color: '#94a3b8',
    limits: {
      papers_per_day: 50,
      p2c_per_day: 3,
      saved_papers: 10,
    },
    features: [
      '50 papers/day',
      'Basic summaries',
      'Knowledge graph (read-only)',
      'Trend radar',
      'Research gaps (top 5)',
      '3 paper-to-code/day',
      'Weekly public digest',
    ],
    locked: ['foryou', 'alerts', 'digest', 'trust', 'topics'],
  },
  pro: {
    label: 'Pro',
    price: '$15',
    period: '/month',
    color: '#2fcf9e',
    badge: 'Most popular',
    features: [
      'Everything in Free',
      '200 papers/day tracking',
      'Personalized For You feed',
      'Topic spike alerts',
      'Daily & weekly digest',
      'Full evidence-backed summaries',
      'Unlimited paper-to-code',
      'Research gap tracker',
      'Saved topics & collections',
      'Export to Markdown',
    ],
    locked: [],
  },
  lab: {
    label: 'Lab',
    price: '$149',
    period: '/month',
    color: '#a78bfa',
    badge: 'Teams',
    features: [
      'Everything in Pro',
      '500+ papers/day',
      'Shared team memory',
      'Team collections & annotations',
      'Slack/email alerts',
      'Admin dashboard',
      'Weekly lab research brief',
      'Private PDF uploads',
      'Literature review builder',
      'API access',
      'Custom tracked topics',
    ],
    locked: [],
  },
};

// Upgrade Gate — wraps any Pro/Lab-only feature
function UpgradeGate({ requiredPlan = 'pro', children, feature = '' }) {
  const { user, token } = useAuth();
  const [showModal, setShowModal] = React.useState(false);
  const [showAuth, setShowAuth] = React.useState(false);

  // Refresh user plan from /me
  const [plan, setPlan] = React.useState(user?.plan || 'free');
  React.useEffect(() => {
    if (!token) return;
    apiFetch('/me', {}, token).then(r => r.json())
      .then(d => setPlan(d.plan || 'free')).catch(() => {});
  }, [token]);

  const planOrder = { free: 0, pro: 1, lab: 2, admin: 99 };
  const hasAccess = planOrder[plan] >= planOrder[requiredPlan];

  if (!user) return (
    <>
      <GateWall
        title={`Sign in to access ${feature || 'this feature'}`}
        sub="Create your free account to get started."
        cta="Sign in / Sign up"
        onCta={() => setShowAuth(true)}
        plan={requiredPlan}
      />
      {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
    </>
  );

  if (!hasAccess) return (
    <>
      <GateWall
        title={`${PLAN_FEATURES[requiredPlan]?.label || 'Pro'} feature`}
        sub={`Upgrade to ${PLAN_FEATURES[requiredPlan]?.label} to unlock ${feature || 'this feature'}.`}
        cta={`Upgrade to ${PLAN_FEATURES[requiredPlan]?.label}`}
        onCta={() => setShowModal(true)}
        plan={requiredPlan}
      />
      {showModal && <UpgradeModal currentPlan={plan} onClose={() => setShowModal(false)} onUpgraded={p => { setPlan(p); setShowModal(false); }} />}
    </>
  );

  return children;
}

function GateWall({ title, sub, cta, onCta, plan }) {
  const p = PLAN_FEATURES[plan] || PLAN_FEATURES.pro;
  return (
    <div style={{
      textAlign: 'center', padding: '70px 20px',
      background: 'var(--d-elev-1)', borderRadius: 16,
      border: `1px solid ${p.color}33`,
    }}>
      
      <h3 style={{ color: 'var(--d-text)', fontSize: 20, marginBottom: 8, fontWeight: 600 }}>{title}</h3>
      <p style={{ color: 'var(--d-text-3)', fontSize: 14, marginBottom: 24, maxWidth: 360, margin: '0 auto 24px' }}>{sub}</p>
      <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
        <button className="btn btn-accent" onClick={onCta} style={{ background: p.color, borderColor: p.color }}>{cta}</button>
        <a href="/" className="btn btn-ghost" style={{ textDecoration: 'none', lineHeight: '1.6' }}>View plans</a>
      </div>
      <div style={{ marginTop: 20, display: 'flex', flexWrap: 'wrap', gap: 8, justifyContent: 'center' }}>
        {(p.features || []).slice(0, 5).map((f, i) => (
          <span key={i} style={{ background: `${p.color}15`, color: p.color, borderRadius: 4, padding: '3px 10px', fontSize: 12 }}>✓ {f}</span>
        ))}
      </div>
    </div>
  );
}

function UpgradeModal({ currentPlan, onClose, onUpgraded }) {
  const { token } = useAuth();
  const [upgrading, setUpgrading] = React.useState(null);
  const [error, setError] = React.useState('');

  const upgrade = async (plan) => {
    setUpgrading(plan);
    setError('');
    try {
      const res = await apiFetch('/me/upgrade-plan', {
        method: 'POST',
        body: JSON.stringify({ plan }),
      }, token);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Upgrade failed');
      onUpgraded(plan);
    } catch (err) {
      setError(err.message);
    } finally {
      setUpgrading(null);
    }
  };

  const plans = ['pro', 'lab'];

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.75)', zIndex: 1001, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
      <div style={{ background: 'var(--d-bg)', border: '1px solid var(--d-border)', borderRadius: 20, padding: 36, maxWidth: 720, width: '100%', maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
          <div>
            <h2 style={{ color: 'var(--d-text)', margin: 0, fontSize: 22 }}>Upgrade ResearchRadar</h2>
            <p style={{ color: 'var(--d-text-3)', fontSize: 13, margin: '6px 0 0' }}>Current plan: <b style={{ color: 'var(--accent)' }}>{(currentPlan || 'free').toUpperCase()}</b></p>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--d-text-3)', cursor: 'pointer', fontSize: 20 }}>✕</button>
        </div>

        {error && <div style={{ color: '#f87171', fontSize: 13, marginBottom: 16, background: 'rgba(248,113,113,.1)', padding: '8px 14px', borderRadius: 8 }}>{error}</div>}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          {plans.map(planKey => {
            const p = PLAN_FEATURES[planKey];
            const isCurrentOrLower = currentPlan === planKey;
            return (
              <div key={planKey} style={{
                border: `1.5px solid ${isCurrentOrLower ? 'var(--d-border)' : p.color}`,
                borderRadius: 14, padding: 24, position: 'relative',
                background: isCurrentOrLower ? 'var(--d-elev-1)' : `${p.color}08`,
              }}>
                {p.badge && (
                  <div style={{ position: 'absolute', top: -10, left: '50%', transform: 'translateX(-50%)', background: p.color, color: '#000', fontSize: 11, fontWeight: 700, padding: '2px 12px', borderRadius: 99, letterSpacing: '0.04em' }}>{p.badge}</div>
                )}
                <div style={{ color: p.color, fontWeight: 700, fontSize: 13, letterSpacing: '0.06em', marginBottom: 6 }}>{p.label.toUpperCase()}</div>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 16 }}>
                  <span style={{ fontSize: 32, fontWeight: 700, color: 'var(--d-text)' }}>{p.price}</span>
                  <span style={{ color: 'var(--d-text-3)', fontSize: 13 }}>{p.period}</span>
                </div>
                <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 20px', display: 'flex', flexDirection: 'column', gap: 7 }}>
                  {p.features.map((f, i) => (
                    <li key={i} style={{ fontSize: 13, color: 'var(--d-text-2)', display: 'flex', gap: 7, alignItems: 'flex-start' }}>
                      <span style={{ color: p.color, flexShrink: 0 }}>✓</span> {f}
                    </li>
                  ))}
                </ul>
                <button
                  className="btn"
                  disabled={isCurrentOrLower || upgrading === planKey}
                  onClick={() => upgrade(planKey)}
                  style={{
                    width: '100%', background: isCurrentOrLower ? 'var(--d-elev-2)' : p.color,
                    borderColor: isCurrentOrLower ? 'var(--d-border)' : p.color,
                    color: isCurrentOrLower ? 'var(--d-text-3)' : '#000',
                    fontWeight: 600, padding: '10px 0',
                  }}>
                  {isCurrentOrLower ? 'Current plan' : upgrading === planKey ? 'Activating…' : `Activate ${p.label}`}
                </button>
                {!isCurrentOrLower && <p style={{ fontSize: 11, color: 'var(--d-text-3)', textAlign: 'center', marginTop: 8 }}>Demo: instant activation. Stripe in production.</p>}
              </div>
            );
          })}
        </div>

        <div style={{ marginTop: 24, padding: 16, background: 'var(--d-elev-1)', borderRadius: 10, fontSize: 13, color: 'var(--d-text-3)', lineHeight: 1.6 }}>
          <b style={{ color: 'var(--d-text-2)' }}>Student discount:</b> Pro at $7/month available — contact us with your .edu email.<br />
          <b style={{ color: 'var(--d-text-2)' }}>Custom reports</b> from $199 · Enterprise from $5,000/year — <a href="mailto:hello@researchradar.ai" style={{ color: 'var(--accent)' }}>contact us</a>
        </div>
      </div>
    </div>
  );
}

// Plan badge shown in the topbar/profile area
function PlanBadge() {
  const { user, token } = useAuth();
  const [plan, setPlan] = React.useState(user?.plan || 'free');
  const [showUpgrade, setShowUpgrade] = React.useState(false);

  React.useEffect(() => {
    if (!token) return;
    apiFetch('/me', {}, token).then(r => r.json())
      .then(d => setPlan(d.plan || 'free')).catch(() => {});
  }, [token]);

  if (!user) return null;
  const p = PLAN_FEATURES[plan] || PLAN_FEATURES.free;
  return (
    <>
      <button
        onClick={() => plan === 'free' ? setShowUpgrade(true) : null}
        style={{
          background: `${p.color}20`, color: p.color, border: `1px solid ${p.color}60`,
          borderRadius: 6, padding: '3px 10px', fontSize: 11, fontWeight: 700,
          letterSpacing: '0.06em', cursor: plan === 'free' ? 'pointer' : 'default',
        }}>
        {p.label.toUpperCase()}
        {plan === 'free' && <span style={{ marginLeft: 5, fontSize: 10 }}>↑ Upgrade</span>}
      </button>
      {showUpgrade && <UpgradeModal currentPlan={plan} onClose={() => setShowUpgrade(false)} onUpgraded={p => { setPlan(p); setShowUpgrade(false); }} />}
    </>
  );
}

// Override ForYouPage to gate Pro
const _ForYouPageRaw = typeof ForYouPage !== 'undefined' ? ForYouPage : () => null;
const ForYouPageGated = (props) => (
  <UpgradeGate requiredPlan="pro" feature="personalized For You feed">
    <_ForYouPageRaw {...props} />
  </UpgradeGate>
);

// Override AlertsPage
const _AlertsPageRaw = typeof AlertsPage !== 'undefined' ? AlertsPage : () => null;
const AlertsPageGated = (props) => (
  <UpgradeGate requiredPlan="pro" feature="topic spike alerts">
    <_AlertsPageRaw {...props} />
  </UpgradeGate>
);

// Override DigestPage
const _DigestPageRaw = typeof DigestPage !== 'undefined' ? DigestPage : () => null;
const DigestPageGated = (props) => (
  <UpgradeGate requiredPlan="pro" feature="personalized digest">
    <_DigestPageRaw {...props} />
  </UpgradeGate>
);

// Trust & Evidence is available to all users (free plan) — no gate
const _TrustPageRaw = typeof TrustPage !== 'undefined' ? TrustPage : () => null;
const TrustPageGated = (props) => <_TrustPageRaw {...props} />;

// ─── Orchestrator Status Page ─────────────────────────────────────────────
function OrchestratorPage() {
  const { token } = useAuth();
  const [status, setStatus]   = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [running, setRunning] = React.useState('');
  const [msg, setMsg]         = React.useState('');

  const load = () => {
    setLoading(true);
    fetch('/admin/orchestrator/status')
      .then(r => r.json()).then(setStatus).catch(() => {}).finally(() => setLoading(false));
  };
  React.useEffect(load, []);

  const runAgent = async (name) => {
    setRunning(name);
    try {
      const res  = await fetch(`/admin/orchestrator/run/${name}`, { method: 'POST' });
      const data = await res.json();
      setMsg(`${name}: ${data.status} (${data.elapsed_s}s) ${data.error || JSON.stringify(data.result || {}).slice(0,80)}`);
      load();
    } catch (e) { setMsg('Error: ' + e.message); }
    setRunning('');
  };

  const runAll = async () => {
    setRunning('all');
    try {
      const res  = await fetch('/admin/orchestrator/run-async', { method: 'POST' });
      const data = await res.json();
      setMsg(data.message || 'Running all agents in background...');
      setTimeout(load, 2000);
    } catch (e) { setMsg('Error: ' + e.message); }
    setRunning('');
  };

  const statusColor = { idle:'#94a3b8', running:'#fbbf24', ok:'#2fcf9e', error:'#f87171' };

  return (
    <div className="page fade-in">
      <PageHead crumb="Admin" title="Agent Orchestrator" sub="Monitor, trigger, and schedule all ResearchRadar agents." />
      {msg && <div style={{ background:'rgba(47,207,158,.08)', border:'1px solid var(--accent)', borderRadius:8, padding:'10px 14px', marginBottom:16, fontSize:13, color:'var(--accent)' }}>{msg}</div>}

      <div style={{ display:'flex', gap:10, marginBottom:24 }}>
        <button className="btn btn-accent" onClick={runAll} disabled={!!running}>
          {running === 'all' ? 'Running all...' : 'Run all agents (background)'}
        </button>
        <button className="btn btn-ghost" onClick={load}>Refresh status</button>
      </div>

      {loading ? (
        <div style={{ textAlign:'center', padding:40, color:'var(--d-text-3)' }}>Loading...</div>
      ) : (
        <>
          <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fill, minmax(320px,1fr))', gap:12, marginBottom:24 }}>
            {(status?.agents || []).map(agent => (
              <div key={agent.name} className="card" style={{ borderRadius:12, padding:'16px 18px', borderLeft:`3px solid ${statusColor[agent.status] || '#94a3b8'}` }}>
                <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:8 }}>
                  <div style={{ fontWeight:600, color:'var(--d-text)', fontSize:14 }}>{agent.name}</div>
                  <span style={{ background:statusColor[agent.status]+'22', color:statusColor[agent.status], fontSize:11, fontWeight:700, borderRadius:4, padding:'2px 8px' }}>{agent.status.toUpperCase()}</span>
                </div>
                <div style={{ fontSize:12, color:'var(--d-text-3)', marginBottom:10 }}>{agent.description}</div>
                <div style={{ display:'flex', gap:16, fontSize:11, color:'var(--d-text-3)', marginBottom:10 }}>
                  <span>Runs: {agent.run_count}</span>
                  <span style={{ color: agent.error_count > 0 ? '#f87171' : 'inherit' }}>Errors: {agent.error_count}</span>
                  <span>Last: {agent.last_run_at ? new Date(agent.last_run_at).toLocaleTimeString() : 'never'}</span>
                </div>
                {agent.last_error && <div style={{ fontSize:11, color:'#f87171', marginBottom:8, fontFamily:'monospace' }}>{agent.last_error}</div>}
                <button className="btn btn-ghost" style={{ fontSize:12, padding:'5px 12px' }}
                  onClick={() => runAgent(agent.name)}
                  disabled={running === agent.name}>
                  {running === agent.name ? 'Running...' : 'Run now'}
                </button>
              </div>
            ))}
          </div>

          {/* Scheduler jobs */}
          {status?.scheduler?.length > 0 && (
            <div className="card" style={{ borderRadius:12, padding:'16px 18px' }}>
              <div style={{ fontWeight:600, color:'var(--d-text)', marginBottom:12, fontSize:14 }}>Scheduled Jobs</div>
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                {status.scheduler.map(j => (
                  <div key={j.id} style={{ display:'flex', justifyContent:'space-between', fontSize:13 }}>
                    <span style={{ color:'var(--d-text)' }}>{j.id}</span>
                    <span style={{ color:'var(--accent)', fontFamily:'monospace', fontSize:12 }}>
                      {j.next_run ? new Date(j.next_run).toLocaleString() : 'not scheduled'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

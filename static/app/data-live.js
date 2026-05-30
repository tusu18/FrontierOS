/* data-live.js — loads real backend data into window.RR_DATA
 * Replaces the static data.js in the live app.
 * Uses a synchronous XHR so data is ready before Babel compiles the JSX.
 */
(function () {
  // ── Static fallback nav & cats (never empty so sidebar always renders) ──
  var NAV = [
    { id: 'dashboard',   label: 'Dashboard',        icon: 'grid'     },
    { id: 'daily',       label: 'Daily Papers',      icon: 'feed'     },
    { id: 'deepdive',    label: 'Paper Deep Dive',   icon: 'doc'      },
    { id: 'memory',      label: 'Research Memory',   icon: 'spark'    },
    { id: 'graph',       label: 'Knowledge Graph',   icon: 'graph'    },
    { id: 'trends',      label: 'Trend Radar',       icon: 'radar'    },
    { id: 'gaps',        label: 'Research Gaps',     icon: 'target'   },
    { id: 'p2c',         label: 'Paper-to-Code',     icon: 'code'     },
    { id: 'builder',     label: 'Project Builder',   icon: 'build'    },
    { id: 'reports',     label: 'Reports',           icon: 'report'   },
    { id: 'collections', label: 'Collections',       icon: 'bookmark' },
    { id: 'settings',    label: 'Settings',          icon: 'gear'     },
  ];
  var CATS = ['cs.CL','cs.AI','cs.LG','cs.CV','cs.IR','cs.RO','cs.SE','cs.NE','cs.DC','cs.CR'];

  var EMPTY = {
    CATS: CATS, PAPERS: [], TRENDS: [], GAPS: [],
    GRAPH: { nodes: [], links: [] },
    KPIS: [
      { label: 'Papers Today',   value: '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
      { label: 'Total Papers',   value: '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
      { label: 'Summarized',     value: '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
      { label: 'KG Entities',    value: '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
      { label: 'High-Opp Papers','value': '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
      { label: 'Code-Ready',     value: '–', delta: '–', dir: 'up', spark: [0,0,0,0,0,0,0] },
    ],
    INTEL: [
      { k: 'Status',          v: 'Loading research memory…', accent: 'gray' },
      { k: 'Source',          v: 'arXiv CS (live)',           accent: 'cyan' },
    ],
    NAV: NAV,
  };

  try {
    var xhr = new XMLHttpRequest();
    // Synchronous XHR — blocks until data arrives so JSX sees real data.
    xhr.open('GET', '/api/rr-data', false);
    xhr.send(null);
    if (xhr.status === 200) {
      var data = JSON.parse(xhr.responseText);
      // Always keep NAV intact even if API returns without it
      data.NAV = data.NAV && data.NAV.length ? data.NAV : NAV;
      data.CATS = data.CATS && data.CATS.length ? data.CATS : CATS;
      window.RR_DATA = data;
    } else {
      console.warn('[ResearchRadar] /api/rr-data returned', xhr.status, '— using empty dataset');
      window.RR_DATA = EMPTY;
    }
  } catch (e) {
    console.warn('[ResearchRadar] Could not load live data:', e);
    window.RR_DATA = EMPTY;
  }

  // ── Async refresh helpers exposed for JSX components ──────────────────────

  /**
   * window.RR_QUERY_MEMORY(query, callback)
   * Calls /api/memory/query and invokes callback({ lead, bullets, papers, ents, next })
   */
  window.RR_QUERY_MEMORY = function (query, callback) {
    fetch('/api/memory/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, limit: 15 }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { callback(null, data); })
      .catch(function (err) { callback(err, null); });
  };

  /**
   * window.RR_GENERATE_CODE(paperId, dbId, mode, callback)
   * Calls /api/code/generate
   */
  window.RR_GENERATE_CODE = function (paperId, dbId, mode, callback) {
    fetch('/api/code/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ paper_id: paperId, db_id: dbId, mode: mode, use_memory: true }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) { callback(null, data.code || ''); })
      .catch(function (err) { callback(err, null); });
  };

  /**
   * window.RR_FETCH_PAPERS(callback)
   * Triggers a fetch + summarize cycle
   */
  window.RR_FETCH_PAPERS = function (callback) {
    fetch('/api/actions/fetch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(function (r) { return r.json(); })
      .then(function (d) { callback(null, d); })
      .catch(function (e) { callback(e, null); });
  };

  /**
   * window.RR_GENERATE_REPORT(type, callback)
   */
  window.RR_GENERATE_REPORT = function (type, callback) {
    fetch('/api/reports/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_type: type, use_memory: true }),
    })
      .then(function (r) { return r.json(); })
      .then(function (d) { callback(null, d.content || ''); })
      .catch(function (e) { callback(e, null); });
  };

})();

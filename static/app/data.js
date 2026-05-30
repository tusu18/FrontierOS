/* ResearchRadar — live data loader
   Fetches real data from the API and populates window.RR_DATA.
   Falls back to empty structures if the API is unavailable.
*/
(function () {
  "use strict";

  const CATS = [
    'cs.CL','cs.AI','cs.LG','cs.CV','cs.IR',
    'cs.RO','cs.SE','cs.NE','cs.DC','cs.CR',
  ];

  const NAV = [
    { id:'dashboard',   label:'Dashboard',       icon:'home'    },
    { id:'daily',       label:'Daily Papers',    icon:'file'    },
    { id:'memory',      label:'Research Memory', icon:'brain'   },
    { id:'graph',       label:'Knowledge Graph', icon:'graph'   },
    { id:'trends',      label:'Trend Radar',     icon:'trend'   },
    { id:'gaps',        label:'Research Gaps',   icon:'gap'     },
    { id:'p2c',         label:'Paper to Code',   icon:'code'    },
    { id:'reports',     label:'Reports',         icon:'report'  },
    { id:'collections', label:'Collections',     icon:'folder'  },
    { id:'foryou',      label:'For You',         icon:'star'    },
    { id:'alerts',      label:'Alerts',          icon:'bell'    },
    { id:'digest',      label:'Digest',          icon:'mail'    },
    { id:'trust',       label:'Trust & Evidence',icon:'shield'  },
    { id:'admin',        label:'Admin',           icon:'settings'},
    { id:'orchestrator', label:'Orchestrator',   icon:'bolt'    },
    { id:'settings',     label:'Settings',       icon:'gear'    },
  ];

  // Scaffold: will be filled by fetchAll()
  window.RR_DATA = {
    CATS,
    NAV,
    PAPERS:   [],
    TRENDS:   [],
    GAPS:     [],
    GRAPH:    { nodes: [], links: [] },
    KPIS:     [],
    INTEL:    [],
    _loaded:  false,
    _error:   null,
  };

  // ── helpers ──────────────────────────────────────────────────────────────

  function xhrGet(url) {
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false); // synchronous — called before React mounts
      try {
        xhr.send();
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          reject(new Error('HTTP ' + xhr.status + ' from ' + url));
        }
      } catch (e) {
        reject(e);
      }
    });
  }

  function safeGet(url, fallback) {
    try {
      var xhr = new XMLHttpRequest();
      xhr.open('GET', url, false);
      xhr.send();
      if (xhr.status >= 200 && xhr.status < 300) {
        return JSON.parse(xhr.responseText);
      }
    } catch (_) {}
    return fallback;
  }

  // ── Transform API paper → RR_DATA PAPERS shape ───────────────────────────

  function transformPaper(p) {
    var s = p.summary || {};
    var scoreMap = { A: 9, B: 7, C: 5 };
    var reprod = p.reprod || (s.reproducibility_score >= 8 ? 'A' : s.reproducibility_score >= 5 ? 'B' : 'C');
    var badges = [];
    if ((s.opportunity_score || s.novelty_score || 0) >= 8) badges.push('High Opportunity');
    if ((s.code_generation_potential || 0) >= 8) badges.push('Code Potential');
    if ((s.reproducibility_score || 0) >= 8) badges.push('Easy Reproduce');
    if (p.is_new) badges.push('New Today');

    return {
      id:           p.arxiv_id || String(p.id),
      _db_id:       p.id,
      db_id:        p.id,
      title:        p.title  || 'Untitled',
      authors:      typeof p.authors === 'string'
                      ? p.authors.replace(/[[\]"]/g,'').split(',').map(function(a){return a.trim();}).filter(Boolean)
                      : (Array.isArray(p.authors) ? p.authors : []),
      cat:          p.primary_category || p.cat || 'cs.AI',
      date:         (p.published_date || p.date || '').slice(0,10),
      tags:         p.keywords || s.keywords || [],
      badges:       badges,
      summary:      s.one_line_summary || p.abstract || '',
      scores: {
        novelty:     s.novelty_score || 5,
        impact:      s.impact_score || 5,
        reprod:      reprod,
        build:       s.code_generation_potential || 5,
        opportunity: s.novelty_score || 5,
      },
      code:         (s.code_generation_potential || 0) >= 8,
      colab:        false,
      methods:      s.methods || [],
      datasets:     s.datasets_or_benchmarks ? [s.datasets_or_benchmarks] : [],
      problem:      s.problem || '',
      contribution: s.main_contribution || '',
      matters:      s.results_or_claims || '',
      who:          '',
      arxiv_url:    p.arxiv_url || ('https://arxiv.org/abs/' + (p.arxiv_id || '')),
      pdf_url:      p.pdf_url  || ('https://arxiv.org/pdf/'  + (p.arxiv_id || '')),
      abstract:     p.abstract || '',
      limitations:  s.limitations || '',
      future_work:  s.future_work  || '',
      research_area:s.research_area || '',
    };
  }

  // ── Transform KG trend → RR_DATA TRENDS shape ────────────────────────────

  function transformTrend(t) {
    return {
      name:        t.name || t.entity || '',
      velocity:    Math.round((t.velocity || t.velocity_score || 0) * 100),
      saturation:  t.saturation_score > 0.7 ? 'High' : t.saturation_score > 0.4 ? 'Medium' : 'Low',
      opportunity: t.gap_score > 0.7 ? 'High' : t.gap_score > 0.4 ? 'Medium' : 'Low',
      papers:      t.frequency || t.frequency_count || 0,
      cat:         t.cat || 'cs.AI',
      methods:     [],
      gaps:        [],
      novelty:     Math.round((t.novelty_score || 0.5) * 10),
    };
  }

  // ── Transform gap → RR_DATA GAPS shape ───────────────────────────────────

  function transformGap(g) {
    return {
      gap:        g.name || g.gap || '',
      score:      g.gap_score || g.score || 0,
      difficulty: g.implementation_potential > 0.7 ? 'Low' : g.implementation_potential > 0.4 ? 'Medium' : 'High',
      evidence:   g.description ? [g.description] : [],
      cats:       ['cs.AI'],
      project:    'Build a solution addressing: ' + (g.name || ''),
    };
  }

  // ── Transform KG graph → RR_DATA GRAPH shape ─────────────────────────────

  function transformGraph(data) {
    var nodes = (data.nodes || []).map(function(n) {
      return { id: String(n.id), label: n.label || n.name || String(n.id), type: n.type || 'method', freq: n.freq || n.frequency_count || 1 };
    });
    var links = (data.links || []).map(function(l) {
      if (Array.isArray(l)) return l.map(String);
      return [String(l.source), String(l.target)];
    });
    return { nodes: nodes, links: links };
  }

  // ── Load all data synchronously ───────────────────────────────────────────

  function fetchAll() {
    try {
      // Full RR data bundle (papers + trends + gaps + graph + kpis)
      var bundle = safeGet('/api/rr-data', null);

      var papers = [];
      var trends = [];
      var gaps   = [];
      var graph  = { nodes: [], links: [] };
      var kpis   = [];
      var intel  = [];

      if (bundle) {
        // Handle both lowercase (new) and uppercase (legacy) keys
        var bp = bundle.papers  || bundle.PAPERS  || [];
        var bt = bundle.trends  || bundle.TRENDS  || [];
        var bg = bundle.gaps    || bundle.GAPS    || [];
        var bgr= bundle.graph   || bundle.GRAPH   || null;

        // Transform papers — already in react shape from /api/rr-data transforms
        papers = bp.map(function(p) {
          // If from build_full_rr_data these are already in react format
          if (p.arxiv_url || p.summary) return p;
          return transformPaper(p);
        });

        // Trends from bundle
        trends = bt.map(function(t) {
          if (t.velocity !== undefined && t.saturation !== undefined) {
            // Already in react shape
            return { name: t.entity || t.name || t.topic || '', velocity: Math.round((t.velocity || 0) * 100), saturation: t.saturation, opportunity: t.opportunity || 'Medium', papers: t.papers || 0, cat: t.cat || 'cs.AI', methods: [], gaps: [], novelty: t.novelty || 5 };
          }
          return transformTrend(t);
        });

        // Gaps from bundle
        gaps = bg.map(function(g) {
          if (g.gap !== undefined && g.score !== undefined) {
            return { gap: g.gap || g.name || '', score: g.score || 0, difficulty: g.difficulty || 'Medium', evidence: g.evidence || [], cats: g.cats || ['cs.AI'], project: g.project || '' };
          }
          return transformGap(g);
        });

        // Graph
        if (bgr) {
          graph = transformGraph(bgr);
        }

        // KPIs
        kpis = bundle.kpis  || bundle.KPIS  || [];
        intel = bundle.intel || bundle.INTEL || [];
      }

      // Fallback: if no papers from bundle, fetch directly
      if (papers.length === 0) {
        var direct = safeGet('/api/papers?limit=50', { papers: [] });
        var rawPapers = direct.papers || (Array.isArray(direct) ? direct : []);
        papers = rawPapers.map(function(p) {
          if (p.arxiv_url || p.summary) return p;
          return transformPaper(p);
        });
      }

      // Fallback: trends
      if (trends.length === 0) {
        var trendData = safeGet('/api/trends', []);
        if (Array.isArray(trendData)) trends = trendData.map(transformTrend);
      }

      // Fallback: gaps
      if (gaps.length === 0) {
        var gapData = safeGet('/api/gaps', []);
        if (Array.isArray(gapData)) gaps = gapData.map(transformGap);
      }

      // Fallback: graph
      if (graph.nodes.length === 0) {
        var graphData = safeGet('/api/rr-data', { graph: { nodes: [], links: [] } });
        if (graphData.graph) graph = transformGraph(graphData.graph);
      }

      // Build live KPIs from stats if not in bundle
      if (kpis.length === 0) {
        var stats = safeGet('/api/stats', {});
        kpis = [
          { label:'Papers indexed', value: stats.total_papers || papers.length, delta: '+' + (stats.today_papers || 0) + ' today', dir:'up', spark:[3,5,4,7,6,9,8,11,10,12] },
          { label:'KG entities',    value: stats.total_entities || 0,            delta:'live graph',                              dir:'up', spark:[10,15,20,18,25,22,30,28,35,33] },
          { label:'Research gaps',  value: gaps.length,                           delta:'detected',                                dir:'up', spark:[1,2,2,3,3,4,5,5,6,7] },
          { label:'Trend topics',   value: trends.length,                         delta:'tracked',                                 dir:'up', spark:[2,3,4,4,5,6,6,7,8,8] },
        ];

        intel = [
          { k:'Daily papers',    v: (stats.today_papers || papers.length) + ' new',      accent:'green'  },
          { k:'KG entities',     v: (stats.total_entities || 0) + ' nodes',              accent:'cyan'   },
          { k:'Memory chunks',   v: (stats.total_memories || 0) + ' indexed',            accent:'purple' },
          { k:'Top category',    v: papers.length > 0 ? (papers[0].cat || 'cs.AI') : 'cs.AI', accent:'gray' },
        ];
      }

      window.RR_DATA.PAPERS   = papers;
      window.RR_DATA.TRENDS   = trends;
      window.RR_DATA.GAPS     = gaps;
      window.RR_DATA.GRAPH    = graph;
      window.RR_DATA.KPIS     = kpis;
      window.RR_DATA.INTEL    = intel;
      window.RR_DATA._loaded  = true;

    } catch (err) {
      window.RR_DATA._error = String(err);
      console.error('[RR_DATA] load error:', err);
    }
  }

  fetchAll();
})();

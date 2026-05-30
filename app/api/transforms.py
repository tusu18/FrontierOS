"""
transforms.py — Convert SQLAlchemy DB rows into the exact JSON shape
that the ResearchRadar React app expects.
"""

from __future__ import annotations
import json
import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Entity type → graph node type ────────────────────────────────────────────
_ETYPE_TO_NODE = {
    "Paper": "paper",
    "Author": "author",
    "Institution": "institution",
    "ResearchArea": "method",
    "Topic": "method",
    "Task": "method",
    "Method": "method",
    "ModelArchitecture": "method",
    "Dataset": "dataset",
    "Benchmark": "benchmark",
    "Metric": "benchmark",
    "Baseline": "method",
    "Claim": "claim",
    "Result": "claim",
    "Limitation": "limitation",
    "FutureWork": "future",
    "CodeRepository": "method",
    "HuggingFaceModel": "method",
    "Tool": "method",
    "Library": "method",
    "Conference": "institution",
    "ResearchGap": "gap",
    "GeneratedProjectIdea": "future",
}

NAV = [
    # ── Core ──────────────────────────────────────────────────────────────
    {"id": "dashboard",   "label": "Dashboard",        "icon": "grid",     "section": "core"},
    {"id": "daily",       "label": "Daily Papers",      "icon": "feed",     "section": "core"},
    {"id": "deepdive",    "label": "Paper Deep Dive",   "icon": "doc",      "section": "core"},
    # ── v2 Personal ────────────────────────────────────────────────────────
    {"id": "foryou",      "label": "For You ✨",        "icon": "spark",    "section": "personal"},
    {"id": "alerts",      "label": "Alerts 🔔",         "icon": "bell",     "section": "personal"},
    {"id": "digest",      "label": "Digest 📧",         "icon": "report",   "section": "personal"},
    {"id": "topics",      "label": "Saved Topics",      "icon": "bookmark", "section": "personal"},
    # ── Intelligence ──────────────────────────────────────────────────────
    {"id": "memory",      "label": "Research Memory",   "icon": "spark",    "section": "intel"},
    {"id": "graph",       "label": "Knowledge Graph",   "icon": "graph",    "section": "intel"},
    {"id": "trends",      "label": "Trend Radar",       "icon": "radar",    "section": "intel"},
    {"id": "gaps",        "label": "Research Gaps",     "icon": "target",   "section": "intel"},
    {"id": "trust",       "label": "Trust & Evidence",  "icon": "check",    "section": "intel"},
    # ── Build ─────────────────────────────────────────────────────────────
    {"id": "p2c",         "label": "Paper-to-Code",     "icon": "code",     "section": "build"},
    {"id": "builder",     "label": "Project Builder",   "icon": "build",    "section": "build"},
    {"id": "reports",     "label": "Reports",           "icon": "report",   "section": "build"},
    {"id": "collections", "label": "Collections",       "icon": "bookmark", "section": "build"},
    # ── Settings ──────────────────────────────────────────────────────────
    {"id": "profile",     "label": "Profile",           "icon": "gear",     "section": "settings"},
    {"id": "admin",       "label": "Admin",             "icon": "grid",     "section": "settings"},
    {"id": "settings",    "label": "Settings",          "icon": "gear",     "section": "settings"},
]

CATS = [
    "cs.CL","cs.AI","cs.LG","cs.CV","cs.IR",
    "cs.RO","cs.SE","cs.NE","cs.DC","cs.CR",
]


def _reprod_grade(score: int) -> str:
    if score >= 8:
        return "A"
    if score >= 6:
        return "B"
    return "C"


def _opportunity(p: dict) -> float:
    n = p.get("novelty_score", 5) or 5
    i = p.get("impact_score", 5) or 5
    td = p.get("technical_depth_score", 5) or 5
    b = p.get("code_generation_potential", 5) or 5
    r = p.get("reproducibility_score", 5) or 5
    return round(n * 0.35 + i * 0.30 + td * 0.20 + b * 0.10 + r * 0.05, 1)


def _badges(p: dict, opp: float) -> List[str]:
    badges = []
    if opp >= 8.5:
        badges.append("High Opportunity")
    if (p.get("code_generation_potential") or 0) >= 7:
        badges.append("Code Potential")
    if (p.get("reproducibility_score") or 0) >= 8:
        badges.append("Easy Reproduce")
    if (p.get("technical_depth_score") or 0) >= 9:
        badges.append("High Compute")
    return badges


def paper_to_react(p: dict) -> dict:
    """Convert a paper+summary dict from get_papers_with_summaries → React paper object."""
    authors = p.get("authors", [])
    if isinstance(authors, str):
        try:
            authors = json.loads(authors)
        except Exception:
            authors = []

    methods = p.get("methods", []) or []
    if isinstance(methods, str):
        try:
            methods = json.loads(methods)
        except Exception:
            methods = [methods]

    datasets = p.get("datasets_or_benchmarks", []) or []
    if isinstance(datasets, str):
        try:
            datasets = json.loads(datasets)
        except Exception:
            datasets = [datasets]

    keywords = p.get("keywords", []) or []
    if isinstance(keywords, str):
        try:
            keywords = json.loads(keywords)
        except Exception:
            keywords = [keywords]

    opp = _opportunity(p)
    r_score = int(p.get("reproducibility_score") or 5)
    b_score = int(p.get("code_generation_potential") or 5)

    return {
        "id":           p.get("arxiv_id", ""),
        "title":        p.get("title", ""),
        "authors":      authors[:4],
        "cat":          p.get("primary_category", ""),
        "date":         (p.get("published_date") or "")[:10],
        "tags":         [k for k in keywords[:4] if k],
        "badges":       _badges(p, opp),
        "summary":      p.get("one_line_summary") or p.get("abstract", "")[:200],
        "scores": {
            "novelty":     int(p.get("novelty_score") or 5),
            "impact":      int(p.get("impact_score") or 5),
            "reprod":      _reprod_grade(r_score),
            "build":       b_score,
            "opportunity": opp,
        },
        "code":         b_score >= 7,
        "colab":        r_score >= 7,
        "methods":      [m for m in methods[:4] if m],
        "datasets":     [d for d in datasets[:4] if d],
        "problem":      p.get("problem", ""),
        "contribution": p.get("main_contribution", ""),
        "matters":      p.get("one_line_summary", ""),
        "who":          "",
        "abstract":     p.get("abstract", ""),
        "limitations":  p.get("limitations", ""),
        "future_work":  p.get("future_work", ""),
        "arxiv_url":    p.get("arxiv_url", ""),
        "pdf_url":      p.get("pdf_url", ""),
        "db_id":        p.get("id"),
    }


def build_kpis(session, papers: List[dict]) -> List[dict]:
    """Build KPI grid data from DB stats."""
    from app.database import Paper, Summary, KGEntity, KGEdge
    from datetime import datetime

    total = session.query(Paper).count()
    summarized = session.query(Summary).count()
    today_str = date.today().isoformat()
    today = session.query(Paper).filter(
        Paper.published_date.startswith(today_str)
    ).count() or session.query(Paper).filter(
        Paper.created_at >= datetime.utcnow().replace(hour=0, minute=0, second=0)
    ).count()

    entities = session.query(KGEntity).count()
    edges = session.query(KGEdge).count()

    high_opp = sum(1 for p in papers if (p.get("scores") or {}).get("opportunity", 0) >= 8.5)
    code_ready = sum(1 for p in papers if p.get("code"))

    # Build simple spark arrays (7 data points) based on total
    def spark(end: int, n: int = 7) -> List[int]:
        step = max(1, end // n)
        return [max(0, end - step * (n - 1 - i)) for i in range(n)]

    return [
        {"label": "Papers Today",          "value": str(today),    "delta": f"+{today}",    "dir": "up",   "spark": spark(today)},
        {"label": "Total Papers",          "value": f"{total:,}",  "delta": f"+{today}",    "dir": "up",   "spark": spark(total)},
        {"label": "Summarized",            "value": str(summarized),"delta": f"{summarized}","dir": "up",  "spark": spark(summarized)},
        {"label": "KG Entities",           "value": f"{entities:,}","delta": f"+{entities}", "dir": "up",  "spark": spark(entities)},
        {"label": "High-Opportunity Papers","value": str(high_opp), "delta": f"+{high_opp}", "dir": "up",  "spark": spark(high_opp)},
        {"label": "Code-Ready Papers",     "value": str(code_ready),"delta": f"+{code_ready}","dir": "up", "spark": spark(code_ready)},
    ]


def build_intel(papers: List[dict], trends: List[dict]) -> List[dict]:
    """Build intelligence strip from real data."""
    intel = []

    if trends:
        top = max(trends, key=lambda t: t.get("velocity", 0), default=None)
        if top:
            intel.append({"k": "Top trend today", "v": top["name"], "accent": "green"})
        rising = sorted(trends, key=lambda t: t.get("velocity", 0), reverse=True)
        if len(rising) > 1:
            intel.append({"k": "Fastest rising topic", "v": rising[1]["name"], "accent": "cyan"})
        saturated = [t for t in trends if t.get("saturation") == "High"]
        if saturated:
            intel.append({"k": "Most saturated topic", "v": saturated[0]["name"], "accent": "gray"})

    if papers:
        best_reprod = max(papers, key=lambda p: (p.get("scores") or {}).get("reprod", ""), default=None)
        if best_reprod:
            intel.append({"k": "Most reproducible paper", "v": best_reprod["title"][:40], "accent": "green"})
        best_code = max(papers, key=lambda p: (p.get("scores") or {}).get("build", 0), default=None)
        if best_code:
            intel.append({"k": "Best paper-to-code", "v": best_code["title"][:40], "accent": "cyan"})
        best_opp = max(papers, key=lambda p: (p.get("scores") or {}).get("opportunity", 0), default=None)
        if best_opp:
            intel.append({"k": "Best project opportunity", "v": best_opp["title"][:40], "accent": "purple"})

    # Pad with defaults if needed
    defaults = [
        {"k": "Papers sourced from", "v": "arXiv CS (public API)", "accent": "gray"},
        {"k": "Model", "v": "OpenRouter · GPT-4o mini", "accent": "cyan"},
    ]
    while len(intel) < 4:
        intel.append(defaults[len(intel) % len(defaults)])

    return intel[:6]


def build_trends(session) -> List[dict]:
    """Build trend radar data from KG trend_memory + daily_trends."""
    from app.database import TrendMemory, KGEntity, DailyTrend
    import json as _json

    # Try to get from latest daily trend first
    latest_dt = session.query(DailyTrend).order_by(DailyTrend.created_at.desc()).first()
    if latest_dt:
        try:
            raw = _json.loads(latest_dt.trend_json or "{}")
            # Try to reshape into React trend format if structured
            dominant = raw.get("dominant_themes", [])
            emerging = raw.get("emerging_topics", [])
            saturated = raw.get("saturated_areas", [])

            trends = []
            for i, theme in enumerate(dominant[:5]):
                trends.append({
                    "name": theme,
                    "velocity": max(10, 40 - i * 5),
                    "saturation": "Medium" if i > 0 else "Low",
                    "opportunity": "High" if i < 2 else "Medium",
                    "papers": max(5, 20 - i * 3),
                    "cat": "cs.CL",
                    "methods": [],
                    "gaps": [],
                    "novelty": round(8.0 - i * 0.3, 1),
                })
            for i, topic in enumerate(emerging[:4]):
                trends.append({
                    "name": topic,
                    "velocity": max(5, 30 - i * 4),
                    "saturation": "Low",
                    "opportunity": "High",
                    "papers": max(4, 12 - i * 2),
                    "cat": "cs.LG",
                    "methods": [],
                    "gaps": [],
                    "novelty": round(7.5 - i * 0.2, 1),
                })
            for topic in saturated[:3]:
                trends.append({
                    "name": topic,
                    "velocity": -8,
                    "saturation": "High",
                    "opportunity": "Low",
                    "papers": 25,
                    "cat": "cs.CL",
                    "methods": [],
                    "gaps": [],
                    "novelty": 4.5,
                })
            if trends:
                return trends
        except Exception:
            pass

    # Fall back to KG trend_memory
    from datetime import timedelta
    since = (date.today() - timedelta(days=7)).isoformat()
    rows = (
        session.query(TrendMemory, KGEntity)
        .join(KGEntity, TrendMemory.entity_id == KGEntity.id)
        .filter(TrendMemory.date >= since)
        .filter(KGEntity.entity_type.in_(["Topic", "Method", "Task", "ResearchArea"]))
        .order_by(TrendMemory.velocity_score.desc())
        .limit(12)
        .all()
    )

    seen = set()
    trends = []
    for tm, ent in rows:
        if ent.name in seen:
            continue
        seen.add(ent.name)
        sat_val = tm.saturation_score or 0
        sat = "High" if sat_val > 0.6 else "Medium" if sat_val > 0.3 else "Low"
        opp = "High" if tm.velocity_score > 0.5 and sat != "High" else "Medium" if sat != "High" else "Low"
        trends.append({
            "name": ent.name,
            "velocity": round(tm.velocity_score * 50),
            "saturation": sat,
            "opportunity": opp,
            "papers": ent.frequency_count,
            "cat": "cs.CL",
            "methods": [],
            "gaps": [],
            "novelty": round(tm.novelty_score * 10, 1),
        })
    return trends


def build_gaps(session) -> List[dict]:
    """Build research gaps list from KGEntity (ResearchGap type) or Limitation type."""
    from app.database import KGEntity
    import json as _json

    gap_entities = (
        session.query(KGEntity)
        .filter(KGEntity.entity_type.in_(["ResearchGap", "Limitation"]))
        .order_by(KGEntity.frequency_count.desc())
        .limit(10)
        .all()
    )

    gaps = []
    for ent in gap_entities:
        meta = {}
        try:
            meta = _json.loads(ent.metadata_json or "{}")
        except Exception:
            pass

        gap_score = meta.get("gap_score", round(min(9.9, ent.frequency_count * 0.6 + 4), 1))
        difficulty = meta.get("difficulty", "Medium")
        cats_raw = _json.loads(ent.source_paper_ids_json or "[]")

        gaps.append({
            "gap": ent.name.replace("Gap: ", ""),
            "score": gap_score,
            "difficulty": difficulty,
            "evidence": [
                f"Mentioned in {ent.frequency_count} papers",
                f"First seen {ent.first_seen_date}",
            ],
            "cats": ["cs.CL", "cs.AI"],
            "project": meta.get("project", f"Build a solution addressing: {ent.name}"),
            "implementation_potential": meta.get("implementation_potential", 0.5),
        })

    return gaps


def build_graph(session) -> dict:
    """Build force-graph data from kg_entities + kg_edges."""
    from app.database import KGEntity, KGEdge

    # Load all entities — typical DB has < 500 so this is cheap
    entities = (
        session.query(KGEntity)
        .order_by(KGEntity.frequency_count.desc())
        .limit(500)
        .all()
    )

    id_to_str = {ent.id: f"e{ent.id}" for ent in entities}
    valid_ids = set(ent.id for ent in entities)

    nodes = []
    for ent in entities:
        node_type = _ETYPE_TO_NODE.get(ent.entity_type, "method")
        nodes.append({
            "id":    f"e{ent.id}",
            "label": ent.name[:45],
            "type":  node_type,
            "freq":  ent.frequency_count,
        })

    edges = session.query(KGEdge).limit(1000).all()
    seen_links = set()
    links = []
    for edge in edges:
        if edge.source_entity_id not in valid_ids or edge.target_entity_id not in valid_ids:
            continue
        a, b = f"e{edge.source_entity_id}", f"e{edge.target_entity_id}"
        # Use integer tuple for deduplication to avoid string-sort "e9" > "e10" bugs
        lo, hi = min(edge.source_entity_id, edge.target_entity_id), max(edge.source_entity_id, edge.target_entity_id)
        key = (lo, hi)
        if key not in seen_links:
            seen_links.add(key)
            links.append([a, b])

    return {"nodes": nodes, "links": links}


def build_full_rr_data(session, papers_limit: int = 100) -> dict:
    """Assemble the full window.RR_DATA object the React app reads."""
    from app.database import get_papers_with_summaries

    raw_papers   = get_papers_with_summaries(session, limit=papers_limit)
    react_papers = []
    for p in raw_papers:
        try:
            react_papers.append(paper_to_react(p))
        except Exception:
            pass

    trends = build_trends(session)
    gaps = build_gaps(session)
    graph = build_graph(session)
    kpis = build_kpis(session, react_papers)
    intel = build_intel(react_papers, trends)

    all_cats = list({p.get("cat", "") for p in react_papers if p.get("cat")}) or CATS

    return {
        "CATS":    sorted(all_cats),
        "PAPERS":  react_papers,
        "TRENDS":  trends,
        "GAPS":    gaps,
        "GRAPH":   graph,
        "KPIS":    kpis,
        "INTEL":   intel,
        "NAV":     NAV,
    }

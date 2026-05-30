"""
ResearchRadar — FastAPI backend

Serves the React UI from frontend/ and provides REST endpoints
that supply real data from the SQLite + knowledge graph layer.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date, datetime
from typing import Any, Dict, List, Optional

# Ensure project root on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils import load_env, setup_logging, ensure_dirs
load_env()
setup_logging()
ensure_dirs()

from fastapi import FastAPI, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.database import (
    create_all_tables, get_session, get_stats, get_kg_stats,
    get_papers_with_summaries, get_all_keywords, get_all_trend_tags,
    Paper, Summary, DailyTrend, KGEntity, KGEdge, TrendMemory, Report,
    paper_to_dict, summary_to_dict,
)
from app.openrouter_client import is_api_key_configured
from app.memory.research_memory_engine import ResearchMemoryEngine

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# App init
# ------------------------------------------------------------------
create_all_tables()
_memory = ResearchMemoryEngine()

app = FastAPI(title="ResearchRadar API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _spark(values: List[float]) -> List[float]:
    """Return last 7 values (or pad) for sparkline."""
    if not values:
        return [0] * 7
    return (([0] * 7) + list(values))[-7:]


def _papers_to_rr(papers: List[Dict]) -> List[Dict]:
    """Convert DB paper dicts to the RR_DATA PAPERS shape."""
    result = []
    for p in papers:
        nov = p.get("novelty_score", 5)
        imp = p.get("impact_score", 5)
        rep = p.get("reproducibility_score", 5)
        cod = p.get("code_generation_potential", 5)
        # Opportunity score (composite)
        opp = round(nov * 0.35 + imp * 0.30 + cod * 0.20 + rep * 0.15, 1)

        reprod_letter = "A" if rep >= 8 else "B" if rep >= 5 else "C"
        methods = p.get("methods", [])
        if isinstance(methods, str):
            try:
                methods = json.loads(methods)
            except Exception:
                methods = [methods] if methods else []
        datasets = p.get("datasets_or_benchmarks", [])
        if isinstance(datasets, str):
            try:
                datasets = json.loads(datasets)
            except Exception:
                datasets = [datasets] if datasets else []
        authors = p.get("authors", [])
        if isinstance(authors, str):
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors] if authors else []
        keywords = p.get("keywords", [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = [keywords] if keywords else []
        categories = p.get("categories", [])
        if isinstance(categories, str):
            try:
                categories = json.loads(categories)
            except Exception:
                categories = []

        badges = []
        if opp >= 8:
            badges.append("High Opportunity")
        if cod >= 8:
            badges.append("Code Potential")
        if rep >= 8:
            badges.append("Easy Reproduce")

        result.append({
            "id": p.get("arxiv_id", str(p.get("id", ""))),
            "db_id": p.get("id"),
            "title": p.get("title", ""),
            "authors": authors[:4],
            "cat": p.get("primary_category", "cs.AI"),
            "date": p.get("published_date", "")[:10],
            "tags": keywords[:4],
            "badges": badges,
            "summary": p.get("one_line_summary", p.get("abstract", "")[:200]),
            "problem": p.get("problem", ""),
            "contribution": p.get("main_contribution", ""),
            "matters": p.get("future_work", ""),
            "who": "",
            "scores": {
                "novelty": nov,
                "impact": imp,
                "reprod": reprod_letter,
                "build": cod,
                "opportunity": opp,
            },
            "code": bool(cod >= 7),
            "colab": bool(cod >= 8 and rep >= 7),
            "methods": methods[:5],
            "datasets": datasets[:5],
            "limitations": p.get("limitations", ""),
            "future_work": p.get("future_work", ""),
            "research_area": p.get("research_area", ""),
            "pdf_url": p.get("pdf_url", ""),
            "arxiv_url": p.get("arxiv_url", ""),
        })
    return result


def _build_rr_data() -> Dict:
    """Build the full RR_DATA object from the real database."""
    session = get_session()
    try:
        stats = get_stats(session)
        kg = get_kg_stats(session)

        # Papers
        papers_raw = get_papers_with_summaries(session, limit=100)
        papers = _papers_to_rr(papers_raw)

        # Categories
        cats = sorted(set(p["cat"] for p in papers if p["cat"])) or [
            "cs.CL", "cs.AI", "cs.LG", "cs.CV", "cs.IR",
            "cs.RO", "cs.SE", "cs.NE", "cs.DC", "cs.CR",
        ]

        # KPIs
        all_papers_count = stats["total"]
        summarized = stats["summarized"]
        today_count = stats["today"]
        entities = kg.get("entities", 0)
        edges = kg.get("edges", 0)

        # Trend data from KG
        trend_rows = (
            session.query(TrendMemory)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(30)
            .all()
        )
        trend_entity_map: Dict[int, Dict] = {}
        for row in trend_rows:
            if row.entity_id not in trend_entity_map:
                ent = session.query(KGEntity).filter_by(id=row.entity_id).first()
                if ent:
                    trend_entity_map[row.entity_id] = {
                        "name": ent.name,
                        "velocity": round(row.velocity_score * 100),
                        "saturation": "High" if row.saturation_score > 0.6 else "Medium" if row.saturation_score > 0.3 else "Low",
                        "opportunity": "High" if row.novelty_score > 0.6 else "Medium" if row.novelty_score > 0.3 else "Low",
                        "papers": ent.frequency_count,
                        "cat": "cs.AI",
                        "methods": [],
                        "gaps": [],
                        "novelty": round(row.novelty_score * 10, 1),
                    }

        trends = list(trend_entity_map.values())[:8]
        if not trends:
            # Derive from keywords when KG is empty
            from collections import Counter
            kw_data = get_all_keywords(session)
            kw_counts = Counter(d["keyword"] for d in kw_data)
            trends = [
                {
                    "name": kw,
                    "velocity": min(99, cnt * 5),
                    "saturation": "Low" if cnt < 5 else "Medium" if cnt < 15 else "High",
                    "opportunity": "High" if cnt < 10 else "Medium",
                    "papers": cnt,
                    "cat": "cs.AI",
                    "methods": [],
                    "gaps": [],
                    "novelty": max(1, 10 - cnt * 0.3),
                }
                for kw, cnt in kw_counts.most_common(8)
            ]

        # Research gaps
        gaps_raw = _memory.find_research_gaps(limit=8)
        gaps = [
            {
                "gap": g["name"],
                "score": g["gap_score"],
                "difficulty": "Medium",
                "evidence": [f"Appears in {g['frequency']} papers", f"First seen: {g['first_seen']}", f"Last seen: {g['last_seen']}"],
                "cats": ["cs.AI"],
                "project": g.get("description", "Explore this gap by building on existing work."),
            }
            for g in gaps_raw
        ]
        if not gaps:
            gaps = [{
                "gap": "No gaps detected yet",
                "score": 0,
                "difficulty": "Unknown",
                "evidence": ["Build the knowledge graph to detect gaps"],
                "cats": ["cs.AI"],
                "project": "Run the KG builder to populate research gap data.",
            }]

        # KG graph for visualization
        kg_entities = session.query(KGEntity).order_by(KGEntity.frequency_count.desc()).limit(60).all()
        kg_edges = session.query(KGEdge).limit(120).all()

        TYPE_COLOR = {
            "Paper": "paper", "Method": "method", "Dataset": "dataset",
            "Benchmark": "benchmark", "Claim": "claim", "Limitation": "limitation",
            "FutureWork": "future", "ResearchGap": "gap", "Author": "author",
            "Institution": "inst", "Topic": "method", "Task": "method",
        }
        graph_nodes = [
            {
                "id": f"e{e.id}",
                "label": e.name[:30],
                "type": TYPE_COLOR.get(e.entity_type, "method"),
                "freq": e.frequency_count,
            }
            for e in kg_entities
        ]
        entity_id_to_gid = {e.id: f"e{e.id}" for e in kg_entities}
        valid_ids = set(entity_id_to_gid.values())
        graph_links = []
        for edge in kg_edges:
            s = entity_id_to_gid.get(edge.source_entity_id)
            t = entity_id_to_gid.get(edge.target_entity_id)
            if s and t and s in valid_ids and t in valid_ids:
                graph_links.append([s, t])

        # KPIS
        kpis = [
            {"label": "Papers Today", "value": str(today_count), "delta": f"+{today_count}", "dir": "up",
             "spark": _spark([max(0, today_count - 10), today_count])},
            {"label": "Total Papers", "value": f"{all_papers_count:,}", "delta": f"+{today_count}", "dir": "up",
             "spark": _spark(range(max(0, all_papers_count - 300), all_papers_count, max(1, all_papers_count // 7)))},
            {"label": "Summarized", "value": str(summarized), "delta": f"+{summarized}", "dir": "up",
             "spark": _spark([summarized])},
            {"label": "KG Entities", "value": f"{entities:,}", "delta": f"+{entities}", "dir": "up",
             "spark": _spark([entities])},
            {"label": "KG Relationships", "value": f"{edges:,}", "delta": f"+{edges}", "dir": "up",
             "spark": _spark([edges])},
            {"label": "Research Gaps", "value": str(len(gaps_raw)), "delta": f"{len(gaps_raw)}", "dir": "down",
             "spark": _spark([len(gaps_raw)])},
        ]

        # Today's intelligence strip
        top_by_novelty = sorted(papers, key=lambda x: x["scores"]["novelty"], reverse=True)
        top_by_opp = sorted(papers, key=lambda x: x["scores"]["opportunity"], reverse=True)
        intel = [
            {"k": "Top trend today", "v": trends[0]["name"] if trends else "—"},
            {"k": "Fastest rising topic", "v": trends[1]["name"] if len(trends) > 1 else "—"},
            {"k": "Most saturated", "v": next((t["name"] for t in trends if t["saturation"] == "High"), "—")},
            {"k": "Best opportunity", "v": top_by_opp[0]["title"][:40] + "…" if top_by_opp else "—"},
            {"k": "Most reproducible", "v": top_by_novelty[0]["title"][:40] + "…" if top_by_novelty else "—"},
            {"k": "Best buildable", "v": next((p["title"][:40] + "…" for p in papers if p["code"]), "—")},
        ]

        nav = [
            {"id": "dashboard", "label": "Dashboard", "icon": "grid"},
            {"id": "daily", "label": "Daily Papers", "icon": "feed"},
            {"id": "deepdive", "label": "Paper Deep Dive", "icon": "doc"},
            {"id": "memory", "label": "Research Memory", "icon": "spark"},
            {"id": "graph", "label": "Knowledge Graph", "icon": "graph"},
            {"id": "trends", "label": "Trend Radar", "icon": "radar"},
            {"id": "gaps", "label": "Research Gaps", "icon": "target"},
            {"id": "p2c", "label": "Paper-to-Code", "icon": "code"},
            {"id": "builder", "label": "Project Builder", "icon": "build"},
            {"id": "reports", "label": "Reports", "icon": "report"},
            {"id": "collections", "label": "Collections", "icon": "bookmark"},
            {"id": "settings", "label": "Settings", "icon": "gear"},
        ]

        return {
            "CATS": cats,
            "PAPERS": papers,
            "TRENDS": trends,
            "GAPS": gaps,
            "GRAPH": {"nodes": graph_nodes, "links": graph_links},
            "KPIS": kpis,
            "INTEL": intel,
            "NAV": nav,
            "META": {
                "total_papers": all_papers_count,
                "summarized": summarized,
                "today": today_count,
                "kg_entities": entities,
                "kg_edges": edges,
                "api_configured": is_api_key_configured(),
                "model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini"),
                "last_updated": datetime.utcnow().strftime("%b %d, %Y · %H:%M UTC"),
            },
        }
    finally:
        session.close()


# ------------------------------------------------------------------
# Dynamic data.js endpoint
# ------------------------------------------------------------------

@app.get("/api/data.js", response_class=Response)
def serve_data_js():
    """Serve window.RR_DATA as a JS file populated from the real database."""
    try:
        data = _build_rr_data()
    except Exception as exc:
        logger.error(f"serve_data_js error: {exc}")
        data = {"CATS": [], "PAPERS": [], "TRENDS": [], "GAPS": [], "GRAPH": {"nodes": [], "links": []}, "KPIS": [], "INTEL": [], "NAV": [], "META": {}}
    js = f"(function(){{ window.RR_DATA = {json.dumps(data, default=str)}; }})();"
    return Response(content=js, media_type="application/javascript")


# ------------------------------------------------------------------
# REST API endpoints
# ------------------------------------------------------------------

@app.get("/api/stats")
def api_stats():
    session = get_session()
    try:
        return {**get_stats(session), **get_kg_stats(session), "api_ok": is_api_key_configured()}
    finally:
        session.close()


@app.get("/api/papers")
def api_papers(limit: int = 100, category: str = "", q: str = ""):
    session = get_session()
    try:
        raw = get_papers_with_summaries(session, limit=limit)
        if category:
            raw = [p for p in raw if category.lower() in p.get("primary_category", "").lower()]
        if q:
            ql = q.lower()
            raw = [p for p in raw if ql in p.get("title", "").lower() or ql in p.get("abstract", "").lower()]
        return _papers_to_rr(raw)
    finally:
        session.close()


@app.get("/api/papers/{arxiv_id}")
def api_paper_detail(arxiv_id: str):
    session = get_session()
    try:
        paper = session.query(Paper).filter_by(arxiv_id=arxiv_id).first()
        if not paper:
            raise HTTPException(404, "Paper not found")
        summary = session.query(Summary).filter_by(paper_id=paper.id).first()
        d = paper_to_dict(paper)
        if summary:
            d.update(summary_to_dict(summary))
        return d
    finally:
        session.close()


@app.get("/api/memory/query")
def api_memory_query(q: str = "", limit: int = 20):
    if not q:
        return []
    return _memory.query_memory(q, limit=limit)


@app.get("/api/memory/gaps")
def api_memory_gaps(limit: int = 20):
    return _memory.find_research_gaps(limit=limit)


@app.get("/api/memory/trending")
def api_trending(entity_type: str = "", window_days: int = 7, limit: int = 20):
    return _memory.get_trending_entities(
        entity_type=entity_type or None,
        window_days=window_days,
        limit=limit,
    )


@app.get("/api/memory/similar/{paper_id}")
def api_similar_papers(paper_id: int, limit: int = 10):
    return _memory.find_similar_papers(paper_id, limit=limit)


@app.get("/api/reports")
def api_reports(limit: int = 20):
    session = get_session()
    try:
        reports = session.query(Report).order_by(Report.created_at.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "type": r.report_type,
                "title": r.title,
                "created_at": str(r.created_at)[:10],
                "preview": r.content_markdown[:300],
                "content": r.content_markdown,
            }
            for r in reports
        ]
    finally:
        session.close()


# ------------------------------------------------------------------
# Action endpoints (async background tasks)
# ------------------------------------------------------------------

class ActionResult(BaseModel):
    ok: bool
    message: str
    count: int = 0


@app.post("/api/actions/fetch", response_model=ActionResult)
def action_fetch(background: BackgroundTasks):
    """Fetch papers from arXiv."""
    def _run():
        try:
            from app.agents.paper_collector_agent import PaperCollectorAgent
            agent = PaperCollectorAgent()
            papers = agent.run()
            logger.info(f"Fetched {len(papers)} papers")
        except Exception as exc:
            logger.error(f"Fetch error: {exc}")
    background.add_task(_run)
    return ActionResult(ok=True, message="Fetching papers in background…")


@app.post("/api/actions/summarize", response_model=ActionResult)
def action_summarize(background: BackgroundTasks):
    """Summarize unsummarized papers."""
    if not is_api_key_configured():
        return ActionResult(ok=False, message="OpenRouter API key not configured.")
    def _run():
        try:
            from app.agents.paper_summarizer_agent import PaperSummarizerAgent
            agent = PaperSummarizerAgent(skip_existing=True)
            results = agent.run()
            logger.info(f"Summarized {len(results)} papers")
        except Exception as exc:
            logger.error(f"Summarize error: {exc}")
    background.add_task(_run)
    return ActionResult(ok=True, message="Summarizing papers in background…")


@app.post("/api/actions/build-kg", response_model=ActionResult)
def action_build_kg(background: BackgroundTasks):
    """Build/update the knowledge graph."""
    def _run():
        try:
            from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
            results = KnowledgeGraphBuilderAgent().run(limit=30)
            from app.agents.research_gap_memory_agent import ResearchGapMemoryAgent
            ResearchGapMemoryAgent().run(limit=30)
            logger.info(f"KG updated: {len(results)} papers ingested")
        except Exception as exc:
            logger.error(f"KG build error: {exc}")
    background.add_task(_run)
    return ActionResult(ok=True, message="Building knowledge graph in background…")


@app.post("/api/actions/trends", response_model=ActionResult)
def action_trends(background: BackgroundTasks):
    """Run trend analysis."""
    if not is_api_key_configured():
        return ActionResult(ok=False, message="OpenRouter API key not configured.")
    def _run():
        try:
            from app.agents.trend_analyst_agent import TrendAnalystAgent
            TrendAnalystAgent().run(save=True)
        except Exception as exc:
            logger.error(f"Trend analysis error: {exc}")
    background.add_task(_run)
    return ActionResult(ok=True, message="Running trend analysis in background…")


class CodeGenRequest(BaseModel):
    paper_id: str          # arxiv_id
    mode: str = "PyTorch skeleton"
    use_memory: bool = True


@app.post("/api/actions/generate-code")
def action_generate_code(req: CodeGenRequest):
    """Generate code for a paper (synchronous — blocks until done)."""
    if not is_api_key_configured():
        raise HTTPException(400, "OpenRouter API key not configured.")
    session = get_session()
    try:
        paper = session.query(Paper).filter_by(arxiv_id=req.paper_id).first()
        if not paper:
            raise HTTPException(404, "Paper not found")
        summary = session.query(Summary).filter_by(paper_id=paper.id).first()
        paper_dict = paper_to_dict(paper)
        if summary:
            paper_dict.update(summary_to_dict(summary))
    finally:
        session.close()

    if req.use_memory:
        from app.agents.memory_aware_code_generator_agent import MemoryAwareCodeGeneratorAgent
        code = MemoryAwareCodeGeneratorAgent().run(paper_dict, req.mode)
    else:
        from app.agents.code_generator_agent import CodeGeneratorAgent
        code = CodeGeneratorAgent().run(paper_dict, req.mode)

    return {"ok": True, "code": code, "mode": req.mode, "title": paper_dict.get("title", "")}


class ReportRequest(BaseModel):
    report_type: str = "Daily report"
    category: str = ""
    use_memory: bool = True


@app.post("/api/actions/generate-report")
def action_generate_report(req: ReportRequest):
    """Generate a research report (synchronous)."""
    if not is_api_key_configured():
        raise HTTPException(400, "OpenRouter API key not configured.")
    if req.use_memory:
        from app.agents.memory_aware_report_writer_agent import MemoryAwareReportWriterAgent
        content = MemoryAwareReportWriterAgent().run(
            report_type=req.report_type,
            category=req.category or None,
            save=True,
        )
    else:
        from app.agents.report_writer_agent import ReportWriterAgent
        content = ReportWriterAgent().run(
            report_type=req.report_type,
            category=req.category or None,
            save=True,
        )
    return {"ok": True, "content": content, "type": req.report_type}


class MemoryQueryRequest(BaseModel):
    query: str
    limit: int = 20


@app.post("/api/memory/ask")
def memory_ask(req: MemoryQueryRequest):
    """Hybrid memory query for the Research Memory chat page."""
    if not req.query.strip():
        raise HTTPException(400, "Query is required.")

    results = _memory.query_memory(req.query, limit=req.limit)
    gaps = _memory.find_research_gaps(limit=3)
    trending = _memory.get_trending_entities(limit=5)

    # Build a structured answer
    entity_hits = [r for r in results if r.get("source") == "entity"]
    semantic_hits = [r for r in results if r.get("source") != "entity"]

    bullets = []
    for h in semantic_hits[:4]:
        text = h.get("text", "")
        if text:
            bullets.append(text[:200])
    for e in entity_hits[:3]:
        bullets.append(f"Entity **{e['name']}** ({e['entity_type']}) — appears {e['frequency']} times in memory.")

    if not bullets:
        bullets = [
            "No relevant papers found yet. Fetch and summarize more papers to grow the research memory.",
            "Run **Build Knowledge Graph** to extract entities from existing summaries.",
        ]

    papers_cited = list(set(
        h.get("paper_id") or h.get("metadata", {}).get("paper_id")
        for h in semantic_hits[:5]
        if (h.get("paper_id") or h.get("metadata", {}).get("paper_id"))
    ))

    paper_titles = []
    if papers_cited:
        session = get_session()
        try:
            for pid in papers_cited[:4]:
                p = session.query(Paper).filter_by(id=pid).first()
                if p:
                    paper_titles.append(f"{p.title[:60]}… ({p.primary_category})")
        finally:
            session.close()

    ents_cited = [e["name"] for e in entity_hits[:5]]
    trend_names = [t["name"] for t in trending[:3]]
    next_actions = [
        "Open Trend Radar for velocity detail",
        "Browse Research Gaps for actionable directions",
        "Open Daily Papers to filter by these topics",
    ]

    lead = (
        f"Found {len(results)} memory records relevant to your query. "
        + (f"Top trends in this space: {', '.join(trend_names)}." if trend_names else "")
    )
    if not results:
        lead = "Your research memory is empty or no results matched. Try fetching and summarizing more papers first."

    return {
        "lead": lead,
        "bullets": bullets[:5],
        "papers": paper_titles[:4],
        "ents": ents_cited[:5],
        "gaps": [g["name"] for g in gaps[:3]],
        "next": next_actions,
    }


# ------------------------------------------------------------------
# Static file serving — MUST be last
# ------------------------------------------------------------------

# Serve frontend files
app.mount("/app", StaticFiles(directory=os.path.join(FRONTEND_DIR, "app")), name="app-js")
app.mount("/styles", StaticFiles(directory=os.path.join(FRONTEND_DIR, "styles")), name="styles")


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_app():
    html_path = os.path.join(FRONTEND_DIR, "app.html")
    with open(html_path) as f:
        return f.read()

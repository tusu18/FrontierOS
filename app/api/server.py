"""
FastAPI server — serves the ResearchRadar React SPA + all API endpoints.

Routes:
  GET  /                      → static/index.html  (landing page)
  GET  /app                   → static/app.html    (React dashboard)
  GET  /api/rr-data           → all window.RR_DATA in one request
  GET  /api/stats             → live db + kg stats
  POST /api/memory/query      → query research memory
  POST /api/actions/fetch     → fetch papers from arXiv
  POST /api/actions/summarize → summarize unsummarized papers
  POST /api/actions/build-kg  → build knowledge graph
  POST /api/code/generate     → generate code for a paper
  POST /api/reports/generate  → generate a report
  GET  /api/reports           → list past reports
  GET  /api/papers            → paginated paper list
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional

# Add project root to path
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.utils import load_env, ensure_dirs
load_env()
ensure_dirs()

from app.database import (
    create_all_tables, get_session,
    get_papers_with_summaries, get_stats, get_kg_stats,
    ensure_default_alert_rules_for_user, ensure_default_alert_rules_for_all_users,
    get_unsummarized_paper_ids,
    Report as ReportModel,
    WaitlistEntry,
    PrivateResearchArtifact, ResearchDirective, CitationAdvice,
    Paper, Summary, User, FetchQueue,
    KGEntity, KGEdge,
)
from app.api.transforms import build_full_rr_data, paper_to_react, NAV
from app.openrouter_client import is_api_key_configured

logger = logging.getLogger(__name__)

# Paths
STATIC_DIR = _ROOT / "static"
APP_HTML   = STATIC_DIR / "app.html"
INDEX_HTML = STATIC_DIR / "index.html"

app = FastAPI(title="ResearchRadar API", docs_url="/api/docs", redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Boot DB on startup
create_all_tables()

# Start agent orchestrator scheduler
@app.on_event("startup")
def _start_orchestrator():
    from app.agents.orchestrator import orchestrator
    orchestrator.start_scheduler()
    logger.info("[Server] Agent orchestrator scheduler started")


# ─── Static file serving ─────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def root():
    """Root → marketing/landing page. /app → React dashboard."""
    if INDEX_HTML.exists():
        return HTMLResponse(INDEX_HTML.read_text())
    return HTMLResponse("<h1>ResearchRadar</h1><a href='/app'>Open Dashboard</a>")


@app.get("/landing", response_class=HTMLResponse)
def landing():
    """Alias for the landing page."""
    if INDEX_HTML.exists():
        return HTMLResponse(INDEX_HTML.read_text())
    return HTMLResponse("<h1>ResearchRadar</h1>")


@app.get("/app", response_class=HTMLResponse)
def dashboard():
    """React dashboard SPA."""
    if APP_HTML.exists():
        return HTMLResponse(APP_HTML.read_text())
    raise HTTPException(404, "app.html not found in static/")


def _static_js(name: str):
    path = STATIC_DIR / name
    if path.exists():
        return HTMLResponse(path.read_text(), media_type="application/javascript")
    raise HTTPException(404, f"{name} not found")


@app.get("/config.js")
def config_js():
    return _static_js("config.js")


@app.get("/ghpages-bridge.js")
def ghpages_bridge_js():
    return _static_js("ghpages-bridge.js")


# Mount everything under /static so the HTML can reference /static/styles/...
# BUT the HTML files reference relative paths like "styles/app.css" — so we
# also mount the whole static dir at root level for the sub-paths.
if STATIC_DIR.exists():
    # /styles/* → static/styles/   (CSS, fonts)
    app.mount("/styles", StaticFiles(directory=str(STATIC_DIR / "styles")), name="styles")
    # /app/*    → static/app/      (JS, JSX, data files)
    # GET /app is handled by the route above; this mount catches /app/icons.jsx etc.
    app.mount("/app",    StaticFiles(directory=str(STATIC_DIR / "app")),    name="app-js")


# ─── Data endpoints ───────────────────────────────────────────────────────────

@app.get("/api/rr-data")
def rr_data(limit: int = 100):
    """Single endpoint that returns the full window.RR_DATA object."""
    session = get_session()
    try:
        data = build_full_rr_data(session, papers_limit=limit)
        return JSONResponse(data)
    except Exception as exc:
        logger.error(f"rr_data error: {exc}")
        # Return minimal safe fallback so the React app still loads
        return JSONResponse({
            "CATS": [], "PAPERS": [], "TRENDS": [], "GAPS": [],
            "GRAPH": {"nodes": [], "links": []},
            "KPIS": [], "INTEL": [], "NAV": NAV,
        })
    finally:
        session.close()


@app.get("/api/stats")
def stats():
    session = get_session()
    try:
        s = get_stats(session)
        kg = get_kg_stats(session)
        return {**s, **kg, "api_key": is_api_key_configured()}
    finally:
        session.close()


@app.get("/api/papers")
def papers(limit: int = 100, cat: Optional[str] = None, q: Optional[str] = None):
    session = get_session()
    try:
        raw    = get_papers_with_summaries(session, limit=limit)
        result = []
        for p in raw:
            try:
                result.append(paper_to_react(p))
            except Exception:
                pass
        if cat and cat != "all":
            result = [p for p in result if p.get("cat") == cat or p.get("primary_category") == cat]
        if q:
            ql = q.lower()
            result = [p for p in result if ql in (p.get("title", "") + " " + p.get("summary", "")).lower()]
        return {"papers": result, "total": len(result)}
    finally:
        session.close()


@app.get("/api/trends")
def api_trends(limit: int = 20):
    """Return trending KG entities with velocity/saturation scores."""
    from app.database import TrendMemory, KGEntity
    session = get_session()
    try:
        trends = (
            session.query(TrendMemory)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(limit)
            .all()
        )
        result = []
        for t in trends:
            name = t.entity_type
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            result.append({
                "name":             name,
                "velocity":         round(t.velocity_score, 3),
                "saturation_score": round(t.saturation_score, 3),
                "novelty_score":    round(t.novelty_score, 3),
                "frequency_count":  t.count,
            })
        return result
    finally:
        session.close()


@app.get("/api/gaps")
def api_gaps(limit: int = 20):
    """Return research gaps from KG entities."""
    from app.memory.research_memory_engine import ResearchMemoryEngine
    engine = ResearchMemoryEngine()
    gaps = engine.find_research_gaps(limit=limit)
    return gaps


# ─── Action endpoints ─────────────────────────────────────────────────────────

class FetchRequest(BaseModel):
    max_results: Optional[int] = None
    categories: Optional[List[str]] = None


@app.post("/api/actions/fetch")
def action_fetch(req: FetchRequest):
    """Fetch papers from arXiv and save to DB."""
    from app.agents.paper_collector_agent import PaperCollectorAgent
    try:
        agent = PaperCollectorAgent()
        if req.max_results:
            agent.max_results = req.max_results
        if req.categories:
            agent.categories = req.categories
        papers = agent.run()
        return {"ok": True, "fetched": len(papers)}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/actions/summarize")
def action_summarize(limit: int = 25, force: bool = False, paper_ids: Optional[List[int]] = None):
    """
    Process pending papers end-to-end:
      1. Summarize papers without a Summary (or specific paper_ids).
      2. Extract evidence spans for those summaries.
      3. Extract KG entities/edges.
      4. Update fetch_queue status.
    Returns per-stage counts. Already-summarized papers are skipped unless force=true.
    """
    if not is_api_key_configured():
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")

    from app.agents.paper_summarizer_agent     import PaperSummarizerAgent
    from app.agents.evidence_extractor_agent    import EvidenceExtractorAgent
    from app.agents.kg_builder_agent            import KnowledgeGraphBuilderAgent

    result = {"processed": 0, "summarized": 0, "evidence_extracted": 0, "kg_extracted": 0, "failed": 0}

    session = get_session()
    try:
        # Decide target paper ids
        if paper_ids:
            target_ids = paper_ids
        else:
            target_ids = get_unsummarized_paper_ids(session, limit=limit)
        result["processed"] = len(target_ids)
    finally:
        session.close()

    if not target_ids and not force:
        return {"ok": True, **result, "message": "No pending papers to process."}

    # 1. Summarize
    try:
        agent = PaperSummarizerAgent(skip_existing=not force)
        summaries = agent.run(paper_ids=target_ids)
        result["summarized"] = len(summaries)
    except Exception as exc:
        logger.error("summarize stage failed: %s", exc)
        result["failed"] += 1

    # 2. Evidence
    try:
        ev = EvidenceExtractorAgent().run(paper_ids=target_ids, max_papers=len(target_ids) or 20)
        result["evidence_extracted"] = ev.get("papers_processed", ev.get("processed", 0)) if isinstance(ev, dict) else 0
    except Exception as exc:
        logger.error("evidence stage failed: %s", exc)

    # 3. KG
    try:
        kg = KnowledgeGraphBuilderAgent().run(limit=len(target_ids) or 20)
        result["kg_extracted"] = len(kg) if isinstance(kg, (list, dict)) else 0
    except Exception as exc:
        logger.error("kg stage failed: %s", exc)

    return {"ok": True, **result}


@app.get("/api/actions/pending-count")
def pending_count():
    """Return how many papers still need summarization."""
    session = get_session()
    try:
        ids = get_unsummarized_paper_ids(session)
        return {"pending": len(ids)}
    finally:
        session.close()


@app.post("/api/actions/build-kg")
def action_build_kg(limit: int = 20):
    """Run KG builder on unsummarized papers."""
    from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
    try:
        agent = KnowledgeGraphBuilderAgent()
        results = agent.run(limit=limit)
        return {"ok": True, "processed": len(results)}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/api/actions/scan-gaps")
def action_scan_gaps():
    """Scan and promote research gaps."""
    from app.agents.research_gap_memory_agent import ResearchGapMemoryAgent
    try:
        agent = ResearchGapMemoryAgent()
        gaps = agent.run(limit=30)
        return {"ok": True, "gaps": len(gaps)}
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ─── Memory query ─────────────────────────────────────────────────────────────

class MemoryQueryRequest(BaseModel):
    query: str
    limit: int = 15
    paper_id: Optional[int] = None


@app.post("/api/memory/query")
def memory_query(req: MemoryQueryRequest):
    """
    Query the research memory and return a structured answer
    in the format memory.jsx expects.
    """
    from app.memory.research_memory_engine import ResearchMemoryEngine
    engine = ResearchMemoryEngine()

    # Retrieval
    results = engine.query_memory(req.query, limit=req.limit)
    gaps    = engine.find_research_gaps(limit=3)
    trends  = engine.get_trending_entities(limit=5)

    entity_names  = [r["name"] for r in results if r.get("source") == "entity"][:5]
    semantic_hits = [r for r in results if r.get("source") != "entity"][:5]

    # Build bullets from retrieved memory
    bullets = []
    for hit in semantic_hits[:3]:
        t = hit.get("text", "")
        if t:
            bullets.append(t[:120])
    if not bullets:
        bullets = [
            f"Found {len(results)} memory items matching your query.",
            f"Trending related topics: {', '.join([t['name'] for t in trends[:3]])}",
        ]

    # Referenced papers (from semantic hits)
    paper_refs = list({
        f"Paper #{r.get('paper_id')} in memory"
        for r in semantic_hits if r.get("paper_id")
    })[:4]

    next_actions = [
        "Open Knowledge Graph to explore entity connections",
        "Open Trend Radar for velocity detail",
        "Ask a follow-up to narrow by category",
    ]

    # Try LLM for a better lead sentence if API key available
    lead = f"Research memory found {len(results)} relevant items for: '{req.query}'"
    if is_api_key_configured() and results:
        try:
            from app.openrouter_client import call_openrouter
            context_text = " | ".join(
                r.get("text") or r.get("name", "") for r in results[:5]
            )[:800]
            msgs = [
                {"role": "system", "content": "You are a research intelligence assistant. Write 1-2 concise sentences summarising the research memory results for the user's query. Be specific and cite entity names."},
                {"role": "user", "content": f"Query: {req.query}\n\nMemory context: {context_text}"},
            ]
            lead = call_openrouter(msgs, max_tokens=120, temperature=0.3) or lead
        except Exception:
            pass

    # Report which search mode produced these results
    search_mode = "semantic embeddings" if os.getenv("ENABLE_LOCAL_EMBEDDINGS", "false") == "true" else "keyword/hybrid-lite"

    return {
        "lead":        lead,
        "bullets":     bullets,
        "papers":      paper_refs or ["No direct paper references found yet — build the KG first."],
        "ents":        entity_names,
        "next":        next_actions,
        "search_mode": search_mode,
    }


# ─── Code generation ──────────────────────────────────────────────────────────

class CodeRequest(BaseModel):
    paper_id: Optional[str] = None   # arxiv_id
    db_id: Optional[int] = None
    mode: str = "PyTorch skeleton"
    use_memory: bool = True


@app.post("/api/code/generate")
def generate_code(req: CodeRequest):
    """Generate code for a paper using the (memory-aware) code generator."""
    if not is_api_key_configured():
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")

    session = get_session()
    try:
        from app.database import Paper, Summary, paper_to_dict, summary_to_dict
        from app.agents.memory_aware_code_generator_agent import MemoryAwareCodeGeneratorAgent
        from app.agents.code_generator_agent import CodeGeneratorAgent

        # Resolve paper
        paper_row = None
        if req.db_id:
            paper_row = session.query(Paper).filter_by(id=req.db_id).first()
        elif req.paper_id:
            paper_row = session.query(Paper).filter_by(arxiv_id=req.paper_id).first()

        if not paper_row:
            raise HTTPException(404, "Paper not found")

        paper_dict = paper_to_dict(paper_row)
        summary_row = session.query(Summary).filter_by(paper_id=paper_row.id).first()
        if summary_row:
            paper_dict.update(summary_to_dict(summary_row))

        paper_dict["id"] = paper_row.id

        if req.use_memory:
            code = MemoryAwareCodeGeneratorAgent().run(paper_dict, req.mode)
        else:
            code = CodeGeneratorAgent().run(paper_dict, req.mode)

        return {"ok": True, "code": code, "mode": req.mode}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))
    finally:
        session.close()


# ─── Reports ─────────────────────────────────────────────────────────────────

class ReportRequest(BaseModel):
    report_type: str = "Daily report"
    category: Optional[str] = None
    use_memory: bool = True


@app.post("/api/reports/generate")
def generate_report(req: ReportRequest):
    if not is_api_key_configured():
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")
    try:
        if req.use_memory:
            from app.agents.memory_aware_report_writer_agent import MemoryAwareReportWriterAgent
            content = MemoryAwareReportWriterAgent().run(req.report_type, req.category, save=True)
        else:
            from app.agents.report_writer_agent import ReportWriterAgent
            content = ReportWriterAgent().run(req.report_type, req.category, save=True)
        return {"ok": True, "content": content}
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.get("/api/reports")
def list_reports(limit: int = 20):
    session = get_session()
    try:
        rows = session.query(ReportModel).order_by(ReportModel.created_at.desc()).limit(limit).all()
        return [
            {
                "id":          r.id,
                "type":        r.report_type,
                "title":       r.title,
                "content":     r.content_markdown[:300] + "…",
                "created_at":  str(r.created_at)[:19],
            }
            for r in rows
        ]
    finally:
        session.close()


@app.get("/api/reports/{report_id}")
def get_report(report_id: int):
    session = get_session()
    try:
        r = session.query(ReportModel).filter_by(id=report_id).first()
        if not r:
            raise HTTPException(404, "Report not found")
        return {"id": r.id, "type": r.report_type, "title": r.title, "content": r.content_markdown}
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════
# v2 API — Auth, User, Interactions, Topics, Alerts, Recommendations, Admin
# ═══════════════════════════════════════════════════════════════════════════

from fastapi import Depends, Header
from datetime import datetime
import json as _json

from app.auth import hash_password, verify_password, create_access_token, decode_token
from app.database import (
    User, UserProfile, UserPaperInteraction, SavedTopic, Alert,
    UserCollection, UserCollectionItem, AlertRule, EmailDigest,
    EvidenceSpan, RecommendationLog, FetchQueue,
    create_user, get_user_by_email, get_user_by_id,
    get_or_create_profile, log_interaction,
    get_user_alerts, get_queue_stats, get_recommendation_feed,
    get_evidence_for_paper,
)


# ─── Auth helpers ─────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: str
    password: str
    full_name: str = ""

class LoginRequest(BaseModel):
    email: str
    password: str

class ProfileUpdate(BaseModel):
    interests: Optional[List[str]] = None
    preferred_categories: Optional[List[str]] = None
    preferred_topics: Optional[List[str]] = None
    ignored_topics: Optional[List[str]] = None
    research_goals: Optional[List[str]] = None
    compute_budget: Optional[str] = None
    alert_frequency: Optional[str] = None
    digest_frequency: Optional[str] = None


def _get_current_user(authorization: str = Header(default="")) -> Optional[dict]:
    """Extract user payload from Bearer token. Returns None if missing/invalid."""
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[7:]
    return decode_token(token)


def _require_user(authorization: str = Header(default="")) -> dict:
    payload = _get_current_user(authorization)
    if not payload:
        raise HTTPException(401, "Not authenticated")
    return payload


# ─── Auth endpoints ────────────────────────────────────────────────────────

def _gen_demo_code(session) -> str:
    """Generate a unique 8-char uppercase alphanumeric demo access code."""
    import random, string
    chars = string.ascii_uppercase + string.digits
    for _ in range(20):
        code = "FO-" + "".join(random.choices(chars, k=6))
        if not session.query(User).filter_by(demo_code=code).first():
            return code
    return "FO-" + "".join(random.choices(chars, k=6))


@app.post("/auth/signup")
def signup(req: SignupRequest):
    session = get_session()
    try:
        if get_user_by_email(session, req.email):
            raise HTTPException(400, "Email already registered")
        user = create_user(session, req.email, hash_password(req.password), req.full_name)
        user.demo_code = _gen_demo_code(session)
        # Seed default alert rules so the user has a working Alerts experience
        ensure_default_alert_rules_for_user(session, user.id)
        session.commit()
        token = create_access_token({"sub": str(user.id), "email": user.email})
        # Send access code via email (non-blocking)
        from app.email_sender import send_access_code
        try:
            send_access_code(user.email, user.full_name, user.demo_code)
        except Exception:
            pass
        return {
            "token": token,
            "user_id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "plan": "free",
            "demo_code": user.demo_code,
            "email_sent": True,
        }
    finally:
        session.close()


class DemoRequestBody(BaseModel):
    email: str
    full_name: str = "Demo User"
    role: str = ""                    # e.g. Researcher, Student, ML engineer
    institution: str = ""
    research_areas: Optional[List[str]] = None  # e.g. ["cs.AI", "cs.CL"]
    interests: Optional[List[str]] = None        # e.g. ["LLM Agents", "RAG"]


@app.post("/auth/request-demo")
def request_demo(req: DemoRequestBody):
    """Create a demo account (no password), store profile, and return a unique access code."""
    session = get_session()
    try:
        import secrets
        user = get_user_by_email(session, req.email)
        if not user:
            placeholder_hash = hash_password(secrets.token_hex(24))
            user = create_user(session, req.email, placeholder_hash, req.full_name)
        else:
            if req.full_name:
                user.full_name = req.full_name
        if not getattr(user, "demo_code", None):
            user.demo_code = _gen_demo_code(session)
        ensure_default_alert_rules_for_user(session, user.id)
        # Persist signup fields on user profile (new + returning signups)
        profile = get_or_create_profile(session, user.id)
        if req.research_areas is not None and req.research_areas:
            profile.preferred_categories_json = _json.dumps(req.research_areas)
        if req.interests is not None and req.interests:
            profile.interests_json = _json.dumps(req.interests)
        if req.institution:
            topics = _json.loads(profile.preferred_topics_json or "[]")
            inst = f"inst:{req.institution.strip()}"
            if inst not in topics:
                topics.insert(0, inst)
                profile.preferred_topics_json = _json.dumps(topics)
        if req.role:
            goals = _json.loads(profile.research_goals_json or "[]")
            if req.role not in goals:
                goals.append(req.role)
                profile.research_goals_json = _json.dumps(goals)
        session.commit()
        # Send email
        from app.email_sender import send_access_code, is_email_configured
        email_sent = False
        try:
            email_sent = send_access_code(user.email, user.full_name, user.demo_code)
        except Exception:
            pass
        return {
            "demo_code": user.demo_code,
            "email": user.email,
            "email_sent": email_sent,
            "message": f"Your access code is {user.demo_code}. Use it to log in at /app",
        }
    finally:
        session.close()


class CodeLoginBody(BaseModel):
    code: str


@app.post("/auth/login-with-code")
def login_with_code(req: CodeLoginBody):
    """Login using a demo access code (no password required)."""
    session = get_session()
    try:
        code = req.code.strip().upper()
        user = session.query(User).filter_by(demo_code=code).first()
        if not user:
            raise HTTPException(401, "Invalid access code")
        user.last_login_at = datetime.utcnow()
        session.commit()
        profile = get_or_create_profile(session, user.id)
        token   = create_access_token({"sub": str(user.id), "email": user.email})
        return {
            "token":     token,
            "user_id":   user.id,
            "email":     user.email,
            "full_name": user.full_name,
            "demo_code": user.demo_code,
            "is_admin":  getattr(user, "is_admin", False),
            "plan":      getattr(profile, "plan", "free"),
        }
    finally:
        session.close()



# ─── Waitlist + Access-code endpoints (landing page v2) ──────────────────────

class WaitlistRequest(BaseModel):
    name: str
    email: str
    affiliation: str = ""
    research_area: str = ""
    use_case: str = ""


@app.post("/api/waitlist")
def join_waitlist(req: WaitlistRequest):
    """Landing page early-access form → store entry and optionally email confirmation."""
    session = get_session()
    try:
        existing = session.query(WaitlistEntry).filter_by(email=req.email.lower().strip()).first()
        if existing:
            return {"status": "already_registered", "email": req.email}
        entry = WaitlistEntry(
            name=req.name.strip(),
            email=req.email.lower().strip(),
            affiliation=req.affiliation.strip(),
            research_area=req.research_area,
            use_case=req.use_case,
        )
        session.add(entry)
        session.commit()
        logger.info("[Waitlist] New entry: %s <%s>", req.name, req.email)
        # Best-effort confirmation email
        try:
            from app.email_sender import send_simple
            send_simple(
                to=req.email,
                subject="You're on the FrontierOS waitlist",
                body=(
                    f"Hi {req.name},\n\nYou're on the FrontierOS early-access list. "
                    "We'll send your access code when a slot opens for your research area.\n\n"
                    "— The FrontierOS team"
                ),
            )
        except Exception:
            pass
        return {"status": "ok", "email": req.email}
    finally:
        session.close()


class AccessVerifyRequest(BaseModel):
    code: str
    email: str


@app.post("/api/access/verify")
def verify_access_code(req: AccessVerifyRequest):
    """Verify an access code from the landing page modal."""
    session = get_session()
    try:
        code = req.code.strip().upper()
        email = req.email.lower().strip()
        # 1. Check demo code on any user account
        user = session.query(User).filter_by(demo_code=code).first()
        if user:
            token = create_access_token({"sub": str(user.id), "email": user.email})
            return {"valid": True, "token": token, "redirect": "/app"}
        # 2. Check waitlist approved code
        entry = session.query(WaitlistEntry).filter_by(access_code=code, email=email).first()
        if entry and entry.approved:
            return {"valid": True, "redirect": "/app"}
        return {"valid": False}
    finally:
        session.close()


@app.post("/auth/login")
def login(req: LoginRequest):
    session = get_session()
    try:
        user = get_user_by_email(session, req.email)
        if not user or not verify_password(req.password, user.password_hash):
            raise HTTPException(401, "Invalid email or password")
        user.last_login_at = datetime.utcnow()
        if not getattr(user, "demo_code", None):
            user.demo_code = _gen_demo_code(session)
        session.commit()
        token = create_access_token({"sub": str(user.id), "email": user.email})
        profile = get_or_create_profile(session, user.id)
        return {
            "token":     token,
            "user_id":   user.id,
            "email":     user.email,
            "full_name": user.full_name,
            "demo_code": user.demo_code,
            "is_admin":  getattr(user, "is_admin", False),
            "plan":      getattr(profile, "plan", "free"),
        }
    finally:
        session.close()


@app.get("/me")
def me(payload: dict = Depends(_require_user)):
    session = get_session()
    try:
        user = get_user_by_id(session, int(payload["sub"]))
        if not user:
            raise HTTPException(404, "User not found")
        profile = get_or_create_profile(session, user.id)
        return {
            "id":          user.id,
            "email":       user.email,
            "full_name":   user.full_name,
            "plan":        getattr(profile, "plan", "free") or "free",
            "is_admin":    user.is_admin,
            "interests":   _json.loads(profile.interests_json or "[]"),
            "preferred_categories": _json.loads(profile.preferred_categories_json or "[]"),
            "preferred_topics":     _json.loads(profile.preferred_topics_json or "[]"),
            "ignored_topics":       _json.loads(profile.ignored_topics_json or "[]"),
            "research_goals":       _json.loads(profile.research_goals_json or "[]"),
            "compute_budget":       profile.compute_budget,
            "alert_frequency":      profile.alert_frequency,
            "digest_frequency":     profile.digest_frequency,
        }
    finally:
        session.close()


@app.get("/me/profile")
def get_profile(payload: dict = Depends(_require_user)):
    session = get_session()
    try:
        user_id = int(payload["sub"])
        p = get_or_create_profile(session, user_id)
        return {
            "interests":            _json.loads(p.interests_json or "[]"),
            "preferred_categories": _json.loads(p.preferred_categories_json or "[]"),
            "preferred_topics":     _json.loads(p.preferred_topics_json or "[]"),
            "ignored_topics":       _json.loads(p.ignored_topics_json or "[]"),
            "research_goals":       _json.loads(p.research_goals_json or "[]"),
            "compute_budget":       p.compute_budget,
            "alert_frequency":      p.alert_frequency,
            "digest_frequency":     p.digest_frequency,
        }
    finally:
        session.close()


@app.put("/me/profile")
def update_profile(update: ProfileUpdate, payload: dict = Depends(_require_user)):
    session = get_session()
    try:
        user_id = int(payload["sub"])
        p = get_or_create_profile(session, user_id)
        if update.interests is not None:
            p.interests_json = _json.dumps(update.interests)
        if update.preferred_categories is not None:
            p.preferred_categories_json = _json.dumps(update.preferred_categories)
        if update.preferred_topics is not None:
            p.preferred_topics_json = _json.dumps(update.preferred_topics)
        if update.ignored_topics is not None:
            p.ignored_topics_json = _json.dumps(update.ignored_topics)
        if update.research_goals is not None:
            p.research_goals_json = _json.dumps(update.research_goals)
        if update.compute_budget is not None:
            p.compute_budget = update.compute_budget
        if update.alert_frequency is not None:
            p.alert_frequency = update.alert_frequency
        if update.digest_frequency is not None:
            p.digest_frequency = update.digest_frequency
        p.updated_at = datetime.utcnow()
        ensure_default_alert_rules_for_user(session, user_id)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/alerts/ensure-default-rules")
def user_ensure_alert_rules(payload: dict = Depends(_require_user)):
    """Create default alert rules for the current user if they have none."""
    user_id = int(payload["sub"])
    session = get_session()
    try:
        created = ensure_default_alert_rules_for_user(session, user_id)
        session.commit()
        total = session.query(AlertRule).filter_by(user_id=user_id).count()
        return {"ok": True, "rules_created": created, "total_rules": total}
    finally:
        session.close()


# ─── Personalized paper feed ───────────────────────────────────────────────

@app.get("/papers/for-you")
def papers_for_you(limit: int = 20, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    from app.agents.recommendation_agent import RecommendationAgent
    result = RecommendationAgent().run(user_id=user_id, top_n=limit)
    return result["recommendations"]


# ─── Paper interactions ────────────────────────────────────────────────────

class InteractionRequest(BaseModel):
    interaction_type: str
    value: float = 1.0
    interaction_value: Optional[float] = None  # accepted as alias for `value`
    metadata: Optional[dict] = None


@app.post("/papers/{paper_id}/interaction")
def paper_interaction(
    paper_id: int,
    req: InteractionRequest,
    payload: dict = Depends(_require_user),
):
    user_id = int(payload["sub"])
    val = req.interaction_value if req.interaction_value is not None else req.value
    session = get_session()
    try:
        log_interaction(session, user_id, paper_id, req.interaction_type, val, req.metadata)
        session.commit()
        # Remember in Mem0
        from app.engines.personalization_engine import PersonalizationEngine
        from app.database import Paper
        paper = session.query(Paper).filter_by(id=paper_id).first()
        if paper:
            PersonalizationEngine.remember(
                user_id,
                f"User {req.interaction_type} paper: {paper.title}",
                {"paper_id": paper_id, "type": req.interaction_type},
            )
        return {"ok": True}
    finally:
        session.close()


@app.post("/papers/{paper_id}/save")
def save_paper(paper_id: int, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        log_interaction(session, user_id, paper_id, "saved")
        session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.post("/papers/{paper_id}/ignore")
def ignore_paper(paper_id: int, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        log_interaction(session, user_id, paper_id, "ignored", value=-1.0)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


# ─── Evidence / Trust layer ────────────────────────────────────────────────

@app.get("/papers/{paper_id}/evidence")
def get_evidence(paper_id: int):
    session = get_session()
    try:
        return get_evidence_for_paper(session, paper_id)
    finally:
        session.close()


@app.post("/papers/{paper_id}/extract-evidence")
def extract_evidence(paper_id: int):
    """Run EvidenceExtractorAgent on a single paper."""
    if not is_api_key_configured():
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")
    from app.agents.evidence_extractor_agent import EvidenceExtractorAgent
    result = EvidenceExtractorAgent().run(paper_ids=[paper_id])
    return result


# ─── Saved topics ──────────────────────────────────────────────────────────

class SaveTopicRequest(BaseModel):
    topic_name: str
    entity_id: Optional[int] = None
    alert_enabled: bool = True


@app.get("/topics/saved")
def get_saved_topics(payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        rows = session.query(SavedTopic).filter_by(user_id=user_id).all()
        return [{"id": r.id, "topic": r.topic_name, "alert_enabled": r.alert_enabled, "created_at": str(r.created_at)[:19]} for r in rows]
    finally:
        session.close()


@app.post("/topics/save")
def save_topic(req: SaveTopicRequest, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        row = SavedTopic(user_id=user_id, topic_name=req.topic_name,
                         entity_id=req.entity_id, alert_enabled=req.alert_enabled)
        session.add(row)
        session.commit()
        return {"ok": True, "id": row.id}
    finally:
        session.close()


@app.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        row = session.query(SavedTopic).filter_by(id=topic_id, user_id=user_id).first()
        if not row:
            raise HTTPException(404, "Topic not found")
        session.delete(row)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


# ─── Alerts ────────────────────────────────────────────────────────────────

@app.get("/alerts")
def list_alerts(unread_only: bool = False, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        return get_user_alerts(session, user_id, unread_only=unread_only)
    finally:
        session.close()


@app.post("/alerts/{alert_id}/mark-read")
def mark_alert_read(alert_id: int, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        a = session.query(Alert).filter_by(id=alert_id, user_id=user_id).first()
        if not a:
            raise HTTPException(404)
        a.read_status = True
        session.commit()
        return {"ok": True}
    finally:
        session.close()


class AlertRuleRequest(BaseModel):
    rule_type: str
    topic_name: Optional[str] = None
    entity_id: Optional[int] = None
    threshold: Optional[dict] = None
    delivery_channels: Optional[List[str]] = None


@app.get("/alerts/rules")
def list_alert_rules(payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        rules = session.query(AlertRule).filter_by(user_id=user_id).all()
        return [
            {
                "id":               r.id,
                "rule_type":        r.rule_type,
                "topic_name":       r.topic_name,
                "entity_id":        r.entity_id,
                "threshold":        _json.loads(r.threshold_json or "{}"),
                "delivery_channels":_json.loads(r.delivery_channels_json or '["in_app"]'),
                "enabled":          r.enabled,
                "created_at":       r.created_at.isoformat() if r.created_at else None,
            }
            for r in rules
        ]
    finally:
        session.close()


@app.post("/alerts/rules")
def create_alert_rule(req: AlertRuleRequest, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        rule = AlertRule(
            user_id=user_id,
            rule_type=req.rule_type,
            topic_name=req.topic_name,
            entity_id=req.entity_id,
            threshold_json=_json.dumps(req.threshold or {}),
            delivery_channels_json=_json.dumps(req.delivery_channels or ["in_app"]),
        )
        session.add(rule)
        session.commit()
        return {"ok": True, "rule_id": rule.id}
    finally:
        session.close()


@app.post("/alerts/run")
def run_alerts(payload: dict = Depends(_require_user)):
    """Manually trigger the AlertAgent for the current user."""
    from app.agents.alert_agent import AlertAgent
    user_id = int(payload["sub"])
    return AlertAgent().run(user_ids=[user_id])


# ─── Digests ───────────────────────────────────────────────────────────────

@app.get("/digests/daily")
def get_daily_digest(payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        d = (session.query(EmailDigest)
             .filter_by(user_id=user_id, digest_type="daily")
             .order_by(EmailDigest.created_at.desc()).first())
        if not d:
            return {"content": "No digest yet. Generate one below."}
        return {"id": d.id, "subject": d.subject, "content": d.content_markdown,
                "created_at": str(d.created_at)[:19]}
    finally:
        session.close()


@app.post("/digests/generate")
def generate_digest(digest_type: str = "daily", payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    from app.agents.digest_agent import DigestAgent
    agent = DigestAgent()
    if digest_type == "weekly":
        return agent.generate_weekly(user_id)
    return agent.generate_daily(user_id)


@app.get("/digests/history")
def digest_history(payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        rows = (session.query(EmailDigest).filter_by(user_id=user_id)
                .order_by(EmailDigest.created_at.desc()).limit(30).all())
        return [{"id": r.id, "type": r.digest_type, "subject": r.subject,
                 "created_at": str(r.created_at)[:19]} for r in rows]
    finally:
        session.close()


# ─── Recommendations ────────────────────────────────────────────────────────

@app.get("/recommendations")
def recommendations(limit: int = 20, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        return get_recommendation_feed(session, user_id, limit)
    finally:
        session.close()


class FeedbackRequest(BaseModel):
    paper_id: int
    feedback: str  # "liked" | "disliked" | "saved" | "ignored"


@app.post("/recommendations/feedback")
def recommendation_feedback(req: FeedbackRequest, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        log_interaction(session, user_id, req.paper_id, req.feedback)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


# ─── Memory context ─────────────────────────────────────────────────────────

@app.get("/memory/context")
def memory_context(
    query: Optional[str] = None,
    paper_id: Optional[int] = None,
    payload: dict = Depends(_require_user),
):
    user_id = int(payload["sub"])
    from app.engines.personalization_engine import PersonalizationEngine
    ctx = PersonalizationEngine.build_context(user_id=user_id, query=query, paper_id=paper_id)
    return ctx


# ─── Collections ─────────────────────────────────────────────────────────────

class CollectionRequest(BaseModel):
    name: str
    description: str = ""


@app.get("/collections")
def list_collections(payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        rows = session.query(UserCollection).filter_by(user_id=user_id).all()
        result = []
        for c in rows:
            count = session.query(UserCollectionItem).filter_by(collection_id=c.id).count()
            result.append({"id": c.id, "name": c.name, "description": c.description,
                           "paper_count": count, "created_at": str(c.created_at)[:19]})
        return result
    finally:
        session.close()


@app.post("/collections")
def create_collection(req: CollectionRequest, payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        col = UserCollection(user_id=user_id, name=req.name, description=req.description)
        session.add(col)
        session.commit()
        return {"ok": True, "id": col.id}
    finally:
        session.close()


@app.post("/collections/{col_id}/papers/{paper_id}")
def add_to_collection(col_id: int, paper_id: int, notes: str = "", payload: dict = Depends(_require_user)):
    user_id = int(payload["sub"])
    session = get_session()
    try:
        col = session.query(UserCollection).filter_by(id=col_id, user_id=user_id).first()
        if not col:
            raise HTTPException(404, "Collection not found")
        item = UserCollectionItem(collection_id=col_id, paper_id=paper_id, notes=notes)
        session.add(item)
        session.commit()
        return {"ok": True}
    finally:
        session.close()


# ─── Admin — Fetch queue ────────────────────────────────────────────────────

@app.get("/admin/fetch-queue")
def admin_fetch_queue():
    session = get_session()
    try:
        stats = get_queue_stats(session)
        recent = (session.query(FetchQueue)
                  .order_by(FetchQueue.created_at.desc()).limit(50).all())
        items = [{"id": r.id, "arxiv_id": r.arxiv_id, "status": r.status,
                  "priority": r.priority, "category": r.source_category,
                  "attempts": r.attempt_count, "error": r.last_error,
                  "created_at": str(r.created_at)[:19]} for r in recent]
        return {"stats": stats, "items": items}
    finally:
        session.close()


class FetchMoreRequest(BaseModel):
    limit: int = 100
    categories: Optional[List[str]] = None


@app.post("/admin/fetch-more")
def admin_fetch_more(req: FetchMoreRequest = FetchMoreRequest()):
    """Trigger large batch fetch with deduplication."""
    from app.agents.fetch_queue_agent import FetchQueueAgent
    try:
        result = FetchQueueAgent().run(
            categories=req.categories,
            limit=req.limit,
        )
        return result
    except Exception as exc:
        raise HTTPException(500, str(exc))


@app.post("/admin/reprocess-failed")
def admin_reprocess_failed():
    """Reset failed queue items to 'queued' for retry."""
    session = get_session()
    try:
        failed = session.query(FetchQueue).filter_by(status="failed").all()
        for row in failed:
            row.status = "queued"
            row.attempt_count = 0
        session.commit()
        return {"ok": True, "reset": len(failed)}
    finally:
        session.close()


@app.post("/api/actions/extract-evidence")
def action_extract_evidence(limit: int = 20):
    """Run EvidenceExtractorAgent on papers lacking evidence spans."""
    if not is_api_key_configured():
        raise HTTPException(400, "OPENROUTER_API_KEY not configured")
    from app.agents.evidence_extractor_agent import EvidenceExtractorAgent
    result = EvidenceExtractorAgent().run(max_papers=limit)
    return result


@app.post("/admin/run-analysis")
def admin_run_analysis(limit: int = 20):
    """Run summarizer + KG extraction on fetched-but-unanalysed papers."""
    from app.agents.paper_collector_agent import PaperCollectorAgent
    from app.memory.research_memory_engine import ResearchMemoryEngine
    session = get_session()
    try:
        # Find papers without summaries
        from app.database import Paper, Summary
        from sqlalchemy import not_, exists
        papers_needing_summary = (
            session.query(Paper)
            .filter(~exists().where(Summary.paper_id == Paper.id))
            .limit(limit)
            .all()
        )
        processed = len(papers_needing_summary)
        # Trigger KG ingestion for recent papers that have summaries
        engine = ResearchMemoryEngine()
        from app.database import Summary as Sum
        recent_sums = session.query(Sum).order_by(Sum.created_at.desc()).limit(limit).all()
        kg_count = 0
        for s in recent_sums:
            try:
                paper = session.query(Paper).filter_by(id=s.paper_id).first()
                if paper:
                    import json as _j
                    summary_data = _j.loads(s.summary_json or '{}')
                    engine.ingest_paper_analysis(paper.id, paper.arxiv_id, summary_data)
                    kg_count += 1
            except Exception:
                pass
        return {
            "papers_needing_summary": processed,
            "kg_ingested": kg_count,
            "message": f"KG updated with {kg_count} papers. {processed} papers still need summarization (requires API key).",
        }
    finally:
        session.close()


@app.post("/admin/run-all-agents")
def admin_run_all_agents():
    """Run all background agents: alerts, recommendations, evidence extraction."""
    results = {}
    try:
        from app.agents.alert_agent import AlertAgent
        results["alerts"] = AlertAgent().run()
    except Exception as e:
        results["alerts"] = {"error": str(e)}
    try:
        from app.agents.recommendation_agent import RecommendationAgent
        session = get_session()
        try:
            users = session.query(User).filter_by(is_active=True).all()
            rec_total = 0
            for u in users:
                r = RecommendationAgent().run(user_id=u.id, top_n=20)
                rec_total += r.get("scored", 0)
            results["recommendations"] = {"users": len(users), "papers_scored": rec_total}
        finally:
            session.close()
    except Exception as e:
        results["recommendations"] = {"error": str(e)}
    if is_api_key_configured():
        try:
            from app.agents.evidence_extractor_agent import EvidenceExtractorAgent
            results["evidence"] = EvidenceExtractorAgent().run(max_papers=10)
        except Exception as e:
            results["evidence"] = {"error": str(e)}
    else:
        results["evidence"] = {"skipped": "No API key configured"}
    return results


@app.get("/admin/kg-stats")
def admin_kg_stats():
    """Return KG entity/edge/trend counts for admin dashboard."""
    session = get_session()
    try:
        from app.database import KGEntity, KGEdge, TrendMemory, SemanticMemory
        return {
            "entities":   session.query(KGEntity).count(),
            "edges":      session.query(KGEdge).count(),
            "trends":     session.query(TrendMemory).count(),
            "semantic":   session.query(SemanticMemory).count(),
            "top_entities": [
                {"name": e.name, "type": e.entity_type, "freq": e.frequency_count}
                for e in session.query(KGEntity).order_by(KGEntity.frequency_count.desc()).limit(10).all()
            ],
        }
    finally:
        session.close()



# ─── Admin health ──────────────────────────────────────────────────────────────

@app.get("/api/admin/health")
def admin_health():
    """Full system health check for the admin panel."""
    session = get_session()
    try:
        from app.database import (Paper, Summary, EvidenceSpan, KGEntity, KGEdge,
                                   FetchQueue, Alert, UserPaperInteraction)
        pending_sum   = session.query(Paper).count() - session.query(Summary).count()
        failed_jobs   = session.query(FetchQueue).filter_by(status="failed").count()
        queued_jobs   = session.query(FetchQueue).filter_by(status="queued").count()
        return {
            "db":             "sqlite" if "sqlite" in os.getenv("DATABASE_URL","sqlite") else "postgres",
            "openrouter":     is_api_key_configured(),
            "smtp":           bool(os.getenv("SMTP_PASSWORD","")),
            "memory_backend": os.getenv("MEMORY_BACKEND","local"),
            "papers_total":   session.query(Paper).count(),
            "summaries_total":session.query(Summary).count(),
            "summaries_pending": max(0, pending_sum),
            "evidence_spans": session.query(EvidenceSpan).count(),
            "kg_entities":    session.query(KGEntity).count(),
            "kg_edges":       session.query(KGEdge).count(),
            "alerts_total":   session.query(Alert).count(),
            "interactions":   session.query(UserPaperInteraction).count(),
            "failed_jobs":    failed_jobs,
            "queued_jobs":    queued_jobs,
            "users":          session.query(User).count(),
        }
    finally:
        session.close()


# ─── Private research context ──────────────────────────────────────────────────

class ArtifactUploadRequest(BaseModel):
    name: str
    content: str
    artifact_type: str = "notes"   # draft | notes | proposal | dataset | paper | other


@app.post("/api/context/upload")
def upload_artifact(req: ArtifactUploadRequest):
    """Upload/paste a private research artifact and extract entities from it."""
    session = get_session()
    try:
        user = session.query(User).first()  # single-user MVP
        if not user:
            raise HTTPException(400, "No user found. Sign up first.")

        # Simple entity extraction via LLM (or keyword fallback)
        topics, methods, claims, questions = [], [], [], []
        entities_json = "{}"

        if is_api_key_configured() and len(req.content) > 50:
            try:
                from app.openrouter_client import call_openrouter_json
                msgs = [
                    {"role": "system", "content":
                     "Extract research entities from this text. Return JSON: "
                     "{topics:[], methods:[], claims:[], open_questions:[]}. "
                     "Keep each item under 60 chars. Max 6 items per list."},
                    {"role": "user", "content": req.content[:3000]},
                ]
                extracted = call_openrouter_json(msgs, max_tokens=400, temperature=0.1) or {}
                topics    = extracted.get("topics", [])
                methods   = extracted.get("methods", [])
                claims    = extracted.get("claims", [])
                questions = extracted.get("open_questions", [])
                import json as _j
                entities_json = _j.dumps(extracted)
            except Exception:
                pass

        artifact = PrivateResearchArtifact(
            user_id=user.id,
            name=req.name.strip(),
            artifact_type=req.artifact_type,
            content=req.content,
            file_size=len(req.content.encode()),
            topics_json=json.dumps(topics),
            methods_json=json.dumps(methods),
            claims_json=json.dumps(claims),
            open_questions_json=json.dumps(questions),
            entities_json=entities_json,
            processed=True,
        )
        session.add(artifact)
        session.commit()

        return {
            "ok": True, "id": artifact.id, "name": artifact.name,
            "topics": topics, "methods": methods,
            "claims": claims, "open_questions": questions,
        }
    finally:
        session.close()


@app.get("/api/context/artifacts")
def list_artifacts():
    """List all private research artifacts for the current user."""
    session = get_session()
    try:
        user = session.query(User).first()
        if not user:
            return {"artifacts": []}
        arts = session.query(PrivateResearchArtifact).filter_by(user_id=user.id)\
                      .order_by(PrivateResearchArtifact.created_at.desc()).all()
        result = []
        for a in arts:
            result.append({
                "id": a.id, "name": a.name, "type": a.artifact_type,
                "size": a.file_size, "date": a.created_at.strftime("%Y-%m-%d"),
                "topics": json.loads(a.topics_json or "[]"),
                "methods": json.loads(a.methods_json or "[]"),
                "claims": json.loads(a.claims_json or "[]"),
                "open_questions": json.loads(a.open_questions_json or "[]"),
            })
        return {"artifacts": result}
    finally:
        session.close()


@app.delete("/api/context/artifacts/{artifact_id}")
def delete_artifact(artifact_id: int):
    session = get_session()
    try:
        a = session.query(PrivateResearchArtifact).filter_by(id=artifact_id).first()
        if a:
            session.delete(a)
            session.commit()
        return {"ok": True}
    finally:
        session.close()


# ─── Research Directives ───────────────────────────────────────────────────────

class DirectiveRequest(BaseModel):
    goal_text: str
    cadence: str = "daily"
    tracked_topics: List[str] = []
    alert_on_competitor: bool = True
    alert_on_novelty: bool = True


@app.get("/api/directives")
def list_directives():
    session = get_session()
    try:
        user = session.query(User).first()
        if not user:
            return {"directives": []}
        dirs = session.query(ResearchDirective).filter_by(user_id=user.id)\
                      .order_by(ResearchDirective.created_at.desc()).all()
        return {"directives": [
            {"id": d.id, "text": d.goal_text, "cadence": d.cadence,
             "active": d.active, "matches": d.match_count, "new": d.new_match_count,
             "topics": json.loads(d.tracked_topics_json or "[]")}
            for d in dirs
        ]}
    finally:
        session.close()


@app.post("/api/directives")
def create_directive(req: DirectiveRequest):
    session = get_session()
    try:
        user = session.query(User).first()
        if not user:
            raise HTTPException(400, "No user")
        d = ResearchDirective(
            user_id=user.id,
            goal_text=req.goal_text.strip(),
            cadence=req.cadence,
            tracked_topics_json=json.dumps(req.tracked_topics),
            alert_on_competitor=req.alert_on_competitor,
            alert_on_novelty=req.alert_on_novelty,
        )
        session.add(d); session.commit()
        return {"ok": True, "id": d.id, "text": d.goal_text}
    finally:
        session.close()


@app.delete("/api/directives/{directive_id}")
def delete_directive(directive_id: str):
    # Accept string IDs — mock directives (d1, d2…) are silently ignored
    try:
        db_id = int(directive_id)
    except ValueError:
        return {"ok": True}   # mock/non-DB id — nothing to delete
    session = get_session()
    try:
        d = session.query(ResearchDirective).filter_by(id=db_id).first()
        if d:
            session.delete(d); session.commit()
        return {"ok": True}
    finally:
        session.close()


@app.put("/api/directives/{directive_id}/toggle")
def toggle_directive(directive_id: str):
    try:
        db_id = int(directive_id)
    except ValueError:
        return {"ok": True, "active": True}  # mock id — no-op
    session = get_session()
    try:
        d = session.query(ResearchDirective).filter_by(id=db_id).first()
        if not d:
            raise HTTPException(404, "Directive not found")
        d.active = not d.active
        session.commit()
        return {"ok": True, "active": d.active}
    finally:
        session.close()


# ─── Citation Advisor ─────────────────────────────────────────────────────────

@app.post("/api/papers/{paper_id}/cite")
def citation_advice(paper_id: str):
    """Run CitationAdvisorAgent for a paper and return structured advice."""
    session = get_session()
    try:
        paper = session.query(Paper).filter_by(arxiv_id=paper_id).first()
        if not paper:
            raise HTTPException(404, "Paper not found")
        user = session.query(User).first()
        if user:
            from app.agents.citation_advisor_agent import CitationAdvisorAgent
            advice = CitationAdvisorAgent().advise(paper.id, user_id=user.id, use_llm=is_api_key_configured())
            if advice and not advice.get("error"):
                return advice

        # Return cached if available
        if user:
            cached = session.query(CitationAdvice)\
                            .filter_by(user_id=user.id, paper_id=paper.id).first()
            if cached:
                return json.loads(cached.raw_json or "{}")

        # Build advice
        summ = session.query(Summary).filter_by(paper_id=paper.id).first()
        title = paper.title
        abstract = paper.abstract[:800] if paper.abstract else ""
        contribution = summ.main_contribution[:400] if summ and summ.main_contribution else ""
        limitations  = summ.limitations[:300] if summ and summ.limitations else ""

        # Load user's private context for comparison
        artifacts = session.query(PrivateResearchArtifact)\
                           .filter_by(user_id=user.id if user else -1)\
                           .order_by(PrivateResearchArtifact.created_at.desc())\
                           .limit(3).all()
        user_context = "\n".join(
            f"[{a.artifact_type}] {a.name}: topics={json.loads(a.topics_json or '[]')}"
            for a in artifacts
        ) if artifacts else "No private context uploaded yet."

        # Compute a keyword-based score as fallback
        novelty = int(summ.novelty_score or 5) if summ else 5
        impact  = int(summ.impact_score  or 5) if summ else 5
        relevance_score = min(99, (novelty * 6 + impact * 4))

        advice = {
            "should_cite": relevance_score >= 60,
            "citation_relevance_score": relevance_score,
            "where_to_cite": "Related Work",
            "citation_role": "method_comparison",
            "suggested_citation_sentence": "",
            "difference_from_user_work": "Upload your research context for a personalised comparison.",
            "evidence": [],
            "confidence": round(min(0.95, relevance_score / 100), 2),
        }

        if is_api_key_configured():
            try:
                from app.openrouter_client import call_openrouter_json
                msgs = [
                    {"role": "system", "content":
                     "You are a research citation advisor. Given a paper and the user's research context, "
                     "return JSON: {should_cite:bool, citation_relevance_score:0-100, where_to_cite:str, "
                     "citation_role:str, suggested_citation_sentence:str, difference_from_user_work:str, confidence:float}. "
                     "citation_role: related_work|baseline|method_comparison|dataset_reference|competing_work|not_relevant"},
                    {"role": "user", "content":
                     f"Paper: {title}\nContribution: {contribution}\nLimitations: {limitations}\n\n"
                     f"User's research context:\n{user_context}"},
                ]
                llm_advice = call_openrouter_json(msgs, max_tokens=400, temperature=0.2)
                if llm_advice:
                    advice.update(llm_advice)
            except Exception:
                pass

        # Cache it
        if user:
            ca = CitationAdvice(
                user_id=user.id, paper_id=paper.id,
                should_cite=advice.get("should_cite", False),
                relevance_score=advice.get("citation_relevance_score", 50),
                where_to_cite=advice.get("where_to_cite", ""),
                citation_role=advice.get("citation_role", ""),
                suggested_sentence=advice.get("suggested_citation_sentence", ""),
                difference_text=advice.get("difference_from_user_work", ""),
                confidence=advice.get("confidence", 0.5),
                raw_json=json.dumps(advice),
            )
            session.add(ca); session.commit()

        return advice
    finally:
        session.close()


# ─── Near My Work (per-paper score) ────────────────────────────────────────────

@app.get("/api/papers/{paper_id}/near-score")
def paper_near_score(paper_id: str):
    """Return near-my-work score and why for a specific paper."""
    from app.agents.near_my_work_agent import NearMyWorkAgent
    result = NearMyWorkAgent().score_by_arxiv_id(paper_id)
    if not result:
        raise HTTPException(404, "Paper or user not found")
    return {
        "score": result["near_my_work_score"],
        "relationship_type": result["relationship_type"],
        "why_relevant": result["why_relevant"],
        "evidence": result["evidence"],
        "hint": None if result["near_my_work_score"] > 0 else "Upload your research context for a personalised score.",
    }


class NearMyWorkRequest(BaseModel):
    user_id: Optional[int] = None
    paper_ids: Optional[List[int]] = None
    limit: int = 20


@app.post("/api/agents/near-my-work")
def run_near_my_work_agent(req: NearMyWorkRequest = NearMyWorkRequest()):
    """Run the named NearMyWorkAgent and return ranked papers with explanations."""
    from app.agents.near_my_work_agent import NearMyWorkAgent
    return NearMyWorkAgent().run(user_id=req.user_id, paper_ids=req.paper_ids, limit=req.limit)


@app.get("/api/papers/{paper_id}/near-score-legacy")
def paper_near_score_legacy(paper_id: str):
    """Legacy inline scorer kept for reference during MVP hardening."""
    session = get_session()
    try:
        paper = session.query(Paper).filter_by(arxiv_id=paper_id).first()
        if not paper:
            raise HTTPException(404, "Paper not found")
        summ = session.query(Summary).filter_by(paper_id=paper.id).first()

        user = session.query(User).first()
        artifacts = session.query(PrivateResearchArtifact)\
                           .filter_by(user_id=user.id if user else -1).all() if user else []

        # Compute overlap dimensions
        my_topics  = set()
        my_methods = set()
        for a in artifacts:
            my_topics  |= set(t.lower() for t in json.loads(a.topics_json  or "[]"))
            my_methods |= set(m.lower() for m in json.loads(a.methods_json or "[]"))

        paper_text = f"{paper.title} {paper.abstract or ''}".lower()
        topic_hits  = sum(1 for t in my_topics  if t in paper_text) if my_topics  else 0
        method_hits = sum(1 for m in my_methods if m in paper_text) if my_methods else 0

        novelty = int(summ.novelty_score or 5) if summ else 5
        impact  = int(summ.impact_score  or 5) if summ else 5

        # Score
        base = (novelty * 4 + impact * 3) / 7
        overlap_bonus = min(30, topic_hits * 10 + method_hits * 8)
        score = min(99, int(base * 6 + overlap_bonus))

        why = []
        if topic_hits:
            why.append(["Topic overlap", min(95, 50 + topic_hits * 15)])
        if method_hits:
            why.append(["Method overlap", min(90, 45 + method_hits * 15)])
        why.append(["Novelty", novelty * 10])
        why.append(["Impact", impact * 10])

        return {"score": score, "why": why,
                "artifacts_used": len(artifacts),
                "hint": "Upload your research context for a personalised score." if not artifacts else None}
    finally:
        session.close()


@app.post("/api/near-my-work/rescan")
def rescan_near_my_work():
    """Re-score all recent papers against private context."""
    session = get_session()
    try:
        from app.agents.recommendation_agent import RecommendationAgent
        user = session.query(User).first()
        if not user:
            return {"ok": False, "msg": "No user"}
        result = RecommendationAgent().run(user_id=user.id, top_n=50)
        return {"ok": True, "papers_scored": result.get("scored", 0)}
    finally:
        session.close()


# ─── Fetch queue status ────────────────────────────────────────────────────────

@app.get("/api/fetch-queue/status")
def fetch_queue_status():
    session = get_session()
    try:
        from collections import Counter
        rows = session.query(FetchQueue).all()
        counts = Counter(r.status for r in rows)
        recent = session.query(FetchQueue).order_by(FetchQueue.updated_at.desc()).limit(5).all()
        return {
            "total": len(rows),
            "by_status": dict(counts),
            "recent": [{"arxiv_id": r.arxiv_id, "status": r.status,
                        "error": r.last_error, "updated": str(r.updated_at)[:16]}
                       for r in recent],
        }
    finally:
        session.close()


# ─── Orchestrator API ─────────────────────────────────────────────────────────

@app.get("/admin/orchestrator/status")
def orchestrator_status():
    """Return status of all registered agents."""
    from app.agents.orchestrator import orchestrator
    return {
        "agents":     orchestrator.status(),
        "scheduler":  orchestrator.scheduler_jobs(),
    }


@app.post("/admin/orchestrator/run/{agent_name}")
def orchestrator_run_agent(agent_name: str):
    """Run a specific agent immediately."""
    from app.agents.orchestrator import orchestrator
    return orchestrator.run(agent_name)


@app.post("/admin/orchestrator/run-all")
def orchestrator_run_all():
    """Run all registered agents sequentially."""
    from app.agents.orchestrator import orchestrator
    results = orchestrator.run_all()
    return {"results": results, "total": len(results)}


@app.post("/admin/orchestrator/run-async")
def orchestrator_run_async():
    """Trigger all agents in a background thread (non-blocking)."""
    from app.agents.orchestrator import orchestrator
    orchestrator.run_all_async()
    return {"ok": True, "message": "All agents queued in background"}


@app.post("/admin/test-email")
def admin_test_email(to: Optional[str] = None):
    """Send a test access-code email (admin diagnostics)."""
    from app.email_sender import send_access_code, is_email_configured
    if not is_email_configured():
        return {"ok": False, "message": "SMTP not configured"}
    target = to or os.getenv("SMTP_USER", "")
    if not target:
        raise HTTPException(400, "No recipient — pass ?to=email or set SMTP_USER")
    ok = send_access_code(target, "Admin", "RR-TEST99")
    return {"ok": ok, "sent_to": target, "message": "sent" if ok else "send failed — check SMTP credentials"}


@app.post("/admin/ensure-alert-rules")
def admin_ensure_alert_rules():
    """Backfill default alert rules for every user that has none."""
    session = get_session()
    try:
        return ensure_default_alert_rules_for_all_users(session)
    finally:
        session.close()


@app.get("/admin/system-health")
def admin_system_health():
    """Holistic system status for the Admin health page."""
    import os as _os
    from app.email_sender import is_email_configured
    from app.database import (
        Paper, Summary, KGEntity, KGEdge, EvidenceSpan, AlertRule, Alert,
        UserPaperInteraction, User,
    )

    session = get_session()
    try:
        db_url = _os.getenv("DATABASE_URL", "sqlite:///data/arxiv_papers.db")
        db_kind = "postgres" if db_url.startswith("postgres") else "sqlite"

        pending = len(get_unsummarized_paper_ids(session))

        # Orchestrator last-run summary
        from app.agents.orchestrator import orchestrator
        agents = orchestrator.status()
        last_runs = [a["last_run_at"] for a in agents if a.get("last_run_at")]
        failed_jobs = sum(a.get("error_count", 0) for a in agents)

        # Live OpenRouter ping (env present ≠ API working)
        openrouter_ok = False
        openrouter_note = ""
        if is_api_key_configured():
            try:
                from app.openrouter_client import call_openrouter
                probe = call_openrouter(
                    [{"role": "user", "content": "Reply with exactly: OK"}],
                    max_tokens=4, temperature=0,
                )
                openrouter_ok = bool(probe and probe.strip())
                if not openrouter_ok:
                    openrouter_note = "key set but API returned empty (check credits / 403)"
            except Exception as exc:
                openrouter_note = str(exc)[:120]
        else:
            openrouter_note = "OPENROUTER_API_KEY not set"

        mem_backend = _os.getenv("MEMORY_BACKEND", "local")
        qdrant_ok = False
        if mem_backend == "qdrant":
            try:
                import urllib.request
                urllib.request.urlopen(_os.getenv("QDRANT_URL", "http://localhost:6333"), timeout=1)
                qdrant_ok = True
            except Exception:
                qdrant_ok = False

        return {
            "database": {
                "backend":   db_kind,
                "url":       db_url.split("@")[-1] if "@" in db_url else db_url,
                "connected": True,
            },
            "integrations": {
                "openrouter_configured": is_api_key_configured(),
                "openrouter_reachable":  openrouter_ok,
                "openrouter_note":       openrouter_note,
                "smtp_configured":       is_email_configured(),
                "smtp_host":             _os.getenv("SMTP_HOST", ""),
                "memory_backend":        mem_backend,
                "qdrant_reachable":      qdrant_ok,
                "local_embeddings":      _os.getenv("ENABLE_LOCAL_EMBEDDINGS", "false") == "true",
            },
            "data": {
                "papers":             session.query(Paper).count(),
                "summaries":          session.query(Summary).count(),
                "summaries_pending":  pending,
                "evidence_spans":     session.query(EvidenceSpan).count(),
                "kg_entities":        session.query(KGEntity).count(),
                "kg_edges":           session.query(KGEdge).count(),
                "alert_rules":        session.query(AlertRule).count(),
                "alerts":             session.query(Alert).count(),
                "user_interactions":  session.query(UserPaperInteraction).count(),
                "users":              session.query(User).count(),
            },
            "orchestrator": {
                "agents":       agents,
                "last_run_at":  max(last_runs) if last_runs else None,
                "failed_jobs":  failed_jobs,
                "scheduler":    orchestrator.scheduler_jobs(),
            },
        }
    finally:
        session.close()


# ─── Plan management ──────────────────────────────────────────────────────────
# In production, this would be triggered by a Stripe webhook.
# For demo: any signed-in user can "activate" a plan.

class PlanUpgradeRequest(BaseModel):
    plan: str  # free | pro | lab

@app.post("/me/upgrade-plan")
def upgrade_plan(req: PlanUpgradeRequest, payload: dict = Depends(_require_user)):
    allowed = {"free", "pro", "lab"}
    if req.plan not in allowed:
        raise HTTPException(400, f"Invalid plan. Choose from: {allowed}")
    user_id = int(payload["sub"])
    session = get_session()
    try:
        p = get_or_create_profile(session, user_id)
        p.plan = req.plan
        session.commit()
        return {"ok": True, "plan": req.plan,
                "message": f"Plan updated to '{req.plan}'. In production, payment would be processed here."}
    finally:
        session.close()

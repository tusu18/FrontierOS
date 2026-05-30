"""
AgentOrchestrator — Central control framework for all ResearchRadar agents.

Responsibilities:
- Register and run agents on demand or on a schedule
- Track run history, status, and errors per agent
- Expose status via API
- Integrate with APScheduler for background scheduling
"""
from __future__ import annotations

import logging
import threading
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─── Agent registry entry ───────────────────────────────────────────────────

class AgentRecord:
    def __init__(self, name: str, fn: Callable, description: str = ""):
        self.name        = name
        self.fn          = fn
        self.description = description
        self.status      = "idle"      # idle | running | ok | error
        self.last_run_at: Optional[datetime] = None
        self.last_result: Any = None
        self.last_error:  Optional[str] = None
        self.run_count   = 0
        self.error_count = 0
        self._lock       = threading.Lock()

    def run(self, **kwargs) -> Dict:
        with self._lock:
            self.status = "running"
        start = datetime.utcnow()
        try:
            result = self.fn(**kwargs)
            elapsed = (datetime.utcnow() - start).total_seconds()
            with self._lock:
                self.status      = "ok"
                self.last_run_at = start
                self.last_result = result
                self.last_error  = None
                self.run_count  += 1
            logger.info("[Orchestrator] %s finished in %.1fs: %s", self.name, elapsed, result)
            return {"agent": self.name, "status": "ok", "elapsed_s": round(elapsed, 2), "result": result}
        except Exception as exc:
            elapsed = (datetime.utcnow() - start).total_seconds()
            tb = traceback.format_exc()
            with self._lock:
                self.status      = "error"
                self.last_run_at = start
                self.last_error  = str(exc)
                self.error_count += 1
                self.run_count   += 1
            logger.error("[Orchestrator] %s FAILED in %.1fs: %s\n%s", self.name, elapsed, exc, tb)
            return {"agent": self.name, "status": "error", "elapsed_s": round(elapsed, 2), "error": str(exc)}

    def to_dict(self) -> Dict:
        return {
            "name":        self.name,
            "description": self.description,
            "status":      self.status,
            "run_count":   self.run_count,
            "error_count": self.error_count,
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_error":  self.last_error,
        }


# ─── Orchestrator singleton ──────────────────────────────────────────────────

class AgentOrchestrator:
    """Singleton orchestrator that owns all agent registrations and runs."""

    _instance: Optional["AgentOrchestrator"] = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._agents: Dict[str, AgentRecord] = {}
                inst._scheduler = None
                cls._instance = inst
        return cls._instance

    # ── Registration ────────────────────────────────────────────────────────

    def register(self, name: str, fn: Callable, description: str = "") -> "AgentOrchestrator":
        self._agents[name] = AgentRecord(name, fn, description)
        logger.info("[Orchestrator] registered agent: %s", name)
        return self

    def _lazy_register_all(self):
        """Register all known ResearchRadar agents (lazy import to avoid circular deps)."""
        if self._agents:
            return  # already registered

        from app.agents.fetch_queue_agent     import FetchQueueAgent
        from app.agents.evidence_extractor_agent import EvidenceExtractorAgent
        from app.agents.recommendation_agent  import RecommendationAgent
        from app.agents.alert_agent           import AlertAgent
        from app.agents.digest_agent          import DigestAgent
        from app.database                     import User, get_session

        def _fetch_papers():
            return FetchQueueAgent().run(limit=200, enqueue_only=True)

        def _extract_evidence():
            return EvidenceExtractorAgent().run(max_papers=20)

        def _run_recommendations():
            s = get_session()
            try:
                users = s.query(User).filter_by(is_active=True).all()
                total = 0
                for u in users:
                    r = RecommendationAgent().run(user_id=u.id, top_n=20)
                    total += r.get("scored", 0)
                return {"users": len(users), "papers_scored": total}
            finally:
                s.close()

        def _run_alerts():
            return AlertAgent().run()

        def _run_daily_digests():
            s = get_session()
            try:
                users = s.query(User).filter_by(is_active=True).all()
                results = []
                for u in users:
                    try:
                        results.append(DigestAgent().generate_daily(u.id))
                    except Exception as e:
                        results.append({"user_id": u.id, "error": str(e)})
                return {"digests_generated": len(results)}
            finally:
                s.close()

        def _refresh_kg():
            from app.memory.research_memory_engine import ResearchMemoryEngine
            from app.database                       import Summary, Paper, get_session as gs
            import json as _j
            sess = gs()
            try:
                eng  = ResearchMemoryEngine()
                sums = sess.query(Summary).order_by(Summary.created_at.desc()).limit(50).all()
                count = 0
                for s in sums:
                    p = sess.query(Paper).filter_by(id=s.paper_id).first()
                    if p:
                        try:
                            eng.ingest_paper_analysis(p.id, p.arxiv_id, _j.loads(s.summary_json or "{}"))
                            count += 1
                        except Exception:
                            pass
                return {"kg_ingested": count}
            finally:
                sess.close()

        self.register("fetch_papers",       _fetch_papers,       "Fetch new arXiv papers into queue")
        self.register("extract_evidence",   _extract_evidence,   "Extract evidence spans from paper abstracts")
        self.register("recommendations",    _run_recommendations,"Score and store paper recommendations for all users")
        self.register("alerts",             _run_alerts,         "Evaluate alert rules and create in-app alerts")
        self.register("daily_digests",      _run_daily_digests,  "Generate daily digests for all active users")
        self.register("refresh_kg",         _refresh_kg,         "Re-ingest recent summaries into the Knowledge Graph")

    # ── Run ─────────────────────────────────────────────────────────────────

    def run(self, name: str, **kwargs) -> Dict:
        """Run a single agent by name in the calling thread."""
        self._lazy_register_all()
        agent = self._agents.get(name)
        if not agent:
            return {"agent": name, "status": "error", "error": f"Unknown agent: {name}"}
        return agent.run(**kwargs)

    def run_all(self, names: Optional[List[str]] = None) -> List[Dict]:
        """Run multiple agents sequentially. Pass names=None for all."""
        self._lazy_register_all()
        targets = names or list(self._agents.keys())
        results = []
        for name in targets:
            results.append(self.run(name))
        return results

    def run_all_async(self, names: Optional[List[str]] = None):
        """Run agents in a background thread (fire-and-forget)."""
        t = threading.Thread(target=self.run_all, args=(names,), daemon=True)
        t.start()
        return t

    # ── Status ──────────────────────────────────────────────────────────────

    def status(self) -> List[Dict]:
        self._lazy_register_all()
        return [a.to_dict() for a in self._agents.values()]

    def agent_status(self, name: str) -> Optional[Dict]:
        self._lazy_register_all()
        a = self._agents.get(name)
        return a.to_dict() if a else None

    # ── Scheduler ───────────────────────────────────────────────────────────

    def start_scheduler(self):
        """Start APScheduler for daily background runs."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            if self._scheduler and self._scheduler.running:
                return

            scheduler = BackgroundScheduler(timezone="UTC")
            self._lazy_register_all()

            # Daily at 06:00 UTC — fetch papers
            scheduler.add_job(lambda: self.run("fetch_papers"),    "cron", hour=6,  minute=0,  id="fetch_papers")
            # Daily at 06:30 — refresh KG with new summaries
            scheduler.add_job(lambda: self.run("refresh_kg"),      "cron", hour=6,  minute=30, id="refresh_kg")
            # Daily at 07:00 — run recommendations
            scheduler.add_job(lambda: self.run("recommendations"), "cron", hour=7,  minute=0,  id="recommendations")
            # Daily at 07:15 — run alerts
            scheduler.add_job(lambda: self.run("alerts"),          "cron", hour=7,  minute=15, id="alerts")
            # Daily at 07:30 — generate digests
            scheduler.add_job(lambda: self.run("daily_digests"),   "cron", hour=7,  minute=30, id="daily_digests")
            # Every 6 hours — extract evidence (LLM-dependent)
            scheduler.add_job(lambda: self.run("extract_evidence"),"interval", hours=6,         id="extract_evidence")

            scheduler.start()
            self._scheduler = scheduler
            logger.info("[Orchestrator] scheduler started with %d jobs", len(scheduler.get_jobs()))
        except Exception as exc:
            logger.warning("[Orchestrator] scheduler start failed: %s", exc)

    def scheduler_jobs(self) -> List[Dict]:
        if not self._scheduler:
            return []
        jobs = []
        for job in self._scheduler.get_jobs():
            jobs.append({
                "id":       job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            })
        return jobs


# ─── Module-level singleton ──────────────────────────────────────────────────

orchestrator = AgentOrchestrator()

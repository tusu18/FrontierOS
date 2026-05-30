#!/usr/bin/env python3
"""
bootstrap_mvp.py — Repair / bootstrap the ResearchRadar MVP.

Brings the database into a launch-ready state:
  1. Summarize unsummarized papers (LLM).
  2. Extract evidence spans for summaries missing them (LLM).
  3. Run KG extraction for summarized papers (LLM).
  4. Create default alert rules for all users.
  5. Run recommendations for all users.
  6. Run alert generation for all users.

Usage:
  python scripts/bootstrap_mvp.py --limit 25      # process up to 25 pending papers
  python scripts/bootstrap_mvp.py --all           # process every pending paper
  python scripts/bootstrap_mvp.py --skip-llm      # only rules/recs/alerts, no OpenRouter
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

from app.utils import load_env, ensure_dirs  # noqa: E402
load_env()
ensure_dirs()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bootstrap")


def print_stats(session, label: str):
    from app.database import (
        Paper, Summary, KGEntity, KGEdge, EvidenceSpan, AlertRule, Alert,
        RecommendationLog, UserPaperInteraction, User, get_unsummarized_paper_ids,
    )
    print(f"\n{'='*52}\n  {label}\n{'='*52}")
    print(f"  Papers:              {session.query(Paper).count()}")
    print(f"  Summaries:           {session.query(Summary).count()}")
    print(f"  Unsummarized:        {len(get_unsummarized_paper_ids(session))}")
    print(f"  KG entities:         {session.query(KGEntity).count()}")
    print(f"  KG edges:            {session.query(KGEdge).count()}")
    print(f"  Evidence spans:      {session.query(EvidenceSpan).count()}")
    print(f"  Users:               {session.query(User).count()}")
    print(f"  Alert rules:         {session.query(AlertRule).count()}")
    print(f"  Alerts:              {session.query(Alert).count()}")
    print(f"  Recommendation logs: {session.query(RecommendationLog).count()}")
    print(f"  Interactions:        {session.query(UserPaperInteraction).count()}")


def main():
    ap = argparse.ArgumentParser(description="Bootstrap the ResearchRadar MVP")
    ap.add_argument("--limit", type=int, default=25, help="Max papers to process")
    ap.add_argument("--all", action="store_true", help="Process all pending papers")
    ap.add_argument("--skip-llm", action="store_true", help="Skip OpenRouter LLM steps")
    args = ap.parse_args()

    from app.database import (
        create_all_tables, get_session, get_unsummarized_paper_ids,
        ensure_default_alert_rules_for_all_users, User,
    )
    create_all_tables()
    session = get_session()

    try:
        print_stats(session, "INITIAL STATE")

        limit = None if args.all else args.limit

        # ── LLM stages ──────────────────────────────────────────────────────
        if not args.skip_llm:
            from app.openrouter_client import is_api_key_configured
            if not is_api_key_configured():
                log.warning("OPENROUTER_API_KEY not set — skipping LLM stages.")
            else:
                target_ids = get_unsummarized_paper_ids(session, limit=limit)
                log.info("Summarizing %d papers...", len(target_ids))

                # 1. Summaries
                if target_ids:
                    from app.agents.paper_summarizer_agent import PaperSummarizerAgent
                    try:
                        res = PaperSummarizerAgent(skip_existing=True).run(paper_ids=target_ids)
                        log.info("Summarized %d papers.", len(res))
                    except Exception as e:
                        log.error("Summarizer failed: %s", e)

                # 2. Evidence
                try:
                    from app.agents.evidence_extractor_agent import EvidenceExtractorAgent
                    ev = EvidenceExtractorAgent().run(max_papers=limit or 200)
                    log.info("Evidence: %s", ev)
                except Exception as e:
                    log.error("Evidence extractor failed: %s", e)

                # 3. KG
                try:
                    from app.agents.kg_builder_agent import KnowledgeGraphBuilderAgent
                    kg = KnowledgeGraphBuilderAgent().run(limit=limit or 200)
                    log.info("KG processed %d papers.", len(kg) if hasattr(kg, "__len__") else 0)
                except Exception as e:
                    log.error("KG builder failed: %s", e)
        else:
            log.info("--skip-llm set; skipping summarize/evidence/KG stages.")

        # ── 4. Default alert rules ──────────────────────────────────────────
        rule_res = ensure_default_alert_rules_for_all_users(session)
        log.info("Alert rules: %s", rule_res)

        # ── 5. Recommendations ──────────────────────────────────────────────
        try:
            from app.agents.recommendation_agent import RecommendationAgent
            users = session.query(User).filter_by(is_active=True).all()
            total = 0
            for u in users:
                try:
                    r = RecommendationAgent().run(user_id=u.id, top_n=20)
                    total += r.get("scored", 0) if isinstance(r, dict) else 0
                except Exception as e:
                    log.warning("Recommendations failed for user %d: %s", u.id, e)
            log.info("Recommendations scored across %d users (total %d).", len(users), total)
        except Exception as e:
            log.error("RecommendationAgent failed: %s", e)

        # ── 6. Alerts ───────────────────────────────────────────────────────
        try:
            from app.agents.alert_agent import AlertAgent
            ar = AlertAgent().run()
            log.info("Alerts: %s", ar)
        except Exception as e:
            log.error("AlertAgent failed: %s", e)

        print_stats(session, "FINAL STATE")
        print("\nBootstrap complete.\n")

    finally:
        session.close()


if __name__ == "__main__":
    main()

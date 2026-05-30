"""
RecommendationAgent — scores papers for each user using the v2 scoring formula.

Score formula:
  recommendation_score =
    0.25 * profile_interest_match
  + 0.20 * interaction_similarity
  + 0.15 * topic_velocity
  + 0.15 * research_opportunity_score
  + 0.10 * recency
  + 0.10 * graph_similarity_to_saved_papers
  + 0.05 * code_or_reproducibility_bonus
  - 0.20 * ignored_topic_penalty
  - 0.15 * already_seen_penalty
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.database import (
    Paper, Summary, UserProfile, UserPaperInteraction, SavedTopic,
    TrendMemory, KGEntity, PaperEntityMention,
    RecommendationLog, get_session, get_or_create_profile,
)
from app.engines.personalization_engine import PersonalizationEngine

logger = logging.getLogger(__name__)


def _keyword_overlap(text1: str, keywords: List[str]) -> float:
    if not text1 or not keywords:
        return 0.0
    text1_lower = text1.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text1_lower)
    return min(1.0, hits / max(len(keywords), 1))


def _recency_score(published_date) -> float:
    if not published_date:
        return 0.3
    try:
        if hasattr(published_date, "year"):
            pub = datetime(published_date.year, published_date.month, published_date.day)
        else:
            pub = datetime.strptime(str(published_date)[:10], "%Y-%m-%d")
        days_old = (datetime.utcnow() - pub).days
        return max(0.0, 1.0 - days_old / 90)  # Full score for today, 0 after 90 days
    except Exception:
        return 0.3


class RecommendationAgent:
    """Compute recommendation scores and persist them in recommendation_logs."""

    def run(
        self,
        user_id: int,
        candidate_paper_ids: Optional[List[int]] = None,
        top_n: int = 20,
    ) -> Dict:
        """
        Score papers for a user and store results.

        Args:
            user_id:              Target user.
            candidate_paper_ids:  Papers to score. None → latest 200 unseen papers.
            top_n:                How many top recommendations to return.
        """
        session = get_session()
        try:
            return self._run(session, user_id, candidate_paper_ids, top_n)
        finally:
            session.close()

    def _run(self, session, user_id, candidate_ids, top_n) -> Dict:
        profile  = get_or_create_profile(session, user_id)
        interests   = json.loads(profile.interests_json or "[]")
        pref_topics = json.loads(profile.preferred_topics_json or "[]")
        ignored     = json.loads(profile.ignored_topics_json or "[]")
        all_kw = list(set(interests + pref_topics))

        # Seen papers
        seen_ids = {
            row.paper_id
            for row in session.query(UserPaperInteraction)
            .filter_by(user_id=user_id)
            .all()
        }
        # Saved papers (for graph similarity proxy)
        saved_ids = {
            row.paper_id
            for row in session.query(UserPaperInteraction)
            .filter_by(user_id=user_id, interaction_type="saved")
            .all()
        }
        # Ignored papers
        ignored_paper_ids = {
            row.paper_id
            for row in session.query(UserPaperInteraction)
            .filter_by(user_id=user_id, interaction_type="ignored")
            .all()
        }
        # Saved topics
        saved_topics = [
            r.topic_name for r in session.query(SavedTopic).filter_by(user_id=user_id).all()
        ]
        all_interest_kw = list(set(all_kw + saved_topics))

        # Velocity map: TrendMemory rows joined with KGEntity for the name
        velocity_map: Dict[str, float] = {}
        for t in session.query(TrendMemory).all():
            name = t.entity_type  # fallback to type string
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            velocity_map[name] = t.velocity_score

        # Candidate papers
        if candidate_ids:
            papers = session.query(Paper).filter(Paper.id.in_(candidate_ids)).all()
        else:
            papers = (
                session.query(Paper)
                .order_by(Paper.published_date.desc())
                .limit(200)
                .all()
            )

        results = []
        for paper in papers:
            pid   = paper.id
            title = paper.title or ""
            abstr = paper.abstract or ""
            text  = (title + " " + abstr).lower()

            summary = session.query(Summary).filter_by(paper_id=pid).first()

            # ── Component scores ──────────────────────────────────────────

            profile_interest_match = _keyword_overlap(text, all_interest_kw)

            # Interaction similarity: boost if paper shares entities with saved papers
            graph_sim = 0.0
            if saved_ids:
                paper_entity_ids = {
                    m.entity_id
                    for m in session.query(PaperEntityMention).filter_by(paper_id=pid).all()
                }
                for sp_id in list(saved_ids)[:10]:
                    saved_entity_ids = {
                        m.entity_id
                        for m in session.query(PaperEntityMention).filter_by(paper_id=sp_id).all()
                    }
                    if paper_entity_ids and saved_entity_ids:
                        overlap = len(paper_entity_ids & saved_entity_ids)
                        union   = len(paper_entity_ids | saved_entity_ids)
                        graph_sim = max(graph_sim, overlap / max(union, 1))

            # Topic velocity bonus
            topic_velocity = 0.0
            for entity in session.query(PaperEntityMention).filter_by(paper_id=pid).limit(10).all():
                entity_obj = session.query(KGEntity).filter_by(id=entity.entity_id).first()
                if entity_obj:
                    v = velocity_map.get(entity_obj.name, 0.0)
                    topic_velocity = max(topic_velocity, min(1.0, v))

            # Opportunity score from summary
            opp_score = 0.0
            code_bonus = 0.0
            if summary:
                opp_raw = getattr(summary, "opportunity_score", None)
                if opp_raw is not None:
                    try:
                        opp_score = float(opp_raw) / 10.0
                    except Exception:
                        pass
                reprod = getattr(summary, "reproducibility_score", None)
                if reprod is not None:
                    try:
                        code_bonus = float(reprod) / 10.0 * 0.05
                    except Exception:
                        pass
                if getattr(summary, "official_code_url", ""):
                    code_bonus = max(code_bonus, 0.05)

            recency = _recency_score(paper.published_date)

            # Penalties
            ignored_topic_pen = _keyword_overlap(text, ignored) * 0.20
            already_seen_pen  = 0.15 if pid in seen_ids else 0.0
            ignored_paper_pen = 0.30 if pid in ignored_paper_ids else 0.0

            # Interaction similarity term
            interaction_sim = min(1.0, len([s for s in saved_ids if s == pid]) * 0.5)

            score = (
                0.25 * profile_interest_match
                + 0.20 * interaction_sim
                + 0.15 * topic_velocity
                + 0.15 * opp_score
                + 0.10 * recency
                + 0.10 * graph_sim
                + code_bonus
                - ignored_topic_pen
                - already_seen_pen
                - ignored_paper_pen
            )
            score = max(0.0, min(1.0, score))

            # Build reason list
            reasons = []
            if profile_interest_match > 0.3:
                top_kw = [kw for kw in all_interest_kw if kw.lower() in text][:3]
                if top_kw:
                    reasons.append(f"Matches your interests: {', '.join(top_kw)}")
            if graph_sim > 0.1:
                reasons.append(f"Similar to {len(saved_ids)} papers you saved")
            if topic_velocity > 0.3:
                reasons.append(f"Topic is trending (velocity {topic_velocity:.0%})")
            if opp_score > 0.6:
                reasons.append("High research opportunity score")
            if code_bonus > 0:
                reasons.append("Code or reproducibility available")
            if not reasons:
                reasons.append("General relevance to your profile")

            results.append({
                "paper_id": pid,
                "title":    title,
                "score":    round(score, 4),
                "reasons":  reasons,
            })

        results.sort(key=lambda x: x["score"], reverse=True)
        top_results = results[:top_n]

        # Persist to recommendation_logs
        for rec in top_results:
            existing = (
                session.query(RecommendationLog)
                .filter_by(user_id=user_id, paper_id=rec["paper_id"])
                .first()
            )
            if existing:
                existing.score       = rec["score"]
                existing.reason_json = json.dumps(rec["reasons"])
            else:
                session.add(RecommendationLog(
                    user_id=user_id,
                    paper_id=rec["paper_id"],
                    score=rec["score"],
                    reason_json=json.dumps(rec["reasons"]),
                ))
        session.commit()

        return {
            "user_id":       user_id,
            "scored":        len(results),
            "recommendations": top_results,
        }

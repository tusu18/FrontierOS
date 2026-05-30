"""
AlertAgent — generates in-app alerts for topic spikes, paper matches,
research gaps, and code availability based on user AlertRules.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.database import (
    User, AlertRule, Alert, RecommendationLog,
    TrendMemory, KGEntity, Paper, Summary,
    SavedTopic, UserProfile, get_session,
)

logger = logging.getLogger(__name__)


def _create_alert(session, user_id: int, alert_type: str, title: str, message: str,
                  paper_ids: List[int] = None, entity_ids: List[int] = None):
    a = Alert(
        user_id=user_id,
        alert_type=alert_type,
        title=title,
        message=message,
        paper_ids_json=json.dumps(paper_ids or []),
        entity_ids_json=json.dumps(entity_ids or []),
        read_status=False,
        delivered_status=False,
    )
    session.add(a)


class AlertAgent:
    """Evaluates alert rules for all users and generates alert records."""

    def run(self, user_ids: Optional[List[int]] = None) -> Dict:
        session = get_session()
        try:
            return self._run(session, user_ids)
        finally:
            session.close()

    def _run(self, session, user_ids) -> Dict:
        if user_ids:
            users = session.query(User).filter(User.id.in_(user_ids)).all()
        else:
            users = session.query(User).filter_by(is_active=True).all()

        total_alerts = 0

        for user in users:
            rules = session.query(AlertRule).filter_by(user_id=user.id, enabled=True).all()
            saved_topics = [
                r.topic_name.lower()
                for r in session.query(SavedTopic).filter_by(user_id=user.id).all()
                if r.topic_name
            ]
            # MVP fallback: use onboarding interests when user has no saved topics yet
            if not saved_topics:
                profile = session.query(UserProfile).filter_by(user_id=user.id).first()
                if profile:
                    try:
                        interests = json.loads(profile.interests_json or "[]")
                        preferred = json.loads(profile.preferred_topics_json or "[]")
                        saved_topics = [
                            t.lower() for t in (interests + preferred) if t
                        ]
                    except json.JSONDecodeError:
                        pass

            for rule in rules:
                try:
                    threshold = json.loads(rule.threshold_json or "{}")
                    count = self._eval_rule(
                        session, user.id, rule, saved_topics, threshold
                    )
                    total_alerts += count
                except Exception as exc:
                    logger.warning("Alert rule %d failed: %s", rule.id, exc)

            session.commit()

        return {"users_processed": len(users), "alerts_created": total_alerts}

    def _eval_rule(self, session, user_id, rule, saved_topics, threshold) -> int:
        rt = rule.rule_type
        count = 0

        if rt == "topic_spike":
            count = self._check_topic_spike(session, user_id, saved_topics, threshold)
        elif rt == "paper_match":
            count = self._check_paper_match(session, user_id, threshold)
        elif rt == "new_research_gap":
            count = self._check_research_gap(session, user_id, saved_topics, threshold)
        elif rt == "new_code_available":
            count = self._check_code_available(session, user_id, saved_topics)

        return count

    def _check_topic_spike(self, session, user_id, saved_topics, threshold) -> int:
        min_velocity = float(threshold.get("min_velocity", 0.4))
        created = 0
        trends = (
            session.query(TrendMemory)
            .filter(TrendMemory.velocity_score >= min_velocity)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(10)
            .all()
        )
        for t in trends:
            # Resolve entity name via KGEntity join
            name = t.entity_type  # fallback
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            name_lower = name.lower()
            # When user has interests/topics, filter; otherwise use global trend velocity (MVP)
            if saved_topics and not any(st in name_lower or name_lower in st for st in saved_topics):
                continue
            # Don't re-alert the same topic within 7 days
            recent = (
                session.query(Alert)
                .filter_by(user_id=user_id, alert_type="topic_spike")
                .filter(Alert.message.contains(name[:40]))
                .filter(Alert.created_at >= datetime.utcnow() - timedelta(days=7))
                .first()
            )
            if recent:
                continue
            pct = int(t.velocity_score * 100)
            _create_alert(
                session, user_id, "topic_spike",
                f"Topic Spike: {name}",
                f"{name} is trending — velocity up {pct}% this period. "
                f"Saturation: {t.saturation_score:.0%}.",
                entity_ids=[t.entity_id] if t.entity_id else [],
            )
            created += 1
        return created

    def _check_paper_match(self, session, user_id, threshold) -> int:
        min_score = float(threshold.get("min_score", 0.8))
        created = 0
        recs = (
            session.query(RecommendationLog)
            .filter_by(user_id=user_id)
            .filter(RecommendationLog.score >= min_score)
            .filter(RecommendationLog.shown_at == None)  # noqa: E711
            .limit(5)
            .all()
        )
        for rec in recs:
            paper = session.query(Paper).filter_by(id=rec.paper_id).first()
            if not paper:
                continue
            reasons = json.loads(rec.reason_json or "[]")
            _create_alert(
                session, user_id, "paper_match",
                f"High-match paper: {paper.title[:80]}",
                f"Score {rec.score:.0%}. " + " ".join(reasons[:2]),
                paper_ids=[paper.id],
            )
            rec.shown_at = datetime.utcnow()
            created += 1
        return created

    def _check_research_gap(self, session, user_id, saved_topics, threshold) -> int:
        min_count = int(threshold.get("min_count", 3))
        created = 0
        gaps = (
            session.query(KGEntity)
            .filter(KGEntity.entity_type.in_(["ResearchGap", "Limitation"]))
            .filter(KGEntity.frequency_count >= min_count)
            .order_by(KGEntity.frequency_count.desc())
            .limit(10)
            .all()
        )
        for gap in gaps:
            name_lower = gap.name.lower()
            if saved_topics and not any(st in name_lower or name_lower in st for st in saved_topics):
                continue
            recent = (
                session.query(Alert)
                .filter_by(user_id=user_id, alert_type="research_gap")
                .filter(Alert.message.contains(gap.name[:30]))
                .filter(Alert.created_at >= datetime.utcnow() - timedelta(days=14))
                .first()
            )
            if recent:
                continue
            _create_alert(
                session, user_id, "research_gap",
                f"New Research Gap: {gap.name[:80]}",
                f"Gap mentioned in {gap.frequency_count} papers. Consider this for your next project.",
                entity_ids=[gap.id],
            )
            created += 1
        return created

    def _check_code_available(self, session, user_id, saved_topics) -> int:
        """Alert on highly reproducible / implementable papers (code_generation_potential >= 8)."""
        cutoff = datetime.utcnow() - timedelta(days=3)
        created = 0
        summaries = (
            session.query(Summary)
            .filter(Summary.code_generation_potential >= 8)
            .filter(Summary.created_at >= cutoff)
            .limit(20)
            .all()
        )
        for s in summaries:
            paper = session.query(Paper).filter_by(id=s.paper_id).first()
            if not paper:
                continue
            text = (paper.title + " " + (paper.abstract or "")).lower()
            if saved_topics and not any(st in text for st in saved_topics):
                continue
            recent = (
                session.query(Alert)
                .filter_by(user_id=user_id, alert_type="code_available")
                .filter(Alert.paper_ids_json.contains(str(paper.id)))
                .filter(Alert.created_at >= datetime.utcnow() - timedelta(days=7))
                .first()
            )
            if recent:
                continue
            _create_alert(
                session, user_id, "code_available",
                f"Highly implementable paper: {paper.title[:80]}",
                f"Code generation potential score: {s.code_generation_potential}/10. "
                f"Reproducibility: {s.reproducibility_score}/10.",
                paper_ids=[paper.id],
            )
            created += 1
        return created

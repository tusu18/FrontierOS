"""
DigestAgent — generates personalized daily/weekly research digests using
the global KG, personal memory, and LLM summarization.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import requests

from app.database import (
    User, UserProfile, Paper, Summary, TrendMemory, KGEntity,
    RecommendationLog, EmailDigest, SavedTopic, get_session, get_or_create_profile,
)

logger = logging.getLogger(__name__)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL              = os.getenv("SUMMARIZER_MODEL", "mistralai/mistral-7b-instruct")


def _call_llm(prompt: str, max_tokens: int = 1500) -> str:
    if not OPENROUTER_API_KEY:
        return "(LLM not configured)"
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("LLM digest call failed: %s", exc)
        return "(digest generation failed)"


class DigestAgent:

    def generate_daily(self, user_id: int) -> Dict:
        session = get_session()
        try:
            return self._daily(session, user_id)
        finally:
            session.close()

    def generate_weekly(self, user_id: int) -> Dict:
        session = get_session()
        try:
            return self._weekly(session, user_id)
        finally:
            session.close()

    def _daily(self, session, user_id: int) -> Dict:
        profile    = get_or_create_profile(session, user_id)
        interests  = json.loads(profile.interests_json or "[]")
        saved_tps  = [r.topic_name for r in session.query(SavedTopic).filter_by(user_id=user_id).all()]
        all_kw     = list(set(interests + saved_tps))

        # Top recommended papers
        recs = (
            session.query(RecommendationLog)
            .filter_by(user_id=user_id)
            .order_by(RecommendationLog.score.desc())
            .limit(5)
            .all()
        )
        top_papers = []
        for r in recs:
            p = session.query(Paper).filter_by(id=r.paper_id).first()
            if p:
                top_papers.append(f"- {p.title} (score {r.score:.0%})")

        # Top trends — resolve entity name via KGEntity join
        trends = (
            session.query(TrendMemory)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(3)
            .all()
        )
        trend_lines = []
        for t in trends:
            name = t.entity_type
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            trend_lines.append(f"- {name}: velocity {t.velocity_score:.0%}")

        # Top gaps
        gaps = (
            session.query(KGEntity)
            .filter(KGEntity.entity_type.in_(["ResearchGap", "Limitation"]))
            .order_by(KGEntity.frequency_count.desc())
            .limit(3)
            .all()
        )
        gap_lines = [f"- {g.name} (mentioned {g.frequency_count}×)" for g in gaps]

        # Highly implementable papers (code_generation_potential >= 8)
        code_papers = (
            session.query(Summary)
            .filter(Summary.code_generation_potential >= 8)
            .order_by(Summary.created_at.desc())
            .limit(3)
            .all()
        )
        code_lines = []
        for s in code_papers:
            p = session.query(Paper).filter_by(id=s.paper_id).first()
            if p:
                code_lines.append(f"- {p.title} (impl score {s.code_generation_potential}/10)")

        papers_block  = "\n".join(top_papers) or "No recommendations yet."
        trends_block  = "\n".join(trend_lines) or "No trend data yet."
        gaps_block    = "\n".join(gap_lines)   or "No gaps yet."
        code_block    = "\n".join(code_lines)  or "No code-ready papers."

        interests_str = ", ".join(all_kw[:5]) or "general CS"

        prompt = f"""You are ResearchRadar's digest writer.
Write a concise, exciting daily digest for a researcher interested in: {interests_str}.

Top Recommended Papers:
{papers_block}

Trending Topics Today:
{trends_block}

Open Research Gaps:
{gaps_block}

Code-Ready Papers:
{code_block}

Format: Markdown. Sections: 🔥 Top Papers | 📈 Trends | 🕳 Research Gaps | 💻 Code Available | 💡 Today's Project Idea.
Be energetic, specific, and useful. End with one concrete project idea to build this week."""

        content = _call_llm(prompt)
        subject = f"Your ResearchRadar Daily Digest — {date.today().strftime('%b %d, %Y')}"
        paper_ids = [r.paper_id for r in recs]

        digest = EmailDigest(
            user_id=user_id,
            digest_type="daily",
            subject=subject,
            content_markdown=content,
            paper_ids_json=json.dumps(paper_ids),
        )
        session.add(digest)
        session.commit()

        return {"digest_id": digest.id, "subject": subject, "content": content}

    def _weekly(self, session, user_id: int) -> Dict:
        profile   = get_or_create_profile(session, user_id)
        interests = json.loads(profile.interests_json or "[]")
        saved_tps = [r.topic_name for r in session.query(SavedTopic).filter_by(user_id=user_id).all()]
        all_kw    = list(set(interests + saved_tps))

        week_ago = datetime.utcnow() - timedelta(days=7)

        # Papers this week
        recent_papers = (
            session.query(Paper)
            .filter(Paper.created_at >= week_ago)
            .order_by(Paper.created_at.desc())
            .limit(100)
            .all()
        )
        total_new = len(recent_papers)

        # Accelerating topics — resolve name via KGEntity
        accel_trends = (
            session.query(TrendMemory)
            .filter(TrendMemory.velocity_score >= 0.3)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(5)
            .all()
        )
        accel_lines = []
        for t in accel_trends:
            name = t.entity_type
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            accel_lines.append(f"- {name}: +{t.velocity_score:.0%}")

        # Saturating topics
        sat_trends = (
            session.query(TrendMemory)
            .order_by(TrendMemory.saturation_score.desc())
            .limit(3)
            .all()
        )
        sat_lines = []
        for t in sat_trends:
            name = t.entity_type
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            sat_lines.append(f"- {name}: {t.saturation_score:.0%} saturated")

        # Growing gaps
        new_gaps = (
            session.query(KGEntity)
            .filter(KGEntity.entity_type.in_(["ResearchGap", "Limitation"]))
            .filter(KGEntity.created_at >= week_ago)
            .order_by(KGEntity.frequency_count.desc())
            .limit(5)
            .all()
        )
        gap_lines = [f"- {g.name}" for g in new_gaps]

        interests_str = ", ".join(all_kw[:6]) or "general CS"
        week_str      = f"{week_ago.strftime('%b %d')} – {date.today().strftime('%b %d, %Y')}"

        prompt = f"""You are ResearchRadar's weekly intelligence writer.
Write a rich "What Changed in Your Field" weekly report for a researcher focused on: {interests_str}.

Week: {week_str}
New papers this week: {total_new}

Accelerating Topics:
{chr(10).join(accel_lines) or 'None detected.'}

Saturating Datasets:
{chr(10).join(sat_lines) or 'None detected.'}

Emerging Research Gaps:
{chr(10).join(gap_lines) or 'None detected.'}

Format: Markdown. Include:
1. Executive Summary (3 bullets)
2. 📈 Topics That Accelerated
3. 📉 Topics That Declined or Saturated
4. 🕳 Strongest New Research Gaps
5. 💡 Top Project Idea This Week
6. 🎯 Papers Worth Reading

Be specific, cite numbers, and give actionable advice. This is a researcher's weekly intelligence briefing."""

        content = _call_llm(prompt, max_tokens=2000)
        subject = f"ResearchRadar Weekly: What changed in {interests_str[:40]} — {date.today().strftime('%b %d')}"

        digest = EmailDigest(
            user_id=user_id,
            digest_type="weekly",
            subject=subject,
            content_markdown=content,
            paper_ids_json=json.dumps([p.id for p in recent_papers[:20]]),
        )
        session.add(digest)
        session.commit()

        return {"digest_id": digest.id, "subject": subject, "content": content}

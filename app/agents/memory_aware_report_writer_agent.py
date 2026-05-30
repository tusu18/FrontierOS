"""
MemoryAwareReportWriterAgent

Extends ReportWriterAgent with historical memory comparison.

Additional report capabilities:
  - Compare today's papers vs historical KG trends
  - Highlight accelerating vs decelerating topics
  - Surface saturated datasets / benchmarks
  - Identify newly appearing methods across categories
  - Show resolved vs unresolved research gaps
  - Report on novel entity combinations
"""

from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.database import get_session, get_papers_with_summaries, save_report, KGEntity, TrendMemory
from app.memory.research_memory_engine import ResearchMemoryEngine
from app.agents.research_gap_memory_agent import ResearchGapMemoryAgent
from app.openrouter_client import call_openrouter, is_api_key_configured
from app.utils import truncate

logger = logging.getLogger(__name__)

_engine = ResearchMemoryEngine()


MEMORY_REPORT_TYPES = [
    "Memory Intelligence Report",
    "Trend Evolution Report",
    "Research Gap Opportunity Report",
    "Method Lineage Report",
    "Dataset Saturation Report",
    "Cross-Domain Discovery Report",
    "Weekly Research Radar",
]


class MemoryAwareReportWriterAgent:
    """
    Generates reports that compare current papers against historical
    knowledge graph memory — not just a daily snapshot.
    """

    def run(
        self,
        report_type: str = "Memory Intelligence Report",
        category: Optional[str] = None,
        save: bool = True,
    ) -> str:
        if not is_api_key_configured():
            return self._offline_report(report_type, category)

        intelligence = self._gather_intelligence(category)
        content = self._generate_report(report_type, category, intelligence)

        if save and content:
            session = get_session()
            try:
                from app.database import save_report
                save_report(session, report_type, f"{report_type} — {date.today().isoformat()}", content, [])
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"MemoryAwareReportWriterAgent: save error: {e}")
            finally:
                session.close()

        return content

    def _gather_intelligence(self, category: Optional[str] = None) -> Dict:
        """Compile trend, gap, and entity intelligence from the knowledge graph."""
        intel: Dict = {}

        # Trending entities (7-day)
        intel["trending_7d"] = _engine.get_trending_entities(limit=15)

        # Fastest-growing methods
        intel["trending_methods"] = _engine.get_trending_entities(entity_type="Method", limit=10)

        # Trending datasets
        intel["trending_datasets"] = _engine.get_trending_entities(entity_type="Dataset", limit=8)

        # Research gaps
        intel["research_gaps"] = _engine.find_research_gaps(area=category, limit=10)

        # Saturation leaders (datasets with highest saturation)
        session = get_session()
        try:
            saturated = (
                session.query(TrendMemory)
                .filter(TrendMemory.entity_type == "Dataset")
                .order_by(TrendMemory.saturation_score.desc())
                .limit(10)
                .all()
            )
            intel["saturated_datasets"] = []
            for row in saturated:
                ent = session.query(KGEntity).filter_by(id=row.entity_id).first()
                if ent:
                    intel["saturated_datasets"].append({
                        "name": ent.name,
                        "saturation": round(row.saturation_score, 2),
                        "count": ent.frequency_count,
                    })

            # Entity type distribution
            from sqlalchemy import func
            type_counts = (
                session.query(KGEntity.entity_type, func.count(KGEntity.id))
                .group_by(KGEntity.entity_type)
                .all()
            )
            intel["entity_type_distribution"] = {et: cnt for et, cnt in type_counts}

            # Total KG size
            from app.database import get_kg_stats
            intel["kg_stats"] = get_kg_stats(session)

        except Exception as exc:
            logger.warning(f"_gather_intelligence: {exc}")
        finally:
            session.close()

        # Compare recent 7-day vs prior 7-day paper counts
        intel["momentum"] = self._compute_momentum()

        return intel

    def _compute_momentum(self) -> Dict:
        """Return count of new entities in last 7d vs prior 7d."""
        session = get_session()
        try:
            today = date.today()
            week_ago = (today - timedelta(days=7)).isoformat()
            two_weeks_ago = (today - timedelta(days=14)).isoformat()

            recent_new = session.query(KGEntity).filter(
                KGEntity.first_seen_date >= week_ago
            ).count()

            prior_new = session.query(KGEntity).filter(
                KGEntity.first_seen_date >= two_weeks_ago,
                KGEntity.first_seen_date < week_ago,
            ).count()

            return {
                "new_entities_this_week": recent_new,
                "new_entities_prior_week": prior_new,
                "acceleration": "up" if recent_new > prior_new else "down" if recent_new < prior_new else "stable",
            }
        finally:
            session.close()

    def _generate_report(self, report_type: str, category: Optional[str], intel: Dict) -> str:
        """Use OpenRouter to generate a polished Markdown report."""
        intel_text = self._format_intelligence(intel)

        system_prompt = (
            "You are a senior AI research analyst writing a structured intelligence report. "
            "Use the provided knowledge-graph data to write a concise, insightful Markdown report. "
            "Do NOT invent data. Cite entity names and counts from the provided intelligence. "
            "Use ##, ###, bullet points, and tables where appropriate."
        )

        user_prompt = f"""
Write a **{report_type}**{f' (focus: {category})' if category else ''} based on the following
knowledge graph intelligence extracted from {intel.get('kg_stats', {}).get('entities', 0)} entities
and {intel.get('kg_stats', {}).get('edges', 0)} relationships in the research memory database.

---
{intel_text}
---

Report structure (adapt sections to the report type):
1. Executive Summary (3–5 bullet points)
2. Trending This Week (topics, methods, datasets accelerating)
3. Saturated / Declining Areas (what to avoid or build on top of)
4. Top Research Gaps & Opportunities (with implementation potential scores)
5. Cross-Domain Signals (methods appearing in new areas)
6. Recommended Next Steps (3 concrete project/research directions)
7. KG Memory Stats (entity counts, trend records, semantic memories)

Today: {date.today().isoformat()}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return call_openrouter(messages, temperature=0.4, max_tokens=3000)

    def _format_intelligence(self, intel: Dict) -> str:
        lines = []

        if intel.get("momentum"):
            m = intel["momentum"]
            lines.append(
                f"**Knowledge Graph Momentum:** {m['new_entities_this_week']} new entities this week "
                f"vs {m['new_entities_prior_week']} prior week ({m['acceleration']})"
            )

        if intel.get("trending_7d"):
            top = [f"{t['name']} (v={t['velocity']:.2f})" for t in intel["trending_7d"][:8]]
            lines.append(f"\n**Trending entities (7d):** {', '.join(top)}")

        if intel.get("trending_methods"):
            top = [t["name"] for t in intel["trending_methods"][:6]]
            lines.append(f"**Trending methods:** {', '.join(top)}")

        if intel.get("trending_datasets"):
            top = [t["name"] for t in intel["trending_datasets"][:5]]
            lines.append(f"**Trending datasets:** {', '.join(top)}")

        if intel.get("saturated_datasets"):
            top = [f"{d['name']} ({d['saturation']:.0%} saturation)" for d in intel["saturated_datasets"][:5]]
            lines.append(f"**Saturated datasets:** {', '.join(top)}")

        if intel.get("research_gaps"):
            for g in intel["research_gaps"][:6]:
                lines.append(
                    f"- Gap: **{g['name']}** | freq={g['frequency']} | "
                    f"gap_score={g['gap_score']} | impl_potential={g.get('implementation_potential', '?')}"
                )

        if intel.get("entity_type_distribution"):
            dist = intel["entity_type_distribution"]
            parts = [f"{k}: {v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])[:10]]
            lines.append(f"\n**Entity distribution:** {', '.join(parts)}")

        return "\n".join(lines) or "No intelligence data available yet."

    def _offline_report(self, report_type: str, category: Optional[str]) -> str:
        """Fallback when no API key is configured."""
        intel = self._gather_intelligence(category)
        return (
            f"# {report_type} (Offline — No API Key)\n\n"
            f"**KG Stats:** {intel.get('kg_stats', {})}\n\n"
            f"**Trending (7d):** {[t['name'] for t in intel.get('trending_7d', [])[:10]]}\n\n"
            f"**Research Gaps:** {[g['name'] for g in intel.get('research_gaps', [])[:5]]}\n\n"
            "_Add OPENROUTER_API_KEY to .env for full AI-generated analysis._"
        )

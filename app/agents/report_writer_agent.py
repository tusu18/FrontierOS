"""ReportWriterAgent: Generates daily/weekly/monthly research reports."""

from __future__ import annotations
import json
import logging
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.database import get_session, get_papers_with_summaries, save_report
from app.openrouter_client import call_openrouter, is_api_key_configured
from app.prompts.report_generation import build_report_prompt, build_whats_next_prompt

logger = logging.getLogger(__name__)

REPORT_TYPES = [
    "Daily report",
    "Weekly report",
    "Monthly report",
    "Category-specific report",
    "Emerging topics report",
    "Research gap report",
    "What should I work on next?",
]


class ReportWriterAgent:
    """
    Generates research reports from stored papers.

    Input:  report_type, optional category filter
    Output: Markdown report string
    """

    def _get_papers_for_report(self, report_type: str, category: Optional[str] = None) -> List[Dict]:
        session = get_session()
        try:
            today = date.today()
            if "daily" in report_type.lower():
                limit = 60
                date_str = today.isoformat()
            elif "weekly" in report_type.lower():
                limit = 200
                date_str = None
            else:
                limit = 300
                date_str = None

            papers = get_papers_with_summaries(session, limit=limit, date_str=date_str if "daily" in report_type.lower() else None)

            if not papers:
                # Fall back to all papers if no date match
                papers = get_papers_with_summaries(session, limit=limit)

            if category:
                papers = [p for p in papers if category.lower() in p.get("primary_category", "").lower()
                          or category.lower() in " ".join(p.get("categories", [])).lower()]

            return papers
        finally:
            session.close()

    def _build_papers_text(self, papers: List[Dict]) -> str:
        parts = []
        for p in papers[:40]:
            title = p.get("title", "")
            arxiv_id = p.get("arxiv_id", "")
            url = p.get("arxiv_url", f"https://arxiv.org/abs/{arxiv_id}")
            summary = p.get("one_line_summary", p.get("abstract", "")[:200])
            novelty = p.get("novelty_score", "N/A")
            impact = p.get("impact_score", "N/A")
            area = p.get("research_area", p.get("primary_category", ""))
            method = p.get("method", "")[:200]
            contribution = p.get("main_contribution", "")[:200]

            parts.append(
                f"**{title}** [{arxiv_id}]({url})\n"
                f"Area: {area} | Novelty: {novelty}/10 | Impact: {impact}/10\n"
                f"Summary: {summary}\n"
                f"Method: {method}\n"
                f"Contribution: {contribution}"
            )
        return "\n\n---\n\n".join(parts)

    def run(
        self,
        report_type: str = "Daily report",
        category: Optional[str] = None,
        save: bool = True,
    ) -> str:
        if not is_api_key_configured():
            return "⚠️ API key not configured."

        papers = self._get_papers_for_report(report_type, category)
        if not papers:
            return "⚠️ No papers found for this report. Fetch some papers first."

        papers_text = self._build_papers_text(papers)

        if "what should i work on" in report_type.lower():
            messages = build_whats_next_prompt(papers_text)
        else:
            messages = build_report_prompt(report_type, papers_text, category or "")

        logger.info(f"ReportWriterAgent: generating '{report_type}' from {len(papers)} papers")
        content = call_openrouter(messages, temperature=0.3, max_tokens=4000)

        if not content:
            return "❌ Report generation failed."

        if save:
            session = get_session()
            try:
                paper_ids = [p.get("id") for p in papers if p.get("id")]
                title = f"{report_type} – {date.today().isoformat()}"
                if category:
                    title += f" [{category}]"
                save_report(session, report_type, title, content, paper_ids)
                session.commit()
                logger.info("ReportWriterAgent: report saved.")
            except Exception as e:
                session.rollback()
                logger.error(f"ReportWriterAgent: save error: {e}")
            finally:
                session.close()

        return content

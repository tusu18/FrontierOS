"""TrendAnalystAgent: Aggregates summaries and identifies research trends."""

from __future__ import annotations
import json
import logging
from datetime import date
from typing import Dict, List, Optional

from app.database import get_session, get_papers_with_summaries, save_daily_trend
from app.openrouter_client import call_openrouter_json, is_api_key_configured
from app.prompts.trend_analysis import build_trend_prompt

logger = logging.getLogger(__name__)


class TrendAnalystAgent:
    """
    Analyzes trends across all stored paper summaries.

    Input:  optional date range
    Output: TrendAnalysis dict
    """

    def _build_summaries_text(self, papers: List[Dict]) -> str:
        parts = []
        for p in papers[:60]:  # Limit for token budget
            title = p.get("title", "")
            summary = p.get("one_line_summary", p.get("abstract", ""))
            area = p.get("research_area", "")
            tags = ", ".join(p.get("trend_tags", []))
            keywords = ", ".join(p.get("keywords", []))
            method = p.get("method", "")[:200]
            parts.append(
                f"- [{area}] {title}\n"
                f"  Summary: {summary}\n"
                f"  Tags: {tags} | Keywords: {keywords}\n"
                f"  Method: {method}"
            )
        return "\n\n".join(parts)

    def run(self, limit: int = 100, save: bool = True) -> Dict:
        if not is_api_key_configured():
            logger.warning("TrendAnalystAgent: No API key.")
            return {}

        session = get_session()
        try:
            papers = get_papers_with_summaries(session, limit=limit)
        finally:
            session.close()

        if not papers:
            logger.warning("TrendAnalystAgent: no papers found.")
            return {}

        summaries_text = self._build_summaries_text(papers)
        messages = build_trend_prompt(summaries_text)
        trend_data = call_openrouter_json(messages, temperature=0.3, max_tokens=2000)

        if not trend_data:
            logger.warning("TrendAnalystAgent: empty response.")
            return {}

        if save:
            session = get_session()
            try:
                save_daily_trend(session, date.today().isoformat(), trend_data)
                session.commit()
                logger.info("TrendAnalystAgent: saved daily trend.")
            except Exception as e:
                session.rollback()
                logger.error(f"TrendAnalystAgent: save error: {e}")
            finally:
                session.close()

        return trend_data

    def get_category_stats(self, papers: List[Dict]) -> Dict[str, int]:
        from collections import Counter
        cats = [p.get("primary_category", "unknown") for p in papers]
        return dict(Counter(cats).most_common(20))

    def get_keyword_freq(self, papers: List[Dict]) -> Dict[str, int]:
        from collections import Counter
        kws = []
        for p in papers:
            kws.extend(p.get("keywords", []))
        return dict(Counter(kws).most_common(30))

    def get_trend_tag_freq(self, papers: List[Dict]) -> Dict[str, int]:
        from collections import Counter
        tags = []
        for p in papers:
            tags.extend(p.get("trend_tags", []))
        return dict(Counter(tags).most_common(30))

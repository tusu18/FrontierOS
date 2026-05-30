"""PaperSummarizerAgent: Uses OpenRouter GPT-4o mini to summarize papers."""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

from app.database import (
    get_session, upsert_summary, upsert_keywords, upsert_trend_tags,
    Paper, Summary
)
from app.openrouter_client import call_openrouter_json, is_api_key_configured
from app.prompts.summarize_paper import build_summarize_prompt
from app.utils import clamp_score

logger = logging.getLogger(__name__)


class PaperSummarizerAgent:
    """
    Summarizes papers using OpenRouter.

    Input:  list of paper dicts (with db_id) or paper DB ids
    Output: dict of {arxiv_id: summary_data}
    """

    def __init__(self, skip_existing: bool = True):
        self.skip_existing = skip_existing

    def summarize_paper(self, paper_id: int, title: str, abstract: str, full_text: str = "") -> Optional[Dict]:
        """Summarize a single paper and save to DB."""
        if not is_api_key_configured():
            logger.warning("PaperSummarizerAgent: No API key configured.")
            return None

        messages = build_summarize_prompt(title, abstract, full_text)
        data = call_openrouter_json(messages, temperature=0.2, max_tokens=2500)

        if not data:
            logger.warning(f"PaperSummarizerAgent: empty response for paper_id={paper_id}")
            return None

        # Clamp all scores
        for score_key in [
            "novelty_score", "impact_score", "technical_depth_score",
            "implementation_difficulty_score", "reproducibility_score", "code_generation_potential"
        ]:
            data[score_key] = clamp_score(data.get(score_key, 5))

        session = get_session()
        try:
            upsert_summary(session, paper_id, data)
            upsert_keywords(session, paper_id, data.get("keywords", []))
            upsert_trend_tags(session, paper_id, data.get("trend_tags", []))
            session.commit()
            logger.info(f"PaperSummarizerAgent: summarized paper_id={paper_id}")
        except Exception as e:
            session.rollback()
            logger.error(f"PaperSummarizerAgent: DB save error: {e}")
        finally:
            session.close()

        return data

    def run(self, paper_ids: Optional[List[int]] = None, progress_callback=None) -> Dict[int, Dict]:
        """Summarize all unsummarized papers (or specified paper_ids)."""
        session = get_session()
        try:
            if paper_ids:
                papers = session.query(Paper).filter(Paper.id.in_(paper_ids)).all()
            else:
                # Get all papers without summaries
                summarized_ids = {s.paper_id for s in session.query(Summary).all()}
                q = session.query(Paper)
                if self.skip_existing:
                    all_ids = {p.id for p in session.query(Paper).all()}
                    unsummarized = all_ids - summarized_ids
                    papers = session.query(Paper).filter(Paper.id.in_(unsummarized)).all()
                else:
                    papers = session.query(Paper).all()
        finally:
            session.close()

        if not papers:
            logger.info("PaperSummarizerAgent: no papers to summarize.")
            return {}

        results = {}
        for i, paper in enumerate(papers):
            logger.info(f"PaperSummarizerAgent: [{i+1}/{len(papers)}] {paper.title[:60]}...")
            try:
                data = self.summarize_paper(paper.id, paper.title, paper.abstract)
                if data:
                    results[paper.id] = data
            except Exception as e:
                logger.error(f"PaperSummarizerAgent: failed on paper_id={paper.id}: {e}")

            if progress_callback:
                progress_callback(i + 1, len(papers))

        return results

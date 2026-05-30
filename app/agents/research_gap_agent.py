"""ResearchGapAgent: Identifies underexplored research directions."""

from __future__ import annotations
import logging
from typing import Dict, List

from app.database import get_session, get_papers_with_summaries
from app.openrouter_client import call_openrouter_json, call_openrouter, is_api_key_configured
from app.prompts.research_gap import build_gap_prompt, build_deep_analysis_prompt

logger = logging.getLogger(__name__)


class ResearchGapAgent:
    """
    Finds research gaps and suggests new publishable directions.

    Input:  list of paper summaries
    Output: gap analysis dict
    """

    def run(self, limit: int = 80) -> Dict:
        if not is_api_key_configured():
            logger.warning("ResearchGapAgent: No API key.")
            return {}

        session = get_session()
        try:
            papers = get_papers_with_summaries(session, limit=limit)
        finally:
            session.close()

        if not papers:
            return {}

        summaries_text = self._build_text(papers)
        messages = build_gap_prompt(summaries_text)
        result = call_openrouter_json(messages, temperature=0.4, max_tokens=2500)
        logger.info(f"ResearchGapAgent: found {len(result.get('underexplored_areas', []))} gaps")
        return result

    def deep_analyze_paper(self, paper: Dict) -> str:
        """Generate deep technical analysis for a single paper."""
        if not is_api_key_configured():
            return "API key not configured."

        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        summary_data = {
            k: paper.get(k, "")
            for k in ["one_line_summary", "method", "main_contribution", "limitations"]
        }

        messages = build_deep_analysis_prompt(title, abstract, summary_data)
        result = call_openrouter(messages, temperature=0.3, max_tokens=3000)
        return result or "Analysis unavailable."

    def generate_literature_review(self, paper: Dict) -> str:
        """Generate a literature review paragraph for a paper."""
        if not is_api_key_configured():
            return "API key not configured."

        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        contribution = paper.get("main_contribution", "")

        messages = [
            {"role": "system", "content": "You are an expert academic writer."},
            {"role": "user", "content": f"""Write a 2-3 paragraph literature review passage about this paper,
suitable for inclusion in a related work section of another paper.

Title: {title}
Abstract: {abstract}
Main contribution: {contribution}

Write in academic style, citing the paper as (Author et al., Year). Use [Author et al., Year] placeholder."""}
        ]
        return call_openrouter(messages, temperature=0.3, max_tokens=800) or "Unavailable."

    def generate_research_ideas(self, paper: Dict) -> str:
        """Generate new research ideas inspired by a paper."""
        if not is_api_key_configured():
            return "API key not configured."

        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        limitations = paper.get("limitations", "")
        future_work = paper.get("future_work", "")

        messages = [
            {"role": "system", "content": "You are a creative ML research scientist."},
            {"role": "user", "content": f"""Based on this paper, generate 5 novel research ideas that extend or build upon it.

Title: {title}
Abstract: {abstract}
Limitations: {limitations}
Future work suggested: {future_work}

For each idea:
1. Give it a catchy title
2. Describe the core idea
3. Explain what gap it fills
4. Suggest an approach
5. Rate novelty and feasibility (1-10)

Format as Markdown."""}
        ]
        return call_openrouter(messages, temperature=0.5, max_tokens=2000) or "Unavailable."

    def _build_text(self, papers: List[Dict]) -> str:
        parts = []
        for p in papers[:50]:
            title = p.get("title", "")
            summary = p.get("one_line_summary", "")
            problem = p.get("problem", "")
            method = p.get("method", "")[:200]
            area = p.get("research_area", "")
            limitations = p.get("limitations", "")[:200]
            parts.append(
                f"Paper: {title}\n"
                f"Area: {area} | Summary: {summary}\n"
                f"Problem: {problem}\n"
                f"Method: {method}\n"
                f"Limitations: {limitations}"
            )
        return "\n\n---\n\n".join(parts)

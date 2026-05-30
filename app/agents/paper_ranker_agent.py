"""PaperRankerAgent: Ranks papers by composite scores."""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

from app.database import get_session, get_papers_with_summaries

logger = logging.getLogger(__name__)


class PaperRankerAgent:
    """
    Ranks papers by novelty, impact, technical depth, and implementation potential.

    Input:  list of paper dicts
    Output: sorted list of paper dicts with rank scores
    """

    SCORE_WEIGHTS = {
        "novelty_score": 0.35,
        "impact_score": 0.30,
        "technical_depth_score": 0.20,
        "code_generation_potential": 0.10,
        "reproducibility_score": 0.05,
    }

    def composite_score(self, paper: Dict) -> float:
        total = 0.0
        for field, weight in self.SCORE_WEIGHTS.items():
            val = paper.get(field, 5)
            try:
                total += float(val) * weight
            except (TypeError, ValueError):
                total += 5.0 * weight
        return round(total, 2)

    def rank(
        self,
        papers: Optional[List[Dict]] = None,
        limit: int = 200,
        sort_by: str = "composite",
    ) -> List[Dict]:
        if papers is None:
            session = get_session()
            try:
                papers = get_papers_with_summaries(session, limit=limit)
            finally:
                session.close()

        if not papers:
            return []

        # Add composite score
        for p in papers:
            p["composite_score"] = self.composite_score(p)

        sort_field_map = {
            "composite": "composite_score",
            "novelty": "novelty_score",
            "impact": "impact_score",
            "technical_depth": "technical_depth_score",
            "implementation": "code_generation_potential",
            "reproducibility": "reproducibility_score",
        }
        field = sort_field_map.get(sort_by, "composite_score")
        ranked = sorted(papers, key=lambda p: p.get(field, 0), reverse=True)

        # Add rank number
        for i, p in enumerate(ranked):
            p["rank"] = i + 1

        return ranked

    def top_n(self, n: int = 10, sort_by: str = "composite") -> List[Dict]:
        return self.rank(limit=500, sort_by=sort_by)[:n]

    def get_summary_stats(self, papers: List[Dict]) -> Dict:
        if not papers:
            return {}
        scores = {
            "novelty": [p.get("novelty_score", 5) for p in papers],
            "impact": [p.get("impact_score", 5) for p in papers],
            "technical_depth": [p.get("technical_depth_score", 5) for p in papers],
            "implementation": [p.get("code_generation_potential", 5) for p in papers],
            "reproducibility": [p.get("reproducibility_score", 5) for p in papers],
        }
        stats = {}
        for k, vals in scores.items():
            vals_f = [float(v) for v in vals if v is not None]
            if vals_f:
                stats[f"avg_{k}"] = round(sum(vals_f) / len(vals_f), 2)
                stats[f"max_{k}"] = max(vals_f)
                stats[f"min_{k}"] = min(vals_f)
        return stats

"""PaperCollectorAgent: Fetches papers from arXiv, deduplicates, saves to DB."""

from __future__ import annotations
import logging
import os
from typing import List, Optional, Dict

from app.arxiv_client import fetch_arxiv_papers, DEFAULT_CATEGORIES
from app.database import get_session, upsert_paper, create_all_tables

logger = logging.getLogger(__name__)


class PaperCollectorAgent:
    """
    Fetches papers from arXiv and stores them in the database.

    Input:  categories list, max_results count
    Output: list of saved paper dicts (with DB ids)
    """

    def __init__(
        self,
        categories: Optional[List[str]] = None,
        max_results: int = 50,
    ):
        raw = os.getenv("FETCH_CATEGORIES", "")
        if raw:
            self.categories = [c.strip() for c in raw.split(",") if c.strip()]
        else:
            self.categories = categories or DEFAULT_CATEGORIES

        self.max_results = int(os.getenv("ARXIV_MAX_RESULTS", str(max_results)))

    def run(self) -> List[Dict]:
        """Fetch and save papers. Returns list of saved paper metadata dicts."""
        logger.info(f"PaperCollectorAgent: fetching {self.max_results} papers from {self.categories}")
        create_all_tables()

        papers = fetch_arxiv_papers(
            categories=self.categories,
            max_results=self.max_results,
        )

        if not papers:
            logger.warning("PaperCollectorAgent: no papers fetched.")
            return []

        session = get_session()
        saved = []
        new_count = 0
        try:
            for meta in papers:
                try:
                    paper = upsert_paper(session, meta)
                    if paper.id and paper.arxiv_id == meta["arxiv_id"]:
                        new_count += 1 if paper.created_at else 0
                    meta["db_id"] = paper.id
                    saved.append(meta)
                except Exception as e:
                    logger.warning(f"Failed to save paper {meta.get('arxiv_id')}: {e}")
                    continue
            session.commit()
            logger.info(f"PaperCollectorAgent: saved {len(saved)} papers (new: {new_count})")
        except Exception as e:
            session.rollback()
            logger.error(f"PaperCollectorAgent: DB error: {e}")
        finally:
            session.close()

        return saved

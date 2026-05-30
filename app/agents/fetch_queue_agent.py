"""
FetchQueueAgent — Batch arXiv fetching with deduplication, queue, and rate limiting.

Environment config:
  ARXIV_DAILY_FETCH_LIMIT   = 200
  ARXIV_BATCH_SIZE          = 50
  ARXIV_MAX_PAGES           = 10
  ARXIV_REQUEST_DELAY_SECS  = 3
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, date
from typing import Dict, List, Optional

import feedparser
import requests
from sqlalchemy.orm import Session

from app.database import (
    Paper, FetchQueue, get_session,
    enqueue_arxiv_id, get_queue_stats,
)

logger = logging.getLogger(__name__)

DAILY_LIMIT   = int(os.getenv("ARXIV_DAILY_FETCH_LIMIT",  "200"))
BATCH_SIZE    = int(os.getenv("ARXIV_BATCH_SIZE",          "50"))
MAX_PAGES     = int(os.getenv("ARXIV_MAX_PAGES",           "10"))
DELAY_SECS    = float(os.getenv("ARXIV_REQUEST_DELAY_SECS", "3"))

ARXIV_BASE_CATEGORIES = [
    "cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.NE",
    "cs.CR", "cs.DB", "cs.SE", "cs.HC", "cs.RO",
]

ARXIV_API = "https://export.arxiv.org/api/query"


def _fetch_arxiv_page(category: str, start: int, max_results: int) -> List[Dict]:
    """Fetch one page from the arXiv Atom API."""
    params = {
        "search_query": f"cat:{category}",
        "start": start,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        resp = requests.get(ARXIV_API, params=params, timeout=30)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        entries = []
        for e in feed.entries:
            arxiv_id = e.get("id", "").split("/abs/")[-1].strip()
            entries.append({
                "arxiv_id":    arxiv_id,
                "title":       e.get("title", "").replace("\n", " ").strip(),
                "abstract":    e.get("summary", "").replace("\n", " ").strip(),
                "authors":     ", ".join(a.get("name", "") for a in e.get("authors", [])),
                "category":    e.get("arxiv_primary_category", {}).get("term", category),
                "published":   e.get("published", "")[:10],
                "arxiv_url":   e.get("link", ""),
                "pdf_url":     next(
                    (l.get("href", "") for l in e.get("links", []) if l.get("type") == "application/pdf"),
                    "",
                ),
            })
        return entries
    except Exception as exc:
        logger.error("arXiv fetch error (cat=%s start=%d): %s", category, start, exc)
        return []


def _paper_exists(session: Session, arxiv_id: str) -> bool:
    return session.query(Paper).filter_by(arxiv_id=arxiv_id).first() is not None


def _queue_entry_exists(session: Session, arxiv_id: str) -> bool:
    return session.query(FetchQueue).filter_by(arxiv_id=arxiv_id).first() is not None


class FetchQueueAgent:
    """
    Fetches arXiv papers in batches, deduplicates, and queues new ones.
    Separate from PaperCollectorAgent to support large-scale fetching.
    """

    def run(
        self,
        categories: Optional[List[str]] = None,
        limit: int = DAILY_LIMIT,
        enqueue_only: bool = False,
    ) -> Dict:
        """
        Fetch papers from arXiv and either store them directly or queue them.

        Args:
            categories:   arXiv categories to fetch from. Defaults to ARXIV_BASE_CATEGORIES.
            limit:        Max new papers to fetch (deduplication-aware).
            enqueue_only: If True, only populate the fetch queue; don't insert Papers.
        """
        session = get_session()
        try:
            return self._run(session, categories or ARXIV_BASE_CATEGORIES, limit, enqueue_only)
        finally:
            session.close()

    def _run(self, session: Session, categories, limit, enqueue_only) -> Dict:
        fetched_total   = 0
        skipped_dup     = 0
        queued_new      = 0
        papers_inserted = 0

        per_cat = max(1, limit // len(categories))

        for category in categories:
            if fetched_total >= limit:
                break

            page = 0
            cat_count = 0

            while cat_count < per_cat and page < MAX_PAGES:
                start = page * BATCH_SIZE
                entries = _fetch_arxiv_page(category, start, BATCH_SIZE)
                if not entries:
                    break

                for entry in entries:
                    if fetched_total >= limit or cat_count >= per_cat:
                        break

                    arxiv_id = entry["arxiv_id"]
                    fetched_total += 1

                    if _paper_exists(session, arxiv_id):
                        skipped_dup += 1
                        # Mark in queue as skipped if queued
                        q = session.query(FetchQueue).filter_by(arxiv_id=arxiv_id).first()
                        if q and q.status == "queued":
                            q.status = "skipped_duplicate"
                        continue

                    if enqueue_only:
                        if not _queue_entry_exists(session, arxiv_id):
                            enqueue_arxiv_id(session, arxiv_id, category)
                            queued_new += 1
                    else:
                        # Insert directly into papers table
                        paper = Paper(
                            arxiv_id=entry["arxiv_id"],
                            title=entry["title"],
                            abstract=entry["abstract"],
                            authors=entry["authors"],
                            primary_category=entry["category"],
                            categories=json.dumps([entry["category"]]),
                            published_date=self._parse_date(entry["published"]),
                            arxiv_url=entry["arxiv_url"],
                            pdf_url=entry["pdf_url"],
                        )
                        session.add(paper)
                        session.flush()

                        # Mark queue entry as fetched
                        q = session.query(FetchQueue).filter_by(arxiv_id=arxiv_id).first()
                        if q:
                            q.status = "fetched"
                        else:
                            row = enqueue_arxiv_id(session, arxiv_id, category)
                            row.status = "fetched"

                        papers_inserted += 1
                        cat_count += 1

                session.commit()
                page += 1
                if len(entries) < BATCH_SIZE:
                    break  # No more results
                time.sleep(DELAY_SECS)

        return {
            "fetched_total":   fetched_total,
            "papers_inserted": papers_inserted,
            "skipped_dup":     skipped_dup,
            "queued_new":      queued_new,
            "queue_stats":     get_queue_stats(session),
            "message":         (
                f"Fetched {fetched_total} candidates. "
                f"Inserted {papers_inserted} new papers. "
                f"Skipped {skipped_dup} duplicates."
            ),
        }

    @staticmethod
    def _parse_date(s: str):
        try:
            return datetime.strptime(s, "%Y-%m-%d").date()
        except Exception:
            return date.today()

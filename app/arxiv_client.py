"""arXiv API client using the Atom feed (feedparser)."""

from __future__ import annotations
import logging
import time
import urllib.parse
from typing import List, Dict, Optional

import feedparser
import requests

logger = logging.getLogger(__name__)

ARXIV_API_BASE = "http://export.arxiv.org/api/query"

DEFAULT_CATEGORIES = [
    "cs.CL", "cs.AI", "cs.LG", "cs.CV", "cs.RO",
    "cs.NE", "cs.IR", "cs.MA", "cs.HC", "cs.MM", "cs.SD",
]


def _build_search_query(categories: List[str]) -> str:
    parts = [f"cat:{c}" for c in categories]
    return " OR ".join(parts)


def fetch_arxiv_papers(
    categories: Optional[List[str]] = None,
    max_results: int = 50,
    sort_by: str = "submittedDate",
    sort_order: str = "descending",
    start: int = 0,
) -> List[Dict]:
    """
    Fetch papers from arXiv.

    Returns list of paper metadata dicts.
    """
    cats = categories or DEFAULT_CATEGORIES
    query = _build_search_query(cats)

    params = {
        "search_query": query,
        "start": start,
        "max_results": max_results,
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    url = ARXIV_API_BASE + "?" + urllib.parse.urlencode(params)
    logger.info(f"Fetching arXiv papers: {url}")

    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            break
        except Exception as e:
            logger.warning(f"arXiv fetch attempt {attempt+1} failed: {e}")
            if attempt < 2:
                time.sleep(5)
            else:
                logger.error("All arXiv fetch attempts failed.")
                return []

    feed = feedparser.parse(resp.text)
    papers = []
    for entry in feed.entries:
        try:
            paper = _parse_entry(entry)
            papers.append(paper)
        except Exception as e:
            logger.warning(f"Failed to parse entry: {e}")
            continue

    logger.info(f"Fetched {len(papers)} papers from arXiv.")
    return papers


def _parse_entry(entry) -> Dict:
    arxiv_id = entry.id.split("/abs/")[-1].strip()
    # Remove version suffix for dedup
    arxiv_id_clean = arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id

    authors = []
    for author in getattr(entry, "authors", []):
        name = getattr(author, "name", "")
        if name:
            authors.append(name)

    categories = []
    primary_category = ""
    for tag in getattr(entry, "tags", []):
        term = tag.get("term", "")
        if term:
            categories.append(term)
    if categories:
        primary_category = categories[0]

    # Prefer arxiv_primary_category if available
    pc = getattr(entry, "arxiv_primary_category", None)
    if pc and isinstance(pc, dict):
        primary_category = pc.get("term", primary_category)
    elif pc and hasattr(pc, "term"):
        primary_category = pc.term

    pdf_url = ""
    arxiv_url = ""
    for link in getattr(entry, "links", []):
        rel = getattr(link, "rel", "")
        href = getattr(link, "href", "")
        if link.get("type") == "application/pdf" or (hasattr(link, "type") and link.type == "application/pdf"):
            pdf_url = href
        if "abs" in href:
            arxiv_url = href

    if not pdf_url:
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    if not arxiv_url:
        arxiv_url = f"https://arxiv.org/abs/{arxiv_id_clean}"

    published = getattr(entry, "published", "")
    updated = getattr(entry, "updated", "")
    # Normalize to YYYY-MM-DD
    if published:
        published = published[:10]
    if updated:
        updated = updated[:10]

    abstract = getattr(entry, "summary", "").replace("\n", " ").strip()
    title = getattr(entry, "title", "").replace("\n", " ").strip()

    return {
        "arxiv_id": arxiv_id_clean,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "categories": list(set(categories)),
        "primary_category": primary_category,
        "published_date": published,
        "updated_date": updated,
        "pdf_url": pdf_url,
        "arxiv_url": arxiv_url,
    }


def fetch_paper_by_id(arxiv_id: str) -> Optional[Dict]:
    """Fetch a single paper by arXiv ID."""
    params = {"id_list": arxiv_id, "max_results": 1}
    url = ARXIV_API_BASE + "?" + urllib.parse.urlencode(params)
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        feed = feedparser.parse(resp.text)
        if feed.entries:
            return _parse_entry(feed.entries[0])
    except Exception as e:
        logger.error(f"fetch_paper_by_id({arxiv_id}) failed: {e}")
    return None

"""
EvidenceExtractorAgent — Trust Layer for ResearchRadar v2.

For each paper summary field, extracts supporting quotes from the abstract
(or PDF when available), assigns a confidence score, and stores evidence_spans.

Confidence heuristic:
  1.0 = direct verbatim match in abstract
  0.7 = paraphrased / near-match
  0.5 = inferred from surrounding text
  0.3 = llm-only inference, not grounded in text

Uncertainty labels:
  high_confidence   ≥ 0.75
  medium_confidence ≥ 0.50
  low_confidence    ≥ 0.30
  missing_evidence  < 0.30
  llm_inferred      (fallback when no abstract text)
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

import requests

from app.database import (
    Paper, Summary, EvidenceSpan,
    add_evidence_span, get_session,
)

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL     = "https://openrouter.ai/api/v1/chat/completions"
MODEL              = os.getenv("SUMMARIZER_MODEL", "mistralai/mistral-7b-instruct")


def _confidence_label(score: float) -> str:
    if score >= 0.75:
        return "high_confidence"
    if score >= 0.50:
        return "medium_confidence"
    if score >= 0.30:
        return "low_confidence"
    return "missing_evidence"


def _call_llm(prompt: str, max_tokens: int = 900) -> str:
    if not OPENROUTER_API_KEY:
        return ""
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return ""


def _extract_evidence_for_fields(
    abstract: str,
    summary: Summary,
) -> List[Dict]:
    """
    Ask the LLM to extract one supporting quote per summary field.
    Returns a list of dicts: {field, claim, quote, section, confidence}.
    """
    fields_to_check = {
        "problem":          getattr(summary, "problem", "") or "",
        "method":           getattr(summary, "method", "") or "",
        "contribution":     getattr(summary, "main_contribution", "") or "",
        "datasets":         getattr(summary, "datasets", "") or "",
        "results":          getattr(summary, "results", "") or "",
        "limitations":      getattr(summary, "limitations", "") or "",
        "future_work":      getattr(summary, "future_work", "") or "",
        "research_gap":     getattr(summary, "research_gap", "") or "",
    }
    # Build compact claims text
    claims_block = "\n".join(
        f"- {k}: {v[:200]}" for k, v in fields_to_check.items() if v
    )
    prompt = f"""You are an evidence extractor. Given an abstract and a set of claims about a research paper, find the best supporting quote from the abstract for each claim.

Abstract:
{abstract[:2000]}

Claims:
{claims_block}

For each claim, output a JSON object with these keys:
  field      – the claim field name
  claim      – the original claim (shortened to ≤80 chars)
  quote      – verbatim excerpt from the abstract that best supports the claim (≤200 chars). Empty string if no support found.
  confidence – float 0.0–1.0 (1.0=exact match, 0.7=paraphrase, 0.5=implied, 0.3=inferred, 0.0=not found)
  section    – "abstract" (always for now)

Output a JSON array only, no prose."""

    raw = _call_llm(prompt, max_tokens=1200)
    try:
        # Strip markdown fences if present
        raw = re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        return json.loads(raw)
    except Exception:
        # Fallback: create low-confidence stubs for each field
        return [
            {
                "field": k,
                "claim": v[:80],
                "quote": "",
                "confidence": 0.25,
                "section": "abstract",
            }
            for k, v in fields_to_check.items() if v
        ]


class EvidenceExtractorAgent:
    """Runs after PaperSummarizerAgent to attach evidence spans to every summary."""

    def run(self, paper_ids: Optional[List[int]] = None, max_papers: int = 20) -> Dict:
        """
        Extract evidence for papers that don't yet have evidence spans.

        Args:
            paper_ids: Specific papers to process. None → auto-select un-evidenced.
            max_papers: Upper bound when auto-selecting.
        """
        session = get_session()
        try:
            return self._run(session, paper_ids, max_papers)
        finally:
            session.close()

    def _run(self, session, paper_ids, max_papers) -> Dict:
        if paper_ids:
            papers_q = session.query(Paper).filter(Paper.id.in_(paper_ids))
        else:
            # Find papers with summaries but no evidence spans yet
            has_evidence = (
                session.query(EvidenceSpan.paper_id)
                .distinct()
                .subquery()
            )
            papers_q = (
                session.query(Paper)
                .join(Summary, Summary.paper_id == Paper.id)
                .filter(~Paper.id.in_(has_evidence))
                .limit(max_papers)
            )

        papers = papers_q.all()
        if not papers:
            return {"processed": 0, "message": "No papers need evidence extraction."}

        processed = 0
        for paper in papers:
            summary = session.query(Summary).filter_by(paper_id=paper.id).first()
            if not summary:
                continue
            abstract = paper.abstract or ""
            if not abstract:
                # No abstract — mark all fields as llm_inferred
                self._add_stubs(session, paper.id, summary, "llm_inferred", 0.2)
                continue

            evidence_items = _extract_evidence_for_fields(abstract, summary)
            for item in evidence_items:
                field      = item.get("field", "unknown")
                claim      = item.get("claim", "")[:500]
                quote      = item.get("quote", "")[:500]
                conf       = float(item.get("confidence", 0.3))
                sect       = item.get("section", "abstract")
                label      = _confidence_label(conf) if quote else "missing_evidence"

                add_evidence_span(
                    session=session,
                    paper_id=paper.id,
                    summary_field=field,
                    claim_text=claim,
                    evidence_text=quote,
                    confidence=conf,
                    uncertainty=label,
                    section=sect,
                )
            session.commit()
            processed += 1
            logger.info("Evidence extracted for paper %d (%s)", paper.id, paper.arxiv_id)

        return {
            "processed": processed,
            "message": f"Evidence extracted for {processed} paper(s).",
        }

    def _add_stubs(self, session, paper_id, summary, label, conf):
        for field in ("problem", "method", "contribution", "datasets", "results",
                      "limitations", "future_work", "research_gap"):
            val = getattr(summary, field, "") or getattr(summary, "main_contribution", "") or ""
            if not val:
                continue
            add_evidence_span(
                session=session,
                paper_id=paper_id,
                summary_field=field,
                claim_text=val[:200],
                evidence_text="",
                confidence=conf,
                uncertainty=label,
                section="abstract",
            )
        session.commit()

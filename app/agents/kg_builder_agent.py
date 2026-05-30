"""
KnowledgeGraphBuilderAgent

Extracts entities and relationships from a summarized paper analysis
using an LLM, then ingests the results into the ResearchMemoryEngine.
"""

from __future__ import annotations
import json
import logging
from typing import Dict, List, Optional

from app.database import get_session, Paper, Summary, paper_to_dict, summary_to_dict
from app.openrouter_client import call_openrouter_json, is_api_key_configured
from app.prompts.kg_extraction import build_kg_extraction_prompt
from app.memory.research_memory_engine import ResearchMemoryEngine

logger = logging.getLogger(__name__)

_engine = ResearchMemoryEngine()


class KnowledgeGraphBuilderAgent:
    """
    Input:  paper_id (int) — must already have a summary in the DB
    Output: ingestion summary dict  {entities, edges, memories}

    Workflow:
      1. Load paper + summary from DB
      2. Retrieve memory context (similar prior papers, trending topics, gaps)
      3. Call LLM to extract structured entities + relationships
      4. Ingest results into ResearchMemoryEngine (handles all DB writes)
    """

    def __init__(self, skip_if_already_ingested: bool = True):
        self.skip_if_already_ingested = skip_if_already_ingested

    def extract_for_paper(
        self,
        paper_id: int,
        full_text_excerpt: str = "",
    ) -> Dict:
        """Run KG extraction for a single paper. Returns ingestion stats."""
        if not is_api_key_configured():
            # Fall back to rule-based extraction (no LLM)
            return self._fallback_extract(paper_id)

        session = get_session()
        try:
            paper = session.query(Paper).filter_by(id=paper_id).first()
            summary = session.query(Summary).filter_by(paper_id=paper_id).first()
            if not paper:
                logger.warning(f"KGBuilderAgent: paper_id={paper_id} not found.")
                return {}
            if not summary:
                logger.warning(f"KGBuilderAgent: no summary for paper_id={paper_id}; using rule-based.")
                session.close()
                return self._fallback_extract(paper_id)

            paper_dict = paper_to_dict(paper)
            analysis_dict = summary_to_dict(summary)
        finally:
            session.close()

        # Build memory context
        memory_context = _engine.build_context_for_agent(
            agent_name="KnowledgeGraphBuilderAgent",
            task="extract_entities_and_relationships",
            paper_id=paper_id,
        )

        # Call LLM
        messages = build_kg_extraction_prompt(
            paper=paper_dict,
            analysis=analysis_dict,
            full_text_excerpt=full_text_excerpt,
            memory_context=memory_context,
        )
        kg_output = call_openrouter_json(
            messages,
            temperature=0.1,
            max_tokens=3000,
            fallback={"entities": [], "relationships": []},
        )

        if not kg_output.get("entities"):
            logger.info(f"KGBuilderAgent: LLM returned no entities for paper_id={paper_id}; falling back.")
            kg_output = {}

        # Merge LLM output with plain analysis dict for the engine
        merged = {**analysis_dict, **kg_output}
        result = _engine.ingest_paper_analysis(paper_id, merged)

        # Compute novel metrics and persist them as agent memory
        metrics = _engine.compute_novel_metrics(paper_id)
        if metrics:
            session2 = get_session()
            try:
                from app.database import upsert_agent_memory
                upsert_agent_memory(
                    session2,
                    agent_name="KnowledgeGraphBuilderAgent",
                    memory_key=f"novel_metrics_{paper_id}",
                    value=metrics,
                    paper_ids=[paper_id],
                )
                session2.commit()
            except Exception as e:
                session2.rollback()
                logger.warning(f"KGBuilderAgent: failed to save novel metrics: {e}")
            finally:
                session2.close()

        result["novel_metrics"] = metrics
        logger.info(f"KGBuilderAgent: paper_id={paper_id} → {result}")
        return result

    def _fallback_extract(self, paper_id: int) -> Dict:
        """Rule-based extraction from existing summary fields (no LLM)."""
        session = get_session()
        try:
            paper = session.query(Paper).filter_by(id=paper_id).first()
            summary = session.query(Summary).filter_by(paper_id=paper_id).first()
            if not paper:
                return {}
            paper_dict = paper_to_dict(paper)
            analysis_dict = summary_to_dict(summary) if summary else {}
        finally:
            session.close()

        return _engine.ingest_paper_analysis(paper_id, {**paper_dict, **analysis_dict})

    def run(
        self,
        paper_ids: Optional[List[int]] = None,
        limit: int = 50,
        progress_callback=None,
    ) -> Dict[int, Dict]:
        """
        Run KG extraction for multiple papers.
        If paper_ids is None, processes all summarized papers that haven't been
        ingested into the KG yet (based on PaperEntityMention absence).
        """
        session = get_session()
        try:
            if paper_ids:
                papers = session.query(Paper).filter(Paper.id.in_(paper_ids)).all()
                target_ids = [p.id for p in papers]
            else:
                # Papers that have a summary but no KG entity mentions
                from app.database import PaperEntityMention
                summarized_ids = {s.paper_id for s in session.query(Summary).all()}
                ingested_ids = {m.paper_id for m in session.query(PaperEntityMention).all()}
                target_ids = list(summarized_ids - ingested_ids)[:limit]
        finally:
            session.close()

        if not target_ids:
            logger.info("KGBuilderAgent: all summarized papers already have KG entities.")
            return {}

        results = {}
        for i, pid in enumerate(target_ids):
            try:
                result = self.extract_for_paper(pid)
                results[pid] = result
            except Exception as e:
                logger.error(f"KGBuilderAgent: failed on paper_id={pid}: {e}")

            if progress_callback:
                progress_callback(i + 1, len(target_ids))

        return results

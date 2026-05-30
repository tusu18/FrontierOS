"""
ResearchGapMemoryAgent

Analyses the knowledge graph to find, rank, and evolve research gaps:
  - Repeated limitations / future-work items that are unresolved
  - Topics with high velocity but still many open questions
  - Cross-category saturation indicators
  - Opportunity scores combining gap frequency + implementation potential

Persists discovered gaps as ResearchGap entities in the KG so they
accumulate and improve over time.
"""

from __future__ import annotations
import json
import logging
from collections import Counter
from datetime import date
from typing import Dict, List, Optional

from app.database import (
    get_session, KGEntity, KGEdge, PaperEntityMention, TrendMemory,
    upsert_kg_entity, upsert_kg_edge, upsert_agent_memory,
    Paper, Summary,
)
from app.memory.research_memory_engine import ResearchMemoryEngine
from app.openrouter_client import call_openrouter_json, is_api_key_configured

logger = logging.getLogger(__name__)

_engine = ResearchMemoryEngine()


class ResearchGapMemoryAgent:
    """
    Maintains the ResearchGap layer of the knowledge graph.

    run() → analyses all limitations + future-work entities,
    promotes high-frequency clusters to ResearchGap nodes,
    returns a ranked list of opportunities.
    """

    # Minimum times a limitation must appear to be promoted to a ResearchGap
    PROMOTION_THRESHOLD = 2

    def run(self, area: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """
        Scan limitations and future-work entities, promote repeated ones to
        ResearchGap nodes, and return a ranked opportunity list.
        """
        session = get_session()
        try:
            # Gather all Limitation and FutureWork entities
            lim_fw = (
                session.query(KGEntity)
                .filter(KGEntity.entity_type.in_(["Limitation", "FutureWork"]))
                .order_by(KGEntity.frequency_count.desc())
                .limit(200)
                .all()
            )

            if not lim_fw:
                logger.info("ResearchGapMemoryAgent: no limitations/future-work entities found.")
                return []

            promoted: List[Dict] = []

            for ent in lim_fw:
                if ent.frequency_count < self.PROMOTION_THRESHOLD:
                    continue

                # Check if a ResearchGap node already exists for this topic
                gap_norm = f"gap: {ent.normalized_name}"
                existing_gap = (
                    session.query(KGEntity)
                    .filter_by(entity_type="ResearchGap", normalized_name=gap_norm[:256])
                    .first()
                )

                # Count papers that *address* this limitation via newer papers
                addressing_count = self._count_addressing_papers(session, ent)
                resolving_ratio = addressing_count / max(1, ent.frequency_count)

                # Gap opportunity score: high freq + low resolution = high score
                gap_score = ent.frequency_count * (1.0 - min(1.0, resolving_ratio * 2))

                # Compute implementation potential from entity neighbourhood
                impl_potential = self._estimate_impl_potential(session, ent)

                if existing_gap:
                    # Update existing gap with fresh scores
                    existing_gap.frequency_count = ent.frequency_count
                    meta = json.loads(existing_gap.metadata_json or "{}")
                    meta.update({
                        "gap_score": round(gap_score, 2),
                        "resolving_ratio": round(resolving_ratio, 3),
                        "implementation_potential": round(impl_potential, 2),
                        "last_updated": date.today().isoformat(),
                    })
                    existing_gap.metadata_json = json.dumps(meta)
                    gap_id = existing_gap.id
                else:
                    # Promote to ResearchGap
                    gap_entity = upsert_kg_entity(
                        session,
                        entity_type="ResearchGap",
                        name=f"Gap: {ent.name}",
                        description=f"Repeated unresolved limitation: '{ent.name}'",
                        confidence=0.75,
                        metadata={
                            "gap_score": round(gap_score, 2),
                            "resolving_ratio": round(resolving_ratio, 3),
                            "implementation_potential": round(impl_potential, 2),
                            "source_entity_type": ent.entity_type,
                            "created": date.today().isoformat(),
                        },
                    )
                    gap_id = gap_entity.id
                    # Link gap ← EMERGES_FROM → original limitation
                    upsert_kg_edge(
                        session,
                        source_id=gap_id,
                        rel_type="EMERGES_FROM",
                        target_id=ent.id,
                        evidence=f"Promoted from {ent.entity_type} '{ent.name}' (freq={ent.frequency_count})",
                        confidence=0.75,
                    )

                promoted.append({
                    "gap_id": gap_id,
                    "name": f"Gap: {ent.name}",
                    "source_type": ent.entity_type,
                    "frequency": ent.frequency_count,
                    "addressing_papers": addressing_count,
                    "gap_score": round(gap_score, 2),
                    "implementation_potential": round(impl_potential, 2),
                    "first_seen": ent.first_seen_date,
                    "last_seen": ent.last_seen_date,
                })

            session.commit()

            # Persist top gaps as agent memory
            promoted.sort(key=lambda x: x["gap_score"], reverse=True)
            upsert_result = []
            for g in promoted[:limit]:
                upsert_result.append(g)

            session2 = get_session()
            try:
                upsert_agent_memory(
                    session2,
                    agent_name="ResearchGapMemoryAgent",
                    memory_key="top_research_gaps",
                    value=upsert_result,
                    confidence=0.8,
                )
                session2.commit()
            finally:
                session2.close()

            logger.info(f"ResearchGapMemoryAgent: promoted {len(promoted)} gaps.")
            return upsert_result

        except Exception as exc:
            session.rollback()
            logger.error(f"ResearchGapMemoryAgent.run: {exc}")
            return []
        finally:
            session.close()

    def get_top_gaps(self, limit: int = 20) -> List[Dict]:
        """Return the most recent top gaps from agent memory."""
        from app.database import AgentMemory
        session = get_session()
        try:
            row = (
                session.query(AgentMemory)
                .filter_by(agent_name="ResearchGapMemoryAgent", memory_key="top_research_gaps")
                .first()
            )
            if row:
                return json.loads(row.memory_value_json or "[]")[:limit]
        except Exception:
            pass
        finally:
            session.close()
        # Fall back to live query
        return _engine.find_research_gaps(limit=limit)

    def _count_addressing_papers(self, session, limitation_entity: KGEntity) -> int:
        """
        Count newer papers that mention this limitation with an IMPROVES_ON
        or EXTENDS relationship — interpreted as 'addressing' the gap.
        """
        norm = limitation_entity.normalized_name
        related_method_edges = (
            session.query(KGEdge)
            .filter(
                KGEdge.relationship_type.in_(["IMPROVES_ON", "EXTENDS"]),
                KGEdge.target_entity_id == limitation_entity.id,
            )
            .count()
        )
        return related_method_edges

    def _estimate_impl_potential(self, session, entity: KGEntity) -> float:
        """
        Estimate implementation potential based on neighbouring entity types.
        High if neighbourhood has code repos, datasets, and baselines.
        """
        mentions = (
            session.query(PaperEntityMention)
            .filter_by(entity_id=entity.id)
            .limit(20)
            .all()
        )
        paper_ids = [m.paper_id for m in mentions]
        if not paper_ids:
            return 0.3

        # Find all entity types from these papers
        neighbour_types = set()
        for pid in paper_ids:
            nbr_mentions = (
                session.query(PaperEntityMention)
                .filter_by(paper_id=pid)
                .limit(30)
                .all()
            )
            for nm in nbr_mentions:
                ent = session.query(KGEntity).filter_by(id=nm.entity_id).first()
                if ent:
                    neighbour_types.add(ent.entity_type)

        score = 0.0
        if "Dataset" in neighbour_types:
            score += 0.3
        if "CodeRepository" in neighbour_types or "HuggingFaceModel" in neighbour_types:
            score += 0.35
        if "Baseline" in neighbour_types:
            score += 0.2
        if "Benchmark" in neighbour_types:
            score += 0.15
        return min(1.0, score)

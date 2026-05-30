"""
ResearchMemoryEngine — the central shared memory layer.

Responsibilities:
  • Ingest structured paper analysis → extract entities + relationships → upsert into KG
  • Provide graph neighbourhood queries, similarity search, gap discovery
  • Compute novel graph-based metrics (velocity, saturation, gap score, etc.)
  • Build rich context dicts for any agent before it runs

All storage is SQLite via the existing SQLAlchemy session factory — no extra
infrastructure required.
"""

from __future__ import annotations

import json
import logging
import math
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from app.database import (
    get_session,
    upsert_kg_entity,
    upsert_kg_edge,
    add_paper_entity_mention,
    add_semantic_memory,
    log_memory_event,
    upsert_trend_memory,
    upsert_agent_memory,
    KGEntity,
    KGEdge,
    PaperEntityMention,
    SemanticMemory,
    TrendMemory,
    AgentMemory,
    Paper,
    Summary,
    EvidenceSpan,
    Keyword,
    _normalize,
)

logger = logging.getLogger(__name__)

# Canonical entity types supported by the engine
ENTITY_TYPES = [
    "Paper", "Author", "Institution", "ResearchArea", "Topic", "Task",
    "Method", "ModelArchitecture", "Dataset", "Benchmark", "Metric",
    "Baseline", "Claim", "Result", "Limitation", "FutureWork",
    "CodeRepository", "ProjectPage", "HuggingFaceModel", "Tool",
    "Library", "Conference", "ResearchGap", "GeneratedProjectIdea",
]

# Relationship types
RELATIONSHIP_TYPES = [
    "AUTHORED_BY", "AFFILIATED_WITH", "BELONGS_TO", "ADDRESSES", "USES",
    "INTRODUCES", "USES_MODEL", "EVALUATES_ON", "REPORTS_METRIC",
    "COMPARES_AGAINST", "MAKES_CLAIM", "SUPPORTED_BY", "HAS_LIMITATION",
    "SUGGESTS_FUTURE_WORK", "HAS_CODE", "IMPLEMENTS", "IMPROVES_ON",
    "RELATED_TO", "USED_FOR", "MEASURES", "EMERGES_FROM", "BUILDS_ON",
    "TARGETS", "SIMILAR_TO", "EXTENDS",
]


class ResearchMemoryEngine:
    """
    Singleton-friendly engine that manages the research knowledge graph and
    semantic memory layer on top of the SQLite database.
    """

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest_paper_analysis(self, paper_id: int, analysis_json: dict) -> dict:
        """
        Main ingestion entry point.

        analysis_json should contain either:
          • LLM KG-builder output with 'entities' and 'relationships' lists, OR
          • A plain summarizer output dict (will be auto-converted to entities)

        Returns a summary of what was ingested.
        """
        session = get_session()
        ingested = {"entities": 0, "edges": 0, "memories": 0}
        try:
            # --- Get paper row ---
            paper = session.query(Paper).filter_by(id=paper_id).first()
            if not paper:
                logger.warning(f"ResearchMemoryEngine: paper_id={paper_id} not found.")
                return ingested

            today = date.today().isoformat()

            # --- Ingest entities ---
            entity_name_to_id: Dict[str, int] = {}
            raw_entities = analysis_json.get("entities", [])

            # Auto-derive entities from a plain summarizer dict when no explicit list
            if not raw_entities:
                raw_entities = self._derive_entities_from_summary(paper, analysis_json)

            for ent in raw_entities:
                etype = ent.get("type", "Topic")
                ename = (ent.get("name") or "").strip()
                if not ename or etype not in ENTITY_TYPES:
                    continue
                entity = upsert_kg_entity(
                    session,
                    entity_type=etype,
                    name=ename,
                    description=ent.get("description", ""),
                    source_paper_id=paper_id,
                    confidence=float(ent.get("confidence_score", 0.7)),
                    metadata=ent.get("metadata", {}),
                )
                entity_name_to_id[_normalize(ename)] = entity.id
                add_paper_entity_mention(
                    session,
                    paper_id=paper_id,
                    entity_id=entity.id,
                    mention_text=ent.get("evidence_text", "")[:500],
                    section=ent.get("section", ""),
                    confidence=float(ent.get("confidence_score", 0.7)),
                )
                ingested["entities"] += 1

            # --- Ingest relationships ---
            for rel in analysis_json.get("relationships", []):
                src_name = _normalize(rel.get("source_entity_name", ""))
                tgt_name = _normalize(rel.get("target_entity_name", ""))
                rel_type = rel.get("relationship_type", "")
                if rel_type not in RELATIONSHIP_TYPES:
                    continue
                src_id = entity_name_to_id.get(src_name)
                tgt_id = entity_name_to_id.get(tgt_name)
                if not src_id or not tgt_id:
                    continue
                upsert_kg_edge(
                    session,
                    source_id=src_id,
                    rel_type=rel_type,
                    target_id=tgt_id,
                    paper_id=paper_id,
                    evidence=rel.get("evidence_text", ""),
                    confidence=float(rel.get("confidence_score", 0.7)),
                )
                ingested["edges"] += 1

            # --- Create semantic memory chunks ---
            chunks = self._build_memory_chunks(paper, analysis_json)
            for chunk_type, text in chunks:
                if text.strip():
                    add_semantic_memory(
                        session,
                        memory_type=chunk_type,
                        source_id=paper_id,
                        source_table="papers",
                        text=text,
                        metadata={"paper_id": paper_id, "date": today},
                    )
                    ingested["memories"] += 1

            # --- Update trend memory for ingested entities ---
            entity_counts = self._get_entity_frequencies(session)
            for norm_name, eid in entity_name_to_id.items():
                entity_row = session.query(KGEntity).filter_by(id=eid).first()
                if entity_row:
                    freq = entity_counts.get(entity_row.entity_type, {}).get(norm_name, 1)
                    total_of_type = sum(entity_counts.get(entity_row.entity_type, {}).values()) or 1
                    saturation = min(1.0, freq / max(1, total_of_type / 5))
                    velocity = self._compute_velocity(session, eid, window_days=7)
                    upsert_trend_memory(
                        session,
                        entity_id=eid,
                        entity_type=entity_row.entity_type,
                        velocity=velocity,
                        saturation=saturation,
                        novelty=max(0.0, 1.0 - saturation),
                    )

            # --- Log event ---
            log_memory_event(
                session,
                event_type="paper_ingested",
                description=f"Ingested paper_id={paper_id}: {ingested}",
                paper_id=paper_id,
                metadata=ingested,
            )

            session.commit()
            logger.info(f"ResearchMemoryEngine: ingested paper_id={paper_id} → {ingested}")
        except Exception as exc:
            session.rollback()
            logger.error(f"ResearchMemoryEngine.ingest_paper_analysis error: {exc}")
        finally:
            session.close()
        return ingested

    # ------------------------------------------------------------------
    # Entity Management
    # ------------------------------------------------------------------

    def upsert_entity(
        self,
        entity_type: str,
        name: str,
        description: str = "",
        metadata: Optional[Dict] = None,
    ) -> int:
        """Normalize and upsert a single entity. Returns the entity DB id."""
        session = get_session()
        try:
            entity = upsert_kg_entity(session, entity_type, name, description, metadata=metadata)
            session.commit()
            return entity.id
        finally:
            session.close()

    def create_edge(
        self,
        source_id: int,
        relation: str,
        target_id: int,
        paper_id: int,
        evidence: str = "",
        confidence: float = 0.7,
    ):
        """Create a graph edge."""
        session = get_session()
        try:
            upsert_kg_edge(session, source_id, relation, target_id, paper_id, evidence, confidence)
            session.commit()
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Graph Queries
    # ------------------------------------------------------------------

    def get_related_entities(
        self, entity_name: str, depth: int = 2, limit: int = 50
    ) -> List[Dict]:
        """BFS neighbourhood of an entity up to `depth` hops."""
        session = get_session()
        try:
            norm = _normalize(entity_name)
            start = session.query(KGEntity).filter_by(normalized_name=norm).first()
            if not start:
                # Try partial match
                start = session.query(KGEntity).filter(
                    KGEntity.normalized_name.like(f"%{norm}%")
                ).first()
            if not start:
                return []

            visited = {start.id}
            frontier = [start.id]
            results = []

            for _ in range(depth):
                next_frontier = []
                for eid in frontier:
                    out_edges = session.query(KGEdge).filter_by(source_entity_id=eid).limit(20).all()
                    in_edges = session.query(KGEdge).filter_by(target_entity_id=eid).limit(20).all()
                    for edge in out_edges + in_edges:
                        neighbor_id = (
                            edge.target_entity_id if edge.source_entity_id == eid
                            else edge.source_entity_id
                        )
                        if neighbor_id not in visited:
                            visited.add(neighbor_id)
                            next_frontier.append(neighbor_id)
                            neighbor = session.query(KGEntity).filter_by(id=neighbor_id).first()
                            if neighbor:
                                results.append({
                                    "id": neighbor.id,
                                    "type": neighbor.entity_type,
                                    "name": neighbor.name,
                                    "description": neighbor.description,
                                    "frequency": neighbor.frequency_count,
                                    "relationship": edge.relationship_type,
                                    "confidence": edge.confidence_score,
                                })
                frontier = next_frontier
                if not frontier or len(results) >= limit:
                    break

            return results[:limit]
        finally:
            session.close()

    def find_similar_papers(self, paper_id: int, limit: int = 10) -> List[Dict]:
        """
        Find similar papers by entity overlap (Jaccard similarity on shared KG entities).
        Falls back to keyword overlap from summaries.
        """
        session = get_session()
        try:
            my_entities = {
                m.entity_id
                for m in session.query(PaperEntityMention).filter_by(paper_id=paper_id).all()
            }
            if not my_entities:
                return []

            # Count shared entities with all other papers
            scores: Dict[int, int] = Counter()
            for eid in my_entities:
                other_mentions = (
                    session.query(PaperEntityMention)
                    .filter(
                        PaperEntityMention.entity_id == eid,
                        PaperEntityMention.paper_id != paper_id,
                    )
                    .all()
                )
                for m in other_mentions:
                    scores[m.paper_id] += 1

            if not scores:
                return []

            results = []
            for other_pid, shared in scores.most_common(limit):
                other_paper = session.query(Paper).filter_by(id=other_pid).first()
                if other_paper:
                    jaccard = shared / max(1, len(my_entities) + shared)
                    results.append({
                        "paper_id": other_pid,
                        "arxiv_id": other_paper.arxiv_id,
                        "title": other_paper.title,
                        "similarity_score": round(jaccard, 3),
                        "shared_entities": shared,
                    })
            return results
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Research Gap Discovery
    # ------------------------------------------------------------------

    def find_research_gaps(self, area: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """
        Find repeated unresolved limitations + future-work that have not been
        addressed by newer papers (i.e. low FutureWork entity resolution).
        """
        session = get_session()
        try:
            q = session.query(KGEntity).filter(
                KGEntity.entity_type.in_(["Limitation", "FutureWork", "ResearchGap"])
            )
            if area:
                q = q.filter(KGEntity.normalized_name.like(f"%{_normalize(area)}%"))

            entities = q.order_by(KGEntity.frequency_count.desc()).limit(limit * 2).all()

            gaps = []
            for ent in entities:
                # Score: higher freq + no outgoing EMERGES_FROM → better gap candidate
                emerging_edges = session.query(KGEdge).filter_by(
                    source_entity_id=ent.id, relationship_type="EMERGES_FROM"
                ).count()
                addressing_papers = (
                    session.query(PaperEntityMention)
                    .filter_by(entity_id=ent.id)
                    .count()
                )
                gap_score = ent.frequency_count / max(1, emerging_edges + 1)
                # implementation_potential: high when frequently mentioned but few
                # papers have emerged to address it (normalised 0–1)
                impl_potential = min(1.0, ent.frequency_count / max(1, addressing_papers + 1) / 10)
                gaps.append({
                    "id": ent.id,
                    "type": ent.entity_type,
                    "name": ent.name,
                    "description": ent.description,
                    "frequency": ent.frequency_count,
                    "papers_mentioning": addressing_papers,
                    "gap_score": round(gap_score, 2),
                    "implementation_potential": round(impl_potential, 3),
                    "first_seen": ent.first_seen_date,
                    "last_seen": ent.last_seen_date,
                })

            gaps.sort(key=lambda x: x["gap_score"], reverse=True)
            return gaps[:limit]
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Trend / Velocity Queries
    # ------------------------------------------------------------------

    def get_trending_entities(
        self,
        entity_type: Optional[str] = None,
        window_days: int = 7,
        limit: int = 20,
    ) -> List[Dict]:
        """Return entities with the highest velocity (rate of new paper mentions) over the window."""
        session = get_session()
        try:
            since = (date.today() - timedelta(days=window_days)).isoformat()
            q = session.query(TrendMemory).filter(TrendMemory.date >= since)
            if entity_type:
                q = q.filter(TrendMemory.entity_type == entity_type)

            rows = q.order_by(TrendMemory.velocity_score.desc()).limit(limit * 3).all()

            seen_ids: set = set()
            results = []
            for row in rows:
                if row.entity_id in seen_ids:
                    continue
                seen_ids.add(row.entity_id)
                entity = session.query(KGEntity).filter_by(id=row.entity_id).first()
                if entity:
                    results.append({
                        "entity_id": entity.id,
                        "type": entity.entity_type,
                        "name": entity.name,
                        "velocity": round(row.velocity_score, 3),
                        "saturation": round(row.saturation_score, 3),
                        "novelty": round(row.novelty_score, 3),
                        "total_mentions": entity.frequency_count,
                    })
                if len(results) >= limit:
                    break

            return results
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Semantic / Hybrid Memory Query
    # ------------------------------------------------------------------

    @staticmethod
    def _bm25_lite(query_words: List[str], text: str, avg_dl: float = 200.0) -> float:
        """Lightweight BM25-style score without external deps."""
        if not query_words or not text:
            return 0.0
        doc = text.lower()
        dl = max(len(doc.split()), 1)
        k1, b = 1.2, 0.75
        score = 0.0
        for w in query_words:
            tf = doc.count(w)
            if tf:
                idf = 1.0 + math.log(1 + 1.0 / (1 + tf))
                score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        return score

    def query_memory(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """
        Hybrid retrieval (keyword/hybrid-lite):
          - paper titles, summaries, keywords
          - semantic_memory chunks
          - KG entity names
          - evidence span text
        Optional embeddings re-rank when ENABLE_LOCAL_EMBEDDINGS=true.
        """
        session = get_session()
        try:
            stop = {"the", "a", "an", "of", "in", "is", "are", "for", "to", "and", "or",
                    "with", "that", "this", "it", "be", "as", "on", "at", "by", "from"}
            query_words = [w.lower() for w in query.split() if w.lower() not in stop and len(w) > 2]
            if not query_words:
                query_words = [w.lower() for w in query.split() if len(w) > 2]

            pool: List[tuple] = []

            # 1. Papers + summaries (title, abstract, one_line, keywords)
            papers = (
                session.query(Paper, Summary)
                .outerjoin(Summary, Summary.paper_id == Paper.id)
                .order_by(Paper.id.desc())
                .limit(300)
                .all()
            )
            kw_rows = session.query(Keyword.paper_id, Keyword.keyword).all()
            kw_by_paper: Dict[int, List[str]] = defaultdict(list)
            for pid, kw in kw_rows:
                kw_by_paper[pid].append(kw)

            for paper, summary in papers:
                kw = kw_by_paper.get(paper.id, [])
                if summary and summary.summary_json:
                    try:
                        sj = json.loads(summary.summary_json)
                        kw = kw + (sj.get("keywords") or [])
                    except json.JSONDecodeError:
                        pass
                blob = " ".join(filter(None, [
                    paper.title, paper.abstract,
                    summary.one_line_summary if summary else "",
                    summary.problem if summary else "",
                    summary.main_contribution if summary else "",
                    " ".join(kw) if isinstance(kw, list) else str(kw),
                ]))
                sc = self._bm25_lite(query_words, blob)
                if sc > 0:
                    pool.append((sc, {
                        "source": "paper",
                        "paper_id": paper.id,
                        "name": paper.title[:120],
                        "text": (summary.one_line_summary if summary else paper.abstract or "")[:400],
                        "relevance": sc,
                    }))

            # 2. Evidence spans
            for span in session.query(EvidenceSpan).limit(400).all():
                blob = " ".join(filter(None, [span.claim_text, span.evidence_text, span.summary_field]))
                sc = self._bm25_lite(query_words, blob)
                if sc > 0:
                    pool.append((sc * 0.9, {
                        "source": "evidence",
                        "paper_id": span.paper_id,
                        "name": span.summary_field,
                        "text": span.evidence_text[:400],
                        "relevance": sc,
                    }))

            # 3. Semantic memory
            sem_q = session.query(SemanticMemory)
            if memory_types:
                sem_q = sem_q.filter(SemanticMemory.memory_type.in_(memory_types))
            for mem in sem_q.limit(500).all():
                sc = self._bm25_lite(query_words, mem.text)
                if sc > 0:
                    pool.append((sc * 0.85, {
                        "source": "semantic_memory",
                        "memory_type": mem.memory_type,
                        "paper_id": mem.source_id,
                        "name": mem.memory_type,
                        "text": mem.text[:400],
                        "relevance": sc,
                    }))

            # 4. KG entities
            for word in query_words[:6]:
                for ent in session.query(KGEntity).filter(
                    KGEntity.normalized_name.like(f"%{word}%")
                ).limit(15).all():
                    sc = self._bm25_lite(query_words, f"{ent.name} {ent.description or ''}")
                    pool.append((sc + ent.frequency_count * 0.01, {
                        "source": "entity",
                        "entity_type": ent.entity_type,
                        "name": ent.name,
                        "text": ent.description or ent.name,
                        "relevance": sc,
                    }))

            pool.sort(key=lambda x: -x[0])
            seen = set()
            results = []
            for _, hit in pool:
                key = (hit.get("source"), hit.get("paper_id"), hit.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                results.append(hit)
                if len(results) >= limit:
                    break

            return results
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Agent Context Builder
    # ------------------------------------------------------------------

    def build_context_for_agent(
        self,
        agent_name: str,
        task: str,
        paper_id: Optional[int] = None,
    ) -> Dict:
        """
        Retrieve relevant shared memory before an agent runs.
        Returns a context dict the agent can use to enrich its output.
        """
        session = get_session()
        ctx: Dict[str, Any] = {
            "agent_name": agent_name,
            "task": task,
            "similar_papers": [],
            "related_entities": [],
            "trending_topics": [],
            "research_gaps": [],
            "prior_agent_memory": {},
        }
        try:
            # Similar papers
            if paper_id:
                ctx["similar_papers"] = self.find_similar_papers(paper_id, limit=5)

                # Entities from this paper
                mentions = (
                    session.query(PaperEntityMention)
                    .filter_by(paper_id=paper_id)
                    .limit(30)
                    .all()
                )
                entity_ids = [m.entity_id for m in mentions]
                for eid in entity_ids[:10]:
                    entity = session.query(KGEntity).filter_by(id=eid).first()
                    if entity:
                        ctx["related_entities"].append({
                            "type": entity.entity_type,
                            "name": entity.name,
                            "frequency": entity.frequency_count,
                        })

            # Trending topics (7-day window)
            ctx["trending_topics"] = self.get_trending_entities(limit=10)

            # Top research gaps
            ctx["research_gaps"] = self.find_research_gaps(limit=5)

            # Prior agent memory
            prior = session.query(AgentMemory).filter_by(agent_name=agent_name).all()
            for row in prior:
                try:
                    ctx["prior_agent_memory"][row.memory_key] = json.loads(row.memory_value_json)
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(f"build_context_for_agent: {exc}")
        finally:
            session.close()
        return ctx

    # ------------------------------------------------------------------
    # Novel Graph Metrics
    # ------------------------------------------------------------------

    def compute_novel_metrics(self, paper_id: int) -> Dict:
        """
        Compute graph-based metrics for a single paper.
        Returns a dict with all novel scores.
        """
        session = get_session()
        try:
            mentions = session.query(PaperEntityMention).filter_by(paper_id=paper_id).all()
            entity_ids = [m.entity_id for m in mentions]

            if not entity_ids:
                return {}

            entities = session.query(KGEntity).filter(KGEntity.id.in_(entity_ids)).all()
            entity_map = {e.id: e for e in entities}

            # Implementation Potential: code + dataset + baseline presence
            has_code = any(
                e.entity_type in ("CodeRepository", "HuggingFaceModel") for e in entities
            )
            has_dataset = any(e.entity_type == "Dataset" for e in entities)
            has_baseline = any(e.entity_type == "Baseline" for e in entities)
            implementation_potential = (
                (0.4 if has_code else 0.0) +
                (0.35 if has_dataset else 0.0) +
                (0.25 if has_baseline else 0.0)
            )

            # Cross-domain: methods appearing in multiple research areas
            method_entities = [e for e in entities if e.entity_type == "Method"]
            cross_domain_score = 0.0
            for me in method_entities:
                area_edges = session.query(KGEdge).filter_by(
                    source_entity_id=me.id, relationship_type="BELONGS_TO"
                ).count()
                if area_edges > 1:
                    cross_domain_score += 0.1 * area_edges
            cross_domain_score = min(1.0, cross_domain_score)

            # Novel combination: pairs of entity types that rarely co-occur
            type_pairs = Counter()
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    type_pairs[(e1.entity_type, e2.entity_type)] += 1
            # Low global freq of pair → high novelty
            novel_combo_score = 0.0
            for pair in list(type_pairs.keys())[:5]:
                e1_type, e2_type = pair
                pair_freq = session.query(KGEdge).filter(
                    KGEdge.relationship_type == "RELATED_TO"
                ).count()
                if pair_freq < 3:
                    novel_combo_score += 0.2
            novel_combo_score = min(1.0, novel_combo_score)

            # Topic velocity (average velocity of paper's topics)
            topic_entities = [e for e in entities if e.entity_type in ("Topic", "Method", "Task")]
            velocities = []
            for te in topic_entities[:5]:
                v = self._compute_velocity(session, te.id, window_days=7)
                velocities.append(v)
            avg_velocity = sum(velocities) / max(1, len(velocities))

            # Saturation (avg saturation of methods)
            saturations = []
            for te in topic_entities[:5]:
                tm = session.query(TrendMemory).filter_by(entity_id=te.id).order_by(
                    TrendMemory.date.desc()
                ).first()
                if tm:
                    saturations.append(tm.saturation_score)
            avg_saturation = sum(saturations) / max(1, len(saturations)) if saturations else 0.0

            return {
                "implementation_potential": round(implementation_potential, 2),
                "cross_domain_score": round(cross_domain_score, 2),
                "novel_combination_score": round(novel_combo_score, 2),
                "topic_velocity": round(avg_velocity, 3),
                "topic_saturation": round(avg_saturation, 3),
                "entity_count": len(entity_ids),
                "has_code": has_code,
                "has_dataset": has_dataset,
                "has_baseline": has_baseline,
            }
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _derive_entities_from_summary(self, paper: Paper, analysis: Dict) -> List[Dict]:
        """Convert a plain summarizer analysis dict into entity dicts for ingestion."""
        entities = []

        def add(etype: str, items, desc: str = ""):
            if isinstance(items, str) and items.strip():
                entities.append({"type": etype, "name": items.strip(), "description": desc, "confidence_score": 0.6})
            elif isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and item.strip():
                        entities.append({"type": etype, "name": item.strip(), "description": desc, "confidence_score": 0.6})

        # Authors from paper metadata
        try:
            authors = json.loads(paper.authors or "[]")
            add("Author", authors)
        except Exception:
            pass

        add("ResearchArea", analysis.get("research_area", ""))
        add("Method", analysis.get("methods", []))
        add("Method", analysis.get("method", ""))
        add("ModelArchitecture", analysis.get("model_architectures", []))
        add("Dataset", analysis.get("datasets_or_benchmarks", []))
        add("Metric", analysis.get("metrics", []))
        add("Baseline", analysis.get("baselines", []))
        add("Limitation", analysis.get("limitations", ""))
        add("FutureWork", analysis.get("future_work", ""))
        add("Topic", analysis.get("keywords", []))
        add("Topic", analysis.get("trend_tags", []))
        add("Task", analysis.get("problem", ""))

        # Code repos
        for kw in analysis.get("keywords", []):
            if "github" in kw.lower() or "code" in kw.lower():
                add("CodeRepository", kw)
        if "github" in analysis.get("method", "").lower():
            add("CodeRepository", "GitHub repository mentioned")

        return entities

    def _build_memory_chunks(self, paper: Paper, analysis: Dict) -> List[tuple]:
        """Build (type, text) tuples for semantic memory storage."""
        title = paper.title
        chunks = []

        if analysis.get("one_line_summary"):
            chunks.append(("summary", f"{title}: {analysis['one_line_summary']}"))
        if analysis.get("problem"):
            chunks.append(("problem", f"{title} — Problem: {analysis['problem']}"))
        if analysis.get("method"):
            chunks.append(("method", f"{title} — Method: {analysis['method']}"))
        if analysis.get("limitations"):
            chunks.append(("limitation", f"{title} — Limitation: {analysis['limitations']}"))
        if analysis.get("future_work"):
            chunks.append(("future_work", f"{title} — Future work: {analysis['future_work']}"))
        if analysis.get("results_or_claims"):
            chunks.append(("claim", f"{title} — Result: {analysis['results_or_claims']}"))
        if analysis.get("main_contribution"):
            chunks.append(("contribution", f"{title} — Contribution: {analysis['main_contribution']}"))
        return chunks

    def _get_entity_frequencies(self, session) -> Dict[str, Dict[str, int]]:
        """Return {entity_type: {normalized_name: count}} for saturation calc."""
        result: Dict[str, Dict[str, int]] = defaultdict(dict)
        entities = session.query(KGEntity).all()
        for e in entities:
            result[e.entity_type][e.normalized_name] = e.frequency_count
        return result

    def _compute_velocity(self, session, entity_id: int, window_days: int = 7) -> float:
        """
        Velocity = mentions in last `window_days` / mentions in prior `window_days`.
        Returns a ratio ≥ 0. Value > 1 means accelerating.
        """
        today = date.today()
        recent_start = (today - timedelta(days=window_days)).isoformat()
        prior_start = (today - timedelta(days=window_days * 2)).isoformat()

        recent = session.query(TrendMemory).filter(
            TrendMemory.entity_id == entity_id,
            TrendMemory.date >= recent_start,
        ).count()

        prior = session.query(TrendMemory).filter(
            TrendMemory.entity_id == entity_id,
            TrendMemory.date >= prior_start,
            TrendMemory.date < recent_start,
        ).count()

        if prior == 0:
            return float(recent)
        return round(recent / prior, 3)

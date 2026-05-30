"""
PersonalizationEngine — bridges ResearchMemoryEngine (global KG) with
Mem0 (personal per-user memory) to build unified agent context.

Memory architecture:
  Global KG  → our own SQLite tables (KGEntity, KGEdge, TrendMemory, etc.)
  Personal   → Mem0 (qdrant-backed, local OSS mode)

Every agent call:
  ctx = PersonalizationEngine.build_context(user_id, task, paper_id, query)
  → returns {global_context, personal_context}
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from app.database import (
    KGEntity, TrendMemory, Paper, Summary,
    UserProfile, UserPaperInteraction, SavedTopic,
    get_or_create_profile, get_session,
)

logger = logging.getLogger(__name__)

# ─── Mem0 setup ────────────────────────────────────────────────────────────
# MEMORY_BACKEND controls how personal memory is stored:
#   disabled → no Mem0; personal memory comes only from DB interactions + browser graph
#   local    → DB-only by default (no external vector DB). Set ENABLE_LOCAL_EMBEDDINGS
#              + a real OpenAI key to enable a local Mem0 store.
#   qdrant   → use a running Qdrant server (QDRANT_URL). Requires OpenAI embeddings key.
# This makes the previous silent "DB-fallback" an explicit, documented mode.
_mem0_client = None
_mem0_tried = False
MEMORY_BACKEND = os.getenv("MEMORY_BACKEND", "local").lower()
MEMORY_STRICT  = os.getenv("MEMORY_STRICT", "false").lower() == "true"


def get_memory_backend_status() -> Dict:
    """Report current personal-memory backend mode for the admin health page."""
    return {
        "mode":      MEMORY_BACKEND,
        "active":    _mem0_client is not None,
        "strict":    MEMORY_STRICT,
        "qdrant_url": os.getenv("QDRANT_URL", ""),
    }


def _project_data_dir(*parts) -> str:
    base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "data", *parts)


def _build_mem0(vector_cfg: Dict):
    from mem0 import Memory
    os.makedirs(_project_data_dir("mem0_home"), exist_ok=True)
    os.environ.setdefault("MEM0_DIR", _project_data_dir("mem0_home"))
    # Embeddings require a real OpenAI-compatible embeddings endpoint.
    embed_key  = os.getenv("OPENAI_API_KEY", "")
    embed_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    if not embed_key:
        raise RuntimeError("OPENAI_API_KEY required for Mem0 embeddings")
    config = {
        "vector_store": vector_cfg,
        "llm": {
            "provider": "openai",
            "config": {
                "model": os.getenv("SUMMARIZER_MODEL", "gpt-4o-mini"),
                "api_key": embed_key,
                "openai_base_url": embed_base,
            },
        },
        "embedder": {
            "provider": "openai",
            "config": {
                "model": os.getenv("EMBEDDING_MODEL_OPENAI", "text-embedding-3-small"),
                "api_key": embed_key,
                "openai_base_url": embed_base,
            },
        },
    }
    return Memory.from_config(config)


def _get_mem0():
    global _mem0_client, _mem0_tried
    if _mem0_client is not None or _mem0_tried:
        return _mem0_client
    _mem0_tried = True

    if MEMORY_BACKEND == "disabled":
        logger.info("MEMORY_BACKEND=disabled — personal memory is DB-only.")
        return None

    if MEMORY_BACKEND == "qdrant":
        try:
            _mem0_client = _build_mem0({
                "provider": "qdrant",
                "config": {
                    "collection_name": os.getenv("QDRANT_COLLECTION", "researchradar_mem0"),
                    "url": os.getenv("QDRANT_URL", "http://localhost:6333"),
                },
            })
            logger.info("Mem0 initialized with Qdrant backend.")
            return _mem0_client
        except Exception as exc:
            if MEMORY_STRICT:
                logger.error("Mem0 qdrant init failed and MEMORY_STRICT=true: %s", exc)
                return None
            logger.warning("Mem0 qdrant init failed (%s); falling back to local.", exc)

    # local mode (or qdrant fallback)
    try:
        _mem0_client = _build_mem0({
            "provider": "qdrant",
            "config": {
                "collection_name": "rr_personal_memory",
                "path": _project_data_dir("mem0_store"),
            },
        })
        logger.info("Mem0 initialized with local embedded store.")
    except Exception as exc:
        logger.info(
            "Mem0 not active (%s). Personal memory uses DB interactions + browser graph. "
            "Set MEMORY_BACKEND=qdrant + OPENAI_API_KEY to enable.", exc
        )
        _mem0_client = None
    return _mem0_client


class PersonalizationEngine:
    """Singleton-style engine — call class methods directly."""

    # ─── Personal memory (Mem0) ───────────────────────────────────────────

    @classmethod
    def remember(cls, user_id: int, text: str, metadata: Optional[Dict] = None) -> None:
        """Store a personal memory event for a user."""
        mem = _get_mem0()
        if mem is None:
            return
        try:
            mem.add(text, user_id=str(user_id), metadata=metadata or {})
        except Exception as exc:
            logger.warning("Mem0 add failed: %s", exc)

    @classmethod
    def search_personal(cls, user_id: int, query: str, limit: int = 5) -> List[Dict]:
        """Search personal memories for a user."""
        mem = _get_mem0()
        if mem is None:
            return []
        try:
            results = mem.search(query, user_id=str(user_id), limit=limit)
            # mem0 returns list of dicts with 'memory' key
            return [{"memory": r.get("memory", r.get("text", "")), "score": r.get("score", 0)} for r in results]
        except Exception as exc:
            logger.warning("Mem0 search failed: %s", exc)
            return []

    # ─── Profile helpers ─────────────────────────────────────────────────

    @classmethod
    def _get_profile_data(cls, session, user_id: int) -> Dict:
        p = get_or_create_profile(session, user_id)
        return {
            "interests":            json.loads(p.interests_json or "[]"),
            "preferred_categories": json.loads(p.preferred_categories_json or "[]"),
            "preferred_topics":     json.loads(p.preferred_topics_json or "[]"),
            "ignored_topics":       json.loads(p.ignored_topics_json or "[]"),
            "research_goals":       json.loads(p.research_goals_json or "[]"),
            "compute_budget":       p.compute_budget or "Single GPU",
        }

    @classmethod
    def _get_interactions(cls, session, user_id: int) -> Dict:
        interactions = (
            session.query(UserPaperInteraction)
            .filter_by(user_id=user_id)
            .order_by(UserPaperInteraction.created_at.desc())
            .limit(100)
            .all()
        )
        saved, read, ignored, liked = [], [], [], []
        for i in interactions:
            paper = session.query(Paper).filter_by(id=i.paper_id).first()
            if not paper:
                continue
            entry = {"paper_id": i.paper_id, "title": paper.title}
            if i.interaction_type == "saved":
                saved.append(entry)
            elif i.interaction_type in ("read", "viewed"):
                read.append(entry)
            elif i.interaction_type == "ignored":
                ignored.append(entry)
            elif i.interaction_type == "liked":
                liked.append(entry)
        return {"saved": saved[:10], "read": read[:10], "ignored": ignored[:10], "liked": liked[:10]}

    @classmethod
    def _get_saved_topics(cls, session, user_id: int) -> List[str]:
        rows = session.query(SavedTopic).filter_by(user_id=user_id).all()
        return [r.topic_name for r in rows]

    # ─── Global KG context ────────────────────────────────────────────────

    @classmethod
    def _get_global_context(cls, session, query: Optional[str], paper_id: Optional[int]) -> Dict:
        # Trending topics — join TrendMemory with KGEntity for the name
        trends = (
            session.query(TrendMemory)
            .order_by(TrendMemory.velocity_score.desc())
            .limit(10)
            .all()
        )
        topic_velocity = []
        for t in trends:
            name = t.entity_type  # fallback
            if t.entity_id:
                ent = session.query(KGEntity).filter_by(id=t.entity_id).first()
                if ent:
                    name = ent.name
            topic_velocity.append({
                "entity": name,
                "velocity": t.velocity_score,
                "saturation": t.saturation_score,
            })

        # Related KG entities if we have a paper
        related_topics = []
        if paper_id:
            from app.database import PaperEntityMention, KGEdge
            mentions = (
                session.query(PaperEntityMention)
                .filter_by(paper_id=paper_id)
                .limit(20)
                .all()
            )
            entity_ids = [m.entity_id for m in mentions]
            entities = session.query(KGEntity).filter(KGEntity.id.in_(entity_ids)).all()
            related_topics = [{"name": e.name, "type": e.entity_type} for e in entities]

        # Top research gaps
        gaps = (
            session.query(KGEntity)
            .filter(KGEntity.entity_type.in_(["ResearchGap", "Limitation"]))
            .order_by(KGEntity.frequency_count.desc())
            .limit(8)
            .all()
        )
        research_gaps = [{"name": g.name, "count": g.frequency_count} for g in gaps]

        return {
            "topic_velocity":    topic_velocity,
            "related_topics":    related_topics,
            "research_gaps":     research_gaps,
        }

    # ─── Main context builder ─────────────────────────────────────────────

    @classmethod
    def build_context(
        cls,
        user_id: Optional[int],
        task: str = "",
        paper_id: Optional[int] = None,
        query: Optional[str] = None,
    ) -> Dict:
        """
        Build the unified agent context combining global KG and personal memory.
        Safe to call with user_id=None (returns global context only).
        """
        session = get_session()
        try:
            global_ctx = cls._get_global_context(session, query, paper_id)

            personal_ctx: Dict[str, Any] = {
                "user_interests":          [],
                "saved_topics":            [],
                "saved_papers":            [],
                "recently_read_papers":    [],
                "ignored_topics":          [],
                "preferred_compute_budget": "Single GPU",
                "preferred_project_types": [],
                "mem0_memories":           [],
            }

            if user_id:
                profile   = cls._get_profile_data(session, user_id)
                intx      = cls._get_interactions(session, user_id)
                saved_tps = cls._get_saved_topics(session, user_id)

                personal_ctx.update({
                    "user_interests":           profile["interests"],
                    "saved_topics":             saved_tps,
                    "saved_papers":             intx["saved"],
                    "recently_read_papers":     intx["read"],
                    "ignored_topics":           profile["ignored_topics"],
                    "preferred_compute_budget": profile["compute_budget"],
                    "preferred_project_types":  profile["research_goals"],
                })

                # Enrich with Mem0 semantic search
                if query or task:
                    mem_results = cls.search_personal(user_id, query or task, limit=5)
                    personal_ctx["mem0_memories"] = mem_results

            return {
                "global_context":   global_ctx,
                "personal_context": personal_ctx,
            }
        finally:
            session.close()

"""
MemoryRetrievalAgent

Before any major agent runs (summarization, trend analysis, project
generation, code generation), call this agent to retrieve relevant
prior memory from the ResearchMemoryEngine.

Returns a structured context dict that the calling agent can inject
into its LLM prompt or use for pre-filtering.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

from app.memory.research_memory_engine import ResearchMemoryEngine

logger = logging.getLogger(__name__)

_engine = ResearchMemoryEngine()


class MemoryRetrievalAgent:
    """
    Provides a unified interface for agents to query shared research memory
    before performing any LLM task.

    Usage:
        ctx = MemoryRetrievalAgent().retrieve(
            query="transformer-based robotics control",
            paper_id=42,
            calling_agent="CodeGeneratorAgent",
        )
        # ctx["related_papers"], ctx["matching_entities"], ctx["gaps"], ...
    """

    def retrieve(
        self,
        query: str,
        paper_id: Optional[int] = None,
        calling_agent: str = "unknown",
        top_k: int = 10,
    ) -> Dict:
        """
        Main retrieval method.

        Returns:
            related_papers    — similar papers by entity overlap
            matching_entities — entities matching the query keywords
            research_gaps     — top unresolved gaps relevant to the query
            trending_topics   — currently accelerating topics
            prior_outputs     — cached outputs from the same agent for this paper
            narrative         — a short human-readable memory summary string
        """
        ctx = {
            "query": query,
            "calling_agent": calling_agent,
            "paper_id": paper_id,
            "related_papers": [],
            "matching_entities": [],
            "research_gaps": [],
            "trending_topics": [],
            "prior_outputs": {},
            "narrative": "",
        }

        try:
            # Graph + text hybrid retrieval
            raw_results = _engine.query_memory(query, limit=top_k * 2)

            # Split into entity results vs semantic memory results
            for r in raw_results:
                if r.get("source") == "entity":
                    ctx["matching_entities"].append(r)
                else:
                    # Semantic memory hits can contain paper context
                    pid = r.get("paper_id") or r.get("metadata", {}).get("paper_id")
                    if pid and pid != paper_id:
                        ctx["related_papers"].append({
                            "paper_id": pid,
                            "memory_type": r.get("memory_type", ""),
                            "text": r.get("text", ""),
                            "relevance": r.get("relevance", 0),
                        })

            ctx["matching_entities"] = ctx["matching_entities"][:top_k]
            ctx["related_papers"] = ctx["related_papers"][:top_k]

            # Deduplicate related papers by paper_id
            seen_pids: set = set()
            deduped = []
            for p in ctx["related_papers"]:
                if p["paper_id"] not in seen_pids:
                    seen_pids.add(p["paper_id"])
                    deduped.append(p)
            ctx["related_papers"] = deduped

            # Similar papers by entity overlap
            if paper_id:
                similar = _engine.find_similar_papers(paper_id, limit=5)
                for s in similar:
                    if s["paper_id"] not in seen_pids:
                        ctx["related_papers"].append(s)

            # Research gaps
            ctx["research_gaps"] = _engine.find_research_gaps(limit=5)

            # Trending topics
            ctx["trending_topics"] = _engine.get_trending_entities(limit=8)

            # Prior agent outputs
            agent_ctx = _engine.build_context_for_agent(calling_agent, query, paper_id)
            ctx["prior_outputs"] = agent_ctx.get("prior_agent_memory", {})

            # Build narrative
            ctx["narrative"] = self._build_narrative(ctx)

        except Exception as exc:
            logger.warning(f"MemoryRetrievalAgent.retrieve: {exc}")

        return ctx

    def _build_narrative(self, ctx: Dict) -> str:
        lines = []
        if ctx["matching_entities"]:
            top_ents = [e["name"] for e in ctx["matching_entities"][:5]]
            lines.append(f"Related entities in memory: {', '.join(top_ents)}.")
        if ctx["trending_topics"]:
            top_trends = [t["name"] for t in ctx["trending_topics"][:4]]
            lines.append(f"Currently trending: {', '.join(top_trends)}.")
        if ctx["research_gaps"]:
            top_gaps = [g["name"] for g in ctx["research_gaps"][:3]]
            lines.append(f"Open research gaps: {', '.join(top_gaps)}.")
        if ctx["related_papers"]:
            lines.append(f"Found {len(ctx['related_papers'])} related papers in memory.")
        return " ".join(lines) or "No prior memory found for this query."

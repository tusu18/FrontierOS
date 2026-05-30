"""
MemoryAwareCodeGeneratorAgent

Extends CodeGeneratorAgent by enriching the prompt with relevant
shared research memory before generating code.

Additions over the base agent:
  - Retrieves similar papers' code patterns from memory
  - Includes known datasets, baselines, and GitHub links from KG
  - Adds implementation potential score context
  - Cites prior generated code from memory for consistency
"""

from __future__ import annotations
import json
import logging
from typing import Dict, Optional

from app.agents.code_generator_agent import CodeGeneratorAgent
from app.agents.memory_retrieval_agent import MemoryRetrievalAgent
from app.database import get_session, save_generated_code, get_generated_code, KGEntity, PaperEntityMention
from app.memory.research_memory_engine import ResearchMemoryEngine
from app.openrouter_client import call_openrouter, is_api_key_configured
from app.utils import truncate

logger = logging.getLogger(__name__)

_retrieval = MemoryRetrievalAgent()
_engine = ResearchMemoryEngine()


class MemoryAwareCodeGeneratorAgent:
    """
    Memory-enriched code generator.

    Falls back to the base CodeGeneratorAgent if memory layer is empty.
    """

    def __init__(self):
        self._base = CodeGeneratorAgent()

    def run(
        self,
        paper: Dict,
        code_mode: str,
        full_text: str = "",
        use_cache: bool = True,
    ) -> str:
        if not is_api_key_configured():
            return "⚠️ OpenRouter API key not configured."

        paper_id = paper.get("id") or paper.get("db_id")

        # Check cache first
        if use_cache and paper_id:
            session = get_session()
            try:
                cached = get_generated_code(session, paper_id, f"memory_{code_mode}")
                if cached:
                    return cached
            finally:
                session.close()

        # Build memory context
        query = f"{paper.get('title', '')} {code_mode}"
        mem_ctx = _retrieval.retrieve(query=query, paper_id=paper_id, calling_agent="MemoryAwareCodeGeneratorAgent")

        # Extract KG-enriched details for this paper
        kg_context = self._build_kg_context(paper_id)

        # Build enriched prompt
        code = self._generate_with_memory(paper, code_mode, full_text, mem_ctx, kg_context)

        # Save to cache with "memory_" prefix so it's distinguishable
        if code and paper_id:
            session = get_session()
            try:
                save_generated_code(session, paper_id, f"memory_{code_mode}", code)
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"MemoryAwareCodeGeneratorAgent: cache save error: {e}")
            finally:
                session.close()

        return code

    def _build_kg_context(self, paper_id: Optional[int]) -> Dict:
        """Pull KG-derived context for the paper."""
        if not paper_id:
            return {}
        session = get_session()
        try:
            mentions = session.query(PaperEntityMention).filter_by(paper_id=paper_id).all()
            entity_ids = [m.entity_id for m in mentions]
            entities = session.query(KGEntity).filter(KGEntity.id.in_(entity_ids)).all()

            datasets = [e.name for e in entities if e.entity_type == "Dataset"]
            baselines = [e.name for e in entities if e.entity_type == "Baseline"]
            code_repos = [e.name for e in entities if e.entity_type in ("CodeRepository", "HuggingFaceModel")]
            methods = [e.name for e in entities if e.entity_type == "Method"]
            metrics = [e.name for e in entities if e.entity_type == "Metric"]

            metrics_data = _engine.compute_novel_metrics(paper_id)

            return {
                "datasets": datasets,
                "baselines": baselines,
                "code_repos": code_repos,
                "methods": methods,
                "metrics": metrics,
                "implementation_potential": metrics_data.get("implementation_potential", 0),
                "has_code": metrics_data.get("has_code", False),
            }
        finally:
            session.close()

    def _generate_with_memory(
        self,
        paper: Dict,
        code_mode: str,
        full_text: str,
        mem_ctx: Dict,
        kg_ctx: Dict,
    ) -> str:
        """Build memory-enriched prompt and call OpenRouter."""
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        method = paper.get("method", "")
        main_contribution = paper.get("main_contribution", "")

        # Memory narrative
        memory_section = ""
        if mem_ctx.get("narrative"):
            memory_section += f"\n**Research Memory Context:**\n{mem_ctx['narrative']}\n"

        if kg_ctx.get("datasets"):
            memory_section += f"\n**Known datasets in this space:** {', '.join(kg_ctx['datasets'][:5])}"
        if kg_ctx.get("baselines"):
            memory_section += f"\n**Common baselines:** {', '.join(kg_ctx['baselines'][:5])}"
        if kg_ctx.get("code_repos"):
            memory_section += f"\n**Available code/models:** {', '.join(kg_ctx['code_repos'][:3])}"
        if kg_ctx.get("methods"):
            memory_section += f"\n**Related methods in memory:** {', '.join(kg_ctx['methods'][:5])}"

        impl_score = kg_ctx.get("implementation_potential", 0)
        if impl_score > 0:
            memory_section += f"\n**Implementation potential score:** {impl_score:.0%}"

        if mem_ctx.get("related_papers"):
            rp_lines = [
                f"  - Paper {rp.get('paper_id', '?')}: {rp.get('text', '')[:80]}"
                for rp in mem_ctx["related_papers"][:3]
            ]
            memory_section += "\n**Related prior work in memory:**\n" + "\n".join(rp_lines)

        prompt_text = f"""\
You are an expert ML engineer. Generate production-quality {code_mode} for the following paper.

**Paper:** {title}
**Abstract:** {truncate(abstract, 600)}
**Method:** {method}
**Main contribution:** {main_contribution}
{f"**Full text excerpt:**\n{truncate(full_text, 1000)}" if full_text else ""}
{memory_section}

Generate {code_mode}. Be specific, practical, and use the known datasets and baselines above
if relevant. Include comments explaining design choices. Output Markdown with code blocks.
"""
        messages = [
            {"role": "system", "content": "You are an expert ML implementation engineer who writes clean, reproducible code."},
            {"role": "user", "content": prompt_text},
        ]
        return call_openrouter(messages, temperature=0.3, max_tokens=4000)

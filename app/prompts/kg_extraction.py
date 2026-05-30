"""Prompt builder for the KnowledgeGraphBuilderAgent."""

from __future__ import annotations
from typing import Dict, Any
from app.utils import truncate


SYSTEM_PROMPT = """\
You are a research knowledge graph extraction agent.
Extract entities and relationships from the given paper analysis.
Return strict JSON only — no prose, no markdown fences.

Entity types (use EXACTLY these values for the "type" field):
Paper, Author, Institution, ResearchArea, Topic, Task, Method, ModelArchitecture,
Dataset, Benchmark, Metric, Baseline, Claim, Result, Limitation, FutureWork,
CodeRepository, ProjectPage, HuggingFaceModel, Tool, Library, ResearchGap.

Relationship types (use EXACTLY these values for the "relationship_type" field):
AUTHORED_BY, AFFILIATED_WITH, BELONGS_TO, ADDRESSES, USES, INTRODUCES,
USES_MODEL, EVALUATES_ON, REPORTS_METRIC, COMPARES_AGAINST, MAKES_CLAIM,
SUPPORTED_BY, HAS_LIMITATION, SUGGESTS_FUTURE_WORK, HAS_CODE, IMPLEMENTS,
IMPROVES_ON, RELATED_TO, USED_FOR, MEASURES, EMERGES_FROM, BUILDS_ON,
TARGETS, SIMILAR_TO, EXTENDS.

Rules:
- normalized_name must be lowercase, stripped, single-spaced.
- description must be ≤ 1 short sentence.
- evidence_text quotes the relevant fragment from the paper (≤ 100 chars).
- confidence_score is a float 0.0–1.0.
- Return ONLY valid JSON, nothing else.

Output schema:
{
  "entities": [
    {
      "type": "<EntityType>",
      "name": "<canonical name>",
      "normalized_name": "<lowercase name>",
      "description": "<one sentence>",
      "evidence_text": "<quoted fragment>",
      "confidence_score": 0.0,
      "metadata": {}
    }
  ],
  "relationships": [
    {
      "source_entity_name": "<name>",
      "relationship_type": "<TYPE>",
      "target_entity_name": "<name>",
      "evidence_text": "<quoted fragment>",
      "confidence_score": 0.0,
      "metadata": {}
    }
  ]
}
"""


def build_kg_extraction_prompt(
    paper: Dict[str, Any],
    analysis: Dict[str, Any],
    full_text_excerpt: str = "",
    memory_context: Dict[str, Any] = None,
) -> list:
    """
    Build the message list for the KG extraction LLM call.

    paper          — dict with title, abstract, authors, primary_category, etc.
    analysis       — dict with one_line_summary, method, limitations, etc.
    full_text_excerpt — optional PDF excerpt (first ~2000 chars)
    memory_context — optional dict from ResearchMemoryEngine.build_context_for_agent
    """
    paper_block = (
        f"Title: {paper.get('title', '')}\n"
        f"Authors: {', '.join(paper.get('authors', []))}\n"
        f"Category: {paper.get('primary_category', '')}\n"
        f"Abstract: {truncate(paper.get('abstract', ''), 800)}"
    )

    analysis_block = (
        f"One-line summary: {analysis.get('one_line_summary', '')}\n"
        f"Problem: {analysis.get('problem', '')}\n"
        f"Method: {analysis.get('method', '')}\n"
        f"Main contribution: {analysis.get('main_contribution', '')}\n"
        f"Datasets/Benchmarks: {analysis.get('datasets_or_benchmarks', [])}\n"
        f"Results/Claims: {analysis.get('results_or_claims', '')}\n"
        f"Limitations: {analysis.get('limitations', '')}\n"
        f"Future work: {analysis.get('future_work', '')}\n"
        f"Keywords: {analysis.get('keywords', [])}\n"
        f"Methods: {analysis.get('methods', [])}\n"
        f"Metrics: {analysis.get('metrics', [])}\n"
        f"Baselines: {analysis.get('baselines', [])}\n"
        f"Model architectures: {analysis.get('model_architectures', [])}"
    )

    text_block = truncate(full_text_excerpt, 1500) if full_text_excerpt else "Not available."

    # Add a small memory hint so the LLM can reference prior entities
    memory_hint = ""
    if memory_context:
        trending = [t["name"] for t in memory_context.get("trending_topics", [])[:5]]
        gaps = [g["name"] for g in memory_context.get("research_gaps", [])[:3]]
        if trending:
            memory_hint += f"\nCurrently trending in memory: {', '.join(trending)}."
        if gaps:
            memory_hint += f"\nKnown research gaps: {', '.join(gaps)}."

    user_content = (
        f"### Paper\n{paper_block}\n\n"
        f"### Analysis\n{analysis_block}\n\n"
        f"### Full-text excerpt\n{text_block}"
        f"{memory_hint}\n\n"
        "Extract all entities and relationships. Return JSON only."
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

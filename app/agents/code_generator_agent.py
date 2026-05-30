"""CodeGeneratorAgent: Generates implementation code/pseudocode from papers."""

from __future__ import annotations
import logging
from typing import Dict, Optional

from app.database import get_session, save_generated_code, get_generated_code
from app.openrouter_client import call_openrouter, is_api_key_configured
from app.prompts.code_generation import build_code_prompt

logger = logging.getLogger(__name__)

CODE_MODES = [
    "Pseudocode",
    "PyTorch implementation sketch",
    "Training pipeline",
    "Dataset preparation script",
    "Evaluation script",
    "Reproduction plan",
    "Minimal working prototype",
    "Streamlit demo idea",
    "GitHub README for reproduction",
    "Colab notebook outline",
]


class CodeGeneratorAgent:
    """
    Generates starter code or pseudocode from a research paper.

    Input:  paper dict, code_mode string
    Output: Markdown string with code
    """

    def run(
        self,
        paper: Dict,
        code_mode: str,
        full_text: str = "",
        use_cache: bool = True,
    ) -> str:
        """Generate code for the given paper and mode."""
        if not is_api_key_configured():
            return "⚠️ OpenRouter API key not configured. Add OPENROUTER_API_KEY to your .env file."

        paper_id = paper.get("id") or paper.get("db_id")

        # Check cache
        if use_cache and paper_id:
            session = get_session()
            try:
                cached = get_generated_code(session, paper_id, code_mode)
                if cached:
                    logger.info(f"CodeGeneratorAgent: returning cached code for paper_id={paper_id}, mode={code_mode}")
                    return cached
            finally:
                session.close()

        title = paper.get("title", "Unknown")
        abstract = paper.get("abstract", "")
        method = paper.get("method", "")
        main_contribution = paper.get("main_contribution", "")
        datasets = paper.get("datasets_or_benchmarks", [])
        datasets_str = ", ".join(datasets) if isinstance(datasets, list) else str(datasets)

        messages = build_code_prompt(
            title=title,
            abstract=abstract,
            method=method,
            main_contribution=main_contribution,
            datasets_or_benchmarks=datasets_str,
            full_text_excerpt=full_text,
            code_mode=code_mode,
        )

        logger.info(f"CodeGeneratorAgent: generating '{code_mode}' for '{title[:50]}'")
        result = call_openrouter(messages, temperature=0.2, max_tokens=4000)

        if not result:
            return "❌ Code generation failed. Please try again."

        # Save to DB
        if paper_id:
            session = get_session()
            try:
                save_generated_code(session, paper_id, code_mode, result)
                session.commit()
                logger.info(f"CodeGeneratorAgent: saved generated code for paper_id={paper_id}")
            except Exception as e:
                session.rollback()
                logger.error(f"CodeGeneratorAgent: save error: {e}")
            finally:
                session.close()

        return result

    def generate_technical_explanation(self, paper: Dict) -> str:
        """Generate a deeper technical explanation of the paper."""
        if not is_api_key_configured():
            return "API key not configured."

        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        method = paper.get("method", "")
        contribution = paper.get("main_contribution", "")

        messages = [
            {"role": "system", "content": "You are an expert ML engineer who explains research clearly."},
            {"role": "user", "content": f"""Provide a deeper technical explanation of this paper for an ML engineer.

Title: {title}
Abstract: {abstract}
Method: {method}
Main contribution: {contribution}

Explain:
1. The core technical innovation (with math/notation if helpful)
2. How it differs from prior work technically
3. Key implementation components
4. Computational complexity considerations
5. Why this approach works (intuition)
6. Potential failure modes

Format as clear Markdown."""}
        ]
        return call_openrouter(messages, temperature=0.2, max_tokens=2500) or "Unavailable."

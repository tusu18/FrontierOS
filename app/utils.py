"""Shared utility functions."""

from __future__ import annotations
import json
import re
import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)


def safe_json_parse(text: str, fallback: Any = None) -> Any:
    """Try to parse JSON from LLM output; repair common issues."""
    if fallback is None:
        fallback = {}
    if not text:
        return fallback

    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned, flags=re.MULTILINE).strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Try extracting first {...} block
    match = re.search(r"\{[\s\S]+\}", cleaned)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    # Attempt naive repair: trailing commas
    repaired = re.sub(r",\s*([}\]])", r"\1", cleaned)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    logger.warning("safe_json_parse: could not parse JSON, returning fallback.")
    return fallback


def truncate(text: str, max_chars: int = 8000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated]"


def setup_logging(level: str = "INFO"):
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=getattr(logging, level.upper(), logging.INFO),
    )


def ensure_dirs():
    """Create data/ and exports/ directories relative to project root."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in ["data", "exports"]:
        os.makedirs(os.path.join(root, d), exist_ok=True)


def load_env():
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env_path = os.path.join(root, ".env")
        if os.path.exists(env_path):
            load_dotenv(env_path)
    except ImportError:
        pass


def clamp_score(val: Any, default: int = 5) -> int:
    try:
        v = int(val)
        return max(1, min(10, v))
    except (TypeError, ValueError):
        return default

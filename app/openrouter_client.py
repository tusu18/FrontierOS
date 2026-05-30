"""OpenRouter API client with retry, timeout, and JSON repair."""

from __future__ import annotations
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from app.utils import safe_json_parse

logger = logging.getLogger(__name__)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def _get_api_key() -> str:
    key = os.getenv("OPENROUTER_API_KEY", "")
    if not key:
        raise ValueError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to your .env file or export it as an environment variable."
        )
    return key


def _get_model() -> str:
    return os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")


def call_openrouter(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2500,
    retries: int = 3,
    retry_delay: float = 5.0,
    timeout: int = 60,
) -> str:
    """
    Call OpenRouter chat completions endpoint.

    Returns the assistant message content as a string.
    Raises RuntimeError on permanent failure.
    """
    try:
        api_key = _get_api_key()
    except ValueError as e:
        logger.error(str(e))
        return ""

    mdl = model or _get_model()
    temperature = float(os.getenv("LLM_TEMPERATURE", str(temperature)))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", str(max_tokens)))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://arxiv-cs-dashboard.local",
        "X-Title": "ArXiv CS Research Dashboard",
    }

    payload = {
        "model": mdl,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )

            if resp.status_code == 429:
                wait = retry_delay * attempt
                logger.warning(f"Rate limited. Waiting {wait}s before retry {attempt}/{retries}.")
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                logger.warning(f"Server error {resp.status_code}. Retrying {attempt}/{retries}.")
                time.sleep(retry_delay)
                continue

            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            logger.debug(f"OpenRouter call successful. Tokens used: {data.get('usage', {})}")
            return content

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout on attempt {attempt}/{retries}.")
            last_error = "Timeout"
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error on attempt {attempt}/{retries}: {e}")
            last_error = str(e)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning(f"Response parse error: {e}")
            last_error = str(e)

        if attempt < retries:
            time.sleep(retry_delay * attempt)

    logger.error(f"OpenRouter call failed after {retries} attempts. Last error: {last_error}")
    return ""


def call_openrouter_json(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2500,
    fallback: Any = None,
) -> Any:
    """
    Call OpenRouter and parse the response as JSON.
    Uses safe_json_parse for robustness.
    """
    text = call_openrouter(messages, model=model, temperature=temperature, max_tokens=max_tokens)
    return safe_json_parse(text, fallback=fallback if fallback is not None else {})


def is_api_key_configured() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY", "").strip())

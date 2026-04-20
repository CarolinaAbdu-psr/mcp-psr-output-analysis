"""
Shared utilities for the SDDP diagnostic agent.

Includes:
  - extract_json_from_response: strip markdown fences from LLM output before JSON parsing
  - setup_logging / get_logger: structured debug logging (toggled via --debug or SDDP_AGENT_DEBUG=1)
"""
from __future__ import annotations

import logging
import os
import re

# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def extract_json_from_response(text: str) -> str:
    """
    Strip markdown code fences and return the raw JSON string from an LLM response.

    Handles the three common formats GPT models return:
      1. ```json\\n{...}\\n```
      2. ```\\n{...}\\n```
      3. Plain JSON (no wrapping) — returned as-is

    As a final fallback, tries to extract the first valid JSON object or array
    by finding the outermost braces/brackets.
    """
    text = text.strip()

    # Case 1 & 2: markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Case 3: plain JSON — starts with { or [
    if text.startswith(("{", "[")):
        return text

    # Fallback: find the outermost { ... } or [ ... ]
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start >= 0:
            end = text.rfind(close_ch)
            if end > start:
                return text[start : end + 1]

    return text  # Return as-is; json.loads will raise the appropriate error


def safe_json_loads(text: str, context: str = "") -> object:
    """
    Parse JSON from an LLM response, stripping markdown fences first.
    Raises json.JSONDecodeError with a descriptive message on failure.
    """
    import json

    cleaned = extract_json_from_response(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        label = f" [{context}]" if context else ""
        raise json.JSONDecodeError(
            f"Failed to parse LLM JSON{label}: {exc.msg}",
            exc.doc,
            exc.pos,
        ) from exc


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s  %(levelname)-7s  %(name)s  │  %(message)s"
_LOG_DATE   = "%H:%M:%S"
_ROOT_LOGGER = "sddp_agent"
_CONFIGURED  = False


def setup_logging(debug: bool = False) -> None:
    """
    Configure the sddp_agent logger.

    debug=True  → DEBUG level; shows LLM prompts, raw responses, tool calls, edge decisions
    debug=False → WARNING level; only errors and warnings are shown
    """
    global _CONFIGURED
    if _CONFIGURED:
        # Allow reconfiguration if called again (e.g., after --debug flag is parsed)
        logging.getLogger(_ROOT_LOGGER).setLevel(
            logging.DEBUG if debug else logging.WARNING
        )
        return

    level = logging.DEBUG if debug else logging.WARNING
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE))

    root = logging.getLogger(_ROOT_LOGGER)
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the sddp_agent namespace."""
    return logging.getLogger(f"{_ROOT_LOGGER}.{name}")


def is_debug() -> bool:
    """True when debug logging is active (via --debug flag or SDDP_AGENT_DEBUG=1 env var)."""
    return (
        logging.getLogger(_ROOT_LOGGER).isEnabledFor(logging.DEBUG)
        or os.getenv("SDDP_AGENT_DEBUG", "0") == "1"
    )

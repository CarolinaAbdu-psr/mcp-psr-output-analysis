"""
Named model registry for the SDDP agent.

Each attribute is a lazily-instantiated LangChain chat model.

Usage:
    from sddp_agent import get_model

    llm = get_model.GPT_4_1            # default
    llm = get_model.GPT_4_1_MINI
    llm = get_model.OPENAI_5
    llm = get_model.O3
    llm = get_model.CLAUDE_4_SONNET    # requires ANTHROPIC_API_KEY in .env
    llm = get_model.DEEPSEEK_REASONER  # requires DEEPSEEK_API_KEY in .env

Available names:
    GPT_4_1 | GPT_4_1_MINI | OPENAI_5 | O3 | CLAUDE_4_SONNET | DEEPSEEK_REASONER
"""
from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import BaseChatOpenAI

REQUEST_TIMEOUT: int = 120
MAX_TOKENS: int = 4096
TEMPERATURE: float = 0.7


# ---------------------------------------------------------------------------
# Internal builders — one per model
# ---------------------------------------------------------------------------

def _gpt_4_1() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4.1",
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        request_timeout=REQUEST_TIMEOUT,
    )


def _gpt_4_1_mini() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-4.1-mini",
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        request_timeout=REQUEST_TIMEOUT,
    )


def _openai_5() -> ChatOpenAI:
    return ChatOpenAI(
        model="gpt-5-2025-08-07",
        request_timeout=REQUEST_TIMEOUT,
    )


def _o3() -> ChatOpenAI:
    return ChatOpenAI(
        model="o3",
        request_timeout=REQUEST_TIMEOUT,
    )


def _claude_4_sonnet() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-sonnet-4-20250514",
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT,
    )


def _deepseek_reasoner() -> BaseChatOpenAI:
    return BaseChatOpenAI(
        model="deepseek-reasoner",
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com",
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        request_timeout=REQUEST_TIMEOUT,
    )


# ---------------------------------------------------------------------------
# Registry: attribute name → builder function
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, object] = {
    "GPT_4_1":           _gpt_4_1,
    "GPT_4_1_MINI":      _gpt_4_1_mini,
    "OPENAI_5":          _openai_5,
    "O3":                _o3,
    "CLAUDE_4_SONNET":   _claude_4_sonnet,
    "DEEPSEEK_REASONER": _deepseek_reasoner,
}


def __getattr__(name: str):
    """Lazy instantiation: each access builds a fresh model instance."""
    builder = _REGISTRY.get(name)
    if builder is None:
        available = ", ".join(_REGISTRY)
        raise AttributeError(
            f"Model '{name}' not found in get_model.\n"
            f"Available: {available}"
        )
    return builder()

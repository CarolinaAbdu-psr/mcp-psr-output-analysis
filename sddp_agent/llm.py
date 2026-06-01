"""
Central LLM factory for the SDDP agent.

Model is selected via the SDDP_AGENT_MODEL environment variable (default: gpt-4.1).

Supported values:
    gpt-4.1            (default) — OpenAI GPT-4.1
    gpt-4.1-mini       — OpenAI GPT-4.1 mini
    gpt-5-2025-08-07   — OpenAI GPT-5
    o3                 — OpenAI o3 (reasoning; no temperature/max_tokens)
    claude-4-sonnet    — Anthropic Claude Sonnet 4 (requires ANTHROPIC_API_KEY)
    deepseek-reasoner  — DeepSeek Reasoner (requires DEEPSEEK_API_KEY)
"""
from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models.base import BaseChatOpenAI

REQUEST_TIMEOUT: int = 120
MAX_TOKENS: int = 4096

_REASONING_MODELS = {"o3", "gpt-5-2025-08-07"}


def get_llm(max_tokens: int | None = None) -> Any:
    """
    Return a LangChain chat model based on SDDP_AGENT_MODEL.

    Args:
        max_tokens: Override the default MAX_TOKENS for this call.
                    Ignored for reasoning models (o3, gpt-5) that don't accept the param.
    """
    model = os.environ.get("SDDP_AGENT_MODEL", "gpt-4.1")
    tokens = max_tokens if max_tokens is not None else MAX_TOKENS

    if model in _REASONING_MODELS:
        return ChatOpenAI(
            model=model,
            request_timeout=REQUEST_TIMEOUT,
        )

    if model == "gpt-4.1":
        return ChatOpenAI(
            model=model,
            temperature=0.7,
            max_tokens=tokens,
            request_timeout=REQUEST_TIMEOUT,
        )

    if model == "gpt-4.1-mini":
        return ChatOpenAI(
            model=model,
            temperature=0.7,
            max_tokens=tokens,
            request_timeout=REQUEST_TIMEOUT,
        )

    if model == "claude-4-sonnet":
        return ChatAnthropic(
            model="claude-sonnet-4-20250514",
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            temperature=0.7,
            max_tokens=tokens,
            timeout=REQUEST_TIMEOUT,
        )

    if model == "deepseek-reasoner":
        return BaseChatOpenAI(
            model="deepseek-reasoner",
            openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
            openai_api_base="https://api.deepseek.com",
            temperature=0.7,
            max_tokens=tokens,
            request_timeout=REQUEST_TIMEOUT,
        )

    # Fallback — unknown model string passed directly to OpenAI
    return ChatOpenAI(
        model=model,
        temperature=0.7,
        max_tokens=tokens,
        request_timeout=REQUEST_TIMEOUT,
    )

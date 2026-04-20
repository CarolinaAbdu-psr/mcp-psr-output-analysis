"""
Router node: map user query to a problem_type and rank all entry points.

Uses the LLM to classify the user's question into one of the three registered
entry points from decision_graph.json and return them ranked by relevance.
The verify_entry node uses this ranking to select and verify the actual entry point.
"""
from __future__ import annotations

import json
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..tools.graph_loader import load_graph
from ..utils import get_logger, safe_json_loads

_log = get_logger("router")

_PROMPT_PATH = Path(__file__).parents[1] / "prompts" / "router_prompt.txt"
_ROUTER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model_name="gpt-4.1", max_tokens=256, temperature=0.4)


def route_problem(state: dict) -> dict:
    """
    Classify user_query into a problem_type and rank all entry point nodes.

    Reads:  user_query, case_metadata, conversation_history
    Writes: problem_type, entry_point_ranking, current_node_id (primary entry node)
    """
    graph = load_graph()
    entry_points = graph["entry_points"]  # {problem_type: node_id}

    history_text = ""
    for msg in state.get("conversation_history", [])[-6:]:
        role = msg["role"].upper()
        history_text += f"{role}: {msg['content']}\n"

    prompt_text = _ROUTER_PROMPT.format(
        entry_points=json.dumps(entry_points, indent=2),
        case_metadata=json.dumps(state.get("case_metadata", {}), indent=2, ensure_ascii=False),
        conversation_history=history_text.strip() or "(none)",
        user_query=state["user_query"],
    )

    _log.debug(
        "[router] classifying query: %r\n  entry_points: %s",
        state["user_query"],
        list(entry_points.keys()),
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_text),
    ])
    raw = response.content

    _log.debug("[router] raw LLM response: %s", raw)

    # Parse problem_type and entry_point_ranking from LLM response
    problem_type = "problema_simulacao"  # safe default
    entry_point_ranking: list[str] = []

    try:
        parsed = safe_json_loads(raw, context="router")
        problem_type = parsed.get("problem_type", problem_type)

        # Validate problem_type
        if problem_type not in entry_points:
            _log.warning("[router] unknown problem_type %r — defaulting", problem_type)
            problem_type = next(iter(entry_points))

        # Extract ranked node IDs
        raw_ranking = parsed.get("entry_point_ranking", [])
        valid_node_ids = set(entry_points.values())
        entry_point_ranking = [nid for nid in raw_ranking if nid in valid_node_ids]

        _log.debug(
            "[router] → %s  ranking: %s  (reason: %s)",
            problem_type,
            entry_point_ranking,
            parsed.get("reasoning", ""),
        )

    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        _log.warning("[router] parse error (%s) — defaulting", exc)

    # If ranking is missing or malformed, build it from problem_type as primary
    if not entry_point_ranking:
        primary = entry_points[problem_type]
        entry_point_ranking = [primary] + [
            nid for pt, nid in entry_points.items() if pt != problem_type
        ]
        _log.debug("[router] built fallback ranking: %s", entry_point_ranking)

    # current_node_id is set to primary — verify_entry may override it
    primary_node_id = entry_point_ranking[0]
    _log.debug("[router] primary entry node: %s", primary_node_id)

    return {
        "problem_type": problem_type,
        "entry_point_ranking": entry_point_ranking,
        "current_node_id": primary_node_id,
        # traversal_history is intentionally NOT set here — verify_entry sets it
    }

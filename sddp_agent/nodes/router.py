"""
Router node: map user query to a problem_type and set the entry node.

Uses the LLM to classify the user's question into one of the three registered
entry points from decision_graph.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from langchain_openai import ChatOpenAI
#from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..tools.graph_loader import load_graph

_PROMPT_PATH = Path(__file__).parents[1] / "prompts" / "router_prompt.txt"
_ROUTER_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


def _get_llm() -> ChatOpenAI:
    llm = ChatOpenAI(model_name="gpt-4.1",max_tokens=256, temperature=0.4)
    #return ChatAnthropic(model=os.getenv("SDDP_AGENT_MODEL", "claude-sonnet-4-6"),temperature=0,max_tokens=256,)
    return llm


def route_problem(state: dict) -> dict:
    """
    Classify user_query into a problem_type and set current_node_id.

    Reads: user_query, case_metadata, conversation_history
    Writes: problem_type, current_node_id, traversal_history
    """
    graph = load_graph()
    entry_points = graph["entry_points"]

    history_text = ""
    for msg in state.get("conversation_history", [])[-6:]:  # last 3 turns
        role = msg["role"].upper()
        history_text += f"{role}: {msg['content']}\n"

    prompt_text = _ROUTER_PROMPT.format(
        entry_points=json.dumps(entry_points, indent=2),
        case_metadata=json.dumps(state.get("case_metadata", {}), indent=2, ensure_ascii=False),
        conversation_history=history_text.strip() or "(none)",
        user_query=state["user_query"],
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt_text),
    ])

    try:
        parsed = json.loads(response.content)
        problem_type = parsed["problem_type"]
    except (json.JSONDecodeError, KeyError):
        # Fallback: default to simulation diagnosis
        problem_type = "problema_simulacao"

    root_node_id = entry_points.get(problem_type, list(entry_points.values())[0])

    return {
        "problem_type": problem_type,
        "current_node_id": root_node_id,
        "traversal_history": [root_node_id],
    }

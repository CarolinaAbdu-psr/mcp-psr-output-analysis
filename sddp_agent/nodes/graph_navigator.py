"""
Graph navigator node: traverse the decision graph one step at a time.

At each analysis node, the navigator:
  1. Retrieves outgoing edges sorted by priority.
  2. For each child (in priority order):
     a. Asks the LLM which tools are needed to test the child's hypothesis.
     b. Resolves placeholder column names to real CSV names.
     c. Calls the selected tools.
     d. Asks the LLM whether the tool results support the child's hypothesis.
     e. Follows the first child whose hypothesis holds.
  3. If no child hypothesis holds, defaults to priority-1 child.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

#from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..tools.catalog import build_catalog_summary
from ..tools.dataframe_tools import call_tool
from ..tools.graph_loader import load_graph

_PROMPTS_DIR = Path(__file__).parents[1] / "prompts"
_TOOL_SELECTOR_PROMPT = (_PROMPTS_DIR / "tool_selector_prompt.txt").read_text(encoding="utf-8")
_COLUMN_RESOLVER_PROMPT = (_PROMPTS_DIR / "column_resolver_prompt.txt").read_text(encoding="utf-8")
_EDGE_SELECTOR_PROMPT = (_PROMPTS_DIR / "edge_selector_prompt.txt").read_text(encoding="utf-8")



def _get_llm(max_tokens= 1024) -> ChatOpenAI:
    llm = ChatOpenAI(model_name="gpt-4.1",max_tokens=max_tokens, temperature=0.4)
    #return ChatAnthropic(model=os.getenv("SDDP_AGENT_MODEL", "claude-sonnet-4-6"),temperature=0,max_tokens=256,)
    return llm

# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _select_tools(
    current_node: dict,
    child_node: dict,
    prior_results: list[dict],
) -> list[dict]:
    """Ask the LLM which tools to run to test the child's hypothesis."""
    available_tools = current_node.get("tools", [])
    if not available_tools:
        return []

    prompt = _TOOL_SELECTOR_PROMPT.format(
        current_node_id=current_node["id"],
        available_tools=json.dumps(available_tools, indent=2),
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        prior_results=json.dumps(prior_results, indent=2) if prior_results else "[]",
    )

    llm = _get_llm(max_tokens=512)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])

    try:
        return json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        return []


def _resolve_params(
    tool_spec: dict,
    csv_catalog: dict,
    results_dir: str,
) -> dict:
    """Ask the LLM to replace placeholder column names with real CSV column names."""
    catalog_summary = build_catalog_summary(csv_catalog, tool_spec["name"])

    prompt = _COLUMN_RESOLVER_PROMPT.format(
        tool_name=tool_spec["name"],
        placeholder_params=json.dumps(tool_spec.get("params", {}), indent=2),
        catalog_summary=catalog_summary,
        results_dir=results_dir,
    )

    llm = _get_llm(max_tokens=512)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])

    try:
        resolved = json.loads(response.content)
        # Ensure file paths use the actual results_dir
        for key in ("file_path", "file_path_a", "file_path_b"):
            if key in resolved and not Path(resolved[key]).is_absolute():
                resolved[key] = str(Path(results_dir) / resolved[key])
        return resolved
    except (json.JSONDecodeError, TypeError):
        # Return placeholder params unchanged as fallback
        return tool_spec.get("params", {})


def _hypothesis_holds(
    child_node: dict,
    tool_results: list[dict],
) -> bool:
    """Ask the LLM whether the tool results support the child's hypothesis."""
    prompt = _EDGE_SELECTOR_PROMPT.format(
        current_node_id="(parent)",
        current_node_label="",
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        tool_results=json.dumps(tool_results, indent=2) if tool_results else "[]",
    )

    llm = _get_llm(max_tokens=256)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])

    try:
        parsed = json.loads(response.content)
        return bool(parsed.get("holds", False))
    except (json.JSONDecodeError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def execute_graph_node(state: dict) -> dict:
    """
    Process one analysis node: select tools, run them, choose next edge.

    Reads: current_node_id, csv_catalog, results_dir, tool_results, traversal_history
    Writes: current_node_id (next), tool_results (appended), traversal_history (appended)
    """
    graph = load_graph()
    current_node = graph["nodes_by_id"].get(state["current_node_id"])

    if current_node is None:
        return {"error": f"Node not found: {state['current_node_id']}"}

    outgoing_edges = graph["adjacency"].get(current_node["id"], [])
    if not outgoing_edges:
        # Leaf with no edges — treat as conclusion
        return {
            "current_node_id": current_node["id"],
            "tool_results": state.get("tool_results", []),
            "traversal_history": state.get("traversal_history", []),
        }

    csv_catalog: dict = state.get("csv_catalog", {})
    results_dir: str = state.get("results_dir", "")
    all_node_results: list[dict] = []
    selected_next_id: str | None = None

    for edge in outgoing_edges:  # already sorted by priority ascending
        child = graph["nodes_by_id"].get(edge["target"])
        if child is None:
            continue

        # 1. Decide which tools are needed for this child's hypothesis
        tools_to_run = _select_tools(current_node, child, all_node_results)

        # 2. Resolve column names and execute
        edge_results: list[dict] = []
        for tool_spec in tools_to_run:
            resolved = _resolve_params(tool_spec, csv_catalog, results_dir)
            result = call_tool(tool_spec["name"], resolved)
            edge_results.append({
                "tool_name": tool_spec["name"],
                "params": resolved,
                "result": result,
            })

        all_node_results.extend(edge_results)

        # 3. Evaluate hypothesis
        if _hypothesis_holds(child, edge_results):
            selected_next_id = child["id"]
            break

    # Fallback to priority-1 child if nothing confirmed
    if selected_next_id is None:
        selected_next_id = outgoing_edges[0]["target"]

    updated_results = list(state.get("tool_results", [])) + [{
        "node_id": current_node["id"],
        "results": all_node_results,
    }]
    updated_history = list(state.get("traversal_history", [])) + [selected_next_id]

    return {
        "current_node_id": selected_next_id,
        "tool_results": updated_results,
        "traversal_history": updated_history,
    }

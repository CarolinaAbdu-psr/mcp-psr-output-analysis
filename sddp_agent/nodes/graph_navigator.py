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
import textwrap
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..tools.catalog import build_catalog_summary
from ..tools.dataframe_tools import call_tool
from ..tools.graph_loader import load_graph
from ..utils import get_logger, safe_json_loads

_log = get_logger("navigator")

_PROMPTS_DIR = Path(__file__).parents[1] / "prompts"
_TOOL_SELECTOR_PROMPT   = (_PROMPTS_DIR / "tool_selector_prompt.txt").read_text(encoding="utf-8")
_COLUMN_RESOLVER_PROMPT = (_PROMPTS_DIR / "column_resolver_prompt.txt").read_text(encoding="utf-8")
_EDGE_SELECTOR_PROMPT   = (_PROMPTS_DIR / "edge_selector_prompt.txt").read_text(encoding="utf-8")


def _get_llm(max_tokens: int = 1024) -> ChatOpenAI:
    return ChatOpenAI(model_name="gpt-4.1", max_tokens=max_tokens, temperature=0.4)


def _short(text: str, n: int = 300) -> str:
    """Truncate long strings for readable debug output."""
    s = str(text)
    return s if len(s) <= n else s[:n] + f"… [{len(s)-n} more chars]"


# ---------------------------------------------------------------------------
# LLM helpers
# ---------------------------------------------------------------------------

def _select_tools(
    child_node: dict,
    prior_results: list[dict],
    parent_node_id: str = "",
) -> list[dict]:
    """
    Ask the LLM which tools (subset of child_node["tools"]) to run
    in order to test the child's hypothesis.

    The tools come from the CHILD node — each node defines the tools needed
    to verify its own hypothesis. The LLM selects the minimal subset.

    Returns a list of tool specs (same format as the graph JSON tools[]).
    Returns [] when no tools are needed or the child has no tools defined.
    """
    available_tools = child_node.get("tools", [])
    if not available_tools:
        _log.debug("  [select_tools] child %s has no tools — hypothesis will use case_metadata", child_node["id"])
        return []

    prompt = _TOOL_SELECTOR_PROMPT.format(
        current_node_id=parent_node_id or "(parent)",
        available_tools=json.dumps(available_tools, indent=2),
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        prior_results=json.dumps(prior_results, indent=2) if prior_results else "[]",
    )

    _log.debug(
        "  [select_tools] testing child %s (tools from child node)\n  prompt:\n%s",
        child_node["id"],
        textwrap.indent(_short(prompt), "    "),
    )

    llm = _get_llm(max_tokens=512)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    raw = response.content

    _log.debug("  [select_tools] raw LLM response:\n%s", textwrap.indent(_short(raw), "    "))

    try:
        tools = safe_json_loads(raw, context="select_tools")
        if not isinstance(tools, list):
            _log.warning("  [select_tools] expected list, got %s — using []", type(tools).__name__)
            return []
        _log.debug("  [select_tools] selected %d tool(s): %s", len(tools), [t.get("name") for t in tools])
        return tools
    except json.JSONDecodeError as exc:
        _log.warning("  [select_tools] JSON parse error: %s — running no tools", exc)
        return []


def _resolve_params(
    tool_spec: dict,
    csv_catalog: dict,
    results_dir: str,
) -> dict | None:
    """
    Ask the LLM to replace placeholder column names with real CSV column names
    and set the correct file_path.

    Returns the resolved params dict, or None if resolution failed.
    """
    catalog_summary = build_catalog_summary(csv_catalog, tool_spec["name"])

    prompt = _COLUMN_RESOLVER_PROMPT.format(
        tool_name=tool_spec["name"],
        placeholder_params=json.dumps(tool_spec.get("params", {}), indent=2),
        catalog_summary=catalog_summary,
        results_dir=results_dir,
    )

    _log.debug(
        "  [resolve_params] tool=%s\n  placeholder params: %s\n  prompt:\n%s",
        tool_spec["name"],
        json.dumps(tool_spec.get("params", {})),
        textwrap.indent(_short(prompt, 400), "    "),
    )

    llm = _get_llm(max_tokens=512)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    raw = response.content

    _log.debug("  [resolve_params] raw LLM response:\n%s", textwrap.indent(_short(raw), "    "))

    try:
        resolved = safe_json_loads(raw, context="resolve_params")
        if not isinstance(resolved, dict):
            _log.warning("  [resolve_params] expected dict, got %s", type(resolved).__name__)
            return None

        # Ensure file paths are absolute
        for key in ("file_path", "file_path_a", "file_path_b", "file_path_max"):
            if key in resolved:
                p = resolved[key]
                if not Path(str(p)).is_absolute():
                    resolved[key] = str(Path(results_dir) / p)
                # Verify the file actually exists
                if not Path(resolved[key]).exists():
                    _log.warning(
                        "  [resolve_params] %s=%r does not exist — trying catalog match",
                        key, resolved[key],
                    )
                    # Try fuzzy-match from catalog (use first file whose name appears in the path)
                    fname = Path(resolved[key]).name
                    matched = next(
                        (f for f in csv_catalog if fname.lower() in f.lower() or f.lower() in fname.lower()),
                        None,
                    )
                    if matched:
                        resolved[key] = str(Path(results_dir) / matched)
                        _log.debug("  [resolve_params] corrected to %r", resolved[key])

        _log.debug("  [resolve_params] resolved params: %s", json.dumps(resolved, ensure_ascii=False))
        return resolved

    except json.JSONDecodeError as exc:
        _log.warning("  [resolve_params] JSON parse error: %s — skipping this tool", exc)
        return None


def _hypothesis_holds(
    child_node: dict,
    tool_results: list[dict],
    case_metadata: dict | None = None,
) -> bool:
    """
    Ask the LLM whether the tool results (or case metadata, when no tools ran)
    support the child node's expected_state.
    Returns False on any parse error.
    """
    meta_text = (
        json.dumps(case_metadata, indent=2, ensure_ascii=False)
        if case_metadata
        else "(not available)"
    )
    prompt = _EDGE_SELECTOR_PROMPT.format(
        current_node_id="(parent)",
        current_node_label="",
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        case_metadata=meta_text,
        tool_results=json.dumps(tool_results, indent=2) if tool_results else "[]",
    )

    _log.debug(
        "  [hypothesis] evaluating child %s (%s)",
        child_node["id"],
        child_node.get("label", ""),
    )

    llm = _get_llm(max_tokens=256)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    raw = response.content

    _log.debug("  [hypothesis] raw LLM response: %s", _short(raw, 200))

    try:
        parsed = safe_json_loads(raw, context="hypothesis")
        holds = bool(parsed.get("holds", False))
        reasoning = parsed.get("reasoning", "")
        _log.debug("  [hypothesis] holds=%s  reason: %s", holds, reasoning)
        return holds
    except json.JSONDecodeError as exc:
        _log.warning("  [hypothesis] JSON parse error: %s — assuming False", exc)
        return False


# ---------------------------------------------------------------------------
# Main node function
# ---------------------------------------------------------------------------

def execute_graph_node(state: dict) -> dict:
    """
    Process one analysis node: select tools, run them, choose next edge.

    Reads:  current_node_id, csv_catalog, results_dir, tool_results, traversal_history
    Writes: current_node_id (next), tool_results (appended), traversal_history (appended)
    """
    graph = load_graph()
    current_node = graph["nodes_by_id"].get(state["current_node_id"])

    if current_node is None:
        _log.error("Node not found: %s", state["current_node_id"])
        return {"error": f"Node not found: {state['current_node_id']}"}

    _log.debug(
        "\n══ NODE: %s  [%s] ══\n  %s",
        current_node["id"],
        current_node.get("type", "?"),
        current_node.get("purpose", ""),
    )

    outgoing_edges = graph["adjacency"].get(current_node["id"], [])
    if not outgoing_edges:
        # Leaf with no edges — treat as conclusion
        _log.debug("  No outgoing edges — treating as conclusion leaf")
        return {
            "current_node_id": current_node["id"],
            "tool_results": state.get("tool_results", []),
            "traversal_history": state.get("traversal_history", []),
        }

    csv_catalog: dict   = state.get("csv_catalog", {})
    results_dir: str    = state.get("results_dir", "")
    case_metadata: dict = state.get("case_metadata", {})
    all_node_results: list[dict] = []
    selected_next_id: str | None = None

    _log.debug(
        "  %d outgoing edges: %s",
        len(outgoing_edges),
        [(e["target"], f"p={e.get('priority','?')}") for e in outgoing_edges],
    )

    for edge in outgoing_edges:  # already sorted by priority ascending
        child = graph["nodes_by_id"].get(edge["target"])
        if child is None:
            _log.warning("  Edge target not found: %s", edge["target"])
            continue

        _log.debug(
            "\n  ─ Testing child [priority=%s]: %s ─",
            edge.get("priority", "?"),
            child["id"],
        )

        # 1. Decide which tools (from the CHILD node) to run to test the child's hypothesis
        tools_to_run = _select_tools(child, all_node_results, parent_node_id=current_node["id"])

        if not tools_to_run:
            _log.debug(
                "  No tools selected for this child — hypothesis will be evaluated from case_metadata"
            )

        # 2. Resolve column names and execute each selected tool
        edge_results: list[dict] = []
        for tool_spec in tools_to_run:
            resolved = _resolve_params(tool_spec, csv_catalog, results_dir)

            if resolved is None:
                _log.warning(
                    "  [tool] %s — param resolution failed, skipping",
                    tool_spec["name"],
                )
                edge_results.append({
                    "tool_name": tool_spec["name"],
                    "params": tool_spec.get("params", {}),
                    "result": {"error": "Parameter resolution failed (could not parse LLM response)"},
                })
                continue

            _log.debug("  [tool] calling %s", tool_spec["name"])
            result = call_tool(tool_spec["name"], resolved)

            if "error" in result:
                _log.warning("  [tool] %s returned error: %s", tool_spec["name"], result["error"])
            else:
                _log.debug("  [tool] %s succeeded — keys: %s", tool_spec["name"], list(result.keys()))

            edge_results.append({
                "tool_name": tool_spec["name"],
                "params": resolved,
                "result": result,
            })

        all_node_results.extend(edge_results)

        # 3. Evaluate whether this child's hypothesis holds
        #    Pass case_metadata so the LLM can reason even when no tools were run
        if _hypothesis_holds(child, edge_results, case_metadata=case_metadata):
            selected_next_id = child["id"]
            _log.debug("  → FOLLOWING edge to: %s", selected_next_id)
            break

    # Fallback to priority-1 child when no hypothesis confirmed
    if selected_next_id is None:
        selected_next_id = outgoing_edges[0]["target"]
        _log.debug(
            "  No hypothesis confirmed → defaulting to priority-1 child: %s",
            selected_next_id,
        )

    updated_results = list(state.get("tool_results", [])) + [{
        "node_id": current_node["id"],
        "results": all_node_results,
    }]
    updated_history = list(state.get("traversal_history", [])) + [selected_next_id]

    _log.debug("  Traversal path so far: %s", " → ".join(updated_history))

    return {
        "current_node_id": selected_next_id,
        "tool_results": updated_results,
        "traversal_history": updated_history,
    }

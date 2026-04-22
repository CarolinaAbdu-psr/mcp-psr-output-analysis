"""
Graph navigator node: traverse the decision graph one step at a time.

At each analysis node, the navigator:
  1. Retrieves outgoing edges sorted by priority.
  2. For each child (in priority order):
     a. Asks the LLM which tools to run AND resolves their parameters — one call.
     b. Calls the selected tools with the resolved parameters.
     c. Asks the LLM whether the tool results support the child's hypothesis.
     d. Follows the first child whose hypothesis holds.
  3. If no child hypothesis holds, defaults to priority-1 child.

LLM calls per edge:
  - _select_and_resolve_tools : select tools + resolve file/column params (merged, 1 call)
  - _hypothesis_holds         : evaluate if results confirm the child's expected_state (1 call)
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..tools.catalog import build_catalog_summary
from ..tools.dataframe_tools import call_tool
from ..tools.graph_loader import load_graph
from ..utils import get_logger, safe_json_loads

_log = get_logger("navigator")

_PROMPTS_DIR = Path(__file__).parents[1] / "prompts"
_TOOL_SELECTOR_RESOLVER_PROMPT = (_PROMPTS_DIR / "tool_selector_resolver_prompt.txt").read_text(encoding="utf-8")
_EDGE_SELECTOR_PROMPT          = (_PROMPTS_DIR / "edge_selector_prompt.txt").read_text(encoding="utf-8")


def _get_llm(max_tokens: int = 1024) -> ChatAnthropic:
    import os
    model = os.environ.get("SDDP_AGENT_MODEL", "claude-sonnet-4-6")
    return ChatAnthropic(model=model, max_tokens=max_tokens, temperature=0.4)  # type: ignore[call-arg]


def _short(text: str, n: int = 300) -> str:
    s = str(text)
    return s if len(s) <= n else s[:n] + f"… [{len(s)-n} more chars]"


# ---------------------------------------------------------------------------
# Post-resolution validation (file existence + fuzzy catalog fallback)
# ---------------------------------------------------------------------------

def _validate_file_params(resolved: dict, csv_catalog: dict, results_dir: str) -> dict:
    """
    Make file paths absolute and verify they exist.
    Falls back to a fuzzy catalog match when a file is not found.
    """
    for key in ("file_path", "file_path_a", "file_path_b", "file_path_max"):
        if key not in resolved:
            continue
        p = resolved[key]
        if not Path(str(p)).is_absolute():
            resolved[key] = str(Path(results_dir) / p)
        if not Path(resolved[key]).exists():
            _log.warning("  [validate] %s=%r not found — trying catalog match", key, resolved[key])
            fname = Path(resolved[key]).name
            matched = next(
                (f for f in csv_catalog if fname.lower() in f.lower() or f.lower() in fname.lower()),
                None,
            )
            if matched:
                resolved[key] = str(Path(results_dir) / matched)
                _log.debug("  [validate] corrected to %r", resolved[key])
    return resolved


# ---------------------------------------------------------------------------
# Merged: select tools + resolve params — one LLM call per edge
# ---------------------------------------------------------------------------

def _select_and_resolve_tools(
    child_node: dict,
    prior_results: list[dict],
    csv_catalog: dict,
    results_dir: str,
    case_metadata: dict,
    parent_node_id: str = "",
) -> list[dict]:
    """
    Single LLM call that selects which tools to run AND returns them with
    fully-resolved parameters (real file paths, real column names).

    Returns a list of tool specs ready for call_tool():
        [{"name": "df_analyze_bounds", "params": {"file_path": "...", "target_col": "Zinf", ...}}]
    Returns [] when no tools are needed.
    """
    available_tools = child_node.get("tools", [])
    if not available_tools:
        _log.debug(
            "  [select_resolve] child %s has no tools — hypothesis will use case_metadata",
            child_node["id"],
        )
        return []

    catalog_summary = build_catalog_summary(csv_catalog)

    prompt = _TOOL_SELECTOR_RESOLVER_PROMPT.format(
        current_node_id=parent_node_id or "(parent)",
        case_metadata=json.dumps(case_metadata, indent=2, ensure_ascii=False),
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        available_tools=json.dumps(available_tools, indent=2),
        prior_results=json.dumps(prior_results, indent=2) if prior_results else "[]",
        catalog_summary=catalog_summary,
        results_dir=results_dir,
    )

    _log.debug(
        "  [select_resolve] testing child %s\n  prompt:\n%s",
        child_node["id"],
        textwrap.indent(_short(prompt, 500), "    "),
    )

    llm = _get_llm(max_tokens=1024)
    response = llm.invoke([SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)])
    raw = response.content

    _log.debug("  [select_resolve] raw LLM response:\n%s", textwrap.indent(_short(raw), "    "))

    try:
        tools = safe_json_loads(raw, context="select_resolve")
        if not isinstance(tools, list):
            _log.warning("  [select_resolve] expected list, got %s — using []", type(tools).__name__)
            return []

        # Validate and fix file paths
        resolved_tools = []
        for tool_spec in tools:
            if not isinstance(tool_spec, dict) or "name" not in tool_spec:
                continue
            params = tool_spec.get("params", {})
            params = _validate_file_params(params, csv_catalog, results_dir)
            resolved_tools.append({"name": tool_spec["name"], "params": params})

        _log.debug(
            "  [select_resolve] %d tool(s) selected: %s",
            len(resolved_tools),
            [t["name"] for t in resolved_tools],
        )
        return resolved_tools

    except json.JSONDecodeError as exc:
        _log.warning("  [select_resolve] JSON parse error: %s — running no tools", exc)
        return []


# ---------------------------------------------------------------------------
# Hypothesis evaluation
# ---------------------------------------------------------------------------

def _hypothesis_holds(
    child_node: dict,
    tool_results: list[dict],
    case_metadata: dict | None = None,
    csv_catalog: dict | None = None,
) -> bool:
    """
    Ask the LLM whether the tool results (and case_metadata) support the
    child node's expected_state. Returns False on any parse error.
    """
    meta_text = (
        json.dumps(case_metadata, indent=2, ensure_ascii=False)
        if case_metadata
        else "(not available)"
    )
    catalog_text = build_catalog_summary(csv_catalog) if csv_catalog else "(not available)"

    prompt = _EDGE_SELECTOR_PROMPT.format(
        current_node_id="(parent)",
        current_node_label="",
        child_node_id=child_node["id"],
        child_node_label=child_node.get("label", ""),
        child_expected_state=child_node.get("content", {}).get("expected_state", ""),
        child_description=child_node.get("content", {}).get("description", ""),
        case_metadata=meta_text,
        catalog_summary=catalog_text,
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
    Process one analysis node: select + resolve tools (1 LLM call), run them,
    evaluate each child hypothesis (1 LLM call per edge), choose next edge.

    Reads:  current_node_id, csv_catalog, results_dir, case_metadata,
            tool_results, traversal_history
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

        # 1. Select tools + resolve params — single LLM call
        tools_to_run = _select_and_resolve_tools(
            child,
            prior_results=all_node_results,
            csv_catalog=csv_catalog,
            results_dir=results_dir,
            case_metadata=case_metadata,
            parent_node_id=current_node["id"],
        )

        if not tools_to_run:
            _log.debug("  No tools selected — hypothesis evaluated from case_metadata")

        # 2. Execute each selected tool
        edge_results: list[dict] = []
        for tool_spec in tools_to_run:
            _log.debug("  [tool] calling %s", tool_spec["name"])
            result = call_tool(tool_spec["name"], tool_spec["params"])

            if "error" in result:
                _log.warning("  [tool] %s returned error: %s", tool_spec["name"], result["error"])
            else:
                _log.debug("  [tool] %s succeeded — keys: %s", tool_spec["name"], list(result.keys()))

            edge_results.append({
                "tool_name": tool_spec["name"],
                "params": tool_spec["params"],
                "result": result,
            })

        all_node_results.extend(edge_results)

        # 3. Evaluate whether this child's hypothesis holds
        if _hypothesis_holds(child, edge_results, case_metadata=case_metadata, csv_catalog=csv_catalog):
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

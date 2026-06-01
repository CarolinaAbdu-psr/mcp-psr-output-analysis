"""
Verify-entry node: confirm the selected entry point by running its own tools.

The router ranks entry points by LLM similarity. This node runs each entry point's
tools (in ranked order) and follows the first one whose hypothesis is confirmed.
If none confirm, it falls back to the top-ranked entry point.

Unlike the normal traversal (which tests CHILDREN with their tools), this node
tests the ENTRY POINTS THEMSELVES — they have not been confirmed yet.

Parameter resolution (file_path, column names) is delegated to
_select_and_resolve_tools, which makes one LLM call per entry point to map
placeholder params to real catalog paths and column names — the same mechanism
used by graph_navigator for child nodes.
"""
from __future__ import annotations

from ..tools.dataframe_tools import call_tool
from ..tools.graph_loader import load_graph
from ..utils import get_logger

# Reuse hypothesis testing and full LLM-based param resolution from graph_navigator
from .graph_navigator import _hypothesis_holds, _select_and_resolve_tools

_log = get_logger("verify_entry")


def verify_entry_point(state: dict) -> dict:
    """
    Run each entry point's own tools to confirm it matches the user's problem.

    Reads:  entry_point_ranking, csv_catalog, results_dir, case_metadata
    Writes: current_node_id (verified entry), traversal_history, tool_results (entry verification)
    """
    ranking: list[str] = state.get("entry_point_ranking", [])
    graph = load_graph()

    if not ranking:
        # Fallback: honour whatever the router set
        current = state.get("current_node_id", "")
        _log.warning("[verify_entry] no ranking received — using current_node_id: %s", current)
        return {"traversal_history": [current] if current else []}

    case_metadata: dict = state.get("case_metadata", {})
    csv_catalog: dict = state.get("csv_catalog", {})
    results_dir: str = state.get("results_dir", "")

    _log.debug("[verify_entry] evaluating %d candidate entry points: %s", len(ranking), ranking)

    all_verification_results: list[dict] = []

    for entry_id in ranking:
        entry_node = graph["nodes_by_id"].get(entry_id)
        if entry_node is None:
            _log.warning("[verify_entry] entry node not found: %s — skipping", entry_id)
            continue

        tools_list: list[dict] = entry_node.get("tools", [])
        _log.debug(
            "\n  ─ Testing entry [%s] tools=%s ─",
            entry_id,
            [t["name"] for t in tools_list],
        )

        # Use the same LLM-based resolution as graph_navigator:
        # pass the entry node as "child_node" so the LLM resolves file_path
        # and column names from the catalog before we call the tools.
        resolved_tools = _select_and_resolve_tools(
            child_node=entry_node,
            csv_catalog=csv_catalog,
            results_dir=results_dir,
            prior_results=None,
            parent_node_id="(entry-verification)",
            case_metadata=case_metadata,
        )

        entry_results: list[dict] = []
        for tool_spec in resolved_tools:
            _log.debug("  [verify_entry] calling %s", tool_spec["name"])
            result = call_tool(tool_spec["name"], tool_spec["params"])

            if "error" in result:
                _log.warning(
                    "  [verify_entry] %s returned error: %s",
                    tool_spec["name"],
                    result["error"],
                )
            else:
                _log.debug(
                    "  [verify_entry] %s succeeded — keys: %s",
                    tool_spec["name"],
                    list(result.keys()),
                )

            entry_results.append({
                "tool_name": tool_spec["name"],
                "params": tool_spec["params"],
                "result": result,
            })

        all_verification_results.extend(entry_results)

        # Evaluate: does the data (or case_metadata for no-tool nodes) support this entry?
        if _hypothesis_holds(entry_node, entry_results, case_metadata=case_metadata, csv_catalog=csv_catalog):
            _log.debug("[verify_entry] ✓ entry point confirmed: %s", entry_id)
            return {
                "current_node_id": entry_id,
                "traversal_history": [entry_id],
                "tool_results": _wrap_verification_results(all_verification_results),
            }

        _log.debug("[verify_entry] ✗ entry point not confirmed: %s", entry_id)

    # No entry point was confirmed — fall back to top-ranked
    selected = ranking[0]
    _log.debug("[verify_entry] no entry confirmed → defaulting to top-ranked: %s", selected)
    return {
        "current_node_id": selected,
        "traversal_history": [selected],
        "tool_results": _wrap_verification_results(all_verification_results),
    }


def _wrap_verification_results(results: list[dict]) -> list[dict]:
    """Package verification results in the standard tool_results format."""
    if not results:
        return []
    return [{"node_id": "(entry-verification)", "results": results}]

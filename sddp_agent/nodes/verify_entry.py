"""
Verify-entry node: confirm the selected entry point by running its own tools.

The router ranks entry points by LLM similarity. This node runs each entry point's
tools (in ranked order) and follows the first one whose hypothesis is confirmed.
If none confirm, it falls back to the top-ranked entry point.

Unlike the normal traversal (which tests CHILDREN with their tools), this node
tests the ENTRY POINTS THEMSELVES — they have not been confirmed yet.
"""
from __future__ import annotations

import json

from ..tools.dataframe_tools import call_tool
from ..tools.graph_loader import load_graph
from ..utils import get_logger

# Reuse hypothesis testing and parameter resolution from graph_navigator
from .graph_navigator import _hypothesis_holds, _resolve_params

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

        # Run ALL tools for this entry point (no LLM sub-selection — verify fully)
        entry_results: list[dict] = []
        for tool_spec in tools_list:
            resolved = _resolve_params(tool_spec, csv_catalog, results_dir)
            if resolved is None:
                _log.warning("  [verify_entry] param resolution failed for %s", tool_spec["name"])
                entry_results.append({
                    "tool_name": tool_spec["name"],
                    "params": tool_spec.get("params", {}),
                    "result": {"error": "Parameter resolution failed"},
                })
                continue

            _log.debug("  [verify_entry] calling %s", tool_spec["name"])
            result = call_tool(tool_spec["name"], resolved)

            if "error" in result:
                _log.warning("  [verify_entry] %s returned error: %s", tool_spec["name"], result["error"])
            else:
                _log.debug("  [verify_entry] %s succeeded — keys: %s", tool_spec["name"], list(result.keys()))

            entry_results.append({
                "tool_name": tool_spec["name"],
                "params": resolved,
                "result": result,
            })

        all_verification_results.extend(entry_results)

        # Evaluate: does the data (or case_metadata for no-tool nodes) support this entry?
        if _hypothesis_holds(entry_node, entry_results, case_metadata=case_metadata):
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

"""
Node-level test harness for the SDDP decision-graph workflow.

Tests graph structure, each tool, and graph traversal — all WITHOUT LLM calls.
Synthetic CSV data is written to temp files; no real SDDP case is required.

Run from the repo root:
    python tests/test_workflow_nodes.py              # all tests
    python tests/test_workflow_nodes.py bounds       # substring match
    python tests/test_workflow_nodes.py graph tool   # multiple filters
"""
from __future__ import annotations

import json
import sys
import tempfile
import textwrap
from pathlib import Path
from typing import Callable

# Force UTF-8 output on Windows (avoids cp1252 encode errors from Portuguese/special chars)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT))

# ── Test registry ─────────────────────────────────────────────────────────────

TESTS: dict[str, Callable] = {}


def test(name: str):
    def decorator(fn):
        TESTS[name] = fn
        return fn
    return decorator


# ── Display helpers ───────────────────────────────────────────────────────────

def _sep(title: str) -> None:
    print(f"\n{'-' * 72}")
    print(f"  TEST: {title}")
    print(f"{'-' * 72}")


def _show(obj) -> None:
    s = json.dumps(obj, indent=2, default=str) if isinstance(obj, (dict, list)) else str(obj)
    preview = s[:600] + ("…" if len(s) > 600 else "")
    print(textwrap.indent(preview, "  "))


# ── CSV fixture helpers ───────────────────────────────────────────────────────

def _tmp_csv(df: "pd.DataFrame") -> Path:
    """Write a DataFrame to a temporary CSV file; caller cleans up."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline="", encoding="utf-8"
    )
    df.to_csv(f, index=False)
    f.close()
    return Path(f.name)


def _cleanup(*paths: Path) -> None:
    for p in paths:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


# ── Import helpers ────────────────────────────────────────────────────────────

def _import_tools():
    try:
        from sddp_agent.tools.dataframe_tools import call_tool, TOOL_DISPATCH
        return call_tool, TOOL_DISPATCH
    except Exception as exc:
        print(f"  [SKIP] Cannot import dataframe_tools: {exc}")
        return None, None


def _load_graph():
    try:
        from sddp_agent.tools.graph_loader import load_graph
        return load_graph()
    except Exception as exc:
        print(f"  [SKIP] Cannot load decision graph: {exc}")
        return None


# =============================================================================
# GROUP 1 — Graph structure integrity
# =============================================================================

@test("graph_loads")
def test_graph_loads():
    _sep("Decision graph loads without error")
    graph = _load_graph()
    assert graph is not None, "load_graph() returned None"
    nodes = graph.get("nodes_by_id", {})
    entry = graph.get("entry_points", {})
    print(f"  nodes        : {len(nodes)}")
    print(f"  entry points : {list(entry.keys())}")
    print(f"  edge sources : {len(graph.get('adjacency', {}))}")
    assert len(nodes) > 0, "No nodes found in graph"
    assert len(entry) > 0, "No entry points found"
    print("\n  [OK] Graph loaded.")


@test("graph_entry_points_valid")
def test_graph_entry_points_valid():
    _sep("All entry points reference valid node IDs")
    graph = _load_graph()
    if graph is None:
        return
    nodes = graph["nodes_by_id"]
    for key, node_id in graph["entry_points"].items():
        assert node_id in nodes, f"Entry point {key!r} → {node_id!r} not found"
        ntype = nodes[node_id].get("type", "?")
        print(f"  OK  {key:40s} -> {node_id}  [{ntype}]")
    print("\n  [OK] All entry points valid.")


@test("graph_edge_targets_valid")
def test_graph_edge_targets_valid():
    _sep("All graph edges point to existing node IDs")
    graph = _load_graph()
    if graph is None:
        return
    nodes = graph["nodes_by_id"]
    broken = []
    for src, edges in graph["adjacency"].items():
        for edge in edges:
            tgt = edge["target"]
            if tgt not in nodes:
                broken.append(f"{src} → {tgt}")
    if broken:
        for b in broken:
            print(f"  FAIL  {b}")
        assert False, f"{len(broken)} broken edge(s) found"
    total_edges = sum(len(e) for e in graph["adjacency"].values())
    print(f"  {total_edges} edges across {len(graph['adjacency'])} source nodes — all targets valid.")
    print("\n  [OK] Edge integrity confirmed.")


@test("graph_tools_registered")
def test_graph_tools_registered():
    _sep("Every tool referenced in the graph exists in TOOL_DISPATCH")
    graph = _load_graph()
    _, TOOL_DISPATCH = _import_tools()
    if graph is None or TOOL_DISPATCH is None:
        return
    unknown: list[str] = []
    seen: set[str] = set()
    for node in graph["nodes_by_id"].values():
        for tool in node.get("tools", []):
            name = tool["name"]
            seen.add(name)
            if name not in TOOL_DISPATCH:
                unknown.append(f"  node {node['id']!r}: {name!r}")
    print(f"  Unique tool names in graph: {sorted(seen)}")
    if unknown:
        for u in unknown:
            print(u)
        assert False, f"{len(unknown)} unregistered tool(s)"
    print("\n  [OK] All tool names match TOOL_DISPATCH.")


@test("graph_node_types")
def test_graph_node_types():
    _sep("All nodes have a valid type (analysis | conclusion)")
    graph = _load_graph()
    if graph is None:
        return
    invalid = []
    counts: dict[str, int] = {}
    for node in graph["nodes_by_id"].values():
        t = node.get("type")
        counts[t] = counts.get(t, 0) + 1
        if t not in ("analysis", "conclusion"):
            invalid.append(f"  {node['id']!r}: type={t!r}")
    for t, n in sorted(counts.items()):
        print(f"  {t:15s}: {n} node(s)")
    if invalid:
        for i in invalid:
            print(i)
        assert False, f"{len(invalid)} node(s) with invalid type"
    print("\n  [OK] All node types valid.")


# =============================================================================
# GROUP 2 — Individual tool execution with synthetic CSV data
# =============================================================================

@test("tool_analyze_bounds_not_converged")
def test_tool_analyze_bounds_not_converged():
    import pandas as pd
    _sep("df_analyze_bounds — Zinf outside CI band (not converged)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    n, zsup = 20, 1000.0
    df = pd.DataFrame({
        "Iteration": range(1, n + 1),
        "Zinf":      [700.0] * n,          # flat, far below band
        "Zsup":      [zsup] * n,
        "Lower_CI":  [zsup - 20] * n,
        "Upper_CI":  [zsup + 20] * n,
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_bounds", {
            "file_path":         str(p),
            "target_col":        "Zinf",
            "lower_bound_col":   "Lower_CI",
            "upper_bound_col":   "Upper_CI",
            "reference_val_col": "Zsup",
            "iteration_col":     "Iteration",
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["bounds_status"]["converged"] is False, "Expected not converged"
        print("\n  [OK] Not converged as expected.")
    finally:
        _cleanup(p)


@test("tool_analyze_bounds_converged")
def test_tool_analyze_bounds_converged():
    import pandas as pd
    _sep("df_analyze_bounds — Zinf inside CI band (converged)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    n, zsup = 20, 1000.0
    df = pd.DataFrame({
        "Iteration": range(1, n + 1),
        "Zinf":      [zsup - 10.0] * n,   # inside [980, 1020]
        "Zsup":      [zsup] * n,
        "Lower_CI":  [zsup - 20] * n,
        "Upper_CI":  [zsup + 20] * n,
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_bounds", {
            "file_path":         str(p),
            "target_col":        "Zinf",
            "lower_bound_col":   "Lower_CI",
            "upper_bound_col":   "Upper_CI",
            "reference_val_col": "Zsup",
            "iteration_col":     "Iteration",
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["bounds_status"]["converged"] is True, "Expected converged"
        print("\n  [OK] Converged as expected.")
    finally:
        _cleanup(p)


@test("tool_analyze_stagnation_flat")
def test_tool_analyze_stagnation_flat():
    import pandas as pd
    _sep("df_analyze_stagnation — flat series (Stagnated)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({"Zinf": [500.0] * 20})
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_stagnation", {
            "file_path":  str(p),
            "target_col": "Zinf",
            "window_size": 5,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["stagnation_results"]["status"] == "Stagnated"
        print("\n  [OK] Stagnation detected for flat series.")
    finally:
        _cleanup(p)


@test("tool_analyze_stagnation_active")
def test_tool_analyze_stagnation_active():
    import pandas as pd
    _sep("df_analyze_stagnation — improving series (Active)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({"Zinf": [float(i * 15) for i in range(20)]})
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_stagnation", {
            "file_path":  str(p),
            "target_col": "Zinf",
            "window_size": 5,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["stagnation_results"]["status"] == "Active"
        print("\n  [OK] Active (not stagnated) for improving series.")
    finally:
        _cleanup(p)


@test("tool_analyze_composition_penalty_high")
def test_tool_analyze_composition_penalty_high():
    import pandas as pd
    _sep("df_analyze_composition — penalties dominate (op < 80 %)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage":          list(range(1, 6)),
        "Operating_Cost": [50.0] * 5,
        "Penalty_Cost":   [50.0] * 5,   # 50 % each → all critical
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_composition", {
            "file_path":           str(p),
            "target_cost_col":     "Operating_Cost",
            "all_cost_cols_json":  '["Operating_Cost","Penalty_Cost"]',
            "label_col":           "Stage",
            "min_threshold":       80.0,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["criticality_report"]["total_critical_found"] == 5
        print("\n  [OK] All 5 stages flagged as critical.")
    finally:
        _cleanup(p)


@test("tool_analyze_composition_normal")
def test_tool_analyze_composition_normal():
    import pandas as pd
    _sep("df_analyze_composition — healthy distribution (op > 80 %)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage":          list(range(1, 6)),
        "Operating_Cost": [90.0] * 5,
        "Penalty_Cost":   [10.0] * 5,   # 90 % operating → no critical
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_composition", {
            "file_path":           str(p),
            "target_cost_col":     "Operating_Cost",
            "all_cost_cols_json":  '["Operating_Cost","Penalty_Cost"]',
            "label_col":           "Stage",
            "min_threshold":       80.0,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        assert result["criticality_report"]["total_critical_found"] == 0
        print("\n  [OK] No stages flagged (healthy cost distribution).")
    finally:
        _cleanup(p)


@test("tool_analyze_heatmap_threshold")
def test_tool_analyze_heatmap_threshold():
    import pandas as pd
    _sep("df_analyze_heatmap — threshold mode")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage":   [1, 2, 3, 4, 5],
        "Agent_A": [5.0, 25.0, 10.0, 35.0, 8.0],
        "Agent_B": [1.0, 2.0,  3.0,  4.0,  5.0],
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_heatmap", {
            "file_path": str(p),
            "mode":      "threshold",
            "label_col": "Stage",
            "threshold": 20.0,
            "top_n":     5,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] Heatmap threshold mode returned valid result.")
    finally:
        _cleanup(p)


@test("tool_filter_above_threshold")
def test_tool_filter_above_threshold():
    import pandas as pd
    _sep("df_filter_above_threshold — filter high values")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage": [1, 2, 3, 4, 5],
        "Cost":  [10.0, 50.0, 5.0, 80.0, 15.0],
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_filter_above_threshold", {
            "file_path": str(p),
            "threshold": 20.0,
            "label_col": "Stage",
            "direction": "above",
            "top_n":     5,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] Filter above threshold returned valid result.")
    finally:
        _cleanup(p)


@test("tool_analyze_violation_frequency")
def test_tool_analyze_violation_frequency():
    import pandas as pd
    _sep("df_analyze_violation — frequency mode")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage": [1, 2, 3, 4, 5, 6],
        "Viol":  [0.0, 10.0, 0.0, 5.0, 0.0, 8.0],
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_violation", {
            "file_path":     str(p),
            "label_col":     "Stage",
            "analysis_type": "frequency",
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] Violation frequency analysis returned valid result.")
    finally:
        _cleanup(p)


@test("tool_analyze_violation_mean_vs_max")
def test_tool_analyze_violation_mean_vs_max():
    import pandas as pd
    _sep("df_analyze_violation — mean_vs_max mode (mean file + max file)")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    # mean ≈ max → violations not sporadic (persistent issue)
    df_mean = pd.DataFrame({"Stage": [1, 2, 3, 4, 5], "Viol": [8.0,  9.0,  10.0, 9.5, 8.5]})
    df_max  = pd.DataFrame({"Stage": [1, 2, 3, 4, 5], "Viol": [9.0, 10.0,  11.0, 10.0, 9.0]})
    p_mean = _tmp_csv(df_mean)
    p_max  = _tmp_csv(df_max)
    try:
        result = call_tool("df_analyze_violation", {
            "file_path":     str(p_mean),
            "file_path_max": str(p_max),
            "label_col":     "Stage",
            "analysis_type": "mean_vs_max",
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] Violation mean_vs_max analysis returned valid result.")
    finally:
        _cleanup(p_mean, p_max)


@test("tool_analyze_cmo_with_zeros")
def test_tool_analyze_cmo_with_zeros():
    import pandas as pd
    _sep("df_analyze_cmo — zero and negative marginal costs")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({
        "Stage": [1, 2, 3, 4, 5, 6],
        "CMO":   [0.0, -5.0, 100.0, 200.0, 0.0, 150.0],
    })
    p = _tmp_csv(df)
    try:
        result = call_tool("df_analyze_cmo", {
            "file_path":      str(p),
            "label_col":      "Stage",
            "zero_tolerance": 0.01,
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] CMO distribution analysis returned valid result.")
    finally:
        _cleanup(p)


@test("tool_get_head")
def test_tool_get_head():
    import pandas as pd
    _sep("df_get_head — return first N rows")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({"A": range(10), "B": [f"v{i}" for i in range(10)]})
    p = _tmp_csv(df)
    try:
        result = call_tool("df_get_head", {"file_path": str(p), "n": 3})
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] df_get_head returned valid result.")
    finally:
        _cleanup(p)


@test("tool_get_summary")
def test_tool_get_summary():
    import pandas as pd
    _sep("df_get_summary — descriptive statistics")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    df = pd.DataFrame({"Value": [10.0, 20.0, 30.0, 40.0, 50.0]})
    p = _tmp_csv(df)
    try:
        result = call_tool("df_get_summary", {"file_path": str(p)})
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] df_get_summary returned valid result.")
    finally:
        _cleanup(p)


@test("tool_cross_correlation")
def test_tool_cross_correlation():
    import pandas as pd
    _sep("df_cross_correlation — two correlated series")
    call_tool, _ = _import_tools()
    if call_tool is None:
        return

    n = 12
    df_a = pd.DataFrame({"Stage": range(n), "ENA":  [float(i * 2)     for i in range(n)]})
    df_b = pd.DataFrame({"Stage": range(n), "Cost": [float(i * 3 + 1) for i in range(n)]})
    pa = _tmp_csv(df_a)
    pb = _tmp_csv(df_b)
    try:
        result = call_tool("df_cross_correlation", {
            "file_path_a": str(pa),
            "file_path_b": str(pb),
            "col_a":       "ENA",
            "col_b":       "Cost",
            "join_on":     "Stage",
        })
        _show(result)
        assert "error" not in result, result.get("error")
        print("\n  [OK] Cross-correlation returned valid result.")
    finally:
        _cleanup(pa, pb)


# =============================================================================
# GROUP 3 — Node tool coverage (all analysis nodes can call their tools)
# =============================================================================

@test("node_coverage_all_tools_callable")
def test_node_coverage_all_tools_callable():
    """Every tool listed inside an analysis node must exist and be callable."""
    _sep("All analysis-node tools exist in TOOL_DISPATCH and are callable")
    graph = _load_graph()
    _, TOOL_DISPATCH = _import_tools()
    if graph is None or TOOL_DISPATCH is None:
        return

    analysis_nodes = [
        n for n in graph["nodes_by_id"].values() if n.get("type") == "analysis"
    ]
    print(f"  Analysis nodes : {len(analysis_nodes)}")

    issues: list[str] = []
    for node in analysis_nodes:
        tools = node.get("tools", [])
        if not tools:
            print(f"  (no tools)  {node['id']}")
            continue
        for tool in tools:
            name = tool["name"]
            fn = TOOL_DISPATCH.get(name)
            if fn is None:
                issues.append(f"  {node['id']}: {name!r} missing from TOOL_DISPATCH")
            elif not callable(fn):
                issues.append(f"  {node['id']}: {name!r} is not callable")
            else:
                print(f"  OK   {node['id']:50s}  ->  {name}")

    if issues:
        for i in issues:
            print(i)
        assert False, f"{len(issues)} issue(s) found"
    print("\n  [OK] All analysis-node tools are callable.")


# =============================================================================
# GROUP 4 — Simulated traversal without LLM
#
# Instead of running real CSV tools during traversal, we inject pre-built
# mock tool results and use a deterministic hypothesis evaluator.  This lets
# us test the ROUTING LOGIC (which edge is followed) independently from the
# individual tool tests above.
# =============================================================================

def _deterministic_hypothesis(child_node: dict, tool_results: list[dict]) -> bool:
    """
    Evaluate whether a child node's hypothesis holds based on tool results,
    using simple deterministic rules derived from each node's expected_state.

    When no specific rule matches, returns True (follow priority-1 by default).
    """
    node_id = child_node["id"]
    by_tool: dict[str, dict] = {r["tool_name"]: r["result"] for r in tool_results}

    # ── Convergence branch ──────────────────────────────────────────────────
    if node_id == "node_zinf_aproximando_zsup":
        # Holds when Zinf is NOT stagnated (still approaching the band)
        r = by_tool.get("df_analyze_stagnation", {})
        return r.get("stagnation_results", {}).get("status") == "Active"

    if node_id == "node_zinf_zsup_distantes":
        # Holds when Zinf IS stagnated (not approaching)
        r = by_tool.get("df_analyze_stagnation", {})
        return r.get("stagnation_results", {}).get("status") == "Stagnated"

    if node_id == "node_iteracoes_insuficientes":
        # Leaf: holds when Zinf was still active (approaching)
        r = by_tool.get("df_analyze_stagnation", {})
        return r.get("stagnation_results", {}).get("status") == "Active"

    if node_id == "node_penalidades_altas":
        # Holds when operating cost < 80% in at least one stage
        r = by_tool.get("df_analyze_composition", {})
        return r.get("criticality_report", {}).get("total_critical_found", 0) > 0

    if node_id == "node_baixo_forwards":
        # Holds when Zinf is stagnated AND penalties are acceptable
        r = by_tool.get("df_analyze_stagnation", {})
        return r.get("stagnation_results", {}).get("status") == "Stagnated"

    # ── Simulation branch ───────────────────────────────────────────────────
    if node_id == "node_proporcao_custo_operativo_sim":
        r = by_tool.get("df_analyze_composition", {})
        return r.get("criticality_report", {}).get("total_critical_found", 0) > 0

    # ── CMO branch ──────────────────────────────────────────────────────────
    if node_id == "node_cmo_zero":
        r = by_tool.get("df_analyze_cmo", {})
        return r.get("zero_analysis", {}).get("has_zeros", False)

    if node_id == "node_cmo_negativo":
        r = by_tool.get("df_analyze_cmo", {})
        return r.get("negative_analysis", {}).get("has_negatives", False)

    # ── Violation branch ────────────────────────────────────────────────────
    if node_id in ("node_violacoes_frequentes", "node_violacao_alta"):
        for r in tool_results:
            freq = r["result"].get("frequency_analysis", {})
            if freq.get("stages_with_violations", 0) > 0:
                return True
        return False

    # Default: first child holds (follows priority-1 edge)
    return True


def _simulate_traversal(
    entry_problem: str,
    mock_results: "dict[str, list[dict]]",
    graph: dict,
    max_steps: int = 20,
) -> list[str]:
    """
    Walk the decision graph without LLM.

    entry_problem : key in graph["entry_points"]
    mock_results  : {child_node_id: [{"tool_name": ..., "result": ...}]}
                    If a child is absent from mock_results, an empty list is used
                    and the deterministic evaluator falls back to True (priority-1).

    Returns the ordered list of visited node IDs.
    """
    current_id: str = graph["entry_points"][entry_problem]
    visited: list[str] = [current_id]

    for _ in range(max_steps):
        node = graph["nodes_by_id"].get(current_id)
        if node is None or node.get("type") == "conclusion":
            break
        edges = graph["adjacency"].get(current_id, [])
        if not edges:
            break

        selected: str | None = None
        for edge in edges:
            child_id = edge["target"]
            child = graph["nodes_by_id"].get(child_id)
            if child is None:
                continue
            results = mock_results.get(child_id, [])
            if _deterministic_hypothesis(child, results):
                selected = child_id
                break

        if selected is None:
            selected = edges[0]["target"]   # priority-1 fallback

        visited.append(selected)
        current_id = selected

    return visited


def _print_path(path: list[str], graph: dict) -> None:
    for i, node_id in enumerate(path):
        node  = graph["nodes_by_id"][node_id]
        ntype = node.get("type", "?")
        label = node.get("label", "")
        connector = "\\-" if i == len(path) - 1 else "|-"
        print(f"    {connector} [{ntype:10s}] {node_id}")
        print(f"    {'  ':12s}  {label}")


# ── Traversal scenario: convergence, Zinf stagnated + penalties high ─────────

@test("traversal_convergence_stagnated_high_penalties")
def test_traversal_convergence_stagnated_high_penalties():
    """
    Scenario: Zinf flat (stagnated) AND penalties dominate.
    Expected path: root → node_zinf_zsup_distantes → node_penalidades_altas → …
    """
    _sep("Traversal — convergência: estagnado + penalidades altas")
    graph = _load_graph()
    if graph is None:
        return

    mock = {
        # root tests whether Zinf is approaching → use stagnation result
        "node_zinf_aproximando_zsup": [
            {"tool_name": "df_analyze_stagnation",
             "result": {"stagnation_results": {"status": "Active"}}}  # NOT stagnated → don't take this branch
        ],
        "node_zinf_zsup_distantes": [
            {"tool_name": "df_analyze_stagnation",
             "result": {"stagnation_results": {"status": "Stagnated"}}}  # stagnated → take this branch
        ],
        "node_penalidades_altas": [
            {"tool_name": "df_analyze_composition",
             "result": {"criticality_report": {"total_critical_found": 4}}}  # penalties high
        ],
    }

    path = _simulate_traversal("problema_convergencia", mock, graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert "node_zinf_zsup_distantes" in path, "Expected node_zinf_zsup_distantes in path"
    assert "node_penalidades_altas" in path, "Expected node_penalidades_altas in path"
    terminal = graph["nodes_by_id"][path[-1]]
    assert terminal.get("type") == "conclusion", f"Expected conclusion, got {terminal.get('type')}"
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] Traversal reached expected conclusion.")


@test("traversal_convergence_approaching_not_stagnated")
def test_traversal_convergence_approaching():
    """
    Scenario: Zinf still approaching (Active), not stagnated.
    Expected path: root → node_zinf_aproximando_zsup → node_iteracoes_insuficientes (conclusion)
    """
    _sep("Traversal — convergência: Zinf aproximando (iterações insuficientes)")
    graph = _load_graph()
    if graph is None:
        return

    mock = {
        "node_zinf_aproximando_zsup": [
            {"tool_name": "df_analyze_stagnation",
             "result": {"stagnation_results": {"status": "Active"}}}   # approaching → take this
        ],
        "node_iteracoes_insuficientes": [
            {"tool_name": "df_analyze_stagnation",
             "result": {"stagnation_results": {"status": "Active"}}}
        ],
    }

    path = _simulate_traversal("problema_convergencia", mock, graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert "node_zinf_aproximando_zsup" in path, "Expected node_zinf_aproximando_zsup"
    terminal = graph["nodes_by_id"][path[-1]]
    assert terminal.get("type") == "conclusion"
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] Traversal reached expected conclusion.")


@test("traversal_simulacao_penalties_high")
def test_traversal_simulacao_penalties():
    """
    Scenario: simulation with penalties dominating costs.
    Expected to route through node_proporcao_custo_operativo_sim.
    """
    _sep("Traversal — simulação: penalidades altas")
    graph = _load_graph()
    if graph is None:
        return

    mock = {
        "node_proporcao_custo_operativo_sim": [
            {"tool_name": "df_analyze_composition",
             "result": {"criticality_report": {"total_critical_found": 5}}}
        ],
    }

    path = _simulate_traversal("problema_simulacao", mock, graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert len(path) >= 2, "Expected at least 2 nodes visited"
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] Simulation traversal completed.")


@test("traversal_cmo_with_zeros")
def test_traversal_cmo_zeros():
    """
    Scenario: CMO has zero values.
    Expected to route toward the zero-CMO conclusion path.
    """
    _sep("Traversal — CMO: zeros presentes")
    graph = _load_graph()
    if graph is None:
        return

    mock = {
        "node_cmo_zero": [
            {"tool_name": "df_analyze_cmo",
             "result": {"zero_analysis": {"has_zeros": True}}}
        ],
    }

    path = _simulate_traversal("cmo", mock, graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert len(path) >= 2
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] CMO traversal completed.")


@test("traversal_violacao_path")
def test_traversal_violacao():
    """Simulate the violation entry point path."""
    _sep("Traversal — violação (entry point)")
    graph = _load_graph()
    if graph is None:
        return

    path = _simulate_traversal("violacao", mock_results={}, graph=graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert len(path) >= 1
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] Violation traversal completed.")


@test("traversal_deslocamento_custo_path")
def test_traversal_deslocamento_custo():
    """Simulate the cost-displacement entry point path."""
    _sep("Traversal — deslocamento custo (entry point)")
    graph = _load_graph()
    if graph is None:
        return

    path = _simulate_traversal("deslocamento_custo", mock_results={}, graph=graph)
    print(f"\n  Path ({len(path)} steps):")
    _print_path(path, graph)

    assert len(path) >= 1
    print(f"\n  Terminal: {path[-1]}")
    print("\n  [OK] Deslocamento custo traversal completed.")


@test("traversal_all_entry_points_reach_conclusion")
def test_traversal_all_entry_points_reach_conclusion():
    """Every entry point must reach a conclusion node within 20 steps."""
    _sep("All entry points reach a conclusion node (no infinite loops)")
    graph = _load_graph()
    if graph is None:
        return

    for entry_key in graph["entry_points"]:
        path = _simulate_traversal(entry_key, mock_results={}, graph=graph)
        terminal = graph["nodes_by_id"].get(path[-1], {})
        ttype = terminal.get("type", "?")
        status = "OK " if ttype == "conclusion" else "WARN"
        print(f"  [{status}] {entry_key:40s} -> {path[-1]}  [{ttype}]  ({len(path)} steps)")

    # All must terminate (assertion on each)
    for entry_key in graph["entry_points"]:
        path = _simulate_traversal(entry_key, mock_results={}, graph=graph)
        terminal = graph["nodes_by_id"].get(path[-1], {})
        assert terminal.get("type") == "conclusion", (
            f"Entry {entry_key!r} did not reach a conclusion: last node={path[-1]!r}"
        )
    print("\n  [OK] All entry points reach a conclusion node.")


# =============================================================================
# Runner
# =============================================================================

def _run(names: list[str]) -> None:
    passed = failed = 0
    for test_name, fn in TESTS.items():
        if names and not any(n.lower() in test_name.lower() for n in names):
            continue
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            print(f"\n  [FAIL] {test_name}: {exc}")
            failed += 1
        except Exception as exc:
            print(f"\n  [ERROR] {test_name}: {type(exc).__name__}: {exc}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 72}")
    print(f"  Results: {passed} passed, {failed} failed  (of {passed + failed} run)")
    print(f"{'=' * 72}\n")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    filters = sys.argv[1:]
    if filters:
        print(f"Running tests matching: {filters}")
    else:
        print(f"Running all {len(TESTS)} tests")
        print(f"Available: {', '.join(TESTS)}\n")
    _run(filters)

"""
Manual test harness for psr-output-analysis server functions.

Run from the repository root:

    python tests/test_server_functions.py                      # all tests
    python tests/test_server_functions.py get_diagnostic_graph  # one test by name
    python tests/test_server_functions.py graph doc            # multiple names (substring match)

Each test prints its output so you can inspect what the LLM would actually receive.
"""

from __future__ import annotations

import importlib
import json
import sys
import textwrap
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Path setup — make sure the repo root and the psr package are importable
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Import helpers — handle optional heavy dependencies gracefully
# ---------------------------------------------------------------------------

def _import_server():
    """Import the server module, skipping tests that need it if it fails."""
    try:
        import psr.outputanalysismcp.server as srv
        return srv
    except Exception as exc:
        print(f"[SKIP] Could not import server module: {exc}")
        return None


def _import_dataframe_functions():
    try:
        import psr.outputanalysismcp.dataframe_functions as df_fns
        return df_fns
    except Exception as exc:
        print(f"[SKIP] Could not import dataframe_functions: {exc}")
        return None


def _import_html_extractor():
    try:
        from sddp_html_to_csv import extract_charts, export_to_csv, _detect_chart_type
        return extract_charts, export_to_csv, _detect_chart_type
    except Exception as exc:
        print(f"[SKIP] Could not import sddp_html_to_csv: {exc}")
        return None, None, None


# ---------------------------------------------------------------------------
# Test registry
# ---------------------------------------------------------------------------

TESTS: dict[str, Callable] = {}

def test(name: str):
    """Decorator to register a test function."""
    def decorator(fn):
        TESTS[name] = fn
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sep(title: str) -> None:
    width = 72
    print(f"\n{'─' * width}")
    print(f"  TEST: {title}")
    print(f"{'─' * width}")


def _result(output: str) -> None:
    print(textwrap.indent(output, "  "))


def _find_sample_csv(subdir: str = "results") -> Path | None:
    """Return the first CSV found in any results/ subfolder under the repo."""
    for csv in REPO_ROOT.rglob(f"{subdir}/*.csv"):
        if not csv.name.startswith("_"):
            return csv
    return None


def _find_sample_study() -> Path | None:
    """Return a study folder that contains a results/_index.json."""
    for idx in REPO_ROOT.rglob("results/_index.json"):
        return idx.parent.parent
    return None


# ---------------------------------------------------------------------------
# Tests — graph & documentation
# ---------------------------------------------------------------------------

@test("get_diagnostic_graph")
def test_get_diagnostic_graph():
    """Verify the graph loads and formats correctly from decision_graph.json."""
    srv = _import_server()
    if srv is None:
        return

    _sep("get_diagnostic_graph")
    output = srv.get_diagnostic_graph()
    _result(output)

    # Quick sanity checks
    assert "Entry points" in output,     "Missing 'Entry points' section"
    assert "Nodes" in output,            "Missing 'Nodes' section"
    assert "Traversal rules" in output,  "Missing 'Traversal rules'"
    assert "type=analysis" in output or "type=conclusion" in output, \
        "No node types found"
    print("\n  [OK] Sanity checks passed.")


@test("get_conclusion_documentation")
def test_get_conclusion_documentation():
    """Test similarity search on Results.md with several intents."""
    srv = _import_server()
    if srv is None:
        return

    intents = [
        "Calibração de penalidades SDDP violações convergência cortes dominados",
        "Número de iterações não suficiente convergência Zinf Zsup",
        "Número de séries forward convergência SDDP amostragem espaço de estados",
        "CMO negativo penalidade vertimento renovável",
    ]

    for intent in intents:
        _sep(f"get_conclusion_documentation — '{intent[:50]}…'")
        output = srv.get_conclusion_documentation(intent, top_k=2)
        _result(output)


@test("conclusion_doc_no_match")
def test_conclusion_doc_no_match():
    """Confirm graceful fallback when no section matches."""
    srv = _import_server()
    if srv is None:
        return

    _sep("get_conclusion_documentation — no match")
    output = srv.get_conclusion_documentation("xyzzy foobar quux", top_k=2)
    _result(output[:400])  # trim full file dump
    assert "[No match]" in output, "Expected [No match] prefix"
    print("\n  [OK] Graceful fallback confirmed.")


@test("results_sections")
def test_results_sections():
    """Inspect how Results.md is split into sections."""
    srv = _import_server()
    if srv is None:
        return

    _sep("_parse_results_sections (internal helper)")
    results_md = REPO_ROOT / "Results.md"
    if not results_md.exists():
        print("  [SKIP] Results.md not found")
        return

    text     = results_md.read_text(encoding="utf-8")
    sections = srv._parse_results_sections(text)
    print(f"  Found {len(sections)} sections:\n")
    for s in sections:
        indent = "  " if s["level"] == 2 else "    "
        preview = s["content"][:80].replace("\n", " ")
        print(f"  {'##' if s['level']==2 else '###'} {s['heading']}")
        print(f"  {indent}  → {preview}…")


# ---------------------------------------------------------------------------
# Tests — available results / index
# ---------------------------------------------------------------------------

@test("get_avaliable_results")
def test_get_avaliable_results():
    """Load results catalogue from a real study folder if one exists."""
    srv = _import_server()
    if srv is None:
        return

    study = _find_sample_study()
    if study is None:
        print("  [SKIP] No study folder with results/_index.json found under repo root.")
        return

    _sep(f"get_avaliable_results — {study}")
    output = srv.get_avaliable_results(str(study))
    _result(output)


@test("get_avaliable_results_fallback")
def test_get_avaliable_results_fallback():
    """Test fallback output when _index.json is absent."""
    srv = _import_server()
    if srv is None:
        return

    # Use the repo root itself as a fake study — it has files but no _index.json
    _sep("get_avaliable_results — fallback (no _index.json)")
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmp:
        results_dir = Path(tmp) / "results"
        results_dir.mkdir()
        (results_dir / "dummy.csv").write_text("a,b\n1,2\n")
        output = srv.get_avaliable_results(tmp)
    _result(output)
    assert "[!]" in output, "Expected fallback warning"
    print("\n  [OK] Fallback warning present.")


# ---------------------------------------------------------------------------
# Tests — dataframe functions (pure Python, no MCP)
# ---------------------------------------------------------------------------

@test("df_analyze_bounds")
def test_df_analyze_bounds():
    """Run analyze_bounds_and_reference on synthetic convergence data."""
    import pandas as pd
    df_fns = _import_dataframe_functions()
    if df_fns is None:
        return

    _sep("analyze_bounds_and_reference — synthetic data")

    # Simulate a converging run: Zinf grows toward Zsup band
    n = 20
    zsup   = 1000.0
    tol    = 20.0
    zinf   = [zsup * (0.80 + 0.01 * i) for i in range(n)]
    df = pd.DataFrame({
        "Iteration": range(1, n + 1),
        "Zinf":      zinf,
        "Zsup":      [zsup] * n,
        "Lower_CI":  [zsup - tol] * n,
        "Upper_CI":  [zsup + tol] * n,
    })

    result = df_fns.analyze_bounds_and_reference(
        df,
        target_col="Zinf",
        lower_bound_col="Lower_CI",
        upper_bound_col="Upper_CI",
        reference_val_col="Zsup",
        iteration_col="Iteration",
    )
    print(f"  converged      : {result['bounds_status']['converged']}")
    print(f"  current Zinf   : {result['bounds_status']['current_value']:.1f}")
    print(f"  interval       : {result['bounds_status']['interval']}")
    print(f"  is_locked      : {result['stability']['is_locked']}")
    print(f"  accuracy_trend : {result['reference_accuracy']['accuracy_trend']}")

    assert result["reference_accuracy"]["accuracy_trend"] == "improving"
    print("\n  [OK] Trend is improving as expected.")


@test("df_analyze_stagnation")
def test_df_analyze_stagnation():
    """Test stagnation detection on flat vs. improving series."""
    import pandas as pd
    df_fns = _import_dataframe_functions()
    if df_fns is None:
        return

    _sep("analyze_stagnation — flat series")
    flat_df = pd.DataFrame({"Zinf": [100.0] * 15})
    r = df_fns.analyze_stagnation(flat_df, "Zinf", window_size=5)
    print(f"  status : {r['stagnation_results']['status']}")
    assert r["stagnation_results"]["status"] == "Stagnated"

    _sep("analyze_stagnation — improving series")
    improving_df = pd.DataFrame({"Zinf": [float(i * 5) for i in range(15)]})
    r2 = df_fns.analyze_stagnation(improving_df, "Zinf", window_size=5)
    print(f"  status : {r2['stagnation_results']['status']}")
    assert r2["stagnation_results"]["status"] == "Active"
    print("\n  [OK] Stagnation detection correct.")


@test("df_analyze_composition")
def test_df_analyze_composition():
    """Test the 80% operating-cost rule with synthetic data."""
    import pandas as pd
    df_fns = _import_dataframe_functions()
    if df_fns is None:
        return

    _sep("analyze_composition — penalty dominating")
    df = pd.DataFrame({
        "Stage":          list(range(1, 6)),
        "Operating_Cost": [50.0, 60.0, 40.0, 55.0, 45.0],
        "Penalty_Cost":   [50.0, 40.0, 60.0, 45.0, 55.0],  # 50% each
    })
    r = df_fns.analyze_composition(
        df,
        target_cost_col="Operating_Cost",
        all_cost_cols=["Operating_Cost", "Penalty_Cost"],
        label_col="Stage",
        min_threshold=80.0,
    )
    share = r["composition_metrics"]["target_share_of_total_pct"]
    critical = r["criticality_report"]["total_critical_found"]
    print(f"  op_cost share : {share:.1f}%")
    print(f"  critical rows : {critical}")
    assert critical == 5, f"Expected 5 critical rows, got {critical}"
    print("\n  [OK] All stages flagged as below 80% threshold.")


# ---------------------------------------------------------------------------
# Tests — HTML extractor helpers
# ---------------------------------------------------------------------------

@test("detect_chart_type")
def test_detect_chart_type():
    """Verify _detect_chart_type classification."""
    _, _, detect = _import_html_extractor()
    if detect is None:
        return

    _sep("_detect_chart_type")
    cases = [
        (["heatmap", "line"],         "heatmap"),
        (["heatmap_series"],          "heatmap"),
        (["area_range", "line"],      "band"),
        (["column", "line"],          "bar"),
        (["line", "spline"],          "line"),
        (["line"],                    "line"),
    ]
    for layer_types, expected in cases:
        got = detect(layer_types)
        status = "OK" if got == expected else "FAIL"
        print(f"  [{status}] {layer_types} → {got!r}  (expected {expected!r})")
        assert got == expected, f"Mismatch: {layer_types}"
    print("\n  [OK] All chart type detections correct.")


# ---------------------------------------------------------------------------
# Tests — index.json round-trip (if a sample study exists)
# ---------------------------------------------------------------------------

@test("index_json")
def test_index_json():
    """Read _index.json from the first available study and pretty-print it."""
    study = _find_sample_study()
    if study is None:
        _sep("index_json")
        print("  [SKIP] No study folder with results/_index.json found.")
        return

    index_path = study / "results" / "_index.json"
    _sep(f"_index.json — {index_path}")
    entries = json.loads(index_path.read_text(encoding="utf-8"))
    print(f"  {len(entries)} entries\n")
    for e in entries[:5]:  # show first 5 only
        print(f"  [{e['chart_type']:<8}]  {e['filename']}")
        print(f"              title   : {e['title']}")
        print(f"              y_unit  : {e['y_unit']}   rows: {e['rows']}")
        print(f"              columns : {', '.join(e['series'][:6])}{'…' if len(e['series']) > 6 else ''}")
        print()
    if len(entries) > 5:
        print(f"  … and {len(entries) - 5} more entries.")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def _run(names: list[str]) -> None:
    """Run tests whose names contain any of the given substrings (case-insensitive)."""
    passed = failed = skipped = 0
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
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'═' * 72}")
    print(f"  Results: {passed} passed, {failed} failed  (of {passed + failed} run)")
    print(f"{'═' * 72}\n")
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

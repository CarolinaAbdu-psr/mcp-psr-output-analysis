"""
Thin wrappers around dataframe_functions.py for use by the SDDP agent.

Each wrapper:
  1. Loads the CSV from params["file_path"] via common.read_csv_path
  2. Calls the corresponding pure function from dataframe_functions.py
  3. Returns a raw dict result (never formatted text)

Tool names match the MCP server names exactly so the decision graph JSON
can reference the same names regardless of whether the MCP server or this
agent is driving the analysis.
"""
from __future__ import annotations

import json
from pathlib import Path

from psr.outputanalysismcp.common import read_csv_path
from psr.outputanalysismcp.dataframe_functions import (
    analyze_bounds_and_reference,
    analyze_composition,
    analyze_cross_correlation,
    analyze_heatmap,
    analyze_stagnation,
    analyze_violation,
    filter_by_threshold,
    get_data_summary,
    get_dataframe_head,
)


# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------

def _wrap_analyze_bounds(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    return analyze_bounds_and_reference(
        df,
        target_col=params["target_col"],
        lower_bound_col=params["lower_bound_col"],
        upper_bound_col=params["upper_bound_col"],
        reference_val_col=params["reference_val_col"],
        iteration_col=params.get("iteration_col") or None,
        lock_threshold=float(params.get("lock_threshold", 0.005)),
    )


def _wrap_analyze_composition(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    all_cols = params.get("all_cost_cols") or params.get("all_cost_cols_json")
    if not all_cols:
        raise KeyError("all_cost_cols")
    if isinstance(all_cols, str):
        all_cols = json.loads(all_cols)
    return analyze_composition(
        df,
        target_cost_col=params["target_cost_col"],
        all_cost_cols=all_cols,
        label_col=params.get("label_col", ""),
        min_threshold=params.get("min_threshold") or None,
        max_threshold=params.get("max_threshold") or None,
    )


def _wrap_analyze_stagnation(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    return analyze_stagnation(
        df,
        target_col=params["target_col"],
        window_size=int(params.get("window_size", 5)),
        cv_threshold=float(params.get("cv_threshold", 1.0)),
        slope_threshold=float(params.get("slope_threshold", 0.01)),
    )


def _wrap_cross_correlation(params: dict) -> dict:
    df_a = read_csv_path(params["file_path_a"])
    df_b = read_csv_path(params["file_path_b"])
    return analyze_cross_correlation(
        df_a,
        df_b,
        col_a=params["col_a"],
        col_b=params["col_b"],
        join_on=params.get("join_on") or None,
        output_csv_path=params.get("output_csv_path") or None,
    )


def _wrap_analyze_heatmap(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    value_cols = params.get("value_cols")
    if isinstance(value_cols, str) and value_cols:
        value_cols = json.loads(value_cols)
    return analyze_heatmap(
        df,
        label_col=params.get("label_col") or None,
        value_cols=value_cols or None,
        mode=params.get("mode", "solver_status"),
        threshold=float(params.get("threshold", 0.0)),
        top_n=int(params.get("top_n", 10)),
    )


def _wrap_filter_threshold(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    value_cols = params.get("value_cols")
    if isinstance(value_cols, str) and value_cols:
        value_cols = json.loads(value_cols)
    return filter_by_threshold(
        df,
        threshold=float(params["threshold"]),
        label_col=params.get("label_col") or None,
        value_cols=value_cols or None,
        direction=params.get("direction", "above"),
        top_n=int(params.get("top_n", 10)),
    )


def _wrap_get_head(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    return get_dataframe_head(df, n=int(params.get("n", 5)))


def _wrap_get_summary(params: dict) -> dict:
    df = read_csv_path(params["file_path"])
    ops = params.get("operations", {})
    if isinstance(ops, str):
        ops = json.loads(ops)
    return get_data_summary(df, ops)


def _wrap_check_nonconvexity_policy(params: dict) -> dict:
    import psr.factory  
    case_path = params["case_path"]
    study_settings = psr.factory.load_study_settings(case_path)
    option = study_settings.get("NonConvexityRepresentationInPolicy")
    if option == 0:
        return {
            "holds": True,
            "NonConvexityRepresentationInPolicy": option,
            "message": "Integralidade violada: NonConvexityRepresentationInPolicy=0 — não-convexidade não ativada na política.",
        }
    return {
        "holds": False,
        "NonConvexityRepresentationInPolicy": option,
        "message": f"Opção ativada (NonConvexityRepresentationInPolicy={option}): sendo considerada na política. Rejeitar hipótese.",
    }


def _wrap_analyze_violation(params: dict) -> dict:
    df = read_csv_path(params["file_path"])

    df_max = None
    if params.get("file_path_max"):
        df_max = read_csv_path(params["file_path_max"])

    value_cols = params.get("value_cols")
    if isinstance(value_cols, str) and value_cols:
        value_cols = json.loads(value_cols)

    return analyze_violation(
        df,
        label_col=params.get("label_col") or None,
        value_cols=value_cols or None,
        analysis_type=params.get("analysis_type", "frequency"),
        df_max=df_max,
        mean_max_ratio_threshold=float(params.get("mean_max_ratio_threshold", 0.8)),
        violation_threshold=float(params.get("violation_threshold", 0.0)),
        frequency_threshold=float(params.get("frequency_threshold", 0.5)),
        top_n=int(params.get("top_n", 5)),
    )


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

TOOL_DISPATCH: dict[str, object] = {
    "df_analyze_bounds":             _wrap_analyze_bounds,
    "df_analyze_composition":        _wrap_analyze_composition,
    "df_analyze_stagnation":         _wrap_analyze_stagnation,
    "df_cross_correlation":          _wrap_cross_correlation,
    "df_analyze_heatmap":            _wrap_analyze_heatmap,
    "df_filter_above_threshold":     _wrap_filter_threshold,
    "df_get_head":                   _wrap_get_head,
    "df_get_summary":                _wrap_get_summary,
    "df_analyze_violation":          _wrap_analyze_violation,
    "df_check_nonconvexity_policy":  _wrap_check_nonconvexity_policy,
}


def call_tool(tool_name: str, params: dict) -> dict:
    """
    Dispatch a tool call by name.

    params must already contain resolved column names and file_path(s).
    Returns a raw result dict; never raises — errors are returned as {"error": str}.
    """
    fn = TOOL_DISPATCH.get(tool_name)
    if fn is None:
        return {"error": f"Unknown tool: {tool_name!r}"}
    try:
        return fn(params)  # type: ignore[operator]
    except FileNotFoundError as exc:
        return {"error": f"File not found: {exc}"}
    except KeyError as exc:
        return {"error": f"Missing parameter or column: {exc}"}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}

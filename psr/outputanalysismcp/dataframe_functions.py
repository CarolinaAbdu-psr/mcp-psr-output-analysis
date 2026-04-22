"""
Generic DataFrame analysis functions for MCP tool consumption.

This module provides column-agnostic statistical functions that the LLM can
call via MCP tools.  Each function takes a DataFrame (already loaded from a
CSV) and a set of column-name parameters, performs a focused analysis, and
returns a structured dict that the tool layer formats into readable text.

Functions
---------
Schema inspection
    get_column_names(df)
        Returns the list of column names — the LLM's first call on an unknown file.

    get_dataframe_head(df, n)
        Returns the first N rows plus shape info — reveals data format and scale.

    get_dataframe_size(df, max_cells)
        Returns shape.  If total cells <= max_cells, also returns the full CSV.

Flexible statistics
    get_data_summary(df, operations_dict)
        Applies a user-specified set of operations (mean/std/min/max) to
        selected columns in a single call.

Convergence / bounds analysis
    analyze_bounds_and_reference(df, target_col, lower_bound_col,
                                  upper_bound_col, reference_val_col, ...)
        Checks whether a target value sits inside a [low, high] band AND
        tracks how close it is to a reference value over time. Covers both
        the SDDP Zinf-vs-band check and any policy-vs-simulation comparison.

Cost / value composition
    analyze_composition(df, target_cost_col, all_cost_cols, label_col, ...)
        Computes the share of one column inside a group total, flags rows
        that breach min/max percentage thresholds.

Stagnation detection
    analyze_stagnation(df, target_col, window_size, cv_threshold, ...)
        Detects whether a series has stopped changing over the most recent N
        rows, using CV and normalised slope as indicators.

Cross-dataframe correlation
    analyze_cross_correlation(df_a, df_b, col_a, col_b, join_on, ...)
        Aligns two DataFrames, computes Pearson r, R², and elasticity, and
        optionally exports a scatter-plot CSV.

Heatmap / matrix analysis
    analyze_heatmap(df, label_col, value_cols, mode, threshold, top_n)
        Analyses a stage×scenario matrix.  Two modes:
        - "solver_status": values 0–3 (optimal/feasible/relaxed/no-solution);
          critical = any cell > 0.
        - "threshold": continuous values (e.g. penalty %); critical = cell > threshold.
        Returns per-scenario and per-stage criticality rankings.

Threshold filtering
    filter_by_threshold(df, threshold, label_col, value_cols, direction, top_n)
        For time-varying bar-chart data (rows = stages, columns = agents/penalties).
        Identifies which columns exceed (or fall below) a threshold at each stage,
        and ranks columns by exceedance frequency.
"""
from __future__ import annotations

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
# Shared constant
# ---------------------------------------------------------------------------

LOCK_THRESHOLD = 0.005  # % absolute gap change below which a series is "locked"


# ---------------------------------------------------------------------------
# Schema inspection
# ---------------------------------------------------------------------------

def get_column_names(df: pd.DataFrame) -> list[str]:
    """
    Return all column names in the DataFrame.

    The LLM should call this first when working with an unfamiliar CSV so it
    can discover available columns before choosing which ones to pass to the
    analysis functions.

    Args:
        df: Any DataFrame.

    Returns:
        Flat list of column name strings.

    Example:
        >>> get_column_names(df)
        ['Iteration', 'Zinf', 'Zsup', 'Zsup +- Tol (low)', 'Zsup +- Tol (high)']
    """
    return df.columns.tolist()


def get_dataframe_head(df: pd.DataFrame, n: int = 5) -> dict:
    """
    Return the first N rows of the DataFrame together with shape info.

    Useful immediately after ``get_column_names`` to understand the actual data
    format, numeric scale, and naming conventions before choosing analysis
    parameters.

    Args:
        df: Any DataFrame.
        n:  Number of rows to include. Default 5.

    Returns:
        Dict with keys:
            ``shape``       — ``{"rows": int, "columns": int}``
            ``columns``     — list of column name strings
            ``sample_rows`` — list of row dicts (one dict per row, keys = column names)
    """
    head = df.head(n)
    return {
        "shape": {"rows": len(df), "columns": len(df.columns)},
        "columns": df.columns.tolist(),
        "sample_rows": head.to_dict(orient="records"),
    }


def get_dataframe_size(df: pd.DataFrame, max_cells: int = 500) -> dict:
    """
    Report the shape of a DataFrame.  If total cells ≤ max_cells, include
    the full CSV content so the LLM can read it directly.

    Args:
        df:        Any DataFrame.
        max_cells: Cell-count ceiling for inline content. Default 500.

    Returns:
        Dict with keys:
            ``shape``        — ``{"rows": int, "columns": int, "total_cells": int}``
            ``downloadable`` — True if content is included
            ``full_content`` — CSV string (only present when downloadable is True)
    """
    n_rows, n_cols = df.shape
    total = n_rows * n_cols
    result: dict = {
        "shape": {"rows": n_rows, "columns": n_cols, "total_cells": total},
        "downloadable": total <= max_cells,
    }
    if total <= max_cells:
        result["full_content"] = df.to_csv()
    return result


# ---------------------------------------------------------------------------
# Flexible statistics
# ---------------------------------------------------------------------------

def get_data_summary(df: pd.DataFrame, operations_dict: dict) -> dict:
    """
    Compute multiple statistics across multiple columns in one call.

    The LLM specifies exactly which columns it cares about and which
    operations to run, avoiding unnecessary computation.

    Supported operations: ``"mean"``, ``"std"``, ``"max"``, ``"min"``.

    Args:
        df: Target DataFrame.
        operations_dict: Mapping of ``{column_name: [list_of_operations]}``.
            Columns that do not exist in the DataFrame receive an error entry
            instead of raising an exception.

            Example::

                {
                    "Forward":  ["mean", "std"],
                    "Backward": ["mean", "max"]
                }

    Returns:
        Nested dict ``{column: {operation: value}}``.
        Unknown columns → ``{column: "Error: Column not found"}``.
        Unknown operations → ``{op: "Error: Operation not supported"}``.

    Example:
        >>> get_data_summary(df, {"Zsup": ["mean", "min"], "Zinf": ["mean"]})
        {'Zsup': {'mean': 123456.0, 'min': 100000.0}, 'Zinf': {'mean': 121000.0}}
    """
    _ops = {
        "mean": lambda s: s.mean(),
        "std":  lambda s: s.std(),
        "max":  lambda s: s.max(),
        "min":  lambda s: s.min(),
    }

    summary: dict = {}
    for column, operations in operations_dict.items():
        if column not in df.columns:
            summary[column] = "Error: Column not found"
            continue

        col_result: dict = {}
        for op in operations:
            if op in _ops:
                col_result[op] = float(_ops[op](df[column]))
            else:
                col_result[op] = "Error: Operation not supported"

        summary[column] = col_result

    return summary


# ---------------------------------------------------------------------------
# Convergence / bounds analysis
# ---------------------------------------------------------------------------

def analyze_bounds_and_reference(
    df: pd.DataFrame,
    target_col: str,
    lower_bound_col: str,
    upper_bound_col: str,
    reference_val_col: str,
    iteration_col: str | None = None,
    lock_threshold: float = LOCK_THRESHOLD,
) -> dict:
    """
    Test convergence within a [low, high] band AND accuracy vs. a reference.

    Designed for SDDP convergence files where:
    - ``target_col``         = Zinf (the value approaching the band)
    - ``lower_bound_col``    = Zsup +- Tol (low)
    - ``upper_bound_col``    = Zsup +- Tol (high)
    - ``reference_val_col``  = Final simulation (or Zsup)

    Works generically on any iterative series with a band and reference.

    Args:
        df:                Target DataFrame (one row per iteration, ordered).
        target_col:        Column whose final value is tested against the band.
        lower_bound_col:   Column holding the lower edge of the tolerance band.
        upper_bound_col:   Column holding the upper edge of the tolerance band.
        reference_val_col: Column holding the reference / target value.
        iteration_col:     Optional column identifying the iteration number
                           (used only for the metadata label in the output).
        lock_threshold:    Gap-change threshold below which the run is
                           considered "locked" / stagnated. Default 0.005 (0.5%).

    Returns:
        Dict with four sections:

        ``metadata``
            total_iterations, last_iteration label.

        ``bounds_status``
            is_inside_interval (bool), current_value, interval [low, high],
            interval_width.

        ``reference_accuracy``
            reference_value, absolute_distance, relative_error_pct,
            accuracy_trend ("improving" | "degrading"),
            total_distance_reduction.

        ``stability``
            is_locked (bool), recent_gap_change.

    Example::

        result = analyze_bounds_and_reference(
            df,
            target_col="Zinf",
            lower_bound_col="Zsup +- Tol (low)",
            upper_bound_col="Zsup +- Tol (high)",
            reference_val_col="Zsup",
            iteration_col="Iteration",
        )
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    last_row   = df.iloc[-1]
    target_val = float(last_row[target_col])
    l_bound    = float(last_row[lower_bound_col])
    u_bound    = float(last_row[upper_bound_col])
    ref_val    = float(last_row[reference_val_col])

    # 1. Is the target inside the tolerance band?
    is_inside = l_bound <= target_val <= u_bound

    # 2. Distance to reference value
    abs_distance  = abs(target_val - ref_val)
    rel_error_pct = (abs_distance / abs(ref_val) * 100) if ref_val != 0 else 0.0

    # 3. Gap trend: Zsup - Zinf as % of Zsup across all iterations
    work = df.copy()
    work["_gap"]     = work[upper_bound_col] - work[lower_bound_col]
    work["_gap_pct"] = (work["_gap"] / work[upper_bound_col].replace(0, 1)) * 100

    # How is the distance to reference changing?
    work["_dist"] = (work[target_col] - work[reference_val_col]).abs()
    accuracy_improvement = float(work["_dist"].iloc[0] - work["_dist"].iloc[-1])

    # Recent tail for lock detection
    total_iters     = len(df)
    tail_n          = max(2, min(10, total_iters // 2))
    recent_gap_chg  = float(
        work["_gap_pct"].iloc[-tail_n] - work["_gap_pct"].iloc[-1]
    )

    return {
        "metadata": {
            "total_iterations": total_iters,
            "last_iteration":   (
                int(last_row[iteration_col]) if iteration_col else total_iters - 1
            ),
        },
        "bounds_status": {
            "converged": is_inside,
            "current_value":      target_val,
            "interval":           [l_bound, u_bound],
            "interval_width":     u_bound - l_bound,
        },
        "reference_accuracy": {
            "reference_value":          ref_val,
            "absolute_distance":        abs_distance,
            "relative_error_pct":       rel_error_pct,
            "accuracy_trend":           "improving" if accuracy_improvement > 0 else "degrading",
            "total_distance_reduction": accuracy_improvement,
        },
        "stability": {
            "is_locked":          abs(recent_gap_chg) < lock_threshold,
            "recent_gap_change":  recent_gap_chg,
        },
    }


# ---------------------------------------------------------------------------
# Cost / value composition
# ---------------------------------------------------------------------------

def analyze_composition(
    df: pd.DataFrame,
    target_cost_col: str,
    all_cost_cols: list[str],
    label_col: str,
    min_threshold: float | None = None,
    max_threshold: float | None = None,
) -> dict:
    """
    Compute how much one column contributes to a group total; flag outlier rows.

    Designed for cost-breakdown tables where you want to know "what share of
    the total is operating cost?" and which stages / scenarios breach a
    healthy range.

    Args:
        df:               DataFrame with one row per stage / scenario.
        target_cost_col:  The column whose share we want (e.g. ``"Op. Cost"``).
        all_cost_cols:    All columns that together sum to the row total
                          (must include ``target_cost_col``).
        label_col:        Column used to label rows in the output
                          (e.g. ``"Etapas"`` or ``"Date"``).
        min_threshold:    Flag rows where ``target_share_pct < min_threshold``.
        max_threshold:    Flag rows where ``target_share_pct > max_threshold``.

    Returns:
        Dict with three sections:

        ``global_summary``
            Per-column totals, grand_total, target_total, other_costs_total.

        ``composition_metrics``
            target_share_of_total_pct, ratio_target_to_others.

        ``criticality_report``
            thresholds_used, total_critical_found, critical_scenarios list
            (each entry: label, percentage, status "Below Min" / "Above Max").

    Example::

        result = analyze_composition(
            df,
            target_cost_col="Costo: Total operativo",
            all_cost_cols=["Costo: Total operativo", "Pen: Vertimiento hidro"],
            label_col="Etapas",
            min_threshold=80.0,   # warn if operating cost < 80 %
        )
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    column_totals   = {c: float(df[c].sum()) for c in all_cost_cols}
    grand_total     = sum(column_totals.values())
    target_total    = column_totals.get(target_cost_col, 0.0)
    other_total     = grand_total - target_total
    global_share    = (target_total / grand_total * 100) if grand_total != 0 else 0.0

    work = df.copy()
    work["_row_total"]        = work[all_cost_cols].sum(axis=1)
    work["_target_share_pct"] = (
        work[target_cost_col] / work["_row_total"] * 100
    ).fillna(0)

    critical: list[dict] = []
    if min_threshold is not None or max_threshold is not None:
        mask = pd.Series([False] * len(df), index=df.index)
        if min_threshold is not None:
            mask |= work["_target_share_pct"] < min_threshold
        if max_threshold is not None:
            mask |= work["_target_share_pct"] > max_threshold

        for _, row in work[mask].iterrows():
            pct    = float(row["_target_share_pct"])
            status = (
                "Below Min" if (min_threshold is not None and pct < min_threshold)
                else "Above Max"
            )
            critical.append({"label": row[label_col], "percentage": pct, "status": status})

    return {
        "global_summary": {
            "all_column_totals": column_totals,
            "grand_total":       grand_total,
            "target_column":     target_cost_col,
            "target_total":      target_total,
            "other_costs_total": other_total,
        },
        "composition_metrics": {
            "target_share_of_total_pct": global_share,
            "ratio_target_to_others":    (
                target_total / other_total if other_total != 0 else 0.0
            ),
        },
        "criticality_report": {
            "thresholds_used":      {"min": min_threshold, "max": max_threshold},
            "total_critical_found": len(critical),
            "critical_scenarios":   critical,
        },
    }


# ---------------------------------------------------------------------------
# Stagnation detection
# ---------------------------------------------------------------------------

def analyze_stagnation(
    df: pd.DataFrame,
    target_col: str,
    window_size: int = 5,
    cv_threshold: float = 1.0,
    slope_threshold: float = 0.01,
) -> dict:
    """
    Detect whether a column has stopped changing over the most recent N rows.

    "Stagnated" means both low recent volatility (CV below ``cv_threshold``)
    AND negligible net movement (normalised slope below ``slope_threshold``).
    Useful for detecting cut-count plateaus, locked gaps, or any iterative
    series that is expected to keep improving.

    Args:
        df:               DataFrame (ordered, one row per iteration).
        target_col:       The column to monitor (e.g. ``"Optimality"``).
        window_size:      Number of most-recent rows to inspect. Default 5.
        cv_threshold:     Maximum coefficient of variation (%) for the recent
                          window to be called "stable". Default 1.0.
        slope_threshold:  Maximum |net_change / total_range| to be called
                          "flat". Default 0.01 (1 % of historical range).

    Returns:
        Dict with three sections:

        ``overall_stats``
            mean, std, cv_pct, min, max of the full series.

        ``recent_window``
            window_size, mean, std, cv_pct, net_change, normalized_change.

        ``stagnation_results``
            is_stagnated (bool), is_volatile (bool),
            status ("Stagnated" | "Active").

    Example::

        result = analyze_stagnation(
            df_cuts, target_col="Optimality", window_size=5
        )
    """
    if df.empty or len(df) < 2:
        return {"error": "Not enough data to analyse stagnation (need >= 2 rows)"}

    full   = df[target_col].astype(float)
    recent = full.tail(window_size)

    def _cv(s: pd.Series) -> float:
        m = s.mean()
        return (s.std() / m * 100) if m != 0 else 0.0

    global_cv  = _cv(full)
    recent_cv  = _cv(recent)

    net_change        = float(recent.iloc[-1] - recent.iloc[0])
    total_range       = float(full.max() - full.min())
    normalized_change = (net_change / total_range) if total_range != 0 else 0.0

    is_stable = recent_cv < cv_threshold
    is_flat   = abs(normalized_change) < slope_threshold

    return {
        "overall_stats": {
            "mean":   float(full.mean()),
            "std":    float(full.std()),
            "cv_pct": float(global_cv),
            "min":    float(full.min()),
            "max":    float(full.max()),
        },
        "recent_window": {
            "window_size":        window_size,
            "mean":               float(recent.mean()),
            "std":                float(recent.std()),
            "cv_pct":             float(recent_cv),
            "net_change":         net_change,
            "normalized_change":  normalized_change,
        },
        "stagnation_results": {
            "is_stagnated": is_stable and is_flat,
            "is_volatile":  recent_cv > global_cv,
            "status":       "Stagnated" if (is_stable and is_flat) else "Active",
        },
    }


# ---------------------------------------------------------------------------
# Cross-dataframe correlation (internal helper + public function)
# ---------------------------------------------------------------------------

def _calculate_linear_metrics(x: np.ndarray, y: np.ndarray) -> dict:
    """
    Fit y = a·x + b via OLS and return slope, intercept, R², and elasticity.

    elasticity = slope * mean(x) / mean(y)
    Interpretation: a 1 % change in x is associated with elasticity% change in y.
    """
    coeffs    = np.polyfit(x, y, 1)
    slope     = float(coeffs[0])
    intercept = float(coeffs[1])

    predicted = np.polyval(coeffs, x)
    ss_res    = float(np.sum((y - predicted) ** 2))
    ss_tot    = float(np.sum((y - y.mean()) ** 2))
    r2        = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    mean_x, mean_y = float(x.mean()), float(y.mean())
    elasticity = slope * (mean_x / mean_y) if mean_y != 0 else 0.0

    return {
        "slope":      slope,
        "intercept":  intercept,
        "r2":         r2,
        "elasticity": elasticity,
    }


def analyze_cross_correlation(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    col_a: str,
    col_b: str,
    join_on: str | None = None,
    output_csv_path: str | None = None,
) -> dict:
    """
    Correlate one column from df_a with one column from df_b.

    Aligns the two DataFrames either on a shared key column (``join_on``) or
    by row index.  Returns Pearson r, R², OLS slope, and elasticity at the
    mean.  Optionally exports a scatter-plot CSV with the regression line.

    Useful for ENA-vs-cost correlations where the two series live in separate
    CSV files.

    Args:
        df_a:             First DataFrame.
        df_b:             Second DataFrame.
        col_a:            Column name from ``df_a`` (independent variable, x).
        col_b:            Column name from ``df_b`` (dependent variable, y).
        join_on:          Column name present in both DataFrames to merge on
                          (e.g. ``"Etapas"``).  If ``None``, aligns by row index.
        output_csv_path:  If provided, saves a CSV with columns
                          [join_on / index, col_a, col_b, regression_line]
                          suitable for scatter-plot visualisation.
                          Pass ``None`` (default) to skip the export.

    Returns:
        Dict with four sections:

        ``alignment``
            matched_records, method used.

        ``correlation_metrics``
            pearson_r, r_squared, correlation_strength
            ("strong" / "moderate" / "weak").

        ``sensitivity``
            slope, elasticity_at_mean, human-readable interpretation.

        ``export``
            csv_saved (bool), path (str or None).

    Example::

        result = analyze_cross_correlation(
            df_disp, df_ena,
            col_a="Average",      # average ENA per stage
            col_b="Average",      # average cost per stage
            join_on="Etapas",
        )
    """
    if join_on:
        merged = pd.merge(
            df_a[[join_on, col_a]],
            df_b[[join_on, col_b]],
            on=join_on,
            suffixes=("_a", "_b"),
        ).dropna()
    else:
        merged = pd.concat(
            [df_a[col_a].rename("_a"), df_b[col_b].rename("_b")], axis=1
        ).dropna()
        col_a, col_b = "_a", "_b"

    if len(merged) < 3:
        return {"error": "Insufficient overlapping data after alignment (need >= 3 rows)."}

    x = merged[col_a].astype(float).values
    y = merged[col_b].astype(float).values

    metrics      = _calculate_linear_metrics(x, y)
    pearson_r    = float(np.corrcoef(x, y)[0, 1])
    abs_r        = abs(pearson_r)
    strength     = "strong" if abs_r > 0.7 else "moderate" if abs_r > 0.4 else "weak"

    csv_saved = False
    if output_csv_path:
        plot_df = merged.copy()
        plot_df["regression_line"] = metrics["slope"] * x + metrics["intercept"]
        plot_df.to_csv(output_csv_path, index=False)
        csv_saved = True

    return {
        "alignment": {
            "matched_records": len(merged),
            "method":          "join on key" if join_on else "row-index alignment",
        },
        "correlation_metrics": {
            "pearson_r":            pearson_r,
            "r_squared":            metrics["r2"],
            "correlation_strength": strength,
        },
        "sensitivity": {
            "slope":              metrics["slope"],
            "elasticity_at_mean": metrics["elasticity"],
            "interpretation": (
                f"A 1% increase in {col_a} is associated with a "
                f"{metrics['elasticity']:.4f}% change in {col_b}."
            ),
        },
        "export": {
            "csv_saved": csv_saved,
            "path":      output_csv_path,
        },
    }


# ---------------------------------------------------------------------------
# Heatmap / matrix analysis
# ---------------------------------------------------------------------------

#: Mapping from integer solver status code to human-readable label.
SOLVER_STATUS_LABELS: dict[int, str] = {
    0: "Optimal",
    1: "Feasible",
    2: "Relaxed",
    3: "No Solution",
}


def analyze_heatmap(
    df: pd.DataFrame,
    label_col: str | None = None,
    value_cols: list[str] | None = None,
    mode: str = "solver_status",
    threshold: float = 0.0,
    top_n: int = 10,
) -> dict:
    """
    Analyse a stage × scenario matrix and identify critical cells.

    Designed for two types of SDDP heatmap outputs:

    **Solver-status heatmap** (``mode="solver_status"``)
        Each cell is an integer 0–3:
        0 = Optimal, 1 = Feasible, 2 = Relaxed, 3 = No Solution.
        Critical cells are any cell with value > 0.

    **Penalty / continuous heatmap** (``mode="threshold"``)
        Each cell is a continuous value (e.g. penalty-participation %).
        Critical cells are any cell > ``threshold``.

    Args:
        df:         DataFrame where rows = stages and columns = scenarios
                    (plus an optional label column).
        label_col:  Name of the row-label column (e.g. ``"Stage"``).
                    If ``None`` or not found, uses the row integer index.
        value_cols: Explicit list of scenario column names.
                    If ``None``, auto-detects all numeric columns except
                    ``label_col``.
        mode:       ``"solver_status"`` (integer codes 0–3) or
                    ``"threshold"`` (continuous, compare against threshold).
        threshold:  Used only in ``"threshold"`` mode. Default 0.0.
        top_n:      Maximum number of entries in the ranked lists. Default 10.

    Returns:
        Dict with sections:

        ``summary``
            total_cells, critical_cells, critical_pct, n_stages, n_scenarios,
            mode (+ status_distribution for solver_status mode).

        ``top_critical_scenarios``
            Scenarios ranked by number of critical stages (descending).
            Each entry: scenario name, count, list of affected stage labels.

        ``top_critical_stages``
            Stages ranked by number of critical scenarios (descending).
            Each entry: stage label, count, list of affected scenario names.

    Example::

        result = analyze_heatmap(
            df_solver,
            label_col="Stage",
            mode="solver_status",
        )
        result = analyze_heatmap(
            df_penalty,
            label_col="Stage",
            mode="threshold",
            threshold=5.0,
        )
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    # --- Resolve value columns ---
    if value_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        value_cols = [c for c in numeric_cols if c != label_col]

    if not value_cols:
        return {"error": "No numeric value columns found. Specify value_cols explicitly."}

    # --- Row labels ---
    if label_col and label_col in df.columns:
        labels: list = df[label_col].tolist()
    else:
        labels = list(range(len(df)))

    data = df[value_cols].values.astype(float)   # shape: (n_stages, n_scenarios)
    n_stages, n_scenarios = data.shape

    # --- Critical mask ---
    if mode == "solver_status":
        critical_mask = data > 0
    else:
        critical_mask = data > threshold

    total_cells    = data.size
    critical_count = int(critical_mask.sum())
    critical_pct   = critical_count / total_cells * 100 if total_cells > 0 else 0.0

    # --- Solver status distribution (mode-specific) ---
    status_distribution: dict = {}
    if mode == "solver_status":
        unique_vals, counts = np.unique(data.astype(int), return_counts=True)
        for v, c in zip(unique_vals, counts):
            label = SOLVER_STATUS_LABELS.get(int(v), f"Status {int(v)}")
            status_distribution[label] = int(c)

    # --- Per-scenario summary ---
    scenario_counts: list[tuple[str, int, list[str]]] = []
    for col_idx, col_name in enumerate(value_cols):
        col_mask  = critical_mask[:, col_idx]
        cnt       = int(col_mask.sum())
        if cnt > 0:
            affected = [str(labels[r]) for r in range(n_stages) if col_mask[r]]
            scenario_counts.append((col_name, cnt, affected))
    scenario_counts.sort(key=lambda x: x[1], reverse=True)

    # --- Per-stage summary ---
    stage_counts: list[tuple[str, int, list[str]]] = []
    for row_idx, stage_label in enumerate(labels):
        row_mask = critical_mask[row_idx, :]
        cnt      = int(row_mask.sum())
        if cnt > 0:
            affected = [value_cols[c] for c in range(n_scenarios) if row_mask[c]]
            stage_counts.append((str(stage_label), cnt, affected))
    stage_counts.sort(key=lambda x: x[1], reverse=True)

    # --- Build result ---
    summary: dict = {
        "total_cells":    total_cells,
        "critical_cells": critical_count,
        "critical_pct":   critical_pct,
        "n_stages":       n_stages,
        "n_scenarios":    n_scenarios,
        "mode":           mode,
    }
    if mode == "solver_status":
        summary["status_distribution"] = status_distribution
    else:
        summary["threshold_applied"] = threshold

    return {
        "summary": summary,
        "top_critical_scenarios": [
            {
                "scenario":              name,
                "critical_stages_count": cnt,
                "affected_stages":       stages,
            }
            for name, cnt, stages in scenario_counts[:top_n]
        ],
        "top_critical_stages": [
            {
                "stage":                    stage,
                "critical_scenarios_count": cnt,
                "affected_scenarios":       scens,
            }
            for stage, cnt, scens in stage_counts[:top_n]
        ],
    }


# ---------------------------------------------------------------------------
# Threshold filtering (time-varying bar-chart data)
# ---------------------------------------------------------------------------

def filter_by_threshold(
    df: pd.DataFrame,
    threshold: float,
    label_col: str | None = None,
    value_cols: list[str] | None = None,
    direction: str = "above",
    top_n: int = 10,
) -> dict:
    """
    Find cells that exceed (or fall below) a threshold in a stage × agent table.

    Designed for bar-chart output files where rows represent time steps / stages
    and columns represent agents (penalties, generators, etc.).

    Args:
        df:         DataFrame with rows = stages, columns = agents.
        threshold:  Numeric boundary value.
        label_col:  Name of the row-label column (e.g. ``"Stage"``).
                    If ``None``, uses the row integer index.
        value_cols: Columns to inspect.  If ``None``, auto-detects all numeric
                    columns except ``label_col``.
        direction:  ``"above"`` (default) — flag cells > threshold.
                    ``"below"``           — flag cells < threshold.
        top_n:      Maximum entries in ranked output lists. Default 10.

    Returns:
        Dict with sections:

        ``summary``
            threshold, direction, total_exceedances, columns_checked,
            stages_with_exceedances.

        ``top_exceeding_columns``
            Columns ranked by exceedance count (descending).
            Each entry: column name, total_exceedances, max_value,
            mean_value_when_exceeded.

        ``by_stage``
            Per-stage list (limited to top_n stages with most exceedances).
            Each entry: stage label, list of {column, value} pairs that
            exceeded the threshold at that stage.

    Example::

        result = filter_by_threshold(
            df_penalties,
            threshold=5.0,
            label_col="Stage",
            direction="above",
        )
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    # --- Resolve columns ---
    if value_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        value_cols = [c for c in numeric_cols if c != label_col]

    if not value_cols:
        return {"error": "No numeric value columns found. Specify value_cols explicitly."}

    # --- Row labels ---
    if label_col and label_col in df.columns:
        labels: list = df[label_col].tolist()
    else:
        labels = list(range(len(df)))

    data = df[value_cols]

    if direction == "above":
        mask = data > threshold
    else:
        mask = data < threshold

    # --- Per-column summary ---
    col_stats: list[tuple[str, int, float, float]] = []
    for col in value_cols:
        cnt = int(mask[col].sum())
        exceeded_vals = data.loc[mask[col], col]
        max_val  = float(data[col].max())
        mean_exc = float(exceeded_vals.mean()) if not exceeded_vals.empty else 0.0
        col_stats.append((col, cnt, max_val, mean_exc))
    col_stats.sort(key=lambda x: x[1], reverse=True)

    # --- Per-stage breakdown ---
    stage_rows: list[tuple[int, str, list[dict]]] = []
    for i, stage_label in enumerate(labels):
        row_mask = mask.iloc[i]
        exceeded = [
            {"column": col, "value": float(data[col].iloc[i])}
            for col in value_cols
            if row_mask[col]
        ]
        if exceeded:
            exceeded.sort(key=lambda x: abs(x["value"]), reverse=True)
            stage_rows.append((len(exceeded), str(stage_label), exceeded))

    stage_rows.sort(key=lambda x: x[0], reverse=True)

    total_exceedances = sum(c[1] for c in col_stats)

    return {
        "summary": {
            "threshold":               threshold,
            "direction":               direction,
            "total_exceedances":       total_exceedances,
            "columns_checked":         len(value_cols),
            "stages_with_exceedances": len(stage_rows),
        },
        "top_exceeding_columns": [
            {
                "column":                col,
                "total_exceedances":     cnt,
                "max_value":             max_val,
                "mean_value_when_exceeded": mean_exc,
            }
            for col, cnt, max_val, mean_exc in col_stats[:top_n]
            if cnt > 0
        ],
        "by_stage": [
            {"stage": label, "exceeded": exc}
            for _, label, exc in stage_rows[:top_n]
        ],
    }



# ---------------------------------------------------------------------------
# Violation analysis (mean vs max / frequency / seasonality)
# ---------------------------------------------------------------------------

def _violation_mean_vs_max(
    df_mean: pd.DataFrame,
    df_max: pd.DataFrame,
    value_cols: list[str],
    labels: list,
    ratio_threshold: float,
    top_n: int,
) -> dict:
    """Internal: compare mean-violation file vs max-violation file."""
    shared_cols = [c for c in value_cols if c in df_max.columns]
    if not shared_cols:
        return {"error": "No matching columns between mean and max dataframes."}

    per_col: list[dict] = []
    systematic_count = 0

    for col in shared_cols:
        mean_vals = df_mean[col].astype(float).values
        max_vals  = df_max[col].astype(float).values
        n         = min(len(mean_vals), len(max_vals))

        # Per-row ratio where max > 0
        rows_with_violation = 0
        ratio_sum = 0.0
        for i in range(n):
            if max_vals[i] > 0:
                rows_with_violation += 1
                ratio_sum += mean_vals[i] / max_vals[i]

        avg_ratio = ratio_sum / rows_with_violation if rows_with_violation > 0 else 0.0
        is_systematic = avg_ratio >= ratio_threshold
        if is_systematic:
            systematic_count += 1

        per_col.append({
            "column":            col,
            "rows_with_violation": rows_with_violation,
            "avg_mean_max_ratio": round(avg_ratio, 4),
            "is_systematic":     is_systematic,
        })

    per_col.sort(key=lambda x: x["avg_mean_max_ratio"], reverse=True)
    n_cols = len(shared_cols)
    majority_systematic = systematic_count > n_cols / 2

    return {
        "analysis_type":   "mean_vs_max",
        "ratio_threshold": ratio_threshold,
        "summary": {
            "columns_analyzed":      n_cols,
            "systematic_violations": systematic_count,
            "systematic_pct":        round(systematic_count / n_cols * 100, 1) if n_cols else 0.0,
            "verdict":               "SYSTEMATIC" if majority_systematic else "WORST_CASE_ONLY",
            "interpretation": (
                "Most violations occur across the majority of scenarios, not just worst-case ones. "
                "Penalty value is likely too low globally — recalibrate upward."
                if majority_systematic else
                "Violations are concentrated in the worst-case scenarios. "
                "Penalty calibration may be acceptable; investigate extreme scenario drivers."
            ),
        },
        "top_columns": per_col[:top_n],
    }


def _violation_frequency(
    df: pd.DataFrame,
    value_cols: list[str],
    labels: list,
    violation_threshold: float,
    frequency_threshold: float,
    top_n: int,
) -> dict:
    """Internal: compute the proportion of stages with non-zero violations."""
    n_stages = len(df)
    per_col: list[dict] = []

    for col in value_cols:
        vals        = df[col].astype(float)
        n_violated  = int((vals > violation_threshold).sum())
        freq_pct    = n_violated / n_stages * 100 if n_stages > 0 else 0.0
        is_frequent = freq_pct >= frequency_threshold * 100

        per_col.append({
            "column":       col,
            "stages_with_violation": n_violated,
            "frequency_pct": round(freq_pct, 1),
            "is_frequent":  is_frequent,
        })

    per_col.sort(key=lambda x: x["frequency_pct"], reverse=True)
    frequent_count = sum(1 for c in per_col if c["is_frequent"])

    return {
        "analysis_type":        "frequency",
        "violation_threshold":  violation_threshold,
        "frequency_threshold_pct": frequency_threshold * 100,
        "summary": {
            "total_stages":              n_stages,
            "frequently_violated_cols":  frequent_count,
            "verdict":                   "FREQUENT" if frequent_count > 0 else "SPORADIC",
            "interpretation": (
                f"{frequent_count} column(s) have violations in ≥{frequency_threshold*100:.0f}% of stages. "
                "Persistent pattern suggests penalty value is too low — recalibrate globally."
                if frequent_count > 0 else
                "Violations are sporadic (< threshold in all columns). "
                "No persistent structural issue detected from frequency alone."
            ),
        },
        "top_columns": per_col[:top_n],
    }


def _violation_seasonality(
    df: pd.DataFrame,
    value_cols: list[str],
    labels: list,
    top_n: int,
) -> dict:
    """Internal: identify whether violations are concentrated in specific stages."""
    data          = df[value_cols].astype(float)
    stage_totals  = data.sum(axis=1).values
    total_viol    = float(stage_totals.sum())

    if total_viol == 0:
        return {
            "analysis_type": "seasonality",
            "summary": {
                "total_stages": len(labels),
                "total_violation": 0.0,
                "verdict": "NO_VIOLATIONS",
                "interpretation": "No violations found in any stage.",
            },
            "top_stages":    [],
            "bottom_stages": [],
        }

    # Rank stages by their total violation
    stage_info = sorted(
        zip(labels, stage_totals.tolist()),
        key=lambda x: x[1],
        reverse=True,
    )

    # How many stages account for 75% of total violation?
    cumulative = 0.0
    concentration_stages = 0
    for _, val in stage_info:
        cumulative += val
        concentration_stages += 1
        if cumulative >= 0.75 * total_viol:
            break

    # "Seasonal" = top 25% (or fewer) of stages hold 75% of violations
    cutoff       = max(1, len(labels) // 4)
    is_seasonal  = concentration_stages <= cutoff

    return {
        "analysis_type": "seasonality",
        "summary": {
            "total_stages":      len(labels),
            "total_violation":   round(total_viol, 4),
            "stages_for_75pct":  concentration_stages,
            "seasonal_cutoff":   cutoff,
            "verdict":           "SEASONAL" if is_seasonal else "SPREAD",
            "interpretation": (
                f"75% of total violations are concentrated in {concentration_stages} stage(s) "
                f"(cutoff={cutoff}). Violations are seasonal — recalibrate penalty for those specific periods."
                if is_seasonal else
                f"Violations are spread across {concentration_stages} stages before reaching 75% of total. "
                "No strong seasonal concentration detected."
            ),
        },
        "top_stages":    [{"stage": lbl, "total_violation": round(float(val), 4)} for lbl, val in stage_info[:top_n]],
        "bottom_stages": [{"stage": lbl, "total_violation": round(float(val), 4)} for lbl, val in stage_info[-top_n:]],
    }


def analyze_violation(
    df: pd.DataFrame,
    label_col: str | None = None,
    value_cols: list[str] | None = None,
    analysis_type: str = "frequency",
    df_max: pd.DataFrame | None = None,
    mean_max_ratio_threshold: float = 0.8,
    violation_threshold: float = 0.0,
    frequency_threshold: float = 0.5,
    top_n: int = 5,
) -> dict:
    """
    Unified violation analysis with three complementary lenses.

    Pass ``analysis_type`` to select which question to answer:

    **"mean_vs_max"** — Are violations systematic across scenarios or only in extremes?
        Requires ``df_max`` (the max-violation DataFrame).
        Computes the mean/max ratio per stage per column.
        If ratio ≥ ``mean_max_ratio_threshold`` for most columns → ``SYSTEMATIC``.
        Systematic violations usually mean the penalty is too low globally.

    **"frequency"** — Do violations occur in most time stages?
        Computes the share of stages where each column exceeds ``violation_threshold``.
        If share ≥ ``frequency_threshold`` → column is ``FREQUENT``.
        Frequent violations across many stages → persistent structural problem.

    **"seasonality"** — Are violations concentrated in specific periods?
        Sums violations per stage and checks whether ≤25% of stages hold ≥75%
        of total violations.
        ``SEASONAL`` result → recalibrate penalty only for those periods.
        ``SPREAD`` result → violations are diffuse, not period-specific.

    Args:
        df:                      Primary DataFrame (typically mean-violation CSV).
                                 Rows = stages, columns = violation types.
        label_col:               Column containing stage/period labels.
                                 If None, uses row index.
        value_cols:              Columns to analyse.  If None, auto-detects numeric
                                 columns (excluding ``label_col``).
        analysis_type:           ``"mean_vs_max"`` | ``"frequency"`` | ``"seasonality"``.
        df_max:                  Second DataFrame with max-violation values.
                                 Required only when ``analysis_type="mean_vs_max"``.
        mean_max_ratio_threshold: Ratio cutoff for "systematic" classification.
                                 Default 0.8.
        violation_threshold:     Minimum value to count as a violation in
                                 ``"frequency"`` mode.  Default 0.0.
        frequency_threshold:     Share of stages (0–1) above which a column is
                                 considered "frequently" violated.  Default 0.5.
        top_n:                   Maximum entries in ranked output lists. Default 5.

    Returns:
        Dict with ``analysis_type``, ``summary`` (verdict + interpretation),
        and per-column or per-stage details depending on mode.

    Example::

        # Frequency analysis
        result = analyze_violation(
            df_mean_violations,
            label_col="Etapas",
            analysis_type="frequency",
            frequency_threshold=0.5,
        )

        # Mean vs Max analysis
        result = analyze_violation(
            df_mean_violations,
            label_col="Etapas",
            analysis_type="mean_vs_max",
            df_max=df_max_violations,
            mean_max_ratio_threshold=0.8,
        )
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    # Resolve value columns
    if value_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        value_cols = [c for c in numeric_cols if c != label_col]

    if not value_cols:
        return {"error": "No numeric value columns found. Specify value_cols explicitly."}

    # Row labels
    if label_col and label_col in df.columns:
        labels: list = df[label_col].tolist()
    else:
        labels = list(range(len(df)))

    atype = analysis_type.strip().lower()

    if atype == "mean_vs_max":
        if df_max is None:
            return {"error": "df_max is required for analysis_type='mean_vs_max'. "
                             "Pass the max-violation DataFrame."}
        return _violation_mean_vs_max(
            df, df_max, value_cols, labels, mean_max_ratio_threshold, top_n
        )
    elif atype == "frequency":
        return _violation_frequency(
            df, value_cols, labels, violation_threshold, frequency_threshold, top_n
        )
    elif atype == "seasonality":
        return _violation_seasonality(df, value_cols, labels, top_n)
    else:
        return {
            "error": (
                f"Unknown analysis_type: {analysis_type!r}. "
                "Choose 'mean_vs_max', 'frequency', or 'seasonality'."
            )
        }


# ---------------------------------------------------------------------------
# CMO (Marginal Cost) distribution analysis
# ---------------------------------------------------------------------------

def analyze_cmo_distribution(
    df: pd.DataFrame,
    label_col: str | None = None,
    value_cols: list[str] | None = None,
    zero_tolerance: float = 0.01,
    top_n: int = 10,
) -> dict:
    """
    Analyse CMO (marginal operating cost) distribution across stages and scenarios.

    The input DataFrame has multiple rows per stage (one row per scenario):

        Etapas  | System_A | System_B
        2024-01 |   30.4   |   28.1
        2024-01 |   30.7   |   28.9
        2024-02 |    0.0   |   31.2
        ...

    Three complementary analyses are returned in a single call:

    **Zero detection** — stages/systems where CMO ≈ 0 (|v| ≤ zero_tolerance).
        A high proportion of near-zero values signals supply surplus.

    **Negative detection** — stages/systems where CMO < 0 (strictly below zero).
        Negative marginal costs occur when the model penalises excess generation.

    **Dispersion** — coefficient of variation (CV) of CMO per stage across scenarios.
        High CV signals price volatility driven by hydrological uncertainty.

    Args:
        df:             DataFrame with one row per (stage, scenario) pair.
        label_col:      Column identifying the stage / time period (e.g. "Etapas").
        value_cols:     CMO columns (one per system). Auto-detects numeric cols if None.
        zero_tolerance: Absolute threshold below which a CMO is treated as zero.
                        Default 0.01.
        top_n:          Maximum entries in ranked lists. Default 10.

    Returns:
        Dict with: overall_stats, findings, top_zero_stages,
        top_negative_stages, top_dispersed_stages.
    """
    if df.empty:
        return {"error": "DataFrame is empty"}

    if value_cols is None:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        value_cols = [c for c in numeric_cols if c != label_col]

    if not value_cols:
        return {"error": "No numeric value columns found. Specify value_cols explicitly."}

    overall_stats: dict = {}
    for col in value_cols:
        vals  = df[col].astype(float)
        total = len(vals)
        n_zero = int((vals.abs() <= zero_tolerance).sum())
        n_neg  = int((vals < -zero_tolerance).sum())
        overall_stats[col] = {
            "total_values":   total,
            "mean":           round(float(vals.mean()), 4),
            "std":            round(float(vals.std()), 4),
            "min":            round(float(vals.min()), 4),
            "max":            round(float(vals.max()), 4),
            "zero_count":     n_zero,
            "zero_pct":       round(n_zero / total * 100, 2) if total > 0 else 0.0,
            "negative_count": n_neg,
            "negative_pct":   round(n_neg / total * 100, 2) if total > 0 else 0.0,
        }

    has_zeros     = any(v["zero_count"]     > 0 for v in overall_stats.values())
    has_negatives = any(v["negative_count"] > 0 for v in overall_stats.values())

    per_stage: list[dict] = []
    if label_col and label_col in df.columns:
        for stage, group in df.groupby(label_col, sort=False):
            total_zero = 0
            total_neg  = 0
            cv_values: list[float] = []
            systems: dict = {}

            for col in value_cols:
                vals   = group[col].astype(float)
                n      = len(vals)
                mean_v = float(vals.mean())
                std_v  = float(vals.std()) if n > 1 else 0.0
                cv     = (std_v / abs(mean_v) * 100) if mean_v != 0 else 0.0
                n_zero = int((vals.abs() <= zero_tolerance).sum())
                n_neg  = int((vals < -zero_tolerance).sum())

                total_zero += n_zero
                total_neg  += n_neg
                cv_values.append(cv)

                systems[col] = {
                    "mean":           round(mean_v, 4),
                    "std":            round(std_v, 4),
                    "cv_pct":         round(cv, 2),
                    "min":            round(float(vals.min()), 4),
                    "max":            round(float(vals.max()), 4),
                    "zero_count":     n_zero,
                    "negative_count": n_neg,
                }

            per_stage.append({
                "stage":                stage,
                "n_scenarios":          len(group),
                "total_zero_count":     total_zero,
                "total_negative_count": total_neg,
                "mean_cv_pct":          round(float(np.mean(cv_values)), 2) if cv_values else 0.0,
                "systems":              systems,
            })

    zero_stages  = sorted([s for s in per_stage if s["total_zero_count"] > 0],
                          key=lambda s: s["total_zero_count"], reverse=True)[:top_n]
    neg_stages   = sorted([s for s in per_stage if s["total_negative_count"] > 0],
                          key=lambda s: s["total_negative_count"], reverse=True)[:top_n]
    disp_stages  = sorted(per_stage, key=lambda s: s["mean_cv_pct"], reverse=True)[:top_n]

    def _sys_zero(s: dict) -> dict:
        return {c: {"zero_count": s["systems"][c]["zero_count"], "mean": s["systems"][c]["mean"]}
                for c in value_cols if c in s["systems"]}

    def _sys_neg(s: dict) -> dict:
        return {c: {"negative_count": s["systems"][c]["negative_count"], "min": s["systems"][c]["min"]}
                for c in value_cols if c in s["systems"]}

    def _sys_disp(s: dict) -> dict:
        return {c: {"cv_pct": s["systems"][c]["cv_pct"],
                    "mean":   s["systems"][c]["mean"],
                    "std":    s["systems"][c]["std"]}
                for c in value_cols if c in s["systems"]}

    return {
        "overall_stats": overall_stats,
        "findings": {
            "has_zero_values":     has_zeros,
            "has_negative_values": has_negatives,
            "zero_tolerance_used": zero_tolerance,
        },
        "top_zero_stages": [
            {"stage": s["stage"], "total_zero_count": s["total_zero_count"], "systems": _sys_zero(s)}
            for s in zero_stages
        ],
        "top_negative_stages": [
            {"stage": s["stage"], "total_negative_count": s["total_negative_count"], "systems": _sys_neg(s)}
            for s in neg_stages
        ],
        "top_dispersed_stages": [
            {"stage": s["stage"], "mean_cv_pct": s["mean_cv_pct"], "systems": _sys_disp(s)}
            for s in disp_stages
        ],
    }

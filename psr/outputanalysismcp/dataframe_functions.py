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
            "is_inside_interval": is_inside,
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

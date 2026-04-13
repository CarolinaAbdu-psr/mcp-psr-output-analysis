#!/usr/bin/env python3
"""MCP server for PSR Output Analysis."""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .common import read_csv, read_csv_path
from .dataframe_functions import (
    get_column_names,
    get_data_summary,
    analyze_bounds_and_reference,
    analyze_composition,
    analyze_stagnation,
    analyze_cross_correlation,

)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"
_SKILLS_DIR   = _PACKAGE_ROOT / "sddp-output-skills"

RESULTS_FOLDER: Path = Path(".")

# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "PSR Output Analysis",
    instructions=(
        "You are an SDDP output analysis assistant. "
        "Analyse simulation results and explain them clearly. "
        "ALWAYS respond in the same language the user used in their question — "
        "tools and documentation are in English but your answers must match the user's language. "

        "## Standard workflow "
        "1. get_avaliable_results(study_path) — set the results folder. "
        "2. Convergence: analyse_policy_convergence() → analyse_policy_vs_simulation(). "
        "3. Cost: analyse_cost_health() → analyse_cost_dispersion() → analyse_penalty_participation() if needed. "
        "4. Performance: analyse_execution_time(). "
        "5. Knowledge: get_sddp_knowledge(topics, problems) when a diagnosis needs theoretical grounding. "
        "6. Charts: call the chart_* tools to dispatch visual graphs whenever you present numerical data. "

        "## Rules "
        "- Always call get_avaliable_results before any analysis tool. "
        "- Call analyse_policy_convergence before drawing conclusions about policy quality. "
        "- Respond in the user's language — not in English unless the user wrote in English. "
        "- Lead with conclusions; use tables for per-stage data. "
        "- See skill prompts (sddp_analyze, sddp_convergence, sddp_costs, sddp_performance) "
        "  for detailed step-by-step guidance. "
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_skill(folder: str) -> str:
    path = _SKILLS_DIR / folder / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.exists() else f"[Skill not found: {folder}]"


def _format_result(result: dict, title: str) -> str:
    """
    Render a nested result dict as indented plain text with a title header.
    Dicts become sections, scalars become key: value lines.
    """
    lines = [f"=== {title} ===", ""]

    def _render(d: dict, indent: int = 0) -> None:
        pad = "  " * indent
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{pad}[{k}]")
                _render(v, indent + 1)
            elif isinstance(v, list):
                lines.append(f"{pad}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        lines.append(f"{pad}  -")
                        _render(item, indent + 2)
                    else:
                        lines.append(f"{pad}  - {item}")
            elif isinstance(v, float):
                lines.append(f"{pad}{k}: {v:,.4f}")
            else:
                lines.append(f"{pad}{k}: {v}")

    _render(result)
    return "\n".join(lines)


def _load_csv(file_path: str) -> tuple[object, str | None]:
    """Return (df, error_str). error_str is None on success."""
    try:
        return read_csv_path(file_path), None
    except FileNotFoundError:
        return None, f"[Error] File not found: {file_path}"
    except Exception as exc:
        return None, f"[Error] Could not read file: {exc}"
    

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@mcp.tool()
def get_avaliable_results(study_path: str) -> list[str]:
    """Set the results folder and return the list of available CSV files."""
    global RESULTS_FOLDER
    RESULTS_FOLDER = Path(os.path.join(study_path, "results"))
    return [f.name for f in RESULTS_FOLDER.iterdir() if f.is_file()]

    
# ---------------------------------------------------------------------------
# SDDP Knowledge base
# ---------------------------------------------------------------------------

_KNOWLEDGE_FILES = ["policy.json", "simulation.json", "execution_time.json"]


@mcp.tool()
def list_sddp_knowledge() -> str:
    """
    List every entry in the SDDP knowledge base (id, topic, title, related_problems).

    Call once to discover what theory is available before calling
    get_sddp_knowledge(). Do NOT call on every turn.

    Returns a catalogue of all entries grouped by JSON file.
    """
    lines = ["=== SDDP KNOWLEDGE BASE CATALOGUE ===", ""]
    for fname in _KNOWLEDGE_FILES:
        path = KNOWLEDGE_DIR / fname
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            lines += [f"## {fname}", f"  [Error: {exc}]", ""]
            continue

        lines.append(f"## {fname}")
        for e in entries:
            related = ", ".join(e.get("related_problems", [])) or "—"
            lines += [
                f"  id       : {e['id']}",
                f"  topic    : {e.get('topic', '')}",
                f"  title    : {e.get('title', '')}",
                f"  problems : {related}",
                "",
            ]
    return "\n".join(lines)


@mcp.tool()
def get_sddp_knowledge(
    ids: list[str] | None = None,
    topics: list[str] | None = None,
    problems: list[str] | None = None,
) -> str:
    """
    Retrieve the full content of SDDP knowledge entries.

    Filters across all knowledge files and returns every entry that matches
    ANY of the given ids, topic strings, OR related_problem strings.
    Pass only the tags you need — do not request the entire knowledge base.

    Args:
        ids:      List of exact entry ids (e.g. ["sddp_convergence_theory"]).
        topics:   List of topic strings to match (e.g. ["convergence"]).
        problems: List of related_problem strings
                  (e.g. ["high_penalty_costs", "mip_complexity"]).

    Returns a formatted text block ready to embed in a response.
    """
    ids_set      = set(ids or [])
    topics_set   = set(topics or [])
    problems_set = set(problems or [])

    if not ids_set and not topics_set and not problems_set:
        return "[Error] Provide at least one of: ids, topics, or problems."

    lines: list[str] = []
    found = 0

    for fname in _KNOWLEDGE_FILES:
        path = KNOWLEDGE_DIR / fname
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        for e in entries:
            match = (
                e.get("id") in ids_set
                or e.get("topic") in topics_set
                or bool(set(e.get("related_problems", [])) & problems_set)
            )
            if not match:
                continue

            found += 1
            refs = "\n".join(
                f"  - {r['title']} ({r['url']})"
                for r in e.get("references", [])
            )
            lines += [
                f"### {e['title']}",
                f"id: {e['id']}  |  topic: {e.get('topic', '')}",
                "",
                e["content"],
                "",
            ]
            if refs:
                lines += ["**References:**", refs, ""]
            lines.append("---")

    if found == 0:
        return "[No knowledge entries matched the provided ids / topics / problems.]"

    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Generic DataFrame tools
# ---------------------------------------------------------------------------

@mcp.tool()
def df_get_columns(file_path: str) -> str:
    """
    List all column names in a CSV file.

    Call this first when working with an unfamiliar file to discover available
    columns before choosing which ones to pass to the other df_* tools.

    Args:
        file_path: Absolute path to the CSV file.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    cols  = get_column_names(df)
    lines = [
        f"=== COLUMNS — {Path(file_path).name} ===",
        "",
        f"  Total columns: {len(cols)}",
        "",
    ]
    for i, c in enumerate(cols, 1):
        lines.append(f"  {i:>3}. {c}")
    return "\n".join(lines)


@mcp.tool()
def df_get_summary(file_path: str, operations_json: str) -> str:
    """
    Compute statistics (mean / std / min / max) on selected columns.

    Args:
        file_path:        Absolute path to the CSV file.
        operations_json:  JSON object mapping column names to lists of
                          operations.  Example:
                          '{"Forward": ["mean", "std"], "Backward": ["mean"]}'

    Supported operations: mean, std, min, max.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    try:
        operations_dict = json.loads(operations_json)
    except json.JSONDecodeError as exc:
        return f"[Error] Invalid JSON in operations_json: {exc}"

    result = get_data_summary(df, operations_dict)
    return _format_result(result, f"DATA SUMMARY — {Path(file_path).name}")


@mcp.tool()
def df_analyze_bounds(
    file_path: str,
    target_col: str,
    lower_bound_col: str,
    upper_bound_col: str,
    reference_val_col: str,
    iteration_col: str = "",
    lock_threshold: float = 0.005,
) -> str:
    """
    Check whether a value converges inside a [low, high] band and tracks
    accuracy relative to a reference value over iterations.

    Use for any convergence file where a tracked value should enter a
    tolerance band (e.g. Zinf vs Zsup ± Tol, simulation vs policy band).

    Args:
        file_path:          Absolute path to the CSV file.
        target_col:         Column being tracked (e.g. "Zinf").
        lower_bound_col:    Column with the lower edge of the band.
        upper_bound_col:    Column with the upper edge of the band.
        reference_val_col:  Column with the reference / expected value.
        iteration_col:      Column identifying the iteration number (optional).
        lock_threshold:     Gap-change % below which the run is "locked".
                            Default 0.005.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = analyze_bounds_and_reference(
        df,
        target_col=target_col,
        lower_bound_col=lower_bound_col,
        upper_bound_col=upper_bound_col,
        reference_val_col=reference_val_col,
        iteration_col=iteration_col or None,
        lock_threshold=lock_threshold,
    )
    return _format_result(result, f"BOUNDS & REFERENCE ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_analyze_composition(
    file_path: str,
    target_cost_col: str,
    all_cost_cols_json: str,
    label_col: str,
    min_threshold: float = 0.0,
    max_threshold: float = 0.0,
) -> str:
    """
    Compute the share of one column inside a group total; flag outlier rows.

    Use this to check whether one cost category dominates (or is too small)
    relative to a set of columns that together form the total.

    Args:
        file_path:           Absolute path to the CSV file.
        target_cost_col:     The column whose share to analyse
                             (e.g. "Costo: Total operativo").
        all_cost_cols_json:  JSON array of ALL columns that sum to the row
                             total (must include target_cost_col).
                             Example: '["Costo: Total operativo", "Pen: X"]'
        label_col:           Column that labels rows in the output
                             (e.g. "Etapas").
        min_threshold:       Flag rows where share < this value (%). Pass 0
                             to disable the lower threshold.
        max_threshold:       Flag rows where share > this value (%). Pass 0
                             to disable the upper threshold.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    try:
        all_cost_cols = json.loads(all_cost_cols_json)
    except json.JSONDecodeError as exc:
        return f"[Error] Invalid JSON in all_cost_cols_json: {exc}"

    result = analyze_composition(
        df,
        target_cost_col=target_cost_col,
        all_cost_cols=all_cost_cols,
        label_col=label_col,
        min_threshold=min_threshold if min_threshold != 0.0 else None,
        max_threshold=max_threshold if max_threshold != 0.0 else None,
    )
    return _format_result(result, f"COMPOSITION ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_analyze_stagnation(
    file_path: str,
    target_col: str,
    window_size: int = 5,
    cv_threshold: float = 1.0,
    slope_threshold: float = 0.01,
) -> str:
    """
    Detect whether a column has stopped improving over the most recent N rows.

    Use on any iterative metric expected to keep changing (cut counts, gap %,
    objective values).  Returns overall stats, recent-window stats, and a
    clear "Stagnated / Active" verdict.

    Args:
        file_path:        Absolute path to the CSV file.
        target_col:       Column to monitor (e.g. "Optimality").
        window_size:      Number of most-recent rows to inspect. Default 5.
        cv_threshold:     Max CV (%) for the window to be "stable". Default 1.0.
        slope_threshold:  Max |net_change / total_range| to be "flat".
                          Default 0.01.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = analyze_stagnation(
        df,
        target_col=target_col,
        window_size=window_size,
        cv_threshold=cv_threshold,
        slope_threshold=slope_threshold,
    )
    return _format_result(result, f"STAGNATION ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_cross_correlation(
    file_path_a: str,
    file_path_b: str,
    col_a: str,
    col_b: str,
    join_on: str = "",
    output_csv_path: str = "",
) -> str:
    """
    Correlate one column from file A with one column from file B.

    Returns Pearson r, R², OLS slope, and elasticity at the mean.
    Optionally exports a scatter-plot CSV with the fitted regression line.

    Use for ENA-vs-cost correlation or any two series from separate files.

    Args:
        file_path_a:      Absolute path to the first CSV (x variable).
        file_path_b:      Absolute path to the second CSV (y variable).
        col_a:            Column name in file A (independent variable).
        col_b:            Column name in file B (dependent variable).
        join_on:          Shared key column to merge on (e.g. "Etapas").
                          Leave empty to align by row index.
        output_csv_path:  If provided, saves a scatter-plot CSV to this path.
                          Leave empty to skip the export.
    """
    df_a, err = _load_csv(file_path_a)
    if err:
        return err
    df_b, err = _load_csv(file_path_b)
    if err:
        return err

    result = analyze_cross_correlation(
        df_a, df_b,
        col_a=col_a,
        col_b=col_b,
        join_on=join_on or None,
        output_csv_path=output_csv_path or None,
    )
    title = (
        f"CROSS-CORRELATION — {Path(file_path_a).name} [{col_a}] "
        f"vs {Path(file_path_b).name} [{col_b}]"
    )
    return _format_result(result, title)


# ---------------------------------------------------------------------------
# Prompts (slash commands)
# ---------------------------------------------------------------------------

@mcp.prompt()
def sddp_analyze(study_path: str) -> str:
    """
    Complete SDDP output analysis: convergence, policy vs simulation,
    cost health, cost dispersion + ENA correlation, penalty participation,
    and execution time. Pass the path to the SDDP case folder.
    """
    skill = _load_skill("sddp-analyze")
    return f"{skill}\n\n---\nCase path provided by user: `{study_path}`"


@mcp.prompt()
def sddp_convergence(study_path: str) -> str:
    """
    Check SDDP policy convergence and validate the final simulation
    against the policy confidence band. Pass the SDDP case folder path.
    """
    skill = _load_skill("sddp-convergence")
    return f"{skill}\n\n---\nCase path provided by user: `{study_path}`"


@mcp.prompt()
def sddp_costs(study_path: str) -> str:
    """
    Deep-dive into SDDP simulation costs: 80% health check, P10-P90
    dispersion with ENA elasticity, and penalty participation by scenario.
    Pass the SDDP case folder path.
    """
    skill = _load_skill("sddp-costs")
    return f"{skill}\n\n---\nCase path provided by user: `{study_path}`"


@mcp.prompt()
def sddp_performance(study_path: str) -> str:
    """
    Analyse SDDP computational performance: iteration time growth,
    Forward/Backward balance, and stage-level timing hot-spots.
    Pass the SDDP case folder path.
    """
    skill = _load_skill("sddp-performance")
    return f"{skill}\n\n---\nCase path provided by user: `{study_path}`"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()

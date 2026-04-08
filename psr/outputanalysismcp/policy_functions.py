"""
SDDP policy convergence analysis functions.

Public API
----------
load_convergence_data(results_folder)    -> (df, df_cuts)
check_convergence(df)                    -> dict
analyse_gap_trend(df)                    -> dict
analyse_cuts(df_cuts, tail_n)            -> dict
build_convergence_report(results_folder) -> str
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd
import os 
import json
from .cost_functions import load_cost_data, analyse_cost_portions
from .common import read_csv


_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"

# Thresholds — centralised here so any future tool can import them directly.
LOCK_THRESHOLD   = 0.005  # % absolute gap change — below this the run is "locked"
CUT_CV_THRESHOLD = 5.0    # % coefficient of variation — below this cuts are "stable"


# ---------------------------------------------------------------------------
# Data and documentation loading
# ---------------------------------------------------------------------------

def load_convergence_data(results_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load convergencia.csv and nuevos-cortes-por-iterac.csv."""
    df      = read_csv(results_folder, "convergencia.csv")
    df_cuts = read_csv(results_folder, "nuevos-cortes-por-iterac.csv")
    return df, df_cuts

def load_policy_vs_simulation_data(results_folder: Path):
    df      = read_csv(results_folder, "poltica-x-funciones-obje.csv")
    return df


def get_json_info(json_filename, target_id):
    # Set the path to your folder here 
    file_path = os.path.join(KNOWLEDGE_DIR, json_filename)  
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
            
        # Locate the specific ID in the list
        entry = next((item for item in data if item.get("id") == target_id), None)
        
        if not entry:
            return f"Error: ID '{target_id}' not found in {json_filename}."

        # Construct the text output
        text_output = (
            f"### {entry['title']}\n\n"
            f"**Content:**\n{entry['content']}\n\n"
            f"**References:**\n"
        )
        
        for ref in entry.get('references', []):
            text_output += f"- {ref['title']} ({ref['url']})\n"
            
        return text_output

    except FileNotFoundError:
        return f"Error: The file '{json_filename}' was not found in {KNOWLEDGE_DIR}."
    except json.JSONDecodeError:
        return f"Error: '{json_filename}' is not a valid JSON file."

# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def check_convergence(df: pd.DataFrame) -> dict:
    """
    Determine whether the last iteration converged.

    Returns a dict with:
        total_iters, last_iter, zinf, zsup, tol_low, tol_high, converged
    """
    last = df.iloc[-1]
    zinf     = last["Zinf"]
    zsup     = last["Zsup"]
    tol_low  = last["Zsup +- Tol (low)"]
    tol_high = last["Zsup +- Tol (high)"]
    return {
        "total_iters": len(df),
        "last_iter":   int(last["Iteration"]),
        "zinf":        zinf,
        "zsup":        zsup,
        "tol_low":     tol_low,
        "tol_high":    tol_high,
        "converged":   tol_low <= zinf <= tol_high,
    }


def analyse_gap_trend(df: pd.DataFrame) -> dict:
    """
    Compute the Zsup-Zinf gap trend over all iterations.

    Returns a dict with:
        df_with_gap, first_gap_pct, last_gap_pct, total_reduction,
        tail_n, recent_change, recent_avg_gap, is_locked
    """
    df = df.copy()
    df["gap"]     = df["Zsup"] - df["Zinf"]
    df["gap_pct"] = df["gap"] / df["Zsup"] * 100

    total_iters     = len(df)
    first_gap_pct   = df["gap_pct"].iloc[0]
    last_gap_pct    = df["gap_pct"].iloc[-1]
    total_reduction = first_gap_pct - last_gap_pct

    tail_n         = max(2, min(10, total_iters // 2))
    recent         = df.tail(tail_n)
    recent_change  = recent["gap_pct"].iloc[0] - recent["gap_pct"].iloc[-1]
    recent_avg_gap = recent["gap_pct"].mean()

    return {
        "df_with_gap":     df,
        "first_gap_pct":   first_gap_pct,
        "last_gap_pct":    last_gap_pct,
        "total_reduction": total_reduction,
        "tail_n":          tail_n,
        "recent_change":   recent_change,
        "recent_avg_gap":  recent_avg_gap,
        "is_locked":       abs(recent_change) < LOCK_THRESHOLD,
    }


def analyse_cuts(df_cuts: pd.DataFrame, tail_n: int) -> dict:
    """
    Compute new-cuts-per-iteration statistics.

    Returns overall and recent-window stats, plus a boolean 'cuts_stable'.
    """
    cuts_all    = df_cuts["Optimality"]
    cuts_mean   = cuts_all.mean()
    cuts_std    = cuts_all.std()
    cuts_cv     = cuts_std / cuts_mean * 100 if cuts_mean else 0

    recent      = df_cuts.tail(tail_n)["Optimality"]
    recent_mean = recent.mean()
    recent_std  = recent.std()
    recent_cv   = recent_std / recent_mean * 100 if recent_mean else 0

    return {
        "df_cuts":     df_cuts,
        "cuts_mean":   cuts_mean,
        "cuts_std":    cuts_std,
        "cuts_cv":     cuts_cv,
        "cuts_min":    int(cuts_all.min()),
        "cuts_max":    int(cuts_all.max()),
        "recent_mean": recent_mean,
        "recent_std":  recent_std,
        "recent_cv":   recent_cv,
        "cuts_stable": recent_cv < CUT_CV_THRESHOLD,
    }

def analyse_simulation_vs_policy(df: pd.DataFrame) -> dict:
    """
    Check whether the final simulation result falls inside the
    Zsup (IC+FCF) ± Tol confidence band on the last iteration.

    The CSV (poltica-x-funciones-obje.csv) has one row per policy iteration:
        Category                    — iteration number
        Zsup (IC+FCF)               — upper bound (confidence interval + FCF)
        Zsup (IC+FCF) +- Tol (low)  — lower edge of the tolerance band
        Zsup (IC+FCF) +- Tol (high) — upper edge of the tolerance band
        Final simulation            — final simulation expected cost (same for all rows)

    The check is performed on the LAST iteration row (the most up-to-date band).

    Returns a dict with:
        last_iter       — iteration index of the last row
        zsup_ic_fcf     — Zsup (IC+FCF) on the last iteration
        tol_low         — lower tolerance bound
        tol_high        — upper tolerance bound
        final_sim       — Final simulation value
        inside_band     — bool: True if tol_low <= final_sim <= tol_high
        deviation       — absolute distance to the nearest band edge (0 if inside)
        deviation_pct   — deviation as % of zsup_ic_fcf
        direction       — "below" | "above" | "inside"
        iteration_table — list of dicts with per-iteration values (for a summary table)
    """
    last = df.iloc[-1]

    zsup_ic_fcf = last["Zsup (IC+FCF)"]
    tol_low     = last["Zsup (IC+FCF) +- Tol (low)"]
    tol_high    = last["Zsup (IC+FCF) +- Tol (high)"]
    final_sim   = last["Final simulation"]

    inside_band = tol_low <= final_sim <= tol_high

    if inside_band:
        deviation = 0.0
        direction = "inside"
    elif final_sim < tol_low:
        deviation = tol_low - final_sim
        direction = "below"
    else:
        deviation = final_sim - tol_high
        direction = "above"

    deviation_pct = deviation / zsup_ic_fcf * 100 if zsup_ic_fcf else 0.0

    # Build a lightweight per-iteration summary so the report can show a table
    iteration_table = [
        {
            "iteration":  int(row["Category"]),
            "zsup_ic_fcf": row["Zsup (IC+FCF)"],
            "tol_low":    row["Zsup (IC+FCF) +- Tol (low)"],
            "tol_high":   row["Zsup (IC+FCF) +- Tol (high)"],
            "final_sim":  row["Final simulation"],
            "inside":     row["Zsup (IC+FCF) +- Tol (low)"] <= row["Final simulation"] <= row["Zsup (IC+FCF) +- Tol (high)"],
        }
        for _, row in df.iterrows()
    ]

    return {
        "last_iter":       int(last["Category"]),
        "zsup_ic_fcf":     zsup_ic_fcf,
        "tol_low":         tol_low,
        "tol_high":        tol_high,
        "final_sim":       final_sim,
        "inside_band":     inside_band,
        "deviation":       deviation,
        "deviation_pct":   deviation_pct,
        "direction":       direction,
        "iteration_table": iteration_table,
    }




# ---------------------------------------------------------------------------
# Logic graph 
# ---------------------------------------------------------------------------
def get_policy_error_report(results_folder: Path):
    df, df_cuts = load_convergence_data(results_folder)
    convergence_info = check_convergence(df)

    basic_info = [
        "=== SDDP POLICY CONVERGENCE ANALYSIS ===",
        f"Total iterations run : {convergence_info['total_iters']}",
        f"Last iteration       : {convergence_info['last_iter']}",
        "",
        "[ LAST ITERATION VALUES ]",
        f"  Zinf              = {convergence_info['zinf']:>18,.2f}",
        f"  Zsup              = {convergence_info['zsup']:>18,.2f}",
        f"  Zsup - Tol (low)  = {convergence_info['tol_low']:>18,.2f}",
        f"  Zsup + Tol (high) = {convergence_info['tol_high']:>18,.2f}",
        "",
        f"CONVERGENCE STATUS: {'CONVERGED' if convergence_info['converged'] else 'NOT CONVERGED'}",
    ]

    knowledge_header = [
        "",
        "=" * 80,
        "SDDP KNOWLEDGE",
        "=" * 80,
        "",
    ]
    basic_knowledge = [
        get_json_info("policy.json", "sddp_convergence_theory"),
        get_json_info("policy.json", "sddp_convergence_criteria"),
    ]

    # Converged
    if convergence_info["converged"]:
        lines = basic_info + knowledge_header + basic_knowledge
        return "\n".join(lines)

    # Not converged
    error = []
    zinf, zsup, tol_low, tol_high = (
        convergence_info["zinf"], convergence_info["zsup"],
        convergence_info["tol_low"], convergence_info["tol_high"],
    )
    miss_dir = (
        f"Zinf is BELOW the lower tolerance bound by {tol_low - zinf:,.2f} "
        f"({(tol_low - zinf) / zsup * 100:.4f}% of Zsup)."
    )
    error += ["Zinf is OUTSIDE the Zsup +/- tolerance band on the last iteration.", miss_dir]

    # Gap and cuts info
    gap    = analyse_gap_trend(df)
    tail_n = gap["tail_n"]
    cuts   = analyse_cuts(df_cuts, tail_n)

    # Cross-check cost health
    df_portions, df_stages = load_cost_data(results_folder)
    portions    = analyse_cost_portions(df_portions)
    grand_total = portions["grand_total"]
    op_value    = portions["op_value"]
    op_share    = portions["op_share"]

    def _build_report(extra_error_lines: list[str], knowledge_id: str) -> str:
        extra_knowledge = [get_json_info("policy.json", knowledge_id)]
        lines = (
            basic_info
            + error
            + extra_error_lines
            + knowledge_header
            + basic_knowledge
            + [""]
            + extra_knowledge
        )
        return "\n".join(lines)

    # Gap locked + cuts stable + high penalties
    if gap["is_locked"] and cuts["cuts_stable"] and not portions["health_ok"]:
        extra = [
            f"  The gap changed less than {LOCK_THRESHOLD}% over the last {tail_n} iterations.",
            "  The Zinf and Zsup bounds are no longer approaching each other.",
            f"  CUT STABILITY: STABLE (CV < {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
            "  The number of new cuts per iteration is consistent.",
            "  Combined with a locked gap, this strongly suggests the algorithm has stalled:",
            "  cuts are being added but they are not improving the lower bound.",
            "  Penalties values are too high",
            f"  Total penalties : {grand_total - op_value:>18,.2f}  ({100 - op_share:.1f}%)",
        ]
        return _build_report(extra, "sddp_non_convergence_stagnation_penalty")

    # Gap locked + cuts stable + healthy costs
    if gap["is_locked"] and cuts["cuts_stable"] and portions["health_ok"]:
        extra = [
            f"  The gap changed less than {LOCK_THRESHOLD}% over the last {tail_n} iterations.",
            "  The Zinf and Zsup bounds are no longer approaching each other.",
            f"  CUT STABILITY: STABLE (CV < {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
            "  The number of new cuts per iteration is consistent.",
            "  Combined with a locked gap, this strongly suggests the algorithm has stalled:",
            "  cuts are being added but they are not improving the lower bound.",
        ]
        return _build_report(extra, "sddp_non_convergence_stagnation_forward")

    # Gap still reducing — more iterations needed
    if not gap["is_locked"]:
        extra = [
            f"  The gap is still reducing (change = {gap['recent_change']:+.4f}% in last {tail_n} iters).",
        ]
        return _build_report(extra, "sddp_non_convergence_insufficient_iterations")


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_convergence_data_report(results_folder: Path) -> str:
    """
    Full convergence report as a structured text string for the LLM.

    Orchestrates: load → check_convergence → analyse_gap_trend → analyse_cuts.
    """
    df, df_cuts = load_convergence_data(results_folder)
    conv        = check_convergence(df)

    lines = [
        "=== SDDP POLICY CONVERGENCE ANALYSIS ===",
        f"Total iterations run : {conv['total_iters']}",
        f"Last iteration       : {conv['last_iter']}",
        "",
        "[ LAST ITERATION VALUES ]",
        f"  Zinf              = {conv['zinf']:>18,.2f}",
        f"  Zsup              = {conv['zsup']:>18,.2f}",
        f"  Zsup - Tol (low)  = {conv['tol_low']:>18,.2f}",
        f"  Zsup + Tol (high) = {conv['tol_high']:>18,.2f}",
        "",
        f"CONVERGENCE STATUS: {'CONVERGED' if conv['converged'] else 'NOT CONVERGED'}",
    ]

    if conv["converged"]:
        lines += [
            "",
            "Zinf is INSIDE the Zsup ± tolerance band on the last iteration.",
            "The policy has successfully converged. No further analysis needed.",
        ]
        return "\n".join(lines)

    # Direction of miss
    zinf, zsup, tol_low, tol_high = (
        conv["zinf"], conv["zsup"], conv["tol_low"], conv["tol_high"]
    )
    if zinf < tol_low:
        miss_dir = (
            f"Zinf is BELOW the lower tolerance bound by {tol_low - zinf:,.2f} "
            f"({(tol_low - zinf) / zsup * 100:.4f}% of Zsup)."
        )
    else:
        miss_dir = (
            f"Zinf is ABOVE the upper tolerance bound by {zinf - tol_high:,.2f} "
            f"({(zinf - tol_high) / zsup * 100:.4f}% of Zsup)."
        )

    lines += ["", "Zinf is OUTSIDE the Zsup ± tolerance band on the last iteration.", miss_dir]

    # Gap trend
    gap    = analyse_gap_trend(df)
    tail_n = gap["tail_n"]

    lines += [
        "",
        "--- ZINF / ZSUP APPROXIMATION (GAP) ANALYSIS ---",
        "  Gap = Zsup - Zinf expressed as % of Zsup.",
        f"  Iteration 1  gap : {gap['first_gap_pct']:.4f}%",
        f"  Iteration {conv['last_iter']} gap : {gap['last_gap_pct']:.4f}%",
        f"  Total reduction  : {gap['total_reduction']:.4f}%",
        "",
        f"  Recent trend (last {tail_n} iterations):",
        f"    Gap change  : {gap['recent_change']:+.4f}%  (positive = improving)",
        f"    Average gap : {gap['recent_avg_gap']:.4f}%",
        "",
    ]
    if gap["is_locked"]:
        lines += [
            f"  LOCKED: YES — The gap changed less than {LOCK_THRESHOLD}% over the last {tail_n} iterations.",
            "  The Zinf and Zsup bounds are no longer approaching each other.",
        ]
    else:
        lines += [
            f"  LOCKED: NO — The gap is still reducing (change = {gap['recent_change']:+.4f}% in last {tail_n} iters).",
        ]

    # Gap table
    df_g = gap["df_with_gap"]
    lines += [
        "",
        f"  Gap per iteration (last {min(10, conv['total_iters'])}):",
        f"  {'Iter':>5} | {'Zinf':>14} | {'Zsup':>14} | {'Gap %':>8}",
        "  " + "-" * 50,
    ]
    for _, row in df_g.tail(10).iterrows():
        lines.append(
            f"  {int(row['Iteration']):>5} | {row['Zinf']:>14,.0f} | {row['Zsup']:>14,.0f} | {row['gap_pct']:>8.4f}%"
        )

    # Cuts
    cuts = analyse_cuts(df_cuts, tail_n)

    lines += [
        "",
        "--- CUTS PER ITERATION ANALYSIS ---",
        "  'Optimality' column = number of new Benders cuts added each iteration.",
        f"  Overall ({conv['total_iters']} iterations):",
        f"    Mean : {cuts['cuts_mean']:.1f} cuts/iter",
        f"    Std  : {cuts['cuts_std']:.1f}",
        f"    CV   : {cuts['cuts_cv']:.1f}%  (coefficient of variation)",
        f"    Min  : {cuts['cuts_min']}   Max: {cuts['cuts_max']}",
        "",
        f"  Last {tail_n} iterations:",
        f"    Mean : {cuts['recent_mean']:.1f}   Std: {cuts['recent_std']:.1f}   CV: {cuts['recent_cv']:.1f}%",
        "",
    ]
    if cuts["cuts_stable"]:
        lines += [
            f"  CUT STABILITY: STABLE (CV < {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
        ]
    else:
        lines += [
            f"  CUT STABILITY: VARIABLE (CV >= {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
        ]

    # Cuts table
    lines += [
        "",
        f"  Cuts per iteration (last {min(10, conv['total_iters'])}):",
        f"  {'Iter':>5} | {'Cuts (Optimality)':>18}",
        "  " + "-" * 28,
    ]
    for _, row in cuts["df_cuts"].tail(10).iterrows():
        lines.append(f"  {int(row['Iteration']):>5} | {int(row['Optimality']):>18}")

    # LLM diagnosis summary
    lines += [
        "",
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Convergence: NOT CONVERGED after {conv['total_iters']} iterations.",
        f"- Final gap (Zsup - Zinf) / Zsup = {gap['last_gap_pct']:.4f}%.",
        f"- Locked: {'YES' if gap['is_locked'] else 'NO'} "
        f"(gap changed {gap['recent_change']:+.4f}% in last {tail_n} iters; threshold = {LOCK_THRESHOLD}%).",
        f"- Cuts stable: {'YES' if cuts['cuts_stable'] else 'NO'} "
        f"(recent CV = {cuts['recent_cv']:.1f}%; threshold = {CUT_CV_THRESHOLD}%).",
    ]

    return "\n".join(lines)

def build_simulation_vs_policy_report(results_folder: Path) -> str:
    """
    Structured report comparing the final simulation against the policy's
    Zsup (IC+FCF) ± Tol confidence band.

    Sections:
        1. Numerical results — status, values, deviation, per-iteration table.
        2. SDDP knowledge — three entries loaded from policy.json that explain
           why divergence happens and what to do about it.
        3. LLM diagnosis summary — flags for the LLM to pick the right explanation.
    """
    df  = load_policy_vs_simulation_data(results_folder)
    res = analyse_simulation_vs_policy(df)

    # Section 1 — Numerical results
    status_label = "INSIDE BAND [OK]" if res["inside_band"] else "OUTSIDE BAND [!!]"

    lines = [
        "=== POLICY vs. FINAL SIMULATION ANALYSIS ===",
        "",
        "[ LAST ITERATION VALUES ]",
        f"  Iteration            : {res['last_iter']}",
        f"  Zsup (IC+FCF)        : {res['zsup_ic_fcf']:>18,.2f}",
        f"  Tol band low         : {res['tol_low']:>18,.2f}",
        f"  Tol band high        : {res['tol_high']:>18,.2f}",
        f"  Final simulation     : {res['final_sim']:>18,.2f}",
        "",
        f"STATUS: {status_label}",
    ]

    if res["inside_band"]:
        lines += [
            "",
            "The final simulation expected cost falls within the policy's confidence band.",
            "The operating policy is consistent with the simulation results.",
        ]
    else:
        dir_map = {
            "above": f"Final simulation is ABOVE the upper bound by {res['deviation']:,.2f} ({res['deviation_pct']:.2f}% of Zsup IC+FCF).",
            "below": f"Final simulation is BELOW the lower bound by {res['deviation']:,.2f} ({res['deviation_pct']:.2f}% of Zsup IC+FCF).",
        }
        lines += ["", dir_map[res["direction"]]]

    # Per-iteration table (last 10)
    table = res["iteration_table"][-10:]
    lines += [
        "",
        f"  {'Iter':>5} | {'Zsup IC+FCF':>15} | {'Tol Low':>15} | {'Tol High':>15} | {'Final Sim':>18} | {'In Band':>8}",
        "  " + "-" * 85,
    ]
    for row in table:
        flag = "YES" if row["inside"] else "NO"
        lines.append(
            f"  {row['iteration']:>5} | {row['zsup_ic_fcf']:>15,.0f} | {row['tol_low']:>15,.0f} |"
            f" {row['tol_high']:>15,.0f} | {row['final_sim']:>18,.2f} | {flag:>8}"
        )

    # Section 2 — SDDP knowledge
    lines += [
        "",
        "=" * 80,
        "SDDP KNOWLEDGE — POLICY vs. SIMULATION VALIDATION",
        "=" * 80,
        "",
        get_json_info("policy.json", "objective_function_analysis_01"),
        get_json_info("policy.json", "policy_divergence_causes_01"),
        get_json_info("policy.json", "non_convexity_impact_01"),
    ]

    # Section 3 — LLM diagnosis summary
    lines += [
        "=" * 80,
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Final simulation inside policy band : {'YES' if res['inside_band'] else 'NO'}",
        f"- Direction of deviation              : {res['direction']}",
        f"- Absolute deviation                  : {res['deviation']:,.2f}",
        f"- Deviation as % of Zsup (IC+FCF)     : {res['deviation_pct']:.2f}%",
    ]

    return "\n".join(lines)


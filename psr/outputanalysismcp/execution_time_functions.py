"""
SDDP execution time analysis functions.

Public API
----------
load_execution_time_data(results_folder)    -> (df_iter, df_disp, df_pol, df_sim)
analyse_iteration_times(df_iter)            -> dict
analyse_stage_dispersion(df_disp)           -> dict
build_execution_time_report(results_folder) -> str
"""
from __future__ import annotations

from pathlib import Path
import pandas as pd

from .common import read_csv

# Column name constants
ITER_COL     = "Iteration"
FWD_COL      = "Forward"
BWD_COL      = "Backward"
STAGE_COL    = "Etapas"
DISP_LOW     = "MIN-MAX (low)"
DISP_HIGH    = "MIN-MAX (high)"
DISP_AVG     = "Average"
POL_TIME_COL = "Pol. time"
SIM_TIME_COL = "Sim. time"

# Thresholds
SPREAD_RATIO_THRESHOLD = 2.0  # flag stages where MIN-MAX high > 2x average
BWD_GROWTH_THRESHOLD   = 2.0  # flag as accelerating if last-third bwd avg / first-third bwd avg > 2


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_execution_time_data(
    results_folder: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load all four execution-time CSVs from *results_folder*.

    Returns
    -------
    (df_iter, df_disp, df_pol, df_sim)
        df_iter : per-iteration forward / backward times
        df_disp : per-stage MIN-MAX and average dispersion
        df_pol  : total policy time (1-row summary)
        df_sim  : total simulation time (1-row summary)
    """
    df_iter = read_csv(results_folder, "tiempos-de-ejecucin-forw.csv")
    df_disp = read_csv(results_folder, "dispersin-de-los-tiempos.csv")
    df_pol  = read_csv(results_folder, "tiempo-de-ejecucin-polit.csv")
    df_sim  = read_csv(results_folder, "tiempo-de-ejecucin-simul.csv")
    return df_iter, df_disp, df_pol, df_sim


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def analyse_iteration_times(df_iter: pd.DataFrame) -> dict:
    """
    Compute forward / backward iteration time statistics.

    Returns a dict with:
        total_iters     : number of iterations
        fwd_mean        : mean forward time (s)
        fwd_std         : std  forward time (s)
        bwd_mean        : mean backward time (s)
        bwd_std         : std  backward time (s)
        ratio_mean      : bwd_mean / fwd_mean  (expected > 1)
        fwd_growth      : last-third avg / first-third avg for Forward
        bwd_growth      : last-third avg / first-third avg for Backward
        is_accelerating : True if bwd_growth > 2.0 (non-linear growth, potential issue)
        df_iter         : original DataFrame (for table rendering)
    """
    n     = len(df_iter)
    third = max(1, n // 3)

    fwd = df_iter[FWD_COL].astype(float)
    bwd = df_iter[BWD_COL].astype(float)

    fwd_mean = float(fwd.mean())
    fwd_std  = float(fwd.std())
    bwd_mean = float(bwd.mean())
    bwd_std  = float(bwd.std())

    ratio_mean = bwd_mean / fwd_mean if fwd_mean != 0 else float("nan")

    fwd_first = float(fwd.iloc[:third].mean())
    fwd_last  = float(fwd.iloc[-third:].mean())
    bwd_first = float(bwd.iloc[:third].mean())
    bwd_last  = float(bwd.iloc[-third:].mean())

    fwd_growth = fwd_last / fwd_first if fwd_first != 0 else float("nan")
    bwd_growth = bwd_last / bwd_first if bwd_first != 0 else float("nan")

    return {
        "total_iters":    n,
        "fwd_mean":       fwd_mean,
        "fwd_std":        fwd_std,
        "bwd_mean":       bwd_mean,
        "bwd_std":        bwd_std,
        "ratio_mean":     ratio_mean,
        "fwd_growth":     fwd_growth,
        "bwd_growth":     bwd_growth,
        "is_accelerating": bwd_growth > BWD_GROWTH_THRESHOLD,
        "df_iter":        df_iter,
    }


def analyse_stage_dispersion(df_disp: pd.DataFrame) -> dict:
    """
    Identify planning stages with high scenario-time variance.

    Returns a dict with:
        n_stages          : total number of stages
        avg_mean          : mean of the Average column (s)
        avg_std           : std  of the Average column (s)
        high_mean         : mean of MIN-MAX (high) (s)
        spread_ratio_mean : mean of (MIN-MAX high / Average) across all stages
        flagged           : DataFrame of stages where MIN-MAX high > 2 x Average,
                            sorted descending by MIN-MAX high
        n_flagged         : count of flagged stages
        worst_stage       : stage label with the highest MIN-MAX (high) value
    """
    df = df_disp.copy()
    df[DISP_HIGH] = df[DISP_HIGH].astype(float)
    df[DISP_AVG]  = df[DISP_AVG].astype(float)

    n_stages     = len(df)
    avg_mean     = float(df[DISP_AVG].mean())
    avg_std      = float(df[DISP_AVG].std())
    high_mean    = float(df[DISP_HIGH].mean())
    spread_ratio = df[DISP_HIGH] / df[DISP_AVG].replace(0, float("nan"))
    spread_ratio_mean = float(spread_ratio.mean())

    flagged = df[df[DISP_HIGH] > SPREAD_RATIO_THRESHOLD * df[DISP_AVG]].copy()
    flagged = flagged.sort_values(DISP_HIGH, ascending=False)

    worst_idx   = df[DISP_HIGH].idxmax()
    worst_stage = str(df.loc[worst_idx, STAGE_COL])

    return {
        "n_stages":          n_stages,
        "avg_mean":          avg_mean,
        "avg_std":           avg_std,
        "high_mean":         high_mean,
        "spread_ratio_mean": spread_ratio_mean,
        "flagged":           flagged,
        "n_flagged":         len(flagged),
        "worst_stage":       worst_stage,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_execution_time_report(results_folder: Path) -> str:
    """
    Full execution-time analysis report as a structured text string for the LLM.

    Orchestrates: load -> analyse_iteration_times -> analyse_stage_dispersion.
    """
    df_iter, df_disp, df_pol, df_sim = load_execution_time_data(results_folder)
    iter_stats = analyse_iteration_times(df_iter)
    disp_stats = analyse_stage_dispersion(df_disp)

    # Scalar totals from summary CSVs
    pol_time = float(df_pol[POL_TIME_COL].iloc[0])
    sim_time = float(df_sim[SIM_TIME_COL].iloc[0])

    # Unpack iteration stats
    total_iters     = iter_stats["total_iters"]
    fwd_mean        = iter_stats["fwd_mean"]
    fwd_std         = iter_stats["fwd_std"]
    bwd_mean        = iter_stats["bwd_mean"]
    bwd_std         = iter_stats["bwd_std"]
    ratio_mean      = iter_stats["ratio_mean"]
    fwd_growth      = iter_stats["fwd_growth"]
    bwd_growth      = iter_stats["bwd_growth"]
    is_accelerating = iter_stats["is_accelerating"]
    df_iter_tbl     = iter_stats["df_iter"]

    # Unpack dispersion stats
    n_stages          = disp_stats["n_stages"]
    avg_mean          = disp_stats["avg_mean"]
    spread_ratio_mean = disp_stats["spread_ratio_mean"]
    flagged           = disp_stats["flagged"]
    n_flagged         = disp_stats["n_flagged"]
    worst_stage       = disp_stats["worst_stage"]
    worst_row         = df_disp[df_disp[STAGE_COL].astype(str) == worst_stage].iloc[0]
    worst_high        = float(worst_row[DISP_HIGH])
    worst_avg         = float(worst_row[DISP_AVG])

    # Growth breakpoints (recomputed for display)
    n     = total_iters
    third = max(1, n // 3)
    fwd   = df_iter_tbl[FWD_COL].astype(float)
    bwd   = df_iter_tbl[BWD_COL].astype(float)
    fwd_first_avg = float(fwd.iloc[:third].mean())
    fwd_last_avg  = float(fwd.iloc[-third:].mean())
    bwd_first_avg = float(bwd.iloc[:third].mean())
    bwd_last_avg  = float(bwd.iloc[-third:].mean())

    # --- Section 1: Total times ---
    lines = [
        "=== SDDP EXECUTION TIME ANALYSIS ===",
        "",
        "--- SECTION 1: TOTAL TIMES ---",
        f"  {'Metric':<28} {'Value (s)':>12}",
        "  " + "-" * 42,
        f"  {'Policy time':<28} {pol_time:>12.2f}",
        f"  {'Simulation time':<28} {sim_time:>12.2f}",
    ]

    # --- Section 2: Iteration time trend ---
    lines += [
        "",
        "--- SECTION 2: ITERATION TIME TREND ---",
        f"  Total iterations : {total_iters}",
        f"  Forward  — mean: {fwd_mean:.2f} s, std: {fwd_std:.2f} s",
        f"  Backward — mean: {bwd_mean:.2f} s, std: {bwd_std:.2f} s",
        f"  Backward / Forward ratio (mean): {ratio_mean:.2f}",
        "",
        f"  Forward  growth (first-third avg -> last-third avg): "
        f"{fwd_first_avg:.2f} s -> {fwd_last_avg:.2f} s  (factor {fwd_growth:.2f}x)",
        f"  Backward growth (first-third avg -> last-third avg): "
        f"{bwd_first_avg:.2f} s -> {bwd_last_avg:.2f} s  (factor {bwd_growth:.2f}x)",
    ]

    if is_accelerating:
        lines.append(
            f"  WARNING: Backward growth factor ({bwd_growth:.2f}x) exceeds "
            f"{BWD_GROWTH_THRESHOLD:.1f}x — non-linear slowdown detected."
        )

    lines += [
        "",
        f"  {ITER_COL:<12} {FWD_COL:>14} {BWD_COL:>14}",
        "  " + "-" * 44,
    ]
    for _, row in df_iter_tbl.iterrows():
        lines.append(
            f"  {str(row[ITER_COL]):<12} {float(row[FWD_COL]):>14.2f} {float(row[BWD_COL]):>14.2f}"
        )

    # --- Section 3: Stage dispersion hot-spots ---
    lines += [
        "",
        "--- SECTION 3: STAGE DISPERSION HOT-SPOTS ---",
        f"  Total stages      : {n_stages}",
        f"  Average time mean : {avg_mean:.2f} s",
        f"  Spread ratio mean (MIN-MAX high / Average): {spread_ratio_mean:.2f}",
        f"  Flagging stages where MIN-MAX high > {SPREAD_RATIO_THRESHOLD:.0f}x Average.",
        f"  Flagged: {n_flagged} of {n_stages}",
    ]

    if flagged.empty:
        lines.append(
            "  Execution times are uniform across stages — no stages exceed the dispersion threshold."
        )
    else:
        lines += [
            "",
            f"  {STAGE_COL:<20} {DISP_LOW:>16} {DISP_HIGH:>16} {DISP_AVG:>12}",
            "  " + "-" * 68,
        ]
        for _, row in flagged.iterrows():
            lines.append(
                f"  {str(row[STAGE_COL]):<20} {float(row[DISP_LOW]):>16.2f} "
                f"{float(row[DISP_HIGH]):>16.2f} {float(row[DISP_AVG]):>12.2f}"
            )

    # --- Section 4: LLM diagnosis summary ---
    accel_str = "YES" if is_accelerating else "NO"

    lines += [
        "",
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Total policy time      : {pol_time:.2f} s",
        f"- Total simulation time  : {sim_time:.2f} s",
        f"- Backward/Forward ratio : {ratio_mean:.2f}  "
        f"(expected > 1, normal up to ~y openings x forwards)",
        f"- Forward growth factor  : {fwd_growth:.2f}  (last-third avg / first-third avg)",
        f"- Backward growth factor : {bwd_growth:.2f}",
        f"- Accelerating: {accel_str}",
        f"- Flagged stages (high dispersion): {n_flagged} of {n_stages}",
        f"- Worst stage: {worst_stage} "
        f"(MIN-MAX high = {worst_high:.2f} s, avg = {worst_avg:.2f} s)",
        "",
        "Suggested knowledge queries:",
        '  - If accelerating growth    -> get_sddp_knowledge(problems=["increasing_iteration_time"])',
        '  - If high stage dispersion  -> get_sddp_knowledge(problems=["mip_complexity", '
        '"intertemporal_coupling", "feasibility_tightness"])',
    ]

    return "\n".join(lines)

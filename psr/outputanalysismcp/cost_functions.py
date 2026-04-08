"""
SDDP cost analysis functions.

Public API
----------
Data loaders:
  load_cost_data(results_folder)                -> (df_portions, df_stages)
  load_dispersion_and_ena_data(results_folder)  -> (df_disp, df_ena | None)
  load_penalty_participation_data(results_folder) -> df_participation

Analysis functions:
  analyse_cost_portions(df_portions)            -> dict
  analyse_stage_hotspots(df_stages)             -> dict
  analyse_cost_dispersion(df_disp, df_ena)      -> dict
  analyse_penalty_participation(df_part)        -> dict

Report builders:
  build_cost_health_report(results_folder)      -> str
  build_cost_dispersion_report(results_folder)  -> str
  build_penalty_participation_report(results_folder) -> str
"""
from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

from .common import read_csv, get_json_info

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OP_COST_COL = "Costo: Total operativo"
STAGE_COL   = "Etapas"

OP_COST_THRESHOLD    = 0.80   # operating cost must be >= 80% of total
STAGE_PEN_THRESHOLD  = 0.20   # flag stages where penalties >= 20% of stage total
PEN_SHARE_THRESHOLD  = 0.01   # show penalties above 1% in health report
DISP_HIGH_CV         = 0.30   # flag stages where (P90-P10)/Average > 30% as high uncertainty
CORR_HIGH            = 0.70   # Pearson r >= 0.70: high correlation
CORR_MODERATE        = 0.50   # Pearson r >= 0.50: moderate correlation
CORR_OUTLIER_SIGMA   = 1.5    # flag stages whose residual > 1.5 * std(residuals)
PEN_PART_THRESHOLD   = 20.0   # flag stage/scenario pairs where penalty % > 20%

# Internal reference: penalty column names -> English description.
# Not shown in reports --kept for potential future use by other modules.
PENALTY_DESCRIPTIONS: dict[str, str] = {
    "Pen: Vertimiento hidro":            "Hydro spillage",
    "Pen: Volumen operativo min. hidro": "Min hydro storage violation",
    "Pen: Volumen operativo max. hidro": "Max hydro storage violation",
    "Pen: Defluencia total max. hidro":  "Max total hydro outflow violation",
    "Pen: Defluencia total min. hidro":  "Min total hydro outflow violation",
    "Pen: Riego hidro":                  "Hydro irrigation deficit",
    "Pen: Restriccion de generacion":    "Generation restriction violation",
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_cost_data(results_folder: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load porciones-de-el-costo-op.csv and costos-operativos-promed.csv."""
    df_portions = read_csv(results_folder, "porciones-de-el-costo-op.csv")
    df_portions = df_portions.rename(columns={"Series 1": "value"})
    df_stages   = read_csv(results_folder, "costos-operativos-promed.csv")
    return df_portions, df_stages


def load_dispersion_and_ena_data(
    results_folder: Path,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """
    Load dispersin-de-los-costos.csv and, if available, energa-total-afluente.csv.
    Returns (df_disp, df_ena). df_ena is None when the ENA file is absent.
    """
    df_disp = read_csv(results_folder, "dispersin-de-los-costos.csv")
    ena_path = Path(results_folder) / "energa-total-afluente.csv"
    df_ena = read_csv(results_folder, "energa-total-afluente.csv") if ena_path.exists() else None
    return df_disp, df_ena


def load_penalty_participation_data(results_folder: Path) -> pd.DataFrame:
    """
    Load participacin-de-las-pena.csv.

    Keeps only the stage column and all '(value)' percentage columns,
    renaming them to Scenario_1, Scenario_2, … for easy access.
    """
    df = read_csv(results_folder, "participacin-de-las-pena.csv")
    val_cols = [c for c in df.columns if "(value)" in c]
    n = len(val_cols)
    rename = {col: f"Scenario_{i+1}" for i, col in enumerate(val_cols)}
    df = df[[STAGE_COL] + val_cols].rename(columns=rename)
    df.columns.name = None
    return df


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def analyse_cost_portions(df_portions: pd.DataFrame) -> dict:
    """
    Compute total cost breakdown and operating-cost health.

    Returns: grand_total, op_value, op_share, pen_rows (sorted df), health_ok
    """
    grand_total = df_portions["value"].sum()
    df = df_portions.copy()
    df["share_pct"] = df["value"] / grand_total * 100

    op_row   = df[df["Category"] == OP_COST_COL]
    op_value = float(op_row["value"].iloc[0]) if not op_row.empty else 0.0
    op_share = op_value / grand_total * 100

    pen_rows = df[df["Category"] != OP_COST_COL].copy()
    pen_rows = pen_rows.sort_values("value", ascending=False)

    return {
        "grand_total": grand_total,
        "op_value":    op_value,
        "op_share":    op_share,
        "pen_rows":    pen_rows,
        "health_ok":   op_share >= OP_COST_THRESHOLD * 100,
    }


def analyse_stage_hotspots(df_stages: pd.DataFrame) -> dict:
    """
    Identify planning stages where penalties dominate the cost.

    Returns: df_stages (with computed columns), pen_cols, flagged (sorted df),
             n_total, n_flagged
    """
    df       = df_stages.copy()
    pen_cols = [c for c in df.columns if c.startswith("Pen:")]

    df["total_penalty"] = df[pen_cols].sum(axis=1)
    df["stage_total"]   = df[OP_COST_COL] + df["total_penalty"]
    df["pen_share_pct"] = df["total_penalty"] / df["stage_total"] * 100

    flagged = df[df["pen_share_pct"] >= STAGE_PEN_THRESHOLD * 100].copy()
    flagged = flagged.sort_values("pen_share_pct", ascending=False)

    return {
        "df_stages": df,
        "pen_cols":  pen_cols,
        "flagged":   flagged,
        "n_total":   len(df),
        "n_flagged": len(flagged),
    }


def _classify_correlation(r: float) -> str:
    """Return STRONG / MODERATE / WEAK based on absolute Pearson r."""
    ar = abs(r)
    if ar >= CORR_HIGH:
        return "STRONG"
    if ar >= CORR_MODERATE:
        return "MODERATE"
    return "WEAK"


def _linear_elasticity(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """
    Fit y = a*x + b and return (slope, r2, elasticity_at_mean).

    elasticity = slope * mean(x) / mean(y)
    Interpretation: a 1% increase in x causes 'elasticity'% change in y.
    """
    coeffs    = np.polyfit(x, y, 1)
    slope     = float(coeffs[0])
    predicted = np.polyval(coeffs, x)
    ss_res    = float(np.sum((y - predicted) ** 2))
    ss_tot    = float(np.sum((y - y.mean()) ** 2))
    r2        = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    elast     = slope * (float(x.mean()) / float(y.mean())) if y.mean() != 0 else 0.0
    return slope, r2, elast


def analyse_cost_dispersion(
    df_disp: pd.DataFrame,
    df_ena: pd.DataFrame | None = None,
) -> dict:
    """
    Compute per-stage cost uncertainty from P10-P90 band.

    When ENA data is available, computes three metric groups:

    1. Pearson correlations
       - corr_incerteza : spread_custo vs spread_ena  (uncertainty co-movement)
       - corr_media     : avg_cost vs avg_ena          (level co-movement, often negative)

    2. Deterministic coefficient (R2)
       - r2_incerteza : fraction of cost-spread variance explained by ENA-spread
       - r2_media     : fraction of avg-cost variance explained by avg-ENA

    3. Inverse elasticity  (%delta_cost / %delta_ena)
       - elast_spread : if ENA spread changes 10%, cost spread changes by elast_spread*10%
       - elast_media  : if avg ENA changes 10%, avg cost changes by elast_media*10%
       - Both derived from OLS slope at the mean point.
    """
    df = df_disp.copy()
    df["spread"] = df["P10-P90 (high)"] - df["P10-P90 (low)"]
    df["cv"]     = df["spread"] / df["Average"].replace(0, float("nan"))

    flagged = df[df["cv"] > DISP_HIGH_CV].copy()
    flagged = flagged.sort_values("cv", ascending=False)

    result: dict = {
        "n_stages":      len(df),
        "mean_avg":      float(df["Average"].mean()),
        "spread_mean":   float(df["spread"].mean()),
        "cv_mean":       float(df["cv"].mean()),
        "df_enriched":   df,
        "flagged":       flagged,
        "n_flagged":     len(flagged),
        "ena_available": df_ena is not None,
    }

    if df_ena is None:
        return result

    # --- Align by row index (both files share the same stage ordering) ---
    n = min(len(df), len(df_ena))
    df_c = df.iloc[:n].copy()
    df_e = df_ena.iloc[:n].copy()

    spread_custo = (df_c["P10-P90 (high)"] - df_c["P10-P90 (low)"]).values
    spread_ena   = (df_e["P10-P90 (high)"] - df_e["P10-P90 (low)"]).values
    avg_cost     = df_c["Average"].values
    avg_ena      = df_e["Average"].values

    # 1. Pearson correlations
    corr_incerteza = float(np.corrcoef(spread_custo, spread_ena)[0, 1])
    corr_media     = float(np.corrcoef(avg_cost, avg_ena)[0, 1])

    # 2 & 3. OLS regression -> R2 + elasticity
    slope_spread, r2_incerteza, elast_spread = _linear_elasticity(spread_ena, spread_custo)
    slope_media,  r2_media,     elast_media  = _linear_elasticity(avg_ena,    avg_cost)

    result.update({
        # Pearson
        "corr_incerteza":  corr_incerteza,
        "corr_media":      corr_media,
        # R2
        "r2_incerteza":    r2_incerteza,
        "r2_media":        r2_media,
        # Elasticity
        "elast_spread":    elast_spread,
        "elast_media":     elast_media,
        "slope_spread":    slope_spread,
        "slope_media":     slope_media,
        "mean_spread_ena": float(spread_ena.mean()),
        "mean_spread_cost": float(spread_custo.mean()),
        "mean_avg_ena":    float(avg_ena.mean()),
        "mean_avg_cost":   float(avg_cost.mean()),
    })
    return result


def analyse_penalty_participation(df_part: pd.DataFrame) -> dict:
    """
    Find stages and scenarios with significant penalty participation.

    Returns: scenario_cols, df_enriched (+ mean/max/n_above columns),
             flagged_stages (mean penalty > PEN_PART_THRESHOLD), n_flagged,
             worst_stage, worst_scenario_col
    """
    scen_cols = [c for c in df_part.columns if c.startswith("Scenario_")]
    df = df_part.copy()

    df["mean_pct"]  = df[scen_cols].mean(axis=1)
    df["max_pct"]   = df[scen_cols].max(axis=1)
    df["n_above"]   = (df[scen_cols] > PEN_PART_THRESHOLD).sum(axis=1)

    flagged = df[df["mean_pct"] > PEN_PART_THRESHOLD].copy()
    flagged = flagged.sort_values("mean_pct", ascending=False)

    worst_stage = str(df.loc[df["mean_pct"].idxmax(), STAGE_COL])

    # Worst scenario = the one with the highest mean penalty across all stages
    scen_means     = df[scen_cols].mean()
    worst_scenario = str(scen_means.idxmax())

    return {
        "scenario_cols":   scen_cols,
        "n_scenarios":     len(scen_cols),
        "df_enriched":     df,
        "flagged":         flagged,
        "n_flagged":       len(flagged),
        "n_total":         len(df),
        "worst_stage":     worst_stage,
        "worst_scenario":  worst_scenario,
        "scenario_means":  scen_means,
    }


# ---------------------------------------------------------------------------
# Report builders
# ---------------------------------------------------------------------------

def build_cost_health_report(results_folder: Path) -> str:
    """
    Tool 1 --Cost health check.

    Reports whether operating cost >= 80% of the total, lists dominant
    penalties and the stages where they concentrate.
    Appended with SDDP knowledge entries sim_total_cost_portions and
    sim_average_cost_stage.
    """
    df_portions, df_stages = load_cost_data(results_folder)
    portions = analyse_cost_portions(df_portions)
    hotspots = analyse_stage_hotspots(df_stages)

    grand_total = portions["grand_total"]
    op_value    = portions["op_value"]
    op_share    = portions["op_share"]
    pen_rows    = portions["pen_rows"]
    pen_cols    = hotspots["pen_cols"]
    flagged     = hotspots["flagged"]

    # --- Cost breakdown ---
    lines = [
        "=== SDDP COST HEALTH ANALYSIS ===",
        "",
        "--- TOTAL COST BREAKDOWN ---",
        f"  {'Category':<45} {'Value':>15}  {'Share':>7}",
        "  " + "-" * 72,
        f"  {OP_COST_COL:<45} {op_value:>15,.2f}  {op_share:>6.1f}%",
    ]
    for _, row in pen_rows.iterrows():
        lines.append(f"  {row['Category']:<45} {row['value']:>15,.2f}  {row['share_pct']:>6.1f}%")
    lines += [
        "  " + "-" * 72,
        f"  {'TOTAL':<45} {grand_total:>15,.2f}  {'100.0%':>7}",
    ]

    # --- Health check ---
    lines += ["", "--- OPERATING COST HEALTH CHECK ---"]
    if portions["health_ok"]:
        lines.append(
            f"  STATUS: OK --Operating cost is {op_share:.1f}% of total "
            f"(threshold: {OP_COST_THRESHOLD*100:.0f}%)."
        )
    else:
        lines += [
            f"  STATUS: WARNING --Operating cost is only {op_share:.1f}% of total "
            f"(threshold: {OP_COST_THRESHOLD*100:.0f}%).",
            "  Penalties are inflating the total --constraint violations likely.",
            "",
            f"  Penalties above {PEN_SHARE_THRESHOLD*100:.0f}% of grand total:",
            f"  {'Penalty':<45} {'Value':>15}  {'Share':>7}",
            "  " + "-" * 72,
        ]
        for _, row in pen_rows[pen_rows["share_pct"] >= PEN_SHARE_THRESHOLD * 100].iterrows():
            lines.append(f"  {row['Category']:<45} {row['value']:>15,.2f}  {row['share_pct']:>6.1f}%")

    # --- Per-stage hot-spots ---
    lines += [
        "",
        "--- PER-STAGE PENALTY HOT-SPOTS ---",
        f"  Stages where penalties >= {STAGE_PEN_THRESHOLD*100:.0f}% of that stage's total.",
        f"  Total stages: {hotspots['n_total']}   Flagged: {hotspots['n_flagged']}",
    ]

    if flagged.empty:
        lines.append("  No stages exceed the threshold --penalty distribution looks healthy.")
    else:
        lines += [
            "",
            f"  {'Stage':<26} {'Op.Cost':>12} {'Tot.Penalty':>12} {'Pen%':>7}  Dominant penalties",
            "  " + "-" * 100,
        ]
        for _, row in flagged.iterrows():
            dominant = [
                f"{col} ({row[col] / row['stage_total'] * 100:.0f}%)"
                for col in pen_cols
                if row[col] > 0 and (row[col] / row["stage_total"]) >= 0.05
            ]
            lines.append(
                f"  {str(row[STAGE_COL]):<26} {row[OP_COST_COL]:>12,.1f} "
                f"{row['total_penalty']:>12,.1f} {row['pen_share_pct']:>7.1f}%  "
                f"{' | '.join(dominant) or '—'}"
            )

        # Penalty totals across flagged stages
        pen_totals = flagged[pen_cols].sum().sort_values(ascending=False)
        pen_totals = pen_totals[pen_totals > 0]
        lines += [
            "",
            "  Penalty totals across flagged stages:",
            f"  {'Penalty':<45} {'Total value':>15}",
            "  " + "-" * 64,
        ]
        for col, val in pen_totals.items():
            lines.append(f"  {col:<45} {val:>15,.2f}")

    # --- SDDP knowledge ---
    lines += [
        "",
        "=" * 80,
        "SDDP KNOWLEDGE",
        "=" * 80,
        "",
        get_json_info("simulation.json", "sim_total_cost_portions"),
        get_json_info("simulation.json", "sim_average_cost_stage"),
    ]

    # --- LLM summary ---
    top_penalties = pen_rows["Category"].head(3).tolist()
    flagged_list  = flagged[STAGE_COL].tolist() if not flagged.empty else []
    lines += [
        "=" * 80,
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Operating cost share : {op_share:.1f}%  "
        f"({'OK' if portions['health_ok'] else 'WARNING --below 80%'})",
        f"- Grand total          : {grand_total:,.2f}",
        f"- Dominant penalties   : {', '.join(top_penalties)}",
        f"- Flagged stages       : {hotspots['n_flagged']} of {hotspots['n_total']}"
        + (f" --{', '.join(str(s) for s in flagged_list[:5])}{'...' if len(flagged_list) > 5 else ''}"
           if flagged_list else ""),
    ]

    return "\n".join(lines)


def _corr_interpretation(r: float, context: str) -> str:
    """One-line interpretation of a Pearson r in context."""
    level = _classify_correlation(r)
    sign  = "positive" if r >= 0 else "negative"
    if level == "STRONG":
        return f"[OK] STRONG {sign} correlation -- {context} move closely together."
    if level == "MODERATE":
        return f"[!!] MODERATE {sign} correlation -- {context} are partially linked; other drivers present."
    return f"[!!] WEAK {sign} correlation -- {context} do not move together in this run."


def build_cost_dispersion_report(results_folder: Path) -> str:
    """
    Tool 2 -- Cost dispersion and ENA correlation.

    Three metric groups when ENA data is available:
      1. Pearson r  -- uncertainty co-movement (spread vs spread) and level co-movement (avg vs avg)
      2. R2         -- fraction of cost variance explained by ENA via OLS regression
      3. Elasticity -- %delta_cost / %delta_ena at the mean (inverse elasticity)
    """
    df_disp, df_ena = load_dispersion_and_ena_data(results_folder)
    stats = analyse_cost_dispersion(df_disp, df_ena)

    df   = stats["df_enriched"]
    flag = stats["flagged"]

    lines = [
        "=== SDDP COST DISPERSION ANALYSIS ===",
        "",
        "--- OVERALL STATISTICS ---",
        f"  Total stages            : {stats['n_stages']}",
        f"  Mean average cost       : {stats['mean_avg']:>14,.2f}",
        f"  Mean P10-P90 spread     : {stats['spread_mean']:>14,.2f}",
        f"  Mean CV (spread/avg)    : {stats['cv_mean']:>14.3f}",
        f"  High-uncertainty stages : {stats['n_flagged']} of {stats['n_stages']}"
        f"  (CV > {DISP_HIGH_CV:.0%})",
    ]

    # -----------------------------------------------------------------------
    # ENA analysis -- only when the file exists
    # -----------------------------------------------------------------------
    lines += ["", "--- ENA CORRELATION ANALYSIS ---"]

    if not stats["ena_available"]:
        lines.append(
            "  ENA file (energa-total-afluente.csv) not found -- "
            "correlation metrics cannot be computed."
        )
    else:
        ci  = stats["corr_incerteza"]
        cm  = stats["corr_media"]
        r2i = stats["r2_incerteza"]
        r2m = stats["r2_media"]
        ei  = stats["elast_spread"]
        em  = stats["elast_media"]

        # --- Section 1: Pearson r ---
        lines += [
            "",
            "  [1] PEARSON CORRELATION",
            f"  {'Metric':<50} {'r':>8}  {'Level':>10}",
            "  " + "-" * 74,
            f"  {'Uncertainty  :  cost spread (P90-P10) vs ENA spread':<50} {ci:>8.4f}  {_classify_correlation(ci):>10}",
            f"  {'Level        :  average cost vs average ENA':<50} {cm:>8.4f}  {_classify_correlation(cm):>10}",
            "",
            f"  Uncertainty: {_corr_interpretation(ci, 'cost spread and ENA spread')}",
            f"  Level      : {_corr_interpretation(cm, 'average cost and average ENA')}",
        ]

        # Contextual note on the sign of corr_media
        if cm > 0:
            lines += [
                "  Note: positive avg-cost vs avg-ENA correlation is unusual.",
                "  It may indicate that high-inflow stages coincide with high penalty costs",
                "  (e.g. spillage, flood-control violations) dominating the average.",
            ]
        else:
            lines += [
                "  Note: negative avg-cost vs avg-ENA correlation is expected --",
                "  higher inflow -> cheaper hydro dispatch -> lower average cost.",
            ]

        # --- Section 2: R2 (deterministic coefficient) ---
        lines += [
            "",
            "  [2] DETERMINISTIC COEFFICIENT  R2  (OLS linear regression)",
            f"  {'Regression':<50} {'R2':>8}  {'Explained variance':>20}",
            "  " + "-" * 82,
            f"  {'cost spread  ~  ENA spread':<50} {r2i:>8.4f}  {r2i*100:>19.1f}%",
            f"  {'average cost ~  average ENA':<50} {r2m:>8.4f}  {r2m*100:>19.1f}%",
            "",
        ]
        if r2i >= 0.50:
            lines.append(
                f"  [OK] ENA spread explains {r2i*100:.1f}% of cost-spread variance. "
                "Hydrological uncertainty is the dominant driver."
            )
        elif r2i >= 0.25:
            lines.append(
                f"  [!!] ENA spread explains {r2i*100:.1f}% of cost-spread variance. "
                "Other drivers (thermal, penalties, storage) also contribute significantly."
            )
        else:
            lines.append(
                f"  [!!] ENA spread explains only {r2i*100:.1f}% of cost-spread variance. "
                "Cost uncertainty is largely independent of inflow uncertainty in this run."
            )

        # --- Section 3: Inverse elasticity ---
        # Expressed as: "if ENA changes by -10%, cost changes by X%"
        delta_pct_ena  = -10.0
        delta_spread   = ei * delta_pct_ena
        delta_avg_cost = em * delta_pct_ena

        lines += [
            "",
            "  [3] INVERSE ELASTICITY  (%delta_cost / %delta_ENA)",
            f"  {'Pair':<50} {'Elasticity':>12}  {'If ENA drops 10%':>20}",
            "  " + "-" * 86,
            f"  {'cost spread  vs  ENA spread':<50} {ei:>12.4f}  cost spread changes {delta_spread:>+.2f}%",
            f"  {'average cost vs  average ENA':<50} {em:>12.4f}  avg cost changes    {delta_avg_cost:>+.2f}%",
            "",
            "  Interpretation:",
            f"  - A 10% drop in ENA spread -> cost spread {'+rises' if delta_spread > 0 else 'falls'} by {abs(delta_spread):.2f}%.",
            f"  - A 10% drop in average ENA -> average cost {'+rises' if delta_avg_cost > 0 else 'falls'} by {abs(delta_avg_cost):.2f}%.",
        ]

        if abs(ei) >= 0.5:
            lines.append(
                "  High spread elasticity: cost uncertainty responds strongly to ENA variability. "
                "Wet-season inflow scenarios drive most of the P10-P90 band width."
            )
        else:
            lines.append(
                "  Low spread elasticity: cost uncertainty is relatively insensitive to ENA "
                "variability; check penalties and thermal constraints as alternative drivers."
            )

    # -----------------------------------------------------------------------
    # Per-stage dispersion table
    # -----------------------------------------------------------------------
    lines += [
        "",
        "--- PER-STAGE DISPERSION TABLE ---",
        f"  {'Stage':<26} {'P10 (low)':>14} {'P90 (high)':>14} {'Average':>14} {'Spread':>12} {'CV':>8}",
        "  " + "-" * 94,
    ]
    for _, row in df.iterrows():
        lines.append(
            f"  {str(row[STAGE_COL]):<26} {row['P10-P90 (low)']:>14,.2f} "
            f"{row['P10-P90 (high)']:>14,.2f} {row['Average']:>14,.2f} "
            f"{row['spread']:>12,.2f} {row['cv']:>8.3f}"
        )

    # High-uncertainty hot-spots
    lines += ["", f"--- HIGH-UNCERTAINTY STAGES (CV > {DISP_HIGH_CV:.0%}) ---"]
    if flag.empty:
        lines.append("  No stages exceed the uncertainty threshold.")
    else:
        lines += [
            f"  {'Stage':<26} {'Average':>14} {'Spread':>12} {'CV':>8}",
            "  " + "-" * 66,
        ]
        for _, row in flag.iterrows():
            lines.append(
                f"  {str(row[STAGE_COL]):<26} {row['Average']:>14,.2f} "
                f"{row['spread']:>12,.2f} {row['cv']:>8.3f}"
            )

    # -----------------------------------------------------------------------
    # SDDP knowledge
    # -----------------------------------------------------------------------
    lines += [
        "",
        "=" * 80,
        "SDDP KNOWLEDGE",
        "=" * 80,
        "",
        get_json_info("simulation.json", "sim_cost_dispersion"),
    ]

    # -----------------------------------------------------------------------
    # LLM summary
    # -----------------------------------------------------------------------
    worst_stage = str(df.loc[df["cv"].idxmax(), STAGE_COL]) if not df.empty else "N/A"
    lines += [
        "=" * 80,
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- ENA data available                              : {'YES' if stats['ena_available'] else 'NO'}",
        f"- Mean CV (spread / avg cost)                     : {stats['cv_mean']:.3f}",
        f"- High-uncertainty stages (CV > {DISP_HIGH_CV:.0%})          : {stats['n_flagged']} of {stats['n_stages']}",
        f"- Stage with highest CV                           : {worst_stage}",
    ]
    if stats["ena_available"]:
        lines += [
            f"- [1] Pearson r uncertainty (spread vs spread)    : {stats['corr_incerteza']:.4f}  [{_classify_correlation(stats['corr_incerteza'])}]",
            f"- [1] Pearson r level (avg cost vs avg ENA)       : {stats['corr_media']:.4f}  [{_classify_correlation(stats['corr_media'])}]",
            f"- [2] R2 cost spread ~ ENA spread                 : {stats['r2_incerteza']:.4f}  ({stats['r2_incerteza']*100:.1f}% explained)",
            f"- [2] R2 avg cost    ~ avg ENA                    : {stats['r2_media']:.4f}  ({stats['r2_media']*100:.1f}% explained)",
            f"- [3] Elasticity spread (cost/ENA uncertainty)    : {stats['elast_spread']:.4f}",
            f"- [3] Elasticity level  (avg cost / avg ENA)      : {stats['elast_media']:.4f}",
            f"      => if ENA spread drops 10%: cost spread changes {stats['elast_spread']*(-10):+.2f}%",
            f"      => if avg ENA drops 10%   : avg cost changes    {stats['elast_media']*(-10):+.2f}%",
        ]

    return "\n".join(lines)


def build_penalty_participation_report(results_folder: Path) -> str:
    """
    Tool 3 --Penalty participation by scenario and stage.

    Uses participacin-de-las-pena.csv to find which stages and scenarios
    carry the heaviest penalty burden.
    """
    df_part = load_penalty_participation_data(results_folder)
    stats   = analyse_penalty_participation(df_part)

    scen_cols = stats["scenario_cols"]
    df        = stats["df_enriched"]
    flagged   = stats["flagged"]

    lines = [
        "=== PENALTY PARTICIPATION ANALYSIS ===",
        f"  Stages: {stats['n_total']}   Scenarios: {stats['n_scenarios']}",
        f"  Flagging stage/scenario pairs where penalty % > {PEN_PART_THRESHOLD:.0f}%.",
        "",
        "--- SCENARIO MEAN PENALTY (averaged across all stages) ---",
        f"  {'Scenario':<14} {'Mean penalty %':>16}",
        "  " + "-" * 34,
    ]
    for col, val in stats["scenario_means"].sort_values(ascending=False).items():
        lines.append(f"  {col:<14} {val:>16.2f}%")
    lines.append(f"  Worst scenario overall: {stats['worst_scenario']}")

    # Per-stage summary table
    lines += [
        "",
        "--- PER-STAGE PENALTY SUMMARY ---",
        f"  {'Stage':<26} {'Mean%':>8} {'Max%':>8} {'N above threshold':>18}",
        "  " + "-" * 66,
    ]
    for _, row in df.sort_values("mean_pct", ascending=False).iterrows():
        lines.append(
            f"  {str(row[STAGE_COL]):<26} {row['mean_pct']:>8.1f}% "
            f"{row['max_pct']:>8.1f}% {int(row['n_above']):>18}"
        )

    # Flagged stages with scenario breakdown
    lines += [
        "",
        f"--- FLAGGED STAGES (mean penalty > {PEN_PART_THRESHOLD:.0f}%) ---",
        f"  Flagged: {stats['n_flagged']} of {stats['n_total']}",
    ]
    if flagged.empty:
        lines.append(f"  No stage exceeds the {PEN_PART_THRESHOLD:.0f}% mean threshold.")
    else:
        # Show per-scenario breakdown for flagged stages
        header_scens = "  ".join(f"{c:>12}" for c in scen_cols)
        lines += [
            "",
            f"  {'Stage':<26}  {header_scens}",
            "  " + "-" * (28 + 14 * len(scen_cols)),
        ]
        for _, row in flagged.iterrows():
            scen_vals = "  ".join(f"{row[c]:>12.1f}%" for c in scen_cols)
            lines.append(f"  {str(row[STAGE_COL]):<26}  {scen_vals}")

    # LLM summary
    lines += [
        "",
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Flagged stages (mean penalty > {PEN_PART_THRESHOLD:.0f}%) : "
        f"{stats['n_flagged']} of {stats['n_total']}",
        f"- Worst stage overall    : {stats['worst_stage']}",
        f"- Worst scenario overall : {stats['worst_scenario']}",
        "",
        "High mean penalty across all scenarios in a stage indicates a systematic",
        "constraint violation that affects the entire scenario set for that period.",
        "High penalty in only a few scenarios points to specific critical conditions",
        "(e.g. low-inflow scenarios triggering storage or generation constraints).",
    ]

    return "\n".join(lines)



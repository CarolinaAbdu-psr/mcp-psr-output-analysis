#!/usr/bin/env python3
"""MCP server for PSR Output Analysis."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from pathlib import Path
import os
import json
import pandas as pd

# Root of the installed package — used to locate the knowledge-base folder.
_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"

mcp = FastMCP(
    "PSR Output Analysis",
    instructions=(
        "You are an SDDP output analysis assistant. "
        "Your job is to analyse the results of an SDDP simulation run and explain them clearly to the user. "

        "## Workflow "
        "1. Set the case path with get_avaliable_results(study_path) to initialise RESULTS_FOLDER and "
        "   see which CSV files are available. "
        "2. Use the analysis tools to extract structured diagnostics from those CSVs. "
        "3. When a diagnosis is uncertain or the user asks 'why', retrieve relevant SDDP theory with "
        "   list_sddp_knowledge() (discovery) and get_sddp_knowledge(topics, problems) (full content). "
        "4. Combine tool output + knowledge to give the user a clear, actionable answer. "

        "## Available tools "
        "Setup: "
        "  get_avaliable_results(study_path) — sets RESULTS_FOLDER and lists available CSV files. "

        "Policy convergence: "
        "  analyse_policy_convergence() — checks whether Zinf entered the Zsup ± tolerance band; "
        "    if not, reports gap trend (locked/progressing) and cut-per-iteration stability. "
        "    Always call this before interpreting any other policy result. "

        "Cost analysis: "
        "  analyse_costs() — three-part cost report: "
        "    (A) full breakdown of operating cost vs. every penalty category with % share; "
        "    (B) 80% health-check — warns if operating cost < 80% of total and lists significant penalties "
        "        with their physical meaning and suggested knowledge tags; "
        "    (C) per-stage hot-spot detection — flags planning stages where penalties ≥ 20% of "
        "        that stage's total cost, ranks them, and identifies the dominant penalty type per stage. "
        "    Call after analyse_policy_convergence(). Use the suggested knowledge tags at the end of the "
        "    report to fetch explanations with get_sddp_knowledge(). "

        "SDDP knowledge base: "
        "  list_sddp_knowledge() — returns all available knowledge entries (id, topic, title, related_problems). "
        "    Call this once to discover what topics are covered; do NOT call it on every turn. "
        "  get_sddp_knowledge(topics, problems) — returns the full content of entries that match "
        "    ANY of the given topic strings OR ANY of the given related_problem strings. "
        "    Pass only the tags you need; combine with diagnosis results to give grounded explanations. "

        "## Rules "
        "- Always set the case path before calling analysis tools. "
        "- Call analyse_policy_convergence() before drawing conclusions about policy quality. "
        "- Retrieve knowledge only when it adds explanatory value; do not dump the entire knowledge base. "
        "- Lead responses with the answer; keep explanations concise. "
        "- Present tabular data as formatted tables, not raw dicts. "
    ),
)

# ---------------------------------------------------------------------------
# Set Results Path 
# ---------------------------------------------------------------------------
@mcp.tool()
def get_results_path(study_path:str):
    """Set the results folder global used by all tool functions."""
    global RESULTS_FOLDER
    RESULTS_FOLDER = os.path.join(study_path,"results")


@mcp.tool()
def get_avaliable_results(study_path:str):
    global RESULTS_FOLDER
    RESULTS_FOLDER = Path(os.path.join(study_path,"results"))

    available_files= []
    for csv in RESULTS_FOLDER.iterdir():
        if csv.is_file():
            available_files.append(csv.name)

    return available_files

# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------
@mcp.tool(name="Analyse Policy Convergence")
def analyse_policy_convergence():
    """
    Analyse SDDP policy convergence from the results CSVs.

    Returns a structured text report covering:
    - Whether the policy converged (Zinf inside Zsup ± tolerance band on the last iteration).
    - If NOT converged:
        - Gap trend (Zsup - Zinf as % of Zsup) over all iterations to detect if the
          bounds are still approaching or are LOCKED (stuck).
        - Cuts-per-iteration stability to diagnose whether the algorithm is still
          actively exploring or has stalled.

    Data sources (inside RESULTS_FOLDER):
    - convergencia.csv          : Iteration, Zinf, Zsup, Zsup +- Tol (low), Zsup +- Tol (high)
    - nuevos-cortes-por-iterac.csv : Iteration, Optimality (number of new cuts added each iter)
    """
    df = pd.read_csv(
        Path(os.path.join(RESULTS_FOLDER, 'convergencia.csv')),
        encoding='utf-8-sig',
    )
    df_cuts = pd.read_csv(
        Path(os.path.join(RESULTS_FOLDER, 'nuevos-cortes-por-iterac.csv')),
        encoding='utf-8-sig',
    )

    # Strip any stray whitespace from column names
    df.columns = df.columns.str.strip()
    df_cuts.columns = df_cuts.columns.str.strip()

    total_iters = len(df)
    last = df.iloc[-1]

    zinf     = last['Zinf']
    zsup     = last['Zsup']
    tol_low  = last['Zsup +- Tol (low)']
    tol_high = last['Zsup +- Tol (high)']
    last_iter = int(last['Iteration'])

    converged = tol_low <= zinf <= tol_high

    lines = [
        "=== SDDP POLICY CONVERGENCE ANALYSIS ===",
        f"Total iterations run : {total_iters}",
        f"Last iteration       : {last_iter}",
        "",
        "[ LAST ITERATION VALUES ]",
        f"  Zinf              = {zinf:>18,.2f}",
        f"  Zsup              = {zsup:>18,.2f}",
        f"  Zsup - Tol (low)  = {tol_low:>18,.2f}",
        f"  Zsup + Tol (high) = {tol_high:>18,.2f}",
        "",
        f"CONVERGENCE STATUS: {'CONVERGED' if converged else 'NOT CONVERGED'}",
    ]

    if converged:
        lines += [
            "",
            "Zinf is INSIDE the Zsup ± tolerance band on the last iteration.",
            "The policy has successfully converged. No further analysis needed.",
        ]
    else:
        # Direction of miss
        if zinf < tol_low:
            miss_dir = f"Zinf is BELOW the lower tolerance bound by {tol_low - zinf:,.2f} ({(tol_low - zinf) / zsup * 100:.4f}% of Zsup)."
        else:
            miss_dir = f"Zinf is ABOVE the upper tolerance bound by {zinf - tol_high:,.2f} ({(zinf - tol_high) / zsup * 100:.4f}% of Zsup)."

        lines += [
            "",
            f"Zinf is OUTSIDE the Zsup ± tolerance band on the last iteration.",
            miss_dir,
        ]

        # -----------------------------------------------------------------
        # 2-a  Gap trend – is the algorithm still making progress?
        # -----------------------------------------------------------------
        df['gap']     = df['Zsup'] - df['Zinf']
        df['gap_pct'] = df['gap'] / df['Zsup'] * 100

        first_gap_pct = df['gap_pct'].iloc[0]
        last_gap_pct  = df['gap_pct'].iloc[-1]
        total_reduction = first_gap_pct - last_gap_pct

        # Use the last third of iterations (min 2, max 10) to judge recent trend
        tail_n = max(2, min(10, total_iters // 2))
        recent_df   = df.tail(tail_n)
        recent_change = recent_df['gap_pct'].iloc[0] - recent_df['gap_pct'].iloc[-1]
        recent_avg_gap = recent_df['gap_pct'].mean()

        # Locked = gap barely moved in recent iterations (< 0.005% absolute change)
        LOCK_THRESHOLD = 0.005
        is_locked = abs(recent_change) < LOCK_THRESHOLD

        lines += [
            "",
            "--- ZINF / ZSUP APPROXIMATION (GAP) ANALYSIS ---",
            f"  Gap = Zsup - Zinf expressed as % of Zsup.",
            f"  Iteration 1  gap : {first_gap_pct:.4f}%",
            f"  Iteration {last_iter} gap : {last_gap_pct:.4f}%",
            f"  Total reduction  : {total_reduction:.4f}%",
            "",
            f"  Recent trend (last {tail_n} iterations):",
            f"    Gap change  : {recent_change:+.4f}%  (positive = improving)",
            f"    Average gap : {recent_avg_gap:.4f}%",
            "",
        ]

        if is_locked:
            lines += [
                f"  LOCKED: YES — The gap changed less than {LOCK_THRESHOLD}% over the last {tail_n} iterations.",
                "  The Zinf and Zsup bounds are no longer approaching each other.",
            ]
        else:
            lines += [
                f"  LOCKED: NO — The gap is still reducing (change = {recent_change:+.4f}% in last {tail_n} iters).",
            ]

        # Last-7 iteration table
        lines += [
            "",
            f"  Gap per iteration (last {min(7, total_iters)}):",
            f"  {'Iter':>5} | {'Zinf':>14} | {'Zsup':>14} | {'Gap %':>8}",
            "  " + "-" * 50,
        ]
        for _, row in df.tail(10).iterrows():
            lines.append(
                f"  {int(row['Iteration']):>5} | {row['Zinf']:>14,.0f} | {row['Zsup']:>14,.0f} | {row['gap_pct']:>8.4f}%"
            )

        # -----------------------------------------------------------------
        # 2-b  Cuts per iteration – is the cut pool growing normally?
        # -----------------------------------------------------------------
        cuts_all    = df_cuts['Optimality']
        cuts_mean   = cuts_all.mean()
        cuts_std    = cuts_all.std()
        cuts_cv     = cuts_std / cuts_mean * 100 if cuts_mean else 0

        recent_cuts     = df_cuts.tail(tail_n)['Optimality']
        recent_cuts_mean = recent_cuts.mean()
        recent_cuts_std  = recent_cuts.std()
        recent_cuts_cv   = recent_cuts_std / recent_cuts_mean * 100 if recent_cuts_mean else 0

        # Stable = coefficient of variation < 5% in recent window
        CUT_CV_THRESHOLD = 5.0
        cuts_stable = recent_cuts_cv < CUT_CV_THRESHOLD

        lines += [
            "",
            "--- CUTS PER ITERATION ANALYSIS ---",
            f"  'Optimality' column = number of new Benders cuts added each iteration.",
            f"  Overall ({total_iters} iterations):",
            f"    Mean : {cuts_mean:.1f} cuts/iter",
            f"    Std  : {cuts_std:.1f}",
            f"    CV   : {cuts_cv:.1f}%  (coefficient of variation)",
            f"    Min  : {int(cuts_all.min())}   Max: {int(cuts_all.max())}",
            "",
            f"  Last {tail_n} iterations:",
            f"    Mean : {recent_cuts_mean:.1f}   Std: {recent_cuts_std:.1f}   CV: {recent_cuts_cv:.1f}%",
            "",
        ]

        if cuts_stable:
            lines += [
                f"  CUT STABILITY: STABLE (CV < {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
                "  The number of new cuts per iteration is consistent.",
                "  Combined with a locked gap, this strongly suggests the algorithm has stalled:",
                "  cuts are being added but they are not improving the lower bound.",
            ]
        else:
            lines += [
                f"  CUT STABILITY: VARIABLE (CV >= {CUT_CV_THRESHOLD}% in last {tail_n} iters).",
                "  The cut count is still fluctuating, which may indicate active exploration.",
            ]

        lines += [
            "",
            f"  Cuts per iteration (last {min(10, total_iters)}):",
            f"  {'Iter':>5} | {'Cuts (Optimality)':>18}",
            "  " + "-" * 28,
        ]
        for _, row in df_cuts.tail(10).iterrows():
            lines.append(f"  {int(row['Iteration']):>5} | {int(row['Optimality']):>18}")

        # -----------------------------------------------------------------
        # Summary for LLM
        # -----------------------------------------------------------------
        lines += [
            "",
            "=== DIAGNOSIS SUMMARY FOR LLM ===",
            f"- Convergence: NOT CONVERGED after {total_iters} iterations.",
            f"- Final gap (Zsup - Zinf) / Zsup = {last_gap_pct:.4f}%.",
            f"- Locked: {'YES' if is_locked else 'NO'} "
            f"(gap changed {recent_change:+.4f}% in last {tail_n} iters; threshold = {LOCK_THRESHOLD}%).",
            f"- Cuts stable: {'YES' if cuts_stable else 'NO'} "
            f"(recent CV = {recent_cuts_cv:.1f}%; threshold = {CUT_CV_THRESHOLD}%)."
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cost Analysis
# ---------------------------------------------------------------------------

# Friendly descriptions for each penalty column so the LLM can reason about
# the physical cause without knowing the raw Spanish CSV column names.
_PENALTY_DESCRIPTIONS = {
    "Pen: Vertimiento hidro":              "Hydro spillage penalty — water being discarded because reservoirs are full or downstream constraints prevent use.",
    "Pen: Volumen operativo min. hidro":   "Min hydro operating-volume penalty — reservoir fell below its minimum allowed storage level.",
    "Pen: Volumen operativo max. hidro":   "Max hydro operating-volume penalty — reservoir exceeded its maximum allowed storage level.",
    "Pen: Defluencia total max. hidro":    "Max total hydro outflow penalty — total discharge (turbine + spillage) exceeded its upper bound.",
    "Pen: Defluencia total min. hidro":    "Min total hydro outflow penalty — total discharge fell below its minimum required outflow (e.g. environmental flow).",
    "Pen: Riego hidro":                    "Hydro irrigation penalty — irrigation demand downstream of the reservoir was not met.",
    "Pen: Restriccion de generacion":      "Generation restriction penalty — a generation limit (min or max) was violated, often indicating an infeasible or overly-tight constraint.",
}

_OP_COST_COL   = "Costo: Total operativo"
_STAGE_COL     = "Etapas"
_OP_COST_THRESHOLD = 0.80   # operating cost must be ≥ 80 % of total
_STAGE_PEN_THRESHOLD = 0.20 # flag stages where penalties ≥ 20 % of that stage's total


@mcp.tool()
def analyse_costs() -> str:
    """
    Analyse SDDP simulation operating costs and penalties.

    Part A — Total cost breakdown (porciones-de-el-costo-op.csv):
        Sums all cost categories (operating cost + all penalty types) to obtain
        the grand total and each category's share.

    Part B — 80 % health check:
        Warns if 'Costo: Total operativo' represents less than 80 % of the grand
        total, listing every penalty above 1 % share so the LLM can explain the
        cause to the user.

    Part C — Per-stage penalty hot-spots (costos-operativos-promed.csv):
        For every planning stage, computes penalty share = Σ(penalties) /
        (operating_cost + Σ(penalties)). Flags stages where penalty share ≥ 20 %,
        ranks them, and breaks down which penalty types dominate in each flagged
        stage — giving the LLM the information it needs to connect with SDDP
        documentation and explain root causes.
    """
    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    df_portions = pd.read_csv(
        Path(os.path.join(RESULTS_FOLDER, "porciones-de-el-costo-op.csv")),
        encoding="utf-8-sig",
    )
    df_stages = pd.read_csv(
        Path(os.path.join(RESULTS_FOLDER, "costos-operativos-promed.csv")),
        encoding="utf-8-sig",
    )
    df_portions.columns = df_portions.columns.str.strip()
    df_stages.columns   = df_stages.columns.str.strip()

    # Rename the value column for safety
    df_portions = df_portions.rename(columns={"Series 1": "value"})

    # ------------------------------------------------------------------
    # Part A — Total cost breakdown
    # ------------------------------------------------------------------
    grand_total = df_portions["value"].sum()
    df_portions["share_pct"] = df_portions["value"] / grand_total * 100

    op_row   = df_portions[df_portions["Category"] == _OP_COST_COL]
    op_value = float(op_row["value"].iloc[0]) if not op_row.empty else 0.0
    op_share = op_value / grand_total * 100

    pen_rows = df_portions[df_portions["Category"] != _OP_COST_COL].copy()
    pen_rows = pen_rows.sort_values("value", ascending=False)

    lines = [
        "=== SDDP COST ANALYSIS ===",
        "",
        "--- PART A: TOTAL COST BREAKDOWN ---",
        f"  Grand total (all categories) : {grand_total:>18,.2f}",
        f"  Operating cost               : {op_value:>18,.2f}  ({op_share:.1f}%)",
        f"  Total penalties              : {grand_total - op_value:>18,.2f}  ({100 - op_share:.1f}%)",
        "",
        f"  {'Category':<45} {'Value':>15}  {'Share':>7}",
        "  " + "-" * 72,
        f"  {_OP_COST_COL:<45} {op_value:>15,.2f}  {op_share:>6.1f}%",
    ]
    for _, row in pen_rows.iterrows():
        lines.append(
            f"  {row['Category']:<45} {row['value']:>15,.2f}  {row['share_pct']:>6.1f}%"
        )

    # ------------------------------------------------------------------
    # Part B — 80 % health check
    # ------------------------------------------------------------------
    lines += ["", "--- PART B: OPERATING COST HEALTH CHECK ---"]

    if op_share >= _OP_COST_THRESHOLD * 100:
        lines.append(
            f"  STATUS: OK — Operating cost represents {op_share:.1f}% of total "
            f"(threshold: {_OP_COST_THRESHOLD*100:.0f}%)."
        )
    else:
        lines += [
            f"  STATUS: WARNING ⚠ — Operating cost is only {op_share:.1f}% of total "
        ]
        for _, row in pen_rows[pen_rows["share_pct"] >= 1.0].iterrows():
            desc = _PENALTY_DESCRIPTIONS.get(row["Category"], "No description available.")
            lines.append(
                f"  {row['Category']:<45} {row['value']:>15,.2f}  {row['share_pct']:>6.1f}%  {desc}"
            )
        lines += [
            "",
            "  SDDP knowledge tags to query: high_penalty_costs, constraint_violation, model_instability",
        ]

    # ------------------------------------------------------------------
    # Part C — Per-stage penalty hot-spots
    # ------------------------------------------------------------------
    pen_cols = [c for c in df_stages.columns if c.startswith("Pen:")]
    df_stages["total_penalty"] = df_stages[pen_cols].sum(axis=1)
    df_stages["stage_total"]   = df_stages[_OP_COST_COL] + df_stages["total_penalty"]
    df_stages["pen_share_pct"] = df_stages["total_penalty"] / df_stages["stage_total"] * 100

    flagged = df_stages[df_stages["pen_share_pct"] >= _STAGE_PEN_THRESHOLD * 100].copy()
    flagged = flagged.sort_values("pen_share_pct", ascending=False)

    lines += [
        "",
        "--- PART C: PER-STAGE PENALTY HOT-SPOTS ---",
        f"  Flagging stages where penalties ≥ {_STAGE_PEN_THRESHOLD*100:.0f}% of that stage's total cost.",
        f"  Total stages: {len(df_stages)}   Flagged: {len(flagged)}",
    ]

    if flagged.empty:
        lines.append("  No stages exceed the penalty threshold. Costs look healthy across all stages.")
    else:
        lines += [
            "",
            f"  {'Stage':<26} {'Op.Cost':>12} {'Tot.Penalty':>12} {'Pen %':>7}  Dominant penalties",
            "  " + "-" * 100,
        ]
        for _, row in flagged.iterrows():
            # Find which individual penalties are non-negligible (> 5 % of stage total)
            dominant = []
            for col in pen_cols:
                val = row[col]
                if val > 0 and (val / row["stage_total"]) >= 0.05:
                    share = val / row["stage_total"] * 100
                    dominant.append(f"{col} ({share:.0f}%)")
            dominant_str = " | ".join(dominant) if dominant else "—"
            lines.append(
                f"  {str(row[_STAGE_COL]):<26} {row[_OP_COST_COL]:>12,.1f} "
                f"{row['total_penalty']:>12,.1f} {row['pen_share_pct']:>7.1f}%  {dominant_str}"
            )

        # Summary of which penalty TYPES appear most across flagged stages
        pen_totals_flagged = flagged[pen_cols].sum().sort_values(ascending=False)
        pen_totals_flagged = pen_totals_flagged[pen_totals_flagged > 0]

        lines += [
            "",
            "  Penalty-type totals across flagged stages (descending):",
            f"  {'Penalty category':<45} {'Total value':>15}  Physical meaning",
            "  " + "-" * 100,
        ]
        for col, val in pen_totals_flagged.items():
            desc = _PENALTY_DESCRIPTIONS.get(col, "No description available.")
            lines.append(f"  {col:<45} {val:>15,.2f}  {desc}")

    # ------------------------------------------------------------------
    # Diagnosis summary for LLM
    # ------------------------------------------------------------------
    flagged_stages_list = flagged[_STAGE_COL].tolist() if not flagged.empty else []
    top_penalties_global = pen_rows["Category"].head(3).tolist()

    lines += [
        "",
        "=== DIAGNOSIS SUMMARY FOR LLM ===",
        f"- Grand total cost         : {grand_total:,.2f}",
        f"- Operating cost share     : {op_share:.1f}%  "
        f"({'OK' if op_share >= _OP_COST_THRESHOLD * 100 else 'WARNING — below 80% threshold'})",
        f"- Largest penalty type(s)  : {', '.join(top_penalties_global)}",
        f"- Stages with high penalty : {len(flagged)} of {len(df_stages)} "
        f"({'none' if not flagged_stages_list else ', '.join(str(s) for s in flagged_stages_list[:5])}{'...' if len(flagged_stages_list) > 5 else ''})"
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# SDDP Knowledge
# ---------------------------------------------------------------------------



def _load_knowledge() -> list[dict]:
    """Load and merge all JSON files from the knowledge directory."""
    entries = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
            entries.extend(data if isinstance(data, list) else [data])
    return entries


@mcp.tool()
def list_sddp_knowledge() -> str:
    """
    List all available SDDP knowledge entries (id, topic, title, related_problems).

    Use this for discovery — call it once to understand what topics are covered,
    then call get_sddp_knowledge() to fetch the full content of the entries you need.
    Do NOT call this on every turn; results are stable across the session.
    """
    entries = _load_knowledge()
    lines = [
        "=== SDDP KNOWLEDGE BASE — AVAILABLE ENTRIES ===",
        f"Total entries: {len(entries)}",
        "",
        f"{'ID':<45} {'TOPIC':<30} TITLE",
        "-" * 110,
    ]
    for e in entries:
        problems = ", ".join(e.get("related_problems", []))
        lines.append(f"{e['id']:<45} {e.get('topic', ''):<30} {e['title']}")
        lines.append(f"  related_problems: {problems}")
    return "\n".join(lines)


@mcp.tool()
def get_sddp_knowledge(topics: list[str] = None, problems: list[str] = None) -> str:
    """
    Retrieve full SDDP knowledge entries whose topic OR related_problems match any
    of the given filter strings (case-insensitive, partial match allowed).

    Args:
        topics:   Filter by topic field. E.g. ["convergence", "solver_performance"].
        problems: Filter by related_problems tags. E.g. ["ineffective_cuts", "penalty_influence"].

    Returns a structured text with the content of every matched entry, including references.
    Call list_sddp_knowledge() first to discover valid topic and problem tag names.
    """
    if not topics and not problems:
        return (
            "No filters provided. "
            "Call list_sddp_knowledge() first to discover available topics and related_problems tags, "
            "then pass at least one topic or problem to this tool."
        )

    topics_lower   = [t.lower() for t in (topics or [])]
    problems_lower = [p.lower() for p in (problems or [])]

    def matches(entry: dict) -> bool:
        topic_match = any(
            t in entry.get("topic", "").lower() for t in topics_lower
        )
        problem_match = any(
            p in rp.lower()
            for rp in entry.get("related_problems", [])
            for p in problems_lower
        )
        return topic_match or problem_match

    entries  = _load_knowledge()
    matched  = [e for e in entries if matches(e)]

    if not matched:
        return (
            f"No entries matched topics={topics} / problems={problems}. "
            "Call list_sddp_knowledge() to see valid filter values."
        )

    lines = [
        f"=== SDDP KNOWLEDGE — {len(matched)} MATCHED ENTRIES ===",
        f"Filters  →  topics: {topics}  |  problems: {problems}",
        "",
    ]
    for e in matched:
        refs = "  ".join(
            f"[{r['title']}]({r['url']})" for r in e.get("references", [])
        )
        lines += [
            f"### {e['title']}",
            f"ID      : {e['id']}",
            f"Topic   : {e.get('topic', '')}",
            f"Problems: {', '.join(e.get('related_problems', []))}",
            "",
            e["content"],
            "",
            f"References: {refs}" if refs else "",
            "-" * 80,
            "",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
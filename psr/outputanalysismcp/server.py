#!/usr/bin/env python3
"""MCP server for PSR Output Analysis."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from pathlib import Path
import json
import os

from .policy_functions import get_policy_error_report, build_simulation_vs_policy_report
from .cost_functions import build_cost_health_report, build_cost_dispersion_report, build_penalty_participation_report
from .execution_time_functions import build_execution_time_report
from .common import read_csv

# Root of the installed package — used to locate the knowledge-base folder.
_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"

RESULTS_FOLDER: Path = Path(".")

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

        "Cost analysis (call after analyse_policy_convergence()): "
        "  analyse_cost_health() — 80% operating-cost check: full penalty breakdown with % share, "
        "    flags whether operating cost is healthy (≥ 80% of total), lists significant penalties, "
        "    and detects per-stage hot-spots where penalties ≥ 20% of that stage's total. "
        "    Embeds sim_total_cost_portions and sim_average_cost_stage knowledge. "
        "  analyse_cost_dispersion() — P10-P90 cost spread per stage: flags high-uncertainty stages "
        "    (CV > 0.30), reports ENA correlation if the inflow file is available. "
        "    Embeds sim_cost_dispersion knowledge. "
        "  analyse_penalty_participation() — scenario-level penalty participation: finds the scenarios "
        "    and planning stages where penalty share of total cost is highest. "
        "    Use after analyse_cost_health() identifies significant penalties. "

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
# Setup
# ---------------------------------------------------------------------------

@mcp.tool()
def get_avaliable_results(study_path: str) -> list[str]:
    """Set the results folder and return the list of available CSV files."""
    global RESULTS_FOLDER
    RESULTS_FOLDER = Path(os.path.join(study_path, "results"))

    return [f.name for f in RESULTS_FOLDER.iterdir() if f.is_file()]


# ---------------------------------------------------------------------------
# Policy convergence
# ---------------------------------------------------------------------------

@mcp.tool()
def analyse_policy_convergence() -> str:
    """
    Analyse SDDP policy convergence from the results CSVs.

    Returns a structured text report with errors and actions suggested

    Data sources: convergencia.csv, nuevos-cortes-por-iterac.csv
    """
    return get_policy_error_report(RESULTS_FOLDER)


@mcp.tool()
def policy_convergence_report() -> str:
    """
    Get the daitails of the convergence graphs, but without analysis. 

    Data sources: convergencia.csv, nuevos-cortes-por-iterac.csv
    """
    return get_policy_error_report(RESULTS_FOLDER)

# ---------------------------------------------------------------------------
# Policy vs simulation 
# ---------------------------------------------------------------------------
@mcp.tool()
def analyse_policy_vs_simulation() -> str:
    """
    Get the daitails of the convergence graphs, but without analysis. 

    Data sources: convergencia.csv, nuevos-cortes-por-iterac.csv
    """
    return build_simulation_vs_policy_report(RESULTS_FOLDER)

# ---------------------------------------------------------------------------
# Cost analysis
# ---------------------------------------------------------------------------

@mcp.tool()
def analyse_cost_health() -> str:
    """
    Analyse SDDP simulation operating cost health.

    (A) Total cost breakdown — operating cost vs. every penalty category with % share.
    (B) 80% health-check — warns if operating cost < 80% of grand total.
    (C) Per-stage hot-spots — flags stages where penalties ≥ 20% of that stage's total cost.

    Embeds sim_total_cost_portions and sim_average_cost_stage knowledge.

    Data sources: porciones-de-el-costo-op.csv, costos-operativos-promed.csv
    """
    return build_cost_health_report(RESULTS_FOLDER)


@mcp.tool()
def analyse_cost_dispersion() -> str:
    """
    Analyse stochastic cost uncertainty per planning stage (P10-P90 spread).

    Flags stages with high coefficient of variation (CV > 0.30) and, if the
    inflow file is available, reports ENA (total inflow energy) correlation.

    Embeds sim_cost_dispersion knowledge.

    Data sources: dispersin-del-costo-op.csv, energa-total-afluente.csv (optional)
    """
    return build_cost_dispersion_report(RESULTS_FOLDER)


@mcp.tool()
def analyse_penalty_participation() -> str:
    """
    Analyse scenario-level penalty participation per planning stage.

    Finds which scenarios and stages have the highest penalty share of total cost,
    ranks hot-spot stages, and shows per-scenario breakdown for the worst stages.

    Data sources: participacin-de-las-pena.csv
    """
    return build_penalty_participation_report(RESULTS_FOLDER)




# ---------------------------------------------------------------------------
# Execution time analysis
# ---------------------------------------------------------------------------

@mcp.tool()
def analyse_execution_time() -> str:
    """
    Analyse SDDP computational performance across policy iterations and stages.

    (1) Total times — total policy and simulation wall-clock time.
    (2) Iteration trend — Forward and Backward times per iteration; growth factors
        comparing the first and last thirds to detect non-linear slowdown (accelerating).
        Backward/Forward ratio is reported; ratio >> 1 is expected due to the x·y
        subproblems solved in the backward phase.
    (3) Stage dispersion hot-spots — flags stages where the MAX scenario time is
        more than 2x the average, signalling MIP complexity, intertemporal coupling,
        or feasibility tightness in specific scenarios.

    Data sources: tiempos-de-ejecucin-forw.csv, dispersin-de-los-tiempos.csv,
                  tiempo-de-ejecucin-polit.csv, tiempo-de-ejecucin-simul.csv
    """
    return build_execution_time_report(RESULTS_FOLDER)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()

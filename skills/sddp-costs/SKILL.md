---
name: sddp-costs
description: >
  Analyse SDDP simulation costs: 80% operating-cost health check, per-stage
  penalty participation, cost dispersion (P10-P90), and MIP solver status
  heatmap for hourly simulation runs. Use when the user asks about costs,
  penalties, constraint violations, the 80% rule, cost composition, feasibility,
  relaxed solutions, solver quality, or mentions keywords like "cost", "custo",
  "penalty", "penalidade", "80%", "violation", "solver", "heatmap",
  "dispersão", "dispersion", "P10", or "P90".
version: 1.0.0
---

The user wants to analyse SDDP simulation costs. Follow this workflow:

1. **Get the case path.** Ask if not provided.

2. **Extract and list results.**
   - `extract_html_results(study_path)` → `get_avaliable_results(study_path)`.

3. **Explore files first.** Call `df_get_columns` + `df_get_head` on every cost CSV before choosing parameters.

4. **Cost health (80 % rule).**
   - Find the cost-breakdown CSV (names: `cost`, `custo`, `portions`, `composição`).
   - `df_analyze_composition` — operating cost as target, all cost columns in total, flag stages where share < 80 %.
   - Fetch: `get_sddp_knowledge(ids=["sim_total_cost_portions"])`.

5. **Penalty participation (bar chart).**
   - Find the per-stage penalty CSV (columns = penalty agents, rows = stages).
   - `df_get_summary` — identify which penalty columns are non-zero (max > 0).
   - `df_filter_above_threshold` — find stages where each active penalty exceeds a meaningful threshold.
   - Fetch: knowledge already loaded from step 4.

6. **Cost dispersion (P10 / P90).**
   - Find the dispersion CSV and run `df_get_summary` for mean, P10, P90 per stage.
   - If an ENA / inflow file is available: `df_cross_correlation`.
   - Fetch: `get_sddp_knowledge(ids=["sim_cost_dispersion", "sim_average_cost_stage"])`.

7. **Solver status heatmap (MIP runs only).**
   - Look for a CSV where columns are scenarios and values are 0–3.
   - `df_analyze_heatmap(mode="solver_status")` — rank critical scenarios and stages.
   - If a penalty-participation heatmap exists: `df_analyze_heatmap(mode="threshold", threshold=5.0)`.
   - Fetch: `get_sddp_knowledge(ids=["sim_solver_status", "sim_solver_troubleshooting"])`.

8. **Format the response.**
   - Respond in the user's language.
   - Four sections: **A. Cost Health**, **B. Cost Dispersion**, **C. Penalty Participation**, **D. Solver Status** — each with a verdict.
   - Highlight stages that appear as critical in both solver status and penalty heatmaps.
   - Cite knowledge entries with reference URLs.

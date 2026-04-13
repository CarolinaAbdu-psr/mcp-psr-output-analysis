---
name: sddp-analyze
description: >
  Complete SDDP output analysis workflow covering convergence, cost health,
  penalty participation, solver status heatmap, and computational performance.
  Use when the user provides an SDDP case folder path and asks for a full
  analysis, a complete report, or says something like "analyze this case",
  "check these results", or "what do the results look like". This skill
  orchestrates all other sddp-* skills in the correct order and produces a
  single consolidated report with an executive summary.
version: 1.0.0
---

# Skill: Complete SDDP Output Analysis

Run a full diagnostic of an SDDP case: convergence, policy validation,
simulation costs, and computational performance.

This skill orchestrates the four domain skills in the correct order.
Apply the **sddp-output-format** rules to the final consolidated response.

---

## Execution Order

### Step 0 — Extract Results from HTML

```
extract_html_results(study_path=<case_folder>)
```

This parses the SDDP dashboard HTML file and exports every chart as a CSV
into `{case_folder}/results/`. Call once per session. If the results folder
already contains CSVs from a previous run, you may skip this step.

---

### Step 1 — List Available Results

```
get_avaliable_results(study_path=<case_folder>)
```

Inspect the returned file list and mentally map filenames to these categories:
- Convergence / policy bounds (use in Step 2)
- Policy vs. simulation comparison (use in Step 2)
- Simulation costs / breakdown (use in Step 3)
- Execution time / performance (use in Step 4)

If a file's purpose is unclear, call `df_get_columns` on it to inspect its
column names before deciding which analysis step to use it for.

---

### Step 2 — Convergence Analysis

Follow the **sddp-convergence** skill in full:

A. Policy convergence (Zinf vs. tolerance band):
   - `df_analyze_bounds` → convergence check
   - `df_analyze_stagnation` → stagnation check (only if not converged)
   - `get_sddp_knowledge(topics=["convergence"])`

B. Policy vs. simulation validation:
   - `df_analyze_bounds` → simulation mean vs. policy confidence band
   - `get_sddp_knowledge(topics=["convergence_validation"])`

**If convergence is Critical:** note it prominently at the top of the final
report. Cost and performance analysis can still run but results must be
interpreted with caution.

---

### Step 3 — Simulation Cost Analysis

Follow the **sddp-costs** skill in full:

A. Cost health (80 % rule):
   - `df_get_columns` + `df_get_head` → understand file structure
   - `df_analyze_composition` → operating cost share per stage
   - `get_sddp_knowledge(ids=["sim_total_cost_portions"])`

B. Cost dispersion (P10/P90):
   - `df_get_summary` → mean, P10, P90 per stage
   - `df_cross_correlation` → ENA vs. cost (if ENA data available)
   - `get_sddp_knowledge(ids=["sim_cost_dispersion", "sim_average_cost_stage"])`

C. Penalty participation (bar chart):
   - `df_get_head` → confirm column structure (columns = penalty agents)
   - `df_filter_above_threshold` → find stages/agents above significance threshold
   - `df_analyze_composition` → share of dominant penalties in total cost
   - `get_sddp_knowledge(ids=["sim_total_cost_portions"])`

D. Solver status heatmap (MIP runs only):
   - `df_get_head` → confirm heatmap structure (columns = scenarios)
   - `df_analyze_heatmap(mode="solver_status")` → critical scenario/stage ranking
   - `df_analyze_heatmap(mode="threshold", threshold=5.0)` → penalty heatmap if available
   - `get_sddp_knowledge(ids=["sim_solver_status", "sim_solver_troubleshooting"])`

---

### Step 4 — Performance Analysis

Follow the **sddp-performance** skill in full:

A. Iteration time growth:
   - `df_get_summary` → Forward, Backward, Total time stats
   - `df_analyze_stagnation` → detect abnormal growth
   - `get_sddp_knowledge(ids=["exec_time_iteration_growth"])`

B. Forward/Backward balance:
   - Compute ratio from summary stats

C. Stage hot-spots:
   - `df_analyze_composition` or `df_get_summary` on per-stage time
   - `get_sddp_knowledge(ids=["exec_time_dispersion_causes"])`

---

## Final Consolidated Report

After all four steps, produce a single response structured as:

```
# SDDP Analysis Report — <case name or folder>

## Executive Summary
[3–5 bullet points: one per domain, verdict + one-sentence finding]

---

## 1. Convergence
[Full convergence section from Step 2]

---

## 2. Simulation Costs
[Full cost section from Step 3]

---

## 3. Computational Performance
[Full performance section from Step 4]

---

## Overall Recommendations
[Consolidated, prioritised list of actions]
```

Verdicts to use in the Executive Summary:

| Verdict  | Symbol |
|----------|--------|
| OK       | ✓      |
| Warning  | ⚠      |
| Critical | ✗      |

Example:
```
- Convergence ✓ — Zinf entered the tolerance band at iteration 18.
- Policy vs. Simulation ✓ — Simulation mean is within the policy CI.
- Cost Health ⚠ — Stage 6 has only 73 % operating cost (below 80 % guideline).
- Cost Dispersion ✓ — P10–P90 spread is within expected seasonal range.
- Performance ✓ — Iteration time growth is consistent with cut accumulation.
```

---

## Adding New Analyses in the Future

When new knowledge entries or CSV types become available:
1. Add the new entry to the appropriate `sddp_knowledge/*.json` file.
2. Create a new `sddp-output-skills/<skill-name>/SKILL.md` with the analysis steps.
3. Add a new `@mcp.prompt()` in `server.py` that loads the new skill.
4. Reference the new skill in this master skill under the appropriate step
   (or add a new Step 5, 6, etc.).

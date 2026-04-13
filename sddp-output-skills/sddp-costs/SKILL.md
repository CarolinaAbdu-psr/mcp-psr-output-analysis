---
name: sddp-costs
description: >
  Deep-dive into SDDP simulation costs: 80% operating-cost health check,
  P10-P90 dispersion with ENA correlation, per-stage penalty participation,
  and MIP solver status heatmap (for hourly simulation runs). Use when the
  user asks about costs, penalties, constraint violations, the 80% rule,
  cost dispersion, feasibility, relaxed solutions, or uses keywords like
  "custo", "penalidade", "penalty", "cost", "violation", "solver status",
  or "heatmap". Requires an SDDP case folder with extracted CSV results.
version: 1.0.0
---

# Skill: SDDP Simulation Cost Analysis

Perform a deep-dive into the simulation costs of an SDDP run.
Covers four sub-analyses:
- A. Cost health (80 % rule)
- B. Cost dispersion (P10 / P90) and hydrological correlation
- C. Penalty participation — time-varying bar chart
- D. Solver status heatmap (MIP hourly simulation only)

Apply the **sddp-output-format** rules to the final response.

---

## Prerequisites

- `extract_html_results(study_path)` must have already run.
- `get_avaliable_results(study_path)` must have already run.

---

## File Exploration Pattern

Before running any analysis, always call these two tools on unfamiliar files:

```
df_get_columns(file_path=<csv>)        # discover column names
df_get_head(file_path=<csv>, n=5)      # understand data format and scale
```

If the file is small, use `df_get_size` to download it entirely:

```
df_get_size(file_path=<csv>, max_cells=500)   # inline content if ≤ 500 cells
```

---

## Step-by-Step Instructions

### A. Cost Health Check (80 % Rule)

**Goal:** Verify that the Operating Cost represents at least 80 % of the Total Cost.
Excessive penalties are a red flag indicating constraint violations.

#### A1. Identify the cost-composition file

Look for a CSV with name fragments like `cost`, `custo`, `total_cost`, `portions`,
`composição`, or `breakdown`. Call `df_get_columns` + `df_get_head` to confirm.

Look for columns that represent cost components. Typical patterns:
- Total operating cost: contains "Total operativo", "Operating Cost", "Costo operativo"
- Penalty cost(s): contains "Pen", "Penalty", "Penalidade", "Violation"
- Fuel / Thermal: contains "Fuel", "Combustível", "Térmico"
- Total cost: contains "Total Cost", "Custo Total", or is a sum of the above

#### A2. Composition analysis

```
df_analyze_composition(
    file_path=<cost_csv>,
    target_cost_col=<operating_cost_col>,
    all_cost_cols_json='["<col1>", "<col2>", ...]',
    label_col=<stage_col>,
    min_threshold=80.0,   # flag stages where operating cost < 80%
    max_threshold=0.0,    # disabled
)
```

Interpret:
- `global_summary.target_share_of_total_pct` ≥ 80 % → healthy (OK)
- Between 60–80 % → borderline (Warning)
- < 60 % → high penalty presence (Critical)
- `criticality_report` → lists the specific stages that breach the 80 % threshold

#### A3. Fetch cost health knowledge

```
get_sddp_knowledge(ids=["sim_total_cost_portions"])
```

Cite this entry when reporting the 80 % threshold and its significance.

---

### B. Cost Dispersion (P10 / P90 Spread)

**Goal:** Quantify how much cost uncertainty exists across scenarios, and
correlate it with hydrological variability (ENA — Natural Inflow Energy).

#### B1. Identify the dispersion file

Look for a CSV with name fragments like `dispersion`, `dispersão`, `percentile`,
`p10`, `p90`, or `cost_series`. Call `df_get_columns` + `df_get_head` to confirm.

Look for columns: average / mean cost, P10, P90, and optionally ENA or inflow.

#### B2. Summary statistics

```
df_get_summary(
    file_path=<dispersion_csv>,
    operations_json='{"<mean_col>": ["mean", "std"], "<p10_col>": ["min", "mean"], "<p90_col>": ["mean", "max"]}'
)
```

Compute P10–P90 spread % per stage = (P90 − P10) / mean × 100.
Identify stages with the highest spread (highest uncertainty).

#### B3. ENA correlation (if available)

```
df_cross_correlation(
    file_path_a=<ena_csv>,
    file_path_b=<cost_csv>,
    col_a=<ena_col>,
    col_b=<mean_cost_col>,
    join_on=<stage_col_if_available>,
)
```

Interpret:
- Strong negative r (< −0.7) → higher inflow → lower cost (expected, OK)
- Weak |r| (< 0.4) → costs driven by factors other than hydrology (Warning)
- Positive r → unusual; possible model data issue (Critical)

#### B4. Fetch dispersion knowledge

```
get_sddp_knowledge(ids=["sim_cost_dispersion", "sim_average_cost_stage"])
```

---

### C. Penalty Participation — Time-Varying Bar Chart

**Goal:** Identify which penalties are active at each stage, and which stages
or penalties are most problematic.

#### C1. Identify the per-stage penalty file

Look for a CSV with name fragments like `penalty`, `penalidade`, `violation`,
`pen_stage`, or `pen_by_stage`. It is a bar-chart CSV where:
- Rows = stages (time steps)
- Columns = individual penalty agents (e.g., "Pen: Déficit", "Pen: Vertimento")

Call `df_get_columns` + `df_get_head` to confirm the structure.

#### C2. Overview: which penalties exist at all?

```
df_get_summary(
    file_path=<penalty_csv>,
    operations_json='{"<pen_col_1>": ["mean", "max"], "<pen_col_2>": ["mean", "max"], ...}'
)
```

Columns with `max = 0` are inactive across all stages — exclude them from
further analysis.

#### C3. Threshold filter: find stages where each penalty is significant

Choose a threshold appropriate to the units (e.g., 5 % for percentage values,
or a domain-appropriate absolute value):

```
df_filter_above_threshold(
    file_path=<penalty_csv>,
    threshold=<value>,
    label_col=<stage_col>,
    direction="above",
    top_n=10,
)
```

Interpret the output:
- `top_exceeding_columns` → which penalties breach the threshold most often
  (ranked by frequency)
- `by_stage` → at each stage, exactly which penalties exceeded the threshold
  and by how much

#### C4. Deep-dive on dominant penalties

For the top 2–3 penalty columns from step C3, run composition analysis to get
their share of the total cost per stage:

```
df_analyze_composition(
    file_path=<cost_csv>,
    target_cost_col=<penalty_col>,
    all_cost_cols_json='["<col1>", "<col2>", ...]',
    label_col=<stage_col>,
    min_threshold=0.0,
    max_threshold=20.0,   # flag stages where this penalty > 20% of total
)
```

#### C5. Knowledge for penalties

```
get_sddp_knowledge(ids=["sim_total_cost_portions"])
```

If the solver status heatmap (Section D) shows Feasible or Relaxed results
in the same stages where penalties are high, also fetch:

```
get_sddp_knowledge(ids=["sim_solver_status", "sim_solver_troubleshooting"])
```

---

### D. Solver Status Heatmap (MIP Hourly Simulation Only)

**Goal:** Identify which stages and scenarios had non-optimal MIP solutions
(Feasible, Relaxed, or No Solution). Skip this section if the run used a
linear (LP) dispatch — no heatmap file will exist.

#### D1. Identify the solver status file

Look for a CSV with name fragments like `solver_status`, `solution_status`,
`mip_status`, `estado_solucao`, or `heatmap`. The file structure is:
- Rows = stages
- Columns = scenarios (named like "Scenario 1", "Cenário 2", "Scen_01")
- Cell values: 0 = Optimal, 1 = Feasible, 2 = Relaxed, 3 = No Solution

Call `df_get_head` to verify the structure before proceeding.

#### D2. Heatmap analysis

```
df_analyze_heatmap(
    file_path=<solver_status_csv>,
    mode="solver_status",
    label_col=<stage_col>,   # leave empty if stages are the row index
    top_n=10,
)
```

Interpret the result:
- `summary.status_distribution` → counts of each status across all cells
- `summary.critical_pct` → % of non-optimal solutions
  - < 5 %  → acceptable (OK)
  - 5–20 % → monitor (Warning)
  - > 20 % → systematic problem (Critical)
- `top_critical_scenarios` → scenarios with the most non-optimal stages
  (these are the "problem scenarios" to investigate)
- `top_critical_stages` → stages where the most scenarios had issues
  (these are the "problem periods" — likely high-demand or low-hydrology stages)

#### D3. Penalty participation heatmap (if available separately)

If there is a dedicated penalty-participation heatmap CSV (different from the
bar-chart penalty file), run:

```
df_analyze_heatmap(
    file_path=<penalty_heatmap_csv>,
    mode="threshold",
    label_col=<stage_col>,
    threshold=5.0,    # flag any scenario/stage with penalty participation > 5%
    top_n=10,
)
```

Cross-reference with the solver status results: stages that appear in
`top_critical_stages` of BOTH heatmaps are the highest-risk periods.

#### D4. Fetch solver status knowledge

```
get_sddp_knowledge(ids=["sim_solver_status", "sim_solver_troubleshooting"])
```

Cite `sim_solver_status` to explain the status codes and their meaning.
Cite `sim_solver_troubleshooting` if Relaxed or No Solution cells are found
(MIP timeout, conflicting constraints, etc.).

---

## Output Format

Follow the **sddp-output-format** rules.

Structure the response as four sections:

```
## A. Cost Health — Verdict: [OK / Warning / Critical]
## B. Cost Dispersion — Verdict: [OK / Warning / Critical]
## C. Penalty Participation — Verdict: [OK / Warning / Critical]
## D. Solver Status (MIP) — Verdict: [OK / Warning / Critical / N/A]
```

For section A: table of top 5 worst stages (lowest operating cost share).
For section B: table with mean, P10, P90, and spread % per stage.
For section C: table of the top penalty columns (frequency × max value)
  plus a per-stage list of which penalties were active at the worst stages.
For section D: table of `top_critical_stages` with their scenario counts,
  plus `top_critical_scenarios` with their stage counts.
  Highlight any stage that appears as critical in BOTH solver status and
  penalty participation analyses.

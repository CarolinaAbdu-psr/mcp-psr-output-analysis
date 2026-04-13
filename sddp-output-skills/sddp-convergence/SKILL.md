# Skill: SDDP Convergence Analysis

Perform a full convergence diagnostic for an SDDP run.
Covers two sub-analyses: (A) policy convergence and (B) policy-vs-simulation validation.

Apply the **sddp-output-format** rules to the final response.

---

## Prerequisites

- `extract_html_results(study_path)` must have already run (CSVs populated).
- `get_avaliable_results(study_path)` must have already run (RESULTS_FOLDER set).

---

## File Exploration Pattern

On any unfamiliar file, always call both tools before choosing parameters:

```
df_get_columns(file_path=<csv>)       # discover column names
df_get_head(file_path=<csv>, n=5)     # verify data format and scale
```

For small convergence files (typically few rows × few columns):

```
df_get_size(file_path=<csv>, max_cells=500)   # inline content if small enough
```

---

## Step-by-Step Instructions

### A. Policy Convergence

**Goal:** Verify that Zinf entered the Zsup confidence interval before the run stopped.

#### A1. Identify the convergence file

Scan the available CSV list for a file whose name contains words like
`convergence`, `convergência`, `policy`, `politica`, or `bounds`.
Call `df_get_columns` + `df_get_head` on candidates and look for columns
containing `Zinf`, `Zsup`, `Lower`, `Upper`, `Gap`, or `Tolerance`.

#### A2. Discover columns

```
df_get_columns(file_path=<convergence_csv>)
```

Map the result to these logical roles:
- `target_col`       → the column tracking Zinf (lower bound, e.g., "Zinf", "Lower Bound")
- `lower_bound_col`  → the column with the lower edge of the band (e.g., "Zsup - Tol", "Lower CI")
- `upper_bound_col`  → the column with the upper edge of the band (e.g., "Zsup + Tol", "Upper CI")
- `reference_val_col`→ the column with Zsup / average upper bound (e.g., "Zsup", "Upper Bound Mean")
- `iteration_col`    → the column with iteration numbers (e.g., "Iteration", "Iteração")

If the file has a "Gap %" or "Optimality" column, note it for step A3.

#### A3. Bounds analysis

```
df_analyze_bounds(
    file_path=<convergence_csv>,
    target_col=<zinf_col>,
    lower_bound_col=<lower_band_col>,
    upper_bound_col=<upper_band_col>,
    reference_val_col=<zsup_col>,
    iteration_col=<iteration_col>,   # optional
    lock_threshold=0.005,
)
```

Interpret the result:
- `bounds_status.inside_band_count` / `total_rows` → convergence rate
- `bounds_status.final_inside_band` = True → **converged** (OK)
- `bounds_status.final_inside_band` = False → **did not converge** (Critical or Warning)
- `stability.locked` = True → gap change stabilised below threshold

#### A4. Stagnation check

If `bounds_status.final_inside_band` is False, check whether Zinf has stagnated:

```
df_analyze_stagnation(
    file_path=<convergence_csv>,
    target_col=<zinf_col>,
    window_size=5,
    cv_threshold=1.0,
    slope_threshold=0.01,
)
```

Interpret:
- `stagnation_results` = "Stagnated" → Zinf stopped improving → potential stagnation problem
- `stagnation_results` = "Active"    → Zinf was still improving when the run stopped → likely
  needs more iterations

#### A5. Fetch convergence knowledge

```
get_sddp_knowledge(topics=["convergence"])
```

Use the content to diagnose the specific cause based on the data:
- Still approaching but run stopped → cite `sddp_non_convergence_insufficient_iterations`
- Stagnated flat → cite `sddp_non_convergence_stagnation_penalty` or
  `sddp_non_convergence_stagnation_forward`
- Converged → cite `sddp_convergence_theory` and `sddp_convergence_criteria`

---

### B. Policy vs. Simulation Validation

**Goal:** Verify that the final simulation cost falls within the policy confidence band.

#### B1. Identify the policy-vs-simulation file

Look for a CSV whose name suggests a comparison, such as:
`policy_vs_simulation`, `objective_function`, `sim_vs_policy`, `função objetivo`.

Call `df_get_columns` to confirm it contains columns for:
- Simulation mean cost
- Policy lower/upper confidence interval

#### B2. Bounds analysis

```
df_analyze_bounds(
    file_path=<pol_vs_sim_csv>,
    target_col=<simulation_mean_col>,
    lower_bound_col=<policy_lower_ci_col>,
    upper_bound_col=<policy_upper_ci_col>,
    reference_val_col=<policy_mean_col>,
)
```

Interpret:
- `bounds_status.final_inside_band` = True → simulation is consistent with policy (OK)
- `bounds_status.final_inside_band` = False → deviation detected (Warning or Critical)
  - Check reference_accuracy for the magnitude of the deviation

#### B3. Fetch validation knowledge

```
get_sddp_knowledge(topics=["convergence_validation"])
```

Match the finding to:
- Simulation outside band AND policy not converged → cite `objective_function_analysis_01`
  and `policy_divergence_causes_01` (incomplete policy)
- Simulation outside band BUT policy converged → cite `policy_divergence_causes_01`
  (sampling discrepancy) or `non_convexity_impact_01` (unit commitment / non-convexity)

---

## Output Format

Follow the **sddp-output-format** rules.

Structure the response as two sections:

```
## A. Policy Convergence — Verdict: [OK / Warning / Critical]
## B. Policy vs. Simulation Validation — Verdict: [OK / Warning / Critical]
```

For each section:
1. State the verdict and the key metric that drove it.
2. Provide a table with the last 5–10 iterations (Zinf, Zsup, Gap %).
3. Write the diagnosis paragraph, citing the relevant knowledge entry.
4. If the verdict is not OK, list specific recommendations.

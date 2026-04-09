---
name: sddp-convergence
description: Analyze SDDP policy convergence and validate the final simulation against the policy band.
---

# SDDP Convergence Check

Analyse SDDP policy convergence and validate the final simulation against the policy band.

## Workflow

### Step 1 — Setup
Call `get_avaliable_results(study_path)`.
Confirm the results folder is reachable before proceeding.

### Step 2 — Policy convergence
Call `analyse_policy_convergence()`.

Read the report carefully:
- **CONVERGED** -> Zinf entered the Zsup ± tolerance band. Confirm and note the final gap.
- **NOT CONVERGED** -> Identify the root cause from the report:
  - *Gap locked + penalty-driven*: excessive penalties are distorting Benders cuts. Action: review penalty values and constraint data.
  - *Gap locked + forward stagnation*: cuts are added but Zinf is not improving. Action: more iterations, or check non-convexities.
  - *Gap still reducing*: algorithm is progressing but needs more iterations.

Use the SDDP KNOWLEDGE entries at the bottom of the report to give a theoretically grounded explanation.

### Step 3 — Policy vs simulation
Call `analyse_policy_vs_simulation()`.

Check whether the final simulation average cost is inside the Zsup ± tolerance band across the last iterations.
- **INSIDE BAND** -> policy quality is validated; the simulation cost is consistent with the policy.
- **OUTSIDE BAND** -> report the absolute and percentage deviation. Possible causes: non-convexity, missing scenarios, or penalty spillover into the simulation.

### Step 4 — Verdict
Give a two-sentence verdict:
1. Whether the policy converged and is reliable.
2. Whether the final simulation is consistent with the converged policy.

Flag clearly if the user should re-run with more iterations or adjust penalty parameters.

## Rules
- Never skip Step 3 — a converged policy can still produce an inconsistent simulation.
- Cite specific numbers from the reports (gap %, deviation amount).
- Keep explanations short; point to SDDP KNOWLEDGE for deeper theory if needed.

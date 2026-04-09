---
name: sddp-full-analysis
description: Run a complete, structured SDDP output analysis for a given case path.
---

# SDDP Full Analysis

Run a complete, structured SDDP output analysis for a given case path.

## Workflow

### Step 1 — Setup
Call `get_avaliable_results(study_path)` with the path the user provided.
Report which CSV files were found. If the results folder is empty or missing, stop and ask the user to check the path.

### Step 2 — Policy convergence
Call `analyse_policy_convergence()`.

Read the CONVERGENCE STATUS field:
- **CONVERGED** -> confirm to the user and move on.
- **NOT CONVERGED** -> explain the reason (gap locked, penalty-driven stagnation, or gap still reducing). Use the SDDP KNOWLEDGE section in the report to give grounded context.

### Step 3 — Policy vs simulation
Call `analyse_policy_vs_simulation()`.

Check whether the final simulation cost falls inside the Zsup ± tolerance band.
- **INSIDE** -> normal result; confirm.
- **OUTSIDE** -> report the deviation (%) and note it as a risk even if convergence passed.

### Step 4 — Cost health
Call `analyse_cost_health()`.

Report:
- Operating cost share (is it above 80%?).
- Dominant penalties if any.
- Stages where penalties exceed 20% of that stage's total (hot-spots).

### Step 5 — Cost dispersion + ENA
Call `analyse_cost_dispersion()`.

Report the three metric groups:
1. **Pearson r** — uncertainty correlation (spread vs spread) and level correlation (avg vs avg).
2. **R²** — how much cost uncertainty is explained by ENA uncertainty.
3. **Elasticity** — "if ENA spread drops 10%, cost spread changes by X%".

Highlight high-CV stages (CV > 0.30).

### Step 6 — Penalty participation (conditional)
Call `analyse_penalty_participation()` **only if** Step 4 found operating cost below 80% or flagged hot-spot stages.

Report which scenarios and stages carry the heaviest penalty burden.

### Step 7 — Execution time
Call `analyse_execution_time()`.

Report:
- Total policy and simulation wall-clock times.
- Whether iteration time is growing (accelerating flag).
- High-dispersion stages (MIP or intertemporal coupling suspects).

### Step 8 — Summary
Present a concise executive summary with:
- Convergence status (one line).
- Policy-vs-simulation alignment (one line).
- Cost health verdict (one line).
- Top 2-3 risks or actions.

## Rules
- Always call `get_avaliable_results` first — without it no other tool works.
- Call `analyse_policy_convergence` before interpreting any other result.
- Do not dump raw tool output at the user; synthesise and explain.
- Use tables for per-stage data; use plain prose for verdicts.
- If a tool call fails (file not found), note it and continue with the remaining steps.

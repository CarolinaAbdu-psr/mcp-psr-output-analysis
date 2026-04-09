---
name: sddp-performance
description: Analyse SDDP computational performance: iteration growth, forward/backward balance, and stage-level hotspots. Use when the user asks for an analysis of SDDP execution times, iteration growth, or stage-level performance.
---

# SDDP Execution Time Analysis

Analyse SDDP computational performance: iteration growth, forward/backward balance, and stage-level hotspots.

## Workflow

### Step 1 — Setup
Call `get_avaliable_results(study_path)`.

### Step 2 — Execution time analysis
Call `analyse_execution_time()`.

Read and report three sections:

**Total times**
- Policy total time and simulation total time.
- Note if simulation time is disproportionately large relative to policy time.

**Iteration growth (Forward and Backward)**
- Forward growth factor: ratio of last-third to first-third average Forward time.
- Backward growth factor: same for Backward.
- **Accelerating flag**: if growth is non-linear, flag it explicitly.
- Report the Backward/Forward ratio. Values > 1 are expected (Backward solves N×Y subproblems per forward step). Very high ratios (>> 3) may indicate MIP complexity in backward.

Use the SDDP KNOWLEDGE entries (exec_time_iteration_growth) to explain why iteration time grows as Benders cuts accumulate.

**Stage dispersion hotspots**
- Stages where MAX scenario time > 2× the stage average.
- These signal: MIP complexity (binary variables), intertemporal coupling (long-horizon constraints), or feasibility tightness in specific scenarios.

Use exec_time_dispersion_causes knowledge to explain likely causes for flagged stages.

### Step 3 — Verdict
One-paragraph summary:
- Is the run performing normally?
- If accelerating: is it a concern for future runs with more iterations?
- Are stage hotspots isolated (a few MIP stages) or widespread?
- Concrete recommendation if issues found (e.g. "check binary variables in stages X, Y").

## Rules
- Backward/Forward ratio > 1 is always expected — do not flag it as an anomaly unless ratio > 5.
- Focus on the accelerating flag and stage hotspots as the actionable findings.
- If no stages are flagged and growth is linear, report a clean bill of health concisely.

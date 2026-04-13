# Skill: SDDP Computational Performance Analysis

Analyse the computational performance of an SDDP run.
Covers three sub-analyses: (A) iteration time growth, (B) Forward/Backward
balance, and (C) stage-level timing hot-spots.

Apply the **sddp-output-format** rules to the final response.

---

## Prerequisites

- `extract_html_results(study_path)` must have already run.
- `get_avaliable_results(study_path)` must have already run.

---

## File Exploration Pattern

```
df_get_columns(file_path=<csv>)       # discover column names
df_get_head(file_path=<csv>, n=5)     # verify data format and scale
df_get_size(file_path=<csv>)          # if small, read the whole file inline
```

---

## Step-by-Step Instructions

### A. Iteration Time Growth

**Goal:** Determine whether execution time per iteration is growing at a
healthy rate (cut accumulation) or at an anomalous rate.

#### A1. Identify the execution time file

Look for a CSV with name fragments like `execution_time`, `tempo_execucao`,
`iteration_time`, `performance`, or `runtime`.

Call `df_get_columns` + `df_get_head`. Look for columns:
- Total time per iteration: "Total", "Iteration Time", "Time (s)"
- Forward time: "Forward", "Frente", "Fwd"
- Backward time: "Backward", "Retaguarda", "Bwd"
- Iteration number: "Iteration", "Iteração"

#### A2. Summary statistics

```
df_get_summary(
    file_path=<exec_time_csv>,
    operations_json='{"<total_time_col>": ["mean", "std", "min", "max"], "<forward_col>": ["mean", "max"], "<backward_col>": ["mean", "max"]}'
)
```

#### A3. Stagnation / growth check

Use stagnation analysis to detect whether growth has levelled off or accelerated:

```
df_analyze_stagnation(
    file_path=<exec_time_csv>,
    target_col=<total_time_col>,
    window_size=5,
    cv_threshold=10.0,    # higher threshold — some growth is normal
    slope_threshold=0.05,
)
```

Interpret:
- `stagnation_results` = "Stagnated" → time has stabilised (OK — normal late-iteration behaviour)
- `stagnation_results` = "Active" and slope is moderate → healthy growth (OK)
- `stagnation_results` = "Active" and slope is high AND the run is in late iterations
  → potential cut pool inefficiency or memory pressure (Warning)

#### A4. Fetch iteration-growth knowledge

```
get_sddp_knowledge(ids=["exec_time_iteration_growth"])
```

Cite this entry when explaining the cut-accumulation pattern and the
Forward/Backward asymmetry. Note whether the observed ratio matches the
expected backward/forward subproblem count.

---

### B. Forward / Backward Balance

**Goal:** Verify that the backward-to-forward time ratio is consistent with
the expected (≈ number of uncertainty openings per forward series).

#### B1. Compute the ratio

From the `df_get_summary` result (Step A2):

```
backward_to_forward_ratio = mean(backward_time) / mean(forward_time)
```

Expected range: the ratio should be close to the number of uncertainty
scenarios opened per series (e.g., if 20 scenarios are used, ratio ≈ 20).

Interpret:
- Ratio ≈ expected → healthy asymmetry (OK)
- Ratio significantly > expected → backward subproblems are harder than forward
  ones (Warning — check for active binary variables or near-infeasible scenarios)
- Ratio ≈ 1 or < expected → investigate; forward phase may be unusually slow

#### B2. No additional tool call needed. Use `df_get_summary` results from A2.

---

### C. Stage-Level Timing Hot-Spots

**Goal:** Identify whether specific stages dominate execution time.

#### C1. Identify the per-stage time file (if separate from iteration file)

Some runs produce a per-stage time CSV (e.g., `stage_time`, `tempo_etapa`).
If available, call `df_get_columns` on it.

If only an iteration-level file exists, skip to the interpretation.

#### C2. Composition analysis on per-stage time

If per-stage data is available:

```
df_analyze_composition(
    file_path=<stage_time_csv>,
    target_cost_col=<max_stage_time_col>,   # or average stage time
    all_cost_cols_json='["<stage1_col>", "<stage2_col>", ...]',
    label_col=<stage_label_col>,
    min_threshold=0.0,
    max_threshold=0.0,    # no threshold — just report the distribution
)
```

Report the top 3 stages by time share.

Alternatively, use `df_get_summary` with `["mean", "max"]` on the stage time
column. A max/mean ratio > 3 indicates significant dispersion (Warning).

#### C3. Fetch stage-dispersion knowledge

```
get_sddp_knowledge(ids=["exec_time_dispersion_causes"])
```

Match the finding to the three structural causes in that entry:
- High dispersion in specific stages → MIP complexity (binary variables)
- Dispersion that grows with stages further from the end → intertemporal coupling
- Dispersion in peak-demand or dry-year scenarios → feasibility tightness

---

## Output Format

Follow the **sddp-output-format** rules.

Structure the response as three sections:

```
## A. Iteration Time Growth — Verdict: [OK / Warning / Critical]
## B. Forward / Backward Balance — Verdict: [OK / Warning / Critical]
## C. Stage Hot-Spots — Verdict: [OK / Warning / Critical]
```

For section A: include a compact table of time per iteration (sample every 5th
iteration if there are many) plus total wall-clock time.
For section B: show Forward mean, Backward mean, and computed ratio.
For section C: list the top 3 slowest stages and the max/mean ratio.

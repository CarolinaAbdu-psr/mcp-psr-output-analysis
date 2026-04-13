---
name: sddp-performance
description: >
  Analyse SDDP computational performance: iteration time growth from cut
  accumulation, Forward/Backward phase balance, and stage-level timing
  hot-spots caused by MIP complexity or intertemporal coupling. Use when the
  user asks about execution time, run duration, performance bottlenecks,
  slow iterations, solver speed, or mentions keywords like "performance",
  "execution time", "tempo de execução", "tempo", "forward", "backward",
  "iteration time", "slow", "lento", or "hot-spot".
version: 1.0.0
---

The user wants to analyse SDDP computational performance. Follow this workflow:

1. **Get the case path.** Ask if not provided.

2. **Extract and list results.**
   - `extract_html_results(study_path)` → `get_avaliable_results(study_path)`.

3. **Identify the execution time file.** Look for CSV names containing `execution_time`, `tempo`, `iteration_time`, or `performance`. Call `df_get_columns` + `df_get_head`. For small files use `df_get_size` to read inline.

4. **Summary statistics.**
   - `df_get_summary` — mean, std, max for Forward time, Backward time, and Total time per iteration.
   - Compute the Backward / Forward ratio from the means.

5. **Iteration time growth.**
   - `df_analyze_stagnation` on the Total time column — detect whether growth has levelled off (healthy) or is accelerating (warning).

6. **Stage hot-spots (if per-stage data is available).**
   - `df_get_summary` or `df_analyze_composition` on per-stage time — find the top 3 slowest stages and compute max / mean ratio.

7. **Fetch knowledge.**
   - `get_sddp_knowledge(ids=["exec_time_iteration_growth"])` — explain cut accumulation and Forward/Backward asymmetry.
   - `get_sddp_knowledge(ids=["exec_time_dispersion_causes"])` — explain stage hot-spots (MIP, intertemporal coupling, feasibility tightness).

8. **Format the response.**
   - Respond in the user's language.
   - Three sections: **A. Iteration Time Growth**, **B. Forward / Backward Balance**, **C. Stage Hot-Spots** — each with a verdict (OK / Warning / Critical).
   - Include a table: Forward mean, Backward mean, computed ratio, expected ratio.
   - Cite knowledge entries with reference URLs.

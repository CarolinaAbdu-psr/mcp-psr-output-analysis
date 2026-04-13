---
name: sddp-analyze
description: >
  Complete SDDP simulation output analysis. Use when the user provides an SDDP
  case folder path and asks to analyse, check, or report on simulation results.
  Triggers on phrases like "analyze this case", "check the results", "analisar
  este caso", "verificar os resultados", or when the user shares a folder path
  containing SDDP output files. Covers convergence, costs, penalties, solver
  status, and computational performance in a single consolidated report.
version: 1.0.0
---

The user wants a complete SDDP output analysis. Follow this workflow:

1. **Get the case path.** If the user has not provided a folder path, ask for it before proceeding.

2. **Extract results.**
   - `extract_html_results(study_path)` — parse the SDDP HTML dashboard and export all charts as CSVs.
   - `get_avaliable_results(study_path)` — set the results folder and list available CSV files.

3. **Explore before analysing.** For every CSV you open, always call `df_get_columns` and `df_get_head` first. Use `df_get_size` for small files to read them inline.

4. **Run analyses in order.**
   - Convergence: `df_analyze_bounds` (Zinf vs band) → `df_analyze_stagnation` (if not converged) → policy-vs-simulation `df_analyze_bounds`.
   - Costs: `df_analyze_composition` (80 % rule) → `df_filter_above_threshold` (per-stage penalties) → `df_analyze_heatmap` (solver status, if MIP run).
   - Performance: `df_get_summary` (Forward / Backward) → `df_analyze_stagnation` (time growth).

5. **Fetch knowledge for every diagnosis.** Call `get_sddp_knowledge(topics=[...])` or `get_sddp_knowledge(ids=[...])` before writing each diagnostic section. Always embed the knowledge content and cite the reference URL in the answer.

6. **Format the response.**
   - Respond in the **same language the user wrote in**.
   - Lead with an Executive Summary (one verdict line per analysis area: ✓ OK / ⚠ Warning / ✗ Critical).
   - Use Markdown tables for per-stage data.
   - Cite every knowledge entry as: `[Knowledge: <title> — <reference> (<url>)]`.

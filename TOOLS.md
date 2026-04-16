# MCP Tool Reference

This document describes every tool exposed by the **PSR Output Analysis** MCP server.

---

## Standard workflow

```
1. extract_html_results(study_path)       — export all charts as CSV + write _index.json
2. get_case_information(study_path)       — case metadata (call alongside step 1)
3. get_avaliable_results(study_path)      — catalogue: type / units / columns for every CSV
4. get_diagnostic_graph()                 — load decision graph; follow nodes in edge order
5. df_* tools                             — called as instructed by each graph node
6. get_conclusion_documentation(intent)  — on conclusion node: retrieve matching docs
```

---

## Setup & initialisation

### `extract_html_results(study_path)`

Parses the SDDP dashboard HTML and exports every chart as a CSV into `{study_path}/results/`.
Also writes `_index.json` (the manifest used by `get_avaliable_results`).

| Parameter | Type | Description |
|---|---|---|
| `study_path` | string | Absolute path to the SDDP case folder. |

**When to call:** Once per session, before anything else.

**Returns:** List of CSV file paths created (or error strings for failures).

---

### `get_case_information(study_path)`

Extracts structured case metadata from the dashboard HTML.

| Parameter | Type | Description |
|---|---|---|
| `study_path` | string | Absolute path to the SDDP case folder. |

**Returns:** Formatted text with: Case Summary, Model & Environment, Run Parameters, System Dimensions, Non-Convexities.

---

### `get_avaliable_results(study_path)`

Sets the active results folder and returns the full catalogue of available CSV files.

| Parameter | Type | Description |
|---|---|---|
| `study_path` | string | Absolute path to the SDDP case folder. |

**When to call:** After `extract_html_results`. Initialises `RESULTS_FOLDER` for all df_* tools.

**Returns:**
- **Full catalogue** (when `_index.json` exists): one block per file with `chart_type`, title, X/Y units, row count, and the **exact column names**. This replaces `df_get_columns` — column names from this output can be used directly in all df_* tools.
- **Plain filename list** with a warning (fallback when `_index.json` is absent).

Chart types written by `extract_html_results`: `line`, `bar`, `band` (area_range / confidence interval), `heatmap`.

**Example output block:**
```
  [band]  convergencia_USD.csv
    Title   : Convergência da Política
    X unit  : Iteração   Y unit: USD   Rows: 50
    Columns : Zinf, Zsup, Lower_CI, Upper_CI
```

---

## Diagnostic graph

### `get_diagnostic_graph()`

Loads `decision-trees/decision_graph.json` and returns a formatted, traversal-ready representation.

**Returns:** All entry points, nodes (with tools and expected state), and edges sorted by priority, plus traversal rules.

**Traversal rules (summary):**
1. Start at the entry point for the diagnosed problem.
2. For each `analysis` node: call all tools in `tools[]`, evaluate against `expected_state`, follow the lowest-priority satisfied edge.
3. On a `conclusion` node: call `get_conclusion_documentation(search_intent)`.

---

### `get_conclusion_documentation(search_intent, top_k=2)`

Retrieves the most relevant sections from `Results.md` for a conclusion node.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `search_intent` | string | — | Free-text description of the diagnosed problem. Use the value from the conclusion node's `documentation.search_intent` field. |
| `top_k` | int | `2` | Maximum number of sections to return. |

**How it works:** Tokenises `search_intent`, scores every `##` and `###` section of `Results.md` by keyword overlap, and returns the top_k matches. `##` (topic-level) sections are preferred over `###` on equal scores, so the LLM always gets the broad explanation alongside the detail.

**When to call:** When the graph traversal reaches a `conclusion` node.

---

## Generic DataFrame tools

These tools work on **any CSV file**. Column names for files exported from the SDDP dashboard are already available from `get_avaliable_results` — no need to discover them separately.

---

### `df_get_head(file_path, n=5)`

Returns the first N rows as a formatted table, plus shape info.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `n` | int | `5` | Number of rows to return. |

**Use for:** Understanding the actual data format, scale, and value conventions of an unfamiliar file.

---

### `df_get_summary(file_path, operations_json)`

Computes statistics across selected columns in a single call.

| Parameter | Type | Description |
|---|---|---|
| `file_path` | string | Absolute path to the CSV file. |
| `operations_json` | string | JSON object mapping column names to lists of operations. Supported: `"mean"`, `"std"`, `"min"`, `"max"`. |

**Example:**
```json
{"Zinf": ["mean", "min", "max"], "Zsup": ["mean"]}
```

**Returns:** Per-column, per-operation results. Unknown columns and unsupported operations return error strings.

---

### `df_analyze_bounds(file_path, target_col, lower_bound_col, upper_bound_col, reference_val_col, iteration_col, lock_threshold)`

Tests whether a tracked value sits inside a `[low, high]` band and measures accuracy relative to a reference value over iterations.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_col` | string | — | Column being tracked (e.g. `"Zinf"`). |
| `lower_bound_col` | string | — | Column with the lower band edge. |
| `upper_bound_col` | string | — | Column with the upper band edge. |
| `reference_val_col` | string | — | Column with the reference value. |
| `iteration_col` | string | `""` | Column identifying the iteration number (optional label). |
| `lock_threshold` | float | `0.005` | Gap-change % below which the run is considered "locked". |

**Returns:** `metadata`, `bounds_status` (converged, interval), `reference_accuracy` (trend), `stability` (is_locked).

**Use for:** SDDP Zinf-vs-tolerance-band convergence check.

---

### `df_analyze_composition(file_path, target_cost_col, all_cost_cols_json, label_col, min_threshold, max_threshold)`

Computes what share of a group total comes from one column; flags rows outside percentage thresholds.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_cost_col` | string | — | The column whose share to analyse. |
| `all_cost_cols_json` | string | — | JSON array of ALL columns that sum to the total. Must include `target_cost_col`. Example: `'["Operating_Cost", "Penalty_Cost"]'` |
| `label_col` | string | — | Column used to label rows in the output. |
| `min_threshold` | float | `0.0` | Flag rows where share < this value (%). Pass `0` to disable. |
| `max_threshold` | float | `0.0` | Flag rows where share > this value (%). Pass `0` to disable. |

**Returns:** `global_summary`, `composition_metrics` (target_share_of_total_pct), `criticality_report`.

**Use for:** Verifying the 80% operating-cost rule, detecting penalty domination.

---

### `df_analyze_stagnation(file_path, target_col, window_size, cv_threshold, slope_threshold)`

Detects whether a series has stopped improving over the most recent N rows.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_col` | string | — | Column to monitor (e.g. `"Zinf"`). |
| `window_size` | int | `5` | Number of most-recent rows to inspect. |
| `cv_threshold` | float | `1.0` | Max CV (%) in the window to be called "stable". |
| `slope_threshold` | float | `0.01` | Max `|net_change / total_range|` to be called "flat". |

**Returns:** `overall_stats`, `recent_window`, `stagnation_results` (`status: "Stagnated" | "Active"`).

**Use for:** Detecting locked Zinf, cut-count plateaus.

---

### `df_analyze_heatmap(file_path, mode, label_col, value_cols_json, threshold, top_n)`

Analyses a stage × scenario matrix and identifies critical cells.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `mode` | string | `"solver_status"` | `"solver_status"` (integer codes 0–3) or `"threshold"` (continuous values). |
| `label_col` | string | `""` | Row-label column (e.g. `"Stage"`). |
| `value_cols_json` | string | `""` | JSON array of scenario column names. Leave empty to auto-detect. |
| `threshold` | float | `0.0` | Criticality cutoff for `"threshold"` mode. |
| `top_n` | int | `10` | Max entries in ranked lists. |

**Returns:** `summary` (critical_cells, status distribution), `top_critical_scenarios`, `top_critical_stages`.

**Use for:** MIP solver status heatmap, penalty-participation heatmap.

---

### `df_filter_above_threshold(file_path, threshold, label_col, value_cols_json, direction, top_n)`

Identifies which columns exceed (or fall below) a threshold at each stage.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `threshold` | float | — | Numeric boundary value. |
| `label_col` | string | `""` | Row-label column (e.g. `"Stage"`). |
| `value_cols_json` | string | `""` | JSON array of columns to check. Leave empty to auto-detect. |
| `direction` | string | `"above"` | `"above"` (flag > threshold) or `"below"` (flag < threshold). |
| `top_n` | int | `10` | Max entries in ranked output. |

**Returns:** `summary`, `top_exceeding_columns` (ranked by frequency), `by_stage` (per-stage detail).

**Use for:** Identifying which agents/penalties drive exceedances per stage.

---

### `df_cross_correlation(file_path_a, file_path_b, col_a, col_b, join_on, output_csv_path)`

Correlates one column from file A with one column from file B.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path_a` | string | — | Absolute path to the first CSV (x variable). |
| `file_path_b` | string | — | Absolute path to the second CSV (y variable). |
| `col_a` | string | — | Column in file A (independent variable). |
| `col_b` | string | — | Column in file B (dependent variable). |
| `join_on` | string | `""` | Shared key column to merge on. Leave empty to align by row index. |
| `output_csv_path` | string | `""` | If provided, saves a scatter-plot CSV with the regression line. |

**Returns:** `alignment`, `correlation_metrics` (Pearson r, R², strength), `sensitivity` (slope, elasticity), `export`.

**Use for:** ENA-vs-cost correlation, any two-file cross-series analysis.

---

## Output format

All df_* tools return plain-text structured as:

```
=== TOOL NAME — filename.csv ===

[section_name]
  key: value
  [sub_section]
    key: value
  critical_scenarios:
    - label: Stage 3
      percentage: 92.1000
      status: Above Max
```

---

## Removed tools

| Tool | Removed in | Replaced by |
|---|---|---|
| `df_get_columns` | 2026-04-16 | Column names now included in `get_avaliable_results` output |
| `df_get_size` | 2026-04-16 | Row count now included in `get_avaliable_results` output |
| `get_decision_tree` | 2026-04-16 | `get_diagnostic_graph` (loads `decision_graph.json`) |

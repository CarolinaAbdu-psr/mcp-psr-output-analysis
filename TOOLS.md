# MCP Tool Reference

This document describes every tool exposed by the **PSR Output Analysis** MCP server.

Tools are split into two groups:

- **Domain tools** — high-level diagnostics that know the SDDP file schema and embed knowledge-base entries.
- **Generic DataFrame tools** — column-agnostic tools that work on any CSV file.

---

## Setup

### `get_avaliable_results(study_path)`

Sets the active results folder and returns a list of all CSV files inside it.

| Parameter | Type | Description |
|---|---|---|
| `study_path` | string | Absolute path to the SDDP case folder (the one that contains a `results/` sub-folder). |

**When to call:** Always call this first. It initialises `RESULTS_FOLDER` which all domain tools depend on.

**Returns:** List of CSV filenames found in `{study_path}/results/`.


---

## Generic DataFrame Tools

These tools work on **any CSV file** and are completely column-agnostic.
They are the building blocks the LLM uses when it needs raw metrics from a file
before writing a skill or when the domain tools do not cover the required analysis.

**Typical workflow:**
1. `df_get_columns` — discover available columns.
2. `df_get_summary` — get basic stats to understand scale and range.
3. One of the analysis tools (`df_analyze_bounds`, `df_analyze_composition`, etc.) for deeper insight.

---

### `df_get_columns(file_path)`

Returns the list of all column names in a CSV file.

| Parameter | Type | Description |
|---|---|---|
| `file_path` | string | Absolute path to the CSV file. |

**When to call:** First tool to call on any unfamiliar file. Its output tells you which column names to pass to the other tools.

**Returns:** Numbered list of column names.

---

### `df_get_summary(file_path, operations_json)`

Computes multiple statistics across multiple columns in a single call.

| Parameter | Type | Description |
|---|---|---|
| `file_path` | string | Absolute path to the CSV file. |
| `operations_json` | string | JSON object mapping column names to lists of operations. Supported: `"mean"`, `"std"`, `"min"`, `"max"`. |

**Example `operations_json`:**
```json
{"Forward": ["mean", "std"], "Backward": ["mean", "max"]}
```

**Returns:** Per-column, per-operation results.  Unknown columns and unsupported operations return error strings instead of raising exceptions.

---

### `df_analyze_bounds(file_path, target_col, lower_bound_col, upper_bound_col, reference_val_col, iteration_col, lock_threshold)`

Tests whether a tracked value sits inside a `[low, high]` band and measures its accuracy relative to a reference value over time.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_col` | string | — | Column being tracked (e.g. `"Zinf"`). |
| `lower_bound_col` | string | — | Column with the lower band edge. |
| `upper_bound_col` | string | — | Column with the upper band edge. |
| `reference_val_col` | string | — | Column with the reference / expected value. |
| `iteration_col` | string | `""` | Column identifying the iteration number (optional label). |
| `lock_threshold` | float | `0.005` | Gap-change % below which the run is considered "locked". |

**Returns:** Four sections — `metadata`, `bounds_status`, `reference_accuracy`, `stability`.

**Use for:** SDDP Zinf-vs-tolerance-band convergence, simulation-vs-policy validation, or any iterative convergence check.

---

### `df_analyze_composition(file_path, target_cost_col, all_cost_cols_json, label_col, min_threshold, max_threshold)`

Computes what share of a group total comes from one specific column; flags rows that breach percentage thresholds.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_cost_col` | string | — | The column whose share to analyse (e.g. `"Costo: Total operativo"`). |
| `all_cost_cols_json` | string | — | JSON array of ALL columns that sum to the row total. Must include `target_cost_col`. Example: `'["Costo: Total operativo", "Pen: X"]'` |
| `label_col` | string | — | Column used to label rows in the output (e.g. `"Etapas"`). |
| `min_threshold` | float | `0.0` | Flag rows where share < this value (%). Pass `0` to disable. |
| `max_threshold` | float | `0.0` | Flag rows where share > this value (%). Pass `0` to disable. |

**Returns:** `global_summary`, `composition_metrics`, `criticality_report`.

**Use for:** Verifying the 80% operating-cost rule, checking if any cost category is out of range, any proportion analysis.

---

### `df_analyze_stagnation(file_path, target_col, window_size, cv_threshold, slope_threshold)`

Detects whether a series has stopped improving over the most recent N rows, using CV and normalised slope.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path` | string | — | Absolute path to the CSV file. |
| `target_col` | string | — | Column to monitor (e.g. `"Optimality"`). |
| `window_size` | int | `5` | Number of most-recent rows to inspect. |
| `cv_threshold` | float | `1.0` | Max CV (%) in the window to be called "stable". |
| `slope_threshold` | float | `0.01` | Max `|net_change / total_range|` to be called "flat". |

**Returns:** `overall_stats`, `recent_window`, `stagnation_results` (`"Stagnated"` or `"Active"`).

**Use for:** Cut-count plateaus, locked gap detection, any iterative metric expected to keep changing.

---

### `df_cross_correlation(file_path_a, file_path_b, col_a, col_b, join_on, output_csv_path)`

Correlates one column from file A with one column from file B using Pearson r, R², and OLS elasticity.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file_path_a` | string | — | Absolute path to the first CSV (x variable). |
| `file_path_b` | string | — | Absolute path to the second CSV (y variable). |
| `col_a` | string | — | Column name in file A (independent variable). |
| `col_b` | string | — | Column name in file B (dependent variable). |
| `join_on` | string | `""` | Shared key column to merge on (e.g. `"Etapas"`). Leave empty to align by row index. |
| `output_csv_path` | string | `""` | If provided, saves a scatter-plot CSV with the regression line to this path. Leave empty to skip. |

**Returns:** `alignment`, `correlation_metrics` (Pearson r, R², strength label), `sensitivity` (slope, elasticity, interpretation), `export`.

**Use for:** ENA-vs-cost spread correlation, any two-file cross-series analysis.

---

## Output format

All generic DataFrame tools return plain-text reports structured as:

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

This format is designed for direct LLM consumption — no JSON parsing required.

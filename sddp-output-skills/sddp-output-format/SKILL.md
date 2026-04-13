---
name: sddp-output-format
description: >
  Formatting rules that apply to every SDDP analysis response produced by
  this MCP server. Governs language matching (answer in the user's language),
  response structure (lead with verdict), Markdown tables, ASCII sparklines,
  knowledge-base citation format with reference links, and severity labels
  (OK / Warning / Critical). Always apply these rules before writing any
  analysis response. Also defines the standard file exploration sequence
  (df_get_columns + df_get_head) that must precede any analysis tool call.
version: 1.0.0
---

# SDDP Output Format Rules

Apply these rules to **every** SDDP analysis response, regardless of topic.
They are not negotiable and must be followed even when the skill prompt for a
specific analysis does not repeat them.

---

## 1. Language Matching

- Detect the language of the user's question.
- Write the **entire response** in that language — section headers, labels,
  diagnostic verdicts, explanations, and table column names.
- Exception: tool names, file names, formula symbols, and proper nouns
  (e.g., "SDDP", "Zinf", "Zsup") stay in their canonical form.
- If unsure, default to the language of the most recent user message.

---

## 2. Response Structure

Lead with the **conclusion** (verdict + severity), then support with data.
Never bury the diagnosis at the end of a long data dump.

Recommended section order:

```
## [Topic] — Verdict: [OK / Warning / Critical]

[2–4 sentence summary of what was found and what it means.]

### Data
[Table or bullet list with key metrics.]

### Diagnosis
[Detailed explanation, referencing knowledge base entries.]

### Recommendations
[Actionable next steps, if any issues were found.]
```

---

## 3. Tables

Use Markdown tables for any per-stage, per-iteration, or per-scenario data.
Keep tables to the most relevant columns — drop columns that are all zeros or
not discussed in the diagnosis.

Example format:

| Stage | Avg Cost (k$) | P10 (k$) | P90 (k$) | Spread |
|------:|-------------:|---------:|---------:|-------:|
| 1     | 1 234.5      | 890.2    | 1 890.4  | 112 %  |

---

## 4. Visual Summaries

When presenting a time series or iteration evolution, describe the trend
explicitly in words **and** provide a compact ASCII sparkline if the series
has 5–30 points, or a representative sample table otherwise.

Sparkline convention (use for convergence gap, cost evolution, etc.):

```
Iteration:  1    5   10   15   20
Zinf:       ▁▂▃▄▅▆▇█  (rising toward Zsup)
Gap %:      45 → 12 → 3.1 → 0.8 → 0.2
```

If chart_* tools are available, call them to produce visual graphs in addition
to the text summary — never instead of it.

---

## 5. Knowledge Base Citations

Whenever you state a diagnosis, recommendation, or threshold (e.g., "operating
cost should be ≥ 80% of total cost"), you **must** cite the source from the
SDDP knowledge base.

Citation format (inline, at the end of the relevant sentence or paragraph):

```
[Knowledge: <entry title> — <reference title> (<url>)]
```

Example:

> Significant penalty costs indicate constraint violations and artificial costs
> that do not reflect operational reality. The 80% operating-cost guideline
> applies here.
> [Knowledge: Total Operating Cost Portions — SDDP User Manual Chapter 4 (https://psr-inc.com/software/sddp/)]

Rules:
- Fetch knowledge entries with `get_sddp_knowledge()` before writing the
  diagnosis section. Use `topics` or `problems` parameters to target only
  what you need — do not fetch the entire knowledge base.
- If a knowledge entry has a `references` list, include at least one
  reference title and URL in the citation.
- If no knowledge entry exists for a finding, note it explicitly so the
  knowledge base can be extended later.

---

## 6. Severity Labels

Use these consistent labels throughout the response:

| Label    | Meaning                                           |
|----------|---------------------------------------------------|
| OK       | Metric is within acceptable range, no action needed |
| Warning  | Metric is borderline; monitor or investigate      |
| Critical | Metric is out of range; results may be unreliable |

---

## 8. Standard File Exploration Sequence

Before calling any analysis tool on a file you haven't seen before, always run
these two tools first:

```
df_get_columns(file_path=<csv>)        # discover column names and count
df_get_head(file_path=<csv>, n=5)      # see actual data format and scale
```

For small files (convergence, execution time), also try:

```
df_get_size(file_path=<csv>, max_cells=500)   # inline the full content if it fits
```

This avoids parameter mistakes (wrong column names, wrong scale assumptions)
and reduces unnecessary back-and-forth tool calls.

---

## 7. What NOT to Include

- Do not repeat the raw tool output verbatim — summarise it.
- Do not list columns or file names that are not relevant to the analysis.
- Do not explain how the tools work unless the user asked.
- Do not add caveats about uncertainty unless the data actually shows it.

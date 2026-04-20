"""Helpers for working with the CSV results catalog (_index.json)."""
from __future__ import annotations


def build_catalog_summary(csv_catalog: dict[str, dict], tool_name: str = "") -> str:
    """
    Return a compact text representation of the CSV catalog for inclusion in LLM prompts.

    When tool_name is provided, files are annotated with a relevance hint based on
    chart_type (band/line files → convergence tools; bar files → cost/penalty tools;
    heatmap files → MIP status tools).
    """
    if not csv_catalog:
        return "(catalog empty — call initialize first)"

    relevance_hints: dict[str, list[str]] = {
        "df_analyze_bounds":        ["band", "line"],
        "df_analyze_stagnation":    ["line", "band"],
        "df_analyze_composition":   ["bar", "stacked"],
        "df_filter_above_threshold": ["bar", "stacked"],
        "df_analyze_heatmap":       ["heatmap"],
        "df_cross_correlation":     ["line", "bar"],
        "df_get_head":              [],
        "df_get_summary":           [],
    }
    preferred_types = relevance_hints.get(tool_name, [])

    lines: list[str] = []
    for filename, meta in csv_catalog.items():
        chart_type = meta.get("chart_type", "?")
        title = meta.get("title", "")
        series = meta.get("series", [])
        rows = meta.get("rows", "?")
        hint = " ← LIKELY MATCH" if (preferred_types and chart_type in preferred_types) else ""
        series_str = ", ".join(f'"{s}"' for s in series) if series else "—"
        lines.append(
            f"  {filename}{hint}\n"
            f"    chart_type={chart_type!r}  title={title!r}  rows={rows}\n"
            f"    columns: {series_str}"
        )

    return "\n".join(lines)


def find_file_for_tool(csv_catalog: dict[str, dict], tool_name: str) -> str | None:
    """
    Heuristic: return the filename most likely needed for a given tool.
    Returns None when the catalog is empty or no match is found.
    """
    type_priority: dict[str, list[str]] = {
        "df_analyze_bounds":        ["band", "line"],
        "df_analyze_stagnation":    ["line", "band"],
        "df_analyze_composition":   ["bar", "stacked"],
        "df_filter_above_threshold": ["bar", "stacked"],
        "df_analyze_heatmap":       ["heatmap"],
    }
    preferred = type_priority.get(tool_name, [])
    for ptype in preferred:
        for fname, meta in csv_catalog.items():
            if meta.get("chart_type") == ptype:
                return fname
    return None

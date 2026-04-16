#!/usr/bin/env python3
"""MCP server for PSR Output Analysis."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import psr.factory

from mcp.server.fastmcp import FastMCP

from .case_information import extract_case_information as _extract_case_info
from .common import read_csv, read_csv_path
from .dataframe_functions import (
    get_dataframe_head,
    get_data_summary,
    analyze_bounds_and_reference,
    analyze_composition,
    analyze_stagnation,
    analyze_cross_correlation,
    analyze_heatmap,
    filter_by_threshold,
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"   # legacy — may not exist
_SKILLS_DIR   = _PACKAGE_ROOT / "skills"

# Import HTML-to-CSV extractor from the project root
sys.path.insert(0, str(_PACKAGE_ROOT))
try:
    from sddp_html_to_csv import export_to_csv as _export_html_to_csv  # type: ignore
except ImportError:
    _export_html_to_csv = None  # type: ignore

RESULTS_FOLDER: Path = Path(".")

# ---------------------------------------------------------------------------
# Server definition
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "PSR Output Analysis",
    instructions=(
        "You are an SDDP output analysis assistant. "
        "Analyse simulation results and explain them clearly. "
        "ALWAYS respond in the same language the user used in their question — "
        "tools and documentation are in English but your answers must match the user's language. "

        "## Standard workflow "
        "0. extract_html_results(study_path) — parse the SDDP dashboard HTML and export all "
        "   charts as CSV files into the results/ folder. Call ONCE per session before anything else. "
        "0b. get_case_information(study_path) — extract case metadata (stages, horizon, series, "
        "    model version, dimensions) from the HTML. Call alongside step 0 to provide context. "
        "1. get_avaliable_results(study_path) — set the results folder; returns all CSV files "
        "   with their chart type, units, row count and exact column names from _index.json. "
        "2. get_graph_entry_point(problem_type) — resolve the entry node for the problem "
        "   ('problema_convergencia', 'deslocamento_custo', or 'problema_simulacao'). "
        "   Returns root node + immediate children only (~200 tokens). "
        "2b. get_graph_node(node_id) — navigate ONE node at a time. Call after evaluating "
        "    each analysis node's tools[] output against its expected_state. Returns current "
        "    node details + outgoing edges with child previews. Repeat until a conclusion node "
        "    is reached. On conclusion nodes: call get_conclusion_documentation(search_intent). "
        "3. df_* tools — execute analysis as instructed by each graph node. "
        "4. Get conclusiion_documentation to use as knowledge to explain to the user why did't work"

        "## Rules "
        "- Call extract_html_results + get_case_information before get_avaliable_results. "
        "- Always call get_avaliable_results before any df_* analysis tool. "
        "- Column names for every dashboard CSV are already in get_avaliable_results output — "
        "  do NOT call df_get_columns for files listed there. "
        "- Traverse the decision graph ONE node at a time via get_graph_node; "
        "  do not call get_diagnostic_graph (deprecated, loads full ~5500-token graph). "
        "- Follow graph edges strictly by priority order; do not skip nodes. "
        "- Respond in the user's language — not in English unless the user wrote in English. "
        "- Lead with conclusions; use tables for per-stage data. "
        "- See the sddp_diagnose prompt for detailed step-by-step guidance. "
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter (--- ... ---) from the start of the text."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    return text[end + 4:].lstrip("\n")


def _load_skill(folder: str) -> str:
    path = _SKILLS_DIR / folder / "SKILL.md"
    if not path.exists():
        return f"[Skill not found: {folder}]"
    return _strip_frontmatter(path.read_text(encoding="utf-8"))


def _format_result(result: dict, title: str) -> str:
    """
    Render a nested result dict as indented plain text with a title header.
    Dicts become sections, scalars become key: value lines.
    """
    lines = [f"=== {title} ===", ""]

    def _render(d: dict, indent: int = 0) -> None:
        pad = "  " * indent
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{pad}[{k}]")
                _render(v, indent + 1)
            elif isinstance(v, list):
                lines.append(f"{pad}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        lines.append(f"{pad}  -")
                        _render(item, indent + 2)
                    else:
                        lines.append(f"{pad}  - {item}")
            elif isinstance(v, float):
                lines.append(f"{pad}{k}: {v:,.4f}")
            else:
                lines.append(f"{pad}{k}: {v}")

    _render(result)
    return "\n".join(lines)


def _load_csv(file_path: str) -> tuple[object, str | None]:
    """Return (df, error_str). error_str is None on success."""
    try:
        return read_csv_path(file_path), None
    except FileNotFoundError:
        return None, f"[Error] File not found: {file_path}"
    except Exception as exc:
        return None, f"[Error] Could not read file: {exc}"
    

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

@mcp.tool()
def extract_html_results(study_path: str) -> list[str]:
    """
    Parse the SDDP dashboard HTML file found in the study folder and export
    every chart as a CSV into {study_path}/results/.

    This is STEP 0 of every analysis session. Call it once before
    get_avaliable_results so that the results folder is populated.

    Args:
        study_path: Absolute path to the SDDP case folder.  The tool searches
                    for *.html files directly inside this folder.

    Returns:
        List of CSV file paths created, or error strings for any failures.
    """
    if _export_html_to_csv is None:
        return ["[Error] sddp_html_to_csv module not available. Check installation."]

    study = Path(study_path)
    html_files = list(study.glob("*.html"))
    if not html_files:
        return ["[Error] No HTML file found in the study folder. Expected an SDDP dashboard .html file."]

    output_dir = study / "results"
    saved: list[str] = []
    for html_file in html_files:
        try:
            files = _export_html_to_csv(str(html_file), output_dir=str(output_dir), verbose=False)
            saved.extend(files)
        except Exception as exc:
            saved.append(f"[Error] {html_file.name}: {exc}")

    return saved


@mcp.tool()
def get_avaliable_results(study_path: str) -> str:
    """
    Set the active results folder and return the catalogue of available result files.

    Reads the _index.json manifest written by extract_html_results, which contains
    for each file: chart type, title, X/Y units, row count, and the exact column
    names (series).  This single call replaces the need for df_get_columns on any
    file that was exported from the SDDP dashboard.

    If the manifest is absent (extract_html_results was not called yet), returns
    a plain filename list as a fallback.

    Args:
        study_path: Absolute path to the SDDP case folder.
    """
    global RESULTS_FOLDER
    RESULTS_FOLDER = Path(os.path.join(study_path, "results"))

    index_path = RESULTS_FOLDER / "_index.json"
    if not index_path.exists():
        # Fallback: manifest not yet generated
        files = sorted(f.name for f in RESULTS_FOLDER.iterdir() if f.is_file())
        header = [
            f"=== AVAILABLE RESULTS — {RESULTS_FOLDER.name} ({len(files)} files) ===",
            "  [!] _index.json not found. Call extract_html_results first for full metadata.",
            "",
        ]
        return "\n".join(header + [f"  {f}" for f in files])

    with open(index_path, encoding="utf-8") as f:
        index = json.load(f)

    lines = [
        f"=== AVAILABLE RESULTS — {RESULTS_FOLDER.name} ({len(index)} files) ===",
        "",
    ]
    for e in index:
        series_str = ", ".join(e["series"]) if e["series"] else "—"
        lines += [
            f"  [{e['chart_type']}]  {e['filename']}",
            f"    Title   : {e['title']}",
            f"    X unit  : {e['x_unit'] or '—'}   Y unit: {e['y_unit'] or '—'}   Rows: {e['rows']}",
            f"    Columns : {series_str}",
            "",
        ]
    return "\n".join(lines)


@mcp.tool()
def get_case_information(study_path: str) -> str:
    """
    Extract structured case metadata from the SDDP dashboard HTML.

    Parses the "Information" tab (Información / Information / Informação) and
    returns case summary, model/environment info, run parameters, system
    dimensions, and non-convexity counts.

    Call this once per session — before or alongside get_avaliable_results —
    to give the analysis context (stages, series, horizon, model version, etc.).

    Args:
        study_path: Absolute path to the SDDP case folder that contains the
                    dashboard .html file.

    Returns:
        Formatted text block with all case metadata sections.
    """
    study = Path(study_path)
    html_files = list(study.glob("*.html"))
    if not html_files:
        return "[Error] No HTML file found in the study folder."

    # Use first HTML found (there is normally only one)
    data = _extract_case_info(str(html_files[0]))

    if "error" in data:
        return f"[Error] {data['error']}"

    lines: list[str] = [
        f"=== CASE INFORMATION — {html_files[0].name} ===",
        "",
    ]

    section_order = [
        ("case_summary",    "Case Summary"),
        ("model_info",      "Model & Environment"),
        ("case_title",      "Case Title"),
        ("run_parameters",  "Run Parameters"),
        ("dimensions",      "System Dimensions"),
        ("non_convexities", "Non-Convexities"),
    ]

    for key, label in section_order:
        value = data.get(key)
        if value is None:
            continue
        lines.append(f"## {label}")
        if isinstance(value, str):
            lines.append(f"  {value}")
        elif isinstance(value, dict):
            col_w = max((len(k) for k in value), default=0)
            for k, v in value.items():
                lines.append(f"  {k.ljust(col_w)}  {v}")
        lines.append("")

    # Any extra keys not in the standard list
    known = {k for k, _ in section_order} | {"_tab_id"}
    for key, value in data.items():
        if key not in known:
            label = key.replace("_", " ").title()
            lines.append(f"## {label}")
            if isinstance(value, dict):
                col_w = max((len(k) for k in value), default=0)
                for k, v in value.items():
                    lines.append(f"  {k.ljust(col_w)}  {v}")
            else:
                lines.append(f"  {value}")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Workflow documentation & decision trees
# ---------------------------------------------------------------------------

_DOCS_DIR    = _PACKAGE_ROOT / "docs"
_TREES_DIR   = _PACKAGE_ROOT / "decision-trees"
_RESULTS_DOC = _PACKAGE_ROOT / "Results.md"

_VALID_DOCS = {
    "index", "convergence", "simulation", "violations",
    "marginal-costs", "execution-time", "csv-schema",
}


def _parse_results_sections(text: str) -> list[dict]:
    """
    Split Results.md into sections by ### headings.

    Returns a list of dicts with keys:
        heading  – the ### heading text (without #)
        content  – full text of the section including the heading line
        level    – heading level (2 for ##, 3 for ###)
    """
    import re
    sections: list[dict] = []
    pattern = re.compile(r'^(#{2,3})\s+(.+)$', re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        level   = len(m.group(1))
        heading = m.group(2).strip()
        start   = m.start()
        end     = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append({
            "heading": heading,
            "content": text[start:end].strip(),
            "level":   level,
        })
    return sections


def _score_section(section: dict, query_tokens: set[str]) -> int:
    """Count how many query tokens appear in the section heading + content."""
    haystack = (section["heading"] + " " + section["content"]).lower()
    return sum(1 for t in query_tokens if t in haystack)


def _search_results_doc(search_intent: str, top_k: int = 2) -> list[dict]:
    """
    Return the top_k Results.md sections most relevant to search_intent.

    Preference is given to ## sections (level 2) when they score equally,
    so the LLM receives the broadest contextual explanation first.
    """
    if not _RESULTS_DOC.exists():
        return []

    text     = _RESULTS_DOC.read_text(encoding="utf-8")
    sections = _parse_results_sections(text)

    import re
    stop = {"de", "do", "da", "dos", "das", "e", "o", "a", "os", "as",
            "em", "no", "na", "por", "para", "com", "que", "se", "um",
            "uma", "the", "of", "in", "and", "to", "a", "is", "for"}
    tokens = {
        t for t in re.split(r'\W+', search_intent.lower())
        if len(t) > 2 and t not in stop
    }

    scored = [
        (s, _score_section(s, tokens))
        for s in sections
    ]
    # Sort: higher score first; among ties prefer broader ## sections
    scored.sort(key=lambda x: (x[1], 1 if x[0]["level"] == 2 else 0), reverse=True)

    return [s for s, score in scored[:top_k] if score > 0]



@mcp.tool()
def get_diagnostic_graph() -> str:
    """
    Deprecated: loads the full ~5500-token graph at once.

    Prefer get_graph_entry_point + get_graph_node for incremental traversal
    (~200-400 tokens per step). Kept for backwards compatibility only.

    Returns the full graph — entry points, nodes, and edges — formatted for
    direct traversal.
    """
    path = _TREES_DIR / "decision_graph.json"
    if not path.exists():
        return "[Error] decision_graph.json not found."

    graph = json.loads(path.read_text(encoding="utf-8"))

    # Index nodes by id for fast lookup
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}

    # Build adjacency list sorted by priority
    adjacency: dict[str, list[dict]] = {}
    for edge in graph.get("edges", []):
        src = edge["source"]
        adjacency.setdefault(src, []).append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda e: e.get("priority", 99))

    lines = [
        "=== DIAGNOSTIC GRAPH ===",
        "",
        "## Entry points",
    ]
    for problem, node_id in graph.get("entry_points", {}).items():
        lines.append(f"  {problem}  →  {node_id}")
    lines.append("")

    lines.append("## Nodes")
    for node in graph.get("nodes", []):
        nid   = node["id"]
        ntype = node.get("type", "?")
        label = node.get("label", "")
        lines.append(f"\n[{nid}]  type={ntype}")
        lines.append(f"  Label   : {label}")
        lines.append(f"  Purpose : {node.get('purpose', '')}")

        content = node.get("content", {})
        if content.get("description"):
            lines.append(f"  Desc    : {content['description']}")
        if content.get("expected_state"):
            lines.append(f"  Expect  : {content['expected_state']}")

        tools = node.get("tools", [])
        if tools:
            lines.append(f"  Tools   :")
            for t in tools:
                params_str = ", ".join(f"{k}={v!r}" for k, v in t.get("params", {}).items())
                lines.append(f"    • {t['name']}({params_str})")

        doc = node.get("documentation", {})
        if doc:
            lines.append(f"  Doc search: \"{doc.get('search_intent', '')}\"  top_k={doc.get('top_k', 2)}")

        # Outgoing edges
        out = adjacency.get(nid, [])
        if out:
            lines.append(f"  Next    :")
            for e in out:
                lines.append(f"    {e.get('priority','?')}. → {e['target']}")

    lines += [
        "",
        "## Traversal rules",
        "  1. Execute all tools[] of the current node.",
        "  2. Evaluate results against expected_state.",
        "  3. Follow the lowest-priority edge whose condition is satisfied.",
        "  4. On type=conclusion: call get_conclusion_documentation(search_intent).",
    ]

    return "\n".join(lines)


def _search_nodes_by_query(nodes_by_id: dict, query: str) -> list[tuple[dict, int]]:
    """Keyword search across node labels, purposes, and descriptions."""
    import re
    stop = {"de", "do", "da", "dos", "das", "e", "o", "a", "os", "as",
            "em", "no", "na", "por", "para", "com", "que", "se", "um", "uma",
            "the", "of", "in", "and", "to", "is", "for"}
    tokens = {
        t for t in re.split(r'\W+', query.lower())
        if len(t) > 2 and t not in stop
    }
    results: list[tuple[dict, int]] = []
    for node in nodes_by_id.values():
        haystack = " ".join([
            node.get("label", ""),
            node.get("purpose", ""),
            node.get("content", {}).get("description", ""),
            node.get("content", {}).get("expected_state", ""),
        ]).lower()
        score = sum(1 for t in tokens if t in haystack)
        if score > 0:
            results.append((node, score))
    results.sort(key=lambda x: x[1], reverse=True)
    return results


def _subtree_summary(root_id: str, adjacency: dict, nodes_by_id: dict, depth: int = 2) -> str:
    """Return a compact listing of nodes reachable from root_id up to `depth` levels."""
    lines: list[str] = []

    def _walk(nid: str, level: int) -> None:
        if level > depth:
            return
        node = nodes_by_id.get(nid, {})
        pad  = "  " * level
        ntype = node.get("type", "?")
        label = node.get("label", nid)
        lines.append(f"{pad}{'└─' if level else '●'} [{ntype}] {label}")
        for edge in adjacency.get(nid, []):
            _walk(edge["target"], level + 1)

    _walk(root_id, 0)
    return "\n".join(lines)


def _load_graph() -> tuple[dict, dict, dict]:
    """Load graph JSON and return (graph, nodes_by_id, adjacency)."""
    path = _TREES_DIR / "decision_graph.json"
    if not path.exists():
        return {}, {}, {}
    graph = json.loads(path.read_text(encoding="utf-8"))
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    adjacency: dict[str, list[dict]] = {}
    for edge in graph.get("edges", []):
        adjacency.setdefault(edge["source"], []).append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda e: e.get("priority", 99))
    return graph, nodes_by_id, adjacency


def _format_node_block(node: dict, adjacency: dict, nodes_by_id: dict) -> str:
    """Render a single node + its outgoing edges as a compact text block."""
    nid   = node["id"]
    ntype = node.get("type", "?")
    lines = [
        f"=== NODE: {nid} ===",
        "",
        f"type   : {ntype}",
        f"Label  : {node.get('label', '')}",
        f"Purpose: {node.get('purpose', '')}",
    ]

    content = node.get("content", {})
    if content.get("description"):
        lines.append(f"Desc   : {content['description']}")
    if ntype == "analysis" and content.get("expected_state"):
        lines.append(f"Expect : {content['expected_state']}")

    tools = node.get("tools", [])
    if tools:
        lines.append("")
        lines.append("Tools to call:")
        for i, t in enumerate(tools, 1):
            params_str = ", ".join(f"{k}={v!r}" for k, v in t.get("params", {}).items())
            lines.append(f"  {i}. {t['name']}({params_str})")

    doc = node.get("documentation", {})
    if doc.get("search_intent"):
        lines += [
            "",
            f'Doc search_intent: "{doc["search_intent"]}"',
            f'  → Call: get_conclusion_documentation("{doc["search_intent"]}")',
        ]

    out_edges = adjacency.get(nid, [])
    if out_edges:
        lines += ["", "Next edges (sorted by priority):"]
        for e in out_edges:
            target_id    = e["target"]
            target_node  = nodes_by_id.get(target_id, {})
            target_label = target_node.get("label", target_id)
            target_type  = target_node.get("type", "?")
            snippet_src  = target_node.get("content", {}).get("description", "") or \
                           target_node.get("documentation", {}).get("search_intent", "")
            snippet      = (snippet_src[:150] + "…") if len(snippet_src) > 150 else snippet_src
            lines.append(f"  {e.get('priority', '?')}. → {target_id}  [{target_type}]  {target_label}")
            if snippet:
                lines.append(f'     "{snippet}"')
    else:
        lines += ["", "No outgoing edges — this is a leaf node."]

    return "\n".join(lines)


@mcp.tool()
def get_graph_entry_point(problem_type: str) -> str:
    """
    Return the entry-point node for a problem type, plus its immediate
    outgoing edges with child node previews (~200 tokens).

    Also shows a 2-level subtree summary so you can confirm this is the
    right entry point before traversing.

    If problem_type does not match any registered entry point, the tool
    performs a keyword search across all nodes and returns the best
    candidates — use get_graph_node(node_id) to start from any of them.

    Call this ONCE at the start of graph traversal instead of
    get_diagnostic_graph().  Then use get_graph_node(node_id) to navigate
    one step at a time.

    Args:
        problem_type: One of "problema_convergencia", "deslocamento_custo",
                      "problema_simulacao" — or a free-text description of
                      the problem (used for keyword search if no exact match).
    """
    graph, nodes_by_id, adjacency = _load_graph()
    if not graph:
        return "[Error] decision_graph.json not found."

    entry_points = graph.get("entry_points", {})
    node_id = entry_points.get(problem_type)

    # ── Exact match found ─────────────────────────────────────────────────
    if node_id:
        node = nodes_by_id.get(node_id)
        if not node:
            return f"[Error] Entry node '{node_id}' not found in nodes list."

        subtree = _subtree_summary(node_id, adjacency, nodes_by_id, depth=2)
        lines = [
            f"=== ENTRY POINT: {problem_type} ===",
            "",
            "Subtree covered by this entry point:",
            subtree,
            "",
        ]
        return "\n".join(lines) + "\n" + _format_node_block(node, adjacency, nodes_by_id)

    # ── No exact match — list registered entry points + keyword search ────
    lines = [
        f'[No exact match for "{problem_type}"]',
        "",
        "## Registered entry points",
    ]
    for ep_key, ep_node_id in entry_points.items():
        ep_node = nodes_by_id.get(ep_node_id, {})
        subtree = _subtree_summary(ep_node_id, adjacency, nodes_by_id, depth=2)
        lines += [
            f"",
            f'  problem_type="{ep_key}"',
            f'  Root node   : {ep_node_id}',
            f'  Label       : {ep_node.get("label", "")}',
            f'  Subtree     :',
        ]
        for sub_line in subtree.splitlines():
            lines.append(f"    {sub_line}")

    hits = _search_nodes_by_query(nodes_by_id, problem_type)[:3]
    if hits:
        lines += [
            "",
            f'## Keyword search results for "{problem_type}"',
            "  Use get_graph_node(node_id) to start from any of these:",
        ]
        for hit_node, score in hits:
            lines.append(
                f'  • {hit_node["id"]}  (score={score})  [{hit_node.get("type","?")}]  '
                f'{hit_node.get("label","")}'
            )

    return "\n".join(lines)


@mcp.tool()
def get_graph_node(node_id: str) -> str:
    """
    Return the full details of a single graph node plus its outgoing edges
    with child node previews (~200-400 tokens).

    Call this after evaluating the current node's tools[] output against its
    expected_state to navigate to the next node.  Repeat until a conclusion
    node is reached, then call get_conclusion_documentation(search_intent).

    Args:
        node_id: Exact node id string (e.g. "node_penalidades_altas").
    """
    graph, nodes_by_id, adjacency = _load_graph()
    if not graph:
        return "[Error] decision_graph.json not found."

    node = nodes_by_id.get(node_id)
    if not node:
        valid = ", ".join(nodes_by_id.keys())
        return (
            f'[Error] Node "{node_id}" not found. '
            f"Valid node ids: {valid}"
        )

    return _format_node_block(node, adjacency, nodes_by_id)


@mcp.tool()
def get_conclusion_documentation(search_intent: str, top_k: int = 2) -> str:
    """
    Retrieve the most relevant sections from Results.md for a conclusion node.

    Performs keyword-based similarity matching between search_intent and every
    section of Results.md, returning the top_k best matches.  ## sections
    (broad topics) are preferred over ### sections when scores are equal, so
    the LLM always receives the high-level explanation alongside the detail.

    Call this when the graph traversal reaches a node of type "conclusion",
    passing the node's documentation.search_intent value.

    Args:
        search_intent: Free-text description of the diagnosed problem.
                       Use the exact value from the conclusion node's
                       documentation.search_intent field.
        top_k:         Maximum number of sections to return. Default 2.
    """
    if not _RESULTS_DOC.exists():
        return "[Error] Results.md not found in repository root."

    matches = _search_results_doc(search_intent, top_k)

    if not matches:
        return (
            f"[No match] No section in Results.md matched '{search_intent}'.\n"
            f"Returning full file.\n\n"
            + _RESULTS_DOC.read_text(encoding="utf-8")
        )

    lines = [
        f"=== RESULTS DOCUMENTATION — '{search_intent}' (top {len(matches)}) ===",
        "",
    ]
    for i, section in enumerate(matches, 1):
        level_label = "Topic" if section["level"] == 2 else "Section"
        lines += [
            f"── {level_label} {i}: {section['heading']} ──",
            "",
            section["content"],
            "",
        ]
    return "\n".join(lines)



# ---------------------------------------------------------------------------
# Generic DataFrame tools
# ---------------------------------------------------------------------------

@mcp.tool()
def df_get_head(file_path: str, n: int = 5) -> str:
    """
    Return the first N rows of a CSV as a formatted table, plus shape info.

    Call this alongside df_get_columns to understand not just the column names
    but also the actual data format, scale, and value conventions (e.g. whether
    values are integers, percentages, or timestamps).

    Args:
        file_path: Absolute path to the CSV file.
        n:         Number of rows to return. Default 5.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = get_dataframe_head(df, n)
    n_rows = result["shape"]["rows"]
    n_cols = result["shape"]["columns"]
    cols   = result["columns"]
    rows   = result["sample_rows"]

    # Build a fixed-width table
    col_widths = [
        max(len(str(c)), max((len(str(r.get(c, ""))) for r in rows), default=1))
        for c in cols
    ]

    def _fmt_row(values: list) -> str:
        return "| " + " | ".join(str(v).ljust(w) for v, w in zip(values, col_widths)) + " |"

    sep = "|" + "|".join("-" * (w + 2) for w in col_widths) + "|"

    lines = [
        f"=== FIRST {min(n, n_rows)} ROWS — {Path(file_path).name} ===",
        "",
        f"  Shape: {n_rows} rows × {n_cols} columns",
        "",
        _fmt_row(cols),
        sep,
    ]
    for row in rows:
        lines.append(_fmt_row([row.get(c, "") for c in cols]))

    return "\n".join(lines)


@mcp.tool()
def df_get_summary(file_path: str, operations_json: str) -> str:
    """
    Compute statistics (mean / std / min / max) on selected columns.

    Args:
        file_path:        Absolute path to the CSV file.
        operations_json:  JSON object mapping column names to lists of
                          operations.  Example:
                          '{"Forward": ["mean", "std"], "Backward": ["mean"]}'

    Supported operations: mean, std, min, max.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    try:
        operations_dict = json.loads(operations_json)
    except json.JSONDecodeError as exc:
        return f"[Error] Invalid JSON in operations_json: {exc}"

    result = get_data_summary(df, operations_dict)
    return _format_result(result, f"DATA SUMMARY — {Path(file_path).name}")


@mcp.tool()
def df_analyze_bounds(
    file_path: str,
    target_col: str,
    lower_bound_col: str,
    upper_bound_col: str,
    reference_val_col: str,
    iteration_col: str = "",
    lock_threshold: float = 0.005,
) -> str:
    """
    Check whether a value converges inside a [low, high] band and tracks
    accuracy relative to a reference value over iterations.

    Use for any convergence file where a tracked value should enter a
    tolerance band (e.g. Zinf vs Zsup ± Tol, simulation vs policy band).

    Args:
        file_path:          Absolute path to the CSV file.
        target_col:         Column being tracked (e.g. "Zinf").
        lower_bound_col:    Column with the lower edge of the band.
        upper_bound_col:    Column with the upper edge of the band.
        reference_val_col:  Column with the reference / expected value.
        iteration_col:      Column identifying the iteration number (optional).
        lock_threshold:     Gap-change % below which the run is "locked".
                            Default 0.005.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = analyze_bounds_and_reference(
        df,
        target_col=target_col,
        lower_bound_col=lower_bound_col,
        upper_bound_col=upper_bound_col,
        reference_val_col=reference_val_col,
        iteration_col=iteration_col or None,
        lock_threshold=lock_threshold,
    )
    return _format_result(result, f"BOUNDS & REFERENCE ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_analyze_composition(
    file_path: str,
    target_cost_col: str,
    all_cost_cols_json: str,
    label_col: str,
    min_threshold: float = 0.0,
    max_threshold: float = 0.0,
) -> str:
    """
    Compute the share of one column inside a group total; flag outlier rows.

    Use this to check whether one cost category dominates (or is too small)
    relative to a set of columns that together form the total.

    Args:
        file_path:           Absolute path to the CSV file.
        target_cost_col:     The column whose share to analyse
                             (e.g. "Costo: Total operativo").
        all_cost_cols_json:  JSON array of ALL columns that sum to the row
                             total (must include target_cost_col).
                             Example: '["Costo: Total operativo", "Pen: X"]'
        label_col:           Column that labels rows in the output
                             (e.g. "Etapas").
        min_threshold:       Flag rows where share < this value (%). Pass 0
                             to disable the lower threshold.
        max_threshold:       Flag rows where share > this value (%). Pass 0
                             to disable the upper threshold.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    try:
        all_cost_cols = json.loads(all_cost_cols_json)
    except json.JSONDecodeError as exc:
        return f"[Error] Invalid JSON in all_cost_cols_json: {exc}"

    result = analyze_composition(
        df,
        target_cost_col=target_cost_col,
        all_cost_cols=all_cost_cols,
        label_col=label_col,
        min_threshold=min_threshold if min_threshold != 0.0 else None,
        max_threshold=max_threshold if max_threshold != 0.0 else None,
    )
    return _format_result(result, f"COMPOSITION ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_analyze_stagnation(
    file_path: str,
    target_col: str,
    window_size: int = 5,
    cv_threshold: float = 1.0,
    slope_threshold: float = 0.01,
) -> str:
    """
    Detect whether a column has stopped improving over the most recent N rows.

    Use on any iterative metric expected to keep changing (cut counts, gap %,
    objective values).  Returns overall stats, recent-window stats, and a
    clear "Stagnated / Active" verdict.

    Args:
        file_path:        Absolute path to the CSV file.
        target_col:       Column to monitor (e.g. "Optimality").
        window_size:      Number of most-recent rows to inspect. Default 5.
        cv_threshold:     Max CV (%) for the window to be "stable". Default 1.0.
        slope_threshold:  Max |net_change / total_range| to be "flat".
                          Default 0.01.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    result = analyze_stagnation(
        df,
        target_col=target_col,
        window_size=window_size,
        cv_threshold=cv_threshold,
        slope_threshold=slope_threshold,
    )
    return _format_result(result, f"STAGNATION ANALYSIS — {Path(file_path).name}")


@mcp.tool()
def df_cross_correlation(
    file_path_a: str,
    file_path_b: str,
    col_a: str,
    col_b: str,
    join_on: str = "",
    output_csv_path: str = "",
) -> str:
    """
    Correlate one column from file A with one column from file B.

    Returns Pearson r, R², OLS slope, and elasticity at the mean.
    Optionally exports a scatter-plot CSV with the fitted regression line.

    Use for ENA-vs-cost correlation or any two series from separate files.

    Args:
        file_path_a:      Absolute path to the first CSV (x variable).
        file_path_b:      Absolute path to the second CSV (y variable).
        col_a:            Column name in file A (independent variable).
        col_b:            Column name in file B (dependent variable).
        join_on:          Shared key column to merge on (e.g. "Etapas").
                          Leave empty to align by row index.
        output_csv_path:  If provided, saves a scatter-plot CSV to this path.
                          Leave empty to skip the export.
    """
    df_a, err = _load_csv(file_path_a)
    if err:
        return err
    df_b, err = _load_csv(file_path_b)
    if err:
        return err

    result = analyze_cross_correlation(
        df_a, df_b,
        col_a=col_a,
        col_b=col_b,
        join_on=join_on or None,
        output_csv_path=output_csv_path or None,
    )
    title = (
        f"CROSS-CORRELATION — {Path(file_path_a).name} [{col_a}] "
        f"vs {Path(file_path_b).name} [{col_b}]"
    )
    return _format_result(result, title)


@mcp.tool()
def df_analyze_heatmap(
    file_path: str,
    mode: str = "solver_status",
    label_col: str = "",
    value_cols_json: str = "",
    threshold: float = 0.0,
    top_n: int = 10,
) -> str:
    """
    Analyse a stage × scenario matrix (heatmap) and rank critical cells.

    Two modes:

    **solver_status** — integer codes 0-3 per cell:
        0 = Optimal, 1 = Feasible, 2 = Relaxed, 3 = No Solution.
        Critical = any cell > 0.  Returns the full status distribution plus
        the scenarios and stages with the most non-optimal occurrences.

    **threshold** — continuous values (e.g. penalty-participation %):
        Critical = any cell > threshold.  Returns the scenarios and stages
        with the most exceedances.

    Use for:
    - SDDP MIP solver status heatmap (hourly simulation)
    - Penalty-participation heatmap (% per stage × scenario)

    Args:
        file_path:       Absolute path to the CSV file.
        mode:            "solver_status" (default) or "threshold".
        label_col:       Column that labels rows (e.g. "Stage"). Leave empty
                         to use the row index.
        value_cols_json: JSON array of scenario column names to analyse.
                         Leave empty to auto-detect all numeric columns.
                         Example: '["Scenario 1", "Scenario 2"]'
        threshold:       Criticality cutoff for "threshold" mode. Default 0.0.
        top_n:           Maximum entries in ranked lists. Default 10.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    value_cols: list[str] | None = None
    if value_cols_json.strip():
        try:
            value_cols = json.loads(value_cols_json)
        except json.JSONDecodeError as exc:
            return f"[Error] Invalid JSON in value_cols_json: {exc}"

    result = analyze_heatmap(
        df,
        label_col=label_col or None,
        value_cols=value_cols,
        mode=mode,
        threshold=threshold,
        top_n=top_n,
    )
    title = f"HEATMAP ANALYSIS ({mode.upper()}) — {Path(file_path).name}"
    return _format_result(result, title)


@mcp.tool()
def df_filter_above_threshold(
    file_path: str,
    threshold: float,
    label_col: str = "",
    value_cols_json: str = "",
    direction: str = "above",
    top_n: int = 10,
) -> str:
    """
    Find which columns exceed (or fall below) a threshold at each stage.

    Use for time-varying bar-chart data where rows = stages and columns =
    agents / penalties.  Returns per-stage lists of which agents breached
    the threshold, and ranks agents by how often they breach it overall.

    Args:
        file_path:       Absolute path to the CSV file.
        threshold:       Numeric boundary value.
        label_col:       Row-label column (e.g. "Stage"). Leave empty for
                         row-index labels.
        value_cols_json: JSON array of columns to check. Leave empty to
                         auto-detect all numeric columns.
                         Example: '["Pen: Vertimiento", "Pen: Déficit"]'
        direction:       "above" (default, flag > threshold) or
                         "below" (flag < threshold).
        top_n:           Maximum entries in ranked lists. Default 10.
    """
    df, err = _load_csv(file_path)
    if err:
        return err

    value_cols: list[str] | None = None
    if value_cols_json.strip():
        try:
            value_cols = json.loads(value_cols_json)
        except json.JSONDecodeError as exc:
            return f"[Error] Invalid JSON in value_cols_json: {exc}"

    result = filter_by_threshold(
        df,
        threshold=threshold,
        label_col=label_col or None,
        value_cols=value_cols,
        direction=direction,
        top_n=top_n,
    )
    title = (
        f"THRESHOLD FILTER ({direction.upper()} {threshold}) — {Path(file_path).name}"
    )
    return _format_result(result, title)



# ---------------------------------------------------------------------------
# Prompts (slash commands)
# ---------------------------------------------------------------------------

@mcp.prompt()
def sddp_diagnose(study_path: str, question: str = "") -> str:
    """
    Full SDDP diagnostic workflow: load the step-by-step skill prompt that
    drives convergence, simulation, violation, and marginal-cost analysis.

    The skill instructs the agent to:
      1. Initialize results and extract case metadata
      2. Route the question to the right diagnostic area
      3. Load technical documentation for that area
      4. Load and follow the decision tree
      5. Synthesize a structured diagnosis with data, causes, and recommendations

    Args:
        study_path: Absolute path to the SDDP case folder.
        question:   User's diagnostic question (optional — defaults to full analysis).
    """
    skill = _load_skill("sddp-diagnose")
    parts = [skill, "", "---", f"Case path: `{study_path}`"]
    if question:
        parts.append(f"Question: {question}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()

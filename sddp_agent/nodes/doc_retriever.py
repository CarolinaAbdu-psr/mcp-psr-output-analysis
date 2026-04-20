"""
Documentation retrieval node: search Results.md at conclusion nodes.

Duplicates the search logic from server.py (_parse_results_sections,
_search_results_doc) to avoid importing the FastMCP server module.
"""
from __future__ import annotations

import re
from pathlib import Path

_RESULTS_DOC = Path(__file__).parents[3] / "Results.md"

_STOP_WORDS = {
    "de", "do", "da", "dos", "das", "e", "o", "a", "os", "as",
    "em", "no", "na", "por", "para", "com", "que", "se", "um", "uma",
    "the", "of", "in", "and", "to", "is", "for",
}


def _parse_sections(text: str) -> list[dict]:
    """Split Results.md into sections by ## and ### headings."""
    sections: list[dict] = []
    pattern = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append({"heading": heading, "content": text[start:end].strip(), "level": level})
    return sections


def _score(section: dict, tokens: set[str]) -> int:
    haystack = (section["heading"] + " " + section["content"]).lower()
    return sum(1 for t in tokens if t in haystack)


def search_results_doc(search_intent: str, top_k: int = 2) -> list[dict]:
    """Return the top_k Results.md sections most relevant to search_intent."""
    if not _RESULTS_DOC.exists():
        return []

    text = _RESULTS_DOC.read_text(encoding="utf-8")
    sections = _parse_sections(text)

    tokens = {
        t for t in re.split(r"\W+", search_intent.lower())
        if len(t) > 2 and t not in _STOP_WORDS
    }

    scored = [(s, _score(s, tokens)) for s in sections]
    scored.sort(key=lambda x: (x[1], 1 if x[0]["level"] == 2 else 0), reverse=True)
    return [s for s, score in scored[:top_k] if score > 0]


def retrieve_documentation(state: dict) -> dict:
    """
    Fetch Results.md documentation for the current conclusion node.

    Reads: current_node_id, tool_results, traversal_history
    Writes: conclusion_nodes (appended)
    """
    from ..tools.graph_loader import load_graph  # local import avoids circular

    graph = load_graph()
    node = graph["nodes_by_id"].get(state["current_node_id"])

    if node is None:
        return {"conclusion_nodes": state.get("conclusion_nodes", [])}

    doc_cfg = node.get("documentation", {})
    search_intent = doc_cfg.get("search_intent", node.get("label", ""))
    top_k = doc_cfg.get("top_k", 2)

    matches = search_results_doc(search_intent, top_k)
    doc_content = (
        "\n\n".join(f"### {s['heading']}\n{s['content']}" for s in matches)
        if matches
        else f"[No documentation match for: {search_intent!r}]"
    )

    # Collect tool results that belong to this traversal path
    traversal_set = set(state.get("traversal_history", []))
    branch_results = [
        r for r in state.get("tool_results", [])
        if r.get("node_id") in traversal_set
    ]

    conclusion_entry = {
        "node_id": node["id"],
        "label": node.get("label", ""),
        "search_intent": search_intent,
        "doc_content": doc_content,
        "tool_results": branch_results,
    }

    updated = list(state.get("conclusion_nodes", [])) + [conclusion_entry]
    return {"conclusion_nodes": updated}

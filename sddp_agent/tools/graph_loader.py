"""Load and cache the SDDP decision graph from decision_graph.json."""
from __future__ import annotations

import json
from pathlib import Path

_GRAPH_PATH = Path(__file__).parents[2] / "decision-trees" / "decision_graph.json"
_CACHED: dict | None = None


def load_graph() -> dict:
    """
    Load and cache the decision graph.

    Returns a dict with:
        entry_points  — {problem_type: root_node_id}
        nodes_by_id   — {node_id: node_dict}
        adjacency     — {source_id: [edge_dict, ...]} sorted by priority ascending
        raw           — original JSON object
    """
    global _CACHED
    if _CACHED is not None:
        return _CACHED

    raw = json.loads(_GRAPH_PATH.read_text(encoding="utf-8"))

    nodes_by_id: dict[str, dict] = {n["id"]: n for n in raw["nodes"]}

    adjacency: dict[str, list[dict]] = {}
    for edge in raw["edges"]:
        adjacency.setdefault(edge["source"], []).append(edge)
    for edges in adjacency.values():
        edges.sort(key=lambda e: e.get("priority", 99))

    _CACHED = {
        "entry_points": raw["entry_points"],
        "nodes_by_id": nodes_by_id,
        "adjacency": adjacency,
        "raw": raw,
    }
    return _CACHED


def get_node(node_id: str) -> dict | None:
    return load_graph()["nodes_by_id"].get(node_id)


def get_children(node_id: str) -> list[dict]:
    """Return child nodes ordered by priority (ascending = highest priority first)."""
    graph = load_graph()
    edges = graph["adjacency"].get(node_id, [])
    return [graph["nodes_by_id"][e["target"]] for e in edges if e["target"] in graph["nodes_by_id"]]

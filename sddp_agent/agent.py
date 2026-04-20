"""
LangGraph StateGraph assembly for the SDDP diagnostic agent.

Flow:
  START → initialize → route_problem → verify_entry_point → execute_graph_node ──(loop)──┐
                                                                    │                      │
                                                            (conclusion node)             ┘
                                                                    ↓
                                               retrieve_documentation → synthesize_response → END
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    execute_graph_node,
    initialize,
    retrieve_documentation,
    route_problem,
    synthesize_response,
    verify_entry_point,
)
from .state import AgentState
from .tools.graph_loader import load_graph

_MAX_LOOP_VISITS = 3  # Safety: stop if a node is visited more than this many times


def _after_execute(state: AgentState) -> str:
    """
    Conditional router called after execute_graph_node.

    Returns the name of the next LangGraph node:
      - "retrieve_documentation" when current_node is a conclusion or missing
      - "execute_graph_node"     to keep traversing the decision graph
    """
    current_id: str = state.get("current_node_id", "")

    # Hard error guard
    if state.get("error"):
        return "retrieve_documentation"

    # Loop detection: if we've visited this node too many times, force termination
    history: list[str] = state.get("traversal_history", [])
    if history.count(current_id) >= _MAX_LOOP_VISITS:
        return "retrieve_documentation"

    # Check node type
    graph = load_graph()
    node = graph["nodes_by_id"].get(current_id)
    if node is None or node.get("type") == "conclusion":
        return "retrieve_documentation"

    return "execute_graph_node"


def build_graph(skip_initialize: bool = False) -> object:
    """
    Compile and return the LangGraph StateGraph.

    Args:
        skip_initialize: When True, the graph starts at route_problem instead
                         of initialize. Used by the REPL for subsequent questions
                         when initialization data is already in session memory.
    """
    workflow: StateGraph = StateGraph(AgentState)  # type: ignore[type-arg]

    # Register nodes
    workflow.add_node("initialize", initialize)
    workflow.add_node("route_problem", route_problem)
    workflow.add_node("verify_entry_point", verify_entry_point)
    workflow.add_node("execute_graph_node", execute_graph_node)
    workflow.add_node("retrieve_documentation", retrieve_documentation)
    workflow.add_node("synthesize_response", synthesize_response)

    # Entry point
    if skip_initialize:
        workflow.set_entry_point("route_problem")
    else:
        workflow.set_entry_point("initialize")
        workflow.add_edge("initialize", "route_problem")

    # Fixed edges
    workflow.add_edge("route_problem", "verify_entry_point")
    workflow.add_edge("verify_entry_point", "execute_graph_node")
    workflow.add_edge("retrieve_documentation", "synthesize_response")
    workflow.add_edge("synthesize_response", END)

    # Conditional loop edge
    workflow.add_conditional_edges(
        "execute_graph_node",
        _after_execute,
        {
            "execute_graph_node": "execute_graph_node",
            "retrieve_documentation": "retrieve_documentation",
        },
    )

    return workflow.compile()


# Pre-built graphs (cached at module level)
_GRAPH_FULL: object | None = None
_GRAPH_SKIP_INIT: object | None = None


def get_graph(skip_initialize: bool = False) -> object:
    """Return a cached compiled graph."""
    global _GRAPH_FULL, _GRAPH_SKIP_INIT
    if skip_initialize:
        if _GRAPH_SKIP_INIT is None:
            _GRAPH_SKIP_INIT = build_graph(skip_initialize=True)
        return _GRAPH_SKIP_INIT
    else:
        if _GRAPH_FULL is None:
            _GRAPH_FULL = build_graph(skip_initialize=False)
        return _GRAPH_FULL

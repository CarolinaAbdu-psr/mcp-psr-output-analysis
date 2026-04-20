"""AgentState TypedDict and SessionMemory for the SDDP diagnostic agent."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict):
    # Input
    study_path: str
    user_query: str

    # Initialization outputs (persisted across questions in the same session)
    csv_catalog: dict[str, dict]   # filename → {title, chart_type, series, rows, x_unit, y_unit}
    case_metadata: dict[str, Any]  # from extract_case_information()
    results_dir: str               # absolute path to results/ folder

    # Graph traversal state
    problem_type: str              # "problema_convergencia" | "deslocamento_custo" | "problema_simulacao"
    current_node_id: str           # ID of the node currently being processed
    traversal_history: list[str]   # ordered list of visited node IDs (loop guard)
    tool_results: list[dict]       # [{node_id, results: [{tool_name, params, result}]}]

    # Conclusion accumulator
    conclusion_nodes: list[dict]   # [{node_id, label, doc_content, tool_results}]

    # Multi-turn conversation context
    conversation_history: list[dict]  # [{role, content}]

    # Final output
    final_response: str
    error: str | None


class SessionMemory:
    """Persists initialization data across multiple questions for the same study case."""

    def __init__(self) -> None:
        self.study_path: str = ""
        self.csv_catalog: dict[str, dict] = {}
        self.case_metadata: dict[str, Any] = {}
        self.results_dir: str = ""
        self.conversation_history: list[dict] = []
        self.last_traversal: list[str] = []

    def is_initialized(self) -> bool:
        return bool(self.study_path and self.csv_catalog)

    def matches(self, study_path: str) -> bool:
        return self.study_path == study_path

    def update_from_state(self, state: AgentState) -> None:
        self.csv_catalog = state["csv_catalog"]
        self.case_metadata = state["case_metadata"]
        self.results_dir = state["results_dir"]
        self.last_traversal = state["traversal_history"]

    def add_turn(self, user_msg: str, assistant_msg: str) -> None:
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "assistant", "content": assistant_msg})
        # Keep last 10 turns (20 messages) to avoid token bloat
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

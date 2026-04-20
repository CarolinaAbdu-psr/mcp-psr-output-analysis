"""
SDDP Diagnostic Agent — interactive REPL.

Usage:
    python -m sddp_agent
    python -m sddp_agent --stream

Embed the case path in your message using @:
    > @C:/casos/base O caso convergiu?
    > Why are penalties so high?        ← reuses active session path
    > @C:/outro_caso Any issues?        ← switches case (triggers re-initialization)
    > exit
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import textwrap
from pathlib import Path

# Load .env before anything else
_REPO_ROOT = Path(__file__).parents[1]
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / ".env")
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment

from .agent import get_graph
from .state import AgentState, SessionMemory

_AT_PATH_RE = re.compile(r"@([^\s]+)")

_BANNER = textwrap.dedent("""\
    ╔══════════════════════════════════════════════════════╗
    ║         SDDP Diagnostic Agent  (LangGraph)           ║
    ╠══════════════════════════════════════════════════════╣
    ║  Embed the case path with @:                         ║
    ║    @C:/casos/base Did the case converge?             ║
    ║  Follow-up questions reuse the active case.          ║
    ║  Type  exit  or  quit  to end the session.           ║
    ╚══════════════════════════════════════════════════════╝
""")


def _parse_input(text: str, memory: SessionMemory) -> tuple[str, str | None]:
    """
    Extract @path from user input and return (clean_query, study_path_or_None).
    study_path_or_None is None when the active session path should be reused.
    """
    match = _AT_PATH_RE.search(text)
    if match:
        raw_path = match.group(1).strip("/\\")
        # Re-attach leading slash on Unix; on Windows drive letters are kept as-is
        if not re.match(r"^[A-Za-z]:", raw_path) and not raw_path.startswith("/"):
            # Relative path — resolve against cwd
            raw_path = str(Path.cwd() / raw_path)
        clean_query = _AT_PATH_RE.sub("", text).strip()
        return clean_query, raw_path
    return text.strip(), None


def _build_initial_state(query: str, study_path: str, memory: SessionMemory) -> AgentState:
    return AgentState(
        study_path=study_path,
        user_query=query,
        csv_catalog=memory.csv_catalog,
        case_metadata=memory.case_metadata,
        results_dir=memory.results_dir,
        problem_type="",
        current_node_id="",
        traversal_history=[],
        tool_results=[],
        conclusion_nodes=[],
        conversation_history=list(memory.conversation_history),
        final_response="",
        error=None,
    )


def _run_query(
    query: str,
    study_path: str,
    memory: SessionMemory,
    stream: bool,
) -> str:
    """Run one query through the agent graph and return the final response."""
    is_new_case = not memory.is_initialized() or not memory.matches(study_path)

    if is_new_case:
        print(f"\n[Initializing case: {study_path}]", flush=True)
        memory.study_path = study_path
        memory.csv_catalog = {}
        memory.case_metadata = {}
        memory.results_dir = ""
        graph = get_graph(skip_initialize=False)
    else:
        graph = get_graph(skip_initialize=True)

    initial_state = _build_initial_state(query, study_path, memory)

    if stream:
        final_state: dict = {}
        for chunk in graph.stream(initial_state):
            for node_name, node_state in chunk.items():
                print(f"  [{node_name}]", flush=True)
                final_state.update(node_state)
        response = final_state.get("final_response", "[No response generated]")
    else:
        result = graph.invoke(initial_state)
        response = result.get("final_response", "[No response generated]")

        # Persist initialization data in session memory
        if is_new_case or not memory.is_initialized():
            memory.csv_catalog = result.get("csv_catalog", {})
            memory.case_metadata = result.get("case_metadata", {})
            memory.results_dir = result.get("results_dir", "")

        memory.update_from_state(result)  # type: ignore[arg-type]

    memory.add_turn(query, response)
    return response


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m sddp_agent",
        description="SDDP Diagnostic Agent — interactive session",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Show progress as each graph node completes.",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):#"ANTHROPIC_API_KEY"):
        print(
            "[ERROR] ANTHROPIC_API_KEY is not set.\n"
            "Add it to the .env file at the repo root or export it in your shell.",
            file=sys.stderr,
        )
        sys.exit(1)

    print(_BANNER)

    memory = SessionMemory()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nSession ended.")
            break

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "q"}:
            print("Session ended.")
            break

        query, path_from_input = _parse_input(user_input, memory)

        if path_from_input:
            study_path = path_from_input
        elif memory.study_path:
            study_path = memory.study_path
        else:
            print(
                "Hint: include the case path with @, e.g.:\n"
                "  @C:/casos/base Did the case converge?\n"
            )
            continue

        if not query:
            print("Hint: add a question after the @path.")
            continue

        if not Path(study_path).exists():
            print(f"[ERROR] Path does not exist: {study_path}")
            continue

        try:
            response = _run_query(query, study_path, memory, stream=args.stream)
            print(f"\nAgent:\n{response}\n")
        except Exception as exc:
            print(f"\n[ERROR] {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()

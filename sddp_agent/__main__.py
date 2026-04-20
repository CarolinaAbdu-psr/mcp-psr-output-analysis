"""
SDDP Diagnostic Agent — interactive REPL.

Usage:
    python -m sddp_agent
    python -m sddp_agent --stream
    python -m sddp_agent --debug        ← developer mode: full LLM/tool trace
    python -m sddp_agent --stream --debug

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

# ---------------------------------------------------------------------------
# Parse --debug early (before imports that configure logging)
# ---------------------------------------------------------------------------
_debug_mode = "--debug" in sys.argv

from .utils import setup_logging, get_logger  # noqa: E402 — must be after dotenv
setup_logging(debug=_debug_mode)
_log = get_logger("main")

from .agent import get_graph           # noqa: E402
from .state import AgentState, SessionMemory  # noqa: E402

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


def _parse_input(text: str) -> tuple[str, str | None]:
    """
    Extract @path from user input.
    Returns (clean_query, study_path_or_None).
    """
    match = _AT_PATH_RE.search(text)
    if match:
        raw_path = match.group(1)
        # On Windows, keep drive letters (C:/) as-is; resolve relative paths
        if not re.match(r"^[A-Za-z]:", raw_path) and not raw_path.startswith("/"):
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
        entry_point_ranking=[],
        current_node_id="",
        traversal_history=[],
        tool_results=[],
        conclusion_nodes=[],
        conversation_history=list(memory.conversation_history),
        final_response="",
        error=None,
    )


def _persist_to_memory(result: dict, memory: SessionMemory, is_new_case: bool) -> None:
    """Update SessionMemory from a completed graph invocation."""
    if is_new_case or not memory.is_initialized():
        memory.csv_catalog = result.get("csv_catalog") or memory.csv_catalog
        memory.case_metadata = result.get("case_metadata") or memory.case_metadata
        memory.results_dir = result.get("results_dir") or memory.results_dir
    memory.update_from_state(result)  # type: ignore[arg-type]


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
        print(f"\n[Using active case: {study_path}]", flush=True)
        graph = get_graph(skip_initialize=True)

    initial_state = _build_initial_state(query, study_path, memory)

    _log.debug(
        "[main] invoking graph  skip_initialize=%s  query=%r",
        not is_new_case, query,
    )

    if stream:
        # Collect all node outputs so we can persist session state after streaming
        final_state: dict = dict(initial_state)  # start from initial so keys are present
        for chunk in graph.stream(initial_state):
            for node_name, node_state in chunk.items():
                print(f"  [{node_name}]", flush=True)
                final_state.update(node_state)
        response = final_state.get("final_response") or "[No response generated]"
        _persist_to_memory(final_state, memory, is_new_case)
    else:
        result = graph.invoke(initial_state)
        response = result.get("final_response") or "[No response generated]"
        _persist_to_memory(result, memory, is_new_case)

    memory.add_turn(query, response)
    _log.debug("[main] response length: %d chars", len(response))
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
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            "Developer mode: print detailed logs of LLM prompts, raw responses, "
            "tool calls, parameter resolution, and edge decisions."
        ),
    )
    args = parser.parse_args()

    # Re-configure logging now that we have the parsed flag
    # (it was already set from sys.argv above, but this handles --debug after other args)
    setup_logging(debug=args.debug)

    # Validate API key (support both OpenAI and Anthropic)
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "[ERROR] No API key found.\n"
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY in the .env file at the repo root.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.debug:
        print("[DEBUG MODE] — detailed logs are enabled\n")

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

        query, path_from_input = _parse_input(user_input)

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
            _log.exception("[main] unhandled exception")
            print(f"\n[ERROR] {type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()

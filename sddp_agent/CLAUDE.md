# CLAUDE.md — SDDP Agent Context

This file provides reusable context for AI-assisted development of the `sddp_agent` package.

## Purpose

`sddp_agent` is a LangGraph diagnostic agent for SDDP (Stochastic Dual Dynamic Programming) power system simulation outputs. It traverses a JSON decision graph, calls Python analysis functions, and generates structured diagnoses.

## Key Files

| File | Role |
|---|---|
| `agent.py` | LangGraph StateGraph — wires nodes and conditional edges |
| `state.py` | `AgentState` TypedDict + `SessionMemory` for multi-turn sessions |
| `system_prompt.py` | SDDP domain system prompt (English) |
| `nodes/initialize.py` | Exports SDDP HTML → CSV, builds `csv_catalog` |
| `nodes/router.py` | Maps user query to `problem_type` via LLM |
| `nodes/graph_navigator.py` | Core traversal: tool selection, column resolution, hypothesis testing |
| `nodes/doc_retriever.py` | Keyword search in `Results.md` at conclusion nodes |
| `nodes/synthesizer.py` | Composes final structured diagnosis |
| `tools/graph_loader.py` | Loads `decision-trees/decision_graph.json` |
| `tools/dataframe_tools.py` | Thin wrappers calling `psr.outputanalysismcp.dataframe_functions` |
| `tools/catalog.py` | Helpers for the CSV results catalog (`_index.json`) |

## Decision Graph Structure

Graph is at `decision-trees/decision_graph.json`. Nodes have:
- `type`: `"analysis"` (has `tools[]`) or `"conclusion"` (has `documentation{}`)
- `tools[]`: list of `{name, params}` — available tools at this node (LLM picks which to run)
- `content.expected_state`: what the data should show for this node's hypothesis to hold
- `documentation.search_intent`: keyword string for Results.md search at conclusion nodes

Edges have `priority` (int, 1=highest). The agent tests children in priority order and follows the first whose hypothesis holds.

## Traversal Logic (graph_navigator.py)

```
For each outgoing edge (by priority):
  1. LLM selects which tools to run (from current node's tools[])
  2. Column names are resolved via LLM (placeholders → real CSV column names)
  3. Tools are executed via call_tool() → raw dict
  4. LLM evaluates: does result support child's expected_state?
  5. Follow first child where hypothesis holds
  6. If none hold → default to priority-1 child
```

## Tool Dispatch

All tools in `TOOL_DISPATCH` (dataframe_tools.py) correspond to the tool names in the decision graph JSON:

- `df_analyze_bounds` → `analyze_bounds_and_reference()`
- `df_analyze_composition` → `analyze_composition()`
- `df_analyze_stagnation` → `analyze_stagnation()`
- `df_cross_correlation` → `analyze_cross_correlation()`
- `df_analyze_heatmap` → `analyze_heatmap()`
- `df_filter_above_threshold` → `filter_by_threshold()`
- `df_get_head` → `get_dataframe_head()`
- `df_get_summary` → `get_data_summary()`

## Session Model

`SessionMemory` persists `csv_catalog`, `case_metadata`, and `results_dir` across questions for the same case. A new `@path` in the user message triggers re-initialization.

## LLM Configuration

- Default model: `claude-sonnet-4-6`
- Override via env var: `SDDP_AGENT_MODEL=claude-opus-4-7`
- API key: `ANTHROPIC_API_KEY` (from `.env` at repo root)

## Prompt Files

Located in `sddp_agent/prompts/`:
- `router_prompt.txt` — problem classification (returns JSON `{problem_type, reasoning}`)
- `tool_selector_prompt.txt` — picks tools to test a child hypothesis (returns JSON list)
- `column_resolver_prompt.txt` — maps placeholder params to real CSV columns (returns JSON dict)
- `edge_selector_prompt.txt` — evaluates if a child hypothesis holds (returns JSON `{holds, reasoning}`)

## SDDP Convergence Rule

**Convergence** = Zinf is inside [Lower_CI, Upper_CI], NOT Zinf == Zsup.
This is enforced in the system prompt and in `node_root_nao_convergencia`'s expected_state.

## Entry Points

| `problem_type` | Root node |
|---|---|
| `problema_convergencia` | `node_root_nao_convergencia` |
| `deslocamento_custo` | `node_deslocamento_custo_sim_politica` |
| `problema_simulacao` | `node_simulacao` |

## Dependencies

```
langgraph>=0.2.0
langchain>=0.3.0
langchain-anthropic>=0.3.0
langchain-core>=0.3.0
python-dotenv>=1.0.0
```

Install: `pip install -e ".[agent]"` from repo root.

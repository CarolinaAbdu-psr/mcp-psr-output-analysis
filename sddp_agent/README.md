# SDDP Diagnostic Agent

A **LangGraph**-based agent that diagnoses SDDP simulation output quality by traversing a structured decision graph, executing Python analysis tools, and generating evidence-based recommendations.

## Architecture

```
User query (@path + question)
        │
        ▼
  ┌─────────────┐
  │  initialize │  Export HTML → CSV, load catalog, extract case metadata (once per case)
  └──────┬──────┘
         │
  ┌──────▼──────┐
  │route_problem│  LLM classifies query → problem_type → entry graph node
  └──────┬──────┘
         │
  ┌──────▼────────────┐
  │execute_graph_node │◄──────────────────────┐
  │                   │                       │ (loop)
  │ For each child    │                       │
  │  (by priority):   │                       │
  │  • select tools   │                       │
  │  • resolve cols   │                       │
  │  • run tools      │                       │
  │  • test hypothesis│                       │
  │  Follow first hit ├───────────────────────┘
  └──────┬────────────┘
         │ (conclusion node)
  ┌──────▼──────────────┐
  │retrieve_documentation│  Search Results.md by keyword similarity
  └──────┬──────────────┘
         │
  ┌──────▼─────────────┐
  │synthesize_response │  LLM composes structured diagnosis
  └────────────────────┘
```

## Installation

```bash
# Install agent dependencies
pip install -e ".[agent]"

# Or add manually
pip install langgraph langchain langchain-anthropic langchain-core python-dotenv
```

## Configuration

Create a `.env` file at the repository root (one already exists as a template):

```
ANTHROPIC_API_KEY=sk-ant-...
```

Optionally override the model:

```
SDDP_AGENT_MODEL=claude-opus-4-7
```

## Usage

```bash
python -m sddp_agent          # start interactive session
python -m sddp_agent --stream # show progress as each node completes
```

Inside the session, include the case path with `@`:

```
You: @C:/casos/base O caso convergiu?
You: Why are penalties so high?           # reuses active case
You: @C:/casos/outro_caso Any issues?     # switches to a new case
You: exit
```

## Decision Graph

The agent follows `decision-trees/decision_graph.json`, which has 3 entry points:

| `problem_type` | Keywords | Root node |
|---|---|---|
| `problema_convergencia` | Zinf/Zsup gap, iterations, convergence | `node_root_nao_convergencia` |
| `deslocamento_custo` | policy vs simulation mismatch, FCF, non-convexities | `node_deslocamento_custo_sim_politica` |
| `problema_simulacao` | penalties, MIP solver, ENA dispersion, cost quality | `node_simulacao` |

## Example Queries

| Query | Expected conclusion |
|---|---|
| `"O caso não convergiu. Por quê?"` | `node_calibrar_penalidades` or `node_limitacao_cenarios` |
| `"Zinf está próximo mas não entrou no IC"` | `node_iteracoes_insuficientes` |
| `"Why is simulation cost above policy?"` | `node_ativar_nao_convexidade` or `node_fcf_outro_caso` |
| `"Há penalidades excessivas na simulação?"` | `node_calibrar_penalidades` |
| `"MIP solver não está convergindo"` | `node_aumentar_tempo_mip` or `node_usar_slices_menores` |
| `"Custos muito dispersos sem correlação ENA"` | `node_dispersao_periodo_umido` |

## File Structure

```
sddp_agent/
├── __init__.py
├── __main__.py          ← REPL entry point
├── agent.py             ← LangGraph StateGraph
├── state.py             ← AgentState TypedDict + SessionMemory
├── system_prompt.py     ← SDDP domain system prompt
├── nodes/
│   ├── initialize.py        ← HTML → CSV export + catalog
│   ├── router.py            ← query → problem_type
│   ├── graph_navigator.py   ← traversal engine
│   ├── doc_retriever.py     ← Results.md keyword search
│   └── synthesizer.py       ← final diagnosis composition
├── tools/
│   ├── graph_loader.py      ← decision_graph.json loader
│   ├── catalog.py           ← _index.json helpers
│   └── dataframe_tools.py   ← wrappers for dataframe_functions.py
└── prompts/
    ├── router_prompt.txt
    ├── tool_selector_prompt.txt
    ├── column_resolver_prompt.txt
    └── edge_selector_prompt.txt
```

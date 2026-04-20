# PSR Output Analysis — MCP Server & Diagnostic Agent

This repository provides two complementary ways to analyze SDDP simulation outputs:

1. **MCP Server** — exposes individual analysis functions as AI tools for use in Claude Code or Claude Desktop.
2. **SDDP Diagnostic Agent** — a LangGraph-based conversational agent that autonomously traverses a decision graph, runs analysis tools, and produces structured diagnoses.

---

## Prerequisites

- **Python 3.10+**
- `psr-output-analysis` package (installed automatically as a dependency)

---

## Installation

```bash
# development install (recommended)
git clone https://github.com/your-org/mcp-psr-output-analysis.git
cd mcp-psr-output-analysis
pip install -e .

# also install agent dependencies
pip install -e ".[agent]"
```

---

## Part 1 — MCP Server

### Running the server

```bash
mcp-psr-output-analysis          # via installed script
mcp run psr/outputanalysismcp/server.py   # via MCP CLI
python -m psr.outputanalysismcp  # via Python module
```

### Configuring Claude Code

Add to `~/.claude/settings.json` (or `settings.local.json` for local-only):

```json
{
  "mcpServers": {
    "psr-output-analysis": {
      "command": "mcp-psr-output-analysis"
    }
  }
}
```

On Windows, if the script is not on PATH, use the full path:

```json
{
  "mcpServers": {
    "psr-output-analysis": {
      "command": "C:\\Users\\<user>\\AppData\\Local\\Programs\\Python\\Python3xx\\Scripts\\mcp-psr-output-analysis.exe"
    }
  }
}
```

Find the exact path with: `where.exe mcp-psr-output-analysis`

### Configuring Claude Desktop

Open the config file:
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add under `mcpServers` (same format as above). Restart Claude Desktop after saving.

### Available MCP tools

#### Setup

| Tool | Description |
|---|---|
| `get_avaliable_results(study_path)` | Sets the active results folder and returns available CSV files. Must be called first. |

#### Policy convergence

| Tool | Description |
|---|---|
| `analyse_policy_convergence()` | Checks whether Zinf entered the [Lower_CI, Upper_CI] band. Reports convergence status, gap trend (LOCKED vs. PROGRESSING), and cut-per-iteration stability. |

#### Cost analysis

| Tool | Description |
|---|---|
| `analyse_costs()` | Three-part report: **(A)** cost breakdown by category with % share; **(B)** 80% health-check (warns if operating cost < 80% of total); **(C)** per-stage hot-spot detection (stages where penalties ≥ 20% of stage total). |

#### SDDP knowledge base

| Tool | Description |
|---|---|
| `list_sddp_knowledge()` | Returns all knowledge entries (id, topic, title, related_problems). |
| `get_sddp_knowledge(topics, problems)` | Returns full content of matching entries (case-insensitive partial match). |

---

## Part 2 — SDDP Diagnostic Agent

A conversational agent that answers diagnostic questions about an SDDP case. It classifies the user's question, navigates a decision graph, runs targeted analysis tools, and produces a structured diagnosis with status (OK / ALERTA / CRÍTICO), root cause, and recommended action.

### Running the agent

```bash
python -m sddp_agent                   # interactive REPL
python -m sddp_agent --stream          # show progress node by node
python -m sddp_agent --debug           # detailed LLM prompt/tool logs
```

Set your API key in a `.env` file at the repo root:

```
OPENAI_API_KEY=sk-...
# or
ANTHROPIC_API_KEY=sk-ant-...
```

### Session model

Point the agent at a case folder using the `@path` prefix. Once set, the path is remembered for the entire session:

```
> @C:/casos/base Did the case converge?
> Why are the penalties so high?       ← reuses C:/casos/base
> @C:/outro_caso Any convergence issues?  ← switches to a new case
```

---

### Agent architecture

The agent is a **LangGraph StateGraph** with six nodes executed in sequence:

```
START
  │
  ▼
initialize ──────── Exports SDDP HTML → CSV, builds the CSV catalog and
  │                  extracts case metadata (binary variables, activities, etc.)
  ▼
route_problem ───── LLM classifies the user query into a problem type and
  │                  ranks entry points by relevance.
  ▼
verify_entry ─────── Runs the entry node's own tools to confirm it matches
  │                  the user's actual problem before traversal begins.
  ▼
execute_graph_node ─ Core traversal loop: tests child hypotheses, runs tools,
  │  ↑               follows the first child whose hypothesis holds.
  │  └── (loop) ─────────────────────────────────────────────────────────┐
  │                                                                       
  ▼ (reaches conclusion node)                                             
retrieve_documentation ── Keyword-searches Results.md for documentation   
  │                        relevant to the conclusion node.               
  ▼                                                                       
synthesize_response ────── Composes the final structured diagnosis.       
  │                                                                       
  ▼                                                                       
END 
```

#### Node descriptions

| Node | File | Role |
|---|---|---|
| `initialize` | `nodes/initialize.py` | Exports the SDDP HTML report to CSV files, reads `_index.json` to build `csv_catalog`, and calls `case_information` to extract metadata such as binary variable settings. Skipped on follow-up questions for the same case. |
| `route_problem` | `nodes/router.py` | Sends the user query + case metadata to the LLM with the list of registered entry points. Returns `problem_type` and an ordered `entry_point_ranking`. |
| `verify_entry_point` | `nodes/verify_entry.py` | Iterates the ranked entry points, runs each node's tools in full, and calls `_hypothesis_holds()` to confirm a match. Falls back to the top-ranked entry if none confirm. |
| `execute_graph_node` | `nodes/graph_navigator.py` | For each outgoing edge (sorted by priority): asks the LLM which of the child's tools to run, resolves placeholder column names to real CSV columns, executes the tools, and evaluates whether the child's hypothesis holds. Follows the first confirmed child; defaults to priority-1 if none confirm. Loops until a conclusion node is reached. |
| `retrieve_documentation` | `nodes/doc_retriever.py` | Reads the conclusion node's `search_intent` field, scores sections of `Results.md` by keyword overlap, and returns the top matching sections as supporting documentation. |
| `synthesize_response` | `nodes/synthesizer.py` | Formats a structured diagnosis from the traversal history, tool results, and retrieved documentation. Output language matches the user's query language. |

---

### Decision graph

The agent traverses `decision-trees/decision_graph.json` — a directed acyclic graph with 35 nodes covering four diagnostic domains.

#### Entry points

| Problem type | Entry node | Triggered when |
|---|---|---|
| `problema_convergencia` | `node_root_nao_convergencia` | User asks about convergence, Zinf, iterations |
| `deslocamento_custo` | `node_deslocamento_custo_sim_politica` | User asks about cost difference between policy and simulation |
| `problema_simulacao` | `node_simulacao` | User asks about simulation costs, penalties, solver status |
| `violacao` | `node_violacao` | User asks about violations, deficit, soft constraints, penalties |

#### Node types

- **`analysis`** nodes have a `tools[]` list and a `content.expected_state`. The agent tests each outgoing edge by running a subset of those tools and asking the LLM if the result matches the child's expected state.
- **`conclusion`** nodes are endpoints. They have a `documentation.search_intent` string used to retrieve supporting content from `Results.md`.

#### Convergence rule

> **Convergence** = Zinf is inside [Lower_CI, Upper_CI].  
> This is NOT the same as Zinf == Zsup.

#### Traversal logic

```
For each outgoing edge (sorted by priority, 1 = highest):
  1. LLM selects which tools from the child's tools[] to run
  2. Placeholder column names are resolved to real CSV column names
  3. Tools are executed; results collected
  4. LLM evaluates: do results (or case metadata, or catalog) support child's expected_state?
  5. Follow the first child whose hypothesis holds
  6. If no child confirmed → default to priority-1 child
```

When a child node has no tools (`tools: []`), the hypothesis is evaluated using:
- **Case metadata** (e.g. `Non-Convexities` key for binary variable nodes)
- **CSV catalog** (if relevant files exist in the output folder, that is treated as positive evidence)

#### Complete node map

**Convergence branch**

| Node | Type | Purpose |
|---|---|---|
| `node_root_nao_convergencia` | analysis | Entry: diagnose convergence failure |
| `node_zinf_aproximando_zsup` | analysis | Zinf approaching the CI band |
| `node_zinf_zsup_distantes` | analysis | Bounds not converging at all |
| `node_penalidades_altas` | analysis | High penalties affecting convergence |
| `node_baixo_forwards` | analysis | Insufficient forward series |
| `node_iteracoes_insuficientes` | conclusion | Add more iterations |
| `node_calibrar_penalidades` | conclusion | Recalibrate penalty weights |
| `node_limitacao_cenarios` | conclusion | Increase number of forward series |

**Cost displacement branch**

| Node | Type | Purpose |
|---|---|---|
| `node_deslocamento_custo_sim_politica` | analysis | Entry: cost gap between policy and simulation |
| `node_variaveis_binarias` | analysis | Check if model uses binary variables |
| `node_integralidade_violada` | analysis | Binary integrality not respected in simulation |
| `node_dados_diferentes_politica` | analysis | Simulation uses different data from policy |
| `node_fcf_outro_caso` | conclusion | External FCF from a different case |
| `node_ativar_nao_convexidade` | conclusion | Activate MIP solver for binary variables |

**Simulation branch**

| Node | Type | Purpose |
|---|---|---|
| `node_simulacao` | analysis | Entry: diagnose simulation cost/quality issues |
| `node_proporcao_custo_operativo_sim` | analysis | Operating cost < 80% of total (penalties dominate) |
| `node_verificar_etapas_penalidades_sim` | analysis | Identify stages and agents with highest penalties |
| `node_dispersao_custos_ena` | analysis | Cost variance correlated with natural inflow |
| `node_estado_solucao_etapa_cenario` | analysis | MIP solver status per stage/scenario |
| `node_solucao_viavel` | analysis | Feasible but suboptimal solutions (time limit hit) |
| `node_solucao_relaxada` | analysis | Relaxed integrality solutions |
| `node_solucao_erro` | analysis | Solver failures |
| `node_dispersao_periodo_umido` | conclusion | Dispersion concentrated in wet season |
| `node_aumentar_tempo_mip` | conclusion | Increase MIP solver time limit |
| `node_usar_slices_menores` | conclusion | Use smaller time slices to reduce problem size |
| `node_checar_conflito_variaveis` | conclusion | Investigate conflicting constraints |

**Violations branch**

| Node | Type | Purpose |
|---|---|---|
| `node_violacao` | analysis | Entry: diagnose violations and penalty calibration |
| `node_media_proxima_maxima` | analysis | Mean violation ≈ max violation (systematic across scenarios) |
| `node_violacao_frequente` | analysis | Violations occur in ≥50% of stages |
| `node_sazonalidade_violacao` | analysis | Violations concentrated in ≤25% of stages (seasonal) |
| `node_conflito_restricoes_analise` | analysis | Fallback: possible constraint conflict |
| `node_penalidade_mal_calibrada_geral` | conclusion | Global penalty recalibration needed |
| `node_penalidade_mal_calibrada_periodo` | conclusion | Seasonal penalty adjustment needed |
| `node_conflito_restricoes_conclusao` | conclusion | Incompatible model constraints |

---

### Analysis tools

All tools are defined in `sddp_agent/tools/dataframe_tools.py` and correspond to the tool names referenced in the decision graph.

| Tool name | Underlying function | Typical use |
|---|---|---|
| `df_analyze_bounds` | `analyze_bounds_and_reference()` | Convergence bands (Zinf vs CI) |
| `df_analyze_composition` | `analyze_composition()` | Cost breakdown by category |
| `df_analyze_stagnation` | `analyze_stagnation()` | Forward series stagnation |
| `df_cross_correlation` | `analyze_cross_correlation()` | Cost vs ENA correlation |
| `df_analyze_heatmap` | `analyze_heatmap()` | Solver status grid by stage/scenario |
| `df_filter_above_threshold` | `filter_by_threshold()` | Stages/agents exceeding penalty threshold |
| `df_get_head` | `get_dataframe_head()` | Raw data preview |
| `df_get_summary` | `get_data_summary()` | Descriptive statistics |
| `df_analyze_violation` | `analyze_violation()` | Violation frequency, seasonality, mean/max ratio |

---

### Output format

The agent always responds with a structured markdown diagnosis:

```markdown
## Diagnóstico: <conclusion node label>

**Status:** OK | ALERTA | CRÍTICO

### O que os dados mostram
<specific numeric values from the analysis tools>

### Causa
<technical explanation drawn from documentation>

### Recomendação
<corrective action — bold for CRÍTICO>

### Dados de Suporte
| Métrica | Valor encontrado | Referência |
|---|---|---|
```

Status meanings:
- **CRÍTICO** — issue prevents correct operation; immediate action required
- **ALERTA** — quality is degraded but case is still usable
- **OK** — no significant problem found

The diagnosis language matches the user's query language automatically.

---

## Repository structure

```
├── psr/outputanalysismcp/      # MCP server
│   ├── server.py               # MCP tool definitions
│   ├── dataframe_functions.py  # Core analysis functions
│   └── case_information.py     # Case metadata extractor
│
├── sddp_agent/                 # LangGraph diagnostic agent
│   ├── agent.py                # LangGraph StateGraph wiring
│   ├── state.py                # AgentState and SessionMemory TypedDicts
│   ├── system_prompt.py        # SDDP domain system prompt
│   ├── nodes/
│   │   ├── initialize.py       # HTML→CSV export, catalog builder
│   │   ├── router.py           # Problem type classifier
│   │   ├── verify_entry.py     # Entry point confirmation
│   │   ├── graph_navigator.py  # Core traversal loop
│   │   ├── doc_retriever.py    # Results.md keyword search
│   │   └── synthesizer.py      # Final diagnosis composer
│   ├── tools/
│   │   ├── graph_loader.py     # Loads decision_graph.json
│   │   ├── dataframe_tools.py  # Tool wrappers + TOOL_DISPATCH
│   │   └── catalog.py          # CSV catalog helpers
│   └── prompts/
│       ├── router_prompt.txt
│       ├── tool_selector_prompt.txt
│       ├── column_resolver_prompt.txt
│       └── edge_selector_prompt.txt
│
├── decision-trees/
│   └── decision_graph.json     # 35-node diagnostic graph
│
├── sddp_knowledge/             # MCP knowledge base (JSON files)
└── Results.md                  # Documentation searched by doc_retriever
```

## Knowledge base

Domain knowledge lives in `sddp_knowledge/` as JSON files:

```json
{
  "id": "unique_id",
  "topic": "convergence",
  "title": "Human-readable title",
  "related_problems": ["tag_a", "tag_b"],
  "content": "Explanation text …",
  "references": [{ "title": "SDDP Manual", "url": "https://…" }]
}
```

| File | Topics covered |
|---|---|
| `policy.json` | Convergence theory, criteria, non-convergence causes, non-convexity |
| `simulation.json` | Cost portions, stage costs, dispersion, solver status |

New files in `sddp_knowledge/` are picked up automatically without restarting.

# PSR Output Analysis MCP Server

MCP server that exposes SDDP output analysis operations as AI tools, enabling
an LLM to read simulation results, diagnose convergence and cost issues, and
explain findings using a built-in SDDP knowledge base.

## Prerequisites

1. **Python 3.10+**
2. `psr-output-analysis` package (installed automatically as a dependency)

## Installation

### Option A — from a local clone (development)

```bash
git clone https://github.com/your-org/mcp-psr-output-analysis.git
cd mcp-psr-output-analysis
pip install -e .
```

### Option B — from PyPI (once published)

```bash
pip install psr-output-analysis-mcp
```

## Running the server

```bash
# directly via the installed script
mcp-psr-output-analysis

# or via the MCP CLI
mcp run psr/outputanalysismcp/server.py

# or as a Python module
python -m psr.outputanalysismcp
```

## Configuring Claude Code

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

If the script is not on the system PATH (common on Windows), use the full path:

```json
{
  "mcpServers": {
    "psr-output-analysis": {
      "command": "C:\\Users\\<user>\\AppData\\Local\\Programs\\Python\\Python3xx\\Scripts\\mcp-psr-output-analysis.exe"
    }
  }
}
```

To find the exact executable path on Windows, run:

```powershell
where.exe mcp-psr-output-analysis
```

## Configuring Claude Desktop

Open the Claude Desktop config file:

- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

Add the entry under `mcpServers`:

```json
{
  "mcpServers": {
    "psr-output-analysis": {
      "command": "mcp-psr-output-analysis"
    }
  }
}
```

After saving, restart Claude Desktop. The tools will appear in the tools panel (hammer icon).

## How it works

The server follows a three-step analysis flow:

```
1. Set case path  →  get_avaliable_results(study_path)
2. Run diagnostics →  analyse_policy_convergence()  /  analyse_costs()
3. Explain results →  list_sddp_knowledge()  +  get_sddp_knowledge(topics, problems)
```

The LLM uses the structured diagnostic reports from steps 1–2 together with the
domain knowledge retrieved in step 3 to give the user clear, grounded answers.

## Available tools

### Setup

| Tool | Description |
|---|---|
| `get_avaliable_results(study_path)` | Sets the active results folder and returns the list of available CSV files inside it. Must be called before any analysis tool. |

### Policy convergence

| Tool | Description |
|---|---|
| `analyse_policy_convergence()` | Checks whether Zinf entered the Zsup ± tolerance band on the last iteration. If not converged, reports the gap trend (LOCKED vs. PROGRESSING) and cut-per-iteration stability to diagnose whether more iterations would help. |

### Cost analysis

| Tool | Description |
|---|---|
| `analyse_costs()` | Three-part cost report: **(A)** full breakdown of operating cost vs. every penalty category with % share; **(B)** 80% health-check — warns if operating cost is below 80% of total and lists significant penalties with their physical meaning; **(C)** per-stage hot-spot detection — flags planning stages where penalties ≥ 20% of that stage's total cost, ranks them, and identifies the dominant penalty type per stage. |

### SDDP knowledge base

| Tool | Description |
|---|---|
| `list_sddp_knowledge()` | Returns all available knowledge entries (id, topic, title, related_problems). Use for discovery — call once per session to understand what topics are covered. |
| `get_sddp_knowledge(topics, problems)` | Returns the full content of entries matching any of the given topic strings or related_problem tags (case-insensitive, partial match). Combine with diagnostic results to give grounded explanations to the user. |

## Knowledge base

Domain knowledge lives in `sddp_knowledge/` as JSON files. Each entry has:

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
| `policy.json` | Convergence theory, convergence criteria, non-convergence causes (stagnation, insufficient iterations), policy vs. simulation validation, non-convexity |
| `simulation.json` | Total cost portions, average cost per stage, cost dispersion, solver status (Optimal / Feasible / Relaxed), solver troubleshooting |

New knowledge files dropped into `sddp_knowledge/` are picked up automatically without restarting the server.

## Results folder structure

The server reads the following CSV files from `<study_path>/results/`:

| File | Used by |
|---|---|
| `convergencia.csv` | `analyse_policy_convergence()` — Zinf, Zsup, tolerance bounds per iteration |
| `nuevos-cortes-por-iterac.csv` | `analyse_policy_convergence()` — new Benders cuts added per iteration |
| `porciones-de-el-costo-op.csv` | `analyse_costs()` — aggregate cost by category |
| `costos-operativos-promed.csv` | `analyse_costs()` — average cost per planning stage |

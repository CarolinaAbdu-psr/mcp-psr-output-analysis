# Installing the PSR Output Analysis Plugin

## One-time setup (per machine)

### 1. Clone the repository

```bash
git clone https://github.com/CarolinaAbdu-psr/mcp-psr-output-analysis.git
cd mcp-psr-output-analysis
```

> Clone to a **permanent folder** — the plugin runs from this path.

### 2. Install Python dependencies

```bash
pip install -e .
```

The `-e` (editable) flag means `git pull` updates everything automatically — no reinstall needed.

### 3. Install the Claude plugin

```bash
claude plugin install .
```

This registers the MCP server and auto-trigger skills with Claude Code.

### 4. Verify the installation

Open a new Claude Code session and type:

> "I have an SDDP case at `<path-to-case>`, can you check the results?"

Claude should start the analysis automatically — no slash command needed.

---

## Getting updates

When a new version is published:

```bash
cd mcp-psr-output-analysis
git pull
```

That's it. The editable install picks up all changes to skills, knowledge base, and server code immediately.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Use `python3` or the full path to your Python executable |
| MCP server not starting | Run `python -m psr.outputanalysismcp` in the repo folder to see the error |
| Skills not triggering | Restart Claude Code after `git pull` |
| `sddp_html_to_csv` import error | Make sure you cloned the full repo (not just installed the package) |

---

## Manual MCP configuration (alternative to `claude plugin install`)

If you prefer to configure MCP manually, add this to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "psr-output-analysis": {
      "command": "python",
      "args": ["-m", "psr.outputanalysismcp"],
      "cwd": "<absolute-path-to-cloned-repo>"
    }
  }
}
```

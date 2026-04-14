# PSR Output Analysis — Setup Guide

This repository is a Claude Code plugin. After the one-time setup below, the
MCP tools and SDDP analysis skills are available in every Claude Code session.

---

## One-time setup

### Step 1 — Clone the repository

```bash
git clone https://github.com/CarolinaAbdu-psr/mcp-psr-output-analysis.git
cd mcp-psr-output-analysis
```

> Clone to a **permanent folder** — the server runs from this location.

### Step 2 — Install Python dependencies

```bash
pip install -e .
```

The `-e` flag (editable install) means the server always reads the latest files
from the cloned folder. No reinstall needed after updates.

### Step 3 — Register this repo as a plugin source

```bash
claude plugin marketplace add /absolute/path/to/mcp-psr-output-analysis
```

Replace `/absolute/path/to/mcp-psr-output-analysis` with the actual path where
you cloned the repo. Examples:

- Windows: `claude plugin marketplace add "C:/Dev/mcp-psr-output-analysis"`
- Mac/Linux: `claude plugin marketplace add ~/Dev/mcp-psr-output-analysis`

### Step 4 — Install the plugin

```bash
claude plugin install psr-output-analysis
```

### Step 5 — Restart Claude Code

Close and reopen Claude Code. The MCP server and SDDP skills are now active.

---

## Verify it works

Open a new Claude Code session and type:

> "I have an SDDP case at `<path-to-case>`, can you check the results?"

Claude should start the analysis automatically — no slash command needed.

---

## Getting updates

When a new version is published:

```bash
cd mcp-psr-output-analysis
git pull
claude plugin update psr-output-analysis
```

Restart Claude Code. Done.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` not found | Use `python3` or the full path to your Python executable |
| MCP server not starting | Run `python -m psr.outputanalysismcp` in the repo folder to see the error |
| Skills not triggering | Restart Claude Code after installing or updating |
| Plugin not found after `marketplace add` | Verify the path is absolute and correct |

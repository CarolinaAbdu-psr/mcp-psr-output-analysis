"""
Synthesizer node: compose the final structured diagnosis from conclusion data.

Combines conclusion node documentation, tool results, and conversation
history to produce the structured markdown format defined in sddp-diagnose.md.
"""
from __future__ import annotations

import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..utils import get_logger

_log = get_logger("synthesizer")

_SYNTHESIS_PROMPT = """\
You have completed the SDDP diagnostic graph traversal. Compose the final diagnosis.

## User question
{user_query}

## Graph path taken
{traversal_path}

## Conclusion(s) reached
{conclusions}

## All tool results collected during traversal
{all_tool_results}

## Instructions
Produce a structured diagnosis in the user's language using this exact format:

```
## Diagnóstico: <conclusion node label>

**Status:** OK | ALERTA | CRÍTICO

### O que os dados mostram
<specific numeric values extracted from tool results — cite actual numbers>

### Causa
<technical explanation based on the documentation content in the conclusion entries>

### Recomendação
<corrective action — use **bold** if Status is CRÍTICO>

### Dados de Suporte
| Métrica | Valor encontrado | Referência |
|---|---|---|
| <key metric> | <value from data> | <threshold or norm> |
```

Rules:
- Status is CRÍTICO when the diagnosed issue prevents correct operation.
- Status is ALERTA when the issue degrades quality but the case is still usable.
- Status is OK only if no real problem was found despite traversal.
- Cite specific numbers from the tool_results — do not make up values.
- If tool results contain errors ({{"error": "..."}}), acknowledge that data was unavailable
  for that metric and note it in the support table.
- If multiple conclusions were reached (multiple branches), produce one section per branch,
  then a brief overall summary.
- Respond in the SAME LANGUAGE as the user question.
"""


def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model_name="gpt-4.1", max_tokens=2048, temperature=0.4)


def synthesize_response(state: dict) -> dict:
    """
    Generate the final structured diagnosis.

    Reads:  conclusion_nodes, tool_results, user_query, traversal_history
    Writes: final_response
    """
    conclusions = state.get("conclusion_nodes", [])
    all_tool_results = state.get("tool_results", [])
    traversal = state.get("traversal_history", [])

    _log.debug(
        "[synthesizer] conclusions=%d  tool_result_nodes=%d  path=%s",
        len(conclusions),
        len(all_tool_results),
        " → ".join(traversal),
    )

    # Compact tool results to save tokens — drop verbose params, keep results
    compact_results: list[dict] = []
    for node_entry in all_tool_results:
        for r in node_entry.get("results", []):
            entry = {
                "node": node_entry.get("node_id", "?"),
                "tool": r.get("tool_name", "?"),
                "result": r.get("result", {}),
            }
            compact_results.append(entry)
            if "error" in r.get("result", {}):
                _log.warning(
                    "[synthesizer] tool %s at node %s had error: %s",
                    r.get("tool_name"),
                    node_entry.get("node_id"),
                    r["result"]["error"],
                )

    _log.debug(
        "[synthesizer] %d tool calls total (%d with errors)",
        len(compact_results),
        sum(1 for r in compact_results if "error" in r.get("result", {})),
    )

    prompt = _SYNTHESIS_PROMPT.format(
        user_query=state.get("user_query", ""),
        traversal_path=" → ".join(traversal),
        conclusions=json.dumps(conclusions, indent=2, ensure_ascii=False),
        all_tool_results=json.dumps(compact_results, indent=2, ensure_ascii=False),
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    _log.debug("[synthesizer] response length: %d chars", len(response.content))
    return {"final_response": response.content}

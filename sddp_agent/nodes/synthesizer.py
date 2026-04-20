"""
Synthesizer node: compose the final structured diagnosis from conclusion data.

Combines conclusion node documentation, tool results, and conversation
history to produce the structured markdown format defined in sddp-diagnose.md.
"""
from __future__ import annotations

import json
import os

#from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT

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
- If multiple conclusions were reached (multiple branches), produce one section per branch,
  then a brief overall summary.
- Respond in the SAME LANGUAGE as the user question.
"""


def _get_llm() -> ChatOpenAI:
    llm = ChatOpenAI(model_name="gpt-4.1",max_tokens=2048, temperature=0.4)
    #return ChatAnthropic(model=os.getenv("SDDP_AGENT_MODEL", "claude-sonnet-4-6"),temperature=0,max_tokens=256,)
    return llm


def synthesize_response(state: dict) -> dict:
    """
    Generate the final structured diagnosis.

    Reads: conclusion_nodes, tool_results, user_query, traversal_history
    Writes: final_response
    """
    conclusions = state.get("conclusion_nodes", [])
    all_tool_results = state.get("tool_results", [])
    traversal = state.get("traversal_history", [])

    # Compact tool result representation to save tokens
    compact_results: list[dict] = []
    for node_entry in all_tool_results:
        for r in node_entry.get("results", []):
            compact_results.append({
                "node": node_entry.get("node_id", "?"),
                "tool": r.get("tool_name", "?"),
                "result": r.get("result", {}),
            })

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

    return {"final_response": response.content}

"""
Synthesizer node: compose the final structured diagnosis from conclusion data.

Combines case metadata, conclusion node documentation, all tool results
(with raw data samples), traversal path, and conversation history to
produce the structured markdown format defined in sddp-diagnose.md.
"""
from __future__ import annotations

import json
import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from ..system_prompt import SYSTEM_PROMPT
from ..utils import get_logger

_log = get_logger("synthesizer")

_SYNTHESIS_PROMPT = """\
You have completed the SDDP diagnostic graph traversal. Compose the final diagnosis.

## User question
{user_query}

## Case metadata (study configuration)
{case_metadata}

## Graph traversal path
{traversal_path}

## Conclusion(s) reached
{conclusions}

## All tool results collected during traversal
Each entry shows the graph node where the tool was called, the tool name, and its full result.
Use these numbers to populate the "Dados de Suporte" table — cite actual values.
{all_tool_results}

## Recent conversation history (for tone and language reference)
{conversation_history}

## Instructions
Produce a structured diagnosis in the SAME LANGUAGE as the user question.
Use this exact format:

```
## Diagnóstico: <conclusion node label>

### O que os dados mostram
<Cite specific numeric values from the tool results above.
 For each key metric, state the value found and whether it crosses the relevant threshold.
 If df_analyze_bounds was run: state converged=true/false, current_value, interval.
 If df_analyze_composition was run: state the operating cost share % and which stages are critical.
 If df_analyze_stagnation was run: state is_stagnated, cv_pct, net_change.
 If df_analyze_violation was run: state the verdict (SYSTEMATIC/FREQUENT/SEASONAL) and top columns.
 If df_analyze_cmo was run: state has_zero_values, has_negative_values, top dispersed stages.
 If a tool returned an error, state that the metric was unavailable.>

### Causa raiz
<Technical explanation grounded in the documentation content from the conclusion entries.
 Explain WHY the data pattern observed leads to the diagnosed problem.>

### Recomendação
<Specific corrective action(s) with priority order if multiple steps are needed.>

### Dados de Suporte
| Métrica | Valor encontrado | Limiar / Referência | Status |
|---|---|---|---|
| <key metric from tool results> | <actual number from data> | <threshold or norm> | ✅ / ⚠️ / ❌ |
```

Rules:
- Cite specific numbers from tool_results — never invent values.
- If multiple conclusions were reached (multiple branches), produce one section per conclusion,
  then an overall summary at the end.
- Use case_metadata to enrich the context (number of stages, series, model version, etc.).
- Respond strictly in the same language as the user question.
"""


def _get_llm() -> ChatAnthropic:
    model = os.environ.get("SDDP_AGENT_MODEL", "claude-sonnet-4-6")
    return ChatAnthropic(model=model, max_tokens=2048, temperature=0.4)  # type: ignore[call-arg]


def _extract_data_samples(all_tool_results: list[dict]) -> list[dict]:
    """
    Build a compact but information-rich representation of tool results.
    Keeps the full result dict (not just top-level keys) so the LLM can
    extract specific numeric values for the support table.
    """
    compact: list[dict] = []
    for node_entry in all_tool_results:
        node_id = node_entry.get("node_id", "?")
        for r in node_entry.get("results", []):
            result = r.get("result", {})
            entry: dict = {
                "node": node_id,
                "tool": r.get("tool_name", "?"),
                "result": result,
            }
            # Surface any errors explicitly
            if "error" in result:
                _log.warning(
                    "[synthesizer] tool %s at node %s had error: %s",
                    r.get("tool_name"),
                    node_id,
                    result["error"],
                )
            compact.append(entry)
    return compact


def synthesize_response(state: dict) -> dict:
    """
    Generate the final structured diagnosis.

    Reads:  conclusion_nodes, tool_results, case_metadata, user_query,
            traversal_history, conversation_history
    Writes: final_response
    """
    conclusions      = state.get("conclusion_nodes", [])
    all_tool_results = state.get("tool_results", [])
    traversal        = state.get("traversal_history", [])
    case_metadata    = state.get("case_metadata", {})

    _log.debug(
        "[synthesizer] conclusions=%d  tool_result_nodes=%d  path=%s",
        len(conclusions),
        len(all_tool_results),
        " → ".join(traversal),
    )

    compact_results = _extract_data_samples(all_tool_results)

    _log.debug(
        "[synthesizer] %d tool calls total (%d with errors)",
        len(compact_results),
        sum(1 for r in compact_results if "error" in r.get("result", {})),
    )

    # Recent conversation history for language/tone reference
    history_text = ""
    for msg in state.get("conversation_history", [])[-6:]:
        role = msg["role"].upper()
        history_text += f"{role}: {msg['content']}\n"

    prompt = _SYNTHESIS_PROMPT.format(
        user_query=state.get("user_query", ""),
        case_metadata=json.dumps(case_metadata, indent=2, ensure_ascii=False),
        traversal_path=" → ".join(traversal),
        conclusions=json.dumps(conclusions, indent=2, ensure_ascii=False),
        all_tool_results=json.dumps(compact_results, indent=2, ensure_ascii=False),
        conversation_history=history_text.strip() or "(first question — no history)",
    )

    llm = _get_llm()
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ])

    _log.debug("[synthesizer] response length: %d chars", len(response.content))
    return {"final_response": response.content}

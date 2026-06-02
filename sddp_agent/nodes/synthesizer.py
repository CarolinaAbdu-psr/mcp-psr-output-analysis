"""
Synthesizer node: compose the final structured diagnosis from conclusion data.

Combines case metadata, conclusion node documentation, all tool results
(with raw data samples), traversal path, and conversation history to
produce the structured markdown format defined in sddp-diagnose.md.
"""
from __future__ import annotations

import json
import os

from langchain_core.messages import HumanMessage, SystemMessage

from .. import get_model

from ..system_prompt import SYSTEM_PROMPT
from ..utils import get_logger

_log = get_logger("synthesizer")

_SYNTHESIS_PROMPT = """\
You have completed an SDDP diagnostic traversal. Write a diagnostic narrative that walks \
the reader through the analysis exactly as a senior engineer would explain it to someone \
who wants to learn the method — building the reasoning step by step, from the first check \
to the final conclusion.

## User question
{user_query}

## Case metadata (study configuration)
{case_metadata}

## Graph traversal path (internal reference only — do NOT mention this in the response)
{traversal_path}

## Conclusion(s) reached
{conclusions}

## Tool results collected during traversal
The entries are ordered chronologically: the first entry is the first check performed,
the last is the final check before the conclusion.
Each entry: node where the tool ran, tool name, full result dict.
Every factual claim in the narrative MUST be grounded in one of these results.
{all_tool_results}

## Recent conversation history (for language and tone reference)
{conversation_history}

## Instructions

Write a flowing diagnostic narrative in the SAME LANGUAGE as the user question.
Do NOT mention: nodes, graphs, LLMs, decision trees, traversal, internal tool names,
or any analysis infrastructure. Write as if you personally ran each check.

---

### Narrative structure

**Title line**
One bold line: the diagnosis conclusion (use the conclusion node label, translated naturally).

**Opening sentence**
One sentence: what problem was reported and in which case.

**One paragraph per check performed** (follow the chronological order of tool_results):
  - Start each paragraph with a short sentence explaining WHY this particular metric
    was the right thing to check next (the SDDP domain logic behind the choice).
  - State what was found: cite the EXACT numbers from the tool result.
    • df_analyze_bounds  → cite current_value, interval [low, high], converged true/false,
                           is_locked, accuracy_trend.
    • df_analyze_stagnation → cite status (Stagnated/Active), cv_pct or net_change if present.
    • df_analyze_composition → cite target_share_of_total_pct, total_critical_found,
                               and the stages flagged (from critical_scenarios list).
    • df_analyze_heatmap / df_filter_above_threshold → cite how many stages/agents exceeded
                               the threshold and the top offenders by name.
    • df_analyze_violation → cite the verdict label, frequency or ratio found, top columns.
    • df_analyze_cmo → cite has_zeros, has_negatives, top dispersed stages.
    • check_*_penalties → cite which penalty names were found and their values.
    • df_check_nonconvexity_policy → cite NonConvexityRepresentationInPolicy value.
    • If a tool returned an error, say the metric was unavailable and move on.
  - End the paragraph with one sentence that either confirms the hypothesis for this step
    ("Esse padrão confirma que...") or rules it out and explains the pivot
    ("Como X não foi detectado, a investigação avançou para...").

**Root-cause paragraph**
Explain WHY the observed data pattern produces the diagnosed problem.
Ground this in the documentation content from the conclusion entries.
Use SDDP-domain language: Benders cuts, FCF, policy vs. simulation, etc.

**Recommendation paragraph**
Specific corrective actions, in priority order when there are multiple.
Be concrete: what setting to change, what value to use, what to rerun.

---

### Style rules
- Write in flowing prose — no bullet lists inside paragraphs, no markdown tables.
- Use bold (**text**) only for the title line and for key numeric findings inline
  (e.g. "o Zinf atingiu **2.345 $/MWh**, fora do intervalo **[2.890 – 2.950]**").
- Each paragraph should be 3–6 sentences. Avoid single-sentence paragraphs.
- Transitions between paragraphs must make causal sense
  ("Como a estagnação foi confirmada, o próximo passo foi investigar...").
- If multiple independent conclusions were reached, write one narrative block per
  conclusion, then one final paragraph summarising the overall picture.
- Use case_metadata to add context: number of stages, series, model version, horizon.
- Never invent numbers. If a value is absent from tool_results, omit that claim.
- Respond strictly in the same language as the user question.
"""


def _get_llm():
    return get_model.GPT_4_1


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

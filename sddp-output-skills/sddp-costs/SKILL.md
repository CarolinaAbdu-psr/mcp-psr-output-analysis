---
name: sddp-costs
description: Analyze SDDP simulation costs — health check, uncertainty correlation, and penalty participation.
---

# SDDP Cost Analysis

Deep-dive into SDDP simulation costs: health check, stochastic uncertainty, and penalty participation.

## Workflow

### Step 1 — Setup
Call `get_avaliable_results(study_path)`.

### Step 2 — Cost health
Call `analyse_cost_health()`.

Report:
- **Operating cost share**: is it ≥ 80%? If below, the model has significant constraint violations.
- **Dominant penalties**: list any penalty above 1% of grand total with its share.
- **Stage hot-spots**: stages where penalties ≥ 20% of that stage's total cost. Present as a table (Stage | Op. Cost | Penalty% | Dominant penalty type).

Verdict: HEALTHY / WARNING / CRITICAL based on the operating cost share.

### Step 3 — Cost dispersion and ENA correlation
Call `analyse_cost_dispersion()`.

Report the three metric groups in plain language:

**[1] Pearson correlations**
- Uncertainty correlation (spread vs spread): are wider ENA bands associated with wider cost bands?
- Level correlation (avg cost vs avg ENA): does higher inflow reduce average cost?

**[2] R² — deterministic coefficient**
- "ENA spread explains X% of cost spread variance."
- If R² < 25%: cost uncertainty is not primarily driven by hydrology — investigate penalties, thermal constraints, or reservoir limits.

**[3] Elasticity**
- "If ENA spread decreases by 10%, cost spread changes by ±Y%."
- "If average ENA decreases by 10%, average cost changes by ±Z%."

Highlight the top high-CV stages (CV > 0.30). These are the periods of greatest stochastic uncertainty.

### Step 4 — Penalty participation (conditional)
Call `analyse_penalty_participation()` **only if** Step 2 found:
- Operating cost share < 80%, OR
- More than 2 stage hot-spots flagged.

Report:
- Which scenarios carry the highest penalty burden on average.
- Which stages show the highest mean penalty participation.
- Per-scenario breakdown for the worst stages.

### Step 5 — Synthesis
Deliver a cost analysis summary:
- Overall cost composition (operating vs penalties).
- Uncertainty drivers: is it hydrology or other factors?
- Whether penalty participation is concentrated in specific scenarios (pointing to a model issue) or spread across all scenarios (systematic constraint).
- Top recommended actions if issues are found.

## Rules
- Present per-stage data as tables, not lists.
- Always include the elasticity interpretation in plain language ("a 10% drop in ENA...").
- If operating cost < 80%, emphasise it prominently — it is the most critical finding.
- Do not re-explain SDDP theory unless the user asks; stay data-focused.

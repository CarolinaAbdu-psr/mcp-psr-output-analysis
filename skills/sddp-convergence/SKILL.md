---
name: sddp-convergence
description: >
  Analyse SDDP policy convergence and validate the final simulation against the
  policy confidence band. Use when the user asks whether the run converged, about
  the quality of the operating policy, about the gap between bounds, or mentions
  keywords like "convergence", "convergência", "converged", "convergiu", "Zinf",
  "Zsup", "policy", "política", "gap", "iterations", or "iterações".
  Requires an SDDP case folder with simulation results.
version: 1.0.0
---

The user wants to check SDDP policy convergence. Follow this workflow:

1. **Get the case path.** Ask if not provided.

2. **Extract and list results.**
   - `extract_html_results(study_path)` — export HTML charts to CSV.
   - `get_avaliable_results(study_path)` — list available files.

3. **Identify the convergence file.** Look for CSV names containing `convergence`, `convergência`, `bounds`, or `policy`. Call `df_get_columns` + `df_get_head` to confirm columns for Zinf, Zsup, and tolerance band.

4. **Policy convergence check.**
   - `df_analyze_bounds` — Zinf (target) vs. tolerance band (lower/upper), Zsup as reference.
   - If not converged: `df_analyze_stagnation` on the Zinf column to distinguish "needs more iterations" from "stagnated".

5. **Policy vs. simulation validation.** Find the policy-vs-simulation comparison CSV and run `df_analyze_bounds` with the simulation mean as the target and the policy confidence interval as the band.

6. **Fetch knowledge.**
   - `get_sddp_knowledge(topics=["convergence"])` — for policy convergence diagnosis.
   - `get_sddp_knowledge(topics=["convergence_validation"])` — for policy-vs-simulation deviation.

7. **Format the response.**
   - Respond in the user's language.
   - Two sections: **A. Policy Convergence** and **B. Policy vs. Simulation Validation**, each with a verdict (OK / Warning / Critical).
   - Include a table of the last 5–10 iterations (Zinf, Zsup, Gap %).
   - Cite knowledge entries with reference URLs.

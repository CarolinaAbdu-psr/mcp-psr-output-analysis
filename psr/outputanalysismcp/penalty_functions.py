"""
Core functions for analyzing penalty settings in SDDP cases via psr.factory.

Each function returns a plain dict (never formatted text) so it can be used
both by the MCP server (which formats results as text) and by the LangGraph
agent (which uses raw dicts for hypothesis evaluation).

Available penalty names per category are exported as constants so the LLM
can enumerate them and pass a targeted subset via the `penalty_names` param.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import psr.factory


# ---------------------------------------------------------------------------
# Available penalty names — exported so callers can discover them
# ---------------------------------------------------------------------------

#: Study-level penalty property names.
STUDY_PENALTY_NAMES: list[str] = [
    "SpillagePenaltyKHm3",
    "MinimumOutflowPenaltyHm3",
    "OverloadPenaltyMwh",
    "WaterwayFlowPenalty",
    "RepresentPenaltiesInTwoLevels",
]

#: Hydro plant penalty property names (all static).
HYDRO_PENALTY_NAMES: list[str] = [
    "AlertStoragePenalty",
    "MaximumOperativeStoragePenalty",
    "MinimumOperativeStoragePenalty",
    "MaximumSpillagePenalty",
    "MaximumTurbiningPenalty",
    "MinimumTurbiningPenalty",
    "MinimumOperativeTotalOutflowPenalty",
]

#: Thermal plant penalty property names.
THERMAL_PENALTY_NAMES: list[str] = [
    "MinimumGenerationPenalty",
]

#: Renewable plant penalty property names (dynamic — summarized as stats).
RENEWABLE_PENALTY_NAMES: list[str] = [
    "SpillingPenalty",
]

#: System-level penalty property names.
SYSTEM_PENALTY_NAMES: list[str] = [
    "RiskAversionCurvePenalty",
    "HydroPlant_PrimaryReserveViolationPenalty",
    "ThermalPlant_PrimaryReserveViolationPenalty",
]


# ---------------------------------------------------------------------------
# Metadata catalogue (unit + note per property)
# ---------------------------------------------------------------------------

_PROP_META: dict[str, dict] = {
    # Study
    "SpillagePenaltyKHm3":         {"unit": "k$/hm3", "note": "Global spillage penalty. 0=no penalty.",
                                     "disabled_at_zero": False},
    "MinimumOutflowPenaltyHm3":    {"unit": "$/hm3",  "note": "Global minimum outflow penalty. -1=disabled.",
                                     "disabled_at_zero": True},
    "OverloadPenaltyMwh":          {"unit": "$/MWh",  "note": "Overload penalty for transmission circuits.",
                                     "disabled_at_zero": False},
    "WaterwayFlowPenalty":         {"unit": "",       "note": "Waterway flow constraint penalty.",
                                     "disabled_at_zero": False},
    "RepresentPenaltiesInTwoLevels": {"unit": "",     "note": "0=No, 1=Yes — split penalties into two cost levels.",
                                     "disabled_at_zero": False},
    # Hydro
    "AlertStoragePenalty":               {"unit": "k$/hm3", "note": "Alert storage violation. -1=auto (> most expensive resource, < deficit).",
                                          "disabled_at_zero": False},
    "MaximumOperativeStoragePenalty":    {"unit": "k$/hm3", "note": "Maximum operative storage violation. -1=auto (> deficit cost).",
                                          "disabled_at_zero": False},
    "MinimumOperativeStoragePenalty":    {"unit": "k$/hm3", "note": "Minimum operative storage violation. -1=auto (> deficit cost).",
                                          "disabled_at_zero": False},
    "MaximumSpillagePenalty":            {"unit": "k$/hm3", "note": "Maximum spillage constraint violation. -1=auto (> deficit cost).",
                                          "disabled_at_zero": False},
    "MaximumTurbiningPenalty":           {"unit": "",       "note": "Maximum turbined outflow violation. 0=disabled.",
                                          "disabled_at_zero": True},
    "MinimumTurbiningPenalty":           {"unit": "",       "note": "Minimum turbined outflow violation. 0=disabled.",
                                          "disabled_at_zero": True},
    "MinimumOperativeTotalOutflowPenalty": {"unit": "k$/hm3", "note": "Min total outflow violation. 0=use study-level MinimumOutflowPenaltyHm3.",
                                          "disabled_at_zero": True},
    # Thermal
    "MinimumGenerationPenalty":          {"unit": "k$/MWh", "note": "Minimum generation violation. -1=auto, 0=disabled.",
                                          "disabled_at_zero": True},
    # Renewable (dynamic)
    "SpillingPenalty":                   {"unit": "$/MWh",  "note": "Curtailment/spilling cost (dynamic). 0=free curtailment.",
                                          "disabled_at_zero": False},
    # System
    "RiskAversionCurvePenalty":          {"unit": "k$/MWh", "note": "Risk aversion curve penalty. -1=auto.",
                                          "disabled_at_zero": False},
    "HydroPlant_PrimaryReserveViolationPenalty":   {"unit": "", "note": "Hydro primary reserve violation penalty.",
                                                    "disabled_at_zero": False},
    "ThermalPlant_PrimaryReserveViolationPenalty": {"unit": "", "note": "Thermal primary reserve violation penalty.",
                                                    "disabled_at_zero": False},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_static(obj, prop: str) -> object:
    """Return obj.get(prop) or None on error."""
    try:
        return obj.get(prop)
    except Exception:
        return None


def _read_dynamic_summary(obj, prop: str) -> dict | None:
    """Return summary stats for a dynamic (time-varying) property, or None."""
    try:
        df = obj.get_df(prop)
        if df is None or df.empty:
            return None
        numeric = df.select_dtypes("number")
        return {
            "mean":    float(numeric.values.mean()),
            "min":     float(numeric.values.min()),
            "max":     float(numeric.values.max()),
            "nonzero": int((numeric.values != 0).sum()),
            "total":   int(numeric.size),
        }
    except Exception:
        return None


def _penalty_status(value: object, *, disabled_at_zero: bool = False) -> str:
    if value is None:
        return "not_set"
    if value == -1:
        return "auto"
    if disabled_at_zero and value == 0:
        return "disabled"
    if value == 0:
        return "zero"
    return "custom"


def _resolve_names(requested: list[str] | None, available: list[str]) -> list[str]:
    """Return the intersection of requested names with available ones (or all if None)."""
    if not requested:
        return available
    unknown = set(requested) - set(available)
    if unknown:
        raise ValueError(
            f"Unknown penalty name(s): {sorted(unknown)}. "
            f"Available: {available}"
        )
    return [n for n in available if n in requested]


def _build_static_entry(obj, prop: str) -> dict:
    meta = _PROP_META[prop]
    value = _read_static(obj, prop)
    return {
        "value":  value,
        "unit":   meta["unit"],
        "status": _penalty_status(value, disabled_at_zero=meta["disabled_at_zero"]),
        "note":   meta["note"],
    }


def _build_dynamic_entry(obj, prop: str) -> dict:
    meta = _PROP_META[prop]
    summary = _read_dynamic_summary(obj, prop)
    if summary is not None:
        status = "zero" if summary["mean"] == 0 else "custom"
    else:
        status = "not_set"
    return {
        "unit":    meta["unit"],
        "status":  status,
        "note":    meta["note"],
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Study-level penalties
# ---------------------------------------------------------------------------

def check_study_penalties(
    case_path: str,
    penalty_names: Optional[list[str]] = None,
) -> dict:
    """
    Read study-level penalty settings from an SDDP case.

    Args:
        case_path:     Absolute path to the SDDP case folder.
        penalty_names: Subset of STUDY_PENALTY_NAMES to read.
                       Pass None (default) to read all.
                       Available names: SpillagePenaltyKHm3,
                       MinimumOutflowPenaltyHm3, OverloadPenaltyMwh,
                       WaterwayFlowPenalty, RepresentPenaltiesInTwoLevels.
    """
    names = _resolve_names(penalty_names, STUDY_PENALTY_NAMES)
    study = psr.factory.load_study(case_path)

    penalties: dict[str, dict] = {}
    for prop in names:
        penalties[prop] = _build_static_entry(study, prop)

    flagged = [p for p, d in penalties.items() if d["status"] in ("zero", "auto")]

    return {
        "case":         Path(case_path).name,
        "category":     "study",
        "queried":      names,
        "penalties":    penalties,
        "flagged":      flagged,
        "summary": (
            f"{len(flagged)} of {len(names)} queried study penalties are at "
            f"zero or auto-default (may indicate uncalibrated settings)."
        ),
    }


# ---------------------------------------------------------------------------
# Hydro penalties
# ---------------------------------------------------------------------------

def check_hydro_penalties(
    case_path: str,
    plant_name: Optional[str] = None,
    penalty_names: Optional[list[str]] = None,
) -> dict:
    """
    Read hydro plant penalty settings.

    Args:
        case_path:     Absolute path to the SDDP case folder.
        plant_name:    Filter to a single plant by name. None = all plants.
        penalty_names: Subset of HYDRO_PENALTY_NAMES to read.
                       Pass None (default) to read all.
                       Available names: AlertStoragePenalty,
                       MaximumOperativeStoragePenalty,
                       MinimumOperativeStoragePenalty,
                       MaximumSpillagePenalty, MaximumTurbiningPenalty,
                       MinimumTurbiningPenalty,
                       MinimumOperativeTotalOutflowPenalty.
    """
    names = _resolve_names(penalty_names, HYDRO_PENALTY_NAMES)
    study = psr.factory.load_study(case_path)
    plants = study.get("HydroPlant") or []

    results: list[dict] = []
    for plant in plants:
        name = getattr(plant, "name", None) or str(getattr(plant, "code", "?"))
        if plant_name and name.lower() != plant_name.lower():
            continue

        penalties: dict[str, dict] = {}
        for prop in names:
            penalties[prop] = _build_static_entry(plant, prop)

        flagged = [p for p, d in penalties.items()
                   if d["status"] in ("zero", "auto", "not_set")]

        results.append({
            "name":      name,
            "code":      getattr(plant, "code", None),
            "penalties": penalties,
            "flagged":   flagged,
        })

    uncalibrated = [r["name"] for r in results if r["flagged"]]

    return {
        "case":         Path(case_path).name,
        "category":     "hydro",
        "queried":      names,
        "plants":       results,
        "total_plants": len(results),
        "uncalibrated": uncalibrated,
        "summary": (
            f"{len(results)} hydro plant(s) read. "
            f"{len(uncalibrated)} have at least one queried penalty at zero/auto/not-set."
        ),
    }


# ---------------------------------------------------------------------------
# Thermal penalties
# ---------------------------------------------------------------------------

def check_thermal_penalties(
    case_path: str,
    plant_name: Optional[str] = None,
    penalty_names: Optional[list[str]] = None,
) -> dict:
    """
    Read thermal plant penalty settings.

    Args:
        case_path:     Absolute path to the SDDP case folder.
        plant_name:    Filter to a single plant by name. None = all plants.
        penalty_names: Subset of THERMAL_PENALTY_NAMES to read.
                       Pass None (default) to read all.
                       Available names: MinimumGenerationPenalty.
    """
    names = _resolve_names(penalty_names, THERMAL_PENALTY_NAMES)
    study = psr.factory.load_study(case_path)
    plants = study.get("ThermalPlant") or []

    results: list[dict] = []
    for plant in plants:
        name = getattr(plant, "name", None) or str(getattr(plant, "code", "?"))
        if plant_name and name.lower() != plant_name.lower():
            continue

        penalties: dict[str, dict] = {}
        for prop in names:
            penalties[prop] = _build_static_entry(plant, prop)

        flagged = [p for p, d in penalties.items()
                   if d["status"] in ("zero", "auto", "not_set")]

        results.append({
            "name":      name,
            "code":      getattr(plant, "code", None),
            "penalties": penalties,
            "flagged":   flagged,
        })

    uncalibrated = [r["name"] for r in results if r["flagged"]]

    return {
        "case":         Path(case_path).name,
        "category":     "thermal",
        "queried":      names,
        "plants":       results,
        "total_plants": len(results),
        "uncalibrated": uncalibrated,
        "summary": (
            f"{len(results)} thermal plant(s) read. "
            f"{len(uncalibrated)} have at least one queried penalty at zero/auto/not-set."
        ),
    }


# ---------------------------------------------------------------------------
# Renewable penalties
# ---------------------------------------------------------------------------

def check_renewable_penalties(
    case_path: str,
    plant_name: Optional[str] = None,
    penalty_names: Optional[list[str]] = None,
) -> dict:
    """
    Read renewable plant curtailment/spilling penalty settings.

    SpillingPenalty is a dynamic property (varies with time); summarized as
    mean/min/max/nonzero statistics.

    Args:
        case_path:     Absolute path to the SDDP case folder.
        plant_name:    Filter to a single plant by name. None = all plants.
        penalty_names: Subset of RENEWABLE_PENALTY_NAMES to read.
                       Pass None (default) to read all.
                       Available names: SpillingPenalty.
    """
    names = _resolve_names(penalty_names, RENEWABLE_PENALTY_NAMES)
    study = psr.factory.load_study(case_path)
    plants = study.get("RenewablePlant") or []

    results: list[dict] = []
    for plant in plants:
        name = getattr(plant, "name", None) or str(getattr(plant, "code", "?"))
        if plant_name and name.lower() != plant_name.lower():
            continue

        penalties: dict[str, dict] = {}
        for prop in names:
            penalties[prop] = _build_dynamic_entry(plant, prop)

        flagged = [p for p, d in penalties.items()
                   if d["status"] in ("zero", "not_set")]

        results.append({
            "name":      name,
            "code":      getattr(plant, "code", None),
            "penalties": penalties,
            "flagged":   flagged,
        })

    uncalibrated = [r["name"] for r in results if r["flagged"]]

    return {
        "case":         Path(case_path).name,
        "category":     "renewable",
        "queried":      names,
        "plants":       results,
        "total_plants": len(results),
        "uncalibrated": uncalibrated,
        "summary": (
            f"{len(results)} renewable plant(s) read. "
            f"{len(uncalibrated)} have at least one queried penalty at zero or not set."
        ),
    }


# ---------------------------------------------------------------------------
# System penalties
# ---------------------------------------------------------------------------

def check_system_penalties(
    case_path: str,
    system_name: Optional[str] = None,
    penalty_names: Optional[list[str]] = None,
) -> dict:
    """
    Read system-level penalty settings.

    Args:
        case_path:     Absolute path to the SDDP case folder.
        system_name:   Filter to a single system by name. None = all systems.
        penalty_names: Subset of SYSTEM_PENALTY_NAMES to read.
                       Pass None (default) to read all.
                       Available names: RiskAversionCurvePenalty,
                       HydroPlant_PrimaryReserveViolationPenalty,
                       ThermalPlant_PrimaryReserveViolationPenalty.
    """
    names = _resolve_names(penalty_names, SYSTEM_PENALTY_NAMES)
    study = psr.factory.load_study(case_path)
    systems = study.get("System") or []

    results: list[dict] = []
    for sys_obj in systems:
        name = getattr(sys_obj, "name", None) or str(getattr(sys_obj, "code", "?"))
        if system_name and name.lower() != system_name.lower():
            continue

        penalties: dict[str, dict] = {}
        for prop in names:
            penalties[prop] = _build_static_entry(sys_obj, prop)

        flagged = [p for p, d in penalties.items()
                   if d["status"] in ("zero", "auto", "not_set")]

        results.append({
            "name":      name,
            "code":      getattr(sys_obj, "code", None),
            "penalties": penalties,
            "flagged":   flagged,
        })

    uncalibrated = [r["name"] for r in results if r["flagged"]]

    return {
        "case":          Path(case_path).name,
        "category":      "system",
        "queried":       names,
        "systems":       results,
        "total_systems": len(results),
        "uncalibrated":  uncalibrated,
        "summary": (
            f"{len(results)} system(s) read. "
            f"{len(uncalibrated)} have at least one queried penalty at zero/auto/not-set."
        ),
    }

"""
Penalty inspector — runs all penalty checks on a real SDDP case without any LLM.

Shows exactly what the agent would see when it reaches node_identificar_penalidades_entrada,
highlighting custom fixed values (the real calibration risk) vs. auto/zero/not_set.

Usage:
    python tests/inspect_penalties.py <case_path>

    # Filter to specific categories:
    python tests/inspect_penalties.py <case_path> --only hydro thermal

    # Show only entities with custom values:
    python tests/inspect_penalties.py <case_path> --custom-only
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT))

from psr.outputanalysismcp.penalty_functions import (
    HYDRO_PENALTY_NAMES,
    RENEWABLE_PENALTY_NAMES,
    STUDY_PENALTY_NAMES,
    SYSTEM_PENALTY_NAMES,
    THERMAL_PENALTY_NAMES,
    check_hydro_penalties,
    check_renewable_penalties,
    check_study_penalties,
    check_system_penalties,
    check_thermal_penalties,
)


# ---------------------------------------------------------------------------
# Status rendering
# ---------------------------------------------------------------------------

_STATUS_LABEL = {
    "custom":   "★ CUSTOM",   # fixed value set by user — review for calibration
    "auto":     "  auto   ",  # -1: SDDP calculates automatically — safe
    "zero":     "  zero   ",  # 0: penalty disabled
    "disabled": " disabled",  # 0 on a disabled_at_zero field
    "not_set":  " not_set ",  # property absent from the case
}

_STATUS_WARN = {"custom"}   # statuses that warrant a calibration review


def _status_line(name: str, entry: dict) -> str:
    status  = entry.get("status", "?")
    value   = entry.get("value")
    unit    = entry.get("unit", "")
    summary = entry.get("summary")          # renewable dynamic penalty
    label   = _STATUS_LABEL.get(status, f"  {status:7s}")

    if summary is not None:
        val_str = (
            f"mean={summary['mean']:.4g} min={summary['min']:.4g} "
            f"max={summary['max']:.4g} nonzero={summary['nonzero']}/{summary['total']}"
        )
    else:
        val_str = f"{value}" + (f" {unit}" if unit else "")

    warn = " ◄ review calibration" if status in _STATUS_WARN else ""
    return f"    {label}  {name:<45s}  {val_str}{warn}"


# ---------------------------------------------------------------------------
# Section printers
# ---------------------------------------------------------------------------

def _print_section_header(title: str) -> None:
    print(f"\n{'─'*70}")
    print(f"  {title}")
    print(f"{'─'*70}")


def _print_study(result: dict, custom_only: bool) -> None:
    _print_section_header("STUDY-LEVEL PENALTIES")
    penalties = result.get("penalties", {})
    shown = 0
    for name, entry in penalties.items():
        if custom_only and entry.get("status") != "custom":
            continue
        print(_status_line(name, entry))
        shown += 1
    if shown == 0:
        print("    (no entries to show)")
    print(f"\n  {result.get('summary', '')}")


def _print_plant_category(result: dict, custom_only: bool) -> None:
    category = result.get("category", "?").upper()
    items: list[dict] = result.get("plants") or result.get("systems") or []
    _print_section_header(
        f"{category} PENALTIES  "
        f"({result.get('total_plants') or result.get('total_systems', 0)} entities)"
    )

    shown_entities = 0
    for entry in items:
        penalties = entry.get("penalties", {})
        has_custom = any(d.get("status") == "custom" for d in penalties.values())

        if custom_only and not has_custom:
            continue

        shown_entities += 1
        custom_mark = " ★" if has_custom else ""
        print(f"\n  [{entry['name']}]{custom_mark}")
        for name, pen_entry in penalties.items():
            if custom_only and pen_entry.get("status") != "custom":
                continue
            print(_status_line(name, pen_entry))

    if shown_entities == 0:
        msg = "no entities with custom values" if custom_only else "no entities found"
        print(f"    ({msg})")

    print(f"\n  {result.get('summary', '')}")


def _print_summary_table(all_results: list[dict]) -> None:
    """Print a compact cross-category summary of custom-value counts."""
    print(f"\n{'═'*70}")
    print("  SUMMARY — entities with custom fixed penalty values (review for calibration)")
    print(f"{'═'*70}")

    total_custom = 0
    for result in all_results:
        cat = result.get("category", "?")
        items = result.get("plants") or result.get("systems") or []

        if items:
            custom_entities = [
                r["name"] for r in items
                if any(d.get("status") == "custom" for d in r.get("penalties", {}).values())
            ]
            if custom_entities:
                total_custom += len(custom_entities)
                print(f"  {cat:<12s}: {len(custom_entities)} entity/entities")
                for name in custom_entities:
                    entry = next(r for r in items if r["name"] == name)
                    custom_pens = [
                        f"{p}={d['value']}"
                        for p, d in entry.get("penalties", {}).items()
                        if d.get("status") == "custom"
                    ]
                    print(f"    • {name}: {', '.join(custom_pens)}")
        else:
            # Study-level
            penalties = result.get("penalties", {})
            custom_pens = {n: d["value"] for n, d in penalties.items() if d.get("status") == "custom"}
            if custom_pens:
                total_custom += len(custom_pens)
                print(f"  {cat:<12s}: {', '.join(f'{n}={v}' for n, v in custom_pens.items())}")

    if total_custom == 0:
        print("  No custom fixed values found — all penalties use auto/zero/not_set defaults.")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_ALL_CATEGORIES = ["study", "hydro", "thermal", "renewable", "system"]

_RUNNERS = {
    "study":     (check_study_penalties,     None),
    "hydro":     (check_hydro_penalties,     None),
    "thermal":   (check_thermal_penalties,   None),
    "renewable": (check_renewable_penalties, None),
    "system":    (check_system_penalties,    None),
}


def run(case_path: str, categories: list[str], custom_only: bool) -> None:
    print(f"\n{'═'*70}")
    print(f"  Penalty Inspector — {Path(case_path).name}")
    print(f"  Case: {case_path}")
    print(f"  Categories: {', '.join(categories)}")
    if custom_only:
        print("  Filter: custom values only")
    print(f"{'═'*70}")

    all_results: list[dict] = []

    for cat in categories:
        fn, _ = _RUNNERS[cat]
        print(f"\n  Loading {cat}...", end=" ", flush=True)
        try:
            result = fn(case_path)
            print("OK")
        except Exception as exc:
            print(f"ERROR: {exc}")
            continue

        all_results.append(result)

        if cat == "study":
            _print_study(result, custom_only)
        else:
            _print_plant_category(result, custom_only)

    if all_results:
        _print_summary_table(all_results)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect SDDP case penalty settings without LLM."
    )
    parser.add_argument("case_path", help="Absolute path to the SDDP case folder")
    parser.add_argument(
        "--only",
        nargs="+",
        choices=_ALL_CATEGORIES,
        default=_ALL_CATEGORIES,
        metavar="CATEGORY",
        help=f"Categories to inspect. Choices: {_ALL_CATEGORIES}",
    )
    parser.add_argument(
        "--custom-only",
        action="store_true",
        help="Show only entities/penalties with custom (user-set) fixed values",
    )
    args = parser.parse_args()

    run(args.case_path, args.only, args.custom_only)


if __name__ == "__main__":
    main()

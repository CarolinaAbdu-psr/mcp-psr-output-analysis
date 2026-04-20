"""
Initialize node: export HTML → CSV, load the results catalog, extract case metadata.

This node runs once per study_path. SessionMemory in __main__.py ensures it is
skipped on subsequent questions for the same case.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from psr.outputanalysismcp.case_information import extract_case_information as _extract_case_info
from ..utils import get_logger

_log = get_logger("initialize")

try:
    from sddp_html_to_csv import export_to_csv as _export_html  # type: ignore
except ImportError:
    _export_html = None  # type: ignore


def initialize(state: dict) -> dict:
    """
    Export SDDP HTML dashboard to CSV files and build the results catalog.

    Reads: state["study_path"]
    Writes: csv_catalog, case_metadata, results_dir, tool_results,
            traversal_history, conclusion_nodes, error
    """
    study_path = Path(state["study_path"])

    _log.debug("[init] study_path: %s", study_path)
    html_files = list(study_path.glob("SDDP.html"))
    if not html_files:
        _log.error("[init] no HTML file found in %s", study_path)
        return {
            "csv_catalog": {},
            "case_metadata": {},
            "results_dir": "",
            "tool_results": [],
            "traversal_history": [],
            "conclusion_nodes": [],
            "error": f"No HTML file found in {study_path}",
        }

    html_file = html_files[0]
    results_dir = study_path / "results"
    _log.debug("[init] HTML file: %s", html_file.name)

    # Export HTML → CSVs + _index.json
    if _export_html is not None:
        try:
            _log.debug("[init] exporting HTML → CSV in %s", results_dir)
            _export_html(str(html_file), output_dir=str(results_dir), verbose=False)
            _log.debug("[init] export complete")
        except Exception as exc:
            _log.error("[init] HTML export failed: %s", exc)
            return {
                "csv_catalog": {},
                "case_metadata": {},
                "results_dir": str(results_dir),
                "tool_results": [],
                "traversal_history": [],
                "conclusion_nodes": [],
                "error": f"HTML export failed: {exc}",
            }

    # Load _index.json catalog
    csv_catalog: dict[str, dict] = {}
    index_path = results_dir / "_index.json"
    if index_path.exists():
        index = json.loads(index_path.read_text(encoding="utf-8"))
        csv_catalog = {e["filename"]: e for e in index}
        _log.debug("[init] catalog loaded: %d files", len(csv_catalog))
    else:
        _log.warning("[init] _index.json not found — falling back to filename list")
        for f in results_dir.glob("*.csv"):
            csv_catalog[f.name] = {"filename": f.name, "chart_type": "unknown", "series": [], "rows": 0}
        _log.debug("[init] fallback catalog: %d files", len(csv_catalog))

    # Extract case metadata
    try:
        case_metadata = _extract_case_info(str(html_file))
        _log.debug("[init] case metadata keys: %s", list(case_metadata.keys()))
    except Exception as exc:
        _log.warning("[init] case metadata extraction failed: %s", exc)
        case_metadata = {"error": str(exc)}

    return {
        "csv_catalog": csv_catalog,
        "case_metadata": case_metadata,
        "results_dir": str(results_dir),
        "tool_results": [],
        "traversal_history": [],
        "conclusion_nodes": [],
        "error": None,
    }

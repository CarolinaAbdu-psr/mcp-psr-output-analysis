"""Shared utilities for PSR output analysis modules."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pandas as pd

# Knowledge-base directory — all modules resolve JSON entries from here.
_PACKAGE_ROOT = Path(__file__).parents[2]
KNOWLEDGE_DIR = _PACKAGE_ROOT / "sddp_knowledge"


def read_csv(folder: Path, filename: str) -> pd.DataFrame:
    """Read a results CSV, stripping BOM and header whitespace."""
    df = pd.read_csv(Path(folder) / filename, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df


def get_json_info(json_filename: str, target_id: str) -> str:
    """
    Return a formatted string for one knowledge entry from a JSON file.

    Args:
        json_filename: filename inside KNOWLEDGE_DIR, e.g. "policy.json"
        target_id:     the "id" field of the entry to retrieve

    Returns a markdown-style block ready to embed in a report.
    If the file or ID is not found, returns an informative error string.
    """
    file_path = KNOWLEDGE_DIR / json_filename
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        entry = next((item for item in data if item.get("id") == target_id), None)
        if not entry:
            return f"[Knowledge not found: id '{target_id}' in {json_filename}]"

        refs = "\n".join(
            f"  - {r['title']} ({r['url']})"
            for r in entry.get("references", [])
        )
        return (
            f"### {entry['title']}\n\n"
            f"{entry['content']}\n\n"
            f"References:\n{refs}\n" if refs else
            f"### {entry['title']}\n\n"
            f"{entry['content']}\n"
        )

    except FileNotFoundError:
        return f"[Knowledge file not found: {json_filename}]"
    except json.JSONDecodeError:
        return f"[Invalid JSON in knowledge file: {json_filename}]"

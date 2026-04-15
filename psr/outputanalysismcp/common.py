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


def read_csv_path(file_path: str | Path) -> pd.DataFrame:
    """Read any CSV by full path, stripping BOM and header whitespace."""
    df = pd.read_csv(Path(file_path), encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    return df



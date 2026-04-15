"""
case_information.py
-------------------
Extract structured case metadata from an SDDP HTML dashboard.

The "Information" tab (Información / Information / Informação) holds several
HTML tables with case metadata: directory summary, model/environment info,
run parameters, system dimensions, and non-convexity counts.

Public API
----------
extract_case_information(html_path: str) -> dict
    Parse the HTML file and return a nested dict with all case metadata.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path


# ---------------------------------------------------------------------------
# Step 1 — find the tab-pane ID for the "Information" nav item
# ---------------------------------------------------------------------------

_INFO_ICON_RE = re.compile(
    # Match <a ... data-bs-target="#<ID>" ...> ... <span ... icon-name="info" ...>
    r'data-bs-target="#([^"]+)"[^>]*>(?:[^<]|<(?!span))*<span\s[^>]*icon-name="info"',
    re.DOTALL,
)


def _find_info_tab_id(html: str) -> str | None:
    """Return the tab-pane id for the 'info' nav link, or None."""
    m = _INFO_ICON_RE.search(html)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Step 2 — extract the raw inner HTML of that tab-pane div
# ---------------------------------------------------------------------------

class _DivExtractor(HTMLParser):
    """Capture the inner HTML of the first <div id="<target_id>"> found."""

    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=False)
        self._target   = target_id
        self._depth    = 0          # nesting depth once we start capturing
        self._buf: list[str] = []
        self.result: str | None = None

    # ---- public interface --------------------------------------------------

    def feed_all(self, html: str) -> str | None:
        self.feed(html)
        return self.result

    # ---- internal ----------------------------------------------------------

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_map = dict(attrs)
        if self._depth == 0:
            if tag == "div" and attr_map.get("id") == self._target:
                self._depth = 1          # start capturing — don't include wrapper
                return
        else:
            if tag in {"div", "table", "thead", "tbody", "tr", "td", "th",
                       "h1", "h2", "h3", "p", "strong", "br", "ul", "li",
                       "a", "span", "em"}:
                if tag == "div":
                    self._depth += 1
                self._buf.append(self._rebuild(tag, attrs))

    def handle_endtag(self, tag: str) -> None:
        if self._depth == 0:
            return
        if tag == "div":
            self._depth -= 1
            if self._depth == 0:
                self.result = "".join(self._buf)
                return
        if self._depth > 0:
            self._buf.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._depth > 0:
            self._buf.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._depth > 0:
            self._buf.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._depth > 0:
            self._buf.append(f"&#{name};")

    @staticmethod
    def _rebuild(tag: str, attrs: list) -> str:
        parts = [f"<{tag}"]
        for k, v in attrs:
            parts.append(f' {k}="{v}"' if v is not None else f" {k}")
        parts.append(">")
        return "".join(parts)


# ---------------------------------------------------------------------------
# Step 3 — parse the inner HTML into structured data
# ---------------------------------------------------------------------------

class _ContentParser(HTMLParser):
    """
    Walk the tab-pane inner HTML and produce a list of sections, each of the form:
        {"heading": str, "table": list[list[str]]}

    A section heading comes from <h1> or <h2>.
    A table is a list of rows; each row is a list of cell strings.
    Sections without a heading use the empty string.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[dict] = []
        self._current_heading: str = ""
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: str | None = None
        self._in_heading = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = True
            self._current_heading = ""
        elif tag == "table":
            self._current_table = []
        elif tag == "tr" and self._current_table is not None:
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3"}:
            self._in_heading = False
        elif tag == "table" and self._current_table is not None:
            self.sections.append({
                "heading": self._current_heading,
                "table": self._current_table,
            })
            self._current_table = None
            self._current_heading = ""
        elif tag == "tr" and self._current_row is not None:
            if self._current_table is not None:
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append(self._current_cell.strip())
            self._current_cell = None

    def handle_data(self, data: str) -> None:
        if self._in_heading:
            self._current_heading += data
        elif self._current_cell is not None:
            self._current_cell += data


# ---------------------------------------------------------------------------
# Step 4 — convert sections into a typed dict
# ---------------------------------------------------------------------------

def _rows_to_kv(rows: list[list[str]], skip_header: bool = True) -> dict[str, str]:
    """Convert a two-column key-value table into a dict, optionally skipping row 0."""
    start = 1 if skip_header else 0
    return {r[0]: r[1] for r in rows[start:] if len(r) >= 2}


def _header_row_to_dict(rows: list[list[str]]) -> dict[str, str]:
    """
    Convert a table whose first row is the header and has one data row.
    Returns {header[i]: value[i]}.
    """
    if len(rows) < 2:
        return {}
    headers = rows[0]
    values  = rows[1]
    return {h: v for h, v in zip(headers, values)}


def _sections_to_dict(sections: list[dict]) -> dict:
    """
    Map parsed sections to a typed result dict using heuristics on the heading
    text and table shape.
    """
    result: dict = {}

    for sec in sections:
        heading = sec["heading"].strip()
        rows    = sec["table"]

        if not rows:
            continue

        n_cols = max(len(r) for r in rows)

        # ── Case summary (≥3 header columns in row 0) ───────────────────────
        if n_cols >= 3 and not result.get("case_summary"):
            result["case_summary"] = _header_row_to_dict(rows)
            continue

        # ── Model / environment (≥4 header columns) ─────────────────────────
        if n_cols >= 4 and not result.get("model_info"):
            result["model_info"] = _header_row_to_dict(rows)
            continue

        # ── Case title (1-column table with "Título" header) ─────────────────
        if n_cols == 1 and len(rows) >= 2:
            result["case_title"] = rows[1][0] if rows[1] else ""
            continue

        # ── Key-value tables (2 columns) ─────────────────────────────────────
        if n_cols == 2:
            kv = _rows_to_kv(rows, skip_header=True)
            if not result.get("run_parameters"):
                result["run_parameters"] = kv
            elif not result.get("dimensions"):
                result["dimensions"] = kv
            elif not result.get("non_convexities"):
                result["non_convexities"] = kv
            else:
                # Extra tables go under their heading or a generic key
                key = re.sub(r"\s+", "_", heading.lower()) or f"extra_{len(result)}"
                result[key] = kv

    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_case_information(html_path: str) -> dict:
    """
    Parse the SDDP dashboard HTML and return structured case metadata.

    Parameters
    ----------
    html_path : str
        Absolute path to the SDDP .html dashboard file.

    Returns
    -------
    dict with keys (present when found):
        case_summary    – directory name, path, execution status
        model_info      – model, user, version, ID, architecture
        case_title      – case title string
        run_parameters  – execution options (stages, dates, series, etc.)
        dimensions      – element counts (hydro plants, buses, etc.)
        non_convexities – non-convexity counts per type
    """
    html = Path(html_path).read_text(encoding="utf-8", errors="replace")

    # 1. Locate the info tab ID
    tab_id = _find_info_tab_id(html)
    if tab_id is None:
        return {"error": "Could not locate the Information tab in the HTML."}

    # 2. Extract the raw inner HTML of that tab pane
    extractor = _DivExtractor(tab_id)
    inner_html = extractor.feed_all(html)
    if inner_html is None:
        return {"error": f"Tab pane #{tab_id} found in nav but content div is missing."}

    # 3. Parse headings + tables
    parser = _ContentParser()
    parser.feed(inner_html)

    # 4. Convert to typed dict
    data = _sections_to_dict(parser.sections)
    data["_tab_id"] = tab_id   # handy for debugging
    return data

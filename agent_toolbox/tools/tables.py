"""HTML table extraction tools for AI agents (Day 4).

Agents often need the data locked inside a page's tables — prices,
results, schedules, vacancy lists — but a plain-text scrape flattens
tables into unreadable lines. extract_tables pulls every HTML table
out of a page as structured JSON (header + rows) using only the stdlib
HTML parser, so an agent can filter, sort, and compute on the data
instead of guessing at flattened text.
"""
from __future__ import annotations

import urllib.request
from html.parser import HTMLParser

from ..registry import registry


def _fetch_html(url: str) -> str:
    """Fetch a page and return its raw HTML.

    Kept as a separate function so tests can stub it without touching
    the network.
    """
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    request = urllib.request.Request(
        url, headers={"User-Agent": "agent-toolbox/0.1 (+https://github.com/dodonquixote/agent-toolbox)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    """Collapse whitespace in cell text to single spaces."""
    return " ".join(text.split())


class _TableParser(HTMLParser):
    """Collect every <table> as {"header": [...|None], "rows": [[...]]}.

    A table's header is its first row when every cell in that row is a
    <th>; otherwise header is None and every row is data. Nested tables
    are recorded as separate tables. Rows with no cells are dropped.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._stack: list[dict] = []  # one dict per open <table>

    def _current(self) -> dict | None:
        return self._stack[-1] if self._stack else None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._stack.append({"rows": [], "row": None, "cell": None,
                                "cell_header": False})
        table = self._current()
        if table is None:
            return
        if tag == "tr":
            table["row"] = []
        elif tag in ("td", "th"):
            if table["row"] is not None:
                table["cell"] = []
                table["cell_header"] = tag == "th"
        elif tag == "br":
            if table["cell"] is not None:
                table["cell"].append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            table = self._stack.pop()
            rows = [row for row in table["rows"] if row["cells"]]
            if not rows:
                return
            header = None
            data_rows = rows
            if all(cell[1] for cell in rows[0]["cells"]):
                header = [cell[0] for cell in rows[0]["cells"]]
                data_rows = rows[1:]
            self.tables.append({
                "header": header,
                "rows": [[cell[0] for cell in row["cells"]] for row in data_rows],
            })
            return
        table = self._current()
        if table is None:
            return
        if tag in ("td", "th"):
            if table["cell"] is not None and table["row"] is not None:
                table["row"].append((_clean("".join(table["cell"])),
                                     table["cell_header"]))
                table["cell"] = None
        elif tag == "tr":
            if table["row"] is not None:
                table["rows"].append({"cells": table["row"]})
                table["row"] = None

    def handle_data(self, data: str) -> None:
        table = self._current()
        if table is not None and table["cell"] is not None:
            table["cell"].append(data)


def extract_tables_from_html(html: str) -> list[dict]:
    """Return every table in `html` as {"header": [...|None], "rows": [[...]]}."""
    parser = _TableParser()
    parser.feed(html)
    return parser.tables


@registry.tool(
    name="extract_tables",
    description=("Extract the HTML tables from a web page as structured "
                 "JSON rows (header + rows) that an agent can filter, "
                 "sort, and compute on, instead of flattened text."),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The http(s) URL of the page to read tables from."},
            "max_tables": {"type": "integer",
                           "description": "Maximum tables to return (default 10).",
                           "default": 10},
        },
        "required": ["url"],
    },
    tags=["extraction", "web"],
)
def extract_tables(url: str, max_tables: int = 10) -> dict:
    try:
        html = _fetch_html(url)
        tables = extract_tables_from_html(html)
    except Exception as exc:  # noqa: BLE001 - any fetch/parse failure = error status
        return {"url": url, "status": "error", "tables": [],
                "table_count": 0,
                "error": f"{type(exc).__name__}: {exc}"}
    tables = tables[:max_tables]
    return {"url": url, "status": "ok", "tables": tables,
            "table_count": len(tables), "error": None}

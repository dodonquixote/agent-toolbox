"""Page-change monitoring tools for AI agents (Day 3).

Agents are usually asked to "keep an eye on" a page — a price, a changelog,
a vacancy listing — but they have no memory between runs, so a change goes
unnoticed until a human re-checks. watch_page fixes that: it fetches a
page's clean text (reusing the Day 1 fetch machinery), stores a snapshot
in a small SQLite database, and on later checks reports exactly which
lines were added or removed since the last snapshot. The agent itself
needs no memory — the tool keeps the continuity.
"""
from __future__ import annotations

import difflib
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ..registry import registry
from .web import fetch_url

ENV_STATE_DB = "AGENT_TOOLBOX_STATE"
DEFAULT_STATE_DIR = Path.home() / ".agent-toolbox"
DEFAULT_STATE_DB = DEFAULT_STATE_DIR / "state.db"


def state_path() -> Path:
    """Return the SQLite state-db path.

    Honours $AGENT_TOOLBOX_STATE when set, otherwise defaults to
    ~/.agent-toolbox/state.db. The db lives outside the project, so
    snapshots are never committed to a repo.
    """
    override = os.environ.get(ENV_STATE_DB)
    if override:
        return Path(override).expanduser()
    return DEFAULT_STATE_DB


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the state db (creating it and its schema if needed)."""
    path = db_path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS page_snapshots ("
        "  url TEXT PRIMARY KEY,"
        "  title TEXT,"
        "  text TEXT NOT NULL,"
        "  checked_at TEXT NOT NULL"
        ")"
    )
    return conn


def diff_lines(old_text: str, new_text: str) -> dict[str, list[str]]:
    """Line-level diff between two snapshots.

    Returns the lines only in the new text ("added") and only in the
    old text ("removed"), in order. Unchanged lines are not reported.
    """
    added: list[str] = []
    removed: list[str] = []
    for line in difflib.ndiff(old_text.splitlines(), new_text.splitlines()):
        if line.startswith("+ "):
            added.append(line[2:])
        elif line.startswith("- "):
            removed.append(line[2:])
    return {"added": added, "removed": removed}


def get_snapshot(url: str, db_path: Path | None = None) -> dict | None:
    """Return the stored snapshot for `url`, or None if never watched."""
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT title, text, checked_at FROM page_snapshots WHERE url = ?",
            (url,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"url": url, "title": row[0], "text": row[1], "checked_at": row[2]}


def _fetch_page(url: str, max_chars: int) -> dict:
    """Fetch a page and return fetch_url's result dict.

    Kept as a separate function so tests can stub it without touching
    the network.
    """
    return fetch_url(url, max_chars=max_chars)


def _store_snapshot(url: str, title: str | None, text: str,
                    checked_at: str, db_path: Path | None = None) -> None:
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO page_snapshots (url, title, text, checked_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(url) DO UPDATE SET"
            "   title = excluded.title,"
            "   text = excluded.text,"
            "   checked_at = excluded.checked_at",
            (url, title, text, checked_at),
        )
        conn.commit()
    finally:
        conn.close()


@registry.tool(
    name="watch_page",
    description=("Monitor a web page for changes: fetch its clean text, "
                 "compare it with the snapshot stored from the previous "
                 "check, and report exactly which lines were added or "
                 "removed. The first check just records the snapshot."),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The http(s) URL to watch."},
            "max_chars": {"type": "integer",
                          "description": "Maximum characters of page text to compare (default 20000).",
                          "default": 20000},
        },
        "required": ["url"],
    },
    tags=["monitoring", "web"],
)
def watch_page(url: str, max_chars: int = 20000) -> dict:
    try:
        page = _fetch_page(url, max_chars)
    except Exception as exc:  # noqa: BLE001 - any fetch failure = error status
        return {"url": url, "status": "error",
                "changed": False, "added": [], "removed": [],
                "title": None, "checked_at": None,
                "previous_checked_at": None,
                "error": f"{type(exc).__name__}: {exc}"}
    text = page.get("text") or ""
    checked_at = datetime.now(timezone.utc).isoformat()
    previous = get_snapshot(url)
    _store_snapshot(url, page.get("title"), text, checked_at)
    if previous is None:
        return {"url": url, "status": "first_seen",
                "changed": False, "added": [], "removed": [],
                "title": page.get("title"), "checked_at": checked_at,
                "previous_checked_at": None, "line_count": len(text.splitlines()),
                "error": None}
    diff = diff_lines(previous["text"], text)
    changed = bool(diff["added"] or diff["removed"])
    return {"url": url, "status": "changed" if changed else "unchanged",
            "changed": changed, "added": diff["added"],
            "removed": diff["removed"],
            "title": page.get("title"), "checked_at": checked_at,
            "previous_checked_at": previous["checked_at"],
            "line_count": len(text.splitlines()), "error": None}

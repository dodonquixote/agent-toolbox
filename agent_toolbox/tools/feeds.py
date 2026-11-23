"""Feed digest tools for AI agents (Day 4).

Agents that follow a blog, changelog, or job board re-read the same feed
every run and re-report items they already saw — or worse, re-act on
them. feed_digest fixes that: it fetches an RSS/Atom feed (stdlib
xml.etree only), remembers every item id it has already shown in the
same SQLite state db as watch_page, and returns only the items that are
new since the last check. The agent itself needs no memory — the tool
keeps the dedupe state.
"""
from __future__ import annotations

import hashlib
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from ..registry import registry
from .watch import state_path


def _fetch_feed(url: str) -> str:
    """Fetch a feed URL and return its raw XML text.

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


def _local(tag: str) -> str:
    """Strip an XML namespace prefix from a tag name."""
    return tag.rsplit("}", 1)[-1]


def _child_text(elem: ET.Element, name: str) -> str | None:
    """Text of the first child element with local name `name`, or None."""
    for child in elem:
        if _local(child.tag) == name:
            return (child.text or "").strip() or None
    return None


def _item_id(item: dict) -> str:
    """Stable id for a feed item: guid/id, else link, else a hash."""
    if item.get("id"):
        return item["id"]
    if item.get("link"):
        return item["link"]
    seed = (item.get("title") or "") + "|" + (item.get("published") or "")
    return "hash:" + hashlib.sha1(seed.encode("utf-8")).hexdigest()


def parse_feed(xml_text: str) -> dict:
    """Parse an RSS 2.0 or Atom feed into a title plus a list of items.

    Each item has keys ``id``, ``title``, ``link``, ``published`` and
    ``summary`` (any of which may be None when the feed omits it).
    Raises xml.etree.ElementTree.ParseError on malformed XML.
    """
    root = ET.fromstring(xml_text)
    kind = _local(root.tag)
    title: str | None = None
    items: list[dict] = []

    if kind == "rss":
        channel = next((c for c in root if _local(c.tag) == "channel"), root)
        title = _child_text(channel, "title")
        entry_elems = [c for c in channel if _local(c.tag) == "item"]
        for entry in entry_elems:
            items.append({
                "id": _child_text(entry, "guid"),
                "title": _child_text(entry, "title"),
                "link": _child_text(entry, "link"),
                "published": _child_text(entry, "pubDate"),
                "summary": _child_text(entry, "description"),
            })
    elif kind == "feed":  # Atom
        title = _child_text(root, "title")
        for entry in (c for c in root if _local(c.tag) == "entry"):
            link = None
            for child in entry:
                if _local(child.tag) == "link":
                    href = child.get("href")
                    rel = child.get("rel") or "alternate"
                    if href and (link is None or rel == "alternate"):
                        link = href
            items.append({
                "id": _child_text(entry, "id"),
                "title": _child_text(entry, "title"),
                "link": link,
                "published": (_child_text(entry, "published")
                              or _child_text(entry, "updated")),
                "summary": (_child_text(entry, "summary")
                            or _child_text(entry, "content")),
            })
    else:
        raise ValueError(f"unsupported feed format: root element <{kind}>")

    for item in items:
        item["id"] = _item_id(item)
    return {"title": title, "items": items}


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the state db (creating it and the feed_seen table if needed)."""
    path = db_path or state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS feed_seen ("
        "  feed_url TEXT NOT NULL,"
        "  item_id TEXT NOT NULL,"
        "  seen_at TEXT NOT NULL,"
        "  PRIMARY KEY (feed_url, item_id)"
        ")"
    )
    return conn


def seen_ids(feed_url: str, db_path: Path | None = None) -> set[str]:
    """Return the item ids already shown for `feed_url`."""
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT item_id FROM feed_seen WHERE feed_url = ?", (feed_url,)).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _mark_seen(feed_url: str, item_ids: list[str],
               db_path: Path | None = None) -> None:
    seen_at = datetime.now(timezone.utc).isoformat()
    conn = _connect(db_path)
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO feed_seen (feed_url, item_id, seen_at)"
            " VALUES (?, ?, ?)",
            [(feed_url, item_id, seen_at) for item_id in item_ids],
        )
        conn.commit()
    finally:
        conn.close()


@registry.tool(
    name="feed_digest",
    description=("Read an RSS/Atom feed and return only the items you have "
                 "not seen before. Seen item ids are remembered in a "
                 "persistent SQLite database, so repeats are never "
                 "reported twice — across runs and across restarts."),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The http(s) URL of the RSS/Atom feed."},
            "max_items": {"type": "integer",
                          "description": "Maximum new items to return (default 50).",
                          "default": 50},
        },
        "required": ["url"],
    },
    tags=["monitoring", "deduplication", "web"],
)
def feed_digest(url: str, max_items: int = 50) -> dict:
    try:
        xml_text = _fetch_feed(url)
        feed = parse_feed(xml_text)
    except Exception as exc:  # noqa: BLE001 - any fetch/parse failure = error status
        return {"feed_url": url, "title": None, "status": "error",
                "new_items": [], "total_items": 0, "new_count": 0,
                "error": f"{type(exc).__name__}: {exc}"}
    seen = seen_ids(url)
    new_items = [item for item in feed["items"] if item["id"] not in seen]
    _mark_seen(url, [item["id"] for item in feed["items"]])
    new_items = new_items[:max_items]
    return {"feed_url": url, "title": feed["title"], "status": "ok",
            "new_items": new_items, "total_items": len(feed["items"]),
            "new_count": len(new_items), "error": None}

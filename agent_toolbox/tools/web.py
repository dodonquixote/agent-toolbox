"""Web tools for AI agents (Day 1).

fetch_url downloads a page and returns clean, readable plain text that an
LLM can consume directly: scripts, styles and navigation chrome are
stripped, entities are unescaped and whitespace is collapsed.
"""
from __future__ import annotations

import urllib.request
from html.parser import HTMLParser

from ..registry import registry

_SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}
_BLOCK_TAGS = {"p", "div", "section", "article", "li", "tr", "h1", "h2",
               "h3", "h4", "h5", "h6", "br", "blockquote", "pre"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.title: str | None = None
        self._in_title = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if self._skip_depth:
            return
        self._parts.append(data)

    def text(self) -> str:
        lines = (" ".join(line.split()) for line in "".join(self._parts).splitlines())
        return "\n".join(line for line in lines if line)


def extract_text(html: str) -> tuple[str | None, str]:
    """Return (title, readable_text) for an HTML document."""
    parser = _TextExtractor()
    parser.feed(html)
    return (parser.title.strip() if parser.title else None), parser.text()


@registry.tool(
    name="fetch_url",
    description=("Fetch a web page and return its main content as clean plain "
                 "text (title + body) that an LLM can read directly."),
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The http(s) URL to fetch."},
            "max_chars": {"type": "integer",
                          "description": "Maximum characters of text to return (default 8000).",
                          "default": 8000},
        },
        "required": ["url"],
    },
    tags=["web"],
)
def fetch_url(url: str, max_chars: int = 8000) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ValueError("url must start with http:// or https://")
    request = urllib.request.Request(
        url, headers={"User-Agent": "agent-toolbox/0.1 (+https://github.com/dodonquixote/agent-toolbox)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        content_type = response.headers.get_content_type()
        raw = response.read()
    if content_type not in ("text/html", "application/xhtml+xml"):
        return {"url": url, "title": None,
                "text": raw.decode("utf-8", errors="replace")[:max_chars],
                "truncated": len(raw) > max_chars}
    title, text = extract_text(raw.decode("utf-8", errors="replace"))
    return {"url": url, "title": title, "text": text[:max_chars],
            "truncated": len(text) > max_chars}

"""Citation verification tools for AI agents (Day 2).

LLMs routinely invent plausible-looking citations. verify_citations
fact-checks them: given a list of {claim, url} pairs, it fetches each
source (reusing the Day 1 fetch machinery) and scores whether the source
text actually supports the claim, via content-term overlap. Each citation
gets a verdict — supported / weak / unsupported / unreachable — so an
agent can drop or flag shaky sources before showing them to a user.
"""
from __future__ import annotations

import re

from ..registry import registry
from .web import fetch_url

# Small stopword set: words that carry no checkable content, so they must
# not count toward (or against) a claim's support score.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "by", "at", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "has", "have", "had", "it", "its", "this", "that",
    "these", "those", "which", "who", "whom", "what", "when", "where",
    "why", "how", "not", "no", "nor", "so", "such", "than", "then",
    "there", "here", "into", "over", "under", "between", "about", "after",
    "before", "during", "per", "via", "also", "more", "most", "other",
    "some", "any", "all", "each", "can", "could", "will", "would",
    "should", "may", "might", "must", "shall", "do", "does", "did",
    "i", "you", "he", "she", "we", "they", "his", "her", "their", "our",
    "your", "my", "me", "him", "us", "them",
}

_WORD_RE = re.compile(r"[a-z0-9]+")

# Score thresholds for the verdicts.
SUPPORTED_AT = 0.6
WEAK_AT = 0.3


def extract_content_terms(text: str) -> list[str]:
    """Return the distinct content-bearing terms of a text, in order.

    Lowercased alphanumeric words, minus stopwords and words shorter
    than three characters (which are usually abbreviations or noise).
    """
    terms: list[str] = []
    for word in _WORD_RE.findall(text.lower()):
        if len(word) < 3 or word in _STOPWORDS:
            continue
        if word not in terms:
            terms.append(word)
    return terms


def score_support(claim: str, source_text: str) -> dict:
    """Score how well `source_text` supports `claim`.

    Returns the overlap score (fraction of the claim's content terms
    found in the source), plus the matched and missing terms.
    """
    claim_terms = extract_content_terms(claim)
    if not claim_terms:
        return {"score": 0.0, "matched_terms": [], "missing_terms": [],
                "claim_terms": []}
    source_terms = set(extract_content_terms(source_text))
    matched = [t for t in claim_terms if t in source_terms]
    missing = [t for t in claim_terms if t not in source_terms]
    return {"score": len(matched) / len(claim_terms),
            "matched_terms": matched, "missing_terms": missing,
            "claim_terms": claim_terms}


def verdict_for(score: float) -> str:
    """Map an overlap score to a verdict."""
    if score >= SUPPORTED_AT:
        return "supported"
    if score >= WEAK_AT:
        return "weak"
    return "unsupported"


def _fetch_source(url: str, max_chars: int) -> dict:
    """Fetch a source page and return fetch_url's result dict.

    Kept as a separate function so tests can stub it without touching
    the network.
    """
    return fetch_url(url, max_chars=max_chars)


def check_citation(claim: str, url: str, max_chars: int = 20000) -> dict:
    """Check one {claim, url} pair and return its verdict dict."""
    try:
        page = _fetch_source(url, max_chars)
    except Exception as exc:  # noqa: BLE001 - any fetch failure = unreachable
        return {"claim": claim, "url": url, "verdict": "unreachable",
                "score": 0.0, "matched_terms": [], "missing_terms": [],
                "source_title": None, "error": f"{type(exc).__name__}: {exc}"}
    result = score_support(claim, page.get("text") or "")
    return {"claim": claim, "url": url,
            "verdict": verdict_for(result["score"]),
            "score": round(result["score"], 3),
            "matched_terms": result["matched_terms"],
            "missing_terms": result["missing_terms"],
            "source_title": page.get("title"), "error": None}


@registry.tool(
    name="verify_citations",
    description=("Fact-check an LLM's citations: for each {claim, url} pair, "
                 "fetch the cited source and score whether its text actually "
                 "supports the claim. Returns per-citation verdicts "
                 "(supported / weak / unsupported / unreachable) plus a "
                 "summary count."),
    parameters={
        "type": "object",
        "properties": {
            "citations": {
                "type": "array",
                "description": "List of {claim, url} objects to check.",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string",
                                  "description": "The statement the source is cited for."},
                        "url": {"type": "string",
                                "description": "The http(s) URL cited as the source."},
                    },
                    "required": ["claim", "url"],
                },
            },
            "max_chars": {"type": "integer",
                          "description": "Maximum source characters fetched per URL (default 20000).",
                          "default": 20000},
        },
        "required": ["citations"],
    },
    tags=["verification", "web"],
)
def verify_citations(citations: list[dict], max_chars: int = 20000) -> dict:
    results = []
    for item in citations:
        if not isinstance(item, dict) or "claim" not in item or "url" not in item:
            raise ValueError("each citation must be an object with 'claim' and 'url'")
        results.append(check_citation(str(item["claim"]), str(item["url"]),
                                      max_chars=max_chars))
    summary = {"total": len(results)}
    for verdict in ("supported", "weak", "unsupported", "unreachable"):
        summary[verdict] = sum(1 for r in results if r["verdict"] == verdict)
    return {"results": results, "summary": summary}

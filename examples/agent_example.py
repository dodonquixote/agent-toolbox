"""Day 5 example: a realistic chained workflow, no API key needed.

An agent that (1) watches a project's changelog page for new releases
and (2) fact-checks a claim about the new release against the page —
the two tools feeding each other through the registry.

The page fetches are stubbed with local text so the example runs
offline; the state db is a throwaway temp file, so re-running it
starts fresh. Swap the stubs for real URLs (and drop the temp db) to
run it live.

Run:  python examples/agent_example.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep the example's state out of the user's real state db.
os.environ["AGENT_TOOLBOX_STATE"] = str(
    Path(tempfile.mkdtemp()) / "agent_example_state.db")

from agent_toolbox import registry  # noqa: E402
from agent_toolbox.tools import citations, watch  # noqa: E402

CHANGELOG_URL = "https://example.test/project/changelog"

CHANGELOG_V1 = """\
Project Changelog
Version 2.3
- Faster startup
- Dark mode
"""

CHANGELOG_V2 = """\
Project Changelog
Version 2.4
- Faster startup
- Dark mode
- Offline sync
"""

# What the (stubbed) page looks like on each check.
PAGES = [CHANGELOG_V1, CHANGELOG_V2]


def fake_fetch_page(url, max_chars):
    """Stand in for the network: return the next changelog version."""
    text = PAGES.pop(0) if PAGES else CHANGELOG_V2
    return {"title": "Project Changelog", "text": text}


def fake_fetch_source(url, max_chars):
    """Stand in for the network: the citation source is the new page."""
    return {"title": "Project Changelog", "text": CHANGELOG_V2}


def main() -> None:
    print("Registered tools:", ", ".join(registry.names()))

    with mock.patch.object(watch, "_fetch_page", side_effect=fake_fetch_page), \
            mock.patch.object(citations, "_fetch_source",
                              side_effect=fake_fetch_source):
        # Step 1: first check just records the snapshot.
        first = registry.call("watch_page", {"url": CHANGELOG_URL})
        print(f"\n1) watch_page, first check: status={first['status']}")

        # Step 2: the page changed — report exactly what is new.
        second = registry.call("watch_page", {"url": CHANGELOG_URL})
        print(f"2) watch_page, second check: status={second['status']}")
        print(f"   added lines: {second['added']}")

        # Step 3: a claim about the change — verify it against the page
        # before repeating it to anyone.
        claim = "Version 2.4 of the project adds offline sync."
        verdict = registry.call("verify_citations", {
            "citations": [{"claim": claim, "url": CHANGELOG_URL}]})
        result = verdict["results"][0]
        print(f"3) verify_citations: {result['verdict']} "
              f"(score {result['score']:.2f}) for claim: {claim!r}")

    print("\nChained workflow done — the agent saw the change, then "
          "checked the claim about it, with no API key and no memory "
          "of its own: the tools kept the state.")


if __name__ == "__main__":
    main()

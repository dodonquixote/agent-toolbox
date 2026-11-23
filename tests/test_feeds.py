import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_toolbox import registry
from agent_toolbox.tools import feeds
from agent_toolbox.tools.feeds import parse_feed, seen_ids

FEED_URL = "https://example.test/blog.xml"

RSS_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Example Blog</title>
    <item>
      <title>First post</title>
      <link>https://example.test/1</link>
      <guid>post-1</guid>
      <pubDate>Mon, 23 Nov 2026 08:00:00 GMT</pubDate>
      <description>Intro post.</description>
    </item>
    <item>
      <title>Second post</title>
      <link>https://example.test/2</link>
      <guid>post-2</guid>
      <pubDate>Tue, 24 Nov 2026 08:00:00 GMT</pubDate>
      <description>Follow-up post.</description>
    </item>
  </channel>
</rss>"""

RSS_FEED_WITH_NEW_ITEM = RSS_FEED.replace(
    "</channel>",
    """  <item>
      <title>Third post</title>
      <link>https://example.test/3</link>
      <guid>post-3</guid>
      <pubDate>Wed, 25 Nov 2026 08:00:00 GMT</pubDate>
      <description>New post.</description>
    </item>
  </channel>""")

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title>Atom entry</title>
    <link href="https://example.test/atom-1"/>
    <id>urn:example:atom-1</id>
    <updated>2026-11-23T08:00:00Z</updated>
    <summary>An Atom entry.</summary>
  </entry>
</feed>"""

RSS_NO_GUID = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>No Guids</title>
  <item><title>Linked only</title><link>https://example.test/only</link></item>
</channel></rss>"""


class FeedDigestTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "state.db"
        self._state_patch = mock.patch.object(
            feeds, "state_path", return_value=self.db)
        self._state_patch.start()
        self.addCleanup(self._state_patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def _run_with_stub(self, xml_text, url=FEED_URL):
        with mock.patch.object(feeds, "_fetch_feed", return_value=xml_text):
            return feeds.feed_digest(url)

    def test_first_run_returns_all_items(self):
        result = self._run_with_stub(RSS_FEED)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["title"], "Example Blog")
        self.assertEqual(result["total_items"], 2)
        self.assertEqual(result["new_count"], 2)
        self.assertEqual([i["title"] for i in result["new_items"]],
                         ["First post", "Second post"])
        self.assertEqual(result["new_items"][0]["id"], "post-1")
        self.assertEqual(result["new_items"][0]["link"], "https://example.test/1")
        self.assertIsNone(result["error"])

    def test_second_run_returns_nothing_new(self):
        self._run_with_stub(RSS_FEED)
        result = self._run_with_stub(RSS_FEED)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["new_count"], 0)
        self.assertEqual(result["new_items"], [])
        self.assertEqual(result["total_items"], 2)

    def test_only_new_items_returned_on_update(self):
        self._run_with_stub(RSS_FEED)
        result = self._run_with_stub(RSS_FEED_WITH_NEW_ITEM)
        self.assertEqual(result["total_items"], 3)
        self.assertEqual(result["new_count"], 1)
        self.assertEqual(result["new_items"][0]["title"], "Third post")

    def test_seen_state_is_persistent_per_feed(self):
        other = "https://example.test/other.xml"
        self._run_with_stub(RSS_FEED)
        result = self._run_with_stub(RSS_FEED, url=other)
        # Same item ids, but a different feed URL is a separate stream.
        self.assertEqual(result["new_count"], 2)
        self.assertEqual(seen_ids(FEED_URL), {"post-1", "post-2"})

    def test_atom_feed_parsed(self):
        result = self._run_with_stub(ATOM_FEED)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["title"], "Example Atom")
        self.assertEqual(result["new_count"], 1)
        item = result["new_items"][0]
        self.assertEqual(item["id"], "urn:example:atom-1")
        self.assertEqual(item["link"], "https://example.test/atom-1")
        self.assertEqual(item["published"], "2026-11-23T08:00:00Z")

    def test_link_used_as_id_when_no_guid(self):
        feed = parse_feed(RSS_NO_GUID)
        self.assertEqual(feed["items"][0]["id"], "https://example.test/only")

    def test_malformed_xml_returns_error(self):
        result = self._run_with_stub("<rss><channel><item>")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["new_items"], [])
        self.assertIn("ParseError", result["error"])

    def test_unsupported_format_returns_error(self):
        result = self._run_with_stub("<html><body>not a feed</body></html>")
        self.assertEqual(result["status"], "error")
        self.assertIn("unsupported feed format", result["error"])

    def test_fetch_failure_returns_error_and_marks_nothing_seen(self):
        with mock.patch.object(feeds, "_fetch_feed",
                               side_effect=ValueError("boom")):
            result = feeds.feed_digest(FEED_URL)
        self.assertEqual(result["status"], "error")
        self.assertIn("ValueError", result["error"])
        self.assertEqual(seen_ids(FEED_URL), set())

    def test_registered_in_registry(self):
        self.assertIn("feed_digest", registry.names())
        defs = {d["function"]["name"]: d for d in registry.function_definitions()}
        self.assertEqual(defs["feed_digest"]["function"]["parameters"]["required"],
                         ["url"])

    def test_callable_via_registry(self):
        result = registry.call("feed_digest", {"url": "ftp://example.test/x.xml"})
        self.assertEqual(result["status"], "error")


class TestParseFeed(unittest.TestCase):
    def test_rss_items_keep_order_and_fields(self):
        feed = parse_feed(RSS_FEED)
        self.assertEqual(feed["title"], "Example Blog")
        self.assertEqual(len(feed["items"]), 2)
        self.assertEqual(feed["items"][1]["published"],
                         "Tue, 24 Nov 2026 08:00:00 GMT")
        self.assertEqual(feed["items"][1]["summary"], "Follow-up post.")

    def test_empty_feed_has_no_items(self):
        feed = parse_feed(
            '<?xml version="1.0"?><rss version="2.0">'
            "<channel><title>Empty</title></channel></rss>")
        self.assertEqual(feed["items"], [])


if __name__ == "__main__":
    unittest.main()

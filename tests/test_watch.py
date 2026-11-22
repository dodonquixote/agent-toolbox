import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent_toolbox import registry
from agent_toolbox.tools import watch
from agent_toolbox.tools.watch import diff_lines, get_snapshot, state_path

URL = "https://example.test/changelog"

PAGE_V1 = "Version 1.0\nFeatures:\n- Fast startup\n- Dark mode"
PAGE_V2 = "Version 1.1\nFeatures:\n- Fast startup\n- Dark mode\n- Offline sync"


class WatchTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "state.db"
        self._state_patch = mock.patch.object(
            watch, "state_path", return_value=self.db)
        self._state_patch.start()
        self.addCleanup(self._state_patch.stop)
        self.addCleanup(self._tmp.cleanup)

    def _run_with_stub(self, pages):
        """Run watch_page with fetch_url stubbed to return `pages[url]`."""
        def fake_fetch(url, max_chars):
            if url in pages:
                return {"title": "Changelog", "text": pages[url]}
            raise ValueError("bad url")

        with mock.patch.object(watch, "_fetch_page", side_effect=fake_fetch):
            return watch.watch_page(URL)

    def test_first_run_records_snapshot(self):
        result = self._run_with_stub({URL: PAGE_V1})
        self.assertEqual(result["status"], "first_seen")
        self.assertFalse(result["changed"])
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["line_count"], 4)
        self.assertIsNone(result["previous_checked_at"])
        self.assertIsNone(result["error"])
        snapshot = get_snapshot(URL)
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["text"], PAGE_V1)

    def test_repeat_unchanged_page(self):
        self._run_with_stub({URL: PAGE_V1})
        result = self._run_with_stub({URL: PAGE_V1})
        self.assertEqual(result["status"], "unchanged")
        self.assertFalse(result["changed"])
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertIsNotNone(result["previous_checked_at"])

    def test_changed_page_reports_added_and_removed(self):
        self._run_with_stub({URL: PAGE_V1})
        result = self._run_with_stub({URL: PAGE_V2})
        self.assertEqual(result["status"], "changed")
        self.assertTrue(result["changed"])
        self.assertEqual(result["added"], ["Version 1.1", "- Offline sync"])
        self.assertEqual(result["removed"], ["Version 1.0"])
        # Snapshot is updated, so a third identical check is unchanged.
        result = self._run_with_stub({URL: PAGE_V2})
        self.assertEqual(result["status"], "unchanged")

    def test_different_urls_are_independent(self):
        other = "https://example.test/other"
        self._run_with_stub({URL: PAGE_V1})
        with mock.patch.object(
                watch, "_fetch_page",
                return_value={"title": "Other", "text": "Hello"}):
            result = watch.watch_page(other)
        self.assertEqual(result["status"], "first_seen")
        self.assertEqual(get_snapshot(URL)["text"], PAGE_V1)
        self.assertEqual(get_snapshot(other)["text"], "Hello")

    def test_fetch_failure_returns_error_and_stores_nothing(self):
        with mock.patch.object(watch, "_fetch_page",
                               side_effect=ValueError("boom")):
            result = watch.watch_page(URL)
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["changed"])
        self.assertIn("ValueError", result["error"])
        self.assertIsNone(get_snapshot(URL))

    def test_registered_in_registry(self):
        self.assertIn("watch_page", registry.names())
        defs = {d["function"]["name"]: d for d in registry.function_definitions()}
        self.assertEqual(defs["watch_page"]["function"]["parameters"]["required"],
                         ["url"])

    def test_callable_via_registry(self):
        # Invalid scheme fails inside fetch_url before any network use.
        result = registry.call("watch_page", {"url": "ftp://example.test/x"})
        self.assertEqual(result["status"], "error")


class TestDiffLines(unittest.TestCase):
    def test_added_removed_and_unchanged(self):
        diff = diff_lines("a\nb\nc", "a\nB\nc\nd")
        self.assertEqual(diff["added"], ["B", "d"])
        self.assertEqual(diff["removed"], ["b"])

    def test_identical_texts_have_empty_diff(self):
        self.assertEqual(diff_lines("a\nb", "a\nb"), {"added": [], "removed": []})

    def test_empty_old_text(self):
        self.assertEqual(diff_lines("", "a\nb"), {"added": ["a", "b"], "removed": []})


class TestStatePath(unittest.TestCase):
    def test_env_override(self):
        with mock.patch.dict(os.environ, {"AGENT_TOOLBOX_STATE": "/tmp/x.db"}):
            self.assertEqual(state_path(), Path("/tmp/x.db"))

    def test_default_under_home(self):
        # The default is fixed at import time from the real home dir, so
        # compare against the module constant rather than recomputing it
        # after clearing the environment.
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(state_path(), watch.DEFAULT_STATE_DB)


if __name__ == "__main__":
    unittest.main()
